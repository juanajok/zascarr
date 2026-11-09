#!/usr/bin/env bash
# Prototipo de conversión con memoria baja: un contenedor desechable por copia.
# Mismo presupuesto que medir_muestras.sh; usa convertir_streaming.py (unar -o - por índice).
set -uo pipefail
BASE=${BASE:-$HOME/eval-cnv}
IMAGEN=${IMAGEN:-zascarr-zascarr:latest}
ENTRADA=${ENTRADA:-$BASE/salida/muestras.tsv}
SALIDA=${SALIDA:-$BASE/salida/medicion-streaming.jsonl}
mkdir -p "$BASE/salida"
: > "$SALIDA"
while IFS=$'\t' read -r sid rel sha size tipo motivo; do
  printf '%s\t%s\n' "$sid" "$motivo" >&2
  out=$(timeout 1200 docker run --rm --network none --read-only \
      --memory=512m --memory-swap=512m --tmpfs /tmp:rw,size=64m \
      -v "$BASE/muestras:/samples:ro" -v "$BASE:/kit:ro" \
      -v "$BASE/trabajo:/trabajo:rw" \
      --entrypoint python3 "$IMAGEN" /kit/convertir_streaming.py "$sid" 2>"$BASE/salida/$sid.streaming.err")
  rc=$?
  if [ "$rc" -ne 0 ] || [ -z "$out" ]; then
      printf '{"id":"%s","error":"contenedor rc=%s","tipo":"streaming"}\n' "$sid" "$rc" >> "$SALIDA"
  else
      printf '%s\n' "$out" >> "$SALIDA"
  fi
done < "$ENTRADA"
echo "fin: $(wc -l < "$SALIDA") líneas" >&2
