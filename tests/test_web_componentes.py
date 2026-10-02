"""
tests/test_web_componentes.py

V2 (Épica V): componentes CSS y macros Jinja. Cada macro se renderiza con TODAS sus variantes y se
comprueba el HTML resultante (clase, texto, ARIA, escape), que el vocabulario de estados vive en un
solo sitio, que las macros llegan a todas las plantillas sin tocar los routers y que las clases de
antes siguen funcionando (se retiran en V14, no antes).

El contraste de los colores de estos componentes lo cubre tests/test_web_css_contraste.py.
"""
from __future__ import annotations

import importlib
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from jinja2 import Environment

from zascarr.web.componentes import (
    ASPECTOS,
    MACROS,
    TIPOS_AVISO,
    aspecto,
    tipo_aviso,
)
from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
CSS_SIN_COMENTARIOS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"


@pytest.fixture(scope="module")
def env() -> Environment:
    return crear_templates().env


def render(env: Environment, fuente: str, **contexto) -> str:
    return env.from_string(fuente).render(**contexto)


class _Elementos(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elementos: list[tuple[str, dict[str, str | None]]] = []
        self.texto: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.elementos.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.texto.append(data)


def parsear(html: str) -> _Elementos:
    p = _Elementos()
    p.feed(html)
    return p


def clases(el: tuple[str, dict]) -> set[str]:
    return set((el[1].get("class") or "").split())


def texto(html: str) -> str:
    return " ".join("".join(parsear(html).texto).split())


# ── chip ──────────────────────────────────────────────────────────────────────────────────
class TestChip:

    @pytest.mark.parametrize("estado", list(ASPECTOS))
    def test_cada_estado_da_su_clase_y_su_icono(self, env, estado):
        html = render(env, '{{ chip(estado, "Texto") }}', estado=estado)
        chip = parsear(html).elementos[0]
        asp = ASPECTOS[estado]

        assert chip[0] == "span" and "chip" in clases(chip)
        assert (asp.clase in clases(chip)) if asp.clase else (clases(chip) == {"chip"})
        assert "Texto" in texto(html)
        if asp.icono:
            icono = parsear(html).elementos[1]
            assert icono[1].get("aria-hidden") == "true"
            assert asp.icono in texto(html)
        else:
            assert len(parsear(html).elementos) == 1      # neutro: sin icono

    def test_el_estado_no_depende_solo_del_color(self, env):
        """Cada estado con matiz lleva un icono propio y distinto del resto."""
        iconos = [a.icono for a in ASPECTOS.values() if a.clase]
        assert all(iconos) and len(set(iconos)) == len(iconos)

    def test_un_estado_desconocido_falla_en_vez_de_pintarse_neutro(self, env):
        with pytest.raises(ValueError, match="desconocido"):
            render(env, '{{ chip("inventado", "x") }}')

    def test_el_texto_se_escapa(self, env):
        html = render(env, '{{ chip("ok", t) }}', t='<script>alert(1)</script>')
        assert "<script>" not in html and "&lt;script&gt;" in html

    def test_acepta_numeros(self, env):
        assert texto(render(env, '{{ chip("neutro", 0) }}')) == "0"


# ── aviso ─────────────────────────────────────────────────────────────────────────────────
class TestAviso:

    @pytest.mark.parametrize("tipo", list(TIPOS_AVISO))
    def test_cada_tipo_da_su_clase_y_su_rol(self, env, tipo):
        html = render(env, '{{ aviso(tipo, "Mensaje") }}', tipo=tipo)
        cont = parsear(html).elementos[0]
        t = TIPOS_AVISO[tipo]

        assert set(t.clase.split()) <= clases(cont)
        assert cont[1].get("role") == t.rol
        assert "Mensaje" in texto(html)

    def test_solo_warn_es_asertivo(self):
        asertivos = {k for k, v in TIPOS_AVISO.items() if v.rol == "alert"}
        assert asertivos == {"warn"}

    def test_la_nota_es_la_didascalia_de_siempre_y_sin_icono(self, env):
        html = render(env, '{{ aviso("nota", "x") }}')
        assert clases(parsear(html).elementos[0]) == {"caption"}
        assert "aria-hidden" not in html

    @pytest.mark.parametrize("tipo", [t for t, v in TIPOS_AVISO.items() if v.icono])
    def test_el_icono_acompana_al_color_y_se_oculta_al_lector(self, env, tipo):
        html = render(env, '{{ aviso(tipo, "x") }}', tipo=tipo)
        icono = next(e for e in parsear(html).elementos if "aviso-icono" in clases(e))
        assert icono[1].get("aria-hidden") == "true"
        assert TIPOS_AVISO[tipo].icono in texto(html)

    def test_con_call_conserva_el_marcado_del_contenido(self, env):
        html = render(env, '{% call aviso("info") %}Mira <a href="/x">esto</a>{% endcall %}')
        assert any(e[0] == "a" and e[1]["href"] == "/x" for e in parsear(html).elementos)

    def test_con_texto_plano_lo_escapa(self, env):
        html = render(env, '{{ aviso("warn", t) }}', t="<b>ojo</b>")
        assert "<b>" not in html and "&lt;b&gt;" in html

    def test_un_tipo_desconocido_falla(self, env):
        with pytest.raises(ValueError, match="desconocido"):
            render(env, '{{ aviso("rojo", "x") }}')


# ── grupo ─────────────────────────────────────────────────────────────────────────────────
class TestGrupo:

    def test_cabecera_con_titulo_recuento_y_contenido(self, env):
        html = render(env, '{% call grupo("Mi título", 3) %}<p id="dentro">cuerpo</p>{% endcall %}')
        els = parsear(html).elementos
        grupo = els[0]

        assert "group" in clases(grupo)
        assert grupo[1].get("role") == "group" and grupo[1].get("aria-label") == "Mi título"
        assert any(e[0] == "div" and "ghead" in clases(e) for e in els)
        assert any(e[0] == "h3" for e in els)
        assert any(e[1].get("id") == "dentro" for e in els)
        assert "3" in texto(html)

    def test_el_recuento_cero_se_muestra(self, env):
        """Un grupo con 0 elementos dice 0; no es lo mismo que no tener recuento."""
        assert "0" in texto(render(env, '{% call grupo("T", 0) %}{% endcall %}'))

    def test_sin_recuento_no_hay_chip(self, env):
        html = render(env, '{% call grupo("T") %}{% endcall %}')
        assert not any("chip" in clases(e) for e in parsear(html).elementos)

    def test_no_crea_un_punto_de_referencia_por_grupo(self, env):
        """`<section aria-label>` sería un landmark por grupo: ruido para un lector de pantalla."""
        assert "<section" not in render(env, '{% call grupo("T", 1) %}{% endcall %}')

    def test_el_titulo_se_escapa(self, env):
        html = render(env, '{% call grupo(t, 1) %}{% endcall %}', t='<i>x</i>')
        assert "<i>" not in html


# ── estado vacío ──────────────────────────────────────────────────────────────────────────
class TestEstadoVacio:

    def test_titulo_texto_y_accion(self, env):
        html = render(
            env, '{{ estado_vacio("Todo clasificado", "No queda nada.", ("Volver", "/ui/")) }}')
        els = parsear(html).elementos

        assert "empty-state" in clases(els[0])
        assert any(e[0] == "h3" for e in els)
        enlace = next(e for e in els if e[0] == "a")
        assert enlace[1]["href"] == "/ui/" and {"btn", "primary"} <= clases(enlace)
        assert "Volver" in texto(html) and "No queda nada." in texto(html)

    def test_sin_accion_no_hay_enlace(self, env):
        html = render(env, '{{ estado_vacio("Vacío", "Nada por aquí.") }}')
        assert not any(e[0] == "a" for e in parsear(html).elementos)

    def test_solo_titulo(self, env):
        html = render(env, '{{ estado_vacio("Vacío") }}')
        els = parsear(html).elementos
        assert [e[0] for e in els] == ["div", "h3"]

    def test_la_url_se_escapa_en_el_atributo_y_no_inyecta_atributos(self, env):
        peligrosa = '/a?b=1&c="2" onclick="x()'
        html = render(env, '{{ estado_vacio("T", none, ("x", u)) }}', u=peligrosa)
        enlace = next(e for e in parsear(html).elementos if e[0] == "a")
        assert enlace[1]["href"] == peligrosa            # el valor llega entero, como dato
        assert set(enlace[1]) == {"class", "href"}       # y no se coló ningún atributo nuevo


# ── progreso y región viva ────────────────────────────────────────────────────────────────
class TestProgresoYRegionViva:

    def test_progreso_es_un_progress_nativo_con_nombre(self, env):
        el = parsear(render(env, '{{ progreso(30, 100, "Leyendo archivos") }}')).elementos[0]
        assert el[0] == "progress" and "progress" in clases(el)
        assert el[1]["value"] == "30" and el[1]["max"] == "100"
        assert el[1]["aria-label"] == "Leyendo archivos"

    def test_region_viva_es_cortes_y_atomica(self, env):
        el = parsear(render(env, '{% call region_viva("resultado") %}ok{% endcall %}')).elementos[0]
        assert el[1]["id"] == "resultado"
        assert el[1]["aria-live"] == "polite" and el[1]["aria-atomic"] == "true"

    def test_region_viva_sin_contenido_existe_vacia(self, env):
        """Tiene que estar en la página ANTES de que cambie para que se anuncie el cambio."""
        html = render(env, '{{ region_viva("r") }}')
        assert 'aria-live="polite"' in html and texto(html) == ""

    def test_region_viva_con_contenido(self, env):
        assert texto(render(env, '{% call region_viva("r") %}hecho{% endcall %}')) == "hecho"


# ── registro: llegan a TODAS las plantillas sin tocar los routers ─────────────────────────
MODULOS_WEB = ["ajustes", "auditoria", "auth", "dashboard", "discovery", "estado", "legal",
               "library", "pendientes", "series", "wishlist"]


class TestRegistro:

    @pytest.mark.parametrize("nombre", MACROS)
    def test_cada_macro_esta_registrada(self, env, nombre):
        assert callable(env.globals[nombre])

    def test_todas_las_macros_declaradas_existen_en_la_plantilla(self):
        fuente = (PLANTILLAS / "_componentes.html").read_text(encoding="utf-8")
        definidas = set(re.findall(r"{%\s*macro\s+(\w+)\(", fuente))
        assert definidas == set(MACROS)

    @pytest.mark.parametrize("modulo", MODULOS_WEB)
    def test_cada_router_web_tiene_las_macros_en_su_entorno(self, modulo):
        """Cada router crea su propio Jinja2Templates (entornos independientes): si alguno no pasara
        por `crear_templates()`, sus plantillas no verían las macros."""
        mod = importlib.import_module(f"zascarr.web.{modulo}")
        entorno = getattr(mod, "templates", None)
        if entorno is None:
            pytest.skip(f"zascarr.web.{modulo} no usa Jinja2Templates")
        assert all(n in entorno.env.globals for n in MACROS)

    def test_los_ayudantes_estan_registrados_y_son_los_del_modulo(self, env):
        assert env.globals["aspecto"] is aspecto and env.globals["tipo_aviso"] is tipo_aviso


class TestSinColisiones:
    """Los nombres de las macros son globales: una plantilla o un router que use el mismo nombre
    como variable la taparía (o sería tapado) sin avisar."""

    NOMBRES = [*MACROS, "aspecto", "tipo_aviso"]

    #: Colisiones que YA existían, aceptadas a propósito y acotadas: no pueden crecer.
    #: {(fichero, nombre): motivo y cuándo se resuelve}
    CONOCIDAS = {
        ("ajustes.py", "aviso"):
            "pasa el aviso de contraseña justa (A11) a _ajustes_guardado.html como variable "
            "`aviso`, que tapa la macro `aviso` solo dentro de esa plantilla. Se renombra en V10 "
            "(Ajustes por objetivos), que es quien la migra.",
    }

    def test_ninguna_plantilla_redefine_un_nombre_de_macro(self):
        nombres = "|".join(self.NOMBRES)
        patron = re.compile(
            r"{%-?\s*(?:set\s+(?:" + nombres + r")\b|for\s+(?:" + nombres + r")\s+in\b)")
        malas = [f.name for f in PLANTILLAS.glob("*.html")
                 if f.name != "_componentes.html" and patron.search(f.read_text(encoding="utf-8"))]
        assert not malas, malas

    def test_ningun_router_pasa_una_variable_con_nombre_de_macro_salvo_las_conocidas(self):
        encontrados = set()
        for f in (RAIZ / "src" / "zascarr" / "web").glob("*.py"):
            for n in self.NOMBRES:
                if re.search(rf'["\']{n}["\']\s*:', f.read_text(encoding="utf-8")):
                    encontrados.add((f.name, n))
        assert encontrados == set(self.CONOCIDAS), (
            f"colisiones nuevas o resueltas: {encontrados ^ set(self.CONOCIDAS)}")

    def test_cada_colision_conocida_tiene_motivo(self):
        assert all(len(m) > 40 for m in self.CONOCIDAS.values())


class TestVocabularioUnico:
    """El estado → aspecto vive en web/componentes.py; las plantillas no lo repiten."""

    def test_el_vocabulario_es_el_de_la_maqueta(self):
        assert set(ASPECTOS) == {"neutro", "ok", "warn", "amber", "info"}
        assert set(TIPOS_AVISO) == {"nota", "info", "ok", "amber", "warn"}

    def test_la_plantilla_de_macros_no_lleva_iconos_ni_clases_de_matiz_propias(self):
        fuente = (PLANTILLAS / "_componentes.html").read_text(encoding="utf-8")
        for icono in {a.icono for a in ASPECTOS.values() if a.icono}:
            assert f">{icono}<" not in fuente, f"icono {icono!r} escrito en la plantilla"
        assert not re.search(r'class="[^"]*\b(ok|warn|amber|info)\b', fuente)


# ── CSS: cada variante que el vocabulario promete existe ──────────────────────────────────
def _selectores() -> list[str]:
    reglas = re.findall(r"([^{}@]+)\{([^{}]*)\}", CSS_SIN_COMENTARIOS)
    return [" ".join(s.split()) for s, _ in reglas]


def _lista_de_selectores() -> set[str]:
    return {x.strip() for s in _selectores() for x in s.split(",")}


class TestCssDeLosComponentes:

    @pytest.mark.parametrize("asp", [a.clase for a in ASPECTOS.values() if a.clase])
    @pytest.mark.parametrize("base", [".chip", ".hero-state"])
    def test_cada_matiz_existe_en_chip_y_hero_state(self, asp, base):
        assert f"{base}.{asp}" in _lista_de_selectores()

    @pytest.mark.parametrize("tipo", [t for t in TIPOS_AVISO if t != "nota"])
    def test_cada_tipo_de_aviso_tiene_su_regla(self, tipo):
        assert f".aviso.{tipo}" in _lista_de_selectores()

    @pytest.mark.parametrize("selector", [
        ".btn.primary", ".btn.ghost", ".btn.sm", ".btn.ghost:hover", ".card", ".chip", ".group",
        ".ghead", ".empty-state", ".aviso", ".hero-state", "progress.progress", ".toast",
        ".caption", "button[disabled]",
    ])
    def test_existe_el_componente(self, selector):
        assert selector in _lista_de_selectores()

    def test_btn_primary_comparte_regla_con_el_nombre_antiguo(self):
        regla = next(s for s in _selectores() if ".btn.primary" in s and ".btn-primary" in s)
        assert "button[type=\"submit\"]" in regla

    def test_el_boton_pequeno_conserva_los_40_px(self):
        """`.btn.sm` solo recorta el relleno: la altura mínima la fija la regla base de V1."""
        decl = next(d for s, d in re.findall(r"([^{}@]+)\{([^{}]*)\}", CSS_SIN_COMENTARIOS)
                    if " ".join(s.split()) == ".btn.sm")
        assert "min-height" not in decl
        base = next(d for s, d in re.findall(r"([^{}@]+)\{([^{}]*)\}", CSS_SIN_COMENTARIOS)
                    if " ".join(s.split()).startswith("button,") and "min-height" in d)
        assert "min-height: 40px" in base

    def test_el_aviso_temporal_se_desactiva_con_reducir_movimiento(self):
        bloque = re.search(r"@media \(prefers-reduced-motion: reduce\)\s*\{(.*?)\n\}", CSS, re.S)
        assert bloque and "animation: none !important" in bloque.group(1)
        assert "animation: toast-sale" in CSS and "@keyframes toast-sale" in CSS

    def test_el_foco_visible_se_conserva(self):
        assert ":focus-visible" in CSS and "outline: 3px solid var(--cyan-t)" in CSS


# ── compatibilidad: ninguna clase de antes desaparece ─────────────────────────────────────
CLASES_ANTERIORES_A_V2 = (
    "ajustes-actions", "ajustes-card", "ajustes-desc", "ajustes-error", "ajustes-grid",
    "ajustes-hint", "ajustes-ok", "assign-form", "audit-adoptar", "audit-block", "audit-count",
    "audit-detail", "audit-item", "audit-ok", "audit-path", "audit-resumen", "audit-why",
    "back-link", "brand", "btn", "btn-ignorar", "btn-logout", "btn-primary", "btn-reintentar",
    "btn-sugerencia", "candidato-detalle", "candidato-fila", "candidato-titulo",
    "candidatos-lista", "candidatos-vacio", "candidatos-wishlist", "caption", "content",
    "cover", "cover-missing", "dashboard", "detected", "discover", "discover-desc",
    "discovery-card", "discovery-card-actions", "discovery-card-body", "discovery-card-desc",
    "discovery-card-title", "discovery-list", "empty", "empty-state", "estado-bad",
    "estado-check-name", "estado-check-row", "estado-check-status", "estado-checks",
    "estado-dot", "estado-dot-sm", "estado-downloading", "estado-failed", "estado-imported",
    "estado-neutral", "estado-ok", "estado-retirado", "estado-searching", "estado-summary",
    "estado-summary-detail", "estado-summary-label", "estado-wanted", "estado-warn",
    "estado-warnings", "estado-warnings-title", "filename", "filter-bar",
    "filter-bar-secondary", "filter-search-box", "htmx-indicator", "htmx-request",
    "issue-chip", "issue-grid", "issue-input", "issue-missing", "issue-present",
    "legal-checkbox", "legal-form", "legal-full", "legal-notice", "legal-notice-footer",
    "legal-notice-info", "legal-notice-warn", "library-card", "library-card-body",
    "library-card-meta", "library-card-title", "library-grid", "login-content", "login-error",
    "login-form", "metric-card", "metric-delta", "metric-detail", "metric-label",
    "metric-value", "metric-warning", "metrics-grid", "nav-logout", "no-results",
    "page-current", "page-link", "pagination", "pending-body", "pending-card", "pending-grid",
    "politica-aviso", "politica-form", "politica-lista-corta", "politica-retirados-ahora",
    "politica-serie", "politica-veredicto", "search-form", "search-input", "section-header",
    "series-card", "series-cover", "series-grid", "series-header", "series-list",
    "series-meta", "series-name", "series-result-item", "series-results", "series-search",
    "series-title", "series-year", "site-footer", "subtitle", "suggestion", "suggestion-label",
    "suggestion-score", "topnav", "view-all", "visible", "wishlist-badge", "wishlist-list",
    "wishlist-motivo", "wishlist-row", "wishlist-title",
)


class TestCompatibilidad:

    def test_se_conocen_las_clases_anteriores(self):
        assert len(CLASES_ANTERIORES_A_V2) > 100

    def test_ninguna_clase_anterior_a_v2_desaparece(self):
        actuales = set(re.findall(r"\.([A-Za-z_][\w-]*)", CSS_SIN_COMENTARIOS))
        perdidas = [c for c in CLASES_ANTERIORES_A_V2 if c not in actuales]
        assert not perdidas, f"clases que desaparecen (se retiran en V14, no antes): {perdidas}"

    def test_las_plantillas_no_usan_clases_inexistentes_del_vocabulario_nuevo(self):
        """Salvo el uso ya existente de `.btn`, ninguna plantilla estrena aún los componentes."""
        nuevos = {"chip", "group", "ghead", "aviso", "hero-state", "toast", "region-viva"}
        usadas = set()
        for f in PLANTILLAS.glob("*.html"):
            if f.name == "_componentes.html":
                continue
            for valor in re.findall(r'class="([^"]+)"', f.read_text(encoding="utf-8")):
                usadas |= nuevos & set(valor.split())
        assert not usadas, f"V2 no migra pantallas; las usa alguna ya: {usadas}"
