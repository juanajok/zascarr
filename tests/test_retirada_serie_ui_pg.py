# ruff: noqa: E501, F401, F811
"""Retirar una serie de la biblioteca desde su ficha (BL-SER1, #303) — pruebas sobre Postgres real y la aplicación entera.

Se recorre lo que recorre la persona: el enlace de la ficha `/ui/series/{id}`, la vista previa, la confirmación con un `POST`
de formulario (sin JavaScript), la misma confirmación como petición htmx (solo el panel) y «Por revisar». El servicio ya está
probado en `test_retirada_serie_pg.py`; aquí solo se prueba que la superficie NO añade reglas y dice las cosas en llano.
El recorrido en un navegador real (teclado y móvil) se hizo aparte y se documenta en el PR: este fichero no lo sustituye.
"""
from __future__ import annotations

import html
import os
import re
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

import zascarr.api.series as api_series
from tests.test_desvinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    SECRETO,
    archivos,
    cliente,
    ent,
    escrituras,
    huella_disco,
    instantanea,
    serie_de_prueba,
    url_bd,
    vinculado,
)
from tests.test_vinculacion_previa_pg import entorno as entorno_base  # noqa: F401
from zascarr.services.tokens_revision import TTL_SEGUNDOS, RetiradaFirmada, crear_token_retirada
from zascarr.services.vinculacion import RETENCION_HORAS
from zascarr.web import retirada_serie as web_retirada

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

HX = {"HX-Request": "true"}
RUTA = "/ui/series/{serie}/retirar"


@pytest.fixture
async def entorno(entorno_base, monkeypatch):
    monkeypatch.setattr(web_retirada, "get_settings",
                        lambda: SimpleNamespace(library_path=entorno_base.lib, secret_key=SECRETO))
    monkeypatch.setattr(api_series, "get_settings",
                        lambda: SimpleNamespace(library_path=entorno_base.lib, secret_key=SECRETO))
    return entorno_base


async def get(ruta: str, **kw) -> httpx.Response:
    async with cliente() as c:
        return await c.get(ruta, **kw)


async def post(ruta: str, datos: dict, **kw) -> httpx.Response:
    async with cliente() as c:
        return await c.post(ruta, data=datos, **kw)


