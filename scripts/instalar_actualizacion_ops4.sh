#!/usr/bin/env bash
# instalar_actualizacion_ops4.sh — provisiona OPS4 sin habilitarlo por defecto.
#
# Crea clave dedicada y registro durable, copia auxiliar/módulos/unidades y,
# solo con --activar, habilita el socket. No cambia la UI ni la bandera
# OPS4_ACTUALIZACION_HABILITADA. Con --dry-run no escribe; --quitar retira
# unidades y binarios, conservando clave/datos salvo --borrar-clave.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${ZASCARR_ROOT}/.env}"
DATA_DIR="${OPS4_DATA_DIR:-${ZASCARR_DATA_DIR:-/var/lib/zascarr}}"
OPS_DIR="${DATA_DIR}/ops"
OPS4_DIR="${DATA_DIR}/ops4"
DEST_AUX="/usr/local/lib/zascarr/zascarr-actualizar-aux"
DEST_LIB="/usr/local/lib/zascarr"
DEST_UNITS="/etc/systemd/system"
leer_env() { [[ -f "${ENV_FILE}" ]] && sed -n "s/^$1=//p" "${ENV_FILE}" | tail -1 | tr -d "\"'" || true; }
GRUPO="${OPS4_GROUP:-${OPS_GROUP:-}}"
if [[ -z "${GRUPO}" ]]; then
    gid="$(leer_env PGID)"; gid="${gid:-1000}"
    GRUPO="$(getent group "${gid}" 2>/dev/null | cut -d: -f1 || true)"
fi
if [[ -z "${GRUPO}" ]] || ! getent group "${GRUPO}" >/dev/null 2>&1; then
    echo "No se pudo resolver el grupo de servicio (PGID/.env u OPS4_GROUP); no se instala nada." >&2
    exit 1
fi
if [[ "${ZASCARR_PRUEBAS:-}" == "1" ]]; then
    DEST_AUX="${OPS4_DEST_AUX:-${DEST_AUX}}"
    DEST_LIB="${OPS4_DEST_LIB:-${DEST_LIB}}"
    DEST_UNITS="${OPS4_DEST_UNIDADES:-${DEST_UNITS}}"
fi

DRY_RUN=0; YES=0; ACTIVAR=0; SIN_SYSTEMD=0; QUITAR=0; BORRAR_CLAVE=0
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=1 ;;
        --yes|-y) YES=1 ;;
        --activar) ACTIVAR=1 ;;
        --sin-systemd) SIN_SYSTEMD=1 ;;
        --quitar) QUITAR=1 ;;
        --borrar-clave) BORRAR_CLAVE=1 ;;
        -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
        *) echo "Opción desconocida: ${arg}" >&2; exit 2 ;;
    esac
done
if (( BORRAR_CLAVE )) && (( ! QUITAR )); then
    echo "--borrar-clave solo se usa con --quitar." >&2; exit 2
fi
if (( ! DRY_RUN )) && [[ "${ZASCARR_PRUEBAS:-}" != "1" ]]; then
    [[ "$(id -u)" -eq 0 ]] || { echo "Ejecútalo con sudo." >&2; exit 1; }
fi
if ! getent group "${GRUPO}" >/dev/null 2>&1; then
    echo "No existe el grupo ${GRUPO}; no se instala nada." >&2; exit 1
fi

