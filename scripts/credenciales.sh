#!/usr/bin/env bash
# =============================================================================
# credenciales.sh — inicializa, comprueba y protege las credenciales del .env.
#
#     sudo bash scripts/credenciales.sh              # = iniciar
#     sudo bash scripts/credenciales.sh iniciar      # crea el .env si falta, genera DB_PASSWORD si no hay una válida
#                                                    # y deja el .env protegido (root, 600). Idempotente.
#     sudo bash scripts/credenciales.sh comprobar    # solo lectura: dice si algo está mal (sin mostrar valores)
#
# Es la inicialización EXPLÍCITA para quien instala a mano con Docker Compose (el instalador bootstrap.sh hace lo
# mismo solo). Nunca imprime una contraseña; si ya existe una base de datos y no hay contraseña conocida, se detiene
# sin inventar otra (ver docs/adr/0012-credenciales-del-env.md, «Si se pierde la contraseña»).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${ZASCARR_ROOT}/.env}"

B='\033[1m'; G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; N='\033[0m'
info()    { echo -e "${B}→${N} $*"; }
success() { echo -e "${G}✓${N} $*"; }
warn()    { echo -e "${Y}⚠${N}  $*" >&2; }
die()     { echo -e "${R}✗${N} $*" >&2; exit 1; }

# shellcheck source=scripts/_credenciales.sh
source "${SCRIPT_DIR}/_credenciales.sh"

mensaje_base_sin_contrasena() {
    local datos="$1"
    die "Ya existe una base de datos de ZascArr en ${datos}/postgres, pero no encuentro su contraseña en
  ${ENV_FILE} (falta, está vacía o conserva el valor de ejemplo).
  No he cambiado ninguna contraseña ni he tocado la base: inventar otra la dejaría inaccesible.
  Qué hacer (detalle en docs/adr/0012-credenciales-del-env.md):
    · Si tienes copia del .env, restáurala en ${ENV_FILE} y vuelve a ejecutar esto.
    · Si no hay datos que conservar, aparta (no la borro yo) la carpeta ${datos}/postgres y vuelve a ejecutar:
      se creará una base nueva con una contraseña nueva."
}

accion="${1:-iniciar}"
case "${accion}" in
    iniciar)
        [[ "$(id -u)" -eq 0 ]] || die "Hace falta ser administrador. Ejecútalo así:
  sudo bash ${SCRIPT_DIR}/credenciales.sh"
        # Protección ANTES de escribir ningún secreto (ADR 0012): si otra cuenta puede sustituir el .env o el código que
        # root ejecuta, no se escribe nada y se explica cómo salir.
        proteger_configuracion "${ENV_FILE}" "${ZASCARR_ROOT}" "${REPO_DIR}" || \
            die "No puedo garantizar que otra cuenta no pueda sustituir el .env (ver arriba). No he escrito nada.
  Instala ZascArr en una carpeta propia de root que no cuelgue de la carpeta de nadie — por defecto /opt/zascarr
  (variable ZASCARR_ROOT) — y vuelve a ejecutarlo."
        if [[ ! -f "${ENV_FILE}" ]]; then
            [[ -f "${REPO_DIR}/.env.example" ]] || die "No encuentro ${REPO_DIR}/.env.example. ¿Está el repo completo?"
            (umask 077; cp -- "${REPO_DIR}/.env.example" "${ENV_FILE}") || die "No pude crear ${ENV_FILE}."
            info "Creado ${ENV_FILE} a partir de .env.example."
        fi
        limpiar_temporales_env "${ENV_FILE}"
        datos="${ZASCARR_DATA_DIR:-$(env_valor "${ENV_FILE}" ZASCARR_DATA_DIR)}"
        datos="${datos:-/var/lib/zascarr}"
        rc=0
        asegurar_credenciales "${ENV_FILE}" "${datos}" || rc=$?
        case "${rc}" in
            0)  success "DB_PASSWORD ya era válida: la conservo." ;;
            10) success "He generado una DB_PASSWORD propia y la he guardado en ${ENV_FILE} (no se muestra)." ;;
            20) mensaje_base_sin_contrasena "${datos}" ;;
            *)  die "No pude generar o guardar DB_PASSWORD. No he cambiado ${ENV_FILE}." ;;
        esac
        proteger_configuracion "${ENV_FILE}" "${ZASCARR_ROOT}" "${REPO_DIR}" || \
            die "No pude dejar protegido el .env o su carpeta. Revisa los permisos de ${ZASCARR_ROOT}."
        ln -sfn "${ENV_FILE}" "${REPO_DIR}/.env" 2>/dev/null || true
        success "Configuración protegida: ${ENV_FILE} es de root y solo root lo lee."
        ;;
    comprobar)
        rc=0
        salida="$(comprobar_proteccion "${ENV_FILE}" "${ZASCARR_ROOT}" "${REPO_DIR}")" || rc=$?
        if [[ "${rc}" -eq 0 ]]; then
            success "Credenciales y protección del .env en orden."
        else
            [[ -z "${salida}" ]] || echo "${salida}" >&2
            exit "${rc}"
        fi
        ;;
    *)
        die "Uso: sudo bash scripts/credenciales.sh [iniciar|comprobar]"
        ;;
esac
