# Evidencia de V4b — Inicio guiado

Capturas y mediciones en navegador real (Chrome 154, *headless*, CDP) contra el entorno aislado de V0
(`docs/design/ui-baseline/ensayo.sh`), con la imagen construida **desde esta rama** (se comprobó que
el contenedor lleva el código nuevo). Datos sintéticos de `sembrar.py`. Herramienta: `verificar.py`
(casos `estados`, `flujo`, `busqueda`); resultados crudos en `verificar-*.json`.

> Procedimiento: levantar con `UI_BASE_DATOS=<carpeta nueva> ensayo.sh preparar`, **esperar unos segundos
> a que la app responda** (la primera navegación justo después de `preparar` falló una vez por llegar
> antes de tiempo) y ejecutar `python3 verificar.py estados|busqueda|flujo http://127.0.0.1:18000 <salida>`
> en ese orden: `flujo` es **destructivo** (vacía la base de datos del ensayo y borra los tebeos de su
> carpeta de biblioteca), así que va el último y exige antes los datos sintéticos.

## El recorrido de una instalación nueva, con la interfaz real

| Paso | Estado observado | Qué enseña el Inicio |
|---|---|---|
| 0 | BD vacía, 14 tebeos en el disco | «Aún no hay tebeos en ZascArr». **Sin tarjetas de cifras, sin `%`.** Un solo botón principal: *Preparar mi biblioteca* |
| 1 | Se pulsa el botón → **Duplicados**; se pulsa *Analizar* | «Miramos tu disco el 3 de octubre y encontramos 14 tebeos. Ahora ZascArr tiene registrados **0**». El paso 1 **sigue** pendiente: **el informe no registra nada**. Sin tarjetas (14 encontrados junto a «0 por revisar · nada sin clasificar» eran ceros contradictorios) |
| 2 | Se pulsa *Registrar* (acción explícita) | Paso 1 **hecho** («12 tebeos registrados · no se movió nada · 4 comparados a fondo el …»). Siguiente: *Revisa 12 tebeos*. Aparecen las cifras, con su procedencia |
| 3 | Se descartan los 12 | Lo obligatorio está hecho: la lista **se pliega** («Lo básico está hecho · 2 de 4 pasos») |
| 4 | Sin tebeos en el disco ni registrados | El paso 1 pasa a *Aún no se puede* y lo **explica**; el botón principal pasa a *Buscar series* |

Los **estados con datos sintéticos tal cual** (catálogo previo, informe, 6 por revisar, 5 deseados) están en
`inicio-catalogo-previo--*` (escritorio, 390 y 320 px; claro y oscuro).

## Medido

| Comprobación | Resultado |
|---|---|
| **Acción principal** en cada estado (7: datos sintéticos a 3 anchos y los 5 del recorrido) | **visible** (caja con tamaño, fuera de un `<details>` cerrado), **alcanzable con Tab** (8-12 tabulaciones) y **`Enter` lleva al destino anunciado**. Con lo obligatorio hecho, la recomendación queda **fuera** del bloque plegado |
| Botón «Buscar» frente al principal | fondo `rgb(246, 243, 236)` frente a `rgb(242, 197, 0)`: distintos (la regla global `button[type=submit]` lo pintaba de amarillo aunque no llevara `.primary`) |
| «Sigues N series» frente a Deseados | 5 peticiones, **3 series distintas**: el Inicio dice «Sigues 3 series»; el contador del menú sigue diciendo 5 |
| `%` en la página sin catálogo de grapas | **ninguno** (en los 5 estados del recorrido y en el de datos sintéticos) |
| Desborde horizontal en escritorio / 390 / 320 px | **ninguno** |
| «Buscar una serie» | `GET /ui/descubrir?q=Guardianes+del+Alba` → caja rellena y **una** petición `/ui/descubrir/buscar?q=…` al cargar |
| Un solo `<h1>` y orden de pasos como lista numerada | sí |

## Una corrección a la propia evidencia

La primera tanda de `inicio-catalogo-previo--*.png` **no era del Inicio**: `comprobar_principal` pulsa el
botón principal con `Enter` (para medir que lleva donde dice) y la captura se tomaba después, ya en *Por
revisar*. Lo vio la revisión de la PR #70, no la herramienta. Ahora `foto_de_inicio` vuelve a `/ui/` y
**comprueba la ruta y el `<h1>` antes de guardar** (si no es el Inicio, aborta sin escribir), y la captura
de la búsqueda comprueba que está en Descubrir. Se regeneraron esas 4 capturas y su JSON; las 10 del
recorrido (`flujo-*`) se tomaron ya tras volver a `/ui/` y se comprobó la franja superior de cada una
(menú «Inicio» activo y `<h1>` «Inicio»), pero **no se regeneraron con la comprobación nueva**.

## Lo que NO prueba esto

Un navegador, un equipo, datos sintéticos; **ni Firefox/Safari ni la Pi**. «Comparados a fondo» es la
cifra del informe tal como la guarda B16 (`files_hashed`), no «comparados contra todo». El recorrido del
disco de la adopción no se midió en un disco en red.
