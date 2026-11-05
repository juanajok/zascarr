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


# ── Limitador de dos niveles (#134, MIT-M8-US02): política, dos niveles, cancelación, bloqueos ──

from zascarr.utils.cortesia import (  # noqa: E402
    BLOQUEO_MAX_S,
    CortesiaEnEspera,
    CortesiaProceso,
    FuenteApagada,
    cortesia_de_proceso,
    fuente_habilitada,
    politica_de,
)


class AjustesFalsos:
    comicvine_rate_limit = 1.0
    anilist_rate_limit = 1.5
    tebeosfera_rate_limit = 2.5
    gcd_rate_limit = 2.0
    forum_rate_limit = 2.0
    comicvine_enabled = True
    anilist_enabled = True
    tebeosfera_enabled = True
    gcd_enabled = True
    forum_enabled = False
    forum_url = ""


def _lim(reloj: Reloj) -> CortesiaProceso:
    return CortesiaProceso(reloj=reloj, dormir=reloj.dormir)


class TestPoliticaPorFuente:
    def test_tabla_de_intervalos_y_maximos(self):
        assert politica_de("comicvine", AjustesFalsos()).intervalo_min_s == 1.0
        assert politica_de("anilist", AjustesFalsos()).intervalo_min_s == 1.5
        assert politica_de("gcd", AjustesFalsos()).intervalo_min_s == 2.0
        for fuente, intentos in (("comicvine", 3), ("anilist", 3), ("tebeosfera", 1),
                                 ("gcd", 2), ("foro", 2), ("portada", 1)):
            politica = politica_de(fuente, AjustesFalsos())
            assert politica.max_intentos == intentos and politica.max_redirecciones == 3

    def test_tebeosfera_no_baja_de_dos_y_medio(self):
        class Ajustes(AjustesFalsos):
            tebeosfera_rate_limit = 1.0
        assert politica_de("tebeosfera", Ajustes()).intervalo_min_s == 2.5
        class AjustesAltos(AjustesFalsos):
            tebeosfera_rate_limit = 4.0
        assert politica_de("tebeosfera", AjustesAltos()).intervalo_min_s == 4.0

    def test_intervalo_de_portada_por_host(self):
        from zascarr.utils.cortesia import intervalo_de_portada
        assert intervalo_de_portada("comicvine.gamespot.com") == 1.0
        assert intervalo_de_portada("comicvine1.cbsistatic.com") == 1.0
        assert intervalo_de_portada("s4.anilist.co") == 1.5
        assert intervalo_de_portada("www.tebeosfera.com") == 2.5
        assert intervalo_de_portada("comics.org") == 2.0
        assert intervalo_de_portada("desconocido.example") == 2.5

    def test_backoff_sin_jitter_y_con_tope(self):
        politica = politica_de("comicvine", AjustesFalsos())
        assert [politica.backoff_s(n) for n in (1, 2, 3, 4, 5)] == [2.0, 4.0, 8.0, 16.0, 30.0]


class TestDosNiveles:
    async def test_la_primera_no_espera_y_la_segunda_cumple_el_intervalo_de_fuente(self):
        r = Reloj()
        lim = _lim(r)
        assert (await lim.esperar("comicvine", "a.example")).espera_s == 0.0
        segunda = await lim.esperar("comicvine", "b.example")
        assert segunda.espera_s == pytest.approx(1.0) and r.dormidos == [pytest.approx(1.0)]

    async def test_el_host_efectivo_cumple_el_maximo_de_sus_fuentes(self):
        r = Reloj()
        lim = _lim(r)
        await lim.esperar("comicvine", "cdn.example")          # 1,0 s de CV
        assert (await lim.esperar("anilist", "cdn.example")).espera_s == pytest.approx(1.5)

    async def test_fuente_y_host_se_aplican_a_la_vez(self):
        r = Reloj()
        lim = _lim(r)
        await lim.esperar("comicvine", "a.example")
        # Otra fuente en otro host no espera por la fuente, pero sí por su propio intervalo.
        assert (await lim.esperar("anilist", "b.example")).espera_s == 0.0
        # La misma fuente en otro host espera por la fuente; el host nuevo no añade.
        assert (await lim.esperar("comicvine", "c.example")).espera_s == pytest.approx(1.0)

    async def test_concurrentes_fifo_y_escalonadas(self):
        r = Reloj()
        lim = _lim(r)
        instantes: list[float] = []

        async def una():
            espera = await lim.esperar("anilist", "api.anilist.co")
            instantes.append(r.t)
            return espera
        esperas = await asyncio.gather(*(una() for _ in range(5)))
        assert len(instantes) == 5
        assert all(b - a >= 1.5 - 1e-9 for a, b in zip(instantes, instantes[1:], strict=False))
        assert esperas[0].espera_s == 0.0 and esperas[-1].espera_s > 0

    async def test_dos_registros_independientes_no_se_coordinan(self):
        r = Reloj()
        a, b = _lim(r), _lim(r)
        await a.esperar("comicvine", "x.example")
        assert (await b.esperar("comicvine", "x.example")).espera_s == 0.0
        assert a.snapshot(AjustesFalsos())["coordinacion"] == "proceso"
        assert b.snapshot(AjustesFalsos())["coordinacion"] == "proceso"


