#!/usr/bin/env bash
# =============================================================================
# _espacio.sh — único helper de espacio libre (#123b).
#
# NO se ejecuta solo: se carga con `source` desde `_comun.sh` o desde
# `restaurar_datos.sh`. Quien lo carga debe haber definido `COMPOSE` (y
# `DB_USER`/`DB_NAME` si usa `tamano_bd_kb`).
#
# Único umbral: `necesario + 10 % + 64 MiB`. No borra ni mueve nada: solo mide
# y devuelve un error con cifras y una acción segura. Las comprobaciones de
# montaje/dispositivo siguen en `backup.sh`/`instalar_backup.sh`; este fichero
# no las duplica.
# =============================================================================

if [[ -n "${_ZASCARR_ESPACIO_CARGADO:-}" ]]; then
    return 0
fi
_ZASCARR_ESPACIO_CARGADO=1

# Devuelve KiB libres; vacío/0 si no se puede medir.
espacio_libre_kb() {
    df -Pk "$1" 2>/dev/null | awk 'NR == 2 { print $4 }'
}

espacio_postgres_libre_kb() {
    "${COMPOSE[@]}" exec -T postgres df -Pk /var/lib/postgresql/data 2>/dev/null \
        | awk 'NR == 2 { print $4 }'
}

# KiB que ocupa la BD; VACÍO si no se pudo medir (p. ej. PostgreSQL parado). Nunca falla: bajo `set -e` un fallo aquí
# mataría al script llamador en la asignación, sin mensaje. Quien llama decide, y `exigir_espacio_kb` no trata un
# vacío como 0 (fallaría abierto).
tamano_bd_kb() {
    local salida
    salida="$("${COMPOSE[@]}" exec -T postgres psql -U "${DB_USER}" -d "${DB_NAME}" -At \
        -c "select (pg_database_size(current_database()) / 1024)::bigint" 2>/dev/null)" || return 0
    printf '%s' "${salida}" | tr -d '[:space:]'
}

# KiB que ocupará un .sql.gz descomprimido, EXACTOS. `gzip -l` guarda el tamaño sin comprimir en 32 bits y con más de
# 4 GiB lo subestima (da módulo 2^32); se cuenta el flujo descomprimido. Vacío si no se pudo leer.
tamano_descomprimido_kb() {
    local bytes
    bytes="$(gzip -dc "$1" 2>/dev/null | wc -c)" || return 0
    bytes="${bytes//[[:space:]]/}"
    [[ "${bytes}" =~ ^[0-9]+$ ]] || return 0
    printf '%s' "$(( (bytes + 1023) / 1024 ))"
}

# Comprueba `libre` (KiB) contra `necesario` + 10 % + 64 MiB. Devuelve 1 y explica en español si no cabe, y 2 si no se
# pudo medir lo necesario (nunca se toma como 0: sería dar por bueno lo que no se sabe); los scripts deciden si
# escriben estado y salen.
exigir_espacio_kb() {
    local libre="$1" necesario="$2" contexto="$3" margen total
    if ! [[ "${necesario}" =~ ^[0-9]+$ ]]; then
        printf 'ERROR: No pude medir cuánto espacio hace falta para %s (¿está PostgreSQL arrancado?). No se ha borrado nada. Arranca PostgreSQL e inténtalo de nuevo.\n' \
            "${contexto}" >&2
        return 2
    fi
    [[ "${libre}" =~ ^[0-9]+$ ]] || libre=0
    margen=$((necesario / 10 + 65536))
    total=$((necesario + margen))
    if (( libre < total )); then
        printf 'ERROR: No hay espacio suficiente para %s: quedan %s MB y hacen falta %s MB (con margen de seguridad). Libera espacio o mueve la biblioteca a otro disco y vuelve a intentarlo. No se ha borrado nada.\n' \
            "${contexto}" "$((libre / 1024))" "$((total / 1024))" >&2
        return 1
    fi
    return 0
}
