# ruff: noqa: E501, F401, F811
"""UXA-12 (#1129): un número ocupado deja de ser un callejón sin salida, sobre Postgres real.

La revisión de la vinculación sigue siendo solo lectura: ahora dice QUÉ archivo ocupa el número, enlaza a ese
número, explica las salidas (corregir el número, dejarlo en Pendientes, comparar) y, si no hay nada marcable,
dice por qué los botones masivos están deshabilitados. Registrar «otra edición» queda fuera (#1250)."""
from __future__ import annotations

import asyncio
import html
import os
import re

import pytest

from tests.test_asistente_vinculacion_pg import (  # noqa: F401
    CLAVE,
    Pagina,
    _secreto_en_el_asistente,
    abrir,
    archivos,
    cliente,
    entorno,
    estado_de_la_base,
    huella_disco,
    sembrar_issue,
    serie_de_prueba,
    url_bd,
)
from tests.test_vinculacion_pg import ent  # noqa: F401
from zascarr.models import IssueFormat

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]


async def _numero_ocupado(entorno, serie, numero="2", ocupantes=("Otro 02.cbz",)):
    """Un `Issue` con archivos ya vinculados, y devuelve su id."""
    iid = await sembrar_issue(entorno.banco, serie, numero)
    for i, nombre in enumerate(ocupantes):
        await archivos(entorno, nombre, carpeta=f"Comics/Otra{i}", issue_id=iid)
    return iid


def _bloque(p: Pagina, nombre: str) -> str:
    fila = p.fila(nombre)
    m = re.search(rf'<li class="vinc-fila" data-id="{fila.id}".*?</li>', p.t, re.S)
    assert m, nombre
    return html.unescape(m.group(0))


class TestOcupado:

    async def test_el_numero_ocupado_dice_que_archivo_lo_ocupa_y_enlaza_a_ese_numero(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 02 (1987).cbz")
        iid = await _numero_ocupado(entorno, serie)
        p = await abrir(serie)
        fila = p.fila("Flash 02 (1987).cbz")
        assert fila.estado == "numero_ya_existe" and not fila.marcable
        bloque = _bloque(p, "Flash 02 (1987).cbz")
        assert 'class="vinc-ocupado"' in bloque
        assert "Ya está en este número" in bloque and "Otro 02.cbz" in bloque
        assert f'href="/ui/series/{serie}/numero/{iid}"' in bloque and "Ver ese número" in bloque

    async def test_el_numero_ocupado_explica_las_salidas_sin_prometer_otra_edicion(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 02 (1987).cbz")
        await _numero_ocupado(entorno, serie)
        bloque = _bloque(await abrir(serie), "Flash 02 (1987).cbz")
        assert "corregir el número" in bloque and "dejarlo en Pendientes" in bloque
        assert "comparar los dos archivos" in bloque
        assert "Registrarlo como otra edición todavía no se puede hacer desde aquí" in bloque
        assert 'name="numero:' in bloque                      # el campo para corregir el número sigue ahí

    async def test_con_varios_archivos_en_el_numero_dice_cuantos_mas(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 02 (1987).cbz")
        await _numero_ocupado(entorno, serie, ocupantes=("A 02.cbz", "B 02.cbz", "C 02.cbz"))
        bloque = _bloque(await abrir(serie), "Flash 02 (1987).cbz")
        assert "A 02.cbz" in bloque and "y 2 más" in bloque

    async def test_una_colision_de_edicion_tambien_muestra_al_ocupante(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash Omnigold 03.cbz")
        iid = await sembrar_issue(entorno.banco, serie, "3", formato=IssueFormat.SINGLE_ISSUE)
        await archivos(entorno, "Otro 03.cbz", carpeta="Comics/Otra", issue_id=iid)
        p = await abrir(serie)
        assert p.fila("Flash Omnigold 03.cbz").estado == "colision_de_edicion"
        bloque = _bloque(p, "Flash Omnigold 03.cbz")
        assert "Otro 03.cbz" in bloque and f'/numero/{iid}"' in bloque


class TestLibreYMixto:

    async def test_un_numero_libre_no_muestra_bloque_de_ocupado(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        p = await abrir(serie)
        assert 'class="vinc-ocupado"' not in p.t

    async def test_un_numero_con_issue_sin_archivos_no_cuenta_como_ocupado(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz")
        await sembrar_issue(entorno.banco, serie, "1")        # existe, pero vacío
        assert 'class="vinc-ocupado"' not in (await abrir(serie)).t

    async def test_mixto_solo_la_fila_ocupada_lleva_el_bloque_y_los_botones_masivos_siguen_activos(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        await _numero_ocupado(entorno, serie)
        p = await abrir(serie)
        assert 'class="vinc-ocupado"' in _bloque(p, "Flash 02 (1987).cbz")
        assert 'class="vinc-ocupado"' not in _bloque(p, "Flash 01 (1987).cbz")
        assert p.fila("Flash 01 (1987).cbz").marcable
        assert 'id="vinc-sin-candidatos"' not in p.t
        assert re.search(r'name="accion" value="marcar_todos"(?![^>]*disabled)[^>]*>Marcar todos', p.t)


class TestSinCandidatos:

    async def test_sin_nada_marcable_se_dice_por_que_y_los_botones_masivos_quedan_deshabilitados(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 02 (1987).cbz")
        await _numero_ocupado(entorno, serie)
        p = await abrir(serie)
        assert 'id="vinc-sin-candidatos"' in p.t
        assert "ninguno de los archivos de esta página se puede marcar" in html.unescape(p.t)
        assert re.search(r'name="accion" value="marcar_todos"[^>]*disabled', p.t)
        assert re.search(r'name="accion" value="desmarcar_todos"[^>]*disabled', p.t)


class TestSoloLecturaYConcurrencia:

    async def test_dos_revisiones_a_la_vez_dan_lo_mismo_y_no_cambian_nada(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 01 (1987).cbz", "Flash 02 (1987).cbz")
        await _numero_ocupado(entorno, serie)
        antes, disco = await estado_de_la_base(entorno.banco), huella_disco(entorno.lib)
        a, b = await asyncio.gather(abrir(serie), abrir(serie))
        assert _bloque(a, "Flash 02 (1987).cbz") == _bloque(b, "Flash 02 (1987).cbz")
        assert await estado_de_la_base(entorno.banco) == antes and huella_disco(entorno.lib) == disco

    async def test_si_otro_archivo_ocupa_el_numero_entre_dos_revisiones_la_segunda_lo_ve(self, entorno):
        serie = await serie_de_prueba(entorno)
        await archivos(entorno, "Flash 02 (1987).cbz")
        iid = await sembrar_issue(entorno.banco, serie, "2")
        assert 'class="vinc-ocupado"' not in (await abrir(serie)).t          # libre
        await archivos(entorno, "Llegó después 02.cbz", carpeta="Comics/Otra", issue_id=iid)
        p = await abrir(serie)                                              # ahora ocupado
        assert p.fila("Flash 02 (1987).cbz").estado == "numero_ya_existe"
        assert "Llegó después 02.cbz" in _bloque(p, "Flash 02 (1987).cbz")
