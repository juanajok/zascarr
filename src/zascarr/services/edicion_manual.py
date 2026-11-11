"""BL-INF5 (#591): edición manual de metadatos de serie y número.

Escribe SOLO la base de datos: no toca archivos, rutas, relaciones ni `metadata_source`.
Cada campo realmente editado queda en `metadata_["manual"][campo]` con fecha y en
`locked_fields`; desbloquear retira ambas marcas sin borrar el valor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.models import Issue, IssueFormat, MetadataSource, Publisher, Series

CAMPOS_SERIE = ("title", "start_year", "end_year", "publisher", "description", "total_issues")
CAMPOS_NUMERO = ("issue_number", "title", "release_date", "format", "synopsis")

MAX_TITULO = 500
MAX_TEXTO = 10_000
MAX_EDITORIAL = 255
MAX_NUMERO = 20


@dataclass
class ResultadoEdicion:
    ok: bool
    errores: dict[str, str] = field(default_factory=dict)
    cambios: dict[str, object] = field(default_factory=dict)


def _marcar(metadata: dict | None, campos: list[str], ahora: datetime) -> dict:
    meta = dict(metadata or {})
    manual = dict(meta.get("manual") or {})
    for campo in campos:
        manual[campo] = {"fecha": ahora.isoformat()}
    meta["manual"] = manual
    return meta


def _desmarcar(metadata: dict | None, campo: str) -> dict:
    meta = dict(metadata or {})
    manual = dict(meta.get("manual") or {})
    manual.pop(campo, None)
    if manual:
        meta["manual"] = manual
    else:
        meta.pop("manual", None)
    return meta


def _sin_lock(bloqueados: list[str] | None, campo: str) -> list[str]:
    return [c for c in (bloqueados or []) if c != campo]


def _anio(valor: str, etiqueta: str, errores: dict[str, str]) -> int | None:
    texto = (valor or "").strip()
    if not texto:
        return None
    if not texto.isdigit():
        errores[etiqueta] = "Escribe el año con números (por ejemplo, 1987)."
        return None
    numero = int(texto)
    if not 1000 <= numero <= 9999:
        errores[etiqueta] = "El año tiene que estar entre 1000 y 9999."
        return None
    return numero


def _entero(
    valor: str, etiqueta: str, errores: dict[str, str], *, maximo: int | None = None
) -> int | None:
    texto = (valor or "").strip()
    if not texto:
        return None
    if not texto.isdigit():
        errores[etiqueta] = "Escribe un número entero igual o mayor que 0."
        return None
    numero = int(texto)
    if maximo is not None and numero > maximo:
        errores[etiqueta] = f"El valor no puede superar {maximo}."
        return None
    return numero


def _sort_order(numero: str | None) -> float | None:
    """Orden estable a partir del primer número de la numeración; None si no es numérico."""
    if not numero:
        return None
    m = re.match(r"\s*(\d+(?:[.,]\d+)?)", numero)
    return float(m.group(1).replace(",", ".")) if m else None


async def _publisher(db: AsyncSession, nombre: str):
    if not nombre:
        return None
    existente = (await db.execute(
        select(Publisher).where(func.lower(Publisher.name) == nombre.casefold())
    )).scalar_one_or_none()
    if existente is not None:
        return existente
    nueva = Publisher(name=nombre, metadata_source=MetadataSource.MANUAL.value)
    db.add(nueva)
    await db.flush()
    return nueva


async def guardar_serie(
    db: AsyncSession, series_id: UUID, *,
    title: str, start_year: str, end_year: str, publisher: str,
    description: str, total_issues: str,
) -> ResultadoEdicion:
    serie = (await db.execute(
        select(Series).options(selectinload(Series.publisher))
        .where(Series.id == series_id))).scalar_one_or_none()
    if serie is None:
        return ResultadoEdicion(False, {"general": "La serie ya no existe."})
    errores: dict[str, str] = {}
    titulo = (title or "").strip()
    if not titulo:
        errores["title"] = "El título no puede estar vacío."
    elif len(titulo) > MAX_TITULO:
        errores["title"] = f"El título no puede superar {MAX_TITULO} caracteres."
    inicio = _anio(start_year, "start_year", errores)
    fin = _anio(end_year, "end_year", errores)
    if inicio is not None and fin is not None and inicio > fin:
        errores["end_year"] = "El año de fin no puede ser anterior al de inicio."
    total = _entero(total_issues, "total_issues", errores, maximo=100_000)
    sinopsis = (description or "").strip()
    if len(sinopsis) > MAX_TEXTO:
        errores["description"] = f"La sinopsis no puede superar {MAX_TEXTO} caracteres."
    editorial = (publisher or "").strip()
    if len(editorial) > MAX_EDITORIAL:
        errores["publisher"] = f"La editorial no puede superar {MAX_EDITORIAL} caracteres."
    if errores:
        return ResultadoEdicion(False, errores, {
            "title": title, "start_year": start_year, "end_year": end_year,
            "publisher": publisher, "description": description, "total_issues": total_issues})

    nueva_editorial = await _publisher(db, editorial)
    cambios: dict[str, object] = {}
    if titulo != (serie.title or ""):
        serie.title = titulo
        cambios["title"] = titulo
    if inicio != serie.start_year:
        serie.start_year = inicio
        cambios["start_year"] = inicio
    if fin != serie.end_year:
        serie.end_year = fin
        cambios["end_year"] = fin
    if (serie.publisher.name if serie.publisher else "") != editorial:
        serie.publisher = nueva_editorial
        cambios["publisher"] = editorial
    if sinopsis != (serie.description or ""):
        serie.description = sinopsis or None
        cambios["description"] = sinopsis
    if total != serie.total_issues:
        serie.total_issues = total
        cambios["total_issues"] = total
    if cambios:
        ahora = datetime.now(UTC)
        serie.metadata_ = _marcar(serie.metadata_, list(cambios), ahora)
        serie.locked_fields = list(dict.fromkeys([*(serie.locked_fields or []), *cambios]))
        await db.flush()
    return ResultadoEdicion(True, cambios=cambios)


async def desbloquear_serie(db: AsyncSession, series_id: UUID, campo: str) -> bool:
    if campo not in CAMPOS_SERIE:
        return False
    serie = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if serie is None:
        return False
    serie.locked_fields = _sin_lock(serie.locked_fields, campo)
    serie.metadata_ = _desmarcar(serie.metadata_, campo)
    await db.flush()
    return True


async def guardar_numero(
    db: AsyncSession, series_id: UUID, issue_id: UUID, *,
    issue_number: str, title: str, release_date: str, format: str, synopsis: str,
) -> ResultadoEdicion:
    issue = (await db.execute(
        select(Issue).where(Issue.id == issue_id, Issue.series_id == series_id)
    )).scalar_one_or_none()
    if issue is None:
        return ResultadoEdicion(False, {"general": "El número ya no existe."})
    errores: dict[str, str] = {}
    numero = (issue_number or "").strip()
    if not numero:
        errores["issue_number"] = "El número no puede estar vacío."
    elif len(numero) > MAX_NUMERO:
        errores["issue_number"] = f"El número no puede superar {MAX_NUMERO} caracteres."
    titulo = (title or "").strip()
    if len(titulo) > MAX_TITULO:
        errores["title"] = f"El título no puede superar {MAX_TITULO} caracteres."
    fecha_txt = (release_date or "").strip()
    fecha: date | None = None
    if fecha_txt:
        try:
            fecha = date.fromisoformat(fecha_txt)
        except ValueError:
            errores["release_date"] = "Escribe la fecha como AAAA-MM-DD o déjala vacía."
    formato_txt = (format or IssueFormat.SINGLE_ISSUE.value).strip()
    try:
        formato = IssueFormat(formato_txt)
    except ValueError:
        errores["format"] = "Elige un formato de la lista."
        formato = IssueFormat.SINGLE_ISSUE
    sinopsis = (synopsis or "").strip()
    if len(sinopsis) > MAX_TEXTO:
        errores["synopsis"] = f"La sinopsis no puede superar {MAX_TEXTO} caracteres."
    if not errores and numero:
        colision = (await db.execute(
            select(Issue.id).where(
                Issue.series_id == series_id, Issue.issue_number == numero,
                Issue.volume == (issue.volume or 1), Issue.id != issue_id)
        )).scalar_one_or_none()
        if colision is not None:
            errores["issue_number"] = (
                f"Ya existe el nº {numero} en esta serie. Elige otro número.")
    if errores:
        return ResultadoEdicion(False, errores, {
            "issue_number": issue_number, "title": title, "release_date": release_date,
            "format": format, "synopsis": synopsis})

    cambios: dict[str, object] = {}
    if numero != (issue.issue_number or ""):
        issue.issue_number = numero
        issue.sort_order = _sort_order(numero)
        cambios["issue_number"] = numero
    if titulo != (issue.title or ""):
        issue.title = titulo or None
        cambios["title"] = titulo
    if fecha != issue.release_date:
        issue.release_date = fecha
        cambios["release_date"] = fecha
    if formato != issue.format:
        issue.format = formato
        cambios["format"] = formato.value
    if sinopsis != (issue.synopsis or ""):
        issue.synopsis = sinopsis or None
        cambios["synopsis"] = sinopsis
    if cambios:
        issue.metadata_ = _marcar(issue.metadata_, list(cambios), datetime.now(UTC))
        issue.locked_fields = list(dict.fromkeys([*(issue.locked_fields or []), *cambios]))
        await db.flush()
    return ResultadoEdicion(True, cambios=cambios)


async def desbloquear_numero(db: AsyncSession, series_id: UUID, issue_id: UUID, campo: str) -> bool:
    if campo not in CAMPOS_NUMERO:
        return False
    issue = (await db.execute(
        select(Issue).where(Issue.id == issue_id, Issue.series_id == series_id)
    )).scalar_one_or_none()
    if issue is None:
        return False
    issue.locked_fields = _sin_lock(issue.locked_fields, campo)
    issue.metadata_ = _desmarcar(issue.metadata_, campo)
    await db.flush()
    return True


def campos_manuales(metadata: dict | None) -> dict:
    manual = (metadata or {}).get("manual") if isinstance(metadata, dict) else None
    return manual if isinstance(manual, dict) else {}
