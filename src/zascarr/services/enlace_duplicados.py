# ruff: noqa: E501, N818
"""BL-DUP2 (#265): unir copias idénticas con enlaces duros.

Cada copia sobrante pasa por la cuarentena de BL-DUP1 y en su ruta se publica
un enlace duro a la copia que se queda. Las dos rutas siguen existiendo, pero
comparten inodo cuando la cuarentena se vacíe. No se borra nada, no se toca el
contenido y la operación se puede deshacer mientras la cuarentena siga ahí.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from zascarr.models import (
    ApartadoEstado,
    ApartadoGrupo,
    ApartadoGrupoEstado,
    ApartadoOperacion,
)
from zascarr.services.apartado_duplicados import (
    ApartadoDuplicadosService,
    GrupoEntrada,
    GrupoRechazado,
    ResultadoGrupo,
    TokenApartadoInvalido,
    VistaApartado,
    _fsync_dir,
    await_hash,
    digest_rutas,
)
from zascarr.services.tokens_revision import (
    GrupoFirmado,
    crear_token_enlazar,
    verificar_token_enlazar,
)

MODO_ENLACE = "enlazar"


@dataclass
class ResultadoEnlace:
    operacion: str
    estado: str
    grupos: list[ResultadoGrupo]
    total_grupos: int = 0
    total_archivos: int = 0
    total_bytes: int = 0
    idempotente: bool = False
    motivo: str | None = None


class EnlaceDuplicadosService(ApartadoDuplicadosService):
    """Une copias idénticas con enlaces duros, reutilizando cuarentena y comprobantes."""

    # ── vista previa ──────────────────────────────────────────────────────
    async def previsualizar(self, sha: str, rutas, keep_index: int) -> VistaApartado:
        sha_norm = (sha or "").lower()
        if len(sha_norm) != 64 or any(c not in "0123456789abcdef" for c in sha_norm):
            raise TokenApartadoInvalido("El contenido del grupo no es válido.")
        grupo = await asyncio.to_thread(
            self._validar_enlace, sha_norm, tuple(rutas), int(keep_index))
        operacion = str(uuid4())
        firma = GrupoFirmado(sha_norm, digest_rutas(grupo[2]), grupo[3], len(grupo[2]))
        token = crear_token_enlazar(operacion, (firma,), self._secret)
        return VistaApartado(token, operacion, tuple(grupo[1]), grupo[3],
                             self._bytes_grupo(grupo[0], grupo[1]))

    def _validar_enlace(self, sha: str, rutas, keep_index: int):
        _, paths, rels, keep = self._grupo_normalizado(GrupoEntrada(sha, rutas, keep_index))
        if keep >= len(paths):
            raise TokenApartadoInvalido("La copia que se queda no es válida.")
        for p in paths:
            if not p.is_file() or p.is_symlink():
                raise GrupoRechazado("no_regular", "Alguna copia ya no está o es un enlace simbólico.")
            if p.stat().st_size <= 0:
                raise GrupoRechazado("vacio", "Alguna copia está vacía.")
            if await_hash(p) != sha:
                raise GrupoRechazado("contenido_cambiado", "El contenido cambió; vuelve a previsualizar.")
        if len({p.stat().st_dev for p in paths}) != 1:
            raise GrupoRechazado("montura_distinta", "Las copias están en discos distintos.")
        if paths[keep].stat().st_size != paths[0].stat().st_size:
            raise GrupoRechazado("tamano_distinto", "Las copias ya no son idénticas.")
        return sha, paths, rels, keep

    # ── token y confirmación ──────────────────────────────────────────────
    def _verificar(self, token: str, secret: str | None = None):
        return verificar_token_enlazar(token, self._secret if secret is None else secret)

    async def confirmar(self, token: str, grupos=None, *, secret: str | None = None) -> ResultadoEnlace:
        firma = self._verificar(token, secret)
        if firma is None:
            raise TokenApartadoInvalido("La propuesta caducó o no es válida.")
        if firma.accion != "enlazar":
            raise TokenApartadoInvalido("Este token no es de enlazar.")
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

    async def _confirmar_normalizado(self, firma, grupos) -> ResultadoEnlace:
        operacion_id = UUID(firma.operacion)
        op = await self._cargar_operacion(operacion_id)
        if op is not None and op.modo != MODO_ENLACE:
            raise TokenApartadoInvalido("Esa operación no es de enlace.")
        if op is not None and op.estado in (ApartadoEstado.CONFIRMADA, ApartadoEstado.DESHECHA,
                                             ApartadoEstado.CANCELADA):
            return self._resultado_guardado(op, idempotente=True)
        if op is None:
            op = ApartadoOperacion(
                id=operacion_id, modo=MODO_ENLACE, estado=ApartadoEstado.EN_CURSO,
                token_hasta=datetime.fromtimestamp(firma.caduca, UTC),
                total_grupos=len(grupos),
                total_archivos=sum(len(g[1]) - 1 for g in grupos),
                total_bytes=sum(self._bytes_grupo(g[0], g[1]) for g in grupos),
            )
            self._db.add(op)
            for sha, paths, rels, keep in grupos:
                self._db.add(ApartadoGrupo(
                    operacion_id=operacion_id, grupo_clave=sha, sha256=sha,
                    size_bytes=paths[0].stat().st_size,
                    estado=ApartadoGrupoEstado.PENDIENTE,
                    detalle={"keep_index": keep, "rutas": rels, "items": []},
                ))
            await self._db.commit()
            op = await self._cargar_operacion(operacion_id) or op
        await self._reconciliar(op)
        return await self._procesar_operacion(op)

    async def _reconciliar(self, op: ApartadoOperacion) -> None:
        """Tras un corte, deja el detalle listo sin duplicar enlaces."""
        for grupo in op.grupos:
            if grupo.estado not in (ApartadoGrupoEstado.PENDIENTE, ApartadoGrupoEstado.MOVIDO):
                continue
            detalle = dict(grupo.detalle or {})
            rutas = list(detalle.get("rutas") or [])
            keep = int(detalle.get("keep_index", 0))
            items = list(detalle.get("items") or [])
            # Normaliza operaciones antiguas (sin items) a pendientes.
            if not items:
                items = [{"ruta": rel, "destino": str(self._base_cuarentena(op.id) / Path(rel)),
                          "estado": "pendiente"} for i, rel in enumerate(rutas) if i != keep]
            for item in items:
                if item.get("estado") == "enlazado":
                    continue
                origen = self._relativa(item["ruta"])[0]
                destino = Path(item["destino"])
                keep_path = self._relativa(rutas[keep])[0] if rutas else None
                if origen.exists() and destino.exists() and keep_path is not None:
                    try:
                        if origen.stat().st_ino == keep_path.stat().st_ino:
                            item["estado"] = "enlazado"
                    except OSError:
                        pass
                elif not origen.exists() and destino.exists():
                    item["estado"] = "hecho_pendiente"
            detalle["items"] = items
            grupo.detalle = detalle
        await self._db.commit()

    async def _procesar_operacion(self, op: ApartadoOperacion) -> ResultadoEnlace:
        for grupo in list(op.grupos):
            if grupo.estado in (ApartadoGrupoEstado.MOVIDO, ApartadoGrupoEstado.DESHECHO,
                                 ApartadoGrupoEstado.RECHAZADO, ApartadoGrupoEstado.ERROR):
                continue
            await self._procesar_grupo(op, grupo)
            await self._db.commit()
        await self._cerrar(op)
        return self._resultado_guardado(op)

    async def _procesar_grupo(self, op: ApartadoOperacion, grupo: ApartadoGrupo) -> None:
        detalle = dict(grupo.detalle or {})
        rutas = list(detalle.get("rutas") or [])
        keep = int(detalle.get("keep_index", 0))
        items = list(detalle.get("items") or [])
        try:
            if len(rutas) < 2 or not 0 <= keep < len(rutas):
                raise GrupoRechazado("grupo_invalido", "El grupo no es válido.")
            paths = [self._relativa(r)[0] for r in rutas]
            # Revalidación justo antes de tocar el disco (hash fuera del bucle async).
            await asyncio.to_thread(self._validar_enlace, grupo.sha256, tuple(paths), keep)
            filas = await self._filas_del_grupo(paths)
            if len(filas) > 1:
                raise GrupoRechazado("catalogo_ambiguo", "El catálogo tiene más de una fila para este grupo.")
            if filas and filas[0].file_path not in {str(p) for p in paths}:
                raise GrupoRechazado("catalogo_incoherente", "El catálogo no coincide con las copias.")
            keep_path = paths[keep]
            base = self._base_cuarentena(op.id)
            file_original = await self._file_original_previo(paths, keep)
            # Verifica la misma montura antes de crear el enlace.
            ref = base if base.exists() else self._library
            if any(p.stat().st_dev != ref.stat().st_dev for p in paths):
                raise GrupoRechazado("montura_distinta", "Las copias o la cuarentena están en otra montura.")
            for i, origen in enumerate(paths):
                if i == keep:
                    continue
                if items and any(x.get("ruta") == rutas[i] and x.get("estado") == "enlazado" for x in items):
                    continue
                destino = base / Path(rutas[i])
                if destino.exists():
                    raise GrupoRechazado("destino_ocupado", "La cuarentena ya tiene esa ruta.")
                tmp = origen.with_name(f".{origen.name}.zascarr-enlace-{uuid4().hex}")
                if tmp.exists():
                    raise GrupoRechazado("destino_ocupado", "No se pudo reservar el temporal.")
                try:
                    os.link(keep_path, tmp, follow_symlinks=False)
                except OSError as exc:
                    raise GrupoRechazado("montura_distinta", "No se pudo crear el enlace duro.") from exc
                try:
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(origen, destino)
                    _fsync_dir(destino.parent)
                    os.replace(tmp, origen)
                    _fsync_dir(origen.parent)
                except OSError as exc:
                    with suppress(OSError):
                        tmp.unlink(missing_ok=True)
                    if destino.exists() and not origen.exists():
                        try:
                            os.replace(destino, origen)
                        except OSError:
                            raise GrupoRechazado("error_disco", "No se pudo restaurar la copia.") from exc
                    raise GrupoRechazado("error_disco", "No se pudo publicar el enlace.") from exc
                item = next((x for x in items if x.get("ruta") == rutas[i]), None)
                if item is None:
                    item = {"ruta": rutas[i]}
                    items.append(item)
                item.update({"destino": str(destino), "estado": "enlazado", "ruta_keep": rutas[keep]})
                detalle["items"] = items
            detalle["file_original"] = file_original
            detalle["items"] = items
            grupo.detalle = detalle
            grupo.estado = ApartadoGrupoEstado.MOVIDO
        except GrupoRechazado as exc:
            compensado = await self._compensar_enlazados(items)
            if not compensado:
                grupo.detalle = {**detalle, "items": items, "motivo": "compensacion_fallida",
                                 "detalle": "No se pudo devolver un enlace ya hecho."}
                grupo.estado = ApartadoGrupoEstado.ERROR
            else:
                grupo.detalle = {**detalle, "items": items, "motivo": exc.motivo,
                                 "detalle": exc.detalle}
                grupo.estado = ApartadoGrupoEstado.RECHAZADO
        except (OSError, ValueError) as exc:
            compensado = await self._compensar_enlazados(items)
            if not compensado:
                grupo.detalle = {**detalle, "items": items, "motivo": "compensacion_fallida",
                                 "detalle": "No se pudo devolver un enlace ya hecho."}
                grupo.estado = ApartadoGrupoEstado.ERROR
            else:
                grupo.detalle = {**detalle, "items": items, "motivo": "error_disco",
                                 "detalle": str(exc)}
                grupo.estado = ApartadoGrupoEstado.ERROR

    async def _compensar_enlazados(self, items: list[dict]) -> bool:
        """Devuelve las copias ya enlazadas del mismo grupo; nunca sobrescribe."""
        for item in reversed(items):
            if item.get("estado") != "enlazado":
                continue
            try:
                original = self._relativa(item["ruta"])[0]
                cuarentena = Path(item["destino"])
                if original.exists() and cuarentena.exists():
                    original.unlink()
                    os.replace(cuarentena, original)
                    _fsync_dir(original.parent)
                    item["estado"] = "deshecho"
            except OSError:
                return False
        return True

    async def _cerrar(self, op: ApartadoOperacion) -> None:
        enlazados = 0
        bytes_ = 0
        for g in op.grupos:
            n = sum(1 for i in (g.detalle or {}).get("items", []) if i.get("estado") == "enlazado")
            enlazados += n
            bytes_ += n * g.size_bytes
        op.total_archivos = enlazados
        op.total_bytes = bytes_
        if enlazados == 0:
            op.estado = ApartadoEstado.CANCELADA
        elif any(g.estado == ApartadoGrupoEstado.ERROR for g in op.grupos):
            op.estado = ApartadoEstado.EN_CURSO
        else:
            op.estado = ApartadoEstado.CONFIRMADA
        op.resultado = self._resultado_dict(op)
        op.actualizada = datetime.now(UTC)
        await self._db.commit()

    def _resultado_guardado(self, op: ApartadoOperacion, *, motivo: str | None = None,
                            idempotente: bool = False) -> ResultadoEnlace:
        grupos = []
        for g in op.grupos:
            detalle = g.detalle or {}
            n = sum(1 for i in detalle.get("items", []) if i.get("estado") in ("enlazado", "deshecho"))
            grupos.append(ResultadoGrupo(
                g.grupo_clave, g.estado.value if hasattr(g.estado, "value") else g.estado,
                detalle.get("motivo"), n, g.size_bytes * n, False))
        if motivo is None and op.resultado:
            motivo = op.resultado.get("motivo")
        return ResultadoEnlace(
            str(op.id), op.estado.value if hasattr(op.estado, "value") else op.estado,
            grupos, op.total_grupos, op.total_archivos, op.total_bytes, idempotente, motivo)

    async def deshacer(self, operacion: str | UUID, *, secret: str | None = None) -> ResultadoEnlace:
        if not isinstance(operacion, UUID):
            try:
                operacion = UUID(str(operacion))
            except ValueError as exc:
                raise TokenApartadoInvalido("La operación de enlace no es válida.") from exc
        op = await self._cargar_operacion(operacion)
        if op is None or op.modo != MODO_ENLACE:
            raise TokenApartadoInvalido("No existe esa operación de enlace.")
        if op.estado == ApartadoEstado.DESHECHA:
            return self._resultado_guardado(op, idempotente=True)
        if op.estado != ApartadoEstado.CONFIRMADA:
            raise TokenApartadoInvalido("La operación no está confirmada; no se puede deshacer.")
        for grupo in op.grupos:
            detalle = dict(grupo.detalle or {})
            for item in detalle.get("items") or []:
                if item.get("estado") != "enlazado":
                    continue
                original = self._relativa(item["ruta"])[0]
                keep = self._relativa(item["ruta_keep"])[0]
                cuarentena = Path(item["destino"])
                if not original.exists() or not keep.exists() or not cuarentena.exists():
                    raise TokenApartadoInvalido("Alguna copia ya no está; no se deshace a ciegas.")
                if original.stat().st_ino != keep.stat().st_ino:
                    raise TokenApartadoInvalido("La copia original cambió; no se sobrescribe.")
                if original.stat().st_dev != cuarentena.stat().st_dev:
                    raise TokenApartadoInvalido("La cuarentena está en otra montura.")
                original.unlink()
                try:
                    os.replace(cuarentena, original)
                    _fsync_dir(original.parent)
                except OSError as exc:
                    raise TokenApartadoInvalido("No se pudo devolver la copia original.") from exc
                item["estado"] = "deshecho"
            grupo.detalle = detalle
            grupo.estado = ApartadoGrupoEstado.DESHECHO
        op.estado = ApartadoEstado.DESHECHA
        op.resultado = self._resultado_dict(op)
        await self._db.commit()
        return self._resultado_guardado(op)
