# ruff: noqa: E501, F811
"""BL-VINC1 C15–C17 sobre Postgres real: qué se revisa, que la búsqueda no cambia vínculos y que el informe
no enseña un vínculo que cambió después. Se salta sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text, update

from tests.test_vinculacion_previa_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    archivos,
    entorno,
    serie_de_prueba,
    url_bd,
)
from zascarr.models import File, ImportRun, Issue, IssueFormat
from zascarr.services import vinculos_dudosos

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]


async def _vincular(entorno, sid: UUID, ids: dict[str, UUID], **campos) -> dict[str, UUID]:
    """Un número por archivo (el del nombre); devuelve archivo → número."""
    issues: dict[str, UUID] = {}
    async with entorno.banco.fabrica() as s:
        for nombre, fid in ids.items():
            iid = uuid4()
            numero = str(int(nombre.rsplit(" ", 1)[-1].split(".")[0]))
            s.add(Issue(id=iid, series_id=sid, issue_number=numero, format=IssueFormat.SINGLE_ISSUE))
            await s.flush()
            await s.execute(update(File).where(File.id == fid).values(issue_id=iid, **campos))
            issues[nombre] = iid
        await s.commit()
    return issues


async def _pares(entorno) -> set[tuple]:
    async with entorno.banco.fabrica() as s:
        return {tuple(r) for r in (await s.execute(text("SELECT id, issue_id FROM files"))).all()}


async def _filas(entorno, tabla: str) -> list[tuple]:
    async with entorno.banco.fabrica() as s:
        return [tuple(r) for r in (await s.execute(text(f"SELECT * FROM {tabla} ORDER BY 1"))).all()]


def _marcados(informe) -> set[str]:
    return {m.archivo_id for lote in informe.lotes for m in lote.archivos}


async def test_ausentes_y_pendientes_no_se_revisan(entorno):
    animal = await serie_de_prueba(entorno, "Animal Man", 1989)
    presente = await archivos(entorno, "Animal Man 1.cbz", carpeta="Comics/Animal Man (2012)", en_disco=False)
    ausente = await archivos(entorno, "Animal Man 2.cbz", carpeta="Comics/Animal Man (2012)", en_disco=False)
    await _vincular(entorno, animal, presente)
    await _vincular(entorno, animal, ausente, is_missing=True)
    pendiente = await archivos(entorno, "Animal Man 3.cbz", carpeta="Comics/Animal Man (2012)", en_disco=False)

    async with entorno.banco.fabrica() as s:
        informe = await vinculos_dudosos.buscar(s)

    assert informe.revisados == 1
    assert _marcados(informe) == {str(presente["Animal Man 1.cbz"])}
    assert not ({str(v) for v in (*ausente.values(), *pendiente.values())} & _marcados(informe))


async def test_la_busqueda_no_cambia_vinculos(entorno):
    animal = await serie_de_prueba(entorno, "Animal Man", 1989)
    await _vincular(entorno, animal, await archivos(
        entorno, "Animal Man 1.cbz", "Animal Man 2.cbz", carpeta="Comics/Animal Man (2012)", en_disco=False))
    await archivos(entorno, "Suelto 1.cbz", carpeta="Comics/Sueltos", en_disco=False)
    pares, issues, series = await _pares(entorno), await _filas(entorno, "issues"), await _filas(entorno, "series")
    async with entorno.banco.fabrica() as s:
        antes = (await s.execute(select(ImportRun.id))).scalars().all()

    await vinculos_dudosos.ejecutar(entorno.banco.fabrica)

    assert await _pares(entorno) == pares                  # el conjunto, no el recuento
    assert await _filas(entorno, "issues") == issues
    assert await _filas(entorno, "series") == series
    async with entorno.banco.fabrica() as s:
        nuevos = (await s.execute(select(ImportRun).where(ImportRun.id.notin_(antes)))).scalars().all()
    assert [r.details["kind"] for r in nuevos] == ["vinculos_dudosos"]


async def test_vinculo_cambiado_desde_la_busqueda_no_sale(entorno):
    animal = await serie_de_prueba(entorno, "Animal Man", 1989)
    otra = await serie_de_prueba(entorno, "Animal Man", 2011)
    ids = await archivos(entorno, "Animal Man 1.cbz", "Animal Man 2.cbz", "Animal Man 3.cbz",
                         carpeta="Comics/Animal Man (2012)", en_disco=False)
    await _vincular(entorno, animal, ids)
    await vinculos_dudosos.ejecutar(entorno.banco.fabrica)

    async with entorno.banco.fabrica() as s:
        vigente, _cuando = await vinculos_dudosos.informe_vigente(s)
    assert _marcados(vigente) == {str(v) for v in ids.values()}

    async with entorno.banco.fabrica() as s:
        nuevo = uuid4()
        s.add(Issue(id=nuevo, series_id=otra, issue_number="2", format=IssueFormat.SINGLE_ISSUE))
        await s.flush()
        await s.execute(update(File).where(File.id == ids["Animal Man 1.cbz"]).values(issue_id=None))
        await s.execute(update(File).where(File.id == ids["Animal Man 2.cbz"]).values(issue_id=nuevo))
        await s.commit()

    async with entorno.banco.fabrica() as s:
        vigente, _cuando = await vinculos_dudosos.informe_vigente(s)
    assert _marcados(vigente) == {str(ids["Animal Man 3.cbz"])}
