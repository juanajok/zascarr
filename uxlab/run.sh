#!/usr/bin/env bash
# Ejecutar solo contra uxlab/compose.uxlab.yml (NO contra el Compose de producción).
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/uxlab/compose.uxlab.yml"
RESULTS="$ROOT/uxlab/results"
command -v docker >/dev/null || { echo "Docker no instalado" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 no instalado" >&2; exit 1; }
export UXLAB_DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
mkdir -p "$RESULTS"
dc() { docker compose -f "$COMPOSE" "$@"; }

cleanup() {
    local status=$?
    trap - EXIT
    if [ "$status" -ne 0 ]; then
        echo >&2
        echo "UXLab falló (exit $status). Estado y logs de arranque:" >&2
        dc ps -a 2>&1 | tee "$RESULTS/compose-ps.txt" || true
        dc logs --no-color --tail=250 permissions postgres seed app 2>&1 \
            | tee "$RESULTS/bootstrap.log" || true
        echo "Diagnóstico conservado en $RESULTS/bootstrap.log" >&2
    fi
    dc down --volumes --remove-orphans >/dev/null 2>&1 || true
    exit "$status"
}
trap cleanup EXIT

# Volúmenes de uso EXCLUSIVO UXLab. Nunca emplear con el proyecto de producción.
dc down --volumes --remove-orphans
dc up -d --build app
dc run --build --rm tests
echo "Resultados Playwright: $RESULTS/"
