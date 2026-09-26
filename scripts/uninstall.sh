#!/usr/bin/env bash
# =============================================================================
# uninstall.sh — Desinstala ZascArr sin tocar tu biblioteca ni tu configuración.
#
# Por defecto ("make uninstall") borra SOLO lo que es de Docker:
#   - Los tres contenedores (zascarr-orquestador, zascarr-db, zascarr-cache).
#   - La red interna que los conecta.
#   - La imagen que este repo construyó (la de postgres/redis, que son
#     oficiales y pueden estar en uso por otra cosa en la misma máquina,
#     NUNCA se tocan).
#
# NUNCA se borra, ni siquiera con --purge:
#   - HOST_LIBRARY_DIR: tu biblioteca de tebeos ya organizada.
#   - HOST_DOWNLOADS_DIR / HOST_AMULE_INCOMING_DIR: tus carpetas de descargas.
# Es la misma garantía A3 del instalador (bootstrap.sh), del lado de salida:
# si el instalador nunca toca tu colección al entrar, el desinstalador nunca
# la toca al salir. No hay ninguna opción para desactivar esto a propósito.
#
# Con --purge ("make uninstall-purge") además se borra lo que es de la APP
# (nunca lo tuyo):
#   - ZASCARR_DATA_DIR (postgres/, redis/, covers/, vpn-state/): catálogo,
#     wishlist, ajustes y caché de portadas. Se reconstruye solo volviendo a
#     apuntar a tu biblioteca — no es información que solo exista ahí.
#   - El propio .env (en ZASCARR_ROOT, el padre del repo): la próxima
#     instalación tendrá que volver a responder el asistente.
#
# Pide confirmación explícita antes de tocar nada, y al final dice con
# nombre y ruta exacta qué se ha borrado y qué se ha quedado.
# =============================================================================
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_comun.sh"

PURGE=false
for arg in "$@"; do
    case "$arg" in
        --purge) PURGE=true ;;
        -h|--help)
            echo "Uso: $0 [--purge]"
            echo ""
            echo "  (sin opciones)  Borra contenedores, red e imagen de ZascArr."
            echo "                  Conserva ZASCARR_DATA_DIR y el .env."
            echo "  --purge         Además borra ZASCARR_DATA_DIR (catálogo/wishlist/ajustes/"
            echo "                  portadas) y el .env."
            echo ""
            echo "Tu biblioteca (HOST_LIBRARY_DIR) y tus carpetas de descargas NUNCA se"
            echo "tocan, con o sin --purge."
            exit 0
            ;;
        *) die "Opción no reconocida: $arg (prueba: $0 --help)" ;;
    esac
done

echo -e "\n${B}====================================${N}"
echo -e "${B}  ZascArr — Desinstalación${N}"
echo -e "${B}====================================${N}\n"

command -v docker >/dev/null 2>&1 || die \
    "No encuentro Docker. Si ya lo desinstalaste tú a mano, aquí no queda nada más que hacer."
docker compose version >/dev/null 2>&1 || die \
    "Falta el plugin de Docker Compose. Instálalo con: sudo apt-get install docker-compose-plugin"
[[ -f "${COMPOSE_FILE}" ]] || die \
    "No encuentro ${COMPOSE_FILE}. ¿Estás dentro del repo (scripts/uninstall.sh, no suelto)?"

# A diferencia de update.sh/backup.sh, un .env ausente no es motivo para
# abortar: es exactamente el estado en el que puede estar una instalación
# que ya falló a medias o que alguien ya empezó a desmontar a mano. Se
# avisa y se sigue sin él (docker compose usa los valores por defecto del
# propio docker-compose.yml, suficientes para parar los contenedores).
LIBRARY_DIR=""
if [[ -f "${ENV_FILE}" ]]; then
    LIBRARY_DIR="$(grep -m1 '^HOST_LIBRARY_DIR=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)"
else
    warn "No encuentro ${ENV_FILE} — sigo sin él (los contenedores igualmente se pueden parar)."
fi

# ── Qué va a pasar, ANTES de tocar nada ─────────────────────────────────────
echo "Esto va a hacer:"
echo "  - Parar y borrar los contenedores de ZascArr (zascarr-orquestador, zascarr-db, zascarr-cache)."
echo "  - Borrar la red interna y la imagen que este repo construyó."
echo "    (las imágenes oficiales de postgres/redis NO se tocan)"
if $PURGE; then
    echo "  - Borrar también los datos de la app en ${ZASCARR_DATA_DIR} (catálogo, wishlist, ajustes, portadas)."
    if [[ -f "${ENV_FILE}" ]]; then
        echo "  - Borrar también ${ENV_FILE} (la próxima instalación repetirá el asistente)."
    fi
