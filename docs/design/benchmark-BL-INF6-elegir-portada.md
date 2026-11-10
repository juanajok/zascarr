# Benchmark — BL-INF6: elegir la portada de la serie entre varias

> Historia **#592 (BL-INF6)**: elegir la portada de la serie entre varias. Ficha breve (§13), sin
> matriz (nivel 1: comportamiento nuevo reversible sobre servicios ya existentes). Lectura:
> 2026-11-10, código vigente contrastado en `main` (`d26d815`, incluye BL-INF4 fusionada y el fix
> de previa única). Benchmark previo del cimiento: `benchmark-BL-INF4-portada-numero.md`;
> especificaciones vivas de referencia: `especificacion-BL-PORT1.md`, `especificacion-BL-PORT3.md`,
> `especificacion-BL-INF4-portada-numero.md`.

## Historia / problema observado

Como coleccionista, quiero elegir cuál de las portadas de mis números es la portada de la serie,
para que la biblioteca enseñe la portada que yo quiero (p. ej. la del número que más me gusta o la
de una edición concreta), no la que la cascada decidió por mí.

Hoy la portada de la serie la elige SOLO la cascada (`src/zascarr/web/series.py:830 portada`):
0. portada previa con ancho suficiente (caché legada o externa, ≥ 300 px, #435) →
1. `covers/v3/<id>.jpg` →
2. primer `File` no ausente por `sort_order` que dé portada (topes de intentos/evaluados y
   presupuesto de segundos; RAR con marca de fallo) →
3. caché legada pequeña →
4. externa/`cover_url` →
5. 404.
No existe ninguna forma de fijar la elección: la clave `portada` no se usa hoy en
`Series.metadata_` (grep del paquete: solo `cortesia.py` y `url_portada.py` mencionan «portada», sin
relación con una elección).

El cimiento ya está puesto por BL-INF4: miniaturas por número cacheadas **por archivo**
(`covers/v3/numero/<file_id>.jpg`, 240 px, clave estable `File.id`, invalidadas por
mtime/tamaño — `especificacion-BL-INF4-portada-numero.md` §3.3) y servidas en
`GET /ui/series/{series_id}/numero/{issue_id}/previa.jpg` con ETag y `max-age=86400`. El panel de
elección puede enseñar candidatas **sin extraer ni descargar nada nuevo**.

Propuesta del builder (a contrastar): candidatas = portada actual + hasta 12 números con archivo +
externa cacheada; elección guardada en `Series.metadata_["portada"]`; regenerar
`covers/v3/<serie>.jpg` al elegir; `cover_url` queda manual/protegida; sin escribir en los archivos
de la biblioteca.

## Datos reales y medición de partida

Sin medición nueva: el coste de enseñar candidatas es ~0 (miniaturas ya cacheadas por INF4) y el de
elegir es **una** regeneración de 600 px con el presupuesto ya existente de la cascada (topes,
marcas de fallo de RAR, turno `unar` serializado, escritura atómica). Serie tipo: decenas de
números; el panel enseña ≤ 12. Riesgo de coste real: NINGUNO periódico; solo el pico puntual de la
regeneración (el mismo que hoy paga la cascada en frío). Medición en la Pi: NOT RUN (no aplica un
banco sintético; el presupuesto heredado de PORT1 ya está medido en `medicion-BL-PORT1-2026-11-06.md`).

## Referencias consultadas (URL, versión/commit; lectura 2026-11-10)

1. **Komga** — checkout local `komga/repo`, commit `25c67d1` (`gradle.properties` declara 1.29.2;
   licencia MIT). Código del backend leído del árbol del commit (`git show`, el checkout es sparse):
   `komga/src/main/kotlin/org/gotson/komga/domain/service/SeriesLifecycle.kt`,
   `interfaces/api/rest/SeriesController.kt`, `domain/model/ThumbnailSeries.kt`,
   `infrastructure/jooq/main/ThumbnailSeriesDao.kt`.
2. **Sonarr** — GitHub `Sonarr/Sonarr`, rama `develop`, commit
   `c018578e4b79ee048575c02d7a8aa2b929e4b837` (2026-11-03, GPL-3.0):
   `src/NzbDrone.Core/Tv/Series.cs` (`Images`), `src/NzbDrone.Core/MediaCover/MediaCoverService.cs`,
   `src/NzbDrone.Core/Tv/RefreshSeriesService.cs`.
3. **Kavita** — GitHub `Kareadita/Kavita`, rama `develop`, commit
   `9e177701c359090fa62e2e90aba571567c6cc680` (2026-11-01, v0.9.1.18, GPL-3.0):
   `Kavita.Models/Entities/Series.cs` (`CoverImage`, `CoverImageLocked`).
4. **Kapowarr** — checkout local `kapowarr/repo`, commit `c191dda` (v1.3.2, GPL-3.0):
   `backend/implementations/volumes.py` (`volumes_covers`, `update_cover`).
5. **Mylar3** — GitHub `evilhero/mylar3`, `master`, commit `0e07100` (2026-11-10, GPL-3.0):
   `mylar/config.py` (`ALTERNATE_LATEST_SERIES_COVERS`), `mylar/importer.py`, `mylar/helpers.py`.
6. **Jellyfin** — GitHub `jellyfin/jellyfin`, `master` (2026-11-10, GPL-2.0):
   `Jellyfin.Api/Controllers/RemoteImageController.cs`.
7. **Plex** — solo documentación oficial (servidor propietario):
   <https://support.plex.tv/articles/201272763-edit-details/> («Change Artwork», última mod.
   2026-08-19).
