# Benchmark M6-US03 · Varios identificadores de fuente por entidad (#129)

> Ficha de **nivel 2** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13).
> **Historia:** #129 «Asociar otra fuente explícitamente» (MIT-M6-US03), pendiente de DoR.
> **Fecha:** 2026-11-09. **SHA de ZascArr:** `ea230e570c3ade9d47a6d3274004caeaa014b816`
> (`origin/main`, 2026-11-09). La especificación hermana
> `docs/design/especificacion-M6-US03-asociar-fuente.md` se contrastó en `04ab6ee`; las citas de
> ZascArr se han vuelto a comprobar en `ea230e5` y no cambian.
> **Referencias:** Sonarr `c018578e` (2026-11-02) · Radarr `7e3f80c9` (2026-11-08) ·
> Kapowarr `c191dda6` (v1.3.2, 2026-09-14) · Mylar3 `cdc94a44` (v0.8.3, 2025-08-17).
> Las cuatro son **GPL-3.0**. Inspirarse en un patrón no es copiar código.
> **Método:** lectura de repositorios y documentos. **No** se ejecutó la aplicación ni pruebas,
> **no** se consultaron fuentes reales, **no** se tocó la base de datos. Lo no comprobado va
> `[sin verificar]` o NOT RUN. **Caduca:** ~60 días (2027-01-08), o antes si cambia la historia o
> una referencia. Es insumo para la especificación, no aprobación: decide el PO.

---

## 0. Veredicto en cinco líneas

1. **D1 se confirma:** la entidad asociada es la **serie**. Ni Sonarr/Radarr (serie/película) ni
   Kapowarr/Mylar3 (volume/issue) asocian varias fuentes a un número o a una edición.
2. **D2 se confirma con un matiz:** una por `(serie, fuente)` y varias fuentes por serie; pero
   Sonarr admite **varios** ids MAL/AniList por serie y Radarr separa `Movie` de `MovieMetadata`.
   «Una por fuente» es una decisión de producto, no una ley del dominio.
3. **D3 se confirma y se mejora:** ninguna referencia guarda procedencia por id; Sonarr y Radarr
   **sobrescriben** los ids secundarios en cada refresco. ZascArr debe anotar `{fuente, id, fecha,
   operacion_id, modo}` fuera de `metadata_source`.
4. **D4 se confirma:** las referencias solo corrigen **borrando y volviendo a añadir**. ZascArr debe
   retirar con historial; «sustituir» son dos operaciones, no un `UPDATE`.
5. **D5 se confirma y se amplía:** las referencias no tienen token ni comprobante (reañadir = error;
   refresco = última escritura). ZascArr reutiliza token + huella + `operacion_id` y añade el
   **modo «id exacto»**, que las tres referencias ya ofrecen como búsqueda.

---

## 1. Ficha breve (resumen para el PO)

