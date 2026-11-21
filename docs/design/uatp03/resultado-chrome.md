# T12 · Chrome de UATP-03

**Fecha:** 2026-11-21  
**SHA de producto:** `53f8417c` (PR #1207); esta evidencia se versiona en un commit documental posterior.  
**Entorno:** app local aislada, PostgreSQL 15 temporal y CBZ sintético de 5 páginas; sin datos de producción.  
**Navegador:** Google Chrome **158.0.8127.36**, Linux, con Playwright; viewports reales 320×568, 390×844 y 568×320; táctil emulado y ratón.  
**Firefox/Safari/iOS/Android físico/lector de pantalla:** **NOT RUN** en este entorno.

## Resultados

| Caso | Resultado | Evidencia |
|---|---|---|
| 320: barra oculta al cargar; asa visible 44×44 | PASS | `#lector-asa` `display:flex`, 44×44 |
| 320: foco inicial no forzado | PASS | `activeElement=BODY`, sin marco |
| 320: toque en asa revela barra sin cambiar página | PASS | `data-pagina=1`, barra `opacity=1`, foco en enlace |
| 320: «Volver al número» alcanzable sin scroll horizontal | PASS | 44 px, `scrollWidth=320=innerWidth` |
| 320: Opciones por toque y Escape | PASS | página 1 intacta, foco vuelve al disparador |
| 390: avance por toque | PASS | página 2 |
| 390: reabrir conserva página guardada | PASS | `data-pagina=2` |
| 390: Opciones/modo conservan página | PASS | página 2 |
| 390: pasar página con la barra oculta no la revela | PASS | `data-chrome=oculto`, página 2 |
| Ratón: trayectoria `x=500, y=300→90→22` mantiene el asa visible | PASS | asa `display:flex` en ambos puntos |
| Ratón: clic en asa revela barra | PASS | barra visible, foco en «Volver al número» |
| 568×320: fin abierto en la última | PASS | `#fin` visible |
| 568×320: Tab desde `#fin-titulo` | PASS | foco en control del fin, barra fuera de pantalla |
| RTL: render y toque izquierdo avanza | PASS | `data-sentido=rtl`, página 1→2 |
| RTL: doble página en `row-reverse` | PASS | `flexDirection=row-reverse` |

Capturas:

- [`t12-320-asa.png`](t12-320-asa.png)
- [`t12-320-barra.png`](t12-320-barra.png)
- [`t12-390-opciones.png`](t12-390-opciones.png)
- [`t12-390-rtl-doble.png`](t12-390-rtl-doble.png)
- [`t12-568x320-fin.png`](t12-568x320-fin.png)

## Límites

- Chrome es la evidencia ejecutada; Firefox/Safari/iOS/Android físico y lector de pantalla quedan **NOT RUN**.
- El CBZ y la base son sintéticos; no sustituye una prueba con la biblioteca real.
