#!/usr/bin/env bash
# =============================================================================
# _credenciales.sh — la contraseña de la base de datos y la protección del .env.
#
# NO se ejecuta solo: se carga con `source` (bootstrap.sh). Sin efectos al
# cargarse. Quien lo carga define `info`, `success`, `warn` y `die`.
#
# Por qué existe (ensayo M4, candidato 0a591d6, Debian 12 sin terminal):
#
#   1. `bootstrap.sh` copiaba `.env.example` y se negaba a seguir (RC=1) porque
#      `DB_PASSWORD` seguía siendo el marcador `cambia_esto_ahora`: la
#      «instalación de una línea» exigía editar un fichero a mano. Ahora, si
#      la contraseña es el marcador o falta, se GENERA una y se guarda en el
#      `.env`. Una que ya esté puesta no se toca jamás.
#   2. El `.env` se creaba con `cp` y la máscara por defecto: modo 644, legible
#      por cualquier cuenta local (medido con `nobody`). Ahora nace en 600 y
#      vuelve a 600 después de cada modificación.
#
# Tres reglas que no se deshacen sin leer las pruebas (`tests/test_credenciales_env.py`):
#
#   - NUNCA se pisa una contraseña puesta por una persona, aunque sea floja.
#   - NUNCA se inventa una contraseña si ya existe una base de datos creada
#     (`<datos>/postgres/PG_VERSION`): Postgres solo lee `POSTGRES_PASSWORD` al
#     crear la base, así que una contraseña nueva dejaría a la aplicación sin
#     poder entrar. Se explica y se corta sin tocar nada.
#   - El valor generado NO sale por la salida ni se escribe en ningún otro sitio.
#   - Si NO se consigue la protección exigida (propietario root, modo 600, carpeta que
#     no pueda cambiar otra cuenta), se corta ANTES de escribir ningún secreto y no
#     se anuncia protección alguna. Nada de «|| true» sobre un `chown` o un `chmod`.
#
# Qué es «protegido» (revisión de #237): 600 no basta. El dueño de la CARPETA que
# contiene el .env puede borrarlo y poner otro, o un enlace, aunque el fichero sea de
# root. Por eso la carpeta (y el camino hasta ella) tiene que ser de root y no
# escribible por otros, y el .env tiene que ser un fichero normal, no un enlace.
# =============================================================================

# Valor de la plantilla `.env.example`. Es un marcador, no una contraseña.
CREDENCIAL_MARCADOR="cambia_esto_ahora"

