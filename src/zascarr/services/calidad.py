"""BL-D3 (#154): comparar la calidad de una edición con candidatos reales.

No sustituye ni borra archivos: produce una propuesta que la UI enseña y que el
coleccionista confirma. La puntuación es deliberadamente conservadora y solo
usa lo que consta (`source_tag`, `width_px`, `quality` y el título del release).
"""
from __future__ import annotations

from dataclasses import dataclass

from zascarr.models import File
from zascarr.services.prowlarr import SearchResult
from zascarr.utils.naming import normalize_series_name, parse_comic_filename

NIVELES = {3: "alta", 2: "media", 1: "básica", 0: "sin datos"}


@dataclass(frozen=True)
class Calidad:
    puntuacion: int
    etiqueta: str
    detalle: str


def _etiqueta(puntuacion: int) -> str:
    return NIVELES.get(puntuacion, "sin datos")


def calidad_de_archivo(archivo: File | None) -> Calidad:
    """Calidad de lo que ya tienes, con los datos del triaje del archivo."""
    if archivo is None:
        return Calidad(0, "sin datos", "No hay archivo")
    fuente = (getattr(archivo, "source_tag", None) or "").casefold()
    ancho = getattr(archivo, "width_px", None) or 0
    guardada = (getattr(archivo, "quality", None) or "").casefold()
    puntos = 0
    if fuente == "digital" or guardada in ("alta", "digital", "mejor"):
        puntos = 3
    elif fuente == "scan_hq" or guardada in ("media", "buena"):
        puntos = 2
    elif fuente in ("scan", "c2c") or guardada in ("baja", "basica"):
        puntos = 1
    if ancho >= 2400:
        puntos = max(puntos, 3)
    elif ancho >= 1600:
        puntos = max(puntos, 2)
    elif ancho >= 900:
        puntos = max(puntos, 1)
    if ancho:
        detalle = f"{ancho} px"
    elif fuente:
        detalle = fuente.replace("_", " ")
    else:
        detalle = "sin datos de resolución"
    return Calidad(puntos, _etiqueta(puntos), detalle)


def calidad_de_titulo(titulo: str) -> Calidad:
    """Calidad que declara el título de un release; desconocida si no declara nada."""
    t = (titulo or "").casefold()
    if any(m in t for m in ("digital", "webrip", "web-dl", "dcp")):
        return Calidad(3, "alta", "digital")
    if any(m in t for m in ("scan_hq", "c2c", "hd", "uhd", "4k", "1080")):
        return Calidad(2, "media", "escaneo de alta calidad")
    if any(m in t for m in ("scan", "escaneo")):
        return Calidad(1, "básica", "escaneo")
    return Calidad(0, "sin datos", "el título no declara calidad")


@dataclass(frozen=True)
class MejoraCandidata:
    resultado: SearchResult
    calidad: Calidad


@dataclass(frozen=True)
class ArchivoActual:
    nombre: str
    calidad: Calidad


def filtrar_mejoras(resultados: list[SearchResult], archivos: list[File],
                    numero: str, serie: str, *, min_tier: int = 1) -> list[MejoraCandidata]:
    """Solo candidatos del MISMO número/serie y con calidad estrictamente mejor."""
    if not archivos:
        return []
    actual = max((calidad_de_archivo(a).puntuacion for a in archivos), default=0)
    try:
        numero_entero = int(str(numero).strip())
    except (TypeError, ValueError):
        return []
    serie_norm = normalize_series_name(serie or "")
    vistos: set[str] = set()
    mejores: list[MejoraCandidata] = []
    for r in resultados:
        if not r.download_url or r.download_url in vistos:
            continue
        parsed = parse_comic_filename(r.title)
        if parsed.edition_kind is not None:
            continue
        texto = (parsed.issue_number or "").strip()
        if not texto.isdigit() or int(texto) != numero_entero:
            continue
        if not serie_norm or normalize_series_name(parsed.series or "") != serie_norm:
            continue
        calidad = calidad_de_titulo(r.title)
        if calidad.puntuacion < min_tier or calidad.puntuacion <= actual:
            continue
        vistos.add(r.download_url)
        mejores.append(MejoraCandidata(r, calidad))
    mejores.sort(key=lambda m: (-m.calidad.puntuacion, -m.resultado.seeders))
    return mejores


def archivos_actuales(archivos: list[File]) -> list[ArchivoActual]:
    return [ArchivoActual(getattr(a, "file_name", "archivo"),
                          calidad_de_archivo(a)) for a in archivos]


@dataclass(frozen=True)
class ResultadoMejoras:
    ok: bool
    error: str | None
    actual: list[ArchivoActual]
    candidatos: list[MejoraCandidata]


async def buscar_mejoras(db, serie, issue, *, min_tier: int = 1) -> ResultadoMejoras:
    """Busca en Prowlarr candidatos del mismo número con calidad mejor. Solo lectura."""
    from sqlalchemy import select

    from zascarr.services.prowlarr import ProwlarrClient
    from zascarr.utils.cortesia import CortesiaEnEspera, FuenteApagada

    archivos = (await db.execute(
        select(File).where(File.issue_id == issue.id, File.is_missing.is_(False))
    )).scalars().all()
    actuales = archivos_actuales(list(archivos))
    if not archivos:
        return ResultadoMejoras(False, "Este número no tiene ningún archivo que mejorar.",
                                actuales, [])
    if not str(issue.issue_number or "").strip().isdigit():
        return ResultadoMejoras(False, "Este número no se puede comparar con un release.",
                                actuales, [])
    from zascarr.config import get_settings
    ajustes = get_settings()
    if not (ajustes.prowlarr_enabled and ajustes.prowlarr_url and ajustes.prowlarr_api_key):
        return ResultadoMejoras(False,
                                "Prowlarr no está activo o le falta la URL o la clave de API.",
                                actuales, [])
    try:
        resultados = await ProwlarrClient().search(
            f"{serie.title} {issue.issue_number}", categories=[7030, 7020])
    except (CortesiaEnEspera, FuenteApagada):
        return ResultadoMejoras(False, "Prowlarr no está disponible ahora mismo.", actuales, [])
    except Exception:
        return ResultadoMejoras(False, "No se pudo consultar Prowlarr.", actuales, [])
    candidatos = filtrar_mejoras(
        resultados, list(archivos), str(issue.issue_number), serie.title,
        min_tier=min_tier)
    if not candidatos:
        return ResultadoMejoras(False,
                                "No se encontró una edición con calidad mejor que la tuya.",
                                actuales, [])
    return ResultadoMejoras(True, None, actuales, candidatos)
