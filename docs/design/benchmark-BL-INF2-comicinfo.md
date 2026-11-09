# Benchmark — Guardar lo que traen mis CBZ (`ComicInfo.xml`) — BL-INF2 (#448)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Nivel **2**: toca modelo,
> ficheros y una decisión de precedencia que no conviene revertir después.
>
> **Fecha:** 2026-11-09. **Base contrastada:** `origin/main` = `ecc5234` (2026-11-09).
> **Caduca:** 2027-01-08 (~60 días, o antes si cambia alguna referencia o la historia).
> **Estado:** insumo para la especificación; **no aprueba** ni implementa. Decide el PO.

**Resumen para quien coordina:**

- ZascArr ya lee estos campos en el triaje y los tira tras usarlos para emparejar; ETQ2 solo guarda
  `<Tags>`/`<Genre>`.
- Kavita y Komga son las referencias útiles (campos, candados, autores); Mylar3 solo identifica y
  Kapowarr ignora el `ComicInfo.xml`; ComicTagger aporta el vocabulario de merge, pero no guarda
  `Translator`.
- La recomendación es **solo huecos + prueba de autoría + `locked_fields`**, con sinopsis/fecha/
  páginas/créditos en el número y editorial en la serie.
- No se copia código: Kavita, Mylar3 y Kapowarr son GPL-3.0; Komga es **MIT** (la premisa de la
  tarjeta no se sostiene) y ComicTagger es Apache-2.0.

**Referencias consultadas** (lectura estática del código en estos commits; no se ejecutó ninguna):

