"""E4 — notificador de importación (webhook de mejor esfuerzo).

Dos contratos:
  - El aviso va DESPUÉS del commit y solo con archivos nuevos (`_ejecutar_ciclo_y_avisar`).
  - El webhook es mejor esfuerzo: desactivado o caído, no envía / no propaga
    (probado con un receptor HTTP falso vía `httpx.MockTransport`).
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from structlog.testing import capture_logs

from zascarr.config import Settings
from zascarr.main import _ejecutar_ciclo_y_avisar
from zascarr.services.importer import ImportReport
from zascarr.services.notifier import Notifier


def _cfg(**kw) -> Settings:
    base = dict(
        webhook_enabled=True, webhook_type="generic",
        webhook_url="https://example.test/hook", webhook_token="",
        webhook_chat_id="", webhook_timeout=5.0,
    )
    base.update(kw)
    return Settings(**base)


def _receptor(status: int = 200, exc: Exception | None = None):
    """Receptor HTTP falso: registra cada petición y responde `status`."""
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if exc is not None:
            raise exc
        return httpx.Response(status)

    return httpx.MockTransport(handler), calls


class TestNotifier:

    @pytest.mark.asyncio
    async def test_desactivado_no_envia(self):
        transport, calls = _receptor()
        async with httpx.AsyncClient(transport=transport) as client:
            notifier = Notifier(settings=_cfg(webhook_enabled=False), client=client)
            await notifier.notify_imported(["a.cbz → A/a.cbz"])
        assert calls == []

    @pytest.mark.asyncio
    async def test_sin_url_no_envia(self):
        transport, calls = _receptor()
        async with httpx.AsyncClient(transport=transport) as client:
            notifier = Notifier(settings=_cfg(webhook_url=""), client=client)
            await notifier.notify_imported(["a.cbz → A/a.cbz"])
        assert calls == []

    @pytest.mark.asyncio
    async def test_generic_envia_json_con_titulo_y_mensaje(self):
        transport, calls = _receptor()
        async with httpx.AsyncClient(transport=transport) as client:
            await Notifier(settings=_cfg(), client=client).notify_imported(
                ["a.cbz → A/a.cbz"]
            )
        assert len(calls) == 1
        req = calls[0]
        assert str(req.url) == "https://example.test/hook"
        assert b"a.cbz" in req.content

    @pytest.mark.asyncio
    async def test_gotify_pone_token_en_query(self):
        transport, calls = _receptor()
        async with httpx.AsyncClient(transport=transport) as client:
            await Notifier(
                settings=_cfg(webhook_type="gotify", webhook_token="tok-secreto"),
                client=client,
            ).notify_imported(["a.cbz"])
        assert len(calls) == 1
        assert str(calls[0].url).startswith("https://example.test/hook/message")
        assert "token=tok-secreto" in str(calls[0].url)

    @pytest.mark.asyncio
    async def test_ntfy_usa_cabecera_title(self):
        transport, calls = _receptor()
        async with httpx.AsyncClient(transport=transport) as client:
            await Notifier(
                settings=_cfg(webhook_type="ntfy"), client=client
            ).notify_imported(["a.cbz"])
        assert calls[0].headers.get("title", "").startswith("ZascArr")

    @pytest.mark.asyncio
    async def test_telegram_usa_bot_y_chat_id(self):
        transport, calls = _receptor()
        async with httpx.AsyncClient(transport=transport) as client:
            await Notifier(
                settings=_cfg(webhook_type="telegram", webhook_token="BOT",
                              webhook_chat_id="123"),
                client=client,
            ).notify_imported(["a.cbz"])
        assert "/botBOT/sendMessage" in str(calls[0].url)
        assert b"123" in calls[0].content

    @pytest.mark.asyncio
    async def test_fallo_no_propaga(self):
        """URL caída/lenta: no debe re-lanzar (la importación ya está hecha)."""
        transport, _ = _receptor(exc=httpx.ConnectError("caída"))
        async with httpx.AsyncClient(transport=transport) as client:
            await Notifier(settings=_cfg(), client=client).notify_imported(["a.cbz"])

    @pytest.mark.asyncio
    async def test_fallo_no_loguea_el_token(self):
        transport, _ = _receptor(exc=httpx.ConnectError("caída"))
        async with httpx.AsyncClient(transport=transport) as client:
            with capture_logs() as logs:
                await Notifier(
                    settings=_cfg(webhook_token="tok-secreto"), client=client
                ).notify_imported(["a.cbz"])
        assert any(log.get("event") == "notifier.send_failed" for log in logs)
        assert "tok-secreto" not in str(logs)


class _FakeSession:
    def __init__(self, fail_commit: bool = False):
        self.committed = False
        self._fail = fail_commit

    async def commit(self):
        if self._fail:
            raise RuntimeError("commit falló")
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _factory(session):
    return lambda: session


def _importer(report):
    class _Imp:
        def __init__(self, _session):
            pass

        async def scan_and_import(self):
            return report

    return _Imp


def _report(imported=(), duplicates=()) -> ImportReport:
    return ImportReport(
        started_at=datetime.now(UTC), imported=list(imported),
        duplicates=list(duplicates),
    )


class TestCicloYAviso:

    @pytest.mark.asyncio
    async def test_aviso_tras_commit(self):
        session = _FakeSession()
        notifier = AsyncMock()
        await _ejecutar_ciclo_y_avisar(
            notifier, _factory(session), _importer(_report(imported=["a.cbz → A/a.cbz"])),
        )
        assert session.committed
        notifier.notify_imported.assert_awaited_once_with(["a.cbz → A/a.cbz"])

    @pytest.mark.asyncio
    async def test_rollback_no_avisa(self):
        session = _FakeSession(fail_commit=True)
        notifier = AsyncMock()
        with pytest.raises(RuntimeError):
            await _ejecutar_ciclo_y_avisar(
                notifier, _factory(session),
                _importer(_report(imported=["a.cbz → A/a.cbz"])),
            )
        notifier.notify_imported.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sin_importados_no_avisa(self):
        notifier = AsyncMock()
        await _ejecutar_ciclo_y_avisar(
            notifier, _factory(_FakeSession()),
            _importer(_report(duplicates=["b.cbz — duplicado de x, descartado"])),
        )
        notifier.notify_imported.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sin_duplicado_en_siguiente_ciclo(self):
        """Ciclo 1 importa (avisa); ciclo 2 reconoce el mismo archivo como
        duplicado (no avisa): un solo aviso, sin repetir."""
        notifier = AsyncMock()
        await _ejecutar_ciclo_y_avisar(
            notifier, _factory(_FakeSession()),
            _importer(_report(imported=["a.cbz → A/a.cbz"])),
        )
        await _ejecutar_ciclo_y_avisar(
            notifier, _factory(_FakeSession()),
            _importer(_report(duplicates=["a.cbz — duplicado de x, descartado"])),
        )
        assert notifier.notify_imported.await_count == 1
