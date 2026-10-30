#!/usr/bin/env bash
# =============================================================================
# probar_restauracion.sh — restaura un dump en una base desechable (#334 B2).
#
# Nunca arranca la aplicación: solo habla con el contenedor `postgres`.
# Crea `zascarr_restore_<TS>_<pid>`, restaura el dump, comprueba recuentos y
# esquema, y la borra SIEMPRE (trap). Deja `restore-status.json` para /estado.
#
#   sudo bash scripts/probar_restauracion.sh --dump <dump.sql.gz>
#   (sin --dump usa el backup_* local más reciente; fallback al offsite)
# =============================================================================
set -euo pipefail
umask 022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${ZASCARR_REPO:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
# shellcheck source=scripts/_comun.sh
source "${REPO_DIR}/scripts/_comun.sh"
# shellcheck source=scripts/_credenciales.sh
source "${SCRIPT_DIR}/_credenciales.sh"

BACKUP_OFFSITE_DIR="${BACKUP_OFFSITE_DIR:-/media/Backup/zascarr/postgres}"
BACKUP_STATUS_DIR="${BACKUP_STATUS_DIR:-/var/lib/zascarr/backup-status}"
RESTORE_STATUS_FILE="${RESTORE_STATUS_FILE:-${BACKUP_STATUS_DIR}/restore-status.json}"

DUMP=""
MANIFEST=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dump) DUMP="${2:-}"; shift 2 ;;
        --manifest) MANIFEST="${2:-}"; shift 2 ;;
        -h|--help)
            echo "Uso: $0 [--dump DUMP.sql.gz] [--manifest MANIFIESTO.json]"
            exit 0 ;;
        *) die "Opción desconocida: $1" ;;
    esac
done

comprobar_requisitos
comprobar_env_legible "${ENV_FILE}"
install -d -m 755 "${BACKUP_STATUS_DIR}" || die "No puedo crear ${BACKUP_STATUS_DIR}."

INICIO="$(date +%s)"
TEMP=""
ERR=""
# `psql_temp` corre en una subshell (command substitution): deja aquí el detalle
# saneado para que `on_exit` lo use al escribir el estado, sin volver a psql.
DETALLE_TEMP_FILE="${RESTORE_STATUS_FILE}.detalle.$$"
STATUS_WRITTEN=0
DUMP_SHA=""
DUMP_BYTES=""
TABLAS_DUMP=""
TABLAS_REST=""
ALEMBIC_DUMP=""
ALEMBIC_REST=""
FILES_DUMP=""; SERIES_DUMP=""; ISSUES_DUMP=""; WISHLIST_DUMP=""
FILES_REST=""; SERIES_REST=""; ISSUES_REST=""; WISHLIST_REST=""
MANIFEST_STATUS=""
MANIFEST_SHA=""
MANIFEST_BYTES=""
MANIFEST_ALEMBIC=""
MANIFEST_DESTINO=""
MANIFEST_DESPLEGADO=""

# ── Dump por defecto ────────────────────────────────────────────────────────
if [[ -z "${DUMP}" ]]; then
    DUMP="$(ls -1t "${BACKUP_DIR}"/backup_*.sql.gz 2>/dev/null | head -1 || true)"
    if [[ -z "${DUMP}" ]]; then
        DUMP="$(ls -1t "${BACKUP_OFFSITE_DIR}"/backup_*.sql.gz 2>/dev/null | head -1 || true)"
    fi
fi
[[ -n "${DUMP}" && -f "${DUMP}" ]] || die "No encuentro un dump para restaurar."

# ── Manifiesto (junto al dump o en los directorios de copias) ───────────────
BASE="$(basename "${DUMP}")"
STEM="${BASE%.sql.gz}"
if [[ -z "${MANIFEST}" ]]; then
    for dir in "$(dirname "${DUMP}")" "${BACKUP_DIR}" "${BACKUP_OFFSITE_DIR}"; do
        if [[ -f "${dir}/MANIFIESTO-${STEM}.json" ]]; then
            MANIFEST="${dir}/MANIFIESTO-${STEM}.json"
            break
        fi
    done
fi
if [[ -n "${MANIFEST}" && -f "${MANIFEST}" ]]; then
    MANIFEST_SHA="$(jq -r '.sha256 // empty' "${MANIFEST}" 2>/dev/null || true)"
    MANIFEST_BYTES="$(jq -r '.bytes // empty' "${MANIFEST}" 2>/dev/null || true)"
    MANIFEST_ALEMBIC="$(jq -r '.alembic // empty' "${MANIFEST}" 2>/dev/null || true)"
    MANIFEST_DESTINO="$(jq -r '.codigo_destino_sha_completo // empty' "${MANIFEST}" 2>/dev/null || true)"
    MANIFEST_DESPLEGADO="$(jq -r '.codigo_desplegado_sha_completo // empty' "${MANIFEST}" 2>/dev/null || true)"
    [[ -n "${MANIFEST_DESPLEGADO}" ]] || MANIFEST_STATUS="manifest_sin_codigo_desplegado"
