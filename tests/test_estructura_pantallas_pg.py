"""Estructura accesible de cada pantalla, pintada de verdad (benchmark-calidad-front, hallazgo 13).

Las pruebas de accesibilidad existentes miran CSS (contraste, tamaños, tokens) o plantillas sueltas;
ninguna pinta la página entera, así que no vieron que el estado vacío saltaba de `h1` a `h3` ni un
botón que decía solo «Ver». Esta pinta las pantallas del menú y las fichas contra Postgres real y
las revisa con `html.parser` de la stdlib (sin dependencias nuevas): un `h1` en `main`, sin saltos
de nivel, `id` únicos, campos con etiqueta, controles con nombre y sin textos de enlace vagos.
"""
from __future__ import annotations

import os
from html.parser import HTMLParser
from uuid import uuid4

import pytest

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import cliente, entorno  # noqa: F401
from zascarr.models import File, FileFormat, Issue, Series

#: Textos que no dicen a dónde llevan fuera de contexto (MDN, «Use descriptive link text»).
VAGOS = {"ver", "aquí", "aqui", "más", "mas", "leer más", "pulsa aquí", "clic aquí"}
CAMPOS = {"input", "select", "textarea"}
SIN_ETIQUETA = {"hidden", "submit", "button", "reset", "image"}


