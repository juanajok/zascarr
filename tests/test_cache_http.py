# ruff: noqa: E501
"""`utils/cache_http.py`: hit, 304, negativas, singleflight, bypass y topes (SCR1).

Sin red real ni Postgres: `httpx.MockTransport`, una caché en memoria (`CacheHttpFalsa`),
reloj simulado y un espía de la cortesía. Los criterios son los AC-01 a AC-05, AC-09, AC-10
y AC-11 de `docs/design/especificacion-SCR1-robots-cache.md`.
"""
from __future__ import annotations

import asyncio
import zlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from zascarr.utils.cache_http import (
    MAX_CUERPO_CACHE,
    FilaCache,
    PoliticaCacheDominio,
    candado_de_singleflight,
    comprimir_cuerpo,
    descomprimir_cuerpo,
    normalizar_y_hashear_url,
    pedir_con_cache,
    reiniciar_candados_para_pruebas,
)
from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    CortesiaProceso,
    FuenteApagada,
    PoliticaFuente,
)
from zascarr.utils.peticiones import (
    CuerpoDemasiadoGrande,
    ReintentosAgotados,
    RespuestaNoTransitoria,
)
from zascarr.utils.robots import GestorRobots

URL = "https://dc.fandom.com/api.php?action=query&titles=Batman+Vol+1"
POLITICA_CACHE = PoliticaCacheDominio(
    ttl_positivo=timedelta(hours=24),
    margen_retencion_304=timedelta(days=14),
    ttl_negativo=timedelta(hours=12),
    codigos_negativos=frozenset({404, 410}),
)


class Reloj:
    def __init__(self, inicio: float = 1000.0):
        self.t = inicio
        self.dormidos: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.dormidos.append(segundos)
        await asyncio.sleep(0)
        self.t += segundos


class RelojFecha:
    def __init__(self):
        self.t = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.t

    def avanzar(self, **kwargs) -> None:
        self.t += timedelta(**kwargs)


