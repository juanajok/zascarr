"""#727: móvil y accesibilidad del flujo «Por revisar» (comprobaciones estructurales)."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
TEMPLATES = RAIZ / "src/zascarr/web/templates"
CSS = (RAIZ / "src/zascarr/static/web.css").read_text(encoding="utf-8")


def test_la_barra_de_progreso_anuncia_cambios_completos():
    t = (TEMPLATES / "_vinculacion_revision.html").read_text(encoding="utf-8")
    assert 'class="vinc-barra" role="status" aria-live="polite" aria-atomic="true"' in t


def test_el_rango_de_pendientes_es_una_region_viva_atomica():
    t = (TEMPLATES / "_pendientes_rango.html").read_text(encoding="utf-8")
    assert 'role="status" aria-live="polite" aria-atomic="true"' in t


def test_los_avisos_de_tarjeta_reciben_el_foco():
    """Tras sustituir una tarjeta por un error HTMX, el aviso es el primer foco."""
    t = (TEMPLATES / "_tarjeta_pendiente.html").read_text(encoding="utf-8")
    assert 'ui.aviso(aviso.tipo, aviso.texto, foco=true)' in t


def test_en_movil_la_barra_y_las_acciones_siguen_visibles_y_son_tocables():
    assert "@media (max-width: 600px)" in CSS
    assert ".vinc-barra { position: sticky; top: 0;" in CSS
    assert "@media (max-width: 480px)" in CSS
    assert ".pending-grid { grid-template-columns: 1fr; }" in CSS
    assert "min-height: 44px" in CSS


def test_las_tarjetas_no_se_quedan_con_hover_en_tactil():
    assert "@media (hover: none)" in CSS
    assert ".pending-card:hover" in CSS
