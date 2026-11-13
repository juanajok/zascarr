# ruff: noqa: E501
"""PR-2 (#134): snapshot servido, Estado con la cortesía, Ajustes y Descubrir (§6, AC-09/14/18).

Sin red ni BD: el limitador es el global del proceso (se reinicia entre pruebas) y las rutas se
prueban con FakeSession, como el resto de la web.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.auth import hash_password
from zascarr.utils import cortesia


class Mundo:
    comicvine_enabled = True
    anilist_enabled = False
    tebeosfera_enabled = True
    gcd_enabled = False
    forum_enabled = True
    forum_url = ""
    comicvine_rate_limit = 1.0
    anilist_rate_limit = 1.5
    tebeosfera_rate_limit = 2.5
    gcd_rate_limit = 2.0
    forum_rate_limit = 2.0


@pytest.fixture
def entorno(monkeypatch):
    cortesia.reiniciar_para_pruebas()
    lim = cortesia.cortesia_de_proceso()
    lim.bloquear("comicvine", "https://comicvine.gamespot.com:443", 7.0, motivo="429")
    lim.registrar_resultado("comicvine", "429", intento=2, espera_s=2.0)
    lim._estado_fuente("tebeosfera").ultima = lim._reloj()   # deja «En espera» visible
    monkeypatch.setattr("zascarr.services.cortesia_estado.get_settings", lambda: Mundo())
    monkeypatch.setattr("zascarr.web.estado.get_settings", lambda: Mundo())
    yield lim
    cortesia.reiniciar_para_pruebas()


class SesionRota:
    async def execute(self, _statement):
        raise RuntimeError("sin BD")
    async def rollback(self):
        return None


@pytest.fixture
def cliente():
    async def _get_db():
        yield SesionRota()
    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestEndpoint:
    def test_devuelve_el_snapshot_con_no_store_y_sin_hosts_fuera_de_la_allowlist(self, entorno, cliente):
        r = cliente.get("/api/estado/cortesia")
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-store"
        datos = r.json()
        assert datos["coordinacion"] == "proceso"
        # SCR2: las dos wikis de Fandom son fuentes declaradas y el snapshot las lista siempre
        # (apagadas por defecto), igual que el resto de la allowlist.
        assert {f["fuente"] for f in datos["fuentes"]} == {
            "comicvine", "anilist", "tebeosfera", "gcd", "metron", "open_library",
            "fandom_dc", "fandom_marvel", "foro", "portada"}
        assert all("://" not in h["host"] for h in datos["hosts"])
        assert all(h["host"] in ("comicvine.gamespot.com", "cbsistatic.com") for h in datos["hosts"])
        texto = json.dumps(datos)
        for prohibido in ("api_key", "Authorization", "Cookie", "?q=", "https://"):
            assert prohibido not in texto, prohibido

    def test_exige_sesion_como_el_resto_de_la_api(self, monkeypatch):
        real = get_settings()
        settings = real.model_copy(update={
            "auth_mode": "password",
            "auth_password_hash": hash_password("secreta"),
            "secret_key": "s" * 32,
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        c = TestClient(app)
        assert c.get("/api/estado/cortesia").status_code == 401
        assert c.get("/api/estado/cortesia", auth=("cualquiera", "secreta")).status_code == 200


class TestEstadoHtml:
    def test_pinta_la_seccion_con_los_textos_y_estados_de_la_spec(self, entorno, cliente):
        r = cliente.get("/estado")
        assert r.status_code == 200
        assert "Esperas al pedir datos" in r.text
        assert "ZascArr espera un poco entre consulta y consulta" in r.text
        assert "cada una espera por su cuenta" in r.text
        assert "Bloqueada temporalmente (~7 s)" in r.text
        assert "En espera" in r.text
        assert "Apagada" in r.text
        assert "Sin configurar" in r.text
        assert "No se consulta ni se reintenta." in r.text
        assert "Algunas webs han pedido que no les preguntemos" in r.text
        assert "puede que sigan sin responder" in r.text
        assert "Nos pidió esperar hace" in r.text
        # «Apagada» es gris (neutral), nunca un fallo en rojo.
        assert "cortesia-estado-neutral" in r.text
        # #134: la tabla es detalle y va plegada; el texto de arriba no es jerga.
        seccion = r.text[r.text.index('id="cortesia"'):]
        seccion = seccion[:seccion.index("</section>")]
        assert "Cortesía con las fuentes" not in seccion
        assert "https://" not in seccion and "api_key" not in seccion
        assert "<details" in seccion
        assert "<summary>Ver el detalle por web</summary>" in seccion
        visible = seccion[:seccion.index("<details")]
        for jerga in ("Cortesía", "peticiones", "procesos", "instalaciones", "coordinación"):
            assert jerga not in visible, jerga
        # La tabla está DENTRO del desplegable, con caption y cabeceras de columna.
        assert seccion.index("<details") < seccion.index("<table") < seccion.index("</details>")
        assert '<caption class="sr">' in seccion
        assert 'scope="col"' in seccion and 'scope="row"' in seccion
        for columna in ("Web", "Estado", "Siguiente consulta", "Esperando turno", "Últimos intentos"):
            assert columna in seccion

    def test_no_promete_recuperacion_ni_fecha(self, entorno, cliente):
        r = cliente.get("/estado")
        seccion = r.text[r.text.index('id="cortesia"'):]
        seccion = seccion[:seccion.index("</section>")]
        for prohibido in ("se recuperará", "volverá a estar disponible", "mañana", "fecha"):
            assert prohibido not in seccion


class TestAjustes:
    def _ajustes(self):
        return SimpleNamespace(
            comicvine_api_key="", comicvine_enabled=False, anilist_enabled=False,
            tebeosfera_enabled=False, gcd_enabled=False, fuentes_heredadas=False,
            prowlarr_url="", prowlarr_api_key="", prowlarr_enabled=False,
            transmission_url="", transmission_username="", transmission_password="",
            transmission_enabled=False, amule_url="", amule_password="", amule_enabled=False,
            auth_mode="none", auth_username="", auth_password_hash="", base_url="",
            webhook_enabled=False, webhook_type="generic", webhook_url="", webhook_token="",
            webhook_chat_id="", webhook_incluir_nombres=False,
            comicvine_rate_limit=1.0, anilist_rate_limit=1.5, tebeosfera_rate_limit=2.5,
            gcd_rate_limit=2.0, forum_rate_limit=2.0, forum_enabled=False, forum_url="",
        )

    def test_politica_dinamica_y_coordinacion(self, monkeypatch):
        monkeypatch.setattr("zascarr.web.ajustes.get_settings", lambda: self._ajustes())
        r = TestClient(app).get("/ui/ajustes")
        assert ("Cortesía: Comic Vine 1 s y 3 intentos; AniList 1,5 s y 3; Tebeosfera 2,5 s y 1; "
                "GCD 2 s y 2; Metron 3 s y 2; Open Library 1 s y 2.") in r.text
        assert "cada una espera por su cuenta" in r.text
        assert "Apagada: No se consulta ni se reintenta." in r.text

    def test_la_espera_de_la_prueba_es_un_aviso_neutro(self):
        mensaje = ("No se ha probado: hay que esperar ~12 s por cortesía. "
                   "Inténtalo de nuevo en un momento.")
        with patch("zascarr.web.ajustes._test_comic_vine", AsyncMock(return_value=(False, mensaje))):
            r = TestClient(app).post("/ui/ajustes/probar/comic-vine",
                                     data={"comicvine_api_key": "clave"})
        assert r.status_code == 200
        assert "ajustes-aviso" in r.text
        assert "ajustes-error" not in r.text
        assert "hay que esperar ~12 s por cortesía" in r.text
