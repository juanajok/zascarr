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
# A9: `resolver_ruta` (con detección de symlinks rotos y comprobación
# fichero/carpeta) y `motivo_solapamiento` (misma ruta, mismo inodo por bind
# mount, anidamiento por componentes). No se reimplementan aquí.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_rutas.sh"

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
# nada.
#
# Segundo bug real, encontrado en revisión de PR (2026-09-26): la primera
# versión de este endurecimiento seguía sin aplicarle a HOST_LIBRARY_DIR
# el mismo valor por defecto que docker-compose.yml (/media/library) — con
# un .env ausente o sin esa clave, RESOLVED_LIBRARY quedaba vacío y
# la comprobación de solapamiento se saltaba la protección de biblioteca en
# silencio, justo el estado que este script dice admitir. Ahora las CUATRO rutas
# (ZASCARR_DATA_DIR y las tres HOST_*) se resuelven con la MISMA
# precedencia que usa "docker compose" al interpolar el compose file:
# variable YA exportada en la shell (puede contradecir al .env, y sigue
# ganando ella) > valor del .env > valor por defecto del propio
# docker-compose.yml. Nunca una ruta a medio determinar.
#
# En vez de reimplementar el parser de Compose (comillas, comentario en línea,
# `export`, CRLF… cada uno daba una ruta distinta a la que ve la app), se le
# pregunta a Compose: `config --environment` imprime el entorno ya resuelto, con
# la misma precedencia que la interpolación. El lector propio queda de RESERVA
# para cuando Compose no pueda responder (un .env a medias o Docker caído).
_ENTORNO_COMPOSE=""

_entorno_compose() {
    if [[ -z "${_ENTORNO_COMPOSE}" ]]; then
        _ENTORNO_COMPOSE="$("${COMPOSE[@]}" config --environment 2>/dev/null || true)"
    fi
    printf '%s' "${_ENTORNO_COMPOSE}"
}

