# ruff: noqa: E501, F401, F811
"""Retirar una serie de la biblioteca (BL-SER1, #303) — pruebas sobre Postgres real y ficheros reales en `tmp`."""
from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

# El entorno base no fija la clave en los módulos nuevos de #303: la fijamos aquí.
import zascarr.api.series as _api_series
import zascarr.web.retirada_serie as _web_retirada
from tests.test_desvinculacion_pg import (  # noqa: F401
    SECRETO,
    archivos,
    cliente,
    escrituras,
    huella_disco,
    instantanea,
    serie_de_prueba,
    url_bd,
)
from tests.test_vinculacion_previa_pg import entorno as entorno_base  # noqa: F401
from zascarr.services.operaciones import resumen_operaciones
from zascarr.services.vinculacion import VinculacionDeArchivos


@pytest.fixture
async def entorno(entorno_base, monkeypatch):
    monkeypatch.setattr(_api_series, "get_settings",
                        lambda: SimpleNamespace(library_path=entorno_base.lib, secret_key=SECRETO))
    monkeypatch.setattr(_web_retirada, "get_settings",
                        lambda: SimpleNamespace(library_path=entorno_base.lib, secret_key=SECRETO))
    return entorno_base

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

PREVIA = "/api/series/{sid}/retirada/previsualizar"
RETIRAR = "/api/series/{sid}/retirada"


async def previa_retirada(sid) -> httpx.Response:
    async with cliente() as c:
        return await c.post(PREVIA.format(sid=sid))


async def retirar(sid, token) -> httpx.Response:
    async with cliente() as c:
        return await c.post(RETIRAR.format(sid=sid), json={"token": token})


async def _serie_con_vinculo(entorno, *nombres, deseados=None):
    serie = await serie_de_prueba(entorno)
    ids = await archivos(entorno, *nombres)
    # vincular con el recorrido real
    from tests.test_desvinculacion_pg import api_previa_vinculacion, confirmar
    r = await api_previa_vinculacion(serie, ids.values())
    assert r.status_code == 200 and r.json()["token"], r.text
    c = await confirmar(r.json()["token"])
    assert c.status_code == 200
    # deseados opcionales
    if deseados:
        async with entorno.banco.fabrica() as s:
            for d in deseados:
                await s.execute(text(
                    "INSERT INTO wishlist (id, series_id, numero, status, origen) VALUES (:i, :s, :n, :st, 'manual')"),
                    {"i": uuid4(), "s": serie, "n": d["numero"], "st": d["status"]})
            await s.commit()
    return serie, ids


# ── Vista previa ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_previa_sin_escrituras_ni_cambios_en_disco(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
    antes_bd = await instantanea(entorno.banco)
    antes_disco = huella_disco(entorno.lib)
    n = len(entorno.banco.sentencias)
    r = await previa_retirada(serie)
    assert r.status_code == 200, r.text
    assert escrituras(entorno.banco, n) == []
    assert huella_disco(entorno.lib) == antes_disco
    assert await instantanea(entorno.banco) == antes_bd


