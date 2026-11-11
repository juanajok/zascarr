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
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.core.importer_triage import TriageResult
from zascarr.core.matcher import MatchStatus, SeriesHit, SeriesMatcher

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


_CREATE_TEMP_FILES = (
    "CREATE TEMP TABLE files (id uuid PRIMARY KEY, issue_id uuid, file_name varchar)"
)
_INSERT_FILE = "INSERT INTO files (id, issue_id, file_name) VALUES (:id, :iid, :name)"


@pytest.mark.asyncio
async def test_no_enlaza_a_un_numero_con_archivos_de_otra_coleccion():
    """BL-INF11: «Superman - Godfall #01» no se cuelga del #1 que ya tiene «Superman #01»."""
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text(_CREATE_TEMP_ISSUES))
            await session.execute(text(_CREATE_TEMP_FILES))
            sid, iid = uuid4(), uuid4()
            await session.execute(text(_INSERT_ISSUE),
                                  {"id": str(iid), "sid": str(sid), "num": "1",
                                   "fmt": "single_issue"})
            await session.execute(text(_INSERT_FILE),
                                  {"id": str(uuid4()), "iid": str(iid),
                                   "name": "Superman #01.cbz"})
            matcher = SeriesMatcher(session)

            async def _find_series(*_a, **_k):
                return [SeriesHit(sid, "Superman", None, 1.0)]

            matcher.find_series = _find_series
            matcher.find_alias = AsyncMock(return_value=None)

            triage = TriageResult(path=Path("Superman - Godfall #01.cbr"))
            r = await matcher.decide(triage, extractor=lambda _n: ("Superman", "1", None))
            assert r.status is MatchStatus.UNSORTED
            assert any("otro título" in nota for nota in r.notes)
            assert r.issue_id is None

            # CBR/CBZ o copia del mismo título: sí puede compartir el número.
            copia = TriageResult(path=Path("Superman #01 (copia).cbz"))
            r2 = await matcher.decide(copia, extractor=lambda _n: ("Superman", "1", None))
            assert r2.issue_id == iid
    finally:
        await engine.dispose()


_CREATE_TEMP_SERIES = (
    "CREATE TEMP TABLE series ("
    "id uuid PRIMARY KEY, title varchar(500), start_year smallint, "
    "title_norm varchar(500), sort_title varchar(500))"
)
_INSERT_SERIES = (
    "INSERT INTO series (id, title, start_year, title_norm, sort_title) "
    "VALUES (:id, :title, :year, :norm, NULL)"
)


@pytest.mark.asyncio
async def test_find_series_equipara_titulo_sin_volumen_con_volumen_de_catalogo():
    """Bug real de la biblioteca (2026-11-11): «Batman #25» no enlazaba.

    El parser extrae «Batman»; el catálogo tiene «Batman Vol 1». La similitud
    (0,54) no llegaba al umbral fuzzy (0,60), así que un número que existía
    se quedaba en Pendientes. «Vol 1» es un sufijo de edición, no parte del
    nombre de la obra: la coincidencia debe ser exacta.
    """
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text(_CREATE_TEMP_SERIES))
            vol1, vol2 = uuid4(), uuid4()
            await session.execute(text(_INSERT_SERIES), {
                "id": str(vol1), "title": "Batman Vol 1",
                "year": 1940, "norm": "batman vol 1"})
            await session.execute(text(_INSERT_SERIES), {
                "id": str(vol2), "title": "Batman Vol 2",
                "year": 2011, "norm": "batman vol 2"})
            matcher = SeriesMatcher(session)

            con_anio = await matcher.find_series("Batman", year=1940)
            assert len(con_anio) == 1
            assert con_anio[0].series_id == vol1
            assert con_anio[0].score == 1.0

            sin_anio = await matcher.find_series("Batman")
            assert {h.series_id for h in sin_anio} == {vol1, vol2}
            assert all(h.score == 1.0 for h in sin_anio)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_no_anade_copias_a_un_numero_ya_contaminado():
    """Si el Issue ya mezcla varias colecciones, una copia de una de ellas
    tampoco entra: primero hay que separar el Issue. Caso real: «Flashpoint
    #2» con diez tie-ins distintos, que si no se siguen acumulando."""
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text(_CREATE_TEMP_ISSUES))
            await session.execute(text(_CREATE_TEMP_FILES))
            sid, iid = uuid4(), uuid4()
            await session.execute(text(_INSERT_ISSUE),
                                  {"id": str(iid), "sid": str(sid), "num": "2",
                                   "fmt": "single_issue"})
            for nombre in ("Flashpoint #02.cbz",
                           "Flashpoint - Deadman and the Flying Graysons #2.cbz"):
                await session.execute(text(_INSERT_FILE),
                                      {"id": str(uuid4()), "iid": str(iid),
                                       "name": nombre})
            matcher = SeriesMatcher(session)

            async def _find_series(*_a, **_k):
                return [SeriesHit(sid, "Flashpoint", None, 1.0)]

            matcher.find_series = _find_series
            matcher.find_alias = AsyncMock(return_value=None)
            copia = TriageResult(path=Path(
                "Flashpoint - Deadman and the Flying Graysons #2 (otra copia).cbz"))
            r = await matcher.decide(
                copia, extractor=lambda _n: ("Flashpoint", "2", None))
            assert r.status is MatchStatus.UNSORTED
            assert r.issue_id is None
            assert any("mezcla varias colecciones" in n for n in r.notes)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_alias_de_catalogo_solo_mismo_espacio_de_numeracion():
    """Un alias traduce el título, no cambia la serie ni el número."""
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            await session.execute(text(_CREATE_TEMP_SERIES))
            sid1, sid2 = uuid4(), uuid4()
            await session.execute(text(_INSERT_SERIES), {
                "id": str(sid1), "title": "100 Bullets", "year": 1999,
                "norm": "100 bullets"})
            await session.execute(text(_INSERT_SERIES), {
                "id": str(sid2), "title": "Batman: Shadow of the Bat", "year": 1992,
                "norm": "batman shadow of the bat"})
            matcher = SeriesMatcher(session)
            hit = await matcher.find_series("100 Balas")
            assert len(hit) == 1 and hit[0].series_id == sid1
            assert hit[0].score == 1.0
            hit = await matcher.find_series("Shadow of the Bat")
            assert len(hit) == 1 and hit[0].series_id == sid2
            assert hit[0].score == 1.0
    finally:
        await engine.dispose()
