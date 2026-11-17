"""T-62: el backoff de envío filtra en Postgres real, no solo en el SQL.

Sin BD se comprueba el `WHERE` que genera `process_wishlist`; aquí se
comprueba **lo que queda en la tabla**: un deseo con `next_retry_at` futuro
no entra en el ciclo, uno ya vencido sí, y un fallo de envío persiste
`retry_count`/`next_retry_at` hasta que un envío correcto los limpia.

Se salta sin `TEST_DATABASE_URL`, mismo patrón que `test_politica_d8_pg.py`.
"""
from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    ComicTradition,
    LegalAcknowledgment,
    Series,
    Wishlist,
    WishlistStatus,
)
from zascarr.services.legal import current_legal_version
from zascarr.services.orchestrator import Orchestrator
from zascarr.services.prowlarr import SearchResult

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def test_process_wishlist_respeta_el_backoff():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        asyncio.run(_caso_eligibilidad(url))


async def _caso_eligibilidad(url: str) -> None:
    motor = create_async_engine(url_asyncpg(url))
    sesion = async_sessionmaker(motor, expire_on_commit=False)
    try:
        async with sesion() as db:
            db.add(LegalAcknowledgment(id=uuid4(), legal_version=current_legal_version()))
            serie = Series(id=uuid4(), title="Serie backoff",
                           tradition=ComicTradition.AMERICAN)
            db.add(serie)
            await db.flush()
            ahora = datetime.now(UTC)
            # Backoff futuro: fuera del ciclo aunque el cooldown ya pasó.
            con_backoff = Wishlist(
                id=uuid4(), series_id=serie.id, status=WishlistStatus.FAILED,
                last_searched_at=ahora - timedelta(hours=7),
                retry_count=1, next_retry_at=ahora + timedelta(minutes=10))
            # Backoff vencido con `last_searched_at` dentro del cooldown global:
            # el backoff manda y el deseo vuelve al ciclo.
            vencido = Wishlist(
                id=uuid4(), series_id=serie.id, status=WishlistStatus.FAILED,
                last_searched_at=ahora - timedelta(minutes=1),
                retry_count=1, next_retry_at=ahora - timedelta(minutes=1))
            # Sin backoff, con el cooldown global reciente: sigue excluido.
            en_cooldown = Wishlist(
                id=uuid4(), series_id=serie.id, status=WishlistStatus.FAILED,
                last_searched_at=ahora - timedelta(minutes=1))
            # Sin backoff y con el cooldown cumplido: elegible como siempre.
            normal = Wishlist(
                id=uuid4(), series_id=serie.id, status=WishlistStatus.FAILED,
                last_searched_at=ahora - timedelta(hours=7))
            db.add_all([con_backoff, vencido, en_cooldown, normal])
            await db.commit()

            orch = Orchestrator(db=db)
            vistos: list = []

            async def _procesar(item):
                vistos.append(item.id)
                return False

            orch._process_item = _procesar
            await orch.process_wishlist()

            assert set(vistos) == {vencido.id, normal.id}
            assert len(vistos) == 2
    finally:
        await motor.dispose()


def test_un_fallo_de_envio_persiste_el_backoff():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        asyncio.run(_caso_persistencia(url))


async def _caso_persistencia(url: str) -> None:
    motor = create_async_engine(url_asyncpg(url))
    sesion = async_sessionmaker(motor, expire_on_commit=False)
    try:
        async with sesion() as db:
            db.add(LegalAcknowledgment(id=uuid4(), legal_version=current_legal_version()))
            serie = Series(id=uuid4(), title="Serie backoff",
                           tradition=ComicTradition.AMERICAN)
            db.add(serie)
            await db.flush()
            item = Wishlist(id=uuid4(), series_id=serie.id, status=WishlistStatus.WANTED)
            db.add(item)
            await db.commit()

            orch = Orchestrator(db=db)

            async def _rankear(_item):
                return [SearchResult(title="Serie backoff #1.cbz", indexer="test",
                                     download_url="magnet:?xt=urn:btih:abc",
                                     size_bytes=1024, seeders=10, category="comics")]

            async def _send(_backend, _result):
                return None

            orch._search_and_rank = _rankear
            orch._send = _send

            assert await orch._process_item(item) is False
            await db.commit()
            item_id = item.id

        async with sesion() as db:
            guardado = (await db.execute(
                select(Wishlist).where(Wishlist.id == item_id))).scalar_one()
            assert guardado.status == WishlistStatus.FAILED
            assert guardado.retry_count == 1
            assert guardado.next_retry_at is not None
    finally:
        await motor.dispose()
