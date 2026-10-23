# ruff: noqa: E501, F401, F811
"""U19 (#206, BL-U19) — continuidad del recorrido carpeta → serie → revisión → vinculación (T1–T7, T12, T13 de la ficha §8).

Complementa `test_u19_recorrido_pg.py` (volver y leer el comprobante). Postgres real, fuentes SIMULADAS (y vigiladas: ninguna de estas
pruebas puede consultar una). Se saltan sin `TEST_DATABASE_URL`.

| # | Criterio de #206 | Clase |
|---|---|---|
| T1, T2 | 1. Selección local directa, sin alta ni preselección | `TestSeleccionLocal` |
| T3–T5 | 2. Continuidad desde una candidata; reutilizar no duplica | `TestContinuidadDesdeCandidata` |
| T6 | 3. Progreso accesible | `TestProgreso` |
| T7 | 4. Navegar no confirma ningún efecto | `TestNavegarNoEscribe` |
| T11 | 8. Fallos y caducidad: el resultado real y la acción permitida | `TestFallos` |
| T12, T13 | límites | `TestLimites` |
"""
from __future__ import annotations

import html
import os
import re
from types import SimpleNamespace
from urllib.parse import quote, urlencode
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from tests.test_asistente_confirmar_pg import confirmar, enviar, listo, numero_de  # noqa: F401
from tests.test_asistente_vinculacion_pg import (  # noqa: F401
    CLAVE,
    SECRETO,
    abrir,
    archivos,
    cliente,
    entorno,
    serie_de_prueba,
    url_bd,
)
from tests.test_u19_recorrido_pg import (  # noqa: F401  (fixtures, vigilancia de fuentes y ayudas)
    DOS,
    TRES,
    UNO,
    A,
    V,
    _secreto_y_sin_red,
    _vigilar_las_fuentes,
    candidata,
    crear_alta,
    enlace,
    get,
    ref_de,
    seguir,
    series,
    sin_fuentes,
    token_de_crear,
    visible,
)
from tests.test_vinculacion_pg import ent  # noqa: F401
from tests.test_vinculacion_previa_pg import escrituras, huella_disco, instantanea
from zascarr.models import ComicTradition, Series
from zascarr.services.tokens_revision import (
    MAX_TOKEN_CANDIDATA_SIN_GRUPO,
    candidata_firmable,
    crear_token_candidata,
)
from zascarr.web import asistente_carpetas, discovery

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

#: Un UUID local que contiene `4050` (el id externo de Comic Vine que usan estas pruebas).
SERIE_CON_4050_EN_EL_ID = UUID("0b4050aa-0000-4000-8000-000000000001")


def sin_el_id_local(enlace: str, sid) -> str:
    """El enlace SIN el UUID de la serie local. El UUID es aleatorio y a veces contiene «4050» por azar; lo que se
    comprueba es que no viaje el identificador EXTERNO, así que el id local se quita antes de buscarlo."""
    return enlace.replace(str(sid), "")


async def elegir(**datos) -> httpx.Response:
    async with cliente() as c:
        return await c.post(f"{A}/elegir", data={"clave": CLAVE, **datos}, headers={"HX-Request": "true"})


async def post(ruta: str, datos: dict) -> httpx.Response:
    async with cliente() as c:
        return await c.post(ruta, data=datos, headers={"HX-Request": "true"})


