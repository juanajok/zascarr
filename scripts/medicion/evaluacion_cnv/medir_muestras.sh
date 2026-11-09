#!/usr/bin/env bash
# Mide la conversión de las copias de la muestra en contenedores desechables (BL-CNV0).
# - sin red, root read-only, 512 MiB sin swap; /tmp tmpfs 64 MiB para lsar y /trabajo en disco;
# - solo se monta la carpeta de COPIAS (nunca la biblioteca);
# - una muestra por contenedor para que el pico de memoria sea por fichero.
set -uo pipefail
BASE=${BASE:-$HOME/eval-cnv}
IMAGEN=${IMAGEN:-zascarr-eval-rar:local}
ENTRADA=${ENTRADA:-$BASE/salida/muestras.tsv}
SALIDA=${SALIDA:-$BASE/salida/medicion.jsonl}
mkdir -p "$BASE/salida"
: > "$SALIDA"
while IFS=$'\t' read -r sid rel sha size tipo motivo; do
  printf '%s\t%s\t%s\n' "$sid" "$tipo" "$motivo" >&2
  out=$(timeout 900 docker run --rm --network none --read-only \
      --memory=512m --memory-swap=512m --tmpfs /tmp:rw,size=64m \
      -v "$BASE/muestras:/samples:ro" -v "$BASE:/kit:ro" \
      -v "$BASE/trabajo:/trabajo:rw" \
      --entrypoint python3 "$IMAGEN" /kit/convertir_uno.py "$sid" "$tipo" 2>"$BASE/salida/$sid.err")
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$out" ]; then
      printf '{"id":"%s","error":"contenedor rc=%s","tipo":"%s"}\n' "$sid" "$rc" "$tipo" >> "$SALIDA"
  else
      printf '%s\n' "$out" >> "$SALIDA"
  fi
done < "$ENTRADA"
echo "fin: $(wc -l < "$SALIDA") líneas en $SALIDA" >&2
