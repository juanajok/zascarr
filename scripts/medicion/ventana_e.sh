#!/usr/bin/env bash
# =============================================================================
# ventana_e.sh — orquestador de la medición E de #326 en la Pi.
#
# Solo herramienta de ventana: no cambia la app ni el catálogo de producción.
# Crea bases desechables `*_test_*`, un directorio sintético fuera de la
# biblioteca y contenedores one-off; todo se borra al terminar. La biblioteca
# real se monta en solo lectura.
#
# Uso:
#   sudo bash scripts/medicion/ventana_e.sh --dry-run
#   sudo bash scripts/medicion/ventana_e.sh --yes
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=scripts/_comun.sh
source "${REPO_DIR}/scripts/_comun.sh"
# shellcheck source=scripts/_credenciales.sh
source "${REPO_DIR}/scripts/_credenciales.sh"

DRY_RUN=0
YES=0
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y) YES=1 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) die "Opción desconocida: ${arg}" ;;
    esac
done
(( DRY_RUN == 0 || YES == 0 )) || die "Usa --dry-run o --yes, no los dos."
(( DRY_RUN == 1 || YES == 1 )) || die "Indica --dry-run o --yes."
[[ "$(id -u)" -eq 0 ]] || die "Ejecútalo con sudo."

[[ -f "${ENV_FILE}" ]] || die "No encuentro ${ENV_FILE}."
LIB_HOST="$(env_valor "${ENV_FILE}" HOST_LIBRARY_DIR)"
[[ -n "${LIB_HOST}" ]] || die "HOST_LIBRARY_DIR no está definido en ${ENV_FILE}."
LIB_HOST="$(realpath "${LIB_HOST}")"
[[ -d "${LIB_HOST}" ]] || die "La biblioteca no existe o no es un directorio."

