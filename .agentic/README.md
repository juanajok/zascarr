# Pipeline de ingeniería multiagente

Herramienta de desarrollo separada de ZascArr. El operador fija el ámbito y los controles; los agentes interpretan, proponen y revisan; el motor decide. No modifica el checkout, instala dependencias, hace push ni despliega. No se usa para acciones ofensivas.

## Instalación y prueba rápida

Requiere Linux/POSIX, Python 3.11+ y Git local. No hay `pip install` ni credenciales. Docker local es opcional. Desde la raíz:

```bash
export PYTHONPATH=.agentic PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s .agentic/tests -v
run=$(mktemp -d)/demo
python3 .agentic/examples/example.py "$run"
python3 -m pipeline --run "$run" delivery
```

Ese ejemplo **simula las respuestas de los agentes**; los checks RED/GREEN, las transiciones y los commits son reales. El mismo fixture con agentes DSH reales está documentado en el [informe de verificación](<../docs/design/agentic-verificacion.md>).

## Manual de operación

1. Copia el [manifiesto](<examples/manifest.json>) y la [política](<examples/policy.json>) **fuera** del directorio de ejecución. Quita secretos e información no autorizada, incluso de la petición y del contexto. `editable` autoriza un conjunto de archivos de texto rastreados en HEAD; `context` agrega archivos de solo lectura. No se toman cambios sin commit. Nunca pongas el driver del test o un control de evaluación en `editable`.
2. Ejecuta `python3 -m pipeline --run RUTA_NUEVA init --repo RUTA_REPO --manifest MANIFIESTO --policy POLITICA`. El directorio padre debe existir y ser de confianza. El motor no reutiliza un directorio de ejecución preexistente. Git de origen y política quedan fijados. Guarda el estado fuera de registros públicos; contiene código y partes de los prompts.
3. Ejecuta `python3 -m pipeline --run RUTA advance`. Si devuelve `pending`, extrae cada sobre con `python3 -m pipeline --run RUTA task ROL`. Solo la persona operadora debe tener acceso al almacén. Pasa a cada invocación su `prompt`, SHA y `context`, no la salida de otros jueces. Cada respuesta es un **objeto JSON payload**, no una modificación de un archivo ni una orden de shell. Lo incorpora `python3 -m pipeline --run RUTA submit ID < respuesta.json`. Este comando acepta una sola vez el ID actual; `fail ID` registra un fallo para reintento. Una tarea expira a los 15 minutos; la caducidad se aplica al hacer `advance` o incorporar una respuesta, no detiene un proveedor externo.
4. Repite `advance`. En `HUMAN_APPROVAL_REQUIRED` revisa objetivo, SPEC y SHA, y decide `python3 -m pipeline --run RUTA decide TOKEN accept --operator NOMBRE` (o `reject`). Un token de SPEC no aprueba la entrega. No hay bypass de gates. `cancel` descarta tareas pendientes; el operador cancela aparte procesos externos en vuelo.
5. `delivery` solo devuelve el candidato en `COMPLETED`; `status` no avanza. La entrega es el JSON con archivos y referencias más un commit verificable en `RUTA/git`; contiene **solo el ámbito**, no la historia completa del repo. Para inspeccionar el diff local: `git --git-dir=RUTA/git diff SHA_CANDIDATO^ SHA_CANDIDATO`. Revisa y aplica manualmente sobre la base adecuada. Verifica nuevamente tras integrar.

### Checkpoints y recuperación

Una operación escribe un checkpoint atómico y toma un cerrojo local `flock`. Tras reiniciar, usa la misma `RUTA` si ya existe `state.json`; no hagas otro `init`. Si una interrupción ocurrió antes del primer checkpoint, crea un run en una ruta nueva. `advance` reutiliza controles, resultados y objetos ya persistidos; un proceso interrumpido entre ejecución de prueba y escritura del checkpoint puede repetir esa prueba. Prepara solo controles sin efectos externos. Los objetos se identifican por SHA-256; la integridad no protege contra alguien que pueda reescribir a la vez el estado y sus referencias. No compartas el almacén con modelos ni agentes, ni lo sitúes en un FS de red que no cumpla el contrato de locking. `BLOCKED`, `FAILED` y `CANCELLED` no se publican; inicia un run nuevo tras corregir política/alcance o un error de infraestructura.

