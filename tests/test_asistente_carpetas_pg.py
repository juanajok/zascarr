# ruff: noqa: E501, F401, F811
"""#118 (MIT-M3-US01) — «Descubrir o crear desde un grupo»: primer paso del asistente de la rebanada 2e, sobre
Postgres real y con las fuentes SIMULADAS. Una clase por criterio; cada prueba afirma lo observable en la página
(texto, formularios, qué se consultó) y lo que NO cambió en la base.

| # | Criterio de #118 | Clase |
|---|---|---|
| 1 | Apertura y contexto; no consulta fuentes | `TestCriterio1Apertura` |
| 2 | Búsqueda a petición, asociada al grupo, sin crear | `TestCriterio2Busqueda` |
| 3 | Candidatas sin preselección, sin inventar campos | `TestCriterio3SinPreseleccion` |
| 4 | Elección explícita de candidata y de tradición | `TestCriterio4Eleccion` |
| 5 | Errores parciales de fuentes | `TestCriterio5ErroresParciales` |
| 6 | Formulario a mano sin dependencias externas | `TestCriterio6Manual` |
| 7 | Atribución de las señales | `TestCriterio7Senales` |

Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import html
import os
import re
from types import SimpleNamespace
from urllib.parse import quote

import httpx
import pytest
from sqlalchemy import text

from tests.test_descubrimiento_grupo_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CV_OK,
    SECRETO,
    cliente,
    entorno,
    res,
    sembrar_flash,
    url_bd,
)
from tests.test_revision_carpetas_pg import archivo
from zascarr.api import revision as api_revision
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.discovery import FUENTE_APAGADA, FUENTE_ERROR, FUENTE_OK, FUENTE_SIN_CLAVE
from zascarr.services.tokens_revision import verificar_token_candidata
from zascarr.web import asistente_carpetas, discovery

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

RUTA = "/ui/pendientes/carpetas/asistente"
CARPETA = "Comics/Flash (1987)"


@pytest.fixture(autouse=True)
def _secreto_en_el_asistente(monkeypatch):
    monkeypatch.setattr(asistente_carpetas, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
    monkeypatch.setattr(discovery, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))     # la vista previa del alta (U19)


async def abrir(clave: str = CARPETA) -> httpx.Response:
    async with cliente() as c:
        return await c.get(RUTA, params={"clave": clave})


async def buscar(clave: str = CARPETA, consulta: str | None = "Flash") -> httpx.Response:
    datos = {"clave": clave, **({"consulta": consulta} if consulta is not None else {})}
    async with cliente() as c:
        return await c.post(f"{RUTA}/buscar", data=datos)


async def elegir(**datos) -> httpx.Response:
    async with cliente() as c:
        return await c.post(f"{RUTA}/elegir", data={"clave": CARPETA, **datos})


async def manual(clave: str = CARPETA, *, htmx: bool = True) -> httpx.Response:
    cabeceras = {"HX-Request": "true"} if htmx else {}
    async with cliente() as c:
        return await c.get(f"{RUTA}/manual", params={"clave": clave}, headers=cabeceras)


def visible(t: str) -> str:
    """El texto que ve la persona: sin etiquetas, con las entidades resueltas y los espacios normalizados."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())


def tokens_de(t: str) -> list[str]:
    return re.findall(r'name="candidata" value="([^"]+)"', t)


async def estado_de_la_base(banco) -> dict:
    async with banco.fabrica() as s:
        return {tabla: [tuple(r) for r in (await s.execute(text(f"SELECT * FROM {tabla} ORDER BY 1"))).all()]
                for tabla in ("series", "issues", "files", "asignacion_operaciones", "alta_operaciones",
                              "vinculacion_operaciones", "local_aliases")}


# ── 1. Apertura y contexto ──────────────────────────────────────────────────────────────────────

