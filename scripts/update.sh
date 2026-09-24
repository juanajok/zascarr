#!/usr/bin/env bash
# =============================================================================
# update.sh — Actualiza ZascArr a la última versión de su rama.
#
# Orden (importa, y no es el obvio):
#   1. Comprobar requisitos (docker, compose, git, curl, gzip) y localizar .env.
#   2. Abortar si hay cambios locales sin guardar.
#   3. Grabar el SHA actual y crear la referencia de rescate refs/zascarr/update/<TS>.
#   4. BACKUP de PostgreSQL ANTES de tocar nada (obligatorio) y VERIFICADO.
#   5. git fetch + merge --ff-only (sin merges sucios; si diverge, aborta).
#   6. Rebuild de la imagen (las deps viven en la IMAGEN, no en el host).
#   7. Migraciones DENTRO del contenedor (alembic upgrade head).
#   8. Recrear el servicio y verificar el healthcheck.
#
# Si algo falla a partir del paso 5 NO hay que hacer malabares a mano: este
# script deja la referencia de rescate apuntando al commit anterior y el dump
# con el MISMO <TS>, y scripts/rollback.sh empareja los dos:
#
#     sudo bash scripts/rollback.sh
#
# Garantía (A3): este script no toca la colección de tebeos.
# =============================================================================
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_comun.sh"

BRANCH="${BRANCH:-$(git -C "${REPO_DIR}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"

echo -e "\n${B}====================================${N}"
echo -e "${B}  ZascArr — Actualización${N}"
echo -e "${B}====================================${N}\n"

# ── 1. Requisitos ────────────────────────────────────────────────────────────
comprobar_requisitos
comprobar_git_utilizable
[[ "${BRANCH}" != "HEAD" ]] || die \
    "El repo está en HEAD desacoplado. Ve a una rama (git checkout main) antes de actualizar."

# ── 2. Árbol limpio ──────────────────────────────────────────────────────────
if ! git -C "${REPO_DIR}" diff --quiet || ! git -C "${REPO_DIR}" diff --cached --quiet; then
    die "Hay cambios locales sin guardar en ${REPO_DIR}.
  Guarda (git commit) o descarta (git checkout -- .) antes de actualizar."
fi

# ── 3. SHA actual + referencia de rescate ────────────────────────────────────
TS="$(date +%Y%m%d_%H%M%S)"
PREV_SHA="$(git -C "${REPO_DIR}" rev-parse HEAD)"
# El MISMO TS nombra la referencia de rescate y el backup: de ahí saca
# rollback.sh la pareja commit + dump sin tener que adivinar nada.
UPDATE_REF="refs/zascarr/update/${TS}"
git -C "${REPO_DIR}" update-ref "${UPDATE_REF}" "${PREV_SHA}"
info "Versión actual: ${PREV_SHA:0:7} (rama ${BRANCH})"
info "Referencia de rescate: ${UPDATE_REF}"

# ── 4. Backup OBLIGATORIO y verificado ANTES de tocar nada ───────────────────
info "Copia de seguridad de PostgreSQL (antes de actualizar)..."
mkdir -p "${BACKUP_DIR}" || die "No puedo crear ${BACKUP_DIR}. ¿Permisos sobre el disco de backups?"
DEST="${BACKUP_DIR}/update_${TS}.sql.gz"
volcar_postgres "${DEST}" || die \
    "El backup falló. NO se ha actualizado nada.
  Revisa: docker compose -f ${COMPOSE_FILE} logs postgres"
# Y se comprueba: un backup sin verificar no es un backup, es una esperanza.
verificar_dump "${DEST}"
success "Backup verificado: ${DEST}"
aplicar_retencion

# ── 5. Actualizar código (fast-forward, sin merges sucios) ───────────────────
info "Descargando la última versión..."
git -C "${REPO_DIR}" fetch origin "${BRANCH}" || die \
    "No pude contactar con GitHub. ¿Red caída? Reintenta cuando vuelva."
if ! git -C "${REPO_DIR}" merge --ff-only "origin/${BRANCH}"; then
    die "La rama local y origin/${BRANCH} han divergido; no puedo avanzar sin merge.
  Resuélvelo a mano (git status) y reintenta. La BD NO se ha tocado."
