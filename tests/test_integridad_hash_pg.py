"""Integridad — `File.original_sha256`: dedupe, etiquetado y reenlazado, contra
Postgres real.

Casos de prueba de la ficha `benchmark-integridad-hash-dedupe`. El contrato en
tres partes: el dedupe reconoce el original por `sha256_hash` **o**
`original_sha256` (sin `MultipleResultsFound`), B6 fija `original_sha256` solo la
primera vez, y un fichero que reaparece se **reenlaza** a la fila desaparecida.

Se salta sin `TEST_DATABASE_URL`, mismo patrón que `test_b6_tagger_pg.py`.
"""
from __future__ import annotations

import hashlib
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.core.importer_triage import TriageResult, sha256_streaming
from zascarr.models import ComicTradition, File, FileFormat, Issue, Series
from zascarr.services.importer import (
    Importer,
    ImportReport,
    _coincidencias_de_hash,
    _triage_and_match,
)
from zascarr.services.tagger import ESCRITO, TaggerService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

PAGINAS = ["p001.jpg", "p002.jpg"]


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
async def db():
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL or ""))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        nombre = (await session.execute(text("SELECT current_database()"))).scalar()
        if not nombre or "test" not in nombre.lower():
            raise RuntimeError(f"TEST_DATABASE_URL apunta a «{nombre}»; se niega.")
        try:
            yield session
        finally:
            if transaccion.is_active:
                await transaccion.rollback()
    await engine.dispose()


def _sha256(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _crear_cbz(ruta: Path, xml: bytes | None = None) -> Path:
    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in PAGINAS:
            zf.writestr(p, f"pagina-{p}".encode())
        if xml is not None:
            zf.writestr("ComicInfo.xml", xml)
    return ruta


async def _montar(db, tmp_path: Path, *, formato: FileFormat = FileFormat.CBZ) -> tuple[File, Path]:
    """Serie + Issue + File con un CBZ real sin etiquetar (o un CBR que no se
    toca)."""
    serie = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                   start_year=1977)
    db.add(serie)
    issue = Issue(id=uuid4(), series_id=serie.id, issue_number="1", volume=1)
    db.add(issue)
    ruta = tmp_path / f"fichero.{formato.value}"
    if formato is FileFormat.CBZ:
        _crear_cbz(ruta)
    else:
        ruta.write_bytes(b"no es un zip")
    archivo = File(
        id=uuid4(), issue_id=issue.id, file_path=str(ruta), file_name=ruta.name,
        file_format=formato, file_size_bytes=ruta.stat().st_size,
        sha256_hash=_sha256(ruta),
    )
    db.add(archivo)
    await db.flush()
    return archivo, ruta


def _fila(db, *, sha256_hash: str, original_sha256: str | None = None,
           is_missing: bool = False, imported_at=None, nombre="x.cbz") -> File:
    f = File(id=uuid4(), file_path=f"/lib/{uuid4()}.cbz", file_name=nombre,
             file_format=FileFormat.CBZ, sha256_hash=sha256_hash,
             original_sha256=original_sha256, is_missing=is_missing,
             imported_at=imported_at)
    db.add(f)
    return f


