"""CCM-0 (#999): diagnóstico de cobertura de metadatos; y backfill estricto.

Por defecto **no escribe**: diagnostica la cobertura de la Capa de Consolidación
de Metadatos (CCM). Con `--backfill` cuenta los campos cuyo valor actual coincide
exactamente con el de su registro de fuente; con `--backfill --apply` escribe
esas filas de `field_provenance` (solo la procedencia, nunca el valor).

    python -m zascarr.cli.consolidacion
    python -m zascarr.cli.consolidacion --json
    python -m zascarr.cli.consolidacion --backfill --json
    python -m zascarr.cli.consolidacion --backfill --apply

No consulta fuentes externas ni toca la biblioteca. En la Pi se ejecuta dentro
del contenedor; no requiere Python en el host.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import async_session_factory, engine
from zascarr.models import (
    Collection,
    EntitySourceRecord,
    FieldProvenance,
    File,
    Issue,
    Series,
)
from zascarr.services.consolidacion.backfill import BackfillEstricto

#: IDs externos que ya existen como columnas paralelas. El orden es el de la
#: ficha de referencia normalizada; no implica prioridad.
IDS_SERIE = (
    "comic_vine_id", "anilist_id", "tebeosfera_slug", "gcd_id",
    "metron_id", "open_library_id", "fandom_dc_slug", "fandom_marvel_slug",
)
IDS_ISSUE = (
    "comic_vine_id", "gcd_id", "metron_id", "anilist_id",
    "tebeosfera_slug", "fandom_dc_slug", "fandom_marvel_slug",
)
CAMPOS_SERIE = (
    "start_year", "end_year", "description", "publisher_id", "language",
    "edition_kind", "total_issues", "cover_url",
)
CAMPOS_ISSUE = (
    "title", "release_date", "page_count", "isbn", "synopsis", "cover_url",
)


async def _contar(db: AsyncSession, modelo) -> int:
    return int((await db.execute(select(func.count()).select_from(modelo))).scalar() or 0)


async def _cobertura(db: AsyncSession, modelo, campos: tuple[str, ...]) -> dict[str, int]:
    salida: dict[str, int] = {}
    for campo in campos:
        salida[campo] = int((await db.execute(
            select(func.count()).select_from(modelo).where(getattr(modelo, campo).is_not(None))
        )).scalar() or 0)
    return salida


async def _ids(db: AsyncSession, modelo, campos: tuple[str, ...]) -> dict[str, object]:
    filas = (await db.execute(select(*(getattr(modelo, campo) for campo in campos)))).all()
    por_campo = {campo: sum(1 for fila in filas if fila[i] is not None)
                 for i, campo in enumerate(campos)}
    con_alguno = sum(1 for fila in filas if any(valor is not None for valor in fila))
    multi = sum(1 for fila in filas if sum(valor is not None for valor in fila) >= 2)
    return {
        "por_campo": por_campo,
        "con_alguno": con_alguno,
        "sin_ninguno": len(filas) - con_alguno,
        "con_mas_de_uno": multi,
        "total_filas": len(filas),
    }


async def diagnosticar(db: AsyncSession) -> dict:
    """Devuelve el informe completo. Solo ejecuta SELECT."""
    series_total = await _contar(db, Series)
    issues_total = await _contar(db, Issue)
    archivos = await _contar(db, File)
    colecciones = await _contar(db, Collection)
    series = await _ids(db, Series, IDS_SERIE)
    issues = await _ids(db, Issue, IDS_ISSUE)
    series_campos = await _cobertura(db, Series, CAMPOS_SERIE)
    issue_campos = await _cobertura(db, Issue, CAMPOS_ISSUE)

    fuentes = dict((await db.execute(
        select(EntitySourceRecord.source, func.count())
        .group_by(EntitySourceRecord.source)
    )).all())
    procedencia = dict((await db.execute(
        select(FieldProvenance.entity_type, func.count())
        .group_by(FieldProvenance.entity_type)
    )).all())
    metadata_source = dict((await db.execute(
        select(Series.metadata_source, func.count())
        .group_by(Series.metadata_source)
    )).all())
    series_con_roles = int((await db.execute(
        select(func.count()).select_from(Series)
        .where(Series.metadata_.has_key("vinculos_rol"))
    )).scalar() or 0)
    series_bloqueadas = int((await db.execute(
        select(func.count()).select_from(Series)
        .where(func.cardinality(Series.locked_fields) > 0)
    )).scalar() or 0)

    return {
        "generado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "totales": {
            "series": series_total,
            "issues": issues_total,
            "archivos": archivos,
            "colecciones": colecciones,
        },
        "series": {
            "ids": series,
            "campos": series_campos,
            "con_roles": series_con_roles,
            "con_locks": series_bloqueadas,
        },
        "issues": {"ids": issues, "campos": issue_campos},
        "tablas_0032": {
            "entity_source_records": sum(fuentes.values()),
            "field_provenance": sum(procedencia.values()),
            "por_fuente": {str(k): int(v) for k, v in fuentes.items()},
            "por_entidad": {str(k): int(v) for k, v in procedencia.items()},
        },
        "metadata_source_serie": {
            str(k) if k is not None else "sin_fuente": int(v)
            for k, v in metadata_source.items()
        },
    }


def _tabla(informe: dict) -> str:
    s, i = informe["series"], informe["issues"]
    t = informe["tablas_0032"]
    lineas = [
        "CCM · diagnóstico de metadatos (solo lectura)",
        f"  generado: {informe['generado_en']}",
        "",
        f"Series: {informe['totales']['series']} · issues: {informe['totales']['issues']} "
        f"· archivos: {informe['totales']['archivos']} "
        f"· colecciones: {informe['totales']['colecciones']}",
        "",
        "IDs de serie:",
    ]
    for campo, n in s["ids"]["por_campo"].items():
        lineas.append(f"  {campo:<20} {n:>6}")
    lineas += [
        f"  con algún ID: {s['ids']['con_alguno']} · sin ninguno: {s['ids']['sin_ninguno']} "
        f"· con más de uno: {s['ids']['con_mas_de_uno']}",
        "",
        "Campos de serie:",
    ]
    for campo, n in s["campos"].items():
        lineas.append(f"  {campo:<20} {n:>6}")
    lineas += [
        f"  roles declarados: {s['con_roles']} · series con locks: {s['con_locks']}",
        "",
        "IDs de issue:",
    ]
    for campo, n in i["ids"]["por_campo"].items():
        lineas.append(f"  {campo:<20} {n:>6}")
    lineas += [
        f"  con algún ID: {i['ids']['con_alguno']} · sin ninguno: {i['ids']['sin_ninguno']} "
        f"· con más de uno: {i['ids']['con_mas_de_uno']}",
        "",
        "Campos de issue:",
    ]
    for campo, n in i["campos"].items():
        lineas.append(f"  {campo:<20} {n:>6}")
    lineas += [
        "",
        "Tablas de la migración 0032:",
        f"  entity_source_records: {t['entity_source_records']}",
        f"  field_provenance:      {t['field_provenance']}",
        f"  por fuente: {t['por_fuente'] or '—'}",
        f"  por entidad: {t['por_entidad'] or '—'}",
        "",
        f"metadata_source de serie: {informe['metadata_source_serie'] or '—'}",
    ]
    return "\n".join(lineas)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="zascarr-consolidacion",
        description="Diagnóstico de cobertura de metadatos de la CCM (solo lectura).",
    )
    p.add_argument("--json", action="store_true", help="salida JSON para automatizar")
    p.add_argument(
        "--backfill", action="store_true",
        help="backfill estricto de field_provenance desde los registros de fuente",
    )
    p.add_argument(
        "--apply", action="store_true",
        help="con --backfill, escribe; sin ello solo cuenta (vista previa)",
    )
    p.add_argument(
        "--limite", type=int, default=None,
        help="máximo de series a revisar en el backfill",
    )
    return p


def _tabla_backfill(res: dict) -> str:
    modo = "APLICADO" if not res["preview"] else "VISTA PREVIA (no escribe)"
    lineas = [
        f"CCM · backfill estricto de procedencia — {modo}",
        f"  series revisadas: {res['series']}",
        f"  campos que coinciden: {res['filas']}",
        f"  campos con fuente pero sin coincidencia: {res['sin_coincidencia']}",
        f"  por fuente: {res['por_fuente'] or '—'}",
    ]
    if res["preview"]:
        lineas.append("  Para escribir: añade --apply.")
    return "\n".join(lineas)


async def _ejecutar(args: argparse.Namespace) -> int:
    if args.apply and not args.backfill:
        print("--apply solo tiene sentido con --backfill", file=sys.stderr)
        return 2
    if args.backfill:
        async with async_session_factory() as db:
            informe = await BackfillEstricto(db).ejecutar(
                preview=not args.apply, limite=args.limite)
            if args.apply:
                await db.commit()
        res = {
            "modo": "backfill_estricto", "preview": informe.preview,
            "series": informe.series, "filas": informe.filas,
            "sin_coincidencia": informe.sin_coincidencia,
            "por_fuente": informe.por_fuente,
        }
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(_tabla_backfill(res))
        return 0
    async with async_session_factory() as db:
        informe = await diagnosticar(db)
    if args.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(_tabla(informe))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    async def _main() -> int:
        try:
            return await _ejecutar(args)
        finally:
            await engine.dispose()

    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
