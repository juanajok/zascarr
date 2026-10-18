#!/usr/bin/env bash
# =============================================================================
# lib-ensayo.sh — M4 · Fase 1 bis (#121). Salvaguardas del ARNÉS, comunes al anfitrión y a la VM. NO se ejecuta: se carga con
# `source`. Sin efectos al cargarse. Todas las funciones se prueban con dobles y procesos controlados, sin arrancar QEMU
# (tests/test_ensayo_f1bis_arnes.py).
#
# Qué garantiza y con qué límites (lo que el guion presenta como garantizado):
#
#   · Presupuesto de descarga, en DOS capas:
#       1. TOPE EN EL NÚCLEO (`instalar_tope_de_red`, regla de nftables en la VM): cuenta los bytes recibidos por la interfaz
#          (salvo el SSH de control) y DESCARTA todo lo que llegue por encima del tope. No depende de que ningún proceso
#          coopere ni de cuándo se tome una muestra: el exceso posible es UN paquete (≈ 1,5 KB) más la diferencia entre lo que
#          cuenta nftables (capa 3) y `rx_bytes` (capa 2, +14 B por paquete ≈ 1 %); por eso la cuota se fija al 98 % del tope.
#          Se comprobó de forma funcional en un espacio de nombres de red real (tests/test_ensayo_f1bis_arnes.py).
#       2. VIGILANTE (`con_limite_de_descarga`): mide cada INTERVALO_S segundos y, al llegar al UMBRAL DE CORTE (tope − margen),
#          CORTA LA RED (`cortar_red`: descarta todo salvo el SSH, al instante) y termina el grupo de procesos entero
#          (TERM, KILL) COMPROBANDO que no queda NINGÚN miembro del grupo vivo —no solo el líder—; si queda alguno, devuelve 5.
#          Cortar la red primero es lo que garantiza el tope aunque el comando sea un CLIENTE de otro proceso: `docker build`
#          lo es (BuildKit ejecuta la construcción en el servicio), y matar el cliente no prueba que el constructor haya dejado
#          de descargar. Aquí no se supone que lo haga: deja de poder recibir. El constructor puede seguir trabajando sin red
#          hasta que sus pasos fallen por tiempo de espera; eso no gasta descarga.
#     Unidad: MiB (1 MiB = 1.048.576 bytes) en todo.
#   · Almacenamiento y espacio libre del anfitrión: `vigilante_anfitrion` los mide cada pocos segundos mientras la VM trabaja y
#     PARA la VM propia al cruzar un límite (el crecimiento posible entre muestras es el de un disco: se declara en el guion).
#   · Ciclo de vida: la VM propia se identifica por PID Y atributos (`-name` y un disco bajo $DIR); un PID que no los cumple
#     NO se señala jamás. `parar_vm_propia` pide apagado limpio, luego TERM, luego KILL, con esperas acotadas, y NO borra el PID
#     ni dice «apagada» hasta comprobar que el proceso ha terminado (un zombi cuenta como terminado).
#   · `procesos_qemu` recorre /proc: `pgrep -x qemu-system-x86_64` no sirve (el nombre de proceso se trunca a 15 caracteres y
#     la comparación exacta no casa nunca con un nombre de 18).
# =============================================================================

NOMBRE_VM="${NOMBRE_VM:-m4-f1bis}"

# procesos_qemu → un PID por línea, de los procesos cuyo ejecutable (argv[0]) es qemu-system-*
procesos_qemu() {
    local p c
    for p in /proc/[0-9]*; do
        [[ -r "${p}/cmdline" ]] || continue
        c="$(tr '\0' ' ' < "${p}/cmdline" 2>/dev/null)" || continue
        case "${c%% *}" in
            */qemu-system-*|qemu-system-*) echo "${p#/proc/}" ;;
        esac
    done
}

# proceso_vivo PID: existe y no es un zombi.
proceso_vivo() {
    local estado
    [[ "${1:-}" =~ ^[0-9]+$ && -r "/proc/$1/status" ]] || return 1
    estado="$(awk '/^State:/{print $2}' "/proc/$1/status" 2>/dev/null)"
    [[ -n "${estado}" && "${estado}" != "Z" && "${estado}" != "X" ]]
}

# esperar_muerte PID SEGUNDOS
esperar_muerte() {
    local pid="$1" limite="$2" t=0
    while proceso_vivo "${pid}"; do
        (( t >= limite )) && return 1
        sleep 1; t=$((t + 1))
    done
    return 0
}

