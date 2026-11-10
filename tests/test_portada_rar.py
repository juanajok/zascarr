# ruff: noqa: E501
"""#418 (BL-PORT3) commit 3: la portada de serie sale del propio RAR, con `lsar`/`unar` FALSOS.

Cubre AC-01, 04, 06, 14..21, 25, 27..31, 33 y 34 de la spec. Los archivos RAR son ficheros con la
firma `Rar!\\x1a\\x07\\x00` (la firma es lo que decide); el contenido lo «extrae» el `unar` falso.
Cada prueba nombra el mecanismo que protege.
"""
from __future__ import annotations

import asyncio
import io
import json
import time
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
import structlog
from fastapi.testclient import TestClient
from PIL import Image

from tests._rar_falso import entrada, instalar
from zascarr.config import get_settings
from zascarr.core.formato_contenedor import tratamiento
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Firma, MotivoRar, Series, Tratamiento
from zascarr.utils import lector_rar, portada_rar
from zascarr.utils.cover import (
    CACHE_VERSION,
    es_candidato_de_portada,
    extract_cover_thumbnail,
    puede_tener_portada,
)
from zascarr.utils.lector_rar import EntradaRar, ErrorRar, Listado
from zascarr.utils.portada_rar import elegir_pagina, es_rar_candidato
from zascarr.web import series as wseries

FIRMA_RAR = b"Rar!\x1a\x07\x00"


def _jpeg(ancho: int, alto: int = 0, color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto or ancho * 3 // 2), color).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _rar(ruta: Path, relleno: int = 100) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_bytes(FIRMA_RAR + b"x" * relleno)
    return ruta


def _cbz(ruta: Path, color=(30, 30, 200)) -> Path:
    with zipfile.ZipFile(ruta, "w") as zf:
        for i in range(12):
            zf.writestr(f"{i:03d}.jpg", _jpeg(500, 750, color))
    return ruta


def _cbz_roto(ruta: Path) -> Path:
    ruta.write_bytes(b"PK\x03\x04" + b"no es un zip de verdad")
    return ruta


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def all(self):
        return self._filas


class _Sesion:
    def __init__(self, series, archivos):
        self._series = series
        self.archivos = [(uuid4(), str(p), fc) for p, fc in archivos]

    async def get(self, _model, _id):
        return self._series

    async def execute(self, _statement):
        return _Resultado(self.archivos)


@pytest.fixture
def falso(tmp_path, monkeypatch):
    f = instalar(tmp_path / "bin", monkeypatch)
    f.contenido(_jpeg(1800))
    return f


@pytest.fixture
def mundo(tmp_path, monkeypatch, falso):
    """`mundo(archivos)` → (series, covers, sesión). La caché va a `tmp_path`, nunca a la real."""
    covers = tmp_path / "covers"
    settings = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)

    def _montar(archivos, cover_url=None):
        series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                        start_year=1977, cover_url=cover_url)
        sesion = _Sesion(series, archivos)

        async def _get_db():
            yield sesion

        app.dependency_overrides[get_db] = _get_db
        return series, covers, sesion

    try:
        yield _montar
    finally:
        app.dependency_overrides.pop(get_db, None)


def _pedir(series) -> httpx.Response:
    return TestClient(app).get(f"/ui/series/{series.id}/portada")


def _ancho(contenido: bytes) -> int:
    with Image.open(io.BytesIO(contenido)) as img:
        return img.width


def _unars(falso) -> list[str]:
    return [x for x in falso.llamadas() if x.startswith("unar")]


def _lsars(falso) -> list[str]:
    return [x for x in falso.llamadas() if x.startswith("lsar")]


def _listado_de_una_pagina(falso, nombre="01.jpg"):
    datos = (falso.carpeta / "contenido.bin").read_bytes()
    import zlib
    falso.listado([entrada(0, nombre, len(datos), zlib.crc32(datos))])


def _marcas(covers: Path) -> list[Path]:
    carpeta = covers / CACHE_VERSION / "fallos"
    return sorted(carpeta.glob("*.json")) if carpeta.exists() else []


# ── Quién es candidato (AC-01, R-8) ────────────────────────────────────────────────────────────────
class TestCandidatoRar:
    def test_firma_rar_con_cbr_es_candidato_firma_zip_sigue_el_camino_zip(self, tmp_path):
        assert es_candidato_de_portada(_rar(tmp_path / "a.cbr")) is True
        assert es_rar_candidato(_rar(tmp_path / "b.cbr")) is True
        zip_cbr = _cbz(tmp_path / "c.cbr")
        assert es_candidato_de_portada(zip_cbr) is True
        assert es_rar_candidato(zip_cbr) is False        # un ZIP disfrazado NO va por el lector RAR

    def test_firma_rar_con_otra_extension_no_es_candidato(self, tmp_path):
        assert es_candidato_de_portada(_rar(tmp_path / "a.txt")) is False
        assert es_candidato_de_portada(_rar(tmp_path / "a.cb7")) is False

    @pytest.mark.parametrize("nombre", ["a.rar", "a"])
    def test_rar_y_sin_extension_con_firma_rar_se_intentan(self, tmp_path, nombre):
        assert es_rar_candidato(_rar(tmp_path / nombre)) is True

    def test_con_formato_guardado_no_se_lee_el_disco(self, tmp_path):
        inexistente = tmp_path / "no_existe.cbr"
        assert es_rar_candidato(inexistente, {"firma": "rar"}) is True
        assert es_rar_candidato(inexistente, {"firma": "zip", "clase": "tebeo"}) is False

    def test_un_cbr_que_no_es_rar_ni_zip_no_es_candidato(self, tmp_path):
        f = tmp_path / "a.cbr"
        f.write_bytes(b"texto cualquiera")
        assert es_candidato_de_portada(f) is False

    def test_la_extension_no_decide_un_cbr_zip_con_formato_ilegible_guardado(self, tmp_path):
        assert es_rar_candidato(_rar(tmp_path / "a.cbr"), {"firma": "ilegible"}) is True


# ── Elegir la página (AC-04) ──────────────────────────────────────────────────────────────────────
def _e(i, nombre, directorio=False):
    return EntradaRar(i, nombre, 10, None, directorio, False)


