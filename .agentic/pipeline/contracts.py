"""Contratos JSON y puerta de calidad sin E/S ni efectos sobre el repositorio."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Iterable
from typing import Any

MAX_JSON_BYTES = 4 * 1024 * 1024
PROFILES = frozenset({"FAST", "STANDARD", "HIGH_ASSURANCE"})
REVIEW_ROLES = frozenset({"QA", "UI_UX", "SECOPS"})
ROLES = REVIEW_ROLES | {"BRAIN", "BENCHMARKER", "SPEC", "DEVELOPER"}
_PASSING_VERDICTS = frozenset({"PASS", "PASS_WITH_WARNINGS"})
_VERDICTS = _PASSING_VERDICTS | {"FAIL", "NA", "NOT_APPLICABLE", "INCONCLUSIVE"}
_CONFIDENCE = frozenset({"LOW", "MEDIUM", "HIGH"})
_SEVERITY = _CONFIDENCE | {"CRITICAL", "INFORMATIONAL"}
_PATH_COMPONENT = re.compile(r"[a-zA-Z0-9_.-]+")
_BUDGET_FIELDS = frozenset(
    {
        "max_calls",
        "max_attempts",
        "max_rounds",
        "max_context_bytes",
        "concurrency",
    }
)
_FINDING_FIELDS = frozenset(
    {
        "id",
        "category",
        "severity",
        "confidence",
        "requirement",
        "file",
        "location",
        "description",
        "evidence",
        "reproduction",
        "impact",
        "recommendation",
        "resolution",
    }
)


def _validate_json(value: Any) -> None:
    if type(value) is str:
        value.encode("utf-8")  # Rechaza sustitutos Unicode aislados.
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON no admite números no finitos")
    elif type(value) is list:
        for item in value:
            _validate_json(item)
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ValueError("Las claves JSON deben ser cadenas")
            key.encode("utf-8")
            _validate_json(item)
    elif value is not None and type(value) not in (bool, int):
        raise ValueError("Tipo no admitido por JSON")


def canonical(value: Any) -> bytes:
    """Serializa un valor JSON como UTF-8 compacto, con claves ordenadas."""
    try:
        _validate_json(value)
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (UnicodeError, RecursionError):
        raise ValueError("Unicode o anidamiento inválido en JSON") from None


def digest(value: Any) -> str:
    """Devuelve el SHA-256 hexadecimal del JSON canónico."""
    return hashlib.sha256(canonical(value)).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clave JSON duplicada")
        result[key] = value
    return result


def _reject_constant(_constant: str) -> None:
    raise ValueError("JSON no admite números no finitos")


def decode(raw: bytes) -> dict[str, Any]:
    """Lee un objeto JSON UTF-8 estricto de hasta MAX_JSON_BYTES."""
    if type(raw) is not bytes or len(raw) > MAX_JSON_BYTES:
        raise ValueError("Se esperaban bytes JSON dentro del límite de tamaño")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        if type(value) is not dict:
            raise ValueError("El JSON debe contener un objeto en la raíz")
        _validate_json(value)
    except (UnicodeError, RecursionError):
        raise ValueError("Unicode o anidamiento inválido en JSON") from None
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict or any(type(key) is not str for key in value):
        raise ValueError(f"{label} debe ser un objeto con claves de texto")
    return value


def _fields(
    value: Any,
    label: str,
    fields: set[str] | frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    obj = _object(value, label)
    if not fields <= obj.keys() or not obj.keys() <= fields | optional:
        raise ValueError(f"Campos incorrectos en {label}")
    return obj


def _text(value: Any, label: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{label} debe ser texto")


def _choice(value: Any, choices: frozenset[str], label: str) -> None:
    if type(value) is not str or value not in choices:
        raise ValueError(f"Valor no admitido para {label}")


def _list(value: Any, label: str) -> list[Any]:
    if type(value) is not list:
        raise ValueError(f"{label} debe ser una lista")
    return value


def _text_list(value: Any, label: str) -> None:
    for item in _list(value, label):
        _text(item, label)


def _models(value: Any, *, partial: bool) -> None:
    models = _object(value, "models/rutas")
    if not models.keys() <= ROLES or (not partial and models.keys() != ROLES):
        raise ValueError("Roles incorrectos en models/rutas")
    for model in models.values():
        _text(model, "modelo")


def check_policy(policy: Any) -> None:
    """Valida la política exacta y las rutas opcionales por perfil."""
    obj = _fields(policy, "policy", _BUDGET_FIELDS | {"version", "models"}, frozenset({"routes"}))
    _text(obj["version"], "version")
    for key in sorted(_BUDGET_FIELDS):
        if type(obj[key]) is not int or obj[key] <= 0:
            raise ValueError(f"{key} debe ser un entero positivo")
    _models(obj["models"], partial=False)
    if "routes" in obj:
        for profile, overrides in _object(obj["routes"], "routes").items():
            _choice(profile, PROFILES, "perfil")
            _models(overrides, partial=True)


def safe_path(path: object) -> bool:
    """Comprueba la sintaxis léxica de una ruta relativa; no consulta el disco."""
    return type(path) is str and all(
        part == ".github" or (not part.startswith(".") and _PATH_COMPONENT.fullmatch(part))
        for part in path.split("/")
    )


def _validate_spec(payload: Any) -> None:
    obj = _fields(payload, "SPEC", {"requirements"})
    ids: set[str] = set()
    requirements = _list(obj["requirements"], "requirements")
    if not 1 <= len(requirements) <= 64:
        raise ValueError("La SPEC requiere entre uno y 64 requisitos")
    mandatory = False
    for raw in requirements:
        requirement = _fields(raw, "requisito", {"id", "criterion", "mandatory"})
        req_id = requirement["id"]
        _text(req_id, "id de requisito")
        _text(requirement["criterion"], "criterion")
        if not req_id.strip() or not requirement["criterion"].strip():
            raise ValueError("Cada requisito necesita identificador y criterio")
        if type(requirement["mandatory"]) is not bool:
            raise ValueError("mandatory debe ser un booleano")
        if req_id in ids:
            raise ValueError("ID de requisito duplicado")
        ids.add(req_id)
        mandatory |= requirement["mandatory"]
    if not mandatory:
        raise ValueError("La SPEC requiere algún requisito obligatorio")


def _validate_review(role: str, payload: Any) -> None:
    obj = _fields(payload, role, {"verdict", "findings", "covered", "summary"})
    _choice(obj["verdict"], _VERDICTS, "verdict")
    _text(obj["summary"], "summary")
    _text_list(obj["covered"], "covered")
    for raw in _list(obj["findings"], "findings"):
        finding = _fields(raw, "hallazgo", _FINDING_FIELDS)
        for value in finding.values():
            _text(value, "campo del hallazgo")
        _choice(finding["severity"], _SEVERITY, "severity")
        _choice(finding["confidence"], _CONFIDENCE, "confidence")


def validate_result(role: str, payload: Any) -> None:
    """Valida solo la carga útil del rol, no su emisor ni el SHA del sobre."""
    _choice(role, ROLES, "rol")
    if role == "BRAIN":
        obj = _fields(payload, role, {"summary", "profile"})
        _text(obj["summary"], "summary")
        _choice(obj["profile"], PROFILES, "perfil")
    elif role == "BENCHMARKER":
        obj = _fields(payload, role, {"summary", "references"})
        _text(obj["summary"], "summary")
        _text_list(obj["references"], "references")
    elif role == "SPEC":
        _validate_spec(payload)
    elif role == "DEVELOPER":
        obj = _fields(payload, role, {"edits", "summary"})
        _text(obj["summary"], "summary")
        for path, text in _object(obj["edits"], "edits").items():
            if not safe_path(path):
                raise ValueError("Ruta de edición inválida")
            _text(text, "contenido de edición")
    else:
        _validate_review(role, payload)


def gate(
    policy: dict[str, Any],
    profile: str,
    spec: dict[str, Any],
    reviewer_roles: Iterable[str],
    check_results: dict[str, bool],
    reviews: dict[str, dict[str, Any]],
) -> list[str]:
    """Devuelve códigos bloqueantes; el motor verifica el inventario y los sobres.

    La aprobación humana para HIGH_ASSURANCE también es responsabilidad del
    motor: esta función no recibe identidad ni hash de una aprobación.
    """
    check_policy(policy)
    _choice(profile, PROFILES, "perfil")
    validate_result("SPEC", spec)
    if isinstance(reviewer_roles, (str, bytes, dict)) or not isinstance(reviewer_roles, Iterable):
        raise ValueError("Se esperaba una colección de roles revisores")
    required = {"QA", "SECOPS"}
    for role in reviewer_roles:
        _choice(role, REVIEW_ROLES, "rol revisor")
        required.add(role)
    checks = _object(check_results, "check_results")
    reports = _object(reviews, "reviews")
    for role, report in reports.items():
        _choice(role, REVIEW_ROLES, "rol revisor")
        validate_result(role, report)

    blockers = [] if checks else ["CHECKS_MISSING"]
    for check_id, passed in sorted(checks.items()):
        if type(passed) is not bool:
            raise ValueError("El resultado de cada control debe ser un booleano")
        if not passed:
            blockers.append(f"CHECK_FAILED:{check_id}")
    for role in sorted(required):
        if role not in reports:
            blockers.append(f"REVIEW_MISSING:{role}")
        elif reports[role]["verdict"] not in _PASSING_VERDICTS:
            blockers.append(f"REVIEW_VERDICT:{role}:{reports[role]['verdict']}")
    if "QA" in reports:
        covered = set(reports["QA"]["covered"])
        for req in spec["requirements"]:
            if req["mandatory"] and req["id"] not in covered:
                blockers.append(f"QA_UNCOVERED:{req['id']}")
    blocking_severities = {"HIGH", "CRITICAL"}
    if profile == "HIGH_ASSURANCE":
        blocking_severities.add("MEDIUM")
    for role, report in sorted(reports.items()):
        for finding in report["findings"]:
            if finding["severity"] in blocking_severities:
                blockers.append(f"FINDING_BLOCKING:{role}:{finding['id']}")
    return list(dict.fromkeys(blockers))
