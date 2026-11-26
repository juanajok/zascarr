"""Consumo durable de un solo uso de OPS4; no instalado ni conectado.

Un directorio ya provisionado por el host contiene marcas permanentes por ID.
Este módulo no es la reserva de operación, no adquiere el cerrojo de
copia/restauración y no autoriza lanzar nada. La retención/capacidad y la
identidad del directorio siguen pendientes: no se borran marcas automáticamente.
Un disco lleno deniega.

Hay dos espacios de nombres deliberadamente separados:

- `reclamar_autorizacion` crea `autorizacion-<id>` en el directorio **dedicado**
  de autorizaciones (persistente, root `0700`); es el consumo que exige el
  verificador para la ruta app→host (`crear_reclamador_durable`).
- `reclamar_id` conserva el nombre experimental `solicitud-<id>` del registro de
  peticiones v3. No es el namespace de la autorización: una marca de uno no
  satisface ni consume la del otro, y comparten el mismo ID a propósito.

Ninguno de los dos usa el directorio temporal del auxiliar ni su purga: ese
directorio es memoria RAM (tmpfs) y se purga, lo que reabriría la ventana de
repetición.
"""
from __future__ import annotations

import contextlib
import os
import re
import stat
from collections.abc import Callable

_ID = re.compile(r"[0-9a-f]{32}\Z")

#: Prefijo del consumo durable de autorizaciones; distinto de `solicitud-<id>`.
PREFIJO_AUTORIZACION = "autorizacion-"
#: Prefijo del registro experimental de peticiones v3; no usar para autorizar.
PREFIJO_SOLICITUD_V3 = "solicitud-"


class RegistroNoDisponibleError(Exception):
    """Persistencia no acreditada; no autoriza efectos ni reutilización del ID."""


def _nombre(id_: object, prefijo: str) -> str:
    if not isinstance(id_, str) or not _ID.fullmatch(id_):
        raise RegistroNoDisponibleError("identificador no válido")
    return f"{prefijo}{id_}"


def _reclamar_marca(
    nombre: str,
    *,
    directorio_fd: object,
    sincronizar: Callable[[int], None],
) -> bool:
    """Crea `nombre` de forma exclusiva y la confirma con dos `fsync`."""
    if type(directorio_fd) is not int or directorio_fd < 0:
        raise RegistroNoDisponibleError("directorio no disponible")
    directory = None
    marker = None
    try:
        directory = os.dup(directorio_fd)
        info = os.fstat(directory)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise RegistroNoDisponibleError("directorio no seguro")
        try:
            marker = os.open(
                nombre,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600, dir_fd=directory,
            )
        except FileExistsError:
            return False
        # La propia existencia de la marca vacía consume el ID. No contiene
        # contraseña, hash, firma ni estado de la operación.
        if sincronizar(marker) is not None or sincronizar(directory) is not None:
            raise RegistroNoDisponibleError("sincronización no acreditada")
        closing, marker = marker, None
        os.close(closing)
        closing, directory = directory, None
        os.close(closing)
        return True
    except RegistroNoDisponibleError:
        raise
    except Exception:
        raise RegistroNoDisponibleError("persistencia no disponible") from None
    finally:
        # No deshacer una creación aunque falle fsync: su resultado es incierto.
        # close no reintenta ni modifica el nombre de la marca.
        if marker is not None:
            with contextlib.suppress(OSError):
                os.close(marker)
        if directory is not None:
            with contextlib.suppress(OSError):
                os.close(directory)


def reclamar_autorizacion(
    id_: object,
    *,
    directorio_fd: int,
    sincronizar: Callable[[int], None] = os.fsync,
) -> bool:
    """Consume una autorización creando `autorizacion-<id>` en su directorio.

    `True` solo tras creación exclusiva y `fsync` de marca y directorio; `False`
    si el nombre ya existe (también enlace, FIFO, directorio o marca incompleta).
    Cualquier otro fallo eleva `RegistroNoDisponibleError` sin secretos. El
    llamador aporta el descriptor del directorio dedicado (persistente, root
    `0700`, nunca un tmpfs ni el registro de peticiones v3) y no se aceptan
    rutas de la petición.
    """
    return _reclamar_marca(
        _nombre(id_, PREFIJO_AUTORIZACION),
        directorio_fd=directorio_fd,
        sincronizar=sincronizar,
    )


