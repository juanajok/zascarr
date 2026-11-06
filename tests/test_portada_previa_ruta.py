"""
tests/test_portada_previa_ruta.py

#435 (BL-PORT5): en `GET /ui/series/{id}/portada`, una portada previa con resolución suficiente
(hoy la caché antigua `covers/<id>.jpg`, ancho >= 300 px) se sirve ANTES que `covers/v2` y que los
archivos. Sin tocar disco ni red: no se extrae, no se consulta `File`, no se escribe `v2`, no se
copia la antigua.
"""
from __future__ import annotations

import hashlib
import io
import os
import random
import threading
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
import structlog
from fastapi.testclient import TestClient
from PIL import Image

import zascarr.web.series as wseries
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.utils.cover import CACHE_VERSION


def _jpeg(ancho: int, color=(30, 90, 160), alto: int = 60) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _cbz(path: Path, color=(200, 30, 30)) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("001.jpg", _jpeg(600, color, 900))
    return path


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    """Cuenta las consultas de archivos: con una previa suficiente no debe haber ninguna."""

    def __init__(self, series, archivos):
        self._series, self._archivos, self.consultas = series, archivos, 0

    async def get(self, _model, _id):
        return self._series

    async def execute(self, _statement):
        self.consultas += 1
        return _Resultado(self._archivos)


@pytest.fixture
def montar(tmp_path, monkeypatch):
    """`montar(archivos=[])` → (series, covers, sesión, llamadas). `llamadas` registra los
    extractores y descargas que `portada()` intente: «no se toca nada» exige que queden vacías."""
    covers = tmp_path / "covers"
    covers.mkdir()
    settings = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
    llamadas: list[str] = []
    real = wseries.extract_cover_thumbnail

    def extractor(path, *a, **k):
        llamadas.append("extractor")
        return real(path, *a, **k)

    async def descarga(url, destino, **k):
        llamadas.append("descarga")
        return False

    monkeypatch.setattr(wseries, "extract_cover_thumbnail", extractor)
    monkeypatch.setattr(wseries, "fetch_and_cache_cover", descarga)

    def _montar(archivos=()):
        series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                        start_year=1977)
        sesion = _Sesion(series, [(str(p), None) for p in archivos])

        async def _get_db():
            yield sesion

        app.dependency_overrides[get_db] = _get_db
        return series, covers, sesion, llamadas

    try:
        yield _montar
    finally:
        app.dependency_overrides.pop(get_db, None)


def _antigua(covers: Path, series, ancho: int, **kw) -> Path:
    ruta = covers / f"{series.id}.jpg"
    ruta.write_bytes(_jpeg(ancho, **kw))
    return ruta


def _v2(covers: Path, series, ancho: int = 600, **kw) -> Path:
    (covers / CACHE_VERSION).mkdir(exist_ok=True)
    ruta = covers / CACHE_VERSION / f"{series.id}.jpg"
    ruta.write_bytes(_jpeg(ancho, **kw))
    return ruta


