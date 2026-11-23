"""Pruebas sin Docker del resumen de estabilidad de UXLab."""
from pathlib import Path
from runpy import run_path


ROOT = Path(__file__).resolve().parents[1]
MOD = run_path(str(ROOT / "uxlab" / "stability_report.py"))
summarise = MOD["summarise"]


def _fixture():
    return {"suites": [
        {"specs": [
            {"title": "UX-01", "tests": [
                {"projectName": "chromium-desktop", "results": [
                    {"status": "passed", "duration": 100},
                    {"status": "passed", "duration": 110},
                    {"status": "passed", "duration": 120},
                ]},
                {"projectName": "chromium-mobile", "results": [
                    {"status": "passed", "duration": 150},
                    {"status": "failed", "duration": 170},
                    {"status": "passed", "duration": 180},
                ]},
            ]},
            {"title": "UX-04", "tests": [
                {"projectName": "chromium-desktop", "results": [
                    {"status": "failed"}, {"status": "failed"}, {"status": "failed"},
                ]},
                {"projectName": "chromium-mobile", "results": [
                    {"status": "passed"}, {"status": "passed"},
                ]},
            ]},
        ]}
    ]}


def test_resume_distingue_flaky_y_fallo_sistematico():
    output = summarise(_fixture(), 3)
    assert output["total_executions"] == 11
    assert output["passed"] == 7
    assert output["intermittent_groups"] == 1
    assert output["systematic_failure_groups"] == 1
    assert output["incomplete_groups"] == 1


def test_tres_pases_iguales_no_se_califican_como_flaky():
    data = {"suites": [{"specs": [{"title": "UX-01", "tests": [
        {"projectName": "chromium-desktop", "results": [
            {"status": "passed"}, {"status": "passed"}, {"status": "passed"}
        ]}
    ]}]}]}
    output = summarise(data, 3)
    assert output["groups"][0]["verdict"] == "consistente"


def test_run_restauracion_de_permisos_en_trap_y_repeticion():
    run = (ROOT / "uxlab" / "run.sh").read_text(encoding="utf-8")
    assert "trap cleanup EXIT" in run
    assert 'HOST_UID="$(id -u)"' in run
    assert 'HOST_GID="$(id -g)"' in run
    assert "chown -R" in run
    assert "--cap-add CHOWN" in run and "--network none" in run
    assert "--repeat-each" in run
    assert 'REPEAT_EACH=3' in run
