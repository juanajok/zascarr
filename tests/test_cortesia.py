# ruff: noqa: E501
"""`utils/cortesia.py`: el limitador de cortesía, con reloj y espera SIMULADOS (nada duerme de verdad)."""
from __future__ import annotations

import asyncio
import time

import pytest

from zascarr.utils import cortesia
from zascarr.utils.cortesia import LimitadorDeCortesia, limitador_de, reiniciar_para_pruebas


class Reloj:
    """Un reloj falso: dormir lo adelanta, y cede el control para que las tareas concurrentes se intercalen."""

    def __init__(self, inicio: float = 1000.0):
        self.t = inicio
        self.dormidos: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.dormidos.append(segundos)
        await asyncio.sleep(0)
        self.t += segundos


def limitador(reloj: Reloj) -> LimitadorDeCortesia:
    return LimitadorDeCortesia(reloj=reloj, dormir=reloj.dormir)


async def test_la_primera_peticion_no_espera():
    r = Reloj()
    assert await limitador(r).esperar(2.5) == 0.0 and r.dormidos == []


async def test_la_segunda_espera_lo_que_falta_hasta_el_minimo():
    r = Reloj()
    lim = limitador(r)
    await lim.esperar(2.5)
    r.t += 1.0                                         # han pasado 1,0 s
    assert await lim.esperar(2.5) == pytest.approx(1.5)
    assert r.dormidos == [pytest.approx(1.5)]


async def test_si_ya_ha_pasado_el_minimo_no_espera():
    r = Reloj()
    lim = limitador(r)
    await lim.esperar(2.5)
    r.t += 2.5
    assert await lim.esperar(2.5) == 0.0 and r.dormidos == []
    r.t += 100
    assert await lim.esperar(2.5) == 0.0


async def test_peticiones_concurrentes_se_escalonan_y_ninguna_se_acerca_mas_del_minimo():
    r = Reloj()
    lim = limitador(r)
    instantes: list[float] = []

    async def una():
        await lim.esperar(2.5)
        instantes.append(r())
    await asyncio.gather(*(una() for _ in range(6)))
    assert len(instantes) == 6
    assert all(b - a >= 2.5 - 1e-9 for a, b in zip(instantes, instantes[1:], strict=False))
    assert instantes[-1] - instantes[0] == pytest.approx(5 * 2.5)


async def test_el_minimo_puede_cambiar_entre_llamadas_y_manda_el_de_cada_una():
    r = Reloj()
    lim = limitador(r)
    await lim.esperar(1.0)
    assert await lim.esperar(5.0) == pytest.approx(5.0)
    assert await lim.esperar(0.0) == pytest.approx(0.0)


async def test_una_espera_cancelada_no_cuenta_como_peticion_hecha_ni_atasca_el_candado():
    r = Reloj()
    lim = LimitadorDeCortesia(reloj=r, dormir=lambda s: asyncio.sleep(3600))
    await lim.esperar(2.5)
    pendiente = asyncio.create_task(lim.esperar(2.5))
    await asyncio.sleep(0)
    pendiente.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pendiente
    # el candado quedó libre y la marca de «última petición» sigue siendo la de la primera
    lim2 = limitador(r)
    lim2._ultima = lim._ultima
    assert lim._candado is not None and not lim._candado.locked()
    r.t += 2.5
    assert await lim2.esperar(2.5) == 0.0


def test_funciona_con_bucles_de_eventos_distintos():
    """Un `asyncio.Lock` queda ligado a su bucle: el limitador no debe fallar si cambia (las pruebas lo hacen)."""
    lim = limitador(Reloj())

    async def usa():
        await lim.esperar(2.5)
    asyncio.run(usa())
    asyncio.run(usa())


def test_por_defecto_mide_con_el_reloj_monotonico():
    assert LimitadorDeCortesia()._reloj is time.monotonic


def test_hay_un_limitador_por_sitio_y_es_el_mismo_cada_vez():
    reiniciar_para_pruebas()
    assert limitador_de("a") is limitador_de("a")
    assert limitador_de("a") is not limitador_de("b")
    assert "a" in cortesia._LIMITADORES


async def test_los_sitios_no_se_bloquean_entre_si():
    reiniciar_para_pruebas()
    a, b = limitador_de("a"), limitador_de("b")
    r = Reloj()
    a._reloj = b._reloj = r
    a._dormir = b._dormir = r.dormir
    await a.esperar(10)
    assert await b.esperar(10) == 0.0                    # otro sitio: no espera por el primero


def test_con_contencion_en_dos_bucles_distintos_no_falla_el_candado():
    """Un `asyncio.Lock` solo se ata a su bucle cuando alguien tiene que ESPERARLO: hace falta concurrencia en
    cada bucle para que, sin rehacerlo, el segundo falle con «bound to a different event loop»."""
    r = Reloj()
    lim = limitador(r)

    async def ronda():
        await asyncio.gather(*(lim.esperar(2.5) for _ in range(3)))
    asyncio.run(ronda())
    asyncio.run(ronda())
    assert len(r.dormidos) >= 5
