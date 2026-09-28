#!/usr/bin/env bash
# =============================================================================
# etiquetar.sh — B6: previsualizar y escribir ComicInfo.xml dentro de los CBZ.
#
# El fichero del coleccionista es lo más valioso del sistema: por defecto este
# comando NO ESCRIBE NADA, solo imprime el plan campo a campo (qué cambiará,
# qué se conserva por procedencia desconocida y qué ya coincide). Para
# aplicarlo hay que pedirlo explícitamente con --apply.
#
# Uso:
#   bash scripts/etiquetar.sh                 # simulación (seguro)
#   bash scripts/etiquetar.sh --limit 200
#   bash scripts/etiquetar.sh --apply         # escribe de verdad
#   bash scripts/etiquetar.sh --apply --no-overwrite
#
# Python no vive en el host (la imagen lo trae), así que el comando entra por
# `docker compose run --rm zascarr` — el mismo camino que usan update.sh y
# rollback.sh para las migraciones. Las rutas de `files.file_path` son las de
# DENTRO del contenedor (/media/library/...), y solo ahí son válidas.
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_comun.sh
source "${SCRIPT_DIR}/_comun.sh"

command -v docker >/dev/null 2>&1 || die \
    "No encuentro Docker. Instálalo con: sudo apt-get install docker.io docker-compose-plugin"

[[ -f "${ENV_FILE}" ]] || die \
    "No encuentro ${ENV_FILE}. Copia .env.example a ${ZASCARR_ROOT}/.env y rellénalo."

MODO="simulación (no se escribe nada)"
for arg in "$@"; do
    if [[ "${arg}" == "--apply" ]]; then
        MODO="APLICAR — se reescriben los CBZ"
    fi
done

info "Etiquetado ComicInfo (B6) — ${MODO}"

"${COMPOSE[@]}" run --rm zascarr \
    python -m zascarr.cli.etiquetar "$@" || die \
    "El etiquetado falló. La colección no se toca a medias: cada CBZ se sustituye
  de forma atómica y verificada, y un fallo deja el original intacto. Revisa el
  informe de arriba para ver qué fichero y por qué."
