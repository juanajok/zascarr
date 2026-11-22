# Ficha de benchmarking — calidad de la interfaz frente a listas de comprobación (2026-11-22)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13), pedida por el PO: contrastar
> ZascArr con listas de comprobación y guías de calidad de la interfaz y aplicar lo que sirva. Es
> **insumo, no aprobación**; decide el PO. Contrastado con `main@ce26086a`. Lo de seguridad
> (hallazgos 11 y 12) es **propuesta para SecOps**, no decisión de diseño (CLAUDE.md §5).

**Problema local:** el sistema de diseño (`sistema-de-diseno-zascarr.md`) y sus pruebas cubren
color, tipografía, forma y componentes, pero no había una pasada sistemática contra una lista de
calidad de la interfaz completa (HTML, accesibilidad, rendimiento, seguridad del navegador, pruebas).

**Datos y medición de partida:** app local de `main` con Postgres efímero (una serie de 8 números, un
pendiente), 19 pantallas recorridas (todas las del menú, ficha de serie, ficha de número, editar
ficha, Estado y una 404), en escritorio y a 320 px (equivale a 1280 px con zoom del 400 %), y una
pasada por el código de las plantillas y de `web.css`.

## Referencias consultadas

| Referencia | Versión | Uso |
|---|---|---|
| thedaviddias/Front-End-Checklist | `e8d14d0` (2026-10-06) | Lista base: ~390 reglas con prioridad (crítica, alta, media, baja) en 11 áreas |
| Jamesiukalu/Frontend-Checklist | `ac54c9f` (2026-11-09) | Mismas áreas (`data/en/items/*.json`) y un auditor en línea |
| sapegin/frontend-pull-request-checklist | `ea24de8` (2024-10-30) | Lista de revisión de cada PR |
| Primer (GitHub), `primer.style/product/ui-patterns` y `/accessibility` | leído el 2026-11-22, sin versión en página | Formularios, estados vacíos, carga, avisos, guardar, servicio degradado |
| unicef/design-system, `design-guidelines.md` | `cd18efe` (2019-07-26) | Textos y etiquetas, avisos, formularios, botones desactivados, carga |
| AleruDivine/UX-Best-Practices | `2daaeb0` (2023-03-20) | Jerarquía, navegación, formularios, móvil |
| dev2me/buenas-practicas-frontend | `12e5003` (2016-08-13) | Índice de una tesis; sin reglas que no estén en las demás |
| eoasakura/Front-End-Checklist-ES | `2112875` (2018-02-15) | Traducción de una versión antigua de la lista base; solo vocabulario |
| web.dev, «Learn Responsive Design» (Interaction, UI patterns) | leído el 2026-11-22 | Puntero grueso, `hover`, tablas con desplazamiento propio, navegación |
| MDN, «Accessibility: HTML» | modificada el 2026-10-07 | Semántica, etiquetas, texto de enlace, tablas, `alt` |

**Supuestos de las referencias que NO valen en ZascArr:** web pública con buscadores (SEO, sitemap,
Open Graph, datos estructurados), CDN, gestión de consentimiento y Google Tag Manager, TypeScript y
empaquetado de JavaScript, PWA y modo sin conexión, vídeo y subtítulos, varios idiomas (`hreflang`).
ZascArr es privada, en la red local de una Raspberry Pi, sin telemetría, con HTMX y sin compilación de
JavaScript (ADR 0001 y 0011).

**Descartado:** el auditor en línea de Jamesiukalu (manda la URL y un registro a un servidor de
terceros, y ZascArr no es accesible desde fuera); las herramientas de investigación de AleruDivine
(Hotjar, Google Analytics…: chocan con «telemetría cero»); dev2me y eoasakura como fuente de reglas
(superados por la lista base vigente).

## Lo que ya cumple

Medido en las 19 pantallas o comprobado en el código:

- **HTML:** `<!doctype html>`, `charset` primero, `lang="es"`, `viewport` sin bloquear el zoom, un
  título distinto por pantalla, favicons en tres tamaños, 404 propia, scripts con `defer`, sin
  scripts ni hojas de terceros (SRI no aplica).
- **Estructura:** un `h1` y un `main` por pantalla, `nav` con nombre, ningún `id` repetido, todos los
  campos con etiqueta, todas las imágenes con `alt`, ningún botón ni enlace sin nombre.
