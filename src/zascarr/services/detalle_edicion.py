"""Detalle de edición por ficha de colección (#465, BL-FU2 PR-1).

Núcleo puro: normaliza una ficha de Tebeosfera a `DetalleEdicion`, calcula los campos
ausentes y contrasta contra una etiqueta acreditada del corpus. NO escribe en `Series`/
`Issue`, no persiste y no hace red. La integración con Discovery es PR-2.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from zascarr.models import IssueFormat, MetadataSource
from zascarr.services.estados_fuentes import EstadoFuente

#: Capacidad de #133 para la ficha de detalle. No se añade al conjunto cerrado de
#: `ESTADOS_DE_FUENTE`: reutiliza sus estados, solo identifica qué se estaba consultando.
CAPACIDAD_DETALLE = "detalle"

RESULTADOS_CONTRASTE = ("coincidencia_verificada", "ambiguo", "incorrecto")


@dataclass(frozen=True)
class DetalleEdicion:
    """Datos de una edición leídos de una fuente; evidencia de lectura, no identidad."""

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
    peticiones: int = 1
    url_ficha: str | None = None


@dataclass(frozen=True)
class ResultadoDetalle:
    """Respuesta de detalle con un estado del vocabulario CERRADO de #133."""

    estado: EstadoFuente
    detalle: DetalleEdicion | None
    motivo: str | None = None


@dataclass(frozen=True)
class ResultadoContraste:
    """Propuesta automática de contraste; nunca sustituye a la revisión humana."""

    resultado: str | None
    campos_requeridos: tuple[str, ...] = ()
    campos_ausentes: tuple[str, ...] = ()
    motivos: tuple[str, ...] = ()


#: Alias del nombre que usa la spec al describir el flujo.
Contraste = ResultadoContraste


def _normalizar(texto: str | None) -> str:
    """NFKD, sin diacríticos, minúsculas, puntuación a espacio y espacios colapsados."""
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    limpio = re.sub(r"[^\w\s]", " ", sin_acentos.lower(), flags=re.UNICODE)
    return " ".join(limpio.split())


def _sin_articulos(texto: str) -> str:
    """Quita artículos iniciales para comparar editoriales por palabra completa."""
    palabras = texto.split()
    while palabras and palabras[0] in {"el", "la", "los", "las", "un", "una"}:
        palabras.pop(0)
    return " ".join(palabras)


def _pais_normalizado(valor: str | None) -> str | None:
    if not valor:
        return None
    v = _normalizar(valor)
    if v in {"es", "espana", "spain", "espanya"}:
        return "ES"
    return valor.strip().upper()


def _idioma_normalizado(valor: str | None) -> str | None:
    if not valor:
        return None
    v = _normalizar(valor)
    if v in {"es", "espanol", "spanish"}:
        return "es"
    return v


def mapa_formato(texto: str | None) -> IssueFormat | None:
    """Mapa CERRADO y conservador del formato físico de la fuente a `IssueFormat`.

    Solo equivalencias inequívocas observadas; si no hay, `None` (campo ausente), nunca una
    adivinanza. `CUADERNO / GRAPA` es una grapa; `cartoné` es tapa dura; `álbum` es álbum.
    """
    v = _normalizar(texto)
    if not v:
        return None
    # El corpus ya usa los valores del enum (`album`, `single_issue`...): se aceptan tal cual.
    for formato in IssueFormat:
        if v == formato.value:
            return formato
    if "cuaderno" in v and "grapa" in v:
        return IssueFormat.SINGLE_ISSUE
    if "cartone" in v:
        return IssueFormat.HARDCOVER
    if "album" in v:
        return IssueFormat.ALBUM
    return None


def _campos_ausentes(detalle: DetalleEdicion) -> frozenset[str]:
    """Deriva el conjunto exacto de campos que la fuente no informa."""
    valores = {
        "editorial": detalle.editorial,
        "sello": detalle.sello,
        "anio": detalle.anio,
        "anio_fin": detalle.anio_fin,
        "numeracion_inicio": detalle.numeracion_inicio,
        "numeracion_fin": detalle.numeracion_fin,
        "numeracion_texto": detalle.numeracion_texto,
        "numero_publicacion": detalle.numero_publicacion,
        "paginas": detalle.paginas,
        "formato": detalle.formato,
        "pais": detalle.pais,
        "idioma": detalle.idioma,
    }
    return frozenset(campo for campo, valor in valores.items() if valor is None)


