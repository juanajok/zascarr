#!/usr/bin/env bash
# =============================================================================
# update.sh — Actualiza ZascArr a la última versión de la rama que TÚ indiques.
#
# La rama es OBLIGATORIA y explícita (#307/#231): sin ella no se actualiza nada.
#
#     sudo bash scripts/update.sh --rama main
#     sudo BRANCH=deploy/<candidato> bash scripts/update.sh        # equivalente
#
# Antes elegía por su cuenta la rama en la que estuviera el repo, así que cualquiera con acceso podía desplegar la
# cabeza de `main` sin decidir qué versión instalaba (ocurrió dos veces, sin ventana ni registro).
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
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_exposicion.sh"

# Rama: `--rama <nombre>` o la variable BRANCH. Sin ninguna de las dos, se para ANTES de tocar nada.
# (`--rama` existe porque `sudo` no siempre deja pasar variables de entorno.)
if [[ "${1:-}" == "--rama" ]]; then
    BRANCH="${2:-}"
elif [[ "${1:-}" == --rama=* ]]; then
    BRANCH="${1#--rama=}"
fi
BRANCH="${BRANCH:-}"

echo -e "\n${B}====================================${N}"
echo -e "${B}  ZascArr — Actualización${N}"
echo -e "${B}====================================${N}\n"

# ── 0. La rama la decide quien actualiza ─────────────────────────────────────
[[ -n "${BRANCH}" ]] || die \
    "Dime qué rama quieres instalar. NO se ha actualizado nada.
  Este script ya no elige por su cuenta la versión que se instala: tienes que indicarla tú.
  Para la última versión estable:   sudo bash ${REPO_DIR}/scripts/update.sh --rama main
  Para una versión concreta:        sudo bash ${REPO_DIR}/scripts/update.sh --rama <nombre-de-la-rama>"
[[ "${BRANCH}" =~ ^[A-Za-z0-9._/-]+$ && "${BRANCH}" != -* && "${BRANCH}" != "HEAD" ]] || die \
    "El nombre de la rama no es válido. NO se ha actualizado nada."

# ── 1. Requisitos ────────────────────────────────────────────────────────────
comprobar_requisitos
comprobar_git_utilizable

# ── 1b. Credenciales (ADR 0012) ──────────────────────────────────────────────
# Sin una DB_PASSWORD propia, el servicio `credenciales` de Compose pararía el arranque DESPUÉS de haber hecho el
# backup y traído el código; se comprueba ya, antes de tocar nada.
validar_credenciales "${ENV_FILE}" || die \
    "La configuración no tiene una contraseña de base de datos válida. NO se ha actualizado nada.
  Ejecuta: sudo bash ${REPO_DIR}/scripts/credenciales.sh   (si ya existe una base de datos, se detendrá
  sin inventar otra contraseña y te dirá qué hacer)."
# Protección del .env: solo se AVISA (una instalación anterior lo dejó legible por otros usuarios y esta
# actualización no debe fallar por eso); la corrige credenciales.sh o volver a ejecutar bootstrap.sh.
if (( ENV_FILE_EXPLICITO == 0 )); then
    PROTECCION_RC=0
    PROTECCION_AVISOS="$(comprobar_proteccion "${ENV_FILE}" "${ZASCARR_ROOT}" "${REPO_DIR}")" || PROTECCION_RC=$?
    if [[ "${PROTECCION_RC}" -eq 1 ]]; then
        warn "El .env no está bien protegido:
${PROTECCION_AVISOS}
  Corrígelo (no cambia tu contraseña): sudo bash ${REPO_DIR}/scripts/credenciales.sh"
    fi
fi

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
TAMANO_KB="$(tamano_bd_kb)"
exigir_espacio_kb "$(espacio_libre_kb "${BACKUP_DIR}")" "${TAMANO_KB}" \
        "la copia previa a la actualización" && ESPACIO_RC=0 || ESPACIO_RC=$?
if (( ESPACIO_RC != 0 )); then
    # Nada se ha tocado: la referencia de rescate recién creada no apunta a nada que haga falta y se retira.
    git -C "${REPO_DIR}" update-ref -d "${UPDATE_REF}" 2>/dev/null || true
    if (( ESPACIO_RC == 2 )); then
        die "No pude comprobar si hay sitio para la copia previa. NO se ha actualizado nada."
    fi
    die "No hay espacio para la copia previa. NO se ha actualizado nada."