class TestDedupeIntegridad:
    """La consulta compartida: por cualquiera de los dos hashes, orden presente
    primero, y sin `MultipleResultsFound` (antes `scalar_one_or_none()`)."""

    @pytest.mark.asyncio
    async def test_dos_filas_mismo_hash_no_lanzan_multiple_results(self, db, tmp_path):
        """Regresión del hallazgo 7: `scalar_one_or_none()` sobre una columna no
        única lanzaba `MultipleResultsFound` y rompía el ciclo para siempre."""
        ruta = _crear_cbz(tmp_path / "a.cbz")
        sha = sha256_streaming(ruta)
        _fila(db, sha256_hash=sha, nombre="vieja.cbz",
              imported_at=datetime(2020, 1, 1, tzinfo=UTC))
        _fila(db, sha256_hash=sha, nombre="nueva.cbz",
              imported_at=datetime(2021, 1, 1, tzinfo=UTC))
        await db.flush()

        outcome = await _triage_and_match(db, ruta)

        assert outcome.duplicate_of == "vieja.cbz"   # presente más antigua primero
        assert outcome.recuperar is None

    @pytest.mark.asyncio
    async def test_coincide_por_original_sha256(self, db, tmp_path):
        """Caso 1: el original de un CBZ ya etiquetado se reconoce por
        `original_sha256`, no solo por `sha256_hash`."""
        ruta = _crear_cbz(tmp_path / "a.cbz")
        sha = sha256_streaming(ruta)
        _fila(db, sha256_hash="d" * 64, original_sha256=sha, nombre="etiquetado.cbz")
        await db.flush()

        outcome = await _triage_and_match(db, ruta)

        assert outcome.duplicate_of == "etiquetado.cbz"

    @pytest.mark.asyncio
    async def test_todas_missing_es_recuperar(self, db, tmp_path):
        """Caso 7: si TODAS las coincidencias están desaparecidas, se reenlaza,
        no se descarta."""
        ruta = _crear_cbz(tmp_path / "a.cbz")
        sha = sha256_streaming(ruta)
        vieja = _fila(db, sha256_hash=sha, is_missing=True, nombre="vieja.cbz",
                      imported_at=datetime(2020, 1, 1, tzinfo=UTC))
        await db.flush()

        outcome = await _triage_and_match(db, ruta)

        assert outcome.recuperar is vieja
        assert outcome.duplicate_of is None

    @pytest.mark.asyncio
    async def test_presente_y_missing_es_duplicado(self, db, tmp_path):
        """Caso 11: con una presente y una desaparecida, gana la presente — es un
        duplicado real, no se reenlaza nada."""
        ruta = _crear_cbz(tmp_path / "a.cbz")
        sha = sha256_streaming(ruta)
        _fila(db, sha256_hash=sha, is_missing=True,
              imported_at=datetime(2020, 1, 1, tzinfo=UTC))
        _fila(db, sha256_hash=sha, is_missing=False, nombre="presente.cbz",
              imported_at=datetime(2021, 1, 1, tzinfo=UTC))
        await db.flush()

        outcome = await _triage_and_match(db, ruta)

        assert outcome.duplicate_of == "presente.cbz"
        assert outcome.recuperar is None

    @pytest.mark.asyncio
    async def test_orden_determinista_presentes_primero(self, db):
        sha = "e" * 64
        _fila(db, sha256_hash=sha, is_missing=True, nombre="m1.cbz",
              imported_at=datetime(2020, 1, 1, tzinfo=UTC))
        _fila(db, sha256_hash=sha, is_missing=False, nombre="p.cbz",
              imported_at=datetime(2022, 1, 1, tzinfo=UTC))
        _fila(db, sha256_hash=sha, is_missing=True, nombre="m2.cbz",
              imported_at=datetime(2021, 1, 1, tzinfo=UTC))
        await db.flush()

        coincidencias = await _coincidencias_de_hash(db, sha)

        assert [f.file_name for f in coincidencias] == ["p.cbz", "m1.cbz", "m2.cbz"]


