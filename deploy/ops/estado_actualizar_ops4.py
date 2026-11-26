#!/usr/bin/env python3
"""Marca la fase o el resultado final de la unidad; no ejecuta nada.

Uso fijo desde la unidad, modo terminal (como hasta ahora):
  zascarr-estado-actualizar-ops4 --ruta ... --resultado hecha|fallida|incierta
                                [--codigo success:exited:0|exit-code:exited:75|otro]

La unidad pasa el código mapeado de `SERVICE_RESULT`; sin `--codigo`, una
invocación manual cierra con el código cerrado «otro».

Modo de fase intermedia (contrato B1, §4), para el mismo intento en curso:
  zascarr-estado-actualizar-ops4 --ruta ... --fase preparacion|copia|git|build|migracion|arranque
                                [--head0 SHA] [--sha-destino SHA] [--sha-actual SHA]

El resultado terminal viene de la tabla cerrada de `ExecStopPost` (A1):
  SERVICE_RESULT:EXIT_CODE:EXIT_STATUS
    success:exited:0   -> hecha     (único éxito limpio)
    exit-code:exited:75-> fallida   (cerrojo ocupado: pre-efecto por contrato)
    *                  -> incierta  (timeout, señal, código 1, parada manual...)

Conserva `id` e `inicio_epoch` del estado que escribió el auxiliar, no inventa
estado si no hay uno válido y nunca pisa un terminal (monotonía). El modo de
fase publica `en_curso` con una fase intermedia del orden del contrato y no
exige `--resultado`; el modo terminal escribe fase `fin`, resultado y código.
Ambos modos son mutuamente excluyentes y sus combinaciones incompatibles o sus
valores fuera de conjuntos cerrados devuelven 2 sin escribir. Devuelve 0
cuando no hay nada que escribir (sin estado previo, ya terminal o rechazo por
monotonía) y 1 solo si la escritura durable no se pudo confirmar; la unidad
lleva el prefijo `-`, así que ese 1 no convierte en fallida una actualización
correcta. No acepta texto libre, no imprime el estado ni rutas.
"""
from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import time

try:  # importado como paquete (pruebas, `python -m`): una sola identidad de módulo
    from .escritor_estado_actualizar_ops4 import (  # noqa: E402
        CODIGOS,
        ESTADO_EN_CURSO,
        ESTADOS_TERMINALES,
        FASES,
        ResultadoEscritura,
        ResultadoLectura,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )
except ImportError:  # instalado como script suelto en /usr/local/lib/zascarr
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    from escritor_estado_actualizar_ops4 import (  # noqa: E402
        CODIGOS,
        ESTADO_EN_CURSO,
        ESTADOS_TERMINALES,
        FASES,
        ResultadoEscritura,
        ResultadoLectura,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )

_RESULTADOS = ESTADOS_TERMINALES
_CODIGO_POR_DEFECTO = "otro"
_CODIGOS = CODIGOS
_FASE_FINAL = FASES[-1]
_FASES_INTERMEDIAS = tuple(fase for fase in FASES if fase not in (FASES[0], FASES[-1]))
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_ID = re.compile(r"[0-9a-f]{32}\Z")
_EXITO_LIMPIO = ("success", "exited", "0")
_PRE_EFECTO_CONTRATO = ("exit-code", "exited", "75")
#: La entrada B2 sale 76 si la reserva no es válida, antes de cualquier efecto.
_PRE_EFECTO_RESERVA = ("exit-code", "exited", "76")


def resultado_final(
    service_result: object, exit_code: object, exit_status: object,
) -> str | None:
    """Tabla pura de A1; `None` si los valores no son cadenas de systemd.

    Es la referencia normativa de la cadena de `ExecStopPost`: solo el éxito
    limpio es `hecha`; el 75 del cerrojo y el 76 de una reserva no vigente son
    `fallida` (ocurren antes de cualquier efecto); el resto es `incierta`
    (H-13: `update.sh` usa 1 antes y después de tocar código/BD, así que no se
    puede distinguir pre de post).
    """
    if not (type(service_result) is str and type(exit_code) is str
            and type(exit_status) is str):
        return None
    if (service_result, exit_code, exit_status) == _EXITO_LIMPIO:
        return "hecha"
    if (service_result, exit_code, exit_status) in (
        _PRE_EFECTO_CONTRATO, _PRE_EFECTO_RESERVA,
    ):
        return "fallida"
    return "incierta"


