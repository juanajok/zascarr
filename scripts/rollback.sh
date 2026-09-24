#!/usr/bin/env bash
# =============================================================================
# rollback.sh — Revierte la última actualización de ZascArr.
#
# Uso:
#   sudo bash scripts/rollback.sh                 # usa la última actualización
#   sudo bash scripts/rollback.sh --sha <SHA> --backup <ruta.sql.gz>
#   sudo bash scripts/rollback.sh --dry-run       # solo enseña el plan
#
# Cómo sabe a dónde volver: update.sh deja DOS cosas con el mismo <TS>:
#   - la referencia de rescate  refs/zascarr/update/<TS>
#   - el dump previo            update_<TS>.sql.gz
# Este script empareja ambas. No adivina:
#   - NO usa "el backup más reciente": backup.sh corre a diario (timer systemd
#     a las 04:00), así que el más reciente suele tener ya el esquema NUEVO.
#     Restaurarlo no revertiría nada y lo llamaríamos "rollback" con un tick.
#   - NO usa HEAD@{1}: el reflog cambia con cualquier operación intermedia y
#     caduca; la referencia de rescate está hecha justo para esto.
#
# Orden:
#   1. Requisitos, git utilizable y argumentos.
#   2. Resolver y VALIDAR el commit destino y el dump (emparejados por ref).
#   3. Enseñar el plan y pedir confirmación.
#   4. Copia de seguridad de la BD ACTUAL (red de seguridad del propio rollback).
#   5. Parar ZascArr y restaurar el dump (dropdb --force + psql ON_ERROR_STOP).
#   6. Verificar que la restauración tiene tablas.
#   7. Guardar copia de este script fuera del repo y resetear el código.
#   8. Vaciar Redis, reconstruir y arrancar. Verificar healthcheck.
#
# Aviso importante: si el commit destino es anterior a la existencia de este
# script, `git reset --hard` lo borra del repo. Por eso el paso 7 guarda una
# copia en /tmp y su ruta se imprime al final.
#
# Garantía (A3): este script no toca la colección de tebeos.
# =============================================================================
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_comun.sh"

TS="$(date +%Y%m%d_%H%M%S)"
TARGET_SHA=""
DUMP=""
REF_USADA=""
ASUMIR_SI=0
DRY_RUN=0
FORZAR=0
SEGURIDAD=""
RESCATE_REF=""
FASE="preparación"
FICHERO="${SCRIPT_DIR}/rollback.sh"

uso() {
    cat <<EOF
Revierte la última actualización de ZascArr.

Uso:
  sudo bash scripts/rollback.sh [opciones]

Opciones:
  --sha <SHA>       Commit al que volver (por defecto: el de la referencia
                    de rescate que dejó update.sh).
  --backup <ruta>   Dump .sql.gz a restaurar (por defecto: el emparejado con
                    esa misma referencia, update_<TS>.sql.gz).
  --yes, -y         No preguntar (para automatizar).
  --forzar          Saltar las protecciones: repetir un rollback ya hecho
                    (BORRA todo lo guardado desde entonces) o descartar
                    cambios locales sin guardar.
  --dry-run, -n     Enseñar el plan y salir sin tocar nada.
  -h, --help        Esta ayuda.

Variables de entorno:
  BACKUP_DIR (def. /var/backups/zascarr/postgres), DB_NAME, DB_USER,
  ZASCARR_ROOT, HEALTH_URL, HEALTH_TIMEOUT.
EOF
}

# Salida limpia en cualquier interrupción: durante media restauración la BD
# puede estar vacía, y eso no se puede quedar en silencio.
interrumpido() {
    echo
    die "Interrumpido en la fase: ${FASE}.
  NO arranques ZascArr todavía. Estado de la base de datos: puede estar a medias.
  Copia de la BD anterior: ${SEGURIDAD:-no llegó a crearse}.
  Revisa los contenedores con: docker compose -f ${COMPOSE_FILE} ps"
}
trap interrumpido INT TERM

echo -e "\n${B}====================================${N}"
echo -e "${B}  ZascArr — Rollback${N}"
echo -e "${B}====================================${N}\n"

# ── 1. Requisitos y argumentos ───────────────────────────────────────────────
comprobar_requisitos
comprobar_git_utilizable

