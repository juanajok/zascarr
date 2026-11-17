# ruff: noqa: E501
"""Pruebas del cliente de Fandom (DC/Marvel Database) — sin red real.

Patrón del repo: `httpx.MockTransport` y utilidades puras. Los wikitext de muestra salen de
páginas reales verificadas en vivo el 2026-11-13 (no inventados), recortados a los campos que
usa el cliente.
"""
from __future__ import annotations

import time
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from zascarr.models import ComicTradition
from zascarr.services.enricher import EnrichmentService
from zascarr.services.fandom import (
    MAX_CUERPO_API,
    MAX_TITULO_PAGINA,
    MAX_WIKITEXT,
    FandomClient,
    FandomMaxLagError,
    FandomPayloadError,
    anios_de_displaytitle,
    creditos_de_parametros,
    enlaces_de_issues,
    extraer_plantilla,
    fecha_de_parametros,
    fecha_inglesa,
    limpiar_markup,
    parametros_de_plantilla,
    primer_parrafo,
    referencia_de_issue,
    seccion,
    titulo_base,
)
from zascarr.utils.cortesia import (
    CortesiaProceso,
    FuenteApagada,
    fuente_de_host_portada,
    fuente_habilitada,
)
from zascarr.utils.peticiones import RespuestaNoTransitoria

WIKITEXT_DC_VOL = (
    "{{DC Database:Volume Template\n"
    "| IssueImage              = Batman 1.jpg\n"
    "| Type                    = Ongoing Series\n"
    "| TotalIssues             = 715\n"
    "| StartYear               = 1940\n"
    "| EndYear                 = 2011\n"
    "| StoryArcs               = [[Batman: Year One|Year One]]; "
    "[[Batman: Ten Nights of the Beast|Ten Nights of the Beast]]; "
    "[[Many Deaths of the Batman]]\n"
    "}}"
)

WIKITEXT_DC_COMIC = (
    "{{DC Database:Comic Template\n"
    "| Title               = Batman\n"
    "| Image               = Batman 404.jpg\n"
    "| Volume              = 1\n"
    "| Issue               = 404\n"
    "| Day                 = 21 <!-- GCD -->\n"
    "| Month               = 2\n"
    "| Year                = 1987\n"
    "| Pubmonth            = 10 <!-- GCD -->\n"
    "| Pubyear             = 1986\n"
    "| Writer1_1           = [[Frank Miller]]\n"
    "| Penciler1_1         = [[Dave Mazzucchelli]]\n"
    "| Inker1_1            = Dave Mazzucchelli\n"
    "| Editor1_1           = Dennis O'Neil\n"
    "| StoryTitle1         = Batman: Year One, Part 4\n"
    "| Synopsis1           = Batman y Gordon... '''texto''' con [[enlace|etiqueta]].\n"
    "}}"
)

WIKITEXT_MARVEL_VOL = (
    "{{Marvel Database:Volume Template\n"
    "| format = Ongoing Series\n"
    "| status = Finished\n"
    "}}"
)

WIKITEXT_MARVEL_COMIC = (
    "{{Marvel Database:Comic Template\n"
    "| Image1      = Fantastic Four Vol 1 1.jpg\n"
    "| ReleaseDate = August 8, 1961\n"
    "| Month       = November\n"
    "| Year        = 1961\n"
    "| Writer1_1   = Stan Lee\n"
    "| Penciler1_1 = Jack Kirby\n"
    "| Synopsis1   = The Fantastic Four debut.\n"
    "}}"
)

WIKITEXT_ARC = (
    "{{DC Database:Story Arc Template\n"
    "| Title = Batman: Year One\n"
    "}}\n"
    "'''Batman: Year One''' es un arco de [[Frank Miller]].\n\n"
    "== Issues ==\n"
    "* [[Batman Vol 1 404]]\n"
    "* [[Batman Vol 1 405]]\n"
    "* [[Batman Vol 1 405]]\n"
    "* [[Batman Vol 1 406]]\n"
    "== Notes ==\n"
    "* Nada relevante.\n"
)

