# ruff: noqa: E501
"""
Etiquetas por serie (BL-ETQ1a, #403) — normalización, validación y alta/borrado.

Fuente única de verdad para la ficha de serie (`web/series.py`): añadir, quitar y crear
etiquetas, más las sugerencias del campo «Añadir una etiqueta…». El filtro de Biblioteca
(BL-ETQ1b, #431) vive en otro módulo y no entra aquí.

Contratos (docs/design/especificacion-etiquetas.md §7):

- **Un solo espacio visible, `etiqueta`** (D-1). La columna `tags.namespace` solo admite ese
  valor en 0022; la persona nunca escribe prefijos.
- **Normalización** `normalize_tag` es espejo de `f_tag_norm` (0022): minúsculas, sin acentos,
  puntuación→espacio y colapso de espacios. **Conserva el artículo** («The Walking Dead» ≠
  «walking dead») y **no** colapsa puntos entre letras (a diferencia de `f_title_norm`):
  `S.H.I.E.L.D.` → «s h i e l d». La paridad Python/SQL se comprueba en `test_tag_norm_pg.py`.
- **El token canónico** es `name_norm` con los espacios como guiones (`clave_de`): `space-opera`.
- **La BD solo recibe texto normalizado**: `Tag.name` se escribe ya con `normalize_tag`, y
  `name_norm` es la columna generada (`f_tag_norm(name)`), que es idempotente sobre texto ya
  normalizado.
- **Autoría** (§7.5): `source='manual'` para lo que toca El Coleccionista. Borrar desde la ficha
  una fila NO manual la marca `oculta=true` (no se borra: la volvería a sembrar la fuente);
  volver a añadirla a mano la deja `manual`, `oculta=false`, `weight=NULL`. `puede_escribir`
  codifica la precedencia que consumirán BL-ETQ2/4.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Tag, series_tags

#: Máximo de caracteres de un nombre (tras `strip`), como el CHECK de 0022.
TOPE_NOMBRE = 64
#: Sugerencias por respuesta.
TOPE_SUGERENCIAS = 8
#: Espacio de nombres del MVP (D-1). Único valor admitido por el CHECK de 0022.
ESPACIO = "etiqueta"

# Puntuación → espacio. Espejo del `[^[:alnum:] ]` de `f_tag_norm`: se conservan letras, dígitos
# y el espacio literal; el guion, el apóstrofo, los signos y los saltos de línea se vuelven espacio.
# `|_` cubre el guion bajo, que `\w` sí acepta pero `[:alnum:]` no (paridad exacta con SQL).
_PUNTUACION = re.compile(r"[^\w ]|_", re.UNICODE)
_ESPACIOS = re.compile(r"\s+")
# Comas, saltos de línea y controles C0 + DEL: rechazados en un nombre (FR-…, §7.4).
_CONTROL = re.compile(r"[,\r\n\x00-\x1f\x7f]")
#: Letras que `unaccent` translitera y NFKD **no** descompone. Sin esta tabla, `normalize_tag`
#: y `f_tag_norm` divergen en nombres como «Smørrebrød», «Æon Flux» o «Straße». No pretende
#: cubrir todo el diccionario de `unaccent` (símbolos, superíndices…): solo letras de nombres.
_TRANSLITERACION = str.maketrans({
    "ø": "o", "æ": "ae", "œ": "oe", "ß": "ss", "ł": "l", "đ": "d", "ð": "d",
    "þ": "th", "ı": "i", "ħ": "h", "ŋ": "n", "ŧ": "t", "ĸ": "q",
})


def normalize_tag(nombre: str) -> str:
    """Espejo Python de `f_tag_norm` (migración 0022).

    NFKD + quitar marcas de combinación = `unaccent` para las letras acentuadas (la misma técnica
    que `core.matcher.normalize_title`, ya contrastada contra `f_unaccent`); después puntuación→
    espacio y colapso. Para las letras que `unaccent` translitera y NFKD no descompone (ø, æ, œ,
    ß…) se aplica `_TRANSLITERACION`, de modo que ambos lados den el mismo `name_norm`.
    **No** quita artículos ni colapsa puntos entre letras.
    """
    nfkd = unicodedata.normalize("NFKD", nombre)
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    sin_puntuacion = _PUNTUACION.sub(" ", sin_acentos)
    return _ESPACIOS.sub(" ", sin_puntuacion).strip().lower().translate(_TRANSLITERACION)


def clave_de(nombre_norm: str) -> str:
    """Token canónico que ve la persona: `name_norm` con cada espacio como `-` (`space-opera`)."""
    return nombre_norm.replace(" ", "-")


class NombreDeEtiquetaInvalidoError(ValueError):
    """El nombre no se puede escribir tal cual; `str(exc)` es el aviso para la persona."""


def validar_nombre(nombre: str) -> str:
    """Valida y normaliza un nombre. Devuelve el texto normalizado o lanza `NombreDeEtiquetaInvalidoError`.

    Reglas (§7.4): 1–64 caracteres tras `strip`; sin comas, saltos de línea ni controles; y el
    valor normalizado no puede quedar vacío. Los espacios internos se conservan.
    """
    texto = nombre.strip()
    if not texto:
        raise NombreDeEtiquetaInvalidoError("Esa etiqueta no existe. Elige una de las sugerencias.")
    if len(texto) > TOPE_NOMBRE:
        raise NombreDeEtiquetaInvalidoError(
            f"El nombre es demasiado largo (máximo {TOPE_NOMBRE} caracteres)."
        )
    if _CONTROL.search(texto):
        raise NombreDeEtiquetaInvalidoError("El nombre no puede llevar comas ni saltos de línea.")
    normalizado = normalize_tag(texto)
    if not normalizado:
        raise NombreDeEtiquetaInvalidoError("Esa etiqueta no existe. Elige una de las sugerencias.")
    return normalizado


def puede_escribir(existente, source_nuevo: str) -> bool:
    """Precedencia de autoría (§7.5): True si un escritor de `source_nuevo` puede
    modificar/borrar la fila `existente` (o crearla, si es `None`).

    Una fila `source='manual'` es intocable para cualquier escritor automático
    (`comic_vine`, `anilist`, `comicinfo_xml`…); la escritura manual siempre puede. Es el
    contrato puro que consumen BL-ETQ2/4, sin BD (AC-16).
    """
    if source_nuevo == "manual":
        return True
    if existente is None:
        return True
    return existente.source != "manual"


@dataclass
class EtiquetaDeSerie:
    """Una etiqueta visible de la ficha. Solo hace falta el token para el chip (el nombre va
    escrito, sin color)."""

    clave: str


@dataclass
class Sugerencia:
    """Fila del desplegable de sugerencias de la ficha."""

    clave: str
    series: int  # cuántas series la usan (visible)


@dataclass
class Resultado:
    """Qué pasó al añadir/quitar/crear, para que el router pinte el aviso exacto."""

    ok: bool
    aviso_tipo: str  # "ok" | "warn"
    aviso: str


class EtiquetasService:
    """Lectura y escritura de etiquetas por serie. Los routers web son finos; aquí va la lógica.

    Los nombres y las claves entran sin normalizar y el servicio normaliza antes de tocar la BD;
    un `etiqueta` que no se resuelve no lanza 500 sino que devuelve un `Resultado` con su aviso.
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def de_serie(self, series_id: UUID) -> list[EtiquetaDeSerie]:
        """Etiquetas visibles de la serie, ordenadas por `name_norm` (una sola consulta)."""
        filas = (
            await self._db.execute(
                select(Tag)
                .join(series_tags, Tag.id == series_tags.c.tag_id)
                .where(
                    series_tags.c.series_id == series_id,
                    series_tags.c.oculta.is_(False),
                )
                .order_by(Tag.name_norm.asc())
            )
        ).scalars().all()
        return [EtiquetaDeSerie(clave=tag.clave) for tag in filas]

    async def sugerir(self, series_id: UUID, texto: str) -> list[Sugerencia]:
        """Sugerencias para el campo de la ficha: prefijo normalizado, sin las ya aplicadas,
        ordenadas por uso y nombre, limitadas a `TOPE_SUGERENCIAS` (una sola consulta).

        `texto` ya viene con ≥2 caracteres (el router corta antes); aquí se normaliza y, si
        queda vacío, no se consulta.
        """
        prefijo_norm = normalize_tag(texto)
        if not prefijo_norm:
            return []
        ya_aplicadas = select(series_tags.c.tag_id).where(
            series_tags.c.series_id == series_id,
            series_tags.c.oculta.is_(False),
        )
        filas = (
            await self._db.execute(
                select(Tag.name_norm, func.count(series_tags.c.series_id))
                .select_from(Tag)
                .outerjoin(
                    series_tags,
                    and_(
                        series_tags.c.tag_id == Tag.id,
                        series_tags.c.oculta.is_(False),
                    ),
                )
                .where(Tag.namespace == ESPACIO)
                .where(Tag.name_norm.like(f"{prefijo_norm}%"))
                .where(Tag.id.not_in(ya_aplicadas))
                .group_by(Tag.id)
                .order_by(func.count(series_tags.c.series_id).desc(), Tag.name_norm.asc())
                .limit(TOPE_SUGERENCIAS)
            )
        ).all()
        return [Sugerencia(clave=clave_de(fila[0]), series=fila[1]) for fila in filas]

    async def anadir(self, series_id: UUID, nombre: str, crear: bool = False) -> Resultado:
        """Añade `nombre` a la serie. Con `crear=True` (D-6) crea la etiqueta si no existe.

        - nombre nuevo + `crear=False` → «Esa etiqueta no existe…».
        - nombre nuevo + `crear=True` → la crea (`manual`) y la añade.
        - nombre existente + `crear=True` → «Esa etiqueta ya existe: …» (no asigna).
        - ya en la serie (visible) → «Esa etiqueta ya estaba en la serie.».
        """
        try:
            nombre_norm = validar_nombre(nombre)
        except NombreDeEtiquetaInvalidoError as exc:
            return Resultado(False, "warn", str(exc))

        tag = await self._por_norm(nombre_norm)
        if tag is None:
            if not crear:
                return Resultado(False, "warn", "Esa etiqueta no existe. Elige una de las sugerencias.")
            try:
                tag = Tag(namespace=ESPACIO, name=nombre_norm)
                self._db.add(tag)
                await self._db.flush()
            except IntegrityError:
                # Carrera: otra petición creó el mismo `(namespace, name_norm)`. No duplicar.
                # Solo se atrapa la violación de unicidad: una BD caída sube al router, que
                # responde con el aviso genérico en vez de culpar a un duplicado inexistente.
                await self._db.rollback()
                return Resultado(False, "warn", f"Esa etiqueta ya existe: {clave_de(nombre_norm)}")
        elif crear:
            return Resultado(False, "warn", f"Esa etiqueta ya existe: {clave_de(nombre_norm)}")

        asignacion = await self._asignacion(series_id, tag.id)
        if asignacion is not None and not asignacion.oculta:
            return Resultado(False, "warn", "Esa etiqueta ya estaba en la serie.")

        if asignacion is not None:
            # Reactivar una fila oculta (fuente): pasa a manual, visible y sin peso (§7.5).
            await self._db.execute(
                series_tags.update()
                .where(
                    series_tags.c.series_id == series_id,
                    series_tags.c.tag_id == tag.id,
                )
                .values(source="manual", oculta=False, weight=None)
            )
        else:
            await self._db.execute(
                series_tags.insert().values(
                    series_id=series_id,
                    tag_id=tag.id,
                    source="manual",
                    oculta=False,
                    weight=None,
                )
            )
        await self._db.flush()
        return Resultado(True, "ok", "Etiqueta añadida.")

    async def quitar(self, series_id: UUID, clave: str) -> Resultado:
        """Quita `clave` de la serie. Una fila manual se borra; una de fuente se marca `oculta=true`."""
        nombre_norm = normalize_tag(clave)
        if not nombre_norm:
            return Resultado(False, "warn", "Esa etiqueta no existe. Elige una de las sugerencias.")
        tag = await self._por_norm(nombre_norm)
        if tag is None:
            return Resultado(False, "warn", "Esa etiqueta no existe. Elige una de las sugerencias.")
        asignacion = await self._asignacion(series_id, tag.id)
        if asignacion is None or asignacion.oculta:
            return Resultado(False, "warn", "Esa etiqueta no estaba en la serie.")
        if asignacion.source == "manual":
            await self._db.execute(
                series_tags.delete().where(
                    series_tags.c.series_id == series_id,
                    series_tags.c.tag_id == tag.id,
                )
            )
        else:
            await self._db.execute(
                series_tags.update()
                .where(
                    series_tags.c.series_id == series_id,
                    series_tags.c.tag_id == tag.id,
                )
                .values(oculta=True)
            )
        await self._db.flush()
        return Resultado(True, "ok", "Etiqueta quitada.")

    async def _por_norm(self, nombre_norm: str) -> Tag | None:
        return (
            await self._db.execute(
                select(Tag).where(Tag.namespace == ESPACIO, Tag.name_norm == nombre_norm)
            )
        ).scalar_one_or_none()

    async def _asignacion(self, series_id: UUID, tag_id: str):
        return (
            await self._db.execute(
                select(series_tags).where(
                    series_tags.c.series_id == series_id,
                    series_tags.c.tag_id == tag_id,
                )
            )
        ).first()
