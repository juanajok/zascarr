# Ficha de benchmarking — BL-IT01 «Acotar la biblioteca sin perder filtros» (#283)

> Ficha de **nivel 1** según `docs/design/benchmark-referencias.md` (CLAUDE.md §13): UI/consulta
> de lectura sobre `SeriesService`, sin migración ni ficheros. **Historia:** issue #283, P1,
> ~5 puntos. **Commit contrastado del repo: `038874a` (2026-11-05, `origin/main`).** Fecha:
> 2026-11-05. Caduca: ~2027-01-04 (60 días). Es insumo para especificar; **no autoriza
> implementar** (decide el PO sobre la spec, no sobre esta ficha).

## 1. Problema local (código vigente, no la propuesta)

El issue pide: (1) añadir un filtro conservando los anteriores y volviendo a una página válida;
(2) retirar filtros de uno en uno y «Limpiar todos» explícito; (3) mostrar los filtros activos y
el recuento **en series**; (4) que una combinación sin coincidencias conserve la consulta y deje
retirar condiciones; (5) que un error/petición inválida no simule una biblioteca vacía; (6)
etiquetas, foco visible y anuncios accesibles en escritorio/móvil/teclado, sin imponer columnas
de escritorio; (7) ninguna consulta a proveedores, lectura de contenido ni mutación de catálogo;
(8) paginar sin materializar el catálogo, con métricas de consultas/objetos/latencia.

**Hechos comprobados en el código vigente** (re-verificados a `038874a`):

| Hecho | Evidencia |
|---|---|
| El reinicio de filtros al pulsar personaje/saga **está documentado y aceptado** hoy: «un reset simple de los demás filtros que se acepta a propósito». | `src/zascarr/web/library.py:1-13` |
| La barra de filtros es un `<form>` HTMX que pide el fragmento y empuja URL; conserva `q`, tradición, editorial y los `character_id`/`story_arc_id` ocultos, y reinicia `page=1`. | `web/templates/biblioteca.html:7-31` (`hx-get="/ui/biblioteca/resultados"`, `hx-target="#rejilla"`, `hx-push-url="true"` en `:7-9`; ocultos y `page=1` en `:28-30`) |
| El recuento «N series catalogadas» vive **fuera** de `#rejilla`, que es el único destino del intercambio; al filtrar no se actualiza. | `biblioteca.html:5` frente a `:53-55`; `_rejilla_biblioteca.html` no pinta `total` |
| Pulsar un resultado de personaje o saga **navega a página completa** y el enlace solo lleva su id: se pierden `q`, tradición, editorial, el otro filtro y la página. | `_resultados_personaje.html:6` (`href="/ui/biblioteca?character_id=…"`), `_resultados_saga.html:6` |
| La conversión de ids usa `UUID(value)` sin capturar `ValueError`: un `publisher_id`/`character_id`/`story_arc_id` no UUID produce **500**, no un aviso con contexto. | `web/library.py:58-64`; comprobado con `TestClient`+`FakeSession`: `GET /ui/biblioteca?publisher_id=no-es-uuid` → 500, `GET …/resultados?character_id=xxx` → 500 |
| El servicio ya combina los cinco filtros con `WHERE` y calcula `total` con un `COUNT` sobre subconsulta; pagina con `offset/limit` y no materializa el catálogo. | `services/series.py:39-90` (`:53` tradición, `:58` búsqueda de título, `:61` personaje, `:68` saga; count y paginación `:82-89`); `page_size=24` en `library.py:75` |
| El repo usa htmx 4.0.0 local; `hx-push-url="true"` empuja **la URL pedida** (no la URL de la página). | `static/vendor/README.md:10`; docs htmx `hx-push-url` [verificado 2026-11-05] |