CDN = "https://static.wikia.nocookie.net/marvel_dc/images/0/06/Batman_1.jpg/revision/latest"


def _ajustes(monkeypatch, **encendidas):
    ajustes = dict(
        comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False,
        gcd_enabled=False, metron_enabled=False, open_library_enabled=False,
        fandom_dc_enabled=True, fandom_marvel_enabled=True,
        comicvine_rate_limit=0.0, anilist_rate_limit=0.0, tebeosfera_rate_limit=0.0,
        gcd_rate_limit=0.0, metron_rate_limit=0.0, open_library_rate_limit=0.0,
        fandom_dc_rate_limit=0.0, fandom_marvel_rate_limit=0.0,
        forum_enabled=False, forum_url="",
    )
    ajustes.update(encendidas)
    falsos = SimpleNamespace(**ajustes)
    monkeypatch.setattr("zascarr.config.get_settings", lambda: falsos)
    return falsos


def _cliente(monkeypatch, rutas: dict, **encendidas) -> FandomClient:
    _ajustes(monkeypatch, **encendidas)

    def handler(request: httpx.Request) -> httpx.Response:
        parametros = dict(request.url.params)
        if parametros.get("list") == "search":
            return httpx.Response(200, json=rutas["search"])
        if parametros.get("prop") == "revisions":
            return httpx.Response(200, json={"query": {"pages": [{
                "title": parametros["titles"],
                "revisions": [{"slots": {"main": {"content":
                    rutas["wikitext:" + parametros["titles"]]}}}],
            }]}})
        if parametros.get("prop") == "imageinfo":
            return httpx.Response(200, json={"query": {"pages": [{
                "title": parametros["titles"],
                "imageinfo": [{"url": rutas["image"]}],
            }]}})
        if parametros.get("action") == "parse":
            return httpx.Response(200, json={"parse": {
                "displaytitle": rutas["displaytitle:" + parametros["page"]]}})
        return httpx.Response(404, text="no previsto")

    return FandomClient("dc.fandom.com", transporte=httpx.MockTransport(handler),
                        cortesia=CortesiaProceso())


# ── utilidades puras ───────────────────────────────────────────────────────────────────────────

def test_titulo_base_quita_volumen_y_colectado():
    assert titulo_base("Batman Vol 1") == "Batman"
    assert titulo_base("Fantastic Four Vol 3") == "Fantastic Four"
    assert titulo_base("Batman Archives Vol 1 (Collected)") == "Batman Archives"
    # Una página de NÚMERO no se confunde con una de volumen: no se le quita el «Vol N».
    assert titulo_base("Batman Vol 1 404") == "Batman Vol 1 404"


def test_plantilla_y_parametros():
    plantilla = extraer_plantilla(WIKITEXT_DC_VOL, "DC Database:Volume Template")
    assert plantilla is not None
    parametros = parametros_de_plantilla(plantilla)
    assert parametros["totalissues"] == "715"
    assert parametros["startyear"] == "1940"
    assert "[[Batman: Year One|Year One]]" in parametros["storyarcs"]


def test_limpiar_markup():
    crudo = "'''Batman''' y [[Gordon|Jim Gordon]]<!-- nota --> <ref>x</ref> [http://a b]"
    assert limpiar_markup(crudo) == "Batman y Jim Gordon b"


