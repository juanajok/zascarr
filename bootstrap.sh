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
        info "Ya existe un clon en ${ZASCARR_ROOT}/zascarr, lo reutilizo."
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

command -v python3 >/dev/null 2>&1 || {
    info "Instalando Python 3..."
    apt-get update -qq && apt-get install -y -qq python3 python3-pip || die \
        "No pude instalar Python 3 automáticamente. Instálalo a mano: sudo apt-get install -y python3 python3-pip"
}

python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null || die \
    "Necesito Python 3.11 o superior. Tu versión: $(python3 --version 2>&1). Actualízalo antes de continuar."

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

read -rp "¿Dónde caen tus descargas (Transmission/aMule)? [/media/data]: " ANS_DOWNLOADS || true
DOWNLOADS_ROOT="${ANS_DOWNLOADS:-/media/data}"

read -rp "¿Idioma de la interfaz? [es/en, por defecto es]: " ANS_LOCALE || true
APP_LOCALE="${ANS_LOCALE:-es}"
if [[ "${APP_LOCALE}" != "es" && "${APP_LOCALE}" != "en" ]]; then
    warn "Idioma '${APP_LOCALE}' no reconocido, uso 'es'."
    APP_LOCALE="es"
fi

HOST_LIBRARY_DIR="${LIBRARY}"
HOST_DOWNLOADS_DIR="${DOWNLOADS_ROOT}/downloads"
HOST_AMULE_INCOMING_DIR="${DOWNLOADS_ROOT}/aMule/Incoming"

set_env_var "HOST_LIBRARY_DIR" "${HOST_LIBRARY_DIR}"
set_env_var "HOST_DOWNLOADS_DIR" "${HOST_DOWNLOADS_DIR}"
set_env_var "HOST_AMULE_INCOMING_DIR" "${HOST_AMULE_INCOMING_DIR}"
set_env_var "APP_LOCALE" "${APP_LOCALE}"
set_env_var "ZASCARR_DATA_DIR" "${ZASCARR_DATA_DIR}"

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
        # Directorio nuevo (quizá creado como root): se lo damos al contenedor
        # (uid 1000) para que pueda escribir. Sin -R: solo el directorio.
        chown 1000:1000 "${LIBRARY}/${dir}" 2>/dev/null || true
    fi
done

# Descargas
mkdir -p "${HOST_DOWNLOADS_DIR}/comics" 2>/dev/null || \
    die "No puedo crear ${HOST_DOWNLOADS_DIR}/comics. ¿Existe el disco de descargas (${DOWNLOADS_ROOT}) y tienes permisos?"
mkdir -p "${HOST_AMULE_INCOMING_DIR}" 2>/dev/null || \
    die "No puedo crear ${HOST_AMULE_INCOMING_DIR}. ¿Existe el disco de descargas (${DOWNLOADS_ROOT}) y tienes permisos?"

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
# "covers" SÍ tiene que quedarse en uid 1000: lo escribe el propio
# contenedor de ZascArr, que corre como ese usuario fijo SIN privilegios
# para autocorregirse (a diferencia de postgres/redis) — no es una
# preferencia de convención, es una restricción técnica del Dockerfile.
# Aquí sí es seguro repetirlo: el contenedor de ZascArr nunca cambia su
# propio UID entre arranques, así que no hay nada que se pueda corromper.
chown -R 1000:1000 "${ZASCARR_DATA_DIR}/covers" 2>/dev/null || \
    warn "Sin permisos para ajustar propietario de ${ZASCARR_DATA_DIR}/covers"
success "Directorios creados en ${LIBRARY}"

info "Validando .env..."
grep -q "DB_PASSWORD=cambia_esto_ahora" "${ENV_FILE}" && \
    die "DB_PASSWORD tiene el valor por defecto. Edita ${ENV_FILE} y pon una contraseña segura."
success ".env válido"

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

info "Corriendo migraciones Alembic..."
# M6: leer DB_PASSWORD sin evaluar .env como shell (un "DB_PASSWORD=$(...)"
# no debe ejecutarse). cut -d= -f2- conserva contraseñas que contengan "=".
DB_PASSWORD="$(grep -E '^DB_PASSWORD=' "${ENV_FILE}" | head -n1 | cut -d= -f2-)"
export DATABASE_URL="postgresql+asyncpg://comics_admin:${DB_PASSWORD}@127.0.0.1:5432/zascarr"
cd "${SCRIPT_DIR}" || die "No puedo entrar en el repo (${SCRIPT_DIR})."
# -e . (no -e ".[dev]"): solo se necesita alembic + deps runtime para migrar;
# pytest/ruff/mypy no tienen que instalarse en el host de producción (L8).
# "command -v alembic", NUNCA "python3 -c 'import alembic'": estamos a punto
# de hacer cd a SCRIPT_DIR, que tiene su propia carpeta alembic/ (las
# migraciones) con el mismo nombre que el paquete instalado. "python3 -c"
# añade el cwd a sys.path y "import alembic" resolvería esa carpeta local en
# vez de la librería real — el check "pasaría" aunque pip install nunca se
# hubiera ejecutado, y el "alembic upgrade head" de más abajo fallaría con
# "orden no encontrada" en cualquier instalación de verdad desde cero.
command -v alembic >/dev/null 2>&1 || pip install --break-system-packages -e . -q || die \
    "No pude instalar las dependencias del proyecto. Ejecuta a mano para ver el error: pip install --break-system-packages -e ."
# "alembic", nunca "python3 -m alembic": estamos parados (cd de arriba)
# dentro del propio directorio del repo, que tiene su propia carpeta
# alembic/ (las migraciones) con el mismo nombre que el paquete instalado.
# "python3 -m alembic" resuelve esa carpeta local en vez de la librería
# real y falla con "cannot be directly executed" (ver Makefile).
alembic upgrade head || die \
    "Las migraciones de la base de datos fallaron. Revisa con: docker compose -f ${COMPOSE_FILE} logs postgres"
success "Migraciones aplicadas"

info "Levantando ZascArr..."
cd "${SCRIPT_DIR}" || die "No puedo entrar en el repo (${SCRIPT_DIR})."
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
