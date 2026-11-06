# SPEC: «Portadas nítidas a partir de lo que ya tengo» (BL-PORT1, issue #300) — v0.3

> **Estado:** v0.3 (2026-11-05). **Q-1 y Q-2 resueltas por el PO (2026-11-04)**; **AC-02 PASS** (medida de
> presentación, §9.2); **AC-12 medido en la Pi (2026-11-05)**: PASS en tiempo y FAIL en los dos umbrales
> propuestos, **ratificados por el PO** con valores nuevos (Q-4). Sin bloqueos de producto: quedan **Q-3** (no
> bloquea), la medida de página de la Pi (NOT RUN, §9.3) y AC-21 (navegador).
> **Evidencia de AC-12:** `docs/design/medicion-BL-PORT1-2026-11-05.md` (banco `e0d6ea5`, 29 de 30 archivos).
> **Base contrastada:** `main` = `35283b5` (2026-11-04). El issue #300 se redactó
> sobre `11aac45`; en los ficheros que toca esta historia no hay diferencia de comportamiento (la ficha lo
> contrasta con `git diff` vacío, §0).
> **Semilla:** `docs/design/benchmark-BL-PORT1.md` (SCOUT.bench, 2026-11-04; veredicto **CONSTRUIR SOBRE LO
> PROPIO**; umbral 240/600/320; caché `covers/v2/<id>.jpg` con regeneración perezosa; sin `srcset`). La ficha
> caduca el **2027-01-03**: si se implementa después, se revalida antes (o se cita el `git diff` de los ficheros).
> **Notación:** EARS con palabras clave en español (CUANDO, MIENTRAS, SI/ENTONCES, DONDE); criterios de
> aceptación Given/When/Then; identificadores en inglés. Los textos de cara a la persona, en español llano
> (CLAUDE.md §6). Esta historia **no añade texto visible**: congela los estados actuales.

---

## 0. Resumen ejecutivo

**Qué cambia.** La portada de una serie se genera y se guarda a un ancho explícito por uso: **600 px** para
Biblioteca/Inicio/ficha, **240 px** para «Por revisar» y **320 px** para Descubrir. La caché de serie pasa a
`covers/v2/<id>.jpg` y se regenera **sola y perezosamente** al pedir la portada, conservando la caché antigua
como respaldo. No se amplía ningún original pequeño. No se añade red.

**Qué no cambia.** La ruta `/ui/series/{id}/portada`, la cascada de 3 niveles, `cached_image_response`
(`ETag` por `mtime`, `private, max-age=86400`, 304), «Por revisar» (240, sin caché en disco, `ETag` del fichero
origen) y Descubrir (320, caché aparte). Sin `srcset`. Sin ajustes nuevos. Sin migración.

**Cómo se demuestra.** 24 criterios Given/When/Then (§8). **AC-02 PASS** (medida del 2026-11-04, §9.2) y
**AC-12 medido en la Pi el 2026-11-05**: p95 a 600 = 156,2 ms (**PASS**, 2,6× de margen), bytes 93,7 KB y ΔRSS
65,5 MB (**FAIL de los umbrales propuestos, ratificados por el PO** con 100 KB y 80 MB → **PASS** con los
nuevos). Quedan por evidencia AC-15 (informe real, PR-3), AC-21 (navegador) y la medida de página de la Pi
(NOT RUN, §9.3). Todo lo demás es pytest. Los números salen de la ficha (§5.3, §10.0–§10.3), de la medida de
presentación (§9.2) y de la medición de AC-12; no se inventa ninguno.

**Decisiones del PO (2026-11-04).** **Q-1 aceptada**: una serie sin CBZ extraíble y solo con caché antigua se
queda a 320/240, sin red y sin borrar, y se cuenta en el informe. **Q-2 = 600 px**: 480 descartado (1,66× en el
peor caso medido, 290 CSS). AC-02 PASS con la tabla de §9.2.

**Decisión del PO (2026-11-05, Q-4).** Con la medida de la Pi delante, se **mantiene 600** y se ratifican los
umbrales: media ≤ **100 KB/portada** (≈100 MB/1000 series) y ΔRSS ≤ **80 MB**. Detalle, cifras y NOT RUN en
`docs/design/medicion-BL-PORT1-2026-11-05.md`.

**Entrega por PRs.** Tres cortes de dominio (§10): **PR-1** comportamiento de la historia; **PR-2** seguridad
de la escritura de caché (MEJORAR 1 y 2 de la ficha); **PR-3** informe del criterio 6 (MEJORAR 3). Orden
recomendado: **PR-2 → PR-1 → PR-3**, con la medida de la Pi como puerta de fusión de PR-1.

---

## 1. Problema y resultado deseado

### 1.1 Hecho verificado en `main` `35283b5`

| Hecho | Evidencia (fichero:línea) |
|---|---|
| La extracción de un CBZ se limita a 240 px de ancho | `utils/cover.py:40` (`_THUMB_MAX_WIDTH = 240`), `:117` (`img.thumbnail((240, 480))`) |
| La descarga externa se limita a 320 px | `utils/cover.py:61` (`_COVER_MAX_WIDTH = 320`), `:179` |
| La portada de una serie extraída de CBZ usa 240, no 320 | `web/series.py:246` llama sin ancho; el 320 solo lo usa la externa |
| La misma imagen se sirve en rejilla de Biblioteca, Inicio y ficha | `_rejilla_biblioteca.html:11`, `dashboard.html:150`, `series_detail.html:8` → mismo `/ui/series/{id}/portada`; macro `ui.portada` con un único `<img>` (`_componentes.html:29-31`) |
| La caché `covers/<id>.jpg` se escribe una vez y nunca se regenera | `web/series.py:227-231` |
| La caché no lleva versión ni ancho en la clave | `web/series.py:227` |
| `ETag` = `mtime` del fichero de caché; `Cache-Control: private, max-age=86400`; 304 con `If-None-Match` | `web/series.py:266-267`; `utils/cover.py:127-140` |
| «Por revisar» extrae a 240, sin caché en disco, con `ETag` del fichero origen | `web/pendientes.py:394-402` |
| Descubrir tiene caché aparte a 320 | `web/discovery.py:139-158` |
| CBR real no tiene extractor | `utils/cover.py:42-46` (`EXTENSIONES_CON_PORTADA = {".cbz", ".zip"}`) |
| La escritura de caché no es atómica | `utils/cover.py:185-192` (`dest.write_bytes`), `:177-182` (`img.save(dest)`) |
| Un fallo de espacio al escribir produce 500, no la portada | `web/series.py:250-255`: tras capturar `EspacioInsuficienteError` se llama a `_etag_for(cache_path)`, que hace `stat()` sobre un fichero inexistente |
| El contenedor de la portada reserva 2:3 aunque la imagen no haya cargado | `static/web.css:1533` (`.portada { aspect-ratio: 2 / 3 }`), `:1557-1560` (la `<img>` es absoluta y tapa el marcador) |

Los anchos de presentación **medidos** (Chrome 156 headless, DPR 1 y 2, `main` `35283b5`; detalle y tabla en
§9.2) son: «Por revisar» 120 CSS; Biblioteca 162,5–290 (290 en el peor caso, viewport 320; **327** en el borde
de una columna a viewport 357); Inicio 106–188,8; ficha 140 CSS a partir de 769 y **120 a ≤768** (`@media
(max-width: 768px)`, `web.css:1113`); Descubrir 80. No hay desbordamiento horizontal y el DPR no cambia la
geometría CSS. Frente a la estimación de la ficha §1 (líneas 80-86) —296/333 y 171,5— la desviación >10 % aparece
solo en el Inicio (+10,1 % en el caso de 900), no en Biblioteca (−2,0 %/−1,8 %); no cambia la decisión. **AC-02
PASS** (§9.2).

### 1.2 Resultado deseado, medible

| Objetivo | Métrica | Umbral |
|---|---|---|
| O-1 Nitidez de la portada de serie | ancho del JPEG en `covers/v2/<id>.jpg` para un original mayor | 600 px ±1, altura proporcional |
| O-2 No mentir con originales pequeños | ancho del JPEG cacheado / servido | nunca mayor que el original |
| O-3 Caché autorreparable | peticiones para regenerar una portada antigua | 1 (la primera), sin intervención de la persona |
| O-4 Caché sin regresión | `ETag`, `Cache-Control`, 304 | idénticos a hoy en formato y semántica |
| O-5 Coste en Pi | p95 de extracción en frío a 600 en la Pi | ≤ 400 ms (≤ 600 ms si el original supera 12 Mpx) — **medido 156,2 ms (PASS)** el 2026-11-05; umbral ratificado (Q-4) |
| O-6 Abrir Biblioteca | extracciones/escrituras durante el render HTML | 0 |
| O-7 Sin red | peticiones externas nuevas | 0 |
| O-8 Lo que queda | series por debajo del objetivo por causa, contadas | informe de una pasada (§9.5) |

