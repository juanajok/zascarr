#!/usr/bin/env bash
# Paso 0 (SOLO LECTURA): qué formato tienen los candidatos. Lee solo la cabecera de cada fichero con `file`. No copia ni escribe nada salvo $SALIDA/clasificacion.tsv.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
mkdir -p "$SALIDA"; cd "$BIBLIOTECA" || parar "no existe $BIBLIOTECA"
[ -z "$PUNTO" ] || findmnt "$PUNTO" >/dev/null || parar "el disco de la biblioteca no está montado"
OUT=$SALIDA/clasificacion.tsv; : > "$OUT"
{
  echo "# 21 .rar de One Piece y el .tar de Paracuellos"
  find . -type f \( -iname '*.rar' -o -iname '*.tar' \) -printf '%P\n'
  echo "# los 12 sin extensión del censo"
  awk -F'\t' '$2=="sin_extension"{print $1}' /tmp/sin-registrar.tsv 2>/dev/null
} > "$SALIDA/candidatos.txt"
N=0
while IFS= read -r f; do
  case "$f" in "#"*|"") continue;; esac
  [ -f "$f" ] || continue
  printf '%s\t%s\t%s\n' "$(stat -c %s -- "$f")" "$(file -b -- "$f" | cut -c1-48)" "$f" >> "$OUT"; N=$((N+1))
done < "$SALIDA/candidatos.txt"
# unos .cbr típicos ya registrados: 1 de cada 120 con tamaño entre 30 y 150 MB (determinista)
find . -type f -iname '*.cbr' -size +30M -size -150M -printf '%P\n' | LC_ALL=C sort | awk 'NR%120==1' | head -6 | while IFS= read -r f; do
  printf '%s\t%s\t%s\n' "$(stat -c %s -- "$f")" "$(file -b -- "$f" | cut -c1-48)" "$f" >> "$OUT"; done
ok "clasificados $(wc -l < "$OUT") ficheros → $OUT"
echo; echo "Resumen por tipo (columna 2):"; cut -f2 "$OUT" | sed 's/, *os:.*//' | sort | uniq -c | sort -rn
echo; echo "Pásame esta salida y el contenido de $OUT (son nombres de ficheros tuyos y sus formatos; nada más)."
