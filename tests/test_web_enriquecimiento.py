"""#128: superficie web de la vista previa y aplicación del plan."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.services.enriquecimiento_plan import (
    ANADIR,
    BLOQUEADO,
    CONSERVAR,
    OMITIR_POR_AUSENCIA,
    PROPONER_SUSTITUCION,
    CampoPlan,
    EnriquecimientoPlanService,
    Plan,
    Resultado,
    ResultadoCampo,
    SinCoincidencia,
    TokenInvalido,
)


class FakeSession:
    def __init__(self, series):
        self.series = series

    async def get(self, _model, _id):
        return self.series

    async def execute(self, _stmt):
        raise AssertionError("la ruta de vista previa no debe consultar la ficha por execute")


def use_session(series):
    async def _db():
        yield FakeSession(series)

    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)

    return _Ctx()


def plan(series) -> Plan:
    return Plan(
        series_id=series.id, titulo=series.title, fuente="tebeosfera",
        fuente_etiqueta="Tebeosfera",
        campos=(
            CampoPlan("description", "Sinopsis", "Actual", "Propuesta", "Tebeosfera",
                      "Se añadirá este dato.", ANADIR),
            CampoPlan("cover_url", "Portada", "Actual", "Propuesta", "Tebeosfera",
                      "Protegido.", BLOQUEADO),
        ),
        token="token-firmado",
    )


def test_previsualizar_muestra_plan_por_campo(monkeypatch):
    s = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(EnriquecimientoPlanService, "previsualizar",
                        AsyncMock(return_value=plan(s)))
    with use_session(s) as client:
        r = client.post(f"/ui/series/{s.id}/enriquecimiento/previsualizar")
    assert r.status_code == 200
    assert "Revisar datos de la fuente" in r.text
    assert "Sinopsis" in r.text and "Propuesta" in r.text
    assert 'name="token" value="token-firmado"' in r.text
    assert 'name="campos" value="description"' in r.text
    assert 'name="campos" value="cover_url"' not in r.text
    assert "Esto es una propuesta: no se ha cambiado nada de tu ficha." in r.text
    # La maquetación móvil oculta la cabecera: cada celda conserva su etiqueta.
    assert '<td class="enriquecimiento-valor" data-label="Ahora">' in r.text
    assert '<td class="enriquecimiento-valor" data-label="Propuesta">' in r.text
    assert '<td data-label="Origen">' in r.text
    assert '<td data-label="Acción">' in r.text
    assert '<td data-label="Aplicar">' in r.text
    # Las acciones se ven en español; no se filtran los códigos internos.
    assert ">Añadir</span>" in r.text and ">Protegido</span>" in r.text
    assert ">anadir</span>" not in r.text


def _plan_con_todas_las_acciones(s):
    return Plan(
        series_id=s.id, titulo=s.title, fuente="tebeosfera", fuente_etiqueta="Tebeosfera",
        token="token-firmado",
        campos=(
            CampoPlan("comic_vine_id", "Identidad", None, "777", "Tebeosfera",
                      "Se añadirá.", ANADIR),
            CampoPlan("description", "Sinopsis", "Actual", "Propuesta", "Tebeosfera",
                      "Se sustituirá si la marcas.", PROPONER_SUSTITUCION),
            CampoPlan("cover_url", "Portada", "Actual", "Propuesta", "Tebeosfera",
                      "Protegido.", BLOQUEADO),
            CampoPlan("total_issues", "Números", 3, 3, "Tebeosfera",
                      "Coincide; se conserva.", CONSERVAR),
            CampoPlan("publisher", "Editorial", "Actual", None, "Tebeosfera",
                      "La fuente no lo trae.", OMITIR_POR_AUSENCIA),
        ),
    )


def test_las_acciones_del_plan_se_muestran_en_espanol(monkeypatch):
    s = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(EnriquecimientoPlanService, "previsualizar",
                        AsyncMock(return_value=_plan_con_todas_las_acciones(s)))
    with use_session(s) as client:
        r = client.post(f"/ui/series/{s.id}/enriquecimiento/previsualizar")
    assert r.status_code == 200
    for texto in ("Añadir", "Sustituir", "Protegido", "Conservar", "Omitir"):
        assert f">{texto}</span>" in r.text
    for codigo in ("anadir", "proponer_sustitucion", "omitir_por_ausencia"):
        assert f">{codigo}</span>" not in r.text


def test_error_de_vista_previa_se_explica_sin_romper(monkeypatch):
    s = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(EnriquecimientoPlanService, "previsualizar",
                        AsyncMock(side_effect=SinCoincidencia(
                            "La fuente no tiene una coincidencia inequívoca para esta serie.")))
    with use_session(s) as client:
        r = client.post(f"/ui/series/{s.id}/enriquecimiento/previsualizar")
    assert r.status_code == 200
    assert "La fuente no tiene una coincidencia inequívoca" in r.text
    assert "Volver a la ficha" in r.text


def test_aplicar_reenvia_el_mismo_token_y_muestra_resultado(monkeypatch):
    s = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    resultado = Resultado(series_id=s.id, titulo=s.title, campos=(
        ResultadoCampo("description", "Sinopsis", "proponer_sustitucion", "aplicado",
                       "Aplicado a la ficha."),
        ResultadoCampo("cover_url", "Portada", "bloqueado", "bloqueado",
                       "Protegido; no se toca."),
    ))
    aplicar = AsyncMock(return_value=resultado)
    monkeypatch.setattr(EnriquecimientoPlanService, "aplicar", aplicar)
    with use_session(s) as client:
        r = client.post(f"/ui/series/{s.id}/enriquecimiento/aplicar",
                        data={"token": "token-firmado", "campos": ["description"]})
    assert r.status_code == 200
    assert "Datos revisados" in r.text
    assert "aplicado" in r.text and "bloqueado" in r.text
    aplicar.assert_awaited_once()
    assert aplicar.await_args.args[1] == ["description"]
    assert aplicar.await_args.args[2] == s.id


def test_aplicar_con_token_invalido_no_afirma_que_aplico(monkeypatch):
    s = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(EnriquecimientoPlanService, "aplicar",
                        AsyncMock(side_effect=TokenInvalido(
                            "La vista previa no es válida o ha caducado; vuelve a revisarla.")))
    with use_session(s) as client:
        r = client.post(f"/ui/series/{s.id}/enriquecimiento/aplicar",
                        data={"token": "malo", "campos": ["description"]})
    assert r.status_code == 200
    assert "no es válida o ha caducado" in r.text
    assert "Esto es lo que ha pasado con cada campo" not in r.text
