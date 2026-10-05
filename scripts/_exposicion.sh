#!/usr/bin/env bash
# =============================================================================
# _exposicion.sh — A11: elegir si ZascArr se abre a la red, y con qué condiciones.
#
# NO se ejecuta solo: se carga con `source`. Las funciones de abajo no escriben
# ni el `.env` ni nada del disco; quien decide y escribe es `bootstrap.sh`.
#
# Postura (ADR 0004, `docs/adr/0004-exposicion-de-red.md`; ficha
# `docs/design/benchmark-A11-exposicion.md`): por defecto solo esta máquina. Abrir
# es una decisión explícita, y las dos opciones que abren EXIGEN contraseña.
#
#   1) Solo esta máquina        -> ZASCARR_BIND_ADDRESS=127.0.0.1   (por defecto)
#   2) Mi red local (LAN)       -> ZASCARR_BIND_ADDRESS=0.0.0.0     + contraseña
#   3) Detrás de un proxy       -> 127.0.0.1 + BASE_URL=https://…   + contraseña
#
# La 3 mantiene el puerto en localhost porque lo expuesto es el proxy (que corre
# en la misma máquina). Este instalador NO instala ni configura el proxy ni el TLS.
# =============================================================================

# Mismo mínimo que `LONGITUD_MINIMA` en src/zascarr/services/seguridad.py. Se repite
# aquí solo para no fallar tarde (la contraseña se pide al principio y se aplica
# después de migrar). La app sigue siendo la que decide; `tests/test_exposicion.py`
# comprueba que las dos cifras son la misma.
LONGITUD_MINIMA_CONTRASENA=12

# exposicion_a_bind OPCION
#   Imprime la dirección en la que el equipo publica el puerto de la interfaz.
#   Devuelve 1 si la opción no es 1, 2 ni 3.
exposicion_a_bind() {
    case "${1:-}" in
        1|3) echo "127.0.0.1" ;;
        2)   echo "0.0.0.0" ;;
        *)   return 1 ;;
    esac
}

# exposicion_actual BIND BASE_URL
#   Qué opción describe la configuración que ya hay (para ofrecerla por defecto
#   al volver a ejecutar el instalador). Ante la duda, 1: nunca se propone abrir.
exposicion_actual() {
    local bind="${1:-}" base_url="${2:-}"
    bind="${bind//[\[\] ]/}"
    case "${bind,,}" in
        ""|127.0.0.1|localhost|::1)
            if url_publica_valida "${base_url}"; then
                local host="${base_url#https://}"
                host="${host%%[/:]*}"
                case "${host,,}" in
                    localhost|127.0.0.1) echo 1 ;;
                    *) echo 3 ;;
                esac
            else
                echo 1
            fi
            ;;
        *) echo 2 ;;
    esac
}