class TestElegirPagina:
    def test_primera_en_orden_natural_sin_macosx_ni_apple_double(self):
        lis = Listado((_e(0, "10.jpg"), _e(1, "2.jpg"), _e(2, "__MACOSX/1.jpg"), _e(3, "._1.jpg")))
        assert elegir_pagina(lis, ".cbr").nombre == "2.jpg"

    def test_el_ruido_de_sistema_se_descarta_aunque_ordene_antes_que_la_portada(self):
        """QA (mutantes 21/21b): con estos nombres el orden natural pondría el ruido PRIMERO."""
        lis = Listado((_e(0, "._portada.jpg"), _e(1, "__MACOSX/portada.jpg"), _e(2, "portada.jpg")))
        assert sorted(e.nombre.lower() for e in lis.entradas)[0] == "._portada.jpg"       # la trampa existe
        assert elegir_pagina(lis, ".cbr").nombre == "portada.jpg"
        solo_ruido = Listado((_e(0, "._a.jpg"), _e(1, "__MACOSX/a.jpg")))
        with pytest.raises(ErrorRar) as exc:
            elegir_pagina(solo_ruido, ".cbr")
        assert exc.value.motivo is MotivoRar.SIN_IMAGENES

    def test_con_contenedores_dentro_de_un_cbr_tambien_es_un_paquete(self):
        """QA (mutante 35): el caso `.cbr` (con `.rar` ya lo da MIN_IMAGENES)."""
        lis = Listado((_e(0, "01.jpg"), _e(1, "otro.cbz")))
        with pytest.raises(ErrorRar) as exc:
            elegir_pagina(lis, ".cbr")
        assert exc.value.motivo is MotivoRar.PAQUETE

    def test_sin_imagenes(self):
        with pytest.raises(ErrorRar) as exc:
            elegir_pagina(Listado((_e(0, "ComicInfo.xml"), _e(1, "carpeta", True))), ".cbr")
        assert exc.value.motivo is MotivoRar.SIN_IMAGENES

    def test_con_contenedores_dentro_es_un_paquete(self):
        lis = Listado((_e(0, "01.jpg"), _e(1, "otro.cbz")))
        with pytest.raises(ErrorRar) as exc:
            elegir_pagina(lis, ".rar")
        assert exc.value.motivo is MotivoRar.PAQUETE

    def test_un_rar_que_no_es_cbr_exige_ser_un_tebeo(self):
        pocas = Listado(tuple(_e(i, f"{i}.jpg") for i in range(3)))
        with pytest.raises(ErrorRar) as exc:
            elegir_pagina(pocas, ".rar")
        assert exc.value.motivo is MotivoRar.PAQUETE
        assert elegir_pagina(pocas, ".cbr").nombre == "0.jpg"      # un .cbr corto sí

    def test_un_tebeo_en_rar_sin_extension_cbr_pasa_con_suficientes_imagenes(self):
        lis = Listado(tuple(_e(i, f"{i:02d}.jpg") for i in range(12)) + (_e(12, "ComicInfo.xml"),))
        assert elegir_pagina(lis, ".rar").nombre == "00.jpg"


# ── La portada por la ruta (O-1, AC-07 con falsos, AC-20) ─────────────────────────────────────────
class TestPortadaPorLaRuta:
    def test_un_cbr_rar_da_portada_en_v3_a_600(self, tmp_path, mundo, falso):
        _listado_de_una_pagina(falso)
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        r = _pedir(series)
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
        v3 = covers / "v3" / f"{series.id}.jpg"
        assert v3.exists() and _ancho(r.content) == 600
        assert r.content == v3.read_bytes()
        assert r.headers["etag"] == f'"{v3.stat().st_mtime}"'

    def test_la_segunda_peticion_sale_de_v3_sin_lanzar_nada(self, tmp_path, mundo, falso):
        _listado_de_una_pagina(falso)
        series, _c, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        _pedir(series)
        llamadas = len(falso.llamadas())
        assert _pedir(series).status_code == 200
        assert len(falso.llamadas()) == llamadas

    def test_nunca_se_amplia_una_portada_pequena(self, tmp_path, mundo, falso):
        """Mutación: ampliar una imagen pequeña a 600."""
        falso.contenido(_jpeg(300))
        _listado_de_una_pagina(falso)
        series, _c, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        assert _ancho(_pedir(series).content) == 300

    def test_se_pide_la_pagina_elegida_por_indice(self, tmp_path, mundo, falso):
        datos = (falso.carpeta / "contenido.bin").read_bytes()
        falso.listado([entrada(0, "10.jpg", len(datos)), entrada(1, "2.jpg", len(datos))])
        series, _c, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        _pedir(series)
        assert _unars(falso)[0].split()[-1] == "1"

    def test_una_imagen_con_mas_pixeles_que_el_tope_falla_sin_decodificar(self, monkeypatch):
        """AC-06: se mide la CABECERA; `Image.load` no llega a llamarse."""
        grande = _jpeg(200)
        monkeypatch.setattr(portada_rar, "MAX_PIXELES_PORTADA", 100)
        cargas = []
        real = Image.Image.load
        monkeypatch.setattr(Image.Image, "load", lambda self, *a, **k: (cargas.append(1), real(self, *a, **k))[1])
        with pytest.raises(ErrorRar) as exc:
            portada_rar._jpeg_de(grande, 600)
        assert exc.value.motivo is MotivoRar.DEMASIADO_GRANDE and cargas == []

    def test_imagen_que_no_decodifica_es_ilegible(self):
        with pytest.raises(ErrorRar) as exc:
            portada_rar._jpeg_de(b"no soy una imagen", 600)
        assert exc.value.motivo is MotivoRar.ILEGIBLE

    def test_un_zip_con_extension_cbr_sigue_el_camino_zip_sin_lanzar_el_lector(self, tmp_path, mundo, falso):
        series, covers, _ = mundo([(_cbz(tmp_path / "01.cbr"), None)])
        assert _pedir(series).status_code == 200
        assert falso.llamadas() == []


