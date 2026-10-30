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
#   - gzip, cabecera de pg_dump y las cuatro tablas que exige el rollback;
#   - revisión Alembic del dump y de la BD actual contra --alembic-esperada.
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

die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '→ %s\n' "$*"; }
ok()   { printf '✓ %s\n' "$*"; }
warn() { printf '⚠ %s\n' "$*" >&2; }

uso() {
    sed -n '3,32p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dump)              [[ -n "${2:-}" ]] || die "--dump necesita un valor"; DUMP="$2"; shift 2 ;;
        --manifest)          [[ -n "${2:-}" ]] || die "--manifest necesita un valor"; MANIFEST="$2"; shift 2 ;;
        --sha)               [[ -n "${2:-}" ]] || die "--sha necesita un valor"; SHA_ESPERADO="$2"; shift 2 ;;
        --alembic-esperada)  [[ -n "${2:-}" ]] || die "--alembic-esperada necesita un valor"; ALEMBIC_ESPERADA="$2"; shift 2 ;;
        --proyecto-esperado) [[ -n "${2:-}" ]] || die "--proyecto-esperado necesita un valor"; PROYECTO_ESPERADO="$2"; shift 2 ;;
        --yes|-y)            ASUMIR_SI=1; shift ;;
        --dry-run)           DRY_RUN=1; shift ;;
        --forzar)            die "--forzar está prohibido: este script no cambia el código ni descarta cambios." ;;
        -h|--help)           uso; exit 0 ;;
        -*)                  die "Opción desconocida: $1" ;;
        *)                   die "Argumento inesperado: $1" ;;
    esac
done

[[ -n "$DUMP" ]] || die "Falta --dump."
[[ -n "$SHA_ESPERADO" ]] || die "Falta --sha (el commit que debe seguir puesto al terminar)."
for cmd in docker git jq gzip gunzip sha256sum stat curl awk; do
    command -v "$cmd" >/dev/null 2>&1 || die "No encuentro $cmd."
done

for var in REPO_DIR ENV_FILE COMPOSE_FILE BACKUP_DIR DB_NAME DB_USER; do
    [[ -n "${!var:-}" ]] || die "Falta $var. Este script no usa valores por defecto de producción."
done
[[ -d "$REPO_DIR" ]] || die "REPO_DIR no es un directorio."
[[ -f "$ENV_FILE" && -r "$ENV_FILE" ]] || die "ENV_FILE no existe o no se puede leer."
[[ -f "$COMPOSE_FILE" ]] || die "COMPOSE_FILE no existe."
[[ -s "$DUMP" ]] || die "El dump no existe o está vacío: $(basename "${DUMP:-?}")."

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
if [[ "$PROYECTO" == "zascarr" ]]; then
    die "El proyecto Compose es 'zascarr' (producción). Este script exige una copia aislada."
fi
if [[ "$PROYECTO" != "$PROYECTO_ESPERADO" ]]; then
    die "El proyecto Compose es '$PROYECTO'; se esperaba '$PROYECTO_ESPERADO'."
fi

# ── Manifiesto ───────────────────────────────────────────────────────────────
BASE="$(basename "$DUMP")"
STEM="${BASE%.sql.gz}"
if [[ -z "$MANIFEST" ]]; then
    MANIFEST="$(dirname "$DUMP")/MANIFIESTO-${STEM}.json"
fi
[[ -f "$MANIFEST" ]] || die "No encuentro el manifiesto: $(basename "$MANIFEST")."
jq -e . "$MANIFEST" >/dev/null 2>&1 || die "El manifiesto no es JSON válido."

M_SHA="$(jq -r '.sha256 // empty' "$MANIFEST")"
M_BYTES="$(jq -r '.bytes // empty' "$MANIFEST")"
M_SCHEMA="$(jq -r '.schema // empty' "$MANIFEST")"
M_ALEMBIC="$(jq -r '.alembic // empty' "$MANIFEST")"
M_DESTINO="$(jq -r '.codigo_destino_sha_completo // empty' "$MANIFEST")"
M_DESPLEGADO="$(jq -r '.codigo_desplegado_sha_completo // empty' "$MANIFEST")"

if [[ -n "$M_SCHEMA" && "$M_SCHEMA" != "1" ]]; then
    die "El manifiesto declara schema '$M_SCHEMA'; este script solo entiende el schema 1."
fi
if [[ -z "$M_SCHEMA" ]]; then
    warn "El manifiesto no declara schema; se asume el esquema 1."
fi

[[ -n "$M_SHA" ]] || die "El manifiesto no declara sha256."
[[ -n "$M_BYTES" && "$M_BYTES" =~ ^[0-9]+$ ]] || die "El manifiesto no declara bytes válidos."
SHA_REAL="$(sha256sum "$DUMP" | awk '{print $1}')"
BYTES_REAL="$(stat -c %s "$DUMP")"
[[ "$SHA_REAL" == "$M_SHA" ]] || die "El SHA-256 del dump no coincide con el manifiesto."
[[ "$BYTES_REAL" == "$M_BYTES" ]] || die "El tamaño del dump no coincide con el manifiesto."
if [[ -f "${DUMP}.sha256" ]]; then
    ( cd "$(dirname "$DUMP")" && sha256sum -c "$(basename "$DUMP").sha256" >/dev/null 2>&1 ) || \
        die "El sidecar .sha256 no coincide con el dump."
