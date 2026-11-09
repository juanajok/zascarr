"""Asociar otra fuente explícitamente — entrega A: proponer y comparar, SIN escribir (#129).

A consulta UNA fuente elegida (capacidad `busqueda`) y devuelve una comparación de solo lectura:
los datos acreditados de la serie local y de cada candidata, con `None` para lo que no consta.
No crea tokens, no escribe en la base, no aplica metadatos y no toca archivos. La confirmación es
la entrega B.

La clasificación de estados/cortesía es la de #133 (`DiscoveryService.buscar_en`), no el camino de
#128 que se traga `CortesiaEnEspera`. H13: Tebeosfera puede hacer 2 peticiones por intento y hasta
8 con sus fallbacks; A no promete «una petición», solo una acción de búsqueda.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.models import MetadataSource, Series
from zascarr.services.discovery import DiscoveryService
from zascarr.services.estados_fuentes import (
    CAPACIDAD_BUSQUEDA,
    FUENTE_SIN_RESULTADOS,
    EstadoFuente,
)

MAX_CONSULTA = 200
LIMITE_CANDIDATAS = 10


@dataclass(frozen=True)
class CandidataComparada:
    titulo: str
    anio: int | None
    editorial: str | None
    pais: str | None
    idioma: str | None
    id_externo: str
    sitio_url: str | None
    tradicion: str | None
    kind: str | None = None
    seleccionable: bool = True
    motivo_no_seleccionable: str | None = None


@dataclass(frozen=True)
class Comparacion:
    serie_id: str
    titulo_local: str
    anio_local: int | None
    editorial_local: str | None
    pais_local: str | None
    idioma_local: str | None
    fuente: MetadataSource
    consulta: str
    estado: EstadoFuente
    avisos: list[str] = field(default_factory=list)
    candidatas: list[CandidataComparada] = field(default_factory=list)


class SerieNoEncontradaError(LookupError):
    pass


def normalizar_consulta(q: str | None, *_: object) -> str:
    """Quita controles, colapsa espacios y acota a 200 caracteres (H15)."""
    texto = unicodedata.normalize("NFKC", q or "")
    texto = "".join(c for c in texto if not unicodedata.category(c).startswith("C"))
    texto = " ".join(texto.split())
    return texto[:MAX_CONSULTA].strip()


def _url_segura(url: str | None) -> str | None:
    """H14: solo http(s) con host; cualquier otra cosa se descarta."""
    if not url:
        return None
    try:
        parte = urlsplit(url)
    except ValueError:
        return None
    if parte.scheme not in ("http", "https") or not parte.hostname:
        return None
    if parte.username or parte.password:
        return None
    return url


async def comparar(db: AsyncSession, series_id: UUID, fuente: MetadataSource,
                   q: str | None = None) -> Comparacion:
    """Lee la serie, consulta UNA fuente y devuelve la comparación; cero escrituras."""
    serie = (await db.execute(
        select(Series).options(selectinload(Series.publisher)).where(Series.id == series_id)
    )).scalar_one_or_none()
    if serie is None:
        raise SerieNoEncontradaError(str(series_id))
    consulta = normalizar_consulta(q) or normalizar_consulta(serie.title)
    if not consulta:
        raise ValueError("consulta vacía")
    busqueda = await DiscoveryService(db).buscar_en(fuente, consulta, LIMITE_CANDIDATAS)
    estado = busqueda.detalles[fuente.value]
    avisos = list(busqueda.avisos)
    candidatas: list[CandidataComparada] = []
    for r in busqueda.resultados[:LIMITE_CANDIDATAS]:
        sagas = fuente is MetadataSource.TEBEOSFERA and r.kind == "saga"
        candidatas.append(CandidataComparada(
            titulo=r.title,
            anio=r.start_year,
            editorial=r.editorial,
            pais=r.pais,
            idioma=r.idioma,
            id_externo=r.external_id,
            sitio_url=_url_segura(r.site_url),
            tradicion=(r.tradition_guess.value if r.tradition_guess is not None else None),
            kind=r.kind,
            seleccionable=not sagas,
            motivo_no_seleccionable=(
                "Es una ficha de saga (obra), no de colección." if sagas else None),
        ))
    if candidatas and all(not c.seleccionable for c in candidatas):
        # Solo sagas: la web respondió, pero no hay ninguna ficha de colección que asociar.
        estado = EstadoFuente(fuente=fuente.value, capacidad=CAPACIDAD_BUSQUEDA,
                              estado=FUENTE_SIN_RESULTADOS,
                              motivo="Solo hay fichas de saga, no colecciones.")
        avisos.append("Tebeosfera solo devolvió fichas de saga, no de colecciones.")
    editorial_local = getattr(getattr(serie, "publisher", None), "name", None)
    return Comparacion(
        serie_id=str(serie.id), titulo_local=serie.title, anio_local=serie.start_year,
        editorial_local=editorial_local, pais_local=None, idioma_local=None,
        fuente=fuente, consulta=consulta, estado=estado, avisos=avisos,
        candidatas=candidatas,
    )
