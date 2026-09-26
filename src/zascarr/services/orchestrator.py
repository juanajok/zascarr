"""
Orquestador — motor de búsqueda en cascada.

Flujo: wishlist (wanted/failed, con cooldown) → Prowlarr → foro (plugin
genérico, desactivado por defecto) → Transmission/aMule → (import loop,
ya existente) → check_completions
cierra el círculo. Backend auto-detectado por tipo de URL:
  magnet:// o .torrent → Transmission
  ed2k://              → aMule

D1: dos reglas nuevas respecto al diseño original.
  - Si el mejor candidato falla al enviarse (backend caído, etc.), se
    prueba el siguiente del pool rankeado antes de rendirse — no una
    sola oportunidad (idea tomada de Mylar3 al comparar herramientas del
    mismo espacio).
  - Un item sin resultados o cuyo envío falla se reintenta solo tras
    `orchestrator_retry_cooldown_hours` (ver config.py), no en cada
    ciclo para siempre — mismo patrón que `enrichment_attempted_at` del
    enricher (H2 del peer review v2), aplicado aquí porque el bug es
    idéntico: sin cooldown, un item condenado quema Prowlarr/foro cada
    ciclo indefinidamente.

check_completions() cierra "descargado → en tu biblioteca" sin preguntarle
a Transmission/aMule si terminaron: ninguno de los dos da una forma fiable
de correlacionar un item de la wishlist con su descarga (Transmission sí
tiene hash, pero aMule no expone nombre/hash del completado hoy). En vez
de eso, se comprueba si ya existe un File enlazado al Issue/Series que el
item pedía — el import loop periódico ya existente es quien de verdad
clasifica el archivo, este método solo refleja ese hecho en el estado de
la wishlist.
"""
from datetime import UTC, datetime, timedelta
from enum import Enum

import structlog
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, Issue, Series, Wishlist, WishlistStatus
from zascarr.services.amule import AMuleClient
from zascarr.services.legal import is_acknowledged
from zascarr.services.prowlarr import ProwlarrClient, SearchResult
from zascarr.services.transmission import TransmissionClient
from zascarr.utils.naming import normalize_series_name

logger = structlog.get_logger()

COMIC_CATEGORIES = [7030, 7020]
MAX_SIZE_BYTES = 500 * 1024 * 1024

# D9: causas distinguibles de "por qué esta búsqueda no avanza", en
# español llano — nunca un detalle técnico (excepción, URL, cuerpo HTTP)
# que el coleccionista no pueda accionar. El aviso legal pendiente NO
# vive aquí: es un estado global (ver services/legal.py), lo muestra la
# UI de wishlist con un banner propio en vez de escribirse en cada fila.
MOTIVO_SIN_FUENTE = "Sin fuente de búsqueda activa — activa Prowlarr o el foro en Ajustes"
MOTIVO_FUENTE_INACCESIBLE = "La fuente de búsqueda no respondió a tiempo — se reintentará automáticamente"
MOTIVO_SIN_RESULTADOS = "No se encontró nada en las fuentes activas"
MOTIVO_CANDIDATO_RECHAZADO = "Se encontró algo, pero ningún cliente de descarga está activo — revisa Ajustes"
MOTIVO_CLIENTE_INACCESIBLE = "No se pudo enviar a ningún cliente de descarga — se reintentará más tarde"
MOTIVO_ERROR_INESPERADO = "Ocurrió un error inesperado al buscar — se reintentará automáticamente"


class DownloadBackend(str, Enum):
    TRANSMISSION = "transmission"
    AMULE        = "amule"


def _detect_backend(url: str) -> DownloadBackend:
    return DownloadBackend.AMULE if url.lower().startswith("ed2k://") else DownloadBackend.TRANSMISSION


class Orchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._prowlarr     = ProwlarrClient()
        self._transmission = TransmissionClient()
        self._amule        = AMuleClient()

    async def process_wishlist(self, limit: int = 10) -> int:
        # Blindaje legal: nada de esto se ejecuta hasta que se acepte el
        # aviso legal — ver services/legal.py. No es un middleware que
        # bloquee la app entera (biblioteca/pendientes siguen accesibles),
        # solo la parte que dispara red/descarga de verdad.
        if not await is_acknowledged(self.db):
            logger.info("orchestrator.cycle_skipped_no_legal_acknowledgment")
            return 0

        cooldown = timedelta(hours=get_settings().orchestrator_retry_cooldown_hours)
        cutoff = datetime.now(UTC) - cooldown
        items = list((await self.db.execute(
            select(Wishlist)
            .where(Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]))
            .where(or_(
                Wishlist.last_searched_at.is_(None),
                Wishlist.last_searched_at < cutoff,
            ))
            .order_by(Wishlist.priority.asc(), Wishlist.added_at.asc())
            .limit(limit)
        )).scalars().all())

        sent = 0
        for item in items:
            try:
                if await self._process_item(item):
                    sent += 1
            except Exception:
                logger.exception("orchestrator.item_failed", id=str(item.id))
                item.status = WishlistStatus.FAILED
                item.last_error = MOTIVO_ERROR_INESPERADO
                await self.db.flush()
        return sent

    async def _process_item(self, item: Wishlist) -> bool:
        candidates = await self._search_and_rank(item)
        if not candidates:
            return False  # ya se dejó constancia del motivo dentro de _search_and_rank

        # D1 (Mylar3): si el mejor candidato falla al enviarse, se prueba
        # el siguiente del pool rankeado antes de rendirse.
        for candidate in candidates:
            backend = _detect_backend(candidate.download_url)
            ref = await self._send(backend, candidate)
            if ref is not None:
                item.status = WishlistStatus.DOWNLOADING
                item.download_backend = backend.value
                item.download_ref = ref
                item.last_error = None  # D9: ya no aplica, se recuperó
                await self.db.flush()
                logger.info("orchestrator.download_started", title=candidate.title, backend=backend.value)
                return True

        # Hubo candidatos pero ninguno se pudo enviar (backend caído, etc.):
        # esto sí es un fallo real, distinto de "sin resultados todavía".
        item.status = WishlistStatus.FAILED
        item.last_error = MOTIVO_CLIENTE_INACCESIBLE
        await self.db.flush()
        return False

    async def _search_and_rank(self, item: Wishlist) -> list[SearchResult] | None:
        """Busca y deja el pool ya rankeado y filtrado por backends
        activos — compartido entre el ciclo automático (_process_item) y
        la búsqueda manual de D10 (preview_candidates), que se detiene
        aquí para que el coleccionista elija antes de enviar nada.

        None: no se pudo construir una búsqueda (nada que hacer todavía).
        []: se buscó de verdad y no quedó ningún candidato utilizable —
        el motivo (D9) ya queda escrito en item.last_error.
        """
        query = await self._build_query(item)
        if not query:
            return None

        item.status = WishlistStatus.SEARCHING
        # D1/H2: marca el intento ya aquí, con o sin resultado — es lo que
        # activa el cooldown de process_wishlist y evita quemar Prowlarr/
        # foro en cada ciclo con un item condenado.
        item.last_searched_at = datetime.now(UTC)
        await self.db.flush()

        settings = get_settings()

        # D9: si ninguna fuente está siquiera activa, ni lo intentamos —
        # se lo decimos al coleccionista en vez de dejarlo en "Buscando…"
        # para siempre sin explicación.
        foro_configurado = settings.forum_enabled and settings.forum_username and settings.forum_url
        if not settings.prowlarr_enabled and not foro_configurado:
            item.status = WishlistStatus.WANTED
            item.last_error = MOTIVO_SIN_FUENTE
            await self.db.flush()
            return []

        results: list[SearchResult] = []
        motivo_prowlarr: str | None = None
        if settings.prowlarr_enabled:
            try:
                results = await self._prowlarr.search(query, categories=COMIC_CATEGORIES)
            except Exception:
                logger.exception("orchestrator.prowlarr_search_failed", id=str(item.id))
                motivo_prowlarr = MOTIVO_FUENTE_INACCESIBLE

        candidates = self._ranked_candidates(results, query) if results else []

        if not candidates:
            forum_result = await self._forum_fallback(query)
            if forum_result:
                candidates = [forum_result]

        # Blindaje legal: opt-in por backend (deshabilitados por defecto,
        # igual que forum_enabled ya lo estaba) — un candidato de un
        # backend no activado ni se intenta enviar, ni se ofrece para
        # elegir a mano en D10.
        candidatos_crudos = candidates
        candidates = [c for c in candidates if self._backend_enabled(_detect_backend(c.download_url), settings)]

        if not candidates:
            item.status = WishlistStatus.WANTED  # nada encontrado todavía, no es un fallo
            # D9: distingue "no había nada" de "había algo pero el
            # backend correspondiente está apagado" — la acción del
            # coleccionista es distinta en cada caso.
            if candidatos_crudos:
                item.last_error = MOTIVO_CANDIDATO_RECHAZADO
            else:
                item.last_error = motivo_prowlarr or MOTIVO_SIN_RESULTADOS
            await self.db.flush()
            return []

        return candidates

    # ── D10: búsqueda manual con confirmación explícita ──────────────────────

    async def preview_candidates(self, item: Wishlist) -> list[SearchResult] | None:
        """"Buscar ahora": ejecuta la misma búsqueda que el ciclo
        automático pero se detiene ANTES de enviar nada — el coleccionista
        ve fuente/tamaño/formato de cada candidato y decide él (ver
        send_manual_candidate). Cancelar tras esto no deja nada a medias:
        no se ha tocado ni Transmission ni aMule todavía.

        Bug real encontrado en el propio desarrollo: _search_and_rank deja
        el item en SEARCHING mientras arma el pool, dando por hecho que
        quien lo llama sigue enseguida con el envío (como sí hace
        _process_item). Aquí NO se envía nada todavía — si se dejara en
        SEARCHING y el coleccionista cancelase, el item quedaría invisible
        para siempre al ciclo automático (que solo mira WANTED/FAILED).
        Por eso se revierte a WANTED en cuanto hay candidatos que mostrar.
        """
        candidates = await self._search_and_rank(item)
        if candidates:
            item.status = WishlistStatus.WANTED
            await self.db.flush()
        return candidates

    async def send_manual_candidate(self, item: Wishlist, candidate: SearchResult) -> bool:
        """El coleccionista ya vio el candidato en preview_candidates y
        decidió enviar justo ESTE — mismo envío que el ciclo automático
        (_send), pero sin volver a rankear ni a filtrar: la elección
        humana ya es la validación. El filtro de blindaje legal por
        backend SÍ se respeta igual que en automático (opt-in real, no
        solo de cara al ranking)."""
        settings = get_settings()
        backend = _detect_backend(candidate.download_url)
        if not self._backend_enabled(backend, settings):
            item.last_error = MOTIVO_CANDIDATO_RECHAZADO
            await self.db.flush()
            return False

        ref = await self._send(backend, candidate)
        if ref is None:
            item.status = WishlistStatus.FAILED
            item.last_error = MOTIVO_CLIENTE_INACCESIBLE
            await self.db.flush()
            return False

        item.status = WishlistStatus.DOWNLOADING
        item.download_backend = backend.value
        item.download_ref = ref
        item.last_error = None
        item.last_searched_at = datetime.now(UTC)
        await self.db.flush()
        logger.info("orchestrator.download_started", title=candidate.title, backend=backend.value, manual=True)
        return True

    async def _build_query(self, item: Wishlist) -> str | None:
        if item.search_query:
            return item.search_query
        if item.series_id:
            series = (await self.db.execute(select(Series).where(Series.id == item.series_id))).scalar_one_or_none()
            if not series:
                return None
            q = series.title
            if item.issue_id:
                issue = (await self.db.execute(select(Issue).where(Issue.id == item.issue_id))).scalar_one_or_none()
                if issue and issue.issue_number:
                    q += f" {issue.issue_number}"
            return q
        if item.issue_id:
            issue = (await self.db.execute(select(Issue).where(Issue.id == item.issue_id))).scalar_one_or_none()
            if issue:
                series = (await self.db.execute(select(Series).where(Series.id == issue.series_id))).scalar_one_or_none()
                if series:
                    return f"{series.title} {issue.issue_number}"
        return None

    async def _send(self, backend: DownloadBackend, result: SearchResult) -> str | None:
        """Devuelve un identificador de la descarga (hash de Transmission, o
        el hash ed2k ya presente en la propia URL) para observabilidad en
        Wishlist.download_ref — no participa en detectar si terminó (ver
        check_completions). None si el envío falló.

        Bug real encontrado verificando D10 en vivo: un Transmission/aMule
        inalcanzable (conexión rechazada, timeout) no devolvía None — la
        excepción de httpx se propagaba tal cual. En el ciclo automático
        eso lo capturaba el `except` genérico de process_wishlist (como
        "error inesperado", impreciso pero no roto); en la confirmación
        manual de D10, al no haber ningún `except` en el router, se colaba
        como un 500 crudo. Se captura aquí, en el único sitio que ambos
        caminos comparten, para que las dos rutas den MOTIVO_CLIENTE_
        INACCESIBLE en vez de un error sin explicar.
        """
        try:
            if backend == DownloadBackend.TRANSMISSION:
                added = await self._transmission.add_torrent(result.download_url)
                if not added:
                    return None
                return added.get("hashString") or added.get("name") or ""
            if backend == DownloadBackend.AMULE:
                if not await self._amule.login():
                    return None
                if not await self._amule.add_ed2k_link(result.download_url):
                    return None
                return _extract_ed2k_hash(result.download_url) or result.download_url
            return None
        except Exception:
            logger.exception("orchestrator.send_failed", backend=backend.value)
            return None

    @staticmethod
    def _backend_enabled(backend: DownloadBackend, settings) -> bool:
        if backend == DownloadBackend.TRANSMISSION:
            return settings.transmission_enabled
        if backend == DownloadBackend.AMULE:
            return settings.amule_enabled
        return False

    async def _forum_fallback(self, query: str) -> SearchResult | None:
        s = get_settings()
        # forum_url vacío por defecto a propósito (blindaje legal): es un
        # plugin IPB genérico, la URL la aporta el usuario, el proyecto no
        # incluye ni recomienda ningún foro concreto.
        if not s.forum_enabled or not s.forum_username or not s.forum_url:
            return None
        try:
            from zascarr.services.forum_scraper import ForumScraper
            scraper = ForumScraper(base_url=s.forum_url, rate_limit=s.forum_rate_limit)
            await scraper.login(s.forum_username, s.forum_password)
            for fr in await scraper.use_ipb_search(query):
                if fr.ed2k_links:
                    return SearchResult(fr.topic_title, "forum:crg", fr.ed2k_links[0], 0, 0, "comics")
                if fr.magnet_links:
                    return SearchResult(fr.topic_title, "forum:crg", fr.magnet_links[0], 0, 1, "comics")
        except Exception:
            logger.exception("orchestrator.forum_fallback_error")
        return None

    def _ranked_candidates(self, results: list[SearchResult], query: str) -> list[SearchResult]:
        """Todo el pool rankeado, no solo el ganador — D1 prueba el
        siguiente si el primero falla al enviarse, en vez de rendirse.
        Preferencia torrents-antes-que-ed2k se conserva concatenando los
        pools en ese orden, cada uno ordenado por score descendente."""
        norm = normalize_series_name(query)
        torrents, ed2k = [], []
        for r in results:
            if r.size_bytes > MAX_SIZE_BYTES:
                continue
            backend = _detect_backend(r.download_url)
            score = self._score(r, norm)
            if backend == DownloadBackend.TRANSMISSION:
                if r.seeders >= 1:
                    torrents.append((score, r))
            else:
                ed2k.append((score, r))
        torrents.sort(key=lambda x: x[0], reverse=True)
        ed2k.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in torrents] + [r for _, r in ed2k]

    @staticmethod
    def _score(r: SearchResult, norm: str) -> float:
        t = normalize_series_name(r.title)
        title_score = 1.0 if norm in t else (0.6 if any(w in t for w in norm.split()) else 0.2)
        if any(m in t for m in ["variant", "2nd print", "reprint", "sketch"]):
            title_score *= 0.3
        seeder_score = min(r.seeders / 50, 1.0) if r.seeders > 0 else 0.1
        fmt = 1.0 if ".cbz" in r.title.lower() else (0.8 if ".cbr" in r.title.lower() else 0.5)
        return title_score * 0.6 + seeder_score * 0.3 + fmt * 0.1

    # ── Cierre del círculo: descargado → en tu biblioteca (D1) ───────────────

    async def check_completions(self, limit: int = 50) -> int:
        """Para cada item DOWNLOADING, ¿ya existe un File enlazado a lo que
        pedía? El import loop periódico ya existente es quien de verdad
        clasifica el archivo; esto solo refleja ese hecho en la wishlist."""
        items = list((await self.db.execute(
            select(Wishlist)
            .where(Wishlist.status == WishlistStatus.DOWNLOADING)
            .limit(limit)
        )).scalars().all())

        completed = 0
        for item in items:
            if await self._is_fulfilled(item):
                item.status = WishlistStatus.IMPORTED
                item.downloaded_at = datetime.now(UTC)
                await self.db.flush()
                completed += 1
                logger.info("orchestrator.item_imported", id=str(item.id))
        return completed

    async def _is_fulfilled(self, item: Wishlist) -> bool:
        # B7 (revisión de PR, 2026-09-26): un File con is_missing=True ya
        # no es "lo tengo" — sin este filtro, un archivo borrado a mano
        # tras haberse importado bastaba para dar por cumplida la wishlist.
        if item.issue_id:
            row = (await self.db.execute(
                select(File.id)
                .where(File.issue_id == item.issue_id)
                .where(File.is_missing.is_(False))
                .limit(1)
            )).first()
            return row is not None
        if item.series_id:
            row = (await self.db.execute(
                select(File.id)
                .join(Issue, File.issue_id == Issue.id)
                .where(Issue.series_id == item.series_id)
                .where(File.imported_at >= item.added_at)
                .where(File.is_missing.is_(False))
                .limit(1)
            )).first()
            return row is not None
        return False


def _extract_ed2k_hash(url: str) -> str | None:
    """ed2k://|file|NOMBRE|TAMAÑO|HASH|/ — el hash ya viaja en la propia
    URL, no hace falta preguntarle nada a aMule para tenerlo."""
    parts = url.split("|")
    return parts[4] if len(parts) >= 5 else None
