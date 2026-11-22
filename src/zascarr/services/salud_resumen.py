"""Resumen cacheado de la última comprobación de salud (UXA-08d, #1219).

El menú (punto de aviso sobre «Estado» o «Más») no puede sondear servicios cada 30 s: lee lo
que la comprobación que ya existe (`GET /api/health`, que llama el HEALTHCHECK de Docker cada
30 s y la pantalla Estado) dejó en la última pasada. Solo se guarda el veredicto global
(`healthy` / `degraded` / `unhealthy`) y cuándo se obtuvo: ningún detalle, ruta ni mensaje.

Un resumen viejo no se cree: pasado `EDAD_MAXIMA_S` el punto no se enciende (no se inventa un
problema ni se mantiene uno que quizá ya no existe). Vive en el proceso (un solo worker, ADR-0011);
tras un reinicio no hay resumen hasta la primera comprobación.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

#: el HEALTHCHECK corre cada 30 s: cuatro pasadas perdidas ya no es «lo último que sabemos».
EDAD_MAXIMA_S = 120.0

#: lo que `GET /api/health` devuelve en `status`; el resto (p. ej. «unreachable» del navegador) no
#: llega nunca aquí.
ESTADOS_QUE_AVISAN = frozenset({"degraded", "unhealthy"})


@dataclass(frozen=True)
class ResumenSalud:
    estado: str
    momento: float  # `time.monotonic()` de la comprobación


_ultimo: ResumenSalud | None = None


def registrar(estado: str, ahora: float | None = None) -> None:
    """Guarda el veredicto global de la comprobación que acaba de terminar."""
    global _ultimo
    _ultimo = ResumenSalud(estado, time.monotonic() if ahora is None else ahora)


def olvidar() -> None:
    """Vacía el resumen (pruebas; un reinicio ya lo hace por sí solo)."""
    global _ultimo
    _ultimo = None


def requiere_atencion(ahora: float | None = None, max_edad: float = EDAD_MAXIMA_S) -> bool:
    """¿La última comprobación, reciente, dijo «Atención» o «Error»? Sin resumen o viejo: no."""
    ultimo = _ultimo
    if ultimo is None:
        return False
    instante = time.monotonic() if ahora is None else ahora
    if not 0 <= instante - ultimo.momento <= max_edad:
        return False
    return ultimo.estado in ESTADOS_QUE_AVISAN
