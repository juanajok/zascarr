"""
tests/test_web_nombre_y_foco.py

U11 (#198): cada control de formulario dice qué pide y se ve cuándo tiene el foco.

Tres fallos medidos en la Pi el 2026-10-15 (`docs/design/auditoria-ui-2026-10-15.md`, M1 y M5):
  · el `:focus` de los buscadores quitaba el `outline` y dejaba solo una sombra que en tema oscuro
    mide 1,14:1 (WCAG 2.4.7 / 1.4.11 piden ≥ 3:1);
  · varios `input`/`select` se apoyaban en el placeholder como única etiqueta, y los 50
    buscadores de Por revisar se llamaban todos «Buscar serie…»;
  · el `.htmx-indicator` en reposo: `web.css` solo le ponía `opacity: 0`, que no lo saca del árbol
    de accesibilidad. En el navegador ya quedaba oculto porque htmx 4 inyecta su propia hoja con
    `visibility: hidden` (medido en el ensayo de U11); la regla propia quita esa dependencia.

Las etiquetas son `<label class="sr" for>` (el patrón del buscador de Inicio), no `aria-label`:
un `label` lo traducen los traductores del navegador y se puede hacer visible sin tocar el control.

ALCANCE: sin navegador (no se añade una dependencia de E2E, CLAUDE.md §8).
  · Se comprueban TODAS las plantillas, incluidos los fragmentos que HTMX inserta después.
  · Para cada intercambio HTMX que trae o sustituye controles en las pantallas de U11, se compone
    el DOM como lo deja htmx (`innerHTML` u `outerHTML` del destino) y se comprueba entero.
    Lo que esto NO ejercita es el propio htmx (disparadores, cabeceras): eso se verificó en
    navegador real contra el ensayo con Postgres real (PR #209).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from uuid import uuid4

import pytest

from tests.test_pendientes import FakeExecResult, FakeSession, use_fake_session
from tests.test_web_css_contraste import (
    FONDOS_DE_CONTEXTO,
    NO_TEXTO,
    PLANTILLAS,
    _reglas,
    _temas,
    contraste,
    resolver,
)
from zascarr.models import ComicTradition, File, FileFormat, Publisher, Series

SIN_NOMBRE_PROPIO = {"hidden", "submit", "button", "reset", "image"}
VACIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source",
          "track", "wbr"}


# ── lectura de controles y de su nombre accesible ─────────────────────────────────────────
class _Controles(HTMLParser):
    """Controles visibles y su nombre accesible, en el orden de cálculo del navegador:
    `aria-labelledby`, `aria-label`, `<label for>` (aunque venga después) y `<label>` envolvente.
    El placeholder NO cuenta: es lo que esta historia elimina como única etiqueta."""

    def __init__(self) -> None:
        super().__init__()
        self.texto_de_label: dict[str, str] = {}
        self.controles: list[tuple[int, dict[str, str | None], list[str]]] = []
        self._labels: list[tuple[str | None, list[str], list[int]]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "label":
            self._labels.append((a.get("for"), [], []))
        elif tag in ("input", "select", "textarea"):
            if tag == "input" and (a.get("type") or "text") in SIN_NOMBRE_PROPIO:
                return
            self.controles.append((self.getpos()[0], a, []))
            if self._labels:
                self._labels[-1][2].append(len(self.controles) - 1)

    def handle_data(self, data):
        for _, trozos, _ in self._labels:
            trozos.append(data)

    def handle_endtag(self, tag):
        if tag == "label" and self._labels:
            para, trozos, envueltos = self._labels.pop()
            texto = " ".join("".join(trozos).split())
            if para:
                self.texto_de_label[para] = texto
            for i in envueltos:
                self.controles[i][2].append(texto)

    def nombres(self) -> list[tuple[int, dict[str, str | None], str | None]]:
        salida = []
        for linea, a, envolventes in self.controles:
            nombre = (a.get("aria-labelledby") and f"#{a['aria-labelledby']}"
                      or a.get("aria-label")
                      or self.texto_de_label.get(a.get("id") or "")
                      or (envolventes[0] if envolventes else None))
            salida.append((linea, a, nombre or None))
        return salida


def _leer(html: str) -> _Controles:
    p = _Controles()
    p.feed(re.sub(r"\{#.*?#\}", "", html, flags=re.S))
    return p


def controles_sin_nombre(html: str) -> list[str]:
    return [f"línea {linea}: <name={a.get('name')!r} placeholder={a.get('placeholder')!r}>"
            for linea, a, nombre in _leer(html).nombres() if not nombre]


def nombres(html: str, clase: str) -> list[str | None]:
    return [n for _, a, n in _leer(html).nombres() if clase in (a.get("class") or "").split()]


# ── composición del DOM tras un intercambio HTMX ──────────────────────────────────────────
class _Elemento(HTMLParser):
    """Localiza el elemento con un id: offsets de su etiqueta de apertura y de cierre."""

    def __init__(self, html: str, id_: str) -> None:
        super().__init__()
        self._id, self._lineas = id_, [0]
        for linea in html.splitlines(keepends=True):
            self._lineas.append(self._lineas[-1] + len(linea))
        self.apertura = self.fin_apertura = self.inicio_cierre = self.cierre = None
        self._profundidad = 0
        self.feed(html)

    def _offset(self) -> int:
        linea, col = self.getpos()
        return self._lineas[linea - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag in VACIOS:
            return
        if self.apertura is None and dict(attrs).get("id") == self._id:
            self.apertura = self._offset()
            self.fin_apertura = self.apertura + len(self.get_starttag_text())
            self._profundidad = 1
        elif self.apertura is not None and self.cierre is None:
            self._profundidad += 1

    def handle_endtag(self, tag):
        if tag in VACIOS or self.apertura is None or self.cierre is not None:
            return
        self._profundidad -= 1
        if self._profundidad == 0:
            self.inicio_cierre = self._offset()
            self.cierre = self.rawdata.index(">", self.inicio_cierre) + 1


def componer(pagina: str, destino: str, fragmento: str, swap: str) -> str:
    """El DOM que deja htmx al poner `fragmento` en `#destino` con `innerHTML` u `outerHTML`."""
    e = _Elemento(pagina, destino)
    assert e.cierre is not None, f"#{destino} no está en la página: ¿cambió el hx-target?"
    if swap == "innerHTML":
        return pagina[:e.fin_apertura] + fragmento + pagina[e.inicio_cierre:]
    assert swap == "outerHTML", swap
    return pagina[:e.apertura] + fragmento + pagina[e.cierre:]


class TestComponer:
    """Salvaguarda del propio compositor."""

    PAGINA = '<main><div id="a" class="x"><div><input></div><p>viejo</p></div><i>fin</i></main>'

    def test_inner(self):
        assert componer(self.PAGINA, "a", "<b>nuevo</b>", "innerHTML") == (
            '<main><div id="a" class="x"><b>nuevo</b></div><i>fin</i></main>')

    def test_outer(self):
        assert componer(self.PAGINA, "a", '<div id="a">nuevo</div>', "outerHTML") == (
            '<main><div id="a">nuevo</div><i>fin</i></main>')

    def test_destino_inexistente_falla(self):
        with pytest.raises(AssertionError, match="no está en la página"):
            componer(self.PAGINA, "no-existe", "", "innerHTML")


# ── 1. ningún control se apoya solo en el placeholder ─────────────────────────────────────
class TestNingunControlSinNombre:

    @pytest.mark.parametrize("plantilla", sorted(p.name for p in PLANTILLAS.glob("*.html")))
    def test_ningun_control_se_apoya_solo_en_el_placeholder(self, plantilla):
        """Regresión del mecanismo (M5): un placeholder desaparece al escribir y no es un nombre."""
        malos = controles_sin_nombre((PLANTILLAS / plantilla).read_text("utf-8"))
        cabecera = f"{plantilla}: controles sin label ni aria-label:\n  "
        assert not malos, cabecera + "\n  ".join(malos)

    @pytest.mark.parametrize("html", [
        '<input type="search" placeholder="Buscar serie…">',
        '<select name="tradition"><option>Todas</option></select>',
        '<textarea name="nota" placeholder="Nota"></textarea>',
        '<label for="otro">X</label><input id="este" type="text">',
        '<label for="q"></label><input id="q" type="search">',
    ])
    def test_el_detector_ve_un_control_sin_nombre(self, html):
        """Salvaguarda del propio test: si el detector no viera nada, la prueba pasaría vacía."""
        assert controles_sin_nombre(html)

    @pytest.mark.parametrize("html,nombre", [
        ('<input type="search" aria-label="Buscar serie">', "Buscar serie"),
        ('<label for="q">Título</label><input id="q" type="search">', "Título"),
        ('<input id="q" type="search"><label for="q">Título</label>', "Título"),
        ('<label>Título <input type="text"></label>', "Título"),
        ('<label class="sr" for="q">Serie de «a.cbz»</label><input id="q">', "Serie de «a.cbz»"),
    ])
    def test_el_detector_lee_el_nombre(self, html, nombre):
        assert not controles_sin_nombre(html)
        assert [n for _, _, n in _leer(html).nombres()] == [nombre]

    def test_los_botones_y_ocultos_no_necesitan_label(self):
        assert not controles_sin_nombre('<input type="hidden" name="x"><input type="submit">')

    @pytest.mark.parametrize("plantilla", ["_tarjeta_pendiente.html", "_resultados_serie.html",
                                           "biblioteca.html", "wishlist.html"])
    def test_las_etiquetas_de_u11_son_label_y_no_aria_label(self, plantilla):
        """Revisión de #209: `label` asociado antes que `aria-label` (traducible, visible si hace
        falta). Si alguien vuelve a `aria-label` en estas plantillas, esto lo detecta."""
        lineas = [n for n, linea in enumerate(
            (PLANTILLAS / plantilla).read_text("utf-8").splitlines(), 1) if "aria-label=" in linea]
        assert not lineas, (
            f"{plantilla}, línea(s) {lineas}: un campo se nombra con "
            '`<label class="sr" for="id">` + `id` único, no con `aria-label` '
            "(el `label` lo traduce el navegador y se puede hacer visible). "
            "`aria-label` solo con justificación explícita: "
            "si la hay, añade la excepción a esta prueba con su motivo.")


# ── 2. Por revisar: un nombre por archivo ─────────────────────────────────────────────────
def _archivo(nombre: str, con_sugerencia: bool = False) -> File:
    meta: dict = {"match_status": "unsorted"}
    if con_sugerencia:
        meta["candidates"] = [{"series_id": str(uuid4()), "title": "Paracuellos",
                               "start_year": 1977, "score": 0.8}]
    return File(id=uuid4(), file_path=f"/lib/_Unsorted/{nombre}", file_name=nombre,
                file_format=FileFormat.CBZ, metadata_=meta)


def _por_revisar(archivos: list[File]) -> str:
    with use_fake_session(FakeSession(exec_queue=[FakeExecResult(archivos)])) as client:
        r = client.get("/ui/pendientes")
    assert r.status_code == 200
    return r.text


class TestPorRevisar:

    def test_cada_buscador_dice_a_que_archivo_pertenece(self):
        archivos = [_archivo("Paracuellos 05.cbz"), _archivo("Paracuellos 06.cbz")]
        assert nombres(_por_revisar(archivos), "series-search") == [
            "Serie de «Paracuellos 05.cbz»", "Serie de «Paracuellos 06.cbz»"]

    def test_el_numero_de_la_sugerencia_tiene_nombre(self):
        html = _por_revisar([_archivo("Paracuellos 05.cbz", con_sugerencia=True)])
        assert nombres(html, "issue-input") == ["Número de «Paracuellos 05.cbz»"]
        assert not controles_sin_nombre(html)

    def test_los_ids_de_las_etiquetas_no_se_repiten(self):
        """Con `for`/`id`, un id repetido daría el nombre de OTRA tarjeta."""
        html = _por_revisar([_archivo("a.cbz", True), _archivo("b.cbz", True)])
        ids = re.findall(r'\bid="([^"]+)"', html)
        assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]


# ── 3. el DOM después de cada intercambio HTMX con controles ──────────────────────────────
def _series() -> list[Series]:
    return [Series(id=uuid4(), title=t, tradition=ComicTradition.TEBEO, start_year=y)
            for t, y in (("Paracuellos", 1977), ("Paracuellos (integral)", 2020))]


class TestTrasIntercambiosHtmx:
    """Criterio 5. Cada caso es un `hx-target`/`hx-swap` real de las plantillas; si cambia el
    destino, `componer` falla en vez de pasar en vacío."""

    def test_por_revisar_tras_buscar_serie(self):
        """`_tarjeta_pendiente.html`: hx-target="#resultados-<id>" hx-swap="innerHTML"."""
        archivo = _archivo("Paracuellos 05.cbz")
        pagina = _por_revisar([archivo])
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult(_series())])) as client:
            fragmento = client.get(f"/ui/pendientes/{archivo.id}/buscar-serie?q=para").text
        dom = componer(pagina, f"resultados-{archivo.id}", fragmento, "innerHTML")

        assert not controles_sin_nombre(dom)
        assert nombres(dom, "issue-input") == [
            "Número en «Paracuellos»", "Número en «Paracuellos (integral)»"]

    def test_por_revisar_tras_un_fallo_al_asignar(self):
        """`asignar` con error devuelve la TARJETA entera: hx-target="#card-<id>" outerHTML."""
        archivo = _archivo("Paracuellos 05.cbz", con_sugerencia=True)
        pagina = _por_revisar([archivo, _archivo("Otro 01.cbz")])
        sesion = FakeSession(get_map={(File, archivo.id): archivo})
        with use_fake_session(sesion) as client:
            r = client.post(f"/ui/pendientes/{archivo.id}/asignar",
                            data={"series_id": str(uuid4()), "issue_number": " "},
                            headers={"HX-Request": "true"})
        assert f'id="card-{archivo.id}"' in r.text, "ya no devuelve la tarjeta: revisa el swap"
        dom = componer(pagina, f"card-{archivo.id}", r.text, "outerHTML")

        assert not controles_sin_nombre(dom)
        assert nombres(dom, "series-search") == [
            "Serie de «Paracuellos 05.cbz»", "Serie de «Otro 01.cbz»"]

    def test_biblioteca_tras_filtrar(self):
        """`biblioteca.html`: el formulario de filtros pinta en #rejilla con innerHTML."""
        from tests.test_web_library import FakeExecResult as R
        from tests.test_web_library import FakeSession as S
        from tests.test_web_library import use_fake_session as usar
        editorial = Publisher(id=uuid4(), name="Bruguera")
        with usar(S([R([editorial]), R(0), R([])])) as client:
            pagina = client.get("/ui/biblioteca").text
        with usar(S([R(2), R(_series())])) as client:
            fragmento = client.get("/ui/biblioteca/resultados?tradition=tebeo").text
        dom = componer(pagina, "rejilla", fragmento, "innerHTML")

        assert "Paracuellos (integral)" in dom
        assert not controles_sin_nombre(dom)
        assert [n for _, _, n in _leer(dom).nombres()] == [
            "Buscar por título", "Tradición", "Editorial", "Buscar personaje", "Buscar saga"]

    def test_deseados_tras_buscar_serie(self):
        """`wishlist.html`: hx-target="#resultados-wishlist" innerHTML."""
        from tests.test_web_wishlist import FakeExecResult as R
        from tests.test_web_wishlist import FakeSession as S
        from tests.test_web_wishlist import use_fake_session as usar
        pagina = (PLANTILLAS / "wishlist.html").read_text("utf-8")
        with usar(S(exec_queue=[R(_series())])) as client:
            fragmento = client.get("/ui/wishlist/buscar-serie?q=para").text
        dom = componer(pagina, "resultados-wishlist", fragmento, "innerHTML")

        assert "Paracuellos" in dom
        assert not controles_sin_nombre(dom)
        assert nombres(dom, "series-search") == ["Buscar serie para añadir a Deseados"]


