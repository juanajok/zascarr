"""Orquestación persistente sin dependencia de proveedor ni permisos de agente."""

from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from pipeline.contracts import canonical, check_policy, digest, gate, safe_path, validate_result
from pipeline.git_snapshot import snapshot, verify_snapshot
from pipeline.runner import Runner, validate_checks
from pipeline.storage import Store

ROLES = ("BRAIN", "BENCHMARKER", "SPEC", "DEVELOPER", "UI_UX", "SECOPS", "QA")
PROFILES = ("FAST", "STANDARD", "HIGH_ASSURANCE")
HIGH_RISKS = {
    "auth",
    "authorization",
    "sensitive-data",
    "migration",
    "infra",
    "critical",
    "external",
    "incident-history",
    "security",
    "irreversible",
}
RISKS = HIGH_RISKS | {"ui", "dependency", "broad", "feature"}
TERMINAL = {"COMPLETED", "CANCELLED", "FAILED", "BLOCKED"}
TASK_TIMEOUT_MS = 900_000
MAX_RESULT_BYTES = 256_000


def detect_risks(config: dict) -> set[str]:
    """Aplica mínimos conservadores cuando la ruta indica un área de riesgo."""
    risks = set(config["risk"])
    for original in config["editable"]:
        path = original.lower()
        parts = set(path.split("/"))
        if parts & {"web", "templates", "static", "frontend", "ui"} or path.endswith(
            (".html", ".css", ".jsx", ".tsx", ".vue", ".svelte")
        ):
            risks.add("ui")
        if parts & {"deploy", "infra", "alembic", "migrations", "security", "auth"} or any(
            word in path for word in ("reautenticacion", "seguridad", "password", "dockerfile")
        ):
            risks.add("critical")
        if parts & {"pyproject.toml", "package.json", "package-lock.json", "cargo.toml"}:
            risks.add("dependency")
    return risks


FLOW = {
    "REQUESTED": {"DISCOVERY"},
    "DISCOVERY": {"BENCHMARKING"},
    "BENCHMARKING": {"SPECIFICATION"},
    "SPECIFICATION": {"SPEC_REVIEW"},
    "SPEC_REVIEW": {"APPROVED_FOR_DEVELOPMENT", "HUMAN_APPROVAL_REQUIRED"},
    "APPROVED_FOR_DEVELOPMENT": {"IMPLEMENTATION"},
    "IMPLEMENTATION": {"DETERMINISTIC_VALIDATION", "CHANGES_REQUESTED"},
    "DETERMINISTIC_VALIDATION": {"PARALLEL_REVIEW", "CHANGES_REQUESTED"},
    "PARALLEL_REVIEW": {"QUALITY_GATE"},
    "QUALITY_GATE": {"ACCEPTED", "CHANGES_REQUESTED", "HUMAN_APPROVAL_REQUIRED"},
    "HUMAN_APPROVAL_REQUIRED": {"APPROVED_FOR_DEVELOPMENT", "ACCEPTED"},
    "CHANGES_REQUESTED": {"REWORK"},
    "REWORK": {"IMPLEMENTATION"},
    "ACCEPTED": {"DELIVERY"},
    "DELIVERY": {"COMPLETED"},
}


def transition(state: dict, target: str) -> None:
    current = state["phase"]
    if current in TERMINAL or (
        target not in FLOW[current] and target not in TERMINAL - {"COMPLETED"}
    ):
        raise ValueError("Transición inválida")
    state["history"].append({"from": current, "to": target, "at_ms": now()})
    state["phase"] = target


def now() -> int:
    return time.time_ns() // 1_000_000


