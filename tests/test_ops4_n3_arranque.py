"""Regresión parcial N3: timeout no autoriza una reserva nueva."""
from __future__ import annotations

import os

from deploy.ops.escritor_estado_actualizar_ops4 import (
    ResultadoLectura,
    escribir_estado,
    leer_estado_estricto,
)
from deploy.ops.registro_repeticiones_ops4 import reclamar_intento
from deploy.ops.zascarr_actualizar_aux import procesar
from tests.test_ops4_auxiliar_b2 import AHORA, CLAVE, ID, peticion


def test_timeout_con_reserva_durable_bloquea_otra_peticion_tras_reapertura(tmp_path):
    estado = tmp_path / "estado.json"
    directorio = tmp_path / "intentos"
    directorio.mkdir(mode=0o700)
    fd = os.open(directorio, os.O_RDONLY | os.O_DIRECTORY)
    inicios = []
    consumos = []

    def leer():
        resultado, datos = leer_estado_estricto(estado)
        if resultado is ResultadoLectura.AUSENTE:
            return None
        assert resultado is ResultadoLectura.OK
        return datos

    def iniciar(unidad):
        inicios.append(unidad)
        # La orden puede haber llegado a systemd antes de agotarse el plazo.
        raise TimeoutError

    def solicitud(id_):
        return procesar(
            peticion(id_), clave=CLAVE, ahora=AHORA,
            reclamar_uso=lambda _id: True, iniciar=iniciar,
            cerrojo_ocupado=lambda: False, admitir=lambda: "admision",
            liberar=lambda _admision: None, leer_estado=leer,
            crear_intento=lambda id_: reclamar_intento(id_, directorio_fd=fd),
            escribir=lambda datos: escribir_estado(estado, datos),
            reclamar_consumo=lambda id_: consumos.append(id_) or True,
            esperar=lambda _id: "sin",
        )

    try:
        assert solicitud(ID).codigo == "incierta"
        assert (directorio / ID).is_file()
        assert leer()["estado"] == "aceptada"
        assert solicitud("b" * 32).codigo == "operacion_en_curso"
        assert leer()["id"] == ID
        assert len(inicios) == 1
        assert consumos == [ID]
    finally:
        os.close(fd)
