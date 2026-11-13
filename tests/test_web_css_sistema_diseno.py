"""Sistema de diseño (#689): regresiones de la deuda pequeña que se cierra aquí.

Cuatro reglas que la revisión dejó abiertas y que no deben volver:
1. `.audit-ok` deja de usarse en plantillas: lo sustituye `ui.aviso("ok"|"info")`, que
   añade icono, `role` y el borde de tinta de los avisos. La clase sigue en la hoja por la
   compatibilidad hasta la V14 (la cubre `test_web_componentes`).
2. `btn-secondary` no existe en la hoja (las variantes son `.ghost` y `.sm`): ninguna
   plantilla debe volver a usarla.
3. `.archivo-fila` separa con tinta visible (`--ink-faint`); con `--paper-2` dentro de una
   viñeta `paper-2` la línea no se veía.
4. `.vinc-fila` usa el borde de 2 px del sistema, no `1px solid currentColor`.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"
TODAS_LAS_PLANTILLAS = "\n".join(
    p.read_text(encoding="utf-8") for p in sorted(PLANTILLAS.rglob("*.html")))


def regla(selector: str) -> str:
    """Cuerpo de la primera regla cuyo selector exacto empieza por `selector`."""
    m = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert m, f"no existe la regla {selector} en web.css"
    return m.group(1)


class TestAvisosDeAuditoria:
    def test_las_plantillas_no_vuelven_a_pintar_audit_ok(self):
        assert "audit-ok" not in TODAS_LAS_PLANTILLAS, (
            "usa ui.aviso(\"ok\"|\"info\"): da icono, role y el borde de los avisos")

    def test_la_auditoria_usa_el_aviso_del_sistema(self):
        for nombre in ("_auditoria_informe.html", "_auditoria_registro.html"):
            texto = (PLANTILLAS / nombre).read_text(encoding="utf-8")
            assert 'ui.aviso("ok"' in texto, nombre
        assert 'ui.aviso("info"' in (PLANTILLAS / "_duplicados.html").read_text(encoding="utf-8")

    def test_la_clase_sigue_en_la_hoja_por_compatibilidad(self):
        # Se retira en la V14, no antes (lo exige test_web_componentes).
        assert ".audit-ok" in CSS


class TestBotonSecundarioReal:
    def test_ninguna_plantilla_usa_btn_secondary(self):
        assert "btn-secondary" not in TODAS_LAS_PLANTILLAS, (
            "esa variante no existe en la hoja: para lo secundario, .btn.ghost o .btn")

    def test_la_hoja_no_declara_btn_secondary(self):
        assert ".btn-secondary" not in CSS


class TestBordesDeFilas:
    def test_archivo_fila_separa_con_tinta_visible(self):
        cuerpo = regla(".archivo-fila")
        assert "border-top: 1px solid var(--ink-faint)" in " ".join(cuerpo.split()), cuerpo
        assert "var(--paper-2)" not in cuerpo

    def test_vinc_fila_usa_el_borde_del_sistema(self):
        cuerpo = " ".join(regla(".vinc-fila").split())
        assert "border: 2px solid var(--ink)" in cuerpo, cuerpo
        assert "currentColor" not in cuerpo
