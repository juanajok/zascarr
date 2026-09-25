"""
LibraryAudit — B16: informe de la biblioteca física ANTES de adoptarla.

Estrictamente de SOLO LECTURA: no borra, no mueve, no renombra y no
registra nada en el catálogo. Su único producto es un informe. La
decisión de qué copia se queda es del coleccionista, nunca del sistema
— que es justo lo que el dedupe silencioso por SHA256 del importador le
quitaba sin avisar (dos carpetas con el mismo tebeo, una gana por orden
alfabético y la otra desaparece del informe como "duplicado").

Qué detecta, con el vocabulario del coleccionista:
  - mismo contenido        → SHA256 idéntico: es el mismo archivo dos veces
  - misma obra, otra copia → mismo título+número, contenido distinto
                             (otra release, otra calidad, otro idioma)
  - carpeta repetida       → dos carpetas con el mismo conjunto de tebeos
  - carpeta vacía          → ni un tebeo en toda la rama

Coste en la Pi (restricción dura, CLAUDE.md §1): hashear 2000 CBR de
~150MB serían ~300GB de lectura. Dos decisiones evitan eso:
  1. Solo se hashean los archivos que COMPARTEN TAMAÑO con algún otro:
     dos ficheros de distinto tamaño no pueden ser idénticos, así que
     los tamaños únicos no se leen jamás. En una biblioteca sana eso
     deja fuera casi todo.
  2. El hash va en streaming (`sha256_streaming`, compartido con el
     triage), no con el `_hash_and_buffer` de ese módulo — ese carga el
     CBZ entero en RAM porque además necesita abrir el ZIP; aquí solo
     hace falta el digest.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.importer_triage import sha256_streaming
from zascarr.core.matcher import normalize_title
from zascarr.models import ImportRun
from zascarr.services.importer import COMIC_EXTS
from zascarr.utils.naming import parse_comic_filename

logger = structlog.get_logger()

# Dos carpetas se consideran "la misma" si comparten al menos este
# porcentaje de la más pequeña. No se exige identidad: el caso real de
# "La Tempestad 01-06 sueltos + los mismos dentro de [Completo]" es un
# subconjunto perfecto, y "Graphic Novels/Carlos Gimenez" vs "Tebeos/
# Carlos Giménez" se solapa de forma parcial pero inequívoca.
UMBRAL_SOLAPE_CARPETA = 0.5
MIN_ARCHIVOS_COMUNES = 2


@dataclass
class MismoContenido:
    """SHA256 idéntico: literalmente el mismo archivo en varios sitios."""
    sha256: str
    size_bytes: int
    rutas: list[str]

    @property
    def bytes_recuperables(self) -> int:
        """Lo que se liberaría quedándose con UNA copia. Es informativo:
        esta clase no borra nada ni sugiere cuál."""
        return self.size_bytes * (len(self.rutas) - 1)


@dataclass
class MismaObraOtraCopia:
    """Mismo título+número aparente pero contenido distinto: otra
    release, otra calidad o otro idioma. NO es un duplicado a eliminar
    — puede ser deliberado (el integral y las grapas sueltas)."""
    obra: str
    rutas: list[str]


@dataclass
class CarpetaRepetida:
    ruta_a: str
    ruta_b: str
    comunes: int
    solo_en_a: int
    solo_en_b: int

    @property
    def es_subconjunto(self) -> bool:
        """Una contiene a la otra entera: el caso más claro de "esta
        carpeta sobra" (pero decide el coleccionista)."""
        return self.solo_en_a == 0 or self.solo_en_b == 0


@dataclass
class CarpetaVacia:
    ruta: str
    subcarpetas: int


@dataclass
class AuditReport:
    started_at: datetime
    finished_at: datetime | None = None
    files_scanned: int = 0
    files_hashed: int = 0
    bytes_hashed: int = 0
    mismo_contenido: list[MismoContenido] = field(default_factory=list)
    misma_obra: list[MismaObraOtraCopia] = field(default_factory=list)
    carpetas_repetidas: list[CarpetaRepetida] = field(default_factory=list)
    carpetas_vacias: list[CarpetaVacia] = field(default_factory=list)

    @property
    def bytes_recuperables(self) -> int:
        return sum(d.bytes_recuperables for d in self.mismo_contenido)

    @property
    def hay_hallazgos(self) -> bool:
        return bool(self.mismo_contenido or self.misma_obra
                    or self.carpetas_repetidas or self.carpetas_vacias)


