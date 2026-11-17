# Auditoría UI/UX — pasada #854 (2026-11-15)

> **Alcance:** pantallas nuevas de la épica SCR y ficha/Ajustes/Estado, contra `docs/design/sistema-de-diseno-zascarr.md` y CLAUDE.md §6.
> **Base:** `origin/main` `3ee54837` (el `main` local está 213 commits por detrás; se leyó con `git show origin/main:…`).
> **Método:** lectura de plantillas, CSS, helpers, rutas y pruebas de UI (`test_web_css_*`, `test_web_arcos*`, `test_web_estado_cortesia`);
> **sin navegador ni capturas** (no hay servidor de esta base en el entorno), así que layout y móvil se verifican a mano en el Corte 1.
> **Sin código ni commits.** **Severidad:** **A** bloquea/engaña de forma medible; **M** accesibilidad, jerarquía o texto incorrecto; **B** pulido.

## Lo que ya cumple (no tocar)

Contraste y texto ≥14 px (`tests/test_web_css_contraste.py:485`), un solo `.primary` en Importar (`test_web_arcos_guia.py:48-61`),
`rel="noopener noreferrer"` y «se abre en otra pestaña» en enlaces externos (`arcos.html:39`, `arco.html:21`), aviso CC-BY-SA del listado
(`arcos.html:22-24`), sin hotlinking, atribución Fandom/relleno fuera del `<details>` (`series_detail.html:69-75`), estado de guardado con `role="status"` (`_ajustes_guardado.html:5`) y foco visible global.

## Hallazgos por pantalla

### Sagas en orden (`web/arcos.py`, `arcos.html`)

- **A — El feed de Herald bloquea el GET de la página.** `web/arcos.py:249-258` hace `"herald_items": await _novedades_de_herald()` en el mismo handler y `_novedades_de_herald` (`:117-132`) descarga el feed con su cortesía (3,5 s; hasta 30 s de `espera_max_s`): la primera carga no pinta hasta que termina la red (deuda en `deudas-menores-2026-11-14.md:41`). → diseño perezoso de §Herald.
- **M — Tres acciones planas y estado vacío sin salida.** `arcos.html:8` pone «Nueva saga», «Buscar en fuentes» e «Importar una guía» como tres `btn ghost` (la tercera además `sm`), y `:9-10` pinta `ui.estado_vacio` sin acción. → `<nav class="arcos-acciones" aria-label="Acciones de sagas">` con los tres del mismo tamaño; en vacío, `ui.estado_vacio(…, ("Nueva saga", "/ui/arcos/nueva"))` como único primary y las otras dos `btn ghost`.
- **M — Las novedades usan la fila de una saga.** `arcos.html:36-43` reutiliza `arcos-lista`/`arco-fila` (mismo borde y fondo que las sagas locales): una noticia externa parece una saga. → `.novedades-lista` propia (separadores finos, sin tarjeta de saga) y mantener el caption `:44`.
- **B — CC-BY-SA solo de Fandom.** `arcos.html:22-24`: las sagas importadas de guías no mencionan su fuente en el listado (el detalle sí, `arco.html:20-22`). → línea discreta «Las guías enlazan su fuente original» o nota única si `pagina.hay_guia`.

### Importar una guía (`importar_guia.html`, `web/arcos.py:170-246`)

- **M — El error general no recibe el foco.** `importar_guia.html:7` usa `ui.aviso("warn", errores.general)` sin `foco=true` (el resto de formularios sí: `arco.html:6`). → `foco=true`, `aria-invalid="true"` y `aria-describedby` en el input de URL.
- **M — Puede tardar y el formulario no lo demuestra.** `importar_guia.html:12-28` es POST de página completa que puede esperar cortesía/robots (hasta 10 s) sin indicador ni botón deshabilitado; `:24` pide «no repitas» pero nada lo impide. → formulario htmx: `hx-post="/ui/arcos/importar-guia" hx-target="#resultado-importar" hx-swap="innerHTML" hx-disabled-elt="button[type=submit]" hx-indicator="#importar-espera"`; éxito con `HX-Redirect: /ui/arcos/{id}?…`, fallo con el parcial; `<div id="resultado-importar" aria-live="polite">` y `<span id="importar-espera" class="htmx-indicator">Leyendo la guía…</span>`.
- **M — URL larga desborda a 320 px.** `importar_guia.html:23` mete URLs en `<code>` y la única regla `code` es `.ajustes-hint code` (`web.css:1179`), así que un ejemplo largo puede desbordar. → `.edicion-form code { overflow-wrap: anywhere; }`.
- **B — Jerga en la ayuda.** `:24` «cortesía y robots.txt». → «La web puede pedir esperar; no repitas la petición.»
- **B — Fuente apagada con formulario activo.** `:8-11` avisa y enlaza Ajustes, pero el submit sigue y devuelve otro error. → ocultar el formulario si `fuente_apagada` y dejar aviso + enlace.

