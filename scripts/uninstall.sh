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
#
# Bug real encontrado en esta misma revisión (2026-09-26): ninguna versión
# anterior de este script leía ZASCARR_DATA_DIR/HOST_DOWNLOADS_DIR/
# HOST_AMULE_INCOMING_DIR del .env — "${ZASCARR_DATA_DIR:?}" dependía por
# completo de que ALGUIEN lo hubiera exportado a mano en la shell antes de
# llamar al script; en una instalación real (solo el .env, nunca exportado)
# --purge habría abortado con "parameter null or not set" en vez de borrar
# nada. Se leen aquí igual que ya se leía HOST_LIBRARY_DIR (grep+cut, sin
# tocar ni depender de la app Python), con los mismos valores por defecto
# que ya usa docker-compose.yml si el .env no los trae.
LIBRARY_DIR=""
DOWNLOADS_DIR=""
AMULE_DIR=""
DATA_DIR="${ZASCARR_DATA_DIR:-}"
if [[ -f "${ENV_FILE}" ]]; then
    LIBRARY_DIR="$(grep -m1 '^HOST_LIBRARY_DIR=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)"
    DOWNLOADS_DIR="$(grep -m1 '^HOST_DOWNLOADS_DIR=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)"
    AMULE_DIR="$(grep -m1 '^HOST_AMULE_INCOMING_DIR=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)"
    if [[ -z "${DATA_DIR}" ]]; then
        DATA_DIR="$(grep -m1 '^ZASCARR_DATA_DIR=' "${ENV_FILE}" 2>/dev/null | cut -d= -f2- || true)"
    fi
else
    warn "No encuentro ${ENV_FILE} — sigo sin él (los contenedores igualmente se pueden parar)."
fi
DOWNLOADS_DIR="${DOWNLOADS_DIR:-/media/data/downloads}"
AMULE_DIR="${AMULE_DIR:-/media/data/aMule/Incoming}"
DATA_DIR="${DATA_DIR:-/var/lib/zascarr}"

# ── A4: validación de rutas antes de --purge (revisión de PR, 2026-09-26) ──
# "${VAR:?}" solo protege contra una variable VACÍA, no contra una ruta
# PELIGROSA — la raíz, una carpeta del sistema, o la propia biblioteca/
# descargas por una mala edición manual del .env. Se resuelve la ruta REAL
# (symlinks, "..", relativas) y se rechazan los casos obvios ANTES de
# construir ningún "rm -rf", nunca confiando en que "eso no va a pasar".
resolver_ruta() {
    # readlink -f resuelve todo lo que pueda aunque el destino final no
    # exista todavía (mismo idioma que _comun.sh ya usa para el symlink de
    # .env) — hace falta para detectar solapamientos incluso contra una
    # carpeta que el usuario nunca llegó a crear.
    readlink -f -- "$1" 2>/dev/null || printf '%s' "$1"
}

RUTAS_SISTEMA_PROHIBIDAS=(/ /root /home /etc /var /usr /bin /sbin /boot /proc /sys /dev /lib /lib64 /opt /tmp)

es_ruta_del_sistema() {
    local candidata="$1" prohibida
    for prohibida in "${RUTAS_SISTEMA_PROHIBIDAS[@]}"; do
        [[ "${candidata}" == "${prohibida}" ]] && return 0
    done
    return 1
}

# ¿"$1" es la misma ruta que "$2", o una está dentro de la otra? Cualquiera
# de los dos sentidos es peligroso: si ZASCARR_DATA_DIR quedara dentro de
# la biblioteca, o la biblioteca dentro de ZASCARR_DATA_DIR, un "rm -rf" de
# subcarpetas con nombre fijo (postgres/redis/covers/vpn-state) podría
# coincidir con carpetas reales del coleccionista.
se_solapan() {
    local a="$1" b="$2"
    [[ -z "${a}" || -z "${b}" ]] && return 1
    [[ "${a}" == "${b}" ]] && return 0
    [[ "${a}" == "${b}/"* ]] && return 0
    [[ "${b}" == "${a}/"* ]] && return 0
    return 1
}

RESOLVED_DATA="$(resolver_ruta "${DATA_DIR}")"
RESOLVED_LIBRARY="$(resolver_ruta "${LIBRARY_DIR}")"
RESOLVED_DOWNLOADS="$(resolver_ruta "${DOWNLOADS_DIR}")"
RESOLVED_AMULE="$(resolver_ruta "${AMULE_DIR}")"

if $PURGE; then
    es_ruta_del_sistema "${RESOLVED_DATA}" && die \
        "ZASCARR_DATA_DIR resuelve a '${RESOLVED_DATA}', una carpeta del sistema — me niego a tocar ahí. Revisa ZASCARR_DATA_DIR en ${ENV_FILE}."
    if se_solapan "${RESOLVED_DATA}" "${RESOLVED_LIBRARY}"; then
        die "ZASCARR_DATA_DIR ('${RESOLVED_DATA}') se solapa con tu biblioteca ('${RESOLVED_LIBRARY}') — me niego a borrar ahí. Revisa HOST_LIBRARY_DIR/ZASCARR_DATA_DIR en ${ENV_FILE}."
    fi
    if se_solapan "${RESOLVED_DATA}" "${RESOLVED_DOWNLOADS}"; then
        die "ZASCARR_DATA_DIR ('${RESOLVED_DATA}') se solapa con tus descargas ('${RESOLVED_DOWNLOADS}') — me niego a borrar ahí. Revisa HOST_DOWNLOADS_DIR/ZASCARR_DATA_DIR en ${ENV_FILE}."
    fi
    if se_solapan "${RESOLVED_DATA}" "${RESOLVED_AMULE}"; then
        die "ZASCARR_DATA_DIR ('${RESOLVED_DATA}') se solapa con la carpeta de aMule ('${RESOLVED_AMULE}') — me niego a borrar ahí. Revisa HOST_AMULE_INCOMING_DIR/ZASCARR_DATA_DIR en ${ENV_FILE}."
    fi
