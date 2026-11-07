"""Detalle de edición BL-FU2 (#465), PR-1: Tebeosfera y contraste.

Resultado **en memoria** para comparar un candidato con una etiqueta acreditada. No
persiste, no escribe Series/Issue/Publisher y no añade rutas de UI. La ficha de
colección de Tebeosfera es el único método de este PR; CV/GCD entran en PR-2/PR-3.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

import structlog
from httpx import HTTPError

from zascarr.models import IssueFormat, MetadataSource
from zascarr.services.estados_fuentes import (
    CAPACIDAD_DETALLE,
    FUENTE_APAGADA,
    FUENTE_CONFIGURACION_INCOMPLETA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_LIMITE_DE_CORTESIA,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
    EstadoFuente,
)
from zascarr.services.tebeosfera import TebeosferaClient, TebeosferaColeccion
from zascarr.utils.cortesia import fuente_habilitada
from zascarr.utils.peticiones import (
    CortesiaEnEspera,
    ErrorDePeticion,
    FuenteApagada,
    ReintentosAgotados,
)

logger = structlog.get_logger()

CAPACIDAD = CAPACIDAD_DETALLE
METODO_TEBEOSFERA = "tebeosfera.get_collection"
SUGERENCIA_AUSENTE = "no consta en la fuente"

#: Campos normalizados que el detalle declara explícitamente si faltan.
CAMPOS_DETALLE = (
    "editorial", "sello", "anio", "anio_fin", "numeracion_inicio", "numeracion_fin",
    "numeracion_texto", "numero_publicacion", "paginas", "formato", "pais", "idioma",
)

_FORMATO_MAP = {
    "cuaderno / grapa": IssueFormat.SINGLE_ISSUE,
    "grapa": IssueFormat.SINGLE_ISSUE,
    "cartone": IssueFormat.HARDCOVER,
    "cartoné": IssueFormat.HARDCOVER,
    "album": IssueFormat.ALBUM,
    "álbum": IssueFormat.ALBUM,
}


@dataclass(frozen=True)
class DetalleEdicion:
    fuente: MetadataSource
    external_id: str
    metodo: str
    editorial: str | None = None
    sello: str | None = None
    anio: int | None = None
    anio_fin: int | None = None
    numeracion_inicio: int | None = None
    numeracion_fin: int | None = None
    numeracion_texto: str | None = None
    numero_publicacion: str | None = None
    paginas: int | None = None
    formato: IssueFormat | None = None
    formato_fuente: str | None = None
    pais: str | None = None
    idioma: str | None = None
    campos_ausentes: frozenset[str] = frozenset()
    peticiones: int = 0
    url_ficha: str | None = None


@dataclass(frozen=True)
class ResultadoDetalle:
    estado: EstadoFuente
    detalle: DetalleEdicion | None
    motivo: str | None = None


@dataclass(frozen=True)
class Contraste:
    resultado: str | None
    campos_requeridos: tuple[str, ...] = ()
    campos_ausentes: tuple[str, ...] = ()
    motivos: tuple[str, ...] = ()


def _campo(etiqueta: Any, nombre: str, defecto=None):
    if isinstance(etiqueta, dict):
        return etiqueta.get(nombre, defecto)
    return getattr(etiqueta, nombre, defecto)


def _normalizar_texto(valor: str | None) -> str:
    if not valor:
        return ""
    texto = unicodedata.normalize("NFKD", valor)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^a-z0-9]+", " ", texto.lower()).strip()
    return " ".join(texto.split())


def _normalizar_editorial(valor: str | None) -> str:
    return _normalizar_texto(valor)


def _normalizar_numero(valor: Any) -> str:
    if valor is None:
        return ""
    texto = str(valor).strip().lower()
    if texto.isdigit():
        return str(int(texto))
    return _normalizar_texto(texto)


def _normalizar_pais(valor: str | None) -> str | None:
    if not valor:
        return None
    limpio = _normalizar_texto(valor)
    if limpio in ("es", "espana", "spain"):
        return "ES"
    return limpio.upper() if len(limpio) <= 3 else limpio


def _normalizar_idioma(valor: str | None) -> str | None:
    if not valor:
        return None
    limpio = _normalizar_texto(valor)
    if limpio in ("es", "espanol", "spanish"):
        return "es"
    return limpio[:3] if len(limpio) > 2 else limpio


def _formato(texto: str | None) -> IssueFormat | None:
    if not texto:
        return None
    limpio = _normalizar_texto(texto)
    for clave, valor in _FORMATO_MAP.items():
        if limpio == _normalizar_texto(clave):
            return valor
    if "grapa" in limpio or "cuaderno" in limpio:
        return IssueFormat.SINGLE_ISSUE
    if "cartone" in limpio:
        return IssueFormat.HARDCOVER
    if "album" in limpio:
        return IssueFormat.ALBUM
    return None


def _campos_ausentes(detalle: DetalleEdicion) -> frozenset[str]:
    return frozenset(
        campo for campo in CAMPOS_DETALLE
        if getattr(detalle, campo, None) is None
    )


def _desde_tebeosfera(coleccion: TebeosferaColeccion) -> DetalleEdicion:
    formato = _formato(coleccion.formato_fuente)
    base = DetalleEdicion(
        fuente=MetadataSource.TEBEOSFERA,
        external_id=coleccion.slug,
        metodo=METODO_TEBEOSFERA,
        editorial=coleccion.editorial,
        sello=coleccion.sello,
        anio=coleccion.anio,
        anio_fin=coleccion.anio_fin,
        numeracion_inicio=coleccion.numeracion_inicio,
        numeracion_fin=coleccion.numeracion_fin,
        numeracion_texto=coleccion.numeracion_texto,
        # La ficha de colección acredita el rango, no el ejemplar concreto.
        numero_publicacion=None,
        paginas=coleccion.paginas,
        formato=formato,
        formato_fuente=coleccion.formato_fuente,
        pais=coleccion.pais,
        idioma=None,
        peticiones=coleccion.peticiones,
        url_ficha=coleccion.url_ficha,
    )
    return DetalleEdicion(**{**base.__dict__, "campos_ausentes": _campos_ausentes(base)})


class DetalleEdicionService:
    """Pide y normaliza el detalle de una edición; no escribe en la base."""

    async def detalle_tebeosfera(
        self, slug: str, *, cliente: TebeosferaClient | None = None,
    ) -> ResultadoDetalle:
        if not fuente_habilitada("tebeosfera"):
            return ResultadoDetalle(
                EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_APAGADA,
                             "Tebeosfera está desactivada en Ajustes."), None)
        if not slug:
            return ResultadoDetalle(
                EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_CONFIGURACION_INCOMPLETA,
                             "No se indicó la ficha de la colección."), None)

        async def _pedir(c: TebeosferaClient) -> TebeosferaColeccion | None:
            return await c.get_collection(slug)

        try:
            if cliente is None:
                async with TebeosferaClient() as c:
                    coleccion = await _pedir(c)
            else:
                coleccion = await _pedir(cliente)
        except FuenteApagada:
            return ResultadoDetalle(
                EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_APAGADA,
                             "Tebeosfera está desactivada en Ajustes."), None)
        except CortesiaEnEspera as exc:
            return ResultadoDetalle(
                EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_LIMITE_DE_CORTESIA,
                             f"Hay que esperar para consultar Tebeosfera ({exc.motivo})."), None)
        except ReintentosAgotados as exc:
            if exc.ultimo_codigo == 429:
                return ResultadoDetalle(
                    EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_LIMITE_DE_CORTESIA,
                                 "Tebeosfera pidió esperar antes de otra consulta."), None)
            return ResultadoDetalle(
                EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_FALLO_TRANSITORIO,
                             "No se pudo consultar Tebeosfera; vuelve a intentarlo."), None)
        except (HTTPError, ErrorDePeticion) as exc:
            logger.warning("detalle_edicion.tebeosfera_fallida", error=type(exc).__name__)
            return ResultadoDetalle(
                EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_FALLO_TRANSITORIO,
                             "No se pudo consultar Tebeosfera; vuelve a intentarlo."), None)

        if coleccion is None:
            return ResultadoDetalle(
                EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_SIN_RESULTADOS,
                             "La ficha de esa colección no existe."), None)
        detalle = _desde_tebeosfera(coleccion)
        return ResultadoDetalle(
            EstadoFuente("tebeosfera", CAPACIDAD, FUENTE_OK), detalle)


def _resultado(*, requeridos: tuple[str, ...], ausentes: set[str], motivos: list[str],
               incorrecto: bool, ambiguo: bool) -> Contraste:
    if incorrecto:
        resultado = "incorrecto"
    elif ambiguo or any(campo in ausentes for campo in requeridos):
        resultado = "ambiguo"
    else:
        resultado = "coincidencia_verificada"
    return Contraste(resultado=resultado, campos_requeridos=requeridos,
                     campos_ausentes=tuple(sorted(ausentes)), motivos=tuple(motivos))


def contrastar(detalle: DetalleEdicion | None, etiqueta: Any, *,
               unidad: str = "edicion") -> Contraste:
    """Contraste puro detalle ↔ etiqueta acreditada (§4.3 de la spec FU2).

    No hay red ni escritura. Una etiqueta no acreditada no produce veredicto.
    """
    if detalle is None or etiqueta is None:
        return Contraste(resultado=None, motivos=("sin_detalle",))
    if _campo(etiqueta, "identidad_acreditada") is False:
        return Contraste(resultado=None, motivos=("no_acreditada",))

    unidad = (unidad or _campo(etiqueta, "unidad_esperada", "edicion") or "edicion").lower()
    editorial_etiqueta = _campo(etiqueta, "editorial")
    anio_etiqueta = _campo(etiqueta, "anio")
    numero_etiqueta = _campo(etiqueta, "numero")
    if numero_etiqueta is None:
        numero_etiqueta = _campo(etiqueta, "numero_publicacion")

    requeridos: list[str] = ["editorial", "anio"]
    if (unidad in ("publicacion", "numero", "número")
            or (unidad == "edicion" and numero_etiqueta is not None)):
        requeridos.append("numero_publicacion")
    elif unidad == "formato":
        requeridos.append("formato")
    elif unidad == "campo":
        campos = _campo(etiqueta, "campos") or {}
        requeridos.extend(campos.keys())

    ausentes: set[str] = set(detalle.campos_ausentes)
    motivos: list[str] = []
    incorrecto = False
    ambiguo = False

    if detalle.editorial is None and detalle.sello is None:
        ausentes.add("editorial")
    elif editorial_etiqueta:
        norm_etiqueta = _normalizar_editorial(editorial_etiqueta)
        norm_detalle = {_normalizar_editorial(detalle.editorial),
                        _normalizar_editorial(detalle.sello)} - {""}
        if norm_etiqueta not in norm_detalle:
            # Prefijo/sufijo por palabra: parecido no es identidad.
            if any(norm_etiqueta and (norm_etiqueta in n.split() or n in norm_etiqueta.split())
                   for n in norm_detalle):
                ambiguo = True
                motivos.append("editorial_parecida")
            else:
                incorrecto = True
                motivos.append("editorial_distinta")

    if detalle.anio is None:
        ausentes.add("anio")
    elif anio_etiqueta is not None:
        if int(anio_etiqueta) == detalle.anio:
            pass
        elif (detalle.anio_fin is not None
              and detalle.anio <= int(anio_etiqueta) <= detalle.anio_fin):
            ambiguo = True
            motivos.append("anio_en_rango")
        else:
            incorrecto = True
            motivos.append("anio_distinto")

    if numero_etiqueta is not None:
        if detalle.numero_publicacion is None:
            ambiguo = True
            motivos.append("numero_ausente")
        elif _normalizar_numero(numero_etiqueta) != _normalizar_numero(detalle.numero_publicacion):
            incorrecto = True
            motivos.append("numero_distinto")

    pais_etiqueta = _normalizar_pais(_campo(etiqueta, "pais"))
    pais_detalle = _normalizar_pais(detalle.pais)
    if pais_etiqueta and pais_detalle and pais_etiqueta != pais_detalle:
        incorrecto = True
        motivos.append("pais_distinto")

    idioma_etiqueta = _normalizar_idioma(_campo(etiqueta, "idioma"))
    idioma_detalle = _normalizar_idioma(detalle.idioma)
    if idioma_etiqueta and idioma_detalle and idioma_etiqueta != idioma_detalle:
        incorrecto = True
        motivos.append("idioma_distinto")

    formato_etiqueta = _campo(etiqueta, "formato")
    if formato_etiqueta:
        valor = (formato_etiqueta.value if isinstance(formato_etiqueta, IssueFormat)
                 else str(formato_etiqueta))
        if detalle.formato is not None and detalle.formato.value != valor:
            ambiguo = True
            motivos.append("formato_distinto")

    return _resultado(requeridos=tuple(requeridos), ausentes=ausentes, motivos=motivos,
                      incorrecto=incorrecto, ambiguo=ambiguo)
