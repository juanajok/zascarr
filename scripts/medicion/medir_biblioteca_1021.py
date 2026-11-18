"""Mide p50/p95 de /ui/biblioteca con sesión real (preparado para #1021).

No guarda credenciales: la contraseña se lee de la variable de entorno
`ZASCARR_TEST_PASSWORD` (o de `--password-env`). Uso en la Pi:

    ZASCARR_TEST_PASSWORD='...' python scripts/medicion/medir_biblioteca_1021.py \
        --base-url http://127.0.0.1:8000 --runs 30

Solo hace GET; no escribe en la aplicación.
"""
from __future__ import annotations

import argparse
import os
import statistics
import time

import httpx

RUTAS = (
    "/ui/biblioteca",
    "/ui/biblioteca?modo=escaparate",
    "/ui/biblioteca?densidad=compacta",
)


def _p95(valores: list[float]) -> float:
    ordenados = sorted(valores)
    return ordenados[max(0, int(len(ordenados) * 0.95) - 1)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--password-env", default="ZASCARR_TEST_PASSWORD")
    ap.add_argument("--usuario", default="")
    args = ap.parse_args()
    password = os.environ.get(args.password_env, "")
    if not password:
        raise SystemExit(f"Falta {args.password_env} (no se imprime).")
    if args.runs < 1:
        raise SystemExit("--runs debe ser >= 1")
    with httpx.Client(base_url=args.base_url, follow_redirects=False, timeout=30) as c:
        r = c.post("/login", data={"password": password, "username": args.usuario,
                                   "next": "/ui/biblioteca"})
        if r.status_code not in (302, 303):
            raise SystemExit(f"Login falló: HTTP {r.status_code}")
        for ruta in RUTAS:
            tiempos, estados = [], []
            for _ in range(args.runs):
                t0 = time.perf_counter()
                resp = c.get(ruta)
                tiempos.append((time.perf_counter() - t0) * 1000)
                estados.append(resp.status_code)
            if any(e >= 500 for e in estados):
                raise SystemExit(f"{ruta}: hubo 5xx")
            print(f"{ruta}: n={args.runs} p50={statistics.median(tiempos):.1f} ms "
                  f"p95={_p95(tiempos):.1f} ms max={max(tiempos):.1f} ms "
                  f"status={sorted(set(estados))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
