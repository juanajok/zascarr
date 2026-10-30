#!/usr/bin/env bash
# =============================================================================
# backup.sh — copia diaria de PostgreSQL, verificada y fuera del disco de datos.
#
# E2/#334: un dump en el mismo disco que la base no es una copia de seguridad.
# Este script:
#   1. comprueba que el disco de respaldo está montado y es otro dispositivo;
#   2. vuelca, verifica (gzip, cabecera, tablas) y firma con SHA-256;
#   3. escribe un manifiesto con commit, Alembic, fecha, origen e ID;
#   4. copia al disco de respaldo y verifica la copia por hash;
#   5. sincroniza al respaldo los dumps con una ref de rescate viva;
#   6. aplica retención sin borrar un dump que tenga una ref viva;
#   7. escribe un estado JSON que /api/health y /estado enseñan.
#
# Instalación: scripts/instalar_backup.sh (unidades en deploy/systemd/).
# No toca la biblioteca de tebeos: solo lee PostgreSQL y escribe copias.
# =============================================================================
set -euo pipefail
umask 022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${ZASCARR_REPO:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"

# shellcheck source=scripts/_comun.sh
source "${REPO_DIR}/scripts/_comun.sh"
# shellcheck source=scripts/_credenciales.sh
source "${SCRIPT_DIR}/_credenciales.sh"

BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR:-/media/Backup/zascarr/postgres}"
BACKUP_OFFSITE_MOUNT="${BACKUP_OFFSITE_MOUNT:-/media/Backup}"
BACKUP_STATUS_DIR="${BACKUP_STATUS_DIR:-/var/lib/zascarr/backup-status}"
BACKUP_LOCK_FILE="${BACKUP_LOCK_FILE:-/run/zascarr-backup.lock}"
STATUS_FILE="${BACKUP_STATUS_DIR}/status.json"

STATUS_WRITTEN=0
LAST_SUCCESS_EPOCH=""
LAST_LOCAL_SUCCESS_EPOCH=""
OFFSITE_OK=1
OFFSITE_ERROR=""
ANCHOR_ERROR=""

command -v flock >/dev/null 2>&1 || die "No encuentro flock (util-linux)."
command -v mountpoint >/dev/null 2>&1 || die "No encuentro mountpoint (util-linux)."

comprobar_requisitos
# Sin comprobar_git_utilizable: el volcado no necesita git. En una copia sin
# `.git` el manifiesto deja el commit vacío y la retención no ve refs; en la Pi
# el repo sí lo tiene y se rellena. update.sh/rollback.sh sí lo exigen.
comprobar_env_legible "${ENV_FILE}"

mkdir -p "${BACKUP_DIR}" || die "No puedo crear ${BACKUP_DIR}."
install -d -m 755 "${BACKUP_STATUS_DIR}" || die "No puedo crear ${BACKUP_STATUS_DIR}."

# Un solo backup a la vez: el timer y una ejecución manual no deben solaparse.
exec 9>"${BACKUP_LOCK_FILE}" || die "No puedo abrir el cerrojo ${BACKUP_LOCK_FILE}."
flock -n 9 || die "Ya hay una copia en curso (${BACKUP_LOCK_FILE})."

# Conserva la última copia completa/local si este intento falla.
if [[ -f "${STATUS_FILE}" ]] && jq -e . "${STATUS_FILE}" >/dev/null 2>&1; then
    LAST_SUCCESS_EPOCH="$(jq -r '.last_success_at_epoch // empty' "${STATUS_FILE}")"
    LAST_LOCAL_SUCCESS_EPOCH="$(jq -r '.last_local_success_at_epoch // empty' "${STATUS_FILE}")"
fi