class TestCancelacionYPresupuesto:
    async def test_cancelar_antes_de_autorizar_no_consume_ni_deja_candado(self):
        r = Reloj()
        lim = CortesiaProceso(reloj=r, dormir=lambda s: asyncio.sleep(3600))
        await lim.esperar("comicvine", "a.example")             # la primera no espera
        pendiente = asyncio.create_task(lim.esperar("comicvine", "a.example"))
        await asyncio.sleep(0)
        pendiente.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pendiente
        # El candado de la fuente quedó libre y la marca sigue siendo la de la primera.
        r.t += 1.0
        assert (await lim.esperar("comicvine", "a.example")).espera_s == 0.0
        assert lim.snapshot(AjustesFalsos())["hosts"][0]["esperando_ahora"] == 0

    async def test_cancelar_tras_autorizar_la_fuente_consume_ese_hueco(self):
        r = Reloj()
        empieza = asyncio.Event()

        async def dormir_largo(_segundos):
            empieza.set()
            await asyncio.Event().wait()          # se queda esperando hasta que lo cancelen

        lim = CortesiaProceso(reloj=r, dormir=dormir_largo)
        # Tebeosfera deja el host «h.example» con su intervalo (2,5 s) marcado.
        await lim.esperar("tebeosfera", "h.example")
        # Comic Vine entra por el mismo host: la FUENTE se autoriza y luego espera al host.
        pendiente = asyncio.create_task(lim.esperar("comicvine", "h.example"))
        await empieza.wait()
        pendiente.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pendiente
        lim._dormir = r.dormir
        # La fuente Comic Vine YA consumió su hueco: otra petición suya espera 1,0 s aunque el
        # host sea distinto y esté libre.
        assert (await lim.esperar("comicvine", "otro.example")).espera_s == pytest.approx(1.0)

    async def test_el_presupuesto_agotado_no_duerme_ni_envia(self):
        r = Reloj()
        lim = _lim(r)
        lim.bloquear("comicvine", "a.example", 60, motivo="429")
        with pytest.raises(CortesiaEnEspera) as exc:
            await lim.esperar("comicvine", "a.example", espera_max_s=10)
        assert exc.value.fuente == "comicvine" and exc.value.motivo == "bloqueo_fuente"
        assert exc.value.espera_estimada_s == pytest.approx(60)
        assert r.dormidos == [] and "http" not in str(exc.value)

    async def test_un_bloqueo_mayor_que_una_hora_se_recorta(self):
        r = Reloj()
        lim = _lim(r)
        lim.bloquear("comicvine", "a.example", 7200, motivo="429")
        bloqueo = lim.snapshot(AjustesFalsos())["fuentes"][0]["bloqueada_hasta_s"]
        assert bloqueo == pytest.approx(BLOQUEO_MAX_S)

    async def test_el_limitador_no_se_puede_usar_desde_un_hilo(self):
        lim = cortesia_de_proceso()

        def desde_hilo():
            return lim.reservar("comicvine", "a.example")
        with pytest.raises(RuntimeError, match="bucle de asyncio"):
            await asyncio.to_thread(desde_hilo)


