# Benchmark B23 — Alta de serie y descarga guiada (nivel 2)

> **Historia:** B23. Como coleccionista, quiero añadir una serie nueva, ver varias
> opciones de descarga, elegir una, y que ZascArr la descargue, recoja el archivo,
> lo convierta a CBZ si hace falta, lo renombre según mis ajustes, lo mueva a la
> carpeta de la serie y lo borre de descargas.
> **Fecha:** 2026-11-16. **SHA de ZascArr contrastado:** `77f6488` (main desplegado).
> **Caduca:** ~2027-01-15 (o antes si cambia una referencia o la historia).

## 1. Problema local y comportamiento actual

Hoy el flujo está partido:

1. **Descubrir** busca en fuentes de metadatos, permite elegir una candidata y crea
   la serie **vacía** (`AltaDeSerie`, `_alta_resultado.html`).
2. **Deseados** permite añadir una serie o un número, y `D10` ya ofrece búsqueda
   manual: `preview_candidates()` devuelve varios candidatos con fuente/tamaño/formato
   y `send_manual_candidate()` envía solo el elegido a Transmission/aMule.
3. **Importador** recoge el archivo, lo mueve, lo renombra con los presets de B9 y
   borra el origen de descargas mediante `safe_move` (copia/verifica/mueve).
4. **Conversión CBR→CBZ** existe, pero es manual desde la ficha (`ConversionService`,
   reversible, guarda el original en `.zascarr/originales`).

El fallo de producto está en el paso 1→2→3: una serie nueva no tiene filas `Issue`.
El matcher puede reconocer la serie por el nombre del archivo, pero no tiene número
al que enlazarlo; el archivo acaba con `issue_id=NULL` (y a veces en `_Unsorted`),
así que no se ve como número de la serie. Además, la conversión no se dispara al
importar. No hace falta inventar el ciclo de descarga: existe y está probado. Falta
**el contrato de alta + catálogo + conversión automática**.

## 2. Referencias consultadas (código leído, no ejecutado)

| Referencia | Versión / commit | Qué se miró |
|---|---|---|
| Sonarr | `Sonarr/Sonarr` `c018578` (2026-11-02) | `Tv/AddSeriesService.cs`, `SeriesAddedHandler.cs`, `RefreshSeriesService.cs`, `MediaFiles/DownloadedEpisodesImportService.cs`, `MediaFiles/RecycleBinProvider.cs` |
| Radarr | `Radarr/Radarr` `19edd43` (2026-11-15) | `Movies/AddMovieService.cs`, importación/renombrado |
| Kapowarr | `Casvt/Kapowarr` `c191dda` (2026-09-14) | `backend/implementations/volumes.py`, `features/post_processing.py`, `implementations/conversion.py`, `features/download_queue.py` |
| Mylar3 | `mylar3/mylar3` `cdc94a4` (2025-08-17) | `mylar/importer.py`, `mylar/PostProcessor.py`, `mylar/cmtagmylar.py`, `mylar/search.py` |
| Komga | `gotson/Komga` `db2ad64` (2026-11-11) | `domain/service/BookImporter.kt`, `domain/service/BookConverter.kt` |
| Suwayomi | `Suwayomi/Suwayomi-Server` `d521528` (2026-11-07) | `manga/impl/Manga.kt`, `Chapter.kt`, `download/DownloadManager.kt`, `fileProvider/impl/ArchiveProvider.kt` |
| Kaizoku | `oae/kaizoku` `fc86b7d` (archivado, 2025-02-03) | `src/server/queue/download.ts`, `checkChapters.ts`, `integration.ts` |

## 3. Cómo lo resuelve cada una

- **Sonarr:** al añadir, pide a Skyhook la serie **y sus episodios**; la escritura
  inicial no bloquea la UI y `SeriesAddedHandler` encola un `RefreshSeriesCommand`
  que crea/actualiza episodios. Después: monitorización por temporada, búsqueda
  automática o interactiva, descarga, importación move/copy (`CanMoveFiles`),
  renombrado por plantilla y papelera de reciclaje configurable. No hay conversión
  de formato.
