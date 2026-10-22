#!/usr/bin/env bash
# Paso 1: COPIA (cp, solo lectura sobre el original) las muestras elegidas a $MUESTRAS y verifica el hash de cada copia.
# La lista sale de $KIT/muestras.txt (una ruta relativa a la biblioteca por línea; `#` = comentario). Nada se escribe en la biblioteca.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
LISTA=${1:-$KIT/muestras.txt}
[ -f "$LISTA" ] || parar "no hay lista de muestras ($LISTA). La prepara Claude tras el paso 0."
mkdir -p "$MUESTRAS" "$SALIDA" 2>/dev/null; [ -w "$MUESTRAS" ] && [ -w "$SALIDA" ] || parar "no puedo escribir en $BASE (¿es de root? Si está vacía: sudo rmdir $BASE; no uses rm -rf)"
cd "$BIBLIOTECA" || parar "no existe $BIBLIOTECA"
[ -z "$PUNTO" ] || findmnt "$PUNTO" >/dev/null || parar "disco de la biblioteca no montado"
# directiva «@CBR n»: añade n .cbr típicos (entre 30 y 150 MB), 1 de cada 120 en orden alfabético: regla fija, no se eligen a mano
LISTA_EFECTIVA=$SALIDA/muestras-efectivas.txt; : > "$LISTA_EFECTIVA"
while IFS= read -r l; do
  case "$l" in
    "@CBR "*) N=${l#@CBR }; ( cd "$BIBLIOTECA" && find . -type f -iname '*.cbr' -size +30M -size -150M -printf '%P\n' | LC_ALL=C sort | awk 'NR%120==1' | head -n "$N" ) >> "$LISTA_EFECTIVA";;
    *) echo "$l" >> "$LISTA_EFECTIVA";;
  esac
done < "$LISTA"
LISTA=$LISTA_EFECTIVA
TOTAL=0; while IFS= read -r f; do case "$f" in "#"*|"") continue;; esac; [ -f "$f" ] && TOTAL=$((TOTAL + $(stat -c %s -- "$f"))); done < "$LISTA"
LIBRE=$(df -B1 --output=avail "$BASE" 2>/dev/null | tail -1 || df -B1 --output=avail "$HOME" | tail -1)
echo "Las muestras ocupan $((TOTAL/1048576)) MiB; hay $((LIBRE/1048576)) MiB libres en $BASE"
[ "$LIBRE" -gt $((TOTAL*2)) ] || parar "poco espacio libre: se necesita al menos el doble de lo que ocupan las muestras"
: > "$SALIDA/muestras.sha256"; I=0
while IFS= read -r f; do
  case "$f" in "#"*|"") continue;; esac
  [ -f "$f" ] || { echo "! no existe: $f"; continue; }
  I=$((I+1)); DST="$MUESTRAS/m$(printf '%02d' $I)"       # nombre neutro: no se copia el nombre real ni la extensión
  cp --no-preserve=ownership -- "$f" "$DST" || parar "falló la copia de $f"
  H1=$(sha256sum -- "$f" | cut -d' ' -f1); H2=$(sha256sum -- "$DST" | cut -d' ' -f1)
  [ "$H1" = "$H2" ] && ok "m$(printf '%02d' $I) ← $f  ($(stat -c %s -- "$DST") bytes, sha256 igual)" || parar "la copia de $f NO coincide con el original"
  printf '%s\t%s\tm%02d\n' "$H1" "$f" "$I" >> "$SALIDA/muestras.sha256"
done < "$LISTA"
[ "$I" -gt 0 ] || parar "0 muestras copiadas: algo ha fallado (revisa los mensajes de arriba)"
chmod -R a-w "$MUESTRAS"/* 2>/dev/null
ok "$I muestras copiadas en $MUESTRAS (solo lectura). Equivalencia de nombres: $SALIDA/muestras.sha256"
