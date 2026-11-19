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
import asyncio
import base64
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import parse_qs, unquote, unquote_plus, urlsplit
from uuid import uuid4

import structlog
from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import (
    Collection,
    CollectionAutoSearch,
    EstadoAlias,
    File,
    Issue,
    LocalAlias,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
    collection_series,
)
from zascarr.services import tareas
from zascarr.services.amule import AMuleClient
from zascarr.services.auth import sign_token, verify_token
from zascarr.services.blog_feed import buscar_en_feed, estado_feed, resultados_de_busqueda
from zascarr.services.legal import is_acknowledged
from zascarr.services.politica import (
    ESTADOS_REACTIVABLES,
    Querer,
    politica_efectiva,
    querer_de_serie,
    retirar_de_serie,
)
from zascarr.services.prowlarr import (
    COMIC_CATEGORIES,
    ProwlarrClient,
    SearchResult,
    prowlarr_indexers_seleccionados,
)
from zascarr.services.series import numero_de_grapa
from zascarr.services.transmission import TransmissionClient
from zascarr.utils.naming import normalize_series_name, parse_comic_filename

logger = structlog.get_logger()
_tarea_descargas = None

MAX_SIZE_BYTES = 500 * 1024 * 1024

# T-62: espera entre fallos de envío consecutivos al cliente de descargas.
# Crece con cada intento y se queda en el tope: un cliente caído no quema
# Prowlarr/foro en cada ciclo, pero el deseo no queda fuera para siempre. El
# usuario puede saltárselo con «Reintentar» (limpia `next_retry_at`).
BACKOFF_ENVIOS = (
    timedelta(minutes=10),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
)


def prowlarr_configurado(settings) -> bool:
    """¿Prowlarr tiene URL y API key? Una fuente encendida pero incompleta no se consulta."""
    return bool(
        (getattr(settings, "prowlarr_url", "") or "").strip()
        and (getattr(settings, "prowlarr_api_key", "") or "").strip()
    )


def hay_fuente_de_busqueda(settings) -> bool:
    """¿Hay al menos una fuente de búsqueda de descargas activa? (D9; la reutiliza el Inicio, V4,
    para no inventar su propia definición de «fuente activa»)."""
    foro_configurado = bool(
        settings.forum_enabled and settings.forum_username and settings.forum_url
    )
    blog_configurado = bool(
        getattr(settings, "blog_feed_enabled", False)
        and (getattr(settings, "blog_feed_url", "") or "").strip()
    )
    return bool(settings.prowlarr_enabled) or foro_configurado or blog_configurado


# D9: causas distinguibles de "por qué esta búsqueda no avanza", en
# español llano — nunca un detalle técnico (excepción, URL, cuerpo HTTP)
# que el coleccionista no pueda accionar. El aviso legal pendiente NO
# vive aquí: es un estado global (ver services/legal.py), lo muestra la
# UI de wishlist con un banner propio en vez de escribirse en cada fila.
MOTIVO_SIN_FUENTE = (
    "Sin fuente de búsqueda activa — activa Prowlarr, el foro o un blog/RSS en Ajustes")
MOTIVO_PROWlARR_CONFIGURACION = (
    "Prowlarr está encendido pero le falta la URL o la clave de API — revísalo en Ajustes"
)
MOTIVO_FUENTE_INACCESIBLE = (
    "La fuente de búsqueda no respondió a tiempo — se reintentará automáticamente"
)
MOTIVO_SIN_RESULTADOS = "No se encontró nada en las fuentes activas"
#: SCR4: el foro pidió esperar (Search Flood Control) — no es «sin resultados».
MOTIVO_FORO_ESPERA = "El foro pidió esperar unos segundos; se reintentará"
#: El foro esperaba Y además Prowlarr trajo cosas que se descartaron: decir solo
#: «el foro pidió esperar» ocultaba el motivo real (bug de UX 2026-11-16).
MOTIVO_ESPERA_CON_DESCARTES = (
    "El foro pidió esperar unos segundos y los resultados de Prowlarr no eran utilizables; "
    "se reintentará")
MOTIVO_CANDIDATO_RECHAZADO = (
    "Se encontró algo, pero ningún cliente de descarga está activo — revisa Ajustes"
)
#: D8: había resultados, pero ninguno declaraba el número pedido. NO es
#: "ningún backend activo" — decir eso sería mentir (D9) sobre lo que pasó.
#: Cubre los dos motivos de descarte (número distinto o serie distinta):
#: decir "ninguno era el número" cuando el descarte fue por título sería
#: engañoso, y D9 existe justo para no dar motivos que no son ciertos.
MOTIVO_NUMERO_DISTINTO = (
    "Se encontraron resultados, pero ninguno coincide con este número de esta serie. "
    "Si el release usa otro nombre para la serie, importa un fichero y asígnalo una vez "
    "en Pendientes: ZascArr aprenderá ese nombre para la próxima búsqueda"
)
MOTIVO_CLIENTE_INACCESIBLE = (
    "No se pudo enviar al cliente de descarga — se reintentará más tarde"
)
#: UX 2026-11-17: decir CUÁL no responde evita que el coleccionista tenga que
#: adivinar entre Transmission y aMule (antes ambos compartían el genérico).
MOTIVO_TRANSMISSION_INACCESIBLE = (
    "Transmission no respondió — se reintentará más tarde"
)
MOTIVO_AMULE_INACCESIBLE = (
    "aMule no respondió — se reintentará más tarde"
)


def motivo_de_cliente(backend) -> str:
    """Mensaje concreto del cliente que falló (o el genérico si no se sabe)."""
    if backend == DownloadBackend.TRANSMISSION:
        return MOTIVO_TRANSMISSION_INACCESIBLE
    if backend == DownloadBackend.AMULE:
        return MOTIVO_AMULE_INACCESIBLE
    return MOTIVO_CLIENTE_INACCESIBLE
MOTIVO_ERROR_INESPERADO = "Ocurrió un error inesperado al buscar — se reintentará automáticamente"


def _clave_de_enlace_de_foro(url: str) -> str:
    """Identidad del fichero: hash ed2k/btih, no la URL.

    El mismo fichero puede estar enlazado dos veces con distinta codificación
    (`%20` vs espacio) y la deduplicación por URL cruda lo dejaba duplicado en
    «Buscar ahora» (bug UX 2026-11-16: Sector Lejano, dos filas idénticas).
    """
    if url.startswith("ed2k://|file|"):
        partes = url.split("|")
        if len(partes) >= 5 and partes[4]:
            return "ed2k:" + partes[4].strip().lower()
    if url.startswith("magnet:?"):
        parametros = parse_qs(url[len("magnet:?"):])
        xt = (parametros.get("xt") or [""])[0]
        if xt.lower().startswith("urn:btih:"):
            return "magnet:" + xt.rsplit(":", 1)[-1].lower()
    return "url:" + url


