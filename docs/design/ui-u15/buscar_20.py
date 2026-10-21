#!/usr/bin/env python3
"""U15 (#202): 20 búsquedas reales contra las fuentes públicas disponibles.

- GCD y Tebeosfera: se consultan de verdad, con sus límites de cortesía.
- AniList: el 2026-10-21 su API respondió 403 «temporarily disabled»; se registra NOT RUN.
- Comic Vine: requiere API key; sin clave en este entorno, se registra NOT RUN.

No usa la base de datos ni la app. Guarda `resultados-reales.json` y
`resultados-reales.md` junto a este script.

Uso (en el contenedor de la app, con el repo montado):
    PYTHONPATH=/work/src python docs/design/ui-u15/buscar_20.py
"""
from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from zascarr.services.gcd import GCDClient
from zascarr.services.tebeosfera import TebeosferaClient

DOC = Path(__file__).parent
LIMIT = 3


REPO = DOC.parents[3]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), *args],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "desconocido"


def _commits() -> dict[str, str]:
    return {
        "producto": _git("rev-parse", "--short", "origin/main"),
        "rama": _git("rev-parse", "--short", "HEAD"),
    }


async def _buscar_gcd(cliente: GCDClient, titulo: str) -> dict:
    try:
        resultados = await cliente.search_series(titulo, limit=LIMIT)
    except Exception as exc:  # noqa: BLE001 - una fuente no tumba la medición
        return {"estado": "error", "detalle": f"{type(exc).__name__}: {exc}", "resultados": []}
    return {
        "estado": "ok",
        "resultados": [
            {
                "titulo": r.name,
                "anio": r.year_began,
                "id": r.gcd_id,
                "idioma": r.language,
                "pais": r.country,
                "sugerencia": r.tradition_guess,
                "url": r.site_url,
            }
            for r in resultados
        ],
    }


async def _buscar_tebeosfera(cliente: TebeosferaClient, titulo: str) -> dict:
    try:
        resultados = await cliente.search_series(titulo, limit=LIMIT)
    except Exception as exc:  # noqa: BLE001
        return {"estado": "error", "detalle": f"{type(exc).__name__}: {exc}", "resultados": []}
    return {
        "estado": "ok",
        "resultados": [
            {
                "titulo": r.title,
                "anio": r.start_year,
                "id": r.slug,
                "tipo": r.kind,
                "sugerencia": "tebeo",
                "url": r.site_url,
            }
            for r in resultados
        ],
    }


def _coincide(resultados: list[dict], referencia: str) -> tuple[bool | None, bool]:
    if not resultados:
        return None, False
    return resultados[0]["sugerencia"] == referencia, any(
        r["sugerencia"] == referencia for r in resultados
    )


