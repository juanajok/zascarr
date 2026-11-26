# Suite pura del producto en el runner

Imagen fijada por digest (`python:3.11-slim-bookworm`) con `pytest==8.4.2`. El job
`producto-runner` de CI la construye, resuelve su ID y ejecuta `run.py`, que copia solo
`zascarr/core/carpetas.py` y `tests/test_core_carpetas.py` al snapshot, en solo lectura,
y deja escribir a pytest en `/scratch`.

Reproducir:

```bash
docker build -t agentic-product-tests:ci .agentic/evals/product
PYTHONPATH=.agentic python .agentic/evals/product/run.py
```

No es la suite completa: acredita el mecanismo del runner con una suite pura y acotada.
Las pruebas que necesitan PostgreSQL, red o el árbol completo siguen fuera.
