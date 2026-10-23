#!/usr/bin/env python3
"""Verificación de presentación de U15/U15b en un Chrome real (headless).

Requiere una app ZascArr arrancada con GCD y Tebeosfera activos y Playwright:

    pip install playwright==1.64.0
    python docs/design/ui-u15/verificar_navegador.py \
        --base-url http://127.0.0.1:8768 \
        --out /tmp/u15-verificacion \
        --sha "$(git rev-parse HEAD)"

No crea ninguna serie: busca, comprueba la presentación y pulsa «Revisar» (la vista previa no
escribe). Las capturas y el resumen quedan en ``--out``.

Esta versión verifica el contrato de #276: la copy de las cuatro procedencias, la ausencia de
pista cuando la fuente no sugiere nada y una tarjeta GCD con ``tradition_guess: None``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import Page, sync_playwright

_COPY_FINAL = "Es solo una pista de la fuente, no de la obra: elige tú."
_PATRONES_PISTA = {
    "explicita": re.compile(
        rf"La fuente lo clasifica como (?P<etiqueta>.+?)\. {re.escape(_COPY_FINAL)}"
    ),
    "transformada": re.compile(
        rf"La fuente no usa esta tradición: a partir de sus datos se sugiere "
        rf"(?P<etiqueta>.+?)\. {re.escape(_COPY_FINAL)}"
    ),
    "por_defecto": re.compile(
        rf"La fuente no indica tradición: se sugiere (?P<etiqueta>.+?) por defecto\. "
        rf"{re.escape(_COPY_FINAL)}"
    ),
    "desconocida": re.compile(
        rf"La fuente sugiere (?P<etiqueta>.+?), pero no consta de dónde sale\. "
        rf"{re.escape(_COPY_FINAL)}"
    ),
}
_PROCEDENCIAS = frozenset(_PATRONES_PISTA)


def _comprobar(condicion: bool, mensaje: str) -> None:
    if not condicion:
        raise AssertionError(mensaje)


def _slug(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalizado.lower()).strip("-") or "consulta"


def _resumen_tarjetas(page: Page) -> dict:
    return page.evaluate(
        """() => {
          const tarjetas = [...document.querySelectorAll('#resultados-descubrir .discovery-card')];
          return {
            n: tarjetas.length,
            tarjetas: tarjetas.map(t => {
              const titulo = t.querySelector('.discovery-card-title');
              const rotulo = t.querySelector('.rotulo');
              const pista = t.querySelector('small');
              const s = t.querySelector('select[name="tradition"]');
              return {
                titulo: titulo ? titulo.innerText.trim() : null,
                fuente: rotulo ? rotulo.innerText.trim() : null,
                pista: pista ? pista.innerText.trim() : null,
                select: s ? {
                  required: s.required,
                  value: s.value,
                  seleccionados: [...s.selectedOptions].map(o => o.value),
                } : null,
              };
            }),
          };
        }"""
    )


def _procedencia_de(pista: str | None) -> str | None:
    """La procedencia que declara una pista, o ``None`` si no hay pista.

    Devuelve ``"invalida"`` si hay texto pero no es una de las cuatro formulaciones de #276.
    """
    if not pista:
        return None
    for nombre, patron in _PATRONES_PISTA.items():
        if patron.fullmatch(pista):
            return nombre
    return "invalida"


def _etiqueta_de_pista(pista: str | None) -> str:
    if not pista:
        return "sin sugerencia"
    for patron in _PATRONES_PISTA.values():
        match = patron.fullmatch(pista)
        if match:
            return match.group("etiqueta")
    return "desconocida"


def _procedencias(datos: dict) -> list[str | None]:
    return [_procedencia_de(t["pista"]) for t in datos["tarjetas"]]


def _comprobar_presentacion(datos: dict, consulta: str) -> None:
    tarjetas = datos["tarjetas"]
    _comprobar(datos["n"] > 0, f"La búsqueda «{consulta}» no devolvió ninguna tarjeta.")
    _comprobar(
        all(t["select"] is not None for t in tarjetas),
        "Hay una tarjeta sin selector de tradición.",
    )
    _comprobar(
        all(t["select"]["required"] for t in tarjetas),
        "Algún selector de tradición no es obligatorio.",
    )
    _comprobar(
        all(t["select"]["value"] == "" for t in tarjetas),
        "Algún selector trae un valor preseleccionado.",
    )
    _comprobar(
        all(t["select"]["seleccionados"] == [""] for t in tarjetas),
        "Algún selector trae una tradición seleccionada por defecto.",
    )

    procedencias = _procedencias(datos)
    _comprobar(
        all(p is None or p in _PROCEDENCIAS for p in procedencias),
        f"Alguna tarjeta lleva una pista que no es la copy de #276: {datos['tarjetas']}",
    )
    _comprobar(
        any(p is not None for p in procedencias),
        f"La búsqueda «{consulta}» no mostró ninguna pista de tradición.",
    )
    _comprobar(
        any(p in {"transformada", "por_defecto", "desconocida"} for p in procedencias),
        f"La búsqueda «{consulta}» no ejercitó ninguna de las procedencias nuevas de #276.",
    )


def _pistas_por_valor(datos: dict) -> dict[str, int]:
    cuenta: Counter[str] = Counter(
        _etiqueta_de_pista(t["pista"]) for t in datos["tarjetas"] if t["pista"]
    )
    return dict(cuenta)


def _pistas_por_procedencia(datos: dict) -> dict[str, int]:
    cuenta: Counter[str] = Counter(
        procedencia if procedencia is not None else "sin_sugerencia"
        for procedencia in _procedencias(datos)
    )
    return dict(cuenta)


def _abrir_busqueda(page: Page, base_url: str, consulta: str) -> dict:
    page.goto(
        f"{base_url}/ui/descubrir?q={quote(consulta)}",
        wait_until="networkidle",
        timeout=90_000,
    )
    page.wait_for_selector("#resultados-descubrir .discovery-card", timeout=90_000)
    page.wait_for_timeout(1_000)
    return _resumen_tarjetas(page)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8768")
    parser.add_argument("--out", default="/tmp/u15-verificacion")
    parser.add_argument("--consulta", default="Mortadelo")
    parser.add_argument("--consulta-sin-sugerencia", default="Lucky Luke")
    parser.add_argument("--sha", default=os.environ.get("ZASCARR_SHA", ""))
    parser.add_argument("--chrome", default=os.environ.get("CHROME_PATH", "/usr/bin/google-chrome"))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ahora = datetime.now(UTC)
    prefijo = ahora.strftime("%Y-%m-%d")
    slug_consulta = _slug(args.consulta)
    slug_nula = _slug(args.consulta_sin_sugerencia)

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
            fuentes.get("gcd") == "enabled" and fuentes.get("tebeosfera") == "enabled",
            f"Las fuentes de U15 no están activas: {fuentes}",
        )

        caja = page.locator('input[name="q"]')
        caja.click()
        caja.press_sequentially(args.consulta, delay=40)
        page.wait_for_selector("#resultados-descubrir .discovery-card", timeout=45_000)
        page.wait_for_timeout(1_000)

        datos = _resumen_tarjetas(page)
        _comprobar_presentacion(datos, args.consulta)
        captura_consulta = f"{prefijo}-descubrir-{slug_consulta}-1280.png"
        page.screenshot(path=str(out / captura_consulta), full_page=True)

        indice_nulo = next(
            (
                i
                for i, tarjeta in enumerate(datos["tarjetas"])
                if not tarjeta["pista"] and tarjeta["fuente"] == "GCD"
            ),
            None,
        )
        captura_gcd_nula = None
        if indice_nulo is not None:
            tarjeta_nula = page.locator("#resultados-descubrir .discovery-card").nth(indice_nulo)
            tarjeta_nula.scroll_into_view_if_needed()
            page.wait_for_timeout(300)
            captura_gcd_nula = f"{prefijo}-descubrir-{slug_consulta}-gcd-sin-sugerencia-1280.png"
            tarjeta_nula.screenshot(path=str(out / captura_gcd_nula))

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
        captura_movil = f"{prefijo}-descubrir-{slug_consulta}-360.png"
        page.screenshot(path=str(out / captura_movil), full_page=True)
        page.set_viewport_size({"width": 1280, "height": 900})

        indice = next(
            (
                i
                for i, tarjeta in enumerate(datos["tarjetas"])
                if tarjeta["pista"] and "Tebeo español" in tarjeta["pista"]
            ),
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
            "Procedencia de la sugerencia: valor por defecto" in texto_preview,
            "La vista previa no muestra la procedencia de la sugerencia.",
        )
        _comprobar(
            "Crear serie vacía" in texto_preview,
            "La vista previa no ofrece el paso de creación.",
        )
        captura_revision = f"{prefijo}-descubrir-revision-manga-1280.png"
        page.screenshot(path=str(out / captura_revision), full_page=True)

        datos_nula = _abrir_busqueda(page, args.base_url, args.consulta_sin_sugerencia)
        _comprobar_presentacion(datos_nula, args.consulta_sin_sugerencia)
        sin_pista = [t for t in datos_nula["tarjetas"] if not t["pista"]]
        _comprobar(
            all(t["fuente"] == "GCD" for t in sin_pista),
            f"Hay tarjetas sin pista que no son GCD: {sin_pista}",
        )
        gcd_sin_pista = [t for t in sin_pista if t["fuente"] == "GCD"]
        _comprobar(
            bool(gcd_sin_pista),
            f"La búsqueda «{args.consulta_sin_sugerencia}» no devolvió ninguna tarjeta "
            "GCD con tradition_guess None.",
        )
        for tarjeta_nula in gcd_sin_pista:
            _comprobar(
                tarjeta_nula["select"] is not None
                and tarjeta_nula["select"]["required"]
                and tarjeta_nula["select"]["value"] == ""
                and tarjeta_nula["select"]["seleccionados"] == [""],
                f"La tarjeta GCD sin sugerencia no tiene el selector vacío: {tarjeta_nula}",
            )
        captura_nula = f"{prefijo}-descubrir-{slug_nula}-gcd-sin-sugerencia-1280.png"
        page.screenshot(path=str(out / captura_nula), full_page=True)

        resumen = {
            "fecha_utc": ahora.isoformat(timespec="seconds"),
            "sha": args.sha,
            "base_url": args.base_url,
            "consulta": args.consulta,
            "consulta_sin_sugerencia": args.consulta_sin_sugerencia,
            "navegador": browser.version,
            "user_agent": page.evaluate("navigator.userAgent"),
            "viewport_escritorio": {"width": 1280, "height": 900},
            "viewport_movil": movil,
            "n_tarjetas": datos["n"],
            "selects": {
                "total": len(datos["tarjetas"]),
                "obligatorios": sum(1 for t in datos["tarjetas"] if t["select"]["required"]),
                "vacios": sum(1 for t in datos["tarjetas"] if t["select"]["value"] == ""),
                "con_tradicion_preseleccionada": sum(
                    1 for t in datos["tarjetas"] if t["select"]["seleccionados"] != [""]
                ),
            },
            "pistas_por_procedencia": _pistas_por_procedencia(datos),
            "pistas_por_valor": _pistas_por_valor(datos),
            "tarjetas_sin_pista": [
                {"titulo": t["titulo"], "fuente": t["fuente"]}
                for t in datos["tarjetas"]
                if not t["pista"]
            ],
            "captura_gcd_sin_pista": captura_gcd_nula,
            "eleccion": {
                "tarjeta": datos["tarjetas"][indice]["titulo"],
                "procedencia": _procedencia_de(datos["tarjetas"][indice]["pista"]),
                "sugerencia": "Tebeo español",
                "elegida": "Manga",
                "vista_previa": texto_preview,
            },
            "sin_sugerencia": {
                "consulta": args.consulta_sin_sugerencia,
                "n_tarjetas": datos_nula["n"],
                "tarjetas_gcd": sum(1 for t in datos_nula["tarjetas"] if t["fuente"] == "GCD"),
                "gcd_sin_pista": [
                    {"titulo": t["titulo"], "fuente": t["fuente"]} for t in gcd_sin_pista
                ],
                "selects_vacios": all(
                    t["select"]["required"]
                    and t["select"]["value"] == ""
                    and t["select"]["seleccionados"] == [""]
                    for t in gcd_sin_pista
                ),
                "sin_texto_de_pista": all(not t["pista"] for t in gcd_sin_pista),
                "captura": captura_nula,
            },
            "capturas": [
                captura_consulta,
                captura_movil,
                captura_revision,
                captura_nula,
                *([captura_gcd_nula] if captura_gcd_nula else []),
            ],
        }
        (out / "verificacion-navegador.json").write_text(
            json.dumps(resumen, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(resumen, ensure_ascii=False, indent=2))
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
