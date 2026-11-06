#!/usr/bin/env python3
"""Censo de portadas por debajo del objetivo (BL-PORT1, #300/#411; FR-13/FR-14).

Una pasada **de solo lectura** sobre la base y los ficheros reales. Clasifica cada serie en UNA
de las seis clases de FR-14 y da el recuento por causa; la cifra que decide si BL-PORT2 merece la
pena es la de las clases que **no** se arreglan solas al pedir la portada.

Qué NO hace: no escribe en la base, ni en la caché, ni en disco (salvo el informe `--json` o
`--csv`), no descarga nada y no toca ficheros. El I/O de disco va en un bucle síncrono acotado
dentro de `asyncio.to_thread`; el script no se usa dentro del servidor.

Clases (FR-14; cada serie cae en una sola):

  ya_en_objetivo          covers/v2/<id>.jpg existe y mide >= 600.
  regenerable_al_pedir    no hay v2, el primer File no ausente se extrae y su primera página
                          mide >= 600: la próxima visita a su portada la regenerará.
  extraible_mas_adelante  el primer File no ausente NO se puede extraer, pero un File posterior
                          sí. La cascada solo mira el primero: hoy no se intentaría.
  original_pequeno        se puede extraer, pero la primera página mide < 600 (no se amplía).
  sin_extractor           no hay ningún File extraíble (CBR/PDF/EPUB reales), o solo hay
                          cover_url: no hay página local que extraer.
  sin_fuente              no hay ningún File no ausente ni cover_url.

Se usa el **mismo predicado** que `web/series.py::portada`: `puede_tener_portada` y la lectura
acotada de la primera página con `core/formato_contenedor` (`natural_key`, `puede_dar_portada`,
`se_lee_como_zip`, `clasificar_infos`, `leer_acotado`), leyendo solo la cabecera de la imagen.

Uso en la Pi (contenedor de un solo uso, sin desplegar; ver también `docs/design/
medicion-BL-PORT1-2026-11-06.md`):

  docker run --rm --network zascarr_default \\
    -e DATABASE_URL="postgresql://zascarr:...@db:5432/zascarr" \\
    -e COVERS_CACHE_PATH=/config/covers \\
    -v zascarr_config:/config:ro \\
    -v "$(pwd)":/app:ro \\
    -w /app zascarr:latest \\
    python scripts/medicion/censo_portadas.py --json /tmp/censo-portadas.json

(La ruta exacta del volumen y del usuario de la base salen de tu `.env`; no se copian aquí.)
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import sys
import zipfile
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from PIL import Image

from zascarr.core.formato_contenedor import (
    ClaseZip,
    EntradaNoLegible,
    clasificar_infos,
    firma_de,
    leer_acotado,
    natural_key,
    se_lee_como_zip,
    zip_fuera_de_limite,
)
from zascarr.utils.cover import (
    CACHE_VERSION,
    IMAGE_EXTS,
    MAX_PIXELES_PORTADA,
    SERIES_COVER_MAX_WIDTH,
    puede_dar_portada,
    puede_tener_portada,
)

OBJETIVO_PX = SERIES_COVER_MAX_WIDTH


class Clase(StrEnum):
    """Conjunto CERRADO de clases del censo (FR-14); no se añaden en el informe."""

    YA_EN_OBJETIVO = "ya_en_objetivo"
    REGENERABLE_AL_PEDIR = "regenerable_al_pedir"
    EXTRAIBLE_MAS_ADELANTE = "extraible_mas_adelante"
    ORIGINAL_PEQUENO = "original_pequeno"
    SIN_EXTRACTOR = "sin_extractor"
    SIN_FUENTE = "sin_fuente"


#: Orden fijo de presentación (del caso mejor al peor para decidir BL-PORT2).
ORDEN_CLASES: tuple[Clase, ...] = (
    Clase.YA_EN_OBJETIVO, Clase.REGENERABLE_AL_PEDIR, Clase.EXTRAIBLE_MAS_ADELANTE,
    Clase.ORIGINAL_PEQUENO, Clase.SIN_EXTRACTOR, Clase.SIN_FUENTE,
)

#: Clases que no se arreglan solas, salvo el caso de `sin_extractor` con portada externa,
#: que la cascada resuelve al abrir la ficha. `sin_extractor` se cuenta aparte con su desglose.
CLASES_QUE_QUEDAN: tuple[Clase, ...] = (
    Clase.ORIGINAL_PEQUENO, Clase.EXTRAIBLE_MAS_ADELANTE, Clase.SIN_FUENTE,
)


@dataclass(frozen=True)
class FicheroResumen:
    """Lo justo para clasificar: la ruta se usa solo para el probe; nunca se publica."""
    ruta: str
    formato_contenido: dict | None = None
    is_missing: bool = False


@dataclass(frozen=True)
class Sonda:
    """Resultado de mirar un fichero: si se pudo medir la primera página y si se puede extraer."""
    mide: bool
    ancho: int | None
    alto: int | None
    extraible: bool

    @property
    def puede_extraer(self) -> bool:
        return bool(self.extraible and self.mide and self.ancho)


@dataclass(frozen=True)
class SerieResumen:
    serie_id: str
    cover_url: str | None = None
    hay_v2: bool = False
    ancho_v2: int | None = None


def clasificar(serie: SerieResumen, ficheros: Sequence[FicheroResumen],
               probe: Callable[[FicheroResumen], Sonda]) -> Clase:
    """Clasifica UNA serie con el mismo camino que la cascada real.

    `ficheros` llega en el orden en que la cascada los miraría (issue.sort_order). `probe` es la
    única puerta al disco: se inyecta para probar el clasificador sin ficheros reales.
    """
    if serie.hay_v2 and serie.ancho_v2 is not None and serie.ancho_v2 >= OBJETIVO_PX:
        return Clase.YA_EN_OBJETIVO

    utiles = [f for f in ficheros if not f.is_missing]
    if not utiles:
        # Sin File no ausente: si tampoco hay cover_url, no hay ninguna fuente de portada. Si
        # hay cover_url, la causa local es que no hay página extraíble.
        return Clase.SIN_FUENTE if not serie.cover_url else Clase.SIN_EXTRACTOR

    primera = probe(utiles[0])
    if primera.puede_extraer:
        if primera.ancho is not None and primera.ancho >= OBJETIVO_PX:
            return Clase.REGENERABLE_AL_PEDIR
        return Clase.ORIGINAL_PEQUENO

    # La cascada NO mira más Files si el primero no da portada; el censo sí, para no contar como
    # «sin extractor» lo que solo es «no se intentó el siguiente».
    if any(probe(f).puede_extraer for f in utiles[1:]):
        return Clase.EXTRAIBLE_MAS_ADELANTE
    return Clase.SIN_EXTRACTOR


def _dimensiones_primera_pagina(path: Path, formato_contenido: dict | None) -> Sonda:
    """Lee SOLO la cabecera de la primera página, como la cascada, sin decodificar la imagen."""
    if not path.exists():
        return Sonda(mide=False, ancho=None, alto=None, extraible=False)
    if not puede_tener_portada(path, formato_contenido):
        return Sonda(mide=False, ancho=None, alto=None, extraible=False)
    ext = path.suffix.lower()
    guardado = puede_dar_portada(ext, formato_contenido)
    sin_guardar = guardado is None
    try:
        if sin_guardar and not se_lee_como_zip(ext, firma_de(path)):
            return Sonda(mide=False, ancho=None, alto=None, extraible=False)
        if zip_fuera_de_limite(path):
            return Sonda(mide=False, ancho=None, alto=None, extraible=False)
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if (sin_guardar and ext not in (".cbz", ".zip")
                    and clasificar_infos(infos).clase is not ClaseZip.TEBEO):
                return Sonda(mide=False, ancho=None, alto=None, extraible=False)
            por_nombre = {i.filename: i for i in infos if not i.is_dir()}
            paginas = sorted((n for n in por_nombre if Path(n).suffix.lower() in IMAGE_EXTS),
                             key=natural_key)
            if not paginas:
                return Sonda(mide=False, ancho=None, alto=None, extraible=False)
            data = leer_acotado(zf, por_nombre[paginas[0]])
    except (OSError, zipfile.BadZipFile, EntradaNoLegible):
        return Sonda(mide=False, ancho=None, alto=None, extraible=False)
    try:
        with Image.open(io.BytesIO(data)) as img:
            # Igual que `extract_cover_thumbnail`: una página que supera el tope no da portada.
            if img.width * img.height > MAX_PIXELES_PORTADA:
                return Sonda(mide=True, ancho=img.width, alto=img.height, extraible=False)
            return Sonda(mide=True, ancho=img.width, alto=img.height, extraible=True)
    except Exception:  # noqa: BLE001 — cualquier fallo de Pillow es «no extraíble», no del censo
        return Sonda(mide=False, ancho=None, alto=None, extraible=False)


def probe_fichero(fichero: FicheroResumen) -> Sonda:
    """El probe real de un `File`: sin escribir nada, sin red, solo cabecera."""
    if fichero.is_missing:
        return Sonda(mide=False, ancho=None, alto=None, extraible=False)
    return _dimensiones_primera_pagina(Path(fichero.ruta), fichero.formato_contenido)


def ancho_de_cache(path: Path) -> int | None:
    """Ancho de una caché ya escrita, leyendo solo la cabecera del JPEG."""
    try:
        with Image.open(path) as img:
            return int(img.width)
    except (OSError, ValueError):
        return None


def anchos_de_cache(covers: Path, serie_id: str) -> tuple[bool, int | None]:
    """(hay_v2, ancho_v2) de una serie. La legada no entra en la clase: solo la v2 es objetivo."""
    v2 = covers / CACHE_VERSION / f"{serie_id}.jpg"
    if v2.exists():
        return True, ancho_de_cache(v2)
    return False, None


@dataclass
class SerieCenso:
    serie_id: str
    cover_url: str | None
    ficheros: list[FicheroResumen] = field(default_factory=list)


def clasificar_series(series: Iterable[SerieCenso], covers: Path,
                      probe: Callable[[FicheroResumen], Sonda] = probe_fichero
                      ) -> dict[str, Clase]:
    """Clasifica todas (bucle síncrono acotado; se llama desde `asyncio.to_thread`)."""
    resultado: dict[str, Clase] = {}
    for serie in series:
        hay_v2, ancho_v2 = anchos_de_cache(covers, serie.serie_id)
        resumen = SerieResumen(serie.serie_id, serie.cover_url, hay_v2, ancho_v2)
        resultado[serie.serie_id] = clasificar(resumen, serie.ficheros, probe)
    return resultado


def _url_asyncpg(url: str) -> str:
    """asyncpg no entiende el sufijo de driver de SQLAlchemy."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


