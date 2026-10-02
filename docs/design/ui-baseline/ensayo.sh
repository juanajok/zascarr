#!/usr/bin/env bash
# Entorno AISLADO para la línea base de la UI (V0). Herramienta de desarrollo, fuera del paquete.
#
#   UI_BASE_DATOS=/ruta/nueva ./ensayo.sh preparar    comprueba, levanta el stack y siembra
#   UI_BASE_DATOS=/ruta/nueva ./ensayo.sh dc <args>   `docker compose` SOLO sobre el stack de ensayo
#   UI_BASE_DATOS=/ruta/nueva ./ensayo.sh bajar       lo desmonta (no borra los datos)
#
# Todo pasa por `dc`: nunca se usan `docker stop|restart|start <nombre>` globales. Si alguna
# comprobación falla, NO se arranca nada.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${AQUI}/../../.." && pwd)"
PROYECTO="zascarr-uibase"
PUERTO=18000
DATOS="${UI_BASE_DATOS:-}"

die() { echo "ensayo.sh: $*" >&2; exit 1; }

# Ruta ESCRITA frente a ruta EFECTIVA (la misma distinción que A9): `mkdir -p`, `: >` y los
# montajes de Docker SIGUEN los enlaces simbólicos, así que comparar el texto de la ruta no basta.
# Se valida ANTES de crear ninguna carpeta ni marca.
comprobar_rutas_efectivas() {
    local real="$1" sub ruta efectiva enlace
    # La carpeta de ensayo en sí no puede llegar por un enlace (ni ella ni ningún padre).
    if [[ "$(realpath -m "${DATOS}")" != "$(realpath -m -s "${DATOS}")" ]]; then
        die "UI_BASE_DATOS pasa por un enlace simbólico: usa la ruta real."
    fi
    # Cada subruta que se va a crear, marcar o montar: ni es un enlace (tampoco roto) ni su
    # destino efectivo sale de la carpeta de ensayo.
    for sub in data data/postgres data/redis data/covers data/vpn-state lib lib/.ui-baseline \
               dl .env .ui-baseline .config.json; do
        ruta="${real}/${sub}"
        if [[ -L "${ruta}" ]]; then
            die "${ruta} es un enlace simbólico (hacia $(readlink "${ruta}")): no se acepta en un entorno de ensayo."
        fi
        efectiva="$(realpath -m "${ruta}")"
        [[ "${efectiva}" == "${real}/"* ]] || die "${ruta} resuelve a ${efectiva}, fuera de ${real}."
    done
    # Y ningún enlace dentro (`find -type l` también ve los rotos): un `lib/_Unsorted` enlazado
    # haría que `sembrar.py` escribiera fuera.
    if [[ -d "${real}" ]]; then
        enlace="$(find "${real}" -maxdepth 4 -type l -print -quit 2>/dev/null || true)"
        [[ -z "${enlace}" ]] || die "hay un enlace simbólico dentro del entorno de ensayo: ${enlace}"
    fi
}

