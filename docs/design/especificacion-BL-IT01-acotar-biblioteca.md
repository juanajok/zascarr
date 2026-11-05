# Especificación — BL-IT01 «Acotar la biblioteca sin perder filtros» (#283) — v0.1

> **Estado:** borrador v0.1 para ratificación del PO. **No autoriza implementar** hasta el DoR de §13;
> no cambia `src/`, `tests/` ni `alembic/` por sí mismo.
> **Historia:** issue **#283**, `[BL-IT01]`, P1, ~5 puntos, talla M. **Ficha de benchmark (nivel 1):**
> [`benchmark-BL-IT01-acotar-biblioteca.md`](benchmark-BL-IT01-acotar-biblioteca.md), contrastada a
> `038874a` (2026-11-05); caduca ~2027-01-04. **Procedimiento:**
> [`benchmark-referencias.md`](benchmark-referencias.md) (CLAUDE.md §13). **Fecha:** 2026-11-05.
> **Base de código:** la de `038874a` (la misma que la ficha); esta spec fija el **contrato**, no describe
> trabajo no fusionado. **Notación:** EARS con palabras clave en español (Ubicuo, CUANDO, SI/ENTONCES,
> MIENTRAS, DONDE) y criterios en Given/When/Then; identificadores en inglés, superficie en español.

## 1. Contexto y problema

El coleccionista ya filtra la biblioteca por título, tradición, editorial, personaje y saga, pero **la
vista pierde su estado**: elegir personaje o saga navega a `/ui/biblioteca?character_id=…` y descarta los
demás filtros; el recuento «N series catalogadas» vive **fuera** de `#rejilla`, el único destino del
intercambio, y al filtrar queda viejo; no hay chips de filtros activos ni «Limpiar todos»; y un
`publisher_id` que no es UUID produce **500** (`UUID(value)` sin capturar). Evidencia a `038874a`:
`web/library.py:58-64`, `web/templates/biblioteca.html:5,7-9,48-50`, `_resultados_personaje.html:6`,
`_resultados_saga.html:6`.

**Reconciliación con el reset intencionado.** El docstring de `web/library.py:1-13` documenta el reinicio
de los demás filtros como «un reset simple … que se acepta a propósito». El issue #283 pide lo contrario:
esta spec **sustituye ese contrato** (elegir personaje/saga añade un filtro, no empieza de cero) y la
misma PR reescribe el docstring, no solo la UI.

**Reconciliación con la ficha IT-01 del issue.** El issue cita `benchmark-itunes-zascarr-2026-10-22.md`,
que **no está en el repo**; la ficha usa la guía de Apple del column browser de iTunes
(`itns72c6bc8b`, vía [`benchmark-BL-IT01-acotar-biblioteca.md`](benchmark-BL-IT01-acotar-biblioteca.md)
§2). Se toma **solo la idea de acotar sin perder lo elegido**; el column browser físico se descarta (§3),
y no se atribuye a iTunes usabilidad ni rendimiento en ZascArr.

**Qué no se toca:** la consulta ya combina los cinco filtros con `WHERE` y pagina en SQL
(`services/series.py:39-90`). Se arregla la **vista y el contrato de estado**, no el motor de búsqueda.

## 2. User story EARS y valor

**US-IT01 (EARS, español llano):**

> **CUANDO** estoy acotando mi biblioteca por título, tradición, editorial, personaje o saga y elijo un
> personaje o una saga, **ENTONCES** el sistema añade ese filtro y conserva los demás. **CUANDO** quiero
> soltar un filtro, tengo su chip con un «Quitar» que conserva el resto y vuelve a la primera página;
> **SI** quiero dejarlo todo, hay un «Limpiar todos» aparte. **MIENTRAS** la biblioteca está acotada, veo
> qué filtros están puestos y cuántas series coinciden, y ese número se anuncia al cambiar. **SI** una
> combinación no tiene resultados, la pantalla conserva mis filtros y me dice cómo quitarlos. **SI** algo
> falla o la dirección trae un valor inválido, veo un aviso con «Reintentar», no una biblioteca vacía que
> parezca real. **CUANDO** recargo, marco o uso Atrás/Adelante, la dirección sigue sirviendo la
> biblioteca entera con mis filtros.