class TestCriterio1Apertura:

    async def test_conserva_la_clave_enseña_el_numero_de_archivos_y_propone_una_consulta_editable(self, entorno):
        await sembrar_flash(entorno.banco, 3)
        r = await abrir()
        t = r.text
        assert r.status_code == 200
        assert CARPETA in visible(t) and re.search(r"Registros en esta carpeta\s*3\b", visible(t))
        assert f'name="clave" value="{CARPETA}"' in t                                   # se conserva la clave
        campo = re.search(r'<input[^>]*name="consulta"[^>]*>', t).group(0)
        assert 'value="Flash"' in campo and "readonly" not in campo and "disabled" not in campo   # propuesta, editable

    async def test_abrir_no_consulta_ninguna_fuente_ni_sale_a_la_red(self, entorno, monkeypatch):
        await sembrar_flash(entorno.banco)
        reales = []
        original = httpx.AsyncClient.send

        async def vigilado(self, request, **kw):
            if not isinstance(self._transport, httpx.ASGITransport):
                reales.append(request.url.host)
            return await original(self, request, **kw)
        monkeypatch.setattr(httpx.AsyncClient, "send", vigilado)
        antes = await estado_de_la_base(entorno.banco)
        assert (await abrir()).status_code == 200
        assert entorno.fuentes.llamadas == [] and reales == []
        assert await estado_de_la_base(entorno.banco) == antes

    async def test_sin_nada_que_proponer_el_campo_va_vacio_y_se_dice(self, entorno):
        await entorno.banco.sembrar(archivo("Comics/_Omnibus/001.cbz"))
        r = await abrir("Comics/_Omnibus")
        campo = re.search(r'<input[^>]*name="consulta"[^>]*>', r.text).group(0)
        assert 'value=""' in campo and "escribe el título" in visible(r.text)
        assert entorno.fuentes.llamadas == []

    async def test_un_grupo_que_ya_no_existe_es_404_y_no_consulta(self, entorno):
        r = await abrir("Comics/NoExiste")
        assert r.status_code == 404 and "ya no tiene registros pendientes" in visible(r.text)
        assert entorno.fuentes.llamadas == []

    async def test_la_clave_y_el_titulo_se_escapan(self, entorno):
        clave = 'Comics/<script>alert(1)</script> (2000)'
        await entorno.banco.sembrar(archivo(f"{clave}/Cosa 01.cbz"))
        r = await abrir(clave)
        assert "<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text

    async def test_la_pagina_de_carpetas_enlaza_al_asistente_con_la_clave_codificada(self, entorno):
        await sembrar_flash(entorno.banco)
        async with cliente() as c:
            r = await c.get("/ui/pendientes/carpetas")
        assert f'href="{RUTA}?clave={quote(CARPETA, safe="/")}"' in r.text
        assert entorno.fuentes.llamadas == []


# ── 2. Búsqueda a petición ──────────────────────────────────────────────────────────────────────

