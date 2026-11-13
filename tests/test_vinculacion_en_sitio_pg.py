"""#720: vincular en su sitio no mueve, no renombra y exige que el Issue ya exista."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.test_revision_carpetas_pg import Banco
from tests.test_vinculacion_previa_pg import url_bd  # noqa: F401  (fixture compartida)
from zascarr.models import ComicTradition, File, FileFormat, Issue, IssueFormat, Series
from zascarr.services import vinculacion_en_sitio
from zascarr.services.vinculacion_en_sitio import vincular_en_sitio

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]


@pytest.fixture
async def banco(url_bd, monkeypatch, tmp_path):
    b = Banco(url_bd)
    await b.limpiar()
    lib = tmp_path / "biblioteca"
    (lib / "Comics" / "Flash").mkdir(parents=True)
    monkeypatch.setattr(vinculacion_en_sitio, "get_settings",
                        lambda: SimpleNamespace(library_path=lib))
    sid = uuid4()
    async with b.fabrica() as s:
        s.add(Series(id=sid, title="Flash", tradition=ComicTradition.AMERICAN))
        s.add(Issue(id=uuid4(), series_id=sid, issue_number="1", format=IssueFormat.SINGLE_ISSUE))
        await s.commit()
    yield SimpleNamespace(banco=b, lib=lib, sid=sid)
    await b.cerrar()


async def test_vincular_en_sitio_enlaza_sin_tocar_el_archivo(banco):
    ruta = banco.lib / "Comics" / "Flash" / "Flash 01.cbz"
    ruta.write_bytes(b"contenido")
    fid = uuid4()
    async with banco.banco.fabrica() as s:
        s.add(File(id=fid, file_path=str(ruta), file_name=ruta.name,
                   file_format=FileFormat.CBZ, metadata_={"match_status": "direct"}))
        await s.commit()

    async with banco.banco.fabrica() as s:
        resultado = await vincular_en_sitio(s, fid, banco.sid, "1")
        await s.commit()
        assert resultado.estado == "vinculado"
        f = await s.get(File, fid)
        assert f is not None and f.issue_id is not None
        assert f.file_path == str(ruta) and ruta.exists()

    assert ruta.read_bytes() == b"contenido"


async def test_vincular_en_sitio_rechaza_packs(banco):
    ruta = banco.lib / "Comics" / "Flash" / "Flash 144-158.cbz"
    ruta.write_bytes(b"x")
    fid = uuid4()
    async with banco.banco.fabrica() as s:
        s.add(File(id=fid, file_path=str(ruta), file_name=ruta.name,
                   file_format=FileFormat.CBZ, metadata_={"match_status": "direct"}))
        await s.commit()
    async with banco.banco.fabrica() as s:
        r = await vincular_en_sitio(s, fid, banco.sid, "1")
        assert r.estado == "es_pack"
        assert "pack" in r.texto.lower()
        assert (await s.get(File, fid)).issue_id is None


async def test_vincular_en_sitio_rechaza_unsorted_y_numero_inexistente(banco):
    ruta = banco.lib / "_Unsorted" / "Flash 01.cbz"
    ruta.parent.mkdir()
    ruta.write_bytes(b"x")
    fid = uuid4()
    async with banco.banco.fabrica() as s:
        s.add(File(id=fid, file_path=str(ruta), file_name=ruta.name,
                   file_format=FileFormat.CBZ, metadata_={"match_status": "unsorted"}))
        await s.commit()
    async with banco.banco.fabrica() as s:
        fuera = await vincular_en_sitio(s, fid, banco.sid, "1")
        assert fuera.estado == "fuera_de_biblioteca"
        assert "Organizar" in fuera.texto

    ruta2 = banco.lib / "Comics" / "Flash" / "Flash 02.cbz"
    ruta2.write_bytes(b"y")
    fid2 = uuid4()
    async with banco.banco.fabrica() as s:
        s.add(File(id=fid2, file_path=str(ruta2), file_name=ruta2.name,
                   file_format=FileFormat.CBZ, metadata_={"match_status": "direct"}))
        await s.commit()
    async with banco.banco.fabrica() as s:
        no_existe = await vincular_en_sitio(s, fid2, banco.sid, "99")
        assert no_existe.estado == "issue_no_existe"
        assert "Organizar" in no_existe.texto
        assert (await s.get(File, fid2)).issue_id is None
