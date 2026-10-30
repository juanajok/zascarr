"""Guardias del sidecar de operaciones 123b (sin aplicar a una BD real)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "aceptacion" / "preparar_operaciones_123b.py"


def _run(*args: str, env: dict | None = None):
    entorno = os.environ.copy()
    entorno.update(env or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=entorno,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="scripts POSIX")
class TestSidecar123b:
    def test_exige_entorno_123b(self, tmp_path):
        r = _run(
            "--database-url",
            "postgresql://u:p@127.0.0.1:15434/zascarr",
            "--biblioteca",
            str(tmp_path),
        )
        assert r.returncode != 0
        assert "ZASCARR_ENTORNO" in r.stderr

    def test_rechaza_puerto_que_no_es_el_aislado(self, tmp_path):
        r = _run(
            "--database-url",
            "postgresql://u:p@127.0.0.1:5432/zascarr",
            "--biblioteca",
            str(tmp_path),
            env={"ZASCARR_ENTORNO": "123b"},
        )
        assert r.returncode != 0
        assert "15434" in r.stderr

    def test_rechaza_host_remoto(self, tmp_path):
        r = _run(
            "--database-url",
            "postgresql://u:p@db.example:15434/zascarr",
            "--biblioteca",
            str(tmp_path),
            env={"ZASCARR_ENTORNO": "123b"},
        )
        assert r.returncode != 0
        assert "aislada" in r.stderr.lower()

    def test_exige_biblioteca(self, tmp_path):
        r = _run(
            "--database-url",
            "postgresql://u:p@127.0.0.1:15434/zascarr",
            "--biblioteca",
            str(tmp_path / "no-existe"),
            env={"ZASCARR_ENTORNO": "123b"},
        )
        assert r.returncode != 0
        assert "biblioteca" in r.stderr.lower()