# url_publica_valida URL
#   `https://dominio[:puerto]` y NADA más: sin ruta (ZascArr no está probado bajo un
#   prefijo), puerto 1–65535, IPv4 solo si es una de verdad, sin IPv6. Solo https: con
#   http el proxy no haría de frontera segura. Misma regla que `url_publica_valida`
#   en src/zascarr/services/seguridad.py (una prueba compara las dos con los mismos casos).
url_publica_valida() {
    local url="${1:-}" host puerto etiqueta ultima
    local -a etiquetas
    [[ "${url}" =~ ^https://([^/:@[:space:]]+)(:([0-9]{1,5}))?$ ]] || return 1
    host="${BASH_REMATCH[1]}"
    puerto="${BASH_REMATCH[3]}"
    if [[ -n "${puerto}" ]] && (( 10#${puerto} < 1 || 10#${puerto} > 65535 )); then
        return 1
    fi
    (( ${#host} <= 253 )) || return 1
    # `read -ra` se come un punto final y los vacíos del medio: se descartan antes.
    [[ "${host}" == .* || "${host}" == *. || "${host}" == *..* ]] && return 1
    IFS=. read -ra etiquetas <<< "${host}"
    for etiqueta in "${etiquetas[@]}"; do
        [[ "${etiqueta}" =~ ^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$ ]] || return 1
    done
    ultima="${etiquetas[${#etiquetas[@]}-1]}"
    if [[ "${ultima}" =~ ^[0-9]+$ ]]; then
        # Parece una IPv4: tiene que serlo de verdad (4 octetos 0–255, sin ceros a la izquierda).
        (( ${#etiquetas[@]} == 4 )) || return 1
        for etiqueta in "${etiquetas[@]}"; do
            [[ "${etiqueta}" =~ ^(0|[1-9][0-9]{0,2})$ ]] || return 1
            (( etiqueta <= 255 )) || return 1
        done
    fi
    return 0
}

# contrasena_suficiente CONTRASENA
#   ¿alcanza la longitud mínima? (en caracteres si la locale es UTF-8; la app
#   vuelve a comprobarla de todos modos).
contrasena_suficiente() {
    local c="${1-}"
    (( ${#c} >= LONGITUD_MINIMA_CONTRASENA ))
}

# interfaz_es_virtual IFACE
#   0 si el nombre es de una interfaz que NO es la red local del equipo: loopback, puentes de
#   contenedores (docker0, br-…, veth…), VPN y túneles (tun, tap, wg, tailscale, zt, ppp) y
#   virtualización (virbr, vmnet, vboxnet, cni, flannel, cali). Una dirección de esas no sirve desde
#   el móvil.
interfaz_es_virtual() {
    case "${1:-}" in
        ""|lo|docker*|br-*|veth*|virbr*|cni*|flannel*|cali*|tun*|tap*|wg*|tailscale*|zt*|ppp*|vmnet*|vboxnet*)
            return 0 ;;
        *) return 1 ;;
    esac
}

# ip_es_privada DIRECCION
#   0 si es una dirección de red local (RFC 1918). Una pública no es «tu red local».
ip_es_privada() {
    [[ "${1:-}" =~ ^(10\.[0-9]+\.[0-9]+\.[0-9]+|192\.168\.[0-9]+\.[0-9]+|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]+\.[0-9]+)$ ]]
}

# ip_de_la_red
#   La dirección de este equipo en la red local, SOLO si se puede ACREDITAR: la ruta por defecto sale
#   por una interfaz de red local (no un puente de Docker ni una VPN) y su dirección es privada.
#   Si no, no imprime nada. La dirección con la que se sale a internet es solo una CANDIDATA: con una
#   VPN como ruta por defecto sería la del túnel. Nunca se toma «la primera» de `hostname -I`, que
#   lista también los puentes de Docker (172.17.0.1).
ip_de_la_red() {
    local ruta dev ip=""
    command -v ip >/dev/null 2>&1 || return 0
    ruta="$(ip -4 route get 1.1.1.1 2>/dev/null)" || return 0
    ip="$(sed -n 's/.* src \([0-9.]*\).*/\1/p' <<< "${ruta}" | head -1)"
    dev="$(sed -n 's/.* dev \([^ ]*\).*/\1/p' <<< "${ruta}" | head -1)"
    if [[ "${ip}" =~ ^[0-9]+(\.[0-9]+){3}$ ]] && ! interfaz_es_virtual "${dev}" && ip_es_privada "${ip}"; then
        echo "${ip}"
    fi
    return 0
}

# direcciones_candidatas
#   «interfaz dirección» por línea: IPv4 privadas de interfaces que no son virtuales. Es lo más que se
#   puede decir sin acreditar cuál es la buena. Vacío si no hay `ip` o no hay ninguna.
direcciones_candidatas() {
    local dev cidr
    command -v ip >/dev/null 2>&1 || return 0
    ip -4 -o addr show scope global 2>/dev/null | awk '{print $2, $4}' | while read -r dev cidr; do
        interfaz_es_virtual "${dev}" && continue
        ip_es_privada "${cidr%%/*}" && echo "${dev} ${cidr%%/*}"
    done
    return 0
}

# linea_url_lan ETIQUETA SANGRIA
#   Imprime cómo entrar desde la red local: la URL si la dirección se acredita; si no, las candidatas
#   (con su interfaz) y la aclaración de que no se ha podido confirmar; si no hay ninguna, el marcador.
linea_url_lan() {
    local etiqueta="${1:-Desde otros dispositivos de tu red}" sangria="${2:-  }" ip cand dev dir
    ip="$(ip_de_la_red)"
    if [[ -n "${ip}" ]]; then
        echo "${sangria}${etiqueta}:  http://${ip}:8000"
        return 0
    fi
    cand="$(direcciones_candidatas)"
    if [[ -n "${cand}" ]]; then
        echo "${sangria}${etiqueta}:  no he podido confirmar cuál es la dirección de este equipo en tu red."
        echo "${sangria}Candidatas (prueba la que responda desde el móvil):"
        while read -r dev dir; do
            [[ -n "${dir}" ]] && echo "${sangria}  http://${dir}:8000   (interfaz ${dev})"
        done <<< "${cand}"
    else
        echo "${sangria}${etiqueta}:  http://<la IP de este equipo>:8000"
        echo "${sangria}No he podido determinar la dirección de este equipo en tu red (mira  ip -4 addr )."
    fi
    return 0
}

# preguntar_exposicion DEFECTO
#   Muestra las tres opciones y deja el resultado en las variables globales
#   EXPOSICION_OPCION, ZASCARR_BIND_ADDRESS y BASE_URL_PUBLICA (esta última solo
#   en la opción 3). Lee de la entrada estándar: quien llama comprueba antes que
#   hay una terminal. Una respuesta no válida cae en la 1: nunca se abre por error.
#   Si la opción 3 no consigue una URL https válida en tres intentos, también cae
#   en la 1.
preguntar_exposicion() {
    local defecto="${1:-1}" ans intento

    echo ""
    echo -e "${B:-}¿Quieres usar ZascArr desde otros dispositivos (móvil, tablet)?${N:-}"
    echo "  1) Solo desde esta máquina (recomendado)"
    echo "  2) Desde mi red local — te pediré una contraseña"
    echo "  3) Detrás de un proxy inverso con dominio y HTTPS — te pediré el dominio y una contraseña"
    if [[ "${defecto}" == "1" ]]; then
        echo "  (Intro lo deja solo en esta máquina.)"
    else
        echo "  (Ahora mismo está: $(exposicion_descripcion "${defecto}"). Intro lo mantiene.)"
    fi
    read -rp "Elige 1, 2 o 3 [${defecto}]: " ans || true
    ans="${ans:-${defecto}}"

    EXPOSICION_OPCION=1
    BASE_URL_PUBLICA=""
    case "${ans}" in
        1|2|3) EXPOSICION_OPCION="${ans}" ;;
        *) echo "No he entendido '${ans}': lo dejo en «solo esta máquina»." >&2 ;;
    esac

    if [[ "${EXPOSICION_OPCION}" == "3" ]]; then
        local url=""
        for intento in 1 2 3; do
            read -rp "Dirección pública con HTTPS (por ejemplo https://tebeos.midominio.org): " url || true
            url="${url%/}"
            if url_publica_valida "${url}"; then
                BASE_URL_PUBLICA="${url}"
                break
            fi
            echo "  Tiene que empezar por https:// y llevar un dominio. Sin HTTPS el proxy no protege nada." >&2
        done
        if [[ -z "${BASE_URL_PUBLICA}" ]]; then
            echo "No he conseguido una dirección válida: lo dejo en «solo esta máquina»." >&2
            EXPOSICION_OPCION=1
        fi
    fi

    ZASCARR_BIND_ADDRESS="$(exposicion_a_bind "${EXPOSICION_OPCION}")"
}

# pedir_contrasena_acceso
#   Pide la contraseña (sin eco) dos veces y deja el resultado en
#   CONTRASENA_ACCESO. Tres intentos; devuelve 1 si no hay una válida, y entonces
#   quien llama NO debe abrir nada. La contraseña vive solo en esta variable: no se
#   escribe en el `.env` ni en ningún fichero, y no viaja por argumentos.
pedir_contrasena_acceso() {
    local intento a b
    CONTRASENA_ACCESO=""
    for intento in 1 2 3; do
        IFS= read -rsp "Contraseña de acceso (mínimo ${LONGITUD_MINIMA_CONTRASENA} caracteres; mejor una frase larga): " a || true
        echo ""
        if ! contrasena_suficiente "${a}"; then
            echo "  Es demasiado corta: mínimo ${LONGITUD_MINIMA_CONTRASENA} caracteres." >&2
            continue
        fi
        IFS= read -rsp "Repítela: " b || true
        echo ""
        if [[ "${a}" != "${b}" ]]; then
            echo "  No coinciden. Vuelve a intentarlo." >&2
            continue
        fi
        CONTRASENA_ACCESO="${a}"
        return 0
    done
    return 1
}

# exposicion_descripcion OPCION
#   Frase para el instalador cuando no puede preguntar (sin terminal).
exposicion_descripcion() {
    case "${1:-}" in
        2) echo "abierto a tu red local" ;;
        3) echo "detrás de un proxy inverso" ;;
        *) echo "solo esta máquina" ;;
    esac
}

# cli_seguridad ARGS...
#   Ejecuta `python -m zascarr.cli.seguridad` DENTRO de la imagen (en el host no
#   hay Python). `run` no publica puertos, así que no abre nada. Necesita
#   COMPOSE_FILE y ENV_FILE, que define bootstrap.sh.
cli_seguridad() {
    docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" run --rm -T zascarr \
        python -m zascarr.cli.seguridad "$@"
}

# asegurar_contrasena_de_acceso
#   Garantiza que hay una contraseña ANTES de abrir el puerto. Devuelve 0 si la
#   hay (ya estaba, o se acaba de fijar) y 1 en cualquier otro caso — incluida la
#   duda —, y entonces quien llama NO abre nada. Interactivo solo si
#   EXPOSICION_INTERACTIVA=1 (bootstrap.sh lo pone según haya terminal).
#
#   Orden: se llama DESPUÉS de migrar y ANTES de levantar la aplicación, así que
#   no hay ni un instante con el puerto abierto y sin contraseña.
asegurar_contrasena_de_acceso() {
    local rc=0 mantener
    CONTRASENA_ACCESO=""    # siempre definida: bootstrap.sh corre con `set -u`
    # `docker compose run -T` lee la entrada estándar aunque el comando no la use: sin
    # `</dev/null` se llevaría las líneas de la contraseña que llegan después.
    cli_seguridad estado </dev/null >/dev/null 2>&1 || rc=$?
    case "${rc}" in
        0)
            if [[ "${EXPOSICION_INTERACTIVA:-0}" != "1" ]]; then
                return 0
            fi
            read -rp "Ya hay una contraseña de acceso. ¿La mantengo? [S/n]: " mantener || true
            case "${mantener,,}" in
                n|no) ;;
                *) return 0 ;;
            esac
            ;;
        3) ;;
        *)
            echo "No he podido comprobar si ya hay una contraseña (código ${rc})." >&2
            return 1
            ;;
    esac

    if [[ "${EXPOSICION_INTERACTIVA:-0}" != "1" ]]; then
        echo "Abrir a la red exige una contraseña y sin terminal no puedo pedírtela." >&2
        return 1
    fi
    pedir_contrasena_acceso || return 1
    # Por stdin: nunca por argumentos ni por el entorno (quedaría en `ps`).
    if ! printf '%s\n' "${CONTRASENA_ACCESO}" | cli_seguridad fijar-contrasena; then
        CONTRASENA_ACCESO=""
        return 1
    fi
    CONTRASENA_ACCESO=""
    return 0
}

