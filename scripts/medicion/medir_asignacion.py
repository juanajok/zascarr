#!/usr/bin/env python3
# ruff: noqa: E501, B023, N818, SIM105
"""Mide el coste del contrato de asignación recuperable (ADR 0006), con ficheros y Postgres reales.

    TEST_DATABASE_URL=postgresql://... python scripts/medicion/medir_asignacion.py --dir /ruta/en/el/disco/real

NO escribe fuera de `--dir` (crea una subcarpeta propia y la borra al terminar) y solo toca una base de
datos EFÍMERA que crea y borra. Mide, para ficheros de 10 a 200 MB (CBZ típicos):

  - rename en el mismo disco (lo que hace `safe_move` hoy),
  - copia + fsync + verificación sha256 (el camino general del contrato),
  - el hash por separado (el coste que más pesa en una Pi sin extensiones criptográficas),
  - espacio temporal extra,
  - recuperar UNA operación huérfana, y listar operaciones vivas con 20 000 cerradas (índice parcial),
  - para el ADR: consultar un marcador en `File.metadata_` (JSONB) con 50 000 filas, sin índice.

Las cifras son de ESTA máquina y de caché caliente (no se puede vaciar sin root): sirven para comparar
caminos entre sí, no para prometer tiempos en una Raspberry Pi.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

RAIZ = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(RAIZ / "src"), str(RAIZ)]

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from tests._pg import bd_efimera, migrar_a_head, url_asyncpg  # noqa: E402
from tests.prototipo_asignacion import DDL, AsignacionRecuperable  # noqa: E402
from zascarr.models import ComicTradition, File, FileFormat, Series  # noqa: E402


def mediana(xs): return statistics.median(xs)


def escribir_fichero(ruta: Path, mb: int) -> str:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with open(ruta, "wb") as f:
        for _ in range(mb):
            bloque = os.urandom(1024 * 1024)
            f.write(bloque)
            h.update(bloque)
        f.flush()
        os.fsync(f.fileno())
    return h.hexdigest()


def sha256(ruta: Path) -> str:
    with open(ruta, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def tiempo(fn, repeticiones=3):
    ts = []
    for _ in range(repeticiones):
        t = time.perf_counter()
        fn()
        ts.append(time.perf_counter() - t)
    return mediana(ts)


def medir_ficheros(base: Path) -> dict:
    res = {}
    for mb in (10, 50, 100, 200):
        origen = base / "origen" / f"{mb}.cbz"
        destino = base / "destino" / f"{mb}.cbz"
        temporal = base / "destino" / f".{mb}.part"
        sha = escribir_fichero(origen, mb)
        destino.parent.mkdir(exist_ok=True)

        def rename():
            os.replace(origen, destino)
            os.replace(destino, origen)

        def copiar_y_verificar():
            shutil.copyfile(origen, temporal)
            with open(temporal, "rb") as f:
                os.fsync(f.fileno())
            assert sha256(temporal) == sha
            temporal.unlink()

        res[mb] = {
            "rename_s (ida y vuelta /2)": round(tiempo(rename) / 2, 4),
            "copia+fsync+sha256_s": round(tiempo(copiar_y_verificar), 3),
            "solo_sha256_s": round(tiempo(lambda: sha256(origen)), 3),
            "solo_copia_s": round(tiempo(lambda: (shutil.copyfile(origen, temporal), temporal.unlink())), 3),
            "espacio_temporal_extra_MB": mb,
        }
        origen.unlink()
    return res


async def medir_bd(url: str, base: Path) -> dict:
    out = {}
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    async with motor.begin() as c:
        for s in [x for x in DDL.split(";\n") if x.strip()]:
            await c.execute(text(s))
    # 50 000 filas de files (con una clave en metadata_ en 1 de cada 1000) para la consulta sin índice
    async with fab() as s:
        serie = Series(id=uuid4(), title="Medición", tradition=ComicTradition.AMERICAN)
        s.add(serie)
        await s.commit()
    async with motor.begin() as c:
        await c.execute(text("""
            INSERT INTO files (id, file_path, file_name, file_format, metadata)
            SELECT gen_random_uuid(), '/m/' || g || '.cbz', g || '.cbz', 'cbz',
                   CASE WHEN g % 1000 = 0 THEN '{"asignacion_pendiente": {"op": "x"}, "match_status": "unsorted"}'::jsonb
                        ELSE '{"match_status": "unsorted", "comicinfo_propio": {"a": 1}}'::jsonb END
            FROM generate_series(1, 50000) g"""))
        await c.execute(text("ANALYZE files"))
    async with motor.connect() as c:
        ts = []
        for _ in range(5):
            t = time.perf_counter()
            n = (await c.execute(text("SELECT count(*) FROM files WHERE metadata ? 'asignacion_pendiente'"))).scalar()
            ts.append(time.perf_counter() - t)
        plan = (await c.execute(text("EXPLAIN SELECT count(*) FROM files WHERE metadata ? 'asignacion_pendiente'"))).all()
    out["metadata_con_50000_filas"] = {"consulta_mediana_ms": round(mediana(ts) * 1000, 1), "encontradas": n,
                                       "plan": " | ".join(r[0] for r in plan[:3])}

    # 20 000 operaciones cerradas + 1 viva: el índice parcial hace que listar las vivas no dependa de las cerradas.
    async with motor.begin() as c:
        await c.execute(text("""
            INSERT INTO asignacion_operaciones (file_id, estado, origen, destino, temporal, size_bytes, mtime_ns, sha256, series_id, issue_number, formato)
            SELECT f.id, 'limpiada', f.file_path, '/d/' || row_number() OVER (), '/t', 1, 1, 'x', :s, '1', 'single_issue'
            FROM (SELECT id, file_path FROM files LIMIT 20000) f"""), {"s": serie.id})
        await c.execute(text("ANALYZE asignacion_operaciones"))
    async with motor.connect() as c:
        ts = []
        for _ in range(5):
            t = time.perf_counter()
            await c.execute(text("SELECT id FROM asignacion_operaciones WHERE estado IN ('preparada','confirmada') ORDER BY creada"))
            ts.append(time.perf_counter() - t)
        plan = (await c.execute(text("EXPLAIN SELECT id FROM asignacion_operaciones WHERE estado IN ('preparada','confirmada')"))).all()
    out["operaciones_vivas_con_20000_cerradas"] = {"consulta_mediana_ms": round(mediana(ts) * 1000, 2),
                                                   "plan": " | ".join(r[0] for r in plan[:2])}

    # Recuperar una operación huérfana (muerta tras publicar) de 100 MB.
    async with motor.begin() as c:
        await c.execute(text("TRUNCATE asignacion_operaciones, files CASCADE"))
    lib = base / "lib"
    origen = lib / "_Unsorted" / "Saga 12.cbz"
    sha = escribir_fichero(origen, 100)
    async with fab() as s:
        f = File(id=uuid4(), file_path=str(origen), file_name=origen.name, file_format=FileFormat.CBZ,
                 file_size_bytes=origen.stat().st_size, sha256_hash=sha, metadata_={"match_status": "unsorted"})
        s.add(f)
        await s.commit()
    class Muerte(Exception): ...
    async def gancho(punto):
        if punto == "tras_publicar":
            raise Muerte
    svc = AsignacionRecuperable(fab, lib, gancho=gancho)
    try:
        await svc.asignar(f.id, serie.id, "12")
    except Muerte:
        pass
    t = time.perf_counter()
    r = await AsignacionRecuperable(fab, lib).reconciliar()
    out["recuperar_una_operacion_100MB_publicada_sin_confirmar_s"] = {"s": round(time.perf_counter() - t, 3), "resultado": [x.estado for x in r]}

    # Camino completo (preparar+copiar+verificar+publicar+confirmar+limpiar) frente a rename, 100 MB.
    ts = []
    for i in range(3):
        o = lib / "_Unsorted" / f"Saga {20 + i}.cbz"
        sha = escribir_fichero(o, 100)
        async with fab() as s:
            ff = File(id=uuid4(), file_path=str(o), file_name=o.name, file_format=FileFormat.CBZ,
                      file_size_bytes=o.stat().st_size, sha256_hash=sha, metadata_={"match_status": "unsorted"})
            s.add(ff)
            await s.commit()
        t = time.perf_counter()
        res = await AsignacionRecuperable(fab, lib).asignar(ff.id, serie.id, str(20 + i))
        ts.append(time.perf_counter() - t)
        assert res.estado == "asignado", res
    out["asignar_un_archivo_de_100MB_extremo_a_extremo_s"] = [round(x, 3) for x in ts]
    await motor.dispose()
    return out


def info_disco(ruta: Path) -> str:
    r = subprocess.run(["findmnt", "-T", str(ruta), "-no", "FSTYPE,SOURCE"], capture_output=True, text=True)
    return r.stdout.strip()


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, type=Path, help="carpeta (en el disco a medir) donde crear la subcarpeta de trabajo")
    args = ap.parse_args()
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        sys.exit("falta TEST_DATABASE_URL (apunta a una base de PRUEBAS; se crea y borra una efímera)")
    base = Path(tempfile.mkdtemp(prefix="zascarr_medicion_", dir=args.dir))
    try:
        salida = {"maquina": {"python": platform.python_version(), "cpu": platform.processor() or platform.machine(),
                              "nucleos": os.cpu_count(), "disco": info_disco(base)}}
        salida["ficheros"] = medir_ficheros(base)
        async with bd_efimera(url) as efimera:
            migrar_a_head(efimera)
            salida["bd"] = await medir_bd(efimera, base)
        print(json.dumps(salida, indent=2, ensure_ascii=False))
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
