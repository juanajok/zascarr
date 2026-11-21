"""Pruebas sintéticas de coherencia, sin Git ni operaciones de despliegue."""

from __future__ import annotations

import pytest

from deploy.ops.experimento_identidad_ops4 import Identidad, Resultado, comparar_identidades

S = "abcdef0123456789" * 2 + "abcdef01"
HEAD = "1" * 40
CAMPOS = ("aprobado", "ref_reconfirmada", "snapshot", "head0")


def entradas() -> dict[str, Identidad]:
    return {
        "aprobado": Identidad(S, True),
        "ref_reconfirmada": Identidad(S, True),
        "snapshot": Identidad(S, True),
        "head0": Identidad(HEAD, True),
    }


def test_coincidencia_es_solo_coherencia_textual() -> None:
    assert comparar_identidades(**entradas()) is Resultado.COHERENTE


@pytest.mark.parametrize("campo", CAMPOS)
@pytest.mark.parametrize(
    "valor",
    [
        None, "", "a", "a" * 39, "a" * 41, "a" * 64, "A" * 40,
        "g" * 40, "é" * 40, "ａ" * 40, "a" * 39 + "\n",
        " " + "a" * 40, "a" * 40 + " ", "0x" + "a" * 40,
        b"a" * 40, 1, True, [],
    ],
)
def test_sha_ausente_abreviado_o_invalido_se_rechaza(campo: str, valor: object) -> None:
    datos = entradas()
    datos[campo] = Identidad(valor, True)
    assert comparar_identidades(**datos) is Resultado.RECHAZADO


@pytest.mark.parametrize("campo", CAMPOS)
@pytest.mark.parametrize("fiable", [False, None, 1, "true", [], object()])
def test_fiabilidad_no_explicita_se_rechaza(campo: str, fiable: object) -> None:
    datos = entradas()
    datos[campo] = Identidad(S, fiable)
    assert comparar_identidades(**datos) is Resultado.RECHAZADO


@pytest.mark.parametrize("campo", CAMPOS)
@pytest.mark.parametrize("valor", [None, S, {}, False])
def test_entrada_ausente_o_sin_tipo_esperado_se_rechaza(campo: str, valor: object) -> None:
    datos = entradas()
    datos[campo] = valor
    assert comparar_identidades(**datos) is Resultado.RECHAZADO


def test_sin_argumentos_falla_cerrado() -> None:
    assert comparar_identidades() is Resultado.RECHAZADO
    assert comparar_identidades(Identidad(S)) is Resultado.RECHAZADO


@pytest.mark.parametrize("campo", ("aprobado", "ref_reconfirmada", "snapshot"))
def test_cualquier_identidad_de_destino_distinta_se_rechaza(campo: str) -> None:
    datos = entradas()
    datos[campo] = Identidad("2" * 40, True)
    assert comparar_identidades(**datos) is Resultado.RECHAZADO


def test_no_op_no_soportado_requiere_decision() -> None:
    datos = entradas()
    datos["head0"] = Identidad(S, True)
    assert comparar_identidades(**datos) is Resultado.REQUIERE_DECISION


def test_no_op_no_oculta_discrepancia_o_entrada_no_fiable() -> None:
    datos = entradas()
    datos["head0"] = Identidad(S, True)
    datos["snapshot"] = Identidad(HEAD, True)
    assert comparar_identidades(**datos) is Resultado.RECHAZADO
    datos["snapshot"] = Identidad(S, False)
    assert comparar_identidades(**datos) is Resultado.RECHAZADO
