#!/usr/bin/env bash
# instalar_ops.sh — instala el auxiliar de «Hacer una copia ahora» (BL-OPS1, FR-26/27).
#
# Idempotente. Con --dry-run enseña lo que haría sin escribir nada; con --yes no pregunta.
#   --refrescar   (lo usa update.sh) si el auxiliar YA está instalado, copia de nuevo el auxiliar y las
#                 unidades solo si cambiaron y reinicia el socket; si no está instalado, no instala nada.
#   --quitar      retira unidades y auxiliar; conserva la clave. Con --borrar-clave también la borra.
# Solo toca OPS_DIR, /usr/local/lib/zascarr, las unidades systemd y tmpfiles.d; no toca la base de datos
# ni la biblioteca. La clave (ops.key) se crea solo si no existe y NUNCA se imprime.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${ZASCARR_ROOT}/.env}"

# Destinos: fijos en producción; las pruebas los desvían con ZASCARR_PRUEBAS=1.
DEST_AUXILIAR="/usr/local/lib/zascarr/zascarr-ops"
DEST_UNIDADES="/etc/systemd/system"
DEST_TMPFILES="/etc/tmpfiles.d/zascarr-ops.conf"
if [[ "${ZASCARR_PRUEBAS:-}" == "1" ]]; then
    DEST_AUXILIAR="${OPS_DEST_AUXILIAR:-${DEST_AUXILIAR}}"
    DEST_UNIDADES="${OPS_DEST_UNIDADES:-${DEST_UNIDADES}}"
    DEST_TMPFILES="${OPS_DEST_TMPFILES:-${DEST_TMPFILES}}"
fi

DRY_RUN=0
YES=0
MODO="instalar"
BORRAR_CLAVE=0
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y) YES=1 ;;
        --refrescar) MODO="refrescar" ;;
        --quitar) MODO="quitar" ;;
        --borrar-clave) BORRAR_CLAVE=1 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "Opción desconocida: ${arg}" >&2; exit 2 ;;
    esac
done
if (( BORRAR_CLAVE )) && [[ "${MODO}" != "quitar" ]]; then
    echo "--borrar-clave solo se usa con --quitar." >&2; exit 2
fi

