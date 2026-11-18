"""#1101: contexto del modo Escaparate (solo lectura, sin N+1 por bloque)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.services import actividad

LIMITE = 6


async def contexto(db: AsyncSession, *, offset: int = 0) -> dict:
    return {
        "continuar": await actividad.continuar_leyendo(db, LIMITE),
        "vistos": await actividad.vistos_recientemente(db, LIMITE),
        "recien": await actividad.recien_incorporados(db, LIMITE),
        "redescubre": await actividad.redescubre_completo(db, 4, offset),
        "autores": await actividad.autores_destacados(db, LIMITE),
        "tradiciones": await actividad.tradiciones_con_conteo(db),
        "huecos": [],
        "offset_sugerencias": offset,
    }


async def sugerencias(db: AsyncSession, *, offset: int = 0) -> list[actividad.Sugerencia]:
    return await actividad.redescubre_completo(db, 4, offset)
