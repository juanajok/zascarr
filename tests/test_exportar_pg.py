"""#341: exportación CSV contra Postgres real (solo lectura y streaming)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    Note,
    Publisher,
    Series,
    Wishlist,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.exportar import (
    BOM,
    CABECERAS_COLECCION,
    CABECERAS_COLECCION_CON_NOTAS,
    CABECERAS_DESEADOS,
    filas_coleccion,
    filas_deseados,
    generar_csv,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
async def db():
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        nombre = (await session.execute(text("SELECT current_database()"))).scalar()
        if not nombre or "test" not in nombre.lower():
            raise RuntimeError(f"TEST_DATABASE_URL apunta a «{nombre}»; se niega.")
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


async def _csv_crudo(filas, cabeceras) -> bytes:
    return b"".join([trozo async for trozo in generar_csv(filas, cabeceras)])


async def _csv(filas) -> tuple[bytes, str]:
    crudo = await _csv_crudo(filas, CABECERAS_COLECCION)
    return crudo, crudo.decode("utf-8-sig")


async def _csv_deseados(filas) -> tuple[bytes, str]:
    crudo = await _csv_crudo(filas, CABECERAS_DESEADOS)
    return crudo, crudo.decode("utf-8-sig")


async def _montar(db, tmp_path: Path):
    publisher = Publisher(id=uuid4(), name=f"Editorial {uuid4().hex}")
    db.add(publisher)
    serie = Series(
        id=uuid4(), title="Thorgal", start_year=1980, tradition=ComicTradition.AMERICAN,
        publisher_id=publisher.id, wishlist_policy=WishlistPolicy.MISSING,
    )
    db.add(serie)
    issue = Issue(
        id=uuid4(), series_id=serie.id, issue_number="1", title="La magia",
        release_date=date(1980, 5, 1), sort_order=1.0,
    )
    db.add(issue)
    ruta = tmp_path / "thorgal-1.cbz"
    ruta.write_bytes(b"no se lee")
    db.add(File(
        id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
        file_format=FileFormat.CBZ, file_size_bytes=3, is_missing=False,
    ))
    db.add(File(
        id=uuid4(), issue_id=issue.id, file_path=str(tmp_path / "thorgal-1.cbr"),
        file_name="thorgal-1.cbr", file_format=FileFormat.CBR,
        file_size_bytes=3, is_missing=True,
    ))
    db.add(Wishlist(id=uuid4(), issue_id=issue.id, status=WishlistStatus.SEARCHING,
                    notes="Falta el número 2", numero=1))
    db.add(Wishlist(id=uuid4(), series_id=serie.id, status=WishlistStatus.WANTED,
                    notes="Serie completa", numero=None))
    await db.flush()
    return serie, issue


@pytest.mark.asyncio
async def test_coleccion_csv_pg(db, tmp_path):
    await _montar(db, tmp_path)
    crudo, texto = await _csv(filas_coleccion(db))
    assert crudo.startswith(BOM.encode("utf-8"))
    lineas = texto.splitlines()
    assert lineas[0] == ",".join(CABECERAS_COLECCION)
    assert any("Thorgal,1980,Editorial " in linea for linea in lineas)
    assert "Thorgal,1980,Editorial " in texto
    assert "La magia" in texto and "CBZ" in texto and "tengo" in texto
    assert "falta" in texto and "CBR" in texto
    assert str(tmp_path) not in texto
    assert "file_path" not in texto


@pytest.mark.asyncio
async def test_deseados_csv_pg(db, tmp_path):
    await _montar(db, tmp_path)
    crudo, texto = await _csv_deseados(filas_deseados(db))
    assert crudo.startswith(BOM.encode("utf-8"))
    lineas = texto.splitlines()
    assert lineas[0] == ",".join(CABECERAS_DESEADOS)
    assert "Thorgal" in texto and "buscando" in texto and "faltantes" in texto
    assert "Falta el número 2" in texto and "Serie completa" in texto
    assert str(tmp_path) not in texto


@pytest.mark.asyncio
async def test_consulta_stream_no_carga_todo(db, tmp_path, monkeypatch):
    await _montar(db, tmp_path)
    generador = filas_coleccion(db)
    primera = await anext(generador)
    assert primera[0] == "Thorgal"
    await generador.aclose()


@pytest.mark.asyncio
async def test_exportar_notas_opcionales(db, tmp_path):
    serie, issue = await _montar(db, tmp_path)
    db.add(Note(series_id=serie.id, texto="nota de serie"))
    db.add(Note(issue_id=issue.id, texto="nota de número"))
    await db.flush()

    sin = await _csv_crudo(filas_coleccion(db), CABECERAS_COLECCION)
    texto_sin = sin.decode("utf-8-sig")
    assert "Nota de la serie" not in texto_sin
    assert "nota de serie" not in texto_sin and "nota de número" not in texto_sin

    con = await _csv_crudo(filas_coleccion(db, incluir_notas=True),
                           CABECERAS_COLECCION_CON_NOTAS)
    texto = con.decode("utf-8-sig")
    assert texto.splitlines()[0].endswith("Nota de la serie,Nota del número")
    assert "nota de serie" in texto and "nota de número" in texto
