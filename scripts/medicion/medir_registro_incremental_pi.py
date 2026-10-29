#!/usr/bin/env python3
"""Medición E de #326: coste de «Buscar archivos sin registrar» y «Registrar».

Se ejecuta **dentro de un contenedor desechable** de la app, contra una base de
datos de medición cuyo nombre lleva `test` (nunca la base de producción) y con
la biblioteca montada en solo lectura. No escribe en la biblioteca ni en
producción: el registro escribe solo en el clon desechable.

Modos:
  seed       registra los archivos ya presentes (preparación de los sintéticos)
  synthetic  E1 (inventario) + E2 (inventario + registro incremental)
  search     E3 (coste del inventario) + E3c (cobertura), sesión de solo lectura
  register   E4 (registro de una muestra acotada) sobre el clon de trabajo

La salida es un JSON saneado por stdout (sin rutas) y un resumen por stderr.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
import platform
import random
import sys
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from zascarr.config import get_settings
from zascarr.core.importer_triage import sha256_streaming
from zascarr.services import library_adopter as la
from zascarr.services.library_adopter import AdoptionReport, InventarioBiblioteca, LibraryAdopter

MIB = 1024 * 1024
GIB = 1024 * MIB
SCHEMA = 1

#: sufijo obligatorio del nombre de la base según el modo
SUFIJO_BD = {
    "seed": "_sint_test_",
    "synthetic": "_sint_test_",
    "search": "_ref_test_",
    "register": "_reg_test_",
}
#: presupuestos del plan autorizado (se pueden endurecer, no relajar, por CLI)
PRESUPUESTO = {
    "E1": {"s": 10, "rss_kib": 256 * 1024, "contenido_bytes": 10 * MIB},
    "E2": {"s": 300, "rss_kib": 512 * 1024, "amplificacion": 1.2},
    "E3": {"s": 60, "rss_kib": 256 * 1024, "contenido_bytes": 10 * MIB,
           "dispositivo_bytes": 100 * MIB},
    "E4": {"s": 1200, "rss_kib": 512 * 1024, "amplificacion": 1.2, "mb_s": 40.0},
}


class ErrorDeMedicion(RuntimeError):  # noqa: N818 — dominio en español
    """Error de uso o de seguridad: nunca incluye rutas ni nombres reales."""


# ── Utilidades ───────────────────────────────────────────────────────────────

def parse_bytes(valor: str) -> int:
    """Convierte `15GiB`, `100MB`, `1.5g` o un entero de bytes."""
    s = str(valor).strip().lower().replace(" ", "")
    if not s:
        raise argparse.ArgumentTypeError("tamaño vacío")
    unidades = {
        "tib": 1024 ** 4, "tb": 1024 ** 4,
        "gib": 1024 ** 3, "gb": 1024 ** 3, "g": 1024 ** 3,
        "mib": 1024 ** 2, "mb": 1024 ** 2, "m": 1024 ** 2,
        "kib": 1024, "kb": 1024, "k": 1024,
        "b": 1,
    }
    for sufijo, factor in unidades.items():
        if s.endswith(sufijo):
            numero = s[: -len(sufijo)]
            try:
                return int(float(numero) * factor)
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"tamaño no válido: {valor!r}") from exc
    try:
        return int(s)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"tamaño no válido: {valor!r}") from exc


def url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def validar_db_url(db_url: str, mode: str) -> str:
    """Exige una BD de medición `*_test_*` y del tipo correcto. Nunca producción."""
    url = make_url(db_url)
    nombre = (url.database or "").lower()
    if "test" not in nombre:
        raise ErrorDeMedicion("la base de datos no lleva 'test' en el nombre")
    if nombre == "zascarr" or nombre.startswith("zascarr_prod"):
        raise ErrorDeMedicion("la base de datos parece la de producción")
    if SUFIJO_BD[mode] not in nombre:
        raise ErrorDeMedicion(f"la base de datos no es del tipo {mode}")
    return url.database or ""


def _leer_montajes(mounts_path: Path = Path("/proc/self/mounts")) -> list[tuple[str, str]]:
    """Pares (punto de montaje, opciones) de /proc/self/mounts."""
    salida: list[tuple[str, str]] = []
    try:
        with mounts_path.open(encoding="utf-8") as fh:
            for linea in fh:
                campos = linea.split()
                if len(campos) < 4:
                    continue
                punto = campos[1].replace("\\040", " ").replace("\\011", "\t")
                salida.append((punto, campos[3]))
    except OSError:
        return []
    return salida


def opciones_de_montaje(ruta: Path, mounts_path: Path = Path("/proc/self/mounts")) -> str | None:
    """Opciones del montaje que contiene `ruta` (el más específico)."""
    destino = str(Path(ruta).resolve())
    mejor: tuple[str, str] | None = None
    for punto, opciones in _leer_montajes(mounts_path):
        coincide = punto == "/" or destino == punto or destino.startswith(punto.rstrip("/") + "/")
        if coincide and (mejor is None or len(punto) > len(mejor[0])):
            mejor = (punto, opciones)
    return mejor[1] if mejor else None


def es_solo_lectura(ruta: Path, mounts_path: Path = Path("/proc/self/mounts")) -> bool:
    opciones = opciones_de_montaje(ruta, mounts_path)
    return bool(opciones and "ro" in opciones.split(","))


def _leer_io() -> dict[str, int]:
    salida: dict[str, int] = {}
    try:
        with Path("/proc/self/io").open(encoding="utf-8") as fh:
            for linea in fh:
                clave, _, valor = linea.partition(":")
                try:
                    salida[clave.strip()] = int(valor.strip())
                except ValueError:
                    continue
    except OSError:
        pass
    return salida


def _restar_io(antes: dict[str, int], despues: dict[str, int]) -> dict[str, int]:
    return {k: despues.get(k, 0) - antes.get(k, 0) for k in set(antes) | set(despues)}


def _rss_kib() -> int:
    try:
        with Path("/proc/self/status").open(encoding="utf-8") as fh:
            for linea in fh:
                if linea.startswith("VmRSS:"):
                    return int(linea.split()[1])
    except (OSError, ValueError):
        pass
    return 0


class MuestreadorMemoria(threading.Thread):
    """Pico de RSS del proceso durante una fase, sin depender de `ru_maxrss`."""

    def __init__(self, intervalo: float = 0.05):
        super().__init__(daemon=True)
        self.intervalo = intervalo
        self.max_kib = 0
        self._parar = threading.Event()

    def run(self) -> None:
        while not self._parar.wait(self.intervalo):
            self.max_kib = max(self.max_kib, _rss_kib())

    def iniciar(self) -> None:
        self.max_kib = _rss_kib()
        self.start()

    def parar(self) -> int:
        self._parar.set()
        self.join(timeout=2)
        self.max_kib = max(self.max_kib, _rss_kib())
        return self.max_kib


def _percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    if len(ordenados) == 1:
        return ordenados[0]
    pos = (len(ordenados) - 1) * p
    bajo = int(pos)
    alto = min(bajo + 1, len(ordenados) - 1)
    return ordenados[bajo] + (ordenados[alto] - ordenados[bajo]) * (pos - bajo)


def _resumen_tiempos(valores: list[float]) -> dict[str, float]:
    return {
        "p50": round(_percentil(valores, 0.50), 6),
        "p95": round(_percentil(valores, 0.95), 6),
        "max": round(max(valores), 6) if valores else 0.0,
    }


def _sha_manifiesto(rutas: list[Path]) -> str:
    return hashlib.sha256("\n".join(sorted(str(r) for r in rutas)).encode()).hexdigest()


def seleccionar_muestra(
    rutas: list[Path], *, max_files: int, max_bytes: int, seed: int = 326,
) -> tuple[list[Path], dict[str, Any]]:
    """Muestra determinista y estratificada por extensión y tamaño.

    No lee contenido: solo `stat`. Reparte el cupo de archivos y de bytes entre
    los grupos no vacíos y elige dentro de cada grupo con una semilla fija.
    """
    if max_files <= 0 or max_bytes <= 0:
        raise ErrorDeMedicion("los topes de la muestra deben ser positivos")
    items: list[tuple[Path, int, str, str]] = []
    for ruta in rutas:
        try:
            tam = ruta.stat().st_size
        except OSError:
            continue
        sufijo = ruta.suffix.lower()
        grupo_ext = sufijo if sufijo in (".cbz", ".cbr") else "otros"
        if tam < 50 * MIB:
            grupo_tam = "pequeno"
        elif tam < 300 * MIB:
            grupo_tam = "mediano"
        else:
            grupo_tam = "grande"
        items.append((ruta, tam, grupo_ext, grupo_tam))
    if not items:
        return [], {"available": 0, "selected": 0, "bytes": 0,
                   "by_format": {}, "by_size": {}, "manifest_sha256": _sha_manifiesto([])}

    grupos: dict[tuple[str, str], list[tuple[Path, int]]] = {}
    for ruta, tam, grupo_ext, grupo_tam in items:
        grupos.setdefault((grupo_ext, grupo_tam), []).append((ruta, tam))
    for clave in grupos:
        random.Random(f"{seed}:{clave[0]}:{clave[1]}").shuffle(grupos[clave])

    # Cupo de archivos por grupo, proporcional al número de candidatos.
    total = len(items)
    cupo_archivos: dict[tuple[str, str], int] = {}
    for clave, candidatos in grupos.items():
        cupo_archivos[clave] = max(1, round(max_files * len(candidatos) / total))
    # Ajuste fino al máximo (o al número disponible).
    while sum(cupo_archivos.values()) > max_files:
        clave = max(cupo_archivos, key=cupo_archivos.get)
        cupo_archivos[clave] -= 1
    # Cupo de bytes por grupo, proporcional a los bytes disponibles, sin superar
    # el global. Se reserva al menos un archivo por grupo no vacío.
    bytes_global = max_bytes
    pesos = {clave: sum(t for _, t in cand) for clave, cand in grupos.items()}
    total_peso = sum(pesos.values()) or 1
    cupo_bytes: dict[tuple[str, str], int] = {}
    for clave, peso in pesos.items():
        cupo_bytes[clave] = max(1, int(bytes_global * peso / total_peso))

    elegidos: list[Path] = []
    bytes_elegidos = 0
    by_format: dict[str, int] = {}
    by_size: dict[str, int] = {}
    for clave in sorted(grupos):
        candidatos = grupos[clave]
        n_max = cupo_archivos[clave]
        b_max = cupo_bytes[clave]
        n = 0
        b = 0
        for ruta, tam in candidatos:
            if n >= n_max or len(elegidos) >= max_files:
                break
            if b + tam > b_max or bytes_elegidos + tam > max_bytes:
                continue
            elegidos.append(ruta)
            bytes_elegidos += tam
            b += tam
            n += 1
            by_format[clave[0]] = by_format.get(clave[0], 0) + 1
            by_size[clave[1]] = by_size.get(clave[1], 0) + 1
    return elegidos, {
        "available": len(items),
        "selected": len(elegidos),
        "bytes": bytes_elegidos,
        "by_format": by_format,
        "by_size": by_size,
        "manifest_sha256": _sha_manifiesto(elegidos),
    }


# ── Instrumentación de BD ────────────────────────────────────────────────────

async def _forzar_estadisticas(session: AsyncSession) -> None:
    with contextlib.suppress(Exception):
        await session.execute(text("SELECT pg_stat_force_next_flush()"))


async def _db_stats(session: AsyncSession) -> dict[str, Any]:
    await _forzar_estadisticas(session)
    fila = (await session.execute(text("""
        SELECT coalesce(tup_inserted, 0), coalesce(tup_updated, 0), coalesce(tup_deleted, 0),
               coalesce(blks_read, 0), coalesce(blks_hit, 0), coalesce(temp_bytes, 0),
               coalesce(xact_commit, 0)
          FROM pg_stat_database WHERE datname = current_database()
    """))).one()
    tablas: dict[str, dict[str, int]] = {}
    for relname, ins, upd, dele, seq, idx in (await session.execute(text("""
        SELECT relname, coalesce(n_tup_ins, 0), coalesce(n_tup_upd, 0), coalesce(n_tup_del, 0),
               coalesce(seq_scan, 0), coalesce(idx_scan, 0)
          FROM pg_stat_user_tables WHERE relname IN ('files', 'import_runs')
    """))).all():
        tablas[relname] = {"ins": int(ins), "upd": int(upd), "del": int(dele),
                           "seq_scan": int(seq), "idx_scan": int(idx)}
    tamano = (await session.execute(text("SELECT pg_database_size(current_database())"))).scalar()
    return {
        "tup_inserted": int(fila[0]), "tup_updated": int(fila[1]), "tup_deleted": int(fila[2]),
        "blks_read": int(fila[3]), "blks_hit": int(fila[4]), "temp_bytes": int(fila[5]),
        "xact_commit": int(fila[6]), "size_bytes": int(tamano or 0), "tables": tablas,
    }


def _db_delta(antes: dict[str, Any], despues: dict[str, Any]) -> dict[str, Any]:
    delta = {k: despues[k] - antes[k] for k in
             ("tup_inserted", "tup_updated", "tup_deleted", "blks_read", "blks_hit",
              "temp_bytes", "xact_commit", "size_bytes")}
    delta["tables"] = {
        nombre: {
            k: (despues["tables"].get(nombre, {}).get(k, 0)
                - antes["tables"].get(nombre, {}).get(k, 0))
            for k in ("ins", "upd", "del", "seq_scan", "idx_scan")
        }
        for nombre in set(antes["tables"]) | set(despues["tables"])
    }
    return delta


# ── Instrumentación del recorrido ───────────────────────────────────────────

@contextlib.contextmanager
def cronometrar_recorrido():
    """Sustituye `recorrer_comics` por un envoltorio que mide y guarda el resultado."""
    original = la.recorrer_comics
    tiempos: list[float] = []
    capturado: list[Any] = []

    def envuelto(*args, **kwargs):
        inicio = time.perf_counter()
        resultado = original(*args, **kwargs)
        tiempos.append(time.perf_counter() - inicio)
        capturado.append(resultado)
        return resultado

    la.recorrer_comics = envuelto
    try:
        yield tiempos, capturado
    finally:
        la.recorrer_comics = original


def _bytes_y_archivos(recorrido: Any) -> tuple[int, int]:
    if recorrido is None:
        return 0, 0
    archivos = getattr(recorrido, "archivos", [])
    total = 0
    for ruta in archivos:
        try:
            total += ruta.stat().st_size
        except OSError:
            continue
    return total, len(archivos)


# ── Medición ─────────────────────────────────────────────────────────────────

@dataclass
class Medida:
    total_s: float
    recorrido_s: float
    io: dict[str, int]
    db: dict[str, Any]
    rss_kib: int
    bytes_vistos: int = 0
    archivos_vistos: int = 0

    def como_dict(self) -> dict[str, Any]:
        return {
            "total_s": round(self.total_s, 3),
            "recorrido_s": round(self.recorrido_s, 3),
            "io": self.io,
            "db": self.db,
            "rss_kib": self.rss_kib,
            "bytes_vistos": self.bytes_vistos,
            "archivos_vistos": self.archivos_vistos,
        }


async def medir_inventario(
    adopter: LibraryAdopter, *, solo_lectura: bool = False,
) -> tuple[InventarioBiblioteca, Medida]:
    if solo_lectura:
        # `SET TRANSACTION READ ONLY` debe ser la primera orden de la
        # transacción. Se comprueba que de verdad quedó activa; cualquier
        # escritura posterior fallaría en PostgreSQL.
        await adopter._db.rollback()
        await adopter._db.execute(text("SET TRANSACTION READ ONLY"))
        modo = (await adopter._db.execute(text("SHOW transaction_read_only"))).scalar()
        if modo != "on":
            raise ErrorDeMedicion("no se pudo activar la transacción de solo lectura")
    sampler = MuestreadorMemoria()
    io0 = _leer_io()
    db0 = await _db_stats(adopter._db)
    with cronometrar_recorrido() as (tiempos, capturado):
        inicio = time.perf_counter()
        sampler.iniciar()
        inv = await adopter.inventario()
        rss = sampler.parar()
        total = time.perf_counter() - inicio
    io1 = _leer_io()
    db1 = await _db_stats(adopter._db)
    await adopter._db.rollback()
    bytes_vistos, archivos_vistos = _bytes_y_archivos(capturado[-1] if capturado else None)
    return inv, Medida(total, sum(tiempos), _restar_io(io0, io1), _db_delta(db0, db1),
                       rss, bytes_vistos, archivos_vistos)


async def medir_adopt(
    adopter: LibraryAdopter, alcance: frozenset[str] | None,
) -> tuple[AdoptionReport, Medida, dict[str, float]]:
    sampler = MuestreadorMemoria()
    io0 = _leer_io()
    db0 = await _db_stats(adopter._db)
    marcas: list[float] = []

    def progreso(_report: AdoptionReport) -> None:
        marcas.append(time.perf_counter())

    with cronometrar_recorrido() as (tiempos, capturado):
        inicio = time.perf_counter()
        sampler.iniciar()
        informe = await adopter.adopt(progreso=progreso, alcance=alcance)
        rss = sampler.parar()
        total = time.perf_counter() - inicio
    io1 = _leer_io()
    db1 = await _db_stats(adopter._db)
    await adopter._db.commit()
    intervalos = [b - a for a, b in zip(marcas, marcas[1:], strict=False) if b > a]
    bytes_vistos, archivos_vistos = _bytes_y_archivos(capturado[-1] if capturado else None)
    return informe, Medida(total, sum(tiempos), _restar_io(io0, io1), _db_delta(db0, db1),
                           rss, bytes_vistos, archivos_vistos), _resumen_tiempos(intervalos)


# ── Comprobaciones ───────────────────────────────────────────────────────────

def _check(nombre: str, condiciones: dict[str, bool], detalle: dict[str, Any]) -> dict[str, Any]:
    fallos = [clave for clave, ok in condiciones.items() if not ok]
    return {"pass": not fallos, "fail": fallos, "detalle": detalle}


def _amplificacion(io: dict[str, int], bytes_objetivo: int) -> float:
    if bytes_objetivo <= 0:
        return 0.0
    return max(io.get("rchar", 0), io.get("read_bytes", 0)) / bytes_objetivo


def _contenido_leido(io: dict[str, int]) -> int:
    # rchar incluye socket de BD; para la búsqueda el umbral es holgado.
    return int(io.get("rchar", 0))


def _resumen_modo(mode: str, checks: dict[str, Any]) -> None:
    print(f"[medicion-e] modo={mode}", file=sys.stderr)
    for nombre, check in checks.items():
        estado = "PASS" if check["pass"] else "FAIL"
        print(f"[medicion-e] {nombre}: {estado}", file=sys.stderr)
        if check["fail"]:
            print(f"[medicion-e]   fallos: {', '.join(check['fail'])}", file=sys.stderr)


# ── Programa principal ───────────────────────────────────────────────────────

async def _ejecutar(args: argparse.Namespace) -> dict[str, Any]:
    library = Path(args.library).resolve()
    if not library.is_dir():
        raise ErrorDeMedicion("la biblioteca no es un directorio")
    settings = get_settings()
    if Path(settings.library_path).resolve() != library:
        raise ErrorDeMedicion("LIBRARY_PATH no coincide con --library")
    if args.require_readonly and not es_solo_lectura(library):
        raise ErrorDeMedicion("la biblioteca no está montada en solo lectura")
    if args.library_kind == "real" and not es_solo_lectura(library):
        raise ErrorDeMedicion("la biblioteca real no está montada en solo lectura")
    if (args.mode in ("seed", "synthetic")) != (args.library_kind == "synthetic"):
        raise ErrorDeMedicion("modo y tipo de biblioteca no coinciden")
    if args.mode in ("search", "register") and args.library_kind != "real":
        raise ErrorDeMedicion("search/register exigen biblioteca real")

    db_url = args.db_url or os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise ErrorDeMedicion("falta --db-url o DATABASE_URL")
    nombre_bd = validar_db_url(db_url, args.mode)

    motor = create_async_engine(url_asyncpg(db_url), poolclass=NullPool)
    fabrica = async_sessionmaker(motor, expire_on_commit=False)
    resultado: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "ok",
        "mode": args.mode,
        "library_kind": args.library_kind,
        "started_at": datetime.now(UTC).isoformat(),
        "db": {"name": nombre_bd},
        "versions": {
            "python": platform.python_version(),
            "machine": platform.machine(),
            "kernel": platform.release(),
        },
        "commit": _commit_del_repo(),
        "checks": {},
    }
    try:
        async with fabrica() as session:
            info = (await session.execute(text(
                "SELECT current_database(), current_user, version()"))).one()
            if info[0] != nombre_bd:
                raise ErrorDeMedicion("la base conectada no es la esperada")
            resultado["db"]["server_version"] = str(info[2]).split(",")[0]
            adopter = LibraryAdopter(session)

            if args.mode == "seed":
                informe, medida, _ = await medir_adopt(adopter, None)
                resultado["seed"] = _resumen_adopt(informe, medida)
                resultado["checks"] = {}

            elif args.mode == "synthetic":
                # E1: inventario puro, en transacción de solo lectura.
                inv1, m1 = await medir_inventario(adopter, solo_lectura=True)
                # E2: el POST vuelve a inventariar y luego registra.
                inv2, m2 = await medir_inventario(adopter)
                alcance = frozenset(inv2.rutas_nuevas)
                bytes_alcance = sum(
                    Path(r).stat().st_size for r in alcance
                    if Path(r).exists()
                )
                informe, m3, tiempos = await medir_adopt(adopter, alcance)
                total_e2 = m2.total_s + m3.total_s
                amp = _amplificacion(m3.io, bytes_alcance)
                resultado["E1"] = _resumen_inventario(inv1, m1)
                resultado["E2"] = {
                    **_resumen_adopt(informe, m3),
                    "inventario_huella": _resumen_inventario(inv2, m2),
                    "total_s": round(total_e2, 3),
                    "per_file_s": tiempos,
                    "amplificacion": round(amp, 3),
                }
                resultado["checks"] = {
                    "E1": _check("E1", {
                        "tiempo": m1.total_s <= PRESUPUESTO["E1"]["s"],
                        "rss": m1.rss_kib <= PRESUPUESTO["E1"]["rss_kib"],
                        "sin_escrituras": (m1.db["tup_inserted"] == 0 and m1.db["tup_updated"] == 0
                                           and m1.db["tup_deleted"] == 0
                                           and all(t["ins"] == 0 and t["upd"] == 0 and t["del"] == 0
                                                   for t in m1.db["tables"].values())),
                        "contenido": (_contenido_leido(m1.io)
                                      <= PRESUPUESTO["E1"]["contenido_bytes"]),
                        "nuevos": inv1.nuevos == args.expected_new,
                        "viejos": inv1.ya_registrados == args.expected_old,
                        "ilegibles": inv1.ilegibles == 0,
                    }, {"total_s": m1.total_s, "rss_kib": m1.rss_kib, "nuevos": inv1.nuevos,
                        "ya_registrados": inv1.ya_registrados}),
                    "E2": _check("E2", {
                        "tiempo": total_e2 <= PRESUPUESTO["E2"]["s"],
                        "rss": max(m2.rss_kib, m3.rss_kib) <= PRESUPUESTO["E2"]["rss_kib"],
                        "sin_errores": informe.error_count == 0,
                        "amplificacion": amp <= PRESUPUESTO["E2"]["amplificacion"],
                        "anadidos": informe.added_count == args.expected_new,
                        "sin_repetidos": informe.duplicate_count == 0,
                        "sin_ambiguos": len(informe.ambiguous) == 0,
                        "sin_omitidos": len(informe.omitted) == 0,
                    }, {"total_s": total_e2, "rss_kib": max(m2.rss_kib, m3.rss_kib),
                        "amplificacion": amp, "anadidos": informe.added_count,
                        "errores": informe.error_count}),
                }

            elif args.mode == "search":
                pasadas = []
                for _ in range(max(1, args.repeat)):
                    inv, med = await medir_inventario(adopter, solo_lectura=True)
                    pasadas.append({"inventario": _resumen_inventario(inv, med),
                                    "medida": med.como_dict()})
                ultima = pasadas[-1]["inventario"]
                totales = [p["medida"]["total_s"] for p in pasadas]
                rss = [p["medida"]["rss_kib"] for p in pasadas]
                ior = [p["medida"]["io"].get("rchar", 0) for p in pasadas]
                iod = [p["medida"]["io"].get("read_bytes", 0) for p in pasadas]
                escrituras = all(p["medida"]["db"]["tup_inserted"] == 0
                                 and p["medida"]["db"]["tup_updated"] == 0
                                 and p["medida"]["db"]["tup_deleted"] == 0
                                 and all(t["ins"] == 0 and t["upd"] == 0 and t["del"] == 0
                                         for t in p["medida"]["db"]["tables"].values())
                                 for p in pasadas)
                resultado["E3"] = {"pasadas": pasadas, "total_s": _resumen_tiempos(totales),
                                   "rss_kib_max": max(rss), "rchar_max": max(ior),
                                   "read_bytes_max": max(iod)}
                cobertura_ok = all(
                    p["inventario"]["carpeta_accesible"] and p["inventario"]["ilegibles"] == 0
                    for p in pasadas
                )
                peor_ilegibles = max(p["inventario"]["ilegibles"] for p in pasadas)
                resultado["E3c"] = {"carpeta_accesible": all(
                                        p["inventario"]["carpeta_accesible"] for p in pasadas),
                                    "ilegibles": peor_ilegibles,
                                    "en_disco": ultima["en_disco"], "nuevos": ultima["nuevos"]}
                resultado["checks"] = {
                    "E3": _check("E3", {
                        "tiempo": _percentil(totales, 0.95) <= PRESUPUESTO["E3"]["s"],
                        "rss": max(rss) <= PRESUPUESTO["E3"]["rss_kib"],
                        "contenido": max(ior) <= PRESUPUESTO["E3"]["contenido_bytes"],
                        "dispositivo": max(iod) <= PRESUPUESTO["E3"]["dispositivo_bytes"],
                        "sin_escrituras": escrituras,
                    }, {"p95_s": _percentil(totales, 0.95), "rss_kib": max(rss),
                        "rchar_max": max(ior), "read_bytes_max": max(iod)}),
                    "E3c": _check("E3c", {
                        "cobertura": cobertura_ok,
                    }, {"carpeta_accesible": all(
                        p["inventario"]["carpeta_accesible"] for p in pasadas),
                        "ilegibles": peor_ilegibles}),
                }

            elif args.mode == "register":
                inv, m_inv = await medir_inventario(adopter)
                if not inv.recorrido_completo:
                    raise ErrorDeMedicion("el recorrido no es completo: no se registra")
                candidatas = [Path(r) for r in inv.rutas_nuevas]
                elegidas, seleccion = seleccionar_muestra(
                    candidatas, max_files=args.max_files, max_bytes=parse_bytes(args.max_bytes),
                    seed=args.seed,
                )
                if not elegidas:
                    raise ErrorDeMedicion("no hay archivos nuevos que registrar")
                antes = {r: (r.stat().st_size, r.stat().st_mtime_ns) for r in elegidas}
                muestras = sorted(
                    elegidas, key=lambda r: r.stat().st_size
                )[: args.verify_sha_samples]
                sha_antes = {r: sha256_streaming(r) for r in muestras}
                seleccion_rutas = frozenset(str(r) for r in elegidas)
                informe, m_reg, tiempos = await medir_adopt(adopter, seleccion_rutas)
                inicio_sha = time.perf_counter()
                despues = {r: (r.stat().st_size, r.stat().st_mtime_ns) for r in elegidas}
                sha_despues = {r: sha256_streaming(r) for r in muestras}
                fin_sha = time.perf_counter()
                cambios = sum(1 for r in elegidas if antes[r] != despues[r])
                sha_cambios = sum(1 for r in muestras if sha_antes[r] != sha_despues[r])
                bytes_objetivo = seleccion["bytes"] or 1
                amp = _amplificacion(m_reg.io, bytes_objetivo)
                mb_s = (seleccion["bytes"] / MIB) / m_reg.total_s if m_reg.total_s > 0 else 0.0
                resultado["E4"] = {
                    "inventario": _resumen_inventario(inv, m_inv),
                    "seleccion": seleccion,
                    "registro": _resumen_adopt(informe, m_reg),
                    "per_file_s": tiempos,
                    "amplificacion": round(amp, 3),
                    "mb_s": round(mb_s, 2),
                    "verificacion": {
                        "archivos": len(elegidas),
                        "cambios_tamano_mtime": cambios,
                        "sha_muestras": len(muestras),
                        "sha_cambios": sha_cambios,
                        "sha_s": round(fin_sha - inicio_sha, 3),
                    },
                }
                resultado["checks"] = {
                    "E4": _check("E4", {
                        "tiempo": m_reg.total_s <= PRESUPUESTO["E4"]["s"],
                        "rss": m_reg.rss_kib <= PRESUPUESTO["E4"]["rss_kib"],
                        "sin_errores": informe.error_count == 0,
                        "amplificacion": amp <= PRESUPUESTO["E4"]["amplificacion"],
                        "throughput": mb_s >= PRESUPUESTO["E4"]["mb_s"],
                        "sin_cambios": cambios == 0 and sha_cambios == 0,
                        "sin_omitidos": len(informe.omitted) == 0,
                        "cobertura": informe.unreadable == 0,
                    }, {"total_s": m_reg.total_s, "rss_kib": m_reg.rss_kib,
                        "mb_s": mb_s, "amplificacion": amp, "seleccion": seleccion,
                        "errores": informe.error_count}),
                }
    finally:
        await motor.dispose()
        resultado["finished_at"] = datetime.now(UTC).isoformat()
    return resultado


def _resumen_inventario(inv: InventarioBiblioteca, med: Medida) -> dict[str, Any]:
    return {
        "en_disco": inv.en_disco, "nuevos": inv.nuevos, "ya_registrados": inv.ya_registrados,
        "cbz": inv.cbz, "cbr": inv.cbr, "otros_formatos": inv.otros_formatos,
        "ilegibles": inv.ilegibles, "carpeta_accesible": inv.carpeta_accesible,
        "registrados_sin_fichero": inv.registrados_sin_fichero,
        "medida": med.como_dict(),
    }


def _resumen_adopt(informe: AdoptionReport, med: Medida) -> dict[str, Any]:
    return {
        "to_process": informe.to_process, "processed": informe.processed,
        "registered": informe.registered_count, "added": informe.added_count,
        "relinked": informe.relinked, "duplicates": informe.duplicate_count,
        "unsorted": informe.unsorted_count, "ambiguous": len(informe.ambiguous),
        "errors": informe.error_count, "omitted": len(informe.omitted),
        "vanished": informe.vanished, "unreadable": informe.unreadable,
        "medida": med.como_dict(),
    }


def _commit_del_repo() -> str | None:
    try:
        import subprocess
        salida = subprocess.run(
            ["git", "-C", str(Path(__file__).resolve().parents[2]), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        return salida.stdout.strip() if salida.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def _configurar_logs() -> None:
    """La app escribe logs de structlog con rutas; el JSON de stdout debe ir solo.

    Los logs van a stderr y se silencia INFO: el medidor no publica rutas.
    """
    structlog.configure(
        processors=[structlog.processors.KeyValueRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        cache_logger_on_first_use=False,
    )
    logging.disable(logging.INFO)


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Medición E de #326 (herramienta de ventana)")
    p.add_argument("--mode", choices=("seed", "synthetic", "search", "register"), required=True)
    p.add_argument("--db-url", default=os.environ.get("DATABASE_URL", ""))
    p.add_argument("--library", default=os.environ.get("LIBRARY_PATH", "/media/library"))
    p.add_argument("--library-kind", choices=("synthetic", "real"), required=True)
    p.add_argument("--max-files", type=int, default=100)
    p.add_argument("--max-bytes", default="15GiB")
    p.add_argument("--seed", type=int, default=326)
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--verify-sha-samples", type=int, default=10)
    p.add_argument("--expected-new", type=int, default=1220)
    p.add_argument("--expected-old", type=int, default=100)
    p.add_argument("--require-readonly", action="store_true")
    p.add_argument("--debug", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    _configurar_logs()
    salida = sys.stdout
    try:
        with contextlib.redirect_stdout(sys.stderr):
            resultado = asyncio.run(_ejecutar(args))
    except Exception as exc:  # noqa: BLE001 — la salida debe ser JSON saneado
        if args.debug:
            import traceback
            traceback.print_exc()
        resultado = {
            "schema": SCHEMA, "status": "error", "mode": args.mode,
            "error": type(exc).__name__,
            "message": str(exc) if isinstance(exc, ErrorDeMedicion) else "fallo de la medición",
        }
        print(json.dumps(resultado, ensure_ascii=False, indent=2), file=salida)
        return 1
    print(json.dumps(resultado, ensure_ascii=False, indent=2), file=salida)
    _resumen_modo(args.mode, resultado.get("checks", {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