**Valor:** no se pierde el trabajo de acotar; se puede recargar, marcar o compartir lo que se está viendo
y encontrarlo igual; y un error nunca se confunde con «no tengo tebeos». Todo con teclado y móvil, sin
aprender sintaxis ni instalar nada.

**Criterio de éxito:** (O-1) añadir un filtro nunca reinicia los demás; (O-2) cada filtro se retira por
separado y «Limpiar todos» es distinto; (O-3) el recuento del fragmento corresponde siempre a la rejilla;
(O-4) ni 422 ni 500 provocados por la entrada; (O-5) toda URL de la barra se recarga y da página completa.

## 3. Alcance y NO-goals

**En alcance (una PR):** contrato de estado en la URL y `HX-Push-Url` a la página completa desde el
fragmento (§5); fragmento `#rejilla` con recuento en región viva, chips, avisos, vacío, rejilla y
paginación (§6); personaje/saga que conserva los cinco filtros con compatibilidad con `?q=` (§7); entrada
inválida y error de BD con aviso y reintento, nunca 422/500 de la UI (§8); accesibilidad y presupuesto de
consultas (§9–§10); docstring, fila `BL-IT01` del `docs/BACKLOG.md` (Épica C) y pruebas de §12 en la misma PR.

**NO-goals explícitos:** (1) **facet counts** por opción — no los pide el issue, multiplican consultas en
la Pi; (2) **filtros guardados / smart filters** — otra historia con persistencia y nombres; (3) **column
browser físico** (iTunes) — no hay jerarquía entre personaje y saga, impondría un orden que ZascArr no
tiene y rompería móvil y teclado (ADR-0001); (4) **ventana de paginación** — se mantiene la lista completa
de páginas, ahora con `aria-current`; el HTML/foco con muchas páginas es un riesgo declarado (§13) para
una historia aparte; (5) **cambios de modelo o migración** — solo lectura sobre `SeriesService`;
(6) **nuevos filtros** (estado, año) y orden configurable; (7) **JavaScript propio nuevo, dependencias,
Redis o caché nueva** (ADR-0001, CLAUDE.md §4).

**Dependencia de orden:** `especificacion-etiquetas.md` (BL-ETQ1) reestructura la misma barra y el mismo
fragmento. **BL-IT01 va primero** (M, sin migración); BL-ETQ1 parte de este contrato (§13, R-6).

## 4. Requisitos funcionales (EARS)

| ID | Patrón | Requisito | AC |
|---|---|---|---|
| FR-01 | Ubicuo | El estado de la vista será **la URL** `/ui/biblioteca` con `q`, `tradition`, `publisher_id`, `character_id`, `story_arc_id` y `page`; recargar, marcar o Atrás/Adelante reconstruyen la misma vista. | AC-09 |
| FR-02 | Por evento | CUANDO cambia un filtro, se retira un chip, se limpia o se pagina, el fragmento devolverá `HX-Push-Url` con la **URL canónica de la página completa** y `Cache-Control: no-store`; nunca empujará `/ui/biblioteca/resultados`. | AC-09 |
| FR-03 | Estado | MIENTRAS haya filtros, el fragmento mostrará un chip por filtro activo, en orden fijo, con retirada individual que conserva el resto y fuerza `page=1`; «Limpiar todos» será una acción aparte. | AC-01, AC-02 |
| FR-04 | Estado | MIENTRAS la rejilla cambia, el fragmento anunciará el recuento en una región viva como **único** número visible de la vista; el texto fijo de la página no llevará cifra. | AC-03 |
| FR-05 | No deseado | SI una combinación no tiene resultados, ENTONCES se conservarán chips y consulta, se dirá que ninguna serie coincide y se ofrecerá salida visible (quitar o limpiar). | AC-04 |
| FR-06 | No deseado | SI falla la BD (`SQLAlchemyError`) en página o fragmento, ENTONCES 200 con `ui.aviso("warn")` y «Reintentar»; nunca 500, ni JSON en la rejilla, ni un vacío que parezca «no hay series». | AC-05 |
| FR-07 | No deseado | SI la URL trae UUID mal formado, tradición inexistente, `page<1`/no numérica o página posterior al final, ENTONCES se descarta o corrige con aviso conservando el resto; nunca 422. | AC-05 |
| FR-08 | Por evento | CUANDO se elige un personaje o saga, se añade su filtro conservando q, tradición, editorial y el otro id, con `page=1`; sin HTMX el enlace real hace la misma navegación. | AC-10 |
| FR-09 | Ubicuo | La paginación será de 24 por página en SQL (`COUNT` + `offset/limit`), conservará filtros y marcará la actual con `aria-current="page"`; sin materializar el catálogo y sin doble consulta por corrección de página. | AC-08 |
| FR-10 | Ubicuo | El flujo será operable con teclado y lector de pantalla: acciones como enlaces reales, nombres accesibles («Quitar filtro Tradición: Manga»), foco definido tras retirar y sin depender solo del color; en móvil sin columnas. | AC-06 |
| FR-11 | Ubicuo | Un GET de biblioteca no escribirá, no llamará a proveedores externos y no pondrá valores del coleccionista en `structlog`. | AC-07 |
| FR-12 | No deseado | SI la respuesta corrige la entrada, ENTONCES la URL empujada será la corregida, para que recargar e historial no conserven estados imposibles. | AC-05, AC-09 |

