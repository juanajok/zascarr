# ruff: noqa: E501
"""MIT-M7 #130-a: normalización y validaciones del servicio de declaraciones."""
from __future__ import annotations

import pytest

from zascarr.services.declaraciones_carpeta import (
    RutaInvalidaError,
    TipoInvalidoError,
    normalizar_ruta,
)


class _SesionQueNoSeUsa:
    async def execute(self, _s):
        raise AssertionError("no debería consultar antes de validar")


def test_normaliza_ruta_relativa_nfc_y_barras():
    assert normalizar_ruta("Cómics\\Autor//Sub/") == "Cómics/Autor/Sub"
    assert normalizar_ruta("  Cómics/./Autor  ") == "Cómics/Autor"


def test_rechaza_absolutas_vacias_y_escapadas():
    for ruta in ("", "   ", "/media/library", "C:\\library", "..", "a/../../b", "."):
        with pytest.raises(RutaInvalidaError):
            normalizar_ruta(ruta)


def test_rechaza_la_raiz_de_la_biblioteca():
    with pytest.raises(RutaInvalidaError):
        normalizar_ruta("Comics/../", raiz_biblioteca="Comics")


def test_tipo_y_origen_invalidos_son_errores_de_negocio():
    async def _caso():
        with pytest.raises(TipoInvalidoError):
            await __import__("zascarr.services.declaraciones_carpeta", fromlist=["declarar"]).declarar(
                _SesionQueNoSeUsa(), "Comics", tipo_de_significado="otro")
    import asyncio
    asyncio.run(_caso())


def test_declaracion_vista_tiene_alcance_y_efectos_en_llano():
    from zascarr.services.declaraciones_carpeta import DeclaracionVista
    v = DeclaracionVista(
        id=__import__("uuid").uuid4(), declaracion_id=__import__("uuid").uuid4(), version=1,
        contexto_raiz="Comics/Autor", incluir_descendientes=True,
        tipo_de_significado=__import__("zascarr.models", fromlist=["TipoSignificadoCarpeta"]).TipoSignificadoCarpeta.AUTOR,
        origen=__import__("zascarr.models", fromlist=["OrigenRegla"]).OrigenRegla.LOCAL,
        estado=__import__("zascarr.models", fromlist=["EstadoRegla"]).EstadoRegla.ACTIVA,
        vigente_desde=__import__("datetime").datetime.now(__import__("datetime").UTC),
        vigente_hasta=None, procedencia={})
    assert v.alcance == "Esta carpeta y sus subcarpetas"
    assert "no crea series" in v.efectos and "no vincula archivos" in v.efectos