fi
NEW_SHA="$(git -C "${REPO_DIR}" rev-parse HEAD)"

if [[ "${NEW_SHA}" == "${PREV_SHA}" ]]; then
    info "Ya estabas en la última versión (${NEW_SHA:0:7}). Re-creo el servicio igualmente."
    # No hay actualización que revertir, así que el ancla y el dump recién
    # creados solo ocuparían disco y ensuciarían la lista de referencias.
    rm -f "${DEST}"
    git -C "${REPO_DIR}" update-ref -d "${UPDATE_REF}" 2>/dev/null || true
    info "Sin cambios que aplicar: descarto el backup y la referencia que había creado."
else
    success "Código actualizado: ${PREV_SHA:0:7} → ${NEW_SHA:0:7}"
    if ! git -C "${REPO_DIR}" diff --quiet "${PREV_SHA}" "${NEW_SHA}" -- .env.example; then
        warn "Ha cambiado .env.example: revisa ${ENV_FILE} por si hay variables nuevas."
    fi
fi

# ── 6. Rebuild de la imagen (las dependencias viven en la imagen) ────────────
info "Reconstruyendo la imagen (puede tardar varios minutos en una Pi)..."
"${COMPOSE[@]}" build zascarr || die \
    "Falló la construcción de la imagen. El CÓDIGO ya está actualizado (${NEW_SHA:0:7}) pero
  la imagen no se ha reconstruido y la BD NO se ha migrado. Para volver atrás:
    sudo bash scripts/rollback.sh
  (referencia de rescate: ${UPDATE_REF}; backup: ${DEST})"

# ── 7. Migraciones DENTRO del contenedor (sin pip en el host) ────────────────
info "Aplicando migraciones de base de datos..."
"${COMPOSE[@]}" run --rm zascarr alembic upgrade head || die \
    "Las migraciones fallaron. El código está actualizado, pero la BD puede quedar a medias.
  Para volver atrás (restaura el dump y revierte el código):
    sudo bash scripts/rollback.sh
  (referencia de rescate: ${UPDATE_REF}; backup: ${DEST})"

# ── 8. Recrear el servicio y verificar ───────────────────────────────────────
info "Reiniciando ZascArr..."
"${COMPOSE[@]}" up -d zascarr || die \
    "No pude arrancar ZascArr. Revisa: docker compose -f ${COMPOSE_FILE} logs zascarr"

info "Verificando healthcheck (${HEALTH_URL})..."
esperar_healthcheck "${HEALTH_TIMEOUT}" || die \
    "ZascArr no responde tras ${HEALTH_TIMEOUT}s.
  Revisa: docker compose -f ${COMPOSE_FILE} logs zascarr
  Para volver atrás:
    sudo bash scripts/rollback.sh
  (referencia de rescate: ${UPDATE_REF}; backup: ${DEST})"
success "ZascArr responde en ${HEALTH_URL}"

# La referencia de rescate NO se borra: es el ancla que permite revertir esta
# actualización si el problema aparece dentro de unos días ("la actualización
# fue bien pero la app va rara"). Se podan solas las que ya han perdido su dump
# por la retención, que es lo que acota su número.
podar_refs_huerfanas "${UPDATE_REF}"

echo -e "\n${B}====================================${N}"
echo -e "${G}${B}  Actualización completada${N}"
echo -e "${B}====================================${N}\n"
echo "  Versión anterior: ${PREV_SHA:0:7}"
echo "  Versión actual:   ${NEW_SHA:0:7}"
echo "  Backup previo:    ${DEST}"
echo ""
echo "  Si algo va mal en los próximos días, el rollback NO es solo"
echo "  cambiar el código (hay que restaurar también la BD). Está automatizado:"
echo ""
echo "      sudo bash scripts/rollback.sh"
echo ""
echo "  El script empareja el commit y el backup por la referencia de rescate"
echo "  (${UPDATE_REF##*/}) y hace su propia copia de seguridad antes de tocar nada."
echo ""
