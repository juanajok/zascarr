# ruff: noqa: E501
"""MIT-M7 132-a: servicio de ciclo de vida de alias (unitarios)."""
from __future__ import annotations

from zascarr.services.alias_reutilizable import AliasInvalidoError, AliasRetiradoError


def test_error_de_alias_en_llano():
    assert "alias" in str(AliasInvalidoError("El alias no es válido.")).lower()
    assert "retirado" in str(AliasRetiradoError("Un alias retirado no se puede reactivar.")).lower()
