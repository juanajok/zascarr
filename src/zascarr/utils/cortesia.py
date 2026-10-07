# ruff: noqa: E501
"""Cortesía con los sitios externos: un mínimo entre peticiones COMPARTIDO por todos los caminos del proceso.

El límite de cortesía de cada cliente de fuentes vivía en la INSTANCIA (`self._last_req`, a 0 al crearla) y cada
búsqueda de Descubrir o cada ciclo del enriquecedor crea clientes nuevos: dos búsquedas seguidas, o una búsqueda
mientras corre el enriquecedor, llegaban al sitio sin espera entre ellas. Aquí el estado vive **por sitio y por
proceso**, no por instancia.

Qué garantiza y qué NO:
- Entre el INICIO de dos peticiones al mismo sitio hay, como mínimo, `minimo` segundos, venga cada una de la
  instancia, del camino o de la tarea que sea; las concurrentes hacen cola (FIFO) y se escalonan.
- **Depende de que haya UN SOLO proceso.** La imagen arranca `uvicorn --workers 1` y el enriquecedor corre en
  ese mismo proceso (`main._enrichment_loop`), así que cubre todos los caminos que existen hoy. Con varios
  procesos o réplicas NO se coordinan (haría falta un estado compartido, p. ej. en Redis).
- Mide con `time.monotonic` (no se ve afectado por cambios de la hora del sistema).
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class LimitadorDeCortesia:
    """Espacia las peticiones a UN sitio. El reloj y la espera son inyectables para probarlo sin dormir."""

    def __init__(self, reloj: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self._reloj = reloj
        self._dormir = dormir
        self._ultima: float | None = None          # inicio de la última petición autorizada
        self._candado: asyncio.Lock | None = None
        self._bucle: asyncio.AbstractEventLoop | None = None

    def _candado_del_bucle(self) -> asyncio.Lock:
        """Un `asyncio.Lock` queda ligado al bucle que lo usa: si el proceso cambia de bucle (las pruebas lo
        hacen en cada test), se crea otro en vez de fallar con «attached to a different loop»."""
        bucle = asyncio.get_running_loop()
        if self._candado is None or self._bucle is not bucle:
            self._candado, self._bucle = asyncio.Lock(), bucle
        return self._candado

    async def esperar(self, minimo: float) -> float:
        """Devuelve cuando ya se puede hacer la petición; cuántos segundos se esperó. La primera no espera.
        Una espera cancelada no marca la petición como hecha."""
        async with self._candado_del_bucle():
            espera = 0.0
            if self._ultima is not None:
                espera = max(0.0, self._ultima + minimo - self._reloj())
                if espera > 0:
                    await self._dormir(espera)
            self._ultima = self._reloj()
            return espera


_LIMITADORES: dict[str, LimitadorDeCortesia] = {}


def limitador_de(sitio: str) -> LimitadorDeCortesia:
    """El limitador compartido del sitio (uno por proceso)."""
    if sitio not in _LIMITADORES:
        _LIMITADORES[sitio] = LimitadorDeCortesia()
    return _LIMITADORES[sitio]


def reiniciar_para_pruebas() -> None:
    _LIMITADORES.clear()
