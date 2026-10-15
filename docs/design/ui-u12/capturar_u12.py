#!/usr/bin/env python3
# ruff: noqa: E501
"""Evidencia de U12 (#199) en la APLICACIÓN INTEGRADA: Chrome headless por CDP a 375 px contra el ensayo aislado.

Reutiliza `Navegador` de `../ui-baseline/capturar.py`. Añade al ensayo (solo con la marca de ensayo) un `.cbr`, un
nombre largo y sin espacios y 60 pendientes de relleno, para que haya más de una página. Los clics son REALES
(`Input.dispatchMouseEvent`) y el `confirm()` de «Ignorar» se acepta por el protocolo.

    UI_BASE_DATOS=… docs/design/ui-baseline/ensayo.sh preparar
    python3 docs/design/ui-u12/capturar_u12.py http://127.0.0.1:18000 docs/design/ui-u12
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "capturar", Path(__file__).resolve().parents[1] / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capturar)

MOVIL = {"nombre": "movil", "w": 375, "h": 812, "movil": True}
LARGO = "Los_Guardianes_del_Alba_Omnigold_Edicion_Especial_Integral_Tomo_" + "x" * 90 + ".cbz"

SQL = f"""
INSERT INTO files (file_path, file_name, file_format, imported_at, metadata)
SELECT '/media/library/_Unsorted/' || n, n, f::file_format, now() - interval '1 second' * k, '{{"match_status":"unsorted"}}'
FROM (VALUES ('Flash cbr 01.cbr', 'cbr', 1), ('{LARGO}', 'cbz', 2)) AS v(n, f, k)
ON CONFLICT (file_path) DO NOTHING;
INSERT INTO files (file_path, file_name, file_format, imported_at, metadata)
SELECT '/media/library/_Unsorted/Relleno ' || lpad(g::text, 3, '0') || '.cbz', 'Relleno ' || lpad(g::text, 3, '0') || '.cbz',
       'cbz'::file_format, now() - interval '1 minute' * g, '{{"match_status":"unsorted"}}'
