# OPS4 — auxiliar y unidad de actualización (rama, sin instalar)

Componentes **separados** del auxiliar de copias/restauración. No se instalan
ni habilitan en producción desde este cambio; el instalador existente no los
toca y la puerta de UI sigue apagada por defecto.

## Auxiliar

[zascarr_actualizar_aux.py](../../deploy/ops/zascarr_actualizar_aux.py) es
socket-activado, lee una línea v4 y:

1. Verifica esquema, HMAC de petición, frescura y cerrojo.
2. Verifica el testigo con `id_esperado` y consume el registro durable
   `consumidos/autorizacion-<id>`.
3. Solo entonces ordena `systemctl start --no-block
   zascarr-actualizar.service`, una unidad fija.
4. Devuelve una respuesta v4 cerrada. No ejecuta scripts ni acepta rama,
   rutas, entorno del cliente o shell.

La clave es `ops/actualizar.key` (dedicada, no `ops.key`) y el registro vive
en `ops4/consumidos`; ambos son root `0700/0440`. El auxiliar no abre red
salvo el socket de systemd (`AF_UNIX`), no registra el testigo y falla cerrado
si el cerrojo, el registro o el inicio no se pueden acreditar.

## Unidades

- `zascarr-actualizar.socket`: socket propio `ops/actualizar.sock`, `Accept=yes`,
  grupo del servicio, sin `[Install]`.
- `zascarr-actualizar@.service`: ejecuta el auxiliar con `python3 -I`, sin
  capacidades, `PrivateNetwork=yes`, `RestrictAddressFamilies=AF_UNIX`,
  `RuntimeMaxSec=45s`.
- `zascarr-actualizar.service`: `ExecStart` fijo
  `/bin/bash /opt/zascarr/zascarr/scripts/update.sh --rama main`,
  `RuntimeMaxSec=5400`, `Restart=no`, `KillMode=control-group`, escritura
  limitada a repo/datos/copias/cerrojo, sin `[Install]`.

## Pruebas

- [test_ops4_auxiliar.py](../../tests/test_ops4_auxiliar.py): 13 casos de
  aceptación única, unidad fija, replay, cerrojo, firma, caducidad, ligadura,
  fallo de inicio y clave inválida.
- [test_ops4_unidades.py](../../tests/test_ops4_unidades.py): 4 casos de
  contrato estático.
- [test_ops4_aislamiento.py](../../tests/test_ops4_aislamiento.py): el
  auxiliar no se importa desde web/API/main ni desde el auxiliar existente.
- **915 pruebas OPS4/paridad** y suite completa **8905 passed / 2431 skipped / 0 failed** verdes.

## Límites

- **No hay instalador de estas unidades todavía**; no se han copiado a
  systemd ni arrancado. No se ha probado en la VM el auxiliar real, el socket,
  la clave, el registro, el cerrojo ni el `update.sh` fijo.
- `zascarr-actualizar.service` ejecuta el actualizador real si se instala y
  arranca; por eso no tiene `[Install]` y no se instala desde
  `instalar_ops.sh`. No debe habilitarse en la Pi sin revisión SecOps.
- No se ha definido la rotación de la clave ni la cuota/retención del registro
  durable. La UI habilitada contra este host aún no se ha validado.
- La actualización sigue deshabilitada y sin despliegue.