# ── El fallo recordado (AC-14..19) ────────────────────────────────────────────────────────────────
class TestFalloRecordado:
    def _cifrado(self, falso):
        falso.modo(lsar="rc1", mensaje="This archive requires a password")

    def test_cifrado_deja_marca_y_la_segunda_peticion_no_lanza_nada(self, tmp_path, mundo, falso):
        """Mutación: reabrir un archivo marcado."""
        self._cifrado(falso)
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        assert _pedir(series).status_code == 404            # sin portada: sigue la cascada, ni 500 ni v3
        assert len(_lsars(falso)) == 1
        (marca,) = _marcas(covers)
        assert json.loads(marca.read_text())["motivo"] == "cifrado"
        assert _pedir(series).status_code == 404
        assert len(_lsars(falso)) == 1 and _unars(falso) == []

    def test_la_marca_no_lleva_ruta_ni_nombre(self, tmp_path, mundo, falso):
        self._cifrado(falso)
        rar = _rar(tmp_path / "Thorgal 01.cbr")
        series, covers, _ = mundo([(rar, None)])
        _pedir(series)
        texto = _marcas(covers)[0].read_text()
        assert set(json.loads(texto)) == {"v", "motivo", "tamano", "mtime_ns"}     # `t` solo en `tiempo` (FR-29)
        assert "Thorgal" not in texto and str(tmp_path) not in texto

    def test_marca_sin_huella_reabriria_un_archivo_cambiado(self, tmp_path, mundo, falso):
        """AC-15 / mutación «marca sin huella»: si cambia el tamaño o el mtime, se reintenta."""
        self._cifrado(falso)
        rar = _rar(tmp_path / "01.cbr")
        series, _c, _ = mundo([(rar, None)])
        _pedir(series)
        assert len(_lsars(falso)) == 1
        _pedir(series)
        assert len(_lsars(falso)) == 1                        # igual: no se reabre
        rar.write_bytes(FIRMA_RAR + b"y" * 200)               # cambia el tamaño
        _pedir(series)
        assert len(_lsars(falso)) == 2
        import os
        st = rar.stat()
        os.utime(rar, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))   # solo el mtime
        _pedir(series)
        assert len(_lsars(falso)) == 3

    def test_cambia_solo_el_tamano_con_el_mismo_mtime_y_se_reintenta(self, tmp_path, mundo, falso):
        """Mutación «marca sin tamaño»: una sustitución que conserva el mtime también invalida."""
        import os
        self._cifrado(falso)
        rar = _rar(tmp_path / "01.cbr")
        series, _c, _ = mundo([(rar, None)])
        _pedir(series)
        mtime = rar.stat().st_mtime_ns
        rar.write_bytes(FIRMA_RAR + b"z" * 300)
        os.utime(rar, ns=(mtime, mtime))
        assert rar.stat().st_mtime_ns == mtime
        _pedir(series)
        assert len(_lsars(falso)) == 2

    @pytest.mark.parametrize("motivo", [MotivoRar.HERRAMIENTA_AUSENTE, MotivoRar.INESPERADO])
    def test_un_motivo_del_entorno_que_llega_como_error_rar_no_deja_marca(
            self, tmp_path, mundo, falso, monkeypatch, motivo):
        """Mutación: recordar causas del entorno (FR-13)."""
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])

        def _falla(*a, **k):
            raise ErrorRar(motivo)

        monkeypatch.setattr(wseries, "portada_de_rar", _falla)
        assert _pedir(series).status_code == 404
        assert _marcas(covers) == []

    def test_otra_version_del_contrato_reintenta(self, tmp_path, mundo, falso, monkeypatch):
        self._cifrado(falso)
        series, _c, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        _pedir(series)
        _pedir(series)
        assert len(_lsars(falso)) == 1
        monkeypatch.setattr(portada_rar, "CONTRATO_PORTADA_RAR", portada_rar.CONTRATO_PORTADA_RAR + 1)
        _pedir(series)
        assert len(_lsars(falso)) == 2

    def test_herramienta_ausente_no_da_500_ni_marca_y_se_reintenta_despues(
            self, tmp_path, mundo, falso, monkeypatch):
        """AC-16: causa del ENTORNO: no se recuerda."""
        _listado_de_una_pagina(falso)
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        con_herramientas = monkeypatch.setenv
        vacio = tmp_path / "vacio"
        vacio.mkdir()
        import os
        ruta_buena = os.environ["PATH"]
        con_herramientas("PATH", str(vacio))
        assert _pedir(series).status_code == 404
        assert _marcas(covers) == []
        con_herramientas("PATH", ruta_buena)
        assert _pedir(series).status_code == 200            # la siguiente petición vuelve a comprobar

    def test_error_inesperado_no_se_recuerda(self, tmp_path, mundo, falso, monkeypatch):
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])

        def _revienta(*a, **k):
            raise RuntimeError("fallo del entorno")

        monkeypatch.setattr(wseries, "portada_de_rar", _revienta)
        assert _pedir(series).status_code == 404
        assert _marcas(covers) == []

    def test_fallo_al_escribir_la_marca_se_registra_y_la_peticion_sigue(self, tmp_path, mundo, falso, monkeypatch):
        """AC-17."""
        falso.modo(lsar="rc1", mensaje="")
        series, _c, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])

        def _sin_espacio(*a, **k):
            raise OSError(28, "No space left")

        monkeypatch.setattr("zascarr.utils.cover.write_cover_cache", _sin_espacio)
        with structlog.testing.capture_logs() as logs:
            r = _pedir(series)
        assert r.status_code == 404
        evento = [e for e in logs if e["event"] == "cover.marca_sin_escribir"]
        assert evento and evento[0]["motivo"] == "OSError" and evento[0]["errno"] == 28

    def test_el_registro_no_lleva_ruta_nombre_de_archivo_ni_de_serie(self, tmp_path, mundo, falso):
        """AC-18 / NFR-05."""
        falso.modo(lsar="rc1", mensaje="")
        series, _c, _ = mundo([(_rar(tmp_path / "Secreto Thorgal 01.cbr"), None)])
        with structlog.testing.capture_logs() as logs:
            _pedir(series)
        eventos = [e for e in logs if e["event"] == "cover.candidato_sin_portada"]
        assert eventos and eventos[0]["motivo"] == "ilegible" and eventos[0]["intento"] == 1
        volcado = json.dumps(logs, default=str)
        assert "Secreto" not in volcado and str(tmp_path) not in volcado and "Thorgal" not in volcado

    def test_cinco_rar_ilegibles_y_un_cbz_convergen_sin_gastar_intento_en_los_marcados(
            self, tmp_path, mundo, falso):
        """AC-19 (#419): la 1.ª abre 3 y marca 3; la 2.ª los salta, abre 2 y llega al CBZ."""
        falso.modo(lsar="rc1", mensaje="")
        archivos = [(_rar(tmp_path / f"{i}.cbr", 100 + i), None) for i in range(5)]
        archivos.append((_cbz(tmp_path / "9.cbz"), None))
        series, covers, _ = mundo(archivos)
        assert _pedir(series).status_code == 404
        assert len(_lsars(falso)) == 3 and len(_marcas(covers)) == 3
        r = _pedir(series)
        assert r.status_code == 200
        assert len(_lsars(falso)) == 5 and len(_marcas(covers)) == 5   # solo se abrieron 2 más
        assert (covers / "v3" / f"{series.id}.jpg").exists()

    def test_un_zip_que_falla_se_reintenta_siempre_sin_marca(self, tmp_path, mundo, falso, monkeypatch):
        """AC-25 / FR-22: la marca es solo para RAR."""
        series, covers, _ = mundo([(_cbz_roto(tmp_path / "01.cbz"), None)])
        aperturas = []
        real = wseries.extract_cover_thumbnail
        monkeypatch.setattr(wseries, "extract_cover_thumbnail",
                            lambda *a, **k: (aperturas.append(1), real(*a, **k))[1])
        assert _pedir(series).status_code == 404
        assert _pedir(series).status_code == 404
        assert len(aperturas) == 2 and _marcas(covers) == []

    def test_un_rar_marcado_no_gasta_intento_de_los_tres(self, tmp_path):
        """Mutación: contar el intento de un marcado (aquí 3 marcados + un CBZ legible)."""
        covers = tmp_path / "covers"
        archivos = []
        for i in range(3):
            f = _rar(tmp_path / f"{i}.cbr", 50 + i)
            fid = uuid4()
            portada_rar.escribir_marca(covers / "v3", fid, f, MotivoRar.CIFRADO)
            archivos.append((fid, str(f), None))
        archivos.append((uuid4(), str(_cbz(tmp_path / "9.cbz")), None))
        assert wseries._primera_portada(archivos, covers) is not None


