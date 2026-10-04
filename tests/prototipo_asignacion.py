# ruff: noqa: E501
"""PROTOTIPO del contrato del ADR 0006: asignar UN archivo de forma recuperable.

No es código de producción ni lo llama ningún router: es una **especificación ejecutable** del orden

    preparar (commit) → copiar y verificar → publicar → confirmar (commit) → retirar el origen → limpiar

con la que se demuestra, contra Postgres real y ficheros reales, que cada punto de fallo queda
reconciliable SIN escanear la biblioteca. Cuando se apruebe la tabla (historia con migración propia),
esto se convierte en el servicio de V6a.

Las decisiones que lo sostienen (ADR 0006):

- La operación vive en una **tabla propia** (`asignacion_operaciones`, migración 0017: el prototipo corre
  sobre el esquema de PRODUCCIÓN). `File.metadata_` no sirve (ver el ADR y las pruebas de
  `test_prototipo_asignacion_pg.py::TestMetadataNoBasta`).
- **Una operación viva por archivo y por destino** (índices únicos parciales): reclamar un archivo y
  reservar un destino son la misma inserción atómica. El destino que se guarda es el **efectivo**
  (con sufijo si el canónico estaba ocupado).
- **Nunca se borra el origen hasta que la asignación está confirmada** y solo si sigue siendo el que se
  preparó (tamaño y `mtime_ns`).
- **Nunca se borra el destino por un fallo de `commit` de resultado desconocido**: se consulta la BD.
- El trabajo corre protegido de la cancelación del cliente (`asyncio.shield`) y bajo un **candado
  consultivo de TRANSACCIÓN** de Postgres, en una conexión dedicada, por operación: una operación
  huérfana (su proceso murió) se distingue de una en curso sin plazos ni reloj, y el candado se suelta
  con la propia transacción, así que **no hay `unlock` que pueda fallar** y ninguna conexión vuelve al
  pool reteniéndolo (revisión de la PR #76; antes era un candado de sesión).
- **Publicar nunca reemplaza:** `renameat2(RENAME_NOREPLACE)` o, si el sistema de ficheros no lo admite,
  `link` + `unlink`; si tampoco, se **rechaza el montaje** (no se vuelve a «comprobar y luego `replace`»).
- **El origen solo se borra si es, por CONTENIDO, la copia verificada, y el destino sigue existiendo
  íntegro (se vuelve a hashear SIEMPRE: no hay exclusión de escritores que sostenga «ya lo verifiqué
  antes») y la BD sigue apuntando a él**: nunca se borra la última copia válida.
- **Perder el candado no detiene el trabajo de Python: se vallan los efectos.** Cada ejecutor toma una
  `epoca` (contador en la fila de la operación) al conseguir el candado. Antes de publicar, confirmar o
  borrar comprueba que SIGUE teniendo el candado (consulta a `pg_locks` sobre su propia conexión) y toda
  escritura en la BD lleva `AND epoca = <la mía>`: un ejecutor antiguo no puede confirmar ni cerrar nada.
  El temporal lleva la época en el nombre: no pisa el de otro. Queda una ventana mínima entre la
  comprobación y el efecto en disco; su efecto es inocuo por construcción (se publica un fichero verificado
  con `NOREPLACE`, y se borra un origen solo si su contenido ya es la copia íntegra y confirmada).
- `max_simultaneas` es **por instancia del servicio**: al integrarlo habrá que compartir el límite entre
  todas las instancias que usan el mismo pool (aquí una sola instancia no demuestra un límite global).
"""
from __future__ import annotations

import asyncio
import contextlib
import ctypes
import errno
import hashlib
import os
import shutil
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from zascarr.models import EDITION_KIND_A_FORMAT, File, Issue, IssueFormat, MetadataSource, Series
from zascarr.services.importer import build_library_path
from zascarr.services.review import ReviewService
from zascarr.utils.naming import parse_comic_filename

# El esquema ya NO se crea aquí: es la migración 0017 (`asignacion_operaciones`), que el prototipo usa tal cual.
VIVAS = "estado IN ('preparada', 'confirmada')"


@dataclass(frozen=True)
class Resultado:
    estado: str      # asignado | asignado_limpieza_pendiente | reparacion_pendiente | propiedad_perdida | ya_asignado | ya_en_curso | pendiente | pendiente_de_comprobar | destino_ocupado | colision_edicion | no_encontrado | error
    motivo: str = ""
    destino: str | None = None


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
    reemplazar». Lanza `FileExistsError` si el destino ya existe (no se toca) y `PublicacionNoSoportadaError`.
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
        temporal.unlink()
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


def _origen_es_el_preparado(origen: Path, size: int, mtime_ns: int) -> bool:
    try:
        st = origen.stat()
    except FileNotFoundError:
        return False
    return st.st_size == size and st.st_mtime_ns == mtime_ns


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


