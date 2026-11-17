# Benchmark nivel 2 — #344 BL-PACK1 «Importar series desde paquetes RAR y ZIP de descarga»

> Ficha de **diseño** para la especificación. No implementa, no extrae nada, no
> toca Descargas ni la biblioteca y **no declara aprobado** ningún punto: propone
> y deja las decisiones al PO. Nivel 2 porque escribe ficheros, procesa
> contenedores hostiles y toca el ciclo de importación.
>
> - **Fecha:** 2026-11-16
> - **`origin/main` contrastado:** `79238696` (worktree `.squad/wt-344`, rama
>   `docs/344-refinamiento`).
> - **Rol:** SCOUT.bench.
> - **Historia:** `#344 BL-PACK1`; 10 criterios de aceptación y 3 preguntas
>   abiertas del PO en el cuerpo del issue. Referencias de partida: #305
>   (spike de formatos), #308 (evaluación de `unar`), #159/B10 (repartida: la
>   conversión CBR→CBZ ya está en BL-CNV; los paquetes quedan aquí).
> - **Caducidad:** 2027-01-15 (~60 días), o antes si cambia el lector RAR, el
>   importador, el modelo de paquetes o la imagen.

---

## 1. Problema local fijado

### 1.1 Qué pasa hoy con un `.rar`/`.zip` en Descargas

El importador recorre las carpetas de descarga con **una lista de extensiones
de cómic**; un `.rar` o un `.zip` no está en esa lista:

- `COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf", ".epub"}`:
  `services/importer.py:72`.
- `Importer.__init__` construye `self._scan_dirs` con
  `transmission_download_dir`, `amule_incoming_dir` y `downloads_path`:
  `services/importer.py:511-520`.
- `scan_and_import` llama `listar_comics(self._scan_dirs, COMIC_EXTS)`:
  `services/importer.py:528-530`; `listar_comics` filtra por
  `rglob("*{ext}")` y excluye `.zascarr` (`utils/fs.py:666-698`).

**Consecuencia:** un paquete en Descargas **no se ve**, no se registra y no
genera una fila `File`; tampoco se importa. No es un fallo de detección por
contenido: simplemente no se llega a mirar.

### 1.2 La auditoría RF-02 no cubre Descargas

El cuerpo del issue dice que «la auditoría lo reporta con motivo (RF-02)». En
`main` eso es cierto **solo si el paquete está dentro de la biblioteca**:

- `LibraryAudit.__init__` toma `get_settings().library_path`:
  `services/library_audit.py:162-167`; `run()` recorre esa raíz
  (`:169-178`).
- `CONTENEDORES_NO_SOPORTADOS = {".rar", ".7z", ".tar", ".cbt"}` y
  `_detectar_no_reconocidos` producen el aviso RF-02:
  `services/library_audit.py:134,322-369`.
- Las carpetas de Descargas no se pasan a `LibraryAudit`; el importador no
  audita paquetes.

Por tanto, **en Descargas el paquete es invisible**, no «se queda en la
auditoría»; si el PO lo deja en la biblioteca, sí aparece el aviso, pero #344
solo trata Descargas. Esta diferencia debe quedar en la spec: el hueco real
incluye una **pantalla/estado de paquetes pendientes** que hoy no existe.

### 1.3 Detección por firma que ya existe, y lo que le falta

`core/formato_contenedor.py` ya tiene el punto único de decisión de #307:

- `firma_de` lee como máximo **512 bytes** y clasifica ZIP, RAR, 7z, TAR, OTRO
  o ILEGIBLE: `core/formato_contenedor.py:88-106`.
- `tratamiento(ext, firma)` decide `LEER_COMO_ZIP`, `SOLO_HASH` o `AVISAR`:
  `:161-184`. Un `.rar` con firma RAR da `AVISAR`; un `.zip` con firma ZIP da
  `LEER_COMO_ZIP`; un `.cbz` que es RAR da `AVISAR`.
- `clasificar_infos`/`clasificar_zip` leen solo el directorio central de un ZIP
  y clasifican `TEBEO`, `ANIDADOS`, `NO_TEBEO`, `CIFRADO`, `INVALIDO`, `VACIO`
  o `LIMITE`: `:200-239`; los topes actuales son 2000 entradas, 1 MiB de
  directorio central, 32 MiB por entrada leída y ratio 100
  (`:48-70`).
- `utils/lector_rar.py` ya lista y lee **una** entrada RAR por índice, con
  topes de 1000 entradas, 500 MiB declarados, 4 MiB de salida de listado,
  timeout, 128 MiB de RSS y un solo lector:
  `utils/lector_rar.py:42-64,318-425`.

Lo que falta es una **capa de paquete**: listar el contenedor entero, decidir
qué entradas son grapas, extraerlas a un temporal y publicarlas como carpeta de
entrada. `lector_rar` está pensado para **una página de cubierta**, no para
extraer un paquete de varios GB; `leer_entrada` devuelve los bytes completos de
una entrada (`:391-425`) y su `RAR_MAX_BYTES_DECLARADOS=500 MiB` no sirve para
un pack real de varios GB.

### 1.4 Frontera con A3/B6 y con #159/B10

**A3 (nunca dañar la colección):** `safe_move`/`safe_move_en_raiz` no
sobrescriben, comprueban el destino y no borran el original hasta que la copia
está completa (`utils/fs.py:355-509,569-660`). #344 no debe mover ni borrar el
paquete original; la extracción crea **copias nuevas** en un temporal y una
carpeta de entrada. Es una operación de **lectura del paquete + escritura de
copias**, no de mover el original.

