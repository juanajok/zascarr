# ruff: noqa: E501, F401, F811
"""U13c (#289) — aceptación de los criterios 5, 6 y 8 sobre una carpeta mixta.

Complementa `tests/test_u13c_carpeta_mixta_pg.py` (E1, D2, D1/E7). No implementa comportamiento nuevo ni cambia
contratos: acredita, con Postgres real, lo que el código vigente ya hace en los criterios que aún no tenían una
prueba propia con una carpeta de tres archivos (dos de la serie elegida y uno ajeno).

- CA5: confirmar solo los dos elegidos vincula esos dos; el excluido sigue accesible con su estado real; el
  comprobante y el resultado son los de siempre (una sola operación).
- CA6: volver o cancelar sin confirmar no vincula nada y no consume la preparación; tras vincular, repetir no
  vuelve a vincular y el resultado no ofrece un «deshacer» que no existe en este recorrido.
- CA8: con cero marcados no hay preparación ni botón de vincular, se dice por qué y una confirmación sin
  token no ejecuta nada.

Los criterios 1, 2, 3, 4 y 7 ya los acreditan otras pruebas (ver `docs/design/ui-u13/u13c-aceptacion-289.md`).
El criterio 9 (360 px, teclado, lector de pantalla) y el rendimiento siguen NOT RUN: requieren navegador real y Pi.
Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from tests.test_asistente_confirmar_pg import (
    confirmar,
    enviar as enviar_confirmacion,
    numero_de,
    operaciones,
    vinculados,
)
from tests.test_asistente_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    CLAVE,
    SECRETO,
    Pagina,
    _secreto_en_el_asistente,
    abrir,
    archivos,
    entorno,
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


async def issue_de(banco, archivo_id) -> object:
    async with banco.fabrica() as s:
        return (await s.execute(text("SELECT issue_id FROM files WHERE id = :i"), {"i": archivo_id})).scalar_one()


async def preparada(entorno) -> tuple[Pagina, object, dict]:
    """Carpeta mixta con los dos de la serie marcados y un token vigente; el ajeno queda sin marcar."""
    serie = await serie_de_prueba(entorno, "Flash", 1987)
    ids = await archivos(entorno, FLASH_1, FLASH_2, AJENO)
    p = await abrir(serie)
    p = await p.reenviar(marcar=[FLASH_1, FLASH_2])
    assert p.token is not None
    return p, serie, ids


# ── CA5 ─────────────────────────────────────────────────────────────────────────────────────────

async def test_ca5_confirmar_dos_de_tres_deja_al_ajeno_accesible_con_su_estado_real(entorno):
    p, serie, ids = await preparada(entorno)
    series_antes, disco_antes = await numero_de("series", entorno.banco), huella_disco(entorno.lib)

    r = await confirmar(p)

    # El resultado es el del servicio y cubre exactamente los dos elegidos.
    assert r.estado == "vinculados_todos" and r.total("vinculados") == 2
    assert await vinculados(entorno.banco) == 2 and await operaciones(entorno.banco) == 1
    assert await issue_de(entorno.banco, ids[AJENO]) is None
    assert await issue_de(entorno.banco, ids[FLASH_1]) is not None and await issue_de(entorno.banco, ids[FLASH_2]) is not None
    # Sin efectos de más: ni series nuevas ni archivos movidos.
    assert await numero_de("series", entorno.banco) == series_antes and huella_disco(entorno.lib) == disco_antes

    # Los dos vinculados dejan de ser pendientes de la carpeta; el excluido sigue accesible en la revisión
    # y con su estado real: no vinculado, con su conflicto y marcable.
    q = await abrir(serie)
    assert [f.nombre for f in q.filas] == [AJENO]
    ajeno = q.fila(AJENO)
    assert ajeno.estado == "con_conflicto_de_carpeta" and ajeno.marcable and not ajeno.marcado
    assert q.token is None


# ── CA6 ─────────────────────────────────────────────────────────────────────────────────────────

async def test_ca6_volver_sin_confirmar_no_vincula_nada_y_no_consume_la_preparacion(entorno):
    p, serie, ids = await preparada(entorno)
    antes = (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib))

    # «Volver» o «cancelar»: la persona sale y regresa a la revisión sin pulsar «Vincular».
    nueva = await abrir(serie)

    assert nueva.token is None and not any(f.marcado for f in nueva.filas)
    assert await vinculados(entorno.banco) == 0 and await operaciones(entorno.banco) == 0
    assert (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib)) == antes
    # Lo aún válido se conserva: la preparación anterior sigue verificando hasta que caduca (D1).
    assert verificar_token_vinculacion(p.token, SECRETO).series_id == str(serie)


async def test_ca6_tras_vincular_repetir_no_vincula_otra_vez_ni_ofrece_deshacer(entorno):
    p, _serie, _ids = await preparada(entorno)

    primera = await confirmar(p)
    segunda = await confirmar(p)

    assert "ya se había aplicado antes" in segunda.visible and "ya se había aplicado antes" not in primera.visible
    assert primera.total("vinculados") == segunda.total("vinculados") == 2
    assert await vinculados(entorno.banco) == 2 and await operaciones(entorno.banco) == 1
    # Este recorrido no tiene operación inversa: el resultado no promete un «deshacer».
    for r in (primera, segunda):
        assert "deshacer" not in r.visible.lower() and "desvincular" not in r.visible.lower()


# ── CA8 ─────────────────────────────────────────────────────────────────────────────────────────

async def test_ca8_con_cero_marcados_no_hay_preparacion_y_se_explica(entorno):
    serie = await serie_de_prueba(entorno, "Flash", 1987)
    await archivos(entorno, FLASH_1, FLASH_2, AJENO)
    antes = (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib))

    p = await abrir(serie)

    assert p.total("marcados") == 0 and p.total("a_vincular") == 0
    assert p.token is None
    assert "No has marcado ningún archivo." in p.visible
    # No se ofrece vincular una selección vacía.
    assert 'class="vinculacion-confirmar"' not in p.t and "Listo para vincular" not in p.visible
    assert (await estado_de_la_base(entorno.banco), huella_disco(entorno.lib)) == antes


async def test_ca8_confirmar_sin_token_no_ejecuta_ninguna_vinculacion_vacia(entorno):
    serie = await serie_de_prueba(entorno, "Flash", 1987)
    await archivos(entorno, FLASH_1, FLASH_2, AJENO)
    p = await abrir(serie)
    antes = await estado_de_la_base(entorno.banco)

    r = await enviar_confirmacion([("token", ""), ("cursor_actual", ""), ("pagina_desde", ""), ("pagina_hasta", "")])

    assert r.status_code in (200, 400, 422), r.text
    assert await vinculados(entorno.banco) == 0 and await operaciones(entorno.banco) == 0
    assert await estado_de_la_base(entorno.banco) == antes
