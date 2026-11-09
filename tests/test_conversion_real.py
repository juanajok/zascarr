# ruff: noqa: E501
"""#564: conversión real con `unar` de los fixtures RAR de dos/tres entradas.

La prueba se salta si no hay `unar`/`lsar` (el entorno de desarrollo puede no tenerlos; la imagen
runtime de ZascArr sí). Reproduce el fallo multi-entrada: cada extracción usa su propia salida.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from zascarr.services.conversion_cbr import construir_cbz
from zascarr.utils import lector_rar

FIXTURES = Path(__file__).parent / "fixtures" / "rar"
pytestmark = pytest.mark.skipif(
    not lector_rar.disponible(), reason="requiere unar/lsar reales")


@pytest.mark.parametrize("fixture", ["minimo_rar4.cbr", "minimo_rar5.cbr", "solido_rar4.cbr"])
def test_rar_real_de_varias_entradas(tmp_path, fixture):
    origen = FIXTURES / fixture
    if not origen.exists():
        pytest.skip(f"falta el fixture {fixture}")
    destino = tmp_path / f"{fixture}.cbz"
    construccion = construir_cbz(origen, destino, lector=lector_rar)
    assert len(construccion.manifiesto) >= 2
    with zipfile.ZipFile(destino) as zf:
        assert zf.testzip() is None
        assert len([i for i in zf.infolist() if not i.is_dir()]) == len(construccion.manifiesto)
        assert {i.filename for i in zf.infolist()} == {m.nombre for m in construccion.manifiesto}
