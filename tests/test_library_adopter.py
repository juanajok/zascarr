"""
tests/test_library_adopter.py

Suite de LibraryAdopter (B11): adoptar una biblioteca ya organizada en
el primer arranque, SIN mover ni renombrar nada — a diferencia de
Importer, que sí mueve desde las carpetas de descargas.
"""
from __future__ import annotations

import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from zascarr.models import File, ImportRun
from zascarr.services.library_adopter import (
    AdoptionReport,
    EstadoAdopcion,
    LibraryAdopter,
    _MARCADOR_HECHO,
)


def make_cbz(path: Path) -> None:
    with zipfile.ZipFile(path, "w"):
        pass


class _Scalars:
    def __init__(self, value):
        self._value = value

    def all(self):
        return [] if self._value is None else [self._value]


class FakeExecResult:
    def __init__(self, value=None):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        # La consulta de dedupe devuelve una lista de coincidencias
        # (`scalars().all()`), no un único `scalar_one_or_none()`.
        return _Scalars(self._value)


class FakeSession:
    """Cola de resultados en orden: cada llamada a execute() saca el
    siguiente. Mismo patrón que test_importer.py."""

    def __init__(self, queue: list):
        self._queue = list(queue)
        self.added: list = []
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.commits_en_lote = 0

    @asynccontextmanager
    async def begin_nested(self):
        """Savepoint por archivo (la adopción lo usa): aquí solo hace falta poder entrar y salir."""
        yield

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


class TestEstado:
    """V4: el Inicio necesita el POR QUÉ, no solo el sí/no de `should_run`."""

    @staticmethod
    async def _estado(monkeypatch, tmp_path, *, marcador, series):
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        cola = [] if marcador else [FakeExecResult(series)]
        adopter = LibraryAdopter(db=FakeSession(cola))
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "zascarr.services.runtime_settings.RuntimeSettingsService.get_flag",
                AsyncMock(return_value=marcador),
            )
            return await adopter.estado()

    @pytest.mark.asyncio
    async def test_hecha_si_hay_marcador_aunque_el_catalogo_este_vacio(self, monkeypatch, tmp_path):
        make_cbz(tmp_path / "Batman 001.cbz")
        estado = await self._estado(monkeypatch, tmp_path, marcador=True, series=0)
        assert estado is EstadoAdopcion.HECHA

    @pytest.mark.asyncio
    async def test_catalogo_previo_si_hay_series_sin_marcador(self, monkeypatch, tmp_path):
        make_cbz(tmp_path / "Batman 001.cbz")
        estado = await self._estado(monkeypatch, tmp_path, marcador=False, series=5)
        assert estado is EstadoAdopcion.CATALOGO_PREVIO

    @pytest.mark.asyncio
    async def test_sin_tebeos_si_la_carpeta_esta_vacia(self, monkeypatch, tmp_path):
        estado = await self._estado(monkeypatch, tmp_path, marcador=False, series=0)
        assert estado is EstadoAdopcion.SIN_TEBEOS

    @pytest.mark.asyncio
    async def test_sin_tebeos_si_la_carpeta_no_existe(self, monkeypatch, tmp_path):
        estado = await self._estado(
            monkeypatch, tmp_path / "no-existe", marcador=False, series=0)
        assert estado is EstadoAdopcion.SIN_TEBEOS

    @pytest.mark.asyncio
    async def test_pendiente_con_tebeos_y_catalogo_vacio(self, monkeypatch, tmp_path):
        make_cbz(tmp_path / "Batman 001.cbz")
        estado = await self._estado(monkeypatch, tmp_path, marcador=False, series=0)
        assert estado is EstadoAdopcion.PENDIENTE

    @pytest.mark.asyncio
    async def test_should_run_solo_es_verdadero_si_esta_pendiente(self, monkeypatch, tmp_path):
        """should_run es `estado() is PENDIENTE` (mismas consultas, mismo orden)."""
        make_cbz(tmp_path / "Batman 001.cbz")
        for marcador, series, esperado in ((True, 0, False), (False, 5, False), (False, 0, True)):
            monkeypatch.setattr(
                "zascarr.services.library_adopter.get_settings",
                lambda: MagicMock(library_path=tmp_path),
            )
            adopter = LibraryAdopter(db=FakeSession([] if marcador else [FakeExecResult(series)]))
            with pytest.MonkeyPatch().context() as mp:
                mp.setattr(
                    "zascarr.services.runtime_settings.RuntimeSettingsService.get_flag",
                    AsyncMock(return_value=marcador),
                )
                assert await adopter.should_run() is esperado


@pytest.fixture(autouse=True)
def _sin_rutas_registradas(monkeypatch):
    """`adopt` empieza preguntando qué rutas ya están registradas; estas pruebas de sesión simulada
    no la modelan (su cola es la de los archivos). Las pruebas con Postgres real SÍ la ejercitan."""
    monkeypatch.setattr(LibraryAdopter, "_rutas_registradas", AsyncMock(return_value=set()))
    monkeypatch.setattr(LibraryAdopter, "_ya_registrada", AsyncMock(return_value=False))


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
    async def test_duplicado_no_se_registra_dos_veces(self, monkeypatch, tmp_path, tmp_path_factory):
        original = tmp_path / "Batman 001.cbz"
        make_cbz(original)
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        # La copia ya registrada EXISTE (fuera de la biblioteca que se recorre): un duplicado real. Con una ruta
        # ficticia sería una referencia obsoleta, que ahora se recupera en vez de descartarse.
        copia = tmp_path_factory.mktemp("copia_registrada") / "sitio.cbz"
        make_cbz(copia)
        existente = File(id=uuid4(), file_name="Batman #001.cbz", file_path=str(copia))
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
        """Sin ERRORES, el marcador se pone aunque todo quede sin clasificar: «registrado» no es
        «clasificado». (Cambio de 2026-10-05: el marcador ya NO se pone «pase lo que pase»; ver el
        test de errores.)"""
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
    async def test_con_errores_el_marcador_no_se_pone(self, monkeypatch, tmp_path):
        """Un marcador no puede esconder lo pendiente: si un archivo falla, el registro NO consta
        como hecho y el estado sigue ofreciendo continuar."""
        make_cbz(tmp_path / "Algo.cbz")
        monkeypatch.setattr(
            "zascarr.services.library_adopter.get_settings",
            lambda: MagicMock(library_path=tmp_path),
        )
        monkeypatch.setattr(
            LibraryAdopter, "_adopt_file", AsyncMock(side_effect=RuntimeError("disco roto")))
        fila_settings = MagicMock(values={})
        session = FakeSession([FakeExecResult(fila_settings)])
        report = await LibraryAdopter(db=session).adopt()

        assert report.error_count == 1
        assert "disco roto" not in report.errors[0]          # sin mensajes del sistema
        assert _MARCADOR_HECHO not in fila_settings.values

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
