# Benchmark — Contexto declarado y reutilizable (MIT-M7, #110)

> Ficha de benchmarking §13 (nivel 2) según `docs/design/benchmark-referencias.md`.
> Feature **#110 «Contexto declarado y reutilizable»** y sus hijas **#130** (declarar el
> significado de una carpeta), **#131** (correspondencia local versionada) y **#132**
> (revisar y retirar decisiones reutilizables).
>
> Lectura: **2026-11-10**, rol SCOUT.bench. `main` contrastado: **`3a8b506`**
> (2026-11-10T17:48+01:00). Referencias fijadas a commit en §2. Todo se ha leído del
> código; **no se ha ejecutado ninguna aplicación**. La ficha **propone**; decide el PO.
> No implementa, no crea migración, no escribe pruebas.
>
> Caducidad: **2027-01-09** (~60 días), o antes si cambia alguna referencia o la feature.

## 1. Problema local

### 1.1 Qué pide la feature, en palabras del tablero

#130 pide **declarar** el significado de una carpeta (por autor, por publicación, por
colección), con su alcance visible (subcarpetas y archivos futuros) y sin inferirlo del
nombre. #131 pide una **correspondencia local versionada** entre un contexto de carpeta y
un destino existente, que solo prepare **propuestas** con `correspondencia_id` y
`version_de_regla`; no crea series, no vincula archivos, no mueve nada. #132 pide
**listar, desactivar y retirar** declaraciones y alias, conservando historial y sin efectos
retrospectivos. Las tres comparten un contrato: identidad de carpeta, alcance, tipos de
destino permitidos, ciclo de vida, conflictos y precedencia explícita o rechazo de la
ambigüedad.

### 1.2 Caso real que lo motiva

En la biblioteca real de 1.542 archivos (medición histórica de
`docs/design/auditoria-b14-carpetas.md` y `docs/design/ficha-propuestas-desde-carpetas.md`),
**123 archivos (8 %) están en una carpeta que no es su serie**: carpetas de autor
(`Carlos Giménez`: 52 archivos, 26 obras), contenedores (`_Omnibus`, `_Specials`), arcos
(`Locas - La muerte de Speedy`), franquicias (`Marvel-Inhumanos`) y carpetas que mezclan
series. El caso testigo es `Batman - Saga de Scott Snyder 01…09` en la carpeta
`Batman - Saga de Scott Snyder (2019)`, que el matcher lleva a `BATMAN (2025)` por igualdad
textual: la carpeta ya contradecía la asignación. Hoy **nadie puede decirle a ZascArr
«esta carpeta es de este autor» o «esta carpeta corresponde a esta serie/edición»**, y la
carpeta solo se lee como pista efímera en cada pasada.

### 1.3 Qué hace hoy ZascArr (verificado en `3a8b506`)

- **La carpeta es una pista, no una decisión, y no se persiste.** `core/carpetas.py` es un
  módulo puro de solo lectura: separa título, año, volumen y calificadores del nombre, y su
  cabecera lo dice expresamente («Una carpeta es una PISTA, nunca una decisión»,
  `core/carpetas.py:1-8`). `services/revision_carpetas.py` agrupa lo pendiente por contexto
  de carpeta y explica conflictos, pero **no escribe en la BD, no mira el disco, no usa la
  red y no ofrece acciones** (`services/revision_carpetas.py:1-10`). Es la rebanada 1.
- **El único antecedente persistente es el alias, y es global.** `LocalAlias`
  (`models/__init__.py:912-928`) guarda `pattern_norm` **único en toda la instalación** →
  `series_id`, sin ámbito, sin estado, sin origen y sin fecha de uso. Una corrección
  posterior sobrescribe la anterior.
- **El alias manda sobre el fuzzy y puede mover archivos.** `SeriesMatcher.find_alias`
  devuelve la serie con `score 1.0` y se consulta antes del matcher
  (`core/matcher.py:216-235`); `decide` corta con `MatchStatus.DIRECT` y nota «alias local
  aprendido» (`core/matcher.py:315-320`); el importador clasifica **sin preguntar** y mueve
  a la biblioteca (inventario A3, `docs/design/inventario-entradas-heredadas-y-alias-2026-10-09.md`).
  El único productor de usuario de alias es la asignación manual de «Por revisar»
  (`services/asignacion.py:565`), que aprende siempre.
- **No existe ninguna tabla de declaraciones ni de correspondencias.** El listado de tablas
  de `models/__init__.py` no tiene `folders`, `folder_contexts` ni equivalente; el
  inventario A6 confirma que **no hay pantalla, endpoint ni servicio que liste, delimite,
  desactive o borre alias**.
- **Lo decidido en ADR 0008 encaja con esta feature:** en el flujo nuevo un alias aporta
  *evidencia*, no *permiso*; confirmar una vinculación no crea alias; la gestión completa
  (listar, delimitar, desactivar, habilitar reglas automáticas con consentimiento) pertenece
  a M7 (`docs/adr/0008-catalogacion-explicita-y-propuestas-sin-ejecucion-silenciosa.md`).

### 1.4 Resultado deseado

Una persona declara una vez —«`Comics/Carlos Giménez` es una carpeta por autor»,
«`Comics/Batman - Saga de Scott Snyder (2019)` corresponde a esta serie/edición»—, ve el
alcance y la versión de esa decisión, recibe propuestas trazables que la usan como
contexto, y puede desactivarla o retirarla sin que nada se mueva, se borre ni se
reinterprete por detrás. **Declarar no es confirmar.** La identidad de la publicación sigue
exigiendo su propia confirmación.

## 2. Referencias consultadas

