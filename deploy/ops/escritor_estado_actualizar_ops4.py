"""Escritor aislado de estado de actualización; no ejecuta ni autoriza nada.

Escribe un JSON canónico en un temporal exclusivo del mismo directorio,
sincroniza el archivo, renombra y sincroniza el directorio. Ante cualquier
error devuelve INCIERTO: no se puede deducir si el nombre antiguo o el nuevo
sobrevivirá a un corte, y el llamador no debe tratarlo como éxito. Un fsync
correcto tampoco demuestra que el hardware o el filesystem respeten flush.
No comprueba propiedad del directorio y no se conecta a la UI ni al auxiliar.

Cerrojo de publicación (B1, obligatorio): leer, decidir y reemplazar es una
sola sección crítica frente a otro escritor del host. El cerrojo es un `flock`
exclusivo sobre el descriptor del directorio del estado (el mismo que se abre
con `O_DIRECTORY|O_NOFOLLOW`), no crea ficheros nuevos y se libera en todas las
salidas al cerrar el descriptor. Lo toman `escribir_estado` (la instantánea
inicial del auxiliar) y `publicar_transicion`, que al tenerlo ya delega en el
publicador interno sin cerrojo y nunca llama a `escribir_estado` (volvería a
tomarlo y se autobloquearía). Sin directorio no hay dónde publicar
(`INVALIDO`); sin cerrojo se falla cerrado (`INCIERTO`). No sustituye al
cerrojo único de operaciones (B2) ni coordina entre hosts.

H-5: el fichero no se publica como `0600 root:root`. La app corre con
PUID:PGID sobre un montaje `ro`; para que pueda leer el estado, el temporal se
publica `0640` y, cuando el llamador lo indica, con dueño `root:<grupo>`
(`propietario`). El grupo se obtiene del directorio `ops` (`0750 root:<grupo>`
por el instalador), no de una ruta ni de una cadena libre.

La guarda de monotonía (`calcular_transicion` y `publicar_transicion`) nunca
pisa un estado terminal, no baja `actualizado_epoch` y no cambia `id` ni
`inicio_epoch`; devuelve cerrado (`INVALIDO`/`INCIERTO`) y nunca lanza.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import secrets
import stat
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import cast

MAX_BYTES = 4096
#: La app lee el estado con PUID:PGID sobre un montaje `ro` (H-5).
MODO_ESTADO = 0o640
#: Única unidad del contrato §1: la actualización manual de OPS4.
UNIDAD = "zascarr-actualizar.service"
#: Orden total de fases del contrato §1 y §2. Todo el código compara fases
#: contra `FASES` (o su índice) en lugar de repetir literales.
FASES: tuple[str, ...] = (
    "aceptada",
    "preparacion",
    "copia",
    "git",
    "build",
    "migracion",
    "arranque",
    "fin",
)
ESTADO_INICIAL = "aceptada"
ESTADO_EN_CURSO = "en_curso"
ESTADOS: frozenset[str] = frozenset(
    {ESTADO_INICIAL, ESTADO_EN_CURSO, "hecha", "fallida", "incierta"}
)
ESTADOS_TERMINALES: frozenset[str] = frozenset({"hecha", "fallida", "incierta"})
CODIGO_EXITO = "success:exited:0"
CODIGO_CERROJO = "exit-code:exited:75"
CODIGO_OTRO = "otro"
CODIGOS: frozenset[str] = frozenset({CODIGO_EXITO, CODIGO_CERROJO, CODIGO_OTRO})
_FASE_INICIAL = FASES[0]
_FASE_FINAL = FASES[-1]
_ORDEN_FASES = {fase: posicion for posicion, fase in enumerate(FASES)}
_ESCRITURA_AJENA = stat.S_IWGRP | stat.S_IWOTH
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
#: Centinela de argumento: «conserva el valor que ya tenía el estado».
_NO_CAMBIA = object()
#: Centinela interno de decisión: la transición pedida es inválida.
_RECHAZO = object()


class ResultadoEscritura(StrEnum):
    OK = "ok"
    INCIERTO = "incierto"
    INVALIDO = "invalido"


class ResultadoLectura(StrEnum):
    OK = "ok"
    AUSENTE = "ausente"
    INVALIDO = "invalido"


def _reemplazar(origen: str, destino: str, dir_fd: int) -> None:
    os.replace(origen, destino, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)


def _objeto_sin_duplicados(pares: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pares:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def propietario_servicio(ruta: str | Path) -> tuple[int, int] | None:
    """Dueño `root:<grupo del directorio ops>` cuando el escritor corre como root.

    En pruebas o en un contexto sin privilegios devuelve `None`: el fichero se
    publica igualmente `0640`, pero no se intenta un `fchown` que fallaría.
    """
    if os.geteuid() != 0:
        return None
    try:
        grupo = os.stat(Path(ruta).parent).st_gid
    except OSError:
        return None
    return (0, grupo)


def _validar_epocas(inicio: object, actualizado: object) -> bool:
    """`0 <= inicio <= actualizado < 2**63`, ambos enteros."""
    return (
        type(inicio) is int
        and type(actualizado) is int
        and 0 <= inicio <= actualizado < 2**63
    )


def _validar_sha(valor: object) -> bool:
    """Un hash del contrato es `None` o 40 hexadecimales minúsculas."""
    return valor is None or (type(valor) is str and _SHA.fullmatch(valor) is not None)


def _validar_v1(datos: dict[str, object]) -> bool:
    if set(datos) != _CAMPOS_V1:
        return False
    identidad = datos["id"]
    if type(identidad) is not str or _ID.fullmatch(identidad) is None:
        return False
    estado = datos["estado"]
    if type(estado) is not str or estado not in ESTADOS:
        return False
    return _validar_epocas(datos["inicio_epoch"], datos["actualizado_epoch"])


def _validar_v2(datos: dict[str, object]) -> bool:
    if set(datos) != _CAMPOS_V2:
        return False
    identidad = datos["id"]
    if type(identidad) is not str or _ID.fullmatch(identidad) is None:
        return False
    if datos["unidad"] != UNIDAD:
        return False
    estado = datos["estado"]
    if type(estado) is not str or estado not in ESTADOS:
        return False
    fase = datos["fase"]
    if type(fase) is not str or fase not in _ORDEN_FASES:
        return False
    if not _validar_epocas(datos["inicio_epoch"], datos["actualizado_epoch"]):
        return False
    if not all(_validar_sha(datos[clave]) for clave in ("head0", "sha_destino", "sha_actual")):
        return False
    resultado, codigo = datos["resultado"], datos["codigo"]
    if estado in ESTADOS_TERMINALES:
        if fase != _FASE_FINAL or resultado != estado:
            return False
        return type(codigo) is str and codigo in CODIGOS
    if fase == _FASE_FINAL:
        return False
    if estado == ESTADO_INICIAL and fase != _FASE_INICIAL:
        return False
    return resultado is None and codigo is None


def validar_estado(datos: object) -> bool:
    """Único punto de validación del contrato §1 y §2; no tiene efectos.

    Acepta las instantáneas v2 canónicas de 12 claves y los v1 válidos de 5, y
    rechaza cualquier otra cosa: no-dict, claves de más o de menos, tipos
    cambiados, `unidad` ajena, fase, resultado o código fuera de su lista
    cerrada, hash mal formado y épocas invertidas o fuera de rango. No lee el
    reloj: comparar con `ahora` es del llamador.
    """
    if type(datos) is not dict:
        return False
    esquema = datos.get("schema")
    if type(esquema) is not int:
        return False
    if esquema == 1:
        return _validar_v1(datos)
    if esquema == 2:
        return _validar_v2(datos)
    return False


def estado_inicial(id_: str, ahora: int) -> dict[str, object]:
    """Instantánea v2 canónica de un intento recién aceptado (contrato §3).

    Es pura: no hace E/S, no lee el reloj (usa `ahora` para las dos épocas) y
    no muta sus argumentos. Devuelve exactamente las 12 claves del esquema 2 y
    lanza `ValueError` si la identidad o la época no cumplen el contrato.
    """
    if type(id_) is not str or _ID.fullmatch(id_) is None:
        raise ValueError("identificador de intento inválido")
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        raise ValueError("época de inicio inválida")
    datos: dict[str, object] = {
        "schema": 2,
        "id": id_,
        "unidad": UNIDAD,
        "estado": ESTADO_INICIAL,
        "fase": _FASE_INICIAL,
        "inicio_epoch": ahora,
        "actualizado_epoch": ahora,
        "head0": None,
        "sha_destino": None,
        "sha_actual": None,
        "resultado": None,
        "codigo": None,
    }
    if not validar_estado(datos):
        raise ValueError("instantánea inicial fuera del contrato")
    return datos


def _base_v2(actual: object) -> dict[str, object] | None:
    """Normaliza un v1/v2 válido a la instantánea v2 de partida, sin mutarlo."""
    if type(actual) is not dict or not validar_estado(actual):
        return None
    if actual["schema"] == 1:
        return {
            "schema": 2,
            "id": actual["id"],
            "unidad": UNIDAD,
            "estado": actual["estado"],
            "fase": _FASE_INICIAL,
            "inicio_epoch": actual["inicio_epoch"],
            "actualizado_epoch": actual["actualizado_epoch"],
            "head0": None,
            "sha_destino": None,
            "sha_actual": None,
            "resultado": None,
            "codigo": None,
        }
    return {clave: actual[clave] for clave in _CAMPOS_V2}


def _congelado(previo: object, entrada: object) -> object:
    """Resuelve un hash inmutable: el previo, el nuevo o `_RECHAZO`."""
    if entrada is _NO_CAMBIA:
        return previo
    if entrada is None:
        nuevo: object = None
    elif type(entrada) is str and _SHA.fullmatch(entrada) is not None:
        nuevo = entrada
    else:
        return _RECHAZO
    if previo is not None and nuevo != previo:
        return _RECHAZO
    return nuevo


def _actual_hash(previo: object, entrada: object) -> object:
    """`sha_actual` puede avanzar, pero nunca volver a `None`."""
    if entrada is _NO_CAMBIA:
        return previo
    if entrada is None:
        return None if previo is None else _RECHAZO
    if type(entrada) is str and _SHA.fullmatch(entrada) is not None:
        return entrada
    return _RECHAZO


def calcular_transicion(
    actual: object,
    estado: str,
    *,
    ahora: int,
    id_: str | None = None,
    inicio_epoch: int | None = None,
    fase: str | None = None,
    head0: object = _NO_CAMBIA,
    sha_destino: object = _NO_CAMBIA,
    sha_actual: object = _NO_CAMBIA,
    codigo: str | None = None,
) -> dict[str, object] | None:
    """Decide la siguiente instantánea v2 sin tocar disco ni mutar la entrada.

    Es la única fuente de la regla de monotonía del contrato §3: conserva `id`
    e inicio, no baja épocas, no pisa un terminal, no retrocede de fase, no
    cambia `head0` ni `sha_destino` una vez fijados, no devuelve un hash a
    `None`, exige fase `fin` en el terminal con resultado igual al estado y
    código de la lista cerrada, y eleva un v1 válido a v2. Devuelve `None`
    cuando la transición es inválida, sin lanzar y sin efectos.
    """
    if type(estado) is not str or estado not in ESTADOS:
        return None
    if type(ahora) is not int or not 0 <= ahora < 2**63:
        return None
    base = _base_v2(actual)
    if base is None:
        return None
    previa = cast(str, base["fase"])
    if base["estado"] in ESTADOS_TERMINALES:
        return None
    if id_ is not None and id_ != base["id"]:
        return None
    if inicio_epoch is not None and inicio_epoch != base["inicio_epoch"]:
        return None
    if ahora < base["actualizado_epoch"]:
        return None
    if fase is None:
        nueva_fase = previa
    elif type(fase) is str and fase in _ORDEN_FASES:
        nueva_fase = fase
    else:
        return None
    if _ORDEN_FASES[nueva_fase] < _ORDEN_FASES[previa]:
        return None
    if estado == ESTADO_INICIAL and nueva_fase != _FASE_INICIAL:
        return None
    nuevo_head0 = _congelado(base["head0"], head0)
    nuevo_destino = _congelado(base["sha_destino"], sha_destino)
    nuevo_actual = _actual_hash(base["sha_actual"], sha_actual)
    if nuevo_head0 is _RECHAZO or nuevo_destino is _RECHAZO or nuevo_actual is _RECHAZO:
        return None
    resultado: str | None = None
    codigo_final: str | None = None
    if estado in ESTADOS_TERMINALES:
        if nueva_fase != _FASE_FINAL:
            return None
        if type(codigo) is not str or codigo not in CODIGOS:
            return None
        resultado = estado
        codigo_final = codigo
    elif nueva_fase == _FASE_FINAL:
        return None
    nuevo: dict[str, object] = {
        "schema": 2,
        "id": base["id"],
        "unidad": UNIDAD,
        "estado": estado,
        "fase": nueva_fase,
        "inicio_epoch": base["inicio_epoch"],
        "actualizado_epoch": ahora,
        "head0": nuevo_head0,
        "sha_destino": nuevo_destino,
        "sha_actual": nuevo_actual,
        "resultado": resultado,
        "codigo": codigo_final,
    }
    return nuevo if validar_estado(nuevo) else None


def escribir_estado(
    ruta: str | Path,
    datos: object,
    *,
    fsync: Callable[[int], None] = os.fsync,
    replace: Callable[[str, str, int], None] = _reemplazar,
    propietario: tuple[int, int] | None = None,
) -> ResultadoEscritura:
    """Valida y publica una instantánea bajo el cerrojo del directorio.

    La validación ocurre antes de tocar el sistema de ficheros: un estado
    inválido devuelve INVALIDO sin temporales, sin cerrojo y sin cambiar el
    fichero existente. Publica exactamente el esquema recibido (v1 de 5 claves
    o v2 de 12) y solo un fallo de durabilidad produce INCIERTO.
    """
    if not validar_estado(datos):
        return ResultadoEscritura.INVALIDO
    try:
        destino = Path(ruta)
        fd_dir = _abrir_directorio(destino.parent)
    except (OSError, TypeError, ValueError):
        return ResultadoEscritura.INVALIDO
    try:
        if not _tomar_cerrojo(fd_dir):
            return ResultadoEscritura.INCIERTO
        return _publicar(
            destino,
            cast(dict[str, object], datos),
            fd_dir,
            fsync=fsync,
            replace=replace,
            propietario=propietario,
        )
    finally:
        os.close(fd_dir)


def publicar_transicion(
    ruta: str | Path,
    estado: str,
    *,
    ahora: int,
    id_: str | None = None,
    inicio_epoch: int | None = None,
    fase: str | None = None,
    head0: object = _NO_CAMBIA,
    sha_destino: object = _NO_CAMBIA,
    sha_actual: object = _NO_CAMBIA,
    codigo: str | None = None,
    propietario: tuple[int, int] | None = None,
    fsync: Callable[[int], None] = os.fsync,
    replace: Callable[[str, str, int], None] = _reemplazar,
) -> ResultadoEscritura:
    """Guarda de monotonía: lee, delega la decisión y escribe con cerrojo.

    Mantiene el cerrojo de publicación tomado mientras lee, decide y escribe, y
    publica con el publicador interno sin cerrojo: nunca vuelve a llamar a
    `escribir_estado` (se autobloquearía). Solo escribe si hay un estado previo
    válido (nunca inventa ni repara uno corrupto), si el intento es el mismo
    (`id_`/`inicio_epoch`), si el estado actual no es terminal y si `ahora` no
    hace retroceder el reloj. Cualquier rechazo es INVALIDO sin tocar el
    fichero; un fallo de durabilidad es INCIERTO.
    """
    try:
        destino = Path(ruta)
        fd_dir = _abrir_directorio(destino.parent)
    except (OSError, TypeError, ValueError):
        return ResultadoEscritura.INVALIDO
    try:
        if not _tomar_cerrojo(fd_dir):
            return ResultadoEscritura.INCIERTO
        lectura, actual = _leer_en_directorio(fd_dir, destino.name)
        if lectura is not ResultadoLectura.OK or actual is None:
            return ResultadoEscritura.INVALIDO
        nuevo = calcular_transicion(
            actual,
            estado,
            ahora=ahora,
            id_=id_,
            inicio_epoch=inicio_epoch,
            fase=fase,
            head0=head0,
            sha_destino=sha_destino,
            sha_actual=sha_actual,
            codigo=codigo,
        )
        if nuevo is None:
            return ResultadoEscritura.INVALIDO
        return _publicar(
            destino,
            nuevo,
            fd_dir,
            fsync=fsync,
            replace=replace,
            propietario=propietario,
        )
    finally:
        os.close(fd_dir)


def _publicar(
    destino: Path,
    datos: dict[str, object],
    fd_dir: int,
    *,
    fsync: Callable[[int], None],
    replace: Callable[[str, str, int], None],
    propietario: tuple[int, int] | None,
) -> ResultadoEscritura:
    """Publica dentro de una sección crítica que ya tiene tomada el llamador.

    No adquiere cerrojos ni revalida la monotonía: es el único camino de
    escritura de `escribir_estado` (que sí toma el cerrojo) y de
    `publicar_transicion` (que ya lo tiene). Elimina el temporal en todas las
    salidas, también en la invalidez, la incertidumbre y la excepción.
    """
    if not validar_estado(datos):
        return ResultadoEscritura.INVALIDO
    try:
        contenido = _serializar(datos)
    except (TypeError, ValueError):
        return ResultadoEscritura.INVALIDO
    temporal = None
    fd = None
    try:
        try:
            info = os.fstat(fd_dir)
            if not stat.S_ISDIR(info.st_mode):
                return ResultadoEscritura.INVALIDO
            temporal = f".{destino.name}.tmp-{secrets.token_hex(8)}"
            fd = os.open(
                temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd_dir
            )
            _escribir_todo(fd, contenido)
            os.fchmod(fd, MODO_ESTADO)
            if propietario is not None:
                uid, gid = propietario
                os.fchown(fd, uid, gid)
            fsync(fd)
        except (OSError, TypeError, ValueError):
            return ResultadoEscritura.INCIERTO
        finally:
            if fd is not None:
                os.close(fd)
                fd = None
        try:
            replace(temporal, destino.name, fd_dir)
            temporal = None
            fsync(fd_dir)
        except (OSError, TypeError, ValueError):
            return ResultadoEscritura.INCIERTO
        return ResultadoEscritura.OK
    finally:
        if temporal is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporal, dir_fd=fd_dir)


def _abrir_directorio(directorio: Path) -> int:
    """Abre el directorio del estado sin seguir enlaces; su descriptor es el cerrojo."""
    return os.open(directorio, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _tomar_cerrojo(fd_dir: int) -> bool:
    """Toma el `flock` exclusivo del descriptor del directorio o falla cerrado.

    Bloquea hasta obtenerlo, de modo que dos escritores serializan su
    publicación (el fichero siempre es un estado completo y válido); cualquier
    error del sistema de ficheros se informa como cerrojo no tomado para que el
    llamador devuelva INCIERTO sin escribir. El cerrojo se libera al cerrar el
    descriptor, en todas las salidas.
    """
    try:
        fcntl.flock(fd_dir, fcntl.LOCK_EX)
    except OSError:
        return False
    return True


def _leer_en_directorio(
    fd_dir: int, nombre: str,
) -> tuple[ResultadoLectura, dict[str, object] | None]:
    """Lee el estado dentro del directorio ya abierto y cerrojado."""
    try:
        fd = os.open(
            nombre,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
            dir_fd=fd_dir,
        )
    except FileNotFoundError:
        return ResultadoLectura.AUSENTE, None
    except OSError:
        return ResultadoLectura.INVALIDO, None
    try:
        return _leer_fd(fd)
    finally:
        os.close(fd)


def _leer_fd(fd: int) -> tuple[ResultadoLectura, dict[str, object] | None]:
    """Garantías del lector estricto sobre un descriptor ya abierto."""
    datos = bytearray()
    try:
        antes = os.fstat(fd)
        if not stat.S_ISREG(antes.st_mode) or antes.st_size > MAX_BYTES:
            return ResultadoLectura.INVALIDO, None
        if stat.S_IMODE(antes.st_mode) & _ESCRITURA_AJENA:
            return ResultadoLectura.INVALIDO, None
        while len(datos) <= MAX_BYTES:
            bloque = os.read(fd, MAX_BYTES + 1 - len(datos))
            if not bloque:
                break
            datos.extend(bloque)
        despues = os.fstat(fd)
        if (
            len(datos) > MAX_BYTES
            or len(datos) != despues.st_size
            or (antes.st_size, antes.st_mtime_ns, antes.st_ctime_ns)
            != (despues.st_size, despues.st_mtime_ns, despues.st_ctime_ns)
        ):
            return ResultadoLectura.INVALIDO, None
    except OSError:
        return ResultadoLectura.INVALIDO, None
    try:
        obj = json.loads(
            bytes(datos).decode("utf-8"),
            object_pairs_hook=_objeto_sin_duplicados,
        )
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return ResultadoLectura.INVALIDO, None
    if type(obj) is not dict or not validar_estado(obj):
        return ResultadoLectura.INVALIDO, None
    return ResultadoLectura.OK, obj


def leer_estado_estricto(
    ruta: str | Path,
) -> tuple[ResultadoLectura, dict[str, object] | None]:
    """Lee el estado v1 o v2 sin seguir enlaces y sin abrir FIFO/dispositivos.

    Devuelve `AUSENTE` si el fichero no existe, `INVALIDO` ante cualquier
    anomalía (tipo, tamaño, permisos de escritura ajenos, JSON con claves
    duplicadas o campos fuera del contrato) y `OK` con el objeto ya validado
    por `validar_estado`, sin transformar valores. No compara épocas con el
    reloj: la detección de reloj invertido es del llamador.
    """
    try:
        fd = os.open(
            Path(ruta), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
        )
    except FileNotFoundError:
        return ResultadoLectura.AUSENTE, None
    except OSError:
        return ResultadoLectura.INVALIDO, None
    try:
        return _leer_fd(fd)
    finally:
        os.close(fd)


def _serializar(datos: dict[str, object]) -> bytes:
    texto = json.dumps(
        datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8") + b"\n"
    if len(texto) > MAX_BYTES:
        raise ValueError
    return texto


def _escribir_todo(fd: int, datos: bytes) -> None:
    vista = memoryview(datos)
    while vista:
        escritos = os.write(fd, vista)
        if escritos <= 0:
            raise OSError("escritura incompleta")
        vista = vista[escritos:]
