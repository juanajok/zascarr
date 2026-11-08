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


# ── #530 C3: el runner de la suite tiene que ser el de producción (1.10.8 + flag) ─────────────

def test_sin_unar_ni_lsar_en_el_runner_es_rojo(monkeypatch):
    monkeypatch.setattr(ci.shutil, "which", lambda nombre: None)
    problemas = ci.problemas_de_la_herramienta()
    assert any("falta unar" in p for p in problemas) and any("falta lsar" in p for p in problemas)


def test_un_runner_con_1_10_1_es_rojo_aunque_el_fallback_lo_tapara(monkeypatch):
    monkeypatch.setattr(ci.shutil, "which", lambda nombre: f"/usr/bin/{nombre}")
    monkeypatch.setattr(ci, "_salida", lambda *orden: "v1.10.1" if "-v" in orden else "sin flag")
    problemas = ci.problemas_de_la_herramienta()
    assert any("unar no es 1.10.8" in p for p in problemas)
    assert any("lsar no es 1.10.8" in p for p in problemas)
    assert any(ci.FLAG_SOLIDOS in p for p in problemas)


def test_el_runner_correcto_pasa(monkeypatch):
    monkeypatch.setattr(ci.shutil, "which", lambda nombre: f"/usr/bin/{nombre}")
    monkeypatch.setattr(ci, "_salida", lambda *orden: "v1.10.8" if "-v" in orden else ci.FLAG_SOLIDOS)
    assert ci.problemas_de_la_herramienta() == []