say() { printf '%s\n' "$*"; }
run() {
    if (( DRY_RUN )); then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

if (( ! DRY_RUN )) && [[ "${ZASCARR_PRUEBAS:-}" != "1" ]]; then
    [[ "$(id -u)" -eq 0 ]] || { echo "Ejecútalo con sudo." >&2; exit 1; }
fi

# ── Dónde vive el estado y qué grupo lo lee ──────────────────────────────────────────────────────
leer_env() { [[ -f "${ENV_FILE}" ]] && sed -n "s/^$1=//p" "${ENV_FILE}" | tail -1 | tr -d "\"'" || true; }

DATA_DIR="${ZASCARR_DATA_DIR:-$(leer_env ZASCARR_DATA_DIR)}"
DATA_DIR="${DATA_DIR:-/var/lib/zascarr}"
OPS_DIR="${DATA_DIR}/ops"
BACKUP_STATUS_DIR="${BACKUP_STATUS_DIR:-${DATA_DIR}/backup-status}"

# El grupo es el del usuario de servicio (PGID del .env): nunca root por defecto, y si no existe se aborta
# antes de crear nada.
resolver_grupo() {
    local gid grupo
    if [[ -n "${OPS_GROUP:-}" ]]; then
        getent group "${OPS_GROUP}" >/dev/null 2>&1 && { printf '%s' "${OPS_GROUP}"; return 0; }
        return 1
    fi
    gid="$(leer_env PGID)"
    gid="${gid:-1000}"
    grupo="$(getent group "${gid}" | cut -d: -f1)"
    [[ -n "${grupo}" ]] || return 1
    printf '%s' "${grupo}"
}

sustituir() {
    # Sustitución con expansión de bash (no `sed`): ningún carácter de la ruta hace de delimitador ni de `&`.
    shopt -u patsub_replacement 2>/dev/null || true
    local texto
    texto="$(cat "$1"; printf x)"
    texto="${texto%x}"
    texto="${texto//@ZASCARR_DATA_DIR@/${DATA_DIR}}"
    texto="${texto//@GRUPO@/${GRUPO}}"
    texto="${texto//@BACKUP_STATUS_DIR@/${BACKUP_STATUS_DIR}}"
    printf '%s' "${texto}"
}

# Copia `origen` (ya sustituido si es una unidad) a `destino` solo si cambia. Devuelve 0 si cambió algo.
instalar_si_cambia() {
    local origen="$1" destino="$2" modo="$3" tmp
    tmp="$(mktemp)"
    if [[ "${origen}" == *.service || "${origen}" == *.socket ]]; then
        sustituir "${origen}" > "${tmp}"
    else
        cat "${origen}" > "${tmp}"
    fi
    if [[ -f "${destino}" ]] && cmp -s "${tmp}" "${destino}"; then
        rm -f "${tmp}"
        return 1
    fi
    run install -D -m "${modo}" "${tmp}" "${destino}"
    rm -f "${tmp}"
    return 0
}

instalado() { [[ -f "${DEST_AUXILIAR}" && -f "${DEST_UNIDADES}/zascarr-ops.socket" ]]; }

if [[ "${MODO}" == "quitar" ]]; then
    say "Quitando «Hacer una copia ahora»..."
    run systemctl disable --now zascarr-ops.socket 2>/dev/null || true
    run rm -f "${DEST_UNIDADES}/zascarr-ops.socket" "${DEST_UNIDADES}/zascarr-ops@.service" \
        "${DEST_TMPFILES}" "${DEST_AUXILIAR}"
    run systemctl daemon-reload
    if (( BORRAR_CLAVE )); then
        run rm -f "${OPS_DIR}/ops.key"
        say "Clave borrada."
    else
        say "La clave se conserva (${OPS_DIR}/ops.key); bórrala con --quitar --borrar-clave."
    fi
    exit 0
fi

if [[ "${MODO}" == "refrescar" ]] && ! instalado; then
    say "Puedes activar «Hacer una copia ahora»: sudo bash scripts/instalar_ops.sh"
    exit 0
fi

# ── Requisitos: se comprueban todos antes de escribir nada ───────────────────────────────────────
command -v systemctl >/dev/null 2>&1 || { echo "No encuentro systemctl." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "No encuentro python3 (hace falta 3.9 o superior)." >&2; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' \
    || { echo "Hace falta python3 3.9 o superior." >&2; exit 1; }
for f in deploy/ops/zascarr_ops.py deploy/systemd/zascarr-ops.socket deploy/systemd/zascarr-ops@.service \
         deploy/systemd/zascarr-ops.tmpfiles.conf; do
    [[ -f "${REPO_DIR}/${f}" ]] || { echo "Falta ${REPO_DIR}/${f}" >&2; exit 1; }
done
GRUPO="$(resolver_grupo)" || {
    echo "No encuentro el grupo del usuario de servicio (PGID del .env, o OPS_GROUP). No se instala nada." >&2
    exit 1
}

say "Repo: ${REPO_DIR}"
say "Carpeta del canal: ${OPS_DIR} (grupo ${GRUPO})"
say "Estado de la copia: ${BACKUP_STATUS_DIR}"

if [[ "${MODO}" == "instalar" ]] && (( ! YES && ! DRY_RUN )); then
    read -r -p "¿Instalar «Hacer una copia ahora»? [s/N] " respuesta
    [[ "${respuesta}" == "s" || "${respuesta}" == "S" ]] || { echo "Cancelado."; exit 1; }
fi

CAMBIO=0
run install -d -m 0750 -o root -g "${GRUPO}" "${OPS_DIR}"

# La clave: solo si no existe. 32 bytes aleatorios en hexadecimal; escritura atómica; nunca se imprime.
if [[ ! -f "${OPS_DIR}/ops.key" ]]; then
    if (( DRY_RUN )); then
        say "[dry-run] crear ${OPS_DIR}/ops.key (0440 root:${GRUPO})"
    else
        tmpkey="$(umask 077; mktemp "${OPS_DIR}/.ops.key.XXXXXX")"
        python3 -c 'import secrets; print(secrets.token_hex(32))' > "${tmpkey}"
        chown "root:${GRUPO}" "${tmpkey}"
        chmod 0440 "${tmpkey}"
        mv -n "${tmpkey}" "${OPS_DIR}/ops.key"
        rm -f "${tmpkey}"
        say "Clave creada."
    fi
else
    say "La clave ya existe: se conserva."
fi

instalar_si_cambia "${REPO_DIR}/deploy/ops/zascarr_ops.py" "${DEST_AUXILIAR}" 0755 && CAMBIO=1
instalar_si_cambia "${REPO_DIR}/deploy/systemd/zascarr-ops@.service" "${DEST_UNIDADES}/zascarr-ops@.service" 0644 && CAMBIO=1
instalar_si_cambia "${REPO_DIR}/deploy/systemd/zascarr-ops.socket" "${DEST_UNIDADES}/zascarr-ops.socket" 0644 && CAMBIO=1
instalar_si_cambia "${REPO_DIR}/deploy/systemd/zascarr-ops.tmpfiles.conf" "${DEST_TMPFILES}" 0644 && CAMBIO=1

if (( CAMBIO )) || [[ "${MODO}" == "instalar" ]]; then
    if (( CAMBIO )); then
        run systemctl daemon-reload
    fi
    # `/run` es tmpfs: el directorio de ids vistos hay que crearlo ya, no esperar al arranque (M-4a).
    run systemd-tmpfiles --create "${DEST_TMPFILES}"
    run systemctl enable --now zascarr-ops.socket
    if (( CAMBIO )) && [[ "${MODO}" == "refrescar" ]]; then
        run systemctl restart zascarr-ops.socket
    fi
fi

if (( CAMBIO )); then
    say "Listo: «Hacer una copia ahora» queda instalado y actualizado."
else
    say "Sin cambios: ya estaba al día."
fi