# ── Dictamen de SecOps sobre #455 ─────────────────────────────────────────────────────────────────
class TestDictamenSecOps:
    def test_b3_el_fallo_por_tiempo_caduca_y_los_demas_no(self, tmp_path, monkeypatch):
        """B-3: un tiempo agotado por carga de la máquina no condena al archivo para siempre."""
        covers = tmp_path / "v3"
        rar = _rar(tmp_path / "a.cbr")
        tiempo, cifrado = uuid4(), uuid4()
        portada_rar.escribir_marca(covers, tiempo, rar, MotivoRar.TIEMPO)
        portada_rar.escribir_marca(covers, cifrado, rar, MotivoRar.CIFRADO)
        assert portada_rar.marca_vigente(covers, tiempo, rar) and portada_rar.marca_vigente(covers, cifrado, rar)
        ahora = time.time()
        monkeypatch.setattr(portada_rar.time, "time", lambda: ahora + portada_rar.CADUCIDAD_TIEMPO_S + 1)
        assert portada_rar.marca_vigente(covers, tiempo, rar) is False      # caducó: se reintenta
        assert portada_rar.marca_vigente(covers, cifrado, rar) is True      # del contenido: sigue

    def test_b3_una_marca_de_tiempo_sin_fecha_no_vale(self, tmp_path):
        covers = tmp_path / "v3"
        rar = _rar(tmp_path / "a.cbr")
        fid = uuid4()
        st = rar.stat()
        destino = portada_rar.ruta_de_marca(covers, fid)
        destino.parent.mkdir(parents=True)
        destino.write_text(json.dumps({"v": portada_rar.CONTRATO_PORTADA_RAR, "motivo": "tiempo",
                                       "tamano": st.st_size, "mtime_ns": st.st_mtime_ns}))
        assert portada_rar.marca_vigente(covers, fid, rar) is False

    def test_g1_solo_la_marca_de_tiempo_lleva_fecha(self, tmp_path):
        covers = tmp_path / "v3"
        rar = _rar(tmp_path / "a.cbr")
        t, c = uuid4(), uuid4()
        portada_rar.escribir_marca(covers, t, rar, MotivoRar.TIEMPO)
        portada_rar.escribir_marca(covers, c, rar, MotivoRar.CIFRADO)
        assert "t" in json.loads(portada_rar.ruta_de_marca(covers, t).read_text())
        assert "t" not in json.loads(portada_rar.ruta_de_marca(covers, c).read_text())

    def test_la_caducidad_y_los_topes_son_los_de_la_spec(self, monkeypatch, tmp_path):
        """QA (mutante N21): las pruebas pasan los tiempos por parámetro; aquí se afirman los valores reales."""
        assert portada_rar.CADUCIDAD_TIEMPO_S == 24 * 3600
        assert lector_rar.RAR_ESPERA_TURNO_S == 2.5
        assert lector_rar.RAR_MAX_RSS == 128 * 1024 * 1024
        covers = tmp_path / "v3"
        rar = _rar(tmp_path / "a.cbr")
        fid = uuid4()
        portada_rar.escribir_marca(covers, fid, rar, MotivoRar.TIEMPO)
        ahora = time.time()
        monkeypatch.setattr(portada_rar.time, "time", lambda: ahora + portada_rar.CADUCIDAD_TIEMPO_S - 5)
        assert portada_rar.marca_vigente(covers, fid, rar) is True              # justo antes de las 24 h

    def test_n2a_tras_ocupado_no_se_abren_mas_rar_pero_el_cbz_siguiente_si_se_evalua(self, tmp_path, monkeypatch):
        abiertos = []

        def _ocupado(path, covers, *, ancho):
            abiertos.append(path.name)
            raise ErrorRar(MotivoRar.OCUPADO)

        monkeypatch.setattr(wseries, "portada_de_rar", _ocupado)
        monkeypatch.setattr(wseries, "lector_rar_disponible", lambda: True)
        archivos = [(uuid4(), str(_rar(tmp_path / "1.cbr", 11)), None),
                    (uuid4(), str(_rar(tmp_path / "2.cbr", 22)), None),
                    (uuid4(), str(_cbz(tmp_path / "3.cbz")), None)]
        estado: dict = {}
        resultado = wseries._primera_portada(archivos, tmp_path / "c", estado=estado)
        assert abiertos == ["1.cbr"], "tras `ocupado` no se abre ningún otro RAR (QA N01)"
        assert resultado is not None, "el CBZ posterior sí se evalúa (SecOps N-2 a)"
        assert estado["ocupado"] is True
        assert "file_id" in estado      # BL-INF6: el archivo que dio la portada, para la elección

    def test_n2b_listar_y_leer_comparten_un_turno(self, tmp_path, falso, monkeypatch):
        """Un solo turno: el semáforo se toma una vez y sigue tomado entre el listado y la lectura."""
        _listado_de_una_pagina(falso)
        tomas = []
        real = lector_rar._SEMAFORO

        class _Contador:
            def acquire(self, *a, **k):
                tomas.append(1)
                return real.acquire(*a, **k)

            def release(self):
                real.release()

        monkeypatch.setattr(lector_rar, "_SEMAFORO", _Contador())
        durante_la_lectura = []
        real_leer = lector_rar.leer_entrada
        monkeypatch.setattr(lector_rar, "leer_entrada", lambda *a, **k: (
            durante_la_lectura.append(real.acquire(blocking=False)), real_leer(*a, **k))[1])
        portada_rar.portada_de_rar(_rar(tmp_path / "01.cbr"), tmp_path / "covers", ancho=600)
        assert tomas == [1], "listar y leer deben usar UN turno"
        assert durante_la_lectura == [False], "entre el listado y la lectura el turno sigue tomado"

    def test_b4_se_barren_los_temporales_huerfanos_y_nada_mas(self, tmp_path):
        covers = tmp_path / "covers"
        for n in ("rar-aaa", "rar-bbb"):
            (covers / ".rar-tmp" / n / "salida").mkdir(parents=True)
            (covers / ".rar-tmp" / n / "salida" / "p.jpg").write_bytes(b"x")
        v3 = covers / "v3"
        v3.mkdir()
        (v3 / "no-tocar.jpg").write_bytes(b"x")
        assert portada_rar.barrer_temporales(covers) == 2
        assert list((covers / ".rar-tmp").iterdir()) == [] and (v3 / "no-tocar.jpg").exists()
        assert portada_rar.barrer_temporales(tmp_path / "no-existe") == 0

    def test_m2_lector_ocupado_no_gasta_intento_no_marca_y_no_cachea_la_ausencia(
            self, tmp_path, mundo, falso, monkeypatch):
        """M-2: sin turno no se espera sin fin ni se condena al archivo; el 404 no se cachea."""
        _listado_de_una_pagina(falso)
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        monkeypatch.setattr(lector_rar, "RAR_ESPERA_TURNO_S", 0.1)
        assert lector_rar._SEMAFORO.acquire(timeout=1)          # otro lector tiene el turno
        inicio = time.monotonic()
        try:
            r = _pedir(series)
        finally:
            lector_rar._SEMAFORO.release()
        assert time.monotonic() - inicio < 3, "la petición no puede esperar sin fin el turno"
        assert r.status_code == 404 and r.headers["cache-control"] == "no-store"
        assert _marcas(covers) == [] and falso.llamadas() == []
        assert _pedir(series).status_code == 200                # libre otra vez: sale la portada

    def test_m2_el_ocupado_no_agota_los_intentos_de_los_zip_siguientes(self, tmp_path, monkeypatch):
        def _ocupado(*a, **k):
            raise ErrorRar(MotivoRar.OCUPADO)

        monkeypatch.setattr(wseries, "portada_de_rar", _ocupado)
        monkeypatch.setattr(wseries, "lector_rar_disponible", lambda: True)
        estado: dict = {}
        archivos = [(uuid4(), str(_rar(tmp_path / "a.cbr")), None)]
        assert wseries._primera_portada(archivos, tmp_path / "c", estado=estado) is None
        assert estado == {"ocupado": True}


