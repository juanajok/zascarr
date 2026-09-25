"""
tests/test_web_discovery.py

Suite de /ui/descubrir (C0): contrato HTTP del alta de series externas.
Mismo patrón de FakeSession que tests/test_api_series.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.discovery import DiscoveryResult


class FakeSession:
    def __init__(self, existing=None):
        self._existing = existing
        self.added: list = []

    async def execute(self, _statement):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=self._existing)
        return result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None


def _override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


class TestIndex:

    def test_pagina_de_busqueda_responde_200_con_nav(self):
        client = TestClient(app)
        r = client.get("/ui/descubrir")
        assert r.status_code == 200
        assert '<nav class="topnav">' in r.text
        assert "Descubrir" in r.text


class TestBuscar:

    def test_busca_y_renderiza_resultados(self):
        resultados = [
            DiscoveryResult(
                source=MetadataSource.COMIC_VINE, external_id="1234",
                title="Batman", start_year=2011, description=None,
                cover_url=None, tradition_guess=ComicTradition.AMERICAN,
            )
        ]
        with use_fake_session(FakeSession()) as client, \
             patch("zascarr.web.discovery.DiscoveryService.search",
                   AsyncMock(return_value=resultados)):
            r = client.get("/ui/descubrir/buscar", params={"q": "Batman"})

        assert r.status_code == 200
        assert "Batman" in r.text
        assert "comic_vine" in r.text

    def test_sin_resultados_muestra_mensaje(self):
        with use_fake_session(FakeSession()) as client, \
             patch("zascarr.web.discovery.DiscoveryService.search",
                   AsyncMock(return_value=[])):
            r = client.get("/ui/descubrir/buscar", params={"q": "xyz"})

        assert "Sin coincidencias" in r.text


class TestCrear:

    def test_crea_serie_sin_exigir_aceptacion_legal(self):
        """Bug de diseño evitado a propósito: dar de alta una serie es
        catalogar metadatos, no descargar nada — a diferencia de
        /ui/wishlist/anadir, esta ruta NUNCA debe devolver 403 por falta
        de aceptación legal."""
        with use_fake_session(FakeSession(existing=None)) as client:
            r = client.post("/ui/descubrir/crear", data={
                "source": "comic_vine", "external_id": "1234",
                "title": "Batman", "tradition": "american",
                "start_year": "2011",
            })

        assert r.status_code == 200
        assert "Batman" in r.text
        assert "Ver ficha" in r.text
        assert "Añadir a deseados" in r.text

    def test_id_externo_ya_registrado_reutiliza_la_serie(self):
        existente = Series(title="Batman", comic_vine_id=1234)
        with use_fake_session(FakeSession(existing=existente)) as client:
            r = client.post("/ui/descubrir/crear", data={
                "source": "comic_vine", "external_id": "1234",
                "title": "Batman", "tradition": "american",
            })

        assert r.status_code == 200
        assert "ya estaba en tu biblioteca" in r.text
