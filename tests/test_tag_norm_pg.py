# ruff: noqa: E501
"""
tests/test_tag_norm_pg.py

Paridad Python/SQL para la normalización de etiquetas (migración 0022, BL-ETQ1a #403).

`f_tag_norm()` en Postgres debe ser un espejo exacto de
`services/etiquetas.py::normalize_tag()`: si alguien toca uno sin tocar el
otro, una etiqueta acentuada deja de encontrarse («Nóir» crea una fila
nueva en vez de reutilizar «noir») aunque el resto de la suite siga en
verde (ninguna otra prueba usa Postgres real).

Requiere una Postgres real y corriendo — no forma parte del resto de la
suite (que es deliberadamente sin DB). Se salta automáticamente si
TEST_DATABASE_URL no está definida:

    docker run --rm -d --name zascarr_test_pg -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=zascarr -p 15433:5432 postgres:15-alpine
    TEST_DATABASE_URL=postgresql://postgres:test@localhost:15433/zascarr \\
        pytest tests/test_tag_norm_pg.py

La función SQL se extrae del propio fichero de migración (no se duplica a
mano) para que esta prueba falle si el SQL cambia y diverge, en vez de
comparar contra una copia que nadie mantiene. Misma técnica que
`test_title_norm.py`.
"""
import ast
import os
from pathlib import Path

import pytest

from zascarr.services.etiquetas import clave_de, normalize_tag

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

RAIZ = Path(__file__).resolve().parents[1]
MIGRATION_PATH = RAIZ / "alembic" / "versions" / "20261107_0022_etiquetas.py"

#: Corpus de nombres reales de etiquetas. Incluye acentos y eñes (español), diéresis y ligaduras
#: (alemán/francés/nórdico), artículos que NO se quitan, puntos entre letras que NO se colapsan y
#: puntuación variada. Son los casos que la ficha y las sugerencias pueden recibir.
NOMBRES = [
    # Español
    "Noir", "Cómic", "Cómic europeo", "Historieta", "Tebeo", "Novela gráfica",
    "Ciencia ficción", "Terror gótico", "Aventuras", "Humor", "Superhéroes",
    "España", "Doña Urraca", "Astérix", "Mortadelo y Filemón: ¡Misión Triunfo!",
    "El Capitán Trueno", "Zipi y Zape", "Superlópez", "Pafman", "Súper López",
    "¿Qué?", "¡Ataque!", "«Hola»", "Manga", "Seinen", "Shonen", "Shojo", "Josei",
    # Inglés / temas
    "Space Opera", "The Walking Dead", "Walking Dead, The", "Cyberpunk",
    "Post-apocalyptic", "Post-apocalíptico", "Hardboiled", "Pulp", "Weird West",
    "Sword and Sorcery", "Coming of age", "Time travel", "Alternate history",
    "Steampunk", "Dieselpunk", "Solarpunk", "Cosmic horror", "Body horror",
    "Psychological", "Slice of life", "Slow burn", "Found family",
    "Enemies to lovers", "Road trip", "Heist", "Spy fiction", "Martial arts",
    "Wuxia", "Isekai", "Mecha", "Kaiju", "Magical girl",
    # Francés / alemán / nórdico
    "Bande dessinée", "Franco-belga", "Müller", "Zürich", "Crème brûlée",
    "Nausicaä", "Tintín", "Hergé", "Moebius", "Métal Hurlant", "Spirou",
    "Gaston Lagaffe", "Lucky Luke", "Smørrebrød", "Æon Flux", "Łódź",
    "Đà Nẵng", "Þór", "Mjølnir", "Straße", "ẞ", "ı", "ħ", "ŋ", "ŧ", "ĸ",
    # Puntuación, mayúsculas y espacios
    "S.H.I.E.L.D.", "S.H.I.E.L.D. vs. H.Y.D.R.A.", "A.K.A. Jessica Jones",
    "X-Men", "Spider-Man", "Batman: The Long Halloween", "Sci-Fi", "Space-Opera",
    "noir/neonoir", "C++", "C#", "100%", "O'Neill", "McDonald's", "Rock'n'Roll",
    "L'Écho", "D'Artagnan", "  varios   espacios  ", "MAYÚSCULAS", "MezClaDeCaSo",
    "trazo_bajo", "punto.entre.letras", "dos--guiones", "guion—largo", "emoji 😀",
    "日本語", "Кино", "Ταινία",
]


def _extract_function_sql(source: str, function_name: str) -> str:
    """Saca el string literal del op.execute(...) que define la función SQL dada, parseando el AST
    de la migración en vez de hacer regex sobre el texto crudo: el fuente contiene dos backslashes
    literales que Python solo colapsa a uno al parsear el literal de cadena — una extracción textual
    manda ese doble backslash tal cual a Postgres y rompe las clases de caracteres del regex."""
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
def tag_norm_sql() -> str:
    return _extract_function_sql(MIGRATION_PATH.read_text(), "f_tag_norm")


@pytest.fixture
async def pg_conn(tag_norm_sql):
    import asyncpg

    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        # `f_unaccent` existe desde 0006; el conftest migra la BD a head una vez por sesión.
        await conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        await conn.execute(tag_norm_sql)
        yield conn
    finally:
        await conn.close()


@pytest.mark.parametrize("nombre", NOMBRES)
async def test_tag_norm_matches_python(pg_conn, nombre):
    esperado = normalize_tag(nombre)
    real = await pg_conn.fetchval("SELECT f_tag_norm($1)", nombre)
    assert real == esperado


async def test_la_funcion_sql_es_idempotente_sobre_lo_ya_normalizado(pg_conn):
    """`quitar` re-normaliza la clave (`space-opera` → `space opera`): el resultado tiene que ser
    un punto fijo, o la etiqueta no se encontraría al segundo intento."""
    for nombre in NOMBRES:
        normalizado = normalize_tag(nombre)
        assert await pg_conn.fetchval("SELECT f_tag_norm($1)", normalizado) == normalizado


async def test_conserva_el_articulo(pg_conn):
    """A diferencia de `f_title_norm`, no se quita el artículo inicial ni pospuesto."""
    assert await pg_conn.fetchval("SELECT f_tag_norm($1)", "The Walking Dead") == "the walking dead"
    assert await pg_conn.fetchval("SELECT f_tag_norm($1)", "Walking Dead, The") == "walking dead the"


async def test_no_colapsa_puntos_entre_letras(pg_conn):
    assert await pg_conn.fetchval("SELECT f_tag_norm($1)", "S.H.I.E.L.D.") == "s h i e l d"


async def test_la_clave_es_un_punto_fijo(pg_conn):
    """El formulario de quitar manda `clave_de(name_norm)`; `f_tag_norm` de esa clave debe volver
    al `name_norm` original (guiones → espacios)."""
    for nombre in NOMBRES:
        normalizado = normalize_tag(nombre)
        clave = clave_de(normalizado)
        assert await pg_conn.fetchval("SELECT f_tag_norm($1)", clave) == normalizado
