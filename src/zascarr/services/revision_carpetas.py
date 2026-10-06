# ruff: noqa: E501
"""Superficie de revisión de solo lectura (rebanada 1): lo pendiente, agrupado por su carpeta.

Contrato en `docs/design/rebanada-1-superficie-de-revision.md`. Resumen de lo que NO hace, que es la razón de
ser de la rebanada: no escribe en la base de datos, no mira el disco, no usa la red y no ofrece ninguna acción
(crear serie, asignar, mover). Solo reúne lo que ya está en `files` y `series` y lo explica.

Dos conjuntos disjuntos de archivos, ambos con `issue_id IS NULL` y sin descartar:

- **A, «Sin serie»**: exactamente el filtro de «Por revisar» (`ReviewService._condiciones_pendientes()`,
  reutilizado, no copiado: el recuento coincide con el número del menú).
- **B, «Serie sugerida, falta confirmar número y edición»**: el importador o el registro encontraron una serie
  candidata pero no el número, y por eso no están en «Por revisar» (eran invisibles).

Una carpeta es una PISTA: el nombre exacto de una serie no la convierte en clasificación. Toda señal de
conflicto (año, calificador de saga, título exacto sin nada que lo corrobore…) marca el grupo «en conflicto»
y no se oculta ni se degrada. No existe un estado «lista».
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.carpetas import (
    UMBRAL_AUTOR_O_CONTENEDOR,
    analizar_carpeta,
    dividir_ruta,
    texto_incluye,
)
from zascarr.core.matcher import normalize_title
from zascarr.models import File, Series
from zascarr.services.review import ReviewService
from zascarr.utils.naming import parse_comic_filename

Estado = Literal["sin_serie", "serie_sugerida", "mixto"]
Severidad = Literal["conflicto", "aviso", "informativa"]

#: Textos fijos que ve la persona: UNA sola fuente. Nunca «reconocido», «clasificado» ni «lista».
ETIQUETAS: dict[str, str] = {
    "sin_serie": "Sin serie",
    "serie_sugerida": "Serie sugerida, falta confirmar número y edición",
    "mixto": "Mezcla: archivos sin serie y con serie sugerida (falta confirmar número y edición)",
    "por_confirmar": "por confirmar",
    "en_conflicto": "en conflicto",
}

LIMITE_POR_DEFECTO = 200
LIMITE_MAXIMO = 1000
#: Archivos que se muestran por grupo (todos los de serie sugerida, que son pocos).
MUESTRA_DE_ARCHIVOS = 20


# ── Contrato de salida ────────────────────────────────────────────────────────────────────────────

class CarpetaLimpiaOut(BaseModel):
    titulo: str
    anio: int | None
    volumen: int | None
    calificadores: list[str]


class PatronDeNombres(BaseModel):
    titulo_dominante: str | None
    proporcion: float
    titulos_distintos: int


class SerieSugerida(BaseModel):
    series_id: str
    titulo: str
    anio: int | None
    puntuacion: float


class Senal(BaseModel):
    codigo: str
    severidad: Severidad
    texto: str


class ArchivoRevision(BaseModel):
    id: str
    nombre: str
    estado: Literal["sin_serie", "serie_sugerida"]


class Grupo(BaseModel):
    clave: str
    carpeta_contextual: str | None
    ascendentes: list[str]
    carpeta_limpia: CarpetaLimpiaOut | None
    estado: Estado
    etiqueta: str
    n_archivos: int
    patron_de_nombres: PatronDeNombres
    serie_sugerida: SerieSugerida | None
    por_confirmar: bool
    en_conflicto: bool
    senales: list[Senal]
    archivos: list[ArchivoRevision]


class Totales(BaseModel):
    sin_serie: int
    serie_sugerida: int
    grupos: int
    #: Archivos con serie sugerida cuya serie ya no existe: no se muestran en ningún grupo, se cuentan.
    candidata_inexistente: int


class Pagina(BaseModel):
    limite: int
    desplazamiento: int


class RespuestaCarpetas(BaseModel):
    generado: str
    totales: Totales
    pagina: Pagina
    grupos: list[Grupo]


# ── Lectura ───────────────────────────────────────────────────────────────────────────────────────

@dataclass
class _Candidata:
    series_id: UUID
    puntuacion: float


@dataclass
class _Archivo:
    id: str
    nombre: str
    sin_serie: bool
    carpetas: tuple[str, ...]
    titulo: str                      # título del nombre del archivo, tal cual lo parsea el parser
    titulo_norm: str
    anio: int | None
    candidata: _Candidata | None = None


@dataclass
class _Acumulado:
    archivos: list[_Archivo] = field(default_factory=list)


def _top_candidata(crudo: object) -> _Candidata | None:
    """La mejor candidata de `metadata.candidates`, o None. Tolera datos mal formados: nunca falla."""
    if not isinstance(crudo, list):
        return None
    mejor: _Candidata | None = None
    for c in crudo:
        if not isinstance(c, dict):
            continue
        try:
            sid, score = UUID(str(c["series_id"])), float(c.get("score") or 0.0)
        except (KeyError, ValueError, TypeError):
            continue
        if mejor is None or score > mejor.puntuacion:
            mejor = _Candidata(sid, score)
    return mejor


class RevisionCarpetas:
    """Servicio de solo lectura. Dos consultas a lo sumo, vengan 20 filas o 20.000."""

    def __init__(
        self,
        db: AsyncSession,
        biblioteca: PurePosixPath | str | None = None,
        ahora: Callable[[], datetime] | None = None,
    ):
        self._db = db
        self._biblioteca = PurePosixPath(str(biblioteca or get_settings().library_path))
        self._ahora = ahora or (lambda: datetime.now(UTC))

    # Puro: sin disco (`PurePosixPath` no consulta nada).
    def _carpetas_de(self, file_path: str) -> tuple[str, ...]:
        ruta = PurePosixPath(file_path)
        try:
            relativa = ruta.relative_to(self._biblioteca)
        except ValueError:
            # Fuera de la biblioteca configurada (p. ej. la ruta cambió): se agrupa por su ruta completa.
            relativa = PurePosixPath(*ruta.parts[1:]) if ruta.is_absolute() else ruta
        return relativa.parts[:-1]

    async def carpetas(
        self, limite: int = LIMITE_POR_DEFECTO, desplazamiento: int = 0,
    ) -> RespuestaCarpetas:
        limite = max(1, min(limite, LIMITE_MAXIMO))
        desplazamiento = max(0, desplazamiento)

        filas = await self._leer()
        ids = {f.candidata.series_id for f in filas if f.candidata}
        series = await self._series(ids)

        validos: list[_Archivo] = []
        sin_serie_total = sugeridas_total = huerfanas = 0
        for f in filas:
            if f.sin_serie:
                sin_serie_total += 1
            elif f.candidata and f.candidata.series_id in series:
                sugeridas_total += 1
            else:
                huerfanas += 1
                continue
            validos.append(f)

        grupos_por_clave: dict[str, _Acumulado] = {}
        divisiones = {}
        for f in validos:
            div = dividir_ruta(f.carpetas)
            divisiones[div.clave] = div
            grupos_por_clave.setdefault(div.clave, _Acumulado()).archivos.append(f)

        grupos = [
            self._grupo(clave, divisiones[clave], acum.archivos, series)
            for clave, acum in grupos_por_clave.items()
        ]
        grupos.sort(key=lambda g: (not g.en_conflicto, -g.n_archivos, g.clave))

        return RespuestaCarpetas(
            generado=self._ahora().astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            totales=Totales(
                sin_serie=sin_serie_total, serie_sugerida=sugeridas_total,
                grupos=len(grupos), candidata_inexistente=huerfanas,
            ),
            pagina=Pagina(limite=limite, desplazamiento=desplazamiento),
            grupos=grupos[desplazamiento:desplazamiento + limite],
        )

    async def _leer(self) -> list[_Archivo]:
        """UNA consulta para A ∪ B, columnas mínimas. A reutiliza el filtro de «Por revisar».

        Sin ORDER BY: el orden de la respuesta lo fija `carpetas()` (grupos por conflicto, tamaño y clave;
        archivos por nombre e id), no el que devuelva la base de datos."""
        es_a = and_(*ReviewService._condiciones_pendientes())
        candidatas = File.metadata_["candidates"]
        hay_candidatas = case(
            (func.jsonb_typeof(candidatas) == "array", func.jsonb_array_length(candidatas)),
            else_=0,
        ) > 0
        es_b = and_(
            File.issue_id.is_(None),
            File.review_dismissed.is_(False),
            File.metadata_["match_status"].astext != "unsorted",
            hay_candidatas,
        )
        filas = (await self._db.execute(
            select(File.id, File.file_path, File.file_name, es_a.label("es_a"), candidatas.label("cand"))
            .where(or_(es_a, es_b))
        )).all()

        salida: list[_Archivo] = []
        for fid, ruta, nombre, sin_serie, cand in filas:
            p = parse_comic_filename(nombre)
            salida.append(_Archivo(
                id=str(fid), nombre=nombre, sin_serie=bool(sin_serie),
                carpetas=self._carpetas_de(ruta),
                titulo=p.series, titulo_norm=normalize_title(p.series), anio=p.year,
                candidata=None if sin_serie else _top_candidata(cand),
            ))
        return salida

    async def _series(self, ids: set[UUID]) -> dict[UUID, tuple[str, int | None]]:
        if not ids:
            return {}
        filas = (await self._db.execute(
            select(Series.id, Series.title, Series.start_year).where(Series.id.in_(ids))
        )).all()
        return {sid: (titulo, anio) for sid, titulo, anio in filas}

    # ── Un grupo ─────────────────────────────────────────────────────────────────────────────────

    def _grupo(self, clave, div, archivos: list[_Archivo], series) -> Grupo:
        sugeridos = [a for a in archivos if not a.sin_serie]
        sin_serie = [a for a in archivos if a.sin_serie]
        if sugeridos and sin_serie:
            estado: Estado = "mixto"
        else:
            estado = "serie_sugerida" if sugeridos else "sin_serie"

        patron = self._patron(archivos)
        sugerida, candidatas_distintas = self._serie_sugerida(sugeridos, series)
        carpeta = analizar_carpeta(div.contextual) if div.contextual else None
        senales = self._senales(
            carpeta, sugerida, candidatas_distintas, patron, archivos, tiene_contexto=bool(div.contextual),
        )
        en_conflicto = any(s.severidad == "conflicto" for s in senales)

        muestra = sorted(sugeridos, key=lambda a: (a.nombre, a.id)) + sorted(
            sin_serie, key=lambda a: (a.nombre, a.id))[:MUESTRA_DE_ARCHIVOS]
        return Grupo(
            clave=clave,
            carpeta_contextual=div.contextual,
            ascendentes=list(div.ascendentes),
            carpeta_limpia=None if carpeta is None else CarpetaLimpiaOut(
                titulo=carpeta.titulo, anio=carpeta.anio, volumen=carpeta.volumen,
                calificadores=carpeta.calificadores,
            ),
            estado=estado,
            etiqueta=ETIQUETAS[estado],
            n_archivos=len(archivos),
            patron_de_nombres=patron,
            serie_sugerida=sugerida,
            por_confirmar=bool(sugeridos),          # al conjunto B siempre le falta el número
            en_conflicto=en_conflicto,
            senales=senales,
            archivos=[ArchivoRevision(
                id=a.id, nombre=a.nombre, estado="sin_serie" if a.sin_serie else "serie_sugerida",
            ) for a in muestra],
        )

    @staticmethod
    def _patron(archivos: list[_Archivo]) -> PatronDeNombres:
        con_titulo = [a for a in archivos if a.titulo_norm]
        if not con_titulo:
            return PatronDeNombres(titulo_dominante=None, proporcion=0.0, titulos_distintos=0)
        cuenta = Counter(a.titulo_norm for a in con_titulo)
        # Desempate determinista: más frecuente y, a igualdad, el menor alfabéticamente.
        dominante = min(cuenta, key=lambda k: (-cuenta[k], k))
        formas = Counter(a.titulo for a in con_titulo if a.titulo_norm == dominante)
        visible = min(formas, key=lambda t: (-formas[t], t))
        return PatronDeNombres(
            titulo_dominante=visible,
            proporcion=round(cuenta[dominante] / len(archivos), 3),
            titulos_distintos=len(cuenta),
        )

    @staticmethod
    def _serie_sugerida(sugeridos: list[_Archivo], series) -> tuple[SerieSugerida | None, int]:
        """La serie que más archivos del grupo sugieren (desempate: mayor puntuación, luego id) y cuántas
        series distintas se sugieren. La puntuación es la MENOR del grupo: no se exagera."""
        if not sugeridos:
            return None, 0
        por_serie: dict[UUID, list[float]] = {}
        for a in sugeridos:
            por_serie.setdefault(a.candidata.series_id, []).append(a.candidata.puntuacion)
        elegida = min(por_serie, key=lambda s: (-len(por_serie[s]), -max(por_serie[s]), str(s)))
        titulo, anio = series[elegida]
        return SerieSugerida(
            series_id=str(elegida), titulo=titulo, anio=anio, puntuacion=min(por_serie[elegida]),
        ), len(por_serie)

    @staticmethod
    def _senales(carpeta, sugerida, candidatas_distintas, patron, archivos, *, tiene_contexto) -> list[Senal]:
        senales: list[Senal] = []
        conflictos: list[Senal] = []

        if sugerida is not None:
            titulo_serie = sugerida.titulo
            titulo_coincide = (
                patron.titulo_dominante is not None
                and normalize_title(patron.titulo_dominante) == normalize_title(titulo_serie)
            )
            # Año de referencia: el de la carpeta; si no lo dice, el que dominan los nombres.
            anios = Counter(a.anio for a in archivos if a.anio)
            if carpeta is not None and carpeta.anio:
                anio_ref, de_donde = carpeta.anio, "La carpeta dice"
            elif anios:
                anio_ref, de_donde = min(anios, key=lambda y: (-anios[y], y)), "Los nombres dicen"
            else:
                anio_ref, de_donde = None, ""
            discrepa = bool(anio_ref and sugerida.anio and abs(anio_ref - sugerida.anio) > 1)
            anio_corrobora = bool(anio_ref and sugerida.anio and abs(anio_ref - sugerida.anio) <= 1)
            volumen_corrobora = bool(
                carpeta and carpeta.volumen is not None
                and texto_incluye(titulo_serie, f"Vol {carpeta.volumen}")
            )

            if discrepa:
                conflictos.append(Senal(
                    codigo="anio_discrepa", severidad="conflicto",
                    texto=f"{de_donde} {anio_ref}; la serie sugerida empieza en {sugerida.anio}.",
                ))
            # Un calificador que la serie sugerida no lleva en su título es algo que la carpeta añade.
            que_anade = [] if carpeta is None else [
                q for q in carpeta.calificadores if not texto_incluye(titulo_serie, q)
            ]
            if que_anade:
                conflictos.append(Senal(
                    codigo="calificador_de_carpeta", severidad="conflicto",
                    texto="La carpeta añade " + ", ".join(f"«{q}»" for q in que_anade) + ".",
                ))
            if candidatas_distintas > 1:
                conflictos.append(Senal(
                    codigo="candidatas_distintas", severidad="conflicto",
                    texto=f"Los archivos del grupo sugieren {candidatas_distintas} series distintas.",
                ))
            if titulo_coincide and not (anio_corrobora or volumen_corrobora) and not discrepa:
                conflictos.append(Senal(
                    codigo="titulo_exacto_sin_corroboracion", severidad="conflicto",
                    texto="El título coincide con la serie sugerida, pero ni un año ni un volumen lo corroboran.",
                ))
            senales.extend(conflictos)

        if patron.titulos_distintos >= UMBRAL_AUTOR_O_CONTENEDOR:
            senales.append(Senal(
                codigo="carpeta_de_autor_o_contenedor", severidad="aviso",
                texto=f"La carpeta reúne {patron.titulos_distintos} títulos distintos: "
                      "parece de autor o de contenedor, no de una serie.",
            ))
        if sugerida is not None and titulo_coincide and (anio_corrobora or volumen_corrobora) and not conflictos:
            senales.append(Senal(
                codigo="coincide_y_corrobora", severidad="informativa",
                texto="El título coincide con la serie sugerida y el año o el volumen lo corroboran.",
            ))
        if not tiene_contexto:
            senales.append(Senal(
                codigo="sin_contexto_de_carpeta", severidad="informativa",
                texto="Estos archivos no están en una carpeta de serie.",
            ))
        return senales
