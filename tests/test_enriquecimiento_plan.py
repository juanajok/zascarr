"""#128: plan de enriquecimiento por campo, firma y aplicación del mismo plan."""
from __future__ import annotations

from uuid import uuid4

import pytest

from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.enricher import SeriesMatch
from zascarr.services.enriquecimiento_plan import (
    ANADIR,
    BLOQUEADO,
    CONSERVAR,
    OMITIR_POR_AUSENCIA,
    PROPONER_SUSTITUCION,
    EnriquecimientoPlanService,
    PlanDesactualizado,
    SinCoincidencia,
    SinFuente,
    TokenInvalido,
    construir_campos,
)


class Resultado:
    def __init__(self, serie):
        self._serie = serie

    def scalar_one_or_none(self):
        return self._serie


class Sesion:
    def __init__(self, serie):
        self.serie = serie
        self.flushes = 0

    async def execute(self, _stmt):
        return Resultado(self.serie)

    async def flush(self):
        self.flushes += 1


def serie(**cambios) -> Series:
    base = dict(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                start_year=1981)
    base.update(cambios)
    return Series(**base)


def match(**cambios) -> SeriesMatch:
    base = dict(source_id="thorgal", description="Una saga vikinga.",
                cover_url="https://img.test/t.jpg", count_of_issues=12)
    base.update(cambios)
    return SeriesMatch(**base)


def servicio(s, m, **kwargs) -> EnriquecimientoPlanService:
    async def buscador(_serie, _source):
        return m
    return EnriquecimientoPlanService(Sesion(s), "secreto-de-prueba", buscador=buscador, **kwargs)


@pytest.mark.asyncio
async def test_plan_por_campo_con_acciones_disponibles():
    s = serie()
    plan = await servicio(s, match()).previsualizar(s.id)
    por_clave = {c.clave: c for c in plan.campos}
    assert por_clave["tebeosfera_slug"].accion == ANADIR
    assert por_clave["description"].accion == ANADIR
    assert por_clave["cover_url"].accion == ANADIR
    assert por_clave["total_issues"].accion == ANADIR
    assert plan.fuente == MetadataSource.TEBEOSFERA.value
    assert plan.token
    assert s.description is None and s.tebeosfera_slug is None  # la vista previa no escribe


@pytest.mark.asyncio
async def test_sustitucion_conservar_y_omitir():
    s = serie(tebeosfera_slug="thorgal", description="Sinopsis propia.",
              cover_url="https://img.test/t.jpg", total_issues=12)
    svc = servicio(s, match(description="Otra sinopsis.", count_of_issues=None))
    plan = await svc.previsualizar(s.id)
    por_clave = {c.clave: c for c in plan.campos}
    assert por_clave["tebeosfera_slug"].accion == CONSERVAR
    assert por_clave["description"].accion == PROPONER_SUSTITUCION
    assert por_clave["cover_url"].accion == CONSERVAR
    assert por_clave["total_issues"].accion == OMITIR_POR_AUSENCIA


@pytest.mark.asyncio
async def test_campo_bloqueado_se_muestra_pero_no_se_aplica():
    s = serie(locked_fields=["description"])
    plan = await servicio(s, match()).previsualizar(s.id)
    descripcion = next(c for c in plan.campos if c.clave == "description")
    assert descripcion.accion == BLOQUEADO
    assert descripcion.propuesto == "Una saga vikinga."
    assert not descripcion.aplicable


@pytest.mark.asyncio
async def test_aplicar_solo_lo_seleccionado_y_resultado_fiel():
    s = serie(description="Sinopsis propia.", cover_url="https://img.test/actual.jpg",
              total_issues=None)
    svc = servicio(s, match(description="Sinopsis nueva.", cover_url="https://img.test/nueva.jpg"))
    plan = await svc.previsualizar(s.id)
    resultado = await svc.aplicar(plan.token, ["description"])
    assert s.description == "Sinopsis nueva."
    assert s.cover_url == "https://img.test/actual.jpg"
    assert s.total_issues is None
    estados = {c.clave: c.estado for c in resultado.campos}
    assert estados["description"] == "aplicado"
    assert estados["cover_url"] == "no_aplicado"
    assert svc.db.flushes == 1


@pytest.mark.asyncio
async def test_aplicar_sin_seleccion_no_cambia_nada():
    s = serie(description="Sinopsis propia.")
    svc = servicio(s, match(description="Otra."))
    plan = await svc.previsualizar(s.id)
    resultado = await svc.aplicar(plan.token, [])
    assert s.description == "Sinopsis propia."
    assert all(c.estado != "aplicado" for c in resultado.campos)


@pytest.mark.asyncio
async def test_plan_desactualizado_no_aplica_nada():
    s = serie(description="Sinopsis propia.")
    svc = servicio(s, match(description="Otra."))
    plan = await svc.previsualizar(s.id)
    s.description = "La cambió otra pestaña."
    with pytest.raises(PlanDesactualizado):
        await svc.aplicar(plan.token, ["description"])
    assert s.description == "La cambió otra pestaña."


@pytest.mark.asyncio
async def test_token_manipulado_no_aplica():
    s = serie(description="Sinopsis propia.")
    svc = servicio(s, match(description="Otra."))
    plan = await svc.previsualizar(s.id)
    with pytest.raises(TokenInvalido):
        await svc.aplicar(plan.token + "x", ["description"])


@pytest.mark.asyncio
async def test_sin_coincidencia_es_error_de_negocio():
    s = serie()
    with pytest.raises(SinCoincidencia):
        await servicio(s, None).previsualizar(s.id)


@pytest.mark.asyncio
async def test_serie_manual_no_se_enriquece():
    s = serie(metadata_source=MetadataSource.MANUAL.value)
    with pytest.raises(SinFuente):
        await servicio(s, match()).previsualizar(s.id)


def test_la_identidad_no_se_sustituye_por_otra():
    s = serie(comic_vine_id=123)
    campos = construir_campos(
        s, SeriesMatch(source_id=456, description="x"), "comic_vine_id", "Comic Vine"
    )
    identidad = next(c for c in campos if c.clave == "comic_vine_id")
    assert identidad.accion == CONSERVAR
