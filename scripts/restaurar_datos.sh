#!/usr/bin/env bash
# =============================================================================
# restaurar_datos.sh — Restaura SOLO los datos de un dump, sin cambiar el código.
#
# Caso 123a-10 de #123: reproduce la vuelta atrás de datos (el escenario de R)
# sin `git reset`, sin rebuild y sin tocar la biblioteca.
#
# Contrato de seguridad, todo ANTES del `dropdb`:
#   - árbol limpio y HEAD == --sha;
#   - ENV_FILE, COMPOSE_FILE, BACKUP_DIR, DB_NAME y DB_USER explícitos;
#   - `docker compose config` con el proyecto esperado (nunca `zascarr`);
#   - manifiesto con SHA-256, bytes y revisión coherentes;
#   - gzip, cabecera de pg_dump y las cinco tablas que exige el rollback (incluida `issues`);
#   - revisión Alembic del dump y de la BD actual contra --alembic-esperada;
#   - el id de intento, la comprobación que falló y la versión de la copia quedan en
#     `ops-restaurar.json` y, por intento terminado, en `ops-restaurar-intentos.jsonl` (máx. 20).
#
# Después: copia de seguridad `rollback-safety_<TS>.sql.gz` verificada, parada
# de la app, dropdb --force, createdb, psql ON_ERROR_STOP, `up -d` sin build,
# health y recuentos/vínculos contra el dump. El health se espera hasta
# HEALTH_TIMEOUT segundos (total), porque la app tarda unos segundos en
# arrancar tras `up -d`. Si falla después del dropdb, intenta recuperar la
# copia previa (best-effort) y sale ≠0 con la orden.
#
# Uso:
#   sudo bash scripts/restaurar_datos.sh \
#     --dump <dump.sql.gz> --sha <SHA> [--manifest <MANIFIESTO.json>] \
#     [--alembic-esperada <rev>] [--proyecto-esperado zascarr-123a] \
#     [--yes] [--dry-run]
#
# Variables obligatorias: REPO_DIR, ENV_FILE, COMPOSE_FILE, BACKUP_DIR,
# DB_NAME y DB_USER. Opcionales: HEALTH_URL, HEALTH_TIMEOUT (segundos TOTALES
# de espera, por defecto 120) y HEALTH_INTERVAL (segundos entre intentos, 2).
# `--forzar` está prohibido: este script no cambia el código.
# =============================================================================
set -euo pipefail
umask 022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DUMP=""
MANIFEST=""
SHA_ESPERADO=""
ALEMBIC_ESPERADA=""
PROYECTO_ESPERADO="zascarr-123a"
ASUMIR_SI=0
DRY_RUN=0
PRODUCCION=0
COPIA_TS=""
ASUMIR_PEDIDO=0
PROYECTO_PEDIDO=0

info() { printf '→ %s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }

# ── BL-OPS2: estado de la restauración (`ops-restaurar.json`, FR-24) ────────
# Lo escribe SOLO este script, con `printf`, temporal en el mismo directorio y `mv` atómico, 0644 y sin fallar la
# operación. Solo códigos y números: nunca la salida de un comando, mensajes de `die`, rutas ni valores de seguridad.
# UATP-06/07 (D-2/D-5): añade `intento` (16 hex), `comprobacion` (código cerrado de §4.4) y `copia_version`
# (tupla del manifiesto o null) y deja una línea por intento terminado en `ops-restaurar-intentos.jsonl`.
ESTADO_ON=0
INICIO_EPOCH="$(date +%s)"
COPIA_ID=""
COPIA_EPOCH=0
FASE_STATUS="verificando"
CODIGO_DIE="precondition_failed"
BASE_DIE="true"
COMPROBACION=""
COPIA_VERSION_JSON="null"
# UATP-08: campos aditivos del resumen; ninguno cambia el orden ni la seguridad.
RECUENTOS_PREVIOS_JSON="null"
FUERA_JSON="null"
COMPROBACIONES_JSON="[]"
VERSION_ARRANCADA_JSON="null"
HEALTH_JSON=""
INTENTO_REGISTRADO=0
INTENTO=""

# 16 hex minúsculas, una vez por ejecución (D-5). Sin `od` (coreutils) se deriva de la hora y el PID con
# `sha256sum`, ya exigido por el preflight: el formato no cambia y no se aborta por no poder generar el id.
generar_intento() {
    local hex=""
    if command -v od >/dev/null 2>&1; then
        hex="$(od -An -N8 -tx1 /dev/urandom 2>/dev/null | tr -d '[:space:]' || true)"
    fi
    if [[ ! "${hex}" =~ ^[0-9a-f]{16}$ ]]; then
        hex="$(printf '%s%s' "$(date +%s%N)" "$$" 2>/dev/null | sha256sum 2>/dev/null | cut -c1-16 || true)"
    fi
    [[ "${hex}" =~ ^[0-9a-f]{16}$ ]] || hex=""
    printf '%s' "${hex}"
}

json_str_o_null() {
    if [[ -n "$1" ]]; then printf '"%s"' "$1"; else printf 'null'; fi
}

# `copia_version`: solo las cuatro claves de D-2 y cada una con su regex; si el objeto no es válido, `null`.
# Se calcula en bash (sin interpolar el fichero en SQL ni en la UI) y nunca bloquea la restauración.
sanear_copia_version() {
    local crudo="$1" head build app alembic
    [[ -n "${crudo}" ]] || { printf 'null'; return 0; }
    printf '%s' "${crudo}" | jq -e 'type == "object"
        and (keys - ["head", "build_sha", "app_version", "alembic"] | length) == 0
        and (has("head") or has("build_sha") or has("app_version") or has("alembic"))' \
        >/dev/null 2>&1 || { printf 'null'; return 0; }
    head="$(printf '%s' "${crudo}" | jq -r '.head // "" | if type == "string" then . else "INVALIDO" end' 2>/dev/null || true)"
    build="$(printf '%s' "${crudo}" | jq -r '.build_sha // "" | if type == "string" then . else "INVALIDO" end' 2>/dev/null || true)"
    app="$(printf '%s' "${crudo}" | jq -r '.app_version // "" | if type == "string" then . else "INVALIDO" end' 2>/dev/null || true)"
    alembic="$(printf '%s' "${crudo}" | jq -r '.alembic // "" | if type == "string" then . else "INVALIDO" end' 2>/dev/null || true)"
    [[ -z "${head}" || "${head}" =~ ^[0-9a-f]{40}$ ]] || { printf 'null'; return 0; }
    [[ -z "${build}" || "${build}" =~ ^[0-9a-f]{40}$ ]] || { printf 'null'; return 0; }
    [[ -z "${app}" || "${app}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { printf 'null'; return 0; }
    [[ -z "${alembic}" || "${alembic}" =~ ^[0-9]{4}$ ]] || { printf 'null'; return 0; }
    printf '{"head":%s,"build_sha":%s,"app_version":%s,"alembic":%s}' \
        "$(json_str_o_null "${head}")" "$(json_str_o_null "${build}")" \
        "$(json_str_o_null "${app}")" "$(json_str_o_null "${alembic}")"
}

# `ops-restaurar-intentos.jsonl` (D-5): una línea por intento TERMINADO (`hecha`/`fallida`), como máximo 20
# (las más recientes), 0644, reescritura atómica y sin fallar la restauración si no se puede escribir. Solo
# códigos, números, booleanos, el id de intento y la tupla de versión: nunca rutas, hashes ni secretos (FR-24).
registrar_intento_jsonl() {
    local resultado="$1" error="$2" base_json="$3"
    (( INTENTO_REGISTRADO )) && return 0
    INTENTO_REGISTRADO=1
    local dir="${BACKUP_STATUS_DIR:-/var/lib/zascarr/backup-status}"
    local fichero="${dir}/ops-restaurar-intentos.jsonl" tmp linea fin_epoch
    local intento_json err_json comprobacion_json
    intento_json="$(json_str_o_null "${INTENTO}")"
    err_json="$(json_str_o_null "${error}")"
    comprobacion_json="$(json_str_o_null "${COMPROBACION}")"
    fin_epoch="$(date +%s)"
    linea="$(printf '{"schema":1,"intento":%s,"copia":"%s","copia_epoch":%s,"copia_version":%s,"inicio_epoch":%s,"fin_epoch":%s,"fase":"%s","resultado":"%s","error":%s,"comprobacion":%s,"base_en_su_sitio":%s}' \
        "${intento_json}" "${COPIA_ID}" "${COPIA_EPOCH}" "${COPIA_VERSION_JSON}" "${INICIO_EPOCH}" \
        "${fin_epoch}" "${FASE_STATUS}" "${resultado}" "${err_json}" "${comprobacion_json}" "${base_json}")"
    install -d -m 755 "${dir}" 2>/dev/null || return 0
    tmp="${dir}/.ops-restaurar-intentos.jsonl.tmp.$$"
    if { if [[ -f "${fichero}" ]]; then tail -n 19 "${fichero}" 2>/dev/null; fi; printf '%s\n' "${linea}"; } \
            >"${tmp}" 2>/dev/null \
            && chmod 644 "${tmp}" 2>/dev/null \
            && mv "${tmp}" "${fichero}" 2>/dev/null; then
        return 0
    fi
    rm -f "${tmp}" 2>/dev/null || true
    return 0
}

COMPROBACIONES_ORDEN=(existencia_copia manifiesto sha256_copia bytes_copia codigo_manifest
    gzip_cabecera cabecera_pg_dump tablas_dump alembic_revision recuentos_nueva
    vinculos_huerfanos seguridad_conservada copia_previa health)

comprobaciones_terminales() {
    # UATP-08/QA: array terminal en fallo; la comprobación que falló es `fallo` y las
    # posteriores `no_ejecutada`. Si el fallo no corresponde a una comprobación, todas
    # quedan `no_ejecutada` (nunca se inventa un ok).
    local error="$1" fallo="$2" codigo encontrado=0 filas=() fila
    if [[ -z "$fallo" ]]; then
        case "$error" in
            revision_distinta) fallo="alembic_revision" ;;
            arranque_fallido) fallo="health" ;;
            seguridad_ilegible|seguridad_no_aplicada) fallo="seguridad_conservada" ;;
            copia_previa_fallida) fallo="copia_previa" ;;
            verificacion_fallida|restauracion_fallida) fallo="recuentos_nueva" ;;
            *) fallo="" ;;
        esac
    fi
    for codigo in "${COMPROBACIONES_ORDEN[@]}"; do
        if [[ -n "$fallo" && "$codigo" == "$fallo" ]]; then
            fila="{\"codigo\":\"${codigo}\",\"estado\":\"fallo\"}"
            encontrado=1
        elif [[ -z "$fallo" || $encontrado -eq 0 ]]; then
            fila="{\"codigo\":\"${codigo}\",\"estado\":\"ok\"}"
            [[ -z "$fallo" ]] && fila="{\"codigo\":\"${codigo}\",\"estado\":\"no_ejecutada\"}"
        else
            fila="{\"codigo\":\"${codigo}\",\"estado\":\"no_ejecutada\"}"
        fi
        filas+=("$fila")
    done
    local IFS=","
    COMPROBACIONES_JSON="[${filas[*]}]"
}

