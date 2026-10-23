# ruff: noqa: E501, F401, F811
"""U13c (#289) — aceptación de la carpeta mixta sobre el SHA de contraste.

Tres pruebas fijas, no temporales, que fijan las decisiones D1/D2 y los ejemplos E1/E7:

- E1: tres archivos, dos de la serie y uno ajeno; solo los dos entran en el token.
- D2: «Marcar todos» incluye al ajeno marcable, pero su conflicto sigue visible en la revisión.
- D1/E7: un token antiguo sigue siendo válido y la confirmación muestra SIEMPRE su serie de origen.

No implementan #289 ni cambian contratos: acreditan el comportamiento del código vigente en `b59b00c`.
Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os

import pytest

from tests.test_asistente_confirmar_pg import confirmar
from tests.test_asistente_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    SECRETO,
    Pagina,
    _secreto_en_el_asistente,
    abrir,
    archivos,
    entorno,
    enviar,
    estado_de_la_base,
    huella_disco,
    serie_de_prueba,
    url_bd,
)
from zascarr.services.tokens_revision import verificar_token_vinculacion

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

FLASH_1 = "Flash 01 (1987).cbz"
FLASH_2 = "Flash 02 (1987).cbz"
AJENO = "Green Lantern 99.cbz"


async def marcar_todos(p: Pagina) -> Pagina:
    """Lo que envía el navegador al pulsar «Marcar todos los que se pueden vincular»."""
    r = await enviar(p.formulario() + [("accion", "marcar_todos")])
    assert r.status_code == 200, r.text
    return Pagina(r.text, p.clave)


async def test_e1_tres_archivos_uno_ajeno_solo_dos_entran_en_el_token(entorno):
    serie = await serie_de_prueba(entorno, "Flash", 1987)
    ids = await archivos(entorno, FLASH_1, FLASH_2, AJENO)

    p = await abrir(serie)
    ajeno = p.fila(AJENO)
    assert ajeno.estado == "con_conflicto_de_carpeta" and ajeno.marcable

    antes = (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib))
    q = await p.reenviar(marcar=[FLASH_1, FLASH_2])

    assert q.token is not None
    firmado = verificar_token_vinculacion(q.token, SECRETO)
    assert sorted(a.id for a in firmado.archivos) == sorted([str(ids[FLASH_1]), str(ids[FLASH_2])])
    assert q.fila(FLASH_1).incluido and q.fila(FLASH_2).incluido
    assert not q.fila(AJENO).marcado and not q.fila(AJENO).incluido
    assert q.total("marcados") == 2 and q.total("a_vincular") == 2
    assert AJENO in q.visible and "Se puede vincular, pero hay señales que lo contradicen" in q.visible
    assert (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib)) == antes


async def test_d2_marcar_todos_incluye_al_ajeno_marcable_y_conserva_su_conflicto(entorno):
    serie = await serie_de_prueba(entorno, "Flash", 1987)
    ids = await archivos(entorno, FLASH_1, FLASH_2, AJENO)

    q = await marcar_todos(await abrir(serie))

    # D2: el masivo incluye al ajeno porque es marcable; la protección es la revisión manual.
    assert all(q.fila(n).marcado and q.fila(n).incluido for n in (FLASH_1, FLASH_2, AJENO))
    assert q.total("marcados") == 3 and q.total("a_vincular") == 3
    firmado = verificar_token_vinculacion(q.token, SECRETO)
    assert sorted(a.id for a in firmado.archivos) == sorted(str(i) for i in ids.values())

    # D2: el conflicto no desaparece al marcar; la fila y el detalle lo siguen diciendo.
    ajeno = q.fila(AJENO)
    assert ajeno.estado == "con_conflicto_de_carpeta"
    assert "Se puede vincular, pero hay señales que lo contradicen" in ajeno.cuerpo
    assert "Qué dice la carpeta frente a esta serie" in ajeno.cuerpo


async def test_e7_serie_destino_visible_al_confirmar_un_token_antiguo(entorno):
    flash = await serie_de_prueba(entorno, "Flash", 1987)
    batman = await serie_de_prueba(entorno, "Batman", 1940)
    await archivos(entorno, FLASH_1, FLASH_2)

    p_flash = await abrir(flash)
    p_flash = await p_flash.reenviar(marcar=[FLASH_1])
    token_antiguo = p_flash.token
    assert token_antiguo is not None
    assert verificar_token_vinculacion(token_antiguo, SECRETO).series_id == str(flash)

    antes = await estado_de_la_base(entorno.banco)
    p_batman = await abrir(batman)
    assert p_batman.token is None and not any(f.marcado for f in p_batman.filas)
    assert await estado_de_la_base(entorno.banco) == antes

    # La preparación antigua no se invalida y su confirmación sigue mostrando Flash, no Batman.
    assert "Serie elegida" in p_flash.visible and "Flash (1987)" in p_flash.visible
    assert "quedarán vinculados a «Flash»" in p_flash.visible
    r = await confirmar(p_flash)
    assert r.estado == "vinculados_todos"
    assert "Serie" in r.visible and "Flash (1987)" in r.visible
    assert "Batman" not in r.visible