async def main() -> None:
    datos = json.loads((DOC / "titulos.json").read_text(encoding="utf-8"))
    consultas = []
    async with GCDClient() as gcd, TebeosferaClient() as tebe:
        for i, t in enumerate(datos["titulos"], 1):
            titulo, referencia = t["titulo"], t["referencia"]
            print(f"[{i:02d}/{len(datos['titulos'])}] {titulo}", flush=True)
            gcd_r = await _buscar_gcd(gcd, titulo)
            tebe_r = await _buscar_tebeosfera(tebe, titulo)
            gcd_primero, gcd_alguno = _coincide(gcd_r["resultados"], referencia)
            tebe_primero, tebe_alguno = _coincide(tebe_r["resultados"], referencia)
            consultas.append({
                "titulo": titulo,
                "referencia": referencia,
                "gcd": gcd_r,
                "tebeosfera": tebe_r,
                "coincide_primero": {"gcd": gcd_primero, "tebeosfera": tebe_primero},
                "coincide_alguno": {"gcd": gcd_alguno, "tebeosfera": tebe_alguno},
            })

    commits = _commits()
    salida = {
        "fecha": datetime.now(UTC).isoformat(timespec="seconds"),
        "commit_producto": commits["producto"],
        "commit_rama": commits["rama"],
        "limit_por_fuente": LIMIT,
        "aviso": (
            "Búsquedas reales contra GCD y Tebeosfera. AniList no estaba disponible "
            "(403, API deshabilitada temporalmente) y Comic Vine no tiene API key en este "
            "entorno. No se ha usado la app ni la base de datos."
        ),
        "fuentes": {
            "gcd": {"estado": "ok", "detalle": "API pública, sin clave"},
            "tebeosfera": {"estado": "ok", "detalle": "scraping, límite 2,5 s"},
            "anilist": {
                "estado": "no_disponible",
                "detalle": (
                    "403: The AniList API has been temporarily disabled due to severe "
                    "stability issues."
                ),
            },
            "comic_vine": {
                "estado": "no_disponible",
                "detalle": "sin COMICVINE_API_KEY en este entorno",
            },
        },
        "consultas": consultas,
    }
    (DOC / "resultados-reales.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _escribir_markdown(salida)
    print("\nGuardados resultados-reales.json y resultados-reales.md")


def _si(v: bool | None) -> str:
    if v is None:
        return "sin resultados"
    return "sí" if v else "NO"


def _escribir_markdown(salida: dict) -> None:
    lineas = [
        "# U15 — Resultados reales de las 20 búsquedas (2026-10-21)",
        "",
        f"- **Fecha:** {salida['fecha']}",
        f"- **Commit de producto:** `{salida['commit_producto']}`",
        f"- **Commit de la rama de evidencia:** `{salida['commit_rama']}`",
        f"- **Límite por fuente:** {salida['limit_por_fuente']} resultados",
        "- **Fuentes consultadas de verdad:** GCD y Tebeosfera.",
        "- **No disponibles:** AniList (403, API deshabilitada temporalmente) y "
        "Comic Vine (sin API key).",
        "",
        "> Esta medición **no incluye Comic Vine ni AniList**. Por tanto, no mide la sugerencia",
        "> «Grapa americana» de Comic Vine que originó U15; mide las otras dos fuentes y deja",
        "> las dos que faltan como NOT RUN. No se ha usado la app ni la base de datos.",
        "",
        "## Resultado por título",
        "",
        "| Título | Referencia | GCD (1.º) | ¿Coincide? | Tebeosfera (1.º) | ¿Coincide? |",
        "|---|---|---|---|---|---|",
    ]
    for c in salida["consultas"]:
        gcd = c["gcd"]["resultados"]
        tebe = c["tebeosfera"]["resultados"]
        gcd_txt = f"{gcd[0]['titulo']} ({gcd[0]['sugerencia']})" if gcd else "sin resultados"
        tebe_txt = f"{tebe[0]['titulo']} ({tebe[0]['sugerencia']})" if tebe else "sin resultados"
        lineas.append(
            f"| {c['titulo']} | {c['referencia']} | {gcd_txt} | "
            f"{_si(c['coincide_primero']['gcd'])} | {tebe_txt} | "
            f"{_si(c['coincide_primero']['tebeosfera'])} |"
        )

    lineas += ["", "## Recuento descriptivo (primer resultado de cada fuente)", ""]
    for fuente in ("gcd", "tebeosfera"):
        validos = [c for c in salida["consultas"] if c[fuente]["resultados"]]
        aciertos = sum(1 for c in validos if c["coincide_primero"][fuente])
        lineas.append(f"- **{fuente}:** {aciertos}/{len(validos)} coincidencias; "
                      f"{len(salida['consultas']) - len(validos)} sin resultados.")
    lineas += [
        "",
        "## Límites",
        "",
        "- Solo se evalúa el **primer resultado** de cada fuente; la app muestra varios y la",
        "  persona elige. El recuento es descriptivo, no una tasa de acierto del producto.",
        "- Tebeosfera asigna «tebeo» a todo por diseño del cliente; GCD asigna según idioma/país.",
        "- La referencia de tradición de `titulos.json` es provisional y no está verificada",
        "  contra un catálogo externo.",
        "- No se ha medido Comic Vine, que es la fuente del caso Mortadelo.",
        "",
    ]
    (DOC / "resultados-reales.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