### Ficha de serie (`series_detail.html`, `web/atribucion.py`)

- **M — Atribución de relleno apilada y repetida.** `series_detail.html:70-75` pinta un `.caption` por fuente (hasta tres), todos «Parte de los datos de esta ficha viene de…», más el de Fandom `:69`; el sistema pide no apilar avisos iguales. → una sola caja con lista (una línea por fuente y licencia) desde `atribucion_de_relleno`, fuera del `<details>` y con los mismos `rel`.
- **M — El `<details>` «Fuentes y atribución» no contiene la atribución.** `:64-67` solo mete `legal_disclaimer("metadata")` mientras los avisos reales están fuera: el resumen promete lo que no hay. → renombrar a «Aviso legal de las fuentes» y meter dentro la nota genérica + `/legal`, o quitar el desplegable y dejar una línea legal.
- **B — Cifras sin `tabular-nums`.** Año del título `:15` y totales `:40-47`: el sistema pide cifras tabulares cuando se comparan. → `font-variant-numeric: tabular-nums` en `.serie-meta`/contadores de la ficha, con token.

### Ajustes (`ajustes.html`)

- **M — Texto obsoleto de GCD.** `:76` dice «GCD, por ahora, solo sirve para buscar series en Descubrir; no completa las que ya tienes»; SCR7 ya rellena huecos por ID. → «GCD, Metron y Open Library también rellenan huecos vacíos de series ya catalogadas; apagarlos deja de consultarlos.»
- **M — La ayuda de Metron atribuye a Open Library campos que no rellena.** `:121` dice «(año, fin, sinopsis)» para ambos; Open Library no escribe `end_year` (spec SCR7 §1). → «Metron: año, fin y sinopsis; Open Library: sinopsis y año de obra/tomo».
- **M — Guías y RSS dentro de «Fuentes de metadatos».** `:13-86` mezcla 7 fuentes de metadatos con Reading Orders, Continuity Guide y Herald. → en el mismo `<form>` (sin cambiar ruta ni defaults), dos subgrupos con `<h3>`/`role="group"`: «Metadatos» y «Guías y novedades».
- **B — Aviso HTTP del foro solo tras guardar.** `:249-251` pinta el aviso si la URL **guardada** es `http`; una URL nueva `http://` no avisa hasta guardar. → `hx-get="/ui/ajustes/foro/aviso" hx-trigger="input changed delay:500ms" hx-include="closest form" hx-target="#aviso-foro"` o nota estática junto al campo.
- **B — Placeholder largo de contraseña.** `:255-257` «ya configurada — deja en blanco…» se recorta a 320 px. → «ya configurada (vacío = no cambiar)».
- **B — Foro sin «Probar conexión».** Las demás integraciones lo tienen; la validación es el script de SCR4 §5. → decisión de producto, no bug; si se añade, reutilizar el patrón.

### Estado / cortesía (`estado.html`, `services/cortesia_estado.py`)

- **M — El motivo del bloqueo se calcula y no se pinta.** `cortesia_estado.py:144` devuelve `motivo_bloqueo` (`429`, `flood`, `maxlag`) y `estado.html:80-89` solo muestra «Bloqueada temporalmente (~7 s)». → mapa a llano (`429`→«La web nos pidió esperar», `flood`→«El foro pidió esperar», `maxlag`→«La wiki pidió bajar el ritmo») y `<div class="muted">{{ f.motivo_bloqueo }}</div>` bajo el estado; prueba de que no sale el código.
- **B — «304 · Sin cambios» sin regresión.** `RESULTADOS["304"]="Sin cambios"` existe (`cortesia_estado.py:42`) y M-5 lo registra, pero `test_web_estado_cortesia.py:101-140` no lo comprueba: puede volver a «—». → prueba con un intento `304` que espere «Sin cambios hace ~X s» en `/estado`.

### Transversal

