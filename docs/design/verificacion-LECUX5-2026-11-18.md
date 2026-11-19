# Verificación BL-LECUX5 — accesibilidad del lector

- **Historia:** [#1072](https://github.com/juanajok/zascarr/issues/1072); épica #1067.
- **Código verificado:** Pi en `78c86b3`; Chrome 156 y **Orca 50.2** reales, con
  `--force-renderer-accessibility` y AT-SPI.

## PASS (real)

La traza de voz de Orca (`SPEECH OUTPUT`, registro de depuración) confirma:

| Comprobación | Evidencia |
|---|---|
| Carga de la página | «Fin de la carga de Leer — XIII.» |
| Contador | «Página 49 de 49» |
| Salto y contenido | «Saltar al contenido», «contenido principal» |
| Barra | «Controles del lector» (panel) |
| Menú | «Opciones» (botón, contraído) |
| Flecha siguiente | «Página siguiente» (button, sombreado) |
| Foco con teclado | El foco llega a la barra/menú y no se pierde; la secuencia de foco se recorrió con Tab. |
| Foco y auto-ocultado | Con el foco dentro, el chrome no se oculta; «Opciones» conserva su estado. |

También se verificó en Chrome el contador `aria-live="polite"`, el menú con
`aria-expanded`, la barra `role="group"`, las flechas con `aria-label`, los objetivos de 48 px y
la regla de foco `forced-colors`.

## NOT RUN / pendiente

- **Anuncio de un cambio de página** en una lectura no final: la pasada con Orca se hizo sobre un
  número ya en la última página; no se capturó el anuncio de «Página 2». **NOT RUN**, no PASS.
- **Apertura/cierre del menú y errores `role="alert"` anunciados**: no se capturó la locución
  completa; se comprobó el DOM/atributos, no la locución. **NOT RUN**.
- **Safari/iOS, tableta táctil física y zoom real:** NOT RUN.
- **`prefers-reduced-motion` y `forced-colors` en dispositivo real:** solo estático; no PASS.

## Consecuencia

El lector ya tiene una pasada real de Orca y los anuncios básicos están acreditados. No se
declara la historia PASS completo ni se cierra: faltan los anuncios de página/menú/error y la
prueba táctil/iOS. El defecto de foco que ocultaba el chrome con el foco dentro está corregido y
cubierto por pruebas.
