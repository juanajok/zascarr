# ruff: noqa: E501
"""MIT-M7 131-a: alcance y errores del servicio de correspondencias."""
from __future__ import annotations

import pytest

from zascarr.services.correspondencias_contexto import (
    RegistroInvalidoError,
    TipoInvalidoError,
    cubre,
)


@pytest.mark.parametrize("raiz,incluir,carpeta,esperado", [
    ("Comics/A", False, "Comics/A", True),
    ("Comics/A", False, "Comics/A/B", False),
    ("Comics/A", True, "Comics/A/B", True),
    ("Comics/A", True, "Comics/AB", False),
    ("Comics/A", True, "Comics", False),
])
def test_alcance_por_segmentos(raiz, incluir, carpeta, esperado):
    assert cubre(raiz, incluir, carpeta) is esperado


def test_tipo_de_destino_invalido_es_error_en_llano():
    from zascarr.services.correspondencias_contexto import _tipo_destino
    with pytest.raises(TipoInvalidoError):
        _tipo_destino("edicion")


def test_registro_invalido_por_tipo():
    import asyncio
    from types import SimpleNamespace

    from zascarr.services.correspondencias_contexto import evaluar
    with pytest.raises(RegistroInvalidoError):
        asyncio.run(evaluar(SimpleNamespace(), SimpleNamespace(tipo="obra", carpeta="Comics/A")))