class TestCriterio2Busqueda:

    async def test_se_usa_la_consulta_que_la_persona_ve_y_se_busca_una_vez(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        r = await buscar(consulta="  Flash Annual  ")
        assert r.status_code == 200 and entorno.fuentes.llamadas == ["Flash Annual"]
        assert "Se ha buscado «Flash Annual»" in visible(r.text)

    async def test_sin_consulta_escrita_se_usa_la_propuesta(self, entorno):
        await sembrar_flash(entorno.banco)
        r = await buscar(consulta="")
        assert r.status_code == 200 and entorno.fuentes.llamadas == ["Flash"]

    async def test_los_resultados_conservan_el_grupo_de_origen(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987),
                                      res(MetadataSource.ANILIST, "2", "Flash", 2000, tradicion=ComicTradition.MANGA)]
        r = await buscar()
        assert r.text.count(f'name="clave" value="{CARPETA}"') == 2
        for token in tokens_de(r.text):                                # y cada candidata está firmada PARA ese grupo
            assert verificar_token_candidata(token, CARPETA, SECRETO) is not None
            assert verificar_token_candidata(token, "Comics/Otra", SECRETO) is None

    async def test_buscar_no_crea_series_ni_vincula_nada(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        antes = await estado_de_la_base(entorno.banco)
        assert (await buscar()).status_code == 200
        assert await estado_de_la_base(entorno.banco) == antes

    async def test_sin_consulta_posible_se_dice_y_no_se_busca(self, entorno):
        await entorno.banco.sembrar(archivo("Comics/_Omnibus/001.cbz"))
        r = await buscar("Comics/_Omnibus", consulta="")
        assert r.status_code == 200 and "Escribe qué buscar" in visible(r.text)
        assert entorno.fuentes.llamadas == []

    async def test_comparte_el_ritmo_de_cortesia_con_el_endpoint_json(self, entorno, monkeypatch):
        await sembrar_flash(entorno.banco)
        monkeypatch.setattr(api_revision, "MIN_INTERVALO_S", 60.0)
        assert "Se ha buscado" in visible((await buscar()).text)
        segunda = await buscar()
        assert segunda.status_code == 200 and "Espera unos segundos" in visible(segunda.text)
        assert "Vuelve a intentarlo en" in visible(segunda.text) and entorno.fuentes.llamadas == ["Flash"]
        async with cliente() as c:                                       # y la API ve el mismo espaciado
            j = await c.post("/api/revision/descubrir", json={"clave": CARPETA})
        assert j.status_code == 429


# ── 3. Candidatas sin preselección ──────────────────────────────────────────────────────────────

class TestCriterio3SinPreseleccion:

    async def test_cada_candidata_muestra_su_fuente_y_nada_llega_elegido_ni_siquiera_una_sola(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        t = (await buscar()).text
        assert "Comic Vine" in visible(t) and "Flash (1987)" in visible(t)
        assert 'selected disabled' in t or 'selected' in t
        assert len(re.findall(r"<option[^>]*\bselected\b[^>]*>", t)) == 1          # solo el marcador deshabilitado
        assert re.search(r'<option value="" selected disabled>', t)
        assert "checked" not in t and not re.search(r"\b(recomendad\w*|mejor|elegid\w*|preseleccionad\w*)\b", visible(t), re.I)

    async def test_no_se_inventan_los_campos_que_la_fuente_no_trae(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.GCD, "9", "Sin datos", None, sitio=None)]
        t = (await buscar()).text
        v = visible(t)
        assert "Sin datos" in v and "None" not in v and "()" not in v
        assert "discovery-card-desc" not in t and "↗" not in t                    # sin descripción ni ficha
        assert 'class="cover cover-missing"' in t                                  # portada ausente = marcador CSS

    async def test_el_orden_es_el_de_las_fuentes_y_no_depende_del_orden_de_llegada(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.GCD, "9", "Zeta", 1990),
                                      res(MetadataSource.COMIC_VINE, "2", "Flash", 1987)]
        titulos = re.findall(r'discovery-card-title">\s*([^<(]+)', (await buscar()).text)
        assert [x.strip() for x in titulos] == ["Flash", "Zeta"]


# ── 4. Elección explícita de candidata y de tradición ───────────────────────────────────────────

