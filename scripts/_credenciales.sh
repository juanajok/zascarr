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

# _cred_recortar VALOR → imprime VALOR sin los espacios en blanco de los extremos (ASCII: espacio, \t \n \r \v \f).
#   LC_ALL=C: el conjunto no depende de la configuración regional (en Python y en el servicio de Compose es el mismo).
_cred_recortar() {
    local LC_ALL=C v="${1-}"
    v="${v#"${v%%[![:space:]]*}"}"
    v="${v%"${v##*[![:space:]]}"}"
    printf '%s' "${v}"
}

# credencial_invalida VALOR
#   0 (verdadero) si el valor no vale como contraseña. Es la ÚNICA definición en los scripts y es la MISMA regla que
#   zascarr/utils/credenciales.py y el servicio `credenciales` de docker-compose.yml (tests/_tabla_credenciales.py la
#   comprueba en las tres):
#     1) se recortan los espacios en blanco de los extremos;
#     2) si empieza y acaba por la misma comilla (' o "), se quita ese par y se recorta otra vez;
#     3) se pasa a minúsculas (ASCII);
#     4) no vale si queda vacío o es EXACTAMENTE uno de CREDENCIALES_CONOCIDAS.
#   NUNCA se borra nada interior: `change me` es una contraseña personal, no `changeme`.
credencial_invalida() {
    local LC_ALL=C v c
    v="$(_cred_recortar "${1-}")"
    if [[ ${#v} -ge 2 && ( "${v:0:1}" == '"' || "${v:0:1}" == "'" ) && "${v: -1}" == "${v:0:1}" ]]; then
        v="$(_cred_recortar "${v:1:${#v}-2}")"
    fi
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

# _cred_representar VALOR → imprime cómo se escribe VALOR a la derecha de `CLAVE=` para que `env_valor` (y Compose)
#   lo lean EXACTAMENTE igual. Sin comillas salvo que haga falta: espacios en los extremos, un comentario ` #…` o una
#   comilla al principio cambiarían el valor leído. Con comillas simples (literales en Compose) si no lleva ninguna;
#   si la lleva, con dobles si no lleva `"`, `$`, `\` ni invertida; si ni así, no se puede representar (devuelve 1).
_cred_representar() {
    local LC_ALL=C v="$1" necesita=0
    if [[ "${v}" == [[:space:]]* || "${v}" == *[[:space:]] || "${v}" == *[[:space:]]"#"* \
          || "${v}" == "'"* || "${v}" == '"'* ]]; then
        necesita=1
    fi
    if (( necesita == 0 )); then printf '%s' "${v}"; return 0; fi
    if [[ "${v}" != *"'"* ]]; then printf "'%s'" "${v}"; return 0; fi
    if [[ "${v}" != *'"'* && "${v}" != *'$'* && "${v}" != *'\'* && "${v}" != *'`'* ]]; then printf '"%s"' "${v}"; return 0; fi
    return 1
}

# env_escribir FICHERO CLAVE VALOR
#   Pone CLAVE=VALOR en el .env. Sustituye TODAS las líneas que `env_valor` consideraría de esa clave (sangradas, con
#   `export`, repetidas) por una sola forma `CLAVE=…` y, si no hay ninguna, añade una: lo que se escribe es lo que se
#   lee. ATÓMICO y SIN VENTANA: 1) si el original existe se cierra ANTES (600, y de root si somos root) — un secreto nuevo
#   no entra nunca en un fichero abierto; 2) el temporal nace 600 en la MISMA carpeta (umask 077) y es de root si somos
#   root: NO hereda el modo ni el propietario del original (un `.env` heredado en 644 daba un secreto nuevo en 644);
#   3) se renombra encima (rename atómico). Si cualquier paso falla se borra el temporal y el original queda como estaba.
#   El valor viaja por el entorno de awk, no por la línea de órdenes ni interpretado (`\`, `&`, `#`).
env_escribir() {
    local fichero="$1" clave="$2" valor="$3" dir tmp entrada rep
    [[ -n "${clave}" && "${clave}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || return 1
    [[ "${valor}" != *$'\n'* && "${valor}" != *$'\r'* ]] || return 1
    rep="$(_cred_representar "${valor}")" || return 1
    fichero="$(readlink -f -- "${fichero}")" || return 1       # si fuese un enlace, se escribe el destino, no se pisa el enlace
    dir="$(dirname -- "${fichero}")"
    if [[ -e "${fichero}" ]]; then
        chmod 600 -- "${fichero}" || return 1
        if [[ "$(id -u)" -eq 0 ]]; then chown 0:0 -- "${fichero}" || return 1; fi
    fi
    tmp="$(umask 077; mktemp "${dir}/.env.tmp.XXXXXX")" || return 1
    if [[ "$(id -u)" -eq 0 ]]; then chown 0:0 -- "${tmp}" || { rm -f -- "${tmp}"; return 1; }; fi
    entrada=/dev/null
    [[ ! -e "${fichero}" ]] || entrada="${fichero}"
    if ! CLAVE_ENV="${clave}" VALOR_ENV="${rep}" awk '
        BEGIN { k = ENVIRON["CLAVE_ENV"]; v = ENVIRON["VALOR_ENV"]; hecho = 0; pat = "^[ \t]*(export[ \t]+)?" k "=" }
        $0 ~ pat { print k "=" v; hecho = 1; next }
        { print }
        END { if (!hecho) print k "=" v }
    ' "${entrada}" > "${tmp}"; then
        rm -f -- "${tmp}"; return 1
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

# --- la ubicación del .env: de fiar de punta a punta (C5) ----------------------------------------------------------
# Proteger el CONTENIDO no basta: borrar o renombrar una entrada depende del permiso sobre la CARPETA que la contiene, así
# que cualquiera que pueda escribir en una carpeta del camino puede sustituir el .env (o reapuntar un enlace). Se recorre
# cada componente de la ruta LÓGICA —no la física: resolverla de golpe pierde los enlaces intermedios, y un enlace en una
# carpeta que otro puede escribir se puede reapuntar—.

#: Cuentas de las que se fía el camino. Solo root; las pruebas lo cambian (no son root).
_CRED_UIDS_CONFIABLES="0"
#: Hook de pruebas: si no está vacío, el recorrido no examina esta carpeta ni las de por encima (son de la máquina).
CRED_CONFIAR_DESDE=""

_cred_uid_confiable() {
    local u="$1" x
    for x in ${_CRED_UIDS_CONFIABLES}; do [[ "${u}" == "${x}" ]] && return 0; done
    return 1
}

# ¿Está DIR por encima del corte (o es el corte) y por tanto se da por bueno?
_cred_bajo_corte() {
    [[ -n "${CRED_CONFIAR_DESDE}" ]] || return 1
    [[ "$1" == "${CRED_CONFIAR_DESDE}" || "${CRED_CONFIAR_DESDE}" == "${1%/}/"* ]]
}

# _cred_dir_inseguro DIR ESTRICTO
#   0 y un motivo por la salida estándar si DIR deja que otra cuenta sustituya lo que contiene: no es de una cuenta de
#   fiar o lo puede escribir su grupo o cualquiera. ESTRICTO=0 admite el bit pegajoso (como /tmp: nadie renombra lo que
#   no es suyo); ESTRICTO=1 —la carpeta que contiene el .env— no.
_cred_dir_inseguro() {
    local d="$1" estricto="$2" u m
    read -r u m < <(stat -c '%u %a' -- "${d}" 2>/dev/null) || { echo "no puedo comprobar los permisos de ${d}."; return 0; }
    if ! _cred_uid_confiable "${u}"; then
        echo "${d} es propiedad de otra cuenta (uid ${u}): podría sustituir lo que contiene."; return 0
    fi
    if (( (8#${m} & 8#022) != 0 )) && { (( estricto == 1 )) || (( (8#${m} & 8#1000) == 0 )); }; then
        echo "${d} es escribible por otras cuentas (modo ${m}): podrían sustituir lo que contiene."; return 0
    fi
    return 1
}

# _cred_camino_inseguro RUTA ESTRICTO_FINAL [PROFUNDIDAD]
#   ESTRICTO_FINAL: 1 = la carpeta final no admite ni el bit pegajoso (la que contiene el .env); 0 = lo admite; 2 = la
#   carpeta final NO se examina (se va a reclamar) pero sí todo lo que lleva hasta ella, enlaces incluidos.
#   0 y el motivo si algún componente de RUTA permite la sustitución. Cada carpeta del camino, desde `/`, ha de ser de fiar;
#   un enlace se admite solo si es de una cuenta de fiar (su carpeta ya se comprobó) y su DESTINO también lo es; `..` y los
#   bucles se rechazan. No toca nada.
_cred_camino_inseguro() {
    local ruta="$1" estricto="$2" prof="${3:-0}" c i n actual="" padre u destino resto motivo ultimo
    local -a comps=()
    (( prof < 20 )) || { echo "demasiados enlaces simbólicos seguidos en ${ruta}."; return 0; }
    [[ "${ruta}" == /* ]] || ruta="${PWD}/${ruta}"
    # Se separa SOLO por `/`: cualquier otro carácter, incluido un salto de línea, es parte del nombre. (Con `tr '/' '\n'` y
    # `read -r` un `\n` dentro del nombre pasaba a ser un separador y se examinaba OTRA ruta.)
    resto="${ruta}"
    while [[ -n "${resto}" ]]; do
        c="${resto%%/*}"
        if [[ "${resto}" == */* ]]; then resto="${resto#*/}"; else resto=""; fi
        [[ -z "${c}" || "${c}" == "." ]] && continue
        [[ "${c}" != ".." ]] || { echo "la ruta ${ruta//$'\n'/\\n} contiene '..': no la resuelvo."; return 0; }
        comps+=("${c}")
    done
    n=${#comps[@]}
    if ! _cred_bajo_corte "/"; then
        motivo="$(_cred_dir_inseguro / $(( n == 0 && estricto )))" && { echo "${motivo}"; return 0; }
    fi
    for (( i = 0; i < n; i++ )); do
        padre="${actual:-/}"
        actual="${actual}/${comps[i]}"
        if _cred_bajo_corte "${actual}"; then continue; fi
        if [[ -L "${actual}" ]]; then
            u="$(stat -c %u -- "${actual}" 2>/dev/null)" || { echo "no puedo comprobar el enlace ${actual}."; return 0; }
            _cred_uid_confiable "${u}" || { echo "el enlace ${actual} es propiedad de otra cuenta (uid ${u}): podría reapuntarlo."; return 0; }
            # `$(…)` recorta los saltos de línea FINALES: se añade un carácter centinela y se quita después (y el único LF que
            # añade readlink).
            destino="$(readlink -- "${actual}" && printf x)" || { echo "no puedo leer el enlace ${actual}."; return 0; }
            destino="${destino%x}"; destino="${destino%$'\n'}"
            if [[ "${destino}" != /* ]]; then          # relativo a la carpeta del enlace (sin enlaces: ya se comprobó)
                resto="${padre}"
                while [[ "${destino}" == ".." || "${destino}" == ../* ]]; do
                    resto="$(dirname -- "${resto}")"; destino="${destino#..}"; destino="${destino#/}"
                done
                destino="${resto%/}/${destino}"
            fi
            resto=""
            for (( c = i + 1; c < n; c++ )); do resto+="/${comps[c]}"; done
            _cred_camino_inseguro "${destino}${resto}" "${estricto}" $(( prof + 1 ))
            return $?
        fi
        [[ -d "${actual}" ]] || { echo "no existe la carpeta ${actual}."; return 0; }
        ultimo=0
        if (( i == n - 1 )); then
            (( estricto != 2 )) || continue                     # 2: la carpeta final se va a reclamar, no se examina
            (( estricto == 1 )) && ultimo=1
        fi
        motivo="$(_cred_dir_inseguro "${actual}" "${ultimo}")" && { echo "${motivo}"; return 0; }
    done
    return 1
}

# Rutas con un salto de línea en el nombre: el comprobador las examina bien (separa solo por `/`), pero el resto del
# instalador captura rutas con `$(…)` (que recorta saltos de línea finales) y recorre listados línea a línea, así que las
# entradas públicas las RECHAZAN con un mensaje claro en vez de confiar en que todo lo demás las trate bien.
_cred_lf_motivo() {
    printf 'La ruta %s contiene un salto de línea en el nombre: no la admito (los scripts no pueden examinarla con garantías). Usa una carpeta con un nombre normal, por defecto /opt/zascarr.' "${1//$'\n'/\\n}"
}

# ubicacion_insegura ENV_FILE
#   0 y el motivo por la salida estándar si otra cuenta podría sustituir o redirigir ENV_FILE; 1 (sin salida) si la
#   ubicación es de fiar. El propio ENV_FILE no puede ser un enlace.
ubicacion_insegura() {
    local env="$1"
    if [[ "${env}" == *$'\n'* ]]; then echo "$(_cred_lf_motivo "${env}")"; return 0; fi
    if [[ -L "${env}" ]]; then
        echo "${env} es un enlace simbólico: otra cuenta podría apuntarlo a un fichero suyo."; return 0
    fi
    _cred_camino_inseguro "$(dirname -- "${env}")" 1 0
}

# comprobar_env_legible [FICHERO]
#   Un .env que EXISTE pero no se puede leer (600 de root y no somos root) no es un .env ausente: Compose falla con
#   `permission denied` en inglés, y un script que lo lea por su cuenta (uninstall.sh) lo trataría como vacío y trabajaría con
#   valores por defecto. Se comprueba ANTES de tocar nada. Un .env AUSENTE no es cosa de esta función. Necesita `die`.
comprobar_env_legible() {
    local f="${1:-${ENV_FILE:-}}"
    if [[ -n "${f}" && -e "${f}" && ! -r "${f}" ]]; then
        die "No puedo leer ${f}: guarda la contraseña de la base de datos y solo el administrador puede abrirlo.
  Vuelve a ejecutarlo con sudo, por ejemplo: sudo bash ${0}"
    fi
}

# proteger_configuracion ENV_FILE RAIZ REPO
#   Deja la configuración administrativa fuera del alcance del usuario de servicio y de otros usuarios locales, y SE NIEGA
#   (devuelve 1, diciendo por qué) si no puede garantizarlo: una advertencia que invalida la protección no se sigue como si
#   nada. Orden:
#     1. Si RAIZ es una carpeta dedicada de ZascArr (raiz_dedicada), lo que hay POR ENCIMA tiene que ser de fiar antes de tocar
#        nada (no se va a reclamar) — un home, por ejemplo, no lo es.
#     2. Si es dedicada se reclama, SOLO esas dos entradas: REPO de root y sin escritura para otros (`chown -h`: nunca se
#        sigue un enlace; contiene el enlace `.env` que Compose sigue, el compose y los scripts que root ejecuta) y RAIZ de
#        root 755. Si es compartida (`/opt`, un home…) no se reclama nada: tiene que ser ya de fiar.
#     3. Se comprueba la ubicación completa (`ubicacion_insegura`) y el repo. Si algo falla, se para SIN haber tocado el .env.
#     4. Solo entonces ENV_FILE pasa a root:root 600.
#   Requiere root. No toca la biblioteca ni las descargas. Idempotente.
proteger_configuracion() {
    local env="$1" raiz="$2" repo="$3" motivo dedicada=0
    [[ "$(id -u)" -eq 0 ]] || { warn "Para proteger la configuración hace falta ser administrador (sudo)."; return 1; }
    local ruta
    for ruta in "${env}" "${raiz}" "${repo}"; do
        [[ "${ruta}" != *$'\n'* ]] || { warn "$(_cred_lf_motivo "${ruta}")"; return 1; }
    done
    if raiz_dedicada "${raiz}" "${repo}"; then dedicada=1; fi
    if (( dedicada == 1 )); then
        if motivo="$(_cred_camino_inseguro "${raiz}" 2 0)"; then
            warn "${motivo}
  ${raiz} es una carpeta de ZascArr, pero cuelga de una ruta que otra cuenta puede cambiar."
            return 1
        fi
        if [[ -d "${repo}" ]]; then
            chown -hR root:root -- "${repo}" && chmod -R go-w -- "${repo}" || { warn "No pude dejar ${repo} a nombre de root."; return 1; }
        fi
        chown root:root -- "${raiz}" && chmod 755 -- "${raiz}" || { warn "No pude dejar ${raiz} a nombre de root."; return 1; }
    fi
    if motivo="$(ubicacion_insegura "${env}")"; then
        if (( dedicada == 0 )); then
            warn "${motivo}
  ${raiz} no es solo de ZascArr (o el repo no está en <carpeta>/zascarr): no la he tocado, y no me fío de ella."
        else warn "${motivo}"; fi
        return 1
    fi
    if motivo="$(_cred_camino_inseguro "${repo}" 1 0)"; then
        warn "El código que root ejecuta (${repo}) lo podría cambiar otra cuenta: ${motivo}"
        return 1
    fi
    if [[ -e "${env}" ]]; then
        chown root:root -- "${env}" && chmod 600 -- "${env}" || { warn "No pude dejar ${env} como root:root 600."; return 1; }
    fi
    return 0
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
    if m="$(ubicacion_insegura "${env}")"; then
        echo "${m}"
        defectos=1
    fi
    return "${defectos}"
}
