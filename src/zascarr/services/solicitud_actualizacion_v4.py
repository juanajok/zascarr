"""Servicio aislado de solicitud v4; no hay ruta web ni auxiliar conectado.

Encadena la composición app-side (`preparar_autorizacion`), la construcción de
la petición v4 y el transporte inyectable. La puerta `habilitada` es `False` por
defecto. No lee la clave, no registra contraseña/testigo, no abre sockets salvo
por el transporte inyectado y no persiste ni ejecuta la actualización. Un
resultado `INCIERTA` no autoriza reintento ciego: no se ha reconciliado estado.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum

from zascarr.config import Settings
from zascarr.services.actualizacion_transporte_v4 import (
    CodigoTransporteV4,
    IntercambioInciertoError,
    pedir_actualizacion_v4,
)
from zascarr.services.autorizacion_actualizacion import (
    Comprobar,
    PreparacionAutorizacion,
    ResultadoAutorizacion,
    preparar_autorizacion,
)
from zascarr.services.ops_actualizacion_v4 import construir_peticion_v4


class ResultadoSolicitudV4(StrEnum):
    NO_HABILITADA = "no_habilitada"
    CONFIRMACION_REQUERIDA = "confirmacion_requerida"
    CONTRASENA_INVALIDA = "contrasena_invalida"
    AUTENTICACION_NO_ACTIVADA = "autenticacion_no_activada"
    CONTRASENA_INCORRECTA = "contrasena_incorrecta"
    OCUPADA = "ocupada"
    BLOQUEADA = "bloqueada"
    NO_DISPONIBLE = "no_disponible"
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    INCIERTA = "incierta"
    RESPUESTA_INVALIDA = "respuesta_invalida"


@dataclass(frozen=True)
class SolicitudV4:
    resultado: ResultadoSolicitudV4
    id: str | None = None
    hasta_epoch: float | None = None


_MAPA_PREPARACION = {
    ResultadoAutorizacion.NO_HABILITADA: ResultadoSolicitudV4.NO_HABILITADA,
    ResultadoAutorizacion.CONFIRMACION_REQUERIDA:
        ResultadoSolicitudV4.CONFIRMACION_REQUERIDA,
    ResultadoAutorizacion.CONTRASENA_INVALIDA:
        ResultadoSolicitudV4.CONTRASENA_INVALIDA,
    ResultadoAutorizacion.AUTENTICACION_NO_ACTIVADA:
        ResultadoSolicitudV4.AUTENTICACION_NO_ACTIVADA,
    ResultadoAutorizacion.CONTRASENA_INCORRECTA:
        ResultadoSolicitudV4.CONTRASENA_INCORRECTA,
    ResultadoAutorizacion.OCUPADA: ResultadoSolicitudV4.OCUPADA,
    ResultadoAutorizacion.BLOQUEADA: ResultadoSolicitudV4.BLOQUEADA,
    ResultadoAutorizacion.NO_DISPONIBLE: ResultadoSolicitudV4.NO_DISPONIBLE,
}


async def solicitar_actualizacion_v4(
    settings: Settings,
    *,
    clave: object,
    contrasena: object,
    entiendo: object,
    habilitada: bool = False,
    ahora: int | None = None,
    comprobar: Comprobar | None = None,
    preparar=preparar_autorizacion,
    construir=construir_peticion_v4,
    enviar=pedir_actualizacion_v4,
    conversar=None,
) -> SolicitudV4:
    """Ejecuta la cadena y devuelve un código cerrado; sin reintento."""
    instante = int(time.time()) if ahora is None else ahora
    if type(instante) is not int or not 0 <= instante < 2**63:
        return SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE)
    kwargs = {
        "clave": clave, "contrasena": contrasena, "entiendo": entiendo,
        "habilitada": habilitada, "ahora": instante,
    }
    if comprobar is not None:
        kwargs["comprobar"] = comprobar
    try:
        preparacion = await preparar(settings, **kwargs)
    except Exception:  # noqa: BLE001 — una composición dudosa no autoriza
        return SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE)
    if not isinstance(preparacion, PreparacionAutorizacion):
        return SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE)
    if preparacion.resultado is not ResultadoAutorizacion.PREPARADA:
        return SolicitudV4(
            _MAPA_PREPARACION.get(
                preparacion.resultado, ResultadoSolicitudV4.NO_DISPONIBLE,
            ),
            hasta_epoch=preparacion.hasta_epoch,
        )
    if not isinstance(preparacion.id, str) or preparacion.autorizacion is None:
        return SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE)
    try:
        peticion = construir(
            clave, id=preparacion.id, creada=instante,
            autorizacion=preparacion.autorizacion,
        )
    except Exception:  # noqa: BLE001
        return SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE)
    try:
        if conversar is None:
            codigo = await enviar(
                settings, peticion, id_=preparacion.id,
            )
        else:
            codigo = await enviar(
                settings, peticion, id_=preparacion.id, conversar=conversar,
            )
    except (IntercambioInciertoError, TimeoutError):
        return SolicitudV4(ResultadoSolicitudV4.INCIERTA, id=preparacion.id)
    except Exception:  # noqa: BLE001 — fallo previo al envío
        return SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE, id=preparacion.id)
    resultado = _MAPA_TRANSPORTE.get(
        codigo, SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE),
    )
    return SolicitudV4(resultado.resultado, id=preparacion.id)


_MAPA_TRANSPORTE = {
    CodigoTransporteV4.ACEPTADA: SolicitudV4(ResultadoSolicitudV4.ACEPTADA),
    CodigoTransporteV4.RECHAZADA: SolicitudV4(ResultadoSolicitudV4.RECHAZADA),
    CodigoTransporteV4.OCUPADA: SolicitudV4(ResultadoSolicitudV4.OCUPADA),
    CodigoTransporteV4.NO_DISPONIBLE: SolicitudV4(ResultadoSolicitudV4.NO_DISPONIBLE),
    CodigoTransporteV4.RESPUESTA_INVALIDA:
        SolicitudV4(ResultadoSolicitudV4.RESPUESTA_INVALIDA),
    CodigoTransporteV4.INCIERTO: SolicitudV4(ResultadoSolicitudV4.INCIERTA),
}