escribir_estado() {
    local estado="$1" error="${2:-}" dump="${3:-}" sha="${4:-}" bytes="${5:-0}" offsite="${6:-false}"
    local now commit alembic protegidos tmp last_success_iso
    now="$(date +%s)"
    if [[ "${estado}" == "ok" || "${estado}" == "degraded" ]]; then
        LAST_SUCCESS_EPOCH="${now}"
        LAST_LOCAL_SUCCESS_EPOCH="${now}"
    fi
    commit="$(git -C "${REPO_DIR}" rev-parse HEAD 2>/dev/null || true)"
    alembic="$("${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -At \
        -c "select version_num from alembic_version" 2>/dev/null | tr -d '[:space:]' || true)"
    protegidos="$(dumps_protegidos_por_ref | jq -R -s 'split("\n") | map(select(length > 0))')"
    last_success_iso=""
    if [[ -n "${LAST_SUCCESS_EPOCH}" && "${LAST_SUCCESS_EPOCH}" != "0" ]]; then
        last_success_iso="$(date -d "@${LAST_SUCCESS_EPOCH}" -Iseconds 2>/dev/null || true)"
    fi
    tmp="${STATUS_FILE}.tmp.$$"
    if ! jq -n \
        --arg status "${estado}" \
        --arg error "${error}" \
        --argjson last_attempt_at_epoch "${now}" \
        --argjson last_success_at_epoch "${LAST_SUCCESS_EPOCH:-0}" \
        --argjson last_local_success_at_epoch "${LAST_LOCAL_SUCCESS_EPOCH:-0}" \
        --arg last_attempt_at "$(date -Iseconds)" \
        --arg last_success_at "${last_success_iso}" \
        --arg dump "$(basename "${dump}")" \
        --arg sha256 "${sha}" \
        --argjson bytes "${bytes:-0}" \
        --argjson offsite "${offsite}" \
        --arg commit "${commit}" \
        --arg alembic "${alembic}" \
        --argjson protegidos "${protegidos}" \
        '{schema: 1, status: $status, error: (if $error == "" then null else $error end),
          last_attempt_at_epoch: $last_attempt_at_epoch,
          last_success_at_epoch: $last_success_at_epoch,
          last_local_success_at_epoch: $last_local_success_at_epoch,
          last_attempt_at: $last_attempt_at, last_success_at: $last_success_at,
          dump: $dump, sha256: $sha256, bytes: $bytes, offsite: $offsite,
          commit: $commit, alembic: $alembic, retencion_protegida: $protegidos}' \
        > "${tmp}"; then
        rm -f "${tmp}"
        return 1
    fi
    chmod 644 "${tmp}" || { rm -f "${tmp}"; return 1; }
    mv "${tmp}" "${STATUS_FILE}" || { rm -f "${tmp}"; return 1; }
    STATUS_WRITTEN=1
    return 0
}

on_exit() {
    local rc=$?
    if (( rc != 0 )) && (( STATUS_WRITTEN == 0 )); then
        escribir_estado "failed" "unexpected" "" "" 0 false || true
    fi
    exit "${rc}"
}
trap on_exit EXIT

TS="$(date +%Y%m%d_%H%M%S)"
DEST="${BACKUP_DIR}/backup_${TS}.sql.gz"

# ── Espacio libre ANTES de volcar (#123b) ───────────────────────────────────
TAMANO_KB="$(tamano_bd_kb)"
exigir_espacio_kb "$(espacio_libre_kb "${BACKUP_DIR}")" "${TAMANO_KB}" \
        "la copia de seguridad local" && ESPACIO_RC=0 || ESPACIO_RC=$?
if (( ESPACIO_RC == 2 )); then
    escribir_estado "failed" "pg_dump_failed" "" "" 0 false || true
    die "No pude medir el espacio necesario (¿PostgreSQL parado o el disco sin montar?). No se ha escrito ningún volcado."
elif (( ESPACIO_RC != 0 )); then
    escribir_estado "failed" "disk_full" "" "" 0 false || true
    die "No hay espacio para la copia de seguridad. No se ha escrito ningún volcado."
fi

# ── Montaje y dispositivo ────────────────────────────────────────────────────
if ! mountpoint -q "${BACKUP_OFFSITE_MOUNT}"; then
    OFFSITE_OK=0
    OFFSITE_ERROR="offsite_mount_missing"
elif [[ "${BACKUP_SKIP_DEVICE_CHECK:-0}" != "1" ]]; then
    dev_mount="$(stat -c %d "${BACKUP_OFFSITE_MOUNT}" 2>/dev/null || true)"
    dev_data="$(stat -c %d "${BACKUP_DIR}" 2>/dev/null || true)"
    if [[ -z "${dev_mount}" || "${dev_mount}" == "${dev_data}" ]]; then
        OFFSITE_OK=0
        OFFSITE_ERROR="offsite_same_device"
    fi
