#!/usr/bin/env bash
# =============================================================================
# diagnostico-red.sh — A10: ¿por qué el contenedor no llega a Prowlarr,
# Transmission o aMule, si corren en esta misma máquina?
#
# SOLO LEE. No ejecuta `ufw`, no cambia reglas, rutas ni montajes: imprime lo
# que ha encontrado y los comandos que puedes pegar TÚ. Si no puede determinar
# algo, lo dice — una regla que parece precisa pero apunta a la subred o a la
# interfaz equivocadas es peor que un «no lo sé».
#
# Uso (en la Pi, fuera del contenedor):
#   sudo bash scripts/diagnostico-red.sh
#   sudo bash scripts/diagnostico-red.sh --puerto 9696 --puerto 8080
#
# No se carga `_comun.sh` a propósito: aquél arregla el symlink de `.env` al
# cargarse, y este script promete no tocar nada.
#
# Salida: 0 = nada que hacer · 1 = hay algo que arreglar · 2 = no se pudo
# determinar (y por eso NO se propone ninguna regla).
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ZASCARR_ROOT="${ZASCARR_ROOT:-$(cd "${REPO_DIR}/.." && pwd)}"
ENV_FILE="${ENV_FILE:-${ZASCARR_ROOT}/.env}"
COMPOSE_FILE="${REPO_DIR}/docker-compose.yml"

B='\033[1m'; G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; N='\033[0m'
info() { echo -e "${B}→${N} $*"; }
ok()   { echo -e "${G}✓${N} $*"; }
warn() { echo -e "${Y}⚠${N}  $*"; }
mal()  { echo -e "${R}✗${N} $*"; }

SALIDA=0            # 0 = nada que hacer · 1 = hay algo que arreglar · 2 = indeterminado
PROPUESTAS=0

# ufw traduce sus mensajes y encabezados; el parseo no puede depender del
# idioma de la Pi.
ufw_c() { LC_ALL=C ufw "$@"; }

# ── argumentos ──────────────────────────────────────────────────────────────
PUERTOS_MANUALES=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --puerto)
            [[ -n "${2:-}" && "${2}" =~ ^[0-9]+$ ]] || { mal "--puerto necesita un número."; exit 2; }
            PUERTOS_MANUALES+=("$2"); shift 2 ;;
        -h|--help)
            echo "Uso: sudo bash scripts/diagnostico-red.sh [--puerto N]..."
            echo "Diagnostica por qué el contenedor no llega a los servicios de la Pi."
            echo "Solo lee: no ejecuta ufw ni cambia nada."
            exit 0 ;;
        *) mal "Opción no reconocida: $1"; exit 2 ;;
    esac
done

# ── utilidades ──────────────────────────────────────────────────────────────

# leer_env CLAVE → valor de .env (la última aparición, como docker compose)
leer_env() {
    local clave="$1" valor=""
    [[ -f "${ENV_FILE}" ]] || return 1
    valor="$(grep -E "^${clave}=" "${ENV_FILE}" 2>/dev/null | tail -1 | cut -d= -f2- || true)"
    valor="${valor%\"}"; valor="${valor#\"}"
    valor="${valor%\'}"; valor="${valor#\'}"
    [[ -n "${valor}" ]] || return 1
    printf '%s' "${valor}"
}

# url_partes URL → "host puerto" (puerto vacío si no lo trae)
url_partes() {
    local url="$1" resto host puerto=""
    resto="${url#*://}"
    resto="${resto%%/*}"
    resto="${resto##*@}"                       # quita usuario:contraseña@
    if [[ "${resto}" == \[*\]* ]]; then        # IPv6 entre corchetes
        host="${resto%%\]*}"
        [[ "${resto}" == *"]:"* ]] && puerto="${resto##*\]:}"
    else
        host="${resto%%:*}"
        [[ "${resto}" == *:* ]] && puerto="${resto##*:}"
    fi
    printf '%s %s\n' "${host}" "${puerto}"
}

