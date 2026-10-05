# ruff: noqa: E501
"""Asignar UN archivo a una serie y número de forma RECUPERABLE (ADR 0006, migración 0017).

El orden, cada paso con su razón:

    preparar (commit) → copiar y verificar → publicar → confirmar (commit) → retirar el origen → limpiar

Una asignación interrumpida (muerte del proceso, caída de la conexión, `commit` de resultado desconocido) se
reconcilia SIN escanear la biblioteca: lo necesario vive en `asignacion_operaciones`. Cada decisión está
demostrada con Postgres y ficheros reales en `tests/test_asignacion_servicio_pg.py` (y por mutación):

- **Una operación viva por archivo y por destino** (índices únicos parciales): reclamar el archivo y reservar
  el destino son la misma inserción atómica. Se guarda el destino **efectivo** (con sufijo si el canónico
  estaba ocupado). Además se comprueba que ninguna otra fila de `files` lo tenga ya registrado (`file_path`
  es único) y, al confirmar, esa restricción es la que decide frente a escritores concurrentes.
- **Nunca se borra el origen** hasta que la asignación está confirmada, y solo si: el destino existe íntegro
  (se relee SIEMPRE: no hay exclusión de escritores que sostenga «ya lo verifiqué»), la BD apunta a él y el
  origen es, por CONTENIDO (sha256), la copia verificada. Si no, se conserva (`reparacion_pendiente`).
- **Un `commit` de resultado desconocido no se trata como `rollback`**: se pregunta a la BD con otra sesión y,
  si ni eso es posible, se conserva todo (`pendiente_de_comprobar`). Nunca se borra el destino por eso.
- **Publicar nunca reemplaza**: `renameat2(RENAME_NOREPLACE)` o, si el sistema de ficheros no lo admite,
  `link` + `unlink`; si tampoco, se RECHAZA el montaje (no hay un tercer camino «comprobar y reemplazar»).
- **Candado consultivo de TRANSACCIÓN** en una conexión dedicada: distingue una operación huérfana de una en
  curso sin plazos ni reloj y no existe un `unlock` que pueda fallar. Perder el candado no detiene el código
  Python del ejecutor, así que cada ejecutor lleva una `epoca`: toda escritura en la BD lleva
  `AND epoca = <la suya>` y se comprueba que SIGUE siendo el dueño antes de publicar, confirmar o borrar.
  Queda una ventana mínima entre la comprobación y el efecto en disco; su efecto es inocuo por construcción.
- **La ejecución no se cancela con el cliente** (`asyncio.shield`).
- **Límite de simultáneas compartido** por todas las instancias que usan el mismo motor (mismo pool): cada
  operación en curso retiene una conexión (la del candado) además de las cortas, así que el pool debe tener
  al menos `2 × simultáneas` (ver `comprobar_pool`).

Resultados (`EstadoResultado`) ≠ estados persistidos (`AsignacionEstado`): los resultados RECUPERABLES dejan la
operación viva con su reserva; `destino_ocupado` la cancela y la libera. NO se registra ninguna ruta en los logs.

Este módulo NO lo llama todavía ningún router: conectar la asignación individual (`POST /ui/pendientes/{id}/asignar`)
es el paso siguiente, y el lote viene después.
"""
from __future__ import annotations

import asyncio
import contextlib
import ctypes
import enum
import errno
import hashlib
import os
import shutil
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from zascarr.models import EDITION_KIND_A_FORMAT, File, Issue, IssueFormat, MetadataSource, Series
from zascarr.services.importer import build_library_path
from zascarr.services.review import MOTIVO_COLISION_EDICION, ReviewService
from zascarr.utils.naming import parse_comic_filename

logger = structlog.get_logger()

#: Cuántas veces se vuelve a reservar un nombre si un ajeno ocupa el destino justo antes de publicar.
_REINTENTOS_DESTINO = 3

# El esquema es la migración 0017 (`asignacion_operaciones`).
VIVAS = "estado IN ('preparada', 'confirmada')"


class EstadoResultado(enum.StrEnum):
    """Lo que el servicio DEVUELVE. No es lo que se persiste (`AsignacionEstado`)."""
    ASIGNADO = "asignado"
    ASIGNADO_LIMPIEZA_PENDIENTE = "asignado_limpieza_pendiente"   # confirmada; falló retirar el origen
    REPARACION_PENDIENTE = "reparacion_pendiente"                 # destino dañado/ausente o BD desviada: se conserva el origen
    PROPIEDAD_PERDIDA = "propiedad_perdida"                       # otro ejecutor tomó la operación: este se detiene
    YA_ASIGNADO = "ya_asignado"
    YA_EN_CURSO = "ya_en_curso"
    PENDIENTE = "pendiente"                                       # no se pudo confirmar; se reintentará
    PENDIENTE_DE_COMPROBAR = "pendiente_de_comprobar"             # ni siquiera se pudo preguntar a la BD
    DESTINO_OCUPADO = "destino_ocupado"                           # CANCELA la operación y libera la reserva
    COLISION_EDICION = "colision_edicion"
    DATOS_NO_VALIDOS = "datos_no_validos"                         # p. ej. número vacío: la petición está mal
    NO_ENCONTRADO = "no_encontrado"
    ERROR = "error"


