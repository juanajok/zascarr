# Especificación — BL-LEC3 (#826): el final del lector como página de fin (decisión D)

> **Estado: DISEÑO APROBADO E IMPLEMENTADO.** La **decisión D está aprobada** (2026-11-21):
> al llegar a la última página **no se muestra nada**; solo al intentar avanzar se entra en una
> **página de fin a pantalla completa**, con vuelta a la última página. Este documento no escribe
> código: **no toca plantillas, JS, CSS, endpoints, base de datos ni biblioteca**.
> **Base contrastada:** worktree `lec-fin-d`, rama `feat/lec-fin-d`, sobre `origin/main` =
> `303f5541bab49749a436e640fa88c5235caf5dc0` (2026-11-21). Implementación en `b2d58bd7` +
> ajustes de la revisión UI (barra oculta en la página de fin y restaurada al volver).
> **Insumo:** [`benchmark-BL-LEC-fin-lector-2026-11-21.md`](benchmark-BL-LEC-fin-lector-2026-11-21.md)
> (§2, §4 opción D, §5, §6, §7 y §8), [`benchmark-referencias.md`](benchmark-referencias.md),
> CLAUDE.md §6, §13 y §14, `docs/design/epica-BL-LECUX-lector.md` (LECUX2, D-LUX2) y el código vigente.
> **Notación:** requisitos **EARS** con palabras clave en español (CUANDO, MIENTRAS, SI/ENTONCES,
> DONDE); criterios **Given/When/Then**; pruebas con nombre en español, como el resto del repo.
> «#N» es el número que se está leyendo; «#K» el siguiente que decide `siguiente_numero` (#826).

---

## 0. Resumen ejecutivo

**Qué cambia.** La presentación del final del lector. Hoy `lector.js` abre solo una tarjeta modal
sobre la última página en cuanto se llega a ella (`lector.js:236-253`). Con la decisión D: la última
página se ve entera y, **solo cuando la persona intenta avanzar**, se entra en una página de fin que
ocupa el área de lectura completa, como contenido del flujo y no como capa. La vuelta (botón, tecla,
gesto o `Esc`) devuelve a la última página sin recargar ni pedir nada. La página de fin no cuenta
como página: no cambia el contador, no guarda progreso y no escribe nada.

| Aspecto | Hoy (verificado) | Con la decisión D |
|---|---|---|
| Al llegar a la última página | Aparece la tarjeta `#fin` sola | **Nada visible**; la página se ve entera |
| Al intentar avanzar en la última página | Nada (el "siguiente" está deshabilitado y `avanzar()` se acota) | Se abre la **página de fin** a pantalla completa |
| Naturaleza de `#fin` | Capa `absolute` abajo, tarjeta de hasta `42rem` | Página del flujo; no hay modal, ni backdrop, ni trampa de foco |
| Contador / progreso | No cambia (la tarjeta es una capa) | **No cambia**: «Página N de N»; sin `POST /progreso` |
| «Marcar leído» | Botón explícito en la tarjeta | **Botón explícito** igual; sin automatización |
| Servidor | Ya pinta `#fin` oculto en el GET | Igual: **sin endpoints nuevos ni cambiados, sin petición para decidir el final** |

---

## 1. Alcance exacto

### 1.1 Entra

Solo la **presentación del final**:

- `src/zascarr/web/templates/lector.html` y `src/zascarr/web/templates/_lector_fin.html`: estructura
  y contenido de la página de fin (`#fin`, título, portada, acciones, vuelta) y el estado inicial
  del control de avanzar.
- `src/zascarr/static/lector.js`: abrir/cerrar la página de fin **bajo intención**; retirar el
  mostrado automático desde `pinta()`; foco, anuncios, teclado y gestos; etiquetas del control de
  avanzar; hidratación de la portada.
- `src/zascarr/static/web.css`: la página de fin deja de ser tarjeta absoluta y pasa a ocupar el
  área de lectura; estados ocultos de imagen y flechas; tamaños y tinta del sistema de diseño.
- Pruebas: `tests/test_lector.py`, `tests/test_lector_js.py` y, si se añade, un fichero
  `tests/test_lector_fin_d.py`. Las pruebas de CSS existentes son puerta de regresión.

### 1.2 No entra (frontera explícita)

| Fuera | Por qué |
|---|---|
| **Endpoints** | No se crea ni se modifica ninguno: `GET /ui/leer/{id}`, `POST /leido`, `POST /deseo`, `POST /progreso`, `POST /sentido`, `GET /estado` y `GET /pagina/{n}` quedan congelados (§1.3) |
| **Base de datos** | Sin migración, sin columnas, sin consultas nuevas |
| **Biblioteca y archivos** | Sin mover, renombrar, convertir ni borrar; el lector sigue siendo de solo lectura |
| **Servicios** | `services/lector.py` (incluido `siguiente_numero`) y `services/lectura.py` no se tocan |
| **Macros compartidas** | No se cambia `_componentes.html` ni el sistema de diseño; la portada reutiliza `ui.portada` como está |
| **Dependencias** | Sin dependencias nuevas; el único JS sigue siendo `static/lector.js` (ADR 0021) |
| **Salto automático al siguiente** | Descartado como defecto (benchmark §4 E, §6) |
| **«Leído» automático** | **No aprobado**; se mantiene el botón explícito (§4, D-LEC-2) |
| **Menú/barra con «Fin del número»** | No se añade una entrada nueva: se entra solo al intentar avanzar (historia futura, si el PO la pide) |
| **Preferencia «seguir automáticamente»** | Otra historia posible, apagada por defecto |
| **Animaciones o intersticiales** | Solo un aparecer sobrio; sin transición de página ni vídeo |

