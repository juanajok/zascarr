#!/usr/bin/env python3
# ruff: noqa: E501
"""Capturas de U17 (#204) para el antes/después: avisos y textos legales en Chrome contra el ensayo aislado.

Reutiliza `Navegador` de `../ui-baseline/capturar.py`. Pantallas con aviso legal o notas largas (Ajustes, Deseados, ficha de serie, Estado,
Descubrir, asistente de carpeta), en claro y oscuro y en escritorio (1280) y vista estrecha (390). Mide además el estilo calculado del aviso
legal y de las notas (mayúsculas, giro, palabras, tamaño) y si el aviso legal tiene enlace visible.

    python3 docs/design/ui-u17/capturar_u17.py ETIQUETA http://127.0.0.1:18000 docs/design/ui-u17

ESCRIBE en el ensayo (acepta el aviso legal): es desechable.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("capturar", Path(__file__).resolve().parents[1] / "ui-baseline" / "capturar.py")
capturar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(capturar)

MEDIDA = r"""(() => {
  const giro = e => { const t = getComputedStyle(e).transform; if (!t || t === 'none') return 0;
    const m = t.match(/matrix\(([^)]+)\)/); if (!m) return 0; const [a, b] = m[1].split(',').map(Number); return Math.round(Math.atan2(b, a) * 180 / Math.PI * 100) / 100; };
  const palabras = t => t.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean).length;
  const notas = [...document.querySelectorAll('main .caption, main .legal-notice, .site-footer .legal-notice')].filter(e => e.getBoundingClientRect().width > 1)
    .map(e => ({sel: e.tagName.toLowerCase() + '.' + String(e.className).trim().split(/\s+/).join('.'), palabras: palabras(e.textContent),
      mayusculas: getComputedStyle(e).textTransform === 'uppercase', giro_grados: giro(e), tamano_px: parseFloat(getComputedStyle(e).fontSize),
      enlace_aviso_legal: !![...e.querySelectorAll('a[href="/legal"]')].find(a => a.textContent.trim() === 'Aviso legal'),
      dentro_de_details_cerrado: !!e.closest('details:not([open])'), texto: e.textContent.replace(/\s+/g, ' ').trim().slice(0, 90)}));
  return notas; })()"""


async def main(etiqueta: str, base: str, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    nav = capturar.Navegador()
    res: dict = {"etiqueta": etiqueta, "pantallas": {}}
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "principal")
        res["chrome"] = nav.version.get("Browser")
        capturar.post_form(base, "/ui/legal/accept", {"acepto_1": "on", "acepto_2": "on", "acepto_3": "on"})
        await nav.vista({"nombre": "e", "w": 1280, "h": 900, "movil": False}, "light")
        await nav.ir(base + "/ui/biblioteca", espera=0.5)
        ficha = await nav.js("(() => { const a=[...document.querySelectorAll('a[href^=\"/ui/series/\"]')].find(x=>x.textContent.includes('Guardianes')); return a? a.getAttribute('href'):null })()")
        pantallas = [("ajustes", "/ui/ajustes"), ("deseados", "/ui/wishlist"), ("ficha-de-serie", ficha), ("estado", "/estado"),
                     ("descubrir", "/ui/descubrir"), ("asistente-de-carpeta", "/ui/pendientes/carpetas/asistente?clave=_Unsorted")]
        for nombre, ruta in pantallas:
            res["pantallas"][nombre] = {}
            for tema in ("light", "dark"):
                for vn, w, h, movil in (("escritorio", 1280, 900, False), ("estrecha", 390, 844, True)):
                    await nav.vista({"nombre": vn, "w": w, "h": h, "movil": movil}, tema)
                    await nav.ir(base + ruta, espera=1.6 if nombre == "estado" else 0.8)
                    res["pantallas"][nombre][f"{vn}-{tema}"] = await nav.js(MEDIDA)
                    if (vn, tema) in (("escritorio", "light"), ("estrecha", "dark")):
                        # llevar el aviso o la nota al centro de la pantalla: es lo que se quiere ver
                        await nav.js("(() => { const e = document.querySelector('main .legal-notice-warn, main .caption, .site-footer .legal-notice'); if (e) e.scrollIntoView({block: 'center', behavior: 'instant'}); })()")
                        await asyncio.sleep(0.3)
                        await nav.foto(salida / f"{etiqueta}--{nombre}--{vn}-{tema}.png", completa=False)
    finally:
        await nav.cerrar()
    (salida / f"medida-{etiqueta}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{'pantalla':24} {'notas':>5} {'>3 pal. en MAYÚS.':>18} {'>3 pal. giradas':>16}  (escritorio, claro)")
    for n, v in res["pantallas"].items():
        f = v["escritorio-light"]
        print(f"{n:24} {len(f):>5} {sum(1 for x in f if x['palabras'] > 3 and x['mayusculas']):>18} {sum(1 for x in f if x['palabras'] > 3 and x['giro_grados']):>16}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3])))
