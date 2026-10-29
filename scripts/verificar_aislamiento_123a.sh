#!/usr/bin/env bash
# =============================================================================
# verificar_aislamiento_123a.sh — compuerta de identidad de la copia (123a-00).
#
# Renderiza la configuración de la copia y la de producción y exige CERO
# colisiones en proyecto, `container_name`, puertos publicados, red y binds.
# Además, todos los binds de la copia deben estar bajo el entorno de la copia.
#
# También permite registrar/comparar los IDs de los contenedores de producción:
#   --ids-antes <fichero>     escribe los IDs actuales (solo lectura)
#   --ids-despues <fichero>   compara y falla si alguno cambió
#
# Uso:
#   bash scripts/verificar_aislamiento_123a.sh \
#     --entorno /srv/123a \
#     --compose /srv/123a/zascarr/docker-compose.yml --env /srv/123a/.env \
#     --prod-compose /opt/zascarr/zascarr/docker-compose.yml --prod-env /opt/zascarr/.env
#
#   bash ... --ids-antes /srv/123a/evidencia/ids-produccion.txt
#   bash ... --ids-despues /srv/123a/evidencia/ids-produccion.txt
#
# No escribe en la base, no arranca contenedores y no toca la biblioteca.
# =============================================================================
set -euo pipefail
umask 022

COMPOSE="${COMPOSE_FILE:-}"
ENV="${ENV_FILE:-}"
PROD_COMPOSE=""
PROD_ENV=""
ENTORNO=""
PROYECTO_ESPERADO="zascarr-123a"
IDS_ANTES=""
IDS_DESPUES=""

die()  { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ok()   { printf '✓ %s\n' "$*"; }
info() { printf '→ %s\n' "$*"; }

uso() {
    sed -n '3,26p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --compose)           [[ -n "${2:-}" ]] || die "--compose necesita un valor"; COMPOSE="$2"; shift 2 ;;
        --env)               [[ -n "${2:-}" ]] || die "--env necesita un valor"; ENV="$2"; shift 2 ;;
        --prod-compose)      [[ -n "${2:-}" ]] || die "--prod-compose necesita un valor"; PROD_COMPOSE="$2"; shift 2 ;;
        --prod-env)          [[ -n "${2:-}" ]] || die "--prod-env necesita un valor"; PROD_ENV="$2"; shift 2 ;;
        --entorno)           [[ -n "${2:-}" ]] || die "--entorno necesita un valor"; ENTORNO="$2"; shift 2 ;;
        --proyecto-esperado) [[ -n "${2:-}" ]] || die "--proyecto-esperado necesita un valor"; PROYECTO_ESPERADO="$2"; shift 2 ;;
        --ids-antes)         [[ -n "${2:-}" ]] || die "--ids-antes necesita un valor"; IDS_ANTES="$2"; shift 2 ;;
        --ids-despues)       [[ -n "${2:-}" ]] || die "--ids-despues necesita un valor"; IDS_DESPUES="$2"; shift 2 ;;
        -h|--help)           uso; exit 0 ;;
        -*)                  die "Opción desconocida: $1" ;;
        *)                   die "Argumento inesperado: $1" ;;
    esac
done

[[ -n "$PROD_COMPOSE" ]] || die "Falta --prod-compose."
[[ -n "$PROD_ENV" ]] || die "Falta --prod-env."
[[ -f "$PROD_COMPOSE" ]] || die "No existe --prod-compose."
[[ -f "$PROD_ENV" ]] || die "No existe --prod-env."
command -v docker >/dev/null 2>&1 || die "No encuentro docker."
command -v jq >/dev/null 2>&1 || die "No encuentro jq."
command -v realpath >/dev/null 2>&1 || die "No encuentro realpath."

ids_actuales() {
    docker compose -f "$PROD_COMPOSE" --env-file "$PROD_ENV" ps -q 2>/dev/null \
        | sed '/^[[:space:]]*$/d' | sort
}

if [[ -n "$IDS_ANTES" && -n "$IDS_DESPUES" ]]; then
    die "Usa --ids-antes o --ids-despues, no los dos a la vez."
fi

if [[ -n "$IDS_ANTES" ]]; then
    ids_actuales > "$IDS_ANTES" || die "No pude leer los IDs de producción."
    chmod 600 "$IDS_ANTES" 2>/dev/null || true
    n="$(wc -l < "$IDS_ANTES" | tr -d '[:space:]')"
    ok "IDs de producción registrados: ${n}."
    exit 0
fi

if [[ -n "$IDS_DESPUES" ]]; then
    [[ -f "$IDS_DESPUES" ]] || die "No existe el fichero de IDs previos."
    antes="$(sed '/^[[:space:]]*$/d' "$IDS_DESPUES" | sort)"
    ahora="$(ids_actuales)" || die "No pude leer los IDs actuales de producción."
    if [[ "$antes" != "$ahora" ]]; then
        printf 'ERROR: los IDs de los contenedores de producción cambiaron.\n' >&2
        printf '  Antes:\n%s\n' "$antes" >&2
        printf '  Ahora:\n%s\n' "$ahora" >&2
        exit 1
    fi
    ok "IDs de producción sin cambios."
    exit 0
fi

[[ -n "$ENTORNO" ]] || die "Falta --entorno (raíz de la copia)."
[[ -n "$COMPOSE" ]] || die "Falta --compose (o COMPOSE_FILE)."
[[ -n "$ENV" ]] || die "Falta --env (o ENV_FILE)."
[[ -f "$COMPOSE" ]] || die "No existe --compose."
[[ -f "$ENV" ]] || die "No existe --env."

ENTORNO_REAL="$(realpath -m "$ENTORNO")"
COPY_JSON="$(docker compose -f "$COMPOSE" --env-file "$ENV" config --format json 2>/dev/null)" || \
    die "No pude renderizar la configuración de la copia."
