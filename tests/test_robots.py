# ruff: noqa: E501
"""`utils/robots.py`: matriz RFC 9309, TTLs, Crawl-delay y singleflight por origen (AC-07).

Sin red real: la descarga se simula con una función `descargar_robots_fn` que cuenta llamadas
y el reloj monotónico es inyectable.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada, PoliticaFuente
from zascarr.utils.peticiones import ReintentosAgotados
from zascarr.utils.robots import (
    MAX_ROBOTS,
    USER_AGENT,
    GestorRobots,
    _reiniciar_gestor_compartido,
    aplicar_crawl_delay,
    gestor_robots_de_proceso,
)

URL = "https://dc.fandom.com/api.php?action=query"


class Reloj:
    def __init__(self, inicio: float = 1000.0):
        self.t = inicio

    def __call__(self) -> float:
        return self.t

    def avanzar(self, segundos: float) -> None:
        self.t += segundos


class Descargas:
    """Descargador falso: devuelve respuestas (o lanza excepciones) y cuenta URLs."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.urls: list[str] = []

    async def __call__(self, url: str) -> httpx.Response:
        self.urls.append(url)
        siguiente = self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


def _robots(texto: str) -> httpx.Response:
    return httpx.Response(200, text=texto)


def _gestor(reloj: Reloj) -> GestorRobots:
    return GestorRobots(reloj=reloj)


# ── 2xx: parsea, aplica Disallow y Crawl-delay, 24 h ───────────────────────────────────────────

async def test_200_aplica_disallow_crawl_delay_y_cachea_24h():
    reloj = Reloj()
    descargas = Descargas(_robots("User-agent: *\nDisallow: /private\nCrawl-delay: 3\n"))
    gestor = _gestor(reloj)
    # Prohibido; el Crawl-delay declarado también viaja (quien prohíbe no lo usa).
    assert await gestor.evaluar("https://dc.fandom.com/private/x",
                                descargar_robots_fn=descargas) == (False, 3.0)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (True, 3.0)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (True, 3.0)
    assert len(descargas.urls) == 1 and descargas.urls[0].endswith("/robots.txt")
    reloj.avanzar(GestorRobots.TTL_OK_S + 1)
    await gestor.evaluar(URL, descargar_robots_fn=descargas)
    assert len(descargas.urls) == 2


async def test_robots_se_lee_como_mucho_512_kib():
    reloj = Reloj()
    texto = "User-agent: *\nDisallow: /x\n" + "#" * (MAX_ROBOTS * 2)
    descargas = Descargas(_robots(texto))
    gestor = _gestor(reloj)
    assert await gestor.evaluar("https://dc.fandom.com/x", descargar_robots_fn=descargas) == (False, None)


# ── 4xx ≠ 429: no disponible = permitido, 12 h ────────────────────────────────────────────────

@pytest.mark.parametrize("codigo", [401, 403, 404, 410])
async def test_4xx_distinto_de_429_permite_y_cachea_12h(codigo):
    reloj = Reloj()
    descargas = Descargas(httpx.Response(codigo))
    gestor = _gestor(reloj)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (True, None)
    reloj.avanzar(GestorRobots.TTL_UNAVAILABLE_S - 1)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (True, None)
    assert len(descargas.urls) == 1
    reloj.avanzar(2)
    await gestor.evaluar(URL, descargar_robots_fn=descargas)
    assert len(descargas.urls) == 2


# ── 429/5xx/red/parse roto: prohibido 15 min, nunca como permiso ─────────────────────────────

@pytest.mark.parametrize("codigo", [429, 500, 503])
async def test_429_y_5xx_prohiben_15_min(codigo):
    reloj = Reloj()
    descargas = Descargas(httpx.Response(codigo))
    gestor = _gestor(reloj)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
    reloj.avanzar(GestorRobots.TTL_UNREACHABLE_S - 1)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
    assert len(descargas.urls) == 1
    reloj.avanzar(2)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
    assert len(descargas.urls) == 2


async def test_fallo_de_red_prohibe_15_min():
    reloj = Reloj()
    descargas = Descargas(ReintentosAgotados("fandom_dc", 2, None))
    gestor = _gestor(reloj)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
    reloj.avanzar(GestorRobots.TTL_UNREACHABLE_S + 1)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
    assert len(descargas.urls) == 2


async def test_parse_que_lanza_prohibe_15_min(monkeypatch):
    def romper(_texto):
        raise ValueError("robots roto")

    monkeypatch.setattr("zascarr.utils.robots.Protego.parse", romper)
    reloj = Reloj()
    descargas = Descargas(_robots("User-agent: *\nDisallow: /\n"))
    gestor = _gestor(reloj)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
    reloj.avanzar(GestorRobots.TTL_UNREACHABLE_S + 1)
    assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
    assert len(descargas.urls) == 2


# ── política y presupuesto se propagan; un 5xx no se recuerda como permiso ────────────────────

async def test_fuente_apagada_y_cortesia_se_propagan():
    reloj = Reloj()
    apagada = Descargas(FuenteApagada("fandom_dc"))
    with pytest.raises(FuenteApagada):
        await _gestor(reloj).evaluar(URL, descargar_robots_fn=apagada)
    espera = Descargas(CortesiaEnEspera("fandom_dc", "dc.fandom.com", 10.0, "cortesia"))
    with pytest.raises(CortesiaEnEspera):
        await _gestor(reloj).evaluar(URL, descargar_robots_fn=espera)


# ── candado por origen (dos evaluaciones simultáneas, una descarga) ───────────────────────────

async def test_dos_evaluaciones_simultaneas_descargan_una_vez():
    reloj = Reloj()
    descargas = Descargas(_robots("User-agent: *\nDisallow: /privado\n"))

    async def descargar_lento(url: str) -> httpx.Response:
        descargas.urls.append(url)
        await asyncio.sleep(0.02)
        return descargas.respuestas[0]

    gestor = _gestor(reloj)
    resultados = await asyncio.gather(
        gestor.evaluar(URL, descargar_robots_fn=descargar_lento),
        gestor.evaluar("https://dc.fandom.com/otra", descargar_robots_fn=descargar_lento),
        gestor.evaluar("https://dc.fandom.com/privado", descargar_robots_fn=descargar_lento),
    )
    assert len(descargas.urls) == 1
    assert resultados[2] == (False, None)


# ── Crawl-delay: solo sube, nunca acelera ────────────────────────────────────────────────────

def test_aplicar_crawl_delay_solo_sube_el_intervalo():
    politica = PoliticaFuente(fuente="fandom_dc", nombre="DC Database",
                              intervalo_min_s=1.5, max_intentos=2, max_redirecciones=3)
    assert aplicar_crawl_delay(politica, None) is politica
    assert aplicar_crawl_delay(politica, 3).intervalo_min_s == 3.0
    assert aplicar_crawl_delay(politica, 0.5).intervalo_min_s == 1.5
    assert aplicar_crawl_delay(politica, float("nan")).intervalo_min_s == 1.5


# ── identificador, singleton y reinicio ──────────────────────────────────────────────────────

def test_user_agent_identifica_al_proyecto():
    assert USER_AGENT.startswith("ZascArr")


def test_singleton_perezoso_del_proceso_y_reinicio():
    gestor = gestor_robots_de_proceso()
    assert gestor_robots_de_proceso() is gestor
    _reiniciar_gestor_compartido()
    assert gestor_robots_de_proceso() is not gestor
