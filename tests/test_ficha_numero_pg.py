# ruff: noqa: E501
"""#447 sobre PostgreSQL real: agregado de autores, orden de números y consultas fijas."""
from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import (
    ComicTradition,
    Creator,
    CreatorRole,
    File,
    FileFormat,
    Issue,
    IssueCreator,
    Series,
)
from zascarr.services.ficha_numero import cargar_ficha_numero, cargar_ficha_serie

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd):
    banco = Banco(url_bd)
    await banco.limpiar()
    yield SimpleNamespace(banco=banco)
    await banco.cerrar()


async def _sembrar(entorno):
    sid = uuid4()
    issues = []
    async with entorno.banco.fabrica() as s:
        serie = Series(id=sid, title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                       description="<p>Una serie de aventuras.</p>", start_year=1977,
                       end_year=2000)
        s.add(serie)
        autores = {}
        for nombre, _rol in (("Ana", CreatorRole.WRITER), ("Bea", CreatorRole.WRITER),
                            ("Carla", CreatorRole.WRITER), ("Dani", CreatorRole.WRITER),
                            ("Eva", CreatorRole.PENCILER)):
            c = Creator(id=uuid4(), name=nombre)
            s.add(c)
            autores[nombre] = c
        for numero in ("1", "2", "10"):
            i = Issue(id=uuid4(), series_id=sid, issue_number=numero, title=f"Número {numero}",
                      release_date=date(1981, 1, 1), page_count=48,
                      synopsis="<p>Sinopsis</p>")
            s.add(i)
            issues.append(i)
        await s.flush()
        for i in issues:
            for nombre in ("Ana", "Bea", "Carla"):
                s.add(IssueCreator(issue_id=i.id, creator_id=autores[nombre].id,
                                   role=CreatorRole.WRITER))
            s.add(IssueCreator(issue_id=i.id, creator_id=autores["Eva"].id,
                               role=CreatorRole.PENCILER))
        f = File(id=uuid4(), issue_id=issues[0].id, file_path="/tmp/thorgal01.cbz",
                 file_name="Thorgal 01.cbz", file_format=FileFormat.CBZ,
                 file_size_bytes=1024)
        s.add(f)
        await s.commit()
    return sid, issues[0].id, issues[1].id


@pytest.mark.asyncio
async def test_autores_principales_y_orden_natural_pg(entorno):
    sid, _, _ = await _sembrar(entorno)
    async with entorno.banco.fabrica() as s:
        antes = len(entorno.banco.sentencias)
        ficha = await cargar_ficha_serie(s, sid)
        despues = len(entorno.banco.sentencias)
    assert ficha is not None
    assert ficha.sinopsis == "Una serie de aventuras."
    assert [a.nombre for a in ficha.autores["writer"]] == ["Ana", "Bea", "Carla"]
    assert [n.numero for n in ficha.numeros] == ["1", "2", "10"]
    assert ficha.numeros_por_id["1"].tiene_archivos is True
    assert despues - antes <= 5


@pytest.mark.asyncio
async def test_ficha_numero_con_autores_archivos_pg(entorno):
    sid, iid, _ = await _sembrar(entorno)
    async with entorno.banco.fabrica() as s:
        ficha = await cargar_ficha_numero(s, sid, iid)
    assert ficha is not None
    assert ficha.autores["writer"] == ["Ana", "Bea", "Carla"]
    assert ficha.archivos and ficha.archivos[0].nombre == "Thorgal 01.cbz"
    assert ficha.sinopsis == "Sinopsis"


@pytest.mark.asyncio
async def test_corte_top3_y_archivos_orden_natural_pg(entorno):
    sid, iid, _ = await _sembrar(entorno)
    async with entorno.banco.fabrica() as s:
        from sqlalchemy import select

        from zascarr.models import Creator, Issue, IssueCreator
        extra = Creator(id=uuid4(), name="Zoe")
        s.add(extra)
        await s.flush()
        first = (await s.execute(select(Issue).where(Issue.series_id == sid, Issue.issue_number == "1"))).scalar_one()
        s.add(IssueCreator(issue_id=first.id, creator_id=extra.id, role=CreatorRole.WRITER))
        for nombre in ("10.cbz", "2.cbz"):
            s.add(File(id=uuid4(), issue_id=first.id, file_path=f"/tmp/{nombre}",
                       file_name=nombre, file_format=FileFormat.CBZ, file_size_bytes=1))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        ficha = await cargar_ficha_serie(s, sid)
        numero = await cargar_ficha_numero(s, sid, first.id)
    assert "Zoe" not in [a.nombre for a in ficha.autores["writer"]]
    assert [a.nombre for a in numero.archivos] == ["2.cbz", "10.cbz", "Thorgal 01.cbz"]
