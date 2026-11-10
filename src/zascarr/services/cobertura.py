# ruff: noqa: E501
"""Cobertura de la información de la biblioteca (#449 BL-INF3).

Solo lectura y **una** consulta agregada: no recorre series ni números desde
Python, no mira archivos y no sale a la red. Las partes del desglose por
procedencia siempre suman su total.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import MetadataSource

SIN_REGISTRAR = "sin_registrar"
#: Etiquetas visibles; nada de valores internos en pantalla.
FUENTES_ES: dict[str, str] = {
    MetadataSource.COMIC_VINE.value: "Comic Vine",
    MetadataSource.GCD.value: "GCD",
    MetadataSource.ANILIST.value: "AniList",
    MetadataSource.TEBEOSFERA.value: "Tebeosfera",
    MetadataSource.COMICINFO_XML.value: "Desde el archivo",
    MetadataSource.MANUAL.value: "Puesto a mano",
    SIN_REGISTRAR: "Sin registrar",
}
FUENTES = tuple(FUENTES_ES)


@dataclass(frozen=True)
class Cobertura:
    series_total: int = 0
    series_sinopsis: int = 0
    series_autores: int = 0
    numeros_total: int = 0
    numeros_sinopsis: int = 0
    numeros_autores: int = 0
    numeros_fecha: int = 0
    series_por_fuente: dict[str, int] = field(default_factory=dict)
    numeros_por_fuente: dict[str, int] = field(default_factory=dict)
    calculado: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def series_sin_sinopsis(self) -> int:
        return self.series_total - self.series_sinopsis

    @property
    def numeros_sin_sinopsis(self) -> int:
        return self.numeros_total - self.numeros_sinopsis

    @property
    def baja(self) -> bool:
        if not self.series_total and not self.numeros_total:
            return False
        return (self.series_sinopsis < self.series_total
                or self.numeros_sinopsis < self.numeros_total)

    @property
    def texto_series(self) -> str:
        return (f"Series: {self.series_sinopsis} de {self.series_total} con sinopsis; "
                f"{self.series_autores} de {self.series_total} con autores (guion o dibujo).")

    @property
    def texto_numeros(self) -> str:
        return (f"Números: {self.numeros_sinopsis} de {self.numeros_total} con sinopsis; "
                f"{self.numeros_autores} de {self.numeros_total} con autores; "
                f"{self.numeros_fecha} de {self.numeros_total} con fecha de portada.")

    @property
    def texto_accion(self) -> str | None:
        if not self.baja:
            return None
        return ("Puedes leer la información de tus archivos o encender una fuente "
                "en Ajustes; ZascArr no ha hecho nada por su cuenta.")

    @property
    def texto_fecha(self) -> str:
        return f"Calculado el {self.calculado.astimezone().strftime('%d/%m/%Y a las %H:%M')}."

    def filas_series(self) -> list[tuple[str, int]]:
        return [(FUENTES_ES[k], self.series_por_fuente.get(k, 0)) for k in FUENTES]


    def __post_init__(self) -> None:
        # dict_fields completos para que las partes sumen siempre.
        series = {k: int(self.series_por_fuente.get(k, 0)) for k in FUENTES}
        numeros = {k: int(self.numeros_por_fuente.get(k, 0)) for k in FUENTES}
        object.__setattr__(self, "series_por_fuente", series)
        object.__setattr__(self, "numeros_por_fuente", numeros)

    def filas_numeros(self) -> list[tuple[str, int]]:  # noqa: F811
        return [(FUENTES_ES[k], self.numeros_por_fuente.get(k, 0)) for k in FUENTES]


_SQL = text("""
WITH
s_total AS (SELECT count(*)::int AS n FROM series),
s_sinopsis AS (
    SELECT count(*)::int AS n FROM series WHERE btrim(coalesce(description, '')) <> ''
),
s_autores AS (
    SELECT count(*)::int AS n FROM series s WHERE EXISTS (
        SELECT 1 FROM issues i JOIN issue_creators ic ON ic.issue_id = i.id
        WHERE i.series_id = s.id AND ic.role IN ('writer', 'penciler')
    )
),
i_total AS (SELECT count(*)::int AS n FROM issues),
i_sinopsis AS (
    SELECT count(*)::int AS n FROM issues WHERE btrim(coalesce(synopsis, '')) <> ''
),
i_autores AS (
    SELECT count(*)::int AS n FROM issues i WHERE EXISTS (
        SELECT 1 FROM issue_creators ic WHERE ic.issue_id = i.id
        AND ic.role IN ('writer', 'penciler')
    )
),
i_fecha AS (
    SELECT count(*)::int AS n FROM issues WHERE release_date IS NOT NULL
),
s_fuentes AS (
    SELECT CASE WHEN metadata_source IN ('comic_vine','gcd','anilist','tebeosfera','comicinfo_xml','manual')
                THEN metadata_source ELSE 'sin_registrar' END AS fuente,
           count(*)::int AS n
    FROM series GROUP BY 1
),
i_fuentes AS (
    SELECT CASE WHEN metadata_source IN ('comic_vine','gcd','anilist','tebeosfera','comicinfo_xml','manual')
                THEN metadata_source ELSE 'sin_registrar' END AS fuente,
           count(*)::int AS n
    FROM issues GROUP BY 1
)
SELECT
    (SELECT n FROM s_total) AS series_total,
    (SELECT n FROM s_sinopsis) AS series_sinopsis,
    (SELECT n FROM s_autores) AS series_autores,
    (SELECT n FROM i_total) AS numeros_total,
    (SELECT n FROM i_sinopsis) AS numeros_sinopsis,
    (SELECT n FROM i_autores) AS numeros_autores,
    (SELECT n FROM i_fecha) AS numeros_fecha,
    coalesce((SELECT string_agg(fuente || '=' || n, ',') FROM s_fuentes), '') AS series_fuentes,
    coalesce((SELECT string_agg(fuente || '=' || n, ',') FROM i_fuentes), '') AS numeros_fuentes
""")


def _mapa(serializado: str) -> dict[str, int]:
    resultado = {k: 0 for k in FUENTES}
    if serializado:
        for trozo in serializado.split(","):
            fuente, _, n = trozo.partition("=")
            if fuente in resultado:
                resultado[fuente] = int(n)
    return resultado


async def calcular(db: AsyncSession) -> Cobertura:
    fila = (await db.execute(_SQL)).mappings().one()
    return Cobertura(
        series_total=fila["series_total"],
        series_sinopsis=fila["series_sinopsis"],
        series_autores=fila["series_autores"],
        numeros_total=fila["numeros_total"],
        numeros_sinopsis=fila["numeros_sinopsis"],
        numeros_autores=fila["numeros_autores"],
        numeros_fecha=fila["numeros_fecha"],
        series_por_fuente=_mapa(fila["series_fuentes"]),
        numeros_por_fuente=_mapa(fila["numeros_fuentes"]),
    )
