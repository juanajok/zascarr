#!/usr/bin/env bash
# =============================================================================
# lib-ensayo.sh — M4 · Fase 1 bis (#121). Salvaguardas del ARNÉS, comunes al anfitrión y a la VM. NO se ejecuta: se carga con
# `source`. Sin efectos al cargarse. Todas las funciones se prueban con dobles y procesos controlados, sin arrancar QEMU
# (tests/test_ensayo_f1bis_arnes.py).
#
# Qué garantiza y con qué límites (lo que el guion presenta como garantizado):
#
#   · Presupuesto de descarga: `con_limite_de_descarga` MIDE mientras el comando trabaja (bytes recibidos por la interfaz, cada
#     INTERVALO_S segundos) y lo CORTA —señal al grupo de procesos entero, KILL si no cede— al alcanzar el UMBRAL DE CORTE
#     (= tope − margen). El exceso posible es el que entra entre dos muestras: ≤ velocidad máxima × INTERVALO_S. Con el margen por
#     defecto (100 MiB) el tope se respeta mientras la velocidad no pase de 100 MiB/s con muestras de 1 s; si algún día lo
#     pasara, el exceso se mide y se informa, pero no se llama «tope duro» a lo que es un corte con margen acotado.
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

# contador_rx_bytes: bytes recibidos por la interfaz de la VM (gancho: las pruebas lo sustituyen).
contador_rx_bytes() {
    local i
    i="${IFACE:-$(ls /sys/class/net 2>/dev/null | grep -v -e '^lo$' -e '^docker' -e '^br-' -e '^veth' | head -n 1)}"
    cat "/sys/class/net/${i}/statistics/rx_bytes"
}

# con_limite_de_descarga TOPE_MIB MARGEN_MIB -- COMANDO…
#   Ejecuta COMANDO (en su propio grupo de procesos) y lo corta al llegar a TOPE−MARGEN MiB recibidos desde RX_BASE_BYTES (por
#   defecto, desde ahora). Devuelve el código del comando, o 4 si lo cortó por el presupuesto (y deja dicho cuánto se había
#   consumido y cuánto se consumió en total tras el corte: el exceso real, medido).
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
            echo "DESCARGA: ${consumido} MiB ≥ umbral de corte ${corte} MiB (tope ${tope} MiB − margen ${margen} MiB): SE CORTA" >&2
            kill -TERM -- "-${pid}" 2>/dev/null || true
            esperar_muerte "${pid}" 5 || kill -KILL -- "-${pid}" 2>/dev/null || true
            esperar_muerte "${pid}" 5 || true
            wait "${pid}" 2>/dev/null || true
            echo "DESCARGA: consumo tras el corte: $(( ($(contador_rx_bytes) - base) / 1048576 )) MiB (tope ${tope} MiB)" >&2
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
