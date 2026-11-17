#!/usr/bin/env bash
# Wrapper de la unidad zascarr-restaurar@.service (BL-OPS2, #443).
set -euo pipefail
REPO="${ZASCARR_REPO:-/opt/zascarr/zascarr}"
exec "${REPO}/scripts/restaurar_datos.sh" --produccion --copia "$1"