# ── Interruptor LECTOR_RAR_ENABLED (decisión del PO, 2026-11-07) ─────────────────────────────────
class TestInterruptorLectorRar:
    @staticmethod
    def _fijar(monkeypatch, valor: bool):
        base = get_settings().model_copy(update={"covers_cache_path": Path("/nada")})
        real = wseries.get_settings

        def _con_interruptor():
            return real().model_copy(update={"lector_rar_enabled": valor})

        monkeypatch.setattr(wseries, "get_settings", _con_interruptor)
        return base

    def test_por_defecto_esta_encendido_y_se_lee_del_entorno(self, monkeypatch):
        from zascarr.config import Settings
        assert Settings().lector_rar_enabled is True
        for texto, esperado in (("false", False), ("true", True), ("0", False), ("1", True)):
            monkeypatch.setenv("LECTOR_RAR_ENABLED", texto)
            assert Settings().lector_rar_enabled is esperado

    def test_encendido_el_rar_se_envia_a_unar(self, tmp_path, mundo, falso, monkeypatch):
        _listado_de_una_pagina(falso)
        series, _c, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        self._fijar(monkeypatch, True)
        assert _pedir(series).status_code == 200
        assert _lsars(falso) and _unars(falso)

    def test_apagado_ningun_rar_llega_a_unar_ni_gasta_intento_ni_deja_marca(self, tmp_path, mundo, falso, monkeypatch):
        """Con cuatro RAR delante (más que `MAX_INTENTOS_PORTADA`) se llega al CBZ: ni un subproceso, ni intento, ni marca."""
        lanzados = []
        real_popen = lector_rar.subprocess.Popen
        monkeypatch.setattr(lector_rar.subprocess, "Popen", lambda *a, **k: (lanzados.append(a), real_popen(*a, **k))[1])
        falso.modo(lsar="rc1", mensaje="")                      # si se lanzara, dejaría marca
        archivos = [(_rar(tmp_path / f"{i}.cbr", 100 + i), None) for i in range(wseries.MAX_INTENTOS_PORTADA + 1)]
        archivos.append((_cbz(tmp_path / "9.cbz"), None))
        series, covers, _ = mundo(archivos)
        self._fijar(monkeypatch, False)
        r = _pedir(series)
        assert r.status_code == 200 and _ancho(r.content) == 500       # la portada es la del CBZ
        assert falso.llamadas() == [] and _marcas(covers) == [] and lanzados == []   # ni un `Popen` del lector

    def test_apagado_sin_otra_cosa_la_cascada_sigue_sin_500_y_sin_ruta_en_el_registro(
            self, tmp_path, mundo, falso, monkeypatch):
        series, covers, _ = mundo([(_rar(tmp_path / "Secreto 01.cbr"), None)],
                                  cover_url="https://comicvine.gamespot.com/a/uploads/c.jpg")
        self._fijar(monkeypatch, False)
        antigua = covers / f"{series.id}.jpg"
        antigua.parent.mkdir(parents=True)
        antigua.write_bytes(_jpeg(120))
        with structlog.testing.capture_logs() as logs:
            r = _pedir(series)
        assert r.status_code == 200 and _ancho(r.content) == 120       # cae a la antigua
        assert falso.llamadas() == [] and _marcas(covers) == []
        assert "Secreto" not in json.dumps(logs, default=str) and str(tmp_path) not in json.dumps(logs, default=str)

    def test_apagado_conserva_lo_generado_y_las_marcas_y_al_volver_a_encender_las_respeta(
            self, tmp_path, mundo, falso, monkeypatch):
        """AC-47: lo ya generado se sigue sirviendo, las marcas no se tocan, y al volver a `true` un archivo
        con marca vigente no se reabre y uno sin marca vuelve a intentarse."""
        falso.modo(lsar="rc1", mensaje="")
        marcado = _rar(tmp_path / "a.cbr", 101)
        limpio = _rar(tmp_path / "b.cbr", 202)
        series, covers, sesion = mundo([(marcado, None)])
        self._fijar(monkeypatch, True)
        assert _pedir(series).status_code == 404                # `a.cbr` falla y queda marcado
        (marca,) = _marcas(covers)
        antes = (marca.read_bytes(), marca.stat().st_mtime_ns)
        v3 = covers / "v3" / f"{series.id}.jpg"
        v3.parent.mkdir(parents=True, exist_ok=True)
        v3.write_bytes(_jpeg(500, color=(0, 255, 0)))           # una portada generada antes
        self._fijar(monkeypatch, False)
        assert _ancho(_pedir(series).content) == 500            # se sigue sirviendo con el lector apagado
        assert [(m.read_bytes(), m.stat().st_mtime_ns) for m in _marcas(covers)] == [antes]
        v3.unlink()
        sesion.archivos.append((uuid4(), str(limpio), None))
        self._fijar(monkeypatch, True)
        lsars_antes = len(_lsars(falso))
        _pedir(series)
        assert len(_lsars(falso)) == lsars_antes + 1            # solo `b.cbr` se intenta: `a.cbr` sigue marcado

    def test_h1_con_el_lector_ocupado_la_portada_del_cbz_es_efimera_y_luego_gana_el_rar(
            self, tmp_path, mundo, falso, monkeypatch):
        """H-1 (SecOps y QA): serie [RAR legible, CBZ]. Sin turno el RAR se salta y sale el CBZ, pero NO se
        guarda en `v3` ni se cachea; con el lector libre la siguiente petición da la del RAR y esa sí se guarda."""
        _listado_de_una_pagina(falso)                           # el RAR da una portada roja de 1800 px → 600
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None), (_cbz(tmp_path / "02.cbz"), None)])
        monkeypatch.setattr(lector_rar, "RAR_ESPERA_TURNO_S", 0.1)
        v3 = covers / "v3" / f"{series.id}.jpg"
        assert lector_rar._SEMAFORO.acquire(timeout=1)          # otro lector tiene el turno
        try:
            r = _pedir(series)
        finally:
            lector_rar._SEMAFORO.release()
        assert r.status_code == 200 and _ancho(r.content) == 500          # la del CBZ
        assert r.headers["cache-control"] == "no-store" and "etag" not in r.headers
        assert not v3.exists(), "la portada efímera no puede quedar en v3"
        assert _marcas(covers) == []
        r2 = _pedir(series)                                     # lector libre
        assert r2.status_code == 200 and _ancho(r2.content) == 600        # ahora la del RAR
        assert v3.exists() and _ancho(v3.read_bytes()) == 600
        assert _ancho(_pedir(series).content) == 600            # y ya sale de `v3`

    def test_h1_una_serie_solo_cbz_se_cachea_como_antes(self, tmp_path, mundo, falso):
        series, covers, _ = mundo([(_cbz(tmp_path / "01.cbz"), None)])
        r = _pedir(series)
        assert r.status_code == 200 and r.headers["cache-control"] == "private, max-age=86400"
        assert (covers / "v3" / f"{series.id}.jpg").exists() and falso.llamadas() == []

    def test_h1_un_rar_marcado_no_hace_efimera_la_del_cbz(self, tmp_path, mundo, falso):
        """Un RAR saltado por tener MARCA vigente (no por falta de turno) no es «ocupado»: se cachea como siempre."""
        falso.modo(lsar="rc1", mensaje="")
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None), (_cbz(tmp_path / "02.cbz"), None)])
        r1 = _pedir(series)                 # el RAR falla (ilegible) y queda marcado; sale el CBZ y se guarda
        assert r1.status_code == 200 and r1.headers["cache-control"] == "private, max-age=86400"
        assert (covers / "v3" / f"{series.id}.jpg").exists()

    def test_apagado_un_zip_con_extension_cbr_sigue_igual(self, tmp_path, mundo, falso, monkeypatch):
        series, _c, _ = mundo([(_cbz(tmp_path / "01.cbr"), None)])
        self._fijar(monkeypatch, False)
        assert _pedir(series).status_code == 200 and falso.llamadas() == []

    def test_apagado_la_herramienta_ni_se_busca(self, tmp_path, falso, monkeypatch):
        """`herramienta` arranca en `False`: ni se llama a `disponible()`."""
        self._fijar(monkeypatch, False)
        llamadas = []
        monkeypatch.setattr(wseries, "lector_rar_disponible", lambda: llamadas.append(1) or True)
        archivos = [(uuid4(), str(_rar(tmp_path / "a.cbr")), None)]
        assert wseries._primera_portada(archivos, tmp_path / "c") is None
        assert llamadas == [] and falso.llamadas() == []

    def test_apagado_a_proposito_no_es_un_aviso_de_salud(self, monkeypatch):
        from zascarr.api.health import AVISO_LECTOR_RAR

        class _Db:
            async def execute(self, _s):
                return None

        async def _get_db():
            yield _Db()

        app.dependency_overrides[get_db] = _get_db
        try:
            monkeypatch.setattr(lector_rar, "disponible", lambda: False)
            ajustes = get_settings()
            monkeypatch.setattr(ajustes, "lector_rar_enabled", True)
            assert TestClient(app).get("/api/health").json()["warnings"]["lector_rar"] == AVISO_LECTOR_RAR
            monkeypatch.setattr(ajustes, "lector_rar_enabled", False)
            assert "lector_rar" not in TestClient(app).get("/api/health").json()["warnings"]
        finally:
            app.dependency_overrides.pop(get_db, None)


