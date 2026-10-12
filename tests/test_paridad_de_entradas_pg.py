# ruff: noqa: E501, F401, F811
"""Paridad de las entradas que crean o renombran una serie (#113, criterio «una colisión por otra entrada no elude la
comprobación»): sobre Postgres real, con los MISMOS datos, el alta con grupo (API), el alta sin grupo (servicio y API sin carpeta), Descubrir
(UI, dos pasos) y `PATCH` ven EXACTAMENTE las mismas series parecidas y ninguna crea ni cambia nada en silencio.

**Excepción declarada (A1):** `POST /api/series` no participa: no detecta colisiones y está obsoleto (I3), su retirada es de
I6 (#114). Lo documenta `test_centralizacion_de_series.py`. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import zascarr.web.discovery as web_discovery
from tests.test_alta_serie_pg import (  # noqa: F401  (BD efímera y entorno sin red)
    CARPETA,
    PREV,
    SECRETO,
    cliente,
    entorno,
    numero_de_series,
    post,
    sembrar_serie,
    serie_en_bd,
    url_bd,
)
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.alta_serie import AltaDeSerie, DatosManuales
from zascarr.services.discovery import DiscoveryResult, DiscoveryService
from zascarr.services.tokens_revision import (
    CLAVE_SIN_GRUPO,
    CandidataFirmada,
    crear_token_candidata,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

AM, MANGA = ComicTradition.AMERICAN, ComicTradition.MANGA

#: (título, año, tradición) ya existentes. Mezcla lo que SÍ es parecida de «Saga del Faro» 2010 americana y lo que no.
EXISTENTES = [
    ("Saga del Faro", 2009, AM),        # año ±1 → parecida
    ("SAGA del  faro", 2011, AM),       # mayúsculas y espacios → mismo título normalizado, ±1 → parecida
    ("Saga del Faro", 2010, MANGA),     # otra tradición → NO
    ("Saga del Faro", 2020, AM),        # año lejano → NO
    ("Otra cosa", 2010, AM),            # otro título → NO
]
#: (año pedido, tradición pedida). La respuesta esperada se CALCULA aparte (`esperadas`), no se escribe a mano.
CASOS = [
    (2010, "american"),      # ±1 de 2009 y de 2011
    (None, "american"),      # año desconocido: no descarta (se avisa de más antes que de menos)
    (2012, "american"),      # solo el 2011 (el 2009 y el 2020 quedan lejos)
    (2010, "manga"),         # solo la serie manga
    (2013, "american"),      # FRONTERA: el 2011 queda a 2 años, no es parecida: ninguna entrada ve nada
]


@pytest.fixture(autouse=True)
def _clave_de_firma_web(monkeypatch, entorno):
    monkeypatch.setattr(web_discovery, "get_settings", lambda: SimpleNamespace(secret_key=SECRETO))


async def sembrar_existentes(entorno) -> dict[tuple, str]:
    ids = {}
    for titulo, anio, trad in EXISTENTES:
        ids[(titulo, anio, trad)] = str(await sembrar_serie(entorno.banco, titulo, anio, trad))
    return ids


def esperadas(ids, anio, tradicion) -> set[str]:
    """Lo que dice la regla (título normalizado igual, año ±1 o desconocido, misma tradición), calculada aquí aparte."""
    trad = ComicTradition(tradicion)
    return {i for (t, a, tr), i in ids.items()
            if t.lower().split() == ["saga", "del", "faro"] and tr == trad and (anio is None or a is None or abs(a - anio) <= 1)}


async def por_alta_con_grupo(anio, tradicion) -> set[str]:
    r = await post(PREV, {"clave": CARPETA, "manual": {"titulo": "Saga del Faro", "anio": anio}, "tradicion": tradicion})
    assert r.status_code == 200, r.text
    return {p["series_id"] for p in r.json()["parecidas"]}


async def por_alta_api_sin_carpeta(anio, tradicion) -> set[str]:
    r = await post("/api/revision/serie/sin-carpeta/previsualizar",
                   {"manual": {"titulo": "Saga del Faro", "anio": anio}, "tradicion": tradicion})
    assert r.status_code == 200, r.text
    return {p["series_id"] for p in r.json()["parecidas"]}


async def por_alta_sin_grupo(entorno, anio, tradicion) -> set[str]:
    async with entorno.banco.fabrica() as s:
        v = await AltaDeSerie(s, secret=SECRETO).previsualizar_sin_grupo(
            tradicion=ComicTradition(tradicion), manual=DatosManuales("Saga del Faro", anio))
    return {p.series_id for p in v.parecidas}


async def por_descubrir(monkeypatch, anio, tradicion) -> set[str]:
    candidata = crear_token_candidata(
        CLAVE_SIN_GRUPO, CandidataFirmada("comic_vine", "5000", "Saga del Faro", anio, "american", None, None), SECRETO)
    async with cliente() as c:
        r = await c.post("/ui/descubrir/revisar", data={"candidata": candidata, "tradition": tradicion})
    assert r.status_code == 200, r.text
    return set(re.findall(r'href="/ui/series/([0-9a-f-]{36})"', r.text.split("Series que ya tienes")[-1])) \
        if "Series que ya tienes" in r.text else set()


async def por_patch(entorno, anio, tradicion) -> set[str]:
    mia = str(await sembrar_serie(entorno.banco, "Un título cualquiera", 1950, ComicTradition.OTHER))
    async with cliente() as c:
        r = await c.patch(f"/api/series/{mia}", json={"title": "Saga del Faro", "start_year": anio, "tradition": tradicion})
    if r.status_code == 200:
        return set()
    assert r.status_code == 409 and r.json()["detail"]["codigo"] == "serie_parecida", r.text
    return {p["series_id"] for p in r.json()["detail"]["parecidas"]}


class TestLasCuatroEntradasVenLasMismasParecidas:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("anio,tradicion", CASOS)
    async def test_mismos_datos_misma_deteccion(self, entorno, monkeypatch, anio, tradicion):
        ids = await sembrar_existentes(entorno)
        previstas = esperadas(ids, anio, tradicion)
        resultados = {
            "alta con grupo (API)": await por_alta_con_grupo(anio, tradicion),
            "alta sin grupo (servicio)": await por_alta_sin_grupo(entorno, anio, tradicion),
            "alta por API sin carpeta": await por_alta_api_sin_carpeta(anio, tradicion),
            "Descubrir (UI)": await por_descubrir(monkeypatch, anio, tradicion),
            "PATCH": await por_patch(entorno, anio, tradicion),
        }
        assert resultados == {entrada: previstas for entrada in resultados}, resultados


class TestNingunaEntradaCreaOCambiaEnSilencio:
    """Con parecidas y sin decisión de la persona, ninguna entrada deja una serie nueva ni cambia una existente."""

    @pytest.mark.asyncio
    async def test_sin_decision_no_hay_efectos(self, entorno, monkeypatch):
        await sembrar_existentes(entorno)
        antes = await numero_de_series(entorno.banco)
        await por_alta_con_grupo(2010, "american")
        await por_alta_sin_grupo(entorno, 2010, "american")
        await por_descubrir(monkeypatch, 2010, "american")
        mia = str(await sembrar_serie(entorno.banco, "Un título cualquiera", 1950, ComicTradition.OTHER))
        async with cliente() as c:
            r = await c.patch(f"/api/series/{mia}", json={"title": "Saga del Faro", "start_year": 2010, "tradition": "american"})
        assert r.status_code == 409
        assert await numero_de_series(entorno.banco) == antes + 1               # solo la serie «mía» de la prueba
        titulos = {s.title for s in await serie_en_bd(entorno.banco)}
        assert "Un título cualquiera" in titulos                                # PATCH no la renombró
