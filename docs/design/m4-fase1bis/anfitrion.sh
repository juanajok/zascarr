#!/usr/bin/env bash
# =============================================================================
# anfitrion.sh — M4 · Fase 1 bis (#121). Orquesta el ensayo desde el EQUIPO ANFITRIÓN.
#
#     bash anfitrion.sh verificar      # SOLO LECTURA. Comprueba requisitos y límites. No crea nada, no arranca nada.
#     bash anfitrion.sh manifiesto     # SOLO LECTURA. Regenera MANIFIESTO-CANDIDATO.txt desde el repositorio.
#     bash anfitrion.sh preparar       # NECESITA AUTORIZACIÓN. Crea la superposición, arranca la VM CON red, prepara, apaga.
#     bash anfitrion.sh ejecutar       # NECESITA AUTORIZACIÓN. Superposición limpia, VM SIN red, ejecuta el ensayo, apaga.
#     bash anfitrion.sh cerrar         # SOLO LECTURA. Comprueba que no queda QEMU ni puerto, calcula huellas, empaqueta.
#
# Reglas que este script hace cumplir (están en GUION.md):
#   · Nada fuera de $DIR. Nunca se escribe en los discos de la fase 1 (se usan solo como base de solo lectura).
#   · Sin carpetas compartidas, USB ni discos físicos; sin socket Docker del anfitrión; sin puente a la LAN: solo SSH en
#     127.0.0.1:2222.
#   · Red ABIERTA solo en `preparar`; `ejecutar` arranca con `restrict=on` (sin salida ni DNS).
#   · Límites (HACIÉNDOSE CUMPLIR, no solo declarados; mecanismos y márgenes en lib-ensayo.sh): 2 vCPU · 4 GiB · disco de 20 GiB ·
#     descarga ≤ $DESCARGA_MAX_MIB MiB (corte a $DESCARGA_MAX_MIB − $MARGEN_MIB MiB, medido mientras se descarga) · ≤ $ALMACEN_MAX_GB GiB en
#     el anfitrión y ≥ $LIBRE_MIN_GB GiB libres (vigilados cada pocos segundos mientras la VM trabaja; al cruzarlos se PARA la VM) ·
#     ventanas de $VENTANA_PREP_MIN y $VENTANA_EJEC_MIN minutos (el límite se aplica también DENTRO de la VM, no solo al cliente SSH).
#   · Ciclo de vida: `trap` ante salida normal, error o señal; la VM se identifica por PID y atributos; no se anuncia «apagada» sin
#     comprobarlo. `ejecutar` rechaza una preparación incompleta o fallida (marcador `preparacion.ok`).
#   · Condición de parada: se apaga la VM y se informa; NO se borran datos ajenos para hacer sitio.
# =============================================================================
set -uo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_HOST="$(git -C "${AQUI}" rev-parse --show-toplevel)"
CANDIDATO="${CANDIDATO:-f2c04212476d7ec1ed8a69cedc8130b4a7b4b9e9}"
DIR="${ZASCARR_ENSAYO_DIR:-/mnt/Datos/ensayo-m4-f1bis}"
FASE1="${ZASCARR_FASE1_DIR:-/mnt/Datos/ensayo-m4/vm}"        # solo lectura: base-debian12.qcow2, preparacion.qcow2, llave y seed
BASE_QCOW="${FASE1}/base-debian12.qcow2"
PREP_BASE="${FASE1}/preparacion.qcow2"
CLAVE="${FASE1}/ensayo_key"
SEED="${FASE1}/seed.iso"
PUERTO="${PUERTO_SSH:-2222}"
DESCARGA_MAX_MIB="${DESCARGA_MAX_MIB:-600}"
MARGEN_MIB="${MARGEN_MIB:-100}"
ALMACEN_MAX_GB="${ALMACEN_MAX_GB:-25}"
LIBRE_MIN_GB="${LIBRE_MIN_GB:-10}"
VENTANA_PREP_MIN="${VENTANA_PREP_MIN:-45}"
VENTANA_EJEC_MIN="${VENTANA_EJEC_MIN:-60}"
MANIFIESTO="${AQUI}/MANIFIESTO-CANDIDATO.txt"
PIDFILE="${DIR}/qemu.pid"
# shellcheck source=docs/design/m4-fase1bis/lib-ensayo.sh
source "${AQUI}/lib-ensayo.sh"

