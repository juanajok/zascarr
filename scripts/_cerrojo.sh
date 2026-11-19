#!/usr/bin/env bash
# =============================================================================
# _cerrojo.sh — el cerrojo ÚNICO de las operaciones de ZascArr (BL-OPS1, FR-12).
#
# NO se ejecuta solo: se carga con `source` (lo carga `_comun.sh`; `restaurar_datos.sh`, que no usa
# `_comun.sh`, lo carga directamente). Lo toman `backup.sh`, `probar_restauracion.sh`, `update.sh`,
# `rollback.sh` y `restaurar_datos.sh`: una sola operación de mantenimiento a la vez, también frente a la
# copia que se pide desde la interfaz (el auxiliar del host solo comprueba este mismo fichero).
#
# Reglas (spec BL-OPS1, FR-12; dictamen de SecOps M-2, M-3, A-1):
#   - Ruta CONSTANTE en producción: /run/zascarr-ops.lock. No se lee de /etc/default/zascarr ni del entorno:
#     un `OPS_LOCK_FILE` perdido allí no tiene efecto. Solo con ZASCARR_PRUEBAS=1 + OPS_LOCK_FILE=<ruta> (las
#     pruebas), y entonces se avisa para que nadie lo deje olvidado.
#   - Descriptor 9 y herencia padre→hijo: si un script operativo invoca a otro que ya tiene el cerrojo
#     (update.sh → probar_restauracion.sh --dump), el hijo comprueba que /proc/self/fd/9 y la ruta son el MISMO
#     fichero (dispositivo:inodo) y hace `flock -n 9` sobre el descriptor heredado, que es idempotente sobre la
#     misma descripción de fichero. Sin descriptor 9, o apuntando a otro fichero, abre y toma el cerrojo como un
#     proceso independiente.
#   - Cerrojo ocupado por otro proceso: no toca nada y devuelve 75 con un mensaje en llano.
#   - Sin permiso para abrirlo (no es root): «Ejecuta con sudo…» y código 1, sin el error crudo de bash.
# =============================================================================

OPS_LOCK_FILE_PRODUCCION="/run/zascarr-ops.lock"

ruta_cerrojo_operaciones() {
    if [[ "${ZASCARR_PRUEBAS:-}" == "1" && -n "${OPS_LOCK_FILE:-}" ]]; then
        printf '%s' "${OPS_LOCK_FILE}"
    else
        printf '%s' "${OPS_LOCK_FILE_PRODUCCION}"
    fi
}

# Devuelve 0 con el cerrojo tomado en el descriptor 9; 75 si lo tiene otro proceso; sale con 1 si no puede
# abrirlo (no es root). Quien lo llama decide qué hacer con el 75 (backup.sh deja constancia; los demás salen).
tomar_cerrojo_operaciones() {
    local ruta heredado=0
    ruta="$(ruta_cerrojo_operaciones)"
    if [[ "${ZASCARR_PRUEBAS:-}" == "1" && -n "${OPS_LOCK_FILE:-}" ]]; then
        echo "ZASCARR_PRUEBAS activo: el cerrojo no es el de producción." >&2
    fi
    command -v flock >/dev/null 2>&1 || { echo "No encuentro flock (util-linux)." >&2; exit 1; }

    if [[ -e /proc/self/fd/9 && -e "${ruta}" ]] \
        && [[ "$(stat -L -c '%d:%i' /proc/self/fd/9 2>/dev/null)" == "$(stat -c '%d:%i' "${ruta}" 2>/dev/null)" ]]; then
        heredado=1
    fi
    if (( heredado == 0 )); then
        # Se prueba la apertura en una subshell con el error de bash silenciado: un `exec` con la redirección
        # fallida no siempre aborta, y el mensaje crudo ("Permiso denegado") no es para la persona.
        # F-1 (SecOps): única creación del fichero, ya 0600 (umask 077 solo en la subshell); si ya existía con
        # otro modo, el `chmod` posterior lo corrige.
        if ! ( umask 077; : >>"${ruta}" ) 2>/dev/null; then
            echo "Ejecuta con sudo: hace falta para tomar el cerrojo de ZascArr." >&2
            exit 1
        fi
        chmod 600 "${ruta}" 2>/dev/null || true
        exec 9>"${ruta}" || { echo "Ejecuta con sudo: hace falta para tomar el cerrojo de ZascArr." >&2; exit 1; }
    fi
    if ! flock -n 9; then
        echo "Hay otra operación de ZascArr en marcha; espera a que termine." >&2
        return 75
    fi
    return 0
}
