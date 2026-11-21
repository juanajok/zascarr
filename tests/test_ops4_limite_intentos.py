"""Pruebas del límite en memoria; sin persistencia ni host real."""
from __future__ import annotations

import threading

from deploy.ops.limite_intentos_actualizar_ops4 import (
    BLOQUEO_S,
    UMBRAL_FALLOS,
    VENTANA_S,
    LimiteIntentos,
)

T = 1_800_000_000


def test_bloqueo_tras_umbral_y_exito_limpia() -> None:
    limite = LimiteIntentos()
    for i in range(UMBRAL_FALLOS - 1):
        assert limite.permite(T + i)
        limite.fallo(T + i)
    assert limite.permite(T + UMBRAL_FALLOS)
    limite.fallo(T + UMBRAL_FALLOS)
    assert not limite.permite(T + UMBRAL_FALLOS)
    assert not limite.permite(T + UMBRAL_FALLOS + BLOQUEO_S - 1)
    assert limite.permite(T + UMBRAL_FALLOS + BLOQUEO_S)
    limite.exito()
    assert limite.permite(T + UMBRAL_FALLOS + BLOQUEO_S)


def test_fallos_fuera_de_ventana_no_cuentan() -> None:
    limite = LimiteIntentos()
    for i in range(UMBRAL_FALLOS - 1):
        limite.fallo(T + i)
    limite.fallo(T + VENTANA_S + 1)
    assert limite.permite(T + VENTANA_S + 2)


def test_reloj_invalido_bloquea() -> None:
    for valor in (True, -1, float("nan")):
        limite = LimiteIntentos()
        limite.fallo(valor)
        assert not limite.permite(T)


def test_permite_con_reloj_invalido_deniega() -> None:
    limite = LimiteIntentos()
    assert not limite.permite(True)
    assert not limite.permite(-1)


def test_concurrencia_no_rompe_invariante() -> None:
    limite = LimiteIntentos()
    hilos = [threading.Thread(target=lambda: [limite.fallo(T + i / 100) for i in range(20)])
             for _ in range(4)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    assert not limite.permite(T + 1)


def test_reiniciar_solo_para_pruebas() -> None:
    limite = LimiteIntentos()
    limite.fallo(T)
    limite.reiniciar()
    assert limite.permite(T)
