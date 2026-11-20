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
  supervivencia a corte eléctrico**. Los tres cortes de VM descritos abajo
  aportan evidencia adicional acotada; faltan garantías del dispositivo y
  cortes físicos. `fsync` exitoso no certifica hardware.
- La excepción impide iniciar efectos en esa admisión, pero una marca incierta
  por sí sola no informa de la fase de una actualización. No usarla como
  estado de UI ni como autorización para crear otro ID y reintentar.

## Tres cortes abruptos de VM (2026-11-20)

Se probó el módulo del commit `1d4b1ff9` dentro de QEMU sin NIC. Para cada
frontera se creó un overlay qcow2 nuevo sobre la base sintética del laboratorio;
ningún caso comparte sus escrituras con otro ni modifica la base. La base y
sus ancestros deben conservarse **sin modificar** mientras existan los overlays.

El [sondeo versionado](../../tests/fixtures/ops4-vm/replay-crash-probe.py)
provisiona y sincroniza el directorio de ensayo, invoca el registro real con
un callback que sí hace `fsync` salvo en la barrera elegida, anuncia la
frontera y se detiene con SIGSTOP. El controlador mata el **proceso QEMU**
mediante SIGKILL (código -9), no solo al proceso Python invitado. Luego arranca
el mismo overlay, comprueba la recuperación y apaga limpiamente la VM.

| Frontera del corte | Resultado observado al arrancar | Oráculo |
| --- | --- | --- |
| Después de crear, antes de `fsync` del fichero | Marca ausente | No se había confirmado; ausencia o presencia son admisibles |
| Después de `fsync` del fichero, antes del del directorio | Marca presente, ID rechazado como repetido | No se había confirmado; ausencia o presencia son admisibles |
| Después de ambos `fsync` y retorno `True` | Marca presente, ID rechazado como repetido | Debe conservar el consumo ya confirmado |

Los tres verificadores terminaron con código 0, indicaron
`automatic_retry=False` y no iniciaron operaciones. Cuando la marca estaba
ausente, el verificador **no la recreó**. `qemu-img check` pasó en los tres
overlays después de su recuperación/apagado. Evidencia privada en
`replay-cuts-01/stage-{1,2,3}`, con registros de corte y recuperación.

SHA-256 de los registros privados de recuperación:

```text
stage-1 81d39443ea463b3ec8dd8d36ae07a86417b6b9481f6329626369d9825b6338b6
stage-2 a9148f918086ab94d7f0d5c9c104bdcb6e18d43bf98692c7950b9cda6d49e84a
stage-3 604f0b0be6b23d3408ec672d674bc0210be1afd5f3d0bccc4750c602f5f38370
```

Los [tests de barreras](../../tests/test_ops4_cortes_registro.py) comprueban
sin parar procesos que no se confirma nada antes de los dos `fsync`. Son
simulaciones del contrato de inyección, separadas de los tres ensayos reales.
No se presupone que las recuperaciones tempranas deban dar siempre el mismo
resultado.

**No equivale a pérdida eléctrica:** matar QEMU conserva las cachés y el
sistema de almacenamiento del anfitrión. No se han probado pérdida de energía
del host, fallos del disco, todos los intercalados ni la Pi. Tampoco se ha
cortado el inicio de una unidad actualizadora: este ensayo es exclusivamente
antirrepetición, no reserva/reconciliación del conjunto de la operación.

La función sigue deshabilitada. No se ha instalado ni usado este registro en
la Pi ni se ha ejecutado el actualizador.
