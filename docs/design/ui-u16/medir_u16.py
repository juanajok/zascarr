#!/usr/bin/env python3
# ruff: noqa: E501
"""Medición de U16 (#203): lo que un móvil real notaría, medido en Chrome (emulación de viewport táctil) contra el ensayo aislado.

Reutiliza `Navegador` de `../ui-baseline/capturar.py`. Para cada pantalla y cada ancho (360, 390 y 414 px) mide:
  1. DESBORDE LATERAL: `scrollWidth > clientWidth` y qué elementos sobresalen del ancho (WCAG 1.4.10).
  2. ZOOM AL ESCRIBIR: campos de texto/selectores con `font-size` < 16 px (Safari en iOS amplía la página al enfocarlos).
  3. OBJETIVOS TÁCTILES: botones, campos, selectores, `summary` y enlaces-botón con alto < 44 px (primarios) o < 24 px (mínimo
     absoluto, WCAG 2.5.8). Los enlaces dentro de un párrafo de texto están exentos y no se cuentan.

    python3 docs/design/ui-u16/medir_u16.py ETIQUETA http://127.0.0.1:18000 docs/design/ui-u16

Escribe `medicion-ETIQUETA.json`. ESCRIBE en el ensayo (acepta el aviso legal): es desechable. Emulación, no un teléfono: no sustituye la
ronda en dispositivos reales (criterio 4 de la tarjeta).
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

ANCHOS = [(360, 740), (390, 844), (414, 896)]

MEDIR = r"""(() => {
  const W = document.documentElement.clientWidth;
  const visible = e => { const cs = getComputedStyle(e), r = e.getBoundingClientRect();
    return cs.visibility !== 'hidden' && cs.display !== 'none' && r.width > 1 && r.height > 1 && !e.closest('[hidden]'); };
  const sel = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (e.className && typeof e.className === 'string'
    ? '.' + e.className.trim().split(/\s+/).slice(0, 3).join('.') : '') + (e.type && e.tagName === 'INPUT' ? '[' + e.type + ']' : '');
  const clip = e => { for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) {
    const o = getComputedStyle(p).overflowX; if (o !== 'visible') return true; } return false; };
  // la barra inferior fija (`nav.nav`) se mide aparte: su ancho depende del de la página, no es la causa del desborde
  const desborde = [...document.querySelectorAll('body *')].filter(e => !e.closest('nav.nav') && visible(e) && !clip(e) && e.getBoundingClientRect().right > W + 1)
    .map(e => ({sel: sel(e), derecha: Math.round(e.getBoundingClientRect().right), ancho: Math.round(e.getBoundingClientRect().width)}));
  // solo los más externos (un elemento cuyo padre ya sobresale no se cuenta aparte)
  desborde.sort((a, b) => b.derecha - a.derecha);
  const campos = [...document.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button]),select,textarea')]
    .filter(visible).map(e => ({sel: sel(e), fuente_px: parseFloat(getComputedStyle(e).fontSize), alto: Math.round(e.getBoundingClientRect().height * 10) / 10,
      etiqueta: (e.getAttribute('aria-label') || e.name || e.id || '').slice(0, 40)}));
  // Un enlace EN LÍNEA es el que va dentro de una frase (su contenedor tiene más texto además del enlace): exento (WCAG 2.5.8).
  const enLinea = e => { if (e.tagName !== 'A' || e.classList.contains('btn') || e.closest('nav, .nav, summary, .tabbar, .menu')) return false;
    const p = e.parentElement; if (!p) return false;
    const resto = [...p.childNodes].filter(n => n !== e).map(n => n.textContent).join('').replace(/\s+/g, '').length;
    return resto > 3; };
  const objetivos = [...document.querySelectorAll('button, input[type=submit], input[type=button], select, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), summary, textarea, a[href], [role=button]')]
    .filter(e => visible(e) && !enLinea(e)).map(e => { const r = e.getBoundingClientRect();
      return {sel: sel(e), texto: (e.innerText || e.value || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 40),
              alto: Math.round(r.height * 10) / 10, ancho: Math.round(r.width * 10) / 10}; });
  const barra = document.querySelector('nav.nav'); const barraAncho = barra ? Math.round(barra.getBoundingClientRect().width) : null;
  return {ancho_visible: W, scroll_width: document.documentElement.scrollWidth, ancho_de_la_barra_inferior: barraAncho,
          desborda_en_horizontal: document.documentElement.scrollWidth > W + 1, elementos_que_sobresalen: desborde.slice(0, 12),
          campos, objetivos}; })()"""


def resumir(m: dict) -> dict:
    campos = m["campos"]
    return {
        "desborda_en_horizontal": m["desborda_en_horizontal"], "scroll_width": m["scroll_width"], "ancho_visible": m["ancho_visible"],
        "elementos_que_sobresalen": m["elementos_que_sobresalen"],
        "campos_menores_de_16px": [c for c in campos if c["fuente_px"] < 16],
        "n_campos": len(campos),
        "objetivos_menores_de_24px": [o for o in m["objetivos"] if o["alto"] < 24],
        # controles (botones, campos, selectores, resúmenes, enlaces-botón) por debajo de 44 px: lo que exige el criterio 3
        "controles_menores_de_44px": [o for o in m["objetivos"] if 24 <= o["alto"] < 44 and not o["sel"].startswith("a") or (o["sel"].startswith("a.btn") and 24 <= o["alto"] < 44)],
        # enlaces sueltos entre 24 y 44 px: cumplen el mínimo (WCAG 2.5.8), se listan como información
        "enlaces_sueltos_entre_24_y_44px": [o for o in m["objetivos"] if 24 <= o["alto"] < 44 and o["sel"].startswith("a") and not o["sel"].startswith("a.btn")],
        "n_objetivos": len(m["objetivos"]),
    }


async def servir_css(nav, ruta: Path) -> None:
    """Sirve la hoja de estilos LOCAL en lugar de la del servidor del ensayo (para iterar sin reconstruir la imagen). Solo para
    desarrollo: la medición que vale como evidencia se hace contra un ensayo reconstruido, sin esto."""
    import base64
    cuerpo = base64.b64encode(ruta.read_bytes()).decode()
    await nav.cdp("Fetch.enable", patterns=[{"urlPattern": "*/static/web.css*", "requestStage": "Request"}])

    async def bucle():
        vistos: set[str] = set()
        while True:
            for e in list(nav._eventos):
                if e.get("method") == "Fetch.requestPaused" and e["params"]["requestId"] not in vistos:
                    vistos.add(e["params"]["requestId"])
                    await nav.cdp("Fetch.fulfillRequest", requestId=e["params"]["requestId"], responseCode=200,
                                  responseHeaders=[{"name": "Content-Type", "value": "text/css"}, {"name": "Cache-Control", "value": "no-store"}], body=cuerpo)
            await asyncio.sleep(0.02)
    asyncio.create_task(bucle())


async def main(etiqueta: str, base: str, salida: Path, css_local: Path | None = None) -> None:
    salida.mkdir(parents=True, exist_ok=True)
    nav = capturar.Navegador()
    resultado: dict = {"etiqueta": etiqueta, "pantallas": {}}
    try:
        await nav.abrir()
        await capturar.comprobar_entorno(nav, base, "principal")
        resultado["chrome"] = nav.version.get("Browser")
        if css_local:
            await servir_css(nav, css_local)
            resultado["css_local_para_iterar"] = str(css_local)
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
        for nombre, ruta in pantallas:
            resultado["pantallas"][nombre] = {"ruta": ruta, "anchos": {}}
            for w, h in ANCHOS:
                await nav.vista({"nombre": f"m{w}", "w": w, "h": h, "movil": True}, "light")
                await nav.ir(base + ruta, espera=1.4 if nombre == "estado" else 0.7)
                resultado["pantallas"][nombre]["anchos"][str(w)] = resumir(await nav.js(MEDIR))
    finally:
        await nav.cerrar()
    (salida / f"medicion-{etiqueta}.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    # Resumen legible
    print(f"{'pantalla':32} {'ancho':>5} {'desborda':>9} {'<16px':>6} {'<24px':>6} {'<44px':>6}")
    for nombre, d in resultado["pantallas"].items():
        for w, r in d["anchos"].items():
            print(f"{nombre:32} {w:>5} {('SÍ +' + str(r['scroll_width'] - r['ancho_visible'])) if r['desborda_en_horizontal'] else 'no':>9} "
                  f"{len(r['campos_menores_de_16px']):>6} {len(r['objetivos_menores_de_24px']):>6} {len(r['controles_menores_de_44px']):>6}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2].rstrip("/"), Path(sys.argv[3]), Path(sys.argv[4]) if len(sys.argv) > 4 else None))
