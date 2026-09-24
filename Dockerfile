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

FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml .
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libxml2 libxslt1.1 tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 zascarr && \
    useradd -u 1000 -g zascarr -m -s /bin/bash zascarr

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=zascarr:zascarr . .

USER zascarr

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/api/health'); r.raise_for_status()"

ENTRYPOINT ["tini", "--"]

# 0.0.0.0 ES INTENCIONAL: ver cabecera. La exposición real la decide el
# compose ("127.0.0.1:8000:8000" = solo loopback del host).
CMD ["python", "-m", "uvicorn", \
     "zascarr.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info"]

EXPOSE 8000