def _tamano_de_enlace_de_foro(url: str) -> int:
    """Tamaño declarado en un enlace ed2k (bytes); 0 si no se puede leer."""
    if url.startswith("ed2k://|file|"):
        partes = url.split("|")
        if len(partes) >= 4 and partes[3].isdigit():
            return int(partes[3])
    return 0


def _sin_duplicados_de_prowlarr(resultados: list[SearchResult]) -> list[SearchResult]:
    """Un mismo release aparece en varios indexers con URL distinta.

    Se conserva uno por (título normalizado, tamaño) — el de más seeders —;
    un tamaño distinto es otra edición y se mantiene (2026-11-16).
    """
    elegidos: dict[tuple[str, int], SearchResult] = {}
    for r in resultados:
        clave = (normalize_series_name(r.title), int(r.size_bytes or 0))
        previo = elegidos.get(clave)
        if previo is None or r.seeders > previo.seeders:
            elegidos[clave] = r
    return list(elegidos.values())


def _nombre_de_fichero_de_enlace(url: str) -> str:
    """Nombre del fichero que viaja dentro de un enlace ed2k o de un magnet.

    Cada enlace de un mismo tema del foro es un número/edición distinta: usar el
    título del TEMA para todos pintaba N candidatos idénticos en «Buscar ahora»
    (bug UX 2026-11-16). El nombre del fichero los distingue y además da el
    formato real (CBZ/CBR) a la fila.
    """
    if url.startswith("ed2k://|file|"):
        partes = url.split("|")
        if len(partes) >= 3 and partes[2]:
            return unquote_plus(partes[2]).strip()[:200]
        return ""
    if url.startswith("magnet:?"):
        parametros = parse_qs(url[len("magnet:?"):])
        nombre = (parametros.get("dn") or [""])[0]
        return unquote(nombre).strip()[:200]
    return ""

#: D10 (2026-11-16): URLs ya enviadas a mano por ítem. El coleccionista puede querer
#: VARIOS candidatos de una misma búsqueda (varios números + un tie-in): cada envío
#: extra no debe pisar el estado ni repetir el mismo enlace. En memoria (un worker).
_ENVIADOS_MANUAL: dict[str, set[str]] = {}
_MAX_ITEMS_ENVIADOS_MANUAL = 500


def _ya_enviado(item_id, download_url: str) -> bool:
    return download_url in _ENVIADOS_MANUAL.get(str(item_id), set())


def _marcar_enviado(item_id, download_url: str) -> None:
    _ENVIADOS_MANUAL.setdefault(str(item_id), set()).add(download_url)
    while len(_ENVIADOS_MANUAL) > _MAX_ITEMS_ENVIADOS_MANUAL:
        _ENVIADOS_MANUAL.pop(next(iter(_ENVIADOS_MANUAL)))
MOTIVO_CANDIDATO_INVALIDO = (
    "Ese candidato ya no es válido — vuelve a buscar y elige uno de la lista actual"
)

# D10: cuánto dura la validez de un candidato mostrado en "Buscar ahora"
# antes de que haya que volver a buscar — suficiente para que una persona
# lo mire y decida, corto para acotar la ventana de un token reenviado.
TOKEN_CANDIDATO_TTL_SEGUNDOS = 600


@dataclass(frozen=True)
class SincronizacionPolitica:
    """D8: resultado de una pasada de `sync_policy_items` — para el log del
    ciclo y para los tests, sin tener que leer la tabla."""
    generados: int
    retirados: int


#: C6 (FR-14): lo que genera la política entra detrás de lo pedido a mano (prioridad 5). Se fija
#: al CREAR el ítem;
#: reactivar uno existente (`retirado`/`imported` → `wanted`) no toca su prioridad.
PRIORIDAD_DE_LA_POLITICA = 8


class DownloadBackend(StrEnum):
    TRANSMISSION = "transmission"
    AMULE        = "amule"


