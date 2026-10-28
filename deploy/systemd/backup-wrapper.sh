#!/usr/bin/env bash
# Wrapper instalado en /usr/local/bin/backup.sh.
# El script real vive en el repo: así una mejora no obliga a reinstalar el wrapper.
set -euo pipefail
REPO="${ZASCARR_REPO:-/opt/zascarr/zascarr}"
exec "${REPO}/scripts/backup.sh" "$@"
