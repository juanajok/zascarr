"""
tests/test_library_adopter.py

Suite de LibraryAdopter (B11): adoptar una biblioteca ya organizada en
el primer arranque, SIN mover ni renombrar nada — a diferencia de
Importer, que sí mueve desde las carpetas de descargas.
"""
from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from zascarr.models import File, ImportRun
from zascarr.services.library_adopter import AdoptionReport, LibraryAdopter, _MARCADOR_HECHO


def make_cbz(path: Path) -> None:
    with zipfile.ZipFile(path, "w"):
        pass


class FakeExecResult:
    def __init__(self, value=None):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class FakeSession:
    """Cola de resultados en orden: cada llamada a execute() saca el
    siguiente. Mismo patrón que test_importer.py."""

    def __init__(self, queue: list):
        self._queue = list(queue)
        self.added: list = []
        self.flush = AsyncMock()

    async def execute(self, _statement):
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)


class TestShouldRun:

    @pytest.mark.asyncio
    async def test_ya_adoptado_antes_no_vuelve_a_correr(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        session = FakeSession([])
        adopter = LibraryAdopter(db=session)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "zascarr.services.runtime_settings.RuntimeSettingsService.get_flag",
                AsyncMock(return_value=True),
            )
            assert await adopter.should_run() is False

    @pytest.mark.asyncio
    async def test_con_series_ya_existentes_no_corre(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        session = FakeSession([FakeExecResult(5)])
        adopter = LibraryAdopter(db=session)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "zascarr.services.runtime_settings.RuntimeSettingsService.get_flag",
                AsyncMock(return_value=False),
            )
            assert await adopter.should_run() is False

    @pytest.mark.asyncio
    async def test_biblioteca_vacia_no_corre(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        session = FakeSession([FakeExecResult(0)])
        adopter = LibraryAdopter(db=session)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "zascarr.services.runtime_settings.RuntimeSettingsService.get_flag",
                AsyncMock(return_value=False),
            )
            assert await adopter.should_run() is False

    @pytest.mark.asyncio
    async def test_biblioteca_con_comics_y_catalogo_vacio_si_corre(self, monkeypatch, tmp_path):
        make_cbz(tmp_path / "Batman 001.cbz")
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        session = FakeSession([FakeExecResult(0)])
        adopter = LibraryAdopter(db=session)

        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "zascarr.services.runtime_settings.RuntimeSettingsService.get_flag",
                AsyncMock(return_value=False),
            )
            assert await adopter.should_run() is True


class TestAdopt:

    @pytest.mark.asyncio
    async def test_archivo_sin_match_se_registra_en_su_sitio_sin_moverlo(self, monkeypatch, tmp_path):
        """Bug que se evita a propósito: un archivo ya organizado que el
        matcher no reconoce NUNCA debe moverse a _Unsorted — se queda
        donde el coleccionista lo puso, solo se marca pendiente."""
        original = tmp_path / "Serie Rara Sin Numero.cbz"
        make_cbz(original)
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )

        # _triage_and_match hace 1 query (dedup, sin resultado) y el
        # matcher (sin título/número extraíble) no llega a consultar
        # series — decide() corta antes. Luego set_flag hace su propia
        # query interna (_row()).
        session = FakeSession([
            FakeExecResult(None),  # dedup: sin duplicado
            FakeExecResult(MagicMock(values={})),  # set_flag -> _row()
        ])
        adopter = LibraryAdopter(db=session)
        report = await adopter.adopt()

        assert original.exists()  # nunca se movió
        assert report.files_scanned == 1
        assert report.unsorted_count == 1
        assert report.registered_count == 0
        assert len(session.added) == 2  # File + ImportRun (set_flag no añade fila nueva)
        file_rec = next(o for o in session.added if isinstance(o, File))
        assert file_rec.file_path == str(original)
        assert file_rec.issue_id is None
        assert file_rec.metadata_["adopted"] is True

    @pytest.mark.asyncio
    async def test_duplicado_no_se_registra_dos_veces(self, monkeypatch, tmp_path):
        original = tmp_path / "Batman 001.cbz"
        make_cbz(original)
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        existente = File(id=uuid4(), file_name="Batman #001.cbz", file_path="/otro/sitio.cbz")
        session = FakeSession([
            FakeExecResult(existente),  # dedup: SÍ hay duplicado
            FakeExecResult(MagicMock(values={})),  # set_flag -> _row()
        ])
        adopter = LibraryAdopter(db=session)
        report = await adopter.adopt()

        assert report.duplicate_count == 1
        assert report.registered_count == 0
        assert not any(isinstance(o, File) for o in session.added)

    @pytest.mark.asyncio
    async def test_marca_hecho_incluso_si_todo_queda_sin_clasificar(self, monkeypatch, tmp_path):
        """El marcador se pone pase lo que pase — el objetivo es no
        repetir el escaneo completo, no garantizar que hubo matches."""
        make_cbz(tmp_path / "Algo.cbz")
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        fila_settings = MagicMock(values={})
        session = FakeSession([
            FakeExecResult(None),
            FakeExecResult(fila_settings),
        ])
        adopter = LibraryAdopter(db=session)
        await adopter.adopt()

        assert fila_settings.values.get(_MARCADOR_HECHO) is True

    @pytest.mark.asyncio
    async def test_persiste_import_run_con_kind_adoption(self, monkeypatch, tmp_path):
        make_cbz(tmp_path / "Algo.cbz")
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        session = FakeSession([
            FakeExecResult(None),
            FakeExecResult(MagicMock(values={})),
        ])
        adopter = LibraryAdopter(db=session)
        await adopter.adopt()

        run = next(o for o in session.added if isinstance(o, ImportRun))
        assert run.details["kind"] == "adoption"
