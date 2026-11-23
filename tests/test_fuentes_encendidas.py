"""UXA-11 (#1128): `fuentes_encendidas` solo cuenta interruptores de Ajustes."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from zascarr.services.discovery import fuentes_encendidas


def test_sin_ninguna_fuente_encendida_es_cero():
    assert fuentes_encendidas(SimpleNamespace()) == 0


@pytest.mark.parametrize("campos, esperado", [
    ({"comicvine_enabled": True}, 1),
    ({"anilist_enabled": True, "gcd_enabled": True, "metron_enabled": True}, 3),
    ({"anilist_enabled": False, "gcd_enabled": False}, 0),
    ({"fandom_dc_enabled": True, "fandom_marvel_enabled": True,
      "open_library_enabled": True, "tebeosfera_enabled": True}, 4),
])
def test_cuenta_solo_los_interruptores_encendidos(campos, esperado):
    assert fuentes_encendidas(SimpleNamespace(**campos)) == esperado


def test_un_valor_que_no_es_true_no_cuenta():
    """Como en la búsqueda: un «truthy» ajeno (p. ej. un `MagicMock`) no enciende nada."""
    assert fuentes_encendidas(SimpleNamespace(anilist_enabled="yes", gcd_enabled=1)) == 0
