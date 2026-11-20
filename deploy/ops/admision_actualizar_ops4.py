"""Admisión aislada de una petición de actualización; no ejecuta ni arranca nada.

Valida el esquema v3, la firma HMAC, la frescura y la repetición mediante
callbacks inyectados. No consulta la BD, no usa socket, no persiste el estado,
no adquiere cerrojos y no invoca systemd. La verificación real de contraseña y
la reclamación durable del identificador deben aportarlas el host; este módulo
solo ordena las comprobaciones y falla cerrado. No conectar al auxiliar hasta
implementar y probar esas piezas, el cerrojo y la ejecución.

La contraseña no se registra ni se conserva: se entrega al verificador y se
descarta. Una petición válida aquí no autoriza efectos por sí sola.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum

from deploy.ops import protocolo_actualizar_ops4 as protocolo

TOLERANCIA_RELOJ_S = 120


class CodigoAdmision(StrEnum):
    ACEPTADA = "aceptada"
    ESQUEMA_INVALIDO = "esquema_invalido"
    FIRMA_INVALIDA = "firma_invalida"
    CADUCADA = "caducada"
    REPETIDA = "repetida"
    PRUEBA_INVALIDA = "prueba_invalida"
    NO_DISPONIBLE = "no_disponible"


def admitir(
    linea: object,
    *,
    clave: object,
    ahora: object,
    verificar_prueba: Callable[[str], bool],
    reclamar_id: Callable[[str], bool],
) -> CodigoAdmision:
    """Orden: esquema → firma → frescura → reclamación → prueba.

    Las excepciones de los callbacks se convierten en rechazo; nunca se
    devuelve la petición, la contraseña ni un mensaje de excepción.
    """
    if not isinstance(clave, bytes) or len(clave) != 32:
        return CodigoAdmision.NO_DISPONIBLE
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return CodigoAdmision.NO_DISPONIBLE
    objeto = protocolo.parsear(linea)
    if objeto is None:
        return CodigoAdmision.ESQUEMA_INVALIDO
    if not protocolo.verificar_firma(clave, objeto):
        return CodigoAdmision.FIRMA_INVALIDA
    if abs(objeto["creada"] - ahora) > TOLERANCIA_RELOJ_S:
        return CodigoAdmision.CADUCADA
    try:
        valida = verificar_prueba(objeto["prueba"])
    except Exception:  # noqa: BLE001 — un fallo de autenticación no autoriza
        return CodigoAdmision.NO_DISPONIBLE
    if valida is not True:
        return CodigoAdmision.PRUEBA_INVALIDA
    try:
        reclamada = reclamar_id(objeto["id"])
    except Exception:  # noqa: BLE001 — un fallo de exclusión no autoriza
        return CodigoAdmision.NO_DISPONIBLE
    if reclamada is not True:
        return CodigoAdmision.REPETIDA
    return CodigoAdmision.ACEPTADA


def admitir_con_reloj(
    linea: object,
    *,
    clave: object,
    verificar_prueba: Callable[[str], bool],
    reclamar_id: Callable[[str], bool],
    reloj: Callable[[], float] = time.time,
) -> CodigoAdmision:
    """Variante que obtiene el reloj del host; un reloj inválido falla cerrado."""
    try:
        ahora = reloj()
    except Exception:  # noqa: BLE001
        return CodigoAdmision.NO_DISPONIBLE
    if type(ahora) not in (int, float) or not 0 <= ahora < 2**63:
        return CodigoAdmision.NO_DISPONIBLE
    return admitir(
        linea, clave=clave, ahora=int(ahora), verificar_prueba=verificar_prueba,
        reclamar_id=reclamar_id,
    )
