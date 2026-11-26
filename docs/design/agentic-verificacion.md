# Verificación del piloto multiagente — 2026-11-25

## Entorno

Checkout ZascArr en `f9d0cf76a78d087e2dcc37a3e15c0ead1c5b3d27`, rama del piloto UX Lab. Se preservó un borrador local no rastreado. Python host 3.14.4; 8 CPU lógicas, alrededor de 31 GiB de RAM total y 244 GiB libres al inspeccionar; no es una medición de Pi. Docker Engine local 29.10.0. Bubblewrap no puede crear namespaces en esta sesión; no se elevó privilegios. DSH web 0.2.2-rc.5, herramientas de subagentes y workflow confirmadas; OpenCode no inicia por DBus en este entorno. Los demás CLI y la matriz de capacidades se detallan en el [manual](<../../.agentic/README.md>). No se consultaron claves ni se modificaron perfiles.

## Evidencia observada

- `PYTHONPATH=.agentic python3 -m unittest discover -s .agentic/tests`: 45 casos, 43 pasan sin Docker y 2 canarios se omiten deliberadamente. Con `AGENTIC_DOCKER_TEST_IMAGE` fijada al ID local `sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39` (`python:3.11-slim-bookworm`), **45 pasan, sin omitidos**. Los canarios distinguen éxito, salida 1, timeout y retirada de contenedores. En Python 3.11 de esa imagen se ejecutaron además las 17 pruebas de contratos sin Docker. Lint Ruff pasa; el cuerpo DSH se validó como función async, que es el contrato de `functions.workflow`.
- Ejemplo final offline `16b57d8db32e469eae58a65f90cd1ba9`: `COMPLETED`; `equals` falló en baseline y pasó en `db54d52628d8fbf664418e9228fe3ce94afae196`. Se leyó el diff desde el Git privado. Siete respuestas simuladas; no se cuentan como llamadas al proveedor.
- DSH nativo `ead2556f738b4496ac5c908901658b1b`: BRAIN, BENCHMARKER, SPEC y DEVELOPER se ejecutaron en contextos separados; UI/UX, SECOPS y QA fueron invocados juntos en paralelo sobre `db54d52628d8fbf664418e9228fe3ce94afae196` y el mismo criterio `R1`. Se intercambiaron manualmente solicitudes/resultados del motor y herramientas nativas. El primer resultado de QA incluyó un string donde el contrato exige un objeto de finding; `submit` lo rechazó, emitió un ID nuevo y conservó los dos veredictos ya válidos. El segundo intento pasó con `QA-01` (LOW). Resultado `COMPLETED`, 8 intentos (`calls`), una ronda, 7 respuestas aceptadas, coste y tokens no observados. No hubo navegador ni escaneo de seguridad: revisión de solo la etiqueta sintética.
- Registro DSH: baseline `db23120dd8af95607c0b6a3b79bc725a082bbe68`; SPEC `b89060f66cec113ac87b1cd3ba05b119af9a8813d05a4b436cfff8d2f8c23753`; RED `f6f6cd3935366539368f58cb8d859e38307f636abb3e9e34f64731e5d44762f8`; GREEN `182fbdba99cd3adfdec535f6179e4aa50800028b20d93df6e5099bfa363a5bc6`; entrega `e69101cc678658ff68a1b10477be513b3d55087d4868e69f193bb6e3722e832c`. El artefacto local corresponde a `.tmp-agentic-dsh-run` y no está versionado.
- `QA-01` recomendó comprobar contenido exacto en vez de subcadena. El informe anterior se conserva: verificaba `contains`. Después se añadió `equals`, con una regresión que rechaza ausencia de LF, CRLF y bytes extra, y se reejecutó el flujo offline con oráculo exacto; no se presenta ese segundo flujo como otra revisión nativa.

- Suite existente de ZascArr (`PYTHONPATH=src`, temporales bajo checkout): 8.700 pasan, 2.471 omitidas, 23 fallan y 13 errores. El directorio largo e interno al checkout afectó, entre otros, sockets Unix y guardas del laboratorio; el filesystem local rechazó algunos nombres de fixture. Repetición de los seis módulos afectados con `--basetemp` corto y externo: 232 pasan y queda un fallo en `test_logs_persistidos.py::test_escribe_por_dia_y_filtra_por_fecha_hora_y_evento`, que usa fechas fijas en la ventana de retención. No se declara verde la suite del producto ni se modificó su lógica.

