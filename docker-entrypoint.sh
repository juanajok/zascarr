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

# Bug real de producción, confirmado con datos reales (2026-09-25): el
# valor mágico "host-gateway" de extra_hosts (docker-compose.yml) puede
# resolver a la puerta de enlace del puente POR DEFECTO (docker0,
# 172.17.0.1 en el caso real) en vez de a la de la red PERSONALIZADA que
# de verdad usa este contenedor (docker-compose siempre crea una propia,
# p.ej. zascarr_zascarr-internal, gateway 172.18.0.1 en ese mismo caso) —
# host.docker.internal apuntaba a una red que este contenedor ni
# siquiera usa, así que Prowlarr/Transmission/aMule (baremetal en el
# host) eran inalcanzables aunque el firewall y el servicio estuvieran
# bien configurados. Se corrige aquí con la puerta de enlace REAL de la
# propia interfaz del contenedor (vía /proc/net/route, sin depender de
# `ip`/iproute2 — no es una dependencia del Dockerfile; python3 sí lo es
# siempre, es la propia app).
GATEWAY_REAL="$(python3 -c "
import struct, socket
with open('/proc/net/route') as f:
    for line in f.readlines()[1:]:
        campos = line.split()
        if campos[1] == '00000000':
            print(socket.inet_ntoa(struct.pack('<L', int(campos[2], 16))))
            break
" 2>/dev/null || true)"
if [ -n "${GATEWAY_REAL}" ]; then
    # /etc/hosts es un bind-mount especial de Docker: "sed -i" falla con
    # "Device or resource busy" porque reemplaza por renombrado, y no se
    # puede renombrar ENCIMA de un bind-mount (bug real, encontrado en la
    # propia verificación de este fix). Truncar-y-escribir sí funciona.
    grep -v '[[:space:]]host\.docker\.internal$' /etc/hosts > /tmp/hosts.nuevo 2>/dev/null || true
    echo "${GATEWAY_REAL}	host.docker.internal" >> /tmp/hosts.nuevo
    cat /tmp/hosts.nuevo > /etc/hosts
    rm -f /tmp/hosts.nuevo
fi

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
