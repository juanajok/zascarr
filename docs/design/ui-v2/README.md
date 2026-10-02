# V2 — componentes CSS y macros Jinja

Historia **V2** de la Épica V. Piezas reutilizables con los nombres de la maqueta, sobre los tokens ya
comprobados de V1. **No migra ninguna pantalla** (cada una lo hará en su historia) y **no toca el menú
ni la navegación** (V3).

## Qué hay

| Pieza | CSS | Macro (`templates/_componentes.html`) |
|---|---|---|
| Botón | `.btn` (+ `.primary`, `.ghost`, `.sm`), `button[disabled]` | — (son clases) |
| Chip de estado | `.chip` (+ `.ok`, `.warn`, `.amber`, `.info`) | `ui.chip(estado, texto)` |
| Tarjeta | `.card` (comparte regla con las viñetas existentes) | — |
| Grupo | `.group`, `.ghead` | `{% call ui.grupo(titulo, recuento) %}…{% endcall %}` |
| Aviso | `.aviso` (+ tipos) y `.caption` para la nota | `ui.aviso(tipo, texto)` o `{% call ui.aviso(tipo) %}` |
| Estado vacío | `.empty-state` (ya existía) | `ui.estado_vacio(titulo, texto, accion)` |
| Estado grande | `.hero-state` (+ matices) | — |
| Progreso | `progress.progress` (nativo) | `ui.progreso(valor, maximo, etiqueta)` |
| Aviso temporal | `.toast` (se desvanece solo por CSS) | — |
| Región viva | — | `ui.region_viva(id)` (`aria-live="polite"`) |

El estado → aspecto vive **una sola vez**, en `src/zascarr/web/componentes.py` (`ASPECTOS`, `TIPOS_AVISO`);
las plantillas no repiten ni clases de matiz ni iconos (una prueba lo comprueba). Un estado desconocido
**falla** en vez de pintarse neutro. Las macros se registran en `crear_templates()` **bajo un único nombre,
`ui`** (`ui.chip(...)`, `ui.aviso(...)`…) y llegan a todas las plantillas **sin tocar ningún router ni
`TemplateResponse`**. Es lo único que V2 añade al entorno de Jinja; los ayudantes (`aspecto`, `tipo_aviso`)
son globales solo de la plantilla de macros.

## Decisiones (y por qué)

- **`.empty-state` es el componente de estado vacío; `.empty` sigue siendo el texto en cursiva de siempre.**
  La ficha pedía `.empty`, pero `.empty` ya se usa en 7 plantillas con otro significado, y `.empty-state` ya
  era la caja discontinua de la maqueta. Cambiar `.empty` rompería lo existente.
- **El icono acompaña al color** (`✓ ! ? i`, `aria-hidden`): el estado no depende solo del matiz.
- **`aviso`: solo `warn` es `role="alert"`**; el resto, `role="status"` (cortés). Lo grave interrumpe; lo demás
  se anuncia sin robar el foco.
- **Progreso con `<progress>` nativo** en vez de `div`+`i` con ancho en línea: rol, valor y nombre accesibles
  sin JavaScript ni ARIA a mano.
- **`grupo` usa `role="group"`, no `<section aria-label>`**: un landmark por cada grupo sería ruido para un
  lector de pantalla.
- **`.toast` no es `position: fixed`**: va en el flujo, se desvanece por CSS y con «reducir movimiento» la
  animación se desactiva y el aviso se queda (lo seguro).
- **Tokens nuevos** (`--ok-bg`, `--warn-bg`, `--amber-bg`, `--info-bg`, valores de la maqueta), con valor propio
  en oscuro y pares de texto comprobados por `tests/test_web_css_contraste.py`.

## Un fallo que la primera versión de V2 habría metido en producción (corregido en la revisión)

La primera versión registraba cada macro como **global suelta** (`chip`, `aviso`, `grupo`…). Jinja incorpora
los globales al contexto de **todas** las plantillas, y `_ajustes_guardado.html` hace `{% if aviso %}` sobre
una variable que el router solo pasa a veces. Con la macro global `aviso`, **ese `if` era verdadero en cada
guardado de Ajustes que no pasaba la variable y pintaba `<Macro 'aviso'>` como texto de ayuda** (reproducido
con el entorno de esa versión). La prueba de colisiones de entonces solo comparaba *nombres* y lo daba por
«colisión conocida e inocua»: no lo era, y las capturas de páginas no pasan por esos fragmentos.

**Arreglo:** un único espacio de nombres, `ui`. Los nombres genéricos dejan de existir como globales (los
usan las plantillas como variables libres, como antes) y no hace falta tocar Ajustes. **Regresión:**
`TestPlantillasExistentesNoCambian` renderiza `_ajustes_guardado.html` con guardado correcto sin clave
`aviso`, `aviso=None`, aviso real de contraseña corta y error —y `_ajustes_prueba.html`— y compara el HTML
**con el del entorno de antes de V2**, exigiendo además que no aparezca ninguna representación de macro;
`test_v2_solo_anade_un_nombre_al_entorno` fija que `ui` es lo único nuevo. Con la versión anterior
reintroducida, **fallan 10 casos**.

## Verificación

- **Pruebas** (sin navegador): `tests/test_web_componentes.py` (109 casos: todas las variantes de cada macro,
  clase/texto/ARIA/escape, estado desconocido, registro en los 11 routers, colisiones, vocabulario único,
  CSS de cada variante, `prefers-reduced-motion`) y `tests/test_web_css_contraste.py` (112), que ahora
  cubre los componentes nuevos en claro y oscuro. **Compatibilidad:** ninguna de las 143 clases anteriores
  a V2 desaparece (se retiran en V14, no antes).
- **Navegador real** (Chrome 154, entorno aislado de V0 reconstruido desde esta rama): el catálogo
  (`catalogo.html`, generado con las macros y el CSS reales por `catalogo.py`) en claro/oscuro y
  escritorio/móvil — `catalogo--*.png`; y **no regresión**: las 30 capturas de las pantallas existentes con el
  CSS anterior frente al nuevo, en el mismo estado de datos: **25 idénticas píxel a píxel; las otras 5 difieren
  solo en una hora (la «Última comprobación» de `/estado`, tres veces, y la hora de aceptación del aviso
  legal, dos)**. También se comprobó en la imagen reconstruida que las macros están registradas y la
  plantilla va empaquetada.

## Límites
- Ninguna pantalla usa aún los componentes: lo verificado es el catálogo y la no regresión, no su uso real.
- La no regresión de las **páginas** (capturas) no cubre los **fragmentos** HTMX (guardados de Ajustes, filas,
  resultados de búsqueda): ahí la garantía es la comparación de HTML contra el entorno de antes de V2 que
  hace `TestPlantillasExistentesNoCambian`, hoy solo para `_ajustes_guardado.html` y `_ajustes_prueba.html`
  (las que consultan variables con nombre de macro); el resto no usa esos nombres.
- El desvanecimiento del `.toast` no se demuestra en capturas (el catálogo lo desactiva); se prueba que la
  animación existe y que «reducir movimiento» la apaga.
- El contraste lo cubre la prueba por reglas (heurística, ver V1) más la inspección del catálogo; un navegador,
  sin probar en la Pi.
