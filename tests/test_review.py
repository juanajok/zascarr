"""
tests/test_review.py

Suite de ReviewService (B2): asignar un archivo de _Unsorted a una serie
(creando el Issue si hace falta) o descartarlo. Sigue el patrón ya usado
en test_importer.py: sesión mínima + archivos reales en tmp_path que se
mueven de verdad, no una simulación del movimiento.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from zascarr.models import ComicTradition, File, FileFormat, Issue, IssueFormat, LocalAlias, MetadataSource, Series
from zascarr.services.review import ReviewService


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """get() resuelve por (Modelo, id) desde un dict; execute() consume
    una cola en el orden en que assign_to_series/search_series la piden."""

    def __init__(self, get_map=None, exec_queue=None):
        self._get_map = get_map or {}
        self._exec_queue = list(exec_queue or [])
        self.added: list = []
        self.flush = AsyncMock()

    async def get(self, model, id_):
        return self._get_map.get((model, id_))

    async def execute(self, _statement):
        return self._exec_queue.pop(0)

    def add(self, obj):
        self.added.append(obj)


def make_series(title="Batman", tradition=ComicTradition.AMERICAN, start_year=None):
    return Series(id=uuid4(), title=title, tradition=tradition, start_year=start_year)


def make_file(path: Path, issue_id=None, review_dismissed=False):
    return File(id=uuid4(), file_path=str(path), file_name=path.name,
                file_format=FileFormat.CBZ, issue_id=issue_id,
                review_dismissed=review_dismissed)


class TestAssignToSeries:

    @pytest.mark.asyncio
    async def test_crea_issue_nuevo_si_no_existe(self, tmp_path):
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "batman misterioso.cbz"
        orig.write_bytes(b"contenido")

        series = make_series("Batman", start_year=2011)
        file = make_file(orig)

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series.id): series},
            exec_queue=[
                FakeExecResult([]),  # sin issue existente para ese número
                FakeExecResult([]),  # B13: sin alias previo para ese patrón
            ],
        )
        service = ReviewService(db=session)
        service._library = library  # evita depender de settings/disco reales

        result = await service.assign_to_series(file.id, series.id, "12")

        assert result.metadata_source == MetadataSource.MANUAL.value
        issues_created = [o for o in session.added if isinstance(o, Issue)]
        assert len(issues_created) == 1
        assert issues_created[0].issue_number == "12"
        # H3 (peer review v2): el Issue creado al vuelo ya NO se marca
        # metadata_source='manual' (eso bloquearía sinopsis/portada/créditos
        # para el enricher); se protege solo la asignación vía locked_fields.
        assert issues_created[0].metadata_source is None
        assert issues_created[0].locked_fields == ["series_id", "issue_number"]
        assert not orig.exists()  # se movió de verdad
        assert Path(result.file_path).exists()
        assert "Batman #012" in result.file_name
        assert "Batman (2011)" in result.file_path
        # B15: sin marcador de edición en el nombre, el Issue nuevo es una
        # grapa estándar — nunca se asume otra cosa por defecto.
        assert issues_created[0].format == IssueFormat.SINGLE_ISSUE

    @pytest.mark.asyncio
    async def test_issue_nuevo_de_un_omnigold_se_crea_como_omnibus(self, tmp_path):
        """B15 (2026-09-26): el número que Pendientes ofrece para un
        Omnigold/Integral no es una grapa suelta — el Issue creado debe
        llevar Issue.format=OMNIBUS, no el SINGLE_ISSUE por defecto, para
        que los huecos y la ficha de serie no lo cuenten como tal."""
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "la patrulla x omnigold 12.cbz"
        orig.write_bytes(b"x")

        series = make_series("La Patrulla-X", start_year=1985)
        file = make_file(orig)

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series.id): series},
            exec_queue=[FakeExecResult([]), FakeExecResult([])],
        )
        service = ReviewService(db=session)
        service._library = library

        await service.assign_to_series(file.id, series.id, "12")

        issue = next(o for o in session.added if isinstance(o, Issue))
        assert issue.format == IssueFormat.OMNIBUS

    @pytest.mark.asyncio
    async def test_issue_nuevo_de_un_tomo_se_crea_como_trade_paperback(self, tmp_path):
        """B15: mismo mecanismo que el Omnigold, pero para Tomo/Vol sueltos
        (manga/BD por tomos) — Issue.format=TRADE_PAPERBACK."""
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "Astro Boy Tomo 5.cbz"
        orig.write_bytes(b"x")

        series = make_series("Astro Boy")
        file = make_file(orig)

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series.id): series},
            exec_queue=[FakeExecResult([]), FakeExecResult([])],
        )
        service = ReviewService(db=session)
        service._library = library

        await service.assign_to_series(file.id, series.id, "5")

        issue = next(o for o in session.added if isinstance(o, Issue))
        assert issue.format == IssueFormat.TRADE_PAPERBACK

    @pytest.mark.asyncio
    async def test_issue_existente_no_toca_el_format(self, tmp_path):
        """Si el Issue ya existe (número reutilizado), assign_to_series no
        debe tocar su format — solo se decide al CREAR uno nuevo."""
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "la patrulla x omnigold 12.cbz"
        orig.write_bytes(b"x")

        series = make_series("La Patrulla-X")
        existing_issue = Issue(id=uuid4(), series_id=series.id, issue_number="12",
                                format=IssueFormat.SINGLE_ISSUE)
        file = make_file(orig)

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series.id): series},
            exec_queue=[FakeExecResult([existing_issue]), FakeExecResult([])],
        )
        service = ReviewService(db=session)
        service._library = library

        await service.assign_to_series(file.id, series.id, "12")

        assert existing_issue.format == IssueFormat.SINGLE_ISSUE

    @pytest.mark.asyncio
    async def test_reutiliza_issue_existente_sin_duplicar(self, tmp_path):
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "batman.cbz"
        orig.write_bytes(b"x")

        series = make_series("Batman")
        existing_issue = Issue(id=uuid4(), series_id=series.id, issue_number="12")
        file = make_file(orig)

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series.id): series},
            exec_queue=[
                FakeExecResult([existing_issue]),
                FakeExecResult([]),  # B13: sin alias previo para ese patrón
            ],
        )
        service = ReviewService(db=session)
        service._library = library

        result = await service.assign_to_series(file.id, series.id, "12")

        assert result.issue_id == existing_issue.id
        assert not any(isinstance(o, Issue) for o in session.added)

    @pytest.mark.asyncio
    async def test_numero_vacio_lanza_error_sin_tocar_nada(self):
        service = ReviewService(db=FakeSession())
        with pytest.raises(ValueError, match="número"):
            await service.assign_to_series(uuid4(), uuid4(), "   ")

    @pytest.mark.asyncio
    async def test_archivo_inexistente_lanza_error(self):
        service = ReviewService(db=FakeSession())
        with pytest.raises(ValueError, match="Archivo"):
            await service.assign_to_series(uuid4(), uuid4(), "12")

    @pytest.mark.asyncio
    async def test_serie_inexistente_lanza_error(self, tmp_path):
        file = make_file(tmp_path / "y.cbz")
        session = FakeSession(get_map={(File, file.id): file})
        service = ReviewService(db=session)
        with pytest.raises(ValueError, match="Serie"):
            await service.assign_to_series(file.id, uuid4(), "12")


class TestAprendeAlias:
    """B13: cada asignación manual desde Pendientes aprende un alias
    local (patrón de nombre → serie) para no volver a preguntar."""

    @pytest.mark.asyncio
    async def test_crea_alias_nuevo(self, tmp_path):
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "la patrulla x omnigold 12.cbz"
        orig.write_bytes(b"x")

        series = make_series("La Patrulla-X", start_year=1985)
        file = make_file(orig)

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series.id): series},
            exec_queue=[FakeExecResult([]), FakeExecResult([])],
        )
        service = ReviewService(db=session)
        service._library = library

        await service.assign_to_series(file.id, series.id, "12")

        alias = next(o for o in session.added if isinstance(o, LocalAlias))
        assert alias.pattern_norm == "patrulla x omnigold"
        assert alias.series_id == series.id

    @pytest.mark.asyncio
    async def test_alias_existente_se_actualiza_en_vez_de_duplicarse(self, tmp_path):
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "la patrulla x omnigold 12.cbz"
        orig.write_bytes(b"x")

        series_correcta = make_series("La Patrulla-X", start_year=1985)
        file = make_file(orig)
        alias_previo = LocalAlias(id=uuid4(), pattern_norm="patrulla x omnigold", series_id=uuid4())

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series_correcta.id): series_correcta},
            exec_queue=[FakeExecResult([]), FakeExecResult([alias_previo])],
        )
        service = ReviewService(db=session)
        service._library = library

        await service.assign_to_series(file.id, series_correcta.id, "12")

        assert not any(isinstance(o, LocalAlias) for o in session.added)  # no crea uno nuevo
        assert alias_previo.series_id == series_correcta.id  # corrige el existente

    @pytest.mark.asyncio
    async def test_sin_serie_detectable_en_el_nombre_no_aprende_nada(self, tmp_path):
        library = tmp_path / "library"
        unsorted = library / "_Unsorted"
        unsorted.mkdir(parents=True)
        orig = unsorted / "___.cbz"  # naming.py no extrae título de esto
        orig.write_bytes(b"x")

        series = make_series("Algo")
        file = make_file(orig)

        session = FakeSession(
            get_map={(File, file.id): file, (Series, series.id): series},
            exec_queue=[FakeExecResult([])],  # solo el lookup de Issue: sin segunda query
        )
        service = ReviewService(db=session)
        service._library = library

        await service.assign_to_series(file.id, series.id, "12")

        assert not any(isinstance(o, LocalAlias) for o in session.added)
        assert session._exec_queue == []  # no se llegó a consultar el alias


class TestDismiss:

    @pytest.mark.asyncio
    async def test_marca_review_dismissed(self, tmp_path):
        file = make_file(tmp_path / "y.cbz")
        session = FakeSession(get_map={(File, file.id): file})
        service = ReviewService(db=session)

        await service.dismiss(file.id)

        assert file.review_dismissed is True

    @pytest.mark.asyncio
    async def test_archivo_inexistente_lanza_error(self):
        service = ReviewService(db=FakeSession())
        with pytest.raises(ValueError):
            await service.dismiss(uuid4())


class TestSearchSeries:

    @pytest.mark.asyncio
    async def test_query_vacia_no_consulta_la_bd(self):
        session = FakeSession()
        service = ReviewService(db=session)

        result = await service.search_series("   ")

        assert result == []
        assert session._exec_queue == []  # nunca se llegó a ejecutar nada

    @pytest.mark.asyncio
    async def test_devuelve_resultados_de_la_busqueda(self):
        series = make_series("Sandman")
        session = FakeSession(exec_queue=[FakeExecResult([series])])
        service = ReviewService(db=session)

        result = await service.search_series("sand")

        assert result == [series]
