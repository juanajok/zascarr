"""Compresión del texto y no de lo ya comprimido (benchmark-calidad-front, hallazgo 7).

Medido en la Pi 5 el 2026-11-22: `web.css` pasa de 176 KB a 39,5 KB con gzip de nivel 6 en 5,7 ms de
CPU. Las portadas, las páginas del lector y las fuentes no ganan nada y gastarían CPU.
"""
from __future__ import annotations

import gzip

from fastapi.testclient import TestClient
from starlette.middleware.gzip import GZipMiddleware

from zascarr.main import app


def _gzip():
    return next(m for m in app.user_middleware if m.cls is GZipMiddleware)


def test_el_css_se_sirve_comprimido_y_se_puede_revalidar():
    c = TestClient(app)
    r = c.get("/static/web.css", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers["content-encoding"] == "gzip"
    assert "accept-encoding" in r.headers["vary"].lower()
    assert r.num_bytes_downloaded < 60_000                       # 176 KB sin comprimir
    assert r.headers.get("etag")                                  # el 304 por ETag sigue igual
    revalidada = c.get("/static/web.css", headers={"Accept-Encoding": "gzip",
                                                   "If-None-Match": r.headers["etag"]})
    assert revalidada.status_code == 304


def test_sin_accept_encoding_no_se_comprime():
    r = TestClient(app).get("/static/web.css", headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in r.headers


def test_las_imagenes_y_lo_ya_comprimido_no_se_recomprimen():
    r = TestClient(app).get("/static/brand/apple-touch-icon.png",
                            headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and "content-encoding" not in r.headers
    excluidos = _gzip().kwargs["exclude_content_types"]
    for tipo in ("image/jpeg", "image/png", "image/webp", "font/woff2", "application/zip",
                 "application/octet-stream", "application/pdf", "application/epub+zip"):
        assert tipo in excluidos, tipo


def test_nivel_y_tamano_minimo_medidos():
    kwargs = _gzip().kwargs
    assert kwargs["compresslevel"] == 6 and kwargs["minimum_size"] == 1024
    assert gzip.decompress(gzip.compress(b"x" * 2048, 6)) == b"x" * 2048
