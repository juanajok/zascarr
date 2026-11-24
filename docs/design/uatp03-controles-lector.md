# Recuperar los controles del lector móvil y volver al número (UATP-03 / UXA-10)

> **Estado:** implementada en TDD (task-34, 2026-11-21). El PO **aceptó D-1…D-5** (§12) y pidió
> continuar. **AC-09/T12 PASS** en Chrome 320×568, 390×844 y 568×320; evidencia en
> [`uatp03/resultado-chrome.md`](uatp03/resultado-chrome.md). Firefox/Safari/iOS/Android físico y
> lector de pantalla quedan **NOT RUN**.
> **Revisión 2026-11-23 (UATP-09 P1):** la lengüeta pasa a la esquina superior derecha y su rótulo
> «Controles» se desvanece a los 6 s; el control de 44×44 sigue visible y el rótulo vuelve al pasar el
> ratón o con el foco. Motivo y detalle en §3.2.
> El benchmark previo (**task-32**, 2026-11-21, solo lectura y no versionado) dictaminó NO PASA.
>
> **Insumos:** [#1127 · UXA-10](https://github.com/juanajok/zascarr/issues/1127) (ampliada por
> UATP-03), [#1141 · épica UATP](https://github.com/juanajok/zascarr/issues/1141),
> [#1126 · UXA-09](https://github.com/juanajok/zascarr/issues/1126),
> [#1072 · LECUX5](https://github.com/juanajok/zascarr/issues/1072),
> [#1118 · UXA-01](https://github.com/juanajok/zascarr/issues/1118),
> [#1119 · UXA-02](https://github.com/juanajok/zascarr/issues/1119),
> [#1157](https://github.com/juanajok/zascarr/issues/1157),
> PR [#1178](https://github.com/juanajok/zascarr/pull/1178),
> [#826](https://github.com/juanajok/zascarr/issues/826) y el benchmark de producto:
> [`benchmark-LECUX6-inmersivo-2026-11-17.md`](benchmark-LECUX6-inmersivo-2026-11-17.md),
> [`benchmark-BL-LEC-lector.md`](benchmark-BL-LEC-lector.md) y
> [`verificacion-LECUX5-2026-11-18.md`](verificacion-LECUX5-2026-11-18.md). La épica de
> referencia es [`epica-BL-LECUX-lector.md`](epica-BL-LECUX-lector.md).
>
> **Base de las referencias de línea:** `origin/main` = **`4e48fe5f`** (2026-11-21). El checkout
> de trabajo puede estar en otra rama; el implementador debe ramificar desde `origin/main`, no
> desde una copia local atrasada.
>
> **Único escritor de este documento:** SPEC.writer. No toca código, tests, otras docs ni
> `docs/BACKLOG.md`; la implementación y la evidencia son tareas aparte.

## 1. Problema y resultado esperado

Hoy el lector abre por defecto en modo **pantalla** (`data-modo="pantalla"`,
[`lector.html:7`](../../src/zascarr/web/templates/lector.html:7)) y el JS oculta la barra al
inicializar ([`lector.js:637`](../../src/zascarr/static/lector.js:637)). En móvil eso deja al
coleccionista ante una página limpia, sin ninguna señal de que existen controles. El benchmark
task-32 lo reprodujo en Chrome y midió el resto de hallazgos:

| # | Hallazgo del benchmark | Evidencia en la base | Decisión |
|---|---|---|---|
| P-1 | No hay señal visible de la barra. El toque central (30–70 %) la revela, pero no se descubre; en el borde superior el toque cambia de página | [`lector.js:640`](../../src/zascarr/static/lector.js:640) solo revela con `pointermove` de ratón; [`lector.js:793`](../../src/zascarr/static/lector.js:793) decide por `x` sin franja superior; no existe asa en [`lector.html`](../../src/zascarr/web/templates/lector.html) | D-1 |
| P-2 | Al cargar, el foco se fuerza al lienzo: deja marco `:focus-visible` y Tab sale del documento | [`lector.js:398`](../../src/zascarr/static/lector.js:398) llama a `lienzo.focus()` y [`lector.js:637`](../../src/zascarr/static/lector.js:637) lo ejecuta en la carga; el anillo está en [`web.css:3007`](../../src/zascarr/static/web.css:3007); sin flechas en táctil ([`web.css:3017`](../../src/zascarr/static/web.css:3017)), Tab cae fuera de la escena | D-2 |
| P-3 | Tocar texto no interactivo de Opciones cierra el panel y manda el foco a `main` | [`lector.js:628`](../../src/zascarr/static/lector.js:628) cierra por `focusout` cuando el foco sale a un destino que no es un control | D-2 |
| P-4 | RTL funciona, pero no hay prueba | La única prueba RTL cubre el fin de página ([`test_lector_js.py:737`](../../tests/test_lector_js.py:737)); no hay prueba del render RTL de la ruta ni del toque/teclado ordinario | D-3 |
| P-5 | Reabrir una lectura la deja en la página guardada, pero no hay prueba web de reapertura ni del acotado **de lectura** (el de escritura sí existe) | [`web/lector.py:67`](../../src/zascarr/web/lector.py:67) lee `current_page` y acota; [`test_lector.py:520`](../../tests/test_lector.py:520) usa una página guardada solo para comprobar el fin, no `data-pagina` ni `src` | D-4 |
| P-6 | UXA-01 y las pruebas de lector vigentes siguen PASS: «Cerrar» visible, `aria-expanded`, Escape devuelve foco y el chrome no se oculta con el foco dentro | [`test_lector_js.py:139`](../../tests/test_lector_js.py:139); PR [#1178](https://github.com/juanajok/zascarr/pull/1178); [`verificacion-LECUX5-2026-11-18.md`](verificacion-LECUX5-2026-11-18.md) | AC-08: no romper |
| P-7 | El guardado de progreso (`fetch` sin `keepalive`) puede perderse al salir o cerrar la pestaña enseguida | [`lector.js:277`](../../src/zascarr/static/lector.js:277) y [`web/lector.py:181`](../../src/zascarr/web/lector.py:181) | **Fuera de alcance** (§2); se registra el riesgo |

**Resultado esperado.** A 320, 390 y 568×320 px, con la barra oculta, hay una **señal visible**
(asa) que la muestra sin abrir Opciones y sin cambiar de página. Con la barra visible, «Volver al
número» es alcanzable sin scroll horizontal. Al cargar no hay foco forzado ni anillo; Tab entra en
la barra y la revela, y el foco no abandona la escena por accidente. Abrir y cerrar Opciones con
toque o Escape conserva página, modo e imagen, devuelve el foco al disparador y no se cierra al
tocar texto no interactivo. LTR y RTL se comportan y se prueban de forma distinguible. Reabrir
muestra la página guardada (acotada al total) y hay prueba web. Todo sin JS nuevo, sin
dependencias, sin migración y conservando UXA-01, UXA-02, #1072, #1157 y #826.

## 2. Alcance / no alcance

**Dentro:**

| Pieza | Cambio |
|---|---|
| [`lector.html`](../../src/zascarr/web/templates/lector.html) | Asa `#lector-asa` (D-1) y texto de ayuda actualizado; sin tocar el resto de controles. |
| [`lector.js`](../../src/zascarr/static/lector.js) | Mostrar/ocultar el asa, revelación por franja superior en táctil, foco inicial, ciclo de Tab, cierre de Opciones por toque, foco al disparador y lectura de la página guardada sin repintar a la 1. |
| [`web.css`](../../src/zascarr/static/web.css) | Estilos del asa (44×44), franja superior, anillo de foco solo con teclado y `:focus-within` existente. Tokens actuales, sin fuentes ni colores nuevos. |
| [`web/lector.py`](../../src/zascarr/web/lector.py) | Acotado de la página guardada a `[1, total]` (D-4), si el PO acepta la recomendación. |
| [`tests/test_lector.py`](../../tests/test_lector.py), [`tests/test_lector_js.py`](../../tests/test_lector_js.py) | Casos T1–T11 de §9. |
| Documentación | D-5 (§7): este doc, evidencia y docs de lector/E2E. |

**Fuera de alcance (explícito):**

- **Rediseñar o compactar la barra.** El benchmark midió ~198 px de alto a 320 px; reducirlo,
  reorganizar zoom/identidad o cambiar el modo inmersivo es otra historia. D-1 añade el asa y
  conserva el alto actual. En horizontal (568×320) esa barra deja poco alto de página: se registra
  como limitación conocida, no se corrige aquí.
- **`keepalive`, `sendBeacon`, `pagehide` o `visibilitychange` para el guardado de progreso.**
  El riesgo de P-7 se documenta y se deja para una historia de persistencia; UATP-03 no cambia
  `guarda()`.
- **Safari/iOS, Android físico, tablet física, Firefox y lector de pantalla.** Solo se exige
  Chrome (emulación de viewport) para AC-09; lo demás es **NOT RUN**, nunca PASS.
- Flechas visibles en táctil, insignia permanente de RTL, cambio de zonas de pase más allá de la
  franja superior, zoom, pantalla completa, OPDS, backend, modelo, migraciones o dependencias.
- Nuevo fichero JS: sigue habiendo un único `static/lector.js` (ADR 0021).
- Cerrar #1127/#1141 en el tablero o tocar `docs/BACKLOG.md` (solo al cerrar la P1, CLAUDE.md §9).

## 3. D-1 · Asa de controles

### 3.1 Marcado

Un solo botón, fuera de `<header class="lector-barra">` (si estuviera dentro, la transformación de
la barra lo ocultaría), como hermano inmediatamente anterior a `.lector-lienzo`:

```html
<button type="button" class="lector-asa" id="lector-asa"
        aria-label="Mostrar los controles" aria-controls="lector-barra" hidden>
  {{ icono("chevron_down") }}<span class="lector-asa-texto">Controles</span>
</button>
```

- El icono se toma de [`web/iconos.py`](../../src/zascarr/web/iconos.py) (`chevron_down` ya existe,
  Lucide/ISC); es decorativo (`aria-hidden`) y el nombre accesible es el `aria-label`.
- El rótulo «Controles» (UATP-09 P1) es **visual**: el nombre accesible sigue siendo el
  `aria-label`, y el rótulo se desvanece a los 6 s (ver §3.2). No es un segundo control.
- `aria-controls="lector-barra"` referencia el `id` real de la barra
  ([`lector.html:13`](../../src/zascarr/web/templates/lector.html:13)).
- No lleva `aria-expanded`: el control solo existe cuando la barra está plegada; cuando se
  despliega, desaparece. Poner un estado que nunca cambia confunde al lector de pantalla.
- `hidden` lo sincroniza el JS; el servidor lo pinta oculto para que un fallo de JS no muestre un
  control que no hace nada. Sin JS la barra nunca se oculta y el asa no aparece (degradación
  honesta).

### 3.2 Visibilidad y geometría

El asa está visible **solo** cuando se cumplen las tres condiciones: `raiz.dataset.chrome ===
"oculto"`, el fin de página (`#fin`) está cerrado y el lector no está en preparación. En el mismo
punto del JS que pone `data-chrome="oculto"` se pone `asa.hidden = false`; al revelar la barra se
pone `hidden = true`. No se acepta:

- que dependa de `programaOculto` (el temporizador de 3 s) ni de hover: en el mismo fotograma en
  que la barra pasa a oculta, el asa pasa a visible; no se acepta un intervalo perceptible con la
  barra oculta y el asa todavía ausente;
- que siga visible con la barra abierta o sobre la página de fin;
- que su ausencia se compense con un `title` (no existe en táctil).

Lo que sí se desvanece a los 6 s es **el rótulo**, no la caja: el control de 44×44 sigue visible
mientras la barra esté oculta. El rótulo es una etiqueta a la izquierda del botón, fuera de su
caja (no la ensancha), así que el icono no se mueve al recogerse. Vuelve entero al pasar el ratón o
al enfocar, y se desvanece de nuevo al salir; con cada ocultación de la barra vuelve a mostrarse otros
6 s. Es CSS (`@keyframes lector-asa-rotulo`) y no añade estado al JS.

Geometría y contraste (revisión 2026-11-23):

- caja táctil mínima **44×44 px CSS** (`min-width: 44px; min-height: 44px`), icono de ~20 px; el
  rótulo es una etiqueta absoluta a su izquierda y no altera esa caja;
- `position: absolute; top: var(--space-2); right: var(--space-2); z-index: 4` (debajo de la
  barra, `z-index: 5`; encima de las flechas, `z-index: 3`). Con una página que no llena ambos
  ejes cae en el margen superior o lateral y **no sobre la viñeta**; si la página llena la
  pantalla (tableta vertical con página a sangre), no hay margen: queda el botón de 44×44 en la
  esquina y el rótulo, que solo vive 6 s, es lo único que puede rozar el dibujo. El centro del
  borde superior quedaba encima del dibujo y, con el rótulo, la caja medía ~117×44;
- fondo: **velo de papel al 75 %** (`color-mix(in srgb, var(--paper) 75%, transparent)`) para que la
  viñeta se transparente cuando el botón cae encima; tinta, icono y borde van **opacos**. En el
  peor caso (tinta clara sobre una viñeta blanca) el texto/icono del control queda en 7,09:1, medido
  en `TestVeloDelLector`; con `prefers-contrast: more` vuelve a papel opaco. Borde
  `var(--border-panel) solid var(--ink)` en los cuatro lados y las cuatro esquinas con
  `var(--radius-panel)`; el rótulo usa `--border-chip` y el mismo velo; sin token, color ni fuente
  nuevos;
- el rótulo se desvanece (`opacity`/`visibility`), sin animar anchura ni mover el botón; con
  `prefers-reduced-motion: reduce` se recoge de golpe (`step-end`);
- foco visible con el anillo existente (`outline: 3px solid var(--ink)`), también en
  `forced-colors: active` (`CanvasText`); sin animación propia que retrase la aparición del asa
  (la animación es solo del rótulo y puede saltarse con el hover o el foco).

### 3.3 Activación

Al activar el asa con toque, clic, <kbd>Enter</kbd> o <kbd>Espacio</kbd>:

1. `data-chrome` pasa a `""` (barra visible) y el asa se oculta;
2. el foco se mueve al **primer control de la barra**, `Volver al número` (el primer enfocable del
   DOM dentro de `#lector-barra`); con teclado el anillo se ve; con toque no debe quedar un marco
   `:focus-visible` permanente sobre ese control (comprobación en Chrome, AC-09);
3. no cambia `data-pagina`, ni la imagen, ni el modo, ni el zoom, ni los filtros de imagen; no se
   hace `POST /progreso` ni `POST /sentido`;
4. no se abre Opciones y no hay navegación.

El foco al primer control es deliberado: el asa desaparece al pulsarla, así que dejarlo en un
elemento recién oculto perdería el foco. Si el foco no se puede mover (control desaparecido), cae
en `#lector-barra` o en el `body` de la escena, nunca en `main`.

### 3.4 ¿Revela todo el borde superior? Decisión

**Sí, en táctil, como franja de 44 px de alto y todo el ancho, solo con la barra oculta.** El asa
se apoya en esa franja (revisión 2026-11-23: empieza 8 px dentro) y es la señal visible; la franja
es su ampliación táctil. Al tocar en ella se revela la barra **sin cambiar de página**. Fuera de la
franja se mantienen las zonas actuales (izquierda/centro/derecha,
[`lector.js:793`](../../src/zascarr/static/lector.js:793)).

Motivo: el hallazgo P-1 es que el borde superior hacía pasar página cuando la persona esperaba
controles; ocultar esa expectativa detrás de un asa de 44×44 vuelve a dejar una zona «muerta» de
568×44 px en horizontal. La franja conserva el gesto esperado y el asa lo hace descubrible.

Límites de la decisión:

- **En ratón/lápiz se conserva** la revelación existente al acercarse a la franja
  (`pointermove` con `clientY <= 90`, [`lector.js:640`](../../src/zascarr/static/lector.js:640)),
  **solo cuando el asa está oculta** (barra ya revelada). Con el asa visible no se auto-revela:
  en una trayectoria real (x=500, y=300→90→22) el primer evento bajo 90 revelaría y ocultaría el
  asa antes de llegar al clic. El ratón pulsa el asa para revelar; después el hover de la franja
  sigue disponible. No compite con el toque.
- La franja **solo revela con la barra oculta**; con la barra visible, un toque en el borde no
  hace nada distinto de lo actual.
- Las zonas de pase se calculan después de descartar la franja: un toque en la esquina superior
  izquierda revela; uno en el tercio izquierdo **por debajo de 44 px** retrocede (LTR). Esto se
  prueba en T6. Solo el **toque sin desplazamiento** revela: un deslizamiento que empieza en la
  franja sigue siendo un deslizamiento normal (pasa página según §5.2).
- Alternativa descartada: que el borde superior no revele y todo quede en el asa. No resuelve la
  expectativa que falló en P-1 y deja una zona amplia que hace lo contrario de lo esperado.

### 3.5 Ayuda actualizada

En `<details class="lector-ayuda">` ([`lector.html:57`](../../src/zascarr/web/templates/lector.html:57)),
después de la frase actual ([`lector.html:59`](../../src/zascarr/web/templates/lector.html:59)), se
añade exactamente:

> «Para volver a ver los controles, toca la lengüeta «Controles» o el centro de la página.»

No se usan glifos de texto (⌄) ni jerga («asa», «chrome», «overlay»). La ayuda ya menciona
<kbd>h</kbd> para teclado; no se duplica.

## 4. D-2 · Foco, Tab y Opciones

### 4.1 Al cargar no se fuerza el lienzo

- La ocultación **inicial** de la barra no mueve el foco: al terminar la carga,
  `document.activeElement` es `document.body` y ningún elemento de `.lector-escena` cumple
  `:focus-visible`. Se elimina el efecto de [`lector.js:398`](../../src/zascarr/static/lector.js:398)
  en ese camino (la función puede conservar el foco al lienzo cuando la persona **pide** entrar en
  pantalla completa o cambiar a modo pantalla; eso no es la carga).
- No se añade `autofocus` en la plantilla. No se hace scroll ni se pinta anillo por la carga.
- El teclado de páginas sigue funcionando desde `body` (el manejador ya admite `target ===
  document.body`, [`lector.js:694`](../../src/zascarr/static/lector.js:694)); no hace falta enfocar
  el lienzo para leer con flechas.

### 4.2 Tab entra en la barra, la revela y no sale de la escena

El lector es una escena modal (`position: fixed; inset: 0`), no una página más. Contrato:

1. **El enlace `Saltar al contenido` no se ofrece en el lector**: su destino (`#main`) queda
   debajo de la escena y no lleva a nada útil. Se oculta con
   `body:has(.lector-escena) .skip { display: none; }` para que la primera parada de Tab sea la
   barra (regresión a comprobar: fuera del lector, el enlace sigue igual).
2. Con la barra oculta y el foco en `body`, **el primer Tab entra en la barra** y la revela:
   `data-chrome` pasa a `""`, se cancela el auto-ocultado y el foco se queda en `Volver al
   número`. No se exige pulsar el asa ni el centro.
3. **El foco no abandona `.lector-escena` con Tab/Shift+Tab.** Desde el último enfocable visible
   (en táctil, el lienzo; en escritorio, la última flecha o el control de fin si está abierto),
   Tab vuelve al primer control de la barra; desde el primero, Shift+Tab va al último. El ciclo se
   calcula con los enfocables **visibles en ese momento** (`display`, `hidden`, `offsetParent`),
   no con una lista fija que ignore las flechas ocultas o la página de fin. **Excepción:** si el
   foco está dentro de la escena pero en un elemento que no entra en el ciclo (p. ej. `#fin-titulo`
   con `tabindex="-1"`), no se intercepta: el Tab nativo va al primer control de la página de fin,
   sin revelar la barra ni taparla (#826).
4. Salir sigue siendo explícito: `Volver al número` (enlace o <kbd>Escape</kbd> con la barra
   visible) y el botón de la ficha. El ciclo de foco no encierra a nadie: no se intercepta
   <kbd>Escape</kbd> ni se bloquea la navegación.
5. Tras un toque o clic en el lienzo, este no queda con un marco `:focus-visible` permanente; si
   el navegador le da el foco, el siguiente Tab va al primer control de la barra (punto 3), no al
   chrome del navegador.

### 4.3 Opciones: abrir, tocar, cerrar y volver

El panel ya tiene «Cerrar» visible en cabecera fija (PR [#1178](https://github.com/juanajok/zascarr/pull/1178),
[`lector.html:32`](../../src/zascarr/web/templates/lector.html:32)); se conserva y se le exige:

- **Abrir** con toque, clic, <kbd>Enter</kbd> o <kbd>Espacio</kbd>: `aria-expanded="true"`, el
  foco se queda en el disparador (`#lector-menu-boton`), la barra queda visible y no se toca la
  página.
- **Tocar texto no interactivo del panel** (título, `legend`, párrafos, ayudas y la frase de
  origen del sentido): el panel **no se cierra** y el foco **no se va a `main`/`body` de la
  aplicación**. Se puede seguir leyendo el panel y pulsar sus
  controles. La implementación debe distinguir «el foco se perdió porque el destino no es
  enfocable» de «la persona salió a un control de fuera»: un `pointerdown`/`touchstart` dentro del
  panel no es motivo de cierre; el cierre por `focusout` solo procede cuando el foco llega a un
  enfocable fuera del panel.
- **Cerrar** con «Cerrar» o <kbd>Escape</kbd>: `aria-expanded="false"`, el panel se oculta, el
  foco vuelve al disparador `#lector-menu-boton`, la barra queda visible y no cambian página, modo,
  zoom ni filtros de imagen; no hay `POST /progreso` ni `POST /sentido`.
- **Tab que sale del panel** hacia un control fuera (p. ej. el lienzo) cierra el panel **sin robar
  el foco**: el foco se queda donde el navegador lo llevó. No se fuerza el retorno al disparador en
  ese caso; el retorno al disparador es solo para Cerrar/Escape.
- El comportamiento de Escape con la barra oculta (revelarla) y con la barra visible y sin panel
  (volver al número) no cambia ([`lector.js:657`](../../src/zascarr/static/lector.js:657)).
- No se anuncia nada nuevo por `aria-live`: los anuncios actuales de #1072 se mantienen.

### 4.4 Señales observables para AC-03/AC-04

| Comprobación | Valor esperado |
|---|---|
| `document.activeElement` tras la carga | `body`; ningún `:focus-visible` dentro de `.lector-escena` |
| Primer <kbd>Tab</kbd> con barra oculta | foco en `Volver al número`; `raiz.dataset.chrome === ""` |
| <kbd>Tab</kbd> desde el lienzo (táctil) | foco en el primer control de la barra, no en el chrome del navegador |
| Toque en texto del panel | `#lector-menu` visible; `activeElement` no es `#main` |
| «Cerrar» / <kbd>Escape</kbd> | panel oculto; foco en `#lector-menu-boton`; `aria-expanded="false"`; `data-pagina` y `src` intactos |
| Cualquier apertura/cierre de Opciones | `data-pagina`, `data-modo`, zoom y filtros de imagen sin cambios; sin peticiones de progreso/sentido |

## 5. D-3 · LTR/RTL: comportamiento y «distinguible»

### 5.1 Contrato del servidor

- El sentido se decide en `services/lector.py` (serie > ComicInfo > tradición) y se pinta en
  `data-sentido="rtl|ltr"` y `data-origen-sentido="serie|comicinfo|tradicion"`
  ([`lector.html:8`](../../src/zascarr/web/templates/lector.html:8)); no se recalcula en cliente.
- En RTL, las etiquetas accesibles de las flechas describen la **acción**, no el lado: la flecha
  izquierda es «Página siguiente» (o «Ver el final» en la última página) y la derecha es «Página
  anterior»; en LTR, al revés. La plantilla ya las intercambia
  ([`lector.html:89`](../../src/zascarr/web/templates/lector.html:89)) y `pinta()` las actualiza
  ([`lector.js:259`](../../src/zascarr/static/lector.js:259)).
- El botón de Opciones muestra «Sentido: derecha a izquierda» / «Sentido: izquierda a derecha»
  ([`lector.html:40`](../../src/zascarr/web/templates/lector.html:40)) y el párrafo de origen dice
  de dónde sale ([`lector.html:61`](../../src/zascarr/web/templates/lector.html:61)).
- Las páginas dobles se ordenan con `flex-direction: row-reverse` cuando
  `data-sentido="rtl"` ([`web.css:2830`](../../src/zascarr/static/web.css:2830)): la primera de la
  pareja queda a la derecha.

### 5.2 Matriz de comportamiento (misma en LTR y RTL, espejada)

| Acción | LTR | RTL |
|---|---|---|
| Toque en el tercio izquierdo (bajo la franja) | retrocede | avanza |
| Toque en el centro | revela | revela |
| Toque en el tercio derecho (bajo la franja) | avanza | retrocede |
| Deslizar hacia la izquierda | avanza | retrocede |
| Deslizar hacia la derecha | retrocede | avanza |
| <kbd>→</kbd> / <kbd>PageDown</kbd> | avanza | ← avanza; PageDown avanza |
| <kbd>←</kbd> / <kbd>PageUp</kbd> | retrocede | → retrocede; PageUp retrocede |
| Flecha izquierda visible | «Página anterior» | «Página siguiente» |
| Pareja en modo doble | primera a la izquierda | primera a la derecha |

La franja superior (D-1) revela en los dos sentidos y no cambia de página.

### 5.3 Qué se considera «distinguible» (criterio verificable)

Un lector puede saber en qué sentido está sin probar a ciegas si se cumplen **las cinco**:

1. `data-sentido` está en el HTML y Opciones dice el sentido en texto visible («Sentido: derecha a
   izquierda»), además de explicar su origen.
2. Las flechas, cuando existen, tienen nombres accesibles de **acción** («Página siguiente») y su
   lado físico se intercambia en RTL.
3. En modo doble, el orden visual de la pareja está espejado y la primera página cae a la derecha.
4. Toque, deslizamiento y teclado respetan la matriz de §5.2; la prueba lo comprueba en ambos
   sentidos, no solo en LTR.
5. LTR no cambia: las pruebas LTR existentes siguen PASS.

**Decisión:** no se añade una insignia persistente «RTL» ni flechas visibles nuevas en táctil. A
320 px el ancho útil no da para más cromo (la barra ya mide ~198 px de alto) y el sentido se
consulta en Opciones; lo que falta no es una señal nueva, sino **probar** el comportamiento que ya
existe. Si el PO quiere una señal permanente, es una historia de diseño aparte con su prueba a
320/390.

### 5.4 Pruebas exigidas

- **Web** (T7): render LTR y RTL de `/ui/leer/{id}`: `data-sentido`, etiquetas de las flechas,
  texto de sentido y origen; sin `500`/`422`.
- **JS** (T6): en RTL, toque izquierdo avanza y derecho retrocede; deslizar a la derecha avanza y a
  la izquierda retrocede; <kbd>←</kbd> avanza y <kbd>→</kbd> retrocede; en LTR lo contrario. Se
  añade a la prueba de comportamiento existente sin duplicar el arnés.
- **Chrome** (T12): con una serie en RTL, comprobar que el toque izquierdo avanza y el orden de la
  pareja doble; dejar constancia de la versión y del sentido usado.

## 6. D-4 · Página guardada y acotado

### 6.1 Contrato

- `ReadingProgress.current_page` es la fuente; se lee por `issue_id`, no por `file_id`
  ([`web/lector.py:67`](../../src/zascarr/web/lector.py:67)). Sin progreso, página 1.
- La página servida se **acota** a `[1, total]`: `max(1, min(guardada, total))`. Si la guardada
  supera el total (el archivo cambió de número de páginas), se sirve **la última**, no la primera:
  reiniciar a 1 contradice «reanudar donde lo dejé». Si es 0 o negativa, la 1. Cambio recomendado
  sobre [`web/lector.py:71`](../../src/zascarr/web/lector.py:71) (hoy reinicia a 1); el acotado de
  escritura ya existe en [`services/lector.py:296`](../../src/zascarr/services/lector.py:296).
- El HTML inicial ya lleva la página correcta: `data-pagina`, `src` de `#lector-pagina`, `alt`,
  contador y `#fin` coherentes; el JS no pinta la 1 para luego saltar. Sin parpadeo ni petición a
  `/pagina/1`.
- No hay migración, columna ni escritura nueva.

### 6.2 Casos que debe cubrir la prueba web (T8/T9)

| Caso | Esperado |
|---|---|
| Sin `ReadingProgress` | `data-pagina="1"`, `src` acaba en `/pagina/1` |
| Progreso 2 de 3 | `data-pagina="2"`, `src` `/pagina/2`, `alt` y contador «Página 2 de 3» |
| Progreso 99 de 3 | `data-pagina="3"`, `src` `/pagina/3` (acotado a la última) |
| Progreso 0 o −5 de 3 | `data-pagina="1"` |
| Total 1 | página 1, contador «Página 1 de 1» |
| Progreso de otro archivo del mismo número | se usa igualmente (la clave es el número) |

La prueba no depende de Postgres: `FakeSession` + `TestClient`, como el resto de
[`test_lector.py`](../../tests/test_lector.py). El E2E de Chrome (T12) reabre de verdad: avanzar a
la página N, volver al número y abrir otra vez; la imagen servida debe ser N.

## 7. D-5 · Documentación

Parte de la implementación, no de esta tarea:

| Doc | Cambio |
|---|---|
| Este documento | Estado final, SHA, enlaces al PR y a la evidencia; D-1…D-5 con la decisión del PO. |
| `docs/design/uatp03/resultado-chrome.md` (nuevo) | Evidencia AC-09: Chrome y versión, SHA, 320×568, 390×844 y 568×320; PASS/FAIL/NOT RUN por fila y capturas. Sin fila PASS si no se ejecutó el navegador. |
| [`docs/TESTING_E2E.md`](../TESTING_E2E.md) | Nueva subsección en §13 «Look-and-feel (navegador real)»: pasos de UATP-03 y plantilla de evidencia. |
| [`docs/design/epica-BL-LECUX-lector.md`](epica-BL-LECUX-lector.md) | Nota en D-LUX7/D-LUX8 ([`:536`](epica-BL-LECUX-lector.md:536)): asa visible con chrome oculto y franja superior de 44 px que revela en táctil; el resto del comportamiento inmersivo no cambia. |
| [`docs/design/ui-migracion.md`](ui-migracion.md) | Añadir las rutas de `/ui/leer` a §4 (hoy no figuran) y el contrato de cliente `data-chrome`/`#lector-asa`/foco. |
| `docs/BACKLOG.md` | **No se toca** hasta cerrar la P1 (CLAUDE.md §9); entonces, nota del mecanismo. |
| Issues #1127 y #1141 | Comentario con SHA, pruebas y enlace a la evidencia; no cerrar sin Chrome y sin decisión del PO. |

## 8. Criterios de aceptación (UATP-03)

Trazabilidad: CAs de #1127 → AC-01/02/04/07/08; ampliación UATP-03 de #1127 → AC-01…AC-08;
benchmark task-32 P-1 → AC-01/02; P-2 → AC-03; P-3 → AC-04; P-4 → AC-07; P-5 → AC-06; P-6 →
AC-08; P-7 → AC-10 (fuera de alcance).

- **AC-01 · Asa visible y descubrible.** Con `data-chrome="oculto"` y `#fin` cerrado, a 320, 390 y
  568×320 px hay un `#lector-asa` visible, de al menos 44×44 px, con icono SVG, `aria-label="Mostrar
  los controles"` y `aria-controls="lector-barra"`. No depende de hover ni del temporizador de 3 s
  (visible en el primer fotograma con la barra oculta). Con la barra visible o sobre `#fin` no
  aparece. Sin JS, no aparece.
- **AC-02 · El asa revela sin cambiar de página.** Activarla con toque, clic, <kbd>Enter</kbd> o
  <kbd>Espacio</kbd> muestra la barra (`data-chrome=""`), oculta el asa, mueve el foco a `Volver al
  número` y no cambia `data-pagina`, imagen, modo, zoom ni filtros; sin POST de progreso/sentido.
  Con teclado se ve el anillo del primer control; con toque no debe quedar un marco permanente.
- **AC-03 · Foco inicial y Tab.** Al cargar, `activeElement` es `body` y ningún elemento de la
  escena cumple `:focus-visible`; no se fuerza el lienzo. El primer <kbd>Tab</kbd> entra en la
  barra, la revela y deja el foco en `Volver al número`. <kbd>Tab</kbd> desde el último enfocable
  visible vuelve al primer control de la barra y <kbd>Shift+Tab</kbd> al revés; el foco no sale de
  `.lector-escena` con Tab. <kbd>Escape</kbd> y el enlace de vuelta siguen saliendo.
- **AC-04 · Opciones con toque y Escape.** Abrir conserva `aria-expanded="true"` y el foco en el
  disparador. Tocar texto no interactivo del panel no lo cierra ni manda el foco a `main`.
  «Cerrar» y <kbd>Escape</kbd> lo cierran, dejan `aria-expanded="false"`, devuelven el foco a
  `#lector-menu-boton` y conservan página, modo, zoom e imagen, sin POST. Tab fuera del panel lo
  cierra sin robar el foco.
- **AC-05 · Volver al número sin scroll horizontal.** Con la barra visible a 320, 390 y 568×320 px,
  `Volver al número` es visible, mide ≥44 px de alto y se puede activar sin scroll horizontal:
  `document.documentElement.scrollWidth <= window.innerWidth` y el rectángulo del enlace cae dentro
  del viewport. Al activarlo se vuelve a la ficha del número; el progreso guardado no se pierde.
- **AC-06 · Reabrir en la página guardada y acotar.** La prueba web pinta la página guardada
  (`data-pagina`, `src`, `alt`, contador) sin pasar por la 1; sin progreso, 1; 99/3 → 3; 0/−5 → 1;
  total 1 → 1. El E2E de Chrome reabre y ve la misma página. El acotado de escritura sigue
  devolviendo 204 y guardando dentro de `[1,total]`.
- **AC-07 · LTR/RTL distinguibles con prueba.** Se cumple §5.3: render web LTR y RTL correcto
  (`data-sentido`, etiquetas de acción, texto de sentido y origen), matriz de toque/deslizamiento/
  teclado espejada y probada en ambos sentidos, pareja doble espejada, y LTR sin regresión. La
  prueba no se limita al fin de página.
- **AC-08 · Regresiones conservadas.** Siguen PASS: «Cerrar» visible y `aria-expanded` (#1178),
  Escape devuelve foco (UXA-01), atajos de un carácter solo con foco en el lienzo (#1179), chrome
  que no se oculta con el foco dentro ni con Opciones abierto (#1072), pasar página sin mostrar la
  barra (#1157), flujo de la página de fin y «Quedarme» (#826) y `UXA-01`/`#1072` en las suites
  existentes.
- **AC-09 · Evidencia Chrome 320/390/568×320.** **PASS** en Chrome, con capturas y medidas en
  [`uatp03/resultado-chrome.md`](uatp03/resultado-chrome.md). Safari/iOS, Android/tablet física,
  Firefox y lector de pantalla quedan **NOT RUN** y se declaran; la prueba con móvil físico del cierre de #1141 no
  se declara PASS desde esta historia.
- **AC-10 · Sin desbordamiento de alcance.** No se toca el alto de la barra (~198 px), el guardado
  con `keepalive`, el backend/modelo/migraciones, las dependencias ni el número de ficheros JS
  (ADR 0021). `docs/BACKLOG.md` no se modifica en la implementación; la documentación de D-5 sí.

## 9. Casos de prueba

Nombres orientativos; lo exigible es el caso y su espera.

| # | Tipo | Caso | Dónde | Espera |
|---|---|---|---|---|
| T1 | Estático/template | Asa en el HTML con `aria-label`, `aria-controls`, icono, `hidden`; CSS 44×44 y regla solo con `data-chrome="oculto"`; ayuda con la frase nueva | `tests/test_lector.py` | AC-01/AC-02 |
| T2 | JS (Node/DOM) | Sincronía `hidden` del asa con `data-chrome` y `#fin`; clic revela, oculta el asa, enfoca `Volver al número`; página/modo/zoom sin cambios y sin fetch | `tests/test_lector_js.py` | AC-01/AC-02 |
| T3 | JS | Carga en modo pantalla: no se llama `lienzo.focus()`, `activeElement` es `body`, ningún `:focus-visible`; `ocultarBarraInmersiva` solo enfoca cuando la petición es explícita (fullscreen/modo) | `tests/test_lector_js.py` | AC-03 |
| T4 | JS | Tab desde `body` entra en la barra y la revela; Tab desde el último visible vuelve al primero; Shift+Tab desde el primero va al último; no sale de la escena | `tests/test_lector_js.py` | AC-03 |
| T5 | JS | Opciones: toque en texto no interactivo no cierra ni mueve a `main`; «Cerrar» y Escape cierran con foco en el disparador; `aria-expanded`; página/modo/imagen intactos | `tests/test_lector_js.py` | AC-04 |
| T6 | JS | Zonas: franja superior revela sin cambiar página; tercio izquierdo/derecho cambian según LTR/RTL; centro revela; deslizamiento espejado; teclado espejado | `tests/test_lector_js.py` | AC-07/AC-04 |
| T7 | Web | Render LTR y RTL de `/ui/leer/{id}`: `data-sentido`, `aria-label` de flechas, «Sentido: …», origen del sentido; 200 sin 500/422 | `tests/test_lector.py` | AC-07 |
| T8 | Web | Sin progreso → 1; progreso 2/3 → `data-pagina="2"` y `src` 2; 99/3 → 3; 0/−5 → 1; otro archivo del mismo número usa el progreso | `tests/test_lector.py` | AC-06 |
| T9 | Servicio/web | Escritura acota a `[1,total]` y responde 204; lectura y escritura comparten el mismo criterio | `tests/test_lector.py` | AC-06 |
| T10 | Estático | «Volver al número» es el primer control de la barra, ≥44 px y sin `white-space: nowrap` que desborde; la franja de 44 px solo revela con chrome oculto | `tests/test_lector.py` / `test_web_css_320.py` | AC-05 |
| T11 | Regresión | Suites de lector (incl. RAR/preparación, fin, siguiente), contraste/tokens y `ruff`; UXA-01/#1072/#1179/#826 sin cambios | comandos §10 | AC-08/AC-10 |
| T12 | Navegador real | Matriz Chrome 320×568, 390×844 y 568×320: AC-01…AC-07 con medidas, teclado y toque; PASS/FAIL/NOT RUN por fila | Chrome + `docs/design/uatp03/resultado-chrome.md` | AC-09: **PASS** |

## 10. Evidencia y comandos

**Pruebas automáticas:** desde la raíz del repo,

```bash
pytest -q tests/test_lector.py tests/test_lector_js.py tests/test_lector_siguiente.py \
  tests/test_aviso_lector_rar.py tests/test_web_css_contraste.py tests/test_web_css_320.py
ruff check src/ tests/
```

- Las pruebas JS requieren `node`; si no está, se marcan **NOT RUN**, no PASS.
- La suite completa se ejecuta con el directorio temporal en el mismo dispositivo que `/`
  (CLAUDE.md §8). No hace falta Postgres para T1–T11.

**Chrome (AC-09).** Registrar versión, SHA, fecha y sistema; para cada viewport
(320×568, 390×844, 568×320) medir y capturar:

| Fila | Cómo | Esperado |
|---|---|---|
| Asa | `#lector-asa` visible con barra oculta; `getBoundingClientRect()` ≥44×44; `hidden=false`; `aria-label`/`aria-controls` | AC-01 |
| Primer fotograma | Cargar en modo pantalla; el asa no espera hover ni 3 s | AC-01 |
| Toque/ratón en asa | `data-chrome=""`, página/imagen/modo sin cambios, foco en `Volver al número`; con ratón, la trayectoria y=300→90→22 no revela ni oculta el asa antes del clic | AC-02 |
| Carga/Tab | `document.activeElement === document.body`; sin `:focus-visible` en la escena; Tab llega a `Volver al número`, la barra se ve; Tab desde el lienzo no sale del documento | AC-03 |
| Opciones | Abrir, tocar el título/leyenda/párrafo (no se cierra, foco no va a `main`), «Cerrar» y Escape (foco al disparador, `aria-expanded=false`, página intacta) | AC-04 |
| Volver al número | Rectángulo del enlace dentro del viewport; `scrollWidth <= innerWidth`; clic vuelve a `/ui/series/.../numero/...` | AC-05 |
| Reabrir | Avanzar a N, volver, reabrir: `src` `/pagina/N`, contador N/M; repetir con 99/3 → 3 | AC-06 |
| RTL | Sentido RTL; toque izquierdo avanza, derecho retrocede; etiquetas de acción; pareja doble espejada | AC-07 |
| Regresión | Pasar página con toque y deslizamiento no muestra la barra; Opciones y fin siguen bien | AC-08 |

**Reglas de evidencia:** un AC con prueba Node/TestClient puede ser PASS de código, pero AC-09
solo es PASS si las tres viewports se ejecutaron en Chrome. Una fila no ejecutada es **NOT RUN**,
no PASS. Safari/iOS, Android/tablet física, Firefox y lector de pantalla: **NOT RUN** declarado.
Las capturas y la tabla final viven en `docs/design/uatp03/resultado-chrome.md`.

## 11. Dependencias y orden

1. **T1–T2** (asa + CSS + JS de visibilidad/activación) y **T3–T4** (foco inicial y Tab) primero:
   son el contrato que más toca la escena.
2. **T5–T6** (Opciones y zonas/RTL) y **T7** (render RTL).
3. **T8–T9** (página guardada y acotado) y **T10**.
4. **T11** regresión; luego **T12** Chrome y docs de D-5.
5. Después: UI/UX y QA independientes (matriz §8), SecOps si el PO considera que el foco/ciclo de
   Tab o el acotado lo requieren; no hay superficie de red ni permisos nuevos.

## 12. Decisiones propuestas

| D | Recomendación | Motivo | Si el PO pide lo contrario |
|---|---|---|---|
| **D-1** | Asa 44×44 visible solo con chrome oculto; **sí** revela la franja superior de 44 px en táctil; con ratón y asa visible no hay auto-revelación (se pulsa el asa; el hover sigue tras revelar); ayuda actualizada | Resuelve P-1 sin dejar el borde superior «muerto» y sin convertir el centro en el único gesto | Sin franja: solo asa; hay que aceptar que el borde superior siga pasando página y probarlo |
| **D-2** | Sin foco al lienzo en la carga; primer Tab a la barra; ciclo de foco dentro de la escena; Opciones no se cierra al tocar texto; Cerrar/Escape al disparador; página intacta | Corrige P-2/P-3 y conserva UXA-01 | Sin ciclo de foco: Tab puede salir; habría que declararlo limitación |
| **D-3** | Comportamiento espejado + pruebas web y JS; «distinguible» = §5.3; sin insignia ni flechas nuevas en táctil | P-4 pide prueba, no UI nueva; a 320 px no cabe más cromo | Insignia/flechas: historia de diseño aparte con prueba a 320/390 |
| **D-4** | Acotar a `[1,total]`, con la última si la guardada supera el total; prueba web de reapertura y acotado | «Reanudar» no debe reiniciar a 1; cierra el hueco de P-5 | Mantener el reinicio a 1: una línea y una prueba; documentar que no es «clamp» |
| **D-5** | Docs de §7; evidencia Chrome aparte; BACKLOG solo al cerrar | Deja rastro repetible y separa PASS de NOT RUN | — |

**Decisión del PO (2026-11-21):** D-1…D-5 **aceptadas**; task-34 las implementa. La historia no se
declara cumplida hasta el E2E de Chrome (AC-09) y la revisión independiente.
