# Benchmark nivel 2 — #156 BL-A5 «Repartir tradiciones entre discos»

> Ficha de **diseño**, insumo para la especificación. No es una aprobación, no
> implementa y no decide por el PO. Nivel 2 porque toca modelo de datos,
> ficheros, escaneo, seguridad de rutas y migración de una instalación real.
>
> - **Fecha:** 2026-11-14
> - **`main` contrastado:** `acb82a40d00eb847a1fcd3719e2d3006af9a4546`
>   (worktree `.squad/wt-156bench`, rama `docs/156-benchmark`).
> - **Rol:** SCOUT.bench.
> - **Historia:** `docs/BACKLOG.md:49` (A5, P2, L): «N carpetas-raíz; cada una
>   asignada a una o varias tradiciones; el importer escribe en la raíz que le
>   toca a esa tradición».
> - **DoR actual:** vacía. Faltan valor/alcance, contrato, riesgos,
>   migración y estimación; esta ficha los pone sobre la mesa, no los cierra.
> - **Caducidad:** 2027-01-13 (~60 días), o antes si cambia el modelo de
>   ficheros, el montaje de Compose, la migración o alguna referencia.

---

## 1. Problema local fijado (ZascArr, `acb82a40`)

### 1.1 Qué pide la historia, en concreto

Un coleccionista con el disco casi lleno quiere **repartir tradiciones entre
discos**. La unidad de decisión no es el archivo suelto ni la serie: es la
**tradición editorial** de la serie (`ComicTradition`). El importer debe escribir
cada archivo nuevo en la raíz que corresponda a su tradición, sin que el
catálogo, el escaneo, las portadas, la disponibilidad o la auditoría empiecen a
mentir sobre dónde está cada cosa.

### 1.2 Lo que hay hoy: una sola raíz, en todos los niveles

| Pieza | Comportamiento actual | Evidencia |
|---|---|---|
| Configuración | **Una** `library_path` (`/media/library` por defecto) y **un** `host_library_dir` que solo se usa para mostrar la ruta del host | `src/zascarr/config.py:188,194-196` |
| Montaje | **Un** bind mount `${HOST_LIBRARY_DIR}:/media/library`; la app recibe `LIBRARY_PATH=/media/library` | `docker-compose.yml:137,142,171-175` |
| Instalador | Pregunta **una** «carpeta de tebeos ya organizados» y comprueba que no se solape con descargas/aMule; no hay lista de raíces | `bootstrap.sh:319-329,341-372,397` |
| Comprobación A9 | Compara **la biblioteca** contra cada cola; no compara raíces de biblioteca entre sí porque no existen | `scripts/_rutas.sh:87-165,170-230` |
| Ajustes en caliente | `library_path` **no** está en `OVERRIDABLE_FIELDS`; D11 solo cubre integraciones/secretos, no rutas de infraestructura | `src/zascarr/services/runtime_settings.py:38-75,202-216` |
| Importador | `self._library = s.library_path`; construye `library / {carpeta tradición} / {Serie (Año)} / …`; `_Unsorted` cuelga de la misma raíz | `services/importer.py:490,741,860,914-957` |
| Escaneo del importador | `scan_and_import` recorre **solo las colas de descarga**; la biblioteca la recorren adopter/rescan/auditoría, no el ciclo de importación | `services/importer.py:497-532` |
| Modelo de archivo | `File.file_path` es una ruta absoluta única; **no hay** `root_id`, `library_id` ni equivalente | `models/__init__.py:786` |
| Asignación manual | `ReviewService` y `AsignacionService` reciben **una** biblioteca y usan `build_library_path`/`safe_move`; `AsignacionService` **también escribe** (copia, verifica, publica y retira el origen) | `services/review.py:127,314`; `services/asignacion.py:1-35,295-300,377,745` |
| Registro/adopción | `LibraryAdopter` recorre **una** raíz, calcula el prefijo de **una** raíz y cuenta «registrados sin fichero» bajo ese prefijo | `services/library_adopter.py:290,304,339-357,391,499` |
| Rescan | Delega en el mismo `LibraryAdopter`; por tanto hereda la raíz única | `services/rescan_biblioteca.py:9-15,51-55` |
| Auditoría | Recorre `get_settings().library_path`; los informes y la cuarentena viven bajo esa raíz | `services/library_audit.py:167,207,308`; `web/auditoria.py:395-399,437` |
| Disponibilidad | Lee la comprobación de **una** raíz; el guardarraíl de desaparición masiva se calcula sobre **todos** los `File`, no por raíz | `services/importer.py:649-668`; limitación ya escrita en `docs/BACKLOG.md:124` |
| Recuperación de movidos | El importer reenlaza una fila desaparecida si vuelve a ver el mismo contenido (`_reenlazar`); el adopter/rescan hace lo mismo al encontrar una ruta nueva. La búsqueda de coincidencias es global sobre `File`; con N raíces, el adopter actual solo recorre una y no puede ver el movimiento a otra | `services/importer.py:320-430,723-724,832-884`; `services/library_adopter.py:689,977-1000` |
| Covers | Caché global en `/config/covers`; extrae del `File.file_path`; no depende de una raíz concreta | `config.py:210`; `utils/cover.py` |
| Conversión/ETQ | Originales y diario bajo `library_path/.zascarr` | `services/conversion.py:206-210` |
| Duplicados | Cuarentena bajo `library_path/.zascarr/apartados`; rutas relativas a **esa** raíz | `services/apartado_duplicados.py:141,222` |
| Vinculación | Comprueba que una ruta está bajo **la** biblioteca y que no es `_Unsorted` | `services/vinculacion_en_sitio.py:41-45`; `services/vinculacion_previa.py:391`; `services/revision_carpetas.py:302-310` |
| Carpetas compartidas | Lista de **raíces conocidas** (biblioteca/descargas/incoming) para el guardián de archivos compartidos; no es una raíz de biblioteca ni un mapeo de tradiciones | `config.py:205`; `web/ajustes.py:545-555`; `services/compartidos.py:102-130` |
| Exportación Kavita | `export_path` es otra raíz, pero la validación de solapamiento solo conoce `library_path`, descargas, incoming y compartidas | `services/exportacion_kavita.py:85-110` |
| Ruta visible | Traduce **un** prefijo de contenedor a **un** prefijo de host | `utils/ruta_visible.py:16-28` |

