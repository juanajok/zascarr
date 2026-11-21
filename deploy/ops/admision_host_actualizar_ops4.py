"""Composición aislada de la admisión de host; no ejecuta ni arranca nada.

Une el contrato v3, la reclamación de identificador y la verificación PBKDF2
contra un lector de credenciales inyectado. No abre el socket del auxiliar, no
adquiere el cerrojo real, no persiste la reclamación y no invoca systemd. Una
respuesta aceptada solo significa que las comprobaciones locales pasaron; no
autoriza efectos ni demuestra que la identidad del host sea correcta.
"""
from __future__ import annotations

from collections.abc import Callable

from deploy.ops.admision_actualizar_ops4 import CodigoAdmision, admitir
from deploy.ops.prueba_viva_ops4 import verificar_prueba_viva


def admitir_host(
    linea: object,
    *,
    clave: object,
    ahora: object,
    lector: object,
    reclamar_id: Callable[[str], bool],
    limite: object | None = None,
) -> CodigoAdmision:
    """Ordena firma/frescura/reclamación y verifica la contraseña viva.

    El lector debe exponer `leer() -> (modo, hash) | None`; cualquier fallo se
    convierte en denegación. La reclamación y la persistencia real siguen fuera
    de este módulo.
    """
    try:
        leer = getattr(lector, "leer", None)
    except Exception:  # noqa: BLE001
        return CodigoAdmision.NO_DISPONIBLE
    if not callable(leer):
        return CodigoAdmision.NO_DISPONIBLE
    if limite is not None:
        permite = getattr(limite, "permite", None)
        if not callable(permite):
            return CodigoAdmision.NO_DISPONIBLE
        try:
            if permite(ahora) is not True:
                return CodigoAdmision.BLOQUEADA
        except Exception:  # noqa: BLE001
            return CodigoAdmision.NO_DISPONIBLE

    def comprobar(prueba: str) -> bool:
        return verificar_prueba_viva(prueba, leer)

    resultado = admitir(
        linea, clave=clave, ahora=ahora,
        verificar_prueba=comprobar, reclamar_id=reclamar_id,
    )
    if limite is not None and resultado in (
        CodigoAdmision.ACEPTADA, CodigoAdmision.PRUEBA_INVALIDA
    ):
        metodo = getattr(limite, "exito" if resultado is CodigoAdmision.ACEPTADA else "fallo", None)
        if not callable(metodo):
            return CodigoAdmision.NO_DISPONIBLE
        try:
            metodo(ahora)
        except Exception:  # noqa: BLE001
            return CodigoAdmision.NO_DISPONIBLE
    return resultado
