"""Protocolo v4 aislado: petición con autorización, sin contraseña.

Una línea JSON UTF-8 terminada en LF (máximo 4096 bytes) contiene `v=4`, `id`
32 hex, `accion="actualizar"`, `creada` (entero Unix de 63 bits), `autorizacion`
(base64url sin relleno del testigo app→host) y `firma` HMAC-SHA256 hex. La firma
cubre los cinco campos en orden fijo con dominio propio; la autorización se
verifica aparte y se consume una sola vez. No se acepta `prueba` ni campos
extra. El módulo no abre sockets, no lee BD, no persiste ni ejecuta nada.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
from typing import Any

VERSION = 4
ACCION = "actualizar"
MAX_LINEA = 4096
MAX_AUTORIZACION_BYTES = 2048
CLAVES = frozenset({"v", "id", "accion", "creada", "autorizacion", "firma"})
_DOMINIO = b"zascarr-ops/actualizar/v4\x00"
_ID = re.compile(r"[0-9a-f]{32}\Z")
_FIRMA = re.compile(r"[0-9a-f]{64}\Z")
_B64 = re.compile(r"[A-Za-z0-9_-]+\Z")


def _sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ValueError("clave repetida")
        resultado[clave] = valor
    return resultado


def decodificar_autorizacion(texto: object) -> bytes | None:
    """Decodifica base64url canónico sin relleno; None si no es válido."""
    if not isinstance(texto, str) or not 1 <= len(texto) <= 4096:
        return None
    if not _B64.fullmatch(texto):
        return None
    relleno = "=" * (-len(texto) % 4)
    try:
        crudo = base64.b64decode(
            (texto + relleno).encode("ascii"), altchars=b"-_", validate=True,
        )
    except (binascii.Error, ValueError, UnicodeEncodeError):
        return None
    if not 1 <= len(crudo) <= MAX_AUTORIZACION_BYTES:
        return None
    canonico = base64.urlsafe_b64encode(crudo).rstrip(b"=").decode("ascii")
    return crudo if canonico == texto else None


def _campos_validos(objeto: dict[str, Any]) -> bool:
    if set(objeto) != CLAVES:
        return False
    if type(objeto["v"]) is not int or objeto["v"] != VERSION:
        return False
    if not isinstance(objeto["id"], str) or not _ID.fullmatch(objeto["id"]):
        return False
    if not isinstance(objeto["accion"], str) or objeto["accion"] != ACCION:
        return False
    creada = objeto["creada"]
    if type(creada) is not int or not 0 <= creada < 2**63:
        return False
    if decodificar_autorizacion(objeto["autorizacion"]) is None:
        return False
    firma = objeto["firma"]
    return isinstance(firma, str) and bool(_FIRMA.fullmatch(firma))


def parsear(linea: bytes) -> dict[str, Any] | None:
    """Valida encuadre y esquema; no verifica HMAC, edad ni consumo."""
    if not isinstance(linea, bytes) or len(linea) > MAX_LINEA:
        return None
    if not linea.endswith(b"\n") or linea.count(b"\n") != 1 or linea.endswith(b"\r\n"):
        return None
    try:
        objeto = json.loads(linea[:-1].decode("utf-8"), object_pairs_hook=_sin_duplicados)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(objeto, dict) or not _campos_validos(objeto):
        return None
    return objeto


def firmar(clave: bytes, objeto: dict[str, Any]) -> str:
    """HMAC canónico de v4; el campo firma se ignora al calcular."""
    if type(clave) is not bytes or len(clave) != 32:
        raise ValueError("clave inválida")
    if not isinstance(objeto, dict) or not _campos_validos(objeto):
        raise ValueError("esquema inválido")
    campos = [
        objeto[k] for k in ("v", "id", "accion", "creada", "autorizacion")
    ]
    mensaje = json.dumps(campos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.new(clave, _DOMINIO + mensaje, hashlib.sha256).hexdigest()


def verificar_firma(clave: bytes, objeto: dict[str, Any]) -> bool:
    try:
        esperada = firmar(clave, objeto)
    except ValueError:
        return False
    return hmac.compare_digest(esperada, objeto["firma"])