**Conclusión:** no existe «media raíz» ni una tabla de raíces. Hay una raíz
única asumida en el importador, el registro, el rescan, la auditoría, la
cuarentena, la conversión, la vinculación y la traducción de rutas. La
tradición solo decide **una carpeta dentro de esa raíz** (`TRADITION_MAP`),
no el disco.

### 1.3 Qué garantías de A3 hay que conservar

`utils/fs.py` es la base de «no dañar la colección»:

- `safe_move` **no sobreescribe**: si el destino existe, usa un nombre único
  (`:96-128`).
- Entre sistemas de ficheros distintos, **copia a un temporal en el destino,
  comprueba el tamaño y solo entonces** sustituye/retira el original
  (`:129-170`); el original no desaparece si la copia falla.
- `_same_filesystem` usa `st_dev`, pero también cae al camino de copia si
  `os.replace` devuelve `EXDEV` — importante con bind mounts del mismo
  dispositivo (`:91-94,141-145`).
- El importador llama `safe_move_async` y registra el destino real
  (`importer.py:759-776`). La asignación manual (`AsignacionService`) es más
  estricta (SHA-256, publicación sin reemplazo), pero **no es el camino que
  usa hoy el importador** (`asignacion.py:1-35`).
- La comprobación de espacio (`comprobar_espacio`) existe antes de copiar;
  A5 debe hacerla **por raíz de destino**, no una vez para una raíz global.
- La desaparición masiva se frena a nivel global (`importer.py:668-690`); con
  N raíces, una raíz desmontada no puede marcar como ausentes los archivos de
  las demás. La propia limitación está documentada en `docs/BACKLOG.md:124`.

---

## 2. Referencias consultadas (contrato, no solo UI)

| Referencia | Versión / commit | Qué se leyó |
|---|---|---|
| **Sonarr** | `c018578e4b79ee048575c02d7a8aa2b929e4b837` (v4.0.20.3014) | `RootFolderService`, `RootFolderController`, `SeriesPathBuilder`, `EpisodeFileMovingService`, `MoveSeriesService`, `RootFolderCheck`, `DiskSpaceService` |
| **Radarr** | `af772b051ac27a0615c7f8b7f78622b6dc183be0` (develop; release v6.4.4.10685) | Misma familia: `RootFolderService`, `MovieService`, `MoveMovieService`, `Movie.RootFolderPath` |
| **Kapowarr** | `c191dda6617929c81292483a8cc07f631111dae2` (v1.3.2) | `backend/implementations/root_folders.py`, `volumes.py`, `file_matching.py`, `definitions.py` |
| **Mylar3** | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (v0.8.3) | `mylar/config.py`, `mylar/moveit.py`, `mylar/PostProcessor.py`, `mylar/helpers.py` |
| **Komga** | `25c67d14eb748dd3fb9f6612c099959a077fc850` (develop, 2026-10-30) | `Library.kt`, `LibraryLifecycle.kt`, `LibraryContentLifecycle.kt`, `FileSystemScanner.kt`, `DuplicateFiles.vue` |

