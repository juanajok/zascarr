FROM python:3.11-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-slim-bookworm AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libxml2 libxslt1.1 tini \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g 1000 secuenciarr && \
    useradd -u 1000 -g secuenciarr -m -s /bin/bash secuenciarr

COPY --from=builder /install /usr/local

WORKDIR /app
COPY --chown=secuenciarr:secuenciarr . .

USER secuenciarr

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/api/health'); r.raise_for_status()"

ENTRYPOINT ["tini", "--"]

# Uvicorn en 127.0.0.1 (network_mode: host — no exponer a LAN sin proxy)
CMD ["python", "-m", "uvicorn", \
     "secuenciarr.main:app", \
     "--host", "127.0.0.1", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--log-level", "info"]

EXPOSE 8000
