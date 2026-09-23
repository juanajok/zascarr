#!/usr/bin/env bash
# =============================================================================
# backup.sh — copia de seguridad diaria de PostgreSQL (E2 del backlog:
# "quiero que haya copias de seguridad automáticas sin configurar nada").
#
# El backup se escribe en un disco distinto al de los datos (BACKUP_DIR,
# configurable) — un backup que muere con el disco que respalda no es un
# backup. De paso aplica retención automática.
#
# Instalación:
#   1. Copia este script a /usr/local/bin/backup.sh y chmod +x
#   2. Instala el timer systemd incluido al final de este fichero:
#        sudo cp zascarr-backup.{service,timer} /etc/systemd/system/
#        sudo systemctl daemon-reload
#        sudo systemctl enable --now zascarr-backup.timer
#   3. Ajusta BACKUP_DIR/RETENTION_DAYS si tu disco de respaldo es otro.
#
# NOTA (E3, no implementado aquí): un backup que nunca se ha restaurado no
# es un backup probado. El script de restore es una historia aparte.
# =============================================================================
set -euo pipefail

# Directorio del repo (donde vive docker-compose.yml). Si copias este script
# a /usr/local/bin, define ZASCARR_REPO a mano.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${ZASCARR_REPO:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/zascarr/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_NAME="${DB_NAME:-tebeoteca}"
DB_USER="${DB_USER:-comics_admin}"

mkdir -p "$BACKUP_DIR"

TS=$(date +%Y%m%d_%H%M%S)
DEST="${BACKUP_DIR}/backup_${TS}.sql.gz"
TMP="${DEST}.tmp"

cd "$REPO_DIR"
docker compose exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$TMP"
mv "$TMP" "$DEST"

echo "[backup] $DB_NAME → $DEST"

# Retención: borra copias más antiguas que RETENTION_DAYS. "Sin configurar
# nada por mi parte" incluye no tener que acordarse de vaciar el disco.
find "$BACKUP_DIR" -name 'backup_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete

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