| Referencia | Versión / commit / fecha | Licencia | Qué se leyó |
|---|---|---|---|
| **Sonarr** | `Sonarr/Sonarr`, rama `develop`, `c018578e4b79ee048575c02d7a8aa2b929e4b837` (2026-11-02) | GPL-3.0 | `RootFolders/RootFolderService.cs`, `RemotePathMappings/RemotePathMapping*.cs`, `Tv/{Series,AddSeriesService,SeriesPathBuilder,MoveSeriesService}.cs`, `Organizer/NamingConfig.cs`, `frontend/src/AddSeries/ImportSeries/Import/{useImportSeries.ts,importSeriesEligibility.ts}` |
| **Radarr** | `Radarr/Radarr`, rama `develop`, `7e3f80c98d01481430ab356f6d7322fc5dc381ee` (2026-11-08) | GPL-3.0 | `Movies/Movie.cs`, `RootFolders/RootFolderService.cs`, `RemotePathMappings/RemotePathMapping.cs`, `Organizer/NamingConfig.cs`, `Movies/MoveMovieService.cs` |
| **Kapowarr** | `Casvt/Kapowarr`, `c191dda6617929c81292483a8cc07f631111dae2` (v1.3.2, 2026-09-14) | GPL-3.0 | `backend/internals/db.py`, `backend/implementations/{root_folders,volumes,matching}.py`, `backend/features/library_import.py` |
| **Mylar3** | `mylar3/mylar3`, `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (2025-08-17) | GPL-3.0 | `mylar/{librarysync,importer,config,__init__}.py`, `mylar/webserve.py` |
| **Komga** | `gotson/komga`, `6e161b6c8b1a4bacc68c9050a1ee0da6bd0707d6` (2026-11-10) | MIT | `domain/model/{Library,Series,Book,SeriesCollection,ReadList}.kt`, `domain/service/{FileSystemScanner,SeriesMetadataLifecycle,SeriesLifecycle}.kt`, `infrastructure/metadata/{comicrack/ComicInfoProvider,mylar/MylarSeriesProvider}.kt` |
| **Kavita** | `Kareadita/Kavita`, `f059e277e934644667dec6843d595bbb5f4b67f8` (release 0.9.1.21, 2026-11-10) | GPL-3.0 | `Kavita.Models/Entities/{Library,Series,FolderPath,CollectionTag}.cs`, `Kavita.Models/Entities/ReadingLists/ReadingList.cs`, `Kavita.Services/Scanner/{DefaultParser,ProcessSeries,ScannerService}.cs` |
| **Calibre** | `kovidgoyal/calibre`, `fd2df1f93d90208867f87d70c3ef898e18e336e6` (2026-11-10) | GPL-3.0 | `src/calibre/library/{database,database2}.py`, `src/calibre/db/{schema_upgrades,adding}.py`, `src/calibre/ebooks/metadata/{meta,worker}.py`, `src/calibre/gui2/{add.py,preferences/adding.py}` |

**Método:** checkouts parciales (`--filter=blob:none --sparse`) y `git show` para los
ficheros fuera del sparse; nada ejecutado. «No lo encontré» no equivale a «no existe».
Las licencias se citan por la barrera legal de §13: **inspirarse en un patrón no es copiar
código**; no se reutiliza ningún fichero de estas referencias.

## 3. Cómo lo resuelve cada referencia

### 3.1 Sonarr

- **Declarar significado: no.** Un *root folder* es un lugar de almacenamiento. Las
  «carpetas sin mapear» son las subcarpetas de primer nivel de la raíz, a la profundidad
  que salga del formato de nombres (`RootFolderService.cs:137-175`; la profundidad se
  cuenta con los separadores de `SeriesFolderFormat`, `:154`). El formato por defecto es
  `{Series Title}` (`Organizer/NamingConfig.cs:17,30`): el nombre de la carpeta **deriva**
  de la serie, no al revés.
- **Correspondencia persistente: sí, una por serie.** `Series.Path` es una cadena
  persistida (`Tv/Series.cs:50`) y `RootFolderPath` otra (`:57`); al crear la serie se
  combinan raíz + carpeta (`AddSeriesService.cs:139-140`) y el importador de biblioteca
  existente envía la ruta tal cual (`useImportSeries.ts:53`), en sitio. Mover la serie a
  otra raíz es una operación explícita que mueve archivos (`MoveSeriesService.cs:124-132`).
  **No hay versión de la correspondencia**; la ruta es la identidad y el histórico es el log
  de eventos.
- **Path mappings no es esto.** `RemotePathMapping` relaciona `Host` + `RemotePath` con
  `LocalPath` (`RemotePathMappings/RemotePathMapping.cs:7-9`) para traducir la ruta que ve
  el cliente de descargas a la que ve Sonarr (`RemotePathMappingService.cs:128-145`). Es una
  traducción de montajes, **no una correspondencia carpeta→serie**. Confundirlas llevaría a
  modelar mal #131.
- **Precedencia:** el nombre de la carpeta es el término de búsqueda de la serie; los
  metadatos vienen de TVDB; el nombre de archivo se parsea para episodio/temporada. No hay
  metadatos embebidos a nivel de carpeta ni una tabla de precedencia visible. El importador
  solo distingue estados de importación (`ready | unmatched | existing | duplicate`,
  `importSeriesEligibility.ts:8-12`), no contradicciones de evidencia.
- **Confirmación y seguridad:** el importar es explícito por carpeta, en sitio, y
  **desactiva la búsqueda de faltantes** (`useImportSeries.ts:60`); dos carpetas que eligen
  la misma serie se marcan duplicadas y no se fusionan. Quitar un root folder solo borra la
  fila (`RootFolderService.cs:131-135`), no toca archivos.

### 3.2 Radarr

Es el mismo contrato que Sonarr, con vocabulario de película: `Movie.Path` y
`RootFolderPath` (`Movies/Movie.cs:25,29`), formato por defecto
`{Movie Title} ({Release Year})` (`Organizer/NamingConfig.cs:12,20`), profundidad de
carpetas sin mapear calculada desde ese formato (`RootFolderService.cs:143-170`), movimiento
explícito a otra raíz (`MoveMovieService.cs:101-109`) y el mismo `RemotePathMapping`
(`RemotePathMappings/RemotePathMapping.cs:7-9`). **Una película = una carpeta**, sin
declaración de autor o colección. No aporta nada que no aporte Sonarr; se cita para no
atribuir el patrón solo a Sonarr.

### 3.3 Kapowarr

- **Declarar significado: no.** `root_folders` solo guarda una ruta (`internals/db.py:383-385`);
  `volumes` guarda `root_folder` y `folder` (más `custom_folder`), es decir, **la carpeta
  del volumen** (`:400-406`). No hay tipo de carpeta ni alcance declarado.
- **Correspondencia persistente: sí, una por volumen.** `change_volume_folder` mueve los
  archivos, actualiza las rutas en la BD y borra carpetas vacías
  (`implementations/volumes.py:748-820`); `change_root_folder` hace lo propio
  (`:685-747`). Es una correspondencia fuerte y transaccional, pero **sin versión** y con
  efecto físico.
- **Library Import** propone, no importa sola: `propose_library_import` devuelve archivos
  con su sugerencia de Comic Vine (`features/library_import.py:121-155`) y solo se actúa
  sobre los `matches` que envía la persona (`:259 y ss.`). Agrupa por nombre de archivo y
  usa la carpeta solo como `prefer_folder_year=True` (`:202`), no como significado.
- **Precedencia:** nombre de archivo + año de carpeta; el emparejamiento corrobora con año
  (±1) o volumen (`implementations/matching.py:29-92`) y un título solo no basta (la ficha
  previa documenta los filtros duros de `select_best_volume_result_for_file`). No hay
  metadatos declarados por carpeta ni conflicto visible.
- **Riesgo destructivo:** si el volumen ya está en la biblioteca, el importador **mueve**
  los archivos a la carpeta del volumen asumiendo que «la probabilidad de que el
  emparejamiento sea erróneo es bastante baja» (`features/library_import.py:316-340`). Es
  exactamente el automatismo que ZascArr no debe copiar.
- **Confirmación:** explícita para el envío de matches; el movimiento posterior no pide una
  segunda confirmación.

### 3.4 Mylar3

- **Declarar significado: sí, con un fichero en la carpeta.** Un `cvinfo` en el directorio
  contiene la URL del volumen de Comic Vine. El escaneo recoge los directorios que lo
  tienen (`librarysync.py:153-154`), lo lee y **adjunta el ComicID a todo lo válido de ese
  directorio** (`:255-274`), usándolo después como `cv_cid` (`:420-421`, `:479-480`). Es una
  declaración local explícita, persistente en disco y con alcance de **ese directorio, no
  de sus subcarpetas** (cada subcarpeta necesita su propio `cvinfo`).
- **La escribe también la aplicación** si `CVINFO` está activo (`importer.py:594-596`,
  `1063-1065`), pero el valor por defecto es **desactivado** (`config.py:159`). Es decir,
  el patrón admite tanto la declaración de la persona como la generación por la app.
- **Correspondencia persistente:** además del `cvinfo`, `comics.ComicLocation` guarda la
  ruta de la serie (`__init__.py:805`) y `issues.Location` la del archivo. **No hay
  versión**; el `cvinfo` es un fichero editable a mano, sin historial, y una edición
  posterior lo pisa sin dejar rastro en la BD.
- **Precedencia:** `cvinfo` primero para el ComicID; después, si `IMP_METADATA` está activo
  (por defecto **no**, `config.py:186`), se leen metadatos embebidos del CBZ; si no, manda
  el parser de nombre. El conflicto no se muestra: la declaración de carpeta gana en
  silencio.
- **Confirmación y seguridad:** el escaneo de biblioteca **no importa**: deja todo en
  `importresults` con estado `Not Imported` (`librarysync.py:676,698`; tabla en
  `__init__.py:811`) y la persona gestiona la importación en la UI (`webserve.py:4372`). Es
  el mejor antecedente de «detectar / proponer / confirmar» de esta comparativa. El
  `cvinfo`, en cambio, **se aplica durante el escaneo sin preguntar** porque es una
  declaración previa.

### 3.5 Komga

- **Declarar significado: no en general; sí dos semánticas de carpeta por biblioteca.**
  `Library.root` es una única raíz (`domain/model/Library.kt:11`), `oneshotsDirectory` marca
  un directorio cuyos libros son one-shots (`:37`; el escáner los convierte en series
  independientes, `FileSystemScanner.kt:159-168`) y `scanDirectoryExclusions` excluye
  nombres de carpeta (`Library.kt:28`; `FileSystemScanner.kt:93`). Son **configuraciones de
  carpeta con significado especial**, no una declaración libre «esta carpeta es de autor».
- **Correspondencia persistente: derivada, no declarada.** Cada directorio se convierte en
  `Series` con `name = dir.name` y `url = dir.uri` (`FileSystemScanner.kt:99-102`); `Series`
  y `Book` guardan su URL (`Series.kt:10-11`, `Book.kt:10-11`). Las **colecciones** y
  **readlists** son agrupaciones de entidades, no de rutas: `SeriesCollection.seriesIds`
  (`SeriesCollection.kt:12`) y `ReadList.bookIds` (`ReadList.kt:14`). No hay versión.
- **Precedencia:** los metadatos de serie se agregan por **frecuencia** entre los
  proveedores (`SeriesMetadataLifecycle.kt:108-121`); el libro se crea con el título del
  nombre y el número que traiga el escaneo (`SeriesLifecycle.kt:139-145`) y luego se aplica
  el parche de ComicInfo. El
  `series.json` de Mylar se lee como sidecar de carpeta (`MylarSeriesProvider.kt:20,34-37`).
  Hay `*Locked` para que una edición humana no se pise, pero **no hay pantalla de conflicto**
  entre carpeta, nombre y metadatos.
- **Declaraciones automáticas desde metadatos:** `ComicInfo.SeriesGroup` crea colecciones
  (`ComicInfoProvider.kt:168-175`; `SeriesMetadataLifecycle.kt:60-67`) y
  `AlternateSeries`/`StoryArc` crean readlists (`ComicInfoProvider.kt:77-91`). Es una
  declaración del autor del fichero que **se aplica sola**, sin revisión; útil como
  evidencia, peligrosa como autoridad.
- **Confirmación y seguridad:** el escaneo es automático; no mueve ni renombra archivos;
  las desapariciones son *soft-delete* y la papelera solo se vacía si
  `emptyTrashAfterScan` está activo (`Library.kt:31`). Es la referencia más limpia en «no
  efectos destructivos», y la más floja en «confirmación humana».

### 3.6 Kavita

- **Declarar significado: no.** La biblioteca tiene varias `Folders` (`Library.cs:82`), un
  `LibraryType` (`:18`), patrones de exclusión (`:86`) y dos interruptores de gestión
  automática: `ManageCollections` y `ManageReadingLists` (`:36,40`). No hay «esta carpeta es
  de autor» ni «esta carpeta es una colección»: la carpeta se parsea.
- **Correspondencia persistente: derivada y estable por nombre original.** `Series.FolderPath`
  y `LowestFolderPath` guardan la carpeta más alta y la más baja que contienen sus archivos
  (`Series.cs:73,78`). `OriginalName`/`NormalizedOriginalName` se conservan aunque la
  persona cambie el nombre visible y se usan para **emparejar carpeta y serie** en escaneos
  posteriores (`Series.cs:38-43`; `ScannerService.cs:334,394-395`;
  `ProcessSeries.cs:164`). Es una correspondencia útil, pero **basada en parecido de nombre
  normalizado**, justo lo que #130 prohíbe para no extender declaraciones.
- **Precedencia:** el parser rellena desde nombres y carpetas de respaldo
  (`DefaultParser.cs:61-120`); si `enableMetadata` está activo, `UpdateFromComicInfo`
  sobrescribe volumen, número y serie (`DefaultParser.cs:33,49,126-140`). `NameLocked`
  protege el nombre editado a mano (`Series.cs:101`). No hay conflicto visible.
- **Confirmación y seguridad:** el escaneo es automático; las series que no se encuentran se
  **borran de la BD** (`ScannerService.cs:302,739-745`), no del disco (no hay borrado de
  archivos en el scanner). Las colecciones/readlists se crean solas si los interruptores
  están activos. No mueve archivos.

### 3.7 Calibre

- **Declarar significado: no.** La biblioteca es una carpeta con `metadata.db`
  (`library/database2.py:204-206`); el directorio de cada libro se **deriva** de sus
  metadatos como `Autor/Título (id)` (`database2.py:681-694`) y se guarda en `books.path`
  (`db/schema_upgrades.py:129`). La **serie es metadato**, no carpeta: tabla `series` y
  `books_series_link` (`library/database.py:399-418`). No hay forma de decir «esta carpeta
  es de autor»: Calibre es dueño del almacén y lo construye él.
- **Correspondencia persistente: una ruta por libro.** `books.path` es la ruta relativa
  estable; no hay versión ni alcance. Mover o renombrar lo hace Calibre, no un escaneo de
  una biblioteca ajena.
- **Precedencia, la más explícita de todas:** primero el patrón de nombre de archivo
  (`ebooks/metadata/meta.py:145-150`); después los metadatos embebidos, que se aplican con
  `base.smart_update(mi)` (`:155-158`); por último el OPF sidecar, que vuelve a aplicar
  `smart_update` (`:160`). El interruptor `read_file_metadata` (por defecto **true**,
  `utils/config_base.py:651`) decide si se leen los embebidos. **No hay UI de conflicto**:
  el que llega después pisa en silencio.
- **Confirmación y seguridad:** añadir es una acción explícita; la biblioteca de Calibre es
  su propio almacén y el original no se usa como biblioteca. No hay escaneo destructivo de
  una carpeta ajena. Es el contrapunto de ZascArr: aquí la biblioteca es de la app; en
  ZascArr es de la persona.

## 4. Matriz referencia × idea × veredicto

Leyenda: **A** adoptar · **D** adaptar · **M** mejorar · **C** construir sobre lo propio ·
**X** descartar. Cada celda lleva el mecanismo que la sostiene; el detalle está en §3.

| Referencia | Declarar significado de carpeta | Correspondencia persistente | Versionado e historial | Alcance explícito | Precedencia y conflicto visible | Confirmación humana | Sin efectos destructivos |
|---|---|---|---|---|---|---|---|
| **Sonarr** | **X** — root + formato de nombre; la carpeta se usa para escanear | **D** — `Series.Path` persistida, una por serie | **X** — sin versión; log de eventos | **D** — toda la carpeta de la serie; sin bandera de futuros | **X** — sin precedencia ni conflicto; solo estados de importación | **A** — importación explícita, en sitio, sin buscar faltantes | **A** — importar no mueve; quitar root no borra |
| **Radarr** | **X** — ídem, `MovieFolderFormat` | **D** — `Movie.Path` persistida | **X** | **D** — carpeta de la película | **X** | **A** | **A** |
| **Kapowarr** | **X** — root folders sin tipo | **D** — `volumes.folder` + `root_folder` | **X** — sin versión | **D** — carpeta del volumen; todos sus archivos | **X** — matching por nombre/año/volumen, sin conflicto visible | **A** — propone y la persona envía matches | **X** — mueve al importar y borra carpetas vacías; mueve si el volumen ya existía |
| **Mylar3** | **A/D** — `cvinfo` es una declaración real de carpeta; **D** para llevarla a BD versionada | **D** — `cvinfo` + `ComicLocation`, sin versión | **X** — fichero editable, sin historial | **D** — solo el directorio, no subcarpetas | **D** — `cvinfo` > embebido > nombre, pero sin conflicto visible | **A** — staging `Not Imported` | **A** — el escaneo no importa; la importación es aparte |
| **Komga** | **X/D** — no hay declaración libre; sí `oneshotsDirectory` y exclusiones como semántica de carpeta | **D** — `Series.url`/`Book.url` derivadas; colecciones y readlists son entidades, no rutas | **X** — sin versión | **D** — subárbol de la carpeta; sin bandera | **X** — agrega por frecuencia y `*Locked`; sin conflicto visible | **X** — escaneo automático, sin confirmación | **A** — solo lectura; soft-delete y papelera opcional |
| **Kavita** | **X** — sin declaración; flags de colecciones/readlists | **D** — `FolderPath`/`LowestFolderPath` + `OriginalName` normalizado | **X** — sin versión | **D** — carpeta más alta/baja; sin bandera | **X** — ComicInfo pisa al nombre; sin conflicto visible | **X** — escaneo automático | **A** — borra filas, no archivos; no mueve |
| **Calibre** | **X** — la biblioteca es un almacén propio; serie = metadato | **X/D** — `books.path` es ruta de almacén, no semántica | **X** — sin versión | **X** — una carpeta por libro | **D** — cadena nombre < embebido < OPF, pero silenciosa | **A** — añadir es explícito | **A** — no escanea una biblioteca ajena; es dueño del almacén |

**Lectura de la matriz:** ninguna referencia cubre las tres piezas juntas (declaración
local + correspondencia versionada + conflicto visible). Lo que sí está resuelto y se puede
igualar es la **persistencia de la ruta**, el **staging/confirmación** y el **no-efecto**.
El versionado y la visibilidad de conflictos son **mejora**, no copia.

## 5. Respuestas directas

### 5.1 ¿Permiten declarar el significado de una carpeta?

**Solo Mylar3 lo hace de verdad**, y solo como correspondencia a un volumen de Comic Vine
(`cvinfo`), no como «por autor» o «es una colección». Komga permite dos semánticas
especiales por biblioteca (`oneshotsDirectory`, exclusiones), pero no una declaración libre.
Sonarr, Radarr, Kapowarr, Kavita y Calibre **solo usan la carpeta para escanear o derivar**;
en Calibre la serie ni siquiera vive en la carpeta, vive en `metadata.db`. Por tanto, #130
no se puede «adoptar» de nadie: se **adapta** el patrón de Mylar (declaración local
explícita con alcance) y se **mejora** guardándola en BD, versionada y sin sidecar.

### 5.2 ¿Hay correspondencias persistentes carpeta→entidad? ¿Versionadas? ¿Con alcance?

Sí en todas, con formas distintas (ver §3): `Series.Path`/`Movie.Path`,
`volumes.folder`, `cvinfo` + `ComicLocation`, `Series.url`, `FolderPath`/`OriginalName`,
`books.path`. **Ninguna las versiona**: no hay `version_de_regla`, ni historial consultable,
ni revalidación de una propuesta antigua. El alcance es implícito y casi siempre «toda la
carpeta»: Sonarr/Radarr la carpeta de la serie/película; Kapowarr la del volumen; Mylar el
directorio exacto (no recursivo); Komga el subárbol; Kavita `FolderPath` (la más alta) y
`LowestFolderPath` (la más baja que contiene todos los archivos); Calibre la carpeta del
libro. **Ninguna tiene una
bandera explícita de «incluir descendientes» ni de «archivos futuros»**; los archivos
futuros heredan porque el siguiente escaneo vuelve a mirar la misma ruta. Eso no es un
contrato: es un efecto secundario.

### 5.3 ¿Qué precedencia aplican? ¿Conflictos visibles?

| Referencia | Orden observado | Conflicto visible |
|---|---|---|
| Mylar3 | `cvinfo` → ComicInfo embebido (si `IMP_METADATA`) → nombre | No |
| Calibre | nombre → embebido (`smart_update`) → OPF sidecar | No |
| Kavita | nombre/carpeta → ComicInfo (si `enableMetadata`) | No; `NameLocked` solo protege ediciones |
| Kapowarr | nombre + año de carpeta → match de Comic Vine con filtros duros (ficha previa) | No; solo puntuación |
| Sonarr/Radarr | nombre de carpeta como término de búsqueda → metadatos de TVDB; nombre de archivo para episodio | No; los estados `ready/unmatched/existing/duplicate` no son contradicciones |
| Komga | metadatos por frecuencia entre proveedores + `*Locked` | No |

**Ninguna muestra un conflicto de evidencia.** Todas resuelven en silencio con una regla
implícita. Ese es el hueco principal que #130 y #131 quieren cubrir.

### 5.4 ¿Quién confirma? ¿Cómo evitan efectos destructivos?

- **Sonarr/Radarr:** la persona importa carpeta a carpeta, en sitio, y se desactiva la
  búsqueda de faltantes; quitar un root no borra archivos.
- **Kapowarr:** la persona envía los matches, pero el importador **mueve** y borra carpetas
  vacías; si el volumen ya existía, mueve asumiendo bajo riesgo. Es el peor antecedente.
- **Mylar3:** el escaneo deja `Not Imported` y la persona importa; el `cvinfo` se aplica
  solo porque es una declaración previa. El escaneo no importa.
- **Komga:** escaneo automático, sin mover ni renombrar; soft-delete y papelera opcional.
- **Kavita:** escaneo automático; borra filas de series no vistas, no archivos.
- **Calibre:** añadir es explícito; la biblioteca es su almacén, no una carpeta ajena.

Para ZascArr la combinación correcta es: **declaración explícita** (Mylar), **staging y
confirmación** (Sonarr/Mylar), **escaneo sin efectos** (Komga/Kavita) y **nunca mover al
declarar** (lo contrario de Kapowarr).

### 5.5 Veredicto y modelo mínimo

| Idea | Veredicto | Qué se toma |
|---|---|---|
| Declaración de carpeta por autor/publicación/colección | **Adaptar** (Mylar `cvinfo`; Komga semánticas especiales) | Tabla en BD, no fichero; tipo y alcance explícitos; origen humano |
| Correspondencia carpeta→entidad persistente | **Adaptar** (Sonarr/Kapowarr/Kavita/Mylar) | Ruta persistida + destino existente; sin mover |
| Versionado e historial | **Mejorar** (ninguna lo tiene) | Filas inmutables con `version`, `supersedes_id` y estado; propuesta con `version_de_regla` |
| Alcance subcarpetas/futuros | **Adaptar** (Komga/Kavita) | `include_descendants` explícito; sin herencia silenciosa |
| Precedencia y conflicto visible | **Mejorar** (ninguna lo muestra) | Orden de evidencia + estados de no-propuesta; nunca elegir solo |
| Confirmación / staging | **Adoptar** (Sonarr/Mylar) | Detectar ≠ proponer ≠ confirmar; sin efectos hasta confirmar |
| Sin efectos destructivos | **Adoptar** (Sonarr/Komga/Kavita/Calibre) | Declarar/desactivar/retirar no mueve, renombra ni borra |
| Alias aprendido como autoridad | **Descartar** (hoy en ZascArr) | Alias = evidencia; #132 lo lista y le da ciclo de vida |
| Sidecar `cvinfo` | **Descartar** | Sin I/O extra, transaccional, versionado y auditable en BD |
| Mover al importar | **Descartar** (Kapowarr) | Viola «no borrar/mover sin confirmación» y la Pi |

**Modelo mínimo:** **dos tablas** (`folder_declarations` y `folder_correspondences`),
ambas **append-only por versión**, más el `local_aliases` existente con ciclo de vida
gestionado por #132. No hace falta una tabla de «carpetas» ni un fichero sidecar. Se
detalla en §8.

## 6. Supuestos de su modelo que NO valen en ZascArr

| Supuesto | Por qué no vale aquí |
|---|---|
| **Una carpeta = una serie** (Sonarr, Radarr, Komga, Kavita) | La biblioteca real tiene carpetas de autor, contenedores, arcos y franquicias; 123 archivos (8 %) están en una carpeta que no es su serie. |
| **La app deriva la carpeta del título y es dueña del almacén** (Calibre, Kapowarr) | ZascArr llega después: la biblioteca es de la persona, con varias estructuras y rutas que no se renombran. |
| **La correspondencia se puede inferir por nombre normalizado** (Kavita `NormalizedOriginalName`) | #130 prohíbe extender declaraciones por parecido de nombre. La identidad debe ser la ruta declarada, no el nombre. |
| **Mover al importar es aceptable si el match «casi seguro» acierta** (Kapowarr) | ZascArr no mueve sin confirmación y con copia verificada (ADR 0006). Declarar contexto no es organizar. |
| **El sidecar en la carpeta es suficiente** (Mylar `cvinfo`) | Un fichero no es transaccional, no tiene versión, se edita a mano y añade I/O en la Pi; además la biblioteca es de la persona y puede no querer ficheros de la app dentro. |
| **El escaneo puede crear colecciones/readlists desde metadatos sin revisión** (Komga, Kavita) | #110 pide propuestas trazables; crear una colección como efecto de escanear es una decisión no confirmada. |
| **El alias aprendido puede ejecutar** (ZascArr actual) | ADR 0008: un alias aporta evidencia, no permiso; no confirma, no vincula y no mueve. |
| **La ruta absoluta es una identidad estable** | El montaje de la biblioteca puede cambiar (`library_path` vs `host_library_dir`); la clave debe ser relativa a la raíz, normalizada, y aun así un renombrado no transfiere la declaración. |

## 7. Reglas propuestas

Estas reglas son contrato para la especificación; no son código ni migración.

### 7.1 Identidad y alcance

- **R1 — Clave de carpeta.** Una declaración se ancla a `path_key`: ruta **relativa a
  `library_path`**, normalizada (NFC, sin acentos no; sin `.`/`..`, sin barra final), y no
  al nombre visible. La ruta absoluta se deriva de `library_path` + `path_key` solo para
  mostrar. Mover o renombrar una
  carpeta **no transfiere** la declaración; la declaración pasa a `fuera_de_alcance` hasta
  que la persona la vuelva a declarar. **No se empareja por nombre parecido.**
- **R2 — Alcance explícito.** `include_descendants` decide si la declaración alcanza
  subcarpetas; por defecto **no**. Un archivo futuro solo hereda si cae dentro del alcance
  declarado. Ninguna ampliación de alcance ocurre sin una nueva versión visible.
- **R3 — Una correspondencia no amplía el alcance de su declaración.** Si la declaración no
  incluye descendientes, la correspondencia tampoco puede incluirlos. Si se necesita más
  alcance, se declara otra vez y se ve el cambio.

### 7.2 Precedencia (orden de evidencia, no de autoridad)

La precedencia **no autoriza a confirmar**. Solo decide qué evidencia se muestra primero y
cuál se usa como hipótesis. Si dos evidencias se contradicen, **no se elige**: se devuelve
el estado de no-propuesta que corresponda.

| Orden | Evidencia | Papel | Límite |
|---|---|---|---|
| 1 | Correspondencia local activa y en alcance | Propone destino y contexto | No confirma, no vincula, no mueve; no crea entidades |
| 2 | Declaración local de la carpeta (autor/publicación/colección) | Encuadra la búsqueda y el alcance | No convierte la carpeta en serie ni en publicación |
| 3 | ComicInfo embebido | Corrobora o contradice serie/número/volumen/año | No sustituye una correspondencia activa sin conflicto visible |
| 4 | Ruta y nombre de carpeta | Contexto, agrupación, año/volumen | Nunca identidad por sí sola |
| 5 | Nombre de archivo | Número/título candidato | Nunca identidad por sí solo |
| 6 | Alias aprendido o sugerencia importada | Evidencia adicional; puede explicar una candidata | Nunca ejecuta, nunca amplía alcance, nunca pisa 1–2 |

Reglas derivadas:

- **R4 — Contradicción = estado, no selección.** Correspondencia activa y ComicInfo que
  apuntan a series/ediciones distintas ⇒ `evidencia_incompatible`. Dos correspondencias
  activas con destinos distintos ⇒ `conflicto_de_correspondencias`. Ninguna precedencia
  implícita puede resolverlo; solo una regla aprobada y documentada podría, y esta ficha
  **no la propone**.
- **R5 — El alias no manda.** Un alias que contradice una declaración local se muestra como
  «alias en conflicto» y **no se aplica**. Para usarlo hace falta una acción explícita de
  #132. Un alias nunca convierte una propuesta en confirmación.
- **R6 — Sin evidencia inventada.** Una propuesta muestra las señales que la produjeron y
  las que la contradicen. No se rellena un hueco con «lo más probable».

### 7.3 Ciclo de vida y propuestas

- **R7 — Estados exactos de evaluación:** `propuesta_disponible`, `fuera_de_alcance`,
  `destino_no_disponible`, `conflicto_de_correspondencias`, `evidencia_incompatible`,
  `regla_desactualizada`. Ningún estado de no-aplicación se convierte en propuesta.
- **R8 — Versionado inmutable.** Cada cambio de contenido (destino, alcance, tipo de
  registro) o de estado (activar, desactivar, retirar) **inserta una fila nueva** con
  `version` incrementada y `supersedes_id`; no se actualiza el contenido de una fila
  histórica. La versión vigente es la de mayor `version` para esa identidad.
- **R9 — Propuesta con identidad y versión.** Toda propuesta lleva `correspondencia_id` y
  `version_de_regla`. Antes de usarla se revalida: si la versión ya no es la vigente, o la
  regla está inactiva/retirada, o el destino ya no existe ⇒ `regla_desactualizada` o
  `destino_no_disponible`; no se presenta como vigente.
- **R10 — Desactivar ≠ retirar.** Desactivar deja de generar propuestas nuevas y permite
  reactivar con una versión nueva. Retirar es terminal: no se reactiva; para volver hace
  falta una correspondencia nueva. En ambos casos se conserva el historial.
- **R11 — Sin efectos retrospectivos.** Ningún cambio de estado reasigna, revierte, mueve,
  renombra ni borra archivos, vinculaciones o series ya confirmadas. Declarar, activar,
  desactivar y retirar son operaciones de solo contexto.
- **R12 — Una sola fuente de verdad.** La resolución de contexto y la lista de #132 las
  sirve el mismo servicio; la UI no decide precedencias ni aplica reglas por su cuenta.

## 8. Modelo mínimo recomendado

### 8.1 Dos tablas, no tres

La opción mínima que **no miente** es:

1. **`folder_declarations`** — versiones inmutables del *significado* de una carpeta.
2. **`folder_correspondences`** — versiones inmutables de la *correspondencia* con un
   destino existente.

No se crea una tabla `folders`: la carpeta no es una entidad de catálogo, es una ruta
declarada. No se crea una tabla de revisiones aparte: **cada fila es una versión**. No se
toca `files`, `series` ni las rutas existentes. El `contexto_raiz` que pide #131 es
`folder_declarations.path_key`; la correspondencia lo referencia por `declaration_id` y no
lo duplica.

| `folder_declarations` | Tipo / regla |
|---|---|
| `id` | UUID, PK |
| `path_key` | Texto normalizado, relativo a `library_path`; índice |
| `kind` | Enumerado cerrado: `autor`, `publicacion`, `coleccion`, `contenedor` |
| `include_descendants` | Booleano, por defecto `false` |
| `version` | Entero ≥ 1; único con `path_key` |
| `supersedes_id` | UUID nullable, FK a la versión anterior |
| `state` | `activa`, `inactiva`, `retirada` |
| `source` | `manual` (en #130 solo manual; `importada` reservado, apagado) |
| `note` | Texto opcional para la persona; sin datos sensibles |
| `created_at` | Timestamp con zona |

Índices: único `(path_key, version)` y único parcial `(path_key) WHERE state='activa'`.
Una carpeta tiene **como máximo una declaración activa**; el histórico queda en las filas
anteriores.

| `folder_correspondences` | Tipo / regla |
|---|---|
| `id` | UUID, PK |
| `declaration_id` | UUID, FK a `folder_declarations.id`; índice |
| `destination_type` | Enumerado cerrado; el contrato decide el conjunto final. Hoy existen `serie` y `editorial` (Publisher); `coleccion` solo si se ancla a una entidad existente, nunca se inventa |
| `destination_id` | UUID del destino **existente**; se valida por servicio (no hay FK polimórfica) |
| `include_descendants` | Booleano; no puede superar el de la declaración |
| `record_type` | Texto nullable (`grapa`, `tomo`, …) si el contrato lo admite |
| `version` | Entero ≥ 1; único con `declaration_id` |
| `supersedes_id` | UUID nullable, FK a la versión anterior |
| `state` | `activa`, `inactiva`, `retirada` |
| `source` | `manual`; `importada` solo si se abre explícitamente |
| `evidence` | JSONB con lo que la persona vio (señales, ruta, año); sin secretos |
| `created_at` | Timestamp con zona |

Índices: único `(declaration_id, version)`; único parcial
`(declaration_id, destination_type, destination_id) WHERE state='activa'`; índice
`(declaration_id, state)`. **Se permiten varias correspondencias activas con destinos
distintos** para que el conflicto sea representable; no se permite duplicar la misma
correspondencia activa.

### 8.2 `local_aliases` no es una tercera fuente de verdad

El alias sigue siendo `pattern_norm → series_id`, pero #132 debe añadirle, como mínimo,
`scope_path` (nullable; `NULL` = legado global), `state` (`propuesto|activo|inactivo|retirado`),
`origin` (`aprendido|importado|manual`) y las marcas de tiempo. Mientras eso no exista, #130
y #131 **leen** el alias como evidencia y no lo escriben. Un alias **no se convierte** en
declaración ni al revés: son unidades distintas (nombre de archivo vs carpeta).

### 8.3 Por qué no las alternativas más simples

| Alternativa | Por qué no |
|---|---|
| **Solo ampliar `local_aliases`** (ámbito + estado) | Un alias es un patrón de nombre→serie; no puede expresar «esta carpeta es de autor» ni un alcance de subcarpetas. Sería el mismo mecanismo con dos semánticas incompatibles. |
| **Un sidecar por carpeta** (estilo `cvinfo`) | Añade I/O en la Pi, no es transaccional, no tiene versión ni historial, se edita a mano y mete ficheros de la app en una biblioteca que es de la persona. |
| **Una sola tabla con `destination_id` nullable** | Una declaración puede existir sin destino y un contexto puede tener varias correspondencias en conflicto; mezclarlas impide representar el conflicto y el ciclo de vida independiente. |
| **Tabla + tabla de eventos separada** | Tres tablas y dos lecturas para lo mismo; el append-only por versión ya da historial completo sin eventos aparte. |
| **Recalcular el contexto en cada escaneo sin persistir** | No hay nada que revisar, desactivar o retirar; #130/#131 quedarían sin sustancia. Sirve para la rebanada 1, no para M7. |

## 9. Matriz ponderada (nivel 2)

Criterios y pesos **por defecto** de `benchmark-referencias.md` (no acordados con el PO en
esta sesión; se muestran para que quien decida pueda mover hasta tres, justificándolo).
Escala 1–5; el total es la suma ponderada sobre 500.

| Opción | Encaje coleccionista 25 | Coste Pi 20 | Seguridad/legal/licencia 20 | Cobertura requisito 15 | Adaptabilidad stack 10 | Mantenimiento 5 | Lock-in 5 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Dos tablas append-only + alias con ciclo de vida** | 4 | 5 | 5 | 5 | 4 | 4 | 5 | **460 / 500 (92 %)** |
| Solo ampliar `local_aliases` | 2 | 5 | 4 | 2 | 5 | 4 | 4 | 350 / 500 (70 %) |
| Sidecar por carpeta | 3 | 4 | 3 | 3 | 3 | 2 | 2 | 310 / 500 (62 %) |
| Recalcular contexto sin persistir | 2 | 5 | 5 | 1 | 5 | 4 | 5 | 360 / 500 (72 %) |

**Por qué gana la primera:** cubre el requisito completo (declaración + correspondencia +
versión + estados) sin coste de escaneo (son pocas filas indexadas por ruta), sin licencia
nueva, sin sidecar y sin tocar los archivos. Su coste real es de interfaz y de contrato, no
de Pi. Las otras tres fallan en cobertura o en auditabilidad.

## 10. IGUALAR / MEJORAR

### IGUALAR (mínimo competitivo, antes de decir que se «mejora»)

1. **Ruta persistida por entidad** (Sonarr/Radarr/Kapowarr/Komga/Kavita/Calibre).
2. **Staging separado de la biblioteca** y confirmación explícita (Sonarr, Mylar3).
3. **Escaneo sin efectos**: no mover, no renombrar, no borrar (Komga, Kavita, Calibre).
4. **Alcance visible** de la carpeta y de lo que abarca (Kavita `FolderPath`/`LowestFolderPath`;
   Sonarr profundidad por formato).
5. **Estados explícitos de no-aplicación**, no un «no encontrado» genérico (Sonarr
   `ready/unmatched/existing/duplicate`; Mylar `Not Imported`).

### MEJORAR (con evidencia de la debilidad)

1. **Versionado**: ninguna de las siete versiona la regla; un cambio de `cvinfo` o de
   `Series.Path` no deja historial consultable. ZascArr debe poder decir «esta propuesta se
   hizo con la versión 3 y ya no es la vigente».
2. **Conflicto visible**: ninguna muestra dos evidencias contradictorias; todas resuelven
   en silencio (Calibre `smart_update`, Komga `mostFrequent`, Kavita `UpdateFromComicInfo`).
   ZascArr debe devolver `evidencia_incompatible` y explicarlo en español.
3. **Identidad sin parecido de nombre**: Kavita empareja por `NormalizedOriginalName`
   (`Series.cs:38-43`), exactamente lo que #130 prohíbe. ZascArr debe anclar a ruta y
   exigir redeclaración tras un renombrado.
4. **Alias con consentimiento**: el alias actual de ZascArr ejecuta y mueve
   (`matcher.py:315-320`); ninguna referencia tiene un «alias aprendido» con este poder.
   #132 debe dejarlo como sugerencia y separar la activación automática.
5. **Declaración sin creación ni vinculación**: ninguna referencia permite declarar una
   carpeta y quedarse en una propuesta. Mylar asocia el directorio a un volumen y
   Komga/Kavita crean series al escanear. ZascArr debe declarar contexto **sin crear series,
   sin vincular archivos y sin mover**.

## 11. Casos que la especificación debe cubrir (no son pruebas implementadas)

- Declarar `Comics/Carlos Giménez` como `autor`, sin descendientes; comprobar que agrupa
  contexto y **no** propone una serie por sí sola.
- Declarar por publicación una carpeta con subcarpetas y `include_descendants=true`;
  comprobar que un archivo futuro dentro del alcance hereda y uno fuera no.
- Declarar una carpeta, renombrarla en disco y reescanear: la declaración **no** se
  transfiere por parecido de nombre; se muestra fuera de alcance.
- Crear una correspondencia a una serie existente; comprobar que la propuesta lleva
  `correspondencia_id` y `version_de_regla`, y que no crea ni vincula nada.
- Cambiar el destino y versionar: una propuesta de la versión anterior debe quedar
  `regla_desactualizada`.
- Tener dos correspondencias activas con destinos distintos: `conflicto_de_correspondencias`,
  con las dos identificadas, sin elegir.
- Poner un ComicInfo que contradice la correspondencia: `evidencia_incompatible`, con las
  dos evidencias visibles.
- Borrar la serie destino: `destino_no_disponible`.
- Desactivar: deja de proponer; reactivar con versión nueva. Retirar: no reactiva y
  conserva historial.
- Un alias que contradice una declaración: se muestra el conflicto y **no** se aplica.
- Ninguna de las operaciones anteriores mueve, renombra, borra ni crea archivos, series o
  vinculaciones.

## 12. NOT RUN

- No se ha ejecutado Sonarr, Radarr, Kapowarr, Mylar3, Komga, Kavita ni Calibre; todo es
  lectura de código en los commits de §2.
- No se ha ejecutado ZascArr, ni sus pruebas, ni una migración, ni una consulta a Postgres.
- No se ha medido el coste en la Pi de ninguna de las opciones; la estimación de §9 es de
  diseño (filas indexadas, sin I/O de escaneo), no una medición.
- No se ha verificado el comportamiento de renombrado/movido de Komga ni de Calibre más
  allá de lo citado; se marcan como no concluyentes.
- No se han leído las interfaces de usuario de las referencias; se ha leído su contrato de
  datos y la ruta de código que decide. «No lo encontré» no equivale a «no existe».

## 13. Caducidad y barrera legal

- **Caduca:** 2027-01-09 (~60 días desde la lectura), o antes si cambia alguna referencia,
  el PO reformula #110 o se fusiona una implementación que invalide la comparación.
- **Licencias:** Sonarr, Radarr, Kapowarr, Mylar3, Kavita y Calibre son **GPL-3.0**; Komga
  es **MIT**. Esta ficha **no copia código ni ficheros**: solo describe contratos y patrones.
  Antes de reutilizar una implementación concreta hay que revisar el fichero, sus avisos y
  las obligaciones de su licencia (CLAUDE.md §13), y la licencia propia del repo
  (`LICENSE`). La licencia de ZascArr no se ve afectada por leer estas referencias; sí lo
  haría copiar código GPL sin cumplir sus obligaciones.
