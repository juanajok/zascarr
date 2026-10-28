#!/usr/bin/env bash
# Utilidades de los escenarios de credenciales (se ejecutan como root en un sistema DESECHABLE: ver
# tests/_sistema_aislado.py). Imprimen `PASS id detalle` / `FAIL id detalle`; JAMÁS un valor de credencial
# (solo longitudes, huellas y modos).
set -uo pipefail

REPO="${REPO:?falta REPO (ruta del repo con bootstrap.sh)}"
[[ "$(id -u)" -eq 0 ]] || { echo "FAIL 00-root solo en un sistema desechable y como root"; exit 2; }

pass() { echo "PASS $1 ${2:-}"; }
fail() { echo "FAIL $1 ${2:-}"; }
# afirmar ID "texto" comando… : PASS si el comando sale 0.
afirmar() {
    local id="$1" texto="$2"; shift 2
    if "$@" >/dev/null 2>&1; then pass "${id}" "${texto}"; else fail "${id}" "${texto}"; fi
}
# negar ID "texto" comando… : PASS si el comando FALLA (lo que se intentaba hacer fue denegado).
negar() {
    local id="$1" texto="$2"; shift 2
    if "$@" >/dev/null 2>&1; then fail "${id}" "${texto} (se pudo hacer)"; else pass "${id}" "${texto}"; fi
}
como() { local u="$1"; shift; runuser -u "${u}" -- "$@"; }
huella() { sha256sum -- "$1" 2>/dev/null | cut -c1-16; }
modo() { stat -c '%a %U:%G' -- "$1" 2>/dev/null; }

SVC=svcprueba
OTRO=otroprueba
preparar_usuarios() {
    getent group "${SVC}" >/dev/null || groupadd --system "${SVC}"
    getent passwd "${SVC}" >/dev/null || useradd --system --no-create-home --shell /usr/sbin/nologin -g "${SVC}" "${SVC}"
    getent passwd "${OTRO}" >/dev/null || useradd --no-create-home --shell /usr/sbin/nologin "${OTRO}"
}

# Un directorio de trabajo que TODOS los usuarios pueden atravesar: si no, «denegado» podría ser solo que no
# pueden entrar en el directorio temporal (0700), y la prueba no demostraría nada sobre el `.env`.
nuevo_trabajo() {
    W="$(mktemp -d)"
    chmod 755 "${W}"
    mkdir -p "${W}/bin" "${W}/opt"
    chmod 755 "${W}/bin" "${W}/opt"
}

# Copia al «equipo» lo mínimo que el instalador necesita (sin .git ni pruebas) en RAIZ/zascarr.
copiar_repo() {
    local raiz="$1" d="${1}/zascarr"
    mkdir -p "${d}/scripts"
    cp -a "${REPO}/bootstrap.sh" "${REPO}/docker-compose.yml" "${REPO}/.env.example" "${d}/"
    cp -a "${REPO}/scripts/." "${d}/scripts/"
    [[ -f "${REPO}/Dockerfile" ]] && cp -a "${REPO}/Dockerfile" "${d}/"
}

# Instalación «heredada»: lo que dejaban las versiones anteriores del instalador (todo del usuario de servicio,
# `.env` legible por todos). `valor` es la contraseña SINTÉTICA del `.env` (vacío = sin `.env`).
instalacion_heredada() {
    local raiz="$1" valor="${2:-}"
    mkdir -p "${raiz}"
    copiar_repo "${raiz}"
    if [[ -n "${valor}" ]]; then
        sed "s#^DB_PASSWORD=.*#DB_PASSWORD=${valor}#" "${raiz}/zascarr/.env.example" > "${raiz}/.env"
        ln -sf "${raiz}/.env" "${raiz}/zascarr/.env"
        chmod 644 "${raiz}/.env"
    fi
    chown -R "${SVC}:${SVC}" "${raiz}"
    chmod 755 "${raiz}"
}

# `docker` de pega: acepta todo salvo `up -d postgres`, donde anota (SIN el valor) lo que Compose vería y falla,
# para detener el instalador justo ahí. Todo lo anterior es lo que se está probando.
poner_docker_de_pega() {
    cat > "${W}/bin/docker" <<'STUB'
#!/bin/sh
echo "docker $*" >> "$STUB_LOG"
# Como Compose de verdad: un --env-file que no se puede leer es un error (y nada se hace).
prev=""
for a in "$@"; do
    if [ "$prev" = "--env-file" ] && [ ! -r "$a" ]; then echo "permission denied: $a" >&2; exit 1; fi
    prev="$a"
done
case "$*" in
  *pg_dump*)
    cat <<'SQL'
--
-- PostgreSQL database dump
--
COPY public.alembic_version (version_num) FROM stdin;
0020
\.
COPY public.series (id) FROM stdin;
\.
COPY public.files (id) FROM stdin;
\.
COPY public.wishlist (id) FROM stdin;
\.
SQL
    exit 0 ;;
  *"up -d postgres"*)
    f=""; prev=""
    for a in "$@"; do [ "$prev" = "--env-file" ] && f="$a"; prev="$a"; done
    if [ -n "$f" ] && [ -r "$f" ]; then
        v=$(grep '^DB_PASSWORD=' "$f" | tail -1 | cut -d= -f2-)
        echo "len=${#v}" >> "$STUB_LOG.visto"
        printf '%s' "$v" | sha256sum | cut -c1-16 >> "$STUB_LOG.huellas"
    fi
    exit 1 ;;
esac
exit 0
STUB
    chmod 755 "${W}/bin/docker"
    : > "${W}/docker.log"
}

# Ejecuta el instalador REAL (bootstrap.sh) con el `docker` de pega. Salida en ${W}/salida.{out,err}.
ejecutar_instalador() {
    local raiz="$1"
    printf '%s\n%s\n%s\n' "${W}/biblioteca" "${W}/descargas" es | \
        env PATH="${W}/bin:${PATH}" STUB_LOG="${W}/docker.log" _ZASCARR_YA_ACTUALIZADO=1 \
            ZASCARR_DATA_DIR="${W}/datos" ZASCARR_USER="${SVC}" ZASCARR_GROUP="${SVC}" \
            bash "${raiz}/zascarr/bootstrap.sh" >"${W}/salida.out" 2>"${W}/salida.err"
    RC=$?
}
llego_a_postgres() { grep -q 'up -d postgres' "${W}/docker.log"; }
valor_de() { grep '^DB_PASSWORD=' "$1" 2>/dev/null | tail -1 | cut -d= -f2-; }
