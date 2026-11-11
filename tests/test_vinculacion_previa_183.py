# ruff: noqa: E501
"""#183 H1/H2: candidatas locales, elección explícita y consumo en el token."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from tests.test_vinculacion_previa_pg import (  # noqa: F401
    SECRETO,
    archivos,
    cliente,
    por_id,
    previsualizar,
    serie_de_prueba,
)
from zascarr.api import revision as api_revision
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import File, Issue, IssueFormat
from zascarr.services import revision_carpetas, vinculacion_previa
from zascarr.services.tokens_revision import verificar_token_eleccion, verificar_token_vinculacion
from zascarr.services.vinculacion_previa import VistaPreviaDeVinculacion
from zascarr.web import asistente_vinculacion

URL = os.environ.get("TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd, monkeypatch, tmp_path):
    b = Banco(url_bd)
    await b.limpiar()
    lib = tmp_path / "biblioteca"
    lib.mkdir()
    monkeypatch.setattr(revision_carpetas, "get_settings", lambda: SimpleNamespace(library_path=lib))
    monkeypatch.setattr(vinculacion_previa, "get_settings", lambda: SimpleNamespace(library_path=lib))
    monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
    monkeypatch.setattr(asistente_vinculacion, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))

    async def _get_db():
        async with b.fabrica() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    yield SimpleNamespace(banco=b, lib=lib)
    app.dependency_overrides.pop(get_db, None)
    await b.cerrar()


async def _issues(entorno, serie, *formatos, volumenes=None):
    ids = []
    async with entorno.banco.fabrica() as s:
        for i, formato in enumerate(formatos):
            iid = uuid4()
            s.add(Issue(id=iid, series_id=serie, issue_number="1", format=formato,
                        volume=(volumenes[i] if volumenes else i + 1)))
            ids.append(iid)
        await s.commit()
    return ids


@pytest.mark.asyncio
async def test_candidatas_locales_y_eleccion_explicita(entorno):
    serie = await serie_de_prueba(entorno)
    await _issues(entorno, serie, IssueFormat.SINGLE_ISSUE, IssueFormat.OMNIBUS,
                  volumenes=[2, 3])
    f = await archivos(entorno, "Flash 1 (1987).cbz")
    p = await previsualizar(serie)
    fila = por_id(p)[str(f["Flash 1 (1987).cbz"])]
    assert fila["estado"] == "numero_ambiguo"
    assert len(fila["candidatas"]) == 2
    assert {c["formato"] for c in fila["candidatas"]} == {"single_issue", "omnibus"}
    assert fila["eleccion"] is None and fila["issue_id_elegida"] is None
    assert fila["token_eleccion"]
    token = fila["token_eleccion"]
    assert verificar_token_eleccion(token, SECRETO) is not None
    candidata = next(c for c in fila["candidatas"] if c["formato"] == "single_issue")

    async with entorno.banco.fabrica() as db:
        servicio = VistaPreviaDeVinculacion(db, secret=SECRETO)
        resultado = await servicio.elegir_publicacion(
            token=token, candidate_id=candidata["candidate_id"])
        await db.commit()
    assert resultado["estado"] == "elegida"

    async with entorno.banco.fabrica() as s:
        guardado = await s.get(File, f["Flash 1 (1987).cbz"])
        assert guardado.issue_id is None
        assert guardado.metadata_["publicacion_identificada"]["issue_id"] == candidata["issue_id"]
        assert guardado.metadata_["publicacion_identificada"]["numero"] == "1"

    # H2: la elección vigente vuelve a la vista, permite marcar y entra en el token como v3.
    p2 = await previsualizar(serie, marcados=[f["Flash 1 (1987).cbz"]])
    fila2 = por_id(p2)[str(f["Flash 1 (1987).cbz"])]
    assert fila2["estado"] == "se_vincularia" and fila2["marcable"]
    assert fila2["issue_id_elegida"] == candidata["issue_id"]
    firmado = verificar_token_vinculacion(p2.json()["token"], SECRETO)
    assert firmado is not None and firmado.archivos[0].issue_id_elegida == candidata["issue_id"]

    # Quitar la elección deja la fila como estaba.
    async with entorno.banco.fabrica() as db:
        servicio = VistaPreviaDeVinculacion(db, secret=SECRETO)
        await servicio.quitar_eleccion(token=token)
        await db.commit()
    p3 = await previsualizar(serie)
    assert por_id(p3)[str(f["Flash 1 (1987).cbz"])]["eleccion"] is None


@pytest.mark.asyncio
async def test_confirmar_usa_la_publicacion_elegida(entorno):
    from zascarr.services.vinculacion import VinculacionDeArchivos

    serie = await serie_de_prueba(entorno)
    await _issues(entorno, serie, IssueFormat.SINGLE_ISSUE, IssueFormat.OMNIBUS,
                  volumenes=[2, 3])
    f = await archivos(entorno, "Flash 1 (1987).cbz")
    p = await previsualizar(serie)
    fila = por_id(p)[str(f["Flash 1 (1987).cbz"])]
    candidata = next(c for c in fila["candidatas"] if c["formato"] == "single_issue")
    async with entorno.banco.fabrica() as db:
        await VistaPreviaDeVinculacion(db, secret=SECRETO).elegir_publicacion(
            token=fila["token_eleccion"], candidate_id=candidata["candidate_id"])
        await db.commit()
    p2 = await previsualizar(serie, marcados=[f["Flash 1 (1987).cbz"]])
    assert p2.json()["token"]
    async with entorno.banco.fabrica() as db:
        r = await VinculacionDeArchivos(db, secret=SECRETO).confirmar(p2.json()["token"])
    assert r.resultado.global_ == "vinculados_todos"
    assert r.resultado.archivos[0].estado == "vinculado"
    async with entorno.banco.fabrica() as db:
        guardado = await db.get(File, f["Flash 1 (1987).cbz"])
        assert str(guardado.issue_id) == candidata["issue_id"]
        assert (await db.execute(text("SELECT count(*) FROM issues WHERE series_id=:s"),
                                {"s": str(serie)})).scalar() == 2


@pytest.mark.asyncio
async def test_ruta_elegir_devuelve_la_fila_actualizada(entorno):
    serie = await serie_de_prueba(entorno)
    await _issues(entorno, serie, IssueFormat.SINGLE_ISSUE, IssueFormat.OMNIBUS,
                  volumenes=[2, 3])
    f = await archivos(entorno, "Flash 1 (1987).cbz")
    fila = por_id(await previsualizar(serie))[str(f["Flash 1 (1987).cbz"])]
    candidata = next(c for c in fila["candidatas"] if c["formato"] == "single_issue")
    async with cliente() as c:
        r = await c.post(
            "/ui/pendientes/carpetas/asistente/vinculacion/elegir",
            data={"eleccion": f"{fila['token_eleccion']}|{candidata['candidate_id']}"})
    assert r.status_code == 200
    assert "Publicación elegida" in r.text
    assert r.headers["cache-control"] == "no-store"
    assert 'class="vinc-candidatas"' in r.text


@pytest.mark.asyncio
async def test_formato_distinto_mantiene_colision(entorno):
    from zascarr.services.vinculacion import VinculacionDeArchivos

    serie = await serie_de_prueba(entorno)
    await _issues(entorno, serie, IssueFormat.SINGLE_ISSUE, IssueFormat.OMNIBUS,
                  volumenes=[2, 3])
    f = await archivos(entorno, "Flash 1 (1987).cbz")
    fila = por_id(await previsualizar(serie))[str(f["Flash 1 (1987).cbz"])]
    elegida = next(c for c in fila["candidatas"] if c["formato"] == "omnibus")
    async with entorno.banco.fabrica() as db:
        await VistaPreviaDeVinculacion(db, secret=SECRETO).elegir_publicacion(
            token=fila["token_eleccion"], candidate_id=elegida["candidate_id"])
        await db.commit()
    token = (await previsualizar(serie, marcados=[f["Flash 1 (1987).cbz"]])).json()["token"]
    async with entorno.banco.fabrica() as db:
        r = await VinculacionDeArchivos(db, secret=SECRETO).confirmar(token)
    assert r.resultado.global_ == "nada_vinculado"
    assert r.resultado.archivos[0].motivo == "colision_de_edicion"
    async with entorno.banco.fabrica() as db:
        guardado = await db.get(File, f["Flash 1 (1987).cbz"])
        assert guardado.issue_id is None
