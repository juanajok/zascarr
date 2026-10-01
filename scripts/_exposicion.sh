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
#   `https://host[:puerto][/ruta]`, sin espacios. Solo https: con http el proxy no
#   haría de frontera segura. Misma regla que `url_publica_valida` en
#   src/zascarr/services/seguridad.py (una prueba compara las dos con los mismos casos).
url_publica_valida() {
    local url="${1:-}"
    [[ "${url}" =~ ^https://([A-Za-z0-9._-]+|\[[0-9A-Fa-f:]+\])(:[0-9]+)?(/[^[:space:]]*)?$ ]]
}

# contrasena_suficiente CONTRASENA
#   ¿alcanza la longitud mínima? (en caracteres si la locale es UTF-8; la app
#   vuelve a comprobarla de todos modos).
contrasena_suficiente() {
    local c="${1-}"
    (( ${#c} >= LONGITUD_MINIMA_CONTRASENA ))
}

# ip_de_la_red
#   Primera IPv4 no local de este equipo, para decirle al coleccionista a qué
#   dirección entrar desde el móvil. Vacío si no se puede saber.
ip_de_la_red() {
    local ip=""
    if command -v hostname >/dev/null 2>&1; then
        ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
    fi
    [[ "${ip}" =~ ^[0-9]+(\.[0-9]+){3}$ ]] && echo "${ip}"
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
        read -rsp "Contraseña de acceso (mínimo ${LONGITUD_MINIMA_CONTRASENA} caracteres; mejor una frase larga): " a || true
        echo ""
        if ! contrasena_suficiente "${a}"; then
            echo "  Es demasiado corta: mínimo ${LONGITUD_MINIMA_CONTRASENA} caracteres." >&2
            continue
        fi
        read -rsp "Repítela: " b || true
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