# vm_es_propia PID DIR: es un qemu con `-name $NOMBRE_VM` y un disco (`file=DIR/…`) bajo DIR.
vm_es_propia() {
    local pid="$1" dir="$2" args
    proceso_vivo "${pid}" || return 1
    args="$(tr '\0' '\n' < "/proc/${pid}/cmdline" 2>/dev/null)" || return 1
    [[ "$(head -n 1 <<<"${args}")" == */qemu-system-* || "$(head -n 1 <<<"${args}")" == qemu-system-* ]] || return 1
    grep -qx -- "${NOMBRE_VM}" <<<"${args}" || return 1
    grep -q -- "^file=${dir}/" <<<"${args}"
}

# solicitar_apagado: gancho que el anfitrión redefine (apagado limpio por SSH, acotado). Por defecto no hace nada.
solicitar_apagado() { :; }

# parar_vm_propia DIR PIDFILE
#   0: la VM propia ya no existe (comprobado) o no había · 1: sigue viva tras TERM y KILL · 3: el PID del fichero es de OTRO proceso
parar_vm_propia() {
    local dir="$1" pidfile="$2" pid
    [[ -f "${pidfile}" ]] || return 0
    pid="$(tr -dc '0-9' < "${pidfile}")"
    if [[ -z "${pid}" ]] || ! proceso_vivo "${pid}"; then rm -f "${pidfile}"; return 0; fi
    if ! vm_es_propia "${pid}" "${dir}"; then
        echo "AVISO: el PID ${pid} de ${pidfile} no es la VM de este ensayo: NO se toca." >&2
        return 3
    fi
    solicitar_apagado || true
    if ! esperar_muerte "${pid}" "${ESPERA_APAGADO_S:-60}"; then
        kill -TERM "${pid}" 2>/dev/null || true
        if ! esperar_muerte "${pid}" "${ESPERA_TERM_S:-20}"; then
            kill -KILL "${pid}" 2>/dev/null || true
            esperar_muerte "${pid}" "${ESPERA_KILL_S:-10}" || true
        fi
    fi
    if proceso_vivo "${pid}"; then return 1; fi
    rm -f "${pidfile}"
    return 0
}

# ahora: segundos desde la época (gancho: las pruebas lo sustituyen por un reloj manejable).
ahora() { date +%s; }

# miembros_vivos_del_grupo PGID → PIDs de los procesos del grupo que NO son zombis (todos, no solo el líder).
miembros_vivos_del_grupo() {
    local pgid="$1" f resto estado ppid pgrp _r
    for f in /proc/[0-9]*/stat; do
        [[ -r "${f}" ]] || continue
        resto="$(sed 's/^.*) //' "${f}" 2>/dev/null)" || continue          # tras el nombre: estado ppid pgrp …
        read -r estado ppid pgrp _r <<<"${resto}"
        [[ "${pgrp:-}" == "${pgid}" && "${estado:-Z}" != "Z" ]] && { f="${f#/proc/}"; echo "${f%%/*}"; }
    done
    return 0
}

# esperar_grupo_vacio PGID SEGUNDOS
esperar_grupo_vacio() {
    local pgid="$1" limite="$2" t=0
    while [[ -n "$(miembros_vivos_del_grupo "${pgid}")" ]]; do
        (( t >= limite )) && return 1
        sleep 1; t=$((t + 1))
    done
    return 0
}

# cortar_red: gancho. vm-preparar.sh lo redefine con nftables; por defecto no hace nada.
cortar_red() { :; }

# instalar_tope_de_red TOPE_MIB INTERFAZ: tope en el núcleo (ver la cabecera). Todo lo que entre por INTERFAZ salvo el SSH de
# control (tcp/22) cuenta; por encima del 98 % del tope se descarta. Verifica que la regla quedó cargada.
instalar_tope_de_red() {
    local tope="$1" iface="$2" cuota
    cuota=$(( tope * 98 / 100 ))
    nft -f - <<REGLAS || return 1
table inet f1bis {
  chain entrada {
    type filter hook prerouting priority -300; policy accept;
    iifname "${iface}" tcp dport 22 accept
    iifname "${iface}" quota over ${cuota} mbytes drop
  }
}
REGLAS
    nft list chain inet f1bis entrada | grep -q "quota over ${cuota} mbytes" || return 1
    echo "tope en el núcleo: ${cuota} MiB (98 % de ${tope} MiB) en ${iface}, SSH exceptuado"
}

# cortar_red_nft INTERFAZ: descarta TODO lo que entre por INTERFAZ salvo el SSH (la regla del SSH va antes).
cortar_red_nft() {
    nft add rule inet f1bis entrada iifname "$1" drop
}

