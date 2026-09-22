"""
tests/test_importer.py

Suite del ImportReport (B1/B3): informe legible de cada ciclo de
Importer.scan_and_import() — quién se importó, quién se descartó por
duplicado y de qué, quién quedó sin clasificar y por qué.
"""
from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from zascarr.models import File, ImportRun
from zascarr.services.importer import Importer, ImportReport


def make_cbz(path: Path) -> None:
    """CBZ mínimo pero válido (zip vacío): suficiente para que triage()
    lo hashee y lo abra sin marcarlo como ilegible."""
    with zipfile.ZipFile(path, "w"):
        pass


class TestImportReport:

    def test_contadores_derivados_de_las_listas(self):
        report = ImportReport(started_at=datetime.now(timezone.utc))
        report.imported.append("a")
        report.duplicates.extend(["b", "c"])
        report.unsorted.append("d")
        report.errors.extend(["e", "f", "g"])

        assert report.imported_count == 1
        assert report.duplicate_count == 2
        assert report.unsorted_count == 1
        assert report.error_count == 3


class FakeDedupeSession:
    """La primera consulta (SELECT File...) devuelve el archivo existente
    que dispara el duplicado. No debe llegar a consultarse nada más: el
    método retorna antes de tocar el matcher."""

    def __init__(self, existing_file):
        self._existing = existing_file
        self.queries = 0

    async def execute(self, _statement):
        self.queries += 1
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=self._existing)
        return result


class TestImportFileDuplicado:

    @pytest.mark.asyncio
    async def test_duplicado_no_se_mueve_y_queda_en_el_informe(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "zascarr.services.importer.get_settings",
            lambda: MagicMock(
                library_path=tmp_path / "library",
                transmission_download_dir=str(tmp_path / "downloads"),
                amule_incoming_dir=str(tmp_path / "amule"),
                downloads_path=tmp_path / "downloads",
            ),
        )
        src = tmp_path / "Batman 001.cbz"
        make_cbz(src)

        existing = File(id=uuid4(), file_name="Batman #001.cbz",
                        file_path="/library/Batman #001.cbz")
        session = FakeDedupeSession(existing)
        importer = Importer(session)
        report = ImportReport(started_at=datetime.now(timezone.utc))

        await importer._import_file(src, report)

        assert report.duplicates == [
            "Batman 001.cbz — duplicado de Batman #001.cbz, descartado"
        ]
        assert report.imported == []
        assert src.exists()          # nunca se movió
        assert session.queries == 1  # nunca llegó a consultar el matcher


class TestPersistRun:

    @pytest.mark.asyncio
    async def test_mapea_reporte_a_import_run(self):
        report = ImportReport(
            started_at=datetime(2026, 9, 21, 3, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 9, 21, 3, 5, tzinfo=timezone.utc),
            files_scanned=3,
        )
        report.imported.append("Batman 001.cbz → Comics/Batman (2011)/Batman #001.cbz")
        report.duplicates.append("Batman 001 copy.cbz — duplicado de Batman #001.cbz, descartado")

        added = []
        session = MagicMock()
        session.add = lambda obj: added.append(obj)
        session.flush = AsyncMock()

        importer = Importer.__new__(Importer)  # evita __init__ (get_settings)
        importer._db = session

        await importer._persist_run(report)

        assert len(added) == 1
        run = added[0]
        assert isinstance(run, ImportRun)
        assert run.files_scanned == 3
        assert run.imported_count == 1
        assert run.duplicate_count == 1
        assert run.unsorted_count == 0
        assert run.error_count == 0
        assert run.details["imported"] == report.imported
        assert run.details["duplicates"] == report.duplicates
        session.flush.assert_awaited_once()