### 1.3 Contratos congelados

- `GET /ui/leer/{file_id}`: misma URL, mismos códigos, mismas cabeceras (`Cache-Control: no-store`,
  `X-Content-Type-Options: nosniff`) y **mismas claves de contexto** para la plantilla. No se añade
  ningún parámetro de consulta ni variable de servidor que decida mostrar la página de fin.
- `POST /ui/leer/{file_id}/leido`: mismo campo `operacion` (`marcar`/`deshacer`), misma respuesta
  HTMX hacia `#fin-acciones` y mismo 303 sin HTMX.
- `POST /ui/leer/{file_id}/deseo`: mismo cuerpo y misma respuesta; solo cambia, en la plantilla, el
  `hx-target` del formulario a un bloque propio (`#fin-deseo`) para no borrar la vuelta.
- Progreso y sentido: `ReadingProgress` solo cambia con los caminos que ya existen; entrar, salir,
  repintar o abrir la página de fin **no escribe**. `siguiente_numero` no se modifica.
- Portada del siguiente: se sirve con la ruta **ya existente**
  `GET /ui/series/{serie_id}/numero/{issue_id}/portada.jpg` (`web/series.py:2048-2063`), con su caché
  privada; no se añade endpoint.

---

## 2. Hechos verificados en el código vigente

| # | Hecho | Evidencia |
|---|---|---|
| F1 | Al llegar a la última página, `pinta()` quita `hidden` a `#fin` sin gesto del lector | `static/lector.js:236-253` |
| F2 | `#fin` se pinta en el servidor **oculto y con todo el contenido**; el contexto ya trae `siguiente`, `leido` y `legal_aceptado` | `templates/lector.html:96-103`, `web/lector.py:75-83` |
| F3 | La tarjeta es una capa `position:absolute` abajo, máx. `42rem` y `calc(100dvh - 6rem)` de alto | `static/web.css:2879-2886`, `:2944-2949` |
| F4 | `#fin` se pinta en los tres estados: `siguiente_numero` siempre devuelve un `Siguiente` (`leer`, `falta` o `sin_siguiente`) | `services/lector.py:368-380`, `:389-433`; `templates/lector.html:96` |
| F5 | Avanzar en la última página no hace nada: `ir()` acota a `total` y sale si el destino es la página actual | `static/lector.js:274-285` |
| F6 | En LTR, el botón de avanzar (`#lector-siguiente`) lleva `aria-disabled="true"` en la última página, en el HTML del servidor y tras `pinta()`; en RTL el JS intercambia los papeles de los dos botones | `templates/lector.html:91-92`; `static/lector.js:236-253` |
| F7 | Pasan página: botones de flecha, teclado (`→`/espacio/`PageDown` según sentido) y, en táctil, deslizamiento y toque en la zona; el **clic de ratón en el lienzo no pasa página** (solo alterna la barra) | `static/lector.js:562-601`, `:622-693` |
| F8 | Con zoom > 1 los gestos y el arrastre mueven la imagen y no pasan página; las teclas sí siguen pasando | `static/lector.js:475-515`, `:640-684` |
| F9 | «Marcar leído» y «Añadir a Deseados» recambian `#fin-acciones`; la respuesta de Deseados trae solo un aviso y hoy borra el resto del contenido | `_lector_fin.html:2-28`; `web/lector.py:93-137` |
| F10 | La portada de un número ya tiene ruta local, 600 px y caché privada | `web/series.py:2048-2063` |
| F11 | El progreso solo se guarda al cambiar de página (`ir()` → `guarda()`) | `static/lector.js:264-281` |
| F12 | La página de fin no recibe el foco al aparecer: el `h2` tiene `tabindex="-1"` pero nadie lo enfoca; la restauración de foco solo existe tras un recambio HTMX | `templates/lector.html:98`; `static/lector.js:603-620` |

---

## 3. Glosario operativo (para leer los requisitos)

- **Última página**: la página `N` del tebeo o, en modo doble, la pareja visible que contiene `N`.
- **Intención de avanzar**: cualquiera de las formas que hoy pasan página hacia delante (F7): botón
  de avanzar, tecla de avance según sentido, deslizamiento de avance y toque en la zona de avance.
  En la última página no hay página siguiente: esa intención es la que **abre la página de fin**.
- **Intención de volver**: la contraria (botón/tecla/gesto de retroceso), más el control
  «Quedarme en esta página» y `Esc`.
- **Página de fin**: el contenido de `#fin` mostrado a pantalla completa dentro del lector; **no** es
  una página del tebeo (no cambia contador, no guarda progreso, no se cuenta).
- **Estados de `siguiente_numero`**: `leer` (el #K está en la biblioteca), `falta` (falta y los huecos
  son fiables) y `sin_siguiente` (no hay siguiente que se pueda afirmar).
