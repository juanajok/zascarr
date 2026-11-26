# SPEC: scratch escribible opt-in para checks Docker

Estado: v1.1 congelada tras revisión; respecto a v1 (2026-11-26) cambian el tmpfs a `uid/gid=65534,mode=0700` y las aserciones de endurecimiento, sin cambio funcional. Base: `.agentic/pipeline/runner.py` en el árbol de trabajo. Esta SPEC no se modifica para adaptarla al código. Revisión v1.1 (2026-11-26): se corrigieron las afirmaciones sobre swap, `noexec` y montajes del host, y el tmpfs pasó a `uid=65534,gid=65534,mode=0700` por mínimo privilegio. La aprobación de v1 no se reutiliza: QA y SECOPS revisaron el delta.

## Problema

El runner no puede acreditar E/S: `/src` y la raíz son de solo lectura y no hay directorio temporal. Un cambio con atomicidad, concurrencia o recuperación de procesos no puede tener un check real en el gate. Véase la [lección B1](<agentic-verificacion.md#lecciones-del-piloto-b1-informadas-por-el-operador>).

## Requisitos

- **R1.** Un check `docker` admite la clave opcional `scratch` con el valor booleano `true`. Cualquier otro valor, tipo o clave adicional se rechaza con `ValueError`. El campo no existe para `contains` ni `equals`.
- **R2.** Con `scratch: true`, el contenedor recibe un tmpfs en `/scratch` con opciones fijas `rw,noexec,nosuid,nodev,size=32m,uid=65534,gid=65534,mode=0700`, y las variables `HOME` y `TMPDIR` apuntan a `/scratch`. No se añade ninguna ruta del host (el snapshot sigue en `/src`, en solo lectura), no se publica red y no se reutiliza el directorio entre ejecuciones. Tmpfs se descarta con el contenedor; el host puede llevarlo a swap.
- **R3.** Sin `scratch`, el comando, el entorno y el resultado son idénticos a la versión anterior. Los checks existentes no cambian.
- **R4.** El resultado conserva exactamente `{passed, kind, exit_code, duration_ms}`. Un fallo de infraestructura, timeout o error de arranque sigue sin acreditar RED.
- **R5.** Pruebas: validación estricta del campo; construcción exacta de `--tmpfs` solo con opt-in y, en esa rama, presencia de `--read-only`, `--network=none`, `--user`, `--cap-drop=ALL`, `--ipc=none` y límites; canario real que escribe, hace un rename atómico, lanza un subproceso y comprueba que `/src` sigue sin ser escribible; segunda ejecución ve `/scratch` vacío. Si Docker no está autorizado, los canarios se omiten y se declara.

## Límites de seguridad

Docker comparte kernel con el host. El tmpfs consume memoria del contenedor (límite global 256 MiB), no queda como archivos tras parar el contenedor (aunque el host puede llevarlo a swap; no es una frontera de confidencialidad). `noexec` impide ejecutar binarios desde `/scratch`, pero no escribir archivos ni ejecutar código interpretado (`python /scratch/x.py`): es defensa en profundidad, no un sandbox. `--ipc=none` elimina `/dev/shm`, así que las pruebas que necesiten memoria compartida no funcionarán; `scratch` cubre ficheros y subprocesos, no IPC. Sigue sin haber red, capabilities, root ni rutas adicionales del host. Si el runner muere con SIGKILL, puede quedar un contenedor y su tmpfs acotado: se limpia con `docker ps -a --filter label=agentic.runner` y `docker rm --force` sobre el ID verificado. Esto habilita pruebas de E/S de **un** contenedor; no acredita servicios externos, base de datos, red, migraciones reales ni concurrencia entre contenedores. No sustituye la suite del proyecto ni una VM cuando la frontera importa.

## Aceptación

RED: las pruebas nuevas fallan en el árbol base (el campo `scratch` es rechazado y no se construye tmpfs). GREEN: suite del framework sin fallos, canarios reales en la imagen fijada por ID (escritura, rename atómico, subproceso, `/src` ro, `noexec`, segunda ejecución vacía y retirada del contenedor), Ruff limpio. Revisión independiente QA y SECOPS sobre el mismo SHA del candidato. La integración la hace el operador: el motor no edita su propio directorio oculto (guarda de automodificación).