## 5. Contrato de estado, URL e historial

### 5.1 URL canónica

- `/ui/biblioteca?q=&tradition=&publisher_id=&character_id=&story_arc_id=&page=`, con orden fijo
  `q, tradition, publisher_id, character_id, story_arc_id, page`; se omiten filtros vacíos y **`page`
  siempre aparece** (también `page=1`). Construida con `urllib.parse.urlencode`, nunca concatenando a mano.
  Ejemplos: `/ui/biblioteca?page=1`; `/ui/biblioteca?q=noir&tradition=manga&page=2`.
- Un valor inválido no entra: se corrige o descarta (§8). `page` es la **efectiva** tras el ajuste.
- La URL canónica es la misma para página y fragmento; solo cambia la ruta (`/ui/biblioteca` frente a
  `/ui/biblioteca/resultados`).

### 5.2 Cabeceras del fragmento

- `GET /ui/biblioteca/resultados` → 200 con `_rejilla_biblioteca.html` y:
  `HX-Push-Url: <URL canónica de la página completa>` (nunca la del fragmento) y
  `Cache-Control: no-store` (Atrás no mezcla filtros con caché).
- htmx 4.0.0 vendorizado lee las cabeceras de respuesta `HX-*`; `HX-Push-Url` se traduce a `pushurl` en
  su lógica de historial y se usa como ruta literal (verificado en `static/vendor/htmx.min.js`).
  `HX-Replace-Url` **no se usa**: las peticiones de fragmento salen de URLs construidas por el servidor;
  la entrada inválida llega por GET de página, donde no hay cabecera de historial.
- La página completa no lleva cabeceras de historial.

### 5.3 Recarga, Atrás/Adelante y sin HTMX

- Recargar o abrir un marcador de una URL canónica devuelve página completa con el mismo estado (layout +
  rejilla recortada).
- **Atrás/Adelante:** al empujar la URL de página, htmx restaura con `GET` a esa URL y cabecera
  `HX-History-Restore-Request: true`, intercambiando el elemento `[hx-history-elt]`. Se añade
  `hx-history-elt` al `<main id="main">` de `base.html` para restaurar solo el contenido; la ruta de
  página no necesita código especial.
- **Sin HTMX:** el formulario es `GET` normal (`action="/ui/biblioteca" method="get"`) y todos los chips,
  paginación y enlaces de personaje/saga tienen `href` a la URL canónica. Es requisito, no extra.
- **Foco:** filtrar no roba el foco; tras retirar un chip va al contenedor de filtros activos (o al campo
  de título si no queda ninguno, §6.3).

## 6. Contrato de la vista (fragmento `#rejilla`)

El destino sigue siendo `#rejilla` (`hx-target="#rejilla"`, `hx-swap="innerHTML"`); dentro se pinta, en
orden: recuento/estado, avisos, chips, rejilla o vacío, paginación. El fragmento no repite layout, `<h1>`,
menú ni pie.

### 6.1 Recuento (región viva)

- `ui.region_viva("recuento-biblioteca")` (`aria-live="polite"`, `aria-atomic="true"`, `tabindex="-1"`;
  si se pinta a mano, además `role="status"`) **dentro** del fragmento. Textos exactos: con filtros «1 serie coincide con estos
  filtros.» / «N series coinciden con estos filtros.»; sin filtros «1 serie catalogada.» / «N series
  catalogadas.»; sin filtros y 0 «Tu biblioteca todavía no tiene series.»; con filtros y 0 «Ninguna serie
  coincide con estos filtros.».
