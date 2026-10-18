"""Las tres copias de «credenciales conocidas» (instalador, Compose y aplicación) no pueden divergir.

Una lista que crece en un sitio y no en otro deja una ruta de arranque abierta justo para el valor nuevo. Cada copia
tiene que ser exactamente la misma.
"""
from __future__ import annotations

import re
from pathlib import Path

from zascarr.utils.credenciales import CREDENCIALES_CONOCIDAS

RAIZ = Path(__file__).resolve().parents[1]


def _de_bash() -> set[str]:
    texto = (RAIZ / "scripts" / "_credenciales.sh").read_text(encoding="utf-8")
    m = re.search(r"^CREDENCIALES_CONOCIDAS=\(([^)]*)\)", texto, re.M)
    assert m, "no se encontró CREDENCIALES_CONOCIDAS en scripts/_credenciales.sh"
    return set(m.group(1).split())


def _de_compose() -> set[str]:
    texto = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
    m = re.search(r'^\s+""\|([a-z0-9_|]+)\)\s*$', texto, re.M)
    assert m, "no se encontró la lista del servicio `credenciales` en docker-compose.yml"
    return set(m.group(1).split("|"))


def test_las_tres_listas_son_la_misma():
    assert _de_bash() == _de_compose() == set(CREDENCIALES_CONOCIDAS)


def test_la_lista_no_esta_vacia_y_esta_en_minusculas():
    assert CREDENCIALES_CONOCIDAS and all(c == c.lower() for c in CREDENCIALES_CONOCIDAS)


def test_el_valor_de_ejemplo_de_la_plantilla_y_el_historico_del_compose_estan_incluidos():
    plantilla = re.search(r"^DB_PASSWORD=(.*)$", (RAIZ / ".env.example").read_text(encoding="utf-8"), re.M).group(1)
    assert not plantilla or plantilla.lower() in CREDENCIALES_CONOCIDAS
    assert "supersecretpassword123" in CREDENCIALES_CONOCIDAS