8. **ComicTagger** — GitHub `beville/ComicTagger`, `master` (2026-11-10, Apache-2.0), README.

## Cómo lo resuelve cada una

- **Komga (demostrado por código) — el análogo directo.** Cada serie puede tener varios
  `ThumbnailSeries` (generados de un libro, subidos o sidecar). Uno solo es el seleccionado:
  `PUT /api/v1/series/{seriesId}/thumbnails/{thumbnailId}/selected`
  (`SeriesController.kt:544-554`, solo admin, 202) llama a `markSelected`, que deja UN único
  seleccionado (`SeriesLifecycle.kt:303-317`). Al servir la portada,
  `getSelectedThumbnail` gana siempre; si no hay seleccionado (o el sidecar seleccionado
  desapareció), un *housekeeping* re-elige y, en última instancia, cae a la política de la
  biblioteca `SeriesCover` (FIRST / FIRST_UNREAD_OR_FIRST / FIRST_UNREAD_OR_LAST / LAST) → la
  miniatura del libro correspondiente (`SeriesLifecycle.kt:240-289`). Si hay más de un
  seleccionado (corrupción/race), el housekeeping conserva el primero y lo registra
  (`SeriesLifecycle.kt:369-376`). La elección persiste en BD y sobrevive a rescans. El thumbnail
  elegido GUARDA los bytes (o la URL del sidecar), no una referencia re-derivable del libro.
- **Sonarr (demostrado por código).** La serie lleva una lista `Images: List<MediaCover>` con
  `CoverType` (Poster, Banner, Fanart…) y URL remota (`Series.cs:14,45`). La elección del usuario
  es esa lista persistida: `MediaCoverService.EnsureCovers` descarga a disco solo la imagen cuya
  URL remota difiere de la guardada y genera variantes redimensionadas (500/250 para póster),
  servidas por el proxy local `/MediaCover/{id}/{type}.jpg` (`MediaCoverService.cs`). Detalle
  ARM/Pi relevante: semáforo explícito para limitar redimensionados concurrentes («ImageSharp is
  slow on ARM»). **Debilidad documentada en código:** el refresh del proveedor reasigna
  `series.Images = seriesInfo.Images` (`RefreshSeriesService.cs`), así que la elección manual NO
  está protegida frente a un refresh que cambie el set de imágenes.
- **Kavita (demostrado por código).** `Series.CoverImage` (ruta gestionada por Kavita, dentro de
  su APPDIR) + `Series.CoverImageLocked`: «si la portada fue sobreescrita por el usuario, NO se
  actualiza durante los scans normales» (`Kavita.Models/Entities/Series.cs:60-64`). Patrón
  mínimo y claro: la elección del usuario persiste con un flag de bloqueo que los procesos
  automáticos respetan.