else
    MANIFEST_STATUS="manifest_ausente"
fi

escribir_restore_estado() {
    local estado="$1" error="${2:-}" detalle="${3:-}"
    local now last_ok last_ok_iso tmp recuentos
    now="$(date +%s)"
    last_ok="$(jq -r '.last_ok_at_epoch // empty' "${RESTORE_STATUS_FILE}" 2>/dev/null || true)"
    if [[ "${estado}" == "ok" || "${estado}" == "warning" ]]; then
        last_ok="${now}"
    fi
    last_ok_iso=""
    if [[ -n "${last_ok}" && "${last_ok}" != "0" ]]; then
        last_ok_iso="$(date -d "@${last_ok}" -Iseconds 2>/dev/null || true)"
    fi
    recuentos="$(jq -n \
        --arg files "${FILES_REST:-}" --arg series "${SERIES_REST:-}" \
        --arg issues "${ISSUES_REST:-}" --arg wishlist "${WISHLIST_REST:-}" \
        '{files: ($files|tonumber? // null), series: ($series|tonumber? // null),
          issues: ($issues|tonumber? // null), wishlist: ($wishlist|tonumber? // null)}')"
    tmp="${RESTORE_STATUS_FILE}.tmp.$$"
    if ! jq -n \
        --arg status "${estado}" \
        --arg error "${error}" \
        --arg detalle "${detalle}" \
        --arg dump "$(basename "${DUMP}")" \
        --arg sha "${DUMP_SHA}" \
        --argjson bytes "${DUMP_BYTES:-0}" \
        --arg manifest "$([[ -n "${MANIFEST}" ]] && basename "${MANIFEST}" || true)" \
        --arg manifest_warning "${MANIFEST_STATUS}" \
        --arg destino "${MANIFEST_DESTINO}" \
        --arg desplegado "${MANIFEST_DESPLEGADO}" \
        --argjson tablas "${TABLAS_REST:-0}" \
        --argjson recuentos "${recuentos}" \
        --arg alembic "${ALEMBIC_REST:-${ALEMBIC_DUMP}}" \
        --argjson duracion "$(( $(date +%s) - INICIO ))" \
        --argjson last_ok "${last_ok:-0}" \
        --arg last_ok_at "${last_ok_iso}" \
        --arg created_at "$(date -Iseconds)" \
        '{schema: 1, status: $status, error: (if $error == "" then null else $error end),
          detalle: (if $detalle == "" then null else $detalle end),
          dump: $dump, sha256: $sha, bytes: $bytes, manifest: $manifest,
          manifest_warning: (if $manifest_warning == "" then null else $manifest_warning end),
          codigo_destino: $destino, codigo_desplegado: $desplegado,
          tablas: $tablas, recuentos: $recuentos, alembic: $alembic,
          duracion_s: $duracion, last_ok_at_epoch: $last_ok,
          last_ok_at: $last_ok_at, created_at: $created_at}' \
        > "${tmp}"; then
        rm -f "${tmp}"
        return 1
    fi
    chmod 644 "${tmp}" || { rm -f "${tmp}"; return 1; }
    mv "${tmp}" "${RESTORE_STATUS_FILE}" || { rm -f "${tmp}"; return 1; }
    STATUS_WRITTEN=1
    return 0
}

limpiar() {
    if [[ -n "${TEMP}" ]]; then
        "${COMPOSE[@]}" exec -T postgres dropdb -U "${DB_USER}" --if-exists --force "${TEMP}" \
            >/dev/null 2>&1 || true
    fi
    [[ -z "${ERR}" ]] || rm -f "${ERR}"
}
on_exit() {
    local rc=$?
    limpiar
    if (( rc != 0 )) && (( STATUS_WRITTEN == 0 )); then
        if [[ -f "${DETALLE_TEMP_FILE}" ]]; then
            escribir_restore_estado "failed" "restore_failed" \
                "$(cat "${DETALLE_TEMP_FILE}")" || true
        else
            escribir_restore_estado "failed" "unexpected" || true
        fi
    fi
    rm -f "${DETALLE_TEMP_FILE}"
    exit "${rc}"
}
trap on_exit EXIT

contar_copy() {
    local dump="$1" tabla="$2"
    gzip -dc "${dump}" | awk -v t="${tabla}" '
        $0 ~ "^COPY public\\." t " " { en=1; next }
        en && $0 == "\\." { en=0 }
        en { n++ }
        END { print n+0 }
    '
}

