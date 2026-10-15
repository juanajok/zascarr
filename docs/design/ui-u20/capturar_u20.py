#!/usr/bin/env python3
# ruff: noqa: E501
"""Evidencia de U20 (#207) en navegador real: Chrome headless por CDP contra el ensayo aislado.

Reutiliza `Navegador` de `../ui-baseline/capturar.py` (solo lectura del servidor salvo las dos acciones
de la propia pantalla, que no escriben en la BD ni en el disco). Los clics son REALES
(`Input.dispatchMouseEvent` en el centro del botón), no `element.click()`.

    UI_BASE_DATOS=… docs/design/ui-baseline/ensayo.sh preparar
    python3 docs/design/ui-u20/capturar_u20.py http://127.0.0.1:18000 docs/design/ui-u20
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import sys
import urllib.request
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "capturar", Path(__file__).resolve().parents[1] / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capturar)

VISTA = {"nombre": "escritorio", "w": 1280, "h": 900, "movil": False}
JERGA = re.compile(r"\btoken\b|\blotes?\b|\bmotivo:", re.I)

ESTADO = r"""(() => ({
  marcados: [...document.querySelectorAll('.vinc-fila')].filter(f => f.dataset.marcado === '1').length,
  bloqueados_marcados: [...document.querySelectorAll('.vinc-fila')].filter(f => f.dataset.marcado === '1' && f.dataset.marcable === '0').length,
  filas: document.querySelectorAll('.vinc-fila').length,
  recuento: (() => { const e = document.querySelector('.vinc-accion-resultado'); return e ? {accion: e.dataset.accion, n: Number(e.dataset.n), texto: e.innerText.trim()} : null; })(),
  botones: [...document.querySelectorAll('.vinc-masivo button')].map(b => ({texto: b.innerText.trim(), desactivado: b.disabled})),
  listo_para_vincular: !!document.querySelector('.lote-listo'),
  texto_visible_con_jerga: (document.querySelector('#revision').innerText.match(/\btoken\b|\blotes?\b|\bmotivo:/gi) || []),
}))()"""


async def clic(nav, selector: str) -> None:
    pos = await nav.js(f"""(() => {{ const e = document.querySelector({selector!r}); e.scrollIntoView({{block: 'center'}});
      const r = e.getBoundingClientRect(); return {{x: r.x + r.width / 2, y: r.y + r.height / 2}}; }})()""")
    for tipo in ("mouseMoved", "mousePressed", "mouseReleased"):
        await nav.cdp("Input.dispatchMouseEvent", type=tipo, x=pos["x"], y=pos["y"], button="left", clickCount=1)
    await asyncio.sleep(1.5)


async def main(base: str, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    html = urllib.request.urlopen(base + "/ui/biblioteca").read().decode()
    series = re.findall(r'href="/ui/series/([0-9a-f-]+)"', html)
    nav = capturar.Navegador()
    pasos: list[dict] = []
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "principal")
        await nav.vista(VISTA, "light")
        await nav.ir(f"{base}/ui/pendientes/carpetas/asistente/vinculacion?clave=_Unsorted&series_id={series[0]}")
        css = await nav.js("fetch('/static/web.css').then(r => r.text()).then(t => t.includes('U20'))")
        for nombre, selector in (("0-abierta", None), ("1-marcar-todos", 'button[value="marcar_todos"]'),
                                 ("2-desmarcar-todos", 'button[value="desmarcar_todos"]')):
            if selector:
                await clic(nav, selector)
            estado = await nav.js(ESTADO)
            png = salida / f"{nombre}.png"
            await nav.foto(png, completa=False)
            pasos.append({"paso": nombre, "captura": png.name, **estado})
        datos = {"chrome": nav.version.get("Browser"), "web_css_con_u20": css, "series_id": series[0], "pasos": pasos}
    finally:
        await nav.cerrar()
    (salida / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(datos, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/"), Path(sys.argv[2])))
