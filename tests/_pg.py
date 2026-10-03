"""Ciclo de vida de la base de datos de pruebas (Postgres real). Solo para tests.

Contrato, que antes no estaba escrito y dos pruebas contradecían:

- La BD que apunta `TEST_DATABASE_URL` se **migra a `head` una vez por sesión** (`conftest.py`); las
  pruebas de Postgres dan por hecho ese esquema y ninguna lo deja a medias.
- Una prueba que necesita OTRO estado (p. ej. «sin migrar») **no usa esa BD**: crea la suya con
  `bd_efimera()`, que se borra al terminar.
- Todo lo que cree o migre una BD se niega a tocar una cuyo nombre no lleve «test».

Ver también `tests/test_pg_ciclo_de_vida.py`.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

RAIZ = Path(__file__).resolve().parents[1]


def url_asyncpg(url: str) -> str:
    """Acepta `postgresql://` y `postgresql+asyncpg://` (la suite documenta la plana)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def exigir_nombre_de_prueba(url: str) -> str:
    """Se niega a seguir si la base señalada no parece de pruebas (defensa en profundidad)."""
    nombre = make_url(url).database or ""
    if "test" not in nombre.lower():
        raise RuntimeError(
            f"La BD «{nombre}» no lleva 'test' en el nombre: las pruebas se niegan a crearla, "
            "migrarla o borrarla. Apunta TEST_DATABASE_URL a una base de pruebas."
        )
    return nombre


def entorno_para_alembic(base: Mapping[str, str], url: str) -> dict[str, str]:
    """Entorno de un subproceso `python -m alembic` sobre la BD `url`.

    `PYTHONSAFEPATH=1` evita que el directorio `alembic/` de la raíz sombree el paquete instalado
    **solo si la raíz no llega por otro camino**: con la raíz del repo en `PYTHONPATH` (algo normal
    al lanzar `pytest` a mano para que `import tests` funcione) el subproceso hereda esa entrada y
    falla con «No module named alembic.__main__; 'alembic' is a package and cannot be directly
    executed». Se quita la raíz de `PYTHONPATH` y se conserva el resto (p. ej. `src/`).
    """
    entorno = dict(base)
    entorno["DATABASE_URL"] = url_asyncpg(url)
    entorno["PYTHONSAFEPATH"] = "1"
    restantes = [
        p for p in entorno.get("PYTHONPATH", "").split(os.pathsep)
        if p and Path(p).resolve() != RAIZ
    ]
    if restantes:
        entorno["PYTHONPATH"] = os.pathsep.join(restantes)
    else:
        entorno.pop("PYTHONPATH", None)
    return entorno


def alembic(url: str, *args: str, estricto: bool = True) -> subprocess.CompletedProcess:
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=RAIZ, env=entorno_para_alembic(os.environ, url),
        capture_output=True, text=True, timeout=180,
    )
    if estricto:
        assert resultado.returncode == 0, resultado.stderr[-2000:]
    return resultado


def migrar_a_head(url: str) -> None:
    exigir_nombre_de_prueba(url)
    alembic(url, "upgrade", "head")


async def _crear_efimera(url_base: str) -> tuple[str, str]:
    exigir_nombre_de_prueba(url_base)
    nombre = f"zascarr_test_efimera_{uuid4().hex[:12]}"
    destino = make_url(url_base).set(database=nombre).render_as_string(hide_password=False)
    admin = create_async_engine(url_asyncpg(url_base), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conexion:
            await conexion.execute(text(f'CREATE DATABASE "{nombre}"'))
    finally:
        await admin.dispose()
    return destino, nombre


async def _borrar_efimera(url_base: str, nombre: str) -> None:
    admin = create_async_engine(url_asyncpg(url_base), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conexion:
            await conexion.execute(text(f'DROP DATABASE IF EXISTS "{nombre}" WITH (FORCE)'))
    finally:
        await admin.dispose()


@asynccontextmanager
async def bd_efimera(url_base: str) -> AsyncIterator[str]:
    """Una base de datos NUEVA y vacía (sin migrar) en el mismo servidor; se borra al salir.

    Devuelve su URL. Necesita permiso de `CREATE DATABASE` (el usuario de los contenedores de
    pruebas y el del servicio de CI lo tienen).
    """
    destino, nombre = await _crear_efimera(url_base)
    try:
        yield destino
    finally:
        await _borrar_efimera(url_base, nombre)


@contextmanager
def bd_efimera_sync(url_base: str) -> Iterator[str]:
    """Lo mismo para fixtures SÍNCRONAS de alcance de módulo (crear y borrar en bucles distintos:
    un `asynccontextmanager` abierto con `asyncio.run` se cerraría, y borraría la BD, al acabar
    ese bucle)."""
    destino, nombre = asyncio.run(_crear_efimera(url_base))
    try:
        yield destino
    finally:
        asyncio.run(_borrar_efimera(url_base, nombre))