def test_fechas():
    assert fecha_inglesa("August 8, 1961") == date(1961, 8, 8)
    assert fecha_inglesa("8 August 1961") == date(1961, 8, 8)
    assert fecha_inglesa("Aug. 8, 1961") == date(1961, 8, 8)
    assert fecha_inglesa("1961-08-08") == date(1961, 8, 8)
    assert fecha_inglesa("sin fecha") is None
    # Batman Vol 1 404 real: portada 1987-02 (Month/Year) y venta 1986-10-21
    # (Pubmonth/Pubyear + Day). Manda la fecha de venta: es `Issue.release_date`.
    assert fecha_de_parametros({
        "day": "21 <!-- GCD -->", "month": "2", "year": "1987",
        "pubmonth": "10 <!-- GCD -->", "pubyear": "1986",
    }) == date(1986, 10, 21)
    assert fecha_de_parametros({"day": "7", "month": "March", "year": "1988",
                                "pubmonth": "March", "pubyear": "1988"}) == date(1988, 3, 7)
    # Respaldo: sin fecha de venta, la de portada (Month/Year) y el día declarado.
    assert fecha_de_parametros({"day": "21", "month": "2", "year": "1987"}) == date(1987, 2, 21)
    # Sin día, la fecha del mes se queda en el día 1 (el mes es el dato fiable).
    assert fecha_de_parametros({"pubmonth": "10", "pubyear": "1986"}) == date(1986, 10, 1)
    assert fecha_de_parametros({"month": "5", "year": "1987"}) == date(1987, 5, 1)
    assert fecha_de_parametros({"pubmonth": "10"}) is None


def test_creditos_por_rol():
    parametros = parametros_de_plantilla(
        extraer_plantilla(WIKITEXT_DC_COMIC, "DC Database:Comic Template"))
    creditos = creditos_de_parametros(parametros)
    assert creditos["writer"] == ["Frank Miller"]
    assert creditos["penciler"] == ["Dave Mazzucchelli"]
    assert creditos["inker"] == ["Dave Mazzucchelli"]
    assert creditos["editor"] == ["Dennis O'Neil"]


def test_anios_de_displaytitle():
    assert anios_de_displaytitle("Fantastic Four Vol 1<span> (1961–1996)</span>") == (1961, 1996)
    assert anios_de_displaytitle("Batman (1940—2011)") == (1940, 2011)
    assert anios_de_displaytitle(None) == (None, None)


def test_arcos_en_orden_de_lectura():
    issues = enlaces_de_issues(seccion(WIKITEXT_ARC, "Issues"))
    assert issues == ["Batman Vol 1 404", "Batman Vol 1 405", "Batman Vol 1 406"]


def test_referencia_de_issue():
    assert referencia_de_issue("Batman Vol 1 404") == ("Batman Vol 1", "404")
    assert referencia_de_issue("No es una página de número") is None


def test_cadena_de_fuentes_american_con_fandom():
    fuentes = [s[1] for s in EnrichmentService._sources_for(ComicTradition.AMERICAN)]
    assert fuentes == ["comic_vine", "fandom_dc", "fandom_marvel"]
    assert [s[1] for s in EnrichmentService._sources_for(ComicTradition.MANGA)] == ["anilist"]


# ── cliente con transporte simulado ───────────────────────────────────────────────────────────

async def test_busqueda_pages_devuelve_titulo_y_snippet(monkeypatch):
    cliente = _cliente(monkeypatch, {
        "search": {"query": {"search": [{
            "title": "Batman: Year One",
            "snippet": 'Un <span class="searchmatch">arco</span> de Batman.',
        }]}},
    })
    try:
        paginas = await cliente.search_pages("Batman Year One", limit=3)
    finally:
        await cliente.__aexit__()
    assert len(paginas) == 1
    assert paginas[0].title == "Batman: Year One"
    assert "arco" in paginas[0].snippet


async def test_busqueda_devuelve_titulos(monkeypatch):
    cliente = _cliente(monkeypatch, {
        "search": {"query": {"search": [{"title": "Batman Vol 1"},
                                        {"title": "Batman Vol 1 1"}]}},
    })
    try:
        assert await cliente.search_series("Batman") == ["Batman Vol 1", "Batman Vol 1 1"]
    finally:
        await cliente.__aexit__()


