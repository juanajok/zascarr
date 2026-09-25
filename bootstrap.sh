#!/usr/bin/env bash
# bootstrap.sh — Instalador de un solo comando para ZascArr.
#
#     curl -fsSL https://raw.githubusercontent.com/juanajok/zascarr/main/bootstrap.sh | sudo bash
#
# Este mismo fichero sirve para dos cosas, según desde dónde se ejecute:
#   1. Suelto (curl | sudo bash, sin repo clonado todavía): instala git y
#      Docker si faltan, crea la carpeta de trabajo, clona el repo, y se
#      relanza a sí mismo desde dentro del clon para seguir con el paso 2.
#   2. Desde dentro del repo ya clonado (primera vez o re-ejecuciones
#      posteriores): configura .env, crea la estructura de directorios,
#      levanta PostgreSQL/Redis, migra y arranca ZascArr. Idempotente.
#
# Garantía (A3): este instalador NUNCA borra ni modifica los ficheros de tu
# colección. Solo crea directorios, copia .env.example a .env y levanta
# contenedores. No hay ningún `rm`, ni movimiento ni sobreescritura de ficheros
# de la colección, y los únicos `chown` van a directorios que ESTE script acaba
# de crear (nunca a los tebeos que ya tenías). Si algo falla, la colección
# queda exactamente como estaba.
set -euo pipefail

# Bug real (reportado): si el shell que invoca este script está posicionado
# dentro de un directorio que ya no existe (p.ej. "cd ~/zascarr" seguido de
# "rm -rf ~/zascarr" en el mismo terminal, exactamente lo que se recomienda
# para reintentar una instalación fallida), getcwd() falla para cualquier
# proceso que intente resolverlo — incluido "git clone" con ruta de destino
# absoluta, que igualmente consulta el cwd por dentro y aborta con "Unable
# to read current working directory". Nos movemos a un sitio que sí existe
# ANTES de hacer nada más, para no heredar ese problema del shell padre.
cd /tmp 2>/dev/null || cd / || true

B='\033[1m'; G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; N='\033[0m'
info()    { echo -e "${B}→${N} $*"; }
success() { echo -e "${G}✓${N} $*"; }
warn()    { echo -e "${Y}⚠${N}  $*"; }
# die() = error en español llano (A2): causa + qué hacer, nunca "exit code 1".
die()     { echo -e "${R}✗${N} $*" >&2; exit 1; }

instalar_git_si_falta() {
    command -v git >/dev/null 2>&1 && return 0
    info "Instalando git (hace falta para poder actualizar ZascArr más adelante)..."
    apt-get update -qq && apt-get install -y -qq git || die \
        "No pude instalar git automáticamente. Instálalo a mano: sudo apt-get install -y git"
    success "git instalado"
}

instalar_docker_si_falta() {
    if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
        return 0
    fi
    info "Instalando Docker (puede tardar varios minutos en una Pi)..."
    curl -fsSL https://get.docker.com | sh || die \
        "No pude instalar Docker automáticamente. Instálalo a mano:
  curl -fsSL https://get.docker.com | sh"
    if [[ -n "${SUDO_USER:-}" ]]; then
        usermod -aG docker "${SUDO_USER}" 2>/dev/null || true
    fi
    success "Docker instalado"
}

# Bug real: todo git de este script corre como root (EUID=0 exigido más
# abajo), pero el repo queda con propietario "media" (ver
# asegurar_usuario_servicio) — git rechaza por seguridad tocar un repo de
# otro propietario ("dubious ownership") salvo que se autorice
# explícitamente. Como aquí SÍ somos root a propósito y de forma
# consciente (instalador con sudo), se autoriza sin más: es lo mismo que
# ya hacen scripts/update.sh y scripts/rollback.sh vía _comun.sh.
autorizar_git_en() {
    git config --global --add safe.directory "$1" 2>/dev/null || true
}

