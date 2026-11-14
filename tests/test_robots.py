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


# ═══════════════════════════════════════════════════════════════════════════════
# M-4 (#813): tope de Crawl-delay y olvido de robots por origen
# ═══════════════════════════════════════════════════════════════════════════════

from types import SimpleNamespace  # noqa: E402

from zascarr.utils.robots import olvidar_origenes_de_fuente, origenes_de_fuente  # noqa: E402


def _ajustes_crawl(monkeypatch, maximo) -> SimpleNamespace:
    ajustes = SimpleNamespace(crawl_delay_max_s=maximo)
    monkeypatch.setattr("zascarr.config.get_settings", lambda: ajustes)
    return ajustes


class TestTopeCrawlDelay:

    async def test_ac_01_86400_se_recorta_a_60_y_avisa_una_vez(self, monkeypatch):
        import structlog

        _ajustes_crawl(monkeypatch, 60)
        reloj = Reloj()
        descargas = Descargas(_robots("User-agent: *\nCrawl-delay: 86400\n"))
        gestor = _gestor(reloj)
        with structlog.testing.capture_logs() as registros:
            assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (True, 60.0)
            assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (True, 60.0)
        avisos = [r for r in registros if r["event"] == "robots.crawl_delay_recortado"]
        assert len(avisos) == 1
        assert avisos[0]["declarado_s"] == 86400.0
        assert avisos[0]["recortado_s"] == 60.0 and avisos[0]["maximo_s"] == 60.0
        assert "://" in avisos[0]["origen"] and "/api" not in avisos[0]["origen"]
        assert len(descargas.urls) == 1             # no hay segunda descarga

    async def test_ac_02_un_delay_menor_no_se_recorta_ni_avisa(self, monkeypatch):
        import structlog

        _ajustes_crawl(monkeypatch, 60)
        gestor = _gestor(Reloj())
        with structlog.testing.capture_logs() as registros:
            assert await gestor.evaluar(
                URL, descargar_robots_fn=Descargas(_robots("User-agent: *\nCrawl-delay: 30\n"))
            ) == (True, 30.0)
        assert not [r for r in registros if r["event"] == "robots.crawl_delay_recortado"]

    def test_ac_03_nunca_baja_del_minimo_local(self, monkeypatch):
        _ajustes_crawl(monkeypatch, 60)
        politica = PoliticaFuente("x", "X", 2.5, 1, 3)
        assert aplicar_crawl_delay(politica, 1.0).intervalo_min_s == 2.5

        _ajustes_crawl(monkeypatch, 5)
        # El cap no acelera por debajo del mínimo local (90 > 5).
        politica90 = PoliticaFuente("x", "X", 90.0, 1, 3)
        assert aplicar_crawl_delay(politica90, 5.0).intervalo_min_s == 90.0

    @pytest.mark.parametrize("texto", [
        "User-agent: *\n",
        "User-agent: *\nCrawl-delay: 0\n",
        "User-agent: *\nCrawl-delay: -3\n",
        "User-agent: *\nCrawl-delay: NaN\n",
        "User-agent: *\nCrawl-delay: abc\n",
    ])
    async def test_ac_04_ausente_cero_negativo_nan_o_texto_no_cambian(self, monkeypatch, texto):
        _ajustes_crawl(monkeypatch, 60)
        gestor = _gestor(Reloj())
        assert await gestor.evaluar(
            URL, descargar_robots_fn=Descargas(_robots(texto))) == (True, None)

    async def test_ac_04_infinito_se_recorta_al_maximo(self, monkeypatch):
        _ajustes_crawl(monkeypatch, 60)
        gestor = _gestor(Reloj())
        assert await gestor.evaluar(
            URL, descargar_robots_fn=Descargas(_robots("User-agent: *\nCrawl-delay: inf\n"))
        ) == (True, 60.0)

    async def test_ac_05_cambiar_el_maximo_surte_efecto_sin_recargar_robots(self, monkeypatch):
        ajustes = _ajustes_crawl(monkeypatch, 60)
        reloj = Reloj()
        descargas = Descargas(_robots("User-agent: *\nCrawl-delay: 86400\n"))
        gestor = _gestor(reloj)
        assert (await gestor.evaluar(URL, descargar_robots_fn=descargas))[1] == 60.0

        # El parser/EntradaRobots guarda el valor CRUDO; solo cambia el recorte de la evaluación.
        ajustes.crawl_delay_max_s = 120
        assert (await gestor.evaluar(URL, descargar_robots_fn=descargas))[1] == 120.0
        assert len(descargas.urls) == 1
        origen = "https://dc.fandom.com"
        assert gestor._cache[origen].parser.crawl_delay(USER_AGENT) == 86400