_SQL = """
SELECT s.id::text AS serie_id, s.cover_url,
       f.file_path, f.metadata, f.is_missing, i.sort_order
FROM series s
LEFT JOIN issues i ON i.series_id = s.id
LEFT JOIN files f ON f.issue_id = i.id AND COALESCE(f.is_missing, false) = false
ORDER BY s.id, i.sort_order ASC NULLS LAST, f.file_path ASC
"""


async def leer_series(url: str) -> list[SerieCenso]:
    """Lee la base en una sola pasada, sin escribir. Devuelve las series en orden de id."""
    import asyncpg  # dependencia de la app; el script se ejecuta dentro de su contenedor

    conn = await asyncpg.connect(_url_asyncpg(url))
    try:
        rows = await conn.fetch(_SQL)
    finally:
        await conn.close()
    por_id: dict[str, SerieCenso] = {}
    for row in rows:
        serie = por_id.setdefault(
            row["serie_id"], SerieCenso(row["serie_id"], row["cover_url"]))
        if row["file_path"]:
            metadata = row["metadata"]
            if isinstance(metadata, str):
                metadata = json.loads(metadata)
            serie.ficheros.append(FicheroResumen(
                ruta=row["file_path"], formato_contenido=metadata,
                is_missing=bool(row["is_missing"])))
    return list(por_id.values())


