"""#344 BL-PACK1 corte 4: publicar e importar un paquete verificado.

El original no se toca nunca. La carpeta publicada va a Descargas y el importer normal la procesa;
el paquete queda suprimido de pendientes por su identidad mientras siga igual.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import PaqueteEstado, PaqueteOperacion
from zascarr.services.asignacion import _renameat2_noreplace
from zascarr.services.importer import Importer

logger = structlog.get_logger()


class PaquetePublicacionError(Exception):
    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


def _descargas() -> Path:
    a = get_settings()
    for valor in (a.transmission_download_dir, a.amule_incoming_dir, a.downloads_path):
        if valor:
            p = Path(valor)
            if p.is_dir():
                return p
    raise PaquetePublicacionError("sin_descargas", "No hay una carpeta de Descargas disponible.")


def _nombre_libre(base: Path, nombre: str) -> Path:
    destino = base / f"{nombre} (extraído)"
    n = 1
    while destino.exists():
        destino = base / f"{nombre} (extraído) ({n})"
        n += 1
    return destino


async def publicar_e_importar(s: AsyncSession, operacion_id: UUID) -> PaqueteOperacion:
    op = await s.get(PaqueteOperacion, operacion_id, with_for_update=True)
    if op is None:
        raise PaquetePublicacionError("no_existe", "La operación no existe.")
    if op.estado is PaqueteEstado.IMPORTADO:
        return op
    if op.estado is not PaqueteEstado.VERIFICADO:
        raise PaquetePublicacionError("estado", "El paquete aún no está verificado.")
    temp = Path(op.temp_dir) if op.temp_dir else None
    if temp is None or not temp.is_dir():
        raise PaquetePublicacionError("sin_temporal", "No queda contenido extraído.")
    descargas = _descargas()
    staging = descargas / ".zascarr" / "paquetes" / str(op.id)
    final = _nombre_libre(descargas, Path(op.paquete_path).stem)
    try:
        staging.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(staging.parent, 0o700)  # noqa: S103 — carpeta propia
        staging.mkdir(mode=0o700)
        st_staging = staging.lstat()
        if not stat.S_ISDIR(st_staging.st_mode) or staging.is_symlink():
            raise PaquetePublicacionError("staging", "La carpeta temporal no es segura.")
        op.estado = PaqueteEstado.PUBLICANDO
        op.staging_dir = str(staging)
        op.destino_dir = str(final)
        s.add(op)
        await s.commit()
        for item in op.items:
            origen = temp / item["nombre"]
            if not origen.is_file() or origen.is_symlink():
                raise PaquetePublicacionError("item", "Falta un tebeo extraído.")
            shutil.copy2(origen, staging / item["nombre"])
        try:
            _renameat2_noreplace(staging, final)
        except FileExistsError:
            final = _nombre_libre(descargas, Path(op.paquete_path).stem + " bis")
            _renameat2_noreplace(staging, final)
            op.destino_dir = str(final)
        op.estado = PaqueteEstado.IMPORTANDO
        s.add(op)
        await s.commit()
        importador = Importer(s)
        importador._scan_dirs = [final]
        reporte = await importador.scan_and_import(disparador="paquete")
        por_nombre = {Path(x).name: "importado" for x in reporte.imported}
        por_nombre.update({Path(x).name: "duplicado" for x in reporte.duplicates})
        por_nombre.update({Path(x).name: "revisar" for x in reporte.unsorted})
        por_nombre.update({Path(x).name: "error" for x in reporte.errors})
        items = []
        for item in op.items:
            nuevo = dict(item)
            nuevo["resultado"] = por_nombre.get(item["nombre"], "revisar")
            items.append(nuevo)
        op.items = items
        if not reporte.errors and any(i["resultado"] == "importado" for i in items):
            op.estado = PaqueteEstado.IMPORTADO
            op.finalizada = datetime.now(UTC)
        else:
            op.estado = PaqueteEstado.ERROR
            op.error_codigo = "importacion"
            op.error_mensaje = "La importación no terminó correctamente; se puede reintentar."
        s.add(op)
        await s.commit()
        await asyncio.to_thread(shutil.rmtree, temp, True)
        await asyncio.to_thread(shutil.rmtree, staging, True)
        return op
    except BaseException as exc:
        await s.rollback()
        op = await s.get(PaqueteOperacion, operacion_id)
        if op is not None:
            op.estado = PaqueteEstado.ERROR
            op.error_codigo = getattr(exc, "codigo", "publicacion")
            op.error_mensaje = getattr(exc, "mensaje", "No se pudo publicar el paquete.")
            s.add(op)
            await s.commit()
        if staging.exists():
            await asyncio.to_thread(shutil.rmtree, staging, True)
        raise
