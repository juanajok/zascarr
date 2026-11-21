"""Pruebas del modelo abstracto, sin host ni efectos externos."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from deploy.ops.modelo_aprobacion_ops4 import (
    Aprobacion,
    AprobacionInvalidaError,
    Estado,
    consumir,
    marcar_incierta,
    reservar,
)

INICIO = datetime(2026, 1, 1, tzinfo=UTC)
DATOS = dict(sha="a" * 40, head_inicial="b" * 40, instalacion="host",
             origen="origin/main", huella_p="manifiesto", ahora=INICIO,
             reloj_fiable=True)


@pytest.fixture
def aprobacion():
    return Aprobacion(sha=DATOS["sha"], head_inicial=DATOS["head_inicial"],
                      instalacion="host", origen="origin/main", huella_p="manifiesto",
                      nonce="nonce", emitida=INICIO)


def test_transiciones_sobre_la_copia_devuelta_y_ambiguedad(aprobacion):
    reservada = reservar(aprobacion, intento="1", **DATOS)
    assert aprobacion.estado is Estado.AUTORIZADA
    assert reservada.estado is Estado.RESERVADA
    with pytest.raises(AprobacionInvalidaError):
        reservar(reservada, intento="2", **DATOS)
    with pytest.raises(AprobacionInvalidaError):
        consumir(reservada, intento="2", **DATOS)
    consumida = consumir(reservada, intento="1", **DATOS)
    incierta = marcar_incierta(consumida, intento="1")
    assert incierta.estado is Estado.INCIERTA
    for a in (consumida, incierta, marcar_incierta(reservada, intento="1")):
        with pytest.raises(AprobacionInvalidaError):
            reservar(a, intento="1", **DATOS)
        with pytest.raises(AprobacionInvalidaError):
            consumir(a, intento="1", **DATOS)


@pytest.mark.parametrize("cambio", [
    {"sha": "a" * 39}, {"sha": "c" * 40}, {"head_inicial": "c" * 40},
    {"instalacion": "otra"}, {"origen": "otro"}, {"huella_p": "otro"},
    {"reloj_fiable": False}, {"ahora": INICIO - timedelta(microseconds=1)},
    {"ahora": INICIO + timedelta(hours=24)}, {"ahora": INICIO.replace(tzinfo=None)},
])
def test_rechazos_tambien_al_consumir(aprobacion, cambio):
    reservada = reservar(aprobacion, intento="1", **DATOS)
    datos = DATOS | cambio
    with pytest.raises(AprobacionInvalidaError):
        reservar(aprobacion, intento="1", **datos)
    with pytest.raises(AprobacionInvalidaError):
        consumir(reservada, intento="1", **datos)
    assert reservada.estado is Estado.RESERVADA


def test_frontera_y_retroceso_tras_reserva(aprobacion):
    casi = INICIO + timedelta(hours=24, microseconds=-1)
    reservada = reservar(aprobacion, intento="1", **(DATOS | {"ahora": casi}))
    with pytest.raises(AprobacionInvalidaError):
        consumir(reservada, intento="1", **DATOS)
    assert consumir(reservada, intento="1", **(DATOS | {"ahora": casi})).estado is Estado.CONSUMIDA


def test_modelo_puro_no_impide_reservas_concurrentes_sin_cerrojo(aprobacion):
    primera = reservar(aprobacion, intento="1", **DATOS)
    segunda = reservar(aprobacion, intento="2", **DATOS)
    assert primera.intento != segunda.intento


def test_tiempo_transcurrido_utc_ante_cambio_horario(aprobacion):
    zona = ZoneInfo("Europe/Madrid")
    primavera = datetime(2026, 3, 28, 12, tzinfo=zona)
    a = replace(aprobacion, emitida=primavera)
    datos = DATOS | {"ahora": datetime(2026, 3, 29, 12, tzinfo=zona)}
    assert reservar(a, intento="1", **datos).estado is Estado.RESERVADA  # 23 horas reales
    otono = datetime(2026, 10, 24, 12, tzinfo=zona)
    a = replace(aprobacion, emitida=otono)
    with pytest.raises(AprobacionInvalidaError):
        reservar(a, intento="1", **(DATOS | {"ahora": datetime(2026, 10, 25, 12, tzinfo=zona)}))


def test_fecha_extrema_no_desborda_al_reservar(aprobacion):
    instante = datetime.max.replace(tzinfo=UTC)
    a = replace(aprobacion, emitida=instante)
    assert reservar(a, intento="1", **(DATOS | {"ahora": instante})).estado is Estado.RESERVADA


def test_retroceso_entre_horas_repetidas_se_detecta(aprobacion):
    zona = ZoneInfo("Europe/Madrid")
    emitida = datetime(2026, 10, 25, 1, tzinfo=zona)
    tarde = datetime(2026, 10, 25, 2, 30, tzinfo=zona, fold=1)
    antes = datetime(2026, 10, 25, 2, 30, tzinfo=zona, fold=0)
    a = replace(aprobacion, emitida=emitida)
    reservada = reservar(a, intento="1", **(DATOS | {"ahora": tarde}))
    with pytest.raises(AprobacionInvalidaError):
        consumir(reservada, intento="1", **(DATOS | {"ahora": antes}))


@pytest.mark.parametrize("cambio", [
    {"sha": "A" * 40}, {"head_inicial": "x" * 40}, {"nonce": ""},
    {"instalacion": " "}, {"emitida": INICIO.replace(tzinfo=None)},
    {"estado": "autorizada"}, {"estado": Estado.RESERVADA},
    {"intento": "1"},
])
def test_registro_invalido(aprobacion, cambio):
    with pytest.raises(AprobacionInvalidaError):
        replace(aprobacion, **cambio)