def _foto(covers: Path) -> dict[str, tuple[str, int]]:
    """Árbol de `covers/`: ruta relativa → (hash, mtime_ns). Para comprobar que no se toca nada."""
    return {
        str(p.relative_to(covers)): (
            hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in covers.rglob("*") if p.is_file()
    }


def _ancho(datos: bytes) -> int:
    with Image.open(io.BytesIO(datos)) as img:
        return img.width


class TestSeConservaLaPreviaSuficiente:

    def test_previa_suficiente_gana_al_archivo_aunque_v2_exista(self, tmp_path, montar):
        """Regresión (#435): `v2` se comprobaba primero y una serie con antigua de 320 px y un CBZ
        legible servía la primera página del archivo (v2) en vez de la portada ya buena."""
        series, covers, _s, llamadas = montar([_cbz(tmp_path / "01.cbz")])
        antigua = _antigua(covers, series, 320, color=(10, 200, 10))
        _v2(covers, series, 600, color=(200, 30, 30))

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and r.content == antigua.read_bytes()
        assert _ancho(r.content) == 320 and llamadas == []

    def test_cabeceras_etag_de_la_antigua_y_304(self, tmp_path, montar):
        """AC-01."""
        series, covers, _s, _l = montar([_cbz(tmp_path / "01.cbz")])
        antigua = _antigua(covers, series, 320)
        cliente = TestClient(app)

        r = cliente.get(f"/ui/series/{series.id}/portada")

        assert r.headers["etag"] == f'"{antigua.stat().st_mtime}"'
        assert r.headers["cache-control"] == "private, max-age=86400"
        assert r.headers["content-type"] == "image/jpeg"
        r2 = cliente.get(f"/ui/series/{series.id}/portada",
                         headers={"If-None-Match": r.headers["etag"]})
        assert r2.status_code == 304

    def test_no_consulta_archivos_ni_extrae_ni_descarga_ni_escribe(self, tmp_path, montar):
        """AC-02, AC-17, AC-18: sin consultas de `File`, extractor ni descargas; `covers/` igual."""
        series, covers, sesion, llamadas = montar([_cbz(tmp_path / "01.cbz")])
        series.cover_url = "https://comicvine.gamespot.com/a/uploads/x.jpg"
        _antigua(covers, series, 320)
        antes = _foto(covers)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200
        assert sesion.consultas == 0 and llamadas == []
        assert _foto(covers) == antes                 # ni v2 nueva, ni la antigua copiada o tocada
        assert not (covers / CACHE_VERSION).exists()

    def test_la_v2_ya_escrita_se_ignora_pero_queda_intacta(self, tmp_path, montar):
        """AC-06, FR-07: la v2 de las cinco series de la Pi ni se borra ni se regenera."""
        series, covers, _s, _l = montar([_cbz(tmp_path / "01.cbz")])
        _antigua(covers, series, 320)
        v2 = _v2(covers, series, 600)
        antes = (v2.read_bytes(), v2.stat().st_mtime_ns)

        TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert (v2.read_bytes(), v2.stat().st_mtime_ns) == antes

    def test_umbral_300_es_suficiente_y_299_no(self, tmp_path, montar):
        """AC-03 en la ruta."""
        series, covers, _s, llamadas = montar([_cbz(tmp_path / "01.cbz")])
        _antigua(covers, series, 300)
        r = TestClient(app).get(f"/ui/series/{series.id}/portada")
        assert _ancho(r.content) == 300 and llamadas == []

        series2, _c, _s2, llamadas2 = montar([_cbz(tmp_path / "02.cbz")])
        _antigua(covers, series2, 299)
        r2 = TestClient(app).get(f"/ui/series/{series2.id}/portada")
        assert _ancho(r2.content) == 600 and llamadas2 == ["extractor"]   # el archivo, a 600

    def test_con_un_rar_primero_conserva_la_antigua_sin_abrirlo(self, tmp_path, montar):
        """AC-10: con previa suficiente no se abre ningún archivo (tampoco el RAR)."""
        rar = tmp_path / "01.cbr"
        rar.write_bytes(b"Rar!\x1a\x07\x01\x00relleno")
        series, covers, sesion, llamadas = montar([rar])
        antigua = _antigua(covers, series, 320)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.content == antigua.read_bytes() and sesion.consultas == 0 and llamadas == []


class TestSiNoHayPreviaSuficienteTodoComoHoy:

    def test_antigua_de_100_px_se_regenera_desde_el_archivo(self, tmp_path, montar):
        """AC-04 (Tebeosfera 100×100)."""
        series, covers, _s, llamadas = montar([_cbz(tmp_path / "01.cbz")])
        antigua = _antigua(covers, series, 100, alto=100)
        antes = antigua.read_bytes()

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert _ancho(r.content) == 600 and llamadas == ["extractor"]
        assert (covers / CACHE_VERSION / f"{series.id}.jpg").exists()
        assert antigua.read_bytes() == antes          # la antigua no se toca

    def test_sin_antigua_la_cascada_es_la_de_main(self, tmp_path, montar):
        """AC-05."""
        series, covers, _s, llamadas = montar([_cbz(tmp_path / "01.cbz")])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and llamadas == ["extractor"]
        assert (covers / CACHE_VERSION / f"{series.id}.jpg").exists()

    def test_v2_ya_escrita_con_antigua_pequena_se_sirve_v2(self, tmp_path, montar):
        """AC-07."""
        series, covers, sesion, llamadas = montar([_cbz(tmp_path / "01.cbz")])
        _antigua(covers, series, 100, alto=100)
        v2 = _v2(covers, series, 600)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.content == v2.read_bytes() and sesion.consultas == 0 and llamadas == []

    def test_sin_archivo_utilizable_y_antigua_pequena_se_sirve_la_antigua(self, tmp_path, montar):
        """AC-10 (antigua de 100 px y primer archivo RAR): la antigua, sin leer el RAR."""
        rar = tmp_path / "01.cbr"
        rar.write_bytes(b"Rar!\x1a\x07\x01\x00relleno")
        series, covers, _s, llamadas = montar([rar])
        antigua = _antigua(covers, series, 100, alto=100)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.content == antigua.read_bytes() and llamadas == []

    def test_nada_de_nada_es_404(self, tmp_path, montar):
        series, _c, _s, _l = montar([])
        series.cover_url = None
        assert TestClient(app).get(f"/ui/series/{series.id}/portada").status_code == 404


class TestFallaCerradoEnLaRuta:

    def test_la_antigua_que_desaparece_antes_del_etag_no_da_500(self, montar, monkeypatch):
        """Si el fichero se borra antes de calcular el ETag, se sirve con el ETag de sus bytes."""
        series, covers, _s, _l = montar([])
        antigua = _antigua(covers, series, 320)

        def sin_fichero(_ruta):
            raise FileNotFoundError(2, "No such file")
        monkeypatch.setattr(wseries, "_etag_for", sin_fichero)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and r.content == antigua.read_bytes()
        assert r.headers["etag"] == wseries._etag_de_bytes(antigua.read_bytes())

    @pytest.mark.parametrize("contenido", [b"", b"no soy una imagen", _jpeg(400)[:20]])
    def test_antigua_ilegible_no_bloquea_la_cascada_ni_da_500(self, tmp_path, montar, contenido):
        """AC-08."""
        series, covers, _s, llamadas = montar([_cbz(tmp_path / "01.cbz")])
        (covers / f"{series.id}.jpg").write_bytes(contenido)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and _ancho(r.content) == 600 and llamadas == ["extractor"]

    def test_permiso_denegado_en_la_antigua_no_da_500(self, tmp_path, montar):
        """AC-16."""
        series, covers, _s, _l = montar([_cbz(tmp_path / "01.cbz")])
        antigua = _antigua(covers, series, 400)
        antigua.chmod(0)
        try:
            if os.access(antigua, os.R_OK):
                pytest.skip("el usuario puede leer aunque el fichero no tenga permisos (root)")
            r = TestClient(app).get(f"/ui/series/{series.id}/portada")
        finally:
            antigua.chmod(0o644)
        assert r.status_code == 200 and _ancho(r.content) == 600


class TestRegistroDeLaRuta:
    def test_ningun_evento_lleva_ruta_nombre_de_archivo_ni_de_serie(self, tmp_path, montar):
        """AC-13."""
        series, covers, _s, _l = montar([_cbz(tmp_path / "secreto-no-salir.cbz")])
        _antigua(covers, series, 320)

        with structlog.testing.capture_logs() as registros:
            TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert any(r["event"] == "cover.previa_suficiente" for r in registros)
        texto = str(registros)
        assert "secreto-no-salir" not in texto and str(tmp_path) not in texto
        assert str(series.id) not in texto and "Thorgal" not in texto


class TestAntiguaTruncadaEnLaRuta:
    """A-1 de QA, reproducido en servidor real: una antigua de 320 px cortada a mitad del cuerpo se
    servía (~70 000 bytes que no se decodifican) en vez del CBZ legible a 600 px de la base."""

    @pytest.mark.parametrize("corte", [0.6, 0.1, 700])
    def test_una_antigua_cortada_no_se_sirve_y_sigue_la_cascada(self, tmp_path, montar, corte):
        series, covers, _s, llamadas = montar([_cbz(tmp_path / "01.cbz")])
        azar = random.Random(7)
        img = Image.new("RGB", (320, 480))
        img.putdata([(azar.randrange(256), azar.randrange(256), azar.randrange(256))
                     for _ in range(320 * 480)])
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80)
        entero = buf.getvalue()
        recortado = entero[:corte] if corte > 1 else entero[:int(len(entero) * corte)]
        (covers / f"{series.id}.jpg").write_bytes(recortado)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and llamadas == ["extractor"]
        assert _ancho(r.content) == 600              # el CBZ, no la antigua rota
        with Image.open(io.BytesIO(r.content)) as servida:
            servida.load()                           # lo servido se decodifica entero


class TestNoBloqueaElBucle:
    def test_la_lectura_de_la_previa_va_en_otro_hilo(self, montar, monkeypatch):
        """CLAUDE.md §4: hasta 8 MiB de lectura más Pillow no van en el event loop. Se compara el
        hilo donde corre la regla con el del bucle (donde corre `db.get`)."""
        series, covers, sesion, _l = montar([])
        _antigua(covers, series, 320)
        hilos: dict[str, int] = {}
        real_get = sesion.get

        async def get(modelo, id_):
            hilos["bucle"] = threading.get_ident()
            return await real_get(modelo, id_)
        sesion.get = get
        real = wseries.portada_previa_suficiente

        def espia(*a, **k):
            hilos["regla"] = threading.get_ident()
            return real(*a, **k)
        monkeypatch.setattr(wseries, "portada_previa_suficiente", espia)

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200
        assert hilos["regla"] != hilos["bucle"]
