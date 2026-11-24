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
export UXLAB_MAX_STEPS="${UXLAB_MAX_STEPS:-18}"
export UXLAB_MAX_INPUT_TOKENS="${UXLAB_MAX_INPUT_TOKENS:-60000}"
export UXLAB_IMAGE_DETAIL="${UXLAB_IMAGE_DETAIL:-low}"
export DEEPSEEK_TOTAL_MAX_USD="${DEEPSEEK_TOTAL_MAX_USD:-0.30}"

SCENARIOS=( ${UXLAB_SCENARIOS:-PILOT-01 PILOT-02} )
PERSONAS=( ${UXLAB_PERSONAS:-p1-movil p2-teclado p3-zoom} )
for id in "${SCENARIOS[@]}" "${PERSONAS[@]}"; do
  [[ "$id" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "Identificador de sesión inválido: $id" >&2; exit 2; }
done
[[ "$UXLAB_MAX_STEPS" =~ ^[0-9]+$ ]] && (( UXLAB_MAX_STEPS >= 1 && UXLAB_MAX_STEPS <= 60 )) || { echo "UXLAB_MAX_STEPS debe estar entre 1 y 60" >&2; exit 2; }
[[ "$UXLAB_MAX_INPUT_TOKENS" =~ ^[0-9]+$ ]] && (( UXLAB_MAX_INPUT_TOKENS >= 10000 && UXLAB_MAX_INPUT_TOKENS <= 250000 )) || { echo "UXLAB_MAX_INPUT_TOKENS fuera de rango" >&2; exit 2; }
[[ "$UXLAB_IMAGE_DETAIL" =~ ^(low|high|original|auto)$ ]] || { echo "UXLAB_IMAGE_DETAIL inválido" >&2; exit 2; }
python3 -c "import sys; sys.exit(0 if 0 < float(sys.argv[1]) <= 10 else 1)" "$DEEPSEEK_TOTAL_MAX_USD" || { echo "DEEPSEEK_TOTAL_MAX_USD inválido" >&2; exit 2; }
OWNER_UID="$(id -u)"
OWNER_GID="$(id -g)"
mkdir -p "$RESULTS/agents/$UXLAB_RUN_ID"
dc() { docker compose -f "$BASE" -f "$OVERLAY" "$@"; }

restore_owner() {
  docker run --rm --pull never --network none \
    --user 0:0 --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE \
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
dc build agent
# Contratos ejecutados antes de consumir un solo token de DeepSeek.
dc run --rm --no-deps agent node --test agents/contracts.test.mjs
# Seis sesiones SEPARADAS; entre cada una se restablece el fixture y se abre
# un contexto independiente. Solo el contenedor 'agent' tiene acceso DeepSeek.
SESSION_STATUS=0
for scenario in "${SCENARIOS[@]}"; do
  for persona in "${PERSONAS[@]}"; do
    export UXLAB_SCENARIO="$scenario"
    export UXLAB_PERSONA="$persona"
    echo "UXLab / DeepSeek: $scenario / $persona"
    if ! dc run --rm --no-deps reset-fixture; then
      echo "No se pudo restablecer el fixture; sesión omitida." >&2
      SESSION_STATUS=1
      continue
    fi
    dc run --rm --no-deps agent || SESSION_STATUS=1
    TOTAL_USD="$(python3 -c 'import glob,json,sys; print(sum(json.load(open(p)).get("model",{}).get("estimatedUSD",0) for p in glob.glob(sys.argv[1]+"/*/session.json")))' "$RESULTS/agents/$UXLAB_RUN_ID")"
    if python3 -c "import sys; sys.exit(0 if float('$TOTAL_USD') > float('$DEEPSEEK_TOTAL_MAX_USD') else 1)"; then
      echo "Presupuesto global alcanzado (USD $TOTAL_USD > $DEEPSEEK_TOTAL_MAX_USD); se detiene el bucle." >&2
      SESSION_STATUS=3
      break 2
    fi
  done
done
echo "Sesiones terminadas: ${#SCENARIOS[@]} escenarios × ${#PERSONAS[@]} perfiles. Informe en $RESULTS/agents/$UXLAB_RUN_ID/"
exit "$SESSION_STATUS"