Enlaces: [Sonarr](https://github.com/Sonarr/Sonarr/tree/c018578e4b79ee048575c02d7a8aa2b929e4b837),
[Radarr](https://github.com/Radarr/Radarr/tree/af772b051ac27a0615c7f8b7f78622b6dc183be0),
[Kapowarr](https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2),
[Mylar3](https://github.com/mylar3/mylar3/tree/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316),
[Komga](https://github.com/gotson/komga/tree/25c67d14eb748dd3fb9f6612c099959a077fc850).

### 2.1 Sonarr / Radarr: raíz por serie, move opcional

- **La raíz es una entidad** (`RootFolder`: `Path`, `Accessible`, `IsEmpty`,
  `FreeSpace`, `TotalSpace`, `UnmappedFolders`) y se gestiona por API
  (`RootFolderController`), no solo por archivo de configuración.
  Evidencia: `src/NzbDrone.Core/RootFolders/RootFolder.cs:5-15`;
  `src/Sonarr.Api.V5/RootFolders/RootFolderController.cs:33-71`.
- **Cada serie guarda su raíz**: `Series.RootFolderPath` y `Series.Path`;
  la ruta de importación se construye con `Path.Combine(RootFolderPath,
  GetSeriesFolder(...))`. Evidencia: `Series.cs:50-57`;
  `SeriesPathBuilder.cs:25-45`; el importador de episodios usa
  `BuildFilePath(... series ...)` (`EpisodeFileMovingService.cs:84-91`).
  Radarr replica el patrón con `Movie.RootFolderPath` (`Movie.cs:25-29`) y
  `MoveMovieService`.
- **Validación al añadir una raíz:** existe, es carpeta, no es duplicado
  exacto, es escribible. Evidencia: `RootFolderService.cs:90-125`;
  `RootFolderController.cs:34-43`. Hay un `RootFolderAncestorValidator` en el
  árbol, pero el alta de raíz **no** lo incluye y `Add` solo compara igualdad
  exacta; **no se encontró** una prohibición general de raíces anidadas en esa
  ruta. La resolución «mejor raíz» es por **prefijo más largo**
  (`RootFolderService.cs:188-206`), es decir, una heurística, no un mapeo
  explícito.
- **Cambiar la raíz de una serie:** la API acepta `moveFiles` (query) y el
  servicio puede mover la carpeta de la serie; si no se pide, actualiza la
  ruta y deja los archivos donde están. Evidencia:
  `SeriesController.cs:202-213`; `SeriesService.cs:311-348`;
  `MoveSeriesService.cs:38-125`; el modal ofrece «Move Files» / «Don't Move
  Files» (`frontend/src/Series/MoveSeries/MoveSeriesModal.tsx:35-75`).
- **Disco lleno/espacio:** cada raíz calcula `FreeSpace`/`TotalSpace`
  (`RootFolderService.cs:190-210`) y hay un servicio de espacio por disco
  (`DiskSpaceService.cs:36-96`). La copia puede fallar y la importación
  captura el error; no hay reserva atómica de espacio.
- **Raíz ausente:** es un health check, no se recrea ni se confunde con
  «todo borrado» (`RootFolderCheck.cs:25-80`). El importador falla con
  `RootFolderNotFoundException` y deja el archivo en origen
  (`ImportApprovedEpisodes.cs:57-82,172-178`).
- **Lo que no cubre:** no hay tradición; la asignación es por serie/película.
  No hay una regla «esta raíz es para manga»; la raíz es solo un prefijo.

### 2.2 Kapowarr: raíz persistida por volumen, colisiones y estado de disco

- **Raíces como tabla**: `root_folders(id, folder)`; cada `VolumeData` guarda
  `root_folder` y `folder` (`definitions.py:900-904`). Al añadir un volumen se
  exige un `root_folder_id` válido (`volumes.py:1078-1190`); la carpeta se
  deriva de `RootFolders()[volume.root_folder]` (`naming.py:237-259`).
- **No permite solapamientos**: `RootFolders.add` rechaza padre/hijo de otra
  raíz **o de la carpeta de descargas** con `are_folders_colliding`
  (`backend/base/files.py:167-205`; `root_folders.py:150-195`). Renombrar una
  raíz migra los volúmenes y mueve archivos (`root_folders.py:197-253`).
- **Raíz ausente:** `__gather_extra_data` **crea la carpeta** si no existe
  (`root_folders.py:37-44`). Esto es un anti-patrón para ZascArr: un disco
  desmontado no debe convertirse en una carpeta vacía en el disco del sistema.
- **Disco lleno:** estado `ROOT_FOLDER_ALMOST_FULL` (>90 %) y
  `ROOT_FOLDER_FULL` (>99 %), calculado por raíz (`root_folders.py:46-82`;
  `definitions.py:286-287`). No sustituye la comprobación de espacio de una
  copia concreta.
- **Cambiar de raíz un volumen:** `Volume.change_root_folder` **mueve** los
  archivos y actualiza rutas de BD (`volumes.py:685-738`). Es automático y sin
  confirmación; no es el contrato que ZascArr debe copiar sin más (A3).
- **Lo que no cubre:** la asignación es por volumen, no por tradición; una
  raíz puede tener muchos volúmenes, pero no hay «esta raíz es la de tebeo
  español»; no hay migración de una instalación de una raíz a N raíces.

### 2.3 Mylar3: destino único de escritura y «múltiples» solo de lectura

- `DESTINATION_DIR` es el **destino por defecto de escritura**.
  `MULTIPLE_DEST_DIRS` es una **única** ruta secundaria; el propio comentario
  de configuración dice: «Nothing will ever get written to these dirs - just
  for scanning, unless it's metatagging/renaming» (`mylar/config.py:51-52`).
- El postprocesador mueve a `comlocation` (la ubicación de la serie) con
  `shutil.move` (`mylar/moveit.py:1-80`); no hay `root_id` persistido ni
  validación de solapamiento entre raíces; el espacio se comprueba en el
  postprocesado (`PostProcessor.py:3254-3290`).
- Los «secondary_folders» se usan para **escanear** una copia secundaria
  (`helpers.py:2792-2802`), no para decidir el destino de una importación
  nueva.
- **Conclusión:** Mylar3 **no** resuelve A5; sirve como evidencia del
  anti-patrón «varias carpetas de escaneo, una sola de escritura».

### 2.4 Komga: varias bibliotecas, una raíz por biblioteca, sin mover

- **Modelo:** cada `Library` tiene **un** `root: URL` (`Library.kt:11-40`).
  Hay N bibliotecas, no N raíces dentro de una biblioteca.
- **Validación:** al añadir/actualizar, la raíz debe existir, ser carpeta, no
  repetir nombre y **no ser padre/hijo de otra biblioteca**
  (`LibraryLifecycle.kt:33-85`; el chequeo `startsWith` es por componentes de
  `Path`). Cambiar la raíz dispara un **rescan**, no un movimiento
  (`:75-83`).
- **Escaneo:** `LibraryContentLifecycle.scanRootFolder` escanea **su** raíz y
  marca/soft-delete lo que ya no está en ella (`:55-130`). El escáner sigue
  symlinks (`FileSystemScanner.kt:88-110`, `FOLLOW_LINKS`); es un detalle de
  seguridad a no copiar sin más.
- **Duplicados:** hay una vista de archivos duplicados agrupada por
  `fileHash` (`komga-webui/src/views/DuplicateFiles.vue:1-100`), con acción de
  borrar; **no mueve** archivos ni decide una raíz de destino.
- **Lo que no cubre:** no escribe ni importa; no asigna una raíz por tradición;
  su unidad es la biblioteca completa. Sirve para el contrato de validación y
  aislamiento, no para el flujo del importer.

**No se usa Suwayomi** en esta ficha: su modelo de capítulos/fuentes no aporta
una decisión sobre raíces de biblioteca y habría sido relleno. Tampoco se
estudian apps de la lista que no están en el encargo.

---

## 3. Matriz ponderada de ideas (nivel 2)

Se usan **los pesos por defecto** de `docs/design/benchmark-referencias.md`,
sin moverlos ni cambiarlos después de ver las referencias:

`encaje con el flujo del Coleccionista 25 · coste en Pi 20 · seguridad,
legalidad y licencia 20 · cobertura del requisito core 15 · adaptabilidad al
stack/modelo 10 · mantenimiento de la referencia 5 · lock-in/coste de salida 5`.

Cada idea se puntúa de **1 a 5**; el total es
`Σ(peso × puntuación) / 5`, de 0 a 100. La puntuación es una **propuesta de
lectura**, no una decisión.

| # | Idea (referencia) | Flujo 25 | Pi 20 | Seg 20 | Core 15 | Stack 10 | Mant. 5 | Lock-in 5 | Total | Resultado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| I1 | Entidad **raíz** persistida y `File.root_id` (Kapowarr + propio) | 5 | 4 | 5 | 5 | 5 | 4 | 4 | **94** | **Construir sobre lo propio** |
| I2 | Mapeo **tradición → una raíz**; una raíz puede servir varias tradiciones (propio; Sonarr/Kapowarr asignan por entidad) | 5 | 4 | 4 | 5 | 5 | 4 | 5 | **91** | **Construir sobre lo propio** |
| I3 | Validar raíz: existe, escribible, **sin solapamientos**, sin recrearla si falta (Komga + Kapowarr + Sonarr) | 5 | 5 | 5 | 5 | 5 | 4 | 4 | **98** | **Adoptar** (contrato), implementación propia |
| I4 | Importar a la raíz resuelta, manteniendo `{tradición}/{Serie (Año)}` y `_Unsorted` en raíz por defecto (propio) | 5 | 5 | 5 | 5 | 5 | 4 | 4 | **98** | **Construir sobre lo propio** |
| I5 | Cambiar la configuración **no mueve** lo ya registrado; mover sería una acción explícita posterior (adaptar Sonarr, no Kapowarr) | 4 | 4 | 3 | 5 | 4 | 4 | 4 | **79** | **Adaptar** |
| I6 | Escanear **todas** las raíces y agrupar desaparición/estado **por raíz** (propio B7 + Komga por biblioteca) | 4 | 3 | 4 | 5 | 4 | 4 | 3 | **78** | **Construir + Mejorar** |
| I7 | Rutas relativas a **su** raíz y traducción host/contenedor por raíz (propio `ruta_visible`) | 4 | 3 | 4 | 5 | 4 | 4 | 3 | **78** | **Construir sobre lo propio** |
| I8 | Raíces en BD + Ajustes para raíces **ya montadas**; mount nuevo sigue siendo `.env`/Compose (Sonarr/Kapowarr) | 4 | 5 | 5 | 4 | 4 | 4 | 4 | **88** | **Adaptar** |
| I9 | Espacio libre, disco lleno y salud **por raíz** (Sonarr + Kapowarr) | 4 | 4 | 4 | 4 | 4 | 3 | 4 | **79** | **Adaptar** |
| I10 | Cuarentena de duplicados **por raíz** y operaciones con `root_id` (propio) | 3 | 4 | 3 | 3 | 4 | 3 | 4 | **67** | **Construir sobre lo propio** |
| I11 | `MULTIPLE_DEST_DIRS` solo de lectura, una sola escritura (Mylar3) | 2 | 3 | 2 | 1 | 2 | 2 | 3 | **42** | **Descartar** |
| I12 | Raíces anidadas y «mejor prefijo» (Sonarr) | 2 | 3 | 2 | 3 | 3 | 3 | 3 | **51** | **Descartar** |
| I13 | Cambiar raíz y mover archivos automáticamente (Kapowarr) | 2 | 2 | 2 | 3 | 2 | 3 | 3 | **45** | **Descartar** (solo move explícito) |
| I14 | Derivar la raíz solo del prefijo de `file_path`, sin `root_id` | 3 | 3 | 3 | 2 | 3 | 2 | 3 | **56** | **Descartar** |
| I15 | Bibliotecas independientes tipo Komga (una raíz por biblioteca, sin mapping) | 3 | 4 | 4 | 2 | 3 | 3 | 2 | **64** | **Descartar como flujo; adaptar validación** |

**Lectura:** las ideas que ganan son las que **persisten la raíz y el mapeo**
(I1/I2), **validan** antes de escribir (I3) y **mantienen la ruta canónica**
(I4). Lo más caro es I6 (escaneo por raíz) y la UI/operación (I8/I9); son
justo lo que impide vender A5 como un cambio de una tarde. Las ideas de
Mylar, el auto-move de Kapowarr y las raíces anidadas de Sonarr quedan fuera
porque contradicen «no engañar al sistema» o A3.

---

## 4. Contrato propuesto y preguntas para el PO

> **Nada de esto está aprobado.** Es el mínimo que, leído contra el código,
> evita los fallos previsibles. El PO decide; la especificación concreta.

### 4.1 Contrato mínimo (propuesta)

1. **Raíz de biblioteca = entidad persistida**, no solo una variable:
   `id`, `nombre`, `path` (ruta del contenedor), `host_path` (solo mostrar),
   `enabled`, `tradiciones` (conjunto). `path` único y normalizado.
2. **Una tradición resuelve a exactamente una raíz.** Una raíz puede servir
   varias tradiciones. Si una tradición no tiene raíz, **no se inventa una**:
   el archivo no se mueve y el informe lo dice con una causa accionable.
3. **El archivo guarda su raíz**: `File.root_id` (nullable para rutas
   externas/no gestionadas) además de `file_path` absoluto. La ruta relativa
   se calcula contra **su** raíz, nunca contra una raíz global.
4. **Las raíces no se solapan**: ni iguales, ni padre/hijo por componentes, ni
   el mismo inodo por bind mount; tampoco con descargas, incoming, export,
   `.zascarr` ni la raíz del sistema. Cada `path` debe estar **dentro de una
   raíz de montaje autorizada** por el operador, no en cualquier ruta del
   contenedor. Se valida antes de guardar.
5. **Raíz ausente = error de operación, no carpeta nueva.** No se crea; las
   importaciones de esa raíz se omiten y las demás siguen; el estado lo dice.
6. **El importer elige raíz antes de construir la ruta** y conserva el layout
   actual bajo ella: `{raíz}/{carpeta de tradición}/{Serie (Año)}/archivo`.
   `_Unsorted` va a la raíz por defecto (configurable), no a una raíz al azar.
7. **Cambiar el mapeo o la ruta de una raíz no mueve archivos existentes.**
   Solo afecta a importaciones nuevas. Mover lo ya registrado es una acción
   explícita, separada y con confirmación; no se incluye en el MVP.
8. **Escaneo y lectura con el mismo contrato:** `raices()` devuelve todas las
   raíces habilitadas; cada `File` se agrupa por `root_id`; la desaparición
   masiva se calcula **por raíz**; una raíz caída no marca ausentes las demás;
   la disponibilidad informa del estado por raíz, no de un «todo bien» global.
9. **Rutas visibles por raíz:** `ruta_visible(ruta, root)` usa el `host_path`
   de esa raíz; si no hay mapeo, muestra la ruta del contenedor. Los informes
   de auditoría y la cuarentena indican de qué raíz son.
10. **Covers:** la caché sigue siendo global (`/config/covers`); solo cambia
    el `file_path` del que se extrae. Una raíz caída deja la portada de sus
    archivos no disponible, pero **no** se busca en otra raíz ni se muestra
    una portada ajena; el estado de la raíz lo explica.
11. **Migración compatible:** la instalación de una raíz se convierte en una
    fila de raíz con todas las tradiciones; todos los `File` que cuelgan de
    ella se rellenan con `root_id`; no se mueve ningún archivo. La
    configuración antigua sigue siendo el valor por defecto mientras no se
    cambie.

### 4.2 Las preguntas que el PO tiene que cerrar

| # | Pregunta | Opciones | Recomendación provisional (no aprobada) |
|---|---|---|---|
| 1 | **¿Dónde vive la configuración?** | (a) `.env`/Compose estático; (b) Ajustes en caliente (D11); (c) tabla BD; (d) mezcla | **Mezcla:** `.env`/Compose autoriza **qué está montado** (frontera de seguridad); BD guarda raíz, nombre, host_path y tradiciones; Ajustes gestiona **solo raíces ya montadas**. Añadir un disco nuevo sigue exigiendo montaje + reinicio, y se dice claramente. No Docker socket. |
| 2 | **¿Mapeo tradición→raíz o también raíz→varias tradiciones?** | (a) 1:1; (b) N tradiciones por raíz; (c) N raíces por tradición con prioridad | **Una raíz puede tener N tradiciones; cada tradición una sola raíz.** Varias raíces para la misma tradición es ambigüedad silenciosa; si el PO la quiere, debe ser una lista ordenada y explícita, no un fallback implícito. |
| 3 | **¿Qué pasa si una tradición no tiene raíz?** | (a) root por defecto; (b) `_Unsorted`; (c) no mover y avisar; (d) elegir la raíz con más espacio | **No mover y avisar** (fallo cerrado). Un default silencioso llena el disco equivocado; elegir por espacio rompe la promesa «cada tradición a su disco». `other`/desconocida puede tener una raíz explícita «sin clasificar». |
| 4 | **¿Se mueven los ficheros ya registrados al cambiar la configuración?** | (a) sí automático; (b) preguntar y mover; (c) no mover; (d) comando aparte | **No en A5.** La historia solo dice «el importer escribe en la raíz que le toca»; mover millones de bytes en una Pi es otra historia, con su propio dry-run/confirmación/rollback. Se documenta que los archivos antiguos se quedan donde están y que su `root_id` no cambia. |
| 5 | **¿Un contrato único de escaneo o uno por consumidor?** | (a) cada servicio itera raíces; (b) un `RaicesService`/iterador común | **Un iterador único** (`iterar_raices`, `raiz_de(ruta)`, `relative_to_root`) usado por adopter, rescan, auditoría, disponibilidad, cuarentena y vinculación. Si cada uno hace su `rglob`, las diferencias de comportamiento serán bugs. |
| 6 | **¿Ruta persistida o derivada?** | (a) solo derivar por prefijo; (b) `root_id` en `File`; (c) ambas | **`root_id` persistido + ruta absoluta**; la derivación por prefijo es solo compatibilidad de migración. Sin `root_id`, una raíz retirada o dos prefijos solapados hacen ambigua la pertenencia y la auditoría no puede distinguir «archivo de raíz A» de «archivo huérfano». |
| 7 | **¿Alcance y esfuerzo?** | (a) L completo; (b) MVP sin UI; (c) partir en historias | **L completo, tres cortes acumulativos** (§7); el «MVP sin UI» puede servir para validar el contrato, pero **no cierra A5** porque el coleccionista no puede añadir el segundo disco. |

### 4.3 Migración de datos (propuesta, no aprobada)

- Nueva tabla `library_roots` (id, nombre, path del contenedor, host_path,
  enabled, timestamps) y tabla/JSONB de `tradiciones` por raíz, o una columna
  `traditions` con validación de enum. Una raíz por fila; el path único.
- Nueva columna `files.root_id` FK nullable (`ON DELETE RESTRICT`): nulo para
  rutas que no cuelgan de ninguna raíz (p. ej. vinculación externa), nunca
  para las que sí.
- Migración de datos: insertar **una** raíz con `path = settings.library_path`
  y todas las tradiciones; rellenar `files.root_id` con esa raíz para los
  `file_path` que cuelgan de su prefijo por componentes; los que no, quedan
  nulos y se muestran como «fuera de raíz».
- `host_library_dir` actual se copia como `host_path` de la raíz 1; las
  nuevas raíces tendrán su propio `host_path`.
- Rollback: la migración no mueve archivos; revertir la tabla/columna deja el
  disco intacto. Las rutas de `File.file_path` no se reescriben.
- Prueba de que no se engaña: después de migrar, un `File` de la raíz 1 debe
  seguir mostrando la misma ruta visible, el mismo `relative_to` y el mismo
  estado `is_missing`; ninguna consulta debe cambiar de resultado.

### 4.4 Flujo del importer (propuesta)

1. `triage`/`matcher` decide la serie, como hoy.
2. Si no hay serie fiable: `_Unsorted` en la **raíz por defecto**; se registra
   `root_id` de esa raíz.
3. Si hay serie: `tradicion = series.tradition`; `raiz = resolver(tradicion)`.
   Si no hay raíz: no se mueve; se registra un aviso `sin_raiz` y el archivo
   queda en la cola de entrada (no se pierde, no se inventa destino).
4. Se construye `build_library_path(raiz.path, series, ...)`, se llama
   `safe_move_async` y se guarda `File.root_id = raiz.id`.
5. El informe dice la raíz por su **nombre**, no solo la ruta; el log no
   incluye datos sensibles.
6. Un fallo de una raíz no detiene el ciclo de las demás; el informe lo
   distingue por raíz.

### 4.5 Anti-patrones para UX/operación

| Anti-patrón | Por qué | Evidencia |
|---|---|---|
| Varias carpetas de **escaneo** y una sola de **escritura** | El coleccionista cree que reparte y el importer sigue llenando el disco de siempre | Mylar3 `MULTIPLE_DEST_DIRS` (`config.py:51-52`, `helpers.py:2792-2802`) |
| **Crear** la raíz que falta al comprobar si está montada | Un USB desmontado se convierte en una carpeta vacía en el disco del sistema; luego «desaparecen» archivos de verdad | Kapowarr `root_folders.py:37-44` |
| Mover todo automáticamente al cambiar la raíz | Una edición de Ajustes puede lanzar una copia de cientos de GB sin confirmación; en la Pi es un riesgo de disco lleno/corte | Kapowarr `volumes.py:685-738`; Sonarr lo ofrece, no lo impone (`MoveSeriesModal`) |
| Permitir raíces anidadas y resolver por «prefijo más largo» | Dos raíces pueden reclamar el mismo archivo; la pertenencia deja de ser explícita | Sonarr `RootFolderService.cs:188-206` |
| Un «fallback» silencioso a otra raíz cuando la elegida está llena o ausente | Rompe la promesa «cada tradición a su disco» y llena el disco equivocado | No se encontró en las referencias; se propone **descartar** |
| Mostrar al coleccionista la ruta del contenedor (`/media/library/...`) | No le sirve para encontrar el archivo en su disco | `utils/ruta_visible.py:16-28` ya lo evita para una raíz; hay que generalizarlo |
| Borrar una raíz con archivos registrados | Deja huérfanas filas y rutas que no se pueden mostrar; el borrado de la raíz no debe borrar archivos | Kapowarr bloquea borrar una raíz en uso (`custom_exceptions.py:214-232`); ZascArr debe bloquear o exigir reasignación explícita |
| Declarar «todo disponible» cuando una raíz no se pudo leer | El estado global miente; el coleccionista no sabe qué disco mirar | `docs/BACKLOG.md:124`; `disponibilidad.py` ya distingue «sin verificar» para una raíz |

### 4.6 IGUALAR / MEJORAR

**IGUALAR (mínimo competitivo, con evidencia):**

- **Raíz como entidad persistida** y asignación por entidad (serie/volumen en
  las referencias; tradición aquí). Evidencia: Sonarr `RootFolder` +
  `Series.RootFolderPath`; Kapowarr `root_folders` + `VolumeData.root_folder`.
- **Validación antes de escribir:** existe, carpeta, escribible, sin
  duplicado exacto; **sin solapamiento** con otras raíces/descargas.
  Evidencia: Komga `LibraryLifecycle.kt:33-85` (padre/hijo);
  Kapowarr `root_folders.py:150-195`.
- **No recrear una raíz ausente** y **no confundir desmontaje con borrado**.
  Evidencia: Sonarr `RootFolderCheck.cs`; ZascArr `_comprobar_biblioteca`
  ya tiene guardarraíles para una raíz.
- **Espacio/estado por raíz** visible. Evidencia: Sonarr `FreeSpace`;
  Kapowarr `ROOT_FOLDER_ALMOST_FULL/FULL`.
- **Escaneo por raíz** con estado independiente. Evidencia: Komga escanea por
  biblioteca; ZascArr ya sabe hacerlo para una raíz.
- **Ruta visible adaptada al host** y migración compatible desde una raíz.
  Evidencia: ZascArr `ruta_visible.py:16-28`; migración propuesta §4.3.

**MEJORAR (hueco probado, no opinión):**

- **Tradición → raíz explícita**: ninguna referencia mapea tradición; Sonarr
  asigna por serie, Kapowarr por volumen y Mylar no reparte escritura. El
  caso de ZascArr exige una regla propia y **sin ambigüedad**. Evidencia:
  `Series.RootFolderPath`, `VolumeData.root_folder`, `config.py:51-52`.
- **Fallo cerrado si la tradición no tiene raíz** y `_Unsorted` con raíz
  explícita: las referencias usan defaults (Kapowarr exige root al añadir;
  Sonarr exige `RootFolderPath`) y no cubren «tradición sin disco».
- **Desaparición masiva por raíz**: la limitación está escrita en
  `docs/BACKLOG.md:124`; ni Sonarr ni Kapowarr la resuelven para una misma
  biblioteca con N raíces, porque su unidad es serie/volumen. ZascArr debe
  agrupar por `root_id` y no marcar ausentes de otras raíces.
- **Cambiar la configuración no mueve archivos**: Kapowarr mueve por defecto;
  Sonarr lo ofrece; ZascArr debe hacer del movimiento una acción explícita y
  separada para no convertir un ajuste en una migración masiva.
- **Cuarentena y auditoría por raíz**: el `.zascarr/apartados` global y la
  ruta relativa única (`web/auditoria.py:395-399`) dejan de ser ciertos con N
  raíces; es un hueco propio que la referencia no cubre.
- **Mostrar al coleccionista la ruta de su host por raíz**, no la del
  contenedor, y decir qué raíz está caída; las referencias bare-metal no
  tienen esta capa.

---

## 5. Riesgos, seguridad y operación

| Riesgo | Por qué importa | Mitigación propuesta |
|---|---|---|
| **Dos raíces solapadas** (iguales, anidadas o bind mount del mismo inodo) | El mismo archivo puede pertenecer a dos tradiciones; el escaneo lo ve dos veces y la ruta relativa es ambigua | Rechazar en el alta/edición con `realpath` + `st_dev/st_ino` + comparación por componentes; test de igualdad, anidamiento, symlink y bind mount. |
| **Raíz mal montada o ausente** | Un `mkdir` silencioso convierte el fallo de montaje en una carpeta nueva; luego se marcan bajas | No crear; comprobar `is_dir` y escribir un fichero temporal; estado por raíz; el importer omite esa raíz y conserva el origen. |
| **Path traversal / symlink escape** | La ruta viene de Ajustes/BD; un symlink puede sacar la escritura de la raíz | Resolver con `realpath`; rechazar si el destino real no está bajo la raíz permitida; el escáner no sigue symlinks de directorio (hoy `recorrer_comics` ya lo declara). |
| **Borrar o reasignar una raíz con archivos** | Filas huérfanas; el usuario no encuentra sus archivos | Bloquear el borrado si hay `File.root_id`; deshabilitar la raíz, no borrar; reasignación explícita en otra historia. |
| **Disco lleno a mitad de copia** | Temporal incompleto, original en riesgo, biblioteca a medias | `comprobar_espacio` por raíz antes de copiar; temporal en el destino, tamaño/hash verificado; no borrar origen hasta confirmar; limpiar temporales; nunca fallback automático a otra raíz. |
| **Cruce de discos (`EXDEV`)** | Renombrar entre raíces no es atómico | Mantener `safe_move` (copia + verificación + borrado del origen); probar `EXDEV` y bind mounts; no usar `shutil.move` a ciegas. |
| **Permisos del usuario de servicio** | La raíz nueva puede no ser escribible | Validar escritura real (temporal + borrado) al guardar; mensaje en español con la ruta y el usuario; no cambiar permisos automáticamente. |
| **Fallo de BD después de mover** | Archivo movido sin fila, o fila con ruta vieja | Mantener el orden actual y el informe; la conciliación/reparación debe cubrir N raíces; test de fallo de commit después de `safe_move` y de reinicio. |
| **Raíz retirada de la configuración** | `File.file_path` sigue existiendo; no hay raíz para mostrar | `root_id` persistido y raíz deshabilitada, no borrada; UI «raíz no disponible»; nunca borrar archivos. |
| **Cambiar el `path` de una raíz con archivos** | `File.file_path` es absoluto y no se reescribe; los archivos quedarían bajo una ruta que ya no es la raíz | Rechazar el cambio si hay `File.root_id` asociados, o tratarlo como raíz nueva + reasignación explícita; no reescribir rutas en silencio. |
| **Exportación a Kavita con N raíces** | `export_path` ya está separado, pero su validación de solapamiento solo compara con `library_path` | Validar `export_path` contra **todas** las raíces y contra descargas/incoming/compartidas; no escribir dentro de ninguna. |
| **Fuga de rutas del host** | Los logs/errores no deben llevar rutas personales | Logs con nombre de raíz, no ruta completa; la UI muestra la ruta solo a quien ya la configuró; nunca credenciales. |
| **Añadir disco “en caliente”** | Docker no puede montar un host path nuevo sin recrear el contenedor | Declarar la limitación: Ajustes gestiona raíces **ya montadas**; para un disco nuevo, montaje + `docker compose up -d`; no socket de Docker. |
| **Migración de una instalación existente** | La ruta actual debe seguir funcionando | Migración aditiva, backfill a raíz 1, `host_library_dir` como `host_path`; sin mover; test con una BD real y una biblioteca sintética. |

**Legal/licencias:** Sonarr, Radarr, Kapowarr, Mylar3 y Komga son GPL-3.0;
ZascArr también. No se copia código ni assets; se copian contratos y se
adaptan. No hay dependencia nueva propuesta.

---

## 6. NOT RUN / PASS / FAIL

| Comprobación | Estado | Detalle |
|---|---|---|
| Lectura del código de ZascArr en `acb82a40` | **PASS** | Rutas, importer, adopter, rescan, auditoría, disponibilidad, cuarentena, conversión, vinculación y `main` citados |
| Lectura del contrato de las 5 referencias | **PASS** | Sonarr/Radarr, Kapowarr, Mylar3 y Komga con versión/commit |
| Ejecución de Sonarr/Radarr/Kapowarr/Mylar3/Komga | **NOT RUN** | Solo lectura de código; no se abrieron las apps |
| Prueba real con dos discos/montajes | **NOT RUN** | No hay host con dos volúmenes en este entorno |
| Migración probada sobre una BD/biblioteca real | **NOT RUN** | La ficha propone la migración; no se ejecutó |
| `safe_move` con `EXDEV`, disco lleno o symlink hostil | **NOT RUN** | Ya existen tests de A3, pero no se ejecutaron aquí ni con N raíces |
| Escaneo/rescan con una raíz caída y otra viva | **NOT RUN** | Requiere test de integración con Postgres y árbol sintético |
| UI de Ajustes, health y rutas visibles | **NOT RUN** | Solo diseño; no se tocó código |
| **FAIL** | — | Ninguno de la ficha; lo no ejecutado está declarado. Un fallo real solo puede aparecer al implementar/probar. |

**No se declara aprobado** ni se propone ADR todavía: si el PO elige
persistir raíces y `root_id`, es una decisión de arquitectura duradera y la
spec debe decidir si necesita ADR; esta ficha solo documenta el coste.

---

## 7. Estimación revisada y partición posible

**Se mantiene L.** No baja a M: toca modelo + migración, importador,
asignación manual, adopter/rescan, auditoría, disponibilidad, cuarentena,
conversión, vinculación, rutas visibles, Ajustes, salud y pruebas con dos
sistemas de ficheros. No hay un corte vertical pequeño que cierre A5: el
primer cambio visible (importar a otra raíz) sin el escaneo por raíz haría que
el resto de la app mintiera, que es justo lo que la historia quiere evitar.

| Corte | Contenido | ¿Cierra A5? | Esfuerzo | Riesgo |
|---|---|---|---|---|
| **A. Cimiento** | Tabla de raíces + `files.root_id` + migración/backfill de una raíz + validadores de solapamiento + tests de modelo; comportamiento actual intacto | No, pero no rompe nada | **M** | Bajo/medio: migración y compatibilidad |
| **B. Importador y asignación** | Resolver tradición→raíz; `_Unsorted` por defecto; `safe_move` por raíz; `ReviewService`/`AsignacionService`; informe con nombre de raíz | Parcial: ya escribe en la raíz correcta | **M/L** | Medio: A3, disco lleno, fallo de BD |
| **C. Operar N raíces** | Adopter/rescan/auditoría/disponibilidad/cuarentena/conversión/vinculación/rutas visibles; estado por raíz y desaparición por raíz | Sí, de extremo a extremo | **L** | Alto: varios servicios, muchos tests |
| **D. Ajustes y operación** | Alta/edición/deshabilitar raíz; mapeo de tradiciones; espacio/health; mensajes y docs; limitación de montaje | Sí, para el coleccionista | **M** | Medio: UX y seguridad de rutas |

Los cortes son **acumulativos**, no historias independientes: A sin B no se
ve; B sin C miente en el escaneo; C sin D no se puede configurar. Si el PO
quiere reducir riesgo, el orden A→B→C→D permite parar después de A sin haber
cambiado el comportamiento, pero **A5 no se cierra** hasta C+D (o hasta una
consola administrativa que haga de D, decisión del PO).

**Pruebas que deben existir antes de implementar (semilla, no ejecutadas):**

- migración de una raíz a tabla + backfill, sin mover archivos;
- alta/edición: ruta inexistente, no escribible, duplicada, anidada, symlink
  que escapa, raíz de descargas;
- importación de cada tradición a su raíz; tradición sin raíz → no mueve y
  avisa; `_Unsorted` en raíz por defecto;
- `safe_move` entre raíces (`EXDEV`), destino ocupado, disco lleno, fallo de
  BD después de mover;
- escaneo de dos raíces con una caída: la otra no marca ausentes; el estado
  global no dice «todo bien»;
- mover un archivo de una raíz a otra y que rescan/adopter lo reenlace una
  sola vez;
- cuarentena/rutas relativas/`ruta_visible` con la raíz correcta;
- cambiar el mapeo **no** mueve lo existente; borrar una raíz con archivos se
  bloquea;
- salud/espacio por raíz y mensajes en español llano.

---

## 8. Fuentes, límites y caducidad

**Fuentes principales citadas arriba** (además de los enlaces de §2):
`docs/BACKLOG.md:49,124`; `src/zascarr/config.py`; `docker-compose.yml`;
`bootstrap.sh`; `scripts/_rutas.sh`; `services/importer.py`;
`services/asignacion.py`; `services/library_adopter.py`;
`services/rescan_biblioteca.py`; `services/library_audit.py`;
`services/disponibilidad.py`; `services/apartado_duplicados.py`;
`services/conversion.py`; `services/exportacion_kavita.py`;
`services/vinculacion*.py`; `web/auditoria.py`; `utils/fs.py`;
`utils/ruta_visible.py`.

**Límites:** no se ejecutaron binarios ni contenedores; no hay una instalación
real con dos discos; las referencias se leyeron, no se probaron. Las
puntuaciones de la matriz son una propuesta de lectura, no una medición.

**Caduca:** 2027-01-13 (~60 días), o antes si cambia `library_path`/el
montaje, el modelo `File`, el importer, el escaneo o alguna referencia.