PROD_JSON="$(docker compose -f "$PROD_COMPOSE" --env-file "$PROD_ENV" config --format json 2>/dev/null)" || \
    die "No pude renderizar la configuración de producción."
printf '%s' "$COPY_JSON" | jq -e . >/dev/null 2>&1 || die "La configuración de la copia no es JSON válido."
printf '%s' "$PROD_JSON" | jq -e . >/dev/null 2>&1 || die "La configuración de producción no es JSON válido."

C_PROYECTO="$(printf '%s' "$COPY_JSON" | jq -r '.name // empty')"
P_PROYECTO="$(printf '%s' "$PROD_JSON" | jq -r '.name // empty')"
[[ -n "$C_PROYECTO" ]] || die "La copia no declara proyecto Compose."
[[ -n "$P_PROYECTO" ]] || die "Producción no declara proyecto Compose."

fallos=0
if [[ "$C_PROYECTO" == "zascarr" ]]; then
    printf 'ERROR: proyecto: la copia usa "zascarr" (producción).\n' >&2
    fallos=1
fi
if [[ "$C_PROYECTO" != "$PROYECTO_ESPERADO" ]]; then
    printf 'ERROR: proyecto: la copia usa "%s"; se esperaba "%s".\n' \
        "$C_PROYECTO" "$PROYECTO_ESPERADO" >&2
    fallos=1
fi
if [[ "$C_PROYECTO" == "$P_PROYECTO" ]]; then
    printf 'ERROR: proyecto: "%s" coincide con producción.\n' "$C_PROYECTO" >&2
    fallos=1
fi

lista_copiar() {
    printf '%s' "$1" | jq -r "$2" 2>/dev/null | sed '/^[[:space:]]*$/d' | sort -u
}

interseccion() {
    comm -12 <(printf '%s\n' "$1" | sort -u) <(printf '%s\n' "$2" | sort -u) \
        | sed '/^[[:space:]]*$/d'
}

C_CONT="$(lista_copiar "$COPY_JSON" '.services[]?.container_name // empty')"
P_CONT="$(lista_copiar "$PROD_JSON" '.services[]?.container_name // empty')"
CHOQUE_CONT="$(interseccion "$C_CONT" "$P_CONT")"
if [[ -n "$CHOQUE_CONT" ]]; then
    printf 'ERROR: contenedor(es) en colisión: %s\n' \
        "$(printf '%s' "$CHOQUE_CONT" | paste -sd, -)" >&2
    fallos=1
fi

C_PUERTOS="$(lista_copiar "$COPY_JSON" '.services[]?.ports[]? | select(.published != null) | "\(.published)/\(.protocol // "tcp")"')"
P_PUERTOS="$(lista_copiar "$PROD_JSON" '.services[]?.ports[]? | select(.published != null) | "\(.published)/\(.protocol // "tcp")"')"
CHOQUE_PUERTOS="$(interseccion "$C_PUERTOS" "$P_PUERTOS")"
if [[ -n "$CHOQUE_PUERTOS" ]]; then
    printf 'ERROR: puerto(s) publicado(s) en colisión: %s\n' \
        "$(printf '%s' "$CHOQUE_PUERTOS" | paste -sd, -)" >&2
    fallos=1
fi

C_REDES="$(lista_copiar "$COPY_JSON" '(.networks // {}) | to_entries[] | (.value.name // .key)')"
P_REDES="$(lista_copiar "$PROD_JSON" '(.networks // {}) | to_entries[] | (.value.name // .key)')"
CHOQUE_REDES="$(interseccion "$C_REDES" "$P_REDES")"
if [[ -n "$CHOQUE_REDES" ]]; then
    printf 'ERROR: red(es) en colisión: %s\n' \
        "$(printf '%s' "$CHOQUE_REDES" | paste -sd, -)" >&2
    fallos=1
fi

C_BINDS="$(lista_copiar "$COPY_JSON" '.services[]?.volumes[]? | select(.type == "bind") | .source // empty')"
P_BINDS="$(lista_copiar "$PROD_JSON" '.services[]?.volumes[]? | select(.type == "bind") | .source // empty')"
n_bind=0
while IFS= read -r origen; do
    [[ -n "$origen" ]] || continue
    n_bind=$((n_bind + 1))
    real="$(realpath -m "$origen")"
    if [[ -n "$P_BINDS" ]] && printf '%s\n' "$P_BINDS" | grep -Fxq "$real"; then
        printf 'ERROR: bind #%d coincide con un bind de producción.\n' "$n_bind" >&2
        fallos=1
        continue
    fi
    if [[ "$real" != "$ENTORNO_REAL" && "$real" != "$ENTORNO_REAL/"* ]]; then
        printf 'ERROR: bind #%d está fuera del entorno de la copia.\n' "$n_bind" >&2
        fallos=1
    fi
done <<< "$C_BINDS"

if (( fallos != 0 )); then
    printf '\nDETENER: la copia no está aislada de producción.\n' >&2
    exit 1
fi

printf 'Proyecto:     %s (esperado %s; producción %s)\n' \
    "$C_PROYECTO" "$PROYECTO_ESPERADO" "$P_PROYECTO"
printf 'Contenedores: %s\n' "$(printf '%s' "$C_CONT" | paste -sd, -)"
printf 'Puertos:      %s\n' "$(printf '%s' "$C_PUERTOS" | paste -sd, -)"
printf 'Redes:        %s\n' "$(printf '%s' "$C_REDES" | paste -sd, -)"
printf 'Binds:        %d, todos bajo el entorno de la copia\n' "$n_bind"
ok "0 colisiones de proyecto, contenedores, puertos, red o binds."