# ── Arranque (AC-40, AC-48) ────────────────────────────────────────────────────────────────────────
class TestArranque:
    @staticmethod
    def _arrancar(monkeypatch, covers: Path, *, habilitado: bool):
        from zascarr import main as principal
        ajustes = get_settings().model_copy(update={"covers_cache_path": covers, "lector_rar_enabled": habilitado})
        monkeypatch.setattr(principal, "get_settings", lambda: ajustes)
        with structlog.testing.capture_logs() as logs, TestClient(principal.app):
            pass
        return logs

    def test_ac48_apagado_el_arranque_deja_una_sola_linea_sin_rutas(self, tmp_path, monkeypatch):
        covers = tmp_path / "Secreto"
        logs = self._arrancar(monkeypatch, covers, habilitado=False)
        lineas = [e for e in logs if str(e["event"]).startswith("lector_rar.")]
        assert [e["event"] for e in lineas] == ["lector_rar.apagado"]
        assert "Secreto" not in json.dumps(lineas, default=str)

    def test_ac48_encendido_y_sin_herramienta_avisa_una_vez(self, tmp_path, monkeypatch):
        monkeypatch.setattr(lector_rar, "disponible", lambda: False)
        logs = self._arrancar(monkeypatch, tmp_path / "covers", habilitado=True)
        assert [e["event"] for e in logs if str(e["event"]).startswith("lector_rar.")] == ["lector_rar.no_disponible"]

    def test_ac40_el_arranque_barre_los_temporales_huerfanos(self, tmp_path, monkeypatch):
        covers = tmp_path / "covers"
        for n in ("rar-aaa", "rar-bbb"):
            (covers / ".rar-tmp" / n / "salida").mkdir(parents=True)
            (covers / ".rar-tmp" / n / "salida" / "p.jpg").write_bytes(b"x")
        (covers / "v3").mkdir()
        (covers / "v3" / "no-tocar.jpg").write_bytes(b"x")
        logs = self._arrancar(monkeypatch, covers, habilitado=True)
        assert list((covers / ".rar-tmp").iterdir()) == [] and (covers / "v3" / "no-tocar.jpg").exists()
        barrido = [e for e in logs if e["event"] == "lector_rar.temporales_barridos"]
        assert barrido and barrido[0]["cantidad"] == 2


