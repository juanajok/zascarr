# ruff: noqa: E501
"""
tests/test_web_discovery.py

Suite de /ui/descubrir (C0): contrato HTTP de la búsqueda y de la creación en dos pasos (I2 de #114). Aquí, lo que no
necesita base de datos (FakeSession, mismo patrón que tests/test_api_series.py); el recorrido completo contra Postgres
real está en tests/test_descubrir_dos_pasos_pg.py.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.discovery import Busqueda, DiscoveryResult, ProcedenciaTradicion
from zascarr.services.tokens_revision import (
    CLAVE_SIN_GRUPO,
    MAX_TOKEN_ALTA,
    verificar_token_candidata,
)


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
        # V3: la barra de navegación nueva sustituye a `<nav class="topnav">` (cambio a propósito).
        assert '<nav class="nav" aria-label="Navegación principal">' in r.text
        assert "Descubrir" in r.text


class TestIndexConBusquedaPrevia:
    """V4: «Buscar una serie» del Inicio llega con `?q=` y la búsqueda se lanza al cargar."""

    def test_con_q_prellena_la_caja_y_lanza_la_busqueda_al_cargar(self):
        r = TestClient(app).get("/ui/descubrir", params={"q": "Batman"})
        assert r.status_code == 200
        assert 'value="Batman"' in r.text
        assert 'hx-trigger="keyup changed delay:400ms, load"' in r.text
        assert 'hx-get="/ui/descubrir/buscar"' in r.text

    def test_sin_q_no_lanza_nada_al_cargar(self):
        r = TestClient(app).get("/ui/descubrir")
        assert 'hx-trigger="keyup changed delay:400ms"' in r.text
        assert ", load" not in r.text
        assert 'value="' not in r.text.split("series-search")[1].split(">")[0]

    def test_q_en_blanco_cuenta_como_sin_q(self):
        r = TestClient(app).get("/ui/descubrir", params={"q": "   "})
        assert ", load" not in r.text

    def test_q_se_escapa(self):
        r = TestClient(app).get("/ui/descubrir", params={"q": '"><script>alert(1)</script>'})
        assert "<script>alert(1)" not in r.text
        assert "&lt;script&gt;" in r.text

    def test_q_demasiado_larga_se_rechaza(self):
        assert TestClient(app).get("/ui/descubrir", params={"q": "x" * 201}).status_code == 422


SECRETO = "secreto-de-prueba-para-firmar"


@pytest.fixture
def con_clave_de_firma(monkeypatch):
    """La ruta firma los resultados con `secret_key`: en las pruebas se fija una."""
    import zascarr.web.discovery as web
    monkeypatch.setattr(web, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))


def _resultado(**kw):
    base = dict(
        source=MetadataSource.COMIC_VINE, external_id="1234", title="Batman", start_year=2011, description=None,
        cover_url=None, site_url="https://comicvine.gamespot.com/batman/4050-1234/",
        tradition_guess=ComicTradition.AMERICAN,
        tradition_provenance=ProcedenciaTradicion.POR_DEFECTO)
    return DiscoveryResult(**{**base, **kw})


@pytest.mark.usefixtures("con_clave_de_firma")
class TestBuscar:

    def test_busca_y_renderiza_resultados(self):
        with use_fake_session(FakeSession()) as client, \
             patch("zascarr.web.discovery.DiscoveryService.search_detallada",
                   AsyncMock(return_value=Busqueda([_resultado()], [], {"comic_vine": "ok", "anilist": "ok", "tebeosfera": "ok", "gcd": "ok"}))):
            r = client.get("/ui/descubrir/buscar", params={"q": "Batman"})

        assert r.status_code == 200
        assert "Batman" in r.text
        assert "Comic Vine" in r.text and "comic_vine" not in r.text.split("<main", 1)[-1].lower().replace('value="comic_vine"', "")

    def test_sin_resultados_muestra_mensaje(self):
        with use_fake_session(FakeSession()) as client, \
             patch("zascarr.web.discovery.DiscoveryService.search_detallada",
                   AsyncMock(return_value=Busqueda([], [], {"comic_vine": "ok", "anilist": "ok", "tebeosfera": "ok", "gcd": "ok"}))):
            r = client.get("/ui/descubrir/buscar", params={"q": "xyz"})

        assert "Sin coincidencias" in r.text

    def test_muestra_avisos_de_fuentes_no_configuradas_o_caidas(self):
        with use_fake_session(FakeSession()) as client, \
             patch("zascarr.web.discovery.DiscoveryService.search_detallada",
                   AsyncMock(return_value=Busqueda([], [], {"comic_vine": "sin_clave", "anilist": "error", "tebeosfera": "ok", "gcd": "apagada"}))):
            r = client.get("/ui/descubrir/buscar", params={"q": "xyz"})

        assert "Comic Vine no está configurado" in r.text and "No respondió AniList" in r.text

    # ── I2 de #114: lo que vuelve del navegador es un token firmado, no datos de la serie ──

    def _buscar(self, resultados):
        with use_fake_session(FakeSession()) as client, \
             patch("zascarr.web.discovery.DiscoveryService.search_detallada",
                   AsyncMock(return_value=Busqueda(resultados, [], {"comic_vine": "ok", "anilist": "ok", "tebeosfera": "ok", "gcd": "ok"}))):
            return client.get("/ui/descubrir/buscar", params={"q": "x"}).text

    def test_la_tarjeta_reenvia_solo_un_token_y_no_datos_de_la_serie(self):
        html = self._buscar([_resultado(description="Murciélago.", cover_url="https://comicvine.gamespot.com/a.jpg")])
        assert 'name="candidata"' in html
        for campo in ("title", "external_id", "source", "start_year", "description", "cover_url"):
            assert f'name="{campo}"' not in html, campo

    def test_el_token_de_la_tarjeta_lo_firmo_el_servidor_con_el_contexto_sin_grupo(self):
        import re
        html = self._buscar([_resultado(external_id="1234")])
        token = re.search(r'name="candidata" value="([^"]+)"', html).group(1)
        c = verificar_token_candidata(token, CLAVE_SIN_GRUPO, SECRETO)
        assert (c.fuente, c.id_externo, c.titulo, c.anio) == ("comic_vine", "1234", "Batman", 2011)
        assert verificar_token_candidata(token, "Comics/Flash (1987)", SECRETO) is None     # no vale en un grupo

    def test_la_tradicion_no_viene_preseleccionada_y_la_sugerencia_es_solo_un_texto(self):
        html = self._buscar([_resultado(tradition_guess=ComicTradition.MANGA,
                                        tradition_provenance=ProcedenciaTradicion.EXPLICITA)])
        select = html[html.index("<select"):html.index("</select>")]
        assert "required" in select and select.count("selected") == 1          # solo el marcador vacío
        assert 'value="" selected disabled' in select
        assert 'value="manga" selected' not in select
        assert "La fuente lo clasifica como Manga" in html
        assert "no de la obra: elige tú" in html

    def test_la_portada_no_permitida_no_se_muestra_ni_se_firma(self):
        html = self._buscar([_resultado(cover_url="http://127.0.0.1:9091/x.jpg")])
        assert "127.0.0.1" not in html and 'class="portada-marca"' in html and "<img" not in html

    def test_un_resultado_que_no_se_puede_firmar_se_omite_con_aviso(self):
        malo = _resultado(external_id="x" * 300, title="Malo")                  # el identificador no cabe en lo que se guarda
        html = self._buscar([malo, _resultado(external_id="1", title="Bueno")])
        assert "Bueno" in html and "Malo" not in html
        assert "Se han omitido 1 resultado(s)" in html

    def test_sin_clave_de_firma_no_se_ofrece_nada_que_crear(self, monkeypatch):
        import zascarr.web.discovery as web
        monkeypatch.setattr(web, "get_settings", lambda: SimpleNamespace(secret_key=""))
        html = self._buscar([_resultado()])
        assert "no tiene clave para firmar" in html and 'name="candidata"' not in html


@pytest.mark.usefixtures("con_clave_de_firma")
class TestEscenariosCA6DeU15:
    """Mapeo 1:1 de los cinco escenarios de CA6 de #202 (#276).

    Los cuatro primeros se comprueban en el HTML de Descubrir; el quinto, la elección explícita de la persona,
    se completa en `test_descubrir_dos_pasos_pg.py::TestRevisarNoEscribeNada` y
    `TestCrear::test_crea_la_serie_con_la_tradicion_elegida...`, donde la tradición elegida manda sobre la sugerida.
    """

    def _buscar(self, resultados):
        with use_fake_session(FakeSession()) as client, \
             patch("zascarr.web.discovery.DiscoveryService.search_detallada",
                   AsyncMock(return_value=Busqueda(resultados, [], {"comic_vine": "ok", "anilist": "ok", "tebeosfera": "ok", "gcd": "ok"}))):
            return client.get("/ui/descubrir/buscar", params={"q": "x"}).text

    @staticmethod
    def _select(html: str) -> str:
        return html[html.index("<select"):html.index("</select>")]

    def test_dato_explicito_respaldado_se_presenta_como_pista_y_no_se_preselecciona(self):
        """AniList declara el tipo manga: se conserva la copy original de U15 y no se preselecciona."""
        html = self._buscar([_resultado(
            source=MetadataSource.ANILIST, external_id="1", title="One Piece", start_year=1997,
            site_url=None, tradition_guess=ComicTradition.MANGA,
            tradition_provenance=ProcedenciaTradicion.EXPLICITA)])
        select = self._select(html)
        assert select.count("selected") == 1 and 'value="" selected disabled' in select
        assert 'value="manga" selected' not in select
        assert "La fuente lo clasifica como Manga" in html
        assert "no de la obra: elige tú" in html

    def test_sugerencia_no_fiable_de_comic_vine_para_un_tebeo_es_solo_una_pista(self):
        """El caso original: Mortadelo devuelto por Comic Vine como «Grapa americana»."""
        html = self._buscar([_resultado(
            source=MetadataSource.COMIC_VINE, external_id="mortadelo", title="Mortadelo y Filemón",
            start_year=1958, site_url=None, tradition_guess=ComicTradition.AMERICAN,
            tradition_provenance=ProcedenciaTradicion.POR_DEFECTO)])
        select = self._select(html)
        assert select.count("selected") == 1 and 'value="" selected disabled' in select
        assert 'value="american" selected' not in select
        assert "La fuente no indica tradición: se sugiere Grapa americana por defecto." in html
        assert "no de la obra: elige tú" in html

    def test_la_procedencia_transformada_se_atribuye_a_los_datos_de_la_fuente(self):
        """GCD deduce la tradición de idioma/país: se dice que no viene como tradición de la ficha."""
        html = self._buscar([_resultado(
            source=MetadataSource.GCD, external_id="7", title="El Jabato", start_year=1958,
            site_url=None, tradition_guess=ComicTradition.TEBEO,
            tradition_provenance=ProcedenciaTradicion.TRANSFORMADA)])
        assert ("La fuente no usa esta tradición: a partir de sus datos "
                "se sugiere Tebeo español.") in html
        assert "no de la obra: elige tú" in html

    def test_origen_desconocido_no_se_presenta_como_dato_confirmado(self):
        """Sin procedencia no se inventa una explicación: se dice que no consta de dónde sale."""
        html = self._buscar([_resultado(
            source=MetadataSource.GCD, external_id="9", title="Sin ficha", site_url=None,
            tradition_guess=ComicTradition.TEBEO, tradition_provenance=None)])
        visible = html.lower()
        assert "La fuente sugiere Tebeo español, pero no consta de dónde sale." in html
        assert "no de la obra: elige tú" in html
        assert "dato confirmado" not in visible and "verificado" not in visible

    def test_ausencia_de_sugerencia_no_muestra_texto_de_pista(self):
        """El contrato representa la ausencia con `None`; no se usa `other` ni se inventa una pista."""
        html = self._buscar([_resultado(
            source=MetadataSource.GCD, external_id="10", title="Sin sugerencia", site_url=None,
            tradition_guess=None, tradition_provenance=None)])
        select = self._select(html)
        assert select.count("selected") == 1 and 'value="" selected disabled' in select
        assert "Sin sugerencia" in html
        assert "La fuente lo clasifica" not in html
        assert "La fuente no indica tradición" not in html
        assert "La fuente sugiere" not in html
        assert "no de la obra: elige tú" not in html


class TestLasRutasDeCreacionNoAceptanLosDatosDeLaSerie:
    """Ya no hay ninguna vía de creación en un clic: faltan el token firmado o la tradición y la petición es inválida (422),
    sin crear nada ni tocar la base."""

    def test_crear_con_el_cuerpo_antiguo_da_422_y_no_crea(self):
        sesion = FakeSession(existing=None)
        with use_fake_session(sesion) as client:
            r = client.post("/ui/descubrir/crear", data={
                "source": "comic_vine", "external_id": "1234", "title": "Batman", "tradition": "american",
                "start_year": "2011"})
        assert r.status_code == 422 and sesion.added == []

    def test_revisar_sin_tradicion_da_422(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post("/ui/descubrir/revisar", data={"candidata": "cualquiera"})
        assert r.status_code == 422

    def test_revisar_con_una_tradicion_inventada_da_422(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post("/ui/descubrir/revisar", data={"candidata": "x", "tradition": "inventada"})
        assert r.status_code == 422

    def test_un_token_de_alta_de_mas_de_su_limite_se_rechaza_sin_efectos(self):
        sesion = FakeSession()
        with use_fake_session(sesion) as client:
            r = client.post("/ui/descubrir/crear", data={"token": "a" * (MAX_TOKEN_ALTA + 1)})
        assert r.status_code == 422 and sesion.added == []


class TestPortada:
    """Bug real reportado ("¿puede tener algo así como el pantallazo de
    Sonarr?"): portadas de candidatos de búsqueda, antes de que exista
    una Series. El endpoint es un proxy — nunca hotlinking directo — con
    lista blanca de host por fuente para no convertirse en un proxy
    abierto de imágenes arbitrarias (SSRF)."""

    def test_host_no_permitido_para_la_fuente_da_400(self):
        client = TestClient(app)
        r = client.get("/ui/descubrir/portada", params={
            "url": "https://evil.example.com/steal.jpg",
            "source": "comic_vine",
        })
        assert r.status_code == 400

    def test_host_de_otra_fuente_no_vale_para_comic_vine(self):
        """anilist.co es un host válido para ANILIST, pero no para
        COMIC_VINE — la lista blanca es por fuente, no global."""
        client = TestClient(app)
        r = client.get("/ui/descubrir/portada", params={
            "url": "https://s4.anilist.co/file/x.jpg",
            "source": "comic_vine",
        })
        assert r.status_code == 400

    def test_host_permitido_sirve_la_imagen_cacheada(self, tmp_path, monkeypatch):
        from zascarr.config import get_settings
        get_settings.cache_clear()
        monkeypatch.setenv("COVERS_CACHE_PATH", str(tmp_path))

        async def fake_fetch(url, dest):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"\xff\xd8\xff")  # cabecera JPEG mínima
            return True

        with patch("zascarr.web.discovery.fetch_and_cache_cover", fake_fetch):
            client = TestClient(app)
            r = client.get("/ui/descubrir/portada", params={
                "url": "https://s4.anilist.co/file/x.jpg",
                "source": "anilist",
            })

        get_settings.cache_clear()
        assert r.status_code == 200
        assert r.content == b"\xff\xd8\xff"
