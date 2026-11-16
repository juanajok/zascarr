"""Rango de números que cubre un tomo recopilatorio (2026-11-16)."""
from __future__ import annotations

import pytest

from zascarr.services.especiales import (
    EspecialSinNumeroError,
    parsear_rango_de_numeros,
)


def test_rango_simple():
    assert parsear_rango_de_numeros("1-12") == [str(n) for n in range(1, 13)]


def test_lista_con_rangos_y_orden():
    assert parsear_rango_de_numeros("5, 1-3, 2") == ["1", "2", "3", "5"]


def test_vacio_no_cubre_nada():
    assert parsear_rango_de_numeros("") == []
    assert parsear_rango_de_numeros("   ") == []


@pytest.mark.parametrize("texto", ["1-", "a-b", "12-1", "1-1000", "-3"])
def test_rangos_invalidos_se_rechazan(texto):
    with pytest.raises(EspecialSinNumeroError):
        parsear_rango_de_numeros(texto)


def test_tope_de_numeros():
    assert len(parsear_rango_de_numeros("0-299")) == 300
    with pytest.raises(EspecialSinNumeroError):
        parsear_rango_de_numeros("0-300")
