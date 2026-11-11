# Clasificación de anuales — decisión y plan (fase 0 + fase 1)

**Estado:** decisión del PO (2026-11-11): **opción A**, serie anual propia con
enlace a la serie madre. **No autoriza migración ni backfill**: la fase 1
espera a una autorización explícita después del censo. La fase 0 (sin esquema)
va en esta rama.

**Censo real ejecutado (2026-11-11):** 80 archivos anuales, **0 series
anuales**, **25 enlazados a la serie madre** (5 series) y **55 sin Issue**;
todos en `/media/library`, ninguno desaparecido. El detalle y las muestras
están en [`censo-anuales-2026-11-11.md`](censo-anuales-2026-11-11.md). El censo
decide que el backfill hace falta, pero no lo autoriza.

**En esta rama:** la migración `0027` y el dry-run
`scripts/medicion/propuesta_anuales.py` están escritos y probados. La `0027`
**ya está aplicada en la Pi** (2026-11-11; ver
[`despliegue-0027-2026-11-11.md`](despliegue-0027-2026-11-11.md)): no movió
datos y la app sigue `healthy`. Las columnas nuevas son aditivas; el código de
la app de la Pi aún es el `main` anterior y las ignora.

**Lote 1 aplicado (2026-11-11):** 2 series anuales (`Batman Annual` y
`Batman: Shadow of the Bat Annual`), 7 Issues y 7 archivos enlazados; 0
archivos movidos. Quedan los 25 enlaces incorrectos y 48 anuales sin Issue.

**Problema.** Un archivo `Batman Annual 01` se parseaba como `Batman` `#1`; el
matcher podía enlazarlo con la grapa `Batman #1` y `numero_de_grapa` lo contaba
como ese hueco. Además, la serie anual que sí existe en Comic Vine/GCD/Metron
no se encontraba, porque el parser le borraba «Annual» al título.

**Benchmark.** `docs/design/benchmark-identidad-editorial.md` (Kapowarr,
Mylar3) y la consulta externa de 2026-11-11 (Metron `c6e1c48`, GCD `83cf0bb`,
Comic Vine, MetronInfo 1.2, ComicInfo/ComicTagger). Conclusión: en las
referencias examinadas, el anual tiene un **espacio de numeración propio**; el enlace a la
madre es opcional y casi siempre una relación aparte. Metron lo clasifica como
tipo de serie `Annual`; Mylar3 usa una tabla `annuals` con `ComicID` padre.
No se copia código: solo el contrato.

**Fuentes:** [Metron, tipos de serie](https://metron-project.github.io/blog/june-2024-update) ·
[MetronInfo, Series/Format](https://metron-project.github.io/docs/metroninfo/documentation) ·
[GCD, modelo Series/Issue](https://github.com/GrandComicsDatabase/gcd-django/blob/83cf0bb491e34b1284747285d08da96c7ec66973/apps/gcd/models/series.py) ·
[Comic Vine, hilo sobre anuales](https://comicvine.gamespot.com/forums/editing-tools-2761/about-annual-issues-702960/) ·
[Kapowarr, anuales](https://casvt.github.io/Kapowarr/general_info/implementation_details/) ·
[Mylar3, tabla annuals](https://github.com/mylar3/mylar3/blob/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316/mylar/__init__.py#L813)

## Decisión

Un **anual no es un número de la serie madre**. Se representa como una
**serie propia** (`Batman Annual`) con su propia numeración (`1..N` o el año),
y un enlace opcional y tipado a la serie madre. `Issue.format` no cambia: el
anual es una clasificación de serie/edición, no un formato de publicación.

```text
Batman (kind=regular)
  └── parent_series_id ── Batman Annual (1961, kind=annual) ── #1, #2...
  └── parent_series_id ── Batman Annual (2016, kind=annual) ── #1, #2...
```

Reglas:

1. Nunca se usa el número `#N` de la madre para un anual.
2. El anual tiene su propia completitud/huecos/wishlist; no suma en la madre.
3. `parent_series_id` es relación de presentación, no identidad; se propone y
   se confirma. No se deduce del título como verdad.
4. La numeración es texto: `1`, `2024` o `Anual 3`; no se inventa un entero.
5. Si no hay serie anual identificada, el archivo va a Pendientes. Nunca se
   prueba la grapa homónima.
6. `Especial` no es `Annual`: se mantiene como marca de edición de la serie
   madre (comportamiento actual) hasta que la clasificación de series lo
   contemple de forma explícita.

## Fase 0 — ya implementada (sin migración)

- `naming.py`: `ANNUAL_PATTERN` solo `Annual|Anual`; `SPECIAL_PATTERN` separa
  `Especial`. El anual **conserva** la palabra en el título (`Batman Annual`);
  el flag `is_annual` lo marca. Se añade `is_special`.
- `matcher.decide(..., annual=True)` solo acepta candidatas con título anual;
  los alias que apuntan a la madre se ignoran para un anual. Sin serie anual,
  `UNSORTED` y a Pendientes.
- `importer._triage_and_match` pasa `annual=parsed.is_annual` y conserva el
  título con «Annual».
- Pruebas: parser, clave de colección, matcher (madre/serie anual/alias) e
  importer.

**Límite de la fase 0:** es una heurística de título. No distingue una serie
que se llame «Annual» sin serlo, y no arregla los archivos ya enlazados a la
madre. Eso es fase 1.

## Fase 1 — censo ejecutado, pendiente de autorización

1. Censo de solo lectura ejecutado el 2026-11-11 con
   `scripts/medicion/censo_anuales.py`: 80 archivos anuales, 0 series anuales,
   25 enlazados a la madre y 55 sin Issue. Resultado en
   [`censo-anuales-2026-11-11.md`](censo-anuales-2026-11-11.md).
2. Migración **aditiva** `0027`: `series.kind` (`regular | annual | special`) y
   `series.parent_series_id` nullable, FK a `series.id`, con check de no
   auto-padre. Sin mover datos. Dry-run en
   `scripts/medicion/propuesta_anuales.py`: 21 series propuestas, 7 con padre,
   26 sin padre, 22 reclasificaciones, 14 números repetidos, 6 packs y 5 a
   revisar.
3. Alta/enlace: la serie anual usa sus IDs de fuente (Comic Vine/GCD/Metron);
   la enrichización funciona con el volumen anual. El enlace al padre se
   propone y se confirma, no se inventa.
4. Backfill: solo propuestas con revisión; nunca mover un archivo o un Issue
   en silencio. Los archivos anuales ya enlazados a la madre se listan.
5. UI: badge «Annual», sección «Anuales» en la ficha del padre, filtro de tipo,
   completitud separada y wishlist propia.
6. Pruebas de aceptación:
   - anual enlaza la serie anual y no la madre;
   - anual sin serie anual → Pendientes, sin tocar el `#N` de la madre;
   - `Batman #1` y `Batman Annual #1` coexisten;
   - dos líneas anuales (1961/2016) se distinguen por año/ID de fuente;
   - huecos de la madre intactos; huecos del anual propios;
   - migración aditiva con rollback; censo antes/después.

**No decidido aquí:** auto-crear la serie anual desde el nombre (recomendación:
no; enlazar solo si existe en la fuente o por confirmación humana), y el
tratamiento de los «Especiales» como serie propia. Se resolverán con el censo y
la especificación de la fase 1.