# subred_de_la_red
#   La subred REAL de la interfaz por la que sale este equipo (`ip route`), no una
#   deducción a partir de la IP: sin conocer la máscara, `192.168.1.50` podría estar
#   en un /16, un /23 o un /24. Vacío si no se puede saber — y entonces no se propone
#   ningún comando (mismo criterio que A10: una regla aparentemente precisa pero
#   equivocada es peor que decir «no puedo determinarlo»).
subred_de_la_red() {
    command -v ip >/dev/null 2>&1 || return 0
    local dev subred
    dev="$(ip -4 route get 1.1.1.1 2>/dev/null | sed -n 's/.* dev \([^ ]*\).*/\1/p' | head -1)"
    [[ -n "${dev}" ]] || return 0
    subred="$(ip -4 route show dev "${dev}" scope link 2>/dev/null | awk '{print $1}' | head -1)"
    [[ "${subred}" =~ ^[0-9]+(\.[0-9]+){3}/[0-9]+$ ]] && echo "${subred}"
    return 0
}

# resumen_acceso ESTADO [CONTRASENA]
#   Qué decirle al coleccionista tras ACTUALIZAR sobre cómo se entra. Actualizar NO cambia la
#   exposición: recrea el contenedor con lo que ya hay en el `.env`. ESTADO es lo que informa
#   `estado_de_publicacion` (lo que Docker tiene de verdad); CONTRASENA, si/no/«» (lo que la app aplicaría).
#   Si está abierto y no hay contraseña se avisa con claridad; ante la duda no se afirma nada.
resumen_acceso() {
    local estado="${1:-indeterminada}" contrasena="${2:-}"
    echo "  Cómo se entra (actualizar no lo cambia):"
    case "${estado}" in
        abierta)
            linea_url_lan "Abierto a tu red local" "    "
            case "${contrasena}" in
                si) echo "    Te pedirá la contraseña de acceso." ;;
                no) echo "    ATENCIÓN: no hay contraseña fijada. Ejecuta  bash bootstrap.sh  para fijarla"
                    echo "    (o elige la opción 1 para volver a dejarlo solo en esta máquina)." ;;
                *)  echo "    No he podido comprobar si pide contraseña; ejecuta  bash bootstrap.sh  para verlo." ;;
            esac
            ;;
        local)
            echo "    Solo desde esta máquina (http://127.0.0.1:8000), o a través de tu proxy si lo configuraste."
            echo "    Desde el móvil u otro equipo no responderá aunque escribas la IP de la Pi."
            echo "    Para abrirlo a tu red, ejecuta  bash bootstrap.sh  y elige la opción 2."
            ;;
        *)
            echo "    No he podido comprobarlo ahora. Para verlo o cambiarlo, ejecuta  bash bootstrap.sh."
            ;;
    esac
}

