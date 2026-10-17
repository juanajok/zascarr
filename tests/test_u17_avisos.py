# ruff: noqa: E501
"""U17 (#204): leer los avisos y el texto legal sin esfuerzo. Regresiones escritas ANTES del código.

Criterios de la tarjeta → clase:
| # | Criterio | Clase |
|---|---|---|
| 1 | Un texto de más de una línea va en caja normal y sin giro; las mayúsculas y el giro, solo para rótulos de ≤ 3 palabras | `TestParrafoNoEsRotulo` |
| 2 | El aviso legal corresponde a la pantalla (Ajustes no habla de «añadir una serie aquí») | `TestAvisoEnSuPantalla` |
| 3 | Decisión (b) del 2026-10-15: frase visible, no plegada, con enlace a «Aviso legal» | `TestFraseVisibleConEnlace` |
| — | `require_legal_acknowledgment` protege las MISMAS acciones (no se toca) | `TestLaAceptacionProtegeLoMismo` |

La medida real (qué se pinta en mayúsculas o girado, en Chrome, claro y oscuro, estrecho y escritorio) está en `docs/design/ui-u17/`.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.routing import APIRoute, APIRouter
from fastapi.testclient import TestClient

import zascarr.api
import zascarr.web
from zascarr.main import app
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1] / "src" / "zascarr"
CSS = (RAIZ / "static" / "web.css").read_text(encoding="utf-8")
SIN_COMENTARIOS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
PLANTILLAS = sorted((RAIZ / "web" / "templates").glob("*.html"))


def reglas(css: str) -> list[tuple[list[str], str]]:
    """(selectores, cuerpo) de cada regla, también las anidadas en `@media`."""
    return [([s.strip() for s in sel.split(",") if s.strip()], cuerpo)
            for sel, cuerpo in re.findall(r"([^{}@]+)\{([^{}]*)\}", css)]


def cuerpo_de(selector: str) -> list[str]:
    """Los cuerpos de las reglas cuyo selector es EXACTAMENTE `selector` (sin descendientes ni estados)."""
    return [c for sels, c in reglas(SIN_COMENTARIOS) if selector in sels]


def macro(tipo: str) -> str:
    plantilla = crear_templates().env.get_template("_legal_disclaimer.html")
    return str(plantilla.module.legal_disclaimer(tipo))


def visible(t: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", t).split())


# ── 1. Un párrafo no es un rótulo ───────────────────────────────────────────────────────────────

class TestParrafoNoEsRotulo:

    @pytest.mark.parametrize("selector", [".caption", ".legal-notice-warn"])
    def test_el_texto_largo_no_va_en_mayusculas_ni_girado(self, selector):
        """La didascalia pintaba en mayúsculas y girada (`rotate(-1.2deg)`) párrafos enteros: el aviso legal, los avisos de Estado y
        las notas de la ficha de serie. Un texto de más de una línea va en caja normal."""
        cuerpos = cuerpo_de(selector)
        assert cuerpos, f"falta la regla de {selector}"
        for c in cuerpos:
            assert "text-transform: uppercase" not in c, f"{selector}: mayúsculas en un párrafo"
            assert "rotate" not in c, f"{selector}: giro en un párrafo"
            assert "letter-spacing: .12em" not in c, f"{selector}: espaciado de rótulo en un párrafo"

    def test_el_rotulo_conserva_el_estilo_de_didascalia(self):
        """Las mayúsculas y el giro quedan para rótulos de ≤ 3 palabras, con su propia clase."""
        cuerpos = cuerpo_de(".rotulo")
        assert cuerpos, "falta la clase `.rotulo` para los rótulos cortos"
        todo = " ".join(cuerpos)
        assert "text-transform: uppercase" in todo and "rotate(-1.2deg)" in todo

    def test_todo_rotulo_de_las_plantillas_tiene_tres_palabras_o_menos(self):
        largos = []
        for p in PLANTILLAS:
            texto = p.read_text(encoding="utf-8")
            for m in re.finditer(r'<(\w+)[^>]*class="[^"]*\brotulo\b[^"]*"[^>]*>(.*?)</\1>', texto, re.S):
                contenido = re.sub(r"\{\{.*?\}\}", "X", m.group(2))           # una expresión Jinja cuenta como una palabra
                contenido = re.sub(r"\{%.*?%\}", "", contenido)
                palabras = len(re.sub(r"<[^>]+>", " ", contenido).split())
                if palabras > 3:
                    largos.append((p.name, palabras, contenido.strip()[:40]))
        assert largos == []

    def test_las_etiquetas_en_linea_ya_no_usan_la_clase_de_nota(self):
        """Los `<span class="caption">` eran etiquetas de 1-2 palabras (la fuente, la tradición): ahora son `.rotulo`."""
        con_span = [p.name for p in PLANTILLAS if re.search(r'<span class="caption', p.read_text(encoding="utf-8"))]
        assert con_span == []

    def test_las_notas_de_estado_van_en_caja_normal(self):
        """`#warnings.caption` del Estado enseñaba una ruta del contenedor en mayúsculas."""
        assert "text-transform: uppercase" not in " ".join(cuerpo_de(".caption"))
        assert not re.search(r"\.estado-warnings[^{}]*\{[^{}]*(uppercase|rotate)", SIN_COMENTARIOS)


# ── 2. El aviso, en su pantalla ─────────────────────────────────────────────────────────────────

class TestAvisoEnSuPantalla:

    def test_ajustes_no_habla_de_anadir_una_serie(self):
        r = TestClient(app).get("/ui/ajustes")
        assert r.status_code == 200
        v = visible(r.text)
        assert "Añadir una serie aquí" not in v
        assert 'class="legal-notice' in r.text                                   # el aviso sigue ahí

    def test_ajustes_habla_de_lo_que_se_hace_en_ajustes(self):
        v = visible(macro("ajustes"))
        assert "integraciones" in v and "responsable" in v
        assert "Añadir una serie" not in v

    def test_deseados_sigue_hablando_de_anadir_una_serie(self):
        """En Deseados el texto sí corresponde: no se cambia."""
        assert "Añadir una serie aquí" in visible(macro("wishlist"))

    def test_los_tipos_conocidos_no_cambian_de_nombre(self):
        for tipo in ("footer", "wishlist", "metadata"):
            assert macro(tipo).strip()

    def test_ajustes_usa_el_tipo_propio_y_no_el_de_deseados(self):
        fuente = (RAIZ / "web" / "templates" / "ajustes.html").read_text(encoding="utf-8")
        assert 'legal_disclaimer("ajustes")' in fuente and 'legal_disclaimer("wishlist")' not in fuente


# ── 3. Frase visible con enlace a «Aviso legal» (decisión (b), 2026-10-15) ──────────────────────

class _Plegados(HTMLParser):
    """Anota si el `<aside>`/`<p>` legal cae dentro de un `<details>` cerrado (plegado)."""

    def __init__(self) -> None:
        super().__init__()
        self.pila: list[str] = []
        self.dentro_de_details = False

    def handle_starttag(self, tag, attrs):
        self.pila.append(tag)
        if tag == "details":
            self.dentro_de_details = True


class TestFraseVisibleConEnlace:

    @pytest.mark.parametrize("tipo", ["footer", "wishlist", "ajustes"])
    def test_es_una_frase_visible_con_enlace_a_aviso_legal(self, tipo):
        h = macro(tipo)
        assert re.search(r'<a href="/legal">Aviso legal</a>', h), f"{tipo}: falta el enlace a «Aviso legal»"
        assert "<details" not in h and "hidden" not in h and 'class="sr"' not in h      # no se pliega ni se oculta
        assert len(visible(h).split()) >= 8                                             # es una frase, no solo un enlace

    def test_la_frase_de_ajustes_se_ve_en_la_pantalla_y_no_esta_plegada(self):
        t = TestClient(app).get("/ui/ajustes").text
        m = re.search(r'<aside class="legal-notice[^"]*">.*?</aside>', t, re.S)
        assert m and '<a href="/legal">Aviso legal</a>' in m.group(0)
        antes = t[:m.start()]
        assert antes.count("<details") == antes.count("</details>")                    # el aviso no cae dentro de un <details>

    def test_el_pie_de_toda_pantalla_sigue_enlazando_al_aviso_legal(self):
        t = TestClient(app).get("/ui/ajustes").text
        assert re.search(r'legal-notice-footer">.*?<a href="/legal">Aviso legal</a>', t, re.S)


# ── 4. La aceptación legal protege lo mismo ─────────────────────────────────────────────────────

def _acciones_protegidas() -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for paquete in (zascarr.web, zascarr.api):
        for m in pkgutil.iter_modules(paquete.__path__):
            modulo = importlib.import_module(f"{paquete.__name__}.{m.name}")
            for v in vars(modulo).values():
                if isinstance(v, APIRouter):
                    for r in v.routes:
                        if isinstance(r, APIRoute) and any(getattr(d, "dependency", None) is require_legal_acknowledgment for d in r.dependencies):
                            out.add((m.name, ",".join(sorted(r.methods - {"HEAD"})), r.path))
    return out


class TestLaAceptacionProtegeLoMismo:

    def test_las_acciones_de_riesgo_protegidas_son_las_de_siempre(self):
        """U17 no toca `require_legal_acknowledgment`: protege exactamente estas seis acciones (POST de Deseados y de la API)."""
        assert _acciones_protegidas() == {
            ("wishlist", "POST", "/ui/wishlist/anadir"),
            ("wishlist", "POST", "/ui/wishlist/{item_id}/reintentar"),
            ("wishlist", "POST", "/ui/wishlist/{item_id}/buscar-ahora"),
            ("wishlist", "POST", "/ui/wishlist/{item_id}/enviar-candidato"),
            ("wishlist", "POST", "/wishlist"),
            ("wishlist", "POST", "/wishlist/{item_id}/search"),
        }

    def test_ni_el_asistente_ni_el_texto_legal_estan_protegidos(self):
        """Tienen que seguir siendo alcanzables para poder aceptar o leer el aviso (docstring de `web/legal.py`)."""
        assert not any(m == "legal" for m, _, _ in _acciones_protegidas())
