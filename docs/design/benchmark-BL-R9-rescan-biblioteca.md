# Benchmark — Reescanear la tebeoteca (BL-R9): a demanda y de forma periódica

> Ficha §13 (nivel 2) según `docs/design/benchmark-referencias.md`. Historia: **BL-R9** (propuesta;
> la crea el PO). Lectura: **2026-11-06** (rol SCOUT.bench); `main` contrastado: `f58274e`.
> Verificación del coordinador: citas de Kapowarr (`kapowarr/repo`, `c191dda`) y de Komga
> (`komga/repo`, `25c67d1`, v1.29.2) comprobadas sobre el código local el 2026-11-06.
> La ficha propone; **decide el PO**.

## 1. Historia / problema observado

BL-R9 — Como coleccionista, quiero que ZascArr reescanee mi tebeoteca — a demanda o periódicamente — y
actualice la biblioteca (archivos nuevos, movidos, sustituidos y desaparecidos) y añada a revisar lo que
no identifique, para que la biblioteca esté al día sin que yo tenga que acordarme de pulsar botones.

**Caso real (anonimizado):** el coleccionista deja tebeos nuevos en la carpeta de la biblioteca (~1.500
registrados) o los reorganiza entre subcarpetas; espera que ZascArr los vea y los coloque en su serie, o
en «Por revisar» si no está seguro. Hoy no ocurre: el ciclo automático solo mira las descargas y la
disponibilidad de lo registrado; registrar lo nuevo exige Auditoría → «Buscar archivos nuevos» → revisar
→ confirmar (todo a mano).

**Comportamiento actual (verificado en el código vigente `f58274e`):**

