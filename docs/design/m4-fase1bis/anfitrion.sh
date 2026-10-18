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
#   · Límites: 2 vCPU · 4 GB · disco de 20 GB · ≤ $DESCARGA_MAX_MB de descarga · ≤ $ALMACEN_MAX_GB en el anfitrión · ≥ $LIBRE_MIN_GB
#     libres en el anfitrión durante toda la fase · ventanas de $VENTANA_PREP_MIN y $VENTANA_EJEC_MIN minutos.
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
DESCARGA_MAX_MB="${DESCARGA_MAX_MB:-600}"
ALMACEN_MAX_GB="${ALMACEN_MAX_GB:-25}"
LIBRE_MIN_GB="${LIBRE_MIN_GB:-10}"
VENTANA_PREP_MIN="${VENTANA_PREP_MIN:-45}"
VENTANA_EJEC_MIN="${VENTANA_EJEC_MIN:-60}"
MANIFIESTO="${AQUI}/MANIFIESTO-CANDIDATO.txt"

info() { echo "→ $*"; }
ok()   { echo "✓ $*"; }
mal()  { echo "✗ $*" >&2; }
die()  { mal "$*"; exit 1; }
libre_gb() { df --output=avail -BG "$(dirname "${DIR}")" | tail -n 1 | tr -dc '0-9'; }
SSH_ARGS=(-i "${CLAVE}" -p "${PUERTO}" -o StrictHostKeyChecking=no -o UserKnownHostsFile="${DIR}/known_hosts"
          -o ConnectTimeout=8 -o BatchMode=yes ensayo@127.0.0.1)
ssh_vm() { ssh "${SSH_ARGS[@]}" "$@"; }
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
    chk "el manifiesto está al día (regenerarlo no lo cambia)" bash -c "cd '${AQUI}' && diff -q '${MANIFIESTO}' <(CANDIDATO='${CANDIDATO}' bash '${BASH_SOURCE[0]}' manifiesto-stdout) "
    for req in "${BASE_QCOW}" "${PREP_BASE}" "${CLAVE}" "${SEED}"; do chk "existe (fase 1, solo lectura): ${req}" test -e "${req}"; done
    chk "ninguna VM en marcha" bash -c "! pgrep -x qemu-system-x86_64 >/dev/null"
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
arrancar() {  # arrancar DISCO red(abierta|cerrada)
    local red="user,id=n0,hostfwd=tcp:127.0.0.1:${PUERTO}-:22"
    [[ "$2" == "cerrada" ]] && red="${red},restrict=on"
    qemu-system-x86_64 -name m4-f1bis -machine q35,accel=kvm -cpu host -smp 2 -m 4096 -nodefaults -display none \
        -serial "file:${DIR}/consola-$(basename "$1" .qcow2).log" -daemonize -pidfile "${DIR}/qemu.pid" \
        -drive "file=$1,if=virtio,format=qcow2,cache=writeback" \
        -drive "file=${SEED},if=virtio,format=raw,readonly=on,media=cdrom" \
        -netdev "${red}" -device virtio-net-pci,netdev=n0 -device virtio-rng-pci
}
esperar_ssh() { local i; for i in $(seq 1 60); do ssh_vm true 2>/dev/null && return 0; sleep 4; done; return 1; }
apagar() {
    ssh_vm 'sudo sync; sudo systemctl poweroff' 2>/dev/null || true
    local i; for i in $(seq 1 40); do [[ -e "${DIR}/qemu.pid" ]] && kill -0 "$(cat "${DIR}/qemu.pid")" 2>/dev/null || break; sleep 2; done
    if [[ -e "${DIR}/qemu.pid" ]] && kill -0 "$(cat "${DIR}/qemu.pid")" 2>/dev/null; then kill "$(cat "${DIR}/qemu.pid")" 2>/dev/null || true; fi
    rm -f "${DIR}/qemu.pid"
}
cronologia() { echo "$(date -Is) $*" | tee -a "${DIR}/cronologia.txt"; }
vigilar_espacio() { [[ "$(libre_gb)" -ge "${LIBRE_MIN_GB}" ]] || { mal "el espacio libre bajó de ${LIBRE_MIN_GB} GB: se detiene"; return 1; }; }

