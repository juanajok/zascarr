"""#1229 (propuesta 11 de #1227, dictamen de SecOps): cabeceras de seguridad en toda respuesta."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from zascarr.database import get_db
from zascarr.main import app
from zascarr.middleware_cabeceras import (
    CABECERAS_DE_SEGURIDAD,
    CabecerasDeSeguridadMiddleware,
    completar_cabeceras,
)
from zascarr.web.errores import manejar_inesperado

ESPERADAS = {
    "x-frame-options": "DENY",
    "content-security-policy":
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
    "x-robots-tag": "noindex",
}


def _valores(cabeceras) -> dict[str, list[str]]:
    salida: dict[str, list[str]] = {}
    for nombre, valor in cabeceras:
        n = nombre.decode() if isinstance(nombre, bytes) else nombre
        v = valor.decode() if isinstance(valor, bytes) else valor
        salida.setdefault(n.lower(), []).append(v)
    return salida


# ── el middleware, aislado ────────────────────────────────────────────────────────────────


async def _ejecutar(app_interna, scope=None):
    enviados = []

    async def send(mensaje):
        enviados.append(mensaje)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    await CabecerasDeSeguridadMiddleware(app_interna)(scope or {"type": "http"}, receive, send)
    return enviados


def _app_que_responde(cabeceras, cuerpos=(b"hola",)):
    async def app_interna(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": list(cabeceras)})
        for i, c in enumerate(cuerpos):
            await send({"type": "http.response.body", "body": c,
                        "more_body": i < len(cuerpos) - 1})
    return app_interna


@pytest.mark.asyncio
async def test_anade_las_seis_cabeceras_exactas():
    enviados = await _ejecutar(_app_que_responde([(b"content-type", b"text/plain")]))
    valores = _valores(enviados[0]["headers"])
    for nombre, esperado in ESPERADAS.items():
        assert valores[nombre] == [esperado], nombre
    assert valores["content-type"] == ["text/plain"]


@pytest.mark.asyncio
async def test_no_pisa_ni_duplica_lo_que_la_ruta_ya_puso_sin_distinguir_mayusculas():
    enviados = await _ejecutar(_app_que_responde([
        (b"X-Content-Type-Options", b"nosniff"), (b"X-Robots-Tag", b"none"),
        (b"Cache-Control", b"private, max-age=86400")]))
    valores = _valores(enviados[0]["headers"])
    assert valores["x-content-type-options"] == ["nosniff"]
    assert valores["x-robots-tag"] == ["none"]           # el de la ruta manda
    assert valores["cache-control"] == ["private, max-age=86400"]  # no se toca
    assert valores["x-frame-options"] == ["DENY"]


@pytest.mark.asyncio
async def test_no_bufferiza_el_cuerpo_en_streaming():
    """Cada trozo llega en su mensaje, en orden, y solo `http.response.start` se modifica."""
    enviados = await _ejecutar(_app_que_responde([], cuerpos=(b"a", b"b", b"c")))
    assert [m["type"] for m in enviados] == ["http.response.start"] + ["http.response.body"] * 3
    assert [m["body"] for m in enviados[1:]] == [b"a", b"b", b"c"]
    assert [m["more_body"] for m in enviados[1:]] == [True, True, False]


@pytest.mark.asyncio
async def test_una_respuesta_sin_cabeceras_tambien_las_recibe():
    async def sin_cabeceras(scope, receive, send):
        await send({"type": "http.response.start", "status": 204})
        await send({"type": "http.response.body", "body": b""})

    enviados = await _ejecutar(sin_cabeceras)
    assert set(_valores(enviados[0]["headers"])) == set(ESPERADAS)


@pytest.mark.asyncio
@pytest.mark.parametrize("tipo", ["lifespan", "websocket"])
async def test_lo_que_no_es_http_pasa_sin_tocar(tipo):
    llamado = []

    async def app_interna(scope, receive, send):
        llamado.append(scope["type"])
        await send({"type": "websocket.accept"})

    enviados = await _ejecutar(app_interna, {"type": tipo})
    assert llamado == [tipo] and enviados == [{"type": "websocket.accept"}]


def test_la_csp_no_lleva_script_ni_style_src():
    """Regresión: `hx-on` evalúa con `Function` y hay `<script>` y `style=` en las plantillas;
    una CSP con `script-src`/`style-src` rompería la interfaz. Es una historia aparte tras medir."""
    csp = ESPERADAS["content-security-policy"]
    assert "script-src" not in csp and "style-src" not in csp and "default-src" not in csp
    assert dict(CABECERAS_DE_SEGURIDAD)[b"content-security-policy"].decode() == csp


def test_completar_cabeceras_no_cambia_la_lista_de_entrada():
    original = [(b"a", b"1")]
    assert len(completar_cabeceras(original)) == 1 + len(ESPERADAS)
    assert original == [(b"a", b"1")]


# ── la aplicación real, por tipo de respuesta ─────────────────────────────────────────────


class _Sesion:
    async def execute(self, *_a, **_k):
        return None


@pytest.fixture
def cliente():
    async def _get_db():
        yield _Sesion()

    app.dependency_overrides[get_db] = _get_db
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _verifica(r):
    valores = _valores(r.headers.raw)
    for nombre, esperado in ESPERADAS.items():
        assert valores.get(nombre) == [esperado], (nombre, valores.get(nombre), r.status_code)


@pytest.mark.parametrize("ruta, estado", [
    ("/legal", 200),                      # HTML
    ("/ui/ajustes", 200),                 # HTML de la UI (/ui/*)
    ("/estado", 200),                     # HTML de la UI
    ("/api/health", 200),                 # JSON
    ("/static/web.css", 200),             # estático
    ("/no-existe-nada", 404),             # 404
])
def test_cada_tipo_de_respuesta_lleva_las_seis_cabeceras(cliente, ruta, estado):
    r = cliente.get(ruta)
    assert r.status_code == estado, r.status_code
    _verifica(r)


def test_opds_lleva_las_seis_cabeceras(cliente):
    r = cliente.get("/opds")
    _verifica(r)


def test_una_redireccion_las_lleva(cliente):
    r = cliente.get("/", follow_redirects=False)
    assert r.status_code == 307
    _verifica(r)


def test_el_403_de_origen_las_lleva(cliente):
    r = cliente.post("/ui/legal/accept", data={"acepto_1": "1"},
                     headers={"Origin": "http://evil.example", "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    _verifica(r)


def test_el_413_del_limite_de_cuerpo_las_lleva(cliente):
    r = cliente.post("/ui/legal/accept", content=b"x" * 400_000,
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413
    _verifica(r)


def test_el_500_inesperado_las_lleva_aunque_lo_envie_servererrormiddleware():
    peticion = Request({"type": "http", "method": "GET", "path": "/x", "headers": [],
                        "query_string": b""})
    import asyncio
    respuesta = asyncio.run(manejar_inesperado(peticion, RuntimeError("boom")))
    assert respuesta.status_code == 500
    _verifica(respuesta)


def test_una_cabecera_que_ya_pone_la_ruta_no_se_duplica_en_la_app_real(cliente):
    r = cliente.get("/api/health")
    assert len(r.headers.get_list("x-content-type-options")) == 1
    assert len(r.headers.get_list("x-frame-options")) == 1


# ── nada propio que DENY / form-action rompan ─────────────────────────────────────────────


RAIZ = Path(__file__).resolve().parent.parent / "src" / "zascarr"


def test_no_hay_iframe_object_ni_embed_propios():
    """`X-Frame-Options: DENY` y `object-src 'none'` romperían una incrustación propia."""
    patron = re.compile(r"<(iframe|object|embed)\b", re.IGNORECASE)
    ficheros = [*(RAIZ / "web" / "templates").rglob("*.html"), *(RAIZ / "static").glob("*.js")]
    assert ficheros
    assert [str(f) for f in ficheros if patron.search(f.read_text(encoding="utf-8"))] == []


def test_ningun_formulario_envia_a_otro_origen():
    """`form-action 'self'` bloquearía un `<form action="https://…">` o un `hx-post` externo."""
    externo = re.compile(r"""(<form[^>]*\baction=|hx-(?:get|post|put|patch|delete)=)["']https?://""",
                         re.IGNORECASE)
    malos = [str(f) for f in (RAIZ / "web" / "templates").rglob("*.html")
             if externo.search(f.read_text(encoding="utf-8"))]
    assert malos == []
