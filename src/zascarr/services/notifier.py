"""Notificador de importación (E4) — webhook de mejor esfuerzo.

Entrega de **mejor esfuerzo** (decisión explícita de la ficha): un fallo
(URL caída/lenta) se registra y **no** se reintenta; nunca bloquea ni revierte
la importación (se llama DESPUÉS del `commit`). Nunca se loguean `webhook_url`
ni `webhook_token`: pueden ser secretos.

`enviar()` **devuelve** un `ResultadoEnvio` (éxito o causa) para que la ruta de
prueba pueda enseñar el motivo; `notify_imported()` usa la MISMA función y solo
registra el resultado. La causa sale del **código HTTP** o de la **clase** de la
excepción — **nunca de `str(exc)`**, que puede llevar dentro la URL (con el
token del bot, en Telegram).
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import structlog

from zascarr.config import Settings, get_settings

logger = structlog.get_logger()

_MAX_LINEAS = 20
# Tipos que este módulo sabe construir. Un valor fuera de aquí NO se manda como
# «generic»: se registra y no se envía. Importa para un tipo guardado ANTES de
# este cambio: convertirlo en otra cosa en silencio es peor que no enviar.
TIPOS_CONOCIDOS = ("generic", "gotify", "ntfy", "telegram")


@dataclass(frozen=True)
class ResultadoEnvio:
    """Éxito o causa del fallo, ya saneada (sin URL ni token)."""

    ok: bool
    motivo: str | None = None


def url_valida(url: str) -> bool:
    """Solo `http`/`https` y con host: un `file://`, un `ftp://` o una URL sin
    host no son destinos de webhook."""
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    return partes.scheme in ("http", "https") and bool(partes.hostname)


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
        # Los NOMBRES solo van si se piden explícitamente: en un tema público de
        # ntfy.sh los lee cualquiera, y revelan qué se está descargando.
        if not self._settings.webhook_incluir_nombres:
            return titulo, "Abre ZascArr para ver el detalle."
        cuerpo = "\n".join(f"- {f}" for f in files[:_MAX_LINEAS])
        if n > _MAX_LINEAS:
            cuerpo += f"\n… y {n - _MAX_LINEAS} más"
        return titulo, cuerpo

    def _motivo_si_no_configurado(self) -> str | None:
        """None si hay lo mínimo para enviar; si no, el motivo (sin secretos)."""
        s = self._settings
        if s.webhook_type not in TIPOS_CONOCIDOS:
            return f"tipo de aviso desconocido: «{s.webhook_type}»"
        if s.webhook_type == "telegram":
            # Telegram NO usa `webhook_url`: construye la ruta con el token.
            if not (s.webhook_token and s.webhook_chat_id):
                return "faltan el token del bot o el chat ID"
            return None
        if not s.webhook_url:
            return "falta la URL"
        if not url_valida(s.webhook_url):
            return "la URL no es http(s) o no tiene host"
        return None

    async def enviar(self, titulo: str, cuerpo: str) -> ResultadoEnvio:
        """Envía y **devuelve** el resultado; nunca propaga la excepción.

        La causa que se devuelve y se registra es el código HTTP o la CLASE de la
        excepción. Nunca `str(exc)`: puede contener la URL (y con ella el token).
        """
        motivo = self._motivo_si_no_configurado()
        if motivo is not None:
            logger.warning("notifier.misconfigured", type=self._settings.webhook_type,
                           motivo=motivo)
            return ResultadoEnvio(ok=False, motivo=motivo)
        try:
            await self._post(titulo, cuerpo)
        except httpx.HTTPStatusError as exc:
            return ResultadoEnvio(ok=False, motivo=f"HTTP {exc.response.status_code}")
        except Exception as exc:          # noqa: BLE001 — mejor esfuerzo
            return ResultadoEnvio(ok=False, motivo=type(exc).__name__)
        return ResultadoEnvio(ok=True)

    async def notify_imported(self, files: list[str]) -> ResultadoEnvio:
        """Avisa si hay archivos nuevos y el webhook está activo. Nunca propaga:
        es mejor esfuerzo tras el commit."""
        if not files or not self._settings.webhook_enabled:
            return ResultadoEnvio(ok=False, motivo="avisos apagados o sin ficheros")
        titulo, cuerpo = self._texto(files)
        resultado = await self.enviar(titulo, cuerpo)
        if resultado.ok:
            logger.info("notifier.sent", type=self._settings.webhook_type)
        else:
            # Sin URL ni token en el log (secretos potenciales).
            logger.warning("notifier.send_failed", type=self._settings.webhook_type,
                           motivo=resultado.motivo)
        return resultado

    async def aviso_de_prueba(self) -> ResultadoEnvio:
        """Manda un aviso de prueba con la MISMA función que el real, para que el
        botón de Ajustes pruebe exactamente el camino de producción."""
        return await self.enviar(
            "ZascArr: aviso de prueba",
            "Si lees esto, los avisos de importación están bien configurados.",
        )

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
