# Cerrar la vista previa del número con teclado (UATP-05 / #1143)

> **Estado:** **aceptada por el PO e implementada en la rama `feat/uatp05-previa-teclado`**
> (2026-11-21, task-53). El benchmark previo (**task-47**, 2026-11-21, solo lectura y no
> versionado) dictaminó **NO PASA**; las decisiones D-1…D-6 de §13 las **acepta el PO** tal como
> se recomiendan y son la base de la implementación. Las pruebas de navegador de §11 siguen
> **NOT RUN** en su matriz completa: solo se ha ejecutado la prueba de humo de §14.
>
> **Insumos:** [#1143 · UATP-05](https://github.com/juanajok/zascarr/issues/1143),
> [#1141 · épica UATP](https://github.com/juanajok/zascarr/issues/1141),
> [#1072 · LECUX5](https://github.com/juanajok/zascarr/issues/1072) y la historia que creó la
> previa, [#590 · BL-INF4](https://github.com/juanajok/zascarr/issues/590). Ficha de referencia:
> [`benchmark-BL-INF4-portada-numero.md`](benchmark-BL-INF4-portada-numero.md) y
> [`especificacion-BL-INF4-portada-numero.md`](especificacion-BL-INF4-portada-numero.md).
>
> **Base de las referencias de línea:** `origin/main` = **`d5f26df5`** (2026-11-21). El bloque
> de previa es idéntico en el HEAD del benchmark (`3eb38cd2`). El implementador debe ramificar
> desde `origin/main`, no desde una copia local atrasada.
>
> **Autoría:** el documento lo redactó SPEC.writer (task-50) y no toca código ni tests. La TDD
> (task-53) registra aquí la aceptación del PO de §13 y las notas de implementación de §14; la
> evidencia de navegador y las revisiones independientes son tareas aparte.

## 1. Problema y resultado esperado

Con teclado, al enfocar un chip de número aparece una tarjeta con su portada, pero **no hay forma
de apartarla sin moverse de sitio**: no hay Escape, ni botón de cierre, ni JS de previa. Además, la
tarjeta tiene `pointer-events:none` y un hueco de 8 px: no se puede recorrer con el puntero y los
clics la atraviesan. En las variantes fijas (listas y Colecciones) la tarjeta es grande, se abre
por hover sin invitación y tapa botones como «Quitar de la colección», de modo que un clic en la
tarjeta puede activar el botón de debajo. Con el puntero parado en un chip y el foco en otro se
pintan **dos** previas y la del hover tapa el texto y el anillo del chip enfocado.

El benchmark task-47 midió el estado actual y lo resumió así:

| # | Hallazgo del benchmark | Evidencia en la base | Decisión |
|---|---|---|---|
| P-1 | Escape no descarta la previa; no hay cierre ni mecanismo sin mover el foco | [`series_detail.html:16`](../../src/zascarr/web/templates/series_detail.html:16), [`_rejilla_biblioteca.html:122`](../../src/zascarr/web/templates/_rejilla_biblioteca.html:122), [`coleccion_detalle.html:84`](../../src/zascarr/web/templates/coleccion_detalle.html:84); [`web.css:2063-2064`](../../src/zascarr/static/web.css:2063) solo `:hover`/`:focus-within` | D-1 |
| P-2 | WCAG 1.4.13 «hoverable»: `pointer-events:none` + hueco de 8 px; al entrar en la tarjeta desaparece | [`web.css:2052`](../../src/zascarr/static/web.css:2052), [`web.css:2056`](../../src/zascarr/static/web.css:2056), hueco en [`web.css:2055`](../../src/zascarr/static/web.css:2055) | D-2 |
| P-3 | El clic atraviesa la tarjeta. En Colecciones la previa fija (200×330) tapa «Quitar de la colección» y el clic puede lanzar el POST de baja | [`coleccion_detalle.html:80-89`](../../src/zascarr/web/templates/coleccion_detalle.html:80), [`web.css:2043-2052`](../../src/zascarr/static/web.css:2043) | D-2, D-4 |
| P-4 | Dos previas a la vez: hover en un chip y foco en otro; la del hover tapa el chip enfocado (medido: 8 chips cubiertos) | [`web.css:2063-2064`](../../src/zascarr/static/web.css:2063); comentario de [`web.css:2061-2062`](../../src/zascarr/static/web.css:2061) | D-3 |
| P-5 | Copy falso: «Pulsa para abrir la ficha» en una tarjeta que no es enlace y cuyo clic abre lo de debajo | [`_previa_numero.html:6`](../../src/zascarr/web/templates/_previa_numero.html:6) | D-5 |
| P-6 | La variante fija no puede ser hoverable (está lejos) y solapa acciones; el botón «Ver portada» solo existe con puntero grueso | [`series_detail.html:395-411`](../../src/zascarr/web/templates/series_detail.html:395), [`_rejilla_biblioteca.html:118-127`](../../src/zascarr/web/templates/_rejilla_biblioteca.html:118), [`web.css:2654`](../../src/zascarr/static/web.css:2654) | D-4 |
| P-7 | La limitación de solape se aceptó sin descarte ni prueba; la spec de BL-INF4 dice «encima» y el CSS lo pone «debajo» | [`benchmark-BL-INF4-portada-numero.md:60`](benchmark-BL-INF4-portada-numero.md:60), [`especificacion-BL-INF4-portada-numero.md:93`](especificacion-BL-INF4-portada-numero.md:93); tests solo de cadenas | D-6 |
| P-8 | Observación de esta spec (no del benchmark): la flecha de [`web.css:2074-2078`](../../src/zascarr/static/web.css:2074) **no se pinta**, porque `overflow:hidden` en [`web.css:2057`](../../src/zascarr/static/web.css:2057) recorta el `::before` que sale 9 px. Comprobado con Chrome headless sobre la CSS real (2026-11-21) | [`web.css:2057`](../../src/zascarr/static/web.css:2057) | D-2 |

**Resultado esperado.** En la ficha y en las listas, con teclado: el foco en un chip abre la previa
tras 150 ms; **Escape la aparta sin mover el foco**; al pasar al siguiente control su texto y su
anillo de foco quedan visibles y solo hay una previa. Con puntero: la previa se puede recorrer sin
que se cierre, el clic no atraviesa la tarjeta y se descarta con clic/Escape. La variante fija solo
se abre con foco o con su botón, nunca por hover, y no permite activar por accidente un botón de
debajo. Abrir el número con <kbd>Enter</kbd> sigue funcionando y no hay trampa de foco. Sin JS
nuevo, sin dependencias, sin migración y conservando BL-INF4 (#590), #1072 y el resto de la UI.

## 2. Alcance / no alcance

**Dentro** (el mecanismo es compartido; el AC funcional se juzga en la previa del número de la
ficha, y se aplica a los cuatro usos porque comparten CSS y el fallo de clic a través de
Colecciones es un riesgo real):

| Pieza | Cambio |
|---|---|
| [`series_detail.html:11-17`](../../src/zascarr/web/templates/series_detail.html:11) | Chip del número (variante anclada): cierre Escape/clic y `hx-sync`. |
| [`series_detail.html:395-411`](../../src/zascarr/web/templates/series_detail.html:395) | «Archivos por número» (variante fija): sin hover, cierre y `hx-sync`. |
| [`_rejilla_biblioteca.html:118-127`](../../src/zascarr/web/templates/_rejilla_biblioteca.html:118) | Lista de Biblioteca (fija): sin hover, botón visible también con puntero fino, cierre. |
| [`coleccion_detalle.html:80-89`](../../src/zascarr/web/templates/coleccion_detalle.html:80) | Lista de Colecciones (fija): ídem; caso «Quitar de la colección». |
| [`_previa_numero.html`](../../src/zascarr/web/templates/_previa_numero.html), [`_previa_serie.html`](../../src/zascarr/web/templates/_previa_serie.html) | Pie honesto y mismo indicador en las dos tarjetas. |
| [`web/series.py:1988-2028`](../../src/zascarr/web/series.py:1988), [`web/colecciones.py:271-285`](../../src/zascarr/web/colecciones.py:271) | Las tres rutas de previa aceptan `cerrar=1` y devuelven vacío. |
| [`web.css:2041-2083`](../../src/zascarr/static/web.css:2041) y [`web.css:2650-2668`](../../src/zascarr/static/web.css:2650) | Puntero, puente, recorte, una sola previa, variante fija y botón. |
| [`tests/test_web_portada_numero.py`](../../tests/test_web_portada_numero.py), [`tests/test_web_css_previa.py`](../../tests/test_web_css_previa.py), [`tests/test_web_ficha_447.py`](../../tests/test_web_ficha_447.py), [`tests/test_web_library.py`](../../tests/test_web_library.py), [`tests/test_web_colecciones.py`](../../tests/test_web_colecciones.py) | Casos T1–T8 de §10. |
| Docs | D-6 (§8): este doc, E2E, corrección de las docs de BL-INF4 y del sistema de diseño. |

**Fuera de alcance (explícito):**

- **JS nuevo.** Nada de `hx-on`, `<script>`, `static/lector.js` ni ficheros JS de previa: solo
  atributos htmx (ADR 0001/0021). No se toca el lector.
- **Un contenedor único de previa**, anclaje por *CSS anchor positioning*, *flip* automático,
  reposicionar la tarjeta, cambiar su tamaño (220/200 px) o el retardo de 150 ms.
- **Convertir la tarjeta en enlace** o en diálogo: sigue siendo decorativa (`aria-hidden`) y sin
  elementos enfocables; ver D-5.
- **Previa en ancho reducido o táctil para la variante anclada:** se conserva la ocultación de
  BL-INF4 (`≤860 px` o `pointer:coarse`); la fija de las listas sigue disponible con su botón.
  Cambiar el umbral es otra historia (D-6).
- **Manipular la tarjeta con el puntero** más allá de recorrerla y descartarla; sin selección de
  texto, sin arrastrar, sin zoom.
- **Ajuste global para desactivar previas**, `aria-live`/anuncios del lector de pantalla nuevo.
- **Eliminar el CSS muerto** `.coleccion-check.chip-previa` ni otras deudas de UI.
- **Safari/Firefox, lector de pantalla, móvil/táctil físico, Pi y `forced-colors` real**:
  **NOT RUN** declarado, nunca PASS. En navegador real solo se exige Chrome estable.
- Backend, modelo, migraciones, dependencias, caché de portadas (`/previa.jpg`, ETag/304),
  `docs/BACKLOG.md` (se toca al cerrar la P1, CLAUDE.md §9).

## 3. D-1 · Cerrar con Escape sin mover el foco (htmx, sin JS)

### 3.1 Contrato de la ruta

Las **tres** rutas de previa aceptan `cerrar: bool = Query(False)`:

- [`previa_numero`](../../src/zascarr/web/series.py:2006),
- [`previa_serie` de series](../../src/zascarr/web/series.py:1989) (lista de Biblioteca),
- [`previa_serie` de colecciones](../../src/zascarr/web/colecciones.py:271).

Con `cerrar=1` devuelven **antes de tocar la BD o el disco**:

```python
if cerrar:
    return HTMLResponse("", headers={"Cache-Control": "no-store"})
```

- `200` con cuerpo vacío (htmx sustituye el hueco por vacío). No es `204`: algunas rutas de la app
  ya usan `200` vacío para el caso «sin previa» y así la prueba es la misma.
- La ruta sigue bajo la autenticación de `/ui`; no hay efecto de escritura, CSRF ni filtración:
  cerrar no necesita saber si el número existe.
- Una visita directa a `…/previa?cerrar=1` devuelve la página vacía; no se enlaza desde ningún
  sitio. `Cache-Control: no-store` como el resto del fragmento.
- El caso normal (sin `cerrar`) no cambia: mismo 200/404, mismo `no-store`, mismo comportamiento
  HTMX de [`web/series.py:2006-2028`](../../src/zascarr/web/series.py:2006).

### 3.2 Marcado del chip

El cierre vive en el **envoltorio** `.chip-previa`, que sigue existiendo después del swap (no se
sustituye el enlace ni el botón, así que el foco no se mueve). Un solo `hx-get` de cierre por chip:

```html
<span class="chip-previa"
      hx-get="/ui/series/{{ series.id }}/numero/{{ enlace.id }}/previa?cerrar=1"
      hx-trigger="keyup[key=='Escape'], click from:'find .previa-numero'"
      hx-target="#previa-{{ enlace.id }}"
      hx-swap="innerHTML"
      hx-sync="closest .chip-previa:replace">
  <a class="chip-enlace" href="/ui/series/…/numero/…"
     hx-get="…/previa" hx-trigger="mouseenter delay:150ms, focusin delay:150ms"
     hx-target="#previa-…" hx-swap="innerHTML"
     hx-sync="closest .chip-previa:replace">…</a>
  <span class="previa-numero" id="previa-…" aria-hidden="true"></span>
</span>
```

- `keyup[key=='Escape']` se escucha en el envoltorio: el `keyup` del enlace enfocado (o del botón)
  **burbujea** hasta él. Es el patrón validado con el htmx 4.0.0 vendorizado en el benchmark
  task-47: Escape pide `?cerrar=1`, el hueco queda vacío y el foco no se mueve.
- `click from:'find .previa-numero'` usa el **mismo** `hx-get` de cierre para el clic/toque en la
  tarjeta (D-2); no se duplica el atributo dentro de la tarjeta y no se hereda nada (htmx 4 tiene
  la herencia desactivada por defecto). **El selector va entrecomillado porque contiene un
  espacio**: el parser de `hx-trigger` del htmx 4.0.0 vendorizado parte el valor por espacios y
  `from:find .previa-numero` se leería como `from:"find"` más una clave suelta (probado con el
  fichero real en Chrome 158: sin comillas, el clic en la tarjeta no cierra; con comillas sí). Es
  la misma semántica, sin cambio de diseño.
- `hx-target` apunta solo al hueco de la previa; el enlace/ botón no se sustituyen.
- `hx-sync="closest .chip-previa:replace"` en **todos** los disparadores del chip (enlace, botón,
  envoltorio): las peticiones de un mismo chip comparten cola y la última aborta la anterior. Sin
  esto, un Escape durante la carga (una portada de CBR puede tardar segundos) dejaría la petición
  abierta en vuelo y la tarjeta podría **reaparecer después** de descartada. Con `replace`, el
  cierre aborta la carga en curso. `closest .chip-previa` resuelve al propio envoltorio tanto en
  el envoltorio como en sus hijos (comprobado en el resolutor de htmx 4.0.0).
- Las variantes fijas añaden el cierre al envoltorio y el mismo `hx-sync` al enlace y al botón
  de apertura; a sus enlaces se les quita `mouseenter` (D-4).

### 3.3 Qué se considera cerrado

- El hueco queda con `:empty` y la tarjeta oculta (regla de D-3 aplicada a `:not(:empty)`).
- `document.activeElement` es el mismo elemento de antes de Escape; el anillo `:focus-visible`
  sigue viéndose. No hay navegación, ni scroll, ni otra petición que el GET de cierre.
- No se anuncia nada (la tarjeta es `aria-hidden`); no hay `aria-live` nuevo.
- El clic en la tarjeta también la vacía; en ese caso el navegador puede mover el foco, pero no
  activa nada de debajo (D-2).

### 3.4 Límites declarados del cierre

El manejador está en el envoltorio, así que Escape funciona **cuando el foco está dentro del chip**
(el escenario de UATP-05, teclado). Si la previa se abrió solo con el puntero y el foco está en
otro sitio, Escape no la cierra; se aparta moviéndose fuera o con un clic/toque en la tarjeta
(D-2). Un manejador global de Escape exigiría JS o una petición por chip (una por cada número de
la página); se descarta en esta historia.

Además, `hx-sync` aborta una petición **ya lanzada**, pero no el temporizador de `delay:150ms` de
htmx: si Escape llega en los 150 ms posteriores al foco y antes de que arranque la petición de
apertura, esta puede arrancar después y repoblar la tarjeta. La ventana es de 150 ms, no hay forma
de cancelarla sin JS y la segunda Escape la cierra; se declara como límite, no se oculta.

## 4. D-2 · Puntero: recorrerla, persistir y no atravesarla

### 4.1 La tarjeta es zona de puntero

- Se quita `pointer-events: none` de [`web.css:2052`](../../src/zascarr/static/web.css:2052) y
  [`web.css:2056`](../../src/zascarr/static/web.css:2056). La tarjeta pasa a ser hoverable y a
  recibir clics (que la descartan, D-1) en vez de dejarlos pasar.
- **Puente de 8 px** en la variante anclada, para cruzar el hueco de `top: calc(100% + 8px)` sin
  perder `:hover`:

  ```css
  .chip-previa:not(.chip-previa-lista) > .previa-numero::after {
    content: "";
    position: absolute;
    left: 0; right: 0;
    top: -8px; height: 8px;   /* solo zona de puntero, sin pintar nada */
  }
  ```

  El puente es hijo de la tarjeta, así que pisarlo mantiene `:hover` en el chip; no se solapa con
  el chip más que el borde exacto, y no bloquea el enlace (no se extiende sobre su caja).
- **Sin recorte.** `overflow:hidden` en [`web.css:2057`](../../src/zascarr/static/web.css:2057)
  recorta el puente **y la flecha** (P-8). El recorte de esquinas pasa a la tarjeta interior
  (`.previa-card`) y el contenedor que dibuja flecha/puente queda visible. La flecha de
  [`web.css:2074-2078`](../../src/zascarr/static/web.css:2074) debe verse; si no se ve, la prueba
  de Chrome (T9) falla.
- El clic en cualquier punto de la tarjeta (imagen, pie o puente) descarta; **no** activa botones,
  enlaces ni formularios de debajo. Esto incluye el caso de Colecciones: un clic sobre la previa
  fija que tapa «Quitar de la colección» **no** lanza el POST de baja.

### 4.2 Persistencia (WCAG 1.4.13)

- Sin timeout: la tarjeta no se cierra sola. Permanece mientras el puntero esté sobre el chip o la
  tarjeta (o mientras el foco esté dentro del chip, en la variante de foco).
- Se aparta al salir del hover/foco, con <kbd>Escape</kbd> (D-1) o con clic/toque en la tarjeta.
- La animación de 120 ms no condiciona el estado: con `prefers-reduced-motion` no hay animación y
  la tarjeta sigue apareciendo, siendo hoverable y descartable.
- Límite: al ser una tarjeta de 220 px y no haber *flip*, cubre chips vecinos mientras está
  abierta. Ya no roba el clic, solo hay una y se aparta; el solape visual restante se acepta y se
  registra (D-6). Cambiar posición/tamaño queda fuera de alcance.

## 5. D-3 · Una sola previa y prioridad del foco

Reglas CSS objetivo:

```css
/* Se abre la anclada con el puntero; la fija ya no se abre por hover (D-4). */
.chip-previa:not(.chip-previa-lista):hover > .previa-numero:not(:empty),
.chip-previa:focus-within > .previa-numero:not(:empty) { display: block; }

/* La previa del foco manda: si un chip tiene foco y contenido, no se pinta la de OTRO chip
   bajo el puntero. Es la regla que cierra «dos previas» (P-4). */
body:has(.chip-previa:focus-within > .previa-numero:not(:empty))
  .chip-previa:hover:not(:focus-within) > .previa-numero:not(:empty) { display: none; }
```

- `:has` ya se usa en la hoja (p. ej. [`web.css:368`](../../src/zascarr/static/web.css:368)); no
  hay dependencia nueva.
- Con hover en A y foco en B, **solo B** se pinta; al salir de B, A puede volver a pintarse si el
  puntero sigue encima (el contenido ya está cargado).
- La previa del chip enfocado queda **debajo** (anclada) o a la derecha (fija) del chip, no encima:
  el texto del chip, su anillo y el hueco del siguiente control deben poder medirse sin intersección
  con la tarjeta (AC-02). Si en la variante fija la tarjeta tapara al chip enfocado, la prueba de
  Chrome lo reporta como FAIL y hay que ajustar la posición (no se acepta tapar el foco).
- No se ocultan por JavaScript ni se vacían las previas viejas: el contenido sobrante queda oculto
  y se reemplaza al volver a enfocar/hover el chip.

## 6. D-4 · La variante fija: solo foco o botón, nunca hover

Afecta a los usos con `.chip-previa-lista`: archivos por número de la ficha, lista de Biblioteca y
lista de Colecciones.

- El enlace de esos chips pierde `mouseenter`:
  `hx-trigger="focusin delay:150ms"` (la anclada conserva `mouseenter` + `focusin`).
- El botón «Ver portada» ([`series_detail.html:400-403`](../../src/zascarr/web/templates/series_detail.html:400),
  [`_rejilla_biblioteca.html:123-126`](../../src/zascarr/web/templates/_rejilla_biblioteca.html:123),
  [`coleccion_detalle.html:85-88`](../../src/zascarr/web/templates/coleccion_detalle.html:85))
  sigue siendo el disparador explícito con `hx-trigger="click"` y pasa a estar visible **también
  con puntero fino**: [`web.css:2654`](../../src/zascarr/static/web.css:2654) deja de ser una
  regla solo para `(hover:none), (pointer:coarse)` y el botón mantiene 44 px de alto. Sin esto,
  al quitar el hover los ratones de escritorio se quedarían sin previa en las listas.
- La tarjeta se pinta a la derecha (escritorio) o sobre la barra inferior (≤860 px / puntero
  grueso, regla existente [`web.css:2657-2665`](../../src/zascarr/static/web.css:2657)). El botón
  no es un interruptor: vuelve a pedir la previa si se pulsa otra vez; para apartarla se usa
  Escape, clic en la tarjeta o salir con el foco. Así no se añade estado ni JS.
- Al tapar acciones (p. ej. «Quitar de la colección»), el orden es: primero se aparta la previa
  (clic/Escape); el botón de debajo nunca recibe el clic por accidente. Cuando el foco sale del
  chip, la tarjeta se oculta y el siguiente control queda libre y visible.
- **Alternativa descartada:** anclar la tarjeta en el flujo de la lista (como la anclada). En estas
  listas cubriría las filas siguientes y obligaría a un puente sobre decenas de píxeles; no
  resuelve el solape, cambia el diseño y añade riesgo. Queda para otra historia si el PO lo pide.

## 7. D-5 · Texto, indicador, ARIA, Enter y trampa

### 7.1 Copy y aspecto

- [`_previa_numero.html:6`](../../src/zascarr/web/templates/_previa_numero.html:6): se sustituye
  «Pulsa para abrir la ficha» (falso: la tarjeta no es enlace) por
  **«Vista previa · Esc o clic para apartarla»**.
- [`_previa_serie.html:1-4`](../../src/zascarr/web/templates/_previa_serie.html:1) recibe el mismo
  indicador en su pie, para que las dos tarjetas se comporten y lean igual.
- Se conserva `Nº N · título` (o `título · año` en la de serie), el pie a 14 px
  (`--text-secundario`, [`web.css:2066-2073`](../../src/zascarr/static/web.css:2066)), las cifras
  `tabular-nums`, la flecha visible y la animación anulable. Nada de glifos de texto ni iconos
  nuevos.
- El pie no promete una acción que la tarjeta no hace; la vía para abrir el número sigue siendo el
  chip enlazado.

### 7.2 ARIA y foco

- La tarjeta sigue siendo **decorativa**: el contenedor vacío de las plantillas conserva
  `aria-hidden="true"` ([`series_detail.html:17`](../../src/zascarr/web/templates/series_detail.html:17),
  [`series_detail.html:411`](../../src/zascarr/web/templates/series_detail.html:411),
  [`_rejilla_biblioteca.html:127`](../../src/zascarr/web/templates/_rejilla_biblioteca.html:127),
  [`coleccion_detalle.html:89`](../../src/zascarr/web/templates/coleccion_detalle.html:89)); todo su
  subárbol, imagen incluida, queda fuera del árbol de accesibilidad (la del número lleva `alt=""`).
- **Cero elementos enfocables** dentro de la tarjeta: sin enlaces, botones, `tabindex`, `role`,
  `inert` ni `autofocus`. El nombre accesible del chip no cambia y el lector de pantalla no recibe
  contenido nuevo.
- **Sin trampa:** Tab y Shift+Tab siguen su orden normal; Escape no mueve el foco ni llama a
  `preventDefault` sobre Tab; la tarjeta no atrapa ni redirige el foco. El clic en la tarjeta no
  es un control con foco (su equivalente de teclado es Escape).
- **Enter abre:** el `<a href>` del chip no lleva `hx-trigger` de `click`; pulsar <kbd>Enter</kbd>
  navega a la ficha como hoy y no dispara ninguna petición htmx. El botón «Ver portada» responde a
  Enter con su propia acción (mostrar/refrescar la previa), como cualquier botón.
- Si el PO quisiera que la tarjeta se anuncie o un botón «Cerrar» dentro, habría que sacarla de
  `aria-hidden` y gestionar foco (historia aparte; no se recomienda: añade ruido y un control
  extra para un contenido repetido).

## 8. D-6 · Persistencia, umbral, evidencia y documentación

- **Sin timeout ni cierre automático**; el único cierre es salir de hover/foco, Escape o clic.
  `prefers-reduced-motion` solo quita la animación.
- **Umbral:** se conserva la ocultación de la variante anclada en `≤860 px` o `pointer:coarse`
  ([`web.css:2083`](../../src/zascarr/static/web.css:2083)). A 1024 px o con zoom 125 % sobre 1440
  se puede probar el recorrido completo; a 720 px (zoom 200 % de 1440) la previa anclada no se
  sirve y el E2E lo registra como **límite declarado** (sin solape, foco/texto/Enter visibles), no
  como PASS de «previa en ancho reducido». La fija de las listas sigue disponible con su botón.
  Cambiar el umbral exige otra historia (toca diseño y móvil).
- **Límite del Escape solo-teclado:** ver §3.4. Se documenta en la evidencia y en la ficha.
- **Solape restante:** la tarjeta grande cubre chips vecinos mientras está abierta; ya no roba el
  clic, solo hay una y se aparta. Sin flip ni reposicionamiento (P-7); se registra como limitación
  aceptada, no como deuda oculta.
- **Evidencia:** `docs/design/uatp05/resultado-chrome.md` (nuevo), con Chrome y versión, SHA,
  viewports, capturas y PASS/FAIL/NOT RUN por fila. Sin navegador no hay PASS.
- **Docs que se actualizan en la implementación:**
  - [`benchmark-BL-INF4-portada-numero.md`](benchmark-BL-INF4-portada-numero.md) §2/§3/limitación:
    la previa es hoverable y descartable, con puente; una sola previa con prioridad del foco; la
    variante fija ya no se abre por hover.
  - [`especificacion-BL-INF4-portada-numero.md`](especificacion-BL-INF4-portada-numero.md): AC-4
    (de «decorativo y no atrapa» a «descartable/hoverable/persistente»), quitar «encima» y
    `pointer-events:none` de §5.
  - [`sistema-de-diseno-zascarr.md`](sistema-de-diseno-zascarr.md), sección de interacción y
    accesibilidad: regla de contenido en hover/foco (WCAG 1.4.13: descartable, hoverable,
    persistente; el clic no atraviesa; solo una a la vez). Si el squad considera que es una
    versión publicada nueva, se regenera también el PDF.
  - [`ui-migracion.md`](ui-migracion.md): contrato de cliente de la previa (rutas, `cerrar=1`,
    `hx-trigger`/`hx-sync`, reglas CSS y umbral).
  - [`docs/TESTING_E2E.md`](../TESTING_E2E.md) §13: subsección 13.8 con el recorrido de §11.
  - Issues #1143 y #1141: comentario con SHA, pruebas y enlace a la evidencia. No cerrar sin
    navegador real y decisión del PO.
  - `docs/BACKLOG.md`: **no se toca** hasta cerrar (CLAUDE.md §9); entonces, nota del mecanismo.

## 9. Criterios de aceptación (UATP-05)

Trazabilidad: AC de #1143 «descartable sin mover foco» → AC-01/AC-02; «texto e indicador del
siguiente» → AC-02/AC-03; «puntero y WCAG 1.4.13» → AC-03/AC-04; «Enter y sin trampa» → AC-05;
«prueba a 1440 y ancho reducido/zoom» → AC-06; benchmark P-1…P-8 → AC-01…AC-05.

- **AC-01 · Escape aparta sin mover el foco.** Con el foco en un chip y su previa cargada,
  <kbd>Escape</kbd> vacía el hueco y oculta la tarjeta; `document.activeElement` es el mismo
  elemento, su `:focus-visible` sigue visible y no hay navegación ni POST. Funciona en la anclada
  y en la fija (enlace y botón). La ruta responde `200` vacío con `Cache-Control: no-store` y no
  consulta la BD.
- **AC-02 · El siguiente control queda visible.** Con el puntero parado en el chip anterior y el
  foco en el siguiente (Tab), se pinta **solo** la previa del enfocado y el rectángulo del chip
  enfocado (texto y anillo) no intersecta ninguna tarjeta visible; `elementFromPoint` en su centro
  devuelve el chip. Se cumple también en la fija (la tarjeta no tapa el título enfocado).
- **AC-03 · Hoverable y persistente (WCAG 1.4.13).** Al mover el puntero del chip a la tarjeta
  cruzando el hueco de 8 px, la tarjeta no parpadea ni se cierra; se puede recorrer y permanece sin
  timeout mientras el puntero esté dentro. Al salir se oculta. La flecha se ve (P-8) y el puente no
  recorta.
- **AC-04 · El clic no atraviesa.** Un clic/toque en cualquier punto de la tarjeta visible no
  activa ningún enlace, botón ni formulario de debajo (comprobado sobre el «Quitar de la
  colección» de Colecciones) y la descarta. No se dispara el POST de baja ni una navegación.
- **AC-05 · Enter, ARIA y sin trampa.** <kbd>Enter</kbd> en el chip abre la ficha con el `href`
  (sin petición htmx). La tarjeta conserva `aria-hidden="true"` y no contiene nada enfocable;
  Tab/Shift+Tab no se interceptan, Escape no mueve el foco y no hay bucle ni trampa. El pie dice
  «Vista previa · Esc o clic para apartarla».
- **AC-06 · Una sola previa.** Con hover en A y foco en B hay exactamente una tarjeta visible (la
  de B); la de A queda oculta. Al salir de B, A puede reaparecer. No se acumulan previas.
- **AC-07 · Variante fija bajo control.** Los chips `.chip-previa-lista` no abren nada al pasar el
  ratón; abren con foco o con «Ver portada», que está disponible también con puntero fino (44 px).
  Al salir el foco se oculta; no deja acciones tapadas sin salida y el clic en la tarjeta no
  activa la acción de debajo.
- **AC-08 · Cierre competitivo.** Si se pulsa Escape con la petición de apertura **ya lanzada** (tras
  los 150 ms de espera), la petición en curso se aborta (`hx-sync=…:replace`) y la tarjeta no
  reaparece después; una segunda Escape no hace nada visible. La ventana de 150 ms previa al
  arranque (límite de §3.4) no la cubre esta AC y se documenta como tal. La prueba de Chrome con
  red lenta acredita el caso con la petición en vuelo.
- **AC-09 · Evidencia 1440 / reducido / zoom / reduced-motion.** Matriz de §11 ejecutada en Chrome
  estable (versión y SHA registrados), con capturas de abierta, descartada y siguiente control, y
  PASS/FAIL/NOT RUN por fila. A 720 px / zoom 200 % se registra el límite (previa anclada oculta).
- **AC-10 · Sin ampliación de alcance.** No hay JS nuevo (`hx-on`, scripts, ficheros), ni
  dependencias, migraciones, rutas nuevas (solo el parámetro `cerrar`), ni cambios en el lector, la
  caché de portadas o `docs/BACKLOG.md`. BL-INF4 (#590) sigue PASS y el lector no se toca: las
  comprobaciones de #1072 que hoy pasan quedan igual.

## 10. Casos de prueba

Nombres orientativos; lo exigible es el caso y su espera.

| # | Tipo | Caso | Dónde | Espera |
|---|---|---|---|---|
| T1 | Web | `?cerrar=1` en las tres rutas de previa: 200 vacío + `no-store`; no llama a `db.get` ni a `ruta_previa` | `test_web_portada_numero.py` | AC-01 |
| T2 | Web | Sin `cerrar` no cambia nada: fragmento con miniatura, sin portada → vacío, 404 ajeno, imagen 304/404 | `test_web_portada_numero.py` | AC-10 |
| T3 | Estático | Los cuatro envoltorios llevan el cierre (`?cerrar=1`, `keyup[key=='Escape']`, `click from:find .previa-numero`, `hx-target` correcto, `hx-sync`); la anclada conserva `mouseenter`, la fija no; el enlace no lleva trigger de clic | `test_web_ficha_447.py`, `test_web_library.py`, `test_web_colecciones.py` | AC-01/05/07 |
| T4 | Estático | La tarjeta no tiene enfocables y conserva `aria-hidden="true"`; el subárbol queda fuera del árbol de accesibilidad (imagen del número con `alt=""`); pie «Vista previa · Esc o clic para apartarla» en las dos tarjetas; 14 px y `tabular-nums` | `test_web_portada_numero.py` + plantillas | AC-05 |
| T5 | CSS | Sin `pointer-events:none`; puente de 8 px; el recorte no oculta la flecha; regla `:has` de una sola previa con prioridad del foco; la fija no se pinta en `:hover`; botón visible con puntero fino; umbral 860/coarse intacto | `test_web_css_previa.py` | AC-02/03/06/07 |
| T6 | Web | Render de ficha, Biblioteca lista y Colecciones: atributos nuevos, botón visible, objetivo de cada previa; sin 500/422 | `test_web_ficha_447.py`, `test_web_library.py`, `test_web_colecciones.py` | AC-01/07 |
| T7 | Regresión | BL-INF4: imagen 240 px, ETag/304, 404 sin caché, fragmento vacío sin previa, 404 de número ajeno, no-store; contraste/tokens y 320 px | comandos §11 | AC-10 |
| T8 | Estático | No hay JS nuevo en la previa: sin `hx-on` ni `<script>` en sus plantillas y sin cambios en `static/lector.js`; solo atributos htmx (`hx-get`, `hx-trigger`, `hx-sync`, `hx-target`, `hx-swap`) | revisión + CI | AC-10 |
| T9 | Chrome real | Matriz §11: Escape sin mover foco, siguiente visible, puente/hover, clic que no atraviesa, una sola previa, fija, Enter, aborto con red lenta, reduced-motion, 1024/zoom y 720 | Chrome + `docs/design/uatp05/resultado-chrome.md` | AC-01…AC-09 |
| T10 | Docs | Este doc con decisión del PO, E2E 13.8 y correcciones de BL-INF4/UI; comentario en #1143 | revisión | D-6 |

## 11. Evidencia E2E (Chrome real)

Preparar una serie con varios números con archivo (la ficha y la rejilla), una lista de Biblioteca y
una colección con al menos 3 series. Registrar **Chrome estable, versión, SHA, fecha y sistema**.
Capturas obligatorias por viewport aplicable: **abierta**, **descartada** y **siguiente control**.
La evidencia de cierre del piloto UAT se anota además en `A3/resultado.md` (referenciado por #1141).

| Fila | Cómo | Esperado |
|---|---|---|
| V1 · 1440×900 | Tab al chip; esperar la tarjeta; Escape; Tab al siguiente | AC-01/02: foco y anillo intactos, una sola previa, siguiente visible |
| V2 · 1440 hover | Hover en un chip; mover el puntero despacio hasta la tarjeta cruzando el hueco; recorrerla; clic en ella | AC-03/04: no parpadea, se recorre, la flecha se ve, el clic la descarta y no activa nada |
| V3 · 1440 dos previas | Puntero parado en el chip A y foco en el chip B | AC-06: exactamente una visible (B); A oculta |
| V4 · 1440 fija | En Biblioteca/lista y Colecciones: foco en el enlace y luego «Ver portada»; Escape; clic sobre la tarjeta que tapa «Quitar» | AC-07/04: abre solo así, no por hover, 44 px, sin POST de baja |
| V5 · 1440 Enter | Foco en el chip con previa abierta; <kbd>Enter</kbd> | AC-05: navega a la ficha, sin petición htmx, sin trampa |
| V6 · 1440 red lenta | CDP `Network.emulateNetworkConditions` lento (o número CBR); esperar a que la petición esté en vuelo y pulsar Escape | AC-08: la tarjeta no reaparece al terminar la carga |
| V7 · reduced-motion | Emular `prefers-reduced-motion: reduce`; abrir, recorrer, Escape | AC-03/01: sin animación, mismo comportamiento |
| V8 · 1024×768 o zoom 125 % | Repetir V1–V3 | AC-02/06: sin scroll horizontal, tarjeta dentro del viewport, foco visible |
| V9 · 720×900 (zoom 200 % de 1440) | Repetir V1 con la ficha y, si aplica, la lista | Límite de §8: la anclada no se sirve; foco/texto/Enter intactos; la fija con botón se puede abrir/descartar |
| V10 · 390×844 táctil emulado | Toque en «Ver portada» y toque en la tarjeta | AC-07/04: abre/cierra sin scroll horizontal; la anclada sigue oculta (límite) |

**Reglas de evidencia:** una fila no ejecutada es **NOT RUN**, no PASS. Safari/iOS, Firefox, lector
de pantalla, móvil/táctil físico, Pi y `forced-colors` reales quedan **NOT RUN** declarados. Las
capturas y la tabla final viven en `docs/design/uatp05/resultado-chrome.md`.

**Pruebas automáticas** desde la raíz del repo:

```bash
pytest -q tests/test_web_portada_numero.py tests/test_web_css_previa.py \
  tests/test_web_ficha_447.py tests/test_web_library.py tests/test_web_colecciones.py \
  tests/test_web_css_contraste.py tests/test_web_css_320.py
ruff check src/ tests/
```

No hace falta Postgres (FakeSession + TestClient). La suite completa se ejecuta con el directorio
temporal en el mismo dispositivo que `/` (CLAUDE.md §8). Las pruebas de navegador son NOT RUN sin
Chrome.

## 12. Dependencias y orden

1. **T1–T2** (rutas `cerrar=1`) primero: es el contrato que usa el resto.
2. **T3–T4** (marcado de los cuatro usos y copy/ARIA) y **T5** (CSS de puntero, puente, recorte y
   una sola previa).
3. **T6** (renders) y **T7–T8** (regresión y no-JS).
4. **T9** Chrome (con red lenta y reduced-motion) y **T10** docs.
5. Después: UI/UX y QA independientes; SecOps solo si el PO considera que el clic/toque o el
   `hx-sync` lo requieren (no hay red ni permisos nuevos). No hay migración.

## 13. Decisiones propuestas (resumen)

| D | Recomendación | Motivo | Si el PO pide lo contrario |
|---|---|---|---|
| **D-1** | `cerrar=1` en las 3 rutas + `keyup[key=='Escape']` y clic en el envoltorio, con `hx-sync=…:replace`; foco intacto | Cierra P-1 y la carrera de una carga lenta sin JS | Sin `hx-sync`: un Escape durante la carga puede repoblarse; habría que declararlo |
| **D-2** | `pointer-events:auto` + puente de 8 px + recorte en la tarjeta interior; el clic descarta y no atraviesa | Cierra P-2/P-3 y hace la flecha visible (P-8) | Sin puente: el puntero no puede recorrerla; WCAG 1.4.13 Hoverable FAIL |
| **D-3** | Una sola previa con prioridad del foco mediante `:has` | Cierra P-4 y deja ver el texto/anillo del siguiente | Sin prioridad: dos previas y foco tapado |
| **D-4** | La fija solo con foco o botón (sin hover); botón visible también con puntero fino | Cierra P-6 y evita el POST accidental de Colecciones | Mantener hover: hay que mover la tarjeta fuera de las acciones y probarlo |
| **D-5** | Tarjeta decorativa, sin enfocables; pie «Vista previa · Esc o clic para apartarla»; Enter nativo | Cierra P-5 y conserva la semántica de BL-INF4 | Hacerla enlace/región: nombre accesible, doble enlace y foco nuevos |
| **D-6** | Sin timeout; umbral 860/coarse intacto; E2E 1440, 1024/125 %, 720/200 % como límite y reduced-motion; docs + evidencia | Deja PASS/FAIL/NOT RUN separados y no amplía el alcance | Cambiar el umbral o el tamaño: otra historia con su prueba móvil |

**Decisión del PO (2026-11-21):** se **aceptan D-1…D-6** tal como se recomiendan en la tabla. La
implementación (task-53) los aplica sin ampliar alcance; el cierre de #1143/#1141 sigue pendiente
de las revisiones independientes (UI/UX, QA) y de la matriz E2E de §11.

## 14. Notas de implementación (task-53, 2026-11-21)

Rama `feat/uatp05-previa-teclado`, sobre `origin/main` = `d5f26df5`. Sin JS nuevo, sin
dependencias, sin migración y sin tocar `docs/BACKLOG.md`.

- **Rutas.** `previa_numero`, `previa_serie` (series) y `previa_serie` (colecciones) aceptan
  `cerrar: bool = Query(False)` y, con `cerrar=1`, devuelven `HTMLResponse("")` con
  `Cache-Control: no-store` antes de consultar la BD o el disco. Cubierto por pruebas que
  envenenan `db.get` y `ruta_previa`/`portada_cacheada`.
- **Marcado.** Los cuatro envoltorios llevan el `hx-get` de cierre, `keyup[key=='Escape']` y
  `click from:'find .previa-numero'` con `hx-target` a su hueco y
  `hx-sync="closest .chip-previa:replace"`; los enlaces y botones de apertura comparten esa cola.
  La variante anclada conserva `mouseenter delay:150ms, focusin delay:150ms`; las fijas solo
  `focusin delay:150ms` y su botón «Ver portada» (visible también con puntero fino).
- **CSS.** `pointer-events` de la tarjeta a `auto` (por omisión y en la fija), puente de 8 px solo
  en la anclada, `overflow:hidden` movido a `.previa-card` (la flecha y el puente ya no se
  recortan), `:has` para que mande la previa del foco y la fija sin `:hover`.
- **Copy y ARIA.** Pie «Vista previa · Esc o clic para apartarla» en las dos tarjetas; la tarjeta
  sigue `aria-hidden="true"`, sin enfocables ni roles, e imagen con `alt=""`.
- **Inventario de query.** `cerrar` se añade a `PARAMETROS_DE_QUERY` de `tests/test_log_acceso.py`
  con el motivo: es una orden de cierre sin datos de la persona (la prueba de inventario la exige).

**Prueba de humo (no sustituye a T9).** Chrome headless 158 (`HeadlessChrome/158.0.0.0`) con una
página que replica el marcado del contrato y un servidor local: foco → abre; <kbd>Escape</kbd> →
vacía el hueco y `document.activeElement` sigue en el enlace; hover → abre; clic en la tarjeta →
cierra y no activa el botón de debajo; la fija no abre por hover pero sí con foco; y con una
respuesta de 1,2 s en vuelo, <kbd>Escape</kbd> aborta y la tarjeta no reaparece (AC-08). La
matriz §11 en la app real, con capturas y viewports, sigue **NOT RUN**.

**Pendiente (fuera de task-53).** Evidencia `docs/design/uatp05/resultado-chrome.md`; revisiones
UI/UX y QA; actualizar `benchmark-BL-INF4-portada-numero.md`,
`especificacion-BL-INF4-portada-numero.md`, `sistema-de-diseno-zascarr.md` y `ui-migracion.md`
(§8, D-6); comentario en #1143/#1141 y `docs/BACKLOG.md` al cerrar.
