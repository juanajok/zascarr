"""Verificación aislada de la contraseña viva para OPS4; no accede a la BD.

El llamador aporta un lector que devuelve `(auth_mode, auth_password_hash)` de
la base de datos viva. Este módulo solo compara PBKDF2 en memoria y falla
cerrado ante modo desconocido, hash inválido, excepción o duda. No usa Docker,
red, socket, ficheros ni logs; no conserva la contraseña. Una respuesta True
significa únicamente que la contraseña coincide con el hash aportado, no que
la operación esté autorizada ni que el host sea confiable.
"""
from __future__ import annotations

import hashlib
import hmac
from collections.abc import Callable

MODOS_VALIDOS = frozenset({"password", "user_password"})
MAX_PRUEBA_BYTES = 512
MIN_ITERACIONES = 10_000
MAX_ITERACIONES = 2_000_000
MAX_HASH_CHARS = 256
MAX_SAL_BYTES = 64
DIGEST_BYTES = 32


def comprobar_hash(prueba: object, almacenado: object) -> bool:
    """Compara una contraseña con un hash `pbkdf2_sha256$iteraciones$sal$hash`.

    No lanza por datos del hash; devuelve False si algo no encaja. El host
    admite 10.000–2.000.000 iteraciones, sal de 1–64 bytes y digest de 32;
    la app genera actualmente 600.000 iteraciones con sal de 16 bytes.
    Un formato imposible se rechaza antes de calcular PBKDF2.
    """
    if not isinstance(prueba, str) or not isinstance(almacenado, str):
        return False
    if not 1 <= len(prueba) <= MAX_PRUEBA_BYTES or len(almacenado) > MAX_HASH_CHARS:
        return False
    try:
        encoded = prueba.encode("utf-8")
    except UnicodeEncodeError:
        return False
    if not 1 <= len(encoded) <= MAX_PRUEBA_BYTES:
        return False
    partes = almacenado.split("$")
    if len(partes) != 4 or partes[0] != "pbkdf2_sha256":
        return False
    try:
        iteraciones = int(partes[1])
        if not MIN_ITERACIONES <= iteraciones <= MAX_ITERACIONES:
            return False
        sal = bytes.fromhex(partes[2])
        esperado = bytes.fromhex(partes[3])
        if not 1 <= len(sal) <= MAX_SAL_BYTES or len(esperado) != DIGEST_BYTES:
            return False
        obtenido = hashlib.pbkdf2_hmac("sha256", encoded, sal, iteraciones)
    except (TypeError, ValueError, OverflowError):
        return False
    return bool(sal and esperado and hmac.compare_digest(obtenido, esperado))


def verificar_prueba_viva(
    prueba: object, leer: Callable[[], object]
) -> bool:
    """Lee credenciales y compara; cualquier excepción o dato raro deniega."""
    try:
        datos = leer()
    except Exception:  # noqa: BLE001 — un fallo de la BD no autoriza
        return False
    if not isinstance(datos, tuple) or len(datos) != 2:
        return False
    modo, almacenado = datos
    if not isinstance(modo, str) or modo not in MODOS_VALIDOS:
        return False
    return comprobar_hash(prueba, almacenado)
