"""Notificador de importación (E4) — webhook de mejor esfuerzo.

Entrega de **mejor esfuerzo** (decisión explícita de la ficha): un fallo
(URL caída/lenta) se registra y **no** se reintenta; nunca bloquea ni
revierte la importación (se llama DESPUÉS del `commit`). Nunca se loguean
`webhook_url` ni `webhook_token`: pueden ser secretos.
"""
from __future__ import annotations

import httpx
import structlog

from zascarr.config import Settings, get_settings

logger = structlog.get_logger()

_MAX_LINEAS = 20


class Notifier:
    def __init__(self, settings: Settings | None = None,
                 client: httpx.AsyncClient | None = None):
        self._settings = settings or get_settings()
        # Para tests: un httpx.AsyncClient con MockTransport (receptor falso).
        self._client = client

    def _texto(self, files: list[str]) -> tuple[str, str]:
        n = len(files)
        plural = "" if n == 1 else "s"
        titulo = f"ZascArr: {n} tebeo{plural} importado{plural}"
        cuerpo = "\n".join(f"- {f}" for f in files[:_MAX_LINEAS])
        if n > _MAX_LINEAS:
            cuerpo += f"\n… y {n - _MAX_LINEAS} más"
        return titulo, cuerpo

    def _configurado(self) -> bool:
        """¿Hay lo mínimo para enviar? Telegram NO usa `webhook_url`: construye
        la ruta con el token del bot (`/bot<token>/sendMessage`), así que exige
        token + chat_id; el resto exigen URL."""
        s = self._settings
        if s.webhook_type == "telegram":
            return bool(s.webhook_token and s.webhook_chat_id)
        return bool(s.webhook_url)

    async def notify_imported(self, files: list[str]) -> None:
        """Avisa si hay archivos nuevos y el webhook está activo. Nunca
        propaga una excepción: es mejor esfuerzo tras el commit."""
        if not files or not self._settings.webhook_enabled:
            return
        if not self._configurado():
            logger.warning("notifier.misconfigured", type=self._settings.webhook_type)
            return
        titulo, cuerpo = self._texto(files)
        try:
            await self._post(titulo, cuerpo)
        except Exception:
            # Sin URL ni token en el log (secretos potenciales).
            logger.warning("notifier.send_failed", type=self._settings.webhook_type)

    async def _post(self, titulo: str, cuerpo: str) -> None:
        s = self._settings
        tipo = s.webhook_type
        url = s.webhook_url
        timeout = httpx.Timeout(s.webhook_timeout)
        headers: dict[str, str] = {}
        json_payload: dict[str, str] | None = None
        content: str | None = None

        if tipo == "gotify":
            url = f"{url.rstrip('/')}/message"
            # Gotify admite el token en cabecera; en la URL acabaría en sus
            # logs de acceso (o los de un proxy) aunque ZascArr no lo registre.
            headers["X-Gotify-Key"] = s.webhook_token
            json_payload = {"title": titulo, "message": cuerpo, "priority": 5}
        elif tipo == "ntfy":
            headers["Title"] = titulo
            if s.webhook_token:
                headers["Authorization"] = f"Bearer {s.webhook_token}"
            content = cuerpo
        elif tipo == "telegram":
            url = f"https://api.telegram.org/bot{s.webhook_token}/sendMessage"
            json_payload = {"chat_id": s.webhook_chat_id, "text": f"{titulo}\n{cuerpo}"}
        else:  # generic
            json_payload = {"title": titulo, "message": cuerpo}

        kwargs: dict = {"timeout": timeout, "headers": headers}
        if content is not None:
            kwargs["content"] = content
        else:
            kwargs["json"] = json_payload

        if self._client is not None:
            respuesta = await self._client.post(url, **kwargs)
        else:
            async with httpx.AsyncClient() as client:
                respuesta = await client.post(url, **kwargs)
        # Un 4xx/5xx NO es un envío correcto: que cuente como fallo (mejor
        # esfuerzo = se registra, no se reintenta, no revierte la importación).
        respuesta.raise_for_status()
