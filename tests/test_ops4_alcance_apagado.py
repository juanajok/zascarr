"""TA-09: la rama no enciende nada y no contiene el actualizador real conectado."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def test_bandera_apagada_por_defecto() -> None:
    texto = (RAIZ / "src" / "zascarr" / "config.py").read_text(encoding="utf-8")
    assert "ops4_actualizacion_habilitada: bool = Field(default=False)" in texto
    compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    assert "OPS4_ACTUALIZACION_HABILITADA=${OPS4_ACTUALIZACION_HABILITADA:-false}" in compose


def test_no_se_invoca_update_sh_ni_se_instala_la_unidad() -> None:
    for ruta in (
        RAIZ / "deploy" / "ops" / "zascarr_actualizar_aux.py",
        RAIZ / "scripts" / "instalar_actualizacion_ops4.sh",
        RAIZ / "src" / "zascarr" / "main.py",
    ):
        texto = ruta.read_text(encoding="utf-8")
        assert "update.sh" not in texto or "instalar" in ruta.name, ruta


def test_las_unidades_no_se_habilitan_al_instalar() -> None:
    instalador = (RAIZ / "scripts" / "instalar_actualizacion_ops4.sh").read_text(encoding="utf-8")
    assert "systemctl enable" not in instalador
    for unidad in ("zascarr-actualizar.service", "zascarr-actualizar.socket",
                   "zascarr-actualizar@.service"):
        texto = (RAIZ / "deploy" / "systemd" / unidad).read_text(encoding="utf-8")
        assert not any(line.strip() == "[Install]" for line in texto.splitlines()), unidad