### Controles reales y perfiles

- `equals` compara el texto completo; `contains` busca una subcadena. Para pruebas del proyecto usa `docker`: `{"id":"pruebas","kind":"docker","image":"sha256:<ID local completo>","argv":["python","-B","-m","unittest"],"timeout":60}`. Es el operador quien suministra imagen y ejecutable confiables. Autoriza ese backend con `--allow-docker` **antes** del subcomando. No utiliza Docker remoto, pulls, red, volúmenes de imagen, logs del candidato ni secretos del host. El daemon tiene que ver el directorio de ejecución; no uses un `/tmp` privado que no sea visible desde él. Docker comparte kernel; usa un runner desechable si no confías en el código, y una VM cuando Docker no sea una frontera suficiente.
- El oráculo RED debe devolver el fallo esperado: en Docker reserva el código `42` **solo** para la aserción que representa ese comportamiento; un fallo genérico `1`, errores de infraestructura y timeouts no acreditan RED. El operador debe auditar el driver: el motor no verifica que el wrapper use el código correctamente. GREEN reejecuta todos los checks sobre el SHA candidato y pide corrección para un fallo normal. No hay una fase de refactor obligatoria ni autoría automática de tests independientes: el operador incorpora las comprobaciones al manifiesto. No uses `contains` como sustituto de tests funcionales.
- FAST evita el agente benchmarker; STANDARD lo incluye. QA y SECOPS siempre se requieren; algunos caminos de UI y el flag `ui` añaden UI/UX. HIGH_ASSURANCE incluye aprobación de SPEC y del candidato, además de bloqueo de hallazgos MEDIUM. Las rutas críticas elevan el mínimo y BRAIN solo puede aumentarlo. La detección por ruta es parcial; declara factores restantes en `risk`. Los checks de aplicación específicos (Playwright, axe, SAST, dependencias) no se ejecutan si no se declaran y cablean en un runner aislado. Usa el [UX Lab](<../uxlab/README.md>) para sus flujos de navegador en un entorno de prueba.
- **E/S: por defecto no; opt-in con `scratch`.** Sin `scratch`, el contenedor mantiene raíz y `/src` de solo lectura, sin red ni temporal escribible. Un check `docker` puede declarar `"scratch": true` (solo `true`) para recibir un tmpfs efímero en `/scratch` (`rw,noexec,nosuid,nodev,size=32m,uid=65534,gid=65534,mode=0700`; no queda como archivos al parar, aunque el host puede llevarlo a swap) con `HOME` y `TMPDIR` apuntando ahí. Ejemplo: `{"id":"procesos","kind":"docker","image":"sha256:…","argv":["python","-B","-m","pytest","-q"],"timeout":60,"scratch":true}`. Sirve para escritura, rename atómico y subprocesos dentro de **un** contenedor. `noexec` no impide ejecutar código interpretado y `--ipc=none` elimina `/dev/shm`: no es un sandbox. No habilita red, varios contenedores, base de datos, sockets del host ni migraciones reales, y no sustituye la suite del proyecto. No confundas este tmpfs con `Runner(scratch=...)`, que es el directorio del host donde se materializa el snapshot. Probado con Docker 29.10.0 rootful; en rootless, `userns-remap` o motores que ignoren `uid`/`gid`, `/scratch` puede quedar inaccesible y el check falla cerrado.
- **Evidencia en capas cuando el cambio toca E/S.** (1) oráculo puro con RED/GREEN, código sin E/S; (2) suite del proyecto en contenedor con dependencias y raíz de solo lectura; (3) prueba de procesos real en un entorno desechable. Con `scratch` y una sola imagen, la capa 3 puede entrar en el gate; si necesita servicios, red o varios contenedores, la ejecuta el operador fuera del runner y se adjunta al informe con comando, SHA y resultado, sin presentarla como check aprobado.
- **HIGH_ASSURANCE y MEDIUM.** Un MEDIUM confirmado bloquea la entrega aunque el resto esté en PASS. No es un defecto del gate: clasifica por impacto real. Si el riesgo es aceptable, pide la decisión humana vinculada al SHA o cambia el diseño; no rebajes la severidad para pasar. Un LOW o INFORMATIONAL debe seguir siendo verificablemente no bloqueante.

