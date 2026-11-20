# ruff: noqa: E501
"""L1/F4a (#1186) sobre Postgres real: limpiar sinopsis con HTML, con original y sin tocar lo protegido.

Se salta sin `TEST_DATABASE_URL`. La base es efímera y migrada a `head`; no toca
la biblioteca ni la Pi."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import Issue, MetadataSource, Series
from zascarr.services.limpiar_sinopsis import LimpiadorSinopsis

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

HTML = "<p>Hola &amp; adiós</p>"
LIMPIO = "Hola & adiós"


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def fabrica(url_bd):
    engine = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def ids(fabrica):
    async with fabrica() as s:
        # Cada prueba parte de cero: el `ids` es function-scoped.
        await s.execute(text("TRUNCATE issues, series RESTART IDENTITY CASCADE"))
        serie = Series(id=uuid4(), title="Serie de prueba")
        s.add(serie)
        await s.flush()
        datos = {
            "html": (HTML, {"otra": "clave"}, None, []),
            "locked": ("<p>No</p>", {}, None, ["synopsis"]),
            "manual": ("<p>Manual</p>", {}, MetadataSource.MANUAL.value, []),
            "limpia": (LIMPIO, {}, None, []),
            "original": ("<p>Otra</p>", {"sinopsis_original": "<p>Antes</p>"}, None, []),
            "html2": ("<p>Segunda &amp; más</p>", {}, None, []),
        }
        ids = {}
        for clave, (sinopsis, meta, fuente, locks) in datos.items():
            issue = Issue(
                id=uuid4(), series_id=serie.id, issue_number=clave,
                synopsis=sinopsis, metadata_=meta, metadata_source=fuente,
                locked_fields=locks,
            )
            s.add(issue)
            ids[clave] = issue.id
        await s.commit()
        return ids


async def _leer(fabrica, issue_id):
    async with fabrica() as s:
        return (await s.execute(
            select(Issue.synopsis, Issue.metadata_, Issue.locked_fields, Issue.metadata_source)
            .where(Issue.id == issue_id)
        )).one()


async def _previsualizar(fabrica, **kw):
    async with fabrica() as s:
        return await LimpiadorSinopsis(s).previsualizar(**kw)


async def _aplicar(fabrica, **kw):
    async with fabrica() as s:
        r = await LimpiadorSinopsis(s).aplicar(**kw)
        await s.commit()
        return r


@pytest.mark.asyncio
async def test_vista_previa_no_escribe_y_cuenta_protegidas(fabrica, ids):
    antes = await _leer(fabrica, ids["html"])
    vista = await _previsualizar(fabrica, limite=20)
    assert vista.pendientes == 3          # html, original y html2
    assert vista.protegidas == 1
    assert vista.manuales == 1
    assert len(vista.muestra) == 3
    assert all("<" not in m.despues for m in vista.muestra)
    despues = await _leer(fabrica, ids["html"])
    assert despues == antes               # la vista previa no escribe


@pytest.mark.asyncio
async def test_aplica_con_original_y_sin_tocar_protegidas(fabrica, ids):
    r = await _aplicar(fabrica, limite=100)
    assert (r.pendientes_antes, r.limpiadas, r.pendientes_despues) == (3, 3, 0)

    synopsis, meta, _locks, _fuente = await _leer(fabrica, ids["html"])
    assert synopsis == LIMPIO
    assert meta["otra"] == "clave"
    assert meta["sinopsis_original"] == HTML

    synopsis, meta, _locks, _fuente = await _leer(fabrica, ids["original"])
    assert synopsis == "Otra"
    assert meta["sinopsis_original"] == "<p>Antes</p>"   # no se pisa el original

    synopsis, meta, _locks, _fuente = await _leer(fabrica, ids["html2"])
    assert synopsis == "Segunda & más"
    assert meta["sinopsis_original"] == "<p>Segunda &amp; más</p>"

    # Protegidas: no cambian.
    for clave in ("locked", "manual", "limpia"):
        synopsis, _meta, _locks, _fuente = await _leer(fabrica, ids[clave])
        assert synopsis in ("<p>No</p>", "<p>Manual</p>", LIMPIO)

    # Idempotente: una segunda pasada no limpia nada.
    segunda = await _aplicar(fabrica, limite=100)
    assert (segunda.pendientes_antes, segunda.limpiadas, segunda.pendientes_despues) == (0, 0, 0)


@pytest.mark.asyncio
async def test_limite_acota_el_lote(fabrica, ids):
    r = await _aplicar(fabrica, limite=2)
    assert r.limpiadas == 2
    assert r.pendientes_despues == 1
