"""#877: «Probar conexión» del foro en Ajustes (sin red ni persistencia)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.forum_scraper import (
    ForumFloodControl,
    OrigenNoPermitidoError,
)
from zascarr.utils.cortesia import CortesiaEnEspera
from zascarr.utils.robots import AccesoProhibidoPorRobots
from zascarr.web.ajustes import _test_foro

URL = "https://foro.example/forum"


def _cliente():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


class _ScraperFalso:
    llamadas: list[tuple[str, dict]] = []
    resultado = True
    error: Exception | None = None

    def __init__(self, url, **kw):
        type(self).llamadas.append((url, kw))

    async def login(self, usuario, password):
        if type(self).error is not None:
            raise type(self).error
        return type(self).resultado


@pytest.fixture
def scraper(monkeypatch):
    _ScraperFalso.llamadas = []
    _ScraperFalso.resultado = True
    _ScraperFalso.error = None
    monkeypatch.setattr("zascarr.web.ajustes.ForumScraper", _ScraperFalso)
    return _ScraperFalso


async def test_url_invalida_no_instancia_el_scraper(monkeypatch):
    def _no_debe_instanciarse(*_a, **_k):
        raise AssertionError("no debe haber red")

    monkeypatch.setattr("zascarr.web.ajustes.ForumScraper", _no_debe_instanciarse)
    ok, mensaje = await _test_foro("ftp://foro.example/foro", "u", "p")
    assert not ok and "dirección del foro no es válida" in mensaje


async def test_faltan_usuario_o_contrasena_sin_red(monkeypatch):
    monkeypatch.setattr("zascarr.web.ajustes.ForumScraper", _ScraperFalso)
    assert await _test_foro(URL, "", "p") == (False, "Falta el usuario o la contraseña.")
    assert await _test_foro(URL, "u", "") == (False, "Falta el usuario o la contraseña.")


async def test_login_ok_usa_permitir_apagada_y_solo_login(scraper):
    ok, mensaje = await _test_foro(URL + "/", " lector ", "clave")
    assert ok and "Conexión correcta" in mensaje
    assert scraper.llamadas == [(URL, {"permitir_apagada": True})]


async def test_credenciales_rechazadas(scraper):
    scraper.resultado = False
    ok, mensaje = await _test_foro(URL, "u", "p")
    assert not ok and "No se pudo iniciar sesión" in mensaje
    assert "usuario y contraseña" in mensaje


@pytest.mark.parametrize(("error", "texto"), [
    (CortesiaEnEspera("foro", "foro.example:443", 12.0), "esperar ~12 s por cortesía"),
    (ForumFloodControl("foro.example:443", 42.0), "pidió esperar ~42 s"),
    (AccesoProhibidoPorRobots("foro", "foro.example"), "robots.txt"),
    (OrigenNoPermitidoError("otro_origen"), "dirección del foro no es válida"),
    (httpx.ConnectError("sin red"), "No se pudo conectar con el foro"),
    (RuntimeError("boom"), "No se pudo comprobar la conexión"),
])
async def test_los_errores_se_dicen_en_llano(scraper, error, texto):
    scraper.error = error
    ok, mensaje = await _test_foro(URL, "u", "p")
    assert not ok and texto in mensaje


async def test_scraper_propaga_permitir_apagada_a_la_envoltura(monkeypatch):
    from zascarr.services import forum_scraper as modulo

    capturado: dict = {}

    async def _pedir(_cliente, _metodo, _url, **kw):
        capturado.update(kw)
        return httpx.Response(200, content=b"")

    monkeypatch.setattr(modulo, "pedir_con_cortesia", _pedir)
    async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _r: httpx.Response(200))) as cliente:
        scraper = modulo.ForumScraper("https://foro.example", rate_limit=0,
                                      permitir_apagada=True)
        await scraper._pedir("https://foro.example/index.php", client=cliente)
    assert scraper._permitir_apagada is True
    assert capturado["permitir_apagada"] is True


def test_la_plantilla_tiene_boton_target_e_indicador():
    plantilla = (Path(__file__).resolve().parents[1]
                 / "src" / "zascarr" / "web" / "templates" / "ajustes.html")
    texto = plantilla.read_text(encoding="utf-8")
    assert 'hx-post="/ui/ajustes/probar/foro"' in texto
    assert 'hx-target="#prueba-foro"' in texto
    assert 'id="prueba-foro" aria-live="polite"' in texto
    assert 'id="prueba-foro-espera"' in texto and "Probando…" in texto
    assert "Solo inicia sesión" in texto


def test_la_ruta_ok_pinta_el_resultado(monkeypatch):
    monkeypatch.setattr("zascarr.web.ajustes._test_foro",
                        AsyncMock(return_value=(True, "Conexión correcta: el foro aceptó el usuario.")))
    c = _cliente()
    try:
        r = c.post("/ui/ajustes/probar/foro", data={
            "forum_url": URL, "forum_username": "lector", "forum_password": "CLAVE_SECRETA"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "✓" in r.text
    assert "Conexión correcta" in r.text and "CLAVE_SECRETA" not in r.text


def test_la_ruta_de_error_pinta_una_equis(monkeypatch):
    monkeypatch.setattr("zascarr.web.ajustes._test_foro",
                        AsyncMock(return_value=(False, "No se pudo iniciar sesión.")))
    c = _cliente()
    try:
        r = c.post("/ui/ajustes/probar/foro", data={
            "forum_url": URL, "forum_username": "u", "forum_password": "CLAVE"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "✗" in r.text and "CLAVE" not in r.text


def test_la_ruta_de_espera_usa_aviso_neutro(monkeypatch):
    monkeypatch.setattr("zascarr.web.ajustes._test_foro", AsyncMock(
        return_value=(False, "No se ha probado: hay que esperar ~12 s por cortesía.")))
    c = _cliente()
    try:
        r = c.post("/ui/ajustes/probar/foro", data={
            "forum_url": URL, "forum_username": "u", "forum_password": "p"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "ajustes-aviso" in r.text
    assert "No se ha probado" in r.text


def test_contrasena_vacia_usa_la_guardada(monkeypatch):
    guardar = AsyncMock()
    monkeypatch.setattr("zascarr.web.ajustes._secreto_o_guardado",
                        lambda _valor, campo: "guardada" if campo == "forum_password" else "")
    monkeypatch.setattr("zascarr.web.ajustes._test_foro", guardar)
    guardar.return_value = (True, "ok")
    c = _cliente()
    try:
        r = c.post("/ui/ajustes/probar/foro", data={
            "forum_url": URL, "forum_username": "u", "forum_password": ""})
    finally:
        _cerrar()
    assert r.status_code == 200
    args = guardar.await_args.args
    assert args[0] == URL and args[1] == "u" and args[2] == "guardada"