def reclamar_intento(
    id_: object,
    *,
    directorio_fd: int,
    sincronizar: Callable[[int], None] = os.fsync,
) -> bool:
    """Crea la marca de intento `<id>` en el directorio dedicado `intentos`.

    Es exclusiva (`O_EXCL` + dos `fsync`) y no contiene secretos: solo su
    existencia acredita que la petición llegó a reserva. No sustituye al
    consumo de la autorización; un fallo de sincronización eleva
    `RegistroNoDisponibleError` sin acreditar el intento.
    """
    return _reclamar_marca(
        _nombre(id_, ""),
        directorio_fd=directorio_fd,
        sincronizar=sincronizar,
    )


def reclamar_id(
    id_: object,
    *,
    directorio_fd: int,
    sincronizar: Callable[[int], None] = os.fsync,
) -> bool:
    """Registro experimental v3 (`solicitud-<id>`), conservado sin cambios.

    No es el namespace de la autorización (AC-AUT-07): sirve al protocolo de
    peticiones v3 y no debe conectarse al verificador de autorizaciones.
    """
    return _reclamar_marca(
        _nombre(id_, PREFIJO_SOLICITUD_V3),
        directorio_fd=directorio_fd,
        sincronizar=sincronizar,
    )


def _abrir_directorio(
    ruta: object,
    *,
    uid_esperado: int,
    modo_esperado: int = 0o700,
) -> int:
    """Abre un directorio durable dedicado y acredita propietario y modo."""
    if type(uid_esperado) is not int or not 0 <= uid_esperado < 2**32:
        raise RegistroNoDisponibleError("propietario no acreditado")
    if type(modo_esperado) is not int or modo_esperado != 0o700:
        raise RegistroNoDisponibleError("modo no acreditado")
    try:
        path = os.fspath(ruta)
        fd = os.open(
            path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
    except (OSError, TypeError, ValueError):
        raise RegistroNoDisponibleError("directorio no disponible") from None
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != uid_esperado
            or stat.S_IMODE(info.st_mode) != modo_esperado
        ):
            raise RegistroNoDisponibleError("directorio no seguro")
        return fd
    except BaseException:
        os.close(fd)
        raise


def abrir_directorio_autorizaciones(
    ruta: object,
    *,
    uid_esperado: int,
    modo_esperado: int = 0o700,
) -> int:
    """Abre el directorio durable de autorizaciones y acredita su identidad.

    No lo crea ni lo repara. Exige `0700`, sin escritura de grupo/otros, y un
    `uid` explícito; no sigue enlaces. El llamador debe usar el descriptor para
    `reclamar_autorizacion`/`crear_reclamador_durable` y cerrarlo al terminar.
    Este módulo no demuestra que la ruta sea la provista por el instalador.
    """
    return _abrir_directorio(
        ruta, uid_esperado=uid_esperado, modo_esperado=modo_esperado,
    )


def abrir_directorio_intentos(
    ruta: object,
    *,
    uid_esperado: int,
    modo_esperado: int = 0o700,
) -> int:
    """Abre el directorio dedicado `intentos` con las mismas garantías."""
    return _abrir_directorio(
        ruta, uid_esperado=uid_esperado, modo_esperado=modo_esperado,
    )


def crear_reclamador_durable(
    directorio_fd: int,
    *,
    sincronizar: Callable[[int], None] = os.fsync,
) -> Callable[[str], bool]:
    """Devuelve el callback de consumo único que exige el verificador del host.

    El directorio debe ser el dedicado y persistente de autorizaciones, abierto
    por un llamador de confianza; este módulo no lo crea ni comprueba su ruta.
    Las excepciones suben al verificador, que las convierte en `no_disponible`;
    un fallo nunca se interpreta como consumo libre.
    """
    def reclamar(id_: str) -> bool:
        return reclamar_autorizacion(
            id_, directorio_fd=directorio_fd, sincronizar=sincronizar,
        )

    return reclamar