## Adaptación a harnesses

| Harness | Modalidad disponible | Verificación |
|---|---|---|
| DeepSeek Harness web 0.2.2-rc.5 | Subagentes + lote nativo mediante [script DSH](<pipeline/dsh_batch.js>); entrega/importación supervisada por el operador | Sesiones independientes y tres revisores en paralelo probados contra fixture sintético. La prueba no certifica capacidad de impedir todas las herramientas del preset; no usar el puente con contenido no autorizado o agentes con acceso al almacén. Headless/SDK de DSH pendientes, sin cambios de perfil. |
| Codex CLI 0.170.0 | Protocolo manual; `exec` ofrece salida estructurada y sandbox según su ayuda | CLI inspeccionada; integración autenticada pendiente. |
| Claude Code 2.1.261 | Protocolo manual; `--print` y control de herramientas documentados | CLI inspeccionada; integración autenticada pendiente. |
| OpenCode 1.19.6 | Protocolo manual genérico | No se pudo iniciar CLI (DBus/sandbox); adaptador nativo no verificado. |
| Otros | Un objeto por tarea, en proceso o sesión nueva; sin historial compartido | Protocolo portable. En un único contexto secuencial no hay independencia entre agentes; no equivale a la prueba DSH. |

En DSH, usa el cuerpo del [script de lote](<pipeline/dsh_batch.js>) en `functions.workflow`, con `args.tasks` como array de sobres `task` (máx. 3). Los roles del lote no reciben el resto del lote. El operador verifica la salida `{task_id, payload}`, aplica `submit` para cada payload válido y `fail` para las llamadas sin respuesta. La ruta `session-default` usa el modelo de sesión; una ruta explícita usa formato `proveedor/modelo` conocido por DSH. No se incluyen claves ni endpoints en el run. La etiqueta de modelo con `session-default` es una ruta solicitada, no prueba de identidad del modelo resuelto; el coste y tokens no observados son `null`.

## Extensión, métricas y CI

Para añadir un rol, decide si una regla determinista lo sustituye. Define prompt y permisos, contrato estricto en [contracts.py](<pipeline/contracts.py>), contexto mínimo y fase en [engine.py](<pipeline/engine.py>), y enrútalo en las políticas. Prueba entradas inválidas, regresión y fallo cerrado antes de declarar el rol obligatorio. Vuelve a ejecutar jueces contra la misma SPEC y nuevo SHA cuando el candidato cambie; el MVP no reutiliza aprobaciones entre SHAs.

El [workflow de CI](<../.github/workflows/agentic.yml>) ejecuta pruebas y ejemplo sin secretos ni proveedores, y un job separado ejecuta los canarios Docker con `python:3.11-slim-bookworm` fijada por digest y verificada por ID; no publica más que el resultado de fixtures sintéticos. Inicializa pruebas de proyecto en runner desechable, sin credenciales de despliegue y con `persist-credentials: false`. No vuelques sobres ni artefactos de proyectos privados en logs de CI. Activa protección de rama como decisión externa, no desde el motor.

El estado registra transiciones, hitos, intentos reservados, reintentos, outputs validados y medidas de runner. No aporta facturación, presupuestos duros de tokens, telemetría remota ni evidencia de retorno frente a un agente único. Consulta la [SPEC y benchmark](<../docs/design/agentic-mvp.md>) y el [ADR](<../docs/adr/0027-pipeline-ingenieria-local.md>) para alcance y límites.