- La frase fija de la página deja de llevar número: «Acota tu biblioteca por título, tradición, editorial,
  personaje o saga.» (≤20 palabras). El recuento vive solo en la región viva para no anunciarlo dos veces.
- **Límite declarado:** la región viva se crea en cada intercambio; el anuncio en lector real es **NOT
  RUN**. Plan B: región estable fuera de `#rejilla` actualizada con `hx-swap-oob`, mismo texto y prueba.

### 6.2 Chips de filtros activos

- Solo si hay filtros: `<ul class="filtros-activos" aria-label="Filtros activos">`, un `<li>` por filtro en
  orden fijo **Búsqueda, Tradición, Editorial, Personaje, Saga**.
- Fila: `<span class="chip info">{{ etiqueta }}</span>` (no interactivo) + enlace real de retirada
  `<a class="quitar-filtro" href="<URL canónica sin este filtro y page=1>"
  hx-get="<URL del fragmento sin este filtro, page=1 y quitar=<clave>>" hx-target="#rejilla"
  hx-swap="innerHTML" aria-label="Quitar filtro {{ etiqueta }}">Quitar</a>`.
- Etiquetas exactas: `Búsqueda: «{q}»`, `Tradición: {rótulo}`, `Editorial: {nombre|desconocida}`,
  `Personaje: {nombre|desconocido}`, `Saga: {título|desconocida}`; los nombres los resuelve el servidor
  (§9), nunca ids en pantalla.
- «Limpiar todos» va aparte (último `<li>`), solo si hay filtros: `href="/ui/biblioteca?page=1"` y
  `hx-get="/ui/biblioteca/resultados?page=1&quitar=todos"`, texto «Limpiar todos».
- `quitar` es un parámetro **interno** (valores cerrados `q`, `tradition`, `publisher_id`,
  `character_id`, `story_arc_id`, `todos`); no es filtro, no entra en la URL canónica ni en
  `HX-Push-Url`; un valor desconocido se ignora.

### 6.3 Foco tras retirar

- Si quedan filtros: `#filtros-activos` lleva `tabindex="-1" autofocus`; htmx 4 enfoca el primer
  `[autofocus]` del contenido intercambiado y el siguiente Tab recorre los chips.
- Si no queda ninguno (o «Limpiar todos»): el campo de título se sustituye fuera de banda
  (`hx-swap-oob="outerHTML"`, parcial `_campo_q.html` compartido con el formulario) con valor vacío y
  `autofocus`.
- **Límite declarado:** el foco de `autofocus` en contenido intercambiado/OOB de htmx 4.0.0 es **NOT RUN**
  en navegador; plan B: foco en el destino de `#rejilla` o `hx-focus`, nunca JavaScript a mano.

### 6.4 Vacío

- **Con filtros y 0 resultados:** se conservan chips y recuento; debajo,
  `<p class="empty">Prueba a quitar algún filtro de los de arriba.</p>`. La salida es la fila de chips
  (retiradas + «Limpiar todos») de encima; no se duplica la acción.
- **Sin filtros y 0 series:** la frase «Tu biblioteca todavía no tiene series.» vive en la región viva
  (§6.1); debajo, `<p class="empty"><a href="/ui/pendientes">Añade lo que tengas en el disco desde Por
  revisar.</a></p>` (sin repetir la frase).
- Nunca un vacío que culpe al usuario ni que diga «0 resultados».

### 6.5 Error

- `SQLAlchemyError` (incluye `ProgrammingError`/esquema sin migrar) se captura en página y fragmento:
  `await db.rollback()`, 200 y aviso con `ui.aviso("warn", "No se pudo cargar la biblioteca. Vuelve a
  intentarlo.")` + enlace «Reintentar» (`href` a la URL canónica de página, `hx-get` a la del fragmento).
- En error **no** se pinta recuento, rejilla ni vacío; los valores del formulario siguen en la barra, así
  que la consulta no se pierde. Otros fallos no controlados conservan el comportamiento global del repo
  (declarado, fuera de esta historia).

