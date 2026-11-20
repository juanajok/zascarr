# OPS4 — matriz de trazabilidad y evidencia

> Esta matriz conserva los FR/AC históricos de C-12. La política elegida de
> `main` y migraciones se describe en [el contrato nuevo](ops4-especificacion-main.md);
> la cobertura histórica no demuestra sus criterios.

## Alcance y lectura

Fuente normativa: [SPEC BL-OPS4](especificacion-BL-OPS4.md), especialmente §§2–7 y 9–10. La relación de abajo es trazabilidad de cobertura **propuesta**, no una declaración de cumplimiento: un AC puede cubrir solo parte de un FR y varios AC son compuestos. Se conservan los identificadores y escenarios existentes; no se inventan AC nuevos. La historia B sigue **NOT IMPLEMENTED**, sin habilitación ni autorización para Pi o producción. Una aprobación de SHA no certifica inocuidad, autoría ni revisión de seguridad; tampoco autoriza migraciones. La viabilidad SecOps no es autorización de activación.

**Estado de esta revisión:** 567 pruebas seleccionadas de OPS4 y paridad pasaron con el entorno virtual del proyecto. La suite completa se ejecutó en este SHA: 8045 passed, 2429 skipped (7 avisos); no sustituye las pruebas de host aislado. Esto no acredita los criterios compuestos ni prueba un host real. Los escenarios futuros de aceptación se marcan **NOT RUN**, también cuando exista una simulación parcial. Sin pruebas root, Docker, Postgres, systemd, Pi ni despliegue real en esta revisión.

## FR ↔ AC existentes

| FR | Criterios relacionados de la SPEC | Alcance y evidencia parcial, no cumplimiento |
|---|---|---|
| FR-01 | AC-01 | Gate del auxiliar probado por aserciones aisladas y una pasada de host sin privilegios en la Pi (sin systemd ni producción); unidad directa y UI futura pendientes. |
| FR-02 | AC-01, AC-07, AC-12 | Estados y ausencia de ejecución en UI pendientes. |
| FR-03 | AC-04, AC-11, AC-14 | Confirmación, sesión/origen y POST pendientes; AC-14 distingue aprobación del administrador. |
| FR-04 | AC-01, AC-05, AC-11 | Rechazo de versiones no implementadas en pruebas del gate; protocolo v3 y paridad completos pendientes. |
| FR-05 | AC-03, AC-09, AC-14, AC-15 | Modelo puro de identidad/vigencia/transiciones y formato canónico del registro A (sin emisión ni persistencia); no hay prueba de A durable ni de la unidad. |
| FR-06 | AC-04, AC-08, AC-09 | Exclusión, contraseña viva y lanzamiento fijo pendientes; el modelo no garantiza exclusión concurrente. |
| FR-07 | AC-06, AC-07, AC-13 | Lector sintético y arnés Git local son piezas experimentales, no receptor/exportador ni ejecución root segura. |
| FR-08 | AC-02, AC-06, AC-07, AC-12, AC-13 | Comparador de mapas y prueba de ref local son parciales; faltan procedencia, BD, copia y guardas integradas. |
| FR-09 | AC-06, AC-07, AC-10, AC-13 | Identidad de extremo a extremo y configuración fija en un despliegue pendientes. |
| FR-10 | AC-10, AC-13 | Identidad de imagen/contenedor y salud app/BD pendientes. |
| FR-11 | AC-09 | Recuperación manual y ausencia de rollback automático tras efectos pendientes. |
| FR-12 | AC-09, AC-15 | Clasificador puro conservador de `systemctl start` (código/estado/activo): no confunde fallo con ausencia de efectos; persistencia, reinicio y reconciliación host siguen pendientes. |
| FR-13 | AC-01–AC-15 | Propiedad transversal de fallo cerrado: cada escenario y sus fallos deben demostrarse; pruebas parciales no cierran el requisito. |

