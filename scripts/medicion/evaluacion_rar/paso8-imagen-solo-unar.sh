#!/usr/bin/env bash
# Paso 8 (2ª tanda, CON RED: unos MB de paquetes de Debian): construye una imagen desechable con SOLO `unar` y compara tamaños con la imagen de ZascArr.
# No toca la imagen de producción ni la configuración de Docker. El paso 4 retira también esta imagen.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
IMAGEN_UNAR=${IMAGEN_UNAR:-zascarr-eval-unar:local}
docker image inspect "$IMAGEN_BASE" >/dev/null 2>&1 || parar "no existe la imagen base $IMAGEN_BASE"
mkdir -p "$SALIDA"; [ -w "$SALIDA" ] || parar "no puedo escribir en $SALIDA"
read -r -p "Este paso USA RED (descarga unar y sus dependencias de Debian). ¿Continuar? Escribe SI: " R; [ "$R" = "SI" ] || parar "cancelado"
docker build --build-arg BASE="$IMAGEN_BASE" -t "$IMAGEN_UNAR" -f "$KIT/Dockerfile.solo-unar" "$KIT" || parar "falló la construcción"
{
  echo "# tamaños (bytes) de docker image inspect"
  for i in "$IMAGEN_BASE" "$IMAGEN_UNAR" "$IMAGEN_EVAL"; do printf '%s\t%s\n' "$i" "$(docker image inspect --format '{{.Size}}' "$i" 2>/dev/null || echo 'no existe')"; done
  docker run --rm --network none --entrypoint cat "$IMAGEN_UNAR" /anadidos.txt
} | tee "$SALIDA/solo-unar.txt"
ok "anotado en $SALIDA/solo-unar.txt"