# resumen_exposicion OPCION URL_PUBLICA
#   Qué decirle al coleccionista al terminar, según lo que se haya dejado.
resumen_exposicion() {
    local opcion="${1:-1}" url="${2:-}" subred
    case "${opcion}" in
        2)
            linea_url_lan "Desde otros dispositivos de tu red" "  "
            echo "  Te pedirá la contraseña que acabas de fijar."
            echo "  Importante: NO reenvíes el puerto 8000 en tu router hacia internet."
            if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi "^Status: active"; then
                subred="$(subred_de_la_red)"
                echo "  Tienes ufw activo: puede bloquear la entrada desde el móvil."
                if [[ -n "${subred}" ]]; then
                    echo "  Si no llegas, permite tu red (yo no toco el cortafuegos):"
                    echo "    sudo ufw allow from ${subred} to any port 8000 proto tcp"
                else
                    echo "  No he podido saber tu subred; permite el puerto 8000 desde ella (yo no toco el cortafuegos)."
                fi
            fi
            ;;
        3)
            echo "  Dirección pública:  ${url}"
            echo "  ZascArr sigue escuchando solo en 127.0.0.1:8000: lo que se expone es tu proxy."
            echo "  El proxy y el HTTPS los pones tú. Ejemplo con Caddy (en esta misma máquina):"
            echo ""
            echo "    ${url#https://} {"
            echo "        reverse_proxy 127.0.0.1:8000"
            echo "    }"
            ;;
        *)
            echo "  Solo se puede entrar desde esta máquina. Para usarlo desde el móvil o la"
            echo "  tablet, vuelve a ejecutar este instalador y elige la opción 2."
            ;;
    esac
}

