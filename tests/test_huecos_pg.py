"""Contrato de «número que me falta» (2026-09-27) contra Postgres real.

`compute_missing_issues` restaba a `Series.total_issues` el conjunto de
`Issue.sort_order`, un campo que **ningún código de `main` escribe** (la única
derivación que existió se quedó en una rama abandonada). Con el conjunto
siempre vacío, la vista no decía "no lo sé": decía que **falta todo**. Medido
con `scripts/medicion/censo_huecos.py`: 0/18 issues con `sort_order` y 52
huecos inventados en 5 series.

Estos tests fijan el contrato nuevo: la posesión sale del **disco** (un `File`
con `is_missing=false`, el mismo criterio que los demás consumidores de "¿lo
tengo?" de B7) y del **formato** (solo una grapa cubre una grapa), no de un
campo sin poblar.

Se saltan sin TEST_DATABASE_URL, mismo patrón que `test_title_norm.py`:

    docker run --rm -d --name zascarr_test_pg -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=zascarr -p 15433:5432 postgres:15-alpine
    TEST_DATABASE_URL=postgresql://postgres:test@localhost:15433/zascarr \\
        pytest tests/test_huecos_pg.py
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.api.series import huecos_de_serie, numeros_poseidos
from zascarr.models import ComicTradition, File, FileFormat, Issue, IssueFormat, Series

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)


def _url_asyncpg(url: str) -> str:
    """Acepta `postgresql://` y `postgresql+asyncpg://` (el resto de la suite
    documenta la URL en formato plano, sin driver)."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
async def db():
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        # Una sentencia por execute: asyncpg no admite varias en un prepared
        # statement. Orden por las FK (files → issues → series).
        for tabla in ("files", "issues", "series"):
            await session.execute(text(f"DELETE FROM {tabla}"))
        await session.commit()
        yield session
    await engine.dispose()


async def crear_serie(db, total_issues=None, title="Serie de prueba") -> Series:
    s = Series(id=uuid4(), title=title, tradition=ComicTradition.AMERICAN,
               total_issues=total_issues)
    db.add(s)
    await db.flush()
    return s


async def crear_issue(db, series, numero, formato=IssueFormat.SINGLE_ISSUE,
                      archivos=(False,)) -> Issue:
    """Crea un Issue con un `File` por cada elemento de `archivos` (`True` =
    desaparecido del disco). Sin elementos: issue catalogado sin archivo."""
    i = Issue(id=uuid4(), series_id=series.id, issue_number=numero, format=formato)
    db.add(i)
    await db.flush()
    for is_missing in archivos:
        db.add(File(id=uuid4(), issue_id=i.id, file_path=f"/lib/{uuid4()}.cbz",
                    file_name="x.cbz", file_format=FileFormat.CBZ, is_missing=is_missing))
    await db.flush()
    return i


class TestContratoDeHuecos:

    @pytest.mark.asyncio
    async def test_1_issue_con_unico_archivo_desaparecido_no_cuenta(self, db):
        """Caso 1: el número cuyo único archivo está `is_missing` NO se posee."""
        s = await crear_serie(db, total_issues=3)
        await crear_issue(db, s, "1", archivos=(False,))
        await crear_issue(db, s, "2", archivos=(True,))   # desaparecido del disco

        h = await huecos_de_serie(db, s)

        assert h.computable is True
        assert h.faltantes == [2, 3]

    @pytest.mark.asyncio
    async def test_2_con_dos_archivos_y_uno_disponible_si_cuenta(self, db):
        """Caso 2: basta UN archivo disponible para poseer el número."""
        s = await crear_serie(db, total_issues=2)
        await crear_issue(db, s, "1", archivos=(True, False))

        h = await huecos_de_serie(db, s)

        assert h.faltantes == [2]
        assert await numeros_poseidos(db, s.id) == {1}

    @pytest.mark.asyncio
    async def test_3_omnibus_no_cubre_la_grapa_del_mismo_numero(self, db):
        """Caso 3: un ómnibus/tomo #12 NO ocupa el hueco de la grapa #12."""
        s = await crear_serie(db, total_issues=12)
        await crear_issue(db, s, "12", formato=IssueFormat.OMNIBUS, archivos=(False,))

        h = await huecos_de_serie(db, s)

        assert 12 in h.faltantes
        assert await numeros_poseidos(db, s.id) == set()

    @pytest.mark.asyncio
    async def test_4_issue_catalogado_sin_archivo_no_cuenta(self, db):
        """Caso 4: estar en el catálogo no es tenerlo. Sin archivo, es hueco."""
        s = await crear_serie(db, total_issues=2)
        await crear_issue(db, s, "1", archivos=())

        h = await huecos_de_serie(db, s)

        assert h.faltantes == [1, 2]

    @pytest.mark.asyncio
    async def test_5_sin_sort_order_poblado_los_huecos_no_salen_de_un_conjunto_vacio(self, db):
        """Caso 5 (el central): con `sort_order` SIN poblar — el estado real de
        cualquier instalación — los huecos no pueden salir del conjunto vacío.
        Salen de una regla de numeración explícita: número entero de una grapa
        con archivo disponible. Total 5 con #1..#3 en disco → [4, 5], no [1..5]."""
        s = await crear_serie(db, total_issues=5)
        for n in ("1", "2", "3"):
            await crear_issue(db, s, n, archivos=(False,))

        poblados = (await db.execute(
            select(func.count()).select_from(Issue).where(Issue.sort_order.isnot(None))
        )).scalar()
        assert poblados == 0, "el test pierde sentido si sort_order se poblara"

        h = await huecos_de_serie(db, s)

        assert h.computable is True
        assert h.faltantes == [4, 5]

    @pytest.mark.asyncio
    async def test_5b_sin_total_conocido_no_se_inventan_huecos(self, db):
        """Caso 5, la otra mitad: sin `total_issues` no hay nada que restar. La
        vista debe decir "no se puede calcular", no inventar ni un hueco."""
        s = await crear_serie(db, total_issues=None)
        await crear_issue(db, s, "1", archivos=(False,))

        h = await huecos_de_serie(db, s)

        assert h.computable is False
        assert h.faltantes == []
        assert h.motivo

    @pytest.mark.asyncio
    async def test_annual_no_tapa_el_hueco_de_la_grapa(self, db):
        """Regresión de C2, que el cambio no debe perder: un 'Annual 1' con
        archivo NO cubre el hueco de la grapa nº 1."""
        s = await crear_serie(db, total_issues=2)
        await crear_issue(db, s, "Annual 1", archivos=(False,))

        h = await huecos_de_serie(db, s)

        assert h.faltantes == [1, 2]

    @pytest.mark.asyncio
    async def test_decimal_tampoco_tapa_el_entero(self, db):
        """Regresión de C2: un `1.5` (Annual/especial) no es el nº 1."""
        s = await crear_serie(db, total_issues=2)
        await crear_issue(db, s, "1.5", archivos=(False,))

        h = await huecos_de_serie(db, s)

        assert h.faltantes == [1, 2]
