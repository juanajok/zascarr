# Épica BL-LECUX — Confort y acabado del lector

<!-- zascarr-kanban:v1:BL-LECUX -->

> **Épica propuesta, no aprobada.** Fecha: 2026-11-17.
> **Base contrastada:** `origin/main` `edf2fa61` (BL-LEC4 ya fusionada; LEC3 y LEC5 abiertas).
> **Fuente:** [`benchmark-BL-LEC-mercado-lectores-2026.md`](benchmark-BL-LEC-mercado-lectores-2026.md)
> (ficha §13) y [`benchmark-BL-LEC-lector.md`](benchmark-BL-LEC-lector.md) (contrato de servido).
> **Persona:** «El Coleccionista» — no técnico, lee en el PC, la tablet o el móvil; no abre
> terminales ni JSON. Raspberry Pi 4/5 compartida con 512 MiB para ZascArr; sin SPA ni Redis;
> un solo worker; un solo JavaScript propio, el del lector (ADR 0021).
> **Insumo, no aprobación:** decide el PO. No autoriza implementar ni publicar en el tablero.

---

## 0. Resumen para el PO

1. **Qué es.** La épica recoge el **acabado de UX y las features del lector propio** que
   sobrevivieron al benchmark de mercado (ajustes de imagen, cierre de la lectura, precarga,
   recuperación de errores de CBR y verificación de accesibilidad) **más la lectura inmersiva
   que pidió el PO el 2026-11-17** (pantalla completa de verdad, sin el marco de ZascArr,
   deslizar en táctil y flechas superpuestas en el PC). No reabre lo que el benchmark
   descartó con motivo (§7).
2. **Por qué ahora.** La lectura base ya está hecha (LEC0–LEC4, en `main`): CBZ y CBR, modos,
   doble página, sentido, teclado, táctil, progreso y preparación de RAR en caché. Lo que
   falta no es otro lector, sino cerrar los huecos que el benchmark dejó medidos y los que
   aparecieron al terminar LEC4, y quitar de en medio el marco de la aplicación: hoy el
   tebeo se lee **dentro** de la interfaz de ZascArr.
3. **Tamaño.** Seis historias (tres M y tres S), sin migraciones, sin dependencias nuevas y
   sin ADR nueva: todo cabe en el alcance de ADR 0021.
4. **Lo que NO entra, y por qué.** Zoom propio, navegación por viñetas, modo webtoon, recorte
   de márgenes, marcadores, estadísticas, PDF/EPUB/CB7, IA de imagen, multiusuario, social,
   telemetría y lectura por OPDS (esa es LEC5). Cada uno tiene su motivo en §7.
5. **Decisiones que necesito del PO:** aprobar la épica y su prioridad; elegir el cierre de
   lectura (automático con aviso o botón explícito); fijar los ajustes de imagen; decidir el
   comportamiento del cascarón inmersivo (chrome auto-oculto y flechas superpuestas);
   confirmar que hay lector de pantalla disponible para verificar LECUX5; y decidir si se
   publica como épica del tablero con sus historias.

---

## 1. Problema y alcance

El benchmark concluyó que el lector propio ya **iguala el mínimo competitivo** del mercado
(página a página, doble página, ajustes de tamaño, sentido de lectura, teclado, táctil,
«continuar donde lo dejé») y que las diferencias que quedan son de **acabado**, no de
arquitectura. También dejó dos huecos concretos: **marcar leído al terminar** y **filtros de
imagen**; y una deuda de UX de LEC4: la pantalla de preparación de un CBR no tiene salida ni
reintento explícitos.

**Petición del PO (2026-11-17):** leer **a pantalla completa y no enmarcado en la interfaz de
ZascArr**, pasar página **deslizando** en tablet/móvil y con **flechas superpuestas** en el
PC, al estilo de un visor de fotos. Hoy el lector hereda el cascarón de `base.html` (barra
lateral, menú, pie) y el lienzo lleva borde y tarjeta; el botón de pantalla completa existe
(LEC2), pero enseña la misma página enmarcada. El deslizar ya está implementado (50 px,
`dx > 2·dy`, zonas 30/40/30); las flechas superpuestas, no. Esta petición se convierte en
**LECUX6** (§5).

