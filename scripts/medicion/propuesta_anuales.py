#!/usr/bin/env python3
"""propuesta_anuales.py — dry-run de clasificación de anuales (SOLO LECTURA).

No crea series, no crea Issues, no mueve archivos. Lee `series`, `issues` y
`files`, aplica el parser de `naming.py` (rama `feat/annuales-fase0`) y escribe
una **propuesta** para revisar antes de tocar la biblioteca:

  - qué serie anual habría que crear y con qué padre;
  - qué archivos irían a esa serie y con qué número;
  - qué enlaces actuales están mal y se propondrían corregir;
  - qué casos son packs/mixtos y no deben convertirse en un Issue anual.

La conexión corre en `BEGIN TRANSACTION READ ONLY`. El script no escribe en la
base ni en la biblioteca; `--json` escribe un fichero local de revisión.

Uso (desde un checkout con esta rama y acceso a la BD):

    DATABASE_URL=postgresql://... python3 scripts/medicion/propuesta_anuales.py --local
    DATABASE_URL=... python3 scripts/medicion/propuesta_anuales.py --local \
        --json /tmp/propuesta.json

`--local` muestra nombres de archivo reales; sin él se seudonimizan. Los títulos
de serie son públicos y se muestran siempre.
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import asyncpg

# La rama fase 0 cambia el parser: un anual conserva «Annual» en la serie y el
# número pegado a la marca gana al año suelto. Si este script se ejecuta con el
# parser antiguo, las propuestas de Shadow/Batman serán peores; por eso avisa.
from zascarr.utils.naming import normalize_series_name, parse_comic_filename

ANUAL_RE = re.compile(r"\b(?:Annual|Anual)\b", re.IGNORECASE)
VOLUMEN_RE = re.compile(r"\b(?:vol(?:umen)?\.?|v)\s*\d+\b", re.IGNORECASE)
RANGO_RE = re.compile(r"\b\d{1,4}\s*[-–]\s*\d{1,4}\b")
ANIO_RE = re.compile(r"\b(?:19|20)\d{2}\b")
# Número regular + «Anual» pegado al final: «Injustice ... #25 - Anual» no es
# un anual puro; es un número con una marca de anual en el subtítulo.
MIXTO_RE = re.compile(
    r"#\s*\d+[A-Za-z]?\s*[-–]\s*(?:annual|anual)\s*$|"
    r"#\s*\d+[A-Za-z]?\s*[-–]\s*(?:annual|anual)\s*\d+",
    re.IGNORECASE,
)


def _norm(valor: str) -> str:
    return normalize_series_name(valor or "")


def _base(valor: str) -> str:
    """Título sin «Annual/Anual», volumen ni año: lo que debería ser el padre."""
    return _norm(ANIO_RE.sub(" ", VOLUMEN_RE.sub(" ", ANUAL_RE.sub(" ", valor or ""))))


def _parent_title(title: str) -> str:
    """Título del padre sin el marcador de volumen que añade la biblioteca."""
    return re.sub(r"\s+", " ", VOLUMEN_RE.sub(" ", title)).strip(" -–—,;")


def _seudonimo(valor: str) -> str:
    return hashlib.sha256(str(valor).encode("utf-8")).hexdigest()[:10]


@dataclass
class Propuesta:
    archivo: str
    archivo_visible: str
    actual_serie: str | None
    actual_numero: str | None
    parser_serie: str
    parser_numero: str
    anual_title: str | None
    padre_id: str | None
    padre_title: str | None
    confianza: str
    accion: str
    motivo: str
    es_pack: bool = False
    numero_actual_distinto: bool = False
    duplicado_hash: int = 0
    notas: list[str] = field(default_factory=list)
    duplicado_numero: int = 0


def _candidatos_padre(parsed_series: str, series: list[dict]) -> list[tuple[dict, float]]:
    base = _base(parsed_series)
    if not base:
        return []
    base_tokens = set(base.split())
    exactos, contenedores = [], []
    for s in series:
        if ANUAL_RE.search(s["title"]):
            continue  # una serie anual no es padre de otra
        variantes = {_norm(s["title"]), _base(s["title"])}
        if base in variantes:
            exactos.append((s, 1.0))
            continue
        for variante in variantes:
            tokens = set(variante.split())
            if base_tokens and base_tokens <= tokens:
                contenedores.append((s, 0.85))
                break
            # Solo un parecido alto y con el padre más corto: «Shadow of the
            # Bat» dentro de «Batman: Shadow of the Bat». Nunca al revés
            # («Green Lantern Corps» NO es «Green Lantern»).
            if tokens and tokens <= base_tokens and base != " ".join(sorted(tokens)):
                ratio = difflib.SequenceMatcher(None, base, variante).ratio()
                if ratio >= 0.90:
                    contenedores.append((s, 0.75))
                    break
    if exactos:
        return exactos
    contenedores.sort(key=lambda x: (-x[1], x[0]["title"]))
    if len(contenedores) == 1:
        return contenedores
    return contenedores[:3]


def _propuesta(fila: dict, series: list[dict], por_hash: Counter, local: bool) -> Propuesta:
    parsed = parse_comic_filename(fila["file_name"])
    stem = Path(fila["file_name"]).stem
    es_pack = bool(RANGO_RE.search(stem) or MIXTO_RE.search(stem))
    candidatos = _candidatos_padre(parsed.series, series)
    padre = candidatos[0][0] if len(candidatos) == 1 else None
    confianza = "alta" if padre and candidatos[0][1] == 1.0 else (
        "media" if padre else "baja")
    if len(candidatos) > 1:
        confianza = "ambigua"

    anual_title = (
        f"{_parent_title(padre['title'])} Annual" if padre else (parsed.series or None)
    )

    numero = parsed.issue_number or ""
    marcador_en_serie = bool(ANUAL_RE.search(parsed.series or ""))
    titulo_raro = bool(re.match(r"^\d", parsed.series or ""))
    actual_serie = fila["serie_actual"]
    actual_numero = fila["numero_actual"]
    numero_actual_distinto = bool(
        actual_numero is not None and numero and str(actual_numero) != numero)

    if es_pack:
        accion = "pack_revisar"
        motivo = "el nombre contiene un rango o un número regular + anual: no es un anual puro"
    elif not parsed.is_annual:
        accion = "revisar"
        motivo = "el parser no lo reconoce como anual"
    elif not numero or not numero.isdigit():
        accion = "revisar"
        motivo = "sin número de anual fiable"
    elif not marcador_en_serie:
        accion = "revisar"
        motivo = ("la marca anual está fuera del título de serie; no se propone "
                  "una serie nueva a ciegas")
    elif titulo_raro:
        accion = "revisar"
        motivo = "el título de serie empieza por cifra; revisar el nombre"
    elif len(candidatos) > 1 and padre is None:
        accion = "revisar"
        motivo = "varios padres posibles"
    elif actual_serie is None:
        if padre is None:
            accion = "crear_serie_sin_padre"
            motivo = (f"sin Issue y sin padre en catálogo; propuesta: "
                      f"{anual_title} #{numero} (serie anual independiente)")
        else:
            accion = "crear_serie_y_enlazar"
            motivo = f"sin Issue; propuesta: {anual_title} #{numero} (padre {padre['title']!r})"
    elif _norm(actual_serie) != _norm(anual_title):
        accion = "reclasificar"
        motivo = f"ahora en «{actual_serie} #{actual_numero}»; propuesta: {anual_title} #{numero}"
    elif numero_actual_distinto:
        accion = "revisar_numero"
        motivo = f"en la serie anual pero el número actual ({actual_numero}) no coincide"
    else:
        accion = "mantener"
        motivo = "ya está en la serie anual correcta"

    if numero_actual_distinto and accion not in ("revisar", "pack_revisar"):
        notas = [f"número actual {actual_numero!r} ≠ parser {numero!r}"]
    else:
        notas = []

    return Propuesta(
        archivo=_seudonimo(fila["file_name"]) if not local else fila["file_name"],
        archivo_visible=fila["file_name"] if local else _seudonimo(fila["file_name"]),
        actual_serie=actual_serie,
        actual_numero=actual_numero,
        parser_serie=parsed.series,
        parser_numero=numero,
        anual_title=anual_title,
        padre_id=str(padre["id"]) if padre else None,
        padre_title=padre["title"] if padre else None,
        confianza=confianza,
        accion=accion,
        motivo=motivo,
        es_pack=es_pack,
        numero_actual_distinto=numero_actual_distinto,
        duplicado_hash=por_hash.get(fila["sha256_hash"] or "", 0),
        notas=notas,
    )


async def _leer(url: str) -> tuple[list[dict], list[dict]]:
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("BEGIN TRANSACTION READ ONLY")
        files = await conn.fetch("""
            SELECT f.id, f.file_name, f.sha256_hash, f.issue_id,
                   i.issue_number AS numero_actual,
                   s.id AS serie_actual_id, s.title AS serie_actual
            FROM files f
            LEFT JOIN issues i ON i.id = f.issue_id
            LEFT JOIN series s ON s.id = i.series_id
            WHERE f.file_name ILIKE '%annual%' OR f.file_name ILIKE '%anual%'
            ORDER BY f.file_name
        """)
        series = await conn.fetch("""
            SELECT id, title, start_year FROM series ORDER BY title
        """)
        return [dict(f) for f in files], [dict(s) for s in series]
    finally:
        await conn.close()


async def main(args: argparse.Namespace) -> int:
    url = os.environ.get("DATABASE_URL") or os.environ.get("TEST_DATABASE_URL")
    if not url:
        print("Falta DATABASE_URL (o TEST_DATABASE_URL).", file=sys.stderr)
        return 2
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    archivos, series = await _leer(url)
    por_hash = Counter(f["sha256_hash"] for f in archivos if f["sha256_hash"])
    propuestas = [_propuesta(f, series, por_hash, args.local) for f in archivos]

    # Dos escaneos distintos del mismo anual no pueden ser dos Issues anuales
    # con el mismo número: se marcan para elegir copia o compartir publicación.
    por_numero = Counter(
        (_norm(p.anual_title or ""), p.parser_numero)
        for p in propuestas
        if p.anual_title and p.parser_numero.isdigit() and not p.es_pack
    )
    for p in propuestas:
        if p.anual_title and p.parser_numero.isdigit() and not p.es_pack:
            clave = (_norm(p.anual_title), p.parser_numero)
            if por_numero[clave] > 1:
                p.duplicado_numero = por_numero[clave]
                if p.accion in ("crear_serie_y_enlazar", "crear_serie_sin_padre"):
                    p.accion = "revisar_numero_repetido"
                    p.motivo = (
                        f"hay {por_numero[clave]} archivos para "
                        f"{p.anual_title} #{p.parser_numero}; decidir copia/publicación")

    resumen = {
        "archivos_anuales": len(propuestas),
        "con_issue": sum(1 for p in propuestas if p.actual_serie),
        "sin_issue": sum(1 for p in propuestas if not p.actual_serie),
        "series_anuales_existentes": sum(
            1 for s in series if ANUAL_RE.search(s["title"])),
        "series_anuales_propuestas": len({
            _norm(p.anual_title) for p in propuestas
            if p.anual_title and p.accion in (
                "crear_serie_y_enlazar", "crear_serie_sin_padre",
                "reclasificar", "mantener")}),
        "propuestas_sin_padre": sum(
            1 for p in propuestas
            if p.accion in ("crear_serie_sin_padre", "reclasificar")
            and p.padre_id is None),
        "acciones": dict(sorted(Counter(p.accion for p in propuestas).items())),
        "packs": sum(1 for p in propuestas if p.es_pack),
        "confianza": dict(sorted(Counter(p.confianza for p in propuestas).items())),
    }

    if args.json:
        destino = Path(args.json)
        destino.write_text(json.dumps({
            "resumen": resumen,
            "series": series,
            "propuestas": [asdict(p) for p in propuestas],
        }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"JSON escrito en {destino} (revisión local; no compartir si incluye nombres)")

    print("\nRESUMEN")
    for clave, valor in resumen.items():
        print(f"  {clave}: {valor}")

    grupos: dict[str, list[Propuesta]] = defaultdict(list)
    for p in propuestas:
        if p.anual_title:
            grupos[_norm(p.anual_title)].append(p)
    print("\nSERIES ANUALES PROPUESTAS")
    for _clave, lista in sorted(grupos.items(), key=lambda x: (-len(x[1]), x[0])):
        p = lista[0]
        print(f"  {p.anual_title!r} | padre={p.padre_title!r} | "
              f"archivos={len(lista)} | confianza={p.confianza}")

    print("\nCASOS QUE NO SE PROPONEN PARA CREAR/ENLAZAR")
    for p in sorted(propuestas, key=lambda x: (x.accion, x.archivo)):
        if p.accion not in (
                "crear_serie_y_enlazar", "crear_serie_sin_padre",
                "reclasificar", "mantener"):
            print(f"  [{p.accion}] {p.archivo_visible} | {p.motivo}")

    print("\nPROPUESTAS DE CAMBIO (hasta 40)")
    cambios = [p for p in sorted(propuestas, key=lambda x: (x.accion, x.archivo))
               if p.accion in ("crear_serie_y_enlazar", "crear_serie_sin_padre",
                               "reclasificar")]
    for p in cambios[:40]:
        print(f"  [{p.accion}] {p.archivo_visible} | {p.motivo}")
    if len(cambios) > 40:
        print(f"  … {len(cambios) - 40} más; usa --json para la lista completa")
    return 0


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run de clasificación de anuales (solo lectura).")
    parser.add_argument("--local", action="store_true",
                        help="Muestra nombres de archivo reales (no compartir la salida).")
    parser.add_argument("--json", help="Escribe la propuesta completa en este JSON local.")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(_args())))
