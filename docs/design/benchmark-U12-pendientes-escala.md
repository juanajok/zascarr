# Ficha de benchmarking — U12: saber cuántos pendientes hay y leer el nombre entero

> Procedimiento: `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Historia: Kanban #199 (BL-U12, P0, 5 pts).
> **Estado: segunda versión, tras la revisión de la PR #213 (DEVUELTO 🔁). No se ha escrito código ni se ha movido
> ninguna tarjeta.** Escrita **antes** de implementar, como exige el gate (en U20 se hizo después; ver
> `benchmark-U20-marcar-todos.md`). Las decisiones marcadas «del revisor» fijan **comportamiento de producto**; la
> implementación propuesta es mía y debe demostrar ese contrato.

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
| Orden | `imported_at DESC` **sin desempate** | `services/review.py:113`. `imported_at` es `NOT NULL` con `server_default=now()` (`models/__init__.py:391`) y `now()` de Postgres es el **inicio de la transacción**: los archivos que una adopción registra en una sola transacción comparten marca, así que los empates **no son raros** |
| Hueco de portada | `.pending-card .cover.cover-missing { visibility: hidden }` conserva el espacio 2:3 | `static/web.css:631` |
| Nombre | `.filename { white-space: nowrap; text-overflow: ellipsis }` | `static/web.css:633` |
| Portadas | una petición `/ui/pendientes/{id}/portada` por tarjeta; `onerror` en línea añade `.cover-missing` | `_tarjeta_pendiente.html`; `utils/cover.py::extract_cover_thumbnail` |
| Texto del Inicio | «Puedes decirnos de qué serie son, uno a uno.» | `services/primeros_pasos.py:155` |
| Cuántas de esas 50 peticiones de portada son 404, y por qué | **No medido, y no hace falta para cumplir el criterio 4** | La auditoría dice «casi todas». Ver «Portadas: tres casos» y «Qué falta medir» |
| Cómo se comporta una imagen que falla, sin JS | **Medido** en Chrome 154 (`file://`, 5 variantes): con `width:100%; height:auto; alt=""` y **sin** `aspect-ratio`, una portada rota mide **0 px** (tarjeta 52 px) y una cargada ocupa su alto natural (300 px); con `aspect-ratio: auto 2/3` o `2/3` la rota **reserva 300 px**. Firefox y Safari **NOT RUN** | Experimento del 2026-10-15, descrito en «Portadas» |

### Qué falta medir (no se inventa)

**La consulta de abajo es un inventario de formatos, no un diagnóstico de portadas.** Dice cuántos pendientes son
`.cbz`, `.cbr`, etc. Sirve para dimensionar el caso «ausencia conocida» (extensión sin extractor). **No** mide
respuestas 404 y **no** distingue archivo ausente, `.cbz` sin imágenes y `.cbz` corrupto: eso exigiría abrir los
archivos, y no se autoriza explorar archivos en producción.

```sql
SELECT file_format, lower(right(file_path, 4)) AS ext, count(*)
FROM files
WHERE issue_id IS NULL AND review_dismissed IS FALSE AND metadata->>'match_status' = 'unsorted'
GROUP BY 1, 2 ORDER BY 3 DESC;
```

Es de **solo lectura** y barata (una agregación sobre `files`). **No hace falta ejecutarla para implementar U12.**
Si más adelante se quisiera saber **por qué** fallan las portadas, será una investigación **aparte**: se presentará
antes el procedimiento exacto, su coste de lectura y los datos que recogería.

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

## Decisiones (cerradas por el revisor de la PR #213, 2026-10-15)

### 1. Navegación: sin saltos. *Contrato del revisor*

> Orden total y estable. Resolver o ignorar tarjetas de la página actual **no** hace que «Siguiente» salte
> pendientes. Se puede volver hacia los anteriores y regresar al inicio. El rango mostrado corresponde al conjunto
> actual, no a posiciones obsoletas.

**Esto sustituye mi inclinación anterior** («`OFFSET` aceptando que salte»), que queda **retirada**: el desempate por
`id` arregla empates, no el desplazamiento del conjunto al sacar filas. La coherencia con Carpetas no justifica
reproducir la limitación aquí.

**Implementación propuesta (a demostrar con las pruebas de abajo): paginación por cursor sobre la clave
`(imported_at DESC, id DESC)`.**
- «Siguiente» = los 50 que van **después de la clave del último mostrado**, no «a partir de la posición 51». Que esa
  fila se resuelva o desaparezca no mueve el cursor: es una clave, no una posición.
