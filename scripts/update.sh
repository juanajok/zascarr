#!/usr/bin/env bash
# =============================================================================
# update.sh — Actualiza ZascArr a la última versión de su rama.
#
# Orden (importa, y no es el obvio):
#   1. Comprobar requisitos (docker, compose, git, demonio) y localizar .env.
#   2. Abortar si hay cambios locales sin guardar.
#   3. Grabar el SHA actual (para poder volver).
#   4. BACKUP de PostgreSQL ANTES de tocar nada (obligatorio).
#   5. git pull --ff-only (sin merges sucios; si diverge, aborta).
#   6. Rebuild de la imagen (las deps viven en la IMAGEN, no en el host).
#   7. Migraciones DENTRO del contenedor (alembic upgrade head).
#   8. Recrear el servicio y verificar el healthcheck.
#
# Garantía (A3): este script no toca la colección de tebeos. Si algo falla antes
# del paso 8, la BD queda con el backup previo y el código puede volver al SHA
# anterior mediante la referencia de rescate refs/zascarr/update/<TS>.
#
# Rollback correcto (NO basta con resetear el código): restaurar el dump previo
# y volver al SHA anterior — ver README.md, sección "Actualizar ZascArr".
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TEBEOTECA_ROOT="${TEBEOTECA_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
COMPOSE_FILE="${REPO_DIR}/docker-compose.yml"
ENV_FILE="${TEBEOTECA_ROOT}/.env"

