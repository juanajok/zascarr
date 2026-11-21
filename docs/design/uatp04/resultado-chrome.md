# T-11 · Chrome de UATP-04

**Fecha:** 2026-11-21  
**SHA de producto:** `abc77570` (PR #1210); la evidencia va en un commit documental posterior.  
**Entorno:** app local aislada, PostgreSQL 15 temporal con dos series «Flash» 1987/2011 y sus deseos; sin datos de producción.  
**Navegador:** Google Chrome **158.0.8127.36**, Linux, Playwright; 320×568 y 390×844, táctil emulado.  
**Lector de pantalla real, Safari/iOS y dispositivo físico:** **NOT RUN**.

## Resultados

| Caso | Resultado | Evidencia |
|---|---|---|
| 320: referencias «Flash (1987)» y «Flash (2011)» visibles | PASS | dos `.wishlist-title` distintas |
| 320: dos enlaces a la ficha con `volver=/ui/wishlist` | PASS | 2 `<a>` con UUID distintos |
| 320: `aria-label` distintos por edición | PASS | Seleccionar/Buscar/Cancelar/Quitar con referencia |
| 320: sin scroll horizontal | PASS | `scrollWidth=innerWidth=320` |
| 320: ficha vuelve a Deseados | PASS | `href=/ui/wishlist`, «← Volver a Deseados» |
| 320: vuelta a Deseados | PASS | URL final `/ui/wishlist` |
| 390: referencias, enlaces, aria y sin scroll | PASS | `scrollWidth=innerWidth=390` |
| 320: Tab llega al enlace de la fila | PASS | foco en `a.wishlist-title` con `href=/ui/series/…?volver=/ui/wishlist` |
| 320: recarga conserva referencias y href | PASS | dos referencias y dos enlaces tras reload |

Capturas:

- [`t11-320.png`](t11-320.png)
- [`t11-390.png`](t11-390.png)

## Límites

- Chrome es la evidencia ejecutada; lector de pantalla, Safari/iOS y dispositivo físico quedan **NOT RUN**.
- Dos series sin año ni volumen siguen compartiendo referencia; es una limitación de datos declarada.
