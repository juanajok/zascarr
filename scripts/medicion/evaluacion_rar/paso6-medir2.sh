#!/usr/bin/env bash
# Paso 6 (2ª tanda, SIN RED): integridad real de la página, ficheros dañados, topes, cifrados y ComicInfo. Pide escribir SI.
# Prueba corta antes de la completa:  SOLO=m02 MODOS=integridad,corrupto bash paso6-medir2.sh
# Los daños se aplican a copias en el tmpfs del contenedor; las muestras van montadas en solo lectura y no se modifican.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
docker image inspect "$IMAGEN_EVAL" >/dev/null 2>&1 || parar "no existe la imagen $IMAGEN_EVAL (paso 2; si ya la retiraste con el paso 4, hay que volver a construirla: es el único paso con red)"
[ -d "$MUESTRAS" ] && [ -d "$SALIDA" ] || parar "faltan $MUESTRAS o $SALIDA: Docker las crearía vacías y como root"
{ echo "fecha: $(date -Is)"; echo "equipo: $(uname -a)"; free -m | sed -n 1,2p; echo "carga: $(uptime)"; docker version --format 'docker: {{.Server.Version}} {{.Server.Arch}}'; } | tee "$SALIDA/entorno2.txt"
echo "OJO: sin descargas ni importaciones en curso durante la medición."
read -r -p "¿Ejecutar AHORA (unos minutos)? Escribe SI: " R; [ "$R" = "SI" ] || parar "cancelado (no se ha medido nada)"
docker run --rm --name zascarr-eval-rar2 --network none --read-only \
  --memory=512m --memory-swap=512m --cpus=2 --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
  --tmpfs /work:rw,size=128m,mode=1777 --tmpfs /tmp:rw,size=16m \
  -v "$MUESTRAS":/m:ro -v "$KIT":/k:ro -v "$SALIDA":/out:rw --user "$(id -u):$(id -g)" \
  -e TIMEOUT="${TIMEOUT:-60}" -e MODOS="${MODOS:-integridad,corrupto,topes,cifrado,comicinfo}" -e SOLO="${SOLO:-}" \
  --entrypoint python "$IMAGEN_EVAL" /k/banco_rar2.py 2>&1 | tee "$SALIDA/banco2.log"
echo; ok "resultados en $SALIDA (resumen2.md, resultados2.jsonl, entorno2.txt, banco2.log)"