# Red de seguridad (la primera barrera es `psql -v VERBOSITY=terse`):
#   1) aplanar CR/LF (un CR no puede inyectar una línea nueva),
#   2) lista permitida: SOLO ERROR:/FATAL:/PANIC: (con espacios iniciales),
#   3) redactar credenciales,
#   4) unir, recortar y truncar a 400 caracteres.
# Se descartan CONTEXT/DETAIL/LINE/STATEMENT/HINT/QUERY y cualquier otra línea.
# Sin línea permitida devuelve vacío: el llamador escribe `detalle: null`.
sanear_detalle() {
    local texto
    texto="$(tr '\r' '\n' \
        | awk '{
            linea=$0
            sub(/^[[:space:]]+/, "", linea)
            if (linea ~ /^(ERROR|FATAL|PANIC):/) print linea
        }' \
        | sed -E \
            -e 's#[[:space:]]+$##' \
            -e 's#(://[^:/@[:space:]]+:).*@#\1***@#g' \
            -e 's#((password|passwd|pwd|PGPASSWORD)[[:space:]]*=[[:space:]]*)("[^"]*"|'"'"'[^'"'"']*'"'"'|[^[:space:]&)]*)#\1***#Ig' \
            -e 's#((password|passwd|pwd|PGPASSWORD)[[:space:]]*=[[:space:]]*).*#\1***#Ig' \
        | tr '\n' ' ' \
        | sed -E 's/[[:space:]]+$//' \
        | cut -c1-400)"
    printf '%s' "${texto}"
}

# El texto crudo de psql nunca se imprime: ni aquí ni en el JSON. Si no hay
# ERROR/FATAL/PANIC utilizable, se apunta al registro en vez de inventar detalle.
mensaje_psql_sin_detalle() {
    echo "[restauración] psql falló sin un ERROR/FATAL utilizable; revisa el registro de restauración y los logs de postgres." >&2
}

