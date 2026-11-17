# UI — Indicador de tareas en curso

> **Estado:** diseño UX, **sin implementar**. Este documento no cambia `src/`, `tests/`,
> tokens, iconos, plantillas ni CSS. Fija el concepto, el sitio, los estados, el componente,
> la accesibilidad, la interacción, el copy y una referencia de marcado/estilos.
> **Base:** `origin/main` = `eb454fbe8ff3ed65980ea2cd08cb15fdf8c29f17` (2026-11-17), worktree
> `.squad/wt-tareas`, rama `docs/indicador-tareas`.
> **Navegador real, 320/1280 medidos, lector de pantalla y lector de foco:** **NOT RUN**.
> **Fuentes obligatorias leídas:** `docs/design/sistema-de-diseno-zascarr.md` completo;
> `CLAUDE.md` §6; `templates/_componentes.html`; `base.html`; `_comprobacion_disco.html`;
> `_conversion_lote.html`; `_auditoria_registro.html`; `_progreso_wishlist.html`;
> `wishlist.html`; `web.css`; `web/iconos.py`.

---

## 0. Decisión en una frase

Un **chip discreto y persistente «ZascArr está trabajando»** en la cabecera global, con el
número de tareas y un panel que se abre solo si el coleccionista lo pide. No es una pantalla,
no es un modal, no interrumpe y no convierte cada búsqueda en una alarma.

---

## 1. Concepto

### 1.1 Qué debe ver el coleccionista cuando algo tarda

El coleccionista no necesita saber qué es un proceso, una cola ni una petición. Necesita tres
cosas, en este orden:

1. **Que le hayamos oído:** algo visible en menos de medio segundo, sin bloquear lo que estaba
   haciendo.
2. **Que sepa si sigue vivo:** una señal pequeña y persistente que no dependa de quedarse en la
   pantalla donde lanzó la tarea.
3. **Que pueda ver el detalle sin ruido:** qué se está haciendo, cuánto falta (si se sabe) y
   dónde terminará, solo cuando lo pida.

El principio es **«no parece colgada, se le está haciendo caso»**. La app no dice «espera»; dice
qué está haciendo y deja seguir.

### 1.2 Qué es una tarea para este indicador

No todo lo que tarda es una tarea global. Hay dos capas, y mezclarlas sería ruido:

| Capa | Ejemplos actuales | Dónde se muestra | Por qué |
|---|---|---|---|
| **Tarea de fondo** | registrar la biblioteca, comprobar el disco, descargar deseados | **chip global + panel** | Sigue viva si cambias de pantalla; ya tiene estado y progreso en el servidor. |
| **Espera de esta página** | buscar una serie, buscar en fuentes, convertir un lote | **indicador local** (el actual `.htmx-indicator`, con umbral) | Si cierras o navegas, la petición ya no es la misma tarea; prometer que sigue sería falso. |

La conversión CBR→CBZ de `_conversion_lote.html:30-34` es hoy una petición de la página: su
texto ya dice «No cierres esta página». **No entra en el chip global** mientras no se convierta
en una tarea de fondo; eso sería otra historia (ejecución en segundo plano) y queda fuera.
Las búsquedas de `wishlist.html:28-34` y el indicador de Descubrir de `web.css:1540-1544` son
esperas locales: mantienen su patrón actual de 400 ms y no se duplican en el chip.

### 1.3 Principios de esta pieza

- **Silencio cuando no hay nada:** sin tareas no hay chip, ni «0 tareas», ni «Todo al día»
  permanente. Oculto es un estado de primera clase.
- **Una señal, no una pantalla:** el chip ocupa una píldora; el detalle vive en un panel.
- **Progreso real o nada:** si hay `X de Y`, se pinta `<progress>` nativo; si no se sabe, se
  usa un giro indeterminado y **no se inventa un porcentaje** (docs/design/sistema-de-diseno-zascarr.md:379-386).
- **Sin ansiedad:** el amarillo de acción no se usa aquí; el rojo solo para un error, no para
  «tarda». No hay cuenta atrás, ni barra que se llene sola, ni aviso a cada tick.
- **Sin tapar acciones:** el chip vive en la cabecera; el panel se abre a demanda y en móvil
  queda por encima de la barra inferior, no encima de un botón primario.
- **La garantía va con la acción con efecto:** el chip no promete que se mueve o se borra nada;
  el detalle enlaza a la pantalla donde eso se explica.
- **Un botón principal por pantalla** (`CLAUDE.md:220-224`): este componente **no es un botón
  principal**. Es información; sus enlaces son secundarios.

---

## 2. Dónde vive

### 2.1 Opciones

| Opción | Qué es | Lo bueno | Lo malo | Veredicto |
|---|---|---|---|---|
| **A. Chip global + panel** | Píldora en la cabecera global (barra lateral en escritorio, barra superior en móvil) y panel de detalle | **Sobrevive a la navegación HTMX**, no ocupa la página, es la forma «tipo Calibre», se puede cerrar | El panel tiene poco ancho; hay que cuidar el espacio del móvil | **Recomendada** |
| **B. Bloque «Ahora» en Inicio/Estado** | Una sección más en una página | Mucho espacio para progreso y detalle | **No sobrevive a navegar**; duplica los bloques que ya existen en Auditoría, No disponibles y Deseados; añade ruido a Inicio | No como pieza principal |
| **C. Ambas** | Chip global + bloque de página | Máxima visibilidad y detalle | Duplica la misma información y el mismo estado; dos sitios que mantener; más ruido | Solo si el PO pide una página «Tareas» más adelante |