## 7. Personaje y saga sin perder filtros

- Los buscadores están **fuera** de `#filtros`; envían el formulario completo con `hx-include="#filtros"`
  (htmx 4 resuelve el selector y añade los `[name]` de dentro).
- Los campos tecleados tienen nombre propio para no chocar con el `q` del título: `name="personaje"` y
  `name="saga"`. Los endpoints `GET /ui/biblioteca/buscar-personaje` y `…/buscar-saga` reciben
  `personaje`/`saga` más `q`, `tradition`, `publisher_id`, `character_id`, `story_arc_id` como contexto.
- **Compatibilidad:** si no llega `personaje` (o `saga`) y sí `q`, el texto de búsqueda es `q` (contrato
  anterior y pruebas actuales: `?q=zzz` sigue devolviendo «Sin coincidencias»). Si llega `personaje`, `q`
  es el título y no el texto del buscador.
- El servidor construye **una URL de página completa por resultado** con los cinco filtros normalizados, el
  id elegido en su clave y `page=1`; la plantilla no concatena parámetros. El enlace es `<a href="…">`
  normal: sin HTMX navega a la página completa con el estado correcto, y con HTMX también es navegación
  completa de esa URL (no se exige `hx-get` en el resultado: el reset ya no existe y el enlace real es el
  contrato).
- El contexto inválido que llegue al parcial se descarta en silencio (no hay aviso fiable en una lista de
  sugerencias); al abrir la URL resultante, la página completa lo explica con aviso (§8).

## 8. Entradas inválidas

Todas las rutas reciben los parámetros como `str` y validan en un único helper: **ninguna entrada de la
UI acaba en 422** (FastAPI no tipa `UUID`/`int` aquí) **ni en 500**.

| Entrada | Comportamiento | Aviso (texto exacto) |
|---|---|---|
| `publisher_id`/`character_id`/`story_arc_id` no UUID | se descarta ese filtro; el resto se conserva | «El filtro de editorial, personaje o saga correspondiente no es válido; se ha quitado.» (el texto concreta cuál) |
| `tradition` fuera de `ComicTradition` | se descarta | «La tradición de ese filtro no existe; se ha quitado.» |
| `page` no numérica | `page=1` | «La página pedida no es válida; se muestra la primera.» |
| `page<1` | `page=1` | «La página pedida no existe; se muestra la primera.» |
| `page>pages` con resultados | página efectiva = `pages`; la URL empujada la refleja | «La página pedida no existe; se muestra la última.» |
| `page>pages` con `pages=0` | `page=1`, sin aviso de página | — |
| `q` de más de 200 caracteres | se recortan a 200 | «La búsqueda era demasiado larga; se han usado los primeros 200 caracteres.» |
| `q` con caracteres de control (`\n`, `\r`, U+0000–U+001F, U+007F) | se quitan antes de construir URL/cabeceras | «La búsqueda tenía caracteres no válidos; se han quitado.» |
| UUID bien formado pero inexistente | **no** es inválido: no se descarta; chip «desconocida/desconocido» y vacío con salida | — |
| Parámetros vacíos (`publisher_id=`) | sin filtro, sin aviso (regresión actual) | — |

Los avisos se pintan con `ui.aviso("amber", texto)` tras el recuento, uno por regla incumplida (no se
agrupan). No se consulta la existencia de un UUID válido (evita SELECT extra): un id de una fila borrada
da vacío con chips retirables, que es un estado explicable.

## 9. Rendimiento y consultas

| Interacción | SELECT máx. | Detalle |
|---|---:|---|
| Página `/ui/biblioteca` | **5** | editoriales (1) + nombres de chips de personaje/saga (≤2; la editorial sale de la lista) + `COUNT` (1) + página (1) |
| Fragmento `/ui/biblioteca/resultados` | **5** | nombres de chips (≤3) + `COUNT` (1) + página (1) |
| Sugerencias de personaje/saga | 1 | `search_characters`/`search_story_arcs` (límite 20 ya existente) |
| Paginación | las mismas | se pinta del contexto, sin consulta extra |

- 24 por página; `COUNT` sobre subconsulta y `offset/limit` en SQL (ya en `SeriesService.list_series`); sin
  facet counts, sin materializar el catálogo, sin N+1.