fi

if [[ -n "$M_ALEMBIC" && -n "$ALEMBIC_ESPERADA" && "$M_ALEMBIC" != "$ALEMBIC_ESPERADA" ]]; then
    die "El manifiesto declara Alembic '$M_ALEMBIC'; se esperaba '$ALEMBIC_ESPERADA'."
fi
if [[ "$M_DESTINO" != "$HEAD_ANTES" && "$M_DESPLEGADO" != "$HEAD_ANTES" ]]; then
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

gzip -t "$DUMP" 2>/dev/null || die "gzip -t falla: el dump no es un gzip íntegro."
if ! INSPECCION="$(inspeccionar "$DUMP")"; then
    die "No pude descomprimir o leer el dump."
fi
IFS='|' read -r T_HEADER T_AV T_SERIES T_FILES T_WISH T_ISSUES VERSION_DUMP \
    N_SERIES N_ISSUES N_FILES N_OPS N_WISH <<< "$INSPECCION"
VERSION_DUMP="$(printf '%s' "$VERSION_DUMP" | tr -d '[:space:]')"

[[ "$T_HEADER" == "1" ]] || die "El dump no tiene la cabecera de pg_dump."
for par in "alembic_version:$T_AV" "series:$T_SERIES" "files:$T_FILES" "wishlist:$T_WISH"; do
    [[ "${par#*:}" == "1" ]] || die "El dump no contiene la tabla ${par%%:*}."
done
[[ -n "$VERSION_DUMP" ]] || die "El dump no contiene version_num en alembic_version."

if [[ -n "$M_ALEMBIC" && "$M_ALEMBIC" != "$VERSION_DUMP" ]]; then
    die "El manifiesto declara Alembic '$M_ALEMBIC' pero el dump trae '$VERSION_DUMP'."
fi

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
    die "Revisión incompatible: dump '$VERSION_DUMP', esperada '$ESPERADA'. No toco la BD."
fi
if [[ "$ACTUAL" != "$ESPERADA" ]]; then
    die "La BD actual está en '$ACTUAL' y se esperaba '$ESPERADA'. No toco la BD."
fi

# ── Plan / dry-run ──────────────────────────────────────────────────────────
printf '\nDatos a restaurar (sin cambiar el código):\n'
printf '  HEAD:              %s\n' "${HEAD_ANTES:0:12}…"
printf '  Proyecto:          %s\n' "$PROYECTO"
printf '  Dump:              %s\n' "$BASE"
printf '  Manifiesto:        %s\n' "$(basename "$MANIFEST")"
printf '  SHA-256:           %s…\n' "${SHA_REAL:0:12}"
printf '  Alembic esperado:  %s\n' "$ESPERADA"
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

# ── Copia de seguridad previa ────────────────────────────────────────────────
DB_TOCADA=0
TS="$(date +%Y%m%d_%H%M%S)"
SEGURIDAD="$BACKUP_DIR/rollback-safety_${TS}.sql.gz"
LOG="$BACKUP_DIR/datos_${TS}.log"
FASE="preparación"

mkdir -p "$BACKUP_DIR" || die "No puedo crear BACKUP_DIR."
[[ -w "$BACKUP_DIR" ]] || die "BACKUP_DIR no es escribible."

TAMANO_KB="$(tamano_bd_kb)"
if ! exigir_espacio_kb "$(espacio_libre_kb "$BACKUP_DIR")" "${TAMANO_KB}" \
        "la copia de seguridad previa a restaurar"; then
    die "No hay espacio para la copia de seguridad. No se ha tocado la BD."
fi
TAMANO_DUMP_KB="$(gzip -l "$DUMP" 2>/dev/null | awk 'NR == 2 { print int($2 / 1024) }')"
if ! exigir_espacio_kb "$(espacio_postgres_libre_kb)" "${TAMANO_DUMP_KB}" \
        "restaurar la base de datos"; then
    die "No hay espacio en el volumen de PostgreSQL para restaurar. No se ha tocado la BD."
fi

info "Copia de seguridad de la BD actual..."
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
if ! "${COMPOSE[@]}" exec -T postgres dropdb -U "$DB_USER" --if-exists --force "$DB_NAME" >/dev/null; then
    recuperar "no pude eliminar $DB_NAME; la BD sigue intacta"
fi
DB_TOCADA=1

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
    recuperar "la revisión restaurada es '$REV_REST' y se esperaba '$ESPERADA'"
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
printf '  Dump:              %s\n' "$BASE"
printf '  Copia previa:      %s\n' "$(basename "$SEGURIDAD")"
printf '  Alembic:           %s\n' "$REV_REST"
printf '  Recuentos:         series=%s issues=%s files=%s operaciones=%s wishlist=%s\n' \
    "$R_SERIES" "$R_ISSUES" "$R_FILES" "$R_OPS" "$R_WISH"
printf '  Vínculos huérfanos: 0\n'
printf '  Health:            %s (%s intentos)\n' "$HEALTH_URL" "$HEALTH_INTENTOS"
printf '  Detalle:           %s\n' "$(basename "$LOG")"
