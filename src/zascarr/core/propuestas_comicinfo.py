# ruff: noqa: E501
"""CNV5-1 / #482: contrato y capacidades de fuentes para completar el ComicInfo.

Módulo **puro**: no importa clientes, no hace red, no toca BD ni archivos. Sabe qué campo puede
proponer cada fuente (matriz fuente×campo), qué fuentes admite cada tradición (ADR 0002), qué
valores son elegibles y cómo normalizarlos con topes. Las funciones son deterministas y fáciles de
probar; la ejecución de peticiones queda para CNV5-2.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

from zascarr.core.comicinfo_write import CAMPOS_GESTIONADOS
from zascarr.services.estados_fuentes import (
    ESTADOS_DE_FUENTE,
    FUENTE_APAGADA,
    FUENTE_CONFIGURACION_INCOMPLETA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_LIMITE_DE_CORTESIA,
    FUENTE_SIN_RESULTADOS,
)
from zascarr.utils.texto_html import texto_plano

#: Presupuesto interactivo (D9): una ronda, sin reintentos ni segundo plano.
MAX_PETICIONES_POR_ACCION = 5
MAX_PETICIONES_POR_FUENTE = 3
ESPERA_MAX_S = 3.0
#: Topes de contrato (no se recorta en silencio: fuera de tope se descarta con motivo).
MAX_SUMMARY = 4000
MAX_PUBLISHER = 255
MAX_LISTA = 500
YEAR_MIN, YEAR_MAX = 1000, 2999
PAGECOUNT_MIN, PAGECOUNT_MAX = 1, 10000


class TradicionComicInfo(StrEnum):
    """Espejo **puro** de `models.ComicTradition` (no importamos ORM/config).

    Aceptamos también el enum del modelo en las funciones: su valor es el mismo string.
    """
    AMERICAN = "american"
    FRANCO_BELGIAN = "franco_belgian"
    MANGA = "manga"
    TEBEO = "tebeo"
    FUMETTI = "fumetti"
    MANHWA = "manhwa"
    MANHUA = "manhua"
    BRITISH = "british"
    OTHER = "other"


class RolAutor(StrEnum):
    """Espejo **puro** de `models.CreatorRole` para el mapeo de roles."""
    WRITER = "writer"
    PENCILER = "penciler"
    INKER = "inker"
    COLORIST = "colorist"
    LETTERER = "letterer"
    COVER_ARTIST = "cover_artist"
    EDITOR = "editor"
    TRANSLATOR = "translator"


class FuenteComicInfo(StrEnum):
    COMIC_VINE = "comic_vine"
    ANILIST = "anilist"
    TEBEOSFERA = "tebeosfera"
    GCD = "gcd"


class NivelDato(StrEnum):
    SERIE = "serie"
    NUMERO = "numero"


class EstadoPropuesta(StrEnum):
    ANADIR = "anadir"
    CONSERVAR = "conservar"
    YA_COINCIDE = "ya_coincide"
    PROPONER_SUSTITUCION = "proponer_sustitucion"
    BLOQUEADO = "bloqueado"


#: Etiqueta llana para la UI; el módulo no la usa para lógica.
NOMBRES_FUENTE = {
    FuenteComicInfo.COMIC_VINE: "Comic Vine",
    FuenteComicInfo.ANILIST: "AniList",
    FuenteComicInfo.TEBEOSFERA: "Tebeosfera",
    FuenteComicInfo.GCD: "GCD",
}

#: Campos de identidad local: una fuente NUNCA los propone (D1).
CAMPOS_IDENTIDAD = frozenset({"Series", "Number", "Volume", "LanguageISO"})

#: Matriz fuente×campo con el NIVEL del dato. Solo lo que hoy devuelve el cliente; no se inventa.
CAPACIDADES: dict[FuenteComicInfo, dict[str, NivelDato]] = {
    FuenteComicInfo.COMIC_VINE: {
        "Year": NivelDato.NUMERO,        # cover_date; start_year es el fallback de serie
        "Publisher": NivelDato.SERIE,
        "Summary": NivelDato.NUMERO,
        "Writer": NivelDato.NUMERO,
        "Penciller": NivelDato.NUMERO,
        "Inker": NivelDato.NUMERO,
        "Colorist": NivelDato.NUMERO,
        "Letterer": NivelDato.NUMERO,
        "CoverArtist": NivelDato.NUMERO,
        "Editor": NivelDato.NUMERO,
        "Translator": NivelDato.NUMERO,
    },
    FuenteComicInfo.ANILIST: {
        "Year": NivelDato.SERIE,
        "Summary": NivelDato.SERIE,
    },
    FuenteComicInfo.TEBEOSFERA: {
        "Year": NivelDato.NUMERO,
        "Publisher": NivelDato.SERIE,
        "PageCount": NivelDato.NUMERO,   # solo si la cifra del número se acredita
    },
    FuenteComicInfo.GCD: {
        "Year": NivelDato.SERIE,
        "Publisher": NivelDato.SERIE,
    },
}

#: Tradiciones que admite cada fuente (ADR 0002 / enricher; GCD para fumetti/BD antigua).
TRADICIONES: dict[FuenteComicInfo, frozenset[TradicionComicInfo]] = {
    FuenteComicInfo.COMIC_VINE: frozenset({TradicionComicInfo.AMERICAN,
                                           TradicionComicInfo.BRITISH}),
    FuenteComicInfo.ANILIST: frozenset({TradicionComicInfo.MANGA, TradicionComicInfo.MANHWA,
                                        TradicionComicInfo.MANHUA}),
    FuenteComicInfo.TEBEOSFERA: frozenset({TradicionComicInfo.TEBEO,
                                           TradicionComicInfo.FRANCO_BELGIAN}),
    FuenteComicInfo.GCD: frozenset({TradicionComicInfo.FUMETTI,
                                    TradicionComicInfo.FRANCO_BELGIAN}),
}

#: Tags de autoría que comparten el lock `issue.locked_fields = ["credits"]`.
TAGS_AUTOR = ("Writer", "Penciller", "Inker", "Colorist", "Letterer", "CoverArtist",
              "Editor", "Translator")
_TAGS_LISTA = frozenset(TAGS_AUTOR) | {"Genre"}

MOTIVO_VACIO = "vacío"
MOTIVO_IDENTIDAD = "campo de identidad (nunca se propone)"
MOTIVO_NO_ELEGIBLE = "campo sin capacidad en la fuente"
MOTIVO_DEMASIADO_LARGO = "más largo de lo permitido"
MOTIVO_FUERA_DE_RANGO = "fuera del rango permitido"
MOTIVO_NO_ES_ENTERO = "no es un número entero"
MOTIVO_DUPLICADO = "valor repetido"
MOTIVO_FUENTE_NO_ADMITIDA = "la tradición no admite esta fuente"
MOTIVO_FUENTE_APAGADA = "la fuente está apagada"


@dataclass(frozen=True)
class OpcionPropuesta:
    """Una opción concreta de una fuente para un campo."""
    valor: str
    fuente: FuenteComicInfo
    nivel: NivelDato
    procedencia: str | None = None
    motivo: str | None = None


@dataclass(frozen=True)
class PropuestaCampo:
    """Todas las opciones de un campo, con el valor actual y el estado del contrato."""
    tag: str
    actual: str | None
    opciones: tuple[OpcionPropuesta, ...] = ()
    estado: EstadoPropuesta = EstadoPropuesta.ANADIR
    bloqueado: bool = False
    motivo: str | None = None


@dataclass(frozen=True)
class ResultadoFuente:
    """Estado cerrado de #133 para una fuente y cuántas peticiones costó."""
    fuente: FuenteComicInfo
    estado: str
    peticiones: int = 0
    motivo: str | None = None

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS_DE_FUENTE:
            raise ValueError(f"estado de fuente desconocido: {self.estado}")