- **Teclado:** «Saltar al contenido» funciona y lleva al `main`; foco visible de 3 px en `cyan-t`.
- **CSS:** tokens de color, texto, forma y espacio; temas claro y oscuro con `prefers-color-scheme`;
  `prefers-reduced-motion`, `prefers-contrast` y `forced-colors`; contraste comprobado en la CI;
  fuentes locales en `woff2` con `font-display: swap`.
- **Caché:** `/static` con `no-cache` y `ETag` (responde 304); portadas con `max-age` y `ETag`.
- **Estados y avisos:** regiones vivas (`aria-live`, `role="status"`), barras de lectura con
  `role="progressbar"` y nombre, indicadores de carga en las acciones lentas.
- **Reflujo:** sin desplazamiento horizontal a 320 px en 14 de 15 pantallas (la tabla de Estado se
  desplaza dentro de su caja, como recomienda web.dev).
- **Privacidad:** sin cookies de terceros, telemetría cero, cookie de sesión `HttpOnly` y
  `SameSite=Lax`.

## Hallazgos

Prioridad de la lista base: **C** crítica, **H** alta, **M** media, **L** baja.

| # | Pri. | Hallazgo (medido) | Regla y fuente | Propuesta | Resultado |
|---|---|---|---|---|---|
| 1 | C | **Ajustes se sale 54 px por la derecha a 320 px.** Dos causas: los `fieldset` miden como su contenido más ancho (`min-inline-size: min-content` por defecto) con selects largos, y las rutas de carpeta no se cortan. Probado en el navegador: con la corrección, 320 px justos | «Support content reflow at 400 % zoom»; sistema de diseño: «nada desborda en horizontal» | `fieldset { min-inline-size: 0 }`, `select { max-width: 100% }` y `overflow-wrap: anywhere` en las tarjetas de Ajustes (solo CSS) | Adoptar |
| 2 | C | **El estado vacío salta de `h1` a `h3`** en Por revisar, Pendientes por carpeta, Mejoras, Novedades y Sagas en orden: `ui.estado_vacio` pinta siempre `h3` | «Use logical heading hierarchy»; MDN | Parámetro de nivel en la macro, `h2` por defecto | Adoptar |
| 3 | H | **Los errores de campo no están ligados a su campo.** En «Editar la ficha» (y otros) el error es un `span.campo-error` sin `aria-invalid` ni `aria-describedby`, y el foco no va al primer error | «Validate forms accessibly»; Primer Forms (`aria-invalid` + `aria-describedby`, foco al primer error) | Macro de campo con error que ponga los dos atributos y lleve el foco al primero | Adaptar |
| 4 | H | **Un botón dice solo «Ver»** (Inicio, paso «No tienes tebeos por clasificar») | «Use descriptive link text»; MDN | «Ver Por revisar», o el destino en `sr` | Adoptar |
| 5 | M | **Botones desactivados sin explicación.** «Buscar» en Asociar fuente está desactivado hasta elegir una web y se activa con un `<script>` en línea (sin JavaScript no se activa nunca); «Aplicar lo seleccionado» se desactiva sin decir por qué | Primer («no desactives el envío»), UNICEF («evita los botones desactivados; si no, explica al lado») | Sin desactivar: el servidor comprueba y responde con un aviso. Se va el script en línea | Adaptar |
| 6 | M | **La rejilla de Biblioteca y el Escaparate piden todas las portadas a la vez** (sin `loading="lazy"`); con 200 series, 200 peticiones a la Pi al abrir | «Lazy load offscreen images»; web.dev | `loading="lazy"` salvo la primera fila (la macro ya admite `carga`) | Adoptar |
| 7 | M | **Sin compresión.** `web.css` pesa 176 KB (39 KB con gzip) y las páginas, de 13 a 63 KB. Con `no-cache` y `ETag` solo se descarga tras cada actualización | «Enable text-based compression» | Comprimir solo texto (HTML, CSS, JS, JSON), nunca las portadas. **Medir antes el coste de CPU en la Pi** | Adaptar, tras medir |
| 8 | L | **El sondeo sigue en pestañas ocultas:** cada pestaña pide `/ui/_tareas` cada 10 s y `/ui/_nav/estado` cada 30 s aunque no se vea | «Load non-critical code on interaction»; presupuesto de la Pi (CLAUDE.md §1) | **Descartado tras probarlo (2026-11-22):** con un filtro (`every 10s[document.visibilityState === 'visible']`), htmx 4.0.0 lee mal el intervalo y sondea sin pausa (611 peticiones en 3 s). Los navegadores ya ralentizan los temporizadores de las pestañas ocultas. Si se retoma, con una extensión o un `hx-trigger` probado en el navegador, nunca solo con pruebas de plantilla | Descartar |
| 9 | L | **38 `autofocus`.** La mayoría lleva el foco al aviso tras una acción (patrón deliberado de `ui.aviso` y `ui.region_viva`) | «Avoid autofocus on form fields» | Mantener el patrón; revisar los que caen en un campo al cargar | Construir sobre lo propio |
| 10 | L | **Un enlace a otra pestaña sin aviso ni `rel`** («aviso legal completo» en el asistente legal); los otros 15 sí lo llevan | «External link security»; MDN | `rel="noopener noreferrer"` y «(se abre en otra pestaña)» | Adoptar |
| 11 | H | **Ninguna cabecera de seguridad global:** ni `X-Frame-Options`/`frame-ancestors` (la app se puede incrustar en otra web y engañar un clic), ni `Referrer-Policy`, ni `Permissions-Policy`; `nosniff` solo en 5 respuestas. Una CSP estricta hoy chocaría con 2 scripts en línea, 7 `hx-on` y 2 `style=` | «Set an X-Frame-Options header», «Set a Referrer-Policy header», «Set X-Content-Type-Options», «Implement a content security policy» | **Para SecOps:** middleware con `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`, `Permissions-Policy` mínima y `X-Robots-Tag: noindex`; la CSP, en un segundo paso | Adaptar (SecOps) |
| 12 | H | **La cookie de sesión no lleva `Secure`** ni siquiera detrás de un proxy con HTTPS (`BASE_URL` en `https`) | «Set Secure, HttpOnly, and SameSite flags on session cookies» | **Para SecOps:** `Secure` cuando `BASE_URL` sea `https`. Toca `web/ajustes.py`, así que espera la pasada final de SecOps (CLAUDE.md §5.8) | Adaptar (SecOps) |
| 13 | H | **Las pruebas de accesibilidad son de CSS y de plantillas sueltas**, no de la página entera: nada habría detectado los hallazgos 2 y 4 | «Include accessibility testing»; sapegin («WCAG AA», «200 % zoom») | Una prueba que pinte cada pantalla (FakeSession) y la revise con `html.parser` de la stdlib: un `h1`, sin saltos de encabezado, `id` únicos, campos con etiqueta, controles con nombre y sin textos vagos. Sin dependencias nuevas | Construir sobre lo propio |