psql_temp() {
    local err salida detalle
    err="$(mktemp "${TMPDIR:-/tmp}/zascarr-psql.XXXXXX")" || return 1
    if ! salida="$("${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" -d "${TEMP}" -At \
            -v VERBOSITY=terse -c "$1" 2>"${err}")"; then
        detalle="$(sanear_detalle < "${err}")"
        rm -f "${err}"
        if [[ -n "${detalle}" ]]; then
            echo "[restauración] Motivo de psql: ${detalle}" >&2
        else
            mensaje_psql_sin_detalle
        fi
        # `psql_temp` corre en una subshell: `on_exit` escribirá el JSON con este
        # mismo texto saneado (o `detalle: null` si el fichero queda vacío).
        printf '%s' "${detalle}" > "${DETALLE_TEMP_FILE}" || true
        return 1
    fi
    rm -f "${err}"
    printf '%s\n' "${salida}"
}

# ── Verificar dump + manifiesto ─────────────────────────────────────────────
verificar_dump "${DUMP}" || {
    escribir_restore_estado "failed" "${VERIFY_ERROR_CODE:-verify_failed}" || true
    die "El dump no pasó la verificación."
}
DUMP_SHA="$(sha256sum "${DUMP}" | awk '{print $1}')"
DUMP_BYTES="$(stat -c %s "${DUMP}")"
if [[ -n "${MANIFEST_SHA}" && "${MANIFEST_SHA}" != "${DUMP_SHA}" ]]; then
    escribir_restore_estado "failed" "manifest_no_coincide" || true
    die "El SHA del manifiesto no coincide con el dump."
fi
if [[ -n "${MANIFEST_BYTES}" && "${MANIFEST_BYTES}" != "${DUMP_BYTES}" ]]; then
    escribir_restore_estado "failed" "manifest_no_coincide" || true
    die "Los bytes del manifiesto no coinciden con el dump."
fi
if [[ -f "${DUMP}.sha256" ]]; then
    if ! ( cd "$(dirname "${DUMP}")" && sha256sum -c "$(basename "${DUMP}").sha256" >/dev/null ); then
        escribir_restore_estado "failed" "sha256_no_coincide" || true
        die "El .sha256 no coincide con el dump."
    fi
fi

TABLAS_DUMP="$(gzip -dc "${DUMP}" | grep -c '^CREATE TABLE public\.' || true)"
ALEMBIC_DUMP="$(gzip -dc "${DUMP}" | awk '
    /^COPY public\.alembic_version / { en=1; next }
    en && $0 == "\\." { en=0 }
    en && !visto { print; visto=1 }
')"
FILES_DUMP="$(contar_copy "${DUMP}" files)"
SERIES_DUMP="$(contar_copy "${DUMP}" series)"
ISSUES_DUMP="$(contar_copy "${DUMP}" issues)"
WISHLIST_DUMP="$(contar_copy "${DUMP}" wishlist)"

# ── Base desechable + restauración ──────────────────────────────────────────
TS="$(date +%Y%m%d_%H%M%S)"
TEMP="zascarr_restore_${TS}_$$"
ERR="$(mktemp "${TMPDIR:-/tmp}/zascarr-restore.XXXXXX")"
"${COMPOSE[@]}" exec -T postgres dropdb -U "${DB_USER}" --if-exists --force "${TEMP}" \
    >/dev/null 2>&1 || true
"${COMPOSE[@]}" exec -T postgres createdb -U "${DB_USER}" "${TEMP}" \
    || { escribir_restore_estado "failed" "createdb_failed" || true; die "No pude crear ${TEMP}."; }
if ! gzip -dc "${DUMP}" | "${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" \
        -d "${TEMP}" -v ON_ERROR_STOP=1 -v VERBOSITY=terse -q >/dev/null 2>"${ERR}"; then
    DETALLE="$(sanear_detalle < "${ERR}")"
    escribir_restore_estado "failed" "restore_failed" "${DETALLE}" || true
    # El motivo también sale por pantalla (en la CI solo se veía este mensaje y el porqué quedaba en el JSON).
    if [[ -n "${DETALLE}" ]]; then
        echo "[restauración] Motivo de psql: ${DETALLE}" >&2
    else
        mensaje_psql_sin_detalle
    fi
    die "La restauración falló."
fi

# `relkind r/p` = tablas normales y particionadas, que es justo lo que pg_dump
# escribe como `CREATE TABLE`. information_schema incluiría vistas y foráneas.
TABLAS_REST="$(psql_temp "select count(*) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'public' and c.relkind in ('r', 'p')")"
for tabla in alembic_version series files wishlist; do
    # `to_regclass` imprime `alembic_version` o `public.alembic_version` según
    # el search_path; la pregunta es solo si existe.
    presente="$(psql_temp "select to_regclass('public.${tabla}') is not null")"
    [[ "${presente}" == "t" ]] || {
        escribir_restore_estado "failed" "tabla_ausente" "falta ${tabla}" || true
        die "Falta la tabla ${tabla} en la restauración."
    }
done
ALEMBIC_REST="$(psql_temp "select version_num from alembic_version")"
FILES_REST="$(psql_temp "select count(*) from files")"
SERIES_REST="$(psql_temp "select count(*) from series")"
ISSUES_REST="$(psql_temp "select count(*) from issues")"
WISHLIST_REST="$(psql_temp "select count(*) from wishlist")"

if [[ "${TABLAS_REST}" != "${TABLAS_DUMP}" ]]; then
    escribir_restore_estado "failed" "tablas_distintas" \
        "dump=${TABLAS_DUMP} restaurada=${TABLAS_REST}" || true
    die "El número de tablas no coincide (dump=${TABLAS_DUMP}, restaurada=${TABLAS_REST})."
fi
for par in "files:${FILES_DUMP}:${FILES_REST}" "series:${SERIES_DUMP}:${SERIES_REST}" \
           "issues:${ISSUES_DUMP}:${ISSUES_REST}" "wishlist:${WISHLIST_DUMP}:${WISHLIST_REST}"; do
    tabla="${par%%:*}"; resto="${par#*:}"; esperado="${resto%%:*}"; obtenido="${resto#*:}"
    if [[ "${esperado}" != "${obtenido}" ]]; then
        escribir_restore_estado "failed" "recuento_distinto" \
            "${tabla}: dump=${esperado} restaurada=${obtenido}" || true
        die "El recuento de ${tabla} no coincide."
    fi
done
if [[ -n "${MANIFEST_ALEMBIC}" && "${ALEMBIC_REST}" != "${MANIFEST_ALEMBIC}" ]]; then
    escribir_restore_estado "failed" "alembic_distinto" \
        "manifiesto=${MANIFEST_ALEMBIC} restaurada=${ALEMBIC_REST}" || true
    die "La revisión de Alembic no coincide."
fi

if [[ -n "${MANIFEST_STATUS}" ]]; then
    escribir_restore_estado "warning" "${MANIFEST_STATUS}" || true
    warn "Restauración correcta, pero el manifiesto no acredita el commit desplegado (${MANIFEST_STATUS})."
    exit 2
fi
escribir_restore_estado "ok" || true
success "Restauración verificada: ${TABLAS_REST} tablas; files=${FILES_REST}, series=${SERIES_REST}, issues=${ISSUES_REST}."
exit 0
