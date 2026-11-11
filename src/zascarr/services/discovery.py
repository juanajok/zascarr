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
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.anilist import AniListClient
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.detalle_edicion import (
    DetalleEdicion,
    ResultadoDetalle,
    detalle_desde_coleccion,
    detalle_desde_cv_volumen,
    detalle_desde_gcd_serie,
    detalle_desde_numero,
)
from zascarr.services.gcd import GCDClient, GCDSerie, es_edicion_espanola
from zascarr.services.identificadores import (
    Identificador,
    IdentificadorInvalidoError,
    ResolucionIdentificador,
    parsear_identificador,
)
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada
from zascarr.utils.peticiones import ReintentosAgotados, RespuestaNoTransitoria

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
    CAPACIDAD_DETALLE,
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


def _estado_detalle(fuente: MetadataSource, estado: str,
                    motivo: str | None = None) -> EstadoFuente:
    """Estado de la capacidad `detalle`; reutiliza el vocabulario de #133."""
    return EstadoFuente(fuente=fuente.value, capacidad=CAPACIDAD_DETALLE,
                        estado=estado, motivo=motivo)


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
    # Aditivo para #464: GCD puede devolver una edición sin país ni idioma. No se descarta
    # (podría ser española y GCD no lo informa); se conserva y se marca para que la UI y la
    # revisión humana sepan que el filtro de idioma no pudo aplicarse.
    idioma_no_informado: bool = False
    # Del D-A1/#129: Tebeosfera distingue colección de saga; el resto no lo informa.
    kind: str | None = None
    # Discriminantes que el cliente ya devuelve; None = «no consta».
    editorial: str | None = None
    pais: str | None = None
    idioma: str | None = None

    @property
    def procedencia(self) -> ProcedenciaTradicion | None:
        """La procedencia que se firma y se muestra: sin sugerencia no hay procedencia; con
        sugerencia y sin dato, el origen es desconocido (nunca se inventa una explicación)."""
        if self.tradition_guess is None:
            return None
        return self.tradition_provenance or ProcedenciaTradicion.DESCONOCIDA


def _editorial_desde_raw(raw: dict) -> str | None:
    """Nombre ya presente en el `raw` de búsqueda (nunca una URL)."""
    valor = raw.get("publisher_name")
    if not valor:
        publisher = raw.get("publisher")
        if isinstance(publisher, dict):
            valor = publisher.get("name")
        elif isinstance(publisher, str) and not publisher.startswith("http"):
            valor = publisher
    return str(valor).strip() if valor else None


def _clasificar_outcome(fuente: MetadataSource, nombre: str,
                        outcome: object) -> tuple[EstadoFuente, list[DiscoveryResult], list[str]]:
    """Clasifica el desenlace de UNA fuente con el vocabulario CERRADO de #133.

    Lo comparten `search_detallada` y `buscar_en` de #129 A: una sola definición de
    `limite_de_cortesia`/`fallo_transitorio`/`fuente_apagada`/etc., sin copiar el camino
    que se traga `CortesiaEnEspera`.
    """
    if isinstance(outcome, FuenteApagada):
        return _estado(fuente, FUENTE_APAGADA, "Está apagada en Ajustes."), [], []
    if isinstance(outcome, CortesiaEnEspera):
        reintentar = (max(1, int(outcome.espera_estimada_s + 0.999))
                      if outcome.espera_estimada_s > 0 else None)
        espera = f" ~{reintentar} s" if reintentar else ""
        estado = _estado(
            fuente, FUENTE_LIMITE_DE_CORTESIA,
            f"No se ha consultado: hay que esperar{espera} por cortesía. "
            "No se ha enviado nada; vuelve a intentarlo en un momento.", reintentar)
        return estado, [], [f"{nombre}: ha pedido esperar antes de volver a consultarla."]
    if isinstance(outcome, ReintentosAgotados) and outcome.ultimo_codigo == 429:
        estado = _estado(fuente, FUENTE_LIMITE_DE_CORTESIA,
                         "Ha pedido esperar antes de volver a consultarla.")
        return estado, [], [f"{nombre}: ha pedido esperar antes de volver a consultarla."]
    if (isinstance(outcome, RespuestaNoTransitoria)
            and outcome.codigo in (401, 403) and fuente is MetadataSource.COMIC_VINE):
        # H15: una clave inválida de CV es configuración, no un fallo transitorio.
        return _estado(fuente, FUENTE_CONFIGURACION_INCOMPLETA,
                       "La clave de Comic Vine no se ha aceptado."), [], []
    if isinstance(outcome, BaseException):
        logger.warning("discovery.source_failed", source=nombre, error=str(outcome))
        return (_estado(fuente, FUENTE_FALLO_TRANSITORIO, "No ha respondido ahora mismo."),
                [], [f"{nombre}: no se pudo consultar ahora mismo."])
    if outcome:
        return _estado(fuente, FUENTE_OK), list(outcome), []
    return (_estado(fuente, FUENTE_SIN_RESULTADOS,
                    "Ha respondido, pero no hay coincidencias."), [], [])


class DiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _slug_numero(resultado: DiscoveryResult) -> str | None:
        """Slug de número si el candidato lo declara; si no, `None` (sin inventar)."""
        external = (resultado.external_id or "").strip()
        site = (resultado.site_url or "").strip()
        if external.startswith("numero:"):
            return external.split(":", 1)[1].strip() or None
        if "/numeros/" in external:
            return external.split("/numeros/", 1)[1].split(".html", 1)[0].strip("/") or None
        if "/numeros/" in site:
            return site.split("/numeros/", 1)[1].split(".html", 1)[0].strip("/") or None
        return None

    async def detalle_de(self, resultado: DiscoveryResult, *,
                         unidad: str = "edicion",
                         numero_esperado: Any | None = None) -> ResultadoDetalle:
        """Pide la ficha de detalle del candidato, sin cambiar `DiscoveryResult`/`Busqueda`.

        Despacho por fuente: Tebeosfera `get_collection`; GCD `get_series` (+`get_publisher`
        solo para el nombre) o `raw` de búsqueda sin petición de serie; Comic Vine sin clave
        → `configuracion_incompleta` sin red (el método llega en PR-3); AniList no tiene
        método → `sin_metodo_autorizado`. Los estados son los de #133, capacidad `detalle`.
        """
        del unidad  # el contraste/la unidad se decide en el consumidor; aquí no cambia la petición
        fuente = resultado.source
        settings = get_settings()
        if not getattr(settings, _INTERRUPTOR[fuente], False):
            return ResultadoDetalle(_estado_detalle(
                fuente, FUENTE_APAGADA, "Está apagada en Ajustes."), None)
        if fuente is MetadataSource.COMIC_VINE and not settings.comicvine_api_key:
            return ResultadoDetalle(_estado_detalle(
                fuente, FUENTE_CONFIGURACION_INCOMPLETA,
                "Falta su clave en Ajustes."), None)
        if fuente is MetadataSource.ANILIST:
            return ResultadoDetalle(_estado_detalle(
                fuente, "sin_metodo_autorizado",
                "AniList no tiene detalle de edición."), None)
        try:
            if fuente is MetadataSource.COMIC_VINE:
                detalle = await self._detalle_cv(resultado)
                if detalle is None:
                    return ResultadoDetalle(_estado_detalle(
                        fuente, FUENTE_SIN_RESULTADOS,
                        "El volumen no existe en Comic Vine."), None)
            elif fuente is MetadataSource.TEBEOSFERA:
                slug_numero = self._slug_numero(resultado)
                async with TebeosferaClient() as cliente:
                    if slug_numero is not None:
                        numero = await cliente.get_numero(slug_numero)
                        if numero is None:
                            return ResultadoDetalle(_estado_detalle(
                                fuente, FUENTE_SIN_RESULTADOS,
                                "La ficha de número no existe."), None)
                        detalle = detalle_desde_numero(numero)
                    elif numero_esperado is not None:
                        numero = await cliente.get_numero_de_coleccion(
                            resultado.external_id, numero_esperado)
                        if numero is None:
                            return ResultadoDetalle(_estado_detalle(
                                fuente, FUENTE_SIN_RESULTADOS,
                                "No hay ficha de número para ese ejemplar."), None)
                        detalle = detalle_desde_numero(numero)
                    else:
                        coleccion = await cliente.get_collection(resultado.external_id)
                        if coleccion is None:
                            return ResultadoDetalle(_estado_detalle(
                                fuente, FUENTE_SIN_RESULTADOS,
                                "La ficha no existe o no es de colección."), None)
                        detalle = detalle_desde_coleccion(coleccion)
            elif fuente is MetadataSource.GCD:
                detalle = await self._detalle_gcd(resultado)
                if detalle is None:
                    return ResultadoDetalle(_estado_detalle(
                        fuente, FUENTE_SIN_RESULTADOS, "La serie no existe."), None)
            else:
                return ResultadoDetalle(_estado_detalle(
                    fuente, "sin_metodo_autorizado", "Sin método de detalle."), None)
        except FuenteApagada:
            return ResultadoDetalle(_estado_detalle(
                fuente, FUENTE_APAGADA, "Está apagada en Ajustes."), None)
        except CortesiaEnEspera as exc:
            reintentar = (max(1, int(exc.espera_estimada_s + 0.999))
                          if exc.espera_estimada_s > 0 else None)
            estado = _estado_detalle(
                fuente, FUENTE_LIMITE_DE_CORTESIA,
                "Hay que esperar por cortesía antes de volver a pedir la ficha.")
            estado = EstadoFuente(estado.fuente, estado.capacidad, estado.estado,
                                  estado.motivo, reintentar)
            return ResultadoDetalle(estado, None)
        except ReintentosAgotados as exc:
            estado = (FUENTE_LIMITE_DE_CORTESIA if exc.ultimo_codigo == 429
                      else FUENTE_FALLO_TRANSITORIO)
            motivo = ("Ha pedido esperar antes de volver a consultarla."
                      if estado == FUENTE_LIMITE_DE_CORTESIA
                      else "No ha respondido ahora mismo.")
            return ResultadoDetalle(_estado_detalle(fuente, estado, motivo), None)
        except Exception as exc:  # noqa: BLE001 — red/parseo: estado #133, nunca traceback
            logger.warning("discovery.detalle_failed", source=fuente.value,
                           error=type(exc).__name__)
            return ResultadoDetalle(_estado_detalle(
                fuente, FUENTE_FALLO_TRANSITORIO, "No se pudo leer la ficha."), None)
        return ResultadoDetalle(_estado_detalle(fuente, FUENTE_OK), detalle)

    async def _detalle_cv(self, resultado: DiscoveryResult) -> DetalleEdicion | None:
        """Comic Vine: `get_volume` (1 petición) → detalle; sin clave no se llama."""
        try:
            volume_id = int(resultado.external_id)
        except (TypeError, ValueError):
            return None
        async with ComicVineClient() as cliente:
            volumen = await cliente.get_volume(volume_id)
        if volumen is None:
            return None
        return detalle_desde_cv_volumen(volumen)

    async def _detalle_gcd(self, resultado: DiscoveryResult) -> DetalleEdicion | None:
        """GCD: usa `raw` de búsqueda si existe (0 peticiones de serie); si no, get_series."""
        raw = getattr(resultado, "raw", None)
        if isinstance(raw, dict) and raw:
            try:
                gcd_id = int(resultado.external_id)
            except (TypeError, ValueError):
                return None
            serie = GCDSerie.desde_raw(raw, gcd_id)
            editorial = _editorial_desde_raw(raw)
            peticiones = 0
            if editorial is None and serie.publisher:
                # La búsqueda trae la editorial como URL; el nombre exige 1 petición.
                peticiones = 1
                try:
                    async with GCDClient() as cliente:
                        editorial = await cliente.get_publisher(serie.publisher)
                except Exception:  # noqa: BLE001 — sin editorial el contraste sigue ambiguo
                    logger.warning("discovery.gcd_publisher_failed")
                    editorial = None
            return detalle_desde_gcd_serie(
                serie, editorial=editorial, peticiones=peticiones, metodo="raw")
        try:
            gcd_id = int(resultado.external_id)
        except (TypeError, ValueError):
            return None
        async with GCDClient() as cliente:
            serie = await cliente.get_series(gcd_id)
            if serie is None:
                return None
            editorial = await cliente.get_publisher(serie.publisher) if serie.publisher else None
        peticiones = serie.peticiones + (1 if serie.publisher else 0)
        return detalle_desde_gcd_serie(serie, editorial=editorial,
                                       peticiones=peticiones, metodo="get_series")

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
            estado, encontrados, avisos_fuente = _clasificar_outcome(fuente, nombre, outcome)
            detalles[fuente.value] = estado
            results.extend(encontrados)
            avisos.extend(avisos_fuente)
        estados = {nombre: detalle.estado for nombre, detalle in detalles.items()}
        return Busqueda(results, avisos, estados, detalles)

    async def resolver_identificador(self, texto: str) -> ResolucionIdentificador:
        """BL-R5 (#234): resuelve por id exacto ANTES que por título.

        Valida la forma sin red; consulta solo la fuente del identificador y solo al
        pedirlo. Un error de la fuente se devuelve como estado de #133, nunca como
        «no existe». Si la serie ya está en la biblioteca, no se consulta la fuente.
        """
        try:
            ident = parsear_identificador(texto)
        except IdentificadorInvalidoError as exc:
            return ResolucionIdentificador(camino="invalido", motivo=str(exc))

        local = await self._serie_local_por_identificador(ident)
        if local is not None:
            return ResolucionIdentificador(
                camino="ya_local", identificador=ident, ya_local=local,
                motivo="Esa serie ya está en tu biblioteca.")

        fuente = ident.fuente
        settings = get_settings()
        nombre = fuente.value
        if not getattr(settings, _INTERRUPTOR[fuente]):
            return ResolucionIdentificador(
                camino="error", identificador=ident,
                estado=_estado_detalle(fuente, FUENTE_APAGADA, "Está apagada en Ajustes."),
                motivo="Esa fuente está apagada en Ajustes.")
        if fuente is MetadataSource.COMIC_VINE and not settings.comicvine_api_key:
            return ResolucionIdentificador(
                camino="error", identificador=ident,
                estado=_estado_detalle(
                    fuente, FUENTE_CONFIGURACION_INCOMPLETA,
                    "Falta su clave en Ajustes."),
                motivo="Comic Vine no está configurado: añade su clave en Ajustes.")
        if fuente is MetadataSource.ANILIST:
            return ResolucionIdentificador(
                camino="error", identificador=ident,
                estado=EstadoFuente(
                    fuente=fuente.value, capacidad=CAPACIDAD_DETALLE,
                    estado="sin_metodo_autorizado",
                    motivo="AniList no permite resolver una serie por identificador; "
                           "búscala por título."),
                motivo="AniList no permite resolver por identificador; búscala por título.")

        detalle = None
        try:
            if fuente is MetadataSource.COMIC_VINE:
                detalle = await ComicVineClient().get_volume(int(ident.valor))
            elif fuente is MetadataSource.GCD:
                detalle = await GCDClient().get_series(int(ident.valor))
            elif fuente is MetadataSource.TEBEOSFERA:
                detalle = await TebeosferaClient().get_collection(ident.valor)
        except Exception as exc:  # noqa: BLE001 — #133 clasifica, nunca «no existe»
            estado, _r, _a = _clasificar_outcome(fuente, nombre, exc)
            estado = _estado_detalle(fuente, estado.estado, estado.motivo)
            return ResolucionIdentificador(
                camino="error", identificador=ident, estado=estado, motivo=estado.motivo)

        if detalle is None:
            estado = _estado_detalle(
                fuente, FUENTE_SIN_RESULTADOS,
                "La fuente ha respondido, pero ese identificador no existe.")
            return ResolucionIdentificador(
                camino="sin_resultado", identificador=ident, estado=estado,
                motivo="Ese identificador no existe en la fuente.")

        resultado = self._resultado_desde_identificador(ident, detalle)
        return ResolucionIdentificador(
            camino="identificador", identificador=ident, resultado=resultado,
            estado=_estado_detalle(fuente, FUENTE_OK),
            motivo=f"Encontrada por identificador en {nombre}.")

    async def _serie_local_por_identificador(self, ident: Identificador) -> Series | None:
        columna = CAMPO_ID_EXTERNO[ident.fuente]
        valor: object = int(ident.valor) if columna != "tebeosfera_slug" else ident.valor
        return (await self.db.execute(
            select(Series).where(getattr(Series, columna) == valor)
        )).scalar_one_or_none()

    @staticmethod
    def _resultado_desde_identificador(ident: Identificador, detalle: object) -> DiscoveryResult:
        """Convierte la ficha de la fuente en un candidato firmable (sin inventar campos)."""
        fuente = ident.fuente
        if fuente is MetadataSource.COMIC_VINE:
            raw = getattr(detalle, "raw", None) or {}
            imagen = raw.get("image") if isinstance(raw.get("image"), dict) else {}
            return DiscoveryResult(
                source=fuente, external_id=str(getattr(detalle, "cv_id", ident.valor)),
                title=str(getattr(detalle, "name", "") or f"Volumen {ident.valor}"),
                start_year=getattr(detalle, "start_year", None),
                description=raw.get("description"),
                cover_url=(imagen.get("medium_url") or imagen.get("small_url")
                           or imagen.get("original_url")),
                site_url=(raw.get("site_detail_url")
                          or f"https://comicvine.gamespot.com/volume/4050-{ident.valor}/"),
                tradition_guess=ComicTradition.AMERICAN,
                tradition_provenance=ProcedenciaTradicion.POR_DEFECTO,
                editorial=getattr(detalle, "publisher", None),
            )
        if fuente is MetadataSource.GCD:
            return DiscoveryResult(
                source=fuente, external_id=str(getattr(detalle, "gcd_id", ident.valor)),
                title=str(getattr(detalle, "name", "") or f"Serie {ident.valor}"),
                start_year=getattr(detalle, "year_began", None),
                description=None, cover_url=None,
                site_url=f"https://www.comics.org/series/{ident.valor}/",
            )
        titulo = getattr(detalle, "titulo", None) or ident.valor.replace("-", " ")
        return DiscoveryResult(
            source=fuente, external_id=str(getattr(detalle, "slug", ident.valor)),
            title=str(titulo), start_year=getattr(detalle, "anio", None),
            description=None, cover_url=None,
            site_url=getattr(detalle, "url_ficha", None),
            tradition_guess=ComicTradition.TEBEO,
            tradition_provenance=ProcedenciaTradicion.POR_DEFECTO,
            kind="collection",
        )

    async def buscar_en(self, fuente: MetadataSource, query: str,
                        limit: int = 10) -> Busqueda:
        """Consulta UNA sola fuente (capacidad `busqueda`) reutilizando #133.

        A de #129 no consulta «por si acaso» las demás. Fuente apagada o CV sin clave
        no instancian cliente. La clasificación de errores/cortesía es la misma que en
        `search_detallada` (ayudante compartido).
        """
        query = (query or "").strip()
        settings = get_settings()
        if not getattr(settings, _INTERRUPTOR[fuente]):
            detalle = _estado(fuente, FUENTE_APAGADA, "Está apagada en Ajustes.")
            return Busqueda([], [], {fuente.value: detalle.estado}, {fuente.value: detalle})
        if fuente is MetadataSource.COMIC_VINE and not settings.comicvine_api_key:
            detalle = _estado(fuente, FUENTE_CONFIGURACION_INCOMPLETA,
                              "Falta su clave en Ajustes.")
            return Busqueda([], [], {fuente.value: detalle.estado}, {fuente.value: detalle})
        if not query:
            detalle = _estado(fuente, FUENTE_SIN_RESULTADOS,
                              "No se ha consultado: no hay consulta que buscar.")
            return Busqueda([], [], {fuente.value: detalle.estado}, {fuente.value: detalle})
        nombre = fuente.value
        constructores = {
            MetadataSource.COMIC_VINE: self._search_comic_vine,
            MetadataSource.ANILIST: self._search_anilist,
            MetadataSource.TEBEOSFERA: self._search_tebeosfera,
            MetadataSource.GCD: self._search_gcd,
        }
        try:
            outcome = await constructores[fuente](query, limit)
        except Exception as exc:  # noqa: BLE001 — se clasifica con #133, sin tumbar la UI
            outcome = exc
        estado, encontrados, avisos = _clasificar_outcome(fuente, nombre, outcome)
        return Busqueda(encontrados, avisos, {fuente.value: estado.estado},
                        {fuente.value: estado})

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
                kind=h.kind,
            )
            for h in hits
        ]

    async def _search_gcd(self, query: str, limit: int) -> list[DiscoveryResult]:
        async with GCDClient() as client:
            hits = await client.search_series(query, limit=limit)
        resultados: list[DiscoveryResult] = []
        for h in hits:
            clasificacion = es_edicion_espanola(h)
            if clasificacion is False:
                # Edición con país/idioma informado y no español: no entra como candidata.
                continue
            resultados.append(DiscoveryResult(
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
                # Sin país ni idioma no se descarta: se conserva y se marca (#464).
                idioma_no_informado=clasificacion is None,
                pais=h.country, idioma=h.language,
            ))
        return resultados