**Recomendación: A.** El chip y su panel resuelven la promesa de «sigue trabajando aunque
cambies de pantalla». B se descarta como pieza principal porque Inicio ya tiene sus pasos y
Estado sus semáforos; añadir otra sección permanente allí compite con la tarea de la página.
Los bloques contextuales que ya existen en las pantallas de origen
(`_auditoria_registro.html:43-53`, `_comprobacion_disco.html:4-6`,
`wishlist.html:37-39`) se quedan como detalle en su sitio: son la «B» natural, sin crear otra
sección. Si más adelante hace falta una página de tareas, se reutiliza el mismo listado en
**Estado** (no en Inicio) como segunda rebanada.

### 2.2 Sitio exacto

- **Fuera de `main[hx-history-elt]`:** la cabecera global es `.side` y el contenido que se
  intercambia es `<main id="main" hx-history-elt>` (`base.html:16-27`). El chip va en `.side`,
  nunca dentro de `#rejilla` ni de un fragmento de página, para que **no lo sustituya** una
  navegación HTMX.
- **Escritorio:** una fila de cabecera dentro de `.side`, junto a la marca; el chip a la derecha
  de «ZascArr». No añade una fila nueva cuando está oculto.
- **Móvil (≤860 px):** la misma fila se convierte en la barra superior; el chip muestra solo
  **icono + número** para no empujar «Cerrar sesión». El panel se abre como hoja fija por encima
  de la barra inferior (`web.css:365-422`).
- **El panel no se ancla al contenido de la página:** se abre desde el chip; en escritorio es un
  panel absoluto de 360 px bajo él; en móvil es una hoja de ancho completo, con scroll interno.
- **No tapa acciones por defecto:** sin tareas no hay nada; con tareas solo hay una píldora en
  la cabecera. El panel es una acción voluntaria del coleccionista.

### 2.3 Supervivencia a HTMX

- El chip se renderiza una vez en `base.html` y no se vuelve a pintar al cambiar de pantalla.
- Se actualiza con un `GET /ui/_tareas` periódico que devuelve **solo fragmentos OOB**: cuenta,
  filas y anuncio. **Nunca se reemplaza el `<details>` ni el `<summary>`** en cada actualización:
  si se reemplazara, el panel se cerraría y el foco se perdería cada pocos segundos.
- El panel abierto sigue abierto; el foco se queda donde estaba; las filas se actualizan en su
  sitio.
- Si no hay tareas, el wrapper se oculta con CSS (`:has` ya se usa en la hoja, `web.css:763`) y
  el panel abierto se queda con «No hay tareas en curso.» hasta que se cierre.
- **No hay JavaScript nuevo:** `details`/`summary` nativo, HTMX para OOB y CSS para el resto.

---

## 3. Estados, tiempos y copy

### 3.1 Regla de aparición

- **Umbral: 400 ms**, el mismo patrón ya usado para no hacer parpadear una búsqueda rápida
  (`web.css:1540-1544`). Las tareas de fondo que siguen vivas al cruzar el umbral muestran el
  chip; las que terminan antes no llegan a verse.
- **No se muestra para cada petición:** una búsqueda de 400 ms tiene su indicador local; no
  crea una tarea de fondo.
- **Se queda visible mientras haya tareas de fondo o un resultado reciente** que merezca una
  confirmación breve.
- **Desaparece** cuando no hay tareas ni resultado pendiente; nunca muestra «0 tareas».

### 3.2 Tabla de estados

| Estado | Cuándo | Chip | Panel | Anuncio de lector |
|---|---|---|---|---|
| **Sin tareas** | No hay tareas de fondo ni resultado reciente | **Oculto** | Cerrado; si estaba abierto, «No hay tareas en curso.» y se cierra con el summary | Ninguno |
| **1 tarea** | Una tarea de fondo | `i` **«1 tarea»** | Una fila | «ZascArr está trabajando en 1 tarea.» solo al empezar |
| **Varias** | Dos o más | `i` **«2 tareas»** | Lista, la primera arriba | «ZascArr está trabajando en 2 tareas.» solo al cambiar el número de tareas, no en cada refresco |
| **Progreso determinado** | Hay `X` de `Y` reales | Igual; el detalle va en el panel | `<progress>` nativo, `X de Y`, etiqueta accesible | No se anuncia cada `X`; el `<progress>` no es una región viva |
| **Progreso indeterminado** | No hay total fiable | Igual | Giro indeterminado + **«Trabajando…»**; **sin barra inventada** | Solo al empezar |
| **Fase** | El servidor conoce el paso | Igual | **«Importando 3 de 12»**, **«Descargando 2 de 3»**, **«Comprobando el disco»** | No se anuncia cada fase; el detalle está en el panel |
| **Terminada** | La tarea acaba bien | `ok` **«Listo»** durante **8 s**; luego oculto | Fila `ok` **«Hecho»** + resumen breve; permanece mientras el panel esté abierto | «Terminó: Registrando tu biblioteca.» una vez |
| **Error** | La tarea falla | `warn` **«Revisar»**; se queda hasta abrir el panel | Fila `warn` **«Error»** + qué hacer + enlace **«Revisar»** | «No se pudo terminar: Registrando tu biblioteca.» una vez |
| **Atascada / antigua** | Sin progreso durante **10 min**, o empezó hace mucho y sigue | `info` **«1 tarea»** / **«2 tareas»**; el aviso va en la fila (no se pone rojo el chip) | Fila `amber` **«Tarda más»** + **«Está tardando más de lo normal. Puedes seguir usando ZascArr.»** | Se anuncia una vez al pasar a «Tarda más»; no se repite |
| **Varias, una con error** | Hay tareas activas y una falló | `warn` **«2 tareas»**; `aria-label` «2 tareas, una con error» | La fila del error primero; las demás, normales | «Una tarea ha fallado.» una vez |
| **Panel abierto sin tareas** | Se abrió y terminó la última | Oculto o «Listo» 8 s | **«No hay tareas en curso.»**; el panel no se cierra solo | Ninguno |

