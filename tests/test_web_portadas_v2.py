"""
tests/test_web_portadas_v2.py

BL-PORT1 (#300), PR-1: tamaño por uso y caché `v2` de la portada de serie.

Cubre la cascada de `web/series.py::portada` (FR-01…FR-10, FR-15…FR-18) y sus
criterios AC-01, AC-05, AC-07, AC-08, AC-09, AC-10, AC-11, AC-13, AC-14,
AC-17, AC-18 y AC-19. Todo con CBZ sintéticos y sesión falsa: ni biblioteca
real ni red.

Orden de la cascada (spec §5.1):
  1. `covers/v2/<id>.jpg`                → servir
  2. primer `File` no ausente extractable → extraer a 600, escribir v2, servir
  3. `covers/<id>.jpg` legado            → servir sin red y sin copiar
  4. `cover_url` externa                 → descargar una vez a 600, escribir v2
  5. nada                                → 404
"""
from __future__ import annotations

import asyncio
import io
import threading
import time
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.utils.cover import CACHE_VERSION, SERIES_COVER_MAX_WIDTH, write_cover_cache

#: Caso sintético del AC-01: 1600×2400 se sirve a 600×900.
CBZ_GRANDE = (1600, 2400)


def _jpeg(ancho: int = 240, alto: int = 360) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=(40, 80, 120)).save(buf, format="JPEG")
    return buf.getvalue()


def _cbz(destino: Path, tamano: tuple[int, int] = CBZ_GRANDE) -> Path:
    """CBZ mínimo con una página, del tamaño pedido (extracción real de Pillow)."""
    buf = io.BytesIO()
    Image.new("RGB", tamano, color=(120, 40, 200)).save(buf, format="JPEG")
    with zipfile.ZipFile(destino, "w") as zf:
        zf.writestr("001.jpg", buf.getvalue())
    return destino


def _serie() -> Series:
    return Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                  start_year=1977, cover_url=None)


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def first(self):
        return self._filas[0] if self._filas else None


class _SesionDePortada:
    """`get` devuelve la serie; `execute`, la misma fila de archivo en cada llamada.
    Guarda los statements para comprobar el filtro `is_missing` (regresión B7/AC-17)."""

    def __init__(self, series: Series, filas: list):
        self._series = series
        self._filas = list(filas)
        self.statements: list[str] = []

    async def get(self, _model, _id):
        return self._series

    async def execute(self, statement):
        self.statements.append(str(statement))
        return _Resultado(self._filas)


class Mundo:
    """Un mundo de portada: serie, sesión falsa y caché redirigida a `tmp_path`."""

    def __init__(self, tmp_path: Path, series: Series, filas: list):
        self.series = series
        self.covers = tmp_path / "covers"
        self.v2 = self.covers / CACHE_VERSION / f"{series.id}.jpg"
        self.legado = self.covers / f"{series.id}.jpg"
        self.sesion = _SesionDePortada(series, filas)

    def url(self) -> str:
        return f"/ui/series/{self.series.id}/portada"

    def get(self, client: TestClient, **kwargs):
        return client.get(self.url(), **kwargs)


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    """Crea el mundo de la prueba; la caché NUNCA se escribe en la ruta real."""
    creados = []

    def _crear(filas: list, series: Series | None = None) -> Mundo:
        m = Mundo(tmp_path, series or _serie(), filas)
        settings = get_settings().model_copy(update={"covers_cache_path": m.covers})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)

        async def _get_db():
            yield m.sesion

        app.dependency_overrides[get_db] = _get_db
        creados.append(m)
        return m

    yield _crear
    app.dependency_overrides.pop(get_db, None)


