"""B6 — plan de cambios de ComicInfo y fusión del XML (núcleo puro).

Aquí vive la **precedencia**, sin tocar disco ni BD: dado el XML que ya hay y
los valores que ZascArr quiere escribir, decide **campo a campo** qué se
cambia, qué se conserva, qué ya coincide y qué no tiene dato. La misma lista de
campos alimenta la vista previa (`dry-run`) y la escritura real — nunca hay dos
caminos que puedan divergir (ficha `docs/design/benchmark-B6-comicinfo.md`).

Reglas (ficha, puntos 1, 12 y mapa mínimo):
  - Sin dato → `sin_dato`: NO se escribe ni se inventa.
  - Vacío en el XML → `cambia` (rellenar).
  - Igual al deseado → `ya_coincide`.
  - Distinto y ZascArr puede **probar** que lo escribió (`propio[tag] == actual`)
    → `cambia` (overlay).
  - Distinto y procedencia desconocida → `conserva` (no se pisa lo manual).
  - `LanguageISO` **nunca** se genera (no se infiere de la tradición).
  - Un `ComicInfo.xml` que no se puede leer (XML roto u otra raíz) **no se
    toca**: `ComicInfoInvalidoError`, y el fichero se marca como inválido.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from xml.etree import ElementTree

#: Entrada canónica dentro del CBZ (se normaliza a una sola, en la raíz).
ENTRADA_XML = "ComicInfo.xml"

#: Campos que B6 gestiona (mapa mínimo de la ficha). El resto del XML se
#: preserva tal cual al reescribir.
CAMPOS_GESTIONADOS = (
    "Series", "Number", "Volume", "Year", "Publisher", "Summary", "LanguageISO",
)


class Accion(StrEnum):
    CAMBIA = "cambia"
    CONSERVA = "conserva"
    YA_COINCIDE = "ya_coincide"
    SIN_DATO = "sin_dato"
    #: Detenido por `locked_fields` (H3): el dato existe y la precedencia lo
    #: permitiría, pero el coleccionista congeló ese campo. Nunca escribe.
    BLOQUEADO = "bloqueado"


@dataclass(frozen=True)
class CampoPlan:
    tag: str
    accion: Accion
    actual: str | None
    nuevo: str | None


def _texto(root: ElementTree.Element | None, tag: str) -> str | None:
    if root is None:
        return None
    el = root.find(tag)
    if el is not None and el.text and el.text.strip():
        return el.text.strip()
    return None


def leer_campos(root: ElementTree.Element | None) -> dict[str, str | None]:
    """Valor actual en el XML de cada campo gestionado (None si no está)."""
    return {tag: _texto(root, tag) for tag in CAMPOS_GESTIONADOS}


def plan(
    existentes: dict[str, str | None],
    deseados: dict[str, str | None],
    propio: dict[str, str] | None = None,
    solo_rellenar: bool = False,
) -> list[CampoPlan]:
    """Calcula el plan campo a campo. `propio` = lo que ZascArr escribió la
    última vez (prueba de autoría); si el valor actual coincide con él, ZascArr
    puede actualizar (`overlay`); si no, se conserva lo existente.

    `solo_rellenar` (estrategia *add missing* de ComicTagger, `--no-overwrite`)
    endurece la precedencia: aunque haya prueba de autoría, un campo con valor
    se conserva — solo se escriben los vacíos."""
    propio = propio or {}
    campos: list[CampoPlan] = []
    for tag in CAMPOS_GESTIONADOS:
        actual = existentes.get(tag)
        # Un valor en blanco no es un dato: no se escribe ni se inventa.
        nuevo = (deseados.get(tag) or "").strip() or None
        if not nuevo:
            accion = Accion.SIN_DATO
        elif actual is None:
            accion = Accion.CAMBIA
        elif actual == nuevo:
            accion = Accion.YA_COINCIDE
        elif not solo_rellenar and propio.get(tag) == actual:
            accion = Accion.CAMBIA
        else:
            accion = Accion.CONSERVA
        campos.append(CampoPlan(tag, accion, actual, nuevo))
    return campos


def hay_cambios(campos: list[CampoPlan]) -> bool:
    return any(c.accion is Accion.CAMBIA for c in campos)


class ComicInfoInvalidoError(ValueError):
    """Hay un `ComicInfo.xml` pero no se puede tratar como tal.

    Ni se fusiona ni se sustituye: quien lo recibe marca el fichero como
    **inválido** y no lo toca. Sustituir un XML que no entendemos sería perder
    lo que hubiera dentro (ficha, «Invariantes de ZascArr»)."""


def parsear(existente: bytes) -> ElementTree.Element:
    """Parsea el XML existente exigiendo la raíz `<ComicInfo>`.

    Un XML ilegible o con otra raíz lanza `ComicInfoInvalidoError` — nunca
    devuelve un árbol vacío que pudiera acabar reemplazando al original."""
    try:
        root = ElementTree.fromstring(existente)
    except ElementTree.ParseError as exc:
        raise ComicInfoInvalidoError(f"XML ilegible: {exc}") from exc
    if root.tag != "ComicInfo":
        raise ComicInfoInvalidoError(f"raíz inesperada: <{root.tag}>")
    return root


def fusionar_xml(
    existente: bytes | None, campos: list[CampoPlan]
) -> bytes:
    """Devuelve el `ComicInfo.xml` resultante: parte del existente (preservando
    **todos** los elementos desconocidos) y aplica solo los `cambia`.

    `existente=None` significa «no había entrada» y se crea desde cero; unos
    bytes que no sean un `<ComicInfo>` legible son `ComicInfoInvalidoError`
    (no se descarta nada en silencio)."""
    root = parsear(existente) if existente else ElementTree.Element("ComicInfo")

    for campo in campos:
        if campo.accion is not Accion.CAMBIA or not campo.nuevo:
            continue
        el = root.find(campo.tag)
        if el is None:
            el = ElementTree.SubElement(root, campo.tag)
        el.text = campo.nuevo

    return ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
