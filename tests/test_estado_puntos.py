"""El estado no depende solo del color: puntos de /estado y chips de Deseados (deuda 1 de la revisión).

Medido (simulación de Machado, ΔE76): el verde y el rojo de los puntos y de los rellenos sólidos pasan de
~90 a 12-29 con deuteranopía y a 13-18 con protanopía; la luminosidad apenas los separa (1,03-1,28:1).
Los colores no se tocan: cada nivel lleva además el MISMO glifo que el chip de su color.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from zascarr.models import WishlistStatus
from zascarr.services.estado_deseo import ASPECTO_DE_DESEO, aspecto_de_deseo
from zascarr.web.componentes import ASPECTOS
from zascarr.web.iconos import ICONO_DE_PUNTO, ICONOS, TINTA_DEL_PUNTO, svg_de_punto
from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1] / "src" / "zascarr"
CSS = (RAIZ / "static" / "web.css").read_text(encoding="utf-8")
CSS_SIN_COMENTARIOS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)

#: Nivel del punto → aspecto del chip del MISMO color (verde ok, rojo warn, amarillo amber).
ASPECTO_DEL_NIVEL = {"ok": "ok", "bad": "warn", "warn": "amber"}
#: Glifo de texto de cada icono de punto: el que dibuja el chip de su color.
GLIFO_DEL_ICONO = {"ok": "✓", "aviso": "!", "pregunta": "?"}


def _reglas():
    return [(" ".join(s.split()), d) for s, d in re.findall(r"([^{}@]+)\{([^{}]*)\}", CSS_SIN_COMENTARIOS)]


class TestPuntosDeEstado:
    def test_cada_nivel_con_color_lleva_un_glifo_y_el_neutro_no(self):
        for nivel in ("ok", "warn", "bad"):
            regla = next(d for s, d in _reglas() if s == f".estado-dot.estado-{nivel}")
            assert re.search(r'background-image:\s*url\("/static/iconos/punto-[a-z]+\.svg"\)', regla), nivel
        neutro = next(d for s, d in _reglas() if s == ".estado-dot.estado-neutral")
        assert "url(" not in neutro

    def test_los_niveles_no_comparten_glifo(self):
        """Verde y rojo son justo los que se confunden: si compartieran glifo, el icono no ayudaría."""
        glifos = [next(d for s, d in _reglas() if s == f".estado-dot.estado-{n}") for n in ("ok", "warn", "bad")]
        urls = [re.search(r"url\(\"([^\"]+)\"\)", g).group(1) for g in glifos]
        assert len(set(urls)) == 3, urls

    @pytest.mark.parametrize("nivel,aspecto", sorted(ASPECTO_DEL_NIVEL.items()))
    def test_el_glifo_del_punto_es_el_del_chip_de_su_color(self, nivel, aspecto):
        """Un solo vocabulario: si cambia el icono de `ASPECTOS`, el punto tiene que seguirlo."""
        icono = ICONO_DE_PUNTO[nivel]
        assert ASPECTOS[aspecto].icono == GLIFO_DEL_ICONO[icono]
        regla = next(d for s, d in _reglas() if s == f".estado-dot.estado-{nivel}")
        assert f"/static/iconos/punto-{icono}.svg" in regla

    def test_los_ficheros_svg_salen_de_iconos_py_y_no_divergen(self):
        for icono in ICONO_DE_PUNTO.values():
            fichero = RAIZ / "static" / "iconos" / f"punto-{icono}.svg"
            assert fichero.read_text(encoding="utf-8") == svg_de_punto(icono), fichero.name
            assert icono in ICONOS

    def test_el_trazo_del_glifo_es_el_par_oscuro_fijo_y_no_lleva_codigo(self):
        for icono in ICONO_DE_PUNTO.values():
            svg = (RAIZ / "static" / "iconos" / f"punto-{icono}.svg").read_text(encoding="utf-8")
            assert f'stroke="{TINTA_DEL_PUNTO}"' in svg and TINTA_DEL_PUNTO == "#17171a"
            assert "<script" not in svg.lower() and not re.search(r"\son\w+\s*=", svg)

    def test_el_color_de_fondo_va_aparte_para_que_la_prueba_de_contraste_lo_vea(self):
        for nivel in ("ok", "warn", "bad"):
            regla = next(d for s, d in _reglas() if s == f".estado-dot.estado-{nivel}")
            assert re.search(r"background-color:\s*var\(--(ok|yellow|warn)\)", regla)

    def test_el_punto_pequeno_cabe_el_glifo(self):
        d = next(d for s, d in _reglas() if s == ".estado-dot-sm")
        assert "width: 16px" in d and "height: 16px" in d

    def test_en_estado_html_el_javascript_en_linea_solo_pone_clases(self):
        """V9 queda aparte: este cambio no toca el JS de /estado, que ya pone `estado-<nivel>`."""
        html = (RAIZ / "web" / "templates" / "estado.html").read_text(encoding="utf-8")
        assert 'className = "estado-dot estado-" + meta.level' in html
        assert "'<div class=\"estado-dot estado-dot-sm estado-' + level + '\"></div>'" in html


class TestContrasteDelGlifo:
    """WCAG 1.4.11 (gráfico no textual): el glifo debe verse sobre el fondo de su punto, ≥ 3:1, en los dos
    temas. Los colores salen de web.css, no se copian: si alguien oscurece `--warn`, el «!» deja de verse
    y esta prueba falla (el rojo en claro va justo: ~3,3:1)."""

    FONDO_DEL_NIVEL = {"ok": "var(--ok)", "bad": "var(--warn)", "warn": "var(--yellow)"}

    @pytest.mark.parametrize("tema", ["claro", "oscuro"])
    @pytest.mark.parametrize("nivel", ["ok", "bad", "warn"])
    def test_el_glifo_se_ve_sobre_el_fondo_de_su_punto(self, tema, nivel):
        from tests.test_web_css_contraste import _temas, contraste, resolver
        regla = next(d for s, d in _reglas() if s == f".estado-dot.estado-{nivel}")
        fondo = re.search(r"background-color:\s*(var\(--[\w-]+\))", regla).group(1)
        assert fondo == self.FONDO_DEL_NIVEL[nivel]                      # el fondo que mide es el que pinta la hoja
        t = _temas()[tema]
        assert contraste(TINTA_DEL_PUNTO, resolver(fondo, t)) >= 3.0, (tema, nivel)


class TestDeseados:
    def test_cada_estado_de_deseo_tiene_aspecto_y_es_uno_del_vocabulario(self):
        assert set(ASPECTO_DE_DESEO) == set(WishlistStatus)
        assert set(ASPECTO_DE_DESEO.values()) <= set(ASPECTOS)

    def test_un_estado_sin_aspecto_falla_en_vez_de_pintarse_neutro(self, monkeypatch):
        monkeypatch.delitem(ASPECTO_DE_DESEO, WishlistStatus.FAILED)
        with pytest.raises(ValueError, match="sin aspecto"):
            aspecto_de_deseo(WishlistStatus.FAILED)

    def test_importado_y_sin_resultados_no_comparten_icono(self):
        ok, falla = (ASPECTOS[aspecto_de_deseo(s)] for s in (WishlistStatus.IMPORTED, WishlistStatus.FAILED))
        assert ok.icono and falla.icono and ok.icono != falla.icono

    def test_la_fila_pinta_el_chip_con_su_icono(self):
        from zascarr.web.wishlist import _ESTADO_LABEL
        env = crear_templates().env
        for estado, esperado in ((WishlistStatus.IMPORTED, "✓"), (WishlistStatus.FAILED, "!")):
            h = env.from_string("{{ ui.chip(a, t) }}").render(ui=env.globals["ui"], a=aspecto_de_deseo(estado),
                                                              t=_ESTADO_LABEL[estado])
            assert f'<span aria-hidden="true">{esperado}</span>' in h and _ESTADO_LABEL[estado] in h

    def test_ninguna_plantilla_ni_regla_usa_ya_wishlist_badge(self):
        """Regresión: la clase heredada (deuda 6) no vuelve; su sustituto es `ui.chip`."""
        con = [p.name for p in (RAIZ / "web" / "templates").rglob("*.html")
               if "wishlist-badge" in p.read_text(encoding="utf-8")]
        assert con == []
        assert "wishlist-badge" not in CSS_SIN_COMENTARIOS
