# Definición de hecho (DoD) — aprobada el 2026-11-26

Un trabajo se cierra cuando se cumple lo que exige su nivel de riesgo y existe evidencia enlazada, no cuando el autor lo considera terminado.

## Común a todo trabajo

- Criterios de aceptación verificados uno por uno.
- Sin hallazgos bloqueantes abiertos del nivel correspondiente.
- Documentación y enlaces actualizados; nada de referencias rotas.
- La evidencia indica el SHA o la fecha concreta a la que se refiere.

## Cambios con código

- Pruebas en verde y, cuando aplique, evidencia del rojo previo por el motivo esperado.
- Suite del proyecto en verde en el entorno declarado; los omitidos se justifican.
- Revisión de seguridad **del SHA final** en los casos que la exigen, incluidos los commits añadidos después.
- Ninguna prueba crítica omitida sin decisión explícita.

## Cambios documentales

- Contraste con la fuente citada; el texto distingue lo comprobado de lo inferido.
- Si se retira una norma, existe aprobación del traslado y consta la fecha.

## Límites

El DoD no sustituye la aprobación de fusión ni la decisión de despliegue, que son actos separados y humanos.

## Reglas migradas

### PRE-18 — Regresión nombrada y sin dependencias por probar

Ninguna dependencia nueva se añade «por testing»: lo que se pueda comprobar con la infraestructura existente se comprueba con ella. Cada bug real se cierra con una **prueba de regresión explícita**, nombrada con el mecanismo del bug, no con una prueba genérica.
