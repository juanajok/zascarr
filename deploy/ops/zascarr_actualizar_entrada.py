#!/usr/bin/env python3
"""Entrada fija de la unidad de actualización OPS4 (B2).

Primera acción: abrir el cerrojo único de operaciones y tomarlo en el
descriptor 9. Si está ocupado sale 75 **sin efectos**. Si lo toma, exige una
reserva vigente (`aceptada`, `id` presente, `inicio` dentro de 300 s), calcula
`head0` y publica `en_curso`/`reservada` antes de `exec` a `update.sh`; el
descriptor 9 se conserva para que `_cerrojo.sh` lo reconozca por
dispositivo:inodo y no cree otro.

No recibe rama, rutas ni comandos del solicitante: la acción es fija. No
ejecuta nada si la reserva no es válida. No es el auxiliar ni el cerrojo de
admisión; el instalador la copia sin activarla y no se habilita en producción.

"""
from __future__ import annotations

import fcntl
import os
import re
import stat
import subprocess
import sys
import time

try:  # importado como paquete (pruebas)
    from .escritor_estado_actualizar_ops4 import (
        ResultadoEscritura,
        ResultadoLectura,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )
except ImportError:  # instalado como script en /usr/local/lib/zascarr
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    from escritor_estado_actualizar_ops4 import (  # noqa: E402
        ResultadoEscritura,
        ResultadoLectura,
        leer_estado_estricto,
        propietario_servicio,
        publicar_transicion,
    )

RUTA_CERROJO = "/run/zascarr-ops.lock"
RESERVA_VIGENCIA_S = 300
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_INVOCACION = re.compile(r"[0-9a-f]{32}\Z")
_CODIGO_BUSY = 75
_CODIGO_INVALIDO = 76


def _fallo(motivo: str) -> int:
    print(f"entrada: {motivo}", file=sys.stderr)
    return _CODIGO_INVALIDO


def ruta_cerrojo() -> str:
    if os.environ.get("ZASCARR_PRUEBAS") == "1" and os.environ.get("OPS_LOCK_FILE"):
        return os.environ["OPS_LOCK_FILE"]
    return RUTA_CERROJO


def _tomar_cerrojo() -> int | None:
    """Abre el cerrojo y lo toma en fd 9; `None` si ya está ocupado."""
    ruta = ruta_cerrojo()
    fd = os.open(ruta, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.set_inheritable(fd, True)
        os.dup2(fd, 9)
        os.set_inheritable(9, True)
        if fd != 9:
            os.close(fd)
        try:
            fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
    except BaseException:
        os.close(fd)
        raise
    return 9


def _marcar_intento(id_: str) -> None:
    """Liga esta invocación de la unidad al id de la reserva (N2)."""
    invocacion = os.environ.get("INVOCATION_ID", "")
    if not _INVOCACION.fullmatch(invocacion):
        raise ValueError("invocación no válida")
    ops4 = os.environ.get("ZASCARR_OPS4_DIR", "/var/lib/zascarr/ops4")
    dir_intentos = os.path.join(ops4, "intentos")
    fd_dir = os.open(
        dir_intentos,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        info = os.fstat(fd_dir)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise ValueError("directorio de intentos no seguro")
        fd = os.open(
            invocacion,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=fd_dir,
        )
        try:
            pendiente = (id_ + "\n").encode("ascii")
            while pendiente:
                escrito = os.write(fd, pendiente)
                if escrito <= 0:
                    raise OSError("escritura incompleta")
                pendiente = pendiente[escrito:]
            os.fsync(fd)
            os.fsync(fd_dir)
        finally:
            os.close(fd)
    finally:
        os.close(fd_dir)


def _head0(repo: str) -> str | None:
    try:
        resultado = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = resultado.stdout.strip()
    return sha if resultado.returncode == 0 and _SHA.fullmatch(sha) else None


def main() -> int:
    repo = os.environ.get("ZASCARR_REPO", "/opt/zascarr/zascarr")
    ops = os.environ.get("ZASCARR_OPS_DIR", "/var/lib/zascarr/ops")
    ruta_estado = os.path.join(ops, "actualizar-status.json")
    try:
        if _tomar_cerrojo() is None:
            return _CODIGO_BUSY
    except OSError as exc:
        return _fallo(f"cerrojo: {exc}")
    lectura, datos = leer_estado_estricto(ruta_estado)
    if lectura is not ResultadoLectura.OK or datos is None:
        return _fallo(f"estado: {lectura}")
    if (
        datos.get("schema") != 2
        or datos.get("estado") != "aceptada"
        or datos.get("fase") != "aceptada"
        or not isinstance(datos.get("id"), str)
    ):
        return _fallo("reserva: no vigente")
    ahora = int(time.time())
    inicio = datos.get("inicio_epoch")
    if (
        type(inicio) is not int
        or inicio > ahora
        or ahora - inicio > RESERVA_VIGENCIA_S
    ):
        return _fallo("reserva: inicio fuera de plazo")
    try:
        _marcar_intento(datos["id"])
    except (OSError, ValueError):
        return _fallo("intento: no se pudo marcar")
    head0 = _head0(repo)
    if head0 is None:
        return _fallo("head0: git")
    resultado = publicar_transicion(
        ruta_estado,
        "en_curso",
        ahora=ahora,
        id_=datos["id"],
        inicio_epoch=inicio,
        fase="reservada",
        head0=head0,
        propietario=propietario_servicio(ruta_estado),
    )
    if resultado is not ResultadoEscritura.OK:
        return _fallo(f"transicion: {resultado}")
    os.execv(
        "/bin/bash",
        ["bash", os.path.join(repo, "scripts", "update.sh"), "--rama", "main"],
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
