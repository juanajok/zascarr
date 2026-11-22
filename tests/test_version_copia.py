"""UATP-07 / D-2 / T-07-02: la versión declarada de la copia no se separa entre pyproject y la app.

`version_de_la_copia` se compone de `head`, `build_sha`, `app_version` y `alembic`. El semver
(`app_version`) **no identifica** el código por sí solo (ADR 0025); este test solo garantiza que la
fuente única de paquete (`pyproject.toml`) y `Settings.app_version` no divergen y que el formato es
el que valida el manifiesto. La tupla completa se prueba contra el manifiesto real en
`tests/test_backup_script.py`.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from zascarr.config import get_settings

RAIZ = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")


def _version_pyproject() -> str:
    datos = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    return datos["project"]["version"]


def test_la_version_de_la_app_y_la_del_paquete_son_la_misma():
    """T-07-02: un cambio en una sola de las dos fuentes rompe este test."""
    assert get_settings().app_version == _version_pyproject()


def test_la_version_es_semver_y_no_es_la_identidad():
    """D-2: el semver es un dato más de la tupla, nunca la identidad de la imagen."""
    version = _version_pyproject()
    assert SEMVER.fullmatch(version), version
    # Si algún día el proyecto decide no usar semver, este test obliga a decidirlo a la vez en
    # `config.py`, `pyproject.toml` y la validación del manifiesto (`scripts/_comun.sh`).
