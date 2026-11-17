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
# La unidad corre con `ProtectHome=true`: el cliente `docker` no puede usar `$HOME/.docker`, así que usa el
# directorio limpio de root que crean tmpfiles/instalar_ops (QA en la VM: sin esto, `docker compose config` falla).
export DOCKER_CONFIG="${DOCKER_CONFIG:-/run/zascarr-ops/docker}"
# La app real escucha en el 8000; el 18000 solo era el valor del arnés de pruebas. Se puede sobreescribir.
export HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health}"
exec "${REPO_DIR}/scripts/restaurar_datos.sh" --produccion --copia "$1"
