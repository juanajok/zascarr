# Benchmark de UX — el final de un tebeo en el lector (BL-LEC)

> **Ficha de benchmarking de nivel 2** según [`benchmark-referencias.md`](benchmark-referencias.md)
> y CLAUDE.md §13. **Fecha:** 2026-11-21. **Base contrastada:** `origin/main` `f570bfa1`.
> **Historia:** BL-LEC / BL-LEC3 (#826), tarjeta de fin del lector.
> **Insumo, no aprobación:** decide el PO. Este documento **no implementa** nada.

## 1. Problema local

**Qué pasa hoy.** Al llegar a la última página, `lector.js` muestra automáticamente una
tarjeta de fin (`<section id="fin">`) que el servidor ya ha pintado. En el cascarón inmersivo
del lector, esa tarjeta se coloca como capa absoluta abajo, con ancho máximo de `42rem` y hasta
`calc(100dvh - 6rem)` de alto (`src/zascarr/static/web.css`, `.lector-escena .lector-fin`).
En el móvil queda sobre la última página, que es justo la que el coleccionista quiere ver
completa; el usuario lo describe como un «cuadro de diálogo con opciones que tapa gran parte
de la última página».

**Por qué importa.** La última página suele contener el cierre de la historia o un gag; taparla
en el instante en que se llega rompe la lectura y obliga a cerrar un panel antes de poder mirar.
La tarjeta también mezcla tres tareas distintas: terminar la lectura, decidir si seguir y
gestionar el número (marcar leído, Deseados, volver).

**Medición de partida.**

- La tarjeta aparece **sola**, sin gesto del lector, en cuanto `pagina === total`.
- Es una capa `position:absolute` sobre el lienzo, no una página del flujo.
- Puede ocupar desde una franja de acciones hasta casi todo el alto de la pantalla.
- El JS actual la enseña y esconde en cada `pinta()` (`if (fin && fin.hidden !== !enFin)`).
- No hay medición de uso real de la tarjeta; **NOT RUN**.

## 2. Referencias consultadas

| Referencia | Versión / fuente | Licencia | Qué hace al terminar | Evidencia |
|---|---|---|---|---|
| **Komga** | issue #722, resuelto en 0.132.2; endpoint `GET /api/v1/books/:id/next` | MIT | Al final, **insistir** (tecla o clic) lleva al siguiente libro; no hay tarjeta automática que tape la página. El endpoint de siguiente es explícito. | [issue #722](https://github.com/gotson/komga/issues/722), [API next](https://komga.org/docs/openapi/get-book-sibling-next/) |
| **Kavita** | Wiki del lector, 2026; issue webui #154 | GPL-3.0 | Controles «Previous/Next Chapter» en el lector; la propuesta original era prompt, salto automático o **página falsa** que informe del siguiente. Su modo fullscreen no permite zoom (dato de contexto, no del fin). | [wiki](https://wiki.kavitareader.com/guides/readers/comic-manga/), [issue #154](https://github.com/Kareadita/Kavita-webui/issues/154) |
| **Suwayomi WebUI** | v1.5.0 | MPL-2.0 | **Página de transición** entre capítulos; no es una tarjeta modal sobre la última página. | [release v1.5.0](https://newreleases.io/project/github/Suwayomi/Suwayomi-WebUI/release/v1.5.0), [issue #912](https://github.com/Suwayomi/Suwayomi-WebUI/issues/912) |
| **YACReader** | iOS 3.5.0; foro oficial | GPL-3.0 (desktop) | Al intentar pasar más allá de la última página, abre un **popup con la portada del siguiente**; tocar la portada lo abre. Hay ajuste «Open next/previous comic on page turn action». | [novedades 3.5.0](https://yacreader.com/52-new-features-in-yacreader-3-5-0-for-ios), [foro](https://yacreader.com/forum/suggestions/2377-auto-skip-start-next-chapter-confirmation) |
| **Panels** | guía oficial 2026 | propietaria | «Continue reading»: al llegar al final, **seguir desplazándose** salta al siguiente título de la misma carpeta; no hay diálogo. | [guía Continue reading](https://guides.panels.app/read-content/continue-reading) |
| **KOReader** | guía 26.11 | AGPL-3.0 | Al llegar al final muestra un **diálogo** con «Open next file»; salta los archivos marcados como terminados. Se puede configurar el comportamiento al final. | [guía, §8.3](https://koreader.rocks/user_guide/#L2-manganextfile) |
| **Chunky** | reseña de usuario | propietaria | Al acabar muestra una **miniatura de la portada del siguiente**; tocarla lleva allí. | [reseña](https://bgrasley.wordpress.com/tag/manga/) (fuente secundaria) |
| **CDisplayEx / Perfect Viewer** | fichas de mercado previas | propietarias | Ofrecen el siguiente álbum / botones de siguiente y anterior; el detalle exacto de la UI no se ejecutó. | [`benchmark-BL-LEC-mercado-lectores-2026.md`](benchmark-BL-LEC-mercado-lectores-2026.md), NOT RUN |
| **Mihon** | commit de lector | Apache-2.0 | Barra de lector con botones anterior/siguiente que se ocultan o deshabilitan según existan capítulos; no hay tarjeta automática de fin. | [commit #5305](https://git.mihon.tech/mihon/mihon/commits/commit/fdf178d4df5ca4819c972ca2730e86ef173beeca) |

**Corrección a la ficha anterior:** [`benchmark-BL-LEC-mercado-lectores-2026.md`](benchmark-BL-LEC-mercado-lectores-2026.md)
dejó L12 «al acabar, el siguiente número» como NOT RUN. Esta ficha lo cubre: el mercado se
divide entre (a) **insistir para avanzar** (Komga, YACReader), (b) **saltar al seguir
desplazando** (Panels), (c) **página de transición** (Suwayomi, propuesta de Kavita) y
(d) **diálogo con siguiente** (KOReader, YACReader con portada, Chunky). Ninguna referencia
seria **enseña una tarjeta modal automática que tape la última página**.

## 3. Supuestos de las referencias que no valen aquí

1. **Un «libro/capítulo» es una unidad**: aquí un número puede tener varios archivos y un
   pack cubre varios números (ADR 0003). El «siguiente» lo decide `siguiente_numero` (#826),
   no el nombre ni `sort_order`.
2. **Hay un botón de siguiente visible siempre**: en ZascArr el lector es inmersivo y táctil;
   las flechas no se ven en móvil. El gesto de avanzar debe ser el mismo que pasa página.
3. **La app puede hacer scroll infinito**: aquí el lector es paginado y comparte modo doble,
   RTL y zoom; una transición no debe romper esos estados.
4. **El progreso es de la app**: aquí la fuente es `ReadingProgress`; no se puede inventar un
   «Leído» sin reflejarlo.
5. **Un diálogo modal es aceptable**: en una Pi, en el móvil, sobre una página que se está
   mirando, no lo es. La referencia de producto de ZascArr pide que el contenido mande.

## 4. Opciones de solución

### A. Estado actual: tarjeta modal automática

La tarjeta se muestra al llegar. Ventaja: acciones visibles sin gesto. Inconveniente: tapa la
última página justo al llegar; mezcla decisiones; el cierre no forma parte de la lectura.

### B. Barra de fin mínima (siempre visible, ~44–64 px)

Una franja en el borde con «Fin · Siguiente #K» y un botón «Opciones». No tapa el centro,
pero sigue ocupando parte del lienzo y compite con el gesto de leer.

### C. Tarjeta solo bajo intención

La última página se ve entera. Solo al **intentar pasar** (swipe, flecha, espacio) se muestra
la tarjeta de acciones. Resuelve el problema principal sin cambiar el flujo de páginas.
Sigue siendo una capa modal, pero ya no sorprende ni tapa una página que no se ha podido ver.

### D. Página de fin dentro del flujo (recomendada)

La última página se ve entera. Al intentar pasar de página se entra en una **página de fin**
—a pantalla completa, como una contraportada o colofón— con la portada del siguiente número,
la frase de cierre y las acciones. No es un popup: es la página siguiente, y «atrás» vuelve a
la última página. Es el patrón de Suwayomi (transición), la propuesta de Kavita (página falsa),
la portada de YACReader/Chunky y el «siguiente» de Komga, adaptado a la navegación de ZascArr.

Ventajas:

- la página que se acaba de leer **nunca queda tapada**;
- el gesto para ver el final es el mismo que para pasar página (swipe/space/flecha);
- da contexto: portada del siguiente, serie, número que falta;
- no hay backdrop ni trampa de foco; es contenido, no un diálogo;
- no necesita petición extra: el servidor ya pinta la tarjeta;
- funciona igual en escritorio, tablet, móvil, doble página, RTL y fullscreen.

Inconvenientes:

- hay que cambiar el contrato visual de `#fin` y el JS que lo muestra;
- hay que decidir si la página de fin cuenta como «página» (recomendado: no, el contador
  sigue en N de N; es una página de cierre, no una página del tebeo);
- el usuario que no intenta avanzar no ve las acciones: es deliberado; el botón de la barra
  y el menú pueden ofrecer «Fin del número» para quien lo busque.

### E. Salto automático al siguiente (estilo Panels/Komga sin confirmación)

Al pasar la última página se abre el siguiente número. Ventaja: cero fricción. Inconveniente:
puede saltarse la contemplación de la última página y no permite decidir; en una biblioteca
con ediciones y packs, el «siguiente» puede no ser el que la persona espera. No se recomienda
como defecto; podría ser una preferencia futura.

### F. Sin UI propia: reutilizar la ficha del número

Al terminar, volver a la ficha o al Inicio («Continuar leyendo»). Ventaja: cero pantalla nueva.
Inconveniente: rompe la lectura, pierde el contexto de «siguiente» y no resuelve «te falta»;
es peor que D.

## 5. Matriz de decisión

Pesos por defecto de [`benchmark-referencias.md`](benchmark-referencias.md) (suman 100), sin
moverlos: encaje con el Coleccionista 25 · coste en Pi 20 · seguridad/legalidad 20 · cobertura
del requisito 15 · adaptabilidad al stack 10 · mantenimiento 5 · lock-in 5. Puntuación 1–5.

| Criterio (peso) | A. Modal automática (hoy) | B. Barra mínima | C. Tarjeta bajo intención | D. **Página de fin en flujo** | E. Salto automático | F. Volver a la ficha |
|---|---:|---:|---:|---:|---:|---:|
| Encaje con el Coleccionista (25) | 2 | 3 | 4 | **5** | 3 | 2 |
| Coste en Pi (20) | 5 | 5 | 5 | **5** | 5 | 5 |
| Seguridad, legalidad (20) | 4 | 4 | 4 | **4** | 4 | 4 |
| Cobertura del requisito (15) | 3 | 3 | 4 | **5** | 3 | 2 |
| Adaptabilidad al stack (10) | 5 | 5 | 4 | **4** | 5 | 5 |
| Mantenimiento (5) | 4 | 4 | 4 | **4** | 4 | 5 |
| Lock-in y salida (5) | 5 | 5 | 5 | **5** | 5 | 5 |
| **Total ponderado /100** | **74,0** | **79,0** | **85,0** | **93,0** | **79,0** | **~72** |

No es una medición de usuario: es una decisión de diseño informada por las referencias.
**NOT RUN:** prueba con coleccionistas reales y medición de tiempos/gestos.

## 6. Recomendación

**D. Página de fin dentro del flujo, activada por intención.**

### Comportamiento propuesto

1. **Al llegar a la última página**, no aparece nada. La página se ve entera; el contador
   sigue diciendo «Página N de N». El botón de avanzar (y el gesto) sigue disponible.
2. **Al intentar avanzar** (flecha, espacio, swipe o clic en la zona de avance), se entra en
   la página de fin:
   - **LEER:** portada del siguiente número, «Has terminado el #N. Siguiente: #K», botón
     primario «Leer el #K», «Quedarme en esta página» y «Volver a la serie».
   - **FALTA:** «Te falta el #K de *Serie*», «Añadir a Deseados» (con la puerta legal tal como
     está hoy), «Volver a la serie».
   - **SIN SIGUIENTE:** «No hay un número siguiente en tu biblioteca», «Volver a la serie».
3. **Atrás/gesto contrario** desde la página de fin vuelve a la última página, sin recargar.
4. La página de fin **no** cambia el contador a «N+1»: es una contraportada, no una página
   del tebeo. Sí puede anunciar «Fin del número» en la barra.
5. **Marcar leído:** el botón viaja a la página de fin. Recomendación al PO: **marcar «Leído»
   automáticamente al abrir la página de fin, con «Deshacer» visible**, porque el gesto de
   entrar ya expresa «he terminado». Si el PO prefiere no automatizar, se mantiene el botón
   explícito; es una decisión de producto, no de implementación.
6. **No se añade** un salto automático por defecto. Una preferencia «seguir automáticamente»
   podría ser otra historia, apagada por defecto.
7. **Accesibilidad:** la página de fin es una región con `h2` enfocable, el foco se mueve a
   ella, `aria-live` anuncia «Fin del número» y no hay trampa de foco ni backdrop modal.
8. **Sin petición extra:** el servidor ya pinta `#fin`; el JS solo lo convierte en la página
   siguiente del flujo. La portada del siguiente se sirve con la ruta local existente.

### Por qué D y no C

C elimina la sorpresa, pero sigue siendo una tarjeta sobre la página. D elimina también la
capa: el final pasa a ser contenido, y el gesto de pasar página es el mismo que en el resto
del tebeo. Las referencias que mejor puntúan en «no tapar» (Komga, YACReader, Panels,
Suwayomi, KOReader) no usan una modal automática; D toma lo que comparten y lo adapta a la
unidad de ZascArr.

### Qué NO se propone

- No copiar el **popup con portada** de YACReader como modal flotante: aquí la portada va en
  una página de fin completa, sin tapar.
- No adoptar el **salto automático** de Panels/Komga como defecto: la biblioteca tiene packs,
  ediciones y decimales; el «siguiente» debe seguir siendo el de `siguiente_numero`.
- No poner la tarjeta en un `dialog` HTML con backdrop: es contenido, no un diálogo.
- No añadir una petición de red para decidir el final; ya está en el HTML.

## 7. Casos de prueba para la historia

1. Última página: `#fin` **no** visible; la página completa es visible y el contador N/N.
2. Avanzar en la última página: aparece la página de fin **sin** recargar; foco en su `h2`.
3. Atrás/espacio inverso: vuelve a la última página; el contador sigue N/N.
4. Sin siguiente: la página de fin dice que no hay; no hay botón de Deseados.
5. Falta #K: texto y enlace/acción de Deseados; sin aviso legal, lleva a `/ui/legal`.
6. Leído: el botón funciona y «Deshacer» si se auto-marca (si el PO lo aprueba).
7. Modo doble, RTL, zoom y pantalla completa: la página de fin no tapa ni cambia la página
   de la que se viene; el gesto de volver funciona.
8. Teclado: `→`/espacio/`PageDown` en el final entra; `←`/`PageUp` vuelve; `Esc` no cierra
   el lector por accidente.
9. Móvil 375, tablet 768 y escritorio 1280: la página de fin es legible sin scroll horizontal;
   la última página se vio completa antes.
10. Sin JS: la página de fin puede quedar visible como contenido estático (degradación
    honesta) o el lector muestra la última página; decidir en la especificación.
11. No se rompe la tarjeta de preparación de RAR ni el fin de un pack.

## 8. Invariantes

- La última página nunca se cubre automáticamente.
- El «siguiente» es el de `siguiente_numero` (numeración, packs, huecos); nunca `sort_order`.
- No se escribe nada en la biblioteca; el lector sigue siendo de solo lectura.
- La página de fin no es una petición extra ni un nuevo endpoint.
- Español llano; un solo botón principal; foco visible; 44 px; sin diálogo nativo.
- Si el PO no acepta la automatización de «Leído», no se cambia el estado sin su decisión.

## 9. NOT RUN y caducidad

- **NOT RUN:** prueba con coleccionistas reales; medición de gestos/tiempos; render real en
  Pi/móvil/tablet; comportamiento con lector RAR preparando; prueba de la tarjeta actual con
  datos de uso. Las referencias se han leído en documentación/issue, no ejecutado cada app.
- **Fuente secundaria:** la reseña de Chunky y las fichas de CDisplayEx/Perfect Viewer no
  son documentación oficial; se usan solo como patrón, no como prueba de detalle.
- **Caduca:** ~60 días (2027-01-20), o antes si cambia el lector o una referencia.

## 10. Resultado por idea

| Idea | Resultado | Motivo |
|---|---|---|
| No tapar la última página al llegar | **Adoptar** (Komga, YACReader, Panels) | Es el problema del PO y lo comparten las referencias que mejor lo resuelven. |
| Entrar al final solo al intentar avanzar | **Adoptar** (Komga, YACReader) | Mismo gesto que pasar página; no sorprende. |
| Portada del siguiente como contexto | **Adaptar** (YACReader, Chunky) | En ZascArr va dentro de una página de fin, no en un popup flotante. |
| Página de transición en el flujo | **Adaptar** (Suwayomi; idea de Kavita) | Encaja con el lector paginado y el gesto de avanzar. |
| Diálogo con «Open next» | **Descartar como modal automático** (KOReader) | KOReader lo usa tras el final; aquí lo convertimos en página de fin. |
| Salto automático | **Descartar por defecto** (Panels/Komga) | Puede saltarse la contemplación y la unidad «número con varios archivos»; posible preferencia futura. |
| Barra mínima permanente | **Descartar** | Sigue ocupando lienzo; D la sustituye por contenido. |
| Marcar leído automático | **Candidata, decide el PO** | Es lo que hace el mercado, pero cambia el contrato de BL-C3; recomendación con «Deshacer». |