@dataclass
class Presupuesto:
    """Contador puro del presupuesto de una acción; no hace esperas ni peticiones."""
    peticiones: int = 0
    por_fuente: dict[FuenteComicInfo, int] = field(default_factory=dict)

    @property
    def agotado(self) -> bool:
        return self.peticiones >= MAX_PETICIONES_POR_ACCION

    def cabe(self, fuente: FuenteComicInfo, cantidad: int = 1) -> bool:
        return (cantidad >= 0 and self.peticiones + cantidad <= MAX_PETICIONES_POR_ACCION
                and self.por_fuente.get(fuente, 0) + cantidad <= MAX_PETICIONES_POR_FUENTE)

    def anotar(self, fuente: FuenteComicInfo, cantidad: int = 1) -> bool:
        if not self.cabe(fuente, cantidad):
            return False
        self.peticiones += cantidad
        self.por_fuente[fuente] = self.por_fuente.get(fuente, 0) + cantidad
        return True


def normalizar_texto(valor: str | None) -> str | None:
    """HTML/fuente → texto plano, `strip` y espacios colapsados. Vacío → None."""
    limpio = texto_plano(valor).strip()
    return limpio or None


def _normalizar_lista(valores: Iterable[str] | str) -> list[str]:
    if isinstance(valores, str):
        valores = valores.replace(";", ",").split(",")
    vistos: set[str] = set()
    limpios: list[str] = []
    for crudo in valores:
        valor = normalizar_texto(crudo) if isinstance(crudo, str) else None
        if not valor:
            continue
        clave = valor.casefold()
        if clave in vistos:
            continue
        vistos.add(clave)
        limpios.append(valor)
    return limpios