- Bucle `main.py::_import_loop` (`import_interval_minutes=15`) → `services/comprobacion_disco.py::ejecutar_automatico`
  → `services/ciclo_importador.py` → `Importer.scan_and_import` (`services/importer.py:474`): recorre SOLO las
  descargas; después `_comprobar_biblioteca` (`importer.py:626`) revisa únicamente la EXISTENCIA de los `File`
  registrados (`is_missing`/`missing_since`, reapariciones; guardarraíles B7/#231). NO registra archivos nuevos
  de la biblioteca y NO compara el contenido de las rutas registradas.
- Registro incremental (#326/BL-R8): manual (`GET /ui/auditoria/nuevos` → `POST /ui/auditoria/registrar-nuevos`,
  `web/auditoria.py:145,154`), solo rutas SIN fila, con confirmación de la huella de lo visto; reenlaza movidos
  (`library_adopter.py:543 _reenlazar_fila`); nunca marca desaparecidos; un test exige que SOLO la pantalla lo
  lance (sin automatismo).
- «Comprobar el disco» (#232/BL-R3a): disparo manual del mismo ciclo del importador; no registra archivos nuevos
  de la biblioteca.
- Límite documentado (`docs/design/registro-incremental-326.md` §7): «Un contenido distinto en una ruta ya
  registrada (archivo sustituido) no se detecta».
- No existe ninguna cadencia periódica de rescan de la biblioteca.

**Resultado deseado:** una operación «Reescanear la biblioteca», a demanda (botón) y con cadencia configurable
(p. ej. diaria; el valor por defecto lo decide el PO con esta ficha), que recorre la biblioteca una vez por
ejecución (con exclusión frente al ciclo del importador y al registro incremental — cerrojos ya existentes),
sin consultar fuentes externas, sin mover ni renombrar ningún fichero, y decide por archivo: ruta nueva →
registrar (identificado con confianza → biblioteca; si no → «Por revisar»); ruta registrada cuyo contenido
cambió (por `stat`) → re-triar y actualizar la fila, o devolverla a revisión; ruta registrada desaparecida →
baja/reaparición (B7); movido → reenlace (existente). Informe honesto por categorías.

## 2. Datos reales y medición de partida

Biblioteca de ~1.500 registros; el coleccionista añade tebeos y reorganiza carpetas; hoy el alta de lo nuevo
exige 4 pasos manuales. Sin medición propia ejecutada (regla del rol: no ejecuto el producto): queda por medir
antes de implementar (a) la duración de un `stat`-walk completo de la biblioteca real en la Pi, (b) cuántas
rutas sin fila hay hoy (referencia histórica: #297 encontró 252). NOT RUN en §10.

## 3. Referencias consultadas (URL, versión/commit; leídas 2026-11-06)

1. **Kodi** — código: xbmc/xbmc, rama `master`, commit `32574fb2dd270a4e7aa3f7e6020bfdd2c78b0609`:
   `system/settings/settings.xml`, `xbmc/application/Application.cpp`, `xbmc/video/VideoInfoScanner.cpp`.
   Wiki oficial (Updating_or_removing_videos; Settings/Media/Videos): HTTP 403 Cloudflare en todos los
   intentos → NOT RUN (§10).
2. **Sonarr** — Sonarr/Sonarr, rama `develop`, commit `c018578e4b79ee048575c02d7a8aa2b929e4b837` (2026-11-03,
   GPL-3.0): `DiskScanService.cs`, `MediaFileTableCleanupService.cs`, `DownloadedEpisodesImportService.cs`,
   `Commands/RescanSeriesCommand.cs`, `Tv/RefreshSeriesService.cs`, `Tv/ShouldRefreshSeries.cs`,
   `Jobs/TaskManager.cs`.
3. **Kapowarr** — checkout LOCAL `kapowarr/repo`, commit `c191dda` (v1.3.2, GPL-3.0):
   `backend/features/tasks.py`, `backend/implementations/volumes.py`,
   `backend/implementations/file_matching.py`, `backend/features/library_import.py`.
4. **Plex** — solo documentación funcional (servidor propietario):
   <https://support.plex.tv/articles/200289306-scanning-vs-refreshing-a-library/> (últ. mod. 2019-07-31) y
   <https://support.plex.tv/articles/200289526-library/> (últ. mod. 2025-05-04); el artículo antiguo
   «Periodically scan my library automatically» da hoy 404. Ejemplo oficial plexinc/tmdb-example-provider,
   commit `3348a89009bb418e083646fbe1360f544774bf71` (ISC): es un Metadata Provider (Match/Metadata), no toca escaneo.
5. **Komga** — checkout LOCAL `komga/repo`, commit `25c67d1` (`gradle.properties`: `version=1.29.2`; checkout
   SPARSE — el backend Kotlin se leyó del árbol del commit vía `git show`): `interfaces/api/rest/LibraryController.kt`,
   `application/scheduler/LibraryScanScheduler.kt`, `interfaces/scheduler/PeriodicScannerController.kt`,
   `domain/model/Library.kt`, `domain/service/FileSystemScanner.kt`, `domain/service/LibraryContentLifecycle.kt`,
   `application/tasks/{Task,TaskProcessor}.kt`.
6. **Kavita** — Kareadita/Kavita, rama `develop`, commit `9e177701c359090fa62e2e90aba571567c6cc680`
   (2026-11-01, release 0.9.1.18, GPL-3.0): `Kavita.Services/TaskScheduler.cs`,
   `Kavita.Services/Scanner/{ScannerService,FolderWatchService,KeptFiles,ProcessSeries,ScanJobQueue}.cs`,
   `Kavita.Server/Controllers/LibraryController.cs`.
7. **Jellyfin** (opcional, sí aportaba) — jellyfin/jellyfin, `master` (GPL-2.0):
   `Emby.Server.Implementations/IO/LibraryMonitor.cs`,
   `Emby.Server.Implementations/ScheduledTasks/Tasks/RefreshMediaLibraryTask.cs`.

## 4. Cómo lo resuelve cada una

- **Kodi** (demostrado por código): scan bajo demanda por fuente; al arrancar, si `videolibrary.updateonstartup`
  (default false, `settings.xml:1052-1056`) → `CApplication::UpdateLibraries()` lanza
  `CVideoLibraryQueue::ScanLibrary` (`Application.cpp:2593-2608`). Detección de cambios: `VideoInfoScanner.cpp`
  calcula un HASH DEL LISTADO de cada carpeta (nombres + mtime de sus entradas, «fast hash» con digest de
  mtimes, `GetPathHash`, ~437-577); si coincide con lo guardado → «hash matches - skipping» (~534-537); si
  cambió → rescan. No hay watchdog ni scan periódico en el core: ambos son addons. Los desaparecidos NO se
  eliminan en el scan: «Clean library» es una acción explícita aparte (`CleanDatabase`).
- **Sonarr** (demostrado por código): `RescanSeriesCommand` (`SeriesId` opcional: una serie o todas) →
  `DiskScanService.Scan(series)`: guardas de salto (root folder inexistente/vacío → `SeriesScanSkippedEvent`,
  no error); lista ficheros de vídeo bajo la carpeta de la serie con exclusiones; `MediaFileTableCleanupService.Clean`
  BORRA la fila del episodio cuyo fichero ya no está (`DeleteMediaFileReason.MissingFromDisk`); los ficheros sin
  fila se deciden con el parser y se importan los identificados — los no identificados quedan EN DISCO sin tocar
  (solo visibles en Manual Import); el contenido cambiado se detecta SOLO por tamaño (`file.Size == fileSize`;
  si difiere → actualiza y re-analiza media info; sin hash ni mtime). Cadencia: `RefreshSeriesCommand` cada 12 h
  (`Jobs/TaskManager.cs`) refresca metadatos y al final puede rescanear el disco según `RescanAfterRefresh`
  (Always/AfterManual/Never; el automático se salta el rescan por defecto); `ShouldRefreshSeries` salta series
  (30 días sin sync, TBA, <6 h desde el último sync, serie acabada con último capítulo >30 días). Fichero
  bloqueado → `FileIsLockedResult` «try again later».
- **Kapowarr** (demostrado por código): la tarea periódica es `update_all` (`tasks.py:792-833`, cron
  `0 * * * *` cada hora, `tasks.py:30-36`) → `refresh_and_scan` (`volumes.py:1356`): con `allow_skipping` salta
  volúmenes actualizados en las últimas 24 h cuyo nº de issues coincide con Comic Vine (y fuerza si >30 días);
  luego `scan_files` (`file_matching.py:30`) por carpeta de volumen: matching SOLO por nombre de fichero (sin
  hash ni mtime), borra bindings viejos, y `FilesDB.delete_unmatched_files()` BORRA filas huérfanas. Movidos:
  la identidad es el path → un fichero movido pierde su enlace. Cambios de contenido: no se detectan. Sin
  identificar: no se crea nada persistente; hay pantalla de match manual (`get_file_matching`/`set_file_matching`
  con `forced_match`). Cola de tareas FIFO de hilos, UNA sola tarea a la vez, con historial y `next_run`
  persistidos (`tasks.py:95-241`). El «mass import» (`library_import.py:121`) es manual con propuestas de Comic
  Vine (límite 20 carpetas) y mueve/renombra ficheros.
- **Plex** (todo «documentado»): Scan = «check for new or changed content and get metadata for it if needed»
  (nuevos, borrados, renombrados, movidos); Refresh = re-obtener metadatos (art. 200289306). Disparadores:
  «Scan my library automatically» por eventos del SO — Plex documenta que NO funciona con shares SMB/NFS/AFP;
  «Scan my library periodically» con intervalos 15 min/30 min/h/2 h/6 h/12 h/diario, anclados al arranque;
  «Run a partial scan when changes are detected» (avanzado); «Empty trash automatically after every scan»
  (desactivado → el item desaparecido se queda con un indicador, no se borra); «Run scanner tasks at a lower
  priority» recomendado para NAS ARM; «Allow media deletion» (opcional). El ejemplo oficial (ISC) aporta el
  patrón de match: respuesta única «mejor coincidencia» vs `manual: 1` que devuelve varios candidatos.
- **Komga** (demostrado por código; el más completo): `POST /api/v1/libraries/{libraryId}/scan?deep=` (solo
  admin, 202 ACCEPTED) → `taskEmitter.scanLibrary(id, deep, HIGHEST_PRIORITY)`. Periódico:
  `LibraryScanScheduler.kt:36-51` registra una tarea fixed-rate POR biblioteca con intervalos HOURLY/EVERY_6H/
  EVERY_12H/DAILY/WEEKLY/DISABLED; default `ScanInterval.EVERY_6H` (`Library.kt:24`); `scanOnStartup` (default
  false). Escáner: `FileSystemScanner.kt` — `Files.walkFileTree` completo (FOLLOW_LINKS), salta ocultos y
  exclusiones; cada libro = nombre + `fileLastModified = max(creationTime, lastModifiedTime)` + `fileSize`;
  fallo de lectura → `visitFileFailed` loguea y SKIP_SUBTREE. Aplicación: `LibraryContentLifecycle.kt` —
  series/libros no vistos → soft-delete (papelera, `emptyTrashAfterScan` opcional); libro con `fileLastModified`
  distinto: si tamaño coincide y hay hash guardado → recalcula hash; hash igual → solo actualiza stats; hash
  distinto → resetea `Media.Status.OUTDATED` y limpia hash; tamaño distinto → OUTDATED (líneas 170-203); libros
  nuevos → alta directa (la carpeta ES la serie; sin cola de revisión); movidos → `tryRestoreSeries`/
  `tryRestoreBooks` emparejan con las bajas por tamaño+hash y restauran metadatos/progreso (271-365);
  mitigación de caches NFS/SMB: `seriesUrlWithDeletedBooks` y `scanForceModifiedTime`. Fallo:
  `DirectoryNotFoundException` → `unavailableDate` en la biblioteca y el task falla (87-93). Concurrencia:
  cola de tareas persistida en BD; `uniqueId SCAN_LIBRARY_{id}_DEEP_{deep}` hace que un segundo scan igual NO
  se duplique; `TaskProcessor` con prioridades 8/6/4/2/0. `hashFiles` default true (`Library.kt:33`).
- **Kavita** (demostrado por código, GPL-3.0): `POST scan` con `force` solo admin →
  `EnqueueScanLibrary`. Periódico: Hangfire RecurringJob «Scan Library» con cron CONFIGURABLE
  (`ServerSettingKey.TaskScan`: «disabled», «daily», «weekly» o cron; si el cron es inválido → `Cron.Daily`
  por defecto — `TaskScheduler.cs:174-187`). OJO: `EnqueueScanLibraries` encola con `runAt = ahora +
  ScanHourDelay` (3 h, `:567,595`). Watcher: `FolderWatchService.cs` elige watch nativo o POLLING según el
  montaje detectado (montaje de red → polling; fallo del watch → degradación a polling persistida); debounce
  `WatcherQuietTime=30 s` sin cambios para correr y `WatcherScanCap=10 min` de techo, con push-back de
  peticiones repetidas (`:106-110, 455-560`); `ScanRequestLock` serializa el encolado (dedupe). Scan:
  `ScannerService.cs` — `ScanLibraryFolders` (641-700) → `ScanFiles` → `ProcessParsedSeries` (tally honesto:
  SeriesAdded/Removed/Failed, ChaptersAdded/Updated/Removed) → `RemoveSeriesNotFound` (las series no vistas se
  BORRAN, línea 745); ficheros que no parsean → no crean entidades (NO hay cola «por revisar»); carpeta
  inaccesible/desmontada → `RootFoldersInaccessible` y se aborta el scan (`ShouldScanSeries`, 449-470). Estado
  persistido: `library.ScanInfo = {Forced|Normal: scanRun(AtUtc, DurationMs)}` + `UpdateLastScanned` (664-668).
  Optimización de coste: `KeptFiles.cs` — carpetas «unchanged» se saltan y sus entidades se conservan.
- **Jellyfin** (demostrado por código, opcional): `LibraryMonitor.cs` — `FileSystemWatcher` recursivo por
  carpeta de librería (solo si `EnableRealtimeMonitor`), debounce agrupando eventos con `FileRefresher`, e
  ignora cambios propios con `_tempIgnoredPaths` y retardo de 45 s; error del watcher → log y dispose (sin
  fallback a polling). Periódico: `RefreshMediaLibraryTask.cs` — «Refresh Library» con disparador por defecto
  cada 12 h → `ValidateMediaLibraryInternal` (scan completo).

## 5. Supuestos de su modelo que NO valen en ZascArr

- **Kodi:** cliente de escritorio local, SQLite embebido, carpeta fuente = «la serie» con un scraper por
  fuente; el usuario es quien dispara la UI. El hash de listado depende de poder re-listar cada carpeta
  barato — en la Pi hay que pagarlo con cuidado.
- **Sonarr:** la identidad es SERIE + temporada + episodio con numeración rígida; el episodio se decide con un
  parser de nombres de escena (sin huella de contenido ni ambigüedad editorial); puede mover/renombrar/borrar
  ficheros como parte del producto; BORRA filas de episodios desaparecidos; asume servidor con CPU sobrante.
- **Kapowarr:** cada volumen cuelga de un ID de Comic Vine (sin fuentes españolas); matching solo por nombre de
  fichero; puede mover/renombrar/borrar en la biblioteca; borra filas huérfanas; pool de procesos en paralelo
  (inviable en Pi); sin confirmación humana.
- **Plex:** producto propietario con análisis pesados (thumbnails, marcadores) que ZascArr no hará jamás; el
  «automatic scan» depende de eventos del SO que Plex mismo descarta para SMB/NFS; el «empty trash» borra
  basura. Solo se toma el CONTRATO documentado; no hay código verificable.
- **Komga:** la carpeta ES la serie (una carpeta por serie, libros sueltos dentro); el libro se empareja por
  URL de ruta; el cambio de contenido se resuelve con «media status OUTDATED» porque no hay triaje editorial;
  papelera + soft-delete; una JVM con pool de tareas configurable. ZascArr: un solo directorio de biblioteca
  con jerarquía libre, identidad editorial entre publicaciones, «Por revisar» como cola humana, y nada de borrar.
- **Kavita:** el parseo crea la serie desde el nombre de carpeta (sin confirmación); lo no parseado se ignora
  (no existe cola de no identificados); el scan programado se retrasa 3 h por diseño; borra series no vistas;
  watcher con degradación a polling (complejidad que en un contenedor de la Pi con volumen montado añade
  riesgo sin pedirla el PO).
- **Jellyfin:** modelo de «virtual folders» con agregados; watch en tiempo real con FileRefresher; solo aporta
  el patrón de cadencia 12 h.

## 6. Resultado por idea (adoptar / adaptar / mejorar / construir sobre lo propio / descartar)

| Idea | Resultado | Motivo |
|---|---|---|
| Scan con dedupe en cola y prioridad para el manual (Komga `uniqueId` + prioridades) | **Adoptar** | En ZascArr ya están el cerrojo `(326,2)` de `comprobacion_disco.py:76` y el estado en memoria `EstadoCicloDisco`: se reutilizan; el contrato «segundo disparo no duplica, se informa honestamente» se toma tal cual, sin código ajeno. |
| Guardas de salto con evento, no error (Sonarr `SeriesScanSkippedEvent`) | **Adoptar** | Coincide con `RAIZ_INACCESIBLE`/`RAIZ_VACIA` de `_comprobar_biblioteca`: el rescan informa categoría «no revisado» en vez de fallar. |
| Separar scan de disco de refresh de metadatos (Sonarr `RescanAfterRefresh`) | **Adoptar** | El rescan de ZascArr NO consulta fuentes (requisito); el patrón de separación de disparadores se toma como contrato. |
| Prioridad baja del scanner en hardware ARM (Plex, documentado) | **Adoptar** | El rescan en la Pi es un solo hilo, stat-first, sin hash salvo que aporte. |
| Cadencia configurable con default (Komga 6 h, Sonarr/Jellyfin 12 h, Plex lista, Kavita cron con fallback a diario) | **Adaptar** | ZascArr tiene UNA biblioteca → un solo ajuste de cadencia (p. ej. off/diaria/semanal), con fallback a un default seguro si el valor es inválido (patrón Kavita). Default lo decide el PO; recomendación: diario. |
| Detección de cambio por stat + hash condicional (Komga `LibraryContentLifecycle.kt:170-203`) | **Adaptar** | Guardar por ruta registrada `(size, mtime)` persistidos; si no cambiaron → skip (no se abre el CBZ); si cambiaron → re-triar con `_triage_and_match`; hash condicional solo cuando aporte certeza. Cierra el límite documentado de #326 §7 y supera a Sonarr (solo tamaño) y a Kapowarr (nada). |
| Skip de carpetas quietas (Kodi `GetPathHash`, Kavita `KeptFiles`) | **Adaptar** | En ZascArr, en lugar de hash de listado, el skip es por stat por ruta (más barato y alineado con el modelo `File`); el informe declara qué se revisó y qué no. |
| Fichero bloqueado/cambiado a mitad de lectura → omitir con causa (Sonarr `FileIsLockedResult`) | **Adaptar** | ZascArr ya tiene `ArchivoCambiado` en `LibraryAdopter.adopt`; añadir la variante «en uso» como omisión temporal honesta. |
| Estado persistido del scan e informe por categorías (Komga tally, Kavita `ScanInfo`/`UpdateLastScanned`) | **Adaptar** | ZascArr ya persiste `ImportRun`; el rescan guarda su propio run (disparador, revisados, nuevos, reenlazados, re-triados, desaparecidos/reaparecidos, a revisión, omitidos con causa, no revisados). |
| El núcleo entero (LibraryAdopter, `_reenlazar_fila`, `_triage_and_match`, cerrojos, B7) | **Construir sobre lo propio** | Ya resuelto y testeado en #326/B7/#232; las referencias solo aportan vocabulario y contrato. Sobrecoste a registrar: persistir el stat por ruta (columna(s) en `File` + migración one-shot) y el loop periódico nuevo. |
| Cola de revisión persistente para lo no identificado | **Mejorar** | Evidencia: Sonarr los deja en disco (solo Manual Import), Kavita no crea entidades, Kapowarr los borra de la vista, Komga los mete como serie por nombre de carpeta. ZascArr ya tiene «Por revisar»; el rescan la alimenta. Criterio comprobable: tras un rescan, todo fichero no identificado aparece en `/ui/pendientes` sin pasos manuales. |
| Baja no destructiva con reaparición | **Mejorar** | Evidencia: Sonarr BORRA la fila (`Delete(MissingFromDisk)`), Kapowarr borra huérfanas, Kavita borra la serie; Komga soft-delete. ZascArr marca `is_missing` y revierte sin borrar (B7): iguala a Komga y supera a los otros tres. |
| Watchdog/inotify en la v1 | **Descartar** | Plex documenta que no funciona en SMB/NFS; Kavita necesita polling-degradación y debounce 30 s/10 min; Jellyfin mantiene un FileRefresher por evento. Coste y fragilidad en contenedor sobre la Pi sin que el PO lo pida; queda registrado como mejora futura si el PO quiere inmediatez. |
| Mover/renombrar ficheros en el scan | **Descartar** | Requisito e invariante: sin mover ni renombrar. |
| Borrar filas/series de desaparecidos, papelera/empty-trash (Sonarr/Kapowarr/Kavita/Komga/Plex) | **Descartar** | Invariante de ZascArr: no borrar. |
| Pool de procesos por volumen (Kapowarr) | **Descartar** | RAM de la Pi. |
| Retraso de 3 h del scan programado (Kavita) | **Descartar** | Sorprende al coleccionista; el manual corre ya o informa «ocupado». |
| Crear la serie desde el nombre de carpeta (Komga/Kavita) | **Descartar** | ZascArr tiene identidad editorial con confirmación. |
| Match por nombre de fichero sin huella (Kapowarr) | **Descartar** | Ya superado por `_triage_and_match`. |

## 7. Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi)

1. **No mentir:** informe por categorías con «no revisado» explícito cuando la raíz sea inaccesible o un
   recorrido quede incompleto (patrón `RAIZ_INACCESIBLE` de #231); la pantalla dice qué se revisó y qué no.
2. **No borrar:** nunca se borra una fila ni un fichero; el desaparecido se marca (`is_missing`/`missing_since`,
   B7) y reaparece al volver; el movido se reenlaza, no se duplica; nada de papelera automática.
3. **Confirmación:** el modo manual mantiene la garantía U21 («no se mueve ni se renombra nada») junto a la
   acción; el registro periódico SIN confirmación humana es decisión del PO (precedente de #326: solo la
   pantalla lanza el registro — la spec decide explícitamente si el modo periódico hereda la confirmación o
   registra con confianza y manda el resto a revisión; recomendación del scout: periódico registra solo lo
   identificado con confianza y el resto a «Por revisar», nunca alta ciega).
4. **Coste Pi:** un solo worker; walk/stat en `asyncio.to_thread`; sin abrir CBZ de rutas sin cambios; sin
   fuentes externas; exclusión con el ciclo del importador vía cerrojo `(326,2)` y con el registro vía
   `(326,1)`; cadencia por defecto conservadora.
5. **Sin dependencias nuevas, sin cola externa (ADR-0011):** estado en memoria + `ImportRun` persistido (como #232).
6. **El test de #326** («solo la pantalla lanza el registro») sigue en verde o se ajusta por decisión explícita
   del PO, nunca en silencio.

## 8. Casos de prueba antes de implementar (semilla EARS)

1. Ruta nueva identificada con confianza → fila creada y vinculada a su serie; no identificada → «Por revisar»
   visible sin pasos manuales.
2. Ruta nueva ya existente en la BD → no se duplica (idempotencia de `adopt`).
3. Ruta registrada cuyo contenido cambió (otro tebeo) → se re-tría; la fila se actualiza o pasa a revisión; sin
   romper la fila.
4. Cambio que conserva tamaño y mtime (límite #326 §7) → comportamiento declarado y testeado (skip o hash
   condicional, lo que decida el PO).
5. Desaparecido → `is_missing`/`missing_since`; reaparece → revierte; la fila NUNCA se borra.
6. Movido → reenlace de la fila por huella (contrato `_reenlazar_fila`); ambigüedad (varias filas coinciden) →
   se informa y no se reenlaza (contrato #326).
7. Manual durante el ciclo automático del importador → exclusión mutua `(326,2)` con «ocupado» honesto; y con el
   registro incremental en marcha `(326,1)`.
8. Segundo disparo manual/periódico con un rescan en curso → no se encola un duplicado; el estado es visible.
9. Raíz inaccesible o vacía → categoría «no revisado», no excepción genérica; desaparición masiva (disco
   desmontado) → guardarraíl de umbral existente.
10. Archivo que cambia mientras se lee → omitido con causa (ya existe `ArchivoCambiado`).
11. Coste: ~1.500 rutas sin cambios → solo stats, sin abrir un solo CBZ (assert sobre lecturas de contenido).
12. Sin red: el rescan no llama a Comic Vine/Tebeosfera/AniList/GCD (mock de clientes con 0 llamadas).
13. Dos rescans seguidos sin cambios → segundo informe «sin cambios» (idempotente y honesto).
14. El informe del rescan se persiste en `ImportRun` con el mismo contrato de lectura que #231/#232.

## 9. Matriz ponderada (criterios y pesos acordados antes de comparar)

Pesos (por defecto, acordados con el coordinador): encaje con el flujo del Coleccionista **25** · coste en Pi
**20** · seguridad, legalidad y licencia **20** · cobertura del requisito core **15** · adaptabilidad al stack
y al modelo de datos **10** · mantenimiento de la referencia **5** · lock-in y coste de salida **5**.
Escala 1–5; máximo 500.

| Referencia | Encaje 25 | Coste Pi 20 | Seg/lic 20 | Cobertura 15 | Adaptab. 10 | Manten. 5 | Lock-in 5 | Total |
|---|---|---|---|---|---|---|---|---|
| Sonarr | 4 | 4 | 5 | 4 | 4 | 5 | 4 | **425** |
| Komga | 4 | 4 | 4 | 5 | 4 | 5 | 4 | **420** |
| Kavita | 4 | 3 | 4 | 4 | 4 | 5 | 4 | **385** |
| Jellyfin | 3 | 3 | 4 | 3 | 3 | 5 | 4 | **335** |
| Plex | 3 | 4 | 3 | 3 | 3 | 3 | 2 | **315** |
| Kapowarr | 2 | 3 | 4 | 3 | 3 | 4 | 4 | **305** |
| Kodi | 2 | 3 | 4 | 3 | 2 | 5 | 4 | **300** |

Justificación breve: Sonarr, contrato de operación más alineado (comandos, tareas, guardas, skip) y misma
familia de producto; Komga, la cobertura más completa del requisito exacto (cambio por mtime+hash condicional,
restore de movidos por hash, dedupe de scan) pero JVM y modelo «carpeta=serie»; Kavita, cron configurable y
watcher con degradación, penalizada por complejidad y retraso de 3 h; Jellyfin y Plex aportan cadencia/prioridad
pero no el modelo de tebeo; Kapowarr penalizada por modelo ComicVine-obligatorio, borrados y pool de procesos;
Kodi, cliente local de otra unidad, útil solo por el skip por hash de listado y la separación scan/clean.

## 10. IGUALAR / MEJORAR (con evidencia)

**IGUALAR (mínimo competitivo):** (1) botón a demanda + cadencia configurable con default — todos lo tienen
(Komga 6 h, Sonarr refresh 12 h, Jellyfin 12 h, Plex intervalos, Kavita cron). (2) Dedupe/no solapamiento de
scans — Komga `uniqueId` + prioridad manual 8; ZascArr ya lo tiene en `(326,2)`/`EstadoCicloDisco`. (3) Informe
por categorías — tally de Komga/Kavita. (4) Desaparecido marcado sin borrar — Plex «empty trash» off +
indicador; Komga soft-delete; ZascArr `is_missing`. (5) Skip de lo no cambiado — Kodi hash de listado, Kavita
`KeptFiles`, Komga mtime; ZascArr: stat por ruta. (6) Detección de contenido cambiado — Komga mtime+hash
condicional; ZascArr debe igualarla (hoy es su límite documentado, #326 §7).

**MEJORAR (solo con la evidencia citada):** (1) cola «Por revisar» persistente alimentada por el scan
(Sonarr/Kapowarr/Kavita/Komga no la tienen como tal). (2) Baja/reaparición sin borrado de fila (Sonarr borra
fila, Kapowarr borra huérfanos, Kavita borra serie). (3) Re-triaje editorial del contenido sustituido (Komga
solo resetea a OUTDATED, no re-decide serie; Sonarr solo re-analiza media info por tamaño).

## 11. Decisión final / ADR

**DECIDE EL PO.** Recomendación de SCOUT.bench: construir sobre lo propio (LibraryAdopter + triaje + cerrojos +
B7) adoptando el contrato de Komga (dedupe de scan en curso, stat+mtime/size con hash condicional, informe
tally, prioridad manual) y la cadencia configurable con default diario (patrón Sonarr/Plex/Jellyfin/Kavita).
Sin watchdog en la v1. **No exige ADR:** no cambia arquitectura (reutiliza `ImportRun`, cerrojos consultivos y
un loop propio como `_import_loop`); el único cambio de modelo es persistir `(size, mtime)` por ruta en `File`
(migración one-shot) y un ajuste de cadencia. Si el PO elige algo distinto en confirmación/cadencia, se refleja
en la spec, no en un ADR.

## 12. NOT RUN

- kodi.wiki: HTTP 403 (Cloudflare) en los intentos de 2026-11-06. Mismo precedente que el 403 de Plex
  registrado por el PO; Kodi se apoya en el código (settings.xml, Application.cpp, VideoInfoScanner.cpp).
- Plex: servidor propietario — nada ejecutado; TODAS las afirmaciones de Plex son «documentado». La URL
  histórica «Periodically scan my library automatically» da 404; se usan 200289306 y 200289526.
- Nada se EJECUTÓ: Sonarr/Komga/Kavita/Jellyfin/Kodi leídos en código, sin servidores levantados; los defaults
  se leen de constantes, no de instalaciones vivas.
- Komga local: checkout sparse (solo komga-webui materializado); el backend se leyó del árbol del commit
  `25c67d1` con `git show` (verificado `version=1.29.2`); no compilado ni ejecutado.
- Medición de partida sobre la Pi con la biblioteca real: pendiente (duración del stat-walk; nº actual de rutas
  sin fila).
- Kavita: sin verificar el significado completo de `FolderWatchMode` en la UI ni el endpoint REST exacto de
  «Scan Library» de la UI (solo el controller del servidor).

## 13. Caducidad

**~60 días desde la lectura: ≈ 2027-01-05**, o antes si cambia la historia, la referencia o una versión mayor
de Komga/Kavita/Sonarr altera los mecanismos citados.

## 14. Barrera legal

Sonarr GPL-3.0, Kapowarr GPL-3.0, Kavita GPL-3.0, Jellyfin GPL-2.0, Kodi GPL-2.0, Plex propietario (solo
patrones documentados), tmdb-example-provider ISC. **Solo se extraen patrones; cero código copiado.** Antes de
reutilizar una implementación concreta, revisar el fichero de origen y sus avisos (CLAUDE.md §13).
