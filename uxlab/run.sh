#!/usr/bin/env bash
# Laboratorio independiente: NUNCA invocar el Compose de producción.
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="$ROOT/uxlab/compose.uxlab.yml"
RESULTS="$ROOT/uxlab/results"

usage() {
  echo "Uso: bash uxlab/run.sh [--stability | --repeat-each N]" >&2
  exit 2
}
REPEAT_EACH=1
if [[ "${1:-}" == "--stability" ]]; then
  REPEAT_EACH=3
  shift
elif [[ "${1:-}" == "--repeat-each" ]]; then
  [[ $# -ge 2 ]] || usage
  REPEAT_EACH="$2"
  shift 2
fi
[[ $# -eq 0 ]] || usage
[[ "$REPEAT_EACH" =~ ^[0-9]+$ ]] || usage
(( REPEAT_EACH >= 1 && REPEAT_EACH <= 10 )) || usage

command -v docker >/dev/null || { echo "Docker no instalado" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 no instalado" >&2; exit 1; }
export UXLAB_DB_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
mkdir -p "$RESULTS"
dc() { docker compose -f "$COMPOSE" "$@"; }

restore_report_ownership() {
  # El runner usa root dentro del contenedor. Recuperar UID/GID reales del host
  # incluso al fallar Playwright o al interrumpirse la preparación.
  # Busybox ya es dependencia del Compose UXLab: sin red, sin nuevos privilegios.
  if ! docker run --rm --network none --pull never \
       --user 0:0 --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE \
       --mount "type=bind,source=$RESULTS,target=/reports" \
       busybox:1.36 chown -R "$HOST_UID:$HOST_GID" /reports; then
    echo "AVISO: no se pudo restaurar la propiedad de $RESULTS (¿Docker rootless/userns?)." >&2
    return 1
  fi
}

cleanup() {
  local status=$?
  trap - EXIT
  if (( status != 0 )); then
    echo >&2
    echo "UXLab falló (exit $status). Estado y logs de arranque:" >&2
    dc ps -a 2>&1 | tee "$RESULTS/compose-ps.txt" || true
    dc logs --no-color --tail=250 permissions postgres seed app 2>&1 \
      | tee "$RESULTS/bootstrap.log" || true
    echo "Diagnóstico conservado en $RESULTS/bootstrap.log" >&2
  fi
  restore_report_ownership || { (( status != 0 )) || status=4; }
  dc down --volumes --remove-orphans >/dev/null 2>&1 || true
  exit "$status"
}
trap cleanup EXIT

# Únicamente limpia volúmenes del proyecto dedicado zascarr-uxlab.
dc down --volumes --remove-orphans
# Ya existe busybox al iniciarse el servicio de permisos; sin nueva descarga.
dc up -d --build app
# --no-deps evita relanzar el servicio seed y duplicar datos.
# Salvar exit code incluso cuando hay fallos: el resumen de estabilidad es útil.
TEST_STATUS=0
dc run --build --rm --no-deps tests npx playwright test --repeat-each "$REPEAT_EACH" || TEST_STATUS=$?

if [[ -f "$RESULTS/results.json" ]]; then
  python3 "$ROOT/uxlab/stability_report.py" "$RESULTS/results.json" \
    "$RESULTS/stability-summary.md" "$RESULTS/stability-summary.json" \
    "$REPEAT_EACH" || { (( TEST_STATUS != 0 )) || TEST_STATUS=5; }
fi
echo "Informes Playwright: $RESULTS/"
exit "$TEST_STATUS"