Los GET de biblioteca solo leen la BD local (criterio 7: sin proveedores ni escritura en este
camino). `page` no se valida en las rutas (`web/library.py:88,106`): fuera de rango no se corrige
y una página posterior a `pages` se lee como «ninguna serie coincide»; los tests no cubren
combinaciones, retirada, recuento, URL ni errores (`tests/test_web_library.py:119,148-173`;
`tests/test_series_service.py:61-79` es de filtros individuales).

**Lectura.** La consulta no es el problema: `SeriesService` ya combina filtros. Se pierde el
**estado de la vista** (la navegación de personaje/saga reinicia, el recuento no está en el
fragmento, no hay retirada individual y la URL empujada es la del fragmento). La solución debe ser
una sola fuente de estado (URL + formulario) y un fragmento con resultado, recuento, filtros
activos y estados vacío/error.

## 2. Referencias consultadas (versión/commit)

| Referencia | Versión / commit | Qué se inspeccionó |
|---|---|---|
| **iTunes column browser** (IT-01, la referencia del issue) | Guía Apple `itns72c6bc8b`, consultada 2026-11-05; la página no declara versión de iTunes | Qué hace y qué **no** promete: hasta cinco categorías en columnas, seleccionar en una acota las siguientes y la lista; el orden de columnas no se cambia. No documenta retirada individual, URL, accesibilidad ni escala |
| **Komga** (local) | **1.29.2**, `25c67d14` (2026-10-30, `main`), MIT | `FilterPanels.vue`/`FilterList.vue`/`filter.ts` y `BrowseSeries.vue`: modelo de filtros activos, modo por campo (`allOf`/`anyOf`), URL, retirada y reset |
| **Kapowarr** (local) | **1.3.2**, `c191dda` (2026-09-14, `main`), GPL-3.0 | `frontend/templates/volumes.html`, `frontend/static/js/volumes.js`, `frontend/api.py`, `backend/implementations/volumes.py`, `backend/base/definitions.py`: filtro de biblioteca y persistencia |
| **Kavita** | **0.9.1.18**, `9e17770` (2026-11-01, `develop`), GPL-3.0 | Filtros AND/OR con `Must Contains`/`Must Not Contains`, filtros dinámicos y smart filters guardables/compartibles por URL; ya verificado en `docs/design/benchmark-etiquetas.md` §2.7 y §3 |

**Límite de la referencia del issue.** El issue remite a un
`benchmark-itunes-zascarr-2026-10-22.md` adjunto que **no está en el repo** (`docs/design/` no
tiene `*itunes*`); esta ficha usa el enlace de Apple y el texto del issue, y no atribuye a iTunes
usabilidad ni rendimiento en ZascArr (el issue lo advierte).

## 3. Cómo lo resuelve cada una (contrato, no pantalla)

- **iTunes column browser.** Filtrado **progresivo**: cada selección acota la lista inferior y las
  columnas siguientes; la jerarquía es fija (Géneros → Compositores → Agrupaciones → Artistas →
  Álbumes) y no se reordena. No documenta retirada, URL, móvil ni teclado. **Sirve la idea de
  acotar sin perder lo anterior, no la disposición en columnas.**
- **Komga.** Filtros como mapa campo → lista de condiciones (`FiltersActive`), con modo por campo
  `anyOf`/`allOf` (la UI arranca en «any of»/OR si el campo no fija modo; `allOf` se guarda en
  `filterMode`; `FilterPanels.vue:115-172`, `filter.ts:4-15`). Cada valor se alterna o se quita;
  `clear(key)` vacía solo ese campo (`FilterPanels.vue:130-136`) y «Reset filters» vacía todos
  (`BrowseSeries.vue:472,873`). El estado se escribe en la query de la ruta (página, orden,
  filtros y `filterMode`) y se restaura al entrar/volver (`BrowseSeries.vue:881-927,1024-1040`).
  **Fricciones:** panel de filtros de SPA, no chips de barra; los enlaces de metadatos de tarjeta
  construyen `query` con una sola clave (`BrowseSeries.vue:299,329,361`), lo que puede reemplazar
  la query entera y perder filtros [verificado en código, no ejecutado].
