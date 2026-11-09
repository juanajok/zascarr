"""#129 A: comparación de solo lectura y rutas web. Sin red."""
from __future__ import annotations

import copy
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
                           publisher=SimpleNamespace(name="Panini Cómics"),
                           comic_vine_id=1, anilist_id=None, tebeosfera_slug=None,
                           gcd_id=None, tradition=None, metadata_={}, locked_fields=[],
                           metadata_source=None)


def _busqueda(resultados, estado=None, fuente=MetadataSource.GCD):
    estado = estado or _estado()
    return Busqueda(list(resultados), [], {fuente.value: estado.estado},
                    {fuente.value: estado})


@pytest.fixture(autouse=True)
def _secreto(monkeypatch):
    import zascarr.services.asociar_fuente as servicio
    monkeypatch.setattr(servicio, "get_settings",
                        lambda: SimpleNamespace(secret_key="x" * 32))


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
    async def test_no_escribe_nada_ni_muta_la_serie(self, fake_discovery):
        fake_discovery([_resultado()])
        serie = _serie()
        antes = copy.deepcopy(serie.__dict__)
        db = _DB(serie)
        await comparar(db, uuid4(), MetadataSource.GCD)
        assert db.added == [] and db.committed is False
        assert serie.__dict__ == antes

    @pytest.mark.asyncio
    async def test_sin_identidad_no_consulta_ni_ofrece_asociar(self, fake_discovery):
        from zascarr.services.asociar_fuente import SerieSinIdentidadError
        serie = _serie()
        serie.comic_vine_id = serie.anilist_id = serie.tebeosfera_slug = serie.gcd_id = None
        llamado = []
        fake_discovery([])
        with pytest.raises(SerieSinIdentidadError):
            await comparar(_DB(serie), uuid4(), MetadataSource.GCD)
        assert llamado == []

    @pytest.mark.asyncio
    async def test_token_de_candidata_seleccionable(self, fake_discovery):
        from zascarr.services.tokens_revision import (
            MAX_TOKEN_ASOCIACION,
            verificar_token_asociacion,
        )
        fake_discovery([_resultado(kind="collection", editorial="Panini", pais="ES")])
        comp = await comparar(_DB(_serie()), uuid4(), MetadataSource.GCD)
        c = comp.candidatas[0]
        assert c.token and len(c.token) <= MAX_TOKEN_ASOCIACION
        firmada = verificar_token_asociacion(c.token, "x" * 32)
        assert firmada is not None
        assert (firmada.entidad, firmada.kind) == ("serie", "collection")
        assert firmada.id_externo == "123" and firmada.fuente == "gcd"
        assert firmada.operacion and len(firmada.huella) == 64

    @pytest.mark.asyncio
    async def test_saga_no_emite_token(self, fake_discovery):
        fake_discovery([_resultado(kind="saga")])
        comp = await comparar(_DB(_serie()), uuid4(), MetadataSource.TEBEOSFERA)
        assert comp.candidatas[0].seleccionable is False
        assert comp.candidatas[0].token is None

    @pytest.mark.asyncio
    async def test_huella_canonica_depende_de_datos_y_es_estable(self, fake_discovery):
        from zascarr.services.asociar_fuente import huella_de_asociacion
        fake_discovery([_resultado()])
        comp = await comparar(_DB(_serie()), uuid4(), MetadataSource.GCD)
        serie = _serie()
        c = comp.candidatas[0]
        assert huella_de_asociacion(serie, c) == huella_de_asociacion(serie, c)
        serie.metadata_ = {"asociaciones": [{"fuente": "gcd", "id_externo": "999"}]}
        assert huella_de_asociacion(serie, c) != huella_de_asociacion(_serie(), c)


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
        assert " checked>" not in r.text
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