# Usuario/grupo de SERVICIO (no el usuario personal que ejecuta sudo):
# mismo patrón que ARR_USER/ARR_GROUP de otros instaladores *arr (Sonarr,
# Radarr, Prowlarr...) — por defecto "media", para que ZascArr conviva con
# el resto de la suite bajo la misma identidad. Se crea como usuario de
# sistema (sin login, sin home propio) si todavía no existe.
asegurar_usuario_servicio() {
    ZASCARR_USER="${ZASCARR_USER:-media}"
    ZASCARR_GROUP="${ZASCARR_GROUP:-media}"
    getent group "${ZASCARR_GROUP}" >/dev/null 2>&1 || groupadd --system "${ZASCARR_GROUP}" || die \
        "No pude crear el grupo ${ZASCARR_GROUP}. Créalo a mano: sudo groupadd --system ${ZASCARR_GROUP}"
    getent passwd "${ZASCARR_USER}" >/dev/null 2>&1 || useradd --system --no-create-home \
        --shell /usr/sbin/nologin -g "${ZASCARR_GROUP}" "${ZASCARR_USER}" || die \
        "No pude crear el usuario ${ZASCARR_USER}. Créalo a mano: sudo useradd --system -g ${ZASCARR_GROUP} ${ZASCARR_USER}"
}

# ── Modo "instalación desde cero" ────────────────────────────────────────────
# Si nos han invocado sueltos (curl | sudo bash, sin haber clonado el repo
# antes), no hay docker-compose.yml al lado de este script: lo detectamos así,
# sin depender de trucos frágiles de BASH_SOURCE bajo un pipe. Preparamos el
# sistema y nos relanzamos desde dentro del clon real para seguir tal cual.
_SD="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" 2>/dev/null && pwd || pwd)"

if [[ ! -f "${_SD}/docker-compose.yml" ]]; then
    echo -e "\n${B}====================================${N}"
    echo -e "${B}  ZascArr — Instalador${N}"
    echo -e "${B}====================================${N}\n"

    [[ "${EUID}" -eq 0 ]] || die \
        "Este instalador necesita permisos de administrador. Ejecútalo así:
  curl -fsSL https://raw.githubusercontent.com/juanajok/zascarr/main/bootstrap.sh | sudo bash"

    instalar_git_si_falta
    instalar_docker_si_falta
    asegurar_usuario_servicio

    # Mismo patrón que el resto de la suite *arr (Sonarr/Radarr/Prowlarr...):
    # código en /opt, propiedad del usuario de servicio (media por defecto),
    # no del usuario personal que ejecutó sudo ni de root.
    ZASCARR_ROOT="${ZASCARR_ROOT:-/opt/zascarr}"
    info "Preparando ${ZASCARR_ROOT}..."
    mkdir -p "${ZASCARR_ROOT}" || die "No puedo crear ${ZASCARR_ROOT}."

    if [[ -d "${ZASCARR_ROOT}/zascarr/.git" ]]; then
        # Bug real: reutilizar el clon SIN actualizarlo deja a cualquiera que
        # reintente el instalador (el caso típico: falló, se corrige en
        # GitHub, se reintenta) pegado para siempre a la primera versión que
        # se descargó — viendo mensajes de error ya corregidos, sin el
        # arreglo aplicado. Se actualiza con fetch + ff-only (mismo patrón
        # seguro que update.sh); si el árbol está sucio o ha divergido, se
        # avisa y se sigue con lo que haya en vez de abortar la instalación.
        info "Ya existe un clon en ${ZASCARR_ROOT}/zascarr, lo actualizo..."
        autorizar_git_en "${ZASCARR_ROOT}/zascarr"
        if git -C "${ZASCARR_ROOT}/zascarr" diff --quiet 2>/dev/null && \
           git -C "${ZASCARR_ROOT}/zascarr" diff --cached --quiet 2>/dev/null; then
            if git -C "${ZASCARR_ROOT}/zascarr" fetch -q origin main 2>/dev/null && \
               git -C "${ZASCARR_ROOT}/zascarr" merge -q --ff-only origin/main 2>/dev/null; then
                success "Clon actualizado a la última versión."
            else
                warn "No pude actualizar el clon existente (sin red, o la rama local ha divergido). Sigo con lo que hay."
            fi
        else
            warn "El clon en ${ZASCARR_ROOT}/zascarr tiene cambios locales sin guardar; no lo toco. Sigo con lo que hay."
        fi
    else
        info "Descargando ZascArr..."
        git clone -q https://github.com/juanajok/zascarr.git "${ZASCARR_ROOT}/zascarr" || die \
            "No pude clonar el repositorio. ¿Hay conexión a internet?"
    fi
    chown -R "${ZASCARR_USER}:${ZASCARR_GROUP}" "${ZASCARR_ROOT}" 2>/dev/null || \
        warn "No pude ajustar el propietario de ${ZASCARR_ROOT} a ${ZASCARR_USER}."

    success "Continuando la instalación..."
    # Bug real (reproducido): tras "curl | sudo bash", el stdin de ESTE
    # proceso sigue siendo el pipe de curl. Bash lo va leyendo por bloques
    # a medida que ejecuta, así que en este punto puede quedar contenido
    # del propio bootstrap.sh sin consumir todavía en ese pipe. Si nos
    # relanzáramos sin más, el "read" de las 3 preguntas de la fase 2 se
    # tragaría esos restos como si fueran la respuesta del usuario (visto
    # en vivo: el idioma leía un comentario del propio script y el sed
    # posterior reventaba). Reconectamos stdin a la terminal real antes.
    # "-r /dev/tty" no basta: el nodo existe y es legible por permisos
    # aunque no haya terminal controladora detrás (p.ej. "docker exec" sin
    # -t), y ahí la apertura real falla con ENXIO. Se intenta abrir de
    # verdad en un subshell aparte (para no tocar los descriptores de este
    # proceso) antes de decidir; el subshell absorbe el error de verdad,
    # a diferencia de intentarlo directamente en este shell.
    # Marca para que la fase 2 no intente autoactualizarse OTRA VEZ (ya se
    # hizo aquí arriba, y hacerlo dos veces reemplazaría el propio fichero
    # bootstrap.sh mientras se está ejecutando).
    export _ZASCARR_YA_ACTUALIZADO=1
    if (exec < /dev/tty) 2>/dev/null; then
        exec bash "${ZASCARR_ROOT}/zascarr/bootstrap.sh" "$@" < /dev/tty
    else
        warn "Sin terminal para las preguntas interactivas: usaré los valores por defecto."
        exec bash "${ZASCARR_ROOT}/zascarr/bootstrap.sh" "$@" < /dev/null
    fi
