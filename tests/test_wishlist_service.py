"""
tests/test_wishlist_service.py

Suite de WishlistService (D1): alta/baja/búsqueda/reintento manual.
Fuente única de verdad tanto para la API JSON como para la UI HTMX —
sin esto la validación de "al menos un ID" y el whitelisting de campos
vivirían duplicados (o ausentes) en dos routers distintos.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from zascarr.models import ComicTradition, Series, Wishlist, WishlistStatus
from zascarr.services.wishlist import WishlistService


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


class FakeSession:
    def __init__(self, get_map=None, exec_queue=None):
        self._get_map = get_map or {}
        self._exec_queue = list(exec_queue or [])
        self.flush = AsyncMock()
        self.deleted: list = []
        self.added: list = []

    async def get(self, model, id_):
        return self._get_map.get((model, id_))

    async def execute(self, _statement):
        return self._exec_queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)


class TestAdd:

    @pytest.mark.asyncio
    async def test_sin_series_id_ni_issue_id_lanza_error(self):
        service = WishlistService(db=FakeSession())
        with pytest.raises(ValueError, match="series_id o issue_id"):
            await service.add()

    @pytest.mark.asyncio
    async def test_con_series_id_crea_el_item(self):
        series_id = uuid4()
        session = FakeSession()
        service = WishlistService(db=session)

        item = await service.add(series_id=series_id, priority=1)

        assert item.series_id == series_id
        assert item.priority == 1
        assert session.added == [item]

    @pytest.mark.asyncio
    async def test_con_issue_id_crea_el_item(self):
        issue_id = uuid4()
        service = WishlistService(db=FakeSession())
        item = await service.add(issue_id=issue_id)
        assert item.issue_id == issue_id


class TestRemove:

    @pytest.mark.asyncio
    async def test_elimina_el_item_existente(self):
        item = Wishlist(id=uuid4())
        session = FakeSession(get_map={(Wishlist, item.id): item})
        service = WishlistService(db=session)

        await service.remove(item.id)

        assert session.deleted == [item]

    @pytest.mark.asyncio
    async def test_item_inexistente_lanza_error(self):
        service = WishlistService(db=FakeSession())
        with pytest.raises(ValueError, match="no encontrado"):
            await service.remove(uuid4())


class TestRetry:

    @pytest.mark.asyncio
    async def test_reintentar_resetea_estado_y_cooldown(self):
        from datetime import datetime, timezone
        item = Wishlist(id=uuid4(), status=WishlistStatus.FAILED,
                        last_searched_at=datetime.now(timezone.utc))
        session = FakeSession(get_map={(Wishlist, item.id): item})
        service = WishlistService(db=session)

        result = await service.retry(item.id)

        assert result.status == WishlistStatus.WANTED
        assert result.last_searched_at is None

    @pytest.mark.asyncio
    async def test_item_inexistente_lanza_error(self):
        service = WishlistService(db=FakeSession())
        with pytest.raises(ValueError, match="no encontrado"):
            await service.retry(uuid4())


class TestSearchSeries:

    @pytest.mark.asyncio
    async def test_query_vacia_no_consulta_la_bd(self):
        session = FakeSession()
        service = WishlistService(db=session)

        result = await service.search_series("   ")

        assert result == []
        assert session._exec_queue == []

    @pytest.mark.asyncio
    async def test_devuelve_resultados_de_la_busqueda(self):
        series = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
        session = FakeSession(exec_queue=[FakeExecResult([series])])
        service = WishlistService(db=session)

        result = await service.search_series("sand")

        assert result == [series]
