"""BL-OPS2 (#443): preparar y pedir una restauración desde la UI.

La lista es informativa; la autoridad es el auxiliar y el script. Aquí solo se
valida a mano, se reautentica con el servicio compartido y se envía una petición
firmada v2. La contraseña no se guarda, no se registra y no vuelve a la plantilla.
"""
from __future__ import annotations

import re

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import Settings
from zascarr.models import CodigoOps
from zascarr.services import ops_host
from zascarr.services.reautenticacion import Reauth, comprobar_contrasena_actual

logger = structlog.get_logger()
RE_COPIA = re.compile(r"backup-[0-9]{8}_[0-9]{6}")
MAX_PRUEBA_BYTES = 512
MENSAJE_CONFIRMA = "Marca que entiendes lo que se pierde antes de continuar."
MENSAJE_COPIA = "Esa copia ya no está disponible. Actualiza la lista."
MENSAJE_CONTRASENA_LARGA = "Esa contraseña es demasiado larga para este paso."
MENSAJE_SIN_CONTRASENA = "Escribe la contraseña actual de ZascArr."
MENSAJE_NO_ACTIVADA = "Activa la contraseña en Ajustes → Seguridad antes de restaurar una copia."
MENSAJE_OPERACION = "ZascArr está haciendo otra tarea de mantenimiento. Espera a que termine."
MENSAJE_ENTENDIDO = "No se ha cambiado nada."
MENSAJE_RESTAURANDO = "Hay una restauración en marcha. Vuelve a probar cuando termine."


async def revision_actual(db: AsyncSession) -> str | None:
    try:
        valor = (await db.execute(text("select version_num from alembic_version"))).scalar()
    except Exception:  # noqa: BLE001 — la UI no debe caer por no poder leer una revisión
        return None
    return str(valor) if valor else None


def ofrecer(copias: list[dict] | None, revision: str | None, auth_mode: str,
            permitir: bool = True) -> list[dict]:
    """Cada copia con `restaurable` y el motivo corto cuando no lo es.

    `permitir=False` mientras hay una copia o una restauración en marcha (FR-29/AC-21): no se ofrece el botón.
    """
    salida: list[dict] = []
    for copia in copias or []:
        motivo = ""
        if not permitir:
            motivo = MENSAJE_RESTAURANDO
        elif auth_mode not in ("password", "user_password"):
            motivo = "Activa la contraseña para restaurar."
        elif not copia.get("verificada"):
            motivo = "Esta copia no se verificó; no se puede restaurar desde aquí."
        elif not revision or copia.get("revision") != revision:
            motivo = "Esta copia es de otra versión de ZascArr."
        elif not RE_COPIA.fullmatch(str(copia.get("id", ""))):
            motivo = "Copia no válida."
        salida.append({**copia, "restaurable": not motivo, "motivo": motivo})
    return salida


async def solicitar(db: AsyncSession, settings: Settings, *, copia: str, contrasena: str,
                    entiendo: bool) -> tuple[CodigoOps, str]:
    """Valida en el orden de FR-03 y devuelve (código, mensaje)."""
    if not RE_COPIA.fullmatch(copia or ""):
        return CodigoOps.COPIA_DESCONOCIDA, MENSAJE_COPIA
    if not contrasena:
        return CodigoOps.PRUEBA_INVALIDA, MENSAJE_SIN_CONTRASENA
    if len(contrasena.encode("utf-8")) > MAX_PRUEBA_BYTES:
        return CodigoOps.PRUEBA_INVALIDA, MENSAJE_CONTRASENA_LARGA
    if not entiendo:
        return CodigoOps.NO_DISPONIBLE, MENSAJE_CONFIRMA
    if settings.auth_mode == "none":
        return CodigoOps.AUTENTICACION_NO_ACTIVADA, MENSAJE_NO_ACTIVADA
    revision = await revision_actual(db)
    copias = ops_host.leer_copias(settings)
    disponibles = ofrecer(copias, revision, settings.auth_mode)
    if not any(c["id"] == copia and c["restaurable"] for c in disponibles):
        return CodigoOps.COPIA_DESCONOCIDA, MENSAJE_COPIA
    vista = ops_host.resolver_estado(settings)
    if vista.en_marcha:
        return CodigoOps.OPERACION_EN_CURSO, MENSAJE_OPERACION
    if ops_host.resolver_restauracion(settings).en_marcha:
        return CodigoOps.OPERACION_EN_CURSO, MENSAJE_OPERACION
    reauth = await comprobar_contrasena_actual(contrasena, settings)
    if reauth.resultado is Reauth.INCORRECTA:
        return CodigoOps.PRUEBA_INVALIDA, "La contraseña no es correcta."
    if reauth.resultado is Reauth.OCUPADA:
        return (CodigoOps.NO_DISPONIBLE,
                "ZascArr está ocupado. Espera unos segundos e inténtalo otra vez.")
    if reauth.resultado is Reauth.BLOQUEADA:
        from zascarr.services.seguridad import mensaje_bloqueada
        return CodigoOps.BLOQUEO_TEMPORAL, mensaje_bloqueada(reauth.hasta_epoch)
    codigo = await ops_host.pedir_restaurar(settings, copia, contrasena)
    if codigo is CodigoOps.ACEPTADA:
        return codigo, "Restauración en marcha. ZascArr se reiniciará en uno o dos minutos."
    return codigo, ops_host.MENSAJES_RESTAURAR.get(codigo, ops_host.MENSAJES_PEDIR.get(
        codigo, "No se pudo iniciar la restauración. No se ha cambiado nada."))