- **Kapowarr (demostrado por código).** Una sola portada por volumen: `volumes_covers` (una fila
  con los bytes), bajada de Comic Vine; `update_cover` permite cambiarla programáticamente
  (`backend/implementations/volumes.py:357-367,601-613,1199-1200`). No hay elección entre
  portadas de números ni candidatas propias.
- **Mylar3 (demostrado por código).** `ALTERNATE_LATEST_SERIES_COVERS` (config global, default
  False) decide si la portada de serie sale del ÚLTIMO número en vez del primero
  (`mylar/config.py:95`; `mylar/importer.py:312,472`); «alternate cover» es un FALLBACK de Comic
  Vine cuando la principal falla (`mylar/helpers.py:4103-4109`). Es un interruptor global, no una
  elección por serie entre portadas propias.
- **Jellyfin (demostrado por código, parcial).** Elección de imagen por descarga de una URL
  remota del proveedor: `POST /Items/{itemId}/RemoteImages/Download?type=…&imageUrl=…`
  (`Jellyfin.Api/Controllers/RemoteImageController.cs:151-171`, elevación requerida) →
  `ProviderManager.SaveImage` la guarda como imagen del item. El contrato «la elegida no se
  reemplaza en refrescos» NO se verificó en código (NOT RUN).
- **Plex (documentado).** «Change Artwork»: elegir entre las opciones existentes (desplazamiento
  horizontal), la elegida se guarda **inmediatamente** con una marca (check); se puede añadir
  arte nuevo (URL o fichero); los campos editados a mano se bloquean frente a refrescos de
  metadatos (artículo «Edit Details»). Patrón UX canónico de selección entre opciones con
  guardado inmediato.
- **ComicTagger (demostrado por README).** Etiquetador de metadatos ComicInfo (escribe DENTRO de
  los archivos). No gestiona portadas de biblioteca; aporta solo si se quisiera escribir en los
  CBZ — expresamente fuera de esta historia.

## Supuestos de su modelo que NO valen en ZascArr

- Komga: carpeta = serie y libros sueltos dentro; el thumbnail seleccionado persiste sus BYTES (o
  una URL de sidecar) en una tabla propia, y existe un pipeline de thumbnails con presupuesto
  propio. ZascArr ya tiene miniaturas por archivo (INF4) y una caché v3 de serie: la elección
  puede ser una REFERENCIA (`file_id`) materializada de forma perezosa, sin tabla nueva.
- Sonarr: las candidatas son imágenes de un proveedor de metadatos remoto (fanart.tv/TVDB), con
  red, resizing y proxy local; la elección es la URL remota y el refresh del proveedor la puede
  pisar. ZascArr elige entre portadas PROPIAS (sin red) y la elección debe sobrevivir a
  refrescos/rescans.
- Kavita: la portada bloqueada es una imagen gestionada por la app (subida/elegida), no una
  referencia a un número; el «lock» es un booleano global de la serie.
- Kapowarr/Mylar3: portada única desde la fuente externa; el «alternar» de Mylar3 es global y
  binario (primer/último número).
- Jellyfin/Plex: productos propietarios/enteros con proveedores de imágenes remotos; de Plex solo
  se toma el contrato UX documentado, sin código verificable.

## Resultado por idea (adoptar / adaptar / mejorar / construir sobre lo propio / descartar)

- **ADAPTAR (Komga)** — «una única seleccionada + fallback automático cuando no la hay o la
  elegida dejó de servir + housekeeping de duplicados»: en ZascArr, `Series.metadata_["portada"]`
  guarda `{"file_id": …}` (referencia, no bytes); la cascada `portada` sirve PRIMERO la elección
  (materializada perezosamente en `covers/v3/<serie>.jpg` con el pipeline 600 px existente); si el
  archivo elegido no da portada (desaparecido, RAR con marca de fallo), se cae a la cascada actual
  SIN borrar la elección ni marcar error falso (análogo al fallback de Komga). Un único valor
  clave no necesita housekeeping de duplicados, pero SÍ la regla «una elección huérfana no
  bloquea la cascada».
- **ADAPTAR (Kavita/Plex)** — «la elección del usuario no la pisa el proceso automático»: la
  elección gana a la cascada, al enricher (que no toca portadas) y a los rescans; solo se quita
  cuando el usuario la quita o elige otra. `cover_url` queda manual/protegida (el panel no la
  pisa; la externa cacheada sigue disponible como candidata).
