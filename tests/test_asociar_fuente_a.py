"""#129 A: comparación de solo lectura y rutas web. Sin red."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import MetadataSource
from zascarr.services.asociar_fuente import (
    _url_segura,
    comparar,
    normalizar_consulta,
)
from zascarr.services.discovery import (
    Busqueda,
    DiscoveryResult,
    _clasificar_outcome,
)
from zascarr.services.estados_fuentes import EstadoFuente
from zascarr.utils.peticiones import RespuestaNoTransitoria
from zascarr.web import asociar_fuente as web


def _estado(estado="ok", motivo=None, capacidad="busqueda"):
    return EstadoFuente("gcd", capacidad, estado, motivo)


def _resultado(**extra):
    base = dict(source=MetadataSource.GCD, external_id="123", title="The Wicked + The Divine",
                start_year=2014, description=None, cover_url=None,
                site_url="https://www.comics.org/series/123/",
                editorial=None, pais=None, idioma=None, kind=None)
    base.update(extra)
    return DiscoveryResult(**base)


class _DB:
    def __init__(self, serie):
        self._serie = serie
        self.added = []
        self.committed = False

    async def execute(self, _statement):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=self._serie)
        return r

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _serie():
    return SimpleNamespace(id=uuid4(), title="The Wicked + The Divine", start_year=2014,
                           publisher=SimpleNamespace(name="Panini Cómics"))


def _busqueda(resultados, estado=None, fuente=MetadataSource.GCD):
    estado = estado or _estado()
    return Busqueda(list(resultados), [], {fuente.value: estado.estado},
                    {fuente.value: estado})


@pytest.fixture
def fake_discovery(monkeypatch):
    def _instalar(resultados, estado=None):
        class _Fake:
            def __init__(self, _db):
                pass

            async def buscar_en(self, fuente, _q, limit=10):
                return _busqueda(resultados, estado, fuente)
        monkeypatch.setattr("zascarr.services.asociar_fuente.DiscoveryService", _Fake)
    return _instalar


class TestModelo:
    @pytest.mark.asyncio
    async def test_campos_acreditados_y_no_consta(self, fake_discovery):
        fake_discovery([_resultado(editorial="Panini", pais="ES", idioma="es")])
        comp = await comparar(_DB(_serie()), uuid4(), MetadataSource.GCD)
        assert comp.titulo_local == "The Wicked + The Divine"
        assert comp.editorial_local == "Panini Cómics"
        assert comp.pais_local is None and comp.idioma_local is None
        c = comp.candidatas[0]
        assert (c.editorial, c.pais, c.idioma) == ("Panini", "ES", "es")
        assert c.sitio_url == "https://www.comics.org/series/123/"
        assert c.seleccionable

    @pytest.mark.asyncio
    async def test_saga_no_seleccionable_y_solo_sagas_sin_resultados(self, fake_discovery):
        fake_discovery([_resultado(kind="saga", title="The Wicked + The Divine")])
        comp = await comparar(_DB(_serie()), uuid4(), MetadataSource.TEBEOSFERA)
        # El fixture usa fuente GCD; se fuerza la comparación a Tebeosfera en el candidato.
        assert comp.candidatas[0].kind == "saga"
        assert comp.candidatas[0].seleccionable is False
        assert comp.estado.estado == "sin_resultados"
        assert "saga" in (comp.estado.motivo or "").lower()

    @pytest.mark.asyncio
    async def test_cada_estado_133_llega_al_modelo(self, fake_discovery):
        for estado in ("fuente_apagada", "configuracion_incompleta",
                       "limite_de_cortesia", "fallo_transitorio", "sin_resultados"):
            fake_discovery([], _estado(estado))
            comp = await comparar(_DB(_serie()), uuid4(), MetadataSource.GCD)
            assert comp.estado.estado == estado
            assert comp.candidatas == []

    @pytest.mark.asyncio
    async def test_no_escribe_nada(self, fake_discovery):
        fake_discovery([_resultado()])
        db = _DB(_serie())
        await comparar(db, uuid4(), MetadataSource.GCD)
        assert db.added == [] and db.committed is False


class TestEntradasYSeguridad:
    def test_q_acotada_y_sin_controles(self):
        assert normalizar_consulta("  a" * 300) == ("a " * 100).strip()[:200]
        assert len(normalizar_consulta("x" * 500)) <= 200
        assert "\x00" not in normalizar_consulta("Thorgal\x00")
        assert normalizar_consulta("  Thorgal   y  Aaricia ") == "Thorgal y Aaricia"

    @pytest.mark.parametrize("url", [
        "javascript:alert(1)", "ftp://x/y", "file:///etc/passwd",
        "https://user:pass@x/y", "//evil.example/x",
    ])
    def test_sitio_url_no_http_se_descarta(self, url):
        assert _url_segura(url) is None

    def test_401_de_comic_vine_es_configuracion(self):
        estado, rs, avisos = _clasificar_outcome(
            MetadataSource.COMIC_VINE, "Comic Vine", RespuestaNoTransitoria(401))
        assert estado.estado == "configuracion_incompleta"
        assert rs == [] and avisos == []


class FakeSession:
    def __init__(self, serie):
        self._serie = serie

    async def execute(self, _statement):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=self._serie)
        return r


def _web_client(db):
    async def _get_db():
        yield db
    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _settings():
    return SimpleNamespace(comicvine_enabled=True, anilist_enabled=True,
                           tebeosfera_enabled=True, gcd_enabled=True,
                           comicvine_api_key="clave")


def _comparacion(candidatas):
    serie = _serie()
    return __import__("zascarr.services.asociar_fuente", fromlist=["Comparacion"]).Comparacion(
        serie_id=str(serie.id), titulo_local=serie.title, anio_local=2014,
        editorial_local="Panini Cómics", pais_local=None, idioma_local=None,
        fuente=MetadataSource.GCD, consulta="The Wicked + The Divine",
        estado=_estado(), avisos=[], candidatas=candidatas)


class TestWeb:
    def teardown_method(self):
        app.dependency_overrides.pop(get_db, None)

    def test_formulario_sin_fuente_seleccionada_y_no_store(self, monkeypatch):
        monkeypatch.setattr(web, "get_settings", _settings)
        r = _web_client(FakeSession(_serie())).get(f"/ui/series/{_serie().id}/asociar")
        # El id del helper no coincide; se repite con el mismo objeto del fake.
        assert r.status_code == 200
        assert "Asociar fuente" in r.text and "Buscar por título" in r.text
        assert "checked" not in r.text
        assert r.headers["cache-control"] == "no-store"

    def test_post_con_candidata_y_no_store(self, monkeypatch):
        monkeypatch.setattr(web, "get_settings", _settings)
        from zascarr.services.asociar_fuente import CandidataComparada
        comp = _comparacion([CandidataComparada(
            titulo="The Wicked + The Divine", anio=2014, editorial=None, pais="US",
            idioma="en", id_externo="123",
            sitio_url="https://www.comics.org/series/123/", tradicion="american",
            kind="collection")])
        monkeypatch.setattr(web, "comparar", AsyncMock(return_value=comp))
        serie = _serie()
        db = FakeSession(serie)
        r = _web_client(db).post(f"/ui/series/{serie.id}/asociar/buscar",
                                 data={"fuente": "gcd", "q": "The Wicked"})
        assert r.status_code == 200
        assert "Fichas encontradas en GCD" in r.text
        assert "No consta" in r.text
        assert 'rel="noopener noreferrer"' in r.text
        assert r.headers["cache-control"] == "no-store"

    def test_post_estado_apagada_no_consulta(self, monkeypatch):
        monkeypatch.setattr(web, "get_settings", _settings)
        comp = _comparacion([])
        comp = type(comp)(**{**comp.__dict__, "estado": _estado("fuente_apagada")})
        monkeypatch.setattr(web, "comparar", AsyncMock(return_value=comp))
        serie = _serie()
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/buscar", data={"fuente": "gcd"})
        assert r.status_code == 200
        assert "No se ha consultado" in r.text and "apagada en Ajustes" in r.text
