#!/usr/bin/env bash
# =============================================================================
# _comun.sh — utilidades compartidas por los scripts de operación de ZascArr.
#
# NO se ejecuta solo: se carga con `source`. Quien lo carga debe haber hecho
# antes `set -euo pipefail`.
#
# Un único sitio para lo que antes estaba copiado en update.sh y rollback.sh
# (y empezaba a divergir): rutas, array COMPOSE, colores, mensajes y esperas.
#
# Dato clave que justifica el array COMPOSE: el .env NO vive en el repo, vive
# en ZASCARR_ROOT (el padre, junto a config/), así que ningún comando puede
# depender del cwd. Todo va con -f y --env-file explícitos.
# =============================================================================

# Guardia contra doble carga (un script puede cargar a otro que lo cargue).
# Con `if` y no con `[[ ]] && return`: bajo `set -e` esa forma abreviada
# devuelve 1 cuando la variable no está puesta y aborta el script que carga.
if [[ -n "${_ZASCARR_COMUN_CARGADO:-}" ]]; then
    return 0
fi
_ZASCARR_COMUN_CARGADO=1

# SCRIPT_DIR es el del script que hace `source`, no el de este fichero.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
COMPOSE_FILE="${REPO_DIR}/docker-compose.yml"
ENV_FILE="${ZASCARR_ROOT}/.env"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/zascarr/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_NAME="${DB_NAME:-zascarr}"
DB_USER="${DB_USER:-comics_admin}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-60}"

B='\033[1m'; G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; N='\033[0m'
info()    { echo -e "${B}→${N} $*"; }
success() { echo -e "${G}✓${N} $*"; }
warn()    { echo -e "${Y}⚠${N}  $*"; }
die()     { echo -e "${R}✗${N} $*" >&2; exit 1; }

COMPOSE=(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}")

# bootstrap.sh deja un symlink REPO_DIR/.env -> ENV_FILE para que un
# "docker compose" manual (sin --env-file) invocado desde el repo también
# encuentre la configuración real, en vez de arrancar en silencio con los
# valores por defecto de docker-compose.yml. Estos scripts ya son inmunes por
# el array COMPOSE de arriba, pero se re-verifica aquí en cada ejecución por
# si el symlink se perdió (está en .gitignore, no lo repone un git reset):
# así el contrato ".env vive en ZASCARR_ROOT, se ve desde REPO_DIR" se
# mantiene desde un único sitio, no repartido por cada script.
if [[ -f "${ENV_FILE}" ]] && [[ "$(readlink -f "${REPO_DIR}/.env" 2>/dev/null)" != "$(readlink -f "${ENV_FILE}")" ]]; then
    ln -sf "${ENV_FILE}" "${REPO_DIR}/.env" 2>/dev/null || true
fi

comprobar_requisitos() {
    command -v docker >/dev/null 2>&1 || die \
        "No encuentro Docker. Instálalo con: sudo apt-get install docker.io docker-compose-plugin"
    docker compose version >/dev/null 2>&1 || die \
        "Falta el plugin de Docker Compose. Instálalo con: sudo apt-get install docker-compose-plugin"
    command -v git >/dev/null 2>&1 || die \
        "No encuentro git. Instálalo con: sudo apt-get install git"
    command -v curl >/dev/null 2>&1 || die \
        "No encuentro curl. Instálalo con: sudo apt-get install curl"
    command -v gzip >/dev/null 2>&1 || die \
        "No encuentro gzip. Instálalo con: sudo apt-get install gzip"
    docker info >/dev/null 2>&1 || die \
        "El demonio de Docker no responde. Arranca el servicio con: sudo systemctl start docker"
    [[ -f "${COMPOSE_FILE}" ]] || die \
        "No encuentro ${COMPOSE_FILE}. ¿Está el repo completo en ${REPO_DIR}?"
    [[ -f "${ENV_FILE}" ]] || die \
        "No encuentro ${ENV_FILE}. Se espera el .env que creó bootstrap.sh en ${ZASCARR_ROOT}."
}

# Los scripts se invocan con sudo (el backup va a /var/backups, que es de root),
# pero el repo es del usuario. Git >= 2.35.1 aborta en ese caso con "detected
# dubious ownership". Hay que detectarlo ANTES de tocar nada: si rollback.sh
# vaciara la BD y luego git se negara a resetear, el destrozo sería doble.
comprobar_git_utilizable() {
    local salida
    if ! salida="$(git -C "${REPO_DIR}" rev-parse --is-inside-work-tree 2>&1)"; then
        if [[ "${salida}" == *"dubious ownership"* ]]; then
            die "Git se niega a trabajar en ${REPO_DIR} por propietario distinto (dubious ownership).
  Es lo típico al ejecutar con sudo un repo que no es de root. Solución:
    sudo git config --global --add safe.directory ${REPO_DIR}
  O bien ejecuta el script como el usuario dueño del repo."
        fi
        die "No puedo usar git en ${REPO_DIR}: ${salida}"
    fi
}

