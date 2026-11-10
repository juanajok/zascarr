# ruff: noqa: E501
"""Guardar lo que trae el ComicInfo de un CBZ ya vinculado (#448 BL-INF2).

Solo lectura del CBZ y escritura de metadatos locales: no consulta fuentes, no toca el fichero y
no crea migraciones. Reutiliza el parser del triaje (`parse_comic_info`) y su límite de tamaño.

**No se llama desde «vincular en su sitio»**: ese contrato garantiza que vincular no lee ficheros.
Se aplica donde el archivo ya se lee (importación y adopción) y desde la acción explícita de la
biblioteca, que cubre lo vinculado a mano.
"""
from __future__ import annotations

import asyncio
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.comicinfo_write import MAX_COMICINFO_BYTES
from zascarr.core.formato_contenedor import EntradaNoLegible, leer_acotado
from zascarr.core.importer_triage import ComicInfo, parse_comic_info
from zascarr.models import Creator, CreatorRole, File, Issue, IssueCreator, Publisher, Series
from zascarr.utils.texto_html import texto_plano

MAX_AUTORES_POR_PAPEL = 20
MAX_NOMBRE = 255
MAX_SINOPSIS = 4000
_ACENTOS = str.maketrans("ÁÉÍÓÚÜÑÇáéíóúüñç", "AEIOUUNCAEIOUUNC")


def normalizar_nombre_autor(nombre: str) -> str:
    """Minúsculas, sin acentos y espacios colapsados (mismo criterio que la columna)."""
    limpio = unicodedata.normalize("NFC", nombre or "").translate(_ACENTOS).lower()
    return " ".join(limpio.split())[:MAX_NOMBRE]
_VALID_ROLES = {r.value for r in CreatorRole}


@dataclass(frozen=True)
class ResultadoComicInfoIssue:
    estado: str                 # aplicado | sin_comicinfo | ilegible | sin_cambios
    campos: int = 0
    autores: int = 0
    series_campos: int = 0
    avisos: tuple[str, ...] = ()
    campos_aplicados: tuple[str, ...] = ()


def _leer_comicinfo(ruta: Path) -> tuple[ComicInfo | None, str, tuple[str, ...], int, int]:
    """(info, estado, avisos, mtime_ns, size) sin lanzar por XML roto/ausente."""
    if ruta.suffix.lower() not in (".cbz", ".zip"):
        return None, "ilegible", ("CBR: no se puede leer",), 0, 0
    try:
        st = ruta.stat()
    except OSError:
        return None, "ilegible", ("no se puede leer el archivo",), 0, 0
    try:
        with zipfile.ZipFile(ruta) as zf:
            info = next((i for i in zf.infolist()
                         if i.filename.lower().endswith("comicinfo.xml")), None)
            if info is None:
                return None, "sin_comicinfo", (), st.st_mtime_ns, st.st_size
            if info.file_size > MAX_COMICINFO_BYTES:
                return None, "ilegible", ("ComicInfo.xml demasiado grande",), st.st_mtime_ns, st.st_size
            try:
                data = leer_acotado(zf, info, tope=MAX_COMICINFO_BYTES)
            except EntradaNoLegible:
                return None, "ilegible", ("ComicInfo.xml no se puede leer",), st.st_mtime_ns, st.st_size
    except (zipfile.BadZipFile, OSError):
        return None, "ilegible", ("archivo ilegible",), st.st_mtime_ns, st.st_size
    try:
        parsed = parse_comic_info(data)
    except Exception:  # noqa: BLE001 — XML de terceros roto no aborta
        return None, "ilegible", ("ComicInfo.xml malformado",), st.st_mtime_ns, st.st_size
    return parsed, "ok", tuple(parsed.warnings), st.st_mtime_ns, st.st_size


def _texto(valor: str | None, tope: int) -> str | None:
    limpio = texto_plano(valor)
    return limpio[:tope] if limpio else None


def _mismo(a: str | None, b: str | None) -> bool:
    return (a or "").strip() == (b or "").strip()


