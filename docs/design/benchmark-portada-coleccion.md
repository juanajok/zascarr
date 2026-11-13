# Benchmark — portada de colección (#155 / task-209)

> Ficha de **nivel 1** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13): UI + datos
> derivados, sin migración obligatoria y sin ficheros de biblioteca. **Historia:** portada de
> colección, contexto de #155/BL-D6; tarea de benchmark `task-209`. **Base contrastada:**
> `origin/main` **`b7818c4`** (2026-11-13); el worktree local está un commit por detrás y el código
> de `Collection`/portadas es el mismo. **Fecha:** 2026-11-13. **Caduca:** ~2027-01-12.
> **No implementa**, no ejecuta la app, no consulta fuentes reales ni toca la Pi: es insumo para la
> especificación; decide el PO.

## 1. Problema local y caso real

`Collection` agrupa series y decide su auto-búsqueda (#155/BL-D6), pero **no tiene imagen**: ni
columna, ni DTO, ni ruta, ni plantilla. La lista `/ui/colecciones` y el detalle son texto; la
portada de serie, en cambio, ya está resuelta con una cascada local-first, proporción 2:3, caché
propia y sin hotlinking.

| Hecho comprobado | Evidencia |
|---|---|
| `Collection` solo tiene `id`, `name`, `description`, `auto_search`, timestamps y la relación `series`. **No hay `cover`, `cover_url` ni `metadata`**. | `src/zascarr/models/__init__.py:475-495` |
| La migración que creó `collections` no añadió imagen; el head real es **0033** y la siguiente sería **0034**. | `alembic/versions/20261112_0031_colecciones.py:26-49`; `alembic/versions/` (último: `20261112_0033_apartado_operaciones.py`) |
| El DTO de listado no lleva imagen y la lista pinta solo nombre, nº de series, política y descripción en un `<li>` de texto. | `src/zascarr/services/colecciones.py:22-28,114-123`; `src/zascarr/web/templates/colecciones.html:24-33` |
| El detalle pinta el nombre y la lista de series; tampoco hay imagen ni panel de portada. | `src/zascarr/web/templates/coleccion_detalle.html:8,81-90` |
| No hay endpoint `/ui/colecciones/.../portada` ni clase/plantilla de portada de colección. | `src/zascarr/web/colecciones.py` (rutas en `:49-185`); grep de `portada`/`cover` en `web/templates/coleccion*.html` |
| La portada de serie **sí** existe: cascada perezosa, 600 px, caché `covers/v3/<serie>.jpg` y `covers/externa/`, elección manual en `Series.metadata_["portada"]`, ETag y `Cache-Control` privado. | `src/zascarr/web/series.py:1242-1340`; `src/zascarr/utils/cover.py:64-74,279-291`; `src/zascarr/services/portada_serie.py` |
| El componente visual `.portada` ya impone **2:3**, marcador con inicial debajo y sin JavaScript; `ui.portada` lo reutiliza en tarjetas. | `src/zascarr/static/web.css:1619-1650`; `src/zascarr/web/templates/_componentes.html:30-33` |
| La caché de portadas cuelga de `covers_cache_path` (`/config/covers` por defecto), está fuera de la biblioteca y no se sirve por hotlink. | `src/zascarr/config.py:163`; `utils/cover.py:279-291` |

**Caso real.** Una colección como «Clásicos Bruguera» o «Grapas en curso» aparece en `/ui/colecciones`
como una fila de texto entre otras; al entrar, el detalle no da ninguna pista visual de qué
colección es. El coleccionista no puede reconocerla de un vistazo ni distinguirla de otra con un
nombre parecido. El resultado deseado es una imagen 2:3 coherente con la biblioteca, local,
económica en la Pi y que no dependa de un servicio externo para verse.

**Medición de partida (NOT RUN).** No se consultó la BD real: no se sabe cuántas colecciones hay,
cuántas series tiene la mayor, ni cuántas series tienen portada ya cacheada. Antes de especificar
hay que medir: colecciones totales, series por colección (máx./mediana), colecciones con 0/1/2-3/≥4
series con portada cacheada, y bytes de `covers/` ya usados. Estimación a validar: 1 mosaico
600×900 JPEG por colección ≈ decenas de KB; 20 colecciones ≈ 1–2 MB de caché, sin contar portadas
de serie que ya existen.

## 2. Referencias consultadas (versión/commit)

| Referencia | Versión / commit | Fecha | Licencia | Qué se leyó |
|---|---|---|---|---|
| **Sonarr** | `c018578e4b79ee048575c02d7a8aa2b929e4b837` (`develop`) | 2026-11-03 | GPL-3.0 | Árbol de `src/Sonarr.Api.V5` y modelo `Series`: **no hay entidad de colección** ni endpoint de imagen de colección; sus `Tags` son ids sin imagen. No se ejecutó la UI. |
| **Radarr** | `b9afb26be5822fb3e28038f157ac1a0f85611c5b` (`develop`) | 2026-10-11 | GPL-3.0 | `src/NzbDrone.Core/Movies/Collections/MovieCollection.cs`, `src/Radarr.Api.V3/Collections/CollectionResource.cs`, `src/NzbDrone.Core/Movies/RefreshCollectionService.cs`, `src/NzbDrone.Core/MediaCover/MediaCoverService.cs`, `frontend/src/Collection/Edit/EditMovieCollectionModalContent.tsx`, `frontend/src/Movie/MovieImage.tsx`. |
| **Plex** (propietario) | Solo documentación oficial; servidor no inspeccionable | docs consultadas 2026-11-13 | Propietario | [Collections](https://support.plex.tv/articles/201273953-collections/) y [Edit Details](https://support.plex.tv/articles/201272763-edit-details/): póster/art, elegir, subir, borrar y bloqueo. |
| **Jellyfin** | `96003befcfa451e466767a2cfb01b6f3a7a78367` (`master`) | 2026-11-13 | GPL-2.0 | `MediaBrowser.Controller/Entities/Movies/BoxSet.cs` (aspecto 2:3), `MediaBrowser.Providers/Plugins/Tmdb/BoxSets/TmdbBoxSetImageProvider.cs`, `Emby.Server.Implementations/Collections/CollectionImageProvider.cs`, `Jellyfin.Api/Controllers/ImageController.cs`, `MediaBrowser.Providers/Manager/ProviderManager.cs`. |
| **Komga** (local) | **1.29.2**, `25c67d14` | 2026-10-30 | MIT | `SeriesCollection.kt`, `ThumbnailSeriesCollection.kt`, `SeriesCollectionLifecycle.kt`, `SeriesCollectionController.kt`, `MosaicGenerator.kt`; migración `V20211206124920__collection_and_readlist_thumbnails.sql`. |
| **Kavita** | `a9cdf1cad9ae14f88a295c3a6fc7993f9823d59d` (`develop`, `0.9.1.22`) | 2026-11-11 | GPL-3.0 | `Kavita.Models/Entities/CollectionTag.cs`, `ReadingLists/ReadingList.cs`, `Kavita.Server/Controllers/UploadController.cs`, `ImageController.cs`, `Kavita.Services/CollectionTagService.cs`, `ReadingListService.cs`, `ImageService.cs`, `CoverImageSize.cs`, `cover-chooser-config-factory.service.ts`. |
| **Kapowarr** (local) | **v1.3.2**, `c191dda` | 2026-09-14 | GPL-3.0 | No hay modelo de colección; portada por volumen (`volumes_covers`/`update_cover`). No aplica. |
| **Mylar3** | `cdc94a4` (`v0.8.3`, `master`) | 2025-08-17 | GPL-3.0 | No se volvió a inspeccionar en esta ronda; la ficha previa `benchmark-BL-INF6-elegir-portada.md` no encontró colección ni portada de colección. **`[sin verificar]`** en esta ficha. |

**Límite explícito.** Plex es propietario: se cita su contrato **documentado**, no su código ni su
almacenamiento. Sonarr no tiene colecciones: su ausencia se comprobó en el árbol de código, no se
infiere de la UI. Mylar3 queda fuera de esta ronda salvo lo ya registrado.

## 3. Cómo lo resuelve cada referencia (contrato, no captura)

- **Sonarr — no aplica.** No hay colecciones ni imagen de colección; sus `Tags` no llevan portada.
  Lo único reutilizable es la idea ya conocida de **no inventar una entidad que el producto no
  tiene**.
- **Radarr — auto del proveedor, sin edición de imagen.** `MovieCollection` lleva
  `List<MediaCover> Images` (`MovieCollection.cs:11,26`), que llega del proveedor (TMDB/SkyHook).
  El refresco **sobrescribe** `collection.Images` (`RefreshCollectionService.cs:76`). El modal de
  edición solo **muestra** el póster; no hay campo ni subida (`EditMovieCollectionModalContent.tsx:113-119`),
  y el `CollectionResource.ToModel` de la API **no copia** `Images`. `MovieImage` usa `url` local o,
  si no, `remoteUrl` (`MovieImage.tsx:10-13`); no se encontró un pipeline de caché de colección
  análogo al de `Movie` en `MediaCoverService` (solo `Movie`/`MovieMetadata`). **Consecuencia:**
  Radarr demuestra el patrón “auto desde proveedor”, que ZascArr no puede adoptar porque no tiene
  proveedor de portadas de colección y prohíbe el hotlink.
- **Plex — collage automático + override manual fuerte.** Una colección colapsada muestra un póster
  **con hasta 4 imágenes de sus elementos**; al editar se puede añadir **póster propio, fondo y
  resumen**, elegir entre opciones existentes, o añadir arte **desde archivo local o URL**. La
  elección se guarda **inmediatamente** con una marca de verificación y los campos manuales quedan
  **bloqueados** frente a refrescos. Borrar una colección **no borra sus elementos**; una colección
  vacía con personalizaciones se conserva; solo el admin puede borrarla. Almacenamiento y API
  interna: **NOT RUN** (servidor propietario). Es la referencia UX más completa.
- **Jellyfin — imagen de proveedor + subida + composición condicionada.** `BoxSet` declara aspecto
  primario **2:3** (`GetDefaultPrimaryImageAspectRatio => 2.0 / 3`). Las imágenes pueden venir de
  TMDB (`TmdbBoxSetImageProvider`, tipos Primary/Backdrop/Thumb) o subirse con el endpoint genérico
  `POST /Items/{itemId}/Images/{imageType}` (elevación requerida; `ImageController.cs:352-389`;
  `SaveImage` en `ProviderManager`). La composición automática desde imágenes de miembros existe
  (`CollectionImageProvider`), pero **solo se activa si `item.IsLocked`** (`Supports` exige
  `IsLocked`); no se verificó si un refresco posterior reemplaza una imagen subida ni dónde la
  guarda exactamente (`[sin verificar]`).
- **Komga — override por bytes + mosaico automático.** `SeriesCollection` no tiene imagen;
  `ThumbnailSeriesCollection` guarda **bytes subidos** (`type = USER_UPLOADED`) y una marca
  `selected`. El POST `/{collection}/thumbnails` es **solo admin** y el `PUT .../selected` cambia
  la elegida (`SeriesCollectionController.kt:165-204`). Al servir, `getThumbnailBytes` devuelve la
  seleccionada o, si no hay, un **mosaico de hasta 4 portadas de series miembro**
  (`SeriesCollectionLifecycle.kt:240-289`; `MosaicGenerator` usa ratio `0.7067` (póster, algo más ancho que 2:3)). Borrar la
  colección **borra sus thumbnails** (`deleteCollection`). La imagen se sirve con
  `Cache-Control: private, max-age=3600`. El mosaico se recalcula al pedirlo.
- **Kavita — auto generado + elegir/subir con bloqueo.** `CollectionTag` y `ReadingList` tienen
  `CoverImage` y `CoverImageLocked` (`CollectionTag.cs:24-28`; `ReadingList.cs:27-33`). El
  `CollectionTagService` genera una **imagen fusionada** con portadas aleatorias de series
  (`GenerateCollectionCoverImage`; `ImageService.CreateMergedImage` compone 1, 2 o 4 celdas) del
  tamaño configurado; el `CoverImageSize.Default` es **320×455** (≈2:3). El upload
  `POST /upload/collection` acepta archivo/URL temporal, exige admin o dueño y guarda con
  `lockCover` (`UploadController.cs:290-339`); el selector de portada ofrece **portadas de series
  de la colección** (`forCollection`, `otherFunc`), upload y “reset”
  (`cover-chooser-config-factory.service.ts`). `CoverImageLocked` impide que el escaneo la
  reemplace.
- **Kapowarr / Mylar3 — no aplica.** Kapowarr no tiene colecciones; su portada es una sola por
  volumen, desde Comic Vine. Mylar3 tampoco modela colección (su “alternate cover” es un
  interruptor global primer/último número, ya documentado en BL-INF6) `[sin verificar]` en esta
  ronda.

## 4. Comparación por criterios

| Criterio | Radarr | Plex | Jellyfin | Komga | Kavita |
|---|---|---|---|---|---|
| **Origen** | proveedor (TMDB) | elementos (hasta 4), archivo, URL | TMDB, subida, miembros si locked | subida, mosaico de series | fusionada de series, subida, serie miembro |
| **Almacenamiento** | `Images` del proveedor; sin caché de colección encontrada | propietario, **NOT RUN** | imagen del proveedor/subida gestionada por Jellyfin `[sin verificar ruta]` | bytes en tabla de thumbnails | fichero en `CoverImageDirectory` |
| **Fallback** | ninguna imagen si no hay proveedor | collage de elementos; custom manda | composición solo si locked | mosaico de hasta 4 series | fusión de portadas aleatorias |
| **Borrar/editar** | refresco pisa imágenes; no hay editor de imagen | elegida se guarda; borrar colección no borra ítems; colección vacía custom se conserva | borrado de imagen genérico; comportamiento de colección **NOT RUN** | borrar colección borra thumbnails; series intactas | reset/desbloqueo; borrado/limpieza de fichero **NOT RUN** |
| **Permisos** | admin para editar la colección | admin borra; arte visible a usuarios | elevación para subir | subida solo admin | subida admin o dueño; lectura autenticada |
| **Coste Pi** | red + muestra remota | servidor propietario | proveedor/subida + composición | composición bajo demanda | composición al generar, ficheros |
| **Sin hotlink** | UI puede usar `remoteUrl` | n/a (servidor) | imágenes servidas por Jellyfin | bytes servidos por Komga | ficheros servidos por Kavita |

## 5. Supuestos de las referencias que NO valen en ZascArr

- **Que existe un proveedor de portadas de colección.** Radarr/Jellyfin lo tienen (TMDB); ZascArr
  no. La colección se define por series locales, no por un id de colección externo.
- **Que la colección tiene un orden de miembros estable.** `Collection.series` es una relación sin
  orden explícito; el mosaico debe fijar un orden determinista (`sort_title`, `title`, `id`) o el
  resultado cambiaría entre cargas.
- **Que se puede componer en el navegador con CSS.** Un grid de 4 `<img>` no es una imagen: no
  tiene ETag, no se puede cachear como una portada, no sirve para exportación ni para una tarjeta
  única y multiplica peticiones. Plex/Komga/Kavita componen en servidor.
- **Que subir un archivo es gratis.** Añade endpoint mutante, validación de contenido, límites,
  permisos, limpieza y un fichero fuera de la biblioteca; en la Pi hay que decodificar y
  redimensionar. El patrón actual de series es **elegir entre lo propio**, no subir (BL-INF6).
- **Que borrar una colección puede limpiar imágenes de series.** No: la colección solo agrupa; las
  series y sus archivos siguen (BL-D6).
- **Que el aspecto puede ser cualquiera.** Las referencias usan póster 2:3 (Jellyfin explícito,
  Kavita 320×455, Komga ratio 0,7067); ZascArr fija 2:3 exacto en `.portada`.

## 6. Resultado por idea

| Idea | Resultado | Motivo / condición |
|---|---|---|
| Collage automático con portadas de series miembro | **Adoptar/Adaptar** | Patrón común (Plex 4, Komga 4, Kavita fusión). En ZascArr: solo portadas **ya cacheadas**, sin extraer ni descargar; 1–4 celdas; 2:3 |
| Portada elegida de una serie miembro (override) | **Adaptar** | Kavita ofrece portadas de series de la colección; Plex permite elegir. En ZascArr: referencia `cover_series_id`, sin copiar bytes, con fallback al collage |
| Subida de archivo propia | **Descartar en esta fase** | Plex/Komga/Kavita/Jellyfin la tienen, pero exige endpoint, validación, almacenamiento y borrado; no hay portada de serie subida en el repo y el coste/riesgo no está justificado para el MVP |
| Portada remota del proveedor / URL | **Descartar** | Sin proveedor de colecciones en ZascArr; hotlink prohibido; SSRF y dependencia externa |
| Varias portadas por colección + seleccionada (Komga) | **Descartar** | Una colección tiene una portada; el override único cubre el caso |
| Lock/override que gana a lo automático | **Adoptar** | Plex bloquea campos manuales; Kavita `CoverImageLocked`; ZascArr ya tiene `metadata_["portada"]`/`locked_fields` para series |
| Fallback cuando la elegida desaparece o deja de ser miembro | **Adoptar** | Komga/Plex caen a collage; en ZascArr el render comprueba pertenencia y cae al mosaico sin romper |
| Borrar la colección limpia su caché, no las series | **Adaptar** | Plex no borra ítems; Komga borra thumbnails. ZascArr: borra `covers/colecciones/<id>` best-effort y no toca biblioteca |
| Proporción 2:3 | **Adoptar** | Jellyfin 2/3 exacto; Kavita 320×455; Komga mosaico 0,7067; ZascArr `.portada` 2:3 |
| ETag y caché privada por imagen | **Adoptar** | Komga `private, max-age=3600`; ZascArr usa `cached_image_response` con 86400 |
| Composición en CSS/JS | **Descartar** | No produce una imagen cacheable; ADR-0001; multiplica peticiones |
| Portada de texto/inicial generada | **Descartar** | Ya existe el marcador `ui.portada` con la inicial; una imagen generada sería ruido y fuente de i18n |
| Cubrir el hueco con la primera serie siempre | **Descartar** | Peor que el collage y que el override; no representa la colección |
| Hacer de esto una entidad/archivo nuevo en biblioteca | **Descartar** | La portada de colección es caché/vista derivada; no es contenido de la biblioteca ni se escribe en CBZ |

## 7. Opción principal recomendada — mosaico local 2:3 con caché

**Nombre de trabajo:** «portada de colección derivada»; **sin migración, sin subida y sin red**.

**Datos.**
- No se añade columna ni tabla: la portada **se deriva** de las series de la colección.
- Miembros candidatos: hasta 4 series de la colección con portada ya disponible en la caché local
  (`covers/v3/<serie>.jpg` o `covers/externa/<serie>.jpg`), ordenadas por `Series.sort_title`,
  `Series.title`, `Series.id` para que el resultado sea determinista.
- Si hay menos de 4, se compone con las disponibles; si no hay ninguna, `404` y la plantilla pinta
  el marcador `ui.portada` (inicial + tinta + trama). Una colección vacía no es un error.
- Composición: 1 imagen → 600×900; 2 → dos celdas verticales; 3–4 → 2×2; cada celda se recorta a
  la proporción de su celda con `object-fit`/Pillow equivalente; fondo neutro para celdas vacías.
  **No se pinta texto** en la imagen (el nombre va en el HTML; evita fuentes/i18n).
- Caché: `covers/colecciones/<collection_id>.jpg` + sidecar `.../colecciones/<collection_id>.json`
  con huella (`ids` + `mtime_ns`/`size` de las portadas usadas). Si la huella cambia (alta/baja de
  serie o cambio de portada de una miembro), se regenera; si no, se sirve la cacheada. Escritura
  atómica como `write_cover_cache`; si el disco falla, se sirve lo compuesto con `no-store` y no se
  rompe la pantalla. Una sola generación por colección (patrón `_GENERANDO` de series).
  **No se invoca la cascada de serie** para generar portadas que falten: eso podría extraer o
  descargar; el collage se hace solo con lo ya cacheado.

**Contrato HTTP/UX.**
- `GET /ui/colecciones/{id}/portada[.jpg]` → `200 image/jpeg` 2:3 con `ETag` y
  `Cache-Control: private, max-age=86400`; `404` sin caché si no hay ninguna portada (el marcador
  del HTML cubre el hueco, sin texto nuevo).
- Lista: cada fila/card incorpora `ui.portada(c.name, c.id, "/ui/colecciones/{{ c.id }}/portada")`
  con `loading="lazy"`; detalle: portada 2:3 junto al nombre (misma macro), sin JS. El marcador
  sigue siendo el fallback de la plantilla si el `<img>` falla.
- Sin hotlink: la imagen se sirve siempre desde `/config/covers` o se compone en servidor; no hay
  URL externa en el `src`.
- Escribir/editar nombre, descripción o política **no cambia** la portada; cambiar miembros o la
  portada de una miembro **sí** (por huella); borrar la colección borra su caché best-effort y no
  toca series, archivos ni B6.
- Español llano y presupuesto de texto: la portada no añade texto; el detalle puede decir «Se
  compone de las portadas de tus series» en `<details>` si hace falta.

**Coste y riesgos.** Coste: leer ≤4 JPEG ya cacheados + una composición Pillow 600×900 por cambio y
colección; después, una petición servida de caché con 304. Sin red, sin extracción de CBZ y sin
dependencia nueva. Riesgos: (1) una colección recién creada puede enseñar marcador hasta que sus
series tengan portada cacheada; (2) el collage no es “arte propio” y puede recortar portadas;
(3) la huella debe incluir `mtime_ns`/tamaño, no solo ids; (4) no confundir `covers/colecciones/`
con `covers/v3/` (espacios de id distintos); (5) el borrado de caché es best-effort y nunca debe
hacer fallar el borrado de la colección.

## 8. Alternativa recomendada — elegir una serie miembro como portada

**Cuándo.** Si el PO quiere control y el collage no le representa; es la evolución natural del
panel «Elegir portada» de serie (BL-INF6) sin abrir un endpoint de subida. **No es la principal**
porque exige migración y una pantalla nueva, y el collage ya cubre el caso por defecto.

**Datos.** `collections.cover_series_id UUID NULL REFERENCES series(id) ON DELETE SET NULL` (migración
**0034**, aditiva y reversible; el head actual es 0033). Alternativa equivalente si se prefiere
uniformidad con serie: `collections.metadata JSONB` con `{"portada": {"tipo":"serie","series_id":…,"fecha":…}}`;
se recomienda `cover_series_id` por ser tipado y barato, y porque no hay más metadata de colección.
Sin `UNIQUE`: una colección solo tiene un `cover_series_id`.

**UX.**
- Panel «Elegir portada» en el detalle, con las portadas de las series **de esa colección** (HTMX,
  parcial, sin JS): radio/selección, confirmar y «Usar la automática» para volver al collage. La
  acción no es `.primary`; un botón principal por pantalla ya está ocupado por «Guardar colección».
- Precedencia: `cover_series_id` válido y **aún miembro** con portada → se sirve la portada de esa
  serie (desde su caché local); si no, collage; si no, marcador. Nunca se rompe la página.
- Si la serie elegida se quita de la colección o se borra (`ON DELETE SET NULL`), la portada cae al
  collage; el campo puede quedar apuntando a una serie que ya no es miembro y el render lo ignora
  (se avisa en el panel y se ofrece «Usar la automática»). No se borra la elección en silencio.
- Borrar colección: la FK desaparece con la fila; no se borra ninguna serie. Reset: `NULL` y cae al
  collage. No hay bytes propios que limpiar; la caché del mosaico se regenera.

**Coste/riesgos.** Una lectura de la portada de serie ya cacheada (600 px) al servir, más la
migración y el panel; sin subida, sin validación de archivos, sin permisos nuevos (la app es de un
coleccionista; si hubiera usuarios, la elección sería de la colección, no del archivo). Riesgo de
UI: el panel necesita un estado vacío; no se debe perder el resto de filtros/estado al elegir
(patrón HTMX de BL-INF6).

**Subida/URL: descartadas por ahora.** Si el PO exige arte no-miembro, la referencia común es subir
archivo (Plex/Komga/Kavita/Jellyfin) con validación de imagen, límite de tamaño, recorte 2:3,
almacenamiento en `covers/colecciones/` y borrado; se pospone porque añade superficie mutua,
seguridad y pruebas que el escenario actual no justifica. URL externa/hotlink queda **prohibida**.

## 9. Matriz 0–5 (pesos suman 100)

Criterios: **local-first/sin hotlink 20** · **coste Pi 20** · **fallback/robustez 15** ·
**UX/expresividad 20** · **simplicidad y riesgo de implementación 15** · **coherencia con el repo 10**.
Opciones: **S0** sin portada; **A** mosaico local cacheado; **B** mosaico + override de serie
miembro (A + alternativa); **C** subida local; **D** URL/proveedor remoto/hotlink.

| Criterio (peso) | S0 | A mosaico | B mosaico+override | C subida | D remoto |
|---|---:|---:|---:|---:|---:|
| Local-first/sin hotlink (20) | **5** — no hay imagen | **5** — solo caché local | **5** — ambos locales | **5** — archivo local | **1** — viola la regla y SSRF |
| Coste Pi (20) | **5** — cero | **4** — ≤4 lecturas + 1 composición perezosa | **4** — igual + 1 lectura de serie | **2** — validar/decodificar/escribir | **1** — red y proveedor |
| Fallback/robustez (15) | **2** — solo marcador | **4** — marcador y caché; sin elegida huérfana | **5** — override → collage → marcador | **4** — archivo → collage, más errores de subida | **2** — depende del proveedor |
| UX/expresividad (20) | **1** — ninguna | **4** — identidad visual, sin control | **5** — control explícito | **5** — arte propio | **4** — arte del proveedor |
| Simplicidad/riesgo (15) | **5** — nada | **4** — caché/huella, sin migración | **2** — migración 0034 + panel | **1** — endpoint mutante, validación, borrado | **1** — red/SSRF |
| Coherencia con el repo (10) | **3** — hueco visual | **5** — local-first, `.portada`, sin migración | **4** — patrón BL-INF6; migración pequeña | **2** — no hay subida de serie | **1** — hotlink prohibido |
| **Total ponderado /5** | **3,55** | **4,30** | **4,25** | **3,35** | **1,75** |

**Lectura.** A gana por poco: resuelve la portada por defecto sin migración y con coste acotado; B
es casi igual de buena y añade control, pero paga migración + panel; C es la referencia “arte
propio” pero el coste/riesgo no se justifica en la Pi para el MVP; D es incompatible con las reglas
del repo. **Recomendación: A como principal; B como alternativa si el PO prioriza control.** C se
revisa solo si el PO pide arte no-miembro; D se descarta.

## 10. IGUALAR / MEJORAR

**IGUALAR (mínimo competitivo).**
1. **Portada de colección visible y 2:3 sin trabajo manual.** Plex/Komga/Kavita enseñan collage
   automático de miembros; ZascArr debe hacer lo mismo con 1–4 portadas locales y marcador si no
   hay, sin pedir al usuario que suba nada.
2. **Override explícito y protegido.** Plex permite elegir/cambiar arte y lo bloquea; Kavita
   `CoverImageLocked`; ZascArr debe dejar elegir una serie miembro (B) y que eso gane al collage
   sin que un proceso automático lo pise.
3. **Imagen servida localmente con ETag y caché privada.** Komga sirve bytes con caché privada;
   ZascArr debe servir desde `/config/covers` con `cached_image_response`, nunca `src` externo.

**MEJORAR (huecos con evidencia y coste).**
1. **Collage determinista y con caché por huella.** Komga recalcula el mosaico en cada petición y
   Kavita usa portadas aleatorias (`GetRandomCoverImagesAsync`); ZascArr puede fijar orden y
   huella (`ids + mtime/size`) para que la misma colección dé la misma imagen y el ETag sea 304.
   Coste: una lectura de `stat` por miembro y composición solo al cambiar; riesgo: huella mal
   calculada = portada obsoleta.
2. **Cero red y cero extracción de CBZ al pintar una colección.** Radarr/Jellyfin dependen de
   proveedor remoto; Komga/Kavita componen con portadas de serie. ZascArr puede leer **solo**
   portadas ya cacheadas, así una rejilla de colecciones no dispara 4 extracciones por colección
   en la Pi. Coste: colecciones nuevas pueden mostrar marcador; riesgo: expectativa de “ya debería
   estar” si las series no se han visitado.
3. **Override como referencia, no como bytes.** Komga guarda bytes y Plex/Kavita suben arte; en
   ZascArr elegir `cover_series_id` sigue la portada de esa serie cuando cambia (sin re-subir ni
   duplicar), y el fallback es automático. Coste: migración 0034; riesgo: una serie elegida que
   abandona la colección exige fallback/aviso.

## 11. Contradicciones y riesgos con el repo

| # | Hecho / riesgo | Evidencia y consecuencia |
|---|---|---|
| 1 | `Collection` no tiene campo de imagen ni `metadata`; la portada principal no puede persistirse | `models:475-495`; la opción A **no necesita** persistencia; la B necesita migración 0034 |
| 2 | La lista usa `<li class="arco-fila">` de texto, no una tarjeta con `.portada`; añadir imagen cambia maquetación | `colecciones.html:25-33`; hay que diseñar la fila/card (móvil y escritorio) sin romper el presupuesto de texto |
| 3 | El detalle tiene ya una sección de exportación (#B20/Kavita) y no tiene hueco de cabecera para portada | `coleccion_detalle.html:8,31-81`; la portada va junto al `h1`, sin desplazar la acción principal |
| 4 | La portada de serie solo se genera al pedirla; una colección que dispare su cascada multiplicaría extracciones | `series.py:1242-1340`; A usa solo caché existente, no la cascada |
| 5 | `.portada` asume un contenedor con ancho y 2:3; en una fila de lista hay que fijar ancho y `loading="lazy"` | `web.css:1619-1650`; `_componentes.html:30-33`; sin JS |
| 6 | La caché de colección no debe confundirse con `covers/v3/<id>` (ids de serie) | `utils/cover.py:64-74`; usar `covers/colecciones/` separado |
| 7 | `Collection.series` no tiene orden explícito; sin orden fijo el collage cambia | `models:493-495`; ordenar por `sort_title,title,id` |
| 8 | El borrado de colección no debe tocar series ni archivos (BL-D6) | `services/colecciones.py:192-199`; limpiar solo caché best-effort |
| 9 | No hay endpoint mutante de subida de portada de serie; introducir uno solo para colección sería una excepción | BL-INF6 (`services/portada_serie.py`) elige entre candidatas locales; C exige justificar el nuevo contrato |
| 10 | El siguiente Alembic es 0034 (head 0033); B no puede ser «sin migración» | `alembic/versions/`; la ficha lo declara explícitamente |

## 12. Casos de prueba antes de implementar (semilla)

1. Colección con 0 series → `GET .../portada` 404, lista/detalle muestran marcador, sin error.
2. Colección con 1, 2, 3 y 4 series con portada cacheada → composición 1/2/(2×2 con una celda
   vacía)/2×2, 2:3, misma imagen en dos peticiones (ETag 304).
3. Una serie miembro cambia de portada (mismo `series_id`, otra caché) → huella cambia y el
   collage se regenera; no se sirve la versión vieja.
4. Se añade/quita una serie → se regenera; una serie sin portada no rompe; si todas desaparecen,
   404/marcador.
5. Colección borrada → `covers/colecciones/<id>` se limpia best-effort; series/archivos intactos.
6. B: se elige una serie miembro → se sirve su portada; se quita de la colección → collage y aviso;
   se borra la serie → `cover_series_id` NULL y collage.
7. Reinicio de app/proceso → el collage cacheado sigue sirviéndose sin recomponer; ETag correcto.
8. Sin red y sin archivos de biblioteca → ninguna petición de colección abre CBZ ni descarga; el
   test puede contar aperturas/llamadas a 0.
9. Disco lleno al escribir la caché → se sirve lo compuesto con `no-store`, la colección se ve y
   no hay 500.
10. Borrar/editar nombre o descripción no cambia la portada; el marcador de una colección sin
    imagen usa la inicial correcta.

## 13. PASS / FAIL / NOT RUN

- **PASS:** el hueco local está fijado con fichero:línea (modelo, migración, DTO, plantillas, sin
  endpoint); la portada de serie y el componente 2:3 están verificados; se han leído los contratos
  de Sonarr/Radarr/Plex/Jellyfin/Komga/Kavita; la recomendación principal y la alternativa tienen
  contrato de datos/UX, fallback, borrado y coste; matriz y barrera legal incluidas.
- **FAIL:** ninguno detectado. No se ha encontrado una contradicción con las reglas del repo; la
  ausencia de proveedor de portadas de colección es un hecho, no un fallo de la ficha.
- **NOT RUN:** no se ejecutó la app, ni Postgres, ni la Pi, ni el navegador; no se levantaron
  Sonarr/Radarr/Plex/Jellyfin/Komga/Kavita (solo lectura de código/docs); Plex es propietario y su
  almacenamiento/API interna no se verificaron; no se verificó si Jellyfin reemplaza una imagen
  subida en un refresco; Radarr no se ejecutó; Mylar3 no se releyó en esta ronda `[sin verificar]`;
  no hay medición de colecciones/series por colección, de latencia ni de bytes de caché; no hay
  prueba de usuario sobre collage frente a arte propio.

## 14. Barrera legal (§13)

Sonarr/Radarr/Kapowarr/Mylar3/Kavita son **GPL-3.0**; Jellyfin **GPL-2.0**; Komga **MIT**; Plex es
**propietario** (solo se citan documentos funcionales). Se copian **patrones y contratos** (collage,
override, caché, 2:3, bloqueo), nunca código, textos, plantillas, estilos, iconos, migraciones ni
diseños de esas aplicaciones. Las portadas de las referencias son material ajeno: ZascArr solo usa
las portadas de las series de la propia biblioteca del coleccionista y las cachea localmente; no se
descargan portadas de colección de TMDB/Plex ni se reutiliza arte de ejemplo. ZascArr es GPL-3.0 y
esta ficha no cambia su licencia.

**Caducidad:** ~2027-01-12, o antes si cambia `Collection`/portadas de serie, si el PO elige subida
o si una referencia cambia en los ficheros citados. Al caducar, se rehacen las citas sobre el SHA
vigente y se actualiza la tabla de referencias. Lo no ejecutado sigue NOT RUN hasta que se ejecute.
