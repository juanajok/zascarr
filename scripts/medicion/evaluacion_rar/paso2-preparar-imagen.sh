#!/usr/bin/env bash
# Paso 2 (CON RED, autorizado por el PO para un contenedor desechable): construye la imagen de evaluación y anota qué se instaló.
# Descarga unos pocos MB de paquetes de Debian y de PyPI (rarfile). NO toca la imagen de producción ni la configuración de Docker.
set -uo pipefail
source "$(dirname "$0")/comun.sh"
docker image inspect "$IMAGEN_BASE" >/dev/null 2>&1 || parar "no existe la imagen base $IMAGEN_BASE (docker images)"
mkdir -p "$SALIDA"
echo "Arquitectura del host: $(uname -m)"
docker build --build-arg BASE="$IMAGEN_BASE" --build-arg CON_UNRAR="${CON_UNRAR:-1}" -t "$IMAGEN_EVAL" -f "$KIT/Dockerfile.eval" "$KIT" || parar "falló la construcción"
docker run --rm --network none --entrypoint cat "$IMAGEN_EVAL" /herramientas.txt | tee "$SALIDA/herramientas.txt"
ok "imagen $IMAGEN_EVAL lista; herramientas anotadas en $SALIDA/herramientas.txt"
