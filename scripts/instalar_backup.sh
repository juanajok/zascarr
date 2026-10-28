#!/usr/bin/env bash
# instalar_backup.sh — instala la copia diaria de ZascArr (#334).
#
# Idempotente. Con --dry-run enseña lo que haría sin escribir nada; con --yes
# no pregunta. Solo toca /etc/default/zascarr, /usr/local/bin/backup.sh y las
# unidades systemd; no toca la base de datos ni la biblioteca.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${ZASCARR_ROOT}/.env}"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/zascarr/postgres}"
BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR:-/media/Backup/zascarr/postgres}"
BACKUP_OFFSITE_MOUNT="${BACKUP_OFFSITE_MOUNT:-/media/Backup}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

DRY_RUN=0
YES=0
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y) YES=1 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "Opción desconocida: ${arg}" >&2; exit 2 ;;
    esac
done

say() { printf '%s\n' "$*"; }
run() {
    if (( DRY_RUN )); then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

# El estado debe quedar donde el compose lo monta. Si el .env fija
# ZASCARR_DATA_DIR, se respeta; si no, el valor por defecto del compose.
DATA_DIR="${ZASCARR_DATA_DIR:-}"
if [[ -z "${DATA_DIR}" && -f "${ENV_FILE}" ]]; then
    DATA_DIR="$(sed -n 's/^ZASCARR_DATA_DIR=//p' "${ENV_FILE}" | tail -1 | tr -d "\"'")"
fi
DATA_DIR="${DATA_DIR:-/var/lib/zascarr}"
BACKUP_STATUS_DIR="${BACKUP_STATUS_DIR:-${DATA_DIR}/backup-status}"

if (( ! DRY_RUN )); then
    [[ "$(id -u)" -eq 0 ]] || { echo "Ejecútalo con sudo." >&2; exit 1; }
fi
[[ -f "${REPO_DIR}/scripts/backup.sh" ]] || {
    echo "No encuentro ${REPO_DIR}/scripts/backup.sh" >&2; exit 1;
}
[[ -f "${REPO_DIR}/deploy/systemd/zascarr-backup.service" ]] || {
    echo "Faltan las unidades en ${REPO_DIR}/deploy/systemd/" >&2; exit 1;
}
for cmd in systemctl mountpoint jq install; do
    command -v "${cmd}" >/dev/null 2>&1 || {
        echo "No encuentro ${cmd}" >&2; exit 1;
    }
done

if ! mountpoint -q "${BACKUP_OFFSITE_MOUNT}"; then
    echo "ABORTAR: ${BACKUP_OFFSITE_MOUNT} no está montado. No se instala nada." >&2
    exit 1
fi

say "Repo: ${REPO_DIR}"
say "Copia local: ${BACKUP_DIR}"
say "Copia fuera del disco: ${BACKUP_OFFSITE_DIR} (montaje ${BACKUP_OFFSITE_MOUNT})"
say "Estado: ${BACKUP_STATUS_DIR}"
say "Retención: ${RETENTION_DAYS} días"

if (( ! YES && ! DRY_RUN )); then
    read -r -p "¿Instalar el timer y hacer la primera copia? [s/N] " respuesta
    [[ "${respuesta}" == "s" || "${respuesta}" == "S" ]] || {
        echo "Cancelado."; exit 1;
    }
fi

DEFAULTS="$(mktemp)"
cleanup() { rm -f "${DEFAULTS}"; }
trap cleanup EXIT
cat > "${DEFAULTS}" <<EOF
ZASCARR_REPO=${REPO_DIR}
BACKUP_DIR=${BACKUP_DIR}
BACKUP_OFFSITE_DIR=${BACKUP_OFFSITE_DIR}
BACKUP_OFFSITE_MOUNT=${BACKUP_OFFSITE_MOUNT}
BACKUP_STATUS_DIR=${BACKUP_STATUS_DIR}
RETENTION_DAYS=${RETENTION_DAYS}
EOF

run install -d -m 700 "${BACKUP_DIR}"
run install -d -m 700 "${BACKUP_OFFSITE_DIR}"
run install -d -m 755 "${BACKUP_STATUS_DIR}"
run install -m 600 "${DEFAULTS}" /etc/default/zascarr
run install -m 755 "${REPO_DIR}/deploy/systemd/backup-wrapper.sh" /usr/local/bin/backup.sh
run install -m 644 "${REPO_DIR}/deploy/systemd/zascarr-backup.service" /etc/systemd/system/zascarr-backup.service
run install -m 644 "${REPO_DIR}/deploy/systemd/zascarr-backup.timer" /etc/systemd/system/zascarr-backup.timer
run systemctl daemon-reload
run systemctl enable --now zascarr-backup.timer

if (( DRY_RUN )); then
    say "[dry-run] La primera copia y la verificación no se ejecutan."
    exit 0
fi

say "Primera copia (puede tardar unos segundos)..."
if ! systemctl start zascarr-backup.service; then
    echo "La primera copia falló. Revisa: journalctl -u zascarr-backup.service -n 80" >&2
    systemctl status zascarr-backup.service --no-pager -l || true
    exit 1
fi
say "Resultado del servicio: $(systemctl show -p Result --value zascarr-backup.service)"
say "--- estado ---"
jq . "${BACKUP_STATUS_DIR}/status.json" 2>/dev/null || true
say "--- timer ---"
systemctl list-timers zascarr-backup.timer --no-pager | head -3
say "--- copias locales ---"
ls -l "${BACKUP_DIR}" | tail -4 || true
say "--- copias fuera del disco ---"
ls -l "${BACKUP_OFFSITE_DIR}" | tail -4 || true
say "Instalación completada. El aviso en /estado requiere desplegar B1."