| Referencia | Repo | Commit | Fecha | Licencia |
|---|---|---|---|---|
| Kavita | `Kareadita/Kavita` | `6ae5d302d24696a2e212de83b69cb60b4604e9b3` | 2026-11-08 | GPL-3.0 (`LICENSE`) |
| Komga | `gotson/komga` | `609e98a1453dcde9b88e5a98f46c14bd70d16dad` | 2026-11-09 | **MIT** (`LICENSE`), no GPL |
| Mylar3 | `mylar3/mylar3` | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` | 2025-08-17 | GPL-3.0 (`LICENSE`) |
| Kapowarr | `Casvt/Kapowarr` | `c191dda6617929c81292483a8cc07f631111dae2` | 2026-09-14 | GPL-3.0 (`LICENSE`) |
| ComicTagger | `comictagger/comictagger` | `fa11a3456cbe5aa9f54f47bdc374ba26b2b946f3` | 2026-09-06 | Apache-2.0 (`LICENSE`) |

> **Corrección de premisa:** la tarjeta decía «Kavita y Komga son GPL». Kavita sí es GPL-3.0; Komga
> publica **MIT** en el commit contrastado. No cambia el veredicto, pero sí la barrera legal: MIT es
> compatible con GPL-3.0, aunque sigue prohibido copiar código sin revisar el fichero y sus avisos.

---

## 1. Problema local, caso real y resultado deseado

### 1.1 Qué hace hoy ZascArr (código vigente)

ZascArr **ya lee** el `ComicInfo.xml` en el triaje y lo usa para **emparejar**, pero no guarda sus
campos descriptivos:

- `core/importer_triage.py:115-126` mapea los ocho tags de crédito (`Writer`, `Penciller`, `Inker`,
  `Colorist`, `Letterer`, `CoverArtist`, `Editor`, `Translator`) a roles internos.
- `core/importer_triage.py:131-145` (`ComicInfo`) guarda `series`, `number`, `volume`, `year`,
  `publisher`, `summary`, `tags`, `genres`, `language_iso`, `page_count` y `credits`.
- `core/importer_triage.py:195-229` parsea el XML y separa los créditos por coma.
- `core/importer_triage.py:375-384` acota la entrada a `MAX_COMICINFO_BYTES` (1 MiB) antes de
  descomprimirla; un XML roto se avisa y se ignora, sin abortar el ciclo.
- `core/matcher.py:18-35` y `:200` usan `Series`/`Number`/`Volume` como señales de identidad.
- `services/importer.py:771` y `services/library_adopter.py:1035` marcan
  `File.metadata_source='comicinfo_xml'` cuando el ComicInfo identifica el archivo
  (`strong_candidate`). Eso describe **la identidad del fichero**, no la procedencia de cada campo.
- `services/importer.py:787-803` (`_aplicar_comicinfo`) ya vuelca `<Tags>` y `<Genre>` en la serie
  vía `services/etiquetas_comicinfo.py` (ETQ2, #538, fusionado el 2026-11-09 en `007aa91`).
- **Nada** escribe `Issue.synopsis`, `Issue.release_date`, `Issue.page_count`,
  `Series.publisher_id`, `Creator` ni `IssueCreator` a partir del ComicInfo.

**Medición de partida:** no se midió una biblioteca real en esta ficha; el argumento de coste es
estructural. El CBZ **ya se abre y se lee** en el triaje, así que BL-INF2 no añade una segunda
lectura ni descomprime páginas: el coste incremental son unas pocas consultas y filas por archivo.
El tope de 1 MiB y el corte de entidades ya están cubiertos por el código y sus pruebas actuales.

El modelo destino ya existe (`models/__init__.py`): `Series.publisher_id` (`:388`),
`Issue.release_date` (`:480`), `Issue.page_count` (`:485`), `Issue.synopsis` (`:487`),
`Creator` (`:329`) e `IssueCreator` (`:512`, PK `issue_id + creator_id + role`). `CreatorRole`
(`:45-54`) tiene los ocho papeles, con `penciler` a una sola L. `Series` e `Issue` tienen
`locked_fields` (`:431`, `:495`), y B6 ya definió la precedencia campo a campo en
`core/comicinfo_write.py:73-103` y el mapa de candados en `services/tagger.py:67-74`.

### 1.2 Caso real que motiva la historia

Un CBZ español comprado/escaneado trae, dentro del ZIP:

- `<Writer>Guionista Original</Writer>`, `<Penciller>Dibujante</Penciller>`,
  `<Editor>Editor de la edición española</Editor>`, `<Translator>Traductor</Translator>`;
- `<Summary>` con HTML (`<p>`, `<br>`, `<i>`), a veces muy largo;
- `<Year>2014</Year>` (sin mes ni día), `<Publisher>Editorial</Publisher>`,
  `<PageCount>48</PageCount>`.

Tras importarlo, ZascArr lo empareja bien, pero la ficha del número (BL-INF1) sigue diciendo
«No consta todavía» en sinopsis, fecha, páginas y autores. El coleccionista ya pagó el trabajo de
etiquetado; ZascArr lo está tirando a la basura después de usarlo para el match.

**Resultado deseado:** guardar esos campos en el mismo pase de triaje, sin abrir el archivo dos
veces, sin escribir en el CBZ, sin pisar lo manual y sin duplicar autores al reimportar.

### 1.3 Alcance y NO-goals

**Dentro:** `Summary`, `Year` (y, si se acepta, `Month`/`Day`), `Publisher`, `PageCount`, `Title`
(opcional), `Volume` (opcional) y los ocho créditos, con sus topes y su procedencia.

**Fuera de BL-INF2:** escribir `ComicInfo.xml` (B6/ETQ6), `<Tags>`/`<Genre>` (ya ETQ2),
`Characters`/`Teams`/`Locations` (ETQ3), `AgeRating`, `LanguageISO`, `StoryArc`/`SeriesGroup`,
`Web`/`Notes` como IDs externos, ISBN/GTIN, portadas y CBR. Tampoco se reescriben `Series.title` ni
`Issue.issue_number`: ya se usaron para emparejar y son identidad, no metadato descriptivo.

---

## 2. Matriz campo × proyecto

Leyenda: **S** = serie, **N** = número/book, **P** = persona/creador, **—** = no lo guarda.
«Identidad» = solo se usa para emparejar o buscar la ficha, no se persiste como metadato del
archivo.

### 2.1 Campos descriptivos

| Tag ComicInfo | Destino propuesto en ZascArr | Kavita | Komga | Mylar3 | Kapowarr | ComicTagger |
|---|---|---|---|---|---|---|
| `Series` | identidad; no reescribir | `S.name` (parser) | `S.title` | identidad | — | `series` |
| `Number` | identidad; no reescribir | `N.number` | `N.number` + `numberSort` | identidad | — | `issue` |
| `Volume` | `Issue.volume` (opcional, solo hueco) | `N.volume` | no se guarda; opción de añadirlo al título de serie | identidad | — | `volume` |
| `Title` | `Issue.title` (opcional) | `N.title` | `N.title` | lee, **no persiste** | — | `title` |
| `Summary` | `Issue.synopsis` | `N.summary`; `S.summary` del primer número | `N.summary` | solo visualización | — | `description` |
| `Year` | `Issue.release_date` (con precisión) | `N.releaseDate`; `S.releaseYear` mínimo | `N.releaseDate` | identidad/año para CV | — | `year`/`month`/`day` |
| `Publisher` | `Series.publisher_id` (entidad normalizada) | `P:Publisher` en N y S | `S.publisher` | no; lo trae de CV | — | `publisher` por archivo |
| `PageCount` | `Issue.page_count` (solo si un archivo) | **lee y no lo usa** | **lee y no lo usa** | solo visualización | — | `page_count` |
| `LanguageISO` | — (no se infiere) | `N.language`; `S.language` | `S.language` | — | — | `language` |
| `AgeRating` | — (fuera) | `N.ageRating`; `S.ageRating` máximo | `S.ageRating` | no (CV) | — | `maturity_rating` |
| `Genre` | `Series.genres` (ETQ2) | `N.genres`; `S.genres` | `S.genres` | — | — | `genres` |
| `Tags` | `Series.tags` (ETQ2) | `N.tags`; `S.tags` | `N.tags` | — | — | — (ComicRack no lee `<Tags>`) |
| `Characters`/`Teams`/`Locations` | — (fuera) | `P` con rol Character/Team/Location | `N.notableEntities` | — | — | `characters`/`teams`/`locations` |
| `Web`/`Notes` | — (fuera; IDs externos) | IDs externos en el parser | `N.links` | ID de CV | — | `web_links`/`notes` |
| `ISBN`/`GTIN` | — (fuera) | `N.ISBN` | `N.isbn` | — | — | — |
| `StoryArc`/`SeriesGroup` | — (fuera) | `N.storyArc`; `S` colecciones | read lists / colecciones | — | — | `story_arcs`/`series_groups` |

### 2.2 Créditos

| Tag ComicInfo | Rol ZascArr | Kavita | Komga | Mylar3 | Kapowarr | ComicTagger |
|---|---|---|---|---|---|---|
| `Writer` | `writer` | `P:Writer` | `Author(role="writer")` | solo visualización | — | `Writer` |
| `Penciller` | `penciler` (una L) | `P:Penciller` | `penciller` | solo visualización | — | `Penciller` |
| `Inker` | `inker` | `P:Inker` | `inker` | solo visualización | — | `Inker` |
| `Colorist` | `colorist` | `P:Colorist` | `colorist` | solo visualización | — | `Colorist` |
| `Letterer` | `letterer` | `P:Letterer` | `letterer` | solo visualización | — | `Letterer` |
| `CoverArtist` | `cover_artist` | `P:CoverArtist` | `cover` | solo visualización | — | `Cover` |
| `Editor` | `editor` | `P:Editor` | `editor` | solo visualización | — | `Editor` |
| `Translator` | `translator` | `P:Translator` | `translator` | **no lo lee** | — | **no lo escribe en ComicInfo** |

> **Dato importante para una edición española:** Kavita y Komga conservan `Editor` y `Translator`
> como papeles separados. Mylar3 no lee `Translator` en absoluto. ComicTagger define el rol
> `translator` en su metadata genérica, pero el tag ComicRack/ComicInfo **no lo serializa**; usarlo
> como referencia para «ida y vuelta» perdería justo el campo que más nos interesa.

---

## 3. Cómo lo hace cada referencia

### 3.1 Kavita

**Qué guarda y en qué modelo.** Kavita tiene un `ComicInfo` completo
(`Kavita.Models/Metadata/ComicInfo.cs:17-128`) y un `CleanComicInfo`
(`Kavita.Services/Extensions/ComicInfoExtensions.cs:11-50`) que recorta espacios, limpia autores,
convierte `Number` con coma decimal a punto y traduce GTIN a ISBN. El parser de nombre rellena
primero y **después** aplica ComicInfo (`Kavita.Services/Scanner/BasicParser.cs:114` →
`DefaultParser.cs:126-157`): `Volume`, `Number`, `Series`, `LocalizedSeries`, `SeriesSort` y
`Format` (special) pueden **pisar** lo deducido del nombre.

A nivel de **número** (`Kavita.Services/Scanner/ProcessSeries.cs:1193-1288`) guarda:
`Title`, `Summary`, `Language`, `SeriesGroup`, `StoryArc`, `AlternateSeries`/`AlternateNumber`/
`AlternateCount`, `StoryArcNumber`, `WebLinks`, `ISBN`, `ReleaseDate` (a partir de
`Year`/`Month`/`Day`), los ocho roles de persona, `Genres`, `Tags` y `AgeRating`.
A nivel de **serie** (`ProcessSeries.cs:414-530`) deriva: `ReleaseYear` = mínimo de los números,
`Summary` = sinopsis del primer número, `Language` = la del primer número, personas agregadas de
los números, `Tags`, `Genres` y `AgeRating` = máximo. **No hay una tabla `Publisher`**: `<Publisher>`
e `<Imprint>` se guardan como `Person` con rol `Publisher`/`Imprint`
(`ComicInfo.cs:127-128`; `GetPeopleForRole` en `:133-148`; el enum en
`Kavita.Models/Entities/Enums/PersonRole.cs:3-23`). **`PageCount` se lee pero no se
usa** (`ComicInfo.cs:35`; no aparece en `UpdateChapterFromComicInfo`).

**Precedencia.** Los campos de capítulo se sobrescriben salvo que su `*Locked` esté activo
(`ProcessSeries.cs:1202-1283`; candados en `Kavita.Models/Entities/Chapter.cs:152-172`). No hay
«solo huecos»: un `Summary` nuevo sustituye al anterior. Los créditos se **reemplazan por rol**:
`PersonHelper.UpdateChapterPeople` calcula los nombres normalizados del ComicInfo, **elimina** los
que ya no están y añade los que faltan (`Kavita.Services/Helpers/PersonHelper.cs:104-143`); la
serie se recalcula desde los capítulos (`:39-96`). El único freno es el candado por rol
(`Chapter.IsPersonRoleLocked`, `:205-221`). No hay prueba de autoría: si un XML trae menos créditos
que el anterior, los que faltan se pierden.

**Autores.** `Person` es global, con `NormalizedName` (`Kavita.Models/Entities/Person/Person.cs:10`)
y alias. La normalización quita puntuación y espacios y pasa a minúsculas
(`Kavita.Common/Extensions/StringExtensions.cs:26` y `:61`): «José A. Pérez» y «jose a perez»
comparten `NormalizedName`. `ChapterPeople`/`SeriesMetadataPeople` llevan el rol y se deduplican
por `(persona normalizada, rol)`; si el mismo nombre aparece en dos roles, se guardan dos filas.
Editor y Traductor son roles de primera clase; Editorial e Impronta también, lo que mezcla
conceptos de entidad y de persona.

**Cuándo se ejecuta.** En el escaneo, cuando el archivo es nuevo o ha cambiado
(`ProcessSeries.cs:1193-1198`: `ForceUpdate || FileChanged`). Lee el `ComicInfo.xml` del archivo
con `ArchiveService.GetComicInfo` (`Kavita.Services/ArchiveService.cs:412-468`), primero la entrada
raíz exacta y si no cualquier entrada cuyo nombre termine en `ComicInfo.xml`; deserializa con
`XDocument.Load` + `XmlSerializer` (`:477-491`). El parseo de archivos va en paralelo
(`Kavita.Services/Scanner/ParseScannedFiles.cs:1208`), pero la actualización de metadatos es por
serie. Es idempotente en el sentido de que un archivo sin cambios no se vuelve a aplicar; no hay
marca de «qué campos escribí».

**Saneado y límites.** Antes de deserializar elimina elementos vacíos (`ArchiveService.cs:477-484`);
`CleanComicInfo` limpia autores y números. **No hay un tope explícito de tamaño** en
`GetComicInfo`: abre la entrada y la carga entera en memoria (`:427-437`). Un XML roto lanza
excepción; el llamador decide. No se ve limpieza de HTML en `<Summary>` ni truncado por longitud.

### 3.2 Komga

**Qué guarda y en qué modelo.** `ComicInfoProvider` declara capacidades de título, sinopsis,
número, `numberSort`, fecha, autores, entidades notables, read lists y enlaces
(`komga/src/main/kotlin/org/gotson/komga/infrastructure/metadata/comicrack/ComicInfoProvider.kt:38-50`).
El parche de **book** (`:52-136`) lleva `title`, `summary`, `number`, `numberSort`,
`releaseDate` (con `LocalDate.of(year, month ?: 1, day ?: 1)`, `:54-56`), `authors`, `notableEntities`,
`readLists`, `links`, `tags` (en minúsculas, `:118`) e ISBN validado (`:120`). El parche de
**serie** (`:145-172`) lleva `title`, `titleSort`, `readingDirection` (según `<Manga>`),
`publisher`, `ageRating`, `language` validado como BCP-47, `genres`, `totalBookCount` y
`collections`. **`PageCount` está en el DTO pero no se usa** (`dto/ComicInfo.kt:88`); no hay
`pageCount` en `BookMetadataPatch` ni en `ComicInfoProvider`. **`Summary` no se copia a la serie**:
en el parche agregado de serie se fuerza `summary = null`
(`komga/src/main/kotlin/org/gotson/komga/domain/service/SeriesMetadataLifecycle.kt:106-124`).
`Volume` no se guarda como campo: solo se añade al título si la biblioteca activa
`importComicInfoSeriesAppendVolume` (`ComicInfoProvider.kt:154`).

**Precedencia.** `MetadataApplier.getIfNotLocked` aplica el parche solo si el valor no es nulo y el
campo no está bloqueado (`komga/src/main/kotlin/org/gotson/komga/domain/service/MetadataApplier.kt:11-36`
para book, `:44-56` para serie). Los candados son por campo: `titleLock`, `summaryLock`,
`numberLock`, `numberSortLock`, `releaseDateLock`, `authorsLock`, `notableEntitiesLock`, `tagsLock`,
`isbnLock`, `linksLock` (`komga/src/main/kotlin/org/gotson/komga/domain/model/BookMetadata.kt:18-27`).
No hay «solo huecos»: un valor no nulo del ComicInfo sustituye al que hubiera, salvo candado.
`authors` se sustituye **como lista completa** (`MetadataApplier.kt:32`), no se fusiona. La
biblioteca decide si importa ComicInfo por libro, serie, read list o colección
(`ComicInfoProvider.kt:177-186`); si está apagado, no se aplica nada.

**Autores.** `Author(name, role)` es un valor por libro: recorta el nombre y pasa el rol a
minúsculas (`komga/src/main/kotlin/org/gotson/komga/domain/model/Author.kt:3-16`); no hay persona
global, alias ni nombre normalizado. Se guarda una fila por `(book, name, role)`
(`komga/src/main/kotlin/org/gotson/komga/infrastructure/jooq/main/BookMetadataDao.kt:204-225`), sin
deduplicación normalizada. Los ocho roles se mapean, con `CoverArtist` → `cover`
(`ComicInfoProvider.kt:60-68`).

**Cuándo se ejecuta.** En la importación y en el escaneo, como tareas: `ScanLibrary` analiza los
libros `UNKNOWN`/`OUTDATED` (`application/tasks/TaskEmitter.kt:45-58`); `AnalyzeBook` devuelve
`REFRESH_METADATA` si el medio está listo (`domain/service/BookLifecycle.kt:104`); entonces
`RefreshBookMetadata` refresca el book y encadena `RefreshSeriesMetadata`
(`application/tasks/TaskHandler.kt:97-105`). Hay un pool de tareas configurable
(`application/tasks/TaskProcessor.kt:25-60`). También hay refresco manual por API
(`interfaces/api/rest/BookController.kt:644`). `getFileContent` extrae la entrada entera a un
`ByteArray` (`domain/service/BookAnalyzer.kt:351-370`). No hay marca de autoría; la idempotencia
depende de que el escaneo no reanalice un libro sin cambios y de los candados.

**Saneado y límites.** Jackson `XmlMapper` con `@JsonIgnoreProperties(ignoreUnknown=true)`
(`infrastructure/metadata/comicrack/dto/ComicInfo.kt:7`): los tags desconocidos se ignoran. Un XML
roto se captura, se registra y devuelve `null` (`ComicInfoProvider.kt:188-201`), sin abortar. Valida
ISBN, BCP-47, `AgeRating` y `numberSort`; los enlaces inválidos se descartan (`:105-116`). **No hay
tope de tamaño** en `getComicInfo`: lee la entrada completa (`:195-196`). Tampoco se ve limpieza de
HTML en `<Summary>`.

### 3.3 Mylar3

**Qué guarda y en qué modelo.** Mylar3 **no guarda** los campos descriptivos del ComicInfo. Solo
lee el XML en la importación si `IMP_METADATA` está activo, y lo usa para **identificar**: serie,
número, año, volumen, título (leído pero no persistido), `Notes` (Issue ID de CV) y `Web` (URL de
CV). Después consulta Comic Vine y es CV quien rellena la BD
(`mylar/librarysync.py:284-460`; `mylar/helpers.py:1627-1938`). El esquema `comics`/`issues`
(`mylar/__init__.py:805-806`) tiene `ComicPublisher`, `Description`, `IssueName`, etc., pero **no
tiene columnas de creadores**. `IssueDetails` devuelve `Writer`/`Penciller`/`Inker`/`Colorist`/
`Letterer`/`CoverArtist`/`Editor`/`Publisher`/`PageCount` para visualización
(`mylar/helpers.py:1751-1791`), pero no los escribe en la BD.

**Precedencia.** No hay precedencia campo a campo en la lectura: el ComicInfo solo aporta
identidad; lo que ya hay en la BD no se toca por leerlo. `IMP_METADATA` está **desactivado por
defecto** y el propio código lo marca como «testing only» (`mylar/config.py:186`). En la escritura,
Mylar3 usa ComicTagger embebido y, por defecto, `CT_CBZ_OVERWRITE=False` añade `--nooverwrite`
(`mylar/config.py:342`, `mylar/cmtagmylar.py:183-189`): si el CBZ ya tiene bloque de tags, **no lo
modifica**. Es un todo-o-nada, no un merge por campo.

**Autores.** No se persisten. El ComicTagger embebido escribe créditos desde los datos de CV; su
lector de ComicInfo no incluye `Translator` (el `ComicInfoXml` embebido solo tiene sinónimos de
writer/penciller/inker/colorist/letterer/cover/editor, `lib/comictaggerlib/comicapi/comicinfoxml.py:24-34`).
Para una edición española, Mylar3 pierde el traductor.

**Cuándo se ejecuta.** En la importación, solo si `IMP_METADATA`; y cada vez que la interfaz/OPDS
pide detalles de un número, porque `IssueDetails` vuelve a abrir el CBZ
(`mylar/opds.py:404`, `:491`, `:795`, `:917`; `mylar/webserve.py:7755`). No hay idempotencia
persistente ni marca de lo aplicado.

**Saneado y límites.** `xml.dom.minidom.parseString` sobre los bytes de la entrada
(`mylar/helpers.py:1692`). Solo encuentra la entrada si el nombre es exactamente `ComicInfo.xml`
(`:1653`), no una ruta anidada. No hay tope de tamaño ni limpieza de HTML. Un XML roto se captura en
la importación y se cae al nombre del archivo (`mylar/librarysync.py:288-300`); en visualización
puede fallar.

### 3.4 Kapowarr

**No lee ComicInfo.** En el commit contrastado no hay ninguna referencia a `ComicInfo` en el
código de backend. `comicinfo.xml` figura en `METADATA_FILES` junto a `cvinfo.xml`,
`series.json` y `metadata.json` (`backend/base/definitions.py:164-174`); se trata como **archivo
general de metadatos**, no como fuente: al extraer datos del nombre se usa la carpeta
(`backend/base/file_extraction.py:386-395`), al emparejar se marca como `GeneralFileType.METADATA`
(`backend/implementations/file_matching.py:468-478`) y al renombrar se conserva el nombre
(`backend/implementations/naming.py:772-773`). No hay campos, precedencia, autores ni saneado que
comparar: **es un control negativo**. Su acierto es no romper el archivo; su límite, que el
coleccionista que solo tenga ComicInfo no obtiene nada.

### 3.5 ComicTagger

**Qué guarda.** `GenericMetadata` es el modelo común; el tag ComicRack/ComicInfo declara sus
atributos en `comicapi/tags/comicrack.py:39-80` y los convierte a XML en `:159-289`: `Series`,
`Number`, `Count`, `Title`, `Volume`, `Genre`, `Summary` (como `description`), `Notes`,
`AlternateSeries`/`Number`/`Count`, `StoryArc`, `SeriesGroup`, `Publisher`, `Imprint`,
`Day`/`Month`/`Year`, `LanguageISO`, `Web`, `Format`, `Manga`, `BlackAndWhite`, `AgeRating`,
`CommunityRating`, `PageCount`, `Characters`, `Teams`, `Locations` y los créditos
`Writer`/`Penciller`/`Inker`/`Colorist`/`Letterer`/`CoverArtist`/`Editor` (`:256-267`). **No hay
`Translator`** ni en `supported_attributes` (`:39-80`) ni en la escritura/lectura de créditos
(`:256-267`, `:356-377`), aunque `GenericMetadata.translator_synonyms` exista
(`comicapi/genericmetadata.py:195`).

**Precedencia.** Es la referencia con un vocabulario explícito de merge: `Mode.OVERLAY` y
`Mode.ADD_MISSING` (`comicapi/merge.py:10-20`). `overlay` sustituye solo si el valor nuevo no está
vacío (`:34-40`); las listas se fusionan deduplicando por `norm_fold` (NFKD + casefold) y gana el
valor nuevo (`:15-31`). La CLI lee los tags existentes y los superpone; luego mezcla el nombre del
archivo con `ADD_MISSING` salvo `--prefer-filename` (`comictaggerlib/cli.py:269-290`).
`--skip-existing-tags` salta el archivo entero si ya tiene el tag (`cli.py:383`, `:518`). Al
escribir, parte del XML existente y **preserva los elementos desconocidos**
(`comicapi/tags/comicrack.py:159-186`); si un campo gestionado queda vacío, **borra** su tag
(`:172-186`). No hay candados persistentes ni prueba de autoría: el control es la opción de merge y
la intervención del usuario.

**Autores.** Lista de créditos con sinónimos (`writer`, `plotter`, `scripter`; `artist` sirve a
penciller e inker, etc., `comicapi/tags/comicrack.py:24-34`). Al escribir, separa por rol y une por
coma; al leer, separa por coma y añade `Cover` para `CoverArtist`. No normaliza nombres para
deduplicar; la GUI pregunta si se quiere fusionar un crédito duplicado
(`comictaggerlib/taggerwindow.py:1502-1535`). Para una edición española, el traductor se pierde en
el viaje a ComicInfo.

**Cuándo se ejecuta.** A demanda: CLI, GUI o lote; `--dryrun` no escribe
(`comictaggerlib/ctsettings/commandline.py:125-131`). No es un servicio de escaneo. Lee y reescribe
el archivo completo.

**Saneado y límites.** `_validate_bytes` exige raíz `<ComicInfo>` y captura `ParseError`
(`comicapi/tags/comicrack.py:407-420`). `cleanup_html` convierte el HTML de la sinopsis a texto y
opcionalmente quita tablas (`comictalker/talker_utils.py:36-100`), pero **no hay tope de longitud**
ni de tamaño de XML.

---

## 4. Lectura de conjunto

| Pregunta | Lo que hacen las referencias | Consecuencia para ZascArr |
|---|---|---|
| ¿Serie o número? | Kavita deriva la serie del primer número y de los capítulos; Komga separa book y series; Mylar3 solo identifica; Kapowarr nada. | `Summary`/fecha/páginas/créditos son del **número**; `Publisher` es de la **serie**. No copiar la sinopsis de un número a la serie. |
| ¿Pisan lo que hay? | Kavita y Komga sobrescriben salvo candado; ComicTagger ofrece overlay/add-missing; Mylar3 no lee para guardar; Kapowarr no lee. | Adoptar **solo huecos** + prueba de autoría; no el overlay ciego. |
| ¿Respetan lo manual? | Kavita/Komga con `*Locked`; nadie distingue «lo escribí yo» de «lo escribió una persona». | Reutilizar `locked_fields` **y** añadir la marca de autoría que B6 ya inventó. |
| ¿Autores? | Kavita: persona global normalizada y reemplazo por rol; Komga: lista por libro sin normalizar; Mylar3: no persiste; ComicTagger: créditos sin normalizar. | Crear/reutilizar `Creator` por nombre normalizado y **añadir solo lo que falta**; no borrar ni sustituir la lista. |
| ¿Cuándo? | Escaneo/importación (Kavita, Komga), a demanda (ComicTagger), solo visualización (Mylar3), nunca (Kapowarr). | En el triaje que ya se hace; al vincular a mano, releer solo ese archivo; nunca en cada request. |
| ¿Cuánto leen? | Todos leen la entrada `ComicInfo.xml` completa; ninguno tiene tope explícito en esa ruta. | Mantener el tope de 1 MiB y no abrir páginas. ZascArr ya lo hace. |
| ¿Sanean? | Kavita limpia autores/números; Komga valida ISBN/BCP-47; ComicTagger limpia HTML; Mylar3 apenas; Kapowarr no aplica. | Limpiar HTML, recortar longitudes, validar fechas/páginas y contar lo descartado. |

---

## 5. Veredicto por idea

| # | Idea | Referencia | Resultado | Motivo / qué cambia en ZascArr |
|---|---|---|---|---|
| 1 | Guardar los campos descriptivos del ComicInfo al importar | Kavita, Komga | **Adoptar** | Es el corazón de BL-INF2; ya se leen y se tiran. |
| 2 | `Summary` en el número, no en la serie | Komga (serie = null) | **Adaptar** | Kavita copia la sinopsis del primer número a la serie; aquí sería mentir sobre la serie. |
| 3 | `Year` → `Issue.release_date` | Kavita, Komga | **Adaptar** | Las dos inventan 1 de enero si faltan mes/día. ZascArr no debe fingir precisión. |
| 4 | `Publisher` → `Series.publisher_id` | Komga | **Adoptar/adaptar** | Entidad normalizada, solo hueco; conflicto entre números no debe hacer *thrash*. |
| 5 | `PageCount` → `Issue.page_count` | Nadie lo usa | **Mejorar** | Solo si el número tiene un archivo; si no, guardarlo por archivo. |
| 6 | `Creator` global con nombre normalizado | Kavita | **Adoptar** | Evita «José A. Pérez» vs «Jose A Perez»; añadir índice único. |
| 7 | Reemplazar/eliminar créditos por rol | Kavita, Komga | **Descartar** | Un XML más pobre borra créditos buenos; pérdida de datos. |
| 8 | Añadir solo créditos que faltan | B6/ETQ2 (propio) | **Construir sobre lo propio** | Misma filosofía que `_aplicar_comicinfo` de ETQ2. |
| 9 | Candados por campo | Kavita, Komga | **Adoptar** | `locked_fields` ya existe; reutilizar nombres de B6. |
| 10 | Estrategias `ADD_MISSING`/`OVERLAY` | ComicTagger | **Adaptar** | El vocabulario sirve; la dirección de lectura es «solo huecos + propio». |
| 11 | Prueba de autoría (`propio`) | B6 (propio) | **Construir sobre lo propio / mejorar** | Ninguna referencia sabe qué escribió ella misma; B6 ya lo resolvió para escribir. |
| 12 | `Publisher` como `PersonRole` | Kavita | **Descartar** | ZascArr tiene `Publisher` normalizado; no mezclar entidad con persona. |
| 13 | Sinopsis de la serie = primer número | Kavita | **Descartar** | La serie no es un número; BL-INF1 ya separa ambos bloques. |
| 14 | Fecha 1 de enero si solo hay año | Kavita, Komga | **Descartar** | «No consta» es mejor que una fecha falsa. |
| 15 | `Translator` como rol separado | Kavita, Komga | **Adoptar** | Clave en edición española; ComicTagger no lo guarda en ComicInfo. |
| 16 | `Editor`/`Translator` no se suman a `Writer` | Kavita, Komga, BL-INF1 | **Adoptar** | BL-INF1 ya los explica como papeles distintos. |
| 17 | Ignorar el ComicInfo | Kapowarr, Mylar3 por defecto | **Descartar** | Es justo el statu quo que la historia quiere cambiar. |
| 18 | Etiquetas/géneros | ETQ2 | **No duplicar** | Ya está hecho; BL-INF2 no toca `series_tags`/`series_genres`. |
| 19 | Escribir el XML de vuelta | B6/ETQ6 | **Descartar de INF2** | Otra historia y otro contrato; aquí solo se lee. |
| 20 | Personajes/equipos/lugares, saga, edad, idioma | Referencias | **Aplazar** | Requieren modelo/UX propios (ETQ3 y otras); no meter en el mismo cambio. |

---

## 6. Recomendación para ZascArr

### 6.1 Las cinco reglas que sostienen el diseño

1. **Leer una vez, en el triaje que ya existe.** `TriageResult.comic_info` ya trae todo; se aplica
   en el mismo ciclo. No se abre el CBZ otra vez ni se leen páginas.
2. **Solo huecos + autoría.** Vacío → rellenar; igual → nada; distinto y lo escribió ZascArr →
   actualizar; distinto y es de otro/manual → conservar; `locked_fields` → no tocar.
3. **Número vs serie.** Sinopsis, fecha, páginas y créditos son del número. Editorial es de la
   serie. Nunca se reescriben `Series.title` ni `Issue.issue_number`, y la sinopsis de un número no
   se copia a la serie.
4. **Autores: crear/reutilizar, nunca borrar.** `Creator` único por nombre normalizado;
   `IssueCreator` por `(issue, creator, role)`; se añaden los que faltan y no se elimina ninguno.
   Editor y Traductor van aparte, con su rol.
5. **Idempotencia por marca, no por fechas.** Se guarda en `metadata_` qué valores escribió
   ZascArr; repetir la importación no duplica ni cambia nada. Nada de `updated_at` si no cambió un
   valor.

### 6.2 Mapa de campos propuesto

| Tag | Destino | Entidad | Regla | Límite / saneado |
|---|---|---|---|---|
| `Summary` | `Issue.synopsis` | Número | Solo si vacío o si el valor actual es el que escribió ZascArr; nunca a `Series.description`. | `texto_plano`, colapsar espacios, **8 KiB**; truncar con aviso. |
| `Year` (+`Month`/`Day`) | `Issue.release_date` | Número | Solo si vacío (o propio). Si hay fecha completa válida, escribirla; si solo hay año, **no inventar** mes/día: guardar el año en `metadata_` con precisión `year`. | Año 1000…(actual+2); mes 1-12; día válido para el mes. |
| `Publisher` | `Series.publisher_id` | Serie | Solo si `NULL`; crear/reutilizar `Publisher` por nombre normalizado. Si dos números discrepan, conservar el primero y registrar el conflicto; no cambiar en cada importación. | 255 caracteres; vacío/espacios → ignorar. |
| `PageCount` | `Issue.page_count` | Número | Solo si `NULL` y el número tiene **exactamente un archivo**. Si tiene varios, guardar el dato por archivo en `File.metadata_` y no tocar `Issue.page_count`. | 1…10 000; fuera de rango → ignorar con aviso. |
| `Title` | `Issue.title` | Número | Opcional; solo si vacío/propio. No sustituye el título que venga de una fuente externa. | 500 caracteres (columna); `texto_plano`. |
| `Volume` | `Issue.volume` | Número | Opcional; solo si el número no tiene volumen fiable. No se usa para reasignar identidad. | 1…10 000. |
| `Writer` | `Creator` + `IssueCreator` rol `writer` | Número → creador | Añadir solo los que falten; nunca borrar. | 50 nombres/rol; 255 por nombre. |
| `Penciller` | rol `penciler` | Número → creador | Igual; ojo a la doble L del tag y la una L del enum. | Igual. |
| `Inker` | rol `inker` | Número → creador | Igual. | Igual. |
| `Colorist` | rol `colorist` | Número → creador | Igual. | Igual. |
| `Letterer` | rol `letterer` | Número → creador | Igual. | Igual. |
| `CoverArtist` | rol `cover_artist` | Número → creador | Igual. | Igual. |
| `Editor` | rol `editor` | Número → creador | Rol separado; no se suma a `writer`. | Igual. |
| `Translator` | rol `translator` | Número → creador | Rol separado; imprescindible en edición española. | Igual. |
| `Tags`/`Genre` | ya ETQ2 | Serie | **No tocar en BL-INF2**. | Topes de ETQ2. |
| `Series`/`Number` | identidad | — | No reescribir; ya emparejaron. | — |
| `LanguageISO`, `AgeRating`, `Characters`, `Teams`, `Locations`, `StoryArc`, `SeriesGroup`, `Web`, `Notes`, `ISBN` | — | — | Fuera de alcance; no inventar. | — |

### 6.3 Precedencia exacta (dirección lectura)

Para cada campo aplicable, en este orden:

1. **Candado:** si el campo está en `locked_fields` de la entidad → `bloqueado`, no se escribe y se
   cuenta.
2. **Sin dato:** si el tag falta, está vacío o no pasa la validación → `sin_dato`, no se toca.
3. **Destino vacío:** si el campo destino es `NULL`/vacío → `cambia` (rellenar).
4. **Ya coincide:** si el valor actual es igual al del ComicInfo → `ya_coincide`, no se escribe.
5. **Es nuestro:** si el valor actual es exactamente el que ZascArr escribió la última vez según la
   marca de `metadata_` → `cambia` (actualizar al valor nuevo).
6. **Es de otro/manual:** si el valor actual no coincide con la marca → `conserva`, no se pisa, y se
   cuenta como conservado.

**Excepciones deliberadas:**

- **`Publisher` de serie:** nunca se sobrescribe un valor no nulo, ni siquiera si es «nuestro». Solo
  se rellena el hueco. Si otro número trae otra editorial, se conserva la primera y se registra
  `publisher_conflict` en `Series.metadata_`; no se cambia en cada importación.
- **Créditos:** no se rige por «valor actual», sino por conjuntos: se añade cada
  `(creator_norm, role)` que falte; no se elimina ninguno. Si `Issue.locked_fields` contiene
  `credits`, se salta el bloque entero.
- **`release_date`:** si solo hay año, no se escribe una fecha falsa. Se guarda
  `metadata_["comicinfo"]["year"]` y, si el PO quiere verlo, se decide en la especificación si se
  añade una columna de precisión o se renderiza el año como «2014» sin día/mes.
- **`PageCount`:** solo se aplica a `Issue.page_count` con un único archivo; con varios, el dato es
  del archivo, no del número.

### 6.4 `metadata_source`, `locked_fields` y marca de autoría

**`metadata_source` es de entidad, no de campo.** No sirve para decir «esta sinopsis vino del
ComicInfo» si la serie se enriqueció con Comic Vine. Regla:

| Entidad | Regla |
|---|---|
| `Series.metadata_source` | Si es `NULL` y se aplicó al menos un campo **de la serie** (p. ej. editorial) → `comicinfo_xml`. Si es `manual` → **nunca** se toca. Si es `comic_vine`/`tebeosfera`/`gcd`/`anilist` → **se conserva**; la entidad sigue siendo de esa fuente y el detalle va en `metadata_`. |
| `Issue.metadata_source` | Igual: si es `NULL` y se aplicó al menos un campo **del número** → `comicinfo_xml`; `manual` → nunca; fuente externa → conservar. |
| `Publisher.metadata_source` | `comicinfo_xml` si se crea desde el CBZ; no pisar `manual` ni una fila con ID de otra fuente. |
| `Creator.metadata_source` | `comicinfo_xml` si se crea desde el CBZ; si se reutiliza una fila existente, **no** se cambia su fuente. |
| `File.metadata_source` | Se queda como está: `comicinfo_xml` significa «la identidad del archivo salió del ComicInfo» (`strong_candidate`), no «todos los campos». No sobrecargarlo. |

**`locked_fields`:** reutilizar los nombres que ya usa B6 (`services/tagger.py:67-74`) y añadir los
nuevos:

- `Series`: `publisher_id` (y `title` si algún día se escribiera).
- `Issue`: `synopsis`, `release_date`, `page_count`, `title`, `volume`, `credits`.
- `Creator`: `name` (si se permite corregir el nombre visible sin que se vuelva a normalizar).

Hoy no hay UI de edición en BL-INF1; el candado se puede fijar por la vía que la especificación
decida (formulario de edición o API). Mientras no exista, el candado protege sobre todo lo que
fijen los flujos existentes (`series_id`, `issue_number` en la asignación manual) y lo que se
incorpore después.

**Marca de autoría:** en `Issue.metadata_` (y `Series.metadata_` para la editorial), bajo
`comicinfo_aplicado`, se guarda:

| Clave | Contenido |
|---|---|
| `file_sha256` / `file_mtime_ns` | Identidad del archivo con el que se aplicó; sirve para saber si la marca es fresca. |
| `campos` | Valores que ZascArr escribió: `synopsis`, `release_date`, `page_count`, `title`, `volume`. |
| `publisher_id` | UUID que ZascArr escribió en la serie, si fue él. |
| `creditos` | Lista de pares `[nombre_normalizado, rol]` que ZascArr añadió. |
| `publisher_conflict` | Editorial observada que no se aplicó, si la hubo. |

No se guarda una marca por cada lectura: si el contenido no cambia, no se reescribe la marca (evita
`updated_at` y escrituras inútiles). La marca es **distinta** de `comicinfo_propio`/`comicinfo_estado`
de B6, que describen la escritura del XML; no mezclarlas.

### 6.5 Algoritmo de autores

1. **Parsear:** dividir el tag por comas, recortar, colapsar espacios, quitar caracteres de control
   y descartar vacíos. Tope: 50 nombres por rol y 200 por número; el resto se ignora con aviso.
2. **Separar nombre visible y nombre de comparación:** se conserva el nombre tal cual para mostrar
   (recortado a 255) y se calcula `name_norm` con NFKC + minúsculas + sin acentos + puntuación a
   espacio + colapso. No se usa `f_title_norm` (quita artículos); sirve `f_tag_norm` o un
   `normalize_name` equivalente.
3. **Reutilizar:** buscar `Creator` por `name_norm`. Si existe, no se crea otro ni se pisa su
   `metadata_source`. Si no existe, se crea con `name` visible y `metadata_source='comicinfo_xml'`.
4. **Evitar duplicados concurrentes:** índice único sobre `name_norm` + `INSERT ... ON CONFLICT DO
   NOTHING` y releer; o serializar por el lock del importador. Sin índice único, dos importaciones
   simultáneas pueden crear dos «Alan Moore».
5. **Asignar rol:** `Writer`→`writer`, `Penciller`→`penciler`, `Inker`→`inker`, `Colorist`→
   `colorist`, `Letterer`→`letterer`, `CoverArtist`→`cover_artist`, `Editor`→`editor`,
   `Translator`→`translator`. Si el mismo nombre aparece en dos roles, se guardan **dos** filas; si
   se repite en el mismo rol, **una**.
6. **Insertar crédito:** añadir `IssueCreator` solo si no existe `(issue_id, creator_id, role)`; la
   PK ya lo impide. No se borra ninguno. Si el número no tiene `issue_id`, no se aplican créditos
   (se aplicarán al vincular).
7. **No mezclar:** `Editor` y `Translator` no se suman a `Writer`; `Publisher`/`Imprint` no son
   créditos de número.

### 6.6 Cuándo, dónde y cuánto se lee

| Momento | Qué se hace | Coste |
|---|---|---|
| Importación con match | Se aplica `TriageResult.comic_info` en el mismo ciclo, después de crear/enlazar el `File`. | Cero I/O extra: el XML ya se leyó. |
| Adopción/registro de biblioteca | Si el archivo queda vinculado, se aplica igual; si queda en `_Unsorted`, se guarda el vínculo y se aplica al vincular. | Cero I/O extra si el triaje ya se hizo. |
| Vínculo manual (arrastrar/asignar) | Se vuelve a leer **solo ese** `ComicInfo.xml` en `asyncio.to_thread`, se aplica y se marca. | Una lectura de una entrada de <1 MiB; aceptable en la Pi. |
| Rescan/re-triaje | Se actualiza la marca y se aplican los cambios; si el archivo cambió de número, se rellena el nuevo y no se borran los créditos del anterior. | El rescan ya re-triea; no hay pase extra. |
| Ficha/API/OPDS | **Nunca** se lee el CBZ para pintar metadatos; se lee la BD. | Cero. |

- **Hilo:** `triage` ya va en `asyncio.to_thread` (`services/importer.py:374` y
  `library_adopter` usan `_triage_sin_bloquear`). Las escrituras van por la sesión async; no se
  añade worker, cola ni Redis.
- **Backfill de una biblioteca ya registrada:** el rescan normal no re-triea los archivos que no
  cambiaron. Si el PO quiere que los CBZ antiguos aparezcan, hace falta una acción explícita
  (comando administrativo o botón en Auditoría) que recorra con `--limit`, `dry-run` e idempotencia,
  como el etiquetador B6. **No** hacerlo automático en el arranque: en una Pi con miles de CBZ es
  un pico de disco.

### 6.7 Saneado y topes

| Entrada | Regla | Qué se hace |
|---|---|---|
| XML > 1 MiB | Ya existe `MAX_COMICINFO_BYTES` | Ignorar la entrada, avisar; no descomprimir más. |
| XML malformado | `ElementTree.ParseError` | Ignorar el ComicInfo, avisar; la importación sigue. |
| Raíz distinta de `<ComicInfo>` | Comprobar `root.tag` | Ignorar con aviso; no interpretar un XML ajeno. |
| Varias entradas `ComicInfo.xml` | Convención: raíz; si hay varias | Usar la primera y avisar; no fusionar en lectura. |
| `<Summary>` con HTML | `utils/texto_html.texto_plano` (`:51`) | Guardar texto plano, sin `script`/`style`, entidades decodificadas y espacios colapsados. |
| `<Summary>` enorme | 8 KiB | Truncar y avisar; no reventar `Text` ni la UI. |
| Entidades | ElementTree no resuelve externas; expat corta anidadas | Mantener el test de entidades; no aceptar DTD/XXE. |
| Caracteres de control | `\x00-\x1f` salvo tabulador/salto | Sustituir por espacio; no guardar basura. |
| `Year`/`Month`/`Day` | Año 1000…actual+2; mes 1-12; día válido | Ignorar el campo si no forma una fecha real. |
| `PageCount` | 1…10 000 | Ignorar fuera de rango; no usar 0 como «desconocido». |
| `Publisher` | 255; vacío → nada | Recortar; no crear editoriales de un espacio. |
| Nombres de autor | 255; 50/rol; 200/número | Descartar el exceso con aviso. |
| Nombres con coma | El estándar separa por coma | Se documenta la limitación; no inventar heurísticas para «Jr.» ni «&». |
| Tags desconocidos | No se guardan | Sin error; el XML puede traer más cosas. |

**Qué se cuenta:** por archivo, `campos_aplicados`, `campos_conservados`, `campos_bloqueados`,
`campos_invalidos`, `autores_creados`, `autores_reutilizados`, `publisher_conflict`. Se guarda en
la marca del `File`/`Issue` y se resume en el informe del ciclo; no se pinta un aviso por campo en
la cara del coleccionista.

### 6.8 Cambios de modelo necesarios (mínimos)

1. **`creators.name_norm`** generada (o índice funcional único) para reutilizar autores sin
   duplicados. Es el único cambio de esquema que la corrección exige; sin él, el «mismo» autor puede
   entrar dos veces por mayúsculas/tildes.
2. **`publishers.name_norm`** (o índice funcional) por la misma razón: `Publisher.name` es único
   exacto (`models/__init__.py:278`) y «Planeta»/«planeta» convivirían.
3. **Nada más obligatorio:** `Issue.synopsis`, `release_date`, `page_count`, `title`, `volume`,
   `Series.publisher_id` y `IssueCreator` ya existen. La marca va en `metadata_` (JSONB).
4. **Opcional, si el PO quiere año visible:** `Issue.release_date_precision` (`year`/`month`/`day`)
   o guardar el año en `metadata_` y renderizarlo en BL-INF1/INF3. No fingir 1 de enero.
5. **Opcional, para páginas por archivo:** `File.metadata_["comicinfo"]["page_count"]`; no hace
   falta columna.

### 6.9 Lo que NO se debe hacer

- No reescribir `Series.title` ni `Issue.issue_number` con `Series`/`Number` del XML: ya se usaron
  para emparejar; cambiarlos rompería la identidad y los vínculos.
- No copiar `Summary` a `Series.description`: la serie no es un número.
- No borrar créditos que no estén en el XML ni sustituir la lista entera.
- No escribir `release_date` con 1 de enero si solo hay año.
- No aplicar `PageCount` a un número con varios archivos.
- No cambiar la editorial de una serie porque un número traiga otra; conservar y registrar.
- No tocar `File.metadata_source` para marcar campos: es identidad del archivo.
- No abrir el CBZ al pintar la ficha; no leer páginas; no escribir en el ZIP.
- No usar `metadata_source` como si fuera procedencia por campo; para eso está la marca.

### 6.10 Casos de prueba antes de implementar

1. **CBZ completo:** sinopsis, año/mes/día, editorial, páginas y ocho roles → se guardan en el
   número/serie correctos; `IssueCreator` tiene una fila por `(creator, role)`.
2. **Solo huecos:** sinopsis existente de Comic Vine sin candado → no se pisa; se rellena lo que
   falta.
3. **Candado:** `Issue.locked_fields=["synopsis"]` → no se escribe, se cuenta como bloqueado.
4. **Manual:** `Issue.metadata_source="manual"` → no se toca nada de ese número.
5. **Propio:** la marca dice que ZascArr escribió la sinopsis y el XML cambia → se actualiza; si la
   marca no coincide con el valor actual → se conserva.
6. **Reimportación:** mismo archivo dos veces → cero duplicados de `Creator`, `IssueCreator`,
   `Publisher`; cero cambios de valores.
7. **XML roto:** la importación sigue, el archivo se vincula, hay aviso y no se aplica nada a medias.
8. **XML > 1 MiB:** se ignora, no se descomprime entero, no se cae el ciclo.
9. **Sinopsis HTML/enorme:** se guarda texto plano, truncado a 8 KiB, sin etiquetas.
10. **Año solo:** no se escribe una fecha falsa; se guarda la precisión y la UI no muestra un día
    inventado.
11. **Páginas con dos archivos:** `Issue.page_count` no se toca; el dato va por archivo.
12. **Editorial en conflicto:** dos números con editoriales distintas → se conserva la primera y se
    registra el conflicto; no hay *thrash*.
13. **Traductor/editor:** se guardan como roles separados; no se suman a `Writer`.
14. **Mismo nombre en dos roles:** dos filas; mismo nombre repetido en un rol: una.
15. **Mayúsculas/tildes:** «José A. Pérez» y «Jose A Perez» reutilizan el mismo `Creator`.
16. **Concurrencia:** dos importaciones con el mismo autor → una sola fila (índice único +
    `ON CONFLICT`).
17. **Archivo sin `issue_id`:** no se aplican campos de número; al vincular se leen y se aplican.
18. **Coste:** una importación no hace una segunda apertura del CBZ; la ficha no lee el archivo.

---

## 7. Matriz ponderada (nivel 2)

Criterios y pesos por defecto de `benchmark-referencias.md` (suman 100; no se movieron):

| Criterio | Peso |
|---|---:|
| Encaje con el flujo del Coleccionista | 25 |
| Coste en Pi | 20 |
| Seguridad, legalidad y licencia | 20 |
| Cobertura del requisito core | 15 |
| Adaptabilidad al stack y al modelo | 10 |
| Mantenimiento de la referencia | 5 |
| Lock-in y coste de salida | 5 |

Opciones evaluadas (escala 1-5):

| Criterio | A. Statu quo (solo ETQ2) | B. Volcar todo sin candados | C. Solo huecos + candados + autoría | D. Solo huecos sin autoría |
|---|---:|---:|---:|---:|
| Encaje Coleccionista (25) | 2 | 3 | **5** | 4 |
| Coste Pi (20) | 5 | 4 | **4** | 4 |
| Seguridad/legal/licencia (20) | 5 | 2 | **5** | 4 |
| Cobertura core (15) | 2 | 5 | **5** | 4 |
| Adaptabilidad stack/modelo (10) | 5 | 3 | **5** | 4 |
| Mantenimiento (5) | 5 | 2 | **4** | 4 |
| Lock-in/salida (5) | 5 | 3 | **5** | 4 |
| **Total / 100** | **3,80** | **3,25** | **4,75** | **4,00** |

**Gana C.** B cubre más campos pero rompe lo manual y no es revertible sin pérdida; D es barata pero
no puede actualizar lo que ella misma escribió y deja datos viejos si el CBZ se sustituye. A no
cumple la historia. C reutiliza B6, `locked_fields` y el triaje existente: el coste marginal son unas
pocas consultas y filas por archivo.

---

## 8. IGUALAR / MEJORAR

### IGUALAR (mínimo competitivo)

- Leer el `ComicInfo.xml` en el mismo escaneo/importación, sin un segundo pase (Kavita, Komga).
- Candados por campo para que lo manual no se pise (Kavita `*Locked`, Komga `*Lock`).
- Créditos con roles separados, incluidos `Editor` y `Translator` (Kavita, Komga).
- Editorial como dato de serie (Komga), no como persona (Kavita).
- Idempotencia cuando el archivo no cambia (Kavita `FileChanged`, Komga `AnalyzeBook`).
- No tocar el CBZ al leer (ninguna referencia lo hace al importar; Kapowarr ni lo abre).

### MEJORAR (con evidencia de la debilidad)

- **No borrar créditos ausentes.** Kavita elimina los que no están en el XML
  (`PersonHelper.cs:121-127`); Komga sustituye la lista entera (`MetadataApplier.kt:32`). ZascArr
  añadirá solo lo que falte.
- **No fingir 1 de enero.** Kavita (`ProcessSeries.cs:1248-1250`) y Komga
  (`ComicInfoProvider.kt:54-56`) rellenan mes/día con 1. ZascArr guardará precisión.
- **Tope explícito de 1 MiB y entidades acotadas.** Ninguna de las referencias que leen ComicInfo
  muestra un tope en esa ruta; ZascArr ya lo tiene (`importer_triage.py:375-384`).
- **`PageCount` con regla de un solo archivo.** Todas lo leen y casi todas lo ignoran; ZascArr puede
  guardarlo sin mentir sobre un número con varios archivos.
- **Editorial sin *thrash*.** Komga toma la más frecuente entre libros
  (`SeriesMetadataLifecycle.kt:106-124`); Kavita no tiene entidad. ZascArr conserva la primera y
  registra el conflicto.
- **Autoría propia.** Ninguna referencia distingue «lo escribí yo» de «lo escribió una persona»;
  B6 ya tiene `comicinfo_propio` y su `plan` (`core/comicinfo_write.py:73-103`). Se reutiliza el
  patrón, no el código de una referencia.

---

## 9. NOT RUN, caducidad y barrera legal

**NOT RUN:**

- No se ejecutó Kavita, Komga, Mylar3, Kapowarr ni ComicTagger; todo es lectura estática del código
  en los commits de la cabecera.
- No se probó con CBZ reales ni con una biblioteca española; no se midió tiempo/RAM en la Pi.
- No se ejecutó la suite de ZascArr ni se creó ninguna migración.
- El comportamiento de `PageCount` en Kavita/Komga se deduce de que el campo no aparece en la ruta
  de aplicación; no se ejecutó para confirmarlo. `[sin verificar en runtime]`
- La ausencia de lectura de ComicInfo en Kapowarr se comprobó con búsqueda en todo el árbol y en su
  documentación; no se ejecutó una importación.

**Caducidad:** 2027-01-08. Antes si cambia `origin/main`, Kavita, Komga, Mylar3, Kapowarr o
ComicTagger, o si el PO cambia el alcance.

**Barrera legal:** inspirarse en un patrón no es copiar código. Kavita, Mylar3 y Kapowarr son
GPL-3.0; Komga es **MIT**; ComicTagger es Apache-2.0. Si se reutiliza un fragmento concreto, hay que
revisar el fichero, sus avisos y las obligaciones de su licencia. Este documento no copia código:
solo describe contratos y decisiones. La licencia de ZascArr está en `LICENSE`; `src/zascarr/LEGAL.md`
trata el contenido y las fuentes, no la reutilización de código de terceros.

---

## 10. Decisión final / ADR

No hace falta un ADR nuevo: es un mapa de datos y una regla de precedencia, no una decisión de
arquitectura. La especificación de BL-INF2 debe recoger:

1. El mapa de campos de §6.2 y las excepciones de §6.3.
2. La regla de `metadata_source`/`locked_fields`/marca de §6.4.
3. El algoritmo de autores de §6.5.
4. La decisión del PO sobre **precisión de fecha** (año solo) y sobre **backfill** de bibliotecas
   existentes.
5. Los casos de prueba de §6.10 como criterios de aceptación.

**Resumen para la tarjeta:** adoptar la lectura de campos descriptivos en el triaje; adaptar la
precedencia de B6 (solo huecos + autoría + candados); descartar el reemplazo de créditos, la
sinopsis de serie desde un número y la fecha 1 de enero; construir sobre ETQ2/B6 la aplicación
idempotente. La referencia más cercana es Kavita para autores y Komga para serie/número; Kapowarr
no aporta nada porque ignora el archivo. Licencia: Komga es MIT, no GPL.
