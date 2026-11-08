"""Paridad Python/SQL de f_tag_norm (migración 0022, BL-ETQ1a)."""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from zascarr.services.etiquetas import normalize_tag

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real)",
)

MIGRATION = (Path(__file__).parent.parent / "alembic" / "versions"
             / "20261107_0022_etiquetas_serie.py")


def _sql_funcion() -> str:
    arbol = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if (isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute)
                and nodo.func.attr == "execute" and nodo.args
                and isinstance(nodo.args[0], ast.Constant)
                and "CREATE OR REPLACE FUNCTION f_tag_norm" in nodo.args[0].value):
            return nodo.args[0].value
    raise AssertionError("no se encontró f_tag_norm en la migración")


CASOS = [
    "Noir", "Nóir", "NOIR", "The Walking Dead", "S.H.I.E.L.D.", "Ñandú",
    "  espacios   múltiples ", "space-opera", "café", "München", "L'Étoile",
    "¡Hola!", "A.B.C.", "Los 4 Fantásticos", "El Capitán Trueno", "Batman",
    "X-Men", "Doña Urraca", "Astérix", "Tintín", "Mafalda", "Mortadelo y Filemón",
    "The Sandman", "Sandman, The", "Dragon Ball", "Bola de Drac", "One Piece",
    "Naruto", "Bleach", "Death Note", "Akira", "Ghost in the Shell",
    "Fullmetal Alchemist", "My Hero Academia", "Tokyo Ghoul", "Evangelion",
    "Sailor Moon", "Cardcaptor Sakura", "Ranma ½", "Inuyasha", "Maison Ikkoku",
    "Lupin III", "Cowboy Bebop", "Hellsing", "Berserk", "Vagabond", "Monster",
    "20th Century Boys", "Pluto", "Nausicaä", "Paprika", "Perfect Blue",
    "Ghost World", "Maus", "Persepolis", "Fun Home", "Watchmen", "V de Vendetta",
    "From Hell", "The League of Extraordinary Gentlemen", "Saga",
    "Y: The Last Man", "Fables", "Hellboy", "Usagi Yojimbo", "Cerebus",
    # Letras europeas que `unaccent` translitera y NFKD no descompone: la
    # columna generada las convierte a ASCII y Python tiene que hacer lo mismo.
    "ø", "Ø", "æ", "Æ", "œ", "Œ", "ß", "ẞ", "ł", "Ł", "đ", "Đ", "ð", "Ð",
    "þ", "Þ", "ı", "ħ", "Ħ", "ŋ", "Ŋ", "ŧ", "Ŧ", "ĸ",
    "Smørrebrød", "Æon Flux", "Straße", "Łódź", "Đà Nẵng", "Þór",
    "Mjølnir", "Ħal Qormi",
]


@pytest.mark.asyncio
async def test_f_tag_norm_es_espejo_de_python():
    import asyncpg

    conn = await asyncpg.connect(TEST_DATABASE_URL)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        await conn.execute(
            "CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text "
            "LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT "
            "AS $$ SELECT public.unaccent('public.unaccent', $1) $$"
        )
        await conn.execute(_sql_funcion())
        for texto in CASOS:
            assert await conn.fetchval("SELECT f_tag_norm($1)", texto) == normalize_tag(texto)
    finally:
        await conn.close()
