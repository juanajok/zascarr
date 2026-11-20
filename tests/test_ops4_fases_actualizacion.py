"""Pruebas del modelo de fases; sin persistencia, host ni ejecución."""
from __future__ import annotations

import pytest

from deploy.ops.modelo_fases_actualizacion_ops4 import (
    EXITO,
    INCIERTAS_POR_FALLO,
    TERMINALES,
    Fase,
    es_terminal,
    puede_reintentar,
    siguiente,
)


def test_cadena_feliz() -> None:
    fase = Fase.PREPARANDO
    vistas = [fase]
    while fase is not Fase.HECHA:
        fase = siguiente(fase, "ok")
        assert fase is not None
        vistas.append(fase)
    assert vistas == [
        Fase.PREPARANDO, Fase.RESERVADA, Fase.COPIANDO, Fase.AVANZANDO,
        Fase.CONSTRUYENDO, Fase.MIGRANDO, Fase.ARRANCANDO, Fase.VERIFICANDO,
        Fase.HECHA,
    ]


@pytest.mark.parametrize("fase", list(Fase))
def test_todas_las_fases_tienen_regla(fase: Fase) -> None:
    if fase in TERMINALES:
        assert siguiente(fase, "ok") is None
        assert siguiente(fase, "fallo") is None
        assert siguiente(fase, "incierto") is None
    else:
        assert siguiente(fase, "ok") in Fase
        assert siguiente(fase, "fallo") in {Fase.FALLIDA, Fase.INCIERTA}
        assert siguiente(fase, "incierto") is Fase.INCIERTA


@pytest.mark.parametrize("fase", sorted(INCIERTAS_POR_FALLO, key=str))
def test_fallo_con_posibles_efectos_es_incierto(fase: Fase) -> None:
    assert siguiente(fase, "fallo") is Fase.INCIERTA


@pytest.mark.parametrize(
    "fase", [f for f in Fase if f not in INCIERTAS_POR_FALLO and f not in TERMINALES]
)
def test_fallo_sin_efectos_declarados_es_fallido(fase: Fase) -> None:
    assert siguiente(fase, "fallo") is Fase.FALLIDA


@pytest.mark.parametrize("resultado", ["", "OK", "fallo ", None, 1, True])
def test_resultado_desconocido_no_avanza(resultado) -> None:
    assert siguiente(Fase.RESERVADA, resultado) is None


@pytest.mark.parametrize("fase", [None, "preparando", 1, object()])
def test_fase_invalida_no_avanza(fase) -> None:
    assert siguiente(fase, "ok") is None


def test_terminales_y_reintento() -> None:
    assert all(es_terminal(f) for f in TERMINALES)
    assert not es_terminal(Fase.PREPARANDO)
    assert not es_terminal("hecha")
    assert all(puede_reintentar(f) is False for f in Fase)


def test_tabla_de_exito_es_total_para_activas() -> None:
    activas = set(Fase) - TERMINALES
    assert set(EXITO) == activas
    assert set(EXITO.values()) <= set(Fase)