BACKUP_DIR="${BACKUP_DIR:-/var/backups/zascarr/postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
DB_NAME="${DB_NAME:-tebeoteca}"
DB_USER="${DB_USER:-comics_admin}"
BRANCH="${BRANCH:-$(git -C "${REPO_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"

B='\033[1m'; G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; N='\033[0m'
info()    { echo -e "${B}→${N} $*"; }
success() { echo -e "${G}✓${N} $*"; }
warn()    { echo -e "${Y}⚠${N}  $*"; }
die()     { echo -e "${R}✗${N} $*" >&2; exit 1; }

# Todos los comandos de compose van con -f y --env-file explícitos: el .env vive
# fuera del repo (TEBEOTECA_ROOT/.env), así que no se puede depender del cwd.
COMPOSE=(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}")

echo -e "\n${B}====================================${N}"
echo -e "${B}  ZascArr — Actualización${N}"
echo -e "${B}====================================${N}\n"

# ── 1. Requisitos ────────────────────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die \
    "No encuentro Docker. Instálalo con: sudo apt-get install docker.io docker-compose-plugin"
docker compose version >/dev/null 2>&1 || die \
    "Falta el plugin de Docker Compose. Instálalo con: sudo apt-get install docker-compose-plugin"
command -v git >/dev/null 2>&1 || die \
    "No encuentro git. Instálalo con: sudo apt-get install git"
docker info >/dev/null 2>&1 || die \
    "El demonio de Docker no responde. Arranca el servicio con: sudo systemctl start docker"
[[ -f "${COMPOSE_FILE}" ]] || die "No encuentro ${COMPOSE_FILE}. ¿Está el repo completo en ${REPO_DIR}?"
[[ -f "${ENV_FILE}" ]] || die \
    "No encuentro ${ENV_FILE}. Se espera el .env que creó bootstrap.sh en ${TEBEOTECA_ROOT}."
[[ "${BRANCH}" != "HEAD" ]] || die \
    "El repo está en HEAD desacoplado. Ve a una rama (git checkout main) antes de actualizar."

# ── 2. Árbol limpio ──────────────────────────────────────────────────────────
if ! git -C "${REPO_DIR}" diff --quiet || ! git -C "${REPO_DIR}" diff --cached --quiet; then
    die "Hay cambios locales sin guardar en ${REPO_DIR}. Guarda (git commit) o descarta (git checkout -- .) antes de actualizar."
fi

# ── 3. SHA actual + referencia de rescate ────────────────────────────────────
TS="$(date +%Y%m%d_%H%M%S)"
PREV_SHA="$(git -C "${REPO_DIR}" rev-parse HEAD)"
# Ref temporal: sobrevive al pull y a un reset (a diferencia del reflog) para
# poder volver al SHA anterior aunque algo falle a mitad. Se borra al terminar bien.
UPDATE_REF="refs/zascarr/update/${TS}"
git -C "${REPO_DIR}" update-ref "${UPDATE_REF}" "${PREV_SHA}"
info "Versión actual: ${PREV_SHA:0:7} (rama ${BRANCH})"
info "Referencia de rescate: ${UPDATE_REF}"

# ── 4. Backup OBLIGATORIO y atómico ANTES de tocar nada ──────────────────────
info "Copia de seguridad de PostgreSQL (antes de actualizar)..."
mkdir -p "${BACKUP_DIR}" || die "No puedo crear ${BACKUP_DIR}. ¿Permisos sobre el disco de backups?"
DEST="${BACKUP_DIR}/backup_${TS}.sql.gz"
TMP="${DEST}.tmp"
# Temporal + mv atómico: un fallo a mitad nunca deja un .gz parcial con pinta de válido.
if ! "${COMPOSE[@]}" exec -T postgres pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${TMP}"; then
    rm -f "${TMP}"
    die "El backup falló. NO se ha actualizado nada. Revisa: docker compose -f ${COMPOSE_FILE} logs postgres"
fi
mv "${TMP}" "${DEST}"
success "Backup: ${DEST}"
# Retención (mismo criterio que scripts/backup.sh)
find "${BACKUP_DIR}" -name 'backup_*.sql.gz' -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true

# ── 5. Actualizar código (fast-forward, sin merges sucios) ───────────────────
info "Descargando la última versión..."
git -C "${REPO_DIR}" fetch origin "${BRANCH}" || die \
    "No pude contactar con GitHub. ¿Red caída? Reintenta cuando vuelva."
if ! git -C "${REPO_DIR}" merge --ff-only "origin/${BRANCH}"; then
    die "La rama local y origin/${BRANCH} han divergido; no puedo avanzar sin merge. Resuélvelo a mano (git status) y reintenta. La BD NO se ha tocado."
fi
NEW_SHA="$(git -C "${REPO_DIR}" rev-parse HEAD)"

if [[ "${NEW_SHA}" == "${PREV_SHA}" ]]; then
    info "Ya estabas en la última versión (${NEW_SHA:0:7}). Re-creo el servicio igualmente para dejarlo sano."
else
    success "Código actualizado: ${PREV_SHA:0:7} → ${NEW_SHA:0:7}"
    if ! git -C "${REPO_DIR}" diff --quiet "${PREV_SHA}" "${NEW_SHA}" -- .env.example; then
        warn "Ha cambiado .env.example: revisa ${ENV_FILE} por si hay variables nuevas."
    fi
fi

# ── 6. Rebuild de la imagen (las dependencias viven en la imagen) ────────────
info "Reconstruyendo la imagen (puede tardar varios minutos en una Pi)..."
"${COMPOSE[@]}" build zascarr || die \
    "Falló la construcción de la imagen. El CÓDIGO ya está actualizado (${NEW_SHA:0:7}) pero la imagen no\n  se ha reconstruido y la BD NO se ha migrado. Para volver al código anterior:\n    git -C ${REPO_DIR} reset --hard ${UPDATE_REF}\n  (backup de la BD: ${DEST})"

# ── 7. Migraciones DENTRO del contenedor (sin pip en el host) ────────────────
info "Aplicando migraciones de base de datos..."
"${COMPOSE[@]}" run --rm zascarr alembic upgrade head || die \
    "Las migraciones fallaron. El código está actualizado, pero la BD puede quedar a medias.\n  Restaura ${DEST} y vuelve atrás con: git -C ${REPO_DIR} reset --hard ${UPDATE_REF}"

# ── 8. Recrear el servicio y verificar ───────────────────────────────────────
info "Reiniciando ZascArr..."
"${COMPOSE[@]}" up -d zascarr || die \
    "No pude arrancar ZascArr. Revisa: docker compose -f ${COMPOSE_FILE} logs zascarr"

info "Verificando healthcheck..."
MAX=60; ELAPSED=0
until curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; do
    ELAPSED=$((ELAPSED+2))
    [[ $ELAPSED -ge $MAX ]] && die \
        "ZascArr no responde tras ${MAX}s. Revisa: docker compose -f ${COMPOSE_FILE} logs zascarr\n  Para volver atrás: restaura ${DEST} y 'git -C ${REPO_DIR} reset --hard ${UPDATE_REF}'"
    echo -n "."; sleep 2
done
echo ""
success "ZascArr responde en http://127.0.0.1:8000"

# Actualización completa y verificada: la referencia de rescate ya no hace falta.
git -C "${REPO_DIR}" update-ref -d "${UPDATE_REF}" 2>/dev/null || true

echo -e "\n${B}====================================${N}"
echo -e "${G}${B}  Actualización completada${N}"
echo -e "${B}====================================${N}\n"
echo "  Versión anterior: ${PREV_SHA:0:7}"
echo "  Versión actual:   ${NEW_SHA:0:7}"
echo ""
echo "  Si algo va mal, el rollback NO es solo cambiar el código"
echo "  (si se aplicaron migraciones nuevas, hay que restaurar también la BD):"
echo ""
echo "    1. Levantar la BD:"
echo "         docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d postgres"
echo "    2. Vaciar y restaurar el dump previo (${DEST}):"
echo "         docker compose -f ${COMPOSE_FILE} exec -T postgres dropdb -U ${DB_USER} --if-exists ${DB_NAME}"
echo "         docker compose -f ${COMPOSE_FILE} exec -T postgres createdb -U ${DB_USER} ${DB_NAME}"
echo "         gunzip -c ${DEST} | docker compose -f ${COMPOSE_FILE} exec -T postgres psql -U ${DB_USER} ${DB_NAME}"
echo "    3. Volver al código anterior (${PREV_SHA:0:7}):"
echo "         git -C ${REPO_DIR} reset --hard ${PREV_SHA}"
echo "    4. Reconstruir y arrancar la versión anterior:"
echo "         docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} build zascarr"
echo "         docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} up -d zascarr"
echo ""
