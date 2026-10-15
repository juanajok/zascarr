# ruff: noqa: E501, F401, F811
"""U12 (#199) — «Por revisar» a escala: saber cuántos pendientes hay y recorrerlos SIN que resolver tarjetas haga saltar
ninguno. Sobre Postgres real. Casos 1–8 de la ficha `docs/design/benchmark-U12-pendientes-escala.md`.

Contrato de producto (fijado por el revisor, PR #213) que estas pruebas demuestran:

  · orden total y estable;
  · resolver o ignorar tarjetas de la página actual NO hace que «Siguiente» omita pendientes;
  · se puede volver a los anteriores y regresar al inicio;
  · el rango que se muestra corresponde al conjunto ACTUAL, no a posiciones obsoletas.

La lista de pendientes es una COLA QUE SE VACÍA: ignorar o asignar una tarjeta la saca del conjunto. Una paginación por
`OFFSET` calculada antes de resolver salta filas después; estas pruebas fallan con ella.

| # | Ficha | Clase |
|---|---|---|
| 1 | El caso de la historia: «Mostrando 1–50 de 120» | `TestRangoYTotal` |
| 2 | Sin saltos al resolver | `TestSinSaltos` |
| 3 | Resolver todas las de la página y seguir | `TestSinSaltos` |
| 4 | Anterior e inicio | `TestAnteriorEInicio` |
| 5 | Empates de `imported_at` | `TestEmpates` |
| 6 | Importación concurrente | `TestImportacionConcurrente` |
| 7 | El rango es del conjunto actual (sin recargar) | `TestRangoActual` |
| 8 | Cursor inválido | `TestCursorInvalido` |

Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import html
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

import pytest
from sqlalchemy import text

from tests.test_vinculacion_previa_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    archivos,
    cliente,
    entorno,
    url_bd,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)"),
]

PAGINA = 50
BASE = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)


# ── ayudas ────────────────────────────────────────────────────────────────────────────────────
async def sembrar(entorno, n: int, *, empate: bool = False, prefijo: str = "Flash") -> list[str]:
    """`n` pendientes. Devuelve los ids en el ORDEN ESPERADO de la lista: `imported_at DESC, id DESC`.
    Con `empate`, todos comparten `imported_at` (como una adopción en una sola transacción)."""
    nombres = [f"{prefijo} {i:04d}.cbz" for i in range(1, n + 1)]
    ids = await archivos(entorno, *nombres, en_disco=False)
    async with entorno.banco.fabrica() as s:
        for i, nombre in enumerate(nombres):
            ts = BASE if empate else BASE + timedelta(minutes=i)
            await s.execute(text("UPDATE files SET imported_at = :t WHERE id = :i"), {"t": ts, "i": ids[nombre]})
        await s.commit()
    return await orden_esperado(entorno)


async def orden_esperado(entorno) -> list[str]:
    """El orden total que fija el contrato, calculado por la BD, de TODOS los pendientes actuales."""
    async with entorno.banco.fabrica() as s:
        filas = await s.execute(text(
            "SELECT id FROM files WHERE issue_id IS NULL AND review_dismissed IS FALSE "
            "AND metadata->>'match_status' = 'unsorted' ORDER BY imported_at DESC, id DESC"))
        return [str(r[0]) for r in filas]


async def total_en_bd(entorno) -> int:
    return len(await orden_esperado(entorno))


class Lista:
    """Una página de Por revisar ya pintada."""

    def __init__(self, t: str, status: int = 200):
        self.t, self.status = t, status
        self.ids = re.findall(r'<div class="pending-card" id="card-([0-9a-f-]{36})"', t)
        m = re.search(r'id="pend-rango"[^>]*data-desde="(\d+)" data-hasta="(\d+)" data-total="(\d+)"', t)
        self.desde, self.hasta, self.total = (int(m.group(i)) for i in (1, 2, 3)) if m else (None, None, None)

    def enlace(self, clase: str) -> str | None:
        m = re.search(rf'<a class="{clase}"[^>]*href="([^"]+)"', self.t)
        return html.unescape(m.group(1)) if m else None

    @property
    def siguiente(self) -> str | None:
        return self.enlace("pend-siguiente")

    @property
    def anterior(self) -> str | None:
        return self.enlace("pend-anterior")

    @property
    def inicio(self) -> str | None:
        return self.enlace("pend-inicio")

    def _clave(self, nombre: str) -> str | None:
        m = re.search(rf'<input type="hidden" name="{nombre}" value="([^"]*)"', self.t)
        return html.unescape(m.group(1)) if m else None

    @property
    def primero(self) -> str | None:
        """La clave `imported_at|id` del primer pendiente mostrado, como la entrega la página al refresco."""
        return self._clave("primero")

    @property
    def ultimo(self) -> str | None:
        return self._clave("ultimo")

    @property
    def visible(self) -> str:
        return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", self.t)).split())


async def pedir(ruta: str = "/ui/pendientes") -> Lista:
    async with cliente() as c:
        r = await c.get(ruta)
    return Lista(r.text, r.status_code)


async def ignorar(ids: list[str]) -> None:
    async with cliente() as c:
        for i in ids:
            r = await c.post(f"/ui/pendientes/{i}/ignorar", headers={"HX-Request": "true"})
            assert r.status_code == 200, r.text


# ── 1. El caso de la historia ─────────────────────────────────────────────────────────────────
class TestRangoYTotal:

    async def test_la_primera_pagina_dice_cuantos_hay_y_ofrece_siguiente(self, entorno):
        orden = await sembrar(entorno, 120)
        p = await pedir()
        assert p.ids == orden[:PAGINA]
        assert (p.desde, p.hasta, p.total) == (1, 50, 120)
        assert "Mostrando 1–50 de 120" in p.visible
        assert p.siguiente and not p.anterior and not p.inicio

    async def test_se_recorre_toda_la_cola_pagina_a_pagina(self, entorno):
        orden = await sembrar(entorno, 120)
        vistos, ruta, rangos = [], "/ui/pendientes", []
        for _ in range(5):
            p = await pedir(ruta)
            vistos += p.ids
            rangos.append((p.desde, p.hasta, p.total))
            if not p.siguiente:
                break
            ruta = p.siguiente
        assert vistos == orden
        assert rangos == [(1, 50, 120), (51, 100, 120), (101, 120, 120)]
        assert not p.siguiente and p.anterior and p.inicio

    async def test_el_total_es_el_de_la_base_con_el_mismo_filtro(self, entorno):
        await sembrar(entorno, 7)
        assert (await pedir()).total == await total_en_bd(entorno) == 7

    async def test_sin_pendientes_no_hay_rango_ni_enlaces_y_lo_dice(self, entorno):
        p = await pedir()
        assert p.ids == [] and p.siguiente is None and p.anterior is None
        assert "Nada pendiente" in p.visible


# ── 2 y 3. Sin saltos al resolver ─────────────────────────────────────────────────────────────
class TestSinSaltos:

    async def test_resolver_tarjetas_de_la_pagina_no_hace_que_siguiente_salte_pendientes(self, entorno):
        """EL CONTRATO. Se abre la página, se guarda el enlace «Siguiente» tal como se renderizó, se ignoran 10
        tarjetas de la página y después se sigue ese enlace. Con `OFFSET 50` saldrían los elementos 61–110 y se
        omitirían los 51–60 (que siguen pendientes); con un cursor salen exactamente los 51–100."""
        orden = await sembrar(entorno, 120)
        p1 = await pedir()
        siguiente = p1.siguiente
        resueltos = p1.ids[10:20]
        await ignorar(resueltos)
        p2 = await pedir(siguiente)
        assert p2.ids == orden[50:100]
        vistos_o_resueltos = set(p1.ids)
        pendientes_sin_ver = [i for i in await orden_esperado(entorno) if i not in vistos_o_resueltos]
        assert p2.ids == pendientes_sin_ver[:PAGINA], "«Siguiente» omitió algún pendiente"

    async def test_resolver_todas_las_de_la_pagina_y_seguir_funciona_porque_el_cursor_es_una_clave(self, entorno):
        orden = await sembrar(entorno, 120)
        p1 = await pedir()
        siguiente = p1.siguiente
        await ignorar(p1.ids)                                   # las 50 desaparecen del conjunto
        p2 = await pedir(siguiente)
        assert p2.ids == orden[50:100]
        assert (p2.desde, p2.hasta, p2.total) == (1, 50, 70)    # el rango es el del conjunto ACTUAL

    async def test_ni_se_repite_ni_se_omite_nada_al_recorrer_resolviendo_sobre_la_marcha(self, entorno):
        """Recorrido completo, ignorando cada tercera tarjeta de cada página antes de seguir."""
        orden = await sembrar(entorno, 120)
        ruta, vistos, resueltos = "/ui/pendientes", [], set()
        while ruta:
            p = await pedir(ruta)
            vistos += p.ids
            a_resolver = p.ids[::3]
            await ignorar(a_resolver)
            resueltos |= set(a_resolver)
            ruta = p.siguiente
        assert vistos == orden, "se repitió u omitió algún pendiente"
        assert len(vistos) == len(set(vistos))
        assert sorted(await orden_esperado(entorno)) == sorted(set(orden) - resueltos)


# ── 4. Anterior e inicio ──────────────────────────────────────────────────────────────────────
class TestAnteriorEInicio:

    async def test_anterior_devuelve_los_50_inmediatamente_anteriores_en_su_orden(self, entorno):
        orden = await sembrar(entorno, 150)
        p3 = await pedir((await pedir((await pedir()).siguiente)).siguiente)
        assert p3.ids == orden[100:150]
        p2 = await pedir(p3.anterior)
        assert p2.ids == orden[50:100]
        assert (p2.desde, p2.hasta, p2.total) == (51, 100, 150)
        p1 = await pedir(p2.anterior)
        assert p1.ids == orden[:50] and not p1.anterior

    async def test_anterior_con_resueltos_devuelve_solo_lo_pendiente_sin_duplicar(self, entorno):
        orden = await sembrar(entorno, 120)
        p1 = await pedir()
        p2 = await pedir(p1.siguiente)
        await ignorar(p1.ids[:5])                               # 5 de la primera página ya no están
        atras = await pedir(p2.anterior)
        assert atras.ids == orden[5:50]
        assert len(atras.ids) == len(set(atras.ids))
        assert (atras.desde, atras.hasta, atras.total) == (1, 45, 115)

    async def test_inicio_vuelve_a_la_primera_pagina_desde_cualquier_sitio(self, entorno):
        orden = await sembrar(entorno, 120)
        p3 = await pedir((await pedir((await pedir()).siguiente)).siguiente)
        assert p3.inicio
        assert (await pedir(p3.inicio)).ids == orden[:50]


# ── 5. Empates ────────────────────────────────────────────────────────────────────────────────
class TestEmpates:

    async def test_con_el_mismo_imported_at_las_paginas_son_disjuntas_y_exhaustivas(self, entorno):
        """Una adopción registra muchos archivos en UNA transacción: `now()` es la misma marca para todos."""
        orden = await sembrar(entorno, 60, empate=True)
        assert orden == sorted(orden, reverse=True), "el desempate es por id descendente"
        p1 = await pedir()
        p2 = await pedir(p1.siguiente)
        assert p1.ids + p2.ids == orden
        assert not set(p1.ids) & set(p2.ids)
        assert (p2.desde, p2.hasta, p2.total) == (51, 60, 60)

    async def test_el_orden_se_repite_igual_en_cada_carga(self, entorno):
        await sembrar(entorno, 60, empate=True)
        assert (await pedir()).ids == (await pedir()).ids


# ── 6. Importación concurrente ────────────────────────────────────────────────────────────────
class TestImportacionConcurrente:

    async def test_lo_que_llega_despues_no_desplaza_ni_hace_saltar_lo_que_se_recorria(self, entorno):
        orden = await sembrar(entorno, 120)
        p1 = await pedir()
        siguiente = p1.siguiente
        nuevos = await archivos(entorno, *(f"Nuevo {i}.cbz" for i in range(5)), en_disco=False)
        async with entorno.banco.fabrica() as s:               # llegan «ahora»: por delante de todo lo anterior
            await s.execute(text("UPDATE files SET imported_at = :t WHERE file_name LIKE 'Nuevo %'"),
                            {"t": BASE + timedelta(days=1)})
            await s.commit()
        p2 = await pedir(siguiente)
        assert p2.ids == orden[50:100]                          # lo que seguía, intacto
        assert (p2.desde, p2.hasta, p2.total) == (56, 105, 125)  # 5 nuevos delante: el rango lo refleja
        inicio = await pedir()
        assert set(inicio.ids[:5]) == {str(i) for i in nuevos.values()}


# ── 7. El rango es del conjunto actual, sin recargar ──────────────────────────────────────────
class TestRangoActual:

    async def test_el_fragmento_de_rango_se_recalcula_sobre_el_conjunto_actual(self, entorno):
        await sembrar(entorno, 120)
        p1 = await pedir()
        await ignorar(p1.ids[10:20])
        primero, ultimo = p1.primero, p1.ultimo
        assert primero and ultimo
        async with cliente() as c:
            r = await c.get("/ui/pendientes/rango", params={"primero": primero, "ultimo": ultimo})
        assert r.status_code == 200
        f = Lista(r.text)
        assert (f.desde, f.hasta, f.total) == (1, 40, 110)
        assert f.total == await total_en_bd(entorno)

    async def test_ignorar_devuelve_el_gancho_que_refresca_el_rango_sin_recargar(self, entorno):
        await sembrar(entorno, 3)
        p = await pedir()
        async with cliente() as c:
            r = await c.post(f"/ui/pendientes/{p.ids[0]}/ignorar", headers={"HX-Request": "true"})
        assert "/ui/_nav/estado" in r.text                      # el menú, como siempre
        assert 'hx-get="/ui/pendientes/rango"' in r.text and 'hx-include="#pend-clave"' in r.text
        assert 'hx-target="#pend-rango"' in r.text

    async def test_la_pagina_lleva_las_claves_que_necesita_el_refresco(self, entorno):
        await sembrar(entorno, 3)
        t = (await pedir()).t
        assert re.search(r'<div id="pend-clave"[^>]*hidden', t)
        assert 'name="primero"' in t and 'name="ultimo"' in t


# ── 8. Cursor inválido ────────────────────────────────────────────────────────────────────────
class TestCursorInvalido:

    @pytest.mark.parametrize("params", [
        {"despues": "esto-no-es-un-cursor"},
        {"antes": "2026-13-45T99:99:99|no-uuid"},
        {"despues": "2026-10-01T12:00:00+00:00|00000000-0000-0000-0000-000000000000|extra"},
        {"despues": "x" * 5000},
        {"despues": f"2026-10-01T12:00:00+00:00|{UUID(int=1)}", "antes": f"2026-10-01T12:00:00+00:00|{UUID(int=2)}"},
    ])
    async def test_un_cursor_que_no_vale_cae_en_la_primera_pagina_sin_error(self, entorno, params):
        orden = await sembrar(entorno, 60)
        p = await pedir("/ui/pendientes?" + urlencode(params))
        assert p.status == 200
        assert p.ids == orden[:PAGINA]
        assert (p.desde, p.hasta, p.total) == (1, 50, 60)
        assert not p.anterior
