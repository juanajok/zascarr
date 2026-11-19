# ADR 0025 — Aviso observacional de versión (#443, historia A)

## Decisión

`/estado` muestra un aviso **solo lectura**. La identidad del código instalado es
el SHA completo de 40 caracteres incorporado a la imagen en `BUILD_SHA` durante
el build, no `app_version`, la rama del checkout actual ni un `git` ejecutado en
el contenedor. `bootstrap.sh` y `scripts/update.sh` pasan el SHA solo si el árbol
de trabajo está limpio (incluidos archivos no seguidos). En builds manuales el
argumento queda vacío por defecto: la aplicación funciona, pero no afirma que
esté actualizada. Quien construya manualmente un checkout limpio puede pasar
`ZASCARR_BUILD_SHA=<SHA completo>` de manera explícita.

La comparación consulta exclusivamente
`https://api.github.com/repos/juanajok/zascarr/compare/<SHA>...main?per_page=1`.
El SHA se valida antes de construir la URL; no se aceptan redirecciones ni
proxies del entorno. Se exige que `base_commit.sha` coincida con la identidad
instalada y que `merge_base_commit.sha` sea ese mismo SHA. La API Compare no
incluye `head_commit`: `ahead` con `ahead_by > 0` y `behind_by == 0` indica
ascendencia; `identical` con ambos contadores a cero indica que coincide. `diverged`,
`behind`, respuesta malformada, error HTTP, desconexión o identidad ausente se
muestran como «No se puede comprobar»: no se ofrece una actualización que el
script `--ff-only` no podría aplicar desde ese commit.

La primera visita y las visitas tras caducar la caché devuelven «Comprobando»
de inmediato; un sondeo mínimo vuelve a pedir solo un estado JSON cada
10 segundos, sin recargar `/estado` ni esperar al remoto. El navegador elige
un texto fijo para ese estado y lo asigna con `textContent`: nunca inserta
HTML de la respuesta. Solo sustituye el nodo
`aria-live` si el texto cambia, para no repetir anuncios idénticos. Una tarea de fondo hace la consulta
con plazo total de 4 s (también para streaming lento), timeout HTTP (3 s), cuerpo
limitado (500 KiB) y una única petición concurrente por proceso. Los resultados
confirmados duran 15 minutos y los fallos 1 minuto. No se hace `git fetch`, no
se llama al auxiliar del host y no se crea ningún botón ni endpoint de escritura.
El navegador no acepta redirecciones (p. ej. al login), respuestas de otra URL
ni respuestas que no sean JSON con un estado conocido; si el sondeo falla, sustituye cualquier
afirmación anterior por «No se puede comprobar». La prueba de comportamiento
DOM ejecuta el JS con Node **solo si está instalado en el entorno de tests**;
Node no es dependencia del producto ni participa en la imagen o en la Pi.

## Límites

La comparación usa la vista pública de GitHub, no la disponibilidad del host
para desplegar ni un test del script de actualización. Un commit que main
alcance puede requerir migraciones y copia de seguridad; este aviso no certifica
que la actualización vaya a completarse. Los builds con cambios no
confirmados y los hechos fuera de los scripts carecen de identidad automática.
El SHA de una imagen ya creada no cambia aunque se modifique el checkout del
host. La caché vive en un proceso, no es persistente ni se comparte entre réplicas.