- **ADOPTAR (Plex, documentado)** — patrón UX «elegir entre opciones con marca de selección y
  guardado inmediato», en versión htmx (botón de elegir por candidata o radio + guardar; sin JS
  nuevo, ADR-0001). La garantía U21 («no se mueve ni se renombra nada; solo cambia la portada que
  se ve») va junto a la acción.
- **ADOPTAR (Sonarr, código)** — la contención de redimensionado en ARM (semáforo para no saturar
  la Pi con redimensionados concurrentes): ZascArr ya la tiene de facto (una sola generación por
  serie, FR-18; turno `unar` serializado); la ficha la fija como requisito explícito de la
  regeneración al elegir.
- **CONSTRUIR SOBRE LO PROPIO** — candidatas del panel = miniaturas INF4 ya cacheadas
  (`previa.jpg`, ETag, `max-age=86400`) + la actual + la externa cacheada: abrir el panel NO
  extrae ni descarga nada; la regeneración de `covers/v3/<serie>.jpg` reutiliza
  `extract_cover_thumbnail` a 600 con los topes, marcas de fallo y escritura atómica de PORT1/PORT3;
  la elección en `metadata_` (JSONB) sin migración ni dependencia nueva. Sobrecoste a registrar:
  un paso nuevo en la cascada (prioridad 0) y el guardado/borrado de la clave.
- **MEJORAR (con evidencia)** — (1) frente a Sonarr: la elección sobrevive a refrescos (evidencia:
  `RefreshSeriesService.cs` reasigna `series.Images` desde el proveedor, sin respetar una
  elección manual). (2) frente a Komga: la elección como REFERENCIA a `file_id` re-derivable
  (evidencia: `ThumbnailSeries` persiste bytes/url, no una referencia re-validable; en ZascArr la
  miniatura por archivo ya se invalida por mtime/tamaño — contrato INF4 §3.3). Criterio
  comprobable: reemplazar el CBZ del número elegido (mismo `File`) y que la portada de serie siga
  siendo la de ese número, regenerada sin pasos manuales.
- **DESCARTAR** — Sonarr «imágenes del proveedor remoto con resizing local y proxy»
  (red + pipeline nuevo; ZascArr elige entre lo propio). Mylar3 `ALTERNATE_LATEST_SERIES_COVERS`
  (interruptor global primero/último, no es elección por serie). Jellyfin
  `RemoteImages/Download` (descargar imágenes remotas; no aplica a portadas propias). ComicTagger
  (escribe dentro de los CBZ; contradice «no escribir en los archivos de la biblioteca»).
  Kapowarr (una sola portada por volumen desde CV: no aporta selección).

## Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi)

1. No escribir en los archivos de la biblioteca: solo lectura para regenerar la v3 al elegir.
2. Sin hotlinking ni red nueva: las candidatas son SIEMPRE locales (miniaturas INF4, actual v3,
   externa CACHEADA); `cover_url` se descarga por el camino existente y protegido
   (`utils/url_portada.py`).
3. La elección es una clave JSONB (`metadata_["portada"]`) sin migración; no se inventa estado en
   columnas nuevas.
4. La cascada actual queda como fallback intacto; la elección es el paso 0. Una elección huérfana
   o con portada fallida NO bloquea: cae a la cascada y se informa, sin borrar la elección.
5. Coste Pi: el panel no precarga (≤ 12 `<img>` cacheados con ETag); la regeneración al elegir es
   UNA escritura de 600 px con los topes existentes, una generación por serie (FR-18) y turno
   `unar` respetado.
6. Honestidad: si el número elegido no tiene portada utilizable, el panel lo dice («este número
   no tiene portada») en vez de fallar en silencio; la marca de fallo de RAR se respeta.
7. UX: un botón principal por pantalla (la acción principal de la ficha de serie sigue siendo la
   suya; «elegir» es una acción de panel, no `.primary`); textos en español llano sin palabras
   internas («miniatura», «caché» no salen a superficie).

## Casos de prueba antes de implementar (semilla para la spec del builder)

1. Elegir un número con miniatura → `metadata_["portada"]` apunta a su `file_id`,
   `covers/v3/<serie>.jpg` se regenera con ESA imagen y `GET /ui/series/{id}/portada` la sirve.
