#!/usr/bin/env python3
# ruff: noqa: E501
"""
zascarr-ops — el auxiliar del host de «Hacer una copia ahora» (BL-OPS1, #443).

Lo lanza systemd por cada conexión al socket `ops.sock` (`zascarr-ops@.service`, `Accept=yes`): vive lo que dura la
conexión, no es un servicio residente. Recibe UNA línea JSON firmada con HMAC y de esquema cerrado, con una única acción
(`copia`), y solo hace una cosa: ordenar a systemd iniciar la unidad ya existente `zascarr-backup.service`. No ejecuta
scripts, no toca Docker, no lee el `.env` y no pasa nada de la petición ni de su entorno a la unidad.

Solo biblioteca estándar (el host no instala nada más; Python ≥ 3.9). `procesar` es una función pura con el estado, el
reloj y el lanzador inyectados, para probarla sin systemd (la app tiene su propio cliente en `services/ops_host.py`;
`tests/test_ops_paridad.py` comprueba que las dos mitades no divergen).

Orden de comprobación (FR-04), parando en el primer fallo, para que quien no sabe firmar no averigüe nada del estado:
    esquema → firma → caducidad → repetición → acción → frecuencia → cerrojo
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import hashlib
import hmac
import json
import os
import re
import select
import socket
import stat
import struct
import subprocess
import sys
import time

# ── Protocolo (la app lo repite en `services/ops_host.py`; la prueba de paridad los compara) ─────────────────────
VERSION = 1
VERSION_RESTAURAR = 2
ACCION_COPIA = "copia"
ACCION_RESTAURAR = "restaurar"
#: La tabla acción → unidad vive AQUÍ, en el código: ni en la petición, ni en `/etc/default/zascarr`, ni en el entorno.
UNIDADES = {
    ACCION_COPIA: "zascarr-backup.service",
    ACCION_RESTAURAR: "zascarr-restaurar@.service",
}
CODIGOS = (
    "aceptada", "esquema_invalido", "firma_invalida", "caducada", "repetida", "accion_no_disponible",
    "demasiado_pronto", "limite_diario", "operacion_en_curso", "no_disponible",
    "copia_desconocida", "autenticacion_no_activada", "prueba_invalida", "bloqueo_temporal",
    "limite_restauraciones",
)
CLAVES_PETICION = ("v", "id", "accion", "creada", "firma")
CLAVES_PETICION_RESTAURAR = ("v", "id", "accion", "copia", "prueba", "creada", "firma")
MAX_BYTES = 512
MAX_BYTES_V1 = 512
MAX_BYTES_RESTAURAR = 4096
LEER_MAX = MAX_BYTES_RESTAURAR + 1
RESTAURACION_ESPERA_S = 30 * 60
LIMITE_RESTAURACIONES = 3
VENTANA_RESTAURACIONES_S = 24 * 3600
UMBRAL_FALLOS = 5
VENTANA_FALLOS_S = 15 * 60
BLOQUEO_FALLOS_S = 30 * 60
BLOQUEO_ESPERA_RESTAURAR_S = 12
RUTA_COPIAS = "/var/backups/zascarr/postgres"
RE_COPIA = re.compile(r"backup-[0-9]{8}_[0-9]{6}")
RE_TS = re.compile(r"[0-9]{8}_[0-9]{6}")
TIEMPO_LECTURA_S = 5             # y espera la línea como mucho esto
CADUCIDAD_S = 120                # |creada − reloj del host| máximo, en los dos sentidos
PURGA_VISTOS_S = 300             # un `id` visto se recuerda 300 s (la caducidad es ±120: un `id` válido vive hasta 240)
ENTRE_COPIAS_S = 300             # intervalo mínimo entre dos copias aceptadas
BLOQUEO_ESPERA_S = 5            # espera máxima por el bloqueo de `aceptadas`
LIMITE_DIARIO = 6                # copias aceptadas en 24 h (ventana móvil)
VENTANA_S = 24 * 3600
TOLERANCIA_RELOJ_S = 300         # una época anotada hasta 300 s en el futuro se acepta (la Pi puede corregir la hora)
#: Ruta CONSTANTE del cerrojo único de operaciones (la misma que `scripts/_cerrojo.sh`; una prueba las compara).
RUTA_CERROJO = "/run/zascarr-ops.lock"
PATH_FIJO = "/usr/sbin:/usr/bin:/sbin:/bin"
#: `systemctl is-active`: libre = se puede iniciar (una copia fallida deja la unidad `failed`: F-3); ocupada = en marcha.
#: Cualquier otra salida (vacía, de varias palabras, `maintenance`…) ⇒ falla cerrado (`estado_unidad_desconocido`).
ESTADOS_LIBRES = frozenset({"inactive", "failed"})
ESTADOS_OCUPADOS = frozenset({"activating", "active", "reloading", "deactivating"})
TIEMPO_SYSTEMCTL_S = 5

_RE_ID = re.compile(r"[0-9a-f]{32}")
_RE_FIRMA = re.compile(r"[0-9a-f]{64}")
_RE_CLAVE = re.compile(r"[0-9a-f]{64}")


# ── Respuesta ───────────────────────────────────────────────────────────────────────────────────────────────────
class Respuesta:
    """`resultado` es `aceptada` o `rechazada`; `codigo` es de la lista cerrada. Nunca lleva texto libre ni rutas."""

    def __init__(self, resultado: str, codigo: str, id_: str | None = None, accion: str | None = None,
                 diario: str | None = None, v: int = 1, copia: str | None = None) -> None:
        self.resultado = resultado
        self.codigo = codigo
        self.id = id_
        self.accion = accion
        #: Código EXTRA solo para el diario (`clave_ausente`, `contador_ilegible`…): no sale por el socket.
        self.diario = diario
        self.v = v
        self.copia = copia

    def linea(self) -> bytes:
        cuerpo = {"v": self.v, "id": self.id, "resultado": self.resultado, "codigo": self.codigo}
        return json.dumps(cuerpo, separators=(",", ":")).encode("ascii") + b"\n"


def _rechazo(codigo: str, id_: str | None = None, accion: str | None = None,
             diario: str | None = None, v: int = 1) -> Respuesta:
    return Respuesta("rechazada", codigo, id_, accion, diario, v=v)


# ── Firma ───────────────────────────────────────────────────────────────────────────────────────────────────────
def firma_de(clave: bytes, v: int, id_: str, accion: str, creada: int,
             copia: str = "", prueba: str = "") -> str:
    """HMAC-SHA256. v1: "{v}|{id}|{accion}|{creada}"; v2 añade copia y prueba al final."""
    if v == VERSION_RESTAURAR:
        texto = f"2|{id_}|restaurar|{copia}|{creada}|{prueba}"
    else:
        texto = f"{v}|{id_}|{accion}|{creada}"
    return hmac.new(clave, texto.encode(), hashlib.sha256).hexdigest()


# ── Esquema ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _sin_duplicados(pares):
    claves = [k for k, _ in pares]
    if len(claves) != len(set(claves)):
        raise ValueError("clave repetida")
    return dict(pares)


def _es_entero(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


def parsear(linea: bytes) -> dict | None:
    """Petición validada, o `None`. v1 ≤512 B; v2 ≤1024 B y admite solo `restaurar`."""
    if not isinstance(linea, (bytes, bytearray)) or len(linea) > LEER_MAX:
        return None
    linea = bytes(linea)
    if not linea.endswith(b"\n") or linea.count(b"\n") != 1:
        return None
    try:
        objeto = json.loads(linea[:-1].decode("utf-8"), object_pairs_hook=_sin_duplicados)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    if not isinstance(objeto, dict):
        return None
    v = objeto.get("v")
    if v == VERSION:
        if len(linea) > MAX_BYTES_V1 or set(objeto) != set(CLAVES_PETICION):
            return None
        return _validar_v1(objeto)
    if v == VERSION_RESTAURAR:
        if len(linea) > MAX_BYTES_RESTAURAR or set(objeto) != set(CLAVES_PETICION_RESTAURAR):
            return None
        return _validar_v2(objeto)
    return None


def _validar_v1(objeto: dict) -> dict | None:
    if not _es_entero(objeto["v"]) or objeto["v"] != VERSION:
        return None
    if not isinstance(objeto["id"], str) or not _RE_ID.fullmatch(objeto["id"]):
        return None
    if not isinstance(objeto["accion"], str):
        return None
    try:
        objeto["accion"].encode("utf-8")
    except UnicodeEncodeError:
        return None
    if not _es_entero(objeto["creada"]):
        return None
    if not isinstance(objeto["firma"], str) or not _RE_FIRMA.fullmatch(objeto["firma"]):
        return None
    return objeto


def _validar_v2(objeto: dict) -> dict | None:
    if not _es_entero(objeto["v"]) or objeto["v"] != VERSION_RESTAURAR:
        return None
    if not isinstance(objeto["id"], str) or not _RE_ID.fullmatch(objeto["id"]):
        return None
    if objeto["accion"] != ACCION_RESTAURAR:
        return None
    if not isinstance(objeto["copia"], str) or not RE_COPIA.fullmatch(objeto["copia"]):
        return None
    prueba = objeto["prueba"]
    if not isinstance(prueba, str):
        return None
    try:
        prueba.encode("utf-8")
    except UnicodeEncodeError:
        return None
    if not 1 <= len(prueba.encode("utf-8")) <= 512:
        return None
    if not _es_entero(objeto["creada"]):
        return None
    if not isinstance(objeto["firma"], str) or not _RE_FIRMA.fullmatch(objeto["firma"]):
        return None
    return objeto


# ── Estado en /run (tmpfs: un reinicio lo vacía y no puede quedar ninguna orden pendiente) ─────────────────────
class AceptacionOcupada(OSError):  # noqa: N818
    """No se tomó `aceptacion.lock` en el tiempo máximo (FR-35): otro proceso está en la sección crítica."""


class ContadorIlegible(Exception):  # noqa: N818
    """`aceptadas` existe pero no se puede leer o interpretar: el auxiliar falla cerrado (nunca lo reinicia a 0)."""


class EstadoOps:
    """`dir_estado` es `/run/zascarr-ops` (root `0700`): `vistos/<id>` y `aceptadas`. `dir_status` es el directorio de
    estado que la app lee (`:ro`), donde solo escribe root."""

    def __init__(self, dir_estado: str, dir_status: str) -> None:
        self.dir_estado = dir_estado
        self.dir_status = dir_status
        self.dir_vistos = os.path.join(dir_estado, "vistos")
        self.ruta_aceptadas = os.path.join(dir_estado, "aceptadas")
        self.ruta_restauradas = os.path.join(dir_estado, "restauradas")
        self.ruta_pruebas = os.path.join(dir_estado, "pruebas")
        self.ruta_ops_status = os.path.join(dir_status, "ops-status.json")

    # un solo uso (FR-06)
    def purgar_vistos(self, ahora: int) -> None:
        try:
            nombres = os.listdir(self.dir_vistos)
        except OSError:
            return
        for nombre in nombres:
            ruta = os.path.join(self.dir_vistos, nombre)
            try:
                with open(ruta, encoding="ascii") as fh:
                    anotado = int(fh.read().strip())
            except (OSError, ValueError):
                anotado = 0
            if ahora - anotado > PURGA_VISTOS_S:
                with contextlib.suppress(OSError):
                    os.unlink(ruta)

    def marcar_visto(self, id_: str, ahora: int) -> bool:
        """`True` si el `id` es nuevo (se anota con `O_EXCL`); `False` si ya estaba visto. Otro error de disco falla
        cerrado (la excepción sube a quien llama, que responde `no_disponible`)."""
        os.makedirs(self.dir_vistos, mode=0o700, exist_ok=True)
        try:
            fd = os.open(os.path.join(self.dir_vistos, id_), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="ascii") as fh:
            fh.write(str(ahora))
        return True

    # frecuencia (FR-10)
    def leer_aceptadas(self, ahora: int) -> list:
        """Las épocas de las copias aceptadas. Ausente ⇒ vacío (primer uso o reinicio). Existe pero ilegible, de tipos
        erróneos o con épocas más allá de la tolerancia de reloj en el futuro ⇒ `ContadorIlegible`."""
        try:
            with open(self.ruta_aceptadas, encoding="ascii") as fh:
                bruto = fh.read()
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError) as exc:
            raise ContadorIlegible from exc
        try:
            datos = json.loads(bruto)
        except ValueError as exc:
            raise ContadorIlegible from exc
        if not isinstance(datos, list) or not all(_es_entero(t) for t in datos):
            raise ContadorIlegible
        if any(t > ahora + TOLERANCIA_RELOJ_S for t in datos):
            raise ContadorIlegible
        return list(datos)

    def anotar_aceptada(self, ahora: int, previas: list) -> None:
        vigentes = [t for t in previas if ahora - t < VENTANA_S]
        self._escribir_atomico(self.ruta_aceptadas, json.dumps(vigentes + [ahora]), 0o600)

    def _leer_epocas(self, ruta: str, ahora: int) -> list:
        """El reloj entra por parámetro (como en el resto del auxiliar): así el bloqueo y los topes se pueden
        probar con un reloj inyectado. En producción `ahora` es `time.time()`."""
        try:
            with open(ruta, encoding="ascii") as fh:
                datos = json.loads(fh.read())
        except FileNotFoundError:
            return []
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ContadorIlegible from exc
        if not isinstance(datos, list) or not all(_es_entero(t) for t in datos):
            raise ContadorIlegible
        if any(t > ahora + TOLERANCIA_RELOJ_S for t in datos):
            raise ContadorIlegible
        return list(datos)

    def leer_restauradas(self, ahora: int) -> list:
        try:
            return [t for t in self._leer_epocas(self.ruta_restauradas, ahora)
                    if t <= ahora + TOLERANCIA_RELOJ_S]
        except ContadorIlegible:
            raise

    def anotar_restaurada(self, ahora: int, previas: list) -> None:
        vigentes = [t for t in previas if ahora - t < VENTANA_RESTAURACIONES_S]
        self._escribir_atomico(self.ruta_restauradas, json.dumps(vigentes + [ahora]), 0o600)

    def leer_fallos(self, ahora: int) -> list:
        return self._leer_epocas(self.ruta_pruebas, ahora)

    def anotar_fallo(self, ahora: int, previos: list) -> None:
        vigentes = [t for t in previos if ahora - t < VENTANA_FALLOS_S]
        self._escribir_atomico(self.ruta_pruebas, json.dumps(vigentes + [ahora]), 0o600)

    def limpiar_fallos(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.ruta_pruebas)

    def escribir_ops_status_restaurar(self, id_: str, pedida_epoch: int, copia: str) -> None:
        cuerpo = {"schema": 1, "accion": ACCION_RESTAURAR, "id": id_,
                  "pedida_epoch": pedida_epoch, "copia": copia, "resultado": "aceptada"}
        self._escribir_atomico(self.ruta_ops_status, json.dumps(cuerpo), 0o644)

    # lo que la app lee (FR-15): SOLO una petición aceptada escribe aquí
    def escribir_ops_status(self, id_: str, pedida_epoch: int) -> None:
        cuerpo = {"schema": 1, "accion": ACCION_COPIA, "id": id_, "pedida_epoch": pedida_epoch,
                  "resultado": "aceptada"}
        self._escribir_atomico(self.ruta_ops_status, json.dumps(cuerpo), 0o644)

    @contextlib.contextmanager
    def bloqueo(self, espera_s: float = BLOQUEO_ESPERA_S):
        """Exclusión mutua entre procesos del auxiliar (`Accept=yes` lanza uno por conexión) desde que se lee
        `aceptadas` hasta que se escribe `ops-status.json`: sin esto, cuatro firmas válidas a la vez se aceptan las
        cuatro y el contador pierde actualizaciones (F-5). `OSError` si no se puede abrir o no llega a tomarse."""
        fd = os.open(os.path.join(self.dir_estado, "aceptacion.lock"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            limite = time.monotonic() + espera_s
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EWOULDBLOCK, errno.EAGAIN):
                        raise
                    if time.monotonic() >= limite:
                        raise AceptacionOcupada from exc
                    time.sleep(0.02)
            yield
        finally:
            os.close(fd)                                   # cerrar el descriptor suelta el flock

    @staticmethod
    def _escribir_atomico(destino: str, texto: str, modo: int) -> None:
        temporal = f"{destino}.tmp.{os.getpid()}"
        fd = os.open(temporal, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, modo)
        try:
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(texto)
            os.chmod(temporal, modo)
            os.replace(temporal, destino)          # mismo directorio: atómico
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(temporal)
            raise


# ── Lanzador (lo único que toca el sistema; se inyecta en las pruebas) ─────────────────────────────────────────
class LanzadorSystemd:
    """Pregunta por el cerrojo y por la unidad, y ordena a systemd iniciarla. Argumentos fijos, sin shell, entorno vacío
    salvo un `PATH` fijo (FR-09): nada de la petición ni del entorno del auxiliar llega a la unidad."""

    def __init__(self, ejecutar=subprocess.run, ruta_cerrojo: str = RUTA_CERROJO) -> None:
        self.ejecutar = ejecutar
        self.ruta_cerrojo = ruta_cerrojo

    def cerrojo_ocupado(self) -> bool:
        """Comprueba SIN crear ni bloquear: `open` de solo lectura sin `O_CREAT`, `flock` no bloqueante y soltar al
        instante; `ENOENT` significa «libre». La autoridad es el cerrojo que toma el script: esto solo evita mentir."""
        try:
            fd = os.open(self.ruta_cerrojo, os.O_RDONLY)
        except FileNotFoundError:
            return False
        except OSError:
            return True                                    # no se puede mirar: se trata como ocupado (falla cerrado)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                return exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN) or True
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        finally:
            os.close(fd)

    def estado_unidad(self, unidad: str) -> str:
        """La SALIDA de `systemctl is-active` (no su código: una unidad `failed` sale con código 3). Con descriptores
        acotados (FR-09, O18) y tiempo máximo de 5 s; `TimeoutExpired`/`OSError` suben a quien llama."""
        resultado = self.ejecutar(["systemctl", "is-active", unidad], env={"PATH": PATH_FIJO}, stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=TIEMPO_SYSTEMCTL_S,
                                  check=False, close_fds=True)
        return resultado.stdout.strip()

    def restauraciones_ocupadas(self) -> bool:
        resultado = self.ejecutar(
            ["systemctl", "list-units", "--plain", "--no-legend",
             "--state=activating,active", "zascarr-restaurar@*.service"],
            env={"PATH": PATH_FIJO}, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=TIEMPO_SYSTEMCTL_S, check=False, close_fds=True,
        )
        return bool(resultado.stdout.strip())

    def iniciar(self, unidad: str) -> bool:
        resultado = self.ejecutar(["systemctl", "start", "--no-block", unidad], env={"PATH": PATH_FIJO},
                                  stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                  timeout=TIEMPO_SYSTEMCTL_S, check=False, close_fds=True)
        return resultado.returncode == 0


def _verificar_regular_root(ruta: str) -> bool:
    try:
        st = os.lstat(ruta)
    except OSError:
        return False
    return (stat.S_ISREG(st.st_mode) and st.st_uid == 0
            and not (st.st_mode & (stat.S_IWGRP | stat.S_IWOTH)))


def listar_copias(dir_backup: str, maximo: int = 30) -> list[str]:
    """Ids `backup-AAAA...` de copias propias y manifiesto válido, de la más nueva a la más vieja."""
    import glob
    import json as _json
    validas = []
    for ruta in glob.glob(os.path.join(dir_backup, "backup_[0-9]*.sql.gz")):
        nombre = os.path.basename(ruta)
        m = re.fullmatch(r"backup_([0-9]{8}_[0-9]{6})\.sql\.gz", nombre)
        if not m:
            continue
        if not _verificar_regular_root(ruta):
            continue
        manifiesto = os.path.join(dir_backup, f"MANIFIESTO-backup_{m.group(1)}.json")
        if not _verificar_regular_root(manifiesto):
            continue
        try:
            with open(manifiesto, "rb") as fh:
                datos = _json.loads(fh.read(4097).decode("utf-8"))
            if not isinstance(datos, dict):
                continue
            # F-21: tipos ESTRICTOS (`true` no es un entero válido). El script revalida el dump después; esto
            # solo evita ofrecer como restaurable lo que ni siquiera tiene un manifiesto coherente.
            schema = datos.get("schema", 1)
            if schema is not None and (not _es_entero(schema) or schema != 1):
                continue
            if not isinstance(datos.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", datos["sha256"]):
                continue
            if not _es_entero(datos.get("bytes")) or datos["bytes"] < 0:
                continue
        except (OSError, ValueError):
            continue
        validas.append(f"backup-{m.group(1)}")
    return sorted(validas, reverse=True)[:maximo]


class VerificadorPrueba:
    """Lee `auth_mode`/hash de la BD viva con una orden fija y compara PBKDF2 en memoria."""

    CONSULTA = (
        "select coalesce((select values->>'auth_mode' from runtime_settings where id=1),'')"
        "||'|'||coalesce((select values->>'auth_password_hash' from runtime_settings where id=1),'')"
    )

    def __init__(self, ejecutar=subprocess.run, db_user: str | None = None,
                 db_name: str | None = None) -> None:
        self.ejecutar = ejecutar
        self.db_user = db_user or os.environ.get("DB_USER", "comics_admin")
        self.db_name = db_name or os.environ.get("DB_NAME", "zascarr")
        self.argv = [
            "/usr/bin/docker", "exec", "zascarr-db", "psql",
            "-U", self.db_user, "-d", self.db_name, "-At",
            "-v", "ON_ERROR_STOP=1", "-c", self.CONSULTA,
        ]

    def leer(self) -> tuple[str, str] | None:
        try:
            resultado = self.ejecutar(
                self.argv,
                env={"PATH": PATH_FIJO, "DOCKER_CONFIG": "/run/zascarr-ops/docker"},
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=8, check=False, close_fds=True,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if resultado.returncode != 0 or len(resultado.stdout or b"") > 4096:
            return None
        try:
            modo, _, hash_ = resultado.stdout.decode("utf-8").strip().partition("|")
        except UnicodeDecodeError:
            return None
        return modo, hash_

    @staticmethod
    def comprobar(prueba: str, almacenado: str) -> bool:
        try:
            partes = almacenado.split("$")
            if len(partes) != 4 or partes[0] != "pbkdf2_sha256":
                return False
            iteraciones = int(partes[1])
            if not 10_000 <= iteraciones <= 2_000_000:
                return False
            sal = bytes.fromhex(partes[2])
            esperado = bytes.fromhex(partes[3])
            obtenido = hashlib.pbkdf2_hmac("sha256", prueba.encode("utf-8"), sal, iteraciones)
        except (ValueError, UnicodeError):
            return False
        return hmac.compare_digest(obtenido, esperado)


# ── El núcleo ───────────────────────────────────────────────────────────────────────────────────────────────────
def procesar(linea: bytes, ahora: int, clave: bytes | None, estado: EstadoOps, lanzador,
             verificador=None, copias=None, dir_backup: str | None = None) -> Respuesta:
    """Valida y, si procede, acepta una petición. Todo lo que toca el mundo (reloj, estado, systemd) entra por
    parámetro. Devuelve siempre una `Respuesta`; no lanza excepciones por una petición mala."""
    peticion = parsear(linea)
    if clave is None:
        # sin clave el auxiliar contesta no_disponible a todo y lo dice en el diario con un código genérico
        return _rechazo("no_disponible", peticion["id"] if peticion else None,
                        diario="clave_ausente", v=peticion["v"] if peticion else 1)
    if peticion is None:
        return _rechazo("esquema_invalido")
    id_ = peticion["id"]
    accion = peticion["accion"]

    esperada = firma_de(clave, peticion["v"], id_, accion, peticion["creada"],
                        peticion.get("copia", ""), peticion.get("prueba", ""))
    if not hmac.compare_digest(esperada, peticion["firma"]):
        return _rechazo("firma_invalida", id_)
    if abs(peticion["creada"] - ahora) > CADUCIDAD_S:
        return _rechazo("caducada", id_)

    try:
        estado.purgar_vistos(ahora)
        if not estado.marcar_visto(id_, ahora):
            return _rechazo("repetida", id_)
    except OSError:
        return _rechazo("no_disponible", id_, diario="vistos_ilegible")

    if peticion["v"] == VERSION_RESTAURAR:
        respuesta = _procesar_restaurar(peticion, ahora, estado, lanzador,
                                         verificador or VerificadorPrueba(),
                                         copias if copias is not None else listar_copias(
                                             dir_backup or os.environ.get("BACKUP_DIR")
                                             or os.environ.get("ZASCARR_BACKUP_DIR", RUTA_COPIAS)))
        respuesta.copia = peticion["copia"]
        return respuesta
    if accion != ACCION_COPIA:
        return _rechazo("accion_no_disponible", id_)
    unidad = UNIDADES[accion]

    try:
        with estado.bloqueo():
            return _aceptar(id_, unidad, ahora, estado, lanzador)
    except AceptacionOcupada:
        return _rechazo("no_disponible", id_, ACCION_COPIA, diario="aceptacion_ocupada")
    except OSError:
        return _rechazo("no_disponible", id_, ACCION_COPIA, diario="bloqueo_no_disponible")


def _procesar_restaurar(peticion: dict, ahora: int, estado: EstadoOps, lanzador,
                        verificador, copias) -> Respuesta:
    """v2: copia propia, límites, cerrojo, fallos, contraseña y arranque de la unidad."""
    id_ = peticion["id"]
    copia = peticion["copia"]
    accion = ACCION_RESTAURAR

    def _r(resp):
        resp.copia = copia
        return resp

    if copia not in copias:
        return _rechazo("copia_desconocida", id_, accion, v=VERSION_RESTAURAR)
    try:
        with estado.bloqueo(BLOQUEO_ESPERA_RESTAURAR_S):
            restauradas = estado.leer_restauradas(ahora)
            if restauradas and ahora - max(restauradas) < RESTAURACION_ESPERA_S:
                return _rechazo("demasiado_pronto", id_, accion, v=VERSION_RESTAURAR)
            if sum(1 for t in restauradas if ahora - t < VENTANA_RESTAURACIONES_S) >= LIMITE_RESTAURACIONES:
                return _rechazo("limite_restauraciones", id_, accion, v=VERSION_RESTAURAR)
            if lanzador.cerrojo_ocupado():
                return _rechazo("operacion_en_curso", id_, accion, v=VERSION_RESTAURAR)
            try:
                if (lanzador.estado_unidad(UNIDADES[ACCION_COPIA]).strip() in ESTADOS_OCUPADOS
                        or lanzador.restauraciones_ocupadas()):
                    return _rechazo("operacion_en_curso", id_, accion, v=VERSION_RESTAURAR)
            except (OSError, subprocess.SubprocessError):
                return _rechazo("no_disponible", id_, accion, diario="systemctl_fallo", v=VERSION_RESTAURAR)
            try:
                fallos = estado.leer_fallos(ahora)
            except ContadorIlegible:
                return _rechazo("no_disponible", id_, accion, diario="contador_ilegible", v=VERSION_RESTAURAR)
            # FR-13: el fichero solo conserva los fallos de los últimos 15 min de la última escritura, así que
            # «5 fallos en 15 min» es `len(fallos) >= UMBRAL_FALLOS`; el bloqueo dura 30 min desde el ÚLTIMO
            # fallo (F-08: antes se reutilizaba la ventana de 15 min y el bloqueo efectivo era más corto).
            if len(fallos) >= UMBRAL_FALLOS and ahora < max(fallos) + BLOQUEO_FALLOS_S:
                return _rechazo("bloqueo_temporal", id_, accion, v=VERSION_RESTAURAR)
            leido = verificador.leer()
            if leido is None:
                return _rechazo("no_disponible", id_, accion, diario="hash_ilegible", v=VERSION_RESTAURAR)
            modo, hash_ = leido
            if modo not in ("password", "user_password"):
                return _rechazo("autenticacion_no_activada", id_, accion, v=VERSION_RESTAURAR)
            if not verificador.comprobar(peticion["prueba"], hash_):
                with contextlib.suppress(OSError):
                    estado.anotar_fallo(ahora, fallos)
                return _rechazo("prueba_invalida", id_, accion, v=VERSION_RESTAURAR)
            ts = copia.split("-", 1)[1]
            unidad = UNIDADES[ACCION_RESTAURAR].replace("@.service", f"@{ts}.service")
            try:
                if not lanzador.iniciar(unidad):
                    return _rechazo("no_disponible", id_, accion, diario="inicio_fallido", v=VERSION_RESTAURAR)
                estado.anotar_restaurada(ahora, restauradas)
                estado.escribir_ops_status_restaurar(id_, ahora, copia)
                estado.limpiar_fallos()
            except OSError:
                return Respuesta("aceptada", "aceptada", id_, accion, diario="estado_no_escrito",
                                 v=VERSION_RESTAURAR)
            return Respuesta("aceptada", "aceptada", id_, accion, v=VERSION_RESTAURAR)
    except AceptacionOcupada:
        return _rechazo("operacion_en_curso", id_, accion, v=VERSION_RESTAURAR)
    except OSError:
        return _rechazo("no_disponible", id_, accion, diario="bloqueo_no_disponible", v=VERSION_RESTAURAR)


def _aceptar(id_: str, unidad: str, ahora: int, estado: EstadoOps, lanzador) -> Respuesta:
    """Frecuencia, tope, cerrojo y arranque, con el bloqueo de `aceptadas` tomado (F-5)."""
    try:
        aceptadas = estado.leer_aceptadas(ahora)
    except ContadorIlegible:
        # falla cerrado: nunca se reinicia a 0 ni se reescribe
        return _rechazo("no_disponible", id_, ACCION_COPIA, diario="contador_ilegible")
    if aceptadas and ahora - max(aceptadas) < ENTRE_COPIAS_S:
        return _rechazo("demasiado_pronto", id_, ACCION_COPIA)
    if sum(1 for t in aceptadas if ahora - t < VENTANA_S) >= LIMITE_DIARIO:
        return _rechazo("limite_diario", id_, ACCION_COPIA)

    try:
        if lanzador.cerrojo_ocupado():
            return _rechazo("operacion_en_curso", id_, ACCION_COPIA)
        situacion = lanzador.estado_unidad(unidad)
    except (OSError, subprocess.SubprocessError):
        return _rechazo("no_disponible", id_, ACCION_COPIA, diario="systemctl_fallo")
    if situacion in ESTADOS_OCUPADOS:
        return _rechazo("operacion_en_curso", id_, ACCION_COPIA)
    if situacion not in ESTADOS_LIBRES:
        return _rechazo("no_disponible", id_, ACCION_COPIA, diario="estado_unidad_desconocido")

    # El `start` va ANTES de anotar: un fallo al iniciar no consume el intento (reembolso, FR-10).
    try:
        iniciada = lanzador.iniciar(unidad)
    except (OSError, subprocess.SubprocessError):
        return _rechazo("no_disponible", id_, ACCION_COPIA, diario="systemctl_fallo")
    if not iniciada:
        return _rechazo("no_disponible", id_, ACCION_COPIA, diario="inicio_fallido")
    try:
        estado.anotar_aceptada(ahora, aceptadas)
        estado.escribir_ops_status(id_, ahora)
    except OSError:
        # la copia ya se ha iniciado: se acepta; la app caerá en «sin noticias» si no ve el rastro
        return Respuesta("aceptada", "aceptada", id_, ACCION_COPIA, diario="estado_no_escrito")
    return Respuesta("aceptada", "aceptada", id_, ACCION_COPIA)


# ── Entrada/salida (el mínimo: lo que no se puede probar sin un socket) ────────────────────────────────────────
def leer_clave(ruta: str) -> bytes | None:
    """Los 32 bytes de la clave, o `None` si falta o no son exactamente 64 caracteres hexadecimales."""
    try:
        with open(ruta, encoding="ascii") as fh:
            texto = fh.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return bytes.fromhex(texto) if _RE_CLAVE.fullmatch(texto) else None


def leer_linea(fd: int, tiempo_s: float = TIEMPO_LECTURA_S) -> bytes:
    """Lee de `fd` hasta el primer `\\n`, `LEER_MAX` bytes o el final del tiempo (o de la conexión): NUNCA más de 513
    bytes. Lo que sobre del límite lo rechaza `parsear`."""
    limite = time.monotonic() + tiempo_s
    buffer = b""
    while len(buffer) < LEER_MAX and b"\n" not in buffer:
        restante = limite - time.monotonic()
        if restante <= 0:
            break
        listo, _, _ = select.select([fd], [], [], restante)
        if not listo:
            break
        trozo = os.read(fd, LEER_MAX - len(buffer))
        if not trozo:
            break
        buffer += trozo
    return buffer


def uid_del_par(fd: int) -> int:
    """El UID del otro extremo (SO_PEERCRED), o -1 si no se puede saber."""
    try:
        conexion = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            _pid, uid, _gid = struct.unpack("3i", conexion.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                                                      struct.calcsize("3i")))
        finally:
            conexion.close()
        return uid
    except (OSError, struct.error, AttributeError):
        return -1


def linea_de_diario(respuesta: Respuesta, uid: int, ms: int) -> str:
    """Una línea por conexión (FR-30): `accion=… id=… uid=… resultado=… codigo=… ms=…`. Nunca el cuerpo, la firma, la
    clave ni rutas; `accion` solo si es la única conocida (no se vuelca una cadena del atacante) y `codigo` incluye el
    código extra del diario si lo hay."""
    codigo = respuesta.diario or respuesta.codigo
    return (f"accion={respuesta.accion if respuesta.accion in (ACCION_COPIA, ACCION_RESTAURAR) else '-'} "
            f"copia={respuesta.copia or '-'} id={respuesta.id or '-'} uid={uid} "
            f"resultado={respuesta.resultado} codigo={codigo} ms={ms}")


def main() -> int:
    inicio = time.monotonic()
    dir_ops = os.environ.get("ZASCARR_OPS_DIR", "/var/lib/zascarr/ops")
    dir_status = os.environ.get("ZASCARR_BACKUP_STATUS_DIR", "/var/lib/zascarr/backup-status")
    estado = EstadoOps("/run/zascarr-ops", dir_status)
    clave = leer_clave(os.path.join(dir_ops, "ops.key"))
    linea = leer_linea(0)
    try:
        respuesta = procesar(linea, int(time.time()), clave, estado, LanzadorSystemd())
    except Exception as exc:  # noqa: BLE001 — ninguna petición puede matar al auxiliar sin respuesta (F-4)
        # al diario, solo la clase del error: nunca el contenido de la petición ni un traceback que lo lleve
        respuesta = _rechazo("no_disponible", diario=f"error_interno_{type(exc).__name__}")
    with contextlib.suppress(OSError):
        os.write(1, respuesta.linea())
    ms = int((time.monotonic() - inicio) * 1000)
    print(linea_de_diario(respuesta, uid_del_par(0), ms), file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