async def test_get_volume_dc(monkeypatch):
    cliente = _cliente(monkeypatch, {
        "wikitext:Batman Vol 1": WIKITEXT_DC_VOL,
        "image": CDN,
    })
    try:
        volumen = await cliente.get_volume("Batman Vol 1")
    finally:
        await cliente.__aexit__()
    assert volumen is not None
    assert volumen.title == "Batman"
    assert volumen.start_year == 1940 and volumen.end_year == 2011
    assert volumen.total_issues == 715
    assert volumen.cover_url == CDN
    assert volumen.story_arcs == [
        "Batman: Year One", "Batman: Ten Nights of the Beast", "Many Deaths of the Batman"]


async def test_get_volume_sin_portada_no_pide_imageinfo(monkeypatch):
    """Si la serie ya tiene portada, `incluir_portada=False` ahorra la petición `imageinfo`."""
    _ajustes(monkeypatch)
    peticiones: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        parametros = dict(request.url.params)
        peticiones.append(parametros)
        if parametros.get("prop") == "revisions":
            return httpx.Response(200, json={"query": {"pages": [{
                "title": parametros["titles"],
                "revisions": [{"slots": {"main": {"content": WIKITEXT_DC_VOL}}}],
            }]}})
        return httpx.Response(404, text="no previsto")

    cliente = FandomClient("dc.fandom.com", transporte=httpx.MockTransport(handler),
                           cortesia=CortesiaProceso())
    try:
        volumen = await cliente.get_volume("Batman Vol 1", incluir_portada=False)
    finally:
        await cliente.__aexit__()
    assert volumen is not None and volumen.cover_url is None
    assert all(p.get("prop") != "imageinfo" for p in peticiones)


def test_gate_de_portadas_del_cdn_comun_de_fandom():
    """AC-12: el CDN es común a las dos wikis; solo se corta si AMBAS están apagadas."""
    assert fuente_de_host_portada("static.wikia.nocookie.net") == "fandom"
    assert fuente_habilitada("fandom", SimpleNamespace(
        fandom_dc_enabled=False, fandom_marvel_enabled=False)) is False
    assert fuente_habilitada("fandom", SimpleNamespace(
        fandom_dc_enabled=True, fandom_marvel_enabled=False)) is True
    assert fuente_habilitada("fandom", SimpleNamespace(
        fandom_dc_enabled=False, fandom_marvel_enabled=True)) is True


def test_atribucion_fandom_enlaza_articulo_y_licencia():
    """SCR2: el doble enlace legal usa el slug como título de página, sin hotlinking."""
    from zascarr.models import Series
    from zascarr.web.series import atribucion_fandom

    serie = Series(title="Batman", fandom_dc_slug="Batman Vol 1")
    datos = atribucion_fandom(serie)
    assert datos is not None
    assert datos["nombre"] == "DC Database"
    assert datos["url_articulo"] == "https://dc.fandom.com/wiki/Batman_Vol_1"
    assert datos["url_licencia"] == "https://creativecommons.org/licenses/by-sa/3.0/"
    marvel = Series(title="Fantastic Four", fandom_marvel_slug="Fantastic Four Vol 1")
    datos_marvel = atribucion_fandom(marvel)
    assert datos_marvel is not None
    assert datos_marvel["nombre"] == "Marvel Database"
    assert datos_marvel["url_articulo"] == "https://marvel.fandom.com/wiki/Fantastic_Four_Vol_1"
    assert atribucion_fandom(Series(title="Sin fuente")) is None


async def test_get_volume_marvel_usa_displaytitle(monkeypatch):
    cliente = _cliente(monkeypatch, {
        "wikitext:Fantastic Four Vol 1": WIKITEXT_MARVEL_VOL,
        "displaytitle:Fantastic Four Vol 1":
            "Fantastic Four Vol 1<span> (1961–1996)</span>",
        "image": CDN,
    }, fandom_marvel_enabled=True)
    cliente._host = "marvel.fandom.com"
    cliente._fuente = "fandom_marvel"
    try:
        volumen = await cliente.get_volume("Fantastic Four Vol 1")
    finally:
        await cliente.__aexit__()
    assert volumen is not None
    assert volumen.title == "Fantastic Four"
    assert (volumen.start_year, volumen.end_year) == (1961, 1996)