class TestCriterio4Eleccion:

    async def _token(self, entorno, **kw) -> str:
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987, **kw)]
        return tokens_de((await buscar()).text)[0]

    async def test_la_sugerencia_de_la_fuente_se_distingue_y_no_esta_elegida(self, entorno):
        t = (await buscar_con_una(entorno)).text
        assert "La fuente lo clasifica como Grapa americana" in visible(t)
        assert "no de la obra: elige tú" in visible(t)
        assert not re.search(r'<option value="american"[^>]*\bselected\b', t)

    async def test_la_carpeta_solo_es_una_pista_y_tampoco_marca_nada(self, entorno):
        t = (await buscar_con_una(entorno)).text
        assert "La carpeta «Comics» suele guardar: Grapa americana, Británico" in visible(t)
        assert not re.search(r'<option value="(american|british)"[^>]*\bselected\b', t)

    async def test_sin_tradicion_no_se_continua_y_se_vuelve_a_ofrecer_el_paso(self, entorno):
        token = await self._token(entorno)
        antes = await estado_de_la_base(entorno.banco)
        r = await elegir(candidata=token)
        v = visible(r.text)
        assert r.status_code == 200 and "Elige la tradición antes de continuar" in v and "Elección anotada" not in v
        assert f'name="candidata" value="{token}"' in r.text                     # el mismo paso, para reintentar
        assert await estado_de_la_base(entorno.banco) == antes

    async def test_con_tradicion_la_eleccion_se_anota_conserva_el_grupo_y_no_crea_la_serie(self, entorno):
        token = await self._token(entorno)
        antes = await estado_de_la_base(entorno.banco)
        r = await elegir(candidata=token, tradition="british")
        v = visible(r.text)
        assert r.status_code == 200 and "Elección anotada" in v
        assert "Todavía no se ha creado ninguna serie" in v and CARPETA in v
        assert "Flash (1987)" in v and "Comic Vine" in v
        assert re.search(r"Tradición elegida\s*Británico", v)                      # la elegida, no la sugerida
        assert "La fuente sugería Grapa americana (era solo una sugerencia)" in v
        assert await estado_de_la_base(entorno.banco) == antes

    async def test_el_titulo_sale_de_lo_firmado_no_de_lo_que_reenvia_el_navegador(self, entorno):
        token = await self._token(entorno)
        r = await elegir(candidata=token, tradition="american", titulo="TÍTULO FALSO", anio="1999")
        v = visible(r.text)
        assert "Flash (1987)" in v and "TÍTULO FALSO" not in v and "1999" not in v

    async def test_un_token_de_otro_grupo_o_manipulado_no_vale(self, entorno):
        token = await self._token(entorno)
        otro = await elegir(clave="Comics/Otra", candidata=token, tradition="american")
        roto = await elegir(candidata=token[:-4] + "XXXX", tradition="american")
        for r in (otro, roto):
            assert r.status_code == 200 and "ya no vale" in visible(r.text) and "Elección anotada" not in visible(r.text)

    async def test_una_tradicion_inexistente_se_rechaza(self, entorno):
        token = await self._token(entorno)
        r = await elegir(candidata=token, tradition="inventada")
        assert "no es válida" in visible(r.text) and "Elección anotada" not in visible(r.text)


async def buscar_con_una(entorno):
    await sembrar_flash(entorno.banco)
    entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
    return await buscar()


# ── 5. Errores parciales ────────────────────────────────────────────────────────────────────────