- **Kapowarr.** Un solo filtro (`LibraryFilter`: `WANTED`/`MONITORED`, `definitions.py:436-443`)
  más búsqueda por título, combinados en la petición (`api.py:981-994`, `volumes.py:954-987`).
  UI: `<select>` «No Filter/Wanted/Monitored» (`volumes.html:79-83`) persistido en
  **localStorage** (`volumes.js:272-275,297-300`), botón de limpiar solo para la búsqueda
  (`:226-229`); los recuentos son globales (`volumes.js:232-246`). **Fricciones:** sin
  multifaceta, chips ni URL compartible; «No Filter» es la única retirada.
- **Kavita (0.9.1.18).** AND/OR con `Must Contains`/`Must Not Contains`; filtros dinámicos y
  smart filters guardables y compartibles por URL (wiki de filtros 0.9.1; ver
  `benchmark-etiquetas.md`). Aporta el **contrato de exclusión** y la persistencia compartible; no
  un patrón de chips verificado en código.
- **Repo propio.** Reutilizar `ui.chip`, `ui.estado_vacio`, `ui.region_viva` y los contadores `hx-swap-oob` para actualizar cabecera sin duplicar el fragmento.

## 4. Supuestos de las referencias que NO valen en ZascArr

- **Que las facetas forman una jerarquía fija de columnas.** Personaje y saga son búsquedas sobre
  universos grandes y sin jerarquía entre sí; el criterio 6 prohíbe imponer columnas al móvil y
  ADR-0001 prohíbe el JS de una SPA.
- **Que la URL puede ser la de un endpoint de datos y que el recuento es global.** En
  iTunes/Komga la URL es de la vista y en Kapowarr el recuento es del catálogo; aquí el formulario
  apunta a `/resultados` (fragmento) y el criterio 3 pide **series que coinciden**.
- **Que «quitar un filtro» y «limpiar todos» son lo mismo.** El enlace actual borra todo; el issue
  exige separarlos y, sin framework, el chip debe ser un enlace/botón accesible (no `alt`-clic).

## 5. Decisión por idea

| Idea | Resultado | Motivo / condición |
|---|---|---|
| Acotar progresivamente sin perder lo ya elegido | **Adoptar** | Es la esencia de iTunes y del issue; añadir un filtro debe reducir el resultado, no reiniciarlo |
| Column browser físico de 3–5 columnas en escritorio | **Descartar** | Jerarquía fija que aquí no existe; móvil y teclado quedarían mal; ADR-0001; se copiaría el diseño, no el patrón |
| Chips de filtros activos con retirada individual | **Adaptar** | Komga muestra valores activos y permite quitar uno; aquí se hacen chips-enlace/botón con `ui.chip`, sin JS: cada chip conserva el resto de la query y vuelve a página 1 |
| «Limpiar todos» explícito y separado de retirar uno | **Adoptar** | Komga `reset filters` (`BrowseSeries.vue:472`) y Kapowarr «No Filter»; en ZascArr un enlace/botón explícito, no el actual «Quitar filtro de personaje/saga» que lo borra todo sin decirlo |
| Estado en la URL (página + filtros), restaurable | **Adaptar** | Komga lo hace en query de ruta; aquí hay que empujar `/ui/biblioteca?…`, no `/ui/biblioteca/resultados?…`, y serializar los cinco filtros con `urlencode` |
| Recuento «N series» dentro del fragmento (o fuera de banda) | **Adoptar** | Criterio 3 del issue; patrón OOB ya usado en `_nav_contadores.html:6-8` y `ui.region_viva` |
| Vacío/error con recuperación conservando la consulta | **Adaptar** | `ui.estado_vacio` ya existe; el vacío actual (`_rejilla:5-6`) no deja retirar condiciones. No se verificó el patrón de error de Komga/Kavita: se resuelve con `ui.aviso` |
| Selección de personaje/saga que conserva el resto | **Adaptar** | Sustituir el enlace de página completa por un `hx-get` que añade la selección al formulario/URL; hoy `_resultados_personaje.html:6` y `_resultados_saga.html:6` lo pierden todo |
| Recuentos por opción (facet counts) en cada filtro | **Descartar en esta historia** | No lo pide el issue; exige N consultas/`GROUP BY` y no hay patrón verificado en las referencias consultadas; reevaluar con datos de uso |