# El nombre del backup y el de la referencia de rescate comparten el mismo TS
# (los genera update.sh), y de ahí sale el emparejamiento. Esto vive aquí para
# que los dos scripts usen exactamente el mismo criterio.
refs_rescate() {
    git -C "${REPO_DIR}" for-each-ref --sort=-refname \
        --format='%(refname) %(objectname)' refs/zascarr/update 2>/dev/null || true
}

ts_de_ref()   { local r="$1"; r="${r##*/}"; printf '%s' "${r}"; }
dump_de_ref() { printf '%s/update_%s.sql.gz' "${BACKUP_DIR}" "$(ts_de_ref "$1")"; }

# Una referencia de rescate sin su dump no sirve para nada (rollback.sh no
# tendría qué restaurar), así que se poda sola. Nunca toca la que se acaba de
# crear (se pasa en $1) ni las que sí conservan su pareja. Es lo que mantiene
# acotado el número de referencias sin borrar nunca un ancla utilizable.
podar_refs_huerfanas() {
    local conservar="${1:-}" ref
    while read -r ref _sha; do
        if [[ -z "${ref:-}" ]]; then continue; fi
        if [[ "${ref}" == "${conservar}" ]]; then continue; fi
        if [[ -f "$(dump_de_ref "${ref}")" ]]; then continue; fi
        git -C "${REPO_DIR}" update-ref -d "${ref}" 2>/dev/null || true
    done < <(refs_rescate)
}

# Igual que podar_refs_huerfanas, pero para el namespace del propio rollback:
# refs/zascarr/rollback-rescue/<TS> deja de servir cuando su dump de seguridad
# rollback-safety_<TS>.sql.gz ya ha caducado por la retención.
podar_refs_rescate_rollback() {
    local conservar="${1:-}" ref
    while read -r ref _sha; do
        if [[ -z "${ref:-}" ]]; then continue; fi
        if [[ "${ref}" == "${conservar}" ]]; then continue; fi
        if [[ -f "${BACKUP_DIR}/rollback-safety_$(ts_de_ref "${ref}").sql.gz" ]]; then continue; fi
        git -C "${REPO_DIR}" update-ref -d "${ref}" 2>/dev/null || true
    done < <(git -C "${REPO_DIR}" for-each-ref --sort=-refname \
        --format='%(refname) %(objectname)' refs/zascarr/rollback-rescue 2>/dev/null || true)
}

# Espera a que PostgreSQL acepte conexiones. Devuelve 1 si se agota el tiempo.
esperar_postgres() {
    local max="${1:-60}" transcurrido=0
    until "${COMPOSE[@]}" exec -T postgres pg_isready -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; do
        transcurrido=$((transcurrido + 2))
        [[ "${transcurrido}" -lt "${max}" ]] || return 1
        echo -n "."; sleep 2
    done
    echo ""
    return 0
}

# Espera al healthcheck de ZascArr. Devuelve 1 si se agota el tiempo.
esperar_healthcheck() {
    local max="${1:-${HEALTH_TIMEOUT}}" transcurrido=0
    until curl -sf "${HEALTH_URL}" >/dev/null 2>&1; do
        transcurrido=$((transcurrido + 2))
        [[ "${transcurrido}" -lt "${max}" ]] || return 1
        echo -n "."; sleep 2
    done
    echo ""
    return 0
}

# Comprueba que un .sql.gz es un gzip íntegro y no está vacío. Es la diferencia
# entre "tengo un backup" y "tengo algo con nombre de backup".
verificar_dump() {
    local dump="$1"
    [[ -f "${dump}" ]] || die "No existe el backup: ${dump}"
    [[ -s "${dump}" ]] || die "El backup está vacío (0 bytes): ${dump}"
    gzip -t "${dump}" 2>/dev/null || die \
        "El backup está corrupto (gzip -t falla): ${dump}
  No lo uso: restaurarlo dejaría la base de datos a medias. Busca otro dump o
  revisa por qué se truncó antes de seguir."
    return 0
}

# pg_dump -> .sql.gz atómico (temporal + mv). Un fallo a mitad nunca deja un .gz
# parcial con pinta de válido, y el resultado se verifica antes de darlo por bueno.
volcar_postgres() {
    local destino="$1" tmp="${1}.tmp"
    rm -f "${tmp}"
    if ! "${COMPOSE[@]}" exec -T postgres pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${tmp}"; then
        rm -f "${tmp}"
        return 1
    fi
    if ! gzip -t "${tmp}" 2>/dev/null; then
        rm -f "${tmp}"
        return 1
    fi
    mv "${tmp}" "${destino}"
    return 0
}

# Aplica la retención a los tres tipos de dump: los diarios (backup_<TS>), los
# emparejados con una actualización (update_<TS>) y la red de seguridad del
# rollback (rollback-safety_<TS>). Todos caducan a los RETENTION_DAYS.
aplicar_retencion() {
    find "${BACKUP_DIR}" -maxdepth 1 \( \
        -name 'backup_*.sql.gz' -o \
        -name 'update_*.sql.gz' -o \
        -name 'rollback-safety_*.sql.gz' \
    \) -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
}
