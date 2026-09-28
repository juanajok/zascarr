#!/usr/bin/env bash
# =============================================================================
# diagnostico-red.sh — A10: ¿por qué el contenedor no llega a Prowlarr,
# Transmission o aMule, si corren en esta misma máquina?
#
# SOLO LEE. No ejecuta `ufw`, no cambia reglas, rutas ni montajes: imprime lo
# que ha encontrado y los comandos que puedes pegar TÚ.
#
# Regla de oro (es el criterio de A10): **mejor «no puedo determinarlo» que un
# comando preciso pero equivocado.** De ahí que:
#   - si no se puede comprobar el recorrido real, o está roto, NO se propone
#     ninguna regla: primero se arregla (o se comprueba) el recorrido;
#   - si alguna regla que no se entiende podría afectar, NO se propone nada;
#   - si alguna regla DENIEGA este tráfico, no se propone un `allow` al final
#     (podría quedar por detrás) ni se asegura que ya está cubierto.
#
# Uso (en la Pi, fuera del contenedor):
#   sudo bash scripts/diagnostico-red.sh
#   sudo bash scripts/diagnostico-red.sh --puerto 9696 --puerto 8080
#
# No se carga `_comun.sh` a propósito: aquél arregla el symlink de `.env` al
# cargarse, y este script promete no tocar nada.
#
# Salida: 0 = nada que hacer · 1 = hay algo que arreglar · 2 = no se pudo
# determinar (y por eso NO se propone ninguna regla en ese punto).
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
NO_ENTENDIDAS=0
ATADAS_A_INTERFAZ=0

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

# _direccion_valida X → 0 si X es una dirección que sabemos interpretar
_direccion_valida() {
    case "$1" in
        any|Anywhere) return 0 ;;
    esac
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+(/[0-9]+)?$ ]]
}

# _puertos_validos EXPR → 0 si EXPR son puertos/rangos numéricos (o "any")
_puertos_validos() {
    local expr="$1" item base
    [[ "${expr}" == "any" ]] && return 0
    local IFS=,
    for item in ${expr}; do
        base="${item%%/*}"
        [[ "${base}" =~ ^[0-9]+$ || "${base}" =~ ^[0-9]+:[0-9]+$ ]] || return 1
    done
    return 0
}

