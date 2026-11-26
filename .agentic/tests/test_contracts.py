"""Pruebas unitarias de contratos y de la puerta defensiva."""

from __future__ import annotations

import hashlib
import unittest

from pipeline.contracts import (
    canonical,
    check_policy,
    decode,
    digest,
    gate,
    safe_path,
    validate_result,
)


def policy() -> dict:
    return {
        "version": "1",
        "max_calls": 24,
        "max_attempts": 2,
        "max_rounds": 3,
        "max_context_bytes": 8192,
        "concurrency": 2,
        "models": dict.fromkeys(
            ("BRAIN", "BENCHMARKER", "SPEC", "DEVELOPER", "QA", "UI_UX", "SECOPS"),
            "fixture",
        ),
    }


def spec() -> dict:
    return {
        "requirements": [
            {"id": "R1", "criterion": "La opción desactivada se conserva", "mandatory": True},
            {"id": "R2", "criterion": "La ayuda explica la opción", "mandatory": False},
        ]
    }


def review(verdict: str = "PASS", covered: tuple[str, ...] = ("R1",)) -> dict:
    return {"verdict": verdict, "findings": [], "covered": list(covered), "summary": "Revisado"}


def finding(severity: str) -> dict:
    return {
        "id": "F1",
        "category": "Regresión",
        "severity": severity,
        "confidence": "LOW",
        "requirement": "R1",
        "file": "app.py",
        "location": "12",
        "description": "La opción desactivada se ignora",
        "evidence": "Prueba local fallida",
        "reproduction": "Ejecutar la prueba unitaria local con la opción desactivada",
        "impact": "Se pierde la configuración",
        "recommendation": "Respetar la opción",
        "resolution": "Pendiente",
    }