fi
DEST="${BACKUP_DIR}/update_${TS}.sql.gz"
volcar_postgres "${DEST}" || die \
    "El backup falló. NO se ha actualizado nada.
  Revisa: sudo docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} logs postgres"
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

HIZO_UPDATE=0
if [[ "${NEW_SHA}" == "${PREV_SHA}" ]]; then
    info "Ya estabas en la última versión (${NEW_SHA:0:7}). Re-creo el servicio igualmente."
    # No hay actualización que revertir, así que el ancla, el dump y su
    # manifiesto recién creados solo ocuparían disco y ensuciarían la lista.
    rm -f "${DEST}" "${BACKUP_DIR}/MANIFIESTO-update_${TS}.json"
    git -C "${REPO_DIR}" update-ref -d "${UPDATE_REF}" 2>/dev/null || true
    info "Sin cambios que aplicar: descarto el backup y la referencia que había creado."
else
    HIZO_UPDATE=1
    success "Código actualizado: ${PREV_SHA:0:7} → ${NEW_SHA:0:7}"
    if ! git -C "${REPO_DIR}" diff --quiet "${PREV_SHA}" "${NEW_SHA}" -- .env.example; then
        warn "Ha cambiado .env.example: revisa ${ENV_FILE} por si hay variables nuevas."
    fi
    # #334: el manifiesto se escribe DESPUÉS del fast-forward: `codigo_destino`
    # es el commit anterior y `codigo_desplegado` el que acaba de quedar.
    UPDATE_EXTRA="$(jq -n --arg destino "${PREV_SHA}" --arg desplegado "${NEW_SHA}" \
        --arg ref "${UPDATE_REF}" \
        '{codigo_destino_sha_completo: $destino,
          codigo_desplegado_sha_completo: $desplegado,
          referencia_emparejada: $ref, cubre_rollback_de_codigo: true}')"
    escribir_manifiesto "${DEST}" "update.sh (dump previo y código desplegado)" \
        "update-${TS}" "${UPDATE_EXTRA}" >/dev/null
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
# `--remove-orphans`: una instalación anterior a ADR 0011 tiene un contenedor `zascarr-cache` (Redis) que ya no está en el
# compose; sin esto seguiría vivo, gastando RAM, sin que nada lo use.
"${COMPOSE[@]}" up -d --remove-orphans zascarr || die \
    "No pude arrancar ZascArr. Revisa: sudo docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} logs zascarr"

info "Verificando healthcheck (${HEALTH_URL})..."
esperar_healthcheck "${HEALTH_TIMEOUT}" || die \
    "ZascArr no responde tras ${HEALTH_TIMEOUT}s.
  Revisa: sudo docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} logs zascarr
  Para volver atrás:
    sudo bash scripts/rollback.sh
  (referencia de rescate: ${UPDATE_REF}; backup: ${DEST})"
success "ZascArr responde en ${HEALTH_URL}"

# #334 B2: solo tras una actualización real (no en el no-op). El despliegue se
# invocó con --rama <BRANCH>; la restauración no necesita rama. Lee el manifiesto
# que se acaba de escribir después del fast-forward.
if (( HIZO_UPDATE == 1 )); then
    info "Comprobando que la copia de rescate restaura..."
    if ! "${REPO_DIR}/scripts/probar_restauracion.sh" --dump "${DEST}"; then
        warn "La restauración post-despliegue no pasó; la app sigue arriba. Revisa el estado de restauración (fila del panel y registro)."
    fi
fi

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
# Cómo se entra. Es informativo: un fallo al comprobarlo NUNCA estropea una actualización ya hecha.
ESTADO_ACCESO="$(estado_de_publicacion 2>/dev/null)" || ESTADO_ACCESO="indeterminada"
CONTRASENA_ACCESO_EFECTIVA=""
if [[ "${ESTADO_ACCESO}" == "abierta" ]] && leer_efectiva 2>/dev/null; then
    CONTRASENA_ACCESO_EFECTIVA="${EFECTIVA_CONTRASENA}"
fi
resumen_acceso "${ESTADO_ACCESO}" "${CONTRASENA_ACCESO_EFECTIVA}" || true
echo ""
