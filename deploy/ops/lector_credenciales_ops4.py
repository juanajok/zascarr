"""Lector aislado de credenciales de la BD para OPS4; no se conecta al auxiliar.

Construye una orden fija de solo lectura (`docker exec zascarr-db psql`) y
valida su salida acotada. El ejecutor se inyecta para pruebas; el módulo no
abre sockets, no usa el socket del auxiliar ni inicia unidades. El usuario y
la base se validan mediante una lista de caracteres y nunca se aceptan de la
petición web. No registra la contraseña ni el hash.

Este módulo **no demuestra** que el contenedor/BD sea el de la instalación
autorizada: esa identidad y los permisos del host deben comprobarse aparte.
"""
from __future__ import annotations

import contextlib
import os
import re
import selectors
import signal
import subprocess
import time
from collections.abc import Callable
from typing import Any

PATH_FIJO = "/usr/sbin:/usr/bin:/sbin:/bin"
DOCKER_FIJO = "/usr/bin/docker"
DB_USER_POR_DEFECTO = "comics_admin"
DB_NAME_POR_DEFECTO = "zascarr"
MAX_SALIDA = 4096
TIEMPO_S = 8
_NOMBRE = re.compile(r"[A-Za-z0-9_]{1,64}\Z")
_CONSULTA = (
    "select coalesce((select values->>'auth_mode' from runtime_settings where id=1),'')"
    "||'|'||coalesce((select values->>'auth_password_hash' from runtime_settings where id=1),'')"
)


def _ejecutar_acotado(
    argv: list[str], *, env: dict[str, str], stdin: int, stdout: int,
    stderr: int, timeout: float, check: bool, close_fds: bool,
) -> subprocess.CompletedProcess[bytes]:
    """Lee como máximo MAX_SALIDA+1 bytes y mata el cliente local si excede límites.

    No equivale a cancelar una consulta ya enviada al daemon Docker. No usa
    communicate(): un productor ilimitado no puede agotar la memoria del lector.
    El plazo cubre lectura, EOF y espera normal del cliente. La creación y la
    recogida tras SIGKILL dependen del kernel; no es un límite de tiempo real.
    """
    if check or stdout != subprocess.PIPE:
        raise ValueError("configuración de ejecución no admitida")
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        argv, env=env, stdin=stdin, stdout=stdout, stderr=stderr,
        close_fds=close_fds, start_new_session=True,
    ) as process:
        finished = False
        try:
            assert process.stdout is not None
            output = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise subprocess.TimeoutExpired(argv, timeout)
                    chunk = os.read(process.stdout.fileno(), MAX_SALIDA + 1 - len(output))
                    if not chunk:
                        break
                    output.extend(chunk)
                    if len(output) > MAX_SALIDA:
                        raise ValueError("salida del cliente por encima del límite")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout)
            code = process.wait(timeout=remaining)
            finished = True
            return subprocess.CompletedProcess(argv, code, bytes(output))
        finally:
            # Limpia también descendientes que hayan heredado el pipe. El grupo
            # es exclusivo del hijo, nunca el grupo del auxiliar o de pytest.
            if not finished:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            process.wait()


class LectorCredenciales:
    """Orden fija; el llamador puede inyectar la ejecución para probar fallos."""

    def __init__(
        self,
        ejecutar: Callable[..., Any] = _ejecutar_acotado,
        *,
        db_user: str = DB_USER_POR_DEFECTO,
        db_name: str = DB_NAME_POR_DEFECTO,
    ) -> None:
        if not _NOMBRE.fullmatch(db_user) or not _NOMBRE.fullmatch(db_name):
            raise ValueError("identidad de BD no válida")
        self._ejecutar = ejecutar
        self.argv = [
            DOCKER_FIJO, "exec", "zascarr-db", "psql",
            "-U", db_user, "-d", db_name, "-At",
            "-v", "ON_ERROR_STOP=1", "-c", _CONSULTA,
        ]

    def leer(self) -> tuple[str, str] | None:
        """Devuelve (modo, hash) o None; cualquier duda falla cerrada."""
        try:
            resultado = self._ejecutar(
                self.argv,
                env={"PATH": PATH_FIJO, "DOCKER_CONFIG": "/run/zascarr-ops/docker"},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=TIEMPO_S, check=False,
                close_fds=True,
            )
        except Exception:  # noqa: BLE001 — un fallo del host no autoriza
            return None
        if getattr(resultado, "returncode", None) != 0:
            return None
        salida = getattr(resultado, "stdout", None)
        if not isinstance(salida, bytes) or len(salida) > MAX_SALIDA:
            return None
        try:
            linea = salida.decode("utf-8").strip()
        except UnicodeDecodeError:
            return None
        if "\n" in linea or "\r" in linea:
            return None
        modo, separador, hash_ = linea.partition("|")
        if not separador or not modo or not hash_:
            return None
        return modo, hash_
