#!/usr/bin/env bash
# Ejecutar siempre desde una copia del repositorio, NUNCA con el Compose de producción.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/uxlab/compose.uxlab.yml"
command -v docker >/dev/null || { echo "Docker no instalado" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 no instalado" >&2; exit 1; }
export UXLAB_DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
mkdir -p "$ROOT/uxlab/results"
dc() { docker compose -f "$COMPOSE" "$@"; }
# down -v toca SOLO los volúmenes del proyecto independiente zascarr-uxlab.
# Deja la BD limpia para obtener un oráculo comparable en cada ejecución.
trap 'dc down --volumes --remove-orphans >/dev/null 2>&1 || true' EXIT
dc down --volumes --remove-orphans
dc up -d --build app
dc run --build --rm tests
echo "Resultados Playwright: $ROOT/uxlab/results/"