class CortesiaEspia(CortesiaProceso):
    """Cuenta las autorizaciones de cortesía (un hit no debe gastar ninguna)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.llamadas: list[tuple[str, str]] = []

    async def esperar(self, *args, **kwargs):
        self.llamadas.append((args[0], args[1]))
        return await super().esperar(*args, **kwargs)


class CacheHttpFalsa:
    """Implementa `CacheHttpProtocolo` en un dict; cuenta lecturas/escrituras/renovaciones."""

    def __init__(self):
        self.filas: dict[str, FilaCache] = {}
        self.leidas = 0
        self.escrituras: list[FilaCache] = []
        self.renovaciones = 0
        self.purgas = 0

    async def leer(self, url_hash: str) -> FilaCache | None:
        self.leidas += 1
        return self.filas.get(url_hash)

    async def escribir(self, fila: FilaCache) -> None:
        self.escrituras.append(fila)
        self.filas[fila.url_hash] = fila

    async def renovar(self, url_hash: str, *, fetched_at: datetime,
                      fresh_until: datetime, retain_until: datetime) -> int:
        fila = self.filas.get(url_hash)
        if fila is None:
            return 0
        self.filas[url_hash] = replace(fila, fetched_at=fetched_at,
                                       fresh_until=fresh_until, retain_until=retain_until)
        self.renovaciones += 1
        return 1

    async def purgar(self, ahora: datetime | None = None) -> int:
        self.purgas += 1
        return 0


class TransporteLento(httpx.AsyncBaseTransport):
    """Transporte que anota peticiones y cede el bucle, para probar solapamiento real."""

    def __init__(self, responder, pausa: float = 0.02):
        self.peticiones = 0
        self.cabeceras: list[httpx.Headers] = []
        self._responder = responder
        self._pausa = pausa

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.peticiones += 1
        self.cabeceras.append(request.headers)
        await asyncio.sleep(self._pausa)
        return self._responder(request)


@pytest.fixture(autouse=True)
def _candados_limpios():
    reiniciar_candados_para_pruebas()
    yield
    reiniciar_candados_para_pruebas()


@pytest.fixture
def fuente_encendida(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: SimpleNamespace(
        fandom_dc_enabled=True, fandom_marvel_enabled=False))


def _politica(**kwargs) -> PoliticaFuente:
    base = dict(fuente="fandom_dc", nombre="DC Database", intervalo_min_s=0.0,
                max_intentos=1, max_redirecciones=3)
    base.update(kwargs)
    return PoliticaFuente(**base)


def _entorno(pausa: float = 0.0):
    reloj = Reloj()
    fecha = RelojFecha()
    cortesia = CortesiaEspia(reloj=reloj, dormir=reloj.dormir)
    return reloj, fecha, cortesia


async def _pedir(cliente, cache, cortesia, reloj, fecha, **kwargs) -> httpx.Response:
    return await pedir_con_cache(
        cliente, "GET", kwargs.pop("url", URL),
        politica=kwargs.pop("politica", _politica()),
        politica_cache=kwargs.pop("politica_cache", POLITICA_CACHE),
        cache=cache,
        robots=kwargs.pop("robots", None),
        espera_max_s=kwargs.pop("espera_max_s", 5.0),
        cortesia=cortesia, reloj=reloj, dormir=reloj.dormir, ahora=fecha,
        **kwargs,
    )


# ── AC-02: un hit no gasta turno ni socket ─────────────────────────────────────────────────────

async def test_hit_sin_turno_ni_socket(fuente_encendida):
    peticiones: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        return httpx.Response(200, content=b'{"ok":true}',
                              headers={"content-type": "application/json"})

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        primera = await _pedir(cliente, cache, cortesia, reloj, fecha)
        llamadas = len(cortesia.llamadas)
        segunda = await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert primera.content == segunda.content == b'{"ok":true}'
    assert len(peticiones) == 1
    assert len(cortesia.llamadas) == llamadas          # el hit no reserva cortesía
    assert segunda.headers["x-zascarr-cache"] == "hit"
    assert segunda.headers["content-type"] == "application/json"


# ── AC-03: stale + 304 renueva sin bajar cuerpo ───────────────────────────────────────────────

async def test_304_renueva_y_conserva_el_cuerpo(fuente_encendida):
    peticiones: list[httpx.Request] = []
    respuestas = [httpx.Response(200, content=b'{"v":1}', headers={
        "content-type": "application/json", "etag": '"abc"'}), httpx.Response(304)]

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return respuestas.pop(0) if respuestas else httpx.Response(500)

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        await _pedir(cliente, cache, cortesia, reloj, fecha)
    url_hash, _, _ = normalizar_y_hashear_url("GET", URL)
    fila = cache.filas[url_hash]
    cuerpo = fila.body_zlib
    fecha.avanzar(hours=25)                            # vencida: toca revalidar
    respuestas.append(httpx.Response(304))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        revalidada = await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert peticiones[-1].headers["if-none-match"] == '"abc"'
    assert revalidada.status_code == 200 and revalidada.content == b'{"v":1}'
    assert revalidada.headers["x-zascarr-cache"] == "revalidada"
    renovada = cache.filas[url_hash]
    assert renovada.fresh_until > fila.fresh_until
    assert renovada.body_zlib == cuerpo and renovada.etag == '"abc"'
    assert cache.renovaciones == 1


# ── AC-04: negativa corta por código HTTP ─────────────────────────────────────────────────────

async def test_negativa_404_se_recuerda_y_expira(fuente_encendida):
    peticiones = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        return httpx.Response(404)

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        for _ in range(2):                             # 1.ª a red + 2.ª desde la negativa
            with pytest.raises(RespuestaNoTransitoria) as exc:
                await _pedir(cliente, cache, cortesia, reloj, fecha)
            assert exc.value.codigo == 404
        assert peticiones == 1
        fila = cache.filas[next(iter(cache.filas))]
        assert fila.is_negative and fila.body_zlib is None
        assert fila.fresh_until == fila.retain_until
        fecha.avanzar(hours=13)                        # pasada la TTL negativa
        with pytest.raises(RespuestaNoTransitoria):
            await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert peticiones == 2


# ── AC-05: 429/5xx/red no se cachean ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("modo", ["429", "500", "red"])
async def test_transitorios_no_crean_fila(fuente_encendida, modo):
    peticiones = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        if modo == "429":
            return httpx.Response(429, headers={"retry-after": "1"})
        return httpx.Response(500)

    def handler_red(request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        raise httpx.ConnectError("sin red", request=request)

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    transporte = httpx.MockTransport(handler if modo != "red" else handler_red)
    async with httpx.AsyncClient(transport=transporte) as cliente:
        for _ in range(2):
            with pytest.raises(ReintentosAgotados):
                await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert cache.filas == {}
    assert peticiones == 2


# ── AC-01: singleflight (misma URL y robots por origen) ───────────────────────────────────────

async def test_singleflight_una_peticion_para_la_misma_url(fuente_encendida):
    transporte = TransporteLento(lambda _r: httpx.Response(
        200, content=b'{"ok":1}', headers={"content-type": "application/json"}))
    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=transporte) as cliente:
        respuestas = await asyncio.gather(
            *[_pedir(cliente, cache, cortesia, reloj, fecha) for _ in range(5)])
    assert transporte.peticiones == 1
    assert all(r.status_code == 200 for r in respuestas)
    assert sum(1 for r in respuestas if r.headers.get("x-zascarr-cache") == "hit") == 4


async def test_singleflight_de_robots_una_fetch_por_origen(fuente_encendida):
    peticiones: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(str(request.url))
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow:\n")
        return httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    robots = GestorRobots(reloj=reloj)
    urls = [f"https://dc.fandom.com/api.php?action=query&titles=X{i}" for i in range(5)]
    async with httpx.AsyncClient(transport=TransporteLento(handler)) as cliente:
        await asyncio.gather(*[
            _pedir(cliente, cache, cortesia, reloj, fecha, robots=robots, url=url)
            for url in urls])
    assert len([p for p in peticiones if p.endswith("/robots.txt")]) == 1
    assert len([p for p in peticiones if "/api.php" in p]) == 5


# ── AC-09: tope de cuerpo y purga ────────────────────────────────────────────────────────────

async def test_cuerpo_grande_no_se_persiste(fuente_encendida):
    grande = b"x" * (MAX_CUERPO_CACHE + 1)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=grande)

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        respuesta = await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert respuesta.content == grande
    assert cache.filas == {}


def test_compresion_con_tope_y_filas_corruptas():
    datos = b"hola" * 1000
    assert descomprimir_cuerpo(comprimir_cuerpo(datos)) == datos
    assert comprimir_cuerpo(b"x" * (MAX_CUERPO_CACHE + 1)) is None
    assert descomprimir_cuerpo(b"no es zlib") is None
    truncado = zlib.compress(datos)[:-3]
    assert descomprimir_cuerpo(truncado) is None
    demasiado = zlib.compress(b"x" * (MAX_CUERPO_CACHE + 1))
    assert descomprimir_cuerpo(demasiado) is None


# ── AC-10: URL canónica, hash y bypass ───────────────────────────────────────────────────────

def test_canonica_ordena_query_quita_credenciales_y_redacta():
    primero = normalizar_y_hashear_url(
        "GET", "https://user:clave@DC.Fandom.com:443/api.php?b=2&a=1")
    segundo = normalizar_y_hashear_url("GET", "https://dc.fandom.com/api.php?a=1&b=2")
    assert primero[0] == segundo[0] and primero[1] == segundo[1]
    assert "user" not in primero[1] and "clave" not in primero[1]
    assert primero[2] == "dc.fandom.com"
    con_clave = normalizar_y_hashear_url(
        "GET", "https://dc.fandom.com/api.php?api_key=SECRETO&a=1")
    assert "SECRETO" not in con_clave[1] and "REDACTADO" in con_clave[1]
    otra_clave = normalizar_y_hashear_url(
        "GET", "https://dc.fandom.com/api.php?api_key=OTRA&a=1")
    assert otra_clave[0] != con_clave[0]              # dos claves no colapsan
    assert normalizar_y_hashear_url("POST", URL)[0] != normalizar_y_hashear_url("GET", URL)[0]


async def test_bypass_va_a_la_red_y_reescribe(fuente_encendida):
    peticiones = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        return httpx.Response(200, content=f'{{"n":{peticiones}}}'.encode(),
                              headers={"content-type": "application/json"})

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        assert (await _pedir(cliente, cache, cortesia, reloj, fecha)).json() == {"n": 1}
        forzada = await _pedir(cliente, cache, cortesia, reloj, fecha, bypass_cache=True)
        assert forzada.json() == {"n": 2}
        desde_cache = await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert peticiones == 2
    assert desde_cache.json() == {"n": 2}
    assert desde_cache.headers["x-zascarr-cache"] == "hit"


# ── AC-11: fuente apagada antes de caché y robots ────────────────────────────────────────────

async def test_fuente_apagada_antes_de_cache_y_robots(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: SimpleNamespace(
        fandom_dc_enabled=False, fandom_marvel_enabled=False))
    peticiones = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n")

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    robots = GestorRobots(reloj=reloj)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        with pytest.raises(FuenteApagada):
            await _pedir(cliente, cache, cortesia, reloj, fecha, robots=robots)
    assert cache.leidas == 0 and peticiones == 0


async def test_solo_admite_get(fuente_encendida):
    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient() as cliente:
        with pytest.raises(ValueError):
            await pedir_con_cache(cliente, "POST", URL, politica=_politica(),
                                  politica_cache=POLITICA_CACHE, cache=cache,
                                  espera_max_s=1.0, cortesia=cortesia,
                                  reloj=reloj, dormir=reloj.dormir, ahora=fecha)


async def test_el_candado_que_no_cede_es_espera_visible(fuente_encendida):
    peticiones = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal peticiones
        peticiones += 1
        return httpx.Response(200, content=b"{}")

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    url_hash, _, _ = normalizar_y_hashear_url("GET", URL)
    candado = candado_de_singleflight(url_hash)
    await candado.acquire()
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
            with pytest.raises(CortesiaEnEspera) as exc:
                await _pedir(cliente, cache, cortesia, reloj, fecha, espera_max_s=0.01)
    finally:
        candado.release()
    assert exc.value.motivo == "candado" and peticiones == 0


async def test_crawl_delay_de_robots_sube_el_intervalo_de_cortesia(fuente_encendida):
    """AC-07: el `Crawl-delay` de robots.txt se aplica como intervalo mínimo de la política."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nCrawl-delay: 4\n")
        return httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    robots = GestorRobots(reloj=reloj)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        await _pedir(cliente, cache, cortesia, reloj, fecha, robots=robots)
    assert any(espera == pytest.approx(4.0) for espera in reloj.dormidos)


