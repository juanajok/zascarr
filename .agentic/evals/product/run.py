"""Ejecuta la suite pura del producto con el runner y scratch en CI."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from pipeline.runner import Runner

ROOT = Path(__file__).resolve().parents[3]
FILES = {
    "zascarr/__init__.py": ROOT / "src/zascarr/__init__.py",
    "zascarr/core/__init__.py": ROOT / "src/zascarr/core/__init__.py",
    "zascarr/core/carpetas.py": ROOT / "src/zascarr/core/carpetas.py",
    "tests/test_core_carpetas.py": ROOT / "tests/test_core_carpetas.py",
}


def image_id() -> str:
    result = subprocess.run(
        ["/usr/bin/docker", "image", "inspect", "--format", "{{.Id}}", "agentic-product-tests:ci"],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    value = result.stdout.strip()
    if not value.startswith("sha256:") or len(value) != 71:
        raise SystemExit(f"ID de imagen inesperado: {value!r}")
    return value


def main() -> int:
    files = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}
    check = {
        "id": "producto-carpetas",
        "kind": "docker",
        "image": image_id(),
        "argv": [
            "python",
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp=/scratch/pytest",
            "tests/test_core_carpetas.py",
        ],
        "timeout": 120,
        "scratch": True,
    }
    with tempfile.TemporaryDirectory(dir=ROOT, prefix=".tmp-producto-") as scratch:
        result = Runner(True, Path(scratch)).run(files, check)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if not result.get("passed") or result.get("kind") != "docker" or result.get("exit_code") != 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