### 3.3 Copy exacto aprobable

**Chip**
- `1 tarea` · `2 tareas` · `10 tareas`
- `Listo` (8 s, tras terminar)
- `Revisar` (error)
- `2 tareas` con `warn` y `aria-label="2 tareas, una con error"` si hay error y siguen activas.

**Panel**
- Título: **«Ahora»**
- Ayuda: **«ZascArr sigue trabajando aunque cambies de pantalla.»** (8 palabras)
- Estado de fila: **«En curso»**, **«Hecho»**, **«Error»**, **«Tarda más»**
- Fase: **«Importando 3 de 12»**, **«Registrando tu biblioteca»**, **«Comprobando el disco»**,
  **«Descargando 2 de 3»**
- Progreso visible: **«3 de 12»**; etiqueta accesible: **«Archivos importados»**,
  **«Tebeos mirados»**, **«Descargas»**
- Tiempo: **«Empezó hace 2 min»**; si pasó una hora, **«Empezó a las 10:32»**
- Enlace de fila: **«Ver la tarea»**; en error: **«Revisar»**; en terminada: **«Ver el resultado»**
- Terminada: **«Terminó: 12 tebeos importados.»**
- Error: **«No se pudo terminar. Vuelve a intentarlo desde la tarea.»**
- Tarda más: **«Está tardando más de lo normal. Puedes seguir usando ZascArr.»**
- Panel vacío: **«No hay tareas en curso.»**

**Anuncios (solo cambios de estado, nunca ticks)**
- **«ZascArr está trabajando en 1 tarea.»**
- **«ZascArr está trabajando en 2 tareas.»**
- **«Terminó: Registrando tu biblioteca.»**
- **«No se pudo terminar: Registrando tu biblioteca.»**
- **«Una tarea ha fallado.»**
- **«Registrando tu biblioteca está tardando más de lo normal.»** (una vez)

Sin «job», «worker», «SSE», «polling», «proceso», «cola» ni porcentajes inventados en la
superficie. El vocabulario es el de la casa: tarea, tebeo, serie, número, descarga, revisar
(`docs/design/sistema-de-diseno-zascarr.md:54-59`; `CLAUDE.md:166-171`).

---

## 4. Componente

### 4.1 Anatomía

```
cabecera global
└─ [ actividad? ] [ chip: i 2 tareas ▾ ]      ← summary nativo, 44 px
   └─ panel (al abrir)
      ├─ h2 «Ahora»
      ├─ ayuda «ZascArr sigue trabajando…»
      ├─ lista de tareas
      │  ├─ chip de estado (info/ok/warn/amber)
      │  ├─ título/fase
      │  ├─ <progress> o giro indeterminado
      │  ├─ tiempo
      │  └─ enlace «Ver la tarea»
      └─ (si está vacío) «No hay tareas en curso.»
```

- **Icono:** no se añade ninguno. La cabecera del panel reutiliza **`activity`** (Lucide,
  `web/iconos.py:78-81`), ya existente, a 18 px y `aria-hidden`; el giro indeterminado es CSS,
  no un icono nuevo. Los estados usan los glifos del chip (`i`, `✓`, `!`, `?`).
- **Chip:** `ui.chip` (`_componentes.html:12-15`) dentro de un `summary`; altura 44 px; borde
  2 px; `radius-pill`; texto `chip` a `.875rem`; estado `info` para en curso, `ok` para hecho,
  `warn` para error, `amber` para «Tarda más». No se escribe un chip a mano
  (`docs/design/sistema-de-diseno-zascarr.md:329-341`).
- **Panel:** `paper-2`, borde de 3 px en `ink`, `radius-panel`, `shadow-ink` (panel flotante,
  `docs/design/sistema-de-diseno-zascarr.md:183-184`), ancho 360 px en escritorio, ancho completo en móvil; `overflow:auto`;
  sin backdrop y sin trampa de foco.
- **Fila:** una tarea por `<li>`; 14 px mínimo; `overflow-wrap:anywhere`; enlaces de 44 px.
- **Progreso:** `ui.progreso` (`_componentes.html:63-65`), barra nativa de 14 px, borde de 3 px,
  `radius-pill`, relleno `yellow` (`docs/design/sistema-de-diseno-zascarr.md:379-386`; `web.css:1405-1415`). Solo con valores
  reales.
- **Indeterminado:** giro CSS de 12 px con `currentColor`, como el de conversión
  (`web.css:1979-1986`), pero reutilizado como `.tarea-giro`; sin barra.
- **Tiempo:** una línea `muted`; no se actualiza cada segundo en el DOM, se recalcula en cada
  refresco (2–3 s); no hay contador en vivo.
- **Contador:** el número visible va en el chip; `aria-label` del `summary` dice
  «ZascArr está trabajando: 2 tareas». En 320 el chip puede mostrar solo el número, pero el
  nombre accesible sigue completo.