class TestGeneracionA600:
    """AC-01 y AC-05: 600 por defecto y sin ampliar originales pequeños."""

    def test_escribe_v2_a_600_y_respeta_el_contrato_de_cabeceras(self, tmp_path, mundo):
        serie = _serie()
        m = mundo([(str(_cbz(tmp_path / "comic.cbz")), None)], series=serie)

        r = TestClient(app).get(m.url())

        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.headers["cache-control"] == "private, max-age=86400"
        assert m.v2.exists(), "la portada de serie se cachea en covers/v2/<id>.jpg"
        with Image.open(m.v2) as img:
            assert img.width == 600
            assert abs(img.height - 900) <= 1
        assert r.headers["etag"] == f'"{m.v2.stat().st_mtime}"'
        assert r.content == m.v2.read_bytes()

    def test_original_pequeno_no_se_amplia(self, tmp_path, mundo):
        m = mundo([(str(_cbz(tmp_path / "pequeno.cbz", (400, 600))), None)])

        r = TestClient(app).get(m.url())

        assert r.status_code == 200
        with Image.open(m.v2) as img:
            assert img.width == 400
            assert img.height == 600


class TestRegeneracionPerezosa:
    """AC-07 y AC-08: el legado 240 se regenera a 600 sin borrar ni perder el 304."""

    def test_legado_240_mas_cbz_regenera_a_600_y_conserva_el_legado(self, tmp_path, mundo):
        m = mundo([(str(_cbz(tmp_path / "comic.cbz")), None)])
        m.legado.parent.mkdir(parents=True, exist_ok=True)
        legado = _jpeg(240, 360)
        m.legado.write_bytes(legado)

        cliente = TestClient(app)
        r = cliente.get(m.url())

        assert r.status_code == 200
        with Image.open(m.v2) as img:
            assert img.width == 600
        assert m.legado.read_bytes() == legado, "el legado no se borra ni se pisa"
        assert r.headers["etag"] == f'"{m.v2.stat().st_mtime}"'

        r2 = cliente.get(m.url(), headers={"If-None-Match": r.headers["etag"]})
        assert r2.status_code == 304
        assert r2.content == b""

    def test_cabeceras_del_legado_sin_archivo_utilizable(self, mundo):
        m = mundo([])                                  # ningún File utilizable
        m.legado.parent.mkdir(parents=True, exist_ok=True)
        m.legado.write_bytes(_jpeg(240, 360))

        cliente = TestClient(app)
        r = cliente.get(m.url())

        assert r.status_code == 200
        assert r.headers["etag"] == f'"{m.legado.stat().st_mtime}"'
        assert r.headers["cache-control"] == "private, max-age=86400"
        r2 = cliente.get(m.url(), headers={"If-None-Match": r.headers["etag"]})
        assert r2.status_code == 304 and r2.content == b""


class TestSinTrabajoSiYaEsta:
    """AC-09 y AC-14: con `v2` escrita no se extrae, no se descarga y no se toca el legado."""

    def test_con_v2_no_llama_al_extractor_ni_a_la_red(self, mundo, monkeypatch):
        m = mundo([])
        m.series.cover_url = "https://comicvine.gamespot.com/a/uploads/cover.jpg"
        m.v2.parent.mkdir(parents=True)
        datos = _jpeg(600, 900)
        m.v2.write_bytes(datos)

        llamadas = {"extraer": 0, "red": 0}

        def _no_extraer(*_a, **_k):
            llamadas["extraer"] += 1
            return None

        async def _no_red(*_a, **_k):
            llamadas["red"] += 1
            return False

        monkeypatch.setattr("zascarr.web.series.extract_cover_thumbnail", _no_extraer)
        monkeypatch.setattr("zascarr.web.series.fetch_and_cache_cover", _no_red)

        r = TestClient(app).get(m.url())

        assert r.status_code == 200
        assert r.content == datos
        assert llamadas == {"extraer": 0, "red": 0}

    def test_legado_sin_archivo_utilizable_se_sirve_sin_red_ni_copia(self, mundo, monkeypatch):
        """AC-13: sin File, con `cover_url` y con caché legada, la red no se toca."""
        m = mundo([])
        m.series.cover_url = "https://comicvine.gamespot.com/a/uploads/cover.jpg"
        m.legado.parent.mkdir(parents=True)
        datos = _jpeg(240, 360)
        m.legado.write_bytes(datos)
        llamadas = []

        async def _no_red(*a, **k):
            llamadas.append((a, k))
            return True

        monkeypatch.setattr("zascarr.web.series.fetch_and_cache_cover", _no_red)

        r = TestClient(app).get(m.url())

        assert r.status_code == 200
        assert r.content == datos
        assert llamadas == []
        assert not m.v2.exists(), "el legado no se copia a v2"

    def test_sin_cache_y_con_cover_url_descarga_una_sola_vez_a_600(self, mundo, monkeypatch):
        """AC-14: la única red es la de siempre, una vez y al ancho de serie."""
        m = mundo([])
        m.series.cover_url = "https://comicvine.gamespot.com/a/uploads/cover.jpg"
        llamadas = []

        async def _falsa(url, dest, **kwargs):
            llamadas.append((url, kwargs))
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_jpeg(600, 900))
            return True

        monkeypatch.setattr("zascarr.web.series.fetch_and_cache_cover", _falsa)

        r = TestClient(app).get(m.url())

        assert r.status_code == 200
        assert len(llamadas) == 1
        assert llamadas[0][1]["ancho"] == SERIES_COVER_MAX_WIDTH
        assert m.v2.exists()
        with Image.open(m.v2) as img:
            assert img.width == 600