# ── SecOps M-1/M-2: credenciales y redacción ──────────────────────────────────────────────────

async def test_con_credenciales_no_lee_ni_escribe_cache(fuente_encendida):
    """M-1: la caché es por URL y no distingue quién pregunta; con credenciales no se usa."""
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return httpx.Response(200, content=b'{"ok":true}',
                              headers={"content-type": "application/json"})

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        primera = await _pedir(cliente, cache, cortesia, reloj, fecha,
                               cabeceras={"Authorization": "Bearer secreto"})
        segunda = await _pedir(cliente, cache, cortesia, reloj, fecha,
                               cabeceras={"Authorization": "Bearer secreto"})
    assert primera.content == segunda.content == b'{"ok":true}'
    assert cache.leidas == 0 and cache.escrituras == []   # ni lectura ni escritura
    assert len(peticiones) == 2                            # siempre red, nunca hit


def test_canonica_redacta_parametros_sensibles():
    """M-2: los nombres habituales de credenciales en query no llegan a `url_canonical`."""
    _, canonica, _ = normalizar_y_hashear_url(
        "GET", "https://x.example/api?api-key=SECRETO&client_secret=OTRO&a=1")
    assert "SECRETO" not in canonica and "OTRO" not in canonica
    assert canonica.count("REDACTADO") == 2


