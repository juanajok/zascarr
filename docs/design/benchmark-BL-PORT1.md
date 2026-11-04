# Ficha de benchmarking — BL-PORT1 (#300): portadas nítidas con lo que ya tengo

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Nivel 2:
> no hay modelo nuevo, pero se toca **caché en disco**, el contrato de la
> portada y el comportamiento ante fuente ausente; es difícil de revertir sin
> migrar ficheros. **Propone SCOUT.bench; decide el PO.** Esta ficha es insumo de
> la especificación, no autorización para implementar.
>
> - **Fecha:** 2026-11-04
> - **SHA contrastado:** `35283b5` (`main` y rama `docs/181-censo-identidad`; los
>   ficheros citados de `src/` tienen **diff vacío** contra `main`).
> - **Alcance:** cómo se elige el tamaño por uso, cómo se versiona y regenera la
>   caché local y si `srcset` se justifica. **No** decide descargar portadas de
>   fuera (BL-PORT2), leer CBR ni mejorar por IA.
> - **Método:** contrato y código, no pantalla. No se han ejecutado Komga,
>   Kavita ni Kapowarr; lo no ejecutado va en NOT RUN.
> - **ADR:** no procede. No cambia arquitectura ni modelo: es un contrato de
>   caché local (ruta versionada + ancho objetivo) que cabe en la
>   especificación; si el PO cambiara a variantes por uso, sería decisión de
>   spec, no ADR.

---

## 0. Veredicto en una línea

**CONSTRUIR SOBRE LO PROPIO.** La cascada de 3 niveles y la respuesta con
`ETag`/`Cache-Control` ya existen (`web/series.py:205-263`,
`utils/cover.py:127-140`). Se adapta el patrón de Komga/Kavita —**una portada
generada a un tamaño generoso y explícito, regenerada de forma controlada**— a
la unidad de ZascArr, con **dos tamaños por uso** (240 y 600 px), **clave de caché
versionada** y **regeneración perezosa**; **`srcset` no se justifica** (motivos en
§5.4). No se copia código: solo se copian patrones.

---

## 1. Problema fijado en el código vigente

