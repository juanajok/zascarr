"""#419: el orden en que `portada()` prueba los archivos de una serie, contra Postgres real.

El doble de sesión de las demás pruebas devuelve las filas en el orden que se le da, así que
invertir `sort_order` o poner los sin número primero no lo notaba. Aquí se siembran archivos
desordenados y se ejecuta la consulta de verdad. Sin `TEST_DATABASE_URL` se salta, como el resto de
pruebas con Postgres.
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import ComicTradition, File, FileFormat, Issue, Series
from zascarr.web.series import _stmt_archivos_de_portada

URL = os.environ.get("TEST_DATABASE_URL")
PG = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")


def test_la_consulta_ordena_por_numero_con_los_sin_numero_al_final_y_desempata_por_id():
    """Sin Postgres: la forma del `ORDER BY` (lo que ejecutan las pruebas con Postgres de abajo)."""
    sql = str(_stmt_archivos_de_portada(uuid4()).compile(dialect=postgresql.dialect()))
    assert "ORDER BY issues.sort_order ASC NULLS LAST, files.id ASC" in sql


@pytest.fixture
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


async def _sembrar_y_leer(url, archivos, *, otra_serie=()):
    """`archivos`: (nombre, sort_order, is_missing, id|None) de UNA serie; devuelve los nombres en
    el orden en que los entrega la consulta. `otra_serie`: de una serie ajena (no deben salir)."""
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    async with fab() as s:
        propia = Series(id=uuid4(), title="Propia", tradition=ComicTradition.AMERICAN)
        ajena = Series(id=uuid4(), title="Ajena", tradition=ComicTradition.AMERICAN)
        s.add_all([propia, ajena])
        await s.flush()

        def anadir(serie, nombre, orden, ausente, id_):
            numero = Issue(id=uuid4(), series_id=serie.id, issue_number=nombre, sort_order=orden)
            s.add(numero)
            ruta = f"/b/{serie.title}/{nombre}.cbz"
            return File(id=id_ or uuid4(), issue_id=numero.id, file_path=ruta,
                        file_name=f"{nombre}.cbz", file_format=FileFormat.CBZ, is_missing=ausente)
        ficheros = [anadir(propia, *a) for a in archivos] + [anadir(ajena, *a) for a in otra_serie]
        await s.flush()
        s.add_all(ficheros)
        await s.commit()
        filas = (await s.execute(_stmt_archivos_de_portada(propia.id))).all()
    await motor.dispose()
    return [f[1].rsplit("/", 1)[1].removesuffix(".cbz") for f in filas]


@PG
@pytest.mark.asyncio
async def test_desordenados_van_de_menor_a_mayor_y_el_que_no_tiene_numero_al_final(url_bd):
    """Mutaciones: `sort_order` descendente y `nulls_first` dejan de dar esta lista."""
    orden = await _sembrar_y_leer(url_bd, [
        ("tres", 3.0, False, None), ("sin-numero", None, False, None),
        ("uno", 1.0, False, None), ("dos-y-medio", 2.5, False, None),
    ])
    assert orden == ["uno", "dos-y-medio", "tres", "sin-numero"]


@PG
@pytest.mark.asyncio
async def test_con_el_mismo_numero_desempata_el_id_siempre_igual(url_bd):
    """O-2: dos archivos con el mismo `sort_order` salen en orden de `id`, no según el plan de la
    consulta. Se insertan al revés para que el desempate no coincida con el orden de inserción."""
    orden = await _sembrar_y_leer(url_bd, [
        ("segundo", 5.0, False, UUID(int=2)), ("primero", 5.0, False, UUID(int=1)),
        ("tercero", 5.0, False, UUID(int=3)),
    ])
    assert orden == ["primero", "segundo", "tercero"]


@PG
@pytest.mark.asyncio
async def test_no_salen_los_ausentes_ni_los_de_otras_series(url_bd):
    orden = await _sembrar_y_leer(
        url_bd,
        [("presente", 1.0, False, None), ("ausente", 2.0, True, None)],
        otra_serie=[("ajeno", 0.5, False, None)],
    )
    assert orden == ["presente"]


@PG
@pytest.mark.asyncio
async def test_solo_se_evaluan_los_primeros_50_archivos(url_bd):
    """O-1: con 55 archivos la consulta entrega los 50 primeros por orden, también los que se
    descartarán por firma. Mutación: quitar el `LIMIT` los entrega todos."""
    archivos = [(f"n{i:02d}", float(i), False, None) for i in range(1, 56)]
    orden = await _sembrar_y_leer(url_bd, archivos)
    assert len(orden) == 50 and orden[0] == "n01" and orden[-1] == "n50"