def normalizar_valor(tag: str, valor: object) -> tuple[str | None, str | None]:
    """Normaliza un valor de fuente para `tag`. Devuelve `(valor, None)` o `(None, motivo)`.

    Es la única puerta: un valor fuera de contrato se DESCARTA con motivo, nunca se recorta.
    """
    if tag not in CAMPOS_GESTIONADOS or tag not in campos_elegibles():
        return None, MOTIVO_IDENTIDAD if tag in CAMPOS_IDENTIDAD else MOTIVO_NO_ELEGIBLE
    if tag in _TAGS_LISTA:
        if not isinstance(valor, (str, list, tuple, set)):
            return None, MOTIVO_VACIO
        lista = _normalizar_lista(valor)
        if not lista:
            return None, MOTIVO_VACIO
        unido = ", ".join(lista)
        if len(unido) > MAX_LISTA:
            return None, MOTIVO_DEMASIADO_LARGO
        return unido, None
    if tag == "Year":
        if isinstance(valor, bool):
            return None, MOTIVO_NO_ES_ENTERO
        try:
            anio = int(str(valor).strip())
        except (TypeError, ValueError):
            return None, MOTIVO_NO_ES_ENTERO
        if not YEAR_MIN <= anio <= YEAR_MAX:
            return None, MOTIVO_FUERA_DE_RANGO
        return str(anio), None
    if tag == "PageCount":
        if isinstance(valor, bool):
            return None, MOTIVO_NO_ES_ENTERO
        try:
            paginas = int(str(valor).strip())
        except (TypeError, ValueError):
            return None, MOTIVO_NO_ES_ENTERO
        if not PAGECOUNT_MIN <= paginas <= PAGECOUNT_MAX:
            return None, MOTIVO_FUERA_DE_RANGO
        return str(paginas), None
    texto = normalizar_texto(valor if isinstance(valor, str) else None)
    if not texto:
        return None, MOTIVO_VACIO
    tope = MAX_SUMMARY if tag == "Summary" else MAX_PUBLISHER if tag == "Publisher" else 500
    if len(texto) > tope:
        return None, MOTIVO_DEMASIADO_LARGO
    return texto, None