- **Acciones:** no hay botón principal. Los enlaces de tarea son navegación normal; no hay
  «Cancelar» global (cancelar exige saber qué se puede deshacer; fuera de alcance).

### 4.2 Tamaños y tokens

| Pieza | Medida | Token/regla |
|---|---|---|
| Chip | 44 px alto; padding 0 10–12 px; borde 2 px; píldora | `docs/design/sistema-de-diseno-zascarr.md:174-200`; `docs/design/sistema-de-diseno-zascarr.md:329-341` |
| Texto chip | `.875rem`, 700, `font-body` | `docs/design/sistema-de-diseno-zascarr.md:156-170`; `CLAUDE.md:182-186` |
| Icono de estado | glifo del chip; 18–20 px si se usa Lucide | `docs/design/sistema-de-diseno-zascarr.md:250-258` |
| Panel | 360 px; borde 3; `radius-panel`; `shadow-ink` | `docs/design/sistema-de-diseno-zascarr.md:174-200` |
| Fila | separación 10–12 px; enlace 44 px | `docs/design/sistema-de-diseno-zascarr.md:272-278` |
| Progreso | 14 px alto; borde 3; píldora; relleno `yellow` | `docs/design/sistema-de-diseno-zascarr.md:379-386` |
| Colores | `info-bg`/`cyan-t`, `ok-bg`/`ok-t`, `warn-bg`/`warn-t`, `amber-bg`/`amber-t`; panel `paper-2` | `docs/design/sistema-de-diseno-zascarr.md:101-131` |
| Sombra | `shadow-ink`, solo el panel; el chip no parece botón principal | `docs/design/sistema-de-diseno-zascarr.md:183-184`, `225-226` |

**No se añaden tokens, colores ni clases de color.** El chip usa las parejas de `ui.chip`; el
panel usa papel y tinta; el progreso usa el amarillo de acción que ya es su color.

### 4.3 Claro/oscuro

- Todo sale de `paper`, `paper-2`, `ink`, `ink-soft` y las parejas `-bg`/`-t`; no hay colores
  nuevos. El tema nocturno sigue `prefers-color-scheme` (`docs/design/sistema-de-diseno-zascarr.md:95`).
- El giro y el pulso usan `currentColor`; no dependen del tema.
- El chip de error no se distingue solo por el rojo: lleva `!` y la palabra «Revisar»; el de
  «Tarda más» lleva `?` y su texto (`docs/design/sistema-de-diseno-zascarr.md:70-76`; `_componentes.html:12-15`).
- El panel es `paper-2` con borde `ink`; el texto sigue los pares de contraste de la casa.

### 4.4 Movimiento

- **Pulso del chip:** opacidad suave 0,85 ↔ 1 cada 2,4 s, solo mientras hay una tarea en curso.
  No escala, no salta, no cambia de posición.
- **Giro indeterminado:** 0,8 s lineal, 12 px, fino; solo en la fila sin total.
- **Apertura del panel:** opacidad/desplazamiento de 3 px en 0,12 s; sin rebote.
- **Cierre:** 0,12 s; no se anima si se cierra por una acción del navegador.
- **`prefers-reduced-motion: reduce`:** se apagan pulso, giro y transición; el estado queda
  quieto y el texto sigue informando (`docs/design/sistema-de-diseno-zascarr.md:287-288`; `web.css:1418-1423`).
- **Sin animación de progreso simulada:** la barra solo refleja valores reales.

---

## 5. Accesibilidad

- **`details`/`summary` nativo:** el estado expandido/colapsado lo comunica el elemento
  (equivalente a `aria-expanded`); el foco se queda en el `summary` al abrir y cerrar; Tab entra
  en el panel; no hay trampa de foco ni modal. No se añade JS para el toggle.
- **El chip no es una región viva.** Cambiar «1 tarea» a «2 tareas» no se anuncia si no se pide.
- **Una sola región viva:** `<p id="tareas-anuncio" class="sr" role="status"
  aria-live="polite" aria-atomic="true">`. Se actualiza **solo** al empezar, terminar, fallar o
  pasar a «Tarda más», nunca en cada refresco ni con cada `X de Y`.
- **El panel no está dentro de `aria-live`:** las filas y el progreso se actualizan sin
  anunciarse. El `<progress>` nativo lleva `aria-label` y no es una región viva; el lector puede
  consultarlo al enfocarlo, pero no oye cada tick.
- **Contador accesible:** `summary` con `aria-labelledby` a `#tareas-nombre`
  («ZascArr está trabajando: 2 tareas»); en 320 el texto visible puede ser solo `2`, pero el
  nombre accesible no se acorta. Ese span se actualiza por OOB; no se reemplaza el summary.
- **Foco:** abrir/cerrar no roba foco; si el panel se actualiza, no se reemplaza el `summary` ni
  la fila enfocada. Las filas terminadas permanecen mientras el panel está abierto para no
  perder el foco.
- **Teclado:** summary, enlaces y progreso alcanzables; no se usa `onclick` ni `hx-confirm`.
- **Contraste:** las parejas `info-bg`/`cyan-t`, `ok-bg`/`ok-t`, `warn-bg`/`warn-t`,
  `amber-bg`/`amber-t` ya están validadas (`docs/design/sistema-de-diseno-zascarr.md:101-131`; `CLAUDE.md:182-186`); no se
  introducen colores.
- **320/1280:** chip en la barra superior; panel de ancho completo con scroll; sin scroll
  horizontal. En 1280, panel de 360 px.
