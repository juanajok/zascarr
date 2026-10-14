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

ALCANCE: sin navegador. Las plantillas se comprueban TODAS (incluidos los fragmentos que HTMX
inserta después de la carga) y, para Por revisar, también el DOM compuesto tras el intercambio de
«Buscar serie». Se complementa con la verificación en navegador real (DoD de la tarjeta).
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


class _Controles(HTMLParser):
    """Recoge los controles visibles y si tienen nombre accesible (label, aria-label o
    aria-labelledby). Un `<label for>` cuenta aunque aparezca después del control."""

    def __init__(self) -> None:
        super().__init__()
        self.para: set[str] = set()
        self.controles: list[tuple[int, str, dict[str, str | None], bool]] = []
        self._dentro_de_label = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "label":
            self._dentro_de_label += 1
            if a.get("for"):
                self.para.add(a["for"])
        elif tag in ("input", "select", "textarea"):
            if tag == "input" and (a.get("type") or "text") in SIN_NOMBRE_PROPIO:
                return
            self.controles.append((self.getpos()[0], tag, a, self._dentro_de_label > 0))

    def handle_endtag(self, tag):
        if tag == "label":
            self._dentro_de_label = max(0, self._dentro_de_label - 1)


def nombre_accesible(a: dict[str, str | None], envuelto: bool, para: set[str]) -> str | None:
    if a.get("aria-label"):
        return a["aria-label"]
    if a.get("aria-labelledby"):
        return f"#{a['aria-labelledby']}"
    if envuelto or (a.get("id") and a["id"] in para):
        return "<label>"
    return None


def controles_sin_nombre(html: str) -> list[str]:
    p = _Controles()
    p.feed(re.sub(r"\{#.*?#\}", "", html, flags=re.S))
    return [f"línea {linea}: <{tag} name={a.get('name')!r} placeholder={a.get('placeholder')!r}>"
            for linea, tag, a, envuelto in p.controles
            if not nombre_accesible(a, envuelto, p.para)]


def nombres(html: str, clase: str) -> list[str]:
    p = _Controles()
    p.feed(html)
    return [nombre_accesible(a, env, p.para) or "" for _, _, a, env in p.controles
            if clase in (a.get("class") or "").split()]


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
    ])
    def test_el_detector_ve_un_control_sin_nombre(self, html):
        """Salvaguarda del propio test: si el detector no viera nada, la prueba pasaría vacía."""
        assert controles_sin_nombre(html)

    @pytest.mark.parametrize("html", [
        '<input type="search" aria-label="Buscar serie">',
        '<label for="q">Título</label><input id="q" type="search">',
        '<input id="q" type="search"><label for="q">Título</label>',
        '<label>Título <input type="text"></label>',
        '<input type="hidden" name="x"><input type="submit" value="Ir">',
    ])
    def test_el_detector_acepta_un_nombre_valido(self, html):
        assert not controles_sin_nombre(html)


# ── 2. Por revisar: un nombre por archivo, también tras el intercambio HTMX ────────────────
def _archivo(nombre: str, con_sugerencia: bool = False) -> File:
    meta: dict = {"match_status": "unsorted"}
    if con_sugerencia:
        meta["candidates"] = [{"series_id": str(uuid4()), "title": "Paracuellos",
                               "start_year": 1977, "score": 0.8}]
    return File(id=uuid4(), file_path=f"/lib/_Unsorted/{nombre}", file_name=nombre,
                file_format=FileFormat.CBZ, metadata_=meta)


