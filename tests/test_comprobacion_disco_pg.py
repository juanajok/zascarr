# ruff: noqa: E501
"""#232 — cerrojo de ciclo y persistencia del disparador contra PostgreSQL real."""
from __future__ import annotations

import asyncio
import os
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import ComicTradition, File, FileFormat, ImportRun, Series
from zascarr.services import comprobacion_disco as servicio
from zascarr.services.comprobacion_disco import FaseCicloDisco
from zascarr.services.disponibilidad import ultima_ejecucion_importador
from zascarr.services.importer import Importer, ImportReport

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def fabrica(url_bd):
    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    async with motor.begin() as conexion:
        await conexion.execute(text("TRUNCATE import_runs, files, issues, series CASCADE"))
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


@pytest.fixture(autouse=True)
async def _limpio():
    servicio.reiniciar_para_pruebas()
    yield
    await servicio.detener()


def _informe(disparador="manual"):
    ahora = datetime.now(UTC)
    return ImportReport(started_at=ahora, finished_at=ahora, disparador=disparador,
                        run_id=uuid4())


class TestCerrojoDeCiclo:

    async def test_cerrojo_tomado_por_otra_conexion_no_ejecuta(self, fabrica, url_bd):
        llamadas = []

        async def ejecutar(*_a, **_k):
            llamadas.append("ciclo")
            return _informe()

        motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
        async with motor.connect() as conexion:
            await conexion.execute(text("SELECT pg_advisory_lock(326, 2)"))
            try:
                assert await servicio.ejecutar_automatico(fabrica, ejecutar=ejecutar) is None
            finally:
                await conexion.execute(text("SELECT pg_advisory_unlock(326, 2)"))
        await motor.dispose()
        assert llamadas == []
        assert servicio.estado_actual().fase is FaseCicloDisco.INACTIVO

    async def test_una_excepcion_libera_el_cerrojo(self, fabrica, url_bd):
        async def ejecutar(*_a, **_k):
            raise RuntimeError("fallo simulado")

        servicio.iniciar_manual(fabrica, ejecutar=ejecutar)
        await asyncio.wait_for(servicio._tarea, 5)
        assert servicio.estado_actual().fase is FaseCicloDisco.ERROR
        assert servicio.estado_actual().causa == "RuntimeError"

        motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
        async with motor.connect() as conexion:
            libre = (await conexion.execute(
                text("SELECT pg_try_advisory_lock(326, 2)"))).scalar()
            if libre:
                await conexion.execute(text("SELECT pg_advisory_unlock(326, 2)"))
        await motor.dispose()
        assert libre is True


class TestPersistenciaYLectura:

    async def test_persist_run_guarda_run_id_y_disparador(self, fabrica):
        ahora = datetime.now(UTC)
        report = ImportReport(started_at=ahora, finished_at=ahora, disparador="manual")
        async with fabrica() as s:
            importer = Importer.__new__(Importer)
            importer._db = s
            await importer._persist_run(report)
            await s.commit()
        assert report.run_id is not None
        async with fabrica() as s:
            run = (await s.execute(select(ImportRun).where(ImportRun.id == report.run_id))).scalar_one()
            assert run.details["disparador"] == "manual"
            assert "kind" not in run.details

    async def test_ultima_ejecucion_solo_mira_ciclos_del_importador(self, fabrica):
        ahora = datetime.now(UTC)
        async with fabrica() as s:
            s.add_all([
                ImportRun(started_at=ahora, finished_at=ahora, files_scanned=7,
                          imported_count=1, details={"disparador": "manual",
                                                     "reappeared": ["a"], "errors": []}),
                ImportRun(started_at=ahora, finished_at=ahora, files_scanned=99,
                          details={"kind": "adoption", "disparador": "manual"}),
                ImportRun(started_at=ahora, finished_at=ahora, files_scanned=100,
                          details={"kind": "audit", "disparador": "automatico"}),
            ])
            await s.commit()
        async with fabrica() as s:
            ultima = await ultima_ejecucion_importador(s)
        assert ultima is not None and ultima.files_scanned == 7
        assert ultima.disparador == "manual" and ultima.reappeared_count == 1

    async def test_ultima_ejecucion_antigua_no_inventa_disparador(self, fabrica):
        ahora = datetime.now(UTC)
        async with fabrica() as s:
            s.add(ImportRun(started_at=ahora, finished_at=ahora, files_scanned=3,
                            details={"imported": []}))
            await s.commit()
        async with fabrica() as s:
            ultima = await ultima_ejecucion_importador(s)
        assert ultima is not None and ultima.disparador is None

    async def test_ultima_ejecucion_por_run_id(self, fabrica):
        ahora = datetime.now(UTC)
        async with fabrica() as s:
            viejo = ImportRun(started_at=ahora, finished_at=ahora, files_scanned=1,
                              details={"disparador": "automatico"})
            nuevo = ImportRun(started_at=ahora, finished_at=ahora, files_scanned=2,
                              details={"disparador": "manual"})
            s.add_all([viejo, nuevo])
            await s.commit()
            viejo_id, nuevo_id = str(viejo.id), str(nuevo.id)
        async with fabrica() as s:
            assert (await ultima_ejecucion_importador(s, viejo_id)).files_scanned == 1
            assert (await ultima_ejecucion_importador(s, nuevo_id)).files_scanned == 2


