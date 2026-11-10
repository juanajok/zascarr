# ruff: noqa: E501
"""CNV5-2 / #482: propuestas de fuentes por campo, **solo lectura**.

Carga un archivo ya asociado, consulta las fuentes encendidas y admitidas por su tradición y
construye opciones de ComicInfo campo a campo con el contrato puro de CNV5-1. No escribe BD,
`metadata_`, XML ni archivos; no busca identidades por título ni crea sesiones. Los clientes se
inyectan en las pruebas; en producción se abren desde las fábricas de cada fuente.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.comicinfo_write import ComicInfoInvalidoError, leer_campos, parsear
from zascarr.core.propuestas_comicinfo import (
    ESPERA_MAX_S,
    FuenteComicInfo,
    NivelDato,
    Presupuesto,
    PropuestaCampo,
    ResultadoFuente,
    construir_propuesta,
    crear_opcion,
    fuentes_para_tradicion,
)
from zascarr.models import File, FileFormat, Issue, Series
from zascarr.services.estados_fuentes import (
    FUENTE_APAGADA,
    FUENTE_FALLO_TRANSITORIO,
    FUENTE_LIMITE_DE_CORTESIA,
    FUENTE_OK,
    FUENTE_SIN_RESULTADOS,
)
from zascarr.utils.cbz import leer_comicinfo

logger = structlog.get_logger()

_IDENTIDADES = {
    FuenteComicInfo.COMIC_VINE: "comic_vine_id",
    FuenteComicInfo.ANILIST: "anilist_id",
    FuenteComicInfo.TEBEOSFERA: "tebeosfera_slug",
    FuenteComicInfo.GCD: "gcd_id",
}
_ETIQUETA_FUENTE = {
    FuenteComicInfo.COMIC_VINE: "Comic Vine",
    FuenteComicInfo.ANILIST: "AniList",
    FuenteComicInfo.TEBEOSFERA: "Tebeosfera",
    FuenteComicInfo.GCD: "GCD",
}
_ESTADO_MOTIVO = {
    FUENTE_APAGADA: "La fuente está apagada en Ajustes; no se ha consultado.",
    FUENTE_FALLO_TRANSITORIO: "La fuente no responde ahora; se muestran las demás.",
    FUENTE_LIMITE_DE_CORTESIA: "Hay que esperar unos segundos antes de volver a preguntar.",
    FUENTE_SIN_RESULTADOS: "La fuente no tiene datos nuevos para este tebeo.",
}


class ArchivoSinIssueError(LookupError):
    """El archivo no está enlazado a un número; no hay ficha de la que proponer."""


@dataclass(frozen=True)
class ResultadoPropuestas:
    """DTO serializable de una ronda de propuestas (sin escritura ni sesión)."""
    file_id: str
    serie_id: str | None
    titulo: str
    tradicion: str | None
    asociada: bool
    estados: tuple[ResultadoFuente, ...] = ()
    campos: tuple[PropuestaCampo, ...] = ()
    avisos: tuple[str, ...] = ()
    peticiones: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_id": self.file_id,
            "serie_id": self.serie_id,
            "titulo": self.titulo,
            "tradicion": self.tradicion,
            "asociada": self.asociada,
            "peticiones": self.peticiones,
            "avisos": list(self.avisos),
            "estados": [
                {"fuente": e.fuente.value, "estado": e.estado, "peticiones": e.peticiones,
                 "motivo": e.motivo}
                for e in self.estados
            ],
            "campos": [
                {
                    "tag": c.tag, "actual": c.actual, "estado": c.estado.value,
                    "bloqueado": c.bloqueado, "motivo": c.motivo,
                    "opciones": [
                        {"valor": o.valor, "fuente": o.fuente.value,
                         "nivel": o.nivel.value, "procedencia": o.procedencia,
                         "motivo": o.motivo}
                        for o in c.opciones
                    ],
                }
                for c in self.campos
            ],
        }


def _fabrica_real(fuente: FuenteComicInfo):
    """Fábrica por defecto: importa el cliente SOLO si esa fuente se va a consultar."""
    if fuente is FuenteComicInfo.COMIC_VINE:
        from zascarr.services.comic_vine import ComicVineClient
        return ComicVineClient(espera_max_s=ESPERA_MAX_S)
    if fuente is FuenteComicInfo.ANILIST:
        from zascarr.services.anilist import AniListClient
        return AniListClient(espera_max_s=ESPERA_MAX_S)
    if fuente is FuenteComicInfo.TEBEOSFERA:
        from zascarr.services.tebeosfera import TebeosferaClient
        return TebeosferaClient(espera_max_s=ESPERA_MAX_S)
    from zascarr.services.gcd import GCDClient
    return GCDClient(espera_max_s=ESPERA_MAX_S)


def _anio(valor: object) -> int | None:
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (date, datetime)):
        return valor.year
    texto = str(valor).strip()
    if len(texto) >= 4 and texto[:4].isdigit():
        return int(texto[:4])
    with contextlib.suppress(TypeError, ValueError):
        return int(texto)
    return None


def _personas(detalle: Mapping[str, Any] | None) -> dict[str, list[str]]:
    """Roles crudos de CV → tags; no adivina roles desconocidos."""
    from zascarr.core.propuestas_comicinfo import RolAutor, role_a_tag

    por_tag: dict[str, list[str]] = {}
    for credito in (detalle or {}).get("person_credits") or []:
        if not isinstance(credito, Mapping):
            continue
        nombre = credito.get("name")
        roles = str(credito.get("role") or "").lower().replace(" ", "_").split(",")
        for rol in roles:
            tag = role_a_tag(RolAutor(rol.strip())) if rol.strip() in RolAutor._value2member_map_ else None
            if tag and nombre:
                por_tag.setdefault(tag, []).append(str(nombre))
    return por_tag


class PropuestasComicInfoService:
    """Una ronda de propuestas para UN archivo. No escribe ni guarda sesión."""

    def __init__(self, db: AsyncSession, *, settings=None,
                 fabricas: Mapping[FuenteComicInfo, Callable[[FuenteComicInfo], Any]] | None = None,
                 actuales: Mapping[str, str | None] | None = None):
        self._db = db
        self._settings = settings
        self._fabricas = fabricas or {}
        self._actuales = actuales

    def _ajustes(self):
        if self._settings is not None:
            return self._settings
        from zascarr.config import get_settings
        return get_settings()

    async def _cargar(self, file_id: UUID):
        return (await self._db.execute(
            select(File, Issue, Series)
            .join(Issue, File.issue_id == Issue.id)
            .join(Series, Issue.series_id == Series.id)
            .where(File.id == file_id)
        )).first()

    def _encendidas(self, settings) -> set[FuenteComicInfo]:
        campos = {
            FuenteComicInfo.COMIC_VINE: "comicvine_enabled",
            FuenteComicInfo.ANILIST: "anilist_enabled",
            FuenteComicInfo.TEBEOSFERA: "tebeosfera_enabled",
            FuenteComicInfo.GCD: "gcd_enabled",
        }
        return {f for f, campo in campos.items() if bool(getattr(settings, campo, False))}

    @staticmethod
    def _clave_fuente(fuente: FuenteComicInfo, serie: Series) -> object | None:
        campo = _IDENTIDADES[fuente]
        valor = getattr(serie, campo, None)
        if fuente is FuenteComicInfo.TEBEOSFERA:
            return valor or None
        return valor

    async def proponer(self, file_id: UUID) -> ResultadoPropuestas:
        fila = await self._cargar(file_id)
        if fila is None:
            raise ArchivoSinIssueError("Ese archivo no existe o no tiene número enlazado.")
        file, issue, serie = fila
        if file.file_format is not FileFormat.CBZ:
            return ResultadoPropuestas(
                str(file.id), str(serie.id), serie.title, str(serie.tradition or ""),
                False, avisos=("Conviértelo primero a CBZ; no hay propuestas para CBR.",))
        actuales = await self._leer_actuales(Path(file.file_path))
        ajustes = self._ajustes()
        encendidas = self._encendidas(ajustes)
        admitidas = set(fuentes_para_tradicion(serie.tradition))
        estados = self._estados_base(encendidas, admitidas)
        identidades = {f: self._clave_fuente(f, serie) for f in FuenteComicInfo}
        if not any(identidades.values()):
            return ResultadoPropuestas(
                str(file.id), str(serie.id), serie.title, str(serie.tradition or ""), False,
                tuple(estados), (), ("Esta serie todavía no está asociada a ninguna fuente. "
                                     "Asóciala primero para poder completar sus datos.",))
        presupuesto = Presupuesto()
        opciones: dict[str, list] = {}
        avisos: list[str] = []
        for fuente in FuenteComicInfo:
            if fuente not in admitidas:
                continue
            if fuente not in encendidas:
                continue
            if not identidades[fuente]:
                estados.append(ResultadoFuente(
                    fuente, FUENTE_SIN_RESULTADOS, 0,
                    f"{_ETIQUETA_FUENTE[fuente]} no tiene una ficha asociada."))
                continue
            estado, valores, gastadas = await self._consultar(
                fuente, serie, issue, identidades[fuente], presupuesto, actuales)
            estados.append(ResultadoFuente(fuente, estado, gastadas,
                                           _ESTADO_MOTIVO.get(estado)))
            for tag, (valor, nivel, procedencia) in valores.items():
                opcion = crear_opcion(tag, valor, fuente=fuente, nivel=nivel,
                                      procedencia=procedencia)
                if opcion is not None and opcion.valor:
                    opciones.setdefault(tag, []).append(opcion)
        campos: list[PropuestaCampo] = []
        for tag in sorted(opciones):
            campos.append(construir_propuesta(tag, actuales.get(tag), opciones[tag]))
        if not campos:
            avisos.append("Las fuentes no tienen datos nuevos para este tebeo. "
                          "Puedes guardar lo que ya tienes.")
        return ResultadoPropuestas(
            str(file.id), str(serie.id), serie.title, str(serie.tradition or ""), True,
            tuple(estados), tuple(campos), tuple(avisos), presupuesto.peticiones)

    def _estados_base(self, encendidas: set[FuenteComicInfo],
                      admitidas: set[FuenteComicInfo]) -> list[ResultadoFuente]:
        estados: list[ResultadoFuente] = []
        for fuente in FuenteComicInfo:
            if fuente in encendidas and fuente in admitidas:
                continue
            motivo = (_ESTADO_MOTIVO[FUENTE_APAGADA] if fuente not in encendidas
                      else "La tradición no admite esta fuente; no se ha consultado.")
            estados.append(ResultadoFuente(fuente, FUENTE_APAGADA, 0, motivo))
        return estados

    async def _leer_actuales(self, ruta: Path) -> dict[str, str | None]:
        if self._actuales is not None:
            return dict(self._actuales)
        try:
            xml = await asyncio.to_thread(leer_comicinfo, ruta)
            if not xml:
                return {}
            return leer_campos(parsear(xml))
        except (OSError, ComicInfoInvalidoError):
            return {}

    async def _consultar(self, fuente: FuenteComicInfo, serie: Series, issue: Issue,
                         identidad: object, presupuesto: Presupuesto,
                         actuales: Mapping[str, str | None]):
        if presupuesto.agotado or not presupuesto.cabe(fuente):
            return FUENTE_LIMITE_DE_CORTESIA, {}, 0
        fabrica = self._fabricas.get(fuente, _fabrica_real)
        valores: dict[str, tuple[object, NivelDato, str | None]] = {}
        gastadas = 0
        try:
            contexto = fabrica(fuente)
            if hasattr(contexto, "__aenter__"):
                async with contexto as cliente:
                    valores, gastadas = await self._pedir(fuente, cliente, serie, issue,
                                                          identidad, presupuesto)
            else:
                valores, gastadas = await self._pedir(fuente, contexto, serie, issue,
                                                      identidad, presupuesto)
        except Exception:  # noqa: BLE001 — una fuente caída no debe borrar las demás
            logger.warning("propuestas.fuente_fallida", fuente=fuente.value)
            return FUENTE_FALLO_TRANSITORIO, {}, gastadas
        if not valores:
            return FUENTE_SIN_RESULTADOS, {}, gastadas
        return FUENTE_OK, valores, gastadas

    async def _pedir(self, fuente, cliente, serie: Series, issue: Issue, identidad: object,
                     presupuesto: Presupuesto):
        valores: dict[str, tuple[object, NivelDato, str | None]] = {}
        gastadas = 0

        def anotar(n: int) -> bool:
            nonlocal gastadas
            if not presupuesto.anotar(fuente, n):
                return False
            gastadas += n
            return True

        if fuente is FuenteComicInfo.COMIC_VINE:
            if not presupuesto.cabe(fuente, 1):
                return {}, gastadas
            volumen = await cliente.get_volume(int(identidad))
            gastadas += 1
            if not presupuesto.anotar(fuente, 1):
                return {}, gastadas
            if volumen is not None:
                valores["Publisher"] = (getattr(volumen, "publisher", None),
                                        NivelDato.SERIE, getattr(volumen, "site_url", None))
                if getattr(volumen, "start_year", None) is not None:
                    valores["Year"] = (volumen.start_year, NivelDato.SERIE, None)
            if getattr(issue, "comic_vine_id", None):
                if not presupuesto.cabe(fuente, 1):
                    return valores, gastadas
                detalle = await cliente.get_issue_detail(int(issue.comic_vine_id))
                gastadas += 1
                presupuesto.anotar(fuente, 1)
                if isinstance(detalle, Mapping):
                    if detalle.get("cover_date"):
                        valores["Year"] = (_anio(detalle["cover_date"]), NivelDato.NUMERO, None)
                    if detalle.get("description"):
                        valores["Summary"] = (detalle["description"], NivelDato.NUMERO, None)
                    for tag, nombres in _personas(detalle).items():
                        valores[tag] = (nombres, NivelDato.NUMERO, None)
            return valores, gastadas

        if fuente is FuenteComicInfo.TEBEOSFERA:
            if not presupuesto.cabe(fuente, 1):
                return {}, gastadas
            coleccion = await cliente.get_collection(str(identidad))
            gastadas += 1
            if not presupuesto.anotar(fuente, 1):
                return {}, gastadas
            if coleccion is not None:
                if getattr(coleccion, "editorial", None):
                    valores["Publisher"] = (coleccion.editorial, NivelDato.SERIE,
                                            getattr(coleccion, "url_ficha", None))
                if getattr(coleccion, "anio", None) is not None:
                    valores["Year"] = (coleccion.anio, NivelDato.SERIE,
                                       getattr(coleccion, "url_ficha", None))
            if getattr(issue, "issue_number", None):
                if not presupuesto.cabe(fuente, 1):
                    return valores, gastadas
                numero = await cliente.get_numero_de_coleccion(
                    str(identidad), issue.issue_number)
                gastadas += 1
                presupuesto.anotar(fuente, 1)
                if numero is not None:
                    if getattr(numero, "anio", None) is not None:
                        valores["Year"] = (numero.anio, NivelDato.NUMERO, None)
                    if getattr(numero, "paginas", None) is not None:
                        valores["PageCount"] = (numero.paginas, NivelDato.NUMERO, None)
            return valores, gastadas

        if fuente is FuenteComicInfo.GCD:
            if not presupuesto.cabe(fuente, 1):
                return {}, gastadas
            serie_gcd = await cliente.get_series(int(identidad))
            gastadas += 1
            if not presupuesto.anotar(fuente, 1):
                return {}, gastadas
            if serie_gcd is not None:
                if getattr(serie_gcd, "year_began", None) is not None:
                    valores["Year"] = (serie_gcd.year_began, NivelDato.SERIE, None)
                editorial = getattr(serie_gcd, "publisher", None)
                if editorial:
                    if not presupuesto.cabe(fuente, 1):
                        return valores, gastadas
                    nombre = await cliente.get_publisher(editorial)
                    gastadas += 1
                    presupuesto.anotar(fuente, 1)
                    if nombre:
                        valores["Publisher"] = (nombre, NivelDato.SERIE, None)
            return valores, gastadas

        # AniList: el cliente actual no tiene consulta por id. NO se busca por título
        # (asociar identidades es #129): si no hay método por id, no hay propuesta.
        metodo = getattr(cliente, "get_manga", None) or getattr(cliente, "get_by_id", None)
        if metodo is None:
            return {}, gastadas
        if not presupuesto.cabe(fuente, 1):
            return {}, gastadas
        candidato = await metodo(int(identidad))
        gastadas += 1
        presupuesto.anotar(fuente, 1)
        if candidato is None:
            return {}, gastadas
        if getattr(candidato, "start_year", None) is not None:
            valores["Year"] = (candidato.start_year, NivelDato.SERIE,
                               getattr(candidato, "site_url", None))
        if getattr(candidato, "description", None):
            valores["Summary"] = (candidato.description, NivelDato.SERIE,
                                  getattr(candidato, "site_url", None))
        return valores, gastadas