## 6. IGUALAR (mínimos competitivos, nivel concreto)

1. **Añadir un filtro conserva los activos y vuelve a una página válida.** Mínimo: elegir
   personaje/saga o cambiar tradición/editorial/q produce una petición con **los cinco filtros**
   en la URL, `page=1` y la intersección correcta, sin reinicio silencioso. Carencia:
   `_resultados_personaje.html:6`/`biblioteca.html:8-9` (el formulario conserva, el enlace no);
   `library.py:1-13` lo documenta como aceptado.
2. **Retirar uno y «Limpiar todos» son operaciones distintas y visibles.** Mínimo: cada filtro
   activo se pinta como chip con nombre accesible («Quitar filtro Tradición: Manga»), conserva el
   resto y vuelve a página 1; «Limpiar todos» deja la biblioteca sin query/filtros. Evidencia:
   Komga `clear(key)`/`reset filters`, Kapowarr «No Filter» + limpiar búsqueda; hoy el único
   enlace (`biblioteca.html:48-50`) borra de más.
3. **Recuento en series actualizado y vacío con salida.** Mínimo: el fragmento (u OOB) actualiza
   «N series coinciden con estos filtros» a la vez que la rejilla, con el número de **series**; el
   vacío conserva la consulta y ofrece quitar/limpiar, sin afirmar que la biblioteca está vacía.
   Evidencia: `biblioteca.html:5` está fuera del destino y `_rejilla:5-6` no ofrece acción;
   `ui.estado_vacio` ya permite título, texto y acción.

## 7. MEJORAR (huecos ordenados por oportunidad, con evidencia)

1. **URL canónica y recuperable (recarga, marcador, atrás/adelante).** Hoy `hx-push-url="true"`
   empuja la URL del fragmento (`/ui/biblioteca/resultados?…`, `biblioteca.html:7-9`,
   `_rejilla:1-3`) y al recargar se obtiene HTML sin layout. Mejora: empujar
   `/ui/biblioteca?<filtros>&page=N` y renderizar ese estado; probar recarga, marcador y
   atrás/adelante. Criterio: la URL de la barra siempre sirve una página completa.
2. **Errores y valores inválidos con recuperación, sin 500 ni «vacío» mentiroso.** Hoy
   `UUID(value)` lanza `ValueError` → 500 (`library.py:58-64`, reproducido con TestClient) y
   `page` no valida rango (`:88,106`). Mejora: filtro inválido se descarta o se explica con
   `ui.aviso` conservando los válidos; página fuera de rango se corrige; un 500 no deja la rejilla
   anterior sin mensaje (htmx no intercambia 4xx/5xx por defecto). Criterio: toda combinación
   inválida acaba en 200/400 explicable y con recuperación.
3. **Accesibilidad del flujo, no solo del formulario.** Hoy no hay `aria-live` para el resultado,
   `page-current` es solo CSS (`_rejilla:29-30`), los resultados de personaje/saga aparecen sin
   anuncio (`biblioteca.html:33-47`) y retirar no define foco. Mejora: `ui.region_viva` para
   recuento/vacío/error, `aria-current="page"`, chips-enlace con nombre accesible y foco al
   control siguiente; alcance WCAG 2.2 AA del flujo. Criterio: teclado y anuncio de carga/resultado
   (criterio 6 del issue).

## 8. Contradicciones y riesgos con el repo

