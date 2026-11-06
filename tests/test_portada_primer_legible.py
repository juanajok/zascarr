"""
tests/test_portada_primer_legible.py

#419 (BL-PORT4): la portada de serie sale del PRIMER archivo, por `sort_order`, que pueda darla.
Antes `portada()` pedía solo uno (`limit(1)`): si ese no daba portada, no probaba el siguiente.
CBZ reales en `tmp_path`; la sesión es falsa y la caché se redirige, como en `test_cover_cache.py`.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest
import structlog
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.dialects import postgresql

import zascarr.web.series as wseries
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.utils.cover import CACHE_VERSION


def _jpeg(color: tuple[int, int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (600, 900), color=color).save(buf, format="JPEG")
    return buf.getvalue()


def _cbz(path: Path, color: tuple[int, int, int] = (120, 40, 200)) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("001.jpg", _jpeg(color))
    return path


def _tebeo_zip(path: Path, color: tuple[int, int, int] = (120, 40, 200)) -> Path:
    """ZIP con 12 páginas: un tebeo comprobado (un .cbr que es ZIP solo se lee así; ver #307)."""
    with zipfile.ZipFile(path, "w") as zf:
        for i in range(12):
            zf.writestr(f"{i + 1:03d}.jpg", _jpeg(color))
    return path


def _cbz_sin_imagenes(path: Path) -> Path:
    """Un ZIP válido, de extensión .cbz, sin ninguna página: «plausible» pero sin portada."""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("leeme.txt", "nada")
    return path


def _cbz_roto(path: Path) -> Path:
    path.write_bytes(b"esto no es un zip")
    return path


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    def __init__(self, series: Series, archivos: list[tuple[str, dict | None]]):
        self._series = series
        self._archivos = archivos
        self.sentencias: list[str] = []

    async def get(self, _model, _id):
        return self._series

    async def execute(self, statement):
        self.sentencias.append(str(statement.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})))
        return _Resultado(self._archivos)


@pytest.fixture
def montar(tmp_path, monkeypatch):
    """`montar(archivos)` → (series, covers, sesión, aperturas). `aperturas` apunta cada archivo
    que `portada()` intenta abrir (se envuelve el extractor real, que sigue leyendo de verdad)."""
    covers = tmp_path / "covers"
    settings = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)
    aperturas: list[str] = []
    real = wseries.extract_cover_thumbnail

    def espia(path, *a, **k):
        aperturas.append(Path(path).name)
        return real(path, *a, **k)

    monkeypatch.setattr(wseries, "extract_cover_thumbnail", espia)

    def _montar(archivos):
        series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                        start_year=1977)
        sesion = _Sesion(series, [(str(p), fc) for p, fc in archivos])

        async def _get_db():
            yield sesion

        app.dependency_overrides[get_db] = _get_db
        return series, covers, sesion, aperturas

    try:
        yield _montar
    finally:
        app.dependency_overrides.pop(get_db, None)


def _v2(covers: Path, series: Series) -> Path:
    return covers / CACHE_VERSION / f"{series.id}.jpg"