def _tradicion(tradicion: TradicionComicInfo | str) -> TradicionComicInfo | None:
    try:
        return TradicionComicInfo(getattr(tradicion, "value", tradicion))
    except ValueError:
        return None


def fuentes_para_tradicion(
        tradicion: TradicionComicInfo | str) -> tuple[FuenteComicInfo, ...]:
    valor = _tradicion(tradicion)
    if valor is None:
        return ()
    return tuple(f for f, admitidas in TRADICIONES.items() if valor in admitidas)


def fuentes_elegibles(encendidas: Iterable[FuenteComicInfo | str],
                      tradicion: TradicionComicInfo | str) -> tuple[FuenteComicInfo, ...]:
    """Fuentes encendidas Y admitidas por la tradición. No instancia ningún cliente."""
    activas: set[FuenteComicInfo] = set()
    for fuente in encendidas:
        try:
            activas.add(FuenteComicInfo(fuente))
        except ValueError:
            continue
    return tuple(f for f in fuentes_para_tradicion(tradicion) if f in activas)


def campos_elegibles(fuente: FuenteComicInfo | None = None) -> frozenset[str]:
    """Solo campos de valor con capacidad en alguna fuente (o en la indicada)."""
    if fuente is not None:
        return frozenset(CAPACIDADES[fuente]) - CAMPOS_IDENTIDAD
    return frozenset().union(*(set(c) for c in CAPACIDADES.values())) - CAMPOS_IDENTIDAD


def campo_elegible(tag: str, fuente: FuenteComicInfo | None = None) -> bool:
    return tag in campos_elegibles(fuente)


def crear_opcion(tag: str, valor: object, *, fuente: FuenteComicInfo,
                 nivel: NivelDato | None = None,
                 procedencia: str | None = None) -> OpcionPropuesta | None:
    """Crea una opción solo si el campo está en la matriz de la fuente y el valor cumple.

    `nivel` explícito manda: `Year` de Comic Vine puede venir del número (cover_date) o de la
    serie (start_year); no se debe etiquetar el año de serie como si fuera del número.
    """
    if tag not in CAPACIDADES.get(fuente, {}) or tag in CAMPOS_IDENTIDAD:
        return None
    if nivel is None:
        nivel = CAPACIDADES[fuente][tag]
    limpio, motivo = normalizar_valor(tag, valor)
    if limpio is None:
        return OpcionPropuesta("", fuente, nivel, procedencia, motivo)
    return OpcionPropuesta(limpio, fuente, nivel, procedencia)


def construir_propuesta(tag: str, actual: str | None,
                        opciones: Iterable[OpcionPropuesta], *,
                        bloqueado: bool = False) -> PropuestaCampo:
    """Agrupa/deduplica opciones y decide el estado (D3) sin aplicar nada."""
    if tag in CAMPOS_IDENTIDAD or tag not in CAMPOS_GESTIONADOS:
        return PropuestaCampo(tag, actual, (), EstadoPropuesta.BLOQUEADO if tag in CAMPOS_IDENTIDAD
                              else EstadoPropuesta.ANADIR, bloqueado=False, motivo=MOTIVO_IDENTIDAD
                              if tag in CAMPOS_IDENTIDAD else MOTIVO_NO_ELEGIBLE)
    if bloqueado:
        return PropuestaCampo(tag, actual, (), EstadoPropuesta.BLOQUEADO, True,
                              "Protegido: no se toca")
    vistos: set[str] = set()
    validas: list[OpcionPropuesta] = []
    motivo: str | None = None
    for opcion in opciones:
        if not opcion.valor:
            motivo = motivo or opcion.motivo
            continue
        limpio, error = normalizar_valor(tag, opcion.valor)
        if limpio is None:
            motivo = motivo or error
            continue
        if opcion.fuente not in CAPACIDADES or tag not in CAPACIDADES[opcion.fuente]:
            motivo = motivo or MOTIVO_NO_ELEGIBLE
            continue
        if limpio.casefold() in vistos:
            continue
        vistos.add(limpio.casefold())
        validas.append(OpcionPropuesta(limpio, opcion.fuente, opcion.nivel,
                                       opcion.procedencia))
    actual_limpio = actual.strip() if isinstance(actual, str) and actual.strip() else None
    if actual_limpio is not None:
        actual_key = actual_limpio.casefold()
        if any(v.valor.casefold() == actual_key for v in validas):
            # Una opción coincide: no hay nada que elegir para este campo.
            estado = EstadoPropuesta.YA_COINCIDE if len(validas) == 1 else EstadoPropuesta.CONSERVAR
        else:
            estado = EstadoPropuesta.PROPONER_SUSTITUCION
    else:
        estado = EstadoPropuesta.ANADIR if validas else EstadoPropuesta.ANADIR
    if not validas:
        estado = EstadoPropuesta.ANADIR if actual_limpio is None else EstadoPropuesta.CONSERVAR
    return PropuestaCampo(tag, actual_limpio, tuple(validas), estado, False, motivo)