def detalle_desde_coleccion(coleccion: Any, *,
                            metodo: str = "get_collection") -> DetalleEdicion:
    """Normaliza un `TebeosferaColeccion` crudo a `DetalleEdicion` (sin red)."""
    formato = mapa_formato(getattr(coleccion, "formato_fuente", None))
    detalle = DetalleEdicion(
        fuente=MetadataSource.TEBEOSFERA,
        external_id=getattr(coleccion, "slug", ""),
        metodo=metodo,
        editorial=getattr(coleccion, "editorial", None),
        sello=getattr(coleccion, "sello", None),
        anio=getattr(coleccion, "anio", None),
        anio_fin=getattr(coleccion, "anio_fin", None),
        numeracion_inicio=getattr(coleccion, "numeracion_inicio", None),
        numeracion_fin=getattr(coleccion, "numeracion_fin", None),
        numeracion_texto=getattr(coleccion, "numeracion_texto", None),
        numero_publicacion=getattr(coleccion, "numero_publicacion", None),
        paginas=getattr(coleccion, "paginas", None),
        formato=formato,
        formato_fuente=getattr(coleccion, "formato_fuente", None),
        pais=getattr(coleccion, "pais", None),
        idioma=getattr(coleccion, "idioma", None),
        peticiones=getattr(coleccion, "peticiones", 1),
        url_ficha=getattr(coleccion, "url_ficha", None),
    )
    return DetalleEdicion(**{**detalle.__dict__, "campos_ausentes": _campos_ausentes(detalle)})


def _campos_requeridos(unidad: str, etiqueta: Mapping[str, Any]) -> tuple[str, ...]:
    requeridos = ["editorial", "anio"]
    if unidad in ("publicacion", "numero"):
        requeridos.append("numero_publicacion")
    elif unidad == "edicion":
        if etiqueta.get("numero") not in (None, ""):
            requeridos.append("numero_publicacion")
    elif unidad == "formato":
        requeridos.append("formato")
    elif unidad == "campo":
        campos = etiqueta.get("campos") or {}
        if not isinstance(campos, Mapping):
            campos = {}
        for campo in campos:
            if campo == "paginas":
                requeridos.append("paginas")
            elif campo == "formato":
                requeridos.append("formato")
            else:
                # Campo editorial no modelado en DetalleEdicion: no se puede comparar.
                requeridos.append(str(campo))
    elif unidad != "serie":
        raise ValueError(f"unidad de contraste desconocida: {unidad}")
    return tuple(dict.fromkeys(requeridos))


def _comparar_editorial(detalle: DetalleEdicion,
                        etiqueta: Mapping[str, Any]) -> tuple[str, str | None]:
    """Devuelve (estado, motivo): `igual`, `aproximado` con motivo, o `distinto`."""
    etiqueta_norm = _sin_articulos(_normalizar(str(etiqueta.get("editorial") or "")))
    if not etiqueta_norm:
        return "ausente", "editorial_sin_etiqueta"
    opciones = [("editorial", detalle.editorial), ("sello", detalle.sello)]
    for campo, valor in opciones:
        if valor is None:
            continue
        valor_norm = _sin_articulos(_normalizar(valor))
        if not valor_norm:
            continue
        if valor_norm == etiqueta_norm:
            return "igual", None
        # Prefix/suffix por palabra completa: «Panini»/«Panini España». Es parecido, no
        # identidad: nunca se acredita por esta vía.
        if (etiqueta_norm.startswith(valor_norm + " ")
                or etiqueta_norm.endswith(" " + valor_norm)
                or valor_norm.startswith(etiqueta_norm + " ")
                or valor_norm.endswith(" " + etiqueta_norm)):
            return "aproximado", f"editorial_aproximada:{campo}"
    return "distinto", "editorial_discrepante"