# ip_a_entero 172.18.0.0 → entero de 32 bits (falla si no es una IPv4 válida)
ip_a_entero() {
    local ip="$1" a b c d octeto
    [[ "${ip}" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]] || return 1
    a="${BASH_REMATCH[1]}"; b="${BASH_REMATCH[2]}"
    c="${BASH_REMATCH[3]}"; d="${BASH_REMATCH[4]}"
    for octeto in "${a}" "${b}" "${c}" "${d}"; do
        (( octeto <= 255 )) || return 1
    done
    echo $(( (a << 24) | (b << 16) | (c << 8) | d ))
}

# cidr_contiene RED/MASCARA SUBNET → 0 si la primera incluye a la segunda.
# Se comparan solo los bits que fija la máscara de la regla: es lo que hace que
# 172.16.0.0/12 (la regla que el proyecto ya recomienda) cuente como cobertura
# de 172.18.0.0/16, en vez de proponer una regla redundante.
cidr_contiene() {
    local regla="$1" subred="$2" r_ip r_pref s_ip s_pref r_int s_int
    r_ip="${regla%%/*}"; r_pref="${regla##*/}"
    s_ip="${subred%%/*}"; s_pref="${subred##*/}"
    [[ "${regla}" == */* ]] || r_pref=32
    [[ "${subred}" == */* ]] || s_pref=32
    [[ "${r_pref}" =~ ^[0-9]+$ && "${s_pref}" =~ ^[0-9]+$ ]] || return 1
    (( r_pref <= 32 && s_pref <= 32 && r_pref <= s_pref )) || return 1
    r_int="$(ip_a_entero "${r_ip}")" || return 1
    s_int="$(ip_a_entero "${s_ip}")" || return 1
    (( (r_int >> (32 - r_pref)) == (s_int >> (32 - r_pref)) ))
}

