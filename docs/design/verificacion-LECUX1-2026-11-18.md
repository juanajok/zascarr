# Verificación BL-LECUX1 — ajustes de imagen

- **Historia:** [#1068](https://github.com/juanajok/zascarr/issues/1068); épica [#1067](https://github.com/juanajok/zascarr/issues/1067).
- **Código verificado:** Pi en `e5f4ff1`; Chrome 156 headless con CDP y sesión real.
- **Benchmark previo:** `docs/design/benchmark-LECUX1-imagen-2026-11-18.md`.
- Las capturas de la prueba quedan fuera del repo (E2); no se publican páginas reales.

## PASS

| Comprobación | Evidencia |
|---|---|
| Neutro | `#lector-paginas.style.filter === "none"` al abrir. |
| Brillo | Valor 20 → `brightness(1.2)`; sin petición de red ni cambio de página. |
| Sepia acumulado | `brightness(1.2) sepia(1)`. |
| Persistencia | Tras recargar: `brightness(1.2) sepia(1)`; `localStorage` contiene `zascarr.lector.imagen`. |
| Menú | El grupo Imagen y el enlace `/legal` están presentes; el filtro solo se aplica al contenedor de páginas. |
| Restablecer | Vuelve a `none` y elimina la clave de `localStorage`. |
| Sin almacenamiento | Cubierto en Node/DOM: el lector aplica valores neutros y no lanza. |

## NOT RUN

- Lector de pantalla real y dispositivo táctil físico: **NOT RUN**; no se convierten en PASS.
- Medición de red en la Pi para los ajustes: no se hizo una traza de red; el código no añade fetch
  y los criterios de DOM/JS cubren que no se pide página nueva.

## Cómo repetir

Abrir un número, ir a Opciones → Imagen, mover brillo/contraste, marcar sepia/invertir, recargar
y comprobar que el filtro se mantiene; «Restablecer imagen» debe volver a neutro y borrar la
preferencia del dispositivo.