class LibraryAudit:
    """Solo lectura. No recibe nada que pueda mutar el disco."""

    def __init__(self, db: AsyncSession):
        self._db = db
        self._library: Path = get_settings().library_path

    async def run(self) -> AuditReport:
        report = AuditReport(started_at=datetime.now(UTC))
        if not self._library.exists():
            report.finished_at = datetime.now(UTC)
            return report

        archivos = self._listar_comics()
        report.files_scanned = len(archivos)

        self._detectar_mismo_contenido(archivos, report)
        self._detectar_misma_obra(archivos, report)
        self._detectar_carpetas_repetidas(archivos, report)
        self._detectar_carpetas_vacias(report)

        report.finished_at = datetime.now(UTC)
        await self._persistir(report)
        return report

    # ── Recolección ──────────────────────────────────────────────────

    def _listar_comics(self) -> list[tuple[Path, int]]:
        """(ruta, tamaño) de cada cómic, deduplicado por inodo — dos
        rutas que son el mismo inodo (hardlink, o el mismo disco montado
        dos veces) no son dos tebeos, es el mismo. Mismo criterio que
        Importer.scan_and_import."""
        vistos: set[tuple[int, int]] = set()
        archivos: list[tuple[Path, int]] = []
        for ext in COMIC_EXTS:
            for f in self._library.rglob(f"*{ext}"):
                try:
                    st = f.stat()
                except OSError:
                    continue
                clave = (st.st_dev, st.st_ino)
                if clave in vistos:
                    continue
                vistos.add(clave)
                archivos.append((f, st.st_size))
        return archivos

    # ── Detectores ───────────────────────────────────────────────────

    def _detectar_mismo_contenido(
        self, archivos: list[tuple[Path, int]], report: AuditReport
    ) -> None:
        por_tamano: dict[int, list[Path]] = defaultdict(list)
        for ruta, size in archivos:
            por_tamano[size].append(ruta)

        por_hash: dict[str, tuple[int, list[Path]]] = {}
        for size, rutas in por_tamano.items():
            if len(rutas) < 2:
                continue  # tamaño único: imposible que sea idéntico a otro
            for ruta in rutas:
                try:
                    digest = sha256_streaming(ruta)
                except OSError as exc:
                    logger.warning("library_audit.hash_failed", path=str(ruta), error=str(exc))
                    continue
                report.files_hashed += 1
                report.bytes_hashed += size
                por_hash.setdefault(digest, (size, []))[1].append(ruta)

        report.mismo_contenido = [
            MismoContenido(sha256=digest, size_bytes=size,
                            rutas=sorted(str(r) for r in rutas))
            for digest, (size, rutas) in por_hash.items()
            if len(rutas) > 1
        ]
        report.mismo_contenido.sort(key=lambda d: d.bytes_recuperables, reverse=True)

    def _detectar_misma_obra(
        self, archivos: list[tuple[Path, int]], report: AuditReport
    ) -> None:
        """Mismo título+número, contenido distinto. Se excluyen los que ya
        salieron como 'mismo contenido': ahí no hay nada que comparar."""
        ya_reportadas = {r for d in report.mismo_contenido for r in d.rutas}

        por_obra: dict[str, list[Path]] = defaultdict(list)
        for ruta, _ in archivos:
            if str(ruta) in ya_reportadas:
                continue
            parsed = parse_comic_filename(ruta.name)
            if not parsed.series or not parsed.issue_number:
                continue  # sin número no se puede afirmar que sean la misma obra
            clave = f"{normalize_title(parsed.series)} #{parsed.issue_number}"
            if clave.startswith("#"):
                continue
            por_obra[clave].append(ruta)

        report.misma_obra = [
            MismaObraOtraCopia(obra=clave, rutas=sorted(str(r) for r in rutas))
            for clave, rutas in sorted(por_obra.items())
            if len(rutas) > 1
        ]

    def _detectar_carpetas_repetidas(
        self, archivos: list[tuple[Path, int]], report: AuditReport
    ) -> None:
        por_carpeta: dict[Path, set[str]] = defaultdict(set)
        for ruta, _ in archivos:
            por_carpeta[ruta.parent].add(ruta.name)

        carpetas = sorted(por_carpeta)
        repetidas: list[CarpetaRepetida] = []
        for i, a in enumerate(carpetas):
            for b in carpetas[i + 1:]:
                comunes = por_carpeta[a] & por_carpeta[b]
                if len(comunes) < MIN_ARCHIVOS_COMUNES:
                    continue
                menor = min(len(por_carpeta[a]), len(por_carpeta[b]))
                if len(comunes) / menor < UMBRAL_SOLAPE_CARPETA:
                    continue
                repetidas.append(CarpetaRepetida(
                    ruta_a=str(a), ruta_b=str(b), comunes=len(comunes),
                    solo_en_a=len(por_carpeta[a] - comunes),
                    solo_en_b=len(por_carpeta[b] - comunes),
                ))
        repetidas.sort(key=lambda c: c.comunes, reverse=True)
        report.carpetas_repetidas = repetidas

    def _detectar_carpetas_vacias(self, report: AuditReport) -> None:
        """Ni un cómic en toda la rama. Se reporta solo la carpeta MÁS
        ALTA de cada rama vacía: con `Comics/Hellboy` y sus 20
        subcarpetas igual de vacías, informar de las 21 es ruido que
        esconde el hallazgo ("puede que falte contenido aquí")."""
        vacias: list[CarpetaVacia] = []
        for carpeta in sorted(d for d in self._library.rglob("*") if d.is_dir()):
            if any(carpeta.is_relative_to(Path(v.ruta)) for v in vacias):
                continue  # ya cubierta por una rama vacía de más arriba
            if self._tiene_algun_comic(carpeta):
                continue
            subcarpetas = sum(1 for _ in carpeta.rglob("*") if _.is_dir())
            vacias.append(CarpetaVacia(ruta=str(carpeta), subcarpetas=subcarpetas))
        report.carpetas_vacias = vacias

    def _tiene_algun_comic(self, carpeta: Path) -> bool:
        for ext in COMIC_EXTS:
            if next(carpeta.rglob(f"*{ext}"), None) is not None:
                return True
        return False

    # ── Persistencia del informe (no del catálogo) ───────────────────

    async def _persistir(self, report: AuditReport) -> None:
        """Se reutiliza import_runs con kind="audit" (mismo patrón que
        kind="adoption" de B11). Las listas se recortan: un informe con
        miles de entradas no cabe razonablemente en una fila y la UI
        tampoco lo pintaría — los contadores sí son completos."""
        tope = 200
        self._db.add(ImportRun(
            started_at=report.started_at,
            finished_at=report.finished_at,
            files_scanned=report.files_scanned,
            imported_count=0,
            duplicate_count=len(report.mismo_contenido),
            unsorted_count=len(report.misma_obra),
            error_count=0,
            details={
                "kind": "audit",
                "files_hashed": report.files_hashed,
                "bytes_hashed": report.bytes_hashed,
                "bytes_recuperables": report.bytes_recuperables,
                "truncado": any(len(x) > tope for x in (
                    report.mismo_contenido, report.misma_obra,
                    report.carpetas_repetidas, report.carpetas_vacias)),
                "mismo_contenido": [
                    {"sha256": d.sha256, "size_bytes": d.size_bytes, "rutas": d.rutas}
                    for d in report.mismo_contenido[:tope]
                ],
                "misma_obra": [
                    {"obra": d.obra, "rutas": d.rutas} for d in report.misma_obra[:tope]
                ],
                "carpetas_repetidas": [
                    {"ruta_a": c.ruta_a, "ruta_b": c.ruta_b, "comunes": c.comunes,
                     "solo_en_a": c.solo_en_a, "solo_en_b": c.solo_en_b}
                    for c in report.carpetas_repetidas[:tope]
                ],
                "carpetas_vacias": [
                    {"ruta": c.ruta, "subcarpetas": c.subcarpetas}
                    for c in report.carpetas_vacias[:tope]
                ],
            },
        ))
        await self._db.flush()