info() { echo "→ $*"; }
ok()   { echo "✓ $*"; }
mal()  { echo "✗ $*" >&2; }
die()  { mal "$*"; exit 1; }
libre_gb() { df --output=avail -BG "$(dirname "${DIR}")" | tail -n 1 | tr -dc '0-9'; }
SSH_ARGS=(-i "${CLAVE}" -p "${PUERTO}" -o StrictHostKeyChecking=no -o UserKnownHostsFile="${DIR}/known_hosts"
          -o ConnectTimeout=8 -o BatchMode=yes ensayo@127.0.0.1)
scp_vm() { scp -q -i "${CLAVE}" -P "${PUERTO}" -o StrictHostKeyChecking=no -o UserKnownHostsFile="${DIR}/known_hosts" "$@"; }
valor_manifiesto() { grep -E "^$1=" "${MANIFIESTO}" | head -n 1 | cut -d= -f2-; }

# ── manifiesto ────────────────────────────────────────────────────────────────────────────────────────────────────
cmd_manifiesto() {
    git -C "${REPO_HOST}" cat-file -e "${CANDIDATO}^{commit}" 2>/dev/null || die "el repositorio no tiene el commit ${CANDIDATO}"
    local f h
    {
        echo "# Manifiesto del candidato — M4 fase 1 bis (#121). Generado por: anfitrion.sh manifiesto. Solo lectura."
        echo "# Formato CLAVE=valor para lo que consumen los scripts; el resto son tablas informativas."
        echo "CANDIDATO=${CANDIDATO}"
        echo "ARBOL=$(git -C "${REPO_HOST}" rev-parse "${CANDIDATO}^{tree}")"
        echo "PADRES=$(git -C "${REPO_HOST}" rev-list --parents -n 1 "${CANDIDATO}" | cut -d' ' -f2-)"
        echo "ASUNTO=$(git -C "${REPO_HOST}" log -1 --format=%s "${CANDIDATO}")"
        echo "FECHA_COMMIT=$(git -C "${REPO_HOST}" log -1 --format=%cI "${CANDIDATO}")"
        echo "BOOTSTRAP_SHA256=$(git -C "${REPO_HOST}" show "${CANDIDATO}:bootstrap.sh" | sha256sum | cut -d' ' -f1)"
        echo "CSS_SHA256=$(git -C "${REPO_HOST}" show "${CANDIDATO}:src/zascarr/static/web.css" | sha256sum | cut -d' ' -f1)"
        local cabeza
        cabeza="$(git -C "${REPO_HOST}" ls-tree --name-only "${CANDIDATO}" alembic/versions/ | sed 's#.*/##' | grep -E '^[0-9]{8}_[0-9]{4}_' | sort | tail -n 1)"
        echo "ALEMBIC_FICHERO=${cabeza}"
        echo "ALEMBIC_ESPERADA=$(git -C "${REPO_HOST}" show "${CANDIDATO}:alembic/versions/${cabeza}" | sed -n 's/^revision = "\(.*\)"/\1/p' | head -n 1)"
        echo "MEMORIA_COMPOSE=$(git -C "${REPO_HOST}" show "${CANDIDATO}:docker-compose.yml" | grep -c 'memory: 512M') servicios con 512M (aplicación y PostgreSQL); servicio credenciales 16M"
        echo "FLAGS_FUENTES_QUE_COMPOSE_TRANSMITE=$(git -C "${REPO_HOST}" show "${CANDIDATO}:docker-compose.yml" | grep -oE '[A-Z]+_ENABLED' | sort -u | tr '\n' ' ')"
        echo "DEFAULTS_FUENTES_CONFIG=$(git -C "${REPO_HOST}" show "${CANDIDATO}:src/zascarr/config.py" | grep -E '^\s+(comicvine|anilist|tebeosfera|gcd)_enabled' | sed 's/^ *//' | tr '\n' ';')"
        echo "# Punto de partida de la VM (fase 1, solo lectura): se comprueban con 'verificar'"
        echo "BASE_QCOW_SHA512=56c0bd55b6623f2739f377e983d2872e7b208d0cb9c3ba4e93d3f72929026da03637c598b3bd472b29998c31c8a4c17d8e6ae1c556852a8b83a66a09bf5c2b37"
        echo "PREPARACION_QCOW_SHA256=6ed7f684335940ba294dbdacd91f5c5e4632c24b9d7aaed975fbefea9a0f28b9"
        echo "PREPARACION_QCOW_CONTENIDO=Debian 12 + Docker 5:29.8.2 + imágenes postgres:15-alpine y python:3.11-slim-bookworm (por digest) + git + python3; SIN instalación del producto (fase 1)"
        echo "BASE_QCOW_ORIGEN=debian-12-genericcloud-amd64.qcow2, build 20261015-2632 (cloud.debian.org, verificado en la fase 1)"
        echo "DIGEST_POSTGRES=sha256:f7d23353e1b15400d22ebe31189f4d314b87a4c129cc400c8c2d8d4ca127bf81"
        echo "DIGEST_PYTHON=sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89"
        echo "DOCKER_VERSIONES=docker-ce/cli 5:29.8.2-1~debian.12~bookworm · containerd.io 2.4.2-2 · buildx 0.38.0-1 · compose 5.6.0-1 (APT oficial, fase 1)"
        echo "# Huellas SHA-256 de ficheros del candidato (git show COMMIT:ruta | sha256sum)"
        for f in bootstrap.sh docker-compose.yml Dockerfile .env.example pyproject.toml scripts/_credenciales.sh scripts/credenciales.sh \
                 scripts/_comun.sh scripts/update.sh scripts/backup.sh scripts/rollback.sh scripts/uninstall.sh \
                 src/zascarr/utils/credenciales.py src/zascarr/config.py; do
            h="$(git -C "${REPO_HOST}" show "${CANDIDATO}:${f}" 2>/dev/null | sha256sum | cut -d' ' -f1)"
            printf 'SHA256 %s  %s\n' "${h}" "${f}"
        done
    } > "${MANIFIESTO}"
    ok "manifiesto escrito en ${MANIFIESTO}"
}

