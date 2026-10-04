#!/usr/bin/env python3
# ruff: noqa: E501, B023, N818, SIM105
"""Mide el coste del contrato de asignación recuperable (ADR 0006), con ficheros y Postgres reales.

    TEST_DATABASE_URL=postgresql://... python scripts/medicion/medir_asignacion.py --dir RUTA [--dir RUTA2 ...]

Lo normal es lanzarlo DESDE EL CONTENEDOR con `scripts/medicion/medir_asignacion.sh`, que levanta una
Postgres aislada, monta SOLO las carpetas que se le indiquen y lo borra todo al terminar.

NO escribe fuera de cada `--dir` (crea una subcarpeta propia, `zascarr_medicion_*`, y la borra al terminar;
el directorio debe existir y no se crea) y solo toca una base de datos EFÍMERA que crea y borra. Para cada
`--dir` mide:

  - CAPACIDADES del montaje: `renameat2(RENAME_NOREPLACE)`, `link`, `fsync` de fichero y de directorio, y si
    `rename` sobre un nombre existente lo reemplaza (lo que decide si el montaje se acepta o se rechaza).

Y, para ficheros de 10 a 200 MB (CBZ típicos):

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
import errno
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
from zascarr.services.asignacion import AsignacionService  # noqa: E402
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


def capacidades(base: Path) -> dict:
    """Qué garantías ofrece ESTE montaje a la publicación sin reemplazo (decide aceptar o rechazar)."""
    from zascarr.services.asignacion import (
        PublicacionNoSoportadaError,
        _publicar,
        _renameat2_noreplace,
    )
    d = base / "capacidades"
    d.mkdir()
    res = {}

    def intentar(nombre, fn):
        try:
            fn()
            res[nombre] = "ok"
        except OSError as exc:
            res[nombre] = f"{errno.errorcode.get(exc.errno, exc.errno)}: {exc.strerror}"

    a, b, c = d / "a", d / "b", d / "c"
    a.write_bytes(b"A")
    intentar("renameat2_noreplace_destino_libre", lambda: _renameat2_noreplace(a, b))
    a2 = d / "a2"
    a2.write_bytes(b"A2")
    try:
        _renameat2_noreplace(a2, b)
        res["renameat2_noreplace_destino_ocupado"] = "REEMPLAZÓ (MAL)"
    except FileExistsError:
        res["renameat2_noreplace_destino_ocupado"] = "EEXIST (bien)"
    except OSError as exc:
        res["renameat2_noreplace_destino_ocupado"] = f"{errno.errorcode.get(exc.errno, exc.errno)}: {exc.strerror}"
    intentar("link", lambda: os.link(a2, c))
    res["replace_sobre_existente_reemplaza"] = (lambda: (os.replace(a2, b), b.read_bytes() == b"A2")[1])() if a2.exists() else None

    def fsync_fichero():
        with open(b, "rb") as f:
            os.fsync(f.fileno())

    def fsync_dir():
        fd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    intentar("fsync_fichero", fsync_fichero)
    intentar("fsync_directorio", fsync_dir)
    # Lo que haría el servicio de verdad:
    x, y = d / "x.part", d / "y.cbz"
    x.write_bytes(b"N")
    y.write_bytes(b"AJENO")
    try:
        _publicar(x, y)
        res["_publicar_con_ajeno"] = "REEMPLAZÓ (MAL)" if y.read_bytes() == b"N" else "?"
    except FileExistsError:
        res["_publicar_con_ajeno"] = "FileExistsError, ajeno intacto (bien)" if y.read_bytes() == b"AJENO" else "AJENO ALTERADO (MAL)"
    except PublicacionNoSoportadaError as exc:
        res["_publicar_con_ajeno"] = f"montaje RECHAZADO: {exc}"
    y.unlink()
    x2 = d / "x2.part"
    x2.write_bytes(b"N")
    try:
        _publicar(x2, y)
        res["_publicar_libre"] = "ok" if y.read_bytes() == b"N" else "contenido distinto"
    except PublicacionNoSoportadaError as exc:
        res["_publicar_libre"] = f"montaje RECHAZADO: {exc}"
    shutil.rmtree(d, ignore_errors=True)
    return res


def medir_ficheros(base: Path, tamanos: list[int]) -> dict:
    res = {}
    for mb in tamanos:
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
            "rename_s": round(tiempo(rename) / 2, 4),
            "copia+fsync+sha256_s": round(tiempo(copiar_y_verificar), 3),
            "solo_sha256_s": round(tiempo(lambda: sha256(origen)), 3),
            "solo_copia_s": round(tiempo(lambda: (shutil.copyfile(origen, temporal), temporal.unlink())), 3),
            "espacio_temporal_extra_MB": mb,
        }
        origen.unlink()
    return res


async def sembrar_serie(fab) -> object:
    async with fab() as s:
        serie = Series(id=uuid4(), title="Medición", tradition=ComicTradition.AMERICAN)
        s.add(serie)
        await s.commit()
    return serie


async def medir_extremo_a_extremo(fab, serie, base: Path, mb_archivo: int, n: int,
                                  origen_base: Path | None = None) -> dict:
    """Asignar N archivos de `mb_archivo` MB con el servicio, por el camino completo.

    Los archivos de origen viven en `origen_base/_Unsorted` (por defecto, la misma carpeta que la biblioteca
    de destino `base/lib`); con `origen_base` en OTRO dispositivo se mide la copia entre dispositivos."""
    lib = base / "lib"
    pendientes = (origen_base or base) / "lib" / "_Unsorted"
    class Muerte(Exception): ...
    # Recuperar una operación huérfana (muerta tras publicar).
    origen = pendientes / "Saga 1.cbz"
    sha = escribir_fichero(origen, mb_archivo)
    async with fab() as s:
        f = File(id=uuid4(), file_path=str(origen), file_name=origen.name, file_format=FileFormat.CBZ,
                 file_size_bytes=origen.stat().st_size, sha256_hash=sha, metadata_={"match_status": "unsorted"})
        s.add(f)
        await s.commit()

    async def gancho(punto):
        if punto == "tras_publicar":
            raise Muerte
    try:
        await AsignacionService(fab, lib, gancho=gancho).asignar(f.id, serie.id, "1")
    except Muerte:
        pass
    t = time.perf_counter()
    r = await AsignacionService(fab, lib).reconciliar()
    recuperar = round(time.perf_counter() - t, 3)

    tiempos = []
    for i in range(n):
        o = pendientes / f"Saga {10 + i}.cbz"
        sha = escribir_fichero(o, mb_archivo)
        async with fab() as s:
            ff = File(id=uuid4(), file_path=str(o), file_name=o.name, file_format=FileFormat.CBZ,
                      file_size_bytes=o.stat().st_size, sha256_hash=sha, metadata_={"match_status": "unsorted"})
            s.add(ff)
            await s.commit()
        t = time.perf_counter()
        res = await AsignacionService(fab, lib).asignar(ff.id, serie.id, str(10 + i))
        tiempos.append(time.perf_counter() - t)
        assert res.estado == "asignado", res
    total = sum(tiempos)
    return {f"recuperar_una_operacion_huerfana_{mb_archivo}MB_s": recuperar, "resultado_recuperar": [x.estado for x in r],
            f"asignar_{n}_archivos_de_{mb_archivo}MB_s": [round(x, 3) for x in tiempos],
            "rendimiento_MB_por_s": round(mb_archivo * n / total, 1)}


async def medir_bd(url: str) -> dict:
    """Lo que no depende del disco de los ficheros: consultas sobre tablas grandes."""
    out = {}
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    serie = await sembrar_serie(fab)
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
    out["metadata_con_50000_filas"] = {"consulta_mediana_ms": round(mediana(ts) * 1000, 1), "encontradas": n}
    async with motor.begin() as c:
        await c.execute(text("""
            INSERT INTO asignacion_operaciones (file_id, estado, origen, destino, temporal, size_bytes, mtime_ns, sha256, series_id, issue_number, formato)
            SELECT f.id, 'limpiada', f.file_path, '/d/' || row_number() OVER (), '/t', 1, 1, repeat('a', 64), :s, '1', 'single_issue'
            FROM (SELECT id, file_path FROM files LIMIT 20000) f"""), {"s": serie.id})
        await c.execute(text("ANALYZE asignacion_operaciones"))
        ts = []
    async with motor.connect() as c:
        for _ in range(5):
            t = time.perf_counter()
            await c.execute(text("SELECT id FROM asignacion_operaciones WHERE estado IN ('preparada','confirmada') ORDER BY creada"))
            ts.append(time.perf_counter() - t)
    out["operaciones_vivas_con_20000_cerradas_ms"] = round(mediana(ts) * 1000, 2)
    await motor.dispose()
    return out


def info_disco(ruta: Path) -> str:
    r = subprocess.run(["findmnt", "-T", str(ruta), "-no", "FSTYPE,SOURCE,OPTIONS"], capture_output=True, text=True)
    return r.stdout.strip() or "(findmnt no disponible en este entorno)"


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", action="append", required=True, type=Path, help="carpeta EXISTENTE donde crear la subcarpeta de trabajo (repetible)")
    ap.add_argument("--tamanos", default="10,50,100,200", help="MB de los ficheros de prueba, separados por comas")
    ap.add_argument("--archivos", type=int, default=5, help="cuántos ficheros asignar de punta a punta por carpeta")
    ap.add_argument("--mb-extremo", type=int, default=100, help="tamaño (MB) de esos ficheros")
    ap.add_argument("--cruzado", metavar="ORIGEN,DESTINO", help="además, asignar con el origen en una carpeta y la "
                    "biblioteca en OTRA (posiciones 1-based de los --dir, p. ej. 2,3): mide la copia entre dispositivos")
    args = ap.parse_args()
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        sys.exit("falta TEST_DATABASE_URL (apunta a una base de PRUEBAS; se crea y borra una efímera)")
    tamanos = [int(x) for x in args.tamanos.split(",")]
    cruce = None
    if args.cruzado:
        try:
            a, b = (int(x) for x in args.cruzado.split(","))
        except ValueError:
            sys.exit("--cruzado debe ser «ORIGEN,DESTINO» con dos posiciones numéricas (p. ej. 2,3)")
        if a == b or not (1 <= a <= len(args.dir) and 1 <= b <= len(args.dir)):
            sys.exit(f"--cruzado {args.cruzado}: deben ser dos posiciones DISTINTAS entre 1 y {len(args.dir)}")
        cruce = (a - 1, b - 1)
    necesario = (max(tamanos) * 3 + args.mb_extremo * 3) * 1024 * 1024
    for d in args.dir:
        if not d.is_dir():
            sys.exit(f"{d} no existe o no es una carpeta: no se crea (indica una carpeta de ensayo que ya exista)")
        libre = shutil.disk_usage(d).free
        if libre < necesario * 2:
            sys.exit(f"{d}: queda poco espacio libre ({libre // 2**20} MB) para la medición ({necesario * 2 // 2**20} MB)")
    salida = {"maquina": {"python": platform.python_version(), "plataforma": platform.platform(),
                          "cpu": platform.processor() or platform.machine(), "nucleos": os.cpu_count()},
              "directorios": {}}
    async with bd_efimera(url) as efimera:
        migrar_a_head(efimera)
        motor = create_async_engine(url_asyncpg(efimera), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        serie = None
        serie = await sembrar_serie(fab)
        for d in args.dir:
            base = Path(tempfile.mkdtemp(prefix="zascarr_medicion_", dir=d))
            try:
                async with motor.begin() as c:
                    await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, local_aliases CASCADE"))
                r = {"montaje": info_disco(base), "capacidades": capacidades(base),
                     "ficheros": medir_ficheros(base, tamanos)}
                r["extremo_a_extremo"] = await medir_extremo_a_extremo(fab, serie, base, args.mb_extremo, args.archivos)
                salida["directorios"][str(d)] = r
            finally:
                shutil.rmtree(base, ignore_errors=True)
        if cruce is not None:
            di, dj = args.dir[cruce[0]], args.dir[cruce[1]]
            base_o = Path(tempfile.mkdtemp(prefix="zascarr_medicion_", dir=di))
            base_d = Path(tempfile.mkdtemp(prefix="zascarr_medicion_", dir=dj))
            try:
                async with motor.begin() as c:
                    await c.execute(text("TRUNCATE asignacion_operaciones, files, issues, local_aliases CASCADE"))
                same = os.stat(base_o).st_dev == os.stat(base_d).st_dev
                salida["cruce"] = {
                    "origen": str(di), "destino": str(dj), "mismo_dispositivo": same,
                    "montaje_origen": info_disco(base_o), "montaje_destino": info_disco(base_d),
                    "extremo_a_extremo": await medir_extremo_a_extremo(
                        fab, serie, base_d, args.mb_extremo, args.archivos, origen_base=base_o)}
            finally:
                shutil.rmtree(base_o, ignore_errors=True)
                shutil.rmtree(base_d, ignore_errors=True)
        await motor.dispose()
    async with bd_efimera(url) as efimera2:
        migrar_a_head(efimera2)
        salida["bd"] = await medir_bd(efimera2)
    print(json.dumps(salida, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