async def test_get_issue_dc(monkeypatch):
    cliente = _cliente(monkeypatch, {
        "wikitext:Batman Vol 1 404": WIKITEXT_DC_COMIC,
        "image": CDN,
    })
    try:
        issue = await cliente.get_issue("Batman Vol 1 404")
    finally:
        await cliente.__aexit__()
    assert issue is not None
    # Fecha de VENTA (Pubmonth/Pubyear + Day), no la de portada: parámetros reales del
    # número 404 de Batman Vol 1 (Day=21, Month=2, Year=1987, Pubmonth=10, Pubyear=1986).
    assert issue.release_date == date(1986, 10, 21)
    assert issue.story_title == "Batman: Year One, Part 4"
    assert "Batman y Gordon" in issue.synopsis
    assert issue.credits["writer"] == ["Frank Miller"]
    assert issue.cover_url == CDN


async def test_get_issue_marvel(monkeypatch):
    cliente = _cliente(monkeypatch, {
        "wikitext:Fantastic Four Vol 1 1": WIKITEXT_MARVEL_COMIC,
        "image": CDN,
    }, fandom_marvel_enabled=True)
    cliente._host = "marvel.fandom.com"
    cliente._fuente = "fandom_marvel"
    try:
        issue = await cliente.get_issue("Fantastic Four Vol 1 1")
    finally:
        await cliente.__aexit__()
    assert issue is not None
    assert issue.release_date == date(1961, 8, 8)
    assert issue.credits["penciler"] == ["Jack Kirby"]


async def test_get_arc(monkeypatch):
    cliente = _cliente(monkeypatch, {"wikitext:Batman: Year One": WIKITEXT_ARC})
    try:
        arco = await cliente.get_arc("Batman: Year One")
    finally:
        await cliente.__aexit__()
    assert arco is not None
    assert arco.title == "Batman: Year One"
    assert arco.issues == ["Batman Vol 1 404", "Batman Vol 1 405", "Batman Vol 1 406"]


async def test_missingtitle_es_none(monkeypatch):
    cliente = _cliente(monkeypatch, {})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": "missingtitle", "info": "x"}})
    cliente._transporte = httpx.MockTransport(handler)
    try:
        assert await cliente.get_volume("No Existente Vol 1") is None
    finally:
        await cliente.__aexit__()


async def test_maxlag_lanza_y_bloquea_cortesia(monkeypatch):
    cliente = _cliente(monkeypatch, {})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": "maxlag", "lag": 12}},
                              headers={"retry-after": "20"})
    cliente._transporte = httpx.MockTransport(handler)
    try:
        with pytest.raises(FandomMaxLagError) as exc:
            await cliente.search_series("Batman")
    finally:
        await cliente.__aexit__()
    assert exc.value.retry_after_s == 20.0


async def test_error_desconocido(monkeypatch):
    cliente = _cliente(monkeypatch, {})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": "internal_api_error"}})
    cliente._transporte = httpx.MockTransport(handler)
    try:
        with pytest.raises(FandomPayloadError):
            await cliente.search_series("Batman")
    finally:
        await cliente.__aexit__()


async def test_404_lanza_respuesta_no_transitoria(monkeypatch):
    cliente = _cliente(monkeypatch, {})
    cliente._transporte = httpx.MockTransport(
        lambda request: httpx.Response(404, text="no está"))
    try:
        with pytest.raises(RespuestaNoTransitoria):
            await cliente.get_issue("Batman Vol 1 404")
    finally:
        await cliente.__aexit__()


async def test_fuente_apagada_no_envia(monkeypatch):
    _ajustes(monkeypatch, fandom_dc_enabled=False)
    peticiones: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        return httpx.Response(200, json={})
    cliente = FandomClient("dc.fandom.com", transporte=httpx.MockTransport(handler),
                           cortesia=CortesiaProceso())
    try:
        with pytest.raises(FuenteApagada):
            await cliente.search_series("Batman")
    finally:
        await cliente.__aexit__()
    assert peticiones == []


