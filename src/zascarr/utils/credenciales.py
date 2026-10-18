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

#: Espacios en blanco que se recortan en los extremos: ASCII, los mismos que `[[:space:]]` en configuración regional C (la
#: que usan el instalador y el servicio de Compose).
_BLANCOS = " \t\n\r\v\f"
_MINUSCULAS = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")


def _normalizada(valor: str | None) -> str:
    """La regla ÚNICA de «no vale» (la misma en `scripts/_credenciales.sh` y en el servicio `credenciales` de Compose;
    `tests/_tabla_credenciales.py` comprueba las tres con la misma tabla): se recortan los extremos; si empieza y acaba por
    la misma comilla se quita ese par y se recorta otra vez; minúsculas ASCII. NUNCA se borra nada interior: `change me` es
    una contraseña personal, no `changeme`."""
    v = (valor or "").strip(_BLANCOS)
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        v = v[1:-1].strip(_BLANCOS)
    return v.translate(_MINUSCULAS)


def es_credencial_conocida(valor: str | None) -> bool:
    """`True` si el valor está vacío o es, tal cual (ver `_normalizada`), una contraseña de ejemplo conocida."""
    limpio = _normalizada(valor)
    return not limpio or limpio in CREDENCIALES_CONOCIDAS


def _es_socket_unix(url: URL) -> bool:
    """Conexión por socket Unix local: sin host de red, ni en la autoridad ni en el parámetro `host` (que en asyncpg/libpq
    puede ser un nombre de máquina: `postgresql://u@/db?host=db.ejemplo.org` es TCP remoto)."""
    if url.host not in (None, ""):
        return False
    extra = url.query.get("host")
    if extra is None:
        return True
    hosts = [extra] if isinstance(extra, str) else list(extra)
    return all(h.startswith("/") for h in hosts)


def problema_de_credenciales(database_url: str | URL) -> str | None:
    """Motivo por el que `database_url` no debe usarse, o `None` si está bien (sin el valor).

    Autenticación alternativa SOPORTADA, explícita (ADR 0012): únicamente el **socket Unix local** sin contraseña (el
    `peer`/`trust` del propio equipo). Una conexión TCP sin contraseña —ni siquiera al bucle local— NO lo es: cualquier
    proceso del equipo podría usarla. No hay más excepciones al contrato «ninguna credencial obligatoria ausente».
    """
    try:
        url = make_url(database_url)
    except ArgumentError:
        return "DATABASE_URL no se puede interpretar"
    if url.username == "INVALID" or url.database == "INVALID":
        return "DATABASE_URL conserva el valor de relleno: no hay una base de datos configurada"
    if url.password and es_credencial_conocida(url.password):
        return "la contraseña de la base de datos es un valor de ejemplo conocido"
    if not url.password and not _es_socket_unix(url):
        return "DATABASE_URL no lleva contraseña y la conexión no es por socket Unix local: se exige una contraseña"
    return None


class CredencialesNoSegurasError(RuntimeError):
    """El arranque se detiene antes de abrir ninguna conexión."""