class TestQAMaxYPrevisualizacion:
    def teardown_method(self):
        app.dependency_overrides.pop(get_db, None)

    def test_post_sin_fuente_es_estado_claro_no_422(self, monkeypatch):
        monkeypatch.setattr(web, "get_settings", _settings)
        serie = _serie()
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/buscar", data={"fuente": ""})
        assert r.status_code == 400
        assert "Elige una web antes de buscar." in r.text
        assert r.headers["cache-control"] == "no-store"

    def test_q_mayor_que_200_es_422(self, monkeypatch):
        monkeypatch.setattr(web, "get_settings", _settings)
        serie = _serie()
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/buscar",
            data={"fuente": "gcd", "q": "x" * 201})
        assert r.status_code == 422

    def test_401_403_cv_usa_copy_de_clave_no_aceptada(self, monkeypatch):
        monkeypatch.setattr(web, "get_settings", _settings)
        comp = _comparacion([])
        comp = type(comp)(**{**comp.__dict__, "estado": EstadoFuente(
            "comic_vine", "busqueda", "configuracion_incompleta",
            "La clave de Comic Vine no se ha aceptado.")})
        monkeypatch.setattr(web, "comparar", AsyncMock(return_value=comp))
        serie = _serie()
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/buscar", data={"fuente": "gcd"})
        assert "La clave de Comic Vine no se ha aceptado." in r.text
        assert "falta su clave" not in r.text

    def test_resultados_tienen_aria_live_y_ficha(self, monkeypatch):
        monkeypatch.setattr(web, "get_settings", _settings)
        from zascarr.services.asociar_fuente import CandidataComparada
        comp = _comparacion([CandidataComparada(
            titulo="The Wicked + The Divine", anio=2014, editorial=None, pais="US",
            idioma="en", id_externo="123",
            sitio_url="https://www.comics.org/series/123/", tradicion="american",
            kind="collection", fuente="gcd")])
        monkeypatch.setattr(web, "comparar", AsyncMock(return_value=comp))
        serie = _serie()
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/buscar", data={"fuente": "gcd"})
        assert 'aria-live="polite"' in r.text and "Ficha 123" in r.text

    def test_el_token_maximo_real_no_da_422_en_la_preview(self, monkeypatch):
        from zascarr.services.tokens_revision import (
            MAX_ID_ASOCIACION,
            MAX_SITIO_URL,
            MAX_TITULO,
            AsociacionFirmada,
            crear_token_asociacion,
        )
        monkeypatch.setattr(web, "get_settings", lambda: SimpleNamespace(
            secret_key="x" * 32, comicvine_enabled=True, anilist_enabled=True,
            tebeosfera_enabled=True, gcd_enabled=True, comicvine_api_key="clave"))
        serie = _serie()
        ch = "\U0001F600"
        url = "http://e.co/" + ch * (MAX_SITIO_URL - len("http://e.co/"))
        token = crear_token_asociacion(AsociacionFirmada(
            1, "serie", "collection", "tebeosfera", ch * MAX_ID_ASOCIACION,
            ch * MAX_TITULO, 2006, url, "f" * 64,
            "00000000-0000-4000-8000-000000000000", str(serie.id)), "x" * 32)
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/previsualizar", data={"token": token})
        assert r.status_code == 200, r.text
        assert r.headers["cache-control"] == "no-store"

    def test_previsualizar_sin_escribir_y_sin_store(self, monkeypatch):
        from zascarr.services.tokens_revision import (
            AsociacionFirmada,
            crear_token_asociacion,
        )
        monkeypatch.setattr(web, "get_settings",
                            lambda: SimpleNamespace(secret_key="x" * 32,
                                                    comicvine_enabled=True,
                                                    anilist_enabled=True,
                                                    tebeosfera_enabled=True,
                                                    gcd_enabled=True,
                                                    comicvine_api_key="clave"))
        serie = _serie()
        token = crear_token_asociacion(AsociacionFirmada(
            version=1, entidad="serie", kind="collection", fuente="gcd",
            id_externo="123", titulo="The Wicked + The Divine", anio=2014,
            sitio_url="https://www.comics.org/series/123/", huella="f" * 64,
            operacion="00000000-0000-4000-8000-000000000000",
            serie_id=str(serie.id)), "x" * 32)
        antes = copy.deepcopy(serie.__dict__)
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/previsualizar", data={"token": token})
        assert r.status_code == 200
        assert "Asociar esta ficha" in r.text and "Tipo" in r.text and "Serie" in r.text
        assert "Ficha" in r.text and "123" in r.text
        assert r.headers["cache-control"] == "no-store"
        assert serie.__dict__ == antes
