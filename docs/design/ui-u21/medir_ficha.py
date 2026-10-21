#!/usr/bin/env python3
"""Mide la ficha de serie de U21 en Chrome real (headless).

Requiere una app ZascArr arrancada y una serie con datos. Ejemplo:

    pip install playwright==1.64.0
    python docs/design/ui-u21/medir_ficha.py \
        --base-url http://127.0.0.1:8767 \
        --series-id 00000000-0000-0000-0000-000000000000 \
        --out /tmp/opencode/zascarr-u21-ficha \
        --sha "$(git rev-parse HEAD)"

Cuenta las palabras visibles antes del selector de política, comprueba el
umbral, mide 360 px, captura claro/oscuro y recorre el foco con Tab. No escribe
en la base de datos: solo abre el desplegable de fuentes y vuelve a cerrarlo.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

UMBRAL_ANTES = 50
UMBRAL_ENTRADA = 20

#: Cuenta nodos de texto visibles de `main` en orden de documento hasta el
#: selector de política. Excluye navegación, pie, avisos legales, contenido de
#: detalles cerrados (pero conserva su `<summary>` visible), controles y texto
#: oculto. Publica tres cifras: antes de la acción con datos variables, texto
#: introductorio sin esos datos y total visible.
MEDIR = r"""() => {
  const main = document.querySelector('main');
  const select = document.querySelector('#wishlist_policy');
  if (!main || !select) return null;
  const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  const palabras = [];
  const palabrasIntro = [];
  const palabrasTotales = [];
  const textos = [];
  let antes = true;
  const saltar = (n) => {
    const el = n.parentElement;
    if (!el) return true;
    if (el.closest('select, option, input, button, textarea')) return true;
    if (el.closest('nav, header, footer, .legal-notice, .back-link')) return true;
    const cerrado = el.closest('details:not([open])');
    if (cerrado && !el.closest('summary')) return true;
    const s = getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden' || el.hidden) return true;
    if (el.offsetParent === null && s.position !== 'fixed') return true;
    return false;
  };
  while (walker.nextNode()) {
    const n = walker.currentNode;
    if (select.contains(n)) {
      antes = false;
      continue;
    }
    if (saltar(n)) continue;
    const el = n.parentElement;
    const t = (n.textContent || '').replace(/\s+/g, ' ').trim();
    if (!t) continue;
    palabrasTotales.push(...(t.match(/[\p{L}\p{N}]+/gu) || []));
    if (antes) {
      textos.push(t);
      palabras.push(...(t.match(/[\p{L}\p{N}]+/gu) || []));
      // Los datos variables de la cabecera (título, editorial, recuento) no
      // forman parte del presupuesto introductorio; el resumen del detalle sí.
      const datosCabecera =
        el.closest('.series-header') && el.closest('h1, .series-meta, p.subtitle');
      if (!datosCabecera) {
        palabrasIntro.push(...(t.match(/[\p{L}\p{N}]+/gu) || []));
      }
    }
  }
  const intro = document.querySelector('.series-intro')?.innerText.trim() || '';
  const parrafos_mayusculas = [...main.querySelectorAll('p')]
    .filter(p => {
      const s = getComputedStyle(p);
      const r = p.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
    })
    .map(p => ({texto: p.innerText.trim(), transform: getComputedStyle(p).textTransform}))
    .filter(p => p.transform === 'uppercase');
  return {
    palabras_antes: palabras.length,
    palabras_intro: palabrasIntro.length,
    palabras_totales: palabrasTotales.length,
    textos,
    intro,
    intro_palabras: (intro.match(/[\p{L}\p{N}]+/gu) || []).length,
    accion: 'select#wishlist_policy (Qué buscar)',
    parrafos_mayusculas: parrafos_mayusculas,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  };
}"""


def _comprobar(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise AssertionError(mensaje)


def _texto_activo(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const el = document.activeElement;
          if (!el) return null;
          return {
            tag: el.tagName.toLowerCase(),
            id: el.id || null,
            texto: (el.innerText || el.value || el.getAttribute('aria-label') || '')
              .replace(/\\s+/g, ' ').trim().slice(0, 100),
          };
        }"""
    )