- **`forced-colors`:** el giro/borde usa `currentColor`; el estado sigue en el texto, no solo
  en el color.
- **No se anuncia «2 tareas» cada segundo:** el único anuncio repetido permitido es el cambio
  de estado, no el contador ni el progreso.

---

## 6. Interacción

1. **Aparición:** una tarea de fondo se registra al lanzarse; el chip se muestra tras **400 ms**
   si sigue viva. Si termina antes, no aparece. Las tareas ya en curso al cargar la página se
   pintan en el primer render (sin esperar al primer refresco).
2. **Actualización:** el endpoint de tareas se consulta cada **3 s** (solo mientras la app está
   abierta; sin jerga en la UI). Actualiza cuenta, filas, tiempo y anuncio por OOB.
3. **Apertura:** pulsar el chip abre el panel; foco en el summary; Tab recorre las tareas.
4. **Cierre:** el mismo summary; no hay backdrop ni cierre por clic fuera; el panel no es modal.
   `Escape` no cierra `<details>` sin JS; se declara como límite aceptado.
5. **Pulsar una tarea:** enlace normal a la pantalla de origen (`/ui/auditoria#registro`,
   `/ui/no-disponibles#comprobar-disco`, `/ui/wishlist#wishlist-progreso`) o a su detalle. La
   navegación no detiene la tarea; el chip sigue en la cabecera.
6. **Terminada:** chip `Listo` y fila `Hecho` durante **8 s**; luego se ocultan. No hay toast ni
   confeti.
7. **Error:** chip `Revisar`; al abrir el panel se marca como visto y el chip deja de reclamar
   atención, pero la fila de error sigue visible mientras el panel esté abierto. No se
   autodescarta un error que nadie ha leído.
8. **Atascada / antigua:** tras **10 min sin progreso**, la fila pasa a `Tarda más` con
   `amber` y el texto de tranquilidad. No se oculta ni se pone el chip en rojo; no hay
   «Cancelar» global.
9. **Sin tareas:** desaparece el chip; si el panel estaba abierto, se queda con «No hay tareas
   en curso.» hasta que se cierre. No se cierra de golpe ni se mueve el foco.
10. **Navegación HTMX:** el chip está fuera de `main[hx-history-elt]`; no se repinta. El panel
    abierto no se cierra al cambiar de pantalla.
11. **No bloquea:** ninguna capa cubre la página por defecto; nada se desactiva mientras corre
    una tarea; se puede seguir usando la app.
12. **Nada de cancelar desde el chip:** si una tarea necesita cancelación, se hace en su
    pantalla y con confirmación; fuera de esta pieza.

---

## 7. Wireframes

### 7.1 Escritorio 1280, chip cerrado

```
┌─ side 244 ─────────┬─ contenido 1240 ──────────────────────────────┐
│ ZASCARR            │                                                │
│ [ i 2 tareas  ▾ ]  │  ...                                           │
│                    │                                                │
│ Inicio             │  ...                                           │
│ Por revisar        │                                                │
│ Biblioteca         │                                                │
│ ...                │                                                │
│                    │                                                │
│ Cerrar sesión      │                                                │
└────────────────────┴────────────────────────────────────────────────┘
```

### 7.2 Escritorio 1280, panel abierto

```
┌─ side 244 ─────────┬────────────────────────────────────────────────┐
│ ZASCARR            │                                                │
│ [ i 2 tareas  ▴ ]  │                                                │
│ ┌─ Ahora ──────────────────────────────┐                         │
│ │ ZascArr sigue trabajando aunque       │                         │
│ │ cambies de pantalla.                  │                         │
│ │                                       │                         │
│ │ i En curso  Importando 3 de 12        │                         │
│ │ [██████░░░░░░] 3 de 12 · hace 2 min   │                         │
│ │ Ver la tarea                          │                         │
│ │                                       │                         │
│ │ i En curso  Comprobando el disco      │                         │
│ │ ◌ Trabajando… · hace 1 min            │                         │
│ │ Ver la tarea                          │                         │
│ └───────────────────────────────────────┘                         │
│ Inicio             │                                                │
│ ...                │                                                │
└────────────────────┴────────────────────────────────────────────────┘
```

### 7.3 Móvil 320, chip cerrado

```
┌─ 320 ───────────────────────────────┐
│ ZASCARR        [ i 2 ]   Cerrar     │
├─────────────────────────────────────┤
│                                     │
│  ... contenido ...                  │
│                                     │
├─────────────────────────────────────┤
│ Inicio  Revisar  Deseados  Estado … │  ← barra inferior fija
└─────────────────────────────────────┘
```

- El chip visible es `i 2`; el nombre accesible es «ZascArr está trabajando: 2 tareas».
- No se muestra «2 tareas» completo si no cabe: el contador accesible no se recorta.

### 7.4 Móvil 320, panel abierto

```
┌─ 320 ───────────────────────────────┐
│ ZASCARR        [ i 2 ]   Cerrar     │
│                                     │
│ ┌─ Ahora ─────────────────────────┐ │
│ │ ZascArr sigue trabajando aunque  │ │
│ │ cambies de pantalla.             │ │
│ │                                  │ │
│ │ i En curso  Importando 3 de 12   │ │
│ │ [████░░░░] 3 de 12 · hace 2 min  │ │
│ │ Ver la tarea                     │ │
│ │                                  │ │
│ │ i En curso  Comprobando el disco │ │
│ │ ◌ Trabajando… · hace 1 min       │ │
│ │ Ver la tarea                     │ │
│ └──────────────────────────────────┘ │
├─────────────────────────────────────┤
│ Inicio  Revisar  Deseados  Estado … │
└─────────────────────────────────────┘
```

