"""Verificación host de la autorización de actualización; no ejecuta nada.

Valida el testigo HMAC emitido por la app tras reautenticar, la acción, el ID,
la ventana corta y el consumo único mediante un callback inyectado. No consulta
contraseñas, no lee la BD, no abre conexiones ni invoca systemd. La persistencia
duradera del consumo y la identidad de la instalación siguen fuera de este
módulo. No está conectado al auxiliar.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable
from enum import StrEnum

VERSION = 1
ACCION = "actualizar"
TTL_MAX = 300
DOMINIO = b"zascarr-ops4-autorizacion-v1\n"
TOLERANCIA_RELOJ_S = 120
MAX_TOKEN = 2048
_ID = re.compile(r"[0-9a-f]{32}\Z")
_CLAVES = frozenset({"v", "accion", "id", "creada", "expira"})


class CodigoAutorizacion(StrEnum):
    ACEPTADA = "aceptada"
    INVALIDA = "invalida"
    CADUCADA = "caducada"
    REPETIDA = "repetida"
    NO_DISPONIBLE = "no_disponible"


def _sin_duplicados(pares: list[tuple[str, object]]) -> dict[str, object]:
    resultado: dict[str, object] = {}
    for clave, valor in pares:
        if clave in resultado:
            raise ValueError("clave duplicada")
        resultado[clave] = valor
    return resultado


def verificar_autorizacion(
    token: object,
    *,
    clave: object,
    ahora: object,
    reclamar_uso: Callable[[str], bool],
    id_esperado: str | None = None,
) -> CodigoAutorizacion:
    """Orden: formato/firma → campos → ventana → consumo único.

    No devuelve el token ni sus datos. Cualquier excepción o callback que no
    devuelva exactamente `True` deniega. Un token válido no autoriza por sí
    solo: el callback debe acreditar el consumo durable.
    """
    if not isinstance(clave, bytes) or len(clave) != 32:
        return CodigoAutorizacion.NO_DISPONIBLE
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return CodigoAutorizacion.NO_DISPONIBLE
    if not isinstance(token, bytes) or not 1 < len(token) <= MAX_TOKEN:
        return CodigoAutorizacion.INVALIDA
    if token.count(b".") != 1:
        return CodigoAutorizacion.INVALIDA
    cuerpo, firma = token.split(b".")
    if len(firma) != 64:
        return CodigoAutorizacion.INVALIDA
    try:
        esperada = hmac.new(clave, DOMINIO + cuerpo, hashlib.sha256).hexdigest().encode("ascii")
    except Exception:  # noqa: BLE001
        return CodigoAutorizacion.NO_DISPONIBLE
    if not hmac.compare_digest(esperada, firma):
        return CodigoAutorizacion.INVALIDA
    try:
        datos = json.loads(cuerpo.decode("utf-8"), object_pairs_hook=_sin_duplicados)
    except (UnicodeDecodeError, ValueError, TypeError):
        return CodigoAutorizacion.INVALIDA
    if not isinstance(datos, dict) or set(datos) != _CLAVES:
        return CodigoAutorizacion.INVALIDA
    if datos["v"] != VERSION or type(datos["v"]) is not int:
        return CodigoAutorizacion.INVALIDA
    if datos["accion"] != ACCION:
        return CodigoAutorizacion.INVALIDA
    if not isinstance(datos["id"], str) or not _ID.fullmatch(datos["id"]):
        return CodigoAutorizacion.INVALIDA
    if id_esperado is not None and (
        not isinstance(id_esperado, str) or datos["id"] != id_esperado
    ):
        return CodigoAutorizacion.INVALIDA
    if type(datos["creada"]) is not int or type(datos["expira"]) is not int:
        return CodigoAutorizacion.INVALIDA
    creada, expira = datos["creada"], datos["expira"]
    if not 0 <= creada < 2**63 or not 0 <= expira < 2**63:
        return CodigoAutorizacion.INVALIDA
    if not 1 <= expira - creada <= TTL_MAX:
        return CodigoAutorizacion.INVALIDA
    if ahora > expira:
        return CodigoAutorizacion.CADUCADA
    if ahora < creada - TOLERANCIA_RELOJ_S:
        return CodigoAutorizacion.INVALIDA
    try:
        reclamada = reclamar_uso(datos["id"])
    except Exception:  # noqa: BLE001
        return CodigoAutorizacion.NO_DISPONIBLE
    return (
        CodigoAutorizacion.ACEPTADA
        if reclamada is True
        else CodigoAutorizacion.REPETIDA
    )
