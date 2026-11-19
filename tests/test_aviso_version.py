"""Historia A #443: el aviso de versión nunca inventa una actualización."""
from __future__ import annotations

import asyncio
import shutil
import subprocess
from types import SimpleNamespace

import httpx
import pytest

from zascarr.services.aviso_version import AvisoVersion, comparar_main, consultar_main

LOCAL = "a" * 40
NUEVO = "b" * 40


def respuesta(
    status: str, *, base: str = LOCAL, merge: str = LOCAL,
    ahead: int = 1, behind: int = 0,
) -> dict:
    # Campos de la API real de GitHub Compare (NO existe head_commit).
    return {
        "status": status, "base_commit": {"sha": base},
        "merge_base_commit": {"sha": merge},
        "ahead_by": ahead, "behind_by": behind, "total_commits": ahead,
        "commits": [{"sha": NUEVO}] if ahead else [],
    }


@pytest.mark.parametrize(
    ("payload", "esperado"),
    [(respuesta("ahead"), "disponible"),
     (respuesta("identical", ahead=0), "actualizada"),
     (respuesta("diverged"), "desconocida"),
     (respuesta("behind"), "desconocida"),
     (respuesta("ahead", base=NUEVO), "desconocida"),
     (respuesta("ahead", merge=NUEVO), "desconocida"),
     (respuesta("ahead", ahead=0), "desconocida"),
     (respuesta("ahead", behind=1), "desconocida"),
     (respuesta("ahead", ahead=True), "desconocida"),
     ({"status": "identical", "base_commit": {"sha": LOCAL}}, "desconocida"),
     ({"status": "ahead"}, "desconocida")],
)
async def test_comparacion_solo_afirma_ascendencia_verificada(payload, esperado):
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            f"https://api.github.com/repos/juanajok/zascarr/compare/{LOCAL}...main?per_page=1"
        )
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await comparar_main(LOCAL, client) == esperado


@pytest.mark.parametrize("sha", ["", "corto", "a" * 39, "g" * 40, "a" * 40 + "/main"])
async def test_identidad_desconocida_no_consulta_la_red(sha):
    aviso = AvisoVersion(lambda: SimpleNamespace(build_sha=sha))
    assert aviso.estado() == "desconocida"
    assert aviso._task is None


async def test_consulta_en_segundo_plano_cache_y_fallo_sin_promesa(monkeypatch):
    from zascarr.services import aviso_version

    reloj = [100.]
    monkeypatch.setattr(aviso_version.time, "monotonic", lambda: reloj[0])
    llamadas = []
    async def consultar(sha):
        llamadas.append(sha)
        await asyncio.sleep(0)
        if len(llamadas) > 1:
            raise httpx.ConnectError("sin red")
        return "disponible"

    monkeypatch.setattr(aviso_version, "consultar_main", consultar)
    aviso = AvisoVersion(lambda: SimpleNamespace(build_sha=LOCAL))
    assert aviso.estado() == "comprobando"
    tarea = aviso._task
    assert aviso.estado() == "comprobando"
    assert aviso._task is tarea
    await tarea
    assert aviso.estado() == "disponible"
    assert llamadas == [LOCAL]
    reloj[0] += 901
    assert aviso.estado() == "comprobando"
    await aviso._task
    assert aviso.estado() == "desconocida"
    assert llamadas == [LOCAL, LOCAL]


async def test_respuesta_http_no_valida_es_desconocida():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(403, json=respuesta("ahead"))
    )) as client:
        assert await comparar_main(LOCAL, client) == "desconocida"


async def test_respuesta_excesiva_no_se_acepta():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, content=b"x" * 512_001)
    )) as client:
        assert await comparar_main(LOCAL, client) == "desconocida"