**Historia.** BL-PORT1 (#300, P1/S): que las portadas de Biblioteca y ficha se
vean nítidas cuando el tebeo tiene buena calidad, sin salir a internet.

**Caso real.** Un CBZ de 1600×2400 px (página de tebeo habitual) se extrae con
`extract_cover_thumbnail`, que lo reduce a **240 px de ancho**
(`utils/cover.py:40,117`). Esa misma imagen se sirve en:

- la rejilla de Biblioteca (`.library-grid`, tarjetas de 160 px mínimos,
  `static/web.css:879-883`),
- la estantería del Inicio (`.series-grid`, 150 px mínimos,
  `static/web.css:985-989`),
- la portada de la ficha (`.portada.series-cover`, 140 px,
  `static/web.css:847-851`),

porque las tres usan la misma ruta `/ui/series/{id}/portada`
(`_rejilla_biblioteca.html:11`, `dashboard.html:150`, `series_detail.html:8`) y
la macro `ui.portada` pinta un único `<img src>` (`_componentes.html:29-31`).

**Comportamiento actual, verificado en el código:**

| Hecho | Evidencia |
|---|---|
| La extracción de un CBZ se limita a **240 px** de ancho | `utils/cover.py:40` (`_THUMB_MAX_WIDTH = 240`), `:117` (`img.thumbnail((240, 480))`) |
| La descarga externa se limita a **320 px** | `utils/cover.py:61` (`_COVER_MAX_WIDTH = 320`), `:179` |
| La portada de una serie extraída de CBZ usa **240**, no 320 | `web/series.py:246` llama a `extract_cover_thumbnail` sin ancho; el 320 solo lo usan las externas (`fetch_and_cache_cover`) |
| «Por revisar» usa el mismo extractor de 240, pero **sin caché en disco** y con `ETag` del fichero origen | `web/pendientes.py:394-402`; `web.css:697-701` (ancho presentado 120 px) |
| La caché `covers/<id>.jpg` se escribe una vez y **nunca se regenera**: si existe, se sirve | `web/series.py:227-231` |
| La caché no incluye la versión del generador ni el ancho: dos portadas de distinta calidad comparten ruta | `web/series.py:227` |
| `ETag` = `mtime` del fichero de caché; `Cache-Control: private, max-age=86400`; 304 con `If-None-Match` | `web/series.py:266-267`; `utils/cover.py:127-140` |
| «Descubrir» tiene su propia caché y su propio tamaño (320 para tarjetas de 80 px) | `web/discovery.py:139-158`; `web.css:1133` |
| CBR real no tiene extractor: `EXTENSIONES_CON_PORTADA = {".cbz", ".zip"}` (un `.cbr` cuyo contenido es ZIP sí se lee, #307; el RAR real no) | `utils/cover.py:42-46` |

**Resultado deseado.** Que una portada extraída de un CBZ (o descargada de una
fuente) se vea nítida a la densidad de referencia en rejilla y ficha, sin
ampliar originales pequeños, sin que el coleccionista borre nada y sin coste
perceptible al abrir Biblioteca.

**Medición de presentación (CSS de este repo, no estimación de diseño).**
`--gutter: clamp(14px, 2.2vw, 24px)` (`web.css:98`) y `.content` con
`max-width: 1240px` (`web.css:449`). Con `auto-fill`/`minmax`, el ancho real de
tarjeta varía con la ventana:

| Uso | Ancho presentado (CSS) | 2× (px de dispositivo) | Fichero que se sirve hoy |
|---|---|---|---|
| «Por revisar» | 120 (`web.css:697-701`) | 240 | extracción 240 |
| Rejilla Biblioteca | 160–200 típico; **296–333** cuando la ventana mide ≤ 357 px y queda **una sola columna** | 320–400; 592–666 en el borde | 240 (CBZ) / 320 (externa) |
| Estantería Inicio | 110–171,5 (`web.css:985-989,1109`) | 220–343 | 240 / 320 |
| Ficha | 140 escritorio / 120 móvil (`web.css:847-851,1113`) | 280 / 240 (3× = 420 / 360) | 240 / 320 |
| Descubrir / asistente | 80 (`web.css:1133`) | 160 | 320 (caché `covers/descubrir`) |

**Datos reales de la biblioteca.** No se ha medido la biblioteca real del
coleccionista ni la Pi en este encargo: **NOT RUN**. La única medición es un
banco sintético local (§10) para orden de magnitud, no para fijar PASS/FAIL.

---

## 2. Longlist → shortlist (eliminados con motivo)

Se parte de lo que el propio proyecto declara como dominio de cada referencia
(CLAUDE.md §13) y se filtra por una pregunta: **¿resuelve el núcleo de esta
historia, que es regenerar una portada local a distinta resolución sin perder
caché ni ETag?**

| Candidato | ¿Qué es para este problema? | Decisión |
|---|---|---|
| **Komga** (MIT, 1.29.2) | Servidor de biblioteca con miniaturas generadas a un tamaño de ajuste y tarea explícita de regeneración | **Shortlist** (contrato más probado) |
| **Kavita** (GPL-3.0, 0.9.1.18) | Servidor de lectura con `CoverImageSize` (320×455 por defecto, hasta 1265×1795) y portadas servidas como fichero | **Shortlist** (contrato de tamaños y regeneración por refresh) |
| **Kapowarr** (GPL-3.0, v1.3.2) | Gestor de cómic que guarda la portada de Comic Vine en SQLite y la sirve sin reescalar | **Shortlist** (contraejemplo: qué pasa sin versionado) |
| **Patrón web** (`srcset`/`sizes`, validadores HTTP) | Mecanismo estándar para servir variantes y revalidar | **Shortlist** (se evalúa si se adopta o se descarta) |
| Construir sobre lo propio | La cascada C1, `cached_image_response`, `ETag`, `covers/<id>.jpg` ya existen | **Shortlist** (parte con ventaja) |
| Sonarr / Radarr | Su portada es arte de proveedor remoto; no extraen la primera página de un CBZ local | **Eliminado**: no responden a la pregunta de regeneración local. No se han auditado; no se afirma que no tengan caché de pósters |
| Mylar3 | Misma familia de cómic que Kapowarr; no se espera un contrato distinto y el presupuesto no da para seis apps | **Eliminado por proporcionalidad**, no por defecto demostrado |
| Suwayomi | Su unidad son capítulos/fuentes y lectura (CLAUDE.md §13); no la portada de una biblioteca de CBZ | **Eliminado por unidad de dominio** |
| Kaizoku (`oae/kaizoku`) | Archivado; patrón histórico de descarga/aviso a lectores, no de caché de portada local | **Eliminado**: referencia no viva (CLAUDE.md §13) |
| «Comprar» (SaaS/CDN de imágenes) | Movería portadas y datos de una biblioteca privada fuera de casa | **Eliminado por invariantes** (sin red, datos privados, sin dependencia nueva). No se comparan precios: queda fuera de las restricciones antes de evaluarse |
| Komga/Kavita **como código** | Kotlin/Spring y C#/.NET; no hay un componente reutilizable que encaje en FastAPI sin arrastrar su modelo | **Eliminado**: se copia el contrato, no la implementación (además, GPL-3.0 en Kavita y Kapowarr; Komga MIT; ver «Barrera legal») |

No se ha encontrado un producto comercial que haga «extraer la portada de un CBZ
y cachearla a dos tamaños» como componente; **no se infiere que no exista**, solo
que no es una opción compatible con las restricciones de esta historia.

---

## 3. Cómo lo resuelve cada referencia (contrato, no pantalla)

**Repos y commits contrastados (lectura de código, no ejecución):**

- **Komga** v1.29.2, commit `25c67d14eb748dd3fb9f6612c099959a077fc850`
  (2026-10-30, rama `master` local): <https://github.com/gotson/komga/tree/25c67d14eb748dd3fb9f6612c099959a077fc850>
- **Kavita** 0.9.1.18, commit `9e177701c359090fa62e2e90aba571567c6cc680`
  (2026-11-01, `develop`): <https://github.com/Kareadita/Kavita/tree/9e177701c359090fa62e2e90aba571567c6cc680>
- **Kapowarr** v1.3.2, commit `c191dda6617929c81292483a8cc07f631111dae2`
  (2026-09-14): <https://github.com/Casvt/Kapowarr/tree/c191dda6617929c81292483a8cc07f631111dae2>
- **MDN** (documentación viva, consultada 2026-11-04): enlaces en §3.4.

### 3.1 Komga 1.29.2 (`25c67d1`, 2026-10-30)

- **Tamaño:** enum `ThumbnailSize` con `DEFAULT(300)`, `MEDIUM(600)`,
  `LARGE(900)`, `XLARGE(1200)` **de lado mayor**
  ([`ThumbnailSize.kt`](https://github.com/gotson/komga/blob/25c67d14eb748dd3fb9f6612c099959a077fc850/komga/src/main/kotlin/org/gotson/komga/domain/model/ThumbnailSize.kt)).
  Es un ajuste **global** de servidor (`KomgaSettingsProvider.kt:51-58`), no por
  uso.
- **Generación:** al analizar el libro, `BookAnalyzer.kt:254` redimensiona la
  portada al `maxEdge` del ajuste con `resizeImageToByteArray`; el resultado se
  guarda como miniatura generada.
- **Servido:** `GET /api/v1/books/{id}/thumbnail` devuelve los bytes guardados,
  **sin parámetro de tamaño** (`BookController.kt:330-341`). El único servido con
  reescalado que se ha encontrado es el de OPDS pequeño (`OpdsController.kt:702-709`), y para una
  miniatura generada pasa `resizeTo = null`.
- **Regeneración:** **no es perezosa**. Se pide una tarea explícita
  (`BookController.kt:772-775`) que selecciona solo miniaturas generadas cuya
  dimensión es menor que el ajuste actual (`BookLifecycle.kt:301-307`) y encola
  `GenerateBookThumbnail` (`TaskHandler.kt:182`). La UI muestra un diálogo al
  cambiar el tamaño, con «sí, solo si son mayores» o «sí, todos los libros»
  (`ServerSettings.vue:191-192,317-350`; textos en `locales/en.json:986-993`).
- **Clave/versión:** la identidad de la miniatura incluye `dimension` y `type`;
  el ajuste nuevo invalida por comparación de dimensión, no por un hash de
  versión (`ThumbnailBook.kt`). La URL pública sigue siendo fija.
- **`srcset`:** no se ha encontrado ninguno en `komga-webui/src` ni en
  `next-ui/src` (`git grep` sobre HEAD en esas dos rutas); la URL de la portada no
  lleva tamaño (`komga-webui/src/functions/urls.ts:17-22,52-57`).
- **Fallo/ambiguo:** si falta la miniatura, el endpoint responde 404; no la genera
  al vuelo. La regeneración es una operación de lote con progreso en la cola de
  tareas.
- **Licencia:** MIT (`LICENSE`), sin obligación de copyleft si se copiara código
  (no es el plan).

### 3.2 Kavita 0.9.1.18 (`9e177701c359090fa62e2e90aba571567c6cc680`, 2026-11-01)

- **Tamaño:** `CoverImageSize`: `Default 320×455`, `Medium 640×909`,
  `Large 900×1277`, `XLarge 1265×1795`
  ([`CoverImageSize.cs`](https://github.com/Kareadita/Kavita/blob/9e177701c359090fa62e2e90aba571567c6cc680/Kavita.Models/Entities/Enums/CoverImageSize.cs)).
  Es un ajuste de servidor, global; la UI lo llama «Cover Image Size» (reportado
  en [#3260](https://github.com/Kareadita/Kavita/issues/3260)).
- **Generación:** `ImageService.WriteCoverThumbnail(..., CoverImageSize size =
  CoverImageSize.Default)` recorta/redimensiona a las dimensiones del ajuste
  (`Kavita.Services/ImageService.cs:168,210`; constantes 320×455 en `:35,39`).
- **Servido:** los endpoints de portada de series/volumen/capítulo hacen
  `PhysicalFile(path)` sobre el fichero ya generado, **sin reescalado por
  petición** (`Kavita.Server/Controllers/ImageController.cs:41-88`). Solo
  colecciones y listas de lectura generan la portada **si falta** al pedirla
  (`ImageController.cs:96-131`).
- **Regeneración:** en el refresh de metadatos (lote); el informe
  [#4913](https://github.com/Kareadita/Kavita/issues/4913) documenta que
  `refresh-metadata?force=true` regenera las no bloqueadas y respeta
  `CoverImageLocked`. No es perezosa para series.
- **Clave/versión:** el nombre es estable por entidad (`series<id>.<ext>`) y la
  `CoverImageSize` **solo se aplica al generar**; `ConvertToEncodingFormat` no
  redimensiona (`ImageService.cs:228-239`). Esto es justo lo que permite que una
  portada antigua o descargada a resolución completa quede fuera del contrato
  (ver debilidad #3).
- **`srcset`:** el componente central de imagen pinta un `<img>` sin `srcset`
  (`UI/Web/src/app/shared/image/image.component.html:1-8`); la URL de portada no
  lleva ancho.
- **Licencia:** GPL-3.0 (`LICENSE`).

### 3.3 Kapowarr v1.3.2 (`c191dda`, 2026-09-14)

- **Tamaño:** no lo elige. Guarda los **bytes** de `image.small_url` de Comic Vine
  (`backend/implementations/comicvine.py:326,512-516`) en la tabla
  `volumes_covers` (`backend/implementations/volumes.py:1199-1204`) y lo sirve
  tal cual (`frontend/api.py:1104-1112`). No hay reescalado en ningún punto
  (no se usa Pillow en el backend).
- **Presentación:** rejilla con `--entry-width: clamp(7rem, 11%, 9rem)` =
  hasta 144 px (`frontend/static/css/volumes.css:83`); ficha hasta 13,5 rem =
  216 px (`view_volume.css:37-40`). La imagen servida es una sola para ambas.
- **Cacheo:** no hay clave de versión ni revalidación explícita en la ruta; el
  fichero se sirve con `send_file` sobre `BytesIO`. No se han verificado las
  cabeceras que añade Flask a un `BytesIO` (**[sin verificar directamente]**).
- **Regeneración:** `Volume.update_cover` existe (`volumes.py:601-615`) pero
  **no tiene ninguna llamada** en el repo (`grep` de `update_cover`: solo la
  definición). La portada se fija al añadir/refrescar el volumen; no hay botón
  ni tarea de regeneración.
- **Fallo/ambiguo:** no hay regeneración ni reintento al pintar la rejilla; la
  portada se sirve tal como se guardó. No se ha verificado qué responde la ruta
  si la fila de `volumes_covers` quedó con `cover` nulo (**[sin verificar
  directamente]**).
- **Licencia:** GPL-3.0 (`LICENSE`).

### 3.4 Patrón web estándar (`srcset`/`sizes`, validadores)

- `srcset` + `sizes` resuelve **resolution switching** cuando hay varias
  variantes. El navegador multiplica la pista de `sizes` por el DPR antes de
  elegir ([MDN, `HTMLImageElement.sizes`](https://developer.mozilla.org/en-US/docs/Web/API/HTMLImageElement/sizes)).
  Sin `sizes`, la pista por defecto es la ventana (100vw) **[sin verificar
  directamente; comportamiento conocido de la spec, no medido aquí]**.
- El cacheo condicional con `ETag`/`If-None-Match` y `Cache-Control` está
  descrito en [MDN, HTTP caching](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching).
  `private, max-age=86400` ya se usa en ZascArr: la revalidación llega **después**
  de 24 h; hasta entonces el navegador puede reutilizar la imagen vieja sin
  preguntar.
- **Lectura para este caso:** `srcset` es la respuesta natural si hay que
  ahorrar bytes entre variantes (móvil vs escritorio, DPR 1/2/3) y el ancho
  presentado se puede declarar con `sizes`. ZascArr no sirve por Internet y su
  ancho de presentación depende de un `auto-fill`; el ahorro sería de bytes en
  LAN/localhost a cambio de multiplicar generaciones y entradas de caché en la
  Pi (ver §5.4).

### 3.5 Supuestos de su modelo que NO valen en ZascArr

- **«Un ajuste global de tamaño basta».** En ZascArr conviven dos usos con
  tamaños muy distintos: miniatura de 120 px y portada de hasta 200–296 px. Un
  único 300/600 para todo desperdicia en «Por revisar» o se queda corto en
  rejilla.
- **«Se puede regenerar en lote cuando haga falta».** La Pi comparte 512 MiB con
  Transmission/aMule/Prowlarr/Kavita; Komga documenta un caso de
  regeneración masiva que dejó el contenedor con carga/memoria al máximo y en bucle de reinicio ([#1961](https://github.com/gotson/komga/issues/1961)).
- **«La portada se genera al importar y no hay más».** En ZascArr la primera
  importación puede no haber extraído portada (CBR, fichero ausente) o haber
  cacheado una versión de 240; la historia exige que se rehaga **sola**.
- **«El almacenamiento de la miniatura es cosa del servidor».** ZascArr guarda
  JPEGs sueltos en `covers/` y su identificador es el nombre del fichero; la
  versión tiene que estar **en la ruta** o en el nombre, no en una tabla nueva.
- **«GPL del proyecto permite copiar el fichero».** ZascArr es GPL-3.0, así que
  copiar código GPL sería compatible, pero arrastraría modelos ajenos; este
  benchmark copia patrones, no código (ver Barrera legal en
  `benchmark-referencias.md`).

---

## 4. Teardown: flujo, fricciones, Kano y debilidad

### 4.1 Flujo core de cada referencia, con fricciones (heurística Nielsen)

- **Komga:** importar analiza → genera miniatura al ajuste global → la sirve
  desde almacén → si el usuario sube el tamaño, aviso → tarea de lote
  regenera. *Fricción:* el ajuste es global y la regeneración es de lote; no hay
  regeneración perezosa ni tamaño por uso. *Acierto:* el diálogo deja claro el
  alcance (solo las pequeñas / todas), visibilidad del sistema y control del
  usuario.
- **Kavita:** escanear/refrescar genera portada al `CoverImageSize` → la sirve
  como fichero → si falta, solo colecciones/listas se generan al vuelo. *Fricción:*
  las portadas ajenas al pipeline (proveedor, subida) pueden quedar fuera de
  tamaño y no hay mecanismo de recuperación claro ([#4913](https://github.com/Kareadita/Kavita/issues/4913)).
  *Acierto:* un tamaño por defecto generoso (320×455) y un enum de hasta 1265 px.
- **Kapowarr:** al añadir/refrescar, descarga `small_url` y la guarda → sirve
  bytes crudos. *Fricción:* sin tamaño por uso, sin versión y sin regeneración;
  una portada mala se queda. *Acierto:* simplicidad extrema y cero coste de
  generación (delega el tamaño en la fuente).

### 4.2 Kano (de la tarea «que mi biblioteca se vea nítida»)

| Tipo | Requisito | Evidencia / por qué |
|---|---|---|
| Básica | La portada se ve, no rompe la tarjeta y no se amplía un original pequeño | `utils/cover.py:117` ya usa `thumbnail` (no amplía); el marcador CSS cubre el 404 (`_componentes.html:23-31`) |
| Básica | Abrir Biblioteca no dispara trabajo de toda la colección | Criterio 4 de la historia; hoy no hay regeneración, así que no hay coste, pero tampoco nitidez |
| Rendimiento | Nítida a 2× en rejilla y ficha; la caché no crece sin límite | `ThumbnailSize`/`CoverImageSize` de las referencias; `#861` demuestra que 300 px se queda corto |
| Rendimiento | Regeneración invisible para el coleccionista, sin borrar nada | Criterio 3; Komga exige un diálogo + tarea, Kavita un refresh; ZascArr puede hacerlo al pedir |
| Deleitable | Un solo fichero sirve rejilla y ficha sin saltos de calidad | El 2× del uso normal (592) cabe en 600; el borde de 333 queda a 1,8×; un solo `<img>` evita `srcset` y `sizes` |
| Deleitable | Cero configuración nueva | El coleccionista no elige tamaños; el PO fija el umbral una vez |
| No deseado (reverse) | Un ajuste global de tamaño en Ajustes | Añadiría una decisión que el coleccionista no puede evaluar y una UI nueva; las referencias lo tienen porque sirven a muchos perfiles |

### 4.3 Mapa de debilidad: 3 quejas reales

| Referencia | Queja y enlace | Qué revela | Qué hacemos |
|---|---|---|---|
| Komga | [#861 «An option to generate larger thumbnails»](https://github.com/gotson/komga/issues/861): las miniaturas de ~300 px se ven borrosas en Tachiyomi; 10 reacciones; se cerró como «released» y el código actual ya ofrece 300/600/900/1200 | Un tamaño fijo pequeño produce queja real; la solución fue **poder subir el tamaño**, no `srcset` | Fijar 600 px para portada; no dejar 240 como único tamaño |
| Komga | [#1961 «Is There a Way to Set Task Threads in Config File»](https://github.com/gotson/komga/issues/1961): al subir de 300 a 600 y regenerar, «komga going full tilt», carga/memoria al máximo y reinicio en bucle | La regeneración **en lote** es peligrosa en un host pequeño; el usuario quedó atrapado sin poder entrar a bajar el ajuste | Regeneración **perezosa por portada**, no tarea de biblioteca; si se añade límite, semáforo local (MEJORAR condicional) |
| Kavita | [#4913 «Kavita+ cover art is stored at full resolution and can't be reclaimed»](https://github.com/Kareadita/Kavita/issues/4913): 2,69 GB en 1.340 portadas de proveedor, `covers/` de 6,21 GB, la mayor 3024×4299, sin forma de recuperarla | Sin una clave/servicio de generación único, la caché se llena de tamaños fuera de contrato; y «arreglar el encoding» no redimensiona | La generación es el **único** camino de escritura de la portada; el tamaño se aplica siempre al generar y la clave lleva la versión |
| (extra) Kavita | [#3260 «Wrong cover resolution when uploading custom covers»](https://github.com/Kareadita/Kavita/issues/3260): una subida de 720×1080 acaba en 213×320 | El redimensionado por ajuste es fácil de equivocar si se mezcla con subidas | No hay subida manual en esta historia; si BL-PORT2 la añade, el mismo contrato de tamaño |
| (extra) Kavita | [#3824 «Image can not cut into proper size of cover image for series»](https://github.com/Kareadita/Kavita/issues/3824): recortes distintos según la proporción de la fuente | El caso ambiguo es la proporción, no el ancho | `thumbnail` mantiene proporción y el CSS recorta; no se introduce recorte nuevo |

---

## 5. Matriz, veredicto, TCO y umbral

### 5.1 Pesos (suman 100) y por qué

| Criterio | Peso | Por qué |
|---|---:|---|
| Nitidez percibida | 30 | Es el objetivo de la historia; sin esto no hay historia |
| Coste en Pi | 20 | 512 MiB del contenedor y CPU de Pi; la regeneración no puede ser un lote ciego |
| Simplicidad de caché | 20 | Una caché que se corrompe o se llena es peor que una portada borrosa |
| Compatibilidad con lo ya hecho | 15 | La cascada C1 y `cached_image_response` ya funcionan; rehacerlos es riesgo |
| No-regresión de ETag/Cache-Control | 10 | Criterio 3 explícito; romper el 304 castiga a cada visita |
| Lock-in | 5 | Casi neutro: todo es local y estándar; solo penaliza atarse a una pieza |

Frente a los pesos por defecto (`benchmark-referencias.md`) se conserva la
estructura: encaje (25) → nitidez (30); coste en Pi 20; seguridad/legalidad (20)
→ simplicidad de caché (20); cobertura (15) → compatibilidad con lo hecho (15);
adaptabilidad (10) → no-regresión de ETag (10); mantenimiento de la referencia
(5) se retira y pasa a nitidez; lock-in se queda en 5 («casi neutro»). Suma 100
y solo cambia de sitio el 5 de mantenimiento, dentro del máximo de tres pesos
movidos.

### 5.2 Matriz 0–5 (cada celda, una línea de evidencia)

Opciones: **S0** no hacer nada; **A** subir el número único (`_THUMB_MAX_WIDTH`) sin separar usos;
**B** tamaño por uso + clave versionada + regeneración perezosa + fallback
legado, sin `srcset` (recomendada); **C** patrón Komga/Kavita completo (ajuste
global + tarea de lote); **D** `srcset` con dos variantes.

| Criterio (peso) | S0 statu quo | A solo subir número | B construir sobre lo propio | C adoptar patrón servidor | D `srcset` |
|---|---:|---:|---:|---:|---:|
| Nitidez (30) | **1** — 240/320 px; a 2× se ve blanda (criterio 1 sin cumplir) | **2** — 600 solo en portadas nuevas; las cacheadas a 240 siguen (`web/series.py:229-231`) | **4** — 600 cubre 2× de 296 CSS y 3× de 200; solo el borde de 333 queda a 1,8× | **5** — 600–1200 px y regeneración probada en servidores (Komga `ThumbnailSize`) | **5** — variante exacta por DPR (`sizes` × DPR, MDN) |
| Coste en Pi (20) | **5** — cero trabajo y cero bytes nuevos | **3** — caché 6,25× de píxeles (240→600); la miniatura de 120 recibiría 600 si se unifica | **4** — una extracción perezosa por portada visible; 600 ≈ 40 ms en banco local vs 12 ms a 240 | **1** — lote de toda la biblioteca; evidencia de OOM/crash (#1961) | **2** — 2–3 variantes por portada; el navegador casi siempre pedirá la mayor (DPR) |
| Simplicidad caché (20) | **5** — nada que versionar | **5** — una ruta y un número | **4** — una clave `v2/` + fallback legado; sin tabla ni job | **3** — ajuste + tarea + progreso + estados (Komga `TaskHandler:182`) | **2** — varias claves por serie y `sizes` por contexto |
| Compatibilidad (15) | **5** — no se toca | **5** — una línea en `cover.py` | **5** — misma cascada, mismos helpers; solo parámetro de ancho y ruta | **2** — sin cola/Redis (ADR-0011), UI de Ajustes nueva, almacén distinto | **3** — `ui.portada` y 4 plantillas ganan atributos; más superficie que probar |
| No-regresión ETag (10) | **5** — hoy cumple | **4** — ETag bien, pero no regenera (criterio 3) | **5** — `cached_image_response` intacto; ETag por mtime de la nueva ruta; mismo `Cache-Control` | **3** — habría que rehacer la respuesta y el ETag; riesgo de 500 | **4** — mismas cabeceras, pero más rutas que versionar |
| Lock-in (5) | **5** — ninguno | **5** — ninguno | **5** — código propio, HTTP estándar | **4** — patrón portátil, no producto | **5** — estándar HTML |
| **Total ponderado /5** | **3,80** | **3,60** | **4,30** | **3,10** | **3,40** |

**Lectura:** S0 puntúa alto en lo barato y aun así **no es elegible**: incumple
los criterios 1 y 3 de la historia. B gana porque resuelve el gatillo (nitidez)
sin renunciar a coste ni a la caché existente. C y D tienen buena calidad pero
pagan un precio que la Pi y el alcance no justifican.

### 5.3 Veredicto, umbral concreto y TCO

**Veredicto: CONSTRUIR SOBRE LO PROPIO**, adoptando de Komga/Kavita el contrato
—tamaño de generación explícito y regeneración controlada por dimensión— y de
Kavita el tamaño por defecto generoso; se descarta `srcset` y se descarta el
ajuste global. Clasificación por idea:

| Idea | Resultado | Motivo |
|---|---|---|
| Portada generada a un ancho explícito (no «lo que salga») | **Adoptar** | Es el contrato que usan las tres referencias |
| Un tamaño por defecto generoso (Komga 300; Kavita 320×455) | **Adaptar** | ZascArr necesita 600 para su rejilla; la unidad es el ancho, no el lado mayor |
| Tamaño por uso en vez de un ajuste global | **Mejorar** | Las referencias no separan miniatura de portada; ZascArr sí tiene dos usos medidos |
| Invalidación por dimensión/versión de caché | **Adaptar** | Komga compara dimensión en tabla; aquí no hay tabla: la versión va en la ruta |
| Regeneración perezosa al pedir la portada | **Mejorar** | Ni Komga ni Kavita la hacen para series; evita el lote que tumbó un host (#1961) |
| Regeneración en lote con tarea y progreso | **Descartar** | Coste y riesgo en Pi; no hay cola (ADR-0011) |
| Ajuste de tamaño en Ajustes | **Descartar** | Decisión del PO, no del coleccionista; una UI nueva para un valor que no puede evaluar |
| `srcset`/`sizes` | **Descartar** por ahora | Un solo fichero de 600 cubre el 2× medido; multiplicaría generaciones y caché (§5.4) |
| Fallback a la caché antigua si no hay fuente | **Construir sobre lo propio** | No hay precedente en las referencias; el invariante «no perder lo que hay» lo exige |

**Umbral que se fija antes de implementar** (criterio 1):

| Uso | Presentación medida | Densidad de referencia | Ancho objetivo |
|---|---|---|---:|
| «Por revisar» | 120 px | 2× | **240 px** (se queda como está) |
| Portada de serie (Biblioteca, Inicio, ficha) | 110–296 px; 333 px en el borde de una columna | 2× | **600 px** de ancho máximo |
| Descubrir/asistente | 80 px | 2× | **320 px** (sin cambios; caché aparte) |

Por qué **600** y no 400/480: el 2× del uso normal en la rejilla es 592 px
(296 CSS) y en la ficha 3× son 420; un único 600 cubre ese uso y deja el borde
de una columna (333 CSS → 666) al 90 % (1,8×). Bajar a 400 dejaría el caso de una
columna a 1,35×; subir a 666 solo mejoraría una banda de 38 px de ancho de
ventana a cambio de ~23 % más píxeles. Si la medición del criterio 4 muestra que
600 no cabe en el presupuesto, **la decisión de bajar a 480 es del PO antes de
implementar**, no del implementador. **Nunca se amplía**: se usa
`Image.thumbnail`, que no escala hacia arriba (criterio 2).

**Diseño de caché (contrato para la spec):**

1. Ruta nueva `covers/v2/<series_id>.jpg`; constante de versión documentada en
   `utils/cover.py`. Cambiar el ancho objetivo o el algoritmo = subir a `v3`.
2. Al pedir `/ui/series/{id}/portada`: si existe `v2`, servir. Si no, intentar
   **solo la extracción local** del primer `File` no ausente (600); si funciona,
   escribir `v2` y servir. Si no hay CBZ extraíble (CBR, `File` ausente, extracción
   fallida) y existe `covers/<id>.jpg` legado, **servirlo sin red** (no se copia al
   `v2`: así se reintenta la extracción local en la siguiente petición; la
   ausencia no se cachea, como hoy). Solo si no existe ninguna caché (serie
   nueva o sin v1) se usa `cover_url` como hoy —ahora a 600— y se escribe `v2`.
   Si no hay nada, 404.
   *Motivo de «legado antes que red»:* el criterio 5 prohíbe descargar «más allá de
   lo que ya hace hoy la cascada»; hoy, si hay caché, la cascada no llega a
   `cover_url`. Una serie cuya única caché sea vieja y sin CBZ extraíble se
   queda en 320 px (o 240 si el CBZ desapareció) hasta BL-PORT2 y se cuenta en
   el criterio 6 (tensión anotada en §8).
3. La caché antigua **no se borra nunca** desde la app; queda como respaldo y la
   purga el desinstalador (`scripts/uninstall.sh:361`).
4. `cached_image_response` no cambia: `ETag` = mtime del fichero servido,
   `Cache-Control: private, max-age=86400`, 304 con `If-None-Match`.
5. Escritura **atómica** (temporal en el mismo directorio + `os.replace`), para
   que un corte no deje un JPEG truncado que `exists()` daría por bueno.
6. `pendientes.py` sigue llamando al extractor con el ancho por defecto 240;
   `fetch_and_cache_cover` gana un ancho (320 por defecto) para no tocar
   Descubrir; `series.py` pasa 600.

**TCO y lock-in**

| Concepto | Estimación | Base |
|---|---|---|
| Construcción | 1–2 días de desarrollo + pruebas; sin dependencia ni migración | Cambio acotado a `utils/cover.py`, `web/series.py`, un parámetro en `fetch_and_cache_cover` y tests |
| Coste de arranque (una vez por serie vista) | ~40 ms/portada en banco local (i5-8365U, Pillow 12.1.1, 1600×2400) a 600 vs ~12 ms a 240; en Pi se espera **3–8× más** **(estimación, NOT RUN)** | Medición local §10; no es PASS/FAIL |
| Caché en disco | 240→600 multiplica píxeles ×6,25; banco sintético: 4–14 KB → 16–180 KB por portada (liso / ruido) | Medición local §10; la cifra real depende del arte |
| Operación | Sin puerto, sin job, sin Redis; mismo volumen `/config/covers` | `config.py:137`, `docker-compose.yml:166` |
| Lock-in | **Nulo**: HTTP estándar + Pillow ya presente; las referencias no se ejecutan en producción | — |

**Invariantes de ZascArr que la solución respeta:** no mentir (si el original es
pequeño, se dice en la medición del criterio 6, no se amplía); no borrar (caché
antigua y originales intactos); confirmación (no hay acción destructiva nueva);
coste Pi (perezoso, sin lote, fuera del event loop con `asyncio.to_thread`).

### 5.4 ¿Se justifica `srcset`?

No, con la evidencia de este encargo:

1. **Un solo fichero cubre el 2× del uso normal.** Las tres superficies de
   portada de serie comparten la misma imagen; 600 px cubre 2× hasta 300 px CSS.
   `srcset` solo añadiría variantes para un DPR que ya está cubierto.
2. **`sizes` sería aproximado y el navegador puede elegir la mayor.** La rejilla
   es `auto-fill`/`minmax`; el ancho real depende del contenedor y del número de
   columnas, no de un breakpoint limpio. El navegador multiplica `sizes` por DPR
   antes de elegir (MDN `HTMLImageElement.sizes`); con `auto-fill` la pista sería
   una aproximación y el ahorro, incierto.
3. **El cuello es CPU/disco, no ancho de banda.** ZascArr se sirve en localhost o
   LAN (`ADR 0004`), no por Internet. Generar dos o tres variantes por serie
   multiplica el trabajo de Pillow y las entradas de caché en la Pi para ahorrar
   bytes que no se pagan.
4. **`srcset` no resuelve el criterio 3.** La regeneración se resuelve con la
   clave de versión, no con variantes. Mezclar ambas añade dos ejes de
   invalidación.

**Cuándo se reevaluaría:** si ZascArr se sirve por Internet con ancho de banda
limitado, o si el PO quiere un tamaño distinto para la ficha (p. ej. una ficha
con portada a 400 CSS px). Entonces se compararía 600/1200 con `sizes` medidos.

---

## 6. IGUALAR (mínimos competitivos, semilla para EARS)

1. **Tamaño por uso con umbral fijado.** La miniatura de «Por revisar» se
   genera a 240 px y la portada de serie a **600 px de ancho máximo** (altura
   proporcional); Descubrir sigue a 320. Un CBZ de 1600×2400 produce 600 px; uno
   de 400×600 produce 400 px (no se amplía). *Aceptación:* medir el ancho del
   fichero de caché con Pillow en los tres casos.
2. **La caché se rehace sola sin perder nada.** Con una caché antigua
   `covers/<id>.jpg` presente **y un CBZ extraíble**, la primera petición devuelve
   200 con la versión nueva (`covers/v2/...`, 600) y la segunda, con
   `If-None-Match`, devuelve 304; `ETag` y `Cache-Control` conservan el formato
   actual; no se borra ningún fichero ni se pide al coleccionista que limpie
   nada. Si no hay CBZ extraíble pero hay caché antigua, se sirve esa caché **sin
   red** (no 404, y `cover_url` no se consulta: criterio 5).
3. **No hay red nueva ni regresión en lo que ya funciona.** La extracción desde
   CBZ funciona sin red; «Por revisar» mantiene su coste y su `ETag` por fichero
   origen; CBR sin extractor sigue devolviendo 404 y el marcador CSS; Descubrir
   mantiene su caché de 320.

## 7. MEJORAR (huecos por oportunidad, con evidencia)

1. **Escritura atómica de la caché.** Hoy `write_cover_cache` hace
   `dest.write_bytes(data)` (`utils/cover.py:185-192`) y `_resize_and_save`
   `img.save(dest)` (`:177-182`); un corte o un disco lleno deja un JPEG
   truncado que `web/series.py:229-231` servirá para siempre porque solo mira
   `exists()`. *Mejor:* escribir a `.<id>.tmp` y `os.replace`; probar con un
   fallo simulado a mitad. *Criterio:* ninguna petición sirve bytes truncados.
2. **Cerrar el borde de disco lleno.** Si `write_cover_cache` lanza
   `EspacioInsuficienteError`, `web/series.py:250-255` sigue llamando a
   `_etag_for(cache_path)`, que hace `stat()` sobre un fichero que no se escribió
   → `FileNotFoundError` → 500, en vez de servir los bytes ya extraídos. *Mejor:*
   `ETag` calculado de los bytes (hash) o sin `ETag` en ese borde, y prueba de
   regresión. (Leído en código; **NOT RUN**.)
3. **Medir el criterio 6 y no adivinar.** Hoy no hay instrumentación de «cuántas
   series quedan por debajo del umbral porque su original es pequeño o no hay
   extractor». *Mejor:* un informe de una pasada, solo lectura, que clasifique
   cada serie (caché < 600 / original < 600 / CBR sin extractor / sin fuente) y
   dé la cifra para decidir BL-PORT2 (§10.3). Sin datos, BL-PORT2 se refinaría a
   ciegas.
4. **(Condicional) Semáforo local de extracción.** Abrir una página en frío lanza
   hasta ~6 extracciones en paralelo (límite del navegador por host); con 600 px
   el pico de CPU sube. *Mejor:* `asyncio.Semaphore(2)` alrededor del
   `to_thread(extract_cover_thumbnail)` y medir antes/después; solo si la
   medición del criterio 4 lo pide. Evidencia del riesgo: Komga #1961.
5. **(Fuera de alcance) Refresco manual de una portada.** Si el original cambia
   o la portada elegida no gusta, BL-PORT2 es el sitio; no meterlo aquí.

## 8. Riesgos

| Riesgo | Impacto | Mitigación / nota |
|---|---|---|
| La URL no cambia; `max-age=86400` puede mostrar la imagen vieja hasta 24 h tras desplegar | Cosmético, temporal | El `ETag` cambia y la revalidación la actualiza; si el PO quiere efecto inmediato, añadir `?v=2` al `src` desde la plantilla (cambio pequeño, no necesario para el criterio 3) |
| Serie **sin CBZ extraíble** (CBR, ficheros ausentes) que solo tiene caché antigua externa: se queda en 320/240 y no se regenera (para no salir a la red) | Esa serie no cumple nitidez todavía | Contarlo en el criterio 6; si son muchas, BL-PORT2 decide si merece la pena la descarga. La tensión con el criterio 1 se eleva al PO |
| Regeneración concurrente de la misma serie: dos peticiones extraen a la vez | CPU desperdiciada, no corrupción (escritura atómica) | Aceptable en Pi (6 conexiones); un lock por clave sería sobrecoste si la medición no lo pide |
| Caché antigua huérfana (`covers/<id>.jpg`) crece | Disco | No se borra desde la app; el desinstalador purga `covers/`; un script de limpieza es opcional y fuera de alcance |
| La primera página del CBZ no es la portada (créditos, scan) | Portada «fea» pero existente | Comportamiento actual; esta historia no cambia la selección de página |
| Decodificar una página enorme (hasta 40 Mpx) en la Pi | Pico de RAM | `MAX_PIXELES_PORTADA` ya acota (`core/formato_contenedor.py:72`); el búfer de salida crece poco (600×900 ≈ 1,6 MB RGB) |
| El ancho 600 no cabe en el presupuesto de disco de alguna instalación | Decisión de producto | Medir (criterio 4) antes de cerrar; el PO puede bajar a 480 antes de implementar |

**Barrera legal:** Komga es MIT; Kavita y Kapowarr son GPL-3.0. No se reutiliza
ningún fichero de implementación; solo se documentan patrones. Si una
implementación futura copiara código de Kavita/Kapowarr, sería compatible con la
GPL-3.0 de ZascArr pero exigiría revisar el fichero concreto y sus avisos, como
manda `benchmark-referencias.md`.

## 9. NOT RUN y caducidad

**NOT RUN (no se ha ejecutado):**

- Medición en Pi (tiempos, CPU, RSS, tamaño de caché): **no ejecutada**.
- Navegador real en escritorio y móvil: **no ejecutado**.
- Komga, Kavita y Kapowarr en marcha: **no ejecutados**; solo lectura de código y
  contraste con issues públicas.
- Biblioteca real del coleccionista: **no medida** (no hay acceso a la BD/ficheros
  en este encargo).
- El 500 de disco lleno y la escritura truncada: **leídos en código, no
  reproducidos**.
- Cabeceras exactas que añade Flask `send_file` sobre `BytesIO` en Kapowarr:
  **[sin verificar directamente]**.
- `benchmark-U12-experimento` no se reutiliza: mide el alto de una portada que
  falla, no la nitidez.

**Banco local ejecutado (solo orden de magnitud, no Pi):** i5-8365U, Python
3.14.4, Pillow 12.1.1, página sintética 1600×2400, JPEG calidad 80–85; 600 px ≈
40 ms vs 240 px ≈ 12 ms; 600 px ≈ 16 KB (liso) / 180 KB (ruido) vs 240 px ≈
4 / 14 KB. **No es PASS/FAIL y no sustituye la medición en Pi.**

**Caduca:** ~60 días → **2027-01-03**, o antes si Komga/Kavita cambian su
contrato de portadas, si el PO cambia los tamaños de presentación o si BL-PORT1
se reformula.

## 10. Plan de medición en Pi (criterio 4) y criterio 6

No se ejecuta aquí; se propone para que la spec lo convierta en tarea. **La
medición va separada del entorno de desarrollo** (DoD de la historia).

### 10.0 Confirmar los anchos de presentación (criterio 1)

La tabla de §1 es un cálculo a partir del CSS (`auto-fill` + `--gutter`), no una
medición en navegador real. Antes de cerrar el umbral, abrir `/ui/biblioteca` y
`/ui/series/<id>` en Chrome y Firefox a 320, 375, 768, 900, 1240 y 1920 px CSS
(DPR 1 y 2), leer `getBoundingClientRect().width` de una `.library-card`, una
`.series-card` y `.series-cover`, y anotar. Si difiere >10 % de la predicción,
ajustar 600/480 **antes** de implementar; es la medida que pide el criterio 1.
En este encargo esas mediciones son **NOT RUN**; mínimo Chrome y Firefox, Safari
si el PO lo pide.

### 10.1 Banco por portada (frío y caliente)

- **Muestra:** 30 CBZ reales de la biblioteca (mezclar 10 pesados > 150 MB, 10
  medios, 10 ligeros) + 5 casos borde: original 400×600 (pequeño), 8000×12000
  (por encima del tope de 40 Mpx: debe rechazarse), CBR real, CBZ cuyo
  `formato_contenido` es ZIP, serie solo con `cover_url`.
- **Script de una pasada**, fuera de `src/` (p. ej. `scripts/medir_portadas.py`
  de usar y tirar, o un fichero temporal): importa `extract_cover_thumbnail`,
  abre el CBZ, extrae a 240/480/600, mide `time.perf_counter()`, `bytes` de
  salida y `resource.getrusage(RUSAGE_SELF).ru_utime`; 5 repeticiones por caso;
  reporta mediana y p95. Fijar el proceso a un núcleo (`taskset -c 0`) para que
  la comparación sea justa. En la Pi, ejecutarlo dentro del contenedor de la app
  con el fixture montado en solo lectura; **no** como parte de la app.
- **Criterio propuesto (a ratificar con el PO):** p95 de extracción en frío
  ≤ 400 ms a 600 px (≤ 600 ms si el original es > 12 Mpx); 30 portadas en frío,
  con 6 peticiones concurrentes, ≤ 6 s; lectura caliente (304) ≤ 30 ms; delta de
  RSS del proceso ≤ 40 MB; media de caché ≤ 60 KB/portada y ≤ 60 MB/1000 series.
  Son **umbrales de propuesta**, no mediciones.

### 10.2 Coste de página y de disco

- Con `COVERS_CACHE_PATH` apuntando a un directorio temporal **vacío**, recorrer
  los 30 ids con `curl -w '%{time_total}'` (frío) y repetir (caliente, 304);
  anotar `docker stats --no-stream` antes/durante/después y
  `/sys/fs/cgroup/memory.current`/`cpu.stat` del contenedor.
- `du -sb` del directorio de caché antes/después, `find -name '*.jpg' | wc -l`,
  media de bytes; extrapolar a 100/1000 series con la media medida, no con la
  del banco sintético.
- Repetir con 480 y 600 para que el PO elija con datos (§5.3).

### 10.3 Criterio 6 (cuánto queda por debajo y por qué)

Informe de una pasada, **solo lectura**, sobre la BD/ficheros reales:

1. Para cada `Series`, leer el ancho del JPEG cacheado con `Image.open(...).width`
   (solo cabecera).
2. Si < 600, abrir el primer `File` no ausente del mismo modo que la cascada y
   leer la cabecera de la primera página del ZIP (`Image.open(BytesIO(bytes))`
   sin decodificar); clasificar: **original < 600** / **sin extractor (CBR, PDF…)**
   / **sin fuente** (no hay CBZ ni `cover_url` utilizable).
3. Salida: CSV por serie + recuento por causa. No escribe ni en la BD ni en la
   caché. Esa cifra es la entrada de BL-PORT2.

## 11. Pruebas antes de implementar (§13, paso 5)

Estas pruebas se escriben **antes** del código y fijan el contrato; ningún
original real ni fuente externa.

1. **Original grande:** CBZ sintético 1600×2400 → caché `v2` con ancho 600
   (tolerancia ±1 px).
2. **Original pequeño:** CBZ 400×600 → caché con ancho 400 (no 600); se cumple
   «no ampliar».
3. **Caché antigua con CBZ:** escribir `covers/<id>.jpg` de 240 y un CBZ
   extraíble; pedir la portada → 200 con 600; segunda petición con `If-None-Match` del ETag devuelto → 304;
   el fichero antiguo sigue en disco.
4. **Sin CBZ extraíble y con caché antigua:** sin `File` utilizable, con
   `cover_url` presente y caché `covers/<id>.jpg` → se sirve la caché antigua
   (200) y **`fetch_and_cache_cover` no se llama** (criterio 5).
5. **Sin ninguna fuente:** sin `File`, sin `cover_url` y sin caché → 404 como hoy.
6. **Serie nueva solo con `cover_url`:** sin `File` y sin caché previa, se
   descarga una vez y se cachea `v2` a 600 (misma llamada que hoy, mayor
   redimensionado; no se amplía si la fuente es menor).
7. **CBR / sin extractor:** `extract_cover_thumbnail` sigue devolviendo `None`
   para `.cbr` real y, sin caché previa, el endpoint responde 404; no se pide
   nada a la red. Si hay caché previa, la sirve (prueba 4).
8. **`is_missing`:** el `File` ausente no se usa; se prueba el siguiente o se cae
   a `cover_url` (regresión de B7).
9. **Disco lleno:** `comprobar_espacio` lanza `EspacioInsuficienteError` →
   respuesta 200 con los bytes extraídos (no 500) y sin `ETag` que dependa de un
   fichero inexistente.
10. **Etiquetas/`pendientes`:** la miniatura de «Por revisar» sigue midiendo 240 y
    su `ETag` sigue saliendo del `mtime` del fichero origen.
11. **Descubrir:** la caché `covers/descubrir` sigue generándose a 320 (no se
    acopla al ancho de serie).
12. **Navegador real (fuera de pytest):** escritorio y móvil; comprobar que la
    rejilla, Inicio y ficha no muestran salto al cargar la imagen y que el
    marcador CSS sigue apareciendo en 404.

---

## 12. Lo que esta ficha NO decide

- Descargar portadas de fuera o sustituir una portada por otra de mejor
  resolución: **BL-PORT2** (su DoR depende de la medición del criterio 6).
- Extraer portadas de CBR reales: sigue fuera (`EXTENSIONES_CON_PORTADA`).
- Cambiar la edición catalogada, la selección de la primera página o el diseño
  de la ficha.
- Un ajuste de tamaño visible en Ajustes: se descarta (§5.3).
- Backlog, tablero y código: SCOUT.bench no los toca; esta ficha se enlaza desde
  la historia y la decide el PO.

## Actualización post-medición (2026-11-04, AC-02)

Medido en **Chrome 156 headless** (DPR 1 y 2), `main` `35283b5`, marcado real y `web.css`.

| Viewport CSS | Portada (CSS) | 2× requerido | 600 da |
|---:|---:|---:|---:|
| 320 | 290 | 580 | 2,07× |
| 357 | 327 | 654 | 1,84× |
| 900 (3 col.) | 188,8 | 377,6 | 3,18× |
| 1920 | 175,33 | 350,66 | 3,42× |

1. **1,8×** de §6/matriz = **columna única móvil** (357→327; 600/654 = 1,84×), no 3 columnas: a 900, 188,8 → 600 da 3,18×.
2. **Desviación §1:** 290 (no 296) a 320, 327 (no 333) a 357, Inicio 188,8 (no 171,5; +10,1 %). No cambia la decisión.
3. **`web.css:1113`** es la regla de 120 px dentro de `@media (max-width: 768px)`; 768→120, 769→140. El corte es **768**, no 1109: 1109 es `.series-grid`, no el ancho del corte.

**Conclusión: 600 se mantiene.** Máximo medido 290 CSS (580 a 2×; 600 = 2,07×); 480 habría dado 1,66× y 1,47× en la columna de 357 → **descartado**. Caché, regeneración perezosa, ETag y «sin `srcset`» no cambian.
