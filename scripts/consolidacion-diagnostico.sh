#!/usr/bin/env bash
# =============================================================================
# consolidacion-diagnostico.sh — CCM-0 (#999)
#
# Diagnóstico de solo lectura de la cobertura de metadatos. No consulta fuentes
# externas, no escribe en la base de datos y no toca la biblioteca.
#
# Uso:
#   sudo bash scripts/consolidacion-diagnostico.sh
#   sudo bash scripts/consolidacion-diagnostico.sh --json
#
# Python no vive en el host: entra por `docker compose run --rm zascarr`, igual
# que etiquetar.sh y migraciones de update.sh.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_comun.sh
source "${SCRIPT_DIR}/_comun.sh"

command -v docker >/dev/null 2>&1 || die \
    "No encuentro Docker. Instálalo con: sudo apt-get install docker.io docker-compose-plugin"

[[ -f "${ENV_FILE}" ]] || die \
    "No encuentro ${ENV_FILE}. Copia .env.example a ${ZASCARR_ROOT}/.env y rellénalo."
comprobar_env_legible

info "CCM-0 · diagnóstico de cobertura de metadatos (solo lectura)"
"${COMPOSE[@]}" run --rm zascarr \
    python -m zascarr.cli.consolidacion "$@" || die \
    "El diagnóstico falló. No se ha escrito nada: el comando es de solo lectura."
