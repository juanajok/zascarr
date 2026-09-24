#!/bin/sh
# =============================================================================
# docker-entrypoint.sh — ajusta el UID/GID del contenedor antes de arrancar.
#
# Bug real (reportado): el contenedor corre fijo como UID 1000 desde el
# Dockerfile, pero el usuario de servicio del host (ZASCARR_USER, por
# defecto "media") es un usuario de SISTEMA creado con `useradd --system`
# — Debian le asigna el UID que tenga libre en su rango de sistema, casi
# nunca 1000. El importador podía COPIAR los archivos del usuario (lectura
# via "otros"), pero no BORRAR el original tras importarlo: borrar exige
# permiso de escritura en el directorio, que "otros" no tiene sobre una
# carpeta `rwxrwsr-x` propiedad de `media:media`.
#
# Mismo patrón que usa toda imagen *arr de LinuxServer.io: PUID/PGID
# ajustan el usuario interno del contenedor en el arranque para que
# coincida con el usuario real del host que ya es dueño de los discos.
# bootstrap.sh resuelve PUID/PGID automáticamente a partir de
# ZASCARR_USER/ZASCARR_GROUP — no hace falta que el coleccionista sepa
# qué es un UID.
# =============================================================================
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u zascarr)" != "${PUID}" ] || [ "$(id -g zascarr)" != "${PGID}" ]; then
    groupmod -o -g "${PGID}" zascarr
    usermod -o -u "${PUID}" zascarr
    # Solo lo que es del propio contenedor (código y caché de portadas), no
    # los discos del usuario (biblioteca/descargas) — esos los controla el
    # propietario real del host, igual que H5 en bootstrap.sh.
    chown -R zascarr:zascarr /app /config/covers 2>/dev/null || true
fi

exec runuser -u zascarr -- "$@"
