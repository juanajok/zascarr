#!/usr/bin/env bash
# Paso 7 (2ª tanda, SIN RED): lectura EN FRÍO. Antes de cada muestra vacía la caché de disco (pide sudo; solo escribe en /proc/sys/vm/drop_caches) y mide
# listar/primera/última con unar y unrar, 1 repetición. Las copias están en el disco del sistema, no en el USB de la biblioteca (que no se toca).
# Sin descargas ni importaciones en curso. Prueba corta:  SOLO_IDS="m02 m08" bash paso7-frio.sh
set -uo pipefail
source "$(dirname "$0")/comun.sh"
docker image inspect "$IMAGEN_EVAL" >/dev/null 2>&1 || parar "no existe la imagen $IMAGEN_EVAL"
[ -d "$MUESTRAS" ] && [ -d "$SALIDA" ] || parar "faltan $MUESTRAS o $SALIDA"
echo "carga: $(uptime)"; sudo -v || parar "hace falta sudo para vaciar la caché de disco"
read -r -p "¿Medir en frío AHORA (varios minutos)? Escribe SI: " R; [ "$R" = "SI" ] || parar "cancelado"
IDS=${SOLO_IDS:-$(cd "$MUESTRAS" && ls | grep -E '^[ms][0-9]{2}$')}
for id in $IDS; do
  D=$SALIDA/frio/$id; mkdir -p "$D"
  sync; echo 3 | sudo tee /proc/sys/vm/drop_caches >/dev/null || parar "no pude vaciar la caché"
  docker run --rm --network none --read-only --memory=512m --memory-swap=512m --cpus=2 --pids-limit 128 --cap-drop ALL --security-opt no-new-privileges \
    --tmpfs /work:rw,size=128m,mode=1777 --tmpfs /tmp:rw,size=16m -v "$MUESTRAS":/m:ro -v "$KIT":/k:ro -v "$D":/out:rw --user "$(id -u):$(id -g)" \
    -e REPS=1 -e TIMEOUT=60 -e MOTORES=unar,unrar -e SOLO="$id" --entrypoint python "$IMAGEN_EVAL" /k/banco_rar.py > "$D/banco.log" 2>&1 || parar "falló la medición de $id (ver $D/banco.log)"
  echo "✓ $id en frío"
done
python3 - "$SALIDA" <<'PY' | tee "$SALIDA/frio.md"
import json, pathlib, sys
print("| muestra | motor | operación | estado | segundos (1ª lectura, caché vacía) | pico MiB |\n|---|---|---|---|---|---|")
for p in sorted(pathlib.Path(sys.argv[1], "frio").glob("*/resultados.jsonl")):
    for l in p.read_text().splitlines():
        r = json.loads(l)
        if r["motor"] in ("unar", "unrar") and r["op"] in ("listar", "primera", "ultima") and not r["estado"].startswith("NOT RUN"):
            print(f"| {r['muestra']} | {r['motor']} | {r['op']} | {r['estado']} | {r.get('seg_primera')} | {r.get('pico_mib_max')} |")
PY
ok "tabla en $SALIDA/frio.md"