while [[ $# -gt 0 ]]; do
    case "$1" in
        --sha)     [[ -n "${2:-}" ]] || die "--sha necesita un valor"; TARGET_SHA="$2"; shift 2 ;;
        --sha=*)   TARGET_SHA="${1#*=}"; shift ;;
        --backup)  [[ -n "${2:-}" ]] || die "--backup necesita una ruta"; DUMP="$2"; shift 2 ;;
        --backup=*) DUMP="${1#*=}"; shift ;;
        --yes|-y)  ASUMIR_SI=1; shift ;;
        --forzar)  FORZAR=1; shift ;;
        --dry-run|-n) DRY_RUN=1; shift ;;
        -h|--help) uso; exit 0 ;;
        -*)        die "Opción desconocida: $1 (usa --help)" ;;
        *)         die "Argumento inesperado: $1 (usa --help)" ;;
    esac
done

PREV_SHA="$(git -C "${REPO_DIR}" rev-parse HEAD)" || die \
    "No puedo leer el commit actual de ${REPO_DIR}."

# ── 2. Resolver el commit y el dump (emparejados por la ref de rescate) ──────
if [[ -z "${TARGET_SHA}" && -z "${DUMP}" ]]; then
    info "Buscando la pareja commit + backup en refs/zascarr/update/..."
    while read -r _ref _sha; do
        [[ -n "${_ref:-}" ]] || continue
        _pareja="$(dump_de_ref "${_ref}")"
        if [[ -f "${_pareja}" ]]; then
            TARGET_SHA="${_sha}"; DUMP="${_pareja}"; REF_USADA="${_ref}"
            break
        fi
        warn "La referencia ${_ref} no tiene su backup (${_pareja}); la salto."
    done < <(refs_rescate)

    if [[ -z "${TARGET_SHA}" ]]; then
        echo -e "\n  Backups en ${BACKUP_DIR}:" >&2
        find "${BACKUP_DIR}" -maxdepth 1 \( -name 'backup_*.sql.gz' -o -name 'update_*.sql.gz' -o -name 'rollback-safety_*.sql.gz' \) -printf '    %f\n' 2>/dev/null \
            | sort >&2 || true
        echo -e "\n  Últimos commits de la rama:" >&2
        git -C "${REPO_DIR}" log --oneline -5 >&2 || true
        die "No encuentro ninguna pareja referencia + backup.
  No adivino a propósito: el backup más reciente puede tener ya el esquema nuevo
  (backup.sh corre a diario) y HEAD@{1} cambia con cualquier operación.
  Elige tú con cuidado:
    sudo bash scripts/rollback.sh --sha <SHA> --backup <ruta-del-dump>"
    fi
fi

# Validar y NORMALIZAR el commit en cuanto lo tenemos: así el emparejamiento
# por SHA de más abajo compara dos hashes completos y no prefijos.
validar_sha() { git -C "${REPO_DIR}" rev-parse --verify --quiet "${1}^{commit}" >/dev/null 2>&1; }
normalizar_sha() { git -C "${REPO_DIR}" rev-parse "${1}^{commit}"; }

if [[ -n "${TARGET_SHA}" ]]; then
    validar_sha "${TARGET_SHA}" || die \
        "\"${TARGET_SHA}\" no es un commit de este repo.
  Comprueba el SHA: git -C ${REPO_DIR} log --oneline -10"
    TARGET_SHA="$(normalizar_sha "${TARGET_SHA}")"
fi

# Solo --backup: deducir el commit del TS que comparten ref y nombre del dump.
if [[ -z "${TARGET_SHA}" ]]; then
    _ts_dump="$(basename "${DUMP}")"; _ts_dump="${_ts_dump#update_}"; _ts_dump="${_ts_dump%.sql.gz}"
    while read -r _ref _sha; do
        [[ -n "${_ref:-}" ]] || continue
        if [[ "$(ts_de_ref "${_ref}")" == "${_ts_dump}" ]]; then
            TARGET_SHA="${_sha}"; REF_USADA="${_ref}"; break
        fi
    done < <(refs_rescate)
    [[ -n "${TARGET_SHA}" ]] || die \
        "No puedo deducir a qué commit corresponde ${DUMP}.
  Pásame también el commit: --sha <SHA>  (git -C ${REPO_DIR} log --oneline -10)"
    validar_sha "${TARGET_SHA}" || die \
        "El commit ${TARGET_SHA} de la referencia de rescate ya no existe en este repo
  (¿se hizo git gc?). Pásame el commit a mano: --sha <SHA>"
    TARGET_SHA="$(normalizar_sha "${TARGET_SHA}")"
fi

