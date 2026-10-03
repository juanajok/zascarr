# ruff: noqa: E501
"""`scripts/ci_postgres.py`: el job de Postgres de la CI no puede quedar verde sin haber probado nada."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "ci_postgres", Path(__file__).resolve().parents[1] / "scripts" / "ci_postgres.py")
ci = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ci)


def informe(tmp_path, **cuentas) -> str:
    c = {"tests": 159, "failures": 0, "errors": 0, "skipped": 0, **cuentas}
    ruta = tmp_path / "pg.xml"
    ruta.write_text(
        '<?xml version="1.0"?><testsuites><testsuite name="pytest" '
        + " ".join(f'{k}="{v}"' for k, v in c.items()) + "/></testsuites>")
    return str(ruta)


class TestInforme:

    def test_una_ejecucion_real_se_acredita(self, tmp_path):
        assert ci.comprobar_informe(informe(tmp_path)) == []

    def test_todo_saltado_no_se_acredita(self, tmp_path):
        """El caso que motiva el script: sin TEST_DATABASE_URL, pytest «pasa» saltándolo todo."""
        motivos = ci.comprobar_informe(informe(tmp_path, tests=159, skipped=159))
        assert any("saltadas" in m for m in motivos)

    def test_una_sola_saltada_basta_para_no_acreditar(self, tmp_path):
        assert ci.comprobar_informe(informe(tmp_path, skipped=1))

    def test_pocas_pruebas_no_se_acreditan(self, tmp_path):
        assert any("mínimo" in m for m in ci.comprobar_informe(informe(tmp_path, tests=3)))

    @pytest.mark.parametrize("clave", ["failures", "errors"])
    def test_fallos_y_errores_no_se_acreditan(self, tmp_path, clave):
        assert ci.comprobar_informe(informe(tmp_path, **{clave: 1}))

    def test_informe_sin_pruebas(self, tmp_path):
        assert ci.comprobar_informe(informe(tmp_path, tests=0))

    def test_suma_varias_suites(self, tmp_path):
        ruta = tmp_path / "x.xml"
        ruta.write_text('<testsuites><testsuite tests="100" skipped="0" failures="0" errors="0"/>'
                        '<testsuite tests="60" skipped="2" failures="0" errors="0"/></testsuites>')
        assert ci.contar(str(ruta)) == {"tests": 160, "failures": 0, "errors": 0, "skipped": 2}


class TestEsperar:

    def test_sin_la_variable_falla_con_un_motivo(self, monkeypatch, capsys):
        monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
        assert ci.main(["esperar"]) == 2
        assert "sin ella las pruebas de Postgres se saltan" in capsys.readouterr().err

    def test_un_servidor_que_no_contesta_falla(self, monkeypatch, capsys):
        monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x_test")
        assert ci.main(["esperar", "--intentos", "1", "--pausa", "0"]) == 3
        assert "no contesta" in capsys.readouterr().err


def test_main_junit_devuelve_distinto_de_cero_si_no_acredita(tmp_path):
    assert ci.main(["junit", informe(tmp_path, skipped=159)]) == 1
    assert ci.main(["junit", informe(tmp_path)]) == 0
