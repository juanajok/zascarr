# Evidencia de U16 (#203): usar todas las pantallas en el móvil sin zoom ni desplazamiento lateral

Rama `claude/u16-movil`, 2026-10-16. **Verificación emulada**: los dispositivos reales están en **NOT RUN** como deuda visible
([`ronda-dispositivos-reales.md`](ronda-dispositivos-reales.md)); **la tarjeta no se cierra con ambos en NOT RUN** (criterio 4).

| Dato | Valor |
|---|---|
| Navegador | Google Chrome 154.0.8037.92 **headless por CDP**, viewport **táctil emulado** (`mobile: true`) a 360×740, 390×844 y 414×896 |
| Entorno | ensayo aislado `docs/design/ui-baseline/ensayo.sh` (Postgres real). «Antes» = `main` `57259ac`; «después» = el commit funcional **`aa46cccba9617b51db1c97acab938c8346a8c6ee`** de la rama `claude/u16-movil` (el último que toca `src/` o `tests/`; `365da6d` solo añade esta documentación y la fusión es `0275335`, que no es lo medido). Cada uno, en un ensayo **reconstruido desde cero**, con la **misma** herramienta |
| Herramientas | [`medir_u16.py`](medir_u16.py) (mide), [`capturar_u16.py`](capturar_u16.py) (capturas) |
| Datos en bruto | [`medicion-antes.json`](medicion-antes.json), [`medicion-despues.json`](medicion-despues.json) |
| Alcance | **14 pantallas × 3 anchos = 42 medidas** por lado: panel, biblioteca, ficha de serie, Descubrir, Por revisar, Pendientes por carpeta, asistente de carpeta, revisión de la vinculación, Deseados, Mi biblioteca, Ajustes, Estado, aviso legal (asistente y texto) |

## Cómo se mide (y qué NO mide)

- **Desborde lateral** (WCAG 1.4.10): `scrollWidth > clientWidth`, y qué elementos sobresalen (la barra inferior fija se anota aparte:
  su ancho es el de la página, no su causa).
- **Zoom al escribir**: campos de texto, búsqueda, contraseña y `select` con `font-size` **< 16 px** (el umbral de Safari en iOS).
  Es una **medida de tamaño**; **no** he visto el zoom de Safari, porque no tengo un iPhone.
- **Objetivos táctiles**: alto de botones, campos, selectores, `summary` y enlaces-botón (**< 44 px**, criterio 3) y de cualquier
  control (**< 24 px**). Un enlace **dentro de una frase** está exento (WCAG 2.5.8) y no se cuenta; un enlace **suelto** debe medir ≥ 24 px.
  *Limitación:* «dentro de una frase» es una **heurística** del script: un enlace se da por integrado si su contenedor tiene más de unos
  pocos caracteres de texto además del propio enlace. Puede **excluir** un grupo de acciones que no sea una frase (p. ej. enlaces separados por
  texto corto). Por eso los **ceros publicados valen para los elementos que selecciona el script, no son una certificación exhaustiva** de
  todos los objetivos táctiles de cada pantalla.
- Solo pantallas **cargadas**: no están medidos los estados que aparecen tras una interacción (p. ej. los resultados de Descubrir, o
  el panel «Más» abierto). La verificación completa por anchos es **V13** (fuera de alcance de esta tarjeta).

## Resultados (suma de las 42 medidas por pantalla y ancho)

| Defecto medido | Antes | Después |
|---|---|---|
| Medidas con **desplazamiento lateral** | **4** (ficha de serie a 360 y 390; aviso legal a 360 y 390) | **0** |
| Campos con fuente **< 16 px** | **102** | **0** |
| Controles con alto **< 44 px** | **241** | **0** |
| Controles o enlaces sueltos con alto **< 24 px** | **18** | **0** |

Por pantalla a **360 px** (antes → después): desborde / campos < 16 px / alto < 24 px / controles < 44 px.

| Pantalla | Desborde | Campos < 16 px | < 24 px | Controles < 44 px |
|---|---|---|---|---|
| panel | no → no | 1 → 0 | 1 → 0 | 5 → 0 |
| biblioteca | no → no | 5 → 0 | 0 → 0 | 2 → 0 |
| ficha de serie | **+53 px → no** | 0 → 0 | 0 → 0 | 1 → 0 |
| Descubrir | no → no | 1 → 0 | 0 → 0 | 4 → 0 |
| Por revisar | no → no | 10 → 0 | 0 → 0 | 11 → 0 |
| Pendientes por carpeta | no → no | 0 → 0 | 1 → 0 | 2 → 0 |
| asistente de carpeta | no → no | 0 → 0 | 1 → 0 | 5 → 0 |
| revisión de la vinculación | no → no | 0 → 0 | 0 → 0 | 14 → 0 |
| Deseados | no → no | 1 → 0 | 0 → 0 | 9 → 0 |
| Mi biblioteca | no → no | 0 → 0 | 0 → 0 | 2 → 0 |
| Ajustes | no → no | 16 → 0 | 2 → 0 | 24 → 0 |
| Estado | no → no | 0 → 0 | 0 → 0 | 0 → 0 |
| aviso legal (asistente) | no → no | 0 → 0 | 1 → 0 | 0 → 0 |
| aviso legal (texto) | **+49 px → no** | 0 → 0 | 0 → 0 | 0 → 0 |