# ── 4. el foco se ve en los dos temas ─────────────────────────────────────────────────────
BUSCADORES = (".series-search", ".search-input", '.filter-bar input[type="search"]',
              ".filter-bar select")


def _anillo() -> tuple[float, str, str]:
    """(grosor en px, estilo, color) del `outline` de `:focus-visible`, en cualquier orden."""
    partes = next(d for s, d in _reglas() if s == ":focus-visible")["outline"].split()
    grosor = next(float(p[:-2]) for p in partes if re.fullmatch(r"[\d.]+px", p))
    estilo = next(p for p in partes if p in ("solid", "double", "dashed", "dotted"))
    color = next(p for p in partes if p.startswith(("var(", "#")))
    return grosor, estilo, color


class TestFocoVisible:

    def test_ningun_foco_quita_el_anillo_sin_sustituto(self):
        """Regresión del mecanismo (M1): `outline: none` en `:focus` anulaba el anillo global de
        `:focus-visible` (más específico) y dejaba una sombra de 1,14:1 en oscuro."""
        malos = [s for s, d in _reglas() if ":focus" in s
                 and re.fullmatch(r"none|0(px)?", d.get("outline", "x"))
                 and not d.get("outline-color") and "border-color" not in d]
        assert not malos, "reglas de foco que quitan el anillo:\n  " + "\n  ".join(malos)

    def test_el_anillo_global_es_continuo_y_de_al_menos_2_px(self):
        """WCAG 2.4.13 (referencia AAA) pide un área equivalente a un perímetro de 2 px."""
        grosor, estilo, _ = _anillo()
        assert grosor >= 2 and estilo in ("solid", "double")

    @pytest.mark.parametrize("tema", ["claro", "oscuro"])
    @pytest.mark.parametrize("fondo", FONDOS_DE_CONTEXTO)
    def test_el_anillo_contrasta_3_a_1_con_cualquier_fondo_de_contexto(self, tema, fondo):
        t = _temas()[tema]
        r = contraste(resolver(_anillo()[2], t), resolver(fondo, t))
        assert r >= NO_TEXTO, f"anillo sobre {fondo} [{tema}]: {r:.2f}:1"

    @pytest.mark.parametrize("buscador", BUSCADORES)
    def test_el_buscador_conserva_el_anillo(self, buscador):
        reglas = [d for s, d in _reglas()
                  if f"{buscador}:focus" in [x.strip() for x in s.split(",")]]
        assert reglas, f"{buscador}: sin regla de foco (¿se renombró?)"
        assert all("outline" not in d for d in reglas), reglas


