"""#123b: un único helper/umbral de espacio en los scripts.

La auditoría del PO exige no duplicar el umbral ni tener dos fuentes de verdad.
Este test es estático a propósito: comprueba que solo `_espacio.sh` define el
helper y que los scripts que lo usan lo cargan desde ahí.
"""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"


def test_solo_espacio_sh_define_el_helper():
    definen = sorted(
        p.name
        for p in SCRIPTS.glob("*.sh")
        if "exigir_espacio_kb()" in p.read_text(encoding="utf-8")
    )
    assert definen == ["_espacio.sh"]


def test_los_scripts_cargan_el_helper_compartido():
    comun = (SCRIPTS / "_comun.sh").read_text(encoding="utf-8")
    restaurar = (SCRIPTS / "restaurar_datos.sh").read_text(encoding="utf-8")
    assert 'source "${SCRIPT_DIR}/_espacio.sh"' in comun
    assert 'source "${SCRIPT_DIR}/_espacio.sh"' in restaurar


def test_no_se_duplica_el_umbral_en_los_scripts():
    for nombre in (
        "backup.sh",
        "update.sh",
        "rollback.sh",
        "restaurar_datos.sh",
        "probar_restauracion.sh",
    ):
        texto = (SCRIPTS / nombre).read_text(encoding="utf-8")
        assert "necesario / 10 + 65536" not in texto, nombre
