# Evidencia de U12 (#199): «Por revisar» a escala, en la aplicación integrada a 375 px

Mediciones en **navegador real** de la rama `claude/u12-pendientes-escala`, 2026-10-15 (segunda versión, tras la
revisión de la PR #214: enlace a carpetas con recuento, página vaciada y refrescos fuera de orden). Ficha de
referencia: `docs/design/benchmark-U12-pendientes-escala.md` (PR #213).

| Dato | Valor |
|---|---|
| Entorno | ensayo aislado `docs/design/ui-baseline/ensayo.sh` (Compose `zascarr-uibase`, **Postgres real**, `127.0.0.1:18000`), rehecho desde cero para esta ejecución |
| Navegador | Google Chrome 154.0.8037.92 headless por CDP; **emulación de viewport** 375 × 812 con `mobile=true` (no es un móvil real) |
| Herramienta | [`capturar_u12.py`](capturar_u12.py): clics **reales** (`Input.dispatchMouseEvent`) y `confirm()` aceptado por el protocolo |
| Datos en bruto | [`datos.json`](datos.json) |
| Datos | **sintéticos**: los 6 pendientes del ensayo (con portada real) + un `.cbr`, un nombre de 158 caracteres sin espacios y 60 archivos de relleno **cuyo fichero no existe**. Total: 68 |

## Resultados

| Criterio de la ficha | Medido | Resultado |
|---|---|---|
| Rango y total (caso 1) | «Mostrando 1–50 de 68 pendientes.» | PASS |
| Navegación con clics reales (caso 4) | «Siguientes →» → «Mostrando 51–68 de 68» (18 tarjetas); «← Anteriores» → «Mostrando 1–50 de 68» | PASS |
| Rango sin recargar tras resolver (caso 7) | «Ignorar» (con `confirm`) → «Mostrando **1–49 de 67**»; 1 sola navegación de documento; el refresco pidió `/ui/pendientes/rango?primero=…&ultimo=…` (**`hx-include` funciona en htmx 4**) y respondió 200 | PASS |
| Sin scroll horizontal a 375 px (12) | `scrollWidth` 375 = `clientWidth` 375, **con** el nombre de 158 caracteres sin espacios | PASS |
| Nombre íntegro (12) | El nombre largo mide 87 px de alto (3 líneas), `text-overflow` ≠ `ellipsis`, `white-space` ≠ `nowrap`, cabe en su caja | PASS |
| Primer pantallazo con nombre completo (11) | El nombre de la primera tarjeta está entero dentro de los 812 px | PASS (la primera tarjeta es el `.cbr`; ver nota) |
| Ausencia conocida (9) | La tarjeta del `.cbr` **no** tiene `<img>`, ni bloque de portada, ni la cadena `/portada` | PASS |
| Disponible (11) | La portada mide **120 × 180** y está **debajo** del nombre | PASS |
| Desconocida sin hueco (10) | **43 portadas** que fallan, todas con **0 px** de alto; sin `onerror` en la página | PASS (Chrome) |
| Peticiones de portada | 49 para 50 tarjetas (la del `.cbr` no pide): 6 × 200 y 43 × 404 | informativo |
| Enlace a carpetas (criterio 5) | «Verlos por carpeta (**1 carpeta**)»: N = número de **carpetas** (grupos), con la misma definición que la pantalla de carpetas. En el ensayo todo está en `_Unsorted`, de ahí 1 | PASS |
| Refrescos fuera de orden (bloqueante 3) | Dos «Ignorar» seguidos; la respuesta del **primer** refresco se retiene hasta que termina el segundo y entonces se suelta. Con `hx-sync`: **1 petición abortada** y queda «1–48 de 65». **Control sin `hx-sync`: también queda «1–48 de 63»** (ver abajo) | PASS |

![primera página](1-primera-pagina-375.png) ![segunda](2-segunda-pagina-375.png) ![tras ignorar](3-tras-ignorar-375.png)

## Refrescos fuera de orden: lo que se midió y lo que NO se puede afirmar

El experimento (`refrescos_fuera_de_orden` en el guion, con `Fetch` del protocolo, en la etapa de **respuesta**) retiene
la respuesta ya calculada del primer refresco, deja terminar el segundo, suelta la antigua y mira qué queda. Cada
ejecución solo vale si hubo 2 resoluciones y 2 refrescos (`valido`). Resultado, en htmx 4.0.0 / Chrome 154:

| Variante | Resoluciones / refrescos | Abortados | Tras el 2.º refresco | Tras soltar el 1.º |
|---|---|---|---|---|
| Con `hx-sync="#pend-rango:replace"` | 2 / 2 | **1** | 1–48 de 65 | 1–48 de 65 |
| Control: sin `hx-sync` (se quita de la respuesta) | 2 / 2 | 0 | 1–48 de 63 | 1–48 de 63 |

**El control también conserva el último.** La explicación, que es la que mejor encaja con lo observado pero que **no
he verificado leyendo el código de htmx**: el refresco es un `outerHTML`; cuando el nuevo sustituye a `#pend-rango`,
la respuesta antigua apunta al elemento viejo, ya desconectado, y no tiene efecto visible. Por tanto:
- **No puedo afirmar que `hx-sync` sea necesario** para este contrato; lo que añade es **abortar** la petición
  antigua (1 abortada en la variante con él) y no depender de un detalle del intercambio. Se mantiene como defensa
  adicional, no como la causa de que el rango sea correcto.
- Una primera versión de este experimento retenía la **petición** (antes de que el servidor la calculara) y por eso
  la respuesta tardía salía fresca: no probaba nada. Está corregido y documentado en el guion.
- No se ha probado el caso en que el refresco nuevo **falla** (204/500) mientras llega el antiguo.

## Lo que esto NO acredita

- **Los 43 × 404 son un artefacto de los datos de relleno** (su fichero no existe), **no** una medición de la
  instalación real. La ficha sigue sin saber cuántos de los pendientes reales fallan ni por qué.
- **Solo Chrome 154.** Firefox y Safari (incluido iOS): **NOT RUN**. El colapso de la portada rota a 0 px está medido
  aquí en la app integrada, pero solo en ese navegador.
- Viewport **emulado**, no un teléfono real; la Pi del responsable y un lector de pantalla: **NOT RUN**.
- Un `.cbz` sin imágenes o corrupto **sigue costando una petición 404**: es la incompatibilidad declarada en la ficha
  (saberlo de antemano exige I/O por archivo o una columna «tiene portada»).

## Dos hallazgos de la implementación (no estaban en la ficha)

1. **`files.imported_at` admite NULL** en la BD real: la migración inicial no pone `NOT NULL`, aunque el modelo no
   declare `Optional`. La ficha afirmaba lo contrario. Con un cursor, una fila con NULL daba un 500 y quedaría fuera
   de toda comparación. Se ordena y compara por `COALESCE(imported_at, 1970)`; prueba con Postgres real que falló antes.
2. **El `confirm()` de «Ignorar» bloquea el clic** hasta que se responde: la verificación automática lo acepta por el
   protocolo, como haría la persona.