estado_restaurar() {
    local fase="$1" resultado="$2" error="${3:-}" base="${4:-null}" recuentos="${5:-null}"
    (( ESTADO_ON )) || return 0
    local dir="${BACKUP_STATUS_DIR:-/var/lib/zascarr/backup-status}"
    local err_json="null" base_json="null" tmp ahora intento_json="null" comprobacion_json="null"
    [[ -n "$error" ]] && err_json="\"${error}\""
    case "$base" in true|false) base_json="$base" ;; esac
    intento_json="$(json_str_o_null "${INTENTO}")"
    comprobacion_json="$(json_str_o_null "${COMPROBACION}")"
    ahora="$(date +%s)"
    if [[ "$resultado" == "fallida" && "${COMPROBACIONES_JSON}" == "[]" ]]; then
        comprobaciones_terminales "$error" "${COMPROBACION}"
    fi
    install -d -m 755 "$dir" 2>/dev/null || return 0
    tmp="${dir}/.ops-restaurar.json.tmp.$$"
    if printf '{"schema":1,"intento":%s,"copia":"%s","copia_epoch":%s,"inicio_epoch":%s,"actualizado_epoch":%s,"fase":"%s","resultado":"%s","error":%s,"comprobacion":%s,"base_en_su_sitio":%s,"copia_version":%s,"recuentos":%s,"recuentos_previos":%s,"fuera":%s,"comprobaciones":%s,"version_arrancada":%s}\n' \
            "${intento_json}" "${COPIA_ID}" "${COPIA_EPOCH}" "${INICIO_EPOCH}" "$ahora" "$fase" "$resultado" \
            "$err_json" "${comprobacion_json}" "$base_json" "${COPIA_VERSION_JSON}" "$recuentos" \
            "${RECUENTOS_PREVIOS_JSON}" "${FUERA_JSON}" "${COMPROBACIONES_JSON}" "${VERSION_ARRANCADA_JSON}" >"${tmp}" 2>/dev/null \
            && chmod 644 "${tmp}" 2>/dev/null \
            && mv "${tmp}" "${dir}/ops-restaurar.json" 2>/dev/null; then
        case "$resultado" in
            hecha|fallida) registrar_intento_jsonl "$resultado" "$error" "$base_json" ;;
        esac
        return 0
    fi
    rm -f "${tmp}" 2>/dev/null || true
    return 0
}

# Un fallo del script deja el estado `fallida` con el código de la fase (FR-24). En el modo sin `--produccion` no
# escribe nada: ese modo conserva su comportamiento de siempre.
die() {
    printf 'ERROR: %s\n' "$*" >&2
    estado_restaurar "${FASE_STATUS}" "fallida" "${CODIGO_DIE}" "${BASE_DIE}"
    exit 1
}

# `omitida.json` (FR-27/AC-36): el cerrojo lo tenía otro proceso; no se toca `ops-restaurar.json` (podría pisar la
# restauración en marcha). Sin `jq` a propósito: debe poder escribirse aunque falte.
escribir_omitida_restaurar() {
    local dir="${BACKUP_STATUS_DIR:-/var/lib/zascarr/backup-status}" tmp
    install -d -m 755 "$dir" 2>/dev/null || return 0
    tmp="${dir}/.omitida.json.tmp.$$"
    if printf '{"schema":1,"accion":"restaurar","omitida_epoch":%s,"motivo":"operacion_en_curso"}\n' \
            "$(date +%s)" >"${tmp}" 2>/dev/null \
            && chmod 644 "${tmp}" 2>/dev/null \
            && mv "${tmp}" "${dir}/omitida.json" 2>/dev/null; then
        return 0
    fi
    rm -f "${tmp}" 2>/dev/null || true
    return 0
}

uso() {
    sed -n '3,32p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dump)              [[ -n "${2:-}" ]] || die "--dump necesita un valor"; DUMP="$2"; shift 2 ;;
        --manifest)          [[ -n "${2:-}" ]] || die "--manifest necesita un valor"; MANIFEST="$2"; shift 2 ;;
        --sha)               [[ -n "${2:-}" ]] || die "--sha necesita un valor"; SHA_ESPERADO="$2"; shift 2 ;;
        --alembic-esperada)  [[ -n "${2:-}" ]] || die "--alembic-esperada necesita un valor"; ALEMBIC_ESPERADA="$2"; shift 2 ;;
        --proyecto-esperado) [[ -n "${2:-}" ]] || die "--proyecto-esperado necesita un valor"; PROYECTO_ESPERADO="$2"; PROYECTO_PEDIDO=1; shift 2 ;;
        --yes|-y)            ASUMIR_SI=1; ASUMIR_PEDIDO=1; shift ;;
        --dry-run)           DRY_RUN=1; shift ;;
        --produccion)        PRODUCCION=1; shift ;;
        --copia)             [[ -n "${2:-}" ]] || die "--copia necesita un valor"; COPIA_TS="$2"; shift 2 ;;
        --forzar)            die "--forzar está prohibido: este script no cambia el código ni descarta cambios." ;;
        -h|--help)           uso; exit 0 ;;
        -*)                  die "Opción desconocida: $1" ;;
        *)                   die "Argumento inesperado: $1" ;;
    esac
done

# D-5: el id del intento se genera una vez por ejecución, antes de escribir el primer estado.
INTENTO="$(generar_intento)"

if (( PRODUCCION )); then
    COPIA_ID="backup-${COPIA_TS}"
    COPIA_EPOCH="$(date -d "${COPIA_TS:0:8} ${COPIA_TS:9:2}:${COPIA_TS:11:2}:${COPIA_TS:13:2}" +%s 2>/dev/null || printf '0')"
fi

# Cerrojo único de operaciones (BL-OPS1). Este script no usa `_comun.sh`: carga solo el cerrojo.
# shellcheck source=scripts/_cerrojo.sh
source "${SCRIPT_DIR}/_cerrojo.sh"
CERROJO_RC=0
tomar_cerrojo_operaciones || CERROJO_RC=$?
if (( CERROJO_RC == 75 )); then
    escribir_omitida_restaurar
    exit 75
elif (( CERROJO_RC != 0 )); then
    exit "${CERROJO_RC}"
fi
if (( PRODUCCION )); then
    ESTADO_ON=1
    estado_restaurar "verificando" "en_curso" "" "true"
fi

for cmd in docker git jq gzip gunzip sha256sum stat curl awk; do
    command -v "$cmd" >/dev/null 2>&1 || die "No encuentro $cmd."
done

# Lo que sale del dump, del manifiesto o de la BD se COMPARA tal cual (solo sin espacios) y se LIMPIA únicamente para
# enseñarlo: limpiar antes de comparar haría pasar `00\x0119` por `0019`.
limpio() { printf '%s' "$1" | tr -cd '[:alnum:]_.-' | cut -c1-64; }
for var in REPO_DIR ENV_FILE COMPOSE_FILE BACKUP_DIR DB_NAME DB_USER; do
    [[ -n "${!var:-}" ]] || die "Falta $var. Este script no usa valores por defecto de producción."
