#!/usr/bin/env python3
"""A11 — comando administrativo de seguridad, para el instalador.

Fija la contraseña de acceso ANTES de que el instalador publique el puerto en la
red (ficha `docs/design/benchmark-A11-exposicion.md`): así no existe ni un
instante con la interfaz abierta y sin contraseña.

    # ¿hay ya una contraseña? (no imprime nada sensible)
    python -m zascarr.cli.seguridad estado

    # fijarla: la contraseña entra por stdin, NUNCA por argumentos ni entorno
    printf '%s\\n' "$CONTRASENA" | python -m zascarr.cli.seguridad fijar-contrasena

    # configuración EFECTIVA (lo que de verdad aplicaría la app al arrancar: el
    # .env más lo que se guardó en Ajustes), no solo lo que dice el .env
    python -m zascarr.cli.seguridad efectiva

    # retirar la dirección pública guardada en Ajustes, para que mande el .env
    python -m zascarr.cli.seguridad retirar-base-url

En la Pi no hay Python en el host: el instalador lo invoca con
`docker compose run --rm -T zascarr python -m zascarr.cli.seguridad ...`.

Usa el MISMO servicio que Ajustes (`services/seguridad.py`): una sola regla de
longitud y el mismo guardado (hash PBKDF2, versión de sesión, caché de Basic).

Códigos de salida (el instalador decide con ellos, no con el texto):
    0  hecho (o, en `estado`, hay contraseña)
    1  error inesperado (p. ej. sin conexión con la base de datos)
    2  contraseña rechazada (el motivo va a stderr, en español)
    3  `estado`: no hay contraseña configurada
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from zascarr.config import get_settings
from zascarr.database import async_session_factory, engine
from zascarr.services.runtime_settings import (
    RuntimeSettingsService,
    capturar_valores_base,
    load_overrides_at_startup,
)
from zascarr.services.seguridad import estado_de_seguridad, fijar_seguridad, hay_contrasena

OK = 0
ERROR = 1
RECHAZADA = 2
SIN_CONTRASENA = 3


async def fijar_contrasena(db, linea: str) -> tuple[int, str, str | None]:
    """(código, mensaje, aviso). `linea` es lo leído de stdin, sin el salto final."""
    if not linea:
        return RECHAZADA, "No he recibido ninguna contraseña por la entrada estándar.", None
    s = get_settings()
    resultado = await fijar_seguridad(
        db, modo="password",
        # No toca el usuario ni la `base_url` que ya hubiera: este comando solo
        # fija la contraseña.
        usuario=s.auth_username, password=linea, base_url=None,
    )
    if resultado.error:
        return RECHAZADA, resultado.error, None
    return OK, "Contraseña guardada.", resultado.aviso


def efectiva() -> str:
    """Tres líneas `clave=valor` con la configuración EFECTIVA. El instalador la
    lee para comprobar —y contarle al coleccionista— lo que de verdad va a pasar,
    no lo que él escribió en el `.env`: una dirección pública guardada antes en
    Ajustes manda sobre el `.env` y puede dejar el servicio más expuesto de lo que
    parece."""
    s = get_settings()
    est = estado_de_seguridad(s)
    base_url = (s.base_url or "").replace("\n", "").replace("\r", "")
    return "\n".join([
        f"exposicion={est['exposicion']}",
        f"contrasena={'si' if est['contrasena'] else 'no'}",
        f"base_url={base_url}",
    ])


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Seguridad de acceso de ZascArr (instalador).")
    sub = p.add_subparsers(dest="orden", required=True)
    sub.add_parser("estado", help="¿hay una contraseña configurada? (código 0 sí, 3 no)")
    sub.add_parser("fijar-contrasena", help="guarda la contraseña que llega por stdin")
    sub.add_parser("efectiva", help="imprime la exposición, la contraseña y la BASE_URL efectivas")
    sub.add_parser(
        "retirar-base-url",
        help="borra la dirección pública guardada en Ajustes: pasa a mandar la del .env",
    )
    return p


async def _ejecutar(orden: str) -> int:
    async with async_session_factory() as db:
        # Mismo orden que el arranque de la app: sin esto `get_settings()` no vería
        # lo que ya se guardó en Ajustes y `estado` mentiría.
        capturar_valores_base()
        await load_overrides_at_startup(db)

        if orden == "estado":
            if hay_contrasena():
                print("contrasena: configurada")
                return OK
            print("contrasena: ninguna")
            return SIN_CONTRASENA

        if orden == "efectiva":
            print(efectiva())
            return OK

        if orden == "retirar-base-url":
            # `base_url=""` en la BD significa «vuelve al valor del .env»
            # (runtime_settings._VACIOS_QUE_VUELVEN_AL_ENV).
            await RuntimeSettingsService(db).save({"base_url": ""})
            await db.commit()
            print("Dirección pública de Ajustes retirada: manda la del .env.")
            return OK

        # El salto de línea final no es parte de la contraseña; los espacios, sí.
        linea = sys.stdin.readline().rstrip("\r\n")
        codigo, mensaje, aviso = await fijar_contrasena(db, linea)
        if codigo != OK:
            print(mensaje, file=sys.stderr)
            return codigo
        await db.commit()
        print(mensaje)
        if aviso:
            print(f"Aviso: {aviso}", file=sys.stderr)
        return OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    async def _main() -> int:
        try:
            return await _ejecutar(args.orden)
        except Exception as exc:  # noqa: BLE001 — el instalador decide por el código
            # Nada de traceback con rutas ni credenciales en un instalador para
            # no técnicos: la clase del error basta para buscarlo.
            print(f"No he podido completar la operación ({type(exc).__name__}).", file=sys.stderr)
            return ERROR
        finally:
            await engine.dispose()

    return asyncio.run(_main())


if __name__ == "__main__":
    sys.exit(main())
