"""Agrega las seis sesiones de agentes en JSON y Markdown, incluso si fallan."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def collect(root: Path) -> dict:
    sessions = []
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        report = directory / "session.json"
        if not report.is_file():
            continue
        data = json.loads(report.read_text(encoding="utf-8"))
        sessions.append({
            "scenario": data["scenario_id"],
            "persona": data["persona_id"],
            "objective_success": data["objective_success"],
            "declared_success": data["declared_success"],
            "false_success": data["false_success"],
            "steps": data["steps"],
            "duration_ms": data["elapsed_ms"],
            "stop_reason": data["stop_reason"],
            "model_calls": data["model"]["calls"],
            "input_tokens": data["model"]["inputTokens"],
            "output_tokens": data["model"]["outputTokens"],
            "estimated_usd": data["model"]["estimatedUSD"],
            "evidence": directory.name + "/session.json",
        })
    return {
        "sessions_expected": 6,
        "sessions_found": len(sessions),
        "objective_successes": sum(x["objective_success"] for x in sessions),
        "false_successes": sum(x["false_success"] for x in sessions),
        "total_model_calls": sum(x["model_calls"] for x in sessions),
        "input_tokens": sum(x["input_tokens"] for x in sessions),
        "output_tokens": sum(x["output_tokens"] for x in sessions),
        "estimated_usd": round(sum(x["estimated_usd"] for x in sessions), 7),
        "sessions": sessions,
    }


def render(d: dict) -> str:
    lines = [
        "# UXLab — piloto DeepSeek + Playwright",
        "",
        f"Sesiones: **{d['sessions_found']}/{d['sessions_expected']}** · "
        f"Objetivos cumplidos: **{d['objective_successes']}** · "
        f"Falsos éxitos: **{d['false_successes']}**",
        "",
        f"Llamadas DeepSeek: {d['total_model_calls']} · "
        f"Entrada: {d['input_tokens']} tokens · "
        f"Salida: {d['output_tokens']} tokens · "
        f"Coste **estimado**: **USD {d['estimated_usd']:.5f}**.",
        "",
        "| Escenario | Perfil | Objetivo | Declarado | Falso éxito | Pasos | Motivo final | Evidencia |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for row in d["sessions"]:
        lines.append(
            f"| {row['scenario']} | {row['persona']} | "
            f"{'sí' if row['objective_success'] else 'no'} | "
            f"{'sí' if row['declared_success'] else 'no'} | "
            f"{'sí' if row['false_success'] else 'no'} | {row['steps']} | "
            f"{row['stop_reason'].replace('|','/')} | "
            f"[JSON]({row['evidence']}) |"
        )
    lines.extend([
        "",
        "**Precauciones:** el coste es estimado con las tarifas pico configuradas; "
        "no garantiza la factura final de DeepSeek. Se han enviado capturas y "
        "árboles accesibles del catálogo **sintético** a un proveedor remoto. "
        "Los agentes no representan usuarios reales; SSR y calibración humana "
        "siguen fuera de alcance.",
        "",
    ])
    return "\n".join(lines)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: report.py <directorio-resultados>")
    root = Path(sys.argv[1])
    report = collect(root)
    (root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / "report.md").write_text(render(report), encoding="utf-8")
    print("Agentes:", report["sessions_found"], "sesiones;",
          report["objective_successes"], "objetivos; USD",
          report["estimated_usd"], "(estimación)")


if __name__ == "__main__":
    main()
