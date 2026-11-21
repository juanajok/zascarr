"""Formato experimental del registro A de OPS4; no emite ni persiste aprobaciones.

Solo convierte bytes canónicos a un objeto validado y viceversa. No comprueba
propietario, ruta, firmas, origen remoto, autenticidad ni durabilidad; no crea A.
No conectar a la UI ni al auxiliar.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

VERSION = 1
MAX_BYTES = 4096
_CLAVES = frozenset({
    "v", "sha", "head0", "instalacion", "origen", "huella_p", "nonce", "emitida",
})
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_HUELLA = re.compile(r"[0-9a-f]{64}\Z")
_NOMBRE = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
# Etiqueta experimental, no acredita el origen remoto ni una ref independiente.
_ORIGEN_EXPERIMENTAL = "origin/main"


class RegistroInvalidoError(ValueError):
    """El registro no cumple el formato cerrado."""


@dataclass(frozen=True)
class Registro:
    sha: str
    head0: str
    instalacion: str
    origen: str
    huella_p: str
    nonce: str
    emitida: int


def _validar(registro: Registro) -> None:
    if not isinstance(registro, Registro):
        raise RegistroInvalidoError("Registro inválido")
    if not all(type(x) is str and _SHA.fullmatch(x) for x in (registro.sha, registro.head0)):
        raise RegistroInvalidoError("SHA inválido")
    if type(registro.huella_p) is not str or not _HUELLA.fullmatch(registro.huella_p):
        raise RegistroInvalidoError("Huella inválida")
    if not all(type(x) is str and _NOMBRE.fullmatch(x) for x in (
        registro.instalacion, registro.nonce
    )):
        raise RegistroInvalidoError("Identidad inválida")
    if type(registro.origen) is not str or registro.origen != _ORIGEN_EXPERIMENTAL:
        raise RegistroInvalidoError("Origen inválido")
    if type(registro.emitida) is not int or registro.emitida <= 0:
        raise RegistroInvalidoError("Fecha inválida")


def serializar(registro: Registro) -> bytes:
    """Línea JSON canónica; no escribe ni sella nada."""
    _validar(registro)
    fila = {
        "v": VERSION, "sha": registro.sha, "head0": registro.head0,
        "instalacion": registro.instalacion, "origen": registro.origen,
        "huella_p": registro.huella_p, "nonce": registro.nonce,
        "emitida": registro.emitida,
    }
    datos = json.dumps(fila, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if len(datos) > MAX_BYTES:
        raise RegistroInvalidoError("Registro demasiado grande")
    return datos


def _sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    claves = [clave for clave, _ in pares]
    if len(claves) != len(set(claves)):
        raise RegistroInvalidoError("Clave duplicada")
    return dict(pares)


def deserializar(datos: object) -> Registro:
    """Aceptar solo una línea canónica y completa; no consulta el host."""
    if not isinstance(datos, (bytes, bytearray)) or len(datos) > MAX_BYTES:
        raise RegistroInvalidoError("Registro inválido")
    if not datos.endswith(b"\n") or datos.count(b"\n") != 1:
        raise RegistroInvalidoError("Registro inválido")
    try:
        fila = json.loads(bytes(datos[:-1]).decode("utf-8"), object_pairs_hook=_sin_duplicados)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise RegistroInvalidoError("Registro inválido") from exc
    if not isinstance(fila, dict) or frozenset(fila) != _CLAVES or fila.get("v") != VERSION:
        raise RegistroInvalidoError("Registro inválido")
    if type(fila["emitida"]) is not int or type(fila["v"]) is not int:
        raise RegistroInvalidoError("Tipo inválido")
    registro = Registro(
        sha=fila["sha"], head0=fila["head0"], instalacion=fila["instalacion"],
        origen=fila["origen"], huella_p=fila["huella_p"], nonce=fila["nonce"],
        emitida=fila["emitida"],
    )
    _validar(registro)
    if serializar(registro) != bytes(datos):
        raise RegistroInvalidoError("Registro no canónico")
    return registro


def vigente(registro: Registro, ahora: int) -> bool:
    """Ventana estricta [emitida, emitida+24h); no demuestra reloj fiable."""
    _validar(registro)
    if type(ahora) is not int:
        raise RegistroInvalidoError("Reloj inválido")
    return registro.emitida <= ahora < registro.emitida + 24 * 3600
