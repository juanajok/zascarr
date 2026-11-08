# ruff: noqa: E501
"""
tests/test_etiquetas_migracion_pg.py

Migración 0022 (BL-ETQ1a, #403): esquema de etiquetas, backfill de una fila legacy,
restricciones de `tags`/`series_tags` y downgrade (incluida la deduplicación por `name`).

Cada prueba trabaja en una BD efímera. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
from uuid import uuid4

import asyncpg
import pytest

from tests._pg import alembic, bd_efimera

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def consultar(url: str, sql: str, *args):
    conexion = await asyncpg.connect(url)
    try:
        return await conexion.fetch(sql, *args)
    finally:
        await conexion.close()


async def ejecutar(url: str, sql: str, *args) -> None:
    conexion = await asyncpg.connect(url)
    try:
        await conexion.execute(sql, *args)
    finally:
        await conexion.close()


async def columnas(url: str, tabla: str) -> list[str]:
    filas = await consultar(
        url,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = $1 ORDER BY ordinal_position",
        tabla,
    )
    return [f["column_name"] for f in filas]


async def tablas(url: str) -> set[str]:
    filas = await consultar(
        url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    )
    return {f["table_name"] for f in filas}


async def restricciones(url: str, tabla: str) -> set[str]:
    filas = await consultar(
        url, "SELECT conname FROM pg_constraint WHERE conrelid = $1::regclass", tabla
    )
    return {f["conname"] for f in filas}


async def indices(url: str, tabla: str) -> set[str]:
    filas = await consultar(url, "SELECT indexname FROM pg_indexes WHERE tablename = $1", tabla)
    return {f["indexname"] for f in filas}


async def crear_serie(url: str, titulo: str = "Thorgal") -> str:
    serie_id = str(uuid4())
    await ejecutar(url, "INSERT INTO series (id, title) VALUES ($1, $2)", serie_id, titulo)
    return serie_id


async def crear_issue(url: str, serie_id: str, numero: str) -> str:
    issue_id = str(uuid4())
    await ejecutar(
        url,
        "INSERT INTO issues (id, series_id, issue_number) VALUES ($1, $2, $3)",
        issue_id,
        serie_id,
        numero,
    )
    return issue_id


class TestUpgrade:

    async def test_0021_a_head_conserva_la_fila_legacy_y_calcula_namespace_y_name_norm(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "0021")
            tag_id = str(uuid4())
            await ejecutar(url, "INSERT INTO tags (id, name) VALUES ($1, 'Nóir')", tag_id)

            alembic(url, "upgrade", "head")

            fila = (
                await consultar(
                    url, "SELECT namespace, name, name_norm FROM tags WHERE id = $1", tag_id
                )
            )[0]
            assert fila["namespace"] == "etiqueta"
            assert fila["name"] == "Nóir"          # el nombre visible no se reescribe
            assert fila["name_norm"] == "noir"     # la columna generada sí lo normaliza
            assert {"namespace", "name_norm"} <= set(await columnas(url, "tags"))
            assert "series_tags" in await tablas(url)
            assert "issue_tags" in await tablas(url)  # sigue dormida, no se toca

    async def test_f_tag_norm_existe_y_es_inmutable(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            fila = (
                await consultar(
                    url, "SELECT provolatile FROM pg_proc WHERE proname = 'f_tag_norm'"
                )
            )[0]
            # IMMUTABLE es obligatorio: la columna generada y el índice GIN no admiten otra cosa.
            assert fila["provolatile"] == b"i"
            assert (
                await consultar(url, "SELECT f_tag_norm('The Walking Dead') AS v")
            )[0]["v"] == "the walking dead"

    async def test_unicidad_por_namespace_y_name_norm(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            await ejecutar(url, "INSERT INTO tags (name) VALUES ('Noir')")
            with pytest.raises(asyncpg.exceptions.UniqueViolationError):
                await ejecutar(url, "INSERT INTO tags (name) VALUES ('Nóir')")

    @pytest.mark.parametrize("sql", [
        "INSERT INTO tags (name) VALUES ('   ')",
        "INSERT INTO tags (name) VALUES (repeat('a', 65))",
        "INSERT INTO tags (namespace, name) VALUES ('genero', 'Noir')",
    ], ids=["name_norm_vacio", "nombre_demasiado_largo", "namespace_no_admitido"])
    async def test_checks_de_tags(self, sql):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                await ejecutar(url, sql)

    async def test_indices_de_tags_y_series_tags(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            assert "ix_tags_name_norm_trgm" in await indices(url, "tags")
            assert "uq_tags_namespace_name_norm" in await restricciones(url, "tags")
            definicion = (
                await consultar(
                    url,
                    "SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_tags_name_norm_trgm'",
                )
            )[0]["indexdef"]
            assert "gin" in definicion and "gin_trgm_ops" in definicion
            assert "ix_series_tags_tag_visible" in await indices(url, "series_tags")

    async def test_series_tags_admite_una_asignacion_valida_y_rechaza_source_y_weight(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            serie_id = await crear_serie(url)
            tag_id = str(uuid4())
            await ejecutar(url, "INSERT INTO tags (id, name) VALUES ($1, 'Noir')", tag_id)

            await ejecutar(
                url,
                "INSERT INTO series_tags (series_id, tag_id, source, weight, oculta) "
                "VALUES ($1, $2, 'manual', 50, false)",
                serie_id,
                tag_id,
            )
            fila = (
                await consultar(
                    url, "SELECT source, weight, oculta FROM series_tags WHERE series_id = $1",
                    serie_id,
                )
            )[0]
            assert (fila["source"], fila["weight"], fila["oculta"]) == ("manual", 50, False)

            otro_tag = str(uuid4())
            await ejecutar(url, "INSERT INTO tags (id, name) VALUES ($1, 'Otro')", otro_tag)
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                await ejecutar(
                    url,
                    "INSERT INTO series_tags (series_id, tag_id, source) VALUES ($1, $2, 'foo')",
                    serie_id,
                    otro_tag,
                )
            with pytest.raises(asyncpg.exceptions.CheckViolationError):
                await ejecutar(
                    url,
                    "INSERT INTO series_tags (series_id, tag_id, weight) VALUES ($1, $2, 101)",
                    serie_id,
                    otro_tag,
                )

    async def test_borrar_la_serie_o_la_etiqueta_borra_la_asignacion(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            serie_id = await crear_serie(url)
            tag_id = str(uuid4())
            await ejecutar(url, "INSERT INTO tags (id, name) VALUES ($1, 'Noir')", tag_id)
            await ejecutar(
                url, "INSERT INTO series_tags (series_id, tag_id) VALUES ($1, $2)", serie_id, tag_id
            )
            await ejecutar(url, "DELETE FROM series WHERE id = $1", serie_id)
            assert await consultar(url, "SELECT 1 FROM series_tags") == []

            serie_id = await crear_serie(url)
            await ejecutar(
                url, "INSERT INTO series_tags (series_id, tag_id) VALUES ($1, $2)", serie_id, tag_id
            )
            await ejecutar(url, "DELETE FROM tags WHERE id = $1", tag_id)
            assert await consultar(url, "SELECT 1 FROM series_tags") == []


class TestDowngrade:

    async def test_vuelve_a_0021_y_conserva_issue_tags(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            serie_id = await crear_serie(url)
            issue_id = await crear_issue(url, serie_id, "1")
            tag_id = str(uuid4())
            await ejecutar(url, "INSERT INTO tags (id, name) VALUES ($1, 'Noir')", tag_id)
            await ejecutar(
                url, "INSERT INTO issue_tags (issue_id, tag_id) VALUES ($1, $2)", issue_id, tag_id
            )

            alembic(url, "downgrade", "0021")

            assert "series_tags" not in await tablas(url)
            cols = set(await columnas(url, "tags"))
            assert "name_norm" not in cols and "namespace" not in cols
            assert "tags_name_key" in await restricciones(url, "tags")
            assert await consultar(url, "SELECT 1 FROM pg_proc WHERE proname = 'f_tag_norm'") == []
            assert len(await consultar(url, "SELECT 1 FROM issue_tags")) == 1
            assert set(await columnas(url, "issue_tags")) == {"issue_id", "tag_id"}

    async def test_downgrade_deduplica_por_name_y_conserva_la_mas_referenciada(self):
        """Una BD futura con más de un namespace podría tener dos filas con el mismo `name`;
        al volver al UNIQUE global hay que quedarse con una y reasignar sus `issue_tags`."""
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            # Simula una BD futura con otro namespace: el UNIQUE nuevo no permite dos filas con
            # el mismo `name`, así que se sustituye por un centinela con el mismo nombre que el
            # downgrade espera borrar (el UNIQUE real de `id` no estorba a los duplicados).
            await ejecutar(url, "ALTER TABLE tags DROP CONSTRAINT uq_tags_namespace_name_norm")
            await ejecutar(
                url,
                "ALTER TABLE tags ADD CONSTRAINT uq_tags_namespace_name_norm UNIQUE (id)",
            )
            conservada, duplicada = uuid4(), uuid4()
            await ejecutar(
                url,
                "INSERT INTO tags (id, name) VALUES ($1, 'Noir'), ($2, 'Noir')",
                conservada,
                duplicada,
            )
            serie_id = await crear_serie(url)
            # La conservada tiene dos referencias; la duplicada, una.
            for numero, tag in (("1", conservada), ("2", conservada), ("3", duplicada)):
                issue_id = await crear_issue(url, serie_id, numero)
                await ejecutar(
                    url,
                    "INSERT INTO issue_tags (issue_id, tag_id) VALUES ($1, $2)",
                    issue_id,
                    tag,
                )

            alembic(url, "downgrade", "0021")

            assert [f["id"] for f in await consultar(url, "SELECT id FROM tags")] == [conservada]
            referencias = await consultar(
                url, "SELECT tag_id, count(*) AS n FROM issue_tags GROUP BY tag_id"
            )
            assert len(referencias) == 1
            assert referencias[0]["tag_id"] == conservada and referencias[0]["n"] == 3