class TestOlvidar:

    async def test_ac_06_olvidar_un_origen_no_toca_el_otro_y_fuerza_descarga(self):
        reloj = Reloj()
        descargas = Descargas(
            _robots("User-agent: *\nDisallow: /privado\n"),
            _robots("User-agent: *\n"),
            _robots("User-agent: *\n"),
        )
        gestor = _gestor(reloj)
        a = "https://a.example/privado/x"
        b = "https://b.example/x"
        assert await gestor.evaluar(a, descargar_robots_fn=descargas) == (False, None)
        assert await gestor.evaluar(b, descargar_robots_fn=descargas) == (True, None)
        assert len(descargas.urls) == 2

        gestor.olvidar("https://a.example")
        # B sigue cacheado: no se vuelve a descargar.
        assert await gestor.evaluar(b, descargar_robots_fn=descargas) == (True, None)
        assert len(descargas.urls) == 2
        # A se vuelve a descargar y ahora permite.
        assert await gestor.evaluar(a, descargar_robots_fn=descargas) == (True, None)
        assert len(descargas.urls) == 3

    async def test_ac_07_unreachable_disallow_sobrevive_si_no_se_olvida(self):
        reloj = Reloj()
        descargas = Descargas(httpx.Response(500), _robots("User-agent: *\n"))
        gestor = _gestor(reloj)
        assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
        assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (False, None)
        assert len(descargas.urls) == 1             # el «prohibido» sobrevive
        gestor.olvidar(URL)
        assert await gestor.evaluar(URL, descargar_robots_fn=descargas) == (True, None)
        assert len(descargas.urls) == 2

    async def test_ac_08_evaluacion_en_vuelo_no_resucita_la_entrada(self):
        reloj = Reloj()
        inicio = asyncio.Event()
        seguir = asyncio.Event()
        descargas: list[str] = []

        async def descargar(url: str) -> httpx.Response:
            descargas.append(url)
            if len(descargas) == 1:
                inicio.set()
                await seguir.wait()
                return _robots("User-agent: *\nDisallow: /api\n")
            return _robots("User-agent: *\n")

        gestor = _gestor(reloj)
        tarea = asyncio.create_task(gestor.evaluar(URL, descargar_robots_fn=descargar))
        await inicio.wait()
        gestor.olvidar(URL)                          # el toggle llega en mitad de la evaluación
        seguir.set()
        assert await tarea == (False, None)          # la evaluación en vuelo devuelve su resultado
        assert "https://dc.fandom.com" not in gestor._cache   # pero no resucita la entrada

        assert await gestor.evaluar(URL, descargar_robots_fn=descargar) == (True, None)
        assert len(descargas) == 2                   # la siguiente descarga de nuevo
        assert "https://dc.fandom.com" in gestor._cache

    async def test_el_aviso_de_recorte_se_rearma_tras_olvidar(self, monkeypatch):
        import structlog

        _ajustes_crawl(monkeypatch, 60)
        gestor = _gestor(Reloj())
        robots = _robots("User-agent: *\nCrawl-delay: 86400\n")
        with structlog.testing.capture_logs() as registros:
            await gestor.evaluar(URL, descargar_robots_fn=Descargas(robots))
            gestor.olvidar(URL)
            await gestor.evaluar(URL, descargar_robots_fn=Descargas(robots))
        assert len([r for r in registros if r["event"] == "robots.crawl_delay_recortado"]) == 2


class TestOrigenesDeFuente:

    @pytest.mark.parametrize(("fuente", "esperado"), [
        ("fandom_dc", ("https://dc.fandom.com",)),
        ("fandom_marvel", ("https://marvel.fandom.com",)),
        ("reading_orders", ("https://comicbookreadingorders.com",)),
        ("continuity_guide", ("https://www.continuityguide.net",)),
        ("foro", ()),
        ("portada", ()),
        ("desconocida", ()),
    ])
    def test_ac_09_mapea_las_fuentes_con_robots(self, monkeypatch, fuente, esperado):
        monkeypatch.setattr("zascarr.config.get_settings", lambda: SimpleNamespace(
            comic_book_herald_feed_url="https://www.comicbookherald.com/category/x/feed/"))
        assert origenes_de_fuente(fuente) == esperado

    def test_ac_09_herald_usa_la_url_de_config(self, monkeypatch):
        monkeypatch.setattr("zascarr.config.get_settings", lambda: SimpleNamespace(
            comic_book_herald_feed_url="https://www.comicbookherald.com/otra/feed/"))
        assert origenes_de_fuente("comic_book_herald") == (
            "https://www.comicbookherald.com",)

    def test_ac_09_no_instancia_el_gestor_compartido(self):
        import zascarr.utils.robots as modulo

        modulo._reiniciar_gestor_compartido()
        assert modulo._GESTOR_DE_PROCESO is None
        origenes_de_fuente("fandom_dc")
        assert modulo._GESTOR_DE_PROCESO is None
        assert olvidar_origenes_de_fuente("fandom_dc") == ("https://dc.fandom.com",)
        assert modulo._GESTOR_DE_PROCESO is None
