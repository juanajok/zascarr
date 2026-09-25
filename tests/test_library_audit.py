"""
tests/test_library_audit.py

Suite de LibraryAudit (B16): informe de SOLO LECTURA de la biblioteca
física antes de adoptarla. Los casos están calcados de la biblioteca
real que motivó la historia (carpetas duplicadas enteras, la misma obra
en dos ediciones, ramas de carpetas vacías).

Ficheros de verdad en tmp_path, no mocks de filesystem: lo que se está
probando ES el comportamiento contra el disco (tamaños, inodos, hash).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from zascarr.models import ImportRun
from zascarr.services.library_audit import LibraryAudit


class FakeSession:
    def __init__(self):
        self.added: list = []
        self.flush = AsyncMock()

    def add(self, obj):
        self.added.append(obj)


def cbz(path: Path, contenido: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("001.jpg", contenido)


@pytest.fixture
def auditor(monkeypatch, tmp_path):
    def _hacer(library: Path) -> LibraryAudit:
        monkeypatch.setattr(
            "zascarr.services.library_audit.get_settings",
            lambda: MagicMock(library_path=library),
        )
        return LibraryAudit(db=FakeSession())
    return _hacer


class TestMismoContenido:

    @pytest.mark.asyncio
    async def test_mismo_archivo_en_dos_carpetas(self, auditor, tmp_path):
        cbz(tmp_path / "Comics/Superman (1987)/Superman Vol2 011.cbr", b"identico")
        cbz(tmp_path / "Comics/Superman Vol2 (Ed.Zinco)/Superman Vol2 011.cbr", b"identico")

        report = await auditor(tmp_path).run()

        assert len(report.mismo_contenido) == 1
        assert len(report.mismo_contenido[0].rutas) == 2
        assert report.bytes_recuperables > 0

    @pytest.mark.asyncio
    async def test_no_hashea_los_de_tamano_unico(self, auditor, tmp_path):
        """La optimización que hace viable auditar 2000 CBR en una Pi:
        dos ficheros de distinto tamaño no pueden ser idénticos, así que
        no se leen. Si esto se rompe, la auditoría pasa de minutos a
        horas sin que ningún test falle por lo demás."""
        cbz(tmp_path / "a/uno.cbr", b"contenido corto")
        cbz(tmp_path / "b/dos.cbr", b"contenido muchisimo mas largo que el otro")

        report = await auditor(tmp_path).run()

        assert report.files_scanned == 2
        assert report.files_hashed == 0
        assert report.mismo_contenido == []

    @pytest.mark.asyncio
    async def test_mismo_tamano_distinto_contenido_no_es_duplicado(self, auditor, tmp_path):
        cbz(tmp_path / "a/uno.cbr", b"AAAA")
        cbz(tmp_path / "b/dos.cbr", b"BBBB")

        report = await auditor(tmp_path).run()

        assert report.files_hashed == 2  # mismo tamaño: sí hubo que mirarlos
        assert report.mismo_contenido == []


class TestMismaObra:

    @pytest.mark.asyncio
    async def test_mismo_numero_en_dos_releases_se_reporta_aparte(self, auditor, tmp_path):
        """No es un duplicado a eliminar: puede ser deliberado (otra
        calidad, otro idioma). Por eso va en su propia categoría."""
        cbz(tmp_path / "a/Gideon Falls 01 - El Granero Negro [SC][CRG].cbr", b"release uno")
        cbz(tmp_path / "b/Gideon Falls 01 - El Granero Negro [DI][otro].cbr", b"release dos distinta")

        report = await auditor(tmp_path).run()

        assert report.mismo_contenido == []
        assert len(report.misma_obra) == 1
        assert len(report.misma_obra[0].rutas) == 2

    @pytest.mark.asyncio
    async def test_un_duplicado_exacto_no_se_reporta_dos_veces(self, auditor, tmp_path):
        cbz(tmp_path / "a/Gideon Falls 01 - El Granero Negro.cbr", b"identico")
        cbz(tmp_path / "b/Gideon Falls 01 - El Granero Negro.cbr", b"identico")

        report = await auditor(tmp_path).run()

        assert len(report.mismo_contenido) == 1
        assert report.misma_obra == []

    @pytest.mark.asyncio
    async def test_sin_numero_no_se_afirma_que_sean_la_misma_obra(self, auditor, tmp_path):
        """Dos obras unitarias de una carpeta de autor no son "la misma
        obra" por no tener número — afirmarlo sería inventar."""
        cbz(tmp_path / "autor/El Princesito.cbr", b"contenido a")
        cbz(tmp_path / "autor/Cancion de Navidad.cbr", b"contenido b")

        report = await auditor(tmp_path).run()

        assert report.misma_obra == []


