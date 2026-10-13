# ruff: noqa: E501
"""Un PROCESO de ZascArr que confirma una vinculación y, si se le pide, muere o se retiene en un punto exacto.

Solo para las pruebas de #117 (`tests/test_vinculacion_recuperacion_pg.py`): la historia pide «reiniciar el
proceso», y un motor nuevo dentro del mismo proceso no lo es (no hay muerte, ni sockets que se corten, ni
transacciones abiertas que Postgres deba abortar). Aquí el proceso es de verdad: `SIGKILL`, sin `finally`,
sin `rollback` de la aplicación, sin respuesta HTTP.

Contrato (variables de entorno → protocolo de líneas por la salida estándar):

| Variable | Qué es |
|---|---|
| `ZASCARR_PRUEBA_BD` | URL de la base de pruebas (la misma que ve el proceso de la prueba) |
| `ZASCARR_PRUEBA_BIBLIOTECA` | directorio de la biblioteca de prueba |
| `ZASCARR_PRUEBA_SECRETO` | clave con la que se firmó el token |
| `ZASCARR_PRUEBA_TOKEN` | el token de vinculación a confirmar |
| `ZASCARR_PRUEBA_MODO` | `confirmar` · `morir_antes_del_commit` · `morir_despues_del_commit` · `fallar_despues_del_commit` · `retener_antes_del_commit` · `retener_y_morir_antes_del_commit` |
| `ZASCARR_PRUEBA_RETENER_S` | tope, en segundos, de la retención de la transacción abierta (los dos modos `retener_…`); termina antes si la prueba escribe una línea por la entrada estándar |
| `ZASCARR_PRUEBA_BARRERA` | `1`: imprime `LISTO` y espera una línea por la entrada estándar antes de pedir (arranque simultáneo) |

Líneas que imprime (cada una con `flush`): `LISTO`; `EN_TRANSACCION vinculados=N informes=M` (lo que ve la propia
transacción, ya escrito y SIN confirmar); `RETENIENDO`; `ANTES_DEL_COMMIT t=<epoch>`; `COMMIT_HECHO t=<epoch>`;
`RESULTADO {json}` con `status`, `body` y `t_fin`. Un proceso que muere no imprime `RESULTADO`.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from tests._pg import url_asyncpg
from zascarr.api import revision as api_revision
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import vinculacion


def _decir(linea: str) -> None:
    print(linea, flush=True)


def _senal() -> asyncio.Event:
    """Se activa cuando la prueba escribe una línea por la entrada estándar (hilo propio: no bloquea el cierre)."""
    evento, bucle = asyncio.Event(), asyncio.get_running_loop()

    def _leer() -> None:
        sys.stdin.readline()
        bucle.call_soon_threadsafe(evento.set)
    threading.Thread(target=_leer, daemon=True).start()
    return evento


async def _principal() -> None:
    modo = os.environ["ZASCARR_PRUEBA_MODO"]
    secreto = os.environ["ZASCARR_PRUEBA_SECRETO"]
    biblioteca = Path(os.environ["ZASCARR_PRUEBA_BIBLIOTECA"])
    retener = float(os.environ.get("ZASCARR_PRUEBA_RETENER_S", "0"))
    senal = _senal() if modo.startswith("retener") or os.environ.get("ZASCARR_PRUEBA_BARRERA") == "1" else None

    motor = create_async_engine(url_asyncpg(os.environ["ZASCARR_PRUEBA_BD"]))
    fabrica = async_sessionmaker(motor, expire_on_commit=False)

    async def _get_db():
        async with fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    api_revision.get_settings = lambda: SimpleNamespace(secret_key=secreto)
    vinculacion.get_settings = lambda: SimpleNamespace(library_path=biblioteca)

    commit_real = AsyncSession.commit

    async def commit(self: AsyncSession) -> None:
        if modo in ("morir_antes_del_commit", "retener_antes_del_commit", "retener_y_morir_antes_del_commit"):
            await self.flush()          # las escrituras YA están en la transacción abierta, sin confirmar
            if modo == "morir_antes_del_commit":
                n = (await self.execute(text("SELECT count(*) FROM files WHERE issue_id IS NOT NULL"))).scalar_one()
                m = (await self.execute(text("SELECT count(*) FROM vinculacion_operaciones"))).scalar_one()
                _decir(f"EN_TRANSACCION vinculados={n} informes={m}")
                os.kill(os.getpid(), signal.SIGKILL)        # muerte real: ni rollback ni respuesta
            _decir("RETENIENDO")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(senal.wait(), retener)        # hasta que la prueba lo diga (o el tope)
            if modo == "retener_y_morir_antes_del_commit":
                os.kill(os.getpid(), signal.SIGKILL)        # muere con la transacción abierta y los candados puestos
            _decir(f"ANTES_DEL_COMMIT t={time.time()}")
        await commit_real(self)
        if modo == "morir_despues_del_commit":
            _decir(f"COMMIT_HECHO t={time.time()}")
            os.kill(os.getpid(), signal.SIGKILL)            # confirmado en Postgres; la respuesta nunca sale
        if modo == "fallar_despues_del_commit":
            _decir(f"COMMIT_HECHO t={time.time()}")
            raise ConnectionError("se perdió la conexión al confirmar")      # el proceso sigue vivo
        if modo == "retener_antes_del_commit":
            _decir(f"COMMIT_HECHO t={time.time()}")
    AsyncSession.commit = commit  # type: ignore[method-assign]

    async with fabrica() as s:                                  # conexión caliente antes de la barrera
        await s.execute(text("SELECT 1"))
    if os.environ.get("ZASCARR_PRUEBA_BARRERA") == "1":
        _decir("LISTO")
        await senal.wait()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                                 headers={"Origin": "http://localhost"}) as c:
        r = await c.post("/api/revision/vinculacion", json={"token": os.environ["ZASCARR_PRUEBA_TOKEN"]})
    _decir("RESULTADO " + json.dumps({"status": r.status_code, "body": r.json(), "t_fin": time.time()}))
    await motor.dispose()


if __name__ == "__main__":
    asyncio.run(_principal())