# Solo --sha: buscar el dump emparejado con ese commit (comparación exacta).
if [[ -z "${DUMP}" ]]; then
    while read -r _ref _sha; do
        [[ -n "${_ref:-}" ]] || continue
        [[ "${_sha}" == "${TARGET_SHA}" ]] || continue
        _pareja="$(dump_de_ref "${_ref}")"
        [[ -f "${_pareja}" ]] || continue
        DUMP="${_pareja}"; REF_USADA="${_ref}"; break
    done < <(refs_rescate)
    [[ -n "${DUMP}" ]] || die \
        "No encuentro el backup que corresponde a ${TARGET_SHA}.
  Pásamelo explícitamente: --backup <ruta.sql.gz>  (los tienes en ${BACKUP_DIR})"
fi

if [[ "${TARGET_SHA}" == "${PREV_SHA}" ]]; then
    # El código YA está en el destino: lo normal es que este rollback ya se
    # hiciera (o que alguien reseteó a mano). Restaurar el dump otra vez tiraría
    # todos los datos guardados desde entonces, así que no se hace sin querer.
    [[ "${FORZAR}" -eq 1 ]] || die \
        "El commit destino es el commit actual (${PREV_SHA:0:7}): el código ya está ahí.
  Lo más probable es que este rollback ya se hiciera. Volver a restaurar el dump
  BORRARÍA todo lo guardado desde entonces.
  Si de verdad quieres hacerlo, repite el comando con --forzar."
    warn "Destino = actual y has pasado --forzar: restauraré el dump igualmente."
fi
if ! git -C "${REPO_DIR}" merge-base --is-ancestor "${TARGET_SHA}" "${PREV_SHA}" 2>/dev/null; then
    warn "${TARGET_SHA:0:7} no es ancestro de ${PREV_SHA:0:7}: el reset llevará el árbol a otra historia."
fi

verificar_dump "${DUMP}"

# El reset --hard descarta los cambios locales sin avisar; misma regla que
# update.sh. Se comprueba aquí, ANTES de tocar la base de datos.
if ! git -C "${REPO_DIR}" diff --quiet || ! git -C "${REPO_DIR}" diff --cached --quiet; then
    [[ "${FORZAR}" -eq 1 ]] || die \
        "Hay cambios locales sin guardar en ${REPO_DIR}.
  El reset --hard los descartaría. Guarda (git commit) o descarta (git checkout -- .),
  o si de verdad quieres tirarlos, repite con --forzar."
    warn "--forzar: se descartarán los cambios locales sin guardar."
fi

# ── 3. Plan y confirmación ───────────────────────────────────────────────────
echo -e "\n${B}  Esto es lo que va a pasar${N}"
echo "    Commit actual  : ${PREV_SHA:0:7}"
echo "    Commit destino : ${TARGET_SHA:0:7}"
echo "    Backup a usar  : ${DUMP}"
echo "    Base de datos  : ${DB_NAME} (usuario ${DB_USER})"
echo "    Antes de tocar nada se hará una copia de la BD ACTUAL."
if [[ -n "${REF_USADA}" ]]; then
    echo "    Referencia     : ${REF_USADA} (se conserva: es el ancla del rollback)"
fi
echo ""

if [[ "${DRY_RUN}" -eq 1 ]]; then
    success "Simulación (--dry-run): no he tocado nada."
    exit 0
fi

if [[ "${ASUMIR_SI}" -eq 0 ]]; then
    [[ -t 0 ]] || die "No hay terminal para preguntar. Si de verdad quieres continuar, usa --yes."
    read -r -p "  Escribe SI para continuar: " _respuesta || die "No he podido leer la respuesta. Usa --yes."
    [[ "${_respuesta}" == "SI" ]] || die "Cancelado. No se ha tocado nada."
fi

# ── 4. Red de seguridad: copia de la BD ACTUAL ───────────────────────────────
# Un rollback también es destructivo: si el dump elegido es el equivocado,
# esto es lo único que permite deshacerlo. Va antes de parar la app (pg_dump
# es consistente por sí solo). Nombre inequívoco: rollback-safety_<TS> es la
# copia "antes del rollback", distinta del update_<TS> previo a la actualización.
FASE="copia de seguridad de la base de datos actual"
SEGURIDAD="${BACKUP_DIR}/rollback-safety_${TS}.sql.gz"
mkdir -p "${BACKUP_DIR}" || die "No puedo crear ${BACKUP_DIR}. ¿Permisos sobre el disco de backups?"

info "Levantando PostgreSQL..."
"${COMPOSE[@]}" up -d postgres >/dev/null || die "No pude arrancar PostgreSQL."
esperar_postgres 60 || die "PostgreSQL no responde tras 60s. Nada se ha tocado."

info "Copia de seguridad de la BD actual (red de seguridad del rollback)..."
volcar_postgres "${SEGURIDAD}" || die \
    "No pude respaldar la base de datos actual. NO sigo: sin red de seguridad, un
  dump equivocado sería irreversible. Revisa: docker compose -f ${COMPOSE_FILE} logs postgres"