**Lista de revisión de cada PR (sapegin), adaptada:** ya se hace casi todo (pruebas, linter, capturas
y comprobación en el navegador, autorrevisión). Falta escribirla: se propone una plantilla de PR con
«Qué cambia / Decisiones anteriores que revisa / Cómo se comprobó (escritorio, 375 y 320 px, los dos
temas, teclado) / NOT RUN», el formato que ya siguen las PR de diseño.

## Lo que NO se propone

- SEO, CDN, PWA, service worker, vídeo y varios idiomas: no aplican (ver supuestos).
- Minificar el CSS con una herramienta: exige un paso de compilación (ADR 0001); la compresión del
  hallazgo 7 da casi todo el ahorro.
- Hoja de impresión: baja prioridad y sin caso de uso del coleccionista.
- Cambiar los `no-store` de las pantallas para la caché de ida y vuelta del navegador: son
  deliberados (datos vivos con HTMX).

## Aplicado (decisión del PO del 2026-11-22: hallazgos 1–10 y 13; el 7, solo tras medir en la Pi)

| # | Qué se hizo | Comprobado |
|---|---|---|
| 1 | `min-inline-size: 0` y `overflow-wrap: anywhere` en `.ajustes-card`; `max-width: 100%` en sus `select` | Ajustes a 320 px: 320 de ancho (antes 374) |
| 2 | `ui.estado_vacio(…, nivel=2)`: `h2` por defecto, `nivel=3` dentro de una sección con `h2` (colección, previa de saga); el título se ve igual con `--text-titulo-bloque` | Prueba de estructura; captura de Por revisar vacía |
| 3 | Macro `ui.invalido(errores, campo, orden)`: `aria-invalid`, `aria-describedby` al `span.campo-error` (con `id`) y `autofocus` en el primero con error. En Editar la ficha, Editar el número, Editar la saga y Añadir un número | En vivo: los cuatro formularios, con el foco en el primer error |
| 3b | **Fallo nuevo hallado al probarlo:** cualquier error de validación en Editar la ficha, Editar el número o Editar la saga daba **500** (tras el `rollback`, la plantilla leía atributos caducados fuera del contexto asíncrono). Se vuelve a leer después del `rollback` | Prueba con Postgres que falla sin el arreglo |
| 4 | «Ver» → «Ver Por revisar» | Prueba de estructura |
| 5 | «Buscar» de Asociar fuente sin `disabled` ni script en línea (el servidor ya respondía «Elige una web antes de buscar»); sin nada aplicable, la previa de datos lo dice y ofrece volver, sin botón desactivado | Pruebas de plantilla |
| 6 | `loading="lazy"` a partir de la fila 3 de la rejilla (12 portadas), de la 7.ª portada de «Sigue leyendo» y en el resto de filas del Escaparate, las sugerencias y el Inicio | Pruebas de plantilla |
| 7 | Medido en la Pi 5 (`ce26086a`, carga 0,2): `web.css` 176 KB → 39,5 KB con gzip 6 en 5,7 ms (nivel 1: 51,4 KB en 1,9 ms); `htmx.min.js` 36,7 → 13,1 KB en 1,5 ms. Decisión del PO: aplicar. `GZipMiddleware` de Starlette (sin dependencia nueva), nivel 6, mínimo 1 KB, sin recomprimir imágenes, fuentes, ZIP, PDF, EPUB ni `application/octet-stream`. `Vary` pasa a llevar `Accept-Encoding` (OPDS incluido) | `test_compresion_texto.py`: CSS comprimido y revalidable con 304, PNG sin tocar |
| 8 | **Descartado tras probarlo** (ver la tabla) | 611 peticiones en 3 s con el filtro |
| 9 | El radio de «Tu lectura» solo recibe el foco al repintarse tras guardar (HTMX), no al cargar la ficha de número | Prueba de plantilla |
| 10 | `rel="noopener noreferrer"` y «(se abre en otra pestaña)» en el enlace del asistente legal; una prueba recorre todas las plantillas | Prueba de plantilla |
| 13 | `tests/test_estructura_pantallas_pg.py`: pinta 18 pantallas contra Postgres y revisa su estructura con `html.parser` | Falla en `main` (4 saltos de encabezado y el «Ver») y pasa con los arreglos |
| PR | Plantilla `.github/pull_request_template.md` con la lista de revisión de sapegin adaptada (qué cambia, decisiones que revisa, cómo se comprobó, NOT RUN) | — |