def visible(t: str) -> str:
    """El texto que ve la persona: sin etiquetas ni entidades."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|style).*?</\1>", "", t)))).strip()


def token_de_pagina(t: str) -> str:
    m = re.search(r'name="token" value="([^"]+)"', t)
    assert m, "la página no lleva el formulario de confirmar"
    return html.unescape(m.group(1))


async def con_deseados(entorno, serie, *deseados):
    async with entorno.banco.fabrica() as s:
        for numero, estado in deseados:
            await s.execute(text(
                "INSERT INTO wishlist (id, series_id, numero, status, origen) "
                "VALUES (:i, :s, :n, CAST(:st AS wishlist_status), 'manual')"),
                {"i": uuid4(), "s": serie, "n": numero, "st": estado})
        await s.commit()


async def con_asignacion_viva(entorno, serie, file_id):
    async with entorno.banco.fabrica() as s:
        await s.execute(text(
            "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
            "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
            "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": file_id, "s": serie, "sha": "a" * 64})
        await s.commit()


async def serie_retirada(ent) -> tuple:
    serie, ids = await vinculado(ent, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
    return serie, ids


def token_caducado(serie, *, puede_haberse_aplicado: bool) -> str:
    ahora = time.time()
    antiguedad = RETENCION_HORAS * 3600 + 60 if puede_haberse_aplicado else 60
    return crear_token_retirada(
        RetiradaFirmada(series_id=str(serie), huella="a" * 64, operacion=str(uuid4())),
        SECRETO, ahora=ahora - TTL_SEGUNDOS - antiguedad)


# ── La ficha: entrada a «Retirar» ───────────────────────────────────────────────────────────────

class TestEntrada:

    async def test_la_ficha_ofrece_retirar_y_avisa_de_que_no_toca_el_disco(self, ent):
        serie, _ = await serie_retirada(ent)
        r = await get(f"/ui/series/{serie}")
        t, v = r.text, visible(r.text)
        assert r.status_code == 200
        assert f'href="{RUTA.format(serie=serie)}"' in t
        assert "Retirar de mi biblioteca" in v
        assert "no borra, mueve ni renombra los archivos del disco" in v

    async def test_la_ficha_no_cambia_por_entrar(self, ent):
        serie, _ = await serie_retirada(ent)
        antes, n = await instantanea(ent.banco), len(ent.banco.sentencias)
        await get(f"/ui/series/{serie}")
        assert escrituras(ent.banco, n) == [] and await instantanea(ent.banco) == antes


# ── Vista previa ────────────────────────────────────────────────────────────────────────────────

class TestVistaPrevia:

    async def test_enseña_lo_que_pasara_sin_escribir_nada_ni_tocar_el_disco(self, ent):
        serie, ids = await serie_retirada(ent)
        antes, antes_disco, n = await instantanea(ent.banco), huella_disco(ent.lib), len(ent.banco.sentencias)
        r = await get(RUTA.format(serie=serie))
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert [q for q in ent.banco.sentencias[n:] if not re.match(r"\s*SELECT\b", q, re.I)] == []
        assert await instantanea(ent.banco) == antes and huella_disco(ent.lib) == antes_disco
        t, v = r.text, visible(r.text)
        assert "¿Retirar «Flash" in v and "de tu biblioteca?" in v
        assert "Los archivos del disco no se borrarán, moverán ni renombrarán." in v
        assert "Números 2" in v and "Archivos vinculados 2" in v and "Deseados 0" in v
        assert "Flash 01 (1987).cbz" in v and "Flash 02 (1987).cbz" in v
        assert "vuelven a «Por revisar»" in v and "La serie no reaparece sola" in v
        assert "Hasta que pulses el botón, no cambia nada" in v and "Retirar de mi biblioteca" in v
        assert 'name="token"' in t and f'action="{RUTA.format(serie=serie)}"' in t and 'method="post"' in t

    async def test_cuenta_deseados_y_sagas_y_alias(self, ent):
        serie, ids = await vinculado(ent, "Flash 01 (1987).cbz")
        await con_deseados(ent, serie, (2, "wanted"), (3, "wanted"))
        async with ent.banco.fabrica() as s:
            iid = (await s.execute(text("SELECT issue_id FROM files WHERE id = :f"), {"f": list(ids.values())[0]})).scalar_one()
            arc = uuid4()
            await s.execute(text("INSERT INTO story_arcs (id, title) VALUES (:a, 'Saga')"), {"a": arc})
            await s.execute(text("INSERT INTO story_arc_issues (story_arc_id, issue_id, reading_order) VALUES (:a, :i, 1)"),
                            {"a": arc, "i": iid})
            await s.execute(text("INSERT INTO local_aliases (id, series_id, pattern_norm) VALUES (:i, :s, 'flash')"),
                            {"i": uuid4(), "s": serie})
            await s.commit()
        v = visible((await get(RUTA.format(serie=serie))).text)
        assert "Deseados 2" in v and "Participaciones en sagas 1" in v and "Alias de búsqueda 1" in v
        assert "Se retiran 2 deseos" in v and "sus 1 alias de búsqueda" in v and "sus 1 participaciones en sagas" in v

    async def test_sin_javascript_propio_y_con_el_contrato_htmx_documentado(self, ent):
        serie, _ = await serie_retirada(ent)
        t = (await get(RUTA.format(serie=serie))).text
        panel = t[t.index('id="retirada"'):]
        assert "<script" not in panel and "onclick" not in panel and "onerror" not in panel
        assert f'hx-post="{RUTA.format(serie=serie)}"' in t and 'hx-target="#retirada"' in t and 'hx-swap="outerHTML"' in t

    async def test_peticion_htmx_devuelve_solo_el_panel(self, ent):
        serie, _ = await serie_retirada(ent)
        r = await get(RUTA.format(serie=serie), headers=HX)
        assert r.text.lstrip().startswith('<div id="retirada"') and "<html" not in r.text and "<nav" not in r.text

    async def test_la_pagina_completa_tiene_vuelta_a_la_serie_y_cancelar(self, ent):
        serie, _ = await serie_retirada(ent)
        t = (await get(RUTA.format(serie=serie))).text
        assert "<html" in t and f'href="/ui/series/{serie}"' in t and "Cancelar" in visible(t)

    async def test_serie_inexistente_es_404(self, ent):
        assert (await get(RUTA.format(serie=uuid4()))).status_code == 404

    async def test_sin_clave_del_servidor_es_503_legible(self, ent, monkeypatch):
        serie, _ = await serie_retirada(ent)
        monkeypatch.setattr(web_retirada, "get_settings", lambda: SimpleNamespace(secret_key=""))
        r = await get(RUTA.format(serie=serie))
        # Página HTML de verdad (no el JSON de `detail` colado en el panel) y con el aviso en llano.
        assert r.status_code == 503 and "<html" in r.text and "clave" in visible(r.text)
        assert 'id="retirada"' in r.text
        r = await post(RUTA.format(serie=serie), {"token": "x" * 40})
        assert r.status_code == 503 and "<html" in r.text and 'id="retirada"' in r.text
        assert "clave" in visible(r.text) and 'name="token"' not in r.text
        r = await post(RUTA.format(serie=serie), {"token": "x" * 40}, headers=HX)
        assert r.status_code == 503 and r.text.lstrip().startswith('<div id="retirada"')

    async def test_bloqueo_por_asignacion_viva_no_ofrece_formulario_y_dice_por_que(self, ent):
        serie, ids = await serie_retirada(ent)
        await con_asignacion_viva(ent, serie, list(ids.values())[0])
        r = await get(RUTA.format(serie=serie))
        t, v = r.text, visible(r.text)
        assert r.status_code == 200 and 'name="token"' not in t and "<form" not in t
        assert "Ahora no se puede retirar" in v
        assert "ZascArr está asignando archivos a esta serie ahora mismo" in v
        assert "1 asignación de archivos en curso" in v

    @pytest.mark.parametrize("estado", ["searching", "downloading"])
    async def test_bloqueo_por_deseado_en_curso_no_ofrece_formulario(self, ent, estado):
        serie, _ = await serie_retirada(ent)
        await con_deseados(ent, serie, (2, estado))
        r = await get(RUTA.format(serie=serie))
        t, v = r.text, visible(r.text)
        assert r.status_code == 200 and 'name="token"' not in t and "<form" not in t
        assert "Hay deseos de esta serie con una búsqueda o una descarga en marcha" in v
        assert "el nº 2 se está" in v and ("buscando" in v or "descargando" in v)

    async def test_un_deseado_que_solo_espera_no_bloquea(self, ent):
        serie, _ = await serie_retirada(ent)
        await con_deseados(ent, serie, (2, "wanted"))
        t, v = (await get(RUTA.format(serie=serie))).text, visible((await get(RUTA.format(serie=serie))).text)
        assert 'name="token"' in t and "Ahora no se puede retirar" not in v

    async def test_no_mezcla_codigos_internos_en_la_superficie(self, ent):
        serie, _ = await serie_retirada(ent)
        v = visible((await get(RUTA.format(serie=serie))).text)
        for codigo in ("token_invalido", "asignacion_viva", "deseado_en_curso", "retirada_serie", "huella"):
            assert codigo not in v


# ── Confirmación ────────────────────────────────────────────────────────────────────────────────

class TestConfirmacion:

    async def test_sin_javascript_formulario_normal_retira_y_lleva_a_por_revisar(self, ent):
        serie, ids = await serie_retirada(ent)
        antes_disco = huella_disco(ent.lib)
        pagina = await get(RUTA.format(serie=serie))
        r = await post(RUTA.format(serie=serie), {"token": token_de_pagina(pagina.text)})
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        t, v = r.text, visible(r.text)
        assert "<html" in t and "«Flash" in v and "ya no está en tu biblioteca" in v
        assert "Los archivos siguen en el disco: no se ha borrado, movido ni renombrado nada." in v
        assert "2 números y 2 archivos retirados de ZascArr" in v and "han vuelto a «Por revisar»" in v
        assert 'href="/ui/pendientes"' in t
        assert "cambio_desde" not in t and "token" not in v.lower() and "retirada_serie" not in v
        assert huella_disco(ent.lib) == antes_disco
        assert "Flash 01 (1987).cbz" in (await get("/ui/pendientes")).text
        assert "Flash 02 (1987).cbz" in (await get("/ui/pendientes")).text

    async def test_con_htmx_solo_se_sustituye_el_panel(self, ent):
        serie, _ = await serie_retirada(ent)
        t = token_de_pagina((await get(RUTA.format(serie=serie))).text)
        r = await post(RUTA.format(serie=serie), {"token": t}, headers=HX)
        assert r.status_code == 200 and r.text.lstrip().startswith('<div id="retirada"') and "<html" not in r.text
        assert 'data-resultado="retirada"' in r.text
        assert 'hx-get="/ui/_nav/estado"' in r.text            # el contador de «Por revisar» del menú se vuelve a pedir

    async def test_repetir_dice_que_ya_estaba_retirada_sin_escribir(self, ent):
        serie, _ = await serie_retirada(ent)
        t = token_de_pagina((await get(RUTA.format(serie=serie))).text)
        await post(RUTA.format(serie=serie), {"token": t})
        antes, n = await instantanea(ent.banco), len(ent.banco.sentencias)
        r = await post(RUTA.format(serie=serie), {"token": t})
        assert r.status_code == 200 and "Esta serie ya estaba retirada" in visible(r.text)
        assert 'data-resultado="ya_retirada"' in r.text
        assert escrituras(ent.banco, n) == [] and await instantanea(ent.banco) == antes

    async def test_el_token_de_otra_serie_no_vale_en_esta_url(self, ent):
        serie, _ = await serie_retirada(ent)
        otra = await serie_de_prueba(ent, "Otra", 1990)
        t = token_de_pagina((await get(RUTA.format(serie=otra))).text)
        antes = await instantanea(ent.banco)
        r = await post(RUTA.format(serie=serie), {"token": t})
        assert r.status_code == 200 and "Esa vista previa es de otra serie" in visible(r.text)
        assert await instantanea(ent.banco) == antes

    @pytest.mark.parametrize("token", ["basura", "a.b", "x" * 40])
    async def test_token_invalido_se_dice_en_llano_dentro_de_la_pagina(self, ent, token):
        serie, _ = await serie_retirada(ent)
        antes = await instantanea(ent.banco)
        r = await post(RUTA.format(serie=serie), {"token": token})
        assert r.status_code == 200 and "Esta página no es válida" in visible(r.text)
        assert "No se ha cambiado nada" in visible(r.text) and await instantanea(ent.banco) == antes

    async def test_peticion_sin_token_o_demasiado_larga_es_422(self, ent):
        serie, _ = await serie_retirada(ent)
        assert (await post(RUTA.format(serie=serie), {})).status_code == 422
        assert (await post(RUTA.format(serie=serie), {"token": "x" * 5000})).status_code == 422

    async def test_caducado_sin_poder_saber_si_se_aplico_no_dice_que_no_se_cambio_nada(self, ent):
        serie, _ = await serie_retirada(ent)
        r = await post(RUTA.format(serie=serie), {"token": token_caducado(serie, puede_haberse_aplicado=True)})
        v = visible(r.text)
        assert r.status_code == 200 and 'data-fase="fallo"' in r.text
        assert "Puede que la retirada ya se hubiera aplicado" in v
        assert "No se ha cambiado nada" not in v
        assert "«Por revisar»" in v

    async def test_serie_borrada_y_fallo_repetible_reintenta_en_su_ruta_no_en_biblioteca(self, ent, monkeypatch):
        """El reintento de una serie que ya no existe no puede apuntar a una ruta que no existe."""
        from zascarr.services.vinculacion import ConflictoDeBloqueoError

        serie = await serie_de_prueba(ent, "Borrada", 1991)
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM series WHERE id = :s"), {"s": serie})
            await s.commit()

        async def conflicto(self, token):
            raise ConflictoDeBloqueoError("otra operación")

        monkeypatch.setattr(web_retirada.RetiradaDeSerie, "confirmar", conflicto)
        token = crear_token_retirada(
            RetiradaFirmada(series_id=str(serie), huella="a" * 64, operacion=str(uuid4())), SECRETO)
        r = await post(RUTA.format(serie=serie), {"token": token})
        assert r.status_code == 200 and 'data-fase="fallo"' in r.text
        assert f'action="/ui/series/{serie}/retirar"' in r.text
        assert "/ui/biblioteca/retirar" not in r.text

    async def test_caducado_sin_informe_purgado_dice_que_no_se_cambio_nada(self, ent):
        serie, _ = await serie_retirada(ent)
        r = await post(RUTA.format(serie=serie), {"token": token_caducado(serie, puede_haberse_aplicado=False)})
        v = visible(r.text)
        assert r.status_code == 200 and 'data-fase="fallo"' in r.text
        assert "No se ha cambiado nada" in v
        assert "Puede que la retirada" not in v

    async def test_cambio_desde_la_vista_previa_dice_que_no_se_cambio_nada(self, ent):
        serie, _ = await serie_retirada(ent)
        t = token_de_pagina((await get(RUTA.format(serie=serie))).text)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE series SET title = 'Otro' WHERE id = :s"), {"s": serie})
            await s.commit()
        antes = await instantanea(ent.banco)
        r = await post(RUTA.format(serie=serie), {"token": t})
        v = visible(r.text)
        assert "No se ha retirado nada" in v and "ha cambiado desde que abriste esta página" in v
        assert 'data-resultado="omitido"' in r.text and await instantanea(ent.banco) == antes

    async def test_asignacion_aparecida_despues_dice_que_no_se_cambio_nada(self, ent):
        serie, ids = await serie_retirada(ent)
        t = token_de_pagina((await get(RUTA.format(serie=serie))).text)
        await con_asignacion_viva(ent, serie, list(ids.values())[0])
        antes = await instantanea(ent.banco)
        r = await post(RUTA.format(serie=serie), {"token": t})
        v = visible(r.text)
        assert "No se ha retirado nada" in v and "ha cambiado desde que abriste esta página" in v
        assert "empezó una asignación" in v
        assert 'data-resultado="omitido"' in r.text and await instantanea(ent.banco) == antes

    async def test_resultado_incierto_ofrece_comprobar_y_repetir_lo_resuelve(self, ent, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession
        serie, _ = await serie_retirada(ent)
        t = token_de_pagina((await get(RUTA.format(serie=serie))).text)
        real, pedido = AsyncSession.commit, {"n": 0}

        async def commit_y_cae(self):
            pedido["n"] += 1
            await real(self)
            if pedido["n"] == 1:
                raise ConnectionError("se perdió la respuesta")
        monkeypatch.setattr(AsyncSession, "commit", commit_y_cae)
        r = await post(RUTA.format(serie=serie), {"token": t})
        v = visible(r.text)
        assert r.status_code == 200 and "No sabemos si se ha retirado" in v and "no se ha cambiado nada" not in v.lower()
        assert "Comprobar el resultado" in v and token_de_pagina(r.text) == t          # el mismo token, para repetir
        monkeypatch.setattr(AsyncSession, "commit", real)                               # solo se restaura el commit
        r2 = await post(RUTA.format(serie=serie), {"token": t})
        assert "Esta serie ya estaba retirada" in visible(r2.text) and 'data-resultado="ya_retirada"' in r2.text

    async def test_la_serie_retirada_ya_no_tiene_ficha(self, ent):
        serie, _ = await serie_retirada(ent)
        t = token_de_pagina((await get(RUTA.format(serie=serie))).text)
        await post(RUTA.format(serie=serie), {"token": t})
        assert (await get(f"/ui/series/{serie}")).status_code == 404
