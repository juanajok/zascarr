# ruff: noqa: E501
"""#449 BL-INF3: cobertura de la información, una consulta agregada y textos exactos."""
from __future__ import annotations

import os
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import (
    ComicTradition,
    Creator,
    CreatorRole,
    Issue,
    IssueCreator,
    Series,
)
from zascarr.services.cobertura import Cobertura, calcular

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


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
    async with entorno.banco.fabrica() as s:
        a = Series(id=uuid4(), title="Alfa", description="Sinopsis A",
                   tradition=ComicTradition.AMERICAN, metadata_source="comic_vine")
        b = Series(id=uuid4(), title="Beta", tradition=ComicTradition.AMERICAN,
                   metadata_source="manual")
        c = Series(id=uuid4(), title="Gamma", description="Sinopsis C",
                   tradition=ComicTradition.AMERICAN)
        s.add_all([a, b, c])
        await s.flush()
        autora = Creator(id=uuid4(), name="Ana")
        s.add(autora)
        await s.flush()
        ia1 = Issue(id=uuid4(), series_id=a.id, issue_number="1", synopsis="Sin A1",
                    release_date=date(1981, 1, 1), metadata_source="comic_vine")
        ia2 = Issue(id=uuid4(), series_id=a.id, issue_number="2")
        ib1 = Issue(id=uuid4(), series_id=b.id, issue_number="1", synopsis="Sin B1",
                    metadata_source="manual")
        s.add_all([ia1, ia2, ib1])
        await s.flush()
        s.add(IssueCreator(issue_id=ia1.id, creator_id=autora.id, role=CreatorRole.WRITER))
        s.add(IssueCreator(issue_id=ib1.id, creator_id=autora.id, role=CreatorRole.PENCILER))
        await s.commit()


@pytest.mark.asyncio
async def test_cifras_y_desglose_conocidos_pg(entorno):
    await _sembrar(entorno)
    async with entorno.banco.fabrica() as s:
        c = await calcular(s)
    assert (c.series_total, c.series_sinopsis, c.series_autores) == (3, 2, 2)
    assert (c.numeros_total, c.numeros_sinopsis, c.numeros_autores, c.numeros_fecha) == (3, 2, 2, 1)
    assert c.series_por_fuente == {
        "comic_vine": 1, "gcd": 0, "anilist": 0, "tebeosfera": 0,
        "comicinfo_xml": 0, "manual": 1, "sin_registrar": 1}
    assert c.numeros_por_fuente == {
        "comic_vine": 1, "gcd": 0, "anilist": 0, "tebeosfera": 0,
        "comicinfo_xml": 0, "manual": 1, "sin_registrar": 1}
    assert sum(c.series_por_fuente.values()) == c.series_total
    assert sum(c.numeros_por_fuente.values()) == c.numeros_total
    assert c.texto_series == "Series: 2 de 3 con sinopsis; 2 de 3 con autores (guion o dibujo)."
    assert c.texto_numeros == "Números: 2 de 3 con sinopsis; 2 de 3 con autores; 1 de 3 con fecha de portada."
    assert c.texto_accion and "leer la información de tus archivos" in c.texto_accion
    assert c.calculado is not None and "Calculado el" in c.texto_fecha
    assert {n for n, _ in c.filas_series()} == {"Comic Vine", "GCD", "AniList", "Tebeosfera", "Desde el archivo", "Puesto a mano", "Sin registrar"}


@pytest.mark.asyncio
async def test_biblioteca_vacia_y_todo_cubierto_pg(entorno):
    async with entorno.banco.fabrica() as s:
        vacia = await calcular(s)
    assert (vacia.series_total, vacia.numeros_total) == (0, 0)
    assert vacia.baja is False and vacia.texto_accion is None
    assert vacia.texto_series.startswith("Series: 0 de 0")
    await _sembrar(entorno)
    async with entorno.banco.fabrica() as s:
        # completar los huecos para el caso «todo cubierto»
        filas = (await s.execute(select(Series))).scalars().all()
        for serie in filas:
            serie.description = serie.description or "Sinopsis"
        issues = (await s.execute(select(Issue))).scalars().all()
        ana = (await s.execute(select(Creator))).scalars().first()
        ya = {(str(i.issue_id), str(i.creator_id), i.role.value) for i in
              (await s.execute(select(IssueCreator))).scalars().all()}
        for issue in issues:
            issue.synopsis = issue.synopsis or "Sinopsis"
            issue.release_date = issue.release_date or date(1981, 1, 1)
            if (str(issue.id), str(ana.id), "writer") not in ya:
                s.add(IssueCreator(issue_id=issue.id, creator_id=ana.id,
                                   role=CreatorRole.WRITER))
        await s.commit()
        cubierta = await calcular(s)
    assert cubierta.baja is False and cubierta.texto_accion is None
    assert cubierta.series_sinopsis == cubierta.series_total
    assert cubierta.numeros_sinopsis == cubierta.numeros_total


@pytest.mark.asyncio
async def test_una_sola_consulta_agregada_pg(entorno):
    await _sembrar(entorno)
    sentencias: list[str] = []
    async with entorno.banco.fabrica() as s:
        event.listen(s.bind.sync_engine, "before_cursor_execute",
                     lambda conn, cursor, statement, *_: sentencias.append(statement))
        await calcular(s)
    assert len(sentencias) == 1


def _cobertura_ejemplo() -> Cobertura:
    return Cobertura(
        series_total=3, series_sinopsis=2, series_autores=2,
        numeros_total=3, numeros_sinopsis=2, numeros_autores=2, numeros_fecha=1,
        series_por_fuente={"comic_vine": 1, "manual": 1, "sin_registrar": 1},
        numeros_por_fuente={"comic_vine": 1, "manual": 1, "sin_registrar": 1},
    )


def test_estado_pinta_el_bloque_y_los_textos(monkeypatch):
    from unittest.mock import AsyncMock

    from zascarr.web import estado as web_estado

    async def _db():
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(web_estado.disponibilidad, "ultima_comprobacion", AsyncMock(return_value=SimpleNamespace(sin_dato=True)))
    monkeypatch.setattr(web_estado.disponibilidad, "contar_no_disponibles", AsyncMock(return_value=0))
    monkeypatch.setattr(web_estado.cobertura, "calcular", AsyncMock(return_value=_cobertura_ejemplo()))
    try:
        r = TestClient(app).get("/estado")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Qué información tengo" in r.text
    assert "Series: 2 de 3 con sinopsis" in r.text
    assert "Números: 2 de 3 con sinopsis" in r.text
    assert "leer la información de tus archivos" in r.text
    assert "De dónde sale cada dato" in r.text
    assert "Calculado el" in r.text