**B6 (ComicInfo dentro del CBZ):** la reescritura segura de CBZ vive en
`utils/cbz.py` y solo la usa el tagger para un `FileFormat.CBZ`
(`utils/cbz.py:1-30`; `services/tagger.py:538-541`). #344 **no reescribe el
paquete ni le inyecta ComicInfo**; si una grapa extraída se importa, el flujo
normal puede etiquetarla después como cualquier CBZ, pero el paquete original
no se toca. No se debe llamar `utils/cbz` sobre el contenedor.

**#159/B10:** la parte de conversión CBR→CBZ ya está entregada en BL-CNV; la
conversión **rechaza un paquete** (`MotivoConversion.PAQUETE`,
`services/conversion_cbr.py:42,64,139-155`) y tiene su propio límite de 150 MiB
(`:24-29`). #344 **no convierte**: extrae y entrega las grapas al importer. Un
`.cbr` extraído se registra como cualquier `.cbr`; su conversión futura es otra
acción. La nota de trazabilidad del issue (`#344`, comentario del 2026-11-15)
dice exactamente que B10 se repartió y que esta es la parte de paquetes.

### 1.5 Resultado deseado (sin decidir implementación)

Un paquete `.rar`/`.zip` en Descargas debe:

1. aparecer como **paquete pendiente** (sin abrirlo automáticamente);
2. poder **listarse** antes de escribir, con topes y causas;
3. extraerse a un **temporal aislado**, verificando cada entrada;
4. publicar solo las grapas `.cbz`/`.cbr` en una **carpeta de entrada** de
   Descargas y dejar que el importer normal las procese;
5. conservar el paquete **intacto** por defecto;
6. dejar un informe con lo importado, lo ignorado y la causa de cualquier
   fallo, sin borrar ni mover nada del PO.

---

## 2. Referencias consultadas (contrato, no UI)

