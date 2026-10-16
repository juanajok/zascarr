#!/usr/bin/env python3
# ruff: noqa: E501
"""U14 (#201), criterio 2, con un lector de pantalla real: Orca + Google Chrome con ventana, fuentes SIMULADAS.

Herramienta de desarrollo, FUERA del paquete. Reutiliza `Cdp` y `frases` de `../ui-u11/orca_u11.py` (misma configuración de Orca
aislada en una base de dconf propia que se borra al terminar). La página de Descubrir y los fragmentos de `/buscar` los genera la
ruta REAL (`fragmentos.py`) y se sirven con `Fetch.fulfillRequest`: NO se consulta ninguna fuente externa. Lo que se acredita es
qué dice Orca cuando la región viva cambia de contenido; no tiempos ni contenido de las fuentes.

    python3 docs/design/ui-u14/orca_u14.py http://127.0.0.1:18000 fragmentos.json docs/design/ui-u14

Escribe `orca-habla.json`: por cada búsqueda, la consulta, el estado de la región y las frases que Orca mandó al sintetizador.
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

_spec = importlib.util.spec_from_file_location("orca_u11", Path(__file__).resolve().parents[1] / "ui-u11" / "orca_u11.py")
u11 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(u11)

PUERTO = 9335
#: (fragmento, consulta, qué debe haber dicho Orca). Cuatro búsquedas SEGUIDAS en la misma página; la cuarta repite el
#: fragmento de la primera para ver que una segunda búsqueda con el mismo texto también se anuncia.
BUSQUEDAS = [
    ("con_resultados_y_una_caida", "Mortadelo", "2 resultados. No respondió AniList"),
    ("sin_coincidencias", "Zzzz", "Ningún resultado"),
    ("todas_fallan", "Flash", "No respondió ninguna fuente"),
    ("con_resultados_y_una_caida", "Mortadelo y", "2 resultados. No respondió AniList"),
]


class CdpAsincrono:
    """CDP con un lector propio: las respuestas se reparten por `id` y los eventos de Fetch van a una cola, sin perder ninguno."""

    def __init__(self, ws) -> None:
        self.ws, self._id, self._futuros = ws, 0, {}
        self.fetch: asyncio.Queue = asyncio.Queue()
        self._lector = asyncio.create_task(self._leer())

    async def _leer(self) -> None:
        try:
            async for crudo in self.ws:
                msg = json.loads(crudo)
                if msg.get("method") == "Fetch.requestPaused":
                    await self.fetch.put(msg["params"])
                elif "id" in msg and msg["id"] in self._futuros:
                    self._futuros.pop(msg["id"]).set_result(msg)
        except websockets.ConnectionClosed:
            return

    async def __call__(self, metodo: str, **params):
        self._id += 1
        fut = asyncio.get_running_loop().create_future()
        self._futuros[self._id] = fut
        await self.ws.send(json.dumps({"id": self._id, "method": metodo, "params": params}))
        msg = await fut
        if "error" in msg:
            raise RuntimeError(f"{metodo}: {msg['error']}")
        return msg.get("result", {})

    async def js(self, expr: str):
        r = await self("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


async def main(base: str, fragmentos: Path, salida: Path) -> None:
    datos = json.loads(fragmentos.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="orca-u14-"))
    registro = tmp / "orca-debug.out"
    base_dconf = "orcau14" + re.sub(r"[^A-Za-z0-9]", "", tmp.name)
    perfil = tmp / "dconf-profile"
    perfil.write_text(f"user-db:{base_dconf}\n", encoding="utf-8")
    entorno = {**os.environ, "DCONF_PROFILE": str(perfil)}
    for clave in ("say-all-on-load", "page-summary-on-load"):
        subprocess.run(["dconf", "write", f"/org/gnome/orca/default/document/{clave}", "false"], env=entorno, check=True)
    orca = subprocess.Popen(["orca", "--debug-file", str(registro)], env=entorno,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(4)
    chrome = subprocess.Popen(
        ["google-chrome", f"--remote-debugging-port={PUERTO}", f"--user-data-dir={tmp / 'perfil'}",
         "--force-renderer-accessibility", "--no-first-run", "--no-default-browser-check",
         "--disable-extensions", "--new-window", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    resultado: dict = {"orca": subprocess.run(["orca", "--version"], capture_output=True, text=True).stdout.strip(), "busquedas": []}
    try:
        for _ in range(50):
            try:
                pestanas = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/json"))
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.3)
        destino = next(p for p in pestanas if p["type"] == "page")
        async with websockets.connect(destino["webSocketDebuggerUrl"], max_size=2 ** 26) as ws:
            cdp = CdpAsincrono(ws)
            resultado["chrome"] = (await cdp("Browser.getVersion"))["product"]
            await cdp("Page.enable")
            await cdp("Fetch.enable", patterns=[{"urlPattern": "*/ui/descubrir", "requestStage": "Request"},
                                                {"urlPattern": "*/ui/descubrir/buscar*", "requestStage": "Request"}])
            cab = [{"name": "Content-Type", "value": "text/html; charset=utf-8"}, {"name": "Cache-Control", "value": "no-store"}]
            n = {"i": 0}
            asyncio.create_task(_servir(cdp, cdp.fetch, datos, n, cab))
            await cdp("Page.navigate", url=base + "/ui/descubrir")
            await asyncio.sleep(5)
            await cdp("Page.bringToFront")
            await cdp.js("document.querySelector('input.series-search').focus()")
            await asyncio.sleep(3)                     # Orca dice el campo; se descarta, no es lo que se mide
            await cdp.js("""(() => { const r = document.querySelector('#descubrir-estado'); window.__reg = r; window.__mut = [];
              new MutationObserver(m => m.forEach(x => window.__mut.push(x.type))).observe(r, {childList: true, subtree: true, characterData: true, attributes: true}); })()""")
            for fragmento, consulta, esperado in BUSQUEDAS:
                inicio = time.time()
                await cdp.js("document.querySelector('input.series-search').select()")
                await cdp("Input.insertText", text=consulta)
                for tipo in ("keyDown", "keyUp"):
                    await cdp("Input.dispatchKeyEvent", type=tipo, key="ArrowRight", code="ArrowRight",
                              windowsVirtualKeyCode=39, nativeVirtualKeyCode=39)
                await asyncio.sleep(7)                 # 400 ms de espera de htmx + respuesta + que Orca termine
                fin = time.time()
                estado = await cdp.js("""(() => { const r = document.querySelector('#descubrir-estado');
                  return {mismo_nodo: r === window.__reg, texto: r.textContent.trim(), aria_live: r.getAttribute('aria-live'),
                          mutaciones: window.__mut.splice(0).length,
                          foco: document.activeElement.className }; })()""")
                resultado["busquedas"].append({"fragmento": fragmento, "consulta": consulta, "esperado": esperado,
                                               "region": estado, "inicio": inicio, "fin": fin})
            await asyncio.sleep(3)
    finally:
        chrome.terminate()
        await asyncio.sleep(1)
        orca.terminate()
        orca.wait(timeout=10)
        (Path.home() / ".config" / "dconf" / base_dconf).unlink(missing_ok=True)
    for b in resultado["busquedas"]:
        b["orca_dijo"] = u11.frases(registro, b.pop("inicio"), b.pop("fin"))
    (salida / "orca-habla.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


async def _servir(cdp, cola, datos, n, cab) -> None:
    secuencia = [f for f, _, _ in BUSQUEDAS]
    while True:
        par = await cola.get()
        if "/buscar" in par["request"]["url"]:
            cuerpo = datos[secuencia[min(n["i"], len(secuencia) - 1)]]
            n["i"] += 1
        else:
            cuerpo = datos["pagina"]
        await cdp("Fetch.fulfillRequest", requestId=par["requestId"], responseCode=200, responseHeaders=cab,
                  body=base64.b64encode(cuerpo.encode()).decode())


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2]), Path(sys.argv[3])))