done
if (( PRODUCCION )); then
    [[ "$COPIA_TS" =~ ^[0-9]{8}_[0-9]{6}$ ]] || die "--copia no tiene el formato esperado."
    [[ -z "$DUMP" && -z "$MANIFEST" && -z "$ALEMBIC_ESPERADA" && (-z "$SHA_ESPERADO" || "$SHA_ESPERADO" == "HEAD") \
        && "$ASUMIR_PEDIDO" == "0" && "$PROYECTO_PEDIDO" == "0" && "$DRY_RUN" == "0" ]] || \
        die "Con --produccion no se aceptan opciones de ensayo (--dump/--manifest/--sha/--alembic-esperada/--proyecto-esperado/--yes/--dry-run)."
    DUMP="$BACKUP_DIR/backup_${COPIA_TS}.sql.gz"
    MANIFEST="$BACKUP_DIR/MANIFIESTO-backup_${COPIA_TS}.json"
    SHA_ESPERADO="HEAD"
    ASUMIR_SI=1
fi
[[ -n "$DUMP" ]] || die "Falta --dump."
[[ -n "$SHA_ESPERADO" ]] || die "Falta --sha (el commit que debe seguir puesto al terminar)."
[[ -d "$REPO_DIR" ]] || die "REPO_DIR no es un directorio."
[[ -f "$ENV_FILE" && -r "$ENV_FILE" ]] || die "ENV_FILE no existe o no se puede leer."
[[ -f "$COMPOSE_FILE" ]] || die "COMPOSE_FILE no existe."
CODIGO_DIE="copia_no_encontrada"
COMPROBACION="existencia_copia"
[[ -s "$DUMP" ]] || die "El dump no existe o está vacío: $(limpio "$(basename "${DUMP:-?}")")."

HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:18000/api/health}"
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-120}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"
[[ "$HEALTH_TIMEOUT" =~ ^[0-9]+$ ]] || die "HEALTH_TIMEOUT no es un número."
[[ "$HEALTH_INTERVAL" =~ ^[1-9][0-9]*$ ]] || die "HEALTH_INTERVAL debe ser un entero >= 1."

COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

# Único helper/umbral de espacio (#123b); no se duplica aquí.
# shellcheck source=scripts/_espacio.sh
source "${SCRIPT_DIR}/_espacio.sh"

# ── Árbol y commit ───────────────────────────────────────────────────────────
git -C "$REPO_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
    die "REPO_DIR no es un repo git utilizable."
HEAD_ANTES="$(git -C "$REPO_DIR" rev-parse HEAD)" || die "No puedo leer HEAD."
SHA_NORMALIZADA="$(git -C "$REPO_DIR" rev-parse --verify --quiet "${SHA_ESPERADO}^{commit}")" || \
    die "--sha no es un commit de este repo."
if (( PRODUCCION )); then
    SHA_NORMALIZADA="$HEAD_ANTES"
fi
if [[ "$HEAD_ANTES" != "$SHA_NORMALIZADA" ]]; then
    die "El HEAD actual no es el esperado. El código no se toca; no sigo."
fi
if ! git -C "$REPO_DIR" diff --quiet || ! git -C "$REPO_DIR" diff --cached --quiet; then
    die "El árbol de trabajo no está limpio. Guárdalo o descártalo antes de restaurar."
fi

# ── Proyecto Compose ─────────────────────────────────────────────────────────
if ! PROYECTO="$( "${COMPOSE[@]}" config --format json 2>/dev/null | jq -r '.name // empty' )"; then
    die "No pude renderizar docker compose config."
fi
[[ -n "$PROYECTO" ]] || die "docker compose config no declara un proyecto."
if (( PRODUCCION )); then
    PROYECTO_PRODUCCION_ESPERADO="zascarr"
    if [[ "${ZASCARR_PRUEBAS:-}" == "1" && -n "${PROYECTO_PRODUCCION:-}" ]]; then
        PROYECTO_PRODUCCION_ESPERADO="$PROYECTO_PRODUCCION"
    fi
    [[ "$PROYECTO" == "$PROYECTO_PRODUCCION_ESPERADO" ]] || \
        die "Con --produccion el proyecto debe ser '$PROYECTO_PRODUCCION_ESPERADO'."
else
    if [[ "$PROYECTO" == "zascarr" ]]; then
        die "El proyecto Compose es 'zascarr' (producción). Este script exige una copia aislada."
    fi
    if [[ "$PROYECTO" != "$PROYECTO_ESPERADO" ]]; then
        die "El proyecto Compose es '$PROYECTO'; se esperaba '$PROYECTO_ESPERADO'."
    fi
fi

# ── Manifiesto ───────────────────────────────────────────────────────────────
BASE="$(basename "$DUMP")"
STEM="${BASE%.sql.gz}"
if [[ -z "$MANIFEST" ]]; then
    MANIFEST="$(dirname "$DUMP")/MANIFIESTO-${STEM}.json"
fi
CODIGO_DIE="copia_no_encontrada"
COMPROBACION="manifiesto"
[[ -f "$MANIFEST" ]] || die "No encuentro el manifiesto: $(limpio "$(basename "$MANIFEST")")."
CODIGO_DIE="copia_no_valida"
COMPROBACION="manifiesto"
jq -e . "$MANIFEST" >/dev/null 2>&1 || die "El manifiesto no es JSON válido."

M_SHA="$(jq -r '.sha256 // empty' "$MANIFEST")"
M_BYTES="$(jq -r '.bytes // empty' "$MANIFEST")"
M_SCHEMA="$(jq -r '.schema // empty' "$MANIFEST" | tr -d '[:space:]')"
M_ALEMBIC="$(jq -r '.alembic // empty' "$MANIFEST" | tr -d '[:space:]')"
M_DESTINO="$(jq -r '.codigo_destino_sha_completo // empty' "$MANIFEST")"
M_DESPLEGADO="$(jq -r '.codigo_desplegado_sha_completo // empty' "$MANIFEST")"
# D-2: la copia puede no declarar versión (copias antiguas); `null` significa «no consta» y NUNCA se infiere.
M_VERSION="$(jq -c '.version_de_la_copia // empty' "$MANIFEST" 2>/dev/null || true)"
COPIA_VERSION_JSON="$(sanear_copia_version "$M_VERSION")"
[[ -n "$COPIA_VERSION_JSON" ]] || COPIA_VERSION_JSON="null"

if [[ -n "$M_SCHEMA" && "$M_SCHEMA" != "1" ]]; then
    CODIGO_DIE="copia_no_valida"
    COMPROBACION="manifiesto"
    die "El manifiesto declara schema '$(limpio "$M_SCHEMA")'; este script solo entiende el schema 1."
fi
if [[ -z "$M_SCHEMA" ]]; then
    warn "El manifiesto no declara schema; se asume el esquema 1."
fi

CODIGO_DIE="copia_no_valida"
COMPROBACION="manifiesto"
[[ -n "$M_SHA" ]] || die "El manifiesto no declara sha256."
CODIGO_DIE="copia_no_valida"
COMPROBACION="manifiesto"
[[ -n "$M_BYTES" && "$M_BYTES" =~ ^[0-9]+$ ]] || die "El manifiesto no declara bytes válidos."
SHA_REAL="$(sha256sum "$DUMP" | awk '{print $1}')"
BYTES_REAL="$(stat -c %s "$DUMP")"
CODIGO_DIE="copia_no_valida"
COMPROBACION="sha256_copia"
[[ "$SHA_REAL" == "$M_SHA" ]] || die "El SHA-256 del dump no coincide con el manifiesto."
CODIGO_DIE="copia_no_valida"
COMPROBACION="bytes_copia"
[[ "$BYTES_REAL" == "$M_BYTES" ]] || die "El tamaño del dump no coincide con el manifiesto."
if [[ -f "${DUMP}.sha256" ]]; then
    ( cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256" >/dev/null 2>&1 ) || {
        CODIGO_DIE="copia_no_valida"
        COMPROBACION="sha256_copia"
        die "El sidecar .sha256 no coincide con el dump."
    }
fi

if [[ -n "$M_ALEMBIC" && -n "$ALEMBIC_ESPERADA" && "$M_ALEMBIC" != "$ALEMBIC_ESPERADA" ]]; then
    CODIGO_DIE="revision_distinta"
    COMPROBACION="alembic_revision"
    die "El manifiesto declara Alembic '$(limpio "$M_ALEMBIC")'; se esperaba '$(limpio "$ALEMBIC_ESPERADA")'."
fi
if (( ! PRODUCCION )) && [[ "$M_DESTINO" != "$HEAD_ANTES" && "$M_DESPLEGADO" != "$HEAD_ANTES" ]]; then
    COMPROBACION="codigo_manifest"
    die "El manifiesto no acredita el commit actual. No restauro datos de otro código."
fi

