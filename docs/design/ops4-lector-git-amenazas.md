# OPS4: frontera del lector Git experimental (#443)

Este documento fija por qué un lector de objetos Git **no se conecta a la UI ni
al auxiliar** y qué tendría que demostrar una implementación futura. No es una
aprobación ni una prueba de seguridad.

## Hallazgos

- `git cat-file` sobre un repositorio no fiable **no es una frontera de
  seguridad**. Limpiar `HOME`, `GIT_CONFIG_GLOBAL` y `GIT_CONFIG_NOSYSTEM` no
  desactiva la configuración local del repositorio ni
  `objects/info/alternates`.
- Un SHA completo evita abreviaturas y ambigüedad sintáctica, pero no autentica
  autoría, procedencia ni resistencia a colisiones SHA-1. Tampoco prueba que el
  contenido sea inocuo.
- Los reemplazos (`refs/replace`) deben desactivarse explícitamente. No se debe
  usar `--filters`, `--textconv`, recuperación perezosa de objetos ausentes ni
  rutas de repositorio controladas por la aplicación.
- Los límites de tamaño y tiempo convierten una bomba o corrupción en un fallo
  controlado; no garantizan memoria acotada ni disponibilidad.
- Sin aislamiento del sistema operativo no puede prometerse «sin red», «sin
  acceso fuera del repositorio» ni «sin ejecución de otros programas». Las
  variables de entorno y opciones de Git reducen superficie, no sustituyen esa
  frontera.
- Una comprobación previa de ruta no protege de enlaces, sustituciones
  concurrentes ni ficheros especiales. La estabilidad debe garantizarla un
  aislamiento efectivo o una copia controlada.

## Requisitos para un adaptador futuro

1. Solo OID hexadecimal completo, longitud fija; nada de refs, prefijos,
   revisiones, opciones ni rutas desde la app.
2. Binario y entorno fijados; sin shell; sin `PATH` influenciable; cerrar y
   recoger el proceso ante error o timeout.
3. Prohibir reemplazos y recuperación perezosa cuando la versión de Git lo
   permita; no usar filtros ni conversores.
4. Leer cabecera y tamaño con límite **antes** de consumir el contenido;
   acotar bytes, tiempo, descriptores y salida; tratar errores como datos no
   fiables.
5. No confundir objeto ausente, corrupto o no verificable con «no existe» o con
   una decisión favorable: fallar cerrado.
6. Snapshot estable y anclado a la identidad aprobada; el resultado no autoriza
   por sí solo ni sustituye A, P, el cerrojo ni la revalidación.

Mientras no exista aislamiento demostrado y revisión independiente, el
adaptador permanece **desconectado y NOT RUN**; no se habilita la actualización.
