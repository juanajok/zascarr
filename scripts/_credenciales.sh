#!/usr/bin/env bash
# =============================================================================
# _credenciales.sh — credenciales obligatorias del .env: inicializar, validar, escribir y proteger.
#
# NO se ejecuta solo: se carga con `source` (bootstrap.sh, _comun.sh, credenciales.sh). Contrato y matriz de
# identidades: docs/adr/0012-credenciales-del-env.md.
#
# Lo que garantiza (cada punto tiene su prueba en tests/test_credenciales_*.py y tests/escenarios/):
#   · La única credencial obligatoria del .env es DB_PASSWORD. La clave que firma la cookie de sesión NO está en el
#     .env: la app la genera y la guarda en la base de datos la primera vez (RuntimeSettingsService.ensure_secret_key).
#   · Ausente, vacía o de ejemplo (`credencial_invalida`) ⇒ se GENERA una propia, solo si todavía no hay base de datos;
#     si ya la hay, se PARA sin inventar otra (inventarla dejaría la base inaccesible).
#   · Una credencial válida existente no se toca, ni se regenera, ni aparece en pantalla.
#   · Escribir el .env es atómico (temporal 0600 en la misma carpeta + rename): un fallo deja el original intacto y
#     nunca un fichero a medias. No se hacen copias de seguridad del .env (serían más copias de un secreto).
#   · El .env es de root (600) y la carpeta que lo contiene y el repo no son escribibles por el usuario de servicio:
#     proteger el contenido no basta si otro puede borrar o sustituir la ENTRADA del directorio.
#
# Nada de aquí imprime el valor de una credencial: solo estados, longitudes y rutas.
# =============================================================================

if [[ -n "${_ZASCARR_CREDENCIALES_CARGADO:-}" ]]; then
    return 0
fi
_ZASCARR_CREDENCIALES_CARGADO=1

# Valores que nunca valen como contraseña, en minúsculas (se compara sin distinguir mayúsculas):
#   cambia_esto_ahora        el ejemplo de .env.example
#   supersecretpassword123   el valor por defecto que tuvo docker-compose.yml (publicado en el repositorio)
#   changeme                 el clásico
# La MISMA lista vive en docker-compose.yml (servicio `credenciales`) y en zascarr/utils/credenciales.py;
# tests/test_credenciales_lista.py comprueba que las tres coinciden.
CREDENCIALES_CONOCIDAS=(cambia_esto_ahora supersecretpassword123 changeme)

# Carpeta del instalador: únicas entradas que puede tener una carpeta que ZascArr considera SUYA (ver raiz_dedicada).
_CRED_ENTRADAS_PROPIAS=(zascarr .env config)

