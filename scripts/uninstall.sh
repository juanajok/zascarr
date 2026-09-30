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
    elif [[ "${valor}" == *[[:space:]]#* ]]; then
        # Comentario en línea SOLO si el '#' va precedido de espacio, como hace
        # Compose: un '#' pegado al valor (`/media/Comics#1`) es parte de la
        # ruta, y truncarlo apuntaría a otra carpeta distinta.
        valor="${valor%%[[:space:]]#*}"
    fi
    valor="${valor#"${valor%%[![:space:]]*}"}"   # sin espacios a la izquierda
    valor="${valor%"${valor##*[![:space:]]}"}"   # sin espacios a la derecha
    printf '%s' "${valor}"
}

# Deja el resultado en VALOR_VAR y el origen en ORIGEN_VAR: "compose"
# (autoridad: es lo que ve la app) o "env" (lector de reserva, incierto). La
# diferencia importa para la red de seguridad de más abajo: con la autoridad, una
# ruta que no existe significa «no había nada»; con la reserva, «no sé qué hay
# ahí». Se usan globales y NO `$( )` porque una sustitución de comando corre en
# un subshell y perdería ORIGEN_VAR.
ORIGEN_VAR=""
VALOR_VAR=""
resolver_var_ruta() {
    # $1 = nombre de la variable/clave (p.ej. HOST_LIBRARY_DIR)
    # $2 = valor por defecto (el mismo que docker-compose.yml declara)
    local nombre="$1" por_defecto="$2" valor=""
    valor="$(printf '%s\n' "$(_entorno_compose)" \
        | grep -m1 "^${nombre}=" | cut -d= -f2- || true)"
    if [[ -n "${valor}" ]]; then
        ORIGEN_VAR="compose"
    else
        valor="$(_valor_del_env "${nombre}" || true)"
        ORIGEN_VAR="env"
    fi
    VALOR_VAR="${valor:-${por_defecto}}"
}

[[ -f "${ENV_FILE}" ]] || warn "No encuentro ${ENV_FILE} — sigo sin él (los contenedores igualmente se pueden parar)."

resolver_var_ruta HOST_LIBRARY_DIR /media/library
LIBRARY_DIR="${VALOR_VAR}"; ORIGEN_LIBRARY="${ORIGEN_VAR}"
resolver_var_ruta HOST_DOWNLOADS_DIR /media/data/downloads
DOWNLOADS_DIR="${VALOR_VAR}"; ORIGEN_DOWNLOADS="${ORIGEN_VAR}"
resolver_var_ruta HOST_AMULE_INCOMING_DIR /media/data/aMule/Incoming
AMULE_DIR="${VALOR_VAR}"; ORIGEN_AMULE="${ORIGEN_VAR}"
resolver_var_ruta ZASCARR_DATA_DIR /var/lib/zascarr
DATA_DIR="${VALOR_VAR}"; ORIGEN_DATA="${ORIGEN_VAR}"

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
# resolver. Fuera de --purge eso NO es motivo para abortar: el script se
# documenta como tolerante (un .env ausente, una instalación a medias) y parar
# los contenedores no necesita la ruta resuelta — se avisa y se sigue mostrando
# la cadena cruda. Dentro de --purge sí se falla cerrado: ahí la ruta es lo que
# se va a borrar.
resolver_para_mostrar() {
    # $1 = etiqueta, $2 = valor crudo → deja la resuelta en RESUELTA
    local etiqueta="$1" valor="$2" salida
    # `2>&1` a propósito: en éxito `resolver_ruta` imprime la ruta por stdout y
    # en fallo el motivo por stderr, así que la misma variable sirve para las dos.
    if salida="$(resolver_ruta "${valor}" 2>&1)"; then
        RESUELTA="${salida}"
        return 0
    fi
    if $PURGE; then
        die "No pude resolver ${etiqueta} ('${valor}'): ${salida} — me niego a hacer --purge sin saber qué voy a tocar."
    fi
    warn "No pude resolver ${etiqueta} ('${valor}'): ${salida} — sigo sin resolverla (solo la muestro)."
    RESUELTA="${valor}"
}

resolver_para_mostrar "ZASCARR_DATA_DIR" "${DATA_DIR}"; RESOLVED_DATA="${RESUELTA}"
resolver_para_mostrar "HOST_LIBRARY_DIR" "${LIBRARY_DIR}"; RESOLVED_LIBRARY="${RESUELTA}"
resolver_para_mostrar "HOST_DOWNLOADS_DIR" "${DOWNLOADS_DIR}"; RESOLVED_DOWNLOADS="${RESUELTA}"
resolver_para_mostrar "HOST_AMULE_INCOMING_DIR" "${AMULE_DIR}"; RESOLVED_AMULE="${RESUELTA}"

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
    # carpeta que exista, NO se purga nada. Distingue el ORIGEN del valor:
    #   - resuelto por Compose (autoridad, es lo que ve la app): que no exista
    #     significa «no había nada que purgar» → se avisa y se sigue con el
    #     resto de la desinstalación (idempotencia: si ya lo borraste a mano, el
    #     desinstalador tiene que poder terminar).
    #   - resuelto por el lector de reserva (incierto): aquí sí se falla
    #     cerrado, porque no se sabe qué hay en esa ruta.
    PURGE_SIN_DATOS=false
    if [[ ! -d "${RESOLVED_DATA}" ]]; then
        if [[ "${ORIGEN_DATA}" == "compose" ]]; then
            warn "ZASCARR_DATA_DIR ('${RESOLVED_DATA}') no existe: no había nada que purgar."
            PURGE_SIN_DATOS=true
        else
            die "ZASCARR_DATA_DIR resuelve a '${RESOLVED_DATA}' (leído del .env, sin poder confirmarlo con Docker), que no es una carpeta existente — me niego a hacer --purge. Revisa ZASCARR_DATA_DIR en ${ENV_FILE}."
        fi
    fi

    # `motivo_solapamiento` (de _rutas.sh): misma ruta, mismo inodo por bind
    # mount, o anidamiento por componentes.
    if ! $PURGE_SIN_DATOS; then
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
else
    PURGE_SIN_DATOS=false
fi

# ── Qué va a pasar, ANTES de tocar nada ─────────────────────────────────────
echo "Esto va a hacer:"
echo "  - Parar y borrar los contenedores de ZascArr (zascarr-orquestador, zascarr-db, zascarr-cache)."
echo "  - Borrar la red interna y la imagen que este repo construyó."
echo "    (las imágenes oficiales de postgres/redis NO se tocan)"
if $PURGE; then
    if $PURGE_SIN_DATOS; then
        echo "  - No hay datos de la app que borrar en ${RESOLVED_DATA} (no existe)."
    else
        echo "  - Borrar también los datos de la app en ${RESOLVED_DATA} (catálogo, wishlist, ajustes, portadas)."
    fi
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
if $PURGE && $PURGE_SIN_DATOS; then
    # Primer estado de la ficha: la autoridad (Compose) dice dónde están los
    # datos y esa carpeta no existe → no había nada que purgar. Se sigue con el
    # resto (el .env), en vez de dejar la desinstalación a medias.
    info "No había datos de la app que borrar en ${RESOLVED_DATA}."
fi
if $PURGE && ! $PURGE_SIN_DATOS; then
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
    # La imagen sale de Compose (`config --images`), no del texto del YAML: así
    # se resuelve aunque esté entrecomillada o venga de `${POSTGRES_IMAGE:-…}`
    # (un `docker run` con la cadena sin interpolar fallaría sin activar la
    # reserva, porque no estaría vacía). Se descarta cualquier valor con '$'.
    IMAGEN_PG="$("${COMPOSE[@]}" config --images 2>/dev/null | grep -m1 -i 'postgres' || true)"
    IMAGEN_PG="${IMAGEN_PG%\"}"; IMAGEN_PG="${IMAGEN_PG#\"}"
    if [[ -z "${IMAGEN_PG}" || "${IMAGEN_PG}" == *'$'* ]]; then
        IMAGEN_PG="postgres:15-alpine"   # reserva explícita
    fi
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
fi

# El .env se borra con --purge siempre, haya o no datos que purgar: si no,
# una ejecución sobre una instalación ya a medias no podría terminar nunca.
if $PURGE; then
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
