"""
DiscoveryService — C0: buscar series en fuentes externas.

La BÚSQUEDA vive aquí; el ALTA de la serie la hace `AltaDeSerie` (I2 de #114: ya no hay
una creación directa paralela, `get_or_create_series` se retiró).

Cierra el círculo vicioso confirmado en producción: Wishlist
(WishlistService.search_series) y el matcher (core/matcher.py) SOLO
trabajan contra `Series` que YA existen en la BD local — en una
instalación nueva (tabla `series` vacía) no hay nada que buscar ni con
qué emparejar un archivo bien nombrado. Este servicio es el paso de
búsqueda del alta: busca en las mismas fuentes que ya usa el enricher
(Comic Vine, AniList, Tebeosfera) — las REUTILIZA para buscar, nunca las
toca para nada de descarga — y ofrece los resultados con los que se da de
alta la `Series` local que el resto del sistema necesita para funcionar.

Un fallo de una fuente (sin API key, sitio caído, rate limit agotado) no
tumba la búsqueda entera: se registra y se sigue con las demás — mismo
criterio de tolerancia a fallos que enricher.py.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import StrEnum

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.gcd import GCDClient
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada
from zascarr.utils.peticiones import ReintentosAgotados

logger = structlog.get_logger()

# Traducción fuente → columna de identidad externa en Series. Cada serie
# solo lleva UNA de las cuatro (igual que en enricher.py): la que
# corresponde a la fuente donde se encontró.
CAMPO_ID_EXTERNO: dict[MetadataSource, str] = {
    MetadataSource.COMIC_VINE: "comic_vine_id",
    MetadataSource.ANILIST: "anilist_id",
    MetadataSource.TEBEOSFERA: "tebeosfera_slug",
    MetadataSource.GCD: "gcd_id",
}
CAMPOS_ID_DE_TEXTO = {"tebeosfera_slug"}

#: Orden FIJO y neutro de las fuentes en cualquier listado (nunca «la mejor primero»).
ORDEN_DE_FUENTES: tuple[MetadataSource, ...] = (
    MetadataSource.COMIC_VINE, MetadataSource.ANILIST,
    MetadataSource.TEBEOSFERA, MetadataSource.GCD,
)

# #133: el conjunto cerrado y `EstadoFuente` viven en un módulo stdlib-only para que las
# herramientas sin red (banco de cobertura, #135) los reutilicen sin cargar los clientes. Aquí se
# reexportan: el contrato público de `discovery` no cambia.
from zascarr.services.estados_fuentes import (  # noqa: E402,F401 — reexportados
    CAPACIDAD_BUSQUEDA,
    ESTADOS_DE_FUENTE,
    FUENTE_APAGADA,
    FUENTE_CONFIGURACION_INCOMPLETA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_LIMITE_DE_CORTESIA,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
    EstadoFuente,
)

#: Metadatos de cada fuente que no están en `MetadataSource`: su interruptor de Ajustes.
_INTERRUPTOR = {
    MetadataSource.COMIC_VINE: "comicvine_enabled",
    MetadataSource.ANILIST: "anilist_enabled",
    MetadataSource.TEBEOSFERA: "tebeosfera_enabled",
    MetadataSource.GCD: "gcd_enabled",
}


def _estado(fuente: MetadataSource, estado: str, motivo: str | None = None,
            reintentar_en: int | None = None) -> EstadoFuente:
    return EstadoFuente(fuente=fuente.value, capacidad=CAPACIDAD_BUSQUEDA, estado=estado,
                        motivo=motivo, reintentar_en=reintentar_en)


@dataclass
class Busqueda:
    """Una búsqueda: los candidatos, los avisos en español y el estado de CADA fuente.

    `fuentes` (fuente → estado) se conserva por compatibilidad con los consumidores que ya lo
    leían; `detalles` añade capacidad, motivo y reintento por fuente. Las búsquedas construidas
    a mano en pruebas pueden dar solo `fuentes`: `__post_init__` completa los detalles que falten
    sin inventar motivo ni plazo.
    """
    resultados: list[DiscoveryResult]
    avisos: list[str]
    fuentes: dict[str, str]
    detalles: dict[str, EstadoFuente] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for fuente in ORDEN_DE_FUENTES:
            nombre = fuente.value
            if nombre in self.fuentes and nombre not in self.detalles:
                self.detalles[nombre] = _estado(fuente, self.fuentes[nombre])


class ProcedenciaTradicion(StrEnum):
    """De dónde sale la tradición que sugiere una fuente.

    No dice si la sugerencia es correcta: solo permite presentarla como lo que es. `EXPLICITA`
    cuando la fuente declara la tradición (AniList solo indexa manga), `TRANSFORMADA` cuando se
    deduce de otro dato suyo (GCD da idioma/país), `POR_DEFECTO` cuando la fuente no la da y el
    producto aplica un valor de partida, y `DESCONOCIDA` cuando hay sugerencia pero no consta su
    origen (también para tokens anteriores a este contrato).
    """
    EXPLICITA = "explicita"
    TRANSFORMADA = "transformada"
    POR_DEFECTO = "por_defecto"
    DESCONOCIDA = "desconocida"


@dataclass
class DiscoveryResult:
    source: MetadataSource
    external_id: str  # texto siempre: unifica el int de CV/AniList y el slug de Tebeosfera
    title: str
    start_year: int | None
    description: str | None
    cover_url: str | None
    # Enlace a la ficha real en la fuente (bug real, reportado: sin esto no
    # hay forma de confirmar CUÁL de varias ediciones/resultados similares
    # es la correcta antes de darla de alta — un "Thorgal" en Tebeosfera
    # son 10 ediciones españolas distintas, cada una con su propia ficha).
    site_url: str | None
    # Punto de partida editable en el formulario de alta, NO una asignación
    # definitiva: Comic Vine también indexa BRITISH, Tebeosfera también
    # indexa FRANCO_BELGIAN. El coleccionista corrige antes de confirmar.
    # Puede faltar: una fuente puede no sugerir ninguna tradición (CA6 de #202).
    tradition_guess: ComicTradition | None = None
    # Solo tiene sentido si hay sugerencia. Si falta con una sugerencia, se trata como
    # `DESCONOCIDA`; es lo que ocurre con los tokens emitidos antes de #276, que no llevaban
    # procedencia.
    tradition_provenance: ProcedenciaTradicion | None = None

    @property
    def procedencia(self) -> ProcedenciaTradicion | None:
        """La procedencia que se firma y se muestra: sin sugerencia no hay procedencia; con
        sugerencia y sin dato, el origen es desconocido (nunca se inventa una explicación)."""
        if self.tradition_guess is None:
            return None
        return self.tradition_provenance or ProcedenciaTradicion.DESCONOCIDA


class DiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(self, query: str, limit: int = 10) -> tuple[list[DiscoveryResult], list[str]]:
        """Devuelve (resultados, avisos). Los avisos son texto en español
        listo para mostrar — bug real reportado: sin esto, "Comic Vine no
        devuelve nada" era indistinguible de "no está configurado" (sin
        COMICVINE_API_KEY), y el coleccionista no tenía forma de saberlo."""
        b = await self.search_detallada(query, limit)
        return b.resultados, b.avisos

    async def search_detallada(self, query: str, limit: int = 10) -> Busqueda:
        """Como `search`, pero además dice en qué estado quedó CADA fuente y capacidad (#133).

        Estados del conjunto cerrado (`ESTADOS_DE_FUENTE`): `ok`, `sin_resultados`,
        `fallo_transitorio`, `configuracion_incompleta`, `limite_de_cortesia` y
        `fuente_apagada`. Una fuente apagada o sin configurar NO se instancia ni se consulta; una
        que falla o limita no tumba a las demás. El motivo lo escribe el servicio, no la
        interfaz, y el reintento solo aparece si la fuente lo indicó.
        """
        query = query.strip()
        if not query:
            # Sin consulta no se ha consultado ninguna fuente: no se inventa otro estado.
            motivo = "No se ha consultado: no hay consulta que buscar."
            detalles = {f.value: _estado(f, FUENTE_APAGADA, motivo) for f in ORDEN_DE_FUENTES}
            return Busqueda([], [], {f.value: FUENTE_APAGADA for f in ORDEN_DE_FUENTES}, detalles)

        avisos: list[str] = []
        settings = get_settings()
        detalles: dict[str, EstadoFuente] = {}

        for fuente in ORDEN_DE_FUENTES:
            if not getattr(settings, _INTERRUPTOR[fuente]):
                detalles[fuente.value] = _estado(fuente, FUENTE_APAGADA, "Está apagada en Ajustes.")

        if settings.comicvine_enabled and not settings.comicvine_api_key:
            avisos.append(
                "Comic Vine no está configurado: añade su clave en Ajustes "
                "para incluirlo en la búsqueda.")
            detalles[MetadataSource.COMIC_VINE.value] = _estado(
                MetadataSource.COMIC_VINE, FUENTE_CONFIGURACION_INCOMPLETA,
                "Falta su clave en Ajustes.")

        # B8: «fuente apagada» vale en TODA ZascArr, también en Descubrir — una
        # fuente desactivada no se instancia ni consulta, las demás sí. Lo mismo con
        # una fuente que necesita clave y no la tiene: no se hace tráfico para nada.
        fuentes: list[tuple[MetadataSource, str, object]] = []
        if settings.comicvine_enabled and settings.comicvine_api_key:
            fuentes.append(
                (MetadataSource.COMIC_VINE, "Comic Vine", self._search_comic_vine(query, limit)))
        if settings.anilist_enabled:
            fuentes.append((MetadataSource.ANILIST, "AniList", self._search_anilist(query, limit)))
        if settings.tebeosfera_enabled:
            fuentes.append(
                (MetadataSource.TEBEOSFERA, "Tebeosfera", self._search_tebeosfera(query, limit)))
        if settings.gcd_enabled:
            fuentes.append((MetadataSource.GCD, "GCD", self._search_gcd(query, limit)))

        outcomes = await asyncio.gather(*(coro for _, _, coro in fuentes), return_exceptions=True)

        results: list[DiscoveryResult] = []
        for (fuente, nombre, _), outcome in zip(fuentes, outcomes, strict=True):
            if isinstance(outcome, FuenteApagada):
                # #134 puede lanzarlo si el ajuste cambia entre la comprobación y la petición.
                detalles[fuente.value] = _estado(
                    fuente, FUENTE_APAGADA, "Está apagada en Ajustes.")
                continue
            if isinstance(outcome, CortesiaEnEspera):
                # La fuente pidió esperar y la espera no cabía en el presupuesto: es cortesía,
                # no un fallo. El plazo solo va si el contrato lo trae.
                reintentar = (max(1, int(outcome.espera_estimada_s + 0.999))
                              if outcome.espera_estimada_s > 0 else None)
                # #134 §6.5: el motivo es el aviso de espera por cortesía, con estimación si consta.
                # El estado sigue siendo el del conjunto cerrado de #133 (`limite_de_cortesia`).
                espera = f" ~{reintentar} s" if reintentar else ""
                detalles[fuente.value] = _estado(
                    fuente, FUENTE_LIMITE_DE_CORTESIA,
                    f"No se ha consultado: hay que esperar{espera} por cortesía. "
                    "No se ha enviado nada; vuelve a intentarlo en un momento.", reintentar)
                avisos.append(f"{nombre}: ha pedido esperar antes de volver a consultarla.")
                continue
            if isinstance(outcome, ReintentosAgotados) and outcome.ultimo_codigo == 429:
                # 429 tras agotar reintentos: tampoco es un fallo transitorio.
                detalles[fuente.value] = _estado(
                    fuente, FUENTE_LIMITE_DE_CORTESIA,
                    "Ha pedido esperar antes de volver a consultarla.")
                avisos.append(f"{nombre}: ha pedido esperar antes de volver a consultarla.")
                continue
            if isinstance(outcome, BaseException):
                logger.warning("discovery.source_failed", source=nombre, error=str(outcome))
                avisos.append(f"{nombre}: no se pudo consultar ahora mismo.")
                detalles[fuente.value] = _estado(
                    fuente, FUENTE_FALLO_TRANSITORIO, "No ha respondido ahora mismo.")
                continue
            if outcome:
                detalles[fuente.value] = _estado(fuente, FUENTE_OK)
                results.extend(outcome)
            else:
                detalles[fuente.value] = _estado(
                    fuente, FUENTE_SIN_RESULTADOS, "Ha respondido, pero no hay coincidencias.")
        estados = {nombre: detalle.estado for nombre, detalle in detalles.items()}
        return Busqueda(results, avisos, estados, detalles)

    async def _search_comic_vine(self, query: str, limit: int) -> list[DiscoveryResult]:
        # Sin API key, la petición está condenada (401) — no la intentamos.
        if not get_settings().comicvine_api_key:
            return []
        async with ComicVineClient() as client:
            hits = await client.search_series(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.COMIC_VINE, external_id=str(h.cv_id),
                title=h.name, start_year=h.start_year, description=h.description,
                cover_url=h.image_url, site_url=h.site_url,
                tradition_guess=ComicTradition.AMERICAN,
                # Comic Vine no devuelve una tradición: es el valor de partida del producto.
                tradition_provenance=ProcedenciaTradicion.POR_DEFECTO,
            )
            for h in hits
        ]

    async def _search_anilist(self, query: str, limit: int) -> list[DiscoveryResult]:
        async with AniListClient() as client:
            hits = await client.search_manga(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.ANILIST, external_id=str(h.anilist_id),
                title=h.title_romaji or h.title_english or "?",
                start_year=h.start_year, description=h.description,
                cover_url=h.cover_url, site_url=h.site_url,
                # AniList solo indexa manga: la propia fuente declara el tipo al buscarlo.
                tradition_guess=ComicTradition.MANGA,
                tradition_provenance=ProcedenciaTradicion.EXPLICITA,
            )
            for h in hits
        ]

    async def _search_tebeosfera(self, query: str, limit: int) -> list[DiscoveryResult]:
        async with TebeosferaClient() as client:
            hits = await client.search_series(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.TEBEOSFERA, external_id=h.slug,
                title=h.title, start_year=h.start_year, description=h.description,
                cover_url=h.cover_url, site_url=h.site_url,
                # Tebeosfera es una base de tebeo español, pero el resultado no trae una tradición
                # por ficha.
                tradition_guess=ComicTradition.TEBEO,
                tradition_provenance=ProcedenciaTradicion.POR_DEFECTO,
            )
            for h in hits
        ]

    async def _search_gcd(self, query: str, limit: int) -> list[DiscoveryResult]:
        async with GCDClient() as client:
            hits = await client.search_series(query, limit=limit)
        return [
            DiscoveryResult(
                source=MetadataSource.GCD, external_id=str(h.gcd_id),
                title=h.name, start_year=h.year_began,
                # El endpoint de BÚSQUEDA de GCD no devuelve sinopsis ni
                # portada a nivel de serie. La web de GCD sí muestra una
                # portada de serie; si la API expone una URL de imagen
                # aprovechable está pendiente de evaluar (ver BACKLOG E7).
                description=None, cover_url=None, site_url=h.site_url,
                # GCD indexa por idioma/país; la tradición se deduce de ese dato, no viene como
                # tal. Si no reconoce ninguno, no hay sugerencia (CA6): `None`, no `other`.
                tradition_guess=(None if h.tradition_guess is None
                                 else ComicTradition(h.tradition_guess)),
                tradition_provenance=(None if h.tradition_guess is None
                                      else ProcedenciaTradicion.TRANSFORMADA),
            )
            for h in hits
        ]

