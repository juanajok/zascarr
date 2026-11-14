"""SCR5 — Comic Book Herald por RSS: parseo, allowlist, caché/robots y fuente apagada."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import structlog

from zascarr.services.comicbook_herald import (
    FEED_POR_DEFECTO,
    MAX_CUERPO,
    MAX_ITEMS,
    ComicBookHeraldClient,
    HeraldItem,
    parsear_feed,
)
from zascarr.utils.cache_http import FilaCache
from zascarr.utils.cortesia import CortesiaProceso, FuenteApagada

FIXTURES = Path(__file__).parent / "fixtures" / "herald"
FEED = FEED_POR_DEFECTO
ARTICULO = "https://www.comicbookherald.com/crisis-on-infinite-earths-reading-order/"


def _ajustes(**kw) -> SimpleNamespace:
    base = dict(comic_book_herald_enabled=True, comic_book_herald_rate_limit=3.5,
                comic_book_herald_feed_url=FEED)
    base.update(kw)
    return SimpleNamespace(**base)


class Reloj:
    def __init__(self):
        self.t = 1000.0
        self.dormidos: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.dormidos.append(segundos)
        self.t += segundos


class CacheFalsa:
    """`CacheHttpProtocolo` en memoria; cuenta escrituras y sirve lo guardado."""

    def __init__(self):
        self.filas: dict[str, FilaCache] = {}
        self.escrituras = 0

    async def leer(self, url_hash):
        return self.filas.get(url_hash)

    async def escribir(self, fila):
        self.filas[fila.url_hash] = fila
        self.escrituras += 1

    async def renovar(self, url_hash, *, fetched_at, fresh_until, retain_until):
        fila = self.filas.get(url_hash)
        if fila is None:
            return 0
        self.filas[url_hash] = replace(fila, fetched_at=fetched_at,
                                       fresh_until=fresh_until, retain_until=retain_until)
        return 1

    async def purgar(self, ahora=None):
        return 0


class RobotsFalso:
    def __init__(self, permitido=True):
        self.permitido = permitido

    async def evaluar(self, _url, *, descargar_robots_fn):
        return self.permitido, 0.0


def _respuesta(contenido: bytes, *, status: int = 200) -> httpx.Response:
    return httpx.Response(status, content=contenido,
                          headers={"content-type": "application/rss+xml; charset=UTF-8"})


def _cliente(handler, *, ajustes=None, cache=None, robots=None, reloj=None):
    reloj = reloj or Reloj()
    return ComicBookHeraldClient(
        cache or CacheFalsa(),
        robots=robots or RobotsFalso(),
        transporte=httpx.MockTransport(handler),
        cortesia=CortesiaProceso(reloj=reloj, dormir=reloj.dormir),
        reloj=reloj, dormir=reloj.dormir, espera_max_s=60.0,
        ajustes=ajustes or _ajustes(),
    )


@pytest.fixture(autouse=True)
def _fuente_encendida(monkeypatch):
    """`fuente_habilitada` (dentro de la caché) lee la configuración real."""
    monkeypatch.setattr("zascarr.config.get_settings", lambda: _ajustes())


def _fixture(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


# ── Parseo del RSS 2.0 real (recortado) ──────────────────────────────────────────────────

def test_parsea_items_con_titulo_enlace_fecha_y_categorias():
    items = parsear_feed(_fixture("feed_reading_orders.xml"))
    assert len(items) == MAX_ITEMS                    # el feed real trae 10; el fixture 12
    primero = items[0]
    assert primero.titulo.startswith("Crisis on Infinite Earths")
    assert primero.url == ARTICULO
    assert primero.publicado == datetime(2026, 11, 10, 14, 30, tzinfo=UTC)
    assert primero.categorias == ("Reading Orders",)
    # Nunca se lee la prosa del artículo (`description`).
    assert all("Resumen que NO debe guardarse" not in item.titulo for item in items)
    assert all(item.url.startswith("https://www.comicbookherald.com/") for item in items)


def test_titulos_con_tildes_y_ene_se_leen_bien():
    items = parsear_feed(_fixture("feed_reading_orders.xml"))
    assert any("Año Uno" in item.titulo for item in items)
    assert any("Patrulla-X" in item.titulo for item in items)
    assert all("Ã" not in item.titulo and "�" not in item.titulo for item in items)


def test_solo_pasan_urls_https_del_host_permitido():
    items = parsear_feed(_fixture("feed_urls_no_permitidas.xml"))
    assert [item.titulo for item in items] == ["Válida"]
    assert items[0].url == "https://www.comicbookherald.com/valida/"


@pytest.mark.parametrize("fixture", ["feed_xml_roto.xml", "feed_xxe.xml"])
def test_xml_roto_o_xxe_devuelve_lista_vacia(fixture):
    assert parsear_feed(_fixture(fixture)) == []
    assert parsear_feed(b"") == []


def test_el_parser_no_resuelve_entidades_ni_red():
    items = parsear_feed(_fixture("feed_xxe.xml"))
    assert items == []                                # el título es una entidad sin resolver


# ── Cliente: caché, robots y fallos esperables ──────────────────────────────────────────

async def test_la_primera_llamada_pide_el_feed_y_la_segunda_es_cache_hit():
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return _respuesta(_fixture("feed_reading_orders.xml"))

    cache = CacheFalsa()
    cliente = _cliente(handler, cache=cache)
    items = await cliente.novedades()
    assert len(items) == MAX_ITEMS and len(peticiones) == 1
    assert cache.escrituras == 1

    assert await cliente.novedades() == items
    assert len(peticiones) == 1                       # hit vigente: ni red ni turno


async def test_la_fuente_apagada_se_propaga_sin_pedir_nada(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings",
                        lambda: _ajustes(comic_book_herald_enabled=False))
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return _respuesta(b"<rss/>")

    cliente = _cliente(handler, ajustes=_ajustes(comic_book_herald_enabled=False))
    with pytest.raises(FuenteApagada):
        await cliente.novedades()
    assert peticiones == []


async def test_robots_denegado_devuelve_vacio_sin_pedir_el_feed():
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return _respuesta(_fixture("feed_reading_orders.xml"))

    cliente = _cliente(handler, robots=RobotsFalso(permitido=False))
    with structlog.testing.capture_logs() as registros:
        assert await cliente.novedades() == []
    assert peticiones == []
    assert any(r["event"] == "comicbook_herald.robots" for r in registros)


async def test_un_fallo_de_red_devuelve_vacio_y_no_lanza():
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sin red")

    with structlog.testing.capture_logs() as registros:
        assert await _cliente(handler).novedades() == []
    assert any(r["event"] == "comicbook_herald.negativa" for r in registros)


async def test_un_404_del_feed_devuelve_vacio():
    assert await _cliente(lambda _r: _respuesta(b"no", status=404)).novedades() == []


async def test_un_cuerpo_mayor_de_un_mib_no_se_parsea():
    def handler(_request: httpx.Request) -> httpx.Response:
        return _respuesta(b"x" * (MAX_CUERPO + 1))

    with structlog.testing.capture_logs() as registros:
        assert await _cliente(handler).novedades() == []
    assert any(r["event"] == "comicbook_herald.cuerpo_demasiado_grande"
               for r in registros)


async def test_un_feed_configurado_fuera_del_host_no_se_pide():
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return _respuesta(_fixture("feed_reading_orders.xml"))

    cliente = _cliente(handler, ajustes=_ajustes(
        comic_book_herald_feed_url="https://evil.example/feed/"))
    assert await cliente.novedades() == []
    assert peticiones == []


def test_legal_menciona_el_feed_publico_y_la_atribucion():
    legal = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "LEGAL.md")
    texto = legal.read_text(encoding="utf-8")
    assert "Comic Book Herald (feed RSS)" in texto
    assert "feed público" in texto and "comicbookherald.com" in texto
    assert "título" in texto and "enlace" in texto


def test_el_tope_de_items_es_diez():
    assert MAX_ITEMS == 10


def test_la_fecha_sin_zona_se_asume_utc():
    xml = (b'<?xml version="1.0"?><rss><channel><item>'
           b"<title>T</title><link>https://www.comicbookherald.com/t/</link>"
           b"<pubDate>Mon, 10 Nov 2026 14:30:00</pubDate></item></channel></rss>")
    (item,) = parsear_feed(xml)
    assert item.publicado == datetime(2026, 11, 10, 14, 30, tzinfo=UTC)


def test_un_item_sin_fecha_es_valido():
    xml = (b'<?xml version="1.0"?><rss><channel><item>'
           b"<title>T</title><link>https://www.comicbookherald.com/t/</link>"
           b"</item></channel></rss>")
    (item,) = parsear_feed(xml)
    assert item.publicado is None and isinstance(item, HeraldItem)


@pytest.mark.parametrize("url", [
    "http://www.comicbookherald.com/x/",           # sin TLS
    "https://comicbookherald.com/x/",              # ápex: no es el host canónico del feed
    "https://www.comicbookherald.com:8443/x/",     # puerto no estándar
    "https://otro.example/x/",                     # host ajeno
])
def test_rechaza_esquema_apex_puerto_raro_y_otros_hosts(url):
    xml = (f"<rss version='2.0'><channel><item><title>T</title>"
           f"<link>{url}</link></item></channel></rss>").encode()
    assert parsear_feed(xml) == []


def test_acepta_el_puerto_443_explicito():
    xml = (b"<rss version='2.0'><channel><item><title>T</title>"
           b"<link>https://www.comicbookherald.com:443/ok/</link></item></channel></rss>")
    items = parsear_feed(xml)
    assert [item.url for item in items] == ["https://www.comicbookherald.com:443/ok/"]
