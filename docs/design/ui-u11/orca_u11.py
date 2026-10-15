#!/usr/bin/env python3
# ruff: noqa: E501
"""U11 (#198) con un lector de pantalla real: Orca + Google Chrome con ventana, contra el ensayo.

Herramienta de desarrollo, FUERA del paquete. Necesita una sesión gráfica con AT-SPI, `orca`,
`google-chrome` y `websockets`. Arranca Orca con su registro de depuración, abre Chrome con
accesibilidad y mueve el foco con pulsaciones REALES de Tab (`Input.dispatchKeyEvent`): el foco cambia
de verdad en el navegador y Orca lo anuncia como si se pulsara la tecla. Al terminar cierra Chrome y
Orca y extrae lo que Orca dijo:

    python3 docs/design/ui-u11/orca_u11.py http://127.0.0.1:18000 docs/design/ui-u11

Escribe `orca-habla.json` (pasos y frases). El registro completo de Orca se queda en un temporal.
La configuración de Orca es una base de dconf PROPIA que se borra al terminar: no toca la del usuario.
"""
from __future__ import annotations

import asyncio
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

PUERTO = 9334

ANTERIOR = """(() => {{ const t = document.querySelector({destino!r});
  const f = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select')]
    .filter(e => e.getClientRects().length && e.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING);
  f[f.length - 1].focus(); return document.activeElement.outerHTML.slice(0, 80); }})()"""

# (ruta, selector del primer control al que se llega con Tab, nº de Tabs, qué debe decir Orca)
PASOS = [
    ("/ui/pendientes", ".pending-card:nth-child(4) .series-search", 1,
     "Serie de «Mundo Cobalto - Edicion Integral 01 [Equipo X].cbz»"),
    ("/ui/pendientes", ".pending-card:nth-child(1) .issue-input", 1,
     "Número de «Los Guardianes del Alba Omnigold 12 [CRG].cbz»"),
    ("/ui/biblioteca", "#f-q", 5, "Buscar por título · Tradición · Editorial · Buscar personaje · Buscar saga"),
    ("/ui/wishlist", "#q-deseados", 1, "Buscar serie para añadir a Deseados"),
]


class Cdp:
    def __init__(self, ws) -> None:
        self.ws, self._id = ws, 0

    async def __call__(self, metodo: str, **params):
        self._id += 1
        await self.ws.send(json.dumps({"id": self._id, "method": metodo, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self._id:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error']}")
                return msg.get("result", {})

    async def js(self, expr: str):
        r = await self("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    async def tab(self) -> None:
        for tipo in ("rawKeyDown", "keyUp"):
            await self("Input.dispatchKeyEvent", type=tipo, key="Tab", code="Tab",
                       windowsVirtualKeyCode=9, nativeVirtualKeyCode=9)


def frases(registro: Path, desde: float, hasta: float) -> list[str]:
    """Lo que Orca mandó al sintetizador entre dos instantes (marcas de tiempo del registro)."""
    salida = []
    for linea in registro.read_text(errors="replace").splitlines():
        m = re.match(r"(\d\d):(\d\d):(\d\d)\.(\d+)", linea)
        if m and "SPEECH OUTPUT:" in linea:
            h, mi, s, frac = (int(x) for x in m.groups())
            hoy = time.localtime(desde)
            t = time.mktime((hoy.tm_year, hoy.tm_mon, hoy.tm_mday, h, mi, s, 0, 0, -1)) + frac / 10 ** len(m.group(4))
            if desde <= t <= hasta:
                frase = linea.split("SPEECH OUTPUT:", 1)[1].strip()
                salida.append(re.sub(r"' \{.*$", "", frase).strip("'"))   # sin los datos de la voz
    return salida


async def main(base: str, salida: Path) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="orca-u11-"))
    registro = tmp / "orca-debug.out"
    # Configuración de Orca AISLADA: una base de dconf propia (no toca la del usuario) con «leer
    # todo al cargar» y el resumen de página desactivados; si no, Orca lee la página entera al
    # cargarla e ignora los cambios de foco mientras tanto.
    base_dconf = "orcau11" + re.sub(r"[^A-Za-z0-9]", "", tmp.name)   # sin «-»: va en una ruta de D-Bus
    perfil = tmp / "dconf-profile"
    perfil.write_text(f"user-db:{base_dconf}\n", encoding="utf-8")
    entorno = {**os.environ, "DCONF_PROFILE": str(perfil)}
    for clave in ("say-all-on-load", "page-summary-on-load"):
        subprocess.run(["dconf", "write", f"/org/gnome/orca/default/document/{clave}", "false"],
                       env=entorno, check=True)
    orca = subprocess.Popen(["orca", "--debug-file", str(registro)], env=entorno,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    await asyncio.sleep(4)
    chrome = subprocess.Popen(
        ["google-chrome", f"--remote-debugging-port={PUERTO}", f"--user-data-dir={tmp / 'perfil'}",
         "--force-renderer-accessibility", "--no-first-run", "--no-default-browser-check",
         "--disable-extensions", "--new-window", base + "/ui/"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    resultado: dict = {"orca": subprocess.run(["orca", "--version"], capture_output=True, text=True).stdout.strip(),
                       "pasos": []}
    try:
        for _ in range(50):
            try:
                pestanas = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/json"))
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.3)
        destino = next(p for p in pestanas if p["type"] == "page")
        async with websockets.connect(destino["webSocketDebuggerUrl"], max_size=2 ** 26) as ws:
            cdp = Cdp(ws)
            resultado["chrome"] = (await cdp("Browser.getVersion"))["product"]
            await cdp("Page.enable")
            for ruta, selector, tabs, esperado in PASOS:
                await cdp("Page.navigate", url=base + ruta)
                await asyncio.sleep(5)                   # Orca lleva el foco al inicio al cargar
                await cdp("Page.bringToFront")
                inicial = await cdp.js(ANTERIOR.format(destino=selector))
                await asyncio.sleep(2.0)             # que Orca termine con el control anterior
                inicio = time.time()
                for _ in range(tabs):
                    await cdp.tab()
                    await asyncio.sleep(2.5)         # que Orca termine de hablar
                fin = time.time()
                paso = {"ruta": ruta, "tabs": tabs, "esperado": esperado,
                        "foco_inicial": inicial,
                        "foco_final": await cdp.js("document.activeElement.id || document.activeElement.name"),
                        "inicio": inicio, "fin": fin}
                if ruta == "/ui/wishlist":
                    # Visibilidad calculada de cada «Buscando…»: indicadores (deben estar `hidden` en
                    # reposo) e insignias de estado (visibles; son V8, no U11).
                    paso["buscando_en_dom"] = await cdp.js(
                        "[...document.querySelectorAll('body *')].filter(e => !e.children.length && /Buscando/.test(e.textContent))"
                        ".map(e => e.className + ' ' + getComputedStyle(e).visibility)")
                resultado["pasos"].append(paso)
            await asyncio.sleep(3)                       # que Orca acabe antes de cerrar Chrome
    finally:
        chrome.terminate()
        await asyncio.sleep(1)
        orca.terminate()
        orca.wait(timeout=10)
        (Path.home() / ".config" / "dconf" / base_dconf).unlink(missing_ok=True)
    for paso in resultado["pasos"]:
        paso["orca_dijo"] = frases(registro, paso.pop("inicio"), paso.pop("fin"))
    (salida / "orca-habla.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2])))
