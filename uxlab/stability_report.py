#!/usr/bin/env python3
"""Resume estabilidad entre repeticiones Playwright, sin confundirla con retries.

Uso: python3 uxlab/stability_report.py results.json summary.md summary.json 3
No usa red ni librerías adicionales; el estado viene de Playwright, no de IA.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def extract_runs(suites: list[dict]) -> list[dict]:
    """Cada elemento de results[] es una ejecución (retries=0 en UXLab)."""
    rows: list[dict] = []

    def visit(suite: dict):
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                for result in test.get("results", []):
                    rows.append({
                        "scenario": spec.get("title", ""),
                        "project": test.get("projectName", ""),
                        "status": result.get("status", "unknown"),
                        "duration_ms": result.get("duration", 0),
                    })
        for nested in suite.get("suites", []):
            visit(nested)

    for suite in suites:
        visit(suite)
    return rows


def summarise(report: dict, repeat_each: int) -> dict:
    rows = extract_runs(report.get("suites", []))
    groups = defaultdict(list)
    for row in rows:
        groups[(row["scenario"], row["project"])].append(row)
    scenarios = []
    for (scenario, project), items in sorted(groups.items()):
        passed = sum(item["status"] == "passed" for item in items)
        failed = sum(item["status"] != "passed" for item in items)
        incomplete = len(items) != repeat_each
        if incomplete:
            verdict = "incompleto"
        elif passed and failed:
            verdict = "intermitente"
        elif failed:
            verdict = "fallo_sistematico"
        else:
            verdict = "consistente"
        scenarios.append({
            "scenario": scenario,
            "project": project,
            "executions": len(items),
            "passed": passed,
            "failed": failed,
            "duration_ms": sum(int(x["duration_ms"] or 0) for x in items),
            "verdict": verdict,
        })
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repeat_each": repeat_each,
        "total_executions": len(rows),
        "passed": sum(r["status"] == "passed" for r in rows),
        "failed": sum(r["status"] != "passed" for r in rows),
        "groups": scenarios,
        "intermittent_groups": sum(s["verdict"] == "intermitente" for s in scenarios),
        "incomplete_groups": sum(s["verdict"] == "incompleto" for s in scenarios),
        "systematic_failure_groups": sum(
            s["verdict"] == "fallo_sistematico" for s in scenarios
        ),
    }
    if not rows:
        raise ValueError("results.json no contiene ejecuciones Playwright")
    return summary


def to_markdown(summary: dict) -> str:
    lines = [
        "# UXLab — estabilidad Playwright",
        "",
        f"Repeticiones por escenario/dispositivo: **{summary['repeat_each']}**",
        f"Ejecuciones: **{summary['total_executions']}**; "
        f"correctas **{summary['passed']}**; fallidas **{summary['failed']}**.",
        f"Grupos intermitentes: **{summary['intermittent_groups']}**; "
        f"incompletos: **{summary['incomplete_groups']}**; "
        f"fallos sistemáticos: **{summary['systematic_failure_groups']}**.",
        "",
        "| Escenario | Dispositivo | Pasadas | Correctas | Fallidas | Diagnóstico |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for group in summary["groups"]:
        lines.append(
            f"| {group['scenario'].replace('|', '/')} | {group['project']} | "
            f"{group['executions']} | {group['passed']} | "
            f"{group['failed']} | {group['verdict']} |"
        )
    lines += [
        "",
        "**Interpretación:** 0 intermitencias observadas en tres pasadas "
        "no equivale a demostrar ausencia de flakiness. "
        "Los errores repetidos 3/3 son defectos persistentes, no intermitencia. "
        "Playwright usa retries=0 para no ocultar fallos.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 5:
        print("Uso: stability_report.py results.json salida.md salida.json repeticiones", file=sys.stderr)
        return 2
    source, markdown, destination, repeats = sys.argv[1:]
    repeat_each = int(repeats)
    if repeat_each < 1 or repeat_each > 10:
        raise ValueError("repeticiones fuera de rango 1..10")
    report = json.loads(Path(source).read_text(encoding="utf-8"))
    summary = summarise(report, repeat_each)
    Path(markdown).write_text(to_markdown(summary), encoding="utf-8")
    Path(destination).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Estabilidad UXLab: "
        f"{summary['passed']}/{summary['total_executions']} correctas; "
        f"{summary['intermittent_groups']} grupos intermitentes, "
        f"{summary['incomplete_groups']} incompletos; "
        f"ver {markdown}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