class TestPorRevisar:

    def _pagina(self, archivos: list[File]) -> str:
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult(archivos)])) as client:
            r = client.get("/ui/pendientes")
        assert r.status_code == 200
        return r.text

    def test_cada_buscador_dice_a_que_archivo_pertenece(self):
        archivos = [_archivo("Paracuellos 05.cbz"), _archivo("Paracuellos 06.cbz")]
        assert nombres(self._pagina(archivos), "series-search") == [
            "Serie de «Paracuellos 05.cbz»", "Serie de «Paracuellos 06.cbz»"]

    def test_el_numero_de_la_sugerencia_tiene_nombre(self):
        html = self._pagina([_archivo("Paracuellos 05.cbz", con_sugerencia=True)])
        assert nombres(html, "issue-input") == ["Número de «Paracuellos 05.cbz»"]
        assert not controles_sin_nombre(html)

    def test_el_dom_tras_buscar_serie_no_tiene_controles_sin_nombre(self):
        """Criterio 5: el fragmento de «Buscar serie» se inserta en `#resultados-<id>` y trae sus
        propios campos «nº». Se compone el DOM como lo deja htmx (innerHTML) y se comprueba
        entero."""
        archivo = _archivo("Paracuellos 05.cbz")
        pagina = self._pagina([archivo])
        series = [Series(id=uuid4(), title=t, tradition=ComicTradition.TEBEO, start_year=y)
                  for t, y in (("Paracuellos", 1977), ("Paracuellos (integral)", 2020))]
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult(series)])) as client:
            fragmento = client.get(f"/ui/pendientes/{archivo.id}/buscar-serie?q=para").text
        destino = f'<div id="resultados-{archivo.id}" class="series-results">'
        assert destino in pagina, "cambió el destino del intercambio: actualiza esta prueba"
        compuesto = pagina.replace(destino, destino + fragmento, 1)

        assert not controles_sin_nombre(compuesto)
        assert nombres(compuesto, "issue-input") == [
            "Número en «Paracuellos»", "Número en «Paracuellos (integral)»"]


class TestBiblioteca:

    def test_los_filtros_tienen_nombre_aunque_haya_editoriales(self):
        from tests.test_web_library import FakeExecResult as R
        from tests.test_web_library import FakeSession as S
        from tests.test_web_library import use_fake_session as usar
        editorial = Publisher(id=uuid4(), name="Bruguera")
        with usar(S([R([editorial]), R(0), R([])])) as client:
            html = client.get("/ui/biblioteca").text
        assert "Bruguera" in html
        assert not controles_sin_nombre(html)


# ── 3. el foco se ve en los dos temas ─────────────────────────────────────────────────────
BUSCADORES = (".series-search", ".search-input", '.filter-bar input[type="search"]',
              ".filter-bar select")


class TestFocoVisible:

    def test_ningun_foco_quita_el_anillo_sin_sustituto(self):
        """Regresión del mecanismo (M1): `outline: none` en `:focus` anulaba el anillo global de
        `:focus-visible` (más específico) y dejaba una sombra de 1,14:1 en oscuro."""
        malos = [s for s, d in _reglas() if ":focus" in s
                 and re.fullmatch(r"none|0(px)?", d.get("outline", "x"))
                 and not d.get("outline-color") and "border-color" not in d]
        assert not malos, "reglas de foco que quitan el anillo:\n  " + "\n  ".join(malos)

    def test_el_anillo_global_es_de_3_px_con_color_de_texto(self):
        regla = next(d for s, d in _reglas() if s == ":focus-visible")
        assert regla["outline"] == "3px solid var(--cyan-t)"

    @pytest.mark.parametrize("tema", ["claro", "oscuro"])
    @pytest.mark.parametrize("fondo", FONDOS_DE_CONTEXTO)
    def test_el_anillo_contrasta_3_a_1_con_cualquier_fondo_de_contexto(self, tema, fondo):
        t = _temas()[tema]
        anillo = re.search(r"var\(--[\w-]+\)", next(
            d for s, d in _reglas() if s == ":focus-visible")["outline"]).group(0)
        r = contraste(resolver(anillo, t), resolver(fondo, t))
        assert r >= NO_TEXTO, f"anillo sobre {fondo} [{tema}]: {r:.2f}:1"

    @pytest.mark.parametrize("buscador", BUSCADORES)
    def test_el_buscador_conserva_el_anillo(self, buscador):
        reglas = [d for s, d in _reglas()
                  if f"{buscador}:focus" in [x.strip() for x in s.split(",")]]
        assert reglas, f"{buscador}: sin regla de foco (¿se renombró?)"
        assert all("outline" not in d for d in reglas), reglas


# ── 4. el indicador de htmx no se anuncia en reposo ───────────────────────────────────────
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