def _leer_intento(ruta: object) -> str | None:
    """Lee el id de la reserva ligado a esta invocación; `None` si no es válido."""
    try:
        fd = os.open(
            os.fspath(ruta),
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
        )
    except (OSError, TypeError):
        return None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_size > 33
        ):
            return None
        datos = os.read(fd, 33)
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(datos) == 33 and datos.endswith(b"\n"):
        datos = datos[:-1]
    if len(datos) != 32:
        return None
    texto = datos.decode("ascii", "ignore")
    return texto if _ID.fullmatch(texto) else None


def _aviso(mensaje: str) -> int:
    """Devuelve 2 sin escribir el estado; nunca imprime estado, rutas ni datos."""
    print(f"zascarr-estado-actualizar-ops4: {mensaje}", file=sys.stderr)
    return 2


def _sha_valido(valor: str | None) -> bool:
    """Un SHA del contrato es `None` o 40 hexadecimales minúsculas."""
    return valor is None or (type(valor) is str and _SHA.fullmatch(valor) is not None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ruta", required=True)
    parser.add_argument("--resultado")
    parser.add_argument("--fase")
    parser.add_argument("--codigo")
    parser.add_argument("--head0")
    parser.add_argument("--sha-destino")
    parser.add_argument("--sha-actual")
    parser.add_argument("--intento")
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if (args.resultado is None) == (args.fase is None):
        return _aviso("elige un modo: --resultado o --fase, nunca ambos")
    if args.resultado is not None:
        if args.resultado not in _RESULTADOS:
            return _aviso("--resultado debe ser hecha, fallida o incierta")
        if args.codigo is None:
            # La unidad pasa el código mapeado; una invocación manual sin él
            # cierra igualmente con el código cerrado más honesto.
            args.codigo = _CODIGO_POR_DEFECTO
        elif type(args.codigo) is not str or args.codigo not in _CODIGOS:
            return _aviso("--codigo debe ser success:exited:0, exit-code:exited:75 u otro")
        if args.head0 is not None or args.sha_destino is not None or args.sha_actual is not None:
            return _aviso("el cierre terminal no acepta --head0, --sha-destino ni --sha-actual")
        if args.intento is None:
            return _aviso("el cierre terminal exige --intento")
    else:
        if args.fase not in _FASES_INTERMEDIAS:
            return _aviso(
                "--fase debe ser una fase intermedia: preparacion, copia, git, "
                "build, migracion o arranque"
            )
        if args.codigo is not None:
            return _aviso("el modo --fase no acepta --codigo")
        for sha in (args.head0, args.sha_destino, args.sha_actual):
            if not _sha_valido(sha):
                return _aviso("cada SHA debe ser 40 hexadecimales minúsculas")
    id_intento = _leer_intento(args.intento) if args.intento is not None else None
    if args.fase is None and id_intento is None:
        return 0
    lectura, datos = leer_estado_estricto(args.ruta)
    if lectura is not ResultadoLectura.OK or datos is None:
        return 0
    if datos["estado"] in _RESULTADOS:
        return 0
    if args.fase is not None:
        for nombre, valor, fijado in (
            ("--head0", args.head0, datos.get("head0")),
            ("--sha-destino", args.sha_destino, datos.get("sha_destino")),
        ):
            if valor is not None and fijado is not None and valor != fijado:
                return _aviso(f"{nombre} ya está fijado para este intento y no puede cambiar")
    ahora = int(time.time())
    if ahora < datos["inicio_epoch"]:
        # Reloj invertido: el lector lo dará incierta; no se escribe.
        return 0
    propietario = propietario_servicio(args.ruta)
    if args.fase is not None:
        hashes = {}
        if args.head0 is not None:
            hashes["head0"] = args.head0
        if args.sha_destino is not None:
            hashes["sha_destino"] = args.sha_destino
        if args.sha_actual is not None:
            hashes["sha_actual"] = args.sha_actual
        resultado = publicar_transicion(
            args.ruta,
            ESTADO_EN_CURSO,
            ahora=ahora,
            id_=datos["id"],
            inicio_epoch=datos["inicio_epoch"],
            fase=args.fase,
            propietario=propietario,
            **hashes,
        )
    else:
        resultado = publicar_transicion(
            args.ruta,
            args.resultado,
            ahora=ahora,
            id_=id_intento,
            inicio_epoch=datos["inicio_epoch"],
            fase=_FASE_FINAL,
            codigo=args.codigo,
            propietario=propietario,
        )
    return 1 if resultado is ResultadoEscritura.INCIERTO else 0


if __name__ == "__main__":
    sys.exit(main())