# ── verificar (solo lectura) ──────────────────────────────────────────────────────────────────────────────────────
cmd_verificar() {
    local fallos=0 req
    chk() { if "${@:2}" >/dev/null 2>&1; then ok "$1"; else mal "$1"; fallos=$((fallos + 1)); fi; }
    info "Comprobaciones de SOLO LECTURA. No se crea ni se arranca nada."
    chk "acceso de lectura y escritura a /dev/kvm" test -r /dev/kvm -a -w /dev/kvm
    for req in qemu-system-x86_64 qemu-img git ssh scp sha256sum sha512sum; do chk "disponible: ${req}" command -v "${req}"; done
    chk "el repositorio tiene el candidato ${CANDIDATO:0:12}…" git -C "${REPO_HOST}" cat-file -e "${CANDIDATO}^{commit}"
    chk "el manifiesto existe" test -f "${MANIFIESTO}"
    chk "el manifiesto es el del candidato" bash -c "[[ \"\$(grep -E '^CANDIDATO=' '${MANIFIESTO}' | cut -d= -f2)\" == '${CANDIDATO}' ]]"
    chk "el manifiesto está al día (regenerarlo no lo cambia)" bash -c "diff -q '${MANIFIESTO}' <(CANDIDATO='${CANDIDATO}' bash '${AQUI}/anfitrion.sh' manifiesto-stdout)"
    for req in "${BASE_QCOW}" "${PREP_BASE}" "${CLAVE}" "${SEED}"; do chk "existe (fase 1, solo lectura): ${req}" test -e "${req}"; done
    chk "ningún proceso QEMU en marcha" test -z "$(procesos_qemu)"
    chk "el puerto ${PUERTO} está libre" bash -c "! ss -ltn | grep -q ':${PUERTO} '"
    local libre; libre="$(libre_gb)"
    chk "espacio libre en el anfitrión ${libre} GB ≥ ${LIBRE_MIN_GB} + lo previsto (${ALMACEN_MAX_GB})" test "${libre:-0}" -ge $((LIBRE_MIN_GB + ALMACEN_MAX_GB))
    chk "el directorio de trabajo ${DIR} no existe (o está vacío)" bash -c "[[ ! -e '${DIR}' ]] || [[ -z \"\$(ls -A '${DIR}')\" ]]"
    if [[ "${1:-}" != "--rapido" ]]; then
        info "Comprobando la huella de la imagen base (tarda unos segundos)…"
        chk "SHA-512 de la imagen base = el del manifiesto (fase 1)" \
            bash -c "[[ \"\$(sha512sum '${BASE_QCOW}' | cut -d' ' -f1)\" == '$(valor_manifiesto BASE_QCOW_SHA512)' ]]"
        info "Comprobando la huella del punto de partida de la VM (3 GB, ~20 s)…"
        chk "SHA-256 de preparacion.qcow2 = el del manifiesto (fase 1, sin modificar)" \
            bash -c "[[ \"\$(sha256sum '${PREP_BASE}' | cut -d' ' -f1)\" == '$(valor_manifiesto PREPARACION_QCOW_SHA256)' ]]"
    fi
    [[ ${fallos} -eq 0 ]] && ok "TODO EN ORDEN: se puede pedir autorización para 'preparar'" || { mal "${fallos} comprobación(es) fallida(s): no se debe continuar"; return 1; }
}

