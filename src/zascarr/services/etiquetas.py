"""Etiquetas manuales por serie (BL-ETQ1a, #403).

Único espacio visible del MVP: `etiqueta` (D-1). El servicio normaliza y valida
el nombre, crea la etiqueta si la persona lo pide desde la ficha (D-6) y escribe
la asignación con `source='manual'` y `weight=NULL`. La relación ORM `Series.tags`
no decide visibilidad: `oculta=false` se filtra aquí.

No toca `Issue.tags`, no lee ni escribe ComicInfo, no llama a fuentes y no pinta
la ficha por sí solo.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Series, Tag, series_tags

NAMESPACE = "etiqueta"
SOURCE_MANUAL = "manual"
MAX_NOMBRE = 64
MIN_SUGERENCIA = 2
MAX_SUGERENCIAS = 8

_ESPACIOS = re.compile(r"\s+")
_NO_ALFANUMERICO = re.compile(r"[^0-9a-z ]+")
#: Letras que `unaccent` translitera y NFKD **no** descompone. Sin esta tabla,
#: `normalize_tag` y `f_tag_norm` divergen en nombres como «Smørrebrød»,
#: «Æon Flux» o «Straße»: la ficha no encontraría la etiqueta que la BD sí
#: guardó. No pretende cubrir todo el diccionario de `unaccent` (símbolos,
#: superíndices, alfabetos no latinos): solo letras de nombres europeos.
_TRANSLITERACION = str.maketrans({
    "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d", "ð": "d",
    "þ": "th", "ı": "i", "ħ": "h", "ŋ": "n", "ŧ": "t", "ĸ": "q",
})


class EtiquetaInvalida(ValueError):  # noqa: N818 — nombre de dominio
    """Nombre que no se puede convertir en una etiqueta válida."""


@dataclass(frozen=True)
class ResultadoEtiqueta:
    tag: Tag | None
    mensaje: str
    cambio: bool


def normalize_tag(texto: str | None) -> str:
    """Espejo Python de `f_tag_norm`: NFKC/NFKD, sin acentos, minúsculas y
    solo alfanumérico separado por espacios. Conserva artículos.

    Las letras que `unaccent` translitera y NFKD no descompone (`ø`, `æ`, `œ`,
    `ß`, `ł`, `đ`, `ð`, `þ`, `ı`, `ħ`, `ŋ`, `ŧ`, `ĸ`) pasan por
    `_TRANSLITERACION` para que el `name_norm` calculado en Python coincida con
    el de la columna generada. El resto del diccionario de `unaccent`
    (símbolos, superíndices, alfabetos no latinos) queda fuera de este espejo.
    """
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", unicodedata.normalize("NFKC", texto))
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    limpio = _NO_ALFANUMERICO.sub(
        " ", sin_acentos.lower().translate(_TRANSLITERACION)
    )
    return " ".join(_ESPACIOS.sub(" ", limpio).split())


def validar_nombre(texto: str | None) -> tuple[str, str]:
    """(nombre visible, normalizado) o `EtiquetaInvalida` con texto para la UI.

    Rechaza vacío, >64 caracteres, comas, saltos de línea, controles y nombres
    que la normalización deja vacíos. Conserva espacios internos.
    """
    nombre = (texto or "").strip()
    if len(nombre) > MAX_NOMBRE:
        raise EtiquetaInvalida("La etiqueta no puede tener más de 64 caracteres.")
    if "," in nombre:
        raise EtiquetaInvalida("La etiqueta no puede llevar comas.")
    if any(ord(c) < 32 or ord(c) == 127 for c in nombre):
        raise EtiquetaInvalida("La etiqueta no puede llevar saltos de línea ni controles.")
    normalizado = normalize_tag(nombre)
    if not normalizado:
        raise EtiquetaInvalida("Escribe al menos una letra o un número.")
    if len(normalizado) > MAX_NOMBRE:
        raise EtiquetaInvalida("La etiqueta no puede tener más de 64 caracteres.")
    return nombre, normalizado


def puede_escribir(existente: object, source_nuevo: str) -> bool:
    """Precedencia: una asignación manual no la modifica un escritor automático."""
    source = getattr(existente, "source", None)
    if isinstance(existente, dict):
        source = existente.get("source")
    return not (source == SOURCE_MANUAL and source_nuevo != SOURCE_MANUAL)


async def etiquetas_de_serie(db: AsyncSession, series_id: UUID) -> list[Tag]:
    filas = await db.execute(
        select(Tag)
        .join(series_tags, series_tags.c.tag_id == Tag.id)
        .where(series_tags.c.series_id == series_id, series_tags.c.oculta.is_(False))
        .order_by(Tag.name_norm, Tag.name)
    )
    return list(filas.scalars().all())


async def _tag_por_nombre(db: AsyncSession, normalizado: str) -> Tag | None:
    fila = await db.execute(
        select(Tag).where(Tag.namespace == NAMESPACE, Tag.name_norm == normalizado)
    )
    return fila.scalar_one_or_none()


async def _crear_tag(db: AsyncSession, nombre: str) -> Tag:
    tag = Tag(name=nombre, namespace=NAMESPACE)
    db.add(tag)
    try:
        await db.flush()
    except IntegrityError:
        # Carrera con otra petición: la fila ya existe; se recupera.
        await db.rollback()
        existente = await _tag_por_nombre(db, normalize_tag(nombre))
        if existente is None:
            raise
        return existente
    return tag


async def anadir_etiqueta(db: AsyncSession, series_id: UUID, texto: str) -> ResultadoEtiqueta:
    nombre, normalizado = validar_nombre(texto)
    tag = await _tag_por_nombre(db, normalizado)
    if tag is None:
        tag = await _crear_tag(db, nombre)
    fila = (await db.execute(
        select(series_tags.c.source, series_tags.c.oculta).where(
            series_tags.c.series_id == series_id, series_tags.c.tag_id == tag.id
        )
    )).first()
    if fila is not None:
        source, oculta = fila[0], fila[1]
        if not oculta:
            return ResultadoEtiqueta(tag, "Esa etiqueta ya estaba en la serie.", False)
        if not puede_escribir({"source": source}, SOURCE_MANUAL):
            return ResultadoEtiqueta(tag, "Esa etiqueta no se puede cambiar.", False)
        await db.execute(
            update(series_tags)
            .where(series_tags.c.series_id == series_id, series_tags.c.tag_id == tag.id)
            .values(source=SOURCE_MANUAL, oculta=False, weight=None)
        )
        await db.flush()
        return ResultadoEtiqueta(tag, "Etiqueta añadida.", True)
    await db.execute(insert(series_tags).values(
        series_id=series_id, tag_id=tag.id, source=SOURCE_MANUAL, weight=None, oculta=False,
    ))
    await db.flush()
    return ResultadoEtiqueta(tag, "Etiqueta añadida.", True)


async def quitar_etiqueta(db: AsyncSession, series_id: UUID, texto: str) -> ResultadoEtiqueta:
    _nombre, normalizado = validar_nombre(texto)
    tag = await _tag_por_nombre(db, normalizado)
    if tag is None:
        return ResultadoEtiqueta(None, "Esa etiqueta no existe.", False)
    fila = (await db.execute(
        select(series_tags.c.source).where(
            series_tags.c.series_id == series_id, series_tags.c.tag_id == tag.id
        )
    )).first()
    if fila is None:
        return ResultadoEtiqueta(tag, "Esa etiqueta no estaba en la serie.", False)
    if fila[0] == SOURCE_MANUAL:
        await db.execute(delete(series_tags).where(
            series_tags.c.series_id == series_id, series_tags.c.tag_id == tag.id))
        await db.flush()
        return ResultadoEtiqueta(tag, "Etiqueta quitada.", True)
    # Una fila de una fuente no se borra: se oculta y no se resucita.
    await db.execute(update(series_tags).where(
        series_tags.c.series_id == series_id, series_tags.c.tag_id == tag.id
    ).values(oculta=True))
    await db.flush()
    return ResultadoEtiqueta(tag, "Etiqueta quitada de la ficha.", True)


async def sugerencias_etiqueta(db: AsyncSession, texto: str, *, series_id: UUID | None = None,
                                limite: int = MAX_SUGERENCIAS) -> list[Tag]:
    normalizado = normalize_tag(texto)[:MAX_NOMBRE]
    if len(normalizado) < MIN_SUGERENCIA:
        return []
    consulta = select(Tag).where(Tag.namespace == NAMESPACE)
    if series_id is not None:
        consulta = consulta.where(Tag.id.not_in(
            select(series_tags.c.tag_id).where(
                series_tags.c.series_id == series_id, series_tags.c.oculta.is_(False))
        ))
    consulta = (
        consulta.where(Tag.name_norm.like(f"{normalizado}%"))
        .order_by(
            func.similarity(Tag.name_norm, normalizado).desc(),
            Tag.name_norm,
        )
        .limit(limite)
    )
    return list((await db.execute(consulta)).scalars().all())


# ── Expresión de filtro de Biblioteca (BL-ETQ1b, #431) ───────────────────────

MAX_EXPRESION = 100
MAX_TOKENS = 12


@dataclass(frozen=True)
class ExpresionEtiquetas:
    positivas: tuple[str, ...]
    negativas: tuple[str, ...]
    avisos: tuple[str, ...] = ()

    @property
    def vacia(self) -> bool:
        return not self.positivas and not self.negativas


def parse_expresion(texto: str | None) -> ExpresionEtiquetas:
    """Parsea `noir -escuela`: nombres normalizados, AND y exclusión.

    Sin prefijos de namespace. El primer signo manda; repetir un token cambia
    su signo (el segundo gana). Aplica los topes de 100 caracteres y 12 tokens
    y devuelve avisos para la UI; nunca lanza.
    """
    avisos: list[str] = []
    bruto = (texto or "").strip()
    if len(bruto) > MAX_EXPRESION:
        bruto = bruto[:MAX_EXPRESION]
        avisos.append("La búsqueda de etiquetas era demasiado larga; se ha recortado.")
    tokens = bruto.split()
    if len(tokens) > MAX_TOKENS:
        tokens = tokens[:MAX_TOKENS]
        avisos.append("Hay demasiadas etiquetas a la vez. Quita alguna.")
    por_sentido: dict[str, bool] = {}
    for token in tokens:
        negativo = token.startswith("-")
        nombre = normalize_tag(token[1:] if negativo else token)
        if not nombre:
            continue
        # El segundo signo del mismo token gana, como en la UI.
        por_sentido[nombre] = negativo
    positivas = tuple(n for n, neg in por_sentido.items() if not neg)
    negativas = tuple(n for n, neg in por_sentido.items() if neg)
    return ExpresionEtiquetas(positivas, negativas, tuple(avisos))


async def resolver_etiquetas(db: AsyncSession, normalizados: list[str]) -> dict[str, Tag]:
    if not normalizados:
        return {}
    filas = await db.execute(
        select(Tag).where(Tag.namespace == NAMESPACE,
                          Tag.name_norm.in_(tuple(set(normalizados))))
    )
    return {tag.name_norm: tag for tag in filas.scalars().all()}


async def facetas_etiquetas(db: AsyncSession, positivas: tuple[str, ...],
                            limite: int = MAX_SUGERENCIAS) -> list[tuple[Tag, int]]:
    """Conteo de etiquetas visibles entre las series que cumplen los positivos.

    Una serie excluida sigue contando en la faceta (solo se aplican positivos),
    como exige AC-08. Una sola consulta agregada.
    """
    subconsulta = select(Series.id)
    for normalizado in positivas:
        subconsulta = subconsulta.where(Series.id.in_(
            select(series_tags.c.series_id).join(
                Tag, Tag.id == series_tags.c.tag_id
            ).where(Tag.name_norm == normalizado, series_tags.c.oculta.is_(False))
        ))
    consulta = (
        select(Tag, func.count(series_tags.c.series_id))
        .join(series_tags, series_tags.c.tag_id == Tag.id)
        .where(series_tags.c.oculta.is_(False), series_tags.c.series_id.in_(subconsulta))
        .group_by(Tag.id)
        .order_by(func.count(series_tags.c.series_id).desc(), Tag.name_norm)
        .limit(limite)
    )
    return [(tag, int(total)) for tag, total in (await db.execute(consulta)).all()]


async def sugerencias_filtro(db: AsyncSession, texto: str, *,
                             limite: int = MAX_SUGERENCIAS) -> list[tuple[Tag, int]]:
    """Sugerencias de Biblioteca: prefijo normalizado, con su recuento visible."""
    normalizado = normalize_tag(texto)[:MAX_NOMBRE]
    if len(normalizado) < MIN_SUGERENCIA:
        return []
    consulta = (
        select(Tag, func.count(series_tags.c.series_id))
        .join(series_tags, series_tags.c.tag_id == Tag.id)
        .where(Tag.namespace == NAMESPACE,
               Tag.name_norm.like(f"{normalizado}%"),
               series_tags.c.oculta.is_(False))
        .group_by(Tag.id)
        .order_by(func.similarity(Tag.name_norm, normalizado).desc(),
                  func.count(series_tags.c.series_id).desc(), Tag.name_norm)
        .limit(limite)
    )
    return [(tag, int(total)) for tag, total in (await db.execute(consulta)).all()]
