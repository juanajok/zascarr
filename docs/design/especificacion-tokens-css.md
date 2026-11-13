# Especificación — tokens CSS de tipografía, forma y espaciado (#689)

> Deuda 1 y 2 del sistema de diseño: la escala de texto no tenía nombre y los
> grosores de borde y los huecos seguían en literales. Esta historia los fija
> como tokens en `:root` de `src/zascarr/static/web.css`. **No se añaden tokens
> de color**: los colores ya estaban cerrados; `--radius-*` y `--shadow-*` no se
> tocan.

## 1. Inventario medido (antes)

Medido sobre `web.css` de `origin/main` antes de esta historia:

| Familia | Declaraciones | Valores distintos | Notas |
|---|---:|---:|---|
| `font-size` | **140** | **22** | incluye los `clamp()` de rótulos y la excepción móvil |
| grosores de `border`/`border-*` | **130** usos con 3px/2.5px/2px/1px | 4 | 3px ×48, 2.5px ×4, 2px ×58, 1px ×20 |
| huecos exactos en `margin`/`padding`/`gap` | **335** usos de 4/8/12/16/24/32 px | 6 | solo literales exactos; los `clamp()` no se tocan |

Valores de texto detectados: `.875rem` (90), `.9rem` (11), `1rem` (6), `1.05rem`
(4), `.95rem` (4), `1.15rem` (3), `.92rem` (3), `.88rem` (3), `1.25rem` (2),
`1.4rem`, `1.2rem`, `1.02rem`, `1.5rem`, `2rem`, `2.75rem`, `2.6rem`, `46cqw`,
`1em`, y los cuatro `clamp()` de titulares/nav más los tres de rótulos.

## 2. Tabla de tokens

### Tipografía

Los `clamp()` del sistema viven dentro del token; quien lo usa no repite el
tamaño. El tamaño de la ficha es el máximo del `clamp()`.

| Token | Valor | Uso |
|---|---|---|
| `--text-titulo-pagina` | `clamp(30px, 4.4vw, 48px)` | `h1` de pantalla (`.dashboard h1`, y equivalentes). |
| `--text-cifra` | `clamp(30px, 3.4vw, 42px)` | cifra de una métrica (`.metric-value`). |
| `--text-titulo-seccion` | `clamp(19px, 2.4vw, 26px)` | `h2` de sección (`.section-header h2`, `.seccion`). |
| `--text-marca` | `1.4rem` | nombre de la marca en la barra lateral. |
| `--text-numero-paso` | `1.25rem` | número del círculo de un paso. |
| `--text-titulo-bloque` | `1.05rem` | `h2` de bloque (`.audit-block h2` y similares). |
| `--text-cuerpo` | `1rem` | texto corrido y controles que usan el tamaño base. |
| `--text-titulo-frase` | `1.05rem` | título que es frase o ruta (`.step h3`, `.siguiente-paso h3`). |
| `--text-estado-resumen` | `1.15rem` | frase de estado general de `/estado`. |
| `--text-didascalia` | `.9rem` | didascalia (`.caption`), aviso legal y textos de lectura secundaria. |
| `--text-nav` | `.95rem` | entradas del menú lateral y variantes de navegación. |
| `--text-boton` | `.88rem` | etiqueta de botón. |
| `--text-secundario` | `.875rem` | metadatos, detalles y notas; el tamaño más usado. |
| `--text-chip` | `.875rem` | chip/insignia de estado (familia `body` fija). |
| `--text-etiqueta` | `.875rem` | rótulo girado (`.rotulo`) y cabecera de grupo del menú. |
| `--text-nav-movil` | `clamp(.75rem, 3.3vw, .875rem)` | **excepción declarada de U16** para que «Deseados» quepa a 320 px; no se toca. |

Tamaños heredados que **no son estilos del sistema** y se conservan para no
cambiar píxeles fuera de la tabla de redondeos: `--text-marca-movil:1.2rem`,
`--text-titulo-descubrir:1.5rem`, `--text-vista-recuento:2rem`,
`--text-hero-grande:2.75rem`, `--text-portada-marca:46cqw`,
`--text-portada-marca-respaldo:2.6rem`, `--text-code-inline:1em`.

### Forma

| Token | Valor | Uso |
|---|---|---|
| `--border-panel` | `3px` | viñetas, cabeceras, barra lateral, separadores principales. |
| `--border-control` | `2.5px` | botones, campos y paginación. |
| `--border-chip` | `2px` | chips, insignias, avisos, didascalias y puntos de estado. |
| `--border-line` | `1px` | separadores internos de listas/tablas. |

Los `outline` de foco, `border: 0`, `border: none` y los bordes decorativos de
4/9 px no son grosores del sistema y se dejan como estaban.

### Espaciado

| Token | Valor |
|---|---:|
| `--space-1` | `4px` |
| `--space-2` | `8px` |
| `--space-3` | `12px` |
| `--space-4` | `16px` |
| `--space-5` | `24px` |
| `--space-6` | `32px` |

Se sustituyen solo literales exactos en `margin`, `padding`, `gap`, `row-gap` y
`column-gap` (335 usos). Los valores intermedios (2/6/10/14/18/20/22/28/30 px),
los `clamp()` y los `calc()` no se tocan: redondear 2 px no es una mejora
declarable en esta historia.

## 3. Tabla de redondeos

| Antes | Después | Δ | Motivo |
|---|---|---:|---|
| `.92rem` | `.9rem` (`--text-didascalia`) | 0,32 px | valor casi duplicado de didascalia; `.92` solo aparecía en `.topnav` heredado y `.legal-checkbox`. |
| `1.02rem` | `1.05rem` (`--text-titulo-bloque`) | 0,48 px | `.discovery-card-title` estaba a medio camino entre bloque y frase. |

No hay redondeos de borde ni de espaciado: los tokens conservan exactamente el
valor original. `1.2rem`, `1.5rem`, `2rem`, `2.75rem`, `2.6rem`, `46cqw` y `1em`
se conservan mediante tokens heredados para no cambiar píxeles.

## 4. Plan de verificación

- `tests/test_web_css_tokens.py`: parseo real de `:root`; valores exactos;
  ninguna declaración `font-size` fuera de `:root` sin `var(--text-*)`; ningún
  `border`/`border-*` con grosor 3/2.5/2/1 px literal; excepción
  `--text-nav-movil` declarada; tokens de espaciado definidos y usados.
- `tests/test_web_css_contraste.py`: resuelve `var(--text-*)` contra los tokens
  y sigue comprobando el mínimo de 14 px (la excepción móvil sigue declarada con
  su motivo).
- `tests/test_web_componentes.py`: verde; no se toca ninguna clase anterior a V2.
- `scripts/comparar_tokens_css.py ANTES.css DESPUES.css`: resuelve los `var()` y
  comprueba declaración a declaración que solo cambian los dos redondeos de la
  tabla. Resultado esperado: `OK`.
- Navegador real (claro/oscuro, 1280/375) lo hará el Lead tras desplegar; aquí
  no hay navegador.

## 5. Riesgos

- **Valores visuales**: los dos redondeos son subpíxel; el resto conserva valor
  exacto. Una diferencia en el comparador se trata como fallo, no como ruido.
- **Tokens heredados**: los tamaños fuera del sistema quedan como tokens
  `--text-*` para no dejar literales, pero no deben usarse en pantallas nuevas.
- **Espaciado parcial**: no se redondean valores intermedios; hacerlo sería otro
  cambio visual, fuera de esta deuda.
- **Clases V2**: no se tocan plantillas, colores, sombras ni radios; los tests
  de compatibilidad siguen siendo la red.