- **Radarr:** igual sin episodios; metadatos de película, búsqueda interactiva,
  importación, renombrado y borrado/papelera.
- **Kapowarr:** `Volume.add()` **descarga de ComicVine el volumen completo y sus
  issues** e inserta todas las filas de una vez; `auto_search` es opcional. El
  postproceso mueve el archivo a la carpeta del volumen, lo renombra y, si está
  activado `convert`, lo convierte. **Borra/renombra el destino existente** sin
  preguntar (no adoptable). Los torrents pueden copiarse para seguir sembrando.
- **Mylar3:** `addComictoDB()` pide el cómic a ComicVine y crea/actualiza los
  issues con estado Wanted; búsqueda automática o manual; postproceso con
  renombrado y `CBR2CBZ_ONLY` mediante ComicTagger (opt-in), dependencia pesada.
- **Komga (import/convert):** su «Import Books» elige carpeta/serie destino,
  renombra el archivo y permite **move/copy/hardlink**; `move` borra el origen.
  `BookConverter` convierte RAR4/RAR5→CBZ sin recomprimir, **verifica que estén
  todas las páginas y ficheros**, conserva id/media/hashes y **solo entonces
  borra el RAR original**. Es la referencia más cercana a la conversión y borrado
  que pide el PO.
- **Suwayomi:** la fila del manga nace al buscar; añadir solo la mete en la
  biblioteca. El catálogo de capítulos es **lazy**: se pide a la fuente al abrir
  la lista; reconcilia por URL con guarda anti-borrado masivo; descarga páginas y
  las archiva (carpeta o CBZ). No tiene torrent/eD2K, renombrado por preset ni
  conversión de archivo completo.
- **Kaizoku (archivado):** alta = mangal exacto + descargar **toda** la serie;
  nombres con `[0001]`; sin tests; usa Redis/BullMQ y no cabe en el presupuesto
  de la Pi. Solo aporta patrones, no arquitectura.

## 4. Supuestos de las referencias que NO valen en ZascArr

1. **Unidad:** episodio/película (Sonarr/Radarr) o capítulo de manga
   (Suwayomi/Kaizoku). ZascArr necesita grapa/tomo/edición (`Issue.format`,
   `sort_order`, alias locales B13, colisiones B15).
2. **Fuente de catálogo:** TVDB/TMDB/ComicVine son fuentes centrales y completas;
   ZascArr usa fuentes españolas irregulares (Tebeosfera, GCD, Fandom, foros) y
   una serie nueva puede no tener catálogo fiable.
3. **Escritura destructiva:** Kapowarr borra el destino existente; Komga borra el
   origen tras verificar. ZascArr tiene el invariante A3 de no sobrescribir y
   `safe_move` copia/verifica antes de borrar. La conversión de Komga **sí** es
   precedente para borrar el RAR original, pero ZascArr ya tiene cuarentena
   reversible y debe conservarla por defecto.
4. **Pi y RAM:** Sonarr/Radarr/Kapowarr/Mylar3 son procesos .NET/Python completos;
   Suwayomi/Kaizoku usan JVM/Redis. ZascArr tiene 512 MB y un solo proceso.
5. **Idioma y edición:** ninguno de ellos tiene presets de nombres en español,
   alias locales ni CBR de escaneos españoles.

## 5. Ideas y resultado (vocabulario del procedimiento)

