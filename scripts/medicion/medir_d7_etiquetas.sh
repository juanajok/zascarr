#!/usr/bin/env bash
# =============================================================================
# Medición D-7 (#402): uso real de etiquetas y CBZ con <Tags>/<Genre>.
#
# Solo lectura: no escribe en la base de datos ni en disco. Se ejecuta dentro
# del contenedor de la app (tiene la BD y la biblioteca montadas) y sale por
# pantalla; con --json, JSON para pegar en la incidencia.
#
# Uso (en la Pi, como root, igual que los demás scripts de operación):
#     scripts/medicion/medir_d7_etiquetas.sh [--json]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

# shellcheck source=../_comun.sh
source "${REPO_DIR}/scripts/_comun.sh"

info "Midiendo D-7 dentro del contenedor (solo lectura; puede tardar en una biblioteca grande)…"
"${COMPOSE[@]}" exec -T zascarr python - < "${SCRIPT_DIR}/medir_d7_etiquetas.py" "$@"