fi

# ── A partir de aquí, siempre dentro de un clon real del repo ──────────────
# El repo (código) vive en SCRIPT_DIR, dentro de ZASCARR_ROOT (su padre — en
# /opt/zascarr por defecto, da /opt/zascarr/zascarr). Los DATOS (Postgres,
# Redis, portadas) viven aparte, en ZASCARR_DATA_DIR (/var/lib/zascarr por
# defecto) — mismo patrón que el resto de la suite *arr: código en /opt,
# datos en /var/lib, nunca mezclados.
SCRIPT_DIR="${_SD}"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ZASCARR_DATA_DIR="${ZASCARR_DATA_DIR:-/var/lib/zascarr}"
# Compose vive en el repo; se invoca con -f explícito para no depender del cwd.
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose.yml"

[[ "${EUID}" -eq 0 ]] || die \
    "Este instalador necesita permisos de administrador. Ejecútalo así:
  sudo bash ${SCRIPT_DIR}/bootstrap.sh"

# Bug real: quien reinvoca este script DIRECTAMENTE ("sudo bash
# .../bootstrap.sh", el camino documentado para reconfigurar o reintentar,
# sin pasar por "curl | sudo bash") nunca pasa por la rama de instalación
# en frío de más arriba, así que se quedaba pegado para siempre a la
# versión que tenía en disco — viendo errores ya corregidos en GitHub sin
# el arreglo aplicado. Se autoactualiza aquí también, salvo que ya se haya
# hecho justo antes (viniendo de esa rama, para no tocar el propio fichero
# mientras se está ejecutando: en su lugar se relanza limpio después).
if [[ -z "${_ZASCARR_YA_ACTUALIZADO:-}" ]]; then
    autorizar_git_en "${SCRIPT_DIR}"
    if git -C "${SCRIPT_DIR}" diff --quiet 2>/dev/null && \
       git -C "${SCRIPT_DIR}" diff --cached --quiet 2>/dev/null; then
        if git -C "${SCRIPT_DIR}" fetch -q origin main 2>/dev/null; then
            ANTES="$(git -C "${SCRIPT_DIR}" rev-parse HEAD 2>/dev/null || true)"
            if git -C "${SCRIPT_DIR}" merge -q --ff-only origin/main 2>/dev/null; then
                DESPUES="$(git -C "${SCRIPT_DIR}" rev-parse HEAD 2>/dev/null || true)"
                if [[ -n "${DESPUES}" && "${ANTES}" != "${DESPUES}" ]]; then
                    success "Código actualizado (${ANTES:0:7} → ${DESPUES:0:7}). Reiniciando con la nueva versión..."
                    export _ZASCARR_YA_ACTUALIZADO=1
                    exec bash "${SCRIPT_DIR}/bootstrap.sh" "$@"
                fi
            fi
        fi
    fi
    export _ZASCARR_YA_ACTUALIZADO=1