fi

# ── Volcado local, verificado ────────────────────────────────────────────────
info "Volcando ${DB_NAME}..."
if ! volcar_postgres "${DEST}"; then
    escribir_estado "failed" "pg_dump_failed" "" "" 0 false || true
    die "pg_dump falló; no se ha guardado nada."
fi
if ! verificar_dump "${DEST}"; then
    rm -f "${DEST}"
    escribir_estado "failed" "${VERIFY_ERROR_CODE:-verify_failed}" "" "" 0 false || true
    die "El volcado no pasó la verificación; se descarta."
fi
SHA="$(sha256sum "${DEST}" | awk '{print $1}')"
BYTES="$(stat -c %s "${DEST}")"

# ── Copia fuera del disco ────────────────────────────────────────────────────
OFFSITE_JSON="$(jq -n --arg error "${OFFSITE_ERROR}" \
    '{copia: false, error: (if $error == "" then null else $error end), verificada: false}')"

if (( OFFSITE_OK == 1 )); then
    if ! install -d -m 700 "${BACKUP_OFFSITE_DIR}" 2>/dev/null; then
        OFFSITE_OK=0
        OFFSITE_ERROR="offsite_copy_failed"
    fi
fi

if (( OFFSITE_OK == 1 )); then
    if ! exigir_espacio_kb "$(espacio_libre_kb "${BACKUP_OFFSITE_DIR}")" \
            "$((BYTES / 1024))" "la copia fuera del disco"; then
        OFFSITE_OK=0
        OFFSITE_ERROR="disk_full"
        OFFSITE_JSON="$(jq -n --arg error "${OFFSITE_ERROR}" \
            '{copia: false, error: $error, verificada: false}')"
    fi
fi

if (( OFFSITE_OK == 1 )); then
    OFF_DEST="${BACKUP_OFFSITE_DIR}/$(basename "${DEST}")"
    OFF_TMP="${OFF_DEST}.tmp.$$"
    if cp "${DEST}" "${OFF_TMP}" && chmod 600 "${OFF_TMP}" && sync && mv "${OFF_TMP}" "${OFF_DEST}"; then
        OFF_SHA="$(sha256sum "${OFF_DEST}" | awk '{print $1}')"
        if [[ "${OFF_SHA}" != "${SHA}" ]]; then
            rm -f "${OFF_DEST}"
            OFFSITE_OK=0
            OFFSITE_ERROR="offsite_verify_failed"
        else
            OFFSITE_JSON="$(jq -n --arg sha "${SHA}" --argjson bytes "${BYTES}" \
                '{copia: true, sha256: $sha, bytes: $bytes, verificada: true}')"
        fi
    else
        rm -f "${OFF_TMP}"
        OFFSITE_OK=0
        OFFSITE_ERROR="offsite_copy_failed"
    fi
fi

# Manifiesto de la copia offsite (si se copió).
if (( OFFSITE_OK == 1 )); then
    OFF_EXTRA="$(jq -n --arg sha "${SHA}" \
        '{origen_copia: "BACKUP_DIR", sha256_origen: $sha}')"
    if ! escribir_manifiesto "${OFF_DEST}" "backup.sh (copia offsite)" \
            "offsite-${TS}" "${OFF_EXTRA}" >/dev/null; then
        OFFSITE_OK=0
        OFFSITE_ERROR="manifest_failed"
        OFFSITE_JSON="$(jq -n --arg error "${OFFSITE_ERROR}" \
            '{copia: false, error: $error, verificada: false}')"
    fi
fi

# Manifiesto local con el resultado del offsite.
LOCAL_EXTRA="$(jq -n --argjson offsite "${OFFSITE_JSON}" \
    '{verificacion: {gzip: "ok", cabecera: "ok",
      tablas: ["alembic_version", "series", "files", "wishlist"], sha256: "ok"},
      offsite: $offsite}')"
if ! MANIFEST="$(escribir_manifiesto "${DEST}" "backup.sh (timer systemd)" \
        "backup-${TS}" "${LOCAL_EXTRA}")"; then
    escribir_estado "failed" "manifest_failed" "${DEST}" "${SHA}" "${BYTES}" \
        "$([[ ${OFFSITE_OK} == 1 ]] && echo true || echo false)" || true
    die "No se pudo escribir el manifiesto local."