# env_valor FICHERO CLAVE
#   Valor efectivo de CLAVE como lo lee Docker Compose: gana la ÚLTIMA aparición, se admite `export `, se quitan
#   espacios, el CR de un fichero con fin de línea de Windows, las comillas que rodean el valor y el comentario
#   `# …` de un valor sin comillas. Vacío si no está. Solo lectura.
env_valor() {
    local fichero="$1" clave="$2" linea
    linea="$(grep -E "^[[:space:]]*(export[[:space:]]+)?${clave}=" -- "${fichero}" 2>/dev/null | tail -n 1)" || true
    [[ -n "${linea}" ]] || return 0
    linea="${linea#*=}"
    linea="${linea%$'\r'}"
    linea="${linea#"${linea%%[![:space:]]*}"}"
    linea="${linea%"${linea##*[![:space:]]}"}"
    if [[ ${#linea} -ge 2 && ( ( "${linea:0:1}" == '"' && "${linea: -1}" == '"' ) \
                              || ( "${linea:0:1}" == "'" && "${linea: -1}" == "'" ) ) ]]; then
        linea="${linea:1:${#linea}-2}"
    else
        linea="${linea%% \#*}"
        linea="${linea%"${linea##*[![:space:]]}"}"
    fi
    printf '%s' "${linea}"
}

# credencial_invalida VALOR
#   0 (verdadero) si el valor está vacío, solo son espacios, o es uno de CREDENCIALES_CONOCIDAS (sin distinguir
#   mayúsculas ni comillas). Es la ÚNICA definición de «no vale» en los scripts.
credencial_invalida() {
    local v="${1:-}" c
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    v="${v#[\"\']}"; v="${v%[\"\']}"
    [[ -n "${v}" ]] || return 0
    v="${v,,}"
    for c in "${CREDENCIALES_CONOCIDAS[@]}"; do
        [[ "${v}" == "${c}" ]] && return 0
    done
    return 1
}

# generar_credencial
#   48 caracteres hexadecimales (24 bytes del sistema operativo = 192 bits). Hexadecimal a propósito: va dentro de
#   la URL de conexión (DATABASE_URL) y de un .env sin comillas, y no necesita escapes en ninguno de los dos.
#   No depende de openssl. Sale por la salida estándar: quien llama la guarda, no la muestra.
generar_credencial() {
    local v
    v="$(od -An -N24 -tx1 /dev/urandom 2>/dev/null | tr -d ' \n')" || return 1
    [[ "${v}" =~ ^[0-9a-f]{48}$ ]] || return 1
    printf '%s' "${v}"
}

# env_escribir FICHERO CLAVE VALOR
#   Pone CLAVE=VALOR en el .env (sustituye TODAS sus líneas `CLAVE=…` o añade una). Atómico: se compone un temporal
#   0600 en la MISMA carpeta, se le da el propietario y modo del original y se renombra encima (rename es atómico en
#   el mismo sistema de ficheros). Si cualquier paso falla se borra el temporal y el original queda como estaba.
#   El valor viaja por el entorno de awk, no por la línea de órdenes (no se ve en `ps`) ni interpretado (`\`, `&`, `#`).
env_escribir() {
    local fichero="$1" clave="$2" valor="$3" dir tmp entrada
    [[ -n "${clave}" && "${clave}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || return 1
    [[ "${valor}" != *$'\n'* && "${valor}" != *$'\r'* ]] || return 1
    fichero="$(readlink -f -- "${fichero}")" || return 1       # si fuese un enlace, se escribe el destino, no se pisa el enlace
    dir="$(dirname -- "${fichero}")"
    tmp="$(umask 077; mktemp "${dir}/.env.tmp.XXXXXX")" || return 1
    entrada=/dev/null
    [[ ! -e "${fichero}" ]] || entrada="${fichero}"
    if ! CLAVE_ENV="${clave}" VALOR_ENV="${valor}" awk '
        BEGIN { k = ENVIRON["CLAVE_ENV"]; v = ENVIRON["VALOR_ENV"]; hecho = 0; p = k "=" }
        index($0, p) == 1 { print p v; hecho = 1; next }
        { print }
        END { if (!hecho) print p v }
    ' "${entrada}" > "${tmp}"; then
        rm -f -- "${tmp}"; return 1
    fi
    if [[ -e "${fichero}" ]]; then
        chmod --reference="${fichero}" -- "${tmp}" && chown --reference="${fichero}" -- "${tmp}" || { rm -f -- "${tmp}"; return 1; }
    fi
    sync -- "${tmp}" 2>/dev/null || true                      # a disco antes de sustituir (una Pi con tarjeta SD pierde la luz)
    mv -f -- "${tmp}" "${fichero}" || { rm -f -- "${tmp}"; return 1; }
    sync -- "${dir}" 2>/dev/null || true
}

# limpiar_temporales_env FICHERO
#   Borra temporales `.env.tmp.*` que dejara una ejecución interrumpida por una muerte súbita (SIGKILL, corte de luz):
#   ahí no hay `trap` que valga y contienen una copia del .env.
limpiar_temporales_env() {
    local dir
    dir="$(dirname -- "$1")"
    find "${dir}" -maxdepth 1 -type f -name '.env.tmp.*' -delete 2>/dev/null || true
}

# asegurar_credenciales FICHERO DIRECTORIO_DE_DATOS
#   Códigos de salida (el llamador pone las palabras; aquí no se imprime nada):
#     0   DB_PASSWORD ya era válida: se conserva tal cual
#     10  no lo era y todavía no hay base de datos: se ha GENERADO y guardado una propia
#     20  no lo era pero YA HAY una base de datos creada: no se toca nada (no se inventa otra contraseña)
#     1   no se pudo generar o guardar (el .env queda como estaba)
#   Que «ya hay base de datos» se decide por PG_VERSION: lo escribe el initdb de la imagen de PostgreSQL al crearla.
asegurar_credenciales() {
    local fichero="$1" datos="$2" actual nueva
    actual="$(env_valor "${fichero}" DB_PASSWORD)"
    credencial_invalida "${actual}" || return 0
    [[ ! -e "${datos}/postgres/PG_VERSION" ]] || return 20
    nueva="$(generar_credencial)" || return 1
    env_escribir "${fichero}" DB_PASSWORD "${nueva}" || return 1
    return 10
}

# validar_credenciales FICHERO
#   0 si DB_PASSWORD vale. 1 si no (y dice por qué, sin el valor). La barrera del instalador y de update.sh.
validar_credenciales() {
    local v
    v="$(env_valor "$1" DB_PASSWORD)"
    if [[ -z "${v//[[:space:]]/}" ]]; then
        echo "DB_PASSWORD falta o está vacía en $1." >&2; return 1
    fi
    if credencial_invalida "${v}"; then
        echo "DB_PASSWORD conserva un valor de ejemplo conocido en $1." >&2; return 1
    fi
    return 0
}

# --- permisos ----------------------------------------------------------------------------------------------------

# _cred_escribible_por_otros DIR  → 0 si DIR no es de root o lo puede escribir su grupo o cualquiera (= se puede
#   crear, borrar o renombrar entradas dentro sin ser root).
_cred_escribible_por_otros() {
    local m
    m="$(stat -c '%u %a' -- "$1" 2>/dev/null)" || return 0
    [[ "${m%% *}" == "0" ]] || return 0
    (( (8#${m##* } & 8#022) != 0 ))
}

# raiz_dedicada RAIZ REPO
#   0 si RAIZ es una carpeta de ZascArr (el instalador la creó o solo guarda lo suyo) y por tanto se puede dejar
#   de root sin dañar nada ajeno. 1 si es compartida: un home, `/`, `/opt`… que contiene otras cosas.
#   Reclamar por error la carpeta personal de alguien es el fallo que este criterio evita.
raiz_dedicada() {
    local raiz repo nombre propia home p
    raiz="$(readlink -f -- "$1" 2>/dev/null)" || return 1
    repo="$(readlink -f -- "$2" 2>/dev/null)" || return 1
    [[ "${raiz}" != "/" && "${repo}" == "${raiz}/zascarr" ]] || return 1
    while IFS=: read -r _ _ _ _ _ home _; do
        [[ "${home}" != "${raiz}" ]] || return 1
    done < <(getent passwd 2>/dev/null)
    while IFS= read -r nombre; do
        [[ "${nombre}" == .env.tmp.* ]] && continue
        propia=0
        for p in "${_CRED_ENTRADAS_PROPIAS[@]}"; do [[ "${nombre}" == "${p}" ]] && propia=1; done
        (( propia == 1 )) || return 1
    done < <(find "${raiz}" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null)
    return 0
}

# proteger_configuracion ENV_FILE RAIZ REPO
#   Deja la configuración administrativa fuera del alcance del usuario de servicio y de otros usuarios locales:
#     · ENV_FILE: root:root 600 (nadie más lo lee ni lo cambia). Siempre.
#     · Si RAIZ es una carpeta dedicada de ZascArr (raiz_dedicada: la estándar <RAIZ>/zascarr, que solo guarda lo
#       suyo) además:
#         – REPO: de root y sin escritura para grupo/otros — contiene el enlace `.env` que Compose sigue por defecto,
#           el docker-compose.yml, el Dockerfile y los scripts que root ejecuta. `chown -h`: nunca se sigue un
#           enlace (uno dentro del repo no puede hacer que se cambie el dueño de un fichero ajeno).
#         – RAIZ: de root 755, para que nadie pueda borrar o renombrar la ENTRADA `.env` (proteger solo el contenido
#           no basta: unlink/rename dependen del permiso sobre la carpeta).
#     · Si RAIZ es compartida (un home, `/opt`…) NO se reclama ni ella ni el repo —podrían ser de otra persona— y se
#       avisa de que ahí el .env no queda a salvo de ser reemplazado por quien pueda escribir en esa carpeta.
#   Requiere root. No toca la biblioteca ni las descargas (no están aquí). Idempotente.
proteger_configuracion() {
    local env="$1" raiz="$2" repo="$3" rc=0
    [[ "$(id -u)" -eq 0 ]] || { warn "Para proteger la configuración hace falta ser administrador (sudo)."; return 1; }
    if [[ -e "${env}" ]]; then
        chown root:root -- "${env}" && chmod 600 -- "${env}" || rc=1
    fi
    if raiz_dedicada "${raiz}" "${repo}"; then
        if [[ -d "${repo}" ]]; then
            chown -hR root:root -- "${repo}" && chmod -R go-w -- "${repo}" || rc=1
        fi
        chown root:root -- "${raiz}" && chmod 755 -- "${raiz}" || rc=1
    elif _cred_escribible_por_otros "${raiz}" || _cred_escribible_por_otros "${repo}"; then
        warn "${raiz} es una carpeta que no es solo de ZascArr (o el repo no está en <carpeta>/zascarr): no la he tocado.
  El .env queda ilegible para otros usuarios (600, de root), pero quien pueda escribir en esa carpeta o en el
  repo podría borrarlo, sustituirlo o redirigir su enlace. Instala ZascArr en una carpeta propia (por defecto
  /opt/zascarr)."
    fi
    return "${rc}"
}

# comprobar_proteccion ENV_FILE RAIZ REPO
#   Solo lectura. Imprime una línea por cada defecto (sin valores) y devuelve 0 si no hay ninguno, 1 si lo hay,
#   2 si no se puede comprobar por falta de permisos (no se es root y el .env no se puede leer).
comprobar_proteccion() {
    local env="$1" raiz="$2" repo="$3" defectos=0 m
    if [[ ! -e "${env}" ]]; then echo "No existe ${env}."; return 1; fi
    if [[ ! -r "${env}" ]]; then echo "No tengo permiso para leer ${env}: ejecútalo con sudo."; return 2; fi
    m="$(stat -c '%u %a' -- "${env}")"
    if [[ "${m%% *}" != "0" || $(( 8#${m##* } & 8#077 )) -ne 0 ]]; then
        echo "El .env no es de root con modo 600 (ahora: modo ${m##* }): otros usuarios pueden leerlo o cambiarlo."
        defectos=1
    fi
    validar_credenciales "${env}" 2>&1 || defectos=1
    if _cred_escribible_por_otros "${repo}"; then
        echo "El repo (${repo}) no es de root o es escribible por otros: se podría redirigir el enlace .env o cambiar lo que root ejecuta."
        defectos=1
    fi
    if raiz_dedicada "${raiz}" "${repo}" && _cred_escribible_por_otros "${raiz}"; then
        echo "La carpeta ${raiz} no es de root con modo 755: otros usuarios podrían reemplazar el .env."
        defectos=1
    fi
    return "${defectos}"
}
