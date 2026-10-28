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

# SCRIPT_DIR es el del script que hace `source`, no el de este fichero. Si el
# llamador ya fijó REPO_DIR (backup.sh instalado fuera del repo), se respeta:
# así el script copiado a /usr/local/bin también encuentra el repo real.
if [[ -z "${REPO_DIR:-}" ]]; then
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
else
    SCRIPT_DIR="${REPO_DIR}/scripts"
fi
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
COMPOSE_FILE="${REPO_DIR}/docker-compose.yml"
# El `.env` puede venir **explícito** en el entorno (las pruebas, o un
# administrador que apunta a otro fichero): entonces es de quien llama y este
# script no toca el `.env` del checkout más abajo. Sin él, la convención de
# siempre: el `.env` vive en ZASCARR_ROOT.
ENV_FILE_EXPLICITO=0
if [[ -n "${ENV_FILE:-}" ]]; then
    ENV_FILE_EXPLICITO=1
else
    ENV_FILE="${ZASCARR_ROOT}/.env"
fi

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

# Credenciales del .env (validar, comprobar protección): ADR 0012.
# shellcheck source=scripts/_credenciales.sh
source "${SCRIPT_DIR}/_credenciales.sh"

# bootstrap.sh deja un symlink REPO_DIR/.env -> ENV_FILE para que un
# "docker compose" manual (sin --env-file) invocado desde el repo también
# encuentre la configuración real, en vez de arrancar en silencio con los
# valores por defecto de docker-compose.yml. Estos scripts ya son inmunes por
# el array COMPOSE de arriba, pero se re-verifica aquí en cada ejecución por
# si el symlink se perdió (está en .gitignore, no lo repone un git reset):
# así el contrato ".env vive en ZASCARR_ROOT, se ve desde REPO_DIR" se
# mantiene desde un único sitio, no repartido por cada script.
#
# NO se hace si el `.env` vino explícito: en una prueba el destino es un
# temporal que desaparece (dejaría un enlace ROTO en el checkout, y
# `get_settings()` lee `.env` desde el cwd), y un administrador que pasa su
# propio `ENV_FILE` no espera que le cambien la raíz del repo.
if (( ENV_FILE_EXPLICITO == 1 )); then
    :
elif [[ -f "${ENV_FILE}" ]] && [[ "$(readlink -f "${REPO_DIR}/.env" 2>/dev/null)" != "$(readlink -f "${ENV_FILE}")" ]]; then
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
    command -v jq >/dev/null 2>&1 || die \
        "No encuentro jq. Instálalo con: sudo apt-get install jq"
    docker info >/dev/null 2>&1 || die \
        "El demonio de Docker no responde. Arranca el servicio con: sudo systemctl start docker"
    [[ -f "${COMPOSE_FILE}" ]] || die \
        "No encuentro ${COMPOSE_FILE}. ¿Está el repo completo en ${REPO_DIR}?"
    [[ -f "${ENV_FILE}" ]] || die \
        "No encuentro ${ENV_FILE}. Se espera el .env que creó bootstrap.sh en ${ZASCARR_ROOT}."
    # Existe pero no se puede leer (600 de root y no somos root): se dice antes de tocar nada (ADR 0012).
    comprobar_env_legible
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

refs_rescate_rollback() {
    git -C "${REPO_DIR}" for-each-ref --sort=-refname \
        --format='%(refname) %(objectname)' refs/zascarr/rollback-rescue 2>/dev/null || true
}

ts_de_ref()   { local r="$1"; r="${r##*/}"; printf '%s' "${r}"; }
dump_de_ref() { printf '%s/update_%s.sql.gz' "${BACKUP_DIR}" "$(ts_de_ref "$1")"; }

# Un dump con una referencia de rescate viva no se borra por edad: la ref es la
# que permite volver y, si el dump desaparece, podar_refs_* se lleva también la
# ref. La regla es por referencia, no por fecha ni por posición en la lista.
dumps_protegidos_por_ref() {
    local ref _sha
    while read -r ref _sha; do
        [[ -n "${ref:-}" ]] || continue
        printf 'update_%s.sql.gz\n' "$(ts_de_ref "${ref}")"
    done < <(refs_rescate)
    while read -r ref _sha; do
        [[ -n "${ref:-}" ]] || continue
        printf 'rollback-safety_%s.sql.gz\n' "$(ts_de_ref "${ref}")"
    done < <(refs_rescate_rollback)
}

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
    done < <(refs_rescate_rollback)
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

