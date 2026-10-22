#!/usr/bin/env bash
# Paso 4: retira las imágenes de evaluación y, si lo pides, las copias de las muestras (solo las que creó esta evaluación: m01, s01…). NO toca la biblioteca.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
for i in "$IMAGEN_EVAL" "${IMAGEN_UNAR:-zascarr-eval-unar:local}"; do docker image rm "$i" 2>/dev/null && ok "imagen $i retirada" || echo "(no había imagen $i)"; done
if [ "${BORRAR_MUESTRAS:-no}" = "si" ]; then
  find "$MUESTRAS" -maxdepth 1 -type f -regex '.*/[ms][0-9][0-9]' -delete && rmdir "$MUESTRAS" 2>/dev/null && ok "copias de las muestras borradas ($MUESTRAS)" || echo "Quedan ficheros en $MUESTRAS que no son copias de esta evaluación: no se tocan."
else echo "Las copias en $MUESTRAS se conservan. Para borrarlas: BORRAR_MUESTRAS=si bash paso4-limpiar.sh"; fi
echo "Los resultados en $SALIDA se conservan."
