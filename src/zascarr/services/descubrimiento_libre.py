# ruff: noqa: E501
"""Descubrir LIBRE: resultados de búsqueda firmados por el servidor, sin carpeta de origen (I2 de #114).

Antes, el formulario de «Crear serie» reenviaba como campos ocultos lo que el navegador quisiera (`title`, `external_id`,
`cover_url`…) y esos datos pasaban a la creación tal cual. Ahora el servidor firma cada resultado **al buscar**, con el
contexto sin grupo (`CLAVE_SIN_GRUPO`, I1), y lo único que vuelve del navegador es ese token y la tradición que elige la
persona: la vista previa y el alta salen de lo que el servidor vio, nunca de lo que reenvía el navegador.

Los resultados que no se pueden firmar (título o identificador que no caben en lo que la base guarda, caracteres no
firmables) se omiten y se cuentan, igual que en el descubrimiento por grupo, y la portada solo sale si cumple la política de
H1. Reutiliza `DescubrimientoDeGrupo._preparar` para que las dos entradas apliquen EXACTAMENTE la misma regla.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from zascarr.models import ComicTradition
from zascarr.services.descubrimiento_grupo import DescubrimientoDeGrupo
from zascarr.services.discovery import DiscoveryResult
from zascarr.services.tokens_revision import CLAVE_SIN_GRUPO, crear_token_candidata


@dataclass(frozen=True)
class ResultadoFirmado:
    """Un resultado de búsqueda tal como se muestra y se firmó. `token` es lo único que se reenvía."""
    token: str
    fuente: str
    titulo: str
    anio: int | None
    descripcion: str | None
    portada: str | None             # la URL del proxy con lista blanca; nunca la del CDN externo
    sitio_url: str | None
    sugerida: ComicTradition | None  # la suposición de la fuente: una pista, nunca un valor elegido
    procedencia: str | None          # de dónde sale la sugerencia; sin sugerencia, no hay procedencia


def firmar_resultados(resultados: list[DiscoveryResult], secret: str, *,
                      ahora: float | None = None) -> tuple[list[ResultadoFirmado], int]:
    """(resultados firmados, cuántos se omitieron por no poder firmarse)."""
    preparados, omitidas = DescubrimientoDeGrupo._preparar(resultados)
    firmados: list[ResultadoFirmado] = []
    for p in preparados:
        f = p.firmable
        portada = None if f.cover_url is None else "/ui/descubrir/portada?" + urlencode(
            {"url": f.cover_url, "source": f.fuente})
        firmados.append(ResultadoFirmado(
            token=crear_token_candidata(CLAVE_SIN_GRUPO, f, secret, ahora=ahora), fuente=f.fuente, titulo=f.titulo,
            anio=f.anio, descripcion=f.descripcion, portada=portada, sitio_url=p.sitio_url,
            sugerida=None if f.tradicion is None else ComicTradition(f.tradicion),
            procedencia=f.procedencia))
    return firmados, omitidas