class TestArchivosAusentesYCorruptos:
    """AC-17, AC-18 y AC-19: is_missing, CBR sin extractor y sin fuente."""

    def test_is_missing_se_filtra_en_la_consulta_y_se_usa_cover_url(self, mundo, monkeypatch):
        m = mundo([])                                  # la consulta ya filtró el File ausente
        m.series.cover_url = "https://comicvine.gamespot.com/a/uploads/cover.jpg"

        async def _falsa(url, dest, **_kwargs):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(_jpeg(600, 900))
            return True

        monkeypatch.setattr("zascarr.web.series.fetch_and_cache_cover", _falsa)

        r = TestClient(app).get(m.url())

        assert r.status_code == 200
        assert m.sesion.statements, "no se consultó ningún archivo"
        assert "is_missing" in m.sesion.statements[0]

    def test_cbr_sin_extractor_da_404_sin_red(self, tmp_path, mundo, monkeypatch):
        cbr = tmp_path / "comic.cbr"
        cbr.write_bytes(b"Rar!\x1a\x07\x00" + b"\0" * 32)
        m = mundo([(str(cbr), None)])
        llamadas = []

        async def _no_red(*a, **k):
            llamadas.append((a, k))
            return True

        monkeypatch.setattr("zascarr.web.series.fetch_and_cache_cover", _no_red)

        r = TestClient(app).get(m.url())

        assert r.status_code == 404
        assert llamadas == []
        assert not m.v2.exists()

    def test_sin_archivo_ni_cover_url_da_404_sin_crear_cache(self, mundo):
        m = mundo([])
        m.series.cover_url = None

        r = TestClient(app).get(m.url())

        assert r.status_code == 404
        assert not m.v2.exists()
        assert not m.legado.exists()


