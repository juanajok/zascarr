"""#123b: el margen de espacio vive en un único helper para copias/restauración.

La auditoría del PO exige no duplicar el umbral ni tener dos fuentes de verdad.
Este test es estático y no circular:

- comprueba que `scripts/_espacio.sh` **sí** contiene la aritmética del margen
  (`necesario + 10 % + 64 MiB`), y
- comprueba que **ningún script de copia/restauración** la repite, con cualquier
  formato (`necesario/10`, `necesario / 10`, `64 * 1024`, `65536`, `0.1`...).

No se escanean dos ficheros ajenos a copias/restauración:

- `scripts/medicion/ventana_e.sh`: preflight de la medición E (exige 8 GiB
  libres para los sintéticos). No copia ni restaura la BD.
- `bootstrap.sh`: queda fuera de la entrega de 123b y no tiene comprobaciones
  de espacio; se audita, no se modifica.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
ESPACIO = SCRIPTS / "_espacio.sh"

COPIAS = (
    "backup.sh",
    "update.sh",
    "rollback.sh",
    "restaurar_datos.sh",
    "probar_restauracion.sh",
)

EXCLUIDOS = {
    "scripts/medicion/ventana_e.sh": "preflight de medición (8 GiB), no copia/restaura",
    "bootstrap.sh": "fuera de la entrega (sin comprobaciones de espacio)",
}

# El margen es 10 % del necesario + 64 MiB. En KiB son 65536; en bytes,
# 64 * 1024 * 1024. Se normaliza el espacio para que el reformateo no escape.
_MARGEN = (
    re.compile(r"necesario/10"),
    re.compile(r"necesario\*0?\.10?"),
    re.compile(r"necesario\*10/100"),
    re.compile(r"65536"),
    re.compile(r"64\*1024"),
    re.compile(r"67108864"),
)


def _sin_espacios(texto: str) -> str:
    return re.sub(r"\s+", "", texto)


def _tiene_aritmetica_de_margen(texto: str) -> bool:
    compacto = _sin_espacios(texto)
    return any(patron.search(compacto) for patron in _MARGEN)


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


def test_el_helper_si_define_el_margen():
    """La prueba negativa no es vacua: el margen existe donde debe existir."""
    assert _tiene_aritmetica_de_margen(ESPACIO.read_text(encoding="utf-8"))


def test_ningun_script_de_copia_duplica_el_margen():
    for nombre in COPIAS:
        texto = (SCRIPTS / nombre).read_text(encoding="utf-8")
        assert not _tiene_aritmetica_de_margen(texto), nombre


def test_los_excluidos_estan_documentados_y_no_son_de_copias():
    assert set(EXCLUIDOS) == {"scripts/medicion/ventana_e.sh", "bootstrap.sh"}
    assert not (set(COPIAS) & {Path(ruta).name for ruta in EXCLUIDOS})