fi

# Actualiza (o añade si no existe) una variable en .env. Idempotente:
# volver a ejecutar el bootstrap no duplica líneas.
set_env_var() {
    local key="$1" value="$2" escaped
    # M7: escapar '\' y '&' para sed, y usar '#' como delimitador (menos
    # frecuente en rutas que '|'). Así "/media/Juan & María" se escribe
    # literal y no se expande como comando de reemplazo de sed.
    escaped="${value//\\/\\\\}"
    escaped="${escaped//&/\\&}"
    if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
        sed -i "s#^${key}=.*#${key}=${escaped}#" "${ENV_FILE}"
    else
        echo "${key}=${value}" >> "${ENV_FILE}"
    fi
}

echo -e "\n${B}====================================${N}"
echo -e "${B}  ZascArr — Bootstrap${N}"
echo -e "${B}====================================${N}\n"

# ── Comprobaciones previas (A2): cada fallo explica causa y solución, y lo
# ── que se puede instalar solo, se instala solo. ──
instalar_docker_si_falta
asegurar_usuario_servicio

info "Comprobando que el demonio de Docker está en marcha..."
docker info >/dev/null 2>&1 || die \
    "El demonio de Docker no responde. Arranca el servicio con: sudo systemctl start docker"

ENV_FILE="${ZASCARR_ROOT}/.env"
mkdir -p "${ZASCARR_ROOT}" || die \
    "No puedo crear ${ZASCARR_ROOT}. ¿Tienes permisos de escritura en el directorio padre?"
if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${SCRIPT_DIR}/.env.example" "${ENV_FILE}" 2>/dev/null || \
        die "No encuentro .env.example en ${SCRIPT_DIR}/. ¿Está el repo completo clonado?"
fi

# ── A1: 3 preguntas, nada más. El resto se deduce o tiene un valor
# ── razonable por defecto (Intro acepta lo que hay entre corchetes). ──
echo -e "${B}Configuración inicial${N} (pulsa Intro para aceptar el valor por defecto)\n"

read -rp "¿Dónde están tus tebeos ya organizados? [/media/library]: " ANS_LIBRARY || true
LIBRARY="${ANS_LIBRARY:-/media/library}"

read -rp "¿Dónde caen tus descargas ya completadas (la carpeta exacta, no una raíz)? [/media/data]: " ANS_DOWNLOADS || true
DOWNLOADS_ROOT="${ANS_DOWNLOADS:-/media/data}"

read -rp "¿Idioma de la interfaz? [es/en, por defecto es]: " ANS_LOCALE || true
APP_LOCALE="${ANS_LOCALE:-es}"
if [[ "${APP_LOCALE}" != "es" && "${APP_LOCALE}" != "en" ]]; then
    warn "Idioma '${APP_LOCALE}' no reconocido, uso 'es'."
    APP_LOCALE="es"
fi

HOST_LIBRARY_DIR="${LIBRARY}"
# Bug real (reportado): antes se añadía "/downloads" y "/aMule/Incoming" a
# lo que el usuario tecleaba, asumiendo que siempre daría una raíz genérica
# para organizar debajo. Un usuario con Transmission/aMule ya apuntando sus
# descargas reales a esa carpeta (el caso normal, no la excepción) se
# encontraba con una subcarpeta nueva y vacía en vez de sus archivos —
# bootstrap.sh "veía" la ruta correcta pero miraba un nivel más abajo de
# donde estaban de verdad. Ahora se usa la ruta EXACTA que da el usuario,
# tal cual, para las dos.
HOST_DOWNLOADS_DIR="${DOWNLOADS_ROOT}"
HOST_AMULE_INCOMING_DIR="${DOWNLOADS_ROOT}"

