#!/usr/bin/env bash
# =============================================================================
# vm-preparar.sh — M4 · Fase 1 bis (#121). Se ejecuta DENTRO de la VM, como root. ÚNICA fase con red abierta.
#
#     sudo env CANDIDATO=<sha> DIGEST_POSTGRES=sha256:… DIGEST_PYTHON=sha256:… bash vm-preparar.sh
#
# Qué hace (y nada más):
#   1. Comprueba que el punto de partida está limpio (sin instalación del producto).
#   2. Pone el espejo local de Git con main = candidato (desde /tmp/candidato.bundle) y comprueba su configuración.
#   3. Comprueba que las dos imágenes base siguen siendo las de la fase 1 (por digest). NO descarga imágenes.
#   4. Construye UNA vez la imagen del candidato desde el espejo (descarga paquetes de Debian y de PyPI): deja las capas en
#      caché para que el bootstrap.sh de la ejecución, SIN red, pueda construir. Eso NO acredita una construcción en frío.
#   5. Verifica la biblioteca sintética, el usuario ordinario sin privilegios y que no hay ni rastro del producto.
#   6. Informa de lo descargado (bytes recibidos por la VM) y aborta si supera el presupuesto.
# =============================================================================
set -euo pipefail
CANDIDATO="${CANDIDATO:?falta CANDIDATO}"
DIGEST_POSTGRES="${DIGEST_POSTGRES:?falta DIGEST_POSTGRES}"
DIGEST_PYTHON="${DIGEST_PYTHON:?falta DIGEST_PYTHON}"
LIMITE_MB="${DESCARGA_MAX_MB:-600}"
EV="${EV:-/root/ensayo/preparacion}"
OTRO="${OTRO:-otroprueba}"
mkdir -p "${EV}"
IFACE="$(ls /sys/class/net | grep -v '^lo$' | grep -v '^docker' | head -n 1)"
rx() { cat "/sys/class/net/${IFACE}/statistics/rx_bytes"; }
RX0="$(rx)"
presupuesto() {
    local mb=$(( ($(rx) - RX0) / 1048576 ))
    echo "descargado hasta ahora: ${mb} MB (presupuesto ${LIMITE_MB} MB)" | tee -a "${EV}/descarga.txt"
    (( mb <= LIMITE_MB )) || { echo "PRESUPUESTO DE DESCARGA SUPERADO: se detiene"; exit 4; }
}
paso() { echo; echo "── $* ──"; }

paso "1. punto de partida limpio"
[[ ! -e /opt/zascarr && ! -e /var/lib/zascarr ]] || { echo "ya hay una instalación del producto: se necesita un punto de partida limpio"; exit 2; }
[[ "$(docker ps -aq | wc -l)" == "0" ]] || { echo "hay contenedores"; exit 2; }
! getent passwd media >/dev/null || { echo "ya existe el usuario 'media'"; exit 2; }
date -Is | tee "${EV}/inicio.txt"

paso "2. espejo local del candidato"
[[ -f /tmp/candidato.bundle ]] || { echo "falta /tmp/candidato.bundle"; exit 2; }
rm -rf /srv/espejo/zascarr.git
install -d /srv/espejo
git init -q --bare /srv/espejo/zascarr.git
git -C /srv/espejo/zascarr.git fetch -q /tmp/candidato.bundle main:refs/heads/main
git -C /srv/espejo/zascarr.git symbolic-ref HEAD refs/heads/main
[[ "$(git -C /srv/espejo/zascarr.git rev-parse main)" == "${CANDIDATO}" ]] || { echo "main del espejo != candidato"; exit 2; }
git config --system url./srv/espejo/zascarr.git.insteadOf https://github.com/juanajok/zascarr.git
git config --system --unset safe.directory 2>/dev/null || true
[[ "$(git ls-remote https://github.com/juanajok/zascarr.git HEAD | cut -f1)" == "${CANDIDATO}" ]] || { echo "git no resuelve el repositorio del producto contra el espejo"; exit 2; }
echo "espejo OK: main = ${CANDIDATO}"

paso "3. imágenes base (sin descargar nada)"
for par in "postgres:15-alpine ${DIGEST_POSTGRES}" "python:3.11-slim-bookworm ${DIGEST_PYTHON}"; do
    set -- ${par}
    actual="$(docker image inspect "$1" --format '{{index .RepoDigests 0}}' 2>/dev/null | sed 's/.*@//')"
    [[ "${actual}" == "$2" ]] || { echo "la imagen $1 no es la esperada (${actual:-ausente} != $2): NO se descarga otra, se detiene"; exit 2; }
    echo "$1 = $2"
done

paso "4. construcción de la imagen del candidato (con red; llena la caché que usará la ejecución sin red)"
rm -rf /tmp/prebuild && git clone -q https://github.com/juanajok/zascarr.git /tmp/prebuild
[[ "$(git -C /tmp/prebuild rev-parse HEAD)" == "${CANDIDATO}" ]] || { echo "el clon no es el candidato"; exit 2; }
( cd /tmp/prebuild && docker build -q -t zascarr-prebuild:f1bis . ) | tee "${EV}/prebuild-imagen.txt"
docker run --rm --entrypoint pip zascarr-prebuild:f1bis freeze > "${EV}/pip-freeze.txt"
docker image ls --digests --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' > "${EV}/imagenes.txt"
rm -rf /tmp/prebuild
presupuesto

paso "5. biblioteca sintética, usuario ordinario y ausencia del producto"
python3 - <<'PY'
import os, struct, zipfile, zlib
def png(w, h, c):
    raw = b''.join(b'\x00' + bytes(c) * w for _ in range(h))
    def ch(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    return b'\x89PNG\r\n\x1a\n' + ch(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0)) + ch(b'IDAT', zlib.compress(raw)) + ch(b'IEND', b'')
for s, c in [("Serie Sintetica Alfa", (200, 40, 40)), ("Serie Sintetica Beta", (40, 160, 60)), ("Serie Sintetica Gamma", (50, 80, 200))]:
    d = f"/media/library/{s}"
    os.makedirs(d, exist_ok=True)
    for i in range(1, 4):
        p = f"{d}/{s} {i:03d}.cbz"
        if not os.path.exists(p):
            with zipfile.ZipFile(p, 'w') as z:
                for k in range(1, 4):
                    z.writestr(f"{k:02d}.png", png(8 + i, 8 + k, c))
os.makedirs("/media/data", exist_ok=True)
PY
[[ "$(find /media/library -type f | wc -l)" == "9" ]] || { echo "la biblioteca sintética no tiene 9 ficheros"; exit 2; }
[[ -z "$(find /media/library -mindepth 1 -type d ! -name 'Serie Sintetica *')" ]] || { echo "la biblioteca ya tiene carpetas del instalador"; exit 2; }
getent passwd "${OTRO}" >/dev/null || useradd --create-home --shell /bin/bash "${OTRO}"
! id -nG "${OTRO}" | grep -qw -e sudo -e adm -e docker || { echo "'${OTRO}' tiene privilegios"; exit 2; }
[[ ! -e /opt/zascarr && ! -e /var/lib/zascarr ]]
[[ "$(docker ps -aq | wc -l)" == "0" ]]
echo "OK"

paso "6. resumen"
presupuesto
date -Is | tee -a "${EV}/inicio.txt" >/dev/null
echo "PREPARACIÓN TERMINADA"