class JsonTests(unittest.TestCase):
    def test_canonical_utf8_stable_and_sha256(self) -> None:
        expected = '{"a":[true,null],"z":"tebeó"}'.encode()
        value = {"z": "tebeó", "a": [True, None]}
        self.assertEqual(canonical(value), expected)
        self.assertEqual(canonical(dict(reversed(tuple(value.items())))), expected)
        self.assertEqual(digest(value), hashlib.sha256(expected).hexdigest())
        self.assertEqual(decode(expected), value)

    def test_canonical_does_not_coerce_python_types_or_non_finite(self) -> None:
        for value in ({1: "x"}, {"x": (1,)}, float("inf"), {"x": [float("nan")]}, "\ud800"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                canonical(value)

    def test_decode_rejects_invalid_or_ambiguous_json(self) -> None:
        for raw in (
            b'{"x":0,"x":1}',
            b'{"outer":[{"x":0,"\\u0078":1}]}',
            b'{"x":NaN}',
            b'{"x":Infinity}',
            b'{"x":-Infinity}',
            b'{"x":1e1000}',
            b"[]",
            b"null",
            b"{} {}",
            b"{",
            b'{"x":"\xff"}',
            b'{"x":"\\ud800"}',
            b"\xff\xfe{\x00}\x00",
            bytearray(b"{}"),
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                decode(raw)

    def test_decode_limits_input_even_with_valid_json_and_deep_nesting(self) -> None:
        for raw in (
            b"{}" + b" " * (8 * 1024 * 1024),
            b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}",
        ):
            with self.assertRaises(ValueError):
                decode(raw)


class PolicyTests(unittest.TestCase):
    def test_exact_policy_with_optional_per_profile_overrides(self) -> None:
        self.assertIsNone(check_policy(policy()))
        self.assertIsNone(check_policy(policy() | {"routes": {"FAST": {"QA": "other"}}}))

    def test_policy_rejects_missing_extra_invalid_keys_and_budget_types(self) -> None:
        missing = policy()
        del missing["version"]
        cases = [
            missing,
            policy() | {"other": True},
            policy() | {"version": 1},
            policy() | {"models": {"QA": "fixture"}},
        ]
        for key in ("max_calls", "max_attempts", "max_rounds", "max_context_bytes", "concurrency"):
            cases.extend(policy() | {key: bad} for bad in (True, 0, -1, 1.0, "2"))
        for changes in (
            {"models": []},
            {"models": {"OTHER": "fixture"}},
            {"models": {"QA": True}},
            {"routes": None},
            {"routes": {"UNKNOWN": {}}},
            {"routes": {"FAST": "fixture"}},
            {"routes": {"FAST": {"OTHER": "fixture"}}},
            {"routes": {"FAST": {"QA": []}}},
        ):
            cases.append(policy() | changes)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                check_policy(candidate)


class ResultTests(unittest.TestCase):
    def test_every_role_has_a_strict_valid_payload(self) -> None:
        for role, payload in (
            ("BRAIN", {"summary": "Propuesta", "profile": "FAST"}),
            ("BENCHMARKER", {"summary": "Comparación", "references": ["Referencia"]}),
            ("SPEC", spec()),
            ("DEVELOPER", {"edits": {"src/app.py": "# revisión"}, "summary": "Cambio"}),
            ("DEVELOPER", {"edits": {}, "summary": "Sin cambios"}),
            ("QA", review()),
            ("SECOPS", review()),
            ("UI_UX", review()),
        ):
            with self.subTest(role=role, payload=payload):
                self.assertIsNone(validate_result(role, payload))
                with self.assertRaises(ValueError):
                    validate_result(role, payload | {"commit": "no es parte del payload"})
                with self.assertRaises(ValueError):
                    validate_result(role, payload | {"emitter": "QA"})

    def test_schema_rejects_wrong_types_duplicate_ids_and_untrusted_envelope_fields(self) -> None:
        requirement = spec()["requirements"][0]
        for role, payload in (
            ("UNKNOWN", {}),
            ("QA", []),
            ("BRAIN", {"summary": "Propuesta", "profile": "fast"}),
            ("BENCHMARKER", {"summary": "Comparación", "references": "Referencia"}),
            ("BENCHMARKER", {"summary": "Comparación", "references": [1]}),
            ("SPEC", {"requirements": [requirement, dict(requirement)]}),
            ("SPEC", {"requirements": [requirement | {"mandatory": 1}]}),
            ("DEVELOPER", {"edits": {"../app.py": "texto"}, "summary": "Cambio"}),
            ("DEVELOPER", {"edits": {"app.py": False}, "summary": "Cambio"}),
            ("UI_UX", review("UNKNOWN")),
            ("UI_UX", review() | {"covered": [1]}),
            ("SECOPS", review() | {"findings": [finding("UNKNOWN")]}),
            ("SECOPS", review() | {"findings": [finding("HIGH") | {"confidence": "CRITICAL"}]}),
            ("QA", review() | {"findings": [finding("HIGH") | {"resolution": False}]}),
            ("QA", review() | {"findings": [finding("HIGH") | {"commit": "externo al esquema"}]}),
        ):
            with self.subTest(role=role, payload=payload), self.assertRaises(ValueError):
                validate_result(role, payload)

    def test_safe_path_accepts_only_permitted_ascii_components(self) -> None:
        for path in ("README.md", "src/a-B_1.py", ".github/workflows/check.yml", "a/b.c.d"):
            with self.subTest(path=path):
                self.assertTrue(safe_path(path))
        for path in (
            "",
            "/app.py",
            "a//b",
            "a/",
            "./a",
            "a/../b",
            ".git/config",
            ".GIT/config",
            "a/.hidden/b",
            ".github/.secret",
            "C:config",
            "a\\b",
            "a b",
            "a\n",
            "cómic.py",
            "a\x00b",
            None,
            3,
        ):
            with self.subTest(path=path):
                self.assertFalse(safe_path(path))


class GateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reviews = {"QA": review(), "SECOPS": review(covered=())}

    def blockers(
        self,
        profile: str = "STANDARD",
        roles: tuple[str, ...] = ("QA", "SECOPS"),
        checks: dict[str, bool] | None = None,
    ) -> list[str]:
        return gate(
            policy(),
            profile,
            spec(),
            roles,
            {"compile": True, "tests": True} if checks is None else checks,
            self.reviews,
        )

    def test_passing_checks_and_required_reviews_allow_any_profile(self) -> None:
        for profile in ("FAST", "STANDARD", "HIGH_ASSURANCE"):
            with self.subTest(profile=profile):
                self.assertEqual(self.blockers(profile), [])

    def test_failed_check_blocks_even_if_all_reviewers_pass(self) -> None:
        self.assertIn("CHECK_FAILED:tests", self.blockers(checks={"compile": True, "tests": False}))
        with self.assertRaises(ValueError):
            self.blockers(checks={"tests": 1})

    def test_empty_check_results_do_not_pass_vacuously(self) -> None:
        self.assertEqual(self.blockers(checks={}), ["CHECKS_MISSING"])

    def test_qa_secops_and_declared_ui_are_required(self) -> None:
        self.reviews.clear()
        self.assertEqual(
            set(self.blockers(roles=("UI_UX",))),
            {
                "REVIEW_MISSING:QA",
                "REVIEW_MISSING:SECOPS",
                "REVIEW_MISSING:UI_UX",
            },
        )

    def test_only_qa_coverage_counts_and_optional_requirement_does_not_block(self) -> None:
        self.reviews = {"QA": review(covered=("R2",)), "SECOPS": review(covered=("R1",))}
        self.assertEqual(self.blockers(), ["QA_UNCOVERED:R1"])

    def test_non_passing_required_verdict_blocks(self) -> None:
        for verdict in ("NA", "NOT_APPLICABLE", "INCONCLUSIVE", "FAIL"):
            self.reviews["SECOPS"]["verdict"] = verdict
            with self.subTest(verdict=verdict):
                self.assertIn(f"REVIEW_VERDICT:SECOPS:{verdict}", self.blockers())

    def test_high_and_critical_block_despite_pass_even_for_optional_judge(self) -> None:
        for severity in ("HIGH", "CRITICAL"):
            self.reviews["UI_UX"] = review() | {"findings": [finding(severity)]}
            with self.subTest(severity=severity):
                self.assertIn("FINDING_BLOCKING:UI_UX:F1", self.blockers())

    def test_medium_blocks_only_high_assurance_and_low_never_blocks(self) -> None:
        self.reviews["QA"]["findings"] = [finding("MEDIUM")]
        self.assertEqual(self.blockers("FAST"), [])
        self.assertEqual(self.blockers("STANDARD"), [])
        self.assertEqual(self.blockers("HIGH_ASSURANCE"), ["FINDING_BLOCKING:QA:F1"])
        self.reviews["QA"]["findings"] = [finding("LOW"), finding("INFORMATIONAL") | {"id": "F2"}]
        self.reviews["QA"]["verdict"] = "PASS_WITH_WARNINGS"
        self.assertEqual(self.blockers("HIGH_ASSURANCE"), [])


if __name__ == "__main__":
    unittest.main()
