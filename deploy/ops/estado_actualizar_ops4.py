#!/usr/bin/env python3
"""Marca el resultado final de la unidad de actualización; no ejecuta nada.

Uso fijo desde la unidad:
  zascarr-estado-actualizar-ops4 --ruta ... --resultado hecha|fallida|incierta

El resultado que recibe viene de la tabla cerrada de `ExecStopPost` (A1):
  SERVICE_RESULT:EXIT_CODE:EXIT_STATUS
    success:exited:0   -> hecha     (único éxito limpio)
    exit-code:exited:75-> fallida   (cerrojo ocupado: pre-efecto por contrato)
    *                  -> incierta  (timeout, señal, código 1, parada manual...)

Conserva `id` e `inicio_epoch` del estado que escribió el auxiliar, no inventa
estado si no hay uno válido y nunca pisa un terminal (monotonía). Devuelve 0
cuando no hay nada que escribir y 1 solo si la escritura durable no se pudo
confirmar; la unidad lleva el prefijo `-`, así que ese 1 no convierte en
fallida una actualización correcta. No acepta texto libre ni imprime el estado.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

try:  # importado como paquete (pruebas, `python -m`): una sola identidad de módulo
    from .escritor_estado_actualizar_ops4 import (  # noqa: E402
        ResultadoEscritura,
        ResultadoLectura,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )
except ImportError:  # instalado como script suelto en /usr/local/lib/zascarr
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    from escritor_estado_actualizar_ops4 import (  # noqa: E402
        ResultadoEscritura,
        ResultadoLectura,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )

_RESULTADOS = {"hecha", "fallida", "incierta"}
_EXITO_LIMPIO = ("success", "exited", "0")
_PRE_EFECTO_CONTRATO = ("exit-code", "exited", "75")


def resultado_final(
    service_result: object, exit_code: object, exit_status: object,
) -> str | None:
    """Tabla pura de A1; `None` si los valores no son cadenas de systemd.

    Es la referencia normativa de la cadena de `ExecStopPost`: solo el éxito
    limpio es `hecha`, solo el 75 del cerrojo es `fallida` (ocurre antes de
    cualquier efecto); el resto es `incierta` (H-13: `update.sh` usa 1 antes y
    después de tocar código/BD, así que no se puede distinguir pre de post).
    """
    if not (type(service_result) is str and type(exit_code) is str
            and type(exit_status) is str):
        return None
    if (service_result, exit_code, exit_status) == _EXITO_LIMPIO:
        return "hecha"
    if (service_result, exit_code, exit_status) == _PRE_EFECTO_CONTRATO:
        return "fallida"
    return "incierta"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ruta", required=True)
    parser.add_argument("--resultado", required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.resultado not in _RESULTADOS:
        return 2
    lectura, datos = leer_estado_estricto(args.ruta)
    if lectura is not ResultadoLectura.OK or datos is None:
        return 0
    if datos["estado"] in {"hecha", "fallida", "incierta"}:
        return 0
    ahora = int(time.time())
    if ahora < datos["inicio_epoch"]:
        # Reloj invertido: el lector lo dará incierta; no se escribe.
        return 0
    resultado = publicar_transicion(
        args.ruta,
        args.resultado,
        ahora=ahora,
        id_=datos["id"],
        inicio_epoch=datos["inicio_epoch"],
        propietario=propietario_servicio(args.ruta),
    )
    return 1 if resultado is ResultadoEscritura.INCIERTO else 0


if __name__ == "__main__":
    sys.exit(main())
