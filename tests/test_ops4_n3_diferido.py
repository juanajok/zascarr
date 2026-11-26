"""Intercalación N3 con entrada real y `update.sh` inofensivo, sin systemd."""
from __future__ import annotations

import os
import time

from deploy.ops.escritor_estado_actualizar_ops4 import (
    ResultadoLectura,
    escribir_estado,
    leer_estado_estricto,
)
from deploy.ops.registro_repeticiones_ops4 import reclamar_intento
from deploy.ops.zascarr_actualizar_aux import procesar
from tests.test_ops4_auxiliar_b2 import CLAVE, ID
from tests.test_ops4_entrada_b2 import _ejecutar, _entorno, _repo
from zascarr.services.autorizacion_actualizacion import crear_autorizacion
from zascarr.services.ops_actualizacion_v4 import construir_peticion_v4


def test_entrada_diferida_usa_reserva_original_despues_de_timeout(tmp_path):
    repo = _repo(tmp_path)
    ruta, entorno = _entorno(tmp_path, repo)
    ruta.unlink()  # Solo el fichero de prueba creado por _entorno.
    directorio = tmp_path / "ops4" / "intentos"
    fd = os.open(directorio, os.O_RDONLY | os.O_DIRECTORY)
    ahora = int(time.time())
    inicios = []

    def leer():
        resultado, datos = leer_estado_estricto(ruta)
        if resultado is ResultadoLectura.AUSENTE:
            return None
        assert resultado is ResultadoLectura.OK
        return datos

    def solicitar(id_):
        autorizacion = crear_autorizacion(clave=CLAVE, id_=id_, ahora=ahora, ttl=60)
        linea = construir_peticion_v4(CLAVE, id=id_, creada=ahora, autorizacion=autorizacion)

        def iniciar(unidad):
            inicios.append(unidad)
            raise TimeoutError  # Systemd queda simulado; la entrada se lanzará después.

        return procesar(
            linea, clave=CLAVE, ahora=ahora, reclamar_uso=lambda _id: True,
            iniciar=iniciar, cerrojo_ocupado=lambda: False,
            admitir=lambda: "admision", liberar=lambda _admision: None,
            leer_estado=leer,
            crear_intento=lambda intento: reclamar_intento(intento, directorio_fd=fd),
            escribir=lambda datos: escribir_estado(ruta, datos),
            reclamar_consumo=lambda _id: True, esperar=lambda _id: "sin",
        )

    try:
        assert solicitar(ID).codigo == "incierta"
        assert solicitar("b" * 32).codigo == "operacion_en_curso"
        assert len(inicios) == 1
        proceso = _ejecutar(entorno)
        assert proceso.returncode == 0, proceso.stderr
        estado = leer()
        assert estado["id"] == ID
        assert (estado["estado"], estado["fase"]) == ("en_curso", "reservada")
        assert (tmp_path / "marca").is_file()  # fixture, no actualización real
    finally:
        os.close(fd)