fi

# ── Sincronización de las anclas vivas ───────────────────────────────────────
if (( OFFSITE_OK == 1 )); then
    # Los nombres se leen ANTES del bucle: `escribir_manifiesto` ejecuta
    # `docker compose exec`, que consume stdin; con un `while read` se perdían
    # las anclas restantes.
    mapfile -t nombres_ancla < <(dumps_protegidos_por_ref)
    for nombre in "${nombres_ancla[@]}"; do
        [[ -n "${nombre}" ]] || continue
        local_dump="${BACKUP_DIR}/${nombre}"
        [[ -f "${local_dump}" ]] || continue
        off_dump="${BACKUP_OFFSITE_DIR}/${nombre}"
        origen_sha="$(sha256sum "${local_dump}" | awk '{print $1}')"
        destino_sha=""
        [[ -f "${off_dump}" ]] && destino_sha="$(sha256sum "${off_dump}" | awk '{print $1}')"
        if [[ "${origen_sha}" != "${destino_sha}" ]]; then
            if ! cp "${local_dump}" "${off_dump}.tmp.$$" \
                || ! chmod 600 "${off_dump}.tmp.$$" \
                || ! sync \
                || ! mv "${off_dump}.tmp.$$" "${off_dump}"; then
                rm -f "${off_dump}.tmp.$$"
                ANCHOR_ERROR="anchor_sync_failed"
                break
            fi
            if [[ "$(sha256sum "${off_dump}" | awk '{print $1}')" != "${origen_sha}" ]]; then
                ANCHOR_ERROR="anchor_sync_failed"
                break
            fi
        fi
        local_manifest="${BACKUP_DIR}/MANIFIESTO-${nombre%.sql.gz}.json"
        off_manifest="${BACKUP_OFFSITE_DIR}/MANIFIESTO-${nombre%.sql.gz}.json"
        if [[ -f "${local_manifest}" ]]; then
            if ! cp -p "${local_manifest}" "${off_manifest}.tmp.$$" \
                || ! chmod 600 "${off_manifest}.tmp.$$" \
                || ! mv "${off_manifest}.tmp.$$" "${off_manifest}"; then
                rm -f "${off_manifest}.tmp.$$"
                ANCHOR_ERROR="anchor_sync_failed"
                break
            fi
        elif [[ ! -f "${off_manifest}" ]]; then
            if ! escribir_manifiesto "${off_dump}" "backup.sh (sincronización de ancla)" \
                    "ancla-${nombre%.sql.gz}" '{}' >/dev/null </dev/null; then
                ANCHOR_ERROR="anchor_sync_failed"
                break
            fi
        fi
    done
fi

# ── Retención ────────────────────────────────────────────────────────────────
aplicar_retencion "${BACKUP_DIR}"
if (( OFFSITE_OK == 1 )); then
    aplicar_retencion "${BACKUP_OFFSITE_DIR}"
fi

# ── Estado final ─────────────────────────────────────────────────────────────
if (( OFFSITE_OK == 1 )) && [[ -z "${ANCHOR_ERROR}" ]]; then
    if ! escribir_estado "ok" "" "${DEST}" "${SHA}" "${BYTES}" true; then
        die "La copia se hizo, pero no se pudo escribir el estado."
    fi
    success "Copia verificada: ${DEST} (${BYTES} B, sha256 ${SHA:0:12}…)"
    success "Copia fuera del disco: ${BACKUP_OFFSITE_DIR}"
    success "Manifiesto: ${MANIFEST}"
    exit 0
fi

if (( OFFSITE_OK == 0 )); then
    escribir_estado "failed" "${OFFSITE_ERROR}" "${DEST}" "${SHA}" "${BYTES}" false || true
    die "Copia local correcta, pero la copia fuera del disco falló (${OFFSITE_ERROR})."
fi

escribir_estado "degraded" "${ANCHOR_ERROR}" "${DEST}" "${SHA}" "${BYTES}" true || true
warn "Copia local y offsite correctas; no se sincronizaron las anclas (${ANCHOR_ERROR})."
exit 2
