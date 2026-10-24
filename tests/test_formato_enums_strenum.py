"""Contratos de los enums de formato migrados a `enum.StrEnum` (#307).

Estos enums no son columnas de Postgres: se guardan como texto plano en
`files.metadata["formato_contenido"]` a través de `.value` y `json.dumps`.
Estas pruebas fijan los contratos que el código usa de verdad y documentan la
diferencia relevante identificada y aceptada para los consumidores auditados
frente a `(str, enum.Enum)`: `str(miembro)` y las f-strings devuelven ahora el
valor (`"zip"`), no el nombre cualificado (`"Firma.ZIP"`). La auditoría de
consumidores confirma que nadie dependía del nombre cualificado.
"""

import enum as pyenum
import json

import pytest

from zascarr.core.formato_contenedor import formato_contenido
from zascarr.models import ClaseZip, Firma, Tratamiento

MIEMBROS = {
    Firma: {
        "ZIP": "zip",
        "RAR": "rar",
        "SIETE_Z": "7z",
        "TAR": "tar",
        "OTRO": "otro",
        "ILEGIBLE": "ilegible",
    },
    ClaseZip: {
        "TEBEO": "tebeo",
        "ANIDADOS": "anidados",
        "NO_TEBEO": "no_tebeo",
        "CIFRADO": "cifrado",
        "INVALIDO": "invalido",
        "VACIO": "vacio",
        "LIMITE": "limite",
    },
    Tratamiento: {
        "LEER_COMO_ZIP": "leer_como_zip",
        "SOLO_HASH": "solo_hash",
        "AVISAR": "avisar",
    },
}


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_value_no_cambia(tipo, miembros):
    for nombre, valor in miembros.items():
        assert getattr(tipo, nombre).value == valor


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_construccion_desde_valor_e_identidad(tipo, miembros):
    for nombre, valor in miembros.items():
        assert tipo(valor) is getattr(tipo, nombre)


@pytest.mark.parametrize("tipo", MIEMBROS)
def test_valor_desconocido_falla(tipo):
    with pytest.raises(ValueError):
        tipo("no_existe")


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_str_y_fstring_devuelven_el_valor(tipo, miembros):
    # Diferencia relevante identificada y aceptada para los consumidores
    # auditados: antes `str(Firma.ZIP)` era "Firma.ZIP"; ahora es "zip".
    # Nadie interpolaba estos miembros.
    for nombre, valor in miembros.items():
        miembro = getattr(tipo, nombre)
        assert str(miembro) == valor
        assert f"{miembro}" == valor


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_comparacion_y_hash_con_texto(tipo, miembros):
    for nombre, valor in miembros.items():
        miembro = getattr(tipo, nombre)
        assert miembro == valor
        assert {valor: "ok"}[miembro] == "ok"


@pytest.mark.parametrize("tipo,miembros", MIEMBROS.items())
def test_json_serializa_como_texto(tipo, miembros):
    for nombre, valor in miembros.items():
        assert json.dumps(getattr(tipo, nombre)) == json.dumps(valor)


def test_formato_contenido_es_json_plano():
    fc = formato_contenido(Firma.ZIP, ClaseZip.TEBEO)
    assert fc == {"firma": "zip", "clase": "tebeo", "contrato": 1}
    assert json.loads(json.dumps(fc)) == fc
    assert all(not isinstance(v, pyenum.Enum) for v in fc.values())
