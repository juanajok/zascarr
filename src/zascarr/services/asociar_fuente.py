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

import hashlib
import json
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.config import get_settings
from zascarr.models import MetadataSource, Series
from zascarr.services.discovery import DiscoveryService
from zascarr.services.estados_fuentes import (
    CAPACIDAD_BUSQUEDA,
    FUENTE_SIN_RESULTADOS,
    EstadoFuente,
)
from zascarr.services.tokens_revision import (
    AsociacionFirmada,
    crear_token_asociacion,
    id_canonico,
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
    fuente: str | None = None
    token: str | None = None


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


class SerieSinIdentidadError(LookupError):
    """D-A: A solo se ofrece para series que ya tienen al menos una identidad de fuente."""


_IDENTIDADES = ("comic_vine_id", "anilist_id", "tebeosfera_slug", "gcd_id")


def tiene_identidad(serie: Series) -> bool:
    return any(getattr(serie, campo, None) for campo in _IDENTIDADES)


def _ids_de_serie(serie: Series) -> dict[str, object]:
    return {campo: getattr(serie, campo, None) for campo in _IDENTIDADES}


def _serializar_fecha(valor: object) -> object:
    if isinstance(valor, datetime):
        return valor.isoformat()
    return valor


def huella_de_asociacion(serie: Series, candidata: CandidataComparada) -> str:
    """Huella canónica A/B (§8.10): claves explícitas, listas ordenadas y JSON estable."""
    metadata = getattr(serie, "metadata_", None) or {}
    asociaciones = metadata.get("asociaciones", []) if isinstance(metadata, dict) else []
    activas = []
    if isinstance(asociaciones, list):
        for entrada in asociaciones:
            if not isinstance(entrada, dict) or entrada.get("deshecho"):
                continue
            activas.append({k: _serializar_fecha(entrada.get(k)) for k in sorted(entrada)})
    activas.sort(key=lambda e: (str(e.get("fuente")), str(e.get("id_externo")),
                                str(e.get("operacion_id"))))
    datos = {
        "version": 1,
        "serie_id": str(serie.id),
        "titulo": serie.title,
        "anio": serie.start_year,
        "tradicion": getattr(getattr(serie, "tradition", None), "value", None),
        "ids": _ids_de_serie(serie),
        "metadata_source": getattr(serie, "metadata_source", None),
        "locked_fields": sorted(getattr(serie, "locked_fields", None) or []),
        "asociaciones": activas,
    }
    datos["candidata"] = {
        "fuente": candidata.fuente, "id_externo": candidata.id_externo, "entidad": "serie",
        "kind": candidata.kind, "titulo": candidata.titulo, "anio": candidata.anio,
        "sitio_url": candidata.sitio_url,
    }
    return hashlib.sha256(json.dumps(
        datos, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


async def comparar(db: AsyncSession, series_id: UUID, fuente: MetadataSource,
                   q: str | None = None) -> Comparacion:
    """Lee la serie, consulta UNA fuente y devuelve la comparación; cero escrituras."""
    serie = (await db.execute(
        select(Series).options(selectinload(Series.publisher)).where(Series.id == series_id)
    )).scalar_one_or_none()
    if serie is None:
        raise SerieNoEncontradaError(str(series_id))
    if not tiene_identidad(serie):
        # D-A (2026-11-09): sin identidad no se consulta ni se ofrece asociar.
        raise SerieSinIdentidadError(str(series_id))
    consulta = normalizar_consulta(q) or normalizar_consulta(serie.title)
    if not consulta:
        raise ValueError("consulta vacía")
    busqueda = await DiscoveryService(db).buscar_en(fuente, consulta, LIMITE_CANDIDATAS)
    estado = busqueda.detalles[fuente.value]
    avisos = list(busqueda.avisos)
    candidatas: list[CandidataComparada] = []
    secreto = get_settings().secret_key
    for r in busqueda.resultados[:LIMITE_CANDIDATAS]:
        sagas = fuente is MetadataSource.TEBEOSFERA and r.kind == "saga"
        canonico = id_canonico(fuente.value, r.external_id)
        seleccionable = not sagas and canonico is not None
        motivo = None
        if sagas:
            motivo = "Es una ficha de saga (obra), no de colección."
        elif canonico is None:
            motivo = "El identificador de esa ficha no es válido."
        candidata = CandidataComparada(
            titulo=r.title, anio=r.start_year, editorial=r.editorial, pais=r.pais,
            idioma=r.idioma, id_externo=canonico or r.external_id,
            sitio_url=_url_segura(r.site_url),
            tradicion=(r.tradition_guess.value if r.tradition_guess is not None else None),
            kind=r.kind, seleccionable=seleccionable,
            motivo_no_seleccionable=motivo, fuente=fuente.value,
        )
        if seleccionable and secreto:
            huella = huella_de_asociacion(serie, candidata)
            firmada = AsociacionFirmada(
                version=1, entidad="serie", kind=r.kind, fuente=fuente.value,
                id_externo=candidata.id_externo, titulo=candidata.titulo,
                anio=candidata.anio, sitio_url=candidata.sitio_url, huella=huella,
                operacion=str(uuid4()), serie_id=str(serie.id))
            token = crear_token_asociacion(firmada, secreto)
            candidata = CandidataComparada(**{**candidata.__dict__, "token": token})
        candidatas.append(candidata)
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
