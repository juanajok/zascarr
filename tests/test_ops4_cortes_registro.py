"""Contrato de barreras sintéticas; pytest nunca corta QEMU ni para procesos."""
from __future__ import annotations

import os
import runpy
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.ops.registro_repeticiones_ops4 import reclamar_id

PROBE = Path(__file__).parent / "fixtures" / "ops4-vm" / "replay-crash-probe.py"


@pytest.mark.parametrize("stage,expected", [
    (1, ["before_file"]),
    (2, ["before_file", "after_file", "before_directory"]),
    (3, ["before_file", "after_file", "before_directory", "after_directory", "accepted"]),
])
def test_barreras_no_confirman_antes_de_dos_fsync(
    stage: int, expected: list[str], tmp_path: Path, monkeypatch,
) -> None:
    transitions = []

    class CutReached(BaseException):
        pass

    def stop(pid, signum):
        assert pid == os.getpid()
        assert signum == signal.SIGSTOP
        raise CutReached

    def observed_claim(id_, **kwargs):
        callback = kwargs["sincronizar"]
        calls = 0

        def observed_sync(fd):
            nonlocal calls
            calls += 1
            suffix = "file" if calls == 1 else "directory"
            transitions.append("before_" + suffix)
            callback(fd)
            transitions.append("after_" + suffix)

        kwargs["sincronizar"] = observed_sync
        result = reclamar_id(id_, **kwargs)
        assert result is True
        transitions.append("accepted")
        return result

    monkeypatch.setattr(os, "kill", stop)
    monkeypatch.setitem(
        sys.modules, "registro_repeticiones_ops4", SimpleNamespace(reclamar_id=observed_claim),
    )
    monkeypatch.setattr(sys, "argv", [str(PROBE), "cut", str(stage)])
    probe = runpy.run_path(str(PROBE), run_name="fixture_inspection")
    main = probe["main"]
    monkeypatch.setitem(main.__globals__, "DIRECTORY", tmp_path / "store")
    with pytest.raises(CutReached):
        main()
    assert transitions == expected
