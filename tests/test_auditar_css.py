"""`scripts/auditar_css.py` (V14 F1, #750): impide que vuelvan clases inventadas o CSS muerto.

Las dos listas del script son la red de la retirada del CSS heredado: una clase usada sin regla
(`btn-secondary` fue el caso real) y una regla que ya no usa nadie. También comprueba que entiende
las clases que no se ven en un `class="…"` estático: prefijos con Jinja, ternarios, macros y la
lista blanca de las que añade htmx o el JS de `/estado`.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("auditar_css", RAIZ / "scripts" / "auditar_css.py")
auditar_css = importlib.util.module_from_spec(_spec)
sys.modules["auditar_css"] = auditar_css          # dataclasses busca su módulo en sys.modules
_spec.loader.exec_module(auditar_css)


def _auditar(css: str, html: str, extras: set[str] | None = None):
    return auditar_css.auditar(css=css, html_por_plantilla={"x.html": html}, extras=extras,
                               incluir_componentes=False, incluir_python=False)


class TestLasDosListas:
    def test_una_clase_usada_sin_regla_es_un_hallazgo(self):
        r = _auditar(".btn { color: red; }", '<button class="btn inventada">')
        assert r.sin_regla == ["inventada"]

    def test_una_regla_que_nadie_usa_es_un_hallazgo(self):
        r = _auditar(".muerta { color: red; }", '<div class="otra">')
        assert r.sin_uso == ["muerta"]
        assert r.sin_regla == ["otra"]

    def test_una_hoja_y_una_plantilla_coherentes_no_dan_nada(self):
        r = _auditar(".btn { color: red; }", '<button class="btn">')
        assert r.sin_regla == [] and r.sin_uso == []


class TestClasesQueNoSeVenEnElAtributo:
    def test_un_prefijo_con_jinja_cubre_sus_variantes(self):
        r = _auditar(".x-uno { color: red; }\n.x-dos { color: blue; }",
                     '<span class="x-{{ valor }}">')
        assert r.sin_uso == []

    def test_un_ternario_jinja_cuenta_sus_literales(self):
        r = _auditar(".hecho { color: red; }\n.otro { color: blue; }",
                     "<span class=\"step {{ 'hecho' if a else 'otro' }}\">")
        assert r.sin_uso == []

    def test_la_clase_de_ui_portada_cuenta_y_lazy_no(self):
        r = _auditar(".mi-portada { color: red; }",
                     '{{ ui.portada(t, id, src, "mi-portada", "lazy") }}')
        assert r.sin_uso == []
        assert "lazy" not in r.usadas

    def test_la_lista_blanca_respeta_lo_que_anade_htmx(self):
        r = _auditar(".htmx-request { opacity: .5; }", '<div class="otra">')
        assert "htmx-request" not in r.sin_uso


class TestElScriptEnElRepo:
    def test_el_repo_actual_no_tiene_reglas_muertas(self):
        """V14 F2 dejó la lista de «sin uso» vacía; si vuelve una, `--strict` falla."""
        r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "auditar_css.py"), "--strict"],
                           capture_output=True, text=True, cwd=RAIZ)
        assert r.returncode == 0, r.stdout + r.stderr

    def test_el_script_se_puede_ejecutar_sin_python_path_especial(self):
        """Carga `web/componentes.py` añadiendo `src/` por su cuenta (CI no define PYTHONPATH)."""
        r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "auditar_css.py")],
                           capture_output=True, text=True, cwd=RAIZ,
                           env={"PATH": "/usr/bin:/bin"})
        assert r.returncode == 0, r.stdout + r.stderr
