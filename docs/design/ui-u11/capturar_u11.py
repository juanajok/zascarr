#!/usr/bin/env python3
# ruff: noqa: E501
"""Evidencia de U11 (#198): foco por teclado y nombre accesible, con Chrome headless por CDP.

Herramienta de desarrollo, FUERA del paquete. Reutiliza `Navegador` de `../ui-baseline/capturar.py`
(mismos requisitos: `google-chrome` y `websockets`) y solo se usa contra el ensayo aislado:

    UI_BASE_DATOS=… docs/design/ui-baseline/ensayo.sh preparar
    python3 docs/design/ui-u11/capturar_u11.py ETIQUETA http://127.0.0.1:18000 docs/design/ui-u11

ETIQUETA es `antes` o `despues`. No hace POST. El foco llega con una pulsación REAL de Tab
(`Input.dispatchKeyEvent`), no con `element.focus()`, para que aplique `:focus-visible`; el nombre
de cada control es el que calcula Chromium en su árbol de accesibilidad (`Accessibility.
getPartialAXTree`), que es lo que recibe un lector de pantalla. Escribe PNG y `datos-ETIQUETA.json`.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "capturar", Path(__file__).resolve().parents[1] / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capturar)

VISTA = {"nombre": "escritorio", "w": 1280, "h": 800, "movil": False}

MEDIR = r"""(() => {
  const rgb = s => s.match(/[\d.]+/g).slice(0, 4).map(Number);
  const lum = ([r, g, b]) => { const f = c => (c /= 255) <= .03928 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4;
                               return .2126 * f(r) + .7152 * f(g) + .0722 * f(b); };
  const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return +((x + .05) / (y + .05)).toFixed(2); };
  const fondo = e => { for (let n = e.parentElement; n; n = n.parentElement) {
      const c = getComputedStyle(n).backgroundColor, v = rgb(c); if (v.length < 4 || v[3] > 0) return c; } };
  const e = document.activeElement, cs = getComputedStyle(e), bg = rgb(fondo(e));
  const m = cs.boxShadow.match(/rgba?\([^)]*\)/); let sombra = null;
  if (m) { const [r, g, b, a = 1] = rgb(m[0]); sombra = cr([r * a + bg[0] * (1 - a), g * a + bg[1] * (1 - a), b * a + bg[2] * (1 - a)], bg); }
  return { elemento: e.tagName.toLowerCase() + (e.className ? '.' + e.className : '') + (e.name ? '[name=' + e.name + ']' : ''),
           focus_visible: e.matches(':focus-visible'),
           outline: cs.outlineStyle === 'none' ? 'none' : cs.outlineStyle + ' ' + cs.outlineWidth + ' ' + cs.outlineColor,
           fondo: fondo(e),
           contraste_anillo: cs.outlineStyle === 'none' ? null : cr(rgb(cs.outlineColor), bg),
           contraste_sombra: sombra };
})()"""


async def nombre_ax(nav, expresion: str) -> str | None:
    obj = (await nav.cdp("Runtime.evaluate", expression=expresion))["result"]
    nodos = (await nav.cdp("Accessibility.getPartialAXTree", objectId=obj["objectId"],
                           fetchRelatives=False))["nodes"]
    return (nodos[0].get("name") or {}).get("value") if nodos else None


async def nombres_de_la_pagina(nav) -> list[dict]:
    total = await nav.js("document.querySelectorAll('input:not([type=hidden]),select,textarea').length")
    salida = []
    for i in range(total):
        sel = f"document.querySelectorAll('input:not([type=hidden]),select,textarea')[{i}]"
        salida.append({"control": await nav.js(f"{sel}.name || {sel}.tagName"),
                       "placeholder": await nav.js(f"{sel}.placeholder || null"),
                       "nombre_accesible": await nombre_ax(nav, sel)})
    return salida


async def tab(nav) -> None:
    """Una pulsación de Tab real. Solo `keyDown`: el `keyup` dispararía la búsqueda HTMX."""
    await nav.cdp("Input.dispatchKeyEvent", type="rawKeyDown", key="Tab", code="Tab",
                  windowsVirtualKeyCode=9, nativeVirtualKeyCode=9)
    await asyncio.sleep(0.3)


ANTERIOR = """(() => {{ const t = document.querySelector({destino!r});
  const f = [...document.querySelectorAll('a[href], button, input:not([type=hidden]), select')]
    .filter(e => e.compareDocumentPosition(t) & Node.DOCUMENT_POSITION_FOLLOWING);
  f[f.length - 1].focus(); }})()"""


async def caso(nav, base, salida, etiqueta, nombre, ruta, tema, destino) -> dict:
    """Pone el foco (por script) en el control ANTERIOR a `destino` y llega a él con Tab."""
    await nav.vista(VISTA, tema)
    await nav.ir(base + ruta)
    await nav.js(ANTERIOR.format(destino=destino))
    await tab(nav)
    await nav.js("document.activeElement.scrollIntoView({block: 'center'})")
    await asyncio.sleep(0.3)
    datos = await nav.js(MEDIR)
    datos["nombre_accesible_del_foco"] = await nombre_ax(nav, "document.activeElement")
    datos["controles"] = await nombres_de_la_pagina(nav)
    png = salida / f"{etiqueta}--{nombre}--{tema}.png"
    await nav.foto(png, completa=False)
    datos.update({"url": ruta, "tema": tema, "captura": png.name})
    return datos


async def main(etiqueta: str, base: str, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    nav = capturar.Navegador()
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "solo-lectura")
        await nav.cdp("Emulation.setFocusEmulationEnabled", enabled=True)
        await nav.cdp("Accessibility.enable")
        await nav.ir(base + "/ui/", espera=0.3)
        css = await nav.js("fetch('/static/web.css').then(r => r.text()).then(t => t.includes('U11'))")
        datos = {"etiqueta": etiqueta, "chrome": nav.version.get("Browser"), "web_css_con_u11": css,
                 "casos": [
            # Buscador de serie de la 4.ª tarjeta (la de «Mundo Cobalto»).
            await caso(nav, base, salida, etiqueta, "por-revisar-foco-buscador", "/ui/pendientes", "dark",
                       ".pending-card:nth-child(4) .series-search"),
            await caso(nav, base, salida, etiqueta, "biblioteca-foco-tradicion", "/ui/biblioteca", "light",
                       "#filtros select[name=tradition]"),
            await caso(nav, base, salida, etiqueta, "deseados-foco-buscador", "/ui/wishlist", "dark",
                       "input.series-search"),
        ]}
        (salida / f"datos-{etiqueta}.json").write_text(
            json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(datos, ensure_ascii=False, indent=2))
    finally:
        await nav.cerrar()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3])))
