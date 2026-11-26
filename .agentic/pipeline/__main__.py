"""Interfaz de operador y transporte JSON para adaptadores sin acceso a estado."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pipeline.contracts import decode
from pipeline.engine import Engine, validate_config
from pipeline.git_snapshot import base_files
from pipeline.runner import Runner


def emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def file_json(path: Path) -> dict:
    with path.open("rb") as src:
        return decode(src.read(4 * 1024 * 1024 + 1))


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--run", type=Path, required=True)
    cli.add_argument("--allow-docker", action="store_true")
    cmds = cli.add_subparsers(dest="action", required=True)
    init = cmds.add_parser("init")
    init.add_argument("--repo", type=Path, default=Path.cwd())
    init.add_argument("--manifest", type=Path, required=True)
    init.add_argument("--policy", type=Path, required=True)
    for action in ("advance", "status", "cancel", "delivery"):
        cmds.add_parser(action)
    claim = cmds.add_parser("task")
    claim.add_argument("role")
    submit = cmds.add_parser("submit")
    submit.add_argument("task_id")
    submit.add_argument(
        "--origin", choices=["submitted", "dsh-native", "fixture"], default="submitted"
    )
    failed = cmds.add_parser("fail")
    failed.add_argument("task_id")
    decision = cmds.add_parser("decide")
    decision.add_argument("token")
    decision.add_argument("--operator", required=True)
    decision.add_argument("decision", choices=["accept", "reject"])
    return cli


def main() -> int:
    args = parser().parse_args()
    engine = Engine(args.run, Runner(allow_docker=args.allow_docker, scratch=args.run.resolve()))
    try:
        if args.action == "init":
            config = file_json(args.manifest)
            validate_config(config, source=False)
            paths = sorted(set(config["editable"] + config["context"]))
            sha, files = base_files(args.repo.resolve(), paths)
            state = engine.create(config | {"source_sha": sha}, file_json(args.policy), files)
        elif args.action == "advance":
            state = engine.advance()
        elif args.action == "status":
            state = engine.state()
        elif args.action == "task":
            pending = engine.state()["pending"]
            if args.role not in pending:
                raise ValueError("No hay una solicitud pendiente para este rol")
            emit(pending[args.role])
            return 0
        elif args.action == "submit":
            try:
                payload = decode(sys.stdin.buffer.read(4 * 1024 * 1024 + 1))
            except ValueError:
                payload = None
            valid = engine.submit(args.task_id, payload, origin=args.origin)
            emit({"accepted": valid})
            return 0 if valid else 2
        elif args.action == "fail":
            engine.submit(args.task_id, None)
            emit({"accepted": False})
            return 0
        elif args.action == "decide":
            engine.approve(args.token, args.operator, args.decision == "accept")
            state = engine.state()
        elif args.action == "cancel":
            engine.cancel()
            state = engine.state()
        else:
            emit(engine.delivery())
            return 0
        emit(
            {
                k: state[k]
                for k in (
                    "workflow_id",
                    "phase",
                    "profile",
                    "round",
                    "calls",
                    "blockers",
                    "approval",
                    "candidate",
                    "delivery_ref",
                )
            }
            | {"pending": {role: t["task_id"] for role, t in state["pending"].items()}}
        )
        return 3 if state["phase"] in {"BLOCKED", "FAILED", "CANCELLED"} else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # No imprimir payloads, rutas del usuario ni errores del subprocess/SDK.
        print(
            "No se pudo procesar la operación: "
            + (
                str(exc)
                if type(exc) is ValueError and exc.__cause__ is None
                else type(exc).__name__
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
