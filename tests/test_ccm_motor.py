"""CCM-2: motor puro, roles y anti-Frankenstein."""
from __future__ import annotations

from types import SimpleNamespace

from zascarr.core.consolidacion.ambitos import Ambito, RolVinculo, rol_de
from zascarr.core.consolidacion.motor import (
    EstadoSerie,
    RegistroFuente,
    construir_plan,
)
from zascarr.core.consolidacion.politicas import POLITICA_VERSION


def _estado(**kwargs) -> EstadoSerie:
    base = dict(
        id="s-1", tradition="american", language="es",
        actuales={
            "title": "Patrulla-X", "start_year": 1985, "end_year": None,
            "publisher_name": "Fórum", "language": "es", "total_issues": None,
            "description": None,
        },
        locked=frozenset(), metadata={}, updated_at="2026-11-17T00:00:00+00:00",
    )
    base.update(kwargs)
    return EstadoSerie(**base)


def _registro(fuente: str, rol: str, *, payload_hash: str | None = None,
              **normalizado) -> RegistroFuente:
    return RegistroFuente(
        fuente=fuente, rol=rol, external_id=f"{fuente}-1",
        normalizado=normalizado, payload_hash=payload_hash or f"hash-{fuente}",
    )


def test_sin_rol_explicito_es_obra_referencia():
    serie = SimpleNamespace(metadata_={})
    assert rol_de(serie, "comic_vine") is RolVinculo.OBRA_REFERENCIA
    serie = SimpleNamespace(metadata_={"vinculos_rol": {"comic_vine": "edicion_propia"}})
    assert rol_de(serie, "comic_vine") is RolVinculo.EDICION_PROPIA


def test_anti_frankenstein_no_copia_edicion_desde_obra_referencia():
    cv = _registro(
        "comic_vine", RolVinculo.OBRA_REFERENCIA.value,
        edition_scope={"title": "Uncanny X-Men", "start_year": 1963,
                       "end_year": 2011, "publisher_name": "Marvel",
                       "total_issues": 544},
        work_scope={"description": "La Patrulla-X original."},
    )
    tebeo = _registro(
        "tebeosfera", RolVinculo.EDICION_PROPIA.value,
        edition_scope={"title": "Patrulla-X", "start_year": 1985,
                       "publisher_name": "Fórum"},
    )
    estado = _estado(actuales={**_estado().actuales, "start_year": None})
    plan = construir_plan(estado, (cv, tebeo))
    por_campo = {c.campo: c for c in plan.cambios}

    assert por_campo["start_year"].seleccionado.fuente == "tebeosfera"
    assert por_campo["end_year"].estado == "sin_dato"
    assert por_campo["total_issues"].estado == "sin_dato"
    assert por_campo["publisher_name"].seleccionado is None
    assert por_campo["description"].estado == "anadir"
    assert por_campo["description"].seleccionado.fuente == "comic_vine"
    assert not any(
        c.campo in {"end_year", "total_issues"} and c.estado == "anadir"
        for c in plan.cambios
    )


def test_edicion_propia_permite_rellenar_edicion():
    cv = _registro(
        "comic_vine", RolVinculo.EDICION_PROPIA.value,
        edition_scope={"end_year": 2011, "total_issues": 544},
    )
    plan = construir_plan(_estado(), (cv,))
    por_campo = {c.campo: c for c in plan.cambios}
    assert por_campo["end_year"].estado == "anadir"
    assert por_campo["end_year"].seleccionado.valor == 2011
    assert por_campo["total_issues"].seleccionado.valor == 544


def test_manual_y_lock_no_se_tocan():
    estado = _estado(locked=frozenset({"total_issues"}),
                     actuales={**_estado().actuales, "start_year": 1985})
    cv = _registro(
        "comic_vine", RolVinculo.EDICION_PROPIA.value,
        edition_scope={"start_year": 1963, "total_issues": 544},
    )
    prov = {
        "start_year": {"source": "manual", "confianza": "manual"},
        "total_issues": {"source": "manual", "confianza": "manual"},
    }
    plan = construir_plan(estado, (cv,), prov)
    por_campo = {c.campo: c for c in plan.cambios}
    assert por_campo["start_year"].estado == "bloqueado"
    assert por_campo["total_issues"].estado == "bloqueado"
    assert not plan.cambios_aplicables()


def test_legado_no_se_pisa():
    estado = _estado(actuales={**_estado().actuales, "total_issues": 12})
    cv = _registro(
        "comic_vine", RolVinculo.EDICION_PROPIA.value,
        edition_scope={"total_issues": 544},
    )
    plan = construir_plan(estado, (cv,), {
        "total_issues": {"source": "comic_vine", "confianza": "legado",
                         "verificado": False},
    })
    cambio = next(c for c in plan.cambios if c.campo == "total_issues")
    assert cambio.estado == "conservar" and cambio.motivo == "legado"


def test_conflicto_y_descarte():
    estado = _estado(actuales={**_estado().actuales, "total_issues": 12})
    cv = _registro(
        "comic_vine", RolVinculo.EDICION_PROPIA.value,
        edition_scope={"total_issues": 544},
    )
    prov = {"total_issues": {"source": "tebeosfera", "confianza": "fuente"}}
    plan = construir_plan(estado, (cv,), prov)
    cambio = next(c for c in plan.cambios if c.campo == "total_issues")
    assert cambio.estado == "conflicto"
    assert cambio.candidatos[0].valor == 544

    descartado = {"source": "tebeosfera", "confianza": "fuente",
                  "descartados": {"comic_vine": {"valor_descartado": 544}}}
    plan2 = construir_plan(estado, (cv,), {"total_issues": descartado})
    cambio2 = next(c for c in plan2.cambios if c.campo == "total_issues")
    assert cambio2.estado == "conservar" and cambio2.motivo == "descartado"


def test_huella_cambia_con_payload_y_politica_estable():
    estado = _estado()
    a = _registro("comic_vine", RolVinculo.OBRA_REFERENCIA.value,
                  payload_hash="a", work_scope={"description": "a"})
    b = _registro("comic_vine", RolVinculo.OBRA_REFERENCIA.value,
                  payload_hash="b", work_scope={"description": "b"})
    p1 = construir_plan(estado, (a,))
    p2 = construir_plan(estado, (b,))
    assert p1.huella != p2.huella
    assert p1.politica_version == POLITICA_VERSION
    assert p1.cambios and p1.cambios[0].ambito in {Ambito.OBRA, Ambito.EDICION}