def recuento(clases: dict[str, Clase]) -> dict[Clase, int]:
    conteo = Counter(clases.values())
    return {clase: conteo.get(clase, 0) for clase in ORDEN_CLASES}


@dataclass(frozen=True)
class DesgloseSinExtractor:
    """`sin_extractor` separado por si hay `cover_url`: la cascada la resuelve al abrir la ficha."""
    con_portada_externa: int = 0
    sin_portada_externa: int = 0

    @property
    def total(self) -> int:
        return self.con_portada_externa + self.sin_portada_externa


def desglose_sin_extractor(series: Iterable[SerieCenso],
                           clases: dict[str, Clase]) -> DesgloseSinExtractor:
    """Cuenta `sin_extractor` con y sin `cover_url` (el dato que corrige la cifra de BL-PORT2)."""
    con = sin = 0
    for serie in series:
        if clases.get(serie.serie_id) is not Clase.SIN_EXTRACTOR:
            continue
        if serie.cover_url:
            con += 1
        else:
            sin += 1
    return DesgloseSinExtractor(con_portada_externa=con, sin_portada_externa=sin)


def cifra_bl_port2(conteo: dict[Clase, int], desglose: DesgloseSinExtractor) -> int:
    """Series que no se arreglan solas y no tienen portada externa que las resuelva (§9.5).

    `sin_extractor` con `cover_url` NO cuenta: la cascada descarga la portada externa a 600 al
    abrir la ficha. Solo cuentan las que no tienen ninguna vía local ni externa.
    """
    return (sum(conteo.get(c, 0) for c in CLASES_QUE_QUEDAN)
            + desglose.sin_portada_externa)


