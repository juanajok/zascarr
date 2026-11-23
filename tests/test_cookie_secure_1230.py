# ruff: noqa: F401, F811
"""#1230 (propuesta 12 de #1227, dictamen de SecOps, opción A del PO): cookie `Secure`.

`Secure` solo si `base_url` empieza por `https://`; vacío o `http://` → como siempre. Una sola
función de atributos para poner Y borrar la cookie.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tests.test_auth_limites import restaurar_settings, retraso_rapido, settings_password
from tests.test_contrasena_actual import ACTUAL, NUEVA, _cliente, _post, con_contrasena
from zascarr.config import get_settings
from zascarr.main import app
from zascarr.services.auth import COOKIE_NAME, atributos_cookie_sesion, crear_cookie_sesion


def _cookie(respuesta) -> str:
    """El `Set-Cookie` de la cookie de sesión, en minúsculas."""
    todas = respuesta.headers.get_list("set-cookie")
    propias = [c for c in todas if c.startswith(f"{COOKIE_NAME}=")]
    assert len(propias) == 1, todas
    return propias[0].lower()


# ── la función ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("base_url, secure", [
    ("https://zascarr.example", True),
    ("HTTPS://ZASCARR.EXAMPLE", True),
    ("  https://zascarr.example/  ", True),
    ("", False),
    (None, False),
    ("http://192.168.1.50:8000", False),
    ("ftp://zascarr.example", False),
    ("zascarr.example", False),
    ("httpsx://zascarr.example", False),
])
def test_secure_solo_con_base_url_https(base_url, secure):
    atributos = atributos_cookie_sesion(SimpleNamespace(base_url=base_url))
    assert atributos == {"httponly": True, "samesite": "lax", "secure": secure}


def test_sin_el_campo_base_url_no_revienta_y_no_es_secure():
    assert atributos_cookie_sesion(SimpleNamespace())["secure"] is False


# ── login, logout y cambio de credenciales ────────────────────────────────────────────────


def _login(settings_password, retraso_rapido, base_url):
    settings_password.base_url = base_url
    cliente = TestClient(app, follow_redirects=False)
    r = cliente.post("/login", data={"password": "secreta", "next": "/ui/"})
    assert r.status_code == 303
    return r


def test_login_con_base_url_https_pone_secure_httponly_y_samesite(
        settings_password, retraso_rapido):
    c = _cookie(_login(settings_password, retraso_rapido, "https://zascarr.example"))
    assert "secure" in c.split("; ") and "httponly" in c and "samesite=lax" in c


@pytest.mark.parametrize("base_url", ["", "http://192.168.1.50:8000"])
def test_login_sin_https_sigue_sin_secure(settings_password, retraso_rapido, base_url):
    c = _cookie(_login(settings_password, retraso_rapido, base_url))
    assert "secure" not in c.split("; ") and "httponly" in c and "samesite=lax" in c


@pytest.mark.parametrize("base_url, secure", [("https://zascarr.example", True), ("", False)])
def test_logout_borra_con_los_mismos_atributos_que_puso(settings_password, base_url, secure):
    settings_password.base_url = base_url
    cliente = TestClient(app, follow_redirects=False)
    cliente.cookies.set(COOKIE_NAME, crear_cookie_sesion(
        settings_password.secret_key, settings_password.auth_session_version))
    r = cliente.post("/logout")
    assert r.status_code == 303 and r.headers["location"] == "/login"
    c = _cookie(r)
    assert "max-age=0" in c
    assert ("secure" in c.split("; ")) is secure
    assert "httponly" in c and "samesite=lax" in c


@pytest.mark.parametrize("base_url, secure", [("https://zascarr.example", True), ("", False)])
def test_cambio_de_credenciales_en_ajustes_pone_la_cookie_con_los_mismos_atributos(
        con_contrasena, base_url, secure):
    r = _post(_cliente(), auth_password=NUEVA, auth_password_repetida=NUEVA,
              auth_password_actual=ACTUAL, base_url=base_url)
    assert r.status_code == 200
    c = _cookie(r)
    assert ("secure" in c.split("; ")) is secure
    assert "httponly" in c and "samesite=lax" in c


# ── nadie fija los atributos por su cuenta ────────────────────────────────────────────────


def _llamadas(codigo: str, metodo: str):
    """Texto de cada llamada `.metodo(…)` (con el paréntesis de cierre que le corresponde)."""
    for m in re.finditer(rf"\.{metodo}\(", codigo):
        profundidad, i = 1, m.end()
        while i < len(codigo) and profundidad:
            profundidad += {"(": 1, ")": -1}.get(codigo[i], 0)
            i += 1
        yield codigo[m.start():i]


def test_ninguna_ruta_llama_a_set_cookie_o_delete_cookie_con_atributos_propios():
    raiz = Path(__file__).resolve().parent.parent / "src" / "zascarr"
    encontradas = []
    for fichero in raiz.rglob("*.py"):
        codigo = fichero.read_text(encoding="utf-8")
        for metodo in ("set_cookie", "delete_cookie"):
            encontradas += [(fichero.name, metodo, c) for c in _llamadas(codigo, metodo)]
    assert {(f, m) for f, m, _ in encontradas} >= {
        ("auth.py", "set_cookie"), ("auth.py", "delete_cookie"), ("ajustes.py", "set_cookie")}
    sin_funcion = [(f, m) for f, m, c in encontradas if "atributos_cookie_sesion(" not in c]
    assert sin_funcion == [], sin_funcion
