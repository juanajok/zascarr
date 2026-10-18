# ruff: noqa: E501
"""Credenciales por defecto: la aplicación se niega a servir con una contraseña de base de datos conocida.

Es la última barrera: el instalador genera una contraseña propia (`scripts/_credenciales.sh`) y Compose se niega a
crear PostgreSQL con una ausente, vacía o de ejemplo (servicio `credenciales`). Esta comprobación cubre la ruta que
no pasa por ninguno de los dos (la app lanzada a mano con un `DATABASE_URL` copiado de un ejemplo). Falla cerrado: el
arranque lo trata como «base de datos no disponible» (modo solo diagnóstico) y el motivo queda en el log, SIN el valor.

La lista es la misma que la de `scripts/_credenciales.sh` y la del servicio `credenciales` de `docker-compose.yml`
(`tests/test_credenciales_lista.py` comprueba que coinciden).
"""
from __future__ import annotations

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

#: En minúsculas: se compara sin distinguir mayúsculas.
CREDENCIALES_CONOCIDAS: frozenset[str] = frozenset(
    {"cambia_esto_ahora", "supersecretpassword123", "changeme"}
)

_ANFITRIONES_LOCALES = {None, "", "localhost", "127.0.0.1", "::1"}


def es_credencial_conocida(valor: str | None) -> bool:
    """`True` si el valor está vacío o es una contraseña de ejemplo conocida."""
    limpio = (valor or "").strip().strip("\"'").strip().lower()
    return not limpio or limpio in CREDENCIALES_CONOCIDAS


def problema_de_credenciales(database_url: str | URL) -> str | None:
    """Motivo por el que `database_url` no debe usarse, o `None` si está bien (sin el valor)."""
    try:
        url = make_url(database_url)
    except ArgumentError:
        return "DATABASE_URL no se puede interpretar"
    if url.username == "INVALID" or url.database == "INVALID":
        return "DATABASE_URL conserva el valor de relleno: no hay una base de datos configurada"
    if url.password and es_credencial_conocida(url.password):
        return "la contraseña de la base de datos es un valor de ejemplo conocido"
    if not url.password and url.host not in _ANFITRIONES_LOCALES:
        return "DATABASE_URL no lleva contraseña para una base de datos que no es local"
    return None


class CredencialesNoSegurasError(RuntimeError):
    """El arranque se detiene antes de abrir ninguna conexión."""