# normalizar_regla "ufw allow from 172.16.0.0/12 to any port 9696 proto tcp"
#   → "allow||tcp|172.16.0.0/12|any|9696"
#     acción | interfaz | proto | origen | dirección destino | puertos destino
#   Lo que no se pueda interpretar con certeza sale como "?", y la función
#   devuelve 1 si la regla no puede afectar al tráfico ENTRANTE a este host
#   (saliente, `route`, o línea que no se entiende).
#
#   Se lee `ufw show added` porque da la sintaxis del propio comando. El ORDEN
#   no se usa nunca para decidir: ufw(8) avisa de que ese informe no conserva el
#   orden original de los comandos ni refleja el estado del cortafuegos activo,
#   así que la decisión es conservadora e independiente del orden (ver
#   `efecto_de_regla`).
normalizar_regla() {
    local linea="$1" accion="" interfaz="" proto="" origen="any"
    local dir_destino="any" puerto_destino="any" i=1 token
    local -a t=()
    read -r -a t <<< "${linea}"
    [[ "${t[0]:-}" == "ufw" ]] || return 1

    while [[ "${i}" -lt "${#t[@]}" ]]; do
        token="${t[$i]}"
        case "${token}" in
            allow|deny|reject|limit) [[ -z "${accion}" ]] && accion="${token}" ;;
            in|rule|--dry-run|log|log-all) : ;;
            out) return 1 ;;                          # saliente: no nos afecta
            route|delete|insert|prepend) return 1 ;;  # no evaluable con certeza
            on) interfaz="${t[$((i + 1))]:-?}"; i=$((i + 1)) ;;
            proto) proto="${t[$((i + 1))]:-?}"; i=$((i + 1)) ;;
            from) origen="${t[$((i + 1))]:-?}"; i=$((i + 1)) ;;
            to)
                i=$((i + 1))
                if [[ "${t[$i]:-}" == "any" ]]; then
                    i=$((i + 1))
                elif [[ -n "${t[$i]:-}" && "${t[$i]}" != "port" ]]; then
                    dir_destino="${t[$i]}"; i=$((i + 1))   # `to DIRECCIÓN`
                fi
                if [[ "${t[$i]:-}" == "port" ]]; then
                    puerto_destino="${t[$((i + 1))]:-?}"; i=$((i + 1))
                fi
                ;;
            port) puerto_destino="${t[$((i + 1))]:-?}"; i=$((i + 1)) ;;
            comment) break ;;
            *)
                # Sintaxis simple: "ufw allow 22/tcp".
                if [[ -n "${accion}" && "${puerto_destino}" == "any" ]]; then
                    puerto_destino="${token}"
                fi
                ;;
        esac
        i=$((i + 1))
    done

    [[ -n "${accion}" ]] || return 1

    # Lo que no se pueda interpretar se marca "?" en vez de darlo por bueno: un
    # `proto udp` no autoriza tráfico TCP, y `to 192.168.1.5 port 9696` no
    # autoriza el tráfico dirigido a la puerta de enlace de Docker.
    _direccion_valida "${origen}" || origen="?"
    _direccion_valida "${dir_destino}" || dir_destino="?"
    _puertos_validos "${puerto_destino}" || puerto_destino="?"
    case "${proto}" in
        ""|tcp|udp) : ;;
        *) proto="?" ;;
    esac
    [[ -n "${interfaz}" ]] && interfaz="${interfaz%% *}"

    printf '%s|%s|%s|%s|%s|%s\n' \
        "${accion}" "${interfaz}" "${proto}" "${origen}" "${dir_destino}" "${puerto_destino}"
}

# efecto_de_regla REGISTRO PUERTO SUBRED GATEWAY PUENTE
#   Imprime cómo afecta esa regla a NUESTRO tráfico (TCP, hacia ese puerto,
#   desde la subred de Docker, hacia la puerta de enlace del contenedor):
#     no_aplica   → se puede DESCARTAR sin duda (no lo toca)
#     match_allow → la regla PERMITE exactamente este tráfico
#     match_deny  → la regla DENIEGA exactamente este tráfico
#     duda_allow  → podría permitirlo, pero no se puede afirmar
#     duda_deny   → podría denegarlo, pero no se puede afirmar
#   Un `duda_allow` nunca acredita cobertura; un `duda_deny` impide proponer.
efecto_de_regla() {
    local registro="$1" puerto="$2" subred="$3" gateway="$4" puente="$5"
    local accion interfaz proto origen dir_destino puerto_destino
    local descartada=0 duda=0

    IFS='|' read -r accion interfaz proto origen dir_destino puerto_destino <<< "${registro}"

    # Primero lo que DESCARTA la regla sin ninguna duda; la duda solo cuenta si
    # la regla no se ha podido descartar.
    case "${puerto_destino}" in
        ""|any) : ;;
        "?") duda=1 ;;
        *) rango_cubre "${puerto_destino}" "${puerto}" || descartada=1 ;;
    esac
    case "${proto}" in
        ""|tcp) : ;;
        "?") duda=1 ;;
        *) descartada=1 ;;        # udp, icmp, gre… no llevan este tráfico
    esac
    case "${dir_destino}" in
        ""|any) : ;;
        "?") duda=1 ;;
        *) [[ "${dir_destino}" == "${gateway}" ]] || descartada=1 ;;
    esac
    if [[ -n "${interfaz}" ]]; then
        if [[ "${interfaz}" == "?" || -z "${puente}" ]]; then
            duda=1
        else
            # Una regla atada a OTRA interfaz no cubre este tráfico: es el caso
            # de las reglas "solo LAN" (`on eth0`). Se distingue del resto de
            # descartes porque es el que más despista al coleccionista.
            [[ "${interfaz}" == "${puente}" ]] || { echo "no_aplica_interfaz"; return 0; }
        fi
    fi
    case "${origen}" in
        ""|any) : ;;
        "?") duda=1 ;;
        *) origen_cubre "${origen}" "${subred}" || descartada=1 ;;
    esac

    if [[ "${descartada}" -eq 1 ]]; then echo "no_aplica"; return 0; fi
    if [[ "${duda}" -eq 1 ]]; then
        case "${accion}" in deny|reject) echo "duda_deny" ;; *) echo "duda_allow" ;; esac
        return 0
    fi
    case "${accion}" in deny|reject) echo "match_deny" ;; *) echo "match_allow" ;; esac
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
# exactamente el caso «necesito root».
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
    "Status: active")   info "ufw: activo" ;;
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
        # primeros hex del id de la red (verificado en sandbox).
        id_red="$(docker network inspect -f '{{.Id}}' "${nombre}" 2>/dev/null || true)"
        [[ -n "${id_red}" ]] && interfaz="br-${id_red:0:12}"
    fi
    SUBREDES+=("${subred}"); GATEWAYS+=("${gw}"); INTERFACES+=("${interfaz}")
    echo "  red ${nombre}: ${ip:-sin IP} · subred ${subred:-?} · puerta de enlace ${gw:-?}"