success "Copia de la BD actual: ${SEGURIDAD}"

LOG="${BACKUP_DIR}/rollback_${TS}.log"
if ! : > "${LOG}" 2>/dev/null; then
    warn "No puedo escribir ${LOG}; el detalle de la restauración no quedará guardado."
    LOG=/dev/null
fi

# ── 5. Parar la app y restaurar el dump ──────────────────────────────────────
FASE="restauración de la base de datos"
info "Deteniendo ZascArr..."
"${COMPOSE[@]}" stop zascarr >/dev/null || warn "No pude detener ZascArr (quizá ya estaba parado)."

info "Eliminando la base de datos actual..."
# --force (PostgreSQL 13+) corta las conexiones abiertas. Sin esto, una sesión
# psql suelta hace fallar dropdb, y seguir adelante dejaría la app parada y la
# BD sin tocar con un error que no explica nada.
"${COMPOSE[@]}" exec -T postgres dropdb -U "${DB_USER}" --if-exists --force "${DB_NAME}" || die \
    "No pude eliminar ${DB_NAME}. La BD sigue intacta y el código NO se ha tocado.
  Copia de seguridad: ${SEGURIDAD}
  Revisa: docker compose -f ${COMPOSE_FILE} logs postgres"

info "Creando base de datos vacía..."
"${COMPOSE[@]}" exec -T postgres createdb -U "${DB_USER}" "${DB_NAME}" || die \
    "No pude crear ${DB_NAME} vacía. La copia de la BD anterior está en ${SEGURIDAD}.
  Revisa: docker compose -f ${COMPOSE_FILE} logs postgres"

info "Restaurando ${DUMP}..."
info "El detalle queda en ${LOG}"
# ON_ERROR_STOP=1 es imprescindible: sin él psql devuelve 0 aunque fallen
# sentencias sueltas, y daríamos por buena una restauración a medias.
if ! gunzip -c "${DUMP}" | "${COMPOSE[@]}" exec -T postgres \
        psql -q -v ON_ERROR_STOP=1 -U "${DB_USER}" -d "${DB_NAME}" 2>&1 | tee -a "${LOG}"; then
    die "La restauración falló (mira ${LOG}). La BD puede estar a medias.
  La copia de la BD anterior está en: ${SEGURIDAD}
  NO arranques ZascArr hasta restaurarla:
    gunzip -c ${SEGURIDAD} | docker compose -f ${COMPOSE_FILE} exec -T postgres psql -q -v ON_ERROR_STOP=1 -U ${DB_USER} -d ${DB_NAME}"
fi
success "Base de datos restaurada"