- **M — Varios `foco=true` en la misma página.** `arco.html:6,8,12,14` generan varios `autofocus` (guardado, importación y pedido); solo uno es válido. → una prioridad explícita (pedido > importación > guardado) con `foco=true` solo en el más reciente; prueba que cuenta `autofocus`.
- **M — Nombres accesibles repetidos por fila.** `arco.html:77-85` repite «Subir una posición», «Bajar una posición» y «Quitar de la saga» sin serie/número: un lector no distingue filas. → `aria-label`/`<span class="sr">` con «Subir Batman #1 una posición», etc.; prueba de nombres únicos.
- **B — `titulo-frase` fijo en el h1 de la saga.** `arco.html:17` lo aplica siempre; el sistema lo reserva a >3 palabras o rutas, y los h1 de pantalla son rótulos Anton. → condicionarlo como en el resto de fichas.
- **B — Paginación con flechas de texto.** `arcos.html:26-29` usa `←`/`→`; el sistema pide SVG de `web/iconos.py` en controles nuevos y no hay flechas en el diccionario. → añadir `arrow_left`/`arrow_right` (Lucide) o dejar «Anteriores/Siguientes» sin glifo.
- **Sin hallazgos:** contraste, foco visible, `prefers-contrast`/`forced-colors`, objetivos de 40 px y tokens de texto están cubiertos por `test_web_css_*`; los avisos usan glifos permitidos por el sistema (`✓ ! ? i`, `_componentes.html:24-27`).

## Diseño exacto de la carga perezosa de Herald

1. **Ruta/parcial.** `GET /ui/arcos/novedades-herald` en `web/arcos.py`, `response_class=HTMLResponse` y sin `db`; llama a `_novedades_de_herald(espera_max_s=10)` (parámetro nuevo; el cliente ya lo acepta, `comicbook_herald.py:184-197`), responde `_novedades_herald.html` y añade `Cache-Control: no-store`. El feed sigue en `http_cache` (TTL 6 h): la segunda visita es caché caliente (0 red). Un fallo de red/robots/fuente apagada devuelve **200 con cuerpo vacío**, nunca 500.
2. **Marcado en `arcos.html`** (sustituye al bloque `{% if herald_items %}` `:33-46`; `arcos()` deja de pasar `herald_items`):
```html
<section id="novedades-herald" class="novedades-herald" aria-label="Novedades de Comic Book Herald"
         hx-get="/ui/arcos/novedades-herald" hx-trigger="revealed once"
         hx-target="#novedades-herald-contenido" hx-swap="innerHTML"
         hx-indicator="#novedades-herald-cargando">
  <div id="novedades-herald-contenido" aria-live="polite">
    <div id="novedades-herald-cargando" class="htmx-indicator">
      <p class="caption">Cargando novedades…</p>
      <div class="novedades-esqueleto" aria-hidden="true">
        <span class="esqueleto-fila"></span><span class="esqueleto-fila"></span><span class="esqueleto-fila"></span>
      </div>
    </div>
  </div>
</section>
```
3. **Por qué así.** `revealed` es core de htmx 4.0.0 (vendorizado; `revealed`/`intersect` están en `static/vendor/htmx.min.js`), `once` evita repetir y el `<div>` con `aria-live` es estable: anuncia la lista y conserva el foco.
4. **Parcial `_novedades_herald.html`.** Si `herald_items` está vacío no emite nada (respuesta vacía ⇒ `:empty` oculta la sección). Si hay: `<h2 id="herald-titulo" class="titulo-frase">Novedades de Comic Book Herald</h2>`, `<ul class="novedades-lista" aria-labelledby="herald-titulo">` con los ítems actuales (`target="_blank" rel="noopener noreferrer"`, fecha `dm/Y`, `sr` de pestaña) y el `<p class="caption">` de `:44`.
5. **CSS sin JS.** `.novedades-esqueleto { min-height: calc(5 * 2.75rem + 4 * var(--space-2)); }` reserva la altura **máxima** (`novedades()` ya devuelve ≤5) para que la lista no haga crecer la página; `.esqueleto-fila { min-height: 2.75rem; border: var(--border-panel) solid var(--ink-faint); border-radius: var(--radius-panel); background: var(--paper-2); }`. Si llegan menos de 5, solo se acorta por debajo de la sección (empuja el pie, no lo que se lee); sin feed, `#novedades-herald:has(#novedades-herald-contenido:empty) { display: none; }` (el proyecto ya usa `:has`, `web.css:2046`) ⇒ **no pinta nada**. Sin `animation` (reduce-motion) y con las tramas nuevas apagadas en el bloque `prefers-contrast: more, forced-colors: active` que exige `test_web_css_*`.
6. **Tope y fallo.** El feed sigue topado por el servicio (`MAX_CUERPO=1 MiB`, `comicbook_herald.py:67,265-268`) y por el tope general de `peticiones.py` (RES-3); el parcial son ≤5 títulos y no necesita tope propio. Si el endpoint falla, el esqueleto queda hasta el 200 vacío, sin mensaje de error (coherente con «sin feed ⇒ no pinta nada»), con el log `comicbook_herald.ui_sin_novedades`.

