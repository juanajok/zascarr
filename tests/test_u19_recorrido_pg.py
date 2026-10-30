# ruff: noqa: E501, F401, F811
"""U19 (#206, BL-U19) — volver, recuperar y leer el comprobante, sobre Postgres real y con las fuentes SIMULADAS.

Contrato: `docs/design/benchmark-U19-recorrido-vincular.md` (§6.4 referencias de navegación, §7.2 lectura del comprobante,
§8 casos de prueba). Estas son las pruebas de MAYOR RIESGO (T8, T9 y T10), escritas ANTES de implementar: cada una falla por el
comportamiento que falta (las rutas nuevas no existen), no por un fallo de la prueba.

| # | Criterio de #206 | Clase |
|---|---|---|
| T8 | 5. Volver antes del alta conserva la elección y no busca en fuentes | `TestT8VolverAntesDelAlta` |
| T9 | 6. Volver después del alta conserva el resultado y no lo repite ni lo deshace | `TestT9VolverDespuesDelAlta` |
| T10 | 7. Volver después de vincular lee el comprobante, sin ejecutar de nuevo | `TestT10LecturaDelComprobante` |

La lectura del comprobante (T10) fija la PRECEDENCIA de la ficha §7.2: integridad → vencimiento → fila. El vencimiento es
`firma + RETENCION_HORAS × 3600` (constante de la operación), con el reloj de la ruta sustituido por `asistente_vinculacion.reloj`.

Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import time
from types import SimpleNamespace
from urllib.parse import quote, unquote, urlencode
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import text

from tests.test_asistente_confirmar_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    Resultado,
    confirmar,
    enviar,
    formulario_de_confirmacion,
    listo,
    numero_de,
    operaciones,
    vinculados,
)
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
from tests.test_vinculacion_pg import ent  # noqa: F401
from tests.test_vinculacion_previa_pg import escrituras, huella_disco, instantanea
from zascarr.config import get_settings
from zascarr.main import app
from zascarr.models import ComicTradition
from zascarr.services.auth import verify_token
from zascarr.services.discovery import DiscoveryService
from zascarr.services.tokens_revision import (
    CandidataFirmada,
    candidata_firmable,
    crear_referencia_de_resultado,
    crear_token,
    crear_token_candidata,
    grupo_de_un_token,
    verificar_token_vinculacion,
)
from zascarr.services.vinculacion import RETENCION_HORAS, VinculacionDeArchivos
from zascarr.web import asistente_carpetas, asistente_vinculacion, discovery

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

A = "/ui/pendientes/carpetas/asistente"
V = f"{A}/vinculacion"
UNO, DOS, TRES = "Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (1987).cbz"
PLAZO = RETENCION_HORAS * 3600
PROPOSITO_REF = "resultado_vinculacion"           # contrato de la ficha §7.2


@pytest.fixture(autouse=True)
def _secreto_y_sin_red(monkeypatch):
    ajustes = lambda: SimpleNamespace(secret_key=SECRETO)                      # noqa: E731
    for modulo in (asistente_carpetas, asistente_vinculacion, discovery):
        monkeypatch.setattr(modulo, "get_settings", ajustes)


# ── ayudas ──────────────────────────────────────────────────────────────────────────────────────

def visible(t: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())


async def get(ruta: str, **params) -> httpx.Response:
    async with cliente() as c:
        return await c.get(ruta, params=params)


def candidata(clave: str = CLAVE, **kw) -> str:
    c = candidata_firmable("comic_vine", "4050", kw.get("titulo", "Flash"), kw.get("anio", 1987), "american", None, None)
    return crear_token_candidata(clave, c, SECRETO, ahora=kw.get("ahora"))


def enlace(t: str, texto: str) -> str:
    """El `href` (ya sin escapar) del enlace de la pantalla cuyo texto contiene `texto`: lo que la persona realmente pulsa.
    Los tests siguen estos enlaces; no componen URLs a partir de los identificadores."""
    for href, cuerpo in re.findall(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        if texto in visible(cuerpo):
            return html.unescape(href)
    raise AssertionError(f"la pantalla no ofrece ningún enlace «{texto}»")


async def seguir(href: str) -> httpx.Response:
    async with cliente() as c:
        return await c.get(href)


def token_de_crear(t: str) -> str:
    m = re.search(r'hx-post="/ui/descubrir/crear".*?name="token" value="([^"]+)"', t, re.S)
    assert m, "la vista previa no ofrece crear"
    return html.unescape(m.group(1))


async def crear_alta(ent, **kw) -> httpx.Response:
    """El camino real: vista previa por GET (nueva) y luego el POST de `/ui/descubrir/crear` con su token."""
    p = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(**kw), tradition="american")
    assert p.status_code == 200, p.text[:300]
    async with cliente() as c:
        return await c.post("/ui/descubrir/crear", data={"token": token_de_crear(p.text)}, headers={"HX-Request": "true"})


async def series(ent) -> list[tuple]:
    async with ent.banco.fabrica() as s:
        return [tuple(r) for r in (await s.execute(text("SELECT id, title FROM series ORDER BY id"))).all()]


LLAMADAS_A_FUENTES: list[str] = []


@pytest.fixture(autouse=True)
def _vigilar_las_fuentes(monkeypatch):
    """Cualquier intento de consultar una fuente queda anotado (y falla): volver nunca busca (ficha §6.4, regla 3)."""
    LLAMADAS_A_FUENTES.clear()

    async def prohibido(*a, **k):
        LLAMADAS_A_FUENTES.append("consulta")
        raise AssertionError("no se puede consultar una fuente al volver")
    monkeypatch.setattr(DiscoveryService, "search_detallada", prohibido)
    monkeypatch.setattr(asistente_carpetas, "buscar_a_ritmo", prohibido)


def sin_fuentes(ent=None):
    assert LLAMADAS_A_FUENTES == [], "volver/reconstruir no puede consultar ninguna fuente"


# ═══ T8 · criterio 5: volver ANTES del alta ═════════════════════════════════════════════════════

class TestT8VolverAntesDelAlta:

    async def test_t8a_la_vista_previa_desde_candidata_se_reconstruye_por_get_sin_efectos(self, ent):
        await archivos(ent, UNO, DOS)
        antes, disco = await instantanea(ent.banco), huella_disco(ent.lib)
        desde = len(ent.banco.sentencias)
        r = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american")
        assert r.status_code == 200
        v = visible(r.text)
        assert "Flash" in v and "Crear serie vacía" in v and "Crear serie vacía" in v
        assert "no vincula ningún archivo" in v                                  # sigue siendo SOLO el alta
        assert grupo_de_un_token(token_de_crear(r.text), SECRETO) == CLAVE      # conserva la carpeta
        assert await instantanea(ent.banco) == antes and huella_disco(ent.lib) == disco
        assert escrituras(ent.banco, desde) == []
        sin_fuentes(ent)

    async def test_t8a_la_vista_previa_a_mano_se_reconstruye_por_get(self, ent):
        await archivos(ent, UNO)
        antes = await instantanea(ent.banco)
        r = await get(f"{A}/alta", clave=CLAVE, titulo="Flash", anio="1987", tradition="american")
        assert r.status_code == 200 and "Crear serie vacía" in visible(r.text)
        assert grupo_de_un_token(token_de_crear(r.text), SECRETO) == CLAVE
        assert await instantanea(ent.banco) == antes

    @pytest.mark.parametrize("caso", ["caducada", "manipulada", "de_otra_carpeta"])
    async def test_t8b_una_eleccion_que_ya_no_vale_dice_que_caduco_y_no_busca(self, ent, caso):
        await archivos(ent, UNO)
        token = {"caducada": lambda: candidata(ahora=time.time() - 3600),
                 "manipulada": lambda: candidata()[:-3] + ("AAA" if not candidata().endswith("AAA") else "BBB"),
                 "de_otra_carpeta": lambda: candidata(clave="Comics/Otra")}[caso]()
        antes = await instantanea(ent.banco)
        r = await get(f"{A}/alta", clave=CLAVE, candidata=token, tradition="american", consulta="Flash")
        assert r.status_code == 200
        v = visible(r.text)
        assert "caducó" in v and "Vuelve a buscar" in v
        assert "Crear serie vacía" not in v and "Usar esta serie" not in v         # no ofrece confirmar nada
        assert await instantanea(ent.banco) == antes
        sin_fuentes(ent)

    async def test_t8c_volver_nunca_llama_a_las_fuentes(self, ent):
        """Recorre A, P, C, V reconstruidos: ni `search_detallada` ni `buscar_a_ritmo` (la vigilancia es autouse)."""
        await archivos(ent, UNO, DOS)
        assert (await get(A, clave=CLAVE, consulta="Flash")).status_code == 200
        assert (await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american")).status_code == 200
        r = await crear_alta(ent)
        assert r.status_code == 200 and "creada" in visible(r.text)
        sid = (await series(ent))[0][0]
        assert (await get(f"{A}/alta/resultado", clave=CLAVE, series_id=str(sid))).status_code == 200
        assert (await get(V, clave=CLAVE, series_id=str(sid))).status_code == 200
        sin_fuentes()

    async def test_t8d_la_consulta_se_precarga_pero_no_se_ejecuta(self, ent):
        await archivos(ent, UNO)
        r = await get(A, clave=CLAVE, consulta="Zzzz Mortadelo")
        assert r.status_code == 200
        assert re.search(r'name="consulta"[^>]*value="Zzzz Mortadelo"', r.text)
        assert 'class="discovery-list"' not in r.text and "Se ha buscado" not in r.text     # no hay resultados
        sin_fuentes(ent)

    async def test_t8e_si_la_serie_aparece_o_desaparece_la_vista_previa_se_recalcula_y_lo_dice(self, ent):
        await archivos(ent, UNO)
        # entre la elección y volver, alguien creó la serie con ese identificador
        await serie_de_prueba(ent, comic_vine_id=4050)
        r = await get(f"{A}/alta", clave=CLAVE, candidata=candidata(), tradition="american")
        v = visible(r.text)
        assert "Ya existe una serie con ese identificador" in v or "Se usará la serie que ya tienes" in v
        assert "Crear serie vacía" not in v                                       # ya no se crearía otra
        assert (await numero_de("series", ent.banco)) == 1

    async def test_t8_sin_la_carpeta_no_hay_vista_previa_y_se_dice(self, ent):
        r = await get(f"{A}/alta", clave="Comics/NoExiste", candidata=candidata(clave="Comics/NoExiste"), tradition="american")
        assert r.status_code in (200, 404)
        assert "ya no tiene registros pendientes" in visible(r.text)


# ═══ T9 · criterio 6: volver DESPUÉS del alta ═══════════════════════════════════════════════════

class TestT9VolverDespuesDelAlta:

    async def test_t9a_c_reconstruida_dice_que_la_serie_existe_sin_repetirla_ni_deshacerla(self, ent):
        await archivos(ent, UNO, DOS, TRES)
        c = await crear_alta(ent)
        assert "creada" in visible(c.text)
        vinculo = enlace(c.text, "enlace al estado de esta alta")                     # el que ve la persona en el resultado
        antes, disco = await instantanea(ent.banco), huella_disco(ent.lib)
        desde = len(ent.banco.sentencias)
        r = await seguir(vinculo)
        assert r.status_code == 200
        v = visible(r.text)
        assert "ya está creada" in v and "Flash" in v
        assert "Quedan 3 archivos" in v and "Revisar los archivos" in v
        assert "Deshacer" not in v and "/ui/descubrir/deshacer" not in r.text           # reconstruir no reabre un efecto
        assert "no se ha creado" not in v.lower() and "no hubo alta" not in v.lower()
        assert await instantanea(ent.banco) == antes and huella_disco(ent.lib) == disco
        assert escrituras(ent.banco, desde) == []
        sin_fuentes(ent)

    async def test_t9_el_resultado_del_alta_ofrece_el_enlace_al_estado_y_se_puede_recargar(self, ent):
        await archivos(ent, UNO, DOS)
        c = await crear_alta(ent)
        vinculo = enlace(c.text, "enlace al estado de esta alta")
        antes = await instantanea(ent.banco)
        primera, segunda = await seguir(vinculo), await seguir(vinculo)               # recargar
        assert primera.text == segunda.text and "ya está creada" in visible(primera.text)
        assert await instantanea(ent.banco) == antes
        assert "Deshacer" in visible(c.text) and "Deshacer" not in visible(primera.text)

    async def test_t9_tras_vincular_el_estado_del_alta_no_dice_que_la_serie_esta_vacia(self, ent):
        """El comprobante `creada` acredita el alta original, no que la serie siga vacía: con archivos ya vinculados no puede decirlo."""
        await archivos(ent, UNO, DOS, TRES)
        c = await crear_alta(ent)
        sid = (await series(ent))[0][0]
        vinculo = enlace(c.text, "enlace al estado de esta alta")
        antes = visible((await seguir(vinculo)).text)
        assert "vacía" not in antes and "Quedan 3 archivos" in antes                    # tampoco antes: no se afirma
        p = await abrir(sid)
        p = await p.reenviar(marcar=[UNO, DOS])
        r = await confirmar(p)
        assert r.estado == "vinculados_todos"
        despues = visible((await seguir(vinculo)).text)
        assert "vacía" not in despues and "ya está creada" in despues
        assert "Queda 1 archivo" in despues                                              # los hechos de AHORA, no los de entonces

    async def test_t9b_deshecha(self, ent):
        await archivos(ent, UNO)
        c = await crear_alta(ent)
        sid, _ = (await series(ent))[0]
        operacion = re.search(r'name="operacion_id" value="([^"]+)"', c.text).group(1)
        vinculo = enlace(c.text, "enlace al estado de esta alta")
        async with cliente() as k:
            d = await k.post("/ui/descubrir/deshacer", data={"series_id": str(sid), "operacion_id": operacion})
        assert "Hecho" in visible(d.text)
        r = await seguir(vinculo)
        v = visible(r.text)
        assert "se deshizo" in v and "ya no está en tu biblioteca" in v
        assert "ya está creada" not in v

    async def test_t9b_serie_existente_sin_comprobante_no_afirma_quien_la_creo(self, ent):
        """Reutilizar no escribe nada (no hay `alta_operaciones`), y un comprobante purgado tampoco: solo consta que existe."""
        await archivos(ent, UNO)
        sid = await serie_de_prueba(ent)
        r = await get(f"{A}/alta/resultado", clave=CLAVE, series_id=str(sid))
        v = visible(r.text)
        assert r.status_code == 200 and "Flash" in v and "está en tu biblioteca" in v
        assert "ya está creada" not in v and "no hubo alta" not in v.lower() and "Deshacer" not in v

    async def test_t9b_comprobante_purgado_degrada_a_hechos(self, ent):
        await archivos(ent, UNO)
        c = await crear_alta(ent)
        sid, _ = (await series(ent))[0]
        vinculo = enlace(c.text, "enlace al estado de esta alta")
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM alta_operaciones"))
            await s.commit()
        v = visible((await seguir(vinculo)).text)
        assert "está en tu biblioteca" in v and "ya está creada" not in v

    async def test_t9b_serie_que_ya_no_existe(self, ent):
        await archivos(ent, UNO)
        r = await get(f"{A}/alta/resultado", clave=CLAVE, series_id=str(uuid4()))
        assert r.status_code == 200 and "ya no existe" in visible(r.text)
        assert "ya está creada" not in visible(r.text)

    async def test_t9_v_con_serie_valida_dice_que_hacer_y_no_afirma_lo_que_no_consta(self, ent):
        await archivos(ent, UNO, DOS)
        sid = await serie_de_prueba(ent)
        v = visible((await get(V, clave=CLAVE, series_id=str(sid))).text)
        assert "Vas a preparar los archivos de esta carpeta para" in v and "Flash" in v
        assert "no vincula nada hasta que lo confirmes" in v
        assert "aún no se ha vinculado nada" not in v                     # eso no consta sin comprobante


# ═══ T10 · criterio 7: leer el comprobante ══════════════════════════════════════════════════════

def ref_de(t: str) -> str:
    """La referencia que el resultado de la vinculación pone en el enlace a sí mismo."""
    m = re.search(r'href="[^"]*/vinculacion/resultado\?ref=([^"&]+)"', t)
    assert m, "el resultado no ofrece un enlace a sí mismo (la referencia de §7.2)"
    return unquote(html.unescape(m.group(1)))


def caducidad_de(ref: str) -> int:
    crudo = verify_token(ref, SECRETO)
    assert crudo is not None
    return json.loads(base64.urlsafe_b64decode(crudo.encode()).decode())["exp"]


async def vinculada(ent, monkeypatch=None):
    """Una vinculación REAL de dos archivos. Devuelve (página de resultado, `ref`, `exp`, `firma`)."""
    p = await listo(ent, UNO, DOS)
    firma = verificar_token_vinculacion(p.token, SECRETO, ignorar_caducidad=True).caduca - 15 * 60
    r = await confirmar(p)
    assert r.estado == "vinculados_todos"
    ref = ref_de(r.t)
    return SimpleNamespace(p=p, r=r, ref=ref, exp=caducidad_de(ref), firma=firma)


class _RelojFalso:
    """Sustituye el nombre `time` de un módulo: `time()` devuelve la hora simulada y lo demás, el módulo real."""

    def __init__(self, hora: dict) -> None:
        self._hora = hora

    def time(self) -> float:
        return self._hora["t"]

    def __getattr__(self, nombre: str):
        return getattr(time, nombre)


@pytest.fixture
def reloj(monkeypatch):
    """UN reloj simulado para TODOS los componentes que miran la hora: la lectura y la emisión de la referencia
    (`web.asistente_vinculacion`), la validez de los tokens (`tokens_revision`) y la confirmación (`services.vinculacion`).
    Cambiar `reloj["t"]` adelanta de verdad lo que cada uno ve; no depende de cuánto tarde la prueba."""
    from zascarr.services import tokens_revision as tokens
    from zascarr.services import vinculacion as servicio
    hora = {"t": time.time()}
    falso = _RelojFalso(hora)
    for modulo in (asistente_vinculacion, tokens, servicio):
        monkeypatch.setattr(modulo, "time", falso)
    return hora


async def leer(ref: str) -> httpx.Response:
    return await get(f"{V}/resultado", ref=ref)


NO_VALIDA = "Esta referencia no es válida"
VENCIDA = "Ha vencido el plazo para consultar este resultado"
NO_ENCONTRADO = "No se encuentra el resultado de esta vinculación"


class TestT10LecturaDelComprobante:

    async def test_t10a_valida_devuelve_el_informe_guardado_sin_ejecutar(self, ent, reloj, monkeypatch):
        v = await vinculada(ent)

        async def prohibido(*a, **k):
            raise AssertionError("la lectura no puede ejecutar ni repetir una vinculación")
        monkeypatch.setattr(asistente_vinculacion, "ejecutar_vinculacion", prohibido)
        antes, informes, disco = await instantanea(ent.banco), await _informes(ent), huella_disco(ent.lib)
        r = await leer(v.ref)
        assert r.status_code == 200
        t = visible(r.text)
        assert "Hecho: todos los archivos quedaron vinculados" in t and "resultado guardado" in t
        assert UNO in t and DOS in t
        assert await instantanea(ent.banco) == antes and await _informes(ent) == informes and huella_disco(ent.lib) == disco
        assert r.headers.get("cache-control") == "no-store"

    @pytest.mark.parametrize("caso", [
        "malformada", "firma_rota", "otro_proposito", "otra_carpeta", "datos_no_uuid", "otra_serie_en_la_fila"])
    async def test_t10b_no_valida_siempre_el_mismo_texto_sin_pistas(self, ent, reloj, caso):
        v = await vinculada(ent)
        op = (await _informes(ent))[0][0]
        datos = {"series_id": str(uuid4()), "operacion": str(op)}
        ref = {
            "malformada": "esto-no-es-una-referencia",
            "firma_rota": v.ref[:-4] + ("AAAA" if not v.ref.endswith("AAAA") else "BBBB"),
            "otro_proposito": crear_token("vincular", CLAVE, datos, SECRETO, ahora=v.firma, ttl=PLAZO),
            "otra_carpeta": crear_token(PROPOSITO_REF, "Comics/Otra", datos, SECRETO, ahora=v.firma, ttl=PLAZO),
            "datos_no_uuid": crear_token(PROPOSITO_REF, CLAVE, {"series_id": "no", "operacion": "tampoco"}, SECRETO,
                                         ahora=v.firma, ttl=PLAZO),
            "otra_serie_en_la_fila": crear_token(PROPOSITO_REF, CLAVE, datos, SECRETO, ahora=v.firma, ttl=PLAZO),
        }[caso]
        reloj["t"] = v.firma + 60
        r = await leer(ref)
        assert r.status_code == 200
        t = visible(r.text)
        assert NO_VALIDA in t and "No se ha cambiado nada" in t
        assert VENCIDA not in t and NO_ENCONTRADO not in t and UNO not in t       # sin pistas ni informe

    async def test_t10c_no_encontrado_antes_del_vencimiento(self, ent, reloj):
        v = await vinculada(ent)
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM vinculacion_operaciones"))
            await s.commit()
        reloj["t"] = v.exp - 60
        r = await leer(v.ref)
        t = visible(r.text)
        assert NO_ENCONTRADO in t and "No se sabe si se aplicó" in t
        assert "Hecho" not in t and "<form" not in r.text                         # ni éxito ni fracaso ni reintento
        assert VENCIDA not in t
        sid = v.p.serie                                                           # y los enlaces para seguir, con la serie del token
        enlaces = [html.unescape(h) for h in re.findall(r'href="([^"]+)"', r.text)]
        assert f"/ui/series/{sid}" in enlaces and f"/ui/pendientes/carpetas?serie={sid}" in enlaces
        assert "Volver a la ficha de la serie" in t and "Elegir otra carpeta para esta serie" in t

    async def test_t10c_una_referencia_no_valida_no_ofrece_enlaces_de_la_serie(self, ent, reloj):
        r = await leer("esto-no-es-una-referencia")
        assert NO_VALIDA in visible(r.text)
        assert "/ui/series/" not in r.text and "carpetas?serie=" not in r.text
        assert "Volver a la ficha de la serie" not in visible(r.text)

    async def test_t10c2_expirado_con_la_fila_ya_purgada(self, ent, reloj):
        v = await vinculada(ent)
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM vinculacion_operaciones"))
            await s.commit()
        reloj["t"] = v.exp + 10
        t = visible((await leer(v.ref)).text)
        assert VENCIDA in t and "no deshace" in t
        assert NO_ENCONTRADO not in t and NO_VALIDA not in t

    async def test_t10h_referencia_vencida_con_la_fila_todavia_presente_es_expirada(self, ent, reloj):
        """La purga física NO decide: pasado `exp`, la fila aún presente tampoco se lee ni se muestra."""
        v = await vinculada(ent)
        assert (await operaciones(ent.banco)) == 1                  # la fila sigue ahí
        reloj["t"] = v.exp + 1
        presente = await leer(v.ref)
        t = visible(presente.text)
        assert VENCIDA in t and UNO not in t and "Hecho" not in t and "vinculados" not in t.lower().replace("no deshace la vinculación", "")
        async with ent.banco.fabrica() as s:
            await s.execute(text("DELETE FROM vinculacion_operaciones"))
            await s.commit()
        purgada = await leer(v.ref)
        assert visible(purgada.text) == t                               # mismo resultado, exista o no la fila

    async def test_t10i_el_limite_exacto_del_vencimiento(self, ent, reloj):
        v = await vinculada(ent)
        for ahora, esperado in ((v.exp - 1, "valido"), (v.exp, "vencido"), (v.exp + 1, "vencido")):
            reloj["t"] = ahora
            t = visible((await leer(v.ref)).text)
            if esperado == "valido":
                assert "Hecho: todos los archivos quedaron vinculados" in t and VENCIDA not in t, ahora
            else:
                assert VENCIDA in t and "Hecho" not in t, ahora

    async def test_t10j_integridad_antes_que_vencimiento(self, ent, reloj):
        v = await vinculada(ent)
        reloj["t"] = v.exp + 3600                                       # vencida
        manipulada = v.ref[:-4] + ("AAAA" if not v.ref.endswith("AAAA") else "BBBB")
        t = visible((await leer(manipulada)).text)
        assert NO_VALIDA in t and VENCIDA not in t                       # una manipulada nunca revela que estaba vencida
        assert VENCIDA in visible((await leer(v.ref)).text)              # una íntegra y vencida sí

    async def test_t10k_leer_o_regenerar_no_reinicia_el_plazo(self, ent, reloj):
        v = await vinculada(ent)
        assert v.exp == v.firma + PLAZO
        # repetir la confirmación con el MISMO token una hora después (el token, de 15 min, ya está caducado: el servicio
        # devuelve el informe guardado): la referencia que se emite tiene el MISMO vencimiento
        reloj["t"] = v.firma + 3600
        repetida = await confirmar(v.p)
        assert repetida.estado == "vinculados_todos" and "ya se había aplicado" in visible(repetida.t)
        assert caducidad_de(ref_de(repetida.t)) == v.exp
        # y 23 horas después
        reloj["t"] = v.firma + 23 * 3600
        assert caducidad_de(ref_de((await confirmar(v.p)).t)) == v.exp
        # la lectura no emite una referencia nueva: reenvía la recibida
        reloj["t"] = v.exp - 10
        leida = (await leer(v.ref)).text
        assert caducidad_de(ref_de(leida)) == v.exp and ref_de(leida) == v.ref

    async def test_t10l_la_purga_real_no_borra_nada_antes_del_vencimiento_y_si_despues(self, ent, reloj):
        """El plazo de la referencia y la purga del servicio son coherentes. Se reponen dos filas con las fechas que tendrían si la
        vinculación se hubiera firmado hace casi 24 h (vence en 60 s) y hace algo más de 24 h (venció hace 60 s); la purga REAL
        (con el reloj de la base de datos) solo borra la segunda, y la lectura dice lo mismo que la purga."""
        v = await vinculada(ent)
        assert v.exp - v.firma == PLAZO
        async with ent.banco.fabrica() as s:
            fila = (await s.execute(text(
                "SELECT operacion_id::text, series_id::text, resultado FROM vinculacion_operaciones"))).one()
            await s.execute(text("DELETE FROM vinculacion_operaciones"))
            await s.commit()
        ahora = time.time()
        casos = {}
        for nombre, vence_en in (("casi_24h", 60), ("mas_de_24h", -60)):
            firma = ahora + vence_en - PLAZO
            op = str(uuid4())
            documento = {**fila[2], "operacion_id": op}
            async with ent.banco.fabrica() as s:
                await s.execute(text(
                    "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta, creada) VALUES "
                    "(:o, :s, CAST(:r AS jsonb), to_timestamp(:h), to_timestamp(:c))"),
                    {"o": op, "s": fila[1], "r": json.dumps(documento), "h": firma + 15 * 60, "c": firma + 1})
                await s.commit()
            ref = crear_referencia_de_resultado(CLAVE, fila[1], op, firma=firma, plazo_s=PLAZO, secret=SECRETO)
            assert caducidad_de(ref) == int(firma + PLAZO)
            casos[nombre] = (op, ref)
        async with ent.banco.fabrica() as s:
            await VinculacionDeArchivos(s, secret=SECRETO)._purgar()                    # la purga real, con la hora de la base
            await s.commit()
            vivas = {r[0] for r in (await s.execute(text("SELECT operacion_id::text FROM vinculacion_operaciones"))).all()}
        assert casos["casi_24h"][0] in vivas and casos["mas_de_24h"][0] not in vivas
        reloj["t"] = ahora
        assert "Hecho" in visible((await leer(casos["casi_24h"][1])).text)              # antes de `exp`: fila viva y se lee
        assert VENCIDA in visible((await leer(casos["mas_de_24h"][1])).text)            # después: expirado, y la fila ya no está

    async def test_t10d_la_lectura_no_alarga_la_retencion(self, ent, reloj):
        v = await vinculada(ent)
        antes = await _informes(ent)
        reloj["t"] = v.exp - 5
        for _ in range(3):
            await leer(v.ref)
        assert await _informes(ent) == antes                              # `creada` y el documento, intactos

    async def test_t10e_la_lectura_no_confirma_ni_reintenta(self, ent, reloj, monkeypatch):
        v = await vinculada(ent)
        llamadas = []
        real = VinculacionDeArchivos._purgar

        async def espia(self):
            llamadas.append(1)
            return await real(self)
        monkeypatch.setattr(VinculacionDeArchivos, "_purgar", espia)
        desde = len(ent.banco.sentencias)
        reloj["t"] = v.exp - 5
        await leer(v.ref)
        assert escrituras(ent.banco, desde) == [] and llamadas == []     # ni escritura, ni candado, ni purga

    async def test_t10f_la_lectura_no_expone_rutas_token_ni_sesion(self, ent, reloj):
        v = await vinculada(ent)
        reloj["t"] = v.exp - 5
        r = await leer(v.ref)
        cuerpo = r.text + str(r.headers)
        assert str(ent.lib) not in cuerpo and "file_path" not in cuerpo
        assert v.p.token not in cuerpo and "zascarr_session" not in cuerpo
        assert re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.sub(r'href="[^"]*"', "", r.text)) is None, \
            "no se pintan ids de archivo"

    async def test_t10g_la_lectura_exige_autenticacion(self, ent, reloj):
        v = await vinculada(ent)
        ajustes = get_settings()
        anterior = ajustes.auth_mode
        ajustes.auth_mode = "password"
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                         follow_redirects=False) as c:
                r = await c.get(f"{V}/resultado", params={"ref": v.ref})
        finally:
            ajustes.auth_mode = anterior
        assert r.status_code in (302, 303, 307, 401, 403) and "Hecho" not in r.text

    async def test_t10_el_resultado_inmediato_enlaza_a_si_mismo_con_la_referencia(self, ent, reloj):
        v = await vinculada(ent)
        assert "enlace a este resultado" in visible(v.r.t)
        assert v.exp - v.firma == PLAZO


async def _informes(ent) -> list[tuple]:
    async with ent.banco.fabrica() as s:
        return [tuple(r) for r in (await s.execute(text(
            "SELECT operacion_id::text, series_id::text, resultado, token_hasta, creada FROM vinculacion_operaciones ORDER BY creada"))).all()]
