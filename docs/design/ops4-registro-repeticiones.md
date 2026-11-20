# OPS4 — registro experimental antirrepetición

La [política de main y migraciones](ops4-especificacion-main.md) exige
antirrepetición y persistencia antes de iniciar efectos. Este componente
cubre **solo el consumo de un ID**, no la reserva durable de operación ni el
cerrojo compartido. Sigue desconectado de la web, el auxiliar y el instalador.

## Contrato implementado

[reclamar_id](../../deploy/ops/registro_repeticiones_ops4.py) recibe un ID de
32 caracteres hexadecimales minúsculos y un descriptor de directorio ya abierto
por un llamador confiable. No recibe rutas de una petición. Duplica el
descriptor, comprueba que sea directorio y rechaza escritura por grupo/otros.
No crea ni provisiona el directorio.

1. Crear `solicitud-<id>` con `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, modo 0600.
   La marca vacía no contiene contraseña, hash, firma ni datos de operación.
2. Sincronizar el fichero y luego el directorio mediante `fsync`.
3. Cerrar los descriptores propios. Solo entonces devolver `True`.

Si el nombre ya existe, devolver `False` sin seguirlo ni borrarlo: también
cuentan como consumidos un enlace, FIFO, directorio o marca incompleta. Ante
cualquier otro error, elevar `RegistroNoDisponibleError` sin detalles del
sistema. No borrar una marca creada aunque falle la sincronización: su
persistencia puede ser incierta. No reintentar `close` tras un error, evitando
cerrar un descriptor que el sistema haya reutilizado.

El callback de sincronización es de confianza y existe para inyectar fallos
en las pruebas. No es una prueba independiente de durabilidad: un callback
que no sincroniza no sirve para el host.

## Orden y composición probados

La [admisión](../../deploy/ops/admision_actualizar_ops4.py) autentica antes de
llamar al registro. Las [pruebas](../../tests/test_ops4_registro_repeticiones.py)
comprueban composición por callback: contraseña incorrecta no crea marcas;
autenticación válida y marca sincronizada permiten una aceptación; la segunda
petición se rechaza como repetida. Un fallo de sincronización produce
`NO_DISPONIBLE`, no aceptación. Esta composición solo se ejecuta en tests;
no está conectada al servicio.

También se prueban creación real y reapertura desde otro proceso, hilos y
procesos concurrentes con un único ganador, orden de `fsync`, fallos en ambas
sincronizaciones, disco lleno, descriptor inválido, errores de duplicación,
inspección y cierre, ausencia de fugas de FD y renombrado del directorio sin
redirigir las operaciones a una ruta sustituta.

## Límites antes de integrar

- La exclusión de un ID se apoya en `O_EXCL` del filesystem local. No impide
  dos actualizaciones con **IDs distintos**. Falta la reserva de operación,
  el cerrojo compartido y la reconciliación de un inicio incierto.
- Directorio confiable, propietario esperado, jerarquía, aprovisionamiento y
  sincronización de su creación deben acreditarse en el host. Un descriptor
  anclado no demuestra que el directorio sea el de la instalación autorizada.
- No hay retención, poda ni cuota implementadas. Las marcas son permanentes;
  un almacenamiento lleno deniega. La política de capacidad/limpieza debe
  decidirse y probarse antes de conectar el componente. Borrar marcas
  indiscriminadamente puede reabrir una ventana de repetición.
- La reapertura en procesos nuevos demuestra persistencia observable, **no
  supervivencia a corte eléctrico**. Faltan pruebas de cortes en la VM y de
  garantías del filesystem/dispositivo. `fsync` exitoso no certifica hardware.
- La excepción impide iniciar efectos en esa admisión, pero una marca incierta
  por sí sola no informa de la fase de una actualización. No usarla como
  estado de UI ni como autorización para crear otro ID y reintentar.

La función sigue deshabilitada. No se ha instalado ni usado este registro en
la Pi ni se ha ejecutado el actualizador.
