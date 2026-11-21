"""Escritor aislado de estado de actualización; no ejecuta ni autoriza nada.

Escribe un JSON canónico en un temporal exclusivo del mismo directorio,
sincroniza el archivo, renombra y sincroniza el directorio. Ante cualquier
error devuelve INCIERTO: no se puede deducir si el nombre antiguo o el nuevo
sobrevivirá a un corte, y el llamador no debe tratarlo como éxito. Un fsync
correcto tampoco demuestra que el hardware o el filesystem respeten flush.
No comprueba propiedad del directorio, no adquiere cerrojos y no se conecta a
la UI ni al auxiliar.

H-5: el fichero no se publica como `0600 root:root`. La app corre con
PUID:PGID sobre un montaje `ro`; para que pueda leer el estado, el temporal se
publica `0640` y, cuando el llamador lo indica, con dueño `root:<grupo>`
(`propietario`). El grupo se obtiene del directorio `ops` (`0750 root:<grupo>`
por el instalador), no de una ruta ni de una cadena libre.

La guarda de monotonía (`publicar_transicion`) nunca pisa un estado terminal,
no baja `actualizado_epoch` y no cambia `id` ni `inicio_epoch`; devuelve
cerrado (`INVALIDO`/`INCIERTO`) y nunca lanza.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import secrets
import stat
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

MAX_BYTES = 4096
#: La app lee el estado con PUID:PGID sobre un montaje `ro` (H-5).
MODO_ESTADO = 0o640
_ESCRITURA_AJENA = stat.S_IWGRP | stat.S_IWOTH
_ID = re.compile(r"[0-9a-f]{32}\Z")
_CAMPOS_ESTADO = {"schema", "id", "estado", "inicio_epoch", "actualizado_epoch"}
_ESTADOS = {"aceptada", "en_curso", "hecha", "fallida", "incierta"}
_TERMINALES = {"hecha", "fallida", "incierta"}


class ResultadoEscritura(StrEnum):
    OK = "ok"
    INCIERTO = "incierto"
    INVALIDO = "invalido"


class ResultadoLectura(StrEnum):
    OK = "ok"
    AUSENTE = "ausente"
    INVALIDO = "invalido"


def _reemplazar(origen: str, destino: str, dir_fd: int) -> None:
    os.replace(origen, destino, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)


def _objeto_sin_duplicados(pares: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pares:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def propietario_servicio(ruta: str | Path) -> tuple[int, int] | None:
    """Dueño `root:<grupo del directorio ops>` cuando el escritor corre como root.

    En pruebas o en un contexto sin privilegios devuelve `None`: el fichero se
    publica igualmente `0640`, pero no se intenta un `fchown` que fallaría.
    """
    if os.geteuid() != 0:
        return None
    try:
        grupo = os.stat(Path(ruta).parent).st_gid
    except OSError:
        return None
    return (0, grupo)


def escribir_estado(
    ruta: str | Path,
    datos: object,
    *,
    fsync: Callable[[int], None] = os.fsync,
    replace: Callable[[str, str, int], None] = _reemplazar,
    propietario: tuple[int, int] | None = None,
) -> ResultadoEscritura:
    """Intenta publicar una instantánea; solo OK si todas las fases terminan."""
    try:
        destino = Path(ruta)
        contenido = _serializar(datos)
        directorio = destino.parent
        fd_dir = os.open(directorio, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, TypeError, ValueError):
        return ResultadoEscritura.INVALIDO

    temporal = None
    fd = None
    try:
        try:
            info = os.fstat(fd_dir)
            if not stat.S_ISDIR(info.st_mode):
                return ResultadoEscritura.INVALIDO
            temporal = f".{destino.name}.tmp-{secrets.token_hex(8)}"
            fd = os.open(
                temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd_dir
            )
            _escribir_todo(fd, contenido)
            os.fchmod(fd, MODO_ESTADO)
            if propietario is not None:
                uid, gid = propietario
                os.fchown(fd, uid, gid)
            fsync(fd)
        except (OSError, TypeError, ValueError):
            return ResultadoEscritura.INCIERTO
        finally:
            if fd is not None:
                os.close(fd)
                fd = None
        try:
            replace(temporal, destino.name, fd_dir)
            temporal = None
            fsync(fd_dir)
        except (OSError, TypeError, ValueError):
            return ResultadoEscritura.INCIERTO
        return ResultadoEscritura.OK
    finally:
        if temporal is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporal, dir_fd=fd_dir)
        os.close(fd_dir)


def leer_estado_estricto(
    ruta: str | Path,
) -> tuple[ResultadoLectura, dict[str, object] | None]:
    """Lee el esquema 1 sin seguir enlaces y sin abrir FIFO/dispositivos.

    Devuelve `AUSENTE` si el fichero no existe, `INVALIDO` ante cualquier
    anomalía (tipo, tamaño, permisos de escritura ajenos, JSON, esquema o
    tipos) y `OK` con el objeto validado. No compara épocas con el reloj: la
    detección de reloj invertido es del llamador.
    """
    try:
        fd = os.open(
            Path(ruta), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        )
    except FileNotFoundError:
        return ResultadoLectura.AUSENTE, None
    except OSError:
        return ResultadoLectura.INVALIDO, None
    try:
        antes = os.fstat(fd)
        if not stat.S_ISREG(antes.st_mode) or antes.st_size > MAX_BYTES:
            return ResultadoLectura.INVALIDO, None
        if stat.S_IMODE(antes.st_mode) & _ESCRITURA_AJENA:
            return ResultadoLectura.INVALIDO, None
        datos = bytearray()
        while len(datos) <= MAX_BYTES:
            bloque = os.read(fd, MAX_BYTES + 1 - len(datos))
            if not bloque:
                break
            datos.extend(bloque)
        despues = os.fstat(fd)
        if (
            len(datos) > MAX_BYTES
            or len(datos) != despues.st_size
            or (antes.st_size, antes.st_mtime_ns, antes.st_ctime_ns)
            != (despues.st_size, despues.st_mtime_ns, despues.st_ctime_ns)
        ):
            return ResultadoLectura.INVALIDO, None
    except OSError:
        return ResultadoLectura.INVALIDO, None
    finally:
        os.close(fd)
    try:
        obj = json.loads(
            bytes(datos).decode("utf-8"),
            object_pairs_hook=_objeto_sin_duplicados,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return ResultadoLectura.INVALIDO, None
    if type(obj) is not dict or set(obj) != _CAMPOS_ESTADO:
        return ResultadoLectura.INVALIDO, None
    if type(obj["schema"]) is not int or obj["schema"] != 1:
        return ResultadoLectura.INVALIDO, None
    if type(obj["id"]) is not str or not _ID.fullmatch(obj["id"]):
        return ResultadoLectura.INVALIDO, None
    if type(obj["estado"]) is not str or obj["estado"] not in _ESTADOS:
        return ResultadoLectura.INVALIDO, None
    inicio, actualizado = obj["inicio_epoch"], obj["actualizado_epoch"]
    if (
        type(inicio) is not int
        or type(actualizado) is not int
        or not 0 <= inicio <= actualizado < 2**63
    ):
        return ResultadoLectura.INVALIDO, None
    return ResultadoLectura.OK, obj


def publicar_transicion(
    ruta: str | Path,
    estado: str,
    *,
    ahora: int,
    id_: str | None = None,
    inicio_epoch: int | None = None,
    propietario: tuple[int, int] | None = None,
    fsync: Callable[[int], None] = os.fsync,
    replace: Callable[[str, str, int], None] = _reemplazar,
) -> ResultadoEscritura:
    """Guarda de monotonía para el auxiliar y el finalizador.

    Solo escribe si hay un estado válido previo (nunca inventa ni repara uno
    corrupto), si el intento que escribe es el mismo (`id_`/`inicio_epoch`),
    si el estado actual no es terminal y si `ahora` no hace retroceder el
    reloj. El terminal no se toca: devuelve `INVALIDO` sin escribir.
    """
    if type(estado) is not str or estado not in _ESTADOS:
        return ResultadoEscritura.INVALIDO
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return ResultadoEscritura.INVALIDO
    lectura, actual = leer_estado_estricto(ruta)
    if lectura is not ResultadoLectura.OK or actual is None:
        return ResultadoEscritura.INVALIDO
    if actual["estado"] in _TERMINALES:
        return ResultadoEscritura.INVALIDO
    if id_ is not None and id_ != actual["id"]:
        return ResultadoEscritura.INVALIDO
    if inicio_epoch is not None and inicio_epoch != actual["inicio_epoch"]:
        return ResultadoEscritura.INVALIDO
    if ahora < actual["inicio_epoch"] or ahora < actual["actualizado_epoch"]:
        return ResultadoEscritura.INVALIDO
    nuevo = {**actual, "estado": estado, "actualizado_epoch": ahora}
    return escribir_estado(
        ruta, nuevo, fsync=fsync, replace=replace, propietario=propietario,
    )


def _serializar(datos: object) -> bytes:
    if not isinstance(datos, dict):
        raise ValueError
    texto = json.dumps(
        datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8") + b"\n"
    if len(texto) > MAX_BYTES:
        raise ValueError
    return texto


def _escribir_todo(fd: int, datos: bytes) -> None:
    vista = memoryview(datos)
    while vista:
        escritos = os.write(fd, vista)
        if escritos <= 0:
            raise OSError("escritura incompleta")
        vista = vista[escritos:]
