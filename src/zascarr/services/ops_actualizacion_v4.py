"""Constructor aislado de la petición v4; no envía ni ejecuta nada.

Sustituye la contraseña de v3 por el testigo corto emitido tras reautenticar.
El testigo se transporta en base64url sin relleno y el HMAC de la petición
cubre los cinco campos canónicos. No registra el testigo ni la petición; no
abre sockets ni persiste. El envío único y la respuesta pertenecen a otra capa.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re

VERSION = 4
ACCION = "actualizar"
MAX_LINEA = 4096
MAX_AUTORIZACION_BYTES = 2048
_DOMINIO = b"zascarr-ops/actualizar/v4\x00"
_ID = re.compile(r"[0-9a-f]{32}\Z")


def construir_peticion_v4(
    clave: bytes, *, id: str, creada: int, autorizacion: bytes,
) -> bytes:
    """Construye una línea JSON firmada; no incluye contraseña ni hash."""
    if type(clave) is not bytes or len(clave) != 32:
        raise ValueError("clave inválida")
    if not isinstance(id, str) or not _ID.fullmatch(id):
        raise ValueError("identificador inválido")
    if type(creada) is not int or not 0 <= creada < 2**63:
        raise ValueError("instante inválido")
    if type(autorizacion) is not bytes or not 1 <= len(autorizacion) <= MAX_AUTORIZACION_BYTES:
        raise ValueError("autorización inválida")
    codificada = base64.urlsafe_b64encode(autorizacion).rstrip(b"=").decode("ascii")
    if len(codificada) > 4096:
        raise ValueError("autorización inválida")
    campos = [VERSION, id, ACCION, creada, codificada]
    mensaje = json.dumps(campos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    firma = hmac.new(clave, _DOMINIO + mensaje, hashlib.sha256).hexdigest()
    objeto = dict(zip(
        ("v", "id", "accion", "creada", "autorizacion"), campos, strict=True,
    ))
    objeto["firma"] = firma
    linea = json.dumps(objeto, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(linea) > MAX_LINEA:
        raise ValueError("petición demasiado larga")
    return linea
