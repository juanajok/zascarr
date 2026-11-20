"""Emisión aislada de autorizaciones cortas tras reautenticar en la app.

El llamador debe ejecutar antes `zascarr.services.reautenticacion` y no emitir
si el resultado no es `OK`. Este módulo no comprueba contraseñas, no lee
ficheros, no persiste ni envía nada: solo construye un testigo HMAC de un uso
para que el host lo verifique. No está importado por la web ni por el auxiliar.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re

VERSION = 1
ACCION = "actualizar"
TTL_POR_DEFECTO = 60
TTL_MAX = 300
DOMINIO = b"zascarr-ops4-autorizacion-v1\n"
MAX_TOKEN = 2048
_ID = re.compile(r"[0-9a-f]{32}\Z")


def crear_autorizacion(
    *, clave: object, id_: object, ahora: object, ttl: object = TTL_POR_DEFECTO,
) -> bytes:
    """Devuelve `json.firma_hex`; no incluye contraseña, hash ni usuario.

    `ahora` y `ttl` son segundos. El fallo de validación lanza `ValueError` sin
    datos sensibles. La autorización solo acredita que la app la emitió para
    ese ID y ventana; el host decide además el consumo único.
    """
    if not isinstance(clave, bytes) or len(clave) != 32:
        raise ValueError("clave no válida")
    if not isinstance(id_, str) or not _ID.fullmatch(id_):
        raise ValueError("identificador no válido")
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        raise ValueError("instante no válido")
    if type(ttl) is not int or not 1 <= ttl <= TTL_MAX:
        raise ValueError("vigencia no válida")
    if ahora + ttl >= 2**63:
        raise ValueError("vigencia no válida")
    cuerpo = json.dumps(
        {"v": VERSION, "accion": ACCION, "id": id_, "creada": ahora,
         "expira": ahora + ttl},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    firma = hmac.new(clave, DOMINIO + cuerpo, hashlib.sha256).hexdigest().encode("ascii")
    token = cuerpo + b"." + firma
    if len(token) > MAX_TOKEN:
        raise ValueError("autorización demasiado grande")
    return token