def test_estado_muestra_aviso_solo_lectura_sin_acciones(monkeypatch):
    from fastapi.testclient import TestClient

    from zascarr.database import get_db
    from zascarr.main import app
    from zascarr.web import estado

    monkeypatch.setattr(estado.aviso_version, "estado", lambda: "disponible")
    class FakeSession:
        async def execute(self, _):
            raise RuntimeError("sin BD")

        async def rollback(self):
            pass

    async def fake_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = fake_db
    try:
        with TestClient(app) as client:
            html = client.get("/estado").text
            bloque = html.split('<section id="version"', 1)[1].split("</section>", 1)[0]
            assert "Hay una versión nueva" in bloque
            assert "main" not in bloque
            assert "<form" not in bloque and "<button" not in bloque
            assert 'id="version-aviso" aria-live="polite"' in html
            assert 'setInterval(pollVersion, POLL_INTERVAL_MS)' in html
            monkeypatch.setattr(estado.aviso_version, "estado", lambda: "actualizada")
            fragmento = client.get("/ui/version/estado")
            assert fragmento.status_code == 200
            assert fragmento.headers["cache-control"] == "no-store"
            assert fragmento.headers["content-type"] == "application/json"
            assert fragmento.json() == {"estado": "actualizada"}
            monkeypatch.setattr(estado.aviso_version, "estado", lambda: "desconocida")
            assert client.get("/ui/version/estado").json() == {"estado": "desconocida"}
            assert "consulta con quien lo instaló" in client.get("/estado").text
            monkeypatch.setattr(estado.aviso_version, "estado", lambda: "comprobando")
            assert client.get("/ui/version/estado").json() == {"estado": "comprobando"}
            monkeypatch.setattr(estado.aviso_version, "estado", lambda: "disponible")
            assert client.get("/ui/version/estado").json() == {"estado": "disponible"}
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_dom_no_repite_anuncio_y_falla_cerrado_con_login_o_sin_red():
    """Contrato JS opcional con Node (solo pruebas; el producto no depende de Node)."""
    from pathlib import Path

    if not shutil.which("node"):
        pytest.skip("Node no está instalado")
    template = (Path(__file__).resolve().parents[1] /
                "src/zascarr/web/templates/estado.html").read_text()
    codigo = template.split("  async function pollVersion() {", 1)[1].split("  poll();", 1)[0]
    codigo = "async function pollVersion() {" + codigo
    prueba = r"""
const vm = require("node:vm");
const assert = require("node:assert/strict");
const codigo = require("node:fs").readFileSync(0, "utf8");
const url = "http://localhost/ui/version/estado";
let valor = "Comprobando si hay una versión nueva… Puedes seguir usando ZascArr.";
let cambios = 0;
let respuesta = {estado: "comprobando"};
let redirigida = false;
let sinRed = false;
const parrafo = {
  get textContent() { return valor; },
  set textContent(text) { valor = text; cambios++; },
  set innerHTML(_) { throw new Error("Nunca insertar HTML remoto"); },
};
const bloque = {
  querySelector(selector) {
    assert.equal(selector, "p[data-version-aviso]");
    return parrafo;
  },
  set textContent(_) { throw new Error("No borrar el párrafo de aria-live"); },
  set innerHTML(_) { throw new Error("No sustituir la estructura"); },
};
const ctx = {
  fetch: async (destino, opts) => {
    assert.equal(destino, url);
    assert.equal(opts.redirect, "manual");
    if (sinRed) throw new Error("sin red");
    return {
      ok: true, redirected: redirigida, url: redirigida ? "http://localhost/login" : url,
      headers: {get: () => redirigida ? "text/html" : "application/json; charset=utf-8"},
      json: async () => respuesta,
    };
  },
  URL,
  window: {location: {origin: "http://localhost"}},
  document: {getElementById: id => id === "version-aviso-texto" ? parrafo : bloque},
};
const pollVersion = vm.runInNewContext(codigo + "\npollVersion", ctx);
(async () => {
  await pollVersion(); assert.equal(cambios, 0);
  assert.equal(bloque.querySelector("p[data-version-aviso]"), parrafo);
  respuesta = {estado: "actualizada", html: '<img src=x onerror=alert(1)>'};
  await pollVersion(); assert.equal(cambios, 1);
  assert.equal(valor, "Tienes la versión más reciente de ZascArr.");
  await pollVersion(); assert.equal(cambios, 1);
  redirigida = true;
  respuesta = '<!doctype html><form onsubmit=alert(1)>Entrar</form>';
  await pollVersion(); assert.equal(cambios, 2);
  assert.match(valor, /No se puede comprobar/);
  assert.doesNotMatch(valor, /Entrar/);
  await pollVersion(); assert.equal(cambios, 2);
  redirigida = false;
  respuesta = {estado: "actualizada"};
  await pollVersion(); assert.equal(cambios, 3);
  sinRed = true;
  await pollVersion(); assert.equal(cambios, 4);
  assert.match(valor, /No se puede comprobar/);
  await pollVersion(); assert.equal(cambios, 4);
  sinRed = false;
  respuesta = {estado: '<img src=x onerror=alert(1)>', attrs: {onclick: "alert(1)"}};
  await pollVersion(); assert.equal(cambios, 4);
  respuesta = '<p data-version-aviso onclick=alert(1)><img src=x onerror=alert(1)></p>';
  await pollVersion(); assert.equal(cambios, 4);
  assert.doesNotMatch(valor, /<img|onclick|onerror/);
  assert.equal(bloque.querySelector("p[data-version-aviso]"), parrafo);
})().catch(err => { console.error(err); process.exitCode = 1; });
"""
    resultado = subprocess.run(
        ["node", "-e", prueba], input=codigo, text=True, capture_output=True, check=False,
    )
    assert resultado.returncode == 0, resultado.stderr


