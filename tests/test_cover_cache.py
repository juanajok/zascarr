"""
tests/test_cover_cache.py

Suite de la caché unificada de portadas (C1): cached_image_response (304
condicional, cabeceras de caché) y fetch_and_cache_cover (descarga +
resize + guardado, sin lanzar si algo falla). Sin URLs reales — un
ASGITransport/monkeypatch de httpx hace de servidor falso.
"""
from __future__ import annotations

import asyncio
import io
import os
import zipfile
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import structlog
from fastapi import Request
from fastapi.testclient import TestClient
from PIL import Image

import zascarr.utils.cover as zcover
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.utils.cover import (
    cached_image_response,
    fetch_and_cache_cover,
    write_cover_cache,
)
from zascarr.utils.espacio import EspacioInsuficienteError


def make_request(headers: dict | None = None) -> Request:
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


class TestCachedImageResponse:

    def test_sin_if_none_match_devuelve_200_con_cabeceras(self):
        response = cached_image_response(make_request(), b"data", "image/jpeg", '"123"')
        assert response.status_code == 200
        assert response.headers["etag"] == '"123"'
        assert response.headers["cache-control"] == "private, max-age=86400"
        assert response.body == b"data"

    def test_if_none_match_coincide_devuelve_304(self):
        request = make_request({"if-none-match": '"123"'})
        response = cached_image_response(request, b"data", "image/jpeg", '"123"')
        assert response.status_code == 304

    def test_if_none_match_distinto_devuelve_200(self):
        request = make_request({"if-none-match": '"999"'})
        response = cached_image_response(request, b"data", "image/jpeg", '"123"')
        assert response.status_code == 200


def _fake_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="blue").save(buf, format="JPEG")
    return buf.getvalue()


