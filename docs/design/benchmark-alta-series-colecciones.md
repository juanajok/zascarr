# Benchmark y auditoría UX/UI — añadir series a una colección (2026-11-14)

> **Estado:** implementación de divulgación progresiva sobre `main` posterior a #790.
> **Método:** lectura de plantilla/CSS/rendimiento, revisión contra el sistema de diseño
> ZascArr y benchmark de referencias. **NOT RUN:** navegador real, tableta física,
> lector de pantalla y validación con coleccionistas. Los PASS son de código/pruebas.

## 1. Problema local

La ficha de una colección tiene dos tareas distintas:

1. **Ver y ordenar** las series que ya pertenecen a la colección.
2. **Añadir** series que aún no están.

En el código previo, la tarea 2 estaba siempre desplegada: un `<fieldset>` con buscador,
selector de tradición, contador, hasta **40 casillas** y paginación, debajo de la lista de
miembros. Con una colección de 31 series, la ficha encadenaba **31 filas + 40 casillas**
antes de llegar a «Datos y búsqueda»; en móvil, con la rejilla a una columna, el selector
ocupaba varias pantallas. Además, cada carga de la ficha consultaba y renderizaba esas 40
series aunque el coleccionista no fuera a añadir nada.

### Hallazgos de la auditoría

| Prioridad | Hallazgo | Evidencia | Estado |
|---|---|---|---|
| **P0** | El alta ocupa la ficha y compite con la lista de miembros | `<fieldset>` con 40 `coleccion-check` siempre visible | **Corregido** |
| **P0** | Carga y renderiza 40 series disponibles en cada visita | `pagina_series_sin_coleccion` en el `GET` de la ficha | **Corregido**: endpoint perezoso |
| **P1** | El botón/entrada de alta queda después de toda la lista de miembros | markup previo | **Corregido**: CTA antes de la lista |
| **P1** | Copia obsoleta: «Añadir series sin colección» | texto previo, falso desde M:N | **Corregido**: «Añadir series a esta colección» |
| **P1** | No hay jerarquía visual en la cabecera «Series» | faltaba `.coleccion-series-cabecera` en CSS | **Corregido** |
| **P2** | Colección vacía sin camino claro | estado vacío remitía a «la lista de abajo» | **Corregido**: el desplegable se abre solo |
| **P2** | Estado de filtros/paginación se perdía al quitar una serie | `POST quitar` redirigía sin query | **Corregido** |
| **P2** | El panel no era accesible por teclado | era un bloque siempre visible, sin control de apertura | **Corregido con `<details>` + `summary`** |

## 2. Benchmark

