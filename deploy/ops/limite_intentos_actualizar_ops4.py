"""Límite de intentos de actualización en memoria; no persiste ni autentica.

Cinco fallos dentro de 15 minutos bloquean 30 minutos, sin calcular PBKDF2
mientras el bloqueo esté activo. El estado es local al proceso: reiniciarlo lo
borra y no coordina varios procesos. La persistencia y el bloqueo compartido
con OPS2 siguen pendientes. No registra contraseñas ni usa E/S.
"""
from __future__ import annotations

import threading
import time

UMBRAL_FALLOS = 5
VENTANA_S = 15 * 60
BLOQUEO_S = 30 * 60


class LimiteIntentos:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fallos: list[float] = []
        self._bloqueado_hasta = 0.0

    def permite(self, ahora: float | None = None) -> bool:
        """False si el bloqueo sigue activo o el reloj no es válido."""
        instante = _instante(ahora)
        if instante is None:
            return False
        with self._lock:
            return self._bloqueado_hasta <= instante

    def fallo(self, ahora: float | None = None) -> None:
        """Anota un fallo; un reloj inválido bloquea de forma conservadora."""
        instante = _instante(ahora)
        with self._lock:
            if instante is None:
                self._bloqueado_hasta = float("inf")
                return
            self._fallos[:] = [t for t in self._fallos if instante - t <= VENTANA_S]
            self._fallos.append(instante)
            if len(self._fallos) >= UMBRAL_FALLOS:
                self._bloqueado_hasta = instante + BLOQUEO_S

    def exito(self, ahora: float | None = None) -> None:
        """Un acierto limpia el bloqueo; el instante se acepta por interfaz común."""
        with self._lock:
            self._fallos.clear()
            self._bloqueado_hasta = 0.0

    def reiniciar(self) -> None:
        """Solo para pruebas o reinicio explícito del proceso."""
        self.exito()


def _instante(ahora: float | None) -> float | None:
    valor = time.time() if ahora is None else ahora
    if type(valor) not in (int, float) or not 0 <= valor < 2**63:
        return None
    return float(valor)