# 24 bytes del sistema en hexadecimal (192 bits, 48 caracteres). Hexadecimal a
# propósito: la contraseña viaja dentro de `DATABASE_URL` y pasa por `sed`, así
# que no puede llevar `@ : / # & \ %`. `od -N` lee un número fijo de bytes:
# sin tuberías con `head`, que bajo `pipefail` darían SIGPIPE y abortarían.
generar_contrasena() {
    local valor
    valor="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')" || return 1
    [[ ${#valor} -ge 32 ]] || return 1
    printf '%s\n' "${valor}"
}

# ¿Es un valor sin rellenar? Vacío, solo espacios, o el marcador EXACTO. Un valor
# cualquiera puesto por una persona NO es marcador: decidir si es «bueno» no es
# cosa del instalador.
credencial_es_marcador() {
    local valor="${1-}"
    valor="${valor//[[:space:]]/}"
    [[ -z "${valor}" || "${valor}" == "${CREDENCIAL_MARCADOR}" ]]
}

# Valor de una clave del `.env` (la primera línea activa; las comentadas no
# cuentan). Solo lectura.
env_leer() {
    local fichero="$1" clave="$2"
    grep -m1 "^${clave}=" "${fichero}" 2>/dev/null | cut -d= -f2- || true
}

# El «administrador» que debe poseer el .env: root. Las pruebas lo cambian (no son
# root) y simulan serlo redefiniendo `_es_root`, porque `EUID` es de solo lectura.
CREDENCIAL_UID_ESPERADO=0
# Hasta dónde se miran los antecesores de la carpeta del .env: vacío = hasta `/` (lo que
# hace el instalador). Las pruebas lo fijan en su carpeta temporal para no depender de los
# permisos de la máquina que las ejecuta (un `$HOME` con grupo escribible las rompería).
CREDENCIAL_CONFIAR_DESDE=""
_es_root() { [[ "${EUID}" -eq 0 ]]; }
_propietario_de() { stat -c %u "$1" 2>/dev/null; }

# Deja el `.env` como fichero normal, 600 y del administrador. FALLA (devuelve 1) si
# no lo consigue: ni se descarta el error de `chown` ni se da por hecho su efecto —se
# comprueba el propietario resultante—. Silenciosa; el aviso lo da quien llama.
proteger_env() {
    local fichero="$1"
    [[ -f "${fichero}" && ! -L "${fichero}" ]] || return 1
    chmod 600 "${fichero}" || return 1
    if _es_root; then
        chown 0:0 "${fichero}" || return 1
    fi
    [[ "$(_propietario_de "${fichero}")" == "${CREDENCIAL_UID_ESPERADO}" ]] || return 1
}

# ¿La ubicación del .env deja que otra cuenta lo sustituya o lo redirija? Imprime el
# motivo y devuelve 0 si es INSEGURA; devuelve 1 (y no imprime nada) si es segura.
# Mira: que no sea un enlace simbólico; que su carpeta sea del administrador y no
# escribible por grupo ni otros; y que ningún antecesor de esa carpeta sea de otra
# cuenta o esté abierto a la escritura (un antecesor con el bit pegajoso, como /tmp,
# no deja renombrar lo que no es tuyo, y vale). Ruta física, sin fiarse de enlaces.
ubicacion_env_insegura() {
    local fichero="$1" uid="${2:-${CREDENCIAL_UID_ESPERADO}}" dir actual modo dueno primero=1
    if [[ -L "${fichero}" ]]; then
        echo "${fichero} es un enlace simbólico: otra cuenta podría apuntarlo a un fichero suyo."
        return 0
    fi
    dir="$(cd -P -- "$(dirname -- "${fichero}")" 2>/dev/null && pwd -P)" || {
        echo "no puedo resolver la carpeta de ${fichero}."
        return 0
    }
    actual="${dir}"
    while :; do
        dueno="$(stat -c %u "${actual}" 2>/dev/null)" || { echo "no puedo leer los permisos de ${actual}."; return 0; }
        modo="$(stat -c %a "${actual}" 2>/dev/null)"
        if (( primero )); then
            if [[ "${dueno}" != "${uid}" ]]; then
                echo "${actual}, que contiene el .env, es propiedad de otra cuenta (uid ${dueno}): podría sustituirlo."
                return 0
            fi
            if (( (8#${modo}) & 8#022 )); then
                echo "${actual}, que contiene el .env, es escribible por otras cuentas (modo ${modo}): podrían sustituirlo."
                return 0
            fi
            primero=0
        else
            [[ -n "${CREDENCIAL_CONFIAR_DESDE}" && "${actual}" == "${CREDENCIAL_CONFIAR_DESDE}" ]] && break
            if [[ "${dueno}" != "${uid}" && "${dueno}" != "0" ]]; then
                echo "${actual} (por encima del .env) es propiedad de otra cuenta (uid ${dueno})."
                return 0
            fi
            if (( (8#${modo}) & 8#022 )) && ! (( (8#${modo}) & 8#1000 )); then
                echo "${actual} (por encima del .env) queda abierto a la escritura de otras cuentas (modo ${modo})."
                return 0
            fi
        fi
        [[ "${actual}" == "/" ]] && break
        actual="$(dirname -- "${actual}")"
    done
    return 1
}

# Cierra la CARPETA que contiene el .env: del administrador y sin escritura para
# grupo ni otros. Solo esa carpeta —nada recursivo—; el repositorio y los datos no se
# tocan. Falla en cerrado.
asegurar_ubicacion_env() {
    local dir
    dir="$(dirname -- "$1")"
    if _es_root; then
        chown 0:0 "${dir}" || return 1
    fi
    [[ "$(_propietario_de "${dir}")" == "${CREDENCIAL_UID_ESPERADO}" ]] || return 1
    chmod go-w "${dir}" || return 1
}

# Copia la plantilla al `.env` con la máscara 077: el fichero NACE cerrado, sin
# un instante en que cualquiera pueda abrirlo. No pisa nada existente, tampoco a
# través de un enlace roto (`-e` es falso para ese caso y `cp` escribiría en su destino).
crear_env_protegido() {
    local origen="$1" destino="$2"
    [[ -e "${destino}" || -L "${destino}" ]] && return 1
    ( umask 077 && cp -- "${origen}" "${destino}" ) || return 1
    proteger_env "${destino}"
}

# Pone (o añade) una clave en el `.env`. Idempotente. Escapa `\`, `&` y `#` (el
# delimitador de sed; M7 cubría «/media/Juan & María» y un `#` rompía el `sed`).
#
# Sin ventana de escritura: primero se cierra el destino (un fichero heredado en 644 no
# vuelve a tener un secreto nuevo dentro), después se escribe en un temporal que NACE
# 600 y del administrador y se RENOMBRA sobre el original. Nada se reescribe en sitio.
env_poner() {
    local fichero="$1" clave="$2" valor="$3" escapado tmp
    proteger_env "${fichero}" || return 1
    escapado="${valor//\\/\\\\}"
    escapado="${escapado//&/\\&}"
    escapado="${escapado//#/\\#}"
    tmp="$( umask 077; mktemp "${fichero}.XXXXXX" )" || return 1
    if proteger_env "${tmp}"; then
        if grep -q "^${clave}=" "${fichero}" 2>/dev/null; then
            sed "s#^${clave}=.*#${clave}=${escapado}#" "${fichero}" > "${tmp}" || { rm -f "${tmp}"; return 1; }
        else
            { cat "${fichero}"; [[ -s "${fichero}" && -n "$(tail -c1 "${fichero}")" ]] && echo
              echo "${clave}=${valor}"; } > "${tmp}" || { rm -f "${tmp}"; return 1; }
        fi
        mv -f "${tmp}" "${fichero}" || { rm -f "${tmp}"; return 1; }
    else
        rm -f "${tmp}"
        return 1
    fi
}

# ¿Hay ya una base de datos creada? Postgres escribe PG_VERSION al inicializarla;
# `bootstrap.sh` crea la carpeta vacía antes, y una carpeta vacía no cuenta.
base_de_datos_creada() {
    local datos="$1"
    [[ -e "${datos}/postgres/PG_VERSION" ]]
}

# Punto de entrada del instalador. Se detiene con `die` (antes de escribir ningún
# secreto) si no puede dejar el .env protegido o si su carpeta no es de fiar.
preparar_credenciales() {
    local fichero="$1" datos="$2" actual modo nueva motivo
    [[ -f "${fichero}" ]] || die "No encuentro ${fichero}. Vuelve a ejecutar el instalador."

    # 1) Lo primero: cerrar el fichero (también uno antiguo en 644) y comprobar el
    #    resultado. Hasta aquí no se ha escrito nada.
    modo="$(stat -c %a "${fichero}" 2>/dev/null || echo "?")"
    proteger_env "${fichero}" || die \
        "No he podido dejar ${fichero} con permisos 600 y propietario root. No sigo: guardaría la contraseña de la base de datos en un fichero que otras cuentas podrían leer. No he escrito nada."
    if motivo="$(ubicacion_env_insegura "${fichero}")"; then
        die "La ubicación de ${fichero} no es segura: ${motivo}
  No sigo: otra cuenta podría sustituir el fichero que contiene la contraseña de la base de datos. No he escrito nada."
    fi

    # 2) La contraseña.
    actual="$(env_leer "${fichero}" DB_PASSWORD)"
    if credencial_es_marcador "${actual}"; then
        if base_de_datos_creada "${datos}"; then
            die "Ya hay una base de datos creada en ${datos}/postgres, pero DB_PASSWORD no está
  rellenada en ${fichero}. No invento una contraseña nueva: no abriría esa base y
  ZascArr se quedaría sin acceso a tus datos.
  Pon en DB_PASSWORD la contraseña con la que se creó (la que usabas antes) y
  vuelve a ejecutar el instalador. No he tocado nada."
        fi
        nueva="$(generar_contrasena)" || die \
            "No he podido generar una contraseña (no leo /dev/urandom). No he tocado nada."
        env_poner "${fichero}" DB_PASSWORD "${nueva}" || die \
            "No he podido guardar la contraseña de la base de datos en ${fichero} con la protección exigida."
        info "He generado una contraseña para la base de datos y la he guardado en ${fichero}. No tienes que apuntarla: ZascArr la usa solo."
    else
        info "Se conserva la contraseña de la base de datos que ya tenías en ${fichero}."
    fi

    # 3) Solo se anuncia lo comprobado.
    if [[ "${modo}" != "600" ]]; then
        warn "${fichero} tenía permisos ${modo} (legible por otras cuentas del equipo); ahora es 600 y del administrador."
    fi
    success ".env listo (permisos 600, solo el administrador lo lee)"
}