# estado_de_publicacion
#   Imprime UNA palabra sobre el contenedor de la aplicación que ya exista:
#     ausente        no hay contenedor (comprobado: Docker respondió y no está)
#     local          existe y solo publica en localhost
#     abierta        existe y publica fuera de localhost (0.0.0.0, una IP, [::]…)
#     indeterminada  no se ha podido comprobar (Docker no responde, salida ilegible)
#   Se mira lo que Docker tiene configurado de verdad (`docker inspect`), no el `.env`:
#   escribir `127.0.0.1` ahí NO cierra el puerto de un contenedor ya creado. Y un fallo
#   al consultar NO es «cerrado»: el llamador decide, no se reduce a un booleano.
estado_de_publicacion() {
    local existe lineas linea host abierta=0 vistas=0
    existe="$(docker ps -a --filter 'name=^/zascarr-orquestador$' --format '{{.Names}}' 2>/dev/null)" || {
        echo indeterminada; return 0
    }
    if [[ -z "${existe}" ]]; then
        echo ausente; return 0
    fi
    lineas="$(docker inspect --format \
        '{{range $p,$b := .HostConfig.PortBindings}}{{range $b}}host=<{{.HostIp}}>{{"\n"}}{{end}}{{end}}' \
        zascarr-orquestador 2>/dev/null)" || { echo indeterminada; return 0; }
    while IFS= read -r linea; do
        [[ "${linea}" =~ ^host=\<(.*)\>$ ]] || continue
        vistas=$((vistas+1))
        host="${BASH_REMATCH[1]//[\[\]]/}"
        case "${host,,}" in
            127.0.0.1|::1|localhost) ;;
            *) abierta=1 ;;   # incluido el vacío: Docker lo trata como todas las interfaces
        esac
    done <<< "${lineas}"
    if [[ "${abierta}" == 1 ]]; then
        echo abierta
    elif [[ "${vistas}" -gt 0 ]]; then
        echo local
    else
        # Existe pero no se ve ninguna publicación: puede no tener ninguna o no haberse
        # leído bien. Sin dato no se afirma que esté cerrado.
        echo indeterminada
    fi
}

