"""
tests/test_importer.py

Suite del ImportReport (B1/B3): informe legible de cada ciclo de
Importer.scan_and_import() — quién se importó, quién se descartó por
duplicado y de qué, quién quedó sin clasificar y por qué.
"""
from __future__ import annotations

import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from zascarr.core.matcher import SeriesHit
from zascarr.models import ComicTradition, File, ImportRun, Series
from zascarr.services.importer import Importer, ImportReport, build_library_path, serialize_candidates


def make_cbz(path: Path) -> None:
    """CBZ mínimo pero válido (zip vacío): suficiente para que triage()
    lo hashee y lo abra sin marcarlo como ilegible."""
    with zipfile.ZipFile(path, "w"):
        pass


class TestSerializeCandidates:
    """B12: candidatos de MatchResult a JSON plano para metadata_, la
    bandeja de Pendientes los lee para sugerir "¿es esta serie?"."""

    def test_ordena_por_score_descendente(self):
        peor = SeriesHit(series_id=uuid4(), title="Thorgal", start_year=None, score=0.42)
        mejor = SeriesHit(series_id=uuid4(), title="La Patrulla-X", start_year=1985, score=0.62)

        resultado = serialize_candidates([peor, mejor])

        assert [c["title"] for c in resultado] == ["La Patrulla-X", "Thorgal"]

    def test_serializa_campos_esperados(self):
        sid = uuid4()
        hit = SeriesHit(series_id=sid, title="Batman", start_year=2011, score=0.62)

        resultado = serialize_candidates([hit])

        assert resultado == [{
            "series_id": str(sid), "title": "Batman", "start_year": 2011, "score": 0.62,
        }]

    def test_lista_vacia(self):
        assert serialize_candidates([]) == []


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


class TestScanDedupePorInodo:
    """Bug real: HOST_DOWNLOADS_DIR y HOST_AMULE_INCOMING_DIR pueden apuntar
    al mismo disco (caso normal cuando el usuario da una sola carpeta de
    descargas — ver bootstrap.sh), y entonces el contenedor monta ese mismo
    disco dos veces, en /media/downloads Y /media/incoming. El mismo archivo
    aparece con dos rutas DISTINTAS (sin symlink de por medio, como en un
    bind-mount de verdad) — deduplicar por ruta resuelta no lo detecta;
    hace falta el inodo."""

    @pytest.mark.asyncio
    async def test_mismo_inodo_en_dos_rutas_se_escanea_una_sola_vez(self, tmp_path, monkeypatch):
        descargas = tmp_path / "downloads"
        incoming = tmp_path / "amule"
        descargas.mkdir()
        incoming.mkdir()

        original = descargas / "Batman 001.cbz"
        make_cbz(original)
        # Hard link, no symlink: mismo inodo bajo dos rutas independientes,
        # igual que dos bind-mounts del mismo disco host.
        os.link(original, incoming / "Batman 001.cbz")

        monkeypatch.setattr(
            "zascarr.services.importer.get_settings",
            lambda: MagicMock(
                library_path=tmp_path / "library",
                transmission_download_dir=str(descargas),
                amule_incoming_dir=str(incoming),
                downloads_path=descargas,
            ),
        )

        importer = Importer(AsyncMock())

        vistos = []
        async def fake_import_file(path, rep, pista=None):
            vistos.append(path)
        importer._import_file = fake_import_file

        report = await importer.scan_and_import()

        assert len(vistos) == 1
        assert report.files_scanned == 1


class TestScanPasaLaPistaDeCohorte:
    """Integración con core/cohort.py: scan_and_import calcula las
    pistas UNA VEZ sobre la foto fija del ciclo y se las pasa a
    _import_file — ver test_cohort.py para la lógica de detección en
    sí, aislada del filesystem."""

    @pytest.mark.asyncio
    async def test_pista_calculada_y_pasada_al_archivo_correcto(self, tmp_path, monkeypatch):
        descargas = tmp_path / "downloads"
        descargas.mkdir()
        for n in (42, 65, 74):
            make_cbz(descargas / f"{n} Dreadstar (First Comics) USA.cbr")
        make_cbz(descargas / "100 Balas - Integral 02.cbz")  # prefijo constante: sin pista

        monkeypatch.setattr(
            "zascarr.services.importer.get_settings",
            lambda: MagicMock(
                library_path=tmp_path / "library",
                transmission_download_dir=str(descargas),
                amule_incoming_dir=str(tmp_path / "no-existe"),
                downloads_path=tmp_path / "no-existe-tampoco",
            ),
        )

        importer = Importer(AsyncMock())
        recibidas: dict[str, object] = {}

        async def fake_import_file(path, rep, pista=None):
            recibidas[path.name] = pista
        importer._import_file = fake_import_file

        await importer.scan_and_import()

        assert recibidas["42 Dreadstar (First Comics) USA.cbr"] is not None
        assert recibidas["65 Dreadstar (First Comics) USA.cbr"].prefijo == "65"
        assert recibidas["100 Balas - Integral 02.cbz"] is None


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


class TestBuildLibraryPathSanitizado:
    """A3: un título con "/" o ".." no puede escapar de la biblioteca."""

    def test_titulo_con_barra_queda_dentro_de_la_biblioteca(self, tmp_path):
        library = tmp_path / "library"
        series = Series(
            id=uuid4(), title="Batman/Superman",
            tradition=ComicTradition.AMERICAN, start_year=2011,
        )

        dest = build_library_path(library, series, "1", ".cbz")

        assert dest.is_relative_to(library)
        assert dest.name == "Batman Superman #001.cbz"
        assert "Batman Superman (2011)" in str(dest)

    def test_titulo_punto_punto_no_escapa(self, tmp_path):
        library = tmp_path / "library"
        series = Series(id=uuid4(), title="..", tradition=ComicTradition.OTHER)

        dest = build_library_path(library, series, None, ".cbz")

        assert dest.is_relative_to(library)

    def test_numero_con_barra_no_crea_subcarpeta(self, tmp_path):
        library = tmp_path / "library"
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)

        dest = build_library_path(library, series, "1/2", ".cbz")

        assert dest.is_relative_to(library)
        assert "/" not in dest.name  # "1/2" ya no es un separador de ruta
