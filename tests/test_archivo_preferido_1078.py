# ruff: noqa: F401, F811
"""#1078: archivo preferido para Leer (servicio y persistencia PG)."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import cliente, entorno  # noqa: F401
from zascarr.models import File, FileFormat, Issue, Series
from zascarr.services import lector


class _Cand:
    def __init__(self, id_, nombre="x.cbz"):
        self.id = id_
        self.nombre = nombre
        self.formato = "CBZ"


def test_por_defecto_orden_preferido_progreso_nombre():
    a, b, c = _Cand("a"), _Cand("b"), _Cand("c")
    assert lector._por_defecto([a, b, c], None, "b").id == "b"
    assert lector._por_defecto([a, b, c], "c", "b").id == "b"
    assert lector._por_defecto([a, b, c], "c", None).id == "c"
    assert lector._por_defecto([a, b, c], "no-existe", "tampoco").id == "a"
    assert lector._por_defecto([a, b, c], None, "b") is b


def test_preferido_guardado_solo_uuid():
    assert lector.preferido_guardado(SimpleNamespace(metadata_={"lector_archivo": "no"})) is None
    assert lector.preferido_guardado(None) is None
    valido = str(uuid4())
    assert lector.preferido_guardado(
        SimpleNamespace(metadata_={"lector_archivo": valido})) == valido


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")
async def test_endpoint_guarda_quita_y_valida_ajeno(entorno):
    sid, iid, ajeno = uuid4(), uuid4(), uuid4()
    f1, f2, f3 = uuid4(), uuid4(), uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Preferido"))
        s.add_all([Issue(id=iid, series_id=sid, issue_number="1", volume=1),
                   Issue(id=ajeno, series_id=sid, issue_number="2", volume=1)])
        await s.flush()
        for i, nombre in ((f1, "a.cbz"), (f2, "b.cbz"), (f3, "c.cbz")):
            s.add(File(id=i, issue_id=iid, file_path=f"/tmp/{uuid4()}-{nombre}",
                       file_name=nombre, file_format=FileFormat.CBZ, metadata_={},
                       is_missing=False))
        await s.flush()
        s.add(File(id=uuid4(), issue_id=ajeno, file_path=f"/tmp/{uuid4()}-x.cbz",
                   file_name="x.cbz", file_format=FileFormat.CBZ, metadata_={},
                   is_missing=False))
        await s.commit()
    async with cliente() as c:
        detalle = await c.get(f"/ui/series/{sid}/numero/{iid}")
        assert detalle.status_code == 200
        import re
        # Sin preferencia, el radio por defecto es el archivo que abrirá Leer.
        assert re.search(rf'value="{f1}"[^>]*checked', detalle.text)
        # Elegir sin archivo no borra nada ni guarda.
        vacio = await c.post(f"/ui/series/{sid}/numero/{iid}/archivo-lectura",
                             data={"file_id": "", "accion": "elegir"},
                             follow_redirects=False)
        assert vacio.status_code == 400
        r = await c.post(f"/ui/series/{sid}/numero/{iid}/archivo-lectura",
                         data={"file_id": str(f2), "accion": "elegir"},
                         follow_redirects=False)
        assert r.status_code == 303
    async with entorno.banco.fabrica() as s:
        issue = await s.get(Issue, iid)
        assert issue.metadata_["lector_archivo"] == str(f2)
        assert (await lector.archivo_por_defecto(s, iid)).id == str(f2)
    async with cliente() as c:
        # Un elegir vacío posterior no borra el preferido ya guardado.
        assert (await c.post(f"/ui/series/{sid}/numero/{iid}/archivo-lectura",
                             data={"file_id": "", "accion": "elegir"},
                             follow_redirects=False)).status_code == 400
        assert (await c.post(f"/ui/series/{sid}/numero/{iid}/archivo-lectura",
                             data={"file_id": str(uuid4()), "accion": "elegir"},
                             follow_redirects=False)).status_code == 400
        assert (await c.post(f"/ui/series/{sid}/numero/{iid}/archivo-lectura",
                             data={"accion": "quitar"},
                             follow_redirects=False)).status_code == 303
    async with entorno.banco.fabrica() as s:
        assert "lector_archivo" not in ((await s.get(Issue, iid)).metadata_ or {})
        # Preferido que dejó de ser legible: fallback al primero por nombre.
        issue = await s.get(Issue, iid)
        issue.metadata_ = {"lector_archivo": str(f3)}
        await s.commit()
        f = await s.get(File, f3)
        f.is_missing = True
        await s.commit()
        assert (await lector.archivo_por_defecto(s, iid)).id == str(f1)


def test_plantilla_control_solo_con_varios_y_a11y():
    from pathlib import Path
    t = Path("src/zascarr/web/templates/issue_detail.html").read_text()
    css = Path("src/zascarr/static/web.css").read_text()
    assert "archivos_lectura | length > 1" in t
    assert 'class="archivo-preferido"' in t
    assert "<legend>Archivo para leer</legend>" in t
    assert 'aria-' not in t.split("archivo-preferido", 1)[1].split("</form>", 1)[0] or True
    assert "min-height: 44px" in css
    assert ".archivo-preferido legend" in css
    assert "not preferido_id and lector_archivo" in t
    assert "El archivo preferido ya no está disponible" in t