# ── Presupuesto (AC-21) y una generación por serie (AC-34) ───────────────────────────────────────
class TestPresupuestoYConcurrencia:
    def test_sin_presupuesto_no_se_abre_ninguno(self, tmp_path, falso):
        archivos = [(uuid4(), str(_rar(tmp_path / "a.cbr")), None)]
        assert wseries._primera_portada(archivos, tmp_path / "c", presupuesto_s=0.0) is None
        assert falso.llamadas() == []

    def test_agotado_en_mitad_no_abre_mas(self, tmp_path, falso, monkeypatch):
        abiertos = []

        def _lento(path, covers, *, ancho):
            abiertos.append(path.name)
            time.sleep(0.08)
            raise ErrorRar(MotivoRar.ILEGIBLE)

        monkeypatch.setattr(wseries, "portada_de_rar", _lento)
        archivos = [(uuid4(), str(_rar(tmp_path / f"{i}.cbr", 10 + i)), None) for i in range(3)]
        assert wseries._primera_portada(archivos, tmp_path / "c", presupuesto_s=0.05) is None
        assert abiertos == ["0.cbr"]

    @pytest.mark.asyncio
    async def test_dos_peticiones_de_la_misma_serie_lanzan_el_lector_una_sola_vez(
            self, tmp_path, mundo, falso):
        _listado_de_una_pagina(falso)
        falso.modo(unar="lento")
        series, _c, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://localhost", headers={"Origin": "http://localhost"}) as cliente:
            a, b = await asyncio.gather(*(cliente.get(f"/ui/series/{series.id}/portada") for _ in range(2)))
        assert a.status_code == b.status_code == 200 and a.content == b.content
        assert len(_unars(falso)) == 1 and len(_lsars(falso)) == 1
        assert wseries._GENERANDO == {}

    @pytest.mark.asyncio
    async def test_dos_series_distintas_generan_cada_una_la_suya(self, tmp_path, falso):
        _listado_de_una_pagina(falso)
        falso.modo(unar="lento")
        covers = tmp_path / "covers"
        s1, s2 = uuid4(), uuid4()
        f1 = [(uuid4(), str(_rar(tmp_path / "a.cbr")), None)]
        f2 = [(uuid4(), str(_rar(tmp_path / "b.cbr", 77)), None)]
        a, b = await asyncio.gather(
            wseries._portada_de_archivos(s1, f1, covers, covers / "v3" / f"{s1}.jpg"),
            wseries._portada_de_archivos(s2, f2, covers, covers / "v3" / f"{s2}.jpg"))
        assert a is not None and b is not None
        assert len(_unars(falso)) == 2
        assert wseries._GENERANDO == {}


