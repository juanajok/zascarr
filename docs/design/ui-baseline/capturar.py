#!/usr/bin/env python3
# ruff: noqa: E501, UP031
"""Línea base de la UI (V0): capturas reproducibles con Chrome headless por CDP.

Herramienta de desarrollo, FUERA del paquete: no entra en la imagen ni en `pyproject.toml`.
Necesita `google-chrome` y el paquete `websockets` del Python del sistema (nada más).

    python3 capturar.py FASE URL_BASE DIRECTORIO_DE_SALIDA

Fases (cada una se ejecuta con el estado del entorno que su nombre indica, ver README.md):
    principal   BD disponible, sin contraseña: pantallas, aviso legal y caso 409
    bd-caida    solo `/estado` y `/ui/` con la BD caída (la prepara quien lo ejecuta)
    login       con contraseña activada: `/login`

No modifica la aplicación. Escribe PNG y `datos-<fase>.json` (lo que se observó).
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

CHROME = "google-chrome"
PUERTO = 9333
ESCRITORIO = {"nombre": "escritorio", "w": 1280, "h": 800, "movil": False}
MOVIL = {"nombre": "movil", "w": 390, "h": 844, "movil": True}


class Navegador:
    def __init__(self) -> None:
        self.dir = tempfile.mkdtemp(prefix="ui-baseline-")
        self.proc = subprocess.Popen(
            [CHROME, "--headless=new", f"--remote-debugging-port={PUERTO}",
             f"--user-data-dir={self.dir}", "--disable-gpu", "--hide-scrollbars",
             "--no-first-run", "--no-default-browser-check", "--disable-extensions",
             "--force-device-scale-factor=1", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        self._id = 0
        self._eventos: list[dict] = []
        self.version: dict = {}

    async def abrir(self) -> None:
        for _ in range(50):
            try:
                self.version = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/json/version"))
                break
            except Exception:  # noqa: BLE001
                await asyncio.sleep(0.2)
        pestanas = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PUERTO}/json"))
        destino = next(p for p in pestanas if p["type"] == "page")
        self.ws = await websockets.connect(destino["webSocketDebuggerUrl"], max_size=64 * 1024 * 1024)
        asyncio.create_task(self._leer())
        for m in ("Page.enable", "Network.enable", "Runtime.enable"):
            await self.cdp(m)

    async def _leer(self) -> None:
        self._pend: dict[int, asyncio.Future] = getattr(self, "_pend", {})
        async for crudo in self.ws:
            msg = json.loads(crudo)
            if "id" in msg and msg["id"] in self._pend:
                self._pend.pop(msg["id"]).set_result(msg)
            else:
                self._eventos.append(msg)

    async def cdp(self, metodo: str, **params):
        self._pend = getattr(self, "_pend", {})
        self._id += 1
        fut = asyncio.get_event_loop().create_future()
        self._pend[self._id] = fut
        await self.ws.send(json.dumps({"id": self._id, "method": metodo, "params": params}))
        r = await fut
        if "error" in r:
            raise RuntimeError(f"{metodo}: {r['error']}")
        return r.get("result", {})

    async def vista(self, v: dict, tema: str) -> None:
        await self.cdp("Emulation.setDeviceMetricsOverride", width=v["w"], height=v["h"],
                       deviceScaleFactor=1, mobile=v["movil"])
        await self.cdp("Emulation.setEmulatedMedia",
                       features=[{"name": "prefers-color-scheme", "value": tema}])

    async def ir(self, url: str, espera: float = 0.8) -> None:
        self._eventos.clear()
        await self.cdp("Page.navigate", url=url)
        for _ in range(100):
            await asyncio.sleep(0.1)
            if any(e.get("method") == "Page.loadEventFired" for e in self._eventos):
                break
        await asyncio.sleep(espera)

    async def js(self, expresion: str):
        r = await self.cdp("Runtime.evaluate", expression=expresion, returnByValue=True,
                           awaitPromise=True)
        return r.get("result", {}).get("value")

    async def foto(self, ruta: Path, completa: bool = True) -> None:
        clip = None
        if completa:
            m = await self.cdp("Page.getLayoutMetrics")
            c = m["cssContentSize"]
            clip = {"x": 0, "y": 0, "width": c["width"], "height": min(c["height"], 6000), "scale": 1}
        r = await self.cdp("Page.captureScreenshot", format="png", captureBeyondViewport=completa,
                           **({"clip": clip} if clip else {}))
        import base64
        ruta.write_bytes(base64.b64decode(r["data"]))

    async def cerrar(self) -> None:
        await self.ws.close()
        self.proc.terminate()


def post_form(base: str, ruta: str, campos: dict) -> int:
    from urllib.parse import urlencode
    req = urllib.request.Request(base + ruta, data=urlencode(campos).encode(), method="POST",
                                 headers={"Origin": base, "Content-Type": "application/x-www-form-urlencoded"})

    class SinRedireccion(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):  # noqa: D401
            return None
    try:
        return urllib.request.build_opener(SinRedireccion).open(req).status
    except urllib.error.HTTPError as e:
        return e.code


async def fase_principal(nav: Navegador, base: str, salida: Path, datos: dict) -> None:
    pantallas = [
        ("panel", "/ui/"), ("biblioteca", "/ui/biblioteca"), ("descubrir", "/ui/descubrir"),
        ("pendientes", "/ui/pendientes"), ("deseados-sin-aviso-legal", "/ui/wishlist"),
        ("mi-biblioteca", "/ui/auditoria"), ("ajustes", "/ui/ajustes"), ("estado", "/estado"),
        ("aviso-legal-asistente", "/ui/legal"), ("aviso-legal-texto", "/legal"),
    ]
    # Ficha de serie: el id sale del enlace de la propia rejilla (no se inventa).
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/biblioteca")
    ficha = await nav.js(
        "(() => { const a=[...document.querySelectorAll('a[href^=\"/ui/series/\"]')]"
        ".find(x=>x.textContent.includes('Guardianes')); return a? a.getAttribute('href'):null })()")
    datos["ficha_serie"] = ficha
    if ficha:
        pantallas.append(("ficha-de-serie", ficha))

    for v in (ESCRITORIO, MOVIL):
        await nav.vista(v, "light")
        for nombre, ruta in pantallas:
            await nav.ir(base + ruta, espera=1.6 if nombre == "estado" else 0.8)
            await nav.foto(salida / f"{nombre}--{v['nombre']}-{v['w']}x{v['h']}-claro.png")
    # Oscuro, solo escritorio y las pantallas con más color y estado.
    await nav.vista(ESCRITORIO, "dark")
    for nombre, ruta in (("panel", "/ui/"), ("pendientes", "/ui/pendientes"),
                         ("estado", "/estado"), ("ajustes", "/ui/ajustes")):
        await nav.ir(base + ruta, espera=1.6 if nombre == "estado" else 0.8)
        await nav.foto(salida / f"{nombre}--escritorio-1280x800-oscuro.png")

    # Aviso legal: se acepta (POST real) y se vuelve a ver Deseados con el aviso resuelto.
    datos["aceptar_aviso_legal_http"] = post_form(
        base, "/ui/legal/accept", {"acepto_1": "on", "acepto_2": "on", "acepto_3": "on"})
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/wishlist")
    await nav.foto(salida / "deseados--escritorio-1280x800-claro.png")

    await caso_409(nav, base, salida, datos)


async def caso_409(nav: Navegador, base: str, salida: Path, datos: dict) -> None:
    """Asignar un ómnibus (Omnigold 12) a una serie cuyo nº 12 es una GRAPA: colisión B15."""
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/pendientes")
    marcador = "Omnigold 12"
    info = await nav.js("""(() => {
      const t=[...document.querySelectorAll('.pending-card')].find(c=>c.textContent.includes(%s));
      if(!t) return null;
      const f=t.querySelector('form.assign-form');
      return {id:t.id, antes:t.outerHTML,
              numero: f? f.querySelector('input[name=issue_number]').value : null,
              serie: f? f.querySelector('input[name=series_id]').value : null}})()""" % json.dumps(marcador))
    datos["caso_409_antes"] = info
    if not info:
        return
    await nav.js(f"document.getElementById({json.dumps(info['id'])}).scrollIntoView({{block:'center'}})")
    await nav.foto(salida / "caso-409-1-antes--escritorio-1280x800-claro.png", completa=False)

    nav._eventos.clear()
    pos = await nav.js(f"""(() => {{ const b=document.getElementById({json.dumps(info['id'])})
        .querySelector('button.btn-sugerencia'); const r=b.getBoundingClientRect();
        return {{x:r.x+r.width/2, y:r.y+r.height/2}} }})()""")
    for tipo in ("mousePressed", "mouseReleased"):
        await nav.cdp("Input.dispatchMouseEvent", type=tipo, x=pos["x"], y=pos["y"],
                      button="left", clickCount=1)
    await asyncio.sleep(1.5)

    respuestas = []
    for e in nav._eventos:
        if e.get("method") == "Network.responseReceived":
            r = e["params"]["response"]
            if "/asignar" in r["url"]:
                cuerpo = None
                try:
                    cuerpo = (await nav.cdp("Network.getResponseBody",
                                            requestId=e["params"]["requestId"])).get("body")
                except RuntimeError as exc:
                    cuerpo = f"(no disponible: {exc})"
                respuestas.append({"url": r["url"], "estado": r["status"],
                                   "content_type": r["headers"].get("content-type") or
                                   r["headers"].get("Content-Type"), "cuerpo": cuerpo})
    datos["caso_409_respuesta"] = respuestas
    datos["caso_409_despues"] = await nav.js(
        f"(() => {{ const t=document.getElementById({json.dumps(info['id'])}); "
        "return t? {existe:true, html:t.outerHTML} : {existe:false, "
        "texto_main: document.querySelector('main').innerText.slice(0,1500)} })()")
    await nav.foto(salida / "caso-409-2-despues--escritorio-1280x800-claro.png", completa=False)
    await nav.foto(salida / "caso-409-3-despues-pagina--escritorio-1280x800-claro.png")


async def fase_bd_caida(nav: Navegador, base: str, salida: Path, datos: dict, etiqueta: str) -> None:
    await nav.vista(ESCRITORIO, "light")
    for nombre, ruta in (("estado", "/estado"), ("panel", "/ui/")):
        await nav.ir(base + ruta, espera=2.0)
        await nav.foto(salida / f"{etiqueta}-{nombre}--escritorio-1280x800-claro.png")
        datos[f"{etiqueta}_{nombre}_texto"] = await nav.js("document.body.innerText.slice(0,800)")
    for ruta in ("/api/health", "/ui/", "/estado"):
        try:
            r = urllib.request.urlopen(base + ruta, timeout=10)
            datos[f"{etiqueta}_http_{ruta}"] = r.status
        except urllib.error.HTTPError as e:
            datos[f"{etiqueta}_http_{ruta}"] = e.code
        except Exception as e:  # noqa: BLE001
            datos[f"{etiqueta}_http_{ruta}"] = repr(e)


async def fase_login(nav: Navegador, base: str, salida: Path, datos: dict) -> None:
    for v in (ESCRITORIO, MOVIL):
        await nav.vista(v, "light")
        await nav.ir(base + "/login")
        await nav.foto(salida / f"login--{v['nombre']}-{v['w']}x{v['h']}-claro.png")
    await nav.vista(ESCRITORIO, "dark")
    await nav.ir(base + "/login")
    await nav.foto(salida / "login--escritorio-1280x800-oscuro.png")


async def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    fase, base, salida = sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3])
    salida.mkdir(parents=True, exist_ok=True)
    nav = Navegador()
    datos: dict = {"fase": fase, "base": base, "fecha": time.strftime("%Y-%m-%d %H:%M:%S %Z")}
    try:
        await nav.abrir()
        datos["navegador"] = nav.version.get("Browser")
        datos["user_agent"] = nav.version.get("User-Agent")
        datos["zoom"] = "100 % (factor de escala del dispositivo 1)"
        if fase == "principal":
            await fase_principal(nav, base, salida, datos)
        elif fase.startswith("bd-caida"):
            await fase_bd_caida(nav, base, salida, datos, fase)
        elif fase == "login":
            await fase_login(nav, base, salida, datos)
        else:
            sys.exit(f"fase desconocida: {fase}")
    finally:
        await nav.cerrar()
        (salida / f"datos-{fase}.json").write_text(
            json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(re.sub(r"\s+", " ", json.dumps({k: v for k, v in datos.items() if k.startswith("caso")},
                                        ensure_ascii=False))[:1500])


if __name__ == "__main__":
    asyncio.run(main())