## Causas del desborde y qué se cambió

1. **El selector «Qué buscar» de la ficha** (`#wishlist_policy`) medía **401 px**: el ancho de un `<select>` es el de su opción más larga.
   `max-width: 100%; min-width: 0`. *(La auditoría midió +127 px en la Pi; en este ensayo, con otros datos, +53 px a 360. La causa es la
   misma; **la magnitud en la Pi no se ha reproducido**.)*
2. **La tabla del aviso legal** medía **397 px** por un texto largo sin saltos: `overflow-wrap: anywhere` en sus celdas.
3. **La barra inferior** usaba `minmax(max-content, 1fr)` y se ensanchaba con la página: columnas `minmax(0, 1fr)` y etiqueta con
   `clamp()`. Era una *víctima* del desborde, pero con ese ancho mínimo podía **causarlo** en cuanto una etiqueta creciera.

Zoom y objetivos: un bloque **táctil** al final de `web.css` (`@media (max-width: 860px), (pointer: coarse)`): `font-size: 1rem` y
`min-height: 44px` en campos, selectores, botones, `.btn`, `summary` y enlaces de volver; **sin `!important`** y sin tocar cada regla. **Ese bloque**
no se aplica en escritorio con ratón y ancho > 860 px. **Fuera de él** hay tres cambios que sí valen en cualquier pantalla: el tope de
ancho del selector de política (`.politica-form select`), `overflow-wrap` en las celdas del aviso legal y las columnas de la barra
inferior (esta, solo ≤ 860 px). Los seis enlaces «← Volver…» sueltos usan ya la clase `.back-link` (que ya existía en la ficha), **cuyos estilos existentes también se aplican en
escritorio** (color, sin subrayado, margen inferior): es un cambio de aspecto posible allí, **no medido ni comparado**.

## Lo que NO está acreditado

- **Dispositivos reales: NOT RUN** (iPhone con Safari y Android de gama baja con Chrome, contra la Pi, a 360/390/414 px). Es la deuda
  aceptada; el registro por pantalla está en [`ronda-dispositivos-reales.md`](ronda-dispositivos-reales.md) con todas las filas en NOT RUN.
- **El zoom de Safari en iOS** no se ha visto: solo se ha medido que ningún campo baja de 16 px.
- **La Pi**: no se ha tocado; la medida de +127 px de la auditoría no se ha repetido.
- **Estados interactivos** (resultados de búsqueda, panel «Más», errores) y el tema oscuro: no se han medido con esta herramienta.
- **Lector de pantalla y teclado**: sin cambios en esta tarjeta, no probados aquí.
- **§13 (benchmarking)**: no se hizo. Es un arreglo de CSS acotado y medido; el procedimiento lo exime («un arreglo evidente de texto o CSS no
  requiere investigación»). Lo digo para que la revisión lo juzgue, no porque lo dé por cerrado.
- **Regresión visual de escritorio: no ejecutada.** El bloque táctil no se aplica con ratón y ancho > 860 px (lo comprueba
  `tests/test_web_movil.py` por estructura, no por captura), pero los cambios de fuera del bloque descritos arriba y `.back-link` sí llegan
  al escritorio y no se han comparado con capturas.

## Pruebas

`tests/test_web_movil.py` (9 pruebas de **contrato del CSS y las plantillas**, sin navegador): columnas de la barra que no superan el ancho,
campos de 16 px y 44 px de alto, botones y `summary` de 44 px, casillas en 24 px, sin `!important`, tope del selector, tablas del aviso
legal y enlaces de volver con su clase. **No sustituyen a la medida en Chrome**: impiden que un defecto medido vuelva por una edición.
Las capturas ([1](1-ficha-de-serie--movil.png), [2](2-por-revisar--movil.png), [3](3-ajustes--movil.png), [4](4-asistente-de-carpeta--movil.png),
[5](5-aviso-legal-texto--movil.png)) sirven para revisar el aspecto a 390 px (la 5, a 360 px).