**En la CI:** la prueba de estructura corre sola en el job «Pruebas con Postgres real» (ejecuta todo
fichero con `TEST_DATABASE_URL` y falla si alguno se salta). Las comprobaciones que solo ve un navegador
(reflujo a 320 px, foco visible, consola sin errores, el sondeo desbocado del hallazgo 8) exigirían
Playwright y Chromium en la CI: choca con CLAUDE.md §8 («ninguna dependencia nueva por testing») y
queda para una decisión aparte del PO (ADR).

## Casos de prueba propuestos

Una regresión por hallazgo adoptado: Ajustes sin desbordar (regla CSS), estado vacío con `h2`,
campo con error con `aria-invalid` y `aria-describedby`, ningún enlace ni botón con texto vago en el
Inicio, rejilla con `loading="lazy"` desde la segunda fila, el enlace del asistente legal con `rel`.
Para el 13, la prueba de estructura recorre todas las pantallas del menú.

## NOT RUN

Lector de pantalla real; tableta y móvil físicos; la Pi (rendimiento y CPU de la compresión);
pantallas con muchos datos (rejilla de 200 series, formularios con errores en todas las pantallas);
Primer: las subpáginas de accesibilidad con cifras (tamaño de objetivo, contraste) no se leyeron;
web.dev: los módulos de Tipografía, Accesibilidad y Temas no se leyeron (sí Interacción y Patrones).

**Caduca:** 2027-01-21 (~60 días).