# ── VM ────────────────────────────────────────────────────────────────────────────────────────────────────────────
# Las acciones sobre la VM pasan por funciones pequeñas que las pruebas sustituyen por dobles (tests/test_ensayo_f1bis_arnes.py).
ssh_remoto() {  # ssh_remoto SEGUNDOS ORDEN… : con límite de tiempo del cliente
    local seg="$1"; shift
    timeout --kill-after=10 "${seg}" ssh "${SSH_ARGS[@]}" "$@"
}
solicitar_apagado() { ssh_remoto 20 'sudo sync; sudo systemctl poweroff' >/dev/null 2>&1 || true; }
arrancar() {  # arrancar DISCO red(abierta|cerrada)
    local red="user,id=n0,hostfwd=tcp:127.0.0.1:${PUERTO}-:22"
    [[ "$2" == "cerrada" ]] && red="${red},restrict=on"
    qemu-system-x86_64 -name "${NOMBRE_VM}" -machine q35,accel=kvm -cpu host -smp 2 -m 4096 -nodefaults -display none \
        -serial "file:${DIR}/consola-$(basename "$1" .qcow2).log" -daemonize -pidfile "${PIDFILE}" \
        -drive "file=$1,if=virtio,format=qcow2,cache=writeback" \
        -drive "file=${SEED},if=virtio,format=raw,readonly=on,media=cdrom" \
        -netdev "${red}" -device virtio-net-pci,netdev=n0 -device virtio-rng-pci
}
esperar_ssh() { local i; for i in $(seq 1 "${INTENTOS_SSH:-60}"); do ssh_remoto 15 true 2>/dev/null && return 0; sleep "${PAUSA_SSH_S:-4}"; done; return 1; }
cronologia() { echo "$(date -Is) $*" | tee -a "${DIR}/cronologia.txt"; }

