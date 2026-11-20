"""Pruebas del clasificador de estado de unidad; sin systemd ni E/S."""
from __future__ import annotations

import pytest

from deploy.ops.experimento_estado_unidad_ops4 import (
    Observacion,
    ResultadoInicio,
    clasificar_inicio,
)


@pytest.mark.parametrize(
    "codigo,estado,activo,esperado",
    [
        (0, "active", True, ResultadoInicio.INICIADO),
        (0, "failed", False, ResultadoInicio.FALLIDO),
        (0, "inactive", False, ResultadoInicio.INCIERTO),
        (0, "activating", False, ResultadoInicio.INCIERTO),
        (0, "failed", True, ResultadoInicio.INCIERTO),
        (1, "active", True, ResultadoInicio.INCIERTO),
        (1, "failed", False, ResultadoInicio.INCIERTO),
        (75, "inactive", False, ResultadoInicio.INCIERTO),
        (0, "not-found", False, ResultadoInicio.NO_DISPONIBLE),
        (0, "not-found", True, ResultadoInicio.INCIERTO),
        (1, "not-found", True, ResultadoInicio.INCIERTO),
        (1, "not-found", False, ResultadoInicio.INCIERTO),
        (0, "desconocido", False, ResultadoInicio.INCIERTO),
    ],
)
def test_clasificacion_conservadora(codigo, estado, activo, esperado):
    assert clasificar_inicio(Observacion(codigo, estado, activo)) is esperado


@pytest.mark.parametrize("codigo", [True, 0.0, "0", None])
def test_codigo_no_entero_no_se_interpreta(codigo):
    assert clasificar_inicio(Observacion(codigo, "active", True)) is ResultadoInicio.INCIERTO


@pytest.mark.parametrize("observacion", [None, {}, "active", 1])
def test_observacion_invalida_es_incierta(observacion):
    assert clasificar_inicio(observacion) is ResultadoInicio.INCIERTO