## Pruebas a añadir o ajustar

- `test_web_arcos.py`: `test_la_pagina_de_sagas_no_pide_el_feed` (parchea `_novedades_de_herald` con un doble que fallaría; `GET /ui/arcos` 200), `test_el_marcado_de_novedades_es_perezoso` (`hx-get`, `hx-trigger="revealed once"`, `aria-live`, esqueleto), `test_parcial_con_items`, `test_parcial_vacio_no_pinta_nada`, `test_parcial_fuente_apagada_cero_red`, `test_parcial_cache_caliente`; mover/ajustar `test_la_lista_muestra_las_novedades…` y `test_sin_novedades…` (`:361-400`).
- `test_web_estado_cortesia.py`: `test_304_se_dice_sin_cambios`, `test_bloqueo_muestra_su_motivo_en_llano` (429/flood/maxlag; nunca el código).
- `test_web_arcos_guia.py`/`test_web_arcos.py`: `test_error_de_importar_lleva_foco`, `test_importar_guia_usa_htmx_y_deshabilita_el_boton` (si se adopta I-2).
- `test_web_ajustes.py`/`test_web_ajustes_fuentes_nuevas.py`: `test_ayuda_gcd_ya_no_dice_solo_descubrir`, `test_ayuda_metron_y_ol_no_se_mezclan`, `test_fuentes_agrupadas_metadatos_y_guias`, `test_aviso_foro_http`.
- `test_web_series.py`/`test_web_atribucion_relleno`: `test_atribucion_de_relleno_es_una_sola_caja`, `test_enlaces_de_atribucion_con_rel`.
- `test_web_css_sistema_diseno.py`/`test_web_css_contraste.py`: `.novedades-lista`, `.novedades-esqueleto`, `.esqueleto-fila` con tokens; `.edicion-form code` con `overflow-wrap`; `:has` de la sección vacía; nada de colores literales.
- `test_revision_ux_2026_11.py` (patrón): `test_arcos_estado_vacio_tiene_accion`, `test_un_solo_autofocus` en detalle de saga, nombres accesibles únicos de los controles de fila.

## Cortes para el builder

| Corte | Contenido | Salida |
|---|---|---|
| **1 — Arreglos baratos** | Textos de Ajustes (A-1/A-2/A-3), foco/errores y espera de Importar (I-1/I-2/I-4), `code` (I-3), una caja de atribución y details de ficha (F-1/F-2/F-3), motivo de bloqueo y 304 (E-1/E-2), `foco` único y nombres accesibles de saga (T-1/T-2), empty state/nav de Sagas (S-2), CSS de noticias (S-3) y pruebas | 1–1,5 d |
| **2 — Herald perezoso** | Ruta/parcial, marcado con `revealed once`, esqueleto CSS sin desplazamiento, `:has` vacío, `no-store`, `espera_max_s=10`, ajuste de pruebas Herald y nuevas de caché/fallo | 0,5–1 d |

## Riesgos y límites

- Sin navegador en esta auditoría: el «sin layout shift» se valida con las pruebas de marcado/CSS y comprobación manual a 320/390/1280 px en el Corte 2; el esqueleto reserva 5 filas y aun así puede faltar si un título ocupa tres líneas a 320 px.
- `revealed` está en htmx 4.0.0 vendorizado; si una actualización lo retirara, el fallback es `hx-trigger="load"` (sigue sin bloquear la página, pero no espera al viewport) — anotarlo en el commit.
- La caché caliente depende de `http_cache` (6 h): la primera visita tras reiniciar sigue pagando la red, pero **fuera** del GET de Sagas.
- Convertir Importar a htmx toca `web/arcos.py`; el resto son plantillas/CSS y `services/cortesia_estado.py` (sin `web/ajustes.py` ni seguridad), así que §5.8 no aplica salvo que se toque la tarjeta Foro en servidor.
