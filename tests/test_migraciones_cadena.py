"""La cadena de migraciones es única y lineal (regresión de revisiones duplicadas).

Ya pasó dos veces (dos `0032`, dos `0034` y, al desplegar SCR1, dos `0037`): dos ramas usan el
mismo número, `alembic upgrade head` falla con «Multiple head revisions» y la actualización deja
la BD sin migrar. Esta prueba lee los ficheros (sin BD) y exige revisiones únicas, una sola
cabeza y que la cadena desde la cabeza cubra TODAS las revisiones.
"""
from __future__ import annotations

import re
from pathlib import Path

VERSIONES = Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _migraciones() -> dict[str, tuple[str, str | None]]:
    """{nombre de fichero: (revision, down_revision)}, leyendo los ficheros de `versions/`."""
    salida: dict[str, tuple[str, str | None]] = {}
    for fichero in sorted(VERSIONES.glob("*.py")):
        if fichero.name == "__init__.py":
            continue
        texto = fichero.read_text(encoding="utf-8")
        rev = re.search(r'^revision = "([^"]+)"', texto, re.M)
        down = re.search(r'^down_revision = (?:None|"([^"]+)")', texto, re.M)
        assert rev, f"{fichero.name}: no declara `revision`"
        salida[fichero.name] = (rev.group(1), down.group(1) if down else None)
    return salida


def test_revisiones_unicas_una_cabeza_y_cadena_lineal():
    migraciones = _migraciones()
    revisiones = [rev for rev, _ in migraciones.values()]
    duplicadas = sorted({r for r in revisiones if revisiones.count(r) > 1})
    assert not duplicadas, (
        f"revisiones duplicadas: {duplicadas} — renumera una de ellas (dos ramas no pueden "
        "usar el mismo número: rompe `alembic upgrade head`)")

    hijas = {down for _, down in migraciones.values() if down is not None}
    for nombre, (_, down) in migraciones.items():
        if down is not None:
            assert down in revisiones, (
                f"{nombre}: down_revision {down!r} no existe")

    cabezas = [nombre for nombre, (rev, _) in migraciones.items() if rev not in hijas]
    assert len(cabezas) == 1, (
        f"hay {len(cabezas)} cabezas de migración: {cabezas} — deja una sola (sin ramas)")

    # La cadena desde la cabeza debe pasar por TODAS las revisiones (sin ramas huérfanas).
    por_rev = {rev: down for _, (rev, down) in migraciones.items()}
    vistas: list[str] = []
    actual: str | None = por_rev[migraciones[cabezas[0]][0]]
    while actual is not None:
        assert actual not in vistas, f"bucle en la cadena: {actual}"
        vistas.append(actual)
        actual = por_rev.get(actual)
    assert len(vistas) + 1 == len(migraciones), (
        f"la cadena desde la cabeza cubre {len(vistas) + 1} de {len(migraciones)} revisiones: "
        "hay ramas huérfanas")
