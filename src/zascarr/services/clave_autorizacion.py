"""Lectura estricta de la clave dedicada de autorización; no está conectada.

La app (o el host) recibe la ruta de una clave **dedicada** de 32 bytes, nunca
la clave de grupo de OPS1/OPS2. Este módulo comprueba propietario, modo, tipo de
fichero y formato hexadecimal antes de devolverla, sin seguir enlaces. No crea
la clave, no la provisiona, no la registra y no la conecta a la web.
"""
from __future__ import annotations

import os
import stat


def leer_clave_autorizacion(
    ruta: object,
    *,
    uid_esperado: int,
    modo_esperado: int = 0o440,
) -> bytes:
    """Devuelve 32 bytes o lanza `ValueError` sin datos sensibles.

    `uid_esperado` es obligatorio para que el llamador no olvide acreditar al
    propietario. `modo_esperado` debe ser exactamente uno de los modos previstos
    (por defecto `0440`: root y grupo de la app, sin escritura). El fichero debe
    ser regular, de 64 caracteres hex o 65 con un único LF final. La lectura usa
    `O_NOFOLLOW|O_NONBLOCK` y se limita a 66 bytes; un FIFO o dispositivo se
    rechaza tras `fstat`, sin bloquear.
    """
    if type(uid_esperado) is not int or not 0 <= uid_esperado < 2**32:
        raise ValueError("clave no disponible")
    if type(modo_esperado) is not int or modo_esperado not in (0o400, 0o440):
        raise ValueError("clave no disponible")
    try:
        path = os.fspath(ruta)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except (OSError, TypeError, ValueError):
        raise ValueError("clave no disponible") from None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != uid_esperado
            or stat.S_IMODE(info.st_mode) != modo_esperado
            or info.st_size not in (64, 65)
        ):
            raise ValueError("clave no disponible")
        datos = os.read(fd, 66)
    except OSError:
        raise ValueError("clave no disponible") from None
    finally:
        os.close(fd)
    if len(datos) == 65 and datos.endswith(b"\n"):
        datos = datos[:-1]
    if len(datos) != 64:
        raise ValueError("clave no disponible")
    try:
        clave = bytes.fromhex(datos.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("clave no disponible") from None
    if len(clave) != 32:
        raise ValueError("clave no disponible")
    return clave