- «Anterior» = los 50 que van **antes de la clave del primero mostrado** (consulta inversa y se invierte). «Inicio» =
  sin cursor.
- Lo nuevo (el importador añade archivos con `imported_at` mayor) entra **por delante** del cursor: aparece en
  «Anterior»/«Inicio», no desplaza ni salta lo que ya se estaba recorriendo.
- **Rango y total:** `N = count_pending()` y la posición inicial `X = 1 + (cuántos pendientes van antes de la clave
  del primero mostrado)`, una `COUNT` más con el **mismo** filtro. Así «Mostrando X–Y de N» describe el conjunto
  **actual**. Coste: una consulta de lista y dos `COUNT` por carga.
- **Tras resolver sin recargar:** el rango y el total se refrescan con el mismo gancho oculto que ya actualiza el
  menú (`RECONTAR_MENU` → `/ui/_nav/estado`), ampliado a este texto. Sin eso el rango quedaría obsoleto en pantalla,
  que el contrato prohíbe.
- Un cursor mal formado o ajeno cae en la primera página (como el cursor del asistente de vinculación).

**Límite declarado:** el cursor da «Anterior»/«Siguiente»/«Inicio», **no** «ir a la página 17». El criterio 1 pide
anterior/siguiente «o equivalente»; no hay selector de página.

### 2. Portadas: tres casos, sin rebajar la aceptación

El criterio 4 dice «archivo del que el servidor **ya sabe** que no hay portada». No exige averiguarlo abriendo todos
los CBZ en cada renderizado.

| Caso | Qué sabe el servidor | Qué se pinta |
|---|---|---|
| **Ausencia conocida** | La **extensión** no tiene extractor: `extract_cover_thumbnail` solo lee `.cbz`/`.zip` (`utils/cover.py:44`). Se decide con `file_path`, **sin I/O** | **Sin `<img>`, sin petición `/portada` y sin bloque de portada**. El predicado debe ser **el mismo** que el del extractor (una constante compartida), para que no puedan discrepar |
| **Disponibilidad desconocida** | Es `.cbz`/`.zip`; solo abriéndolo se sabe si tiene imagen, está ausente o corrupto | `<img loading="lazy" alt="">` **sin** `aspect-ratio` y con `height:auto`. Si carga, ocupa su alto natural; si falla, **mide 0 px** y no deja hueco (medido en Chrome 154). **Sin `onerror`** y sin JS. La petición **sí** se hace (es desconocida) y puede ser 404 |
| **Disponible** | La petición devolvió imagen | Se muestra **debajo del nombre** (orden de lectura: nombre, detalle, portada) o con `max-height`, para que no empuje el nombre fuera del primer pantallazo a 375 px |

**Rechazado por el revisor (y por mí):**
- Devolver **200 con un SVG** solo para que desaparezcan los 404: no resuelve el hueco.
- **Explorar archivos en producción** (abrir o hacer `stat` de los CBZ al renderizar) para convertir «desconocida»
  en «conocida».

**Incompatibilidad concreta, declarada en vez de rebajar el criterio:** para que **ninguna** petición de un `.cbz`
sea 404 haría falta saber de antemano que no tiene portada, y eso solo se obtiene con I/O por archivo o con un
estado persistido (una columna «tiene portada», que es una migración y ADR 0005 la excluye). Con los mecanismos que
hay, el criterio 4 se cumple **para la ausencia conocida** (no hay petición ni bloque) y **el hueco desaparece también
en la desconocida**, pero un `.cbz` sin imágenes seguirá costando una petición 404. Si el responsable quiere cero 404
también ahí, es otra decisión (esquema o precálculo) y **no** está en U12.

**Lo que no está verificado:** el colapso a 0 px de la imagen rota se midió **solo en Chrome 154**. Firefox y
Safari (incluido iOS) **NOT RUN**: hay que comprobarlo antes de dar el criterio 2 por cumplido, y si alguno reserva
el bloque, la opción de la tarjeta con miniatura pequeña vuelve a estudiarse.

### 3. Texto del Inicio. *Aprobado por el revisor*

> Revisa los archivos pendientes y elige a qué serie pertenecen.

Sustituye «Puedes decirnos de qué serie son, uno a uno.» (`services/primeros_pasos.py:155`). **No** amplía U12 a la
revisión general de textos de U21. Hay que revisar `tests/test_primeros_pasos.py` y `tests/test_inicio.py`.

## Invariantes de ZascArr

