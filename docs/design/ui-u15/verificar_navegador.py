#!/usr/bin/env python3
"""Verificación de presentación de U15 en un Chrome real (headless).

Requiere una app ZascArr arrancada con GCD y/o Tebeosfera activos y Playwright:

    pip install playwright==1.64.0
    python docs/design/ui-u15/verificar_navegador.py \
        --base-url http://127.0.0.1:8765 \
        --out /tmp/u15-verificacion \
        --sha "$(git rev-parse HEAD)"

No crea ninguna serie: busca, comprueba la presentación y pulsa «Revisar» (la vista previa no
escribe). Las capturas y el resumen quedan en ``--out``.

La copy que exige este script es la de U15 (anterior a #276): las fuentes por defecto usan ahora
la frase con procedencia. La evidencia de 2026-10-21 sigue siendo válida para el contrato vigente
entonces; #276 tiene sus propias pruebas automáticas.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


def _comprobar(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise AssertionError(mensaje)


def _resumen_tarjetas(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const tarjetas = [...document.querySelectorAll('#resultados-descubrir .discovery-card')];
          return {
            n: tarjetas.length,
            titulos: tarjetas.map(t => {
              const titulo = t.querySelector('.discovery-card-title');
              return titulo ? titulo.innerText.trim() : null;
            }),
            selects: tarjetas.map(t => {
              const s = t.querySelector('select[name="tradition"]');
              return s ? {
                required: s.required,
                value: s.value,
                seleccionados: [...s.selectedOptions].map(o => o.value),
              } : null;
            }),
            pistas: tarjetas.map(t => t.querySelector('small')?.innerText.trim() || null),
          };
        }"""
    )


def _comprobar_presentacion(datos: dict) -> None:
    _comprobar(datos["n"] > 0, "La búsqueda no devolvió ninguna tarjeta.")
    _comprobar(
        all(s is not None for s in datos["selects"]),
        "Hay una tarjeta sin selector de tradición.",
    )
    _comprobar(
        all(s["required"] for s in datos["selects"]),
        "Algún selector de tradición no es obligatorio.",
    )
    _comprobar(
        all(s["value"] == "" for s in datos["selects"]),
        "Algún selector trae un valor preseleccionado.",
    )
    _comprobar(
        all(s["seleccionados"] == [""] for s in datos["selects"]),
        "Algún selector trae una tradición seleccionada por defecto.",
    )
    _comprobar(
        all(
            p
            and p.startswith("La fuente lo clasifica como ")
            and "Es solo una pista de la fuente, no de la obra: elige tú." in p
            for p in datos["pistas"]
        ),
        "Alguna tarjeta no lleva el texto de pista completo.",
    )


def _pista_por_valor(pistas: list[str]) -> dict[str, int]:
    cuenta: Counter[str] = Counter()
    for pista in pistas:
        match = re.match(r"La fuente lo clasifica como (.+?)\. Es solo una pista", pista)
        cuenta[match.group(1) if match else "desconocido"] += 1
    return dict(cuenta)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--out", default="/tmp/u15-verificacion")
    parser.add_argument("--consulta", default="Mortadelo")
    parser.add_argument("--sha", default=os.environ.get("ZASCARR_SHA", ""))
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(UTC)
    prefijo = ahora.strftime("%Y-%m-%d")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=args.chrome,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": 1280, "height": 900}, locale="es-ES")
        page.goto(f"{args.base_url}/ui/descubrir", wait_until="networkidle")

        salud = page.request.get(f"{args.base_url}/api/health")
        _comprobar(salud.ok, f"/api/health devolvió {salud.status}.")
        fuentes = salud.json().get("fuentes", {})
        _comprobar(
            fuentes.get("gcd") == "enabled" or fuentes.get("tebeosfera") == "enabled",
            f"Ninguna fuente de U15 está activa: {fuentes}",
        )

        caja = page.locator('input[name="q"]')
        caja.click()
        caja.press_sequentially(args.consulta, delay=40)
        page.wait_for_selector("#resultados-descubrir .discovery-card", timeout=45_000)
        page.wait_for_timeout(1_000)

        datos = _resumen_tarjetas(page)
        _comprobar_presentacion(datos)
        page.screenshot(path=str(out / f"{prefijo}-descubrir-mortadelo-1280.png"), full_page=True)

        page.set_viewport_size({"width": 360, "height": 800})
        page.wait_for_timeout(300)
        movil = page.evaluate(
            """() => ({
              viewport: window.innerWidth,
              clientWidth: document.documentElement.clientWidth,
              scrollWidth: document.documentElement.scrollWidth,
              bodyScrollWidth: document.body.scrollWidth,
            })"""
        )
        _comprobar(
            movil["scrollWidth"] <= movil["clientWidth"] + 1,
            f"Desbordamiento horizontal a 360 px: {movil}",
        )
        page.screenshot(path=str(out / f"{prefijo}-descubrir-mortadelo-360.png"), full_page=True)
        page.set_viewport_size({"width": 1280, "height": 900})

        indice = next(
            (i for i, pista in enumerate(datos["pistas"]) if pista and "Tebeo español" in pista),
            None,
        )
        _comprobar(
            indice is not None,
            "No hay ninguna tarjeta con pista «Tebeo español» para probar la elección.",
        )
        tarjeta = page.locator("#resultados-descubrir .discovery-card").nth(indice)
        tarjeta.locator('select[name="tradition"]').select_option("manga")
        tarjeta.get_by_role("button", name="Revisar").click()
        page.wait_for_function(
            "document.body.innerText.includes('Tradición elegida: Manga')",
            timeout=30_000,
        )
        page.wait_for_timeout(500)
        preview = (
            page.locator("#resultados-descubrir .discovery-card").nth(indice).locator(".alta-paso")
        )
        texto_preview = preview.inner_text().strip()
        _comprobar(
            "Tradición elegida: Manga" in texto_preview,
            "La vista previa no refleja la tradición elegida.",
        )
        _comprobar(
            "Crear serie vacía" in texto_preview,
            "La vista previa no ofrece el paso de creación.",
        )
        page.screenshot(
            path=str(out / f"{prefijo}-descubrir-revision-manga-1280.png"), full_page=True
        )

        resumen = {
            "fecha_utc": ahora.isoformat(timespec="seconds"),
            "sha": args.sha,
            "base_url": args.base_url,
            "consulta": args.consulta,
            "navegador": browser.version,
            "user_agent": page.evaluate("navigator.userAgent"),
            "viewport_escritorio": {"width": 1280, "height": 900},
            "viewport_movil": movil,
            "n_tarjetas": datos["n"],
            "selects": {
                "total": len(datos["selects"]),
                "obligatorios": sum(1 for s in datos["selects"] if s["required"]),
                "vacios": sum(1 for s in datos["selects"] if s["value"] == ""),
                "con_tradicion_preseleccionada": sum(
                    1 for s in datos["selects"] if s["seleccionados"] != [""]
                ),
            },
            "pistas_por_valor": _pista_por_valor(datos["pistas"]),
            "eleccion": {
                "tarjeta": datos["titulos"][indice],
                "sugerencia": "Tebeo español",
                "elegida": "Manga",
                "vista_previa": texto_preview,
            },
            "capturas": [
                f"{prefijo}-descubrir-mortadelo-1280.png",
                f"{prefijo}-descubrir-mortadelo-360.png",
                f"{prefijo}-descubrir-revision-manga-1280.png",
            ],
        }
        (out / "verificacion-navegador.json").write_text(
            json.dumps(resumen, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
