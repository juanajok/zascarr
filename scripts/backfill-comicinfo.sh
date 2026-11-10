#!/usr/bin/env bash
# =============================================================================
# BL-ETQ2b (#573): relee el ComicInfo.xml de los CBZ ya registrados y aplica
# etiquetas y géneros (ETQ2). Solo lectura de ficheros; DRY-RUN por defecto.
#
# Uso (en la Pi, como root, desde el repo):
#     scripts/backfill-comicinfo.sh --dry-run    # informe (defecto)
#     scripts/backfill-comicinfo.sh --aplicar    # aplica (idempotente)
#
# No escribe en los ficheros, no mueve ni renombra nada. Comparte el cerrojo
# de ciclo con el importador y el rescan: si hay una pasada en marcha, avisa y
# no toca nada.
# =============================================================================
set -euo pipefail

BACKFILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${BACKFILL_DIR}/.." && pwd)"

# shellcheck source=_comun.sh
source "${REPO_DIR}/scripts/_comun.sh"

info "Releyendo el ComicInfo de la biblioteca registrada (solo lectura de ficheros)…"
"${COMPOSE[@]}" exec -T zascarr python - < "${BACKFILL_DIR}/backfill-comicinfo.py" "$@"