class TestOriginalSha256Tagger:
    """B6 fija `original_sha256` solo la primera vez que reemplaza un CBZ."""

    @pytest.mark.asyncio
    async def test_se_fija_la_primera_vez_y_no_se_sobrescribe(self, db, tmp_path):
        """Caso 3: la segunda escritura (overlay) no lo cambia."""
        archivo, ruta = await _montar(db, tmp_path)
        original = _sha256(ruta)
        servicio = TaggerService(db)

        r1 = await servicio.ejecutar(archivo, dry_run=False)
        assert r1.accion == ESCRITO
        assert archivo.original_sha256 == original

        # Overlay: cambia la BD para forzar una segunda escritura.
        serie = (await db.execute(
            select(Series).join(Issue, Issue.series_id == Series.id)
            .where(Issue.id == archivo.issue_id))).scalar_one()
        serie.title = "Thorgal (reedición)"
        await db.flush()
        await servicio.ejecutar(archivo, dry_run=False)

        assert archivo.original_sha256 == original

    @pytest.mark.asyncio
    async def test_bd_desfasada_calcula_el_original_del_disco(self, db, tmp_path):
        """Caso 4: con `sha256_hash`/`file_size_bytes` desfasados, el original
        sale del disco (justo antes de reemplazar), no de la BD mentirosa."""
        archivo, ruta = await _montar(db, tmp_path)
        original = _sha256(ruta)
        archivo.sha256_hash = "0" * 64
        archivo.file_size_bytes = 1
        await db.flush()

        r = await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert r.accion == ESCRITO
        assert archivo.original_sha256 == original

    @pytest.mark.asyncio
    async def test_cbr_no_toca_original(self, db, tmp_path):
        """Caso 8: B6 no toca CBR, así que `original_sha256` sigue NULL."""
        archivo, _ = await _montar(db, tmp_path, formato=FileFormat.CBR)

        await TaggerService(db).ejecutar(archivo, dry_run=False)

        assert archivo.original_sha256 is None


class TestReenlazado:
    """Un fichero que reaparece se reenlaza a la fila `is_missing`."""

    @pytest.mark.asyncio
    async def test_actualiza_la_fila_y_cuenta_como_recuperado(self, db, tmp_path):
        """Casos 9 y 10: `imported_at` se reinicia, la fila pasa a describir el
        fichero nuevo, las marcas de ComicInfo se vacían si el entrante es el
        original, y el informe lo cuenta como importado («recuperado»)."""
        serie = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN,
                       start_year=2011)
        db.add(serie)
        issue = Issue(id=uuid4(), series_id=serie.id, issue_number="1")
        db.add(issue)

        entrante = tmp_path / "descargas" / "original.cbz"
        entrante.parent.mkdir()
        _crear_cbz(entrante)
        hash_original = sha256_streaming(entrante)

        fila = File(
            id=uuid4(), issue_id=issue.id, file_path="/lib/desaparecido.cbz",
            file_name="desaparecido.cbz", file_format=FileFormat.CBZ,
            sha256_hash="d" * 64, original_sha256=hash_original,
            is_missing=True, missing_since=datetime(2020, 1, 1, tzinfo=UTC),
            imported_at=datetime(2020, 1, 1, tzinfo=UTC),
            metadata_={"comicinfo_estado": {"resultado": "escrito"},
                       "comicinfo_propio": {"Series": "Batman"}},
        )
        db.add(fila)
        await db.flush()

        importer = Importer.__new__(Importer)
        importer._db = db
        importer._library = tmp_path / "lib"
        report = ImportReport(started_at=datetime.now(UTC))

        await importer._reenlazar(
            fila, entrante, TriageResult(path=entrante, sha256=hash_original), report)

        # La fila describe el fichero nuevo y queda presente.
        assert fila.is_missing is False
        assert fila.missing_since is None
        assert fila.sha256_hash == hash_original
        assert fila.file_name.endswith(".cbz")
        assert fila.file_path.startswith(str(tmp_path / "lib"))
        # D8: imported_at se reinicia (el cierre compara contra Wishlist.added_at).
        assert fila.imported_at > datetime(2020, 1, 2, tzinfo=UTC)
        # El entrante es el original de una fila etiquetada: marcas vacías,
        # original_sha256 conservado.
        assert fila.original_sha256 == hash_original
        assert "comicinfo_estado" not in (fila.metadata_ or {})
        assert "comicinfo_propio" not in (fila.metadata_ or {})
        # Cuenta como importado, distinguido con «recuperado» (E4 avisa igual).
        assert len(report.imported) == 1
        assert "(recuperado)" in report.imported[0]
        assert not entrante.exists()   # se movió a la biblioteca