| Idea | De | Resultado | Motivo / qué cambia |
|---|---|---|---|
| Al añadir, crear el catálogo de números de la fuente | Sonarr, Kapowarr, Mylar3 | **Adoptar** | Evita que la serie nazca vacía; es la base para buscar y enlazar. |
| Refresco de catálogo **asíncrono**, sin bloquear el alta | Sonarr | **Adaptar** | La Pi y las fuentes lentas no deben congelar la UI; estado «catálogo pendiente» visible. |
| Catálogo **lazy** si la fuente no lo da al añadir | Suwayomi | **Adaptar** | Solo cuando la fuente tenga contrato estable; no crear filas al navegar. |
| Fallback: crear el `Issue` al importar si la serie no tiene catálogo | ZascArr | **Mejorar** | Cubre fuentes españolas sin listado; seguro solo si la serie está vacía y el número se parsea con confianza. |
| Búsqueda interactiva con varios candidatos y elección explícita | Sonarr, Kapowarr, Mylar3 | **Adoptar** | ZascArr ya la tiene (D10) con token firmado; conservarla, no auto-elegir en el alta manual. |
| Enviar a Transmission/aMule el candidato elegido | Sonarr, Kapowarr | **Adoptar** | Ya existe; mantener el opt-in por backend. |
| Importar move/copy y renombrar al destino | Sonarr, Komga | **Adoptar** | `safe_move` y presets B9 ya lo hacen; no sobrescribir. |
| Convertir CBR→CBZ tras verificar y borrar el RAR original | Komga | **Adaptar** | Komga verifica páginas y solo entonces borra; ZascArr debe hacer lo mismo, pero conservando la cuarentena reversible por defecto y ofreciendo «liberar originales». |
| `CBR2CBZ` opt-in con conversor externo (ComicTagger) | Mylar3 | **Descartar** | Dependencia pesada y ya hay conversión propia verificada (`conversion_cbr.py`). |
| Borrar/renombrar el destino existente sin preguntar | Kapowarr | **Descartar** | Viola A3; ZascArr usa nombre único y confirma. |
| Cola con estados/reintentos y borrado del origen | Sonarr, Suwayomi | **Construir sobre lo propio** | `WishlistStatus`, `download_ref`, importador y `ImportRun` ya cubren el ciclo; solo falta el eslabón alta→catálogo→conversión. |
| Alta = descargar toda la serie | Kaizoku | **Descartar** | Coste en Pi, red y legal; ZascArr usa deseados/faltantes. |
| Deducción de número desde el nombre del archivo como clave | Kaizoku | **Descartar** | Frágil; ZascArr usa `Issue` y matcher con formato/alias. |
| `ComicInfo.xml` mínimo al empaquetar | Suwayomi | **Adaptar** | ZascArr ya lo escribe; no copiar su omisión de `Volume`. |
| Escaneo Komga/Kavita tras cada importación | Kaizoku | **Descartar** | ZascArr lee su propia biblioteca; no hay lector externo en el ciclo. |

## 6. Matriz nivel 2

Pesos por defecto (suman 100): encaje con el Coleccionista 25 · coste en Pi 20 ·
seguridad/legalidad/licencia 20 · cobertura del requisito core 15 · adaptabilidad
al stack/modelo 10 · mantenimiento de la referencia 5 · lock-in 5.

Puntuación 1–5 (5 = mejor para ZascArr), ponderada a 100:

| Referencia | Flujo | Pi | Legal | Core | Stack | Maint. | Lock-in | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Kapowarr** | 5 | 4 | 4 | 5 | 4 | 3 | 4 | **87,0** |
| **Komga (import/convert)** | 3 | 5 | 5 | 4 | 3 | 4 | 5 | **82,0** |
| **Sonarr** | 5 | 4 | 3 | 3 | 2 | 4 | 4 | **74,0** |
| **Mylar3** | 4 | 3 | 3 | 4 | 2 | 2 | 3 | **65,0** |
| **Suwayomi** | 3 | 4 | 4 | 2 | 2 | 4 | 4 | **65,0** |
| **Kaizoku (archivado)** | 3 | 4 | 3 | 2 | 1 | 1 | 3 | **55,0** |

## 7. IGUALAR / MEJORAR

**IGUALAR (mínimo competitivo):**

- Al añadir una serie se crea su catálogo de números, aunque sea en segundo plano.
- Búsqueda interactiva con varios candidatos, fuente/tamaño/formato y elección.
- Importación con renombrado, movimiento y limpieza del origen.
- Conversión CBR→CBZ verificada, no a ciegas.
- Estado visible de cada paso; nunca «éxito» si el archivo no quedó enlazado.

**MEJORAR (con evidencia):**

- **Híbrido catálogo + creación al importar:** Kapowarr/Mylar3 dependen de un
  catálogo completo; las fuentes españolas no siempre lo dan. ZascArr puede crear
  el número al importar cuando la serie está vacía y el nombre lo identifica,
  sin inventar en series ya catalogadas.
