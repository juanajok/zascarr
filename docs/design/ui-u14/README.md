# Evidencia de U14 (#201): Descubrir, progreso y resultados limpios, en navegador real

Mediciones de la rama `claude/u14-descubrir`, 2026-10-16. Ficha: `docs/design/benchmark-U14-descubrir-estados.md` (PR #216).

| Dato | Valor |
|---|---|
| Navegador | Google Chrome 154.0.8037.92 headless por CDP; escritorio 1280×900 y móvil 375×812 (**emulación de viewport**), claro y oscuro |
| Entorno | ensayo aislado `docs/design/ui-baseline/ensayo.sh` (Postgres real), rehecho desde cero para esta ejecución |
| Herramientas | [`fragmentos.py`](fragmentos.py) (genera la página y los fragmentos con la ruta real) y [`capturar_u14.py`](capturar_u14.py) |
| Datos en bruto | [`datos.json`](datos.json) |

## Qué es real y qué es simulado (importa)

- **Real:** hoja de estilos, htmx, plantilla base, el navegador y los **clics y teclas por el protocolo**; y, del ensayo, la
  página con las fuentes apagadas (captura `0-ensayo-fuentes-apagadas.png`).
- **Simulado:** el ensayo tiene las cuatro fuentes **apagadas a propósito** y su red no está aislada, así que **no las
  encendí** (serían consultas reales a sitios externos; Tebeosfera es una asociación sin ánimo de lucro). La página «con las
  cuatro fuentes» y los resultados los **genera la ruta real** (`fragmentos.py`, con `DiscoveryService.search_detallada`
  sustituido por una `Busqueda` ya calculada) y se sirven al navegador con `Fetch.fulfillRequest`. La **espera** de 0,5–1,5 s
  también es simulada (el servidor responde al instante; el navegador la retiene).
- Por tanto esto acredita la **presentación y el comportamiento del navegador**, **no** el tiempo ni el contenido de las fuentes.

## Resultados

| Criterio de la ficha | Medido | Resultado |
|---|---|---|
| 1. Progreso a los 400 ms | Con la respuesta retenida 0,5 y 1,5 s, el indicador pasó a visible **392–417 ms** después de empezar la petición (3 mediciones) y desaparece al terminar | PASS |
| 1. Sin parpadeo | Con una respuesta de 12–16 ms el indicador **nunca llegó a verse** (muestreo cada 20 ms) | PASS |
| 1. Fuentes nombradas | «Buscando en Comic Vine, AniList, Tebeosfera y GCD…», solo las encendidas; con el ensayo real (todo apagado), no hay indicador y la página lo dice | PASS |
| 2. Una sola región viva, fuera del destino | 1 `aria-live` en la página, **antes y después** de buscar; 0 dentro de `#resultados-descubrir`; la respuesta cambia su **contenido** con `hx-swap-oob="innerHTML"` (ver «Persistencia de la región viva») | PASS (estructura); verbalización: ver abajo |
| 2. Sin duplicar a la vista | La región está **oculta a la vista** (`sr`: ~1×1 px) y el recuento visible es aparte (`aria-hidden`) | PASS |
| 3. Texto limpio | `<p>…<a>Bruguera</a> &amp; Filemón…<script>` → «Mortadelo Bruguera & Filemón, agentes de la T.I.A.», sin `<`/`>` | PASS |
| 4. Fuente legible | «Comic Vine» (no `comic_vine`/`COMIC_VINE`) | PASS |
| 5. Select del sistema | Oscuro: fondo `rgb(19,19,22)`, texto `rgb(240,237,228)`, borde 2 px, **42 px** de alto; claro: fondo `rgb(246,243,236)`. Antes: el control nativo gris | PASS (el contraste lo comprueba además `test_web_css_contraste`) |
| 6. Enlace | Nombre en el **árbol de accesibilidad de Chromium**: «Ver la ficha de «Mortadelo y Filemón» en Comic Vine (se abre en otra pestaña)» | PASS |
| 7. Errores por fuente | Una caída: «No respondió AniList. Los resultados de Comic Vine, Tebeosfera y GCD sí se han consultado.»; todas: «No respondió ninguna fuente: …» **sin** «Sin coincidencias»; sin clave: «…añade su clave en Ajustes» | PASS |
| Sin scroll horizontal a 375 px | `scrollWidth` = `clientWidth` | PASS |

![lenta](1-lenta-escritorio-claro.png) ![móvil oscuro](4-movil-oscuro.png)

## Lo que NO está acreditado

- **Otros lectores (NVDA, VoiceOver, TalkBack) y otros navegadores (Firefox, Safari): NOT RUN.** El lector real que sí se
  probó es Orca (ver «Persistencia de la región viva»); no se generaliza a otros.
- **Fuentes reales y tiempos reales:** la espera de 15–20 s de la auditoría no se ha reproducido. **No hay una
  duración máxima conocida de una búsqueda:** 30 s es el tope de **cada petición**; Comic Vine y AniList reintentan hasta 3
  veces (durmiendo `Retry-After` o 2·2ⁿ s) y Tebeosfera encadena hasta 4 peticiones, así que el total por fuente no está
  acotado por 30 s ni se ha medido.
- Firefox y Safari (iOS); un móvil real; la Pi: **NOT RUN**.
- Hay un hueco vacío bajo el buscador (el indicador oculto conserva su línea para que el resultado no salte al aparecer): es
  una decisión de maquetación, no un error, pero se ve.

## Persistencia de la región viva (corrección tras la revisión de #217)

**Hallazgo del revisor, confirmado leyendo el código de htmx vendorizado (4.0.0, `htmx.min.js`, función de intercambio
fuera de banda):** `hx-swap-oob="true"` se resuelve como `outerHTML`, es decir, **sustituye el propio elemento**. La versión
anterior de la respuesta devolvía `<div id="descubrir-estado" class="sr" aria-live… hx-swap-oob="true">`: el `id` se conservaba,
pero el nodo no. **Corrección:** la respuesta devuelve `<div id="descubrir-estado" hx-swap-oob="innerHTML">texto</div>`; htmx
descarta esa envoltura y mete solo su contenido en el nodo que ya está en la página. Los atributos (`aria-live`, `aria-atomic`,
`class="sr"`) viven **solo** en la página.

| Qué | Cómo se midió | Resultado |
|---|---|---|
| El nodo es el mismo | Chrome 154 (CDP), cuatro búsquedas seguidas en la misma página; se guarda la referencia del nodo (`window.__reg`) y tras cada una se compara `===`; un `MutationObserver` registra qué ve la región. Datos: `datos.json` → `persistencia_de_la_region` | **PASS:** `es_el_mismo_nodo: true` las 4 veces, un solo `#descubrir-estado`, `aria-live`/`aria-atomic`/`class` intactos, sin `hx-swap-oob` residual. Las mutaciones son un cambio de contenido (`childList`) más dos cambios de `class` (las clases transitorias de htmx) |
| Orca anuncia cada actualización | **Orca 50.2** (Wayland, AT-SPI 2.60.4) + Google Chrome 154 con ventana, configuración de Orca aislada. Cuatro búsquedas seguidas con fuentes **simuladas**. Lo anotado es lo que Orca mandó al sintetizador (`SPEECH OUTPUT`). Bruto: [`orca-habla.json`](orca-habla.json); herramienta: [`orca_u14.py`](orca_u14.py) | **PASS** en esta combinación: con resultados y una caída → «2 resultados. No respondió AniList. Los resultados de Comic Vine, Tebeosfera y GCD sí se han consultado.»; sin coincidencias → «Ningún resultado.»; todas fallan → «No respondió ninguna fuente: Comic Vine, AniList, Tebeosfera y GCD. Inténtalo de nuevo en un momento.»; y una cuarta búsqueda, igual que la primera, **también** se anuncia. **Una sola frase por búsqueda**; Orca no leyó la lista de resultados |

**Control, para no atribuir a la corrección lo que no es suyo** ([`orca-habla-control-outerhtml.json`](orca-habla-control-outerhtml.json)):
con la versión ANTERIOR (nodo sustituido, `mismo_nodo: false`) Orca 50.2 + Chrome 154 **también** anunció las cuatro
búsquedas. Es decir: en esta combinación el defecto no se oía. La corrección no se justifica por un fallo observado aquí sino
por el contrato: una región viva debe existir antes de que cambie su contenido, y otras combinaciones de navegador y lector
pueden no anunciar un nodo que aparece ya relleno. Lo que se acredita es que **con el mecanismo correcto el anuncio funciona**,
no que el anterior fallara.

**Alcance:** las fuentes están simuladas, así que esto acredita **cómo se anuncia una actualización de la región**, no tiempos
ni contenido de las fuentes. El criterio 2 queda **acreditado para Orca + Chrome en Linux**; para NVDA, VoiceOver, TalkBack,
Firefox y Safari, **NOT RUN**.