class TestSnapshotPortada:
    async def test_el_host_de_una_portada_publica_su_intervalo_real_y_su_fuente(self):
        """Criterio 8: un host usado solo por portadas no sale con 0,0 s ni con fuentes: []."""
        r = Reloj()
        lim = _lim(r)
        origen = "https://s4.anilist.co:443"
        await lim.esperar("portada", origen, motivo="portada", intervalo_s=1.5, solo_host=True)
        host = next(h for h in lim.snapshot(AjustesFalsos())["hosts"] if h["host"] == origen)
        assert host["intervalo_min_s"] == pytest.approx(1.5)
        assert host["fuentes"] == ["anilist"]

    async def test_un_host_sin_fuente_mapeada_publica_el_intervalo_efectivo_de_su_portada(self):
        """Muerde el guardado: sin `_intervalos_de_host`, el snapshot daría 0,0 (no 2,5)."""
        r = Reloj()
        lim = _lim(r)
        origen = "https://cdn.desconocido.example:443"
        await lim.esperar("portada", origen, motivo="portada", intervalo_s=2.5, solo_host=True)
        host = next(h for h in lim.snapshot(AjustesFalsos())["hosts"] if h["host"] == origen)
        assert host["intervalo_min_s"] == pytest.approx(2.5)
        assert host["fuentes"] == []                    # host fuera de la allowlist

    async def test_un_intervalo_de_portada_distinto_del_de_su_fuente_manda_el_efectivo(self):
        """Muerde el `max`: 5,0 s de la portada no deben reducirse a los 2,5 de Tebeosfera."""
        r = Reloj()
        lim = _lim(r)
        origen = "https://www.tebeosfera.com:443"
        lim.registrar_politica(politica_de("tebeosfera", AjustesFalsos()))
        await lim.esperar("portada", origen, motivo="portada", intervalo_s=5.0, solo_host=True)
        host = next(h for h in lim.snapshot(AjustesFalsos())["hosts"] if h["host"] == origen)
        assert host["intervalo_min_s"] == pytest.approx(5.0)
        assert host["fuentes"] == ["tebeosfera"]

    async def test_el_intervalo_del_host_es_el_maximo_entre_portada_y_su_fuente(self):
        r = Reloj()
        lim = _lim(r)
        origen = "https://comicvine.gamespot.com:443"
        lim.registrar_politica(politica_de("comicvine", AjustesFalsos()))
        await lim.esperar("comicvine", origen)
        await lim.esperar("portada", origen, motivo="portada", intervalo_s=1.0, solo_host=True)
        host = next(h for h in lim.snapshot(AjustesFalsos())["hosts"] if h["host"] == origen)
        assert host["intervalo_min_s"] == pytest.approx(1.0)   # 1,0 real, no 2,5 de la sintética
        assert host["fuentes"] == ["comicvine"]


class TestSnapshot:
    async def test_forma_y_datos_sin_secretos(self):
        r = Reloj()
        lim = _lim(r)
        await lim.esperar("comicvine", "comicvine.gamespot.com")
        lim.bloquear("anilist", "graphql.anilist.co", 30, motivo="429")
        lim.registrar_resultado("comicvine", "ok", intento=1, espera_s=0.0)
        lim.registrar_resultado("comicvine", "429", intento=2, espera_s=2.0)
        datos = lim.snapshot(AjustesFalsos())
        assert set(datos) == {"coordinacion", "generado", "fuentes", "hosts"}
        assert datos["coordinacion"] == "proceso"
        assert [f["fuente"] for f in datos["fuentes"]] == [
            "comicvine", "anilist", "tebeosfera", "gcd", "foro", "portada"]
        cv = next(f for f in datos["fuentes"] if f["fuente"] == "comicvine")
        assert cv["intervalo_min_s"] == 1.0 and cv["max_intentos"] == 3
        assert cv["ultimos_intentos"][0]["resultado"] == "429"
        assert len(cv["ultimos_intentos"]) <= 3
        anilist = next(f for f in datos["fuentes"] if f["fuente"] == "anilist")
        assert anilist["bloqueada_hasta_s"] == pytest.approx(30) and anilist["bloqueo_motivo"] == "429"
        foro = next(f for f in datos["fuentes"] if f["fuente"] == "foro")
        assert foro["habilitada"] is False
        assert datos["hosts"][0]["host"] == "comicvine.gamespot.com"
        assert datos["hosts"][0]["fuentes"] == ["comicvine"]
        serializado = repr(datos)
        assert "http" not in serializado and "query" not in serializado

    async def test_el_estado_esta_acotado(self):
        r = Reloj()
        lim = _lim(r)
        for i in range(10):
            lim.registrar_resultado("comicvine", "ok", intento=i + 1)
        datos = lim.snapshot(AjustesFalsos())
        assert all(len(f["ultimos_intentos"]) <= 3 for f in datos["fuentes"])
        assert len(datos["fuentes"]) == 6