2. La elección gana a la previa con ≥ 300 px (PORT5) y a la externa; `cover_url` manual no se pisa.
3. El archivo elegido desaparece (o su RAR tiene marca de fallo) → la cascada cae al siguiente
   paso SIN borrar la elección; no se cuenta como error del sistema.
4. Reemplazar el CBZ elegido (mismo `File`, otro contenido) → la elección sigue siendo válida y la
   portada de serie se re-materializa de la miniatura nueva (perezoso, mismo patrón de hoy).
5. Quitar la elección → se borra la clave y la cascada vuelve a su orden automático.
6. Sin red: abrir el panel y elegir no llama a ninguna fuente externa (mock con 0 llamadas).
7. Sin escritura en la biblioteca: assert de que ningún archivo de la carpeta cambia (mtime/hash).
8. Serie sin archivos (solo externa cacheada) → el panel ofrece la externa y lo dice; sin
   candidatas → estado vacío honesto.
9. Coste: abrir el panel con las 12 candidatas ya cacheadas no extrae nada nuevo (contador de
   aperturas de CBZ a 0); elegir regenera UNA sola imagen con el presupuesto existente.
10. Dos elecciones seguidas (cambio de opinión) → la segunda regenera y no quedan artefactos
    (escritura atómica; sin ficheros huérfanos en v3).

## Decisión final / ADR si cambia arquitectura

DECIDE EL PO. Recomendación de SCOUT.bench: construir sobre lo propio — miniaturas INF4 como
candidatas, cascada PORT1 como fallback intacto, elección persistida en `Series.metadata_["portada"]`
como REFERENCIA a `file_id`, materializada perezosamente en `covers/v3/<serie>.jpg` con el
pipeline existente — adaptando de Komga el «una sola seleccionada + fallback automático» y de
Kavita/Plex el «la elección del usuario no la pisa lo automático». Sin migración, sin dependencia
nueva, sin red nueva. No exige ADR (no cambia arquitectura); si el PO quiere fijar la prioridad
de la elección en la cascada como decisión duradera, un ADR corto basta.

## IGUALAR / MEJORAR (con evidencia)

- **IGUALAR (mínimo competitivo):** Komga — elegir entre portadas PROPIAS de los números, una
  seleccionada persistente, la elección gana a lo automático y, si falta o falla, fallback
  automático sin intervención. Sonarr — contención de redimensionado en ARM.
- **MEJORAR (solo con la evidencia citada):** (1) la elección sobrevive a refrescos y rescans
  (Sonarr la pierde: `RefreshSeriesService.cs` reasigna `Images` desde el proveedor); (2) la
  elección es una referencia re-derivable (`file_id`) y no bytes congelados, de modo que sigue a
  la miniatura del número cuando el CBZ se reemplaza (Komga persiste bytes/url en
  `ThumbnailSeries`, sin re-derivación desde el libro).

## NOT RUN

- Doc oficial de Plex: solo se verificó el artículo «Edit Details» (Change Artwork); no se
  ejecutó ninguna instancia de Plex (propietario; todo «documentado»).
- Sonarr/Kavita/Jellyfin/Mylar3/Komga: leídos en código, NO ejecutados. No se leyó el endpoint de
  la UI de Sonarr que edita `Images` (PUT de series con imágenes); solo el modelo y el servicio
  de descarga. El «no se reemplaza en refrescos» de Jellyfin no se verificó en código.
- Kapowarr y Mylar3: solo grepeado el patrón de portada; no se exploró su UI completa (no se
  infiere ausencia de selección por no encontrarla, pero el modelo de datos —una sola portada
  por volumen— no la contempla).
- Medición en la Pi de la regeneración al elegir: hereda los topes medidos de PORT1; no se midió
  el panel.

## Caduca (~60 días)

2027-01-09 (o antes si cambia la historia, la decisión del PO o alguna referencia citada).

## Licencias (barrera legal)

Komga MIT (verificado en su `LICENSE`); Sonarr GPL-3.0; Kavita GPL-3.0; Kapowarr GPL-3.0; Mylar3
GPL-3.0; Jellyfin GPL-2.0; ComicTagger Apache-2.0; Plex propietario (solo documentación funcional).
Solo se extraen patrones; cero código copiado.
