# ruff: noqa: E501
"""#448 BL-INF2 sobre PostgreSQL real: huecos, manual, locked, créditos e idempotencia."""
from __future__ import annotations

import os
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import (
    ComicTradition,
    Creator,
    File,
    FileFormat,
    Issue,
    IssueCreator,
    Publisher,
    Series,
)
from zascarr.services.comicinfo import aplicar_a_issue

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

XML = """<?xml version="1.0"?><ComicInfo>
<Writer>Ana</Writer><Penciller>Bea</Penciller><Editor>Eva</Editor><Translator>Tina</Translator>
<Summary>Una historia</Summary><PageCount>32</PageCount><Publisher>Norma</Publisher>
</ComicInfo>"""


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd, tmp_path):
    banco = Banco(url_bd)
    await banco.limpiar()
    yield SimpleNamespace(banco=banco, tmp=tmp_path)
    await banco.cerrar()


async def _fila(entorno, xml=XML):
    sid, iid = uuid4(), uuid4()
    ruta = entorno.tmp / "Thorgal 3.cbz"
    with zipfile.ZipFile(ruta, "w") as zf:
        zf.writestr("ComicInfo.xml", xml)
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN))
        await s.flush()
        s.add(Issue(id=iid, series_id=sid, issue_number="3"))
        await s.flush()
        s.add(File(issue_id=iid, file_path=str(ruta), file_name=ruta.name,
                   file_format=FileFormat.CBZ, file_size_bytes=ruta.stat().st_size))
        await s.commit()
    return sid, iid, ruta


@pytest.mark.asyncio
async def test_aplica_huecos_publisher_y_creditos_pg(entorno):
    sid, iid, ruta = await _fila(entorno)
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        r = await aplicar_a_issue(s, issue, ruta)
        await s.commit()
        assert r.estado == "aplicado" and r.campos == 2 and r.autores == 4
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        assert issue.synopsis == "Una historia" and issue.page_count == 32
        assert issue.metadata_source == "comicinfo_xml"
        creds = (await s.execute(select(IssueCreator).where(IssueCreator.issue_id == iid))).scalars().all()
        assert {c.role.value for c in creds} == {"writer", "penciler", "editor", "translator"}
        assert len({c.creator_id for c in creds}) == 4
        serie = await s.get(Series, sid)
        assert serie.publisher_id is not None
        assert (await s.get(Publisher, serie.publisher_id)).name == "Norma"


@pytest.mark.asyncio
async def test_repetir_no_duplica_y_creators_reutilizados_pg(entorno):
    _, iid, ruta = await _fila(entorno, XML.replace("Ana", "Ana, Ana"))
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        await aplicar_a_issue(s, issue, ruta)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        r2 = await aplicar_a_issue(s, issue, ruta)
        await s.commit()
        assert r2.estado == "sin_cambios"
        creadores = (await s.execute(select(Creator).where(Creator.name.in_(["Ana"])))).scalars().all()
        assert len(creadores) == 1
        creds = (await s.execute(select(IssueCreator).where(
            IssueCreator.issue_id == iid, IssueCreator.role == "writer"))).scalars().all()
        assert len(creds) == 1


@pytest.mark.asyncio
async def test_manual_y_locked_no_se_pisan_pg(entorno):
    _, iid, ruta = await _fila(entorno)
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        issue.metadata_source = "manual"
        issue.synopsis = "Lo escribió la persona"
        issue.locked_fields = ["synopsis"]
        await s.commit()
        r = await aplicar_a_issue(s, issue, ruta)
        assert r.estado == "sin_cambios"
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        assert issue.synopsis == "Lo escribió la persona"
        assert issue.page_count is None


@pytest.mark.asyncio
async def test_accion_explicita_aplica_a_vinculado_a_mano_e_idempotente_pg(entorno):
    _, iid, _ = await _fila(entorno)
    from zascarr.services.comicinfo import leer_archivos_vinculados
    async with entorno.banco.fabrica() as s:
        r1 = await leer_archivos_vinculados(s)
        assert r1.aplicados == 1 and r1.ilegibles == 0
    async with entorno.banco.fabrica() as s:
        r2 = await leer_archivos_vinculados(s)
        assert r2.aplicados == 0 and r2.omitidos == 1
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        assert issue.synopsis == "Una historia" and issue.page_count == 32
        assert len((await s.execute(select(IssueCreator).where(
            IssueCreator.issue_id == iid))).scalars().all()) == 4


