# ruff: noqa: E501
"""`services/reading_order_resolver.py`: casos de la spec, dos años, confianza y rangos (AC-01).

Módulo puro: sin red ni BD. Se comprueba también que no importa `httpx` ni `sqlalchemy`.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from zascarr.services import reading_order_resolver as resolver
from zascarr.services.reading_order_resolver import (
    ReadingOrderItem,
    clave_de_serie,
    expandir_rango,
    parsear_referencia,
)


@pytest.mark.parametrize(("texto", "esperado"), [
    # Tabla obligatoria de la spec §3 (6 casos del Anexo D + variantes reales).
    ("Uncanny X-Men (1963) #141-142",
     ReadingOrderItem("Uncanny X-Men", anio_volumen=1963, numero_inicio="141",
                      numero_fin="142", tipo="issue", confianza="alta")),
    ("Batman Vol. 3 (2016) #1-6",
     ReadingOrderItem("Batman", anio_volumen=2016, volumen=3, numero_inicio="1",
                      numero_fin="6", tipo="issue", confianza="alta")),
    ("New Teen Titans Annual #2 (1983)",
     ReadingOrderItem("New Teen Titans", anio_numero=1983, numero_inicio="2",
                      tipo="annual", confianza="media")),
    ("Green Lantern Vol. 2 #173 (1984)",
     ReadingOrderItem("Green Lantern", anio_numero=1984, volumen=2,
                      numero_inicio="173", tipo="issue", confianza="alta")),
    ("Daredevil (1998) #1-8",
     ReadingOrderItem("Daredevil", anio_volumen=1998, numero_inicio="1",
                      numero_fin="8", tipo="issue", confianza="alta")),
    ("Crisis on Infinite Earths #1 (limited series) (1985)",
     ReadingOrderItem("Crisis on Infinite Earths", anio_numero=1985, numero_inicio="1",
                      tipo="issue", confianza="media", avisos=("limited series",))),
    ("Legends of the DC Universe: Crisis on Infinite Earths #1 (one-shot) (1999)",
     ReadingOrderItem("Legends of the DC Universe: Crisis on Infinite Earths",
                      anio_numero=1999, numero_inicio="1", tipo="special",
                      confianza="media", avisos=("one-shot",))),
    ("Batman Vol. 2 TPB",
     ReadingOrderItem("Batman", volumen=2, tipo="tpb", confianza="baja")),
    ("Batman: Year One Omnibus",
     ReadingOrderItem("Batman: Year One", tipo="tpb", confianza="baja")),
    ("Amazing Spider-Man #0.1",
     ReadingOrderItem("Amazing Spider-Man", numero_inicio="0.1", tipo="issue",
                      confianza="media")),
    ("Part II: The Dark Phoenix Saga", None),
    # Variantes de número y de marcadores.
    ("X-Men #1/2",
     ReadingOrderItem("X-Men", numero_inicio="1/2", tipo="issue", confianza="media")),
    ("X-Men #12.NOW",
     ReadingOrderItem("X-Men", numero_inicio="12.NOW", tipo="issue", confianza="media")),
    ("X-Men #1A",
     ReadingOrderItem("X-Men", numero_inicio="1A", tipo="issue", confianza="media")),
    ("X-Men #½",                                # ½ se normaliza a 0.5 (Anexo D)
     ReadingOrderItem("X-Men", numero_inicio="0.5", tipo="issue", confianza="media")),
    ("X-Men (1991) #1-8 (of 8)",
     ReadingOrderItem("X-Men", anio_volumen=1991, numero_inicio="1", numero_fin="8",
                      tipo="issue", confianza="alta", avisos=("of 8",))),
    ("Giant-Size X-Men #1",
     ReadingOrderItem("Giant-Size X-Men", numero_inicio="1", tipo="special",
                      confianza="media")),
    ("Batman Vol. 2 (2016)",
     ReadingOrderItem("Batman", anio_volumen=2016, volumen=2, tipo="volume",
                      confianza="baja")),
    ("", None),
    ("   ", None),
    ("Batman Vol. 1-3", None),                  # límite declarado: no es rango de volúmenes
])
def test_parsear_referencia_cubre_la_tabla(texto, esperado):
    assert parsear_referencia(texto) == esperado


def test_los_dos_anios_no_se_mezclan():
    """`anio_volumen` es de la edición; `anio_numero`, del número. La spec los separa."""
    item = parsear_referencia("Green Lantern Vol. 2 #173 (1984)")
    assert item is not None
    assert (item.anio_volumen, item.anio_numero, item.volumen) == (None, 1984, 2)
    item = parsear_referencia("Daredevil (1998) #1-8")
    assert item is not None
    assert (item.anio_volumen, item.anio_numero, item.volumen) == (1998, None, None)


def test_parentesis_no_reconocido_baja_la_confianza():
    item = parsear_referencia("Batman (Edición especial) #1")
    assert item is not None
    assert item.confianza == "baja" and item.avisos == ("edición especial",)


@pytest.mark.parametrize(("texto", "esperado"), [
    ("Uncanny X-Men (1963) #141-142", ["141", "142"]),
    ("Batman Vol. 3 (2016) #1-6", ["1", "2", "3", "4", "5", "6"]),
    ("Amazing Spider-Man #0.1", None),
    ("X-Men #1/2", None),
    ("X-Men #1A", None),
    ("Uncanny X-Men (1963) #141", None),
    ("Batman Vol. 2 TPB", None),
])
def test_expandir_rango_solo_enteros(texto, esperado):
    item = parsear_referencia(texto)
    assert item is not None
    assert expandir_rango(item) == esperado


def test_expandir_rango_tiene_tope():
    item = parsear_referencia("X-Men #1-9999")
    assert item is not None
    assert expandir_rango(item) is None               # por encima de MAX_RANGO
    assert resolver.MAX_RANGO == 100


def test_clave_de_serie_reutiliza_el_matcher_del_proyecto():
    item = parsear_referencia("The Sandman (1989) #1")
    assert item is not None
    assert clave_de_serie(item) == "sandman"


def test_el_modulo_es_puro_sin_httpx_ni_sqlalchemy():
    fuente = Path(inspect.getfile(resolver)).read_text(encoding="utf-8")
    assert "import httpx" not in fuente
    assert "import sqlalchemy" not in fuente
    assert "from sqlalchemy" not in fuente
