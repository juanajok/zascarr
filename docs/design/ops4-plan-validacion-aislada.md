# OPS4: plan de validación aislada (#443)

La actualización desde la interfaz continúa **deshabilitada**. Este plan no es una
aprobación de diseño, instalación, prueba en producción ni ejecución como root.
Las pruebas aisladas son evidencia limitada, no sustituyen las puertas de la
[especificación OPS4](especificacion-BL-OPS4.md).

| Riesgo | Observable que se necesita | Estado |
|---|---|---|
| Aprobación repetida | Con N procesos e intentos distintos se acepta como máximo una reserva durable de la misma aprobación. | Pendiente; el modelo puro puede bifurcarse. |
| Interrupción de escritura | Ante caída en cada escritura, `fsync` y renombrado, ningún reinicio acepta una aprobación de resultado ambiguo como libre. | Pendiente; un error tras `rename` no demuestra qué sobrevivirá. |
| Identidad y tiempo | La unidad revalida intento, SHA completo, host, origen, manifiesto y vigencia real antes de efectos. | Modelo puro parcial; no acredita origen, reloj fiable ni unidad. |
| Ruta hostil | Enlaces, padres reemplazables o permisos inseguros no permiten leer/escribir fuera del directorio anclado. | Pendiente de política y pruebas de descriptores y ancestros. |
| Referencia mutable | El flujo usa el SHA aprobado, o se detiene ante ref cambiada; no instala otro. | Arnés Git local reproduce el cambio de ref; el ejecutor aún no existe. |
| Árbol Git | Cada objeto y entrada del árbol se verifica, sin checkout, hooks ni filtros; el resultado se ancla al commit y a la política host. | Lector puro experimental con pruebas de objetos sintéticos; pendientes autenticidad, ascendencia, anclaje de P y entrega inmutable a root. No es autorización. |
| Inicio ambiguo | Si `systemctl start` falla o se pierde la respuesta tras un posible efecto, no se reintenta y se exige reconciliación. | Pendiente de unidad y arnés real. |
| Runtime | La imagen, el contenedor, la salud y la BD corresponden a la versión exacta aprobada. | NOT RUN: Docker, PostgreSQL, systemd y host aislado. |
| Aislamiento de producción | Ninguna prueba usa la Pi, datos reales, sistema de ficheros de producción ni root. | Obligatorio en este tramo. |

## Límite del lector Git experimental

El lector procesa objetos suministrados por un proveedor inyectado, no hace
`fetch` ni genera un snapshot materializado. SHA-1 no acredita autoría ni
resistencia suficiente a colisiones; no se verifican firmas ni ascendencia, y
los árboles vacíos no figuran en el inventario de blobs. Los límites se aplican
tras recibir cada objeto, por lo que no acotan la memoria del proveedor ni el
coste total del inventario. Un resultado correcto solo vale dentro de estas
hipótesis; no prueba procedencia, integridad de P ni transferencia segura a root.

## Resultado del experimento de persistencia

Se ensayó un prototipo desechable con `flock`, marcador de reserva y escrituras
con `fsync`. **No se incorpora como almacén**: la revisión identificó que un
fallo de `fsync` seguido de corte puede hacer desaparecer el marcador y dejar
aparentemente libre la aprobación; un cerrojo abierto por ruta puede ser
sustituido, y no hay transferencia segura al ejecutor separado. Reabrir el
objeto en la misma máquina no simula un reinicio ni demuestra durabilidad. La
reconciliación externa y la cadena de confianza de rutas siguen pendientes.

Las pruebas de funciones puras y simulaciones no prueban persistencia frente a
toda avería física, seguridad de ruta en el host, ni ejecución privilegiada.
El criterio de salida continúa siendo la SPEC y la revisión independiente del
SHA final; para activar o desplegar hace falta autorización separada.