- El panel es una hoja fija por encima de la barra inferior, con scroll interno; el chip
  superior sigue visible para cerrar. No hay backdrop ni modal.

### 7.5 Claro/oscuro

- Claro: `paper`/`paper-2`, texto `ink`, chip `info` con `info-bg`/`cyan-t`; progreso `yellow`.
- Oscuro: los mismos tokens invertidos por `prefers-color-scheme`; el chip de error usa
  `warn-bg`/`warn-t`; el panel `paper-2` con borde `ink`. Sin colores nuevos.
- En ambos temas, el estado se lee por **texto + glifo**, no solo por el color.

---

## 8. Referencia HTML/CSS (no implementar)

> **Referencia de diseño, no código para pegar.** Usa `ui.chip` y `ui.progreso` existentes;
> las clases `.tareas-*` son el nombre propuesto para la pieza nueva. No añadir JS, tokens ni
> colores. El endpoint `GET /ui/_tareas` es el contrato que faltaría implementar.

### 8.1 Marcado de referencia

```jinja
{# En base.html, dentro de .side y fuera de main[hx-history-elt]. #}
<div class="side-cabecera">
  <a href="/ui/" class="brand">ZascArr</a>
  <div id="tareas-globales" class="tareas-globales"
       hx-get="/ui/_tareas" hx-trigger="load, every 3s" hx-swap="none">
    {#- Siempre presente: el CSS lo oculta si no hay filas y el panel está cerrado.
        Así, si la última tarea termina con el panel abierto, el panel no se arranca. -#}
    <details class="tareas" id="tareas">
      <summary class="tareas-disparador" aria-labelledby="tareas-nombre">
        {#- El nombre accesible vive en un span actualizable por OOB; no se reemplaza el summary. -#}
        <span id="tareas-nombre" class="sr">{% if n_tareas %}ZascArr está trabajando: {{ n_tareas }} tarea{{ 's' if n_tareas != 1 }}{{ '; una con error' if hay_error else '' }}{% else %}{{ estado_global_texto }}{% endif %}</span>
        {#- En escritorio, «2 tareas»; en 320, el mismo chip con solo el número. -#}
        <span class="tareas-chip-largo">
          {% if n_tareas %}
          {{ ui.chip(estado_global, n_tareas ~ " tarea" ~ ("s" if n_tareas != 1 else "")) }}
          {% else %}
          {{ ui.chip(estado_global, estado_global_texto) }}
          {% endif %}
        </span>
        <span class="tareas-chip-corto" aria-hidden="true">
          {% if n_tareas %}{{ ui.chip(estado_global, n_tareas) }}{% else %}{{ ui.chip(estado_global, "✓" if estado_global == "ok" else "!") }}{% endif %}
        </span>
        <span class="tareas-flecha" aria-hidden="true">{{ icono("chevron_down") }}</span>
      </summary>
      <div class="tareas-panel" role="region" aria-labelledby="tareas-titulo">
        <h2 id="tareas-titulo" class="titulo-frase">
          <span class="tarea-icono" aria-hidden="true">{{ icono("activity") }}</span> Ahora
        </h2>
        <p class="muted">ZascArr sigue trabajando aunque cambies de pantalla.</p>
        <ul class="tareas-lista" id="tareas-lista">
          {% for t in tareas %}
          <li class="tarea" data-tarea="{{ t.clave }}">
            <div class="tarea-cabecera">
              {{ ui.chip(t.aspecto, t.estado_texto) }}
              <h3 class="titulo-frase">{{ t.titulo }}</h3>
            </div>
            <p class="tarea-fase">{{ t.fase }}</p>
            {% if t.total %}
              {{ ui.progreso(t.hechos, t.total, t.etiqueta_progreso) }}
              <p class="muted">{{ t.hechos }} de {{ t.total }} · {{ t.tiempo }}</p>
            {% else %}
              <p class="tarea-fase"><span class="tarea-giro" aria-hidden="true"></span> Trabajando…</p>
              <p class="muted">{{ t.tiempo }}</p>
            {% endif %}
            <a class="tarea-enlace" href="{{ t.url }}">Ver la tarea</a>
          </li>
          {% endfor %}
        </ul>
        {% if not tareas %}<p class="muted">No hay tareas en curso.</p>{% endif %}
      </div>
    </details>
  </div>
</div>

<p id="tareas-anuncio" class="sr" role="status" aria-live="polite" aria-atomic="true">{{ anuncio }}</p>
```

- El chip corto (`2`) solo se ve a ≤480 px; el largo (`2 tareas`) a partir de ahí. Ambos son
  `ui.chip`; el `summary` lleva el nombre completo en `#tareas-nombre` (`aria-labelledby`).
  `estado_global` es `info`
  (en curso), `ok` (Listo) o `warn` (Revisar/una con error); el chip corto mantiene el glifo
  del estado, así que un error no se queda en un «2» sin señal.
- Si el panel sigue abierto cuando ya no quedan tareas, el chip dice **«Listo»** (o
  **«Revisar»** si hubo error) en vez de **«0 tareas»**; al cerrar, la pieza se oculta. No hay
  un estado «0 tareas».
- El `<details>` no se destruye al quedarse sin tareas: solo se oculta por CSS si no hay filas
  y está cerrado. Si estaba abierto, se ve «No hay tareas en curso.»