---

## 2. Alcance

### 2.1 En alcance

1. Ancho de generación por uso (240 / 600 / 320) y su verificación con la medida de presentación.
2. Clave de caché versionada `covers/v2/<id>.jpg` + regeneración perezosa con respaldo a la caché antigua.
3. Integridad de la escritura de la caché: atómica y sin 500 por disco lleno o permiso denegado (MEJORAR 1 y 2).
4. Medición en la Pi del coste (criterio 4) y del navegador real (criterio 7).
5. Informe de una pasada de lo que queda por debajo del umbral y por qué (criterio 6, MEJORAR 3).

### 2.2 Fuera de alcance (no-goals explícitos)

| No-goal | Por qué |
|---|---|
| **BL-PORT2**: descargar portadas de fuera, sustituir una portada por otra, refresco manual de una portada | Es otra historia; su DoR depende del informe del criterio 6 (ficha §12, líneas 637-640) |
| Extraer portadas de **CBR real** (o PDF/EPUB/7z) | No hay extractor; añadir dependencia es otra decisión (`EXTENSIONES_CON_PORTADA`, ficha §12) |
| Mejora por **IA** (upscale, restauración) | Ni ligero ni verificable en la Pi; fuera del issue |
| Cambiar la **edición catalogada**, la selección de la primera página del CBZ o el diseño de la ficha | No es nitidez; la primera página «fea» sigue siéndolo (riesgo R-06) |
| `srcset` / `sizes` | Descartado con evidencia en ficha §5.4 (líneas 423-445): un solo fichero de 600 cubre el 2× medido |
| Regeneración en lote, tarea con progreso, cola, semáforo «por si acaso» | Coste y riesgo en Pi; ADR-0011; el semáforo de MEJORAR 4 solo entra **si la medida lo pide** (Q-4) |
| Ajuste de tamaño visible en Ajustes | Decisión del PO, no del coleccionista (ficha §5.3, líneas 349-361) |
| Borrar la caché antigua `covers/<id>.jpg` desde la app | Invariante «no borrar»; la purga el desinstalador (`scripts/uninstall.sh:361`, `covers/`) |
| Cambiar `COVERS_CACHE_PATH`, variables de entorno, esquema o migraciones | Sin modelo nuevo (NFR-08) |
| Mostrar al coleccionista cualquier texto nuevo (tamaños, caché, versión) | El estado visible no cambia (§6) |

---

## 3. User stories

### US-1 — ver la colección, no miniaturas

**Como** coleccionista, **quiero** que las portadas de mi Biblioteca y de la ficha se vean nítidas en mi
pantalla cuando el tebeo que tengo en disco tiene buena calidad, **para** reconocer mi colección de un vistazo
y abrir el tebeo correcto sin tener que fijarme en una miniatura borrosa.

**Valor real:** identificar y elegir; no es estética. Hoy la misma imagen de 240 px se estira a tarjetas de
hasta **290 CSS medidas** (580 px de dispositivo a 2×; la estimación del CSS decía 296), así que la persona ve
una imagen ampliada y blanda. **Coste de no
hacerlo:** la rejilla deja de servir para reconocer; se abre la ficha para confirmar.

**No incluye:** salir a internet a buscar mejores portadas (US de BL-PORT2).

### US-2 — que se arregle solo, sin tocar nada

**Como** coleccionista que no abre terminales, **quiero** que las portadas que ya estaban guardadas se
arreglen solas la próxima vez que las mire, **para** no tener que borrar cachés, vaciar carpetas ni entender
por qué una portada antigua se queda pequeña.

**Valor real:** cero mantenimiento y cero pérdida: no se borra nada de lo que ya hay. **Coste de no hacerlo:**
subir el tamaño solo arreglaría las portadas nuevas; la colección ya cacheada seguiría igual y haría falta una
instrucción manual (lo que Komga resuelve con un diálogo y una tarea de lote, ficha §3.1).

### US-3 — decidir con datos si hace falta descargar portadas (operativa, no del coleccionista)

**Como** responsable de esta instalación en la Pi, **quiero** un recuento de cuántas portadas se quedan por
debajo del objetivo **y por qué** (original pequeño, sin extractor, sin fuente), **para** decidir si BL-PORT2
merece la pena sin adivinar, sabiendo que la cifra no se infla con portadas que simplemente aún no se han
visitado.

**Valor real:** una decisión de producto con una cifra honesta, no una impresión. **Coste de no hacerlo:**
BL-PORT2 se refinaría a ciegas y la tensión del criterio 1 vs 5 quedaría sin cuantificar (Q-1).

---

## 4. Requisitos funcionales (EARS)

> `Estado` = lo que hay en `main` `35283b5`: `cumplido` (existe y esta spec lo congela), `parcial` o `pendiente`.
> Un FR `cumplido` entra igual: su AC es **regresión**, no implementación.
> La columna **Fuente** cita la ficha de benchmark cuando fija un número; sin fuente, no se fija.

| ID | Patrón | Requisito | Fuente | Estado | AC |
|---|---|---|---|---|---|
| FR-01 | Ubicuo | El sistema generará la portada de una serie (Biblioteca, Inicio y ficha) con un **ancho máximo de 600 px** (alto proporcional), la miniatura de «Por revisar» a **240 px** y la de Descubrir/asistente a **320 px**. | Issue crit. 1; ficha §5.3 tabla (líneas 364-370) | pendiente | AC-01, AC-02, AC-03, AC-04 |
| FR-02 | Ubicuo | El sistema **nunca ampliará** una imagen: si el original es menor que el objetivo, se sirve y se cachea a su tamaño. | Issue crit. 2; ficha líneas 378-379 | pendiente | AC-05, AC-06 |
| FR-03 | Ubicuo | El sistema guardará la portada de serie en `covers/v2/<series_id>.jpg`; la versión viajará **en la ruta** y un cambio de ancho objetivo o de algoritmo exigirá subir a `v3`. | Ficha líneas 381-383 | pendiente | AC-07, AC-09 |
| FR-04 | Estado | MIENTRAS exista `covers/v2/<id>.jpg`, el sistema la servirá sin extraer, sin descargar y sin escribir. | Ficha líneas 385-386 | pendiente | AC-09 |
| FR-05 | Por evento | CUANDO se pida una portada de serie sin `v2` y haya un `File` no ausente extractable, el sistema extraerá su primera página a 600, escribirá `v2` y servirá 200. | Ficha líneas 385-391 | pendiente | AC-01, AC-07 |
| FR-06 | Estado | SI no hay CBZ extraíble (CBR real, `File` ausente, extracción fallida) y existe `covers/<id>.jpg` legado, ENTONCES el sistema servirá esa caché **sin red** y sin copiarla a `v2`. | Issue crit. 5; ficha líneas 390-397 | pendiente | AC-13, AC-18 |
| FR-07 | Por evento | CUANDO no exista ninguna caché y haya `cover_url` utilizable, el sistema la descargará una vez, la redimensionará a 600 como máximo y escribirá `v2`; si no hay nada, responderá 404. | Ficha líneas 391-392 | pendiente | AC-06, AC-14, AC-19 |
| FR-08 | No deseado | SI el candidato tiene `is_missing = true`, ENTONCES no se usará; se toma el primer `File` no ausente por `sort_order` (un único candidato, como hoy). | B7; ficha líneas 620-622 | cumplido | AC-17, AC-19 |
| FR-09 | Ubicuo | El sistema **no borrará** `covers/<id>.jpg` ni `covers/v2/<id>.jpg` desde la aplicación; la caché antigua queda como respaldo. | Ficha líneas 398-399 | pendiente | AC-07 |
| FR-10 | Ubicuo | El sistema conservará el contrato de respuesta: `ETag` = `mtime` del fichero servido, `Cache-Control: private, max-age=86400` y 304 con `If-None-Match` que coincida. | Issue crit. 3; ficha líneas 400-402 | cumplido | AC-07, AC-08 |
| FR-11 | No deseado | SI la escritura de la caché falla (espacio insuficiente, permiso denegado u otro `OSError`), ENTONCES el sistema servirá 200 con los bytes ya extraídos y un `ETag` calculado de esos bytes, registrará un aviso y **no** devolverá 500. (Camino de extracción; la descarga externa sin caché previa mantiene hoy su 404, R-13.) | Issue DoD; ficha líneas 470-481 | pendiente | AC-22 |
| FR-12 | Ubicuo | El sistema escribirá la caché de forma **atómica** (temporal en el mismo directorio + `os.replace`): ninguna petición servirá un JPEG truncado y una interrupción no dejará un fichero parcial que `exists()` dé por bueno. | Ficha líneas 402-403 y MEJORAR 1 (469-475) | pendiente | AC-23, AC-24 |
| FR-13 | Ubicuo | El sistema ofrecerá un **informe de una pasada, solo lectura**, que clasifique cada serie por la causa de estar por debajo del objetivo y dé el recuento; no escribirá en la base, ni en la caché, ni en disco. | Issue crit. 6; ficha §10.3 (586-597) | pendiente | AC-15 |
| FR-14 | Ubicuo | El sistema clasificará con el **mismo predicado que la cascada** (`puede_tener_portada` + lectura de la primera página) y distinguirá: `ya_en_objetivo`, `regenerable_al_pedir`, `extraible_mas_adelante`, `original_pequeno`, `sin_extractor`, `sin_fuente`. | Invariante «no mentir»; ficha §10.3 refinado en §9.5 | pendiente | AC-15, AC-16 |
| FR-15 | No deseado | SI existe `v2` o caché legada, ENTONCES el sistema no consultará `cover_url` ni hará ninguna petición externa; la historia no añade fuentes ni descargas nuevas. | Issue crit. 5; ficha líneas 393-397 | pendiente | AC-13, AC-14 |
| FR-16 | Por evento | CUANDO se abra Biblioteca, Inicio o la ficha, el sistema servirá el HTML sin generar ni escribir ninguna portada: cada imagen se pide aparte y solo se regenera la de su serie. | Issue crit. 4; ficha líneas 282-283 | pendiente | AC-10 |
| FR-17 | Ubicuo | El sistema mantendrá «Por revisar» igual: miniatura de 240 px, sin caché en disco y con `ETag` del `mtime` del fichero origen. | Issue crit. 1; ficha líneas 404-406 | cumplido | AC-03 |
| FR-18 | Ubicuo | El sistema mantendrá Descubrir/asistente igual: caché `covers/descubrir` a 320 px, sin acoplarse al ancho de serie. | Issue crit. 1; ficha líneas 405-406 | cumplido | AC-04 |