class _Estructura(HTMLParser):
    """Recoge lo necesario para las comprobaciones; solo cuenta encabezados dentro de `main`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.encabezados: list[int] = []
        self.etiquetas_for: set[str] = set()
        self.campos: list[dict] = []
        self.controles: list[dict] = []
        self._en_main = 0
        self._en_label = 0
        self._abiertos: list[dict] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.append(a["id"])
        if tag == "main":
            self._en_main += 1
        if self._en_main and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.encabezados.append(int(tag[1]))
        if tag == "label":
            self._en_label += 1
            if a.get("for"):
                self.etiquetas_for.add(a["for"])
        if tag in CAMPOS and (tag != "input" or a.get("type", "text") not in SIN_ETIQUETA):
            self.campos.append({**a, "_tag": tag, "_en_label": bool(self._en_label)})
        if tag == "button" or (tag == "a" and "href" in a):
            control = {**a, "_tag": tag, "_texto": ""}
            self.controles.append(control)
            self._abiertos.append(control)
        if tag == "img" and self._abiertos and a.get("alt"):
            self._abiertos[-1]["_texto"] += a["alt"]

    def handle_endtag(self, tag):
        if tag == "main":
            self._en_main -= 1
        if tag == "label":
            self._en_label = max(0, self._en_label - 1)
        if tag in {"button", "a"} and self._abiertos:
            self._abiertos.pop()

    def handle_data(self, data):
        for control in self._abiertos:
            control["_texto"] += data


def _revisar(ruta: str, html: str) -> list[str]:
    p = _Estructura()
    p.feed(html)
    fallos = []
    if p.encabezados.count(1) != 1:
        fallos.append(f"{ruta}: {p.encabezados.count(1)} h1 dentro de main")
    for antes, despues in zip(p.encabezados, p.encabezados[1:], strict=False):
        if despues - antes > 1:
            fallos.append(f"{ruta}: salto de encabezado h{antes} → h{despues}")
    repetidos = sorted({i for i in p.ids if p.ids.count(i) > 1})
    if repetidos:
        fallos.append(f"{ruta}: id repetidos {repetidos}")
    for c in p.campos:
        etiquetado = (c["_en_label"] or c.get("aria-label") or c.get("aria-labelledby")
                      or (c.get("id") and c["id"] in p.etiquetas_for))
        if not etiquetado:
            fallos.append(f"{ruta}: {c['_tag']} «{c.get('name') or c.get('id')}» sin etiqueta")
    for c in p.controles:
        nombre = " ".join(c["_texto"].split()) or c.get("aria-label") or c.get("title")
        if not nombre:
            fallos.append(f"{ruta}: {c['_tag']} sin nombre ({c.get('href') or c.get('class')})")
        elif nombre.lower().rstrip(" →") in VAGOS and not c.get("aria-label"):
            fallos.append(f"{ruta}: {c['_tag']} con texto vago «{nombre}»")
    return fallos


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")
async def test_las_pantallas_tienen_una_estructura_accesible(entorno):  # noqa: F811
    sid, iid, fid = uuid4(), uuid4(), uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Estructura", start_year=1999, total_issues=3))
        await s.flush()
        s.add(Issue(id=iid, series_id=sid, issue_number="1", sort_order=1.0))
        await s.flush()
        s.add(File(id=fid, issue_id=iid, file_path=f"/tmp/{uuid4()}-1.cbz", file_name="1.cbz",
                   file_format=FileFormat.CBZ, metadata_={}))
        s.add(File(id=uuid4(), file_path=f"/tmp/{uuid4()}-suelto.cbz", file_name="suelto.cbz",
                   file_format=FileFormat.CBZ, metadata_={}))
        await s.commit()

    rutas = [
        "/ui/", "/ui/pendientes", "/ui/pendientes/carpetas", "/ui/biblioteca",
        "/ui/biblioteca?modo=escaparate", "/ui/mejoras", "/ui/colecciones", "/ui/listas",
        "/ui/auditoria", "/ui/descubrir", "/ui/novedades", "/ui/wishlist", "/estado", "/ui/arcos",
        f"/ui/series/{sid}", f"/ui/series/{sid}/numero/{iid}", f"/ui/series/{sid}/editar",
        "/ui/no-existe",
    ]
    fallos: list[str] = []
    async with cliente() as c:
        for ruta in rutas:
            r = await c.get(ruta)
            assert r.status_code in (200, 404), (ruta, r.status_code)
            fallos += _revisar(ruta, r.text)
    assert not fallos, "\n".join(fallos)


def test_el_revisor_detecta_lo_que_debe():
    """El revisor no es una red rota: cada regla salta con su caso."""
    malo = ('<main><h1>T</h1><h3>Salto</h3><input name="q"><a href="/x">Ver</a>'
            '<button></button><p id="a"></p><p id="a"></p></main>')
    fallos = "\n".join(_revisar("/x", malo))
    for esperado in ("h1 → h3", "«q» sin etiqueta", "texto vago «Ver»", "button sin nombre",
                     "id repetidos ['a']"):
        assert esperado in fallos, esperado
    bueno = ('<main><h1>T</h1><h2>S</h2><label>Título <input name="t"></label>'
             '<a href="/x">Ver la serie</a><button aria-label="Cerrar">×</button></main>')
    assert _revisar("/x", bueno) == []


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")
async def test_un_error_de_validacion_se_muestra_y_no_da_500(entorno):  # noqa: F811
    """Regresión: tras el `rollback` de un envío con errores, la plantilla leía atributos caducados
    de la serie, el número o la saga fuera del contexto asíncrono (MissingGreenlet → 500). Cualquier
    error de «Editar la ficha», «Editar el número» o «Editar la saga» acababa en un error del
    servidor en vez de enseñar el mensaje junto al campo (hallado al probar el hallazgo 3)."""
    from zascarr.models import StoryArc

    sid, iid, aid = uuid4(), uuid4(), uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Con errores"))
        s.add(StoryArc(id=aid, title="Saga"))
        await s.flush()
        s.add(Issue(id=iid, series_id=sid, issue_number="1", sort_order=1.0))
        await s.commit()
    casos = [
        (f"/ui/series/{sid}/editar", {"title": "", "start_year": "hola"}, "title"),
        (f"/ui/series/{sid}/numero/{iid}/editar", {"issue_number": "", "title": "x"},
         "issue_number"),
        (f"/ui/arcos/{aid}/editar", {"title": ""}, "title"),
    ]
    async with cliente() as c:
        for ruta, datos, primero in casos:
            r = await c.post(ruta, data=datos)
            assert r.status_code == 200, (ruta, r.status_code)
            assert (f'name="{primero}" aria-invalid="true" aria-describedby="error-{primero}" '
                    "autofocus") in r.text, ruta
            assert f'id="error-{primero}"' in r.text, ruta