- `hx-swap="none"` + OOB: el endpoint actualiza `#tareas-lista`, el contador y
  `#tareas-anuncio`, **sin tocar** `<details>` ni `<summary>`.
- `t.aspecto` es `info`/`ok`/`warn`/`amber`; `t.estado_texto` es `En curso`/`Hecho`/`Error`/
  `Tarda más`. No se inventa un estado ni un color.

### 8.2 CSS de referencia

```css
/* Cabecera: la fila ya existe por la marca; el chip no añade una fila si está oculto. */
.side-cabecera {
  display: flex; align-items: center; justify-content: space-between;
  gap: var(--space-2); min-height: 44px;
}
.tareas-globales { position: relative; min-width: 0; }
.tareas-globales:not(:has(.tareas-lista > li)):not(:has(details[open])) { display: none; }

.tareas-disparador {
  display: inline-flex; align-items: center; gap: 4px;
  min-height: 44px; padding: 0; list-style: none; cursor: pointer;
}
.tareas-disparador::-webkit-details-marker { display: none; }
.tareas-disparador .chip { min-height: 44px; padding: 0 10px; }
.tareas-disparador:focus-visible { outline: 3px solid var(--cyan-t); outline-offset: 2px; }
.tareas-flecha { display: inline-flex; }
.tareas-flecha .ico-svg { width: 18px; height: 18px; }
.tareas[open] .tareas-flecha { transform: rotate(180deg); }
.tareas-disparador .chip { animation: tareas-latido 2.4s ease-in-out infinite; }

.tareas-panel {
  position: absolute; z-index: 60; top: calc(100% + 8px); left: 0;
  width: 360px; max-width: calc(100vw - 32px); max-height: 60vh; overflow: auto;
  padding: var(--space-3); background: var(--paper-2);
  border: var(--border-panel) solid var(--ink); border-radius: var(--radius-panel);
  box-shadow: var(--shadow-ink);
}
.tareas-panel h2 { margin: 0 0 var(--space-1); }
.tarea-icono { display: inline-flex; margin-right: 6px; }
.tarea-icono .ico-svg { width: 18px; height: 18px; vertical-align: -3px; }
.tareas-lista { list-style: none; margin: var(--space-3) 0 0; padding: 0; display: grid; gap: var(--space-3); }
.tarea { border-top: var(--border-line) solid var(--ink-faint); padding-top: var(--space-3); }
.tarea:first-child { border-top: 0; padding-top: 0; }
.tarea-cabecera { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-2); }
.tarea-cabecera h3 { margin: 0; overflow-wrap: anywhere; }
.tarea-fase, .tarea .muted { margin: 4px 0; overflow-wrap: anywhere; }
.tarea-enlace { display: inline-flex; align-items: center; min-height: 44px; }
.tarea-giro {
  width: 12px; height: 12px; display: inline-block; vertical-align: -2px;
  border: var(--border-chip) solid currentColor; border-right-color: transparent;
  border-radius: 50%; animation: tarea-giro .8s linear infinite;
}

@keyframes tareas-latido { 50% { opacity: .82; } }
@keyframes tarea-giro { to { transform: rotate(360deg); } }

@media (max-width: 860px) {
  .tareas-panel {
    position: fixed; left: 0; right: 0; bottom: 64px; width: auto;
    max-width: 100%; max-height: 60dvh; border-radius: var(--radius-panel) var(--radius-panel) 0 0;
  }
}
@media (max-width: 480px) {
  .tareas-chip-largo { display: none; }
  .tareas-flecha { display: none; }
}
@media (min-width: 481px) { .tareas-chip-corto { display: none; } }
@media (prefers-reduced-motion: reduce) {
  .tareas-disparador .chip, .tarea-giro { animation: none; }
}
```

- El pulso y el giro se apagan con `prefers-reduced-motion`; el texto y la barra siguen.
- En móvil, el panel queda por encima de la barra inferior (`bottom: 64px`, como la hoja del
  panel de filtros de Biblioteca) y deja visible la barra superior con el chip.
- **No se añaden colores**: todo sale de `paper`, `paper-2`, `ink`, `cyan-t`, `ok-t`, `warn-t`,
  `amber-t` y `yellow` (solo progreso).
- **No se añade JS**: `details`, `:has`, HTMX OOB y CSS.

### 8.3 Contrato mínimo del endpoint (para la implementación)

`GET /ui/_tareas` devuelve **fragmentos OOB**, no una página:

- `#tareas-lista` con las filas, cada una con `data-tarea` estable.
- El contador visible del chip y `#tareas-nombre` (si no se actualizan los dos, el lector de
  pantalla oiría una cuenta vieja). No se reemplaza el `summary`: se actualiza el span.
- `#tareas-anuncio` **solo** si cambió el estado, no en cada respuesta.
- Nunca devuelve un `<details>` nuevo: el panel abierto se queda abierto.

Fuentes que ya existen y habría que agregar sin consultas nuevas por fila:
`_auditoria_registro.html:43-53` (registro, progreso y `every 2s`),
`_comprobacion_disco.html:4-6` (comprobación, `every 5s`),
`wishlist.html:37-39` y `_progreso_wishlist.html:1-15` (descargas, `every 30s`).
La conversión de `_conversion_lote.html:30-34` **no** entra mientras sea una petición de página.

---

## 9. Criterios de aceptación UI

