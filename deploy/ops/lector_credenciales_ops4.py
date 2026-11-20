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

import re
import subprocess
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


class LectorCredenciales:
    """Orden fija; el llamador puede inyectar la ejecución para probar fallos."""

    def __init__(
        self,
        ejecutar: Callable[..., Any] = subprocess.run,
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
