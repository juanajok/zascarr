# Verificación BL-LECUX5 — accesibilidad del lector

- **Historia:** [#1072](https://github.com/juanajok/zascarr/issues/1072); épica #1067.
- **Código verificado:** Pi en `78c86b3`; Chrome 156 headless con sesión real.
- **Alcance:** teclado, DOM, foco, roles y objetivos; **lector de pantalla real: NOT RUN**.

## PASS (teclado y DOM)

| Comprobación | Evidencia |
|---|---|
| Contador | `aria-live="polite"` en `#lector-contador`. |
| Menú | Botón «Opciones» con `aria-controls="lector-menu"`; al abrirlo `aria-expanded="true"`; al cerrarlo vuelve a `false`. |
| Barra | `role="group"` y nombre accesible. |
| Flechas | Dos `<button>` con `aria-label` «Página anterior»/«Página siguiente»; 48 px. |
| Orden de foco | Salto de contenido → Volver al número → Opciones → tarjeta de fin; el foco no queda atrapado. |
| Foco y auto-ocultado | Con el foco dentro de la barra, el chrome **no** se oculta tras 3 s; `focusout` lo reprograma. |
| Aviso legal | Enlace `/legal` dentro de Opciones. |
| Errores | `#lector-error` con `role="alert"`; la espera usa `role="status"`. |
| `forced-colors` | Regla de foco visible con `CanvasText` para flechas, botones y controles de imagen. |
| `prefers-reduced-motion` | Sin transición en barra/flechas (regla estática). |

## NOT RUN

- **Lector de pantalla real (NVDA/Orca/VoiceOver): NOT RUN.** No hay uno disponible en el
  entorno; no se declara PASS ni se cierra la historia como verificada.
- **Chrome/Safari en dispositivo táctil físico y zoom real:** NOT RUN.
- **`forced-colors` y `prefers-reduced-motion` en navegador real:** solo comprobación estática;
  no se convierten en PASS.
- **Arrastre/selección táctil con hardware:** NOT RUN.

## Consecuencia

El defecto de foco que podía ocultar el chrome con el foco dentro está corregido y cubierto por
pruebas. La historia **no se cierra del todo** hasta disponer de lector de pantalla; se mantiene
abierta con esta evidencia.