class AsignacionRecuperable:
    def __init__(self, fabrica: async_sessionmaker[AsyncSession], biblioteca: Path, *,
                 gancho: Callable[[str], Awaitable[None]] = _no_hacer_nada,
                 borrar: Callable[[Path], None] | None = None, max_simultaneas: int = 1):
        self._fabrica = fabrica
        self._biblioteca = biblioteca
        # Cada operación en curso retiene UNA conexión (la del candado) además de las cortas que use:
        # el pool debe tener al menos 2 × max_simultaneas.
        self._cupo = asyncio.Semaphore(max_simultaneas)
        self._gancho = gancho            # las pruebas inyectan aquí el fallo (muerte, excepción…)
        self._borrar = borrar or (lambda p: p.unlink())

    # ── API ──────────────────────────────────────────────────────────────────

    async def asignar(self, file_id: UUID, series_id: UUID, issue_number: str) -> Resultado:
        """Prepara (con commit) y ejecuta. La ejecución no se cancela con el cliente."""
        preparada = await self._preparar(file_id, series_id, (issue_number or "").strip())
        if isinstance(preparada, Resultado):
            return preparada
        return await asyncio.shield(self._ejecutar(preparada))

    async def reconciliar(self) -> list[Resultado]:
        """Continúa o cierra las operaciones vivas. Consulta SOLO la tabla (índice parcial): no recorre la biblioteca."""
        async with self._fabrica() as s:
            ids = [r[0] for r in (await s.execute(text(
                f"SELECT id FROM asignacion_operaciones WHERE {VIVAS} ORDER BY creada"))).all()]
        return [await self._ejecutar(i) for i in ids]

    # ── 1. preparar ──────────────────────────────────────────────────────────

    async def _preparar(self, file_id, series_id, issue_number) -> UUID | Resultado:
        if not issue_number:
            return Resultado("error", "El número de issue no puede estar vacío")
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
                return Resultado("colision_edicion", "Ese número ya existe como otra edición")
            if issue is not None and file.issue_id == issue.id:
                return Resultado("ya_asignado", "Ya estaba asignado", file.file_path)

            origen = Path(file.file_path)
            try:
                st = origen.stat()
            except FileNotFoundError:
                return Resultado("error", "El archivo de origen ya no está en su sitio")
            sha = file.sha256_hash or await asyncio.to_thread(_sha256, origen)
            canonico = build_library_path(self._biblioteca, serie, issue_number, origen.suffix)

            for k in range(0, 1000):
                candidato = canonico if k == 0 else canonico.with_name(f"{canonico.stem} ({k}){canonico.suffix}")
                if candidato.exists():
                    continue
                op_id = uuid4()
                try:
                    async with s.begin_nested():
                        await s.execute(text(
                            "INSERT INTO asignacion_operaciones (id, file_id, estado, origen, destino, temporal, "
                            "size_bytes, mtime_ns, sha256, series_id, issue_number, formato) VALUES "
                            "(:id, :f, 'preparada', :o, :d, :t, :sz, :mt, :sha, :s, :n, CAST(:fmt AS issue_format))"),
                            {"id": op_id, "f": file_id, "o": str(origen), "d": str(candidato),
                             "t": str(candidato.with_name(f".{candidato.name}.{op_id.hex[:8]}.part")),
                             "sz": st.st_size, "mt": st.st_mtime_ns, "sha": sha, "s": series_id,
                             "n": issue_number, "fmt": formato.value})
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
                for anterior in range(1, prop.epoca):                  # temporales de ejecutores anteriores
                    base_temporal.with_name(f"{base_temporal.name}.{anterior}").unlink(missing_ok=True)
                base_temporal.unlink(missing_ok=True)
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
                except PublicacionNoSoportadaError as exc:
                    mi_temporal.unlink(missing_ok=True)
                    await self._cerrar(op_id, "cancelada", prop.epoca)
                    return Resultado("error", str(exc), op["destino"])
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
                    return Resultado("colision_edicion", "Ese número apareció como otra edición mientras se copiaba")
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
                await ReviewService(s)._learn_alias(nombre_original, serie.id)
                await s.execute(text("UPDATE asignacion_operaciones SET estado = 'confirmada', actualizada = now() "
                                     "WHERE id = :i AND epoca = :ep"), {"i": op["id"], "ep": prop.epoca})
                await s.commit()
            return None
        except Exception as exc:  # noqa: BLE001 — el resultado del commit puede ser desconocido
            actual = None
            try:
                actual = await self._op(op["id"])
            except Exception:  # noqa: BLE001 — ni siquiera se puede preguntar
                return Resultado("pendiente_de_comprobar",
                                 f"No se sabe si se confirmó ({type(exc).__name__}); se conservan los ficheros", op["destino"])
            if actual is not None and actual["estado"] == "confirmada":
                return None                      # sí se confirmó: la respuesta se perdió
            return Resultado("pendiente", f"No se pudo confirmar ({type(exc).__name__}); se reintentará", op["destino"])

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
        if origen.exists() and origen != destino:
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
        elif origen == destino:
            return Resultado("error", "El origen y el destino coinciden; no se borra nada")
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