Esta épica convierte esos hallazgos en historias implementables. **No es la épica BL-LEC**
(#822): no añade formatos, no toca el contrato de servido, no implementa OPDS y no reabre
`sort_order` ni el modelo de progreso. Es la capa de confort encima de lo ya entregado.

**Fuera de la épica por decisión:** la lectura desde apps externas (LEC5, #828) y el progreso
desde esas apps. Aquí solo se lee dentro de ZascArr.

---

## 2. Lo que ya está igualado (y no se reimplementa)

Comprobado en `origin/main` `edf2fa61`, no en el informe:

| Función de mercado | Estado en ZascArr |
|---|---|
| Página a página, una o dos páginas, ajustar al ancho/pantalla | LEC2: modos y apaisadas solas |
| Sentido de lectura (serie > ComicInfo > tradición) | LEC2: guardado por serie |
| Teclado, zonas táctiles y deslizar | LEC2: `lector.js` (zonas 30/40/30 y umbral de 50 px) |
| Pantalla completa del navegador | LEC2: botón con Fullscreen API; **la página sigue enmarcada** en el cascarón de ZascArr |
| Lectura inmersiva y flechas superpuestas | **No existe**: el lector va dentro de la app, sin flechas sobre la página → LECUX6 |
| Contador de página y menú de opciones | `lector.html` |
| «Continuar donde lo dejé» y «Continuar leyendo» | Progreso por archivo (LEC1) e Inicio (CUR5) |
| CBR/RAR con caché y estados de preparación | LEC4: `cache_lectura.py` y `GET /ui/leer/{id}/estado` |
| Errores en llano al preparar un CBR | LEC4: motivos sin códigos de salida |
| Leer la página con bytes originales y `ETag` privado | LEC1 + `cached_image_response` |
| Siguiente número al acabar | LEC3 (#826), abierta |
| Leer desde una app por OPDS-PSE | LEC5 (#828), abierta |

Las ideas de biblioteca/metadatos del benchmark ya están cubiertas por otras fichas
(Whakoom, Metron, BL-IT01, B6, BL-DUP0); esta épica no las toca.

---

## 3. Huecos que justifican la épica

| Hueco | Evidencia | Historia |
|---|---|---|
| No hay ajustes de imagen (brillo, contraste, sepia, invertir) | Benchmark §4.2 y §7.4: aparecen en cinco apps del informe; coste 0 en la Pi si se hacen en cliente | LECUX1 |
| El lector no cierra la lectura ni ofrece terminarla | Benchmark §4.2 y §7.4: el mercado marca leído al terminar; ZascArr solo mueve `current_page` y deja `READING` | LECUX2 |
| No hay precarga de la página siguiente | Benchmark §7.1: «IGUALAR» del mercado; `lector.js` no precarga y cada cambio espera a la imagen | LECUX3 |
| La preparación de un CBR no tiene reintento explícito ni salida clara | Revisión de `lector.js`: sondea 5 veces y **recarga la página**; si falla, deja el motivo pero no hay «Reintentar» ni «Volver» junto al aviso | LECUX4 |
| La accesibilidad del lector no está verificada con lector de pantalla | LEC2 cerró con QA PASS de foco/nombres/aria, pero la pasada real con lector de pantalla no consta; LEC4 añadió estados nuevos | LECUX5 |
| El lector va enmarcado en la interfaz y no tiene flechas superpuestas | **Petición del PO (2026-11-17)**, no del informe: `lector.html` hereda barra lateral/menú/pie de `base.html` y `.lector-lienzo` lleva borde y tarjeta; el botón de pantalla completa no quita el marco. Deslizar ya existe | LECUX6 |

**Nota de honestidad:** LECUX4 y LECUX5 no nacen del informe de mercado; nacen de la
revisión del lector ya construido. LECUX6 nace de una **petición del PO** posterior al
benchmark. Se incluyen porque esta épica es de **acabado** y porque el benchmark exige no
vender como resuelto lo que no se ha probado.

---

## 4. Historias

| ID | Historia | Prioridad | Tamaño | Depende de |
|---|---|---|---|---|
| **BL-LECUX6** | Lectura inmersiva: pantalla completa real, flechas superpuestas y gesto | P1 | M | — |
| **BL-LECUX1** | Ajustes de imagen y preferencias del lector | P2 | M | — |
| **BL-LECUX2** | Cerrar la lectura al llegar al final | P2 | S | #826 (LEC3) |
| **BL-LECUX3** | Precarga y transición sin parpadeo | P2 | S | — |
| **BL-LECUX4** | Preparación de CBR y errores con salida | P2 | S | #827 (LEC4, ya en `main`) |
| **BL-LECUX5** | Accesibilidad del lector verificada | P1 | M | LECUX6, LECUX1–LECUX4 |

**Prioridad de la épica: P2 (Should).** LECUX6 y LECUX5 se proponen P1: el primero porque
es una petición expresa del PO y cambia la experiencia de lectura; el segundo porque la
accesibilidad no es un extra. Si el PO prefiere, LECUX5 puede quedar como verificación
obligatoria al cerrar el resto y la épica bajar a P2.

---

## 5. Detalle de las historias

### BL-LECUX1 — Ajustes de imagen y preferencias del lector

**Como** coleccionista, **quiero** ajustar el brillo, el contraste y el tono cuando un escaneo
se ve mal, **y** que el lector recuerde cómo me gusta leerlo, **para** no tocar el archivo ni
repetir los ajustes cada vez.

**Alcance**

- En «Opciones», un grupo **«Imagen»**: brillo y contraste (rangos acotados, valor neutro en
  el centro), y dos casillas: **sepia** e **invertir**. Botón **«Restablecer imagen»**.
- Se aplica **solo** al elemento de la página con `filter` de CSS. No se recodifica ni se
  redimensiona nada; no hay petición nueva al servidor por ajustar; el `ETag` y los bytes no
  cambian.
- Las preferencias se guardan **por dispositivo** en `localStorage`
  (`zascarr.lector.imagen`), con el mismo envoltorio `try/catch` que el modo: sin
  almacenamiento, el lector funciona igual con valores neutros.
- La misma sección «Opciones» se ordena por grupos: **Cómo leer** (ayuda breve de teclas y
  gestos), **Imagen** y **Navegación** (modos, sentido, pantalla completa). La ayuda va en un
  `<details>` para no romper el presupuesto de texto.

**Criterios de aceptación**

1. Con los valores neutros, el filtro CSS es `none` y la página se ve exactamente como hoy.
2. Cambiar un ajuste no dispara ninguna petición de red ni modifica `current_page`.
3. El ajuste se aplica a la página visible y a la que se precarga (LECUX3), no a los
   controles ni a otras pantallas.
4. Al reabrir el lector, los ajustes guardados se aplican antes de pintar la primera página
   (sin parpadeo visible).
5. «Restablecer imagen» vuelve a neutro y borra la preferencia guardada.
6. Controles con etiqueta visible, agrupados, alcanzables por teclado, objetivos de 44 px y
   texto ≥14 px; el estado no se distingue solo por color.
7. `prefers-contrast: more` y `prefers-reduced-motion` no empeoran: el filtro no se aplica a
   la interfaz, solo a la imagen.
8. Pruebas: DOM mínimo en Node (aplica, persiste, restablece y funciona sin `localStorage`);
   navegador real a 375, 768 y 1280 px, claro y oscuro; imagen clara y oscura de prueba.

**Límites**

- No hay presets guardados en servidor ni ajustes por serie: por dispositivo y punto.
- No hay colorización, nitidez, eliminación de moiré ni recorte: eso es análisis de imagen y
  queda descartado por coste en la Pi (benchmark §7.5).
- Sin migración, sin dependencias, sin tocar `services/`.

**Evidencia:** benchmark §4.2 (fila de filtros) y §7.4 (candidata 1).

---

### BL-LECUX2 — Cerrar la lectura al llegar al final

**Como** coleccionista, **quiero** que al llegar al final del tebeo ZascArr me ofrezca
terminarlo y pasar al siguiente, **para** no tener que volver a la ficha a marcarlo.

**Alcance**

- Se apoya en la **tarjeta de fin que ya define LEC3 (#826)**: el servidor la pinta oculta y
  el JS la muestra al llegar a la última página. Esta historia **no crea una segunda tarjeta**.
- Añade el cierre del número:
  - **Propuesta A (recomendada):** el botón principal de la tarjeta es **«Marcar como leído»**;
    al pulsarlo, se marca `COMPLETED` y se muestra «Guardado: Leído» con «Deshacer».
  - **Propuesta B:** marcar automáticamente al mostrar la última página, con aviso
    `role="status"` y «Deshacer». El PO elige (§11, D-LUX2).
- La escritura del estado pasa por **`services/lectura.py::marcar`** (misma verdad que BL-C3),
  no por un `UPDATE` nuevo desde el router ni desde el JS; repetir no duplica y no pisa
  `completed_at` si ya estaba leído.
- «Deshacer» vuelve a `Leyendo` y **no toca** nota ni puntuación (regla de BL-C3).
- La tarjeta dice también qué pasa con lo que falta: «Siguiente: #K» (LEC3) o «Te falta el #K»
  → Deseados, o «No hay un número siguiente en tu biblioteca».

**Criterios de aceptación**

1. Llegar a la última página por navegación normal muestra la tarjeta una vez; no reaparece al
   repintar la misma página.
2. «Marcar como leído» deja `status=completed`, `current_page=total` y `completed_at` si
   estaba vacío; si ya estaba leído, no cambia fechas ni nota.
3. «Deshacer» deja `status=reading` y conserva `rating` y `notes`.
4. Funciona con teclado y sin JavaScript: la tarjeta se puede mostrar con el servidor y el
   cierre tiene un `POST` real con `Form(...)`, no solo JS.
5. Probado con un número de un archivo, con un pack (`covered_issue_ids`) y con un número ya
   leído; pruebas de servicio con Postgres real para la transición de estado.
6. La tarjeta no tapa la última página ni el contador; a 320 px no hay scroll lateral.

**Dependencia:** #826 (LEC3) fusionada y con la tarjeta `#fin` implementada. Si el PO prefiere
reducir tarjetas, esta historia puede **integrarse en #826** en vez de existir aparte.

**Evidencia:** benchmark §4.2 (fila «marcar Leído al terminar») y §7.4 (candidata 4).

---

### BL-LECUX3 — Precarga y transición sin parpadeo

**Como** coleccionista, **quiero** que la página siguiente aparezca sin espera ni parpadeo,
**para** no romper el ritmo de lectura.

**Alcance**

- `lector.js` precarga la página o pareja siguiente (y la anterior si el modo doble la
  necesita) con `new Image()` y la **misma URL** de página, para aprovechar la caché HTTP
  privada que ya sirve el servidor (`Cache-Control: private`, `ETag`).
- Mantiene la imagen actual visible hasta que la siguiente carga; sin fondo en blanco, sin
  parpadeo, sin cambiar el alto del lienzo.
- Recalcula la precarga al cambiar de modo o de sentido; no precarga fuera de rango; no
  precarga mientras el CBR se está preparando ni si `/estado` devuelve `error`.
- Máximo **2 imágenes** en vuelo (la pareja). Nada de precargar la serie entera.

**Criterios de aceptación**

1. Al avanzar, la nueva página no muestra hueco en blanco si ya estaba precargada.
2. No hay peticiones a páginas fuera de `[1, total]`; con una sola imagen no se precarga la
   pareja inexistente.
3. En un CBR recién preparado no se dispara la precarga antes de que `/estado` diga `listo`.
4. Cambiar de modo o de sentido no deja precargas «viejas» ni duplica peticiones.
5. Medición en la Pi: p50/p95 del cambio de página y RSS sin empeorar; no se multiplica la
   extracción de un RAR (la precarga lee de la caché ya preparada, no lanza `unar`).
6. Prueba de DOM en Node: no se pide una página fuera de rango y se pide exactamente la
   siguiente; navegador real con red y con pestaña en segundo plano (`visibilitychange`).

**Límites:** si el navegador no puede precargar (o el usuario navega muy rápido), el lector
sigue funcionando igual. La precarga es una mejora, no un requisito de corrección.

**Evidencia:** benchmark §7.1 (IGUALAR del mercado, «precarga») y §4.2 (fila de precarga).

---

### BL-LECUX4 — Preparación de CBR y errores con salida

**Como** coleccionista, **cuando** un CBR tarda o no se puede preparar, **quiero** entender
qué pasa y poder reintentar o volver, **para** no quedarme mirando un aviso sin salida.

**Alcance**

- La pantalla «Preparando el tebeo…» gana dos acciones visibles: **«Reintentar»** (volver a
  consultar `/estado`, sin recargar la página entera) y **«Volver al número»** (enlace que ya
  existe arriba; se repite junto al aviso).
- Si `/estado` devuelve `error`, el motivo se muestra en llano y **permanece**; no se recarga
  la página en bucle ni se reintenta en silencio. Los motivos de LEC4 (cifrado, multivolumen,
  ilegible, sin imágenes, demasiado grande, sin espacio, `unar` no disponible) tienen su texto
  y su acción (reintentar o volver).
- La espera no es infinita: tras el tiempo de extracción configurado (`lector_extraccion_timeout_s`)
  el servidor ya devuelve error; la UI lo refleja y deja de sondear.
- El sondeo actual (5 intentos y recarga) se sustituye por un sondeo acotado con botón
  explícito; sin JS, la pantalla sigue mostrando el mensaje y el enlace de vuelta.

**Criterios de aceptación**

1. Error de preparación: se ve el motivo, «Reintentar» y «Volver al número»; no hay recarga
   automática de la página.
2. «Reintentar» consulta el estado de nuevo y, si pasa a `listo`, recarga **una** vez; si
   sigue en error, no entra en bucle.
3. Ningún mensaje contiene códigos de salida, rutas ni nombres internos; todos en español llano.
4. Los siete motivos de LEC4 tienen su caso de prueba (servicio o DOM) y su texto revisado.
5. Accesible: el aviso de error es `role="alert"`, la espera `role="status"`, el foco no se
   pierde y los botones son alcanzables por teclado.

**Dependencia:** LEC4 ya fusionada (`services/cache_lectura.py`, `GET /ui/leer/{id}/estado`).
**No cambia** topes, cuota ni política de extracción: solo la pantalla.

**Evidencia:** revisión de `lector.js` y de la plantilla `lector.html`; principio del benchmark
de errores en llano y con salida (ficha §8.6 y §9).

---

### BL-LECUX5 — Accesibilidad del lector verificada

**Como** coleccionista que usa el teclado o un lector de pantalla, **quiero** leer y controlar
el lector sin verlo, **para** que el lector no sea la única pantalla que se queda atrás.

**Alcance**

- Auditoría real del lector con: teclado solo, lector de pantalla (NVDA/Orca o VoiceOver) y
  zoom de navegador; incluye los estados nuevos de LECUX6 y LECUX1–LECUX4.
- Comprobación de: orden de foco al abrir y al cambiar de página; anuncio del contador
  (`aria-live`), del menú (`aria-expanded`), de los errores (`role="alert"`) y del guardado;
  foco visible; contraste de controles sobre el fondo oscuro del lector; `prefers-reduced-motion`
  y `forced-colors`; objetivos táctiles; texto ≥14 px.
- Se corrigen en esta historia los defectos encontrados; no se abre una historia por defecto.
- Evidencia en `docs/design/ui-BL-LECUX5/` (o el directorio que use el equipo): qué se probó,
  con qué versión, PASS/FAIL/NOT RUN. **Sin lector de pantalla disponible, NOT RUN; nunca PASS.**

**Criterios de aceptación**

1. Recorrido completo con teclado: abrir, avanzar, retroceder, abrir/cerrar Opciones, cambiar
   modo, aplicar un filtro, cerrar la lectura (si LECUX2), volver a la ficha; el foco nunca se
   pierde ni queda atrapado.
2. Lector de pantalla: cada cambio de página se anuncia una vez; el contador no se repite en
   bucle; el estado del menú y los errores se anuncian; los nombres accesibles son únicos y
   están en español.
3. Contraste de controles y contador medido en el tema oscuro del lector; cumple el sistema de
   diseño.
4. `prefers-reduced-motion` desactiva animaciones; `forced-colors` mantiene visible el foco.
5. Los defectos encontrados quedan corregidos y cubiertos por una prueba (HTML/JS o manual
   documentada).
6. La hoja de evidencia separa PASS, FAIL y NOT RUN; no se declara PASS sin prueba real.

**Dependencia:** después de LECUX6 y LECUX1–LECUX4 (verifica la UI final); si LECUX2 no se
aprueba, se verifica igual la tarjeta de LEC3.

**Evidencia:** `CLAUDE.md` §6 y el sistema de diseño (accesibilidad); LEC2 dejó foco/nombres/aria
en QA PASS, pero no consta la pasada real con lector de pantalla.

---

### BL-LECUX6 — Lectura inmersiva: pantalla completa real, flechas superpuestas y gesto

**Como** coleccionista, **quiero** abrir un tebeo y verlo a pantalla completa, sin la interfaz
de ZascArr alrededor, pasar página deslizando en la tablet o el móvil y con flechas sobre la
página en el PC, **para** leer como en un visor de fotos, sin que la aplicación me robe
espacio ni atención.

**Alcance**

- **Fuera el marco.** La pantalla `/ui/leer/{id}` deja de mostrar el cascarón de `base.html`
  a efectos visuales: sin barra lateral/menú, sin «tareas», sin pie y sin la tarjeta con
  borde alrededor de la imagen. Fondo neutro que no compita con la página (tokens del tema;
  sin el `--paper-2` del lienzo actual), a decidir en D-LUX10; la página ocupa el viewport
  (`100dvh`).
- **Chrome superpuesto, no marco.** Una barra mínima flotante (serie y número, «Página N de
  M», «Opciones», «Volver al número») se oculta sola tras unos segundos de inactividad y
  reaparece con el ratón, un toque o una tecla. Mientras está oculta, la página no se mueve
  ni cambia de tamaño.
- **Pantalla completa de verdad.** El botón «Pantalla completa» (o `f`) entra en el
  fullscreen del navegador y, dentro, el chrome se oculta igual; si el navegador no soporta
  la API (iPhone), el modo inmersivo sin chrome es el sustituto y el botón se oculta, como
  hoy. `Esc` sale primero del fullscreen y, con el chrome visible, vuelve al número.
- **Flechas superpuestas en PC.** Dos chevrones semitransparentes a izquierda y derecha de la
  página, al estilo de un visor de fotos, visibles al pasar el ratón o al enfocar (en
  pantallas táctiles, `@media (hover: none)`, no se muestran); son `<button>` reales con
  `aria-label` («Página anterior» / «Página siguiente»), de 44 px y con foco visible. En
  doble página avanzan la pareja.
- **Deslizar en táctil.** Se conserva el gesto de LEC2 (50 px, `dx > 2·dy`) y las zonas
  30/40/30; se verifica que con el nuevo layout no compite con el scroll y que el sentido
  RTL sigue invirtiendo el gesto.
- **Teclado.** Flechas, espacio, `f`, `m`, `Home`/`End` y `Esc` siguen funcionando; la barra
  flotante no atrapa el foco.
- **Aviso legal.** Al no pintarse el pie, el enlace «Aviso legal» sigue disponible desde
  «Opciones» (y en la ficha al volver), para no perder el aviso que hoy está en el pie.
- **Preparación de CBR.** «Preparando el tebeo…» se pinta en el mismo cascarón inmersivo,
  con el mensaje centrado y el enlace de vuelta; sin marco de la aplicación.

**Criterios de aceptación**

1. En escritorio (1280), tablet (768) y móvil (375), al abrir el lector no se ve barra
   lateral, menú, pie ni el borde/tarjeta alrededor de la página; el tebeo ocupa el alto
   disponible.
2. El chrome flotante desaparece por inactividad y vuelve con ratón/toque/teclado; no tapa
   el contador ni las flechas; es alcanzable con Tab y su foco es visible.
3. «Pantalla completa» entra y sale del fullscreen; sin la API, el botón no se muestra y el
   modo inmersivo sigue siendo completo; `Esc` se comporta como se describe.
4. Las flechas superpuestas aparecen con ratón y con foco de teclado y no con puntero táctil;
   avanzan/retroceden bien en LTR, RTL y doble página.
5. Deslizar en móvil/tablet pasa página; un gesto vertical no cambia de página; umbral y
   sentido se prueban en la tablet real.
6. La página no se recarga ni pierde la posición al entrar/salir de pantalla completa ni al
   ocultar/mostrar el chrome.
7. Sin JS, la pantalla sigue mostrando la primera página, el enlace de vuelta y el contador
   (degradación honesta); el marco ausente no deja la página en blanco.
8. La barra es `role="group"` con nombre accesible, las flechas tienen nombre, los avisos
   siguen en `role="status"`/`alert` y `prefers-reduced-motion` no anima el ocultado.
9. Sin peticiones nuevas de página, sin cambios de URL y sin tocar `services/` ni el contrato
   de servido.
10. Navegador real: Chrome de escritorio con ratón, Chrome/Safari móvil y tablet si hay;
    fullscreen y fallback; teclado y lector de pantalla (se cierra con LECUX5).

**Límites:** no hay zoom propio, panel a panel ni modo webtoon; no se oculta la salida
(siempre queda «Volver al número» y `Esc`); el lector es la única pantalla sin chrome, igual
que ya es la única oscura a propósito.

**Evidencia:** petición del PO (2026-11-17); benchmark §4.2 (pantalla completa/táctil) y §7.5
(lo descartado no entra); patrón de visor de fotos (Panels/OpenComic como referencia de UX,
sin copiar interfaz).

---

## 6. Orden propuesto y dependencias

```
LECUX6 (inmersivo) ───────────┐
LECUX1 (imagen/preferencias) ─┤
LECUX3 (precarga) ────────────┼─► LECUX5 (accesibilidad verificada)
LECUX4 (errores CBR) ─────────┤
LECUX2 (cierre) ◄─ #826 ──────┘
```

1. **LECUX6** va primero: cambia el cascarón donde luego se integran los ajustes y la
   precarga, y es la petición expresa del PO.
2. **LECUX1** y **LECUX3** son independientes y se pueden atacar en cuanto el PO apruebe.
3. **LECUX4** es independiente (LEC4 ya está en `main`).
4. **LECUX2** espera a **#826 (LEC3)**; si el PO prefiere, se integra en esa tarjeta.
5. **LECUX5** va al final, sobre la UI ya cambiada.
6. WIP del proyecto (2 en curso): no abrir dos de estas a la vez si compiten con otras
   historias; ninguna de las seis es urgente salvo que el PO suba LECUX6.

---

## 7. Fuera de alcance (con motivo del benchmark)

No vuelven sin un motivo nuevo y una ficha propia (benchmark §7.5):

- **Zoom propio del lector:** LEC2 decidió el zoom nativo del navegador; duplicarlo añade
  gestos y estado sin ganar nada.
- **Navegación por viñetas / Guided View:** exige detectar viñetas (análisis de imagen) o una
  dependencia de JS; choca con el presupuesto de la Pi y con «sin dependencias».
- **Modo webtoon / scroll vertical continuo:** la épica BL-LEC lo excluye a propósito; la
  tradición no dice el formato y no hay contenido webtoon en el objetivo.
- **Recorte automático de márgenes:** puede cortar arte; detectarlo exige analizar cada página.
- **Marcadores por página, notas de página, historial y estadísticas:** el progreso ya
  reanuda la lectura; añaden modelo/UI sin demanda medida. Las estadísticas ya estaban
  descartadas en el backlog.
- **PDF, EPUB, CB7, CBT:** 2 PDF y 1 CB7; fuera de la épica BL-LEC.
- **IA de imagen, colorización, reescalado:** coste de CPU/RAM incompatible con la Pi y
  dependencias externas.
- **Multiusuario, perfiles, listas públicas, reseñas, recomendaciones y telemetría:** fuera
  del producto (parking lot, LEGAL.md).
- **Sincronización de progreso con apps externas:** es LEC5/una historia nueva con API
  compatible; OPDS-PSE no devuelve progreso (benchmark §5.3).
- **OPDS, descargas de archivos, cambios en `services/lector.py` de servido:** otra épica.
- **Preferencias en base de datos o por serie:** esta épica las quiere por dispositivo; si
  algún día se piden por serie, será otra historia con migración.

---

## 8. Invariantes y reglas

1. **Pi compartida:** 512 MiB, un worker, sin Redis. Nada de procesado de imagen en servidor;
   los filtros son de cliente.
2. **Un solo JavaScript propio**, `src/zascarr/static/lector.js`, sin dependencias, sin build
   y solo en la pantalla de lectura (ADR 0021). Nada de JS nuevo fuera del lector.
3. **Sin dependencias nuevas** (ni Python, ni Node, ni CDN). Las pruebas de JS usan el DOM
   mínimo en Node que ya existe.
4. **El lector no escribe en la biblioteca** ni en los CBZ; el cierre de lectura escribe solo
   en `reading_progress` a través de la capa de servicios.
5. **Sin migraciones** en esta épica. Si una historia necesita una columna, para y pregunta:
   no entra.
6. **Autenticación y caché:** la misma de `/ui`; las páginas siguen con `Cache-Control:
   private` y `ETag`; nada de rutas ni nombres de archivo en URL o pantalla.
7. **Español llano y sistema de diseño:** textos ≥14 px, sin jerga (`filter`, `PSE`,
   `localStorage`, `aria` no llegan al coleccionista), tokens y componentes existentes.
8. **Presupuesto de texto:** la ayuda de LECUX1 va en `<details>`; no se añaden párrafos
   nuevos antes de la acción principal de la pantalla.
9. **Un botón principal por pantalla:** en el lector, «Siguiente» sigue siendo la acción que
   hace avanzar; los controles nuevos (filtros, «Restablecer», pantalla completa) son
   neutros; en la tarjeta de fin, el principal es el cierre o «Leer el #K» según decida el PO.
10. **Lector inmersivo (excepción declarada):** la pantalla de lectura es la única sin el
    cascarón de la aplicación (sin barra lateral, menú ni pie), igual que ya es la única
    pantalla con JavaScript propio. La salida sigue siempre disponible («Volver al número»,
    `Esc`) y el enlace al aviso legal se mantiene en «Opciones»; ninguna otra pantalla
    pierde su marco.
11. **Sin telemetría, sin red externa y sin hotlinking.**

---

## 9. Medición y verificación

- **Pruebas automáticas:** `python -m pytest -q` en verde; pruebas de JS con el DOM mínimo de
  `tests/test_lector_js.py` (Node); pruebas de servicio con Postgres real para el cierre de
  lectura (LECUX2).
- **Navegador real:** 375, 768 y 1280 px, claro y oscuro, teclado; en la tablet/móvil si hay
  dispositivo. Chrome y, si se puede, Safari/iOS para `fullscreen` y filtros.
- **Inmersivo:** escritorio con ratón (flechas superpuestas al pasar el ratón y con foco),
  tablet táctil (deslizar y ausencia de flechas), móvil (zonas de toque) y el fallback de
  fullscreen de iPhone; comprobar que no queda barra lateral, menú, pie ni marco.
- **Lector de pantalla:** NVDA, Orca o VoiceOver; si no hay, **NOT RUN** documentado y la
  historia no se declara cerrada como PASS.
- **Pi:** p50/p95 de servir una página y de cambiar de página, RSS del contenedor y peticiones
  de red; la precarga no debe multiplicar la extracción de RAR.
- **Evidencia separada** PASS / FAIL / NOT RUN en la PR y en el directorio de la historia; no
  se convierte un NOT RUN en PASS.
- **Regresión:** las pruebas existentes del lector (`test_lector*.py`, `test_lectura*.py`,
  `test_cache_lectura.py`, `test_web_lectura.py`) siguen en verde; el lector sigue funcionando
  sin JavaScript en lo esencial (primera página y enlaces).

---

## 10. Mapa de código

| Qué | Dónde | Nota |
|---|---|---|
| JS del lector | `src/zascarr/static/lector.js` (~240 líneas) | Único JS propio; aquí van LECUX1, LECUX3, LECUX4 y LECUX6 |
| Plantilla del lector | `src/zascarr/web/templates/lector.html` | Opciones, contador, preparación, tarjeta de fin (LECUX2) y cascarón inmersivo (LECUX6) |
| Cascarón de base | `src/zascarr/web/templates/base.html` | LECUX6: el lector deja de pintar barra lateral, tareas y pie (CSS `body:has(.lector)` o bloque propio) |
| Estilos del lector | `src/zascarr/static/web.css` (~2735–2775) | Filtros, chrome flotante, flechas superpuestas y fullscreen; tokens, no estilos sueltos |
| Rutas del lector | `src/zascarr/web/lector.py` | `/ui/leer/{id}`, `/pagina/{n}`, `/estado`, `/sentido`, `/progreso` |
| Servicio de lectura | `src/zascarr/services/lector.py` | Página, progreso, sentido; sin tocar el contrato de servido |
| Estado de lectura | `src/zascarr/services/lectura.py::marcar` | Fuente única del estado/nota/puntuación para LECUX2 |
| Caché de CBR | `src/zascarr/services/cache_lectura.py` | Estados y motivos para LECUX4 |
| Configuración | `src/zascarr/config.py` (`lector_*`) | Timeout y topes ya decididos en LEC4; no se reabren |
| Pruebas JS | `tests/test_lector_js.py` | DOM mínimo en Node: extender para filtros/precarga/errores |
| Pruebas de servicio | `tests/test_lector.py`, `tests/test_lectura.py`, `tests/test_web_lectura.py`, `tests/test_cache_lectura.py` | Regresión |
| Diseño | `docs/design/sistema-de-diseno-zascarr.md` | Tokens, accesibilidad y textos |
| ADR | `docs/adr/0021-javascript-propio-del-lector.md` | Alcance cerrado del JS; esta épica no lo amplía |

---

## 11. Decisiones del PO

| # | Decisión | Propuesta |
|---|---|---|
| D-LUX1 | Aprobar la épica y su prioridad | P2; LECUX5 P1 por accesibilidad |
| D-LUX2 | Cierre de lectura: botón explícito o automático con deshacer | Botón explícito como principal; automático solo si el PO lo pide |
| D-LUX3 | Ajustes de imagen: qué controles y límites | Brillo y contraste con rango acotado; sepia e invertir; sin nitidez ni recorte |
| D-LUX4 | ¿Integrar LECUX2 dentro de #826 (LEC3) en vez de tarjeta aparte? | Sí, si #826 aún no ha empezado; si ya está en curso, historia aparte |
| D-LUX5 | ¿Hay lector de pantalla disponible para verificar LECUX5? | Si no, NOT RUN y no se declara la épica cerrada del todo |
| D-LUX6 | Publicar como épica del tablero con sus historias | Sí, cuando el PO apruebe; el marcador `zascarr-kanban:v1:BL-LECUX` ya va en este documento |
| D-LUX7 | Lectura inmersiva: ¿por defecto o accionable? | **Por defecto**: abrir el lector ya sin marco y con chrome auto-oculto; el fullscreen del navegador es un extra |
| D-LUX8 | Flechas superpuestas: ¿siempre visibles o al pasar el ratón? | Al pasar el ratón/enfocar en PC; nunca en táctil (el gesto manda) |
| D-LUX9 | Al ocultar el pie, ¿dónde queda el aviso legal? | Enlace «Aviso legal» dentro de «Opciones» y en la ficha al volver |
| D-LUX10 | Fondo del visor inmersivo | Neutro del tema activo; si el PO quiere negro de visor de fotos, se fija aquí |

---

## 12. Definition of Ready / Done de la épica

**Ready para abrir historias:** PO aprueba D-LUX1–D-LUX4 y D-LUX7–D-LUX10; LEC3 fusionada
(para LECUX2); criterios de cada historia acordados; sin dependencias nuevas.

**Done de la épica:**

- Las seis historias (o las que el PO apruebe) fusionadas con pruebas en verde.
- Navegador real a 375/768/1280, modo inmersivo verificado en escritorio/tablet/móvil, y
  lector de pantalla verificado, o NOT RUN declarado.
- Medición en la Pi de los cambios de LECUX3 y del coste de la precarga.
- Sin dependencias nuevas, sin migraciones y sin JS fuera del lector.
- Documentación: ficha del benchmark enlazada, historia cerrada en el tablero y `BACKLOG`
  actualizado si el PO decide dar de alta la épica en él.

---

## 13. Trazabilidad

- [Benchmark de mercado de lectores 2026](benchmark-BL-LEC-mercado-lectores-2026.md):
  §4.2 (ideas de lectura), §5 (clientes OPDS, fuera de esta épica), §7.1/§7.2 (IGUALAR /
  MEJORAR) y §7.4 (candidatas).
- [Ficha BL-LEC](benchmark-BL-LEC-lector.md): contrato de servido, matriz §9, medición §12 y
  decisiones D-L1–D-L4.
- Épica base **#822** y subhistorias **#823** (LEC0), **#824** (LEC1), **#825** (LEC2),
  **#826** (LEC3), **#827** (LEC4) y **#828** (LEC5).
- **Petición del PO (2026-11-17):** leer a pantalla completa sin el marco de ZascArr, deslizar
  en tablet/móvil y flechas superpuestas en el PC, al estilo de un visor de fotos (LECUX6).
- `CLAUDE.md` §6 (UX), §8 (pruebas) y §10 (sin SPA, excepción ADR 0021); sistema de diseño;
  ADR 0021.
- Mapa de código de §10.

---

## 14. Historial de revisión

- **2026-11-17:** creación de la épica a partir del benchmark de mercado y de la revisión del
  lector en `origin/main` `edf2fa61`. No se ha publicado en el tablero ni se ha abierto
  ninguna historia.
- **2026-11-17 (revisión 2):** añadida **BL-LECUX6** (lectura inmersiva, flechas superpuestas
  y gesto) por petición del PO; LECUX5 pasa a depender también de ella. Sin cambios en las
  demás historias ni en los descartes.
