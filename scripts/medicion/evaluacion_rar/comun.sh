# Común a los pasos de la evaluación del lector RAR/CBR (protocolo: docs/design/protocolo-evaluacion-lector-rar.md). Se carga con `source`.
# La biblioteca NUNCA se monta en un contenedor: solo se LEE con `cp` (paso 1) y `file`/`stat` (paso 0).
BIBLIOTECA=${BIBLIOTECA:-/media/WDElements/Tebeos}
PUNTO=${PUNTO-/media/WDElements}                      # punto de montaje del disco de la biblioteca (vacío = no se comprueba)
BASE=${BASE:-$HOME/eval-rar}                       # todo lo que genera la evaluación vive aquí (fuera de la biblioteca)
MUESTRAS=$BASE/muestras
SALIDA=$BASE/salida
IMAGEN_BASE=${IMAGEN_BASE:-zascarr-zascarr:latest}   # la imagen de ZascArr que ya hay en la Pi (misma base python:3.11-slim-bookworm)
IMAGEN_EVAL=${IMAGEN_EVAL:-zascarr-eval-rar:local}
KIT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ok()    { echo "✓ $*"; }
parar() { echo; echo "✗ PARAR: $*"; exit 1; }
