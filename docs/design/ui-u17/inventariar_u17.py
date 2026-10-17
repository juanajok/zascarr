#!/usr/bin/env python3
# ruff: noqa: E501
"""Inventario de U17 (#204): qué texto se pinta en MAYÚSCULAS o GIRADO, y cuánto texto lleva, en Chrome contra el ensayo aislado.

Reutiliza `Navegador` de `../ui-baseline/capturar.py` y la lista de pantallas de `../ui-u16/medir_u16.py`. Para cada pantalla, escritorio y móvil, en
claro y oscuro, recorre TODOS los elementos visibles y anota los que tienen `text-transform: uppercase` o una `transform` con giro, con su número de
palabras. Un rótulo (≤ 3 palabras) puede ir en mayúsculas o girado; un texto de más de una línea (> 3 palabras), no (criterio 1 de la tarjeta).
Los títulos (`h1`–`h4`) y las pegatinas de estado se anotan aparte: la regla de la tarjeta habla de **avisos y textos legales**.

    python3 docs/design/ui-u17/inventariar_u17.py ETIQUETA http://127.0.0.1:18000 docs/design/ui-u17

ESCRIBE en el ensayo (acepta el aviso legal, para ver Deseados completo): es desechable.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _cargar(nombre: str, ruta: Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


capturar = _cargar("capturar", AQUI.parent / "ui-baseline" / "capturar.py")

VISTAS = [("escritorio", 1280, 900, False), ("movil", 390, 844, True)]

INVENTARIO = r"""(() => {
  const palabras = t => t.replace(/\s+/g, ' ').trim().split(' ').filter(Boolean).length;
  const visible = e => { const cs = getComputedStyle(e), r = e.getBoundingClientRect();
    return cs.visibility !== 'hidden' && cs.display !== 'none' && r.width > 1 && r.height > 1 && !e.closest('[hidden]'); };
  const giro = e => { const t = getComputedStyle(e).transform; if (!t || t === 'none') return 0;
    const m = t.match(/matrix\(([^)]+)\)/); if (!m) return 0; const [a, b] = m[1].split(',').map(Number);
    return Math.round(Math.atan2(b, a) * 180 / Math.PI * 100) / 100; };
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string' ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.') : '');
  const filas = [];
  for (const e of document.querySelectorAll('main *, .site-footer *')) {
    if (!visible(e)) continue;
    // solo el elemento que POSEE el texto (nodos de texto directos): evita contar cada ancestro
    const propio = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' ');
    const total = e.textContent || '';
    const cs = getComputedStyle(e);
    const may = cs.textTransform === 'uppercase', g = giro(e);
    if (!(may || g)) continue;
    if (!propio.trim() && !e.matches('.caption, .legal-notice, .aviso')) continue;
    filas.push({sel: sel(e), tag: e.tagName.toLowerCase(), clases: String(e.className), mayusculas: may, giro_grados: g,
                palabras: palabras(propio.trim() ? propio : total), texto: total.replace(/\s+/g, ' ').trim().slice(0, 70)});
  }
  return filas; })()"""


def clasificar(f: dict) -> str:
    if f["tag"] in ("h1", "h2", "h3", "h4"):
        return "titulo"
    c = f["clases"]
    if "caption" in c or "legal-notice" in c or "aviso" in c:
        return "aviso_o_nota"
    return "otro"


async def main(etiqueta: str, base: str, salida: Path) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    medir = _cargar("medir_u16", AQUI.parent / "ui-u16" / "medir_u16.py")
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
        sid = ficha.rsplit("/", 1)[-1] if ficha else ""
        pantallas = [
            ("panel", "/ui/"), ("biblioteca", "/ui/biblioteca"), ("ficha-de-serie", ficha or "/ui/biblioteca"), ("descubrir", "/ui/descubrir"),
            ("por-revisar", "/ui/pendientes"), ("pendientes-por-carpeta", "/ui/pendientes/carpetas"),
            ("asistente-de-carpeta", "/ui/pendientes/carpetas/asistente?clave=_Unsorted"),
            ("revision-de-la-vinculacion", f"/ui/pendientes/carpetas/asistente/vinculacion?clave=_Unsorted&series_id={sid}"),
            ("deseados", "/ui/wishlist"), ("mi-biblioteca-auditoria", "/ui/auditoria"), ("ajustes", "/ui/ajustes"),
            ("estado", "/estado"), ("aviso-legal-asistente", "/ui/legal"), ("aviso-legal-texto", "/legal"),
        ]
        del medir
        for nombre, ruta in pantallas:
            res["pantallas"][nombre] = {"ruta": ruta, "vistas": {}}
            for tema in ("light", "dark"):
                for vn, w, h, movil in VISTAS:
                    await nav.vista({"nombre": vn, "w": w, "h": h, "movil": movil}, tema)
                    await nav.ir(base + ruta, espera=1.4 if nombre == "estado" else 0.7)
                    filas = await nav.js(INVENTARIO)
                    for f in filas:
                        f["clase_de_uso"] = clasificar(f)
                    res["pantallas"][nombre]["vistas"][f"{vn}-{tema}"] = filas
    finally:
        await nav.cerrar()
    (salida / f"inventario-{etiqueta}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{'pantalla':30} {'avisos/notas >3 palabras en MAYÚSCULAS o girados (escritorio-claro)':>70}  | títulos >3 | otros >3")
    for n, d in res["pantallas"].items():
        v = d["vistas"]["escritorio-light"]
        a = [f for f in v if f["clase_de_uso"] == "aviso_o_nota" and f["palabras"] > 3]
        t = [f for f in v if f["clase_de_uso"] == "titulo" and f["palabras"] > 3]
        o = [f for f in v if f["clase_de_uso"] == "otro" and f["palabras"] > 3]
        print(f"{n:30} {len(a):>70}  | {len(t):>10} | {len(o):>8}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3])))