def test_primer_parrafo_ignora_plantillas():
    assert primer_parrafo(WIKITEXT_DC_VOL) is None
    assert primer_parrafo(WIKITEXT_ARC) == "Batman: Year One es un arco de Frank Miller."


# ── M-1 de SecOps: parseo acotado y tope de tamaño ─────────────────────────────────────────────

def _cliente_con_cuerpo(monkeypatch, cuerpo: bytes) -> FandomClient:
    """Cliente cuyo transporte devuelve siempre `cuerpo` en el cuerpo HTTP."""
    _ajustes(monkeypatch)
    cliente = FandomClient(
        "dc.fandom.com",
        transporte=httpx.MockTransport(lambda _r: httpx.Response(200, content=cuerpo)),
        cortesia=CortesiaProceso(),
    )
    return cliente


async def test_cuerpo_de_api_demasiado_grande_no_se_parsea(monkeypatch):
    cliente = _cliente_con_cuerpo(monkeypatch, b"{" + b"x" * MAX_CUERPO_API)
    try:
        # Si se intentara `respuesta.json()` lanzaría; el tope debe devolver None antes.
        assert await cliente.get_volume("Batman Vol 1") is None
    finally:
        await cliente.__aexit__()


async def test_wikitext_demasiado_grande_no_se_parsea(monkeypatch):
    contenido = "x" * (MAX_WIKITEXT + 1)
    _ajustes(monkeypatch)
    cuerpo = (
        '{"query": {"pages": [{"title": "Batman Vol 1", "revisions": '
        '[{"slots": {"main": {"content": ' + __import__("json").dumps(contenido) + "}}}]}]}}"
    ).encode()
    assert len(cuerpo) < MAX_CUERPO_API
    cliente = _cliente_con_cuerpo(monkeypatch, cuerpo)
    try:
        assert await cliente.get_volume("Batman Vol 1") is None
    finally:
        await cliente.__aexit__()


async def test_codigo_de_error_de_mediawiki_se_sanea_en_la_excepcion(monkeypatch):
    """m-4: el `code` de terceros no puede forjar líneas de log (saltos/ANSI fuera)."""
    import json

    codigo = "internal_api_error\nFORJADO\x1b[31m"
    cliente = _cliente_con_cuerpo(
        monkeypatch, json.dumps({"error": {"code": codigo}}).encode())
    try:
        with pytest.raises(FandomPayloadError) as exc:
            await cliente.search_series("Batman")
    finally:
        await cliente.__aexit__()
    assert "\n" not in str(exc.value) and "\x1b" not in str(exc.value)
    assert "\n" not in exc.value.code and len(exc.value.code) <= 40


def test_parseo_de_wikitext_malformado_es_lineal():
    """M-1: entradas patológicas de 200k no pueden colgar el parser (presupuesto < 1 s)."""
    casos: list[tuple[str, object]] = [
        ("limpiar_markup('<')", lambda: limpiar_markup("<" * 200_000)),
        ("limpiar_markup('_')", lambda: limpiar_markup("_" * 200_000)),
        ("limpiar_markup('=')", lambda: limpiar_markup("=" * 200_000)),
        ("limpiar_markup('[')", lambda: limpiar_markup("[" * 200_000)),
        ("comentario sin cierre", lambda: limpiar_markup("<!--" + "x" * 200_000)),
        ("ref sin cierre", lambda: limpiar_markup("<ref>" + "x" * 200_000)),
        ("seccion con '='", lambda: seccion("=" * 200_000, "Issues")),
        ("plantilla sin cierre", lambda: extraer_plantilla(
            "{{DC Database:Volume Template" + "x" * 200_000,
            "DC Database:Volume Template")),
        ("enlaces con '['", lambda: enlaces_de_issues("[" * 200_000)),
    ]
    for nombre, accion in casos:
        inicio = time.perf_counter()
        accion()
        transcurrido = time.perf_counter() - inicio
        assert transcurrido < 1.0, f"{nombre}: {transcurrido:.3f} s"


