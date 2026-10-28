#!/usr/bin/env bash
# Wrapper instalado en /usr/local/bin/restore-check.sh.
# El script real vive en el repo: una mejora no obliga a reinstalar el wrapper.
set -euo pipefail
REPO="${ZASCARR_REPO:-/opt/zascarr/zascarr}"
exec "${REPO}/scripts/probar_restauracion.sh" "$@"
