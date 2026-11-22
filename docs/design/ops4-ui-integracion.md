# OPS4 — integración de UI (deshabilitada por defecto)

La pantalla `/estado` incorpora un formulario de actualización **solo** cuando
`OPS4_ACTUALIZACION_HABILITADA=true`. En el valor por defecto (`false`) se
conserva el botón `disabled` y la ruta responde 404 antes de leer la clave o
reautenticar. No se ha desplegado ni habilitado en producción.

## Configuración

- `OPS4_ACTUALIZACION_HABILITADA` (bool, `false`).
- `OPS4_AUTORIZACION_KEY_FILE` (por defecto `/run/zascarr-ops/actualizar.key` en el contenedor; fichero real `/var/lib/zascarr/ops/actualizar.key`).
- `OPS4_SOCKET_FILE` (por defecto `/run/zascarr-ops/actualizar.sock`).

La clave y el socket son dedicados; no se reutilizan los de copia/restauración.

## Flujo

`POST /ui/actualizar` exige confirmación explícita y contraseña actual. Lee la
clave dedicada con `uid=0`, modo `0440`, sin seguir enlaces; llama al servicio
v4, que reautentica por el servicio compartido y envía el testigo. Los mensajes
no incluyen contraseña, testigo ni detalles internos. `INCIERTA` indica
expresamente no reintentar y revisar el host.

El formulario incluye contraseña, confirmación y un único botón; sigue el
lenguaje llano de la pantalla. No hay JavaScript nuevo.

## Pruebas

- [test_ops4_ui_actualizacion.py](../../tests/test_ops4_ui_actualizacion.py):
  deshabilitada da 404 sin leer clave/servicio, confirmación obligatoria,
  clave ausente 503, aceptación/rechazo sin secretos e incierta sin invitación
  a reintentar.
- [test_ops4_ui_gate.py](../../tests/test_ops4_ui_gate.py): la ruta solo está
  activa tras la puerta; sin habilitar responde 404.
- **391 pruebas OPS4/instalador** y suite completa **8949 passed / 2454 skipped /
  0 failed** verdes. Incluye un E2E local ruta→servicio→socket Unix temporal→
  admisión→consumo durable.

## Límites

- El auxiliar y las unidades están en la rama; el circuito auxiliar→unidad se
  validó en la VM con un `update.sh` falso y la ruta se validó localmente contra
  un socket/admisión reales. **No** se ha probado el formulario HTTP completo en
  la VM ni el `update.sh` real. La bandera sigue apagada.
- Falta provisionar la clave/directorio, instalar la unidad endurecida y
  revisar SecOps del SHA final.
- La sesión y el origen siguen protegidos por el middleware existente; no se
  añade un segundo mecanismo. La confirmación de formulario no sustituye la
  reautenticación.
- La UI sigue deshabilitada por defecto; no hay despliegue.