FROM generate_series(1, 60) g
ON CONFLICT (file_path) DO NOTHING;
"""

MEDIR = r"""(() => {
  const cards = [...document.querySelectorAll('.pending-card')];
  const nombre = c => c.querySelector('.filename');
  const primero = cards[0], n0 = nombre(primero).getBoundingClientRect();
  const largo = cards.find(c => nombre(c).textContent.startsWith('Los_Guardianes_del_Alba_Omnigold_Edicion'));
  const cbr = cards.find(c => nombre(c).textContent.endsWith('.cbr'));
  const conPortada = cards.find(c => c.querySelector('img.cover') && nombre(c).textContent.includes('Omnigold 12'));
  const el = c => { const n = nombre(c); const cs = getComputedStyle(n); return {
      texto: n.textContent.trim().length, caben: n.scrollWidth <= n.clientWidth + 1, ellipsis: cs.textOverflow === 'ellipsis',
      nowrap: cs.whiteSpace === 'nowrap', alto: Math.round(n.getBoundingClientRect().height) }; };
  return {
    ancho_pagina: document.documentElement.scrollWidth, ancho_ventana: document.documentElement.clientWidth,
    sin_scroll_horizontal: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    rango: (document.querySelector('#pend-rango') || {}).textContent?.trim(),
    primer_nombre_completo_en_el_primer_pantallazo: n0.top >= 0 && n0.bottom <= window.innerHeight,
    primer_nombre: el(primero),
    nombre_largo: largo ? el(largo) : null,
    cbr: cbr ? {img: !!cbr.querySelector('img'), bloque_portada: !!cbr.querySelector('.cover'), html_portada: cbr.innerHTML.includes('/portada')} : null,
    con_portada: conPortada ? (() => { const i = conPortada.querySelector('img.cover'); const r = i.getBoundingClientRect(), nr = nombre(conPortada).getBoundingClientRect();
        return {alto: Math.round(r.height), ancho: Math.round(r.width), debajo_del_nombre: r.top >= nr.bottom, natural: i.naturalWidth}; })() : null,
    imagenes: cards.filter(c => c.querySelector('img')).length, tarjetas: cards.length,
    portadas_rotas: (() => { const rotas = [...document.querySelectorAll('img.cover')].filter(i => i.complete && i.naturalWidth === 0);
      return {n: rotas.length, alturas: [...new Set(rotas.map(i => Math.round(i.getBoundingClientRect().height)))],
              alto_tarjeta_con_rota: rotas.length ? Math.round(rotas[0].closest('.pending-card').getBoundingClientRect().height) : null}; })(),
    onerror_en_pagina: document.documentElement.innerHTML.includes('onerror'),
  };
})()"""


async def clic(nav, selector: str, indice: int = 0) -> None:
    pos = await nav.js(f"""(() => {{ const e = document.querySelectorAll({selector!r})[{indice}]; e.scrollIntoView({{block: 'center'}});
      const r = e.getBoundingClientRect(); return {{x: r.x + r.width / 2, y: r.y + r.height / 2}}; }})()""")
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        await nav.cdp("Input.dispatchMouseEvent", type=tipo, x=pos["x"], y=pos["y"], button="left", clickCount=1)


async def aceptar_confirm(nav, espera: float = 5.0) -> bool:
    """El `hx-confirm` de «Ignorar» abre un `confirm()` que BLOQUEA el clic hasta que se responde: se acepta por el
    protocolo (como lo haría la persona), mientras el clic sigue en curso."""
    for _ in range(int(espera / 0.1)):
        if any(e.get("method") == "Page.javascriptDialogOpening" for e in nav._eventos):
            await nav.cdp("Page.handleJavaScriptDialog", accept=True)
            return True
        await asyncio.sleep(0.1)
    return False


def peticiones(nav, patron: str) -> list[dict]:
    salida = []
    for e in nav._eventos:
        if e.get("method") == "Network.requestWillBeSent" and re.search(patron, e["params"]["request"]["url"]):
            salida.append({"url": e["params"]["request"]["url"]})
    return salida


def respuestas(nav, patron: str) -> list[int]:
    return [e["params"]["response"]["status"] for e in nav._eventos
            if e.get("method") == "Network.responseReceived" and re.search(patron, e["params"]["response"]["url"])]


async def refrescos_fuera_de_orden(nav, base: str, quitar_sync: bool) -> dict:
    """Bloqueante 3 de la revisión: dos «Ignorar» seguidos lanzan dos refrescos del rango y el PRIMERO termina
    DESPUÉS. Con `Fetch` se retiene la RESPUESTA del primero (en la etapa de respuesta: el servidor ya la calculó,
    con el dato de ese momento) hasta que el segundo ha terminado, y se mira qué queda en pantalla. `quitar_sync` elimina `hx-sync` de las respuestas de «Ignorar» (variante de control: sin el
    mecanismo...). RESULTADO HONESTO: en htmx 4.0.0 / Chrome 154 la variante de control TAMBIÉN conserva el último,
    porque el refresco es un `outerHTML`: al sustituir el nuevo a `#pend-rango`, la respuesta antigua apunta a un
    elemento ya desconectado y no hace nada. `hx-sync` añade el ABORTO de la petición antigua (visible en
    `refrescos_abortados_o_fallidos`), pero no es lo que evita la sobrescritura: es una defensa adicional."""
    await nav.ir(base + "/ui/pendientes", espera=1.5)
    inicial = await nav.js("document.querySelector('#pend-rango').textContent.trim()")
    retenidas: list[dict] = []
    await nav.cdp("Fetch.enable", patterns=[
        {"urlPattern": "*/ui/pendientes/rango*", "requestStage": "Response"},
        {"urlPattern": "*/ignorar", "requestStage": "Response"}])
    nav._eventos.clear()

    async def atender() -> None:
        while True:
            for e in list(nav._eventos):
                if e.get("method") != "Fetch.requestPaused" or e.get("_visto"):
                    continue
                e["_visto"] = True
                par = e["params"]
                url = par["request"]["url"]
                if url.endswith("/ignorar") and "responseStatusCode" in par:
                    cuerpo = await nav.cdp("Fetch.getResponseBody", requestId=par["requestId"])
                    import base64
                    texto = base64.b64decode(cuerpo["body"]).decode() if cuerpo.get("base64Encoded") else cuerpo["body"]
                    if quitar_sync:
                        texto = texto.replace(' hx-sync="#pend-rango:replace"', "")
                    cabeceras = [h for h in par["responseHeaders"] if h["name"].lower() != "content-length"]
                    await nav.cdp("Fetch.fulfillRequest", requestId=par["requestId"], responseCode=200,
                                  responseHeaders=cabeceras, body=base64.b64encode(texto.encode()).decode())
                elif "/ui/pendientes/rango" in url:
                    if not retenidas:                       # la respuesta del PRIMER refresco se retiene
                        retenidas.append(par)
                    else:
                        await nav.cdp("Fetch.continueResponse", requestId=par["requestId"])
            await asyncio.sleep(0.05)

    tarea = asyncio.create_task(atender())
    try:
        for _ in range(2):                                  # dos tarjetas resueltas, seguidas
            await asyncio.gather(clic(nav, ".pending-card .btn-ignorar"), aceptar_confirm(nav))
            nav._eventos[:] = [e for e in nav._eventos if e.get("method") != "Page.javascriptDialogOpening"]
            await asyncio.sleep(0.8)
        await asyncio.sleep(1.0)
        tras_el_segundo = await nav.js("document.querySelector('#pend-rango').textContent.trim()")
        if retenidas:                                       # ahora se SUELTA la respuesta antigua
            try:
                await nav.cdp("Fetch.continueResponse", requestId=retenidas[0]["requestId"])
            except RuntimeError:
                pass                                        # htmx la abortó: ya no existe
        await asyncio.sleep(1.5)
        al_final = await nav.js("document.querySelector('#pend-rango').textContent.trim()")
    finally:
        tarea.cancel()
        await nav.cdp("Fetch.disable")
    def cuenta(metodo: str, patron: str) -> int:
        return sum(1 for e in nav._eventos if e.get("method") == metodo
                   and re.search(patron, json.dumps(e.get("params", {}))))
    diagnostico = {
        "posts_ignorar": cuenta("Network.requestWillBeSent", r'"url": "[^"]*/ignorar"'),
        "refrescos_pedidos": cuenta("Network.requestWillBeSent", r'/ui/pendientes/rango'),
        "refrescos_abortados_o_fallidos": cuenta("Network.loadingFailed", r'.'),
        "fetch_pausados": sum(1 for e in nav._eventos if e.get("method") == "Fetch.requestPaused")}
    # Una ejecución solo vale si ocurrió lo que se quería probar: dos resoluciones y dos refrescos.
    valido = diagnostico["posts_ignorar"] == 2 and diagnostico["refrescos_pedidos"] == 2 and bool(retenidas)
    return {"valido": valido, "con_hx_sync": not quitar_sync, "diagnostico": diagnostico, "inicial": inicial,
            "tras_el_segundo_refresco": tras_el_segundo,
            "tras_soltar_el_primero": al_final, "primero_retenido": bool(retenidas),
            "gana_el_ultimo": al_final == tras_el_segundo}


async def main(base: str, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    sembrado = subprocess.run(
        ["docker", "exec", "-i", "zascarr-uibase-db", "psql", "-q", "-U", "comics_admin", "-d", "zascarr", "-v", "ON_ERROR_STOP=1"],
        input=SQL, text=True, capture_output=True)
    assert sembrado.returncode == 0, sembrado.stderr
    nav = capturar.Navegador()
    datos: dict = {}
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "principal")
        await nav.vista(MOVIL, "light")
        datos["chrome"] = nav.version.get("Browser")
        datos["viewport"] = f"{MOVIL['w']}x{MOVIL['h']} (emulación de viewport con mobile=true)"

        # ── A. Primera página
        await nav.ir(base + "/ui/pendientes", espera=1.5)
        await nav.js("document.querySelectorAll('img.cover').forEach(i => i.scrollIntoView())")   # fuerza la carga diferida
        await asyncio.sleep(1.5)
        await nav.js("window.scrollTo(0, 0)")
        datos["pagina_1"] = await nav.js(MEDIR)
        datos["peticiones_portada"] = {"total": len(peticiones(nav, r"/portada$")), "estados": sorted(respuestas(nav, r"/portada$"))}
        await nav.foto(salida / "1-primera-pagina-375.png", completa=False)

        # ── B. Navegación: Siguientes → y ← Anteriores, con clics reales
        await clic(nav, "a.pend-siguiente")
        await asyncio.sleep(1.5)
        datos["siguiente"] = await nav.js("(document.querySelector('#pend-rango') || {}).textContent?.trim()")
        datos["siguiente_tarjetas"] = await nav.js("document.querySelectorAll('.pending-card').length")
        await nav.foto(salida / "2-segunda-pagina-375.png", completa=False)
        await clic(nav, "a.pend-anterior")
        await asyncio.sleep(1.5)
        datos["anterior"] = await nav.js("(document.querySelector('#pend-rango') || {}).textContent?.trim()")

        # ── C. Resolver una tarjeta y ver el rango actualizarse SIN recargar
        antes = await nav.js("document.querySelector('#pend-rango').textContent.trim()")
        nav._eventos.clear()
        _clic, aceptado = await asyncio.gather(clic(nav, ".pending-card .btn-ignorar"), aceptar_confirm(nav))
        datos["confirm_aceptado"] = aceptado
        await asyncio.sleep(2.0)
        despues = await nav.js("(document.querySelector('#pend-rango') || {}).textContent?.trim()")
        datos["refresco_sin_recargar"] = {
            "antes": antes, "despues": despues,
            "tarjetas": await nav.js("document.querySelectorAll('.pending-card').length"),
            "peticion_rango": [p["url"] for p in peticiones(nav, r"/ui/pendientes/rango")],
            "estado_rango": respuestas(nav, r"/ui/pendientes/rango"),
            "navegaciones": await nav.js("performance.getEntriesByType('navigation').length")}
        await nav.foto(salida / "3-tras-ignorar-375.png", completa=False)

        # ── D. Refrescos que terminan FUERA DE ORDEN (revisión de #214): con el mecanismo y sin él (control)
        datos["fuera_de_orden"] = {
            "con_hx_sync": await refrescos_fuera_de_orden(nav, base, quitar_sync=False),
            "control_sin_hx_sync": await refrescos_fuera_de_orden(nav, base, quitar_sync=True)}
    finally:
        await nav.cerrar()
    (salida / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(datos, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2])))