## Trazabilidad y separación de revisiones

| Criterio | Evidencia |
|---|---|
| P-01 | Reapertura después de guardar BRAIN, cancelación, caducidad y doble envío concurrente con un único resultado aceptado. No se recupera un `init` interrumpido antes del primer checkpoint. |
| P-02 | Contratos estrictos, alcance acotado, hashes, rechazo de edición de tests/políticas y de IDs obsoletos. El operador, no un rol, controla Docker, estado y transferencias. |
| P-03 | RED declarativo y GREEN en el ejemplo; canarios Docker y regresión que impide acreditar RED con salida 1 no diferenciada. Se requiere wrapper confiable que reserve 42 para el fallo esperado. |
| P-04 | Tres jueces en paralelo en fixture DSH, HIGH defensivo bloquea aunque todos los checks pasen y aprobación de SPEC no autoriza entrega. |
| P-05 | Rework con el candidato fallido y evidencia; reintentos y no progreso acotados; los tokens y coste no observados siguen desconocidos. |
| P-06 | Fixture positivo offline/nativo y negativos deterministas. No se ejecutó la matriz de productos completa. |

QA y SECOPS revisaron independientemente una instantánea privada de código `ba68187e652f8a855a3d8ce7d93e3c602609d392`. Sus hallazgos motivaron endurecer la evidencia RED Docker, añadir evidencia al rework, ligar las decisiones a referencias y retener y verificar los commits. Las correcciones quedaron en `db6ef6d494b4d937a56b021069f64bdce37f292d`. QA rerun independiente: 43 pasan y dos canarios omitidos; QA y SECOPS aceptaron únicamente el piloto sintético, supervisado y con checks declarativos, no fusión ni datos privados. En una comprobación adicional, el wrapper sintético Docker ejecutado sobre los dos snapshots dio RED `42`, GREEN `0` y error de preparación `1` ante archivo ausente; no amplía el dictamen independiente a Docker. Persiste que la identidad del operador no se autentica en el MVP: el token es de correlación, no una credencial. Las etiquetas de origen no certifican autoría. No se ofrece el puente de esta sesión para datos privados ni se sustituye el veredicto sobre el SHA real de una fusión con el SHA de un snapshot parcial.

## Lecciones del piloto B1 (informadas por el operador)

El operador informa de que B1 solo quedó acreditado combinando un oráculo puro, la suite del proyecto y una prueba de procesos real. Este informe no reproduce B1 ni verifica esa afirmación: la registra como lección de operación.

La consecuencia técnica es doble. En el momento de B1 el runner no podía acreditar E/S: `contains` y `equals` solo inspeccionan texto y el contenedor `docker` tenía raíz y `/src` de solo lectura, sin red ni scratch escribible, así que atomicidad, concurrencia, recuperación tras caída y estado entre procesos quedaban fuera. Y con `HIGH_ASSURANCE` cualquier hallazgo MEDIUM confirmado bloquea, también los que en STANDARD serían deuda: es intencional, no un defecto del gate.

### Scratch opt-in del runner (implementado el 2026-11-26)

Cambio: un check `docker` admite `"scratch": true` (solo ese valor) y recibe un tmpfs en `/scratch` con opciones fijas `rw,noexec,nosuid,nodev,size=32m,uid=65534,gid=65534,mode=0700`; `HOME` y `TMPDIR` apuntan ahí. Sin el campo, el comando es idéntico al anterior. [SPEC](<agentic-runner-scratch.md>), [manual](<../../.agentic/README.md>) y [código](<../../.agentic/pipeline/runner.py>).

- RED: antes de implementar, la prueba unitaria nueva falló porque el campo se rechazaba y el canario no podía escribir.
- GREEN: 47 pruebas con **3 canarios Docker** ejecutados con la imagen fijada por ID (`sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`); el nuevo canario comprueba `uid/gid=65534` y `mode=0700` reales, escritura, rename atómico, subproceso, `noexec` efectivo, `/src` no escribible y `/scratch` vacío en la siguiente ejecución; Docker 29.10.0 rootful. Ruff 0.17.4: `All checks passed`. RED previo: `test_scratch_is_opt_in...` falló con `AssertionError: False is not True` al rechazarse el campo; el canario figuraba omitido.
- Motor: E2E con el campo nuevo dio RED `42`, GREEN `0` y `COMPLETED`; la evidencia guardó los dos códigos.

