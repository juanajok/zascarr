#!/usr/bin/env bash
# Piloto remoto DeepSeek. Ejecutar en portátil con clave montada en secreto Docker.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS="$ROOT/uxlab/results"
KEY="$ROOT/uxlab/.secrets/deepseek_api_key"
BASE="$ROOT/uxlab/compose.uxlab.yml"
OVERLAY="$ROOT/uxlab/compose.agents.yml"

command -v docker >/dev/null || { echo "Docker no instalado" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 no instalado" >&2; exit 1; }
[[ -s "$KEY" ]] || { echo "Falta uxlab/.secrets/deepseek_api_key. Ver uxlab/agents/README.md." >&2; exit 2; }
[[ "$(stat -c '%a' "$KEY")" == "600" ]] || { echo "La clave debe tener chmod 600 (no se usará con permisos amplios)" >&2; exit 2; }
export UXLAB_DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
export UXLAB_GIT_SHA="$(git -C "$ROOT" rev-parse HEAD)"
export UXLAB_RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)"
export DEEPSEEK_MAX_USD="${DEEPSEEK_MAX_USD:-0.05}"
OWNER_UID="$(id -u)"
OWNER_GID="$(id -g)"
mkdir -p "$RESULTS/agents/$UXLAB_RUN_ID"
dc() { docker compose -f "$BASE" -f "$OVERLAY" "$@"; }

restore_owner() {
  docker run --rm --pull never --network none --read-only \
    --user 0:0 --cap-drop ALL --cap-add CHOWN \
    --mount "type=bind,source=$RESULTS,target=/reports" \
    busybox:1.36 chown -R "$OWNER_UID:$OWNER_GID" /reports
}

cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 )); then
    dc ps -a 2>&1 | tee "$RESULTS/agents/$UXLAB_RUN_ID/compose-ps.txt" || true
    dc logs --no-color --tail=150 postgres seed app browser 2>&1 \
      | tee "$RESULTS/agents/$UXLAB_RUN_ID/bootstrap.log" || true
  fi
  python3 "$ROOT/uxlab/agents/report.py" \
    "$RESULTS/agents/$UXLAB_RUN_ID" || true
  restore_owner || { echo "Error restaurando permisos del host" >&2; (( status != 0 )) || status=4; }
  dc down --volumes --remove-orphans >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

dc down --volumes --remove-orphans
dc up -d --build browser
# Contratos ejecutados antes de consumir un solo token de DeepSeek.
dc run --rm --no-deps agent node --test agents/contracts.test.mjs
# Seis sesiones SEPARADAS; entre cada una se restablece el fixture y se abre
# un contexto independiente. Solo el contenedor 'agent' tiene acceso DeepSeek.
for scenario in PILOT-01 PILOT-02; do
  for persona in p1-movil p2-teclado p3-zoom; do
    export UXLAB_SCENARIO="$scenario"
    export UXLAB_PERSONA="$persona"
    echo "UXLab / DeepSeek: $scenario / $persona"
    dc run --rm --no-deps reset-fixture
    dc run --rm --no-deps agent
  done
done
echo "Seis sesiones terminadas. Informe en $RESULTS/agents/$UXLAB_RUN_ID/"
