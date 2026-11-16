"""A7: el instalador pregunta el usuario de servicio y no solo usa ZASCARR_USER."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_bootstrap_pregunta_el_usuario_con_media_por_defecto_y_lo_valida():
    texto = (RAIZ / "bootstrap.sh").read_text(encoding="utf-8")
    assert "¿Usuario de servicio del sistema?" in texto
    assert "USUARIO_POR_DEFECTO" in texto and "media" in texto
    assert "asegurar_usuario_servicio" in texto
    # El prompt va antes de resolver PUID/PGID: si no, se calcularían con otro usuario.
    assert texto.index("¿Usuario de servicio del sistema?") < texto.index('RESOLVED_UID="$(id -u')


def test_bootstrap_no_crea_el_usuario_antes_de_preguntar():
    texto = (RAIZ / "bootstrap.sh").read_text(encoding="utf-8")
    prompt = texto.index("¿Usuario de servicio del sistema?")
    # La única llamada que debe quedar antes del prompt es la definición de la función.
    assert "asegurar_usuario_servicio\n" not in texto[:prompt]
    assert texto.count("asegurar_usuario_servicio") >= 2


def test_la_eleccion_se_persiste_en_env_para_reejecuciones():
    texto = (RAIZ / "bootstrap.sh").read_text(encoding="utf-8")
    assert 'set_env_var "ZASCARR_USER"' in texto
    assert 'set_env_var "ZASCARR_GROUP"' in texto
