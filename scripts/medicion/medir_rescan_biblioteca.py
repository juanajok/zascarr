"""Medición SINTÉTICA y LOCAL (no la Pi) del rescan de la biblioteca de BL-R9.

Mide los dos costes que importan: la primera pasada (1.200 nuevos: hay que leerlos y registrarlos) y la
pasada «sin cambios» (1.300 rutas registradas: solo `stat`, sin abrir un CBZ), más una pasada con 10
sustituidos (re-triaje). Requiere una base de PRUEBAS (su nombre lleva «test»); crea y borra una efímera.
Uso: TEST_DATABASE_URL=postgresql://... PYTHONPATH=src python scripts/medicion/medir_rescan_biblioteca.py
"""
# ruff: noqa: E501, E402, E702
from __future__ import annotations

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

N_VIEJOS, N_NUEVOS = 100, 1200


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


async def rescan(fab, **kw):
    async with fab() as s:
        return await la.LibraryAdopter(s).rescanear(**kw)


async def main(url: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        lib = Path(tmp) / "lib"
        ajustes = type("A", (), {"library_path": lib})()
        la.get_settings = lambda: ajustes
        from types import SimpleNamespace

        import zascarr.services.importer as imp
        imp.get_settings = lambda: SimpleNamespace(
            library_path=lib, transmission_download_dir="/tmp/t",
            amule_incoming_dir="/tmp/a", downloads_path=Path("/tmp/d"))
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        t = time.perf_counter(); crear(lib, N_VIEJOS, 0); print(f"crear {N_VIEJOS} viejos: {time.perf_counter()-t:.1f}s")
        async with fab() as s:
            await la.LibraryAdopter(s).adopt()
        crear(lib, N_NUEVOS, N_VIEJOS)

        r0 = resource.getrusage(resource.RUSAGE_SELF)
        t = time.perf_counter(); inf1 = await rescan(fab); dt = time.perf_counter() - t
        r1 = resource.getrusage(resource.RUSAGE_SELF)
        print(f"rescan 1 ({inf1.files_scanned} archivos, {inf1.nuevos_registrados + inf1.nuevos_a_revisar} registrados, "
              f"{inf1.re_triados} re-triados): {dt:.1f}s  CPU {r1.ru_utime - r0.ru_utime:.1f}s  "
              f"RSS {r1.ru_maxrss // 1024} MiB")

        t = time.perf_counter(); inf2 = await rescan(fab); dt = time.perf_counter() - t
        r2 = resource.getrusage(resource.RUSAGE_SELF)
        print(f"rescan 2 (sin cambios, {inf2.sin_cambios} solo stat): {dt:.2f}s  CPU {r2.ru_utime - r1.ru_utime:.1f}s")

        for i in range(10):
            p = lib / f"Serie {i:02d}" / f"Titulo {i:05d}.cbz"
            with zipfile.ZipFile(p, "w") as z:
                z.writestr("000.jpg", jpg(999) + f"cambio-{i}".encode())
        t = time.perf_counter(); inf3 = await rescan(fab); dt = time.perf_counter() - t
        print(f"rescan 3 ({inf3.re_triados} sustituidos re-triados): {dt:.2f}s")

        print("0 errores" if not inf1.errores and not inf2.errores and not inf3.errores
              else f"errores: {inf1.errores[:3]} {inf2.errores[:3]} {inf3.errores[:3]}")
        await motor.dispose()


if __name__ == "__main__":
    import asyncio as _a
    _url = os.environ.get("TEST_DATABASE_URL")
    if not _url:
        raise SystemExit("fija TEST_DATABASE_URL (base de pruebas, nombre con «test»)")
    with bd_efimera_sync(_url) as url_efimera:
        migrar_a_head(url_efimera)
        _a.run(main(url_efimera))