def informe_json(clases: dict[str, Clase], series: Iterable[SerieCenso]) -> dict:
    """JSON publicable: solo `serie_id` y clase, sin rutas, nombres ni datos personales."""
    series = list(series)
    conteo = recuento(clases)
    desglose = desglose_sin_extractor(series, clases)
    return {
        "generado": datetime.now(UTC).isoformat(),
        "objetivo_px": OBJETIVO_PX,
        "total": len(clases),
        "clases": {c.value: conteo[c] for c in ORDEN_CLASES},
        "sin_extractor_con_portada_externa": desglose.con_portada_externa,
        "sin_extractor_sin_portada_externa": desglose.sin_portada_externa,
        "cifra_bl_port2": cifra_bl_port2(conteo, desglose),
        "estado": {
            "lectura": "PASS" if clases else "NOT RUN",
            "clasificacion": "PASS" if clases else "NOT RUN",
            "decision_BL_PORT2": "NOT RUN",
        },
        "series": [{"serie_id": sid, "clase": clases[sid].value}
                   for sid in sorted(clases)],
    }


def imprimir_tabla(clases: dict[str, Clase], desglose: DesgloseSinExtractor) -> None:
    conteo = recuento(clases)
    print(f"{'Clase':<26} {'Series':>7}")
    print("-" * 34)
    for clase in ORDEN_CLASES:
        print(f"{clase.value:<26} {conteo[clase]:>7}")
    print("-" * 34)
    print(f"{'TOTAL':<26} {len(clases):>7}")
    print()
    por_debajo = len(clases) - conteo[Clase.YA_EN_OBJETIVO]
    print(f"Por debajo del objetivo (no ya_en_objetivo): {por_debajo}")
    print(f"Cifra para decidir BL-PORT2 (original_pequeno + extraible_mas_adelante + "
          f"sin_extractor_sin_portada_externa + sin_fuente): "
          f"{cifra_bl_port2(conteo, desglose)}")
    print(f"De los sin extractor: {desglose.con_portada_externa} con portada externa "
          f"(se resuelven al abrir la ficha) · {desglose.sin_portada_externa} sin ninguna "
          f"(necesitan BL-PORT2)")
    print()
    if clases:
        print(f"PASS  lectura de la base y clasificación de {len(clases)} series (solo lectura)")
    else:
        print("NOT RUN  no hay series en la base: no hay nada que clasificar")
    print("NOT RUN  decisión BL-PORT2: pendiente de valorar la cifra con el PO")


def escribir_salida(clases: dict[str, Clase], series: Iterable[SerieCenso], *,
                    json_path: str | None, csv_path: str | None) -> None:
    if json_path:
        Path(json_path).write_text(
            json.dumps(informe_json(clases, series), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
    if csv_path:
        lineas = ["serie_id,clase"]
        lineas += [f"{sid},{clases[sid].value}" for sid in sorted(clases)]
        Path(csv_path).write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _argumentos(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Censo de solo lectura de portadas por debajo del objetivo (BL-PORT1 3/3).")
    parser.add_argument("--database-url", default=os.environ.get(
        "DATABASE_URL") or os.environ.get("TEST_DATABASE_URL"),
        help="PostgreSQL (por defecto DATABASE_URL o TEST_DATABASE_URL)")
    parser.add_argument("--covers", default=os.environ.get("COVERS_CACHE_PATH", "/config/covers"),
                        help="directorio de caché de portadas (por defecto COVERS_CACHE_PATH)")
    parser.add_argument("--json", "--salida", dest="json_path", default=None,
                        help="ruta del informe JSON (única escritura permitida)")
    parser.add_argument("--csv", dest="csv_path", default=None,
                        help="ruta opcional del CSV por serie (serie_id,clase)")
    return parser.parse_args(argv)


async def _main(argv: Sequence[str] | None = None) -> int:
    args = _argumentos(argv)
    if not args.database_url:
        print("Falta DATABASE_URL (o TEST_DATABASE_URL).", file=sys.stderr)
        return 2
    try:
        series = await leer_series(args.database_url)
    except Exception as exc:  # noqa: BLE001 — el informe no debe tumbar nada; solo dice FAIL
        print(f"FAIL  no se pudo leer la base ({type(exc).__name__}).", file=sys.stderr)
        return 1
    # Todo el I/O de disco (cabeceras de caché y páginas) va en un hilo, en bucle acotado.
    clases = await asyncio.to_thread(clasificar_series, series, Path(args.covers))
    desglose = desglose_sin_extractor(series, clases)
    imprimir_tabla(clases, desglose)
    try:
        escribir_salida(clases, series, json_path=args.json_path, csv_path=args.csv_path)
    except OSError as exc:
        print(f"FAIL  no se pudo escribir el informe ({type(exc).__name__}).", file=sys.stderr)
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
