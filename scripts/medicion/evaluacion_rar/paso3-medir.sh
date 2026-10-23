#!/usr/bin/env bash
# Paso 3 (SIN RED): ejecuta el banco dentro del contenedor desechable, con los límites del protocolo (§5): 512 MiB sin swap, red desconectada,
# sistema de ficheros de solo lectura, muestras :ro, un tmpfs acotado de trabajo y nada de la biblioteca montado.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
docker image inspect "$IMAGEN_EVAL" >/dev/null 2>&1 || parar "falta la imagen $IMAGEN_EVAL: ejecuta antes paso2-preparar-imagen.sh"
[ -d "$MUESTRAS" ] && [ -n "$(ls -A "$MUESTRAS" 2>/dev/null)" ] || parar "no hay muestras en $MUESTRAS: ejecuta antes paso1-copiar-muestras.sh"
[ "$(docker info --format '{{.MemoryLimit}}' 2>/dev/null)" = "true" ] || parar "Docker no soporta límite de memoria en este sistema: sin él la prueba de 512 MiB no vale"
mkdir -p "$SALIDA"
{ echo "fecha: $(date -Is)"; echo "equipo: $(uname -a)"; echo "cpus: $(nproc)"; free -m | sed -n 1,2p; echo "carga: $(uptime)"; docker version --format 'docker: {{.Server.Version}} {{.Server.Arch}}'; } | tee "$SALIDA/entorno.txt"
echo "OJO: no debe haber descargas ni importaciones en curso durante la medición (la carga de arriba lo anota)."
if [ "${DROP_CACHES:-0}" = "1" ]; then sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null && echo "caché de disco vaciada (DROP_CACHES=1)"; fi
read -r -p "¿Ejecutar la medición AHORA (puede tardar entre 15 y 40 min)? Escribe SI: " R; [ "$R" = "SI" ] || parar "cancelado (no se ha medido nada)"
[ -d "$MUESTRAS" ] && [ -d "$SALIDA" ] || parar "faltan $MUESTRAS o $SALIDA: Docker las crearía vacías y como root"
docker run --rm --name zascarr-eval-rar --network none --read-only \
  --memory=512m --memory-swap=512m --cpus=2 --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /work:rw,size=128m,mode=1777 --tmpfs /tmp:rw,size=16m \
  -v "$MUESTRAS":/m:ro -v "$KIT":/k:ro -v "$SALIDA":/out:rw --user "$(id -u):$(id -g)" \
  -e REPS="${REPS:-3}" -e TIMEOUT="${TIMEOUT:-60}" -e MOTORES="${MOTORES:-}" -e SOLO="${SOLO:-}" \
  --entrypoint python "$IMAGEN_EVAL" /k/banco_rar.py 2>&1 | tee "$SALIDA/banco.log"
echo; ok "resultados en $SALIDA (resumen.md, resultados.jsonl, entorno.txt, herramientas.txt, banco.log)"
