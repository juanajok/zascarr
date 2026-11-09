# ruff: noqa: E501
"""QA de B: token atado a su serie, guards, caducado, H11 y copy."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tests.test_asociar_fuente_b import (
    _DB,
    _Res,
    _serie,
    _servicio,
    _token,
)
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.asociacion_fuente import (
    auditar_asociaciones,
    reparar_asociaciones,
)
from zascarr.services.tokens_revision import TTL_SEGUNDOS
from zascarr.services.vinculacion import RETENCION_HORAS, TokenInvalidoError
from zascarr.web import asociar_fuente as web


class _DBStatements(_DB):
    def __init__(self, respuestas):
        super().__init__(respuestas)
        self.statements = []

    async def execute(self, statement, *_a, **_k):
        self.statements.append(statement)
        return await super().execute(statement, *_a, **_k)


def _settings():
    return SimpleNamespace(secret_key="x" * 32, comicvine_enabled=True,
                           anilist_enabled=True, tebeosfera_enabled=True,
                           gcd_enabled=True, comicvine_api_key="clave")


class TestTokenDeOtraSerie:
    @pytest.mark.asyncio
    async def test_servicio_rechaza_token_de_otra_serie_sin_escribir(self):
        serie_a = _serie()
        serie_b = _serie()
        db = _DB([])
        with pytest.raises(TokenInvalidoError):
            await _servicio(db).confirmar(_token(serie_a), serie_esperada=serie_b.id)
        assert db.added == [] and db.valores is None

    def test_ruta_devuelve_400_y_no_escribe(self, monkeypatch):
        serie_a = _serie()
        serie_b = _serie()
        monkeypatch.setattr(web, "get_settings", _settings)
        from tests.test_asociar_fuente_b_web import _FakeSession
        async def _db():
            yield _FakeSession(serie_b)
        app.dependency_overrides[get_db] = _db
        try:
            r = TestClient(app).post(f"/ui/series/{serie_b.id}/asociar/confirmar",
                                     data={"token": _token(serie_a)})
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 400
        assert "No se ha podido asociar" in r.text
        assert serie_a.gcd_id is None and serie_a.metadata_.get("asociaciones") is None


class TestGuards:
    @pytest.mark.asyncio
    async def test_la_serie_se_bloquea_con_for_update(self):
        serie = _serie()
        db = _DBStatements([_Res(), _Res(), _Res(scalar=serie), _Res(), _Res(rowcount=1), _Res()])
        await _servicio(db).confirmar(_token(serie))
        assert any(getattr(s, "_for_update_arg", None) is not None for s in db.statements)

    @pytest.mark.asyncio
    async def test_huella_distinta_no_escribe(self):
        serie = _serie()
        token = _token(serie)
        serie.metadata_ = {"asociaciones": [{"version": 1, "fuente": "gcd",
                                             "id_externo": "999", "entidad": "serie",
                                             "kind": "collection",
                                             "fecha": "2026-11-09T10:00:00+00:00",
                                             "operacion_id": str(uuid4()),
                                             "origen": "confirmada", "modo": "busqueda"}]}
        db = _DB([_Res(), _Res(), _Res(scalar=serie), _Res()])
        resultado = await _servicio(db).confirmar(token)
        assert resultado.motivo == "propuesta_desactualizada"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_ya_asociada_sin_escribir(self):
        serie = _serie(gcd_id=123)
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.resultado == "ya_asociada"
        assert db.valores is None and db.added == []

    @pytest.mark.asyncio
    async def test_integrity_error_en_commit_es_conflicto_no_503(self):
        serie = _serie()
        class _DBCommit(_DB):
            async def commit(self):
                from sqlalchemy.exc import IntegrityError
                raise IntegrityError("COMMIT", {}, Exception("unique"))
        db = _DBCommit([_Res(), _Res(), _Res(scalar=serie), _Res(), _Res(rowcount=1), _Res()])
        resultado = await _servicio(db).confirmar(_token(serie))
        assert resultado.motivo == "conflicto_identificador"
        assert db.rollbacks == 1


class TestCaducado:
    def _resultado(self, ahora):
        serie = _serie()
        db = _DB([_Res(), _Res(), _Res(scalar=serie)])
        return __import__("asyncio").run(
            _servicio(db, ahora=ahora).confirmar(_token(serie, ahora=1000)))

    def test_caducado_reciente_dice_no_se_ha_cambiado(self):
        from zascarr.services.asociacion_fuente import MENSAJE_CADUCADO_SIN_APLICAR
        mensaje = self._resultado(1000 + TTL_SEGUNDOS + 1).mensaje
        assert mensaje == MENSAJE_CADUCADO_SIN_APLICAR

    def test_caducado_viejo_no_afirma_que_no_se_cambio(self):
        from zascarr.services.asociacion_fuente import MENSAJE_CADUCADO_SIN_INFORME
        mensaje = self._resultado(1000 + TTL_SEGUNDOS + RETENCION_HORAS * 3600 + 1).mensaje
        assert mensaje == MENSAJE_CADUCADO_SIN_INFORME
        assert "No se ha cambiado nada" not in mensaje


class TestH11:
    def test_audita_huerfana_duplicada_e_invalida(self):
        serie = _serie(gcd_id=123)
        serie.metadata_ = {"asociaciones": [
            {"version": 1, "fuente": "gcd", "id_externo": "999", "entidad": "serie",
             "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
             "operacion_id": str(uuid4()), "origen": "confirmada", "modo": "busqueda"},
            {"version": 1, "fuente": "comic_vine", "id_externo": "1", "entidad": "serie",
             "kind": None, "fecha": "2026-11-09T10:00:00+00:00",
             "operacion_id": str(uuid4()), "origen": "confirmada", "modo": "busqueda"},
            {"version": 1, "fuente": "comic_vine", "id_externo": "1", "entidad": "serie",
             "kind": None, "fecha": "2026-11-09T10:00:00+00:00",
             "operacion_id": str(uuid4()), "origen": "confirmada", "modo": "busqueda"},
            {"basura": True},
        ]}
        tipos = {i.tipo for i in auditar_asociaciones(serie)}
        assert {"huerfana", "duplicada", "invalida"} <= tipos

    @pytest.mark.asyncio
    async def test_repara_moviendo_al_historial_sin_tocar_columna(self):
        serie = _serie(gcd_id=123)
        serie.metadata_ = {"asociaciones": [
            {"version": 1, "fuente": "gcd", "id_externo": "999", "entidad": "serie",
             "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
             "operacion_id": str(uuid4()), "origen": "confirmada", "modo": "busqueda"},
        ]}
        db = _DB([_Res(scalar=serie), _Res(rowcount=1)])
        r = await reparar_asociaciones(db, serie.id)
        assert r.reparada and r.movidas == 1
        assert db.valores["metadata"]["asociaciones"] == []
        hist = db.valores["metadata"]["asociaciones_historial"]
        assert hist[0]["deshecho"]["motivo"] == "reparacion"
        assert serie.gcd_id == 123


@pytest.mark.asyncio
async def test_enricher_con_rowcount_cero_no_pisa_identidad_ni_metadatos():
    from unittest.mock import AsyncMock

    from tests.test_enricher import FakeExecResult, FakeSession, make_series
    from zascarr.models import ComicTradition
    from zascarr.services.anilist import AniListResult
    from zascarr.services.enricher import EnrichmentReport, EnrichmentService

    class _Session0(FakeSession):
        async def execute(self, statement):
            if statement.__class__.__name__ == "Update":
                return SimpleNamespace(rowcount=0)
            return await super().execute(statement)

    series = make_series("Berserk", tradition=ComicTradition.MANGA)
    anilist = AsyncMock()
    anilist.search_manga.return_value = [AniListResult(anilist_id=42, title_romaji="Berserk")]
    session = _Session0([FakeExecResult([series])])
    report = EnrichmentReport()
    await EnrichmentService(db=session)._enrich_series_batch(
        AsyncMock(), anilist, AsyncMock(), 10, report)
    assert series.anilist_id is None
    assert series.metadata_source is None
    assert report.series_enriched == []


class TestCopyB2:
    def _render(self, monkeypatch, resultado):
        from tests.test_asociar_fuente_b_web import _FakeSession
        serie = _serie()
        monkeypatch.setattr(web, "get_settings", _settings)

        class _Servicio:
            def __init__(self, *_a, **_k):
                pass

            async def confirmar(self, _token, **_k):
                return resultado

        monkeypatch.setattr(web, "AsociacionDeFuente", _Servicio)

        async def _db():
            yield _FakeSession(serie)
        app.dependency_overrides[get_db] = _db
        try:
            return TestClient(app).post(f"/ui/series/{serie.id}/asociar/confirmar",
                                        data={"token": _token(serie)})
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_conflicto_sin_otra_serie_no_pinta_none(self, monkeypatch):
        from zascarr.services.asociacion_fuente import ResultadoAsociacion
        res = ResultadoAsociacion(
            version=1, tipo="asociar_fuente", operacion_id=str(uuid4()),
            series_id=str(uuid4()), resultado="omitida", motivo="conflicto_identificador",
            mensaje="conflicto", fuente="gcd", id_externo="123", otra_serie=None)
        r = self._render(monkeypatch, res)
        assert "None" not in r.text
        assert "otra serie" in r.text

    def test_repeticion_dice_que_es_la_misma(self, monkeypatch):
        from zascarr.services.asociacion_fuente import ResultadoAsociacion
        res = ResultadoAsociacion(
            version=1, tipo="asociar_fuente", operacion_id=str(uuid4()),
            series_id=str(uuid4()), resultado="asociada", motivo=None,
            mensaje="Ficha asociada.", repetida=True, fuente="gcd", id_externo="123")
        r = self._render(monkeypatch, res)
        assert "Es la misma asociación" in r.text
        assert "no se ha duplicado" in r.text.lower()
