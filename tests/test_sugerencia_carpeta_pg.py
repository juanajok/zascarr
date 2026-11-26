# ruff: noqa: E501, F811
"""BL-PARSE3 C6: semántica real de los hermanos de carpeta, sobre Postgres.

La carpeta es la ruta completa (dos «Vol 1» de series distintas no se mezclan); los archivos
ausentes y los pendientes no cuentan como hermanos. Se salta sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import itertools
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from tests.test_vinculacion_previa_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    archivos,
    entorno,
    serie_de_prueba,
    url_bd,
)
from zascarr.models import File, Issue, IssueFormat
from zascarr.services.sugerencia_carpeta import sugerencias_por_carpeta

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]


_NUMEROS = itertools.count(1)


async def _vincular(entorno, sid, ids: dict, **campos) -> None:
    async with entorno.banco.fabrica() as s:
        for fid in ids.values():
            iid = uuid4()
            s.add(Issue(id=iid, series_id=sid, issue_number=str(next(_NUMEROS)),
                        format=IssueFormat.SINGLE_ISSUE))
            await s.flush()
            await s.execute(update(File).where(File.id == fid).values(issue_id=iid, **campos))
        await s.commit()


async def test_hermanos_semantica_real(entorno):
    flash = await serie_de_prueba(entorno, "Flash", 1987)
    batman = await serie_de_prueba(entorno, "Batman", 1940)
    # Comics/Flash/Vol 1: 3 hermanos en Flash, uno ausente en Batman (no cuenta) y dos pendientes.
    await _vincular(entorno, flash, await archivos(
        entorno, "Flash 1.cbz", "Flash 2.cbz", "Flash 3.cbz", carpeta="Comics/Flash/Vol 1", en_disco=False))
    await _vincular(entorno, batman, await archivos(
        entorno, "Batman 9.cbz", carpeta="Comics/Flash/Vol 1", en_disco=False), is_missing=True)
    pend_flash = await archivos(entorno, "Flash 4.cbz", "Flash 5.cbz",
                                carpeta="Comics/Flash/Vol 1", en_disco=False)
    # Comics/Batman/Vol 1: misma última carpeta, otra ruta; solo 2 hermanos → nada.
    await _vincular(entorno, batman, await archivos(
        entorno, "Batman 1.cbz", "Batman 2.cbz", carpeta="Comics/Batman/Vol 1", en_disco=False))
    pend_batman = await archivos(entorno, "Batman 3.cbz", carpeta="Comics/Batman/Vol 1", en_disco=False)

    async with entorno.banco.fabrica() as s:
        ids = [*pend_flash.values(), *pend_batman.values()]
        pagina = (await s.execute(select(File).where(File.id.in_(ids)))).scalars().all()
        sug = await sugerencias_por_carpeta(s, list(pagina))

    for fid in pend_flash.values():
        assert sug[fid].series_id == flash
        assert sug[fid].hermanos == 3          # ni el ausente ni el otro pendiente cuentan
    assert next(iter(pend_batman.values())) not in sug
