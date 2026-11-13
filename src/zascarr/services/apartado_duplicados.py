# ruff: noqa: E501, N818
"""BL-DUP1 (#264 A): apartar copias idénticas a una cuarentena reversible.

Contrato en `docs/design/especificacion-BL-DUP1-apartar.md` y ADR 0017.
Este módulo NO borra nada: mueve a `<library>/.zascarr/apartados/<operacion>/…`
con rename atómico, repunta `File` si la copia movida era la catalogada y
permite deshacer sin sobrescribir.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.config import get_settings
from zascarr.core.importer_triage import sha256_streaming
from zascarr.models import (
    ApartadoEstado,
    ApartadoGrupo,
    ApartadoGrupoEstado,
    ApartadoOperacion,
    File,
)
from zascarr.services.tokens_revision import (
    MAX_GRUPOS_APARTAR,
    ApartarFirmada,
    GrupoFirmado,
    crear_token_apartar,
    uuid_texto,
    verificar_token_apartar,
)


class ApartadoError(Exception):
    """Error de negocio con mensaje en español (sin rutas completas en logs)."""


class TokenApartadoInvalido(ApartadoError):
    pass


class GrupoRechazado(ApartadoError):
    def __init__(self, motivo: str, detalle: str | None = None):
        super().__init__(detalle or motivo)
        self.motivo = motivo
        self.detalle = detalle


@dataclass(frozen=True)
class GrupoEntrada:
    """Grupo recibido en confirmar: rutas completas o relativas a la biblioteca."""
    sha256: str
    rutas: tuple[str | Path, ...]
    keep_index: int


@dataclass
class VistaApartado:
    token: str
    operacion: str
    rutas: tuple[Path, ...]
    keep_index: int
    bytes_liberados: int


@dataclass
class ResultadoGrupo:
    grupo_clave: str
    estado: str
    motivo: str | None = None
    movidos: int = 0
    bytes: int = 0
    repuntado: bool = False


@dataclass
class ResultadoApartado:
    operacion: str
    estado: str
    grupos: list[ResultadoGrupo] = field(default_factory=list)
    total_grupos: int = 0
    total_archivos: int = 0
    total_bytes: int = 0
    idempotente: bool = False
    motivo: str | None = None

    def a_dict(self) -> dict:
        return {
            "operacion": self.operacion,
            "estado": self.estado,
            "grupos": [g.__dict__ for g in self.grupos],
            "total_grupos": self.total_grupos,
            "total_archivos": self.total_archivos,
            "total_bytes": self.total_bytes,
            "motivo": self.motivo,
        }

    def __getitem__(self, clave: str):
        return self.a_dict()[clave]


def digest_rutas(rutas: Iterable[str]) -> str:
    """SHA-256 de las rutas relativas normalizadas, ordenadas y separadas por NUL."""
    normalizadas = sorted(str(r) for r in rutas)
    return hashlib.sha256("\0".join(normalizadas).encode("utf-8")).hexdigest()


def _fsync_dir(ruta: Path) -> None:
    try:
        fd = os.open(str(ruta), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class ApartadoDuplicadosService:
    """Servicio de apartar/deshacer copias idénticas (#264 A)."""

    def __init__(self, db: AsyncSession, *, settings=None, secret: str | None = None):
        self._db = db
        self._settings = settings or get_settings()
        self._library = Path(self._settings.library_path)
        self._secret = secret if secret is not None else getattr(self._settings, "secret_key", "")

    # ── rutas y token ─────────────────────────────────────────────────────
    def _relativa(self, ruta: str | Path) -> tuple[Path, str]:
        p = Path(ruta)
        if not p.is_absolute():
            p = self._library / p
        if p.is_symlink():
            raise GrupoRechazado("no_regular", "No se sigue un enlace simbólico.")
        try:
            p = p.resolve(strict=False)
            root = self._library.resolve()
        except OSError as exc:
            raise GrupoRechazado("ruta_invalida", "La ruta no es válida.") from exc
        if root != p and root not in p.parents:
            raise GrupoRechazado("fuera_biblioteca", "La ruta no está dentro de la biblioteca.")
        if ".zascarr" in p.parts:
            raise GrupoRechazado("zascarr", "La cuarentena no se aparta a sí misma.")
        try:
            rel = p.relative_to(root).as_posix()
        except ValueError as exc:
            raise GrupoRechazado("fuera_biblioteca", "La ruta no está dentro de la biblioteca.") from exc
        return p, rel

    def _grupo_normalizado(self, grupo: GrupoEntrada) -> tuple[str, list[Path], list[str], int]:
        if not isinstance(grupo.sha256, str) or len(grupo.sha256) != 64:
            raise TokenApartadoInvalido("El contenido del grupo no es válido.")
        pares = [self._relativa(r) for r in grupo.rutas]
        if len(pares) < 2:
            raise GrupoRechazado("pocas_rutas", "Un grupo necesita al menos dos copias.")
        if not 0 <= grupo.keep_index < len(pares):
            raise TokenApartadoInvalido("La copia que se queda no es válida.")
        keep_path = pares[grupo.keep_index][0]
        pares.sort(key=lambda par: par[1])
        abs_paths = [p for p, _ in pares]
        rels = [r for _, r in pares]
        keep_sorted = next(i for i, (p, _) in enumerate(pares) if p == keep_path)
        return grupo.sha256, abs_paths, rels, keep_sorted

    async def previsualizar(self, sha: str, rutas: Sequence[str | Path],
                            keep_index: int) -> VistaApartado:
        """Valida y firma una propuesta SIN escribir disco/BD. Un grupo por llamada."""
        sha_norm = (sha or "").lower()
        if len(sha_norm) != 64 or any(c not in "0123456789abcdef" for c in sha_norm):
            raise TokenApartadoInvalido("El contenido del grupo no es válido.")
        grupo = await asyncio.to_thread(
            self._validar_grupo, sha_norm, tuple(rutas), int(keep_index))
        operacion = str(uuid4())
        firma = GrupoFirmado(sha_norm, digest_rutas(grupo[2]), grupo[3], len(grupo[2]))
        token = crear_token_apartar(operacion, (firma,), self._secret)
        return VistaApartado(token, operacion, tuple(grupo[1]), grupo[3],
                             self._bytes_grupo(grupo[0], grupo[1]))

    def _validar_grupo(self, sha: str, rutas: tuple[str | Path, ...],
                       keep_index: int) -> tuple[str, list[Path], list[str], int]:
        _, paths, rels, keep = self._grupo_normalizado(GrupoEntrada(sha, rutas, keep_index))
        if keep >= len(paths):
            raise TokenApartadoInvalido("La copia que se queda no es válida.")
        for p in paths:
            if not p.is_file():
                raise GrupoRechazado("no_existe", "Alguna copia ya no está.")
            if p.stat().st_size <= 0:
                continue
            if awaitable_hash(p) != sha:
                raise GrupoRechazado("contenido_cambiado", "El contenido cambió; vuelve a previsualizar.")
        if paths[keep].stat().st_size != paths[0].stat().st_size:
            raise GrupoRechazado("tamano_distinto", "Las copias ya no son idénticas.")
        for p in paths:
            if p.stat().st_size != paths[keep].stat().st_size:
                raise GrupoRechazado("tamano_distinto", "Las copias ya no son idénticas.")
        return sha, paths, rels, keep

    def _bytes_grupo(self, _sha: str, paths: Sequence[Path]) -> int:
        try:
            return paths[0].stat().st_size * (len(paths) - 1)
        except OSError:
            return 0

    def _base_cuarentena(self, operacion: UUID) -> Path:
        """Cuarentena real, resuelta: nunca fuera de la biblioteca (symlink incluido)."""
        raiz = self._library.resolve()
        base = self._library / ".zascarr" / "apartados" / str(operacion)
        real = base.resolve(strict=False)
        if real != raiz and raiz not in real.parents:
            raise GrupoRechazado("cuarentena_fuera", "La cuarentena queda fuera de la biblioteca.")
        try:
            if real.stat().st_dev != raiz.stat().st_dev:
                raise GrupoRechazado("montura_distinta", "La cuarentena está en otra montura.")
        except FileNotFoundError:
            pass
        return base

    async def _file_original_previo(self, paths: Sequence[Path], keep: int) -> dict | None:
        filas = await self._filas_del_grupo(paths)
        if len(filas) > 1:
            raise GrupoRechazado("catalogo_ambiguo", "El catálogo tiene más de una fila para este grupo.")
        if not filas or filas[0].file_path == str(paths[keep]):
            return None
        fila = filas[0]
        if fila.file_path not in {str(p) for i, p in enumerate(paths) if i != keep}:
            raise GrupoRechazado("catalogo_incoherente", "El catálogo no coincide con las copias.")
        return {"file_id": str(fila.id), "file_path": fila.file_path,
                "file_name": fila.file_name, "file_size_bytes": fila.file_size_bytes,
                "sha256_hash": fila.sha256_hash, "file_mtime_ns": fila.file_mtime_ns}

    async def confirmar(self, token: str, grupos: Sequence[GrupoEntrada | dict] | None = None,
                        *, secret: str | None = None) -> ResultadoApartado:
        """Confirma un token de apartar. No acepta rutas que no estén en el token."""
        firma = self._verificar(token, secret)
        if firma is None:
            raise TokenApartadoInvalido("La propuesta caducó o no es válida.")
        if firma.accion != "apartar":
            raise TokenApartadoInvalido("Este token no es de apartar.")
        entradas = self._coercionar_grupos(grupos)
        if len(entradas) != len(firma.grupos):
            raise TokenApartadoInvalido("Los grupos no coinciden con la propuesta.")
        normalizados = []
        for entrada, firmado in zip(entradas, firma.grupos, strict=False):
            sha, paths, rels, keep = self._grupo_normalizado(entrada)
            if sha != firmado.sha256 or digest_rutas(rels) != firmado.rutas_digest or keep != firmado.keep_index:
                raise TokenApartadoInvalido("Los grupos no coinciden con la propuesta.")
            normalizados.append((sha, paths, rels, keep))
        return await self._confirmar_normalizado(firma, normalizados)

    def _verificar(self, token: str, secret: str | None) -> ApartarFirmada | None:
        clave = self._secret if secret is None else secret
        return verificar_token_apartar(token, clave)

    def _coercionar_grupos(self, grupos) -> list[GrupoEntrada]:
        if grupos is None:
            raise TokenApartadoInvalido("Faltan las rutas de la propuesta.")
        if isinstance(grupos, dict):
            grupos = [grupos]
        resultado = []
        for g in grupos:
            if isinstance(g, GrupoEntrada):
                resultado.append(g)
            elif isinstance(g, dict):
                sha = g.get("sha256", g.get("sha"))
                rutas = g.get("rutas", ())
                keep = g.get("keep_index", g.get("keep"))
                if not isinstance(sha, str) or not isinstance(rutas, (list, tuple)):
                    raise TokenApartadoInvalido("Grupo mal formado.")
                resultado.append(GrupoEntrada(sha, tuple(rutas), int(keep)))
            else:
                raise TokenApartadoInvalido("Grupo mal formado.")
        if len(resultado) > MAX_GRUPOS_APARTAR:
            raise TokenApartadoInvalido("Demasiados grupos para una confirmación.")
        return resultado

    # ── operación durable ─────────────────────────────────────────────────
    async def _cargar_operacion(self, operacion_id: UUID) -> ApartadoOperacion | None:
        resultado = await self._db.execute(
            select(ApartadoOperacion).options(selectinload(ApartadoOperacion.grupos))
            .where(ApartadoOperacion.id == operacion_id))
        return resultado.scalar_one_or_none()

    async def _confirmar_normalizado(self, firma: ApartarFirmada, grupos) -> ResultadoApartado:
        operacion_id = UUID(firma.operacion)
        op = await self._cargar_operacion(operacion_id)
        if op is not None and op.estado in (ApartadoEstado.CONFIRMADA, ApartadoEstado.DESHECHA):
            return self._resultado_guardado(op, idempotente=True)
        if op is not None and op.estado == ApartadoEstado.CANCELADA:
            raise TokenApartadoInvalido("Esta operación se canceló.")
        if op is None:
            op = ApartadoOperacion(
                id=operacion_id, estado=ApartadoEstado.EN_CURSO,
                token_hasta=datetime.fromtimestamp(firma.caduca, UTC),
                total_grupos=len(grupos), total_archivos=sum(len(g[1]) - 1 for g in grupos),
                total_bytes=sum(self._bytes_grupo(g[0], g[1]) for g in grupos),
            )
            self._db.add(op)
            for sha, paths, rels, keep in grupos:
                try:
                    file_original = await self._file_original_previo(paths, keep)
                except GrupoRechazado:
                    file_original = None
                self._db.add(ApartadoGrupo(
                    operacion_id=operacion_id, grupo_clave=sha, sha256=sha,
                    size_bytes=paths[0].stat().st_size, estado=ApartadoGrupoEstado.PENDIENTE,
                    detalle={"keep_index": keep, "rutas": rels, "items": [],
                             "file_original": file_original},
                ))
            await self._db.commit()
            op = await self._cargar_operacion(operacion_id) or op
        else:
            await self._reconciliar(op)
        return await self._procesar_operacion(op)

    async def _procesar_operacion(self, op: ApartadoOperacion) -> ResultadoApartado:
        for grupo in list(op.grupos):
            if grupo.estado in (ApartadoGrupoEstado.MOVIDO, ApartadoGrupoEstado.DESHECHO,
                                 ApartadoGrupoEstado.RECHAZADO, ApartadoGrupoEstado.ERROR):
                if grupo.estado == ApartadoGrupoEstado.MOVIDO:
                    await self._finalizar_grupo_movido(grupo)
                continue
            await self._procesar_grupo(op, grupo)
            await self._db.commit()
        await self._cerrar_operacion(op)
        return self._resultado_guardado(op)

    async def _procesar_grupo(self, op: ApartadoOperacion, grupo: ApartadoGrupo) -> None:
        detalle = dict(grupo.detalle or {})
        rutas_rel = list(detalle.get("rutas") or [])
        keep = int(detalle.get("keep_index", 0))
        movidos: list[tuple[Path, Path]] = []
        try:
            paths = [self._relativa(r)[0] for r in rutas_rel]
            if len(paths) < 2 or not 0 <= keep < len(paths):
                raise GrupoRechazado("grupo_invalido", "El grupo no es válido.")
            previos = {
                item.get("ruta") for item in (detalle.get("items") or [])
                if item.get("estado") == "movido"
            }
            for i, p in enumerate(paths):
                if i != keep and rutas_rel[i] in previos:
                    continue
                if not p.exists():
                    raise GrupoRechazado("no_existe", "Alguna copia ya no está.")
            for i, p in enumerate(paths):
                if i != keep and rutas_rel[i] in previos:
                    continue
                if p.stat().st_size > 0 and await_hash(p) != grupo.sha256:
                    raise GrupoRechazado("contenido_cambiado", "El contenido cambió; no se mueve.")
                if p.stat().st_size != paths[keep].stat().st_size:
                    raise GrupoRechazado("tamano_distinto", "Las copias ya no son idénticas.")
            filas = await self._filas_del_grupo(paths)
            if len(filas) > 1:
                raise GrupoRechazado("catalogo_ambiguo", "El catálogo tiene más de una fila para este grupo.")
            file_original = detalle.get("file_original")
            if file_original is None:
                file_original = await self._file_original_previo(paths, keep)
            destino_base = self._base_cuarentena(op.id)
            if detalle.get("file_original") != file_original:
                detalle["file_original"] = file_original
                grupo.detalle = detalle
                await self._db.commit()  # write-ahead antes de mover
            items_previos = {
                item.get("ruta"): item for item in (detalle.get("items") or [])
                if item.get("estado") == "movido"
            }
            for i, origen in enumerate(paths):
                if i == keep:
                    continue
                rel = Path(rutas_rel[i])
                destino = destino_base / rel
                if rutas_rel[i] in items_previos and destino.exists() and not origen.exists():
                    continue
                if destino.exists():
                    raise GrupoRechazado("destino_ocupado", "La cuarentena ya tiene esa ruta.")
                referencia = destino_base if destino_base.exists() else self._library
                if origen.stat().st_dev != referencia.stat().st_dev:
                    raise GrupoRechazado("montura_distinta", "La cuarentena está en otra montura.")
                destino.parent.mkdir(parents=True, exist_ok=True)
                if origen.stat().st_dev != destino.parent.stat().st_dev:
                    raise GrupoRechazado("montura_distinta", "La cuarentena está en otra montura.")
                try:
                    os.replace(origen, destino)
                except OSError as exc:
                    raise GrupoRechazado("rename_fallido", "No se pudo mover la copia.") from exc
                _fsync_dir(destino.parent)
                _fsync_dir(origen.parent)
                movidos.append((origen, destino))
            if file_original is not None:
                fila = await self._db.get(File, UUID(file_original["file_id"]))
                if fila is not None:
                    stat_keep = paths[keep].stat()
                    fila.file_path = str(paths[keep])
                    fila.file_name = paths[keep].name
                    fila.file_size_bytes = stat_keep.st_size
                    fila.sha256_hash = grupo.sha256
                    fila.file_mtime_ns = stat_keep.st_mtime_ns
            detalle["items"] = [
                {"ruta": rutas_rel[i], "estado": "movido", "destino": str(destino_base / Path(rutas_rel[i]))}
                for i in range(len(paths)) if i != keep
            ]
            detalle["file_original"] = file_original
            grupo.detalle = detalle
            grupo.estado = ApartadoGrupoEstado.MOVIDO
        except GrupoRechazado as exc:
            compensado = await self._compensar_movidos(movidos)
            if not compensado:
                grupo.detalle = {**detalle, "motivo": "compensacion_fallida",
                                 "detalle": "No se pudo devolver una copia ya movida."}
                grupo.estado = ApartadoGrupoEstado.ERROR
            else:
                grupo.detalle = {**detalle, "motivo": exc.motivo, "detalle": exc.detalle}
                grupo.estado = ApartadoGrupoEstado.RECHAZADO
        except (OSError, ValueError) as exc:
            compensado = await self._compensar_movidos(movidos)
            if not compensado:
                grupo.detalle = {**detalle, "motivo": "compensacion_fallida",
                                 "detalle": "No se pudo devolver una copia ya movida."}
                grupo.estado = ApartadoGrupoEstado.ERROR
            else:
                grupo.detalle = {**detalle, "motivo": "error_disco", "detalle": str(exc)}
                grupo.estado = ApartadoGrupoEstado.ERROR

    async def _compensar_movidos(self, movidos: list[tuple[Path, Path]]) -> bool:
        for origen, destino in reversed(movidos):
            try:
                if destino.exists() and not origen.exists():
                    os.replace(destino, origen)
                    _fsync_dir(origen.parent)
            except OSError:
                return False
        return True

    async def _filas_del_grupo(self, paths: Sequence[Path]) -> list[File]:
        resultado = await self._db.execute(select(File).where(File.file_path.in_([str(p) for p in paths])))
        return list(resultado.scalars().all())

    # ── deshacer y reconciliación ─────────────────────────────────────────
    async def deshacer(self, operacion: str | UUID, *, secret: str | None = None) -> ResultadoApartado:
        if not uuid_texto(str(operacion)):
            firma = self._verificar(str(operacion), secret)
            if firma is None or firma.accion != "deshacer":
                raise TokenApartadoInvalido("El token de deshacer no es válido.")
            operacion = firma.operacion
        op = await self._cargar_operacion(UUID(str(operacion)))
        if op is None:
            raise ApartadoError("No existe esa operación de apartado.")
        if op.estado == ApartadoEstado.DESHECHA:
            return self._resultado_guardado(op, idempotente=True)
        if op.estado != ApartadoEstado.CONFIRMADA:
            raise ApartadoError("La operación no está confirmada; no se puede deshacer.")
        movidos = []
        for grupo in op.grupos:
            for item in (grupo.detalle or {}).get("items") or []:
                if item.get("estado") == "movido":
                    original = self._relativa(item["ruta"])[0]
                    cuarentena = Path(item["destino"])
                    if original.exists():
                        return self._resultado_guardado(op, motivo="sitio_ocupado")
                    if not cuarentena.exists():
                        return self._resultado_guardado(op, motivo="cuarentena_ausente")
                    movidos.append((grupo, item, original, cuarentena))
        realizados = []
        try:
            for grupo, item, original, cuarentena in movidos:
                original.parent.mkdir(parents=True, exist_ok=True)
                if original.exists():
                    raise GrupoRechazado("sitio_ocupado", "El sitio original está ocupado.")
                if cuarentena.stat().st_dev != original.parent.stat().st_dev:
                    raise GrupoRechazado("montura_distinta", "La cuarentena está en otra montura.")
                os.replace(cuarentena, original)
                _fsync_dir(original.parent)
                realizados.append((grupo, item, original, cuarentena))
                item["estado"] = "deshecho"
                detalle = grupo.detalle or {}
                original_file = detalle.get("file_original")
                if original_file:
                    fila = await self._db.get(File, UUID(original_file["file_id"]))
                    if fila is not None:
                        fila.file_path = original_file["file_path"]
                        fila.file_name = original_file["file_name"]
                        fila.file_size_bytes = original_file["file_size_bytes"]
                        fila.sha256_hash = original_file["sha256_hash"]
                        fila.file_mtime_ns = original_file["file_mtime_ns"]
                grupo.estado = ApartadoGrupoEstado.DESHECHO
            await self._db.commit()
        except (OSError, GrupoRechazado) as exc:
            for _grupo, item, original, cuarentena in reversed(realizados):
                try:
                    if original.exists() and not cuarentena.exists():
                        cuarentena.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(original, cuarentena)
                        item["estado"] = "movido"
                except OSError:
                    item["estado"] = "error"
            await self._db.commit()
            motivo = getattr(exc, "motivo", "error_disco")
            return self._resultado_guardado(op, motivo=motivo)
        op.estado = ApartadoEstado.DESHECHA
        op.resultado = self._resultado_dict(op)
        await self._db.commit()
        return self._resultado_guardado(op)

    async def _reconciliar(self, op: ApartadoOperacion) -> None:
        """Repara una operación en_curso: nunca anuncia éxito sin releer el disco."""
        for grupo in op.grupos:
            if grupo.estado not in (ApartadoGrupoEstado.PENDIENTE, ApartadoGrupoEstado.MOVIDO):
                continue
            detalle = dict(grupo.detalle or {})
            items = list(detalle.get("items") or [])
            rutas_rel = list(detalle.get("rutas") or [])
            keep = int(detalle.get("keep_index", 0))
            base = self._base_cuarentena(op.id)
            if not detalle.get("file_original"):
                try:
                    detalle["file_original"] = await self._file_original_previo(
                        [self._relativa(r)[0] for r in rutas_rel], keep)
                except GrupoRechazado:
                    detalle["file_original"] = None
            if not items and rutas_rel:
                items = [
                    {"ruta": rel, "estado": "pendiente", "destino": str(base / Path(rel))}
                    for i, rel in enumerate(rutas_rel) if i != keep
                ]
            movidos = 0
            for item in items:
                if item.get("estado") == "movido":
                    movidos += 1
                    continue
                origen = self._relativa(item["ruta"])[0]
                destino = Path(item["destino"])
                if not origen.exists() and destino.exists():
                    item["estado"] = "movido"
                    movidos += 1
            detalle["items"] = items
            grupo.detalle = detalle
            if movidos and movidos == len(items):
                grupo.estado = ApartadoGrupoEstado.MOVIDO
        await self._db.commit()

    async def _finalizar_grupo_movido(self, grupo: ApartadoGrupo) -> None:
        detalle = grupo.detalle or {}
        if not detalle.get("file_original"):
            return
        original = detalle["file_original"]
        fila = await self._db.get(File, UUID(original["file_id"]))
        if fila is None:
            return
        rutas = detalle.get("rutas") or []
        keep = int(detalle.get("keep_index", 0))
        if 0 <= keep < len(rutas):
            destino = self._relativa(rutas[keep])[0]
            if destino.exists():
                st = destino.stat()
                fila.file_path = str(destino)
                fila.file_name = destino.name
                fila.file_size_bytes = st.st_size
                fila.sha256_hash = grupo.sha256
                fila.file_mtime_ns = st.st_mtime_ns

    async def _cerrar_operacion(self, op: ApartadoOperacion) -> None:
        if any(g.estado == ApartadoGrupoEstado.PENDIENTE for g in op.grupos):
            return
        if any(g.estado == ApartadoGrupoEstado.ERROR for g in op.grupos):
            # Fallo incierto: queda en_curso para recuperación; nunca éxito falso.
            op.estado = ApartadoEstado.EN_CURSO
        else:
            op.estado = ApartadoEstado.CONFIRMADA
        op.resultado = self._resultado_dict(op)
        op.actualizada = datetime.now(UTC)
        await self._db.commit()

    def _resultado_dict(self, op: ApartadoOperacion, motivo: str | None = None) -> dict:
        grupos = []
        for g in op.grupos:
            detalle = g.detalle or {}
            grupos.append({
                "grupo_clave": g.grupo_clave,
                "estado": g.estado.value if hasattr(g.estado, "value") else g.estado,
                "motivo": detalle.get("motivo"), "items": detalle.get("items", []),
            })
        return {"estado": op.estado.value if hasattr(op.estado, "value") else op.estado,
                "grupos": grupos, "motivo": motivo}

    def _resultado_guardado(self, op: ApartadoOperacion, *, motivo: str | None = None,
                            idempotente: bool = False) -> ResultadoApartado:
        grupos = []
        for g in op.grupos:
            detalle = g.detalle or {}
            movidos = [i for i in detalle.get("items", []) if i.get("estado") == "movido"]
            grupos.append(ResultadoGrupo(
                g.grupo_clave, g.estado.value if hasattr(g.estado, "value") else g.estado,
                detalle.get("motivo"), len(movidos), g.size_bytes * len(movidos),
                bool(detalle.get("file_original")),
            ))
        return ResultadoApartado(
            str(op.id), op.estado.value if hasattr(op.estado, "value") else op.estado,
            grupos, op.total_grupos, op.total_archivos, op.total_bytes, idempotente, motivo)


# Alias de compatibilidad con el nombre corto que usa la especificación.
ApartadoDuplicados = ApartadoDuplicadosService


# ── helpers de hash (sin abrir imágenes, en streaming) ──────────────────────
def await_hash(path: Path) -> str:
    return sha256_streaming(path)


def awaitable_hash(path: Path) -> str:
    return sha256_streaming(path)


def comprobante_para_token(token: str, secret: str) -> ApartarFirmada | None:
    """Atajo de lectura para pruebas/UI sin inyectar el servicio."""
    return verificar_token_apartar(token, secret)