- `page>pages` **no puede costar una segunda consulta**: el servicio obtiene el `COUNT` antes del `offset`
  y ajusta la página ahí; se expone `pagina_efectiva(page, total, page_size)` (función pura) para reutilizar
  el cálculo en URL y plantilla. La prueba lo fija con contador de sentencias; si no se puede evitar el
  doble `SELECT`, no se fusiona hasta arreglarlo.
- **NOT RUN:** latencia real en la Pi (objetivo provisional p95 ≤ 300 ms para 2.000 series / 20.000
  números, a medir con el guion de la Pi antes de fusionar), tamaño de HTML y plan de consulta. La suite
  mide el **número** de sentencias, no tiempos.

## 10. Accesibilidad

- Labels reales (`<label class="sr" for>`); chips en `<ul>` con `aria-label`; paginación en
  `<nav aria-label="Páginas de la biblioteca">`; nada de controles sin nombre (lo comprueba la composición
  de `test_web_nombre_y_foco.py`).
- Recuento en región viva (§6.1); la rejilla **no** es viva. Avisos con `role="status"`/`alert` según
  `ui.aviso`.
- Nombres accesibles: «Quitar filtro Tradición: Manga», «Quitar filtro Búsqueda: «noir»», «Limpiar
  todos», «Reintentar». La palabra «Quitar» es visible; el nombre completo va en `aria-label`.
- Teclado: todo con Tab/Enter; foco tras retirar definido (§6.3); sin atajos de un carácter ni `accesskey`.
- No depender solo del color: cada chip lleva su texto y el enlace de retirada es texto subrayado;
  contraste y foco se heredan de `web.css` y los comprueba `test_web_css_contraste`. Las clases nuevas
  (`.filtros-activos`, `.quitar-filtro`, `.limpiar-filtros`) usan solo tokens existentes.
- Móvil: chips en `flex-wrap` (sin columnas ni scroll horizontal); recuento antes de la rejilla.
- **Límites WCAG 2.2 AA:** se acredita el HTML (nombres, roles, `aria-current`, `aria-live`, foco visible)
  con pruebas; lector real y Atrás/Adelante en navegador son **NOT RUN** hasta la pasada manual.

## 11. Sin efectos y privacidad

- Los GET son de **solo lectura**: no escriben en BD, no mueven ni leen ficheros, no llaman a Comic
  Vine/AniList/Tebeosfera/GCD y no disparan el ciclo de descargas.
- Logs: los fallos se registran como `logger.warning("biblioteca.consulta_fallida",
  error=type(exc).__name__)` — **nunca** q, ids ni nombres. El registro de acceso de uvicorn no incluye la
  query desde #361 (`utils/log_acceso.py`); los proxies inversos quedan fuera de esa protección (advertido
  en `SECURITY.md`).
- Sin telemetría (LEGAL.md/CLAUDE.md §5.3); `no-store` en el fragmento para no servir estado viejo.

## 12. Criterios de aceptación (Given/When/Then)

**AC-01 (issue 1) — añadir un filtro conserva los demás.** Given q, tradición, editorial y saga activos,
When se elige un personaje, Then la URL y el resultado conservan esos filtros, añaden `character_id` y
ponen `page=1`; el recuento y la rejilla corresponden a la intersección. *Prueba*: `test_web_library.py`
(parcial con contexto + página) y composición de `test_web_nombre_y_foco.py`.

**AC-02 (issue 2) — retirar uno y limpiar todos.** Given dos filtros, When se pulsa el «Quitar» de uno,
Then desaparece su chip, el otro se conserva, la URL lleva `page=1` y el fragmento empuja la URL de página
de la nueva combinación; When se pulsa «Limpiar todos», Then `/ui/biblioteca?page=1` queda sin filtros y es
una acción distinta de cada chip. *Prueba*: `test_web_library.py` (URLs de chips y `HX-Push-Url`).

**AC-03 (issue 3) — chips y recuento.** Given una petición con filtros, When se pinta el fragmento, Then
los chips aparecen en orden fijo con los textos exactos de §6.2, el recuento de §6.1 está en una región
`aria-live` y la frase fija de la página ya no lleva número. *Prueba*: `test_web_library.py`; la
composición comprueba que el DOM no tiene controles sin nombre y conserva la región viva.