#: Resultados tras los cuales la operación SIGUE viva y conserva su reserva.
RESULTADOS_RECUPERABLES = frozenset({
    EstadoResultado.PENDIENTE, EstadoResultado.REPARACION_PENDIENTE,
    EstadoResultado.ASIGNADO_LIMPIEZA_PENDIENTE, EstadoResultado.PENDIENTE_DE_COMPROBAR,
})


@dataclass(frozen=True)
class Resultado:
    estado: EstadoResultado
    motivo: str = ""
    destino: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "estado", EstadoResultado(self.estado))


async def _no_hacer_nada(_punto: str) -> None:
    return None


def _sha256(ruta: Path) -> str:
    with open(ruta, "rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _copiar_y_verificar(origen: Path, temporal: Path, sha_esperado: str, size: int) -> None:
    """Copia a un temporal en la carpeta de destino y lo VERIFICA (tamaño y sha256) antes de publicarlo."""
    temporal.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copyfile(origen, temporal)
        with open(temporal, "rb") as f:
            os.fsync(f.fileno())
        if temporal.stat().st_size != size or _sha256(temporal) != sha_esperado:
            raise OSError("la copia no coincide con el original (tamaño o sha256)")
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


class PublicacionNoSoportadaError(OSError):
    """El sistema de ficheros del destino no ofrece ninguna publicación atómica sin reemplazo."""


class PublicadoConResiduoError(OSError):
    """El destino SÍ quedó publicado (con `link`), pero no se pudo retirar el nombre temporal.

    No es un fallo de publicar: el destino es íntegro y hay que seguir adelante; lo que queda es un residuo
    (un segundo nombre del mismo contenido) que se retira en la limpieza, no antes de acreditar el destino."""


_RENAME_NOREPLACE = 1
_AT_FDCWD = -100
_libc = ctypes.CDLL(None, use_errno=True)
_NO_SOPORTADO = {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EPERM, errno.EXDEV}


def _renameat2_noreplace(origen: Path, destino: Path) -> None:
    f = getattr(_libc, "renameat2", None)
    if f is None:
        raise OSError(errno.ENOSYS, "renameat2 no disponible")
    if f(_AT_FDCWD, os.fsencode(origen), _AT_FDCWD, os.fsencode(destino), _RENAME_NOREPLACE) != 0:
        e = ctypes.get_errno()
        raise OSError(e, os.strerror(e))


def _publicar(temporal: Path, destino: Path) -> None:
    """Publica `temporal` como `destino` SIN poder reemplazar a nadie.

    `os.replace` sustituye en silencio un nombre existente, y comprobar `exists()` antes deja una ventana
    en la que otro escritor puede crear el destino. Aquí la garantía la da el núcleo:
    `renameat2(RENAME_NOREPLACE)`, o `link` (que falla con EEXIST) + `unlink` si el sistema de ficheros
    no admite lo primero. Si no admite ninguna, se rechaza: NO hay un tercer camino «comprobar y
    reemplazar». Lanza `FileExistsError` si el destino ya existe (no se toca), `PublicacionNoSoportadaError`
    (nada publicado) y `PublicadoConResiduoError` (SÍ publicado; solo falló retirar el temporal).
    """
    try:
        _renameat2_noreplace(temporal, destino)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            raise FileExistsError(errno.EEXIST, "el destino ya existe", str(destino)) from exc
        if exc.errno not in _NO_SOPORTADO:
            raise
        try:
            os.link(temporal, destino)       # atómico y falla con EEXIST: tampoco reemplaza
        except FileExistsError:
            raise
        except OSError as exc2:
            raise PublicacionNoSoportadaError(
                exc2.errno, f"este montaje no permite publicar sin reemplazar ({exc2.strerror})") from exc2
        try:
            temporal.unlink()
        except OSError as exc3:
            # `link` ya creó el destino: borrar OTRO nombre no lo deshace. Se avisa de que está publicado.
            raise PublicadoConResiduoError(exc3.errno, "destino publicado; el temporal no se pudo retirar") from exc3
    # Durabilidad del nombre ante un corte eléctrico: sincronizar el directorio. Mejor esfuerzo: no todos
    # los sistemas de ficheros lo admiten (NO medido en CIFS/exFAT/NTFS reales; ver el ADR).
    try:
        fd = os.open(destino.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _temporales_de(op, epoca: int) -> list[Path]:
    """Los nombres temporales que esta operación pudo dejar (el base y uno por época) y que SIGUEN existiendo."""
    base = Path(op["temporal"])
    candidatos = [base, *(base.with_name(f"{base.name}.{n}") for n in range(1, epoca + 1))]
    return [c for c in candidatos if c.exists()]


def _origen_es_el_preparado(origen: Path, size: int, mtime_ns: int) -> bool:
    try:
        st = origen.stat()
    except FileNotFoundError:
        return False
    return st.st_size == size and st.st_mtime_ns == mtime_ns


_CUPOS: weakref.WeakKeyDictionary[AsyncEngine, tuple[asyncio.Semaphore, int]] = weakref.WeakKeyDictionary()
_CUPO_SIN_MOTOR: dict[int, asyncio.Semaphore] = {}


def _cupo_compartido(motor: AsyncEngine | None, limite: int) -> asyncio.Semaphore:
    """Un único semáforo por motor (= por pool): dos instancias del servicio sobre el mismo motor no pueden
    sumar sus límites. Dos límites DISTINTOS para el mismo motor son un error de configuración: se rechaza en
    vez de elegir uno en silencio."""
    if limite < 1:
        raise ValueError("max_simultaneas debe ser al menos 1")
    if motor is None:                     # fábrica sin motor asociado (no ocurre en producción)
        return _CUPO_SIN_MOTOR.setdefault(limite, asyncio.Semaphore(limite))
    if motor not in _CUPOS:
        _CUPOS[motor] = (asyncio.Semaphore(limite), limite)
    semaforo, fijado = _CUPOS[motor]
    if fijado != limite:
        raise ValueError(f"el motor ya tiene un límite de {fijado} asignaciones simultáneas; no puede ser {limite}")
    return semaforo


def comprobar_pool(motor: AsyncEngine, max_simultaneas: int) -> bool:
    """Cada operación retiene una conexión (el candado) y usa otra para el trabajo corto: hacen falta 2 por
    operación. Devuelve False si el pool del motor no da para eso."""
    pool = motor.pool
    capacidad = (getattr(pool, "size", lambda: 0)() or 0) + (getattr(pool, "_max_overflow", 0) or 0)
    return capacidad >= 2 * max_simultaneas


class _Propiedad:
    """Lo que un ejecutor sabe de su derecho a actuar: el candado (en su conexión dedicada) y su época."""

    def __init__(self, sesion_del_candado: AsyncSession, clave: int, epoca: int):
        self._sesion, self._clave, self.epoca = sesion_del_candado, clave, epoca

    async def vigente(self) -> bool:
        """¿Esta conexión SIGUE sosteniendo el candado? Perder la conexión (o terminar su transacción) lo
        libera, pero el código Python sigue vivo: hay que preguntarlo antes de cada efecto, no suponerlo."""
        try:
            fila = (await self._sesion.execute(text(
                "SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted AND pid = pg_backend_pid() "
                "AND classid = :hi AND objid = :lo"),
                {"hi": self._clave >> 32, "lo": self._clave & 0xFFFFFFFF})).first()
            return fila is not None
        except Exception:  # noqa: BLE001 — sin conexión no hay propiedad que acreditar
            return False


class AsignacionService:
    def __init__(self, fabrica: async_sessionmaker[AsyncSession], biblioteca: Path, *,
                 gancho: Callable[[str], Awaitable[None]] = _no_hacer_nada,
                 borrar: Callable[[Path], None] | None = None, max_simultaneas: int = 1):
        self._fabrica = fabrica
        self._biblioteca = biblioteca
        # El límite es de TODAS las instancias que usan el mismo motor (el mismo pool), no de esta.
        self._max_simultaneas = max_simultaneas
        self._motor = fabrica.kw.get("bind")
        self._gancho = gancho            # las pruebas inyectan aquí el fallo (muerte, excepción…)
        self._borrar = borrar or (lambda p: p.unlink())

    @property
    def _cupo(self) -> asyncio.Semaphore:
        return _cupo_compartido(self._motor, self._max_simultaneas)

    # ── API ──────────────────────────────────────────────────────────────────

    async def asignar(self, file_id: UUID, series_id: UUID, issue_number: str, *,
                       aprender_alias: bool = True) -> Resultado:
        """Prepara (con commit) y ejecuta. La ejecución no se cancela con el cliente.

        Si el destino lo ocupa un ajeno justo antes de publicar (`destino_ocupado`), la operación queda
        cancelada y se reintenta con el siguiente nombre libre (hasta `_REINTENTOS_DESTINO` veces)."""
        resultado = Resultado(EstadoResultado.ERROR, "sin intentar")
        for _ in range(_REINTENTOS_DESTINO):
            preparada = await self._preparar(file_id, series_id, (issue_number or "").strip(), aprender_alias)
            if isinstance(preparada, Resultado):
                return preparada
            resultado = await asyncio.shield(self._ejecutar(preparada))
            if resultado.estado is not EstadoResultado.DESTINO_OCUPADO:
                return resultado
        return resultado

    async def reconciliar(self) -> list[Resultado]:
        """Continúa o cierra las operaciones vivas. Consulta SOLO la tabla (índice parcial): no recorre la biblioteca."""
        async with self._fabrica() as s:
            ids = [r[0] for r in (await s.execute(text(
                f"SELECT id FROM asignacion_operaciones WHERE {VIVAS} ORDER BY creada"))).all()]
        resultados = []
        for i in ids:
            r = await self._ejecutar(i)
            logger.info("asignacion.reconciliada", operacion=str(i), resultado=r.estado.value)
            resultados.append(r)
        return resultados

    # ── 1. preparar ──────────────────────────────────────────────────────────

    async def _preparar(self, file_id, series_id, issue_number, aprender_alias: bool = True) -> UUID | Resultado:
        if not issue_number:
            return Resultado(EstadoResultado.DATOS_NO_VALIDOS, "El número de issue no puede estar vacío")
        async with self._fabrica() as s:
            file = await s.get(File, file_id)
            serie = await s.get(Series, series_id)
            if file is None or serie is None:
                return Resultado("no_encontrado", "Archivo o serie no encontrados")

            viva = (await s.execute(text(
                f"SELECT id FROM asignacion_operaciones WHERE file_id = :f AND {VIVAS}"), {"f": file_id})).first()
            if viva is not None:
                return viva[0]          # ya hay una: se continúa (o se informa si otro proceso la ejecuta)

            formato = EDITION_KIND_A_FORMAT.get(
                parse_comic_filename(file.file_name).edition_kind, IssueFormat.SINGLE_ISSUE)
            issue = (await s.execute(select(Issue).where(
                Issue.series_id == serie.id, Issue.issue_number == issue_number))).scalar_one_or_none()
            if issue is not None and (issue.format or IssueFormat.SINGLE_ISSUE) != formato:
                await self._marcar_colision(file_id)
                return Resultado(EstadoResultado.COLISION_EDICION, "Ese número ya existe como otra edición")
            if issue is not None and file.issue_id == issue.id:
                return Resultado("ya_asignado", "Ya estaba asignado", file.file_path)

            origen = Path(file.file_path)
            try:
                st = origen.stat()
            except FileNotFoundError:
                return Resultado("error", "El archivo de origen ya no está en su sitio")
            # El hash esperado es el del fichero QUE SE VA A COPIAR, leído ahora: `File.sha256_hash` puede estar
            # obsoleto (p. ej. tras reescribir ComicInfo) y daría un fallo espurio al verificar la copia.
            sha = await asyncio.to_thread(_sha256, origen)
            st2 = origen.stat()
            if (st2.st_size, st2.st_mtime_ns) != (st.st_size, st.st_mtime_ns):
                return Resultado("error", "El archivo cambió mientras se preparaba la asignación; inténtalo de nuevo")
            canonico = build_library_path(self._biblioteca, serie, issue_number, origen.suffix)

            for k in range(0, 1000):
                candidato = canonico if k == 0 else canonico.with_name(f"{canonico.stem} ({k}){canonico.suffix}")
                if candidato.exists():
                    continue
                registrado = (await s.execute(text("SELECT 1 FROM files WHERE file_path = :p"),
                                              {"p": str(candidato)})).first()
                if registrado is not None:        # otra fila de `files` ya usa ese nombre
                    continue
                op_id = uuid4()
                try:
                    async with s.begin_nested():
                        await s.execute(text(
                            "INSERT INTO asignacion_operaciones (id, file_id, estado, origen, destino, temporal, "
                            "size_bytes, mtime_ns, sha256, series_id, issue_number, formato, aprender_alias) VALUES "
                            "(:id, :f, 'preparada', :o, :d, :t, :sz, :mt, :sha, :s, :n, CAST(:fmt AS issue_format), :alias)"),
                            {"id": op_id, "f": file_id, "o": str(origen), "d": str(candidato),
                             "t": str(candidato.with_name(f".{candidato.name}.{op_id.hex[:8]}.part")),
                             "sz": st.st_size, "mt": st.st_mtime_ns, "sha": sha, "s": series_id,
                             "n": issue_number, "fmt": formato.value, "alias": aprender_alias})
                    await s.commit()
                    return op_id
                except IntegrityError as exc:
                    if "uq_asignacion_viva_por_archivo" in str(exc.orig):
                        await s.rollback()
                        otra = (await s.execute(text(
                            f"SELECT id FROM asignacion_operaciones WHERE file_id = :f AND {VIVAS}"), {"f": file_id})).first()
                        return otra[0]
                    continue                      # destino reservado por otra operación: siguiente sufijo
            return Resultado("error", "No se encontró un nombre de destino libre")

    # ── 2-5. ejecutar / reconciliar una operación ────────────────────────────

    async def _ejecutar(self, op_id: UUID) -> Resultado:
        async with self._cupo:
            # Candado consultivo de TRANSACCIÓN en una conexión dedicada: lo suelta Postgres al terminar
            # esa transacción (commit, rollback o caída), de modo que NO existe un `unlock` que pueda fallar
            # ni una conexión que vuelva al pool reteniéndolo. La transacción se queda abierta mientras dura
            # el trabajo (en una sesión aparte): `idle_in_transaction_session_timeout` debe permitirlo.
            clave = op_id.int & 0x7FFF_FFFF_FFFF_FFFF
            candado_s = self._fabrica()
            try:
                if not (await candado_s.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": clave})).scalar():
                    return Resultado("ya_en_curso", "Otra ejecución la está completando")
                epoca = await self._tomar_epoca(op_id)
                if epoca is None:
                    return Resultado("ya_asignado", "Operación ya cerrada")
                return await self._continuar(op_id, _Propiedad(candado_s, clave, epoca))
            finally:
                # Si la conexión del candado murió, cerrarla falla; el candado ya no existe y el resultado
                # de la operación NO debe perderse por eso.
                with contextlib.suppress(Exception):
                    await candado_s.close()

    async def _tomar_epoca(self, op_id: UUID) -> int | None:
        """Cada ejecutor que consigue el candado incrementa la época (y la confirma): es su ficha de vallado."""
        async with self._fabrica() as s:
            fila = (await s.execute(text(
                f"UPDATE asignacion_operaciones SET epoca = epoca + 1, actualizada = now() "
                f"WHERE id = :i AND {VIVAS} RETURNING epoca"), {"i": op_id})).first()
            await s.commit()
        return fila[0] if fila else None

    async def _marcar_colision(self, file_id: UUID) -> None:
        """B15: deja el motivo en el archivo para que siga visible al recargar «Por revisar».

        Fusión ATÓMICA (`||` de JSONB) y en su propia transacción corta: varios escritores reescriben
        `File.metadata_` ENTERO a partir de una lectura anterior, y una escritura así borraría lo que
        hubiera añadido otro entretanto."""
        async with self._fabrica() as s:
            await s.execute(text(
                "UPDATE files SET metadata = coalesce(metadata, '{}'::jsonb) || "
                "jsonb_build_object('review_motivo', CAST(:m AS text)) WHERE id = :f"),
                {"m": MOTIVO_COLISION_EDICION, "f": file_id})
            await s.commit()

    async def _op(self, op_id: UUID):
        async with self._fabrica() as s:
            return (await s.execute(text("SELECT * FROM asignacion_operaciones WHERE id = :i"),
                                    {"i": op_id})).mappings().first()

    async def _continuar(self, op_id: UUID, prop: _Propiedad) -> Resultado:
        op = await self._op(op_id)
        if op is None or op["estado"] in ("limpiada", "cancelada"):
            return Resultado("ya_asignado", "Operación ya cerrada", op["destino"] if op else None)
        origen, destino = Path(op["origen"]), Path(op["destino"])
        base_temporal = Path(op["temporal"])
        mi_temporal = base_temporal.with_name(f"{base_temporal.name}.{prop.epoca}")
        perdida = Resultado("propiedad_perdida", "Otra ejecución tomó la operación; esta se detiene sin tocar nada",
                            op["destino"])

        if op["estado"] == "preparada":
            await self._gancho("tras_preparar")
            if not destino.exists():
                try:
                    for anterior in range(1, prop.epoca):              # temporales de ejecutores anteriores
                        base_temporal.with_name(f"{base_temporal.name}.{anterior}").unlink(missing_ok=True)
                    base_temporal.unlink(missing_ok=True)
                except OSError as exc:
                    # No se toca nada más: la operación sigue viva y el próximo intento vuelve a limpiarlos.
                    logger.warning("asignacion.temporal_previo_sin_retirar", operacion=str(op_id), error=type(exc).__name__)
                    return Resultado("error", "No se pudo retirar un temporal anterior; se reintentará", op["destino"])
                if not _origen_es_el_preparado(origen, op["size_bytes"], op["mtime_ns"]):
                    return Resultado("error", "El origen cambió o desapareció antes de copiarlo; no se toca nada")
                if not await prop.vigente():
                    return perdida
                try:
                    await asyncio.to_thread(_copiar_y_verificar, origen, mi_temporal, op["sha256"], op["size_bytes"])
                except OSError as exc:
                    return Resultado("error", f"La copia no se pudo verificar: {exc}")
                await self._gancho("tras_copiar")
                if not await prop.vigente():
                    mi_temporal.unlink(missing_ok=True)
                    return perdida
                try:
                    await asyncio.to_thread(_publicar, mi_temporal, destino)
                except FileNotFoundError:
                    return perdida           # su temporal ya no está: otro ejecutor lo limpió al tomar la operación
                except FileExistsError:
                    # Alguien (ajeno a las operaciones) ocupó el destino tras reservarlo: NO se toca. La
                    # operación se cancela y quien reintente reservará el siguiente nombre libre.
                    mi_temporal.unlink(missing_ok=True)
                    if not await self._cerrar(op_id, "cancelada", prop.epoca):
                        return perdida
                    return Resultado("destino_ocupado", "Otro fichero ocupó el destino; no se tocó. Reintenta.", op["destino"])
                except PublicadoConResiduoError:
                    # Publicado y verificado (es el mismo contenido que la copia verificada): se SIGUE hacia
                    # confirmar. El temporal que no se pudo retirar lo recoge la limpieza (su ruta y su época
                    # están en la operación), sin liberar nada antes.
                    logger.warning("asignacion.temporal_sin_retirar", operacion=str(op_id))
                except PublicacionNoSoportadaError as exc:
                    # Nada publicado. Si retirar la copia propia falla, la operación se CONSERVA viva.
                    if not await self._retirar_copia_y_cancelar(op_id, mi_temporal, prop):
                        return Resultado("error", "No se pudo retirar la copia temporal; se limpiará al reintentar",
                                         op["destino"])
                    return Resultado("error", str(exc), op["destino"])
                except OSError as exc:
                    # Sin permiso, solo lectura, sin espacio…, o un error cuyo efecto no se conoce. Primero se
                    # MIRA el destino: si existe, pudo publicarse (p. ej. un montaje de red que falló al responder),
                    # así que NO se cancela ni se libera la reserva: la operación sigue viva y la reconciliación
                    # (que comprueba el destino por contenido) la resuelve. Solo si no hay destino se da por
                    # no publicado, se retira la copia propia y se cancela; si retirarla falla, tampoco se cancela.
                    logger.warning("asignacion.publicar_fallo", operacion=str(op_id), error=type(exc).__name__)
                    if destino.exists():
                        return Resultado(EstadoResultado.PENDIENTE_DE_COMPROBAR,
                                         "Error al publicar con el destino ya presente; se conserva todo", op["destino"])
                    if not await self._retirar_copia_y_cancelar(op_id, mi_temporal, prop):
                        return Resultado("error", "No se pudo retirar la copia temporal; se limpiará al reintentar",
                                         op["destino"])
                    return Resultado("error", "No se pudo escribir en la carpeta de destino", op["destino"])
            else:
                # Un intento anterior ya publicó. Se comprueba antes de aprovecharlo.
                ok = destino.stat().st_size == op["size_bytes"] and await asyncio.to_thread(_sha256, destino) == op["sha256"]
                if not ok:
                    return Resultado("error", "El destino existe pero no coincide con el original; no se toca nada")
            await self._gancho("tras_publicar")
            if not await prop.vigente():
                return perdida
            confirmada = await self._confirmar(op, prop)
            if isinstance(confirmada, Resultado):
                return confirmada
            await self._gancho("tras_confirmar")

        return await self._limpiar(op_id, origen, op, prop)

    async def _retirar_copia_y_cancelar(self, op_id: UUID, temporal: Path, prop: _Propiedad) -> bool:
        """Fallo anterior a publicar: retira la copia propia y SOLO ENTONCES cancela (libera la reserva).

        Si no se puede retirar, devuelve False y la operación sigue viva: su ruta temporal está en la fila, y
        al continuar se retiran los temporales de épocas anteriores antes de copiar de nuevo."""
        try:
            await asyncio.to_thread(temporal.unlink, missing_ok=True)
        except OSError:
            return False
        await self._cerrar(op_id, "cancelada", prop.epoca)
        return True

    async def _cerrar(self, op_id: UUID, estado: str, epoca: int) -> bool:
        """Cierra la operación SOLO si la época sigue siendo la del llamante (vallado)."""
        async with self._fabrica() as s:
            hecho = (await s.execute(text(
                "UPDATE asignacion_operaciones SET estado = CAST(:e AS asignacion_estado), actualizada = now() "
                "WHERE id = :i AND epoca = :ep RETURNING 1"), {"e": estado, "i": op_id, "ep": epoca})).first()
            await s.commit()
        return hecho is not None

    async def _confirmar(self, op, prop: _Propiedad) -> Resultado | None:
        """Una transacción: archivo, issue, alias y la propia operación. Ante un fallo de commit de
        RESULTADO DESCONOCIDO no se asume nada: se pregunta a la BD con otra sesión."""
        try:
            async with self._fabrica() as s:
                # Vallado: lo PRIMERO es reclamar la fila con la época propia; si otro ejecutor la tomó
                # después, esto no devuelve nada y no se escribe ni una línea más. La fila queda bloqueada
                # hasta el commit, así que el otro ejecutor tampoco puede confirmar a la vez.
                if (await s.execute(text(
                        "UPDATE asignacion_operaciones SET actualizada = now() "
                        "WHERE id = :i AND epoca = :ep AND estado = 'preparada' RETURNING 1"),
                        {"i": op["id"], "ep": prop.epoca})).first() is None:
                    await s.rollback()
                    return Resultado("propiedad_perdida", "Otra ejecución tomó la operación; no se confirma", op["destino"])
                file = await s.get(File, op["file_id"], with_for_update=True)
                serie = await s.get(Series, op["series_id"])
                issue = (await s.execute(select(Issue).where(
                    Issue.series_id == serie.id, Issue.issue_number == op["issue_number"]))).scalar_one_or_none()
                if issue is not None and (issue.format or IssueFormat.SINGLE_ISSUE).value != op["formato"]:
                    await s.rollback()
                    await self._marcar_colision(op["file_id"])
                    return await self._abandonar(op, prop, Resultado(
                        EstadoResultado.COLISION_EDICION, "Ese número apareció como otra edición mientras se copiaba"))
                if issue is None:
                    issue = Issue(series_id=serie.id, issue_number=op["issue_number"],
                                  locked_fields=["series_id", "issue_number"], format=IssueFormat(op["formato"]))
                    s.add(issue)
                    await s.flush()
                nombre_original = file.file_name
                file.issue_id = issue.id
                file.file_path = op["destino"]
                file.file_name = Path(op["destino"]).name
                file.metadata_source = MetadataSource.MANUAL.value
                await s.flush()
                if op["aprender_alias"]:
                    await ReviewService(s)._learn_alias(nombre_original, serie.id)
                await s.execute(text("UPDATE asignacion_operaciones SET estado = 'confirmada', actualizada = now() "
                                     "WHERE id = :i AND epoca = :ep"), {"i": op["id"], "ep": prop.epoca})
                await s.commit()
            return None
        except IntegrityError as exc:
            if _restriccion(exc) == "files_file_path_key":
                # FALLO CONOCIDO (la sentencia falló antes de cualquier commit): otra fila de `files` registró
                # ese nombre mientras se copiaba. Es la restricción única de la BD, no una consulta previa,
                # quien decide frente a escritores concurrentes.
                return await self._abandonar(op, prop, Resultado(
                    EstadoResultado.DESTINO_OCUPADO, "Otro archivo registró ese nombre mientras se copiaba", op["destino"]))
            return await self._resultado_desconocido(op, exc)
        except Exception as exc:  # noqa: BLE001 — el resultado del commit puede ser desconocido
            return await self._resultado_desconocido(op, exc)

    async def _abandonar(self, op, prop: _Propiedad, resultado: Resultado) -> Resultado:
        """Fallo CONOCIDO tras publicar y antes de confirmar: ninguna fila referencia el destino y el origen
        sigue intacto, así que se retira SOLO la copia propia (si su contenido es el verificado) y se cancela la
        operación, que libera la reserva. Si este ejecutor ya no es el dueño, no se toca nada."""
        if not await prop.vigente():
            return Resultado(EstadoResultado.PROPIEDAD_PERDIDA, "Otra ejecución tomó la operación", op["destino"])
        destino = Path(op["destino"])
        with contextlib.suppress(OSError):
            if destino.is_file() and await asyncio.to_thread(_sha256, destino) == op["sha256"]:
                destino.unlink()
        await self._cerrar(op["id"], "cancelada", prop.epoca)
        return resultado

    async def _resultado_desconocido(self, op, exc: Exception) -> Resultado | None:
        """El `commit` pudo o no aplicarse. NO se asume `rollback` ni se borra nada: se pregunta a la BD con
        otra sesión. `None` = sí se confirmó (la respuesta se perdió) y el flujo sigue."""
        try:
            actual = await self._op(op["id"])
        except Exception:  # noqa: BLE001 — ni siquiera se puede preguntar
            return Resultado(EstadoResultado.PENDIENTE_DE_COMPROBAR,
                             f"No se sabe si se confirmó ({type(exc).__name__}); se conservan los ficheros", op["destino"])
        if actual is not None and actual["estado"] == "confirmada":
            return None
        return Resultado(EstadoResultado.PENDIENTE,
                         f"No se pudo confirmar ({type(exc).__name__}); se reintentará", op["destino"])

    async def _limpiar(self, op_id: UUID, origen: Path, op, prop: _Propiedad) -> Resultado:
        """Retira el origen SOLO si su borrado no puede perder la última copia válida:

        1. el destino existe y es íntegro: tamaño y sha256 **siempre releídos** (nada de «lo verifiqué al
           publicar»: entre publicar y limpiar puede alterarlo quien sea, y no hay exclusión de escritores);
        2. la BD sigue apuntando a ese destino con el `Issue` esperado;
        3. el origen es, por CONTENIDO, la copia verificada (sha256): tamaño y `mtime_ns` no bastan;
        4. este ejecutor SIGUE siendo el dueño de la operación.
        Si algo no cuadra se CONSERVA el origen y se devuelve `reparacion_pendiente`.
        """
        destino = Path(op["destino"])
        if origen == destino:
            return Resultado("error", "El origen y el destino coinciden; no se borra nada")
        temporales = _temporales_de(op, prop.epoca)
        if origen.exists() or temporales:
            try:
                ok_destino = (destino.is_file() and destino.stat().st_size == op["size_bytes"]
                              and await asyncio.to_thread(_sha256, destino) == op["sha256"])
            except OSError:
                ok_destino = False
            if not ok_destino:
                return Resultado("reparacion_pendiente",
                                 "El destino falta o no está íntegro; se conserva el origen", op["destino"])
            if not await self._bd_apunta_al_destino(op):
                return Resultado("reparacion_pendiente",
                                 "La BD no apunta a la asignación esperada; se conserva el origen", op["destino"])
        # Residuos de la publicación (un segundo nombre del mismo contenido): con el destino ya acreditado.
        # Si alguno no se puede retirar se CONSERVA el origen y la operación sigue confirmada: la próxima
        # continuación (reintento o arranque) vuelve a intentarlo.
        for temporal in temporales:
            try:
                await asyncio.to_thread(temporal.unlink)
            except OSError:
                return Resultado("asignado_limpieza_pendiente",
                                 "Queda un temporal sin retirar; se conserva el origen", op["destino"])
        if origen.exists():
            try:
                mismo_contenido = (origen.stat().st_size == op["size_bytes"]
                                   and await asyncio.to_thread(_sha256, origen) == op["sha256"])
            except OSError:
                mismo_contenido = False
            if not mismo_contenido:
                return Resultado("asignado_limpieza_pendiente",
                                 "El origen ya no es el fichero que se copió; no se borra", op["destino"])
            if not await prop.vigente():
                return Resultado("propiedad_perdida", "Otra ejecución tomó la operación; no se borra nada", op["destino"])
            try:
                await asyncio.to_thread(self._borrar, origen)
            except OSError as exc:
                return Resultado("asignado_limpieza_pendiente", f"No se pudo borrar el original: {exc}", op["destino"])
        await self._gancho("tras_borrar_origen")
        if not await self._cerrar(op_id, "limpiada", prop.epoca):
            return Resultado("propiedad_perdida", "Otra ejecución tomó la operación", op["destino"])
        return Resultado("asignado", "", op["destino"])

    async def _bd_apunta_al_destino(self, op) -> bool:
        async with self._fabrica() as s:
            fila = (await s.execute(text(
                "SELECT f.file_path, i.series_id, i.issue_number FROM files f LEFT JOIN issues i ON i.id = f.issue_id "
                "WHERE f.id = :f"), {"f": op["file_id"]})).first()
        return (fila is not None and fila[0] == op["destino"] and fila[1] == op["series_id"]
                and fila[2] == op["issue_number"])


# ── Integración con el resto de la aplicación ─────────────────────────────────────────────────────

def _restriccion(exc: DBAPIError) -> str | None:
    """Nombre de la restricción de Postgres que provocó el error, si se puede saber (asyncpg lo expone en la
    excepción original o en su causa). Nunca se decide por el texto del mensaje."""
    orig = getattr(exc, "orig", None)
    for candidato in (orig, getattr(orig, "__cause__", None)):
        nombre = getattr(candidato, "constraint_name", None)
        if nombre:
            return nombre
    return None


#: La restricción que impide borrar un archivo o una serie con una asignación VIVA (migración 0017).
RESTRICCION_OPERACION_VIVA = "ck_asignacion_viva_con_referencias"


def conflicto_por_operacion_viva(exc: DBAPIError) -> bool:
    """¿Este error de integridad es EXACTAMENTE «hay una asignación viva que depende de esto»?

    Solo esa restricción se traduce a un 409; cualquier otro `IntegrityError` sigue siendo un error."""
    return _restriccion(exc) == RESTRICCION_OPERACION_VIVA


def servicio_por_defecto(gancho: Callable[[str], Awaitable[None]] = _no_hacer_nada) -> AsignacionService:
    """El servicio con la configuración de la aplicación (motor y biblioteca reales)."""
    from zascarr.config import get_settings
    from zascarr.database import async_session_factory

    s = get_settings()
    return AsignacionService(async_session_factory, s.library_path, gancho=gancho,
                             max_simultaneas=s.asignacion_simultaneas)


async def reconciliar_al_arrancar(servicio: AsignacionService | None = None) -> int:
    """Continúa o cierra las operaciones que quedaron vivas en una ejecución anterior.

    Se lanza como TAREA DE FONDO tras el arranque (no retrasa el healthcheck), solo con la BD disponible y
    **nunca propaga una excepción**: un fallo aquí se registra y se reintenta al siguiente arranque, pero no
    puede tirar la aplicación. Consulta solo `asignacion_operaciones` (índice parcial): no recorre la
    biblioteca. Devuelve cuántas operaciones procesó (0 si falló)."""
    try:
        servicio = servicio or servicio_por_defecto()
        resultados = await servicio.reconciliar()
    except Exception:  # noqa: BLE001 — ver la docstring
        logger.exception("asignacion.reconciliacion_fallida")
        return 0
    if resultados:
        logger.info("asignacion.reconciliacion_terminada", operaciones=len(resultados),
                    pendientes=sum(1 for r in resultados if r.estado in RESULTADOS_RECUPERABLES))
    return len(resultados)