@pytest.mark.asyncio
async def test_page_count_solo_con_un_archivo_y_rango_pg(entorno):
    sid, iid, ruta = await _fila(entorno)
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        await aplicar_a_issue(s, issue, ruta)
        await s.commit()
        assert issue.page_count == 32 and issue.metadata_source == "comicinfo_xml"
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        issue.page_count = 32
        issue.metadata_source = "comicinfo_xml"
        s.add(File(issue_id=iid, file_path="/tmp/otro.cbz", file_name="otro.cbz",
                   file_format=FileFormat.CBZ, file_size_bytes=1))
        await s.commit()
        r = await aplicar_a_issue(s, issue, ruta)
        await s.commit()
        assert r.estado == "sin_cambios" and issue.page_count == 32
    grande = entorno.tmp / "grande.cbz"
    with zipfile.ZipFile(grande, "w") as zf:
        zf.writestr("ComicInfo.xml", "<ComicInfo><PageCount>999999</PageCount></ComicInfo>")
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        r = await aplicar_a_issue(s, issue, grande)
        assert issue.page_count == 32 and r.campos == 0


@pytest.mark.asyncio
async def test_marca_persiste_en_sesion_nueva_y_fuente_solo_paginas_pg(entorno):
    _, iid, ruta = await _fila(entorno)
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        issue.synopsis = None
        issue.page_count = None
        await s.commit()
        await aplicar_a_issue(s, issue, ruta)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        assert isinstance(issue.metadata_.get("comicinfo_aplicado"), dict)
        assert issue.metadata_source == "comicinfo_xml"


@pytest.mark.asyncio
async def test_creditos_respetan_locked_fields_pg(entorno):
    _, iid, ruta = await _fila(entorno)
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        issue.locked_fields = ["credits"]
        await s.commit()
        await aplicar_a_issue(s, issue, ruta)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(IssueCreator).where(
            IssueCreator.issue_id == iid))).scalars().all() == []


@pytest.mark.asyncio
async def test_nombres_con_articulo_no_se_confunden_pg(entorno):
    from zascarr.services.comicinfo import normalizar_nombre_autor
    assert normalizar_nombre_autor("The  Beatles") == "the beatles"
    assert normalizar_nombre_autor("Beatles") == "beatles"
    iid, ruta = (await _fila(entorno, "<ComicInfo><Writer>The Beatles</Writer></ComicInfo>"))[1:]
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        await aplicar_a_issue(s, issue, ruta)
        await s.commit()
        norm = (await s.execute(select(Creator.name_norm).where(
            Creator.name == "The Beatles"))).scalar_one()
        assert norm == "the beatles"


@pytest.mark.asyncio
async def test_accion_55_archivos_pagina_y_sigue_pg(entorno):
    from zascarr.services.comicinfo import leer_archivos_vinculados
    sid, iid, _ = await _fila(entorno)
    async with entorno.banco.fabrica() as s:
        for n in range(55):
            s.add(File(issue_id=iid, file_path=f"/tmp/f{n}.cbz", file_name=f"f{n}.cbz",
                       file_format=FileFormat.CBZ, file_size_bytes=1))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        r = await leer_archivos_vinculados(s)
        assert r.total == 56 and r.siguiente == 50
    async with entorno.banco.fabrica() as s:
        r2 = await leer_archivos_vinculados(s, offset=50)
        assert r2.total == 56 and r2.siguiente is None


@pytest.mark.asyncio
async def test_paginas_32_a_50_y_999999_pg(entorno):
    _, iid, ruta = await _fila(entorno)
    otra = entorno.tmp / "p50.cbz"
    with zipfile.ZipFile(otra, "w") as zf:
        zf.writestr("ComicInfo.xml", "<ComicInfo><PageCount>50</PageCount></ComicInfo>")
    enorme = entorno.tmp / "p999999.cbz"
    with zipfile.ZipFile(enorme, "w") as zf:
        zf.writestr("ComicInfo.xml", "<ComicInfo><PageCount>999999</PageCount></ComicInfo>")
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        issue.page_count = 32
        issue.metadata_source = "comicinfo_xml"
        await s.commit()
        await aplicar_a_issue(s, issue, otra)
        assert issue.page_count == 50
        await aplicar_a_issue(s, issue, enorme)
        assert issue.page_count == 50
