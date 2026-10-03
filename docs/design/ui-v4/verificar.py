#!/usr/bin/env python3
# ruff: noqa: E501
"""Verificación en navegador real del Inicio guiado de V4, contra el entorno de ensayo.

Herramienta de desarrollo, FUERA del paquete. Reutiliza el cliente CDP de
`docs/design/ui-baseline/capturar.py` (Chrome headless; nada que instalar).

    python3 verificar.py CASO URL_BASE DIRECTORIO_DE_SALIDA

Casos:
    estados   el Inicio con los datos sintéticos tal cual los siembra `sembrar.py` (catálogo ya
              existente, informe de duplicados, 6 por revisar, 5 deseados): escritorio, 390, 320 px,
              claro y oscuro; pasos, botones primarios, cifras y desbordes
    flujo     el recorrido real de una instalación nueva, con la interfaz: la base de datos se vacía
              (los tebeos siguen en el disco), y se pasa por SIN registrar → informe de duplicados →
              biblioteca registrada → todo clasificado → sin tebeos en el disco. Cada paso se mide
              y se captura. DESTRUCTIVO: solo corre contra el entorno de ensayo (comprueba antes que
              contiene los datos sintéticos) y vacía SU base de datos con `ensayo.sh dc exec`
    busqueda  «Buscar una serie» del Inicio: llega a /ui/descubrir?q=… con la caja rellena y la
              petición de búsqueda lanzada al cargar

Escribe `verificar-<caso>.json` con lo observado y capturas PNG.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("capturar", AQUI.parent / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
sys.modules["capturar"] = capturar
_spec.loader.exec_module(capturar)

ENSAYO = AQUI.parent / "ui-baseline" / "ensayo.sh"
ESCRITORIO = {"nombre": "escritorio", "w": 1280, "h": 800, "movil": False}
MOVIL = {"nombre": "movil", "w": 390, "h": 844, "movil": True}
MOVIL_MIN = {"nombre": "movil320", "w": 320, "h": 700, "movil": True}

JS_INICIO = """(() => {
  const q = s => document.querySelector(s);
  const main = q('main');
  return JSON.stringify({
    ruta: location.pathname,
    subtitulo: q('.subtitle') && q('.subtitle').innerText,
    encabezados: [...document.querySelectorAll('h1')].map(h => h.innerText),
    pasos: [...document.querySelectorAll('.step')].map(li => ({
      clase: li.className.replace('step ', ''),
      titulo: li.querySelector('h3').innerText.trim(),
      detalle: li.querySelector('p').innerText,
      boton: li.querySelector('a.btn') && li.querySelector('a.btn').innerText,
      primario: !!li.querySelector('a.btn.primary')})),
    plegado: !!q('details.pasos-plegados'),
    botones_primarios: document.querySelectorAll('main .btn.primary').length,
    hay_metricas: !!q('.metrics-grid'),
    metricas: [...document.querySelectorAll('.metric-card')].map(c => c.innerText.replace(/\\n+/g, ' · ')),
    porcentajes_en_la_pagina: (main.innerText.match(/\\d+\\s?%/g) || []),
    desborde: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth,
  });
})()"""


JS_PRINCIPAL = """(() => {
  const a = document.querySelector('main a.btn.primary');
  const b = document.querySelector('main .search-form button');
  const fondo = e => e && getComputedStyle(e).backgroundColor;
  if (!a) return JSON.stringify({hay_principal: false, fondo_buscar: fondo(b)});
  const r = a.getBoundingClientRect(), cs = getComputedStyle(a);
  return JSON.stringify({
    hay_principal: true, href: a.getAttribute('href'), texto: a.innerText.trim(),
    visible: a.getClientRects().length > 0 && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0,
    dentro_de_details_cerrado: !!a.closest('details:not([open])'),
    alto: Math.round(r.height), fondo_principal: fondo(a), fondo_buscar: fondo(b),
    buscar_distinto_del_principal: fondo(a) !== fondo(b),
  });
})()"""


async def foto_de_inicio(nav, base, ruta: Path) -> None:
    """Fotografía SOLO el Inicio: vuelve a `/ui/` y comprueba la ruta y el <h1> antes de guardar.
    `comprobar_principal` termina en el destino del botón (Por revisar, Descubrir…): sin esta
    comprobación una captura con nombre de Inicio podía ser de otra pantalla."""
    await nav.ir(base + "/ui/", espera=0.8)
    pagina = json.loads(await nav.js("""JSON.stringify({ruta: location.pathname,
        h1: (document.querySelector('h1') || {}).textContent})"""))
    if pagina["ruta"] != "/ui/" or (pagina["h1"] or "").strip().lower() != "inicio":
        raise SystemExit(f"no es el Inicio ({pagina}); no guardo {ruta.name}")
    await nav.foto(ruta)


async def tab(nav) -> None:
    for tipo in ("keyDown", "keyUp"):
        await nav.cdp("Input.dispatchKeyEvent", type=tipo, key="Tab", code="Tab", windowsVirtualKeyCode=9)
    await asyncio.sleep(0.03)


async def comprobar_principal(nav, base, activar: bool = True) -> dict:
    """La acción recomendada no solo existe en el HTML: se VE, se alcanza con el teclado y lleva
    donde dice. Contar `.btn.primary` no acredita nada de eso (revisión de la PR #70)."""
    await nav.ir(base + "/ui/", espera=0.8)
    datos = json.loads(await nav.js(JS_PRINCIPAL))
    if not datos.get("hay_principal"):
        return datos
    await nav.js("(() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); })()")
    pasos_de_tab = 0
    for pasos_de_tab in range(1, 61):
        await tab(nav)
        foco = json.loads(await nav.js("""JSON.stringify((() => { const e = document.activeElement;
            return {href: e && e.getAttribute && e.getAttribute('href'), clase: e && e.className} })())"""))
        if foco["href"] == datos["href"] and "primary" in (foco["clase"] or ""):
            datos["alcanzable_con_tab_en"] = pasos_de_tab
            break
    else:
        datos["alcanzable_con_tab_en"] = None
    if activar and datos["alcanzable_con_tab_en"]:
        for tipo, extra in (("keyDown", {"text": "\r"}), ("keyUp", {})):
            await nav.cdp("Input.dispatchKeyEvent", type=tipo, key="Enter", code="Enter",
                          windowsVirtualKeyCode=13, **extra)
        await asyncio.sleep(1.2)
        datos["tras_enter_va_a"] = await nav.js("location.pathname")
    return datos


async def inicio(nav, base) -> dict:
    await nav.ir(base + "/ui/", espera=1.0)
    return json.loads(await nav.js(JS_INICIO))


def sql(consulta: str) -> str:
    """Solo contra el stack de ensayo: `ensayo.sh dc` repite las comprobaciones de aislamiento."""
    r = subprocess.run(
        [str(ENSAYO), "dc", "exec", "-T", "postgres", "sh", "-c",
         'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -At'],
        input=consulta, text=True, capture_output=True, env=os.environ, check=True)
    return r.stdout.strip()


async def foto_en(nav, salida: Path, nombre: str, vistas=(ESCRITORIO,), tema="light") -> None:
    for v in vistas:
        await nav.vista(v, tema)
        await nav.ir(await nav.js("location.href"), espera=0.6)
        await nav.foto(salida / f"{nombre}--{v['nombre']}-{v['w']}x{v['h']}-{'claro' if tema == 'light' else 'oscuro'}.png")


async def caso_estados(nav, base, salida, datos):
    # «Sigues N series» cuenta SERIES; el contador del menú sigue contando PETICIONES de Deseados.
    datos["deseados_en_la_bd"] = {
        "peticiones": int(sql("SELECT count(*) FROM wishlist WHERE status <> 'retirado';")),
        "series_distintas": int(sql(
            "SELECT count(DISTINCT coalesce(w.series_id, i.series_id)) FROM wishlist w "
            "LEFT JOIN issues i ON i.id = w.issue_id WHERE w.status <> 'retirado';")),
    }
    for v in (ESCRITORIO, MOVIL, MOVIL_MIN):
        await nav.vista(v, "light")
        datos[f"inicio_{v['nombre']}"] = await inicio(nav, base)
        datos[f"inicio_{v['nombre']}"]["accion_principal"] = await comprobar_principal(nav, base)
        await foto_de_inicio(nav, base, salida / f"inicio-catalogo-previo--{v['nombre']}-{v['w']}x{v['h']}-claro.png")
    await nav.ir(base + "/ui/", espera=1.0)   # la comprobación del botón principal termina en otra página
    datos["menu_deseados"] = await nav.js("document.querySelector('#cnt-deseados').textContent")
    datos["texto_del_paso_series"] = await nav.js(
        "[...document.querySelectorAll('.step h3')].map(h => h.innerText).find(t => t.startsWith('Sigues'))")
    await nav.vista(ESCRITORIO, "dark")
    await foto_de_inicio(nav, base, salida / "inicio-catalogo-previo--escritorio-1280x800-oscuro.png")


async def caso_flujo(nav, base, salida, datos):
    await capturar.comprobar_entorno(nav, base, "principal")   # exige los datos sintéticos
    await nav.vista(ESCRITORIO, "light")

    # 0. Instalación nueva: BD vacía, los tebeos siguen en el disco.
    datos["vaciado"] = sql("""
        TRUNCATE series, issues, files, import_runs, wishlist, legal_acknowledgments RESTART IDENTITY CASCADE;
        UPDATE runtime_settings SET values = values - '_library_adoption_done';
        SELECT (SELECT count(*) FROM series) || ' series, ' || (SELECT count(*) FROM files) || ' ficheros';""")

    async def paso(clave, nombre, vistas=(ESCRITORIO,)):
        estado = await inicio(nav, base)
        datos[clave] = estado
        estado["accion_principal"] = await comprobar_principal(nav, base)
        for v in vistas:
            await nav.vista(v, "light")
            await foto_de_inicio(nav, base, salida / f"flujo-{nombre}--{v['nombre']}-{v['w']}x{v['h']}-claro.png")
        await nav.vista(ESCRITORIO, "light")
        return estado

    await paso("1_tebeos_en_el_disco_sin_registrar", "1-sin-registrar", (ESCRITORIO, MOVIL))

    # 2. El botón principal lleva a la pantalla donde se puede mirar el disco y registrar.
    await nav.ir(base + "/ui/", espera=0.8)
    await capturar_click(nav, "a.btn.primary")
    datos["2_el_boton_principal_lleva_a"] = await nav.js("location.pathname")
    await capturar_click(nav, 'form[hx-post="/ui/auditoria/analizar"] button')
    await asyncio.sleep(4)
    datos["2_informe_generado"] = bool(await nav.js("!!document.querySelector('#informe .audit-block')"))
    await paso("2_con_informe_sin_registrar", "2-con-informe-sin-registrar")

    # 3. Se registra la biblioteca (acción explícita).
    await nav.ir(base + "/ui/auditoria", espera=1.0)
    await capturar_click(nav, 'button[hx-post="/ui/auditoria/adoptar"], form[hx-post="/ui/auditoria/adoptar"] button')
    await asyncio.sleep(6)
    datos["3_adopcion_ejecutada"] = (await nav.js("document.body.innerText")).count("registrad") > 0
    await paso("3_biblioteca_registrada", "3-registrada", (ESCRITORIO, MOVIL, MOVIL_MIN))

    # 4. Se descarta lo que queda por revisar (la misma acción que ofrece «Por revisar»).
    datos["4_descartados"] = sql("UPDATE files SET review_dismissed = true WHERE issue_id IS NULL RETURNING 1;").count("1")
    await paso("4_todo_clasificado", "4-todo-listo", (ESCRITORIO, MOVIL))

    # 5. Sin tebeos en el disco ni registrados: la pantalla de «aún no hay nada», sin ceros.
    subprocess.run([str(ENSAYO), "dc", "exec", "-T", "zascarr", "sh", "-c",
                    "find /media/library -type f \\( -name '*.cbz' -o -name '*.cbr' \\) -delete"],
                   env=os.environ, check=True, capture_output=True)
    sql("TRUNCATE series, issues, files, import_runs, wishlist RESTART IDENTITY CASCADE; "
        "UPDATE runtime_settings SET values = values - '_library_adoption_done';")
    await paso("5_instalacion_vacia", "5-vacia", (ESCRITORIO, MOVIL))


async def capturar_click(nav, selector: str) -> None:
    pos = await nav.js(f"""(() => {{ const e = document.querySelector({json.dumps(selector)});
        if (!e) return null; e.scrollIntoView({{block: 'center', behavior: 'instant'}});
        const r = e.getBoundingClientRect(); return {{x: r.x + r.width / 2, y: r.y + r.height / 2}} }})()""")
    if pos is None:
        raise SystemExit(f"no encuentro {selector} en {await nav.js('location.pathname')}")
    for tipo in ("mousePressed", "mouseReleased"):
        await nav.cdp("Input.dispatchMouseEvent", type=tipo, x=pos["x"], y=pos["y"], button="left", clickCount=1)
    await asyncio.sleep(0.9)


async def caso_busqueda(nav, base, salida, datos):
    await nav.vista(ESCRITORIO, "light")
    await nav.ir(base + "/ui/", espera=0.8)
    n0 = sum(1 for e in nav._eventos if e.get("method") == "Network.requestWillBeSent")
    await nav.js("(() => { const i = document.querySelector('#q-inicio'); i.focus(); i.value = 'Guardianes del Alba'; })()")
    await capturar_click(nav, '.search-form button[type=submit]')
    await asyncio.sleep(2.5)
    peticiones = [e["params"]["request"]["url"] for e in nav._eventos
                  if e.get("method") == "Network.requestWillBeSent"][n0:]
    datos["tras_buscar"] = {
        "ruta": await nav.js("location.pathname + location.search"),
        "caja": await nav.js("document.querySelector('input[name=q]').value"),
        "peticiones_a_la_busqueda": [u.replace(base, "") for u in peticiones if "/buscar" in u],
        "resultado_visible": (await nav.js("document.querySelector('#resultados-descubrir').innerText"))[:200],
    }
    if not (datos["tras_buscar"]["ruta"] or "").startswith("/ui/descubrir"):
        raise SystemExit(f"no es Descubrir ({datos['tras_buscar']['ruta']}); no guardo la captura")
    await nav.foto(salida / "busqueda-llega-a-descubrir--escritorio-1280x800-claro.png", completa=False)


async def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    caso, base, salida = sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3])
    salida.mkdir(parents=True, exist_ok=True)
    nav = capturar.Navegador()
    datos: dict = {"caso": caso, "base": base}
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "verificar")
        datos["navegador"] = nav.version.get("Browser")
        fn = {"estados": caso_estados, "flujo": caso_flujo, "busqueda": caso_busqueda}.get(caso)
        if not fn:
            sys.exit(f"caso desconocido: {caso}")
        await fn(nav, base, salida, datos)
    finally:
        await nav.cerrar()
        (salida / f"verificar-{caso}.json").write_text(
            json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(datos, ensure_ascii=False)[:2500])


if __name__ == "__main__":
    asyncio.run(main())