def validate_config(config: dict, *, source: bool = True) -> None:
    fields = {"request", "risk", "editable", "context", "checks", "red"}
    if source:
        fields.add("source_sha")
    if set(config) != fields:
        raise ValueError("Campos del manifiesto inválidos")
    if source and (
        not isinstance(config["source_sha"], str)
        or not re.fullmatch(r"[a-f0-9]{40}(?:[a-f0-9]{24})?", config["source_sha"])
    ):
        raise ValueError("SHA de origen no válido")
    if not isinstance(config["request"], str) or not 0 < len(config["request"]) <= 4000:
        raise ValueError("Petición inválida")
    for key in ("editable", "context"):
        items = config[key]
        if (
            type(items) is not list
            or len(items) > 64
            or any(not safe_path(p) for p in items)
            or len(set(items)) != len(items)
        ):
            raise ValueError("Ámbito de archivos inválido")
    if not config["editable"]:
        raise ValueError("No hay archivos editables")
    for path in config["editable"]:
        parts = path.lower().split("/")
        if set(parts) & {".github", "test", "tests", "__tests__"} or parts[-1].startswith("test_"):
            raise ValueError("El desarrollador no puede editar controles de evaluación")
    paths = set(config["editable"] + config["context"])
    if any(any(p.startswith(q + "/") for q in paths) for p in paths):
        raise ValueError("Colisión fichero/directorio")
    flags = config["risk"]
    if (
        type(flags) is not list
        or len(flags) > len(RISKS)
        or any(not isinstance(f, str) or f not in RISKS for f in flags)
    ):
        raise ValueError("Factores de riesgo inválidos")
    validate_checks(config["checks"])
    if not 1 <= len(config["checks"]) <= 16 or config["red"] not in [
        c["id"] for c in config["checks"]
    ]:
        raise ValueError("Se requiere un control RED obligatorio")