| Referencia | Versión / commit | Qué se leyó |
|---|---|---|
| **Sonarr** | `c018578e4b79ee048575c02d7a8aa2b929e4b837` (v4.0.20.3014) | `DownloadedEpisodesImportService`, `ManualImportService`, `FileExtensions`, importación de carpetas/season packs |
| **Radarr** | `19edd437952373cd7bd39224c6235b61fad5672a` (develop; release v6.4.4.10685) | `DownloadedMovieImportService`, `ManualImportService`, `FileExtensions` |
| **Kapowarr** | `c191dda6617929c81292483a8cc07f631111dae2` (v1.3.2) | `archive_contains_issues`, `rar_to_folder`/`zip_to_folder`, `extract_files_from_folder` |
| **Mylar3** | `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (v0.8.3) | `PostProcessor`, `moveit.movefiles`, `getimage.open_archive` |
| **ComicTagger / ComicAPI** | `fa11a3456cbe5aa9f54f47bdc374ba26b2b946f3` (develop, Apache-2.0) | `comicapi/comicarchive.py`, `archivers/folder.py`, `archivers/rar.py` |
| **Calibre-Web** | `6e840acbda8d62fdd159bf3855c01872d629a914` (GPL-3.0) | README y modelo de biblioteca de ebooks; no es un extractor de paquetes |
| **Spike propio #305** | `docs/design/benchmark-formatos-contenedor.md` | Censo, opciones A/B/C, comportamiento de Sonarr/Radarr/Kapowarr/Mylar3/Suwayomi, riesgos de 7z/TAR |
| **Spike propio #308** | `docs/design/evaluacion-lector-rar-2026-10-23.md` y `...-tanda2...` | `unar`/`lsar`, medidas, topes, truncados, límites y condiciones de adopción |
| **#344 / #308 / #305** | issues | Contrato de 10 AC, decisión de adoptar `unar` y preguntas abiertas |

Enlaces: [Sonarr](https://github.com/Sonarr/Sonarr/tree/c018578e4b79ee048575c02d7a8aa2b929e4b837),
[Radarr](https://github.com/Radarr/Radarr/tree/19edd437952373cd7bd39224c6235b61fad5672a),
[Kapowarr](https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2),
[Mylar3](https://github.com/mylar3/mylar3/tree/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316),
[ComicTagger](https://github.com/comictagger/comictagger/tree/fa11a3456cbe5aa9f54f47bdc374ba26b2b946f3),
[Calibre-Web](https://github.com/janeczku/calibre-web/tree/6e840acbda8d62fdd159bf3855c01872d629a914).

### 2.1 Sonarr / Radarr: no extraen; importan carpetas y avisan del archivo

- **Season pack = carpeta de vídeos**, no archivo comprimido. `ProcessFolder`
  recoge los ficheros de vídeo de la carpeta, pide una decisión por fichero y
  los importa; no hay `extract` ni temporal de descompresión:
  `src/NzbDrone.Core/MediaFiles/DownloadedEpisodesImportService.cs:64-82,
  162-235`; `ManualImportService.cs:116-141,239-299` hace lo mismo para la
  importación manual. Radarr replica el patrón:
  `DownloadedMovieImportService.cs:65-82,163-234`;
  `MovieImport/Manual/ManualImportService.cs:107-132,187-246`.
- **Un archivo comprimido no se abre.** Si la carpeta no da ningún vídeo y
  contiene una extensión de archivo comprimido, la importación se rechaza con
  una causa visible: `ImportRejectionReason.ArchiveFile`, «Found archive file,
  might need to be extracted» (`DownloadedEpisodesImportService.cs:369-381`;
  Radarr `:354-370`). `FileExtensions.ArchiveExtensions` incluye `.7z`, `.rar`,
  `.zip`, `.tar`, `.r00`… (`src/NzbDrone.Core/MediaFiles/FileExtensions.cs:18-32`).
- **No hay directorio temporal de extracción**: el import mueve o copia desde
  la carpeta de descarga (`ImportMode`, `:222-235`) y el cliente de descargas
  decide si descomprime. Sonarr/Radarr **no** son un lector de paquetes; son
  una referencia de **comportamiento ante archivo comprimido**.
- **Borrado:** solo se borra la carpeta de descarga si la importación fue
  correcta y `ShouldDeleteFolder` lo permite; si queda un `.rar` de más de
  10 MB, se conserva y se avisa «manual cleanup»
  (`DownloadedEpisodesImportService.cs:115-148,227-235`). El archivo no se
  borra por el hecho de existir.
- **Lo que no cubre:** descompresión, listado, topes de bombas, verificación
  de entradas, estado de paquete, reanudación. ZascArr no puede «adoptar» su
  importador para paquetes; sí puede adoptar su **causa visible** y su política
  de no borrar el archivo.

### 2.2 Kapowarr: lista y extrae, pero con un contrato destructivo que no se copia

- `archive_contains_issues` **lista** un ZIP (`ZipFile.namelist`) o un RAR
  (`rar lb`) y devuelve True si alguna entrada tiene extensión de contenedor:
  `backend/base/files.py:212-236`. Es la idea útil: **mirar dentro antes de
  decidir**.
- `zip_to_folder` hace `zip.extractall(archive_folder)`;
  `rar_to_folder` ejecuta `rar x` con ruta completa de salida;
  `extract_files_from_folder` mueve los ficheros relevantes, **borra el resto**
  y **borra el archivo original**; al final elimina la carpeta temporal:
  `backend/implementations/converters.py:35-100,477-516`.
- No hay topes de entradas/tamaño/ratio en esa ruta, no hay verificación por
  CRC/tamaño y no se conserva el original. Es exactamente el **anti-patrón**
  que #344 no debe copiar.
- **Lo que sí se adapta:** listar antes, clasificar paquete y no tratar el
  archivo como un tebeo individual (`archive_contains_issues`). La extracción,
  el borrado y el `extractall` se descartan.

### 2.3 Mylar3: varios ficheros de una carpeta, pero sin descomprimir

- `moveit.movefiles` recorre `imported['filelisting']` y mueve **varios
  ficheros** con `shutil.move`; no descomprime ni verifica CRC:
  `mylar/moveit.py:1-80`. `PostProcessor` construye la lista de ficheros y
  procesa cada uno; es un flujo de carpeta con varios ficheros, no de paquete.
- `getimage.open_archive` abre ZIP o `rarfile` para **leer páginas** de un
  tebeo; no extrae un paquete ni publica una carpeta de entrada:
  `mylar/getimage.py:41-64`.
- **Lo que no cubre:** detección de paquete, topes, extracción aislada,
  verificación y estado. Se descarta como contrato de #344; solo confirma que
  «varios ficheros en una carpeta» ya es un caso normal del importador.

### 2.4 ComicTagger / Calibre-Web: no son extractores de paquetes

- **ComicTagger/ComicAPI** representa **un cómic** (fichero o carpeta):
  `comicapi/comicarchive.py:1` («a single comic, be it file or folder of
  images»); `FolderArchiver` trata una carpeta como un cómic
  (`comicapi/archivers/folder.py:1-60`). Sabe leer CBZ/CBR, pero no convierte
  un `.rar`/`.zip` de varios tebeos en una carpeta de entrada. Se descarta.
- **Calibre-Web** es una interfaz de biblioteca de ebooks sobre Calibre
  (`README.md`, sección *Features*); no es un gestor de paquetes de descarga
  ni un extractor de archivos. Se descarta por alcance.
- **Barrera legal:** Sonarr/Radarr/Kapowarr/Mylar3/Calibre-Web son GPL-3.0;
  ComicTagger es Apache-2.0. No se copia código; solo se contrastan contratos.

### 2.5 Lo que ya está decidido en el propio proyecto (#308/#418)

- `unar`/`lsar` ya están en la imagen (`Dockerfile:27-30`, etapa runtime) y
  el ADR 0015 acepta el riesgo de ejecutarlo en el mismo contenedor con
  subproceso, sin shell, entorno mínimo, grupo de procesos, tiempo, RSS
  128 MiB, salida/bytes acotados, un solo lector y verificación por tamaño/CRC
  (`docs/adr/0015-lector-de-rar-con-unar.md`, Decisión).
- La evaluación #308 midió 35 muestras RAR (RAR4/RAR5, sólidos hasta 215 MB):
  `unar` leyó la página con **≤ 25,8 MiB de pico**, primera página ≤ 0,09 s en
  caliente y ≤ ~0,33 s en frío; `lsar -j` puede tardar 2,5–4,7 s en sólidos;
  `unar` devuelve 0 sin escribir si el índice no existe y `lsar` lista un
  truncado con 0; hay que verificar siempre
  (`docs/design/evaluacion-lector-rar-tanda2-2026-10-23.md:24-70`).
- **Esto no mide extraer un paquete completo**: solo listar y leer una página.
  La medición de un pack RAR/ZIP de varios GB es **NOT RUN** (§4).

---

## 3. Matriz ponderada de ideas

Se usan los pesos por defecto de `docs/design/benchmark-referencias.md`, sin
moverlos: **flujo del Coleccionista 25 · coste en Pi 20 · seguridad, legalidad
y licencia 20 · requisito core 15 · adaptabilidad al stack 10 · mantenimiento
5 · lock-in 5**. Puntuación 1–5; total `Σ(peso×puntuación)/5`, 0–100. Es una
propuesta de lectura, no una decisión.

| # | Idea (de dónde) | Flujo 25 | Pi 20 | Seg 20 | Core 15 | Stack 10 | Mant. 5 | Lock-in 5 | Total | Resultado |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| I1 | Detectar por **firma** (≤512 B), no por extensión; incluye `.rar.zip`, ZIP/RAR cruzados (#307/#308) | 5 | 5 | 5 | 5 | 5 | 4 | 4 | **98** | **Adoptar** |
| I2 | **Listar antes** de escribir; clasificar paquete y entradas (Kapowarr + #308) | 5 | 5 | 5 | 5 | 4 | 4 | 4 | **96** | **Adoptar/adaptar** |
| I3 | Topes de paquete: entradas, tamaño declarado, tamaño por entrada, ratio ZIP, directorio central, salida RAR (propio #307 + #308) | 4 | 4 | 5 | 5 | 5 | 4 | 4 | **89** | **Construir sobre lo propio** |
| I4 | Extraer a **temporal aislado** fuera de biblioteca/Descargas, 0700, limpieza garantizada (propio #418 + ADR 0015) | 4 | 4 | 5 | 5 | 5 | 4 | 4 | **89** | **Adaptar** |
| I5 | Verificar **tamaño + CRC + primera imagen decodificada** por entrada, y listado vs extraído (propio #308; ninguna referencia verifica el paquete) | 5 | 4 | 4 | 5 | 5 | 4 | 4 | **90** | **Mejorar** |
| I6 | Usar `unar`/`lsar` directo para RAR y `zipfile` para ZIP; sin `rarfile`/`unrar` (ADR 0015) | 4 | 5 | 5 | 5 | 5 | 5 | 4 | **94** | **Adoptar** |
| I7 | **Original intacto**: no mover, renombrar, convertir ni borrar; A3 (propio) | 5 | 5 | 5 | 5 | 5 | 4 | 4 | **98** | **Adoptar** |
| I8 | Al importer solo pasan `.cbz`/`.cbr` (firma compatible); resto listado e ignorado (propio) | 5 | 4 | 4 | 5 | 5 | 4 | 4 | **90** | **Construir sobre lo propio** |
| I9 | Estado de paquete **duradero** (tabla de operaciones) y pendiente derivado del disco (nuevo; Kapowarr no lo tiene) | 4 | 4 | 4 | 3 | 4 | 3 | 3 | **75** | **Construir sobre lo propio** |
| I10 | Reanudar una extracción a medias reutilizando ficheros temporales | 4 | 4 | 4 | 3 | 4 | 3 | 3 | **75** | **Descartar en v1** (reintento limpio) |
| I11 | Multivolumen `.partN.rar`/`.r00` dentro de esta historia | 3 | 3 | 3 | 1 | 2 | 2 | 2 | **50** | **Descartar** (siguiente historia) |
| I12 | `rar x`/`zip.extractall` + mover + **borrar original** (Kapowarr) | 1 | 2 | 1 | 1 | 2 | 1 | 1 | **26** | **Descartar** |
| I13 | Aceptar un archivo comprimido como «casi importado» y borrarlo (Sonarr/Radarr no lo hacen) | 1 | 2 | 1 | 1 | 1 | 1 | 1 | **24** | **Descartar** |
| I14 | No extraer y limitarse a rechazar con causa (Sonarr/Radarr) | 3 | 4 | 3 | 2 | 3 | 3 | 3 | **61** | **Descartar como solución; adoptar la causa visible** |
| I15 | ComicTagger/Calibre como extractores (un solo cómic/ebook) | 2 | 3 | 2 | 1 | 2 | 2 | 2 | **41** | **Descartar** |

**Lectura:** la mejor base es la propia: firma (#307), lector RAR acotado
(#418), A3 y el punto único de formato. Lo que hay que **construir** es la capa
de paquete (topes, extracción, verificación, estado y UI). Kapowarr aporta la
idea de listar, pero su implementación (extractall + borrar original) se
descarta; Sonarr/Radarr no resuelven el problema, solo enseñan a no borrar y a
decir la causa.

### 3.1 IGUALAR / MEJORAR

**IGUALAR (mínimo que ya ofrecen las referencias o el propio ZascArr):**

- Decidir por **firma** de contenido (≤512 B), no por extensión: ya está en
  `core/formato_contenedor.py:88-106`.
- **Listar antes** de escribir y clasificar paquete vs tebeo: Kapowarr lo hace
  con `archive_contains_issues` (`backend/base/files.py:212-236`); ZascArr
  puede reutilizar su punto único de formato.
- **Topes y verificación** de tamaño/CRC: el propio lector RAR ya verifica
  tamaño y CRC de una entrada (`utils/lector_rar.py:391-425`); #307 ya acota
  ZIP (`core/formato_contenedor.py:48-70,242-260`).
- **Original intacto**: A3 (`utils/fs.py:355-509`) y Sonarr/Radarr, que no
  borran el `.rar` de más de 10 MB (`DownloadedEpisodesImportService.cs:
  115-148`).
- **No abrir automáticamente** y **causa visible**: contrato del issue y
  patrón de rechazo de Sonarr/Radarr (`ImportRejectionReason.ArchiveFile`).

**MEJORAR (hueco probado, no opinión):**

- **Extraer de verdad** un paquete: Sonarr/Radarr no lo hacen (solo rechazan
  el archivo: `DownloadedEpisodesImportService.cs:369-381`), y Mylar3 no
  descomprime paquetes (`mylar/moveit.py:1-80`). ZascArr sí debe hacerlo, con
  `unar`/`zipfile`.
- **Hacerlo sin destruir**: Kapowarr usa `rar x`/`zip.extractall` y borra el
  original (`backend/implementations/converters.py:477-516`); ZascArr debe
  extraer a un temporal, verificar y conservar el original. Es la mejora de
  seguridad/operación más clara frente a la referencia.
- **Verificar cada entrada** (tamaño, CRC, primera imagen): ninguna de las
  referencias de paquete lo hace; #308 demuestra que un `rc 0` no basta.
- **Estado durable y reintento limpio**: Kapowarr no tiene una operación
  observable; ZascArr necesita saber qué se importó, qué se ignoró y por qué.
- **Solo grapas `.cbz/.cbr`**: el resto se informa y no se publica; evita
  llenar Descargas con imágenes sueltas o ficheros de release.
- **Multivolumen**: se detecta y se rechaza con causa ahora; la extracción
  completa es otra historia (decisión del PO).

---

## 4. Seguridad y costes en la Pi

### 4.1 Amenazas y controles

| Amenaza | Qué puede pasar | Control propuesto |
|---|---|---|
| **Zip-bomb / RAR-bomb** | Un paquete pequeño declara/expande cientos de GB y llena la Pi | Listar antes; topes de entradas, tamaño declarado total y por entrada, ratio de la entrada leída y bytes **realmente escritos**; no confiar en la cabecera; cortar por bytes reales. |
| **Path traversal** (`../../`, `/etc/...`) | Escribir fuera del temporal | **No extraer por nombre**: nombres de salida generados por ZascArr; rechazar nombres con `..`, absolutos o separadores raros; verificar que cada ruta resuelta está bajo el temporal. |
| **Symlink / hardlink** | Escritura o lectura fuera del temporal; hardlink a un fichero ajeno | ZIP: no se crean enlaces al escribir; RAR: `_unico_fichero_regular` ya rechaza symlinks y exige un solo fichero; en el paquete, `lstat` + `st_nlink == 1`; abortar y limpiar si aparece un enlace. |
| **Entrada anidada** | Un paquete dentro de otro, recursión o bomba por capas | Listar el exterior; si hay `.rar`/`.zip`/`.7z`/`.tar` (u otro contenedor no-grapa) → `PAQUETE_ANIDADO`, no se extrae nada. Un `.cbz`/`.cbr` sí es una grapa esperada, no «anidado». |
| **Truncado / listado corto** | `lsar` lista un truncado con rc 0; `unar` sale 0 sin escribir | Verificar existencia, tamaño y CRC de **cada** entrada; contar entradas extraídas frente a las aceptadas; no aceptar un listado corto; si el paquete cambió, abortar. |
| **Contraseña / cifrado** | No se puede leer; no pedir contraseña | `lsar` cifrado o flags ZIP → `CIFRADO`, causa llana; no fuerza bruta. |
| **Multivolumen** | Un `.part1.rar` no es un paquete completo | Detectar por nombre y por error `MULTIVOLUMEN`; rechazar con causa; no extraer el primer volumen como si fuera completo. |
| **Disco lleno** | Temporal o carpeta de entrada a medias | `comprobar_espacio` antes de escribir, por el tamaño declarado + margen; durante la extracción contar bytes reales; si falla, limpiar y conservar original. No cambiar de disco automáticamente. |
| **Timeout / CPU** | `unar` se cuelga o tarda demasiado; el contenedor se queda sin CPU | Grupo de procesos propio, timeout de listado y de extracción, matar el grupo; un solo `unar` a la vez; extracción ZIP en hilo; no paralelizar paquetes. |
| **Memoria** | `unar` o un ZIP grande agotan los 512 MiB | `RAR_MAX_RSS=128 MiB` vigilado; ZIP en streaming, nunca `read()` completo; Pillow solo cabecera/primera imagen con tope de píxeles; no `RLIMIT_AS` para `unar` (lo mata, ADR 0015). |
| **Paquete modificado durante la operación** | Se publica una mezcla o se lee un archivo cambiado | Guardar `stat` (size, mtime_ns, dev, ino) al listar; revalidar antes de extraer y al publicar; si cambió, abortar y limpiar. |
| **Fallo de proceso/BD a mitad** | Estado inconsistente, temporales huérfanos | Estado durable por operación, limpieza al arrancar, no reanudar a medias; reintento desde cero; el original siempre intacto. |

**Superficie ya aceptada:** ADR 0015 acepta `unar` en el mismo contenedor y
reconoce que un fallo de ejecución de código equivaldría a comprometer la app;
no hay seccomp ni usuario separado. #344 **no cambia** esa decisión: reutiliza
el lector y añade llamadas de extracción; cualquier incremento de superficie
debe pasar por SecOps. `LECTOR_RAR_ENABLED=false` debe dejar los paquetes RAR
en «no disponible» sin intentar `unar` (ZIP sigue con stdlib).

### 4.2 Costes medidos y no medidos

| Medida | Valor | Aplicabilidad |
|---|---|---|
| Pico de `unar` leyendo una página RAR | **≤ 25,8 MiB** en 35 muestras; sólido de 215 MB | Medido en la Pi (#308); **no** es el pico de extraer un paquete completo |
| Primera página RAR, caliente/frío | **≤ 0,09 s / ≤ ~0,33 s** (disco del sistema) | Medido; no extrapolable a decenas de ficheros |
| `lsar -j` de un RAR sólido | **2,5 s (57 MB), 4,7 s (215 MB)** | Medido; un paquete sólido grande puede acercarse |
| `unar` 1.10.8 + GNUstep en imagen | **~687,8 MiB** de imagen; +22,5 MiB frente a sin `unar` (tanda2) | Ya está en la imagen; #344 no añade dependencia |
| ZIP stdlib | Sin dependencia; directorio central y topes #307 | Medido para lectura de una página, no para un paquete |
| **Extracción de un paquete realista de varios GB** | **NOT RUN** | No se ejecutó; no hay paquete real en este entorno |
| **Pico de disco temporal + pico de RSS + tiempo total del paquete** | **NOT RUN** | Debe medirse en la Pi antes de cerrar AC9 |
| **Bomba real ZIP/RAR, truncado, cifrado, multivolumen** | **NOT RUN** para paquete | #308 probó páginas y daños; no un paquete completo |
| **Lectura en frío desde el USB de la biblioteca** | **NOT RUN** | #308 lo dejó pendiente; #344 no lo mide |

**Presupuesto de espacio:** hay que reservar, como mínimo, el tamaño declarado
del contenido aceptado en el temporal y, si la publicación va a otra carpeta,
el mismo tamaño otra vez; el paquete original no se copia. Si el temporal está
en el mismo sistema de ficheros que Descargas se puede publicar con un rename
y evitar la segunda copia; si no, hay copia verificada. En una Pi con el disco
casi lleno y paquetes de varios GB, la comprobación de espacio es parte del
contrato, no un detalle.

**Temporal:** no usar `/tmp` a ciegas (puede ser overlay/tmpfs y su tamaño no
está garantizado). Se propone una ruta dedicada, fuera de biblioteca y
Descargas, configurable (p. ej. `PACK_TMP_PATH`, por defecto
`/config/paquetes-tmp` en el volumen de datos), con permisos `0700`, un
`mkdtemp` por operación y barrido de huérfanos al arrancar. El
`covers_cache_path` actual (`config.py:224`) es el ejemplo de temporal ya
aislado, pero una extracción de varios GB no debe compartir la caché de
portadas sin un límite propio.

---

## 5. Diseño propuesto para ZascArr (sin código)

### 5.1 Detección y cola de paquetes

- **Candidato** = fichero en una carpeta de Descargas (`downloads_path`,
  `transmission_download_dir`, `amule_incoming_dir`) cuya extensión final sea
  `.rar` o `.zip` (también `.rar.zip`/`.zip.rar`) y cuya **firma** sea RAR o
  ZIP (`firma_de`, ≤512 B). No se recorre la biblioteca; no se sigue un
  symlink de directorio.
- La **lista de pendientes se deriva del sistema de ficheros** (ruta + stat +
  firma), no de una fila de «pendiente». Así un paquete nuevo aparece sin
  migración y uno borrado desaparece. Una operación ya `importado` con la
  misma identidad (stat) lo suprime de la lista; si el paquete cambia de
  tamaño/mtime/inodo, vuelve a aparecer.
- **No se abre automáticamente**: la detección lee 512 bytes; el listado del
  contenido y la extracción solo ocurren con una petición explícita del
  usuario (issue, alcance 1).
- **Dónde vive el estado:** una tabla durable de **operaciones** (propuesta
  `paquete_operaciones`, migración aditiva) para listar/extraer/verificar/
  publicar/importar, sus causas, contadores y el token de la operación. No se
  usa `RuntimeSetting` como cola (es configuración JSONB), ni `File` (un
  paquete no es un cómic), ni `ImportRun.details` (es un informe truncado a
  200 que no sirve para reanudar). La lista de pendientes sigue siendo
  derivada; la tabla solo guarda operaciones.
- **Identidad de operación:** `path` normalizado + `(st_dev, st_ino)` + tamaño
  + `mtime_ns` + firma. No se hashea el paquete entero por defecto (varios GB;
  el `stat` ya detecta cambio); si el PO quiere hash de evidencia, es otro
  coste y otra decisión.

### 5.2 Máquina de estados

```text
(pendiente derivado, sin fila)
  │  el usuario pide «ver contenido»
  ▼
