# Verificación BL-LECUX2 — cierre de lectura

- **Historia:** [#1069](https://github.com/juanajok/zascarr/issues/1069); épica #1067.
- **Código verificado:** Pi en `c5639e3`; Chrome 156 headless con sesión real.
- **Benchmark previo:** `docs/design/benchmark-LECUX2-cierre-2026-11-18.md`.

## PASS

| Comprobación | Evidencia |
|---|---|
| Tarjeta de fin | Al llegar al final se ve la tarjeta de LEC3 con «Marcar como leído». |
| Marcar | El POST real deja el texto «Guardado: Leído.» y el botón «Deshacer». |
| Deshacer | Vuelve a mostrar «Marcar como leído» sin borrar nota ni puntuación (servicio BL-C3). |
| Siguiente | Se mantiene el «Siguiente: #5» de LEC3, sin una segunda tarjeta. |
| Servicio | La escritura pasa por `services.lectura.marcar`; no hay UPDATE desde el router. |
| Formularios | El `POST` tiene `action` real y `hx-post`; sin HTMX redirige a la lectura. |

## NOT RUN

- Repetición de la operación con el número ya leído y conservación de `completed_at` en la Pi:
  cubierto por pruebas de servicio con Postgres, no por esta pasada de navegador.
- Lector de pantalla real (NVDA/Orca/VoiceOver) y tableta táctil física.
- No se convierte ningún NOT RUN en PASS.