# ── RES-1/RES-2 de SecOps (re-verificación de M-1) ──────────────────────────────────────────────

def test_fecha_inglesa_es_lineal_con_letras_hostiles():
    """RES-1: `[A-Za-z]+` sin tope hacía cuadrático el `search` (20k letras → 6,2 s)."""
    for texto in ("A" * 20_000, "Aug " * 5_000, "A" * 1_000_000):
        inicio = time.perf_counter()
        assert fecha_inglesa(texto) is None
        transcurrido = time.perf_counter() - inicio
        assert transcurrido < 1.0, f"{len(texto)} letras: {transcurrido:.3f} s"
    # Las fechas válidas se siguen reconociendo con el patrón acotado.
    assert fecha_inglesa("August 8, 1961") == date(1961, 8, 8)
    assert fecha_inglesa("8 August 1961") == date(1961, 8, 8)


async def test_get_issue_marvel_con_releasedate_hostil_no_bloquea(monkeypatch):
    """RES-1 end-to-end: una fecha de 20k letras no cuelga `get_issue` (antes 6,3 s)."""
    wikitext = WIKITEXT_MARVEL_COMIC.replace("August 8, 1961", "A" * 20_000)
    cliente = _cliente(monkeypatch, {
        "wikitext:Fantastic Four Vol 1 1": wikitext,
        "image": CDN,
    }, fandom_marvel_enabled=True)
    cliente._host = "marvel.fandom.com"
    cliente._fuente = "fandom_marvel"
    try:
        inicio = time.perf_counter()
        issue = await cliente.get_issue("Fantastic Four Vol 1 1")
        transcurrido = time.perf_counter() - inicio
    finally:
        await cliente.__aexit__()
    assert issue is not None and issue.release_date is None
    assert transcurrido < 1.0, f"{transcurrido:.3f} s"


def test_titulo_base_acota_titulos_hostiles():
    """RES-2: rachas de espacios en el título no pueden hacer cuadrático `titulo_base`."""
    hostil = "Batman" + " " * 20_000 + "Vol 1"
    inicio = time.perf_counter()
    base = titulo_base(hostil)
    transcurrido = time.perf_counter() - inicio
    assert transcurrido < 1.0, f"{transcurrido:.3f} s"
    assert len(base) <= MAX_TITULO_PAGINA
    # El comportamiento normal no cambia.
    assert titulo_base("Batman Vol 1") == "Batman"
    assert titulo_base("Batman Archives Vol 1 (Collected)") == "Batman Archives"


def test_issues_de_valor_de_arc():
    """La plantilla de arco declara sus números con {{c|…}}; los tomos ({{co|…}}) no cuentan."""
    from zascarr.services.fandom import issues_de_valor_de_arc

    valor = ('* {{c|Batman Vol 1 404}} -- "Chapter One: Who I Am"\n'
             '* {{c|Batman Vol 1 405}} -- "Chapter Two"\n'
             "* {{co|Batman: Year One (Collected)}}\n"
             "* [[Batman Vol 1 406|Batman #406]]")
    assert issues_de_valor_de_arc(valor) == [
        "Batman Vol 1 404", "Batman Vol 1 405", "Batman Vol 1 406"]
    assert issues_de_valor_de_arc(None) == []


# ── SCR1: caché HTTP condicional en el cliente real ───────────────────────────────────────────
# Se prueban AC-06 (missingtitle negativo / maxlag no cacheado) y AC-11 (fuente apagada antes
# de la caché). La caché es la falsa de `test_cache_http`; el reloj es el de esa suite.

def _cliente_cache(monkeypatch, handler, cache, *, robots=None, **encendidas):
    """Cliente Fandom con la caché falsa inyectada y el `MockTransport` dado."""
    from tests.test_cache_http import CacheHttpFalsa  # noqa: F401 — documenta el contrato

    _ajustes(monkeypatch, **encendidas)
    return FandomClient("dc.fandom.com", transporte=httpx.MockTransport(handler),
                        cortesia=CortesiaProceso(), cache=cache, robots=robots)