done <<< "${REDES}"

# ── el recorrido REAL: ¿a dónde cree el contenedor que está la Pi? ──────────
#
# Sin esto no se propone NADA. Dos motivos, los dos del caso real del
# 2026-09-25: si no se puede comprobar no hay datos para sostener una regla, y
# si el contenedor sale por otra red, la regla para la subred «correcta» no
# arregla el fallo — imprimirla sería un comando preciso pero inútil.
info "Comprobando el recorrido dentro del contenedor..."
RESUELTO="$(docker exec "${CONTENEDOR}" python3 -c \
    "import socket; print(socket.gethostbyname('host.docker.internal'))" 2>/dev/null || true)"

if [[ -z "${RESUELTO}" ]]; then
    mal "No he podido preguntar DENTRO del contenedor a dónde resuelve
  host.docker.internal, así que no sé por qué red sale el tráfico.

  No te propongo ninguna regla: sin ese dato podría estar apuntando a una red
  que el contenedor ni usa. Compruébalo tú con:

    docker exec ${CONTENEDOR} python3 -c \"import socket; print(socket.gethostbyname('host.docker.internal'))\"
    docker inspect ${CONTENEDOR} --format '{{range .NetworkSettings.Networks}}{{.Gateway}} {{end}}'"
    echo ""
    exit 2
fi

SUBRED=""; GATEWAY=""; PUENTE=""; COINCIDENCIAS=0
for j in "${!GATEWAYS[@]}"; do
    if [[ "${GATEWAYS[$j]}" == "${RESUELTO}" ]]; then
        COINCIDENCIAS=$((COINCIDENCIAS + 1))
        SUBRED="${SUBREDES[$j]}"; GATEWAY="${GATEWAYS[$j]}"; PUENTE="${INTERFACES[$j]}"
    fi
done

if [[ "${COINCIDENCIAS}" -eq 0 ]]; then
    mal "El contenedor cree que la Pi está en ${RESUELTO}, y ésa NO es la puerta de
  enlace de ninguna de sus redes (${GATEWAYS[*]}).

  Es la causa real documentada el 2026-09-25: el contenedor manda el tráfico a
  la red de Docker EQUIVOCADA. Ninguna regla de ufw para la subred correcta lo
  arregla, así que no te propongo ninguna. La versión actual lo autocorrige al
  arrancar (docker-entrypoint.sh reescribe /etc/hosts); reinícialo con:

    docker compose -f ${COMPOSE_FILE} up -d --force-recreate zascarr

  Y si sigue igual, compruébalo con:
    docker exec ${CONTENEDOR} python3 -c \"import socket; print(socket.gethostbyname('host.docker.internal'))\""
    echo ""
    exit 1