### 4.1 Reglas de negocio (BR)

| ID | Regla | Verificación |
|---|---|---|
| BR-01 | Esta historia **no añade texto visible**. Los estados que ya existen se conservan; ningún identificador interno (`covers`, `v2`, `ETag`, token, lote, nombre de fuente) aparece en pantalla. | Prueba sobre el HTML renderizado: el diff de plantillas es vacío salvo, si Q-3 = sí, el parámetro `?v=2` del `src`; ninguna cadena nueva visible |
| BR-02 | Cero configuración nueva: el umbral se fija en código, no se ofrece en Ajustes. | Búsqueda en ajustes/plantillas: no hay control nuevo; `git diff` sin cambios en Ajustes ni en `config.py` |
| BR-03 | Si el original es pequeño, la persona no recibe ningún aviso ni etiqueta: la portada se ve a su tamaño real. La cifra vive en el informe (US-3), no en la UI. | AC-15 + revisión de plantillas (sin condicionales nuevas) |
| BR-04 | La versión de caché no se muestra ni se expone en enlaces que la persona copie como «su portada» (la ruta interna puede cambiarla solo el servidor). | Revisión de plantillas: el `src` sigue siendo `/ui/series/{id}/portada` (con o sin `?v=2`) |

---

## 5. Contratos y datos

### 5.1 `GET /ui/series/{series_id}/portada` (existente; cambia la cascada interna)

| Aspecto | Contrato |
|---|---|
| Petición | GET; `?v=2` opcional como separador de caché del navegador (solo si Q-3 = sí); `If-None-Match` opcional |
| 200 | `image/jpeg` + `ETag` + `Cache-Control: private, max-age=86400` |
| 304 | cuando `If-None-Match` coincide con el `ETag`; sin cuerpo |
| 404 | serie inexistente o ninguna fuente de portada; el `<img>` cae al marcador CSS, sin texto nuevo |
| 500 | **no debe ocurrir** por fallo de escritura de la caché (FR-11, PR-2). Los demás fallos imprevistos quedan como riesgo R-10 |
| Orden de la cascada (nuevo) | 1) `covers/v2/<id>.jpg` si existe → servir. 2) Extracción local del primer `File` no ausente a 600 → escribir `v2`, servir. 3) `covers/<id>.jpg` legado → servir sin red y sin copiar. 4) `cover_url` (solo si no había ninguna caché) a 600 → escribir `v2`, servir. 5) 404 |
| Sin caché de ausencias | igual que hoy: si no hay portada, la siguiente petición vuelve a intentarlo |

### 5.2 Contrato de caché en disco

| Clave | Ruta | Contenido | Quién escribe |
|---|---|---|---|
| Serie, v2 (nueva) | `covers/v2/<series_id>.jpg` | JPEG a ancho ≤ 600, alto proporcional | `write_cover_cache` (extracción) y `fetch_and_cache_cover` (externa) |
| Serie, legado | `covers/<id>.jpg` | lo que hubiera (240 o 320) | no se escribe más; solo se lee como respaldo |
| Descubrir | `covers/descubrir/<hash>.jpg` | JPEG a ancho ≤ 320 | sin cambios |
| «Por revisar» | — (sin caché) | bytes en respuesta | sin cambios |

**Invariantes:** (a) la versión viaja en la ruta y un cambio de ancho o algoritmo exige `v3`; (b) la escritura
es atómica (PR-2) y crea el directorio si falta; (c) no se borra ninguna de las dos claves; (d) `covers/` entero
lo purga el desinstalador (`scripts/uninstall.sh:361`), luego `v2` no deja restos.

### 5.3 Constantes (nombres orientativos; los fija quien implemente)

| Constante | Valor | Uso |
|---|---|---|
| `_THUMB_MAX_WIDTH` | 240 | «Por revisar» (sin cambios; ficha línea 368) |
| `_COVER_MAX_WIDTH` | 320 | por defecto de `fetch_and_cache_cover`; Descubrir (ficha línea 370) |
| `_SERIES_COVER_MAX_WIDTH` | 600 | portada de serie (ficha líneas 366-370) |
| `CACHE_VERSION` (o `VERSION_PORTADA`) | `"v2"` | nombre del subdirectorio (ficha línea 383) |

### 5.4 Datos que se leen (sin cambios de modelo)

