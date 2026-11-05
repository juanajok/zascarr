# Ficha de benchmarking — BL-DUP0 (#263): duplicados reales y contrato para actuar

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). **Spike
> documental**: no escribe código de producto, no mueve ni borra nada y no
> consulta fuentes externas. Decide el PO; esta ficha es insumo, no aprobación.
>
> - **Fecha:** 2026-11-05
> - **SHA contrastado:** `1b0e2ad` (`main` al leer los ficheros citados). El
>   árbol compartido está ahora en `3456697` (rama `feat/300-portadas-v2`) y los
>   ficheros que cita esta ficha —`library_audit.py`, `utils/fs.py`, `models`,
>   `importer.py`— no cambiaron entre ambos (diff vacío). Hay además cambios sin
>   commitear de otros procesos en `src/`/`tests/`, ajenos a esta ficha.
> - **Feature padre:** #262 (BL-DUP). Historias: #264 (apartar), #265 (enlazar),
>   #266 (carpetas).
> - **Alcance de esta ficha:** referencias, restricciones heredadas, métricas
>   delta sobre el censo #297 y recomendación D1–D4. **No** implementa, no mide
>   la biblioteca real sin autorización y no publica rutas ni nombres.
> - **Nivel:** spike P1. No se incluye matriz 0–5: no se elige un producto
>   entero para adoptar; se elige un contrato. La tabla de referencias y la de
>   decisión D1–D4 cumplen esa función.

---

## 0. Resultado en una línea

Ninguna referencia resuelve el caso de ZascArr tal cual: **Komga borra**
(permanente), **Sonarr/Radarr usan papelera con purga automática**, **Mylar3
decide por tamaño/formato** y **Kapowarr sobrescribe** el destino. Lo que se
adopta es el **concepto** de papelera/cuarentena y la detección por contenido
(SHA-256, ya en B16), no su automatismo. ZascArr debe **construir sobre B16**:
cuarentena en la misma montura, mover solo contenido idéntico, decidir la
persona, comprobante idempotente y deshacer; **sin borrar, sin puntuación y sin
purga automática** en la primera versión.

---

## 1. Problema y datos de partida (B16 + censo #297)

**Problema local.** La auditoría B16 (`services/library_audit.py`) ya detecta
cinco clases —mismo contenido, misma obra con otra copia, carpeta repetida,
carpeta vacía, no reconocido— y persiste un informe en `ImportRun`
(`details.kind == "audit"`). Es **solo lectura**: el coleccionista ve «X GB
recuperables» y no puede actuar. El importador, además, **descarta en silencio**
el contenido idéntico: el catálogo conoce **una** de las copias
(`importer.py:703-705`). BL-DUP añade la acción; BL-DUP0 mide y compara antes
de diseñarla.

**Lo que B16 ya hace, verificado en el código:**

| Hecho | Evidencia |
|---|---|
| Hashea solo ficheros que comparten tamaño (dos tamaños distintos no pueden ser idénticos) | `services/library_audit.py:216-243` |
| Agrupa por hash; `bytes_recuperables = size × (copias − 1)` | `library_audit.py:73-83,237-243` |
| Deduplica el recorrido por inodo `(st_dev, st_ino)` | `library_audit.py:194-209`; `utils/fs.py:179-208` |
| Persiste contadores y listas en `import_runs.details`; **recorta cada lista a 200** y marca `truncado` | `library_audit.py:368-405` |
| `ImportRun.details` es un informe para pintar, no una API campo a campo | `models/__init__.py:781-801` |
| El importador descarta duplicados y solo deja la primera copia en catálogo | `services/importer.py:703-705`; censo #297, §«Interpretación» |

**Censo #297 (base que se reutiliza, no se repite).** `docs/design/censo-disco-vs-base-2026-10-22.md`:
252 ficheros del disco sin fila; **222 copias exactas** (217 `.cbr`/`.cbz` +
5 sin extensión); **8,1 GB** las 217 de `.cbr`/`.cbz`; **0 enlaces duros**
(`stat %h = 1`); grupos que cruzan carpetas. Además: 29 contenidos nuevos
(RAR/TAR/sin extensión), 14 filas `is_missing` y 1 `.part`. La muestra se midió
en solo lectura; **no autoriza recuperar espacio**.

