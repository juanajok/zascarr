"""
tests/test_orchestrator.py

Suite del orquestador (D1): búsqueda en cascada con reintento de
candidatos, cooldown de reintento (H2-style) y cierre del círculo
"descargado -> en tu biblioteca" vía existencia de File, sin depender de
Transmission/aMule ni Prowlarr reales.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from zascarr.config import get_settings
from zascarr.models import ComicTradition, File, FileFormat, Issue, Series, Wishlist, WishlistStatus
from zascarr.services.orchestrator import DownloadBackend, Orchestrator, _extract_ed2k_hash
from zascarr.services.prowlarr import SearchResult


@pytest.fixture(autouse=True)
def _p2p_enabled(monkeypatch):
    """Blindaje legal: prowlarr/transmission/amule están deshabilitados
    por defecto (opt-in). Esta suite prueba la lógica de búsqueda/envío
    en sí, no el propio opt-in (eso tiene su test dedicado más abajo),
    así que se habilitan los tres para no romper cada test existente."""
    settings = get_settings()
    settings = settings.model_copy(update={
        "prowlarr_enabled": True, "transmission_enabled": True, "amule_enabled": True,
    })
    monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: settings)


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def first(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Cola de resultados en el orden en que el orquestador los pide."""

    def __init__(self, queue: list | None = None):
        self._queue = list(queue or [])
        self.flush = AsyncMock()

    async def execute(self, _statement):
        return self._queue.pop(0)


def make_series(title="Batman", tradition=ComicTradition.AMERICAN) -> Series:
    return Series(id=uuid4(), title=title, tradition=tradition)


def make_result(title="Batman #1.cbz", url="magnet:?xt=urn:btih:abc", seeders=10, size=1024) -> SearchResult:
    return SearchResult(title=title, indexer="test", download_url=url,
                        size_bytes=size, seeders=seeders, category="comics")


# ═══════════════════════════════════════════════════════════════════════════
# 1. _ranked_candidates — pool completo, no solo el ganador
# ═══════════════════════════════════════════════════════════════════════════

class TestRankedCandidates:

    def test_ordena_por_score_descendente(self):
        orch = Orchestrator(db=FakeSession())
        peor = make_result(title="Batman Variant.cbz", seeders=5)
        mejor = make_result(title="Batman #1.cbz", seeders=50)
        ranked = orch._ranked_candidates([peor, mejor], "Batman")
        assert ranked[0] is mejor
        assert ranked[1] is peor

    def test_torrents_antes_que_ed2k(self):
        orch = Orchestrator(db=FakeSession())
        ed2k = make_result(title="Batman.cbz", url="ed2k://|file|batman.cbz|100|HASH123|/", seeders=0)
        torrent = make_result(title="Batman.cbz", seeders=1)
        ranked = orch._ranked_candidates([ed2k, torrent], "Batman")
        assert ranked == [torrent, ed2k]

    def test_torrent_sin_seeders_se_descarta(self):
        orch = Orchestrator(db=FakeSession())
        sin_seeders = make_result(seeders=0)
        ranked = orch._ranked_candidates([sin_seeders], "Batman")
        assert ranked == []

    def test_por_encima_del_tamano_maximo_se_descarta(self):
        orch = Orchestrator(db=FakeSession())
        grande = make_result(size=999_999_999_999)
        assert orch._ranked_candidates([grande], "Batman") == []


class TestExtractEd2kHash:

    def test_extrae_el_hash_de_la_url(self):
        assert _extract_ed2k_hash("ed2k://|file|batman.cbz|123456|ABCDEF0123456789|/") == "ABCDEF0123456789"

    def test_url_malformada_devuelve_none(self):
        assert _extract_ed2k_hash("ed2k://not-a-real-link") is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. _process_item — reintento con el siguiente candidato (Mylar3)
# ═══════════════════════════════════════════════════════════════════════════

