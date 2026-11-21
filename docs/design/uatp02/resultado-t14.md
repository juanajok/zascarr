# T14 · E2E de navegador de UATP-02

**Fecha:** 2026-11-21  
**SHA de producto:** `f570bfa1` (PR #1196)  
**Entorno:** aplicación local aislada, PostgreSQL 15 temporal con datos sintéticos; **no** se usó la base ni la sesión de producción.  
**Navegador:** Google Chrome 156.0.8078.47 (headless) con Playwright; viewport 1440×900 y 320×800.  
**Firefox:** **NOT RUN** en este entorno (falla al crear el sandbox `unshare(CLONE_NEWPID): EPERM`); no se declara PASS.

## Resultado

| Caso | Resultado | Evidencia |
|---|---|---|
| Biblioteca filtrada: `q=Flash`, año 1987, `orden=anio_desc`, tarjetas | PASS | tarjeta visible |
| Ficha: enlace «Volver a la biblioteca» | PASS | texto y `href` canónico |
| Volver: conserva `q`, `anio_desde`, `anio_hasta`, `orden`, `page`, `foco` y ancla | PASS | URL restaurada |
| Foco en tarjeta | PASS | `document.activeElement.id = serie-928f…` |
| Vista lista: fila presente | PASS | 1 fila |
| Vista lista: conserva `vista=lista` y `orden=anio_desc`; foco en fila | PASS | `tr#serie-…` enfocado |
| Tarjeta ausente: foco en `#rejilla` sin perder `q` | PASS | `activeElement = rejilla`; URL conserva `q=NoExiste` |
| Acceso directo a ficha: regreso a Biblioteca | PASS | `href=/ui/biblioteca` |
| 320 px: volver y foco en tarjeta | PASS | `activeElement = serie-928f…` |

Capturas:

- [`t14-ficha-escritorio.png`](t14-ficha-escritorio.png)
- [`t14-biblioteca-tarjetas.png`](t14-biblioteca-tarjetas.png)
- [`t14-biblioteca-lista.png`](t14-biblioteca-lista.png)
- [`t14-biblioteca-320.png`](t14-biblioteca-320.png)

## Límites

- Chrome es la evidencia ejecutada; Firefox queda **NOT RUN** por el entorno, no por un fallo de producto.
- Los datos son sintéticos; la comprobación no sustituye al UAT con la biblioteca real.
- D-1/D-2/D-3 quedan aceptadas por el PO (2026-11-21).