def _color_medio(datos: bytes) -> tuple[int, int, int]:
    with Image.open(io.BytesIO(datos)) as img:
        return img.convert("RGB").getpixel((img.width // 2, img.height // 2))


class TestPortadaDelPrimerArchivoLegible:

    def test_primer_archivo_ilegible_no_impide_usar_un_cbz_posterior(self, tmp_path, montar):
        """Regresión (#419): el `limit(1)` miraba solo el primer archivo; con un .cbz roto delante,
        la serie se quedaba sin portada aunque el siguiente número era un CBZ perfecto."""
        malo = _cbz_sin_imagenes(tmp_path / "01.cbz")
        bueno = _cbz(tmp_path / "02.cbz", color=(200, 30, 30))
        series, covers, _s, aperturas = montar([(malo, None), (bueno, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200
        assert aperturas == ["01.cbz", "02.cbz"]
        r_, g_, b_ = _color_medio(r.content)
        assert r_ > 150 and g_ < 90           # la portada es la del posterior (rojiza)
        assert _v2(covers, series).exists()   # y se cachea en v2 como cualquier otra

    def test_primer_archivo_legible_es_el_que_se_usa_y_no_se_abre_otro(self, tmp_path, montar):
        primero = _cbz(tmp_path / "01.cbz", color=(30, 30, 200))
        segundo = _cbz(tmp_path / "02.cbz", color=(200, 30, 30))
        series, covers, _s, aperturas = montar([(primero, None), (segundo, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200
        assert aperturas == ["01.cbz"]
        assert _color_medio(r.content)[2] > 150      # azulada: la del primero

    def test_sin_ningun_legible_sigue_la_cascada_con_la_cache_antigua(self, tmp_path, montar):
        series, covers, _s, aperturas = montar([(_cbz_roto(tmp_path / "01.cbz"), None),
                                               (_cbz_sin_imagenes(tmp_path / "02.cbz"), None)])
        covers.mkdir(parents=True)
        (covers / f"{series.id}.jpg").write_bytes(_jpeg((10, 200, 10)))

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200
        assert _color_medio(r.content)[1] > 150      # la caché antigua, sin copiarla a v2
        assert not _v2(covers, series).exists()

    def test_sin_nada_que_servir_es_404_sin_500(self, tmp_path, montar):
        series, covers, _s, _a = montar([(_cbz_roto(tmp_path / "01.cbz"), None)])
        series.cover_url = None

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 404

    def test_los_que_puede_tener_portada_descarta_no_se_abren(self, tmp_path, montar):
        """Un .cbr RAR (firma guardada) no puede dar portada: ni se abre ni gasta intento."""
        rar = tmp_path / "01.cbr"
        rar.write_bytes(b"Rar!\x1a\x07\x01\x00")
        pdf = tmp_path / "02.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        bueno = _cbz(tmp_path / "03.cbz")
        series, covers, _s, aperturas = montar([
            (rar, {"firma": "rar"}), (pdf, None), (bueno, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200
        assert aperturas == ["03.cbz"]

    def test_el_tope_de_intentos_acota_las_aperturas_por_peticion(self, tmp_path, montar):
        """Con N archivos plausibles que fallan no se abre uno más, aunque detrás haya un bueno."""
        tope = wseries.MAX_INTENTOS_PORTADA
        rotos = [(_cbz_sin_imagenes(tmp_path / f"{i:02d}.cbz"), None)
                 for i in range(tope)]
        bueno = _cbz(tmp_path / "99.cbz")
        series, covers, _s, aperturas = montar([*rotos, (bueno, None)])
        series.cover_url = None

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert tope == 3
        assert len(aperturas) == tope and "99.cbz" not in aperturas
        assert r.status_code == 404

    def test_los_descartados_no_gastan_intentos(self, tmp_path, montar):
        """Mutación: si el contador sube antes del filtro, 3 .pdf delante agotarían el tope."""
        pdfs = []
        for i in range(wseries.MAX_INTENTOS_PORTADA + 2):
            p = tmp_path / f"{i:02d}.pdf"
            p.write_bytes(b"%PDF-1.4")
            pdfs.append((p, None))
        bueno = _cbz(tmp_path / "99.cbz")
        series, _c, _s, aperturas = montar([*pdfs, (bueno, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and aperturas == ["99.cbz"]

    def test_la_consulta_excluye_ausentes_y_sigue_el_orden_de_sort_order(self, tmp_path, montar):
        series, _c, sesion, _a = montar([])
        series.cover_url = None

        TestClient(app).get(f"/ui/series/{series.id}/portada")

        sql = sesion.sentencias[0]
        assert "is_missing" in sql and "sort_order" in sql
        # recorre candidatos: el tope de filas es el de archivos evaluados, no 1
        assert wseries.MAX_EVALUADOS_PORTADA == 50
        assert f"LIMIT {wseries.MAX_EVALUADOS_PORTADA}" in sql

    def test_un_candidato_fallido_se_registra_sin_ruta(self, tmp_path, montar):
        malo = _cbz_sin_imagenes(tmp_path / "secreto-no-salir.cbz")
        bueno = _cbz(tmp_path / "02.cbz")
        series, _c, _s, _a = montar([(malo, None), (bueno, None)])

        with structlog.testing.capture_logs() as registros:
            TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert any(r["event"] == "cover.candidato_sin_portada" for r in registros)
        assert "secreto-no-salir" not in str(registros) and str(tmp_path) not in str(registros)


class TestFormatoDesconocidoSeDecidePorFirma:
    """#422, criterio 2 de #419: solo se descarta sin leer la ausencia CONOCIDA. Con el formato sin
    guardar (o ilegible) un `.cbr` que por dentro es ZIP sigue dando portada, como hoy; un RAR no
    gasta intento."""

    def test_cbr_zip_sin_formato_guardado_sigue_dando_portada_por_firma(self, tmp_path, montar):
        """Regresión: descartar por extensión saltaba este .cbr, que hoy sí da portada."""
        cbr = _tebeo_zip(tmp_path / "01.cbr", color=(200, 30, 30))
        series, covers, _s, aperturas = montar([(cbr, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and aperturas == ["01.cbr"]
        assert _color_medio(r.content)[0] > 150

    def test_cbr_zip_con_lectura_ilegible_guardada_se_decide_por_firma(self, tmp_path, montar):
        cbr = _tebeo_zip(tmp_path / "01.cbr", color=(200, 30, 30))
        series, _c, _s, aperturas = montar([(cbr, {"firma": "ilegible"})])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and aperturas == ["01.cbr"]

    def test_cbr_rar_sin_formato_guardado_no_gasta_intento_ni_se_abre(self, tmp_path, montar):
        """Mutación: si un RAR sin formato consumiera intento, estos 4 agotarían el tope de 3."""
        rars = []
        for i in range(wseries.MAX_INTENTOS_PORTADA + 1):
            rar = tmp_path / f"{i:02d}.cbr"
            rar.write_bytes(b"Rar!\x1a\x07\x01\x00relleno")
            rars.append((rar, None))
        bueno = _cbz(tmp_path / "99.cbz")
        series, _c, _s, aperturas = montar([*rars, (bueno, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and aperturas == ["99.cbz"]

    def test_un_cbz_que_por_firma_no_es_zip_no_se_abre_ni_gasta_intento(self, tmp_path, montar):
        rotos = [(_cbz_roto(tmp_path / f"{i:02d}.cbz"), None)
                 for i in range(wseries.MAX_INTENTOS_PORTADA + 1)]
        bueno = _cbz(tmp_path / "99.cbz")
        series, _c, _s, aperturas = montar([*rotos, (bueno, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and aperturas == ["99.cbz"]

    def test_la_consulta_trae_solo_el_formato_y_no_todo_el_metadato(self, tmp_path, montar):
        series, _c, sesion, _a = montar([])
        series.cover_url = None

        TestClient(app).get(f"/ui/series/{series.id}/portada")

        sql = sesion.sentencias[0]
        assert "formato_contenido" in sql

    def test_la_ausencia_conocida_se_descarta_sin_leer_el_archivo(self, tmp_path, montar):
        """El formato guardado manda sobre la firma: si dice RAR no se abre ni gasta intento,
        aunque el archivo (cambiado después) sea ahora un ZIP."""
        cambiado = _tebeo_zip(tmp_path / "01.cbr")
        bueno = _cbz(tmp_path / "02.cbz")
        series, _c, _s, aperturas = montar([(cambiado, {"firma": "rar"}), (bueno, None)])

        r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200 and aperturas == ["02.cbz"]