async def test_missingtitle_se_cachea_negativo_y_no_repite(monkeypatch):
    from tests.test_cache_http import CacheHttpFalsa, Reloj
    from zascarr.utils.robots import GestorRobots

    peticiones: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        return httpx.Response(200, json={"error": {"code": "missingtitle", "info": "x"}})

    cache = CacheHttpFalsa()
    reloj = Reloj()
    cliente = _cliente_cache(monkeypatch, handler, cache,
                             robots=GestorRobots(reloj=reloj))
    try:
        assert await cliente.get_volume("No Existe Vol 1") is None
        assert await cliente.get_volume("No Existe Vol 1") is None
    finally:
        await cliente.__aexit__()
    assert len([u for u in peticiones if "/api.php" in u]) == 1   # la 2.ª sale de la negativa
    filas = [f for f in cache.filas.values() if "/api.php" in f.url_canonical]
    assert len(filas) == 1 and filas[0].is_negative and filas[0].status_code == 200
    assert filas[0].body_zlib                     # conserva el JSON de `missingtitle`


async def test_maxlag_no_se_cachea(monkeypatch):
    from tests.test_cache_http import CacheHttpFalsa, Reloj
    from zascarr.utils.robots import GestorRobots

    peticiones: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        return httpx.Response(200, json={"error": {"code": "maxlag", "lag": 12}},
                              headers={"retry-after": "1"})

    reloj = Reloj()
    cortesia = CortesiaProceso(reloj=reloj, dormir=reloj.dormir)
    cache = CacheHttpFalsa()
    _ajustes(monkeypatch)
    cliente = FandomClient("dc.fandom.com", transporte=httpx.MockTransport(handler),
                           cortesia=cortesia, reloj=reloj, dormir=reloj.dormir,
                           cache=cache, robots=GestorRobots(reloj=reloj))
    try:
        with pytest.raises(FandomMaxLagError):
            await cliente.get_volume("Batman Vol 1")
        reloj.t += 60                              # pasa el bloqueo compartido por maxlag
        with pytest.raises(FandomMaxLagError):
            await cliente.get_volume("Batman Vol 1")
    finally:
        await cliente.__aexit__()
    # Ningún fallo lógico se cachea: dos llamadas al API = dos peticiones (no hay fila /api.php).
    assert len([u for u in peticiones if "/api.php" in u]) == 2
    assert not [f for f in cache.filas.values() if "/api.php" in f.url_canonical]


async def test_404_de_la_api_se_recuerda_y_se_relanza(monkeypatch):
    from tests.test_cache_http import CacheHttpFalsa, Reloj
    from zascarr.utils.robots import GestorRobots

    peticiones: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        return httpx.Response(404)

    cache = CacheHttpFalsa()
    reloj = Reloj()
    cliente = _cliente_cache(monkeypatch, handler, cache,
                             robots=GestorRobots(reloj=reloj))
    try:
        for _ in range(2):
            with pytest.raises(RespuestaNoTransitoria) as exc:
                await cliente.get_volume("Batman Vol 1")
            assert exc.value.codigo == 404
    finally:
        await cliente.__aexit__()
    assert len([u for u in peticiones if "/api.php" in u]) == 1   # 2.ª desde la negativa


async def test_fuente_apagada_con_cache_no_lee_ni_pide(monkeypatch):
    from tests.test_cache_http import CacheHttpFalsa

    peticiones = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        return httpx.Response(200, json={})

    cache = CacheHttpFalsa()
    cliente = _cliente_cache(monkeypatch, handler, cache, fandom_dc_enabled=False)
    try:
        with pytest.raises(FuenteApagada):
            await cliente.get_volume("Batman Vol 1")
    finally:
        await cliente.__aexit__()
    assert peticiones == 0 and cache.leidas == 0      # ni socket ni lectura de caché
