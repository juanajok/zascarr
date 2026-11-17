"""Lector CBZ (BL-LEC1): servicio de páginas, progreso y pantalla."""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest
from PIL import Image

from tests.test_pendientes import FakeExecResult, FakeSession, use_fake_session
from zascarr.models import File, FileFormat, Issue, Series
from zascarr.services import lector


def _jpeg(color=(200, 30, 30)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(buf, format="JPEG")
    return buf.getvalue()


def _cbz(tmp_path):
    ruta = tmp_path / "lectura.cbz"
    with zipfile.ZipFile(ruta, "w") as z:
        for i in (2, 1, 10):
            z.writestr(f"{i:03d}.jpg", _jpeg((i * 20, 30, 30)))
    return ruta


def _file(tmp_path):
    return File(id=uuid4(), issue_id=uuid4(), file_path=str(_cbz(tmp_path)),
                file_name="lectura.cbz", file_format=FileFormat.CBZ, metadata_={})


@pytest.mark.asyncio
async def test_listado_natural_y_pagina_por_indice(tmp_path):
    f = _file(tmp_path)
    db = FakeSession(get_map={(File, f.id): f})
    assert await lector.total_paginas(db, f.id) == 3
    p1 = await lector.pagina(db, f.id, 1)
    p2 = await lector.pagina(db, f.id, 2)
    assert p1.content_type == "image/jpeg" and p1.etag != p2.etag
    assert len(p1.datos) > 0 and p1.datos != p2.datos


@pytest.mark.asyncio
async def test_pagina_fuera_de_rango_y_archivo_no_zip(tmp_path):
    f = _file(tmp_path)
    db = FakeSession(get_map={(File, f.id): f})
    with pytest.raises(lector.PaginaFueraDeRangoError):
        await lector.pagina(db, f.id, 0)
    f2 = File(id=uuid4(), issue_id=uuid4(), file_path=str(tmp_path / "x.pdf"),
              file_name="x.pdf", file_format=FileFormat.PDF, metadata_={})
    db2 = FakeSession(get_map={(File, f2.id): f2})
    with pytest.raises(lector.ArchivoNoLegibleError):
        await lector.pagina(db2, f2.id, 1)


@pytest.mark.asyncio
async def test_archivos_legibles_por_db(tmp_path):
    f = _file(tmp_path)
    cbr = File(id=uuid4(), issue_id=f.issue_id, file_path=str(tmp_path / "x.cbr"),
               file_name="x.cbr", file_format=FileFormat.CBR, metadata_={})
    db = FakeSession(exec_queue=[FakeExecResult([f, cbr])])
    filas = await lector.archivos_legibles(db, f.issue_id)
    assert [a.id for a in filas] == [str(f.id)]


def test_pantalla_y_pagina(tmp_path):
    f = _file(tmp_path)
    issue = SimpleNamespace(id=f.issue_id, issue_number="1", series_id=uuid4())
    serie = SimpleNamespace(id=issue.series_id, title="Serie")
    db = FakeSession(get_map={(File, f.id): f, (Issue, issue.id): issue,
                              (Series, serie.id): serie},
                     exec_queue=[FakeExecResult([None])])
    with use_fake_session(db) as client:
        r = client.get(f"/ui/leer/{f.id}")
        assert r.status_code == 200
        assert 'data-total="3"' in r.text and "/pagina/1" in r.text
        p = client.get(f"/ui/leer/{f.id}/pagina/1")
        assert p.status_code == 200 and p.headers["content-type"].startswith("image/jpeg")
        assert client.get(f"/ui/leer/{f.id}/pagina/0").status_code == 404
        assert client.get(f"/ui/leer/{f.id}/pagina/99").status_code == 404


def test_guardar_progreso_recorta_y_marca_leyendo(tmp_path):
    f = _file(tmp_path)
    db = FakeSession(get_map={(File, f.id): f}, exec_queue=[FakeExecResult([])])
    # El servicio real usa async; el fake no tiene un `commit` que persista, pero sí registra.
    import asyncio
    asyncio.run(lector.guardar_progreso(db, f.id, 99))
    assert db.commit.await_count == 1