**AC-04 (issue 4) — vacío con salida.** Given una combinación sin resultados, Then el recuento dice
«Ninguna serie coincide con estos filtros.», los chips siguen, aparece «Prueba a quitar algún filtro de los
de arriba.» y se puede retirar o limpiar; Given biblioteca sin filtros y sin series, Then «Tu biblioteca
todavía no tiene series.» con enlace a `/ui/pendientes`. *Prueba*: `test_web_library.py`.

**AC-05 (issue 5) — inválidos y errores.** Given `?publisher_id=no-es-uuid`, `?tradition=inventada`,
`?page=0`, `?page=abc` o `?page=99` con 3 páginas, When se pide página o fragmento, Then 200, se conserva
lo válido, aparece el aviso de §8 y la URL empujada corrige el estado; Given una sesión que lanza
`SQLAlchemyError`, Then 200 con `ui.aviso("warn")` y «Reintentar», sin rejilla, sin vacío y sin
`{"detail":…}`; ninguna de estas peticiones devuelve 422/500. *Prueba*: `test_web_library.py` (incluida la
regresión del 500 histórico).

**AC-06 (issue 6) — accesibilidad.** Given el HTML de página y fragmento, Then cada chip tiene nombre
«Quitar filtro …», «Limpiar todos» y «Reintentar» son enlaces reales, la página actual lleva
`aria-current="page"`, no hay controles sin nombre en el DOM compuesto, el foco tras retirar está definido
en el HTML y no hay columnas nuevas ni dependencia de color. *Prueba*: composición de
`test_web_nombre_y_foco.py` + `test_web_css_contraste.py`. Teclado/lector reales: **NOT RUN**.

**AC-07 (issue 7) — sin efectos.** Given una petición de página o fragmento, When se ejecuta con dobles de
los clientes de fuente y de escritura, Then 0 llamadas externas, 0 escrituras y ningún evento de
`structlog` con q/ids/nombres (solo la clase del error si falla). *Prueba*: doble que falla si se invoca +
handler de structlog.

**AC-08 (issue 8) — paginación y coste.** Given 50 series y filtros, When se piden página y fragmento, Then
24 por página, `COUNT` y `offset/limit` en SQL, ninguna consulta por serie ni facetas, y ≤5 SELECT en
página y ≤5 en fragmento (incluidos los nombres de chips); Then `page>pages` no añade un segundo SELECT.
*Prueba*: `test_web_library.py` con contador de sentencias + `test_series_service.py` para
`pagina_efectiva`. Latencias: **NOT RUN** en la Pi.

**AC-09 (contrato de URL) — recarga, marcadores e historial.** Given un fragmento con filtros, Then
`HX-Push-Url` es exactamente la URL canónica de página (nunca `/resultados`) y `Cache-Control: no-store`;
Then abrir esa URL da página completa con layout y el mismo estado; Then `<main>` lleva `hx-history-elt`;
Then sin HTMX el formulario, chips y paginación navegan a las mismas URLs de página. *Prueba*:
`test_web_library.py` (igualdad de cabecera, layout en la URL empujada, `hx-history-elt`) y composición.
Atrás/Adelante reales: **NOT RUN**.

**AC-10 (personaje/saga) — mecanismo y compatibilidad.** Given el buscador de personaje con q/tradición/
editorial/saga activos, When se teclea, Then la petición lleva `personaje=…` y el contexto
(`hx-include="#filtros"`), y cada resultado es un enlace de página con los cinco filtros y `page=1`; Then
`?q=zzz` sigue respondiendo «Sin coincidencias» y `?personaje=bat` busca por el texto nuevo. *Prueba*:
`test_web_library.py` (enlaces del parcial y compatibilidad).

