# Verificación de host sin privilegios — OPS4 (#443)

- **Fecha:** 2026-11-20.
- **Host:** Raspberry Pi de producción, usuario `pi` (uid 1000), **sin usar sudo,
  Docker, systemd, base de datos ni red**.
- **Alcance autorizado:** arnés aislado, sin tocar producción. No se autorizó
  fusionar, desplegar ni probar root/systemd.
- **Código del auxiliar:** `/opt/zascarr/zascarr/deploy/ops/zascarr_ops.py`
  (solo lectura).

## PASS

El arnés se ejecutó desde `/home/pi/ops4-harness` con un directorio temporal
propio y terminó con código 0:

| Caso | Resultado | Código |
|---|---|---|
| v1 `actualizar` con HMAC válido | rechazada | `accion_no_disponible` |
| JSON con claves duplicadas | rechazada | `esquema_invalido` |
| v2 `actualizar` | rechazada | `esquema_invalido` |

- `UNIDADES` solo contenía `copia` y `restaurar`; `actualizar` no existía.
- Cualquier intento de lanzar un subproceso hacía fallar el arnés; no se llamó a
  `systemctl`.
- El estado temporal quedó dentro del directorio del arnés y el repositorio de
  producción no se modificó (`git status` limpio, sin escritura).
- El arnés se eliminó de `/home/pi` al terminar.
- `/api/health` por LAN: **healthy** (DB, backup, restore y disco OK).

## Limitaciones y NOT RUN

- El usuario `pi` pertenece a los grupos `sudo` y `docker`; el arnés **no**
  invocó esos privilegios, pero no fue una identidad sin grupos privilegiados.
  No se usó `setpriv`/`runuser` porque exigían root.
- **NOT RUN:** unidad systemd real, Docker, PostgreSQL de producción, reinicios,
  fallos de `fsync`, actualización real, permisos de root y la Pi como entorno
  de ejecución del futuro actualizador.
- El arnés prueba la puerta actual, no una implementación futura.

### Límites de permisos observados (solo lectura)

| Ruta | Lectura | Escritura |
|---|---|---|
| `/opt/zascarr/zascarr` | sí | **no** |
| `/opt/zascarr/zascarr/.env` | **no** | no |
| `/var/backups/zascarr` | sí | **no** |
| `/var/run/docker.sock` | **sí** | **sí** |

El usuario `pi` pertenece al grupo `docker` y puede operar el socket, lo que en
la práctica equivale a privilegios elevados sobre los contenedores. El arnés
**no lo usó**, pero esta identidad no demuestra separación de privilegios. Una
prueba de contención real necesitaría un usuario sin ese grupo, un espacio de
nombres o un host separado. Las unidades instaladas son de copia/restauración y
auxiliar; no se observó ninguna de actualización. Esta comprobación no autoriza
usar Docker ni systemd.

## Conclusión

La puerta actual del auxiliar se comporta de forma cerrada en este host cuando
se ejecuta con el usuario `pi` y sin privilegios operativos. No cambia el estado
de #443: la actualización sigue deshabilitada y la PR #1159 continúa en borrador.