# ── Inspección del dump (una pasada, sin escribir) ───────────────────────────
inspeccionar() {
    local sql="$1"
    gzip -dc "$sql" | awk '
        /PostgreSQL database dump/ { header=1 }
        /^COPY public\.alembic_version / { en_av=1; av=1; next }
        en_av && $0=="\\." { en_av=0; next }
        en_av { if (version=="") version=$0; next }
        /^COPY public\.series / { en_series=1; series=1; next }
        en_series && $0=="\\." { en_series=0; next }
        en_series { n_series++; next }
        /^COPY public\.issues / { en_issues=1; issues=1; next }
        en_issues && $0=="\\." { en_issues=0; next }
        en_issues { n_issues++; next }
        /^COPY public\.files / { en_files=1; files=1; next }
        en_files && $0=="\\." { en_files=0; next }
        en_files { n_files++; next }
        /^COPY public\.vinculacion_operaciones / { en_ops=1; ops=1; next }
        en_ops && $0=="\\." { en_ops=0; next }
        en_ops { n_ops++; next }
        /^COPY public\.wishlist / { en_wish=1; wish=1; next }
        en_wish && $0=="\\." { en_wish=0; next }
        en_wish { n_wish++; next }
        END {
            printf "%d|%d|%d|%d|%d|%d|%s|%d|%d|%d|%d|%d\n",
                   header, av, series, files, wish, issues, version,
                   n_series, n_issues, n_files, n_ops, n_wish
        }
    '
}

gzip -t "$DUMP" 2>/dev/null || {
    CODIGO_DIE="copia_no_valida"
    COMPROBACION="gzip_cabecera"
    die "gzip -t falla: el dump no es un gzip íntegro."
}
if ! INSPECCION="$(inspeccionar "$DUMP")"; then
    CODIGO_DIE="copia_no_valida"
    COMPROBACION="gzip_cabecera"
    die "No pude descomprimir o leer el dump."
fi
IFS='|' read -r T_HEADER T_AV T_SERIES T_FILES T_WISH T_ISSUES VERSION_DUMP \
    N_SERIES N_ISSUES N_FILES N_OPS N_WISH <<< "$INSPECCION"
VERSION_DUMP="$(printf '%s' "$VERSION_DUMP" | tr -d '[:space:]')"

[[ "$T_HEADER" == "1" ]] || { CODIGO_DIE="copia_no_valida"; COMPROBACION="cabecera_pg_dump"; die "El dump no tiene la cabecera de pg_dump."; }
# D-6/FR-17(d): `issues` también es obligatoria. Un dump sin ella puede pasar el SHA y el gzip y fallar DESPUÉS de
# createdb/carga (o completar con un catálogo incompleto); aquí se rechaza antes del primer evento de contenedor.
for par in "alembic_version:$T_AV" "series:$T_SERIES" "issues:$T_ISSUES" "files:$T_FILES" "wishlist:$T_WISH"; do
    [[ "${par#*:}" == "1" ]] || { CODIGO_DIE="copia_no_valida"; COMPROBACION="tablas_dump"; die "El dump no contiene la tabla ${par%%:*}."; }
done
[[ -n "$VERSION_DUMP" ]] || { CODIGO_DIE="copia_no_valida"; COMPROBACION="tablas_dump"; die "El dump no contiene version_num en alembic_version."; }

if [[ -n "$M_ALEMBIC" && "$M_ALEMBIC" != "$VERSION_DUMP" ]]; then
    CODIGO_DIE="revision_distinta"
    COMPROBACION="alembic_revision"
    die "El manifiesto declara Alembic '$(limpio "$M_ALEMBIC")' pero el dump trae '$(limpio "$VERSION_DUMP")'."
fi

COMPROBACION="alembic_revision"
ACTUAL="$( "${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -At \
    -c "select version_num from alembic_version" 2>/dev/null | tr -d '[:space:]' )" || \
    die "No pude leer la revisión de Alembic de la BD actual."
[[ -n "$ACTUAL" ]] || die "La BD actual no tiene revisión de Alembic."

if [[ -n "$ALEMBIC_ESPERADA" ]]; then
    ESPERADA="$ALEMBIC_ESPERADA"
elif [[ -n "$M_ALEMBIC" ]]; then
    ESPERADA="$M_ALEMBIC"
else
    ESPERADA="$ACTUAL"
fi
if [[ "$VERSION_DUMP" != "$ESPERADA" ]]; then
    CODIGO_DIE="revision_distinta"
    COMPROBACION="alembic_revision"
    die "Revisión incompatible: dump '$(limpio "$VERSION_DUMP")', esperada '$(limpio "$ESPERADA")'. No toco la BD."
fi
if [[ "$ACTUAL" != "$ESPERADA" ]]; then
    CODIGO_DIE="revision_distinta"
    COMPROBACION="alembic_revision"
    die "La BD actual está en '$(limpio "$ACTUAL")' y se esperaba '$(limpio "$ESPERADA")'. No toco la BD."
fi

# A partir de aquí ya no hay comprobaciones de contenido: lo que falle es una fase de la restauración y
# `comprobacion` vuelve a `null` (no se hereda el código de la última comprobación del preflight).
COMPROBACION=""

# ── BL-OPS2: restauración de producción (base nueva + cambio por renombrado) ──
# Orden aprobado (FR-19…FR-23): verificar → cargar en `<DB>_restaurando` CON la app sirviendo → comprobar →
# parar → releer la seguridad vigente → reaplicarla y releerla → copia previa (ya con la app parada) → cambiar
# por renombrado → arrancar y comprobar → borrar la previa. Cualquier fallo ANTES del renombrado deja la base
# viva intacta; cualquier fallo DESPUÉS deshace por renombrado, sin borrar antes de recuperar.
NUEVA_DB=""
PREVIA_DB=""
FALLIDA_DB=""
APP_PARADA=0
declare -A CONTEO_REST=()

inspeccionar_tablas() {
    gzip -dc "$1" | awk '
        /^COPY public\./ {
            tabla = $0
            sub(/^COPY public\./, "", tabla)
            sub(/ .*/, "", tabla)
            if (tabla ~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
                actual = tabla
                if (!(tabla in vistas)) { vistas[tabla] = 1; orden[++k] = tabla }
                dentro = 1
            } else {
                dentro = 0
            }
            next
        }
        dentro && $0 == "\\." { dentro = 0; actual = ""; next }
        dentro { n[actual]++ }
        END { for (i = 1; i <= k; i++) printf "%s|%d\n", orden[i], n[orden[i]] }
    '
}

# `< /dev/null`: esta función se usa dentro de un `while read` con sustitución de procesos; si `docker exec`
# heredara esa entrada, se comería las líneas que faltan (lo destapó la prueba con PostgreSQL real, F-18).
psql_en() { "${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$1" -At -c "$2" </dev/null; }
db_existe() { [[ "$(psql_en postgres "select 1 from pg_database where datname = '$1'" 2>/dev/null | tr -d '[:space:]')" == "1" ]]; }
crear_db() { "${COMPOSE[@]}" exec -T postgres createdb -U "$DB_USER" "$1" >/dev/null; }
borrar_db() { "${COMPOSE[@]}" exec -T postgres dropdb -U "$DB_USER" --if-exists --force "$1" >/dev/null 2>&1; }
parar_app() { "${COMPOSE[@]}" stop zascarr >/dev/null 2>&1; }
arrancar_app() { "${COMPOSE[@]}" up -d zascarr >/dev/null 2>&1; }

