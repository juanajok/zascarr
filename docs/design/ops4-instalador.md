# OPS4 — instalador de clave, módulos y unidades

[instalar_actualizacion_ops4.sh](../../scripts/instalar_actualizacion_ops4.sh)
provisiona OPS4 **sin habilitar la UI ni activar el socket por defecto**.

## Comportamiento

- Crea `ops/actualizar.key` (32 bytes hex + LF, `0440 root:<grupo>`) solo si
  no existe; no la imprime ni la rota.
- Crea `ops4/consumidos` `0700` y copia el auxiliar, protocolo, verificador y
  registro durable a `/usr/local/lib/zascarr`.
- Sustituye `@ZASCARR_DATA_DIR@`/`@GRUPO@` e instala el socket y las unidades.
- **Sin `--activar` no habilita nada**: las unidades quedan en disco, sin
  `[Install]`, y la UI sigue con `OPS4_ACTUALIZACION_HABILITADA=false`.
- `--activar` **inicia** el socket (sin persistencia; no usa `enable`), no la
  UI. El mensaje advierte de que la unidad fija puede ejecutar `update.sh` si
  recibe una petición válida y de que la bandera de UI sigue en `false`.
  `--sin-systemd` evita systemd; `--dry-run` no escribe.
- `--quitar` retira unidades/módulos y conserva clave/datos; con
  `--borrar-clave` elimina también la clave.

## Pruebas

[test_instalar_ops4.py](../../tests/test_instalar_ops4.py): **6 casos** con
directorios temporales y `--sin-systemd`, sin tocar systemd, la Pi ni
producción. Verifican clave/modo, directorios, módulos, unidades sustituidas,
idempotencia, dry-run, retirada y argumentos inválidos.

## Validación real en la VM (2026-11-21)

Se ejecutó el instalador en un overlay desechable sin NIC, con 9p de solo
lectura para el repo y una clave precreada conocida. `--yes --activar`
conservó la clave, instaló módulos/unidades, activó el socket y mostró que la
UI seguía deshabilitada por defecto.

- Socket `LISTEN` en `/var/lib/zascarr/ops/actualizar.sock`.
- Clave existente conservada; modo/propietario comprobados.
- Petición v4: `{"resultado":"aceptada","codigo":"aceptada"}`.
- Unidad fija con `update.sh` falso: `Result=success`, `ExecMainStatus=0`,
  `inactive/dead`; marcador escrito.
- Segunda petición: `repetida`.
- QEMU terminó con código 0.

Evidencia privada: `instalador-ops4/run-01`. **No** se ejecutó `update.sh` real,
no se usó la Pi y no se activó la bandera de UI.

## Límites

- El instalador no se ha ejecutado en la Pi. La VM validó archivos, socket,
  auxiliar y unidad con script falso, no el actualizador real.
- No implementa rotación de clave, cuota/retención del registro ni
  configuración de la UI; no enciende `OPS4_ACTUALIZACION_HABILITADA`.
- La unidad de actualización ejecuta `update.sh` real si se activa; instalar
  y activar requieren la revisión SecOps y una ventana autorizada.
- Sin despliegue.