class TestCarpetasRepetidas:

    @pytest.mark.asyncio
    async def test_carpeta_contenida_entera_en_otra(self, auditor, tmp_path):
        """Caso real: 'La Tempestad 01-06' sueltos y otra vez dentro de
        un subdirectorio [Completo]."""
        for n in (1, 2, 3):
            cbz(tmp_path / f"Liga/La Tempestad 0{n}.cbr", f"tempestad {n}".encode())
            cbz(tmp_path / f"Liga/[Completo]/La Tempestad 0{n}.cbr", f"tempestad {n}".encode())

        report = await auditor(tmp_path).run()

        assert len(report.carpetas_repetidas) == 1
        repetida = report.carpetas_repetidas[0]
        assert repetida.comunes == 3
        assert repetida.es_subconjunto

    @pytest.mark.asyncio
    async def test_carpetas_sin_solape_suficiente_no_se_reportan(self, auditor, tmp_path):
        cbz(tmp_path / "a/uno.cbr", b"1")
        cbz(tmp_path / "a/dos.cbr", b"2")
        cbz(tmp_path / "a/tres.cbr", b"3")
        cbz(tmp_path / "b/uno.cbr", b"1")
        cbz(tmp_path / "b/otro distinto.cbr", b"4")
        cbz(tmp_path / "b/otro mas.cbr", b"5")

        report = await auditor(tmp_path).run()

        assert report.carpetas_repetidas == []


class TestCarpetasVacias:

    @pytest.mark.asyncio
    async def test_reporta_solo_la_carpeta_mas_alta_de_la_rama(self, auditor, tmp_path):
        """Con Hellboy y sus 20 subcarpetas igual de vacías, informar de
        las 21 esconde el hallazgo en vez de enseñarlo."""
        (tmp_path / "Comics/Hellboy/9 La Isla").mkdir(parents=True)
        (tmp_path / "Comics/Hellboy/10 Makoma").mkdir(parents=True)
        cbz(tmp_path / "Comics/Batman/Batman 01.cbr", b"x")

        report = await auditor(tmp_path).run()

        rutas = [c.ruta for c in report.carpetas_vacias]
        assert rutas == [str(tmp_path / "Comics/Hellboy")]
        assert report.carpetas_vacias[0].subcarpetas == 2

    @pytest.mark.asyncio
    async def test_carpeta_contenedora_con_comics_dentro_no_es_vacia(self, auditor, tmp_path):
        cbz(tmp_path / "Comics/Batman/Batman 01.cbr", b"x")

        report = await auditor(tmp_path).run()

        assert report.carpetas_vacias == []


class TestInforme:

    @pytest.mark.asyncio
    async def test_biblioteca_limpia_no_tiene_hallazgos(self, auditor, tmp_path):
        cbz(tmp_path / "Comics/Batman/Batman 01.cbr", b"uno")
        cbz(tmp_path / "Comics/Batman/Batman 02.cbr", b"dos distinto")

        report = await auditor(tmp_path).run()

        assert not report.hay_hallazgos

    @pytest.mark.asyncio
    async def test_persiste_import_run_con_kind_audit(self, auditor, tmp_path):
        cbz(tmp_path / "Comics/Batman/Batman 01.cbr", b"x")
        audit = auditor(tmp_path)

        await audit.run()

        run = next(o for o in audit._db.added if isinstance(o, ImportRun))
        assert run.details["kind"] == "audit"

    @pytest.mark.asyncio
    async def test_no_toca_ni_un_archivo_del_disco(self, auditor, tmp_path):
        """La garantía central de B16: es solo lectura. Si esto falla,
        la historia entera pierde su razón de ser."""
        cbz(tmp_path / "a/Batman 01.cbr", b"identico")
        cbz(tmp_path / "b/Batman 01.cbr", b"identico")
        antes = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}

        report = await auditor(tmp_path).run()

        despues = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*") if p.is_file()}
        assert antes == despues
        assert report.mismo_contenido  # y aun así encontró el duplicado

    @pytest.mark.asyncio
    async def test_biblioteca_inexistente_no_revienta(self, auditor, tmp_path):
        report = await auditor(tmp_path / "no-existe").run()

        assert report.files_scanned == 0
        assert not report.hay_hallazgos
