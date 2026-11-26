"""Lector aislado del estado informativo de actualización (#443).

Contrato B1, solo lectura: un JSON UTF-8 de hasta 4096 bytes con esquema 1
(cinco claves, el histórico) o esquema 2 (doce claves: ``schema``, ``id``,
``unidad``, ``estado``, ``fase``, ``inicio_epoch``, ``actualizado_epoch``,
``head0``, ``sha_destino``, ``sha_actual``, ``resultado`` y ``codigo``).
``estado`` pertenece a {aceptada, en_curso, hecha, fallida, incierta} y
``fase`` al orden cerrado aceptada, reservada, preparacion, copia, git, build,
migracion, arranque y fin. Un intento activo sin noticias durante 7200
segundos se interpreta incierto, nunca fallido; un terminal es terminal
aunque sea antiguo.

``leer_estado_actualizacion`` conserva su contrato (requiere el id esperado);
``leer_ultimo_intento`` lee el último intento sin id de petición. Ambas son de
solo lectura y no elevan ni reparan el fichero.

Esto es únicamente información declarada por un hipotético escritor del host:
no acredita su procedencia, éxito efectivo, seguridad ni autorización para
iniciar, repetir o recuperar una operación. La integración deberá proteger el
archivo y directorios y reconciliar el host ante cualquier incertidumbre.
No se devuelven datos libres del archivo ni errores, rutas o identificadores.
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

MAX_BYTES = 4096
#: El ejecutor permite 5400 s; el margen evita declarar incierta una obra sana.
SIN_NOTICIAS_SEGUNDOS = 7200
#: Única unidad admitida del contrato §1.
UNIDAD = "zascarr-actualizar.service"
ESTADOS: frozenset[str] = frozenset(
    {"aceptada", "en_curso", "hecha", "fallida", "incierta"}
)
ESTADOS_TERMINALES: frozenset[str] = frozenset({"hecha", "fallida", "incierta"})
CODIGOS: frozenset[str] = frozenset(
    {"success:exited:0", "exit-code:exited:75", "otro"}
)
_FASES: frozenset[str] = frozenset(
    {
        "aceptada",
        "reservada",
        "preparacion",
        "copia",
        "git",
        "build",
        "migracion",
        "arranque",
        "fin",
    }
)
_FASE_INICIAL = "aceptada"
_ESTADO_INICIAL = "aceptada"
_FASE_FINAL = "fin"
_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_CAMPOS_V1 = frozenset({"schema", "id", "estado", "inicio_epoch", "actualizado_epoch"})
_CAMPOS_V2 = frozenset(
    {
        "schema",
        "id",
        "unidad",
        "estado",
        "fase",
        "inicio_epoch",
        "actualizado_epoch",
        "head0",
        "sha_destino",
        "sha_actual",
        "resultado",
        "codigo",
    }
)


class EstadoActualizacion(StrEnum):
    """Categorías cerradas, sin mensajes proporcionados por el host."""

    ACEPTADA = "aceptada"
    EN_CURSO = "en_curso"
    HECHA = "hecha"
    FALLIDA = "fallida"
    INCIERTA = "incierta"


@dataclass(frozen=True)
class IntentoActualizacion:
    """Interpretación cerrada de un estado; sin textos libres del host."""

    estado: EstadoActualizacion
    fase: str
    inicio_epoch: int
    actualizado_epoch: int
    head0: str | None
    sha_destino: str | None
    sha_actual: str | None
    resultado: str | None
    codigo: str | None
    sin_noticias: bool


def _objeto_sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pares:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _identidad_valida(valor: object) -> bool:
    return type(valor) is str and _ID.fullmatch(valor) is not None


def _estado_valido(valor: object) -> bool:
    return type(valor) is str and valor in ESTADOS


def _epocas_validas(inicio: object, actualizado: object) -> bool:
    return (
        type(inicio) is int
        and type(actualizado) is int
        and 0 <= inicio <= actualizado < 2**63
    )


def _sha_valido(valor: object) -> bool:
    return valor is None or (type(valor) is str and _SHA.fullmatch(valor) is not None)


def _normalizar(datos: object) -> dict[str, Any] | None:
    """Valida el contrato §1 y §2 y devuelve la instantánea v2, sin mutar.

    Un v1 válido se interpreta con los valores por defecto del contrato; un
    v2 se acepta solo con sus doce claves y la coherencia de terminal. Cualquier
    clave de más o de menos, tipo, unidad, fase, hash, época o resultado fuera
    de contrato devuelve `None` sin interpretación parcial.
    """
    if type(datos) is not dict:
        return None
    esquema = datos.get("schema")
    if type(esquema) is not int:
        return None
    if esquema == 1:
        if set(datos) != _CAMPOS_V1:
            return None
        if not _identidad_valida(datos.get("id")) or not _estado_valido(datos.get("estado")):
            return None
        if not _epocas_validas(datos.get("inicio_epoch"), datos.get("actualizado_epoch")):
            return None
        return {
            "schema": 2,
            "id": datos["id"],
            "unidad": UNIDAD,
            "estado": datos["estado"],
            "fase": _FASE_INICIAL,
            "inicio_epoch": datos["inicio_epoch"],
            "actualizado_epoch": datos["actualizado_epoch"],
            "head0": None,
            "sha_destino": None,
            "sha_actual": None,
            "resultado": None,
            "codigo": None,
        }
    if esquema != 2:
        return None
    if set(datos) != _CAMPOS_V2:
        return None
    if not _identidad_valida(datos.get("id")) or datos.get("unidad") != UNIDAD:
        return None
    if not _estado_valido(datos.get("estado")):
        return None
    fase = datos.get("fase")
    if type(fase) is not str or fase not in _FASES:
        return None
    if not _epocas_validas(datos.get("inicio_epoch"), datos.get("actualizado_epoch")):
        return None
    for clave in ("head0", "sha_destino", "sha_actual"):
        if not _sha_valido(datos.get(clave)):
            return None
    estado = datos["estado"]
    resultado, codigo = datos.get("resultado"), datos.get("codigo")
    if estado in ESTADOS_TERMINALES:
        if fase != _FASE_FINAL or resultado != estado:
            return None
        if type(codigo) is not str or codigo not in CODIGOS:
            return None
    elif (
        resultado is not None
        or codigo is not None
        or fase == _FASE_FINAL
        or (estado == _ESTADO_INICIAL and fase != _FASE_INICIAL)
    ):
        return None
    return {clave: datos[clave] for clave in _CAMPOS_V2}


def _abrir_regular(path: Path) -> int:
    """Abre cada componente sin seguir enlaces; nunca espera a un FIFO."""
    parts = path.parts
    if not parts or any(part in ("..", "") for part in parts):
        raise ValueError
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
    current = os.open("/" if path.is_absolute() else ".", flags_dir)
    try:
        components = parts[1:] if path.is_absolute() else parts
        if not components:
            raise ValueError
        for part in components[:-1]:
            next_fd = os.open(part, flags_dir, dir_fd=current)
            os.close(current)
            current = next_fd
        # O_PATH permite inspeccionar el tipo sin abrir un dispositivo o FIFO.
        # El acceso posterior por /proc/self/fd ancla el mismo inode, incluso si
        # se sustituye la entrada del directorio. Si proc no está disponible,
        # la lectura falla cerrada; esto no acredita propiedad ni procedencia.
        anchor = os.open(components[-1], os.O_PATH | os.O_NOFOLLOW, dir_fd=current)
        try:
            expected = os.fstat(anchor)
            if not stat.S_ISREG(expected.st_mode):
                raise ValueError
            fd = os.open(f"/proc/self/fd/{anchor}", os.O_RDONLY | os.O_NONBLOCK)
            try:
                actual = os.fstat(fd)
                if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                    raise ValueError
                return fd
            except BaseException:
                os.close(fd)
                raise
        finally:
            os.close(anchor)
    finally:
        os.close(current)


def _leer_json(path: Path) -> object | None:
    """Lee el archivo con el abridor endurecido; `None` ante cualquier anomalía."""
    try:
        fd = _abrir_regular(Path(path))
        try:
            antes = os.fstat(fd)
            if antes.st_size > MAX_BYTES:
                return None
            datos = bytearray()
            while len(datos) <= MAX_BYTES:
                bloque = os.read(fd, MAX_BYTES + 1 - len(datos))
                if not bloque:
                    break
                datos.extend(bloque)
            despues = os.fstat(fd)
            if (len(datos) > MAX_BYTES or len(datos) != despues.st_size
                    or (antes.st_size, antes.st_mtime_ns, antes.st_ctime_ns)
                    != (despues.st_size, despues.st_mtime_ns, despues.st_ctime_ns)):
                return None
        finally:
            os.close(fd)
        return json.loads(bytes(datos).decode("utf-8"),
                          object_pairs_hook=_objeto_sin_duplicados)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return None


def _intento(base: dict[str, Any], ahora_epoch: int) -> IntentoActualizacion | None:
    """Aplica reloj y reconciliación sobre una instantánea ya normalizada a v2."""
    if base["actualizado_epoch"] > ahora_epoch:
        return None
    estado = EstadoActualizacion(base["estado"])
    sin_noticias = False
    if (estado in (EstadoActualizacion.ACEPTADA, EstadoActualizacion.EN_CURSO)
            and ahora_epoch - base["actualizado_epoch"] >= SIN_NOTICIAS_SEGUNDOS):
        estado = EstadoActualizacion.INCIERTA
        sin_noticias = True
    return IntentoActualizacion(
        estado=estado,
        fase=base["fase"],
        inicio_epoch=base["inicio_epoch"],
        actualizado_epoch=base["actualizado_epoch"],
        head0=base["head0"],
        sha_destino=base["sha_destino"],
        sha_actual=base["sha_actual"],
        resultado=base["resultado"],
        codigo=base["codigo"],
        sin_noticias=sin_noticias,
    )


def interpretar_ultimo_intento(
    datos: object, *, ahora_epoch: int | None
) -> IntentoActualizacion | None:
    """Decide sobre un estado ya leído; puro, sin E/S y sin reloj interno.

    Aplica la validación v1/v2, la comparación con `ahora_epoch` y la
    reconciliación: un activo con 7200 s o más sin noticias es incierto con
    `sin_noticias=True` (nunca fallido) y un terminal es siempre terminal. Un
    reloj inválido, una época futura, una clave de más, un hash mal formado o
    un esquema desconocido devuelven `None` sin excepción ni mutar `datos`.
    """
    if type(ahora_epoch) is not int or not 0 <= ahora_epoch < 2**63:
        return None
    base = _normalizar(datos)
    if base is None:
        return None
    return _intento(base, ahora_epoch)


def leer_ultimo_intento(
    path: Path, *, ahora_epoch: int | None = None
) -> IntentoActualizacion | None:
    """Lee el último intento sin exigir id de petición; `None` si no vale.

    No eleva, no repara y no escribe: un v1 se interpreta con los valores por
    defecto del contrato y un fichero ausente, inválido o de esquema
    desconocido devuelve `None` sin interpretación parcial.
    """
    if ahora_epoch is None:
        ahora_epoch = int(time.time())
    if type(ahora_epoch) is not int or not 0 <= ahora_epoch < 2**63:
        return None
    datos = _leer_json(Path(path))
    if datos is None:
        return None
    return interpretar_ultimo_intento(datos, ahora_epoch=ahora_epoch)


def leer_estado_actualizacion(
    path: Path, *, id_esperado: str, ahora_epoch: int | None = None
) -> EstadoActualizacion:
    """Lee una instantánea correlacionada o devuelve siempre incertidumbre.

    Acepta v1 y v2 y conserva el contrato anterior para v1: el id esperado es
    obligatorio y un id distinto, un fichero inválido o un reloj inválido
    resultan `INCIERTA`. El reloj puede inyectarse para las pruebas; un reloj
    inválido falla cerrado. La lectura es síncrona y quien la integre en una
    vista async debe delegarla.
    """
    if not isinstance(id_esperado, str) or not _ID.fullmatch(id_esperado):
        return EstadoActualizacion.INCIERTA
    if ahora_epoch is None:
        ahora_epoch = int(time.time())
    if type(ahora_epoch) is not int or not 0 <= ahora_epoch < 2**63:
        return EstadoActualizacion.INCIERTA
    datos = _leer_json(Path(path))
    if datos is None:
        return EstadoActualizacion.INCIERTA
    base = _normalizar(datos)
    if base is None or base["id"] != id_esperado:
        return EstadoActualizacion.INCIERTA
    intento = _intento(base, ahora_epoch)
    if intento is None:
        return EstadoActualizacion.INCIERTA
    return intento.estado
