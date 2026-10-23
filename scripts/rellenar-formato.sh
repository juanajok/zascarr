#!/usr/bin/env bash
# =============================================================================
# rellenar-formato.sh — #307 (D5): guardar el formato REAL (por contenido) de los .cbr/.cb7 ya registrados.
#
# A DEMANDA: ningún ciclo lo lanza solo. Por defecto NO ESCRIBE NADA: dice cuántas filas faltan. Para rellenar un lote hay que pedirlo con --apply.
# Solo lee ≤ 512 bytes de cada fichero (y el directorio central si es un ZIP) y solo escribe en la base (files.metadata); nunca toca los ficheros.
#
# Uso:
#   sudo bash scripts/rellenar-formato.sh                      # cuántas filas faltan (no lee ni escribe nada)
#   sudo bash scripts/rellenar-formato.sh --apply --limite 100 # un lote
#
# No lo ejecutes sobre tu biblioteca real sin haberlo decidido: el coste de lectura en el disco USB no está medido.
# Python no vive en el host: entra por `docker compose run --rm zascarr`, como etiquetar.sh.
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

MODO="solo cuenta (no se lee ni se escribe nada)"
for arg in "$@"; do
    if [[ "${arg}" == "--apply" ]]; then
        MODO="APLICAR — se rellena un lote en la base (los ficheros no se tocan)"
    fi
done

info "Formato real por contenido (#307) — ${MODO}"

"${COMPOSE[@]}" run --rm zascarr \
    python -m zascarr.cli.rellenar_formato "$@" || die \
    "El relleno terminó con ficheros ilegibles o con un error. Los ficheros no se tocan y las filas sin rellenar siguen pendientes: se pueden reintentar."
