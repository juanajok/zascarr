"""#993: aviso de números nuevos, una vez por pasada y sin nombres por defecto."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from zascarr.services.notifier import Notifier


def _notifier(nombres: bool) -> Notifier:
    ajustes = SimpleNamespace(
        webhook_enabled=True, webhook_type="generic", webhook_url="https://aviso.example/hook",
        webhook_token="", webhook_chat_id="", webhook_timeout=5,
        webhook_incluir_nombres=nombres,
    )
    n = Notifier(settings=ajustes)
    n._post = AsyncMock()
    return n


async def test_aviso_con_nombres():
    n = _notifier(True)
    r = await n.notify_novedades([("Batman", 12), ("Batman", 13)])
    assert r.ok
    titulo, cuerpo = n._post.await_args.args
    assert "2 números nuevos" in titulo
    assert "- Batman #12" in cuerpo and "- Batman #13" in cuerpo


async def test_aviso_sin_nombres_por_defecto():
    n = _notifier(False)
    await n.notify_novedades([("Batman", 12)])
    _, cuerpo = n._post.await_args.args
    assert "Batman" not in cuerpo
    assert "Abre ZascArr" in cuerpo


async def test_webhook_apagado_no_hace_red():
    n = _notifier(True)
    n._settings.webhook_enabled = False
    r = await n.notify_novedades([("Batman", 12)])
    assert not r.ok
    n._post.assert_not_awaited()