comprobar_destino() {
    [[ -n "${DATOS}" ]] || die "falta UI_BASE_DATOS (carpeta NUEVA o ya creada por este script)."
    [[ "${DATOS}" = /* ]] || die "UI_BASE_DATOS debe ser una ruta absoluta."
    local real; real="$(realpath -m "${DATOS}")"
    # Nunca un destino que pueda ser de una instalación real.
    local prohibido
    for prohibido in /var/lib/zascarr /opt/zascarr /media /srv /home/media; do
        [[ "${real}/" != "${prohibido}/"* ]] || die "${real} cae dentro de ${prohibido}: puede ser de una instalación real."
    done
    [[ "${real}/" != "${REPO}/"* ]] || die "los datos de ensayo no pueden estar dentro del repositorio."
    # Solo se acepta una carpeta inexistente, vacía o ya marcada por este script.
    if [[ -e "${real}" ]]; then
        if [[ -n "$(ls -A "${real}" 2>/dev/null)" && ! -f "${real}/.ui-baseline" ]]; then
            die "${real} existe, no está vacía y no es un entorno de ensayo (falta .ui-baseline)."
        fi
    fi
    comprobar_rutas_efectivas "${real}"
    DATOS="${real}"
}

dc() {
    docker compose -p "${PROYECTO}" -f "${REPO}/docker-compose.yml" -f "${AQUI}/compose.ensayo.yml" \
        --env-file "${DATOS}/.env" "$@"
}

# Resuelve el compose COMBINADO y rechaza cualquier cosa que pueda tocar producción.
comprobar_compose() {
    dc config --format json > "${DATOS}/.config.json" || die "no se pudo resolver el compose de ensayo."
    python3 - "${DATOS}" "${PUERTO}" <<'PY' || die "el compose de ensayo no está aislado (ver arriba)."
import json, os, sys
datos, puerto = sys.argv[1], int(sys.argv[2])
base = os.path.realpath(datos)
cfg = json.load(open(f"{datos}/.config.json"))
errores = []
if cfg.get("name") != "zascarr-uibase":
    errores.append(f"proyecto inesperado: {cfg.get('name')}")
globales = {"zascarr-db", "zascarr-cache", "zascarr-orquestador"}
for nombre, s in cfg["services"].items():
    cn = s.get("container_name")
    if cn in globales or not (cn or "").startswith("zascarr-uibase-"):
        errores.append(f"{nombre}: container_name {cn!r} no es de ensayo")
    for p in s.get("ports", []):
        pub, host = p.get("published"), p.get("host_ip")
        if not (nombre == "zascarr" and str(pub) == str(puerto) and host == "127.0.0.1"):
            errores.append(f"{nombre}: publica {host}:{pub} (solo se permite 127.0.0.1:{puerto} en zascarr)")
    for v in s.get("volumes", []):
        src = v.get("source", "")
        efectiva = os.path.realpath(src)   # destino REAL: sigue los enlaces simbólicos
        if v.get("type") == "bind" and not (efectiva == base or efectiva.startswith(base + os.sep)):
            errores.append(f"{nombre}: monta {src} (efectivo {efectiva}), fuera de {base}")
for r in cfg.get("networks", {}).values():
    if (r.get("name") or "").startswith("zascarr_"):
        errores.append(f"red global: {r.get('name')}")
if errores:
    print("\n".join("  - " + e for e in errores), file=sys.stderr)
    sys.exit(1)
PY
}

# Contenedores del proyecto de ensayo que existan AHORA, uno por línea. Aborta si Docker no
# responde: «no pude comprobar» NO equivale a «no hay nada». Une la etiqueta del proyecto de
# Compose y el prefijo del nombre, porque `container_name` explícito no se aísla por carpeta.
contenedores_del_ensayo() {
    local por_etiqueta por_nombre nombre
    por_etiqueta="$(docker ps -a --filter "label=com.docker.compose.project=${PROYECTO}" \
        --format '{{.Names}}')" || die "Docker no responde (docker ps): no puedo comprobar si hay un stack de ensayo; no actúo."
    por_nombre="$(docker ps -a --format '{{.Names}}')" \
        || die "Docker no responde (docker ps): no puedo comprobar si hay un stack de ensayo; no actúo."
    {
        printf '%s\n' "${por_etiqueta}"
        while IFS= read -r nombre; do
            case "${nombre}" in "${PROYECTO}"-*) printf '%s\n' "${nombre}" ;; esac
        done <<< "${por_nombre}"
    } | sed '/^$/d' | sort -u
}

# El nombre de proyecto `zascarr-uibase` es único por máquina: si OTRA carpeta de datos (otra
# sesión, otro worktree) tiene SU stack, `dc` o `bajar` desde ésta lo tocarían igual. Se mira
# CADA contenedor existente —también un stack parcial (solo Postgres y Redis, por ejemplo)— y
# se exige que TODOS sus montajes cuelguen de ESTA carpeta; basta uno ajeno, o no poder
# acreditar ninguno, para abortar. Las rutas se comparan como rutas (`[[ == "…"* ]]`), no como
# expresión regular.
comprobar_propietario() {
    local contenedores nombre montajes origen n
    # OJO: `die` dentro de `$(…)` solo sale del subshell; el estado se propaga a mano.
    contenedores="$(contenedores_del_ensayo)" || exit 1
    [[ -n "${contenedores}" ]] || return 0               # consulta correcta y sin recursos
    while IFS= read -r nombre; do
        montajes="$(docker inspect "${nombre}" \
            --format '{{range .Mounts}}{{.Source}}{{"\n"}}{{end}}' 2>/dev/null)" \
            || die "no pude comprobar los montajes de ${nombre}; no actúo."
        n=0
        while IFS= read -r origen; do
            [[ -n "${origen}" ]] || continue
            n=$((n + 1))
            [[ "${origen}" == "${DATOS}/"* ]] \
                || die "${nombre} monta ${origen}: el stack zascarr-uibase en marcha pertenece a OTRA carpeta de datos; no lo toco."
        done <<< "${montajes}"
        [[ "${n}" -gt 0 ]] || die "no puedo acreditar de quién es ${nombre} (sin montajes); no lo toco."
    done <<< "${contenedores}"
}

preparar() {
    comprobar_destino
    command -v docker >/dev/null || die "falta docker."
    if ss -ltn "sport = :${PUERTO}" 2>/dev/null | grep -q LISTEN; then
        die "el puerto ${PUERTO} ya está en uso."
    fi
    local existentes
    existentes="$(contenedores_del_ensayo)" || exit 1   # `die` en $(…) no sale del script
    if [[ -n "${existentes}" ]]; then
        die "ya hay recursos de un stack de ensayo (zascarr-uibase-*): ejecuta 'bajar' antes (o espera a la otra sesión)."
    fi
    mkdir -p "${DATOS}"/data/{postgres,redis,covers,vpn-state} "${DATOS}/lib" "${DATOS}/dl"
    : > "${DATOS}/.ui-baseline"
    : > "${DATOS}/lib/.ui-baseline"          # lo exige sembrar.py dentro del contenedor
    cat > "${DATOS}/.env" <<ENV
DB_PASSWORD=linea_base_local_no_usar
ZASCARR_DATA_DIR=${DATOS}/data
HOST_LIBRARY_DIR=${DATOS}/lib
HOST_DOWNLOADS_DIR=${DATOS}/dl
HOST_AMULE_INCOMING_DIR=${DATOS}/dl
PUID=$(id -u)
PGID=$(id -g)
TZ=Europe/Madrid
APP_LOCALE=es
FORUM_ENABLED=false
TRANSMISSION_URL=http://127.0.0.1:1
AMULE_URL=http://127.0.0.1:1
PROWLARR_URL=http://127.0.0.1:1
ENV
    comprobar_compose
    echo "ensayo.sh: aislamiento comprobado; levantando el stack '${PROYECTO}'…"
    dc build zascarr
    dc up -d postgres redis
    local i
    for i in $(seq 40); do
        docker exec zascarr-uibase-db pg_isready -U comics_admin -d zascarr -q && break
        sleep 2
    done
    dc run --rm -T zascarr alembic upgrade head
    dc run --rm -T zascarr python - < "${AQUI}/sembrar.py"
    dc up -d zascarr
    echo "ensayo.sh: listo en http://127.0.0.1:${PUERTO}"
}

case "${1:-}" in
    preparar) comprobar_destino; preparar ;;
    dc)       shift; comprobar_destino; [[ -f "${DATOS}/.env" ]] || die "no hay entorno preparado en ${DATOS}."
              comprobar_compose; comprobar_propietario; dc "$@" ;;
    bajar)    comprobar_destino; [[ -f "${DATOS}/.env" ]] || die "no hay entorno preparado en ${DATOS}."
              comprobar_compose; comprobar_propietario; dc down ;;
    *)        sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
