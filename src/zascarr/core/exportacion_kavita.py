"""B20: planificación pura de la exportación de una colección a un árbol Kavita.

No toca disco ni BD. El servicio le pasa las filas ya leídas (archivo, issue y
serie) y la raíz; aquí se decide una fila por issue, el nombre canónico
`Serie NNN - Título.ext` y las colisiones. El parche ComicInfo es fase 2: este
módulo no reescribe archivos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from zascarr.utils.fs import sanitize_segment

EXTENSIONES = {".cbz", ".cbr", ".cb7", ".pdf", ".epub"}


@dataclass(frozen=True)
class ArchivoFuente:
    file_id: str
    issue_id: str | None
    series_id: str
    series_title: str
    numero: str | None
    issue_title: str | None
    source_path: str
    size_bytes: int
    sha256: str | None = None
    is_missing: bool = False
    form: str = "single_issue"


@dataclass(frozen=True)
class ArchivoPlan:
    file_id: str
    issue_id: str
    series_id: str
    source_path: str
    destino_relativo: str
    size_bytes: int
    sha256: str | None

    @property
    def destino(self) -> str:
        return self.destino_relativo


@dataclass
class PlanExportacion:
    folder: str
    archivos: list[ArchivoPlan] = field(default_factory=list)
    omitidos: list[str] = field(default_factory=list)
    colisiones: list[str] = field(default_factory=list)
    carpetas_colision: list[str] = field(default_factory=list)

    @property
    def total_archivos(self) -> int:
        return len(self.archivos)

    @property
    def total_bytes(self) -> int:
        return sum(a.size_bytes for a in self.archivos)


def _extension(source_path: str) -> str:
    sufijo = Path(source_path).suffix.lower()
    return sufijo if sufijo in EXTENSIONES else (sufijo if sufijo else ".cbz")


def _numero(numero: str | None) -> str:
    crudo = (numero or "").strip()
    if crudo.isdigit():
        return f"{int(crudo):03d}"
    return crudo


def nombre_de_archivo(serie: str, numero: str | None, titulo: str | None,
                      source_path: str) -> str:
    """Nombre canónico de la exportación, saneado y de un solo nivel."""
    cabecera = sanitize_segment(serie)
    n = _numero(numero)
    subtitulo = sanitize_segment(titulo or serie)
    base = f"{cabecera} {n} - {subtitulo}" if n else f"{cabecera} - {subtitulo}"
    return sanitize_segment(base) + _extension(source_path)


def _fuente_de_issue(archivos: list[ArchivoFuente]) -> ArchivoFuente | None:
    disponibles = [a for a in archivos if not a.is_missing]
    if not disponibles:
        return None
    # La variante canónica: primera ruta estable. Las demás se reportan como omitidas.
    return sorted(disponibles, key=lambda a: (a.source_path, a.file_id))[0]


def plan_export(collection_files: list[ArchivoFuente], root: str | Path, *,
                folder: str = "") -> PlanExportacion:
    """Construye el plan sin tocar disco.

    Una fila por issue; se omite el número sin archivo disponible. Dos issues
    que produzcan el mismo nombre de archivo se detectan como colisión y el
    segundo no se planifica (nunca se pisa).
    """
    raiz = Path(root)
    nombre_carpeta = sanitize_segment(folder or "coleccion")
    por_issue: dict[str, list[ArchivoFuente]] = {}
    for archivo in collection_files:
        if archivo.issue_id is None:
            continue
        por_issue.setdefault(str(archivo.issue_id), []).append(archivo)
    plan = PlanExportacion(folder=nombre_carpeta)
    usados: dict[str, str] = {}
    carpetas: dict[str, str] = {}
    carpetas_por_serie: dict[str, str] = {}
    for serie_id, titulo in {
            a.series_id: a.series_title for a in collection_files}.items():
        base = sanitize_segment(titulo)
        candidata, n = base, 1
        while (candidata.casefold() in carpetas
               and carpetas[candidata.casefold()] != serie_id):
            n += 1
            candidata = f"{base} [{n}]"
        if candidata != base:
            plan.carpetas_colision.append(base)
        carpetas[candidata.casefold()] = serie_id
        carpetas_por_serie[serie_id] = candidata
    for issue_id in sorted(por_issue):
        archivos = por_issue[issue_id]
        fuente = _fuente_de_issue(archivos)
        if fuente is None:
            plan.omitidos.append(issue_id)
            continue
        if len(archivos) > 1:
            plan.omitidos.extend(a.file_id for a in archivos if a is not fuente)
        carpeta = carpetas_por_serie.get(fuente.series_id) or sanitize_segment(fuente.series_title)
        nombre = nombre_de_archivo(fuente.series_title, fuente.numero, fuente.issue_title,
                                   fuente.source_path)
        relativo = f"{nombre_carpeta}/{carpeta}/{nombre}"
        if relativo.casefold() in usados:
            plan.colisiones.append(relativo)
            continue
        if not (raiz / relativo).resolve().is_relative_to(raiz.resolve()):
            plan.colisiones.append(relativo)
            continue
        usados[relativo.casefold()] = issue_id
        plan.archivos.append(ArchivoPlan(
            file_id=fuente.file_id, issue_id=issue_id, series_id=fuente.series_id,
            source_path=fuente.source_path, destino_relativo=relativo,
            size_bytes=fuente.size_bytes, sha256=fuente.sha256))
    return plan