- **Principal**: el único botón/enlace con `.primary` de la página (CLAUDE.md §6).

---

## 4. Decisiones

| # | Decisión | Origen |
|---|---|---|
| D-LEC-1 | **Opción D aprobada**: al llegar a la última página no se muestra nada; la página de fin se abre solo con intención de avanzar; la vuelta devuelve a la última página | PO, 2026-11-21 (benchmark §6 y §10) |
| D-LEC-2 | **«Marcar como leído» sigue siendo explícito.** No se marca al llegar, ni al abrir la página de fin, ni al salir: la automatización **no está aprobada**. Sin automatización no hay «Deshacer» por automatización | PO, 2026-11-21 |
| D-LEC-3 | La página de fin **no cuenta como página**: contador «Página N de N», `data-pagina` sin cambios, sin `POST /progreso` | benchmark §6.4 |
| D-LEC-4 | **Sin salto automático** al siguiente número ni preferencia en esta historia | benchmark §4 E, §6.6 |
| D-LEC-5 | **No es un modal**: sin `role="dialog"`, sin `aria-modal`, sin backdrop, sin trampa de foco; es contenido | benchmark §6.7, §6 «Qué NO se propone» |
| D-LEC-6 | **Sin petición ni endpoint nuevos para decidir o construir el final**: el servidor ya entrega la página de fin en el HTML | benchmark §6.8, §8 |
| D-LEC-7 | El título de la página es **«Fin del número»** (rótulo de ≤3 palabras, sin clase de frase larga); la frase «Has llegado al final» describía la tarjeta automática y no se conserva | esta especificación |
| D-LEC-8 | Un solo principal por pantalla: **«Leer el #K»** (`leer`) y **«Añadir a Deseados»** (`falta`); en `sin_siguiente` no hay principal. «Marcar como leído» queda **neutro** | CLAUDE.md §6 + benchmark §6.2 |
| D-LEC-9 | `Esc` en la página de fin **vuelve** a la última página y no cierra el lector; con Opciones abierta, `Esc` cierra Opciones primero (comportamiento vigente) | benchmark §7.8 |
| D-LEC-10 | La portada del siguiente número se muestra **solo** en estado `leer`, con la ruta local existente y **solo al abrir** la página de fin | benchmark §6.2/§6.8 + Pi |

---

## 5. Requisitos EARS

### 5.1 Flujo: llegar, avanzar, volver

- **FR-1 (llegar).** CUANDO la navegación deja visible la última página (o la pareja que la
  contiene), ENTONCES la página se ve completa, el contador dice «Página N de N» (en doble, «Páginas
  N−1–N de N»), `#fin` sigue con `hidden`, **no se mueve el foco**, no aparece ningún contenido nuevo
  y no se hace ninguna petición nueva. El único anuncio es el del contador que ya existe.
- **FR-2 (avanzar).** CUANDO, con la última página visible, se expresa intención de avanzar,
  ENTONCES se muestra la página de fin (`#fin.hidden = false`) **sin recargar, sin navegar y sin
  peticiones**; las imágenes de página y las flechas superpuestas dejan de verse; el foco pasa a
  `#fin-titulo`; la región viva anuncia «Fin del número.»; el contador **no** cambia.
- **FR-3 (avanzar en la página de fin).** CUANDO se expresa intención de avanzar estando en la página
  de fin, ENTONCES no ocurre nada: ni navegación, ni petición, ni cambio de foco, ni salto automático.
- **FR-4 (volver con el control).** CUANDO se activa `#fin-quedarme` estando en la página de fin,
  ENTONCES vuelve a verse la última página, `#fin` recupera `hidden`, el foco va a `#lector-lienzo`,
  la región viva anuncia el texto del contador, sin recarga ni petición, con el mismo zoom y la misma
  página/pareja de antes.
- **FR-5 (volver con teclas, gestos y `Esc`).** CUANDO, estando en la página de fin, se expresa
  intención de volver (teclas de retroceso según sentido, `PageUp`, `Shift+Espacio`; deslizamiento o
  toque en la zona de retroceso; `Esc`), ENTONCES se cumple FR-4. `Esc` no cierra el lector ni la
  página de fin; con Opciones abierta, `Esc` cierra Opciones primero; en pantalla completa, `Esc` es
  del navegador y no cierra la página de fin. Fuera de la página de fin, `Esc` mantiene su
  comportamiento actual.
- **FR-6 (repintados).** CUANDO `pinta()` se ejecuta por cualquier motivo (carga de imagen, cambio de
  modo, sentido, zoom, filtros de imagen, redimensionado), ENTONCES **nunca** abre la página de fin
  por sí misma y, si está abierta, no la cierra ni la recambia.
- **FR-7 (navegación intacta).** MIENTRAS no se ha abierto la página de fin, anterior/siguiente,
  `Home`/`End`, modos, zoom, filtros y `Esc` funcionan igual que hoy.
- **FR-8 (reentrada).** CUANDO se vuelve a la última página y se vuelve a intentar avanzar, ENTONCES
  la página de fin se muestra otra vez; una pulsación o gesto produce exactamente una transición.

### 5.2 Contenido de la página de fin por estado

