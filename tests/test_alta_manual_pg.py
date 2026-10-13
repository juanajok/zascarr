# ruff: noqa: E501, F401, F811
"""#189 (MIT-M9) — alta manual de series SIN fuentes, desde la interfaz: Postgres real y las fuentes SIMULADAS para
comprobar que no se llaman. Reutiliza la vista previa y la confirmación del alta (2b); no hay lógica de negocio nueva en
la capa web. Tres historias:

| Historia | Qué cubre | Clase |
|---|---|---|
| US01 | Crear una serie local mínima | `TestUS01CrearLaSerieMinima` |
| US02 | Coincidencia local sin bloquear | `TestUS02CoincidenciaLocal` |
| US03 | Confirmar y entregar a #119 | `TestUS03ConfirmarYEntregar` |

Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import html
import os
import re
from types import SimpleNamespace
from urllib.parse import unquote, urlencode
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_descubrimiento_grupo_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    SECRETO,
    cliente,
    entorno,
    sembrar_flash,
    url_bd,
)
from zascarr.models import ComicTradition, Series
from zascarr.services.discovery import DiscoveryService
from zascarr.web import asistente_vinculacion
from zascarr.web import discovery as web_discovery

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

REVISAR, CREAR, DESHACER = "/ui/descubrir/revisar", "/ui/descubrir/crear", "/ui/descubrir/deshacer"
CARPETA = "Comics/Flash (1987)"


@pytest.fixture(autouse=True)
def _secreto(monkeypatch):
    ajustes = lambda: SimpleNamespace(secret_key=SECRETO)           # noqa: E731
    monkeypatch.setattr(web_discovery, "get_settings", ajustes)
    monkeypatch.setattr(asistente_vinculacion, "get_settings", ajustes)


async def enviar(ruta: str, campos: dict | list) -> httpx.Response:
    pares = list(campos.items()) if isinstance(campos, dict) else campos
    async with cliente() as c:
        return await c.post(ruta, content=urlencode(pares),
                            headers={"Content-Type": "application/x-www-form-urlencoded", "HX-Request": "true"})


async def revisar(titulo: str, tradicion: str = "american", *, anio: str = "", clave: str | None = None, **extra) -> httpx.Response:
    campos = {"titulo": titulo, "anio": anio, "tradition": tradicion, **extra}
    if clave:
        campos["clave"] = clave
    return await enviar(REVISAR, campos)


def visible(t: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())


def token_de(t: str) -> str:
    m = re.search(r'name="token" value="([^"]+)"', t)
    assert m, "la vista previa no trae token (¿falta decidir?)"
    return html.unescape(m.group(1))


def campos_ocultos(t: str, formulario: int = 0) -> list[tuple[str, str]]:
    f = re.findall(r"<form[^>]*>.*?</form>", t, re.S)[formulario]
    return [(html.unescape(n), html.unescape(v)) for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', f)]


async def n_series(banco) -> int:
    async with banco.fabrica() as s:
        return (await s.execute(text("SELECT count(*) FROM series"))).scalar_one()


async def estado(banco) -> dict:
    async with banco.fabrica() as s:
        return {t: [tuple(r) for r in (await s.execute(text(f"SELECT * FROM {t} ORDER BY 1"))).all()]
                for t in ("series", "files", "issues", "alta_operaciones", "vinculacion_operaciones")}


async def serie(banco, titulo: str, anio: int | None = 1987, tradicion=ComicTradition.AMERICAN):
    sid = uuid4()
    async with banco.fabrica() as s:
        s.add(Series(id=sid, title=titulo, start_year=anio, tradition=tradicion))
        await s.commit()
    return sid


def formulario_de_crear(t: str) -> list[tuple[str, str]]:
    """Los campos del formulario que lleva el token (el de «Crear serie vacía»), tal como los enviaría el navegador."""
    for f in re.findall(r"<form[^>]*>.*?</form>", t, re.S):
        if 'name="token"' in f:
            return [(html.unescape(n), html.unescape(v))
                    for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', f)]
    raise AssertionError("la vista previa no ofrece crear (¿falta decidir?)")


async def crear(titulo: str, tradicion: str = "american", **kw) -> tuple[httpx.Response, str]:
    """Revisar y confirmar, como lo haría la persona. Devuelve (resultado, token)."""
    v = await revisar(titulo, tradicion, **kw)
    campos = formulario_de_crear(v.text)
    return await enviar(CREAR, campos), dict(campos)["token"]


# ── US01. Crear la serie mínima ─────────────────────────────────────────────────────────────────

class TestUS01CrearLaSerieMinima:

    async def test_el_alta_a_mano_esta_en_descubrir_y_no_consulta_ninguna_fuente(self, entorno, monkeypatch):
        reales = []
        original = httpx.AsyncClient.send

        async def vigilado(self, request, **kw):
            if not isinstance(self._transport, httpx.ASGITransport):
                reales.append(request.url.host)
            return await original(self, request, **kw)
        monkeypatch.setattr(httpx.AsyncClient, "send", vigilado)
        async with cliente() as c:
            t = (await c.get("/ui/descubrir")).text
        assert "Crear la serie a mano" in visible(t) and 'name="titulo"' in t and 'hx-post="/ui/descubrir/revisar"' in t
        r = await revisar("Mortadelo y Filemón", "tebeo")
        assert r.status_code == 200 and entorno.fuentes.llamadas == [] and reales == []

    async def test_pide_solo_titulo_y_tradicion_y_el_anio_es_opcional(self, entorno):
        antes = await estado(entorno.banco)
        sin_anio = visible((await revisar("Mortadelo", "tebeo")).text)
        con_anio = visible((await revisar("Mortadelo", "tebeo", anio="1970")).text)
        assert "Se guardará como «Mortadelo»" in sin_anio and "Tradición elegida: Tebeo español" in sin_anio
        assert "Se guardará como «Mortadelo» (1970)" in con_anio
        assert "Se creará una serie vacía: sin números ni archivos" in con_anio
        assert "origen «manual»" in con_anio and "no viene de ninguna fuente" in con_anio     # procedencia visible
        assert await estado(entorno.banco) == antes                       # la vista previa no escribe nada

    async def test_la_tradicion_no_se_infiere_ni_tiene_valor_por_defecto(self, entorno):
        async with cliente() as c:
            t = (await c.get("/ui/descubrir")).text
        selector = re.search(r'<select id="manual-tradicion".*?</select>', t, re.S).group(0)
        assert '<option value="" selected disabled>' in selector and selector.count("selected") == 1
        r = await enviar(REVISAR, {"titulo": "Mortadelo", "anio": ""})      # sin tradición: el servidor no la inventa
        assert r.status_code == 422

    async def test_no_inventa_editorial_pais_idioma_formato_ni_procedencia_externa(self, entorno):
        r, _ = await crear("Serie rara")
        assert r.status_code == 200
        async with entorno.banco.fabrica() as s:
            f = (await s.execute(text(
                "SELECT title, start_year, tradition, publisher_id, imprint_id, universe_id, description, cover_url, "
                "total_issues, comic_vine_id, anilist_id, tebeosfera_slug, gcd_id, metadata_source, metadata->'alta'->>'origen' "
                "FROM series"))).one()
        assert f[0] == "Serie rara" and f[1] is None and f[2] == "american"
        assert all(v is None for v in f[3:13])                           # nada de editorial, descripción, portada ni ids
        assert f[13] == "manual" and f[14] == "manual"                  # procedencia manual, y la guarda el servicio

    @pytest.mark.parametrize("titulo,anio,mensaje", [
        ("   ", "", "El título no puede estar vacío"),
        ("###", "", "El título no puede estar vacío ni ser solo símbolos"),
        ("Flash", "mil", "El año debe ser un número"),
        ("Flash", "1500", "El año no es válido"),
        ("Fla\x00sh", "", "caracteres que no se pueden guardar"),
    ])
    async def test_un_dato_invalido_se_explica_en_el_formulario_y_no_crea_nada(self, entorno, titulo, anio, mensaje):
        antes = await estado(entorno.banco)
        r = await revisar(titulo, "american", anio=anio)
        t, v = r.text, visible(r.text)
        assert r.status_code == 200 and mensaje in v and 'name="titulo"' in t     # el formulario sigue ahí
        assert "Se guardará como" not in v and await estado(entorno.banco) == antes
        assert 'name="token"' not in t

    async def test_lo_escrito_se_escapa_y_no_se_pierde_al_fallar(self, entorno):
        r = await revisar("<img src=x onerror=alert(1)>", "american", anio="mil")
        assert "<img src=x" not in r.text and "&lt;img" in r.text

    async def test_crear_la_serie_no_vincula_ni_mueve_ni_renombra_archivos(self, entorno):
        carpeta = await sembrar_flash(entorno.banco, 3)
        antes = await estado(entorno.banco)
        r, _ = await crear("Flash", "american", anio="1987", clave=carpeta)
        assert r.status_code == 200 and "creada" in visible(r.text)
        despues = await estado(entorno.banco)
        assert despues["files"] == antes["files"] and despues["issues"] == []          # ni vínculos ni números
        assert despues["vinculacion_operaciones"] == [] and len(despues["series"]) == 1


# ── US02. Coincidencia local sin bloquear ───────────────────────────────────────────────────────

class TestUS02CoincidenciaLocal:

    async def test_sin_coincidencias_se_crea_sin_preguntar(self, entorno):
        v = await revisar("Serie nueva", "american", anio="2001")
        assert 'name="token"' in v.text and "Series que ya tienes y se parecen" not in visible(v.text)

    async def test_una_candidata_se_muestra_con_sus_datos_y_no_se_elige_ni_se_fusiona(self, entorno):
        sid = await serie(entorno.banco, "Flash", 1987)
        antes = await estado(entorno.banco)
        r = await revisar("Flash", "american", anio="1987")
        t, v = r.text, visible(r.text)
        assert "Series que ya tienes y se parecen" in v and f'href="/ui/series/{sid}"' in t and "Flash" in v and "(1987)" in v
        assert "Es esta" in v and "Es distinta: crear otra" in v
        assert 'name="token"' not in t                                  # sin decisión no hay nada que ejecutar
        assert await estado(entorno.banco) == antes and entorno.fuentes.llamadas == []

    async def test_varias_candidatas_distinguibles_y_la_consulta_es_solo_local(self, entorno, monkeypatch):
        llamadas = []

        async def prohibida(self, *a, **k):
            llamadas.append(1)
            raise AssertionError("no debe consultar fuentes")
        monkeypatch.setattr(DiscoveryService, "search_detallada", prohibida)
        a = await serie(entorno.banco, "Flash", 1987)
        b = await serie(entorno.banco, "Flash", 1988)
        r = await revisar("Flash", "american", anio="1987")
        t = r.text
        assert f'href="/ui/series/{a}"' in t and f'href="/ui/series/{b}"' in t and "(1987)" in visible(t) and "(1988)" in visible(t)
        assert llamadas == []

    async def test_reutilizar_entrega_el_id_de_la_existente_sin_escribir_nada(self, entorno):
        sid = await serie(entorno.banco, "Flash", 1987)
        antes = await estado(entorno.banco)
        v = await revisar("Flash", "american", anio="1987", decision="reutilizar", serie_id=str(sid))
        assert "Se usará la serie existente que elegiste, sin modificarla" in visible(v.text)
        resultado = await enviar(CREAR, [("token", token_de(v.text))])
        t = resultado.text
        assert "ya estaba en tu biblioteca" in visible(t) and f'href="/ui/series/{sid}"' in t
        assert await estado(entorno.banco) == antes and 'name="series_id"' not in t      # nada que deshacer

    async def test_continuar_con_el_alta_es_una_decision_explicita(self, entorno):
        await serie(entorno.banco, "Flash", 1987)
        v = await revisar("Flash", "american", anio="1987", decision="crear_igualmente")
        r = await enviar(CREAR, [("token", token_de(v.text))])
        assert "creada" in visible(r.text) and await n_series(entorno.banco) == 2

    async def test_si_aparecen_parecidas_despues_de_la_vista_previa_se_muestra_el_conflicto_y_no_se_crea(self, entorno):
        v = await revisar("Flash", "american", anio="1987")
        token = token_de(v.text)
        await serie(entorno.banco, "Flash", 1987)                         # aparece mientras se revisaba
        r = await enviar(CREAR, [("token", token)])
        t = visible(r.text)
        assert "Han aparecido series parecidas" in t and "creada" not in t.replace("no se ha creado", "")
        assert await n_series(entorno.banco) == 1

    async def test_demasiadas_parecidas_es_un_bloqueo_visible_y_conserva_el_formulario(self, entorno):
        async with entorno.banco.fabrica() as s:
            s.add_all([Series(id=uuid4(), title="Flash", start_year=1987, tradition=ComicTradition.AMERICAN) for _ in range(101)])
            await s.commit()
        r = await revisar("Flash", "american", anio="1987", decision="crear_igualmente")
        assert "demasiadas para decidir desde aquí" in visible(r.text) and 'name="titulo"' in r.text
        assert await n_series(entorno.banco) == 101


# ── US03. Confirmar y entregar ──────────────────────────────────────────────────────────────────

class TestUS03ConfirmarYEntregar:

    async def test_navegar_o_revisar_no_crea_y_confirmar_exige_su_propia_accion(self, entorno):
        async with cliente() as c:
            assert (await c.get(CREAR)).status_code == 405
        await revisar("Flash", "american")
        await revisar("Flash", "american", anio="1987")
        assert await n_series(entorno.banco) == 0
        assert (await enviar(CREAR, [("cursor", "x")])).status_code == 422               # sin token no hay alta
        malo = visible((await enviar(CREAR, [("token", "no-es-un-token")])).text)
        assert "no es válido" in malo or "No se ha podido" in malo
        assert await n_series(entorno.banco) == 0

    async def test_el_resultado_distingue_creada_y_trae_el_id_de_la_serie(self, entorno):
        r, _ = await crear("Flash", "american", anio="1987")
        t = r.text
        assert "creada" in visible(t) and "Es una serie vacía: sin números ni archivos" in visible(t)
        m = re.search(r'href="/ui/series/([0-9a-f-]{36})"', t)
        assert m, "no hay series_id en el resultado"
        async with entorno.banco.fabrica() as s:
            assert str((await s.execute(text("SELECT id FROM series"))).scalar_one()) == m.group(1)

    async def test_con_carpeta_el_resultado_entrega_serie_y_grupo_a_la_revision_y_no_vincula(self, entorno):
        carpeta = await sembrar_flash(entorno.banco, 3)
        r, _ = await crear("Flash", "american", anio="1987", clave=carpeta)
        t = r.text
        m = re.search(r'href="(/ui/pendientes/carpetas/asistente/vinculacion\?[^"]+)"', t)
        assert m and "todavía no se ha hecho" in visible(t)
        destino = html.unescape(m.group(1))
        async with entorno.banco.fabrica() as s:
            sid = str((await s.execute(text("SELECT id FROM series"))).scalar_one())
        assert f"series_id={sid}" in destino and unquote(destino).count(f"clave={carpeta}") == 1
        async with cliente() as c:                                       # y ese enlace abre la revisión de #119
            pagina = (await c.get(destino)).text
        assert "Revisar selección y números" in visible(pagina) and 'data-marcado="1"' not in pagina
        assert 'class="card lote-listo"' not in pagina

    async def test_sin_carpeta_no_se_inventa_un_grupo_ni_se_redirige(self, entorno):
        r, _ = await crear("Flash", "american", anio="1987")
        t = r.text
        assert "no hay ninguna vinculación pendiente" in visible(t) and "/vinculacion?" not in t

    async def test_el_grupo_sale_del_token_firmado_no_de_lo_que_reenvia_el_navegador(self, entorno):
        carpeta = await sembrar_flash(entorno.banco, 2)
        v = await revisar("Flash", "american", clave=carpeta)
        campos = [(k, val) for k, val in formulario_de_crear(v.text) if k != "clave"] + [("clave", "Comics/Otra")]
        t = (await enviar(CREAR, campos)).text
        destino = unquote(html.unescape(re.search(r'href="(/ui/pendientes/carpetas/asistente/vinculacion\?[^"]+)"', t).group(1)))
        assert f"clave={carpeta}" in destino and "Otra" not in destino

    async def test_un_fallo_tras_el_commit_se_dice_y_comprobar_no_duplica_el_alta(self, entorno, monkeypatch):
        v = await revisar("Flash", "american", anio="1987")
        token = token_de(v.text)
        real = AsyncSession.commit

        async def commit_y_luego_falla(self):
            await real(self)
            raise ConnectionError("se perdió la conexión al confirmar")
        monkeypatch.setattr(AsyncSession, "commit", commit_y_luego_falla)
        r = await enviar(CREAR, [("token", token)])
        monkeypatch.setattr(AsyncSession, "commit", real)
        t = visible(r.text)
        assert r.status_code == 200 and "No se sabe si la serie llegó a crearse" in t and "Comprobar el resultado" in t
        assert "creada" not in t.replace("llegó a crearse", "")                      # no afirma éxito
        assert await n_series(entorno.banco) == 1                                     # y de hecho SÍ estaba
        comprobado = visible((await enviar(CREAR, [("token", token)])).text)
        assert "creada (ya se había creado)" in comprobado and await n_series(entorno.banco) == 1

    async def test_un_fallo_antes_del_commit_no_deja_nada_y_el_mismo_token_crea_una_sola_vez(self, entorno, monkeypatch):
        v = await revisar("Flash", "american", anio="1987")
        token = token_de(v.text)
        real = AsyncSession.commit

        async def falla(self):
            raise ConnectionError("se cayó antes de confirmar")
        monkeypatch.setattr(AsyncSession, "commit", falla)
        r = await enviar(CREAR, [("token", token)])
        monkeypatch.setattr(AsyncSession, "commit", real)
        assert "Comprobar el resultado" in visible(r.text) and await n_series(entorno.banco) == 0
        assert "creada" in visible((await enviar(CREAR, [("token", token)])).text) and await n_series(entorno.banco) == 1

    async def test_confirmar_el_alta_no_autoriza_la_vinculacion(self, entorno):
        carpeta = await sembrar_flash(entorno.banco, 3)
        await crear("Flash", "american", anio="1987", clave=carpeta)
        async with entorno.banco.fabrica() as s:
            vinculados = (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one()
            operaciones = (await s.execute(text("SELECT count(*) FROM vinculacion_operaciones"))).scalar_one()
        assert vinculados == 0 and operaciones == 0


