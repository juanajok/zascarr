"""Medición SINTÉTICA y LOCAL (no la Pi) del registro incremental de #326: 1.200 .cbz pequeños + 100 ya registrados.
Requiere una base de PRUEBAS (su nombre lleva «test»); crea y borra una efímera.
Uso: TEST_DATABASE_URL=postgresql://... PYTHONPATH=src python scripts/medicion/medir_registro_incremental.py"""
# ruff: noqa: E501, E402, E702
from __future__ import annotations

import asyncio
import io
import os
import resource
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # raíz del repo: para importar tests._pg
from PIL import Image  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg  # noqa: E402
from zascarr.services import library_adopter as la  # noqa: E402

N_NUEVOS, N_VIEJOS = 1200, 100


def jpg(i: int) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (60, 90), (i % 256, (i * 7) % 256, (i * 13) % 256)).save(b, "JPEG")
    return b.getvalue()


def crear(raiz: Path, n: int, desde: int) -> None:
    for i in range(desde, desde + n):
        d = raiz / f"Serie {i % 40:02d}"
        d.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(d / f"Titulo {i:05d}.cbz", "w") as z:
            for p in range(12):
                z.writestr(f"{p:03d}.jpg", jpg(i * 100 + p) + str(i).encode())


async def main(url: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp) / "lib"
        ajustes = type("A", (), {"library_path": lib})()
        la.get_settings = lambda: ajustes
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        t = time.perf_counter(); crear(lib, N_VIEJOS, 0); print(f"crear {N_VIEJOS} viejos: {time.perf_counter()-t:.1f}s")
        async with fab() as s:
            await la.LibraryAdopter(s).adopt()
        crear(lib, N_NUEVOS, N_VIEJOS)
        async with fab() as s:
            t = time.perf_counter(); inv = await la.LibraryAdopter(s).inventario(); dt = time.perf_counter() - t
            print(f"inventario (solo rutas): {dt:.2f}s  en_disco={inv.en_disco} nuevos={inv.nuevos}")
        r0 = resource.getrusage(resource.RUSAGE_SELF)
        async with fab() as s:
            t = time.perf_counter(); inf = await la.LibraryAdopter(s).adopt(alcance=inv.rutas_nuevas); dt = time.perf_counter() - t
        r1 = resource.getrusage(resource.RUSAGE_SELF)
        print(f"registro incremental: {dt:.1f}s  ({dt/N_NUEVOS*1000:.0f} ms/archivo)  añadidos={inf.added_count} errores={inf.error_count} repetidos={inf.duplicate_count}")
        print(f"CPU usuario+sistema: {(r1.ru_utime+r1.ru_stime)-(r0.ru_utime+r0.ru_stime):.1f}s  pico RSS proceso: {r1.ru_maxrss/1024:.0f} MiB")
        async with fab() as s:
            t = time.perf_counter(); inv2 = await la.LibraryAdopter(s).inventario(); print(f"segundo inventario: {time.perf_counter()-t:.2f}s nuevos={inv2.nuevos}")
        await motor.dispose()


with bd_efimera_sync(os.environ["TEST_DATABASE_URL"]) as _url:
    migrar_a_head(_url)
    asyncio.run(main(_url))
