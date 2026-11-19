"""CCM-4: motor y adaptadores de issue."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from zascarr.core.consolidacion.ambitos import RolVinculo
from zascarr.core.consolidacion.motor import RegistroFuente
from zascarr.core.consolidacion.motor_issue import (
    EstadoIssue,
    construir_plan_issue,
)
from zascarr.services.consolidacion.adaptadores_issue import (
    AdaptadorComicVineIssue,
    AdaptadorFandomIssue,
    AdaptadorTebeosferaIssue,
)


def _estado(**kw):
    base = dict(id="i-1", tradition="american", language="es",
                actuales={"title": "Número 1", "release_date": None,
                          "page_count": None, "isbn": None, "synopsis": None},
                locked=frozenset(), updated_at="2026-11-17T00:00:00+00:00")
    base.update(kw)
    return EstadoIssue(**base)


def _reg(fuente, rol, **normalizado):
    return RegistroFuente(fuente=fuente, rol=rol, external_id=f"{fuente}-1",
                          normalizado=normalizado, payload_hash=f"h-{fuente}")


def test_issue_sin_rol_edicion_no_rellena_fecha():
    cv = _reg("comic_vine", RolVinculo.OBRA_REFERENCIA.value,
              edition_scope={"release_date": "2020-01-01"})
    plan = construir_plan_issue(_estado(), (cv,))
    cambio = next(c for c in plan.cambios if c.campo == "release_date")
    assert cambio.estado == "sin_dato"


def test_issue_con_edicion_propia_rellena_fecha_y_paginas():
    cv = _reg("comic_vine", RolVinculo.EDICION_PROPIA.value,
              edition_scope={"release_date": "2020-01-01", "page_count": 32})
    plan = construir_plan_issue(_estado(), (cv,))
    por_campo = {c.campo: c for c in plan.cambios}
    assert por_campo["release_date"].estado == "anadir"
    assert por_campo["page_count"].seleccionado.valor == 32


def test_issue_sinopsis_de_obra_si_se_puede_proponer():
    cv = _reg("comic_vine", RolVinculo.OBRA_REFERENCIA.value,
              work_scope={"synopsis": "Una historia."})
    plan = construir_plan_issue(_estado(), (cv,))
    cambio = next(c for c in plan.cambios if c.campo == "synopsis")
    assert cambio.estado == "anadir" and cambio.seleccionado.valor == "Una historia."


class _ClienteCV:
    async def get_issue_detail(self, issue_id):
        return {"id": issue_id, "name": "Número 1", "issue_number": "1",
                "store_date": "2020-01-01", "cover_date": "2019-12-01",
                "description": "Sinopsis", "page_count": 32}


class _ClienteTebeosfera:
    async def get_numero(self, slug):
        return SimpleNamespace(slug=slug, numero_publicacion="1", fecha="2020-01-01",
                               paginas=32, url_ficha="https://example.test/1")


class _ClienteFandom:
    async def get_issue(self, page):
        return SimpleNamespace(page_title=page, release_date=datetime(2020, 1, 1).date(),
                               story_title="Número 1", synopsis="Sinopsis")


@pytest.mark.asyncio
async def test_adaptadores_issue_normalizan_por_id():
    cv = await AdaptadorComicVineIssue(_ClienteCV()).fetch_issue("1")
    assert cv.estado.value == "ok"
    assert cv.ficha.normalizado["edition_scope"]["release_date"] == "2020-01-01"
    assert cv.ficha.normalizado["work_scope"]["synopsis"] == "Sinopsis"
    tebeo = await AdaptadorTebeosferaIssue(_ClienteTebeosfera()).fetch_issue("slug-1")
    assert tebeo.ficha.normalizado["edition_scope"]["page_count"] == 32
    fandom = await AdaptadorFandomIssue(_ClienteFandom(), "fandom_dc").fetch_issue("Batman Vol 1 1")
    assert fandom.ficha.normalizado["work_scope"]["synopsis"] == "Sinopsis"
