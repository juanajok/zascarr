"""#1002: pantalla «Completar datos» y roles contra Postgres real."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.core.consolidacion.tipos import (
    EstadoFetch,
    FichaRecolectada,
    ResultadoFetch,
    hash_payload,
)
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import EntitySourceRecord, FieldProvenance, Series

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    async def _get_db():
        async with b.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    yield b
    app.dependency_overrides.pop(get_db, None)
    await b.cerrar()


def cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    )


async def _serie_con_ficha(banco: Banco, cv_id: int = 4050) -> UUID:
    sid = await banco.serie("Patrulla-X", 1985)
    async with banco.fabrica() as db:
        fila = await db.get(Series, sid)
        fila.total_issues = None
        fila.comic_vine_id = cv_id
        db.add(EntitySourceRecord(
            entity_type="series", entity_id=sid, source="comic_vine",
            external_id=str(cv_id), license="CV",
            payload={"normalizado": {"edition_scope": {
                "start_year": 1963, "total_issues": 544}}},
            payload_hash="h1",
        ))
        await db.commit()
    return sid


@pytest.mark.asyncio
async def test_pantalla_muestra_roles_conflictos_y_huecos(banco):
    sid = await _serie_con_ficha(banco)
    async with cliente() as c:
        r = await c.get(f"/ui/series/{sid}/datos")
    assert r.status_code == 200
    assert "Completar datos" in r.text
    assert "De dónde vienen los datos" in r.text
    assert "Comic Vine" in r.text
    assert "Huecos listos" in r.text
    assert "Edición que tengo" in r.text
    assert "Hay datos de edición que no se están usando" in r.text
    async with cliente() as c:
        lote = await c.get("/ui/datos")
    assert lote.status_code == 200 and "Revisar datos" in lote.text


@pytest.mark.asyncio
async def test_rol_edicion_propia_permite_aplicar_hueco(banco):
    sid = await _serie_con_ficha(banco)
    async with cliente() as c:
        r = await c.post(f"/ui/series/{sid}/datos/rol",
                         data={"fuente": "comic_vine", "rol": "edicion_propia"})
        assert r.status_code == 303
        r = await c.post(f"/ui/series/{sid}/datos/aplicar")
        assert r.status_code == 303
    async with banco.fabrica() as db:
        serie = await db.get(Series, sid)
        await db.refresh(serie)
        assert serie.total_issues == 544
        valores = (await db.execute(select(Series.id).where(Series.id == sid))).scalar_one()
        assert valores == sid


@pytest.mark.asyncio
async def test_conflicto_se_puede_resolver_y_mantener(banco):
    sid = await _serie_con_ficha(banco)
    async with banco.fabrica() as db:
        fila = await db.get(Series, sid)
        fila.total_issues = 12
        fila.metadata_ = {"vinculos_rol": {"comic_vine": "edicion_propia"}}
        db.add(FieldProvenance(
            entity_type="series", entity_id=sid, field="total_issues",
            source="tebeosfera", value={"valor": 12, "confianza": "fuente"},
        ))
        await db.commit()
    async with cliente() as c:
        r = await c.post(f"/ui/series/{sid}/datos/elegir",
                         data={"campo": "total_issues", "fuente": "comic_vine"})
        assert r.status_code == 303
    async with banco.fabrica() as db:
        fila = await db.get(Series, sid)
        await db.refresh(fila)
        assert fila.total_issues == 544

    # Otra serie: «mantener el mío» deja el descarte registrado.
    sid2 = await _serie_con_ficha(banco, 4051)
    async with banco.fabrica() as db:
        fila = await db.get(Series, sid2)
        fila.total_issues = 12
        fila.metadata_ = {"vinculos_rol": {"comic_vine": "edicion_propia"}}
        db.add(FieldProvenance(
            entity_type="series", entity_id=sid2, field="total_issues",
            source="tebeosfera", value={"valor": 12, "confianza": "fuente"},
        ))
        await db.commit()
    async with cliente() as c:
        r = await c.post(f"/ui/series/{sid2}/datos/mantener",
                         data={"campo": "total_issues", "fuente": "comic_vine"})
        assert r.status_code == 303
    async with banco.fabrica() as db:
        proc = (await db.execute(select(FieldProvenance).where(
            FieldProvenance.entity_id == sid2,
            FieldProvenance.field == "total_issues"))).scalar_one()
        assert proc.value["descartados"]["comic_vine"]["valor_descartado"] == 544


@pytest.mark.asyncio
async def test_boton_buscar_fichas_recolecta_sin_red_externa(banco, monkeypatch):
    sid = await banco.serie("Green Lantern", 2005)
    async with banco.fabrica() as db:
        fila = await db.get(Series, sid)
        fila.comic_vine_id = 4050
        await db.commit()

    class _Adaptador:
        async def fetch_serie(self, external_id, *, hash_previo=None):
            ficha = FichaRecolectada(
                fuente="comic_vine", entidad="series", external_id=external_id,
                url=None, licencia="CV", raw_acotado={"name": "Green Lantern"},
                normalizado={"edition_scope": {"start_year": 2005}},
                normalizer_version=1, payload_hash=hash_payload({"x": 1}),
                observado_en=datetime.now(UTC),
            )
            return ResultadoFetch(EstadoFetch.OK, ficha)

    class _Pila:
        async def aclose(self):
            return None

    async def _abrir():
        return {"adaptadores": {"comic_vine": _Adaptador()}, "pila": _Pila()}

    monkeypatch.setattr("zascarr.web.series.abrir_adaptadores", _abrir)
    async with cliente() as c:
        r = await c.post(f"/ui/series/{sid}/datos/recolectar")
    assert r.status_code == 303
    async with banco.fabrica() as db:
        total = (await db.execute(select(EntitySourceRecord).where(
            EntitySourceRecord.entity_id == sid))).scalars().all()
        assert len(total) == 1 and total[0].source == "comic_vine"


@pytest.mark.asyncio
async def test_lote_lanza_recoleccion_en_segundo_plano(banco, monkeypatch):
    llamado = []

    async def _falso(limite=20):
        llamado.append(limite)

    async def _abrir():
        class _Pila:
            async def aclose(self):
                return None
        return {"adaptadores": {"comic_vine": object()}, "pila": _Pila()}

    monkeypatch.setattr("zascarr.web.datos.abrir_adaptadores", _abrir)
    monkeypatch.setattr("zascarr.web.datos._recolectar_en_segundo_plano", _falso)
    async with cliente() as c:
        r = await c.post("/ui/datos/recolectar")
        assert r.status_code == 303
    assert llamado == [20]
