# ruff: noqa: E501
"""`POST /api/series` (C3) está obsoleto, sin cambiar su comportamiento (I3 de #114, ADR 0010 P-2, fase 1).

Fija dos cosas: que solo esa ruta está marcada `deprecated` en el esquema OpenAPI (con la advertencia de que no ofrece
G1–G8) y que **sigue haciendo exactamente lo que hacía** — es la limitación declarada, no un defecto a arreglar en la
fase 1. Cuando se retire (fase 2, I6) estas pruebas se sustituyen por las del `410`/eliminación.
"""
from __future__ import annotations

from tests.test_api_series import FakeSession, use_fake_session
from zascarr.main import app
from zascarr.models import ComicTradition

RUTA = "/api/series"


def _operaciones():
    return app.openapi()["paths"]


class TestMarcadoComoObsoleto:
    def test_solo_el_post_de_crear_esta_marcado_deprecated(self):
        paths = _operaciones()
        assert paths[RUTA]["post"]["deprecated"] is True
        marcadas = {(ruta, metodo) for ruta, ops in paths.items() for metodo, op in ops.items()
                    if isinstance(op, dict) and op.get("deprecated")}
        assert marcadas == {(RUTA, "post")}

    def test_la_descripcion_dice_que_no_ofrece_las_garantias_del_alta(self):
        descripcion = _operaciones()[RUTA]["post"]["description"]
        assert "G1–G8" in descripcion and "alta por token" in descripcion
        assert "/api/revision/serie" in descripcion
        assert "/api/revision/serie/sin-carpeta/previsualizar" in descripcion       # el sustituto existe y se nombra

    def test_el_resto_de_operaciones_de_series_no_cambia(self):
        paths = _operaciones()
        for ruta, metodo in ((RUTA, "get"), ("/api/series/{series_id}", "get"),
                             ("/api/series/{series_id}", "patch"), ("/api/series/{series_id}", "delete")):
            assert not paths[ruta][metodo].get("deprecated"), (ruta, metodo)


class TestSigueComportandoseIgual:
    """La limitación declarada: lo que el alta por token NO hace y esta ruta tampoco."""

    def test_crea_en_un_paso_con_201(self):
        sesion = FakeSession([])
        with use_fake_session(sesion) as client:
            r = client.post(RUTA, json={"title": "Batman"})
        assert r.status_code == 201

    def test_la_tradicion_por_defecto_es_american_y_no_hay_procedencia(self):
        sesion = FakeSession([])
        with use_fake_session(sesion) as client:
            client.post(RUTA, json={"title": "Batman"})
        serie = sesion.added[0]
        assert serie.tradition == ComicTradition.AMERICAN        # G2: sigue sin elegirse
        assert serie.metadata_source is None                      # G5: sin procedencia; el enriquecedor puede completarla
        assert not serie.locked_fields                            # sin identidad protegida