**Lo que falta medir** (delta sobre #297, definido en §7): grupos por clase,
grupos con copia en catálogo y vinculación, grupos que cruzan carpetas de
tradición, carpetas subconjunto y grupos que cruzan monturas.

---

## 2. Referencias consultadas (versión/commit y método)

Se leyeron contratos y código, no pantallas. No se ejecutaron las aplicaciones:
lo no ejecutado está en §8.

| Referencia | Versión / commit | Qué se leyó |
|---|---|---|
| **jdupes** | 1.31.3 (2026-10-20), commit `9af6c67530d2475cdf2e3e9d3256a5438ae667ad` (2026-11-01) | `README.md` (opciones), `jdupes.c`/`args.c` (orden y acciones) |
| **fdupes** | commit `a7c1da4c561a9f37c7f27bf2350404d209c86014` (2026-04-14); última release v2.4.0 | `fdupes.c` (ayuda, orden, borrado) |
| **Komga** | v1.29.2, commit `25c67d14eb748dd3fb9f6612c099959a077fc850` (2026-10-30) | `Hasher.kt`, `BookDtoDao.kt`, `BookController.kt`, `BookLifecycle.kt`, UIs `DuplicateFiles.vue` y `DuplicatePages*` |
| **Kavita** | 0.9.1.18, commit `9e177701c359090fa62e2e90aba571567c6cc680` (2026-11-01) | tarball completo del commit: `ProcessSeries.cs`, `Parser.cs`, `SeriesService.cs`, `UI/Web`; búsqueda de `duplicat` en todo el árbol |
| **Sonarr** | v4.0.20.3014, commit `c018578e4b79ee048575c02d7a8aa2b929e4b837` | `RecycleBinProvider.cs`, `UpgradeMediaFileService.cs`, `RecycleBinValidator.cs`, `ConfigService.cs` |
| **Radarr** | v6.4.4.10685, commit `479b6f2a17b5e5b0378659bc27401750f10829a7` | mismos ficheros que Sonarr (equivalencia verificada) |
| **Mylar3** | commit `cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316` (2026-03-25); release v0.8.3 | `helpers.py::duplicate_filecheck`, `PostProcessor.py::duplicate_process`, `config.py` (`DUPECONSTRAINT`, `DUPLICATE_DUMP`) |
| **Kapowarr** | v1.3.2, commit `c191dda6617929c81292483a8cc07f631111dae2` (2026-09-14) | `post_processing.py`, `volumes.py`, `download_queue.py`; búsqueda de duplicados en `backend/` |
| **Documentación propia** | `1b0e2ad` | `benchmark-integridad-hash-dedupe.md`, `censo-disco-vs-base-2026-10-22.md`, `B20-exportacion-kavita.md`, `services/library_audit.py`, `utils/fs.py`, `models/__init__.py` |

**Enlaces de contraste** (los ficheros citados están en el commit indicado):
[jdupes](https://codeberg.org/jbruchon/jdupes/src/commit/9af6c67530d2475cdf2e3e9d3256a5438ae667ad/README.md),
[fdupes](https://github.com/adrianlopezroche/fdupes/blob/a7c1da4c561a9f37c7f27bf2350404d209c86014/fdupes.c),
[Komga](https://github.com/gotson/komga/tree/25c67d14eb748dd3fb9f6612c099959a077fc850),
[Kavita](https://github.com/Kareadita/Kavita/tree/9e177701c359090fa62e2e90aba571567c6cc680),
[Sonarr](https://github.com/Sonarr/Sonarr/tree/c018578e4b79ee048575c02d7a8aa2b929e4b837),
[Radarr](https://github.com/Radarr/Radarr/tree/479b6f2a17b5e5b0378659bc27401750f10829a7),
[Mylar3](https://github.com/mylar3/mylar3/tree/cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316),
[Kapowarr](https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2).

**Búsqueda en Kavita (para no inferir ausencia por no encontrarla).** Se
descargó el árbol completo del commit y se buscó `duplicat` en todo el código
(`Kavita.Services`, `Kavita.Server`, `UI/Web`). Lo encontrado es: colisión de
**series** con el mismo nombre normalizado (`ProcessSeries.cs:107-116,295+`,
que se reporta y aborta la actualización) y normalización de marcadores de
volumen/capítulo en `Parser.cs`; **no se encontró** detector de
libros/ficheros duplicados ni endpoint/UI de duplicados. No se afirma que no
exista en otra versión: se afirma qué hay en `0.9.1.18`.

---

## 3. Cómo lo resuelve cada referencia (contrato, no pantalla)

### 3.1 jdupes y fdupes — el criterio de orden y los enlaces duros

- **jdupes:** por defecto **no actúa**: agrupa e imprime. `-d` pregunta qué
  fichero conservar y borra el resto; `-N` conserva el primero **sin
  preguntar**; `-L/--link-hard` convierte todos los duplicados en enlaces duros
  al **primero de la cadena**, también sin preguntar. El orden se elige con
  `-o name|time` (por defecto `name`) y `-O` da prioridad al orden de los
  argumentos. `-1` evita emparejar entre sistemas de ficheros (`README.md:108-145`,
  `:250-345`). Unidad: **fichero** con el mismo contenido.
- **fdupes:** mismo modelo; `-d` pregunta, `-N` conserva el primero y borra el
  resto; el orden por defecto es **mtime** y `-o time|ctime|name` lo cambia;
  `-H` considera enlaces duros como duplicados. **No crea enlaces duros**:
  su `-L` es `--maxsize`, no `--link-hard` (`fdupes.c:1416-1469`; enum
  `ORDER_MTIME` en `:77-82`). Unidad: fichero.
- **Lo que ZascArr no copia:** el orden es una **pista de presentación**, no
  una regla de decisión; `-N` y `-L` automatizan una elección que aquí es del
  coleccionista. Cuando BL-DUP2 enlace, lo hará solo con contenido idéntico,
  misma montura y decisión explícita; nunca sobre un CBZ que se va a parchear
  (mismo inodo; `B20-exportacion-kavita.md` §3 y §9).

### 3.2 Komga — duplicados de fichero por hash, borrado permanente

- **Qué detecta:** libros con el mismo `fileHash` (XXH3-128, semilla 0,
  `infrastructure/hash/Hasher.kt:16-37`), agrupados por hash y tamaño
  (`BookDtoDao.kt:275-296`). Endpoint `GET /api/v1/books/duplicates` solo
  admin (`BookController.kt:246-265`); la UI agrupa por `fileHash` y muestra un
  botón de borrar por libro (`DuplicateFiles.vue`).
- **Qué decide:** la persona, libro a libro. El borrado es **permanente**:
  `BookLifecycle.deleteBookFiles` hace `deleteIfExists()` del fichero y luego
  `softDeleteMany` del libro (`BookLifecycle.kt:546-575`); no hay cuarentena
  ni deshacer. **Unidad:** fichero/libro.
- **Otro eje (páginas):** además detecta páginas repetidas por hash y puede
  borrarlas automáticamente si el hash conocido tiene acción `DELETE_AUTO`
  (`PageHashLifecycle.kt:48-55`). Es otra unidad (página), no un fichero.
- **Qué haría ZascArr distinto:** misma identidad por contenido, pero sin
  borrado permanente; el equivalente a `page-hash` no aplica a un CBZ (las
  páginas viven dentro del archivo).

### 3.3 Kavita — colisión de series, no duplicados de fichero

- **Qué detecta:** al actualizar una serie, `GetFullSeriesByAnyName` puede
  devolver **varias series** con el mismo nombre normalizado; se captura la
  excepción, se construye un informe con las series en colisión y se devuelve
  `UpdateFailed` (`ProcessSeries.cs:107-116,295-325`). Es una colisión de
  **identidad de serie** durante el escaneo, no una comparación de ficheros.
- **Qué decide:** no elige ni borra: **informa y no actualiza**. El
  bibliotecario resuelve fuera. **Unidad:** serie/nombre.
- **Qué haría ZascArr distinto:** B16 ya separa «mismo contenido» de «misma
  obra»; para duplicados de fichero no hay nada que copiar de Kavita. Se
  adopta solo la idea de **no fusionar en silencio y reportar la colisión**.

### 3.4 Sonarr / Radarr — ficheros sustituidos y papelera

- **Qué resuelve:** al importar una mejora, el fichero anterior se sustituye.
  `UpgradeMediaFileService` llama a `RecycleBinProvider.DeleteFile` antes de
  colocar el nuevo (`UpgradeMediaFileService.cs:56-75`).
- **Qué decide:** el sistema, por la decisión de *upgrade* (calidad/idioma), no
  la persona; si no hay `RecycleBin` configurada, **borra permanentemente**
  (`RecycleBinProvider.cs:69-84`). Si la hay, mueve conservando la subcarpeta
  relativa, evita pisar con sufijo `_N` y fija `mtime` (`:90-135`). La limpieza
  automática existe: `RecycleBinCleanupDays` por defecto **7**
  (`ConfigService.cs:106-109`; `RecycleBinProvider.cs:160-197`). El validador
  rechaza que la papelera coincida con una carpeta de serie o sea su padre
  (`RecycleBinValidator.cs:20-39`); no es una garantía general de anidamiento.
  No hay verificación por hash en esta ruta ni deshacer.
- **Qué haría ZascArr distinto:** no sustituir por calidad; solo apartar
  **contenido idéntico** y por decisión de la persona; sin purga automática;
  con comprobante y deshacer. La papelera de Sonarr puede estar en otra
  montura y usa `IDiskTransferService` (cruce no auditado aquí:
  **[sin verificar directamente]**); ZascArr exige misma montura para que el
  movimiento sea atómico y reversible.

### 3.5 Mylar3 — duplicado de número, decisión automática y «dump»

- **Qué detecta:** `duplicate_filecheck` compara por `IssueID` (misma serie +
  número) y usa el tamaño/formatos (`DUPECONSTRAINT`: `filesize`, prioridad
  CBR/CBZ) y marcas «fixed»; no compara hashes (`helpers.py:2231-2400`).
  **Unidad:** número/edición, no fichero idéntico.
- **Qué decide:** automáticamente qué copia conservar (`dupe_file`/`dupe_src`).
  Si `DDUMP`/`DUPLICATE_DUMP` están configurados, el perdedor se **mueve** a
  una carpeta de volcado para intervención manual; en modo copia puede dejarlo
  en su sitio (`PostProcessor.py:208-245`; `config.py:189-192`).
- **Debilidades reales:** el propio chequeo ha fallado por configuración
  (`#488`, `TypeError` con `dupeconstraint` nulo), ha tenido que corregir la
  ruta completa en la detección (`#1680`) y el proyecto reconoce el riesgo de
  **sobrescribir** al renombrar números repetidos (`#1596`). Evidencia de que
  la decisión automática por tamaño/formato es frágil y destructiva.
- **Qué haría ZascArr distinto:** el «dump» como cuarentena es el patrón más
  cercano, pero **sin elegir ganador por tamaño/formato** y solo con hashes
  idénticos; nunca mover «misma obra, otra copia» (eso es BL-R6).

### 3.6 Kapowarr — sin detector de duplicados; reemplazo del destino

- **Qué detecta:** no se encontró detección de ficheros duplicados. Lo que
  existe es identidad de **volumen** (`VolumeAlreadyAdded`,
  `volumes.py:1118-1143`) y deduplicación de **enlaces de descarga** en cola
  (`download_queue.py:483+`).
- **Qué decide:** al postprocesar, si el destino generado ya existe, **borra el
  destino y mueve el nuevo** (`post_processing.py:121-127` y `:182-188`,
  `delete_file_folder`); no hay papelera, cuarentena ni deshacer. **Unidad:**
  ruta generada por número/volumen, no contenido.
- **Qué haría ZascArr distinto:** nunca borrar el destino; si el nombre colisiona,
  cuarentena con nombre único y decisión humana. La identidad de volumen de
  Kapowarr sirve para su catálogo, no para deduplicar contenido.

---

## 4. Adoptar / adaptar / descartar (por idea, con motivo)

| Idea | Resultado | Motivo |
|---|---|---|
| Identidad por **contenido** (SHA-256) y no por nombre/tamaño | **Adoptar** | B16 y el importador ya la usan; es la única base segura para «idéntico». fdupes/jdupes y Komga confirman el patrón |
| Agrupar y **mostrar hechos** de cada copia; decidir la persona | **Adoptar** | Principio de #262 y ADR 0008; jdupes/fdupes preguntan, pero Sonarr/Mylar deciden solos |
| Papelera/cuarentena en lugar de borrar | **Adoptar** (concepto) | Sonarr `RecycleBin`, Mylar `DUPLICATE_DUMP`; Komga/Kapowarr borran, y el invariante de ZascArr es no borrar |
| Mover conservando ruta relativa y evitar colisiones | **Adoptar** | Sonarr conserva subcarpeta y sufija `_N` |
| **Misma montura** para mover con `os.replace` y poder deshacer | **Adaptar** | Sonarr puede usar otra montura y delegar en transferencia; aquí `safe_move` cae a copia+borrado (`utils/fs.py:89-171`) y perdería atomicidad |
| Cuarentena **fuera** de la biblioteca | **Descartar** en v1 | Un bind mount separado puede dar EXDEV al renombrar; y hay que excluirla de todos modos. Se prefiere subcarpeta oculta del mismo montaje; si se necesita aislar de otros lectores, se estudia montar el padre (fuera de alcance) |
| Purga automática a los N días | **Descartar** | Sonarr la tiene por defecto (7 días); el principio de #262 es «nada se borra sin consentimiento» |
| Borrado permanente | **Descartar** | Komga y Kapowarr lo hacen; contradice «nada se borra en la primera versión» |
| Elegir ganador por tamaño/formato/calidad | **Descartar** | Mylar lo hace y tiene quejas de sobrescritura (#1596); #262 prohíbe puntuación y preselección |
| Enlaces duros ya | **Descartar** hasta BL-DUP2 | jdupes `-L` y B20 muestran el riesgo de inodo compartido; requiere misma montura e idéntico verificado; va en #265 |
| Reflinks/CoW | **Descartar** | Casi nunca disponibles en la Pi; #262 ya lo descartó; BL-DUP0 podría reabrirlo con datos, pero no hay evidencia de soporte |
| `send2trash`/papelera del SO | **Descartar** | Dependencia nueva y comportamiento fuera de la BD; #262 ya lo descartó |
| Detección de **páginas** duplicadas (Komga) | **Descartar** en BL-DUP | Otra unidad (página); B16 opera fichero; no resuelve el ahorro de ficheros idénticos |
| Colisión de series por nombre (Kavita) | **Adoptar** solo como aviso, no como detector | Informa y no fusiona; es una identidad de serie, no un duplicado de fichero |
| Cuarentena reversible sobre B16 + `safe_move` | **Construir sobre lo propio** | B16 aporta la detección y `safe_move` la base de no-destrucción; ninguna referencia hace hash + decisión humana + deshacer |
| Comprobante de operación idempotente | **Construir sobre lo propio** | Patrón de `asignacion_operaciones` (0017), `alta_operaciones` (0018), `vinculacion_operaciones` (0019); `import_runs.details` no sirve: es un informe de pantalla y trunca a 200 |

**Licencias revisadas por fichero** (no se reutiliza código; si se reutilizara,
se revisaría el fichero concreto): jdupes **MIT** (`LICENSE.txt`), fdupes
**MIT** (`LICENSE`), Komga **MIT** (`LICENSE`), Kavita **GPL-3.0** (`LICENSE`),
Sonarr **GPL-3.0** (`LICENSE.md`), Radarr **GPL-3.0** (`LICENSE`), Mylar3
**GPL-3.0** (`LICENSE`), Kapowarr **GPL-3.0** (`LICENSE`). ZascArr es GPL-3.0;
la copia de código GPL sería compatible, pero aquí solo se copian patrones.

---

## 5. Restricciones técnicas verificadas (criterio 3)

Se heredan de `benchmark-integridad-hash-dedupe.md`; solo se comprueba lo que
faltaba.

### 5.1 EXDEV y misma montura

- `utils/fs.py::_same_filesystem` (`:89-94`) compara `st_dev`; `safe_move`
  (`:96-171`) usa `os.replace` en el mismo sistema y, si el kernel devuelve
  `EXDEV`, **copia y verifica antes de borrar**. Es correcto para importar,
  pero para cuarentena/deshacer se quiere un **rename atómico** (sin copia y
  sin ventana de dos copias): la cuarentena debe estar dentro del **mismo punto
  de montaje**, no solo del mismo `st_dev`.
- El compose monta la biblioteca como **un único bind mount**:
  `${HOST_LIBRARY_DIR}:/media/library` (`docker-compose.yml:163`). Una
  subcarpeta oculta de `/media/library` cumple misma montura; un bind aparte
  (aunque sea el mismo disco) puede fallar `rename` igual (el propio
  `safe_move` documenta el caso de bind mounts con `st_dev` igual y `EXDEV`:
  `utils/fs.py:140-145`).
- `B20-exportacion-kavita.md` §3 confirma el patrón `os.link()` → caer a copia
  por `EXDEV`; para BL-DUP2 el enlace duro exige misma montura.

### 5.2 PUID/PGID y permisos

- El contenedor corre con `PUID`/`PGID` resueltos por bootstrap
  (`docker-compose.yml:158-159`; `bootstrap.sh:408-416`); el entrypoint ajusta
  el usuario interno y **solo** da permiso al código y a `covers`, no a la
  biblioteca del usuario (`docker-entrypoint.sh:56-68`). La cuarentena la crea
  el propio servicio con ese UID/GID o bootstrap, **nunca** un `chown -R` sobre
  la colección.
- Preflight exigido: la raíz de cuarentena debe ser escribible por el UID de
  servicio; si no, **fallar cerrado** con un mensaje que diga qué carpeta y qué
  hacer. No se puede “arreglar” con `chmod 777`.

### 5.3 Exclusión de la cuarentena

`Path.rglob` y `os.walk` **no saltan** carpetas ocultas por sí solos: hay que
excluir por prefijo. Recorridos que deben usar el helper:

| Recorrido | Evidencia |
|---|---|
| Importador (solo descargas) | `services/importer.py:468-479` (`_scan_dirs`); si en el futuro escanea biblioteca, mismo helper |
| Adopción y registro incremental | `library_adopter.py:267,289-291,318` (`recorrer_comics`, `rglob`, `inventario`) |
| Auditoría | `library_audit.py:194-209,301-311,318-349` (`rglob` de ficheros, carpetas vacías y no reconocidos) |
| Comprobación de disco (BL-R3 #232, esquema #231) | `importer.py:626-660`: **no recorre**, comprueba rutas registradas; la operación debe dejar el catálogo coherente (no registrar la cuarentena como si estuviera en la biblioteca) |

La exclusión se centraliza en un helper (`utils/fs.py`) y se aplica también a
`listar_comics` (importador), aunque hoy sus `_scan_dirs` no recorran la
biblioteca: así la exclusión no depende de dónde se monte la cuarentena. **Hoy
ninguno de esos recorridos excluye una cuarentena: el helper no existe**, así
que esto es un requisito de implementación de BL-DUP1, no una restricción ya
resuelta. Se prueba con una carpeta señuelo dentro de la cuarentena: no
aparece en inventario, auditoría, adopción ni en la lista de no reconocidos.

---

## 6. Recomendación D1–D4 (criterio 4) y propuesta de ADR

| Decisión | Recomendación | Evidencia clave |
|---|---|---|
| **D1** dónde y exclusión | `<library>/.zascarr-cuarentena`, misma montura, creada con PUID/PGID, excluida por helper en todos los recorridos | `utils/fs.py:89-171` (EXDEV), compose de un solo bind, `rglob` no salta ocultos |
| **D2** vaciar | Solo acción explícita con vista previa; **sin purga automática** en v1 | Sonarr limpia a los 7 días (`ConfigService.cs:106-109`); #262 prohíbe borrar sin consentimiento |
| **D3** comprobante | Dos tablas + token de vista previa + idempotencia + estados de deshacer; migración nueva | `ImportRun.details` trunca a 200; patrón de operaciones 0017–0019 |
| **D4** postura | ADR 0015: mover a cuarentena es una operación de la colección, reversible, sin borrado ni puntuación | Referencias §3 y principios de #262 |

### D1 — Dónde vive la cuarentena

**Recomendación:** `QUARANTINE_PATH` configurable, por defecto
`<library>/.zascarr-cuarentena` (subcarpeta oculta del **mismo bind mount**);
diseño `<quarantine>/<operacion_id>/<ruta relativa original>` para que el
deshacer sepa volver sin ambigüedad. Validar en runtime que la ruta está dentro
de la biblioteca y que comparte su punto de montaje; si no, **abortar** (no
caer a copia). Crear en bootstrap junto a las carpetas de biblioteca
(`bootstrap.sh:427-450`) o en el primer uso, siempre con PUID/PGID; si no es
escribible, fallar cerrado.

**Evidencia:** `safe_move`/EXDEV (§5.1), compose de un solo bind (§5.1),
PUID/PGID (§5.2), `rglob` no salta ocultos (§5.3), Sonarr conserva subcarpeta
pero permite otra montura, Mylar usa un dump manual. **Consecuencia:** la
cuarentena puede quedar visible para otros lectores que escaneen la misma raíz
(Kavita); se documenta y se puede aislar en una decisión posterior (montar el
padre). No
se oculta con `.` esperando que el importador la ignore: la exclusión es
explícita.

### D2 — Vaciar la cuarentena

**Recomendación:** en v1 **no hay purga automática**. «Vaciar» es una acción
explícita, separada, con vista previa de cuántos ficheros y bytes se pierden y
confirmación reforzada; irreversible y con aviso de que el deshacer deja de
estar disponible. Sin programador ni `send2trash`.

**Evidencia:** Sonarr tiene `RecycleBinCleanupDays = 7` por defecto
(`ConfigService.cs:106-109`) y limpia en tarea; Mylar deja el dump a
intervención manual; #262 dice «nada se borra definitivamente en la primera
versión». **Consecuencia:** el disco puede crecer; la pantalla debe mostrar
tamaño y fecha, y no prometer espacio recuperado hasta vaciar.

### D3 — Comprobante de la operación

**Recomendación:** comprobante propio con dos tablas (borrador, no migración
en este encargo):

```text
cuarentena_operaciones(id, estado, token_hasta, creada, actualizada,
                       total_files, total_bytes)
cuarentena_items(id, operacion_id, origen, destino, sha256, size_bytes,
                 mtime_ns, estado, error, actualizada)
```

Estados de operación: `preparada`, `confirmada`, `deshecha`, `cancelada`;
estados de ítem: `pendiente`, `movida`, `deshecha`, `error`. Token de vista
previa firmado con caducidad (como `alta_operaciones`/`vinculacion_operaciones`);
la confirmación repite **exactamente** la lista del token y comprueba hash y
`mtime` antes de mover; reintento con el mismo token devuelve el mismo informe;
no se puede reutilizar un token deshecho. Índice parcial para que un fichero no
tenga dos operaciones vivas. Las rutas se guardan en la BD local para el
deshacer; **nunca** se publican.

**Evidencia:** `ImportRun.details` es un informe de pantalla y **trunca a 200**
(`library_audit.py:368-405`; `models/__init__.py:797-801`), no sirve para
idempotencia por ítem; `asignacion_operaciones` (migración 0017, ADR 0006),
`alta_operaciones` (0018) y `vinculacion_operaciones` (0019) son el patrón
probado de comprobante + token + purga. **Consecuencia:** migración nueva y
ADR (D4); el token de vista previa usa el TTL corto de revisión (15 min,
`services/tokens_revision.py:30`) y el comprobante se conserva 24 h
(`RETENCION_HORAS` de `alta_serie.py:81`/`vinculacion.py:57`); los ítems se
conservan mientras exista la cuarentena (para el deshacer) y se purgan al
vaciar.

### D4 — Postura nueva: ZascArr mueve ficheros de la colección

**Recomendación:** ADR propio **antes** de «Lista para desarrollar». Propuesta
de ADR 0015 (no creado en este encargo):

`docs/adr/0015-cuarentena-y-operaciones-sobre-la-coleccion.md`

- **Contexto:** hasta hoy ZascArr solo mueve al importar; B16 es solo lectura;
  BL-DUP pide apartar una copia idéntica sin perder nada.
- **Decisión:** se permite **mover** un fichero no registrado a una cuarentena
  del mismo montaje, tras vista previa y confirmación, con hash verificado en
  el momento, comprobante idempotente y deshacer; **no se borra**, **no se
  sustituye**, **no se elige por puntuación**, **no hay purga automática**; los
  enlaces duros y las carpetas van en historias posteriores.
- **Alternativas descartadas:** borrado permanente (Komga/Kapowarr), papelera
  del SO/`send2trash` (dependencia), papelera con purga automática (Sonarr),
  copia a otra montura (EXDEV/espacio), enlace duro ya (BL-DUP2).
- **Consecuencias:** nueva tabla/migración, nueva superficie de UI, disciplina
  de exclusión en cuatro recorridos, y un riesgo operativo nuevo que el ADR
  acota; el PO decide.
- **Invariantes que el ADR debe fijar:** solo contenido idéntico verificado en
  el momento; decide la persona y ninguna copia va premarcada; nunca se borra
  ni se sobrescribe; mover y deshacer en la misma montura; catálogo coherente
  (una fila nunca apunta a una ruta movida); coste acotado a los ficheros
  elegidos, sin analizar imágenes; rutas y nombres no se publican.

### IGUALAR / MEJORAR (semilla para la spec)

**IGUALAR (mínimos):**
1. Identidad por **contenido** (hash), nunca por nombre/tamaño, como jdupes/fdupes
   y Komga.
2. **Reversibilidad**: mover a cuarentena, no borrar, conservando la ruta
   relativa como Sonarr.
3. **Decisión humana** con hechos lado a lado, sin preselección, como Komga; no
   como la elección automática de Mylar.
4. **Comprobante idempotente** y catálogo coherente, como las operaciones
   0017–0019.

**MEJORAR (huecos de las referencias):**
1. **Exclusión explícita** de la cuarentena en todos los recorridos: Sonarr y
   Mylar no la garantizan en un árbol compartido y `rglob` no salta ocultos.
2. **Misma montura obligatoria** y rename atómico: Sonarr delega la
   transferencia y puede cruzar monturas; aquí se aborta si no es atómico.
3. **Sin purga automática ni scoring**: Sonarr limpia a los 7 días y Mylar elige
   por tamaño/formato; ZascArr no.
4. **Medir antes de construir** (censo #297 + delta) en lugar de extrapolar de
   otra biblioteca.

---

## 7. Plan de medición delta (criterio 2) — EJECUTADA EN PARTE (M1–M4; M5 NOT RUN)

**Estado:** M1–M4 **ejecutadas** en la Pi del PO el 2026-11-05, en una sesión
`default_transaction_read_only=on`; resultados y caveat de truncado en
[`medicion-BL-DUP0-2026-11-05.md`](medicion-BL-DUP0-2026-11-05.md). **M5 sigue
NOT RUN** (requiere `stat` dentro del contenedor de la app). La medición no
volvió a ejecutar la auditoría ni escribió nada.

### 7.1 Las cinco métricas

| # | Métrica | Unidad | Definición operativa | Fuente | Estado |
|---|---|---|---|---|---|
| M1 | Grupos por clase | grupo | `mismo_contenido`, `misma_obra`, `carpetas_repetidas`, `carpetas_vacias`, `no_reconocidos`; para idénticos, ficheros y bytes | `import_runs.details` + contadores | **Ejecutada**; contadores completos; lista 200/215 |
| M2 | Grupos idénticos con copia en catálogo (y vinculada) | grupo | ≥1 ruta del grupo coincide con `files.file_path` con `is_missing = false`; «vinculada» = esa fila tiene `issue_id` no nulo | `details` + `files` | **Ejecutada** sobre 200/215 (mínimo) |
| M3 | Grupos que cruzan carpetas de tradición | grupo | ≥2 primeras carpetas distintas bajo la biblioteca (proxy de tradición: `Comics`, `Manga`, `Tebeos`…); variante estricta con `series.tradition` para grupos con ≥2 copias en catálogo | `details` + `files`/`issues`/`series` | **Ejecutada** sobre 200/215 (mínimo) |
| M4 | Carpetas subconjunto | par y carpeta | `solo_en_a = 0` o `solo_en_b = 0` en `carpetas_repetidas`; contar pares y carpetas distintas | `details` | **Ejecutada** (6 pares; mínimo por la regla del encargo) |
| M5 | Grupos que cruzan monturas | grupo | ≥2 `st_dev` distintos (o puntos de montaje distintos) entre las rutas del grupo; ficheros no `stat`ables aparte | rutas + `stat`/`/proc/self/mountinfo` dentro del contenedor | **NOT RUN** |

**Delta sobre #297:** el censo ya da 222 copias exactas (217 `.cbr`/`.cbz` +
5 sin extensión), 8,1 GB las 217, sin enlaces duros. M1–M5 añaden grupos,
catálogo, carpeta de tradición, subconjunto y monturas; **no se reejecuta el
censo completo** si sus cifras siguen válidas.

### 7.2 Consultas de solo lectura (M1–M4)

**Consultas ejecutadas** el 2026-11-05 sobre el informe
`48b5624f-49f6-4382-aa69-18d7bcb75b21` (2026-10-29 21:06:30 UTC), filtrando por
`id` en lugar del «último informe». El informe tenía **`truncado = true`**: la
lista se recortó a 200 de 215 grupos y M2–M4 son **mínimos**, no totales; los
contadores `duplicate_count`/`unsorted_count` sí son completos. El respaldo de
§7.3 no se ejecutó (no era necesario para publicar el mínimo).

```sql
-- Todo en una transacción de solo lectura: se lanza con
-- PGOPTIONS='-c default_transaction_read_only=on'
WITH u AS (
  SELECT id, started_at, files_scanned, duplicate_count, unsorted_count, details
  FROM import_runs
  WHERE details->>'kind' = 'audit'
  ORDER BY started_at DESC
  LIMIT 1
)
SELECT id, started_at, files_scanned, duplicate_count, unsorted_count,
       details->>'truncado' AS truncado,
       details->>'files_hashed' AS files_hashed,
       details->>'bytes_hashed' AS bytes_hashed,
       details->>'bytes_recuperables' AS bytes_recuperables,
       jsonb_array_length(details->'mismo_contenido') AS grupos_identicos_lista,
       (SELECT coalesce(sum(jsonb_array_length(e->'rutas')), 0)
          FROM jsonb_array_elements(details->'mismo_contenido') e) AS ficheros_identicos_lista
FROM u;
```

```sql
-- M2: copia en catálogo y vinculación (solo grupos de la lista)
WITH u AS (
  SELECT details FROM import_runs
  WHERE details->>'kind' = 'audit'
  ORDER BY started_at DESC LIMIT 1
), g AS (
  SELECT e->>'sha256' AS sha,
         ARRAY(SELECT jsonb_array_elements_text(e->'rutas')) AS rutas
  FROM u, jsonb_array_elements(u.details->'mismo_contenido') e
)
SELECT count(*) AS grupos,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM files f
         WHERE f.file_path = ANY(g.rutas) AND NOT f.is_missing
       )) AS con_copia_en_catalogo,
       count(*) FILTER (WHERE EXISTS (
         SELECT 1 FROM files f
         WHERE f.file_path = ANY(g.rutas) AND NOT f.is_missing
           AND f.issue_id IS NOT NULL
       )) AS con_copia_vinculada
FROM g;
```

```sql
-- M3a: primer nivel bajo la biblioteca (proxy; no publica las rutas)
WITH u AS (
  SELECT details FROM import_runs
  WHERE details->>'kind' = 'audit'
  ORDER BY started_at DESC LIMIT 1
), g AS (
  SELECT e->>'sha256' AS sha,
         ARRAY(SELECT jsonb_array_elements_text(e->'rutas')) AS rutas
  FROM u, jsonb_array_elements(u.details->'mismo_contenido') e
), r AS (
  SELECT g.sha, x.ruta,
         -- ajustar el prefijo si LIBRARY_PATH no es /media/library
         split_part(regexp_replace(x.ruta, '^/media/library/?', ''), '/', 1) AS raiz
  FROM g CROSS JOIN LATERAL unnest(g.rutas) AS x(ruta)
)
SELECT count(*) FILTER (WHERE n > 1) AS cruzan_primera_carpeta,
       count(*) FILTER (WHERE n = 1) AS una_sola_carpeta,
       count(*) FILTER (WHERE n = 0) AS sin_raiz
FROM (SELECT sha, count(DISTINCT raiz) AS n FROM r GROUP BY sha) s;
```

```sql
-- M3b: tradición estricta (solo grupos con ≥2 copias en catálogo)
WITH u AS (
  SELECT details FROM import_runs
  WHERE details->>'kind' = 'audit'
  ORDER BY started_at DESC LIMIT 1
), g AS (
  SELECT e->>'sha256' AS sha,
         ARRAY(SELECT jsonb_array_elements_text(e->'rutas')) AS rutas
  FROM u, jsonb_array_elements(u.details->'mismo_contenido') e
), m AS (
  SELECT g.sha, s.tradition
  FROM g CROSS JOIN LATERAL unnest(g.rutas) AS x(ruta)
  JOIN files f ON f.file_path = x.ruta AND NOT f.is_missing
  JOIN issues i ON i.id = f.issue_id
  JOIN series s ON s.id = i.series_id
)
SELECT
  (SELECT count(*) FROM g) AS grupos,
  (SELECT count(*) FROM (SELECT sha FROM m GROUP BY sha
     HAVING count(DISTINCT tradition) > 1) z) AS cruzan_tradicion,
  (SELECT count(*) FROM (SELECT g.sha FROM g LEFT JOIN m ON m.sha = g.sha
     GROUP BY g.sha HAVING count(m.tradition) = 0) z) AS sin_mapeo;
```

```sql
-- M4: carpetas subconjunto (pares y carpetas distintas)
WITH u AS (
  SELECT details FROM import_runs
  WHERE details->>'kind' = 'audit'
  ORDER BY started_at DESC LIMIT 1
), c AS (
  SELECT e->>'ruta_a' AS a, e->>'ruta_b' AS b,
         (e->>'solo_en_a')::int AS solo_a,
         (e->>'solo_en_b')::int AS solo_b
  FROM u, jsonb_array_elements(u.details->'carpetas_repetidas') e
)
SELECT count(*) AS pares,
       count(*) FILTER (WHERE solo_a = 0) AS a_subconjunto_de_b,
       count(*) FILTER (WHERE solo_b = 0) AS b_subconjunto_de_a,
       count(*) FILTER (WHERE solo_a = 0 AND solo_b = 0) AS iguales
FROM c;
```

```sql
-- M4b: carpetas distintas que son subconjunto (no publica rutas)
WITH u AS (
  SELECT details FROM import_runs
  WHERE details->>'kind' = 'audit'
  ORDER BY started_at DESC LIMIT 1
), c AS (
  SELECT e->>'ruta_a' AS a, e->>'ruta_b' AS b,
         (e->>'solo_en_a')::int AS solo_a,
         (e->>'solo_en_b')::int AS solo_b
  FROM u, jsonb_array_elements(u.details->'carpetas_repetidas') e
), lados AS (
  SELECT b AS ruta FROM c WHERE solo_b = 0
  UNION ALL
  SELECT a AS ruta FROM c WHERE solo_a = 0
)
SELECT count(DISTINCT ruta) AS carpetas_subconjunto
FROM lados;
```

**Ejecución (sin imprimir credenciales; patrón del censo #297):**

```bash
# 1) guardar el bloque de la consulta en /tmp/dup0-m1.sql (o M2/M3/M4)
docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' \
  zascarr-db psql -U comics_admin -d zascarr -X -A -F $'\t' \
  < /tmp/dup0-m1.sql
```

### 7.3 M5 y respaldo si el informe está truncado

- **M5** necesita `stat` de las rutas dentro del contenedor de la app (para ver
  los mismos puntos de montaje que ZascArr). Propuesta: un script de medición
  **fuera de `src/`** (`scripts/medicion/medir_dup0_monturas.py`, no creado en
  este encargo) que lee por stdin líneas `sha<TAB>ruta`, hace `os.stat`, y
  agrupa por `sha` contando `st_dev` distintos y puntos de montaje de
  `/proc/self/mountinfo`; salida solo de recuentos. No escribe en la BD ni en la
  biblioteca. Si una ruta ya no existe, se cuenta aparte (`ausente`).
  Comando previsto (una vez exista el script y con autorización):
  ```bash
  # exportar solo sha+ruta a /tmp (no se publica); luego stat dentro de la app
  docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' zascarr-db \
    psql -U comics_admin -d zascarr -X -A -F $'\t' -c \
    "SELECT g->>'sha256', r FROM (SELECT details FROM import_runs WHERE details->>'kind'='audit' ORDER BY started_at DESC LIMIT 1) u, jsonb_array_elements(u.details->'mismo_contenido') g, jsonb_array_elements_text(g->'rutas') r" \
    > /tmp/dup0-grupos.tsv
  docker cp scripts/medicion/medir_dup0_monturas.py zascarr-app:/tmp/medir_dup0_monturas.py
  docker exec -i zascarr-app python3 /tmp/medir_dup0_monturas.py < /tmp/dup0-grupos.tsv
  ```
- **Truncado:** si `details->>'truncado'` es `true`, M2–M4 son mínimos. Respaldo
  en solo lectura: reutilizar los artefactos del censo #297
  (`scripts/medicion/censo_disco_vs_base.py`: inventario del disco, filas de la
  base y hashes de los ficheros sin registrar) para reconstruir los grupos
  completos; si esos artefactos ya no están, recalcular hashes solo de los
  ficheros que comparten tamaño (8,1 GB en la muestra), con
  `ionice -c3 nice -n19`, y **no** reejecutar el censo entero. Cualquier
  recálculo queda como NOT RUN hasta autorización.
- **Privacidad:** la salida que se publique lleva solo recuentos y porcentajes;
  las rutas, nombres y hashes se quedan en `/tmp` y no se pegan en la ficha, el
  issue ni el tablero.

### 7.4 Resultados publicados

M1–M4 quedaron **ejecutadas**; **M5 sigue NOT RUN**. Las cifras, la naturaleza
de cada una (completa o mínimo) y la lectura para D1–D4 están en
[`medicion-BL-DUP0-2026-11-05.md`](medicion-BL-DUP0-2026-11-05.md). No se
duplican aquí para que la ficha de resultados sea la única fuente de cifras.

---

## 8. PASS / FAIL / NOT RUN

| Criterio de #263 | Estado | Evidencia / motivo |
|---|---|---|
| 1. Ficha §13 con referencias, versiones, adoptar/adaptar/descartar y licencias | **PASS** | §2–§4; commit por referencia y licencia revisada |
| 2. Medición en solo lectura sobre biblioteca real, métricas delta | **PASS parcial / NOT RUN M5** | M1–M4 ejecutadas el 2026-11-05 con `truncado=true` (M2–M4 mínimos); M5 pendiente. Ficha: `medicion-BL-DUP0-2026-11-05.md` |
| 3. Restricciones técnicas comprobadas (EXDEV, PUID/PGID, exclusión, adopción/auditoría/#232) | **PASS (por código/documentación)** | §5: EXDEV y PUID/PGID heredados; la exclusión **no existe hoy** y queda como requisito de BL-DUP1. No se ha probado en la Pi: **NOT RUN** la ejecución |
| 4. Recomendación D1–D4 y propuesta de ADR | **PASS** | §6; ADR 0015 propuesto, no creado |
| 5. PASS/FAIL/NOT RUN separados | **PASS** | esta tabla |
| **FAIL** | — | Ninguno: no se ejecutó código que pudiera fallar; los hallazgos de Kavita/Komga no son fallos de ZascArr |
| **NOT RUN adicionales** | — | `jdupes`/`fdupes`/Komga/Kavita/Sonarr/Radarr/Mylar3/Kapowarr no se ejecutaron; solo lectura de código. `EXDEV` y `PUID/PGID` no se probaron en la Pi. No se abrió ningún contenedor ni se tocó la biblioteca. |

---

## 9. Casos de prueba que exigirá la spec (si D1–D4 se aceptan)

No se escriben aquí; son el contrato para BL-DUP1/BL-DUP2/BL-DUP3. Todos con
`tmp_path`/tmpfs y sin biblioteca real:

1. **Mover idéntico:** dos ficheros mismo hash; se mueve el elegido a
   cuarentena, el otro queda; el hash del movido se verificó antes; el original
   del elegido ya no está en su ruta.
2. **Hash distinto:** el fichero cambió entre vista previa y confirmación;
   abortar sin mover y sin dejar cuarentena parcial.
3. **Otra montura:** cuarentena en distinto punto de montaje (simulado) →
   abortar con error claro, sin copia silenciosa.
4. **Exclusión:** fichero señuelo dentro de cuarentena no aparece en
   inventario, adopción, auditoría ni no reconocidos.
5. **Deshacer:** mover y deshacer restaura la ruta y el hash; si la ruta está
   ocupada, no se pisa y se informa.
6. **Reintento:** mismo token/operación no mueve dos veces ni duplica el
   comprobante; token caducado no ejecuta.
7. **Corte a mitad:** matar el proceso entre dos ítems; al reiniciar, el
   comprobante reconcilia (movidos/ pendientes) sin perder ni duplicar.
8. **Sin colisión:** dos originales con el mismo nombre en cuarentena no se
   pisan.
9. **Fila registrada:** si la copia elegida tiene fila en `files`, o se rechaza
   (recomendado en v1) o se actualiza `file_path` en la misma operación; nunca
   queda una fila apuntando a una ruta movida.
10. **PUID/PGID:** la cuarentena creada por bootstrap/servicio es escribible por
    el UID de servicio; sin `chmod 777` ni `chown -R` sobre la colección.

---

## 10. Lo que esta ficha NO decide y caducidad

- No implementa BL-DUP1/2/3, no crea la tabla ni la migración, no crea el ADR
  0015 (solo lo propone), no toca la biblioteca ni la base.
- No decide la UI, el copy, el número máximo de ítems por vista previa ni el
  formato exacto del token: eso es de la especificación y del PO.
- No reabre reflinks/CoW: sin evidencia de soporte en la Pi; BL-DUP0 podría
  reabrirlo con datos, pero no es necesario para v1.
- No afirma que Kavita no tenga duplicados en otras versiones: solo documenta
  lo encontrado en `0.9.1.18`.
- **Caduca:** ~60 días → **2027-01-04**, o antes si cambia el censo #297, la
  normativa de cuarentena, las referencias o la historia #262.
