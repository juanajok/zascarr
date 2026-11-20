"""Emisión aislada de autorizaciones cortas tras reautenticar en la app.

`crear_autorizacion` es el emisor puro: construye un testigo HMAC de un solo uso
sin E/S ni red. `preparar_autorizacion` es la composición obligatoria de la app
(puerta → validación → `auth_mode` → reautenticación → emisión): solo emite tras
`Reauth.OK`, llama exactamente una vez al servicio compartido de reautenticación
de OPS3 y usa la clave dedicada **recibida como argumento**. No lee ficheros, no
usa la clave del auxiliar, no abre conexiones, no persiste y no registra la
contraseña ni el testigo.

La provisión de la clave y el envío al host siguen pendientes y fuera de este
módulo: la composición recibe la clave como argumento y **no** implementa la
lectura del fichero (Q-AUT-1), la sesión/origen, el transporte ni el envío único
(Q-AUT-2), de modo que `aceptada`/`resultado_incierto` pertenecen a esa capa
futura y quedan NOT RUN. La actualización está deshabilitada: nada de aquí se
importa desde web, API, `main.py`, el auxiliar ni el instalador, y `habilitada`
vale `False` por defecto (fallo cerrado). El host debe verificar además el
consumo único y sus propias guardas de instalación, cerrojo, estado y unidad.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from zascarr.config import Settings
from zascarr.services.reautenticacion import (
    Reauth,
    ResultadoReauth,
    comprobar_contrasena_actual,
)

VERSION = 1
ACCION = "actualizar"
TTL_POR_DEFECTO = 60
TTL_MAX = 300
DOMINIO = b"zascarr-ops4-autorizacion-v1\n"
MAX_TOKEN = 2048
#: Tope de la contraseña en UTF-8; se valida aquí para no reflejarla en errores.
MAX_CONTRASENA_BYTES = 512
_ID = re.compile(r"[0-9a-f]{32}\Z")


class ResultadoAutorizacion(StrEnum):
    """Códigos cerrados de la capa de composición de la app; sin texto libre."""

    NO_HABILITADA = "no_habilitada"
    CONFIRMACION_REQUERIDA = "confirmacion_requerida"
    CONTRASENA_INVALIDA = "contrasena_invalida"
    AUTENTICACION_NO_ACTIVADA = "autenticacion_no_activada"
    CONTRASENA_INCORRECTA = "contrasena_incorrecta"
    OCUPADA = "ocupada"
    BLOQUEADA = "bloqueada"
    NO_DISPONIBLE = "no_disponible"
    PREPARADA = "preparada"


@dataclass(frozen=True)
class PreparacionAutorizacion:
    """Resultado de la composición; el testigo nunca se muestra en `repr`."""

    resultado: ResultadoAutorizacion
    #: ID CSPRNG generado tras `Reauth.OK`; debe viajar también en la petición.
    id: str | None = None
    #: Testigo opaco para el host: no se registra, no se copia y no se reenvía.
    autorizacion: bytes | None = field(default=None, repr=False)
    #: Solo con `BLOQUEADA`: hora (epoch) en que termina el bloqueo, para el aviso.
    hasta_epoch: float | None = None


Comprobar = Callable[[str, Settings], Awaitable[ResultadoReauth]]
GenerarId = Callable[[], str]
Emitir = Callable[..., bytes]


def _generar_id() -> str:
    """ID de un intento: CSPRNG, 32 hex; no se toma del formulario ni de la URL."""
    return secrets.token_hex(16)


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


async def preparar_autorizacion(
    settings: Settings,
    *,
    clave: object,
    contrasena: object,
    entiendo: object,
    habilitada: bool = False,
    ahora: int | None = None,
    comprobar: Comprobar = comprobar_contrasena_actual,
    generar_id: GenerarId = _generar_id,
    emitir: Emitir = crear_autorizacion,
) -> PreparacionAutorizacion:
    """Composición obligatoria app-side; solo emite tras `Reauth.OK`.

    Orden normativo, sin atajos: puerta de función → confirmación y forma de la
    contraseña → `auth_mode` → reautenticación → clave/ID/emisión. Cualquier
    resultado distinto de `Reauth.OK` (incluidas excepciones y valores no
    esperados) devuelve un código de denegación sin leer ni usar la clave, sin
    generar ID y sin emitir.

    La clave dedicada llega como argumento: la lectura del fichero, su provisión
    y el envío del testigo no se implementan aquí (decisiones abiertas Q-AUT-1 y
    Q-AUT-2). `habilitada=False` por defecto mantiene la función deshabilitada.
    """
    if habilitada is not True:
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_HABILITADA)
    if entiendo is not True:
        return PreparacionAutorizacion(ResultadoAutorizacion.CONFIRMACION_REQUERIDA)
    if not isinstance(contrasena, str):
        return PreparacionAutorizacion(ResultadoAutorizacion.CONTRASENA_INVALIDA)
    try:
        if not 1 <= len(contrasena.encode("utf-8")) <= MAX_CONTRASENA_BYTES:
            return PreparacionAutorizacion(ResultadoAutorizacion.CONTRASENA_INVALIDA)
    except UnicodeEncodeError:
        return PreparacionAutorizacion(ResultadoAutorizacion.CONTRASENA_INVALIDA)
    if settings.auth_mode == "none":
        return PreparacionAutorizacion(
            ResultadoAutorizacion.AUTENTICACION_NO_ACTIVADA
        )
    if settings.auth_mode not in ("password", "user_password"):
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)

    try:
        reauth = await comprobar(contrasena, settings)
    except Exception:  # noqa: BLE001 — un fallo de reautenticación no autoriza
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)
    if not isinstance(reauth, ResultadoReauth):
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)
    if reauth.resultado is Reauth.INCORRECTA:
        return PreparacionAutorizacion(ResultadoAutorizacion.CONTRASENA_INCORRECTA)
    if reauth.resultado is Reauth.OCUPADA:
        return PreparacionAutorizacion(ResultadoAutorizacion.OCUPADA)
    if reauth.resultado is Reauth.BLOQUEADA:
        return PreparacionAutorizacion(
            ResultadoAutorizacion.BLOQUEADA, hasta_epoch=reauth.hasta_epoch,
        )
    if reauth.resultado is not Reauth.OK:
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)

    # Solo a partir de aquí se usa la clave, se genera ID y se emite.
    if not isinstance(clave, bytes) or len(clave) != 32:
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)
    try:
        identificador = generar_id()
    except Exception:  # noqa: BLE001 — sin ID fiable no hay autorización
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)
    if not isinstance(identificador, str) or not _ID.fullmatch(identificador):
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)
    instante = int(time.time()) if ahora is None else ahora
    try:
        token = emitir(
            clave=clave, id_=identificador, ahora=instante, ttl=TTL_POR_DEFECTO,
        )
    except Exception:  # noqa: BLE001 — emisión dudosa ⇒ fallo cerrado
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)
    if not isinstance(token, bytes) or not 1 <= len(token) <= MAX_TOKEN:
        return PreparacionAutorizacion(ResultadoAutorizacion.NO_DISPONIBLE)
    return PreparacionAutorizacion(
        ResultadoAutorizacion.PREPARADA, id=identificador, autorizacion=token,
    )