[listando] ── error/topes/nested/cifrado/multivolumen ──► [error] (sin temporal)
  │ ok
  ▼
[listado]  (vista previa; no se ha escrito nada)
  │  el usuario confirma «extraer e importar»
  ▼
[extrayendo] ── fallo ──► [error] (temporal limpiado; original intacto)
  │
  ▼
[verificando] ── fallo ──► [error] (nada publicado)
  │ ok
  ▼
[publicando]  (carpeta de entrada en Descargas, completa)
  │
  ▼
[importando]  (el importer normal procesa .cbz/.cbr)
  │
  ├─ todas verificadas ──► [importado] (original intacto; temporal limpio;
  │                         carpeta de entrada vacía; paquete suprimido de pendientes)
  └─ fallo/parcial ──────► [error] o [parcial] (causa; original intacto;
                            sin anunciar importado; reintento limpio)
```

- No se persiste `pendiente`: es derivado.
- `listando` no escribe; `extrayendo` escribe **solo** en el temporal;
  `verificando` comprueba; `publicando` crea la carpeta final completa;
  `importando` es el flujo normal; `importado` no vuelve a extraer.
- Un fallo siempre limpia temporal/staging; **no se reanuda** una extracción a
  medias en v1: el reintento vuelve a listar y extraer desde cero. Es más
  simple y evita publicar una mezcla.
- Al arrancar, las operaciones en estados vivos se marcan `error` recuperable
  y se barren temporales huérfanos; el paquete original sigue pendiente.

### 5.3 Listado y topes (antes de escribir)

Propuesta inicial (revisable; no aprobada):

| Límite | Valor propuesto | A qué se aplica |
|---|---|---|
| Entradas | ZIP ≤ 2000 (ya `MAX_ENTRADAS`); RAR ≤ 1000 (ya `RAR_MAX_ENTRADAS`) | Listado |
| Directorio central ZIP | ≤ 1 MiB (ya `MAX_DIRECTORIO_CENTRAL`) | Antes de abrir el ZIP |
| Tamaño declarado total del paquete | ≤ **8 GiB** (nuevo; el de 500 MiB del lector de cubiertas es para una página y no sirve para un pack) | Listado |
| Tamaño por entrada | ≤ **2 GiB** | Aceptar/grapa |
| Ratio de compresión | ZIP ≤ 100 por entrada (ya `MAX_RATIO_LEIDA`); RAR: usar `XADCompressedSize` si está, y acotar por bytes escritos y tamaño declarado; no fingir ratio si no se puede | Listado + extracción |
| Salida de listado RAR | 4 MiB actual; si el paquete la supera, rechazar con causa «listado demasiado grande» (no extraer) | Listado |
| Entradas aceptadas | Solo `.cbz`/`.cbr` con firma compatible; si no hay ninguna, «no contiene tebeos» | Listado |
| Nombres | Rechazar `..`, ruta absoluta, separadores raros, NUL; no usarlos para la ruta de salida | Antes de extraer |

El listado devuelve por entrada: nombre (solo para mostrar; no para la ruta),
tamaño declarado, CRC si consta, tipo (grapa/otro/anidado) y qué se haría. No
se escribe nada. Un paquete con `.cbz`/`.cbr` y otros ficheros es válido: los
otros se ignoran con causa.

### 5.4 Extracción y verificación

- **ZIP:** `zipfile` en un hilo de trabajo; por cada entrada aceptada, se
  escribe con **nombre generado** dentro del temporal (no con el nombre del
  paquete), en streaming y con topes; se calcula CRC mientras se escribe y se
  compara con el declarado; no se usa `extractall`.
- **RAR:** se reutiliza `utils/lector_rar.py` (sin shell, ruta absoluta,
  entorno mínimo, grupo de procesos, timeout, RSS, un solo lector), **por
  índice**, no por nombre; se extrae **una entrada** a un directorio vacío y
  se verifica que haya un solo fichero regular, sin symlink ni hardlink. No se
  usa `unar` con `-o` sobre un nombre del paquete; el índice evita comodines.
- **Comprobación por entrada:** existe, es regular, tamaño = listado, CRC =
  listado si consta, no se sale del temporal. Si falla una, se aborta el
  paquete; no se publica ninguna.
- **Comprobación de la grapa:** `.cbz` → firma ZIP; `.cbr` → firma RAR o ZIP
  (un `.cbr`-ZIP ya lo lee #307); abrir el contenedor, comprobar que lista y
  que **la primera imagen decodifica** con Pillow y el tope de píxeles. No se
  abren todas las páginas (coste); se documenta que la verificación es de
  entrada + primera página, no una auditoría completa del cómic.
- **`unar` RAR5 sólido:** limitación conocida de extracción (ADR 0015); si la
  entrada no se puede leer, se rechaza con causa, no se publica.
- **Paquete cambiado:** comparar stat antes/después; si cambió, abortar.
- **Original:** nunca se renombra, mueve, convierte ni borra.

### 5.5 Publicación e importación

- **Temporal** fuera de biblioteca y Descargas; **publicación** en una carpeta
  nueva dentro de la **misma carpeta de Descargas** del paquete, con nombre
  seguro y sufijo único. Para que el importer no vea ficheros a medias, se
  publica primero en una carpeta oculta bajo `.zascarr/paquetes/<operación>/`
  (que `listar_comics` ya excluye, `utils/fs.py:666-698`) y se renombra a la
  carpeta final cuando está completa. Si el temporal y Descargas están en el
  mismo sistema de ficheros, el rename es atómico; si no, se copia verificado
  y se limpia el temporal.
- **Solo se publican** las grapas aceptadas; los ficheros ignorados no se
  escriben (se informan). Los nombres finales se sanean y se deduplican para
  no sobrescribir.
- **Entrada al importer normal:** se lanza `Importer.scan_and_import` (o se
  deja para el siguiente ciclo, decisión de UX) sobre Descargas; como la
  carpeta solo contiene `.cbz`/`.cbr`, entra por `COMIC_EXTS`. No se crea
  `File` para el paquete ni para los ignorados.
- **Resultado:** se mapea por fichero (importado, duplicado, a revisar,
  error); el paquete solo se marca `importado` si todas las grapas publicadas
  tienen resultado verificado; si queda alguna, `error`/`parcial` con causa.
- **Limpieza:** temporal siempre; carpeta de entrada vacía después de importar;
  si quedó parcial, se conserva para diagnóstico/limpieza manual y se dice.
  **El original no se borra** por defecto (decisión del PO; §6).

### 5.6 UI mínima (sin código)

- Una sección **«Paquetes pendientes»** en Descargas/Estado (ruta nueva o
  tarjeta; no una pantalla de catálogo): nombre, formato real, tamaño, estado,
  causa si la hay; sin abrir nada al cargar.
- Botón **«Ver contenido»** → listado (entradas aceptadas/ignoradas, topes);
  no escribe.
- Botón **«Extraer e importar»** con confirmación explícita; progreso por
  estados; el original se queda donde está y se dice.
- Resultado por paquete: importados, ignorados, duplicados, a revisar, error;
  enlace a la cola normal.
- Enlace a la sección desde `Estado`/Auditoría; no cambiar la auditoría de
  biblioteca (RF-02 sigue siendo de biblioteca).

### 5.7 Trazabilidad y observabilidad

- Tabla de operaciones: estado, contadores, causa, `paquete_clave`, `items`
  (nombre/tamaño/CRC/destino/estado), timestamps; no guarda los bytes.
- Informe `ImportRun` o `kind="paquete"` con el resumen (sin rutas completas en
  logs; localmente la UI puede mostrar lo necesario para encontrar el paquete).
- Logs sin rutas/nombres de terceros; hashes solo si el PO los pide; nunca
  contenido del paquete en GitHub.
- No se cambia el contrato de #307 (`formato_contenido`), ni la auditoría de
  biblioteca, ni `File` para el paquete.

---

## 6. Decisiones abiertas del PO (no decididas aquí)

| # | Pregunta | Opciones | Recomendación provisional (no aprobada) |
|---|---|---|---|
| a | **¿El paquete extraído se guarda como copia en Descargas o se limpia?** | (a) conservar la carpeta extraída; (b) extraer solo para importar y limpiar; (c) conservar solo si falla | **(b) por defecto:** publicar las grapas, importarlas y limpiar temporal/carpeta vacía; conservar la carpeta si hubo fallo/parcial para diagnóstico. El paquete original se conserva. |
| b | **¿Original tras una importación verificada?** | (a) conservar siempre; (b) ofrecer mover a papelera; (c) borrar automáticamente | **(a) conservar siempre por defecto**; una papelera/borrado explícito es otra historia. A3 y Sonarr/Radarr (RAR >10 MB no se borra) apuntan a no borrar. |
| c | **¿Multivolumen `.partN.rar`/`.r00` en esta historia?** | (a) sí; (b) siguiente historia; (c) solo detectar/rechazar | **(c) en #344: detectar y rechazar con causa; la extracción multivolumen, en la siguiente.** Requiere juntar volúmenes, verificar el conjunto y una UI distinta. |
| d | **¿Dónde vive el temporal?** | (a) `/config/paquetes-tmp`; (b) `/tmp`; (c) carpeta padre de Descargas; (d) ruta configurable | **(a) ruta dedicada configurable**, fuera de biblioteca/Descargas; si es posible, en el mismo sistema de ficheros que Descargas para publicar con rename. `/tmp` no garantiza espacio. |
| e | **¿Qué se considera «paquete»?** | (a) cualquier `.rar/.zip`; (b) solo si contiene `.cbz/.cbr`; (c) también `.zip` de un solo cómic | **(b)**: un `.zip` de un solo tebeo no es un paquete de #344; se lista y se dice «no contiene grapas»; un paquete anidado se rechaza. |
| f | **¿Verificar todas las páginas o la primera?** | (a) todas; (b) entrada + primera página; (c) solo CRC | **(b)** en v1: coste acotado; se documenta como verificación de entrada + primera página, no auditoría completa. |
| g | **¿La importación posterior es automática o manual?** | (a) automática al publicar; (b) siguiente ciclo; (c) botón | **(b/c):** la extracción es manual; una vez publicada, el flujo normal puede tomarla en el siguiente ciclo o con un botón «Importar ahora». No se extrae automáticamente. |

---

## 7. Partición, estimación y NOT RUN

### 7.1 Estimación

**L**, sin calibrar (la issue la deja a quien implemente). No baja a M: hay
modelo/migración de operaciones, dos lectores, extracción aislada, topes,
verificación, publicación, importación, estado, UI, limpieza, seguridad y
pruebas adversas. La dependencia `unar` **ya está** en la imagen; no se añade
una nueva, pero el trabajo de seguridad de extracción es nuevo.

### 7.2 Cortes verticales propuestos (acumulativos, no historias independientes)

| Corte | Contenido | ¿Cierra #344? | Esfuerzo | Riesgo |
|---|---|---|---|---|
| **A. Paquetes visibles y listado** | Detección por firma en Descargas, cola derivada, preview de entradas y topes; **sin extraer** | No; valor inmediato y valida contrato | **M** | Bajo/medio: lectura de metadatos |
| **B. ZIP de extremo a extremo** | Tabla de operaciones + extracción ZIP a temporal + verificación + publicación + import + limpieza | Parcial (ZIP) | **M/L** | Medio: estado, espacio, concurrencia |
| **C. RAR de extremo a extremo** | Reutiliza `utils/lector_rar`/`unar`; topes de paquete, una entrada a la vez, RAR5 sólido con causa | Sí para RAR, junto con B | **M/L** | Alto: subproceso, RSS/timeout, ADR 0015 |
| **D. Operación y robustez** | Reintento limpio, barrido de huérfanos, UI de progreso, informe/auditoría, pruebas adversas, espacio/telemetría | Cierra la experiencia completa | **M** | Medio: muchos casos límite |

Los cortes B y C comparten la capa de paquete; no se debe implementar RAR
antes de que ZIP valide la máquina de estados. El multivolumen (c) es una
historia siguiente, no un corte de esta.

### 7.3 PASS / FAIL / NOT RUN

- **PASS:** lectura del issue #344, #308/#305, de la evaluación RAR, del
  contrato #307, del ADR 0015 y del código actual; referencias con
  versión/commit; topes y contrato de seguridad documentados. No se declara
  aprobación.
- **FAIL:** ninguno de la ficha. El hueco de producto (el paquete de Descargas
  no existe en la UI/importador) es el problema que la historia debe cerrar,
  no un fallo de este benchmark.
- **NOT RUN:** todo lo que exige ejecutar (tabla siguiente).

| Comprobación | Estado | Por qué |
|---|---|---|
| Extraer un paquete RAR realista (varios GB, decenas de `.cbr`) | **NOT RUN** | No hay paquete real en este entorno; solo se leyó el contrato |
| Extraer un paquete ZIP realista | **NOT RUN** | Ídem |
| Medir tiempo total, pico de RSS y pico de disco temporal en la Pi | **NOT RUN** | Requiere hardware y muestra; AC9 |
| Bomba real ZIP/RAR, ratio falso, tamaño declarado falso | **NOT RUN** | #307 probó ZIP de una página; #308 probó daños de página, no un paquete completo |
| Path traversal, symlink y hardlink en un paquete real | **NOT RUN** | Hay fixtures hostiles del lector RAR, pero no la capa de paquete |
| Multivolumen real | **NOT RUN** | Fuera de alcance propuesto; solo detección |
| Paquete RAR cifrado | **NOT RUN** | El censo no tenía RAR cifrados; no hay muestra |
| Reinicio/muerte a mitad de extracción | **NOT RUN** | No se implementó |
| UI, estado durable, migración | **NOT RUN** | Esta ficha no toca código |
| Sonarr/Radarr/Kapowarr/Mylar3/ComicTagger/Calibre ejecutados | **NOT RUN** | Solo lectura de código |
| PASS/FAIL de las referencias | **PASS de lectura, NOT RUN de ejecución** | No se presentan como medición |

**No se declara aprobado** ningún diseño de §5 ni ninguna recomendación de §6;
el PO decide. La ficha caduca el **2027-01-15** o antes si cambia el lector
RAR, el importador, la imagen o el contrato de paquetes.