def _detect_backend(url: str) -> DownloadBackend:
    return (
        DownloadBackend.AMULE if url.lower().startswith("ed2k://") else DownloadBackend.TRANSMISSION
    )


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

        settings = get_settings()
        ahora = datetime.now(UTC)
        cooldown = timedelta(hours=settings.orchestrator_retry_cooldown_hours)
        cutoff = ahora - cooldown
        elegibles = (
            select(Wishlist)
            .where(Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]))
            # T-62: un fallo de ENVÍO se rige por su propio backoff (10 min,
            # 30 min, 2 h, 6 h); vencido, entra aunque el cooldown global de 6 h
            # aún no haya pasado — si no, las esperas cortas nunca servirían.
            # El cooldown de `last_searched_at` sigue gobernando los intentos
            # que no programaron reintento (sin resultados, candidato rechazado).
            .where(or_(
                and_(
                    Wishlist.next_retry_at.is_not(None),
                    Wishlist.next_retry_at <= ahora,
                ),
                and_(
                    Wishlist.next_retry_at.is_(None),
                    or_(
                        Wishlist.last_searched_at.is_(None),
                        Wishlist.last_searched_at < cutoff,
                    ),
                ),
            ))
            .order_by(Wishlist.priority.asc(), Wishlist.added_at.asc())
        )
        # C6 (FR-18): lo MANUAL conserva su lote por ciclo (`limit` = max_concurrent_downloads); lo
        # que genera la política va aparte y solo lo limita el techo por hora
        # (`politica_busquedas_por_hora`).
        manuales = list((await self.db.execute(
            elegibles.where(Wishlist.origen != WishlistOrigin.POLICY).limit(limit)
        )).scalars().all())
        de_politica = list((await self.db.execute(
            elegibles.where(Wishlist.origen == WishlistOrigin.POLICY)
            .limit(settings.politica_busquedas_por_hora)
        )).scalars().all())

        sent = 0
        for item in [*manuales, *de_politica]:
            if item.origen == WishlistOrigin.POLICY and not await self._queda_cupo_de_politica():
                break          # techo agotado: lo demás espera a un ciclo posterior
            try:
                if await self._process_item(item):
                    sent += 1
            except Exception:
                logger.exception("orchestrator.item_failed", id=str(item.id))
                item.status = WishlistStatus.FAILED
                item.last_error = MOTIVO_ERROR_INESPERADO
                await self.db.flush()
        return sent

    async def _queda_cupo_de_politica(self) -> bool:
        """FR-05/FR-07: ¿se han buscado menos de R ítems de política en la última hora? Se cuenta
        con
        las marcas YA CONFIRMADAS en la BD y con la hora de la BD (`now()`), no con el reloj del
        proceso: así vale también en el primer ciclo tras un arranque o un reinicio."""
        usadas = (await self.db.execute(
            select(func.count()).select_from(Wishlist)
            .where(Wishlist.origen == WishlistOrigin.POLICY)
            .where(Wishlist.last_searched_at > func.now() - timedelta(hours=1))
        )).scalar_one()
        return int(usadas) < get_settings().politica_busquedas_por_hora

    async def _marcar_busqueda(self, item: Wishlist) -> None:
        """Marca el intento con la hora de la BD (FR-23). En ítems de política la marca se CONFIRMA
        con un commit corto ANTES de la primera petición externa (FR-22): si el ciclo falla después,
        la marca persiste y la ventana la cuenta. Se hace con `UPDATE … now() RETURNING` para no
        dejar el atributo expirado (carga perezosa en async).

        Se confirma SOLO la marca. El estado `searching` queda como cambio sin confirmar (flush):
        si el proceso muere o se cancela durante la petición, el rollback lo deshace y el ítem sigue
        siendo reintentable; confirmarlo lo dejaría «buscando» para siempre (el ciclo solo toma
        `wanted`/`failed`)."""
        marca = (await self.db.execute(
            update(Wishlist).where(Wishlist.id == item.id)
            .values(last_searched_at=func.now())
            .returning(Wishlist.last_searched_at)
        )).scalar_one()
        item.last_searched_at = marca
        if item.origen == WishlistOrigin.POLICY:
            await self.db.commit()
        item.status = WishlistStatus.SEARCHING
        await self.db.flush()

    async def _restaurar_marca(self, item: Wishlist,
                               marca_previa: datetime | None) -> None:
        """Deshace la marca de intento de `_marcar_busqueda` (usada si el foro pide esperar).

        La marca de política se confirma con commit ANTES de la petición (FR-22), así que no basta
        con tocar el atributo: se restaura con un UPDATE y, en política, se confirma igual que se
        confirmó la marca. El ítem vuelve a ser elegible al pasar la espera y no cuenta en el techo
        por hora (`_queda_cupo_de_politica`).
        """
        await self.db.execute(
            update(Wishlist).where(Wishlist.id == item.id)
            .values(last_searched_at=marca_previa)
        )
        item.last_searched_at = marca_previa
        if getattr(item, "origen", None) == WishlistOrigin.POLICY:
            await self.db.commit()
        await self.db.flush()

    def _programar_reintento(self, item: Wishlist,
                             ahora: datetime | None = None) -> datetime:
        """Programa el siguiente intento tras un fallo de ENVÍO al cliente.

        T-62: el fallo de envío (cliente inaccesible) se reintenta con espera
        creciente — 10 min, 30 min, 2 h, 6 h (tope) — en vez de depender del
        cooldown global de 6 h, que además bloqueaba a todos los deseos a la
        vez. Suma un fallo consecutivo y fija `next_retry_at`; lo limpia un
        envío correcto o el reintento manual. No se llama por «sin resultados»
        ni por «candidato rechazado»: eso no es un fallo del cliente.
        """
        item.retry_count = (item.retry_count or 0) + 1
        espera = BACKOFF_ENVIOS[min(item.retry_count, len(BACKOFF_ENVIOS)) - 1]
        item.next_retry_at = (ahora or datetime.now(UTC)) + espera
        return item.next_retry_at

    def _limpiar_reintento(self, item: Wishlist) -> None:
        """Un envío correcto recupera el deseo: fuera el backoff pendiente."""
        item.retry_count = 0
        item.next_retry_at = None

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
                self._limpiar_reintento(item)  # T-62: el cliente volvió a responder
                await self.db.flush()
                logger.info(
                    "orchestrator.download_started", title=candidate.title, backend=backend.value
                )
                return True

        # Hubo candidatos pero ninguno se pudo enviar (backend caído, etc.):
        # esto sí es un fallo real, distinto de "sin resultados todavía".
        item.status = WishlistStatus.FAILED
        item.last_error = motivo_de_cliente(backend)
        self._programar_reintento(item)
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

        # D1/H2: marca el intento ya aquí, con o sin resultado — es lo que
        # activa el cooldown de process_wishlist y evita quemar Prowlarr/
        # foro en cada ciclo con un item condenado. C6: va ANTES de comprobar si hay alguna fuente
        # activa (decisión del PO): un ítem sin fuentes gasta el cooldown de 6 h y no vuelve a
        # ocupar huecos del lote en cada ciclo.
        marca_previa = getattr(item, "last_searched_at", None)
        await self._marcar_busqueda(item)

        settings = get_settings()

        # D9: si ninguna fuente está siquiera activa, ni lo intentamos —
        # se lo decimos al coleccionista en vez de dejarlo en "Buscando…"
        # para siempre sin explicación.
        if not hay_fuente_de_busqueda(settings):
            item.status = WishlistStatus.WANTED
            item.last_error = MOTIVO_SIN_FUENTE
            await self.db.flush()
            return []

        results: list[SearchResult] = []
        titulo_serie = ""
        alias_serie: set[str] = set()
        if item.series_id:
            serie = (await self.db.execute(
                select(Series).where(Series.id == item.series_id))).scalar_one_or_none()
            titulo_serie = serie.title if serie else ""
            # B13: alias confirmados a mano. Se cargan antes de las fuentes para que el
            # feed RSS también pueda aceptar un release con el nombre español.
            alias_serie = set((await self.db.execute(
                select(LocalAlias.pattern_norm)
                .where(LocalAlias.series_id == item.series_id,
                       LocalAlias.estado == EstadoAlias.ACTIVO))).scalars().all())

        # Prowlarr y foro se consultan SIEMPRE juntos (no en cascada): el
        # coleccionista ve en una sola lista lo que hay en cada fuente. En
        # paralelo para que el foro no espere a que Prowlarr agote su timeout.
        # Un flood del foro no invalida los resultados de Prowlarr; si no hay
        # ninguno, se conserva el comportamiento de espera de SCR4.
        from zascarr.services.forum_scraper import ForumFloodControl
        from zascarr.utils.cortesia import CortesiaEnEspera

        resultado_prowlarr, resultado_foro = await asyncio.gather(
            self._prowlarr_candidates(query, settings),
            self._forum_candidates(query),
            return_exceptions=True,
        )
        # `CancelledError` hereda de BaseException: no es un fallo de fuente, es la
        # cancelación del ciclo (apagado, timeout del proceso). Se propaga tal cual.
        for resultado in (resultado_prowlarr, resultado_foro):
            if isinstance(resultado, asyncio.CancelledError):
                raise resultado

        motivo_prowlarr: str | None = None
        if isinstance(resultado_prowlarr, BaseException):
            logger.exception("orchestrator.prowlarr_search_failed", id=str(item.id))
            motivo_prowlarr = MOTIVO_FUENTE_INACCESIBLE
        elif resultado_prowlarr is not None:
            results, motivo_prowlarr = resultado_prowlarr

        forum_flood = isinstance(resultado_foro, ForumFloodControl)
        forum_espera = isinstance(resultado_foro, CortesiaEnEspera)
        if forum_flood:
            logger.info("orchestrator.forum_flood_sin_bloquear_prowlarr", id=str(item.id))
        elif forum_espera:
            logger.info("orchestrator.forum_cortesia_sin_bloquear_prowlarr", id=str(item.id))
        elif isinstance(resultado_foro, BaseException):
            logger.warning("orchestrator.forum_search_failed", id=str(item.id),
                           error=type(resultado_foro).__name__)
        else:
            results.extend(resultado_foro or [])

        motivo_blog: str | None = None
        if getattr(settings, "blog_feed_enabled", False):
            url_blog = (getattr(settings, "blog_feed_url", "") or "").strip()
            if not estado_feed(url_blog):
                motivo_blog = (
                    "El blog/RSS está encendido pero le falta una URL válida — "
                    "revísalo en Ajustes")
            else:
                try:
                    entradas = await buscar_en_feed(url_blog, query, alias=alias_serie)
                    results.extend(resultados_de_busqueda(entradas, url_blog))
                except Exception:
                    logger.exception("orchestrator.blog_search_failed")
                    motivo_blog = MOTIVO_FUENTE_INACCESIBLE

        # Deduplica por URL: la misma release puede aparecer en Prowlarr y en
        # el foro, y no queremos dos botones para exactamente lo mismo.
        vistos: set[tuple[str, str]] = set()
        unicos: list[SearchResult] = []
        for resultado in results:
            clave = (resultado.download_url, resultado.title)
            if clave in vistos:
                continue
            vistos.add(clave)
            unicos.append(resultado)

        candidates = self._ranked_candidates(unicos, query) if unicos else []

        if not candidates and forum_flood:
            # C-1 (SecOps): un flood es una espera, no un intento fallido. Se deshace la
            # marca para que el ítem se reintente al pasar la espera y no consuma cupo de
            # política (la marca se había confirmado antes de la petición).
            # El estado vuelve a WANTED ANTES de restaurar: en política, la restauración
            # confirma, y no debe persistir el SEARCHING transitorio de _marcar_busqueda.
            item.status = WishlistStatus.WANTED
            item.last_error = MOTIVO_FORO_ESPERA
            await self._restaurar_marca(item, marca_previa)
            await self.db.flush()
            return None

        # La relevancia se resuelve con el título local (sin el número) y los alias;
        # titulo_serie/alias_serie se cargaron antes de consultar las fuentes.
        candidates = self._relevantes(
            candidates, item.search_query or titulo_serie or query, alias_serie)

        descartados_por_numero = 0
        if item.numero is not None:
            antes = len(candidates)
            candidates = [
                c
                for c in candidates
                if self._candidato_es_del_numero(c, item.numero, titulo_serie, alias_serie)
            ]
            descartados_por_numero = antes - len(candidates)

        # Blindaje legal: opt-in por backend (deshabilitados por defecto,
        # igual que forum_enabled ya lo estaba) — un candidato de un
        # backend no activado ni se intenta enviar, ni se ofrece para
        # elegir a mano en D10.
        candidatos_crudos = candidates
        candidates = [
            c
            for c in candidates
            if self._backend_enabled(_detect_backend(c.download_url), settings)
        ]

        if not candidates:
            # Se comprueba DESPUÉS de relevancia/número/backend: un candidato de
            # Prowlarr que se descarta no debe ocultar que el foro pidió esperar.
            if forum_espera:
                item.status = WishlistStatus.WANTED
                # Si Prowlarr sí respondió pero todo se descartó, no mentir con un
                # «el foro pidió esperar» que oculta de dónde venir el problema.
                item.last_error = (
                    MOTIVO_ESPERA_CON_DESCARTES if unicos else MOTIVO_FORO_ESPERA)
                await self._restaurar_marca(item, marca_previa)
                await self.db.flush()
                return []
            item.status = WishlistStatus.WANTED  # nada encontrado todavía, no es un fallo
            # D9: distingue "no había nada" de "había algo pero el
            # backend correspondiente está apagado" — la acción del
            # coleccionista es distinta en cada caso.
            if candidatos_crudos:
                item.last_error = MOTIVO_CANDIDATO_RECHAZADO
            elif descartados_por_numero:
                item.last_error = MOTIVO_NUMERO_DISTINTO
            else:
                item.last_error = motivo_prowlarr or motivo_blog or MOTIVO_SIN_RESULTADOS
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
        solo de cara al ranking).

        Hallazgo de revisión (2026-09-26): sin comprobar el ESTADO del
        item, confirmar dos veces el mismo token dentro de su ventana de
        validez (doble clic, pestaña duplicada, un reenvío deliberado)
        podía encolar la misma descarga otra vez sobre un item que ya
        está DOWNLOADING/IMPORTED. Solo se envía desde un estado
        accionable — el mismo criterio que decide si se ofrece "Buscar
        ahora" en la UI (web/wishlist.py::_row, puede_buscar_ahora).

        Segundo hallazgo, revisión de PR (2026-09-26): ese guardarraíl
        por sí solo detiene un reenvío SECUENCIAL (tras completar el
        primer envío), no dos peticiones CONCURRENTES — ambas pueden
        leer WANTED/FAILED en su propia sesión antes de que ninguna
        termine `_send()` (I/O de red, con `await` de por medio).
        Firmado (D10) no es lo mismo que de un solo uso. Se reclama el
        item con un UPDATE condicionado (WANTED/FAILED → SEARCHING)
        ANTES de tocar la red: Postgres serializa los UPDATE contra la
        misma fila (bloquea al segundo hasta que el primero confirma, y
        entonces reevalúa el WHERE), así que como mucho una petición ve
        su fila afectada — la otra ve 0 filas y no llega a enviar nada.
        """
        if _ya_enviado(item.id, candidate.download_url):
            # Doble clic/reenvío del MISMO candidato: no se encola dos veces. No impide
            # enviar otros candidatos distintos del mismo preview (2026-11-16).
            item.last_error = MOTIVO_CANDIDATO_INVALIDO
            await self.db.flush()
            return False

        if item.status not in (WishlistStatus.WANTED, WishlistStatus.FAILED):
            if item.status == WishlistStatus.DOWNLOADING:
                # Envío EXTRA desde el mismo «Buscar ahora»: no se toca el estado ni
                # `download_ref` (siguen apuntando a la primera descarga); el importador
                # recogerá también los ficheros de los envíos extra.
                settings = get_settings()
                backend = _detect_backend(candidate.download_url)
                if not self._backend_enabled(backend, settings):
                    item.last_error = MOTIVO_CANDIDATO_RECHAZADO
                    await self.db.flush()
                    return False
                ref = await self._send(backend, candidate)
                if ref is None:
                    item.last_error = motivo_de_cliente(backend)
                    # T-62: el envío extra es auxiliar. Un fallo NO cambia el estado
                    # del deseo (la descarga principal sigue en DOWNLOADING) ni
                    # programa el backoff del ciclo (que solo mira WANTED/FAILED):
                    # se informa en ese candidato y el coleccionista decide.
                    await self.db.flush()
                    return False
                self._limpiar_reintento(item)
                _marcar_enviado(item.id, candidate.download_url)
                await self.db.flush()
                logger.info("orchestrator.download_started", title=candidate.title,
                            backend=backend.value, manual=True, extra=True)
                return True
            item.last_error = MOTIVO_CANDIDATO_INVALIDO
            await self.db.flush()
            return False

        reclamado = await self.db.execute(
            update(Wishlist)
            .where(Wishlist.id == item.id)
            .where(Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]))
            .values(status=WishlistStatus.SEARCHING)
        )
        if reclamado.rowcount == 0:
            # Perdió la carrera: otra petición concurrente ya reclamó
            # este mismo item entre que se cargó y que llegamos aquí.
            # Deliberadamente NO se escribe last_error aquí (verificado
            # en vivo, 2026-09-26): esta escritura llegaría después de
            # que la petición ganadora ya confirmara la suya (pasa por
            # el mismo `await self._send()`, más lento), y un simple
            # `flush()` sobre este objeto en memoria pisaría con
            # "candidato inválido" el resultado real ya guardado —
            # incluido un `last_error=None` de un envío que sí tuvo
            # éxito. La fila que ve el perdedor se refresca aparte
            # (`_get_row`, en el router) con el estado real y actual.
            return False
        item.status = WishlistStatus.SEARCHING

        settings = get_settings()
        backend = _detect_backend(candidate.download_url)
        if not self._backend_enabled(backend, settings):
            # La reclamación deja el item en SEARCHING (transitorio) —
            # si no se envía nada, hay que devolverlo a un estado
            # accionable, o quedaría "colgado" igual que el bug ya
            # corregido de preview_candidates.
            item.status = WishlistStatus.FAILED
            item.last_error = MOTIVO_CANDIDATO_RECHAZADO
            await self.db.flush()
            return False

        ref = await self._send(backend, candidate)
        if ref is None:
            item.status = WishlistStatus.FAILED
            item.last_error = motivo_de_cliente(backend)
            self._programar_reintento(item)
            await self.db.flush()
            return False

        item.status = WishlistStatus.DOWNLOADING
        item.download_backend = backend.value
        item.download_ref = ref
        item.last_error = None
        self._limpiar_reintento(item)  # T-62: el envío manual recupera el deseo
        _marcar_enviado(item.id, candidate.download_url)
        # Hora de la BD (FR-23).
        item.last_searched_at = (await self.db.execute(select(func.now()))).scalar_one()
        await self.db.flush()
        logger.info(
            "orchestrator.download_started",
            title=candidate.title,
            backend=backend.value,
            manual=True,
        )
        return True

    async def _build_query(self, item: Wishlist) -> str | None:
        if item.search_query:
            return item.search_query
        if item.series_id:
            series = (
                await self.db.execute(select(Series).where(Series.id == item.series_id))
            ).scalar_one_or_none()
            if not series:
                return None
            q = series.title
            # D8: un item generado por la política lleva el número en
            # `item.numero` y NO tiene `issue_id` (el número que no tienes no
            # tiene fila `Issue`). Sin esto, los N items generados harían la
            # MISMA consulta —solo el título— y podrían acabar enviando el mismo
            # candidato N veces.
            if item.numero is not None:
                q += f" {item.numero}"
            elif item.issue_id:
                issue = (
                    await self.db.execute(select(Issue).where(Issue.id == item.issue_id))
                ).scalar_one_or_none()
                if issue and issue.issue_number:
                    q += f" {issue.issue_number}"
            return q
        if item.issue_id:
            issue = (
                await self.db.execute(select(Issue).where(Issue.id == item.issue_id))
            ).scalar_one_or_none()
            if issue:
                series = (
                    await self.db.execute(select(Series).where(Series.id == issue.series_id))
                ).scalar_one_or_none()
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
                    logger.warning("orchestrator.send_sin_credenciales",
                                   backend=backend.value)
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

    async def enviar_candidato_de_mejora(self, candidate: SearchResult) -> tuple[bool, str]:
        """BL-D3: envía la edición que el coleccionista confirmó. No toca la wishlist ni
        sustituye archivos; el importador la dejará como archivo disponible del número."""
        settings = get_settings()
        backend = _detect_backend(candidate.download_url)
        if not self._backend_enabled(backend, settings):
            return False, "El cliente de descarga de ese enlace está desactivado en Ajustes."
        ref = await self._send(backend, candidate)
        if ref is None:
            return False, "No se pudo enviar la descarga — revisa el cliente en Ajustes."
        logger.info("orchestrator.upgrade_started", title=candidate.title,
                    backend=backend.value)
        return True, "Descarga enviada. Cuando llegue, el importador la añadirá al número."

    async def _prowlarr_candidates(
            self, query: str, settings) -> tuple[list[SearchResult], str | None]:
        """Resultados de Prowlarr y, si falla, el motivo D9 que se mostrará si no hay nada más."""
        if not settings.prowlarr_enabled:
            return [], None
        if not prowlarr_configurado(settings):
            # D9 (2026-11-11): fuente encendida pero incompleta NO es «sin resultados».
            return [], MOTIVO_PROWlARR_CONFIGURACION
        try:
            seleccionados = prowlarr_indexers_seleccionados(settings)
            if seleccionados:
                encontrados = await self._prowlarr.search(
                    query, categories=COMIC_CATEGORIES, indexer_ids=seleccionados)
            else:
                encontrados = await self._prowlarr.search(
                    query, categories=COMIC_CATEGORIES)
            sin_repetir = _sin_duplicados_de_prowlarr(encontrados)
            if len(sin_repetir) != len(encontrados):
                logger.info("orchestrator.prowlarr_duplicados",
                            descartados=len(encontrados) - len(sin_repetir))
            return sin_repetir, None
        except Exception:
            logger.exception("orchestrator.prowlarr_search_failed")
            return [], MOTIVO_FUENTE_INACCESIBLE

    async def _forum_candidates(self, query: str) -> list[SearchResult]:
        """Candidatos del foro configurado; admite dobles antiguos que devolvían uno solo.

        El scraper recorre TODOS los temas y enlaces de la búsqueda, no solo el
        primero: el foro suele tener varias ediciones/releases en la misma página.
        """
        resultado = await self._forum_fallback(query, propagar_espera=True)
        if resultado is None:
            return []
        if isinstance(resultado, SearchResult):
            return [resultado]
        return list(resultado)

    async def _forum_fallback(
            self, query: str, *, propagar_espera: bool = False) -> list[SearchResult]:
        s = get_settings()
        # forum_url vacío por defecto a propósito (blindaje legal): es un
        # plugin IPB genérico, la URL la aporta el usuario, el proyecto no
        # incluye ni recomienda ningún foro concreto.
        if not s.forum_enabled or not s.forum_username or not s.forum_url:
            return []
        try:
            from zascarr.services.forum_scraper import ForumFloodControl, ForumScraper
            from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada
            scraper = ForumScraper(base_url=s.forum_url, rate_limit=s.forum_rate_limit)
            if not await scraper.login(s.forum_username, s.forum_password):
                logger.info("orchestrator.forum_login_fallido",
                            host=self._host_para_log_foro(s.forum_url))
                return []
            encontrados: list[SearchResult] = []
            vistos: set[str] = set()
            for fr in await scraper.use_ipb_search(query):
                for enlace in (*fr.ed2k_links, *fr.magnet_links):
                    clave = _clave_de_enlace_de_foro(enlace)
                    if clave in vistos:
                        continue
                    vistos.add(clave)
                    nombre = _nombre_de_fichero_de_enlace(enlace)
                    encontrados.append(SearchResult(
                        nombre or fr.topic_title, "forum:crg", enlace,
                        _tamano_de_enlace_de_foro(enlace),
                        1 if enlace.lower().startswith("magnet:?") else 0, "comics"
                    ))
            return encontrados
        except ForumFloodControl:
            # El ítem ya está marcado; _search_and_rank deja MOTIVO_FORO_ESPERA.
            raise
        except CortesiaEnEspera as exc:
            # La búsqueda manual necesita distinguir «el foro pidió esperar» de «no hay
            # nada»; el ciclo automático puede omitirlo y reintentar más tarde.
            if propagar_espera:
                raise
            logger.info("orchestrator.forum_sin_turno",
                        motivo=getattr(exc, "motivo", "cortesia"))
        except FuenteApagada as exc:
            logger.info("orchestrator.forum_sin_turno",
                        motivo=getattr(exc, "motivo", "apagada"))
        except Exception as exc:
            # m-3 (SecOps): solo el tipo, sin traza ni URL (la del foro puede llevar `s=`).
            logger.warning("orchestrator.forum_fallback_error", error=type(exc).__name__)
        return []

    @staticmethod
    def _host_para_log_foro(url: str) -> str:
        """Host del foro para el log, sin la URL ni una posible `s=<sesión>`."""
        try:
            return (urlsplit(url).hostname or "?")[:100]
        except ValueError:
            return "?"

    @staticmethod
    def _candidato_es_del_numero(candidate: SearchResult, numero: int,
                                 titulo_serie: str = "",
                                 alias_serie: set[str] | None = None) -> bool:
        """D8: ¿este candidato es ESE número de ESA serie?

        **Falla cerrado**: sin serie con la que comparar, no se acepta nada.
        Preferimos dejar el número en Pendientes antes que dar por bueno un
        candidato de otra serie.

        El número se compara como entero y solo si el texto parseado es todo
        dígitos: así "04" vale para el 4, y "1.5", "4-6" o "12a" se rechazan de
        forma explícita en vez de por accidente (`lstrip("0")` funcionaba para el
        0 porque ambos lados quedaban vacíos, pero era frágil).

        El título se compara por **igualdad** del normalizado, no por contención:
        la contención acepta series distintas que comparten prefijo —"Batman" en
        "Batman Beyond", "Spider-Man" en "Spider-Man 2099", "Superman" en
        "Superman Batman"— en los dos sentidos. Medido con el banco de rutas
        reales (`scripts/medicion/muestra81_etiquetada.csv`, 81 rutas): igualdad
        acierta 71 y los 5 casos que solo pasaban con contención **no eran
        series distintas legítimas sino sobre-captura del parser** ("Taxus La
        Historia completa" para "Taxus", "Jim Starlin's Dreadstar" para
        "Dreadstar"). Un subtítulo tras " - " ("Asterix T01 - Asterix el Galo")
        lo separa ya el parser (RF-04), así que la igualdad no lo pierde.

        Esa holgura **ya existe y no se toca**: los alias locales de B13 que el
        coleccionista confirmó a mano para esta serie. Un release español puede
        llamar "La Patrulla-X" a una serie catalogada como "X-Men", y sin alias
        la igualdad estricta descartaría el candidato bueno. Aceptarlos no
        afloja el filtro porque no inventan nada: son lo que una persona ya dio
        por bueno. **Límite conocido (arranque en frío):** un alias solo se
        aprende cuando ya hay un fichero asignado a mano desde Pendientes, así
        que la PRIMERA búsqueda de una serie recién dada de alta con nombre
        inglés y releases en español se queda sin candidatos; el motivo del item
        invita a importar uno y asignarlo, que es lo que enseña el alias."""
        parsed = parse_comic_filename(candidate.title)
        if parsed.edition_kind is not None:      # ómnibus/tomo: no es la grapa #N
            return False
        texto = (parsed.issue_number or "").strip()
        if not texto.isdigit():
            return False
        if int(texto) != numero:
            return False
        norm_cand = normalize_series_name(parsed.series or "")
        # Un normalizado vacío haría `"" in ...` o `== ""` y colaría cualquier
        # cosa (un título como "004" normaliza a nada).
        if not norm_cand:
            return False
        norm_serie = normalize_series_name(titulo_serie or "")
        if norm_serie and norm_cand == norm_serie:
            return True
        # Alias locales (B13): es lo que una persona ya confirmó a mano para esta
        # instalación, así que aceptarlos no afloja el filtro — no inventa nada.
        # Sigue fallando cerrado: sin serie Y sin alias, no se acepta nada.
        return normalize_title(parsed.series or "") in (alias_serie or set())

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
                # Un feed RSS no publica seeders; sus magnet/.torrent son directos
                # y no se descartan por no traer ese dato.
                if r.seeders >= 1 or r.indexer.startswith("blog:"):
                    torrents.append((score, r))
            else:
                ed2k.append((score, r))
        torrents.sort(key=lambda x: x[0], reverse=True)
        ed2k.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in torrents] + [r for _, r in ed2k]

    @classmethod
    def _relevantes(cls, candidates: list[SearchResult], norm: str,
                    alias_serie: set[str] | None = None) -> list[SearchResult]:
        """Descarta releases que no contienen TODOS los términos de la serie.

        Se aplica DESPUÉS de cargar los alias locales (B13): un release con el nombre
        español confirmado por el coleccionista no debe caer por no contener el título
        inglés. Una consulta de una sola letra no tiene términos significativos: no filtra.
        """
        terminos = [t for t in normalize_series_name(norm).split() if len(t) > 1]
        if not terminos:
            return candidates
        alias = alias_serie or set()
        relevante: list[SearchResult] = []
        for candidato in candidates:
            parsed = parse_comic_filename(candidato.title)
            if alias and normalize_title(parsed.series or "") in alias:
                relevante.append(candidato)
                continue
            normalizado = normalize_series_name(candidato.title)
            # Palabras completas, no subcadenas: «ko» está dentro de «Konar» y
            # hacía pasar un manual de ginecología como «DC K.O.».
            palabras = set(re.findall(r"\w+", normalizado))
            if all(t in palabras for t in terminos):
                relevante.append(candidato)
        return relevante

    @staticmethod
    def _score(r: SearchResult, norm: str) -> float:
        t = normalize_series_name(r.title)
        title_score = 1.0 if norm in t else (0.6 if any(w in t for w in norm.split()) else 0.2)
        if any(m in t for m in ["variant", "2nd print", "reprint", "sketch"]):
            title_score *= 0.3
        seeder_score = min(r.seeders / 50, 1.0) if r.seeders > 0 else 0.1
        fmt = 1.0 if ".cbz" in r.title.lower() else (0.8 if ".cbr" in r.title.lower() else 0.5)
        return title_score * 0.6 + seeder_score * 0.3 + fmt * 0.1

    # ── D8: generación y retirada, con un solo predicado ─────────────────────
    #
    # Son la misma operación vista desde dos lados: "deja la wishlist con
    # exactamente los números que la política quiere". El predicado
    # (`querer_de_serie`) y la sentencia de retirada viven en
    # `services/politica.py` — la ficha de serie los reutiliza sin instanciar
    # este orquestador. Aquí queda el ciclo: qué series toca, el tope por
    # vuelta, las rondas y la escritura de la generación.

    async def sync_policy_items(self, lote: int | None = None) -> SincronizacionPolitica:
        """Materializa lo que la política quiere y retira lo que ya no quiere.

        Detrás de la puerta legal, igual que buscar (ficha D8, caso 16): crear
        items es el primer paso de "facilitar descargas", así que sin acuse no
        se escribe nada.

        Coste Pi: unas pocas consultas por serie con política activa (o con
        items de política pendientes de retirar) y **como mucho `lote` filas
        nuevas por ciclo**, repartidas en rondas entre series para que una de
        200 números no se lleve el cupo entero (`_generar_lo_que_falta`). No hay
        ninguna consulta por número: eso es lo que hace viable una serie larga.
        """
        if not await is_acknowledged(self.db):
            logger.info("orchestrator.policy_cycle_skipped_no_legal_acknowledgment")
            return SincronizacionPolitica(0, 0)

        if lote is None:
            lote = get_settings().orchestrator_politica_lote
        planes = []
        for serie in await self._series_para_sincronizar():
            efectiva = await politica_efectiva(self.db, serie)
            planes.append((serie, await querer_de_serie(self.db, serie, politica=efectiva)))
        retirados = await self._retirar_lo_que_ya_no_se_quiere(planes)
        generados = await self._generar_lo_que_falta(planes, lote)
        return SincronizacionPolitica(generados, retirados)

    async def _series_para_sincronizar(self) -> list[Series]:
        """Series que esta pasada tiene algo que hacer: las que generan números
        o las que aún tienen items de política pendientes.

        Lo segundo no es redundante: al pasar una serie a `ninguno` deja de
        generar, pero sus items generados siguen en `wanted`/`failed` y hay que
        retirarlos. Si solo se mirara la política activa, quedarían
        buscándose para siempre.
        """
        pendientes = select(Wishlist.series_id).where(
            Wishlist.origen == WishlistOrigin.POLICY,
            Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]),
            Wishlist.series_id.is_not(None),
        )
        # #155 con M:N: incluir suma series; excluir gana sobre incluir.
        incluidas = select(collection_series.c.series_id).join(
            Collection, Collection.id == collection_series.c.collection_id
        ).where(Collection.auto_search == CollectionAutoSearch.INCLUIR)
        excluidas = select(collection_series.c.series_id).join(
            Collection, Collection.id == collection_series.c.collection_id
        ).where(Collection.auto_search == CollectionAutoSearch.EXCLUIR)
        consulta = (
            select(Series)
            .where(
                or_(
                    Series.id.in_(pendientes),
                    and_(
                        Series.id.not_in(excluidas),
                        or_(
                            Series.wishlist_policy.in_(
                                [WishlistPolicy.MISSING, WishlistPolicy.ALL]),
                            Series.id.in_(incluidas),
                        ),
                    ),
                ),
            )
            .order_by(Series.sort_title)
        )
        return list((await self.db.execute(consulta)).scalars().all())

    async def _retirar_lo_que_ya_no_se_quiere(
            self, planes: list[tuple[Series, Querer]]) -> int:
        """Marca `retirado` lo de origen `politica` que el predicado ya no pide.

        Un solo `UPDATE` por serie (**atómico**: una sentencia, sin leer y
        reescribir en Python) y **solo** sobre lo que no ha empezado. La
        sentencia vive en `services/politica.py` porque la UI la reutiliza para
        aplicar la retirada al guardar, sin esperar al ciclo.
        """
        retirados = 0
        for series, querer in planes:
            retirados += await retirar_de_serie(self.db, series, querer)
        return retirados

    async def _generar_lo_que_falta(
            self, planes: list[tuple[Series, Querer]], lote: int) -> int:
        """Crea o reactiva los items de política que el predicado pide y aún no
        están donde tienen que estar. Tope `lote` por ciclo, en rondas entre
        series.

        No basta con insertar: el índice único parcial no mira el estado, así
        que un número ya existente como `retirado`/`imported` seguiría ocupando
        el hueco y volver a quererlo daría error de integridad. Pero la
        reactivación es **solo** para esos dos estados (`ESTADOS_REACTIVABLES`):
        un `FAILED` ya lo reintenta `process_wishlist` —reiniciarlo borraría su
        `last_error` (D9) y gastaría el lote— y un `DOWNLOADED` está esperando al
        importador.
        """
        por_serie: list[tuple[Series, list[int]]] = []
        for series, querer in planes:
            if not querer.numeros:
                continue
            existentes = dict((await self.db.execute(
                select(Wishlist.numero, Wishlist.status)
                .where(Wishlist.series_id == series.id)
                .where(Wishlist.origen == WishlistOrigin.POLICY)
                .where(Wishlist.numero.is_not(None))
            )).all())
            faltan = sorted(
                numero for numero in querer.numeros
                # No existe → hay que crearlo. Existe en un estado reactivable
                # (`retirado`/`imported`) → hay que reactivarlo. Cualquier otro
                # estado se deja como está.
                if numero not in existentes or existentes[numero] in ESTADOS_REACTIVABLES
            )
            if faltan:
                por_serie.append((series, faltan))

        generados, ronda = 0, 0
        while generados < lote:
            hubo = False
            for series, faltan in por_serie:
                if ronda >= len(faltan):
                    continue
                hubo = True
                if generados >= lote:
                    break
                await self._materializar(series, faltan[ronda])
                generados += 1
            if not hubo:
                break
            ronda += 1
        return generados

    @staticmethod
    def _stmt_materializar(series_id, numero: int, ahora: datetime):
        """El `INSERT ... ON CONFLICT ... DO UPDATE` que crea o reactiva el item
        de política de un número.

        Separado para poder fijar en un test dos cosas que no son obvias: que la
        inferencia del conflicto reproduce el `WHERE` del índice parcial
        (`origen='politica' AND numero IS NOT NULL`) y que el `DO UPDATE` **solo**
        toca un estado reactivable — así no pisa un item en vuelo ni reinicia un
        `FAILED`.
        """
        return (
            pg_insert(Wishlist)
            .values(
                id=uuid4(),
                series_id=series_id,
                issue_id=None,
                status=WishlistStatus.WANTED,
                priority=PRIORIDAD_DE_LA_POLITICA,
                origen=WishlistOrigin.POLICY,
                numero=numero,
                added_at=ahora,
            )
            .on_conflict_do_update(
                index_elements=["series_id", "numero"],
                index_where=text("origen = 'politica' AND numero IS NOT NULL"),
                set_={
                    "status": WishlistStatus.WANTED,
                    "added_at": ahora,
                    "download_ref": None,
                    "download_backend": None,
                    "last_error": None,
                    # T-62: una reactivación de política empieza de cero; un
                    # backoff viejo no debe retrasar el deseo reactivado.
                    "retry_count": 0,
                    "next_retry_at": None,
                },
                # Defensa contra dos ciclos solapados: entre el SELECT de
                # `_generar_lo_que_falta` y este INSERT, el otro ciclo puede
                # haber puesto la fila en cualquier estado. Si ya no es
                # reactivable, este upsert no la toca (ni la pisa ni la
                # reinicia).
                where=Wishlist.status.in_(ESTADOS_REACTIVABLES),
            )
        )

    async def _materializar(self, series: Series, numero: int) -> None:
        """Reactiva o crea el item de política del número `numero`."""
        await self.db.execute(self._stmt_materializar(series.id, numero, datetime.now(UTC)))

    # ── Cierre del círculo: descargado → en tu biblioteca (D1) ───────────────

    async def check_completions(self, limit: int = 50) -> int:
        """Para cada item DOWNLOADING, ¿ya existe un File enlazado a lo que
        pedía? El import loop periódico ya existente es quien de verdad
        clasifica el archivo; esto solo refleja ese hecho en la wishlist."""
        global _tarea_descargas
        try:
            items = list((await self.db.execute(
                select(Wishlist)
                .where(Wishlist.status == WishlistStatus.DOWNLOADING)
                .limit(limit)
            )).scalars().all())

            if items and _tarea_descargas is None:
                _tarea_descargas = tareas.iniciar_descargas(total=len(items))
            completed = 0
            for item in items:
                if await self._is_fulfilled(item):
                    item.status = WishlistStatus.IMPORTED
                    item.downloaded_at = datetime.now(UTC)
                    await self.db.flush()
                    completed += 1
                    logger.info("orchestrator.item_imported", id=str(item.id))
            if not items and _tarea_descargas is not None:
                tareas.terminar(_tarea_descargas.id, resumen="Descargas revisadas")
                _tarea_descargas = None
            elif _tarea_descargas is not None:
                tareas.actualizar(_tarea_descargas.id, hechos=completed)
            return completed
        except BaseException as exc:
            if _tarea_descargas is not None:
                tareas.error(_tarea_descargas.id, tipo_error=type(exc).__name__)
                _tarea_descargas = None
            raise
        finally:
            pass

    async def _is_fulfilled(self, item: Wishlist) -> bool:
        # B7 (revisión de PR, 2026-09-26): un File con is_missing=True ya
        # no es "lo tengo" — sin este filtro, un archivo borrado a mano
        # tras haberse importado bastaba para dar por cumplida la wishlist.
        if item.numero is not None:
            # D8: item generado por número. Se empareja por NÚMERO —ligarlo solo
            # a la serie haría que cualquier `File` nuevo de la serie cerrara
            # TODOS los items generados a la vez— y con los mismos criterios que
            # los huecos y que el cierre de serie: `numero_de_grapa` (un ómnibus
            # #4 no es la grapa #4), `is_missing=false` (un fichero desaparecido
            # no cierra nada) e `imported_at >= added_at` (un File anterior al
            # item no lo cumple). Sin lo primero, un fichero borrado a mano
            # cerraría el item como IMPORTED nada más generarse.
            filas = (await self.db.execute(
                select(Issue.issue_number, Issue.format)
                .join(File, File.issue_id == Issue.id)
                .where(Issue.series_id == item.series_id)
                .where(File.is_missing.is_(False))
                .where(File.imported_at >= item.added_at)
            )).all()
            return any(numero_de_grapa(numero, formato) == item.numero
                       for numero, formato in filas)
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


# ── D10: candidato firmado por el servidor, no reconstruido del formulario ───
#
# Hallazgo de revisión (2026-09-26): la primera versión de "Buscar ahora"
# hacía que el formulario de "Descargar este" reenviase los campos del
# candidato (título, indexer, download_url...) en claro, en campos ocultos.
# web/wishlist.py::enviar_candidato los recogía y construía un SearchResult
# directamente con lo que llegara — sin comprobar que esos datos vinieran
# de verdad de una búsqueda hecha para ESE item. Un formulario manipulado a
# mano (o interceptado) podía colar cualquier download_url para cualquier
# item sin haber pasado nunca por preview_candidates().
#
# Ahora el servidor firma el candidato ENTERO junto con el item_id y una
# caducidad corta (HMAC, la misma clave que firma la cookie de sesión —
# services/auth.py::sign_token/verify_token). El formulario solo reenvía
# ese token, nunca los datos sueltos: cualquier cambio en cualquier campo,
# o usarlo para otro item, o usarlo pasada su caducidad, invalida la firma.

def crear_token_candidato(item_id, candidate: SearchResult, secret: str) -> str:
    payload = {
        "item_id": str(item_id),
        "title": candidate.title,
        "indexer": candidate.indexer,
        "download_url": candidate.download_url,
        "size_bytes": candidate.size_bytes,
        "seeders": candidate.seeders,
        "category": candidate.category,
        "exp": int(time.time()) + TOKEN_CANDIDATO_TTL_SEGUNDOS,
    }
    crudo_json = json.dumps(payload, separators=(",", ":")).encode()
    crudo = base64.urlsafe_b64encode(crudo_json).decode()
    return sign_token(crudo, secret)


def verificar_token_candidato(token: str, item_id, secret: str) -> SearchResult | None:
    """None si el token es inválido, de otro item, o ha caducado — nunca
    revienta con un token ausente/manipulado."""
    if not token or not secret:
        return None
    crudo = verify_token(token, secret)
    if crudo is None:
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(crudo.encode()).decode())
    except Exception:
        return None
    if payload.get("item_id") != str(item_id):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    try:
        return SearchResult(
            title=payload["title"],
            indexer=payload["indexer"],
            download_url=payload["download_url"],
            size_bytes=payload["size_bytes"],
            seeders=payload["seeders"],
            category=payload["category"],
        )
    except KeyError:
        return None