else
    echo "  - CONSERVAR ${ZASCARR_DATA_DIR} (catálogo, wishlist, ajustes, portadas)."
    [[ -f "${ENV_FILE}" ]] && echo "  - CONSERVAR ${ENV_FILE}."
fi
echo ""
if [[ -n "${LIBRARY_DIR}" ]]; then
    echo "  Tu biblioteca (${LIBRARY_DIR}) NUNCA se toca, con o sin --purge."
else
    echo "  Tu biblioteca NUNCA se toca, con o sin --purge."
fi
echo ""
read -r -p "¿Seguro que quieres continuar? Escribe 'si' para confirmar: " CONFIRMACION
[[ "${CONFIRMACION,,}" == "si" ]] || die "Cancelado. No se ha tocado nada."

# ── Contenedores, red e imagen ───────────────────────────────────────────────
info "Parando y borrando contenedores, red e imagen..."
DOWN=(docker compose -f "${COMPOSE_FILE}")
[[ -f "${ENV_FILE}" ]] && DOWN+=(--env-file "${ENV_FILE}")
"${DOWN[@]}" down --rmi local --remove-orphans || die \
    "No pude parar los contenedores. Revisa a mano: docker compose -f ${COMPOSE_FILE} ps"
success "Contenedores, red e imagen borrados."

if $PURGE; then
    info "Borrando datos de la app en ${ZASCARR_DATA_DIR}..."
    # Bug real, encontrado verificando en vivo: Postgres crea su directorio
    # con permisos 700 propiedad del usuario del PROCESO DENTRO DEL
    # CONTENEDOR (buena práctica suya, no un descuido) — un "rm -rf" del
    # usuario del host no puede tocarlo aunque sea dueño del resto del
    # árbol, y como el error quedaba silenciado (`|| true`), el script
    # informaba "borrado" sin haberlo estado. Se borra desde DENTRO de un
    # contenedor, con la MISMA imagen que ya usa docker-compose.yml (no
    # hace falta descargar nada nuevo: ya está en caché de cualquier
    # instalación real) — root dentro del contenedor sí puede borrar sus
    # propios ficheros sea cual sea el usuario interno de cada servicio.
    # ${VAR:?} de guardia: nunca un "rm -rf $VAR/" con VAR vacío por
    # accidente, mismo cuidado de A3 aplicado al lado de borrar.
    if docker run --rm -v "${ZASCARR_DATA_DIR:?}:/purgar" postgres:15-alpine \
        sh -c 'rm -rf /purgar/postgres /purgar/redis /purgar/covers /purgar/vpn-state'
    then
        success "Datos de la app borrados: ${ZASCARR_DATA_DIR}"
    else
        warn "No pude borrar ${ZASCARR_DATA_DIR} automáticamente (revisa permisos). Bórralo a mano:
    sudo rm -rf ${ZASCARR_DATA_DIR}/{postgres,redis,covers,vpn-state}"
    fi
    if [[ -f "${ENV_FILE}" ]]; then
        info "Borrando ${ENV_FILE}..."
        rm -f "${ENV_FILE}"
        success ".env borrado."
    fi
fi

# Avisos informativos, sin tocar nada: los timers systemd de backup/vpn-state
# son opcionales y el usuario los instaló a mano (scripts/backup.sh,
# scripts/vpn-state.sh) — no es este script quien decide desactivarlos.
if command -v systemctl >/dev/null 2>&1; then
    for unidad in zascarr-backup.timer zascarr-vpn-state.timer; do
        if systemctl is-enabled "${unidad}" >/dev/null 2>&1; then
            warn "El timer systemd '${unidad}' sigue activo. Si ya no quieres que corra:
    sudo systemctl disable --now ${unidad}"
        fi
    done
fi

echo -e "\n${B}====================================${N}"
echo -e "${G}${B}  Desinstalación completada${N}"
echo -e "${B}====================================${N}\n"
echo "  Se ha quedado en el disco, intacto:"
if [[ -n "${LIBRARY_DIR}" ]]; then
    echo "    - Tu biblioteca: ${LIBRARY_DIR}"
else
    echo "    - Tu biblioteca (la ruta que le hubieras dado)."
fi
if ! $PURGE; then
    echo "    - Los datos de la app: ${ZASCARR_DATA_DIR}"
    [[ -f "${ENV_FILE}" ]] && echo "    - Tu configuración: ${ENV_FILE}"
    echo ""
    echo "  Para reinstalar sin perder nada de esto, clona el repo de nuevo en"
    echo "  ${ZASCARR_ROOT}/zascarr y ejecuta bootstrap.sh — reconocerá el .env que ya tienes."
else
    echo ""
    echo "  Los datos de la app y la configuración se han borrado también."
fi
echo "  El código en ${REPO_DIR} sigue ahí; bórralo a mano si quieres:"
echo "    rm -rf ${REPO_DIR}"
echo ""
