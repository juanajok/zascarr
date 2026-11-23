"""Restablece únicamente fixtures UXLab antes de CADA sesión sintética."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update

from zascarr.database import async_session_factory
from zascarr.models import Issue, ReadingProgress, ReadingStatus, Series, SeriesRecentView


async def main() -> None:
    async with async_session_factory() as db:
        all_count = (await db.execute(select(func.count(Series.id)))).scalar_one()
        ids = (await db.execute(
            select(Series.id).where(Series.title.like("UXLAB-%"))
        )).scalars().all()
        # Valla contra reutilización por error de una base de datos de producción.
        if all_count != 4 or len(ids) != 4:
            raise RuntimeError(
                "RESTABLECIMIENTO RECHAZADO: la BD debe contener "
                "exactamente las 4 series sintéticas UXLab"
            )
        await db.execute(update(Series).where(Series.id.in_(ids)).values(favorite=False))
        await db.execute(delete(SeriesRecentView).where(SeriesRecentView.series_id.in_(ids)))
        result = await db.execute(
            select(ReadingProgress, Series.title)
            .join(Issue, ReadingProgress.issue_id == Issue.id)
            .join(Series, Issue.series_id == Series.id)
        )
        n = 0
        for progress, title in result:
            if title != "UXLAB-Nebulosa de Papel":
                raise RuntimeError("RESTABLECIMIENTO RECHAZADO: progreso inesperado")
            progress.status = ReadingStatus.READING
            progress.current_page = 3
            progress.last_read_at = datetime(2026, 11, 23, tzinfo=timezone.utc)
            n += 1
        if n != 1:
            raise RuntimeError("RESTABLECIMIENTO RECHAZADO: progreso de prueba ausente")
        await db.commit()
    print("UXLab: favoritas y progreso sintéticos restaurados; resto de BD intacto")


if __name__ == "__main__":
    asyncio.run(main())
