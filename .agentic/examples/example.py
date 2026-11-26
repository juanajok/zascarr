"""Crea un ejemplo benigno. Los veredictos offline son fixtures, no asistencia real."""

from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.__main__ import emit, file_json
from pipeline.engine import TERMINAL, Engine
from pipeline.runner import Runner


def fixture(role: str) -> dict:
    if role == "BRAIN":
        return {"summary": "Cambio de texto acotado", "profile": "STANDARD"}
    if role == "BENCHMARKER":
        return {"summary": "Reusar el archivo de etiqueta", "references": ["label.txt"]}
    if role == "SPEC":
        return {
            "requirements": [
                {"id": "R-01", "criterion": "La etiqueta dice Tu tebeoteca", "mandatory": True}
            ]
        }
    if role == "DEVELOPER":
        return {"summary": "Corrige etiqueta", "edits": {"label.txt": "Tu tebeoteca\n"}}
    return {"verdict": "PASS", "covered": ["R-01"], "findings": [], "summary": "Fixture simulado"}


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("run", type=Path)
    cli.add_argument("--prepare-only", action="store_true")
    args = cli.parse_args()
    root = Path(__file__).resolve().parent
    engine = Engine(args.run, Runner())
    # SHA fuente = commit real de un baseline de ejemplo, no el de ZascArr.
    baseline = {"label.txt": (root / "label.txt").read_text(encoding="utf-8")}
    from tempfile import TemporaryDirectory

    from pipeline.git_snapshot import snapshot

    with TemporaryDirectory() as parent:
        source = snapshot(Path(parent) / "source", baseline)
    state = engine.create(
        file_json(root / "manifest.json") | {"source_sha": source},
        file_json(root / "policy.json"),
        baseline,
    )
    if not args.prepare_only:
        for _ in range(30):
            state = engine.advance()
            if state["phase"] in TERMINAL or not state["pending"]:
                break
            for role, task in state["pending"].items():
                engine.submit(task["task_id"], fixture(role), origin="fixture")
    emit({k: state[k] for k in ("workflow_id", "phase", "calls", "candidate", "history")})
    return 0 if args.prepare_only or state["phase"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
