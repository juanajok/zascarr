# Ficha de benchmarking — leer mis tebeos en ZascArr (BL-LEC)

> Ficha de **nivel 2** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13): sirve
> contenido de los archivos de la biblioteca (seguridad), añade estado (progreso de lectura) y
> el primer JavaScript propio de la interfaz. Fecha: 2026-11-14. Contrastada con `origin/main`
> `6b8f53f`. **Insumo, no aprobación:** decide el PO.

## 1. Historia y problema observado

Como coleccionista, quiero abrir un tebeo de mi biblioteca y leerlo en ZascArr, en el PC, la
tablet o el móvil, retomando por donde lo dejé y pasando al siguiente número al acabar, sin
depender de otra aplicación.

**Decisiones del PO tomadas antes de esta ficha:**

| Fecha | Decisión |
|---|---|
| 2026-11-14 | **Lector propio** en ZascArr, aunque Kavita corra en la misma Pi. |
| 2026-11-14 | **OPDS sirve también contenido** (OPDS-PSE), como fase posterior. Cambia la decisión de BL-C5 (#160: «solo catálogo, no contenido»). |

**Origen:** una propuesta externa (pegada en el chat el 2026-11-13) para un lector por páginas
con FastAPI y JS sin dependencias. Esta ficha separa lo que se sostiene de lo que no.

## 2. Datos reales y medición de partida

| Dato | Valor | Origen |
|---|---|---|
| CBR en el disco de la biblioteca | 4.891 (202,1 GiB) | `find` de solo lectura, 2026-11-07 |
| CBZ | 746 (26,8 GiB) | ídem |
| PDF / CB7 | **2 / 1** | `find` de solo lectura, 2026-11-14 |
| Lector de RAR | `unar` por subproceso acotado, **de uno en uno** (`utils/lector_rar.py`, ADR 0015) | `main` |
| RAR sólidos | leer la última página de un sólido grande tarda **segundos** | #308, tanda 2 |
| Formato real de un archivo | un único punto de decisión, `core/formato_contenedor.py` (#307); tope de 2.000 entradas | `main` |
| Ficha de número | ya existe: `GET /ui/series/{series_id}/numero/{issue_id}` (`web/series.py`) | `main` |
| OPDS | catálogo 1.2 en `/opds`, Basic con `intentar_credenciales`, sin contenido (`api/opds.py`) | #160 |
| JS en `static/` | solo `vendor/htmx.min.js`. El libro de marca dice «nada de JavaScript propio»; el ADR 0001 admite Alpine.js para detalles de cliente | `main`, sistema de diseño |
| Kavita | corre en la misma Pi | CLAUDE.md §1 |
| Progreso de lectura | **ya existe**: `ReadingProgress`, 1:1 con `Issue` (`issue_id` único), con `status` (`ReadingStatus`), `current_page`, `started_at` y `completed_at`; `services/lectura.py` (BL-C3, #150) lo marca a mano y Biblioteca filtra por «Leídos / Leyendo / Sin leer». No guarda **qué archivo** se leía | `main` |
| Listas de lectura | existe la tabla `reading_lists` | `main` |
| Conversión CBR → CBZ | ya existe a demanda: `services/conversion.py` (BL-CNV1, #478) | `main` |

## 3. Referencias consultadas (código leído)

| Referencia | Commit | Licencia | Ficheros leídos |
|---|---|---|---|
| Komga | `gotson/komga` `db2ad64` (2026-11-11) | MIT | `interfaces/api/CommonBookController.kt`, `interfaces/api/rest/BookController.kt`, `interfaces/api/Utils.kt::setNotModified`, `infrastructure/mediacontainer/divina/RarExtractor.kt`, `interfaces/api/opds/v1/OpdsController.kt`, `domain/service/BookConverter.kt`, `build.gradle.kts` (junrar 8.1.2) |
| Kavita | `Kareadita/Kavita` `a9cdf1c` (2026-11-11) | GPL-3.0 | `Kavita.Services/CacheService.cs`, `Kavita.Services/Scanner/ScannerService.cs`, `Kavita.Models/Entities/Progress/AppUserProgress.cs`, `Kavita.Services.csproj` (SharpCompress 0.50.7) |
| Suwayomi-Server | `Suwayomi/Suwayomi-Server` `d521528` (2026-11-07) | MPL-2.0 | `source/local/loader/RarPageLoader.kt`, `manga/MangaAPI.kt`, migraciones (`last_page_read`) |

## 4. Cómo lo resuelve cada una

- **Komga.**
  - **Páginas:** `api/v1/books/{bookId}/pages/{pageNumber}` y una variante `/raw` que devuelve los bytes originales. La variante normal puede convertir la imagen a JPEG o PNG. Caché con `Last-Modified` del libro y `private` (`setNotModified`).
  - **RAR:** `RarExtractor` **abre el archivo en cada petición de página** (`Archive(path)` dentro de `getEntryStream`), así que un RAR sólido se descomprime desde el principio en cada página. Rechaza los RAR cifrados y multivolumen. Al escanear lee cada entrada entera para detectar su tipo y sus dimensiones.
  - **OPDS-PSE** en OPDS v1: rol `PAGE_STREAMING`, el número de páginas y la última leída. Si las páginas mezclan formatos, anuncia `?convert=jpeg`.
- **Kavita.**
  - Al abrir un capítulo, `CacheService.Ensure` **extrae el archivo entero a una carpeta de caché**, con un `SemaphoreSlim` por capítulo para que dos peticiones no lo extraigan a la vez.
  - Las páginas se sirven desde esa carpeta. Tras cada escaneo se limpia la caché **salvo los capítulos con una sesión de lectura activa** (`CleanupCacheExceptActiveChaptersAsync`).
  - Usa SharpCompress. El progreso es por usuario y capítulo (`PagesRead`). Su lector es una SPA en Angular.
- **Suwayomi.**
  - `RarPageLoader` **mantiene abierto un `Archive`** de junrar por capítulo y entrega las páginas por tuberías.
  - Filtra las imágenes por contenido y las ordena con orden natural sin mayúsculas.
  - El endpoint es `manga/{id}/chapter/{idx}/page/{index}`, y el progreso se guarda en `last_page_read` del capítulo.

## 5. Supuestos que NO valen en ZascArr

1. **Hay RAM y CPU de sobra** (Komga analiza todas las entradas al escanear y reabre el RAR en cada página). Aquí hay 512 MiB en una Pi compartida.
2. **Una SPA como lector** (Kavita, Komga): lo descarta el ADR 0001.
3. **Varios usuarios con su progreso**: ZascArr tiene una sola contraseña y no tiene usuarios.
4. **junrar o SharpCompress en el proceso**: aquí el RAR se lee con `unar` por subproceso (ADR 0015).
5. **La unidad es el libro o el capítulo**: aquí un número puede tener varios archivos (ediciones, copias) y un archivo puede cubrir varios números (ADR 0003).

## 6. Resultado por idea

| # | Idea | Resultado | Motivo |
|---|---|---|---|
| L1 | Servir la página N con sus **bytes originales**, sin recodificar | **Adoptar** (Komga `/raw`, Suwayomi) | Nada de Pillow por página: ahorra CPU en la Pi y no pierde nitidez. |
| L2 | Elegir la página **por su posición** en un listado ya validado, con orden natural y filtrando imágenes por contenido | **Adoptar** (Suwayomi) | Nunca un nombre que venga de la URL. El listado sale de `formato_contenedor` (#307). |
| L3 | Reabrir el archivo en cada página | **Adoptar solo para ZIP; descartar para RAR** (Komga) | En ZIP leer una entrada es directo. En un RAR sólido es descomprimir desde el principio en cada página. |
| L4 | Extraer el archivo entero a una caché al abrirlo, con bloqueo por archivo y limpieza que respeta las lecturas activas | **Adaptar** (Kavita) | Solo para RAR (los CBZ se leen directamente), usando el turno único de `lector_rar`, con **cuota en disco**, en un volumen del contenedor que no sea la tarjeta SD, y limpieza por antigüedad salvo lo que se está leyendo. Coste y tamaño: NOT RUN. |
| L5 | Mantener abierto el archivo y servir por tuberías | **Descartar** (Suwayomi) | Con `unar` por subproceso no hay un objeto vivo que reutilizar, y dejar procesos abiertos por lector va contra el presupuesto de la Pi. |
| L6 | Analizar todas las páginas al escanear (tipo y dimensiones) | **Descartar** (Komga) | Leer todos los bytes de 5.637 archivos en la Pi. El número de páginas sale del listado al abrir; la orientación (doble página), del navegador (`naturalWidth`). |
| L7 | Caché HTTP privada, validada | **Adoptar** (Komga) | `ETag` con el hash del archivo y el índice, `Cache-Control: private`. Igual que las portadas (`utils/cover.py`). |
| L8 | Progreso guardado en el servidor | **Construir sobre lo propio** | Ya existe `ReadingProgress` por número (BL-C3). El lector actualiza `current_page` y el estado (`READING` al abrir, `COMPLETED` en la última página) **a través de `services/lectura.py`**, sin un segundo camino. Hueco: no se sabe a qué archivo se refiere la página cuando el número tiene varios (D-L2). |
| L9 | Lector como SPA | **Descartar** (Kavita, Komga) | ADR 0001. **Adaptar:** un único script propio, pequeño, sin dependencias ni compilación, limitado a la pantalla de lectura. Necesita una ADR nueva (D-L1). |
| L10 | OPDS-PSE con el número de páginas y la última leída | **Adaptar** (Komga) | Sobre el `/opds` existente y su Basic. Sin conversión: si las páginas no son JPEG, PNG o GIF, ese número no anuncia PSE en lugar de recodificar. |
| L11 | Rechazar RAR cifrados y multivolumen con motivo | **Adoptar** (Komga) | Con texto llano en la interfaz. |
| L12 | Al acabar, el siguiente número **de tu serie** (por `sort_order`) o lo que te falta (a Deseados); más adelante, el siguiente de una lista de lectura (`reading_lists`) o saga | **Mejorar** | Lo que un lector suelto no sabe: la numeración y las ediciones de ZascArr. No se ha comprobado qué ofrecen Komga o Kavita al acabar (NOT RUN). |
| L13 | Renderizar PDF | **Descartar por ahora** | 2 PDF en el disco. |
| L14 | Sentido de lectura según la tradición | **Adaptar** | Valor por defecto por tradición (manga de derecha a izquierda), `<Manga>YesAndRightToLeft` del ComicInfo si lo trae, y siempre se puede cambiar por serie. La tradición no dice el formato: un manhwa impreso no es un webtoon. |

## 7. Invariantes de ZascArr

1. **Solo lectura:** el lector nunca escribe en un archivo de la biblioteca (D3 de BL-CNV: archivos compartidos).
2. **La página se elige por índice** de un listado validado; los topes de `formato_contenedor` y un tope por entrada antes de leerla (el tagger tuvo una bomba de descompresión sin tope, #387).
3. **Misma autenticación que `/ui`** (y Basic en `/opds`); caché `private`; sin rutas ni nombres de archivo en las URL.
4. **RAR de uno en uno** (turno de `lector_rar`) y caché en disco con cuota; nada bloqueante en el bucle de eventos.
5. **Sin red y sin CDN:** el script se sirve desde `static/`, como htmx.
6. **El color y el texto siguen el sistema de diseño;** el lector es la única pantalla oscura a propósito, y lo declara.

## 8. Casos de prueba antes de implementar

- Un CBZ con páginas `1.jpg`, `2.jpg`, `10.jpg` → orden natural; un `ComicInfo.xml` y un `Thumbs.db` no son páginas.
- Índice fuera de rango, negativo o no numérico → 404, sin trazas.
- Entrada que declara 10 MB y descomprime 2 GB → se corta en el tope.
- Archivo que cambia entre dos peticiones (hash distinto) → `ETag` nuevo y listado rehecho.
- RAR sólido → una sola extracción aunque lleguen tres peticiones de páginas a la vez.
- Caché llena → se limpia la más antigua que no esté en lectura; si no cabe, se dice.
- RAR cifrado o multivolumen → mensaje llano, sin lector.
- Sin sesión → al login (y 401 en `/opds`).
- El caso que las referencias no cubren: número con dos archivos → el lector abre el que la persona elige y el progreso cuadra con D-L2.
- Marcar «Leído» a mano (BL-C3) y llegar a la última página en el lector dejan el mismo estado; abrir un número ya leído no lo devuelve a «Leyendo» (decisión de la especificación).

## 9. Matriz (pesos por defecto, sin mover) — cómo servir las páginas de un RAR

| Criterio (peso) | A. Reabrir por página (Komga) | B. Caché de extracción (Kavita, adaptada) | C. Archivo abierto (Suwayomi) | D. Convertir antes a CBZ (BL-CNV) |
|---|---|---|---|---|
| Encaje con el flujo del Coleccionista (25) | 2 (segundos por página en sólidos) | 4 (espera la primera vez) | 4 | 3 (no vale para archivos compartidos, D3) |
| Coste en Pi (20) | 1 | 3 (disco con cuota) | 2 (procesos vivos) | 5 al leer |
| Seguridad, legalidad y licencia (20) | 4 | 4 (topes de extracción) | 3 | 4 |
| Cobertura del requisito core (15) | 3 | 5 | 4 | 2 |
| Adaptabilidad al stack (10) | 4 | 4 | 1 (`unar` no lo permite) | 3 |
| Mantenimiento (5) | 4 | 4 | 3 | 4 |
| Lock-in y salida (5) | 5 | 5 | 4 | 4 |
| **Total (sobre 5)** | **2,55** | **3,95** | **3,05** | **3,40** |

Para CBZ no hay matriz: L3 (leer la entrada directamente) gana sin discusión.

## 10. IGUALAR / MEJORAR

**IGUALAR:**
- Leer página a página con precarga.
- Recordar la página y sincronizar el progreso entre dispositivos.
- Doble página y sentido de lectura.
- Rechazar cifrados y multivolumen.
- OPDS-PSE.

**MEJORAR (con evidencia):**
- No reabrir un RAR sólido en cada página (Komga lo hace: §4).
- No analizar la biblioteca entera al escanear (Komga: §4).
- Al acabar un número, ofrecer el siguiente según la numeración propia de ZascArr, o lo que falta (L12).

## 11. Decisiones del PO (2026-11-14)

| # | Decisión | Resultado |
|---|---|---|
| D-L1 | JavaScript propio | **Sí, solo en la pantalla de lectura:** un fichero sin dependencias ni compilación, servido desde `static/`. Excepción declarada a «nada de JavaScript propio»; se formaliza en una ADR nueva dentro de BL-LEC0. |
| D-L2 | Qué archivo se leía | **Sí:** columna opcional `file_id` en `reading_progress` (migración aditiva). Si ese archivo cambia o desaparece, se retoma desde la página guardada en el que se abra, avisando. |
| D-L3 | Caché de RAR | **Propuesta aceptada:** volumen del contenedor en el disco de datos, nunca en la tarjeta SD; cuota fija de ~1 GiB que BL-LEC0 ajusta con la medición; se limpia lo más antiguo salvo lo que se está leyendo. |
| D-L4 | Cómo se abre el lector | **Botón «Leer» / «Continuar (pág. N)» en la ficha del número**; el doble clic, solo como atajo en el PC. |

## 12. NOT RUN

- Latencia y memoria de servir una página de CBZ en la Pi.
- Tiempo y espacio de extraer un RAR sólido grande completo con `unar` en la Pi, y el tamaño de caché que haría falta.
- Comportamiento de Panels, Chunky, Mihon y YACReader con el OPDS-PSE de ZascArr.
- Qué ofrecen Komga y Kavita al terminar un libro (siguiente libro, listas de lectura).
- Cifras de la propuesta externa (< 100 ms la primera página, < 15 MB de RAM, ~1 s en extraer un sólido): sin medir.

## 13. Notas sobre la propuesta externa

- **PyMuPDF:** la propuesta dice que su AGPL obligaría a relicenciar ZascArr. La GPLv3 (§13) permite combinarla con AGPLv3; lo que se arrastra es la obligación de ofrecer el código por red en esa parte. Evitarla sigue siendo prudente, y además los PDF están fuera (L13).
- **«Convertir CBR a CBZ al importar»** contradice D3 y D4 de BL-CNV (#476) y supone una «copia organizada» que ZascArr no tiene (vincula en su sitio, ADR 0007).
- **No se cita en el proyecto ningún sitio de descargas** como origen de archivos (CLAUDE.md §5.1).

## 14. Caducidad

~60 días (2027-01-13), o antes si cambian el ADR 0001, el ADR 0015 o BL-C5.

**Barrera legal:** esta ficha toma ideas, no código. Komga es MIT, Kavita GPL-3.0 y Suwayomi
MPL-2.0; antes de reutilizar una implementación, revisar el fichero y sus avisos.