## Evidencia inspeccionada: límites de cada prueba

- [test_ops4_cliente_actualizacion.py](../../tests/test_ops4_cliente_actualizacion.py): paridad del constructor v3 y el verificador aislado, incluyendo UTF-8 y límites. El cliente no envía peticiones y el auxiliar actual rechaza v3; no prueba autenticación, confidencialidad, antigüedad ni antirreplay. La contraseña va en claro por el canal local propuesto y no debe registrarse.
- [test_ops4_solicitud_actualizacion.py](../../tests/test_ops4_solicitud_actualizacion.py): comprueba confirmación, modos de autenticación, reautenticación simulada y construcción de la petición tras OK. No hay transporte, socket ni llamada a unidad; la reautenticación real no se prueba aquí. La lectura de clave se limita a fichero regular sin seguir enlaces y se prueba con el formato del instalador, enlace y FIFO; no verifica propiedad ni modo del host.
- [test_ops4_transporte_actualizacion.py](../../tests/test_ops4_transporte_actualizacion.py): valida una respuesta cerrada de v3 con conversador simulado, timeout y fallo de transporte. No abre socket real ni está importado por web/API/main.
- [test_ops4_escritor_estado.py](../../tests/test_ops4_escritor_estado.py): publica JSON canónico con temporal exclusivo, fsync, rename y fsync del directorio; un fallo devuelve incierto y no se interpreta como éxito. No prueba durabilidad física, propiedad ni integración con el ejecutor.
- [test_ops4_fases_actualizacion.py](../../tests/test_ops4_fases_actualizacion.py): modelo puro de fases y transiciones; fallo antes de migrar es fallido, después puede ser incierto, y ningún terminal autoriza reintento. No persiste ni ejecuta.
- [test_ops4_flujo_actualizacion.py](../../tests/test_ops4_flujo_actualizacion.py): une en memoria la preparación de la app y la admisión del host, incluida repetición y caducidad. No hay socket, unidad, BD real ni ejecución; no acredita el contrato de red ni la persistencia.
- [test_ops4_admision_host.py](../../tests/test_ops4_admision_host.py): compone firma, frescura, reclamación y PBKDF2 con un lector simulado; una caída de BD y una contraseña incorrecta deniegan sin distinguirse. No hay socket, unidad ni persistencia real.
- [test_ops4_lector_credenciales.py](../../tests/test_ops4_lector_credenciales.py): comprueba la orden fija y el entorno cerrado del lector de BD con un ejecutor falso; no invoca Docker ni acredita identidad real del contenedor.
- [test_ops4_prueba_viva.py](../../tests/test_ops4_prueba_viva.py): compara PBKDF2 con un lector de credenciales inyectado, rechaza modos/hashes malformados y excepciones; no accede a la BD viva real ni demuestra identidad del operador.
- [test_ops4_admision_actualizar.py](../../tests/test_ops4_admision_actualizar.py): ordena esquema, firma, frescura, reclamación y prueba con callbacks inyectados; no ejecuta ni persiste. Una admisión correcta no sustituye la verificación viva, el cerrojo ni la unidad.
- [test_ops4_estado_actualizacion.py](../../tests/test_ops4_estado_actualizacion.py): lector informativo de JSON cerrado con ID correlacionado, límites y sin seguir enlaces; no acredita procedencia, éxito, durabilidad ni autoridad, y un estado activo sin noticias se vuelve incierto con el reloj de pared.

