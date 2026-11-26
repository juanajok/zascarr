"""Contrato E2E offline: decisiones simuladas, comprobaciones reales."""

from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from pipeline.engine import TASK_TIMEOUT_MS, Engine, transition, validate_config
from pipeline.runner import Runner

POLICY = dict(
    version="test",
    max_calls=30,
    max_attempts=2,
    max_rounds=2,
    max_context_bytes=12000,
    concurrency=3,
    models=dict.fromkeys(
        ("BRAIN", "BENCHMARKER", "SPEC", "DEVELOPER", "QA", "SECOPS", "UI_UX"), "fixture"
    ),
)


def fixture(irregular: bool = False) -> dict:
    return {
        "request": "Corrige la etiqueta de bienvenida",
        "risk": ["ui"] if irregular else [],
        "editable": ["label.txt"],
        "context": ["label.txt"],
        "checks": [
            {"id": "label", "kind": "contains", "path": "label.txt", "text": "Tu tebeoteca"}
        ],
        "red": "label",
        "source_sha": "a" * 40,
    }


def answer(role: str, bad: bool = False) -> dict:
    return {
        "BRAIN": {"summary": "Cambio localizado", "profile": "FAST"},
        "BENCHMARKER": {"summary": "Mantener la etiqueta existente", "references": ["label.txt"]},
        "SPEC": {
            "requirements": [{"id": "R-01", "criterion": "Dice Tu tebeoteca", "mandatory": True}]
        },
        "DEVELOPER": {
            "edits": {"label.txt": "Nombre incorrecto" if bad else "Tu tebeoteca\n"},
            "summary": "Corrige etiqueta",
        },
        **{
            r: {"verdict": "PASS", "summary": "Fixture", "covered": ["R-01"], "findings": []}
            for r in ("QA", "SECOPS", "UI_UX")
        },
    }[role]


class EngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "run"

    def new(self, config: dict | None = None, policy: dict | None = None) -> Engine:
        engine = Engine(self.root, Runner())
        engine.create(config or fixture(), policy or POLICY, {"label.txt": "Biblioteca\n"})
        return engine

    def drive(self, engine: Engine, *, bad: bool = False) -> dict:
        for _ in range(30):
            state = engine.advance()
            if not state["pending"]:
                return state
            for task in state["pending"].values():
                engine.submit(task["task_id"], answer(task["agent_id"], bad))
        self.fail("No terminó dentro del límite")

    def test_success_after_reopening_and_parallel_contexts(self) -> None:
        engine = self.new(fixture(True))
        state = engine.advance()
        task = next(iter(state["pending"].values()))
        engine.submit(task["task_id"], answer("BRAIN"))
        engine = Engine(self.root, Runner())
        for role in ("BENCHMARKER", "SPEC", "DEVELOPER"):
            state = engine.advance()
            task = next(iter(state["pending"].values()))
            self.assertEqual(task["agent_id"], role)
            engine.submit(task["task_id"], answer(role))
        state = engine.advance()
        self.assertEqual(set(state["pending"]), {"QA", "SECOPS", "UI_UX"})
        for task in state["pending"].values():
            self.assertEqual(task["commit_sha"], state["candidate"]["commit_sha"])
            self.assertNotIn("reviews", task["context"])
            engine.submit(task["task_id"], answer(task["agent_id"]))
        done = engine.advance()
        self.assertEqual(done["phase"], "COMPLETED")
        self.assertEqual(done["calls"], 7)
        self.assertEqual(engine.delivery()["files"]["label.txt"], "Tu tebeoteca\n")

    def test_repeated_bad_change_blocks_before_judges(self) -> None:
        state = self.drive(self.new(), bad=True)
        self.assertEqual(state["phase"], "BLOCKED")
        self.assertNotIn("PARALLEL_REVIEW", [e["to"] for e in state["history"]])

    def test_malformed_retries_and_stale_ignored(self) -> None:
        engine = self.new()
        task = engine.advance()["pending"]["BRAIN"]
        self.assertFalse(engine.submit(task["task_id"], {"summary": 0}))
        new = engine.advance()["pending"]["BRAIN"]
        self.assertNotEqual(new["task_id"], task["task_id"])
        with self.assertRaises(ValueError):
            engine.submit(task["task_id"], answer("BRAIN"))
        self.assertTrue(engine.submit(new["task_id"], answer("BRAIN")))

    def test_budget_blocks_and_cancel_has_no_delivery(self) -> None:
        engine = self.new(policy=POLICY | {"max_calls": 1})
        task = engine.advance()["pending"]["BRAIN"]
        engine.submit(task["task_id"], answer("BRAIN"))
        self.assertEqual(engine.advance()["phase"], "BLOCKED")
        with self.assertRaises(ValueError):
            engine.delivery()

    def test_cancel_invalidates_pending(self) -> None:
        engine = self.new()
        task = engine.advance()["pending"]["BRAIN"]
        engine.cancel()
        self.assertEqual(engine.advance()["phase"], "CANCELLED")
        with self.assertRaises(ValueError):
            engine.submit(task["task_id"], answer("BRAIN"))

    def test_human_approval_binds_spec_and_candidate(self) -> None:
        engine = self.new(fixture() | {"risk": ["auth"]})
        state = self.drive(engine)
        self.assertEqual(state["phase"], "HUMAN_APPROVAL_REQUIRED")
        with self.assertRaises(ValueError):
            engine.approve("a" * 64, "Operadora", True)
        engine.approve(state["approval"]["token"], "Operadora", True)
        state = self.drive(engine)
        self.assertEqual(state["phase"], "HUMAN_APPROVAL_REQUIRED")
        engine.approve(state["approval"]["token"], "Operadora", True)
        self.assertEqual(engine.advance()["phase"], "COMPLETED")

    def test_tampered_evidence_prevents_delivery(self) -> None:
        engine = self.new()
        state = self.drive(engine)
        self.assertEqual(state["phase"], "COMPLETED")
        evidence = self.root / "objects" / state["checks"]["label"]
        evidence.write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "alterada"):
            engine.delivery()

    def test_transition_does_not_allow_skipping_gates(self) -> None:
        with self.assertRaises(ValueError):
            transition({"phase": "REQUESTED", "history": []}, "COMPLETED")

    def test_expired_attempt_gets_new_id_and_spends_budget(self) -> None:
        engine = self.new()
        first = engine.advance()["pending"]["BRAIN"]
        with patch("pipeline.engine.now", return_value=first["issued_ms"] + TASK_TIMEOUT_MS):
            second = engine.advance()["pending"]["BRAIN"]
        self.assertNotEqual(first["task_id"], second["task_id"])
        self.assertEqual(engine.state()["calls"], 2)
        self.assertEqual(engine.state()["events"][-1]["event"], "task_timeout")

    def test_two_concurrent_submissions_cannot_both_succeed(self) -> None:
        engine = self.new()
        task = engine.advance()["pending"]["BRAIN"]

        def submit(_: int) -> bool:
            try:
                return Engine(self.root, Runner()).submit(task["task_id"], answer("BRAIN"))
            except ValueError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(submit, range(2))), [False, True])
        self.assertEqual(len(engine.state()["evidence"]), 1)

    def test_cannot_scope_policy_or_independent_tests_as_editable(self) -> None:
        for path in ("tests/oracle.py", ".github/workflows/rules.yml", ".agentic/policy.json"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_config(fixture() | {"editable": [path]})

    def test_old_approval_cannot_approve_delivery(self) -> None:
        engine = self.new(fixture() | {"risk": ["auth"]})
        spec = self.drive(engine)["approval"]["token"]
        engine.approve(spec, "Operadora", True)
        release = self.drive(engine)["approval"]["token"]
        self.assertNotEqual(spec, release)
        with self.assertRaises(ValueError):
            engine.approve(spec, "Operadora", True)

    def test_rework_sees_failed_candidate_and_corrects_it(self) -> None:
        engine = self.new()
        for role in ("BRAIN", "SPEC", "DEVELOPER"):
            task = engine.advance()["pending"][role]
            engine.submit(task["task_id"], answer(role, bad=True))
        repair = engine.advance()["pending"]["DEVELOPER"]
        self.assertEqual(repair["context"]["previous_edits"]["label.txt"], "Nombre incorrecto")
        self.assertFalse(repair["context"]["previous_checks"]["label"]["passed"])
        engine.submit(repair["task_id"], answer("DEVELOPER"))
        self.assertEqual(self.drive(engine)["phase"], "COMPLETED")

    def test_high_defensive_finding_blocks_green_candidate(self) -> None:
        engine = self.new(policy=POLICY | {"max_rounds": 1})
        for role in ("BRAIN", "SPEC", "DEVELOPER"):
            task = engine.advance()["pending"][role]
            engine.submit(task["task_id"], answer(role))
        reviews = engine.advance()["pending"]
        finding = dict.fromkeys(
            (
                "category",
                "file",
                "location",
                "description",
                "evidence",
                "reproduction",
                "impact",
                "recommendation",
                "resolution",
            ),
            "Fixture defensivo no ejecutable",
        ) | {
            "id": "DEF-01",
            "severity": "HIGH",
            "confidence": "HIGH",
            "requirement": "R-01",
        }
        engine.submit(reviews["QA"]["task_id"], answer("QA"))
        engine.submit(reviews["SECOPS"]["task_id"], answer("SECOPS") | {"findings": [finding]})
        result = engine.advance()
        self.assertEqual(result["phase"], "BLOCKED")
        self.assertIn("FINDING_BLOCKING:SECOPS:DEF-01", result["blockers"])
        with self.assertRaises(ValueError):
            engine.delivery()

    def test_docker_exit_one_is_not_proof_of_expected_red(self) -> None:
        config = fixture() | {
            "checks": [
                {
                    "id": "label",
                    "kind": "docker",
                    "image": "sha256:" + "a" * 64,
                    "argv": ["benign-test-driver"],
                    "timeout": 1,
                }
            ]
        }
        engine = self.new(config)
        output = {"kind": "docker", "passed": False, "exit_code": 1, "duration_ms": 10}
        with patch.object(engine.runner, "run", return_value=output):
            state = self.drive(engine)
        self.assertEqual(state["phase"], "BLOCKED")
        self.assertIn("CHECK_INFRASTRUCTURE:label", state["blockers"])