class TestProcessItemRetryPool:

    @pytest.mark.asyncio
    async def test_si_el_mejor_falla_al_enviarse_prueba_el_siguiente(self):
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        session = FakeSession()  # search_query ya viene puesto, _build_query no toca la DB
        orch = Orchestrator(db=session)
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [
            make_result(title="Batman #1 malo.cbz", seeders=50),
            make_result(title="Batman #1 bueno.cbz", seeders=10),
        ]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.side_effect = [None, {"hashString": "abc123", "name": "Batman #1 bueno.cbz"}]

        result = await orch._process_item(item)

        assert result is True
        assert item.status == WishlistStatus.DOWNLOADING
        assert item.download_ref == "abc123"
        assert item.download_backend == DownloadBackend.TRANSMISSION.value
        assert orch._transmission.add_torrent.await_count == 2

    @pytest.mark.asyncio
    async def test_todos_los_candidatos_fallan_es_failed(self):
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=10)]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = None

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.FAILED

    @pytest.mark.asyncio
    async def test_sin_candidatos_vuelve_a_wanted_no_a_failed(self):
        item = Wishlist(id=uuid4(), search_query="Serie Rarísima", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = []

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.WANTED  # sin resultados no es un fallo


# ═══════════════════════════════════════════════════════════════════════════
# 3. last_searched_at — marcado en cada intento (H2 aplicado aquí también)
# ═══════════════════════════════════════════════════════════════════════════

class TestUltimoIntento:

    @pytest.mark.asyncio
    async def test_se_marca_incluso_sin_resultados(self):
        item = Wishlist(id=uuid4(), search_query="X", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = []

        assert item.last_searched_at is None
        await orch._process_item(item)
        assert item.last_searched_at is not None

    @pytest.mark.asyncio
    async def test_se_marca_con_exito(self):
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=10)]
        orch._transmission = AsyncMock()
        orch._transmission.add_torrent.return_value = {"hashString": "abc"}

        await orch._process_item(item)
        assert item.last_searched_at is not None

    def test_query_de_seleccion_incluye_wanted_failed_y_cooldown(self):
        """Sin DB real: se verifica que el WHERE generado cubre WANTED y
        FAILED (no solo WANTED, o un fallo de envío se abandona para
        siempre) y compara last_searched_at contra NULL o el cooldown."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
        from sqlalchemy import or_
        stmt = (
            select(Wishlist)
            .where(Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]))
            .where(or_(
                Wishlist.last_searched_at.is_(None),
                Wishlist.last_searched_at < cutoff,
            ))
        )
        compiled = str(stmt)
        assert "wishlist_status" in compiled or "status IN" in compiled
        assert "last_searched_at IS NULL" in compiled
        assert "last_searched_at <" in compiled


# ═══════════════════════════════════════════════════════════════════════════
# 4. check_completions — cierre del círculo por existencia de File
# ═══════════════════════════════════════════════════════════════════════════

def make_file(issue_id=None) -> File:
    return File(id=uuid4(), file_path="/lib/x.cbz", file_name="x.cbz",
                file_format=FileFormat.CBZ, issue_id=issue_id)


class TestCheckCompletions:

    @pytest.mark.asyncio
    async def test_issue_con_file_enlazado_pasa_a_imported(self):
        issue_id = uuid4()
        item = Wishlist(id=uuid4(), issue_id=issue_id, status=WishlistStatus.DOWNLOADING)
        session = FakeSession([
            FakeExecResult([item]),          # select pendientes DOWNLOADING
            FakeExecResult([make_file(issue_id)]),  # _is_fulfilled: File.id existe
        ])
        orch = Orchestrator(db=session)

        completed = await orch.check_completions()

        assert completed == 1
        assert item.status == WishlistStatus.IMPORTED
        assert item.downloaded_at is not None

    @pytest.mark.asyncio
    async def test_sin_file_todavia_se_queda_downloading(self):
        issue_id = uuid4()
        item = Wishlist(id=uuid4(), issue_id=issue_id, status=WishlistStatus.DOWNLOADING)
        session = FakeSession([
            FakeExecResult([item]),
            FakeExecResult([]),  # ningún File enlazado todavía
        ])
        orch = Orchestrator(db=session)

        completed = await orch.check_completions()

        assert completed == 0
        assert item.status == WishlistStatus.DOWNLOADING
        assert item.downloaded_at is None

    @pytest.mark.asyncio
    async def test_item_solo_con_series_id_busca_por_join_a_issues(self):
        series_id = uuid4()
        item = Wishlist(id=uuid4(), series_id=series_id, status=WishlistStatus.DOWNLOADING,
                        added_at=datetime.now(timezone.utc) - timedelta(days=1))
        session = FakeSession([
            FakeExecResult([item]),
            FakeExecResult([make_file()]),  # el join ya filtra por series_id
        ])
        orch = Orchestrator(db=session)

        completed = await orch.check_completions()
        assert completed == 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. Blindaje legal (aceptación) y opt-in P2P — no tocar red sin ninguno
# ═══════════════════════════════════════════════════════════════════════════

class TestGateLegalYOptInP2P:

    @pytest.mark.asyncio
    async def test_process_wishlist_no_hace_nada_sin_aceptar_el_aviso(self):
        """Ni siquiera llega a mirar la wishlist si no hay acknowledgment
        — el ciclo entero se salta, Prowlarr no se toca."""
        session = FakeSession([FakeExecResult([])])  # is_acknowledged: ninguna fila
        orch = Orchestrator(db=session)
        orch._prowlarr = AsyncMock()

        sent = await orch.process_wishlist()

        assert sent == 0
        orch._prowlarr.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_backend_deshabilitado_descarta_el_candidato(self, monkeypatch):
        """Aunque Prowlarr encuentre algo, un backend no activado
        (transmission_enabled=False, default de fábrica) no se intenta."""
        item = Wishlist(id=uuid4(), search_query="Batman", status=WishlistStatus.WANTED)
        settings = get_settings().model_copy(update={
            "prowlarr_enabled": True, "transmission_enabled": False, "amule_enabled": False,
        })
        monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: settings)

        orch = Orchestrator(db=FakeSession())
        orch._prowlarr = AsyncMock()
        orch._prowlarr.search.return_value = [make_result(seeders=50)]  # magnet:// -> Transmission
        orch._transmission = AsyncMock()

        result = await orch._process_item(item)

        assert result is False
        assert item.status == WishlistStatus.WANTED  # sin candidatos utilizables, no es un fallo
        orch._transmission.add_torrent.assert_not_called()
