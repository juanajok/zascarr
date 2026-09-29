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
import base64
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from uuid import uuid4

import structlog
from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import (
    File,
    Issue,
    LocalAlias,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.amule import AMuleClient
from zascarr.services.auth import sign_token, verify_token
from zascarr.services.legal import is_acknowledged
from zascarr.services.prowlarr import ProwlarrClient, SearchResult
from zascarr.services.series import huecos_de_serie, numero_de_grapa
from zascarr.services.transmission import TransmissionClient
from zascarr.utils.naming import normalize_series_name, parse_comic_filename

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
MOTIVO_CLIENTE_INACCESIBLE = "No se pudo enviar a ningún cliente de descarga — se reintentará más tarde"
MOTIVO_ERROR_INESPERADO = "Ocurrió un error inesperado al buscar — se reintentará automáticamente"
MOTIVO_CANDIDATO_INVALIDO = "Ese candidato ya no es válido — vuelve a buscar y elige uno de la lista actual"

# D10: cuánto dura la validez de un candidato mostrado en "Buscar ahora"
# antes de que haya que volver a buscar — suficiente para que una persona
# lo mire y decida, corto para acotar la ventana de un token reenviado.
TOKEN_CANDIDATO_TTL_SEGUNDOS = 600

# ── D8: qué números quiere la política y qué se hace con ellos ───────────────
#
# La generación **y** la retirada consumen el MISMO predicado
# (`querer_de_serie`): "números que esta política quiere ahora". Se materializa
# lo que el predicado pide y no existe, y se retira lo de origen `politica` que
# el predicado ya no pide. Con una sola fuente de verdad no pueden divergir ni
# dejar items huérfanos: cualquier motivo para dejar de querer un número
# (cambió la política, llegó el fichero, apareció un item manual de serie) entra
# por el mismo sitio.

#: D8: `futuros` está reservado en el tipo pero no sabe calcularse todavía. No
#: es un fallo: se declara (D9) en vez de inventar una lista de números.
MOTIVO_POLITICA_FUTUROS = (
    "La política «futuros» todavía no se puede aplicar: haría falta que la fuente "
    "publique los números que aún no han salido"
)
#: D8: un item manual a nivel de serie pide la serie genérica. Generar además
#: cada número la buscaría dos veces, así que el predicado no quiere ninguno
#: mientras ese item siga vivo. Importa el caso en que el item manual aparece
#: DESPUÉS: los generados pendientes se retiran igual que si cambiara la
#: política, para no acabar con las dos búsquedas a la vez.
MOTIVO_SERIE_EN_CURSO = (
    "Ya hay un item de esta serie en curso: no se generan números para no buscarla dos veces"
)

#: D8: un item en estos estados ya "empezó" — hay una búsqueda en vuelo
#: (SEARCHING, transitorio) o una descarga en marcha (DOWNLOADING). Marcarlo
#: `retirado` sería mentir (D9) sobre lo que de verdad está pasando, así que la
#: retirada no los toca. Tampoco los reescribe la generación: reiniciarles
#: `added_at` rompería el cierre (`File.imported_at >= Wishlist.added_at`).
ESTADOS_EN_VUELO = (WishlistStatus.SEARCHING, WishlistStatus.DOWNLOADING)

#: D8: un item que ya está donde tiene que estar para este ciclo — pendiente y
#: vivo. La generación no lo reescribe (sería churn y resetearía `added_at`);
#: solo reactiva lo `retirado`/`failed`/`imported`/`downloaded`.
ESTADOS_YA_MATERIALIZADOS = (WishlistStatus.WANTED, *ESTADOS_EN_VUELO)

#: D8: un item en estos estados ya no cuenta como "vivo" al decidir si hay un
#: item manual de serie en curso o un número ya ocupado a mano. FAILED sí
#: cuenta: sigue en la lista y se reintenta tras el cooldown.
ESTADOS_TERMINADOS = (WishlistStatus.IMPORTED, WishlistStatus.RETIRADO)


@dataclass(frozen=True)
class Querer:
    """D8: números que la política de UNA serie quiere **ahora**. Es el único
    predicado de la feature — lo consumen la generación y la retirada.

    `computable=False` significa "no hay con qué calcularlo" (misma semántica
    que `Huecos`), nunca "no falta nada". `motivo` es el texto en español que
    la UI enseña cuando no hay números que generar.
    """
    numeros: frozenset[int]
    computable: bool
    motivo: str | None = None


@dataclass(frozen=True)
class SincronizacionPolitica:
    """D8: resultado de una pasada de `sync_policy_items` — para el log del
    ciclo y para los tests, sin tener que leer la tabla."""
    generados: int
    retirados: int


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

        # D8: la búsqueda es de TEXTO, así que devolver algo no significa que sea
        # el número pedido. El filtro va ANTES de `candidatos_crudos` a
        # propósito: si lo único que había era de otro número, el motivo no puede
        # decir "ningún backend activo" (sería falso, y D9 existe justo para no
        # dar ese tipo de motivo).
        titulo_serie = ""
        alias_serie: set[str] = set()
        descartados_por_numero = 0
        if item.numero is not None:
            if item.series_id:
                serie = (await self.db.execute(
                    select(Series).where(Series.id == item.series_id))).scalar_one_or_none()
                titulo_serie = serie.title if serie else ""
                # B13: los alias que el coleccionista ya confirmó a mano. Un
                # release español puede llamar "La Patrulla-X" a una serie
                # catalogada como "X-Men"; sin ellos, la igualdad estricta
                # descartaría el candidato bueno.
                alias_serie = set((await self.db.execute(
                    select(LocalAlias.pattern_norm)
                    .where(LocalAlias.series_id == item.series_id))).scalars().all())
            antes = len(candidates)
            candidates = [c for c in candidates
                          if self._candidato_es_del_numero(c, item.numero, titulo_serie, alias_serie)]
            descartados_por_numero = antes - len(candidates)

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
            elif descartados_por_numero:
                item.last_error = MOTIVO_NUMERO_DISTINTO
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
        if item.status not in (WishlistStatus.WANTED, WishlistStatus.FAILED):
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
            # D8: un item generado por la política lleva el número en
            # `item.numero` y NO tiene `issue_id` (el número que no tienes no
            # tiene fila `Issue`). Sin esto, los N items generados harían la
            # MISMA consulta —solo el título— y podrían acabar enviando el mismo
            # candidato N veces.
            if item.numero is not None:
                q += f" {item.numero}"
            elif item.issue_id:
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

    # ── D8: generación y retirada, con un solo predicado ─────────────────────
    #
    # Son la misma operación vista desde dos lados: "deja la wishlist con
    # exactamente los números que la política quiere". Por eso comparten
    # `querer_de_serie` y se ejecutan en la misma pasada — separarlas dejaría
    # ventanas en las que un item generado ya no lo quiere nadie y sigue
    # buscándose.

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
        planes = [(serie, await self.querer_de_serie(serie))
                  for serie in await self._series_para_sincronizar()]
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
        return list((await self.db.execute(
            select(Series)
            .where(or_(
                Series.wishlist_policy.in_([WishlistPolicy.MISSING, WishlistPolicy.ALL]),
                Series.id.in_(pendientes),
            ))
            .order_by(Series.sort_title)
        )).scalars().all())

    async def querer_de_serie(self, series: Series) -> Querer:
        """«Números que la política de ESTA serie quiere ahora» — el predicado
        único de D8. Público a propósito: la ficha de serie de la UI tiene que
        enseñar lo mismo que se va a generar, no recalcularlo por su cuenta.

        Falla cerrado y declara: si no se puede calcular, `numeros` va vacío y
        `motivo` lo dice, en vez de inventar una lista (misma regla que
        `huecos_de_serie` en #13).
        """
        politica = series.wishlist_policy
        if politica == WishlistPolicy.NONE:
            return Querer(frozenset(), True)
        if politica == WishlistPolicy.FUTURE:
            return Querer(frozenset(), False, MOTIVO_POLITICA_FUTUROS)

        # Items manuales de esta serie que siguen vivos (un FAILED sigue
        # contando: está en la lista y se reintenta tras el cooldown).
        manuales = (await self.db.execute(
            select(Wishlist.issue_id, Wishlist.numero)
            .where(Wishlist.series_id == series.id)
            .where(Wishlist.origen == WishlistOrigin.MANUAL)
            .where(Wishlist.status.not_in(ESTADOS_TERMINADOS))
        )).all()

        # Un item manual a NIVEL DE SERIE pide la serie genérica: generar además
        # cada número la buscaría dos veces. Ojo al orden temporal — da igual
        # que el item manual sea anterior o posterior a los generados: el
        # predicado es declarativo y la retirada usa este mismo resultado.
        if any(issue_id is None and numero is None for issue_id, numero in manuales):
            return Querer(frozenset(), True, MOTIVO_SERIE_EN_CURSO)

        huecos = await huecos_de_serie(self.db, series)
        if not huecos.computable:
            return Querer(frozenset(), False, huecos.motivo)

        numeros = (frozenset(range(1, series.total_issues + 1))
                   if politica == WishlistPolicy.ALL else frozenset(huecos.faltantes))

        # Un item manual de un NÚMERO concreto ocupa ese número: generarlo
        # también sería la misma duplicación. El índice único parcial no cubre
        # los manuales (a propósito), así que la base no lo impide — hay que
        # excluirlo aquí.
        ocupados = {numero for _, numero in manuales if numero is not None}
        ids_issue = [issue_id for issue_id, _ in manuales if issue_id is not None]
        if ids_issue:
            for numero_issue, formato in (await self.db.execute(
                    select(Issue.issue_number, Issue.format)
                    .where(Issue.id.in_(ids_issue)))).all():
                if (n := numero_de_grapa(numero_issue, formato)) is not None:
                    ocupados.add(n)
        return Querer(numeros - ocupados, True)

    @staticmethod
    def _stmt_retirada(series_id, querer: Querer):
        """El `UPDATE` atómico que retira lo de política que ya no se quiere.

        Separado para poder fijar en un test el `WHERE` exacto: **solo**
        `WANTED`/`FAILED` (lo que no ha empezado) y **solo** `origen='politica'`
        (lo manual no se toca nunca).
        """
        stmt = (
            update(Wishlist)
            .where(Wishlist.series_id == series_id)
            .where(Wishlist.origen == WishlistOrigin.POLICY)
            .where(Wishlist.status.in_([WishlistStatus.WANTED, WishlistStatus.FAILED]))
            .values(status=WishlistStatus.RETIRADO, last_error=None)
        )
        if querer.numeros:
            # Sin números que quiera, se retira todo lo pendiente de esa serie.
            # Se evita `NOT IN ()` para no depender del renderizado de un IN
            # vacío.
            stmt = stmt.where(or_(
                Wishlist.numero.is_(None),
                Wishlist.numero.not_in(sorted(querer.numeros)),
            ))
        return stmt

    async def _retirar_lo_que_ya_no_se_quiere(
            self, planes: list[tuple[Series, Querer]]) -> int:
        """Marca `retirado` lo de origen `politica` que el predicado ya no pide.

        Un solo `UPDATE` por serie (**atómico**: una sentencia, sin leer y
        reescribir en Python) y **solo** sobre lo que no ha empezado.
        """
        retirados = 0
        for series, querer in planes:
            resultado = await self.db.execute(self._stmt_retirada(series.id, querer))
            retirados += resultado.rowcount or 0
        return retirados

    async def _generar_lo_que_falta(
            self, planes: list[tuple[Series, Querer]], lote: int) -> int:
        """Crea (o reactiva) los items de política que el predicado pide y aún
        no están materializados. Tope `lote` por ciclo, en rondas entre series.

        No basta con insertar: el índice único parcial no mira el estado, así
        que un número ya existente como `retirado`/`failed`/`imported` seguiría
        ocupando el hueco. `_materializar` usa `ON CONFLICT ... DO UPDATE` y
        reinicia `status`, `added_at`, `download_ref`, `download_backend` y
        `last_error` — reiniciar `added_at` no es cosmético, el cierre compara
        `File.imported_at >= Wishlist.added_at`.
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
                if existentes.get(numero) not in ESTADOS_YA_MATERIALIZADOS
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
        (`origen='politica' AND numero IS NOT NULL`) y que el `DO UPDATE` **no**
        pisa un item en vuelo.
        """
        return (
            pg_insert(Wishlist)
            .values(
                id=uuid4(),
                series_id=series_id,
                issue_id=None,
                status=WishlistStatus.WANTED,
                priority=5,
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
                },
                # Defensa contra dos ciclos solapados: entre el SELECT de
                # `_generar_lo_que_falta` y este INSERT, el otro ciclo puede
                # haber reclamado la fila (SEARCHING) o enviado la descarga
                # (DOWNLOADING). El upsert no puede pisar eso.
                where=Wishlist.status.not_in(ESTADOS_EN_VUELO),
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