fi

if [[ "${COINCIDENCIAS}" -gt 1 ]]; then
    mal "${COINCIDENCIAS} redes del contenedor comparten la puerta de enlace ${RESUELTO},
  así que no sé a cuál de sus subredes pertenece el tráfico. No propongo regla."
    echo ""
    exit 2
fi

if [[ -z "${SUBRED}" ]]; then
    mal "La red por la que sale el contenedor (${GATEWAY}) no declara subred.
  No puedo proponer una regla para una subred que no existe."
    echo ""
    exit 2
fi

ok "host.docker.internal -> ${RESUELTO} (la puerta de enlace de ${SUBRED})"

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

# ── las reglas ──────────────────────────────────────────────────────────────
# `ufw show added` da la sintaxis del comando (mucho más fiable de trocear que
# la tabla de `status numbered`), pero NO conserva el orden original de los
# comandos ni refleja el estado del cortafuegos activo. Por eso:
#   - la decisión NO depende del orden (ver `efecto_de_regla`);
#   - si el número de reglas no coincide con el de `ufw status`, no se usa.
REGLAS_ACTIVAS="$(ufw_c status 2>/dev/null | awk \
    '$2 ~ /^(ALLOW|DENY|REJECT|LIMIT)$/ || $3 ~ /^(ALLOW|DENY|REJECT|LIMIT)$/' | wc -l || true)"
REGLAS_TEXTO="$(ufw_c show added 2>/dev/null || true)"
REGLAS_UTILES="$(printf '%s\n' "${REGLAS_TEXTO}" | grep -c '^ufw ' || true)"

if [[ "${REGLAS_ACTIVAS}" -ne "${REGLAS_UTILES}" ]]; then
    mal "ufw dice tener ${REGLAS_ACTIVAS} reglas activas y \`ufw show added\` me da
  ${REGLAS_UTILES}. Las dos fuentes no coinciden (¿reglas editadas a mano?), así que
  no puedo decirte qué reglas están en vigor. Míralas tú con:

    sudo ufw status numbered"
    echo ""
    exit 2
fi

# Se clasifican TODAS las reglas y luego se decide. La decisión es conservadora
# y NO depende del orden, porque el orden efectivo no se puede leer con certeza
# desde `show added`:
#   - si ALGUNA regla deniega este tráfico, no se propone un `allow` al final
#     (podría quedar por detrás de la que deniega) ni se dice que ya está
#     cubierto (podría ganar la que deniega);
#   - si ALGUNA regla que no se entiende podría denegarlo, no se propone nada;
#   - solo si NINGUNA regla lo toca se propone añadir una, que es la única
#     conclusión que no depende del orden: una regla al final solo se alcanza si
#     ninguna otra casa.
CUBIERTOS=(); BLOQUEADOS=(); DUDOSOS=()
for i in "${!PUERTOS[@]}"; do
    [[ "${ORIGENES[$i]}" == "host.docker.internal" ]] || continue
    puerto="${PUERTOS[$i]}"
    cubierto=0; bloqueado=0; dudoso=0
    while read -r linea; do
        normalizada="$(normalizar_regla "${linea}")" || continue
        case "$(efecto_de_regla "${normalizada}" "${puerto}" "${SUBRED}" "${GATEWAY}" "${PUENTE}")" in
            match_allow)       cubierto=1 ;;
            match_deny)        bloqueado=1 ;;
            duda_deny)         dudoso=1 ;;
            duda_allow)        NO_ENTENDIDAS=$((NO_ENTENDIDAS + 1)) ;;
            no_aplica_interfaz) ATADAS_A_INTERFAZ=$((ATADAS_A_INTERFAZ + 1)) ;;
        esac
    done <<< "${REGLAS_TEXTO}"

    if [[ "${bloqueado}" -eq 1 ]]; then
        BLOQUEADOS+=("${puerto}")
    elif [[ "${dudoso}" -eq 1 ]]; then
        DUDOSOS+=("${puerto}")
    elif [[ "${cubierto}" -eq 1 ]]; then
        CUBIERTOS+=("${puerto}")
    else
        PARCIALES+=("${puerto}")
    fi