# contador_rx_bytes: bytes recibidos por la interfaz de la VM (gancho: las pruebas lo sustituyen).
contador_rx_bytes() {
    local i
    i="${IFACE:-$(ls /sys/class/net 2>/dev/null | grep -v -e '^lo$' -e '^docker' -e '^br-' -e '^veth' | head -n 1)}"
    cat "/sys/class/net/${i}/statistics/rx_bytes"
}

# con_limite_de_descarga TOPE_MIB MARGEN_MIB -- COMANDO…
#   Ejecuta COMANDO (en su propio grupo de procesos) y, al llegar a TOPE−MARGEN MiB recibidos desde RX_BASE_BYTES (por defecto,
#   desde ahora): 1) CORTA LA RED (`cortar_red`), 2) termina el grupo ENTERO (TERM; KILL si algún miembro lo ignora) y 3)
#   COMPRUEBA que no queda ningún miembro vivo. Devuelve el código del comando; 4 si lo cortó por el presupuesto; 5 si lo cortó
#   pero ALGÚN miembro del grupo sigue vivo (un líder que muere con TERM no prueba que haya terminado el grupo).
con_limite_de_descarga() {
    local tope="$1" margen="$2" pid base consumido corte
    shift 3
    corte=$((tope - margen))
    base="${RX_BASE_BYTES:-$(contador_rx_bytes)}"
    setsid "$@" &
    pid=$!
    while proceso_vivo "${pid}"; do
        consumido=$(( ($(contador_rx_bytes) - base) / 1048576 ))
        if (( consumido >= corte )); then
            echo "DESCARGA: ${consumido} MiB ≥ umbral de corte ${corte} MiB (tope ${tope} MiB − margen ${margen} MiB): SE CORTA LA RED Y EL COMANDO" >&2
            cortar_red || echo "DESCARGA: AVISO: no se pudo cortar la red" >&2
            kill -TERM -- "-${pid}" 2>/dev/null || true
            if ! esperar_grupo_vacio "${pid}" "${ESPERA_TERM_S:-5}"; then
                kill -KILL -- "-${pid}" 2>/dev/null || true
                esperar_grupo_vacio "${pid}" "${ESPERA_KILL_S:-5}" || true
            fi
            proceso_vivo "${pid}" || wait "${pid}" 2>/dev/null || true       # solo se espera a un líder ya muerto: `wait` no puede colgar el corte
            echo "DESCARGA: consumo tras el corte: $(( ($(contador_rx_bytes) - base) / 1048576 )) MiB (tope ${tope} MiB)" >&2
            if [[ -n "$(miembros_vivos_del_grupo "${pid}")" ]]; then
                echo "DESCARGA: ATENCIÓN: siguen vivos miembros del grupo ${pid}: $(miembros_vivos_del_grupo "${pid}" | tr '\n' ' ')" >&2
                return 5
            fi
            return 4
        fi
        sleep "${INTERVALO_S:-1}"
    done
    wait "${pid}"
}

# vigilante_anfitrion DIR PIDFILE LIBRE_MIN_GB ALMACEN_MAX_GB [INTERVALO_S]
#   Bucle para ejecutar en segundo plano mientras la VM trabaja. Si el espacio libre del anfitrión baja de LIBRE_MIN_GB o el
#   tamaño de DIR supera ALMACEN_MAX_GB: escribe el motivo en DIR/.parada y PARA la VM propia. `libre_gb` es un gancho.
vigilante_anfitrion() {
    local dir="$1" pidfile="$2" libre_min="$3" max_gb="$4" intervalo="${5:-2}" libre uso max_bytes
    max_bytes="${ALMACEN_MAX_BYTES:-$(( max_gb * 1073741824 ))}"     # ALMACEN_MAX_BYTES: solo para las pruebas
    while :; do
        libre="$(libre_gb)"
        uso="$(du -sb -- "${dir}" 2>/dev/null | cut -f1)"
        if [[ "${libre:-0}" -lt "${libre_min}" ]]; then
            echo "espacio libre ${libre} GiB < ${libre_min} GiB" > "${dir}/.parada"
        elif [[ "${uso:-0}" -gt "${max_bytes}" ]]; then
            echo "almacenamiento ${uso} bytes > ${max_gb} GiB" > "${dir}/.parada"
        fi
        if [[ -f "${dir}/.parada" ]]; then
            parar_vm_propia "${dir}" "${pidfile}" || true
            return 0
        fi
        sleep "${intervalo}"
    done
}