@pytest.fixture
def montaje(tmp_path, monkeypatch):
    library = tmp_path / "lib"
    library.mkdir()
    descargas = tmp_path / "descargas"
    descargas.mkdir()
    ajustes = type("A", (), {})()
    ajustes.library_path = library
    ajustes.transmission_download_dir = str(tmp_path / "transmission")
    ajustes.amule_incoming_dir = str(tmp_path / "amule")
    ajustes.downloads_path = descargas
    monkeypatch.setattr("zascarr.services.importer.get_settings", lambda: ajustes)
    return ajustes


def _fila(path: Path, *, missing=False) -> File:
    return File(file_path=str(path), file_name=path.name, file_format=FileFormat.CBZ,
                file_size_bytes=1, sha256_hash="a" * 64, is_missing=missing,
                metadata_={})


def _cbz(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("001.jpg", b"x" * 100)


async def _manual(fabrica):
    assert servicio.iniciar_manual(fabrica) is True
    await asyncio.wait_for(servicio._tarea, 30)


class TestCicloReal:

    async def test_ciclo_sin_cambios_no_escribe_catalogo_y_guarda_disparador(self, fabrica, montaje):
        presente = montaje.library_path / "presente.cbz"
        presente.write_bytes(b"x")
        async with fabrica() as s:
            s.add(_fila(presente))
            await s.commit()
        async with fabrica() as s:
            antes = (await s.execute(select(File.id, File.file_path, File.is_missing,
                                            File.missing_since, File.metadata_))).all()
            runs_antes = len((await s.execute(select(ImportRun))).all())

        await _manual(fabrica)

        assert servicio.estado_actual().fase is FaseCicloDisco.TERMINADO
        async with fabrica() as s:
            despues = (await s.execute(select(File.id, File.file_path, File.is_missing,
                                              File.missing_since, File.metadata_))).all()
            runs = (await s.execute(select(ImportRun).order_by(ImportRun.started_at.desc()))).scalars().all()
        assert despues == antes
        assert len(runs) == runs_antes + 1
        assert runs[0].details["disparador"] == "manual"
        assert "kind" not in runs[0].details
        assert "comprobacion_biblioteca" in runs[0].details
        assert str(servicio.estado_actual().run_id) == str(runs[0].id)

    async def test_ciclo_con_alta_y_ausencia_aplica_las_reglas(self, fabrica, montaje):
        ausente = montaje.library_path / "ausente.cbz"
        async with fabrica() as s:
            s.add(_fila(ausente))
            await s.commit()
        _cbz(montaje.downloads_path / "nuevo.cbz")

        await _manual(fabrica)

        async with fabrica() as s:
            run = (await s.execute(select(ImportRun).order_by(ImportRun.started_at.desc()).limit(1))).scalar_one()
            fila = (await s.execute(select(File).where(File.file_path == str(ausente)))).scalar_one()
        assert run.disappeared_count == 1 and fila.is_missing is True
        assert run.imported_count + run.unsorted_count >= 1

    async def test_automatico_guarda_disparador_automatico(self, fabrica, montaje):
        informe = await servicio.ejecutar_automatico(fabrica)
        assert informe is not None
        async with fabrica() as s:
            run = (await s.execute(select(ImportRun).order_by(ImportRun.started_at.desc()).limit(1))).scalar_one()
        assert run.details["disparador"] == "automatico"
        assert str(servicio.estado_actual().run_id) == str(run.id)

    async def test_sin_proveedores_ni_portadas(self, fabrica, montaje, monkeypatch):
        def prohibido(*_a, **_k):
            raise AssertionError("no debe consultarse una fuente externa")

        import zascarr.services.anilist as anilist
        import zascarr.services.comic_vine as comic_vine
        import zascarr.services.tebeosfera as tebeosfera
        import zascarr.utils.cover as cover
        monkeypatch.setattr(comic_vine, "ComicVineClient", prohibido)
        monkeypatch.setattr(anilist, "AniListClient", prohibido)
        monkeypatch.setattr(tebeosfera, "TebeosferaClient", prohibido)
        monkeypatch.setattr(cover, "extract_cover_thumbnail", prohibido)

        await _manual(fabrica)

        assert servicio.estado_actual().fase is FaseCicloDisco.TERMINADO

    async def test_el_aviso_usa_el_mismo_camino_y_solo_con_importados(self, fabrica, montaje, monkeypatch):
        class FakeNotifier:
            def __init__(self):
                self.llamadas: list[list[str]] = []

            async def notify_imported(self, files):
                self.llamadas.append(list(files))

        notifier = FakeNotifier()
        monkeypatch.setattr(servicio, "Notifier", lambda: notifier)

        await _manual(fabrica)                     # sin archivos nuevos: no avisa
        assert notifier.llamadas == []

        async with fabrica() as s:
            s.add(Series(title="Batman", tradition=ComicTradition.AMERICAN, start_year=2011))
            await s.commit()
        _cbz(montaje.downloads_path / "Batman 001.cbz")
        await _manual(fabrica)                     # archivo nuevo: un aviso
        assert len(notifier.llamadas) == 1

    async def test_no_lee_contenido_de_la_biblioteca(self, fabrica, montaje, monkeypatch):
        presente = montaje.library_path / "no-leer.cbz"
        presente.write_bytes(b"x")
        async with fabrica() as s:
            s.add(_fila(presente))
            await s.commit()

        def prohibido(*_a, **_k):
            raise AssertionError("la comprobación no debe abrir contenido de la biblioteca")

        monkeypatch.setattr(Path, "read_bytes", prohibido)
        await _manual(fabrica)
        assert servicio.estado_actual().fase is FaseCicloDisco.TERMINADO