- [test_ops4_aislamiento.py](../../tests/test_ops4_aislamiento.py): barrera estática que impide que los módulos experimentales se importen desde `src/zascarr` o el auxiliar y busca ciertas cadenas de procesos, red, Docker y `update.sh`. También exige que los experimentos no hagan E/S ni persistan. No sustituye controles de ejecución ni revisa configuración del host.
- [test_ops4_estado_unidad.py](../../tests/test_ops4_estado_unidad.py): clasifica observaciones sintéticas de `systemctl start`; código no cero y estados inconsistentes son inciertos. No ejecuta systemd ni prueba el futuro ejecutor.
- [test_ops4_registro.py](../../tests/test_ops4_registro.py): serializa y valida una línea canónica de A con campos cerrados y ventana de 24 h, con mutaciones deterministas. La revisión posterior encontró tipos JSON que escapaban como `TypeError` y etiquetas distintas de `origin/main` que se aceptaban; se corrigieron con regresiones. La afirmación anterior de que ninguna entrada malformada escapaba era demasiado amplia: las muestras no son exhaustivas. La etiqueta fija no autentica el remoto ni una ref independiente; no escribe, no emite ni verifica firmas.
- [test_ops4_gate.py](../../tests/test_ops4_gate.py): llama a `procesar` con estado temporal y lanzador/subproceso prohibidos; comprueba rechazo de `actualizar` v1 con HMAC correcto, rechazo de esquema v2 y de versiones 3/4, y estado anterior intacto. La firma de v3 es ficticia, no HMAC v3 válido. También rechaza JSON con claves duplicadas, `v` booleano, exceso de tamaño y firma incorrecta de `actualizar`, sin lanzar subprocesos. No ensaya UI, systemd ni instalación.
- [test_ops4_inventario.py](../../tests/test_ops4_inventario.py): compara mapas sintéticos; comprueba cambios/bajas/modos protegidos, altas, rutas inseguras, allowlist y gate v3. El caso positivo solo dice `conforme` para mapas aportados; el test demuestra que dos mapas truncados iguales también pueden dar `conforme`. No prueba obtención, completitud ni sellado de P.
- [test_ops4_modelo.py](../../tests/test_ops4_modelo.py): simula en memoria reserva, consumo, incertidumbre, identidades y frontera de 24 horas, incluidos cambios horarios. Comprueba expresamente que dos reservas sobre el mismo objeto original son posibles sin cerrojo. **No es un registro de aprobación**, ni acredita exclusión, durabilidad, `fsync`, operador, sudo o reconciliación host.
- [test_ops4_objetos.py](../../tests/test_ops4_objetos.py): proveedor sintético en memoria de objetos commit/tree/blob; comprueba hashes, tipos, rutas, modos, límites y entradas malformadas. No usa Git ni red, y no prueba un snapshot instalado ni un receptor sin privilegios.
- [test_ops4_arnes_git.py](../../tests/test_ops4_arnes_git.py): crea repositorios locales efímeros y comprueba secuencialmente que una ref remota puede avanzar mientras el SHA capturado permanece; el entorno Git del arnés es aislado. No prueba un ejecutor, ni barreras concurrentes del flujo, ni que este se detenga.
- [test_ops4_identidad.py](../../tests/test_ops4_identidad.py): contrasta SHA aportados sintéticamente. La marca de fiabilidad procede del llamador; no acredita autenticidad, `fast-forward` ni autorización.
- [test_ops4_crash_model.py](../../tests/test_ops4_crash_model.py): simula resultados posibles de un renombrado sin sincronización y una puerta hipotética cerrada al arranque. No acredita persistencia física ni un mecanismo real de reconciliación.
- [test_ops4_ui_gate.py](../../tests/test_ops4_ui_gate.py): comprueba que Estado no pinta controles de actualización dentro de la sección de versión y que no existe una ruta POST ejecutable en el enrutador actual. No certifica una futura UI ni el comportamiento de autenticación. Los 503 de middleware no se usan como prueba de inexistencia.

## AC existentes: observables futuros

Todos los siguientes son **NOT RUN como aceptación integral**. Cada observable es una condición binaria mínima para el escenario; no sustituye las demás condiciones del AC ni las pruebas negativas, positivas y de fallos inyectados de la SPEC. Las evidencias parciales anteriores no los convierten en PASS.