VIGILANTE_PID=""
iniciar_supervision() {
    # Limpieza ante salida normal, error o señal: la VM propia no se queda viva ni el vigilante colgado.
    trap 'exit 130' INT; trap 'exit 143' TERM; trap 'exit 129' HUP
    trap limpiar EXIT
    rm -f "${DIR}/.parada"
    vigilante_anfitrion "${DIR}" "${PIDFILE}" "${LIBRE_MIN_GB}" "${ALMACEN_MAX_GB}" "${INTERVALO_VIGILANTE_S:-2}" &
    VIGILANTE_PID=$!
}
limpiar() {
    local rc=$? estado
    trap - EXIT INT TERM HUP
    [[ -n "${VIGILANTE_PID}" ]] && kill "${VIGILANTE_PID}" 2>/dev/null
    local j; for j in $(jobs -p); do kill "${j}" 2>/dev/null; done      # el comando remoto en segundo plano, si lo hubiera
    parar_vm_propia "${DIR}" "${PIDFILE}"; estado=$?
    case ${estado} in
        0) cronologia "LIMPIEZA: no queda ninguna VM propia (comprobado) · rc=${rc}" ;;
        1) mal "LA VM PROPIA SIGUE VIVA tras TERM y KILL (PID $(cat "${PIDFILE}" 2>/dev/null)): hay que pararla a mano"; rc=${rc:-1}; [[ ${rc} -eq 0 ]] && rc=1 ;;
        3) mal "el PID de ${PIDFILE} no es la VM de este ensayo: no se ha tocado"; [[ ${rc} -eq 0 ]] && rc=1 ;;
    esac
    [[ -f "${DIR}/.parada" ]] && { mal "PARADA POR LÍMITE DEL ANFITRIÓN: $(cat "${DIR}/.parada")"; [[ ${rc} -eq 0 ]] && rc=1; }
    exit "${rc}"
}

exigir_preparacion_completa() {
    local m="${DIR}/preparacion.ok" tam mtime
    [[ -f "${m}" ]] || { mal "no hay preparación COMPLETA (falta ${m}): 'preparar' no terminó bien o no se ejecutó"; return 1; }
    [[ "$(sed -n 's/^CANDIDATO=//p' "${m}")" == "${CANDIDATO}" ]] || { mal "la preparación es de otro candidato"; return 1; }
    [[ "$(sed -n 's/^RC=//p' "${m}")" == "0" ]] || { mal "la preparación terminó con error"; return 1; }
    [[ -f "${DIR}/.parada" ]] && { mal "la preparación se interrumpió por un límite: $(cat "${DIR}/.parada")"; return 1; }
    [[ -f "${DIR}/f1bis-prep.qcow2" ]] || { mal "falta f1bis-prep.qcow2"; return 1; }
    tam="$(stat -c %s "${DIR}/f1bis-prep.qcow2")"; mtime="$(stat -c %Y "${DIR}/f1bis-prep.qcow2")"
    [[ "$(sed -n 's/^PREP_BYTES=//p' "${m}")" == "${tam}" && "$(sed -n 's/^PREP_MTIME=//p' "${m}")" == "${mtime}" ]] \
        || { mal "f1bis-prep.qcow2 cambió después de preparar (tamaño o fecha)"; return 1; }
    [[ ! -e "${DIR}/f1bis-ejec.qcow2" ]] || { mal "ya existe f1bis-ejec.qcow2: una ejecución previa. No se reutiliza (usa un directorio nuevo)"; return 1; }
    return 0
}

crear_bundle() {
    git init -q --bare "${DIR}/espejo.git" && git -C "${DIR}/espejo.git" fetch -q "${REPO_HOST}" "${CANDIDATO}:refs/heads/main" || return 1
    git -C "${DIR}/espejo.git" bundle create "${DIR}/candidato.bundle" main >/dev/null 2>&1 || return 1
    sha256sum "${DIR}/candidato.bundle" | tee "${DIR}/candidato.bundle.sha256"
    git -C "${REPO_HOST}" show "${CANDIDATO}:bootstrap.sh" > "${DIR}/bootstrap.sh"
}

