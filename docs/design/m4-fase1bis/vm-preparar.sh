#!/usr/bin/env bash
# =============================================================================
# vm-preparar.sh — M4 · Fase 1 bis (#121). Se ejecuta DENTRO de la VM, como root. Única fase con salida: SOLO por el proxy con presupuesto del anfitrión.
#
#     sudo env PROXY=http://10.0.2.100:3128 CANDIDATO=<sha> DIGEST_POSTGRES=sha256:… DIGEST_PYTHON=sha256:… bash vm-preparar.sh
#
# Qué hace (y nada más):
#   1. Comprueba que el punto de partida está limpio (sin instalación del producto).
#   2. Pone el espejo local de Git con main = candidato (desde /tmp/candidato.bundle) y comprueba su configuración.
#   3. Comprueba que las dos imágenes base siguen siendo las de la fase 1 (por digest). NO descarga imágenes.
#   4. Comprueba el proxy con presupuesto del anfitrión (única salida de la VM) y construye UNA vez la imagen del candidato desde el espejo
#      (descarga paquetes de Debian y de PyPI POR el proxy): deja las capas en
#      caché para que el bootstrap.sh de la ejecución, SIN red, pueda construir. Eso NO acredita una construcción en frío.
#   5. Verifica la biblioteca sintética, el usuario ordinario sin privilegios y que no hay ni rastro del producto.
#   6. Informa de lo descargado (bytes recibidos por la VM) y aborta si supera el presupuesto.
# =============================================================================
set -euo pipefail
# shellcheck source=docs/design/m4-fase1bis/lib-ensayo.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib-ensayo.sh"
CANDIDATO="${CANDIDATO:?falta CANDIDATO}"
DIGEST_POSTGRES="${DIGEST_POSTGRES:?falta DIGEST_POSTGRES}"
DIGEST_PYTHON="${DIGEST_PYTHON:?falta DIGEST_PYTHON}"
LIMITE_MIB="${DESCARGA_MAX_MIB:-600}"
MARGEN_MIB="${MARGEN_MIB:-100}"
EV="${EV:-/root/ensayo/preparacion}"
OTRO="${OTRO:-otroprueba}"
mkdir -p "${EV}"
# Unidad: MiB (1 MiB = 1.048.576 bytes). El tope se HACE CUMPLIR mientras se descarga (`con_limite_de_descarga`: corta a
# tope − margen); `presupuesto` solo informa y comprueba el total al final.
IFACE="$(ls /sys/class/net | grep -v -e '^lo$' -e '^docker' -e '^br-' -e '^veth' | head -n 1)"
export IFACE
RX_BASE_BYTES="$(contador_rx_bytes)"
export RX_BASE_BYTES
presupuesto() {
    local mib=$(( ($(contador_rx_bytes) - RX_BASE_BYTES) / 1048576 ))
    echo "descargado hasta ahora: ${mib} MiB (tope ${LIMITE_MIB} MiB, corte a $((LIMITE_MIB - MARGEN_MIB)) MiB)" | tee -a "${EV}/descarga.txt"
    (( mib <= LIMITE_MIB )) || { echo "PRESUPUESTO DE DESCARGA SUPERADO (${mib} MiB > ${LIMITE_MIB} MiB): se detiene"; exit 4; }
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
# La VM NO tiene red directa: su única salida es el proxy con presupuesto del anfitrión (PROXY). Se comprueba ANTES de construir nada:
#   · sin proxy no hay salida (control negativo);  · con proxy se llega a Debian;  · con proxy NO se llega a un destino fuera de la lista.
# Si algo falla, se aborta SIN haber descargado nada de importancia (unos KB de cabeceras).
PROXY="${PROXY:?falta PROXY (http://10.0.2.100:3128)}"
if curl -sS -m 8 -o /dev/null https://deb.debian.org 2>/dev/null; then echo "HAY salida directa a Internet sin pasar por el proxy: no es lo previsto, se detiene"; exit 4; fi
[[ "$(curl -sS -m 40 -o /dev/null -w '%{http_code}' -x "${PROXY}" -I http://deb.debian.org/debian/dists/bookworm/Release 2>/dev/null)" == "200" ]] \
    || { echo "el proxy con presupuesto no deja llegar a deb.debian.org: se detiene (nada descargado)"; exit 4; }
[[ "$(curl -sS -m 20 -o /dev/null -w '%{http_code}' -x "${PROXY}" -I https://example.com 2>/dev/null)" =~ ^(403|000)$ ]] \
    || { echo "el proxy deja llegar a un destino FUERA de la lista: se detiene"; exit 4; }
echo "proxy comprobado: control negativo (sin proxy no hay salida), Debian alcanzable y un destino fuera de la lista rechazado"
# El cliente de Docker reenvía estos valores como argumentos de construcción predefinidos (HTTP_PROXY/HTTPS_PROXY): `apt` y `pip` de
# los pasos RUN salen por el proxy, que además resuelve los nombres (no hace falta DNS en la VM).
install -d -m 0700 /root/.docker
cat > /root/.docker/config.json <<JSON
{"proxies": {"default": {"httpProxy": "${PROXY}", "httpsProxy": "${PROXY}", "noProxy": "localhost,127.0.0.1"}}}
JSON
# Segunda defensa, dentro del invitado: al umbral corta la red del invitado y termina el grupo de procesos entero.
cortar_red() { cortar_red_nft "${IFACE}"; }
# Construcción, bajo la vigilancia del invitado (el presupuesto autorizado lo hace cumplir el proxy del anfitrión): si la descarga llega al umbral de corte, se mata el grupo de procesos entero.
( cd /tmp/prebuild && con_limite_de_descarga "${LIMITE_MIB}" "${MARGEN_MIB}" -- docker build -q -t zascarr-prebuild:f1bis . ) | tee "${EV}/prebuild-imagen.txt"
presupuesto
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