| AC | Observable binario mínimo en entorno desechable | Cobertura parcial inspeccionada |
|---|---|---|
| AC-01 | Registro del shim de unidad vacío y UI sin acción, también ante invocación directa. | Gate de `procesar` solamente. |
| AC-02 | Remoto en T o inaccesible: resultado de rechazo y HEAD sigue en HEAD0. | Arnés muestra avance de ref, no rechazo. |
| AC-03 | Cada A inválida: auxiliar y unidad rechazan, sin efectos en código/BD. | Modelo valida algunas identidades, no A real. |
| AC-04 | Credencial/BD inválida: rechazo, ninguna unidad; centinela ausente de canales observables. | Sin prueba equivalente en estos archivos. |
| AC-05 | Petición firmada por miembro de grupo sin A o prueba real: ninguna unidad iniciada. | Gate v1 rechaza acción, no ejercita autorización v3. |
| AC-06 | Con barreras adversarias, resultado usa exclusivamente S o se detiene, sin mezcla ni avance por ref mutable. | Arnés local demuestra cambio de ref únicamente. |
| AC-07 | Cada alteración hostil se rechaza antes de build/avance y UI indica intervención; control positivo despliega S. | Comparador sintético cubre un subconjunto; no despliega. |
| AC-08 | Dos peticiones o cerrojo ocupado: como máximo una reserva/unidad y estado ajeno intacto. | Modelo demuestra que falta exclusión en memoria. |
| AC-09 | Tras cada corte/fallo inyectado, A reservada o consumida no reaparece libre; estado distingue no iniciado de efecto incierto o parcial y no hay reintento ni rollback. | Transiciones abstractas únicamente. |
| AC-10 | Solo se declara `hecha` si HEAD/snapshot, ID de imagen y contenedor, BD y salud corresponden a S. | Sin prueba integrada. |
| AC-11 | Peticiones malformadas/replay: rechazo sin secreto ni Docker/systemctl; paridad v1/v2. | Gate verifica casos concretos, no paridad completa. |
| AC-12 | Migración/revisión incompatible: bloqueo antes de backup/build/avance y sin `alembic upgrade`. | Comparador clasifica algunos cambios Alembic en mapas, no consulta BD. |
| AC-13 | Cambio ordinario compatible: despliegue exacto de S con P fijo y sin ejecución root de controles de S. | Comparador acepta cambio de bytes permitido, sin build ni despliegue. |
| AC-14 | Herramienta local con sudo y confirmación explícita del SHA completo emite A durable; variantes sin autoridad no la emiten. | No hay herramienta de emisión acreditada; modelo no la sustituye. |
| AC-15 | A válida se reserva una sola vez; límite 24 h, reloj, concurrencia y fallos durables bloquean hasta reconciliación y nueva aprobación. | Modelo prueba frontera y estados en memoria; no durabilidad ni concurrencia real. |

## Fuentes y pendientes de aceptación

- [SPEC BL-OPS4](especificacion-BL-OPS4.md): FR-01–13 (§3), AC-01–15 (§5), límites y puertas (§§6–7), tramos y contradicciones (§§9–10). Sus escenarios se reproducen aquí por identificador y observable resumido; el texto completo y vinculante es el de la SPEC.
- Tests reales: [gate](../../tests/test_ops4_gate.py), [inventario](../../tests/test_ops4_inventario.py), [modelo](../../tests/test_ops4_modelo.py), [objetos](../../tests/test_ops4_objetos.py), [arnés Git](../../tests/test_ops4_arnes_git.py).
- Para cerrar la puerta hacen falta las pruebas aisladas completas de §7 y §10, incluidas las contradicciones y casos ausentes de §10.1–10.2, revisión de seguridad y autorización expresa aparte. Root, Docker y systemd solo en aislamiento garantizado; una omisión es **NOT RUN**, nunca PASS. No conectar a producción ni usar Pi sin autorización separada.
