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

El usuario `pi` pertenece al grupo `docker` y puede operar el socket. La
primera pasada **no lo usó**, pero esa identidad no demuestra separación de
privilegios. Las unidades instaladas son de copia/restauración y auxiliar; no
se observó ninguna de actualización. Esta comprobación no autoriza usar Docker
ni systemd.

### Repetición en sandbox sin grupos privilegiados

Se repitió el arnés con **bubblewrap 0.12.0**:

```text
bwrap --unshare-all --die-with-parent --ro-bind / / --dev /dev --proc /proc   --tmpfs /tmp --bind <temporal> /tmp/ops4 --setenv OPS4_TMP /tmp/ops4   --chdir /home/pi/ops4-harness python3 /home/pi/ops4-harness/ops4_host_unprivileged.py
```

Dentro del sandbox: `uid=1000(pi)`, grupos solo `1000(pi),65534(nogroup)`,
sin red y con `/` de solo lectura; solo el directorio temporal era escribible.
Resultado: los tres casos volvieron a ser rechazados, `UNIDADES` solo tenía
`copia`/`restaurar` y no se lanzó ningún subproceso. El sandbox reduce la
superficie de esta prueba, pero **no es una validación de systemd, Docker,
PostgreSQL ni de la durabilidad**; esos siguen NOT RUN.

## Conclusión

La puerta actual del auxiliar se comporta de forma cerrada en este host cuando
se ejecuta con el usuario `pi` y sin privilegios operativos. No cambia el estado
de #443: la actualización sigue deshabilitada y la PR #1159 continúa en borrador.


## systemd: unidad transitoria y unidades reales

Con autorización expresa se usó `sudo` para una prueba **sin instalar nada**:

- `systemd-run --unit=zascarr-ops4-test-<epoch> --collect --wait   --property=Type=oneshot --property=NoNewPrivileges=yes ...`
- Resultado: `Result=success`, `ActiveState=inactive`, `SubState=dead`;
  la unidad quedó retirada y el marcador temporal se borró con `sudo`.
- No se arrancó, paró ni modificó ZascArr, su socket, Docker, PostgreSQL ni
  ninguna unidad de producción.

Revisión de solo lectura de las unidades instaladas:

- `zascarr-ops@.service`: `NoNewPrivileges=yes`, `ProtectSystem=strict`,
  `PrivateNetwork=yes`, `CapabilityBoundingSet=` vacío; `ReadWritePaths` solo
  incluye `/var/lib/zascarr/backup-status` y `/run/zascarr-ops`.
- `zascarr-ops.socket`: `SocketUser=root`, `SocketGroup=media`, modo `0660`.
- `zascarr-restaurar@.service`: `User=root`, `ProtectSystem=strict`,
  `CapabilityBoundingSet=` vacío.
- No existe una unidad de actualización instalada.

`/opt/zascarr/zascarr/.env` es un **enlace simbólico** con modo 777 que apunta a
`/opt/zascarr/.env`, cuyo fichero real es `root:root 600`; `pi` no puede leerlo.
El modo 777 del enlace no expone el contenido.

**NOT RUN:** iniciar una unidad de actualización (no existe), reinicios reales,
Docker/PostgreSQL de producción, fallos de `fsync` y actualización de punta a
punta. La prueba transitoria acredita que systemd funciona y que las unidades
existentes están instaladas; no acredita el futuro ejecutor.