# rango_cubre EXPR PUERTO → 0 si la expresión de puertos de ufw incluye PUERTO.
# Acepta "any", "9696", "9696/tcp", "80,443", "8080:8090/tcp".
rango_cubre() {
    local expr="$1" puerto="$2" item proto desde hasta
    [[ -z "${expr}" || "${expr}" == "any" || "${expr}" == "Anywhere" ]] && return 0
    local IFS=,
    for item in ${expr}; do
        proto=""
        [[ "${item}" == */* ]] && { proto="${item##*/}"; item="${item%%/*}"; }
        # Ni lo que no sea TCP ni lo que no sea numérico (nombres de servicio o
        # de aplicación) permiten AFIRMAR que cubre este puerto.
        [[ -n "${proto}" && "${proto}" != "tcp" ]] && continue
        [[ "${item}" =~ ^[0-9]+$ || "${item}" =~ ^[0-9]+:[0-9]+$ ]] || continue
        if [[ "${item}" == *:* ]]; then
            desde="${item%%:*}"; hasta="${item##*:}"
            (( puerto >= desde && puerto <= hasta )) && return 0
        else
            (( puerto == item )) && return 0
        fi
    done
    return 1
}

# origen_cubre ORIGEN SUBNET → 0 si el origen de la regla incluye esa subred.
# `Anywhere` es «cualquier origen» según ufw(8) (equivale a 0.0.0.0/0), no una
# cadena literal.
origen_cubre() {
    local origen="$1" subred="$2"
    case "${origen}" in
        ""|any|Anywhere|0.0.0.0/0|::/0) return 0 ;;
    esac
    [[ "${origen}" == "${subred}" ]] && return 0
    cidr_contiene "${origen}" "${subred}"
}

# normalizar_regla "ufw allow from 172.16.0.0/12 to any port 9696 proto tcp"
#   → "allow||172.16.0.0/12|9696"
#   Devuelve 1 si la regla no puede afectar al tráfico ENTRANTE a este host, o
#   si no se entiende. Se lee `ufw show added` (la sintaxis del propio comando)
#   y no la tabla de `ufw status`, donde "on eth0" cae dentro de la columna
#   "To" y no se puede trocear por espacios.
normalizar_regla() {
    local linea="$1" accion="" interfaz="" origen="any" destino="any" i=1 token
    local -a t=()
    read -r -a t <<< "${linea}"
    [[ "${t[0]:-}" == "ufw" ]] || return 1

    while [[ "${i}" -lt "${#t[@]}" ]]; do
        token="${t[$i]}"
        case "${token}" in
            allow|deny|reject|limit) [[ -z "${accion}" ]] && accion="${token}" ;;
            in|rule|--dry-run|log|log-all) : ;;
            out) return 1 ;;                       # saliente: no nos afecta
            route|delete|insert|prepend) return 1 ;; # no evaluable con certeza
            on) interfaz="${t[$((i + 1))]:-}"; i=$((i + 1)) ;;
            proto) i=$((i + 1)) ;;
            from) origen="${t[$((i + 1))]:-any}"; i=$((i + 1)) ;;
            to)
                i=$((i + 1))
                [[ "${t[$i]:-}" != "any" ]] && i=$((i + 1))   # dirección destino
                if [[ "${t[$i]:-}" == "port" ]]; then
                    destino="${t[$((i + 1))]:-any}"; i=$((i + 1))
                fi
                ;;
            port) destino="${t[$((i + 1))]:-any}"; i=$((i + 1)) ;;
            comment) break ;;
            *)
                # Sintaxis simple: "ufw allow 22/tcp".
                if [[ -n "${accion}" && "${destino}" == "any" ]]; then
                    destino="${token}"
                fi
                ;;
        esac
        i=$((i + 1))
    done

    [[ -n "${accion}" ]] || return 1
    printf '%s|%s|%s|%s\n' "${accion}" "${interfaz}" "${origen}" "${destino}"
}

# ── ¿hay algo que comprobar? ────────────────────────────────────────────────
echo ""
echo -e "${B}Diagnóstico de red: del contenedor a los servicios de la Pi${N}"
echo -e "${B}(solo lectura — no ejecuta ningún comando de configuración)${N}"
echo ""

if ! command -v ufw >/dev/null 2>&1; then
    ok "No hay ufw instalado en esta máquina: no hay ninguna regla que proponer."
    echo ""
    exit 0
fi

# No se exige root de entrada: se PIDE la respuesta a ufw y se interpreta. Un
# usuario normal recibe un error por stderr y nada por stdout, que es
# exactamente el caso «necesito root»; así el diagnóstico no depende de cómo se
# llame al script.
ESTADO_UFW="$(ufw_c status 2>/dev/null | head -1 || true)"
if [[ -z "${ESTADO_UFW}" ]]; then
    if [[ "${EUID}" -ne 0 ]]; then
        mal "Necesito permisos de administrador: \`ufw status\` no deja leer las reglas
  a un usuario normal, y sin eso no puedo decirte si falta alguna."
        echo "  Vuelve a ejecutarlo así: sudo bash ${SCRIPT_DIR}/diagnostico-red.sh"
    else
        mal "\`ufw status\` no responde. No voy a adivinar si falta una regla."
    fi
    echo ""
    exit 2
fi
case "${ESTADO_UFW}" in
    "Status: active")
        info "ufw: activo" ;;
    "Status: inactive")
        ok "ufw está instalado pero inactivo: no filtra nada, así que no hay
  ninguna regla que proponer."
        echo ""
        exit 0 ;;
    *)
        mal "No entiendo la respuesta de \`ufw status\`: «${ESTADO_UFW:-sin salida}».
  No voy a adivinar si falta una regla."
        echo ""
        exit 2 ;;
esac

# ── la red REAL del contenedor ──────────────────────────────────────────────
info "Leyendo por dónde sale el contenedor de ZascArr..."

CONTENEDOR=""
if [[ -f "${COMPOSE_FILE}" ]]; then
    CONTENEDOR="$(docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" \
        ps -q zascarr 2>/dev/null | head -1 || true)"
fi
if [[ -z "${CONTENEDOR}" ]]; then
    mal "El contenedor de ZascArr no está arrancado (o no lo encuentro).
  Sin él no sé qué red de Docker usa de verdad, y no pienso adivinarla."
    echo "  Arranca ZascArr y vuelve a intentarlo:"
    echo "    docker compose -f ${COMPOSE_FILE} up -d zascarr"
    echo ""
    exit 2
fi

REDES="$(docker inspect -f '{{range $n, $c := .NetworkSettings.Networks}}{{$n}} {{$c.IPAddress}} {{$c.Gateway}}{{"\n"}}{{end}}' "${CONTENEDOR}" 2>/dev/null || true)"
if [[ -z "${REDES}" ]]; then
    mal "No puedo leer las redes del contenedor. No voy a adivinar la subred."
    echo ""
    exit 2
fi

SUBREDES=(); GATEWAYS=(); INTERFACES=()
while read -r nombre ip gw; do
    [[ -n "${nombre}" ]] || continue
    subred="$(docker network inspect -f '{{range .IPAM.Config}}{{.Subnet}}{{"\n"}}{{end}}' "${nombre}" 2>/dev/null | head -1 || true)"
    interfaz="$(docker network inspect -f '{{index .Options "com.docker.network.bridge.name"}}' "${nombre}" 2>/dev/null || true)"
    if [[ -z "${interfaz}" ]]; then
        # Docker no guarda el nombre en ese caso: lo deriva como "br-" + los 12
        # primeros hex del id de la red (verificado en sandbox). Se marca como
        # derivado para que quede claro que no se ha leído.
        id_red="$(docker network inspect -f '{{.Id}}' "${nombre}" 2>/dev/null || true)"
        [[ -n "${id_red}" ]] && interfaz="br-${id_red:0:12} (derivado)"
    fi
    SUBREDES+=("${subred}"); GATEWAYS+=("${gw}"); INTERFACES+=("${interfaz}")
    echo "  red ${nombre}: ${ip:-sin IP} · subred ${subred:-?} · puerta de enlace ${gw:-?}"
done <<< "${REDES}"

if [[ -z "${SUBREDES[0]:-}" ]]; then
    mal "El contenedor está en una red sin subred declarada (¿network_mode host?).
  No puedo proponer una regla para una subred que no existe."
    echo ""
    exit 2
fi
SUBRED="${SUBREDES[0]}"

# ── el recorrido REAL: ¿a dónde cree el contenedor que está la Pi? ──────────
info "Comprobando el recorrido dentro del contenedor..."
RESUELTO="$(docker exec "${CONTENEDOR}" python3 -c \
    "import socket; print(socket.gethostbyname('host.docker.internal'))" 2>/dev/null || true)"
if [[ -z "${RESUELTO}" ]]; then
    warn "No he podido preguntar dentro del contenedor a dónde resuelve
  host.docker.internal. Sigo, pero el recorrido queda sin comprobar."
else
    recorrido_ok=0
    for gw in "${GATEWAYS[@]}"; do
        [[ "${RESUELTO}" == "${gw}" ]] && recorrido_ok=1
    done
    if [[ "${recorrido_ok}" -eq 1 ]]; then
        ok "host.docker.internal -> ${RESUELTO} (es la puerta de enlace de su red)"
    else
        SALIDA=1
        warn "host.docker.internal -> ${RESUELTO}, que NO es la puerta de enlace de
  ninguna de las redes del contenedor (${GATEWAYS[*]}).

  Es la causa real documentada el 2026-09-25: el contenedor manda el tráfico a
  la red de Docker EQUIVOCADA, y entonces ninguna regla de ufw para la subred
  correcta lo arregla. La versión actual lo autocorrige al arrancar
  (docker-entrypoint.sh reescribe /etc/hosts). Reinícialo:

    docker compose -f ${COMPOSE_FILE} up -d --force-recreate zascarr"
    fi
fi

# ── los puertos que importan ────────────────────────────────────────────────
ETIQUETAS=(); PUERTOS=(); ORIGENES=()

if [[ "${#PUERTOS_MANUALES[@]}" -gt 0 ]]; then
    for p in "${PUERTOS_MANUALES[@]}"; do
        ETIQUETAS+=("(a mano)"); PUERTOS+=("${p}"); ORIGENES+=("host.docker.internal")
    done
else
    # Manda la URL configurada: si apunta a otra máquina, la regla de ufw de
    # ESTA Pi no pinta nada y no se propone.
    for par in "Prowlarr:PROWLARR_URL:9696" "Transmission:TRANSMISSION_URL:9091" "aMule:AMULE_URL:4711"; do
        etiqueta="${par%%:*}"; resto="${par#*:}"; clave="${resto%%:*}"; defecto="${resto##*:}"
        url="$(leer_env "${clave}" || true)"
        if [[ -z "${url}" ]]; then
            url="http://host.docker.internal:${defecto}"
            etiqueta="${etiqueta} (por defecto)"
        fi
        read -r host puerto <<< "$(url_partes "${url}")"
        if [[ -z "${puerto}" ]]; then
            [[ "${url}" == https://* ]] && puerto=443 || puerto=80
        fi
        ETIQUETAS+=("${etiqueta}"); PUERTOS+=("${puerto}"); ORIGENES+=("${host}")
    done
fi

echo ""
info "Puertos que cruzan el puente de Docker:"
for i in "${!PUERTOS[@]}"; do
    case "${ORIGENES[$i]}" in
        host.docker.internal)
            echo "  ${ETIQUETAS[$i]}: ${ORIGENES[$i]}:${PUERTOS[$i]}" ;;
        127.0.0.1|localhost)
            echo "  ${ETIQUETAS[$i]}: ${ORIGENES[$i]}:${PUERTOS[$i]}  ← NO PUEDE FUNCIONAR"
            SALIDA=1 ;;
        *)
            echo "  ${ETIQUETAS[$i]}: ${ORIGENES[$i]}:${PUERTOS[$i]}  (otra máquina: no pasa por aquí)"
            SALIDA=1 ;;
    esac
done
for i in "${!PUERTOS[@]}"; do
    case "${ORIGENES[$i]}" in
        127.0.0.1|localhost)
            warn "${ETIQUETAS[$i]} apunta a ${ORIGENES[$i]}, y dentro del contenedor eso
  es el propio contenedor, no la Pi. Ninguna regla de ufw lo arregla: cámbialo
  por http://host.docker.internal:${PUERTOS[$i]} en /ui/ajustes." ;;
    esac
done

# ── ¿alguna regla cubre ya ese tráfico? ─────────────────────────────────────
REGLAS_ACTIVAS="$(ufw_c status 2>/dev/null | awk \
    '$2 ~ /^(ALLOW|DENY|REJECT|LIMIT)$/ || $3 ~ /^(ALLOW|DENY|REJECT|LIMIT)$/' | wc -l || true)"
REGLAS_TEXTO="$(ufw_c show added 2>/dev/null || true)"
REGLAS_UTILES="$(printf '%s\n' "${REGLAS_TEXTO}" | grep -c '^ufw ' || true)"

if [[ "${REGLAS_ACTIVAS}" -gt 0 && "${REGLAS_UTILES}" -eq 0 ]]; then
    mal "ufw dice tener ${REGLAS_ACTIVAS} reglas activas, pero no puedo leerlas en su
  forma original (\`ufw show added\`). No te propongo una regla a ciegas:
  míralas con \`sudo ufw status numbered\`."
    echo ""
    exit 2
fi

CUBIERTOS=(); BLOQUEADOS=(); ATADAS_A_INTERFAZ=0
for i in "${!PUERTOS[@]}"; do
    [[ "${ORIGENES[$i]}" == "host.docker.internal" ]] || continue
    puerto="${PUERTOS[$i]}"
    cubierto=0; bloqueado=0
    while read -r linea; do
        normalizada="$(normalizar_regla "${linea}")" || continue
        IFS='|' read -r accion interfaz origen destino <<< "${normalizada}"
        if [[ -n "${interfaz}" ]]; then
            # Una regla atada a OTRA interfaz no cubre este tráfico: es
            # exactamente el caso de las reglas "solo LAN" (`on eth0`).
            atada=1
            for j in "${!INTERFACES[@]}"; do
                [[ "${INTERFACES[$j]}" == "${interfaz}"* ]] && atada=0
            done
            [[ "${atada}" -eq 1 ]] && { ATADAS_A_INTERFAZ=$((ATADAS_A_INTERFAZ + 1)); continue; }
        fi
        rango_cubre "${destino}" "${puerto}" || continue
        origen_cubre "${origen}" "${SUBRED}" || continue
        case "${accion}" in
            allow|limit) cubierto=1 ;;
            deny|reject) bloqueado=1 ;;
        esac
    done <<< "${REGLAS_TEXTO}"

    [[ "${cubierto}" -eq 1 ]] && CUBIERTOS+=("${puerto}")
    [[ "${bloqueado}" -eq 1 ]] && BLOQUEADOS+=("${puerto}")
done

# ── informe ─────────────────────────────────────────────────────────────────
echo ""
info "Resultado:"

if [[ "${#CUBIERTOS[@]}" -eq 0 && "${#BLOQUEADOS[@]}" -eq 0 ]]; then
    ok "Ningún puerto tiene ya una regla que cubra ${SUBRED}."
fi

for i in "${!PUERTOS[@]}"; do
    [[ "${ORIGENES[$i]}" == "host.docker.internal" ]] || continue
    puerto="${PUERTOS[$i]}"
    etiqueta="${ETIQUETAS[$i]}"

    ya=0
    for p in "${CUBIERTOS[@]:-}"; do [[ "${p}" == "${puerto}" ]] && ya=1; done
    if [[ "${ya}" -eq 1 ]]; then
        ok "${etiqueta} (${puerto}/tcp): ya hay una regla que cubre ${SUBRED}."
        continue
    fi

    bloquea=0
    for p in "${BLOQUEADOS[@]:-}"; do [[ "${p}" == "${puerto}" ]] && bloquea=1; done

    SALIDA=1
    PROPUESTAS=$((PROPUESTAS + 1))
    warn "${etiqueta} (${puerto}/tcp): no hay ninguna regla que cubra ${SUBRED}."
    echo "      La regla NO lleva 'on <interfaz>' a propósito: omitirlo hace que valga"
    echo "      para todas las interfaces (ufw(8)) y no caduca si Docker recrea el"
    echo "      puente (${INTERFACES[0]:-?}), que cambia de nombre con el id de la red."
    if [[ "${bloquea}" -eq 1 ]]; then
        echo ""
        echo "      OJO: hay una regla que DENIEGA este tráfico. Una regla nueva se añade"
        echo "      al final y no serviría — mírala con \`sudo ufw status numbered\` y pon"
        echo "      la nueva ANTES:"
        echo "        sudo ufw insert <número> allow from ${SUBRED} to any port ${puerto} proto tcp"
    else
        echo "        sudo ufw allow from ${SUBRED} to any port ${puerto} proto tcp"
    fi
done

if [[ "${ATADAS_A_INTERFAZ}" -gt 0 ]]; then
    echo ""
    echo "  (${ATADAS_A_INTERFAZ} regla(s) atadas a otra interfaz no se han contado como"
    echo "   cobertura: aplican a un puente distinto del que usa el contenedor.)"
fi

echo ""
if [[ "${PROPUESTAS}" -gt 0 ]]; then
    warn "No he ejecutado nada. Los comandos de arriba son para que los mires antes
  de pegarlos tú."
elif [[ "${SALIDA}" -ne 0 ]]; then
    warn "Hay algo que arreglar por otro lado (ver arriba). No he tocado nada."
else
    ok "No hay nada que arreglar por este lado."
fi
echo ""
exit "${SALIDA}"