class TestRenderNoGeneraPortadas:
    """AC-10: abrir Biblioteca no extrae ni escribe; pedir una portada, sí (una)."""

    @staticmethod
    def _sesion_biblioteca(series: list) -> object:
        class _R:
            def __init__(self, valor):
                self._valor = valor

            def scalar(self):
                return self._valor

            def scalars(self):
                return self

            def all(self):
                return self._valor if isinstance(self._valor, list) else []

        class _Sesion:
            def __init__(self):
                self._cola = [_R([]), _R(len(series)), _R(series)]

            async def execute(self, _statement):
                return self._cola.pop(0)

        return _Sesion()

    def test_abrir_biblioteca_no_extrae_ni_escribe_y_pedir_una_portada_extrae_una(
        self, tmp_path, monkeypatch
    ):
        series = [Series(id=uuid4(), title=f"Serie {i}", tradition=ComicTradition.AMERICAN)
                  for i in range(200)]
        covers = tmp_path / "covers"
        settings = get_settings().model_copy(update={"covers_cache_path": covers})
        monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)

        llamadas = {"extraer": 0, "escribir": 0}

        def _contar_extraer(*_a, **_k):
            llamadas["extraer"] += 1
            return None

        def _contar_escribir(*_a, **_k):
            llamadas["escribir"] += 1

        monkeypatch.setattr("zascarr.web.series.extract_cover_thumbnail", _contar_extraer)
        monkeypatch.setattr("zascarr.web.series.write_cover_cache", _contar_escribir)

        async def _get_db():
            yield self._sesion_biblioteca(series)

        app.dependency_overrides[get_db] = _get_db
        try:
            r = TestClient(app).get("/ui/biblioteca")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        assert llamadas == {"extraer": 0, "escribir": 0}
        assert not covers.exists(), "el render no debe crear ni el directorio de caché"

        # Ahora sí, una única portada: como mucho una extracción de ESA serie.
        cbz = _cbz(tmp_path / "comic.cbz")
        sesion_portada = _SesionDePortada(series[0], [(str(cbz), None)])

        def _extrae(*_a, **_k):
            llamadas["extraer"] += 1
            return _jpeg(600, 900), "image/jpeg"

        monkeypatch.setattr("zascarr.web.series.extract_cover_thumbnail", _extrae)
        monkeypatch.setattr("zascarr.web.series.write_cover_cache", write_cover_cache)

        async def _get_db_portada():
            yield sesion_portada

        app.dependency_overrides[get_db] = _get_db_portada
        try:
            r2 = TestClient(app).get(f"/ui/series/{series[0].id}/portada")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r2.status_code == 200
        assert llamadas["extraer"] == 1
        assert (covers / CACHE_VERSION / f"{series[0].id}.jpg").exists()


class TestNoBloqueaElBucle:
    """AC-11: la extracción corre en un hilo aparte; el bucle sigue latiendo."""

    async def test_la_extraccion_no_congela_el_bucle(self, tmp_path, mundo, monkeypatch):
        m = mundo([(str(_cbz(tmp_path / "comic.cbz")), None)])
        hilos = []

        def _extrae_lento(*_a, **_k):
            hilos.append(threading.current_thread())
            time.sleep(0.3)
            return _jpeg(600, 900), "image/jpeg"

        monkeypatch.setattr("zascarr.web.series.extract_cover_thumbnail", _extrae_lento)

        parar = asyncio.Event()
        peor = 0.0

        async def latido():
            nonlocal peor
            previo = time.perf_counter()
            while not parar.is_set():
                await asyncio.sleep(0.01)
                ahora = time.perf_counter()
                peor = max(peor, ahora - previo)
                previo = ahora

        tarea = asyncio.create_task(latido())
        await asyncio.sleep(0.05)
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transporte, base_url="http://localhost",
            headers={"Origin": "http://localhost"},
        ) as cliente:
            r = await cliente.get(m.url())
        parar.set()
        await tarea

        assert r.status_code == 200
        assert hilos and hilos[0] is not threading.main_thread()
        assert peor < 0.15, f"el bucle se congeló {peor:.3f}s durante la extracción"


class TestUsaLaVersionEnLaRuta:
    """FR-03: la clave de caché lleva la versión; el legado no se escribe."""

    def test_la_cache_nueva_va_a_v2_y_el_legado_solo_se_lee(self, tmp_path, mundo):
        m = mundo([(str(_cbz(tmp_path / "comic.cbz")), None)])

        TestClient(app).get(m.url())

        assert CACHE_VERSION == "v2"
        assert m.v2.exists()
        assert not m.legado.exists()

    def test_el_query_v2_de_la_ui_no_cambia_la_respuesta(self, tmp_path, mundo):
        """`?v=2` es solo el separador de caché del navegador (R-01): el endpoint lo ignora
        y responde igual que sin query."""
        m = mundo([(str(_cbz(tmp_path / "comic.cbz")), None)])
        cliente = TestClient(app)

        sin_query = cliente.get(m.url())
        con_query = cliente.get(m.url() + "?v=2")

        assert sin_query.status_code == con_query.status_code == 200
        assert con_query.headers["etag"] == sin_query.headers["etag"]
        assert con_query.headers["cache-control"] == "private, max-age=86400"
        assert con_query.content == sin_query.content