# ── RES-3 (#812): un cuerpo enorme se propaga y no escribe caché ni negativa ──────────────

async def test_un_cuerpo_enorme_se_propaga_sin_escribir_cache(fuente_encendida, monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: SimpleNamespace(
        fandom_dc_enabled=True, fandom_marvel_enabled=False,
        max_cuerpo_transfer_bytes=1024))
    peticiones: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        peticiones.append(1)
        return httpx.Response(200, content=b"x" * 4096)

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        with pytest.raises(CuerpoDemasiadoGrande) as exc:
            await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert exc.value.motivo == "content_length" and len(peticiones) == 1
    assert cache.escrituras == [] and cache.filas == {}
    assert cache.renovaciones == 0 and cache.purgas == 0


async def test_el_cuerpo_normal_sigue_cacheando_y_sirviendo_json(fuente_encendida):
    peticiones: list[int] = []

    def handler(_request: httpx.Request) -> httpx.Response:
        peticiones.append(1)
        return httpx.Response(200, content=b'{"ok":true}',
                              headers={"content-type": "application/json"})

    reloj, fecha, cortesia = _entorno()
    cache = CacheHttpFalsa()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as cliente:
        primera = await _pedir(cliente, cache, cortesia, reloj, fecha)
        segunda = await _pedir(cliente, cache, cortesia, reloj, fecha)
    assert primera.json() == segunda.json() == {"ok": True}
    assert len(peticiones) == 1 and len(cache.escrituras) == 1
