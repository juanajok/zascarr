"""B20: API de exportación de una colección a un árbol Kavita."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.exportacion_kavita import ExportacionError, exportar_coleccion

router = APIRouter(prefix="/export", tags=["exportacion"])


class ExportacionBody(BaseModel):
    patch_comicinfo: bool = False
    copiar: bool = False


@router.post("/collections/{collection_id}")
async def exportar(collection_id: UUID, body: ExportacionBody | None = None,
                   db: AsyncSession = Depends(get_db)) -> dict:
    """Exporta la colección. La raíz es siempre `export_path` (`/media/export`)."""
    peticion = body or ExportacionBody()
    try:
        resumen = await exportar_coleccion(
            db, collection_id, patch_comicinfo=peticion.patch_comicinfo,
            copiar=peticion.copiar)
    except ExportacionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await db.commit()
    return {
        "run_id": resumen.run_id,
        "collection_id": resumen.collection_id,
        "destino": resumen.destino,
        "resumen": {
            "materializados": resumen.materializados,
            "omitidos": resumen.omitidos,
            "colisiones": resumen.colisiones,
            "deriva": resumen.deriva,
            "errores": resumen.errores,
            "bytes_copiados": resumen.bytes_copiados,
            "saltados": resumen.saltados,
            "modo": resumen.modo,
            "carpetas_colisionadas": resumen.carpetas_colisionadas,
            "parcheados": resumen.parcheados,
            "patch_no_escribible": resumen.patch_no_escribible,
        },
    }