| # | Lo que hay / lo que se pretende | Evidencia y consecuencia |
|---|---|---|
| 1 | El docstring acepta reiniciar filtros; el issue pide lo contrario | `library.py:1-13`; hay que **actualizar el contrato documentado**, no solo la UI, y añadir regresión |
| 2 | `hx-push-url` empuja la URL del fragmento | `biblioteca.html:7-9`, docs htmx; recargar/marcar/compartir da HTML sin layout; **riesgo alto**, el criterio 1/2 no se puede acreditar con eso |
| 3 | El recuento está fuera del fragmento | `biblioteca.html:5` vs `:53`; queda obsoleto al filtrar; si se mueve, cuidado con el presupuesto de texto (≤20 palabras de entrada) |
| 4 | «Quitar filtro de personaje/saga» borra todo | `biblioteca.html:48-50`; convierte una retirada individual en «limpiar todos» sin decirlo |
| 5 | El enlace de personaje/saga reinicia y pierde la página | `_resultados_personaje.html:6`, `_resultados_saga.html:6`; contradice el criterio 1 |
| 6 | Un id no UUID produce 500 | `library.py:58-64`; reproducido con TestClient; además htmx no intercambia el 500 → la rejilla anterior se queda sin aviso |
| 7 | `page` sin `ge=1` ni corrección de rango | `library.py:88,106`; una página posterior a `pages` se lee como «ninguna serie coincide», que el criterio 4 prohíbe |
| 8 | No hay chips ni «Limpiar todos»; `ui.chip` es un `<span>` no interactivo | `_componentes.html:10-13`; habrá que envolverlo en enlace/botón con nombre accesible, sin JS |
| 9 | La paginación pinta todos los números | `_rejilla:25-32`; con `pages` grande, HTML y foco desmesurados; el criterio 8 pide no materializar el catálogo, y aunque la consulta pagina, la navegación no se acota |
| 10 | Los tests actuales no fijan el comportamiento nuevo | `tests/test_web_library.py:119,148-173`; faltan combinaciones, retirada, recuento, URL, página fuera de rango, error y accesibilidad; el servicio solo prueba filtros individuales (`test_series_service.py:61-79`) |
| 11 | El issue, su ficha IT-01 y el reset intencionado no están reconciliados en el repo | `docs/BACKLOG.md` no tiene fila BL-IT01 (grep a `038874a`); `docs/design/` no tiene `*itunes*`; el docstring `library.py:1-13` debe cambiar y registrarse antes de implementar (DoR) |

**Riesgos de implementación:** (a) imitar el orden fijo de columnas de iTunes impondría un orden
de facetas que ZascArr no tiene; (b) chips-enlace + htmx pueden perder el foco al reemplazar el
fragmento (usar `hx-swap="innerHTML"` y foco explícito); (c) el recuento OOB debe ir en el mismo
render que la rejilla; (d) el `COUNT` con `distinct` por personaje/saga exige test de combinación
en PostgreSQL real; (e) no convertir los filtros en consultas guardadas.

## 9. NOT RUN

No se abrió navegador real ni la Pi; no se ejecutó htmx (su semántica se leyó en documentación y
vendor 4.0.0); no se ejecutó la suite completa ni una consulta real a PostgreSQL (el 500 se
reprodujo con `TestClient` y `FakeSession`); no se levantaron Komga, Kapowarr ni Kavita para
interactuar con sus filtros (se leyó su código/documentación); Sonarr/Radarr no se consultaron
(opcional); sin medición de latencia, tamaño de HTML ni auditoría WCAG 2.2; sin comprobar móvil ni
atrás/adelante con historial de htmx. La referencia iTunes no prueba usabilidad ni rendimiento.

**Caducidad:** ~2027-01-04. Antes hay que revalidar contrato de filtros, versión de htmx y estado
de `docs/BACKLOG.md`; si el PO cambia el alcance (facet counts, filtros guardados), se revisa antes
de especificar. La ficha es insumo: no autoriza implementar.
