"""Procedencia y protección de los campos de una serie (MIT-M6-US01, #127).

SOLO LECTURA y sin modelo nuevo: reúne lo que ya está registrado en `Series.metadata_["alta"]`,
`Series.metadata_source` y `Series.locked_fields`. No consulta fuentes, no escribe y no inventa
procedencia campo a campo.

La distinción importante es qué se puede afirmar:

- el **alta** deja el origen (`manual` o la fuente) y la fecha en `metadata_["alta"]`;
- el **enriquecimiento** deja la fuente a nivel de serie en `metadata_source`, pero no un registro
  por campo: se atribuye a los campos que ese enriquecimiento escribe (sinopsis, portada, total y
  el identificador externo), y solo si hay un valor;
- un campo **bloqueado** está en `locked_fields` y el enriquecedor no lo sobrescribe;
- cualquier otro caso es **origen no registrado**, no «manual» por descarte.

El contrato no guarda propuestas de enriquecimiento por campo; por eso la vista no presenta una
propuesta que no consta. Eso queda como NOT RUN de #128.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from zascarr.models import MetadataSource, Series
from zascarr.services.portada_serie import eleccion_de_portada
from zascarr.services.tokens_revision import id_canonico
from zascarr.utils.texto_html import texto_plano

#: Campos gestionados que se muestran. `identidad` agrupa el id externo que corresponda; nunca se
#: muestra el valor del identificador, solo si consta.
CAMPOS_GESTIONADOS: tuple[tuple[str, str], ...] = (
    ("title", "Título"),
    ("start_year", "Año de inicio"),
    ("end_year", "Año de fin"),
    ("publisher", "Editorial"),
    ("description", "Sinopsis"),
    ("cover_url", "Portada"),
    ("total_issues", "Números en total"),
    ("identidad", "Identificador de la fuente"),
)

#: Campos que el enriquecedor puede escribir. `title`/`start_year` no: esos vienen del alta.
CAMPOS_DE_ENRIQUECIMIENTO = frozenset({"description", "cover_url", "total_issues", "identidad"})

#: Campos del alta que proceden de la candidata elegida o de lo escrito a mano.
CAMPOS_DE_ALTA = frozenset({"title", "start_year", "description", "cover_url", "identidad"})

NOMBRE_DE_FUENTE = {
    MetadataSource.COMIC_VINE.value: "Comic Vine",
    MetadataSource.ANILIST.value: "AniList",
    MetadataSource.TEBEOSFERA.value: "Tebeosfera",
    MetadataSource.GCD.value: "GCD",
    MetadataSource.METRON.value: "Metron",
    MetadataSource.OPEN_LIBRARY.value: "Open Library",
    MetadataSource.COMICINFO_XML.value: "el propio archivo",
    MetadataSource.MANUAL.value: "manual",
}

ID_FIELDS = (
    "comic_vine_id", "anilist_id", "tebeosfera_slug", "gcd_id",
    "metron_id", "open_library_id",
)

#: H8: una entrada activa con un campo desconocido o incompleta no se interpreta.
_CLAVES_ENTRADA = frozenset({
    "version", "fuente", "id_externo", "entidad", "kind", "fecha", "operacion_id",
    "origen", "modo",
})


@dataclass(frozen=True)
class CampoProcedencia:
    """Un campo gestionado, con lo que consta y solo lo que consta."""
    clave: str
    etiqueta: str
    valor: str
    origen: str | None
    manual: bool
    bloqueado: bool
    observaciones: tuple[str, ...] = ()


@dataclass(frozen=True)
class IdentidadDeFuente:
    """Una línea por fuente con identidad en la columna; nunca pinta el id interno (H12)."""
    clave: str
    fuente: str
    fecha: str | None
    procedencia: str


@dataclass(frozen=True)
class ProcedenciaDeSerie:
    campos: tuple[CampoProcedencia, ...]
    hay_datos: bool
    resumen: str
    identidades: tuple[IdentidadDeFuente, ...] = ()


def _texto(valor: object | None) -> str:
    if valor is None:
        return "Sin dato"
    if isinstance(valor, str):
        return valor.strip() or "Sin dato"
    return str(valor)


def _fecha(valor: object) -> str | None:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=UTC)
    return fecha.date().isoformat()


def _alta(series: Series) -> dict:
    alta = (series.metadata_ or {}).get("alta") if isinstance(series.metadata_, dict) else None
    return alta if isinstance(alta, dict) else {}


def _fuente(nombre: str | None) -> str:
    if not nombre:
        return "una fuente"
    return NOMBRE_DE_FUENTE.get(str(nombre), "una fuente")


def _entrada_valida(entrada: dict) -> bool:
    if set(entrada) != _CLAVES_ENTRADA or entrada.get("version") != 1:
        return False
    fuente = entrada.get("fuente")
    if fuente not in NOMBRE_DE_FUENTE or entrada.get("entidad") != "serie":
        return False
    if entrada.get("kind") not in (None, "collection", "saga"):
        return False
    if entrada.get("origen") not in ("confirmada", "enriquecimiento"):
        return False
    if entrada.get("modo") not in ("busqueda", "id_exacto"):
        return False
    if id_canonico(str(fuente), entrada.get("id_externo")) != entrada.get("id_externo"):
        return False
    return _fecha(entrada.get("fecha")) is not None


def _id_externo(series: Series) -> tuple[str | None, bool]:
    """(campo de id con valor, si alguno) y si alguno de los ids está bloqueado."""
    bloqueados = set(series.locked_fields or [])
    con_valor = next((campo for campo in ID_FIELDS if getattr(series, campo, None)), None)
    return con_valor, any(campo in bloqueados for campo in ID_FIELDS)


def _valor(clave: str, series: Series, id_presente: bool) -> str:
    if clave == "title":
        return _texto(series.title)
    if clave == "start_year":
        return _texto(series.start_year)
    if clave == "end_year":
        return _texto(series.end_year)
    if clave == "publisher":
        return _texto(series.publisher.name if series.publisher else None)
    if clave == "description":
        if not series.description:
            return "Sin dato"
        # Las fuentes entregan la sinopsis en HTML: en la tabla se enseña texto plano, no etiquetas.
        texto = texto_plano(series.description)
        if not texto:
            return "Sin dato"
        return texto if len(texto) <= 160 else texto[:157].rstrip() + "…"
    if clave == "cover_url":
        # BL-INF6: la portada elegida a mano no tiene por qué estar en `cover_url` (puede salir
        # de un CBZ), pero SÍ es la portada guardada de la serie.
        if series.cover_url or eleccion_de_portada(series) is not None:
            return "Portada guardada"
        return "Sin portada"
    if clave == "total_issues":
        return _texto(series.total_issues)
    return "Identificador registrado" if id_presente else "Sin identificar"


def _tiene_valor(clave: str, series: Series, id_presente: bool) -> bool:
    """Un campo vacío no acredita que su origen lo haya rellenado."""
    if clave == "title":
        return bool(series.title)
    if clave == "start_year":
        return series.start_year is not None
    if clave == "end_year":
        return series.end_year is not None
    if clave == "publisher":
        return series.publisher is not None
    if clave == "description":
        return bool(series.description)
    if clave == "cover_url":
        return bool(series.cover_url) or eleccion_de_portada(series) is not None
    if clave == "total_issues":
        return series.total_issues is not None
    return id_presente


def _origen(clave: str, series: Series, alta: dict, id_presente: bool) -> tuple[str | None, bool]:
    """(texto de origen, es manual). Solo atribuye lo que el registro permite afirmar."""
    # BL-INF6: la portada elegida a mano se registra ella misma (en `metadata_["portada"]`), así
    # que consta como manual aunque `metadata_source` sea el de una fuente o la serie sea de alta
    # manual.
    if clave == "cover_url" and eleccion_de_portada(series) is not None:
        return "Elegida a mano", True
    # BL-INF5: la edición manual por campo deja su propia marca con fecha.
    manual_meta = ((series.metadata_ or {}).get("manual")
                   if isinstance(series.metadata_, dict) else None)
    if isinstance(manual_meta, dict) and clave in manual_meta:
        return "Editado a mano", True
    origen_alta = str(alta.get("origen") or "")
    fuente_alta = alta.get("fuente")
    manual = origen_alta == "manual" or series.metadata_source == MetadataSource.MANUAL.value
    if not _tiene_valor(clave, series, id_presente):
        return None, manual
    if manual:
        return "Introducido a mano", True
    if origen_alta == "descubrir" and clave in CAMPOS_DE_ALTA:
        return f"Alta desde {_fuente(fuente_alta)}", False
    if (clave in CAMPOS_DE_ENRIQUECIMIENTO
            and series.metadata_source
            and series.metadata_source != MetadataSource.MANUAL.value):
        return f"Enriquecido desde {_fuente(series.metadata_source)}", False
    return None, False


def _observaciones(clave: str, series: Series, alta: dict, bloqueado: bool) -> tuple[str, ...]:
    observaciones: list[str] = []
    if bloqueado:
        observaciones.append("Protegido: el enriquecimiento no lo sobrescribe.")
    if (clave in CAMPOS_DE_ENRIQUECIMIENTO and series.enrichment_attempted_at
            and not bloqueado):
        fecha = series.enrichment_attempted_at.date().isoformat()
        observaciones.append(f"Último intento de enriquecimiento: {fecha}.")
    return tuple(observaciones)


def procedencia_de_serie(series: Series) -> ProcedenciaDeSerie:
    """La procedencia visible de los campos gestionados de UNA serie."""
    alta = _alta(series)
    id_presente, id_bloqueado = _id_externo(series)
    bloqueados = set(series.locked_fields or [])
    campos: list[CampoProcedencia] = []
    hay_datos = False
    for clave, etiqueta in CAMPOS_GESTIONADOS:
        bloqueado = id_bloqueado if clave == "identidad" else clave in bloqueados
        origen, manual = _origen(clave, series, alta, id_presente)
        if origen is not None or bloqueado:
            hay_datos = True
        campos.append(CampoProcedencia(
            clave=clave,
            etiqueta=etiqueta,
            valor=_valor(clave, series, id_presente),
            origen=origen,
            manual=manual,
            bloqueado=bloqueado,
            observaciones=_observaciones(clave, series, alta, bloqueado),
        ))
    fecha_alta = _fecha(alta.get("fecha"))
    if hay_datos and all(c.origen is not None for c in campos):
        resumen = "Esta serie tiene procedencia registrada para todos los datos visibles."
    elif hay_datos:
        resumen = ("Esta serie tiene procedencia registrada para algunos datos; el resto aparece "
                   "como origen no registrado.")
    else:
        resumen = ("No hay procedencia registrada para esta serie: no se atribuye ningún dato a "
                   "una fuente ni a una edición manual.")
    if fecha_alta:
        resumen += f" El alta consta del {fecha_alta}."
    return ProcedenciaDeSerie(campos=tuple(campos), hay_datos=hay_datos, resumen=resumen,
                              identidades=identidades_de_fuente(series))


_FUENTE_DE_COLUMNA = {
    "comic_vine_id": MetadataSource.COMIC_VINE.value,
    "anilist_id": MetadataSource.ANILIST.value,
    "tebeosfera_slug": MetadataSource.TEBEOSFERA.value,
    "gcd_id": MetadataSource.GCD.value,
}


def identidades_de_fuente(series: Series) -> tuple[IdentidadDeFuente, ...]:
    """H12: una línea por fuente; la fecha solo si hay una entrada activa válida.

    Una columna con id pero sin procedencia no es huérfana: dice «origen no registrado».
    El JSONB se lee con tolerancia; una entrada inválida nunca rompe la ficha.
    """
    meta = series.metadata_ if isinstance(series.metadata_, dict) else {}
    asociaciones = meta.get("asociaciones") if isinstance(meta.get("asociaciones"), list) else []
    validas: dict[str, dict] = {}
    for entrada in asociaciones:
        if not isinstance(entrada, dict) or not _entrada_valida(entrada):
            continue
        fuente = entrada["fuente"]
        validas.setdefault(str(fuente), entrada)
    lineas: list[IdentidadDeFuente] = []
    for columna, fuente in _FUENTE_DE_COLUMNA.items():
        valor = getattr(series, columna, None)
        if not valor:
            continue
        entrada = validas.get(fuente)
        if entrada is not None and str(entrada.get("id_externo")) == str(valor):
            lineas.append(IdentidadDeFuente(
                clave=fuente, fuente=NOMBRE_DE_FUENTE[fuente],
                fecha=_fecha(entrada.get("fecha")), procedencia="registrada"))
        else:
            lineas.append(IdentidadDeFuente(
                clave=fuente, fuente=NOMBRE_DE_FUENTE[fuente], fecha=None,
                procedencia="no registrada"))
    return tuple(lineas)
