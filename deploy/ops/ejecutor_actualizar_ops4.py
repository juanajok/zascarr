"""Ejecutor aislado de la actualización; no está conectado ni instalado.

Construye una orden fija sobre el actualizador del host y clasifica el
resultado. No se invoca desde la UI, el auxiliar ni systemd en este tramo.
Un código 0 solo significa que el proceso terminó; no prueba salud, migración
correcta ni éxito del despliegue. Un timeout o error es incierto, nunca
ausencia de efectos. La frontera de confianza de lo que ejecuta `update.sh`
tras el fetch sigue pendiente de revisión.

Las pruebas inyectan el lanzador; este módulo no ejecuta nada por sí solo.
"""
from __future__ import annotations

import subprocess
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path

REPO_FIJO = Path("/opt/zascarr/zascarr")
RAMA_FIJA = "main"
TIEMPO_MAX_S = 5400
PATH_FIJO = "/usr/sbin:/usr/bin:/sbin:/bin"


class ResultadoEjecucion(StrEnum):
    TERMINADO = "terminado"
    FALLIDO = "fallido"
    INCIERTO = "incierto"


def construir_orden() -> tuple[str, ...]:
    """Orden fija; no acepta rama, shell, argumentos libres ni entorno del cliente."""
    repo = REPO_FIJO
    if not repo.is_absolute() or ".." in repo.parts:
        raise ValueError("ruta de instalación no válida")
    return ("/bin/bash", str(repo / "scripts" / "update.sh"), "--rama", RAMA_FIJA)


def ejecutar(
    orden: Sequence[str],
    *,
    lanzar: Callable[..., object] = subprocess.run,
) -> ResultadoEjecucion:
    """Lanza una orden ya construida y clasifica sin probar el éxito funcional."""
    if not isinstance(orden, tuple) or orden != construir_orden():
        return ResultadoEjecucion.INCIERTO
    try:
        resultado = lanzar(
            list(orden),
            env={
                "PATH": PATH_FIJO,
                "HOME": "/root",
                "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=TIEMPO_MAX_S,
            check=False,
            close_fds=True,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        return ResultadoEjecucion.INCIERTO
    except Exception:  # noqa: BLE001 — un fallo del lanzador no autoriza
        return ResultadoEjecucion.INCIERTO
    codigo = getattr(resultado, "returncode", None)
    if type(codigo) is not int:
        return ResultadoEjecucion.INCIERTO
    if codigo == 0:
        return ResultadoEjecucion.TERMINADO
    return ResultadoEjecucion.FALLIDO
