"""Barrida inicial de la CCM (CCM-6): recorre todas las series con ID.

No es una recolección masiva sin control: procesa una serie por vez, guarda
evidencia, aplica SOLO huecos seguros y deja los conflictos para revisión
manual. El estado vive en memoria del proceso (un solo worker); al reiniciar
la app hay que volver a lanzarla.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import UTC, datetime

import structlog
from sqlalchemy import or_, select

from zascarr.database import async_session_factory
from zascarr.models import Series
from zascarr.services.consolidacion.adaptadores import abrir_adaptadores
from zascarr.services.consolidacion.aplicador import Aplicador, PlanCaducadoError
from zascarr.services.consolidacion.consulta import cargar_contexto
from zascarr.services.consolidacion.recolector import Recolector

logger = structlog.get_logger()

#: Una sola recolección/relleno a la vez en el proceso (incluye la manual).
BLOQUEO_RECOLECCION = asyncio.Lock()


@dataclass(frozen=True)
class EstadoBarrida:
    estado: str = "inactiva"          # inactiva | en_curso | completada | error
    total: int = 0
    procesadas: int = 0
    recolectadas: int = 0
    aplicados: int = 0
    conflictos: int = 0
    fallos: int = 0
    series_conflictos: tuple[dict, ...] = ()
    iniciada_en: datetime | None = None
    terminada_en: datetime | None = None
    error: str | None = None
    lote: int = 0

    @property
    def en_curso(self) -> bool:
        return self.estado == "en_curso"

    @property
    def porcentaje(self) -> int:
        return int(self.procesadas * 100 / self.total) if self.total else 0


_ESTADO = EstadoBarrida()


def estado_barrida() -> EstadoBarrida:
    return _ESTADO


def barrida_en_curso() -> bool:
    return _ESTADO.estado == "en_curso"


def _actualizar(**cambios) -> None:
    global _ESTADO
    _ESTADO = replace(_ESTADO, **cambios)


def marcar_sin_fuentes() -> None:
    global _ESTADO
    _ESTADO = EstadoBarrida(estado="error",
                            error="No hay fuentes de metadatos activas.",
                            terminada_en=datetime.now(UTC))


def iniciar_barrida() -> bool:
    """Marca la barrida como en curso; el llamante lanza `ejecutar_barrida`.

    Devuelve False si ya hay una en curso o una recolección manual bloqueada.
    """
    global _ESTADO
    if _ESTADO.estado == "en_curso" or BLOQUEO_RECOLECCION.locked():
        return False
    _ESTADO = EstadoBarrida(estado="en_curso", iniciada_en=datetime.now(UTC))
    return True


def _series_con_id():
    return select(Series.id).where(or_(
        Series.comic_vine_id.is_not(None),
        Series.tebeosfera_slug.is_not(None),
        Series.gcd_id.is_not(None),
        Series.anilist_id.is_not(None),
        Series.metron_id.is_not(None),
        Series.open_library_id.is_not(None),
        Series.fandom_dc_slug.is_not(None),
        Series.fandom_marvel_slug.is_not(None),
    )).order_by(Series.id)


async def ejecutar_barrida() -> None:
    """Trabajo de fondo: recorre, recolecta y aplica huecos seguros."""
    if BLOQUEO_RECOLECCION.locked():
        _actualizar(estado="error", error="Ya hay una recolección en curso.")
        return
    async with BLOQUEO_RECOLECCION:
        abierto = None
        try:
            abierto = await abrir_adaptadores()
            if not abierto["adaptadores"]:
                _actualizar(estado="error", error="No hay fuentes de metadatos activas.")
                return
            async with async_session_factory() as db:
                ids = list((await db.execute(_series_con_id())).scalars().all())
                _actualizar(total=len(ids))
                for pos, serie_id in enumerate(ids, start=1):
                    correcta = await _procesar_serie(db, abierto["adaptadores"], serie_id)
                    _actualizar(
                        procesadas=pos, lote=((pos - 1) // 20) + 1,
                        fallos=_ESTADO.fallos + (0 if correcta else 1))
                _actualizar(estado="completada", terminada_en=datetime.now(UTC))
        except Exception as exc:  # noqa: BLE001 — el fondo no tumba la app
            logger.exception("ccm.barrida_fallida")
            _actualizar(estado="error", terminada_en=datetime.now(UTC),
                        error=f"La barrida se ha detenido: {type(exc).__name__}.")
        finally:
            if abierto is not None:
                await abierto["pila"].aclose()


async def _procesar_serie(db, adaptadores, serie_id) -> bool:
    """Recolecta una serie, aplica huecos seguros y cuenta conflictos."""
    try:
        serie = await db.get(Series, serie_id)
        if serie is None:
            return False
        informe = await Recolector(db, adaptadores).recolectar_serie(serie)
        await db.commit()
        _actualizar(recolectadas=_ESTADO.recolectadas + informe.guardados)

        contexto = await cargar_contexto(db, serie_id)
        plan = contexto.plan()
        conflictos = plan.conflictos()
        try:
            resultado = await Aplicador(db).aplicar(plan)
            await db.commit()
        except PlanCaducadoError:
            await db.rollback()
            contexto = await cargar_contexto(db, serie_id)
            plan = contexto.plan()
            conflictos = plan.conflictos()
            resultado = await Aplicador(db).aplicar(plan)
            await db.commit()
        _actualizar(aplicados=_ESTADO.aplicados + resultado.aplicados)
        if conflictos:
            _actualizar(
                conflictos=_ESTADO.conflictos + len(conflictos),
                series_conflictos=_ESTADO.series_conflictos + ({
                    "id": str(serie_id), "titulo": contexto.serie.title,
                    "campos": len(conflictos),
                },),
            )
        return True
    except Exception:  # noqa: BLE001 — una serie no corta la barrida
        await db.rollback()
        logger.exception("ccm.barrida_serie_fallida", serie_id=str(serie_id))
        return False
