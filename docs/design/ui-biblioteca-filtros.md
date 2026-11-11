# UX — Biblioteca: filtros, orden y vista

> **Estado:** diseño UX previo a implementación. **No toca `src/` ni `tests/`**, no crea rutas,
> plantillas, migraciones ni servicios. Fija la jerarquía, el panel, los chips, el contador, el
> comportamiento móvil, los estados y el plan por rebanadas.
> **Base:** `origin/main` = `8b1969c7138c35882a33885c844ca16babd0fb9e` (2026-11-11), worktree
> `.squad/wt-bib-ui`, rama `docs/bib-filtros-ui`.
> **Insumos:** `src/zascarr/web/templates/biblioteca.html`; `src/zascarr/web/library.py`;
> `_rejilla_biblioteca.html`; `_campo_q.html`; `static/web.css` (`filter-bar`, `library-vistas`,
> `filtros-activos`); especificación y benchmark BL-IT01 (#283) ya vigentes; historia de orden
> (#628); `CLAUDE.md` §6.
> **Benchmark nuevo:** **`docs/design/benchmark-biblioteca-filtros.md` no existe al redactar**
> (revisado en `main` y en el worktree de benchmark en curso). No se puede alinear todavía; se
> conserva el contrato vigente de BL-IT01 y se deja una sección de contraste pendiente (§13). Si
> aparece, sus reglas mandan sobre lo que aquí sea solo una elección de layout.
> **Navegador, lector de pantalla, 320 px medidos y Pi:** **NOT RUN**.

---

## 0. Problema y resumen

La Biblioteca tiene hoy **dos barras** y siete controles visibles: título, tradición, editorial,
lectura, orden + «Aplicar orden», etiquetas, más personaje y saga. El resultado es una pantalla que
parece un formulario antes que una biblioteca. La búsqueda de título compite con tres buscadores
más; el orden tiene su propio botón; la vista vive fuera y los filtros activos no tienen una
jerarquía clara.

**Propuesta:** una **barra única de biblioteca** con una sola búsqueda visible, contador, botón
**«Filtros»**, orden compacto y vista compacta. Los filtros avanzados viven en un **panel
desplegable** (`<details>`) con etiquetas visibles; los filtros activos se ven como chips
removibles debajo. La barra se lee en una línea; en móvil la búsqueda ocupa su propia fila y la
barra de acciones sigue siendo una línea.

**Jerarquía en seis líneas:**

1. **Siempre visible:** título de la pantalla y frase de entrada.
2. **Siempre visible:** una única búsqueda por título.
3. **Siempre visible:** contador de resultados + botón **«Filtros»** con su cuenta.
4. **Siempre visible:** **orden** compacto y **vista** compacta, en la misma línea de acciones.
5. **Plegado en el panel «Filtros»:** tradición, editorial, lectura, personaje, saga y etiquetas.
6. **Debajo:** chips de filtros activos con «Quitar» + «Limpiar filtros», y la rejilla.

**Presupuesto de entrada:** la frase de entrada tiene **9 palabras** (≤20). No se añade una segunda
frase de entrada; el panel usa etiquetas, no párrafos.

---

## 1. Jerarquía de la pantalla

### 1.1 Cabecera

- **H1 «Biblioteca»** (Anton, 1 palabra).
- Entrada: **«Busca por título y acota el resto desde «Filtros».»** (9 palabras).
- Columna secundaria de cabecera: el enlace actual
  **«Leer la información de mis archivos»** sale de la zona de filtros y se queda como enlace
  secundario junto al título. No es un filtro y no compite con la barra.
- No se añade botón principal: la Biblioteca es una pantalla de lectura y acotación; la única
  acción de escritura de la página sigue siendo el enlace a la lectura de archivos.

### 1.2 Barra de biblioteca

Un solo formulario GET/HTMX, con `hx-get="/ui/biblioteca/resultados"`, `hx-target="#rejilla"` y
`hx-swap="innerHTML"`, organizado en dos zonas:

**Búsqueda (primera fila en móvil, inline en escritorio):**
- Campo único **«Buscar por título…»**, etiqueta accesible «Buscar por título»; envía con Enter y
  con el cambio del formulario (comportamiento actual).
- No hay un segundo campo de búsqueda visible: personaje, saga y etiquetas son **búsquedas por
  campo dentro del panel**. Se descarta un buscador único con selector de ámbito porque obligaría a
  cambiar de endpoint/sugerencias y haría ambiguo qué se está buscando; la búsqueda por título es
  la principal y las otras son avanzadas.

**Acciones (una fila):**
1. **Contador** estable, región viva (§4).
2. **«Filtros»** con cuenta: `Filtros` o `Filtros (3)`; abre el panel.
3. **Orden** compacto: `<select>` nativo con etiqueta accesible «Ordenar por».
4. **Vista** compacta: un único control que alterna tarjetas/lista (§5).

En escritorio la búsqueda ocupa el espacio flexible de la izquierda y las acciones quedan a la
derecha, todo en una línea. En móvil la búsqueda ocupa su propia fila completa y las acciones
siguen en **una sola línea** debajo. «Filtros» pasa a icono con cuenta en móvil; su nombre accesible
es explícito. Nada de lo que filtra desaparece: solo se pliega en el panel y se compactan las
etiquetas.

### 1.3 Panel «Filtros»

- Se implementa con **`<details>` + `<summary>`** nativo (sin JS nuevo). El `summary` es el disparador
  de la barra; el panel se abre debajo de la barra.
- En escritorio, el panel es un **desplegable** de ancho completo bajo la barra, en dos columnas,
  con sombra/canto de panel; no desplaza la rejilla.
- En móvil, el panel es una **hoja/panel de ancho completo** bajo la barra, con altura máxima y
  scroll interno; no hay modal ni trampa de foco.
- Contenido del panel:
  - **Tradición** (select, «Todas las tradiciones»).
  - **Editorial** (select, «Todas las editoriales», solo si hay editoriales).
  - **Lectura** (select, «Toda la lectura» / «Con leídos» / «Leyendo» / «Sin leídos»).
  - **Personaje** (búsqueda con sugerencias, solo biblioteca local).
  - **Saga** (búsqueda con sugerencias, solo biblioteca local).
  - **Etiquetas** (búsqueda con sugerencias).
- **Los filtros se aplican al cambiarlos** (comportamiento actual del formulario). El panel no
  necesita un botón «Aplicar» para el uso normal; se incluye un **`<noscript>` «Aplicar filtros»**
  como salida sin HTMX. No se añade un botón principal dentro del panel ni a la barra.
- El panel **no contiene orden ni vista**: esos dos viven en la barra, junto al contador, para no
  competir con los filtros.
- **Sugerencias:** los buscadores de personaje/saga/etiqueta reutilizan sus endpoints y parciales
  actuales; se muestran dentro del panel, con `aria-live` y sin consultar fuentes externas.

### 1.4 Chips y contador

- Debajo de la barra/panel, si hay filtros: una fila de chips con su «Quitar» y **«Limpiar filtros»**.
- El contador vive en la barra, **no** en la rejilla: permanece visible mientras se abre el panel y
  se actualiza por OOB.
- La rejilla sigue siendo el único destino del intercambio; los chips viven dentro de `#rejilla`
  para actualizarse con ella.

### 1.5 Comicinfo

- El enlace **«Leer la información de mis archivos»** se mueve a la cabecera, junto al título, como
  enlace secundario. No se elimina ni cambia su comportamiento; solo deja de ocupar una fila de la
  zona de filtros.

---

## 2. Wireframes

### 2.1 Escritorio, panel cerrado

```
┌─ 1200 px ─────────────────────────────────────────────────────────────┐
│ BIBLIOTECA                                      Leer la información… │
│ Busca por título y acota el resto desde «Filtros».                    │
│                                                                        │
│ [Buscar por título…………………] [12 series] [Filtros (3)] [Título A-Z ▾] [⊞]│
│                                                                        │
│ [Búsqueda: «noir» ×] [Tradición: Manga ×] [Personaje: Batman ×]       │
│ [Limpiar filtros]                                                      │
│                                                                        │
│ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐                │
│ │        │ │        │ │        │ │        │ │        │                │
│ └────────┘ └────────┘ └────────┘ └────────┘ └────────┘                │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Escritorio, panel abierto

```
┌─ 1200 px ─────────────────────────────────────────────────────────────┐
│ [Buscar por título…………………] [12 series] [Filtros (3)] [Título A-Z ▾] [⊞]│
│ ┌─ Filtros ──────────────────────────────────────────────────────────┐ │
│ │ Tradición [Todas las tradiciones ▾]  Lectura [Toda la lectura ▾]   │ │
│ │ Editorial [Todas las editoriales ▾]                                │ │
│ │ Personaje [Buscar personaje…]   Saga [Buscar saga…]                │ │
│ │ Etiquetas [Buscar por etiqueta…]                                   │ │
│ │ Los filtros se aplican al cambiarlos.                              │ │
│ │ <noscript> [Aplicar filtros] </noscript>                           │ │
│ └───────────────────────────────────────────────────────────────────┘ │
│ [Búsqueda: «noir» ×] [Tradición: Manga ×] [Limpiar filtros]           │
│                                                                        │
│ [rejilla]                                                              │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Móvil 320 px, panel cerrado

```
┌─ 320 px ──────────────────────────────┐
│ BIBLIOTECA                            │
│ Busca por título y acota el resto…    │
│ [Leer la información…]                │
│                                       │
│ [ Buscar por título……………… ]          │
│ [12 series] [Filtros (3)] [Título A-Z ▾] [⊞] │
│                                       │
│ [Búsqueda ×] [Manga ×]                 │
│ [Limpiar filtros]                     │
│                                       │
│ [portada] [portada]                   │
└───────────────────────────────────────┘
```

- La primera fila es la búsqueda; la segunda, las acciones, en una línea.
- En móvil, «Filtros (3)» conserva texto y cuenta; la vista es un icono con nombre accesible
  «Ver como lista»/«Ver como tarjetas»; el orden muestra una etiqueta corta.
- El contador visible es **«12 series»**; el texto completo para lectores de pantalla es
  «12 series coinciden con estos filtros.» (o «12 series catalogadas.» sin filtros).

### 2.4 Móvil, panel abierto

```
┌─ 320 px ──────────────────────────────┐
│ [ Buscar por título……………… ]          │
│ [12 series] [Filtros (3)] [Título A-Z ▾] [⊞] │
│ ┌─ Filtros ────────────────────────┐  │
│ │ Tradición [Todas ▾]              │  │
│ │ Editorial [Todas ▾]              │  │
│ │ Lectura [Toda ▾]                 │  │
│ │ Personaje [Buscar…]              │  │
│ │ Saga [Buscar…]                   │  │
│ │ Etiquetas [Buscar…]              │  │
│ │ (scroll interno)                 │  │
│ └──────────────────────────────────┘  │
└───────────────────────────────────────┘
```

- El panel es una hoja de ancho completo, con altura máxima y scroll; se cierra con el mismo
  `summary` «Filtros», que queda visible en la barra.
- No hay backdrop ni modal: es un desplegable/hoja no modal.

---

## 3. Panel: comportamiento y accesibilidad

### 3.1 Disparador y estado

- `<details id="panel-filtros">` con `<summary>` es el control; el estado expandido/colapsado lo
  comunica el elemento de forma nativa (equivale a `aria-expanded`). Se añade
  `aria-controls="filtros-campos"` al `summary` y un `id` al contenido.
- Si la implementación prefiere un `<button>` para una hoja, deberá llevar **`aria-expanded`** y
  `aria-controls`; no se admite un toggle que dependa de JavaScript nuevo.
- El botón/`summary` muestra **«Filtros»**; si hay filtros activos, **«Filtros (N)»**, con nombre
  accesible «Filtros, N activos».
- **Abrir:** el foco se queda en el `summary` (no salta al primer campo); Tab entra en el panel.
- **Cerrar:** el foco vuelve/queda en el `summary`; no se mueve a la rejilla.
- **Escape:** `<details>` nativo no cierra con Escape; se documenta como límite aceptado. No se
  añade JavaScript solo para eso.

### 3.2 Foco dentro del panel

- Al abrir, el orden de tabulación es: Tradición → Editorial → Lectura → Personaje → Saga →
  Etiquetas → (botón de sugerencia/elegido) → `Aplicar` (solo `<noscript>`) → `summary` de cierre.
- Las sugerencias de personaje/saga/etiqueta se anuncian en una región `aria-live`; el foco no se
  roba al aparecer.
- Al aplicar un filtro (cambio automático), el foco se queda en el control que se acaba de usar;
  el contador anuncia el nuevo resultado.
- Al quitar un chip fuera del panel, el foco va al contenedor de chips (comportamiento actual); los
  valores del panel se sincronizan por OOB para que al abrirlo no muestre estados viejos.

### 3.3 Sin JavaScript

- El formulario conserva un GET normal y el `<noscript>` ofrece **«Aplicar filtros»**.
- Los enlaces de resultados de personaje/saga y de etiquetas conservan su `href` de página
  completa.
- El panel es `<details>`: abre y cierra sin JS.
- No se usa `hx-confirm`, ni diálogos nativos, ni `onclick`.

---

## 4. Contador y filtros activos

### 4.1 Contador

- **Siempre visible en la barra**, fuera de `#rejilla`; el fragmento lo actualiza con
  `hx-swap-oob` (región estable, `role="status"`, `aria-live="polite"`, `aria-atomic="true"`).
- Texto visible corto: **«12 series»**; en singular **«1 serie»**; cero **«0 series»**. El visible
  va `aria-hidden="true"` para no duplicar la lectura.
- Texto completo para el anuncio, dentro de la región viva (`sr`):
  - sin filtros: «12 series catalogadas.»
  - con filtros: «12 series coinciden con estos filtros.»
  - sin filtros y 0: «Tu biblioteca todavía no tiene series.»
  - con filtros y 0: «Ninguna serie coincide con estos filtros.»
- El contador no se duplica en la rejilla ni en el título; hay un solo número visible.
- Si el filtro de lectura está activo, se conserva el recuento específico actual como **detalle
  bajo los chips**, no como segundo contador en la barra: **«3 de 12 series con algún número
  leído.»**, **«2 de 12 series con algún número en lectura.»** o **«9 de 12 series sin ningún número
  leído.»**. El contador completo de la región viva incluye también ese dato para el lector.
- Las facetas de etiquetas que hoy aparecen al filtrar por etiqueta se mantienen en el fragmento;
  no se convierten en otra barra ni en un contador.
- En error de lectura, el contador visible es **«—»** y su nombre accesible es
  **«No se pudo cargar el contador»**; no se pinta un 0 inventado. El aviso de error explica.

### 4.2 Chips

- Solo si hay filtros. Orden fijo:
  1. **Búsqueda: «…»**
  2. **Tradición: …**
  3. **Editorial: …**
  4. **Lectura: Leídos / Leyendo / Sin leídos**
  5. **Personaje: …**
  6. **Saga: …**
  7. **Etiqueta: …** (una por etiqueta; las negativas como «Sin …»)
- Cada chip es no interactivo + enlace **«Quitar»** con `aria-label="Quitar filtro …"`; conserva el
  resto y vuelve a página 1.
- **«Limpiar filtros»** al final; quita búsqueda, tradición, editorial, lectura, personaje, saga y
  etiquetas, pero **no** cambia orden ni vista. Se elige «Limpiar filtros» y no «Limpiar todo»
  porque el orden y la vista no son filtros y no deben borrarse con esta acción.
- La cuenta de «Filtros (N)» coincide con el número de chips.
- El contador y la cuenta de filtros se actualizan juntos; la rejilla conserva el foco de chips
  actual.
- La lista interna de claves de «quitar» se amplía a `leido` y a las etiquetas, para que sus chips
  también devuelvan el foco al contenedor; hoy la lista solo cubre búsqueda, tradición, editorial,
  personaje y saga.

### 4.3 Sincronización con el panel

- El panel está fuera de `#rejilla`; al retirar un chip o limpiar, el fragmento incluye
  actualizaciones OOB de los campos del panel (selects, búsquedas, ids ocultos) además del
  contador, la cuenta y la rejilla. No se reemplaza el `<details>` para no cerrarlo.
- Si la implementación no puede sincronizar los campos por OOB, la alternativa segura es que los
  chips naveguen a la URL completa (se repinta la página); no se acepta que el panel muestre un
  valor viejo mientras el chip ya no está.

---

## 5. Orden y vista

### 5.1 Orden

- Un `<select name="orden" id="f-orden">` nativo en la barra, con etiqueta accesible
  **«Ordenar por»**.
- Opciones cortas (las mismas decisiones de #628, sin etiquetas largas):
  - **«Título A-Z»** (`titulo`)
  - **«Título Z-A»** (`titulo_desc`)
  - **«Año reciente»** (`anio_desc`)
  - **«Año antiguo»** (`anio_asc`)
  - **«Añadidas»** (`reciente`)
- **Sin botón «Aplicar orden»**: el cambio de select aplica el orden con HTMX y conserva los
  filtros; la URL sigue siendo la canónica.
- En móvil, el ancho se limita y el texto seleccionado sigue siendo legible; su nombre accesible
  incluye «Ordenar por».

### 5.2 Vista

- Un único control en la barra alterna **Tarjetas ↔ Lista**. Es un enlace real a la URL de la otra
  vista; con HTMX actualiza la rejilla y su propio estado por OOB, sin recargar. Sin HTMX navega a
  la página completa.
- Visible: icono de rejilla o lista (Lucide copiado a `web/iconos.py`, sin CDN) y, en escritorio,
  texto corto **«Tarjetas»/«Lista»**; en móvil, icono con nombre accesible
  **«Ver como lista»/«Ver como tarjetas»** y `title`.
- No se muestra un grupo de dos enlaces que compita con los filtros; un solo control basta para dos
  estados.
- La vista no se cuenta como filtro en «Filtros (N)» ni limpia los filtros.

### 5.3 Qué se retira

- Se retira el botón **«Aplicar orden»**.
- Se retira la barra secundaria de personaje/saga como barra independiente; sus campos y
  sugerencias se mueven al panel.
- Se mueve la vista desde `_rejilla_biblioteca.html` a la barra.

---

## 6. Móvil y 320 px

- **Una fila de búsqueda** a ancho completo; la «barra de una línea» es la de **acciones**, no la
  búsqueda, que no se oculta.
- **Una fila de acciones**: contador + «Filtros» + orden + vista. En 320 px:
  - contador `12 series` (~60 px),
  - `Filtros (3)` con cuenta (~75 px; nombre accesible),
  - orden ~90 px con etiqueta corta,
  - vista icono (~40 px),
  - gaps de 6 px.
  - La suma cabe en los 288 px útiles de 320; si el texto del orden es más ancho, el select se
    acorta y el texto se recorta visualmente, nunca la página.
- **Panel**: hoja de ancho completo bajo la barra, `max-height: min(70vh, ...)`, scroll interno,
  sin scroll lateral de página.
- **Qué se esconde:** solo los controles avanzados dentro del panel y las etiquetas largas de
  orden/vista. **Qué no se esconde:** búsqueda, contador, Filtros, orden, vista, chips y limpiar.
- **Chips** envuelven; «Limpiar filtros» puede ir en una línea propia.
- Si el número de series es largo (miles), en móvil el contador muestra solo la cifra con nombre
  accesible «N series»; la cifra completa sigue en el `sr`. Así entran las cuatro acciones sin
  recortar ni desbordar.
- **320:** `document.documentElement.scrollWidth == clientWidth`; sin tabla; texto ≥14 px; foco
  visible; objetivos ≥40 px.

---

## 7. Accesibilidad

- **Labels:** búsqueda con `aria-label`/label; orden con label accesible; panel con labels
  visibles; view con `aria-label` y `title`; Filtros con nombre accesible y cuenta.
- **`aria-expanded`:** el `summary` de `<details>` comunica el estado de forma nativa. Si se usa un
  `<button>` para una hoja, debe llevar `aria-expanded` y `aria-controls`; no se añade JS nuevo.
- **Foco:** abrir/cerrar deja el foco en el `summary`; Tab entra en el panel; al quitar un chip, el
  foco va a los chips; al limpiar, a la búsqueda; el contador se anuncia.
- **`aria-live`:** el contador es una región viva estable (`role="status"`, `polite`, `atomic`); no
  se recrea en cada intercambio. Texto completo para el lector; visible corto.
- **No solo color:** la cuenta de filtros es texto; el estado de vista se anuncia con nombre
  accesible; los chips llevan texto.
- **Teclado:** `<details>`/`summary` nativo; selects y enlaces reales; sin trampas; Escape no cierra
  el panel (límite declarado de `<details>` sin JS).
- **Texto ≥14 px**; H1 en Anton; frases en Archivo; rutas/títulos con `overflow-wrap`.
- **Sin diálogos nativos ni `hx-confirm`**; el panel no es modal.

---

## 8. Estados y textos finales

| # | Situación | Texto visible exacto | Comportamiento |
|---|---|---|---|
| 1 | Entrada de la pantalla | «Busca por título y acota el resto desde «Filtros».» | 9 palabras |
| 2 | Sin filtros | Contador «12 series»; completo «12 series catalogadas.» | Chips ausentes |
| 3 | Con filtros | Contador «3 series»; completo «3 series coinciden con estos filtros.» | Chips + limpiar |
| 3b | Con filtro de lectura | Bajo los chips: «3 de 12 series con algún número leído.» | Se conserva el dato actual; el contador sigue compacto |
| 4 | Filtros activos | «Filtros (3)» | Cuenta = chips |
| 5 | Sin resultados con filtros | «Ninguna serie coincide con estos filtros.» + «Quita algún filtro o cambia la búsqueda.» | Conserva chips y consulta; «Limpiar filtros» |
| 6 | Biblioteca vacía sin filtros | «Tu biblioteca todavía no tiene series.» + «Añade lo que tengas en el disco desde Por revisar.» | Enlace a Por revisar; no culpa al filtro |
| 7 | Muchos filtros | Contador y «Filtros (N)»; chips envuelven | Panel no se cierra; no se ocultan chips |
| 8 | Filtro inválido en URL | «El filtro de lectura no es válido; se ha quitado.» | 200 con aviso; conserva el resto |
| 9 | Error de BD | «No se pudo cargar la biblioteca. Vuelve a intentarlo.» | Aviso + «Reintentar»; contador «—» con nombre accesible; sin rejilla vacía falsa |
| 10 | Sin sugerencias de personaje/saga/etiqueta | «Sin coincidencias.» | Región viva; sin ruido |
| 11 | Sin editoriales | No se pinta el select de editorial | No hay hueco vacío |
| 12 | Panel cerrado | «Filtros» + contador | Panel oculto; chips visibles |
| 13 | Panel abierto | «Filtros (N)» | Panel y foco en summary |
| 14 | Orden | «Ordenar por» + opción | Aplica sin botón; conserva filtros |
| 15 | Vista tarjetas | «Ver como lista» (icono de rejilla) | Cambia a lista |
| 16 | Vista lista | «Ver como tarjetas» (icono de lista) | Cambia a tarjetas |
| 17 | Muchas páginas | Paginación actual | Conserva filtros/orden/vista |
| 18 | Sin HTMX | `<noscript>` «Aplicar filtros» | GET normal |
| 19 | Panel abierto en móvil | Hoja con scroll | Cierra con el summary; no atrapa foco |
| 20 | Contador 1 | «1 serie» / «1 serie catalogada.» | Singular |

---

## 9. Plan de implementación por rebanadas

Ordenadas de **menor a mayor riesgo**; cada una debe dejar la pantalla usable y los tests de
BL-IT01/#628 en verde.

1. **Rebanada 1 — barra compacta y orden/vista (bajo riesgo).**
   - Añadir la barra con búsqueda, contador, «Filtros», orden y vista; mover orden y vista.
   - Retirar «Aplicar orden»; usar opciones cortas.
   - No mover todavía los filtros avanzados ni cambiar el fragmento.
   - Tests: URL canónica, orden, vista, HX-Push; adaptar el test que busca «Aplicar orden».

2. **Rebanada 2 — panel «Filtros» (riesgo medio).**
   - Un solo `<details>` con tradición, editorial, lectura, personaje, saga y etiquetas; conservar
     endpoints, parciales y nombres (`personaje`, `saga`, `q`).
   - La búsqueda de título queda fuera; los chips siguen funcionando.
   - Sin OOB del panel todavía: la sincronización se hace en la rebanada 3.
   - Tests: campos, sugerencias, panel cerrado/abierto, sin JS.

3. **Rebanada 3 — contador y chips estables (riesgo medio).**
   - Mover el contador a la barra; región viva estable; OOB desde el fragmento.
   - Cuenta de «Filtros (N)»; unificar chips de etiquetas; «Limpiar filtros».
   - OOB de los campos del panel al retirar/limpiar; conservar foco.
   - Tests: contador, chips, quitar/limpiar, foco, OOB.

4. **Rebanada 4 — móvil y accesibilidad (riesgo bajo/medio).**
   - Una fila de acciones en 320; hoja/panel con scroll; iconos/etiquetas cortas; foco y
     `aria-live`; comprobar 320 sin scroll lateral.

5. **Rebanada 5 — estados y copy (bajo riesgo).**
   - Vacíos, sin resultados, muchos filtros, invalidaciones, textos finales y enlaces de salida.

- **Primero la 1**: no toca consultas, modelos, URLs ni endpoints; es layout y controles, y permite
  ver el resultado de la jerarquía antes de mover los filtros.
- **No hay migración, ni cambio de `SeriesService`, ni de `_PAGE_SIZE`, ni de la paginación.**
- El benchmark pendiente se contrasta antes de cerrar la rebanada 2; si cambia el patrón de panel,
  se ajusta el layout, no el contrato de URL/HTMX.

---

## 10. Lo que queda fuera

- **Filtros guardados, smart filters o presets**: otra historia con persistencia y nombres.
- **Buscador único con selector de ámbito** (título/personaje/saga/etiqueta): se descarta por
  ambigüedad y por cambiar endpoints/sugerencias; se prefiere una búsqueda principal + campos
  avanzados en el panel.
- **Facet counts por opción** (cuántas series por tradición/editorial): multiplican consultas y no
  están en el encargo.
- **Nuevos filtros** (año, estado, país) o nuevas opciones de orden.
- **Cambios de consulta, paginación, `_PAGE_SIZE`, URL o HX-Push** más allá de conservar el contrato.
- **Rediseño de tarjetas, portadas, rejilla o vista lista**; solo se mueve su control.
- **Cambiar el comportamiento de «Leer la información de mis archivos»**; solo se mueve de sitio.
- **JS nuevo, SPA, framework, dependencia o migración**.
- **Medición real** de navegador, lector, 320 px y Pi: **NOT RUN**.

---

## 11. Riesgos y mitigaciones

| Riesgo | Por qué duele | Mitigación |
|---|---|---|
| El panel `<details>` tapa chips o rejilla | La persona pierde contexto mientras filtra | Panel no modal, cierre por `summary`, chips se recuperan al cerrar; valorar hoja en móvil |
| `aria-expanded` no explícito | Requisito de accesibilidad | `<summary>` nativo comunica el estado; si se usa `<button>`, añadir `aria-expanded`/`aria-controls` sin JS nuevo |
| Escape no cierra el panel | Costumbre de teclado | Límite declarado de `<details>`; se cierra con el summary; no se promete Escape |
| Campos del panel viejos tras quitar un chip | El formulario y la URL divergen | OOB de los campos al quitar/limpiar; alternativa: navegación completa para chips |
| `quitar` no conoce lectura/etiquetas | Foco y estado de chips inconsistente | Ampliar la lista interna de claves y probar quitar cada tipo |
| Contador recreado en cada swap | Se pierde el anuncio o se duplica | Región estable fuera de `#rejilla`; OOB; texto completo sr + visible corto |
| Una línea a 320 imposible | Densidad móvil | Búsqueda en fila propia; acciones con cuenta corta, orden corto y vista icono; contador solo cifra si es largo; medir sin scroll lateral |
| Se rompen tests de BL-IT01/#628 | URL, chips, orden, vista | Rebanadas 1–3 con tests por contrato; actualizar el test de «Aplicar orden» y el de dos enlaces de vista |
| Búsqueda única esconde personaje/saga | Descubrimiento | «Filtros» visible con cuenta; panel con etiquetas claras; entrada lo dice |
| Vista en un solo control no se entiende | Icono sin texto en móvil | `aria-label`/`title`; icono de la vista destino; texto en escritorio |
| Sugerencias dentro de panel absoluto | Desplegables recortados | `z-index`, panel con scroll, resultados dentro de su caja; no cerrar el panel al teclear |
| Benchmark nuevo ausente | Puede contradecir el patrón | Se deja §13; contrastar antes de implementar la rebanada 2; el contrato URL/HTMX se conserva |
| Panel sin botón Apply | Auto-aplicar puede parecer brusco | Los filtros se aplican al cambiarlos (comportamiento actual); `<noscript>` Apply; no botón principal |
| Contador durante un error | Un «0» falso parece biblioteca vacía | Se oculta o se pinta «—»; el aviso explica; no se anuncia una cifra inventada |
| «Limpiar filtros» vs «Limpiar todo» | «Todo» podría borrar orden/vista | El texto nombra solo los filtros; orden y vista se conservan |

---

## 12. Criterios de aceptación UX → comprobación

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Una barra siempre visible | Búsqueda, contador, Filtros, orden y vista presentes; sin segunda barra |
| 2 | Panel con filtros avanzados | Tradición, editorial, lectura, personaje, saga y etiquetas dentro de `<details>` |
| 3 | Chips y contador | Chips removibles, limpiar, cuenta; contador OOB en región viva |
| 4 | Orden/vista compactos | Select sin «Aplicar orden»; un control de vista; no compiten con filtros |
| 5 | 320 px | Una fila de acciones; panel hoja; sin scroll lateral |
| 6 | Accesibilidad | Labels, `aria-expanded`/details, foco, `aria-live`, ≥14 px |
| 7 | Estados | Sin resultados, vacío, muchos filtros, inválido, error; textos de §8 |
| 8 | Contrato URL/HTMX | URL canónica, HX-Push, fragmento, sin JS nuevo |
| 9 | Sin regresiones | Filtros, paginación, personaje/saga y vista siguen funcionando |
| 10 | Rebanadas | La 1 es layout/controles; 2 panel; 3 contador/chips; 4 móvil; 5 copy |

**PASS de este documento:** jerarquía, panel, chips, contador, orden, vista, móvil, accesibilidad,
estados y plan por rebanadas decididos.
**NOT RUN:** implementación, navegador real, lector de pantalla, teclado físico, 320 px medidos y
Pi. Benchmark nuevo no disponible al redactar.

---

## 13. Contraste con el benchmark pendiente

- **No existe** `docs/design/benchmark-biblioteca-filtros.md` al redactar. Se ha revisado `main` y
  el worktree de benchmark en curso; no está.
- Reglas que **no** se cambian y que cualquier benchmark debería respetar:
  - El estado es la URL; `HX-Push-Url` apunta siempre a la página completa.
  - El fragmento conserva el contrato de chips, contador, vacío/error y foco.
  - Nada de JS nuevo, dependencias, migración ni consultas externas.
- Cuando aparezca, contrastar especialmente: **una barra vs panel**, **búsqueda única vs por
  campo**, **panel desplegable vs hoja modal** y **auto-aplicar vs Aplicar explícito**. Si el
  benchmark impone otra regla, se actualiza este documento antes de la implementación.