say() { printf '%s\n' "$*"; }
run() {
    if (( DRY_RUN )); then
        printf '[dry-run] %s\n' "$*"
    else
        "$@"
    fi
}
sustituir() {
    shopt -u patsub_replacement 2>/dev/null || true
    local texto
    texto="$(cat "$1"; printf x)"
    texto="${texto%x}"
    texto="${texto//@ZASCARR_DATA_DIR@/${DATA_DIR}}"
    texto="${texto//@GRUPO@/${GRUPO}}"
    texto="${texto//@REPO@/${REPO_DIR}}"
    if [[ "${texto}" =~ @[A-Z_]+@ ]]; then
        echo "Marcadores sin sustituir en $1" >&2; return 1
    fi
    printf '%s' "${texto}"
}
copiar() {
    local origen="$1" destino="$2" modo="$3" tmp
    tmp="$(mktemp)"
    if [[ "${origen}" == *.service || "${origen}" == *.socket ]]; then
        sustituir "${origen}" > "${tmp}"
    else
        cat "${origen}" > "${tmp}"
    fi
    run install -D -m "${modo}" "${tmp}" "${destino}"
    rm -f "${tmp}"
}
crear_dirs() {
    run install -d -m 0750 "${OPS_DIR}"
    run install -d -m 0700 "${OPS4_DIR}"
    run install -d -m 0700 "${OPS4_DIR}/consumidos"
    # H-5: la app (PUID:PGID, montaje ro) debe leer el estado 0640 root:<grupo>;
    # el grupo del fichero lo toma el escritor del directorio. Si no se puede
    # fijar el dueño, se aborta: un estado ilegible es "sin noticias" permanente.
    if (( ! DRY_RUN )) && [[ "${ZASCARR_PRUEBAS:-}" != "1" ]]; then
        chown "root:${GRUPO}" "${OPS_DIR}"
    fi
}
crear_clave() {
    local key="${OPS_DIR}/actualizar.key" tmp
    if [[ -f "${key}" ]]; then say "Clave existente: se conserva."; return; fi
    if (( DRY_RUN )); then say "[dry-run] crear ${key} (0440 root:${GRUPO})"; return; fi
    tmp="$(umask 077; mktemp "${OPS_DIR}/.actualizar.key.XXXXXX")"
    python3 -c 'import secrets; print(secrets.token_hex(32))' > "${tmp}"
    chmod 0440 "${tmp}"
    if [[ "${ZASCARR_PRUEBAS:-}" != "1" ]]; then chown "root:${GRUPO}" "${tmp}"; fi
    mv -n "${tmp}" "${key}"
    rm -f "${tmp}"
    say "Clave de actualización creada."
}

if (( QUITAR )); then
    say "Retirando OPS4..."
    if (( ! SIN_SYSTEMD )); then
        run systemctl disable --now zascarr-actualizar.socket 2>/dev/null || true
    fi
    run rm -f "${DEST_UNITS}/zascarr-actualizar.socket" \
        "${DEST_UNITS}/zascarr-actualizar@.service" \
        "${DEST_UNITS}/zascarr-actualizar.service" \
        "${DEST_AUX}" "${DEST_LIB}/protocolo_actualizar_v4_ops4.py" \
        "${DEST_LIB}/verificador_autorizacion_ops4.py" \
        "${DEST_LIB}/registro_repeticiones_ops4.py" \
        "${DEST_LIB}/escritor_estado_actualizar_ops4.py" \
        "${DEST_LIB}/zascarr-estado-actualizar-ops4"
    if (( ! SIN_SYSTEMD )); then run systemctl daemon-reload || true; fi
    if (( BORRAR_CLAVE )); then run rm -f "${OPS_DIR}/actualizar.key"; say "Clave borrada."; else
        say "Se conserva ${OPS_DIR}/actualizar.key."
    fi
    exit 0
fi

say "Repo: ${REPO_DIR}"
say "Datos OPS4: ${OPS4_DIR}"
say "Socket auxiliar: ${OPS_DIR}/actualizar.sock"
if (( ! YES && ! DRY_RUN )); then
    read -r -p "¿Provisionar OPS4 (sin habilitar la UI)? [s/N] " respuesta
    [[ "${respuesta}" == "s" || "${respuesta}" == "S" ]] || { echo "Cancelado."; exit 1; }
fi

crear_dirs
crear_clave
copiar "${REPO_DIR}/deploy/ops/zascarr_actualizar_aux.py" "${DEST_AUX}" 0755
copiar "${REPO_DIR}/deploy/ops/estado_actualizar_ops4.py" \
    "${DEST_LIB}/zascarr-estado-actualizar-ops4" 0755
for modulo in protocolo_actualizar_v4_ops4.py verificador_autorizacion_ops4.py \
              registro_repeticiones_ops4.py escritor_estado_actualizar_ops4.py; do
    copiar "${REPO_DIR}/deploy/ops/${modulo}" "${DEST_LIB}/${modulo}" 0644
done
for unidad in zascarr-actualizar.socket zascarr-actualizar@.service \
              zascarr-actualizar.service; do
    copiar "${REPO_DIR}/deploy/systemd/${unidad}" "${DEST_UNITS}/${unidad}" 0644
done

if (( ! SIN_SYSTEMD )); then
    run systemctl daemon-reload
    if (( ACTIVAR )); then
        run systemctl start zascarr-actualizar.socket
        say "Socket iniciado (no persistente). La unidad fija puede ejecutar update.sh si recibe una petición válida."
        say "La bandera de UI depende de OPS4_ACTUALIZACION_HABILITADA (por defecto false)."
    else
        say "Unidades instaladas, NO activadas. Usa --activar para iniciar el socket."
    fi
else
    say "Instalación de archivos completada; systemd omitido (--sin-systemd)."
fi
say "La bandera de UI es OPS4_ACTUALIZACION_HABILITADA (por defecto false)."
