# ruff: noqa: E501
"""#418: `scripts/ci_rar_real.py` falla si las pruebas de RAR real se saltaron (una saltada no es una pasada)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

RUTA = Path(__file__).resolve().parents[1] / "scripts" / "ci_rar_real.py"
spec = importlib.util.spec_from_file_location("ci_rar_real", RUTA)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def _informe(tmp_path, casos: list[str]) -> str:
    cuerpo = "".join(f'<testcase classname="tests.test_lector_rar_real" name="t{i}">{c}</testcase>'
                     for i, c in enumerate(casos))
    f = tmp_path / "i.xml"
    f.write_text(f"<testsuites><testsuite>{cuerpo}</testsuite></testsuites>")
    return str(f)


def test_todas_ejecutadas_es_verde(tmp_path):
    assert ci.motivos(_informe(tmp_path, [""] * ci.MINIMO_DE_PRUEBAS)) == []


def test_una_saltada_es_roja(tmp_path):
    casos = [""] * (ci.MINIMO_DE_PRUEBAS - 1) + ["<skipped/>"]
    assert any("saltadas" in m for m in ci.motivos(_informe(tmp_path, casos)))


def test_un_xfail_ejecutado_no_cuenta_como_saltado(tmp_path):
    """pytest registra un xfail como `<skipped type="pytest.xfail">`: se ejecutó, no se saltó."""
    casos = [""] * (ci.MINIMO_DE_PRUEBAS - 1) + ['<skipped type="pytest.xfail" message="x"/>']
    assert ci.motivos(_informe(tmp_path, casos)) == []


def test_un_fallo_es_rojo(tmp_path):
    casos = [""] * (ci.MINIMO_DE_PRUEBAS - 1) + ["<failure/>"]
    assert any("fallo" in m for m in ci.motivos(_informe(tmp_path, casos)))


def test_sin_pruebas_de_rar_real_es_rojo_no_verde_vacio(tmp_path):
    """Si el fichero de pruebas desapareciera o no se recogiera, el informe vacío NO es verde."""
    assert any("solo 0" in m for m in ci.motivos(_informe(tmp_path, [])))