set_env_var "HOST_LIBRARY_DIR" "${HOST_LIBRARY_DIR}"
set_env_var "HOST_DOWNLOADS_DIR" "${HOST_DOWNLOADS_DIR}"
set_env_var "HOST_AMULE_INCOMING_DIR" "${HOST_AMULE_INCOMING_DIR}"
set_env_var "APP_LOCALE" "${APP_LOCALE}"
set_env_var "ZASCARR_DATA_DIR" "${ZASCARR_DATA_DIR}"

# Bug real (reportado): el contenedor corre fijo como UID 1000, pero
# ZASCARR_USER es un usuario de SISTEMA (useradd --system) — Debian le
# asigna el UID que tenga libre en su rango, casi nunca 1000. El
# importador podía copiar los tebeos del usuario (lectura vía "otros")
# pero no borrar el original tras importarlo (falta permiso de escritura
# en el directorio de descargas, propiedad de ese usuario). PUID/PGID
# (docker-entrypoint.sh) ajustan el UID interno del contenedor para que
# coincida con el usuario de servicio real — se resuelven aquí, no hace
# falta que el coleccionista sepa qué es un UID.
RESOLVED_UID="$(id -u "${ZASCARR_USER}" 2>/dev/null || echo 1000)"
RESOLVED_GID="$(getent group "${ZASCARR_GROUP}" 2>/dev/null | cut -d: -f3)"
RESOLVED_GID="${RESOLVED_GID:-1000}"
set_env_var "PUID" "${RESOLVED_UID}"
set_env_var "PGID" "${RESOLVED_GID}"

success "Biblioteca: ${LIBRARY}"
success "Descargas:  ${DOWNLOADS_ROOT}"
success "Idioma:     ${APP_LOCALE}"

info "Creando estructura de directorios..."

# Datos de los contenedores (Postgres, Redis, estado de VPN, portadas),
# separados del código (ZASCARR_ROOT) — mismo patrón que el resto de la
# suite *arr: código en /opt, datos en /var/lib.
mkdir -p "${ZASCARR_DATA_DIR}/"{postgres,redis,covers,vpn-state} || die \
    "No puedo crear ${ZASCARR_DATA_DIR}/. ¿Tienes permisos de escritura?"

# Biblioteca (donde el coleccionista haya dicho que vive).
# A3: solo tocamos (mkdir + chown) los directorios que ESTE script crea. Si
# ya existían, se respetan tal cual — nunca se re-propietan los tebeos que
# el usuario ya tenía.
for dir in "Comics" "Comics/_Specials" "Comics/_Omnibus" \
           "Manga" "BD" "Tebeos" "Fumetti" "Manhwa" \
           "Graphic Novels" "_Unsorted"; do
    if [[ ! -d "${LIBRARY}/${dir}" ]]; then
        mkdir -p "${LIBRARY}/${dir}" || die \
            "No encuentro el disco donde están tus tebeos (${LIBRARY}). ¿Está conectado y montado? ¿Tienes permisos de escritura?"
        # Directorio nuevo (quizá creado como root): se lo damos al UID/GID
        # real con el que corre el contenedor (PUID/PGID) para que pueda
        # escribir. Sin -R: solo el directorio.
        chown "${RESOLVED_UID}:${RESOLVED_GID}" "${LIBRARY}/${dir}" 2>/dev/null || true
    fi
done

# Descargas — se crea la carpeta EXACTA si no existe, sin inventar
# subcarpetas dentro (el importador ya escanea recursivamente: no necesita
# "comics/" ni "aMule/Incoming/" para encontrar los archivos). Si YA
# existían (el caso normal: Transmission/aMule llevan tiempo escribiendo
# ahí), se respetan tal cual (H5) — el contenedor necesitará entonces el
# UID/GID real de quien sea su dueño, que es justo lo que resuelve PUID/PGID.
for d in "${HOST_DOWNLOADS_DIR}" "${HOST_AMULE_INCOMING_DIR}"; do
    if [[ ! -d "${d}" ]]; then
        mkdir -p "${d}" || die \
            "No puedo crear ${d}. ¿Existe el disco de descargas y tienes permisos?"
        chown "${RESOLVED_UID}:${RESOLVED_GID}" "${d}" 2>/dev/null || true
    fi
