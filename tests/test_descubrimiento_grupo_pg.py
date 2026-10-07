# ruff: noqa: E501
"""`POST /api/revision/descubrir` (rebanada 2a) — pruebas de aceptación sobre Postgres real.

Contrato: `docs/design/rebanada-2-elegir-serie-y-vincular.md`, bloque A. Las fuentes se SIMULAN (se parchea
`DiscoveryService.search_detallada`); lo que se prueba es lo que 2a añade: que la red solo se use a petición,
que nada se elija ni se recomiende, lo que se calcula en LOCAL (`ya_en_biblioteca`, `parecidas_locales`,
`coincidencia_con_la_carpeta`, esta última con **el mismo código** que la superficie de la rebanada 1), los
tokens firmados y que no se escriba nada. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
import re
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import BIB, Banco, archivo, candidatas
from zascarr.api import revision as api_revision
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services import revision_carpetas
from zascarr.services.discovery import (
    FUENTE_ERROR,
    FUENTE_OK,
    FUENTE_SIN_CLAVE,
    Busqueda,
    DiscoveryResult,
    DiscoveryService,
)
from zascarr.services.tokens_revision import (
    verificar_token,
    verificar_token_candidata,
)
from zascarr.utils.url_portada import es_url_de_portada_permitida

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

SECRETO = "clave-de-prueba-para-firmar"
RUTA = "/api/revision/descubrir"
CV_OK = "https://comicvine.gamespot.com/a/uploads/scale_large/1/11/cover.jpg"


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


def res(fuente: MetadataSource, id_: str, titulo: str, anio: int | None, **kw) -> DiscoveryResult:
    return DiscoveryResult(
        source=fuente, external_id=id_, title=titulo, start_year=anio, description=kw.get("descripcion"),
        cover_url=kw.get("cover"), site_url=kw.get("sitio", f"https://ejemplo.example/{id_}"),
        tradition_guess=kw.get("tradicion", ComicTradition.AMERICAN),
    )


class FuentesFalsas:
    """Sustituye a `DiscoveryService.search_detallada`: registra las llamadas y devuelve lo que se le diga."""

    def __init__(self):
        self.llamadas: list[str] = []
        self.resultados: list[DiscoveryResult] = []
        self.avisos: list[str] = []
        self.fuentes = {"comic_vine": FUENTE_OK, "anilist": FUENTE_OK, "tebeosfera": FUENTE_OK, "gcd": FUENTE_OK}

    async def buscar(self, consulta, limit=10):
        self.llamadas.append(consulta)
        return Busqueda(list(self.resultados), list(self.avisos), dict(self.fuentes))


@pytest.fixture
async def entorno(url_bd, monkeypatch):
    b = Banco(url_bd)
    await b.limpiar()
    monkeypatch.setattr(revision_carpetas, "get_settings", lambda: SimpleNamespace(library_path=BIB))
    monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
    monkeypatch.setattr(api_revision, "MIN_INTERVALO_S", 0.0)
    api_revision.reiniciar_ritmo_para_pruebas()
    fuentes = FuentesFalsas()
    monkeypatch.setattr(DiscoveryService, "search_detallada", fuentes.buscar)

    async def _get_db():
        async with b.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    yield SimpleNamespace(banco=b, fuentes=fuentes)
    app.dependency_overrides.pop(get_db, None)
    await b.cerrar()


def cliente(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                             headers={"Origin": "http://localhost"}, **kw)


async def descubrir(clave: str, consulta: str | None = None, **kw) -> httpx.Response:
    cuerpo = {"clave": clave, **({"consulta": consulta} if consulta is not None else {})}
    async with cliente() as c:
        return await c.post(RUTA, json=cuerpo, **kw)


async def sembrar_flash(banco, n: int = 3, carpeta: str = "Comics/Flash (1987)"):
    await banco.sembrar(*(archivo(f"{carpeta}/Flash {i:02d} (1987).cbz") for i in range(1, n + 1)))
    return carpeta


# ── La red solo a petición ───────────────────────────────────────────────────────────────────

class TestSoloAPeticion:

    async def test_abrir_los_grupos_no_consulta_las_fuentes_ni_sale_a_la_red(self, entorno, monkeypatch):
        await sembrar_flash(entorno.banco)
        reales = []
        original = httpx.AsyncClient.send

        async def vigilado(self, request, **kw):
            if not isinstance(self._transport, httpx.ASGITransport):
                reales.append(request.url.host)
            return await original(self, request, **kw)
        monkeypatch.setattr(httpx.AsyncClient, "send", vigilado)
        async with cliente() as c:
            r = await c.get("/api/revision/carpetas")
        assert r.status_code == 200 and r.json()["grupos"]
        assert entorno.fuentes.llamadas == [] and reales == []

    async def test_se_busca_solo_al_llamar_y_una_vez_con_la_consulta(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        r = await descubrir(carpeta, "Flash")
        assert r.status_code == 200 and entorno.fuentes.llamadas == ["Flash"]


# ── La consulta ──────────────────────────────────────────────────────────────────────────────

class TestConsulta:

    async def test_se_propone_la_carpeta_limpia_y_la_persona_puede_cambiarla(self, entorno):
        await entorno.banco.sembrar(archivo("Comics/Batman - Saga de Scott Snyder (2019)/Batman 01.cbz"))
        clave = "Comics/Batman - Saga de Scott Snyder (2019)"
        sin = (await descubrir(clave)).json()
        assert (sin["consulta"], sin["consulta_propuesta"]) == ("Batman", "Batman")
        con = (await descubrir(clave, "  Batman Año Uno  ")).json()
        assert (con["consulta"], con["consulta_propuesta"]) == ("Batman Año Uno", "Batman")
        assert entorno.fuentes.llamadas == ["Batman", "Batman Año Uno"]

    async def test_una_consulta_en_blanco_usa_la_propuesta(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        assert (await descubrir(carpeta, "   ")).json()["consulta"] == "Flash"

    async def test_sin_carpeta_de_serie_se_propone_el_titulo_que_dominan_los_nombres(self, entorno):
        await entorno.banco.sembrar(*(archivo(f"Comics/Mortadelo {i:02d}.cbz") for i in range(1, 4)))
        r = (await descubrir("Comics")).json()
        assert r["consulta_propuesta"] == "Mortadelo" and r["grupo"]["carpeta_contextual"] is None

    @pytest.mark.parametrize("nombre", ["001.cbz", "01.cbz", "# 12.cbz"])
    async def test_sin_nada_que_proponer_ni_que_buscar_es_422(self, entorno, nombre):
        """Sin carpeta de serie y con nombres sin título legible (o solo un número) no hay consulta posible."""
        await entorno.banco.sembrar(archivo(f"Comics/_Omnibus/{nombre}"))
        r = await descubrir("Comics/_Omnibus")
        assert r.status_code == 422 and entorno.fuentes.llamadas == []

    async def test_con_consulta_escrita_a_mano_se_puede_buscar_aunque_no_haya_propuesta(self, entorno):
        await entorno.banco.sembrar(archivo("Comics/_Omnibus/001.cbz"))
        assert (await descubrir("Comics/_Omnibus", "Flash")).status_code == 200


# ── Nada se elige ni se recomienda ───────────────────────────────────────────────────────────

class TestNadaPreseleccionado:

    async def test_un_unico_resultado_con_titulo_exacto_sale_sin_nada_elegido(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        cuerpo = (await descubrir(carpeta)).json()
        assert len(cuerpo["candidatas"]) == 1
        prohibidas = {"recomendada", "elegida", "seleccionada", "preseleccionada", "mejor", "score", "puntuacion",
                      "confianza", "por_defecto"}
        assert prohibidas.isdisjoint(cuerpo) and prohibidas.isdisjoint(cuerpo["candidatas"][0])
        assert re.search(r"\b(recomendad\w*|mejor|elegid\w*)\b", str(cuerpo["avisos"]), re.I) is None

    async def test_el_orden_es_el_fijo_de_las_fuentes_y_luego_el_titulo(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [
            res(MetadataSource.GCD, "9", "Zeta", 1990), res(MetadataSource.TEBEOSFERA, "t1", "Flash", 1987),
            res(MetadataSource.COMIC_VINE, "3", "flash vol 2", 2011), res(MetadataSource.ANILIST, "5", "Flash", 2000),
            res(MetadataSource.COMIC_VINE, "2", "Flash", 1987), res(MetadataSource.GCD, "8", "Alfa", 1991),
        ]
        a = [(c["fuente"], c["titulo"]) for c in (await descubrir(carpeta)).json()["candidatas"]]
        assert a == [("comic_vine", "Flash"), ("comic_vine", "flash vol 2"), ("anilist", "Flash"),
                     ("tebeosfera", "Flash"), ("gcd", "Alfa"), ("gcd", "Zeta")]
        entorno.fuentes.resultados.reverse()
        api_revision.reiniciar_ritmo_para_pruebas()
        assert a == [(c["fuente"], c["titulo"]) for c in (await descubrir(carpeta)).json()["candidatas"]]


# ── Lo que se calcula en local ───────────────────────────────────────────────────────────────

async def _serie(banco, titulo, anio, tradicion=ComicTradition.AMERICAN, **ids):
    sid = uuid4()
    async with banco.fabrica() as s:
        s.add(Series(id=sid, title=titulo, tradition=tradicion, start_year=anio, **ids))
        await s.commit()
    return sid


class TestLocales:

    async def test_ya_en_biblioteca_solo_por_identificador_externo_exacto(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        sid = await _serie(entorno.banco, "Flash (la mía)", 1987, comic_vine_id=2)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987),
                                      res(MetadataSource.COMIC_VINE, "3", "Flash", 1987)]
        c = {x["token"]: x for x in (await descubrir(carpeta)).json()["candidatas"]}.values()
        por_id = {x["titulo"] + x["fuente"]: x for x in c}
        cand2, = [x for x in c if x["ya_en_biblioteca"]]
        assert cand2["ya_en_biblioteca"] == {"series_id": str(sid), "titulo": "Flash (la mía)", "anio": 1987,
                                             "tradicion": "american"}
        sin = [x for x in c if not x["ya_en_biblioteca"]]
        assert len(sin) == 1 and por_id

    async def test_el_identificador_de_texto_de_tebeosfera_tambien(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        sid = await _serie(entorno.banco, "Thorgal", 1981, ComicTradition.TEBEO, tebeosfera_slug="thorgal_1981_distrinovel")
        entorno.fuentes.resultados = [res(MetadataSource.TEBEOSFERA, "thorgal_1981_distrinovel", "Thorgal", 1981),
                                      res(MetadataSource.TEBEOSFERA, "thorgal_1981_otro", "Thorgal", 1981)]
        c = (await descubrir(carpeta)).json()["candidatas"]
        assert [x["ya_en_biblioteca"] is not None for x in c] == [True, False] or \
               sorted(x["ya_en_biblioteca"] is not None for x in c) == [False, True]
        assert sid and sum(1 for x in c if x["ya_en_biblioteca"]) == 1

    async def test_el_mismo_titulo_sin_id_es_solo_una_parecida_con_aviso(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        sid = await _serie(entorno.banco, "Flash", 1988)                       # sin id externo, año ±1
        lejana = await _serie(entorno.banco, "Flash", 2011)                    # año incompatible
        otro = await _serie(entorno.banco, "Flash Gordon", 1987)               # otro título normalizado
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987)]
        (cand,) = (await descubrir(carpeta)).json()["candidatas"]
        assert cand["ya_en_biblioteca"] is None                                 # NO es una coincidencia
        assert [p["series_id"] for p in cand["parecidas_locales"]] == [str(sid)]
        assert cand["parecidas_locales"][0]["motivo"] and lejana and otro

    async def test_los_articulos_no_cuentan_igual_que_en_el_resto_de_zascarr(self, entorno):
        """`The Flash` y `Flash` tienen el mismo título normalizado (como `La Patrulla X` y `Patrulla X`)."""
        carpeta = await sembrar_flash(entorno.banco)
        sid = await _serie(entorno.banco, "The Flash", 1987)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987)]
        (cand,) = (await descubrir(carpeta)).json()["candidatas"]
        assert [p["series_id"] for p in cand["parecidas_locales"]] == [str(sid)]

    async def test_un_anio_desconocido_no_descarta_la_parecida(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        sid = await _serie(entorno.banco, "Flash", None)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987),
                                      res(MetadataSource.COMIC_VINE, "3", "Flash", None)]
        c = (await descubrir(carpeta)).json()["candidatas"]
        assert all([p["series_id"] for p in x["parecidas_locales"]] == [str(sid)] for x in c)

    async def test_la_serie_que_ya_esta_por_id_no_se_repite_como_parecida(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        await _serie(entorno.banco, "Flash", 1987, comic_vine_id=2)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987)]
        (cand,) = (await descubrir(carpeta)).json()["candidatas"]
        assert cand["ya_en_biblioteca"] and cand["parecidas_locales"] == []

    async def test_se_muestra_la_tradicion_de_la_parecida_para_que_se_vea_si_es_otra(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        await _serie(entorno.banco, "Flash", 1987, ComicTradition.MANGA)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987)]
        (cand,) = (await descubrir(carpeta)).json()["candidatas"]
        assert cand["parecidas_locales"][0]["tradicion"] == "manga"


# ── La carpeta corrobora o contradice (el MISMO código que la rebanada 1) ───────────────────────

def _firma(senales):
    return [(s["codigo"], s["severidad"], s["texto"], sorted(s["archivos"])) for s in senales]


class TestCoincidenciaConLaCarpeta:

    async def test_las_senales_son_exactamente_las_de_la_superficie_de_revision(self, entorno):
        """Paridad con la rebanada 1: el mismo grupo, la misma serie (título y año) ⇒ las mismas señales."""
        sid = await entorno.banco.serie("BATMAN", 2025)
        clave = "Comics/Batman - Saga de Scott Snyder (2019)"
        await entorno.banco.sembrar(*(
            archivo(f"{clave}/Batman - Saga Scott Snyder {n:02d} - El Tribunal de los Buhos [SC][CRG].cbr",
                    estado="direct", cands=candidatas(sid, "BATMAN", 2025)) for n in range(1, 10)))
        async with cliente() as c:
            grupo = next(g for g in (await c.get("/api/revision/carpetas")).json()["grupos"] if g["clave"] == clave)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "9", "BATMAN", 2025)]
        (cand,) = (await descubrir(clave)).json()["candidatas"]
        assert _firma(cand["coincidencia_con_la_carpeta"]["senales"]) == _firma(grupo["senales"])
        assert cand["coincidencia_con_la_carpeta"]["en_conflicto"] is grupo["en_conflicto"] is True

    async def test_la_carpeta_contradice_un_resultado_y_corrobora_otro(self, entorno):
        clave = "Comics/Absolute Batman (2024)"
        await entorno.banco.sembrar(*(archivo(f"{clave}/Absolute Batman {n:02d}.cbz") for n in range(1, 5)))
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Absolute Batman", 2024),
                                      res(MetadataSource.COMIC_VINE, "2", "Absolute Batman", 2016)]
        buena, mala = (await descubrir(clave)).json()["candidatas"]
        assert buena["anio"] == 2024 and buena["coincidencia_con_la_carpeta"]["en_conflicto"] is False
        assert [s["codigo"] for s in buena["coincidencia_con_la_carpeta"]["senales"]] == ["coincide_y_corrobora"]
        assert mala["coincidencia_con_la_carpeta"]["en_conflicto"] is True
        assert "anio_discrepa" in [s["codigo"] for s in mala["coincidencia_con_la_carpeta"]["senales"]]

    async def test_un_titulo_exacto_sin_nada_que_lo_corrobore_es_un_conflicto(self, entorno):
        clave = "Comics/Flash"
        await entorno.banco.sembrar(*(archivo(f"{clave}/Flash {n:02d}.cbz") for n in range(1, 4)))
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987)]
        (cand,) = (await descubrir(clave)).json()["candidatas"]
        assert cand["coincidencia_con_la_carpeta"]["en_conflicto"] is True
        assert "titulo_exacto_sin_corroboracion" in [s["codigo"] for s in cand["coincidencia_con_la_carpeta"]["senales"]]

    async def test_se_evaluan_todos_los_archivos_del_grupo_con_serie_o_sin_ella(self, entorno):
        """Los archivos «sin serie» también cuentan: la candidata se evalúa contra TODOS, no solo los sugeridos."""
        clave = "Comics/Flash (1987)"
        await entorno.banco.sembrar(
            archivo(f"{clave}/Flash 01 (1987).cbz"), archivo(f"{clave}/Flash 02 (1987).cbz"),
            archivo(f"{clave}/Flash 03 (2011).cbz"))
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "2", "Flash", 1987)]
        (cand,) = (await descubrir(clave)).json()["candidatas"]
        senal = next(s for s in cand["coincidencia_con_la_carpeta"]["senales"] if s["codigo"] == "anio_discrepa")
        assert len(senal["archivos"]) == 1 and cand["coincidencia_con_la_carpeta"]["en_conflicto"] is True


# ── Portada y datos externos ─────────────────────────────────────────────────────────────────

class TestDatosExternos:

    async def test_la_portada_solo_sale_por_el_proxy_y_solo_si_cumple_la_politica(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [
            res(MetadataSource.COMIC_VINE, "1", "Flash", 1987, cover=CV_OK),
            res(MetadataSource.COMIC_VINE, "2", "Flash B", 1987, cover="http://127.0.0.1:9091/x.jpg"),
            res(MetadataSource.COMIC_VINE, "3", "Flash C", 1987, cover="https://evil.example/x.jpg"),
        ]
        buena, interna, ajena = (await descubrir(carpeta)).json()["candidatas"]
        assert buena["portada"].startswith("/ui/descubrir/portada?url=https%3A%2F%2Fcomicvine.gamespot.com")
        assert buena["portada"].endswith("&source=comic_vine")
        assert interna["portada"] is None and ajena["portada"] is None
        # …y la URL hostil NO entra en el token firmado.
        for cand in (interna, ajena):
            firmada = verificar_token_candidata(cand["token"], carpeta, SECRETO)
            assert firmada is not None and firmada.cover_url is None
        assert verificar_token_candidata(buena["token"], carpeta, SECRETO).cover_url == CV_OK
        assert es_url_de_portada_permitida(CV_OK)

    async def test_la_descripcion_se_recorta_en_la_vista_y_en_el_token(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987, descripcion="x" * 5000)]
        (cand,) = (await descubrir(carpeta)).json()["candidatas"]
        assert len(cand["descripcion"]) == 300
        assert len(verificar_token_candidata(cand["token"], carpeta, SECRETO).descripcion) == 1000

    async def test_un_titulo_con_html_viaja_como_dato_sin_interpretarse(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        malo = "<img src=x onerror=alert(1)>"
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", malo, 1987)]
        r = await descubrir(carpeta)
        assert r.headers["content-type"].startswith("application/json")
        assert r.json()["candidatas"][0]["titulo"] == malo


# ── Los tokens ───────────────────────────────────────────────────────────────────────────────

class TestTokens:

    async def _token(self, entorno, carpeta="Comics/Flash (1987)"):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "42", "Flash", 1987, descripcion="d",
                                          tradicion=ComicTradition.AMERICAN)]
        return carpeta, (await descubrir(carpeta)).json()["candidatas"][0]["token"]

    async def test_el_token_trae_lo_que_el_servidor_vio_y_nada_mas(self, entorno):
        carpeta, token = await self._token(entorno)
        firmada = verificar_token_candidata(token, carpeta, SECRETO)
        assert (firmada.fuente, firmada.id_externo, firmada.titulo, firmada.anio, firmada.tradicion) == (
            "comic_vine", "42", "Flash", 1987, "american")

    async def test_otro_grupo_otra_clave_o_otro_proposito_no_lo_aceptan(self, entorno):
        carpeta, token = await self._token(entorno)
        assert verificar_token_candidata(token, "Comics/Otra", SECRETO) is None            # otro contexto
        assert verificar_token_candidata(token, carpeta, "otra-clave") is None             # otra clave
        assert verificar_token(token, "alta", carpeta, SECRETO) is None                    # otro propósito
        assert verificar_token(token, "vincular", carpeta, SECRETO) is None

    async def test_un_token_manipulado_o_roto_no_se_acepta(self, entorno):
        carpeta, token = await self._token(entorno)
        cuerpo, firma = token.rsplit(".", 1)
        for malo in (cuerpo + "A." + firma, cuerpo + "." + firma[:-1] + ("0" if firma[-1] != "0" else "1"),
                     "", "basura", "a.b", token[::-1], cuerpo, "." + firma):
            assert verificar_token_candidata(malo, carpeta, SECRETO) is None, malo

    async def test_un_token_caducado_no_se_acepta(self, entorno):
        carpeta, token = await self._token(entorno)
        assert verificar_token_candidata(token, carpeta, SECRETO) is not None
        import time
        assert verificar_token_candidata(token, carpeta, SECRETO, ahora=time.time() + 16 * 60) is None

    async def test_sin_clave_del_servidor_es_503_y_no_se_busca(self, entorno, monkeypatch):
        carpeta = await sembrar_flash(entorno.banco)
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=""))
        r = await descubrir(carpeta)
        assert r.status_code == 503 and entorno.fuentes.llamadas == []


# ── Estado de las fuentes, errores del cuerpo y acceso ────────────────────────────────────────────

class TestRespuestaYAcceso:

    async def test_el_estado_de_cada_fuente_y_los_avisos_se_devuelven_tal_cual(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        entorno.fuentes.fuentes.update(comic_vine=FUENTE_SIN_CLAVE, tebeosfera=FUENTE_ERROR)
        entorno.fuentes.avisos = ["Comic Vine no está configurado.", "Tebeosfera: no se pudo consultar ahora mismo."]
        cuerpo = (await descubrir(carpeta)).json()
        assert cuerpo["fuentes"] == {"comic_vine": "sin_clave", "anilist": "ok", "tebeosfera": "error", "gcd": "ok"}
        assert cuerpo["avisos"] == entorno.fuentes.avisos and cuerpo["candidatas"] == []

    async def test_el_esquema_de_la_respuesta_es_estable(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        r = await descubrir(carpeta)
        assert r.headers["cache-control"] == "no-store"
        c = r.json()
        assert set(c) == {"consulta", "consulta_propuesta", "grupo", "fuentes", "avisos", "candidatas"}
        assert set(c["grupo"]) == {"clave", "carpeta_contextual", "n_archivos"}
        assert set(c["candidatas"][0]) == {
            "token", "fuente", "titulo", "anio", "tradicion_sugerida", "sitio_url", "portada", "descripcion",
            "ya_en_biblioteca", "parecidas_locales", "coincidencia_con_la_carpeta"}
        assert set(c["candidatas"][0]["coincidencia_con_la_carpeta"]) == {"en_conflicto", "senales"}

    async def test_un_grupo_que_no_existe_es_404_y_no_busca(self, entorno):
        r = await descubrir("Comics/Inexistente")
        assert r.status_code == 404 and entorno.fuentes.llamadas == []

    @pytest.mark.parametrize("cuerpo", [{}, {"clave": ""}, {"clave": "x" * 1001}, {"clave": "a", "consulta": "x" * 201},
                                       {"clave": "a", "extra": 1}, {"clave": 5}])
    async def test_cuerpos_invalidos_son_422(self, entorno, cuerpo):
        async with cliente() as c:
            r = await c.post(RUTA, json=cuerpo)
        assert r.status_code == 422 and entorno.fuentes.llamadas == []

    async def test_sin_sesion_no_hay_datos_ni_busqueda(self, entorno, monkeypatch):
        from zascarr.config import get_settings
        from zascarr.services.auth import hash_password
        ajustes = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
        carpeta = await sembrar_flash(entorno.banco)
        r = await descubrir(carpeta)
        assert r.status_code == 401 and entorno.fuentes.llamadas == [] and "candidatas" not in r.text

    async def test_no_se_registra_ni_la_ruta_ni_la_consulta(self, entorno, caplog, capfd):
        await entorno.banco.sembrar(archivo("Comics/CarpetaSecretaQ9/Cosa 01.cbz"))
        with caplog.at_level("DEBUG"):
            await descubrir("Comics/CarpetaSecretaQ9", "ConsultaSecretaQ9")
        salida = capfd.readouterr()
        for visible in (caplog.text, salida.out, salida.err):
            assert "SecretaQ9" not in visible and BIB not in visible


# ── Solo lectura y coste ─────────────────────────────────────────────────────────────────────

TABLAS = ("files", "series", "issues", "import_runs", "asignacion_operaciones", "local_aliases")


async def _huella(banco):
    async with banco.fabrica() as s:
        return {t: tuple((await s.execute(text(
            f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {t} x"
        ))).one()) for t in TABLAS}


class TestSoloLecturaYCoste:

    async def test_cero_escrituras(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        await _serie(entorno.banco, "Flash", 1988, comic_vine_id=7)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "7", "Flash", 1988),
                                      res(MetadataSource.ANILIST, "5", "Flash", 1987)]
        await descubrir(carpeta)                                   # calienta la conexión
        api_revision.reiniciar_ritmo_para_pruebas()
        antes = await _huella(entorno.banco)
        entorno.banco.sentencias.clear()
        assert (await descubrir(carpeta)).status_code == 200
        assert entorno.banco.sentencias, "no se ejecutó ninguna consulta: la prueba no mide nada"
        assert all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in entorno.banco.sentencias)
        assert await _huella(entorno.banco) == antes

    async def test_el_numero_de_consultas_no_crece_con_los_archivos_ni_los_resultados(self, entorno):
        carpeta = await sembrar_flash(entorno.banco, n=3)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        await descubrir(carpeta)
        api_revision.reiniciar_ritmo_para_pruebas()
        entorno.banco.sentencias.clear()
        await descubrir(carpeta)
        pocas = len(entorno.banco.sentencias)

        await entorno.banco.limpiar()
        await entorno.banco.sembrar(*(archivo(f"{carpeta}/Flash {i:05d} (1987).cbz") for i in range(2000)),
                                    *(archivo(f"Comics/Otra {i % 50:02d}/Cosa {i:04d}.cbz") for i in range(500)))
        for i in range(40):
            await _serie(entorno.banco, f"Serie {i}", 1990 + i % 5, comic_vine_id=1000 + i)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, str(1000 + i), f"Serie {i}", 1990 + i % 5)
                                      for i in range(40)] + [res(MetadataSource.ANILIST, "7", "Flash", 1987)]
        api_revision.reiniciar_ritmo_para_pruebas()
        entorno.banco.sentencias.clear()
        r = await descubrir(carpeta)
        muchas = len(entorno.banco.sentencias)
        assert r.status_code == 200 and len(r.json()["candidatas"]) == 41
        assert pocas == muchas <= 3, (pocas, muchas)


# ── Una búsqueda a la vez y con calma ────────────────────────────────────────────────────────

class TestRitmo:

    async def test_una_segunda_busqueda_a_la_vez_es_429_y_no_llega_a_las_fuentes(self, entorno):
        carpeta = await sembrar_flash(entorno.banco)
        await api_revision._BUSQUEDA_EN_CURSO.acquire()
        try:
            r = await descubrir(carpeta)
        finally:
            api_revision._BUSQUEDA_EN_CURSO.release()
        assert r.status_code == 429 and "Retry-After" in r.headers and entorno.fuentes.llamadas == []

    async def test_dos_busquedas_seguidas_se_espacian(self, entorno, monkeypatch):
        carpeta = await sembrar_flash(entorno.banco)
        monkeypatch.setattr(api_revision, "MIN_INTERVALO_S", 60.0)
        assert (await descubrir(carpeta)).status_code == 200
        segunda = await descubrir(carpeta)
        assert segunda.status_code == 429 and int(segunda.headers["Retry-After"]) >= 1
        assert len(entorno.fuentes.llamadas) == 1

    async def test_el_bloqueo_se_libera_aunque_la_busqueda_falle(self, entorno, monkeypatch):
        carpeta = await sembrar_flash(entorno.banco)

        async def rota(self, consulta, limit=10):
            raise RuntimeError("fallo inesperado")
        monkeypatch.setattr(DiscoveryService, "search_detallada", rota)   # esta SÍ es una función: se enlaza
        async with cliente() as c:
            with pytest.raises(RuntimeError):
                await c.post(RUTA, json={"clave": carpeta})
        assert not api_revision._BUSQUEDA_EN_CURSO.locked()

    async def test_un_404_o_un_422_no_consumen_el_espaciado(self, entorno, monkeypatch):
        carpeta = await sembrar_flash(entorno.banco)
        monkeypatch.setattr(api_revision, "MIN_INTERVALO_S", 60.0)
        assert (await descubrir("Comics/Inexistente")).status_code == 404
        assert (await descubrir(carpeta)).status_code == 200        # no se bloquea por el 404 anterior