async def _aplicar_creditos(db: AsyncSession, issue: Issue, info: ComicInfo, *,
                            avisos: list[str]) -> int:
    añadidos = 0
    existentes = {
        (str(c.creator_id), c.role.value)
        for c in (await db.execute(
            select(IssueCreator).where(IssueCreator.issue_id == issue.id))).scalars().all()
    }
    for rol, nombres in info.credits.items():
        if rol not in _VALID_ROLES:
            continue
        for bruto in nombres[:MAX_AUTORES_POR_PAPEL]:
            nombre = (bruto or "").strip()
            if not nombre:
                continue
            if len(nombre) > MAX_NOMBRE:
                avisos.append("Un nombre de ComicInfo es demasiado largo; se ignora")
                continue
            norm = normalizar_nombre_autor(nombre)
            creado = await db.execute(
                pg_insert(Creator)
                .values(name=nombre, metadata_source="comicinfo_xml")
                .on_conflict_do_nothing(index_elements=["name_norm"])
                .returning(Creator.id))
            creator_id = creado.scalar_one_or_none()
            if creator_id is None:
                creator_id = (await db.execute(
                    select(Creator.id).where(Creator.name_norm == norm))).scalar_one()
            clave = (str(creator_id), rol)
            if clave in existentes:
                continue
            await db.execute(
                pg_insert(IssueCreator)
                .values(issue_id=issue.id, creator_id=creator_id, role=CreatorRole(rol))
                .on_conflict_do_nothing(
                    index_elements=["issue_id", "creator_id", "role"]))
            existentes.add(clave)
            añadidos += 1
    return añadidos


async def _aplicar_editorial(db: AsyncSession, issue: Issue, info: ComicInfo) -> int:
    if not info.publisher:
        return 0
    serie = await db.get(Series, issue.series_id)
    if serie is None or serie.metadata_source == "manual" or serie.publisher_id is not None:
        return 0
    if "publisher_id" in (serie.locked_fields or []):
        return 0
    nombre = info.publisher.strip()
    if not nombre or len(nombre) > MAX_NOMBRE:
        return 0
    editorial = (await db.execute(
        select(Publisher).where(func.lower(Publisher.name) == nombre.lower()))).scalar_one_or_none()
    if editorial is None:
        editorial = Publisher(name=nombre, metadata_source="comicinfo_xml")
        db.add(editorial)
        await db.flush()
    serie.publisher_id = editorial.id
    return 1


async def aplicar_a_issue(db: AsyncSession, issue: Issue, ruta: str | Path) -> ResultadoComicInfoIssue:
    """Aplica el ComicInfo del archivo al número; nunca lanza por XML roto/ausente."""
    ruta = Path(ruta)
    info, estado, avisos, mtime_ns, size = await asyncio.to_thread(_leer_comicinfo, ruta)
    if info is None:
        return ResultadoComicInfoIssue(estado, avisos=avisos)
    marca = {"mtime_ns": mtime_ns, "size": size, "fecha": datetime.now(UTC).isoformat()}
    anterior = (issue.metadata_ or {}).get("comicinfo_aplicado") if isinstance(issue.metadata_, dict) else None
    if isinstance(anterior, dict) and anterior.get("mtime_ns") == mtime_ns and anterior.get("size") == size:
        return ResultadoComicInfoIssue("sin_cambios", avisos=avisos)
    if issue.metadata_source == "manual":
        return ResultadoComicInfoIssue("sin_cambios", avisos=(*avisos, "número marcado como manual"),
                                       campos_aplicados=())
    fuente_previa = issue.metadata_source
    locked = set(issue.locked_fields or [])
    campos = 0
    aplicados: list[str] = []
    if "synopsis" not in locked:
        nuevo = _texto(info.summary, MAX_SINOPSIS)
        actual = issue.synopsis
        if (nuevo and not _mismo(actual, nuevo)
                and (not actual or fuente_previa == "comicinfo_xml")):
            issue.synopsis = nuevo
            campos += 1
            aplicados.append("sinopsis")
    archivos = (await db.execute(select(func.count(File.id)).where(
        File.issue_id == issue.id))).scalar_one()
    if (archivos == 1 and "page_count" not in locked
            and info.page_count and 1 <= info.page_count <= 10000
            and (issue.page_count is None
                 or (fuente_previa == "comicinfo_xml"
                     and issue.page_count != info.page_count))):
        issue.page_count = info.page_count
        campos += 1
        aplicados.append("páginas")
    autores = 0 if "credits" in locked else await _aplicar_creditos(db, issue, info, avisos=list(avisos))
    series_campos = await _aplicar_editorial(db, issue, info)
    if campos or autores:
        issue.metadata_source = "comicinfo_xml"
    actual = issue.metadata_ if isinstance(issue.metadata_, dict) else {}
    issue.metadata_ = {**actual, "comicinfo_aplicado": marca}
    return ResultadoComicInfoIssue(
        "aplicado" if (campos or autores or series_campos) else "sin_cambios",
        campos=campos, autores=autores, series_campos=series_campos,
        avisos=tuple(avisos), campos_aplicados=tuple(aplicados))

