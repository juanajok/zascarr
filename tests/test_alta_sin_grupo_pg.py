# ruff: noqa: E501, F401, F811
"""El alta SIN grupo de carpeta (I1 de #114) — recorrido completo sobre Postgres real.

Vista previa → token → confirmación → deshacer, llamando al servicio (`AltaDeSerie.previsualizar_sin_grupo`) y, para lo
que ya existe, a la aplicación por HTTP. Lo que se prueba: que el alta sin grupo ofrece lo MISMO que el alta con grupo (vista
previa sin escribir, tradición elegida, identificador exacto, parecidas que decide la persona, colisiones nuevas, candados,
comprobante, idempotencia, deshacer), que **no anota ninguna carpeta** (`desde_grupo` es `null`; la clave reservada, con NUL, no
llega a la base), que los contextos no se cruzan y que el mayor token sin grupo lo aceptan los puntos de entrada de siempre.
Ninguna fuente real; se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import select, text

from tests.test_alta_serie_pg import (  # noqa: F401  (BD efímera y entorno sin red)
    ALTA,
    CARPETA,
    CV_OK,
    SECRETO,
    cliente,
    entorno,
    numero_de_series,
    post,
    sembrar_serie,
    serie_en_bd,
    url_bd,
)
from zascarr.models import AltaEstado, AltaOperacion, ComicTradition, Series
from zascarr.services.alta_serie import (
    AltaDeSerie,
    AltaDeshechaError,
    DatosManuales,
    ParecidasNuevasError,
    TokenInvalidoError,
)
from zascarr.services.tokens_revision import (
    CLAVE_SIN_GRUPO,
    MAX_TOKEN_ALTA,
    MAX_TOKEN_ALTA_SIN_GRUPO,
    CandidataFirmada,
    crear_token_alta,
    crear_token_candidata,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

AM = ComicTradition.AMERICAN


def candidata_sin_grupo(clave=CLAVE_SIN_GRUPO, fuente="comic_vine", id_="796", titulo="Flash", anio=1987) -> str:
    return crear_token_candidata(clave, CandidataFirmada(fuente, id_, titulo, anio, "american", "Velocista.", CV_OK), SECRETO)


async def previsualizar(entorno, **kw):
    async with entorno.banco.fabrica() as s:
        return await AltaDeSerie(s, secret=SECRETO).previsualizar_sin_grupo(tradicion=kw.pop("tradicion", AM), **kw)


async def confirmar(entorno, token):
    async with entorno.banco.fabrica() as s:
        return await AltaDeSerie(s, secret=SECRETO).confirmar(token)


async def comprobantes(entorno) -> list:
    async with entorno.banco.fabrica() as s:
        return list((await s.execute(select(AltaOperacion))).scalars().all())


class TestAltaManualSinGrupo:
    @pytest.mark.asyncio
    async def test_la_vista_previa_no_escribe_nada_y_ofrece_crear(self, entorno):
        v = await previsualizar(entorno, manual=DatosManuales("Flash", 1987))
        assert v.accion == "crear" and v.origen == "manual" and v.token and v.efectos == {"series_nuevas": 1, "numeros": 0, "archivos": 0}
        assert await numero_de_series(entorno.banco) == 0 and await comprobantes(entorno) == []

    @pytest.mark.asyncio
    async def test_confirmar_crea_la_serie_con_la_tradicion_elegida_y_sin_carpeta(self, entorno):
        v = await previsualizar(entorno, manual=DatosManuales("Flash", 1987), tradicion=ComicTradition.MANGA)
        r = await confirmar(entorno, v.token)
        assert r.resultado == "creada" and not r.repetida and r.deshacer
        (s,) = await serie_en_bd(entorno.banco)
        assert (s.title, s.start_year, s.tradition, s.metadata_source, s.locked_fields) == ("Flash", 1987, ComicTradition.MANGA, "manual", [])
        alta = s.metadata_["alta"]
        assert alta["version"] == 1 and alta["origen"] == "manual" and alta["desde_grupo"] is None and alta["tradicion_elegida"] is True
        assert "\x00" not in str(s.metadata_)                        # la clave reservada nunca llega a la base
        (c,) = await comprobantes(entorno)
        assert c.series_id == s.id and c.estado == AltaEstado.CREADA and str(c.operacion_id) == alta["operacion_id"]

    @pytest.mark.asyncio
    async def test_repetir_la_confirmacion_devuelve_lo_mismo_sin_crear_otra(self, entorno):
        v = await previsualizar(entorno, manual=DatosManuales("Flash", 1987))
        a, b = await confirmar(entorno, v.token), await confirmar(entorno, v.token)
        assert (a.repetida, b.repetida) == (False, True) and a.serie.series_id == b.serie.series_id
        assert await numero_de_series(entorno.banco) == 1 and len(await comprobantes(entorno)) == 1

    @pytest.mark.asyncio
    async def test_se_puede_deshacer_y_el_token_no_la_recrea(self, entorno):
        v = await previsualizar(entorno, manual=DatosManuales("Flash", 1987))
        r = await confirmar(entorno, v.token)
        async with entorno.banco.fabrica() as s:
            d = await AltaDeSerie(s, secret=SECRETO).deshacer(
                __import__("uuid").UUID(r.deshacer["series_id"]), __import__("uuid").UUID(r.deshacer["operacion_id"]))
        assert d.deshecho and await numero_de_series(entorno.banco) == 0
        with pytest.raises(AltaDeshechaError):
            await confirmar(entorno, v.token)


class TestAltaDesdeFuenteSinGrupo:
    @pytest.mark.asyncio
    async def test_crea_con_el_identificador_protegido_y_la_procedencia(self, entorno):
        v = await previsualizar(entorno, candidata=candidata_sin_grupo())
        assert v.accion == "crear" and v.origen == "descubrir" and v.fuente == "comic_vine" and v.tradicion_sugerida == "american"
        r = await confirmar(entorno, v.token)
        (s,) = await serie_en_bd(entorno.banco)
        assert r.resultado == "creada" and s.comic_vine_id == 796 and s.locked_fields == ["comic_vine_id"]
        assert s.metadata_source == "comic_vine" and s.cover_url == CV_OK and s.description == "Velocista."
        assert s.metadata_["alta"]["desde_grupo"] is None and s.metadata_["alta"]["fuente"] == "comic_vine"

    @pytest.mark.asyncio
    async def test_el_mismo_identificador_es_la_unica_coincidencia_automatica(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Otro título", 2001, comic_vine_id=796)
        v = await previsualizar(entorno, candidata=candidata_sin_grupo())
        assert v.accion == "reutilizar" and v.existente.series_id == str(sid)
        r = await confirmar(entorno, v.token)
        assert r.resultado == "reutilizada" and r.motivo == "mismo_identificador" and await numero_de_series(entorno.banco) == 1
        assert (await serie_en_bd(entorno.banco))[0].title == "Otro título"           # la existente no se toca


class TestParecidasSinGrupo:
    @pytest.mark.asyncio
    async def test_hay_parecidas_y_la_persona_decide(self, entorno):
        sid = await sembrar_serie(entorno.banco, "Flash", 1987)
        v = await previsualizar(entorno, manual=DatosManuales("flash", 1988))
        assert v.accion == "elegir" and v.token is None and [p.series_id for p in v.parecidas] == [str(sid)]
        crea = await previsualizar(entorno, manual=DatosManuales("flash", 1988), decision="crear_igualmente")
        assert crea.accion == "crear" and await confirmar(entorno, crea.token)
        elige = await previsualizar(entorno, manual=DatosManuales("flash", 1988), decision="reutilizar", serie_id=sid)
        assert elige.accion == "reutilizar" and (await confirmar(entorno, elige.token)).motivo == "elegida_por_la_persona"

    @pytest.mark.asyncio
    async def test_una_parecida_que_aparece_entre_la_vista_previa_y_la_confirmacion_se_rechaza(self, entorno):
        v = await previsualizar(entorno, manual=DatosManuales("Flash", 1987))
        await sembrar_serie(entorno.banco, "FLASH", 1987)
        with pytest.raises(ParecidasNuevasError):
            await confirmar(entorno, v.token)
        assert await numero_de_series(entorno.banco) == 1


class TestLosContextosNoSeCruzan:
    @pytest.mark.asyncio
    async def test_una_candidata_sin_grupo_no_sirve_con_grupo(self, entorno):
        async with entorno.banco.fabrica() as s:
            with pytest.raises(TokenInvalidoError):
                await AltaDeSerie(s, secret=SECRETO).previsualizar(CARPETA, tradicion=AM, candidata=candidata_sin_grupo())

    @pytest.mark.asyncio
    async def test_una_candidata_de_un_grupo_no_sirve_sin_grupo(self, entorno):
        with pytest.raises(TokenInvalidoError):
            await previsualizar(entorno, candidata=candidata_sin_grupo(clave=CARPETA))

    @pytest.mark.asyncio
    async def test_el_alta_con_grupo_sigue_anotando_la_carpeta(self, entorno):
        v = await post("/api/revision/serie/previsualizar", {"clave": CARPETA, "manual": {"titulo": "Flash", "anio": 1987}, "tradicion": "american"})
        assert (await post(ALTA, {"token": v.json()["token"]})).status_code == 200
        (s,) = await serie_en_bd(entorno.banco)
        assert s.metadata_["alta"]["desde_grupo"] == CARPETA


class TestElMayorTokenSinGrupoLoAceptanLosPuntosDeEntrada:
    @pytest.mark.asyncio
    async def test_el_token_de_alta_de_la_longitud_exacta_se_acepta_por_http(self, entorno):
        """El mayor token de alta sin grupo (100 parecidas firmadas, todos los textos en su cota) mide `MAX_TOKEN_ALTA_SIN_GRUPO`
        y lo recibe el endpoint de siempre, cuyo límite es el del alta con grupo."""
        from tests.test_alta_sin_grupo import alta_maxima
        letra = "\U00020000"                                                    # una LETRA de 4 bytes (pesa lo mismo que el emoji)
        a = alta_maxima(CLAVE_SIN_GRUPO, fuente="tebeosfera", titulo=letra * 500, id_externo=letra * 255)   # `tebeosfera`: id de texto
        token = crear_token_alta(a, SECRETO)
        assert MAX_TOKEN_ALTA_SIN_GRUPO - 8 <= len(token) <= MAX_TOKEN_ALTA_SIN_GRUPO          # (la caducidad real mide un dígito menos)
        assert len(token) < MAX_TOKEN_ALTA
        r = await post(ALTA, {"token": token})
        assert r.status_code == 200 and r.json()["resultado"] in ("creada", "reutilizada"), r.text


class TestElCandadoDelTituloSeComparteConElAltaConGrupo:
    @pytest.mark.asyncio
    async def test_la_confirmacion_sin_grupo_espera_al_candado_del_titulo_y_luego_ve_lo_que_creo_otra_alta(self, entorno):
        """Otra alta (con grupo o sin él: el candado es el mismo) tiene el candado del título normalizado. La confirmación
        sin grupo espera —se comprueba en `pg_locks`, sin esperas fijas— y, al continuar, ve la serie recién creada como
        parecida nueva. Sin candado, la vería ausente y crearía el duplicado."""
        from sqlalchemy import text

        from zascarr.services.alta_serie import bloquear_titulo
        v = await previsualizar(entorno, manual=DatosManuales("Saga del Faro", 2010))
        async with entorno.banco.fabrica() as otra:
            await bloquear_titulo(otra, "Saga del Faro")
            espera = asyncio.create_task(confirmar(entorno, v.token))
            for _ in range(200):
                async with entorno.banco.fabrica() as c:
                    bloqueados = (await c.execute(text("SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted"))).scalar()
                if bloqueados:
                    break
                await asyncio.sleep(0.05)
            assert bloqueados and not espera.done(), "la confirmación debía esperar al candado del título"
            otra.add(Series(title="Saga del Faro", tradition=AM, start_year=2010))
            await otra.commit()
        with pytest.raises(ParecidasNuevasError):
            await asyncio.wait_for(espera, timeout=30)
        assert await numero_de_series(entorno.banco) == 1
