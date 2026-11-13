"""Las migraciones forman una sola cadena: sin revisiones repetidas ni dos cabezas.

Regresión de la actualización del 2026-11-13: #686 (0032, IDs externos) y #678
(0032, apartado) colgaban las dos de 0031. Cada PR pasaba su CI por separado y
`alembic upgrade head` falló en la Pi con «Multiple head revisions». Esta prueba
lee los ficheros sin importar alembic ni tocar ninguna base de datos.
"""
from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

VERSIONES = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _revisiones() -> dict[str, tuple[str, str | tuple[str, ...] | None]]:
    """Devuelve {fichero: (revision, down_revision)} leyendo las asignaciones de cada módulo."""
    resultado = {}
    for fichero in sorted(VERSIONES.glob("[0-9]*.py")):
        valores = {}
        for nodo in ast.parse(fichero.read_text(encoding="utf-8")).body:
            if isinstance(nodo, ast.Assign) and len(nodo.targets) == 1:
                objetivo = nodo.targets[0]
            elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
                objetivo = nodo.target
            else:
                continue
            if isinstance(objetivo, ast.Name) and objetivo.id in ("revision", "down_revision"):
                valores[objetivo.id] = ast.literal_eval(nodo.value)
        assert "revision" in valores, f"{fichero.name} no declara revision"
        resultado[fichero.name] = (valores["revision"], valores.get("down_revision"))
    return resultado


def test_ninguna_revision_repetida():
    cuenta = Counter(rev for rev, _ in _revisiones().values())
    repetidas = {rev: n for rev, n in cuenta.items() if n > 1}
    assert not repetidas, f"revisiones repetidas: {repetidas}"


def test_una_sola_cabeza_y_una_sola_raiz():
    revisiones = _revisiones()
    padres: set[str] = set()
    raices = []
    for rev, abajo in revisiones.values():
        if abajo is None:
            raices.append(rev)
        elif isinstance(abajo, (tuple, list)):
            padres.update(abajo)
        else:
            padres.add(abajo)
    todas = {rev for rev, _ in revisiones.values()}
    cabezas = sorted(todas - padres)
    assert cabezas and len(cabezas) == 1, f"cabezas: {cabezas}"
    assert len(raices) == 1, f"raíces: {raices}"
    assert padres <= todas, f"down_revision sin fichero: {sorted(padres - todas)}"