# El comando remoto largo va EN SEGUNDO PLANO y se espera con `wait`: bash difiere los `trap` mientras corre una orden en primer
# plano, y una señal (Ctrl-C, SIGTERM) tardaría hasta el final de la ventana en limpiar; `wait` sí se interrumpe.
REMOTO_RC=255
remoto_con_salida() {  # remoto_con_salida SEGUNDOS "orden" FICHERO → código en REMOTO_RC
    local seg="$1" orden="$2" fichero="$3" rcf
    rcf="$(mktemp)"
    { ssh_remoto "${seg}" "${orden}"; echo $? > "${rcf}"; } 2>&1 | tee "${fichero}" &
    wait $!
    REMOTO_RC="$(cat "${rcf}" 2>/dev/null || echo 255)"; rm -f "${rcf}"
}

cmd_preparar() {
    cmd_verificar || die "'verificar' no pasa: no se prepara nada"
    mkdir -p "${DIR}" || die "no puedo crear ${DIR}"
    iniciar_supervision
    cronologia "INICIO preparar (ventana ${VENTANA_PREP_MIN} min; descarga ≤ ${DESCARGA_MAX_MIB} MiB con corte a $((DESCARGA_MAX_MIB - MARGEN_MIB)) MiB)"
    crear_bundle || die "no pude crear el bundle del candidato"
    qemu-img create -q -f qcow2 -b "${PREP_BASE}" -F qcow2 "${DIR}/f1bis-prep.qcow2" 20G || die "no pude crear la superposición"
    arrancar "${DIR}/f1bis-prep.qcow2" abierta || die "no arranca la VM"
    esperar_ssh || die "la VM no responde por SSH"
    cronologia "VM arrancada (red ABIERTA, solo para esta preparación)"
    scp_vm "${DIR}/candidato.bundle" ensayo@127.0.0.1:/tmp/candidato.bundle || die "no pude copiar el bundle"
    scp_vm "${DIR}/bootstrap.sh" ensayo@127.0.0.1:/home/ensayo/bootstrap.sh || die "no pude copiar bootstrap.sh"
    scp_vm "${AQUI}/vm-preparar.sh" "${AQUI}/vm-ejecutar.sh" "${AQUI}/lib-ensayo.sh" ensayo@127.0.0.1:/home/ensayo/ || die "no pude copiar los scripts"
    # El límite de tiempo se aplica DENTRO de la VM (`timeout` mata el grupo de procesos entero); el del cliente es de respaldo.
    remoto_con_salida $((VENTANA_PREP_MIN * 60 + 90)) "sudo timeout --kill-after=30 $((VENTANA_PREP_MIN * 60)) env CANDIDATO='${CANDIDATO}' DIGEST_POSTGRES='$(valor_manifiesto DIGEST_POSTGRES)' DIGEST_PYTHON='$(valor_manifiesto DIGEST_PYTHON)' DESCARGA_MAX_MIB='${DESCARGA_MAX_MIB}' MARGEN_MIB='${MARGEN_MIB}' bash /home/ensayo/vm-preparar.sh" "${DIR}/preparacion.log"
    local rc=${REMOTO_RC}
    mkdir -p "${DIR}/evidencia-preparacion"
    ssh_remoto 120 'sudo tar -C /root/ensayo -czf - preparacion' > "${DIR}/evidencia-preparacion/preparacion.tar.gz" 2>/dev/null || true
    parar_vm_propia "${DIR}" "${PIDFILE}"; local vm=$?
    [[ ${vm} -eq 0 ]] || { mal "la VM no se pudo apagar (código ${vm})"; return 1; }
    cronologia "FIN preparar rc=${rc}; VM apagada y comprobada"
    [[ ${rc} -eq 0 ]] && grep -q 'PREPARACIÓN TERMINADA' "${DIR}/preparacion.log" && [[ ! -f "${DIR}/.parada" ]] || die "la preparación NO terminó bien (rc=${rc}); no se escribe preparacion.ok"
    {
        echo "CANDIDATO=${CANDIDATO}"; echo "RC=${rc}"; echo "FECHA=$(date -Is)"
        echo "PREP_BYTES=$(stat -c %s "${DIR}/f1bis-prep.qcow2")"; echo "PREP_MTIME=$(stat -c %Y "${DIR}/f1bis-prep.qcow2")"
        echo "DESCARGA_MIB=$(sed -n 's/^descargado hasta ahora: \([0-9]*\) MiB.*/\1/p' "${DIR}/preparacion.log" | tail -n 1)"
    } > "${DIR}/preparacion.ok"
    ok "preparación terminada y registrada (${DIR}/preparacion.ok)"
}

