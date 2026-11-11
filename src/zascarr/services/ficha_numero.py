# ruff: noqa: E501
"""Ficha de serie y de número: SOLO lectura, sin red y con un número FIJO de consultas (#447).

No escribe, no enriquece y no consulta fuentes. La sinopsis se sirve como texto plano
(`utils.texto_html.texto_plano`); los autores se agrupan por papel y los principales de la serie
se calculan con un agregado, no con una consulta por número.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.core.importer_triage import natural_key
from zascarr.models import Creator, Issue, IssueCreator, Series
from zascarr.utils.texto_html import texto_plano

#: Un solo sitio para el copy provisional hasta que llegue `ui-BL-INF1-ficha-numero.md`.
TEXTOS = {
    "serie_bloque": "Sobre esta serie",
    "sinopsis": "Sinopsis",
    "sinopsis_completa": "Leer la sinopsis completa",
    "editorial": "Editorial",
    "inicio": "Año de inicio",
    "fin": "Año de fin",
    "autores": "Autores principales",
    "autores_numero": "Autores",
    "serie": "Serie",
    "formato": "Formato",
    "fecha": "Fecha de portada",
    "paginas": "Páginas",
    "archivos": "Archivos",
    "procedencia": "De dónde sale cada dato",
    "sin_dato": "No consta todavía.",
    "sin_sinopsis": "No consta todavía la sinopsis. Puede venir de una fuente de datos o de la ficha de tus archivos.",
    "sin_sinopsis_numero": "No consta todavía la sinopsis.",
    "sin_datos": "Todavía no hay información de esta serie. Puede venir de las fuentes de Ajustes o de la ficha de tus archivos.",
    "sin_datos_numero": "Todavía no hay información de este número ni archivos vinculados. Puede venir de una fuente de datos o de la ficha del archivo.",
    "sin_autores": "No constan todavía los autores. Pueden venir de una fuente o de los datos de la serie.",
    "sin_autores_numero": "No constan todavía los autores. Pueden venir de la fuente o de la ficha del archivo.",
    "sin_archivos": "No hay ningún archivo vinculado a este número. Puedes vincularlo desde la ficha de la serie.",
    "sin_procedencia": "No consta todavía de dónde sale este dato.",
    "portada_serie": "Portada de la serie",
    "portada_numero": "Portada del número",
    "publicacion": "Publicación",
    "isbn": "ISBN",
    "volver": "← Volver a la serie",
    "ir_serie": "Ir a la serie",
    "glosario": "Qué significan estos papeles",
    "glosario_texto": "Guion: quién escribe el texto. Dibujo: quién dibuja las páginas. Tinta: quién entinta el dibujo. Color: quién da el color. Rotulación: quién rotula el texto. Portada: quién hizo la portada. Edición: quién coordina la publicación; no es una edición distinta del número. Traducción: quién traduce esta versión.",
}

#: Una sola tabla de formatos de publicación (la comparte la ficha; el asistente la reexporta).
FORMATOS_LEGIBLES: dict[str, str] = {
    "single_issue": "grapa", "trade_paperback": "tomo en rústica",
    "hardcover": "tomo en tapa dura", "omnibus": "ómnibus",
    "graphic_novel": "novela gráfica", "album": "álbum",
    "manga_tankobon": "tomo de manga", "digital": "digital",
}

ROLES_ES: tuple[tuple[str, str], ...] = (
    ("writer", "Guion"),
    ("penciler", "Dibujo"),
    ("inker", "Tinta"),
    ("colorist", "Color"),
    ("letterer", "Rotulación"),
    ("cover_artist", "Portada"),
    ("editor", "Edición"),
    ("translator", "Traducción"),
)
_ROLE_LABEL = dict(ROLES_ES)
_TOPE_AUTORES = 3


@dataclass(frozen=True)
class AutorPrincipal:
    nombre: str
    papel: str
    numeros: int


@dataclass(frozen=True)
class ArchivoDeNumero:
    id: str
    nombre: str
    formato: str
    tamano: int | None
    falta_en_disco: bool
    #: SHA-256 del contenido si consta (B16); None = no se ha comprobado.
    sha256: str | None = None
    #: BL-R6: "" (único), copia, variante o sin_comprobar.
    clasificacion: str = ""


@dataclass(frozen=True)
class OtraEdicion:
    """Otra publicación de la serie con el mismo número (edición distinta)."""
    issue_id: str
    numero: str
    volumen: int
    formato: str


@dataclass(frozen=True)
class NumeroEnlace:
    id: str
    numero: str
    tiene_archivos: bool


@dataclass
class FichaSerie:
    serie: Series
    sinopsis: str
    autores: dict[str, list[AutorPrincipal]] = field(default_factory=dict)
    numeros: list[NumeroEnlace] = field(default_factory=list)
    numeros_por_id: dict[str, NumeroEnlace] = field(default_factory=dict)
    origen_autores: str = "Origen no registrado"
    autores_texto: str = ""

    def enlace_para_numero(self, numero: object) -> NumeroEnlace | None:
        """Enlace robusto para el chip: normaliza «01»/1 y prefiere el número con archivos."""
        cands = [n for n in self.numeros if natural_key(n.numero) == natural_key(str(numero))]
        if not cands:
            return None
        return next((n for n in cands if n.tiene_archivos), cands[0])


@dataclass
class FichaNumero:
    serie: Series
    issue: Issue
    sinopsis: str
    autores: dict[str, list[str]] = field(default_factory=dict)
    archivos: list[ArchivoDeNumero] = field(default_factory=list)
    #: BL-R6: otras publicaciones con el mismo número (ediciones distintas, no variantes).
    otras_ediciones: list[OtraEdicion] = field(default_factory=list)
    procedencia: dict[str, str] = field(default_factory=dict)
    formato: str = ""
    fecha_larga: str | None = None
    editorial: str = ""
    paginas_texto: str | None = None
    tiene_datos: bool = False


def _fecha_llana(valor: date | None) -> str | None:
    if valor is None:
        return None
    return valor.strftime("%d/%m/%Y")


def _texto_sinopsis(valor: str | None) -> str:
    return texto_plano(valor)


async def cargar_ficha_serie(db: AsyncSession, series_id: UUID) -> FichaSerie | None:
    """Serie + autores principales + números, en un número fijo de consultas."""
    serie = (await db.execute(
        select(Series).options(selectinload(Series.publisher)).where(Series.id == series_id)
    )).scalar_one_or_none()
    if serie is None:
        return None
    issues = (await db.execute(
        select(Issue)
        .options(selectinload(Issue.credits), selectinload(Issue.files))
        .where(Issue.series_id == series_id)
    )).scalars().all()
    issues = sorted(issues, key=lambda i: (
        getattr(i, "sort_order", None) is None, getattr(i, "sort_order", None) or 0.0,
        natural_key(i.issue_number or ""), str(i.id)))
    filas = (await db.execute(
        select(IssueCreator.role, Creator.name, func.max(Creator.metadata_source),
               func.count(func.distinct(IssueCreator.issue_id)))
        .join(Creator, Creator.id == IssueCreator.creator_id)
        .join(Issue, Issue.id == IssueCreator.issue_id)
        .where(Issue.series_id == series_id)
        .group_by(IssueCreator.role, Creator.name)
        .order_by(func.count(func.distinct(IssueCreator.issue_id)).desc(), Creator.name)
    )).all()
    autores: dict[str, list[AutorPrincipal]] = {}
    # Solo Guion y Dibujo son «autores principales» de la serie (UX §2.4).
    todas: dict[str, list[AutorPrincipal]] = {}
    fuentes_creditos: set[str] = set()
    credito_sin_fuente = False
    for rol, nombre, fuente_credito, cantidad in filas:
        clave = rol.value if hasattr(rol, "value") else str(rol)
        if clave in ("writer", "penciler"):
            todas.setdefault(clave, []).append(
                AutorPrincipal(nombre=nombre, papel=clave, numeros=int(cantidad)))
            if fuente_credito:
                fuentes_creditos.add(str(fuente_credito))
            else:
                credito_sin_fuente = True
    for clave, lista in todas.items():
        lista.sort(key=lambda a: (-a.numeros, natural_key(a.nombre)))
        autores[clave] = lista[:_TOPE_AUTORES]
    numeros = [NumeroEnlace(id=str(i.id), numero=i.issue_number or "(sin número)",
                            tiene_archivos=bool(getattr(i, "files", None))) for i in issues]
    if not autores or credito_sin_fuente:
        origen = "Origen no registrado"
    elif len(fuentes_creditos) == 1:
        origen = _procedencia(next(iter(fuentes_creditos)), True)
    elif len(fuentes_creditos) > 1:
        origen = "Varias fuentes"
    else:
        origen = "Origen no registrado"
    textos_autores = []
    for clave, etiqueta in ROLES_ES:
        if clave in ("writer", "penciler") and autores.get(clave):
            textos_autores.append(etiqueta + ": " + ", ".join(a.nombre for a in autores[clave]))
    autores_texto = "; ".join(textos_autores)
    return FichaSerie(serie=serie, sinopsis=_texto_sinopsis(getattr(serie, "description", None)),
                      autores=autores, numeros=numeros,
                      numeros_por_id={n.numero: n for n in numeros}, origen_autores=origen,
                      autores_texto=autores_texto)


async def cargar_ficha_numero(db: AsyncSession, series_id: UUID,
                              issue_id: UUID) -> FichaNumero | None:
    """Número de esa serie con autores y archivos; sin consultas por archivo ni por autor."""
    issue = (await db.execute(
        select(Issue)
        .options(selectinload(Issue.credits).selectinload(IssueCreator.creator),
                 selectinload(Issue.files))
        .where(Issue.id == issue_id, Issue.series_id == series_id)
    )).scalar_one_or_none()
    if issue is None:
        return None
    serie = (await db.execute(
        select(Series).options(selectinload(Series.publisher)).where(Series.id == series_id)
    )).scalar_one_or_none()
    if serie is None:
        return None
    autores: dict[str, list[str]] = {}
    for credito in sorted(getattr(issue, "credits", None) or [],
                          key=lambda c: (c.role.value, c.creator.name)):
        autores.setdefault(credito.role.value, []).append(credito.creator.name)
    archivos = [ArchivoDeNumero(
        id=str(f.id), nombre=f.file_name, formato=f.file_format.value,
        tamano=f.file_size_bytes, falta_en_disco=bool(f.is_missing),
        sha256=getattr(f, "sha256_hash", None),
    ) for f in sorted(getattr(issue, "files", None) or [],
                      key=lambda f: natural_key(f.file_name))]
    archivos = clasificar_archivos(archivos)
    otras_ediciones = (await _otras_ediciones(db, series_id, issue)
                       if len(archivos) > 1 else [])
    procedencia: dict[str, dict[str, str]] = {}
    nombre_fuente = _procedencia(getattr(issue, "metadata_source", None), True)
    fuentes_credito = {getattr(c.creator, "metadata_source", None)
                       for c in (getattr(issue, "credits", None) or [])}
    if autores:
        if any(f is None for f in fuentes_credito):
            origen_autores = "Origen no registrado"
        elif len(fuentes_credito) == 1:
            origen_autores = _procedencia(next(iter(fuentes_credito)), True)
        elif len(fuentes_credito) > 1:
            origen_autores = "Varias fuentes"
        else:
            origen_autores = "Origen no registrado"
    else:
        origen_autores = "Origen no registrado"
    if issue.synopsis:
        procedencia[TEXTOS["sinopsis"]] = {"valor": issue.synopsis and _texto_sinopsis(issue.synopsis),
                                           "origen": nombre_fuente}
    fecha = getattr(issue, "release_date", None)
    if fecha is not None:
        procedencia[TEXTOS["fecha"]] = {"valor": fecha_larga(fecha), "origen": nombre_fuente}
    paginas = getattr(issue, "page_count", None)
    if paginas is not None:
        procedencia[TEXTOS["paginas"]] = {
            "valor": f"{paginas} página" if paginas == 1 else f"{paginas} páginas",
            "origen": nombre_fuente}
    if autores:
        nombres = ", ".join(n for lista in autores.values() for n in lista)
        procedencia[TEXTOS["autores_numero"]] = {"valor": nombres, "origen": origen_autores}
    if archivos:
        procedencia[TEXTOS["archivos"]] = {
            "valor": ", ".join(a.nombre for a in archivos), "origen": "El propio archivo"}
    formato = FORMATOS_LEGIBLES.get(getattr(getattr(issue, "format", None), "value", None), "")
    fecha = getattr(issue, "release_date", None)
    paginas = getattr(issue, "page_count", None)
    tiene_datos = bool(issue.synopsis or fecha or paginas or autores or archivos)
    return FichaNumero(
        serie=serie, issue=issue, sinopsis=_texto_sinopsis(issue.synopsis),
        autores=autores, archivos=archivos, otras_ediciones=otras_ediciones,
        procedencia=procedencia, formato=formato,
        fecha_larga=fecha_larga(fecha),
        editorial=getattr(getattr(serie, "publisher", None), "name", "") or "",
        paginas_texto=(f"{paginas} página" if paginas == 1 else f"{paginas} páginas") if paginas else None,
        tiene_datos=tiene_datos)


def _procedencia(metadata_source: str | None, presente: bool) -> str:
    if not presente:
        return TEXTOS["sin_procedencia"]
    if not metadata_source:
        return "Origen no registrado"
    nombres = {
        "comic_vine": "Comic Vine", "anilist": "AniList",
        "tebeosfera": "Tebeosfera", "gcd": "GCD", "manual": "Puesto a mano",
        "comicinfo_xml": "El propio archivo",
    }
    return nombres.get(str(metadata_source), "Origen no registrado")


def etiqueta_rol(rol: str) -> str:
    return _ROLE_LABEL.get(rol, rol)


def fecha_llana(valor: date | None) -> str | None:
    return _fecha_llana(valor)


_FORMATO = {
    "single_issue": "grapa", "trade_paperback": "tomo en rústica",
    "hardcover": "tapa dura", "omnibus": "ómnibus", "graphic_novel": "novela gráfica",
    "album": "álbum", "manga_tankobon": "tankōbon", "digital": "digital",
}
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")


def fecha_larga(valor: date | None) -> str | None:
    if valor is None:
        return None
    return f"{valor.day} de {_MESES[valor.month - 1]} de {valor.year}"


def partir_sinopsis(texto: str, max_palabras: int = 40) -> tuple[str, str]:
    """(visible, resto) sin partir palabras; sin «…» en el summary."""
    palabras = texto.split()
    if len(palabras) <= max_palabras:
        return texto, ""
    return " ".join(palabras[:max_palabras]), " ".join(palabras[max_palabras:])


def clasificar_archivos(archivos: list[ArchivoDeNumero]) -> list[ArchivoDeNumero]:
    """BL-R6: copia exacta (mismo SHA-256), variante (otro contenido del mismo
    número) o sin comprobar. Un solo archivo no lleva clasificación."""
    if len(archivos) <= 1:
        return list(archivos)
    cuentas = Counter(a.sha256 for a in archivos if a.sha256)
    clasificados: list[ArchivoDeNumero] = []
    for archivo in archivos:
        if archivo.sha256 is None:
            clase = "sin_comprobar"
        elif cuentas[archivo.sha256] > 1:
            clase = "copia"
        else:
            clase = "variante"
        clasificados.append(replace(archivo, clasificacion=clase))
    return clasificados


async def _otras_ediciones(db: AsyncSession, series_id: UUID, issue: Issue) -> list[OtraEdicion]:
    """Publicaciones de la misma serie con el MISMO número y distinto volumen/formato.

    No agrupa por título+número: exige otra fila `Issue` y que algún discriminante
    (volumen o formato) cambie. Si no hay número, no se puede afirmar nada.
    """
    if not issue.issue_number:
        return []
    clave = natural_key(issue.issue_number)
    filas = (await db.execute(
        select(Issue).where(Issue.series_id == series_id, Issue.id != issue.id)
    )).scalars().all()
    otras: list[OtraEdicion] = []
    for fila in filas:
        if not fila.issue_number or natural_key(fila.issue_number) != clave:
            continue
        if fila.volume == issue.volume and fila.format == issue.format:
            continue
        otras.append(OtraEdicion(
            issue_id=str(fila.id), numero=fila.issue_number or "",
            volumen=int(fila.volume), formato=FORMATOS_LEGIBLES.get(
                getattr(fila.format, "value", ""), str(getattr(fila.format, "value", "")))))
    return sorted(otras, key=lambda o: (o.volumen, o.formato))
