# ruff: noqa: E501
"""`censo_calidad.py` contra Postgres real, con un caso sintético por comprobación.

La fixture `tests/fixtures/calidad_sintetica.sql` crea una base de pruebas con
una fila (o pareja) que dispara cada comprobación del catálogo. La prueba
ejecuta el script como lo haría una persona (subprocess + `--json`) sobre una
base efímera migrada a `head`, para no tocar `zascarr_test`.

Se salta sin `TEST_DATABASE_URL` (Postgres real).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import asyncpg
import pytest

from tests._pg import bd_efimera, migrar_a_head

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "medicion" / "censo_calidad.py"
FIXTURE = RAIZ / "tests" / "fixtures" / "calidad_sintetica.sql"

#: Comprobaciones que no pueden tener caso por una restricción de la base.
SIN_CASO_POSIBLE = {"G2c"}  # UNIQUE (name_norm) en creators
NO_EJECUTABLES = {"I3", "D1b"}


def _censo(env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        env=env, capture_output=True, text=True, timeout=120,
    )


def _url_asyncpg(url: str) -> str:
    """asyncpg no entiende el sufijo de driver de SQLAlchemy (el helper de tests._pg lo añade)."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _cargar_fixture(url: str) -> None:
    conn = await asyncpg.connect(_url_asyncpg(url))
    try:
        await conn.execute(FIXTURE.read_text(encoding="utf-8"))
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_catalogo_completo_contra_datos_sinteticos(tmp_path: Path) -> None:
    async with bd_efimera(URL) as destino:
        migrar_a_head(destino)
        await _cargar_fixture(destino)
        env = {**os.environ, "DATABASE_URL": destino}

        proceso = _censo(env, "--json")
        assert proceso.returncode == 0, proceso.stderr[-3000:]
        datos = json.loads(proceso.stdout)
        por_id = {c["id"]: c for c in datos["checks"]}

        # El catálogo no se ha recortado: cada comprobación tiene su fila.
        assert len(por_id) >= 82, sorted(por_id)

        # Un caso por comprobación (salvo las que la base impide o exigen disco/parser).
        for cid, check in por_id.items():
            if cid in NO_EJECUTABLES:
                assert check["estado"] == "NOT RUN", cid
                assert check["motivo"], cid
                continue
            assert check["estado"] == "OK", cid
            if cid in SIN_CASO_POSIBLE:
                assert check["casos"] == 0, (cid, check["casos"])
            else:
                assert check["casos"] >= 1, (cid, check["casos"])
            assert check["poblacion"] is not None, cid

        # La salida compartible NO lleva títulos ni rutas reales del fixture.
        compartible = json.dumps(datos, ensure_ascii=False)
        assert "Mortadelo" not in compartible
        assert "Titulo Real" not in compartible
        assert "/biblioteca" not in compartible

        # La huella es estable entre ejecuciones (sin contar la fecha).
        segunda = _censo(env, "--json")
        assert segunda.returncode == 0, segunda.stderr[-3000:]
        assert json.loads(segunda.stdout)["huella"] == datos["huella"]

        # --solo filtra por prefijo: A1 devuelve solo A1, no A2.
        solo = _censo(env, "--json", "--solo", "A1")
        assert solo.returncode == 0, solo.stderr[-3000:]
        ids = [c["id"] for c in json.loads(solo.stdout)["checks"]]
        assert ids == ["A1a", "A1b"]

        # La muestra para etiquetar se escribe con valores reales y una etiqueta
        # esperada PREVIA (el PO solo rellena `etiqueta_po`).
        csv = tmp_path / "muestra.csv"
        muestreo = _censo(env, "--local", "--csv", str(csv), "--muestreo", "3", "--solo", "B1a,B4a")
        assert muestreo.returncode == 0, muestreo.stderr[-3000:]
        texto = csv.read_text(encoding="utf-8")
        cabecera = texto.splitlines()[0]
        assert cabecera == "comprobacion,caso_id,etiqueta_esperada,etiqueta_po,detalle_json"
        assert "B1a" in texto and "B4a" in texto
        assert "Batman" in texto  # --local sí enseña el título real


@pytest.mark.asyncio
async def test_solo_lectura_la_base_no_cambia() -> None:
    """El censo no escribe: contar filas antes y después debe dar lo mismo."""
    async with bd_efimera(URL) as destino:
        migrar_a_head(destino)
        await _cargar_fixture(destino)
        conn = await asyncpg.connect(_url_asyncpg(destino))
        try:
            antes = await conn.fetchval(
                "SELECT (SELECT count(*) FROM series) + (SELECT count(*) FROM issues) "
                "+ (SELECT count(*) FROM files)")
        finally:
            await conn.close()
        proceso = _censo({**os.environ, "DATABASE_URL": destino}, "--json")
        assert proceso.returncode == 0, proceso.stderr[-3000:]
        conn = await asyncpg.connect(_url_asyncpg(destino))
        try:
            despues = await conn.fetchval(
                "SELECT (SELECT count(*) FROM series) + (SELECT count(*) FROM issues) "
                "+ (SELECT count(*) FROM files)")
        finally:
            await conn.close()
        assert despues == antes
