# ruff: noqa: E501, F401, F811
"""Deshacer una vinculación desde la ficha de la serie (BL-R1b, #254) — pruebas sobre Postgres real y la aplicación entera.

Se recorre lo que recorre la persona: la ficha `/ui/series/{id}` (lista de archivos por número), la vista previa, la confirmación
con un `POST` de formulario (sin JavaScript), la misma confirmación como petición htmx (solo el panel) y «Por revisar». El
servicio ya está probado en `test_desvinculacion_pg.py`; aquí solo se prueba que la superficie NO añade reglas y dice las cosas en llano.
El recorrido en un navegador real (con JS y sin él) se hizo aparte y se documenta en el PR: este fichero no lo sustituye.
"""
from __future__ import annotations

import html
import os
import re
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from tests.test_desvinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    F1,
    F2,
    SECRETO,
    SHA,
    api_previa_vinculacion,
    archivos,
    cliente,
    confirmar,
    ent,
    entorno,
    escrituras,
    fila,
    firmar_desv,
    instantanea,
    pendientes,
    serie_de_prueba,
    token_desv,
    url_bd,
    vinculado,
)
from zascarr.api import revision as api_revision
from zascarr.services.archivos_por_numero import archivos_por_numero
from zascarr.web import desvinculacion as web_desv

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

HX = {"HX-Request": "true"}


@pytest.fixture(autouse=True)
def _clave_del_servidor(monkeypatch):
    monkeypatch.setattr(web_desv, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))


async def get(ruta: str, **kw) -> httpx.Response:
    async with cliente() as c:
        return await c.get(ruta, **kw)


async def post(ruta: str, datos: dict, **kw) -> httpx.Response:
    async with cliente() as c:
        return await c.post(ruta, data=datos, **kw)


