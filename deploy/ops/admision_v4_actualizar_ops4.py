"""Admisión v4 aislada: firma de petición y autorización con consumo único.

No ejecuta, no lee hashes ni BD, no abre sockets y no persiste. La petición
v4 no contiene contraseña; el host verifica el testigo emitido por la app y
exige que su ID coincida con el de la petición. El callback de consumo debe ser
durable y separado del registro v3. Una aceptación solo admite la petición:
las guardas de instalación, cerrojo, estado y unidad siguen pendientes.
"""
from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

from deploy.ops import protocolo_actualizar_v4_ops4 as protocolo
from deploy.ops.verificador_autorizacion_ops4 import (
    CodigoAutorizacion,
    verificar_autorizacion,
)

TOLERANCIA_RELOJ_S = 120


class CodigoV4(StrEnum):
    ACEPTADA = "aceptada"
    ESQUEMA_INVALIDO = "esquema_invalido"
    FIRMA_INVALIDA = "firma_invalida"
    CADUCADA = "caducada"
    AUTORIZACION_INVALIDA = "autorizacion_invalida"
    REPETIDA = "repetida"
    NO_DISPONIBLE = "no_disponible"


def admitir_v4(
    linea: object,
    *,
    clave: object,
    ahora: object,
    reclamar_uso: Callable[[str], bool],
) -> CodigoV4:
    """Orden: esquema → firma de petición → frescura → testigo → consumo."""
    if type(clave) is not bytes or len(clave) != 32:
        return CodigoV4.NO_DISPONIBLE
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return CodigoV4.NO_DISPONIBLE
    objeto = protocolo.parsear(linea)
    if objeto is None:
        return CodigoV4.ESQUEMA_INVALIDO
    if not protocolo.verificar_firma(clave, objeto):
        return CodigoV4.FIRMA_INVALIDA
    if abs(objeto["creada"] - ahora) > TOLERANCIA_RELOJ_S:
        return CodigoV4.CADUCADA
    testigo = protocolo.decodificar_autorizacion(objeto["autorizacion"])
    if testigo is None:
        return CodigoV4.AUTORIZACION_INVALIDA
    resultado = verificar_autorizacion(
        testigo, clave=clave, ahora=ahora, reclamar_uso=reclamar_uso,
        id_esperado=objeto["id"],
    )
    if resultado is CodigoAutorizacion.ACEPTADA:
        return CodigoV4.ACEPTADA
    if resultado is CodigoAutorizacion.CADUCADA:
        return CodigoV4.CADUCADA
    if resultado is CodigoAutorizacion.REPETIDA:
        return CodigoV4.REPETIDA
    if resultado is CodigoAutorizacion.NO_DISPONIBLE:
        return CodigoV4.NO_DISPONIBLE
    return CodigoV4.AUTORIZACION_INVALIDA
