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
- `--activar` habilita/inicia solo el socket; `--sin-systemd` permite probar
  la copia de archivos sin systemd; `--dry-run` no escribe.
- `--quitar` retira unidades/módulos y conserva clave/datos; con
  `--borrar-clave` elimina también la clave.

## Pruebas

[test_instalar_ops4.py](../../tests/test_instalar_ops4.py): **6 casos** con
directorios temporales y `--sin-systemd`, sin tocar systemd, la Pi ni
producción. Verifican clave/modo, directorios, módulos, unidades sustituidas,
idempotencia, dry-run, retirada y argumentos inválidos.

## Límites

- El instalador **no se ha ejecutado en la VM ni en la Pi**. La VM se
  provisionó manualmente; sus resultados están en
  [auxiliar/unidad](ops4-auxiliar-unidad.md).
- No implementa rotación de clave, cuota/retención del registro ni
  configuración de la UI; no enciende `OPS4_ACTUALIZACION_HABILITADA`.
- La unidad de actualización ejecuta `update.sh` real si se activa; instalar
  y activar requieren la revisión SecOps y una ventana autorizada.
- Sin despliegue.