# Reserva: interpreta el .env a mano para los cuatro casos que Compose sí
# resuelve — comillas envolventes, comentario en línea (solo sin comillas),
# `export` y finales CRLF.
_valor_del_env() {
    local nombre="$1" linea valor
    [[ -f "${ENV_FILE}" ]] || return 1
    linea="$(grep -m1 -E "^[[:space:]]*(export[[:space:]]+)?${nombre}=" "${ENV_FILE}" || true)"
    [[ -n "${linea}" ]] || return 1
    valor="${linea#*"${nombre}"=}"
    valor="${valor%$'\r'}"                    # CRLF
    if [[ "${valor}" == \"* ]]; then
        valor="${valor#\"}"; valor="${valor%%\"*}"
    elif [[ "${valor}" == \'* ]]; then
        valor="${valor#\'}"; valor="${valor%%\'*}"
    else
        valor="${valor%%#*}"                  # comentario en línea
    fi
    valor="${valor#"${valor%%[![:space:]]*}"}"   # sin espacios a la izquierda
    valor="${valor%"${valor##*[![:space:]]}"}"   # sin espacios a la derecha
    printf '%s' "${valor}"
}

resolver_var_ruta() {
    # $1 = nombre de la variable/clave (p.ej. HOST_LIBRARY_DIR)
    # $2 = valor por defecto (el mismo que docker-compose.yml declara)
    local nombre="$1" por_defecto="$2" valor=""
    valor="$(printf '%s\n' "$(_entorno_compose)" \
        | grep -m1 "^${nombre}=" | cut -d= -f2- || true)"
    if [[ -z "${valor}" ]]; then
        valor="$(_valor_del_env "${nombre}" || true)"
    fi
    printf '%s' "${valor:-${por_defecto}}"
}

[[ -f "${ENV_FILE}" ]] || warn "No encuentro ${ENV_FILE} — sigo sin él (los contenedores igualmente se pueden parar)."

LIBRARY_DIR="$(resolver_var_ruta HOST_LIBRARY_DIR /media/library)"
DOWNLOADS_DIR="$(resolver_var_ruta HOST_DOWNLOADS_DIR /media/data/downloads)"
AMULE_DIR="$(resolver_var_ruta HOST_AMULE_INCOMING_DIR /media/data/aMule/Incoming)"
DATA_DIR="$(resolver_var_ruta ZASCARR_DATA_DIR /var/lib/zascarr)"

# ── A4: validación de rutas antes de --purge (revisión de PR, 2026-09-26) ──
# "${VAR:?}" solo protege contra una variable VACÍA, no contra una ruta
# PELIGROSA — la raíz, una carpeta del sistema, o la propia biblioteca/
# descargas por una mala edición manual del .env. Se resuelve la ruta REAL
# (symlinks, "..", relativas) y se rechazan los casos obvios ANTES de
# construir ningún "rm -rf", nunca confiando en que "eso no va a pasar".
#
# La resolución y el solapamiento vienen de `_rutas.sh` (A9): detecta symlinks
# rotos componente a componente, comprueba que el ancestro existente sea carpeta,
# y ve el mismo inodo por bind mount además del anidamiento por componentes. La
# versión local anterior (`readlink -f` + prefijo de texto) no veía nada de eso.

RUTAS_SISTEMA_PROHIBIDAS=(/ /root /home /etc /var /usr /bin /sbin /boot /proc /sys /dev /lib /lib64 /opt /tmp)

es_ruta_del_sistema() {
    local candidata="$1" prohibida
    for prohibida in "${RUTAS_SISTEMA_PROHIBIDAS[@]}"; do
        [[ "${candidata}" == "${prohibida}" ]] && return 0
    done
    return 1
}

# `resolver_ruta` (de _rutas.sh) devuelve 1 con el motivo por stderr si no puede
# resolver: aquí se falla cerrado, no se sigue con una ruta a medias.
RESOLVED_DATA="$(resolver_ruta "${DATA_DIR}")" || die \
    "No pude resolver ZASCARR_DATA_DIR ('${DATA_DIR}') — me niego a seguir sin saber qué voy a borrar."
RESOLVED_LIBRARY="$(resolver_ruta "${LIBRARY_DIR}")" || die \
    "No pude resolver HOST_LIBRARY_DIR ('${LIBRARY_DIR}') — me niego a seguir sin poder comprobar que no se solapa con tu biblioteca."
RESOLVED_DOWNLOADS="$(resolver_ruta "${DOWNLOADS_DIR}")" || die \
    "No pude resolver HOST_DOWNLOADS_DIR ('${DOWNLOADS_DIR}') — me niego a seguir sin poder comprobar que no se solapa con tus descargas."
RESOLVED_AMULE="$(resolver_ruta "${AMULE_DIR}")" || die \
    "No pude resolver HOST_AMULE_INCOMING_DIR ('${AMULE_DIR}') — me niego a seguir sin poder comprobar que no se solapa con la carpeta de aMule."

if $PURGE; then
    # Fallar cerrado, no abierto: con los valores por defecto de arriba
    # ninguna de estas cuatro debería poder quedar vacía nunca — pero si
    # algún cambio futuro rompiera esa garantía, mejor abortar aquí que
    # seguir con una comprobación de solapamiento sobre cadenas vacías.
    [[ -n "${RESOLVED_DATA}" ]] || die \
        "No he podido determinar ZASCARR_DATA_DIR de forma inequívoca — me niego a hacer --purge sin saber qué voy a borrar."
    [[ -n "${RESOLVED_LIBRARY}" ]] || die \
        "No he podido determinar HOST_LIBRARY_DIR de forma inequívoca — me niego a hacer --purge sin poder comprobar que no se solapa con tu biblioteca."
    [[ -n "${RESOLVED_DOWNLOADS}" ]] || die \
        "No he podido determinar HOST_DOWNLOADS_DIR de forma inequívoca — me niego a hacer --purge sin poder comprobar que no se solapa con tus descargas."
    [[ -n "${RESOLVED_AMULE}" ]] || die \
        "No he podido determinar HOST_AMULE_INCOMING_DIR de forma inequívoca — me niego a hacer --purge sin poder comprobar que no se solapa con la carpeta de aMule."

    es_ruta_del_sistema "${RESOLVED_DATA}" && die \
        "ZASCARR_DATA_DIR resuelve a '${RESOLVED_DATA}', una carpeta del sistema — me niego a tocar ahí. Revisa ZASCARR_DATA_DIR en ${ENV_FILE}."

    # Red de seguridad independiente del lector: si la ruta resuelta no es una
    # carpeta que exista, NO se purga nada. Es lo que convierte cualquier
    # desajuste de interpretación del .env (comillas, comentario, export, CRLF,
    # o uno que no se haya previsto) en un aviso claro en vez de un «borrado»
    # en vacío. Si ya lo borraste a mano, tampoco hay nada que purgar.
    if [[ ! -d "${RESOLVED_DATA}" ]]; then
        die "ZASCARR_DATA_DIR resuelve a '${RESOLVED_DATA}', que no es una carpeta existente — me niego a hacer --purge. Si ya borraste esos datos a mano, no hay nada que purgar; si no, revisa ZASCARR_DATA_DIR en ${ENV_FILE}."
    fi

    # `motivo_solapamiento` (de _rutas.sh): misma ruta, mismo inodo por bind
    # mount, o anidamiento por componentes.
    if motivo="$(motivo_solapamiento "${RESOLVED_DATA}" "${RESOLVED_LIBRARY}")"; then
        die "ZASCARR_DATA_DIR ('${RESOLVED_DATA}') y tu biblioteca ('${RESOLVED_LIBRARY}'): ${motivo} — me niego a borrar ahí. Revisa HOST_LIBRARY_DIR/ZASCARR_DATA_DIR en ${ENV_FILE}."
    fi
    if motivo="$(motivo_solapamiento "${RESOLVED_DATA}" "${RESOLVED_DOWNLOADS}")"; then
        die "ZASCARR_DATA_DIR ('${RESOLVED_DATA}') y tus descargas ('${RESOLVED_DOWNLOADS}'): ${motivo} — me niego a borrar ahí. Revisa HOST_DOWNLOADS_DIR/ZASCARR_DATA_DIR en ${ENV_FILE}."
    fi
    if motivo="$(motivo_solapamiento "${RESOLVED_DATA}" "${RESOLVED_AMULE}")"; then
        die "ZASCARR_DATA_DIR ('${RESOLVED_DATA}') y la carpeta de aMule ('${RESOLVED_AMULE}'): ${motivo} — me niego a borrar ahí. Revisa HOST_AMULE_INCOMING_DIR/ZASCARR_DATA_DIR en ${ENV_FILE}."
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
    #
    # La imagen sale del propio docker-compose.yml, no hardcodeada: si el
    # compose salta de versión de Postgres, el desinstalador purga con la misma
    # (y sigue estando en caché). El literal queda solo como reserva.
    IMAGEN_PG="$(awk '/^  postgres:/{f=1; next} f && /image:/{print $2; exit}' "${COMPOSE_FILE}" || true)"
    [[ -n "${IMAGEN_PG}" ]] || IMAGEN_PG="postgres:15-alpine"
    docker run --rm -v "${RESOLVED_DATA:?}:/purgar" "${IMAGEN_PG}" \
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
        # -e sigue symlinks: un enlace colgante (destino ya borrado) da
        # -e falso aunque la propia entrada del enlace siga ahí. -L
        # detecta la entrada exista o no su destino — revisión de PR
        # (2026-09-26).
        if [[ -e "${RESOLVED_DATA}/${sub}" || -L "${RESOLVED_DATA}/${sub}" ]]; then
            RESTOS+=("${sub}")
        fi
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

# Revisión de PR (2026-09-26): un "make uninstall-purge" automatizado (CI,
# un script de aprovisionamiento) solo puede fiarse del código de salida,
# no del color del texto — si el resumen dice "con avisos", la shell tiene
# que estar de acuerdo.
$PURGE_TOTAL_OK || exit 1
