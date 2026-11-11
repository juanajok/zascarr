"""#340/BL-WK2: estado de colección por serie y decisión «no la voy a completar».

El estado es **derivado**: no hay columna nueva. La decisión explícita vive en
`Series.metadata_["coleccion"]` (JSONB), es reversible y no toca `Series.status`
ni `wishlist_policy`. Los huecos se siguen calculando con `huecos_de_serie`
(C2/B22), sin cambiar su contrato.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Series, WishlistPolicy
from zascarr.services.series import (
    UNIDAD_DE_GRAPA,
    compute_missing_issues,
    huecos_de_serie,
    numeros_poseidos_por_serie,
    razon_de_no_calculable,
)

CLAVE_METADATA = "coleccion"
VERSION = 1

COMPLETA = "completa"
FALTAN = "faltan"
NO_CALCULABLE = "no_calculable"
NO_COMPLETAR = "no_completar"
TIPOS = (COMPLETA, FALTAN, NO_CALCULABLE, NO_COMPLETAR)

ETIQUETAS = {
    COMPLETA: "Completa",
    FALTAN: "Te faltan números",
    NO_CALCULABLE: "No se puede calcular",
    NO_COMPLETAR: "No la vas a completar",
}


class ConflictoVersionError(RuntimeError):
    """Otra pestaña guardó una decisión distinta desde que se abrió la ficha."""


def version_de_decision(series: Series) -> int:
    datos = (series.metadata_ or {}).get(CLAVE_METADATA) or {}
    try:
        return max(0, int(datos.get("version") or 0))
    except (TypeError, ValueError):
        return 0


@dataclass(frozen=True)
class EstadoColeccion:
    tipo: str
    faltantes: tuple[int, ...] = ()
    motivo: str | None = None

    @property
    def etiqueta(self) -> str:
        if self.tipo == FALTAN:
            return f"Te faltan {len(self.faltantes)}"
        return ETIQUETAS[self.tipo]

    @property
    def no_completar(self) -> bool:
        return self.tipo == NO_COMPLETAR


def decision_no_completar(series: Series) -> bool:
    """¿La persona decidió no completar esta serie? (JSONB, tolerante)."""
    datos = (series.metadata_ or {}).get(CLAVE_METADATA) or {}
    return isinstance(datos, dict) and bool(datos.get("no_completar"))


def marcar_no_completar(series: Series) -> None:
    """Guarda la decisión con versión y fecha; conserva el resto de metadata."""
    actual = dict(series.metadata_ or {})
    anterior = dict(actual.get(CLAVE_METADATA) or {})
    actual[CLAVE_METADATA] = {
        **anterior,
        "no_completar": True,
        "actualizado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": VERSION,
    }
    series.metadata_ = actual


def revertir_no_completar(series: Series) -> None:
    """Reversible: deja constancia de la vuelta, no borra la clave ni la política."""
    actual = dict(series.metadata_ or {})
    anterior = dict(actual.get(CLAVE_METADATA) or {})
    actual[CLAVE_METADATA] = {
        **anterior,
        "no_completar": False,
        "actualizado_en": datetime.now(UTC).isoformat(timespec="seconds"),
        "version": VERSION,
    }
    series.metadata_ = actual


async def cambiar_decision(
    db: AsyncSession, series_id: UUID, *, no_completar: bool,
    version_esperada: int,
) -> int:
    """UPDATE optimista del JSONB: solo escribe si la versión sigue siendo la vista.

    No hace falta cargar ni bloquear la fila: el `WHERE` incluye la versión y
    devuelve 0 filas si otra pestaña se adelantó; el router lo convierte en 409.
    """
    version_esperada = max(0, int(version_esperada))
    nueva_version = version_esperada + 1
    actualizado = datetime.now(UTC).isoformat(timespec="seconds")
    # Se construye del lado de Postgres para que el JSONB sea un objeto (un
    # dict de Python pasado a JSONB se serializa como string y `||` daría un array).
    coleccion = func.jsonb_build_object(
        "no_completar", bool(no_completar),
        "actualizado_en", actualizado,
        "version", nueva_version)
    condicion_version = func.coalesce(
        Series.metadata_["coleccion"]["version"].astext, "0"
    ) == str(version_esperada)
    sentencia = (
        update(Series)
        .where(Series.id == series_id, condicion_version)
        .values(metadata_=(
            func.coalesce(Series.metadata_, func.jsonb_build_object())
            .op("||")(func.jsonb_build_object("coleccion", coleccion))))
        .returning(Series.id)
    )
    resultado = await db.execute(sentencia)
    if resultado.scalar_one_or_none() is None:
        raise ConflictoVersionError("La decisión cambió en otra pestaña")
    await db.flush()
    return nueva_version


def estado_puro(series: Series, poseidos: set[int]) -> EstadoColeccion:
    """Estado sin BD, para tests y para reutilizar la misma regla en la ficha."""
    if decision_no_completar(series):
        return EstadoColeccion(NO_COMPLETAR)
    no_calculable = razon_de_no_calculable(series)
    if no_calculable is not None:
        return EstadoColeccion(NO_CALCULABLE, motivo=no_calculable.motivo)
    faltantes = compute_missing_issues(series.total_issues, poseidos)
    if not faltantes:
        return EstadoColeccion(COMPLETA)
    return EstadoColeccion(FALTAN, tuple(faltantes))


async def estado_de_coleccion(db: AsyncSession, series: Series,
                              poseidos: set[int] | None = None) -> EstadoColeccion:
    if decision_no_completar(series):
        return EstadoColeccion(NO_COMPLETAR)
    if poseidos is None:
        huecos = await huecos_de_serie(db, series)
    else:
        huecos = await huecos_de_serie(db, series, poseidos)
    if not huecos.computable:
        return EstadoColeccion(NO_CALCULABLE, motivo=huecos.motivo)
    if not huecos.faltantes:
        return EstadoColeccion(COMPLETA)
    return EstadoColeccion(FALTAN, tuple(huecos.faltantes))


def conflicto_con_politica(series: Series) -> bool:
    """D8: no completar mientras la política busca lo que falta (no se corrige sola)."""
    return (not decision_no_completar(series)
            and (series.wishlist_policy or WishlistPolicy.NONE)
            in (WishlistPolicy.MISSING, WishlistPolicy.ALL))


async def ids_por_estado(db: AsyncSession, tipo: str) -> set[UUID]:
    """IDs que cumplen el estado pedido, con UNA consulta de series + la de posesión.

    Es un filtro de presentación; no modifica el cálculo de huecos ni escribe.
    """
    if tipo not in TIPOS:
        return set()
    filas = (await db.execute(
        select(Series.id, Series.total_issues, Series.metadata_source, Series.metadata_)
    )).all()
    if tipo == NO_COMPLETAR:
        return {sid for sid, _total, _fuente, metadata in filas
                if isinstance(metadata, dict)
                and bool((metadata.get(CLAVE_METADATA) or {}).get("no_completar"))}
    poseidos = await numeros_poseidos_por_serie(db)
    salida: set[UUID] = set()
    for sid, total, fuente, metadata in filas:
        decidida = (isinstance(metadata, dict)
                    and bool((metadata.get(CLAVE_METADATA) or {}).get("no_completar")))
        if decidida:
            continue
        # Réplica exacta de `razon_de_no_calculable` sin cargar la Serie entera.
        no_calculable = not total or fuente not in UNIDAD_DE_GRAPA
        if tipo == NO_CALCULABLE:
            if no_calculable:
                salida.add(sid)
            continue
        if no_calculable:
            continue
        faltan = bool(compute_missing_issues(total, poseidos.get(sid, set())))
        if (tipo == FALTAN and faltan) or (tipo == COMPLETA and not faltan):
            salida.add(sid)
    return salida