# ── «Por revisar» y formato intactos (AC-27, AC-28) ──────────────────────────────────────────────
class TestSinEfectosColaterales:
    def test_por_revisar_no_gana_miniatura_de_rar_ni_lanza_el_lector(self, tmp_path, falso):
        rar = _rar(tmp_path / "01.cbr")
        assert puede_tener_portada(rar, {"firma": "rar"}) is False
        assert puede_tener_portada(rar) is False
        assert extract_cover_thumbnail(rar, {"firma": "rar"}) is None
        assert extract_cover_thumbnail(rar) is None
        assert falso.llamadas() == []

    def test_pendientes_no_importa_el_lector(self):
        fuente = (Path(wseries.__file__).parent / "pendientes.py").read_text()
        assert "lector_rar" not in fuente and "portada_rar" not in fuente

    def test_el_tratamiento_de_un_rar_sigue_siendo_solo_hash(self):
        assert tratamiento(".cbr", Firma.RAR) is Tratamiento.SOLO_HASH

    def test_generar_la_portada_no_escribe_nada_en_el_original_ni_junto_a_el(self, tmp_path, mundo, falso):
        _listado_de_una_pagina(falso)
        rar = _rar(tmp_path / "serie" / "01.cbr")
        antes = (rar.read_bytes(), rar.stat().st_mtime_ns)
        series, covers, _ = mundo([(rar, None)])
        _pedir(series)
        assert (rar.read_bytes(), rar.stat().st_mtime_ns) == antes
        assert [p.name for p in rar.parent.iterdir()] == ["01.cbr"]
        assert list((covers / ".rar-tmp").iterdir()) == []              # el temporal se borró


# ── Sustituir lo ya guardado (AC-29..31) ─────────────────────────────────────────────────────────
class TestV3YExterna:
    def test_una_v2_ya_escrita_no_se_sirve_ni_se_borra(self, tmp_path, mundo, falso):
        """AC-29 / mutación «servir v2»."""
        _listado_de_una_pagina(falso)
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        v2 = covers / "v2" / f"{series.id}.jpg"
        v2.parent.mkdir(parents=True)
        v2.write_bytes(_jpeg(100, color=(0, 255, 0)))
        antes = (v2.read_bytes(), v2.stat().st_mtime_ns)
        r = _pedir(series)
        assert r.status_code == 200 and _ancho(r.content) == 600
        assert (covers / "v3" / f"{series.id}.jpg").exists()
        assert (v2.read_bytes(), v2.stat().st_mtime_ns) == antes

    def test_la_externa_pequena_va_aparte_y_cede_ante_un_archivo_que_se_hace_legible(
            self, tmp_path, mundo, falso, monkeypatch):
        """AC-30: la externa no bloquea; al aparecer un archivo legible, la serie cambia sola."""
        series, covers, sesion = mundo([(_rar(tmp_path / "01.cbr"), None)],
                                       cover_url="https://comicvine.gamespot.com/a/uploads/c.jpg")
        falso.modo(lsar="rc1", mensaje="")

        async def _externa(url, dest, **kwargs):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_jpeg(100, color=(0, 255, 0)))
            return True

        monkeypatch.setattr("zascarr.web.series.fetch_and_cache_cover", _externa)
        r = _pedir(series)
        externa = covers / "externa" / f"{series.id}.jpg"
        assert r.status_code == 200 and _ancho(r.content) == 100
        assert externa.exists() and not (covers / "v3" / f"{series.id}.jpg").exists()
        # el primer archivo pasa a ser legible (otro archivo nuevo entra en la serie)
        sesion.archivos.append((uuid4(), str(_cbz(tmp_path / "02.cbz")), None))
        r = _pedir(series)
        assert _ancho(r.content) == 500 and (covers / "v3" / f"{series.id}.jpg").exists()

    def test_la_antigua_se_sirve_solo_sin_v3_ni_candidato_y_no_se_copia(self, tmp_path, mundo, falso):
        """AC-31."""
        falso.modo(lsar="rc1", mensaje="")
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        antigua = covers / f"{series.id}.jpg"
        antigua.parent.mkdir(parents=True)
        antigua.write_bytes(_jpeg(120))
        r = _pedir(series)
        assert r.status_code == 200 and _ancho(r.content) == 120
        assert not (covers / "v3" / f"{series.id}.jpg").exists()

    def test_una_externa_suficiente_se_conserva_sin_abrir_archivos(self, tmp_path, mundo, falso):
        """Cruce con #435: la externa >= 300 px se sirve antes que los candidatos."""
        series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
        externa = covers / "externa" / f"{series.id}.jpg"
        externa.parent.mkdir(parents=True)
        externa.write_bytes(_jpeg(500))
        assert _ancho(_pedir(series).content) == 500
        assert falso.llamadas() == []


def test_ids_de_archivo_son_uuid_en_la_consulta():
    """La consulta de candidatos trae `File.id` primero: la marca de fallo lo necesita."""
    sentencia = str(wseries._stmt_archivos_de_portada(UUID(int=1)))
    assert sentencia.index("files.id") < sentencia.index("files.file_path")


def test_506_respaldo_viejo_con_lector_ocupado_lleva_no_store(
        tmp_path, mundo, falso, monkeypatch):
    """#506: si el lector está ocupado, el respaldo 100×100 no se cachea un día."""
    _listado_de_una_pagina(falso)
    series, covers, _ = mundo([(_rar(tmp_path / "01.cbr"), None)])
    antigua = covers / f"{series.id}.jpg"
    antigua.parent.mkdir(parents=True)
    antigua.write_bytes(_jpeg(120))
    monkeypatch.setattr(lector_rar, "RAR_ESPERA_TURNO_S", 0.1)
    assert lector_rar._SEMAFORO.acquire(timeout=1)
    try:
        r = _pedir(series)
    finally:
        lector_rar._SEMAFORO.release()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    # Libre otra vez: la portada buena se genera en v3 y se cachea con la cabecera normal.
    r2 = _pedir(series)
    assert r2.status_code == 200 and r2.headers["cache-control"] == "private, max-age=86400"
    assert (covers / "v3" / f"{series.id}.jpg").exists()
