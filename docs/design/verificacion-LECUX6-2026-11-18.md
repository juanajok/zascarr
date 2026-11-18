# Verificación BL-LECUX6 — lectura inmersiva

- **Historia:** [#1073](https://github.com/juanajok/zascarr/issues/1073); épica [#1067](https://github.com/juanajok/zascarr/issues/1067).
- **Código verificado:** Pi en `fe72c49` (merge de #1093), health OK.
- **Método:** Chrome 156 headless con CDP, sesión real contra la app de la Pi; DOM y estilos computados.
  Capturas fuera del repo (E2): las imágenes no se publican porque muestran una obra real.
- **Benchmark previo:** `docs/design/benchmark-LECUX6-inmersivo-2026-11-17.md`.

## PASS

| Comprobación | Evidencia |
|---|---|
| 1280 px | `.lector-escena`; barra; `.side` y `.site-footer` con `display:none`; página visible. |
| 375 px y 768 px | Sin scroll horizontal (`scrollWidth == innerWidth`); barra visible; flechas superpuestas ocultas; página visible. |
| Flechas | Dos botones reales con `aria-label`; en escritorio el contenedor conserva ambos controles; en táctil/estrecho `display:none`. |
| Opciones | Se abre, contiene el enlace `/legal` y el botón de pantalla completa. |
| `H` | Oculta el chrome y una segunda pulsación lo muestra. |
| Fullscreen | `requestFullscreen()` disponible y entra en fullscreen en Chrome headless. |
| LEC3 | Al llegar al final aparece `#fin` con «Has terminado el #1. Siguiente: #2.» sin romper la tarjeta de fin. |
| Sin nuevas peticiones | No se pide ninguna página nueva al abrir/cerrar chrome ni al cambiar de tamaño. |

## NOT RUN

- Lector de pantalla real (NVDA/Orca/VoiceOver): **NOT RUN** hasta disponer de uno; no se declara PASS.
- Safari/iOS, tablet táctil física y gesto con dedo real: **NOT RUN**; la comprobación táctil es emulación de métricas.
- Fullscreen en dispositivo físico: **NOT RUN**; la API y el flujo se probaron en Chrome headless.

## Cómo repetir

Abrir `/ui/leer/<archivo>` con sesión, comprobar que no hay barra lateral/pie, que `H`/`F`/`Opciones` funcionan y que al llegar a la última página aparece la tarjeta de LEC3. Las capturas de esta pasada quedan en `fuera-de-zascarr/verify-lecux6/` (ignorado por Git).