class TestCriterio5ErroresParciales:

    async def test_la_fuente_que_falla_se_identifica_y_las_demas_siguen_disponibles(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987)]
        entorno.fuentes.fuentes["anilist"] = FUENTE_ERROR
        entorno.fuentes.avisos = ["AniList: no se pudo consultar ahora mismo."]
        v = visible((await buscar()).text)
        assert "AniList: no ha respondido ahora mismo" in v and "Comic Vine: ha respondido" in v
        assert "No han respondido: AniList" in v and "Flash (1987)" in v
        assert "Ninguna fuente" not in v                                         # un error no es «sin coincidencias»

    async def test_si_todas_fallan_no_se_dice_que_no_hay_coincidencias(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.fuentes = {f: FUENTE_ERROR for f in ("comic_vine", "anilist", "tebeosfera", "gcd")}
        v = visible((await buscar()).text)
        assert "No se ha podido consultar ninguna fuente" in v and "No es que no haya coincidencias" in v
        assert "ha encontrado coincidencias" not in v

    async def test_con_error_en_una_y_sin_resultados_en_las_otras_se_dicen_las_dos_cosas(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.fuentes["tebeosfera"] = FUENTE_ERROR
        v = visible((await buscar()).text)
        assert "No han respondido: Tebeosfera" in v
        assert "Ninguna fuente que ha respondido ha encontrado coincidencias" in v

    async def test_sin_ningun_error_y_sin_resultados_es_sin_coincidencias(self, entorno):
        await sembrar_flash(entorno.banco)
        v = visible((await buscar()).text)
        assert "Ninguna fuente que ha respondido ha encontrado coincidencias" in v and "No han respondido" not in v

    async def test_con_las_fuentes_apagadas_se_dice_y_se_ofrece_el_camino_a_mano(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.fuentes = {"comic_vine": FUENTE_SIN_CLAVE, "anilist": FUENTE_APAGADA,
                                   "tebeosfera": FUENTE_APAGADA, "gcd": FUENTE_APAGADA}
        v = visible((await buscar()).text)
        assert "Comic Vine: sin clave configurada" in v and "AniList: apagada en los ajustes" in v
        assert "No hay ninguna fuente activa" in v and "crear la serie a mano" in v
        assert "Ninguna fuente que ha respondido" not in v


# ── 6. Formulario a mano ────────────────────────────────────────────────────────────────────────

class TestCriterio6Manual:

    async def test_se_abre_sin_consultar_fuentes_y_conserva_la_clave(self, entorno):
        await sembrar_flash(entorno.banco)
        antes = await estado_de_la_base(entorno.banco)
        r = await manual()
        assert r.status_code == 200 and f'name="clave" value="{CARPETA}"' in r.text
        assert 'name="titulo"' in r.text and 'value="Flash"' in r.text            # título propuesto, editable
        assert entorno.fuentes.llamadas == [] and await estado_de_la_base(entorno.banco) == antes

    async def test_un_enlace_directo_sin_htmx_da_la_pagina_completa_con_el_formulario_abierto(self, entorno):
        await sembrar_flash(entorno.banco)
        r = await manual(htmx=False)
        t = r.text
        assert r.status_code == 200 and "<html" in t and "Elegir la serie de una carpeta" in visible(t)
        assert 'name="titulo"' in t and f'name="clave" value="{CARPETA}"' in t
        assert entorno.fuentes.llamadas == []

    async def test_se_abre_sin_clave_de_firma_ni_fuentes_y_envia_a_la_vista_previa_del_alta(self, entorno, monkeypatch):
        """Abrir el formulario no necesita ninguna credencial. Desde #189 envía a la vista previa del alta (la misma de
        Descubrir), que es la que firma y por tanto la que necesita la clave del servidor: se prueba en `test_alta_manual_pg`."""
        await sembrar_flash(entorno.banco)
        monkeypatch.setattr(asistente_carpetas, "get_settings", lambda: SimpleNamespace(secret_key=""))
        assert (await abrir()).status_code == 200
        r = await manual()
        assert r.status_code == 200 and 'hx-post="/ui/descubrir/revisar"' in r.text
        assert 'name="titulo"' in r.text and 'name="tradition"' in r.text and f'name="clave" value="{CARPETA}"' in r.text
        assert entorno.fuentes.llamadas == []


# ── 7. Atribución de las señales ────────────────────────────────────────────────────────────────

class TestCriterio7Senales:

    async def test_las_senales_se_presentan_frente_a_esta_candidata_y_no_como_las_de_otra(self, entorno):
        await sembrar_flash(entorno.banco)
        entorno.fuentes.resultados = [res(MetadataSource.COMIC_VINE, "1", "Flash", 1987),
                                      res(MetadataSource.COMIC_VINE, "2", "Batman", 2011)]
        t = (await buscar()).text
        assert "frente a <strong>esta</strong> candidata" in t
        assert "Serie sugerida" not in visible(t)                    # ninguna señal «guardada» disfrazada de nueva

    async def test_el_contexto_de_apertura_no_muestra_senales_de_una_candidata_guardada(self, entorno):
        await sembrar_flash(entorno.banco)
        v = visible((await abrir()).text)
        assert "Qué se ha observado" not in v and "Serie sugerida" not in v
