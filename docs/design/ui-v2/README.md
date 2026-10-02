# V2 — componentes CSS y macros Jinja

Historia **V2** de la Épica V. Piezas reutilizables con los nombres de la maqueta, sobre los tokens ya
comprobados de V1. **No migra ninguna pantalla** (cada una lo hará en su historia) y **no toca el menú
ni la navegación** (V3).

## Qué hay

| Pieza | CSS | Macro (`templates/_componentes.html`) |
|---|---|---|
| Botón | `.btn` (+ `.primary`, `.ghost`, `.sm`), `button[disabled]` | — (son clases) |
| Chip de estado | `.chip` (+ `.ok`, `.warn`, `.amber`, `.info`) | `chip(estado, texto)` |
| Tarjeta | `.card` (comparte regla con las viñetas existentes) | — |
| Grupo | `.group`, `.ghead` | `{% call grupo(titulo, recuento) %}…{% endcall %}` |
| Aviso | `.aviso` (+ tipos) y `.caption` para la nota | `aviso(tipo, texto)` o `{% call aviso(tipo) %}` |
| Estado vacío | `.empty-state` (ya existía) | `estado_vacio(titulo, texto, accion)` |
| Estado grande | `.hero-state` (+ matices) | — |
| Progreso | `progress.progress` (nativo) | `progreso(valor, maximo, etiqueta)` |
| Aviso temporal | `.toast` (se desvanece solo por CSS) | — |
| Región viva | — | `region_viva(id)` (`aria-live="polite"`) |

El estado → aspecto vive **una sola vez**, en `src/zascarr/web/componentes.py` (`ASPECTOS`, `TIPOS_AVISO`);
las plantillas no repiten ni clases de matiz ni iconos (una prueba lo comprueba). Un estado desconocido
**falla** en vez de pintarse neutro. Las macros se registran en `crear_templates()` y llegan a todas las
plantillas **sin tocar ningún router ni `TemplateResponse`**.

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

## Una colisión de nombres, encontrada por la prueba y acotada

Las macros son globales. `ajustes.py` ya pasa una variable `aviso` a `_ajustes_guardado.html` (el aviso de
contraseña justa de A11), que **tapa la macro `aviso` solo dentro de esa plantilla**. Renombrarla sería tocar
Ajustes, fuera del alcance de V2: queda como colisión **conocida y acotada** (la prueba falla si aparece una
nueva o si esta se resuelve sin actualizar la lista) y se renombra en **V10**, que es quien migra Ajustes.

## Verificación

- **Pruebas** (sin navegador): `tests/test_web_componentes.py` (94 casos: todas las variantes de cada macro,
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
- El desvanecimiento del `.toast` no se demuestra en capturas (el catálogo lo desactiva); se prueba que la
  animación existe y que «reducir movimiento» la apaga.
- El contraste lo cubre la prueba por reglas (heurística, ver V1) más la inspección del catálogo; un navegador,
  sin probar en la Pi.