| Estado | Cuándo | Frase | Principal | Otras acciones |
|---|---|---|---|---|
| `leer` | El #K está en la biblioteca | «Has terminado el #N. Siguiente: **#K**.» | «Leer el #K» → `/ui/leer/{archivo del siguiente}` | Marcar leído / Deshacer · Quedarme · Volver a la serie |
| `falta` | Falta el #K y los huecos son fiables | «Te falta el **#K** de *Serie*.» | «Añadir a Deseados» | Marcar leído / Deshacer · Quedarme · Volver a la serie |
| `sin_siguiente` | No hay siguiente que se pueda afirmar | «No hay un número siguiente en tu biblioteca.» | — | Marcar leído / Deshacer · Quedarme · Volver a la serie |

- **FR-9 (contenido).** SI el estado es `leer`, ENTONCES la página muestra todo lo de la fila `leer`
  y, si la portada responde, la del siguiente número (FR-12).
- **FR-10 (`falta` y puerta legal).** SI el estado es `falta` y el aviso legal **no** está aceptado,
  ENTONCES «Añadir a Deseados» es un enlace a `/ui/legal?volver=%2Fui%2Fleer%2F{id}` con el aviso
  «Antes tienes que leer y aceptar el aviso legal; después podrás pedirlo.» y **no** hay `hx-post`.
  SI el aviso está aceptado, ENTONCES es un formulario `hx-post` a la ruta existente `/deseo`, cuyo
  recambio se limita a `#fin-deseo`; al confirmarse se ve «Añadido a Deseados.» y la página conserva
  el texto, «Quedarme» y «Volver a la serie».
- **FR-11 (`sin_siguiente`).** SI el estado es `sin_siguiente`, ENTONCES no hay «Leer el #K» ni
  «Añadir a Deseados»; sí la frase, el marcado de leído y la vuelta.
