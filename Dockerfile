# =============================================================================
# ZascArr — Dockerfile (fix C1 del peer review)
# =============================================================================
# Cambio: uvicorn escucha en 0.0.0.0 dentro del contenedor.
#
# Antes (bug): --host 127.0.0.1 + bridge network SIN ports: publicado en el
# compose => la API quedaba 100% inalcanzable salvo desde dentro del propio
# contenedor (el HEALTHCHECK pasaba, dando falsa sensación de salud).
#
# Ahora: uvicorn en 0.0.0.0 + "127.0.0.1:8000:8000" en el compose. La
# decisión de seguridad ("no exponer a LAN") vive en el lado del host del
# mapeo de puertos, donde es verificable con `ss -tlnp`, no dentro del
# contenedor donde era ciega.
# =============================================================================

FROM python:3.11-slim-trixie AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim-trixie AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libxml2 libxslt1.1 tini unar \
    && rm -rf /var/lib/apt/lists/*
# `unar` (con `lsar`) lee la portada de los .cbr que son RAR (#418): solo en `runtime`, el
# `builder` no lo necesita. Se lanza a demanda por subproceso, así que no cambia el arranque.
# Base Debian trixie (#528): trae `unar`/`lsar` 1.10.8, que conoce `-json-skip-solid-information`.
# Es el flag que evita que un sólido grande repita ~29 KB por entrada y supere el tope de salida.
# `gnustep-base-runtime` es dependencia DURA de `unar` (`--no-install-recommends` no evita sus ejecutables):
# trae demonios de objetos distribuidos (`gdomap`, `gdnc`) y sus ficheros de servicio, y una veintena de
# herramientas (`defaults`, `pl*`, `xmlparse`, `cvtenc`…) que nadie usa aquí y que ampliarían la superficie
# de la imagen (ADR 0015, dictamen SecOps A-1 y C-3). Se borran TODOS los ejecutables y scripts de servicio
# del paquete, por su lista de ficheros y por nombre (trixie añade `gdomap-helper`, `gdomap.service` y
# `gdomap_probes`; `gpbs` no existe en trixie). `lsar`/`unar` solo necesitan las bibliotecas. El job de Docker
# de la CI lo comprueba dentro de la imagen y que los fixtures RAR se siguen leyendo.
RUN dpkg -L gnustep-base-runtime \
        | grep -E '^/(usr/bin|usr/sbin|etc/init\.d|etc/default)/[^/]+$' | xargs -r rm -f \
    && find /usr /etc /var/lib/systemd -type f \( -name 'gdomap*' -o -name gdnc -o -name gpbs -o -name 'gpbs*' \) -delete
# usermod/groupmod (paquete "passwd") y runuser (paquete "util-linux") ya
# vienen en python:3.11-slim-trixie — sin dependencia nueva.
# #530 C2: trixie arrastra por `gnustep-base-runtime` y sus dependencias herramientas de
# construcción (dpkg-dev, make, patch, binutils, perl) y utilidades que el runtime no usa
# (gnutls-bin, graphviz). Se borran sus ejecutables/scripts; las bibliotecas se conservan (son
# dependencias duras o las carga `unar`). DOS excepciones obligatorias:
#   · `dpkg-architecture`: GNUstep lo invoca EN RUNTIME para DEB_HOST_MULTIARCH; sin él
#     `lsar`/`unar` abortan (SIGABRT). No se borra.
#   · `perl-base` + `libdpkg-perl` + `perl-modules-5.40`: `dpkg-architecture` es un script Perl y
#     necesita el intérprete y sus módulos. Solo se limpian las utilidades del paquete `perl`, no
#     el intérprete. (Sin esta excepción, `lsar`/`unar` dejan de funcionar y la verificación de la
#     imagen lo detecta.)
# Verificado con `lsar`/`unar`, los fixtures y los hostiles en `scripts/comprobar_imagen_rar.py`;
# la CI tiene un presupuesto de 750 MiB.
RUN for paquete in gnutls-bin make patch binutils binutils-x86-64-linux-gnu graphviz perl; do \
        dpkg -L "$paquete" 2>/dev/null \
            | grep -E '^/(usr/bin|usr/sbin|etc/init\.d|etc/default|usr/libexec)/[^/]+$' \
            | xargs -r rm -f; \
    done \
    && dpkg -L dpkg-dev 2>/dev/null \
        | grep -E '^/(usr/bin|usr/sbin|etc/init\.d|etc/default|usr/libexec)/[^/]+$' \
        | grep -v '^/usr/bin/dpkg-architecture$' \
        | xargs -r rm -f

RUN groupadd -g 1000 zascarr && \
    useradd -u 1000 -g zascarr -m -s /bin/bash zascarr

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=zascarr:zascarr . .
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/api/health'); r.raise_for_status()"

# Se queda como root a propósito: /entrypoint.sh ajusta PUID/PGID y hace
# `runuser` a zascarr antes de ejecutar el CMD real — nunca corre la app
# como root. Ver docker-entrypoint.sh para el porqué (bug real de permisos
# entre el UID fijo del contenedor y el usuario de servicio del host).
ENTRYPOINT ["tini", "--", "/entrypoint.sh"]

# 0.0.0.0 ES INTENCIONAL: ver cabecera. La exposición real la decide el
# compose ("127.0.0.1:8000:8000" = solo loopback del host).
CMD ["python", "-m", "uvicorn", \
     "zascarr.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--ws", "none", \
     "--log-level", "info"]

EXPOSE 8000
