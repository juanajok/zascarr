"""Borradores explícitos de una revisión de carpeta (#725).

No es una selección válida: solo conserva marcas y números escritos por la
persona para que pueda cerrar la página y reanudar después. El asistente
siempre vuelve a evaluar el borrador contra el servicio; aquí no se decide
ninguna vinculación.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import RevisionBorrador
from zascarr.services.tokens_revision import MAX_CLAVE_GRUPO

TTL = timedelta(days=7)
MAX_PAGINAS = 100
MAX_IDS = 1000
MAX_NUMERO = 100
MAX_BYTES = 200_000


class BorradorNoValidoError(ValueError):
    """El formulario no tiene la forma mínima para guardarse."""


@dataclass(frozen=True)
class BorradorGuardado:
    paginas: dict[str, dict]
    cursor: str
    actualizado: datetime

    @property
    def total_marcados(self) -> int:
        return sum(len(set(p.get("marcados", []))) for p in self.paginas.values())


def _limpio(clave: str, series_id: str, cursor: str, paginas: dict) -> tuple[str, UUID, str, dict]:
    if not clave or len(clave) > MAX_CLAVE_GRUPO:
        raise BorradorNoValidoError("La carpeta no es válida.")
    try:
        sid = UUID(series_id)
    except (ValueError, TypeError) as exc:
        raise BorradorNoValidoError("La serie no es válida.") from exc
    if not isinstance(paginas, dict) or len(paginas) > MAX_PAGINAS:
        raise BorradorNoValidoError("Hay demasiadas páginas en el borrador.")
    salida: dict[str, dict] = {}
    for pagina, b in paginas.items():
        if not isinstance(pagina, str) or len(pagina) > 2000 or not isinstance(b, dict):
            raise BorradorNoValidoError("Una página del borrador no es válida.")
        marcados = b.get("marcados", [])
        numeros = b.get("numeros", {})
        desde, hasta = b.get("desde", 0), b.get("hasta", 0)
        if not isinstance(marcados, list) or len(marcados) > MAX_IDS:
            raise BorradorNoValidoError("Hay demasiadas marcas en una página.")
        if not isinstance(numeros, dict) or len(numeros) > MAX_IDS:
            raise BorradorNoValidoError("Hay demasiados números en una página.")
        try:
            marcados_ok = sorted({str(UUID(str(x))) for x in marcados})
            numeros_ok = {str(UUID(str(k))): str(v) for k, v in numeros.items()
                          if len(str(v)) <= MAX_NUMERO}
        except (ValueError, TypeError) as exc:
            raise BorradorNoValidoError("El borrador contiene identificadores no válidos.") from exc
        if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 0
                   for n in (desde, hasta)):
            raise BorradorNoValidoError("La posición de la página no es válida.")
        salida[pagina] = {"marcados": marcados_ok, "numeros": numeros_ok,
                          "desde": desde, "hasta": hasta}
    if not cursor or len(cursor) > 2000:
        raise BorradorNoValidoError("El cursor de la página no es válido.")
    datos = json.dumps({"cursor": cursor, "paginas": salida}, ensure_ascii=False)
    if len(datos.encode("utf-8")) > MAX_BYTES:
        raise BorradorNoValidoError("El borrador es demasiado grande.")
    return clave, sid, cursor, json.loads(datos)


class BorradoresRevision:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def guardar(self, *, clave: str, series_id: str, cursor: str,
                      paginas: dict) -> BorradorGuardado:
        clave, sid, cursor, datos = _limpio(clave, series_id, cursor, paginas)
        ahora = datetime.now(UTC)
        await self.db.execute(
            pg_insert(RevisionBorrador).values(
                clave=clave, series_id=sid, datos=datos,
                actualizado=ahora, caduca=ahora + TTL,
            ).on_conflict_do_update(
                index_elements=["clave", "series_id"],
                set_={"datos": datos, "actualizado": ahora, "caduca": ahora + TTL},
            )
        )
        return BorradorGuardado(paginas=datos["paginas"], cursor=cursor, actualizado=ahora)

    async def obtener(self, *, clave: str, series_id: str) -> BorradorGuardado | None:
        if not clave or len(clave) > MAX_CLAVE_GRUPO:
            return None
        try:
            sid = UUID(series_id)
        except (ValueError, TypeError):
            return None
        fila = (await self.db.execute(
            sa.select(RevisionBorrador).where(
                RevisionBorrador.clave == clave, RevisionBorrador.series_id == sid)
        )).scalar_one_or_none()
        if fila is None:
            return None
        if fila.caduca <= datetime.now(UTC):
            await self.db.delete(fila)
            return None
        datos = fila.datos if isinstance(fila.datos, dict) else {}
        paginas = datos.get("paginas") if isinstance(datos.get("paginas"), dict) else {}
        cursor = datos.get("cursor") if isinstance(datos.get("cursor"), str) else ""
        if not paginas or not cursor:
            await self.db.delete(fila)
            return None
        return BorradorGuardado(paginas=paginas, cursor=cursor, actualizado=fila.actualizado)

    async def borrar(self, *, clave: str, series_id: str) -> None:
        try:
            sid = UUID(series_id)
        except (ValueError, TypeError):
            return
        await self.db.execute(sa.delete(RevisionBorrador).where(
            RevisionBorrador.clave == clave, RevisionBorrador.series_id == sid))