@pytest.mark.asyncio
async def test_previa_contenido_y_token(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    r = await previa_retirada(serie)
    assert r.status_code == 200
    j = r.json()
    assert j["puede_retirar"] is True
    assert j["token"] is not None
    assert j["serie"]["titulo"].startswith("Flash")
    assert len(j["archivos"]) == 1
    assert j["archivos"][0]["nombre"] == "Flash 01 (1987).cbz"
    assert j["alias"] >= 0
    assert j["aviso_disco"] == "Los archivos del disco no se borrarán, moverán ni renombrarán."


@pytest.mark.asyncio
async def test_previa_bloqueo_por_asignacion_viva_por_serie(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    # insertar una asignación viva apuntando a la serie (y a un archivo suyo: el CHECK exige ambos)
    async with entorno.banco.fabrica() as s:
        await s.execute(text(
            "INSERT INTO asignacion_operaciones (id, file_id, series_id, estado, origen, destino, temporal, size_bytes, mtime_ns, sha256, issue_number, formato) "
            "VALUES (:i, :f, :s, 'preparada', '/o', '/d', '/t', 1, 1, :h, '1', 'single_issue')"),
            {"i": uuid4(), "f": list(ids.values())[0], "s": serie, "h": "a" * 64})
        await s.commit()
    r = await previa_retirada(serie)
    assert r.status_code == 200
    j = r.json()
    assert j["puede_retirar"] is False
    assert j["token"] is None
    assert any(b["codigo"] == "asignacion_viva" for b in j["bloqueos"])


@pytest.mark.asyncio
async def test_previa_bloqueo_por_deseado_en_curso(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz", deseados=[{"numero": 2, "status": "searching"}])
    r = await previa_retirada(serie)
    assert r.status_code == 200
    j = r.json()
    assert j["puede_retirar"] is False
    assert j["token"] is None
    assert any(b["codigo"] == "deseado_en_curso" for b in j["bloqueos"])


@pytest.mark.asyncio
async def test_previa_deseado_no_bloqueante(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz", deseados=[{"numero": 2, "status": "wanted"}])
    r = await previa_retirada(serie)
    assert r.status_code == 200
    j = r.json()
    assert j["puede_retirar"] is True
    assert j["token"] is not None


# ── Confirmación ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirmar_retira_y_deja_archivos_por_revisar(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
    r = await previa_retirada(serie)
    token = r.json()["token"]
    antes_disco = huella_disco(entorno.lib)
    c = await retirar(serie, token)
    assert c.status_code == 200, c.text
    j = c.json()
    assert j["resultado"] == "retirada"
    # serie borrada
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(text("SELECT count(*) FROM series WHERE id = :s"), {"s": serie})).scalar() == 0
        assert (await s.execute(text("SELECT count(*) FROM issues WHERE series_id = :s"), {"s": serie})).scalar() == 0
        # archivos en Por revisar
        for fid in ids.values():
            row = (await s.execute(text("SELECT issue_id, review_dismissed, metadata FROM files WHERE id = :f"), {"f": fid})).mappings().first()
            assert row["issue_id"] is None
            assert row["review_dismissed"] is False
            hist = (row["metadata"] or {}).get("vinculo_historial")
            assert isinstance(hist, list) and len(hist) == 1
            assert hist[0].get("deshecho", {}).get("operacion_id") == j["operacion_id"]
    assert huella_disco(entorno.lib) == antes_disco


@pytest.mark.asyncio
async def test_idempotencia_ya_retirada(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    r = await previa_retirada(serie)
    token = r.json()["token"]
    c1 = await retirar(serie, token)
    assert c1.status_code == 200 and c1.json()["resultado"] == "retirada"
    # repetir el mismo token
    c2 = await retirar(serie, token)
    assert c2.status_code == 200, c2.text
    assert c2.json()["resultado"] == "ya_retirada"


@pytest.mark.asyncio
async def test_token_ajeno_422(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    r = await previa_retirada(serie)
    token = r.json()["token"]
    # otra serie
    otra = await serie_de_prueba(entorno)
    c = await retirar(otra, token)
    assert c.status_code == 422


@pytest.mark.asyncio
async def test_cambio_desde_vista_previa_omitido(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    r = await previa_retirada(serie)
    token = r.json()["token"]
    # cambiar la serie tras la vista previa (editar título)
    async with entorno.banco.fabrica() as s:
        await s.execute(text("UPDATE series SET title = 'Otro' WHERE id = :s"), {"s": serie})
        await s.commit()
    c = await retirar(serie, token)
    assert c.status_code == 200, c.text
    assert c.json()["resultado"] == "omitido"
    assert c.json()["motivo"] == "cambio_desde_la_vista_previa"
    # serie sigue existiendo (no se borró)
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(text("SELECT count(*) FROM series WHERE id = :s"), {"s": serie})).scalar() == 1


@pytest.mark.asyncio
async def test_delete_series_intacto(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    async with cliente() as c:
        r = await c.delete(f"/api/series/{serie}")
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_comprobante_presente(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    r = await previa_retirada(serie)
    token = r.json()["token"]
    c = await retirar(serie, token)
    assert c.status_code == 200
    oid = c.json()["operacion_id"]
    async with entorno.banco.fabrica() as s:
        row = (await s.execute(text("SELECT resultado FROM vinculacion_operaciones WHERE operacion_id = :o"), {"o": oid})).scalar()
        assert row is not None
        assert (row or {}).get("tipo") == "retirada_serie"
        # sin rutas/nombres/hash
        assert "file_path" not in json.dumps(row)
        assert "sha256" not in json.dumps(row)
        assert "token" not in json.dumps(row)


@pytest.mark.asyncio
async def test_sagas_perdidas(entorno):
    # crear una saga con un issue de la serie
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    fid = list(ids.values())[0]
    async with entorno.banco.fabrica() as s:
        iid = (await s.execute(text("SELECT issue_id FROM files WHERE id = :f"), {"f": fid})).scalar()
        arc = uuid4()
        await s.execute(text("INSERT INTO story_arcs (id, title) VALUES (:a, 'Saga')"), {"a": arc})
        await s.execute(text("INSERT INTO story_arc_issues (story_arc_id, issue_id, reading_order) VALUES (:a, :i, 1)"), {"a": arc, "i": iid})
        await s.commit()
    r = await previa_retirada(serie)
    assert r.json()["sagas"] == 1
    token = r.json()["token"]
    c = await retirar(serie, token)
    assert c.status_code == 200
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(text("SELECT count(*) FROM story_arc_issues WHERE issue_id = :i"), {"i": iid})).scalar() == 0
        # el arc sigue existiendo (no se borra la saga, solo la participación)
        assert (await s.execute(text("SELECT count(*) FROM story_arcs WHERE id = :a"), {"a": arc})).scalar() == 1


@pytest.mark.asyncio
async def test_dos_confirmaciones_simultaneas_del_mismo_token(entorno):
    """La misma persona pulsa dos veces (o dos pestañas): una retira y la otra ve «ya retirada». Nada se aplica dos veces."""
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
    token = (await previa_retirada(serie)).json()["token"]
    antes_disco = huella_disco(entorno.lib)
    a, b = await asyncio.gather(retirar(serie, token), retirar(serie, token))
    assert a.status_code == 200 and b.status_code == 200
    resultados = sorted([a.json()["resultado"], b.json()["resultado"]])
    assert resultados == ["retirada", "ya_retirada"], (a.text, b.text)
    assert a.json()["operacion_id"] == b.json()["operacion_id"]
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(text("SELECT count(*) FROM series WHERE id = :s"), {"s": serie})).scalar() == 0
        assert (await s.execute(text("SELECT count(*) FROM vinculacion_operaciones WHERE resultado ->> 'tipo' = 'retirada_serie'"),
                                {})).scalar() == 1
        for fid in ids.values():
            fila = (await s.execute(text("SELECT issue_id, metadata FROM files WHERE id = :f"), {"f": fid})).mappings().first()
            assert fila["issue_id"] is None and len(fila["metadata"]["vinculo_historial"]) == 1
    assert huella_disco(entorno.lib) == antes_disco


@pytest.mark.asyncio
async def test_el_informe_de_retirada_no_se_confunde_con_una_vinculacion(entorno):
    serie, ids = await _serie_con_vinculo(entorno, "Flash 01 (1987).cbz")
    c = await retirar(serie, (await previa_retirada(serie)).json()["token"])
    oid = UUID(c.json()["operacion_id"])
    async with entorno.banco.fabrica() as s:
        assert await VinculacionDeArchivos(s, secret=SECRETO).leer_resultado(oid, serie) is None
        resumen = await resumen_operaciones(s)
    # Solo cuenta la vinculación real que hizo `_serie_con_vinculo`; el informe de retirada no se suma.
    assert resumen["vinculacion"]["total"] == 1
    assert resumen["vinculacion"]["completada"] == 1