cmd_preparar() {
    cmd_verificar || die "'verificar' no pasa: no se prepara nada"
    mkdir -p "${DIR}" || die "no puedo crear ${DIR}"
    cronologia "INICIO preparar (ventana ${VENTANA_PREP_MIN} min, descarga ≤ ${DESCARGA_MAX_MB} MB)"
    # Bundle del candidato, desde el repositorio local (sin red).
    git init -q --bare "${DIR}/espejo.git" && git -C "${DIR}/espejo.git" fetch -q "${REPO_HOST}" "${CANDIDATO}:refs/heads/main" || die "no pude traer el candidato"
    git -C "${DIR}/espejo.git" bundle create "${DIR}/candidato.bundle" main >/dev/null 2>&1 || die "no pude crear el bundle"
    sha256sum "${DIR}/candidato.bundle" | tee "${DIR}/candidato.bundle.sha256"
    git -C "${REPO_HOST}" show "${CANDIDATO}:bootstrap.sh" > "${DIR}/bootstrap.sh"
    qemu-img create -q -f qcow2 -b "${PREP_BASE}" -F qcow2 "${DIR}/f1bis-prep.qcow2" 20G || die "no pude crear la superposición"
    arrancar "${DIR}/f1bis-prep.qcow2" abierta || die "no arranca la VM"
    esperar_ssh || { apagar; die "la VM no responde por SSH"; }
    cronologia "VM arrancada (red ABIERTA, solo para esta preparación)"
    scp_vm "${DIR}/candidato.bundle" ensayo@127.0.0.1:/tmp/candidato.bundle
    scp_vm "${DIR}/bootstrap.sh" ensayo@127.0.0.1:/home/ensayo/bootstrap.sh
    scp_vm "${AQUI}/vm-preparar.sh" "${AQUI}/vm-ejecutar.sh" ensayo@127.0.0.1:/home/ensayo/
    timeout $((VENTANA_PREP_MIN * 60)) ssh "${SSH_ARGS[@]}" "sudo env CANDIDATO='${CANDIDATO}' DIGEST_POSTGRES='$(valor_manifiesto DIGEST_POSTGRES)' DIGEST_PYTHON='$(valor_manifiesto DIGEST_PYTHON)' DESCARGA_MAX_MB='${DESCARGA_MAX_MB}' bash /home/ensayo/vm-preparar.sh" \
        | tee "${DIR}/preparacion.log"
    local rc=${PIPESTATUS[0]}
    mkdir -p "${DIR}/evidencia-preparacion"
    ssh_vm 'sudo tar -C /root/ensayo -czf - preparacion' > "${DIR}/evidencia-preparacion/preparacion.tar.gz" 2>/dev/null || true
    apagar
    vigilar_espacio || true
    cronologia "FIN preparar rc=${rc}; VM apagada"
    [[ ${rc} -eq 0 ]] && ok "preparación terminada" || die "la preparación falló (rc=${rc}); ver ${DIR}/preparacion.log"
}

cmd_ejecutar() {
    [[ -f "${DIR}/f1bis-prep.qcow2" ]] || die "primero 'preparar'"
    [[ -n "$(pgrep -x qemu-system-x86_64)" ]] && die "hay una VM en marcha"
    chmod a-w "${DIR}/f1bis-prep.qcow2"
    qemu-img create -q -f qcow2 -b "${DIR}/f1bis-prep.qcow2" -F qcow2 "${DIR}/f1bis-ejec.qcow2" 20G || die "no pude crear la superposición de ejecución"
    cronologia "INICIO ejecutar (ventana ${VENTANA_EJEC_MIN} min, red CERRADA)"
    arrancar "${DIR}/f1bis-ejec.qcow2" cerrada || die "no arranca la VM"
    esperar_ssh || { apagar; die "la VM no responde por SSH"; }
    timeout $((VENTANA_EJEC_MIN * 60)) ssh "${SSH_ARGS[@]}" "sudo env CANDIDATO='${CANDIDATO}' BOOTSTRAP_SHA256='$(valor_manifiesto BOOTSTRAP_SHA256)' ALEMBIC_ESPERADA='$(valor_manifiesto ALEMBIC_ESPERADA)' CSS_SHA256='$(valor_manifiesto CSS_SHA256)' MUESTRAS='${MUESTRAS:-5}' bash /home/ensayo/vm-ejecutar.sh" \
        | tee "${DIR}/ejecucion.log"
    local rc=${PIPESTATUS[0]}
    mkdir -p "${DIR}/evidencia"
    ssh_vm 'sudo tar -C /root/ensayo -czf - evidencia' > "${DIR}/evidencia/evidencia-vm.tar.gz" 2>/dev/null || true
    apagar
    cronologia "FIN ejecutar rc=${rc} (3 = PARADA DE SEGURIDAD; 124 = ventana agotada); VM apagada"
    return "${rc}"
}

cmd_cerrar() {
    local fallos=0
    pgrep -x qemu-system-x86_64 >/dev/null && { mal "queda un proceso QEMU"; fallos=1; } || ok "sin proceso QEMU"
    ss -ltn | grep -q ":${PUERTO} " && { mal "el puerto ${PUERTO} sigue abierto"; fallos=1; } || ok "puerto ${PUERTO} cerrado"
    ( cd "${DIR}" && sha256sum candidato.bundle bootstrap.sh f1bis-prep.qcow2 f1bis-ejec.qcow2 2>/dev/null ) | tee "${DIR}/huellas-finales.txt"
    du -sh "${DIR}" | tee "${DIR}/almacenamiento.txt"
    ok "evidencia en ${DIR}/evidencia/ (revisar y sanear antes de compartir)"
    return "${fallos}"
}

case "${1:-}" in
    verificar) shift; cmd_verificar "$@" ;;
    manifiesto) cmd_manifiesto ;;
    manifiesto-stdout) MANIFIESTO_SALIDA=/dev/stdout; _tmp="$(mktemp)"; MANIFIESTO="${_tmp}"; cmd_manifiesto >/dev/null; cat "${_tmp}"; rm -f "${_tmp}" ;;
    preparar) cmd_preparar ;;
    ejecutar) cmd_ejecutar ;;
    cerrar) cmd_cerrar ;;
    *) sed -n '2,14p' "${BASH_SOURCE[0]}"; exit 2 ;;
esac