# `ALTER DATABASE … RENAME` con hasta 5 reintentos de 1 s («other users» conectados, R-5).
renombrar_db() {
    local desde="$1" hasta="$2" intento
    for intento in 1 2 3 4 5; do
        if psql_en postgres "ALTER DATABASE \"$desde\" RENAME TO \"$hasta\"" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

esperar_health() {
    local inicio intentos salud
    inicio="$(date +%s)"
    intentos=0
    while (( $(date +%s) - inicio < HEALTH_TIMEOUT )); do
        intentos=$((intentos + 1))
        if salud="$(curl -sf --max-time 2 "$HEALTH_URL" 2>/dev/null)" && \
           printf '%s' "$salud" | jq -e '.checks.database == "ok"' >/dev/null 2>&1; then
            HEALTH_JSON="$salud"
            return 0
        fi
        sleep "$HEALTH_INTERVAL"
    done
    return 1
}

leer_recuentos_previos() {
    # UATP-08 D-4: recuentos de la base viva ANTES del cambio, con la app aún sirviendo.
    local series issues files
    series="$(psql_en "$DB_NAME" "select count(*) from series" 2>/dev/null | tr -d '[:space:]')" || return 1
    issues="$(psql_en "$DB_NAME" "select count(*) from issues" 2>/dev/null | tr -d '[:space:]')" || return 1
    files="$(psql_en "$DB_NAME" "select count(*) from files" 2>/dev/null | tr -d '[:space:]')" || return 1
    [[ "$series" =~ ^[0-9]+$ && "$issues" =~ ^[0-9]+$ && "$files" =~ ^[0-9]+$ ]] || return 1
    RECUENTOS_PREVIOS_JSON="{\"series\":${series},\"issues\":${issues},\"files\":${files}}"
}

leer_version_arrancada() {
    # UATP-08 S-1: mismo esquema que `_version_copia` (head/build_sha/app_version/alembic).
    # `head` es el código que quedó puesto (HEAD_ANTES), la app viene del health y la revisión
    # es la restaurada; lo que no consta se declara null, nunca se omite la clave.
    if [[ -z "${HEALTH_JSON}" ]]; then
        VERSION_ARRANCADA_JSON="$(jq -cn --arg head "${HEAD_ANTES}" --arg alembic "${ESPERADA:-}" '
            {head: (if ($head | test("^[0-9a-f]{40}$")) then $head else null end),
             build_sha: null, app_version: null,
             alembic: (if ($alembic | test("^[0-9]{4}$")) then $alembic else null end)}' 2>/dev/null || printf 'null')"
        [[ -n "${VERSION_ARRANCADA_JSON}" ]] || VERSION_ARRANCADA_JSON="null"
        return 0
    fi
    VERSION_ARRANCADA_JSON="$(printf '%s' "${HEALTH_JSON}" | jq -c --arg head "${HEAD_ANTES}" \
        --arg alembic "${ESPERADA:-}" '
        {head: (if ($head | test("^[0-9a-f]{40}$")) then $head else null end),
         build_sha: (if (.build_sha | type) == "string" and (.build_sha | test("^[0-9a-f]{40}$")) then .build_sha else null end),
         app_version: (if (.version | type) == "string" and (.version | test("^[0-9]+\\.[0-9]+\\.[0-9]+$")) then .version else null end),
         alembic: (if ($alembic | test("^[0-9]{4}$")) then $alembic else null end)}
        | if ([.head, .build_sha, .app_version, .alembic] | map(select(. != null)) | length) > 0 then . else null end' \
        2>/dev/null || printf 'null')"
    [[ -n "${VERSION_ARRANCADA_JSON}" ]] || VERSION_ARRANCADA_JSON="null"
}

calcular_fuera() {
    # UATP-08 D-4: solo diferencias no negativas; si no se puede, null (no se inventa).
    [[ "${RECUENTOS_PREVIOS_JSON}" != "null" && -n "$1" ]] || { FUERA_JSON="null"; return 0; }
    FUERA_JSON="$(jq -cn --argjson p "${RECUENTOS_PREVIOS_JSON}" --argjson r "$1" '
        if ([($p.series - $r.series), ($p.issues - $r.issues), ($p.files - $r.files)] | all(. >= 0))
        then {series: ($p.series - $r.series), issues: ($p.issues - $r.issues), files: ($p.files - $r.files)}
        else null end' 2>/dev/null || printf 'null')"
    [[ -n "${FUERA_JSON}" ]] || FUERA_JSON="null"
}

leer_fila_seguridad() { # $1 base, $2 fichero destino
    "${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$1" -At \
        -c "select values::text from runtime_settings where id=1" >"$2" 2>/dev/null && [[ -s "$2" ]]
}

validar_fila_seguridad() { # $1 fichero JSON de la fila vigente (FR-18)
    jq -e '(.auth_mode == "password" or .auth_mode == "user_password")
            and (.auth_password_hash | type == "string" and length > 0)
            and (.secret_key | type == "string" and length > 0)
            and ((.auth_session_version // 0) | type == "number" and . >= 0)
            and (.base_url == null or (.base_url | type == "string"))
            and (.auth_username == null or (.auth_username | type == "string"))
            and ([(to_entries[] | select(.key | endswith("_enabled")) | .value | type)] | all(. == "boolean"))
            and (.fuentes_heredadas == null or (.fuentes_heredadas | type == "boolean"))' \
        "$1" >/dev/null 2>&1
}

# FR-34: lo vigente de seguridad y política gana; las integraciones y los marcadores vienen de la copia; las
# claves de seguridad ausentes en la vigente se ELIMINAN de la restaurada. La versión de sesión es max+1 y una
# versión de la copia ausente o no entera cuenta como 0.
combinar_seguridad() { # $1 vigente, $2 copia, $3 destino
    jq -c -n --slurpfile c "$1" --slurpfile r "$2" '
        def segura($k):
            ((["auth_mode", "auth_username", "auth_password_hash", "secret_key",
                "base_url", "fuentes_heredadas"] | index($k)) != null)
            or ($k | endswith("_enabled")) or ($k | startswith("webhook_"));
        def version($v):
            if (($v | type) == "number" and $v >= 0 and $v == ($v | floor)) then $v else 0 end;
        ($c[0] // {}) as $cur | ($r[0] // {}) as $rest |
        (($rest | with_entries(select(segura(.key) | not)))
         + ($cur | with_entries(select(segura(.key)))))
        | .auth_session_version = (([version($cur.auth_session_version), version($rest.auth_session_version)] | max) + 1)
    ' >"$3" 2>/dev/null
}

# Reaplica la fila con una sola sentencia atómica, por la entrada estándar de `psql`, sin interpolar valores en
# SQL (etiqueta de dólar aleatoria comprobada ausente del contenido), y la relee canónicamente.
aplicar_seguridad() { # $1 base, $2 fila final
    local etiqueta="$1"
    if grep -Fq "$etiqueta" "$2"; then
        return 1
    fi
    if ! {
        printf 'INSERT INTO runtime_settings (id, "values") VALUES (1, $%s$' "$etiqueta"
        cat "$2"
        printf '$%s$::jsonb) ON CONFLICT (id) DO UPDATE SET "values" = EXCLUDED."values";\n' "$etiqueta"
    } | "${COMPOSE[@]}" exec -T postgres psql -q -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$NUEVA_DB" >>"$LOG" 2>&1; then
        return 1
    fi
    leer_fila_seguridad "$NUEVA_DB" "${2}.db" || return 1
    jq -S . "$2" >"${2}.esperado" 2>/dev/null || return 1
    jq -S . "${2}.db" >"${2}.obtenido" 2>/dev/null || return 1
    cmp -s "${2}.esperado" "${2}.obtenido" || return 1
    return 0
}

# Comprobaciones de la base nueva: revisión de Alembic, recuentos GENÉRICOS de cada bloque `COPY` del dump
# (AC-51: también las tablas de las migraciones 0030/0031 y las que vengan) y vínculos huérfanos.
verificar_base_nueva() {
    local revision tabla esperado obtenido huerfanos
    revision="$(psql_en "$NUEVA_DB" "select version_num from alembic_version" 2>/dev/null | tr -d '[:space:]')" || return 1
    [[ "$revision" == "$ESPERADA" ]] || return 1
    while IFS='|' read -r tabla esperado; do
        [[ -n "$tabla" ]] || continue
        [[ "$tabla" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || return 1
        obtenido="$(psql_en "$NUEVA_DB" "select count(*) from \"$tabla\"" 2>/dev/null | tr -d '[:space:]')" || return 1
        [[ "$obtenido" =~ ^[0-9]+$ ]] || return 1
        if [[ "$obtenido" != "$esperado" ]]; then
            warn "Recuento distinto en $tabla: dump=$esperado restaurada=$obtenido."
            return 1
        fi
        CONTEO_REST["$tabla"]="$obtenido"
    done < <(inspeccionar_tablas "$DUMP")
    huerfanos="$(psql_en "$NUEVA_DB" \
        "select (select count(*) from files f left join issues i on i.id=f.issue_id where f.issue_id is not null and i.id is null)||'|'||(select count(*) from issues i left join series s on s.id=i.series_id where s.id is null)||'|'||(select count(*) from wishlist w left join series s on s.id=w.series_id left join issues i on i.id=w.issue_id where (w.series_id is not null and s.id is null) or (w.issue_id is not null and i.id is null))||'|'||(select count(*) from vinculacion_operaciones o left join series s on s.id=o.series_id where s.id is null);" \
        2>/dev/null | tr -d '[:space:]')" || return 1
    IFS='|' read -r H_FILES H_ISSUES H_WISH H_OPS <<< "$huerfanos"
    [[ "$H_FILES" == "0" && "$H_ISSUES" == "0" && "$H_WISH" == "0" && "$H_OPS" == "0" ]] || return 1
    return 0
}

# Fallo con la base viva INTACTA (antes del renombrado): retira la base nueva, vuelve a arrancar la app si se
# había parado y deja `base_en_su_sitio:true` (FR-19…FR-21, AC-31).
fallo_pre() { # $1 código de §9.2
    FASE_STATUS="${2:-$FASE_STATUS}"
    estado_restaurar "$FASE_STATUS" "fallida" "$1" "true"
    if (( APP_PARADA )); then
        arrancar_app || warn "No pude volver a arrancar ZascArr; arranca con: docker compose up -d zascarr"
    fi
    if [[ -n "$NUEVA_DB" ]]; then
        borrar_db "$NUEVA_DB" || warn "No pude retirar ${NUEVA_DB}; la siguiente restauración se negará hasta retirarla."
    fi
    printf 'ERROR: la restauración no se completó (%s). La base de datos no se ha cambiado.\n' "$1" >&2
    exit 1
}

# Vuelta atrás por renombrado (FR-23): la restaurada pasa a `_fallida`, la previa vuelve a ser la viva y SOLO se
# borra la fallida si la app arranca y responde. Si no se puede volver, `recuperacion_fallida` únicamente si hay
# copia previa y los datos están en `_previa`/`_fallida`; si no, `unexpected`.
deshacer_arranque() {
    local fallo=0 motivo="unexpected"
    parar_app || true
    if ! renombrar_db "$DB_NAME" "$FALLIDA_DB"; then fallo=1; fi
    if (( ! fallo )); then
        if ! renombrar_db "$PREVIA_DB" "$DB_NAME"; then fallo=1; fi
    fi
    if (( ! fallo )); then
        arrancar_app || true
        if esperar_health; then
            borrar_db "$FALLIDA_DB" || warn "No pude borrar ${FALLIDA_DB}; la siguiente restauración se negará hasta retirarla."
            estado_restaurar "cambiando" "fallida" "arranque_fallido" "true"
            printf 'ERROR: la restauración no salió bien; ZascArr vuelve a los datos de antes.\n' >&2
            exit 1
        fi
        fallo=2
    fi
    if [[ -s "$SEGURIDAD" ]] && { db_existe "$PREVIA_DB" || db_existe "$FALLIDA_DB"; }; then
        motivo="recuperacion_fallida"
    fi
    estado_restaurar "cambiando" "fallida" "$motivo" "false"
    if [[ "$motivo" == "recuperacion_fallida" ]]; then
        printf 'ERROR: ZascArr no pudo volver atrás solo. Los datos de antes están en la copia previa; avisa a quien instaló ZascArr.\n' >&2
    else
        printf 'ERROR: no se sabe por qué falló la restauración ni pude comprobar una vuelta atrás.\n' >&2
    fi
    exit 1
}

ejecutar_produccion() {
    local modo timestamp_bd
    NUEVA_DB="${DB_NAME}_restaurando"
    PREVIA_DB="${DB_NAME}_previa"
    FALLIDA_DB="${DB_NAME}_fallida"
    [[ "$DB_NAME" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "DB_NAME no es un identificador de base de datos válido."
    FASE_STATUS="verificando"
    estado_restaurar "verificando" "en_curso" "" "true"

    mkdir -p "$BACKUP_DIR" || die "No puedo crear BACKUP_DIR."
    [[ -w "$BACKUP_DIR" ]] || die "BACKUP_DIR no es escribible."
    timestamp_bd="$(date +%Y%m%d_%H%M%S)"
    SEGURIDAD="$BACKUP_DIR/rollback-safety_${timestamp_bd}.sql.gz"
    LOG="$BACKUP_DIR/datos_${timestamp_bd}.log"
    if : >"$LOG" 2>/dev/null; then chmod 600 "$LOG" 2>/dev/null || true; else LOG=/dev/null; fi
    FILA_SEGURIDAD=""
    FILA_RESTAURADA=""
    FILA_FINAL=""
    limpiar_temporales() {
        rm -f "${FILA_SEGURIDAD:-}" "${FILA_RESTAURADA:-}" "${FILA_FINAL:-}" \
            "${FILA_FINAL:-}.db" "${FILA_FINAL:-}.esperado" "${FILA_FINAL:-}.obtenido" 2>/dev/null || true
    }
    trap limpiar_temporales EXIT INT TERM

    # (1) Precondición de seguridad ANTES de tocar nada (FR-18): leer la fila viva y validar tipos.
    FILA_SEGURIDAD="$(mktemp "${BACKUP_DIR}/seguridad.XXXXXX")" || die "No pude preparar la configuración vigente."
    chmod 600 "$FILA_SEGURIDAD"
    leer_fila_seguridad "$DB_NAME" "$FILA_SEGURIDAD" || {
        CODIGO_DIE="seguridad_ilegible"
        die "No pude leer la configuración vigente. No se ha tocado la BD."
    }
    if ! validar_fila_seguridad "$FILA_SEGURIDAD"; then
        modo="$(jq -r '.auth_mode // empty' "$FILA_SEGURIDAD" 2>/dev/null)"
        if [[ "$modo" != "password" && "$modo" != "user_password" ]]; then
            CODIGO_DIE="autenticacion_no_activada"
            die "La seguridad vigente no está activada o está incompleta. No se ha tocado la BD."
        fi
        CODIGO_DIE="seguridad_ilegible"
        die "La seguridad vigente no está activada o está incompleta. No se ha tocado la BD."
    fi

    # (UATP-08) Recuentos de la base viva antes del cambio; best-effort, nunca falla la restauración.
    leer_recuentos_previos || RECUENTOS_PREVIOS_JSON="null"

    # (2) Restos de una restauración anterior y base nueva huérfana (FR-19.2). Nunca se borran solas las previas.
    FASE_STATUS="preparando"
    estado_restaurar "preparando" "en_curso" "" "true"
    if db_existe "$PREVIA_DB" || db_existe "$FALLIDA_DB"; then
        CODIGO_DIE="precondition_failed"
        die "Hay una restauración anterior sin cerrar (${PREVIA_DB} o ${FALLIDA_DB}). No se ha tocado nada."
    fi
    if db_existe "$NUEVA_DB"; then
        borrar_db "$NUEVA_DB" || { CODIGO_DIE="precondition_failed"; die "No pude retirar una base de restauración anterior."; }
    fi

    # (3) Espacio: la copia previa y el volumen de PostgreSQL (NFR-04).
    TAMANO_KB="$(tamano_bd_kb)"
    if ! exigir_espacio_kb "$(espacio_libre_kb "$BACKUP_DIR")" "${TAMANO_KB}" "la copia de seguridad previa a restaurar"; then
        CODIGO_DIE="sin_espacio"
        die "No hay espacio para la copia de seguridad. No se ha tocado la BD."
    fi
    TAMANO_DUMP_KB="$(tamano_descomprimido_kb "$DUMP")"
    if ! exigir_espacio_kb "$(espacio_postgres_libre_kb)" "${TAMANO_DUMP_KB}" "restaurar la base de datos"; then
        CODIGO_DIE="sin_espacio"
        die "No hay espacio en el volumen de PostgreSQL para restaurar. No se ha tocado la BD."
    fi

    # (4) Cargar la copia en la base NUEVA con la app todavía sirviendo (FR-19.3).
    FASE_STATUS="restaurando"
    estado_restaurar "restaurando" "en_curso" "" "true"
    crear_db "$NUEVA_DB" || { CODIGO_DIE="precondition_failed"; die "No pude crear la base de restauración. No se ha tocado la BD."; }
    if ! gzip -dc "$DUMP" | "${COMPOSE[@]}" exec -T postgres psql -q -v ON_ERROR_STOP=1 \
            -U "$DB_USER" -d "$NUEVA_DB" >>"$LOG" 2>&1; then
        fallo_pre "restauracion_fallida"
    fi

    # (5) Comprobar la base nueva (revisión, recuentos genéricos y huérfanos) ANTES de parar nada (FR-19.4).
    FASE_STATUS="comprobando"
    estado_restaurar "comprobando" "en_curso" "" "true"
    verificar_base_nueva || fallo_pre "verificacion_fallida"

    # (6) Parada breve y, YA SIN CONCURRENCIA, relectura de la fila de seguridad vigente (FR-20.5/6).
    FASE_STATUS="parando"
    estado_restaurar "parando" "en_curso" "" "true"
    APP_PARADA=1
    parar_app || { APP_PARADA=0; fallo_pre "unexpected"; }
    FASE_STATUS="seguridad"
    estado_restaurar "seguridad" "en_curso" "" "true"
    leer_fila_seguridad "$DB_NAME" "$FILA_SEGURIDAD" || fallo_pre "seguridad_ilegible"
    validar_fila_seguridad "$FILA_SEGURIDAD" || fallo_pre "seguridad_ilegible"
    FILA_RESTAURADA="${FILA_SEGURIDAD}.restaurada"
    leer_fila_seguridad "$NUEVA_DB" "$FILA_RESTAURADA" || fallo_pre "seguridad_ilegible"
    FILA_FINAL="${FILA_SEGURIDAD}.final"
    combinar_seguridad "$FILA_SEGURIDAD" "$FILA_RESTAURADA" "$FILA_FINAL" || fallo_pre "seguridad_ilegible"
    aplicar_seguridad "zascarr_$(date +%s)_$$" "$FILA_FINAL" || fallo_pre "seguridad_no_aplicada"

    # (7) Copia previa verificada, con la app parada (FR-21; F-04).
    FASE_STATUS="copia_previa"
    estado_restaurar "copia_previa" "en_curso" "" "true"
    ( umask 077; : >"${SEGURIDAD}.tmp" ) || fallo_pre "copia_previa_fallida"
    if ! "${COMPOSE[@]}" exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip >"${SEGURIDAD}.tmp"; then
        rm -f "${SEGURIDAD}.tmp"
        fallo_pre "copia_previa_fallida"
    fi
    if ! gzip -t "${SEGURIDAD}.tmp"; then
        rm -f "${SEGURIDAD}.tmp"
        fallo_pre "copia_previa_fallida"
    fi
    mv "${SEGURIDAD}.tmp" "$SEGURIDAD" || fallo_pre "copia_previa_fallida"
    chmod 600 "$SEGURIDAD" 2>/dev/null || true
    if ! SAFE="$(inspeccionar "$SEGURIDAD")"; then
        rm -f "$SEGURIDAD"
        fallo_pre "copia_previa_fallida"
    fi
    IFS='|' read -r S_HEADER S_AV S_SERIES S_FILES S_WISH _S_ISSUES _S_VERSION \
        _SN_SERIES _SN_ISSUES _SN_FILES _SN_OPS _SN_WISH <<< "$SAFE"
    if [[ "$S_HEADER" != "1" || "$S_AV" != "1" || "$S_SERIES" != "1" || "$S_FILES" != "1" || "$S_WISH" != "1" ]]; then
        rm -f "$SEGURIDAD"
        fallo_pre "copia_previa_fallida"
    fi

    # (8) Cambio por renombrado (FR-22): la viva pasa a `_previa` y la nueva ocupa su sitio.
    FASE_STATUS="cambiando"
    estado_restaurar "cambiando" "en_curso" "" "true"
    if ! renombrar_db "$DB_NAME" "$PREVIA_DB"; then
        fallo_pre "cambio_fallido"
    fi
    if ! renombrar_db "$NUEVA_DB" "$DB_NAME"; then
        if renombrar_db "$PREVIA_DB" "$DB_NAME"; then
            arrancar_app || warn "No pude volver a arrancar ZascArr; arranca con: docker compose up -d zascarr"
            borrar_db "$NUEVA_DB" || warn "No pude retirar ${NUEVA_DB}; la siguiente restauración se negará hasta retirarla."
            estado_restaurar "cambiando" "fallida" "cambio_fallido" "true"
            printf 'ERROR: la restauración no salió bien; ZascArr vuelve a los datos de antes.\n' >&2
            exit 1
        fi
        deshacer_arranque
    fi
    NUEVA_DB=""

    # (9) Arrancar, comprobar el health y, solo entonces, borrar la previa (FR-23).
    FASE_STATUS="arrancando"
    estado_restaurar "arrancando" "en_curso" "" "true"
    if ! arrancar_app; then
        deshacer_arranque
    fi
    if ! esperar_health; then
        deshacer_arranque
    fi
    # (9 bis) FR-17(d): el código NO puede haber cambiado durante la restauración. Se relee HEAD y el árbol
    # al final, ya con la base nueva en su sitio y respondiendo; si algo cambió, se falla cerrado: no se
    # declara la restauración terminada ni se borra la previa (sigue disponible para recuperar).
    HEAD_DESPUES_FINAL="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || true)"
    if [[ "${HEAD_DESPUES_FINAL}" != "${HEAD_ANTES}" ]] \
        || ! git -C "$REPO_DIR" diff --quiet 2>/dev/null \
        || ! git -C "$REPO_DIR" diff --cached --quiet 2>/dev/null; then
        CODIGO_DIE="unexpected"
        die "El código cambió durante la restauración, así que no se declara terminada. La base restaurada sigue en su sitio y la previa se conserva."
    fi
    borrar_db "$PREVIA_DB" || warn "No pude borrar ${PREVIA_DB}; la siguiente restauración se negará hasta retirarla."
    limpiar_temporales
    RECUENTOS_REST_JSON="{\"series\":${CONTEO_REST[series]:-0},\"issues\":${CONTEO_REST[issues]:-0},\"files\":${CONTEO_REST[files]:-0}}"
    leer_version_arrancada
    calcular_fuera "${RECUENTOS_REST_JSON}"
    COMPROBACIONES_JSON='[{"codigo":"existencia_copia","estado":"ok"},{"codigo":"manifiesto","estado":"ok"},{"codigo":"sha256_copia","estado":"ok"},{"codigo":"bytes_copia","estado":"ok"},{"codigo":"codigo_manifest","estado":"no_ejecutada"},{"codigo":"gzip_cabecera","estado":"ok"},{"codigo":"cabecera_pg_dump","estado":"ok"},{"codigo":"tablas_dump","estado":"ok"},{"codigo":"alembic_revision","estado":"ok"},{"codigo":"recuentos_nueva","estado":"ok"},{"codigo":"vinculos_huerfanos","estado":"ok"},{"codigo":"seguridad_conservada","estado":"ok"},{"codigo":"copia_previa","estado":"ok"},{"codigo":"health","estado":"ok"}]'
    estado_restaurar "arrancando" "hecha" "" "true" \
        "${RECUENTOS_REST_JSON}"
    ok "Copia restaurada. La base de datos de antes se guardó como $(basename "$SEGURIDAD")."
    printf '  Recuentos:         series=%s issues=%s files=%s\n' \
        "${CONTEO_REST[series]:-0}" "${CONTEO_REST[issues]:-0}" "${CONTEO_REST[files]:-0}"
    return 0
}


# ── Plan / dry-run ──────────────────────────────────────────────────────────
printf '\nDatos a restaurar (sin cambiar el código):\n'
printf '  HEAD:              %s\n' "${HEAD_ANTES:0:12}…"
printf '  Proyecto:          %s\n' "$PROYECTO"
printf '  Dump:              %s\n' "$(limpio "$BASE")"
printf '  Manifiesto:        %s\n' "$(limpio "$(basename "$MANIFEST")")"
printf '  SHA-256:           %s…\n' "${SHA_REAL:0:12}"
printf '  Alembic esperado:  %s\n' "$(limpio "$ESPERADA")"
printf '  Recuentos dump:    series=%s issues=%s files=%s operaciones=%s wishlist=%s\n' \
    "$N_SERIES" "$N_ISSUES" "$N_FILES" "$N_OPS" "$N_WISH"

if (( DRY_RUN )); then
    ok "Dry-run: no se ha parado la app, no se ha tocado la BD y no se ha escrito nada."
    exit 0
fi

if (( ASUMIR_SI == 0 )); then
    printf '\nEscribe SI para restaurar SOLO los datos (el código no cambia): ' >&2
    read -r RESPUESTA || die "No pude leer la confirmación."
    [[ "$RESPUESTA" == "SI" ]] || die "Cancelado. No se ha tocado nada."
fi

# ── BL-OPS2: el modo de producción tiene su propio flujo (base nueva + renombrado) ──────────────────
if (( PRODUCCION )); then
    ejecutar_produccion
    exit 0
fi

# ── Copia de seguridad previa ────────────────────────────────────────────────
DB_TOCADA=0
TS="$(date +%Y%m%d_%H%M%S)"
SEGURIDAD="$BACKUP_DIR/rollback-safety_${TS}.sql.gz"
LOG="$BACKUP_DIR/datos_${TS}.log"
FASE="preparación"

mkdir -p "$BACKUP_DIR" || die "No puedo crear BACKUP_DIR."
[[ -w "$BACKUP_DIR" ]] || die "BACKUP_DIR no es escribible."

TAMANO_KB="$(tamano_bd_kb)"
exigir_espacio_kb "$(espacio_libre_kb "$BACKUP_DIR")" "${TAMANO_KB}" \
        "la copia de seguridad previa a restaurar" && ESPACIO_RC=0 || ESPACIO_RC=$?
if (( ESPACIO_RC == 2 )); then
    die "No pude medir el espacio (la base de datos actual o el disco de copias), así que no puedo asegurar la copia previa. No se ha tocado la BD."
elif (( ESPACIO_RC != 0 )); then
    die "No hay espacio para la copia de seguridad. No se ha tocado la BD."
fi
TAMANO_DUMP_KB="$(tamano_descomprimido_kb "$DUMP")"
exigir_espacio_kb "$(espacio_postgres_libre_kb)" "${TAMANO_DUMP_KB}" \
        "restaurar la base de datos" && ESPACIO_RC=0 || ESPACIO_RC=$?
if (( ESPACIO_RC == 2 )); then
    die "No pude medir el tamaño del dump ni el espacio del volumen de PostgreSQL. No se ha tocado la BD."
elif (( ESPACIO_RC != 0 )); then
    die "No hay espacio en el volumen de PostgreSQL para restaurar. No se ha tocado la BD."
fi

info "Copia de seguridad de la BD actual..."
# El temporal nace 600: con umask 022 sería legible por todos durante TODO el pg_dump.
( umask 077; : > "${SEGURIDAD}.tmp" ) || die "No pude crear la copia de seguridad. No se ha tocado la BD."
if ! "${COMPOSE[@]}" exec -T postgres pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "${SEGURIDAD}.tmp"; then
    rm -f "${SEGURIDAD}.tmp"
    die "No pude crear la copia de seguridad. No se ha tocado la BD."
fi
if ! gzip -t "${SEGURIDAD}.tmp"; then
    rm -f "${SEGURIDAD}.tmp"
    die "La copia de seguridad no pasa gzip -t. No se ha tocado la BD."
fi
mv "${SEGURIDAD}.tmp" "$SEGURIDAD"
chmod 600 "$SEGURIDAD"
if ! SAFE="$(inspeccionar "$SEGURIDAD")"; then
    rm -f "$SEGURIDAD"
    die "La copia de seguridad no se pudo inspeccionar. No se ha tocado la BD."
fi
IFS='|' read -r S_HEADER S_AV S_SERIES S_FILES S_WISH _S_ISSUES _S_VERSION \
    _SN_SERIES _SN_ISSUES _SN_FILES _SN_OPS _SN_WISH <<< "$SAFE"
if [[ "$S_HEADER" != "1" || "$S_AV" != "1" || "$S_SERIES" != "1" || "$S_FILES" != "1" || "$S_WISH" != "1" ]]; then
    rm -f "$SEGURIDAD"
    die "La copia de seguridad no parece una BD de ZascArr. No se ha tocado la BD."
fi
ok "Copia previa verificada: $(basename "$SEGURIDAD")."

if ! : > "$LOG" 2>/dev/null; then
    LOG=/dev/null
    warn "No puedo escribir el detalle de la restauración."
else
    chmod 600 "$LOG" 2>/dev/null || true
fi

# ── Recuperación best-effort ─────────────────────────────────────────────────
recuperar() {
    local motivo="$1"
    trap - INT TERM
    printf 'ERROR: %s\n' "$motivo" >&2
    if (( DB_TOCADA )); then
        printf 'Intentando recuperar la BD anterior desde %s...\n' "$(basename "$SEGURIDAD")" >&2
        "${COMPOSE[@]}" stop zascarr >/dev/null 2>&1 || true
        "${COMPOSE[@]}" exec -T postgres dropdb -U "$DB_USER" --if-exists --force "$DB_NAME" \
            >/dev/null 2>&1 || true
        "${COMPOSE[@]}" exec -T postgres createdb -U "$DB_USER" "$DB_NAME" \
            >/dev/null 2>&1 || true
        if gzip -dc "$SEGURIDAD" | "${COMPOSE[@]}" exec -T postgres psql -q \
                -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" >>"$LOG" 2>&1; then
            printf 'BD anterior restaurada. La app sigue parada.\n' >&2
        else
            printf 'No se pudo recuperar automáticamente la BD anterior.\n' >&2
        fi
    fi
    printf 'Orden de recuperación:\n' >&2
    printf '  gunzip -c "$BACKUP_DIR/%s" | docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres psql -q -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME"\n' \
        "$(basename "$SEGURIDAD")" >&2
    printf '  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d zascarr\n' >&2
    exit 1
}
interrumpido() { recuperar "interrumpido durante ${FASE}"; }
trap interrumpido INT TERM

# ── Parar, destruir y restaurar ──────────────────────────────────────────────
FASE="parada de la app"
info "Parando la app..."
if ! "${COMPOSE[@]}" stop zascarr >/dev/null; then
    recuperar "no pude parar la app; la BD no se ha tocado"
fi

FASE="dropdb"
info "Eliminando la base de datos..."
# Se marca ANTES: una interrupción durante el dropdb ya puede haber dejado la BD a medias, y la recuperación solo se
# intenta con la BD marcada como tocada. Si el dropdb falla de verdad, recuperar restaura la copia previa (inocuo).
DB_TOCADA=1
if ! "${COMPOSE[@]}" exec -T postgres dropdb -U "$DB_USER" --if-exists --force "$DB_NAME" >/dev/null; then
    recuperar "el dropdb falló: la BD debería seguir como estaba; se intenta dejarla como estaba"
fi

FASE="createdb"
info "Creando base de datos vacía..."
if ! "${COMPOSE[@]}" exec -T postgres createdb -U "$DB_USER" "$DB_NAME" >/dev/null; then
    recuperar "no pude crear la base de datos vacía"
fi

FASE="restauración"
info "Restaurando datos..."
if ! gzip -dc "$DUMP" | "${COMPOSE[@]}" exec -T postgres psql -q -v ON_ERROR_STOP=1 \
        -U "$DB_USER" -d "$DB_NAME" >>"$LOG" 2>&1; then
    recuperar "la restauración del dump falló"
fi

# ── Verificación ─────────────────────────────────────────────────────────────
FASE="verificación"
REV_REST="$( "${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -At \
    -c "select version_num from alembic_version" 2>/dev/null | tr -d '[:space:]' )" || \
    recuperar "no pude leer la revisión restaurada"
if [[ "$REV_REST" != "$ESPERADA" ]]; then
    recuperar "la revisión restaurada es '$(limpio "$REV_REST")' y se esperaba '$(limpio "$ESPERADA")'"
fi

RECUENTOS="$( "${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -At -c \
    "select (select count(*) from series)||'|'||(select count(*) from issues)||'|'||(select count(*) from files)||'|'||(select count(*) from vinculacion_operaciones)||'|'||(select count(*) from wishlist);" \
    2>/dev/null | tr -d '[:space:]' )" || recuperar "no pude contar las tablas restauradas"
IFS='|' read -r R_SERIES R_ISSUES R_FILES R_OPS R_WISH <<< "$RECUENTOS"
for par in \
    "series:$N_SERIES:$R_SERIES" "issues:$N_ISSUES:$R_ISSUES" \
    "files:$N_FILES:$R_FILES" "operaciones:$N_OPS:$R_OPS" "wishlist:$N_WISH:$R_WISH"; do
    tabla="${par%%:*}"; resto="${par#*:}"; esperado="${resto%%:*}"; obtenido="${resto#*:}"
    if [[ "$esperado" != "$obtenido" ]]; then
        recuperar "recuento distinto en $tabla: dump=$esperado restaurada=$obtenido"
    fi
done

HUERFANOS="$( "${COMPOSE[@]}" exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" -At -c \
    "select (select count(*) from files f left join issues i on i.id=f.issue_id where f.issue_id is not null and i.id is null)||'|'||(select count(*) from issues i left join series s on s.id=i.series_id where s.id is null)||'|'||(select count(*) from wishlist w left join series s on s.id=w.series_id left join issues i on i.id=w.issue_id where (w.series_id is not null and s.id is null) or (w.issue_id is not null and i.id is null))||'|'||(select count(*) from vinculacion_operaciones o left join series s on s.id=o.series_id where s.id is null);" \
    2>/dev/null | tr -d '[:space:]' )" || recuperar "no pude comprobar los vínculos"
IFS='|' read -r H_FILES H_ISSUES H_WISH H_OPS <<< "$HUERFANOS"
if [[ "$H_FILES" != "0" || "$H_ISSUES" != "0" || "$H_WISH" != "0" || "$H_OPS" != "0" ]]; then
    recuperar "vínculos huérfanos: files=$H_FILES issues=$H_ISSUES wishlist=$H_WISH operaciones=$H_OPS"
fi

FASE="arranque"
info "Arrancando la app (sin rebuild)..."
if ! "${COMPOSE[@]}" up -d zascarr >/dev/null; then
    recuperar "no pude arrancar la app"
fi
HEALTH_INICIO="$(date +%s)"
HEALTH_INTENTOS=0
HEALTH_OK=0
while (( $(date +%s) - HEALTH_INICIO < HEALTH_TIMEOUT )); do
    HEALTH_INTENTOS=$((HEALTH_INTENTOS + 1))
    if HEALTH="$(curl -sf --max-time 2 "$HEALTH_URL" 2>/dev/null)" && \
       printf '%s' "$HEALTH" | jq -e '.checks.database == "ok"' >/dev/null 2>&1; then
        HEALTH_OK=1
        break
    fi
    sleep "$HEALTH_INTERVAL"
done
if (( HEALTH_OK == 0 )); then
    recuperar "la app no responde con health 200 y database=ok en ${HEALTH_TIMEOUT}s (${HEALTH_INTENTOS} intentos)"
fi

HEAD_DESPUES="$(git -C "$REPO_DIR" rev-parse HEAD)" || recuperar "no pude releer HEAD"
if [[ "$HEAD_DESPUES" != "$HEAD_ANTES" ]]; then
    recuperar "el HEAD cambió durante la restauración"
fi
if ! git -C "$REPO_DIR" diff --quiet || ! git -C "$REPO_DIR" diff --cached --quiet; then
    recuperar "el árbol de trabajo cambió durante la restauración"
fi

trap - INT TERM
ok "Datos restaurados sin cambiar el código."
printf '  HEAD:              %s…\n' "${HEAD_ANTES:0:12}"
printf '  Dump:              %s\n' "$(limpio "$BASE")"
printf '  Copia previa:      %s\n' "$(basename "$SEGURIDAD")"
printf '  Alembic:           %s\n' "$(limpio "$REV_REST")"
printf '  Recuentos:         series=%s issues=%s files=%s operaciones=%s wishlist=%s\n' \
    "$R_SERIES" "$R_ISSUES" "$R_FILES" "$R_OPS" "$R_WISH"
printf '  Vínculos huérfanos: 0\n'
printf '  Health:            %s (%s intentos)\n' "$HEALTH_URL" "$HEALTH_INTENTOS"
printf '  Detalle:           %s\n' "$(basename "$LOG")"