class Engine:
    def __init__(self, root: Path, runner: Runner) -> None:
        self.store = Store(root)
        self.runner = runner

    def create(self, config: dict, policy: dict, files: dict) -> dict:
        validate_config(config)
        check_policy(policy)
        if (
            set(files) != set(config["editable"] + config["context"])
            or any(not isinstance(v, str) or "\0" in v for v in files.values())
            or sum(len(v.encode()) for v in files.values()) > 512_000
        ):
            raise ValueError("Contenido de snapshot inválido")
        profiles = detect_risks(config)
        profile = (
            "HIGH_ASSURANCE"
            if profiles & HIGH_RISKS
            else "STANDARD"
            if profiles or len(config["editable"]) > 2
            else "FAST"
        )
        self.store.root.mkdir(mode=0o700)
        (self.store.root / "objects").mkdir(mode=0o700)
        prompts = {
            role: (Path(__file__).resolve().parents[1] / "agents" / f"{role.lower()}.md").read_text(
                encoding="utf-8"
            )
            for role in ROLES
        }
        base = self._snapshot(files)
        state = dict(
            schema_version=1,
            workflow_id=uuid.uuid4().hex,
            phase="REQUESTED",
            history=[],
            config_ref=self.store.put(config),
            policy_ref=self.store.put(policy),
            prompts_ref=self.store.put(prompts),
            profile=profile,
            baseline=base,
            candidate=None,
            spec_ref=None,
            pending={},
            results={},
            attempts={},
            evidence=[],
            calls=0,
            round=1,
            seen=[],
            red=None,
            checks={},
            reviews={},
            blockers=[],
            approval=None,
            decisions=[],
            events=[],
            created_ms=now(),
            delivery_ref=None,
        )
        self.store.save(state)
        return state

    def _snapshot(self, files: dict, parent: str | None = None) -> dict:
        return {
            "commit_sha": snapshot(self.store.root / "git", files, parent),
            "artifact_ref": self.store.put(files),
        }

    def _persist(self, state: dict, target: str) -> None:
        transition(state, target)
        self.store.save(state)

    def _block(self, state: dict, reason: str) -> None:
        state["blockers"].append(reason)
        state["pending"] = {}
        self._persist(state, "BLOCKED")

    def _evidence(self, state: dict, payload: dict) -> str:
        key = self.store.put(payload)
        state["evidence"].append(key)
        return key

    def _checks(self, state: dict, config: dict, snap: dict, *, red: bool = False) -> None:
        files = self.store.get(snap["artifact_ref"])
        for check in config["checks"]:
            if red != (state["phase"] == "SPEC_REVIEW"):
                raise ValueError("Control en fase no válida")
            if red and config["red"] != check["id"]:
                continue
            if (red and state["red"]) or (not red and check["id"] in state["checks"]):
                continue
            result = self.runner.run(files, check)
            if (
                type(result.get("passed")) is not bool
                or result["kind"] != check["kind"]
                or (
                    check["kind"] == "docker"
                    and red
                    and not result["passed"]
                    and result["exit_code"] != 42
                )
            ):
                self._evidence(
                    state,
                    {
                        "origin": "runner",
                        "commit_sha": snap["commit_sha"],
                        "check_id": check["id"],
                        **result,
                    },
                )
                self._block(state, f"CHECK_INFRASTRUCTURE:{check['id']}")
                return
            ref = self._evidence(
                state,
                {
                    "origin": "runner",
                    "commit_sha": snap["commit_sha"],
                    "spec_version": state["spec_ref"],
                    "policy_version": state["policy_ref"],
                    "check_id": check["id"],
                    **result,
                },
            )
            if red:
                state["red"] = ref
            else:
                state["checks"][check["id"]] = ref
            self.store.save(state)

    def _approve_at(self, state: dict, target: str) -> None:
        request = {
            "target": target,
            "workflow_id": state["workflow_id"],
            "round": state["round"],
            "spec_version": state["spec_ref"],
            "policy_version": state["policy_ref"],
            "config_ref": state["config_ref"],
            "baseline": state["baseline"],
            "candidate": state["candidate"],
            "red": state["red"],
            "checks": state["checks"],
            "reviews": state["reviews"],
        }
        state["approval"] = request | {"token": digest(request)}
        self._persist(state, "HUMAN_APPROVAL_REQUIRED")

    def _context(self, role: str, s: dict, config: dict) -> dict:
        context = {"request": config["request"], "profile": s["profile"]}
        if role in {"BRAIN", "BENCHMARKER"}:
            context["scope"] = config["editable"]
        if role in {"BENCHMARKER", "DEVELOPER", "QA", "UI_UX", "SECOPS"}:
            snap = s["candidate"] if role in {"QA", "UI_UX", "SECOPS"} else s["baseline"]
            files = self.store.get(snap["artifact_ref"])
            context["files"] = {p: files[p] for p in set(config["context"] + config["editable"])}
        if role == "SPEC":
            if "BENCHMARKER" in s["results"]:
                context["benchmark"] = self.store.get(s["results"]["BENCHMARKER"])["payload"]
            else:
                context["existing_paths"] = config["editable"]
        if role in {"DEVELOPER", "QA", "UI_UX", "SECOPS"}:
            context["spec"] = self.store.get(s["spec_ref"])
        if role == "DEVELOPER":
            context["editable"] = config["editable"]
            context["blockers"] = s["blockers"]
            context["feedback"] = [
                self.store.get(ref)["payload"]["findings"] for ref in s["reviews"].values()
            ]
            context["red"] = self.store.get(s["red"])
            previous = s.get("previous_attempt")
            if previous and previous["candidate"]:
                failed_files = self.store.get(previous["candidate"]["artifact_ref"])
                context["previous_edits"] = {
                    p: failed_files[p]
                    for p in config["editable"]
                    if failed_files[p] != context["files"][p]
                }
                context["previous_checks"] = {
                    key: self.store.get(ref) for key, ref in previous["checks"].items()
                }
        if role in {"QA", "UI_UX", "SECOPS"}:
            context["checks"] = {k: self.store.get(v) for k, v in s["checks"].items()}
        return context

    def _issue(self, s: dict, roles: list[str], config: dict, policy: dict) -> None:
        prompts = self.store.get(s["prompts_ref"])
        room = policy["concurrency"] - len(s["pending"])
        needed = [role for role in roles if role not in s["results"] and role not in s["pending"]]
        for role in needed[:room]:
            key = f"{s['phase']}:{s['round']}:{role}"
            attempt = s["attempts"].get(key, 0) + 1
            if s["calls"] >= policy["max_calls"] or attempt > policy["max_attempts"]:
                self._block(s, f"BUDGET_OR_RETRIES:{role}")
                return
            candidate = s["candidate"] if role in {"QA", "SECOPS", "UI_UX"} else s["baseline"]
            routes = policy.get("routes", {}).get(s["profile"], {})
            task = dict(
                schema_version=1,
                workflow_id=s["workflow_id"],
                task_id=uuid.uuid4().hex,
                agent_id=role,
                attempt_id=attempt,
                commit_sha=candidate["commit_sha"],
                source_sha=config["source_sha"],
                spec_version=s["spec_ref"],
                policy_version=s["policy_ref"],
                model_id=routes.get(role, policy["models"][role]),
                prompt_version=digest(prompts[role]),
                correlation_id=s["workflow_id"],
                prompt=prompts[role],
                context=self._context(role, s, config),
                issued_ms=now(),
            )
            if len(canonical(task)) > policy["max_context_bytes"]:
                self._block(s, f"CONTEXT_BUDGET:{role}")
                return
            s["attempts"][key] = attempt
            s["calls"] += 1
            s["pending"][role] = task
        self.store.save(s)

    def _rework(self, s: dict, policy: dict) -> None:
        if s["round"] >= policy["max_rounds"]:
            self._block(s, "ROUND_LIMIT")
            return
        s["round"] += 1
        s["previous_attempt"] = {"candidate": s["candidate"], "checks": s["checks"]}
        s["candidate"] = None
        s["checks"] = {}
        for role in ("DEVELOPER", "QA", "SECOPS", "UI_UX"):
            s["results"].pop(role, None)
        self._persist(s, "REWORK")

    def _judge_roles(self, config: dict) -> list[str]:
        return ["QA", "SECOPS"] + (["UI_UX"] if "ui" in detect_risks(config) else [])

    def advance(self) -> dict:
        with self.store.lock():
            return self._advance(self.store.load())

    def _advance(self, s: dict) -> dict:
        config = self.store.get(s["config_ref"])
        policy = self.store.get(s["policy_ref"])
        roles = self._judge_roles(config)
        expired = [
            role
            for role, task in s["pending"].items()
            if now() - task["issued_ms"] >= TASK_TIMEOUT_MS
        ]
        for role in expired:
            task = s["pending"].pop(role)
            s["events"].append(
                {"event": "task_timeout", "task_id": task["task_id"], "at_ms": now()}
            )
        if expired:
            self.store.save(s)
        while (phase := s["phase"]) not in TERMINAL | {"HUMAN_APPROVAL_REQUIRED"}:
            if phase == "REQUESTED":
                self._persist(s, "DISCOVERY")
            elif phase == "DISCOVERY":
                if "BRAIN" not in s["results"]:
                    self._issue(s, ["BRAIN"], config, policy)
                    break
                profile = self.store.get(s["results"]["BRAIN"])["payload"]["profile"]
                s["profile"] = max((profile, s["profile"]), key=PROFILES.index)
                self._persist(s, "BENCHMARKING")
            elif phase == "BENCHMARKING":
                if s["profile"] != "FAST" and "BENCHMARKER" not in s["results"]:
                    self._issue(s, ["BENCHMARKER"], config, policy)
                    break
                self._persist(s, "SPECIFICATION")
            elif phase == "SPECIFICATION":
                if "SPEC" not in s["results"]:
                    self._issue(s, ["SPEC"], config, policy)
                    break
                s["spec_ref"] = self.store.put(self.store.get(s["results"]["SPEC"])["payload"])
                self._persist(s, "SPEC_REVIEW")
            elif phase == "SPEC_REVIEW":
                self._checks(s, config, s["baseline"], red=True)
                if s["phase"] == "BLOCKED":
                    break
                if self.store.get(s["red"])["passed"]:
                    self._block(s, "RED_ALREADY_GREEN")
                elif s["profile"] == "HIGH_ASSURANCE":
                    self._approve_at(s, "APPROVED_FOR_DEVELOPMENT")
                else:
                    self._persist(s, "APPROVED_FOR_DEVELOPMENT")
            elif phase in {"APPROVED_FOR_DEVELOPMENT", "REWORK"}:
                self._persist(s, "IMPLEMENTATION")
            elif phase == "IMPLEMENTATION":
                if "DEVELOPER" not in s["results"]:
                    self._issue(s, ["DEVELOPER"], config, policy)
                    break
                files = self.store.get(s["baseline"]["artifact_ref"])
                proposal = self.store.get(s["results"]["DEVELOPER"])["payload"]["edits"]
                candidate = files | proposal
                version = digest(candidate)
                if version == s["baseline"]["artifact_ref"] or version in s["seen"]:
                    self._block(s, "NO_PROGRESS")
                else:
                    s["seen"].append(version)
                    s["candidate"] = self._snapshot(candidate, s["baseline"]["commit_sha"])
                    s["reviews"] = {}
                    self._persist(s, "DETERMINISTIC_VALIDATION")
            elif phase == "DETERMINISTIC_VALIDATION":
                self._checks(s, config, s["candidate"])
                if s["phase"] == "BLOCKED":
                    break
                s["blockers"] = [
                    f"CHECK_FAILED:{key}"
                    for key, ref in s["checks"].items()
                    if not self.store.get(ref)["passed"]
                ]
                self._persist(s, "CHANGES_REQUESTED" if s["blockers"] else "PARALLEL_REVIEW")
            elif phase == "PARALLEL_REVIEW":
                if any(role not in s["results"] for role in roles):
                    self._issue(s, roles, config, policy)
                    break
                s["reviews"] = {role: s["results"][role] for role in roles}
                self._persist(s, "QUALITY_GATE")
            elif phase == "QUALITY_GATE":
                sha = s["candidate"]["commit_sha"]
                reviews = {}
                for role, ref in s["reviews"].items():
                    report = self.store.get(ref)
                    if (
                        report["commit_sha"] != sha
                        or report["spec_version"] != s["spec_ref"]
                        or report["policy_version"] != s["policy_ref"]
                        or report["agent_id"] != role
                    ):
                        self._block(s, "STALE_REVIEW")
                        return s
                    reviews[role] = report["payload"]
                checks = {}
                for check in config["checks"]:
                    check_id = check["id"]
                    record = self.store.get(s["checks"][check_id])
                    if (
                        record["commit_sha"] != sha
                        or record["spec_version"] != s["spec_ref"]
                        or record["policy_version"] != s["policy_ref"]
                        or record["check_id"] != check_id
                    ):
                        self._block(s, "STALE_CHECK")
                        return s
                    checks[check_id] = record["passed"]
                s["blockers"] = gate(
                    policy, s["profile"], self.store.get(s["spec_ref"]), roles, checks, reviews
                )
                self._evidence(
                    s,
                    {
                        "origin": "gate",
                        "commit_sha": sha,
                        "spec_version": s["spec_ref"],
                        "policy_version": s["policy_ref"],
                        "blockers": s["blockers"],
                    },
                )
                if s["blockers"]:
                    self._persist(s, "CHANGES_REQUESTED")
                elif s["profile"] == "HIGH_ASSURANCE":
                    self._approve_at(s, "ACCEPTED")
                else:
                    self._persist(s, "ACCEPTED")
            elif phase == "CHANGES_REQUESTED":
                self._rework(s, policy)
            elif phase == "ACCEPTED":
                self._persist(s, "DELIVERY")
            elif phase == "DELIVERY":
                files = self.store.get(s["candidate"]["artifact_ref"])
                try:
                    verify_snapshot(
                        self.store.root / "git",
                        s["candidate"]["commit_sha"],
                        s["baseline"]["commit_sha"],
                        files,
                    )
                except ValueError:
                    self._block(s, "INVALID_DELIVERY_COMMIT")
                    return s
                final = dict(
                    s["candidate"],
                    source_sha=config["source_sha"],
                    files=files,
                    spec_version=s["spec_ref"],
                    policy_version=s["policy_ref"],
                    red=s["red"],
                    checks=s["checks"],
                    reviews=s["reviews"],
                    decisions=s["decisions"],
                    profile=s["profile"],
                )
                s["delivery_ref"] = self.store.put(final)
                self._persist(s, "COMPLETED")
        return s

    def submit(self, task_id: str, payload: dict | None, *, origin: str = "submitted") -> bool:
        with self.store.lock():
            s = self.store.load()
            task = next((t for t in s["pending"].values() if t["task_id"] == task_id), None)
            if task is None:
                raise ValueError("Tarea desconocida, obsoleta o ya incorporada")
            role = task["agent_id"]
            try:
                if now() - task["issued_ms"] >= TASK_TIMEOUT_MS:
                    raise ValueError("Respuesta fuera de plazo")
                validate_result(role, payload)
                if len(canonical(payload)) > MAX_RESULT_BYTES:
                    raise ValueError("Resultado demasiado grande")
                if role == "DEVELOPER":
                    config = self.store.get(s["config_ref"])
                    edits = payload["edits"]
                    if (
                        set(edits) - set(config["editable"])
                        or any("\0" in v for v in edits.values())
                        or sum(len(v.encode()) for v in edits.values()) > 128_000
                    ):
                        raise ValueError("Cambio fuera de la autorización")
                if role in {"QA", "UI_UX", "SECOPS"}:
                    known = {r["id"] for r in self.store.get(s["spec_ref"])["requirements"]}
                    if set(payload["covered"]) - known:
                        raise ValueError("Referencias a requisitos inexistentes")
            except (ValueError, TypeError):
                s["events"].append(
                    {"event": "invalid_or_failed_result", "task_id": task_id, "at_ms": now()}
                )
                del s["pending"][role]
                self.store.save(s)
                return False
            envelope = {k: v for k, v in task.items() if k not in {"context", "prompt"}}
            s["results"][role] = self._evidence(
                s,
                envelope
                | {
                    "payload": payload,
                    "origin": origin,
                    "received_ms": now(),
                    "tokens": None,
                    "cost": None,
                },
            )
            del s["pending"][role]
            self.store.save(s)
            return True

    def approve(self, token: str, operator: str, accept: bool) -> None:
        with self.store.lock():
            s = self.store.load()
            approval = s["approval"]
            if (
                s["phase"] != "HUMAN_APPROVAL_REQUIRED"
                or approval["token"] != token
                or not operator.strip()
                or len(operator) > 120
            ):
                raise ValueError("Decisión obsoleta o identidad inválida")
            s["decisions"].append(
                self._evidence(
                    s,
                    approval
                    | {
                        "operator": operator,
                        "accepted": accept,
                        "at_ms": now(),
                        "origin": "operator",
                    },
                )
            )
            s["approval"] = None
            self._persist(s, approval["target"] if accept else "CANCELLED")

    def cancel(self) -> None:
        with self.store.lock():
            s = self.store.load()
            s["pending"] = {}
            self._persist(s, "CANCELLED")

    def state(self) -> dict:
        with self.store.lock():
            return self.store.load()

    def delivery(self) -> dict:
        with self.store.lock():
            s = self.store.load()
            if s["phase"] != "COMPLETED":
                raise ValueError("No se ha aprobado la entrega")
            final = self.store.get(s["delivery_ref"])
            for ref in s["evidence"]:
                self.store.get(ref)
            if digest(final["files"]) != final["artifact_ref"]:
                raise ValueError("Candidato alterado")
            verify_snapshot(
                self.store.root / "git",
                final["commit_sha"],
                s["baseline"]["commit_sha"],
                final["files"],
            )
            return final
