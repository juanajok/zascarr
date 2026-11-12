"""#155/BL-D6: validaciones puras de colecciones."""
from __future__ import annotations

from zascarr.services.colecciones import (
    MAX_DESCRIPCION,
    MAX_NOMBRE,
    _politica,
    _validar_descripcion,
    _validar_nombre,
)


def test_nombre_se_recorta_y_valida_longitud():
    assert _validar_nombre("  Grapas  ") == ("Grapas", None)
    assert _validar_nombre("   ")[1] is not None
    assert _validar_nombre("x" * (MAX_NOMBRE + 1))[1] is not None


def test_descripcion_opcional_y_tope():
    assert _validar_descripcion("") == (None, None)
    assert _validar_descripcion("En curso") == ("En curso", None)
    assert _validar_descripcion("x" * (MAX_DESCRIPCION + 1))[1] is not None


def test_politica_tri_estado_solo_acepta_valores_conocidos():
    assert _politica("heredar") is not None
    assert _politica("INCLUIR") is not None
    assert _politica("excluir") is not None
    assert _politica("otra") is None