class TestFetchAndCacheCover:
    """H1: la descarga pasa por la política de `utils/url_portada.py` (`tests/test_cover_ssrf.py`
    cubre el rechazo de destinos, direcciones, redirecciones y tamaño). Aquí se conservan los
    tres casos de siempre (descarga correcta, fallo de red e imagen ilegible) con un host de la
    lista y la red simulada: antes se parcheaba `httpx.AsyncClient.get` con `cdn.example`, que la
    política ya no admite."""

    URL = "https://comicvine.gamespot.com/a/uploads/cover.jpg"

    @staticmethod
    def _red(monkeypatch, handler):
        from zascarr.utils import url_portada

        async def resolutor(host, puerto):
            return ["93.184.216.34"]
        monkeypatch.setattr(url_portada, "resolver_dns", resolutor)
        def _cliente():
            return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)
        monkeypatch.setattr(url_portada, "_cliente_por_defecto", _cliente)

    @pytest.mark.asyncio
    async def test_descarga_correcta_guarda_el_fichero(self, tmp_path, monkeypatch):
        dest = tmp_path / "cover.jpg"
        self._red(monkeypatch, lambda r: httpx.Response(200, content=_fake_jpeg_bytes()))

        ok = await fetch_and_cache_cover(self.URL, dest)

        assert ok is True
        assert dest.exists()
        with Image.open(dest) as img:
            assert img.format == "JPEG"

    @pytest.mark.asyncio
    async def test_descarga_fallida_no_lanza_ni_cachea(self, tmp_path, monkeypatch):
        dest = tmp_path / "cover.jpg"

        def _caido(request):
            raise httpx.ConnectTimeout("timeout")
        self._red(monkeypatch, _caido)

        ok = await fetch_and_cache_cover(self.URL, dest)

        assert ok is False
        assert not dest.exists()

    @pytest.mark.asyncio
    async def test_sin_espacio_no_lanza_ni_cachea(self, tmp_path, monkeypatch):
        """#123b: si no cabe la portada, se omite con aviso; no se rompe la ficha."""
        dest = tmp_path / "cover.jpg"
        self._red(monkeypatch, lambda r: httpx.Response(200, content=_fake_jpeg_bytes()))

        def sin_espacio(*_a, **_k):
            raise EspacioInsuficienteError(
                bytes_libres=1, bytes_necesarios=1000, contexto="guardar la portada"
            )

        monkeypatch.setattr(zcover, "comprobar_espacio", sin_espacio)
        ok = await fetch_and_cache_cover(self.URL, dest)
        assert ok is False
        assert not dest.exists()

    @pytest.mark.asyncio
    async def test_imagen_ilegible_no_lanza_ni_cachea(self, tmp_path, monkeypatch):
        dest = tmp_path / "cover.jpg"
        self._red(monkeypatch, lambda r: httpx.Response(200, content=b"no es una imagen"))

        ok = await fetch_and_cache_cover(self.URL, dest)

        assert ok is False
        assert not dest.exists()

    @pytest.mark.asyncio
    async def test_fallo_al_publicar_no_deja_temporal_ni_pisa_la_cache_anterior(self, tmp_path, monkeypatch):
        """FR-12: la escritura de `fetch_and_cache_cover` también es atómica. Si el
        `os.replace` final falla, la caché anterior (completa) se conserva y el temporal no
        queda en el disco."""
        dest = tmp_path / "cover.jpg"
        anterior = _fake_jpeg_bytes()
        dest.write_bytes(anterior)
        self._red(monkeypatch, lambda r: httpx.Response(200, content=_fake_jpeg_bytes()))

        def _permiso_denegado(*_a, **_k):
            raise PermissionError(13, "Permiso denegado")

        # Se inyecta en la stdlib (`os.replace`), no en un atributo del módulo: así la prueba
        # falla por el comportamiento y no por un símbolo que aún no exista.
        monkeypatch.setattr(os, "replace", _permiso_denegado)

        ok = await fetch_and_cache_cover(self.URL, dest)

        assert ok is False
        assert dest.read_bytes() == anterior
        assert [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


# ─────────────────────────────────────────────────────────────────────────────
# BL-PORT1 (#300), PR-2: escritura segura de la caché (FR-11 y FR-12, AC-22/23/24)
#
# El bug que se cierra: `write_cover_cache` escribía directo en `covers/<id>.jpg`
# (un corte dejaba un JPEG truncado que `exists()` da por bueno para siempre) y,
# si la escritura fallaba, `portada()` pedía el `mtime` de un fichero que no
# existía → FileNotFoundError → 500 en vez de la portada ya extraída.
# ─────────────────────────────────────────────────────────────────────────────


def _jpeg(color: int = 40) -> bytes:
    """JPEG real (Pillow), pequeño, para no depender de bytes mágicos a mano."""
    buf = io.BytesIO()
    Image.new("RGB", (60, 90), color=(color, 40, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_cbz_con_pagina(path: Path) -> None:
    """CBZ mínimo con una página, como `tests/test_cover.py`: extracción real, sin dobles."""
    buf = io.BytesIO()
    Image.new("RGB", (600, 900), color=(120, 40, 200)).save(buf, format="JPEG")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("001.jpg", buf.getvalue())


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def first(self):
        return self._rows[0] if self._rows else None


class _SesionDePortada:
    """Sesión mínima de `portada()`: la serie y un único archivo extractable. Sin cola
    compartida a propósito: dos peticiones concurrentes pueden llamar a `get`/`execute`."""

    def __init__(self, series: Series, cbz: Path):
        self._series = series
        self._cbz = cbz

    async def get(self, _model, _id):
        return self._series

    async def execute(self, _statement):
        return _FakeResult([(str(self._cbz), None)])


@pytest.fixture
def portada_de_serie(tmp_path, monkeypatch):
    """CBZ real + caché redirigida a `tmp_path/covers` + sesión falsa.

    La caché NUNCA se escribe en la ruta real de ajustes (mismo patrón que
    `tests/test_web_series.py:646-652`)."""
    cbz = tmp_path / "comic.cbz"
    _make_cbz_con_pagina(cbz)
    covers = tmp_path / "covers"
    settings = get_settings().model_copy(update={"covers_cache_path": covers})
    monkeypatch.setattr("zascarr.web.series.get_settings", lambda: settings)

    series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                    start_year=1977)
    sesion = _SesionDePortada(series, cbz)

    async def _get_db():
        yield sesion

    app.dependency_overrides[get_db] = _get_db
    try:
        yield series, covers
    finally:
        app.dependency_overrides.pop(get_db, None)


def _temporales(carpeta: Path) -> list[Path]:
    """Restos de una escritura interrumpida en `carpeta` (nombre `.<destino>…tmp`)."""
    return [p for p in carpeta.iterdir() if p.name.endswith(".tmp")] if carpeta.exists() else []


class TestFalloDeDiscoEnLaPortada:
    """FR-11 (AC-22): si la caché no se puede escribir tras extraer el CBZ, se sirve la
    portada ya extraída con 200 y un ETag de sus bytes; nunca un 500."""

    def test_sin_espacio_sirve_la_portada_con_etag_de_bytes_y_304(self, portada_de_serie, monkeypatch):
        series, covers = portada_de_serie

        def _sin_espacio(*_a, **_k):
            raise EspacioInsuficienteError(
                bytes_libres=1, bytes_necesarios=1000, contexto="guardar la portada"
            )

        monkeypatch.setattr(zcover, "comprobar_espacio", _sin_espacio)

        with structlog.testing.capture_logs() as registros:
            cliente = TestClient(app)
            r = cliente.get(f"/ui/series/{series.id}/portada")

            assert r.status_code == 200, r.text
            assert r.headers["content-type"] == "image/jpeg"
            assert r.headers["cache-control"] == "private, max-age=86400"
            with Image.open(io.BytesIO(r.content)) as img:
                img.load()
                assert img.format == "JPEG"
            etag = r.headers["etag"]
            # El ETag sale de los bytes servidos: la segunda petición lo repite y da 304.
            r2 = cliente.get(f"/ui/series/{series.id}/portada",
                             headers={"If-None-Match": etag})
            assert r2.status_code == 304

        assert not (covers / f"{series.id}.jpg").exists()
        avisos = [a for a in registros if a["event"] == "cover.cache_sin_espacio"]
        assert avisos, f"no se registró el aviso de caché no escrita: {registros!r}"
        assert avisos[0]["motivo"] == "EspacioInsuficienteError"
        assert avisos[0]["errno"] is None      # el espacio se comprueba ANTES de escribir
        assert str(covers) not in repr(registros), "el aviso no debe llevar rutas del disco"

    def test_permiso_denegado_al_publicar_no_da_500(self, portada_de_serie, monkeypatch):
        series, covers = portada_de_serie

        def _permiso_denegado(*_a, **_k):
            raise PermissionError(13, "Permiso denegado")

        # El fallo se inyecta en la stdlib (`os.replace`), no en un atributo del módulo: el
        # temporal se escribe y lo que falla es la publicación en el destino.
        monkeypatch.setattr(os, "replace", _permiso_denegado)

        with structlog.testing.capture_logs() as registros:
            r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200, r.text
        with Image.open(io.BytesIO(r.content)) as img:
            img.load()
            assert img.format == "JPEG"
        assert not (covers / f"{series.id}.jpg").exists()
        assert _temporales(covers) == []
        avisos = [a for a in registros if a["event"] == "cover.cache_sin_espacio"]
        assert avisos and avisos[0]["motivo"] == "PermissionError"
        assert avisos[0]["errno"] == 13        # el errno real no se pierde como «OSError»
        assert str(covers) not in repr(registros)


def _falla_a_mitad_de_escritura(monkeypatch):
    """Simula un disco que se llena a mitad del temporal: escribe medio contenido y falla.

    Se inyecta en la stdlib (`os.fdopen`), no en un atributo del módulo, para que la prueba
    falle por el comportamiento y no por un símbolo que aún no exista (QA, 2026-11-05)."""
    original = os.fdopen

    class _FicheroQueCorta:
        def __init__(self, real):
            self._real = real

        def write(self, data):
            self._real.write(data[: max(1, len(data) // 2)])
            raise OSError(28, "No queda espacio en el dispositivo")

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self._real.close()
            return False

    monkeypatch.setattr(
        os, "fdopen", lambda fd, *a, **k: _FicheroQueCorta(original(fd, *a, **k))
    )


class TestEscrituraAtomica:
    """FR-12 (AC-23): temporal en el mismo directorio (`mkstemp`, `O_EXCL`) + `os.replace`.
    Un fallo a mitad de la escritura no deja `covers/<id>.jpg` truncado ni temporales, y la
    petición siguiente puede escribir la caché buena."""

    def test_fallo_a_mitad_no_publica_el_fichero_ni_deja_temporal(self, tmp_path, monkeypatch):
        dest = tmp_path / "covers" / "serie.jpg"

        with monkeypatch.context() as m:
            _falla_a_mitad_de_escritura(m)
            with pytest.raises(OSError):
                write_cover_cache(dest, _jpeg())

        assert not dest.exists()
        assert list((tmp_path / "covers").iterdir()) == []

    def test_fallo_a_mitad_no_deja_cache_truncada_y_la_siguiente_peticion_la_escribe(
        self, portada_de_serie, monkeypatch
    ):
        series, covers = portada_de_serie
        dest = covers / f"{series.id}.jpg"

        with monkeypatch.context() as m:
            _falla_a_mitad_de_escritura(m)
            r = TestClient(app).get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200                       # el corte no rompe la petición…
        with Image.open(io.BytesIO(r.content)) as img:
            img.load()
            assert img.format == "JPEG"                   # …y se sirve el JPEG completo
        assert not dest.exists(), "quedó una caché a medias que exists() daría por buena"
        assert _temporales(covers) == []

        r2 = TestClient(app).get(f"/ui/series/{series.id}/portada")
        assert r2.status_code == 200
        assert dest.exists()
        with Image.open(dest) as img:
            img.load()
            assert img.format == "JPEG"
        # Ya cacheada, vuelve al ETag por mtime de siempre.
        assert r2.headers["etag"] == f'"{dest.stat().st_mtime}"'

    def test_escritura_buena_publica_el_fichero_entero(self, tmp_path):
        dest = tmp_path / "covers" / "serie.jpg"
        datos = _jpeg()
        write_cover_cache(dest, datos)
        assert dest.read_bytes() == datos
        assert list((tmp_path / "covers").iterdir()) == [dest]

    def test_no_se_sigue_un_symlink_plantado_con_forma_de_temporal(self, tmp_path):
        """`mkstemp` crea el temporal con `O_EXCL` y nombre aleatorio: un enlace plantado con
        la forma `.<destino>.…zascarr.tmp` (la que tenía el nombre predecible) no se abre, no
        se sigue y no se pisa."""
        dest = tmp_path / "serie.jpg"
        victima = tmp_path / "victima.txt"
        victima.write_bytes(b"intacto")
        plantado = tmp_path / f".{dest.name}.plantado.zascarr.tmp"
        plantado.symlink_to(victima)

        write_cover_cache(dest, b"jpeg")

        assert victima.read_bytes() == b"intacto"
        assert plantado.is_symlink()
        assert dest.read_bytes() == b"jpeg"


class TestDosPeticionesALaVez:
    """FR-12 + NFR-10 (AC-24): duplicar la extracción es aceptable; corromper el fichero o
    servir un JPEG truncado, no. Sin lock: la publicación atómica es la que protege."""

    async def test_dos_peticiones_concurrentes_dejan_un_jpeg_valido_sin_temporales(
        self, portada_de_serie
    ):
        series, covers = portada_de_serie
        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transporte, base_url="http://localhost",
            headers={"Origin": "http://localhost"},
        ) as cliente:
            respuestas = await asyncio.gather(
                cliente.get(f"/ui/series/{series.id}/portada"),
                cliente.get(f"/ui/series/{series.id}/portada"),
            )

        assert [r.status_code for r in respuestas] == [200, 200]
        cuerpos = []
        for r in respuestas:
            with Image.open(io.BytesIO(r.content)) as img:
                img.load()                                  # un JPEG truncado revienta aquí
                assert img.format == "JPEG"
            cuerpos.append(r.content)

        dest = covers / f"{series.id}.jpg"
        assert dest.exists()
        assert _temporales(covers) == []
        with Image.open(dest) as img:
            img.load()
            assert img.format == "JPEG"
        assert cuerpos[0] == cuerpos[1] == dest.read_bytes()


class TestCacheYaEscrita:
    """FR-10 (regresión): una caché existente se sirve como hoy — ETag por `mtime`,
    `Cache-Control: private, max-age=86400` y 304 con `If-None-Match` — sin extraer ni reescribir."""

    def test_se_sirve_con_etag_por_mtime_y_no_se_toca(self, portada_de_serie):
        series, covers = portada_de_serie
        covers.mkdir(parents=True)
        dest = covers / f"{series.id}.jpg"
        dest.write_bytes(_jpeg())

        cliente = TestClient(app)
        r = cliente.get(f"/ui/series/{series.id}/portada")

        assert r.status_code == 200
        assert r.headers["etag"] == f'"{dest.stat().st_mtime}"'
        assert r.headers["cache-control"] == "private, max-age=86400"
        assert r.content == dest.read_bytes()

        r2 = cliente.get(f"/ui/series/{series.id}/portada",
                         headers={"If-None-Match": r.headers["etag"]})
        assert r2.status_code == 304
        assert r2.content == b""
