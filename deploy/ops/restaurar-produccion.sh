#!/usr/bin/env bash
# Wrapper de la unidad zascarr-restaurar@.service (BL-OPS2, #443).
# Traduce el entorno de la unidad a las variables que exige restaurar_datos.sh.
set -euo pipefail
if [[ ! "${1:-}" =~ ^[0-9]{8}_[0-9]{6}$ ]]; then
    echo "Copia no válida para restaurar." >&2
    exit 2
fi
REPO="${ZASCARR_REPO:-/opt/zascarr/zascarr}"
export REPO_DIR="${REPO_DIR:-$REPO}"
export ENV_FILE="${ENV_FILE:-$(dirname "$REPO")/.env}"
export COMPOSE_FILE="${COMPOSE_FILE:-$REPO/docker-compose.yml}"
export DB_NAME="${DB_NAME:-zascarr}"
export DB_USER="${DB_USER:-comics_admin}"
exec "${REPO_DIR}/scripts/restaurar_datos.sh" --produccion --copia "$1"
