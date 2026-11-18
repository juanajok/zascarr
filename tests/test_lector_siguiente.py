"""Siguiente número al terminar (BL-LEC3): sin sort_order y sin huecos inventados."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_pendientes import FakeExecResult, FakeSession
from zascarr.models import File, FileFormat, Issue, IssueFormat, Series
from zascarr.services import lector
from zascarr.services.series import Huecos


def _mundo(tmp_path, *, numero="1", formato=IssueFormat.SINGLE_ISSUE,
           total=10, cubiertos=None):
    serie = SimpleNamespace(id=uuid4(), title="Serie", total_issues=total,
                            metadata_source="comic_vine", kind="regular")
    issue = SimpleNamespace(id=uuid4(), series_id=serie.id, issue_number=numero,
                            format=formato)
    f = File(id=uuid4(), issue_id=issue.id, file_path=str(tmp_path / "x.cbz"),
             file_name="x.cbz", file_format=FileFormat.CBZ, metadata_={},
             covered_issue_ids=cubiertos or [])
    return f, issue, serie


def _db(f, issue, serie, *, cola=None):
    return FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                                (Series, serie.id): serie},
                       exec_queue=cola or [])


@pytest.mark.asyncio
async def test_decimal_y_anual_no_tienen_siguiente(tmp_path):
    for numero, formato in (("1.5", IssueFormat.SINGLE_ISSUE),
                            ("Annual 1", IssueFormat.SINGLE_ISSUE)):
        f, issue, serie = _mundo(tmp_path, numero=numero, formato=formato)
        r = await lector.siguiente_numero(_db(f, issue, serie), f.id)
        assert r.estado == lector.SIN_SIGUIENTE


@pytest.mark.asyncio
async def test_siguiente_poseido_es_leer(tmp_path, monkeypatch):
    f, issue, serie = _mundo(tmp_path, total=10)
    proximo = SimpleNamespace(id=uuid4(), series_id=serie.id, issue_number="2",
                              format=IssueFormat.SINGLE_ISSUE)
    archivo = lector.ArchivoDeLectura(str(uuid4()), "2.cbz", "CBZ")
    db = _db(f, issue, serie, cola=[FakeExecResult([proximo])])
    monkeypatch.setattr(lector, "numeros_poseidos", lambda *_: _async({2}))
    monkeypatch.setattr(lector, "archivo_por_defecto", lambda *_: _async(archivo))
    r = await lector.siguiente_numero(db, f.id)
    assert r.estado == lector.LEER and r.numero == 2 and r.archivo == archivo


@pytest.mark.asyncio
async def test_hueco_fiable_es_falta(tmp_path, monkeypatch):
    f, issue, serie = _mundo(tmp_path, total=10)
    monkeypatch.setattr(lector, "numeros_poseidos", lambda *_: _async({1}))
    monkeypatch.setattr(lector, "huecos_de_serie", lambda *a, **k: _async(
        Huecos([2, 3], True, None)))
    r = await lector.siguiente_numero(_db(f, issue, serie), f.id)
    assert r.estado == lector.FALTA and r.numero == 2


@pytest.mark.asyncio
async def test_sin_total_no_inventa_falta(tmp_path, monkeypatch):
    f, issue, serie = _mundo(tmp_path, total=None)
    monkeypatch.setattr(lector, "numeros_poseidos", lambda *_: _async({1}))
    monkeypatch.setattr(lector, "huecos_de_serie", lambda *a, **k: _async(
        Huecos([], False, "sin total")))
    r = await lector.siguiente_numero(_db(f, issue, serie), f.id)
    assert r.estado == lector.SIN_SIGUIENTE


@pytest.mark.asyncio
async def test_un_pack_5_a_7_lleva_al_8(tmp_path, monkeypatch):
    cubiertos = [SimpleNamespace(id=uuid4(), series_id=uuid4(), issue_number=str(n),
                                 format=IssueFormat.SINGLE_ISSUE) for n in (5, 6, 7)]
    f, issue, serie = _mundo(tmp_path, numero="5", cubiertos=[c.id for c in cubiertos])
    db = _db(f, issue, serie, cola=[FakeExecResult(cubiertos)])
    monkeypatch.setattr(lector, "numeros_poseidos", lambda *_: _async({5, 6, 7}))
    monkeypatch.setattr(lector, "huecos_de_serie", lambda *a, **k: _async(
        Huecos([8], True, None)))
    r = await lector.siguiente_numero(db, f.id)
    assert r.estado == lector.FALTA and r.numero == 8


@pytest.mark.asyncio
async def test_ultimo_numero_sin_siguiente(tmp_path, monkeypatch):
    f, issue, serie = _mundo(tmp_path, numero="10", total=10)
    monkeypatch.setattr(lector, "numeros_poseidos", lambda *_: _async({10}))
    monkeypatch.setattr(lector, "huecos_de_serie", lambda *a, **k: _async(
        Huecos([], True, None)))
    r = await lector.siguiente_numero(_db(f, issue, serie), f.id)
    assert r.estado == lector.SIN_SIGUIENTE


async def _async(valor):
    return valor
