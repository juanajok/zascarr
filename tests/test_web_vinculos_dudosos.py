# ruff: noqa: E501, UP017
"""BL-VINC1 C18–C20, C22 y C23: el bloque «Vínculos dudosos» de Duplicados, sin Postgres.

El servicio se sustituye por un informe fijo (`informe_vigente`) y la búsqueda por una que espera: la
plantilla solo pinta lo que recibe (R9).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

import httpx
import pytest

from tests.test_web_auditoria import FakeSession
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import tareas, vinculos_dudosos
from zascarr.services.vinculos_dudosos import (
    EvidenciaMezcla,
    Informe,
    Lote,
    Marcado,
    Motivo,
    SerieMezclada,
)

RUTA = "/ui/auditoria/vinculos-dudosos"
CUANDO = datetime(2026, 11, 27, 10, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    vinculos_dudosos.reiniciar_para_pruebas()
    tareas._reset_para_pruebas()

    async def _get_db():
        yield FakeSession()
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)
    vinculos_dudosos.reiniciar_para_pruebas()
    tareas._reset_para_pruebas()


def _informe() -> Informe:
    corps = Lote(
        carpeta="/media/library/DC/Green Lantern Corps Vol. 3", serie_id="s-gl", serie_titulo="Green Lantern",
        archivos=[Marcado(archivo_id="f-1", issue_id="i-1", nombre="Green Lantern Corps 001.cbz", numero="1", orden=1.0,
                          motivos=[Motivo("otra_serie", "El nombre encaja con «Green Lantern Corps Vol. 3»"),
                                   Motivo("otro_titulo", "Comparte el #1 con tebeos de otro título")],
                          serie_mezcla=True)],
        destino_id="s-glc3", destino_titulo="Green Lantern Corps Vol. 3", destino_sin_numeros=True)
    lemire = Lote(
        carpeta="/media/library/DC/Animal Man (2012)", serie_id="s-am", serie_titulo="ANIMAL MAN",
        archivos=[Marcado(archivo_id="f-2", issue_id="i-2", nombre="Animal Man 001.cbz", numero="1", orden=1.0,
                          motivos=[Motivo("anio", "La carpeta dice 2012; la serie empieza en 1989")])])
    mezcla = SerieMezclada(serie_id="s-sup", titulo="Superman", archivos=[
        EvidenciaMezcla(archivo_id="f-3", issue_id="i-3", nombre="Superman 001.cbz", numero="1", volumen=2,
                        carpeta="/media/library/DC/Superman Vol. 2"),
        EvidenciaMezcla(archivo_id="f-4", issue_id="i-4", nombre="Superman 001.cbz", numero="1", volumen=3,
                        carpeta="/media/library/DC/Superman Vol. 3"),
    ])
    return Informe(lotes=[corps, lemire], series_mezcladas=[mezcla], revisados=4506)


def _con_informe(monkeypatch, valor):
    async def _vigente(_db):
        return valor
    monkeypatch.setattr(vinculos_dudosos, "informe_vigente", _vigente)


def cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                             headers={"Origin": "http://localhost", "HX-Request": "true"})


def _texto(html: str) -> str:
    sin = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S)
    sin = re.sub(r"<[^>]+>", " ", sin)
    return re.sub(r"\s+", " ", sin)


@pytest.mark.asyncio
async def test_busqueda_en_segundo_plano_una_a_la_vez(monkeypatch):
    _con_informe(monkeypatch, None)
    liberar = asyncio.Event()
    llamadas = []

    async def _buscar_lenta(_fabrica):
        llamadas.append(1)
        await liberar.wait()
    monkeypatch.setattr(vinculos_dudosos, "_ejecutar_en_tarea", _buscar_lenta)

    async with cliente() as c:
        r1 = await c.post(RUTA)
        r2 = await c.post(RUTA)
    assert r1.status_code == r2.status_code == 200
    assert "Buscando vínculos dudosos…" in r1.text
    assert "Ya se están buscando" in r2.text
    assert 'hx-trigger="every 5s"' in r1.text
    await asyncio.sleep(0)
    assert llamadas == [1]
    liberar.set()
    assert tareas.TipoTarea("vinculos") and tareas.TITULOS["vinculos"] == "Buscando vínculos dudosos"


@pytest.mark.asyncio
async def test_bloque_en_duplicados(monkeypatch):
    _con_informe(monkeypatch, (_informe(), CUANDO))
    async with cliente() as c:
        pagina = await c.get("/ui/auditoria")
        r = await c.get(RUTA)
    assert f'hx-get="{RUTA}"' in pagina.text and 'hx-trigger="load"' in pagina.text
    html, texto = r.text, _texto(r.text)
    assert r.headers["cache-control"] == "no-store"
    assert re.search(r"<h2[^>]*>\s*Vínculos dudosos\s*</h2>", html)
    assert "Archivos que están en una serie, pero cuyo nombre o carpeta apuntan a otra." in texto
    boton = re.search(r"<button[^>]*>\s*Buscar vínculos dudosos\s*</button>", html)
    assert boton and "primary" not in boton.group(0)
    assert "2 archivos en 2 grupos. Primero, los que tienen más motivos." in texto
    assert "Además, 1 series mezclan volúmenes." in texto or "Además, 1 serie mezcla volúmenes." in texto
    assert "Esto es solo un informe. Corregir estos archivos llegará más adelante, por grupos." in texto
    # el lote con más motivos, primero, con su destino
    assert texto.index("Green Lantern Corps 001.cbz") < texto.index("Animal Man 001.cbz")
    assert "Podría ser «Green Lantern Corps Vol. 3», que aún no tiene números en tu biblioteca." in texto
    assert "Destino por verificar." in texto
    assert "Su serie mezcla volúmenes" in texto
    # R4b: un grupo por serie, con su desglose y los archivos plegados
    assert "Series que mezclan volúmenes" in texto
    assert "«Superman»: archivos del vol. 2 (1) y del vol. 3 (1)" in texto
    assert "vol. 3 · 1 archivo" in texto
    assert re.search(r"<details[^>]*>\s*<summary>\s*Ver los 2 archivos\s*</summary>", html)
    assert 'href="/ui/series/s-sup"' in html and 'href="/ui/series/s-gl"' in html


@pytest.mark.asyncio
async def test_el_informe_no_tiene_acciones_sobre_vinculos(monkeypatch):
    _con_informe(monkeypatch, (_informe(), CUANDO))
    async with cliente() as c:
        html = (await c.get(RUTA)).text
    formularios = re.findall(r"<form\b[^>]*>", html)
    assert all('hx-post="/ui/auditoria/vinculos-dudosos"' in f for f in formularios)    # solo el de buscar
    assert "deshacer" not in html and "desvincular" not in html.lower().replace("desvincular un archivo", "")
    assert "Desvincular un archivo no lo pasa a la serie buena: lo devuelve a «Por revisar»." in _texto(html)


@pytest.mark.parametrize(("valor", "esperado"), [
    (None, "Aún no se ha buscado."),
    ((Informe(lotes=[], series_mezcladas=[], revisados=10), CUANDO), "No hay vínculos dudosos."),
], ids=["sin_busqueda", "sin_resultados"])
@pytest.mark.asyncio
async def test_sin_busqueda_y_sin_resultados(monkeypatch, valor, esperado):
    _con_informe(monkeypatch, valor)
    async with cliente() as c:
        texto = _texto((await c.get(RUTA)).text)
    assert esperado in texto
    if valor is not None:
        assert "Última búsqueda:" in texto


@pytest.mark.asyncio
async def test_vocabulario_del_glosario(monkeypatch):
    _con_informe(monkeypatch, (_informe(), CUANDO))
    async with cliente() as c:
        r = await c.get(RUTA)
    assert r.status_code == 200 and "Vínculos dudosos" in r.text
    texto = _texto(r.text).lower()
    for prohibida in ("colección", "registro", "token", "lote", "ficha", "matcher", "auditoría"):
        assert prohibida not in texto, prohibida
