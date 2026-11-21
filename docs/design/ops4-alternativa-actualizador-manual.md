# OPS4 — alternativa de botón para el actualizador manual (#443)

**Estado: política elegida por el usuario, no implementada ni habilitada.**
La [SPEC histórica](especificacion-BL-OPS4.md) mantiene el análisis C-12; el
[nuevo contrato](ops4-especificacion-main.md) está en revisión. Esta decisión no
autoriza fusionar, desplegar ni activar.

## Alternativa planteada

El usuario pide desde la UI una acción fija, tras confirmar y reautenticarse;
el auxiliar del host comprueba de nuevo la contraseña viva y solicita una unidad
preinstalada sin aceptar comando, ruta ni rama del cliente. El actualizador
haría copia verificada, actualizaría desde `main`, reconstruiría imagen,
ejecutaría migraciones, recrearía el servicio y comprobaría salud. El estado
host debe sobrevivir al reinicio de la app y distinguir solicitud aceptada,
ejecución, éxito verificado y fallo o resultado incierto. No hay reintento ni
rollback automáticos. Todo esto sería un cambio de política respecto de C-12.

Confiar en `main` sin aprobación administrativa para cada SHA ni rechazo de
migraciones reduce pasos del usuario, pero también elimina esas dos barreras
explícitas de la SPEC. Los cambios futuros de `main` y sus migraciones tendrían
el mismo grado de confianza que una actualización manual por consola. Ese
intercambio fue elegido expresamente por el usuario; no supone que el código
actual sea seguro para conectarlo directamente a la UI.

## Lo que se puede aprovechar y lo que falta

- La UI de restauración ya muestra confirmación y contraseña, y su auxiliar
  verifica la contraseña contra la BD; HMAC de la app no identifica a la
  persona. El protocolo v2 actual está cerrado para sus acciones y no autoriza
  por sí solo `actualizar`. Se necesita un contrato específico, con límites y
  pruebas de compatibilidad y secretos.
- El cerrojo común existente y la copia previa son puntos de partida; la
  ejecución debe seguir excluyendo copia/restauración simultáneas. Una orden
  `systemctl start --no-block` aceptada no prueba que la tarea haya terminado.
- El seguimiento en memoria de la app no basta: la actualización puede reiniciar
  el propio proceso. Hay que correlacionar y conservar estado del host sin
  secretos y reconciliar estados inciertos después de perder la conexión.

## Riesgos concretos antes de reutilizar el script

[update.sh](../../scripts/update.sh) hoy hace `fetch` y avanza una rama móvil,
construye desde el repositorio, aplica `alembic upgrade head` y puede ejecutar
un instalador desde el árbol ya actualizado. Su comprobación inicial de árbol
limpio no excluye todos los archivos no rastreados del contexto de build; el
entorno influye en rutas y configuración mediante `scripts/_comun.sh`.
Por tanto **un nombre fijo de script no garantiza por sí mismo una frontera
privilegiada segura**. Antes de exponerlo hay que revisar propiedad de archivos
host, rutas/entorno, contenido ejecutado con root tras el fetch, concurrencia,
identidad de imagen y comportamiento de fallos; una rama fija y contraseña no
resuelven esos riesgos por sí solas.

**Pendiente:** definición de qué código actualizado se confía para ejecutarse
con privilegios, revisión de seguridad y pruebas de extremo a extremo en un
entorno aislado. La política fue elegida, pero no hay implementación en esta
rama.
