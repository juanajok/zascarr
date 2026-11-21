# T9 · Chrome de UATP-05

**Fecha:** 2026-11-21  
**SHA de producto:** `5cc84b9c` (PR #1211).  
**Entorno:** app local aislada, PostgreSQL 15 temporal, una serie y un número con CBZ sintético.  
**Navegador:** Google Chrome **158.0.8127.36**, Linux, Playwright.  
**Red lenta, reduced-motion real y lector de pantalla:** **NOT RUN**.

## Resultados

| Caso | Resultado |
|---|---|
| 1440: foco en el chip abre la previa | PASS |
| 1440: Escape la aparta sin mover el foco (sigue en el enlace) | PASS |
| 1440: hover abre la previa | PASS |
| 1440: puntero dentro de la previa no la cierra (hoverable) | PASS |
| 1440: clic dentro de la previa la aparta sin navegar | PASS |
| 1024: hover abre la previa | PASS |
| 720: la variante anclada no se sirve (límite declarado) | PASS (por diseño) |
| 390: botón «Ver portada» abre la previa fija | PASS |

Capturas:

- [`t9-1440.png`](t9-1440.png)
- [`t9-720.png`](t9-720.png)
- [`t9-390.png`](t9-390.png)

## Límites

- La red lenta, `prefers-reduced-motion` real y el lector de pantalla quedan **NOT RUN**.
- Los anchos intermedios con zoom y el dispositivo físico no se ejecutaron.