done

# Solo los datos del propio bootstrap (creados más arriba) se chown en
# profundidad; la colección del usuario no se toca (H5).
#
# "postgres" y "redis" NO se tocan aquí a propósito (bug real, encontrado
# en una reejecución idempotente): sus contenedores autocorrigen el
# propietario de su directorio de datos a SU PROPIO usuario interno en
# cada arranque — pero solo en el arranque. Si bootstrap.sh se vuelve a
# ejecutar con los contenedores YA vivos (el caso normal de "ejecútalo de
# nuevo cuando quieras"), un chown aquí reescribe por debajo los ficheros
# de un Postgres en marcha, y las migraciones revientan con "Permission
# denied" en cuanto pierde acceso a sus propios ficheros. No hace falta:
# el propietario que deje el "mkdir -p" (root) es indiferente, porque
# postgres/redis arrancan como root y se autoasignan lo que necesitan.
chown -R "${ZASCARR_USER}:${ZASCARR_GROUP}" "${ZASCARR_DATA_DIR}/vpn-state" 2>/dev/null || \
    warn "Sin permisos para ajustar propietario de ${ZASCARR_DATA_DIR}/vpn-state"
# "covers" SÍ tiene que quedarse en el UID/GID real del contenedor
# (RESOLVED_UID/RESOLVED_GID = PUID/PGID): lo escribe el propio contenedor
# de ZascArr, que tras el ajuste de docker-entrypoint.sh corre como ese
# usuario SIN privilegios para autocorregirse (a diferencia de
# postgres/redis) — no es una preferencia de convención, es una
# restricción técnica. Aquí sí es seguro repetirlo: el contenedor nunca
# cambia su propio UID entre arranques (mismo PUID/PGID en el .env), así
# que no hay nada que se pueda corromper.
chown -R "${RESOLVED_UID}:${RESOLVED_GID}" "${ZASCARR_DATA_DIR}/covers" 2>/dev/null || \
    warn "Sin permisos para ajustar propietario de ${ZASCARR_DATA_DIR}/covers"
success "Directorios creados en ${LIBRARY}"

info "Validando .env..."
grep -q "DB_PASSWORD=cambia_esto_ahora" "${ENV_FILE}" && \
    die "DB_PASSWORD tiene el valor por defecto. Edita ${ENV_FILE} y pon una contraseña segura."
success ".env válido"

# Bug real (reportado): el .env vive en ZASCARR_ROOT (el padre), pero Docker
# Compose por defecto solo busca .env en el directorio desde el que se
# invoca (el "project directory"), que para cualquiera que haga
# "cd ${SCRIPT_DIR} && docker compose ..." a mano es SCRIPT_DIR, no
# ZASCARR_ROOT. Sin --env-file explícito, Compose no lo encuentra y arranca
# con los valores por defecto de docker-compose.yml (incluida la contraseña
# de la BD) en silencio — así fue como un "docker compose up -d" manual dejó
# un contenedor en bucle de reinicio la primera vez que pasó.
#
# Arreglo estructural (no solo documentación): un symlink SCRIPT_DIR/.env ->
# ENV_FILE hace que el descubrimiento POR DEFECTO de Compose ya encuentre el
# .env real sin que nadie tenga que acordarse de --env-file. El fichero de
# verdad sigue viviendo en ZASCARR_ROOT (a salvo de un "git reset --hard" de
# rollback.sh); el symlink es solo el puente, está en .gitignore y se
# recrea aquí en cada ejecución (idempotente).
if [[ -e "${SCRIPT_DIR}/.env" || -L "${SCRIPT_DIR}/.env" ]] && [[ "$(readlink -f "${SCRIPT_DIR}/.env" 2>/dev/null)" != "$(readlink -f "${ENV_FILE}")" ]]; then
    rm -f "${SCRIPT_DIR}/.env"