| Campo | Contenido |
|---|---|
| **Historia / problema** | Asociar a una serie una segunda fuente (GCD, Tebeosfera, Comic Vine, AniList) de forma explícita, visible y reversible. Hoy no hay tabla, campo, ruta ni pantalla; el enricher excluye cualquier serie que ya tenga un id. |
| **Datos de partida** | Cuatro columnas únicas en `Series`; no hay medición de series con más de un id externo (el censo #181 mide colisiones de número, no identidad externa). |
| **Referencias** | Sonarr `c018578e` · Radarr `7e3f80c9` · Kapowarr `c191dda6` · Mylar3 `cdc94a44` (control). |
| **Cómo lo resuelven** | Columnas escalares por fuente, un id canónico único y el resto derivado/sobrescribible. Ninguna guarda procedencia. Kapowarr solo tiene Comic Vine y su unicidad es de aplicación. |
| **Supuestos que no valen** | Una fuente canónica completa; el usuario puede encontrar siempre la entidad; borrar y reañadir es barato; los ids secundarios son de la fuente y se pueden pisar. |
| **Resultado por idea** | §8: adoptar la unidad y la cardinalidad; adaptar la unicidad y la búsqueda por id; mejorar procedencia, conflicto, corrección e idempotencia; descartar tabla de metadatos, editor libre de ids y reasignación automática. |
| **Invariantes ZascArr** | No mentir, no borrar, confirmación explícita, coste Pi, una operación = un comprobante. |
| **Casos de prueba** | §11 (14 casos, no ejecutados). |
| **Decisión / ADR** | §15: no hace falta ADR; confirma columnas + JSONB + token. Si el PO eligiera tabla de asociaciones o varios ids por fuente, sí. |
| **Matriz** | §13 (nivel 2, criterios y pesos por defecto). |
| **IGUALAR / MEJORAR** | §12. |
| **NOT RUN** | §14. |
| **Caduca** | 2027-01-08 (~60 días). |

Esta ficha cierra el **NOT RUN** de benchmark de la especificación hermana (§5.3). No decide D1-D5:
argumenta y propone; el PO decide.

---

## 2. Problema local, caso y alcance

### 2.1 Qué falta

`Series` guarda la identidad externa en **cuatro columnas paralelas, cada una `unique=True`**:
`comic_vine_id`, `anilist_id`, `tebeosfera_slug` y `gcd_id`
(`src/zascarr/models/__init__.py:410-421`). El enricher considera «identificada» cualquier serie con
una de ellas y **no la empareja con otra fuente a propósito**
(`src/zascarr/services/enricher.py:190-202`; el docstring de `:32-36` lo razona). No existe tabla,
campo, servicio, ruta ni plantilla de «asociar fuente»; la asociación *es* el valor de la columna.

`metadata_source` es **univaluada** (`:424`): significa «fuente del alta o del enriquecimiento», y
`manual` **bloquea el enriquecimiento entero** (`services/enricher.py:202`). No cabe ahí «esta serie
también está en GCD». `locked_fields` protege campos del enriquecimiento, no identidad externa, y no
hay operación de desbloqueo en la UI (`docs/design/procedencia-127.md` §3).

### 2.2 Caso que motiva

Una serie dada de alta desde una carpeta con `comic_vine_id` (o con `tebeosfera_slug`) que el
coleccionista sabe que **también está en GCD**: hoy no puede declararlo sin cambiar la fuente de
enriquecimiento, tocar la base de datos o borrar la serie. El resultado deseado es una operación
explícita, confirmada, visible y reversible; que no fusione, no enriquezca, no toque archivos y no
elimine protecciones (#109, punto 7).

No se ha inventado un título concreto ni se ha consultado una fuente real: el caso es el patrón que
la historia describe, no un dato de la instalación.

### 2.3 Medición de partida (y su hueco)

El censo de identidad (#181) mide **colisiones de `number_key`** y recopilaciones, no cuántas series
tienen más de un identificador externo (`docs/design/censo-identidad-real.md:34-36`). Por tanto **no
hay medición de partida para D2**: que el modelo actual admita cuatro columnas no dice cuántas están
llenas a la vez.

Antes de implementar, un recuento de solo lectura cierra el hueco: cuántas series tienen 0, 1, 2, 3 o
4 ids no nulos, y cuántos valores se repiten en cada columna (no debería haber ninguno, por el
`UNIQUE`). No se ha ejecutado aquí (NOT RUN, §14). Es una consulta de minutos y evita diseñar para un
estado que no existe.

### 2.4 Fuera de alcance

- `Issue`, edición u obra: `Issue` solo tiene `comic_vine_id` (`models:489`) y #184 quedó pospuesta
  (ADR 0003).
- Enriquecimiento de metadatos: #128 y #127; asociar **no** cambia qué fuente enriquece.
- Mover, renombrar o escribir archivos.
- Un cliente o una fuente nuevos: solo las cuatro que ya existen.
- Pintar ids en la ficha: #127 decide no mostrarlos.

---

## 3. Referencias y método

### 3.1 Qué se consultó

| Referencia | Commit | Fecha | Versión | Licencia | Qué se leyó |
|---|---|---|---|---|---|
| **Sonarr** | `c018578e4b79ee048575c02d7a8aa2b929e4b837` | 2026-11-02 | rama `develop` | GPL-3.0 | `Tv/Series.cs`, `AddSeriesService`, `SeriesService`, `RefreshSeriesService`, `SeriesExistsValidator`, `SkyHookProxy`, migraciones 001/002/018/019/034/094/206/217, `SeriesResource`, `SeriesController`, modal de edición, alta, tests de refresco. |
| **Radarr** | `7e3f80c98d01481430ab356f6d7322fc5dc381ee` | 2026-11-08 | rama `develop` | GPL-3.0 | `Movies/Movie.cs`, `MovieMetadata`, `AddMovieService`, `MovieService`, `RefreshMovieService`, `MovieMetadataRepository`, `MovieExistsValidator`, `MovieLookupController`, migraciones 106/161/186/207, modal de edición, alta, tests. |
| **Kapowarr** | `c191dda6617929c81292483a8cc07f631111dae2` | 2026-09-14 | `V1.3.2` | GPL-3.0 | `implementations/volumes.py`, `internals/db.py`, `features/library_import.py`, `implementations/matching.py`, `implementations/comicvine.py`, `base/custom_exceptions.py`, UI de alta e importación, esquema y migraciones. |
| **Mylar3** | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` | 2025-08-17 | `v0.8.3` | GPL-3.0 | Esquema de `comics`/`issues`/`annuals` y `comicbookdb.py`; control de que el ecosistema de cómic no tiene un marco multi-fuente. |

Sonarr, Radarr y Kapowarr están activos; Mylar3 no tiene commits desde 2025-08-17 (v0.8.3) y se usa
como control histórico del ecosistema de cómic. No se examinaron Kavita, Komga, Suwayomi ni Comicarr
para esta ficha: se consideraron menos pertinentes para el problema de identidad multi-fuente de una
serie (Kavita/Komga leen ficheros; Suwayomi indexa capítulos). Se declara como límite, no como
ausencia.

### 3.2 Qué se ejecutó

Nada de la aplicación. La evidencia es **lectura** de código, migraciones, plantillas y pruebas. No
se llamó a TVDB, TMDb, Comic Vine, GCD ni Tebeosfera; no se abrió la UI; no se midió RAM ni latencia
en la Pi. Las afirmaciones sobre comportamiento en marcha van marcadas `[sin verificar]`.

---

## 4. Cómo lo resuelve cada referencia

### 4.1 Sonarr

**Modelo.** `Series` lleva `TvdbId`, `TvRageId`, `TvMazeId`, `ImdbId`, `TmdbId`, y **dos conjuntos**
`MalIds` y `AniListIds` (`src/NzbDrone.Core/Tv/Series.cs:26-32`). Es decir: varias fuentes a la vez,
pero con dos formas de cardinalidad: escalar para las fuentes «clásicas» y conjunto para MAL/AniList.

**Dónde vive y qué es único.**

- `TvdbId` es el id canónico. Nació `UNIQUE` (`Datastore/Migration/001_initial_setup.cs:19`) y se
  restauró tras una migración que borró duplicados (`018_remove_duplicates.cs`,
  `019_restore_unique_constraints.cs:11-13`).
- `TvRageId` e `ImdbId` nacieron `UNIQUE` (`001:20-21`), pero se les quitó el índice en la migración
  `002` y se hicieron nullable en la `034` (`002_remove_tvrage_imdb_unique_constraint.cs:11-12`;
  `034_remove_series_contraints.cs:12-13`). El código **no documenta el motivo**; no se infiere.
- `TvMazeId` se añadió con índice **no único** (`094_add_tvmazeid.cs:11-12`).
- `TmdbId` se añadió mucho después, también con índice **no único** (`206_add_tmdbid.cs:11-12`).
- `MalIds` y `AniListIds` se añadieron como **columna de texto con un array JSON** (valor por
  defecto `[]`), no como enteros paralelos (`217_add_mal_and_anilist_ids.cs:11-12`).

**Cómo se rellenan.** El alta siempre parte de `TvdbId`: `AddSeriesService.AddSkyhookData` pide la
ficha a Skyhook por ese id y el resto de ids vienen de la respuesta
(`Tv/AddSeriesService.cs:113-130`). El usuario no teclea IMDb/TMDb: busca por título o por
`tvdb:`/`tvdbid:` (`MetadataSource/SkyHook/SkyHookProxy.cs:120-146`). El refresco **sobrescribe**
todos los ids secundarios con lo que diga Skyhook (`Tv/RefreshSeriesService.cs:97-100`).

**Conflicto.** El POST valida `TvdbId > 0` y que no exista otra serie con ese id
(`Sonarr.Api.V3/Series/SeriesController.cs:104`;
`Validation/Paths/SeriesExistsValidator.cs:16,27`). El alta masiva filtra duplicados por `TvdbId` y
los omite con un log de depuración (`Tv/AddSeriesService.cs:61,79-82`). No reasigna en el alta.

**Reasignación automática.** Si Skyhook devuelve otro `TvdbId` porque el original era un duplicado en
TVDB, el refresco **cambia el id de la serie en su sitio** y deja solo un warning
(`Tv/RefreshSeriesService.cs:86-89`). Está probado como comportamiento intencionado
(`TvTests/RefreshSeriesServiceFixture.cs:191-204`, `should_update_if_tvdb_id_changed`). No se
comprueba si el id nuevo ya pertenece a otra serie local: la barrera es el índice único, y el fallo
lo captura el `catch` genérico del refresco.

**UI y corrección.** El modal de edición expone monitorización, perfil, tipo, carpeta y etiquetas;
**ningún campo de id** (`frontend/src/Series/Edit/EditSeriesModalContent.tsx:202,245,257,313,335`).
El alta sí ofrece `tvdb:####` (`AddSeries/AddNewSeries/AddNewSeries.tsx:93,141,160`). Para corregir
un id equivocado no hay editor: se borra la serie y se vuelve a añadir
(`Tv/SeriesService.cs:175-180`); `deleteFiles=false` conserva los archivos en disco, pero la
entrada de biblioteca y su identidad no se recuperan.

**Matiz de contrato.** La UI no edita ids, pero el `PUT` mapea `TvdbId` desde el cuerpo
(`SeriesResource.ToModel` y `Series.ApplyChanges`, `Tv/Series.cs:81`) y el `PutValidator` **no**
aplica el validador de existencia (solo el `PostValidator` lo hace,
`SeriesController.cs:95-104`). Es una vía de cambio de identidad sin conflicto explicado, aunque la UI
no la use. No se ejecutó: es lectura de código.

### 4.2 Radarr

**Modelo.** Radarr separa la **entrada de biblioteca** (`Movie`) de la **ficha de fuente**
(`MovieMetadata`). `Movie` guarda `MovieMetadataId`, ruta, perfil, monitorización y etiquetas; la
ficha guarda `TmdbId`, `ImdbId`, título, imágenes, etc. (`Movies/Movie.cs:47-56`;
`Movies/MovieMetadata.cs:24,41`). `Movie.TmdbId` e `Movie.ImdbId` son propiedades de compatibilidad
que delegan en la ficha.

**Dónde vive y qué es único.**

- `MovieMetadata.TmdbId` es `UNIQUE` (`Migration/207_movie_metadata.cs:11-12`).
- `Movies.MovieMetadataId` es `UNIQUE` (`207:86`): una entrada de biblioteca por ficha.
- Antes de la separación, `Movies.TmdbId` ya era `UNIQUE`; la migración `186_fix_tmdb_duplicates`
  borró duplicados (conservando la fila con archivo, luego la que tenía info, luego la más antigua) y
  creó el índice único (`186:17-18,28-60`).
- `ImdbId` **no** es único; es un campo de la ficha que llena TMDb
  (`Migration/106_add_tmdb_stuff.cs:12-16`).

**Cómo se rellenan.** El alta parte de `TmdbId`: `AddMovieService.AddSkyhookData` pide la ficha por
ese id (`Movies/AddMovieService.cs:114`), y `MovieMetadataRepository.UpsertMany` **fusiona por
`TmdbId`**: si ya existe, conserva el id de base y actualiza lo que cambió
(`Movies/MovieMetadataRepository.cs:54-73`). El `ImdbId` llega de TMDb; no se teclea. La búsqueda
acepta `tmdb:` e `imdb:` (`frontend/src/AddMovie/AddNewMovie/AddNewMovie.js:106`) y hay endpoints
`/movie/lookup/tmdb` y `/movie/lookup/imdb`
(`Radarr.Api.V3/Movies/MovieLookupController.cs:58-71`).

**Conflicto.** El POST valida que no exista una película con ese `TmdbId`
(`Validation/Paths/MovieExistsValidator.cs:16,26`; `MovieController.cs:113`). El alta masiva **no**
filtra duplicados por `TmdbId` en `AddMovieService`; las últimas barreras son los índices únicos de
`MovieMetadata.TmdbId` y `Movies.MovieMetadataId` (observación de código, no ejecutada).

**Reasignación automática.** Igual que Sonarr: si TMDb dice que el id fue reemplazado por un
duplicado, el refresco cambia `MovieMetadata.TmdbId` en su sitio (`RefreshMovieService.cs:100-103`),
con prueba intencionada (`MovieTests/RefreshMovieServiceFixture.cs:100-110`,
`should_update_if_tmdb_id_changed`).

**UI y corrección.** El modal de edición expone monitorización, disponibilidad, perfil, carpeta y
etiquetas; **ningún id** (`frontend/src/Movie/Edit/EditMovieModalContent.tsx:169,190,201,212,234`).
El `PUT` de Radarr **no** copia `TmdbId`/`ImdbId` (`Movie.ApplyChanges`, `Movies/Movie.cs:150-162`),
así que la identidad no se cambia por esa vía. La corrección es borrar y volver a añadir
(`MovieService.DeleteMovie`).

### 4.3 Kapowarr

**Modelo.** Solo Comic Vine. `volumes.comicvine_id` y `issues.comicvine_id` son la identidad; no hay
columna de otra fuente ni tabla de asociaciones (`backend/internals/db.py:387-433`). `issues` tiene
`UNIQUE` (`:419`); **`volumes` no** (`:389`). La unicidad del volumen es **solo de aplicación**:
`Library.add` consulta `_cv_to_id` y lanza `VolumeAlreadyAdded` si ya existe
(`implementations/volumes.py:1060-1072,1141-1143`). Dos altas concurrentes podrían duplicar; el
esquema no lo impide.

**Conflicto.** `VolumeAlreadyAdded` responde 400 con `comicvine_id` y `volume_id`
(`base/custom_exceptions.py:348-367`). La búsqueda marca `already_added` con el id local
(`implementations/comicvine.py:404-413`) y la UI lo pinta (`frontend/static/js/add_volume.js:76-91`).

**Importación de una serie ya existente.** `import_library` llama a `Library.add`; si salta
`VolumeAlreadyAdded`, **reutiliza** el `volume_id` existente y mueve los archivos a su carpeta
(`features/library_import.py:295-322`). No crea un volumen duplicado. El comentario del código
reconoce el riesgo inverso: si los archivos se emparejaron con el volumen equivocado y ese volumen
ya existía, se mueven igualmente (viñeta 2 del comentario, `:305-312`).

**Cómo se empareja.** `select_best_volume_result_for_file` filtra por título, idioma, tipo de
especial y número de issues, y ordena por una puntuación; devuelve el primero
(`implementations/matching.py:511-656`). Los empates conservan el orden de la búsqueda; **no hay
desempate explícito ni confirmación**. En la vista previa de importación sí se puede **cambiar la
elección** buscando otro CV (`frontend/static/js/library_import.js:218-273`), pero una vez añadido no
hay editor de id.

**Búsqueda por id exacto.** La UI acepta `cv:4050-2127`, `cv:2127` o `4050-2127`
(`frontend/templates/add_volume.html:134`), además del título. Es un alias de búsqueda, no una
asociación persistida.

**Corrección y deshacer.** Borrar el volumen y volver a añadirlo; no hay historial de identidad ni
deshacer. El id no se edita en ninguna pantalla.

### 4.4 Mylar3 (control)

`comics.ComicID` es `TEXT UNIQUE` (`mylar/__init__.py:805`): el id de Comic Vine es la única
identidad de la serie. `issues.IssueID` y `ComicID` relacionan números (`:806`). `annuals.GCDComicID`
es un id auxiliar de la tabla de anuales de GCD (`mylar/comicbookdb.py:212`), no una segunda
fuente asociada a la serie. No hay marco multi-fuente, ni procedencia, ni editor de id. Confirma la norma
del ecosistema de cómic en lo leído: **un id canónico por serie**, no varios.

### 4.5 ZascArr hoy (contraste)

| Pieza | Hoy | Dónde |
|---|---|---|
| Cuatro ids en columnas paralelas, cada uno `UNIQUE` | Sí | `models/__init__.py:410-421` |
| Varias fuentes a la vez | El esquema lo admite; nada las lee en conjunto | `enricher.py:190-202` |
| Fuente del alta/enriquecimiento | `metadata_source` univaluada; `manual` bloquea el enricher | `models:424`; `enricher.py:202` |
| Protección por campo | `locked_fields`; sin operación de desbloqueo | `models:431`; `procedencia-127.md` §3 |
| Asociación con procedencia | No hay servicio, tabla, campo ni ruta (spec §1.6) | `grep` de `asociar` solo devuelve comentarios |
| Corrección de identidad | No hay editor de ids; solo alta/retirada | `services/edicion_serie.py:36` |
| Reutilización al chocar el `UNIQUE` | El alta busca la existente y la reutiliza | `services/alta_serie.py:461-473` |
| Procedencia por operación en JSONB | `metadata.alta`, `metadata.vinculo_historial` | `alta_serie.py:211-218`; `desvinculacion.py:194-229` |
| Comprobante idempotente | `vinculacion_operaciones`, disparador inmutable | `models:729-748`; migración `0019:49-59` |
| Token con huella | `tokens_revision` + `_huella` de #128 | `tokens_revision.py:90-125`; `enriquecimiento_plan.py:138-158` |

La base propia ya tiene las piezas que a las referencias les faltan: procedencia versionada, historial
de deshacer y comprobante inmutable. El benchmark no las inventa; confirma que son el camino.

---

## 5. Matriz proyecto × aspecto

### 5.1 Referencias

| Aspecto | Sonarr | Radarr | Kapowarr | Mylar3 |
|---|---|---|---|---|
| **Entidad asociada** | Serie | Película | Volume | Comic |
| **Dónde vive el id** | Columnas escalares + arrays JSON para MAL/AniList | `MovieMetadata` (tabla) con `TmdbId`/`ImdbId`; `Movie` apunta | `volumes.comicvine_id` | `comics.ComicID` |
| **Varias fuentes a la vez** | Sí (TVDB, TVRage, TVMaze, IMDb, TMDb, MAL, AniList) | Sí (TMDb, IMDb) | No (solo CV) | No (solo CV) |
| **Unicidad** | `TvdbId` único; `ImdbId`/`TvRageId` sin único desde 002/034; `TmdbId`/`TvMazeId` índice no único; MAL/AniList sin índice | `MovieMetadata.TmdbId` único; `Movies.MovieMetadataId` único; `ImdbId` no único | `issues.comicvine_id` único; `volumes.comicvine_id` **sin** único en esquema | `ComicID` único |
| **Id ya existente** | POST rechaza («already added»); alta masiva omite; refresco puede reasignar en sitio | POST rechaza; refresco puede reasignar en sitio; alta masiva sin filtro | `VolumeAlreadyAdded` 400; import reutiliza el volumen | No se ve un camino de alta masiva; `ComicID` único |
| **Relleno** | Alta por `TvdbId`; resto de Skyhook; refresco sobrescribe | Alta por `TmdbId`; IMDb de TMDb; refresco sobrescribe | Alta por CV id; sin otra fuente | Alta por CV id |
| **Manual vs automático** | No hay marca por id; el usuario elige la entidad, los ids son de la fuente | No hay marca por id; IMDb es derivado | No hay marca; solo CV | No hay marca |
| **¿Editar id en UI?** | No; el PUT mapea `TvdbId` sin validador de existencia | No; el PUT no copia ids | No; solo elegir el CV en la vista previa de importación | No |
| **Corrección** | Borrar + reañadir | Borrar + reañadir | Borrar + reañadir | Borrar + reañadir |
| **Deshacer** | No | No | No | No |
| **Idempotencia / reintento** | Reañadir = error; refresco = última escritura; sin comprobante | Upsert de metadata idempotente; alta no; sin comprobante | Import repetido reutiliza; alta repetida = 400; sin comprobante | Sin comprobante |
| **Búsqueda por id exacto** | `tvdb:` / `tvdbid:` | `tmdb:` / `imdb:`; endpoints `/lookup/tmdb` y `/lookup/imdb` | `cv:` / `4050-2127` | No se encontró en lo leído `[sin verificar]` |
| **Importación masiva** | Filtra duplicados por `TvdbId` y los omite en silencio | No filtra en `AddMovieService`; barrera = índice | Reutiliza el volumen existente y mueve archivos; acepta riesgo de mal match | No examinada |

### 5.2 ZascArr hoy frente a la propuesta #129

| Aspecto | Hoy | #129 (propuesta) |
|---|---|---|
| Entidad | `Series` | `Series` (sin cambio) |
| Almacenamiento del id | 4 columnas, `UNIQUE` por columna | Se rellena la columna de la fuente; el id no se mueve a JSONB |
| Varias fuentes | El esquema lo admite; el enricher no las busca | Varias fuentes por serie, una por fuente |
| Unicidad | BD, por columna | BD, por columna; el servicio **pre-comprueba** y mapea `IntegrityError` |
| Procedencia | `metadata_source` univaluada; `metadata.alta` | `metadata.asociaciones` versionado, fuera de `metadata_source` |
| Conflicto | `IntegrityError` / reutilización silenciosa en el alta | Rechazo explícito con motivo; tres desenlaces |
| Corrección | No hay editor de ids; retirar serie | Retirar la asociación con historial; sustituir = retirar + asociar |
| Idempotencia | `vinculacion_operaciones` para vincular/retirar | Mismo almacén, `tipo = "asociar_fuente"` |
| UI | No existe | Flujo guiado: buscar/pegar id, comparar, confirmar, ver y retirar |

---

## 6. Patrones comunes y sus límites

### 6.1 Columnas, JSONB o tabla

Las referencias usan **columna escalar** para el id canónico y, como mucho, **array JSON en columna
de texto** para fuentes de cardinalidad variable (Sonarr, `MalIds`/`AniListIds`,
`217:11-12`). Radarr va más lejos y separa una **tabla de ficha de fuente** (`MovieMetadata`), que
comparte con listas de importación (`ImportListMovies.MovieMetadataId`, `207:57`); la entrada de
biblioteca sigue siendo una fila con un puntero único.

Para ZascArr, la columna es la única forma de que el `UNIQUE` de Postgres impida que el mismo id esté
en dos series y de que el enricher filtre con un `WHERE ... IS NULL` barato. El JSONB no debe ser la
fuente de verdad del id vigente: sirve para la **procedencia y el historial**, no para sustituir la
columna. Una tabla `series_fuentes` daría más generalidad, pero exige migración, índice único
compuesto y joins en el enricher; no hay evidencia de que haga falta (censo #181: 0 colisiones de
número, no de identidad; ver §2.3).

### 6.2 Unicidad

Sonarr, Radarr y Mylar3 confían en una restricción de base de datos para el id canónico; Sonarr y
Radarr además **pre-comprueban** para dar un mensaje. Kapowarr solo pre-comprueba: su esquema no tiene
`UNIQUE` en `volumes.comicvine_id`, así que la garantía es de aplicación y una carrera puede
duplicar. La lección es doble: pre-comprobar para el mensaje, **y** mantener el `UNIQUE` para la
corrección; mapear `IntegrityError` al mismo conflicto que la pre-comprobación, nunca a un 500.

Sonarr también enseña el límite: `ImdbId`/`TvRageId` dejaron de ser únicos en las primeras
migraciones. No se documenta el motivo y no se infiere. Lo que sí se ve es que la unicidad se
decidió **por fuente** y se revisó con el tiempo: no se puede copiar «unique en todo» sin comprobar
la cardinalidad de cada fuente.

### 6.3 Procedencia

Ninguna referencia guarda «este id lo puso una persona el día X». El id canónico es de la fuente y
los secundarios se **sobrescriben** en cada refresco (Sonarr `RefreshSeriesService.cs:97-100`;
Radarr `RefreshMovieService.cs:107`). No hay `manual` por id, ni historial, ni forma de saber si un
valor se corrigió a mano. Por eso no se puede adoptar su modelo de procedencia: **no existe**. La
procedencia tiene que ser un dato propio, y ZascArr ya tiene el patrón (`metadata.alta`,
`vinculo_historial`).

### 6.4 Corrección

Las tres referencias corrigen **borrando y volviendo a añadir**. Sonarr y Radarr llegan a borrar
filas en migraciones para imponer el `UNIQUE` (`018_remove_duplicates.cs`;
`186_fix_tmdb_duplicates.cs:28-60`): la corrección de identidad es destructiva y no tiene deshacer.
En ZascArr, donde una serie tiene números, archivos e historial, eso no es aceptable. La corrección
debe ser una operación explícita sobre la asociación, no sobre la serie.

### 6.5 Idempotencia

El alta no es idempotente en Sonarr/Radarr (repetir devuelve error de validación) y el refresco es
«última escritura gana». Radarr sí tiene un upsert idempotente de **metadata** por `TmdbId`
(`MovieMetadataRepository.UpsertMany`), pero no de la entrada de biblioteca. Ninguna referencia tiene
token, huella ni comprobante. ZascArr no debe copiar ese nivel: la operación de asociar debe devolver
el mismo resultado al repetir el mismo token, y no debe decidir vigencia con `updated_at`.

### 6.6 Cardinalidad

«Una por fuente» es lo habitual, pero **no universal**: Sonarr admite varios MAL/AniList ids por
serie (modelo y migración 217; el código no documenta el porqué). Es una decisión de
producto, no una verdad del dominio. Para #129, una por `(serie, fuente)` es razonable (simplicidad,
UI y ausencia de evidencia en contra); si algún día una fuente devuelve varias, el sitio natural es una lista en
`metadata.asociaciones` o una tabla, no una columna nueva. Se declara como límite conocido, no se
resuelve ahora.

### 6.7 Búsqueda por id

Las tres referencias ofrecen un **alias de búsqueda por id exacto** (`tvdb:`, `tmdb:`/`imdb:`,
`cv:`/`4050-2127`). No es una asociación: resuelve el id a la entidad canónica y luego se añade. Es
una lección de UX barata: el coleccionista que tiene el id de GCD a mano no debería depender de una
búsqueda por título que puede devolver homónimas. #129 debería aceptar el id exacto como modo de la
entrega A, con una sola petición y el mismo token.

---

## 7. Supuestos de las referencias que NO valen en ZascArr

| Supuesto | Sonarr / Radarr | Kapowarr / Mylar3 | Por qué no vale aquí |
|---|---|---|---|
| **Hay una fuente canónica completa** | TVDB/TMDb es la verdad; el resto se deriva | Comic Vine es la única | ZascArr elige por tradición entre cuatro fuentes y las españolas (Tebeosfera, GCD) son primarias para muchas series. |
| **El usuario siempre puede encontrar la entidad en la fuente** | Buscar por título o id canónico | Buscar por título o CV | Una edición española puede no estar bien indexada o tener homónimas; por eso la asociación explícita. |
| **Los ids secundarios son de la fuente y se pueden pisar** | Refresco sobrescribe | Solo hay un id | ZascArr conserva ediciones manuales y procedencia; pisar un id confirmado es mentir. |
| **Borrar y reañadir es barato** | La entidad no tiene archivos propios (o se conservan aparte) | El volumen se puede reañadir | Una serie tiene números, archivos e historial; borrar pierde identidad y contexto. |
| **El emparejamiento automático puede aceptar un mal match** | El refresco reasigna y avisa | El import mueve archivos al volumen ya existente | ZascArr exige confirmación para asociar; un id equivocado no debe entrar por la puerta de atrás. |
| **La unidad es el volume/issue** | Serie/película | Volume/issue | La unidad catalogada de ZascArr es la **serie** (ADR 0003); no hay edición ni obra. |
| **No hace falta procedencia** | No hay campo | No hay campo | #109 y #127 la exigen; ZascArr ya la tiene para el alta y el vínculo. |

---

## 8. Resultado por idea

| Idea | Resultado | Motivo y evidencia | Qué implica para #129 |
|---|---|---|---|
| **Entidad = serie** | **Adoptar** | Sonarr/Radarr asocian a la entidad catalogada; Kapowarr a volume; ZascArr cataloga series (ADR 0003). | D1 (a), sin cambio. |
| **Varias fuentes a la vez, una por fuente** | **Adoptar** | Sonarr lleva 7 fuentes; Radarr 2; ZascArr ya tiene 4 columnas. | D2 (a), sin cambio. |
| **Id vigente en columna, `UNIQUE` por fuente** | **Adoptar** | Es lo que ya hace ZascArr y lo que da la garantía que Kapowarr no tiene en `volumes`. | D2; el servicio pre-comprueba y mapea `IntegrityError`. |
| **Solo ids 1:1 con la entidad** | **Adaptar** | Sonarr admite varios MAL/AniList; Tebeosfera puede devolver `collection`/`saga` (spec, D-A1). | Validar `kind`/cardinalidad antes de asociar; no confiar solo en el `UNIQUE`. |
| **Búsqueda por id exacto** | **Adoptar / adaptar** | `tvdb:`, `tmdb:`/`imdb:`, `cv:`/`4050-2127`; una petición, sin paginar. | Añadir modo «id exacto» a la entrega A y al token (D5). |
| **Conflicto = rechazo con explicación, no reasignación** | **Mejorar** | Sonarr/Radarr rechazan en el alta, pero **reasignan en el refresco** si la fuente fusiona (`RefreshSeriesService.cs:86-89`, probado). | D2/D5: tres desenlaces; nunca reescribir un id ajeno. |
| **Tabla de metadata separada (`MovieMetadata`)** | **Descartar** | Radarr la necesita para compartir ficha con listas; ZascArr ya tiene `metadata` JSONB y 4 fuentes. | No migración; no tabla nueva. |
| **Procedencia por asociación** | **Mejorar** | Ninguna referencia la tiene; sobrescriben. ZascArr ya tiene `metadata.alta` y `vinculo_historial`. | D3: `metadata.asociaciones` versionado. |
| **Corrección = borrar + reañadir** | **Descartar** | Destructiva y sin deshacer; Sonarr/Radarr incluso purgan filas en migraciones. | D4: retirar con historial; sustituir = retirar + asociar. |
| **Reasignación automática cuando la fuente fusiona** | **Descartar** | Cambia el id en sitio, sin historial y sin comprobar colisión local; probado como intencionado. | D4: avisar, no reescribir; el usuario decide. |
| **Dedupe silencioso en importación** | **Descartar** | Sonarr omite duplicados con log de depuración; Kapowarr reutiliza el volumen y mueve archivos. | Devolver `repetida`/`conflicto` con comprobante; no silencio. |
| **Token + huella + `operacion_id`** | **Construir sobre lo propio** | #128, #303 y `vinculacion_operaciones` ya lo tienen; las referencias no. | D5: reutilizar, `tipo = "asociar_fuente"`. |
| **Editor libre de ids («escribe el tvdbId»)** | **Descartar** | Ninguna referencia lo tiene; la UI solo busca/elegir. Un campo libre invita a errores y a ids huérfanos. | UI guiada: buscar o pegar id, comparar, confirmar, retirar. |

---

## 9. Reglas para ZascArr (3-5)

### R1 · El id vive en su columna; la procedencia, en JSONB

Una asociación escribe **solo** la columna de esa fuente (`Series.comic_vine_id`,
`anilist_id`, `tebeosfera_slug` o `gcd_id`) y añade una entrada a `metadata.asociaciones`. La columna
es la verdad del id vigente; el JSONB es el **registro de operaciones** (append-only), no una segunda
copia del estado. La entrada lleva `version`, `fuente`, `id_externo`, `entidad: "serie"`, `fecha`,
`operacion_id`, `origen` y `modo` (`busqueda`/`id_exacto`). El `UNIQUE` de la columna se mantiene. Para
leer la procedencia del id vigente se toma la última entrada no retirada de esa fuente; si su
`id_externo` no coincide con la columna, el estado es inconsistente y se trata como error de datos,
no como una segunda verdad.

**Confirma D1/D2/D3.** No se toca `metadata_source` ni `locked_fields`. `fusionar_metadata` sigue
sin pisar `alta`.

### R2 · Tres desenlaces, no uno

Al confirmar una asociación solo puede pasar una de estas tres cosas:

1. **Mismo id, misma serie:** éxito idempotente; se devuelve `repetida: true` y el mismo comprobante,
   sin escribir.
2. **Mismo `(serie, fuente)` con otro id:** se rechaza como «ya tiene otra; retírala primero». Nunca
   se sobrescribe.
3. **El id pertenece a otra serie:** se rechaza con «pertenece a otra serie» y **no se reasigna**.

La pre-comprobación da el mensaje; el `UNIQUE` da la garantía. Un `IntegrityError` de carrera se
mapea al mismo conflicto, nunca a un 500. Si la fuente puede devolver una ficha que no es 1:1 con la
serie (Tebeosfera `saga`), se rechaza antes de firmar el token.

**Confirma D2 y precisa D5.** Es el punto que las referencias no cubren: Sonarr/Radarr solo tienen
los casos 1 y 3 (y el 3 lo resuelven rechazando en el alta, pero reasignando en el refresco).

### R3 · Nada se reescribe ni se borra en silencio

No hay corrección por `UPDATE` de un id existente. Para cambiar de id: **retirar** (quitar el id de
esa fuente y añadir a `metadata.asociaciones_historial` una entrada con `deshecho: {operacion_id,
fecha}` y `previo`) y **asociar** el nuevo, en dos operaciones con dos comprobantes. La retirada no
toca las demás fuentes, no borra la serie, no toca archivos y no aplica metadatos. Si la fuente dice
que el id fue fusionado o retirado, se muestra un aviso y se pide acción; **nunca** se reescribe solo.

**Confirma D4.** Es la diferencia deliberada con Sonarr/Radarr (`RefreshSeriesService.cs:86-89`) y
con Kapowarr (borrar volumen).

### R4 · La procedencia no es `metadata_source`

No se pone `metadata_source = 'manual'` ni se cambia la fuente de enriquecimiento. `metadata_source`
sigue siendo la fuente del alta/enriquecimiento; la asociación se registra aparte. Se conserva la
procedencia aunque el id ya existiera (si el enricher lo puso, la entrada dice `origen:
"enriquecimiento"`; si lo confirmó una persona, `"confirmada"`). Sin usuario, sin sesión, sin IP: no
es auditoría, es procedencia y comprobante.

**Confirma D3.** Evita el bloqueo total del enricher que produciría `manual` y la atribución falsa de
metadatos que produciría `metadata_source = <fuente asociada>`.

### R5 · Token, huella, `operacion_id` y comprobante

La propuesta se firma con un token de propósito `asociar_fuente`, TTL de 15 min y una huella que incluye:
título, año, tradición, los cuatro ids, `metadata_source`, `locked_fields`,
`metadata.asociaciones` de la serie y la identidad firmada de la candidata (fuente + id + `kind` si
lo hay). Se revalida dentro de la transacción, con candado consultivo por `operacion_id` y
`SELECT ... FOR UPDATE` de la serie. Repetir el token devuelve el mismo comprobante
(`vinculacion_operaciones`, `resultado.tipo = "asociar_fuente"`). `updated_at` **no** decide: cambia
con cualquier edición y no distingue qué cambió. El modo «id exacto» se firma igual y hace **una**
petición, sin paginar.

**Confirma D5 y lo amplía** con el modo de id exacto, que las tres referencias ofrecen como búsqueda
pero no como operación persistida.

---

## 10. Qué confirma o cambia en D1-D5

| Decisión | Veredicto | Cambio concreto | Evidencia |
|---|---|---|---|
| **D1 · Entidad** | **Confirma** | Ninguno: `Series`, no `Issue` ni edición/obra. Las referencias tampoco asocian varias fuentes a un número. | Sonarr `Series`; Radarr `Movie`; Kapowarr `Volume`; Mylar3 `Comic`; `Issue` solo `comic_vine_id` en ZascArr. |
| **D2 · Cardinalidad** | **Confirma, con matiz** | Una por `(serie, fuente)`, varias fuentes por serie; conflicto = rechazo. Añadir: pre-comprobar **y** `UNIQUE`; mapear `IntegrityError`; validar que la fuente es 1:1 antes de asociar; medir cuántas series tienen varios ids antes de implementar. | Sonarr 7 fuentes pero `TvdbId` único; `MalIds`/`AniListIds` como conjunto; Kapowarr solo pre-comprueba; Radarr `MovieMetadata` único. |
| **D3 · Procedencia** | **Confirma y mejora** | `metadata.asociaciones` versionado con `origen` y `modo`; no tocar `metadata_source` ni `locked_fields`; la columna es la verdad, el JSONB es historial. | Ninguna referencia guarda procedencia; Sonarr/Radarr sobrescriben; ZascArr ya tiene `metadata.alta` y `vinculo_historial`. |
| **D4 · Corrección** | **Confirma** | Retirar con historial; sustituir = retirar + asociar; prohibido el `UPDATE` en un paso y la reasignación automática. | Sonarr/Radarr borran y reañaden; migraciones 018/186 purgan filas; ZascArr `desvinculacion.py:194-229`. |
| **D5 · Vigencia e idempotencia** | **Confirma y amplía** | Token + huella + `operacion_id` + comprobante; **añadir** `modo` (`busqueda`/`id_exacto`), los tres desenlaces y el `tipo` nuevo; `updated_at` no decide. | ZascArr `tokens_revision`, `enriquecimiento_plan._huella`, `vinculacion_operaciones`; referencias sin token. |

**Lo que cambia de verdad respecto a la especificación actual:**

1. **Modo «id exacto»**: la especificación de A no menciona el id exacto. Las tres referencias
   permiten pegarlo; conviene aceptarlo como modo firmado, con una sola petición.
2. **Los tres desenlaces** de R2: la especificación dice «rechaza» para el conflicto, pero no separa
   «mismo id repetido» (idempotente) de «otro id de la misma fuente» (retirar primero) y de «id de
   otra serie» (no reasignar). Es una precisión de contrato, no un cambio de decisión.
3. **Validar la cardinalidad de la fuente** antes de asociar (Tebeosfera `saga`): el `UNIQUE` no
   basta si la fuente no es 1:1. Enlaza con D-A1.
4. **Medir antes de implementar**: el censo #181 no cuenta series con varios ids; el `UNIQUE` no
   sustituye a la medición.

---

## 11. Casos de prueba antes de implementar (no ejecutados)

Estos casos se escribirán **antes** del código y se ejecutarán en la implementación; aquí solo se
enumeran. No son código ni se han ejecutado.

1. **Asociar una segunda fuente:** serie con `comic_vine_id`, se asocia un `gcd_id` válido; la
   columna queda llena, `metadata.asociaciones` tiene una entrada con `operacion_id`, y
   `metadata_source`, `locked_fields`, números, archivos y la fuente de enriquecimiento no cambian.
2. **Repetir el mismo id y la misma serie:** `repetida: true`, mismo comprobante, sin escritura
   nueva (contar filas/entradas antes y después).
3. **Id de otra serie:** el mismo `gcd_id` ya está en otra serie; se rechaza con un motivo claro, no
   se reasigna y no se escribe nada.
4. **Otro id de la misma fuente:** la serie ya tiene `comic_vine_id`; se intenta otro
   `comic_vine_id`; se rechaza «ya tiene otra; retírala primero», sin sobrescribir.
5. **Token caducado o manipulado:** se rechaza sin escribir; el mensaje pide volver a revisar.
6. **Huella cambiada:** entre la vista y la confirmación se asocia otra fuente o cambia un id; se
   rechaza por huella y no se aplica.
7. **Retirar:** se quita el id de esa fuente, las demás quedan intactas, la serie y los archivos
   siguen, y `metadata.asociaciones_historial` guarda `deshecho` con `previo` y `operacion_id`.
8. **Sustituir:** retirar + asociar produce dos comprobantes; no existe un camino de un solo paso que
   pise el id.
9. **Dos envíos simultáneos del mismo token:** el candado consultivo serializa; una escritura y dos
   respuestas iguales.
10. **Resultado desconocido:** se pierde la respuesta tras pedir `commit`; se relee por
    `operacion_id` y no se anuncia «no se ha cambiado nada».
11. **Carrera de unicidad:** dos operaciones intentan el mismo id a la vez; una gana y la otra
    recibe el conflicto, no un 500.
12. **Fuente no 1:1:** Tebeosfera devuelve `kind = "saga"`; se rechaza antes de firmar el token y no
    se asocia.
13. **Id exacto:** se pega un id válido y se asocia con una sola petición; un id inválido no produce
    candidata ni token.
14. **Fuente apagada o rate limit:** el estado se clasifica con el clasificador de #133; no se
    confunde con «no existe» ni se reintenta en bucle.

---

## 12. IGUALAR / MEJORAR

### IGUALAR (mínimo competitivo)

- Un id por fuente, varias fuentes por serie, con el id vigente en columna y `UNIQUE` en base.
- Rechazo claro cuando el id ya existe, sin reasignarlo en el alta.
- Búsqueda por título **y** por id exacto, con una sola petición por acción y sin paginar.
- Asociar no mueve ni escribe archivos ni aplica metadatos (#109, punto 7).
- La ficha sigue sin pintar ids (#127), pero la procedencia debe decir que la asociación consta.

### MEJORAR (con evidencia de la debilidad)

| Mejora | Debilidad de la referencia | Criterio comprobable |
|---|---|---|
| **Procedencia por asociación** | Sonarr/Radarr no tienen campo; sobrescriben en cada refresco. | Tras asociar y refrescar, la entrada de procedencia sigue y el id confirmado no cambia. |
| **Conflicto sin reasignación** | Sonarr/Radarr reasignan el id canónico en el refresco si la fuente fusiona, sin comprobar colisión local. | Un id que ya pertenece a otra serie no se mueve; la operación se rechaza y se explica. |
| **Corrección con historial** | Borrar + reañadir; migraciones que purgan filas. | Retirar deja historial y no borra la serie; sustituir son dos operaciones. |
| **Idempotencia por token** | Reañadir = error; refresco = última escritura; sin comprobante. | Repetir el token devuelve el mismo resultado sin duplicar. |
| **Sin dedupe silencioso** | Sonarr omite duplicados con log; Kapowarr reutiliza el volumen y mueve archivos. | La importación devuelve `repetida`/`conflicto` explícito, no silencio. |
| **Cardinalidad validada** | Sonarr admite varios MAL/AniList; Kapowarr no distingue sagas. | Una ficha que no es 1:1 se rechaza antes de asociar. |

---

## 13. Matriz ponderada (nivel 2)

Criterios y pesos por defecto del procedimiento (suman 100): encaje con el flujo del Coleccionista
25 · coste en Pi 20 · seguridad, legalidad y licencia 20 · cobertura del requisito core 15 ·
adaptabilidad al stack y al modelo de datos 10 · mantenimiento de la referencia 5 · lock-in y coste
de salida 5. **No se han movido pesos.** Puntuación de juicio (1-5), no medición; se muestra para
que el PO pueda discutirla.

Opciones para guardar la asociación:

- **A. Columna por fuente + procedencia en JSONB** (lo que propone la especificación).
- **B. Solo JSONB** (`metadata.asociaciones` como única verdad).
- **C. Tabla `series_fuentes`** con `UNIQUE (series_id, fuente)` y `UNIQUE (fuente, id_externo)`.
- **D. Statu quo**: no asociar; solo la fuente del enricher.

| Criterio (peso) | A | B | C | D |
|---|---:|---:|---:|---:|
| Encaje con el Coleccionista (25) | 5 | 4 | 4 | 1 |
| Coste en Pi (20) | 4 | 5 | 3 | 5 |
| Seguridad, legalidad y licencia (20) | 5 | 3 | 5 | 5 |
| Cobertura del requisito core (15) | 5 | 3 | 5 | 1 |
| Adaptabilidad al stack y modelo (10) | 5 | 5 | 4 | 5 |
| Mantenimiento (5) | 4 | 3 | 3 | 5 |
| Lock-in y coste de salida (5) | 5 | 4 | 3 | 5 |
| **Total ponderado (0-100)** | **95** | **78** | **81** | **68** |

**Lectura.** A gana porque mantiene la garantía de la columna y añade la procedencia sin migración
ni join; su coste es el doble escritura (columna + JSONB) en la misma transacción, que ya es el
patrón de `alta_serie` y `desvinculacion`. C es la alternativa más fuerte en cobertura y seguridad, pero exige
migración, índice compuesto, joins en el enricher y una tabla más que mantener, sin evidencia de que
haga falta (§2.3). B es atractiva por coste, pero pierde la unicidad de base y obliga a índices de
expresión o a confiar solo en el servicio; no compensa. D no cubre el requisito.

La puntuación no decide: la decisión es del PO. Si el PO elige C, hace falta ADR y migración; si
elige A, no hay migración.

---

## 14. NOT RUN, `[sin verificar]` y cómo verificarlo

### NOT RUN

1. **Aplicación y pruebas:** no se arrancó ZascArr, no se ejecutó pytest, no se abrió el navegador.
2. **Base de datos:** no se consultó la instalación; el recuento de series con varios ids (§2.3) está
   pendiente.
3. **Fuentes reales:** no se llamó a TVDB, TMDb, Comic Vine, GCD ni Tebeosfera; no se comprobó qué
   devuelven hoy ni si una ficha es `collection`/`saga`.
4. **Pi:** no se midió RAM, latencia ni coste de la operación.
5. **Referencias en marcha:** no se instaló Sonarr/Radarr/Kapowarr/Mylar3; su comportamiento se
   afirma por código, migraciones y pruebas leídas, no por ejecución.
6. **Decisión del PO** sobre D1-D5 y sobre el orden de las entregas B y C.

### `[sin verificar]`

| Afirmación | Por qué no se verificó | Cómo verificarlo |
|---|---|---|
| Sonarr/Radarr reasignan el id canónico cuando la fuente fusiona duplicados | Se leyó el código y la prueba, no se ejecutó | Leer `RefreshSeriesService.cs:86-89` + `RefreshSeriesServiceFixture.cs:191-204`; opcionalmente, montar un caso con Skyhook simulado. |
| La frecuencia real de fusiones de TVDB/TMDb | No se consultaron las fuentes | Historial de cambios de TVDB/TMDb o Issues de Sonarr/Radarr; no se ha medido. |
| Kapowarr puede duplicar un volumen en dos altas concurrentes | Se deduce de la ausencia de `UNIQUE`; no se probó la carrera | Leer `db.py:387-407`; prueba de integración con dos transacciones concurrentes. |
| Sonarr usa `MalIds`/`AniListIds` en la UI o solo como metadata | No se revisó toda la UI de anime | Buscar `MalIds`/`AniListIds` en `frontend/src`; comprobar la ficha de serie. |
| Mylar3 no tiene editor de `ComicID` | No se revisó toda la UI de Mylar3 | Abrir «Edit Comic» en Mylar3 o buscar `ComicID` en las plantillas. |
| Tebeosfera devuelve `kind` de forma fiable | Es un delta de la especificación, no se consultó la fuente | Una consulta real a Tebeosfera y revisar `collection`/`saga`; ya marcado en la spec. |

---

## 15. Decisión final y ADR

**No hace falta ADR para la opción A.** Confirma decisiones ya vigentes: columnas paralelas por
fuente (CLAUDE.md §12), JSONB para metadata suelta y token/comprobante para operaciones (#128/#303).
No añade dependencia, tabla ni migración.

**Sí haría falta ADR** si el PO elige la opción C (tabla `series_fuentes`), si decide admitir varios
ids por fuente (como Sonarr con MAL/AniList), o si cambia la unidad de asociación (edición/obra). En
esos casos, la decisión es arquitectónica y duradera, no un detalle de implementación.

**Recomendación:** A + R1-R5, con la entrega B (persistir) y el corte C (retirar) en el mismo
release (sin corrección, la asociación equivocada es permanente). El PO decide D1-D5; esta ficha
solo argumenta.

---

## 16. Referencias (URLs y commits)

- Sonarr, `develop` en `c018578e4b79ee048575c02d7a8aa2b929e4b837`:
  <https://github.com/Sonarr/Sonarr/tree/c018578e4b79ee048575c02d7a8aa2b929e4b837>
  - `Series`: <https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/NzbDrone.Core/Tv/Series.cs>
  - `RefreshSeriesService`: <https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/NzbDrone.Core/Tv/RefreshSeriesService.cs>
  - `SeriesExistsValidator`: <https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/NzbDrone.Core/Validation/Paths/SeriesExistsValidator.cs>
  - Migración 217 (MAL/AniList): <https://github.com/Sonarr/Sonarr/blob/c018578e4b79ee048575c02d7a8aa2b929e4b837/src/NzbDrone.Core/Datastore/Migration/217_add_mal_and_anilist_ids.cs>
- Radarr, `develop` en `7e3f80c98d01481430ab356f6d7322fc5dc381ee`:
  <https://github.com/Radarr/Radarr/tree/7e3f80c98d01481430ab356f6d7322fc5dc381ee>
  - `MovieMetadata`: <https://github.com/Radarr/Radarr/blob/7e3f80c98d01481430ab356f6d7322fc5dc381ee/src/NzbDrone.Core/Movies/MovieMetadata.cs>
  - `MovieMetadataRepository`: <https://github.com/Radarr/Radarr/blob/7e3f80c98d01481430ab356f6d7322fc5dc381ee/src/NzbDrone.Core/Movies/MovieMetadataRepository.cs>
  - Migración 207 (MovieMetadata): <https://github.com/Radarr/Radarr/blob/7e3f80c98d01481430ab356f6d7322fc5dc381ee/src/NzbDrone.Core/Datastore/Migration/207_movie_metadata.cs>
- Kapowarr, `V1.3.2` en `c191dda6617929c81292483a8cc07f631111dae2`:
  <https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2>
  - `volumes.py`: <https://github.com/Casvt/Kapowarr/blob/c191dda6617929c81292483a8cc07f631111dae2/backend/implementations/volumes.py>
  - `library_import.py`: <https://github.com/Casvt/Kapowarr/blob/c191dda6617929c81292483a8cc07f631111dae2/backend/features/library_import.py>
  - `db.py`: <https://github.com/Casvt/Kapowarr/blob/c191dda6617929c81292483a8cc07f631111dae2/backend/internals/db.py>
- Mylar3, `v0.8.3` en `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316`:
  <https://github.com/mylar3/mylar3/tree/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316>

---

## 17. Caducidad y mantenimiento

Esta ficha caduca el **2027-01-08** (~60 días) o antes si:

- cambia #129, D1-D5 o la especificación hermana;
- cambia una referencia (nuevo commit en Sonarr/Radarr/Kapowarr/Mylar3) en los ficheros citados;
- el PO decide la opción C (tabla) o varios ids por fuente;
- se mide el recuento de series con varios ids y contradice el supuesto de D2.

Al caducar, se rehacen las citas sobre el SHA vigente de ZascArr y se actualiza la tabla de
referencias. Lo no ejecutado sigue siendo NOT RUN hasta que se ejecute.
