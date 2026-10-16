#!/usr/bin/env python3
# ruff: noqa: E501
"""Evidencia de U19 (#206) en navegador real: Chrome headless por CDP contra el ensayo aislado, con EVENTOS REALES de teclado.

Reutiliza `Navegador` de `../ui-baseline/capturar.py`. Las fuentes del ensayo están APAGADAS a propósito y no se encienden: el
fragmento de `POST .../asistente/buscar` lo genera la ruta real con `buscar_a_ritmo` sustituido (`fragmentos_u19.py`) y se sirve con
`Fetch.fulfillRequest`; todo lo demás (elegir, vista previa, alta, revisión, vinculación, lectura del resultado) lo atiende el
servidor del ensayo con su base de datos real. ESCRIBE en el ensayo (crea una serie, vincula archivos): es desechable.

    python3 docs/design/ui-u19/capturar_u19.py http://127.0.0.1:18000 fragmentos.json docs/design/ui-u19
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("capturar", Path(__file__).resolve().parents[1] / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capturar)

ESCRITORIO = {"nombre": "escritorio", "w": 1280, "h": 900, "movil": False}
MOVIL = {"nombre": "movil", "w": 375, "h": 812, "movil": True}
A = "/ui/pendientes/carpetas/asistente?clave=_Unsorted"
TECLAS = {"Tab": 9, "Enter": 13, "ArrowDown": 40}


async def tecla(nav, nombre: str) -> None:
    vk = TECLAS[nombre]
    extra = {"text": "\r"} if nombre == "Enter" else {}
    await nav.cdp("Input.dispatchKeyEvent", type="keyDown", key=nombre, code=nombre, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk, **extra)
    await nav.cdp("Input.dispatchKeyEvent", type="keyUp", key=nombre, code=nombre, windowsVirtualKeyCode=vk, nativeVirtualKeyCode=vk)


async def escribir(nav, texto: str) -> None:
    for ch in texto:
        await nav.cdp("Input.dispatchKeyEvent", type="keyDown", key=ch, text=ch)
        await nav.cdp("Input.dispatchKeyEvent", type="keyUp", key=ch)


async def tab_hasta(nav, selector: str, maximo: int = 120) -> int:
    """Pulsa Tab (evento real) hasta que el foco está en `selector`. Devuelve cuántas veces; -1 si no llegó."""
    for n in range(1, maximo + 1):
        await tecla(nav, "Tab")
        if await nav.js(f"document.activeElement && document.activeElement.matches({selector!r})"):
            return n
    return -1


async def pausa(s: float = 0.9) -> None:
    await asyncio.sleep(s)


async def servir_buscar(nav, fragmento: str) -> asyncio.Task:
    await nav.cdp("Fetch.enable", patterns=[{"urlPattern": "*/asistente/buscar", "requestStage": "Request"}])
    cab = [{"name": "Content-Type", "value": "text/html; charset=utf-8"}, {"name": "Cache-Control", "value": "no-store"}]

    async def bucle():
        vistos: set[str] = set()
        while True:
            for e in list(nav._eventos):
                if e.get("method") == "Fetch.requestPaused":
                    rid = e["params"]["requestId"]
                    if rid not in vistos:
                        vistos.add(rid)
                        await nav.cdp("Fetch.fulfillRequest", requestId=rid, responseCode=200, responseHeaders=cab,
                                      body=base64.b64encode(fragmento.encode()).decode())
            await asyncio.sleep(0.02)
    return asyncio.create_task(bucle())


PASOS_JS = r"""(() => { const nav = document.querySelector('nav.pasos-asistente'); if (!nav) return null;
  return [...nav.querySelectorAll('li')].map(li => ({texto: li.textContent.replace(/\s+/g, ' ').trim(), clase: li.className,
    aria_current: li.getAttribute('aria-current')})); })()"""


async def pasos(nav) -> dict:
    lista = await nav.js(PASOS_JS)
    # lo que expone el árbol de accesibilidad de Chromium para el paso actual
    obj = (await nav.cdp("Runtime.evaluate", expression="document.querySelector('nav.pasos-asistente li[aria-current=step]')"))["result"]
    ax = None
    if obj.get("objectId"):
        nodos = (await nav.cdp("Accessibility.getPartialAXTree", objectId=obj["objectId"], fetchRelatives=False))["nodes"]
        ax = {p["name"]: p["value"].get("value") for p in nodos[0].get("properties", [])} if nodos else None
    return {"pasos": lista, "arbol_de_accesibilidad_del_actual": ax}


def texto(nav_js_resultado) -> str:
    return re.sub(r"\s+", " ", nav_js_resultado or "").strip()


async def visible(nav) -> str:
    return texto(await nav.js("document.querySelector('main').innerText"))


async def main(base: str, fragmentos: Path, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    datos = json.loads(fragmentos.read_text(encoding="utf-8"))
    nav = capturar.Navegador()
    informe: dict = {"pasos_de_la_prueba": []}

    def anotar(clave: str, **valores) -> None:
        informe["pasos_de_la_prueba"].append({"paso": clave, **valores})
        print(clave, json.dumps(valores, ensure_ascii=False)[:300])

    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "principal")
        await nav.cdp("Accessibility.enable")
        informe["chrome"] = nav.version.get("Browser")
        await nav.vista(ESCRITORIO, "light")

        # ── 1. Selección local directa, solo con el teclado ────────────────────────────────────
        await nav.ir(base + A, espera=0.8)
        anotar("1a-pasos-en-A", **await pasos(nav))
        n = await tab_hasta(nav, "#asistente-local-q")
        anotar("1b-tabs-hasta-el-buscador-local", tabs=n)
        await escribir(nav, "Mundo")
        await tecla(nav, "Enter")
        await pausa()
        t = await nav.js("document.querySelector('#asistente-locales').innerText")
        anotar("1c-resultados-locales", texto=texto(t), preseleccion=await nav.js("!!document.querySelector('#asistente-locales [checked],#asistente-locales [selected]')"))
        await nav.foto(salida / "1-locales.png", completa=False)
        m = await tab_hasta(nav, "#asistente-locales a")
        anotar("1d-tabs-hasta-el-enlace", tabs=m)
        await tecla(nav, "Enter")
        await pausa(1.5)
        v = await visible(nav)
        anotar("1e-revision", url=await nav.js("location.pathname + location.search"),
               banner="Vas a preparar los archivos de esta carpeta para" in v and "no vincula nada hasta que lo confirmes" in v,
               pasos=(await pasos(nav))["pasos"])
        await nav.foto(salida / "2-revision-desde-serie-local.png", completa=False)

        # ── 2. Candidata de fuente (simulada) → vista previa → alta, con el teclado ─────────────
        tarea = await servir_buscar(nav, datos["buscar"])
        try:
            await nav.ir(base + A, espera=0.8)
            await nav.js("document.querySelector('#asistente-consulta').focus()")
            await tecla(nav, "Enter")                                   # envía la búsqueda (simulada)
            await pausa(1.2)
            r = await nav.js("document.querySelector('#asistente-resultados').innerText")
            anotar("2a-resultados-simulados", texto=texto(r)[:400], parecidas_bajo_la_candidata="series que ya tienes y se parecen" in r.lower())
            await nav.foto(salida / "3-resultados-con-parecidas.png", completa=False)
            # la PRIMERA candidata coincide con una serie que ya tienes: elegir su tradición por teclado lleva a decidir («Es esta»)
            await nav.js("[...document.querySelectorAll('#asistente-resultados select')][0].focus()")
            await escribir(nav, "Grapa")
            await tecla(nav, "Tab")
            await tecla(nav, "Enter")
            await pausa(1.5)
            bloque = "(([...document.querySelectorAll('.asistente-paso')].find(e => e.innerText.includes('Elección anotada'))) || null)"
            ambig = await nav.js(f"({bloque} || {{innerText: ''}}).innerText")
            anotar("2a2-decidir-entre-parecidas", texto=texto(ambig)[:300], ofrece_es_esta="Es esta" in ambig, ofrece_crear_otra="Es distinta: crear otra" in ambig)
            await nav.js(f"{bloque}.querySelector('input[name=decision][value=reutilizar]').form.querySelector('button').focus()")
            await tecla(nav, "Enter")                                   # «Es esta»
            await pausa(1.5)
            tras = await nav.js(f"({bloque} || {{innerText: ''}}).innerText")
            anotar("2a3-es-esta", texto=texto(tras)[-420:], decision_tomada="Se usará la serie existente que elegiste" in tras)
            await nav.foto(salida / "3b-es-esta.png", completa=False)
            enlace_decision = await nav.js(f"[...{bloque}.querySelectorAll('a')].find(a => a.textContent.includes('enlace a esta vista previa')).href")
            anotar("2a4-el-enlace-lleva-la-decision", decision="decision=reutilizar" in enlace_decision, serie_id="serie_id=" in enlace_decision, consulta="consulta=" in enlace_decision)
            await nav.ir(enlace_decision, espera=1.0)                   # recargar por el enlace que ofrece la pantalla
            vd = await visible(nav)
            anotar("2a5-reconstruida-con-la-decision", conserva="Se usará la serie existente que elegiste" in vd, vuelve_a_preguntar="Es esta" in vd)
            await nav.foto(salida / "3c-decision-conservada.png", completa=False)
            await nav.ir(base + A, espera=0.8)
            await nav.js("document.querySelector('#asistente-consulta').focus()")
            await tecla(nav, "Enter")
            await pausa(1.2)
            # la segunda candidata (Tebeosfera): su selector de tradición, por teclado
            await nav.js("[...document.querySelectorAll('#asistente-resultados select')][1].focus()")
            await escribir(nav, "Tebeo")
            sel = await nav.js("[...document.querySelectorAll('#asistente-resultados select')][1].value")
            await tecla(nav, "Tab")
            await tecla(nav, "Enter")                                   # «Elegir esta serie»
            await pausa(1.5)
        finally:
            tarea.cancel()
            await nav.cdp("Fetch.disable")
        vp = await nav.js("(([...document.querySelectorAll('.asistente-paso')].find(e => e.innerText.includes('Elección anotada'))) || {innerText: ''}).innerText")
        anotar("2b-tras-elegir", tradicion_elegida_por_teclado=sel, texto=texto(vp)[:700],
               callejon="todavía no está disponible" in vp, ofrece_crear="Crear serie vacía" in vp)
        await nav.foto(salida / "4-vista-previa-tras-elegir.png", completa=False)
        series_antes = await nav.js("fetch('/ui/biblioteca').then(r => r.text()).then(t => (t.match(/Cobalto Integral/g) || []).length)")
        anotar("2c-la-serie-aun-no-existe", apariciones_en_la_biblioteca=series_antes)

        # recargar la vista previa por su enlace (GET): la elección se conserva
        enlace = await nav.js("[...document.querySelectorAll('a')].find(a => a.textContent.includes('enlace a esta vista previa')).href")
        await nav.ir(enlace, espera=1.0)
        v = await visible(nav)
        anotar("2d-vista-previa-reconstruida", url=enlace.split("?")[0].replace(base, ""), ofrece_crear="Crear serie vacía" in v,
               pasos=(await pasos(nav))["pasos"], encabezado=v[:120])
        await nav.foto(salida / "5-vista-previa-recargada.png", completa=False)

        # crear la serie (el único efecto de esta pantalla) con el teclado
        k = await tab_hasta(nav, "form[hx-post='/ui/descubrir/crear'] button[type=submit]")
        await tecla(nav, "Enter")
        await pausa(1.5)
        r2 = await nav.js("document.querySelector('.alta-paso').innerText")
        anotar("2e-alta-creada", tabs=k, texto=texto(r2)[:400])
        await nav.foto(salida / "6-alta-creada.png", completa=False)
        # volver al estado del alta por el ENLACE que ofrece el resultado (no se compone ninguna URL)
        vinculo = await nav.js("(() => { const a = [...document.querySelectorAll('a')].find(a => a.textContent.includes('enlace al estado de esta alta')); return a ? a.href : null; })()")
        assert vinculo, "el resultado del alta no ofrece el enlace al estado de la alta"
        await nav.ir(vinculo, espera=0.8)
        v = await visible(nav)
        anotar("2f-alta-reconstruida", enlace_ofrecido=vinculo.replace(base, "")[:80], texto=v[:300], deshacer="Deshacer" in v, vacia="vacía" in v, pasos=(await pasos(nav))["pasos"])
        await nav.foto(salida / "7-alta-reconstruida.png", completa=False)

        # ── 3. Revisión, vinculación y lectura del resultado ───────────────────────────────────
        k = await tab_hasta(nav, "a.btn")
        await tecla(nav, "Enter")                                       # «Revisar los archivos de esta carpeta»
        await pausa(1.5)
        anotar("3a-revision-de-la-serie-nueva", url=await nav.js("location.search"), pasos=(await pasos(nav))["pasos"])
        await nav.js("[...document.querySelectorAll('button')].find(b => b.textContent.includes('Marcar todos')).focus()")
        await tecla(nav, "Enter")
        await pausa(1.5)
        boton = await nav.js("(() => { const b = document.querySelector('form.vinculacion-confirmar button'); return b ? b.textContent.trim() : null; })()")
        anotar("3b-marcado", boton_de_confirmar=boton)
        await nav.foto(salida / "8-revision-marcada.png", completa=False)
        await nav.js("document.querySelector('form.vinculacion-confirmar button').focus()")
        await tecla(nav, "Enter")                                       # «Vincular N archivos»: el segundo efecto
        await pausa(2.0)
        x = await visible(nav)
        permalink = await nav.js("(() => { const a = [...document.querySelectorAll('a')].find(a => a.textContent.includes('enlace a este resultado')); return a ? a.href : null; })()")
        anotar("3c-resultado", titulo=x[:140], hay_enlace_al_resultado=bool(permalink), pasos=(await pasos(nav))["pasos"])
        await nav.foto(salida / "9-resultado.png", completa=False)
        assert permalink, "el resultado no ofrece el enlace a sí mismo"

        await nav.ir(permalink, espera=1.0)                              # «volver»: se lee el comprobante, no se ejecuta de nuevo
        x2 = await visible(nav)
        anotar("3d-lectura-valida", url=permalink.split("?")[0].replace(base, ""), repetida="ya se había aplicado" in x2 or "resultado guardado" in x2,
               mismo_titulo=x2[:140], pasos=(await pasos(nav))["pasos"])
        await nav.foto(salida / "10-lectura-valida.png", completa=False)
        await nav.cdp("Page.reload")
        await pausa(1.2)
        anotar("3e-recargar", sigue=("resultado guardado" in await visible(nav)))
        mala = permalink.split("ref=")[0] + "ref=esto-no-es-una-referencia"
        await nav.ir(mala, espera=0.8)
        v = await visible(nav)
        anotar("3g-referencia-no-valida", texto=v[:200], sin_pistas="vencido" not in v and "No se encuentra" not in v)
        await nav.foto(salida / "11-referencia-no-valida.png", completa=False)

        # ── 4. Aspecto: móvil y oscuro ─────────────────────────────────────────────────────────
        await nav.vista(MOVIL, "dark")
        await nav.ir(base + A, espera=0.8)
        anotar("4a-movil-oscuro", scroll_horizontal=await nav.js("document.documentElement.scrollWidth > document.documentElement.clientWidth"),
               pasos=(await pasos(nav))["pasos"])
        await nav.foto(salida / "12-movil-oscuro.png", completa=False)
    finally:
        await nav.cerrar()
    (salida / "datos.json").write_text(json.dumps(informe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2]), Path(sys.argv[3])))
