"""Paridad Python/SQL para el matching de títulos (migración 0006, H1).

f_title_norm() en Postgres debe ser un espejo exacto de
core.matcher.normalize_title(): si alguien toca uno sin tocar el otro,
"Nausicaa" vuelve a no encontrar "Nausicaä" en producción aunque los 128
tests del resto de la suite sigan en verde (ninguno usa Postgres real).

Requiere una Postgres real y corriendo — no forma parte del resto de la
suite (que es deliberadamente sin DB). Se salta automáticamente si
TEST_DATABASE_URL no está definida:

    docker run --rm -d --name secuenciarr_test_pg -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=tebeoteca -p 15433:5432 postgres:15-alpine
    TEST_DATABASE_URL=postgresql://postgres:test@localhost:15433/tebeoteca \\
        pytest tests/test_title_norm.py

Las funciones SQL se extraen del propio fichero de migración (no se
duplican a mano) para que esta prueba falle si el SQL cambia y diverge,
en vez de comparar contra una copia que nadie mantiene.
"""
import ast
import os
from pathlib import Path

import pytest

from secuenciarr.core.matcher import normalize_title

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "alembic" / "versions" / "20260921_0006_matcher_metadata_fixes.py"
)

TITLES = [
    "The Sandman",
    "Sandman, The",
    "S.H.I.E.L.D.",
    "S.H.I.E.L.D. vs. H.Y.D.R.A.",
    "Nausicaä",
    "Nausicaä del Valle del Viento",
    "Mortadelo y Filemón: ¡Misión Triunfo!",
    "Thorgal",
    "X-Men",
    "Spider-Man",
    "El Capitán Trueno",
    "Astérix",
    "Die Fantastischen Vier",
    "Los 4 Fantásticos",
    "A.K.A. Jessica Jones",
    "Batman: The Long Halloween",
    "The",
    "El",
]


def _extract_function_sql(source: str, function_name: str) -> str:
    """Saca el string literal del op.execute(...) que define la función SQL
    dada, parseando el AST de la migración en vez de hacer regex sobre el
    texto crudo: el fuente contiene dos backslashes literales que Python
    solo colapsa a uno al parsear el literal de cadena — una extracción
    textual manda ese doble backslash tal cual a Postgres y rompe todas las
    clases de caracteres del regex (\\s deja de ser "espacio")."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "execute"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and f"CREATE OR REPLACE FUNCTION {function_name}" in node.args[0].value
        ):
            return node.args[0].value
    raise AssertionError(f"no se encontró la definición de {function_name} en {MIGRATION_PATH}")


@pytest.fixture(scope="module")
def title_norm_sql() -> tuple[str, str]:
    source = MIGRATION_PATH.read_text()
    return (
        _extract_function_sql(source, "f_unaccent"),
        _extract_function_sql(source, "f_title_norm"),
    )


@pytest.fixture
async def pg_conn(title_norm_sql):
    import asyncpg

    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        f_unaccent_sql, f_title_norm_sql = title_norm_sql
        await conn.execute(f_unaccent_sql)
        await conn.execute(f_title_norm_sql)
        yield conn
    finally:
        await conn.close()


@pytest.mark.parametrize("title", TITLES)
async def test_title_norm_matches_python(pg_conn, title):
    expected = normalize_title(title)
    actual = await pg_conn.fetchval("SELECT f_title_norm($1)", title)
    assert actual == expected