- **Conversión reversible por defecto:** Komga borra el RAR tras verificar; el
  invariante de ZascArr conserva el original en cuarentena y permite liberarlo.
  Si el PO pide borrado inmediato, hacerlo opt-in explícito, nunca por defecto.
- **No sobrescribir:** Kapowarr sustituye el destino; ZascArr usa `_unique_path`.
- **Presupuesto de Pi:** catálogo en segundo plano y conversión acotada a 150 MiB.

## 8. Casos de prueba antes de implementar

1. Serie nueva sin `Issue`: importar un `Serie 001.cbz` crea el número 001 y el
   `File` queda enlazado; no acaba en `_Unsorted`.
2. Serie nueva con catálogo ya creado: el importador enlaza el número existente,
   no crea otro.
3. Varios candidatos: la UI muestra todos; solo el elegido se envía.
4. CBR que es ZIP: se convierte/renombra a CBZ sin recomprimir.
5. CBR RAR ≤150 MiB: se convierte, se verifica el manifiesto y el CBZ queda en la
   carpeta de la serie; el origen de descargas ya no existe.
6. CBR >150 MiB, cifrado, multivolumen o con otro tebeo dentro: no se convierte,
   se importa como CBR y se informa del motivo; no se pierde nada.
7. Fallo de conversión: el CBR importado sigue disponible y el original de
   descargas no se pierde.
8. Archivo ambiguo o sin número: va a Pendientes, no se inventa un número.
9. Reejecución idempotente: no duplica `Issue`, `File` ni descargas.
10. Nombre con preset B9: el destino usa el preset y el padding configurados.

## 9. Simulación end-to-end

Se ejecutará con varios roles (alta, búsqueda, descarga, importación,
verificación) sobre una base Postgres de pruebas y clientes simulados; el guion y
el resultado se anexan a esta ficha. **No se descarga contenido real**: se usa un
CBZ/CBR de fixture y un Transmission/Prowlarr simulados.

## 10. NOT RUN

- No se ejecutaron Sonarr, Radarr, Kapowarr, Mylar3, Komga, Suwayomi ni Kaizoku;
  todo es lectura de código/documentación.
- No se midió RAM/CPU de ninguna referencia.
- No se validó el catálogo real de una fuente española ni la conversión con un
  CBR real en la Pi.
- No se comprobó la licencia de cada fichero reutilizable (solo se adoptan ideas,
  no código).

---

## Anexo — Simulación end-to-end (2026-11-16)

**Entorno:** Postgres 16 efímero (`bd_efimera`), biblioteca y Descargas temporales,
Prowlarr y Transmission simulados; ningún contenido real ni red externa. El guion
vive en `tests/test_b23_flujo_pg.py`.

**Roles ejecutados (agentes independientes):**

1. **Alta/búsqueda:** crea una serie vacía, un deseo, obtiene dos candidatos y elige
   el segundo. Comprueba que **solo el elegido** llega al cliente.
2. **Descarga/importación:** simula la llegada del archivo a Descargas; comprueba
   que el origen desaparece, el CBZ queda en la biblioteca, se crea el número y el
   `File` queda enlazado.
3. **QA de bordes:** catálogo ya existente, archivo sin número, conversión fallida,
   opt-in apagado, carrera de `Issue` y nombre canónico.

**Resultado:** PASS en los siete escenarios del test (altas, catálogo existente,
dos candidatos, CBR-ZIP, especial/pack, opt-in apagado y nombre sin número); los
detalles y la salida de cada rol quedan en la PR. **NOT RUN:** Prowlarr/Transmission reales, SMB, CBR RAR
real con `unar`, navegador y Pi física.

**Conclusión de diseño:** el eslabón que faltaba no era el ciclo de descarga, sino
el contrato alta→catálogo→número. La simulación confirma que, con la opción
«crear el número al importar si la serie no tiene catálogo», una serie nueva puede
completar el flujo sin inventar números en series ya catalogadas. La conversión
CBR→CBZ sigue siendo opt-in y conserva el CBR si falla.
