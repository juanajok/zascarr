# ruff: noqa: E501
"""«Hacer una copia ahora» — cliente del auxiliar del host y lectura de su estado (BL-OPS1, ADR 0021).

Lógica única (CLAUDE.md §3.1): el router solo la llama. Dos mitades:

- `pedir_copia`: construye una petición firmada (HMAC-SHA256), la envía por el socket Unix del auxiliar con un tope de
  5 s y devuelve un `CodigoOps`. Nunca lanza al router y nunca registra la clave, la firma ni el cuerpo.
- `resolver_estado` / `leer_copias`: leen SOLO los ficheros que escribe el host (`status.json`, `ops-status.json`,
  `omitida.json`, `copias.json`); no tocan la base ni el disco de la biblioteca. Lo que se pinta sale de mapas cerrados
  (`CAUSAS_COPIA`, `MENSAJES_PEDIR`): jamás una cadena libre de un fichero (C-13).

El protocolo se repite aquí y en `deploy/ops/zascarr_ops.py`; `tests/test_ops_paridad.py` los compara.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import stat
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

from zascarr.config import Settings
from zascarr.models import CodigoOps, OpsAccion
from zascarr.services.primeros_pasos import MESES

logger = structlog.get_logger()

# ── Protocolo (idéntico al del auxiliar; lo comprueba la prueba de paridad) ─────────────────────────────────────
VERSION = 1
VERSION_RESTAURAR = 2
MAX_BYTES = 1024
MAX_BYTES_V1 = 512
MAX_BYTES_RESTAURAR = 4096
CADUCIDAD_S = 120
PURGA_VISTOS_S = 300
ENTRE_COPIAS_S = 300
ENTRE_RESTAURACIONES_S = 30 * 60
LIMITE_DIARIO = 6
LIMITE_RESTAURACIONES = 3
TIEMPO_TOTAL_S = 5.0
TIEMPO_RESTAURAR_S = 20.0
RUTA_CERROJO = "/run/zascarr-ops.lock"
CLAVES_FIRMA = ("v", "id", "accion", "creada")
CLAVES_FIRMA_RESTAURAR = ("v", "id", "accion", "copia", "creada", "prueba")
_RE_COPIA = re.compile(r"backup-[0-9]{8}_[0-9]{6}")
#: Pasados estos minutos sin que la copia pedida dé señales, se deja de decir «en marcha» (FR-22).
SIN_NOTICIAS_TRAS_S = 35 * 60
#: Tope de lo que se lee de cualquiera de los ficheros de estado (son JSON de unos cientos de bytes).
MAX_FICHERO_ESTADO = 256 * 1024
MAX_COPIAS_LISTADO = 30

_RE_CLAVE = re.compile(r"[0-9a-f]{64}")
_RE_ID = re.compile(r"[0-9a-f]{32}")


def firma_de(clave: bytes, v: int, id_: str, accion: str, creada: int) -> str:
    """HMAC-SHA256(clave, "{v}|{id}|{accion}|{creada}") en hexadecimal."""
    return hmac.new(clave, f"{v}|{id_}|{accion}|{creada}".encode(), hashlib.sha256).hexdigest()


def leer_clave(ruta: str) -> bytes | None:
    """Los 32 bytes de `ops.key` (64 caracteres hexadecimales), o `None` si falta, no se puede leer o no tiene ese formato."""
    try:
        texto = Path(ruta).read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return bytes.fromhex(texto) if _RE_CLAVE.fullmatch(texto) else None


def firma_restaurar_de(clave: bytes, v: int, id_: str, copia: str, creada: int,
                        prueba: str) -> str:
    """HMAC-SHA256(clave, "{v}|{id}|restaurar|{copia}|{creada}|{prueba}")."""
    return hmac.new(
        clave,
        f"{v}|{id_}|restaurar|{copia}|{creada}|{prueba}".encode(),
        hashlib.sha256,
    ).hexdigest()


def construir_peticion_restaurar(clave: bytes, copia: str, prueba: str,
                                 ahora: int | None = None,
                                 id_: str | None = None) -> tuple[bytes, str]:
    """(línea, id) de una petición `restaurar` v2 firmada, terminada en `\n`."""
    if not _RE_COPIA.fullmatch(copia):
        raise ValueError("copia")
    id_ = id_ or secrets.token_hex(16)
    creada = int(time.time() if ahora is None else ahora)
    cuerpo = {"v": VERSION_RESTAURAR, "id": id_, "accion": OpsAccion.RESTAURAR.value,
              "copia": copia, "creada": creada, "prueba": prueba,
              "firma": firma_restaurar_de(clave, VERSION_RESTAURAR, id_, copia,
                                          creada, prueba)}
    return json.dumps(cuerpo, separators=(",", ":")).encode("ascii") + b"\n", id_


def construir_peticion(clave: bytes, ahora: int | None = None, id_: str | None = None) -> tuple[bytes, str]:
    """(línea, id) de una petición `copia` firmada, terminada en `\\n`."""
    id_ = id_ or secrets.token_hex(16)
    creada = int(time.time() if ahora is None else ahora)
    cuerpo = {"v": VERSION, "id": id_, "accion": OpsAccion.COPIA.value, "creada": creada,
              "firma": firma_de(clave, VERSION, id_, OpsAccion.COPIA.value, creada)}
    return json.dumps(cuerpo, separators=(",", ":")).encode("ascii") + b"\n", id_


def interpretar_respuesta(linea: bytes, id_enviado: str) -> CodigoOps:
    """El código de la respuesta, o `NO_DISPONIBLE` si es ilegible, de otro `id` o de un código que no está en la lista."""
    try:
        cuerpo = json.loads(linea.decode("ascii"))
        if cuerpo.get("v") not in (VERSION, VERSION_RESTAURAR) or cuerpo["id"] != id_enviado:
            return CodigoOps.NO_DISPONIBLE
        return CodigoOps(cuerpo["codigo"])
    except (UnicodeDecodeError, ValueError, KeyError, TypeError):
        return CodigoOps.NO_DISPONIBLE


async def _conversar(ruta_socket: str, peticion: bytes) -> bytes:
    lector, escritor = await asyncio.open_unix_connection(ruta_socket, limit=MAX_BYTES * 2)
    try:
        escritor.write(peticion)
        await escritor.drain()
        return await lector.readuntil(b"\n")
    finally:
        escritor.close()
        with contextlib.suppress(OSError):
            await escritor.wait_closed()


async def pedir_restaurar(settings: Settings, copia: str, prueba: str,
                          conversar=_conversar) -> CodigoOps:
    """Pide restaurar una copia propia. La contraseña viaja solo en la petición firmada;
    nunca se registra ni se devuelve. Cualquier fallo es `NO_DISPONIBLE`."""
    clave = leer_clave(settings.ops_key_file)
    if clave is None:
        logger.warning("ops.no_disponible", error="clave")
        return CodigoOps.NO_DISPONIBLE
    try:
        peticion, id_ = construir_peticion_restaurar(clave, copia, prueba)
    except ValueError:
        return CodigoOps.COPIA_DESCONOCIDA
    try:
        linea = await asyncio.wait_for(
            conversar(settings.ops_socket_file, peticion),
            timeout=TIEMPO_RESTAURAR_S,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("ops.no_disponible", error=type(exc).__name__)
        return CodigoOps.NO_DISPONIBLE
    codigo = interpretar_respuesta(linea, id_)
    logger.info("ops.restauracion_pedida", id=id_, codigo=codigo.value)
    return codigo


async def pedir_copia(settings: Settings, conversar=_conversar) -> CodigoOps:
    """Pide una copia al auxiliar. Cualquier fallo (sin socket, sin clave, tiempo, respuesta rara) es `NO_DISPONIBLE`:
    esta función no lanza al router. Registra solo `id` y `codigo`, o la clase del error."""
    clave = leer_clave(settings.ops_key_file)
    if clave is None:
        logger.warning("ops.no_disponible", error="clave")
        return CodigoOps.NO_DISPONIBLE
    peticion, id_ = construir_peticion(clave)
    try:
        linea = await asyncio.wait_for(conversar(settings.ops_socket_file, peticion), timeout=TIEMPO_TOTAL_S)
    except Exception as exc:  # noqa: BLE001 — nada de esto puede llegar al router
        logger.warning("ops.no_disponible", error=type(exc).__name__)
        return CodigoOps.NO_DISPONIBLE
    codigo = interpretar_respuesta(linea, id_)
    logger.info("ops.copia_pedida", id=id_, codigo=codigo.value)
    return codigo


def auxiliar_disponible(settings: Settings) -> bool:
    """¿Existe el socket del auxiliar y se puede escribir en él? Sin socket: «No activado en este equipo»."""
    try:
        return stat.S_ISSOCK(os.stat(settings.ops_socket_file).st_mode) and os.access(settings.ops_socket_file, os.W_OK)
    except OSError:
        return False


# ── Textos (catálogo cerrado de la especificación §9) ───────────────────────────────────────────────────────────
GENERICA = "No se sabe por qué falló. Prueba otra vez; si se repite, avisa a quien instaló ZascArr."

#: código de `status.json` → «causa → qué hacer». `status_write_failed` es RESERVADO: ningún script lo escribe.
CAUSAS_COPIA: dict[str, str] = {
    "offsite_mount_missing": "El disco de respaldo no está conectado. Conéctalo y vuelve a pedir la copia.",
    "offsite_same_device": "El disco de respaldo es el mismo que el de los datos. Avisa a quien instaló ZascArr.",
    "offsite_copy_failed": "No se pudo guardar en el disco de respaldo. Comprueba que tiene sitio y vuelve a probar.",
    "offsite_verify_failed": "La copia en el disco de respaldo no salió bien. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "anchor_sync_failed": "La copia en el disco de respaldo no salió bien. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "disk_full": "No hay sitio en el disco. Libera espacio y vuelve a pedir la copia.",
    "pg_dump_failed": "ZascArr no pudo leer sus datos. Prueba otra vez dentro de unos minutos.",
    "gzip_invalid": "La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "header_missing": "La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "tables_missing": "La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "decompress_failed": "La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "empty": "La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "not_found": "La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "verify_failed": "La copia salió mal y se descartó. Prueba otra vez; si se repite, avisa a quien instaló ZascArr.",
    "manifest_failed": "No se pudo anotar en el registro de copias. Avisa a quien instaló ZascArr.",
    "precondition_failed": "ZascArr no pudo preparar la copia. Avisa a quien instaló ZascArr.",
    "unexpected": GENERICA,
}
RESERVADOS_NO_EMITIDOS = frozenset({"status_write_failed"})

_FRASE_NO_SE_PUDO = ("No se pudo pedir la copia. Inténtalo otra vez; si sigue igual, avisa a quien instaló ZascArr. "
                     "Mira Estado, arriba.")
MENSAJES_RESTAURAR: dict[CodigoOps, str] = {
    CodigoOps.COPIA_DESCONOCIDA: "Esa copia ya no está disponible. Actualiza la lista.",
    CodigoOps.AUTENTICACION_NO_ACTIVADA: "Activa la contraseña en Ajustes → Seguridad antes de restaurar una copia.",
    CodigoOps.PRUEBA_INVALIDA: "La contraseña no es correcta.",
    CodigoOps.BLOQUEO_TEMPORAL: "Demasiados intentos seguidos. Espera unos minutos y vuelve a intentarlo.",
    CodigoOps.LIMITE_RESTAURACIONES: "Has restaurado varias veces en las últimas horas. Prueba más tarde.",
    CodigoOps.OPERACION_EN_CURSO: "ZascArr está haciendo otra tarea de mantenimiento. Espera a que termine.",
}

MENSAJES_PEDIR: dict[CodigoOps, str] = {
    CodigoOps.OPERACION_EN_CURSO: "ZascArr está haciendo otra tarea de mantenimiento. Espera a que termine.",
    CodigoOps.DEMASIADO_PRONTO: f"Acabas de pedir una copia. Prueba otra vez dentro de {ENTRE_COPIAS_S // 60} minutos.",
    CodigoOps.LIMITE_DIARIO: ("Has pedido ya el máximo de copias en un día. La de esta noche se hará igualmente; "
                              "prueba otra vez más tarde."),
    CodigoOps.COPIA_DESCONOCIDA: "Esa copia ya no está disponible. Actualiza la lista.",
    CodigoOps.AUTENTICACION_NO_ACTIVADA: ("Activa la contraseña en Ajustes → Seguridad antes de restaurar una copia."),
    CodigoOps.PRUEBA_INVALIDA: "La contraseña no es correcta.",
    CodigoOps.BLOQUEO_TEMPORAL: ("Demasiados intentos seguidos. Espera unos minutos y vuelve a intentarlo."),
    CodigoOps.LIMITE_RESTAURACIONES: ("Has restaurado varias veces en las últimas horas. Prueba más tarde."),
    **{c: _FRASE_NO_SE_PUDO for c in (CodigoOps.NO_DISPONIBLE, CodigoOps.FIRMA_INVALIDA, CodigoOps.CADUCADA,
                                      CodigoOps.REPETIDA, CodigoOps.ESQUEMA_INVALIDO, CodigoOps.ACCION_NO_DISPONIBLE,
                                      CodigoOps.COPIA_DESCONOCIDA)},
}


def causa_de(codigo: object) -> str:
    """Texto de la causa para un código de `status.json`. Lo que no sea un código conocido, la acción genérica."""
    return CAUSAS_COPIA.get(codigo, GENERICA) if isinstance(codigo, str) else GENERICA


# ── Lectura de los ficheros del host ────────────────────────────────────────────────────────────────────────────
def _leer_json(ruta: str) -> dict | None:
    try:
        with open(ruta, "rb") as f:
            datos = f.read(MAX_FICHERO_ESTADO + 1)
        if len(datos) > MAX_FICHERO_ESTADO:
            return None
        valor = json.loads(datos.decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None
    return valor if isinstance(valor, dict) else None


#: Épocas aceptadas de los ficheros del host: de 1970 al año 2100. Una cifra enorme no debe tumbar el formateo ni
#: dejar «en marcha» para siempre (SecOps F-6).
EPOCA_MAX = 4_102_444_800
TOLERANCIA_RELOJ_S = 300


def _epoch(valor: object) -> int | None:
    if isinstance(valor, int) and not isinstance(valor, bool) and 0 <= valor <= EPOCA_MAX:
        return valor
    return None


def hora_llana(epoch: int, ahora: int) -> str:
    """«hoy a las 10:35», «ayer a las 23:10» o «el 4 de noviembre a las 23:10», en la zona del SERVIDOR (`TZ`)."""
    try:
        fecha = datetime.fromtimestamp(epoch).astimezone()
        hoy = datetime.fromtimestamp(ahora).astimezone().date()
    except (OverflowError, OSError, ValueError):
        return "en una fecha que no se puede leer"
    hora = f"{fecha:%H:%M}"
    dias = (hoy - fecha.date()).days
    if dias == 0:
        return f"hoy a las {hora}"
    if dias == 1:
        return f"ayer a las {hora}"
    return f"el {fecha.day} de {MESES[fecha.month - 1]} a las {hora}"


def fecha_absoluta(epoch: int | None) -> str:
    """`dd/mm/aaaa a las HH:MM` en la zona del servidor; `None`/ilegible → «fecha no disponible»."""
    if epoch is None:
        return "fecha no disponible"
    try:
        fecha = datetime.fromtimestamp(epoch).astimezone()
    except (OverflowError, OSError, ValueError):
        return "fecha no disponible"
    return f"{fecha:%d/%m/%Y} a las {fecha:%H:%M}"


def _dia_llano(epoch: int) -> str:
    try:
        fecha = datetime.fromtimestamp(epoch).astimezone()
    except (OverflowError, OSError, ValueError):
        return "(fecha ilegible)"
    return f"{fecha.day} de {MESES[fecha.month - 1]}"


def tamano_llano(n: int) -> str:
    for unidad, base in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if n >= base:
            return f"{n / base:.1f}".replace(".", ",") + f" {unidad}"
    return f"{n} B"


class EstadoCopia:
    """Estados de la interfaz (FR-22), evaluados de arriba abajo."""

    NO_ACTIVADO = "no_activado"
    NO_ARRANCO = "no_arranco"
    EN_MARCHA = "en_marcha"
    SIN_NOTICIAS = "sin_noticias"
    HECHA = "hecha"
    CON_AVISO = "con_aviso"
    FALLO = "fallo"
    DIARIO = "diario"


@dataclass(frozen=True)
class VistaCopias:
    estado: str
    mensaje: str
    detalle: str = ""                  # la acción corta de la causa, o la línea de la copia nocturna omitida
    boton: bool = True                 # ¿hay botón?
    habilitado: bool = True
    en_marcha: bool = False
    nivel: str = ""                    # tipo de aviso de la interfaz: ok, amber, warn o vacío (texto llano)
    nocturna_omitida: str = ""
    extra: dict = field(default_factory=dict)


MSG_NO_ACTIVADO = "Hacer copias desde aquí no está activado en este equipo. Las copias de cada noche siguen funcionando."
MSG_EN_MARCHA = "Copia en marcha. Puede tardar unos minutos."
MSG_NO_ARRANCO = "No se pudo hacer la copia: había otra tarea en marcha. Vuelve a pedirla cuando termine."
MSG_SIN_NOTICIAS = ("No hay noticias de la copia. Revisa el resumen de arriba; si no dice nada, avisa a quien instaló ZascArr.")


def resolver_estado(settings: Settings, ahora: int | None = None, disponible: bool | None = None) -> VistaCopias:
    """El estado que ve la persona, según la tabla de FR-22. Solo lee ficheros; nunca pinta una cadena libre."""
    ahora = int(time.time()) if ahora is None else ahora
    if disponible is None:
        disponible = auxiliar_disponible(settings)
    if not disponible:
        return VistaCopias(EstadoCopia.NO_ACTIVADO, MSG_NO_ACTIVADO, boton=False, habilitado=False)

    estado = _leer_json(settings.backup_status_file) or {}
    ops = _leer_json(settings.ops_status_file) or {}
    # ops-status.json también lo escribe la restauración (BL-OPS2); aquí solo cuenta `copia`.
    if ops.get("accion") not in (None, "copia"):
        ops = {}
    omitida = _leer_json(settings.omitida_file) or {}
    # `omitida.json` también lo escribe la restauración (BL-OPS2, accion:"restaurar"); aquí solo cuenta la copia.
    if omitida.get("accion") not in (None, "copia"):
        omitida = {}
    pedida = _epoch(ops.get("pedida_epoch"))
    if pedida is not None and pedida > ahora + TOLERANCIA_RELOJ_S:
        pedida = None                      # una petición «del futuro» no deja la copia en marcha para siempre
    ultimo_intento = _epoch(estado.get("last_attempt_at_epoch")) or 0
    omitida_epoch = _epoch(omitida.get("omitida_epoch"))

    if pedida is not None:
        if omitida_epoch is not None and omitida_epoch >= pedida and ultimo_intento < pedida:
            return VistaCopias(EstadoCopia.NO_ARRANCO, MSG_NO_ARRANCO, nivel="amber")
        if ultimo_intento < pedida:
            if ahora - pedida <= SIN_NOTICIAS_TRAS_S:
                return VistaCopias(EstadoCopia.EN_MARCHA, MSG_EN_MARCHA, habilitado=False, en_marcha=True)
            return VistaCopias(EstadoCopia.SIN_NOTICIAS, MSG_SIN_NOTICIAS, nivel="amber")
        return _resultado(estado, pedida_hecha=True, ahora=ahora)

    vista = _resultado(estado, pedida_hecha=False, ahora=ahora)
    if omitida_epoch is not None and omitida_epoch > ultimo_intento:
        vista = VistaCopias(vista.estado, vista.mensaje, vista.detalle, nivel=vista.nivel,
                            nocturna_omitida=f"La copia de la noche del {_dia_llano(omitida_epoch)} se omitió: había otra tarea en marcha.")
    return vista


def _frase(principio: str, causa: str) -> str:
    """«<principio>. <causa>», salvo que la causa ya empiece por «La copia»: entonces va sola (no se repite)."""
    return causa if causa.startswith("La copia") else f"{principio}. {causa}"


def _resultado(estado: dict, pedida_hecha: bool, ahora: int) -> VistaCopias:
    situacion = estado.get("status")
    error = estado.get("error")
    intento = _epoch(estado.get("last_attempt_at_epoch"))
    cuando = hora_llana(intento, ahora) if intento else ""
    causa = causa_de(error)
    if situacion == "failed" and error == "manifest_failed":
        situacion = "degraded"             # la copia existe y es válida: solo falta anotarla (no es un fallo)
        causa = CAUSAS_COPIA["manifest_failed"]
    if situacion == "ok" and (pedida_hecha or intento):
        return VistaCopias(EstadoCopia.HECHA if pedida_hecha else EstadoCopia.DIARIO,
                           f"Copia hecha {cuando} y comprobada.", nivel="ok")
    if situacion == "degraded":
        if error == "manifest_failed":
            return VistaCopias(EstadoCopia.CON_AVISO if pedida_hecha else EstadoCopia.DIARIO,
                               f"Copia hecha {cuando}, con un aviso: {causa[0].lower() + causa[1:]}", nivel="amber")
        return VistaCopias(EstadoCopia.CON_AVISO if pedida_hecha else EstadoCopia.DIARIO,
                           _frase("Copia hecha, con un aviso", causa), nivel="amber")
    if situacion == "failed":
        return VistaCopias(EstadoCopia.FALLO if pedida_hecha else EstadoCopia.DIARIO,
                           _frase("La copia falló", causa), nivel="warn")
    return VistaCopias(EstadoCopia.DIARIO, "Todavía no hay ninguna copia anotada.")


_RE_HEAD = re.compile(r"^[0-9a-f]{40}$")
_RE_APP = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_RE_ALEMBIC = re.compile(r"^[0-9]{4}$")
_RE_INTENTO = re.compile(r"^[0-9a-f]{16}$")
_RE_COPIA = re.compile(r"^backup-[0-9]{8}_[0-9]{6}$")


def _version_copia(valor: object) -> dict | None:
    """Tupla de identidad del código saneada; cualquier desajuste → None («no consta»)."""
    if not isinstance(valor, dict):
        return None
    claves = ("head", "build_sha", "app_version", "alembic")
    salida: dict[str, str | None] = {}
    for clave in claves:
        dato = valor.get(clave)
        if clave in ("head", "build_sha"):
            salida[clave] = dato if isinstance(dato, str) and _RE_HEAD.fullmatch(dato) else None
        elif clave == "app_version":
            salida[clave] = dato if isinstance(dato, str) and _RE_APP.fullmatch(dato) else None
        else:
            salida[clave] = dato if isinstance(dato, str) and _RE_ALEMBIC.fullmatch(dato) else None
    return salida if any(salida.values()) else None


def version_llana(version: dict | None) -> str:
    """Texto compacto de la versión de una copia (sin hashes)."""
    if not isinstance(version, dict):
        return "Versión no consta"
    app, revision = version.get("app_version"), version.get("alembic")
    if app and revision:
        return f"Versión {app} · revisión {revision}"
    if app:
        return f"Versión {app}"
    if revision:
        return f"Revisión {revision}"
    return "Versión no consta"


def leer_copias(settings: Settings, ahora: int | None = None) -> list[dict] | None:
    """El listado de `copias.json` (hasta 30), o `None` si falta o no se puede leer. Solo pasan fecha, tamaño y si hay
    copia en el disco de respaldo: ni rutas, ni nombres, ni hashes aunque el fichero los trajera."""
    datos = _leer_json(settings.copias_file)
    if datos is None or not isinstance(datos.get("copias"), list):
        return None
    ahora = int(time.time()) if ahora is None else ahora
    salida: list[dict] = []
    for item in datos["copias"][:MAX_COPIAS_LISTADO]:
        if not isinstance(item, dict):
            continue
        creada, tamano = _epoch(item.get("creada_epoch")), _epoch(item.get("bytes"))
        if creada is None or tamano is None:
            continue
        salida.append({
            "id": item.get("id") if isinstance(item.get("id"), str) else "",
            "revision": item.get("revision") if isinstance(item.get("revision"), str) else "",
            "verificada": item.get("verificada") is True,
            "creada_epoch": creada, "fecha": hora_llana(creada, ahora),
            "fecha_absoluta": fecha_absoluta(creada),
            "version": _version_copia(item.get("version_de_la_copia")),
            "tamano": tamano_llano(tamano),
            "fuera_del_disco": item.get("fuera_del_disco") is True,
        })
    return salida


# ── BL-OPS2: estado de la restauración (FR-24/FR-25/FR-29/FR-30/FR-32) ────────────────────────────────────────
# El script `restaurar_datos.sh` es el ÚNICO escritor de `ops-restaurar.json`. Aquí solo se lee, y lo que se pinta
# sale de mapas cerrados: jamás una cadena libre del fichero (C-13). `/login` es público: su aviso no lleva fecha.
class EstadoRestaurar:
    """Estados de la restauración en la interfaz, evaluados de arriba abajo (FR-29)."""

    SIN_DATOS = "sin_datos"
    NO_ARRANCO = "no_arranco"
    EN_MARCHA = "en_marcha"
    SIN_NOTICIAS = "sin_noticias"
    HECHA = "hecha"
    FALLO = "fallo"


#: Pasados estos minutos sin que el script actualice el estado, se deja de decir «en marcha» (FR-25; la unidad
#: tiene `TimeoutStartSec=45min`).
SIN_NOTICIAS_RESTAURAR_S = 50 * 60
#: El aviso de `/login` dura una hora desde que terminó la restauración (FR-32).
AVISO_LOGIN_S = 3600
FASES_APP_SIRVIENDO = frozenset({"verificando", "preparando", "restaurando", "comprobando"})
FASES_APP_PARADA = frozenset({"parando", "seguridad", "copia_previa", "cambiando", "arrancando"})
SIN_FASE = frozenset()

MSG_REST_NO_ARRANCO = "No se pudo restaurar: había otra tarea en marcha. Vuelve a probar cuando termine."
MSG_REST_SIN_NOTICIAS = ("No hay noticias de la restauración. Si ZascArr no responde, avisa a quien instaló ZascArr.")
MSG_REST_EN_MARCHA_SIRVIENDO = "Preparando la copia del {fecha}. ZascArr sigue funcionando."
MSG_REST_EN_MARCHA_PARADA = ("Cambiando los datos. ZascArr dejará de responder unos minutos. Si no vuelve, "
                             "recarga la página. Si pasan más de 10 minutos, avisa a quien instaló ZascArr.")
MSG_REST_HECHA = ("Copia del {fecha} restaurada: {series} series, {issues} números y {files} archivos anotados. "
                  "Entra con tu contraseña de siempre.")
MSG_REST_HECHA_SIN_FECHA = ("Se restauró una copia: {series} series, {issues} números y {files} archivos anotados. "
                            "Entra con tu contraseña de siempre.")
MSG_LOGIN_RESTAURADA = "Se restauró una copia. Entra con tu contraseña de siempre."
MSG_REST_BASE_FUERA = " ZascArr podría no responder ahora mismo."
GENERICA_RESTAURAR = "No se sabe por qué falló. Si ZascArr no responde, avisa a quien instaló ZascArr."

#: `error` de §9.2 → «causa → qué hacer». Lo desconocido cae en `GENERICA_RESTAURAR` (AC-20).
CAUSAS_RESTAURAR: dict[str, str] = {
    "precondition_failed": "ZascArr no pudo preparar la restauración. No se ha cambiado nada. Avisa a quien instaló ZascArr.",
    "copia_no_encontrada": "Esa copia ya no está en el disco. Elige otra.",
    "copia_no_valida": "Esa copia está dañada, así que no se ha usado. Elige otra.",
    "revision_distinta": "Esa copia es de otra versión de ZascArr y no se puede restaurar desde aquí. Elige una más reciente.",
    "sin_espacio": "No hay sitio en el disco para restaurar. Libera espacio y vuelve a probar. No se ha cambiado nada.",
    "seguridad_ilegible": "ZascArr no pudo conservar tu configuración de acceso, así que no ha restaurado nada. Avisa a quien instaló ZascArr.",
    "seguridad_no_aplicada": "ZascArr no pudo conservar tu configuración de acceso, así que no ha restaurado nada. Avisa a quien instaló ZascArr.",
    "autenticacion_no_activada": "Activa la contraseña en Ajustes → Seguridad antes de restaurar una copia.",
    "restauracion_fallida": "La copia no se pudo cargar o no pasó las comprobaciones. Tus datos siguen como estaban. Prueba con otra copia.",
    "verificacion_fallida": "La copia no se pudo cargar o no pasó las comprobaciones. Tus datos siguen como estaban. Prueba con otra copia.",
    "copia_previa_fallida": "No se pudo guardar una copia de lo de ahora, así que no se ha restaurado nada. Comprueba que hay sitio en el disco de copias.",
    "cambio_fallido": "La restauración no salió bien y ZascArr volvió a como estaba. Avisa a quien instaló ZascArr.",
    "arranque_fallido": "La restauración no salió bien y ZascArr volvió a como estaba. Avisa a quien instaló ZascArr.",
    "recuperacion_fallida": "Se guardó una copia de lo de antes de restaurar. ZascArr no pudo volver atrás solo. Avisa a quien instaló ZascArr cuanto antes.",
    "unexpected": GENERICA_RESTAURAR,
}


def miles(n: int) -> str:
    """Separador español de miles independiente de la configuración regional del equipo (AC-49)."""
    return f"{int(n):,}".replace(",", ".")


@dataclass(frozen=True)
class VistaRestaurar:
    estado: str
    mensaje: str = ""
    detalle: str = ""
    en_marcha: bool = False
    nivel: str = ""
    base_en_su_sitio: bool | None = None
    recuentos: dict | None = None
    copia_epoch: int | None = None
    copia: str | None = None
    copia_version: dict | None = None
    recuentos_previos: dict | None = None
    version_arrancada: dict | None = None
    intento: str | None = None
    comprobacion: str | None = None
    comprobaciones: tuple[dict, ...] = ()


def _recuentos_restaurar(valor: object) -> dict | None:
    """Solo tres enteros positivos: lo que no sea eso se ignora (nunca se pinta un valor libre del fichero)."""
    if not isinstance(valor, dict):
        return None
    salida: dict[str, int] = {}
    for clave in ("series", "issues", "files"):
        n = _epoch(valor.get(clave))
        if n is None:
            return None
        salida[clave] = n
    return salida


CODS_COMPROBACION = frozenset({
    "existencia_copia", "manifiesto", "sha256_copia", "bytes_copia", "codigo_manifest",
    "gzip_cabecera", "cabecera_pg_dump", "tablas_dump", "alembic_revision",
    "recuentos_nueva", "vinculos_huerfanos", "seguridad_conservada", "copia_previa", "health",
})
ESTADOS_COMPROBACION = frozenset({"ok", "fallo", "no_ejecutada"})


def _comprobaciones(valor: object) -> tuple[dict, ...]:
    if not isinstance(valor, list):
        return ()
    salida = []
    for fila in valor[:14]:
        if not isinstance(fila, dict):
            continue
        codigo, estado = fila.get("codigo"), fila.get("estado")
        if (isinstance(codigo, str) and codigo in CODS_COMPROBACION
                and isinstance(estado, str) and estado in ESTADOS_COMPROBACION):
            salida.append({"codigo": codigo, "estado": estado})
    return tuple(salida)


def _mensaje_en_marcha(fase: object, copia_epoch: int | None) -> str:
    fecha = _dia_llano(copia_epoch) if copia_epoch is not None else "ahora"
    if isinstance(fase, str) and fase in FASES_APP_PARADA:
        return MSG_REST_EN_MARCHA_PARADA
    return MSG_REST_EN_MARCHA_SIRVIENDO.format(fecha=fecha)


def resolver_restauracion(settings: Settings, ahora: int | None = None) -> VistaRestaurar:
    """El estado de la restauración, de arriba abajo según FR-29. Solo lee ficheros del host: no sondea el
    auxiliar (si no está activado, estos ficheros no existen y el estado es `sin_datos`)."""
    ahora = int(time.time()) if ahora is None else ahora
    datos = _leer_json(settings.ops_restaurar_status_file) or {}
    resultado = datos.get("resultado")
    actualizado = _epoch(datos.get("actualizado_epoch"))
    copia_epoch = _epoch(datos.get("copia_epoch"))
    fase = datos.get("fase")
    copia = datos.get("copia")
    copia = copia if isinstance(copia, str) and _RE_COPIA.fullmatch(copia) else None
    copia_version = _version_copia(datos.get("copia_version"))
    recuentos_previos = _recuentos_restaurar(datos.get("recuentos_previos"))
    version_arrancada = _version_copia(datos.get("version_arrancada"))
    intento = datos.get("intento")
    intento = intento if isinstance(intento, str) and _RE_INTENTO.fullmatch(intento) else None
    comprobacion = datos.get("comprobacion")
    comprobacion = (comprobacion if isinstance(comprobacion, str)
                    and comprobacion in CODS_COMPROBACION else None)
    comprobaciones = _comprobaciones(datos.get("comprobaciones"))
    extras = dict(copia=copia, copia_version=copia_version,
                  recuentos_previos=recuentos_previos,
                  version_arrancada=version_arrancada, intento=intento,
                  comprobacion=comprobacion, comprobaciones=comprobaciones)
    ops = _leer_json(settings.ops_status_file) or {}
    pedida = _epoch(ops.get("pedida_epoch")) if ops.get("accion") == "restaurar" else None

    # 1) El auxiliar la aceptó pero el script no llegó a escribir fases (el cerrojo lo tenía otro proceso).
    omitida = _leer_json(settings.omitida_file) or {}
    if omitida.get("accion") == "restaurar":
        omitida_epoch = _epoch(omitida.get("omitida_epoch"))
        if omitida_epoch is not None and (actualizado is None or actualizado < omitida_epoch) \
                and (pedida is None or omitida_epoch >= pedida):
            return VistaRestaurar(EstadoRestaurar.NO_ARRANCO, MSG_REST_NO_ARRANCO,
                                  nivel="amber", copia_epoch=copia_epoch, **extras)

    if not datos:
        # Entre la aceptación del auxiliar y la primera fase del script: `ops-status.json` ya lleva la petición.
        if pedida is not None and -TOLERANCIA_RELOJ_S <= ahora - pedida <= SIN_NOTICIAS_RESTAURAR_S:
            return VistaRestaurar(EstadoRestaurar.EN_MARCHA,
                                  MSG_REST_EN_MARCHA_SIRVIENDO.format(fecha="ahora"),
                                  en_marcha=True, copia_epoch=None, **extras)
        return VistaRestaurar(EstadoRestaurar.SIN_DATOS, **extras)

    # 2) En curso y reciente / obsoleto.
    if resultado == "en_curso":
        if actualizado is not None and ahora - actualizado > SIN_NOTICIAS_RESTAURAR_S:
            return VistaRestaurar(EstadoRestaurar.SIN_NOTICIAS, MSG_REST_SIN_NOTICIAS,
                                  nivel="amber", copia_epoch=copia_epoch, **extras)
        return VistaRestaurar(EstadoRestaurar.EN_MARCHA, _mensaje_en_marcha(fase, copia_epoch),
                              en_marcha=True, copia_epoch=copia_epoch, **extras)

    # 3) Hecha, con recuentos (solo números) y fecha de la copia.
    if resultado == "hecha":
        recuentos = _recuentos_restaurar(datos.get("recuentos"))
        if recuentos is None:
            return VistaRestaurar(EstadoRestaurar.HECHA, MSG_LOGIN_RESTAURADA, nivel="ok",
                                  copia_epoch=copia_epoch, **extras)
        plantilla = MSG_REST_HECHA if copia_epoch is not None else MSG_REST_HECHA_SIN_FECHA
        mensaje = plantilla.format(fecha=_dia_llano(copia_epoch), series=miles(recuentos["series"]),
                                   issues=miles(recuentos["issues"]), files=miles(recuentos["files"]))
        return VistaRestaurar(EstadoRestaurar.HECHA, mensaje, nivel="ok", recuentos=recuentos,
                              copia_epoch=copia_epoch, **extras)

    # 4) Fallida: causa cerrada + acción; `base_en_su_sitio:false` añade el aviso de que puede no responder.
    if resultado == "fallida":
        error = datos.get("error")
        causa = CAUSAS_RESTAURAR.get(error, GENERICA_RESTAURAR) if isinstance(error, str) else GENERICA_RESTAURAR
        base = datos.get("base_en_su_sitio")
        base_en_su_sitio = base if isinstance(base, bool) else None
        mensaje = causa + (MSG_REST_BASE_FUERA if base_en_su_sitio is False else "")
        return VistaRestaurar(EstadoRestaurar.FALLO, mensaje, nivel="warn",
                              base_en_su_sitio=base_en_su_sitio, copia_epoch=copia_epoch, **extras)

    return VistaRestaurar(EstadoRestaurar.SIN_DATOS, **extras)


def aviso_de_login(settings: Settings, ahora: int | None = None) -> str | None:
    """Texto del aviso de `/login` si consta una restauración `hecha` de la última hora (FR-32). Sin fecha."""
    ahora = int(time.time()) if ahora is None else ahora
    datos = _leer_json(settings.ops_restaurar_status_file) or {}
    if datos.get("resultado") != "hecha":
        return None
    actualizado = _epoch(datos.get("actualizado_epoch"))
    if actualizado is None or actualizado > ahora + TOLERANCIA_RELOJ_S:
        return None
    if ahora - actualizado > AVISO_LOGIN_S:
        return None
    return MSG_LOGIN_RESTAURADA
