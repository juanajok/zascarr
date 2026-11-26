"""Aplica las mismas comprobaciones funcionales a dos candidatos sintéticos."""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(path: Path):
    spec = importlib.util.spec_from_file_location("candidato", path)
    if spec is None or spec.loader is None:
        raise ValueError("No se pudo cargar el candidato")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    baseline = load(ROOT / "pagina.py")
    baseline_signature = inspect.signature(baseline.page)
    ok = True
    for filename in ("solucion-unica.py", "solucion-pipeline.py"):
        path = ROOT / filename
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "oraculo.py"), str(path)], check=False
        )
        current = inspect.signature(load(path).page)
        print(
            f"{filename}: sha256={hashlib.sha256(path.read_bytes()).hexdigest()} "
            f"oracle_exit={result.returncode} same_introspection_signature="
            f"{current == baseline_signature}",
            flush=True,
        )
        ok &= result.returncode == 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