class TestFuenteHabilitada:
    def test_enciende_y_apaga(self):
        class Ajustes(AjustesFalsos):
            comicvine_enabled = False
        assert fuente_habilitada("comicvine", Ajustes()) is False
        assert fuente_habilitada("anilist", Ajustes()) is True
        assert fuente_habilitada("foro", Ajustes()) is False


class TestOrigenNormalizadoComoHost:
    """AC-02 (§3.2): la clave del nivel host es `(esquema, host, puerto)`, no el hostname."""

    async def test_mismo_host_distinto_esquema_o_puerto_son_colas_distintas(self):
        from zascarr.utils.cortesia import PoliticaFuente
        r = Reloj()
        lim = _lim(r)
        for fuente, intervalo in (("tebeosfera", 2.5), ("comicvine", 1.0),
                                  ("gcd", 2.0), ("anilist", 1.5)):
            lim.registrar_politica(PoliticaFuente(fuente, fuente, intervalo, 3, 3))
        await lim.esperar("tebeosfera", "https://cdn.example")             # marca el origen https:443
        assert (await lim.esperar("comicvine", "http://cdn.example")).espera_s == 0.0
        assert (await lim.esperar("gcd", "https://cdn.example:8443")).espera_s == 0.0
        # El mismo origen SÍ comparte cola: espera el máximo de los intervalos del host (2,5 s).
        assert (await lim.esperar("anilist", "https://cdn.example")).espera_s == pytest.approx(2.5)

    async def test_la_url_completa_tambien_se_normaliza(self):
        r = Reloj()
        lim = _lim(r)
        await lim.esperar("comicvine", "https://cdn.example/ruta?x=1")
        assert (await lim.esperar("comicvine", "https://cdn.example:443/otra")) is not None
        assert (await lim.esperar("anilist", "https://cdn.example/c.png")).espera_s > 0


class TestPresupuestoPorDefecto:
    async def test_sin_presupuesto_explicito_no_se_duerme_hasta_una_hora(self):
        """Un caller nuevo no puede dormir indefinidamente: el defecto es 30 s (fondo, §3.7)."""
        r = Reloj()
        lim = _lim(r)
        lim.bloquear("comicvine", "https://a.example", 1000, motivo="429")
        with pytest.raises(CortesiaEnEspera) as exc:
            await lim.esperar("comicvine", "https://a.example")
        assert exc.value.espera_estimada_s == pytest.approx(1000)
        assert r.dormidos == []
        with pytest.raises(CortesiaEnEspera):
            async with lim.reservar("comicvine", "https://a.example"):
                pass


class TestPortadaNoContagiaSuIntervaloAlHost:
    async def test_la_fuente_sintetica_portada_no_infla_el_intervalo_del_host(self):
        """La portada usa su intervalo por host; no debe hacer que Comic Vine espere 2,5 s."""
        r = Reloj()
        lim = _lim(r)
        lim.registrar_politica(politica_de("comicvine", AjustesFalsos()))
        origen = "https://comicvine.gamespot.com:443"
        await lim.esperar("portada", origen, intervalo_s=2.5, solo_host=True)
        # Comic Vine llega después al mismo host: espera SU 1,0 s, no el 2,5 de la portada.
        assert (await lim.esperar("comicvine", origen)).espera_s == pytest.approx(1.0)