cmd_ejecutar() {
    exigir_preparacion_completa || die "no se ejecuta"
    [[ -z "$(procesos_qemu)" ]] || die "hay un proceso QEMU en marcha"
    mkdir -p "${DIR}"
    iniciar_supervision
    chmod a-w "${DIR}/f1bis-prep.qcow2"
    qemu-img create -q -f qcow2 -b "${DIR}/f1bis-prep.qcow2" -F qcow2 "${DIR}/f1bis-ejec.qcow2" 20G || die "no pude crear la superposición de ejecución"
    cronologia "INICIO ejecutar (ventana ${VENTANA_EJEC_MIN} min, red CERRADA)"
    arrancar "${DIR}/f1bis-ejec.qcow2" cerrada || die "no arranca la VM"
    esperar_ssh || die "la VM no responde por SSH"
    remoto_con_salida $((VENTANA_EJEC_MIN * 60 + 90)) "sudo timeout --kill-after=30 $((VENTANA_EJEC_MIN * 60)) env CANDIDATO='${CANDIDATO}' BOOTSTRAP_SHA256='$(valor_manifiesto BOOTSTRAP_SHA256)' ALEMBIC_ESPERADA='$(valor_manifiesto ALEMBIC_ESPERADA)' CSS_SHA256='$(valor_manifiesto CSS_SHA256)' MUESTRAS='${MUESTRAS:-5}' bash /home/ensayo/vm-ejecutar.sh" "${DIR}/ejecucion.log"
    local rc=${REMOTO_RC}
    mkdir -p "${DIR}/evidencia"
    ssh_remoto 120 'sudo tar -C /root/ensayo -czf - evidencia' > "${DIR}/evidencia/evidencia-vm.tar.gz" 2>/dev/null || true
    parar_vm_propia "${DIR}" "${PIDFILE}"; local vm=$?
    [[ ${vm} -eq 0 ]] || { mal "la VM no se pudo apagar (código ${vm})"; return 1; }
    cronologia "FIN ejecutar rc=${rc} (3 = PARADA DE SEGURIDAD; 2 = precondición del arnés; 124/137 = ventana agotada); VM apagada y comprobada"
    return "${rc}"
}

cmd_cerrar() {
    local fallos=0
    [[ -z "$(procesos_qemu)" ]] && ok "sin proceso QEMU" || { mal "queda un proceso QEMU: $(procesos_qemu | tr '\n' ' ')"; fallos=1; }
    ss -ltn | grep -q ":${PUERTO} " && { mal "el puerto ${PUERTO} sigue abierto"; fallos=1; } || ok "puerto ${PUERTO} cerrado"
    ( cd "${DIR}" && sha256sum candidato.bundle bootstrap.sh f1bis-prep.qcow2 f1bis-ejec.qcow2 2>/dev/null ) | tee "${DIR}/huellas-finales.txt"
    du -sh "${DIR}" | tee "${DIR}/almacenamiento.txt"
    ok "evidencia en ${DIR}/evidencia/ (revisar y sanear antes de compartir)"
    return "${fallos}"
}

# Solo se ejecuta si se llama como programa (las pruebas lo cargan con `source` para probar las funciones con dobles).
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
case "${1:-}" in
    verificar) shift; cmd_verificar "$@" ;;
    manifiesto) cmd_manifiesto ;;
    manifiesto-stdout) _tmp="$(mktemp)"; MANIFIESTO="${_tmp}"; cmd_manifiesto >/dev/null; cat "${_tmp}"; rm -f "${_tmp}" ;;
    preparar) cmd_preparar ;;
    ejecutar) cmd_ejecutar ;;
    cerrar) cmd_cerrar ;;
    *) sed -n '2,14p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
fi