fi
ln -sf "${ENV_FILE}" "${SCRIPT_DIR}/.env" || \
    warn "No pude crear el enlace ${SCRIPT_DIR}/.env -> ${ENV_FILE}. Un 'docker compose' sin --env-file ejecutado desde ${SCRIPT_DIR} no verá tu configuración."

info "Levantando PostgreSQL y Redis..."
cd "${SCRIPT_DIR}" || die "No puedo entrar en el repo (${SCRIPT_DIR})."
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d postgres redis || die \
    "No pude levantar PostgreSQL/Redis. Revisa el detalle con: docker compose -f ${COMPOSE_FILE} logs postgres"

info "Esperando a PostgreSQL..."
MAX=60; ELAPSED=0
until docker compose -f "${COMPOSE_FILE}" exec -T postgres pg_isready -U comics_admin -d zascarr -q 2>/dev/null; do
    ELAPSED=$((ELAPSED+2))
    [[ $ELAPSED -ge $MAX ]] && die "PostgreSQL no responde tras ${MAX}s.\n  Revisa con: docker compose -f ${COMPOSE_FILE} logs postgres"
    echo -n "."; sleep 2
done
echo ""; success "PostgreSQL listo"

info "Construyendo la imagen de ZascArr..."
cd "${SCRIPT_DIR}" || die "No puedo entrar en el repo (${SCRIPT_DIR})."
# A8 (bug real, reportado): las migraciones corrían en el HOST, vía
# "pip install --break-system-packages -e ." — origen de la clase de bugs
# más cara de la sesión (conflicto typing_extensions de Debian/apt, M3;
# más el propio riesgo de tocar el Python del sistema en una Pi real).
# Ahora se construye la imagen explícitamente aquí, ANTES de migrar, y se
# migra y se arranca con esa MISMA imagen — nunca se instala nada de
# Python en el host, la única fuente de dependencias es la imagen Docker.
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" build zascarr || die \
    "No pude construir la imagen de ZascArr. Revisa el detalle con: docker compose -f ${COMPOSE_FILE} build zascarr"

info "Corriendo migraciones Alembic (dentro del contenedor)..."
# DATABASE_URL ya lo resuelve el propio docker-compose.yml desde .env
# (mismo mecanismo que usa el servicio "zascarr" al arrancar) — apuntando
# a "postgres:5432" por nombre de servicio en la red interna de Docker, no
# a "127.0.0.1:5432"; no hace falta reconstruirlo a mano leyendo el .env.
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" run --rm zascarr \
    alembic upgrade head || die \
    "Las migraciones de la base de datos fallaron. Revisa con: docker compose -f ${COMPOSE_FILE} logs postgres"
success "Migraciones aplicadas"

info "Levantando ZascArr..."
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" up -d zascarr || die \
    "No pude arrancar ZascArr. Revisa el detalle con: docker compose -f ${COMPOSE_FILE} logs zascarr"

info "Verificando healthcheck..."
MAX=30; ELAPSED=0
until curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; do
    ELAPSED=$((ELAPSED+2))
    [[ $ELAPSED -ge $MAX ]] && warn "ZascArr aún no responde. Revisa:\n  docker compose -f ${COMPOSE_FILE} logs zascarr" && break
    echo -n "."; sleep 2
done
echo ""

HEALTH=$(curl -sf http://127.0.0.1:8000/api/health 2>/dev/null || echo '{"status":"unreachable"}')
echo -e "\n${B}Estado del sistema:${N}"
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"

echo -e "\n${B}====================================${N}"
echo -e "${G}${B}  Bootstrap completado${N}"
echo -e "${B}====================================${N}\n"
echo "  ZascArr:      http://127.0.0.1:8000  (E1: estado del sistema, en español)"
echo "  API (para curiosos): http://127.0.0.1:8000/api/docs"
echo "  Kavita:           http://127.0.0.1:5000  (si está instalado)"
echo "  Prowlarr:         http://127.0.0.1:9696  (si está instalado)"
echo ""
echo "  Logs en tiempo real:"
echo "    docker compose -f ${COMPOSE_FILE} logs -f zascarr"
echo ""
curl -sf http://127.0.0.1:5000 >/dev/null 2>&1 || \
    warn "Kavita no detectado en :5000. Instala con:\n  sudo bash ${SCRIPT_DIR}/scripts/kavita.sh install"
