# Sistema de diseño de ZascArr

> **Instantánea publicada el 2026-11-13** sobre `main@76e7812`, con la revisión de UI/UX de
> [#689](https://github.com/juanajok/zascarr/pull/689).
> Artefacto visual original: [`sistema-de-diseno-zascarr.pdf`](sistema-de-diseno-zascarr.pdf).
>
> Esta es la copia **diffeable** del sistema. Las láminas de color, las muestras de componentes y
> los dibujos de la marca viven en el PDF; aquí quedan las reglas, los tokens y el texto.
> Si se publica una versión nueva, se actualizan los dos ficheros en la misma PR.

## Libro de marca

ZascArr se diseña como un tebeo: papel y tinta con acentos CMYK, bordes gruesos de tinta, sombra
dura sin desenfoque, una trama de puntos y didascalias amarillas.

Todo es CSS y HTMX servidos por la propia app: dos fuentes libres en `static/vendor/fonts`, iconos
SVG en línea, nada de CDN, de JavaScript propio ni de imágenes externas. Lo ligero y lo legible van
primero: la app corre en una Raspberry Pi compartida y la usa «el Coleccionista», que no abre
terminales.

## Principios

- **La viñeta es la unidad.** Cualquier bloque es un rectángulo `paper-2` con borde de 3 px en `ink`
  y radio `radius-panel`. Si algo se puede tocar o está activo, gana `shadow-ink-sm` o `shadow-ink`.
- **Un aviso no parece un botón.** La sombra dura desplazada es de lo que se pulsa (y del rótulo
  girado). La didascalia y los avisos van sin ella, con el canto `radius-panel`.
- **Un botón principal por pantalla.** El amarillo es LA acción que hace avanzar la tarea, y se pide
  con `.primary`. Un envío es neutro por defecto: los botones que se repiten (uno por fila o por
  tarjeta) y los «Guardar» de Ajustes no son principales. La única excepción con significado propio
  es el verde de «Sí, organizar» (aceptar una sugerencia).
- **El relleno y el texto no comparten color.** `cyan`, `magenta`, `yellow`, `ok` y `warn` son tinta
  de imprenta: rellenos, bordes y trama. Como texto se usan sus variantes `-t` (`cyan-t`, `mag-t`,
  `ok-t`, `warn-t`, `amber-t`). Una prueba de la CI (`test_web_css_contraste`) impide usar un relleno
  como color de texto.
- **Un relleno sólido lleva siempre su pareja.** El texto sobre `yellow` va en `on-yellow`; sobre
  `ok-solid`, en `on-ok-solid`; sobre `warn-solid`, en `on-warn-solid`; sobre `hot`, en `on-hot`.
  Nunca blanco ni `ink` a mano: en el tema nocturno `ink` es claro.
- **Un estado, un aspecto.** El aspecto de cada estado (`neutro`, `ok`, `warn`, `amber`, `info`) se
  define una sola vez en `web/componentes.py` y se pinta con las macros `ui.*`. Una plantilla nunca
  elige colores ni clases de matiz por su cuenta.
- **El color nunca va solo.** Cada estado lleva palabra e icono: ✓ ok, ! warn, ? amber, i info. Un
  número que te falta tiene borde discontinuo; uno que tienes, ✓.

## Voz y contenido

- Español llano, de tú, en frases completas. «Aún no hay tebeos en ZascArr. Te guiamos paso a paso.»
  · «Miramos tu disco el 12 de octubre y encontramos 1.542 tebeos.»
- **Un error dice qué pasó y qué hacer.** «No se ha podido consultar ninguna fuente ahora mismo. No
  es que no haya coincidencias: vuelve a intentarlo en unos minutos o crea la serie a mano.»
  Prohibido «exit code 1», trazas o nombres de campos.
- **Di lo que NO ha pasado cuando importa.** «Elección anotada. Todavía no se ha creado ninguna serie
  ni se ha vinculado ningún archivo.» · «Abrir este asistente no ha consultado ninguna fuente: solo
  se busca cuando tú lo pides.»
- Los chips son de una a tres palabras: «Hecho», «Toca ahora», «Después», «Aún no se puede», «En
  conflicto», «por confirmar». Un recuento va con su sustantivo: «12 carpetas».
- Los botones son verbos con objeto: «Revisar mi biblioteca», «Buscar en las fuentes», «Buscar
  ahora». Lo secundario es `.btn.ghost` («Ahora no»).
- El vocabulario es de tebeoteca: tebeo, serie, número, grapa, edición, deseados, por revisar.
  Nunca «issue», «wishlist» ni «item» en la superficie.
- Las mayúsculas las pone el CSS, no el texto: escribe «Inicio» y la rotulación lo convierte.
  Mayúsculas solo en rótulos de ≤ 3 palabras. Sin emoji en el texto.
- **Presupuesto de texto:** una frase de entrada por pantalla de ≤ 20 palabras que diga qué se hace
  aquí, y ≤ 50 palabras visibles antes de la primera acción. Lo demás, plegado en `<details>` («¿De
  dónde salen estos datos?»). Nada de «token», «lote» ni códigos internos.
- La garantía va junto a la acción con efecto («no se mueve ni se renombra nada»), no en la cabecera
  de una pantalla que no cambia nada.

## Color

Página y controles en `paper`; viñetas en `paper-2`; texto en `ink`, `ink-soft` (secundario) o
`ink-faint` (metadatos). Los tres textos pasan 4,5:1 sobre `paper` y `paper-2` en los dos temas.

Para teñir un componente por estado usa `ok-bg`, `warn-bg`, `amber-bg` o `info-bg`. Nunca un
`color-mix()`: la prueba de contraste solo admite los tres decorativos declarados (separadores y
rótulo de error). Encima, el chip lleva el texto `-t` de su matiz; el aviso y el `hero-state` llevan
`ink`.

La didascalia, el rótulo, el aviso legal, el toast y el paso «siguiente» usan `caption-bg` con texto
`ink`.

`yellow` es el color de la acción y del «estás aquí»: botón principal, entrada activa del menú, paso
actual, barra de progreso y enlace «ver todo» al pasar. Uno solo por pantalla en grande. Nunca en la
marca.

`bermellon` (y `bermellon-trama`) son de la marca y solo de la marca: nunca un botón, un estado ni un
fondo de la interfaz.

«La marca» es el logo (el estallido y sus tres dibujos). La portada de este sistema no es la marca ni
la interfaz: es una pieza de presentación, y puede usar las cuatro tintas CMYK, con el amarillo en
una tira y nunca como losa principal.

`magenta` y `cyan` son trama y marca, no estados. `hot` (magenta oscuro) solo para el contador de
Por revisar.

El tema nocturno sigue la preferencia del sistema (`prefers-color-scheme`); no hay selector manual.

### Tokens

Cada muestra del PDF enseña el tema Papel (claro) a la izquierda y el Nocturno (oscuro) a la derecha.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `paper` | `#f6f3ec` | `#131316` | Fondo de página, de la barra lateral y de los controles (botón neutro, campos, chip neutro). |
| `paper-2` | `#efeadf` | `#1b1b20` | Fondo de las viñetas: `.card`, tarjetas de pendientes, filas de deseados, métricas, ajustes, grupos y estados vacíos. |
| `ink` | `#17171a` | `#f0ede4` | Texto principal y TODOS los bordes de tinta. Sobre `paper`, `paper-2`, `caption-bg` y los fondos `-bg`. Como relleno, la entrada de paginación actual (texto `paper`). |
| `ink-soft` | `#4a4a50` | `#b7b4ab` | Texto secundario (`.subtitle`, `.muted`, descripciones, enlaces de navegación en reposo) sobre `paper` y `paper-2`. |
| `ink-faint` | `#63636b` | `#9c9aa0` | Texto terciario (metadatos, `.empty`, etiquetas de grupo del menú, marcador de posición) sobre `paper`, `paper-2` y `caption-bg`; el mínimo de texto (4,96:1 sobre `paper-2` en claro). |
| `cyan` | `#0d9bd6` | `#38b6e8` | Cian CMYK: SOLO relleno, borde y trama (puntos de la segunda métrica). Nunca texto: usa `cyan-t`. |
| `magenta` | `#d81a75` | `#f04d97` | Magenta CMYK: SOLO relleno y trama (los puntos de la marca y de las métricas). Nunca texto: usa `mag-t`. |
| `yellow` | `#f2c500` | `#ffd23f` | Amarillo CMYK, el color de la ACCIÓN: relleno del botón principal (`.primary`, uno por pantalla), de la entrada activa del menú, del paso actual, del enlace de salto y de la barra de progreso. Nunca en la marca. El texto encima va SIEMPRE en `on-yellow`. |
| `caption-bg` | `#fdf3d0` | `#2b2617` | Fondo de la didascalia (`.caption`, texto de lectura), del rótulo (`.rotulo`), del aviso legal, del toast y del paso «siguiente». Texto en `ink`. |
| `ok` | `#2e8b57` | `#4cbf83` | Verde de relleno y borde (sugerencia de candidato, punto de semáforo «bien»). Nunca texto: usa `ok-t`. Se distingue de `warn` solo por el matiz (1,28:1): acompáñalo de palabra o icono. |
| `warn` | `#c0392b` | `#f07167` | Rojo de relleno (punto de semáforo «mal»). Nunca texto: usa `warn-t`. |
| `cyan-t` | `#0a6a96` | `#5cc4f0` | Cian como TEXTO (chip info, botón reintentar, enlace atrás al pasar) y anillo de foco, sobre `paper`, `paper-2` e `info-bg`. |
| `ok-t` | `#1f6b43` | `#5fd096` | Verde como TEXTO (chip ok, «guardado», métrica en positivo) sobre `paper`, `paper-2` y `ok-bg`. |
| `warn-t` | `#a8321f` | `#f58a80` | Rojo como TEXTO (chip warn, errores de formulario, cifra de métrica en alerta) sobre `paper`, `paper-2` y `warn-bg`. |
| `amber-t` | `#7a5a00` | `#ffd23f` | Ámbar como TEXTO (chip amber: «por confirmar», «No se puede marcar») sobre `amber-bg` y `paper`. |
| `mag-t` | `#b0125f` | `#f46aa7` | Magenta como texto y acento de casillas y radios (`accent-color`) sobre `paper`. |
| `on-yellow` | `#17171a` | `#17171a` | Texto fijo sobre `yellow` en los DOS temas (en oscuro `ink` es claro y daba 1,2:1). |
| `ok-solid` | `#1f6b43` | `#5fd096` | Relleno sólido verde: insignia «importado», número que tienes, botón de sugerencia. Texto en `on-ok-solid`. |
| `on-ok-solid` | `#ffffff` | `#0f2a1b` | Texto sobre `ok-solid`. |
| `warn-solid` | `#a8321f` | `#f58a80` | Relleno sólido rojo: insignia «falló». Texto en `on-warn-solid`. Igual de claro que `ok-solid` (1,03:1 en claro): la palabra hace la diferencia. |
| `on-warn-solid` | `#ffffff` | `#2a0f0c` | Texto sobre `warn-solid`. |
| `hot` | `#b0125f` | `#f46aa7` | Insignia «caliente» del menú (contador de Por revisar). Texto en `on-hot`. |
| `on-hot` | `#ffffff` | `#1a0610` | Texto sobre `hot`: en oscuro cambia el color del texto, no el matiz. |
| `ok-bg` | `#e1f2e8` | `#16301f` | Fondo teñido verde de chip ok (texto `ok-t`), aviso ok y `hero-state` ok (texto `ink`) y del paso hecho. |
| `warn-bg` | `#fbe4df` | `#3a1b17` | Fondo teñido rojo de chip warn (texto `warn-t`), aviso warn y `hero-state` warn (texto `ink`). |
| `amber-bg` | `#fdf0c4` | `#35290c` | Fondo teñido ámbar de chip amber (texto `amber-t`), aviso amber y `hero-state` amber (texto `ink`). |
| `info-bg` | `#dff1fa` | `#10293a` | Fondo teñido cian de chip info (texto `cyan-t`), aviso info y `hero-state` info (texto `ink`). |
| `bermellon` | `#f2542d` | `#f2542d` | Bermellón de la marca: el estallido «¡ZAS!» (`static/brand`). SOLO en la marca, nunca en la interfaz ni como estado; con `ink` y blanco son sus tres tintas. |
| `bermellon-trama` | `#c2391a` | `#c2391a` | Trama del estallido en el dibujo completo de la marca (180 px). Un tono del bermellón, no una tinta más; solo en la marca. |

## Tipografía

Dos familias libres (OFL), servidas por la app y nunca desde un CDN: **Anton** (`display`) para
rotular y **Archivo** variable (`body`) para todo lo que se lee y se usa. Sin tercera familia «de
cómic» y sin fuentes comerciales.

### Rotulación

Anton (OFL, subconjunto latino), peso 400 y **solo en mayúsculas** (`text-transform`): rótulos de
≤ 3 palabras y `h1` de pantalla. Una frase o una ruta va en Archivo (`titulo-frase`). Impact queda de
respaldo.

| Estilo | Tamaño / interlineado | Peso | Uso |
|---|---|---|---|
| `titulo-pagina` | 48px / 1.15 | 400 | `h1` de la página. En la hoja: `clamp(30px, 4.4vw, 48px)`. |
| `cifra` | 42px / 1 | 400 | Cifra de una métrica (`.metric-value`). En la hoja: `clamp(30px, 3.4vw, 42px)`. Con `tabular-nums`. |
| `titulo-seccion` | 26px / 1.15 | 400 | `h2` de sección (`.section-header h2`, `.seccion`). En la hoja: `clamp(19px, 2.4vw, 26px)`. |
| `marca` | 1.4rem / 1.55 | 400 | El nombre en la barra lateral, junto a la cajita de la marca. |
| `numero-paso` | 1.25rem / 1 | 400 | Número del círculo de cada paso de Primeros pasos. |
| `titulo-bloque` | 1.05rem / 1.15 | 400 | `h2` de un bloque de revisión (`.audit-block`). Interlineado 1.15: con menos, las tildes de las mayúsculas tocan la línea de encima. |

### Texto

Archivo variable (OFL, normal e itálica, pesos 100–900) para todo lo que se lee y se usa. Mínimo
informativo: 14 px (`.875rem`), salvo la etiqueta de la barra inferior del móvil (hasta 12 px a
320 px).

| Estilo | Tamaño / interlineado | Peso | Uso |
|---|---|---|---|
| `cuerpo` | 16px / 1.55 | 400 | Texto corrido de toda la aplicación. |
| `titulo-frase` | 1.05rem / 1.15 | 800 | Un título que es una FRASE (> 3 palabras) o una RUTA: `.titulo-frase`, `h3` de los pasos. Archivo negrita, sin mayúsculas ni interletraje; el tamaño lo pone su nivel de título. |
| `estado-resumen` | 1.15rem / 1.55 | 700 | Frase de estado general en `/estado`, junto al semáforo grande. |
| `didascalia` | 0.9rem / 1.5 | 600 | Texto de la didascalia (`.caption`) y del aviso legal: caja de lectura, sin mayúsculas ni giro, hasta 70ch. |
| `nav` | 0.95rem / 1.55 | 700 | Entradas del menú lateral; en la barra inferior del móvil, `clamp(.75rem, 3.3vw, .875rem)` a 600. |
| `boton` | 0.88rem / 1.55 | 700 | Etiqueta de botón; `.btn.sm` baja a 0.875rem. |
| `secundario` | 0.875rem / 1.55 | 400 | Metadatos, detalles y notas: el tamaño más usado de la hoja (38 reglas) y el mínimo. |
| `chip` | 0.875rem / 1.55 | 700 | Texto de un chip de estado, con familia fija (`body`) aunque esté dentro de un titular; las insignias (`.wishlist-badge`, `.issue-chip`, `.badge`) van a 800 y con `tabular-nums`. |
| `etiqueta` | 0.875rem / 1.55 | 700 | Rótulo (`.rotulo`, girado -1,2°) y cabecera de grupo del menú, en mayúsculas. Solo ≤ 3 palabras. |

Los tamaños de título usan `clamp()` en la hoja; los estilos guardan el máximo.

## Forma: bordes, sombras y radios

Grosor del borde según el papel: **3 px** en viñetas, cabeceras, barra lateral y separadores
principales; **2,5 px** en botones, campos y paginación; **2 px** en chips, insignias, avisos y
didascalias; **1 px** solo en separadores internos de listas.

`radius-panel` (4 px) para todo lo rectangular; `radius-pill` para chips, insignias y progreso;
círculo para los puntos de semáforo y los números de paso.

Sombra dura, nunca difusa: `shadow-ink-sm` en botones y rótulos, `shadow-ink` en grupos,
`hero-state` y paneles flotantes. Didascalias y avisos, sin sombra.

Gesto de botón: al pasar sube (-2 px, -2 px) con `shadow-ink-hover`; al pulsar baja (1 px, 1 px) con
`shadow-ink-active`. Toda sombra dura sale de los tokens: nunca escribas `Npx Npx 0 var(--ink)` a
mano (en oscuro la tinta es crema). Las tarjetas suben 3–4 px y ganan `shadow-ink`.

Una sola inclinación: el rótulo (`.rotulo`) a -1,2°. Nada más va torcido; la didascalia ya no.

| Token | Valor (claro · oscuro) | Uso |
|---|---|---|
| `radius-panel` | 4px | Todo lo rectangular: viñetas, botones, campos, avisos, paginación. Casi recto, como el recuadro de una viñeta. |
| `radius-pill` | 999px | Chips, insignias del menú y barra de progreso. |
| `shadow-ink` | `4px 4px 0 #17171a` · `4px 4px 0 #6f6d76` | Sombra dura de viñeta: grupos, `hero-state`, paso siguiente, panel «Más» y tarjetas al pasar. Sin desenfoque. Su color es `--shadow-color`: la tinta en claro y un gris de tinta en oscuro (≥ 3:1 sobre los dos papeles), nunca la tinta crema. |
| `shadow-ink-sm` | `3px 3px 0 #17171a` · `3px 3px 0 #6f6d76` | Sombra dura pequeña: botones en reposo, rótulo (`.rotulo`), entrada activa del menú, campos con foco, toast. Solo lo que se pulsa o es rótulo: la didascalia y los avisos van sin sombra. |
| `shadow-ink-hover` | `5px 5px 0 #17171a` · `5px 5px 0 #6f6d76` | Botón al pasar: sube (-2 px, -2 px) y la sombra crece a 5 px. Nunca escribas este desplazamiento a mano. |
| `shadow-ink-active` | `1px 1px 0 #17171a` · `1px 1px 0 #6f6d76` | Botón al pulsar: baja (1 px, 1 px) y la sombra casi desaparece. |
| `side` | 244px | Ancho de la barra lateral de escritorio (`.app`, columna 1). Por debajo de 860 px la barra pasa a ser inferior. |

## Trama

- La página entera lleva una trama de puntos de `ink` de 0,55 px cada 7 px al 5 % de opacidad: el
  papel impreso. No la quites ni la dupliques.
- Las métricas llevan su propia trama de 1,4 px cada 7 px al 10 %, en `magenta`, `cyan`, `magenta` y
  `yellow` según su orden.
- Los estados vacíos llevan una esquina de trama de `cyan` (1,7 px cada 8 px, 22 %) abajo a la
  derecha, detrás del texto y con tamaño fijo.
- Portada que falta: `ui.portada` pone siempre debajo un marcador de una tinta (`cyan`, `magenta` o
  `yellow`) con la trama de otra (1,6 px cada 8 px) y la inicial en Anton; la `<img>` va encima y lo
  tapa si llega. Nunca una imagen rota ni `onerror=`. El color no significa nada.
- La trama va donde no hay nada que leer encima: detrás de texto, como mucho al 5–10 %; sin texto,
  hasta ~30 %. El desalineamiento de planchas (cian y magenta corridos) va solo en el rótulo de la
  página de error.
- Con `prefers-contrast: more` o `forced-colors`, todas las tramas y el desalineamiento se apagan.
  Cada trama nueva se añade a ese bloque, al final de la hoja (lo exige una prueba).

## Iconografía

### Logos

El estallido «¡ZAS!»: una Z rotulada en blanco (`#FFFFFF`) con contorno y sombra de tinta (`ink`,
`#17171A`), que sobresale un poco de un estallido de puntas cóncavas en `bermellon` (`#F2542D`). Son
las tres tintas de la marca. El papel `#F6F3EC` es el fondo del cuadrado, y la trama
`bermellon-trama` (`#C2391A`) solo aparece en el dibujo completo. Los colores van fijos en cada SVG,
no siguen el tema.

- `zascarr-icono.svg`: dibujo de interfaz, de 24 a 48 px, sobre cuadrado de papel redondeado. Es el
  fondo de `.brand::before` (barra lateral a 32 px).
- `zascarr-favicon.svg`: por debajo de 24 px (mínimo 16). Sin fondo: el estallido es la silueta, con
  contorno de tinta para las pestañas claras.
- `zascarr-favicon-32.png`: respaldo del favicon para navegadores sin SVG.
- `zascarr-completo.svg`: dibujo completo con trama y líneas de impacto. Solo grande (desde ~96 px);
  es la fuente del icono de iOS y no se sirve en ninguna página.
- `apple-touch-icon.png`: 180 × 180, rasterizado del completo, para la pantalla de inicio de iOS.

Espacio libre de ¼ del lado. Decorativa: el nombre lo dice el texto de al lado. Nada de amarillo en
la marca. En negro sobre claro funciona; sobre fondo oscuro haría falta una versión invertida que
hoy no existe (el icono de interfaz ya lleva su papel).

### Iconos

Los iconos de la interfaz son SVG de trazo de Lucide (ISC), en línea con `icono(nombre)` de
`web/iconos.py`: rejilla de 24, trazo de 2 y `stroke="currentColor"`, así que toman el color del
enlace. Van con `aria-hidden` junto a una etiqueta de texto.

Menú (grupo de assets Icons): `inicio` (`house`), `revisar` (`inbox`), `biblioteca` (`library`),
`duplicados` (`copy`), `descubrir` (`search`), `deseados` (`star`), `estado` (`activity`),
`ajustes` (`settings`) y `mas` (`ellipsis`); entre paréntesis, el nombre en Lucide. Nunca caracteres
de texto (⌂ ✎ ★…), que cada sistema dibuja distinto. Un icono nuevo se copia de `lucide-static`
1.60.0 al diccionario.

Los estados de chip y aviso siguen usando sus glifos ✓ ! ? i. Los puntos de semáforo de `/estado`
llevan el mismo glifo que el chip de su color (verde ✓, rojo !, amarillo ?), dibujado con los trazos
de Lucide en `static/iconos`.

En la app van a 20 × 20 px: `ink-soft` en reposo, `ink` al pasar, `on-yellow` en la entrada activa.

## Maquetación

- Escritorio: barra lateral de `side` (244 px) con borde derecho de 3 px y contenido de hasta
  1240 px.
- ≤ 860 px: la barra pasa arriba y el menú a una barra inferior fija de cinco entradas (Inicio,
  Revisar, Deseados, Estado y «Más»).
- Separación entre tarjetas: `--gutter`, `clamp(14px, 2.2vw, 24px)`.
- Rejillas de portadas con `auto-fill` y mínimos de 150, 160 o 200 px; portadas siempre en proporción
  2:3.
- Las filas de lista hacen `flex-wrap: wrap`: lo que no cabe baja de línea, no se oculta ni se
  encoge.

## Interacción y accesibilidad

- Foco visible siempre: contorno de 3 px en `cyan-t` con separación de 2 px.
- Objetivos táctiles de al menos 40 px: botones, enlaces del menú (44 px) y paginación. Casillas y
  radios de 24 px con `accent-color` `mag-t`.
- En el móvil y en pantallas táctiles (≤ 860 px o `pointer: coarse`): los campos miden ≥ 16 px de
  letra (iOS no amplía al enfocarlos), los controles ≥ 44 px de alto y nada desborda en horizontal.
- Todo `input`, `select` y `textarea` sin regla propia hereda la base de tinta (`:where`, sin
  especificidad): nunca el aspecto blanco del navegador en el tema nocturno.
- `color-scheme` sigue al tema.
- Un botón deshabilitado (p. ej. con `hx-disabled-elt` mientras corre la petición) no se levanta al
  pasar.
- Lo que cambia tras una acción HTMX cae en una `ui.region_viva` (`aria-live="polite"`); un aviso
  warn usa `role="alert"`, el resto `role="status"`.
- Sin diálogos nativos para lo importante; la confirmación es un paso visible en la página.
- Movimiento mínimo: transiciones de 0,12–0,15 s en transformaciones y un toast que se desvanece en
  8 s solo con CSS. Con «reducir movimiento» se apaga todo y el toast se queda.
- Un `<progress>` nativo para el progreso: rol y valor accesibles sin ARIA a mano.

## Cómo se usa

Enlaza `/static/web.css` (declara las `@font-face` de `/static/vendor/fonts`),
`/static/vendor/htmx.min.js` (vendorizado, con `defer`) y los iconos de `/static/brand` (favicon SVG,
PNG de 32 px y `apple-touch-icon`). No añadas otras hojas ni scripts.

Pinta los componentes con las macros:

- `ui.chip(estado, texto)`
- `ui.aviso(tipo, texto)`
- `{% call ui.grupo(título, recuento) %}`
- `ui.estado_vacio(título, texto, (etiqueta, url))`
- `ui.progreso(valor, máximo, etiqueta)`
- `ui.region_viva(id)`
- `ui.menu(ruta)`
- `ui.portada(título, id, src)`

Las clases heredadas (`.btn-primary`, `button[type="submit"].neutro`, `.issue-chip`,
`.legal-notice-warn`, `.estado-dot`, `.topnav`) siguen funcionando hasta la V14. No las uses en
pantallas nuevas.

## Componentes

### Estado

#### Aviso

Un mensaje en bloque tras una acción o sobre el estado de una pantalla: caja con borde de 2 px en
`ink`, fondo teñido del tipo, icono y texto en `ink`.

- **Uso:** `{{ ui.aviso(tipo, texto) }}` o `{% call ui.aviso(tipo) %}…{% endcall %}` (esta forma
  admite enlaces). `tipo ∈ nota | info | ok | amber | warn`. `nota` es la didascalia.
- **Roles:** `warn` va con `role="alert"` (interrumpe al lector de pantalla); el resto, con
  `role="status"`.
- **Lo que pones tú:** qué ha pasado y qué hacer, en frases completas. Di también lo que NO ha
  pasado cuando importa («no se ha repetido nada»).
- **No hagas:** usar `warn` para algo que no exige atención, ni apilar varios avisos del mismo tipo.

#### Chip

La etiqueta de estado: una píldora (`radius-pill`) con borde de 2 px en `ink`, icono y de una a tres
palabras en `chip`.

- **Uso:** `{{ ui.chip(estado, texto) }}`, con `estado ∈ neutro | ok | warn | amber | info`. El
  aspecto (clase e icono ✓ ! ? i) lo pone `web/componentes.py`. Un estado desconocido lanza un error.
- **Colores:** `ok-bg` / `ok-t`, `warn-bg` / `warn-t`, `amber-bg` / `amber-t`, `info-bg` / `cyan-t`;
  el neutro, `paper` / `ink`.
- **Lo que pones tú:** el texto («Hecho», «Toca ahora», «12 carpetas»). Si la etiqueta es larga
  (p. ej. en Pendientes por carpeta), el contenedor deja que se parta y pasa a `radius-panel`.
- **No hagas:** escribir `<span class="chip ok">` a mano ni elegir el estado por el color que quieres
  ver.

#### Didascalia

La cajita amarilla de narración, en dos papeles: la didascalia (`.caption`), que se lee, y el rótulo
(`.rotulo`), que etiqueta.

- **Didascalia:** caja `caption-bg` con borde de 2 px en `ink`, `radius-panel` y sin sombra. Texto en
  `didascalia` (0.9rem a 600, interlineado 1.5) y hasta 70ch. Úsala para una nota que acompaña: una
  confirmación («guardado y aplicado»), de dónde sale una propuesta o el aviso legal
  (`.legal-notice-warn`, heredada).
- **Rótulo:** pegatina en línea `caption-bg` con `shadow-ink-sm`, en `etiqueta` (mayúsculas,
  interletraje .12em) y girada -1,2°. Solo para ≤ 3 palabras: la fuente («Tebeosfera») o la tradición
  («Europea»).
- También con macro: `ui.aviso("nota", texto)` pinta la didascalia.
- **No hagas:** poner una frase en `.rotulo` ni devolver las mayúsculas a `.caption`.

#### HeroState

El estado grande de una pantalla («Todo bien», «Atención»): viñeta con `shadow-ink`, fondo teñido
(`ok-bg`, `warn-bg`, `amber-bg`, `info-bg`), un icono de 2.75rem y texto en `ink`.

- **Lo que pones tú:** el icono (`aria-hidden`), un título corto y una frase con el detalle.
- **Uso:** uno por pantalla, arriba. Está definido desde la V2, pero ninguna plantilla lo usa
  todavía.

#### InsigniaEstado

Estado de una fila de Deseados: un `ui.chip` cuyo aspecto decide
`services/estado_deseo.py::aspecto_de_deseo`. La antigua `.wishlist-badge` se retiró en #391.

- **Estados:** `wanted` («Por buscar») y `retirado` (lo retiró la política, no falló nada) son
  neutros. En marcha (`searching`, `downloading`, `downloaded`) son info con «i». `imported` es ok con
  ✓ («En tu biblioteca») y `failed` es warn con ! («Sin resultados»). Un estado sin aspecto hace
  fallar la página.
- **Lo que pones tú:** nada en la plantilla, que pinta `ui.chip(row.aspecto, row.estado)`. Al lado va
  el motivo en `.wishlist-motivo` (cursiva en `ink-soft`), no otro chip.

#### Progreso

Barra de progreso: `<progress>` nativo con borde de 3 px en `ink`, `radius-pill`, fondo `paper-2` y
relleno `yellow`.

- **Uso:** `{{ ui.progreso(valor, maximo, etiqueta) }}`. La etiqueta es el nombre accesible («Archivos
  revisados»).
- **No hagas:** simular progreso con un temporizador; solo el progreso real.

#### Semaforo

El semáforo de `/estado`: un resumen con punto grande (22 px) y una fila por servicio con punto
pequeño (16 px), nombre y frase de estado.

- **Puntos:** `.estado-dot.estado-ok` (`ok`, con ✓), `-warn` (`yellow`, con ?), `-bad` (`warn`, con !)
  y `-neutral` (`ink-faint`, sin glifo), todos con borde de 2 px en `ink`. El glifo es el mismo que el
  del chip de su color, en el par oscuro fijo; así el estado no depende solo del color (verde y rojo
  se confunden con daltonismo).
- **Lo que pones tú:** la frase concreta de cada servicio («Sin conexión con PostgreSQL»), nunca un
  código. Una VPN caída es aviso, no error.
- **Ojo:** la frase de al lado sigue siendo obligatoria, y con `forced-colors` los puntos se quedan
  sin fondo. Hoy el marcado lo monta JS en línea en `estado.html`; la V9 lo pasa a HTMX.

#### Toast

Aviso temporal sobre `caption-bg` con borde de 3 px y `shadow-ink-sm` que se desvanece a los 8 s solo
con CSS (en el PDF, con la animación parada).

- **Regla:** el estado definitivo tiene que estar visible también en la página; el toast solo lo
  repite. Con «reducir movimiento» no se desvanece.
- Definido en la V2; todavía sin uso en las plantillas.

### Acciones

#### Boton

El botón de tinta: borde de 2,5 px en `ink`, `radius-panel`, `shadow-ink-sm`, etiqueta en `boton` y al
menos 40 px de alto (44 px en táctil).

- **Principal:** `.btn.primary` o `button.primary`, con relleno `yellow` y texto `on-yellow`. Es LA
  acción que hace avanzar la tarea de la pantalla, una por pantalla.
- **Neutro por defecto:** un `<button>` o un `type="submit"` sin clase va sobre `paper`. Así van los
  que se repiten (uno por fila o por tarjeta) y los «Guardar» de Ajustes.
- **Variantes:** `.btn.sm` (sigue teniendo 40 px), `.btn.ghost` (subrayado y sin borde) para la salida
  secundaria, `.btn-ignorar` (sin sombra, en `warn-t` al pasar) para descartar y `.btn-reintentar`
  (`cyan-t`) para repetir. El verde `.btn-sugerencia` (`ok-solid`) es la excepción con significado
  propio: aceptar una sugerencia («Sí, organizar»).
- **Gesto:** al pasar sube 2 px y la sombra crece a 5 px; al pulsar baja 1 px. Con `disabled` queda al
  50 %, sin sombra y sin levantarse.
- **Lo que pones tú:** un verbo con su objeto («Buscar en las fuentes»), `<a class="btn">` para
  navegar y `<button>` para actuar.
- **Heredado (V14):** `.btn-primary` y `button[type="submit"].neutro`. Usa `.btn.primary` y nada.

### Formularios

#### Campo

Campos de formulario: borde de tinta (2,5 px en barras de filtro, 2 px en ajustes y login),
`radius-panel`, fondo `paper` y 40 px de alto. El foco suma `shadow-ink-sm` y el contorno `cyan-t`.

- **Etiqueta:** encima del campo, en negrita a 0.875rem. La ayuda va en `.ajustes-hint` (`ink-faint`) y
  el error en `warn-t`.
- Casillas y radios de 24 px con `accent-color` `mag-t`. El marcador de posición, en `ink-faint`,
  cumple 4,5:1.
- **Lo que pones tú:** `Form(...)` con campos explícitos en el endpoint y nunca un valor real por
  defecto (`cambia_esto_ahora` como marcador obvio).

### Colección

#### ChipNumero

Un número de una serie en la ficha: `.issue-chip.issue-present` (lo tienes, con ✓ y relleno
`ok-solid`) o `.issue-missing` (te falta, borde discontinuo y texto en `ink-faint`).

- **Regla:** el estado no depende solo del color, sino de ✓ frente al borde discontinuo.
- Clase heredada; convivirá con el Chip hasta la V14.

#### Metrica

La cifra del Inicio: viñeta con trama de color propia, cifra en `cifra`, etiqueta en mayúsculas en
`ink-faint` y detalle en `secundario`.

- **Trama:** la tarjeta n.º 1 y la 3, en `magenta`; la 2, en `cyan`; la 4, en `yellow`, al 10 %.
- **Variantes:** `.metric-delta` (en `ok-t`, negrita) para lo positivo; `.metric-warning` pone la
  cifra en `warn-t`.
- **Lo que pones tú:** una cifra real, una etiqueta de tebeoteca y de dónde sale («calculados en 9
  series…»). Nunca cifras inventadas ni de relleno.

#### PortadaSerie

Tarjeta de portada (`.series-card`, también `.library-card`, `.discovery-card` y la ficha con
`.series-cover`): portada 2:3 con borde inferior de 3 px, título en una línea con elipsis y año en
`ink-faint`.

- **Portada en dos capas** (`ui.portada(titulo, clave, src, clase)`): un marcador SIEMPRE debajo y la
  `<img>` encima. Si la imagen carga, lo tapa; si no llega, se ve el marcador, sin JavaScript.
- **El marcador:** una de las tres tintas (`.portada-c`, `-m`, `-y`) con la trama de otra encima y la
  inicial en Anton, en el par oscuro fijo. El color sale de `series.id % 3`, o de un CRC32 del título
  cuando no hay id; no significa nada. La inicial es el primer carácter alfanumérico, en mayúscula, y
  va `aria-hidden`.
- **La `<img>`:** siempre con `alt=""` (el título va en texto), y sin alto, fondo, borde ni sombra
  propios. El marco va en el contenedor de cada contexto.
- **Portada:** siempre de la caché local (`/ui/series/{id}/portada`), nunca un `src` externo.
- **Rejilla:** `.series-grid` o `.library-grid` con `auto-fill` (150 y 160 px de mínimo) y
  `--gutter`.
- **Lo que pones tú:** el título, el año y el id de la serie.

### Contenedores

#### EstadoVacio

Lo que se ve cuando no hay nada: `paper-2` con borde discontinuo de 3 px, texto centrado en
`ink-soft`, una esquina de trama `cyan` abajo a la derecha (detrás del texto, tamaño fijo; se apaga
con contraste alto) y, si hay salida, un botón principal.

- **Uso:** `{{ ui.estado_vacio(titulo, texto, (etiqueta, url)) }}`. La acción es opcional.
- **Lo que pones tú:** qué falta, por qué y el siguiente paso, de tú («Cuando revises tu disco…»).

#### Grupo

Caja con cabecera: viñeta `paper-2` con `shadow-ink`, cabecera en `paper` separada por 3 px de `ink`,
título en rotulación y recuento opcional en chip neutro.

- **Uso:** `{% call ui.grupo(titulo, recuento) %}…{% endcall %}`. El contenido va dentro tal cual y
  pone su propio relleno.
- **Lo que pones tú:** un título que nombre el grupo y, si ayuda, el recuento (número o texto).

#### Pasos

Primeros pasos del Inicio: lista numerada (`ol.steps`) con un círculo por paso (estilo `numero-paso`),
título, chip de estado y, a veces, un botón.

- **Títulos:** son frases, así que van en `titulo-frase` (Archivo a 800, sin mayúsculas), no en Anton.
- **Estados:** `.hecho` (✓ sobre `ok-bg`; más bajo, borde de 2 px y sin relleno: deja constancia sin
  competir con el que toca), `.siguiente` (fondo `caption-bg`, `shadow-ink`, círculo `yellow` y
  `aria-current="step"`), `.bloqueado` (borde discontinuo) y pendiente (sin clase).
- **Reglas:** el estado se lee por el texto del chip («Hecho», «Toca ahora», «Después», «Aún no se
  puede», «Opcional»), no solo por el color. Solo el paso siguiente lleva botón principal; el resto,
  `.btn.sm`.
- Los datos los calcula `services/inicio.py`; la plantilla solo los pinta.

#### Tarjeta

La viñeta base: `paper-2`, borde de 3 px en `ink`, `radius-panel` y 20 px de relleno (`.card`).

- **Familia:** la misma regla viste `.pending-card`, `.wishlist-row`, `.library-card`, `.metric-card`,
  `.discovery-card` y `.ajustes-card`. Las tarjetas que enlazan suben 3–4 px y ganan `shadow-ink` al
  pasar.
- **Lo que pones tú:** un `<section>` con título y contenido.

### Marca

La marca de ZascArr: el estallido «¡ZAS!» (una Z rotulada en blanco, con contorno y sombra de tinta,
que sobresale de un estallido `bermellon`) seguida del nombre en rotulación.

- **Marcado:** `<a href="/ui/" class="brand">ZascArr</a>` dentro de `.side`. El `::before` pone
  `zascarr-icono.svg` de fondo, a 32 × 32 px (28 en `.topnav`). La imagen es decorativa: el nombre lo
  dice el texto, que el CSS pone en mayúsculas con el estilo `marca`.
- Un dibujo por tamaño (grupo de assets Logos): `zascarr-icono.svg` de 24 a 48 px;
  `zascarr-favicon.svg` por debajo de 24 px (mínimo 16 px; también la cabecera móvil a 18 px); y
  `zascarr-completo.svg`, con trama y líneas de impacto, solo a 180 px (`apple-touch-icon.png`).
- **Espacio libre:** ¼ del lado alrededor (8 px a 32 px). Nada lo toca.
- **No hagas:** amarillo en la marca (es el color de acción, y el de Mylar3, Kapowarr y Radarr), meter
  la Z dentro del estallido (recuerda a Komga), usar la versión completa por debajo de ~96 px ni
  redibujarla.

### Navegación

#### Menu

La navegación principal: una sola lista (`web/menu.py`) que se presenta como barra lateral en
escritorio y, por debajo de 860 px, como barra inferior de cinco entradas más el panel «Más».

- **Uso:** `{{ ui.menu(request.url.path) }}`. Nunca se escribe un enlace del menú a mano en una
  plantilla.
- **Aspecto:** entradas en `nav` e `ink-soft`, con 44 px de alto. Al pasar ganan borde de `ink`; la
  activa (`aria-current="page"`) va en `yellow` / `on-yellow` con `shadow-ink-sm`. Las cabeceras de
  grupo, en `etiqueta` e `ink-faint`.
- **Contadores:** `.badge` (píldora con borde de 2 px), `.badge.hot` (`hot` / `on-hot`) para Por
  revisar y `.dot` amarillo para Estado. Salen ocultos (`hidden`) y los rellena `GET
  /ui/_nav/estado` cada 30 s.
- **Grupos:** Mi colección, Añadir y Sistema.
- **Iconos:** SVG de trazo de `web/iconos.py` (Lucide, 20 × 20 px en `.ico-svg`), con
  `stroke="currentColor"`: toman el color del enlace en reposo, activo, al pasar y en el tema
  nocturno.

#### Paginacion

Paginación de la biblioteca: enlaces con borde de 2,5 px, 40 px de alto y la página actual invertida
(`ink` de fondo, texto `paper`).

- **Lo que pones tú:** `aria-current="page"` en la actual y textos «Anterior» y «Siguiente» con
  flecha.

#### PasosAsistente

Dónde estás en un recorrido de varias pantallas (carpeta → serie → revisión → vinculación): una fila
de pasos numerados, solo con CSS.

- **Estados:** `.actual` (número sobre `yellow` / `on-yellow`, texto en `ink` y `aria-current="step"`),
  `.hecho` (número sobre `ok-bg` en `ok-t`) y `.pendiente` (círculo discontinuo). Los demás textos,
  en `ink-soft`.
- **Lo que pones tú:** un `aria-label` en el `<nav>` que diga qué recorrido es, y el estado de cada
  paso en texto para el lector de pantalla (`<span class="sr">`). El número es decorativo.
- **Macro:** `_asistente_macros.html`. No confundir con Pasos, la lista de primeros pasos del Inicio.

## Propuestas desde la portada

> **Solo la propuesta 1 está adoptada** (en #390, `main@e2edc44`; su forma final está en
> PortadaSerie). El resto **no está adoptado ni existe en `web.css`**: son ideas para discutir, con su
> maqueta en el grupo de componentes «Propuestas». Para construir una pantalla de hoy, sigue este
> documento.

### Qué hace bien la portada que la app aún no hace

1. **El color se ve.** La portada usa el CMYK a tono pleno, en bloques. La app lo reserva al amarillo
   de acción y a tramas del 5–10 %: la identidad «cuatricromía» casi no aparece fuera del logo.
2. **Composición de página, no de rejilla.** Viñetas de tamaños distintos, a ras y con un medianil fijo
   de 12 px, con una losa que manda. La app repite tarjetas iguales en `auto-fill`.
3. **Jerarquía por tamaño.** El nombre enorme en Anton con una línea pequeña debajo: se lee primero lo
   primero.
4. **El rótulo como cinta.** La pegatina girada se monta sobre el canto de una viñeta, no ocupa su
   propia línea.
5. **Funciona en los dos temas sin cambiar nada:** los bloques plenos aguantan el oscuro mejor que las
   tarjetas casi negras.

### Las propuestas, de más a menos rentable

| # | Propuesta | Qué toma de la portada | Coste | ¿Toca alguna regla? |
|---|---|---|---|---|
| 1 | **PropuestaPortadaFaltante:** la portada que falta como viñeta de color con trama y la inicial | Bloque CMYK con trama | Bajo: un `<span>` decidido en el servidor; elimina los `onerror=` | No: el color es decorativo (`id % 3`) |
| 2 | **PropuestaInicio:** el Inicio como página de viñetas, con la losa «Toca ahora» y cifras satélite | Losa con satélites, medianil y cinta | Medio: solo la plantilla y CSS grid; mismos datos | No: un principal y la sombra solo en lo que se pulsa |
| 3 | **PropuestaCabecera:** una tira de tres viñetas junto al título, con el color de la zona del menú | Bloques plenos y trama | Bajo: ~15 líneas de CSS y un bloque en `base.html` | No: el color orienta y no significa; se apaga en móvil y con contraste alto |
| 4 | **PropuestaMomentoMarca:** una losa bermellón con la marca en login, error y primer arranque | La losa bermellón | Bajo: CSS y un SVG que ya existe | Sí: «bermellón solo en la marca». Decisión de producto |

### Lo que tienen en común (y conviene fijar antes que nada)

- Un token **medianil** de 12 px para el hueco entre viñetas que se tocan. Es el primer paso de la
  escala de huecos que pide la revisión (deuda 2).
- La trama a tono pleno solo sin texto encima, como ya dice CLAUDE.md §6 (hasta ~30 %). Las cuatro
  maquetas la ponen en bloques sin texto, o con una sola letra decorativa.
- Todo se apaga con `prefers-contrast` y `forced-colors`, como las tramas actuales; cada bloque nuevo
  se añade a ese bloque del final de la hoja.
- Nada de imágenes ni JS: gradientes radiales y CSS grid. En la Pi, unos cientos de bytes más de CSS.

### Lo que la portada no autoriza

- No hay que torcer más cosas. El único giro sigue siendo el del rótulo.
- El amarillo no se convierte en decoración: sigue siendo la acción. En la portada es una tira
  pequeña, no la losa.
- El desalineamiento de planchas sigue solo en la página de error.

### PropuestaCabecera

**Propuesta, no adoptada.** La cabecera de cada pantalla como la portada: el título en Anton y la
frase de entrada a la izquierda, y a la derecha una tira de tres viñetas a ras, separadas por un
medianil de 12 px.

- **De la portada:** bloques CMYK a tono pleno, con trama de otro color y bordes de tinta. Hoy el CMYK
  solo aparece al 10 % en las métricas; aquí se ve, pero en un sitio sin nada que leer encima.
- **Color por zona del menú, no por estado:** Mi colección en `cyan`, Añadir en `magenta` y Sistema en
  `ink`. Es orientación y no significado: la zona también la dicen el título y el menú, así que el
  color nunca va solo.
- **Coste:** unas 15 líneas de CSS, sin imágenes ni JS. En `base.html`, un bloque `cab` con la zona
  que ya calcula `web/menu.py` (`entrada_activa`).
- **Accesibilidad:** las viñetas son decorativas (`aria-hidden`), desaparecen por debajo de 860 px y
  se apagan con `prefers-contrast` o `forced-colors`, como las demás tramas.

### PropuestaInicio

**Propuesta, no adoptada.** El Inicio maquetado como una página de tebeo. La viñeta grande, a la
izquierda, es lo que toca ahora; a la derecha, las cifras se reparten en viñetas de distintos tamaños
con el mismo medianil de 12 px. Hoy son una rejilla de tarjetas iguales y una lista de pasos debajo.

- **De la portada:** la losa grande con satélites, a ras y con medianil fijo. Y el rótulo pegado sobre
  el canto de la viñeta, como una cinta (`.rotulo` con `position: absolute`), que dice el estado sin
  ocupar una línea.
- **Jerarquía:** la única viñeta con sombra y botón principal es la del siguiente paso: un botón
  principal por pantalla y la sombra solo en lo que se pulsa. Las cifras no llevan sombra.
- **Presupuesto de texto:** cabe en él, con una frase de entrada y una de ayuda antes del botón.
- **Coste:** solo CSS grid. `services/inicio.py` ya calcula `pasos.principal` y las cifras: la
  plantilla cambia de disposición, no de datos. En móvil pasa a dos columnas y la viñeta grande ocupa
  todo el ancho.

### PropuestaMomentoMarca

**Propuesta, no adoptada, y toca una regla.** En las pantallas sin tarea de colección (login, página de
error y primer arranque), una viñeta `bermellon` con su trama y la marca grande, como la losa de la
portada.

- **De la portada:** la losa bermellón es lo primero que se reconoce. Hoy el bermellón solo existe en
  un icono de 32 px.
- **La regla:** CLAUDE.md §6 y el README de la marca dicen que el bermellón es «solo de la marca». Aquí
  la viñeta enmarca la marca, así que puede leerse como uso de marca, pero también como un fondo de
  interfaz. Es una decisión de producto, no la doy por hecha.
- **Límites si se adopta:** solo en pantallas sin nada que hacer con la colección; nunca detrás de
  texto ni en un botón; el amarillo sigue siendo solo de la acción («Entrar»).
- **Coste:** CSS y el `zascarr-completo.svg` que ya existe (hoy solo alimenta el icono de iOS), así que
  no hay fichero nuevo. `login.html` vive fuera de `base.html`: el cambio es local.

### PropuestaPortadaFaltante

**Adoptada en #390** (`main@e2edc44`); la forma final está en PortadaSerie. Esta ficha se queda como
registro de la propuesta.

Cuando falta la portada, en lugar de la trama gris de `.cover-missing`, una viñeta de color pleno con
trama y la inicial de la serie en Anton. Una biblioteca recién importada, con muchas portadas sin
descargar, deja de ser una pared gris y pasa a parecerse a la portada.

- **De la portada:** el bloque CMYK a sangre con la trama de otro color encima.
- **El color no significa nada:** sale de `series.id % 3` (`cyan`, `magenta` o `yellow`), así que no
  codifica la tradición ni el estado y no hay nada que leer solo por el color. La inicial es
  decorativa (`aria-hidden`); el título sigue siendo texto debajo.
- **Contraste:** la inicial va en el par oscuro fijo (`on-yellow`, `#17171a`), que se lee sobre los
  tres rellenos en los dos temas: el más justo, sobre `magenta` en claro, da 3,68:1, suficiente para
  texto grande y decorativo (el resto va de 5,3 a 12,4). Con contraste alto, papel liso.
- **Lo que cambió al implementarla:** el servidor no puede saber si habrá portada, porque la caché se
  llena al pedirla. Así que el marcador no sustituye a la `<img>`: va siempre debajo y la imagen lo
  tapa si llega. Sin candidato de serie, el color sale de un CRC32 del título. Se van los cinco
  `onerror=`.

## Revisión

Estado de `web.css` y de las plantillas en `main@76e7812` (13 de noviembre de 2026), comparado con la
revisión anterior (`f8fc17b`). Primero lo que funciona y lo que se ha cerrado, para no romperlo;
después la deuda abierta, de más a menos grave.

> **Si vas a hacer una pantalla nueva, no copies ninguno de los problemas abiertos.**

### Lo que está bien y hay que conservar

- **El contraste está garantizado por la CI.** Los colores no han cambiado: todos los pares de texto
  pasan 4,5:1 en los dos temas, y el más justo sigue siendo `ink-faint` sobre `paper-2` en claro, con
  4,96:1. La separación relleno/texto (`cyan` frente a `cyan-t`) y las parejas `on-*` siguen
  intactas.
- **Un único vocabulario de estados** (`web/componentes.py`), y ahora también **un único juego de
  iconos** (`web/iconos.py`). Un nombre desconocido hace fallar la página en vez de pintar un hueco.
- **Identidad propia y ligera:** dos fuentes libres del subconjunto latino (unos 93 KB entre las
  tres), una marca con tres dibujos por tamaño, iconos en línea y ni un CDN.
- **Accesibilidad:** foco de 3 px que ya no se pierde en los campos, objetivos de 44 px en táctil,
  campos de 16 px en el móvil, `prefers-reduced-motion`, y ahora también `prefers-contrast` /
  `forced-colors`, que apagan las tramas.

### Cerrado desde la revisión anterior

- La letra de cartel ya existe en la Pi. Anton y Archivo se sirven desde `static/vendor/fonts` (OFL);
  Impact queda de respaldo.
- La didascalia ya no se usa para párrafos (U17). `.caption` es ahora una caja de lectura: sin
  mayúsculas, sin giro ni sombra, a 0.9rem y como mucho 70ch. Las mayúsculas y el giro pasan a
  `.rotulo` (4 usos).
- El botón principal lo decide la intención (`button.primary`, `.btn.primary`). Un envío es neutro, y
  `.neutro` queda solo por compatibilidad.
- Lenguaje técnico en `/estado`: el subtítulo ya no habla de «JSON crudo».
- La sombra dura nocturna (#384): un `--shadow-color` por tema (gris de tinta `#6f6d76` en oscuro,
  ≥ 3:1 sobre los dos papeles) y los tokens `--shadow-ink-hover` / `--shadow-ink-active`: ya no
  desaparece en reposo ni sale crema al pasar.
- `ruff` limpio en `src/` (#387), con un hallazgo de seguridad real cerrado de paso: el tagger leía el
  `ComicInfo.xml` del CBZ sin tope (bomba de descompresión).
- La portada que falta, sin JavaScript (#390): `ui.portada` pone SIEMPRE un marcador debajo (color de
  imprenta con trama e inicial, `web/portada_marca.py`) y la `<img>` encima; si la portada no llega,
  se ve el marcador. Se van los cinco `onerror=` y la clase `.cover-missing`. La `<img>` no lleva
  alto, fondo, borde ni sombra propios: con ancho y alto fijados, Chromium pinta el icono de imagen
  rota aunque el `alt` esté vacío.
- Verde y rojo ya no dependen solo del matiz (#391): cada punto de `/estado` lleva el glifo del chip
  de su color (verde ✓, rojo !, amarillo ?), en el par oscuro fijo y con ≥ 3:1 en los dos temas (lo
  fija una prueba; el más justo, el rojo en claro, da 3,29:1). Las filas de Deseados pasan a `ui.chip`
  con el aspecto de `services/estado_deseo.py` (✓ en tu biblioteca, ! sin resultados, i en marcha). Se
  retira `.wishlist-badge`.
- El mínimo de 14 px, declarado y medido (#395): la prueba ya no se salta los `clamp` (cuenta su
  mínimo), y `var()`, `inherit` y `cqw` fallan salvo lista explícita con motivo. La etiqueta de la
  barra inferior del móvil es la única excepción (12 px, por debajo de 424 px de ancho): «Deseados»
  ocupa 65,5 px a 14 px y la columna a 320 px deja 62. Una excepción que deja de hacer falta hace
  fallar la prueba. La regla está ahora en CLAUDE.md §6.
- Cada estado se tiñe con su token (#396): `.suggestion` y `.audit-ok` pasan a `ok-bg` y
  `.legal-notice-info` a `info-bg`, el mismo tinte que los avisos de su estado (el cambio más visible,
  ok en oscuro, ΔE 10,2; todo el texto sigue ≥ 5,1:1). Eran 7 usos de `color-mix()` en 6 reglas;
  quedan 3, decorativos y declarados con su motivo (los dos separadores discontinuos y el
  desalineamiento del rótulo de error). Una prueba hace fallar cualquier `color-mix()` nuevo, en
  cualquier propiedad.
- Revisión recorriendo la app (#689, con una biblioteca de prueba de 22 CBZ, a 1280 y 375 px):
  - **Búsquedas:** responden a `input` y no solo a `keyup`, que no salta al pegar ni con
    autocompletado; eran 7.
  - **Duplicados:** un solo botón principal (registrar).
  - **Resumen del registro:** no cuenta ceros ni dice «1 repetidos».
  - **Descubrir sin fuentes:** enseña abierta el alta a mano, y tras crear una serie ofrece «Añadir
    números del disco».
  - **Por revisar:** «Ignorar» va al pie de cada tarjeta y el especial ya no se sale.
  - **Ficha de serie:** los datos van junto a la portada.
  - **Pruebas:** una regresión por hallazgo en `tests/test_revision_ux_2026_11.py`.
- De paso: el foco de los campos ya no se borra (`outline: none` daba 1,14:1 en oscuro), los botones
  deshabilitados no se levantan y los títulos de dos líneas tienen 1.15 de interlineado para que las
  tildes no se toquen.

### Deuda abierta, de más a menos grave

1. **La escala de texto sigue sin nombre.** Hay 90 declaraciones de `font-size` y 19 valores distintos,
   con los mismos casi duplicados (`.875`, `.88`, `.9`, `.92` y `.95rem`). Propuesta: fijar los estilos
   de este sistema como variables y redondear los demás a ellos.
2. **Espaciado y grosores sin tokens.** Los huecos siguen en literales, y los grosores de borde siguen
   una regla que solo vive en este README. `.vinc-fila` sigue con `1px solid currentColor`, y la nueva
   `.archivo-fila` separa con 1 px de `paper-2`, que dentro de una viñeta `paper-2` no se ve.
   Propuesta: `--border-panel`, `--border-control` y `--border-chip`, y una escala corta de huecos.
3. **CSS heredado pendiente de la V14.** Ninguna plantilla usa `.topnav`, que acaba de recibir reglas
   nuevas (el favicon a 18 px). `.btn-primary`, `.issue-chip`, `.legal-notice-warn` y `.estado-dot`
   conviven con sus sustitutos (`.wishlist-badge` ya se retiró en #391). `/estado` sigue montando sus
   filas con JS en línea (V9). `.hero-state` y `.toast` siguen sin uso.
4. **Clases de plantilla sin regla CSS: 41, antes unas 25.** Casi todas son ganchos de pruebas o de
   HTMX. Hay que revisar `btn-secondary`, en `_auditoria_registro.html`: un nombre de variante que no
   existe en la hoja (las variantes son `.ghost` y `.sm`).
5. **«Tu biblioteca está limpia» va solo con color y palabra.** `.audit-ok` (3 usos en
   `_auditoria_informe` y `_auditoria_registro`) es un mensaje de estado ok sin icono ni `role`, al
   contrario que `ui.aviso`. Propuesta: pasarlo a `ui.aviso("ok", …)`, que le da ✓, `role="status"` y
   el borde de tinta de los demás avisos (opción B de #396, aplazada).
6. **En Por revisar, la portada que falta o tarda mide 0 px** (decisión de U12), así que las tarjetas
   cambian de alto al cargar y una fila no se alinea. Propuesta: usar `ui.portada`, como en la
   Biblioteca. Revierte U12, así que la decide el PO.
7. **«En tu disco había 22 el 12 de noviembre»** (Inicio) no dice qué había. Propuesta: «22 tebeos». El
   texto lo fija `test_web_dashboard`.
