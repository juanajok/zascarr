"""Regresiones del opt-in y readiness del arnés PostgreSQL; nunca usan Docker."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

MODULE = Path(__file__).parent / "test_restaurar_produccion_pg.py"


def cargar_modulo():
    spec = importlib.util.spec_from_file_location("ops4_pg_harness_inspeccion", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sin_optin_no_se_invoca_docker(monkeypatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("ZASCARR_PG_IT", raising=False)
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append((a, k)))
    module = cargar_modulo()
    assert calls == []
    assert module._PG_OPT_IN is False
    assert module._DOCKER_OK is False


def test_las_tres_condiciones_se_conservan(monkeypatch) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.delenv("ZASCARR_PG_IT", raising=False)
    module = cargar_modulo()
    reasons = [mark.kwargs.get("reason", "") for mark in module.pytestmark]
    assert len(module.pytestmark) == 3
    assert any("POSIX" in reason for reason in reasons)
    assert any("PostgreSQL" in reason or "ZASCARR_PG_IT" in reason for reason in reasons)
    assert any("Docker" in reason for reason in reasons)


def test_readiness_exige_tcp_y_consulta_final(monkeypatch) -> None:
    module = cargar_modulo()
    calls = []
    responses = []

    def compose(*args, **_kwargs):
        calls.append(args)
        if "pg_isready" in args:
            assert "-h" in args and "127.0.0.1" in args
            # Primer aviso TCP: aún no hay consulta final válida.
            return subprocess.CompletedProcess(args, 0, "", "")
        if "psql" in args:
            stdout = "1\n" if len(responses) else "0\n"
            responses.append(stdout)
            return subprocess.CompletedProcess(args, 0, stdout, "")
        raise AssertionError(args)

    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    proyecto = module.Proyecto.__new__(module.Proyecto)
    proyecto._compose = compose
    proyecto.esperar_postgres()
    assert len([call for call in calls if "pg_isready" in call]) == 2
    assert len([call for call in calls if "psql" in call]) == 2
    assert all("-h" in call and "127.0.0.1" in call
               for call in calls if "pg_isready" in call)


def test_readiness_no_acepta_socket_unix(monkeypatch) -> None:
    module = cargar_modulo()
    calls = []

    def compose(*args, **_kwargs):
        calls.append(args)
        # Simula el initdb: el socket Unix responde, pero TCP no.
        ready = 0 if "pg_isready" not in args or "-h" not in args else 1
        return subprocess.CompletedProcess(args, ready, "", "")

    monkeypatch.setattr(module.time, "sleep", lambda _s: None)
    instantes = iter([0.0, 0.0, 100.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(instantes, 100.0))
    proyecto = module.Proyecto.__new__(module.Proyecto)
    proyecto._compose = compose
    with pytest.raises(AssertionError):
        proyecto.esperar_postgres()
    assert all("-h" in call or "psql" in call for call in calls)