def campos_de(t: str, que: str) -> dict[str, str]:
    """Los campos ocultos del PRIMER formulario que apunta a `que` (lo que enviaría el navegador)."""
    m = re.search(rf'<form[^>]*hx-post="{re.escape(que)}"[^>]*>(.*?)</form>', t, re.S)
    assert m, f"no hay formulario hacia {que}"
    return {html.unescape(n): html.unescape(v) for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', m.group(1))}


def formulario_con(t: str, que: str, **contiene) -> dict[str, str]:
    for m in re.finditer(rf'<form[^>]*hx-post="{re.escape(que)}"[^>]*>(.*?)</form>', t, re.S):
        c = {html.unescape(n): html.unescape(v) for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', m.group(1))}
        if all(c.get(k) == v for k, v in contiene.items()):
            return c
    raise AssertionError(f"no hay formulario hacia {que} con {contiene}")


# ═══ T1, T2 · criterio 1: selección local directa ═══════════════════════════════════════════════

class TestSeleccionLocal:

    async def test_t1_una_serie_local_sin_identificadores_se_encuentra_y_se_elige_sin_alta(self, ent):
        await archivos(ent, UNO, DOS)
        sid = await serie_de_prueba(ent)                                          # sin comic_vine_id / anilist_id / slug
        assert "¿Ya la tienes en tu biblioteca?" in visible((await get(A, clave=CLAVE)).text)
        antes, disco = await instantanea(ent.banco), huella_disco(ent.lib)
        r = await get(f"{A}/locales", clave=CLAVE, q="flash")
        assert r.status_code == 200
        enlace = re.search(r'href="([^"]*vinculacion\?clave=[^"]+series_id=([0-9a-f-]{36}))"', r.text)
        assert enlace and enlace.group(2) == str(sid)
        v = await get(V, clave=CLAVE, series_id=str(sid))                         # elegirla es abrir la revisión
        assert v.status_code == 200 and "Vas a preparar los archivos" in visible(v.text)
        assert await instantanea(ent.banco) == antes and huella_disco(ent.lib) == disco
        assert (await numero_de("series", ent.banco)) == 1 and (await numero_de("alta_operaciones", ent.banco)) == 0
        sin_fuentes()

    async def test_t2_candidatas_ambiguas_muestran_datos_y_ninguna_esta_elegida(self, ent):
        await archivos(ent, UNO)
        a = await serie_de_prueba(ent, titulo="Flash", anio=1987)
        b = await serie_de_prueba(ent, titulo="Flash", anio=1959)
        r = await get(f"{A}/locales", clave=CLAVE, q="Flash")
        v = visible(r.text)
        assert "(1987)" in v and "(1959)" in v and "Grapa americana" in v
        assert str(a) in r.text and str(b) in r.text
        assert not re.search(r"\b(selected|checked)\b", r.text)                  # nada preseleccionado
        assert r.text.count("Preparar los archivos de esta carpeta para esa serie") == 2

    async def test_t2_con_un_solo_resultado_tampoco_hay_seleccion_automatica(self, ent):
        await archivos(ent, UNO)
        await serie_de_prueba(ent)
        r = await get(f"{A}/locales", clave=CLAVE, q="Flash")
        assert "Ninguna está elegida" in visible(r.text) and not re.search(r"\b(selected|checked)\b", r.text)
        assert "<form" not in r.text                                              # no hay nada que envíe una elección sola

    async def test_t2_sin_resultados_o_sin_texto_se_dice_y_no_es_un_error(self, ent):
        await archivos(ent, UNO)
        assert "No hay ninguna serie tuya" in visible((await get(f"{A}/locales", clave=CLAVE, q="Zzzz")).text)
        assert "Escribe parte del título" in visible((await get(f"{A}/locales", clave=CLAVE, q="  ")).text)

    async def test_t2b_el_selector_local_no_hace_una_consulta_por_fila(self, ent):
        await archivos(ent, UNO)
        await serie_de_prueba(ent, titulo="Flash A", anio=1980)
        d1 = len(ent.banco.sentencias)
        await get(f"{A}/locales", clave=CLAVE, q="Flash")
        con_una = len(ent.banco.sentencias) - d1
        for i in range(19):
            await serie_de_prueba(ent, titulo=f"Flash {i}", anio=1990 + i % 5)
        d2 = len(ent.banco.sentencias)
        r = await get(f"{A}/locales", clave=CLAVE, q="Flash")
        con_veinte = len(ent.banco.sentencias) - d2
        assert r.text.count("Preparar los archivos") == 20
        assert con_veinte == con_una, "el número de sentencias no puede crecer con las filas"


# ═══ T3–T5 · criterio 2: continuidad desde una candidata ═══════════════════════════════════════

class TestContinuidadDesdeCandidata:

    async def test_t3_elegir_una_candidata_de_la_carpeta_lleva_a_la_vista_previa_del_alta(self, ent):
        """H1: hoy una candidata con su carpeta no podía pasar por la vista previa; ahora `/elegir` la enseña."""
        await archivos(ent, UNO, DOS)
        r = await elegir(candidata=candidata(), tradition="american", consulta="Flash")
        v = visible(r.text)
        assert r.status_code == 200 and "Elección anotada" in v and "Crear serie vacía" in v
        assert "Todavía no se ha creado ninguna serie" in v and "no vincula ningún archivo" in v
        assert "El paso siguiente" not in v and "todavía no está disponible" not in v        # el callejón ya no existe
        assert "enlace a esta vista previa" in v and "Elegir otra" in v
        assert re.search(r'href="[^"]*asistente\?clave=[^"]+consulta=Flash"', r.text)         # volver conserva la búsqueda

    async def test_t4_elegir_no_crea_nada_y_confirmar_el_alta_no_vincula_ningun_archivo(self, ent):
        await archivos(ent, UNO, DOS)
        antes, disco = await instantanea(ent.banco), huella_disco(ent.lib)
        desde = len(ent.banco.sentencias)
        await elegir(candidata=candidata(), tradition="american")
        assert await instantanea(ent.banco) == antes and escrituras(ent.banco, desde) == []
        c = await crear_alta(ent)                                                       # el botón de la vista previa
        assert c.status_code == 200 and "creada" in visible(c.text)
        assert (await numero_de("series", ent.banco)) == 1
        async with ent.banco.fabrica() as s:
            vinculados = (await s.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one()
        assert vinculados == 0 and (await numero_de("vinculacion_operaciones", ent.banco)) == 0
        assert huella_disco(ent.lib) == disco                                           # ni mueve ni renombra

    async def test_t5_una_candidata_ya_existente_se_reutiliza_y_no_se_duplica(self, ent):
        await archivos(ent, UNO)
        # El id local lo fijamos con un `4050` DENTRO (como el UUID aleatorio que, por azar, rompió la CI de `main` el
        # 2026-10-23): la comprobación de abajo no puede confundir un trozo del id local con el identificador externo.
        sid = SERIE_CON_4050_EN_EL_ID
        async with ent.banco.fabrica() as s:
            s.add(Series(id=sid, title="Flash", start_year=1987, tradition=ComicTradition.AMERICAN, comic_vine_id=4050))
            await s.commit()
        r = await elegir(candidata=candidata(), tradition="american")
        v = visible(r.text)
        assert "Ya existe una serie con ese identificador" in v and "Usar esta serie" in v and "Crear serie vacía" not in v
        p = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american")
        c = await post("/ui/descubrir/crear", {"token": token_de_crear(p.text)})
        assert "ya estaba en tu biblioteca" in visible(c.text)
        enlace = re.search(r'href="[^"]*vinculacion\?clave=[^"]+series_id=([^"&]+)"', c.text)
        assert enlace and enlace.group(1) == str(sid)                                   # a la revisión va el id LOCAL
        assert "4050" not in sin_el_id_local(enlace.group(0), sid)                      # nunca el identificador externo
        assert (await numero_de("series", ent.banco)) == 1

    async def test_t5_elegir_una_parecida_del_asistente_conserva_la_carpeta_y_no_duplica(self, ent):
        """«Es esta» y «Es distinta» de la vista previa, con una candidata del asistente: viajan con su carpeta."""
        await archivos(ent, UNO, DOS)
        sid = await serie_de_prueba(ent)                              # mismo título y tradición, sin identificadores
        r = await elegir(candidata=candidata(), tradition="american")
        assert "Es esta" in visible(r.text) and "Es distinta: crear otra" in visible(r.text)
        es_esta = formulario_con(r.text, "/ui/descubrir/revisar", decision="reutilizar", serie_id=str(sid))
        assert es_esta["clave"] == CLAVE and es_esta["candidata"]                       # la carpeta viaja con la candidata
        p = await post("/ui/descubrir/revisar", es_esta)
        assert "Se usará la serie existente que elegiste" in visible(p.text)
        c = await post("/ui/descubrir/crear", {"token": token_de_crear(p.text)})
        assert "ya estaba en tu biblioteca" in visible(c.text) and (await numero_de("series", ent.banco)) == 1
        assert f"series_id={sid}" in c.text                                             # sigue a la revisión de ESA serie

    async def test_t5_la_revision_recibe_el_series_id_local_tras_crear(self, ent):
        await archivos(ent, UNO, DOS)
        c = await crear_alta(ent)
        sid = (await series(ent))[0][0]
        enlace = re.search(r'href="([^"]*vinculacion\?clave=[^"]+series_id=([^"&]+))"', c.text)
        assert enlace and enlace.group(2) == str(sid) and "4050" not in sin_el_id_local(enlace.group(1), sid)
        async with cliente() as k:
            assert (await k.get(html.unescape(enlace.group(1)))).status_code == 200


# ═══ T6 · criterio 3: progreso accesible ════════════════════════════════════════════════════════

def pasos(t: str) -> list[tuple[str, str, bool]]:
    """(nombre, estado, aria-current) de cada paso del indicador."""
    m = re.search(r'<nav class="pasos-asistente".*?</nav>', t, re.S)
    assert m, "la pantalla no tiene el indicador de pasos"
    return [(visible(re.sub(r'<span class="(sr|num)"[^>]*>.*?</span>', "", cuerpo)).strip(), cls, 'aria-current="step"' in attrs)
            for cls, attrs, cuerpo in re.findall(r'<li class="([^"]+)"([^>]*)>(.*?)</li>', m.group(0), re.S)]


class TestProgreso:

    async def _pantallas(self, ent):
        p = await listo(ent, UNO, DOS)                                  # siembra los archivos y prepara una revisión
        sid = p.serie
        r = await confirmar(p)
        return {
            "A": (await get(A, clave=CLAVE)).text,
            "alta": (await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american")).text,
            "alta/resultado": (await get(f"{A}/alta/resultado", clave=CLAVE, series_id=str(sid))).text,
            "V": (await get(V, clave=CLAVE, series_id=str(sid))).text,
            "X": r.t,
            "lectura": (await get(f"{V}/resultado", ref=ref_de(r.t))).text,
        }, {"A": 1, "alta": 1, "alta/resultado": 1, "V": 2, "X": 3, "lectura": 3}

    async def test_t6_cada_pantalla_marca_su_paso_con_aria_current_step(self, ent):
        pantallas, esperado = await self._pantallas(ent)
        for nombre, actual in esperado.items():
            ps = pasos(pantallas[nombre])
            assert [n for n, _, _ in ps] == ["Elegir la serie", "Revisar los archivos", "Vincular"], nombre
            assert [c for _, _, c in ps].count(True) == 1 and ps[actual - 1][2], nombre      # uno, y el correcto
            assert pantallas[nombre].count('aria-current="step"') == 1, nombre

    async def test_t6_al_confirmar_la_cabecera_y_los_pasos_pasan_a_vincular(self, ent):
        """Confirmar solo sustituye `#revision`: la cabecera (título, frase y pasos) viaja como respuesta fuera de banda."""
        p = await listo(ent, UNO, DOS)
        r = await confirmar(p)
        assert re.search(r'<div id="cabecera-vinculacion" hx-swap-oob="true">', r.t)
        assert "Resultado de la vinculación" in r.t and "En este paso no se vincula ni se crea nada" not in r.t
        ps = pasos(r.t)
        assert [c for _, c, _ in ps] == ["hecho", "hecho", "actual"] and ps[2][2]
        assert r.t.count('aria-current="step"') == 1

    async def test_t6_sin_htmx_el_resultado_es_una_pagina_con_un_solo_indicador(self, ent):
        p = await listo(ent, UNO, DOS)
        from tests.test_asistente_confirmar_pg import formulario_de_confirmacion
        r = await enviar(formulario_de_confirmacion(p.t), htmx=False)
        assert r.status_code == 200 and r.text.count('class="pasos-asistente"') == 1 and "hx-swap-oob" not in r.text
        assert r.text.count('aria-current="step"') == 1

    async def test_t6_una_referencia_no_valida_no_afirma_ningun_paso(self, ent):
        r = await get(f"{V}/resultado", ref="no-valida")
        assert 'class="pasos-asistente"' not in r.text and "(hecho)" not in visible(r.text)

    async def test_t6_lo_pendiente_no_se_presenta_como_hecho(self, ent):
        pantallas, _ = await self._pantallas(ent)
        a = pasos(pantallas["A"])
        assert [c for _, c, _ in a] == ["actual", "pendiente", "pendiente"]
        v = pasos(pantallas["V"])
        assert [c for _, c, _ in v] == ["hecho", "actual", "pendiente"]
        assert "(pendiente)" in visible(pantallas["A"]) and "(hecho)" not in visible(pantallas["A"])

    async def test_t6_el_estado_se_dice_en_texto_no_solo_por_color(self, ent):
        pantallas, _ = await self._pantallas(ent)
        t = visible(pantallas["V"])
        assert "Elegir la serie (hecho)" in t and "Revisar los archivos (paso actual)" in t and "Vincular (pendiente)" in t


# ═══ T7 · criterio 4: navegar no confirma ═══════════════════════════════════════════════════════

class TestNavegarNoEscribe:

    async def test_t7_navegar_y_volver_no_escriben_en_la_bd_ni_en_el_disco(self, ent):
        await archivos(ent, UNO, DOS)
        sid = await serie_de_prueba(ent)
        antes, disco = await instantanea(ent.banco), huella_disco(ent.lib)
        desde = len(ent.banco.sentencias)
        tok = candidata()
        for ruta, params in [
            (A, {"clave": CLAVE}), (A, {"clave": CLAVE, "consulta": "Flash"}),
            (f"{A}/locales", {"clave": CLAVE, "q": "Flash"}),
            (f"{A}/manual", {"clave": CLAVE}),
            (f"{A}/alta", {"clave": CLAVE, "candidata": tok, "tradition": "american"}),
            (f"{A}/alta", {"clave": CLAVE, "titulo": "Flash", "anio": "1987", "tradition": "american"}),
            (f"{A}/alta/resultado", {"clave": CLAVE, "series_id": str(sid)}),
            (V, {"clave": CLAVE, "series_id": str(sid)}),
            (f"{V}/resultado", {"ref": "no-valida"}),
        ]:
            r = await get(ruta, **params)
            assert r.status_code == 200, (ruta, params)
        e = await elegir(candidata=tok, tradition="american")                              # elegir = vista previa
        assert e.status_code == 200
        assert escrituras(ent.banco, desde) == [], "navegar/elegir/volver no puede escribir"
        assert await instantanea(ent.banco) == antes and huella_disco(ent.lib) == disco
        sin_fuentes()




# ═══ Volver conserva la decisión ya tomada (criterio 5, revisión de #219) ═══════════════════════

class TestVolverConservaLaEleccion:
    """Se siguen los ENLACES que la pantalla ofrece (no se componen URLs): elegir → decidir entre parecidas → recargar."""

    async def _con_dos_parecidas(self, ent):
        await archivos(ent, UNO, DOS)
        a = await serie_de_prueba(ent, titulo="Flash", anio=1987)
        b = await serie_de_prueba(ent, titulo="Flash", anio=1986)
        return a, b

    async def test_es_esta_se_conserva_al_reconstruir_y_se_revalida(self, ent):
        a, b = await self._con_dos_parecidas(ent)
        r = await elegir(candidata=candidata(), tradition="american", consulta="Flash")
        assert "Es esta" in visible(r.text)
        es_esta = formulario_con(r.text, "/ui/descubrir/revisar", decision="reutilizar", serie_id=str(a))
        assert es_esta["consulta"] == "Flash"                                           # la búsqueda de la que se parte viaja
        p = await post("/ui/descubrir/revisar", es_esta)
        vinculo = enlace(p.text, "enlace a esta vista previa")
        assert "decision=reutilizar" in vinculo and f"serie_id={a}" in vinculo and "consulta=Flash" in vinculo
        antes = await instantanea(ent.banco)
        rec = await seguir(vinculo)
        v = visible(rec.text)
        assert "Se usará la serie existente que elegiste" in v and "Es esta" not in v and "Crear serie vacía" not in v
        assert "Decide de nuevo" not in v
        assert await instantanea(ent.banco) == antes
        # la serie elegida deja de existir: ya no vale, se dice, y se vuelve a decidir (no se da por buena en silencio)
        async with ent.banco.fabrica() as sesion:
            await sesion.execute(text("DELETE FROM series WHERE id = :i"), {"i": str(a)})
            await sesion.commit()
        v2 = visible((await seguir(vinculo)).text)
        assert "ya no vale" in v2 and "Decide de nuevo" in v2
        assert "Se usará la serie existente que elegiste" not in v2 and "Es esta" in v2   # queda la otra parecida

    async def test_crear_otra_se_conserva_al_reconstruir(self, ent):
        await self._con_dos_parecidas(ent)
        r = await elegir(candidata=candidata(), tradition="american")
        distinta = formulario_con(r.text, "/ui/descubrir/revisar", decision="crear_igualmente")
        p = await post("/ui/descubrir/revisar", distinta)
        vinculo = enlace(p.text, "enlace a esta vista previa")
        assert "decision=crear_igualmente" in vinculo
        v = visible((await seguir(vinculo)).text)
        assert "Crear serie vacía" in v and "Es esta" not in v and "Decide de nuevo" not in v

    async def test_una_decision_inventada_no_se_da_por_buena(self, ent):
        a, _ = await self._con_dos_parecidas(ent)
        otra = uuid4()
        r = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american", decision="reutilizar", serie_id=str(otra))
        v = visible(r.text)
        assert "ya no vale" in v and "Es esta" in v and "Se usará la serie existente" not in v
        r2 = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american", decision="reutilizar", serie_id="no-uuid")
        assert "Es esta" in visible(r2.text) and "Se usará la serie existente" not in visible(r2.text)

    async def test_el_camino_a_mano_tambien_conserva_sus_datos_y_su_decision(self, ent):
        a, _ = await self._con_dos_parecidas(ent)
        async with cliente() as c:
            f = await c.get(f"{A}/manual", params={"clave": CLAVE}, headers={"HX-Request": "true"})
        assert 'name="clave"' in f.text
        p = await post("/ui/descubrir/revisar", {"clave": CLAVE, "titulo": "Flash", "anio": "1987", "tradition": "american"})
        vinculo = enlace(p.text, "enlace a esta vista previa")
        assert "titulo=Flash" in vinculo and "anio=1987" in vinculo and "clave=Comics/Flash" in vinculo
        v = visible((await seguir(vinculo)).text)
        assert "Es esta" in v and "Crear serie vacía" not in v
        es_esta = formulario_con(p.text, "/ui/descubrir/revisar", decision="reutilizar", serie_id=str(a))
        p2 = await post("/ui/descubrir/revisar", es_esta)
        vinculo2 = enlace(p2.text, "enlace a esta vista previa")
        assert f"serie_id={a}" in vinculo2 and "titulo=Flash" in vinculo2
        v2 = visible((await seguir(vinculo2)).text)
        assert "Se usará la serie existente que elegiste" in v2 and "Es esta" not in v2

    async def test_el_resultado_de_elegir_tiene_una_sola_referencia_a_la_vista_previa(self, ent):
        """La envoltura de fuera ya no lleva un enlace propio que se quedaría viejo tras decidir."""
        await archivos(ent, UNO)
        r = await elegir(candidata=candidata(), tradition="american")
        assert visible(r.text).count("enlace a esta vista previa") == 1


# ═══ T11 · criterio 8: fallos y caducidad ═══════════════════════════════════════════════════════

class TestFallos:

    async def test_t11_la_serie_ya_no_existe_al_revisar(self, ent):
        await archivos(ent, UNO)
        for series_id in (str(uuid4()), "no-es-un-uuid"):
            r = await get(V, clave=CLAVE, series_id=series_id)
            v = visible(r.text)
            assert r.status_code == 200 and ("ya no existe" in v or "Hace falta una serie" in v), series_id
            assert 'class="vinculacion-confirmar"' not in r.text                    # no hay nada que confirmar

    async def test_t11_la_carpeta_ya_no_tiene_registros(self, ent):
        sid = await serie_de_prueba(ent)
        v = visible((await get(V, clave="Comics/NoExiste", series_id=str(sid))).text)
        assert "ya no tiene registros pendientes" in v
        a = visible((await get(f"{A}/alta/resultado", clave="Comics/NoExiste", series_id=str(sid))).text)
        assert "ya no tiene registros pendientes" in a and "Revisar los archivos de esta carpeta" not in a

    async def test_t11_un_alta_con_el_token_roto_no_crea_nada_ni_afirma_exito(self, ent):
        await archivos(ent, UNO)
        p = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american")
        roto = token_de_crear(p.text)[:-4] + "XXXX"
        antes = await instantanea(ent.banco)
        r = await post("/ui/descubrir/crear", {"token": roto})
        v = visible(r.text)
        assert r.status_code == 200 and "repite la vista previa" in v and "creada" not in v
        assert "Revisar los archivos" not in v and "/ui/descubrir/deshacer" not in r.text   # sin éxito, sin ids ni «Deshacer» inventados
        assert await instantanea(ent.banco) == antes

    async def test_t11_sin_clave_de_firma_no_se_ofrece_nada(self, ent, monkeypatch):
        await archivos(ent, UNO)
        sin = lambda: SimpleNamespace(secret_key="")                              # noqa: E731
        for modulo in (asistente_carpetas, discovery):
            monkeypatch.setattr(modulo, "get_settings", sin)
        r = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american")
        v = visible(r.text)
        assert "no tiene clave para firmar" in v and "Crear serie vacía" not in v


# ═══ T12, T13 · límites ═════════════════════════════════════════════════════════════════════════

class TestLimites:

    async def test_t12_cambiar_de_serie_descarta_los_numeros_borrador_de_la_anterior(self, ent):
        """Patrón de Sonarr: elegir otra serie invalida lo elegido debajo. Aquí los borradores viajan con la serie."""
        await archivos(ent, UNO, DOS)
        a = await serie_de_prueba(ent, titulo="Flash", anio=1987)
        b = await serie_de_prueba(ent, titulo="Flash", anio=1959)
        pa = await abrir(a)
        pa = await pa.reenviar(marcar=[UNO, DOS], numeros={UNO: "7"})
        assert pa.token is not None and pa.fila(UNO).numero == "7"
        pb = await abrir(b)                                                                  # otra serie: revisión limpia
        assert pb.token is None and all(not f.marcado for f in pb.filas)
        assert pb.fila(UNO).numero != "7"

    async def test_t13_un_token_de_candidata_con_clave_larga_cabe_en_el_campo(self, ent):
        clave_larga = "Comics/" + "x" * 990
        tok = candidata(clave=clave_larga)
        assert len(tok) <= MAX_TOKEN_CANDIDATA_SIN_GRUPO
        async with cliente() as c:
            r = await c.post("/ui/descubrir/revisar", data={"candidata": tok, "clave": clave_larga, "tradition": "american"})
        assert r.status_code == 200
