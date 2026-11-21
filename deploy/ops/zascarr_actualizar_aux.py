#!/usr/bin/env python3
"""Auxiliar privilegiado y separado de la actualización OPS4; no instalado.

Socket-activado por `zascarr-actualizar.socket`, lee una línea v4, verifica
firma, frescura, testigo y consumo durable, comprueba el cerrojo y ordena
iniciar la unidad fija `zascarr-actualizar.service`. No recibe rama, rutas ni
shell; no registra el testigo ni la contraseña. No se instala ni se habilita en
producción desde este cambio.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
import subprocess
import sys
import time

try:  # importado como paquete (pruebas): una sola identidad de módulo
    from .escritor_estado_actualizar_ops4 import (  # noqa: E402
        ResultadoEscritura,
        escribir_estado,
        propietario_servicio,
        publicar_transicion,
    )
    from .protocolo_actualizar_v4_ops4 import (  # noqa: E402
        decodificar_autorizacion,
        parsear,
        verificar_firma,
    )
    from .registro_repeticiones_ops4 import (  # noqa: E402
        abrir_directorio_autorizaciones,
        crear_reclamador_durable,
    )
    from .verificador_autorizacion_ops4 import (  # noqa: E402
        CodigoAutorizacion,
        verificar_autorizacion,
    )
except ImportError:  # instalado como script suelto en /usr/local/lib/zascarr
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    from escritor_estado_actualizar_ops4 import (  # noqa: E402
        ResultadoEscritura,
        escribir_estado,
        propietario_servicio,
        publicar_transicion,
    )
    from protocolo_actualizar_v4_ops4 import (  # noqa: E402
        decodificar_autorizacion,
        parsear,
        verificar_firma,
    )
    from registro_repeticiones_ops4 import (  # noqa: E402
        abrir_directorio_autorizaciones,
        crear_reclamador_durable,
    )
    from verificador_autorizacion_ops4 import (  # noqa: E402
        CodigoAutorizacion,
        verificar_autorizacion,
    )

UNIDAD = "zascarr-actualizar.service"
RUTA_CERROJO = "/run/zascarr-ops.lock"
PATH_FIJO = "/usr/sbin:/usr/bin:/sbin:/bin"
TIEMPO_SYSTEMCTL_S = 5
TOLERANCIA_S = 120
MAX_LINEA = 4096


class Respuesta:
    def __init__(self, resultado: str, codigo: str, id_: str | None = None) -> None:
        self.resultado = resultado
        self.codigo = codigo
        self.id = id_

    def linea(self) -> bytes:
        return json.dumps(
            {"v": 4, "id": self.id, "resultado": self.resultado, "codigo": self.codigo},
            separators=(",", ":"),
        ).encode("ascii") + b"\n"


def rechazo(codigo: str, id_: str | None = None) -> Respuesta:
    return Respuesta("rechazada", codigo, id_)


def procesar(
    linea: bytes, *, clave: bytes, ahora: int,
    reclamar_uso, iniciar, cerrojo_ocupado, escribir=None, transicionar=None,
) -> Respuesta:
    """Orden: esquema → firma → frescura → cerrojo → testigo → consumo → estado → inicio.

    T-17: solo se escribe `aceptada` (con el consumo durable ya reclamado);
    tras `systemctl start` no se escribe ninguna instantánea más. Si el start
    falla se intenta `fallida` por la guarda de monotonía, que no pisa un
    terminal escrito por el finalizador.
    """
    if transicionar is None:
        transicionar = escribir
    if type(clave) is not bytes or len(clave) != 32:
        return rechazo("no_disponible")
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return rechazo("no_disponible")
    objeto = parsear(linea)
    if objeto is None:
        return rechazo("esquema_invalido")
    id_ = objeto["id"]
    if not verificar_firma(clave, objeto):
        return rechazo("firma_invalida", id_)
    if abs(objeto["creada"] - ahora) > TOLERANCIA_S:
        return rechazo("caducada", id_)
    try:
        if cerrojo_ocupado():
            return rechazo("operacion_en_curso", id_)
    except Exception:  # noqa: BLE001
        return rechazo("no_disponible", id_)
    testigo = decodificar_autorizacion(objeto["autorizacion"])
    if testigo is None:
        return rechazo("autorizacion_invalida", id_)
    resultado = verificar_autorizacion(
        testigo, clave=clave, ahora=ahora, reclamar_uso=reclamar_uso, id_esperado=id_,
    )
    if resultado is CodigoAutorizacion.CADUCADA:
        return rechazo("caducada", id_)
    if resultado is CodigoAutorizacion.REPETIDA:
        return rechazo("repetida", id_)
    if resultado is CodigoAutorizacion.NO_DISPONIBLE:
        return rechazo("no_disponible", id_)
    if resultado is not CodigoAutorizacion.ACEPTADA:
        return rechazo("autorizacion_invalida", id_)
    inicial = {
        "schema": 1, "id": id_, "estado": "aceptada",
        "inicio_epoch": ahora, "actualizado_epoch": ahora,
    }
    if escribir is not None and escribir(inicial) != ResultadoEscritura.OK:
        return rechazo("no_disponible", id_)
    try:
        iniciada = iniciar(UNIDAD)
    except Exception:  # noqa: BLE001
        return rechazo("no_disponible", id_)
    if iniciada is not True:
        if transicionar is not None:
            transicionar({**inicial, "estado": "fallida", "actualizado_epoch": ahora})
        return rechazo("no_disponible", id_)
    # T-17: no se escribe `en_curso` después del start. El finalizador cierra;
    # una instantánea posterior podría pisar un terminal si la unidad acaba antes.
    return Respuesta("aceptada", "aceptada", id_)


def _leer_clave(ruta: str) -> bytes | None:
    try:
        fd = os.open(ruta, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) != 0o440
            or info.st_size not in (64, 65)
        ):
            return None
        datos = os.read(fd, 66)
    except OSError:
        return None
    finally:
        os.close(fd)
    if len(datos) == 65 and datos.endswith(b"\n"):
        datos = datos[:-1]
    if len(datos) != 64:
        return None
    try:
        clave = bytes.fromhex(datos.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        return None
    return clave if len(clave) == 32 else None


def _cerrojo_ocupado() -> bool:
    try:
        fd = os.open(RUTA_CERROJO, os.O_RDONLY)
    except FileNotFoundError:
        return False
    except OSError:
        return True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    finally:
        os.close(fd)


def _iniciar(unidad: str) -> bool:
    try:
        resultado = subprocess.run(
            ["systemctl", "start", "--no-block", unidad],
            env={"PATH": PATH_FIJO}, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=TIEMPO_SYSTEMCTL_S, check=False, close_fds=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return resultado.returncode == 0


def _leer_linea() -> bytes:
    datos = b""
    while len(datos) <= MAX_LINEA:
        bloque = os.read(0, MAX_LINEA + 1 - len(datos))
        if not bloque:
            break
        datos += bloque
        if b"\n" in datos:
            break
    return datos


def main() -> int:
    dir_ops = os.environ.get("ZASCARR_OPS_DIR", "/var/lib/zascarr/ops")
    dir_ops4 = os.environ.get("ZASCARR_OPS4_DIR", "/var/lib/zascarr/ops4")
    ruta_estado = os.path.join(dir_ops, "actualizar-status.json")
    clave = _leer_clave(os.path.join(dir_ops, "actualizar.key"))
    linea = _leer_linea()
    reclamar = None
    fd_dir = None
    try:
        fd_dir = abrir_directorio_autorizaciones(
            os.path.join(dir_ops4, "consumidos"), uid_esperado=0, modo_esperado=0o700,
        )
        reclamar = crear_reclamador_durable(fd_dir)
        propietario = propietario_servicio(ruta_estado)
        respuesta = procesar(
            linea, clave=clave or b"", ahora=int(time.time()),
            reclamar_uso=reclamar, iniciar=_iniciar, cerrojo_ocupado=_cerrojo_ocupado,
            escribir=lambda datos: escribir_estado(
                ruta_estado, datos, propietario=propietario,
            ),
            transicionar=lambda datos: publicar_transicion(
                ruta_estado, datos["estado"],
                ahora=datos["actualizado_epoch"], id_=datos["id"],
                inicio_epoch=datos["inicio_epoch"], propietario=propietario,
            ),
        )
    except Exception:  # noqa: BLE001 — nunca se devuelve un éxito dudoso
        respuesta = rechazo("no_disponible")
    finally:
        if fd_dir is not None:
            with contextlib.suppress(OSError):
                os.close(fd_dir)
    with contextlib.suppress(OSError):
        os.write(1, respuesta.linea())
    return 0


if __name__ == "__main__":
    sys.exit(main())