# ── 6. Verificar que la restauración es una BD de ZascArr de verdad ──────────
# ON_ERROR_STOP ya garantiza que el dump se aplicó entero; aquí se confirma que
# el CONTENIDO es el esperado, no "cualquier dump que descomprime". El
# healthcheck del final prueba la app, no la base de datos.
info "Comprobando el esquema restaurado..."
FALTAN=""
for _tabla in alembic_version series files wishlist; do
    _n="$("${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_name='${_tabla}';" 2>/dev/null \
        | tr -d '[:space:]')" || _n=0
    [[ "${_n}" == "1" ]] || FALTAN="${FALTAN} ${_tabla}"
done
if [[ -n "${FALTAN}" ]]; then
    die "La base de datos restaurada no parece una BD de ZascArr: faltan las tablas:${FALTAN}.
  El dump era válido como gzip, pero no su contenido. Copia de la BD anterior: ${SEGURIDAD}"
fi
REVISION="$("${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
    "SELECT version_num FROM alembic_version;" 2>/dev/null | tr -d '[:space:]')" || REVISION=""
FILAS="$("${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -tAc \
    "SELECT (SELECT count(*) FROM series) || '/' || (SELECT count(*) FROM files) || '/' || (SELECT count(*) FROM wishlist);" 2>/dev/null \
    | tr -d '[:space:]')" || FILAS="-/-/-"
success "Restauración verificada: esquema de ZascArr completo, revisión de alembic «${REVISION:-no encontrada}», series/files/wishlist ${FILAS}"

# ── 7. Guardar el script y resetear el código ────────────────────────────────
FASE="reset del código"
COPIASCRIPT="/tmp/zascarr-rollback-${TS}.sh"
if [[ -f "${FICHERO}" ]] && cp "${FICHERO}" "${COPIASCRIPT}" 2>/dev/null; then
    chmod +x "${COPIASCRIPT}" 2>/dev/null || true
    info "Copia de este script fuera del repo: ${COPIASCRIPT}"
else
    COPIASCRIPT=""
    warn "No pude guardar una copia del script en /tmp. Si el commit destino es anterior
  a scripts/rollback.sh, el reset lo borrará del repo (el rollback seguirá, ya está cargado)."
fi

# Ancla simétrica para poder DESHACER este rollback: apunta al commit que
# estamos a punto de dejar (PREV_SHA) y sobrevive al reset. Su pareja de datos
# es ${SEGURIDAD}. Sin esto, un rollback equivocado se revertiría solo con el
# reflog, que cambia con cualquier operación intermedia y caduca.
RESCATE_REF="refs/zascarr/rollback-rescue/${TS}"
git -C "${REPO_DIR}" update-ref "${RESCATE_REF}" "${PREV_SHA}"

info "Reseteando el código a ${TARGET_SHA:0:7}..."
git -C "${REPO_DIR}" reset --hard "${TARGET_SHA}" >/dev/null || die \
    "No pude resetear el código. La BD YA está restaurada y el servicio está parado.
  Resuélvelo a mano: git -C ${REPO_DIR} reset --hard ${TARGET_SHA}"
success "Código en ${TARGET_SHA:0:7}"

# ── 8. Redis, reconstruir y arrancar ─────────────────────────────────────────
FASE="arranque del servicio"
# Redis es EXCLUSIVO de ZascArr: docker-compose.yml levanta un contenedor
# zascarr-cache que solo consume la app, así que FLUSHDB no toca datos ajenos.
info "Vaciando la caché de Redis (puede tener estado de la versión nueva)..."
"${COMPOSE[@]}" exec -T redis redis-cli FLUSHDB >/dev/null 2>&1 \
    || warn "No pude vaciar Redis. Si algo se comporta raro: docker compose -f ${COMPOSE_FILE} restart redis"

info "Reconstruyendo la imagen (puede tardar varios minutos en una Pi)..."
"${COMPOSE[@]}" build zascarr || die \
    "Falló la construcción de la imagen. La BD ya está restaurada y el código en ${TARGET_SHA:0:7}.
  Reintenta: docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} build zascarr"

info "Arrancando ZascArr..."
"${COMPOSE[@]}" up -d zascarr || die \
    "No pude arrancar ZascArr. Revisa: docker compose -f ${COMPOSE_FILE} logs zascarr"

info "Verificando healthcheck (${HEALTH_URL})..."
esperar_healthcheck "${HEALTH_TIMEOUT}" || die \
    "ZascArr no responde tras ${HEALTH_TIMEOUT}s.
  La BD ya está restaurada y el código en ${TARGET_SHA:0:7}, pero el servicio no arranca.
  Revisa: docker compose -f ${COMPOSE_FILE} logs zascarr"

# La referencia de rescate de update (REF_USADA) se CONSERVA a propósito:
# mientras siga ahí, el commit destino seguirá siendo el actual y un rollback
# repetido se detendrá pidiendo --forzar en vez de irse dos actualizaciones
# hacia atrás sin avisar. El ancla de ESTE rollback (RESCATE_REF) también se
# conserva para poder deshacerlo. Ambas se podan solas cuando la retención se
# lleva su dump.
podar_refs_huerfanas "${REF_USADA}"
podar_refs_rescate_rollback "${RESCATE_REF}"

echo -e "\n${B}====================================${N}"
echo -e "${G}${B}  Rollback completado${N}"
echo -e "${B}====================================${N}\n"
echo "  Versión anterior (la que se ha revertido): ${PREV_SHA:0:7}"
echo "  Versión actual ahora:                      ${TARGET_SHA:0:7}"
echo "  Backup restaurado:    ${DUMP}"
echo "  Copia de la BD que había antes del rollback:"
echo "    ${SEGURIDAD}"
echo "  Detalle de la restauración: ${LOG}"
if [[ -n "${COPIASCRIPT}" ]]; then
    echo "  Copia de este script: ${COPIASCRIPT}"
fi
echo "  Ancla para deshacer este rollback: ${RESCATE_REF}"
echo ""
echo "  Si quieres volver a la versión que has revertido:"
echo "    docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} stop zascarr"
echo "    gunzip -c ${SEGURIDAD} | docker compose -f ${COMPOSE_FILE} exec -T postgres psql -q -v ON_ERROR_STOP=1 -U ${DB_USER} -d ${DB_NAME}"
echo "    git -C ${REPO_DIR} reset --hard ${RESCATE_REF}"
echo "    docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} build zascarr"
echo "    docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d zascarr"
echo ""