# Comprueba que un .sql.gz es un gzip íntegro, tiene cabecera de pg_dump y las
# tablas que rollback.sh necesita. Devuelve 1 (no `die`) para que backup.sh
# pueda dejar un estado visible; update.sh aborta igual con `set -e`.
# Deja la causa en VERIFY_ERROR_CODE.
VERIFY_ERROR_CODE=""
verificar_dump() {
    local dump="$1" tmp tabla
    VERIFY_ERROR_CODE=""
    [[ -f "${dump}" ]] || {
        VERIFY_ERROR_CODE="not_found"
        echo "[dump] ERROR: no existe ${dump}" >&2
        return 1
    }
    [[ -s "${dump}" ]] || {
        VERIFY_ERROR_CODE="empty"
        echo "[dump] ERROR: está vacío (0 bytes): ${dump}" >&2
        return 1
    }
    gzip -t "${dump}" 2>/dev/null || {
        VERIFY_ERROR_CODE="gzip_invalid"
        echo "[dump] ERROR: gzip -t falla; no lo uso: ${dump}" >&2
        return 1
    }
    tmp="$(mktemp "${TMPDIR:-/tmp}/zascarr-verify.XXXXXX")" || {
        VERIFY_ERROR_CODE="decompress_failed"
        return 1
    }
    if ! gzip -dc "${dump}" > "${tmp}"; then
        rm -f "${tmp}"
        VERIFY_ERROR_CODE="decompress_failed"
        echo "[dump] ERROR: no se pudo descomprimir: ${dump}" >&2
        return 1
    fi
    if ! grep -q 'PostgreSQL database dump' "${tmp}"; then
        rm -f "${tmp}"
        VERIFY_ERROR_CODE="header_missing"
        echo "[dump] ERROR: no tiene cabecera de pg_dump: ${dump}" >&2
        return 1
    fi
    for tabla in alembic_version series files wishlist; do
        if ! grep -q "^COPY public\.${tabla} " "${tmp}"; then
            rm -f "${tmp}"
            VERIFY_ERROR_CODE="tables_missing"
            echo "[dump] ERROR: falta la tabla ${tabla}: ${dump}" >&2
            return 1
        fi
    done
    rm -f "${tmp}"
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
    chmod 600 "${destino}" 2>/dev/null || true
    return 0
}

# Manifiesto de una copia: identidad del candidato + integridad. Atómico y 0600.
# `extra` es un objeto JSON con campos adicionales (offsite, ref emparejada...).
# Devuelve la ruta del manifiesto por stdout; 1 si no se pudo escribir.
escribir_manifiesto() {
    local dump="$1" origen="$2" id="$3"
    local extra="${4:-}"
    local base stem dir manifest tmp sha bytes created commit alembic
    [[ -n "${extra}" ]] || extra="{}"
    [[ -f "${dump}" ]] || { echo "[manifiesto] ERROR: no existe ${dump}" >&2; return 1; }
    command -v jq >/dev/null 2>&1 || { echo "[manifiesto] ERROR: falta jq" >&2; return 1; }
    base="$(basename "${dump}")"
    stem="${base%.sql.gz}"
    dir="$(dirname "${dump}")"
    manifest="${dir}/MANIFIESTO-${stem}.json"
    tmp="${manifest}.tmp.$$"
    sha="$(sha256sum "${dump}" | awk '{print $1}')" || return 1
    bytes="$(stat -c %s "${dump}")" || return 1
    created="$(date -Iseconds)"
    commit="$(git -C "${REPO_DIR}" rev-parse HEAD 2>/dev/null || true)"
    alembic="$("${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -At \
        -c "select version_num from alembic_version" 2>/dev/null | tr -d '[:space:]' || true)"
    if ! jq -n \
        --arg backup "${base}" \
        --arg sha256 "${sha}" \
        --argjson bytes "${bytes}" \
        --arg commit "${commit}" \
        --arg alembic "${alembic}" \
        --arg created "${created}" \
        --arg origin "${origen}" \
        --arg id "${id}" \
        --argjson extra "${extra}" \
        '{schema: 1, backup: $backup, sha256: $sha256, bytes: $bytes,
          codigo_desplegado_sha_completo: $commit, alembic: $alembic,
          created_at: $created, origin: $origin, id: $id} + $extra' \
        > "${tmp}"; then
        rm -f "${tmp}"
        echo "[manifiesto] ERROR: jq no pudo escribir ${manifest}" >&2
        return 1
    fi
    chmod 600 "${tmp}" || { rm -f "${tmp}"; return 1; }
    mv "${tmp}" "${manifest}" || { rm -f "${tmp}"; return 1; }
    printf '%s\n' "${manifest}"
    return 0
}

# Aplica la retención a los tres tipos de dump en un directorio (por defecto,
# BACKUP_DIR). Un dump con una ref de rescate viva no se borra por edad; el
# resto caduca a los RETENTION_DAYS. La regla es por referencia, no por fecha.
aplicar_retencion() {
    local dir="${1:-${BACKUP_DIR}}"
    local protegidos=() p args=()
    mapfile -t protegidos < <(dumps_protegidos_por_ref)
    for p in "${protegidos[@]}"; do
        args+=(! -name "${p}")
    done
    find "${dir}" -maxdepth 1 \( \
        -name 'backup_*.sql.gz' -o \
        -name 'update_*.sql.gz' -o \
        -name 'rollback-safety_*.sql.gz' \
    \) -mtime "+${RETENTION_DAYS}" "${args[@]}" -delete 2>/dev/null || true
}
