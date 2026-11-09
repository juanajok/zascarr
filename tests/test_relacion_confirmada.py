# ruff: noqa: E501
"""D3-B4 (#233): `estado_de_relacion` es un predicado PURO. Sin BD, sin efectos.

Cubre los cuatro estados, la coherencia del comprobante (operación/serie/fecha/version), la ausencia
de retroactividad y qué relaciones se protegen.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from zascarr.services.relacion_confirmada import (
    VERSIONES_CONOCIDAS,
    EstadoRelacion,
    es_protegida,
    estado_de_relacion,
    relacion_actual,
    vinculo_valido,
)

SERIE = uuid4()
SERIE_2 = uuid4()
ISSUE = uuid4()


def _archivo(*, issue_id=ISSUE, metadata_source=None, vinculo=None):
    return SimpleNamespace(issue_id=issue_id, metadata_source=metadata_source,
                           metadata_={} if vinculo is None else {"vinculo": vinculo})


def _issue(series_id=SERIE):
    return SimpleNamespace(id=ISSUE, series_id=series_id)


def _vinculo(**kw):
    base = {"version": 1, "operacion_id": str(uuid4()), "serie_id": str(SERIE),
            "fecha": "2026-11-09T12:00:00+00:00", "numero": "1", "formato": "single_issue"}
    base.update(kw)
    return base


def test_sin_relacion_no_depende_de_la_procedencia():
    assert estado_de_relacion(_archivo(issue_id=None, metadata_source="manual"), None) is EstadoRelacion.SIN_RELACION
    assert estado_de_relacion(_archivo(issue_id=None, metadata_source="comicinfo_xml"), None) is EstadoRelacion.SIN_RELACION


def test_confirmada_exige_vinculo_valido_y_coherente():
    archivo = _archivo(metadata_source="manual", vinculo=_vinculo())
    assert estado_de_relacion(archivo, _issue()) is EstadoRelacion.CONFIRMADA
    assert es_protegida(EstadoRelacion.CONFIRMADA) is True


def test_manual_sin_comprobante_no_es_confirmada_pero_si_se_protege():
    archivo = _archivo(metadata_source="manual", vinculo=None)
    assert estado_de_relacion(archivo, _issue()) is EstadoRelacion.MANUAL_SIN_COMPROBANTE
    assert es_protegida(EstadoRelacion.MANUAL_SIN_COMPROBANTE) is True


def test_manual_con_vinculo_invalido_no_se_marca_retroactivamente_como_confirmada():
    """D3: una relación manual antigua SIN comprobante no se convierte en confirmada al leerla."""
    for roto in (_vinculo(operacion_id="no-es-uuid"), _vinculo(serie_id=str(SERIE_2)),
                 _vinculo(fecha="ayer"), _vinculo(version=0), _vinculo(version=2),
                 _vinculo(version=True), _vinculo(version="1")):
        assert vinculo_valido({"vinculo": roto}, SERIE) is None
        assert estado_de_relacion(_archivo(metadata_source="manual", vinculo=roto),
                                  _issue()) is EstadoRelacion.MANUAL_SIN_COMPROBANTE


def test_automatica_no_se_protege_y_si_manual_sin_comprobante():
    assert estado_de_relacion(_archivo(metadata_source="comicinfo_xml"), _issue()) is EstadoRelacion.AUTOMATICA
    assert es_protegida(EstadoRelacion.AUTOMATICA) is False
    assert estado_de_relacion(_archivo(metadata_source=None), _issue()) is EstadoRelacion.AUTOMATICA


def test_sin_issue_no_se_inventa_confirmada():
    """Un `issue_id` sin fila cargada no puede acreditar la serie: se clasifica por procedencia."""
    assert estado_de_relacion(_archivo(metadata_source="manual", vinculo=_vinculo()), None) is EstadoRelacion.MANUAL_SIN_COMPROBANTE
    assert estado_de_relacion(_archivo(metadata_source="comicinfo_xml", vinculo=_vinculo()), None) is EstadoRelacion.AUTOMATICA


def test_version_desconocida_no_es_evidencia_y_la_1_si():
    """Regresión QA de #545: la spec exige versiones CONOCIDAS, no cualquier `>= 1`."""
    assert frozenset({1}) == VERSIONES_CONOCIDAS
    archivo_v1 = _archivo(metadata_source="manual", vinculo=_vinculo(version=1))
    assert estado_de_relacion(archivo_v1, _issue()) is EstadoRelacion.CONFIRMADA
    for version in (2, 0, -1, True, "1", 1.0, None):
        roto = _vinculo(version=version)
        assert vinculo_valido({"vinculo": roto}, SERIE) is None, version
        assert estado_de_relacion(_archivo(metadata_source="manual", vinculo=roto),
                                  _issue()) is EstadoRelacion.MANUAL_SIN_COMPROBANTE, version


def test_vinculo_valido_acepta_fecha_z_y_no_acepta_dicts_rotos():
    assert vinculo_valido({"vinculo": _vinculo(fecha="2026-11-09T12:00:00Z")}, SERIE) is not None
    assert vinculo_valido({"vinculo": "no-es-un-dict"}, SERIE) is None
    assert vinculo_valido({}, SERIE) is None
    assert vinculo_valido(None, SERIE) is None


def test_relacion_actual_es_una_huella_sin_ruta_ni_usuario():
    archivo = _archivo(metadata_source="manual", vinculo=_vinculo())
    rel = relacion_actual(archivo, _issue())
    assert set(rel) == {"issue_id", "serie_id", "operacion_id"}
    assert rel["issue_id"] == str(ISSUE) and rel["serie_id"] == str(SERIE)
    assert all("ruta" not in v for v in rel.values())
    # manual sin comprobante: la operación es `None`, no se inventa.
    assert relacion_actual(_archivo(metadata_source="manual"), _issue())["operacion_id"] is None
    assert relacion_actual(_archivo(issue_id=None), None) is None