TEXTOS_COMICINFO = {
    "titulo": "Leer la información de mis archivos",
    "entrada": "Revisa los datos que ya traen tus CBZ vinculados y guarda solo los que falten.",
    "resumen": "Se leerán {n} {archivo} vinculado{plural}. {cbr} CBR no se pueden leer.",
    "ejecutar": "Leer ahora",
    "seguir": "Seguir leyendo",
    "no_automatico": "Esta acción no se ejecuta sola: solo cuando la pides.",
    "aplicados": "Datos aplicados",
    "omitidos": "Sin cambios",
    "ilegibles": "No se han podido leer",
    "volver": "Volver a la biblioteca",
}


@dataclass(frozen=True)
class ResumenAccionComicInfo:
    total: int
    cbr: int
    offset: int = 0
    limite: int = 50
    aplicados: int = 0
    omitidos: int = 0
    ilegibles: int = 0

    @property
    def siguiente(self) -> int | None:
        return self.offset + self.limite if self.offset + self.limite < self.total else None

    @property
    def texto_resumen(self) -> str:
        archivo = "archivo" if self.total == 1 else "archivos"
        return TEXTOS_COMICINFO["resumen"].format(
            n=self.total, archivo=archivo, plural="" if self.total == 1 else "s",
            cbr=self.cbr)


async def archivos_para_leer(db: AsyncSession) -> tuple[int, int]:
    """(CBZ vinculados totales, CBR vinculados) para el resumen previo; sin leer archivos."""
    filas = (await db.execute(
        select(File.file_path).join(Issue, Issue.id == File.issue_id)
    )).scalars().all()
    cbz = sum(1 for r in filas if str(r).lower().endswith((".cbz", ".zip")))
    cbr = sum(1 for r in filas if str(r).lower().endswith(".cbr"))
    return cbz, cbr


async def leer_archivos_vinculados(db: AsyncSession, *, offset: int = 0,
                                   limite: int = 50) -> ResumenAccionComicInfo:
    """Acción explícita por tandas: lee CBZ ya vinculados y aplica solo huecos."""
    offset = max(0, offset)
    filas = (await db.execute(
        select(File.file_path, File.issue_id, File.id).join(Issue, Issue.id == File.issue_id)
        .where(File.issue_id.is_not(None)).order_by(File.id)
    )).all()
    total = sum(1 for r in filas if str(r.file_path).lower().endswith((".cbz", ".zip")))
    cbr = sum(1 for r in filas if str(r.file_path).lower().endswith(".cbr"))
    tanda = [r for r in filas if str(r.file_path).lower().endswith((".cbz", ".zip"))][
        offset:offset + limite]
    aplicados = omitidos = ilegibles = 0
    for fila in tanda:
        issue = await db.get(Issue, fila.issue_id)
        if issue is None:
            ilegibles += 1
            continue
        try:
            async with db.begin_nested():
                r = await aplicar_a_issue(db, issue, fila.file_path)
        except Exception:  # noqa: BLE001, S110 — un archivo roto no aborta la tanda
            ilegibles += 1
            continue
        if r.estado == "aplicado":
            aplicados += 1
        elif r.estado in ("sin_cambios", "sin_comicinfo"):
            omitidos += 1
        else:
            ilegibles += 1
        await asyncio.sleep(0)
    await db.commit()
    return ResumenAccionComicInfo(
        total=total, cbr=cbr, offset=offset, limite=limite,
        aplicados=aplicados, omitidos=omitidos, ilegibles=ilegibles)
