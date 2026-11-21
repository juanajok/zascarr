# OPS4 — integración de UI (deshabilitada por defecto)

La pantalla `/estado` incorpora un formulario de actualización **solo** cuando
`OPS4_ACTUALIZACION_HABILITADA=true`. En el valor por defecto (`false`) se
conserva el botón `disabled` y la ruta responde 404 antes de leer la clave o
reautenticar. No se ha desplegado ni habilitado en producción.

## Configuración

- `OPS4_ACTUALIZACION_HABILITADA` (bool, `false`).
- `OPS4_AUTORIZACION_KEY_FILE` (por defecto `/var/lib/zascarr/ops4/autorizacion.key`).
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
- **897 pruebas OPS4/paridad** y suite completa **8905 passed / 2431 skipped /
  0 failed** verdes.

## Límites

- El auxiliar y las unidades ya están en la rama, pero **no instalados**; habilitar
  la UI contra un host sin ese servicio devolverá «no disponible». No se ha
  probado en la VM con el auxiliar real.
- Falta provisionar la clave/directorio, instalar la unidad endurecida y
  revisar SecOps del SHA final.
- La sesión y el origen siguen protegidos por el middleware existente; no se
  añade un segundo mecanismo. La confirmación de formulario no sustituye la
  reautenticación.
- La UI sigue deshabilitada por defecto; no hay despliegue.