async def test_timeout_global_cubre_stream_que_no_deja_de_enviar(monkeypatch):
    from zascarr.services import aviso_version

    class Lento(httpx.AsyncByteStream):
        async def __aiter__(self):
            while True:
                await asyncio.sleep(0.015)
                yield b" "

    real = httpx.AsyncClient
    def client_factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        assert kwargs["timeout"].connect == 1.5
        return real(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=Lento())
        ), **kwargs)

    monkeypatch.setattr(aviso_version.httpx, "AsyncClient", client_factory)
    monkeypatch.setattr(aviso_version, "_PLAZO_TOTAL", 0.06)
    assert await asyncio.wait_for(consultar_main(LOCAL), timeout=0.5) == "desconocida"


async def test_redireccion_a_otro_host_no_se_sigue(monkeypatch):
    from zascarr.services import aviso_version

    llamadas = []
    def handler(request):
        llamadas.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/privado"})

    real = httpx.AsyncClient
    def client_factory(**kwargs):
        return real(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(aviso_version.httpx, "AsyncClient", client_factory)
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    assert await consultar_main(LOCAL) == "desconocida"
    assert llamadas == [
        f"https://api.github.com/repos/juanajok/zascarr/compare/{LOCAL}...main?per_page=1"
    ]


def test_sha_de_imagen_conectado_a_config_y_compose(monkeypatch):
    from pathlib import Path

    from zascarr.config import Settings

    repo = Path(__file__).resolve().parents[1]
    dockerfile = (repo / "Dockerfile").read_text()
    assert "ARG ZASCARR_BUILD_SHA=" in dockerfile
    assert "ENV BUILD_SHA=${ZASCARR_BUILD_SHA}" in dockerfile
    monkeypatch.setenv("BUILD_SHA", LOCAL)
    assert Settings().build_sha == LOCAL
    compose = (repo / "docker-compose.yml").read_text()
    assert "ZASCARR_BUILD_SHA: ${ZASCARR_BUILD_SHA:-}" in compose
    for script in ("bootstrap.sh", "scripts/update.sh"):
        texto = (repo / script).read_text()
        assert 'ZASCARR_BUILD_SHA="${BUILD_SHA}"' in texto
