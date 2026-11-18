# Verificación BL-LECUX3 — precarga

- **Historia:** [#1070](https://github.com/juanajok/zascarr/issues/1070); épica #1067.
- **Código verificado:** Pi en `7c8ece9`; Chrome 156 headless con CDP y sesión real.
- **Benchmark previo:** `docs/design/benchmark-LECUX3-precarga-2026-11-18.md`.

## PASS

| Comprobación | Evidencia |
|---|---|
| Página inicial | Chrome pide `/pagina/1` (visible) y `/pagina/2` (precarga). |
| Avance | Tras `ArrowRight`, pide `/pagina/3`; no repite `/2` ni salta fuera. |
| Final | Con `End` llega a la última página (49) y no pide `/50`. |
| Duplicados | Ninguna URL de página repetida en la traza de red. |
| Sin precarga fuera de rango | Las URLs solicitadas están dentro de `[1, total]`. |
| Sin cambios de servidor | La precarga usa la misma URL de página; no hay endpoint nuevo. |

## Pi

- 100 peticiones HTTP reales a páginas (con sesión): **p50 7,149 ms · p95 7,805 ms · máx 292,731 ms**
  (incluye HTTP/cliente; no es el tiempo de cambio de página en navegador).
- RSS del contenedor tras la prueba: **136,5 MiB / 512 MiB**.

## NOT RUN

- p50/p95 del **cambio de página percibido en navegador** (la traza mide peticiones, no el render).
- Tableta/móvil táctil físico y lector de pantalla.
- No se convierte ningún NOT RUN en PASS.

## Cómo repetir

Abrir un número sin progreso, observar la petición de la página siguiente en DevTools/Red; avanzar
una vez y comprobar que pide la siguiente; llegar al final y comprobar que no pide una página
posterior al total.
