"""Criterio 4: clasificación del inventario, sin estados inventados."""

from __future__ import annotations

import uuid

import pytest

from zascarr.services.operaciones import (
    _clave_candado,
    clasificar_alta,
    clasificar_asignacion,
    clasificar_vinculacion,
)


class TestClasificarAsignacion:
    def test_estados_historicos(self):
        assert clasificar_asignacion("limpiada", en_curso=False) == "completada"
        assert clasificar_asignacion("cancelada", en_curso=False) == "fallida"

    def test_viva_sin_candado_es_recuperable(self):
        assert clasificar_asignacion("preparada", en_curso=False) == "recuperable"
        assert clasificar_asignacion("confirmada", en_curso=False) == "recuperable"

    def test_viva_con_candado_es_en_curso(self):
        assert clasificar_asignacion("preparada", en_curso=True) == "en_curso"

    def test_estado_inventado_no_se_clasifica_como_completada(self):
        with pytest.raises(ValueError):
            clasificar_asignacion("inventado", en_curso=False)


class TestClasificarAlta:
    def test_creada_y_deshecha(self):
        assert clasificar_alta("creada") == "completada"
        assert clasificar_alta("deshecha") == "no_aplica"

    def test_desconocida(self):
        with pytest.raises(ValueError):
            clasificar_alta("otra")


class TestClasificarVinculacion:
    @pytest.mark.parametrize(
        ("global_", "esperado"),
        [
            ("vinculados_todos", "completada"),
            ("vinculados_parcialmente", "parcial"),
            ("nada_vinculado", "sin_efecto"),
        ],
    )
    def test_globales(self, global_, esperado):
        assert clasificar_vinculacion(global_) == esperado

    def test_desconocido(self):
        with pytest.raises(ValueError):
            clasificar_vinculacion("otra")


def test_la_clave_del_candado_es_la_misma_del_servicio():
    op = uuid.UUID("00000000-0000-0000-0000-000000000101")
    clave = op.int & 0x7FFF_FFFF_FFFF_FFFF
    assert _clave_candado(op) == (clave >> 32, clave & 0xFFFFFFFF)


def test_la_ruta_get_operaciones_esta_registrada():
    from zascarr.main import app

    assert "/api/operaciones" in app.openapi()["paths"]
