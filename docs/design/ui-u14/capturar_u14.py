#!/usr/bin/env python3
# ruff: noqa: E501
"""Evidencia de U14 (#201) en navegador real: Chrome headless por CDP contra el ensayo aislado.

Reutiliza `Navegador` de `../ui-baseline/capturar.py`. El ensayo tiene las fuentes APAGADAS a propósito (nada sale a la red)
y no se encienden: la página y los fragmentos de búsqueda los genera la ruta REAL con el servicio sustituido
(`fragmentos.py`) y se sirven al navegador con `Fetch.fulfillRequest`. Lo demás (hoja de estilos, htmx, plantilla base) viene
del servidor del ensayo. Se prueba la PRESENTACIÓN y el comportamiento del navegador, no las fuentes.

    python3 docs/design/ui-u14/capturar_u14.py http://127.0.0.1:18000 fragmentos.json docs/design/ui-u14
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "capturar", Path(__file__).resolve().parents[1] / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capturar)

ESCRITORIO = {"nombre": "escritorio", "w": 1280, "h": 900, "movil": False}
MOVIL = {"nombre": "movil", "w": 375, "h": 812, "movil": True}


async def servir(nav, pagina: str, fragmento: str, retraso: float) -> asyncio.Task:
    """Atiende `Fetch.requestPaused`: la página de Descubrir y `/buscar` se sirven desde aquí (esta con `retraso`)."""
    await nav.cdp("Fetch.enable", patterns=[
        {"urlPattern": "*/ui/descubrir", "requestStage": "Request"},
        {"urlPattern": "*/ui/descubrir/buscar*", "requestStage": "Request"}])
    cabeceras = [{"name": "Content-Type", "value": "text/html; charset=utf-8"}, {"name": "Cache-Control", "value": "no-store"}]

    async def uno(par):
        url = par["request"]["url"]
        cuerpo = fragmento if "/buscar" in url else pagina
        if "/buscar" in url and retraso:
            await asyncio.sleep(retraso)
        await nav.cdp("Fetch.fulfillRequest", requestId=par["requestId"], responseCode=200,
                      responseHeaders=cabeceras, body=base64.b64encode(cuerpo.encode()).decode())

    async def bucle():
        vistos: set[str] = set()
        while True:
            for e in list(nav._eventos):
                if e.get("method") == "Fetch.requestPaused":
                    rid = e["params"]["requestId"]
                    if rid not in vistos:
                        vistos.add(rid)
                        asyncio.create_task(uno(e["params"]))
            await asyncio.sleep(0.02)
    return asyncio.create_task(bucle())


MUESTREAR = r"""(() => {
  const ind = document.querySelector('#buscando-descubrir'); window.__v = []; window.__ev = {};
  const t0 = performance.now(); window.__t0 = t0;
  document.addEventListener('htmx:before:request', () => { window.__ev.antes = Math.round(performance.now() - t0); });
  document.addEventListener('htmx:after:request', () => { window.__ev.despues = Math.round(performance.now() - t0); });
  window.__iv = setInterval(() => { const c = getComputedStyle(ind);
    window.__v.push([Math.round(performance.now() - t0), c.visibility, +c.opacity]); }, 20);
  return true; })()"""

ANALIZAR = r"""(() => {
  clearInterval(window.__iv);
  const v = window.__v, antes = window.__ev.antes, despues = window.__ev.despues;
  const visibles = v.filter(x => x[1] === 'visible' && x[2] > 0);
  const primero = visibles.length ? visibles[0][0] : null;
  return { peticion_empieza_ms: antes ?? null, peticion_termina_ms: despues ?? null,
    indicador_visible_por_primera_vez_ms: primero,
    espera_hasta_verlo_ms: (primero !== null && antes !== undefined) ? primero - antes : null,
    llego_a_verse: visibles.length > 0,
    visible_al_final: v.length ? (v[v.length - 1][1] === 'visible') : null,
    muestras: v.length }; })()"""

HECHOS = r"""(() => {
  const cuerpo = document.querySelector('main') || document.body;
  const vivas = [...cuerpo.querySelectorAll('[aria-live], [role="status"], [role="alert"]')];
  const reg = document.querySelector('#descubrir-estado');
  const destino = document.querySelector('#resultados-descubrir');
  const sel = document.querySelector('.discovery-card-actions select');
  const cs = sel ? getComputedStyle(sel) : null;
  const enlace = document.querySelector('.discovery-card-title a');
  const desc = document.querySelector('.discovery-card-desc');
  return {
    regiones_vivas_en_la_pagina: vivas.length,
    la_region_es_la_unica: vivas.length === 1 && vivas[0] === reg,
    la_region_no_esta_en_el_destino: !destino.contains(reg),
    destino_con_aria_live: destino.querySelectorAll('[aria-live], [role="status"], [role="alert"]').length,
    texto_de_la_region: reg ? reg.textContent.trim() : null,
    region_visible_a_la_vista: reg ? (reg.getBoundingClientRect().width > 2 && reg.getBoundingClientRect().height > 2) : null,
    recuento_visible: (document.querySelector('.discovery-count') || {}).textContent ?? null,
    avisos_visibles: [...document.querySelectorAll('#resultados-descubrir .aviso')].map(a => a.textContent.replace(/\s+/g, ' ').trim()),
    descripcion: desc ? desc.textContent.trim() : null,
    descripcion_con_etiquetas: desc ? /[<>]/.test(desc.textContent) : null,
    fuente: (document.querySelector('.discovery-card-title .caption') || {}).textContent ?? null,
    enlace_aria_label: enlace ? enlace.getAttribute('aria-label') : null,
    select: cs ? {fondo: cs.backgroundColor, color: cs.color, borde: cs.borderTopWidth + ' ' + cs.borderTopStyle + ' ' + cs.borderTopColor,
                  alto: Math.round(sel.getBoundingClientRect().height), appearance: cs.appearance} : null,
    scroll_horizontal: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  }; })()"""


async def nombre_ax(nav, expresion: str):
    obj = (await nav.cdp("Runtime.evaluate", expression=expresion))["result"]
    nodos = (await nav.cdp("Accessibility.getPartialAXTree", objectId=obj["objectId"], fetchRelatives=False))["nodes"]
    return (nodos[0].get("name") or {}).get("value") if nodos else None


async def clic_en(nav, selector: str) -> None:
    pos = await nav.js(f"""(() => {{ const e = document.querySelector({selector!r}); e.scrollIntoView({{block: 'center'}});
      const r = e.getBoundingClientRect(); return {{x: r.x + r.width / 2, y: r.y + r.height / 2}}; }})()""")
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        await nav.cdp("Input.dispatchMouseEvent", type=tipo, x=pos["x"], y=pos["y"], button="left", clickCount=1)


async def escenario(nav, base, datos, salida: Path, *, nombre, vista, tema, fragmento, retraso, foto=True):
    await nav.vista(vista, tema)
    nav._eventos.clear()
    tarea = await servir(nav, datos["pagina"], datos[fragmento], retraso)
    try:
        await nav.ir(base + "/ui/descubrir", espera=1.0)
        await nav.js(MUESTREAR)
        await clic_en(nav, "input.series-search")
        await nav.cdp("Input.insertText", text="Mortadelo")
        await nav.cdp("Input.dispatchKeyEvent", type="keyDown", key="o", text="o")
        await nav.cdp("Input.dispatchKeyEvent", type="keyUp", key="o")
        await asyncio.sleep(0.4 + retraso + 1.6)
        tiempos = await nav.js(ANALIZAR)
        hechos = await nav.js(HECHOS)
        hechos["enlace_nombre_en_el_arbol_de_accesibilidad"] = await nombre_ax(
            nav, "document.querySelector('.discovery-card-title a')") if hechos["enlace_aria_label"] else None
        if foto:
            await nav.foto(salida / f"{nombre}.png", completa=False)
    finally:
        tarea.cancel()
        await nav.cdp("Fetch.disable")
    return {"escenario": nombre, "vista": f"{vista['w']}x{vista['h']}", "tema": tema, "fragmento": fragmento,
            "retraso_simulado_s": retraso, "tiempos": tiempos, "hechos": hechos}


OBSERVAR = r"""(() => {
  const reg = document.querySelector('#descubrir-estado');
  window.__reg = reg; window.__mut = [];
  new MutationObserver(m => m.forEach(x => window.__mut.push(x.type + ':' + (x.type === 'childList'
    ? reg.textContent.trim().slice(0, 60) : x.attributeName)))).observe(reg, {childList: true, subtree: true, characterData: true, attributes: true});
  return {id: reg.id, aria_live: reg.getAttribute('aria-live'), aria_atomic: reg.getAttribute('aria-atomic'), clase: reg.className}; })()"""

ESTADO_REGION = r"""(() => { const r = document.querySelector('#descubrir-estado');
  const mut = window.__mut.splice(0);
  return { es_el_mismo_nodo: r === window.__reg, sigue_en_el_documento: window.__reg.isConnected,
    regiones_con_ese_id: document.querySelectorAll('#descubrir-estado').length,
    aria_live: r.getAttribute('aria-live'), aria_atomic: r.getAttribute('aria-atomic'), clase: r.className,
    atributo_hx_swap_oob_residual: r.hasAttribute('hx-swap-oob'),
    texto: r.textContent.trim(), mutaciones_del_observador: mut }; })()"""


async def servir_secuencia(nav, pagina: str, fragmentos: list[str]) -> asyncio.Task:
    """Como `servir`, pero la N-ésima petición a `/buscar` recibe el N-ésimo fragmento (varias búsquedas seguidas)."""
    await nav.cdp("Fetch.enable", patterns=[
        {"urlPattern": "*/ui/descubrir", "requestStage": "Request"},
        {"urlPattern": "*/ui/descubrir/buscar*", "requestStage": "Request"}])
    cabeceras = [{"name": "Content-Type", "value": "text/html; charset=utf-8"}, {"name": "Cache-Control", "value": "no-store"}]
    n = {"i": 0}

    async def uno(par):
        if "/buscar" in par["request"]["url"]:
            cuerpo = fragmentos[min(n["i"], len(fragmentos) - 1)]
            n["i"] += 1
        else:
            cuerpo = pagina
        await nav.cdp("Fetch.fulfillRequest", requestId=par["requestId"], responseCode=200,
                      responseHeaders=cabeceras, body=base64.b64encode(cuerpo.encode()).decode())

    async def bucle():
        vistos: set[str] = set()
        while True:
            for e in list(nav._eventos):
                if e.get("method") == "Fetch.requestPaused":
                    rid = e["params"]["requestId"]
                    if rid not in vistos:
                        vistos.add(rid)
                        asyncio.create_task(uno(e["params"]))
            await asyncio.sleep(0.02)
    return asyncio.create_task(bucle())


async def persistencia(nav, base, datos) -> dict:
    """Revisión de #217: la región viva es EL MISMO nodo antes y después de cada búsqueda, y solo cambia su contenido.

    Tres búsquedas seguidas en la misma página (con resultados y una caída, sin coincidencias, todas fallan) y una cuarta
    idéntica a la primera. Tras cada una: identidad del nodo, sus atributos, su texto y las mutaciones que vio un
    `MutationObserver` (lo que recibe la tecnología de apoyo es un cambio de contenido, no un nodo nuevo)."""
    secuencia = ["con_resultados_y_una_caida", "sin_coincidencias", "todas_fallan", "con_resultados_y_una_caida"]
    consultas = ["Mortadelo", "Zzzz", "Flash", "Mortadelo y"]
    await nav.vista(ESCRITORIO, "light")
    nav._eventos.clear()
    tarea = await servir_secuencia(nav, datos["pagina"], [datos[k] for k in secuencia])
    try:
        await nav.ir(base + "/ui/descubrir", espera=1.0)
        inicial = await nav.js(OBSERVAR)
        pasos = []
        for k, q in zip(secuencia, consultas):
            await clic_en(nav, "input.series-search")
            await nav.cdp("Input.dispatchKeyEvent", type="keyDown", key="a", code="KeyA", modifiers=2, commands=["selectAll"])
            await nav.cdp("Input.dispatchKeyEvent", type="keyUp", key="a", code="KeyA", modifiers=2)
            await nav.cdp("Input.insertText", text=q)
            await asyncio.sleep(0.4 + 1.2)
            pasos.append({"fragmento": k, "consulta": q, **(await nav.js(ESTADO_REGION))})
    finally:
        tarea.cancel()
        await nav.cdp("Fetch.disable")
    return {"region_inicial": inicial, "busquedas": pasos}


async def main(base: str, fragmentos: Path, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    datos = json.loads(fragmentos.read_text(encoding="utf-8"))
    nav = capturar.Navegador()
    resultados = []
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "solo-lectura")
        await nav.cdp("Accessibility.enable")
        # Lo REAL del ensayo: con las fuentes apagadas, la página lo dice y no hay indicador.
        await nav.vista(ESCRITORIO, "light")
        await nav.ir(base + "/ui/descubrir", espera=0.8)
        real = await nav.js("""({indicador: !!document.querySelector('#buscando-descubrir'),
            texto: (document.querySelector('.caption') || {}).textContent})""")
        await nav.foto(salida / "0-ensayo-fuentes-apagadas.png", completa=False)
        # Casos: lenta (indicador a los ~400 ms), rápida (sin parpadeo) y las variantes de aspecto
        casos = [
            dict(nombre="1-lenta-escritorio-claro", vista=ESCRITORIO, tema="light", fragmento="con_resultados_y_una_caida", retraso=1.5),
            dict(nombre="2-rapida-sin-parpadeo", vista=ESCRITORIO, tema="light", fragmento="con_resultados_y_una_caida", retraso=0.0, foto=False),
            dict(nombre="3-escritorio-oscuro", vista=ESCRITORIO, tema="dark", fragmento="con_resultados_y_una_caida", retraso=0.5),
            dict(nombre="4-movil-oscuro", vista=MOVIL, tema="dark", fragmento="con_resultados_y_una_caida", retraso=0.5),
            dict(nombre="5-todas-fallan", vista=ESCRITORIO, tema="light", fragmento="todas_fallan", retraso=0.0),
            dict(nombre="6-sin-clave-y-una-caida", vista=ESCRITORIO, tema="light", fragmento="sin_clave_y_una_caida", retraso=0.0),
            dict(nombre="7-sin-coincidencias", vista=ESCRITORIO, tema="light", fragmento="sin_coincidencias", retraso=0.0),
        ]
        for c in casos:
            resultados.append(await escenario(nav, base, datos, salida, **c))
        persist = await persistencia(nav, base, datos)
    finally:
        await nav.cerrar()
    out = {"chrome": nav.version.get("Browser"), "ensayo_real_fuentes_apagadas": real, "persistencia_de_la_region": persist, "escenarios": resultados}
    (salida / "datos.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2)[:6000])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2]), Path(sys.argv[3])))