Límites: habilita E/S de **un** contenedor; no hay red, servicios, base de datos, sockets del host ni concurrencia entre contenedores. El tmpfs se contabiliza contra el límite de memoria del contenedor, no queda como archivos al parar, pero el host puede llevarlo a swap; no es una frontera de confidencialidad. `noexec` no impide ejecutar código interpretado y `--ipc=none` elimina `/dev/shm`. Docker comparte kernel. La prueba sigue siendo responsabilidad del operador: el motor no verifica que el driver compruebe atomicidad de verdad.

QA y SECOPS revisaron el candidato `a5ce56ab5cee2f8a04d2f5a72f9c47561b51f980` (snapshot parcial) y dieron **PASS_WITH_WARNINGS**, sin bloqueantes. Sus advertencias se aplicaron: tmpfs con `uid`/`gid` y `mode=0700`, aserciones de endurecimiento en la rama con scratch, corrección de `noexec`, montajes del host, swap, `/dev/shm`, limpieza tras SIGKILL y distinción entre el tmpfs del check y `Runner(scratch=...)`. Los canarios reales, que ellos no ejecutaron, sí se ejecutaron aquí sobre el árbol vivo; la evidencia consta arriba. El snapshot de revisión incluye `engine.py` y `__main__.py` preexistentes solo para acreditar el cableado del campo; el cambio funcional es `runner.py`, y esos dos archivos no se modificaron en este incremento. SECOPS confirmó el correctivo de mínimo privilegio y advirtió de la dependencia de Docker rootful/userns, ya documentada; QA revisó el delta final.

## Subconjunto real del producto con scratch (2026-11-26)

Objetivo: comprobar que `scratch` sirve para una suite real sin red ni base de datos, no solo para el canario. Se eligió el módulo puro `src/zascarr/core/carpetas.py` y su suite `tests/test_core_carpetas.py` (**48 casos**). Se copiaron al snapshot únicamente `zascarr/__init__.py`, `zascarr/core/__init__.py`, `zascarr/core/carpetas.py` y `tests/test_core_carpetas.py`; `/src` sigue en solo lectura y pytest escribe en `/scratch`.

Imagen de pruebas: `python:3.11-slim-bookworm` (digest `sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39`) con `pytest==8.4.2`; ID local `sha256:f7a3d4b6743fead5225c26e58ccb1fdf12a2a9f2bc518ab293e633c90200c4f9`. Receta reproducible: `FROM python:3.11-slim-bookworm` + `pip install --no-cache-dir pytest==8.4.2`; no está versionada como Dockerfile, así que la reproducibilidad depende de esa receta y del digest base.

Resultado: `Runner` con `scratch: true` ejecutó `python -B -m pytest -q -p no:cacheprovider --basetemp=/scratch/pytest tests/test_core_carpetas.py` y devolvió `passed=true`, `kind=docker`, `exit_code=0`, 792 ms. El mismo subconjunto, en el host, da **48 passed**. Un E2E del motor con un check declarativo RED más esta suite como GREEN terminó en `COMPLETED` (6 intentos); el check de producto pasó con `0` en el candidato.

Límite: esto acredita que `scratch` funciona con una suite de producto **pura** y acotada. No acredita la suite completa: el runner solo materializa los archivos autorizados del manifiesto (hasta 64 rutas y 512 KB), así que un árbol de pruebas grande o con dependencias no encaja sin montar el repo, que no está implementado. Las pruebas con PostgreSQL, red o varios servicios siguen fuera del gate. La imagen de pytest no está fijada por digest propio ni se construye en CI.

## Límites de la evidencia y próximos criterios

Las pruebas de gate modelan un hallazgo defensivo HIGH y verifican que no se compensa con otros PASS; no reproducen ataques. El conjunto cubre fallos de control, violaciones de contrato, presupuesto, interrupción/rehidratación, evidencia alterada, concurrencia, revisión inválida y aprobación obsoleta. El ejemplo no certifica que una aplicación web esté lista para producción. Pendientes: matriz de proyectos real, pruebas independientes de navegador y de escáneres, aislamiento fuerte/credenciales por adaptador, conectores automáticos para otros harnesses, comparación coste/latencia y requisitos cubiertos frente a un agente y ejecución de CI remota. No se han desplegado cambios.
