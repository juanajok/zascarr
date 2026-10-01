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
import json, sys
datos, puerto = sys.argv[1], int(sys.argv[2])
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
        if v.get("type") == "bind" and not src.startswith(datos + "/"):
            errores.append(f"{nombre}: monta {src}, fuera de {datos}")
for r in cfg.get("networks", {}).values():
    if (r.get("name") or "").startswith("zascarr_"):
        errores.append(f"red global: {r.get('name')}")
if errores:
    print("\n".join("  - " + e for e in errores), file=sys.stderr)
    sys.exit(1)
PY
}

preparar() {
    comprobar_destino
    command -v docker >/dev/null || die "falta docker."
    if ss -ltn "sport = :${PUERTO}" 2>/dev/null | grep -q LISTEN; then
        die "el puerto ${PUERTO} ya está en uso."
    fi
    if docker ps -a --format '{{.Names}}' | grep -qx -e zascarr-uibase-db -e zascarr-uibase-app; then
        die "ya hay un stack de ensayo (zascarr-uibase-*): ejecuta 'bajar' antes."
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
              comprobar_compose; dc "$@" ;;
    bajar)    comprobar_destino; [[ -f "${DATOS}/.env" ]] || die "no hay entorno preparado en ${DATOS}."
              dc down ;;
    *)        sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