# leer_efectiva
#   Deja en EFECTIVA_EXPOSICION (local|red|proxy), EFECTIVA_CONTRASENA (si|no) y
#   EFECTIVA_BASE_URL lo que la aplicación aplicaría DE VERDAD al arrancar: el `.env`
#   más lo guardado en Ajustes. Una dirección pública guardada antes en Ajustes manda
#   sobre el `.env`; mirar solo el `.env` daría una imagen falsa. Devuelve 1 si no se
#   pudo leer.
leer_efectiva() {
    local salida linea
    EFECTIVA_EXPOSICION=""
    EFECTIVA_CONTRASENA=""
    EFECTIVA_BASE_URL=""
    EFECTIVA_BASE_URL_PUBLICA=""
    salida="$(cli_seguridad efectiva </dev/null 2>/dev/null)" || return 1
    while IFS= read -r linea; do
        case "${linea}" in
            exposicion=*) EFECTIVA_EXPOSICION="${linea#exposicion=}" ;;
            contrasena=*) EFECTIVA_CONTRASENA="${linea#contrasena=}" ;;
            base_url=*)   EFECTIVA_BASE_URL="${linea#base_url=}" ;;
            base_url_publica=*) EFECTIVA_BASE_URL_PUBLICA="${linea#base_url_publica=}" ;;
        esac
    done <<< "${salida}"
    [[ -n "${EFECTIVA_EXPOSICION}" && -n "${EFECTIVA_CONTRASENA}" && -n "${EFECTIVA_BASE_URL_PUBLICA}" ]]
}

# ajustar_base_url OPCION URL
#   Deja la BASE_URL EFECTIVA coherente con la opción elegida. Necesita `set_env_var`
#   (la define bootstrap.sh). El `.env` y Ajustes pueden contradecirse —la de Ajustes
#   manda—, así que el instalador siempre deja UNA sola fuente de verdad: la del `.env`.
#     3) escribe la URL nueva en el `.env` y RETIRA la de Ajustes (proxy A -> proxy B).
#   1|2) si hay una dirección pública efectiva (en el `.env` o en Ajustes) la retira de
#        los dos sitios, para no dejar un proxy fantasma (proxy -> solo esta máquina).
#   Devuelve 1 si no pudo comprobar o retirar algo.
ajustar_base_url() {
    local opcion="${1:-1}" url="${2:-}"
    if [[ "${opcion}" == "3" ]]; then
        set_env_var "BASE_URL" "${url}"
        cli_seguridad retirar-base-url </dev/null >/dev/null 2>&1 || return 1
        return 0
    fi
    leer_efectiva || return 1
    # Se decide con el criterio de la APP (`base_url_publica`): una dirección histórica
    # como `http://…` o con subruta no la acepta el validador de entradas nuevas, pero
    # la app la trata como pública y hay que limpiarla igual.
    if [[ "${EFECTIVA_BASE_URL_PUBLICA}" == "si" ]]; then
        echo "Retiro la dirección pública anterior (${EFECTIVA_BASE_URL}): ya no la usas." >&2
        set_env_var "BASE_URL" ""
        cli_seguridad retirar-base-url </dev/null >/dev/null 2>&1 || return 1
    fi
    return 0
}

# verificar_exposicion_efectiva
#   0 si lo EFECTIVO es seguro: solo esta máquina, o hay contraseña. 1 si no lo es o si
#   no se pudo comprobar. Es la última comprobación antes de arrancar: no sustituye al
#   orden de los pasos, lo respalda mirando el resultado real.
verificar_exposicion_efectiva() {
    leer_efectiva || return 1
    [[ "${EFECTIVA_EXPOSICION}" == "local" || "${EFECTIVA_CONTRASENA}" == "si" ]]
}

# exposicion_a_opcion NIVEL
#   local|red|proxy (lo que informa `leer_efectiva`) -> 1|2|3, la numeración del menú.
exposicion_a_opcion() {
    case "${1:-}" in
        red)   echo 2 ;;
        proxy) echo 3 ;;
        *)     echo 1 ;;
    esac
}