def _medir(page: Page) -> dict:
    datos = page.evaluate(MEDIR)
    _comprobar(datos is not None, "No se encontró main o el selector #wishlist_policy.")
    _comprobar(
        datos["palabras_antes"] <= UMBRAL_ANTES,
        f"Hay {datos['palabras_antes']} palabras antes de la acción; el umbral es {UMBRAL_ANTES}.",
    )
    _comprobar(
        datos["intro_palabras"] <= UMBRAL_ENTRADA,
        f"La entrada tiene {datos['intro_palabras']} palabras; el umbral es {UMBRAL_ENTRADA}.",
    )
    _comprobar(
        datos["palabras_intro"] <= UMBRAL_ANTES,
        f"El texto introductorio tiene {datos['palabras_intro']} palabras; "
        f"el umbral es {UMBRAL_ANTES}.",
    )
    _comprobar(
        not datos["parrafos_mayusculas"],
        f"Hay párrafos en mayúsculas: {datos['parrafos_mayusculas']}",
    )
    return datos


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8767")
    parser.add_argument("--series-id", required=True)
    parser.add_argument("--out", default="/tmp/opencode/zascarr-u21-ficha")
    parser.add_argument("--sha", default=os.environ.get("ZASCARR_SHA", ""))
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(UTC)
    prefijo = ahora.strftime("%Y-%m-%d")
    url = f"{args.base_url}/ui/series/{args.series_id}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=args.chrome,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="es-ES")
        page.goto(url, wait_until="networkidle")

        claro = _medir(page)
        page.screenshot(path=str(out / f"{prefijo}-ficha-1280-claro.png"), full_page=True)

        # Teclado: el enlace de vuelta es navegación; el orden útil es
        # «Fuentes y atribución» -> «Qué buscar» -> resto.
        page.locator(".back-link").focus()
        teclado = []
        for _ in range(8):
            page.keyboard.press("Tab")
            teclado.append(_texto_activo(page))
        _comprobar(
            any((paso or {}).get("id") == "wishlist_policy" for paso in teclado),
            f"El selector de política no es alcanzable con Tab: {teclado}",
        )
        page.locator("#wishlist_policy").focus()
        foco = page.evaluate(
            """() => {
              const el = document.activeElement;
              const s = getComputedStyle(el);
              return {
                id: el.id,
                outlineStyle: s.outlineStyle,
                outlineWidth: s.outlineWidth,
                boxShadow: s.boxShadow,
              };
            }"""
        )
        _comprobar(
            foco["outlineStyle"] != "none" or foco["boxShadow"] != "none",
            f"El selector no muestra foco visible: {foco}",
        )

        # Fuentes: cerrado por defecto, accesible con el teclado y sin
        # duplicar el aviso legal fuera del desplegable.
        fuentes = page.locator("details.series-fuentes")
        _comprobar(fuentes.count() == 1, "No hay un único desplegable de fuentes.")
        _comprobar(
            fuentes.get_attribute("open") is None, "El desplegable de fuentes empieza abierto."
        )
        fuentes.locator("summary").focus()
        page.keyboard.press("Enter")
        _comprobar(
            fuentes.get_attribute("open") is not None, "El desplegable no se abre con Enter."
        )
        _comprobar(
            page.get_by_text(
                "Los metadatos de esta ficha proceden de fuentes de terceros"
            ).is_visible(),
            "El aviso de fuentes no se ve al abrir el desplegable.",
        )
        page.keyboard.press("Enter")
        _comprobar(fuentes.get_attribute("open") is None, "El desplegable no se cierra con Enter.")

        aria = page.locator("main").aria_snapshot()
        (out / "aria-ficha.txt").write_text(aria, encoding="utf-8")
        _comprobar(
            'combobox "Qué buscar"' in aria, "El selector no tiene nombre accesible «Qué buscar»."
        )
        # Las capturas no deben heredar el anillo de foco de la prueba de teclado.
        page.evaluate("document.activeElement?.blur()")

        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(200)
        oscuro = _medir(page)
        page.screenshot(path=str(out / f"{prefijo}-ficha-1280-oscuro.png"), full_page=True)

        page.emulate_media(color_scheme="light")
        page.set_viewport_size({"width": 360, "height": 800})
        page.wait_for_timeout(300)
        movil = _medir(page)
        caja_select = page.locator("#wishlist_policy").bounding_box()
        _comprobar(caja_select is not None, "El selector no tiene caja a 360 px.")
        _comprobar(
            movil["scrollWidth"] <= movil["clientWidth"] + 1,
            f"Desbordamiento horizontal a 360 px: {movil}",
        )
        _comprobar(
            caja_select["x"] >= 0 and caja_select["x"] + caja_select["width"] <= 361,
            f"El selector se sale de 360 px: {caja_select}",
        )
        page.screenshot(path=str(out / f"{prefijo}-ficha-360-claro.png"), full_page=True)

        page.emulate_media(color_scheme="dark")
        page.wait_for_timeout(200)
        movil_oscura = _medir(page)
        _comprobar(
            movil_oscura["scrollWidth"] <= movil_oscura["clientWidth"] + 1,
            f"Desbordamiento horizontal a 360 px en oscuro: {movil_oscura}",
        )
        page.screenshot(path=str(out / f"{prefijo}-ficha-360-oscuro.png"), full_page=True)

        resumen = {
            "fecha_utc": ahora.isoformat(timespec="seconds"),
            "sha": args.sha,
            "base_url": args.base_url,
            "series_id": args.series_id,
            "url": url,
            "navegador": browser.version,
            "user_agent": page.evaluate("navigator.userAgent"),
            "viewport_escritorio": {"width": 1280, "height": 900},
            "viewport_movil": {"width": 360, "height": 800},
            "medida_clara": claro,
            "medida_oscura": oscuro,
            "medida_movil": movil,
            "medida_movil_oscura": movil_oscura,
            "umbral_antes_accion": UMBRAL_ANTES,
            "umbral_entrada": UMBRAL_ENTRADA,
            "foco": foco,
            "teclado": teclado,
            "aria": {
                "combobox": 'combobox "Qué buscar"',
                "fuentes": "details.series-fuentes con summary «Fuentes y atribución»",
                "snapshot": "aria-ficha.txt",
            },
            "capturas": [
                f"{prefijo}-ficha-1280-claro.png",
                f"{prefijo}-ficha-1280-oscuro.png",
                f"{prefijo}-ficha-360-claro.png",
                f"{prefijo}-ficha-360-oscuro.png",
            ],
        }
        (out / f"{prefijo}-ficha.json").write_text(
            json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