def _numero_normalizado(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip().lower()
    if not texto:
        return None
    digitos = re.findall(r"\d+", texto)
    if len(digitos) == 1:
        return str(int(digitos[0]))
    return " ".join(texto.split())


def contrastar(detalle: DetalleEdicion | None, etiqueta: Mapping[str, Any] | None, *,
               unidad: str = "edicion") -> ResultadoContraste:
    """Contrasta una ficha con una etiqueta del corpus. Puro: sin red ni BD.

    Reglas: requeridos editorial+año (y número si la etiqueta lo trae / la unidad lo exige);
    ausencia de requerido ⇒ `ambiguo`; discrepancia ⇒ `incorrecto`; formato discrepante ⇒
    `ambiguo`; país/idioma discrepantes ⇒ `incorrecto`; etiqueta no acreditada o sin detalle
    ⇒ `resultado=None` (sin veredicto editorial). La coincidencia es **propuesta**: la
    acreditación final es humana.
    """
    if not etiqueta:
        return ResultadoContraste(None, motivos=("etiqueta_ausente",))
    requeridos = _campos_requeridos(unidad, etiqueta)
    if not etiqueta.get("identidad_acreditada"):
        return ResultadoContraste(
            None, campos_requeridos=requeridos,
            campos_ausentes=(tuple(sorted(detalle.campos_ausentes)) if detalle else ()),
            motivos=("etiqueta_no_acreditada",))
    if detalle is None:
        return ResultadoContraste(
            None, campos_requeridos=requeridos, motivos=("detalle_ausente",))

    valores = {
        "editorial": detalle.editorial, "sello": detalle.sello, "anio": detalle.anio,
        "anio_fin": detalle.anio_fin, "numeracion_inicio": detalle.numeracion_inicio,
        "numeracion_fin": detalle.numeracion_fin,
        "numeracion_texto": detalle.numeracion_texto,
        "numero_publicacion": detalle.numero_publicacion, "paginas": detalle.paginas,
        "formato": detalle.formato, "pais": detalle.pais, "idioma": detalle.idioma,
    }
    # Se deriva de los valores, no de un `campos_ausentes` que un llamador pueda dejar
    # desactualizado: la ausencia es un hecho del detalle, no una etiqueta de confianza.
    ausentes_set = {campo for campo, valor in valores.items() if valor is None}
    ausentes = tuple(sorted(ausentes_set))
    motivos: list[str] = []
    campos_conocidos = set(valores)
    faltan = [campo for campo in requeridos
              if campo in ausentes_set or campo not in campos_conocidos]
    for campo in faltan:
        motivos.append(f"{campo}_ausente")
    if faltan:
        return ResultadoContraste(
            "ambiguo", campos_requeridos=requeridos, campos_ausentes=ausentes,
            motivos=tuple(dict.fromkeys(motivos)))

    incorrecto = False
    ambiguo = False

    estado_editorial, motivo_editorial = _comparar_editorial(detalle, etiqueta)
    if estado_editorial == "distinto":
        incorrecto = True
        motivos.append(motivo_editorial or "editorial_discrepante")
    elif estado_editorial == "aproximado":
        ambiguo = True
        motivos.append(motivo_editorial or "editorial_aproximada")
    elif estado_editorial == "ausente":
        ambiguo = True
        motivos.append(motivo_editorial or "editorial_ausente")

    anio_etiqueta = etiqueta.get("anio")
    if anio_etiqueta is not None:
        if detalle.anio is not None and int(anio_etiqueta) == detalle.anio:
            pass
        elif (detalle.anio is not None and detalle.anio_fin is not None
              and detalle.anio <= int(anio_etiqueta) <= detalle.anio_fin):
            ambiguo = True
            motivos.append("anio_en_rango")
        else:
            incorrecto = True
            motivos.append("anio_discrepante")

    if "numero_publicacion" in requeridos:
        numero_etiqueta = _numero_normalizado(etiqueta.get("numero"))
        numero_detalle = _numero_normalizado(detalle.numero_publicacion)
        if numero_etiqueta is not None and numero_detalle != numero_etiqueta:
            incorrecto = True
            motivos.append("numero_publicacion_discrepante")

    if "formato" in requeridos:
        formato_etiqueta = etiqueta.get("formato")
        esperado = mapa_formato(str(formato_etiqueta)) if formato_etiqueta else None
        if esperado is not None and detalle.formato is not None and esperado != detalle.formato:
            ambiguo = True
            motivos.append("formato_discrepante")
        elif esperado is not None and detalle.formato is None:
            ambiguo = True
            motivos.append("formato_ausente")

    if "paginas" in requeridos:
        paginas = etiqueta.get("campos", {}).get("paginas")
        if paginas is not None and detalle.paginas != paginas:
            incorrecto = True
            motivos.append("paginas_discrepantes")

    if detalle.pais is not None and etiqueta.get("pais") is not None:
        if _pais_normalizado(detalle.pais) != _pais_normalizado(str(etiqueta["pais"])):
            incorrecto = True
            motivos.append("pais_discrepante")
    elif detalle.pais is None:
        motivos.append("pais_ausente")

    if detalle.idioma is not None and etiqueta.get("idioma") is not None:
        if _idioma_normalizado(detalle.idioma) != _idioma_normalizado(str(etiqueta["idioma"])):
            incorrecto = True
            motivos.append("idioma_discrepante")
    elif detalle.idioma is None:
        motivos.append("idioma_ausente")

    if incorrecto:
        resultado = "incorrecto"
    elif ambiguo:
        resultado = "ambiguo"
    else:
        resultado = "coincidencia_verificada"
    return ResultadoContraste(resultado, campos_requeridos=requeridos,
                              campos_ausentes=ausentes,
                              motivos=tuple(dict.fromkeys(motivos)))


__all__ = [
    "CAPACIDAD_DETALLE",
    "Contraste",
    "DetalleEdicion",
    "RESULTADOS_CONTRASTE",
    "ResultadoContraste",
    "ResultadoDetalle",
    "contrastar",
    "detalle_desde_coleccion",
    "mapa_formato",
]
