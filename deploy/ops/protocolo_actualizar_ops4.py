"""Contrato aislado propuesto para actualizar; no habilita ninguna operación.

Una línea UTF-8 JSON terminada en LF, de hasta 4096 bytes, contiene exactamente
v=3, id (32 hex minúsculos), accion="actualizar", creada (entero Unix no
negativo de 63 bits), prueba (contraseña UTF-8 de 1 a 512 bytes) y firma (64 hex
minúsculos). Los campos se firman como JSON UTF-8 canónico en orden fijo, con
prefijo de dominio, sin incluir la firma. El serializador escapa los controles;
no se normaliza Unicode. La prueba viaja en claro por el canal local: HMAC no la
cifra. Nunca debe registrarse ni pasarse por argv o entorno; su representación
byte a byte debe comprobarse con el verificador real antes de la integración.

Este módulo no consulta la BD, no autentica a la persona, no limita intentos,
no comprueba caducidad ni impide repeticiones, no persiste ni lanza procesos.
Una firma válida no equivale a autorización. Quien lo integre deberá implementar
esas puertas, proteger los secretos y acordar el contrato con el otro extremo.
No lo importa el auxiliar actual: v3 sigue rechazado en producción.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import Any

VERSION = 3
ACCION = "actualizar"
MAX_LINEA = 4096
MAX_PRUEBA = 512
CLAVES = frozenset({"v", "id", "accion", "creada", "prueba", "firma"})
_DOMINIO = b"zascarr-ops/actualizar/v3\x00"
_ID = re.compile(r"[0-9a-f]{32}\Z")
_FIRMA = re.compile(r"[0-9a-f]{64}\Z")


def _sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    resultado: dict[str, Any] = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ValueError("clave repetida")
        resultado[clave] = valor
    return resultado


def _campos_validos(objeto: dict[str, Any]) -> bool:
    if set(objeto) != CLAVES:
        return False
    if type(objeto["v"]) is not int or objeto["v"] != VERSION:
        return False
    if not isinstance(objeto["id"], str) or not _ID.fullmatch(objeto["id"]):
        return False
    if objeto["accion"] != ACCION or not isinstance(objeto["accion"], str):
        return False
    creada = objeto["creada"]
    if type(creada) is not int or not 0 <= creada < 2**63:
        return False
    prueba = objeto["prueba"]
    if not isinstance(prueba, str):
        return False
    try:
        if not 1 <= len(prueba.encode("utf-8")) <= MAX_PRUEBA:
            return False
    except UnicodeEncodeError:
        return False
    firma = objeto["firma"]
    return isinstance(firma, str) and bool(_FIRMA.fullmatch(firma))


def parsear(linea: bytes) -> dict[str, Any] | None:
    """Valida el encuadre y esquema; no valida firma, edad ni repetición."""
    if not isinstance(linea, bytes) or len(linea) > MAX_LINEA:
        return None
    if not linea.endswith(b"\n") or linea.count(b"\n") != 1:
        return None
    try:
        objeto = json.loads(linea[:-1].decode("utf-8"), object_pairs_hook=_sin_duplicados)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(objeto, dict) or not _campos_validos(objeto):
        return None
    return objeto


def firmar(clave: bytes, objeto: dict[str, Any]) -> str:
    """Calcula HMAC para un objeto válido; su campo firma se ignora al firmar."""
    if not isinstance(clave, bytes) or len(clave) != 32:
        raise ValueError("clave inválida")
    if not isinstance(objeto, dict) or not _campos_validos(objeto):
        raise ValueError("esquema inválido")
    campos = [objeto[k] for k in ("v", "id", "accion", "creada", "prueba")]
    mensaje = json.dumps(campos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hmac.new(clave, _DOMINIO + mensaje, hashlib.sha256).hexdigest()


def verificar_firma(clave: bytes, objeto: dict[str, Any]) -> bool:
    """Comprueba únicamente integridad y posesión de la clave compartida."""
    try:
        esperada = firmar(clave, objeto)
    except ValueError:
        return False
    return hmac.compare_digest(esperada, objeto["firma"])
