#!/usr/bin/env bash
# =============================================================================
# backup.sh — copia de seguridad diaria de PostgreSQL (E2 del backlog:
# "quiero que haya copias de seguridad automáticas sin configurar nada").
#
# El backup se escribe en un disco distinto al de los datos (BACKUP_DIR,
# configurable) — un backup que muere con el disco que respalda no es un
# backup. De paso aplica retención automática a los tres tipos de dump:
# los diarios (backup_<TS>), los emparejados con una actualización
# (update_<TS>) y la red de seguridad del rollback (rollback-safety_<TS>).
#
# Instalación:
#   1. Copia este script a /usr/local/bin/backup.sh y chmod +x
#   2. Define ZASCARR_REPO (o ZASCARR_ROOT) apuntando a tu instalación:
#        echo 'ZASCARR_REPO=/home/USUARIO/zascarr/zascarr' | sudo tee /etc/default/zascarr
#      (y lee ese fichero con EnvironmentFile= en el unit de abajo)
#   3. Instala el timer systemd incluido al final de este fichero:
#        sudo cp zascarr-backup.{service,timer} /etc/systemd/system/
#        sudo systemctl daemon-reload
#        sudo systemctl enable --now zascarr-backup.timer
#   4. Ajusta BACKUP_DIR/RETENTION_DAYS si tu disco de respaldo es otro.
#
# NOTA (E3, cerrada 2026-09-24): el RESTORE ya no es una historia pendiente:
# es scripts/rollback.sh (empareja commit y dump por la referencia de
# rescate que deja update.sh). Backup y rollback ya se probaron los dos
# contra Docker/PostgreSQL reales, incluido dropdb --force con una conexión
# concurrente abierta — ver docs/BACKLOG.md.
# =============================================================================
set -euo pipefail

# El .env vive en ZASCARR_ROOT (el padre del repo), NO en el repo: por eso
# todo va con -f y --env-file explícitos. Si este script se copia a
# /usr/local/bin, el repo ya no es "el directorio de al lado": ZASCARR_REPO
# (o ZASCARR_ROOT) lo fija a mano.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${ZASCARR_REPO:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
COMPOSE_FILE="${REPO_DIR}/docker-compose.yml"
ENV_FILE="${ZASCARR_ROOT}/.env"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/zascarr/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_NAME="${DB_NAME:-zascarr}"
DB_USER="${DB_USER:-comics_admin}"

COMPOSE=(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}")

[[ -f "${COMPOSE_FILE}" ]] || { echo "[backup] ERROR: no encuentro ${COMPOSE_FILE}" >&2; exit 1; }
[[ -f "${ENV_FILE}" ]] || { echo "[backup] ERROR: no encuentro ${ENV_FILE} (se espera el .env que creó bootstrap.sh)" >&2; exit 1; }

mkdir -p "${BACKUP_DIR}" || { echo "[backup] ERROR: no puedo crear ${BACKUP_DIR}" >&2; exit 1; }

TS="$(date +%Y%m%d_%H%M%S)"
DEST="${BACKUP_DIR}/backup_${TS}.sql.gz"
TMP="${DEST}.tmp"

# Temporal + verificación + mv atómico: un fallo a mitad nunca deja un .gz
# parcial con pinta de válido, y un dump sin verificar no es un backup.
if ! "${COMPOSE[@]}" exec -T postgres pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${TMP}"; then
    rm -f "${TMP}"
    echo "[backup] ERROR: pg_dump falló. No se ha guardado nada." >&2
    exit 1
fi
if ! gzip -t "${TMP}"; then
    rm -f "${TMP}"
    echo "[backup] ERROR: el gzip resultante no pasa la verificación; se descarta." >&2
    exit 1
fi
mv "${TMP}" "${DEST}"

echo "[backup] ${DB_NAME} → ${DEST}"

# Retención: también se lleva los dumps de update.sh/rollback.sh que ya hayan
# caducado (todos comparten el criterio de RETENTION_DAYS).
find "${BACKUP_DIR}" -maxdepth 1 \( \
    -name 'backup_*.sql.gz' -o \
    -name 'update_*.sql.gz' -o \
    -name 'rollback-safety_*.sql.gz' \
    \) -mtime "+${RETENTION_DAYS}" -delete

# =============================================================================
# unidades systemd para el timer (guardar como ficheros separados):
#
# --- /etc/systemd/system/zascarr-backup.service ---
# [Unit]
# Description=Backup diario de PostgreSQL para ZascArr
# After=docker.service
#
# [Service]
# Type=oneshot
# EnvironmentFile=-/etc/default/zascarr
# ExecStart=/usr/local/bin/backup.sh
#
# --- /etc/systemd/system/zascarr-backup.timer ---
# [Unit]
# Description=Ejecuta el backup de ZascArr una vez al día
#
# [Timer]
# OnCalendar=*-*-* 04:00:00
# Persistent=true
# RandomizedDelaySec=15min
#
# [Install]
# WantedBy=timers.target
# =============================================================================
