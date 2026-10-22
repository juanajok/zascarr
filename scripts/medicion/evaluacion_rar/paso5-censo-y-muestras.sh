#!/usr/bin/env bash
# Paso 5 (2ª tanda). Dos partes, la 2ª con confirmación:
#  A) SOLO LECTURA: lee los primeros 4 KiB de cada .cbr/.rar/sin-extensión de la biblioteca y dice cuántos son RAR4/RAR5, sólidos o cifrados (python3 de la Pi, sin instalar nada).
#  B) Propone muestras por REGLA (2 sólidos, hasta 2 cifrados, 24 .cbr típicos), te las enseña y, si escribes SI, las COPIA (cp) como s01, s02… con el hash comprobado.
# La biblioteca no se monta en ningún contenedor ni se escribe en ella.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
command -v python3 >/dev/null || parar "no hay python3 en la Pi"
cd "$BIBLIOTECA" 2>/dev/null || parar "no existe $BIBLIOTECA"
[ -z "$PUNTO" ] || findmnt "$PUNTO" >/dev/null || parar "el disco de la biblioteca no está montado"
mkdir -p "$MUESTRAS" "$SALIDA" 2>/dev/null; [ -w "$MUESTRAS" ] && [ -w "$SALIDA" ] || parar "no puedo escribir en $BASE (¿es de root? Si está vacía: sudo rmdir $BASE; no uses rm -rf)"
echo "Leyendo cabeceras (solo lectura; puede tardar un par de minutos en el disco USB)…"
python3 "$KIT/censo_cabeceras_rar.py" "$BIBLIOTECA" --tsv "$SALIDA/censo-cabeceras.tsv" --elegir "${TIPICOS:-24}" > "$SALIDA/muestras2.txt" || parar "falló el censo de cabeceras"
echo; echo "== Muestras propuestas (regla fija; ver $SALIDA/muestras2.txt) =="; cat "$SALIDA/muestras2.txt"
TOTAL=0; while IFS= read -r f; do case "$f" in "#"*|"") continue;; esac; [ -f "$f" ] && TOTAL=$((TOTAL + $(stat -c %s -- "$f"))); done < "$SALIDA/muestras2.txt"
LIBRE=$(df -B1 --output=avail "$BASE" | tail -1)
echo; echo "Ocupan $((TOTAL/1048576)) MiB; hay $((LIBRE/1048576)) MiB libres en $BASE"
[ "$LIBRE" -gt $((TOTAL*2)) ] || parar "poco espacio libre: hace falta al menos el doble"
read -r -p "¿Copiar esas muestras (cp, solo lectura sobre el original)? Escribe SI: " R; [ "$R" = "SI" ] || { echo "No se ha copiado nada. El censo queda en $SALIDA/censo-cabeceras.tsv"; exit 0; }
H=$SALIDA/muestras2.sha256; : > "$H"; I=0
while IFS= read -r f; do
  case "$f" in "#"*|"") continue;; esac
  [ -f "$f" ] || { echo "! no existe: $f"; continue; }
  I=$((I+1)); DST="$MUESTRAS/s$(printf '%02d' $I)"
  cp --no-preserve=ownership -- "$f" "$DST" || parar "falló la copia de $f"
  H1=$(sha256sum -- "$f" | cut -d' ' -f1); H2=$(sha256sum -- "$DST" | cut -d' ' -f1)
  [ "$H1" = "$H2" ] && ok "s$(printf '%02d' $I) ← $f  ($(stat -c %s -- "$DST") bytes, sha256 igual)" || parar "la copia de $f NO coincide con el original"
  printf '%s\t%s\ts%02d\n' "$H1" "$f" "$I" >> "$H"
done < "$SALIDA/muestras2.txt"
[ "$I" -gt 0 ] || parar "0 muestras copiadas"
chmod a-w "$MUESTRAS"/s[0-9][0-9] 2>/dev/null
ok "$I muestras copiadas en $MUESTRAS. Equivalencia de nombres: $H"
echo "Pásame: $SALIDA/censo-cabeceras.tsv (resumen), $SALIDA/muestras2.txt y la salida de este paso."
