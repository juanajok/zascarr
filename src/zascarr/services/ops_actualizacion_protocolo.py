"""Constructor aislado del protocolo de actualización v3, aún no operativo.

No autoriza, envía ni ejecuta operaciones. La prueba viaja en claro en el
resultado: el HMAC protege su integridad, no su confidencialidad. El llamante
no debe registrar ni imprimir la petición. El identificador y el instante son
explícitos; corresponde al futuro integrador garantizar unicidad y vigencia.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re

VERSION = 3
ACCION = "actualizar"
MAX_LINEA = 4096
MAX_PRUEBA = 512
_DOMINIO = b"zascarr-ops/actualizar/v3\x00"
_ID = re.compile(r"[0-9a-f]{32}\Z")


def construir_peticion(clave: bytes, *, id: str, creada: int, prueba: str) -> bytes:
    """Construye una línea JSON UTF-8 firmada; rechaza cualquier dato inválido.

    La clave debe contener exactamente 32 bytes. El tiempo es un entero Unix
    no negativo de 63 bits, y la prueba ocupa entre 1 y 512 bytes UTF-8.
    """
    if not isinstance(clave, bytes) or len(clave) != 32:
        raise ValueError("clave inválida")
    if not isinstance(id, str) or not _ID.fullmatch(id):
        raise ValueError("identificador inválido")
    if type(creada) is not int or not 0 <= creada < 2**63:
        raise ValueError("instante inválido")
    if not isinstance(prueba, str):
        raise ValueError("prueba inválida")
    try:
        longitud = len(prueba.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("prueba inválida") from None
    if not 1 <= longitud <= MAX_PRUEBA:
        raise ValueError("prueba inválida")

    campos = [VERSION, id, ACCION, creada, prueba]
    mensaje = json.dumps(campos, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    firma = hmac.new(clave, _DOMINIO + mensaje, hashlib.sha256).hexdigest()
    objeto = dict(zip(("v", "id", "accion", "creada", "prueba"), campos, strict=True))
    objeto["firma"] = firma
    linea = json.dumps(objeto, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(linea) > MAX_LINEA:
        raise ValueError("petición demasiado larga")
    return linea
