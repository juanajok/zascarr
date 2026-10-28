"""Medición SINTÉTICA y LOCAL (no la Pi) de la lectura de disponibilidad (#231): 1.500 archivos registrados, 300 no
disponibles (con fechas repetidas) y 2.500 ciclos del importador (tamaño de la Pi de referencia a 2026-10-20).
Mide consultas por petición, tiempo (mediana y p95 de 30 repeticiones) y RSS. Requiere una base de PRUEBAS (su nombre lleva
«test»); crea y borra una efímera. No toca el disco: la lectura no lo necesita.
Uso: TEST_DATABASE_URL=postgresql://... PYTHONPATH=src python scripts/medicion/medir_disponibilidad.py"""
# ruff: noqa: E501, E402, E702
from __future__ import annotations

import asyncio
import os
import resource
import statistics
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # raíz del repo: para importar tests._pg
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg  # noqa: E402
from zascarr.models import File, ImportRun  # noqa: E402
from zascarr.services import disponibilidad  # noqa: E402

N_ARCHIVOS, N_AUSENTES, N_CICLOS, REPS = 1500, 300, 2500, 30
T0 = datetime(2026, 10, 1, 3, 0, tzinfo=UTC)


async def main(url: str) -> None:
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    async with fabrica() as s:
        s.add_all([File(id=uuid4(), file_path=f"/media/lib/{i % 40:02d}/Obra {i:05d}.cbz", file_name=f"Obra {i:05d}.cbz",
                        file_format="cbz", is_missing=i < N_AUSENTES,
                        missing_since=None if (i < N_AUSENTES and i % 10 == 0) else (T0 + timedelta(hours=i % 12) if i < N_AUSENTES else None))
                   for i in range(N_ARCHIVOS)])
        s.add_all([ImportRun(id=uuid4(), started_at=T0 + timedelta(minutes=10 * i), finished_at=T0 + timedelta(minutes=10 * i),
                             details={"imported": [], "comprobacion_biblioteca": {
                                 "ambito": "biblioteca", "resultado": "comprobada" if i % 50 else "raiz_vacia",
                                 "archivos_registrados": N_ARCHIVOS, "ausentes": N_AUSENTES, "bajas_omitidas": False,
                                 "fecha": (T0 + timedelta(minutes=10 * i)).isoformat()}}) for i in range(N_CICLOS)])
        await s.commit()

    consultas = 0

    @event.listens_for(motor.sync_engine, "before_cursor_execute")
    def _cuenta(*_a, **_k):
        nonlocal consultas
        consultas += 1

    async def medir(nombre: str, coro_fn) -> None:
        nonlocal consultas
        tiempos = []
        for _ in range(REPS):
            consultas = 0
            t = time.perf_counter()
            async with fabrica() as s:
                await coro_fn(s)
            tiempos.append((time.perf_counter() - t) * 1000)
        tiempos.sort()
        print(f"{nombre:<34} consultas={consultas}  mediana={statistics.median(tiempos):6.1f} ms  p95={tiempos[int(REPS * .95) - 1]:6.1f} ms")

    async with fabrica() as s:
        primera = await disponibilidad.listar_no_disponibles(s)
        segunda = await disponibilidad.listar_no_disponibles(s, primera.siguiente)
    r0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(f"{N_ARCHIVOS} archivos, {N_AUSENTES} no disponibles, {N_CICLOS} ciclos; páginas de {disponibilidad.LIMITE_PAGINA}")
    await medir("ultima_comprobacion", disponibilidad.ultima_comprobacion)
    await medir("lista · primera página", disponibilidad.listar_no_disponibles)
    await medir("lista · página 2 (cursor)", lambda s: disponibilidad.listar_no_disponibles(s, primera.siguiente))
    await medir("lista · página 3 (la última)", lambda s: disponibilidad.listar_no_disponibles(s, segunda.siguiente))
    print(f"RSS pico del proceso: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} MiB (antes de medir: {r0 / 1024:.0f} MiB)")
    await motor.dispose()


with bd_efimera_sync(os.environ["TEST_DATABASE_URL"]) as _url:
    migrar_a_head(_url)
    asyncio.run(main(_url))