| Referencia | Cómo resuelve el alta | Qué se adopta / adapta / descarta |
|---|---|---|
| **Sonarr** ([Add New](https://wiki.servarr.com/en/sonarr/library)) | Página/búsqueda separada para añadir; la biblioteca no mezcla el alta con la lista | **Adoptar** el principio «no cargar el alta hasta pedirla»; **adaptar** a un panel en línea, sin página nueva |
| **Komga** ([Collections](https://komga.org/docs/guides/collections/)) | Se añade desde el menú de acción de la serie o multiselección; la ficha de colección tiene un modo de edición con barra de herramientas | **Adoptar** que el alta sea una acción explícita; **descartar** el diálogo modal nativo (el sistema de diseño lo prohíbe para lo importante) |
| **Kavita** ([Collections](https://wiki.kavitareader.com/guides/features/collections/)) | «Add to → Add to Collection» desde el menú contextual de la serie/libro; la colección se edita desde su menú de acciones | **Adoptar** la baja fricción del CTA y no enseñar todas las series de la biblioteca por defecto; **adaptar** a una ficha con desplegable |
| **Jellyfin / Plex** (patrón de colecciones) | «Add to collection» desde el menú del elemento; el selector aparece en un diálogo | **Adoptar** el disparador explícito; **descartar** el diálogo por accesibilidad y por el sistema de diseño |
| **Calibre-Web / estanterías** | Se añade desde la ficha del libro o la edición de la estantería | **Adoptar** la separación entre consultar y editar |
| **ZascArr, sistema de diseño** ([sistema](sistema-de-diseno-zascarr.md)) | Lo secundario va plegado en `<details>`; ≤ 50 palabras antes de la primera acción; objetivos táctiles ≥ 40 px; sin diálogos nativos | **Adoptar** el patrón `<details>` + `summary` como botón; **adaptar** con carga HTMX solo al abrir |

### Opciones evaluadas

| Opción | Ventaja | Problema | Veredicto |
|---|---|---|---|
| A. Dejar el selector siempre abierto | Descubrible | Es el problema actual; móvil larguísimo; carga 40 series | **Descartar** |
| B. Página separada «Añadir series» | Muy simple | Rompe el contexto de la colección y añade un viaje | **Descartar** para este caso |
| C. Diálogo modal | No ocupa la ficha | Diálogo nativo/overlay; foco y vuelta atrás; el sistema de diseño lo evita | **Descartar** |
| D. `<details>` con contenido ya renderizado | Sin JS | Sigue enviando 40 series y el DOM crece | **Descartar** |
| **E. `<details>` + HTMX perezoso** | Botón nativo, teclado, sin diálogo, cero payload hasta abrir | Requiere endpoint y una prueba más | **Adoptar** |

## 3. Solución implementada

- La cabecera «Series» muestra **un botón «Añadir series»** antes de la lista de miembros.
- Es un `<details>` con `summary` estilizado como `.btn`; el marcador nativo se oculta.
- El contenido no viaja en el HTML inicial: `hx-get="/ui/colecciones/{id}/anadir"` se dispara
  con `toggle once` (o `load` si la colección está vacía o hay que reabrir tras un error).
- El endpoint devuelve solo el fragmento **`_coleccion_anadir.html`**, con:
  - buscador y tradición;
  - contador y paginación (40 por página);
  - casillas de selección;
  - un formulario POST separado para «Añadir series seleccionadas».
- La colección vacía abre el desplegable automáticamente: no hay un estado vacío sin salida.
- Un error de alta devuelve la ficha con `abrir_alta`, que abre y carga el panel.
- La vista lista/tarjetas se conserva; los enlaces de vista y las altas de quitar mantienen
  búsqueda, tradición, página y selección.
- No se usa JavaScript propio: HTMX + `<details>`; sin diálogo nativo.

### Móvil y tableta

- El CTA queda inmediatamente bajo la cabecera, no tras 31 filas.
- El panel ocupa el ancho de la tarjeta; filtros 3 → 2 columnas a 760 px → 1 a 480 px.
- La rejilla de casillas pasa a **una columna a 480 px**; cada etiqueta mantiene 44 px de alto.
- El botón/summary hereda `.btn` (≥ 40 px; en táctil los controles del panel son ≥ 44 px).
- El contenido solo se pide al abrir: en una colección de 31 series, la ficha inicial no
  renderiza las 40 casillas ni la paginación.

## 4. Presupuesto y accesibilidad

- Antes de la primera acción: cabecera + botón «Añadir series»; no hay 40 controles.
- Un solo botón principal en la pantalla: «Guardar colección» (el alta es `.btn` neutro).
- `<details>`/`<summary>` da apertura, cierre, foco y teclado sin ARIA manual.
- Al cargar el fragmento, el foco se queda en el `summary`; no se roba al abrir.
- El contador es `role="status"`, las casillas son etiquetas de 44 px y el foco visible
  usa el token del sistema.
- Sin diálogos nativos ni `confirm()`.

## 5. Criterios de aceptación

- `GET /ui/colecciones/{id}` **no** contiene casillas ni la lista de series disponibles;
  contiene «Añadir series» y el `hx-get` al panel.
- `GET /ui/colecciones/{id}/anadir` devuelve el fragmento con filtros, casillas y
  paginación, y `Cache-Control: no-store`.
- El panel conserva búsqueda, tradición, página y selección; «Limpiar filtros» funciona.
- Una colección vacía abre el panel sin un clic adicional.
- Quitar una serie conserva el estado de la vista.
- La suite de colecciones y los tests de componentes/CSS siguen verdes.

## 6. PASS / FAIL / NOT RUN

- **PASS (código/pruebas):** ficha sin alta masiva, endpoint perezoso, filtros/paginación,
  empty state con panel abierto, estado de vista al quitar, CSS de cabecera.
- **FAIL (previo, corregido):** selector siempre visible, copia «sin colección», carga
  innecesaria, botón después de la lista.
- **NOT RUN:** navegador real, tableta/móvil físico, lector de pantalla y validación con
  coleccionistas. No hay capturas nuevas; la comprobación es de plantilla y pruebas.
