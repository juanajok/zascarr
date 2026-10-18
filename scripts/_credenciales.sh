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

# Deja el `.env` en 600 (y de root si somos root). Silenciosa; el aviso, si
# procede, lo da quien llama. `chmod` sigue el enlace simbólico si lo hubiera.
proteger_env() {
    local fichero="$1"
    [[ -f "${fichero}" ]] || return 1
    chmod 600 "${fichero}" || return 1
    if [[ "${EUID}" -eq 0 ]]; then
        chown 0:0 "${fichero}" 2>/dev/null || true
    fi
}

# Copia la plantilla al `.env` con la máscara 077: el fichero NACE cerrado, sin
# un instante en que cualquiera pueda abrirlo. No pisa un `.env` existente.
crear_env_protegido() {
    local origen="$1" destino="$2"
    [[ -e "${destino}" ]] && return 1
    ( umask 077 && cp -- "${origen}" "${destino}" ) || return 1
    proteger_env "${destino}"
}

# Pone (o añade) una clave en el `.env`. Idempotente. Escapa `\` y `&` para sed
# y `#` (el delimitador elegido): M7 cubría «/media/Juan & María», pero un `#`
# en el valor rompía el `sed` (error latente que estas pruebas destaparon).
# `sed -i` reescribe el fichero, así que después se vuelve a cerrar.
env_poner() {
    local fichero="$1" clave="$2" valor="$3" escapado
    escapado="${valor//\\/\\\\}"
    escapado="${escapado//&/\\&}"
    escapado="${escapado//#/\\#}"
    if grep -q "^${clave}=" "${fichero}" 2>/dev/null; then
        sed -i "s#^${clave}=.*#${clave}=${escapado}#" "${fichero}" || return 1
    else
        echo "${clave}=${valor}" >> "${fichero}" || return 1
    fi
    proteger_env "${fichero}"
}

# ¿Hay ya una base de datos creada? Postgres escribe PG_VERSION al inicializarla;
# `bootstrap.sh` crea la carpeta vacía antes, y una carpeta vacía no cuenta.
base_de_datos_creada() {
    local datos="$1"
    [[ -e "${datos}/postgres/PG_VERSION" ]]
}

# Punto de entrada del instalador. Códigos: 0 correcto; sale con `die` si no se
# puede continuar sin inventar una contraseña.
preparar_credenciales() {
    local fichero="$1" datos="$2" actual modo nueva
    [[ -f "${fichero}" ]] || die "No encuentro ${fichero}. Vuelve a ejecutar el instalador."

    modo="$(stat -c %a "${fichero}" 2>/dev/null || echo "?")"
    actual="$(env_leer "${fichero}" DB_PASSWORD)"

    if credencial_es_marcador "${actual}"; then
        if base_de_datos_creada "${datos}"; then
            proteger_env "${fichero}" || true
            die "Ya hay una base de datos creada en ${datos}/postgres, pero DB_PASSWORD no está
  rellenada en ${fichero}. No invento una contraseña nueva: no abriría esa base y
  ZascArr se quedaría sin acceso a tus datos.
  Pon en DB_PASSWORD la contraseña con la que se creó (la que usabas antes) y
  vuelve a ejecutar el instalador. No he tocado nada."
        fi
        nueva="$(generar_contrasena)" || die \
            "No he podido generar una contraseña (no leo /dev/urandom). No he tocado nada."
        env_poner "${fichero}" DB_PASSWORD "${nueva}" || die \
            "No he podido guardar la contraseña de la base de datos en ${fichero}."
        info "He generado una contraseña para la base de datos y la he guardado en ${fichero}. No tienes que apuntarla: ZascArr la usa solo."
    else
        info "Se conserva la contraseña de la base de datos que ya tenías en ${fichero}."
    fi

    proteger_env "${fichero}" || die "No he podido proteger ${fichero}."
    if [[ "${modo}" != "600" ]]; then
        warn "${fichero} tenía permisos ${modo} (legible por otras cuentas del equipo); ahora es 600: solo el administrador lo lee."
    fi
    success ".env listo (permisos 600)"
}