TS="$(date +%Y%m%d_%H%M%S)"
SINT_DB="zascarr_medicion_sint_test_${TS}"
REF_DB="zascarr_medicion_ref_test_${TS}"
REG_DB="zascarr_medicion_reg_test_${TS}"
SYNTH="$(dirname "${LIB_HOST}")/.zascarr-medicion-${TS}"
RESULT="/var/lib/zascarr/medicion-e/${TS}"
case "$(realpath -m "${SYNTH}")" in
    "${LIB_HOST}"/*) die "El directorio sintético quedaría dentro de la biblioteca." ;;
esac

IMG="$(docker inspect zascarr-orquestador --format '{{.Config.Image}}' 2>/dev/null || true)"
[[ -n "${IMG}" ]] || die "No encuentro la imagen de la app (¿está arriba?)."
NET="$(docker inspect zascarr-db --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' 2>/dev/null | head -1)"
[[ -n "${NET}" ]] || die "No encuentro la red del compose."
PUID="$(docker inspect zascarr-orquestador --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | sed -n 's/^PUID=//p' | tail -1)"
PGID="$(docker inspect zascarr-orquestador --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | sed -n 's/^PGID=//p' | tail -1)"
PUID="${PUID:-1000}"; PGID="${PGID:-1000}"
DB_PASSWORD="$(env_valor "${ENV_FILE}" DB_PASSWORD)"
[[ -n "${DB_PASSWORD}" ]] || die "DB_PASSWORD no está en ${ENV_FILE}."
DB_URL="postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@postgres:5432/"

say() { printf '%s\n' "$*"; }
dc() { "${COMPOSE[@]}" exec -T postgres "$@"; }
run() {
    if (( DRY_RUN )); then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}

stop_if_busy() {
    if docker ps --format '{{.Names}}' | grep -q '^zascarr-medicion-'; then
        die "Ya hay una medición en marcha."
    fi
    if systemctl is-active --quiet zascarr-backup.service 2>/dev/null; then
        die "Hay una copia de seguridad en marcha."
    fi
    if systemctl is-active --quiet zascarr-restore.service 2>/dev/null; then
        die "Hay una restauración en marcha."
    fi
}

preflight() {
    local disponible_mb libres_kb abiertos
    disponible_mb="$(free -m | awk '/^Mem:/{print $7}')"
    (( disponible_mb >= 512 )) || die "MemAvailable=${disponible_mb} MiB: por debajo de 512 MiB."
    libres_kb="$(df -Pk "$(dirname "${SYNTH}")" | awk 'NR==2{print $4}')"
    (( libres_kb >= 8 * 1024 * 1024 )) || die "Menos de 8 GiB libres para los sintéticos."
    curl -fsS "${HEALTH_URL}" | jq -e '.status == "healthy"' >/dev/null \
        || die "La app no está healthy."
    abiertos="$(dc psql -U "${DB_USER}" -d "${DB_NAME}" -At -c \
        "select count(*) from import_runs where finished_at is null" 2>/dev/null || echo 1)"
    [[ "${abiertos}" == "0" ]] || die "Hay ${abiertos} import_runs abiertos."
    mountpoint -q "$(findmnt -n -o TARGET -T "${LIB_HOST}")" \
        || die "La biblioteca no está en un montaje."
    stop_if_busy
    say "Preflight OK: ${disponible_mb} MiB disponibles, ${libres_kb} KiB libres, app healthy."
}

cleanup() {
    local rc=$?
    trap - EXIT
    if (( DRY_RUN == 0 )); then
        for db in "${SINT_DB}" "${REF_DB}" "${REG_DB}"; do
            dc dropdb -U "${DB_USER}" --if-exists --force "${db}" >/dev/null 2>&1 || true
        done
        docker rm -f "zascarr-medicion-${TS}-seed" "zascarr-medicion-${TS}-synthetic" \
            "zascarr-medicion-${TS}-search" "zascarr-medicion-${TS}-register" >/dev/null 2>&1 || true
        [[ -n "${SYNTH}" && "${SYNTH}" != "${LIB_HOST}" ]] && rm -rf "${SYNTH}"
        rm -f "${TMP_ENV:-}" 2>/dev/null || true
    fi
    exit "${rc}"
}

run_medicion() {
    local db="$1" mode="$2" kind="$3" lib="$4"
    shift 4
    local nombre="zascarr-medicion-${TS}-${mode}"
    local archivo="${RESULT}/${mode}.json"
    TMP_ENV="$(mktemp)"
    chmod 600 "${TMP_ENV}"
    {
        printf 'DATABASE_URL=%s%s\n' "${DB_URL}" "${db}"
        printf 'LIBRARY_PATH=/media/library\n'
        printf 'PUID=%s\nPGID=%s\n' "${PUID}" "${PGID}"
    } > "${TMP_ENV}"
    say "→ ${mode}: ${db} (${kind})"
    run timeout 1800 docker run --rm --name "${nombre}" --network "${NET}" \
        --memory=512m --memory-swap=512m --env-file "${TMP_ENV}" \
        -v "${lib}:/media/library:ro" -v "${REPO_DIR}:/repo:ro" \
        "${IMG}" python /repo/scripts/medicion/medir_registro_incremental_pi.py \
        --mode "${mode}" --library /media/library --library-kind "${kind}" \
        --require-readonly "$@" > "${archivo}" 2> "${RESULT}/${mode}.err"
    rm -f "${TMP_ENV}"; TMP_ENV=""
    jq -e '.status == "ok"' "${archivo}" >/dev/null || die "La fase ${mode} falló; revisa ${RESULT}/${mode}.err."
}

generar() {
    local prefijo="$1" count="$2" start="$3" pages="$4" size="$5"
    run docker run --rm --network none \
        -e "PUID=${PUID}" -e "PGID=${PGID}" \
        -v "${SYNTH}:/sinteticos" -v "${REPO_DIR}:/repo:ro" \
        "${IMG}" python /repo/scripts/medicion/preparar_sinteticos.py \
        --out /sinteticos --prefix "${prefijo}" --count "${count}" \
        --start "${start}" --pages "${pages}" --size-mb "${size}" --series 40
}


cleanup_plan() {
    say "Bases: ${SINT_DB}, ${REF_DB}, ${REG_DB} (se borran al terminar)."
    say "Sintéticos: ${SYNTH} (fuera de la biblioteca; se borra)."
    say "Resultados: ${RESULT} (JSON saneado; logs .err root-only)."
    say "Biblioteca real configurada (montaje de solo lectura en el contenedor)."
}

if (( DRY_RUN )); then
    say "Plan de medición E (${TS})"
    cleanup_plan
    say "Imagen: ${IMG}; red: ${NET}; PUID/PGID: ${PUID}/${PGID}"
    say "No se crea nada. Ejecuta con --yes en la ventana."
    exit 0
fi

install -d -m 700 "${SYNTH}" "${RESULT}"
chown -R "${PUID}:${PGID}" "${SYNTH}"
trap cleanup EXIT
preflight

say "→ Creando bases desechables..."
dc createdb -U "${DB_USER}" "${SINT_DB}"
dc sh -c "pg_dump -U ${DB_USER} --schema-only ${DB_NAME} | psql -q -U ${DB_USER} -d ${SINT_DB}" >/dev/null
dc createdb -U "${DB_USER}" "${REF_DB}"
dc sh -c "pg_dump -U ${DB_USER} ${DB_NAME} | psql -q -U ${DB_USER} -d ${REF_DB}" >/dev/null
dc createdb -U "${DB_USER}" "${REG_DB}"
dc sh -c "pg_dump -U ${DB_USER} ${REF_DB} | psql -q -U ${DB_USER} -d ${REG_DB}" >/dev/null

say "→ Sintéticos: 100 viejos + 1.200 nuevos + 20 grandes..."
generar Viejos 100 0 12 0
run_medicion "${SINT_DB}" seed synthetic "${SYNTH}"
generar Nuevos 1200 100 12 0
generar Grandes 20 1200 1 100
run_medicion "${SINT_DB}" synthetic synthetic "${SYNTH}" \
    --expected-new 1220 --expected-old 100
if ! jq -e '.checks.E1.pass and .checks.E2.pass' "${RESULT}/synthetic.json" >/dev/null; then
    say "⚠ E1/E2 no han pasado el presupuesto: no se mide el USB real."
    jq -c '{E1:.checks.E1,E2:.checks.E2}' "${RESULT}/synthetic.json" || true
    exit 0
fi

say "→ USB real: buscar (solo lectura)..."
run_medicion "${REF_DB}" search real "${LIB_HOST}" --repeat 3
if ! jq -e '.checks.E3.pass' "${RESULT}/search.json" >/dev/null; then
    say "⚠ E3 (coste) ha fallado: no se ejecuta E4."
    jq -c '{E3:.checks.E3,E3c:.checks.E3c}' "${RESULT}/search.json" || true
    exit 0
fi
if ! jq -e '.checks.E3c.pass' "${RESULT}/search.json" >/dev/null; then
    say "⚠ E3c (cobertura) ha fallado: no se ejecuta E4. Se documenta como FAIL de cobertura."
    jq -c '{E3:.checks.E3,E3c:.checks.E3c,E3c_datos:.E3c}' "${RESULT}/search.json" || true
    exit 0
fi
if [[ "$(jq -r '.E3c.nuevos' "${RESULT}/search.json")" == "0" ]]; then
    say "E4 NOT RUN: no hay archivos nuevos que registrar."
    exit 0
fi

say "→ USB real: registrar muestra acotada..."
run_medicion "${REG_DB}" register real "${LIB_HOST}" \
    --max-files 100 --max-bytes 15GiB --verify-sha-samples 10

say "→ Resultados:"
for f in "${RESULT}"/*.json; do
    printf '  %s: ' "$(basename "${f}")"
    jq -c '{status,checks}' "${f}" || true
done
say "Informe crudo saneado en ${RESULT}."