# ── 5. el indicador de htmx no se anuncia en reposo ───────────────────────────────────────
class TestIndicadorSilencioso:

    def test_en_reposo_sale_del_arbol_de_accesibilidad(self):
        """`opacity: 0` lo oculta a la vista pero no a un lector de pantalla; `visibility` sí. No se
        confía en la hoja que inyecta htmx: depende de `includeIndicatorCSS` y de que cargue."""
        reposo = next(d for s, d in _reglas() if s == ".htmx-indicator")
        assert reposo["visibility"] == "hidden"

    def test_durante_la_peticion_se_ve_en_los_dos_casos_de_htmx(self):
        """htmx pone `.htmx-request` en el elemento que pide o en el `hx-indicator` mismo."""
        regla = next(d for s, d in _reglas()
                     if {".htmx-request .htmx-indicator", ".htmx-request.htmx-indicator"}
                     <= {x.strip() for x in s.split(",")})
        assert regla["visibility"] == "visible" and regla["opacity"] == "1"

    def test_ninguna_plantilla_vuelve_a_mostrarlo_en_linea(self):
        malos = [f.name for f in PLANTILLAS.glob("*.html")
                 if re.search(r'class="[^"]*htmx-indicator[^"]*"[^>]*style=', f.read_text("utf-8"))]
        assert not malos, malos