def visible(t: str) -> str:
    """El texto que ve la persona: sin etiquetas ni entidades."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?s)<(script|style).*?</\1>", "", t)))).strip()


def ruta(serie, fid) -> str:
    return f"/ui/series/{serie}/archivos/{fid}/deshacer"


def token_de_pagina(t: str) -> str:
    m = re.search(r'name="token" value="([^"]+)"', t)
    assert m, "la página no lleva el formulario de confirmar"
    return html.unescape(m.group(1))


# ── La ficha: archivos por número ───────────────────────────────────────────────────────────────

class TestListaDeArchivos:

    async def test_cada_numero_muestra_sus_archivos_y_el_boton_solo_si_se_puede(self, ent):
        serie, ids = await vinculado(ent, F1, F2)
        r = await get(f"/ui/series/{serie}")
        t = r.text
        assert r.status_code == 200 and 'id="archivos-por-numero"' in t
        for nombre, fid in ids.items():
            assert nombre in t and f'href="{ruta(serie, fid)}"' in t
        v = visible(t)
        assert "Archivos por número" in v and "Desvincular" in v
        assert v.index("#1") < v.index("#2") and t.count('class="archivo-fila"') == 2

    async def test_sin_archivos_no_hay_seccion(self, ent):
        serie = await serie_de_prueba(ent)
        r = await get(f"/ui/series/{serie}")
        assert r.status_code == 200 and "archivos-por-numero" not in r.text

    async def test_sin_boton_y_con_la_razon_d9_y_en_curso(self, ent):
        serie, ids = await vinculado(ent, F1, F2)
        async with ent.banco.fabrica() as s:        # F2: vinculado SIN procedencia (como los de «organizar» o el importador)
            await s.execute(text("UPDATE files SET metadata = metadata - 'vinculo' WHERE id = :f"), {"f": ids[F2]})
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids[F1], "s": serie, "sha": SHA})
            await s.commit()
        t = (await get(f"/ui/series/{serie}")).text
        assert 'href="' + ruta(serie, ids[F1]) + '"' not in t and 'href="' + ruta(serie, ids[F2]) + '"' not in t
        assert 'data-razon="en_curso"' in t and 'data-razon="sin_procedencia"' in t
        v = visible(t)
        assert "Ahora mismo ZascArr trabaja con este archivo" in v
        # La razón de «sin procedencia» se dice UNA vez, en el desplegable, no en cada fila.
        assert "¿Por qué algunos archivos no se pueden desvincular?" in v and v.count("Pendientes por carpeta") == 1

    async def test_archivo_no_disponible_se_puede_deshacer_y_se_dice_que_no_esta_verificado(self, ent):
        serie, ids = await vinculado(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET is_missing = true, missing_since = now()"))
            await s.commit()
        t = (await get(f"/ui/series/{serie}")).text
        assert f'href="{ruta(serie, ids[F1])}"' in t and "Quizá no esté en el disco" in visible(t)
        p = await get(ruta(serie, ids[F1]))
        assert "aún no está confirmado" in visible(p.text) and "última revisión de la biblioteca" in visible(p.text) and 'name="token"' in p.text

    async def test_la_lista_no_hace_una_consulta_por_archivo(self, ent):
        pocos, _ = await vinculado(ent, *(f"Flash {i:02d} (1987).cbz" for i in range(1, 3)))
        await get(f"/ui/series/{pocos}")                         # calienta el pool
        n = len(ent.banco.sentencias)
        await get(f"/ui/series/{pocos}")
        consultas_pocos = len(ent.banco.sentencias) - n
        muchos = await serie_de_prueba(ent, "Otra", 1990)
        nombres = [f"Otra {i:02d} (1990).cbz" for i in range(1, 31)]
        ids = await archivos(ent, *nombres, carpeta="Comics/Otra (1990)")
        r = await api_previa_vinculacion(muchos, ids.values(), clave="Comics/Otra (1990)")
        assert (await confirmar(r.json()["token"])).status_code == 200
        n = len(ent.banco.sentencias)
        t = (await get(f"/ui/series/{muchos}")).text
        consultas_muchos = len(ent.banco.sentencias) - n
        assert t.count('class="archivo-fila"') == 30
        assert consultas_muchos == consultas_pocos                # 30 archivos, las mismas consultas que 2

    async def test_la_lista_no_escribe(self, ent):
        serie, _ = await vinculado(ent, F1)
        await get(f"/ui/series/{serie}")
        antes, n = await instantanea(ent.banco), len(ent.banco.sentencias)
        await get(f"/ui/series/{serie}")
        assert escrituras(ent.banco, n) == [] and await instantanea(ent.banco) == antes

    async def test_el_orden_es_el_de_lectura_y_no_mezcla_series(self, ent):
        serie = await serie_de_prueba(ent)
        ids = await archivos(ent, "Flash 10 (1987).cbz", "Flash 02 (1987).cbz", "Flash 01 (1987).cbz")
        r = await api_previa_vinculacion(serie, ids.values())
        await confirmar(r.json()["token"])
        otra, _ = await vinculado(ent, "Otra 05 (1990).cbz", serie=await serie_de_prueba(ent, "Otra", 1990))
        async with ent.banco.fabrica() as s:
            res = await archivos_por_numero(s, serie)
        assert [n.numero for n in res] == ["1", "2", "10"] and all(len(n.archivos) == 1 for n in res)
        assert "Otra 05" not in "".join(a.nombre for n in res for a in n.archivos)

    async def test_el_boton_de_la_lista_coincide_con_lo_que_dice_la_vista_previa_de_la_api(self, ent):
        # La lista aplica la MISMA regla que el servicio: se compara archivo a archivo con la API de BL-R1a.
        serie, ids = await vinculado(ent, F1, F2, "Flash 03 (1987).cbz")
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = metadata - 'vinculo' WHERE id = :f"), {"f": ids[F2]})
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('confirmada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids["Flash 03 (1987).cbz"], "s": serie, "sha": SHA})
            await s.commit()
        async with ent.banco.fabrica() as s:
            lista = {a.id: a.bloqueo for n in await archivos_por_numero(s, serie) for a in n.archivos}
        async with cliente() as c:
            for fid in ids.values():
                p = (await c.post("/api/revision/desvinculacion/previsualizar", json={"file_id": str(fid)})).json()
                assert lista[str(fid)] == (p["bloqueo"]["codigo"] if p["bloqueo"] else None)


# ── Vista previa ────────────────────────────────────────────────────────────────────────────────

class TestVistaPrevia:

    async def test_enseña_lo_que_pasara_sin_escribir_nada(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        await get(ruta(serie, fid))
        antes, n = await instantanea(ent.banco), len(ent.banco.sentencias)
        r = await get(ruta(serie, fid))
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert [q for q in ent.banco.sentencias[n:] if not re.match(r"\s*SELECT\b", q, re.I)] == []
        assert await instantanea(ent.banco) == antes
        t, v = r.text, visible(r.text)
        assert F1 in v and "Flash" in v and "#1" in v
        assert "¿Desvincular este archivo?" in v and "Qué pasará" in v and "Vuelve a «Por revisar»" in v
        assert "no se toca" in v and "no se mueve, no se renombra ni se borra" in v
        assert "sin archivo" in v and "entre los números que te faltan" in v                    # el número se queda sin archivo (D1: se conserva)
        assert "Volver a vincularlo es un paso aparte" in v and "si lo cancelas o falla, el archivo se queda allí" in v    # criterio 2 de #254
        assert "Hasta que pulses el botón, no cambia nada" in v and "Desvincular el archivo" in v
        assert 'class="aviso amber"' not in t                                                   # sin aviso de peligro que no existe
        assert 'name="token"' in t and 'action="/ui/series/' in t and 'method="post"' in t

    async def test_la_vineta_del_numero_depende_de_si_se_queda_sin_archivos(self, ent):
        # Revisión UX: «se queda sin archivo» solo cuando de verdad no le queda ninguno; si no, «con N archivos más».
        serie, ids = await vinculado(ent, F1)
        solo = visible((await get(ruta(serie, ids[F1]), headers=HX)).text)
        assert "pero sin archivo: aparecerá entre los números que te faltan" in solo and "archivo más" not in solo
        async with ent.banco.fabrica() as s:
            iid = (await s.execute(text("SELECT issue_id FROM files WHERE id = :f"), {"f": ids[F1]})).scalar_one()
            await s.execute(text("INSERT INTO files (id, issue_id, file_path, file_name, file_format) VALUES (:i, :n, '/otro.cbz', 'otro.cbz', 'cbz')"),
                            {"i": uuid4(), "n": iid})
            await s.commit()
        con_otro = visible((await get(ruta(serie, ids[F1]), headers=HX)).text)
        assert "con 1 archivo más, que no cambian" in con_otro and "sin archivo" not in con_otro and "números que te faltan" not in con_otro

    async def test_sin_javascript_propio_y_con_el_contrato_htmx_documentado(self, ent):
        serie, ids = await vinculado(ent, F1)
        t = (await get(ruta(serie, ids[F1]))).text
        panel = t[t.index('id="desvinculacion"'):]
        assert "<script" not in panel and "onclick" not in panel and "onerror" not in panel
        assert f'hx-post="{ruta(serie, ids[F1])}"' in t and 'hx-target="#desvinculacion"' in t and 'hx-swap="outerHTML"' in t

    async def test_peticion_htmx_devuelve_solo_el_panel(self, ent):
        serie, ids = await vinculado(ent, F1)
        r = await get(ruta(serie, ids[F1]), headers=HX)
        assert r.text.lstrip().startswith("<div id=\"desvinculacion\"") and "<html" not in r.text and "<nav" not in r.text

    async def test_la_pagina_completa_tiene_menu_y_vuelta_a_la_serie(self, ent):
        serie, ids = await vinculado(ent, F1)
        t = (await get(ruta(serie, ids[F1]))).text
        assert "<html" in t and f'href="/ui/series/{serie}"' in t and "Cancelar" in visible(t)

    async def test_archivo_o_serie_inexistente_es_404(self, ent):
        serie, ids = await vinculado(ent, F1)
        assert (await get(ruta(serie, uuid4()))).status_code == 404
        assert (await get(ruta(uuid4(), ids[F1]))).status_code == 404

    async def test_archivo_de_otra_serie_es_404(self, ent):
        serie, ids = await vinculado(ent, F1)
        otra = await serie_de_prueba(ent, "Otra", 1990)
        assert (await get(ruta(otra, ids[F1]))).status_code == 404

    async def test_bloqueado_dice_la_razon_y_no_ofrece_el_formulario(self, ent):
        serie, ids = await vinculado(ent, F1)
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET metadata = metadata - 'vinculo'"))
            await s.commit()
        r = await get(ruta(serie, ids[F1]))
        assert r.status_code == 200 and 'name="token"' not in r.text and "<form" not in r.text
        assert "Pendientes por carpeta" in visible(r.text)

    async def test_ya_no_vinculado_dice_que_no_hay_nada_que_deshacer(self, ent):
        serie, ids = await vinculado(ent, F1)
        t = await token_desv(ids[F1])
        await post(ruta(serie, ids[F1]), {"token": t})
        r = await get(ruta(serie, ids[F1]))
        assert r.status_code == 200 and "no hay nada que deshacer" in visible(r.text) and "<form" not in r.text

    async def test_sin_clave_del_servidor_es_503_legible(self, ent, monkeypatch):
        serie, ids = await vinculado(ent, F1)
        monkeypatch.setattr(web_desv, "get_settings", lambda: SimpleNamespace(secret_key=""))
        r = await get(ruta(serie, ids[F1]))
        assert r.status_code == 503 and "clave" in visible(r.text)


# ── Confirmación ────────────────────────────────────────────────────────────────────────────────

class TestConfirmacion:

    async def test_sin_javascript_formulario_normal_deshace_y_lleva_a_por_revisar(self, ent):
        serie, ids = await vinculado(ent, F1)
        fid = ids[F1]
        pagina = await get(ruta(serie, fid))
        r = await post(ruta(serie, fid), {"token": token_de_pagina(pagina.text)})          # lo que envía el navegador sin JS
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        t, v = r.text, visible(r.text)
        assert "<html" in t and "Archivo desvinculado de Flash #1" in v and "ha vuelto a «Por revisar»" in v
        assert "No se ha movido ni borrado nada" in v and "Para vincularlo de nuevo, ve a «Por revisar»" in v
        assert 'href="/ui/pendientes"' in t and f'href="/ui/series/{serie}"' in t
        f = await fila(ent.banco, fid)
        assert f["issue_id"] is None and "vinculo" not in f["metadata"] and len(f["metadata"]["vinculo_historial"]) == 1
        assert await pendientes(ent) == 1
        assert "cambio_desde" not in t and "token_invalido" not in t and "ya_deshecho" not in t        # sin códigos en superficie
        assert "token" not in v.lower()

    async def test_el_archivo_reaparece_en_por_revisar(self, ent):
        serie, ids = await vinculado(ent, F1)
        assert F1 not in (await get("/ui/pendientes")).text
        await post(ruta(serie, ids[F1]), {"token": await token_desv(ids[F1])})
        assert F1 in (await get("/ui/pendientes")).text

    async def test_con_htmx_solo_se_sustituye_el_panel(self, ent):
        serie, ids = await vinculado(ent, F1)
        r = await post(ruta(serie, ids[F1]), {"token": await token_desv(ids[F1])}, headers=HX)
        assert r.status_code == 200 and r.text.lstrip().startswith('<div id="desvinculacion"') and "<html" not in r.text
        assert 'data-resultado="deshecho"' in r.text
        assert 'hx-get="/ui/_nav/estado"' in r.text            # el contador de «Por revisar» del menú se vuelve a pedir

    async def test_repetir_dice_que_ya_estaba_deshecho_sin_escribir(self, ent):
        serie, ids = await vinculado(ent, F1)
        t = await token_desv(ids[F1])
        await post(ruta(serie, ids[F1]), {"token": t})
        despues, n = await fila(ent.banco, ids[F1]), len(ent.banco.sentencias)
        r = await post(ruta(serie, ids[F1]), {"token": t})
        assert "Este archivo ya estaba desvinculado" in visible(r.text) and 'data-resultado="ya_deshecho"' in r.text
        assert escrituras(ent.banco, n) == [] and await fila(ent.banco, ids[F1]) == despues

    async def test_el_token_de_otro_archivo_no_vale_en_esta_url(self, ent):
        serie, ids = await vinculado(ent, F1, F2)
        t2 = await token_desv(ids[F2])
        antes = await instantanea(ent.banco)
        r = await post(ruta(serie, ids[F1]), {"token": t2})
        assert r.status_code == 200 and "Esa vista previa es de otro archivo" in visible(r.text)
        assert await instantanea(ent.banco) == antes

    async def test_el_token_de_otra_serie_no_vale_en_esta_url(self, ent):
        serie, ids = await vinculado(ent, F1)
        otra = await serie_de_prueba(ent, "Otra", 1990)
        t = await token_desv(ids[F1])
        r = await post(ruta(otra, ids[F1]), {"token": t})
        assert "Esa vista previa es de otro archivo" in visible(r.text)
        assert (await fila(ent.banco, ids[F1]))["issue_id"] is not None

    @pytest.mark.parametrize("token", ["basura", "a.b", "x" * 40])
    async def test_token_invalido_se_dice_en_llano_dentro_de_la_pagina(self, ent, token):
        serie, ids = await vinculado(ent, F1)
        antes = await instantanea(ent.banco)
        r = await post(ruta(serie, ids[F1]), {"token": token})
        assert r.status_code == 200 and "Esta página no es válida" in visible(r.text)
        assert "Abrir de nuevo" in visible(r.text) and await instantanea(ent.banco) == antes

    async def test_peticion_sin_token_o_demasiado_larga_es_422(self, ent):
        serie, ids = await vinculado(ent, F1)
        assert (await post(ruta(serie, ids[F1]), {})).status_code == 422
        assert (await post(ruta(serie, ids[F1]), {"token": "x" * 5000})).status_code == 422

    async def test_caducado_se_dice_y_no_cambia_nada(self, ent):
        import time
        serie, ids = await vinculado(ent, F1)
        f = await fila(ent.banco, ids[F1])
        v = f["metadata"]["vinculo"]
        viejo = firmar_desv(f, file_id=ids[F1], issue_id=f["issue_id"], series_id=v["serie_id"], vinculo_operacion=v["operacion_id"],
                            ahora=time.time() - 3600)
        antes = await instantanea(ent.banco)
        r = await post(ruta(serie, ids[F1]), {"token": viejo})
        assert "Esta página ha caducado" in visible(r.text) and "No se ha cambiado nada" in visible(r.text)
        assert await instantanea(ent.banco) == antes

    async def test_cambio_desde_la_vista_previa_dice_que_no_se_cambio_nada(self, ent):
        serie, ids = await vinculado(ent, F1)
        t = await token_desv(ids[F1])
        async with ent.banco.fabrica() as s:
            await s.execute(text("UPDATE files SET file_size_bytes = coalesce(file_size_bytes, 0) + 1"))
            await s.commit()
        antes = await instantanea(ent.banco)
        r = await post(ruta(serie, ids[F1]), {"token": t})
        v = visible(r.text)
        assert "No se ha desvinculado nada" in v and "ha cambiado desde que abriste esta página" in v and "No se ha cambiado nada" in v
        assert 'data-resultado="omitido"' in r.text and await instantanea(ent.banco) == antes

    async def test_en_curso_aparecido_despues_dice_que_espere(self, ent):
        serie, ids = await vinculado(ent, F1)
        t = await token_desv(ids[F1])
        async with ent.banco.fabrica() as s:
            await s.execute(text(
                "INSERT INTO asignacion_operaciones (file_id, series_id, estado, origen, destino, temporal, size_bytes, "
                "mtime_ns, sha256, issue_number, formato) VALUES (:f, :s, CAST('preparada' AS asignacion_estado), '/o', '/d', "
                "'/t', 1, 1, :sha, '1', CAST('single_issue' AS issue_format))"), {"f": ids[F1], "s": serie, "sha": SHA})
            await s.commit()
        r = await post(ruta(serie, ids[F1]), {"token": t})
        assert "Ahora mismo ZascArr está trabajando con este archivo" in visible(r.text) and "prueba de nuevo" in visible(r.text)

    async def test_resultado_incierto_ofrece_comprobar_y_repetir_lo_resuelve(self, ent, monkeypatch):
        from sqlalchemy.ext.asyncio import AsyncSession
        serie, ids = await vinculado(ent, F1)
        t = await token_desv(ids[F1])
        real, pedido = AsyncSession.commit, {"n": 0}

        async def commit_y_cae(self):
            pedido["n"] += 1
            await real(self)
            if pedido["n"] == 1:
                raise ConnectionError("se perdió la respuesta")
        monkeypatch.setattr(AsyncSession, "commit", commit_y_cae)
        r = await post(ruta(serie, ids[F1]), {"token": t})
        v = visible(r.text)
        assert r.status_code == 200 and "No sabemos si se ha desvinculado" in v and "no se ha cambiado nada" not in v.lower()
        assert "Comprobar el resultado" in v and token_de_pagina(r.text) == t          # el mismo token, para repetir
        monkeypatch.undo()
        monkeypatch.setattr(web_desv, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
        monkeypatch.setattr(api_revision, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))
        r2 = await post(ruta(serie, ids[F1]), {"token": t})
        assert "Este archivo ya estaba desvinculado" in visible(r2.text)

    async def test_fallo_inesperado_no_filtra_detalles_ni_cambia_nada(self, ent, monkeypatch):
        from zascarr.services.desvinculacion import DesvinculacionDeArchivo
        serie, ids = await vinculado(ent, F1)
        t = await token_desv(ids[F1])
        antes = await instantanea(ent.banco)

        async def falla():
            raise RuntimeError("detalle interno con /ruta/secreta")
        monkeypatch.setattr(DesvinculacionDeArchivo, "_gancho_con_filas_bloqueadas", staticmethod(falla))
        r = await post(ruta(serie, ids[F1]), {"token": t})
        assert r.status_code == 200 and "No se ha podido completar" in visible(r.text) and "No se ha cambiado nada" in visible(r.text)
        assert "detalle interno" not in r.text and "/ruta/secreta" not in r.text and "RuntimeError" not in r.text
        assert await instantanea(ent.banco) == antes

    async def test_el_fichero_nunca_se_toca(self, ent):
        from tests.test_vinculacion_previa_pg import huella_disco
        serie, ids = await vinculado(ent, F1)
        disco = huella_disco(ent.lib)
        await post(ruta(serie, ids[F1]), {"token": await token_desv(ids[F1])})
        assert huella_disco(ent.lib) == disco

    async def test_cadena_de_pantallas_deshacer_y_volver_a_ver_el_hueco_en_la_serie(self, ent):
        serie, ids = await vinculado(ent, F1)
        await post(ruta(serie, ids[F1]), {"token": await token_desv(ids[F1])})
        t = (await get(f"/ui/series/{serie}")).text
        assert "archivos-por-numero" not in t                 # ya no tiene archivos: el número es un hueco, no una fila
        assert "En tu biblioteca" not in visible(t)           # y la serie ya no lo cuenta como poseído

# ── Lenguaje llano (revisión UX del squad, CLAUDE.md §6 «Presupuesto de texto») ─────────────────

class TestLenguajeLlano:

    async def test_la_vista_previa_cabe_en_el_presupuesto_de_texto_antes_del_boton(self, ent):
        serie, ids = await vinculado(ent, F1)
        v = visible((await get(ruta(serie, ids[F1]), headers=HX)).text)           # solo el panel, sin el menú
        antes_del_boton = v[:v.index("Desvincular el archivo")]
        assert len(antes_del_boton.split()) <= 100, len(antes_del_boton.split())          # tenía ~150; el objetivo del squad es ~60
        assert "Pendientes por carpeta" not in v and "Vincular en su sitio" not in v         # nombres internos fuera de la vista previa

    async def test_ninguna_pantalla_dice_token_ni_enseña_un_codigo(self, ent, monkeypatch):
        import time
        serie, ids = await vinculado(ent, F1, F2)
        textos = [(await get(f"/ui/series/{serie}")).text, (await get(ruta(serie, ids[F1]))).text,
                  (await post(ruta(serie, ids[F1]), {"token": "basura"})).text]
        f = await fila(ent.banco, ids[F2])
        v = f["metadata"]["vinculo"]
        viejo = firmar_desv(f, file_id=ids[F2], issue_id=f["issue_id"], series_id=v["serie_id"], vinculo_operacion=v["operacion_id"],
                            ahora=time.time() - 3600)
        textos.append((await post(ruta(serie, ids[F2]), {"token": viejo})).text)
        for t in textos:
            vis = visible(t).lower()
            assert "operacion_id" not in vis and "cambio_desde" not in vis and "token_" not in vis
            assert "token" not in vis

    async def test_los_enlaces_de_desvincular_se_distinguen_para_un_lector_de_pantalla(self, ent):
        serie, ids = await vinculado(ent, F1, F2)
        t = (await get(f"/ui/series/{serie}")).text
        for nombre in (F1, F2):
            assert re.search(r">Desvincular<span class=\"sr\"> " + re.escape(nombre) + "</span>", t)

    async def test_el_resultado_tiene_un_solo_destino_para_asignarlo_de_nuevo(self, ent):
        serie, ids = await vinculado(ent, F1)
        t = (await post(ruta(serie, ids[F1]), {"token": await token_desv(ids[F1])}, headers=HX)).text
        assert t.count('href="/ui/pendientes"') == 1 and "/ui/pendientes/carpetas" not in t