`Series.id`, `Series.cover_url`; `File.file_path`, `File.is_missing`, `File.metadata_["formato_contenido"]`
(#307); `Issue.sort_order`. Nada nuevo en base de datos: **sin migración** (NFR-08).

### 5.5 Decisiones de diseño ya tomadas por la ficha (no se reabren en esta spec)

1. Un **solo** fichero de 600 sirve rejilla, Inicio y ficha; sin `srcset` (ficha §5.4).
2. Regeneración **perezosa al pedir**, no en lote ni con tarea (ficha §5.3, §3.1-§3.2).
3. **Legado antes que red**: una serie sin extractor y con caché antigua se sirve a 320/240 hasta BL-PORT2
   (ficha líneas 393-397). La tensión con el criterio 1 se eleva al PO en Q-1.
   **Actualizado por BL-PORT5 (#435, 2026-11-06):** el archivo local ya no gana siempre a la antigua. Una
   portada previa con ancho **≥ 300 px** (hoy, la caché antigua `covers/<id>.jpg`) se sirve **antes** que `v2` y
   que los archivos, y una `v2` ya escrita de esa serie se ignora sin borrarla. Con una antigua menor (los 100×100
   de Tebeosfera) o sin ella, la cascada de esta especificación no cambia. Ver `especificacion-BL-PORT5.md`.
4. El **ancho es global para el uso «portada de serie»**, no configurable por la persona (ficha §4.2).
5. Un único candidato `File` por petición (`limit(1)`), como hoy: no se busca «el siguiente extractable».

---

## 6. Estados: qué ve la persona

Esta historia **no introduce estado visible nuevo**. La tabla fija lo que ya hay para que no se rompa.

| Situación | Respuesta del servidor | Qué ve la persona | Cómo se comprueba |
|---|---|---|---|
| **Vacío** — no hay fuente ni caché | 404 | El **marcador de tinta** con la inicial (color y trama de imprenta), sin icono de imagen rota, sin texto de error, con el mismo alto 2:3 que una portada | Navegador (AC-21) + HTML: `<img>` colapsa y el marcador queda visible (`web.css:1527-1560`) |
| **Carga** — primera petición que extrae/regenera | 200 tras el trabajo | La tarjeta ya ocupa su alto (contenedor `aspect-ratio: 2/3`); la imagen aparece encima al cargar; **no hay salto de maquetación** ni cambio de alto de la tarjeta | Navegador: `getBoundingClientRect()` de la tarjeta antes y después de cargar; diferencia 0 px (AC-21) |
| **Caliente** — `v2` ya escrita | 200 o 304 | La misma imagen, sin parpadeo ni recarga perceptible | pytest: segundo GET con `If-None-Match` → 304 (AC-07/08) |
| **Error 404** — sin CBZ extraíble ni caché ni `cover_url` | 404 | Marcador, igual que «Vacío»; no se distingue ni se explica | pytest + navegador (AC-18, AC-21) |
| **Error de red** — `cover_url` caída, URL no permitida, timeout | 404 | Marcador, igual que «Vacío»; sin mensaje nuevo | pytest con doble que falla (AC-14) |
| **Fallo de disco al escribir caché tras extraer un CBZ** — disco lleno o permiso denegado | **200 con la imagen** (FR-11, PR-2), aviso en el log | La persona ve su portada; no hay error ni marcador; no se le pide liberar espacio para ver una portada | pytest con `comprobar_espacio`/escritura simuladas (AC-22) |
| **Fallo de disco al escribir una descarga externa** — sin caché previa | 404 (sin cambios: `fetch_and_cache_cover` devuelve `False`) | Marcador, igual que «Vacío»; no se le pide nada | Sin cambio en esta historia; anotado en R-13 |
| **Fallo al leer una caché corrupta o sin permisos** | hoy 500 (sin cambios) | El navegador pinta el marcador igual que en 404; no hay texto nuevo | **No es requisito de esta historia**; riesgo R-10. No se promete arreglarlo |

**Nada de esto se anuncia en pantalla**: no hay «cargando…», ni «portada no disponible», ni botón de
«regenerar». La persona solo ve portada o marcador (BR-01, BR-03).

---

## 7. Requisitos no funcionales

> Los umbrales de NFR-02, NFR-03 y NFR-04 siguen siendo **propuestas** de la ficha §10.1 (líneas 556-573); el
> banco por portada del 2026-11-05 mide ya NFR-02 (p95) y da la evidencia de NFR-05/NFR-06 (RSS y bytes).
> **Q-4 quedó ratificada por el PO el 2026-11-05** con el dato delante: NFR-05 y NFR-06 llevan los valores
> nuevos; NFR-03/NFR-04 siguen **NOT RUN** (§9.3), no se sustituyen por un PASS supuesto.

| ID | NFR | Umbral | Método de verificación |
|---|---|---|---|
| NFR-01 | Nada bloqueante en el *event loop*: zipfile, Pillow, disco y lectura de caché fuera del bucle | 100 % de esas llamadas en `asyncio.to_thread` | pytest: el extractor simulado comprueba que se ejecuta en un hilo distinto del principal (AC-11) + revisión de código |
| NFR-02 | Coste de extracción en frío en la Pi | p95 ≤ 400 ms a 600 px (≤ 600 ms si el original supera 12 Mpx) — **medido 156,2 ms el 2026-11-05 (PASS, 2,6× de margen)** | Banco de 29 CBZ reales, 5 repeticiones, mediana y p95 (ficha §10.1); detalle en `docs/design/medicion-BL-PORT1-2026-11-05.md` |
| NFR-03 | Coste de una rejilla en frío | 30 portadas en frío con 6 peticiones concurrentes ≤ 6 s | Mismo banco, `curl -w '%{time_total}'` (ficha §10.2) — **NOT RUN** |
| NFR-04 | Lectura caliente | 304 ≤ 30 ms | Banco caliente (ficha §10.1) — **NOT RUN** |
| NFR-05 | Memoria | delta de RSS del proceso ≤ **80 MB** (ratificado por el PO el 2026-11-05; antes 40 MB) | Medido en el banco: **Δ 65,5 MB** (pico 79,1 → 144,6 MB, dentro de 512 MB); `docker stats`/cgroup siguen **NOT RUN** (ficha §10.2) |
| NFR-06 | Tamaño de caché | media ≤ **100 KB/portada**; extrapolación ≤ **100 MB/1000 series** (ratificado el 2026-11-05; antes 60 KB/60 MB) | Medido en el banco: **93,7 KB/portada** a 600 (20,9 KB a 240); `du` real y extrapolación con la media medida siguen **NOT RUN** (ficha §10.2) |
| NFR-07 | Latencia de abrir Biblioteca | 0 extracciones/escrituras en el render; latencia del HTML sin empeorar más del 10 % respecto a la línea base del mismo entorno (n=30) | pytest (AC-10) + medida `curl` antes/después |
| NFR-08 | Sin dependencias nuevas, sin esquema, sin configuración | solo stdlib + Pillow ya presente; `git diff --stat alembic/ pyproject.toml config.py` vacío | Revisión de la PR |
| NFR-09 | Sin red nueva | 0 peticiones externas añadidas; solo la cascada actual | Dobles de los clientes que fallan si se invocan (AC-14) |
| NFR-10 | Concurrencia | dos peticiones simultáneas de la misma serie no corrompen ni sirven truncado; duplicar CPU es aceptable (sin lock si la medida no lo pide) | pytest con dos peticiones concurrentes y escritura atómica (PR-2, AC-24) |
| NFR-11 | Accesibilidad y presupuesto de texto | `alt=""` + título de la tarjeta como nombre accesible; marcador `aria-hidden`; 0 controles nuevos; 0 texto visible nuevo | Pruebas existentes de componentes/contraste + `git diff` de plantillas (BR-01) |
| NFR-12 | Presupuesto de la Pi | dentro del contenedor de 512 MB; sin proceso, hilo persistente ni job nuevos | `docker-compose.yml` (512M) + revisión: todo ocurre en el request, en un `to_thread` acotado |

---

## 8. Criterios de aceptación (Given/When/Then)

> Uno por comportamiento. Cada AC indica su verificación: `pytest` (automática), `medida` (registro numérico en
> un documento) o `navegador` (observación manual con pasos). Sin verificación, el AC no existe.

### Criterio 1 del issue — tamaño según dónde se muestra

**AC-01 (FR-01, FR-05) — se genera a 600**
Given un CBZ sintético de 1600×2400 px y una serie sin ninguna caché,
When se pide `GET /ui/series/{id}/portada`,
Then la respuesta es 200 `image/jpeg`, existe `covers/v2/<id>.jpg` y su ancho es **600 ±1 px** (alto 900 ±1).
*Verificación: pytest.*

**AC-02 (FR-01) — el umbral se confirma con la pantalla real antes de implementar — PASS (2026-11-04)**
Given las plantillas de `main` `35283b5` y el `web.css` del repo, medidos en Chrome 156 headless a 320, 375, 390,
768, 900, 1024, 1240, 1440 y 1920 px CSS (DPR 1 y 2),
When se mide `getBoundingClientRect().width` de `.library-card .portada`, `.series-card .portada` y
`.portada.series-cover` (tabla completa en §9.2),
Then: el peor caso presentado es **290 CSS** (Biblioteca a 320) → **600 = 2,07×**; el borde de una columna
(357 → 327 CSS) queda a **1,84×**; ningún uso normal supera 300 CSS; `480` queda descartado (1,66× y 1,47×); no
hay desbordamiento horizontal y el DPR no cambia la geometría CSS.
*Verificación: medida registrada en §9.2 (Chrome 156 headless, 2026-11-04). Firefox y Safari: NOT RUN; la
geometría depende de `auto-fill`/`minmax` del CSS y el margen medido (2,07×) lo absorbe.*

**AC-03 (FR-17) — «Por revisar» intacto**
Given un archivo con CBZ y su ficha de pendiente,
When se pide `GET /ui/pendientes/{file_id}/portada`,
Then el JPEG mide **240 px o menos** de ancho, no se escribe nada en `covers/` y el `ETag` sigue siendo el
`mtime` del fichero origen (no el de la caché).
*Verificación: pytest (regresión).*

**AC-04 (FR-18) — Descubrir intacto**
Given un candidato de Descubrir con `cover_url`,
When se pide `GET /ui/descubrir/portada`,
Then el JPEG guardado en `covers/descubrir/<hash>.jpg` mide **320 px o menos** de ancho y no se crea nada en
`covers/v2/`.
*Verificación: pytest (regresión).*

### Criterio 2 del issue — sin ampliar lo que no existe

**AC-05 (FR-02) — original pequeño, CBZ**
Given un CBZ sintético de 400×600 px,
When se pide la portada de su serie,
Then el JPEG servido y cacheado mide **400 px** de ancho (no 600), sin ampliación.
*Verificación: pytest.*

**AC-06 (FR-02, FR-07) — original pequeño, externa**
Given un `cover_url` que devuelve una imagen de 250×375 px,
When se genera su portada de serie,
Then el JPEG cacheado en `v2` mide **250 px** de ancho (no 600 ni 320 ampliados).
*Verificación: pytest con red simulada.*

### Criterio 3 del issue — la caché se rehace sola, sin perder ETag ni Cache-Control

**AC-07 (FR-03, FR-04, FR-05, FR-09, FR-10) — regeneración perezosa con respaldo**
Given una caché antigua `covers/<id>.jpg` de 240 px, un CBZ extraíble de 1600×2400 y ninguna `v2`,
When se pide la portada,
Then: (a) la primera petición devuelve 200 con una imagen de 600 px y escribe `covers/v2/<id>.jpg`; (b) la
caché antigua **sigue en disco**; (c) una segunda petición con el `If-None-Match` del `ETag` devuelto responde
**304**.
*Verificación: pytest.*

**AC-08 (FR-10) — cabeceras exactas**
Given una portada servida (v2 o legado),
When se inspecciona la respuesta,
Then `ETag` es el `mtime` del fichero servido con comillas, `Cache-Control` es exactamente
`private, max-age=86400`, y un 304 con `If-None-Match` coincidente no lleva cuerpo.
*Verificación: pytest (regresión de `test_cover_cache.py::TestCachedImageResponse`).*

**AC-09 (FR-03, FR-04) — clave versionada y cero trabajo si ya está**
Given `covers/v2/<id>.jpg` ya escrita y el extractor y la descarga instrumentados,
When se pide la portada,
Then se sirve `v2` sin llamar a `extract_cover_thumbnail` ni a `fetch_and_cache_cover`, y la ruta usada es la
versionada (no `covers/<id>.jpg`).
*Verificación: pytest con contadores.*

### Criterio 4 del issue — ligero en la Pi

**AC-10 (FR-16) — abrir Biblioteca no genera nada**
Given 200 series en la línea base y el extractor y la escritura instrumentados,
When se pide `GET /ui/biblioteca` (el HTML, sin pedir las imágenes),
Then la respuesta es 200, `extract_cover_thumbnail` se ha llamado **0 veces**, `write_cover_cache` **0 veces** y
el directorio de caché sigue como estaba; pedir después **una** portada hace como mucho **una** extracción de
**esa** serie.
*Verificación: pytest.*

**AC-11 (NFR-01) — nada bloqueante en el bucle**
Given el endpoint de portada con un extractor simulado que anota el hilo en que corre,
When se sirve una portada con extracción,
Then la extracción ocurrió en un hilo distinto del principal (`threading.current_thread()`), y una petición
ligera concurrente (p. ej. `/api/health`) no espera a que termine.
*Verificación: pytest.*

**AC-12 (NFR-02 a NFR-06) — medida en la Pi, separada del entorno de desarrollo — PASS en tiempo; FAIL en los dos umbrales propuestos (ratificados por el PO)**
Given la rama `feat/300-portadas-v2` @ `e0d6ea5` montada en la Pi del PO, en un contenedor de un solo uso, con
una muestra determinista de 30 CBZ/ZIP reales (29 medidos, 1 ilegible) y 5 repeticiones por archivo y ancho,
When se ejecuta el banco `scripts/medicion/banco_portadas.py` (ficha §10.1/§10.2),
Then: **p95 a 600 = 156,2 ms ≤ 400 ms → PASS** (2,6× de margen; ningún original se amplió); **bytes medios a
600 = 93,7 KB → FAIL del propuesto de 60 KB**; **ΔRSS = 65,5 MB → FAIL del propuesto de 40 MB**. Con la
ratificación de Q-4 por el PO (2026-11-05: 100 KB y 80 MB), ambos pasan a **PASS con los umbrales nuevos**.
Quedan **NOT RUN** la medida de página (30 frías/6 concurrentes ≤ 6 s), el 304 caliente ≤ 30 ms, `docker
stats`/cgroup y el `du` real de la caché; no se cierran por omisión.
*Verificación: `docs/design/medicion-BL-PORT1-2026-11-05.md` (tabla, veredicto por umbral y NOT RUN).*

### Criterio 5 del issue — sin red

**AC-13 (FR-06, FR-15) — legado sin red**
Given una serie sin `File` utilizable, con `cover_url` presente y `covers/<id>.jpg` antigua,
When se pide la portada,
Then responde 200 con la caché antigua y `fetch_and_cache_cover` **no se llama**; no se copia a `v2`.
*Verificación: pytest (doble que falla si se invoca).*

**AC-14 (FR-07, FR-15) — la única red es la de hoy**
Given los dobles de todos los clientes externos que fallan si se invocan,
When se recorren los caminos con `v2` (AC-09), con legado (AC-13) y con extracción local (AC-05),
Then **0** peticiones externas; solo el camino «sin ninguna caché y con `cover_url`» hace una descarga (y una
sola).
*Verificación: pytest.*

### Criterio 6 del issue — medición de lo que queda

**AC-15 (FR-13) — informe de una pasada, sin efectos**
Given la base y la biblioteca reales,
When se ejecuta el informe,
Then produce una tabla/CSV por serie y un recuento por causa, **no** escribe en la base ni en la caché ni en
disco (el directorio de caché y el `mtime` de la base no cambian) y cubre las seis clases de FR-14.
*Verificación: pytest del clasificador con casos fabricados + ejecución real registrada (PR-3).*

**AC-16 (FR-14) — la clasificación no miente**
Given casos fabricados: original 1600×2400 con caché 240 (regenerable), original 400×600 (original pequeño),
`.cbr` real sin extractor, serie sin `File` ni `cover_url` (sin fuente), serie con `v2` de 600 (ya en objetivo)
y serie cuyo primer `File` no es extractable pero un `File` posterior sí (`extraible_mas_adelante`),
When se clasifican,
Then cada uno cae en su clase correcta, `regenerable_al_pedir` **no** se cuenta como «queda por debajo» y
`extraible_mas_adelante` se cuenta aparte (no como «original pequeño»).
*Verificación: pytest.*

### Criterio 7 del issue — pruebas pedidas

**AC-17 (FR-08) — archivo ausente (`is_missing`)**
Given una serie cuyo único `File` tiene `is_missing = true` y `cover_url` presente,
When se pide la portada,
Then no se intenta extraer de él; se usa `cover_url`; sin `cover_url`, 404. Regresión de B7.
*Verificación: pytest (regresión; `tests/test_web_series.py::TestPortada`).*

**AC-18 (FR-06) — CBR sin extractor**
Given una serie con un `.cbr` real, ninguna caché y **sin** `cover_url`,
When se pide la portada,
Then `extract_cover_thumbnail` devuelve `None`, la respuesta es 404 y **no se hace ninguna petición de red**.
(Con `cover_url` presente y sin caché se aplica la cascada de hoy: una descarga a 600 y se cachea en `v2`;
eso es AC-14, no una consulta nueva.)
*Verificación: pytest.*

**AC-19 (FR-07, FR-08) — archivo ausente y sin fuente**
Given una serie sin `File` (o con todos ausentes) y sin `cover_url`,
When se pide la portada,
Then 404 y el HTML de la ficha sigue pintando `ui.portada` con su marcador.
*Verificación: pytest (regresión).*

**AC-20 — la suite entera sigue verde y sin deps**
Given la rama con los tests nuevos,
When se ejecuta la suite completa,
Then `pytest` pasa, no hay dependencia nueva, ni migración, ni cambio en `config.py`.
*Verificación: pytest + `git diff --stat alembic/ pyproject.toml config.py`.*

**AC-21 — navegador real (escritorio y móvil)**
Given Chrome y Firefox en escritorio (1240 y 1920 CSS) y móvil (375 y 320 CSS), con DPR 1 y 2,
When se abre Biblioteca, Inicio, la ficha y «Por revisar», con la caché vacía y después caliente,
Then: la tarjeta mide el ancho anotado en §9.2 y la imagen servida mide 600 px (2,07× en el peor caso de la
tabla; 1,84× en el borde de una columna a 357); al comparar con la portada anterior de 240 px, la nueva se ve
nítida y la vieja no; no hay salto de maquetación al cargar (el alto de la tarjeta no cambia); el 404 (forzando
una serie sin fuente) pinta el marcador sin icono de imagen rota; y «Por revisar» se ve igual que antes.
*Verificación: navegador (pasos y capturas anotadas, con los anchos de §9.2; NO RUN en CI).*

### Seguridad de la escritura (PR-2; cierra el borde de los criterios 3 y 4)

**AC-22 (FR-11) — disco lleno o permiso denegado no dan 500**
Given `comprobar_espacio` que lanza `EspacioInsuficienteError` (y, en otro caso, una escritura que lanza
`PermissionError`),
When se pide una portada que hay que extraer y cachear,
Then la respuesta es **200** con los bytes extraídos, `ETag` derivado de los bytes (no de un fichero que no
existe) y un aviso en el log; una segunda petición con ese `ETag` devuelve 304.
*Verificación: pytest.*

**AC-23 (FR-12) — un corte no deja nada truncado**
Given un fallo simulado a mitad de la escritura de la caché,
When termina la operación,
Then no queda un `covers/v2/<id>.jpg` truncado (o no queda ninguno), no se sirve ningún JPEG truncado, el
temporal se limpia y una petición posterior puede escribir la caché buena.
*Verificación: pytest.*

**AC-24 (FR-12, NFR-10) — dos peticiones a la vez no corrompen**
Given dos peticiones concurrentes de la misma serie sin `v2`,
When terminan ambas,
Then el fichero final `covers/v2/<id>.jpg` es un JPEG válido y completo, ninguna respuesta sirve bytes
truncados y no queda ningún temporal. Duplicar la extracción es aceptable (sin lock).
*Verificación: pytest.*

---

## 9. Plan de pruebas y mediciones

### 9.1 Pruebas automáticas (pytest)

| Fichero | Qué fija |
|---|---|
| `tests/test_cover.py` | extracción a 600 por parámetro, 240 por defecto, pequeño sin ampliar, CBR/ausente/corrupto → `None` |
| `tests/test_cover_cache.py` | `fetch_and_cache_cover` a 600 y a 320 por defecto, sin ampliar; escritura atómica y fallos (PR-2); cabeceras sin cambios |
| `tests/test_web_series.py` | cascada nueva: v2, extracción, legado sin red, `cover_url`, 404, `If-None-Match`/304, `is_missing`, ETag de bytes (PR-2) |
| `tests/test_web_library.py` | AC-10: el render no genera portadas |
| `tests/test_web_discovery.py` | AC-04: Descubrir sigue a 320 |
| `tests/test_medicion_portadas.py` (PR-3) | clasificador de AC-15/16 con casos fabricados |

Los CBZ se fabrican con Pillow/zipfile en `tmp_path`, como `test_cover.py`; nada de originales reales ni de red
(ficha §11, líneas 599-633). La caché se redirige con `get_settings().model_copy(update={"covers_cache_path":
tmp_path})`, patrón ya usado en `test_web_series.py:646-652`.

### 9.2 D-0 · Medida de presentación — **PASS** (2026-11-04)

**Método.** Chrome 156 headless, DPR 1 y 2, sobre `main` `35283b5`; HTML estático con el marcado real y el
`web.css` del repo; `getBoundingClientRect().width` de `.library-card .portada`, `.series-card .portada` y
`.portada.series-cover`. DPR no cambia la geometría CSS. Sin desbordamiento horizontal en ningún caso.

| Viewport | `.content` | cols Biblio | portada Biblio | cols Inicio | portada Inicio | ficha | Descubrir |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 320 | 320 | 1 | **290** | 2 | 135 | 120 | 80 |
| 375 | 375 | 2 | 162,5 | 2 | 162,5 | 120 | 80 |
| 390 | 390 | 2 | 170 | 3 | 106,66 | 120 | 80 |
| 768 | 768 | 4 | 167,33 | 6 | 106,33 | 120 | 80 |
| 900 | 656 | 3 | 188,8 | 3 | 188,8 | 140 | 80 |
| 1024 | 780 | 4 | 164,11 | 4 | 164,11 | 140 | 80 |
| 1240 | 996 | 5 | 167,59 | 5 | 167,59 | 140 | 80 |
| 1440 | 1196 | 6 | 168 | 6 | 168 | 140 | 80 |
| 1920 | 1240 | 6 | 175,33 | 7 | 146 | 140 | 80 |

**Conclusión: PASS.** El peor caso presentado es **290 CSS** (Biblioteca a 320 de viewport) → **600 = 2,07×**.
El borde de una sola columna (357 de viewport → 327 CSS) queda a **1,84×**. `480` queda descartado: 1,66× en 290
y 1,47× en 327. Ningún uso normal supera 300 CSS, luego **Q-2 no se reabre**.

- **Corte de la ficha:** el paso de 140 a 120 px es `@media (max-width: 768px)` (`web.css:1113`); medido 768 →
  120 y 769 → 140. **No hay ningún corte en 1109 px** (esa línea es la rejilla del Inicio en móvil).
- **Precisión sobre el «1,8×» de la ficha:** ese 1,8× es la **columna única del móvil** (327 CSS a viewport
  357 → 1,84×), no el escritorio a 3 columnas: a 900 CSS la portada mide 188,8 y 600 da **3,18×**. La frase de
  la ficha mezcla dos anchos; la decisión no cambia.
- **Desviación frente a la estimación de la ficha §1 (líneas 80-86):** estimaba 296/333 para Biblioteca y 171,5
  para Inicio; medido 290/327 y 188,8. La desviación >10 % aparece **solo en el Inicio** (+10,1 % en el caso de
  900); en Biblioteca es −2,0 % / −1,8 %. No cambia la decisión porque en ese caso 600 da 3,18×.
- **Cobertura:** Chrome 156 headless. Firefox y Safari: **NOT RUN**; la geometría depende de
  `auto-fill`/`minmax` del CSS y el margen de 2,07× lo absorbe.

**Evidencia de AC-02.** Esta tabla, con navegador, versión, DPR y fecha, es el registro del gate.

### 9.3 Medición en la Pi (criterio 4)

- **Hecho el 2026-11-05:** banco `scripts/medicion/banco_portadas.py` (rama `e0d6ea5`) sobre la Pi del PO, en un
  contenedor de un solo uso: 30 candidatos, 29 medidos (1 ilegible), 5 repeticiones por archivo y ancho, 240 y
  600 px. Resultado: p95 a 600 = **156,2 ms (PASS)**, bytes **93,7 KB** y ΔRSS **65,5 MB** (FAIL de los umbrales
  propuestos; ratificados por el PO con 100 KB y 80 MB). Evidencia completa, veredicto por umbral y NOT RUN en
  `docs/design/medicion-BL-PORT1-2026-11-05.md`.
- **Pendiente (NOT RUN):** la medida de página y disco de la ficha §10.2: 30 portadas en frío con 6 peticiones
  concurrentes (≤ 6 s), 304 caliente (≤ 30 ms), `docker stats --no-stream`/`/sys/fs/cgroup/memory.current` y
  `du -sb` real de la caché con extrapolación a 100/1000 series. No se cierran por omisión.
- **Salida:** `docs/design/medicion-BL-PORT1-2026-11-05.md` (agregados y cifras, sin rutas ni nombres de archivo).
  PASS/FAIL/NOT RUN separados (DoD del issue). El ancho está decidido (**Q-2 = 600**, 480 descartado en §9.2) y
  los umbrales de bytes y RSS ratificados (Q-4): si la medida de página no cumple, la primera palanca es el
  semáforo local de MEJORAR 4 (ficha §7.4) y la cifra se lleva al PO; cambiar el ancho exige reabrir Q-2 y, con
  `v2` ya desplegada, `v3` (FR-03).

### 9.4 Navegador real (criterio 7)

AC-21 en escritorio (1240 y 1920) y móvil (375 y 320): caché vacía → primera carga (fría) y caliente; forzar un
404 con una serie sin fuente; comprobar «Por revisar». Capturas y pasos anotados. No corre en CI (junto con la
medida de la Pi, §9.3); se marca **NOT RUN** si no se ejecuta.

### 9.5 Informe del criterio 6 (PR-3)

`scripts/medicion/censo_portadas.py` — una pasada, **solo lectura**, sobre la base y los ficheros reales:

1. Para cada `Series`: leer la cabecera del JPEG cacheado (preferir `v2`; si no existe, la legada) con
   `Image.open(...).width`, **sin decodificar**.
2. Si el ancho es menor que 600: localizar el primer `File` no ausente con el mismo criterio que la cascada,
   abrir su primera página en orden natural con `puede_tener_portada` + lectura acotada y leer solo la cabecera.
3. Clasificar en: `ya_en_objetivo` · `regenerable_al_pedir` (extraíble y original ≥ 600; se arreglará al
   visitarla) · `extraible_mas_adelante` (el primer `File` no es extractable pero otro posterior sí; hoy no se
   intentaría) · `original_pequeno` · `sin_extractor` · `sin_fuente`.
4. Salida: CSV por serie + recuento por causa. No escribe base, caché ni disco. La cifra que decide BL-PORT2 es
   `original_pequeno + extraible_mas_adelante + sin_extractor + sin_fuente`; `regenerable_al_pedir` **no**
   cuenta como problema.

**Refinamiento respecto a la ficha §10.3:** la ficha propone tres causas; se añaden `ya_en_objetivo`,
`regenerable_al_pedir` y `extraible_mas_adelante` para no atribuir a «original pequeño» lo que en realidad es
«aún no visitada» o «no se intentó el siguiente fichero». Sin esto, el informe mentiría en la dirección de pedir
BL-PORT2 de más.

### 9.6 Regla de PASS/FAIL/NOT RUN

Cada criterio se cierra con: `PASS` (test o medida adjunta con su salida), `FAIL` (con la salida) o `NOT RUN`
(con el motivo y qué falta). Un criterio `NOT RUN` no cierra el criterio del issue (DoD: «PASS, FAIL y NOT RUN
separados»). Ningún `NOT RUN` se sustituye por «debería funcionar».

---

## 10. División en PRs

**Valoración de la propuesta del Lead:** de acuerdo con los tres cortes; son tres dominios distintos y el
primero ya es grande. Dos matices: **el orden** (recomiendo PR-2 antes que PR-1) y que **la medida de la Pi es
puerta de PR-1**, no de PR-3: es la evidencia de NFR-02/03/06 y debe estar antes de fusionar (después de
desplegar, cualquier cambio de ancho exigiría `v3`). El ancho ya está decidido: **Q-2 = 600** (§11).

| PR | Título | FR | AC | Ficheros (previsión) | Depende de |
|---|---|---|---|---|---|
| **PR-1** | `BL-PORT1 (1/3): tamaño por uso y caché v2 perezosa` | FR-01…FR-10, FR-15…FR-18 | AC-01…AC-14, AC-17…AC-21 | `utils/cover.py`, `web/series.py`, `web/pendientes.py` (sin cambios funcionales; se verifica que sigue a 240), `web/discovery.py` (ancho explícito 320), tests; plantillas solo si Q-3 = sí | Nada (si PR-2 ya está, mejor) |
| **PR-2** | `BL-PORT1 (2/3): escritura segura de la caché (atómica y sin 500)` | FR-11, FR-12 | AC-22, AC-23, AC-24 | `utils/cover.py`, `web/series.py`, `tests/test_cover_cache.py`, `tests/test_web_series.py` | Nada; independiente de PR-1 |
| **PR-3** | `BL-PORT1 (3/3): censo de portadas por debajo del objetivo` | FR-13, FR-14 | AC-15, AC-16 | `scripts/medicion/censo_portadas.py`, `docs/design/medicion-BL-PORT1-<fecha>.md`, `tests/test_medicion_portadas.py` | PR-1 desplegado (la `v2` debe existir en la instalación real) |

**Orden recomendado: PR-2 → PR-1 → PR-3.** Razones: (a) PR-2 es pequeño, autocontenido y cierra un 500 real
que hoy existe; (b) PR-1 reescribe la cascada pero parte del camino de escritura ya seguro; (c) PR-3 mide lo
que queda **después** de que la regeneración perezosa haya podido actuar. Si el Lead prefiere PR-1 primero, es
válido siempre que PR-2 esté fusionado **antes del despliegue** y PR-1 declare en su descripción que el borde de
disco lleno es el bug heredado (no una regresión nueva).

**Por qué no cabe todo en una PR:** son tres decisiones separadas — contrato de tamaño y clave de caché;
integridad de la escritura; medición—, con revisiones y pruebas distintas. Juntarlas haría una PR de ~10
ficheros donde un fallo de caché ocultaría un fallo de medición. Además, PR-3 depende de que PR-1 esté
desplegado; no puede ir en el mismo commit.

**Una PR = un dominio.** Si el tablero exige una fila por PR, se abren tres tarjetas hijas de #300 con la
numeración `(1/3)`, `(2/3)`, `(3/3)`; no se reparte el issue en tres historias.

---

## 11. Preguntas para el PO

### Q-1 (RESUELTA por el PO el 2026-11-04) — Criterio 1 contra criterio 5: series que solo tienen caché externa antigua

**Pregunta.** Una serie sin CBZ extraíble (CBR real o `File` ausente) cuya única caché es una externa de 320
px se servirá a 320 (o 240) y **no** se regenerará, porque hacerlo exigiría consultar `cover_url` (criterio 5
lo prohíbe salvo en la cascada actual). ¿Se acepta que esas series no cumplan el criterio 1 hasta BL-PORT2?

**Recomendación: sí, aceptarlo y contarlo.** Es la única lectura coherente de los criterios 2, 3 y 5 juntos:
no ampliar, no salir a la red, no borrar. Se sirve la mejor imagen local que hay. El informe de PR-3 dirá
cuántas son (`sin_extractor` + `sin_fuente`; para el criterio 1, también `original_pequeno`) y esa cifra decide
BL-PORT2. **No** se propone descargar ahora: sería una historia distinta con su propio benchmark y su propia
puerta legal.

**Decisión del PO (2026-11-04): se acepta tal cual.** Esas series se quedan a 320/240, sin red y sin borrar, y
se cuentan en el informe del criterio 6. Sin trabajo adicional en esta historia.

### Q-2 (RESUELTA por el PO el 2026-11-04) — 600 px; 480 descartado

**Pregunta.** ¿Se fija el ancho objetivo de la portada de serie en **600** o en **480**?

**Recomendación (v0.1, con la estimación de la ficha): 600.** El 2× del uso normal más ancho es 592 (296 CSS en el borde de una columna, ficha líneas
83 y 372-377); 600 lo cubre y deja el borde de 333 CSS a 1,8×. Con 480, ese mismo caso queda a 1,62× y el uso
normal de escritorio (186 CSS → 372 a 2×) a 2,58×; se ahorraría ~36 % de píxeles (20 % de ancho) a cambio de
volver a ver blando el caso más exigente.

**Decisión del PO (2026-11-04): 600 px.** Con AC-02 PASS (§9.2): peor caso medido **290 CSS** (Biblioteca a 320)
→ **600 = 2,07×**; borde de una columna (327 CSS a 357) → **1,84×**; a 900 CSS con 3 columnas, 188,8 → **3,18×**.
**480 queda descartado**: 1,66× en 290 y 1,47× en 327. Ficha: 140 CSS a ≥769 y 120 a ≤768 (`@media
(max-width: 768px)`); Descubrir, 80. La medida de la Pi sigue siendo puerta de PR-1 para NFR-02/03/06 (§9.3).

**Nota de precisión (registro).** El «1,8×» de la ficha corresponde a la **columna única del móvil** (327 CSS a
357), no al escritorio a 3 columnas (188,8 CSS → 3,18× con 600). Y la ficha estimaba 296/333 y 171,5; medido
290/327 y 188,8 (+10,1 % en el peor caso del Inicio), lo que no cambia la decisión.

### Q-3 (no bloquea) — ¿Añadir `?v=2` al `src` para que el arreglo se vea al instante?

**Pregunta.** La URL de la portada no cambia y `Cache-Control` permite reutilizar la imagen vieja hasta 24 h
tras desplegar (ficha §8, línea 500). ¿Se añade `?v=2` en los tres usos de `ui.portada` para que la primera
visita tras el despliegue no muestre la portada vieja?

**Recomendación: sí, en PR-1.** Es un cambio de una línea por plantilla (`_rejilla_biblioteca.html:11`,
`dashboard.html:150`, `series_detail.html:8`), no toca cabeceras ni `ETag`, y evita que el coleccionista
concluya que «no ha funcionado» durante un día. Coste: un parámetro en el HTML y actualizar las pruebas de
plantilla que comparen el `src` exacto. Si el Lead prefiere no tocarlo, se acepta la ventana de 24 h y se anota
como riesgo R-01 (es cosmético y temporal).

### Q-4 (RESUELTA por el PO el 2026-11-05) — umbrales de coste de la Pi

**Pregunta.** ¿Se ratifican los umbrales propuestos por la ficha §10.1 (p95 frío ≤ 400 ms a 600; 30 frías con 6
concurrentes ≤ 6 s; 304 ≤ 30 ms; delta RSS ≤ 40 MB; media ≤ 60 KB/portada y ≤ 60 MB/1000 series) como criterio
de PASS/FAIL de NFR-02…NFR-06?

**Recomendación (v0.1): ratificarlos tal cual y declararlos provisionales** hasta que haya una medida real de la
Pi. La medida llegó el 2026-11-05 (banco de 29 archivos): p95 a 600 = 156,2 ms (**PASS**), bytes 93,7 KB y ΔRSS
65,5 MB (**FAIL** de los dos umbrales propuestos).

**Decisión del PO (2026-11-05): se mantiene 600 y se ratifican umbrales nuevos.** Media ≤ **100 KB/portada**
(≈100 MB/1000 series, ~1 % de una biblioteca de 8 GB) y ΔRSS ≤ **80 MB** (pico total 144,6 MB dentro del
contenedor de 512 MB). No se baja a 480: en el móvil de una columna (290 CSS) 480 da 1,66×, no 2×, y el objetivo
de la historia es nitidez a 2×. **NFR-05 y NFR-06** llevan los valores nuevos; NFR-03/NFR-04 siguen NOT RUN.

---

## 12. Riesgos

| ID | Riesgo | Impacto | Mitigación / nota |
|---|---|---|---|
| R-01 | La URL no cambia y `max-age=86400` muestra la imagen vieja hasta 24 h tras desplegar | Cosmético, temporal | `ETag` nuevo revalida al caducar; Q-3 propone `?v=2` |
| R-02 | Serie solo con caché externa antigua y sin CBZ extraíble: se queda a 320/240 (tensión criterio 1 vs 5) | Esa serie no cumple nitidez todavía | Q-1; se cuenta en el informe (PR-3); BL-PORT2 decide |
| R-03 | El primer `File` no es extractable (CBR) pero otro posterior sí: la cascada no lo intenta | Serie se queda sin extracción aunque tenga un CBZ | Comportamiento actual, fuera de alcance (no se cambia la selección); el informe lo cuenta como `extraible_mas_adelante` para BL-PORT2 |
| R-04 | Regeneración concurrente de la misma serie: dos peticiones extraen a la vez | CPU desperdiciada; no corrupción | Escritura atómica (PR-2); duplicar es aceptable en Pi (6 conexiones); sin lock salvo que la medida lo pida |
| R-05 | La caché legada huérfana crece y no se borra desde la app | Disco (≈ 4–14 KB por serie; ~4–14 MB por 1000) | Invariante no borrar; la purga el desinstalador; limpieza opcional fuera de alcance |
| R-06 | La primera página del CBZ no es la portada (créditos, scan) | Portada «fea» pero existente | Comportamiento actual; esta historia no cambia la selección de página |
| R-07 | Decodificar una página enorme en la Pi | Pico de RAM | `MAX_PIXELES_PORTADA` (40 Mpx) ya acota; el búfer de salida a 600×900 RGB ≈ 1,6 MB; todo en `to_thread` |
| R-08 | El ancho 600 no cabe en el presupuesto de disco/memoria de alguna instalación | Decisión de producto | Medido el 2026-11-05: 93,7 KB/portada y ΔRSS 65,5 MB, dentro de los umbrales ratificados (100 KB/80 MB). No se reabre Q-2; la medida de página (frías/concurrentes, du real) sigue NOT RUN |
| R-09 | Un corte deja un JPEG truncado que `exists()` daría por bueno | Portada rota para siempre | PR-2 (atómica); hasta entonces es el bug heredado documentado en la ficha |
| R-10 | Caché ilegible (permisos, corrupción previa): hoy 500 | El navegador pinta el marcador igual; no hay texto nuevo | Fuera de alcance (§6); riesgo declarado, no se promete |
| R-11 | El informe se ejecuta antes de que la regeneración perezosa haya pasado por la biblioteca y cuenta como «problema» lo que solo era «no visitada» | Cifra sesgada → BL-PORT2 mal priorizada | Clase `regenerable_al_pedir` separada (FR-14, §9.5); ejecutar tras desplegar PR-1 y tras una pasada de uso normal |
| R-12 | La ficha caduca el 2027-01-03 | Referencia obsoleta | Revalidar antes de implementar; citar `git diff` de los ficheros si ha cambiado `main` |
| R-13 | Una descarga externa que no puede escribir la caché (disco lleno) descarta los bytes ya descargados y responde 404: la persona ve el marcador aunque la imagen llegó | Portada no visible hasta que haya sitio; no es regresión (hoy igual) | Fuera de alcance: cambiar el contrato de `fetch_and_cache_cover` para devolver bytes es otra historia; se anota para BL-PORT2 o para una mejora de escritura |

---

## 13. Trazabilidad: criterios del issue → requisitos → criterios de aceptación → prueba

| Criterio del issue #300 | FR | AC | Verificación |
|---|---|---|---|
| 1. Tamaño según dónde se muestra (240/600/320; umbral antes de implementar) | FR-01, FR-02, FR-03, FR-17, FR-18 | AC-01, AC-02, AC-03, AC-04 | pytest + medida (D-0: **PASS**, 2026-11-04) |
| 2. Sin ampliar lo que no existe | FR-02 | AC-05, AC-06 | pytest |
| 3. La caché se rehace sola, sin perder `ETag` ni `Cache-Control` | FR-03, FR-04, FR-05, FR-09, FR-10 | AC-07, AC-08, AC-09 | pytest |
| 4. Ligero en la Pi (perezoso, fuera del bucle, sin reprocesar la colección, medido) | FR-05, FR-11, FR-12, FR-16 | AC-10, AC-11, AC-12, AC-22, AC-23, AC-24 | pytest + medida (banco 2026-11-05: p95 **PASS**; bytes/RSS ratificados; página NOT RUN) |
| 5. Sin red | FR-06, FR-15 | AC-13, AC-14 | pytest |
| 6. Medición de lo que queda | FR-13, FR-14 | AC-15, AC-16 | pytest del clasificador + informe real |
| 7. Pruebas (grande, pequeño, caché vieja, CBR, ausente, navegador) | FR-06, FR-07, FR-08 | AC-17, AC-18, AC-19, AC-20, AC-21 | pytest + navegador |

---

## 14. Auto-revisión

- [x] **Cada AC es comprobable** con pytest (20), medida registrada (AC-02, AC-12) o navegador con pasos
      (AC-21). No hay «rápido», «bonito» ni «intuitivo». **AC-02 PASS** (§9.2, 2026-11-04) y **AC-12 medido**
      (2026-11-05): PASS en tiempo; FAIL de los dos umbrales propuestos, ratificados por el PO.
- [x] **Los 7 criterios del issue** están cubiertos uno a uno (§13) y no se contradice ninguno. La única
      tensión real (criterio 1 vs 5) está declarada y **resuelta por el PO** (Q-1), no escondida.
- [x] **Los números citan la ficha o una medida**: 240/600/320 (§5.3, líneas 364-370 y 372-379); `v2` (383);
      orden de la cascada (385-397); no borrar (398-399); cabeceras (400-402); atómica (402-403); 500 de disco
      (470-481); informe (§10.3, 586-597); umbrales de la Pi (§10.1, 556-573) y medición de AC-12 del 2026-11-05
      (156,2 ms / 93,7 KB / 65,5 MB, umbrales ratificados); anchos de presentación medidos (§9.2, 2026-11-04)
      frente a la estimación de la ficha (§1, 80-86; §10.0, 545-554); `srcset` descartado (§5.4, 423-445).
- [x] **El benchmark existe** (`docs/design/benchmark-BL-PORT1.md`, 2026-11-04) para esta feature P1; no se
      inventa referencia. Veredicto aplicado: IGUALAR → FR-01…FR-12; MEJORAR 1/2 → FR-11/FR-12; MEJORAR 3 →
      FR-13/FR-14.
- [x] **Nada bloqueante**: toda la implementación nueva va en `asyncio.to_thread`; no hay lote, ni job, ni
      semáforo por defecto, ni dependencia nueva, ni migración.
- [x] **Sin texto nuevo en pantalla** ni identificadores internos (BR-01 a BR-04): el estado visible es el de
      hoy (§6).
- [x] **Una historia, no dos**: PR-1 es el comportamiento; PR-2 es la integridad de la misma caché (MEJORAR
      1/2); PR-3 es medición. No hay cambio de dominio oculto en PR-1.
- [x] **Sin `srcset`**: se aplica la decisión de la ficha §5.4; si se reabre, exige un benchmark nuevo.
- [x] **Dependencia de la ficha declarada**: caduca 2027-01-03; PR-3 depende de PR-1 desplegado; la medida por
      portada de la Pi ya está hecha (AC-12, 2026-11-05) y la de página sigue **NOT RUN**, sin sustituirse por un
      PASS supuesto.

### Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-04 | v0.1 | Primera especificación a partir del issue #300 y de la ficha `benchmark-BL-PORT1.md` (`35283b5`). Pendiente: Q-1, Q-2 (bloquean), Q-3, Q-4; tabla de AC-02 (NOT RUN). |
| 2026-11-04 | v0.2 | **Q-1 y Q-2 resueltas por el PO** (§11): Q-1 aceptada; Q-2 = **600 px**, 480 descartado. **AC-02 PASS** con la medida de presentación en Chrome 156 headless (§9.2): peor caso 290 CSS → 600 = 2,07×; borde 327 CSS → 1,84×; a 900 CSS, 3,18×. Correcciones: corte de la ficha es `@media (max-width: 768px)` (768 → 120, 769 → 140; no hay corte en 1109 px); nota de precisión del «1,8×» (columna única del móvil, no escritorio); desviación conocida frente a la estimación de la ficha (290/327/188,8 vs 296/333/171,5; +10,1 % en Inicio). |
| 2026-11-05 | v0.3 | **AC-12 medido en la Pi** (rama `e0d6ea5`, contenedor de un solo uso): p95 a 600 = **156,2 ms (PASS**, 2,6× de margen), bytes **93,7 KB** y ΔRSS **65,5 MB** (**FAIL** de los umbrales propuestos de 60 KB y 40 MB). **Q-4 ratificada por el PO** con el dato delante: se mantiene **600** y los umbrales pasan a **NFR-05 ≤ 80 MB** y **NFR-06 ≤ 100 KB/portada y ≤ 100 MB/1000 series** (PASS con los nuevos). Quedan **NOT RUN** 30 frías/6 concurrentes, 304 caliente, `docker stats`/cgroup y `du` real. Evidencia: `docs/design/medicion-BL-PORT1-2026-11-05.md`. |
