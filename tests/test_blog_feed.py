"""BLOG1: parser RSS/Atom y conector genérico de blogs (sin red)."""
from __future__ import annotations

from types import SimpleNamespace

from zascarr.services.blog_feed import (
    EntradaFeed,
    buscar_en_feed,
    parsear_feed,
    resultados_de_busqueda,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item><title>Batman 001</title><link>https://blog.example/post/1</link>
<pubDate>Mon, 01 Jan 2024 10:00:00 GMT</pubDate>
<enclosure url="https://blog.example/files/Batman001.torrent" type="application/x-bittorrent"/>
</item>
<item><title>Batman 002</title><link>https://blog.example/post/2</link>
<description>Descarga: magnet:?xt=urn:btih:abcdef0123456789&amp;dn=Batman2</description>
</item>
<item><title>Batman 003</title><link>https://blog.example/post/3</link>
<description>Solo un post, sin descarga.</description>
</item>
</channel></rss>"""

ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Batman 004</title><link rel="alternate" href="https://blog.example/4"/>
<updated>2024-01-01T10:00:00Z</updated>
<content type="html">ed2k://|file|Batman004.cbz|123|ABCDEF0123456789ABCDEF0123456789|/</content>
</entry>
</feed>"""


def test_parser_rss_extrae_directos_y_descarta_posts():
    entradas = parsear_feed(RSS)
    assert [e.titulo for e in entradas] == ["Batman 001", "Batman 002"]
    assert entradas[0].tipo == "torrent"
    assert entradas[0].descarga_url.endswith("Batman001.torrent")
    assert entradas[1].tipo == "magnet"
    assert "magnet:?xt=urn:btih:" in entradas[1].descarga_url


def test_parser_atom_ed2k_y_link_alternate():
    entradas = parsear_feed(ATOM)
    assert len(entradas) == 1
    assert entradas[0].enlace == "https://blog.example/4"
    assert entradas[0].tipo == "ed2k"
    assert entradas[0].descarga_url.startswith("ed2k://|file|")


def test_xml_roto_no_lanza():
    assert parsear_feed("<rss><channel><item>") == []
    assert parsear_feed("no es xml") == []


def test_filtro_de_terminos_y_una_letra():
    from zascarr.services import blog_feed
    xml = RSS
    entradas = [e for e in parsear_feed(xml)]
    assert len(entradas) == 2
    # misma regla que Prowlarr: todos los términos significativos
    assert [e.titulo for e in entradas if blog_feed._relevante(e.titulo, "batman 001")] == [
        "Batman 001"]
    # una sola letra no filtra
    assert blog_feed._relevante("cualquier cosa", "x")


async def test_buscar_en_feed_filtra_y_no_devuelve_post_sin_descarga(monkeypatch):
    from zascarr.services import blog_feed
    async def _descargar(*_a, **_k):
        return RSS
    monkeypatch.setattr(blog_feed, "_descargar", _descargar)
    entradas = await buscar_en_feed("https://blog.example/feed.xml", "Batman 001")
    assert [e.titulo for e in entradas] == ["Batman 001"]


def test_resultados_para_orquestador():
    e = EntradaFeed("Batman 001", "https://blog.example/1", None,
                    "magnet:?xt=urn:btih:abcdef", "magnet")
    [r] = resultados_de_busqueda([e], "https://blog.example/feed.xml")
    assert r.indexer == "blog:blog.example"
    assert r.download_url == e.descarga_url
    assert r.seeders == 0


def test_orquestador_considera_blog_fuente_y_no_descarta_torrent_sin_seeders():
    from zascarr.services.orchestrator import Orchestrator, hay_fuente_de_busqueda
    from zascarr.services.prowlarr import SearchResult
    settings = SimpleNamespace(
        prowlarr_enabled=False, forum_enabled=False, blog_feed_enabled=True,
        blog_feed_url="https://blog.example/feed.xml",
    )
    assert hay_fuente_de_busqueda(settings)
    orch = object.__new__(Orchestrator)
    resultado = SearchResult("Batman 001", "blog:blog.example",
                             "magnet:?xt=urn:btih:abc", 0, 0, "blog")
    assert Orchestrator._ranked_candidates(orch, [resultado], "Batman 001") == [resultado]


def test_activo_false_no_consulta_blog(monkeypatch):
    from zascarr.services import blog_feed
    llamado = False
    async def _descargar(*_a, **_k):
        nonlocal llamado
        llamado = True
        return RSS
    monkeypatch.setattr(blog_feed, "_descargar", _descargar)
    from zascarr.services.orchestrator import hay_fuente_de_busqueda
    assert not hay_fuente_de_busqueda(SimpleNamespace(
        prowlarr_enabled=False, forum_enabled=False, blog_feed_enabled=False,
        blog_feed_url=""))
    assert not llamado