done

# ── informe ─────────────────────────────────────────────────────────────────
contiene() {
    local buscado="$1"; shift
    local p
    for p in "$@"; do [[ "${p}" == "${buscado}" ]] && return 0; done
    return 1
}

echo ""
info "Resultado:"

if [[ "${#CUBIERTOS[@]}" -eq 0 && "${#BLOQUEADOS[@]}" -eq 0 && "${#DUDOSOS[@]}" -eq 0 ]]; then
    ok "Ninguna regla de ufw toca el tráfico que cruza el puente."
fi

for i in "${!PUERTOS[@]}"; do
    [[ "${ORIGENES[$i]}" == "host.docker.internal" ]] || continue
    puerto="${PUERTOS[$i]}"
    etiqueta="${ETIQUETAS[$i]}"

    if contiene "${puerto}" "${BLOQUEADOS[@]:-}"; then
        SALIDA=1
        warn "${etiqueta} (${puerto}/tcp): hay una regla de ufw que DENIEGA este tráfico."
        echo "      Una regla nueva se añade al final y podría quedar por detrás de la"
        echo "      que deniega, así que NO te propongo ningún comando. Mira el orden"
        echo "      efectivo y decide tú:"
        echo "        sudo ufw status numbered"
        continue
    fi
    if contiene "${puerto}" "${DUDOSOS[@]:-}"; then
        [[ "${SALIDA}" -eq 0 ]] && SALIDA=2
        warn "${etiqueta} (${puerto}/tcp): hay reglas de ufw que no puedo interpretar
  con certeza (protocolo o destino) y que podrían denegar este tráfico."
        echo "      No te propongo nada: míralas tú con \`sudo ufw status numbered\`."
        continue
    fi
    if contiene "${puerto}" "${CUBIERTOS[@]:-}"; then
        ok "${etiqueta} (${puerto}/tcp): ya hay una regla que cubre ${SUBRED}."
        continue
    fi

    SALIDA=1
    PROPUESTAS=$((PROPUESTAS + 1))
    warn "${etiqueta} (${puerto}/tcp): ninguna regla toca este tráfico."
    echo "      La regla NO lleva 'on <interfaz>' a propósito: omitirlo hace que valga"
    echo "      para todas las interfaces (ufw(8)) y no caduca si Docker recrea el"
    echo "      puente (${PUENTE:-?}), que cambia de nombre con el id de la red."
    echo "        sudo ufw allow from ${SUBRED} to any port ${puerto} proto tcp"
done

if [[ "${ATADAS_A_INTERFAZ}" -gt 0 ]]; then
    echo ""
    echo "  (${ATADAS_A_INTERFAZ} regla(s) atadas a otra interfaz no se han contado como"
    echo "   cobertura: aplican a un puente distinto del que usa el contenedor.)"
fi

if [[ "${NO_ENTENDIDAS}" -gt 0 ]]; then
    echo ""
    echo "  (${NO_ENTENDIDAS} regla(s) que no he podido interpretar NO se han contado"
    echo "   como cobertura. Están en \`sudo ufw status numbered\`.)"
fi

echo ""
if [[ "${PROPUESTAS}" -gt 0 ]]; then
    warn "No he ejecutado nada. Los comandos de arriba son para que los mires antes
  de pegarlos tú."
elif [[ "${SALIDA}" -eq 2 ]]; then
    warn "No he tocado nada, y no te he propuesto ningún comando: falta algún dato
  para poder sostenerlo (ver arriba)."
elif [[ "${SALIDA}" -ne 0 ]]; then
    warn "Hay algo que arreglar por otro lado (ver arriba). No he tocado nada."
else
    ok "No hay nada que arreglar por este lado."
fi
echo ""
exit "${SALIDA}"