- **FR-12 (portada del siguiente).** DONDE el estado es `leer`, la página de fin muestra la portada
  del siguiente número con la ruta local existente (F10), sin endpoint nuevo. La portada **no se pide
  antes** de abrir la página de fin (el HTML inicial no lleva `src`), se pide **como mucho una vez
  por apertura**, no bloquea el texto/acciones/foco y su caché es la privada de la ruta. Si falta o
  falla, se ve el **marcador de portada** de `ui.portada` (inicial y trama), nunca una imagen rota ni
  un mensaje de error. Es decorativa: `alt=""` (el texto ya dice «Siguiente: #K»).
- **FR-13 (textos).** Los textos visibles de la tabla son **literales**; español llano, sin jerga
  interna (`estado`, `sin_siguiente`, `tarjeta`, `modal` no aparecen). Los números van con «#». La
  frase de «Has terminado el #?» conserva el respaldo actual cuando no hay número.
- **FR-14 («Leído» explícito).** Entrar en la página de fin, salir o avanzar **no** marcan leído ni
  escriben `ReadingProgress`; solo el envío explícito de «Marcar como leído» (endpoint existente) lo
  hace. «Deshacer» vuelve a «En lectura» conservando nota y puntuación (comportamiento actual de
  `services/lectura.marcar`). No hay marcado automático, ni por llegar, ni por abrir, ni por salir.
- **FR-15 (tras una acción).** CUANDO se marca/deshace o se añade a Deseados desde la página de fin,
  ENTONCES la página sigue abierta, el foco no cae al `body`, el resultado se anuncia por la región
  viva y las acciones de vuelta siguen disponibles. El recambio de «Añadir a Deseados» se limita a
  `#fin-deseo`; el de «Marcar/Deshacer» mantiene `hx-target="#fin-acciones"` y vuelve a pintar el
  contenido del estado sin borrar la vuelta.

### 5.3 Entradas, modos y entornos

- **FR-16 (doble página).** SI la pareja visible contiene la última página, ENTONCES avanzar abre la
  página de fin aunque `data-pagina` no sea igual a N; volver deja visible **la misma pareja**; la
  página de fin es única (no se empareja con nada) y no usa «Desplazar la pareja».
- **FR-17 (RTL).** Las intenciones de avanzar y volver se definen por el **sentido de lectura**, no
  por la dirección física: con `sentido=rtl` la tecla y el gesto que avanzan son los contrarios que
  con `ltr`, y el texto de la página de fin no cambia de orden (es español, LTR).
- **FR-18 (zoom).** MIENTRAS el zoom es > 1, las teclas y el botón de avanzar siguen abriendo la
  página de fin; los gestos y el arrastre siguen moviendo la imagen y **no** abren la página de fin
  (regla vigente, F8). Entrar y salir no cambia el nivel de zoom; la página de fin no se amplía ni se
  desplaza con el zoom; el zoom tampoco impide el gesto de volver desde la página de fin.
- **FR-19 (pantalla completa).** Entrar o salir de la página de fin no cambia el estado de pantalla
  completa; salir de pantalla completa (tecla del navegador) no cierra la página de fin ni el lector;
  las acciones siguen accesibles en pantalla completa.
- **FR-20 (teclado).** Las teclas de avanzar/volver funcionan desde el lienzo, desde el título y desde
  zonas no interactivas de la página de fin. `Espacio`/`Enter` sobre un botón o enlace enfocado no se
  interceptan (actúan de forma nativa). En la página de fin, `Home`/`End` no hacen nada y el avance
  no hace nada (FR-3). El foco no queda atrapado: se puede salir a la barra con `Shift+Tab` y sus
  controles siguen operativos.
- **FR-21 (táctil y ratón).** En la última página, el deslizamiento de avance y el toque en la zona de
  avance abren la página de fin, igual que en el resto del tebeo; el toque central sigue mostrando u
  ocultando la barra. En la página de fin, el deslizamiento/toque de retroceso vuelve, el de avance no
  hace nada y los controles reciben clic/toque con normalidad. **No se añade** el clic de ratón en el
  lienzo como forma de pasar página (comportamiento vigente, F7).

### 5.4 Foco, accesibilidad y presentación

- **FR-22 (foco).** Al abrir la página de fin el foco va a `#fin-titulo` (`h2` con `tabindex="-1"`).
  Al volver, el foco va a `#lector-lienzo` y nunca se pierde en `body`. Al llegar a la última página
  el foco **no** se mueve. Nunca se oculta `#fin` con el foco dentro.
- **FR-23 (no modal).** `#fin` es una `<section>` nombrada por el `h2` (`aria-labelledby`); **no** es
  `role="dialog"` ni lleva `aria-modal`, no hay backdrop ni cierre por clic fuera, y no hay trampa de
  foco. El resto del lector (barra) sigue accesible.
- **FR-24 (anuncios).** La región `#lector-resultado` (`aria-live="polite"`, ya existe) anuncia
  «Fin del número.» al abrir la página de fin y el texto del contador al volver («Página N de N.» o
  «Páginas N–M de N.»). Al llegar a la última página no se añade ningún anuncio nuevo.
- **FR-25 (accesibilidad visual).** Foco visible en los dos temas y en `forced-colors`; objetivos
  táctiles ≥ 44 px; texto ≥ 14 px; contraste por tokens, sin colores literales; cualquier transición
  ≤ 180 ms y desactivada con `prefers-reduced-motion: reduce`.
- **FR-26 (estructura accesible).** MIENTRAS la página de fin está visible, las imágenes de página y
  las flechas superpuestas están ocultas también para accesibilidad (`hidden`, no enfocables). La
  portada es decorativa (`alt=""`). El marcador de fallo no lleva texto de error.
- **FR-27 (presentación).** La página de fin ocupa **el área de lectura entera**, como una
  contraportada opaca (sin borde de panel, sin sombra y sin fondo translúcido); no es la tarjeta
  flotante anterior. Al abrirla se oculta la barra del lector (que en móvil taparía el título) y al
  volver se restaura solo si estaba visible. El contenido va centrado con medida legible, admite
  desplazamiento vertical y **no** produce desplazamiento horizontal entre 320 y 1280 px.
- **FR-28 (sin JavaScript).** `#fin` llega en el HTML del servidor con `hidden` en los tres estados.
  Sin JS no se abre (el lector ya avisa de que hace falta JavaScript para pasar páginas); no hay
  conmutador de servidor que la muestre ni cambio de URL.
- **FR-29 (coste y peticiones).** Ni llegar a la última página ni abrir/cerrar la página de fin
  añaden peticiones, consultas ni escrituras. La página de fin no tiene endpoint propio. La única
  petición nueva posible es la portada de FR-12, al abrir y como mucho una vez. `GET /ui/leer/{id}`
  conserva ruta, cabeceras y contexto (F2), sin consultas añadidas.
- **FR-30 (regresión).** Resto del lector intacto: páginas y precarga, progreso, sentido, modos,
  zoom, filtros, pantalla completa, preparación de RAR, ficha y packs. Sin migración, sin
  dependencias y sin tocar servicios.

---

## 6. Criterios de aceptación (Given/When/Then)

| # | Dado | Cuando | Entonces |
|---|---|---|---|
| **AC-1** | Lector en la página N−1 (o en la pareja anterior a la última) | Se avanza una vez | Se ve la última página completa, `#fin` oculto, foco sin mover, contador «Página N de N», sin anuncio de fin y con el único `POST /progreso` de siempre |
| **AC-2** | Última página visible (LTR, un solo archivo, zoom 1) | Se pulsa el botón de avanzar, `→`, `Espacio` o `PageDown` | `#fin` visible sin recargar ni navegar, foco en `#fin-titulo`, anuncio «Fin del número.», contador sigue N de N, imágenes/flechas ocultas, **0** `POST /progreso` |
| **AC-3** | Página de fin abierta | Se intenta avanzar otra vez | Nada cambia: sin navegación, sin petición, sin mover foco |
| **AC-4** | Página de fin abierta | Se pulsa «Quedarme en esta página» | Vuelve la última página, `#fin` oculto, foco en `#lector-lienzo`, anuncio del contador, sin recarga ni petición, mismo zoom y misma página/pareja |
| **AC-5** | Página de fin abierta | Se usan las teclas/gestos de volver y `Esc` | Se cumple AC-4; `Esc` no cierra el lector; con Opciones abierta cierra Opciones; en pantalla completa no se sale de la página de fin |
| **AC-6** | Estado `leer` | Se abre la página de fin | Título «Fin del número», frase con #N y #K, principal «Leer el #K» hacia el lector del siguiente, «Marcar como leído» explícito y neutro, «Quedarme» y «Volver a la serie»; portada del siguiente con URL del n.º K y **sin `src` en el HTML inicial** |
| **AC-7** | Estado `falta` sin aviso legal | Se abre la página de fin | «Te falta el #K…», enlace a `/ui/legal?volver=%2Fui%2Fleer%2F{id}`, sin `hx-post="/deseo"`, con el aviso legal y la vuelta |
| **AC-8** | Estado `falta` con aviso legal | Se pulsa «Añadir a Deseados» | La petición va al endpoint existente, se ve «Añadido a Deseados.» y la página conserva «Quedarme» y «Volver a la serie» |
| **AC-9** | Estado `sin_siguiente` | Se abre la página de fin | «No hay un número siguiente en tu biblioteca.», sin «Leer el #K» ni Deseados, con leído explícito y vuelta |
| **AC-10** | Lector en la última página y en la página de fin | Se llega y se abre sin pulsar «Marcar como leído» | No hay `POST /leido` y `ReadingProgress.status` no cambia; solo al pulsar el botón se marca `COMPLETED`; «Deshacer» vuelve a `READING` conservando nota/puntuación y la página sigue abierta |
| **AC-11** | Modo doble con la pareja que contiene la última página visible | Se avanza y luego se vuelve | Se abre la página de fin (aunque `data-pagina` < N) y al volver se ve la misma pareja (mismo `data-pagina` y `paginaBVisible`); la página de fin no se empareja |
| **AC-12** | Serie con sentido RTL | Se usa la tecla/gesto de avance y el de vuelta | El avance abre la página de fin y la vuelta funciona con el mapeo invertido; el contenido de la página de fin no se reordena |
| **AC-13** | Zoom al 200 % en la última página | Se pulsa la tecla/botón de avanzar; se arrastra; se vuelve | La tecla/botón abren la página de fin; el arrastre mueve la imagen y no la abre; al volver el zoom sigue al 200 %; la página de fin no se amplía ni desborda en horizontal |
| **AC-14** | Lector en pantalla completa | Se entra y se sale de la página de fin, y se sale de pantalla completa | La pantalla completa no se pierde al abrir la página de fin; salir de pantalla completa no cierra ni la página de fin ni el lector; la vuelta sigue funcionando |
| **AC-15** | Foco en el `h2` o en un control de la página de fin | Se pulsan teclas de avanzar/volver, `Espacio`/`Enter` sobre un control, `Tab`/`Shift+Tab`, `Home`/`End` | Volver funciona desde el título; `Espacio`/`Enter` activan el control enfocado; `Home`/`End` y avanzar no hacen nada; el foco no queda atrapado y los controles de la barra son alcanzables |
| **AC-16** | Página de fin abierta | Se inspecciona accesibilidad | `#fin` es `section` nombrada por el `h2`; no hay `role="dialog"`/`aria-modal`/backdrop; foco visible en los dos temas y `forced-colors`; objetivos ≥44 px; texto ≥14 px |
| **AC-17** | JavaScript desactivado | Se carga la lectura | `#fin` está en el HTML con `hidden` y no se abre; el aviso de que hace falta JS y la primera página siguen igual; la URL no cambia |
| **AC-18** | Red observable (DevTools) | Se llega a la última página, se abre y se cierra la página de fin | Llegar: 0 peticiones nuevas. Abrir (`leer`): solo la portada del siguiente, una vez, por la ruta local existente. Cerrar: 0 peticiones. Sin endpoints ni parámetros nuevos; `GET /ui/leer/{id}` conserva estado y cabeceras |
| **AC-19** | Suite completa | Se ejecutan las pruebas (§7) | Verde, incluidas las de CSS/auditoría y las del lector existentes; sin reglas CSS muertas y sin cambios fuera del alcance (§1.1) |
| **AC-20** | Anchos 320, 375, 768 y 1280 px, temas claro y oscuro | Se recorre el flujo completo | La última página se vio entera antes; la página de fin es legible sin desplazamiento horizontal y todas las acciones y la vuelta son alcanzables |

---

## 7. Lista de pruebas

### 7.1 Automáticas

**`tests/test_lector.py` (servidor, plantilla)**

- `test_el_fin_llega_en_el_html_oculto_sin_contenido_visible` — el HTML del lector trae `#fin` con
  `hidden` y ningún indicio de «abierto»; el estado solo lo cambia el JS al abrirla.
- `test_el_fin_se_pinta_oculto_en_los_tres_estados` — `leer`, `falta` y `sin_siguiente` (hoy no hay
  prueba de `sin_siguiente` en el GET del lector).
- `test_la_pagina_de_fin_no_es_un_dialogo` — `section` + `aria-labelledby`, `h2 tabindex="-1"`, sin
  `role="dialog"` ni `aria-modal`; los ids `#fin`, `#fin-titulo`, `#fin-acciones` se conservan.
- `test_el_control_de_avanzar_sigue_operativo_en_la_ultima_pagina` — GET con `pagina_actual=total`:
  el botón de avance no lleva `aria-disabled="true"`; el de retroceso en la página 1 sí.
- `test_la_pagina_de_fin_conserva_la_vuelta_tras_cada_accion` — «Quedarme» (`#fin-quedarme`) y
  «Volver a la serie» presentes; el formulario de Deseados apunta a `#fin-deseo`.
- `test_la_portada_del_siguiente_no_se_pide_al_llegar` — en `leer`, el `<img>` de la portada no tiene
  `src`, y `#fin` no tiene peticiones asociadas en el HTML inicial.
- `test_marcar_leido_desde_la_pagina_de_fin_sigue_siendo_explicito` — el GET no marca nada; el POST
  existente sigue funcionando y devuelve el estado de leído con la vuelta.
- `test_fin_falta_conserva_la_puerta_legal` — extiende la prueba existente (AC-7) y añade el caso
  con aviso aceptado y el recambio de `#fin-deseo` (AC-8).
- `test_fin_sin_siguiente_no_ofrece_deseados_ni_leer` — AC-9.
- `test_los_textos_de_la_pagina_de_fin_son_los_especificados` — tabla de §5.2 literal, incluido
  «Fin del número» y «Quedarme en esta página».

**`tests/test_lector_js.py` (DOM mínimo en Node; actualizar el objeto de salida)**

- `finOcultoAlLlegar` — avanzar hasta la última página deja `#fin.hidden === true` y no toca el foco.
- `avanzarAbreFin` — botón/tecla/gesto en la última página: `#fin.hidden === false`,
  `document.activeElement === #fin-titulo`, `#lector-paginas.hidden === true`,
  `#lector-resultado.textContent === "Fin del número."`.
- `avanzarEnFinNoHaceNada` — AC-3 (sin cambios y sin `fetch`).
- `volverCierraFin` — AC-4/AC-5: `#fin.hidden === true`, foco en `#lector-lienzo`, anuncio del
  contador, `data-pagina` igual, zoom igual, mismo `src` de la imagen (sin recarga).
- `volverConTeclasYGestos` — `←`/`PageUp`/`Shift+Espacio`/deslizamiento contrario y `Esc` (sin
  salir del lector, incluidas las ramas de Opciones y pantalla completa).
- `dobleUltimaParejaAbreFin` — AC-11, y `paginaBVisible` igual al volver.
- `rtlAvanceYVuelta` — AC-12.
- `zoomNoAbreFinConGestoYSiConTecla` — AC-13 y conservación del zoom al volver.
- `repintarNoAbreNiCierraFin` — cargar la imagen, cambiar modo/sentido/zoom y `resize` (AC-6/FR-6).
- `tecladoEnFin` — AC-15 (`Espacio`/`Enter` sobre control no interceptados; `Home`/`End` no actúan;
  avance no actúa).
- `portadaSeHidrataAlAbrirYSoloUnaVez` — FR-12: sin `src` al llegar; al abrir se fija la URL una vez;
  un error de carga oculta la imagen y deja el marcador.

**CSS y auditoría (sin cambios de expectativa; puerta de regresión)**

- `tests/test_auditar_css.py::test_el_repo_actual_no_tiene_reglas_muertas` — obliga a retirar las
  reglas de la tarjeta y no dejar clases nuevas sin regla.
- `tests/test_web_css_contraste.py` (texto ≥14 px, sin colores literales), `tests/test_web_css_tokens.py`
  (sin grosores literales fuera de `:root`), `tests/test_web_css_320.py` y
  `tests/test_web_css_sistema_diseno.py` en verde.
- `tests/test_lector_siguiente.py` y `tests/test_lectura.py` **sin tocar**: son la garantía de que el
  «siguiente» de packs/decimales y el estado de lectura no cambian.

### 7.2 Manuales (evidencia PASS/FAIL/NOT RUN en la PR)

1. **Escritorio 1280 y 768**: última página completa; `→`, `Espacio`, `PageDown`, botón de avanzar y
   `←`/`PageUp`/`Esc` de vuelta; foco visible; sin salto de scroll.
2. **Móvil 375 y 320**: deslizar para entrar, deslizar al contrario para volver, toque en zona;
   sin scroll horizontal; acciones alcanzables; última página vista completa antes.
3. **Tablet táctil** y **ratón**: flechas superpuestas solo en escritorio; en la página de fin no se
   muestran.
4. **Doble página, RTL, zoom 200 %, filtros de imagen, pantalla completa**: combinaciones de AC-11 a
   AC-14.
5. **Dos temas** y `forced-colors`; `prefers-reduced-motion`.
6. **Sin JS**: `#fin` no aparece; primera página y aviso intactos.
7. **Lector de pantalla** (NVDA/Orca/VoiceOver): anuncio al abrir, orden de lectura, sin trampa. Si no
   hay dispositivo, se marca **NOT RUN** y no se convierte en PASS.
8. **Pi**: al abrir la página de fin en estado `leer` con la portada sin caché, medir la petición y su
   tiempo; comprobar que llegar y avanzar no generan peticiones. **NOT RUN** hasta tener la Pi.
9. **RAR preparando y fin de un pack**: no se rompen; el «siguiente» sigue siendo el de
   `siguiente_numero`.

### 7.3 Comandos

```bash
cd /mnt/Datos/Documentos/Repos/zascarr/.worktrees/lec-fin-d
python -m pytest -q tests/test_lector.py tests/test_lector_js.py tests/test_lector_siguiente.py
python -m pytest -q tests/test_auditar_css.py tests/test_web_css_contraste.py \
  tests/test_web_css_tokens.py tests/test_web_css_320.py tests/test_web_css_sistema_diseno.py
```

---

## 8. Lo que NO se hace (explícito)

- **No** se salta automáticamente al siguiente número ni se abre solo al terminar la última página.
- **No** se marca «Leído» automáticamente: ni al llegar, ni al abrir la página de fin, ni al salir.
  La automatización **no está aprobada**; el botón sigue siendo explícito (D-LEC-2, FR-14).
- **No** hay modal: ni `<dialog>`, ni `role="dialog"`, ni `aria-modal`, ni backdrop, ni trampa de foco.
- **No** hay petición extra para saber si hay final ni para pintar la página de fin: el HTML ya la
  trae (D-LEC-6, FR-29). La única petición posible es la portada del siguiente al abrir (FR-12).
- **No** se añaden endpoints, parámetros de URL, variables de servidor, tablas, columnas ni consultas.
- **No** se tocan la base de datos, la biblioteca, los archivos ni `services/`.
- **No** se cambia el cálculo del «siguiente» (`siguiente_numero`), ni los packs, ni los decimales.
- **No** se añade una entrada «Fin del número» en el menú/barra: se entra solo con intención de
  avanzar.
- **No** se añade una preferencia «seguir automáticamente» (otra historia, apagada por defecto).
- **No** se cambia el contador, el progreso, el modo, el sentido, el zoom ni los filtros.
- **No** se añaden dependencias ni se toca `_componentes.html`/el sistema de diseño.
- **No** se añade telemetría.

---

## 9. Riesgos, NOT RUN y puertas

- **Doble anuncio al abrir** (foco en el `h2` + región viva): se acepta para que el anuncio no
  dependa de si el lector de pantalla verbaliza encabezados enfocados; si en la pasada manual resulta
  redundante, se deja solo el foco en el título **sin cambiar AC-2/AC-16** (la región viva mantiene el
  anuncio de la vuelta).
- **Portada del siguiente en frío**: la ruta existente puede generar la miniatura la primera vez
  (coste en Pi). No bloquea la página; se mide en la puerta manual (§7.2.8). Si el PO considera
  inaceptable el coste, se retira FR-12 sin afectar al resto de la decisión D.
- **Teclado con foco dentro de la página de fin**: hoy el manejador global ignora las teclas cuando
  el foco no está en el lienzo o en las flechas (F7). FR-20 exige ampliarlo a `#fin`; es el punto con
  más riesgo de regresión y tiene prueba propia (`tecladoEnFin`).
- **NOT RUN** hasta la pasada manual: lector de pantalla, render real en Pi/móvil/tablet, tiempo de la
  portada en frío y medición de uso. No se convierten en PASS.
- **Puerta de alcance**: el diff de la implementación solo puede tocar §1.1. Cualquier cambio en
  `web/lector.py`, `services/`, modelos, migraciones, `_componentes.html` o configuración **para y
  pregunta**: está fuera de esta especificación.

---

## 10. Trazabilidad con la ficha de benchmarking

| Ficha | Dónde queda |
|---|---|
| §4 D «página de fin dentro del flujo» y §6 «comportamiento propuesto» | FR-1…FR-8, AC-1…AC-5 |
| §6.2 contenidos `leer`/`falta`/`sin_siguiente` | FR-9…FR-13, AC-6…AC-9 |
| §6.5 «Leído» explícito o automático (decisión del PO) | **Explícito** (D-LEC-2, FR-14, AC-10) |
| §6.6 sin salto automático | D-LEC-4, FR-3, AC-3 |
| §6.7 accesibilidad (h2 enfocable, `aria-live`, sin trampa de foco) | FR-22…FR-26, AC-15/AC-16 |
| §6.8 sin petición extra y portada local | FR-12, FR-29, AC-18 |
| §7 casos de prueba 1–11 | AC-1…AC-20 y §7.1/§7.2 |
| §8 invariantes | FR-7, FR-14, FR-28, FR-29 y §8 |
| Referencias (Komga/YACReader «insistir», Suwayomi/Kavita «página de transición») | La página de fin entra solo por intención y es contenido, no modal |

---

## 11. Referencias

- [`benchmark-BL-LEC-fin-lector-2026-11-21.md`](benchmark-BL-LEC-fin-lector-2026-11-21.md) — ficha de
  benchmarking de nivel 2; decisión D propuesta.
- [`benchmark-referencias.md`](benchmark-referencias.md) — procedimiento, vocabulario y ficha.
- [`epica-BL-LECUX-lector.md`](epica-BL-LECUX-lector.md) — LECUX2 y D-LUX2 (cierre de lectura).
- [`sistema-de-diseno-zascarr.md`](sistema-de-diseno-zascarr.md) — tokens, tipografía, forma,
  accesibilidad y textos.
- `CLAUDE.md` §6 (UX, un principal por pantalla, 14 px, sistema de diseño) y §14 (glosario).
- Código vigente: `src/zascarr/web/lector.py:75-83`, `src/zascarr/services/lector.py:368-433`,
  `templates/lector.html:82-107`, `templates/_lector_fin.html`, `static/lector.js:236-253`,
  `:274-289`, `:562-693`, `static/web.css:2879-2886`, `:2944-2949`, `web/series.py:2048-2063`.