- **No mentir:** el total sale de `count_pending()` con el **mismo** filtro; el menú, el Inicio y la lista deben dar
  la misma cifra (hoy el recuento del menú ya se comparte con ese filtro único).
- **No perder nada:** ningún pendiente queda sin poder alcanzarse; paginar no filtra.
- **Sin efectos:** la lista no escribe nada.
- **Pi:** una consulta de lista + una de recuento por carga; `OFFSET` profundo a vigilar si la cola crece mucho.
- **Sin JS propio ni migraciones** (ADR 0005): el recuento y el desplazamiento no necesitan esquema nuevo.

## Casos de prueba antes de implementar

Postgres real para el orden, el cursor y el recuento; `FakeSession` donde baste.

**Navegación (el contrato del revisor):**
1. **El caso de la historia:** con 120 pendientes, la página 1 dice «Mostrando 1–50 de 120» y ofrece «Siguiente»; la
   tercera dice «101–120 de 120» y no ofrece «Siguiente».
2. **Sin saltos al resolver (el contrato):** se abre la página 1, se resuelven 10 de sus tarjetas por el servicio
   real y **después** se sigue «Siguiente» (renderizado antes). La unión de *vistos ∪ resueltos ∪ siguiente* es
   exactamente el primer tramo del orden: **ningún pendiente se omite ni se repite**.
3. **Resolver todas las de la página y seguir:** con las 50 resueltas, «Siguiente» sigue funcionando (el cursor es una
   clave, no una fila).
4. **Anterior e inicio:** desde la página 2, «Anterior» devuelve **los mismos** 50 que siguen pendientes antes del
   primero mostrado, sin duplicar ni omitir, e «Inicio» vuelve a la primera.
5. **Empates:** 60 archivos con el **mismo** `imported_at` (como una adopción en una transacción): las páginas son
   disjuntas y su unión es exhaustiva.
6. **Importación concurrente:** entre dos cargas llegan archivos con `imported_at` mayor: no desplazan ni saltan lo que
   se recorría; aparecen por delante.
7. **El rango es del conjunto actual:** tras resolver 10, el rango y el total visibles se actualizan **sin recargar**
   y coinciden con `count_pending()` y con el menú.
8. **Cursor inválido o ajeno:** cae en la primera página, sin 500.

**Portadas y nombre:**
9. **Ausencia conocida:** un `.cbr` pendiente no emite `<img>` ni `/portada` ni bloque de portada; el predicado es el
   mismo que usa `extract_cover_thumbnail` (prueba que lo compara con la constante compartida).
10. **Desconocida sin hueco:** un `.cbz` pendiente se pinta con `<img loading="lazy" alt="">` sin `aspect-ratio` y sin
    `onerror`; en navegador real, una portada que falla **mide 0 px** (Chrome; Firefox/Safari NOT RUN o PASS según
    se ejecute).
11. **Disponible sin perjudicar el nombre:** a **375 px**, el primer pantallazo muestra al menos un nombre completo
    **con portada disponible**.
12. **Nombre íntegro, visual (no solo HTML):** a **375 px** y con un nombre **largo y sin espacios**, el nombre se ve
    entero: sin elipsis (`text-overflow` no es `ellipsis`), con `overflow-wrap` que lo parta, y sin desplazamiento
    horizontal de la página (`scrollWidth ≤ clientWidth`). Además de la regresión CSS (sin `white-space: nowrap`).
13. **Inicio:** el texto es el aprobado y no contiene «uno a uno».
14. **Teclado:** «Anterior», «Siguiente» e «Inicio» son enlaces nativos con nombre accesible propio.
15. **Sin efectos:** la lista y sus enlaces no escriben nada.

## Estimación refinada

Se mantiene **5 (M)**, **confianza Media**, con una advertencia honesta: el cursor (consulta de lista **y** de
«anterior», dos `COUNT`, ampliar el gancho que refresca el menú, paginador y CSS de tarjeta) pesa más que el
`OFFSET` que se había contado. Si al implementar la parte del cursor + refresco del rango + las pruebas 2–7 supera
lo previsto, se **divide** (navegación / portadas y nombre) en lugar de recortar criterios. Es una estimación, no un
compromiso.

## Decisión final

Las tres decisiones las **cerró el revisor** (2026-10-15). No cambia la arquitectura: **sin ADR** (sin esquema, sin
JS propio, sin dependencia nueva). Esta ficha pasa a «lista para implementar» solo cuando el revisor la dé por
corregida; hasta entonces, **U12 sigue en «En refinamiento»**.
