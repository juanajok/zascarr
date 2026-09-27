"""Regresión del SQL crudo de `SeriesMatcher.find_issue` contra Postgres real.

El matcher consulta `issues` con SQL a mano (no ORM), así que los tests con
dobles no pueden cubrir su semántica — aquí se ejercita la consulta de verdad.

Motivo concreto (B15, 2026-09-27): la normalización de ceros era ASIMÉTRICA
(`ltrim(issue_number, '0') = :num`, con el parámetro ya recortado en Python) y
`ltrim('0','0')` es la cadena VACÍA, así que el issue **#0 no encontraba nunca
su fila** (`'' = '0'`). Se corrigió recortando los dos lados y excluyendo la
fila sin número (que si no casaría con cualquier búsqueda de `'0'`).

Se salta automáticamente si TEST_DATABASE_URL no está definida:

    docker run --rm -d --name zascarr_test_pg -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=zascarr -p 15433:5432 postgres:15-alpine
    TEST_DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:15433/zascarr \\
        pytest tests/test_matcher_sql_pg.py
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.core.matcher import SeriesMatcher

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

# Tabla TEMP con el nombre real: sombrea a `issues` para ESA sesión, así el SQL
# del matcher (que no va cualificado) la usa tal cual, sin tocar el esquema real.
_CREATE_TEMP_ISSUES = (
    "CREATE TEMP TABLE issues ("
    "id uuid PRIMARY KEY, series_id uuid, "
    "issue_number varchar(20), format varchar(30))"
)
_INSERT_ISSUE = (
    "INSERT INTO issues (id, series_id, issue_number, format) "
    "VALUES (:id, :sid, :num, :fmt)"
)


def _url_asyncpg(url: str) -> str:
    """Acepta `postgresql://` y `postgresql+asyncpg://` (el resto de la suite
    documenta la URL en formato plano, sin driver)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


# (número almacenado, format almacenado, número buscado, formato esperado, ¿debe encontrarlo?)
CASOS = [
    ("0",   "single_issue", "0",   None,           True),   # el bug del #0
    ("000", "single_issue", "0",   None,           True),   # el mismo número con ceros
    ("007", "omnibus",      "7",   "omnibus",      True),   # ceros a la izquierda
    ("7",   "single_issue", "007", "single_issue", True),   # y al revés
    ("1.5", "single_issue", "1.5", "single_issue", True),   # decimales (por esto es VARCHAR)
    ("12",  "single_issue", "12",  "omnibus",      False),  # formato distinto → no enlaza
    ("12",  "omnibus",      "12",  None,           False),  # sin marcador: única fila ómnibus
    ("",    "single_issue", "0",   None,           False),  # fila sin número: no casa con '0'
]


@pytest.mark.asyncio
async def test_find_issue_semantica_real():
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text(_CREATE_TEMP_ISSUES))
            matcher = SeriesMatcher(session)

            for almacenado, fmt, buscado, esperado, debe in CASOS:
                sid = uuid4()  # una serie por caso: los casos no se estorban
                await session.execute(text(_INSERT_ISSUE),
                                      {"id": str(uuid4()), "sid": str(sid),
                                       "num": almacenado, "fmt": fmt})

                issue_id, conflicto = await matcher.find_issue(sid, buscado, esperado)
                etiqueta = f"{almacenado!r}({fmt}) buscando {buscado!r} con {esperado!r}"
                if debe:
                    assert issue_id is not None, f"no encontró {etiqueta}"
                    assert conflicto is False, f"marcó conflicto de más en {etiqueta}"
                else:
                    assert issue_id is None, f"encontró de más en {etiqueta}"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_find_issue_ambiguedad_real():
    """Dos ediciones del MISMO número (grapa y ómnibus): 'Omnigold 12' elige el
    ómnibus; 'Batman 12' sin marcador no elige a ciegas."""
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text(_CREATE_TEMP_ISSUES))
            sid, grapa, omnibus = uuid4(), uuid4(), uuid4()
            for iid, fmt in ((grapa, "single_issue"), (omnibus, "omnibus")):
                await session.execute(text(_INSERT_ISSUE),
                                      {"id": str(iid), "sid": str(sid),
                                       "num": "12", "fmt": fmt})
            matcher = SeriesMatcher(session)

            # El marcador explícito sí es evidencia: se enlaza el ómnibus.
            assert await matcher.find_issue(sid, "12", "omnibus") == (omnibus, False)
            # Sin marcador hay dos candidatas y nada que las separe → a revisión.
            assert await matcher.find_issue(sid, "12", None) == (None, True)
    finally:
        await engine.dispose()
