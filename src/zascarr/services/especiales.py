"""Alta manual de una publicación sin número editorial.

Un especial o tomo puede ser una publicación identificable por título y
formato aunque no tenga un número en el nombre. Se representa con un `Issue`
normal de `issue_number=NULL`; el archivo se enlaza sin moverlo.

No crea Issues el matcher: este camino es SOLO manual. Ver ADR 0016.
"""
from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, Issue, IssueFormat, Series

#: Formatos que puede declarar una persona para un especial/tomo sin número.
FORMATOS_ESPECIAL = (
    IssueFormat.GRAPHIC_NOVEL,
    IssueFormat.TRADE_PAPERBACK,
    IssueFormat.HARDCOVER,
    IssueFormat.OMNIBUS,
)


class EspecialSinNumeroError(ValueError):
    """El archivo, la serie, el título o el formato no permiten el alta."""


#: Tope de números cubiertos por un tomo (evita un rango absurdo por error).
MAX_NUMEROS_CUBIERTOS = 300


def parsear_rango_de_numeros(texto: str) -> list[str]:
    """«1-12», «1,3,5-7» → ['1','2',…,'12'] (ordenado, sin repetir).

    Solo enteros no negativos; un rango invertido se rechaza en vez de inventarlo.
    """
    limpio = (texto or "").strip()
    if not limpio:
        return []
    numeros: set[int] = set()
    for trozo in re.split(r"[\s,;]+", limpio):
        if not trozo:
            continue
        if "-" in trozo:
            partes = trozo.split("-")
            if len(partes) != 2 or not all(p.isdigit() for p in partes):
                raise EspecialSinNumeroError(f"Número o rango no válido: {trozo}")
            inicio, fin = int(partes[0]), int(partes[1])
            if fin < inicio:
                raise EspecialSinNumeroError(f"Rango invertido: {trozo}")
            if fin - inicio + 1 > MAX_NUMEROS_CUBIERTOS:
                raise EspecialSinNumeroError(
                    f"El rango {trozo} es demasiado grande")
            numeros.update(range(inicio, fin + 1))
        else:
            if not trozo.isdigit():
                raise EspecialSinNumeroError(f"Número no válido: {trozo}")
            numeros.add(int(trozo))
    if len(numeros) > MAX_NUMEROS_CUBIERTOS:
        raise EspecialSinNumeroError("Demasiados números cubiertos")
    return [str(n) for n in sorted(numeros)]


class EspecialesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def vincular_especial(
        self,
        file_id,
        series_id,
        titulo: str,
        formato: IssueFormat | str = IssueFormat.GRAPHIC_NOVEL,
        *,
        mover: bool = False,
        numeros_cubiertos: str = "",
    ) -> Issue:
        """Crea (o reutiliza) un Issue sin número y enlaza el archivo.

        Con `mover=True` lo mueve a `…/{Serie (Año)}/Especiales/{archivo}` (carpeta
        de la serie, creada si no existe). Sin `mover`, no toca el archivo. El
        llamador es responsable del commit; este servicio solo hace flush.

        `numeros_cubiertos` («1-12», «1,3,5-7») marca que este tomo recopila esos
        números: pasan a contarse como poseídos (dejan de ser huecos).
        """
        titulo = (titulo or "").strip()
        if not titulo:
            raise EspecialSinNumeroError("El título del especial no puede estar vacío")
        if len(titulo) > 500:
            raise EspecialSinNumeroError("El título del especial es demasiado largo")

        try:
            formato_issue = IssueFormat(formato)
        except ValueError as exc:
            raise EspecialSinNumeroError(f"Formato de especial no válido: {formato}") from exc
        if formato_issue not in FORMATOS_ESPECIAL:
            raise EspecialSinNumeroError(
                "Un especial sin número no puede ser single_issue; "
                "indica graphic_novel, trade_paperback, hardcover u omnibus"
            )

        archivo = await self.db.get(File, file_id)
        if archivo is None:
            raise EspecialSinNumeroError("Archivo no encontrado")
        if archivo.issue_id is not None:
            raise EspecialSinNumeroError("El archivo ya está enlazado a un Issue")

        serie = await self.db.get(Series, series_id)
        if serie is None:
            raise EspecialSinNumeroError("Serie no encontrada")

        issue = Issue(
            series_id=serie.id,
            issue_number=None,
            title=titulo,
            format=formato_issue,
            locked_fields=["series_id"],
            metadata_={"sin_numero": True, "origen": "manual"},
            metadata_source="manual",
        )
        self.db.add(issue)
        await self.db.flush()

        cubiertos = parsear_rango_de_numeros(numeros_cubiertos)
        archivo.issue_id = issue.id
        archivo.metadata_ = {
            **(archivo.metadata_ or {}),
            "sin_numero": True,
            "match_status": "manual_especial",
        }
        if cubiertos:
            archivo.metadata_["numeros_cubiertos"] = cubiertos
            await self._marcar_numeros_cubiertos(serie.id, cubiertos, archivo.id)

        if mover:
            from zascarr.services.importer import build_library_path
            from zascarr.services.raices import raiz_por_tradicion
            from zascarr.utils.fs import safe_move_async

            raiz = await raiz_por_tradicion(self.db, serie.tradition)
            if raiz is None:
                raise EspecialSinNumeroError(
                    "No hay una raíz de biblioteca activa para esa tradición")
            origen = Path(archivo.file_path)
            destino = build_library_path(
                Path(raiz.path), serie, None, origen.suffix,
                fallback_name=origen.name, especial=True)
            final = await safe_move_async(origen, destino)
            archivo.file_path = str(final)
            archivo.file_name = final.name

        await self.db.flush()
        return issue

    async def _marcar_numeros_cubiertos(self, series_id, numeros: list[str],
                                        file_id) -> None:
        """Marca en cada Issue cubierto que un tomo lo recopila.

        Si el número no existe en el catálogo de la serie se crea una fila mínima
        (sin título) para poder contarlo; no se inventa un archivo. La consulta de
        «poseídos» ya existente lo trata como presente con la marca
        `cubierto_por_tomo` (2026-11-16, decisión del PO).
        """
        existentes = (await self.db.execute(
            select(Issue).where(Issue.series_id == series_id))).scalars().all()
        por_numero = {
            int(str(i.issue_number)): i for i in existentes
            if str(i.issue_number or "").strip().isdigit()
        }
        for numero in numeros:
            issue = por_numero.get(int(numero))
            if issue is None:
                issue = Issue(
                    series_id=series_id,
                    issue_number=str(numero),
                    format=IssueFormat.SINGLE_ISSUE,
                    metadata_={"origen": "tomo", "cubierto_por_tomo": str(file_id)},
                    locked_fields=["series_id"],
                )
                self.db.add(issue)
            else:
                issue.metadata_ = {
                    **(issue.metadata_ or {}),
                    "cubierto_por_tomo": str(file_id),
                }
