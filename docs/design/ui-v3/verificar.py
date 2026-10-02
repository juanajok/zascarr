#!/usr/bin/env python3
# ruff: noqa: E501
"""Verificación en navegador real del shell de V3 (menú + contadores), contra el entorno de ensayo.

Herramienta de desarrollo, FUERA del paquete. Reutiliza el cliente CDP de
`docs/design/ui-baseline/capturar.py` (Chrome headless; nada que instalar). Las condiciones del
entorno (parar la BD, activar la contraseña, reiniciar la app) las prepara quien la ejecuta con
`docs/design/ui-baseline/ensayo.sh`; el procedimiento exacto está en `README.md`.

    python3 verificar.py CASO URL_BASE DIRECTORIO_DE_SALIDA

Casos:
    menu         menú de escritorio y móvil en las 8 pantallas: enlaces, aria-current, contadores,
                 «Más» (acceso a TODAS las secciones en móvil), desbordes y capturas
    teclado      orden de tabulación, enlace de salto, foco visible, «Más» con teclado
    sondeo       el fragmento se pide al cargar y se repite a los ~30 s
    red          fallo de red del fragmento (URL bloqueada): el menú sigue entero
    bd-caida     BD parada con la app EN MARCHA, ya con contadores cargados: el sondeo da 204 y no
                 borra nada
    degradado    app arrancada SIN BD: /estado funciona, el fragmento es 204, el menú intacto
    sesion       (con contraseña activada) entra, y con la sesión caducada el sondeo da 204 sin
                 redirigir ni cambiar la página; cerrar sesión funciona

Escribe `verificar-<caso>.json` con lo observado y capturas PNG.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("capturar", AQUI.parent / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
sys.modules["capturar"] = capturar
_spec.loader.exec_module(capturar)

FRAGMENTO = "/ui/_nav/estado"
PAGINAS = [("inicio", "/ui/"), ("revisar", "/ui/pendientes"), ("biblioteca", "/ui/biblioteca"),
           ("duplicados", "/ui/auditoria"), ("descubrir", "/ui/descubrir"),
           ("deseados", "/ui/wishlist"), ("estado", "/estado"), ("ajustes", "/ui/ajustes")]
SECUNDARIAS = ["/ui/biblioteca", "/ui/auditoria", "/ui/descubrir", "/ui/ajustes"]
ESCRITORIO = {"nombre": "escritorio", "w": 1280, "h": 800, "movil": False}
MOVIL = {"nombre": "movil", "w": 390, "h": 844, "movil": True}
MOVIL_MIN = {"nombre": "movil320", "w": 320, "h": 700, "movil": True}

# Estado del menú tal como lo ve el navegador (lo ve = renderizado, no solo en el DOM).
JS_MENU = """(() => {
  const visible = e => !!e && e.getClientRects().length > 0;
  const q = s => document.querySelector(s);
  const enlaces = [...document.querySelectorAll('.nav a, .nav summary')];
  return JSON.stringify({
    href_en_dom: [...document.querySelectorAll('.nav-grupo a')].map(a => a.getAttribute('href')),
    enlaces_visibles: enlaces.filter(visible).map(a => (a.getAttribute('href') || 'MAS')),
    actuales_en_dom: [...document.querySelectorAll('[aria-current]')].map(e => e.getAttribute('href')),
    actuales_visibles: [...document.querySelectorAll('[aria-current]')].filter(visible).map(e => e.getAttribute('href')),
    pendientes: q('#cnt-pendientes') && {texto: q('#cnt-pendientes').textContent, oculto: q('#cnt-pendientes').hidden},
    deseados: q('#cnt-deseados') && {texto: q('#cnt-deseados').textContent, oculto: q('#cnt-deseados').hidden},
    estado: q('#cnt-estado') && {oculto: q('#cnt-estado').hidden},
    scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
    ruta: location.pathname,
    barra_inferior: (() => { const n = q('.nav'); const r = n.getBoundingClientRect(); return {abajo: getComputedStyle(n).position === 'fixed', top: Math.round(r.top), alto: Math.round(r.height)}; })(),
  });
})()"""


def n_peticiones(nav, parte: str = "_nav/estado") -> int:
    return sum(1 for e in nav._eventos
               if e.get("method") == "Network.requestWillBeSent" and parte in e["params"]["request"]["url"])


def respuestas(nav, parte: str = "_nav/estado") -> list[dict]:
    return [{"estado": e["params"]["response"]["status"]}
            for e in nav._eventos
            if e.get("method") == "Network.responseReceived" and parte in e["params"]["response"]["url"]]


async def estado(nav) -> dict:
    return json.loads(await nav.js(JS_MENU))


async def pulsar(nav, tecla: str, codigo: str, repetir: int = 1) -> None:
    """Pulsación real: Enter y Espacio necesitan el carácter (`text`) para generar el `keypress` que
    activa un <summary>; sin él, un teclado sintético no abre un <details> aunque el navegador sí lo haría."""
    codigos = {"Tab": 9, "Enter": 13, " ": 32}
    texto = {"Enter": "\r", " ": " "}.get(tecla)
    for _ in range(repetir):
        extra = {"text": texto} if texto else {}
        await nav.cdp("Input.dispatchKeyEvent", type="keyDown", key=tecla, code=codigo,
                      windowsVirtualKeyCode=codigos[tecla], **extra)
        await nav.cdp("Input.dispatchKeyEvent", type="keyUp", key=tecla, code=codigo,
                      windowsVirtualKeyCode=codigos[tecla])
        await asyncio.sleep(0.05)


async def click(nav, selector: str) -> None:
    pos = await nav.js(f"""(() => {{ const e = document.querySelector({json.dumps(selector)});
        e.scrollIntoView({{block: 'center', behavior: 'instant'}}); const r = e.getBoundingClientRect();
        return {{x: r.x + r.width / 2, y: r.y + r.height / 2}} }})()""")
    for tipo in ("mousePressed", "mouseReleased"):
        await nav.cdp("Input.dispatchMouseEvent", type=tipo, x=pos["x"], y=pos["y"],
                      button="left", clickCount=1)
    await asyncio.sleep(0.8)


async def caso_menu(nav, base, salida, datos):
    por_vista = {}
    for v in (ESCRITORIO, MOVIL, MOVIL_MIN):
        await nav.vista(v, "light")
        filas = {}
        for clave, ruta in PAGINAS:
            await nav.ir(base + ruta, espera=1.2)
            filas[clave] = await estado(nav)
            if clave in ("revisar", "ajustes"):
                await nav.foto(salida / f"menu-{clave}--{v['nombre']}-{v['w']}x{v['h']}-claro.png", completa=False)
        por_vista[v["nombre"]] = filas
    datos["por_vista"] = por_vista

    # Tema oscuro del shell
    await nav.vista(ESCRITORIO, "dark")
    await nav.ir(base + "/ui/pendientes", espera=1.2)
    await nav.foto(salida / "menu-revisar--escritorio-1280x800-oscuro.png", completa=False)
    await nav.vista(MOVIL, "dark")
    await nav.ir(base + "/ui/pendientes", espera=1.2)
    await nav.foto(salida / "menu-revisar--movil-390x844-oscuro.png", completa=False)

    # «Más»: abrir y llegar a CADA sección secundaria desde la barra inferior, en 390 y 320 px.
    alcanzadas = {}
    for v in (MOVIL, MOVIL_MIN):
        await nav.vista(v, "light")
        for destino in SECUNDARIAS:
            await nav.ir(base + "/ui/pendientes", espera=0.8)
            await click(nav, ".nav-mas summary")
            abierto = await nav.js("document.querySelector('.nav-mas').open")
            if destino == SECUNDARIAS[0] and v is MOVIL:
                await nav.foto(salida / f"mas-abierto--{v['nombre']}-{v['w']}x{v['h']}-claro.png", completa=False)
            await click(nav, f'.nav-mas-panel a[href="{destino}"]')
            fin = await estado(nav)
            alcanzadas[f"{v['nombre']}:{destino}"] = {
                "abierto": abierto, "ruta_final": fin["ruta"], "visibles_aria_current": fin["actuales_visibles"],
                "mas_marcado": await nav.js("document.querySelector('.nav-mas').classList.contains('nav-mas-activa')")}
    datos["acceso_movil_a_secundarias"] = alcanzadas


async def caso_teclado(nav, base, salida, datos):
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/descubrir", espera=1.0)
    orden = []
    desc = """(() => { const e = document.activeElement; const r = e.getBoundingClientRect();
        const cs = getComputedStyle(e);
        return JSON.stringify({tag: e.tagName, clase: e.className, href: e.getAttribute('href'),
          texto: (e.textContent || '').trim().slice(0, 30), contorno: cs.outlineStyle + ' ' + cs.outlineWidth,
          visible: r.width > 0 && r.top >= 0 && r.top < innerHeight}) })()"""
    for i in range(1, 13):
        await pulsar(nav, "Tab", "Tab")
        orden.append(json.loads(await nav.js(desc)))
        if i == 1:
            await nav.foto(salida / "teclado-1-salto--escritorio-1280x800-claro.png", completa=False)
        if i == 4:
            await nav.foto(salida / "teclado-4-foco-en-menu--escritorio-1280x800-claro.png", completa=False)
    datos["orden_de_tabulacion"] = orden
    # El enlace de salto lleva el foco al contenido
    await nav.ir(base + "/ui/descubrir", espera=0.6)
    await pulsar(nav, "Tab", "Tab")
    await pulsar(nav, "Enter", "Enter")
    await asyncio.sleep(0.3)
    datos["tras_el_salto"] = json.loads(await nav.js(
        "JSON.stringify({id: document.activeElement.id, tag: document.activeElement.tagName, hash: location.hash})"))

    # Móvil: «Más» con teclado (Enter abre/cierra el details nativo)
    await nav.vista(MOVIL, "light")
    await nav.ir(base + "/ui/descubrir", espera=0.8)
    await nav.js("document.querySelector('.nav-mas summary').focus()")
    antes = await nav.js("document.querySelector('.nav-mas').open")
    await pulsar(nav, "Enter", "Enter")
    despues = await nav.js("document.querySelector('.nav-mas').open")
    await nav.foto(salida / "teclado-mas--movil-390x844-claro.png", completa=False)
    await pulsar(nav, "Enter", "Enter")
    cerrado = await nav.js("document.querySelector('.nav-mas').open")
    await pulsar(nav, " ", "Space")
    con_espacio = await nav.js("document.querySelector('.nav-mas').open")
    # Con el panel abierto, Tab llega a sus enlaces y el foco se ve
    await pulsar(nav, "Tab", "Tab")
    en_panel = json.loads(await nav.js("""JSON.stringify({href: document.activeElement.getAttribute('href'),
        dentro: !!document.activeElement.closest('.nav-mas-panel')})"""))
    datos["mas_con_teclado"] = {"antes": antes, "tras_enter": despues, "tras_otro_enter": cerrado,
                                "tras_espacio": con_espacio, "tab_con_el_panel_abierto": en_panel}


async def caso_sondeo(nav, base, salida, datos):
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/descubrir", espera=2.0)
    datos["al_cargar"] = {"peticiones": n_peticiones(nav), "menu": await estado(nav)}
    await asyncio.sleep(33)
    datos["tras_35_s"] = {"peticiones": n_peticiones(nav), "respuestas": respuestas(nav)}


async def caso_red(nav, base, salida, datos):
    await nav.vista(ESCRITORIO, "light")
    await nav.cdp("Network.setBlockedURLs", urls=["*_nav/estado*"])
    await nav.ir(base + "/ui/descubrir", espera=2.0)
    datos["con_el_fragmento_bloqueado"] = {
        "menu": await estado(nav), "peticiones_intentadas": n_peticiones(nav),
        "errores_de_consola_de_pagina": await nav.js("window.__errores || null")}
    await nav.foto(salida / "red-fragmento-bloqueado--escritorio-1280x800-claro.png", completa=False)
    await nav.cdp("Network.setBlockedURLs", urls=[])


async def caso_bd_caida(nav, base, salida, datos):
    """Se ejecuta con la BD PARADA DESPUÉS de haber cargado los contadores: lo prepara el operador
    (ver README). Aquí se carga la página ANTES (con BD), se espera a que el operador pare la BD y se
    mide el siguiente sondeo."""
    import os
    import subprocess
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/descubrir", espera=2.0)
    antes = await estado(nav)
    datos["antes_de_parar_la_bd"] = antes
    ensayo = AQUI.parent / "ui-baseline" / "ensayo.sh"
    subprocess.run([str(ensayo), "dc", "stop", "postgres"], env=os.environ, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    n0 = n_peticiones(nav)
    await asyncio.sleep(33)
    datos["tras_el_siguiente_sondeo_con_la_bd_caida"] = {
        "peticiones_nuevas": n_peticiones(nav) - n0, "respuestas": respuestas(nav)[-1:], "menu": await estado(nav),
        "la_pagina_sigue_en": await nav.js("location.pathname")}
    await nav.foto(salida / "bd-caida-sondeo--escritorio-1280x800-claro.png", completa=False)
    datos["contadores_conservados"] = (antes["pendientes"] == datos["tras_el_siguiente_sondeo_con_la_bd_caida"]["menu"]["pendientes"])
    subprocess.run([str(ensayo), "dc", "start", "postgres"], env=os.environ, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def caso_degradado(nav, base, salida, datos):
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/estado", espera=2.5)
    datos["estado_con_arranque_degradado"] = await estado(nav)
    datos["texto_de_estado"] = (await nav.js("document.querySelector('main').innerText.slice(0, 200)"))
    datos["peticiones_al_fragmento"] = n_peticiones(nav)
    datos["respuestas_al_fragmento"] = respuestas(nav)
    await nav.foto(salida / "degradado-estado--escritorio-1280x800-claro.png", completa=False)
    await nav.vista(MOVIL, "light")
    await nav.ir(base + "/estado", espera=2.0)
    datos["estado_degradado_movil"] = await estado(nav)
    await nav.foto(salida / "degradado-estado--movil-390x844-claro.png", completa=False)


async def caso_sesion(nav, base, salida, datos, clave: str):
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/pendientes", espera=1.0)
    datos["sin_sesion_redirige_a"] = await nav.js("location.pathname + location.search")
    await nav.foto(salida / "sesion-login--escritorio-1280x800-claro.png", completa=False)
    datos["pagina_de_login_con_menu"] = await nav.js("!!document.querySelector('.nav')")
    await nav.js(f"document.querySelector('input[name=password]').value = {json.dumps(clave)}")
    await click(nav, 'button[type="submit"]')
    await asyncio.sleep(1.5)
    datos["tras_entrar"] = {"ruta": await nav.js("location.pathname"), "menu": await estado(nav)}
    datos["boton_cerrar_sesion"] = await nav.js("!!document.querySelector('.side-foot .btn-logout')")
    await nav.foto(salida / "sesion-dentro--escritorio-1280x800-claro.png", completa=False)

    # Sesión caducada: se borran las cookies y se espera al siguiente sondeo
    n0 = n_peticiones(nav)
    antes = await estado(nav)
    ruta = await nav.js("location.pathname")
    await nav.cdp("Network.clearBrowserCookies")
    await asyncio.sleep(33)
    despues = await estado(nav)
    datos["sesion_caducada"] = {
        "peticiones_nuevas": n_peticiones(nav) - n0, "respuestas": respuestas(nav)[-1:],
        "la_pagina_no_cambio": ruta == despues["ruta"], "ruta": despues["ruta"],
        "enlaces_intactos": antes["href_en_dom"] == despues["href_en_dom"],
        "contadores_conservados": antes["pendientes"] == despues["pendientes"],
        "texto_de_la_pagina_contiene_login": await nav.js("document.body.innerText.toLowerCase().includes('contraseña') && !!document.querySelector('form[action=\"/login\"]')")}
    await nav.foto(salida / "sesion-caducada--escritorio-1280x800-claro.png", completa=False)

    # Y una navegación real con la sesión caducada sí lleva a /login (A6 intacto)
    await nav.ir(base + "/ui/pendientes", espera=1.0)
    datos["navegar_sin_sesion"] = await nav.js("location.pathname")

    # Cerrar sesión funciona: se vuelve a entrar y se sale con el botón
    await nav.js(f"document.querySelector('input[name=password]').value = {json.dumps(clave)}")
    await click(nav, 'button[type="submit"]')
    await asyncio.sleep(1.2)
    await click(nav, ".side-foot .btn-logout")
    await asyncio.sleep(1.2)
    datos["tras_cerrar_sesion"] = await nav.js("location.pathname")


async def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    caso, base, salida = sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3])
    clave = sys.argv[4] if len(sys.argv) > 4 else ""
    salida.mkdir(parents=True, exist_ok=True)
    nav = capturar.Navegador()
    datos: dict = {"caso": caso, "base": base}
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "verificar")
        datos["navegador"] = nav.version.get("Browser")
        fn = {"menu": caso_menu, "teclado": caso_teclado, "sondeo": caso_sondeo, "red": caso_red,
              "bd-caida": caso_bd_caida, "degradado": caso_degradado}.get(caso)
        if caso == "sesion":
            await caso_sesion(nav, base, salida, datos, clave)
        elif fn:
            await fn(nav, base, salida, datos)
        else:
            sys.exit(f"caso desconocido: {caso}")
    finally:
        await nav.cerrar()
        (salida / f"verificar-{caso}.json").write_text(
            json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(datos, ensure_ascii=False)[:3000])


if __name__ == "__main__":
    asyncio.run(main())