fi

# ── Qué va a pasar, ANTES de tocar nada ─────────────────────────────────────
echo "Esto va a hacer:"
echo "  - Parar y borrar los contenedores de ZascArr (zascarr-orquestador, zascarr-db, zascarr-cache)."
echo "  - Borrar la red interna y la imagen que este repo construyó."
echo "    (las imágenes oficiales de postgres/redis NO se tocan)"
if $PURGE; then
    echo "  - Borrar también los datos de la app en ${RESOLVED_DATA} (catálogo, wishlist, ajustes, portadas)."
    if [[ -f "${ENV_FILE}" ]]; then
        echo "  - Borrar también ${ENV_FILE} (la próxima instalación repetirá el asistente)."
    fi
else
    echo "  - CONSERVAR ${RESOLVED_DATA} (catálogo, wishlist, ajustes, portadas)."
    [[ -f "${ENV_FILE}" ]] && echo "  - CONSERVAR ${ENV_FILE}."
fi
echo ""
if [[ -n "${RESOLVED_LIBRARY}" ]]; then
    echo "  Tu biblioteca (${RESOLVED_LIBRARY}) NUNCA se toca, con o sin --purge."
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

PURGE_DATA_OK=true
PURGE_ENV_OK=true
if $PURGE; then
    info "Borrando datos de la app en ${RESOLVED_DATA}..."
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
    # accidente, sobre la ruta ya RESUELTA y VALIDADA arriba, no la cadena
    # cruda del .env.
    docker run --rm -v "${RESOLVED_DATA:?}:/purgar" postgres:15-alpine \
        sh -c 'rm -rf /purgar/postgres /purgar/redis /purgar/covers /purgar/vpn-state' \
        || true  # el veredicto real es la comprobación de abajo, no el código de salida

    # Revisión de PR (2026-09-26): un código de salida 0 no demuestra que
    # de verdad se borró — se comprueba cada subcarpeta desde el HOST tras
    # el intento. Listar la entrada en ZASCARR_DATA_DIR no necesita
    # permisos sobre EL CONTENIDO de "postgres" (propiedad de otro usuario
    # dentro del contenedor), solo sobre su carpeta padre, de la que el
    # usuario del host sí es dueño.
    RESTOS=()
    for sub in postgres redis covers vpn-state; do
        [[ -e "${RESOLVED_DATA}/${sub}" ]] && RESTOS+=("${sub}")
    done
    if [[ "${#RESTOS[@]}" -eq 0 ]]; then
        success "Datos de la app borrados: ${RESOLVED_DATA}"
    else
        PURGE_DATA_OK=false
        warn "No se borró del todo ${RESOLVED_DATA} — sigue ahí: ${RESTOS[*]} (revisa permisos). Bórralo a mano:
    sudo rm -rf ${RESOLVED_DATA}/{${RESTOS[*]// /,}}"
    fi

    if [[ -f "${ENV_FILE}" ]]; then
        info "Borrando ${ENV_FILE}..."
        rm -f "${ENV_FILE}" 2>/dev/null || true
        if [[ -f "${ENV_FILE}" ]]; then
            PURGE_ENV_OK=false
            warn "No pude borrar ${ENV_FILE} (revisa permisos). Bórralo a mano: rm -f ${ENV_FILE}"
        else
            success ".env borrado."
        fi
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

# Revisión de PR (2026-09-26): el titular final ya no da un "completada"
# genérico si el --purge se quedó a medias — PURGE_DATA_OK/PURGE_ENV_OK
# reflejan la comprobación real de arriba, no el código de salida a ciegas.
PURGE_TOTAL_OK=true
$PURGE && { $PURGE_DATA_OK || PURGE_TOTAL_OK=false; }
$PURGE && { $PURGE_ENV_OK || PURGE_TOTAL_OK=false; }

echo -e "\n${B}====================================${N}"
if $PURGE_TOTAL_OK; then
    echo -e "${G}${B}  Desinstalación completada${N}"
else
    echo -e "${Y}${B}  Desinstalación completada con avisos${N}"
fi
echo -e "${B}====================================${N}\n"
echo "  Se ha quedado en el disco, intacto:"
if [[ -n "${LIBRARY_DIR}" ]]; then
    echo "    - Tu biblioteca: ${LIBRARY_DIR}"
else
    echo "    - Tu biblioteca (la ruta que le hubieras dado)."
fi
if ! $PURGE; then
    echo "    - Los datos de la app: ${RESOLVED_DATA}"
    [[ -f "${ENV_FILE}" ]] && echo "    - Tu configuración: ${ENV_FILE}"
    echo ""
    echo "  Para reinstalar sin perder nada de esto, clona el repo de nuevo en"
    echo "  ${ZASCARR_ROOT}/zascarr y ejecuta bootstrap.sh — reconocerá el .env que ya tienes."
elif $PURGE_TOTAL_OK; then
    echo ""
    echo "  Los datos de la app y la configuración se han borrado también."
else
    echo ""
    echo "  Aviso: el purgado no terminó limpio, revisa los mensajes de arriba."
    $PURGE_DATA_OK || echo "    - Quedan restos en ${RESOLVED_DATA} (detalle arriba)."
    $PURGE_ENV_OK  || echo "    - ${ENV_FILE} sigue ahí."
fi
echo "  El código en ${REPO_DIR} sigue ahí; bórralo a mano si quieres:"
echo "    rm -rf ${REPO_DIR}"
echo ""
