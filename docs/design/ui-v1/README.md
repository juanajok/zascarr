# V1 — antes y después (tokens, contraste y tamaños)

Evidencia de la historia **V1** de la Épica V. Mismo entorno aislado y mismas herramientas que la línea
base de V0 (`docs/design/ui-baseline/`: `ensayo.sh` + `capturar.py`), sobre la rama de V1: Chrome 154
*headless*, escritorio 1280×800 y móvil 390×844, 100 % de zoom, datos sintéticos. «Antes» = las capturas de
`ui-baseline/` (commit `ab49c76`); «después» = `despues--*.png` de esta carpeta.

## Contraste calculado (WCAG 2.x), antes y después

| Par | Claro antes | Claro después | Oscuro antes | Oscuro después |
|---|---:|---:|---:|---:|
| Texto atenuado (`--ink-faint`) sobre `--paper` | 3.05 | 5.37 | 4.47 | 6.66 |
| Texto atenuado (`--ink-faint`) sobre `--paper-2` | 2.82 | 4.96 | 4.14 | 6.16 |
| Botón «reintentar» (cyan → `--cyan-t`) sobre `--paper` | 2.84 | 5.39 | 7.97 | 9.37 |
| Verde como texto (ok → `--ok-t`) sobre `--paper-2` | 3.54 | 5.40 | 7.42 | 8.94 |
| Rojo como texto (warn → `--warn-t`) sobre `--paper-2` | 4.53 | 5.57 | 5.93 | 7.21 |
| Blanco sobre verde sólido (insignia «en tu biblioteca») | 4.25 | 6.48 | 2.31 | 8.01 |
| Blanco sobre rojo sólido (insignia «falló») | 5.44 | 6.69 | 2.89 | 7.53 |
| Texto del botón amarillo («Guardar»…) | 10.87 | 10.87 | 1.23 | 12.39 |
| Anillo de foco (cyan → `--cyan-t`) sobre `--paper` | 2.84 | 5.39 | 7.97 | 9.37 |

Mínimo exigido: **4,5:1** para texto y **3:1** para foco, bordes e iconos. Se calcula con la misma función que
usa la prueba (`tests/test_web_css_contraste.py`).

## Lo que la medición destapó y la épica no decía

- **En el tema oscuro, los botones amarillos («Guardar», «Buscar»…) llevaban texto CLARO**: `--ink` es claro
  en oscuro y daba **1,23:1** sobre el amarillo (en `ui-baseline/ajustes--escritorio-1280x800-oscuro.png` se ve
  el texto casi ilegible). No lo detectaba un recorrido regla a regla porque el color venía de otra regla
  (`button { color: var(--ink) }` + `--btn-bg`). Mismo defecto en `.audit-count` y en el resaltado de
  `.view-all` y de la lista de la búsqueda.
- **Las insignias verdes y rojas con texto blanco no llegaban en oscuro** (2,31:1 y 2,89:1) y la verde rozaba
  el límite en claro (4,25:1).
- **El anillo de foco era cyan: 2,84:1 sobre el papel** (los indicadores de foco piden 3:1).
- **Los marcadores de posición** usaban el gris por defecto del navegador, fuera de la paleta.

## Qué se hizo (solo `web.css` y una prueba; ninguna plantilla)

- Rellenos y texto se separan: `--cyan`/`--ok`/`--warn`/`--magenta`/`--yellow` **siguen siendo relleno, borde y trama**
  (la identidad CMYK no cambia); como texto van `--cyan-t`, `--ok-t`, `--warn-t`, `--amber-t`, `--mag-t`.
- `--ink-faint` **conserva el nombre** y cambia de valor (`#63636b` / `#9c9aa0`).
- Pares para rellenos sólidos (`--ok-solid`/`--on-ok-solid`, `--warn-solid`/`--on-warn-solid`, `--on-yellow`) y el par
  de la insignia «caliente» de la maqueta (`--hot`/`--on-hot`, con el texto oscuro en el tema oscuro porque el
  par de la maqueta daba 3,38:1). Aún no hay clase que lo use: lo estrena V3.
- Texto mínimo **14 px** (31 declaraciones de `font-size` subidas), controles de **40 px**, casillas y radios de
  **24 px**, foco en `--cyan-t`, `::placeholder` con color de texto, `✓` en «lo tienes» y borde discontinuo en
  «te falta», borde de tinta en los puntos de estado.

## Efecto en el tamaño de las páginas (móvil, 390 px)

| Captura | Ancho antes → después | Alto antes → después |
|---|---:|---:|
| Ajustes | 390 → 390 | 4.286 → 4.679 |
| Pendientes | 390 → 390 | 5.616 → 5.654 |
| Panel | 390 → 390 | 1.666 → 1.698 |
| Estado | 390 → 390 | 1.040 → 1.053 |
| Ficha de serie | **413** → **413** | 1.806 → 1.867 |
| Aviso legal (texto) | **409** → **409** | 6.000 → 6.000 |
| Deseados | **731** → **390** (con V1 a secas llegó a 756) | 1.582 → 1.542 |

**Deseados: una regresión de V1, corregida en V1.** Con el texto mínimo de 14 px, y sin otro cambio, el
ancho de página en Deseados subía de 731 a **756 px** a 390 px de viewport. La causa, medida con el DOM:
`.wishlist-row` es `display: flex` **sin `flex-wrap`**, y el título (`flex: 1`) se aplastaba a 36 px mientras
la insignia (`white-space: nowrap`, 123 px), «Buscar ahora», el «Buscando…» invisible pero con su sitio
(87 px) y «Quitar» seguían sin caber. Arreglo mínimo, sin bajar los 14 px ni ocultar nada:
`flex-wrap: wrap`, una base para el título (`flex: 1 1 10rem`) y que el panel de candidatos ocupe línea
propia solo cuando tiene contenido. Medido: **390 px → 390 de ancho de página; 320 px → 320; 1280 px sin
cambios (captura idéntica píxel a píxel)**; títulos, estados, motivos y botones siguen visibles y
utilizables (`despues--deseados--movil-*.png`; `intermedio--…sin-flex-wrap.png` muestra el desborde).

**Lo que sigue desbordando, y no es de V1 (a V13):** la ficha de serie (413 px) y el aviso legal en texto
(409 px) desbordaban ya en la línea base y no cambian. V13 debe medir también a **320 px CSS**, la
referencia de reflujo de WCAG.

## Límites
Un navegador y un equipo (Chrome 154, sin probar en la Pi). **La prueba de contraste es una heurística por
reglas**: comprueba los pares de color que `web.css` declara (con los fondos de contexto que define), no la
cascada ni los colores heredados del DOM, ni el contraste renderizado sobre tramas o sombras; cualquier color
que no sabe resolver la hace fallar en vez de omitirse. Se complementa con esta revisión en navegador. Las capturas «después» son un subconjunto (9) de las 30 tomadas, para no inflar el
repositorio; el resto está reproducible con `ui-baseline/README.md`.
