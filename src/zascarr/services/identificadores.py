"""BL-R5 (#234): interpretar un identificador o enlace de una fuente, sin red.

Solo forma parte del contrato «primero el identificador»: la validación de forma
ocurre aquí, offline. La consulta a la fuente y el alta firmada siguen en
`services/discovery.py` y en el alta existente.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlsplit

from zascarr.models import MetadataSource


class IdentificadorInvalidoError(ValueError):
    """La forma del texto no corresponde a ningún identificador soportado."""


@dataclass(frozen=True)
class Identificador:
    fuente: MetadataSource
    valor: str
    enlace: str | None = None


@dataclass(frozen=True)
class ResolucionIdentificador:
    """Resultado de resolver un identificador: sin red, la red la hace el servicio."""

    camino: str                       # identificador | ya_local | invalido | sin_resultado | error
    identificador: Identificador | None = None
    resultado: Any | None = None      # DiscoveryResult, sin importar discovery aquí
    estado: Any | None = None         # EstadoFuente de #133
    motivo: str | None = None
    ya_local: Any | None = None       # Series local (solo camino ya_local)


def _url(texto: str) -> str:
    return texto if "://" in texto else f"https://{texto}"


def parsear_identificador(texto: str) -> Identificador:
    """Valida la FORMA y devuelve (fuente, valor). No hace ninguna petición."""
    original = (texto or "").strip()
    if not original:
        raise IdentificadorInvalidoError("Pega un identificador o el enlace de una ficha.")
    compacto = re.sub(r"[\s-]", "", original)
    if re.fullmatch(r"(?:97[89])?\d{9}[\dXx]", compacto) or re.fullmatch(r"97[89]\d{10}", compacto):
        raise IdentificadorInvalidoError(
            "Ese es un ISBN: identifica una publicación, no una serie. Su tratamiento se estudia "
            "aparte (#182), no se convierte en identificador de serie.")

    if "://" in original or original.lower().startswith(("www.", "comicvine.", "comics.",
                                                         "tebeosfera.", "anilist.")):
        partes = urlsplit(_url(original))
        host = (partes.hostname or "").lower()
        ruta = unquote(partes.path)
        if host.endswith("comicvine.gamespot.com"):
            m = re.search(r"(4050-\d+)", ruta) or re.search(r"(4050-\d+)", original)
            if not m:
                raise IdentificadorInvalidoError(
                    "Ese enlace de Comic Vine no lleva el identificador del volumen (4050-…).")
            return Identificador(MetadataSource.COMIC_VINE, str(int(m.group(1).split("-", 1)[1])),
                                 original)
        if host.endswith("comics.org"):
            m = re.search(r"/series/(\d+)", ruta)
            if not m:
                raise IdentificadorInvalidoError(
                    "Ese enlace de GCD no es de una serie (/series/…).")
            return Identificador(MetadataSource.GCD, m.group(1), original)
        if host.endswith("tebeosfera.com"):
            m = re.search(r"/colecciones/([^/]+?)(?:\.html)?/*$", ruta)
            if not m:
                raise IdentificadorInvalidoError(
                    "Ese enlace de Tebeosfera no es de una colección (/colecciones/…).")
            return Identificador(MetadataSource.TEBEOSFERA, m.group(1), original)
        if host.endswith("anilist.co"):
            m = re.search(r"/(?:manga|anime)/(\d+)", ruta)
            if not m:
                raise IdentificadorInvalidoError("Ese enlace de AniList no es de una ficha.")
            return Identificador(MetadataSource.ANILIST, m.group(1), original)
        raise IdentificadorInvalidoError(
            "Ese enlace no es de una fuente que ZascArr sepa resolver. Pega el enlace "
            "de la ficha en Comic Vine, Tebeosfera, GCD o AniList.")

    prefijado = re.fullmatch(
        r"(?i)(cv|comicvine|gcd|tb|tebeosfera|anilist|al)\s*:\s*(.+)", original)
    if prefijado:
        prefijo, valor = prefijado.group(1).lower(), prefijado.group(2).strip()
        if prefijo in ("cv", "comicvine"):
            m = re.fullmatch(r"(?:4050-)?(\d+)", valor)
            if not m:
                raise IdentificadorInvalidoError(
                    "Un identificador de Comic Vine es un volumen: cv:4050-12345 o cv:12345.")
            return Identificador(MetadataSource.COMIC_VINE, str(int(m.group(1))), original)
        if prefijo == "gcd":
            if not re.fullmatch(r"\d+", valor):
                raise IdentificadorInvalidoError("Un identificador de GCD es numérico: gcd:12345.")
            return Identificador(MetadataSource.GCD, str(int(valor)), original)
        if prefijo in ("tb", "tebeosfera"):
            if not re.fullmatch(r"[A-Za-z0-9._-]+", valor):
                raise IdentificadorInvalidoError(
                    "El identificador de Tebeosfera es su slug (letras, números, guiones).")
            return Identificador(MetadataSource.TEBEOSFERA, valor, original)
        if prefijo in ("anilist", "al"):
            if not re.fullmatch(r"\d+", valor):
                raise IdentificadorInvalidoError(
                    "Un identificador de AniList es numérico: al:12345.")
            return Identificador(MetadataSource.ANILIST, str(int(valor)), original)

    m = re.fullmatch(r"(4050-\d+)", original)
    if m:
        return Identificador(MetadataSource.COMIC_VINE,
                             str(int(m.group(1).split("-", 1)[1])), original)
    raise IdentificadorInvalidoError(
        "No sé a qué fuente pertenece. Escribe cv:, gcd:, tb: o al: delante del identificador, "
        "o pega el enlace de la ficha.")
