"""Guardas de los falsos positivos de ruff S que se silenciaron con `noqa` (dictamen SecOps).

Un `noqa` es una afirmación sobre el código de HOY; estas pruebas fallan si deja de ser cierta.
"""
from __future__ import annotations

import re

import pytest

from zascarr.services.asignacion import VIVAS
from zascarr.web.iconos import ICONOS, icono


def test_asignacion_vivas_es_literal():
    """S608 en `services/asignacion.py`: las consultas interpolan solo `VIVAS`. Si alguien la
    hiciera derivar de algo externo, dejaría de ser esta forma literal."""
    assert re.fullmatch(r"estado IN \('[a-z_]+'(, '[a-z_]+')*\)", VIVAS), VIVAS


@pytest.mark.parametrize("nombre", sorted(ICONOS))
def test_iconos_sin_codigo(nombre):
    """S704 en `web/iconos.py`: lo que se marca como seguro son trazados SVG, no código."""
    interior = ICONOS[nombre]
    assert "<script" not in interior.lower()
    assert not re.search(r"\son\w+\s*=", interior, re.IGNORECASE)
    assert "javascript:" not in interior.lower()


def test_un_icono_desconocido_falla_y_no_se_interpola():
    with pytest.raises(ValueError, match="Icono desconocido"):
        icono("<script>alert(1)</script>")
