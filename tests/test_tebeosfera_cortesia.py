# ruff: noqa: E501
"""Cortesía con Tebeosfera: 2,5 s como mínimo entre peticiones, COMPARTIDO por todas las instancias y caminos.

Antes cada `TebeosferaClient` llevaba su propio `_last_req` (a 0 al crearse) y cada búsqueda de Descubrir o cada
ciclo del enricher crea uno nuevo: dos búsquedas seguidas llegaban al sitio sin espera entre ellas. Con reloj y
transporte simulados se comprueba, para instancias distintas, caminos distintos y peticiones concurrentes, que
entre el inicio de dos peticiones al sitio pasan al menos 2,5 s. Nada sale a la red y nada duerme de verdad.

La garantía depende de que haya UN SOLO PROCESO (`uvicorn --workers 1`); ver `utils/cortesia.py`.
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from types import SimpleNamespace

import httpx
import pytest
import structlog

from zascarr.config import get_settings
from zascarr.services import tebeosfera
from zascarr.services.tebeosfera import MINIMO_ENTRE_PETICIONES_S, TebeosferaClient
from zascarr.utils import cortesia
from zascarr.utils.cortesia import LimitadorDeCortesia

HTML = ('<div class="linea_resultados"><a href="/colecciones/thorgal_1981_distrinovel.html">'
        'THORGAL (1981, DISTRINOVEL)</a></div>')


class Reloj:
    def __init__(self):
        self.t = 5000.0

    def __call__(self):
        return self.t

    async def dormir(self, s):
        await asyncio.sleep(0)
        self.t += s


class Sitio:
    """El «sitio»: un transporte simulado que anota el instante (del reloj falso) de CADA petición."""

    def __init__(self, reloj: Reloj, falla: bool = False):
        self.reloj, self.falla = reloj, falla
        self.instantes: list[float] = []

    def transporte(self) -> httpx.MockTransport:
        def _h(request: httpx.Request) -> httpx.Response:
            self.instantes.append(self.reloj())
            if self.falla:
                raise httpx.ConnectError("caído")
            return httpx.Response(200, text=HTML)
        return httpx.MockTransport(_h)

    def separaciones(self) -> list[float]:
        return [b - a for a, b in zip(self.instantes, self.instantes[1:], strict=False)]


@pytest.fixture
def mundo(monkeypatch):
    cortesia.reiniciar_para_pruebas()
    reloj = Reloj()
    cortesia._LIMITADORES["tebeosfera"] = LimitadorDeCortesia(reloj=reloj, dormir=reloj.dormir)
    ajustes = {"tebeosfera_rate_limit": 2.5}
    monkeypatch.setattr(tebeosfera, "get_settings", lambda: SimpleNamespace(**ajustes))
    yield SimpleNamespace(reloj=reloj, sitio=Sitio(reloj), ajustes=ajustes)
    cortesia.reiniciar_para_pruebas()


def cliente(mundo) -> TebeosferaClient:
    return TebeosferaClient(transporte=mundo.sitio.transporte())


async def buscar(mundo, consulta="Thorgal"):
    async with cliente(mundo) as c:
        return await c.search_series(consulta)


class TestInstanciasYCaminosDistintos:

    async def test_dos_busquedas_seguidas_con_clientes_distintos_se_espacian(self, mundo):
        """El caso del fallo: cada búsqueda crea un cliente nuevo. Antes, la 1.ª petición de la 2.ª búsqueda no
        esperaba nada."""
        await buscar(mundo)
        await buscar(mundo)
        s = mundo.sitio
        assert len(s.instantes) == 4                          # 2 peticiones por búsqueda (colecciones + sagas)
        assert all(x >= 2.5 - 1e-9 for x in s.separaciones()), s.separaciones()

    async def test_la_primera_peticion_del_proceso_no_espera(self, mundo):
        await buscar(mundo)
        assert mundo.sitio.instantes[0] == pytest.approx(5000.0)

    async def test_busquedas_concurrentes_de_clientes_distintos_se_escalonan(self, mundo):
        await asyncio.gather(*(buscar(mundo, f"t{i}") for i in range(5)))
        s = mundo.sitio
        assert len(s.instantes) == 10
        assert all(x >= 2.5 - 1e-9 for x in s.separaciones()), s.separaciones()
        assert s.instantes[-1] - s.instantes[0] == pytest.approx(9 * 2.5)

    async def test_el_camino_de_descubrir_y_el_del_enricher_comparten_el_limite(self, mundo):
        """Descubrir abre un cliente por búsqueda (`async with`); el enricher uno por ciclo, dentro de un
        `AsyncExitStack`. Concurrentes, comparten el mismo limitador."""
        async def como_descubrir():
            async with cliente(mundo) as c:
                await c.search_series("a")

        async def como_el_enricher():
            async with AsyncExitStack() as pila:
                c = await pila.enter_async_context(cliente(mundo))
                await c.search_series("b")
                await c.search_series("c")
        await asyncio.gather(como_descubrir(), como_el_enricher(), como_descubrir())
        s = mundo.sitio
        assert len(s.instantes) == 8
        assert all(x >= 2.5 - 1e-9 for x in s.separaciones()), s.separaciones()

    async def test_las_dos_peticiones_de_una_misma_busqueda_tambien_se_espacian(self, mundo):
        await buscar(mundo)
        assert mundo.sitio.separaciones() == [pytest.approx(2.5)]

    async def test_una_peticion_que_falla_cuenta_para_el_espaciado(self, mundo):
        mundo.sitio.falla = True
        assert await buscar(mundo) == []                      # el cliente trata el fallo como «sin resultado»
        mundo.sitio.falla = False
        await buscar(mundo)
        assert all(x >= 2.5 - 1e-9 for x in mundo.sitio.separaciones())

    async def test_el_limitador_es_el_compartido_del_sitio_y_no_uno_propio(self, mundo):
        a, b = cliente(mundo), cliente(mundo)
        async with a, b:
            await a._throttle()
            await b._throttle()
        assert mundo.sitio.instantes == []                    # (solo throttle: sin peticiones)
        assert cortesia._LIMITADORES["tebeosfera"]._ultima is not None
        assert not hasattr(a, "_last_req") and not hasattr(b, "_last_req")


class TestElMinimo:

    @pytest.mark.parametrize("configurado", [2.0, 1.0, 0.0, 0.1, -3.0])
    async def test_una_configuracion_por_debajo_del_minimo_se_eleva_a_2_5(self, mundo, configurado):
        mundo.ajustes["tebeosfera_rate_limit"] = configurado
        await buscar(mundo)
        await buscar(mundo)
        assert all(x >= MINIMO_ENTRE_PETICIONES_S - 1e-9 for x in mundo.sitio.separaciones())

    @pytest.mark.parametrize("configurado", [2.5, 3.0, 10.0])
    async def test_una_configuracion_igual_o_superior_se_respeta(self, mundo, configurado):
        mundo.ajustes["tebeosfera_rate_limit"] = configurado
        await buscar(mundo)
        assert all(x == pytest.approx(configurado) for x in mundo.sitio.separaciones())

    def test_el_minimo_del_proyecto_es_2_5_y_el_valor_por_defecto_tambien(self):
        assert MINIMO_ENTRE_PETICIONES_S == 2.5
        assert type(get_settings()).model_fields["tebeosfera_rate_limit"].default == 2.5

    async def test_avisa_en_el_registro_si_la_configuracion_estaba_por_debajo(self, mundo):
        mundo.ajustes["tebeosfera_rate_limit"] = 1.0
        with structlog.testing.capture_logs() as registros:
            cliente(mundo)
        assert [r["event"] for r in registros] == ["tebeosfera.rate_limit_elevado"]
        assert registros[0]["configurado"] == 1.0 and registros[0]["minimo"] == 2.5

    async def test_con_la_configuracion_correcta_no_avisa(self, mundo):
        with structlog.testing.capture_logs() as registros:
            cliente(mundo)
        assert registros == []


class TestCancelacionYBucles:

    async def test_cancelar_una_busqueda_en_espera_no_rompe_el_espaciado_de_las_demas(self, mundo):
        await buscar(mundo)                                   # la 1.ª y la 2.ª petición ya hechas
        tarea = asyncio.create_task(buscar(mundo, "cancelada"))
        await asyncio.sleep(0)
        tarea.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tarea
        await buscar(mundo, "siguiente")
        assert all(x >= 2.5 - 1e-9 for x in mundo.sitio.separaciones())

    def test_funciona_en_bucles_de_eventos_distintos(self, monkeypatch):
        cortesia.reiniciar_para_pruebas()
        reloj = Reloj()
        cortesia._LIMITADORES["tebeosfera"] = LimitadorDeCortesia(reloj=reloj, dormir=reloj.dormir)
        monkeypatch.setattr(tebeosfera, "get_settings", lambda: SimpleNamespace(tebeosfera_rate_limit=2.5))
        sitio = Sitio(reloj)

        async def una():
            async with TebeosferaClient(transporte=sitio.transporte()) as c:
                await c.search_series("x")
        asyncio.run(una())
        asyncio.run(una())
        assert all(x >= 2.5 - 1e-9 for x in sitio.separaciones())
        cortesia.reiniciar_para_pruebas()
