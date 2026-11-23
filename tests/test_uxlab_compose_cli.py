"""Guardarraíl contra el fallo de arranque observado en UXLab (2026-11-23)."""
from pathlib import Path


def test_seed_invoca_el_cli_de_alembic():
    compose = (Path(__file__).resolve().parents[1]
               / "uxlab" / "compose.uxlab.yml").read_text(encoding="utf-8")
    # El paquete alembic no implementa __main__: "python -m alembic" termina con exit 1.
    assert "alembic upgrade head && python /uxlab/seed.py" in compose
    assert "python -m alembic" not in compose


def test_run_no_reejecuta_seed():
    run = (Path(__file__).resolve().parents[1] / "uxlab" / "run.sh").read_text(encoding="utf-8")
    assert "dc run --build --rm --no-deps tests" in run
