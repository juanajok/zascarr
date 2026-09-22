"""
tests/test_cover_cache.py

Suite de la caché unificada de portadas (C1): cached_image_response (304
condicional, cabeceras de caché) y fetch_and_cache_cover (descarga +
resize + guardado, sin lanzar si algo falla). Sin URLs reales — un
ASGITransport/monkeypatch de httpx hace de servidor falso.
"""
from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import Request
from PIL import Image

from secuenciarr.utils.cover import cached_image_response, fetch_and_cache_cover


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

    @pytest.mark.asyncio
    async def test_descarga_correcta_guarda_el_fichero(self, tmp_path):
        dest = tmp_path / "cover.jpg"
        fake_response = httpx.Response(200, content=_fake_jpeg_bytes(), request=httpx.Request("GET", "http://x"))

        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=fake_response)):
            ok = await fetch_and_cache_cover("http://cdn.example/cover.jpg", dest)

        assert ok is True
        assert dest.exists()
        with Image.open(dest) as img:
            assert img.format == "JPEG"

    @pytest.mark.asyncio
    async def test_descarga_fallida_no_lanza_ni_cachea(self, tmp_path):
        dest = tmp_path / "cover.jpg"
        with patch("httpx.AsyncClient.get", new=AsyncMock(side_effect=httpx.ConnectTimeout("timeout"))):
            ok = await fetch_and_cache_cover("http://cdn.muerto/cover.jpg", dest)

        assert ok is False
        assert not dest.exists()

    @pytest.mark.asyncio
    async def test_imagen_ilegible_no_lanza_ni_cachea(self, tmp_path):
        dest = tmp_path / "cover.jpg"
        fake_response = httpx.Response(200, content=b"no es una imagen", request=httpx.Request("GET", "http://x"))
        with patch("httpx.AsyncClient.get", new=AsyncMock(return_value=fake_response)):
            ok = await fetch_and_cache_cover("http://cdn.example/cover.jpg", dest)

        assert ok is False
        assert not dest.exists()