1. Sin tareas de fondo, el chip y el panel no ocupan espacio visible; no hay «0 tareas».
2. Con una tarea, el chip dice «1 tarea»; con dos, «2 tareas»; el nombre accesible no se recorta
   en 320.
3. Solo aparecen tareas de fondo; búsquedas y conversión conservan su indicador local y no crean
   un chip global.
4. Una tarea que termina antes de 400 ms no parpadea; una que sigue viva aparece después del
   umbral.
5. El chip sigue visible al navegar entre pantallas con HTMX y no se repinta con el contenido.
6. El panel se abre/cierra con el summary; el foco no se mueve al refrescar y el panel abierto no
   se cierra solo.
7. El progreso determinado usa `<progress>` nativo con `X de Y` real; el indeterminado usa giro
   y «Trabajando…», nunca una barra inventada.
8. La fase y el tiempo se leen en el panel; el tiempo no se actualiza cada segundo.
9. Terminada: «Listo»/«Hecho» durante 8 s; después se oculta sin toast.
10. Error: «Revisar»/«Error» con qué hacer; no se autodescarta sin abrir el panel.
11. Atascada: «Tarda más» con el texto de tranquilidad; el chip no se pone rojo por tardar.
12. El lector de pantalla oye solo los cambios de estado, nunca «2 tareas» cada segundo ni cada
    tick de progreso.
13. 320 y 1280, claro y oscuro: sin scroll horizontal, panel usable, objetivos de 44 px, texto
    ≥14 px, contraste de los pares existentes.
14. `prefers-reduced-motion` apaga pulso/giro/transición y no impide entender el estado.
15. No se añaden tokens, colores, iconos, JS, dependencias, migraciones ni un segundo botón
    principal; no se bloquea la página ni se abre un modal.
16. Copy exacto de §3.3 aprobado; sin «job», «worker», «SSE», «polling» en superficie.

**NOT RUN:** implementación, navegador real, 320/1280 medidos, lector de pantalla, teclado
físico, `prefers-reduced-motion` real y tareas reales. Este documento no ha ejecutado ni
modificado código.

---

## 10. Riesgos y decisiones abiertas

- **Fuente única del estado:** hoy las señales están dispersas en tres bloques con sondeos
  distintos. Sin un registro/endpoint que las agregue, el chip no puede ser coherente.
  Recomendación: un registro en memoria del proceso único (sin Redis/DB) que lea esas fuentes;
  al reiniciar, no hay tareas y el chip no miente.
- **Panel abierto y sondeo:** el mayor riesgo de implementación es reemplazar el `<details>` o
  la lista entera cada 3 s. Debe actualizarse por OOB y conservar foco/estado abierto.
- **Tareas de primer plano:** si el PO quiere que la conversión sobreviva a navegar, hay que
  convertirla en tarea de fondo; no se resuelve con este chip. No se promete.
- **Error persistente:** el chip «Revisar» necesita una marca de «visto» al abrir el panel; si
  no, se queda para siempre. Es parte del contrato mínimo.
- **320:** el chip completo no cabe en la barra superior; la variante `2` con `aria-label` evita
  el scroll horizontal. Hay que medirlo en navegador real.
- **`<details>` y Escape:** no cierra con Escape sin JS; se declara límite aceptado, como en el
  resto de paneles nativos de la app.
- **No cancelar:** no hay «Cancelar» global; si una tarea se atasca, el enlace lleva a su
  pantalla. Cancelar requiere saber qué se puede deshacer; fuera de alcance.
- **Duplicación con B:** si se añade un bloque «Ahora» en Inicio/Estado, debe ser el **mismo**
  listado y no un segundo sistema; de momento no se recomienda.

---

## 11. Resumen para el PO — 10 líneas

1. **Recomiendo A:** un chip discreto en la cabecera global y un panel de detalle, no una pantalla nueva.
2. **Vive en `.side`**, fuera de `main[hx-history-elt]`, para sobrevivir a la navegación HTMX.
3. **Solo tareas de fondo** (registro, disco, descargas); búsquedas y conversión mantienen su indicador local.
4. **Sin tareas, oculto:** nunca «0 tareas» ni «Todo al día» permanente.
5. **Umbral 400 ms:** una tarea rápida no parpadea; una larga se ve y se queda.
6. **Contador y progreso:** «1 tarea»/«2 tareas», `X de Y` con `<progress>` real, giro si no hay total.
7. **Panel «Ahora»:** lista, fase, tiempo y enlace; se abre y cierra con el summary, sin modal.
8. **Estados:** «Listo» 8 s, «Revisar» en error, «Tarda más» a los 10 min; sin ansiedad ni rojo por tardar.
9. **Accesibilidad:** un solo `aria-live` para cambios de estado, nunca un anuncio por tick; foco y 44 px.
10. **B/C no ahora:** los bloques contextuales ya son la B; C duplicaría. Sin tokens, JS ni migración nuevos; **NOT RUN**.

---

## 12. Decisión del PO (2026-11-17)

- **Aprobada A**: chip global en `.side` + panel «Ahora».
- **Aprobado ampliar el alcance**: además de las tareas de fondo, el chip incluye **conversión CBR→CBZ** y **extracción de paquetes**.

Consecuencia: esas dos operaciones dejan de ser esperas locales y pasan a **tareas de fondo** con el mismo chip, contador, fases y aviso de fin. La UI local actual se mantiene mientras la tarea sea de página; cuando se ejecute en segundo plano, su indicador será el global. Esto amplía el trabajo y exige especificación técnica antes de implementar; no cambia tokens, componentes ni copy ya redactados.
