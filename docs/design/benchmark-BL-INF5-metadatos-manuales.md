# Benchmark — Editar metadatos a mano de serie y números — BL-INF5 (#591)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Nivel **2**: toca modelo
> (JSONB de procedencia), comportamiento duradero del enriquecido y una regla de precedencia que
> no conviene revertir después. No hay migración.
>
> **Fecha:** 2026-11-10. **Base contrastada:** `origin/main` = `d26d815` (2026-11-10).
> **Caduca:** 2027-01-09 (~60 días, o antes si cambia una referencia o la historia).
> **Estado:** insumo para la especificación; **no aprueba** ni implementa. Decide el PO.

**Resumen para quien coordina:**

- ZascArr ya tiene el candado por campo (`locked_fields` en `series` e `issues`, H3) y una tabla de
  procedencia de solo lectura, pero **no hay ninguna pantalla que escriba metadatos descriptivos**:
  hoy solo se editan por alta, por ComicInfo (#448) o por el enriquecido.
- **Komga y Kavita** son las referencias útiles: candado booleano por campo y edición manual que
  activa el candado. **Mylar3** aporta el patrón de «valor de la fuente + valor manual en paralelo»
  y validación de fecha; **Sonarr/Radarr no resuelven el problema** (su refresco pisa los metadatos
  sin candado) y **Kapowarr tampoco lo ofrece** (solo monitorización y tipo de edición).
- La recomendación es **adaptar** el candado por campo que ya existe, **mejorar** con procedencia
  por campo fechada en `metadata_["manual"][campo]` (ninguna referencia guarda *cuándo* lo editó la
  persona), y **construir sobre lo propio** para colisión, huecos y `sort_order`. **Descartar** el
  modelo de columnas espejo de Mylar3 (exigiría migración), el diálogo modal/SPA y la escritura de
  ComicInfo (fuera: #480/B6).
- No se copia código. Komga es **MIT**; Kavita, Mylar3, Sonarr, Radarr y Kapowarr son **GPL-3.0**
  (compatibles con la GPL-3.0 de ZascArr, pero cada fichero exige revisar sus avisos).

**Referencias consultadas** (lectura estática del código en estos commits; **no se ejecutó** ninguna
aplicación salvo `git clone` para inspeccionar; ver NOT RUN):

| Referencia | Repo | Commit | Fecha | Referencia de versión | Licencia |
|---|---|---|---|---|---|
| Sonarr | `Sonarr/Sonarr` | `c018578e4b79ee048575c02d7a8aa2b929e4b837` | 2026-11-03 | `main`; último release publicado v4.0.20.3014 | GPL-3.0 (`LICENSE.md`) |
| Radarr | `Radarr/Radarr` | `7e3f80c98d01481430ab356f6d7322fc5dc381ee` | 2026-11-07 | `master`; último release publicado v6.4.4.10685 | GPL-3.0 (`LICENSE`) |
| Komga | `gotson/komga` | `6e161b6c8b1a4bacc68c9050a1ee0da6bd0707d6` | 2026-11-10 | `master`; release 1.30.1 del mismo día | **MIT** (`LICENSE`) |
| Kavita | `Kareadita/Kavita` | `f059e277e934644667dec6843d595bbb5f4b67f8` | 2026-11-10 | `develop` (commit de release 0.9.1.21; último release estable v0.9.1.4) | GPL-3.0 (`LICENSE`) |
| Mylar3 | `mylar3/mylar3` | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` | 2025-08-17 | `python3-dev` (sin release reciente verificada) | GPL-3.0 (`LICENSE`) |
| Kapowarr | `Casvt/Kapowarr` | `c191dda6617929c81292483a8cc07f631111dae2` | 2026-09-14 | v1.3.2 (el commit fija la versión) | GPL-3.0 (`LICENSE`) |

> **Corrección de premisa:** la tarjeta de la historia no afirmaba licencias; la ficha previa de
> BL-INF2 ya corrigió que Komga no es GPL sino MIT. Se mantiene: MIT es compatible con GPL-3.0,
> pero **copiar un fichero de Komga a ZascArr sigue obligando a conservar su aviso y su licencia**.

---

## 1. Problema local, caso real y resultado deseado

### 1.1 Qué hace hoy ZascArr (código vigente en `d26d815`)

- `src/zascarr/models/__init__.py:382-454` (`Series`) y `:475-515` (`Issue`): los campos
  descriptivos ya existen (`title`, `start_year`, `end_year`, `publisher_id`, `description`,
  `total_issues`; y `issue_number`, `title`, `release_date`, `format`, `synopsis`). También existen
  `metadata_ JSONB`, `metadata_source` y `locked_fields ARRAY(String)` en ambas entidades. **No
  hace falta migración.**
- La ficha de serie (`web/series.py::detalle`, `templates/series_detail.html:71-125`) y la de número
  (`web/series.py::detalle_numero`, `templates/issue_detail.html`) son **solo lectura**: no tienen
  formulario de edición ni ruta POST que escriba estos campos.
- La procedencia que se enseña es **de solo lectura y no campo a campo para todo**:
  `services/procedencia.py` reúne `metadata_["alta"]`, `metadata_source` y `locked_fields`; la
  plantilla añade «Editorial» y «Año de fin» con el texto fijo «Origen no registrado». No existe
  `metadata_["manual"]`.
- El enriquecido **sí respeta** `locked_fields` campo a campo (`services/enricher.py:301-312`,
  `:429-445`; `services/enriquecimiento_plan.py:179-245`) y la previsualización de «Revisar cambios
  de datos» ya muestra qué campos están protegidos. Pero como no hay forma de escribir un valor
  manual, el candado hoy solo lo activan el alta (`services/alta_serie.py:457`) y la vinculación
  manual de números (`services/review.py:300-307`).
- `services/comicinfo.py` (#448) ya escribe sinopsis, fecha, páginas, editorial y créditos desde el
  `ComicInfo.xml`, y **respeta `locked_fields`** y no pisa lo manual. **No escribe en el archivo.**
- Los huecos se calculan del DISCO y del formato (`services/series.py::numeros_poseidos`), no de
  `sort_order`; `sort_order` se lee como preferencia de orden pero **ningún código de `main` lo
  escribe** (documentado en `services/series.py:330-350` y en `tests/test_huecos_pg.py`).

**Comportamiento actual, en una frase:** si la fuente se equivoca, el coleccionista no puede
corregirlo desde ZascArr; o lo deja mal para siempre, o edita la base de datos.

### 1.2 Caso real que motiva la historia

Tebeoteca española con tres situaciones frecuentes:

1. **Serie mal identificada por la fuente:** el título que trae Comic Vine es el original en inglés,
   el año de inicio no es el de la edición española, la editorial es la estadounidense y la sinopsis
   está en otro idioma. El coleccionista quiere el título y la editorial que tiene en la estantería.
2. **Número mal numerado:** un tomo español se importó como «#1» pero en la serie es el «#12»; o un
   `Annual` que la fuente no conoce. Hoy el chip de la ficha miente y los huecos («te faltan») se
   calculan sobre el número equivocado.
3. **Hueco editorial:** la fuente no tiene sinopsis, o tiene un total de números que no corresponde
   a la edición española (por ejemplo, 12 tomos frente a 8).

**Resultado deseado:** una pantalla propia, sin JavaScript nuevo, donde escribir esos datos; al
guardar, **cada campo tocado queda marcado como manual, con su fecha, y protegido** para que el
enriquecido no lo revierta; el resto de la serie conserva su procedencia; la tabla «De dónde sale
cada dato» lo dice campo a campo y permite devolver el control a la fuente; **ningún archivo se
toca**. Si el número cambia, se recalcula el orden y los huecos.

### 1.3 Alcance y NO-goals

**Dentro:** editar campos de **serie** (título, año de inicio/fin, editorial, sinopsis, total de
números) y de **número** (número, título, fecha, formato, sinopsis); procedencia por campo
(`metadata_["manual"]` fechada); candado por defecto; desbloqueo sin borrar el valor; colisión
`(serie, número, volumen)` con aviso llano; recálculo de `sort_order` y de huecos; formularios
propios con la garantía «tus archivos no se tocan».

**Fuera (decidido por el PO):** crear números o series desde esta pantalla; escribir
`ComicInfo.xml` en el archivo (#480/B6); editar autores, créditos, géneros, etiquetas, portada,
IDs externos, `volume` o la tradición; edición en lote; historial/auditoría de cambios; deshacer
un guardado; renombrar carpetas o archivos al cambiar el título.

---

## 2. Matriz campo × referencia

Leyenda: **S** = serie/volumen; **N** = número/libro/capítulo; **—** = no aplica o no lo guarda;
«candado» = mecanismo por campo que impide que el refresco lo pise.

| Campo de ZascArr | Komga | Kavita | Mylar3 | Kapowarr | Sonarr/Radarr |
|---|---|---|---|---|---|
| `Series.title` | `title` + `titleLock` | `SeriesMetadata` no tiene título propio; el nombre se deriva de la carpeta / `Series.Name` | `ComicName`; sin edición libre (se cambia por «editar detalles»/match) | — (solo Comic Vine) | `Series.Title`/`Movie.Title` se editan por API, pero el refresco los sobrescribe |
| `Series.start_year` / `end_year` | `status`/`publisher`; no hay año de inicio/fin como tal | `ReleaseYear` + `ReleaseYearLocked` | `ComicYear` + `Corrected_SeriesYear` | — | `Year` (solo uno), sin candado |
| `Series.publisher_id` | `publisher` (texto) + `publisherLock` | `Publisher` como `Person` con rol + `PublisherLocked` | `ComicPublisher`; no editable a mano | — | `Network`/`Studio` (solo Radarr), sin candado |
| `Series.description` | `summary` + `summaryLock` | `Summary` + `SummaryLocked` | `Description` + `DescriptionEdit` | — | `Overview`, sin candado |
| `Series.total_issues` | `totalBookCount` + `totalBookCountLock` | `TotalCount`/`MaxCount` + `TotalCount` derivado (sin candado propio visible) | `Total` (de la fuente); no editable | — | `Statistics` (derivado) |
| `Issue.issue_number` | `number` + `numberLock` | `Number`/`MinNumber`/`MaxNumber` + `SortOrder`/`SortOrderLocked` | `Issue_Number`; el match se resuelve por fichero | — | `EpisodeNumber` (no editable como metadato) |
| `Issue.title` | `title` + `titleLock` | `TitleName` + `TitleNameLocked` | `IssueName`; sin edición libre | — | `EpisodeTitle`, sin candado |
| `Issue.release_date` | `releaseDate` + `releaseDateLock` | `ReleaseDate` + `ReleaseDateLocked` | `IssueDate`/`ReleaseDate` + `IssueDate_Edit` | — | `AirDate`, sin candado |
| `Issue.format` | tipo de libro por carpeta / `BookMetadata` no guarda «formato» | `Format` (special) en el parser; no candado específico | `Type`/`Corrected_Type` | `special_version` + `special_version_locked` | calidad de fichero, no formato editorial |
| `Issue.synopsis` | `summary` + `summaryLock` | `Summary` + `SummaryLocked` | solo visualización de la fuente; no edición libre | — | `Overview`, sin candado |
| Procedencia **por campo** | booleano por campo; **sin fecha** | booleano por campo; **sin fecha** | columnas `*Edit`/`Corrected_*`; **sin fecha** | — | — |
| Desbloqueo | icono de candado en el formulario | candado en el DTO/UI | borrar el valor manual (`DescriptionEdit = None`) | — | — |
| Colisión de número | no se ve comprobación en el código de metadatos; el libro se identifica por fichero | no se ve comprobación específica; el capítulo se identifica por fichero | sin comprobación al editar fecha; sí validación de fecha | — | — |

> No se infiere soporte por la UI: las celdas «—» salen de leer el código de refresco, el modelo y
> la ruta de escritura (apartados 3), no de que una pantalla no enseñe el campo.

---

## 3. Cómo lo resuelve cada referencia

### 3.1 Sonarr y Radarr (ciclo de refresco y estados)

**Qué hacen.** El refresco de metadatos es autoritativo: `RefreshSeriesService.RefreshSeriesInfo`
asigna `Title`, `Year`, `Overview`, etc. **sin consultar ningún candado**
(`src/NzbDrone.Core/Tv/RefreshSeriesService.cs:92-125`). Radarr hace lo mismo con
`movieMetadata.Title`, `Overview` y `Year`
(`src/NzbDrone.Core/Movies/RefreshMovieService.cs:106-125`). Los formularios de edición
(`frontend/src/Series/Edit/EditSeriesModalContent.tsx:202-335` y
`frontend/src/Movie/Edit/EditMovieModalContent.tsx:169-234`) solo ofrecen campos operativos:
monitorización, perfil de calidad, carpeta, pestaña de etiquetas y —en Radarr— disponibilidad
mínima. **No hay formulario de metadatos descriptivos y `Series.ApplyChanges`/`Movie.ApplyChanges`
solo copian campos operativos**, así que la corrección manual no existe como función de producto.

**Qué se aprende.** Su lección es negativa y útil: si el refresco manda y no hay candado, cualquier
edición manual sería efímera. ZascArr ya decidió lo contrario con `locked_fields` (H3); esta
historia debe **mantener el refresco como autoritativo para lo NO bloqueado y hacer del candado la
excepción explícita**. No se adopta su ausencia de edición. **Descartar** como referencia de UX y de
modelo; **adoptar** la regla «el refresco no pregunta, salvo que el campo esté protegido».

### 3.2 Komga (edición manual con candado por campo)

**Modelo.** `SeriesMetadata` guarda un booleano por campo: `statusLock`, `titleLock`,
`titleSortLock`, `summaryLock`, `publisherLock`, `totalBookCountLock`, etc.
(`komga/src/main/kotlin/org/gotson/komga/domain/model/SeriesMetadata.kt:21-33`). `BookMetadata`
hace lo mismo y separa **`number`** de **`numberSort` (Float)**, con `numberLock` y `numberSortLock`
(`BookMetadata.kt:19-33`).

**Precedencia.** `MetadataApplier.getIfNotLocked` aplica el parche solo si el candado está apagado
(`MetadataApplier.kt:11-32`). Es la misma idea que `locked_fields` de ZascArr, pero con columnas
booleanas por campo en lugar de un `ARRAY` de nombres.

**Edición manual.** La API expone `PATCH /api/v1/series/{id}/metadata` y
`PATCH /api/v1/books/{id}/metadata`; el DTO distingue «campo omitido» de «campo a null» mediante
`isSet(...)` para poder borrar un valor (`SeriesController.kt:672-740`, `BookController.kt:650-670`).
En la UI, el diálogo de edición pinta un icono de candado por campo y **al cambiar el valor activa
el candado** (`@change="form.titleLock = true"`, `komga-webui/src/components/dialogs/EditSeriesDialog.vue:66-72`;
para número y orden, `EditBooksDialog.vue:78-116`). El campo «Sort Number» tiene ayuda explícita
«You can use decimal numbers» (`locales/en.json:430-432`).

**Qué se aprende.** Es la referencia más cercana a la decisión del PO: **candado por campo, activado
al editar, y visible en el propio formulario**. Se **adapta** a HTMX sin JS: en vez de un icono que
alterna, el candado se activa al guardar un valor cambiado y se gestiona con dos acciones de
servidor («devolver a la fuente» / «proteger»). Se **mejora** añadiendo la fecha del cambio manual:
Komga solo guarda el booleano.

### 3.3 Kavita (candado por campo en serie y capítulo)

**Modelo.** `SeriesMetadata` tiene candados por campo (`SummaryLocked`, `ReleaseYearLocked`,
`GenresLocked`, `TagsLocked`, roles de persona, etc.;
`Kavita.Models/Entities/Metadata/SeriesMetadata.cs:54-78`). `Chapter` tiene los suyos, incluido
`SortOrderLocked` («Can the sort order be updated on scan or is it locked from UI»,
`Kavita.Models/Entities/Chapter.cs:40` y `:152-172`).

**Edición manual.** `SeriesService.UpdateSeriesMetadata` **activa el candado automáticamente** al
detectar que cambió el valor (`SeriesService.cs:102-230`; p. ej. `ReleaseYearLocked = true` en
`:115-118`, `SummaryLocked = true` en `:136-138`). En el capítulo, `ChapterController.UpdateChapterMetadata`
toma los candados del DTO (`ChapterController.cs:191-260` y `:380-399`) y actualiza título, sinopsis,
fecha y orden; el `SortOrder` se acepta con un `// TODO: Figure out validation`
(`ChapterController.cs:220-223`).

**Precedencia.** El escaneo aplica el `ComicInfo.xml` solo si el campo no está bloqueado:
`UpdateChapterFromComicInfo` comprueba `TitleNameLocked`, `SummaryLocked`, `ReleaseDateLocked`,
roles, géneros y etiquetas (`Kavita.Services/Scanner/ProcessSeries.cs:1193-1283`).

**Qué se aprende.** Confirma dos ideas: (a) **el candado se activa con la edición**, no en una
pantalla aparte; (b) el candado debe cubrir también el **orden** (`SortOrderLocked`), porque el
escaneo puede reordenar. Se **adopta** el candado automático al guardar y se **adapta** el orden a
`Issue.sort_order` de ZascArr. Se **descartan** sus diálogos SPA y la validación pendiente del
orden: aquí la validación de número y fecha es requisito.

### 3.4 Mylar3 (valor de la fuente + valor manual en paralelo)

**Modelo.** La tabla `comics` tiene columnas paralelas para el valor manual: `DescriptionEdit`
junto a `Description`, `Corrected_SeriesYear` junto a `ComicYear`, `Corrected_Type` junto a
`Type`; `issues` tiene `IssueDate_Edit` junto a `IssueDate`
(`mylar/__init__.py:805-806`). La lectura prefiere el valor manual y el importer/updater lo
**preserva al refrescar** (`mylar/importer.py:145` y `:525`; `mylar/updater.py:327-341`).

**Edición manual y validación.** `description_edit` guarda en `DescriptionEdit` y, si se vacía,
vuelve a `None` para que el refresco recupere la descripción de la fuente
(`mylar/webserve.py:2092-2116`). `issue_edit` valida que la fecha sea `YYYY-MM-DD`, rechaza una
fecha mal formada y **rechaza un año anterior al de la serie**; guarda el valor anterior y el tipo
en `IssueDate_Edit` (`mylar/webserve.py:2115-2165`). `comic_config` permite corregir el año de serie
(`Corrected_SeriesYear`), el tipo y el alias de búsqueda (`mylar/webserve.py:7048-7115`). No hay un
formulario general de «todos los campos»: la edición es por campos concretos y con JS/AJAX.

**Qué se aprende.** Su patrón de **valor manual separado del valor de la fuente** es el mismo
problema que resuelve `metadata_["manual"]`, pero con **columnas nuevas** (coste de migración y de
mantener dos esquemas). Se **adapta** la idea al JSONB que ya existe: el valor vive en su columna
normal (una sola verdad para la ficha) y el JSONB guarda **quién manda y desde cuándo**. Se
**adopta** su validación de fecha (formato y coherencia con el año de la serie) y su gesto de
«vaciar para devolver a la fuente», aunque en ZascArr se separa en una acción explícita
«Devolver a la fuente» que **no borra el valor** (AC-2). Se **descartan** las columnas espejo
(prohibido migrar en esta historia) y la edición por AJAX (sin JS).

### 3.5 Kapowarr (lo que no cubre)

Kapowarr toma los metadatos de Comic Vine y **no permite editarlos a mano**: la edición pública de
un volumen acepta solo `monitored`, `monitor_new_issues`, `special_version` y
`special_version_locked` (`backend/implementations/volumes.py:535-541`; los issues solo
`monitored`, `:179`), y la documentación «Editing a volume» describe únicamente carpeta raíz,
monitorización y tipo de edición (`docs/src/general_info/how_to_use.md:30-54`). El refresco
`refresh_and_scan` vuelve a traer los datos de la fuente (`volumes.py:1356-1420`). La petición de
edición manual de series e issues existe en su tracker y se cerró como duplicada
([issue #228](https://github.com/Casvt/Kapowarr/issues/228), 2025-01-21).

**Qué se aprende.** Confirma que el problema es real y que la referencia **no lo resuelve**;
**descartar** como fuente de patrón de edición. Su `special_version_locked` es el único candado y
protege el tipo de edición, no los metadatos descriptivos; no se adopta para este alcance.

---

## 4. Supuestos de la referencia que NO valen en ZascArr

1. **SPA, modal y build de Node.** Komga (Vue), Kavita (Angular) y Sonarr/Radarr (React) editan en
   diálogos con JS. ZascArr es Jinja2 + HTMX 4 vendorizado, sin build ni JS nuevo (ADR-0001). La
   edición será **una página con formulario POST normal**, no un modal.
2. **API primero, cliente después.** Komga/Kavita resuelven la edición por `PATCH`/`POST` JSON. En
   ZascArr el contrato es el formulario HTML (`Form(...)` explícitos, sin mass assignment); no se
   añade una API pública para esto.
3. **Unidad editorial distinta.** Sonarr/Radarr usan episodios/películas y Komga/Kavita
   libro/capítulo; ZascArr tiene **grapa/tomo** con `issue_number VARCHAR` y `volume`, y una
   edición española puede cambiar el número respecto a la fuente. La colisión y los huecos se
   piensan con esa unidad.
4. **Sin candado o candado único.** Sonarr/Radarr no tienen candado descriptivo; Kapowarr solo
   protege el tipo. ZascArr ya tiene `locked_fields` por campo y lo respeta el enriquecido; no se
   importa un modelo nuevo.
5. **Sin migración.** Mylar3 necesita columnas espejo; aquí **no se toca el esquema**. `metadata_`
   JSONB y `locked_fields` ya existen.
6. **Raspberry Pi 4/5 compartida (512 MiB).** Nada de workers, colas ni tareas de fondo para
   guardar; una transacción corta y dos o tres consultas. Nada de JS ni dependencias nuevas.
7. **Conservación de archivos.** Ninguna referencia garantiza «no se toca el archivo» en su flujo
   de metadatos: Mylar3 reescribe `ComicInfo` al etiquetar; Komga/Kavita leen del archivo. ZascArr
   escribe solo en PostgreSQL; la garantía es parte del contrato de UX.
8. **Fuentes españolas.** Comic Vine/AniList no cubren bien Tebeosfera/GCD; la edición manual es
   precisamente la válvula de escape. La procedencia no puede mentir atribuyendo a una fuente un
   valor escrito a mano.

---

## 5. Resultado por idea

| # | Idea | Resultado | Motivo |
|---|---|---|---|
| I1 | Candado booleano por campo que impide que el refresco pise el valor | **Adaptar** | ZascArr ya tiene `locked_fields ARRAY(String)` (H3) en `Series` e `Issue`, y el enriquecido lo respeta; no se añaden columnas. Se reutiliza el mecanismo, no se copia código. |
| I2 | Activar el candado automáticamente al guardar un campo cambiado | **Adoptar** | Komga (`@change=...Lock=true`) y Kavita (`SeriesService.cs:115-138`) lo hacen; coincide con «bloqueado por defecto» del PO. |
| I3 | Mostrar y alternar el candado en el propio formulario | **Adaptar** | En Komga es un icono; en ZascArr sin JS será una casilla/acción explicada en llano. Se separa el cambio de valor del cambio de protección para no sorprender. |
| I4 | Devolver el control a la fuente sin borrar el valor | **Mejorar** | Mylar3 borra el override al vaciar; Komga/Kavita solo quitan el candado (el valor queda). ZascArr puede hacerlo explícito, conservar el valor y **mantener la fecha de procedencia manual** para no atribuirlo en falso a una fuente. |
| I5 | Procedencia **por campo con fecha** (`metadata_["manual"][campo]`) | **Mejorar** | Ninguna referencia guarda la fecha: Komga/Kavita solo booleanos; Mylar3 solo el valor anterior en `IssueDate_Edit`. ZascArr puede añadir `{"fecha": ISO-8601}` en el JSONB sin migración y enseñarlo en la tabla. |
| I6 | No cambiar `metadata_source` de toda la serie al editar un campo | **Construir sobre lo propio** | `metadata_source` describe la fuente global y ya se usa en el enriquecido y en la procedencia; convertirlo a `manual` apagaría el enriquecido de toda la serie. El precedente es `metadata_["alta"]` (procedencia por operación) y `comicinfo_aplicado.aplicado` (por campo). |
| I7 | Colisión `(serie, número, volumen)` explicada en llano | **Construir sobre lo propio** | La restricción `UNIQUE (series_id, issue_number, volume)` ya existe (`models/__init__.py:477`); hoy un choque sería un `IntegrityError` crudo. Se añade comprobación previa y traducción del error. Ninguna referencia de cómic lo resuelve de forma reutilizable. |
| I8 | Recalcular `sort_order` al cambiar el número | **Adaptar** | Komga separa `number` de `numberSort` (Float); Kavita tiene `SortOrder` + `SortOrderLocked`. ZascArr ya tiene `Issue.sort_order FLOAT` y orden natural de reserva; se escribe solo cuando el número cambia y es numérico, dejando `NULL` para «Annual 1», que el orden natural ya resuelve. |
| I9 | Huecos y «te faltan» se recalculan sin acción extra | **Construir sobre lo propio** | `numeros_poseidos` ya sale del disco y del formato; cambiar número/formato/total en la misma transacción basta. Las referencias calculan totales de otra forma (Komga `totalBookCount`, Kavita `TotalCount`); no se importa. |
| I10 | Validación de fecha (formato y coherencia) | **Adoptar** | Mylar3 valida `YYYY-MM-DD` y rechaza año anterior al de la serie (`webserve.py:2140-2160`). ZascArr añade rango 1800-2100, ya usado en `tokens_revision.ANIO_MIN/MAX`. |
| I11 | Edición en lote | **Descartar** | Komga la tiene (`PATCH /books/metadata` en lote); no está en el alcance del PO y multiplica el riesgo de colisión. |
| I12 | Diálogo modal / SPA / iconos de candado con JS | **Descartar** | ADR-0001 y el contrato «sin JS nuevo»; además htmx 4 intercambia cuerpos 4xx (recogido en `docs/design/ui-migracion.md`), así que los errores de validación deben ser **navegación normal**, no fragmentos htmx. |
| I13 | Escribir `ComicInfo.xml` al guardar | **Descartar** | Fuera de alcance (#480/B6) y rompería la garantía «tus archivos no se tocan». |
| I14 | Historial/auditoría de ediciones | **Descartar (por ahora)** | Ninguna referencia lo ofrece; el PO no lo pidió. La fecha por campo es el mínimo honesto. Si se pide, el JSONB ya tiene sitio. |
| I15 | Refresco autoritativo salvo candado | **Adoptar** | Komga (`MetadataApplier`) y Kavita (`ProcessSeries`) lo hacen así; ZascArr ya lo implementa en el enriquecido. La historia no cambia esa dirección. |
| I16 | Columnas espejo por campo (Mylar3) | **Descartar** | Exigiría migración y duplicar la verdad; el JSONB de ZascArr cubre el caso sin esquema nuevo. |

---

## 6. Invariantes de ZascArr que la historia NO puede romper

- **No mentir en la procedencia.** Un valor escrito a mano nunca se atribuye a una fuente; si se
  desbloquea, sigue constando como manual (o como «origen no registrado» si se borra la marca), no
  como «enriquecido desde X».
- **No borrar ni mover archivos.** La historia solo escribe `series`, `issues` y `publishers`; ni
  `files`, ni disco, ni `ComicInfo`.
- **No romper instalaciones.** Sin migración; las filas existentes con `metadata_` antiguo o
  `locked_fields` con nombres no gestionados se leen con tolerancia.
- **Un solo proceso, 512 MiB.** Guardar es una transacción corta; sin tareas de fondo, sin red.
- **El coleccionista decide.** Los errores se explican con causa y acción; nada de 422/JSON crudo.
- **El refresco sigue siendo autoritativo fuera del candado.** No se convierte toda la serie en
  manual; solo los campos que el coleccionista protege.
- **Español llano, sin jerga.** «Protegido», «Manual», «Devolver a la fuente»; nada de
  `locked_fields` ni `metadata_source` en superficie.

---

## 7. Casos de prueba antes de implementar (semilla de la especificación)

1. **PG real:** guardar `title`, `start_year`, `end_year`, `description`, `total_issues` y editorial
   de una serie; comprobar valores, `metadata_["manual"][campo]["fecha"]`, `locked_fields` y que
   `metadata_source` y `metadata_["alta"]` no cambian.
2. **PG real:** guardar `issue_number`, `title`, `release_date`, `format` y `synopsis` de un número;
   comprobar lo mismo y que `metadata_["comicinfo_aplicado"]` sobrevive.
3. **PG real:** desbloquear un campo; el valor **sigue ahí**, el candado desaparece y la marca
   manual (con fecha) se conserva; volver a proteger funciona.
4. **PG real:** un campo no cambiado no se marca manual; un campo vacío opcional no crea marca.
5. **PG real:** colisión exacta y por ceros a la izquierda (`3` frente a `03`); no se escribe nada y
   el mensaje es llano. El `UNIQUE` sigue siendo la última defensa.
6. **PG real:** `sort_order` pasa a `2.0` / `2.5` / `NULL` según el número; «Annual 1» queda `NULL`
   y el orden natural lo coloca.
7. **PG real:** cambiar número, formato o `total_issues` cambia `numeros_poseidos`/`faltantes` en la
   misma transacción (sin escritura extra).
8. **PG real:** editorial por nombre; reutiliza una existente sin distinguir mayúsculas y crea una
   nueva con `metadata_source='manual'` si no existe; vaciar el campo la quita de la serie.
9. **PG real:** JSONB asignado como dict nuevo (mutarlo in situ no se persiste); recargar la fila y
   verlo.
10. **Web (FakeSession):** GET de los dos formularios con valores precargados, garantía junto al
    botón y sin `<script>` ni `hx-confirm`; 404 si el número no es de la serie.
11. **Web (FakeSession):** POST correcto → 303 y aviso verde al volver; POST con error → 200, mismo
    formulario, valores conservados y mensaje llano, nunca 422 crudo.
12. **Web (FakeSession):** la ficha enseña «Manual» con fecha y la acción «Devolver a la fuente»;
    el número también.
13. **Regresión:** el enriquecido no sobrescribe un campo manual bloqueado y sí puede proponer
    cambios en los no bloqueados; el ComicInfo (#448) respeta el candado como hoy.

> Estos casos se **escriben** en la especificación con nombres de fichero y con el patrón de la
> suite (`TEST_DATABASE_URL` + `tests/_pg.py`, FakeSession web). **No se ejecutan en esta tarea**
> (solo documentación): ver NOT RUN.

---

## 8. Matriz ponderada (nivel 2)

Criterios y pesos por defecto de `benchmark-referencias.md` (suman 100): encaje con el flujo del
Coleccionista 25 · coste en Pi 20 · seguridad, legalidad y licencia 20 · cobertura del requisito
core 15 · adaptabilidad al stack y al modelo de datos 10 · mantenimiento de la referencia 5 ·
lock-in y coste de salida 5. No se mueven pesos; se puntúa de 1 a 5.

Alternativas de **modelo de procedencia** (la decisión de producto de esta historia):

- **A.** Un solo `metadata_source="manual"` para toda la entidad (lo que ya hay para el alta).
- **B.** Candado booleano por campo, sin fecha (Komga/Kavita).
- **C.** Columnas espejo por campo (Mylar3).
- **D.** Candado por campo + `metadata_["manual"]` fechado en el JSONB existente (propuesta).

| Criterio (peso) | A | B | C | D |
|---|---:|---:|---:|---:|
| Encaje con el Coleccionista (25) | 2 | 4 | 2 | 5 |
| Coste en Pi (20) | 5 | 5 | 2 | 4 |
| Seguridad, legalidad y licencia (20) | 4 | 4 | 4 | 5 |
| Cobertura del requisito core (15) | 2 | 4 | 3 | 5 |
| Adaptabilidad al stack y modelo (10) | 4 | 5 | 2 | 5 |
| Mantenimiento de la referencia (5) | 3 | 4 | 3 | 4 |
| Lock-in y coste de salida (5) | 4 | 4 | 3 | 4 |
| **Total ponderado (sobre 5)** | **3,15** | **4,25** | **2,55** | **4,70** |

Lectura: **A** apagaría el enriquecido de toda la serie y no permite devolver un solo campo;
**C** exige migración y dos verdades; **B** es el mínimo competitivo y **D** lo iguala añadiendo la
fecha y el desbloqueo honesto sin coste de esquema. La ficha propone **D**; decide el PO.

---

## 9. IGUALAR / MEJORAR (con evidencia)

**IGUALAR (mínimo competitivo):**

- Candado por campo tras editar, con la misma semántica que Komga/Kavita (I1/I2). Evidencia:
  `MetadataApplier.kt:11-32`, `SeriesService.cs:115-138`.
- Edición manual de los campos que la ficha enseña, sin pedir al coleccionista que edite el archivo.
- Validación de fecha y de número; no aceptar valores imposibles.
- Desbloqueo visible y reversible.

**MEJORAR (hueco probado en las referencias):**

1. **Fecha de la edición manual.** Komga y Kavita solo guardan booleanos
   (`SeriesMetadata.kt:21-33`, `SeriesMetadata.cs:54-78`); Mylar3 guarda el valor anterior en
   `IssueDate_Edit` pero no una fecha legible (`webserve.py:2157-2165`). ZascArr añadirá
   `{"fecha": ...}` por campo, que es lo que pide «procedencia por campo» y lo que hace honesta la
   tabla.
2. **Desbloqueo que no borra ni miente.** Mylar3 vacía el override para devolver el control
   (`description_edit`), lo que pierde el valor; ZascArr conserva el valor y la marca manual y solo
   retira el candado, mostrando «sin proteger». Criterio comprobable: tras desbloquear, el valor
   sigue en la ficha y el enriquecido puede proponer un cambio.
3. **Colisión explicada.** Ninguna referencia de cómic la resuelve en la UI; ZascArr la convierte en
   «ya existe el nº 3 en esta serie» antes de tocar la base, con `UNIQUE` como red.
4. **Garantía de archivos.** Ninguna referencia la ofrece en su flujo de metadatos; ZascArr la pone
   junto al botón y en el aviso posterior, y la prueba comprueba que no se escribe ni `files` ni
   disco.

---

## 10. NOT RUN

- **No se ejecutó** Sonarr, Radarr, Komga, Kavita, Mylar3 ni Kapowarr. La lectura es estática del
  código en los commits de la tabla; no se abrió su UI ni se probó su edición en un navegador.
- **No se midió** el tiempo de guardado en la Pi ni el tamaño del JSONB resultante; el presupuesto
  de la especificación es estructural (2-3 consultas, sin red ni disco).
- **No se probó** el flujo real de ZascArr con Postgres ni con navegador: no hay formularios todavía.
- **No se auditó** la UI de Mylar3 completa (es un `webserve.py` de ~520 KB); se siguió la ruta de
  escritura de metadatos y sus overrides, no todas sus pantallas.
- **No se comprobó** si Komga/Kavita tienen alguna validación de número duplicado fuera del flujo
  de metadatos; se documenta como hueco no resuelto, no como ausencia probada.
- **No se reutilizó** código de ninguna referencia; solo se citan contratos y líneas.

---

## 11. Decisión final / ADR

No cambia la arquitectura: se usan `metadata_ JSONB` y `locked_fields` que ya existen, sin
migración. No procede ADR. Si en el futuro se decide guardar un historial de ediciones o una API
pública de metadatos, eso sí sería una decisión arquitectónica y merecería ADR.

---

## 12. Caducidad

2027-01-09 (~60 días), o antes si cambia `locked_fields`/`metadata_` en ZascArr o alguna de las
referencias mueve su modelo de candados.