def estado_es_vacio(estado: str) -> bool:
    return estado in (FUENTE_SIN_RESULTADOS, FUENTE_APAGADA)


def estado_es_error(estado: str) -> bool:
    return estado in (FUENTE_FALLO_TRANSITORIO, FUENTE_CONFIGURACION_INCOMPLETA,
                      FUENTE_LIMITE_DE_CORTESIA)


def resultado_fuente(fuente: FuenteComicInfo, estado: str, *, peticiones: int = 0,
                     motivo: str | None = None) -> ResultadoFuente:
    return ResultadoFuente(fuente, estado, peticiones, motivo)


def sin_peticiones(encendidas: Iterable[FuenteComicInfo | str],
                   tradicion: TradicionComicInfo | str) -> tuple[ResultadoFuente, ...]:
    """Estados de las fuentes que no se consultan, con cero peticiones."""
    activas = fuentes_elegibles(encendidas, tradicion)
    return tuple(ResultadoFuente(f, FUENTE_APAGADA, 0) for f in FuenteComicInfo
                 if f not in activas)


def role_a_tag(role: RolAutor | str) -> str | None:
    """Rol de #448 → tag ComicInfo; el plan de B6 usa el mismo mapa."""
    normalizado = getattr(role, "value", role)
    return {
        RolAutor.WRITER.value: "Writer",
        RolAutor.PENCILER.value: "Penciller",
        RolAutor.INKER.value: "Inker",
        RolAutor.COLORIST.value: "Colorist",
        RolAutor.LETTERER.value: "Letterer",
        RolAutor.COVER_ARTIST.value: "CoverArtist",
        RolAutor.EDITOR.value: "Editor",
        RolAutor.TRANSLATOR.value: "Translator",
    }.get(str(normalizado))


__all__ = [
    "MAX_PETICIONES_POR_ACCION", "MAX_PETICIONES_POR_FUENTE", "ESPERA_MAX_S",
    "MAX_SUMMARY", "MAX_PUBLISHER", "MAX_LISTA", "YEAR_MIN", "YEAR_MAX",
    "PAGECOUNT_MIN", "PAGECOUNT_MAX", "FuenteComicInfo", "NivelDato", "EstadoPropuesta",
    "OpcionPropuesta", "PropuestaCampo", "ResultadoFuente", "Presupuesto",
    "CAPACIDADES", "TRADICIONES", "CAMPOS_IDENTIDAD", "NOMBRES_FUENTE", "TAGS_AUTOR",
    "TradicionComicInfo", "RolAutor",
    "normalizar_texto", "normalizar_valor", "fuentes_para_tradicion", "fuentes_elegibles",
    "campos_elegibles", "campo_elegible", "crear_opcion", "construir_propuesta",
    "estado_es_vacio", "estado_es_error", "resultado_fuente", "sin_peticiones", "role_a_tag",
]
