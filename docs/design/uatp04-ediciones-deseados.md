# Distinguir ediciones homónimas en Deseados (UATP-04 / UXA-13)

> **Estado:** implementada en TDD (task-52, 2026-11-21) siguiendo las recomendaciones D-1…D-5;
> pendiente la ratificación final del PO, la pasada independiente de QA/SecOps y la evidencia de
> navegador **PASS en Chrome** (320/390); evidencia en [`uatp04/resultado-chrome.md`](uatp04/resultado-chrome.md). El benchmark previo (**task-46**, 2026-11-21, solo lectura
> y no versionado) comprobó que los criterios de #1142 **no se cumplían** antes de este corte.
>
> **Insumos:** [#1142 · UATP-04](https://github.com/juanajok/zascarr/issues/1142),
> [#1130 · UXA-13](https://github.com/juanajok/zascarr/issues/1130),
> [#1141 · épica UATP](https://github.com/juanajok/zascarr/issues/1141), el benchmark de producto
> de Deseados ([`benchmark-DESEADOS-2026-11-16.md`](benchmark-DESEADOS-2026-11-16.md)) y la
> evolución de referencia normalizada (migración `0030`,
> [`20261112_0030_referencia_normalizada.py`](../../alembic/versions/20261112_0030_referencia_normalizada.py:46)).
>
> **Base de las referencias de línea:** `origin/main` = **`d5f26df5`** (2026-11-21). El checkout
> de trabajo puede estar en otra rama; el implementador debe ramificar desde `origin/main`.
>
> **Único escritor de este documento:** SPEC.writer. No toca código, tests ni otras docs; la
> implementación y la evidencia son tareas aparte (TDD/QA).

## 1. Problema y resultado esperado

**Problema (verificado en `origin/main`; hallazgos del benchmark task-46):**

| # | Hallazgo | Evidencia |
|---|---|---|
| P-1 | La fila guardada se compone solo con `title` (más el número, si el deseo es por número). Con dos series «Flash» de 1987 y 2011, las dos filas dicen «Flash» y el número no existe: no se distingue la edición | [`web/wishlist.py:60-67`](../../src/zascarr/web/wishlist.py:60) |
| P-2 | El selector ya pinta `title` + `start_year`, pero no usa `reference_name`: el **volumen** de una edición homónima del mismo año se pierde, y la composición no coincide con la ficha | [`_resultados_series_wishlist.html:7`](../../src/zascarr/web/templates/_resultados_series_wishlist.html:7) |
| P-3 | Ni la fila ni el selector enlazan a la identidad elegida. La fila es un `<span>` sin `href`, así que no hay forma de comprobar en la ficha qué serie quedó guardada (ni antes ni después de recargar) | [`_fila_wishlist.html:6`](../../src/zascarr/web/templates/_fila_wishlist.html:6); selector en [`_resultados_series_wishlist.html:7`](../../src/zascarr/web/templates/_resultados_series_wishlist.html:7) |
| P-4 | Los nombres accesibles se repiten entre filas homónimas: `Seleccionar Flash`, `Quitar Flash de Deseados`, `Progreso de Flash`… Un lector de pantalla no puede elegir la de 1987 o la de 2011 | [`_fila_wishlist.html:4`](../../src/zascarr/web/templates/_fila_wishlist.html:4); [`_estado_wishlist.html:9`](../../src/zascarr/web/templates/_estado_wishlist.html:9), `:19`, `:27`, `:36`, `:44`; [`_progreso_wishlist.html:9`](../../src/zascarr/web/templates/_progreso_wishlist.html:9) |
| P-5 | `#resultados-wishlist` no es región viva: al buscar no se anuncia el resultado (ni «Sin coincidencias»). Solo se anuncia el indicador «Buscando series…» | [`wishlist.html:33-35`](../../src/zascarr/web/templates/wishlist.html:33) |
| P-6 | `volver` no conoce Deseados: tras abrir la ficha desde una fila, el enlace dice «Volver a la biblioteca» y no hay contrato de vuelta a `/ui/wishlist` | [`web/retorno.py:143-148`](../../src/zascarr/web/retorno.py:143); [`series_detail.html:34`](../../src/zascarr/web/templates/series_detail.html:34); llamada en [`web/series.py:801`](../../src/zascarr/web/series.py:801) |
| P-7 | `Series.reference_name` ya existe y la ficha ya la muestra con su propio fallback, pero Deseados no la usa: dos composiciones distintas para la misma identidad | [`models/__init__.py:557-561`](../../src/zascarr/models/__init__.py:557); [`series_detail.html:219`](../../src/zascarr/web/templates/series_detail.html:219) |

**Lo que no hay que romper (PASS actual).** La fila es `flex-wrap` y no desborda a 390 px
([`web.css:769-777`](../../src/zascarr/static/web.css:769)); el estado es texto + icono, no solo
color (`ui.chip` en [`_estado_wishlist.html:1`](../../src/zascarr/web/templates/_estado_wishlist.html:1));
el progreso ya refresca en una región viva propia
([`wishlist.html:38-39`](../../src/zascarr/web/templates/wishlist.html:38)); y el enlace de
«Buscar ahora» no debe leer relaciones sin precargar (regresión del 2026-11-17,
[`tests/test_web_wishlist.py:659`](../../tests/test_web_wishlist.py:659)). UATP-04 conserva todo eso.

**Resultado esperado.** El selector y la fila guardada muestran la **misma** referencia humana
(`reference_name`, con `title` como fallback) y, en el fixture Flash, se ve el año. La fila enlaza
a la ficha de la serie seleccionada con un `href` de servidor que sobrevive a la recarga. Todos los
nombres accesibles de una fila y el del progreso llevan esa referencia, así que dos ediciones
homónimas nunca ofrecen dos acciones con el mismo nombre. La búsqueda anuncia resultados y
ausencia de resultados. A 320 y 390 px la referencia se ve completa y el estado sigue legible.
Abrir la ficha desde Deseados y volver devuelve a Deseados. Sin JS nuevo, sin migración, sin
cambiar búsqueda ni orquestador.

## 2. Alcance / no alcance

**Dentro:**

| Pieza | Cambio |
|---|---|
| [`web/wishlist.py`](../../src/zascarr/web/wishlist.py) | `_row` pasa a exponer **una** `referencia` y un `enlace_ficha` (D-1, D-2, D-3); el progreso reutiliza `referencia`. |
| [`web/templates/_fila_wishlist.html`](../../src/zascarr/web/templates/_fila_wishlist.html) | La referencia es un `<a href="/ui/series/{id}?volver=…">` (o texto si no hay serie); checkbox con `aria-label` completo. |
| [`web/templates/_estado_wishlist.html`](../../src/zascarr/web/templates/_estado_wishlist.html) | Los cinco `aria-label` usan `row.referencia`; texto visible y aspecto no cambian. |
| [`web/templates/_progreso_wishlist.html`](../../src/zascarr/web/templates/_progreso_wishlist.html) | Título y `aria-label` del `<progress>` usan `fila.referencia`. |
| [`web/templates/_resultados_series_wishlist.html`](../../src/zascarr/web/templates/_resultados_series_wishlist.html) | Referencia con la misma composición y nombre accesible del botón «Añadir» distinto por resultado. |
| [`web/templates/wishlist.html`](../../src/zascarr/web/templates/wishlist.html) | `#resultados-wishlist` con `aria-live="polite"` (D-4). |
| [`web/retorno.py`](../../src/zascarr/web/retorno.py) | `volver` admite la ruta exacta `/ui/wishlist` y un constructor de URL para la fila (D-5). |
| [`web/templates/series_detail.html`](../../src/zascarr/web/templates/series_detail.html) | La etiqueta del enlace de vuelta dice «a Deseados» cuando el destino es `/ui/wishlist`. |
| [`static/web.css`](../../src/zascarr/static/web.css) | Subrayado y zona táctil ≥ 24 px del enlace dentro de la fila; corte de palabras largo; sin truncar. |
| Tests | Casos T-1…T-11 de §7. |

**Fuera de alcance (explícito):**

- **Buscar por año, volumen o referencia.** `WishlistService.search_series` sigue buscando solo por
  `Series.title` ([`services/wishlist.py:45-58`](../../src/zascarr/services/wishlist.py:45)). Buscar
  «Flash 1987» y que aparezca no es UATP-04.
- **Orquestador, candidatos, tokens, envío de descargas y estados del deseo.** No cambia
  `preview_candidates`, `send_manual_candidate`, `_ESTADO_LABEL` ni la máquina de estados.
- **API, modelo y base de datos.** Sin campos, sin migración, sin cambio de contrato API. El
  `reference_name` es columna calculada existente; no se rellena ni se inventa nada nuevo.
- **Enlace a la ficha del número.** Decisión D-2; hoy los deseos por número solo entran por API y
  la ficha de número no tiene contrato `volver`.
- **Anuncio de la fila añadida** (el `#wishlist-list` no es región viva) y **foco/scroll al volver**:
  se registran como limitaciones, no se implementan aquí.
- Otras pantallas: `_alta_resultado.html` (Descubrir), panel de fuentes, dashboard y `_serie_creada.html`
  repiten «Añadir a deseados» y no forman parte de este contrato.
- Lector de pantalla real, Safari/iOS y dispositivos físicos: **NOT RUN**, nunca PASS.

## 3. Contrato

### 3.1 Composición única (servidor)

Una sola función compone la referencia: `_row`, y **todos** los fragmentos de la fila la consumen.
Nada de formatear `title` + año en Jinja ni en JS.

```text
series = item.series or (item.issue.series if item.issue else None)
referencia = (series.reference_name or series.title) if series else "?"
si item.issue:
    numero = item.issue.number_key or item.issue.issue_number
    si numero: referencia = referencia + " #" + numero
return { "item", "referencia", "enlace_ficha", … }
```

Reglas:

1. `reference_name` ya incluye año y volumen **solo cuando constan** (función SQL
   `f_series_reference(title, start_year, volume)`,
   [`20261112_0030_referencia_normalizada.py:46-62`](../../alembic/versions/20261112_0030_referencia_normalizada.py:46)).
   Si es `NULL`, se usa `title`; nunca se rellena el año «a ojo» ni desde la carpeta.
2. `enlace_ficha` es la URL de la ficha de **esa** serie (D-3) o `None` si no hay serie. Para un
   deseo por número se enlaza a la serie (D-2).
3. La clave `titulo` desaparece del dict (o queda como alias exacto de `referencia`; jamás otra
   composición). Los tests que hoy esperan `row["titulo"]` se actualizan a `referencia`.
4. El progreso (`_progreso_wishlist.html`) usa `fila.referencia`; el panel de candidatos **no**
   se toca: su ruta no puede leer `item.series` sin precargar (regresión 2026-11-17,
   [`wishlist.py:293-295`](../../src/zascarr/web/wishlist.py:293)) y su etiqueta no forma parte de AC.

### 3.2 Fila guardada y enlace (D-3)

```html
<span class="wishlist-title">
  {% if row.enlace_ficha %}<a href="{{ row.enlace_ficha }}">{{ row.referencia }}<span class="sr"> — ver la ficha de la serie</span></a>
  {% else %}{{ row.referencia }}{% endif %}
</span>
```

- El `href` se renderiza en el servidor. Aparece igual en la página (`GET /ui/wishlist`), en el
  fragmento de `POST /ui/wishlist/anadir` y después de recargar; no depende de JS, de sesión ni de
  estado en memoria.
- `volver` se construye con el helper de D-5: `/ui/series/{id}?volver=%2Fui%2Fwishlist`.
- Sin serie no hay enlace: se muestra `?` (y el número, si el deseo es por número) y no se
  inventa destino.
- El selector **no** convierte el nombre en enlace: hacerlo abandonaría la búsqueda en curso. La
  verificación de identidad se hace en la fila ya guardada (que es lo que pide #1142).

### 3.3 Selector

- Referencia: `{% set referencia = s.reference_name or s.title %}` y se pinta en
  `<span class="series-name">`. Misma composición que §3.1.
- Botón «Añadir a deseados»: nombre accesible **distinto por resultado** sin `aria-label`, para
  que el cambio de estado no lo deje mintiendo. El texto visible va en un hijo que se sustituye;
  un `sr` aporta la referencia:

  ```html
  <button ...>
    <span data-texto>Añadir a deseados</span><span class="sr">: {{ referencia }}</span>
  </button>
  ```

  Los dos `hx-on` existentes actualizan **solo** `[data-texto]` (`'Añadiendo…'`, `'Añadido'`,
  `'No se pudo añadir'`) y conservan `this.disabled`. Nombres resultantes: «Añadir a deseados:
  Flash (1987)» → «Añadido: Flash (1987)» → «No se pudo añadir: Flash (1987)».
- Sin coincidencias se mantiene «Sin coincidencias.» para que también se anuncie (§3.4).

### 3.4 Región viva de resultados (D-4)

[`wishlist.html:35`](../../src/zascarr/web/templates/wishlist.html:35) pasa a:

```html
<div id="resultados-wishlist" class="series-results" aria-live="polite"></div>
```

- Mismo patrón que los otros buscadores locales
  ([`_filtros_panel_campos.html:66`](../../src/zascarr/web/templates/_filtros_panel_campos.html:66)).
- El contenedor existe **vacío desde la carga**; así se anuncia el cambio al insertar el fragmento.
- No se añade `role="status"` ni se anida en otra región viva: el indicador «Buscando series…» ya
  tiene `role="status"` ([`wishlist.html:33-34`](../../src/zascarr/web/templates/wishlist.html:33));
  duplicarlo anunciaría dos veces.

### 3.5 Nombres accesibles (antes → después)

| Elemento | Hoy (dos filas «Flash») | Después |
|---|---|---|
| Checkbox de selección | `Seleccionar Flash` | `Seleccionar Flash (1987)` |
| «Reintentar» | `Reintentar la búsqueda de Flash` | `Reintentar la búsqueda de Flash (1987)` |
| «Buscar ahora» | `Buscar ahora Flash` | `Buscar ahora Flash (1987)` |
| «Cancelar búsqueda» | `Cancelar la búsqueda de Flash` | `Cancelar la búsqueda de Flash (1987)` |
| «Ya lo tengo» | `Marcar Flash como conseguido` | `Marcar Flash (1987) como conseguido` |
| «Quitar» | `Quitar Flash de Deseados` | `Quitar Flash (1987) de Deseados` |
| Progreso | `Progreso de Flash` | `Progreso de Flash (1987)` |
| «Añadir a deseados» (selector) | texto repetido sin referencia | `Añadir a deseados: Flash (1987)` |

Todos sustituyen `row.titulo`/`fila.titulo` por `row.referencia`/`fila.referencia`; el texto
visible de los botones no cambia. El estado visible sigue siendo `ui.chip` (texto + icono) y el
motivo de D9 se mantiene tal cual.

### 3.6 Progreso

`_progreso_wishlist.html`: título y `aria-label="Progreso de {{ fila.referencia }}"`. La sección
conserva su `aria-label="Descargas en curso"` y el refresco cada 30 s; no se añaden regiones vivas
nuevas (el contenedor `#wishlist-progreso` ya la tiene).

### 3.7 Retorno a Deseados (D-5)

[`web/retorno.py`](../../src/zascarr/web/retorno.py) gana una constante y un constructor:

```text
_RUTA_DE_DESEADOS = "/ui/wishlist"

def url_de_ficha_desde_deseos(series_id):
    sid = str(UUID(str(series_id)))
    return f"/ui/series/{sid}?volver={quote(_RUTA_DE_DESEADOS, safe='')}"
```

`volver_segura` acepta **solo la forma exacta** `/ui/wishlist` (sin query, sin fragmento, sin
barra final). Cualquier otra forma cae al comportamiento actual (`None` → la ficha ofrece
`/ui/biblioteca`):

```text
if partes.path == _RUTA_DE_DESEADOS:
    return valor if valor == _RUTA_DE_DESEADOS else None
```

La etiqueta de [`series_detail.html:34`](../../src/zascarr/web/templates/series_detail.html:34)
añade la rama `volver == '/ui/wishlist'` → «← Volver a Deseados»; el resto de destinos conserva
«a la biblioteca»/«a la colección».

Invariantes de seguridad (hereda los de UATP-01/02 y SecOps los revalida):

- solo ruta local exacta: nada de `//`, `%` en la ruta, controles, espacios, barra invertida,
  `..`, query, fragmento ni redirección externa;
- `volver` se sigue pintando con autoescape en `href`; un valor manipulado no sale de `/ui/...`;
- no se añade historial paralelo, cookie, JS ni estado de sesión.

Si el PO rechaza D-5, se elimina el `?volver` del enlace de la fila y AC-7; el resto del contrato
no depende de ello (el botón «Atrás» del navegador sigue volviendo a Deseados).

### 3.8 Móvil y CSS

- `.wishlist-title` conserva `flex: 1 1 10rem`, gana `overflow-wrap: anywhere` (referencias
  largas) y **no** usa `text-overflow: ellipsis`, `white-space: nowrap` ni recorte.
- Dentro de la fila, `a` se subraya (el color es `inherit` global; el subrayado cumple 1.4.1):
  `.wishlist-title a { text-decoration: underline; text-underline-offset: 2px; }`.
- En el bloque U16 (`max-width: 860px` / `pointer: coarse`,
  [`web.css:1603-1608`](../../src/zascarr/static/web.css:1603)), el enlace de la fila mide
  `min-height: 24px` (mismo criterio que `.metric-detail a`); los botones siguen a 44 px.
- No se toca el reparto flex ni el orden de los elementos; no aparece scroll horizontal a 320 px.

## 4. Decisiones (recomendaciones de SPEC.writer; pendientes de PO)

| ID | Decisión | Recomendación | Alternativa descartada |
|---|---|---|---|
| **D-1** | Composición | `reference_name` con fallback `title`, calculada solo en `_row`; selector, fila, progreso y nombres accesibles la consumen | Poner `title` + `start_year` en Jinja (dos fuentes); añadir editorial para desambiguar (no está en la ficha ni en `reference_name`); deducir el año de la carpeta (**inventa**) |
| **D-2** | Deseo por número | Sufijo `#number_key` (fallback `issue_number`) y enlace a la **serie** | Enlazar a la ficha del número: hoy no tiene `volver` y el deseo por número solo entra por API; sería otra historia |
| **D-3** | Enlace de fila | `<a href>` de servidor, misma pestaña, con `volver`; el selector no navega | `target="_blank"` (rompe el flujo de vuelta); JS/localStorage (no hay JS propio); enlazar en el selector (pierde la búsqueda) |
| **D-4** | Anuncio de resultados | `aria-live="polite"` en `#resultados-wishlist`, sin `role` extra | `ui.region_viva` (añade `tabindex`/atomic y no es el patrón de los otros buscadores); no anunciar (P-5 sigue abierto) |
| **D-5** | Retorno | Incluir `/ui/wishlist` exacto en `volver_segura` + helper y etiqueta «Volver a Deseados» | Dejarlo fuera: el enlace funciona, pero «Volver» miente y la continuidad de la épica se rompe; el coste es 1 ruta exacta y 2 tests |

## 5. Fuera de alcance

Además de lo listado en §2: no se toca `WishlistService.search_series`, ni el índice/orden del
selector, ni `_candidatos_wishlist.html`, ni `WishlistStatus`, ni la API, ni `docs/BACKLOG.md`.
La documentación de inventario (`ui-migracion.md`) y `docs/TESTING_E2E.md` los actualiza la
implementación si su contrato cambia; este documento es el contrato de UATP-04.

## 6. Criterios de aceptación

- **AC-1 (composición única).** Con `reference_name`, la fila, el selector, el progreso y todos los
  `aria-label` de la fila muestran exactamente ese valor; con `NULL`, muestran `title`. Nunca se
  añade un año, volumen o editorial que la serie no declare.
- **AC-2 (fixture Flash).** Con dos series «Flash» de 1987 y 2011, el selector muestra
  «Flash (1987)» y «Flash (2011)», y la fila guardada de cada una muestra el mismo texto.
- **AC-3 (enlace persistente).** La fila contiene un `<a href>` de servidor a `/ui/series/{id}`
  (con `volver`), también en la respuesta de `/anadir` y tras recargar; no depende de JS ni de
  sesión. Sin serie no hay `href` inventado.
- **AC-4 (nombres accesibles).** Para dos filas homónimas con distinto año, los nombres
  accesibles de checkbox, reintentar, buscar ahora, cancelar, marcar, quitar y progreso incluyen
  la referencia (el año, o el volumen cuando el año falta) y no hay dos iguales entre filas.
- **AC-5 (región viva).** `#resultados-wishlist` declara `aria-live="polite"` desde la carga; al
  buscar se anuncia el resultado o «Sin coincidencias.», sin una segunda región viva anidada.
- **AC-6 (selector accesible).** Cada botón «Añadir a deseados» tiene un nombre accesible con su
  referencia; tras añadir, el nombre accesible incluye «Añadido» y la misma referencia, y no se
  confunde con otro resultado.
- **AC-7 (retorno, D-5).** Desde una fila se abre la ficha y «← Volver a Deseados» regresa a
  `/ui/wishlist`; `volver_segura` acepta solo la forma exacta y rechaza query, fragmento, barra
  final, `//` y rutas ajenas.
- **AC-8 (móvil y estado).** A 320 y 390 px no hay scroll horizontal, la referencia se ve completa
  sin recorte ni elipsis, el enlace es alcanzable (≥ 24 px de alto) y el chip de estado con su
  motivo siguen visibles y legibles.
- **AC-9 (sin efectos colaterales).** Sin migración, sin cambio de modelo/API, sin tocar
  `search_series`, `preview_candidates`, tokens ni estados del deseo; los tests existentes de
  Deseados, retorno, ficha y CSS siguen PASS.

## 7. Plan de pruebas

| ID | Archivo(s) | Qué fija |
|---|---|---|
| T-1 | [`tests/test_web_wishlist.py`](../../tests/test_web_wishlist.py) | `_row` con `reference_name`; fallback `title`; sin año inventado; sufijo `#number_key` y fallback; `enlace_ficha` con y sin serie. |
| T-2 | `tests/test_web_wishlist.py` | Índice con Flash (1987) y Flash (2011): dos referencias visibles, dos `href` distintos con `volver`, y `aria-label` de fila distintos (checkbox y acciones). |
| T-3 | `tests/test_web_wishlist.py` | `POST /ui/wishlist/anadir` devuelve la fila con la misma referencia y `href` (sobrevive a la inserción HTMX y a recargar). |
| T-4 | `tests/test_web_wishlist.py` | `GET /ui/wishlist/buscar-serie`: referencias del selector y nombre accesible del botón «Añadir» distinto; el `hx-on` actualiza `[data-texto]` y conserva `this.disabled`. |
| T-5 | `tests/test_web_wishlist.py` | `#resultados-wishlist` con `aria-live="polite"`; fragmento «Sin coincidencias.» presente; sin `role="status"` añadido. |
| T-6 | `tests/test_web_wishlist.py` | Progreso con dos Flash: títulos y `aria-label` del `<progress>` distintos; no cambia el número de consultas a Transmission. |
| T-7 | [`tests/test_web_retorno.py`](../../tests/test_web_retorno.py) | `url_de_ficha_desde_deseos` produce `/ui/series/{id}?volver=%2Fui%2Fwishlist`; acepta solo `/ui/wishlist` exacto; rechaza `?x`, `#f`, `/`, `//` y rutas ajenas. |
| T-8 | [`tests/test_web_series.py`](../../tests/test_web_series.py) | Ficha con `volver=/ui/wishlist`: `href="/ui/wishlist"` y «Volver a Deseados»; un valor manipulado cae a Biblioteca. |
| T-9 | [`tests/test_web_css_contraste.py`](../../tests/test_web_css_contraste.py) | `.wishlist-title` con `overflow-wrap: anywhere`; `a` subrayado; enlace de fila ≥ 24 px en el bloque U16; sin `ellipsis`/`nowrap` en la referencia. |
| T-10 | [`tests/test_wishlist_series_pg.py`](../../tests/test_wishlist_series_pg.py) (**PG opcional**, skip sin `TEST_DATABASE_URL`) | Con Postgres real, dos series «Flash» 1987/2011 calculan `Flash (1987)`/`Flash (2011)` y `_row` devuelve esas referencias. |
| T-11 | Evidencia de navegador (§8) | 320/390 px, teclado y recarga; **PASS Chrome** en [`uatp04/resultado-chrome.md`](uatp04/resultado-chrome.md). |

Comandos mínimos:

```bash
pytest -q tests/test_web_wishlist.py tests/test_web_retorno.py \
          tests/test_web_series.py tests/test_web_css_contraste.py
pytest -q tests/test_wishlist_series_pg.py   # solo con TEST_DATABASE_URL
ruff check src/ tests/
```

No se admite como PASS un test que solo compruebe la cadena `Flash` en todo el HTML: la
referencia debe afirmarse sobre el `href`, el texto de la fila y el `aria-label` concretos.

## 8. Evidencia de cierre

1. Salida de los comandos de §7 y SHA verificado (`origin/main` de partida + commits del PR).
2. Captura en Chrome (emulación de viewport) a **320×568** y **390×844** con dos filas Flash
   distintas: referencia completa, sin scroll horizontal (`scrollWidth <= clientWidth`), chip y
   motivo visibles, enlace enfocable con Tab.
3. Fragmento de DOM con los dos `href` (UUID distintos + `volver`) y los `aria-label` de la tabla
   de §3.5; el mismo fragmento tras recargar.
4. Recorrido: selector → «Añadir» → fila → enlace a ficha → «Volver a Deseados» → fila; y
   recarga de `/ui/wishlist` conservando el enlace.
5. **NOT RUN** hasta que se ejecute: lector de pantalla real, Safari/iOS, dispositivo físico y
   prueba con personas (UATP-09). No se declaran PASS.
6. La «Prueba de cierre» de #1142 remite a `replica-a1/A1/resultado.md` (evidencia del piloto UAT,
   fuera de este repo). QA adjunta esa réplica o reproduce el fixture Flash (1987)/Flash (2011) con
   su propio registro; si no tiene acceso a la evidencia original, UATP-04 se queda **NOT RUN** y
   no se cierra.

## 9. Riesgos y limitaciones

- **Dos series idénticas sin año ni volumen.** `reference_name` sería igual para ambas y los
  nombres accesibles seguirían coincidiendo. No se resuelve inventando datos; los distingue el
  destino del enlace y la ficha. Es una limitación de datos, se registra y no se maquilla.
- **`aria-live` sobre la lista completa** puede resultar verboso con 20 resultados. Se acepta por
  coherencia con los otros buscadores (ya hay debounce de 400 ms); si QA lo mide como ruido, la
  mejora sería un contador en región viva aparte, no un cambio de este contrato.
- **Añadir una fila no se anuncia** (el `#wishlist-list` no es región viva) y **volver no restaura
  foco/scroll**: fuera de alcance; posibles seguimientos de UXA-13.
- **D-5 amplía una allowlist** ya auditada por SecOps en UATP-01/02. La ruta exacta no admite query
  ni fragmento; aun así, la pasada de seguridad del SHA final debe confirmarla.
- **Deseo por número solo por API.** Si aparece una UI que cree deseos por número, D-2 (enlace a la
  serie) se revisa; hoy es la opción que no exige tocar la ficha de número.

## 10. Pendiente del PO

1. Ratificar D-1…D-5: la implementación (task-52) aplica las recomendaciones; si el PO retira D-5,
   se quita el `?volver` del enlace de fila y AC-7, sin tocar el resto.
2. Confirmar que «año o volumen» es identificación suficiente para #1142, sin añadir editorial a
   la composición.
3. Confirmar que el enlace de fila va a la serie también para deseos por número (D-2).

**Pendiente de verificación:** T-10 con Postgres real (skip sin `TEST_DATABASE_URL`) y la evidencia
de navegador/lector de pantalla de §8, que queda **NOT RUN** hasta ejecutarse.