**AC-11 (cierre documental y regresiones).** Given el diff de la PR, Then `web/library.py` ya no documenta
el reset como aceptado y describe el contrato de URL/chips; Then `docs/BACKLOG.md` tiene la fila `BL-IT01`
(#283, P1, M) en la Épica C con enlaces a ficha y spec; Then hay regresión de (a) conservar filtros al
elegir personaje/saga, (b) `HX-Push-Url` de página y no de fragmento, (c) el 500 histórico de UUID mal
formado; Then la suite completa pasa. *Prueba*: revisión del diff + AC-01/AC-05/AC-09.

## 13. Una PR: archivos, riesgos, DoR y DoD

**Archivos:** `src/zascarr/web/library.py` (validación única, URLs canónicas, cabeceras, contexto, rutas,
endpoints de personaje/saga, docstring); `src/zascarr/services/series.py` (`pagina_efectiva()` y ajuste de
página sin doble consulta, `nombres_de_filtros()` con ≤3 SELECT); `web/templates/biblioteca.html`,
`_rejilla_biblioteca.html`, `_resultados_personaje.html`, `_resultados_saga.html`, nuevo `_campo_q.html`,
`base.html` (`hx-history-elt`) y `_componentes.html` (`region_viva` gana `tabindex="-1"`, spec §6.1);
`static/web.css` (chips y recuento con tokens existentes);
`tests/test_web_library.py`, `tests/test_series_service.py`, `tests/test_web_nombre_y_foco.py`,
`tests/test_web_css_contraste.py`; `docs/BACKLOG.md` (fila `BL-IT01`). Sin migración, sin dependencias.

**Riesgos:** R-1 `HX-Push-Url`/`hx-history-elt`/`autofocus` en htmx 4 no se comportan como se leyó (media/
alto; prueba en navegador real antes de fusionar, plan B foco en destino y URL por enlace real); R-2 la
corrección de página añade un SELECT (media/medio; `pagina_efectiva()`, prueba de contador); R-3 el campo
de título queda viejo al retirar su chip (media/medio; `quitar` + `_campo_q.html` con OOB); R-4 colisión de
`q` en `hx-include` (media/alto; el campo tecleado es `personaje`/`saga`); R-5 lista completa de páginas
genera mucho HTML/foco (media/bajo; no-goal declarado, se reevalúa con datos); R-6 BL-ETQ1 toca las mismas
plantillas (alta/medio; BL-IT01 primero y ETQ1 se rebasa); R-7 un 500 ajeno a `SQLAlchemyError` sigue
pintándose como texto plano en la rejilla (baja/medio; comportamiento global existente, declarado).

**DoR de la tarjeta:** ficha enlazada (hecha, caduca ~2027-01-04); spec aprobada por el PO; textos y
NO-goals de §3/§14 ratificados; sin migración ni dependencias; `Bloqueada = No`; talla M y WIP del MVP.
**DoD de la PR:** AC-01…AC-11 en verde (suite completa), ≤5 SELECT medido en pruebas, docstring y BACKLOG
actualizados, sin JS nuevo ni dependencias, y verificación manual en navegador real (recarga,
Atrás/Adelante, foco, teclado) antes de fusionar; latencia en Pi medida o declarada NOT RUN.

## 14. Trazabilidad, NOT RUN, PO y caducidad

- **Issue → AC:** criterio 1→AC-01; 2→AC-02; 3→AC-03; 4→AC-04; 5→AC-05; 6→AC-06; 7→AC-07; 8→AC-08;
  contrato de URL→AC-09; personaje/saga→AC-10; cierre documental→AC-11. **FR → AC:** FR-01/02→AC-09;
  FR-03→AC-01/02; FR-04→AC-03; FR-05→AC-04; FR-06/07→AC-05; FR-08→AC-10; FR-09→AC-08; FR-10→AC-06;
  FR-11→AC-07; FR-12→AC-05/09.
- **NOT RUN (no medido, no inferido):** Atrás/Adelante y restauración de htmx 4 en navegador real; foco de
  `autofocus` en contenido intercambiado/OOB; anuncio en lector de pantalla; latencia y tamaño de HTML en
  la Pi; chips a 360/390 px; auditoría WCAG 2.2 completa del flujo.
- **Dudas que debe ratificar el PO (no bloquean el contrato técnico, sí el DoR):** D-1 textos exactos de
  §6.1/§6.2/§6.4/§6.5 (cambiarlos exige actualizar sus pruebas); D-2 confirmar los NO-goals de §3, en
  especial que la ventana de paginación queda fuera y que los chips de personaje/saga navegan a página
  completa (sin HTMX) aunque el resto de la barra use HTMX; D-3 orden de fusión frente a BL-ETQ1 (este
  primero).
- **Caducidad: ~2027-01-04**, la de la ficha. Antes hay que revisar el contrato de filtros, la versión de
  htmx y el estado de `docs/BACKLOG.md`. Sin decisión del PO, esta spec no autoriza implementar.
