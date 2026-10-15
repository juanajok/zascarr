# Ficha de benchmarking — U12: saber cuántos pendientes hay y leer el nombre entero

> Procedimiento: `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Historia: Kanban #199 (BL-U12, P0, 5 pts).
> **Estado: ficha lista para revisión. No se ha escrito código ni se ha movido ninguna tarjeta.** Escrita
> **antes** de implementar, como exige el gate (en U20 se hizo después; ver `benchmark-U20-marcar-todos.md`).

## Historia / problema observado

Como coleccionista con más de mil pendientes, quiero saber cuántos hay y leer el nombre entero de cada archivo,
para decidir sin abrir nada. Hoy `/ui/pendientes` pinta 50 tarjetas sin decir que hay más, sin paginar, con un hueco
de portada vacío y el nombre cortado con elipsis (auditoría `docs/design/auditoria-ui-2026-10-15.md`, hallazgo C1).

## Datos reales y medición de partida

| Dato | Valor | Cómo se sabe |
|---|---|---|
| Pendientes en la instalación de referencia | 1.322, en 108 carpetas | Auditoría del 2026-10-15 en la Pi (`a5369ef`). **No lo he vuelto a medir** |
| Lo que pinta la lista | las **50** más recientes, sin total ni desplazamiento | Código en `main` `e65e047`: `ReviewService.pending_files(limit=50)`, sin `offset`; `web/pendientes.py::index` no pasa parámetros |
| El total ya existe | `ReviewService.count_pending()` cuenta **con el mismo filtro** (`_condiciones_pendientes`) | `services/review.py:85`; lo usan el menú (`navegacion.py:27`) y el Inicio (`inicio.py:73`) |
| Orden | `imported_at DESC` **sin desempate** | `services/review.py:113`. Con un `OFFSET` sería no determinista si dos archivos comparten `imported_at` |
| Hueco de portada | `.pending-card .cover.cover-missing { visibility: hidden }` conserva el espacio 2:3 | `static/web.css:631` |
| Nombre | `.filename { white-space: nowrap; text-overflow: ellipsis }` | `static/web.css:633` |
| Portadas | una petición `/ui/pendientes/{id}/portada` por tarjeta; `onerror` en línea añade `.cover-missing` | `_tarjeta_pendiente.html`; `utils/cover.py::extract_cover_thumbnail` |
| Texto del Inicio | «Puedes decirnos de qué serie son, uno a uno.» | `services/primeros_pasos.py:155` |
| **Cuántas de esas 50 peticiones de portada son 404, y por qué** | **No medido** | La auditoría dice «casi todas». Ver «Qué falta medir» |

### Qué falta medir (no se inventa)

El criterio 4 («sin 404 evitables») depende de **por qué** fallan las portadas, y eso no está medido. Hay tres causas
posibles con remedios distintos: formato sin extractor (`.cbr`), archivo ausente del disco, y `.cbz` sin imágenes o
corrupto. Consulta de **solo lectura** para la Pi, que habrá que ejecutar el responsable o con su autorización:

```sql
SELECT file_format, lower(right(file_path, 4)) AS ext, count(*)
FROM files
WHERE issue_id IS NULL AND review_dismissed IS FALSE AND metadata->>'match_status' = 'unsorted'
GROUP BY 1, 2 ORDER BY 3 DESC;
```

## Referencias consultadas (código leído)

| Referencia | Commit | Licencia | Qué se leyó |
|---|---|---|---|
| Sonarr, rama `v5-develop` | `d137dc5a19f46a8aa6d41e706143cad1f0af27af` | GPL-3.0 | `frontend/src/Components/Table/TablePager.tsx`, `frontend/src/Wanted/Missing/Missing.tsx`, `src/NzbDrone.Core/Datastore/BasicRepository.cs` (`GetPaged`), `PagingSpec.cs`, `frontend/src/Series/SeriesPoster.tsx`, `Localization/Core/en.json` |
| Kapowarr, rama `development` | `5b225cfed49d9eccf13e14cb2a947143477606ef` | GPL-3.0 | `docs/src/general_info/library_import.md`, `frontend/static/js/library_import.js` (ya leídos para U20) |

**Solo como patrón: no se copia código.** **No consultadas:** Radarr, Mylar3, Suwayomi (no se buscó paginación en
ellas; **no se afirma que no la tengan**).

## Cómo lo resuelve cada una

**Sonarr (vista «Missing» y su `TablePager`).**
- Paginación **de servidor por desplazamiento**: `GetPaged` ejecuta dos consultas, los registros con
  `LIMIT {PageSize} OFFSET {(Page-1)*PageSize}` y un `SELECT COUNT` aparte para `TotalRecords`.
- El control muestra **«página / total de páginas»**, primera/anterior/siguiente/última y un selector de página,
  cada botón con `aria-label` («Ir a la página siguiente»), y debajo el **total de registros**
  (`TotalRecords`). El tamaño de página es configurable y tiene máximo (`TablePageSizeMaximum`).
- La confirmación de «buscar todo lo que falta» cita el recuento total (`...{totalRecords} missing episodes?`).
- El póster usa un **placeholder** (`posterPlaceholder`) que **mantiene su tamaño**; no colapsa el hueco.

**Kapowarr (Library Import).**
- **No pagina**: acota por **fuera** de la lista, con «máximo de carpetas escaneadas» (`limit`) antes de proponer,
  para no agotar el límite de ComicVine.
- La lista entera se pinta de una vez; el recuento es el de lo que devolvió la propuesta.

## Supuestos de su modelo que NO valen en ZascArr

- **La lista es una cola que se vacía.** En Sonarr, ver una página no la altera. Aquí **resolver una tarjeta la
  saca del conjunto** (`RECONTAR_MENU` la hace desaparecer): un `OFFSET` calculado antes de resolver salta filas
  después. Es el punto delicado de la historia (ver opciones).
- **Pi compartida.** Sonarr usa dos consultas por vista; aquí el recuento ya está calculado para el menú, pero la
  lista de páginas profundas con `OFFSET` recorre todas las filas anteriores. Con 1.322 filas es irrelevante;
  **no medido** más allá.
- **Hoja de portadas.** Sonarr tiene miniaturas casi siempre (metadatos); aquí salen del propio CBZ y un `.cbr` **no
  tiene extractor** (`extract_cover_thumbnail` devuelve `None`), así que «sin portada» es el caso normal, no la excepción.
- **Selector de tamaño de página.** Sonarr lo expone; para El Coleccionista sería otro control que entender. No se
  adopta.

## Adoptar / adaptar / descartar

| Idea | Decisión | Motivo |
|---|---|---|
| Recuento total junto a la lista (`TotalRecords`) | **Adoptar** | `count_pending()` ya existe y usa el mismo filtro que la lista |
| Texto «Mostrando 1–50 de N» en vez de «página / total» | **Adaptar** | Lo exige el criterio 1; coincide con el vocabulario de «Pendientes por carpeta» |
| Anterior/siguiente con `aria-label` propio | **Adoptar** | Criterio 1: operables por teclado |
| Paginación por `OFFSET` (Sonarr) | **Adaptar** con un desempate estable (`imported_at DESC, id`) | Consistente con `/ui/pendientes/carpetas` (`desplazamiento`/`limite`); ver decisión abierta 1 |
| Selector de tamaño de página | **Descartar** | Un control más sin valor para el caso |
| Primera/última página y selector de página | **Descartar por ahora** | Con 50 por página y ~27 páginas, anterior/siguiente basta; revisable |
| Placeholder que conserva el tamaño del póster | **Descartar** | Contradice el criterio 2 (no reservar el espacio). Ver decisión abierta 2 |
| Acotar por fuera en vez de paginar (Kapowarr) | **Descartar** | La persona tiene que poder llegar a todos |

## Decisiones abiertas (no se toman aquí)

1. **Qué pasa con el desplazamiento al resolver tarjetas.** Opciones: (a) `OFFSET` por página como Carpetas y Sonarr,
   aceptando que «Siguiente» tras resolver varias salta esas filas (no se pierden: reaparecen en la primera página);
   (b) paginación por **cursor** `(imported_at, id)`, sin saltos pero sin «página anterior» simple; (c) semántica de
   cola: siempre las 50 primeras de lo que queda, con «Mostrando 1–50 de N». *Inclinación:* (a) con desempate, por
   coherencia con Carpetas y por la letra del criterio 1; la (c) sería la más honesta con una cola, pero el criterio
   pide controles de paginación explícitos.
2. **Cómo evitar el hueco sin `onerror`.** El criterio 4 prohíbe depender de `onerror`, pero el servidor **solo
   sabe de antemano** lo que la extensión dice (`.cbr` etc. → sin extractor) sin abrir el archivo. Para un `.cbz` sin
   imágenes o ausente, saberlo exige I/O. Opciones: (a) no pintar `<img>` para extensiones sin extractor y dejar el
   resto con `loading="lazy"` aceptando un posible 404; (b) que `/portada` devuelva **200 con un SVG neutro** (sin 404,
   sin `onerror`, pero el espacio vuelve a ser un bloque); (c) tarjeta con miniatura **pequeña** al lado, donde el
   «hueco» no cuesta pantalla. Cada una cumple parte de los criterios 2 y 4; **elegir es decisión de diseño** y
   depende de la medición de arriba.
3. **Qué dice el Inicio en lugar de «uno a uno».** Criterio 1 solo pide que no lo prometa. Hay que fijar la frase
   (probablemente la de U21: «una frase de entrada ≤ 20 palabras») y revisar `tests/test_primeros_pasos.py`.

## Invariantes de ZascArr

- **No mentir:** el total sale de `count_pending()` con el **mismo** filtro; el menú, el Inicio y la lista deben dar
  la misma cifra (hoy el recuento del menú ya se comparte con ese filtro único).
- **No perder nada:** ningún pendiente queda sin poder alcanzarse; paginar no filtra.
- **Sin efectos:** la lista no escribe nada.
- **Pi:** una consulta de lista + una de recuento por carga; `OFFSET` profundo a vigilar si la cola crece mucho.
- **Sin JS propio ni migraciones** (ADR 0005): el recuento y el desplazamiento no necesitan esquema nuevo.

## Casos de prueba antes de implementar

Con `FakeSession` donde baste y con Postgres real para el orden y el recuento:
1. **El caso de la historia:** con 120 pendientes, la página 1 dice «Mostrando 1–50 de 120» y ofrece «Siguiente»; la 3
   dice «101–120 de 120» y no ofrece «Siguiente» (`desplazamiento`, `limite`, `total`).
2. **El recuento coincide:** la cifra de la lista = `count_pending()` = la del menú (un único filtro).
3. **Orden determinista:** dos archivos con el mismo `imported_at` aparecen siempre en el mismo orden y ninguno se
   repite ni se salta entre páginas (el desempate por `id`). *Límite que Sonarr no garantiza en lo que leí.*
4. **Resolver y paginar:** tras asignar/ignorar una tarjeta, el total baja en 1 y no aparece una fila dos veces
   (según la decisión abierta 1).
5. **Sin hueco:** una tarjeta sin miniatura no reserva el bloque de portada (según la abierta 2).
6. **Nombre íntegro:** un nombre largo sale entero en el HTML (sin `white-space: nowrap` en `.filename`).
7. **No promete «uno a uno»:** el texto del Inicio no contiene «uno a uno» con más de una página.
8. **Teclado:** «Anterior» y «Siguiente» son enlaces nativos con nombre accesible propio.

## Estimación refinada

Se mantiene **5 (M)**, **confianza Media**: servicio (`offset` + desempate) y ruta, plantilla del paginador, CSS de
tarjeta y nombre, cambio del texto del Inicio y sus pruebas. Lo que puede moverla: la decisión abierta 2 (la (b) es
pequeña; la (c) toca el diseño de la tarjeta) y el resultado de la medición de portadas. Es una estimación, no un
compromiso.

## Decisión final

**Pendiente de revisión.** No cambia la arquitectura: sin ADR. Para pasar a «En curso» faltan las tres decisiones
abiertas y, si se quiere acotar el criterio 4, la consulta de solo lectura sobre la Pi.
