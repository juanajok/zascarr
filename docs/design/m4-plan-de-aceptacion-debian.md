# M4 — Plan de aceptación técnica del candidato en un Debian aislado (propuesta, 2.ª versión)

> **Estado: PROPUESTA documental, 2026-10-18 (segunda versión, tras la devolución de #226). No se ha ejecutado nada**: ninguna máquina virtual creada, ninguna
> descarga, ninguna instalación, actualización, restauración ni prueba de fallo, ninguna consulta de fuentes, ningún acceso a la Pi ni despliegue. Cubre #107 (M4) y
> #121 (instalar y actualizar), #122 (coste y esfuerzo) y #123 (restaurar y aceptar). **No cierra ni mueve ninguna tarjeta** y no autoriza código.
>
> **Resoluciones del responsable ya incorporadas (§10):** el entorno es una **máquina virtual Debian 12 desechable** (no Docker-en-Docker privilegiado sobre el equipo de
> trabajo); los **veinte casos M4-01…M4-20 son obligatorios** y cada uno debe tener una salida trazable; un FAIL **no** se acepta por adelantado; #143 se reproduce **por HTTP** y
> su conclusión exige envío íntegro y página correcta; no se autoriza todavía crear la VM ni descargar nada.
>
> **Esto es una propuesta de CAMBIO DE CONTRATO de M4** (las tarjetas dicen «en una Raspberry Pi») y **no extiende la decisión de #203**. El resultado se llamará
> **«aceptación técnica del candidato en Debian»**: **no** acredita hardware Raspberry, rendimiento ARM ni el esfuerzo humano de #122, y **no puede presentarse como aceptación completa
> de esas capacidades**.

## 1. Qué se propone y qué no

| Propone | No propone |
|---|---|
| Una **aceptación técnica** de un **candidato** (un commit concreto) en una **VM Debian 12 desechable**, con PostgreSQL real y datos sintéticos | Tocar la Pi de producción o cualquier biblioteca real |
| Reutilizar la evidencia existente donde su contrato coincide, y **repetir solo lo que falte** | Repetir por formalismo lo ya demostrado |
| Declarar por escrito qué **no** acredita un Debian x86-64 frente a la Pi (rendimiento ARM, tarjeta SD/NVMe, memoria real) | Llamar PASS a lo que el entorno no puede ver |
| Llevar **#143 como riesgo conocido** y reproducirlo por HTTP antes de decidir (§7) | Marcar #143 como resuelta, aceptarlo por adelantado ni tratarlo como un NOT RUN corriente |
| Fijar los **umbrales de #122 antes de medir** (§8) | Medir primero y poner el umbral después |

## 2. Candidato y versiones anteriores

| Dato | Valor | Comprobado |
|---|---|---|
| **Candidato fijado** | **`0a591d6f91a6b54f8cecb1e675afc59dc0290873`** (`main`, `git describe` = `v1.15.1-316-g0a591d6`; `pyproject.toml` sigue en `1.15.1`, **no hay etiqueta de versión posterior**). El artefacto es el árbol de ese commit y la imagen que construye su `Dockerfile`. **Los cambios documentales posteriores de este plan no lo sustituyen.** Si hace falta una corrección de producto, **habrá un candidato nuevo** y se decidirá qué evidencia debe repetirse | CI de `main` en `0a591d6`: suite unitaria, PostgreSQL real, build Docker y pip-audit correctos; ruff informativo en rojo (deuda #211) |
| **Esquema esperado** | cabeza de Alembic `20261009_0019_vinculacion_operaciones` (0019). `api/health.py` ya compara la versión de la base con la cabeza del código | `git ls-tree` de `alembic/versions` |
| **Versión anterior A (código)** | **`a5369ef`** (v1.15.1, la que corre en la Pi según el informe del 2026-10-14). **Entre `a5369ef` y el candidato no hay ninguna migración nueva** | `git diff --stat a5369ef 0a591d6 -- alembic` vacío |
| **Versión anterior B (migraciones)** | **`497e925`**: **dos migraciones por detrás** (0018 `alta_operaciones` y 0019 `vinculacion_operaciones`) | `git diff --stat 497e925 a5369ef -- alembic` |

**Las dos rutas se ejecutan desde instalaciones independientes**, cada una con su estado anterior documentado (commit, esquema, datos sembrados y huella de la biblioteca). **No se declara «soportada»
una versión por haberla elegido para el ensayo**: son versiones de partida del ensayo, nada más. Actualizar desde A prueba el procedimiento y la conservación pero **no ejercita ninguna migración**; solo B lo
hace, y un PASS de A no se presentará como prueba de migraciones.

## 3. Entorno: máquina virtual Debian 12 desechable (resolución D-2)

**Decisión del responsable:** **VM Debian 12 («bookworm») desechable**, con Docker y PostgreSQL **dentro** de ella. Se descarta Docker-en-Docker privilegiado directamente sobre el equipo de trabajo como
única frontera: `--privileged` concede todas las capacidades y acceso a los dispositivos del anfitrión y relaja el confinamiento, así que **no garantiza** que los efectos destructivos del ensayo (instalar como
administrador, llenar almacenamiento, restaurar sobre una base) queden dentro. La opción C (el ensayo actual, `docs/design/ui-baseline/ensayo.sh`) puede **reutilizarse para pruebas de aplicación**, **no para sustituir** el
ensayo de los scripts (`bootstrap.sh`, `update.sh`, `backup.sh`, `rollback.sh`).

### 3.1 Viabilidad previa (comprobación, no ejecución)
Antes de crear nada se comprueba **solo lectura** si este usuario puede usar **KVM** (`/dev/kvm` existe en el equipo; el acceso no se ha comprobado) y si `qemu-system-x86_64` arranca una VM sin privilegios. **Si KVM no está disponible, se detiene el
plan y se informa**: no se ejecuta silenciosamente en emulación por software ni en otra arquitectura, porque cambiaría lo que el ensayo acredita.

### 3.2 Origen, versiones y presupuesto de descarga (**no autorizado todavía**; se pide en el momento de ejecutar)

| Artefacto | Origen y versión propuestos | Verificación | Orden de magnitud (**no medido**) |
|---|---|---|---|
| Imagen de la VM | imagen oficial **Debian 12 «genericcloud» amd64** de `cloud.debian.org`, versión y fecha fijadas al autorizar | suma de comprobación publicada por Debian (SHA-512) | cientos de MB |
| Paquetes del sistema | repositorios de Debian 12 (`apt`): `git`, `curl`, `gzip` y lo que pida `bootstrap.sh` | firma de `apt` | decenas de MB |
| Docker y Compose | **a decidir (D-3b):** (i) el que instala `bootstrap.sh` (`curl -fsSL https://get.docker.com \| sh`, que **ejecuta un script remoto**), o (ii) `docker.io` + `docker-compose-plugin` de Debian ya instalados antes de la prueba | firma de `apt` / versión anotada | ~100–200 MB |
| Imágenes de contenedor | `postgres:15-alpine` y `python:3.11-slim-bookworm` (las de `docker-compose.yml` y `Dockerfile`) desde Docker Hub, **por digest anotado** | digest | ~100–200 MB |
| Dependencias de Python | `pip` desde PyPI al construir la imagen (las de `pyproject.toml` del candidato y de cada versión anterior) | versiones del `pyproject.toml` | cientos de MB |
| Código | el commit del candidato y de las versiones anteriores, **entregados a la VM como un `git bundle`** (sin acceso a GitHub desde la VM) | SHA del commit | decenas de MB |
Presupuesto de partida: **≤ 3 GB de descarga en total** y **≤ 25 GB de almacenamiento** en el anfitrión (ver §3.3). Si el trabajo real lo supera, se pide ampliación antes de seguir. **Solo imágenes, paquetes y código: nunca fuentes de tebeos ni contenido.**

### 3.3 Salvaguardas de la VM (se cumplen antes de ejecutar)

| Salvaguarda | Condición |
|---|---|
| **Sin nada del anfitrión** | La VM **no** comparte carpetas (sin 9p/virtiofs), **ni** discos físicos, **ni** USB, **ni** el socket de Docker del anfitrión, **ni** la biblioteca real ni carpetas personales. Se lanza **sin privilegios** y con `-nodefaults`. La entrada (el `git bundle` y la biblioteca sintética) entra por un disco virtual de solo lectura |
| **Docker dentro** | Docker, sus imágenes y todos sus volúmenes (PostgreSQL, biblioteca sintética, copias) viven **dentro de la VM** |
| **Recursos** | **2 vCPU, 4 GB de RAM** (la RAM de una Pi 4) y un disco virtual de **20 GB**; los topes del compose (**512 M** para la aplicación y para la base de datos) se comprueban como **efectivos** (§8) |
| **Almacenamiento acotado para presión de disco** | La presión de disco se hace **solo** sobre un **segundo disco virtual pequeño (2 GB)** montado dentro de la VM como destino de la copia o de los datos de prueba; llenarlo no puede consumir más que esos 2 GB del anfitrión. **Prohibido** llenar el disco raíz de la VM o del anfitrión |
| **Separación entre casos destructivos** | La VM parte de una **imagen base limpia con superposiciones (`qcow2` con *backing file*)**: cada grupo de casos destructivos usa **su propia superposición**, que se **descarta** al terminar. Se vuelve a un **punto de partida con instantánea** antes de cada caso destructivo (matar procesos, llenar el disco pequeño, corromper una copia, forzar una migración que falla) |
| **Red** | **Fase de obtención** (limitada a los orígenes de §3.2): la VM solo obtiene los artefactos autorizados. **Fase de ensayo**: **sin salida a Internet** (`restrict=on`); lo que un caso necesite del exterior se declara en el caso. Las **fuentes de tebeos permanecen apagadas** (valor por defecto desde la 0020 / ADR 0013 en instalaciones nuevas; una instalación que se **actualiza** con uso previo las conserva activas y hay que apagarlas en Ajustes) y **no se consulta ninguna**; la VM no ve la red local |
| **Condiciones de parada** | Se detiene la ejecución y se informa si: el anfitrión baja de **10 GB** libres; la VM supera su tope de RAM/CPU de forma sostenida; algo intenta acceder a una ruta o dispositivo del anfitrión; se detecta tráfico a un destino no autorizado; **el ensayo supera una ventana de tiempo acordada**; o aparece un FAIL de seguridad (§9 del guion: la biblioteca sintética cambia o se abre un puerto no previsto) |
| **Reproducibilidad** | Cada caso registra la **imagen y su suma**, el **commit**, la **instantánea** de partida, los **recursos** y la **red** de la fase |

## 4. Qué NO acredita un Debian x86-64 (se declara, no se resuelve)

- **Rendimiento en Raspberry Pi / ARM:** tiempos, memoria pico real, latencia de una tarjeta SD o un NVMe. El informe del 2026-10-14 (Pi 5, NVMe) midió confirmar 100 archivos en 0,29–0,30 s y el ensayo x86 dio casi lo mismo: **el margen no es extrapolable a una Pi 4 con SD**.
- **Compatibilidad de imágenes ARM64** y del instalador en Raspberry Pi OS (p. ej. el controlador de memoria desactivado por defecto: hallazgo 1 de ese informe).
- **Carga normal de la Pi** (Kavita, Transmission, Prowlarr activos), **reinicio de la máquina física**, **disco real casi lleno** en la Pi.
- **Fuentes reales, móviles físicos, lectores de pantalla.**
Todo ello permanece **NOT RUN** y **no pasa a PASS** por este plan. El informe de aceptación lo listará con ese nombre.

## 5. Matriz de aceptación

**Los veinte casos son obligatorios y cada uno debe cerrar con una salida trazable (PASS, FAIL o NOT RUN con su evidencia).** `REUTILIZAR` solo vale si la correspondencia de contrato es exacta (§5.1, §10.1); un caso con estado `HUECO` o `RIESGO CONOCIDO` se ejecuta como diagnóstico y **puede acabar en FAIL, lo que no equivale a aceptar el candidato** (§10.1).

**Leyenda de la evidencia.** `P` = prueba automática que ya existe y pasa en la CI de `main` (`0a591d6`) · `Pi` = ejecución en la Raspberry del 2026-10-13/14 sobre **`a5369ef`** (evidencia histórica de **otra versión** y otro entorno: orienta, no acredita este candidato) ·
`NUEVO` = hay que ejecutarlo en el entorno aislado · `HUECO` = **hoy el producto no lo hace o no lo demuestra**; no es un caso de ejecución sino un hallazgo (§6).

| # | Caso | Criterios de la tarjeta | Evidencia reutilizable (prueba · SHA · resultado) | Qué falta ejecutar | Estado inicial |
|---|---|---|---|---|---|
| M4-01 | **Instalación limpia** con `bootstrap.sh` del candidato, **sin terminal** (el instalador hace tres preguntas con valor por defecto y, sin terminal, usa el que ya hay; **hay que comprobar** que no queda ningún paso manual oculto) | #121.1, .2, .8 | `P`: `test_bootstrap_rutas` y `test_compose_env` (rutas y entorno) · `Pi`: instalación previa de otra versión | Ejecutar `bootstrap.sh` completo en el Debian aislado; registrar commit, imagen y URL | **NUEVO** |
| M4-02 | **Salud y esquema** tras instalar (`/api/health`, `/estado`) | #121.2 | `P`: `test_health`, `test_health_db_pg` (compara la versión de Alembic con la cabeza del código) · `Pi`: V-10 `database=ok` | Consultarlos sobre la instalación real y comprobar `alembic_version` = 0019 | **NUEVO** (con prueba que lo respalda). **Además:** comprobar que el tope de memoria del compose es **efectivo** (§8) |
| M4-03 | **Actualización A → candidato** (`update.sh` desde `a5369ef`; sin migraciones) | #121.3, .4 | `Pi`: `update.sh` en la Pi llevó producción de otra versión a `a5369ef` (informe «Contexto») | Instalar `a5369ef`, sembrar datos, actualizar, comparar estado antes/después | **NUEVO** |
| M4-04 | **Actualización B → candidato** (`update.sh` desde `497e925`; migraciones 0018 y 0019) | #121.3, .4 | `P`: `test_migracion_alta_pg`, `test_migracion_vinculacion_pg` (esquema por migración) | Instalar `497e925`, sembrar datos, actualizar, comprobar que las dos migraciones aplican y los datos sobreviven | **NUEVO** |
| M4-05 | **Conservación**: base de datos, configuración, archivos y vínculos intactos tras la actualización | #121.4 | `Pi`: V-14 y V-40 (manifiesto de la biblioteca idéntico antes/después) | Repetir: huella de la biblioteca (nombre, tamaño, fecha), recuentos de tablas y vínculos antes/después de M4-03 y M4-04 | **NUEVO** |
| M4-06 | **Fallo de migración recuperable**: forzar una migración que falla en un entorno de prueba | #121.6 | `update.sh` deja el SHA de rescate y el dump emparejado (lectura del script); **no hay prueba de que informe versión y paso fallido** | Provocar el fallo y observar el mensaje, el estado previo y la ruta de `rollback.sh` | **NUEVO** (puede acabar en HUECO) |
| M4-07 | **Presión de disco** al instalar, actualizar o respaldar | #121.5, #123.6 | **Ninguna.** No hay comprobación de espacio libre en `bootstrap.sh`, `update.sh`, `backup.sh` ni `rollback.sh`; solo `utils/cbz.py` mira el espacio, y para otra cosa | Limitar el espacio del destino (volumen de tamaño fijo) y observar qué ocurre, con qué mensaje y si se toca la colección | **HUECO** hasta observarlo (§6): se observa **conservación, mensaje y recuperación** |
| M4-08 | **Diagnóstico sin SQL**: entender el fallo y la acción desde `/estado` o el instalador | #121.7 | `P`: `test_diagnostico_red`; semáforos de `/estado` (V1/V9) | Revisar que en M4-06/M4-07 el mensaje se entiende sin SQL ni comandos no documentados | **NUEVO** |
| M4-09 | **Copia identificable**: versión y commit del candidato, versión del esquema, fecha, origen e identificador | #123.1 | **Ninguna.** `backup.sh` produce `backup_<TS>.sql.gz` y `update.sh` empareja `update_<TS>` con una referencia de git; **no se guarda ni el commit ni la versión del esquema** | Comprobar si, con el **procedimiento documentado** (incluido un **manifiesto externo asociado inequívocamente a la copia**), cada copia queda identificada de forma verificable (§6, H-2) | **HUECO de diseño**: caso a ejecutar |
| M4-10 | **Restauración** de una copia compatible con `rollback.sh` (con `--sha` y `--backup`) y verificación de salud, esquema, series, archivos y vínculos | #123.2, .3 | `Pi`: V-33/V-34 restauraron **con comandos explícitos** (`pg_dump`→`dropdb`→restaurar), **no** con `rollback.sh` (el propio guion lo dice) · `P`: ninguna ejercita `rollback.sh` | Ejecutar `update.sh` y `rollback.sh` reales; comprobar **compatibilidad y preservación del estado antes** de la restauración destructiva, y luego recuentos, salud y que el mismo token devuelve el mismo informe | **NUEVO** |
| M4-11 | **Rechazo de copias inválidas**: vacía, corrupta (`gzip -t`), de otra versión, sin tablas de ZascArr | #123.7 | Lectura de `verificar_dump` (vacío / corrupto) y del control de tablas de `rollback.sh` (`alembic_version`, `series`, `files`, `wishlist`); **sin pruebas** | Probar cada caso y registrar que no se presenta como completada y que el estado previo se conserva | **NUEVO**; «de otra versión» = **HUECO** (§6, H-3) |
| M4-12 | **Reinicio de contenedor/servicio** y recuperación | #121 (estado), #123.5 | `P`: `test_vinculacion_recuperacion_pg` (`SIGKILL` de un **proceso** que monta la `app` con `ASGITransport`, no un contenedor) — la propia reconciliación de #117 lo deja **NOT RUN** · `Pi`: V-30/V-31 con `docker kill` + `start` sobre `a5369ef` | **Ejecutar `docker kill`/`restart` del servicio real** en la VM, con una confirmación en vuelo y repetir el token; no basta con la prueba de procesos. **Los reinicios provocados forman parte del caso** y no cuentan como incumplimiento del umbral de reinicios (§8) | **NUEVO** (exigido: no se sustituye por la prueba de procesos) |
| M4-13 | **Operaciones reconocidas tras restaurar**: completadas, en curso, recuperables y fallidas, sin escanear la biblioteca | #123.4 | `P`: `test_vinculacion_resultado_pg` (#178), `test_vinculacion_recuperacion_pg` (#179), `test_u19_recorrido_pg` (T10: lectura del comprobante) · `Pi`: V-34 | Restaurar una copia que contenga informes y comprobar `leer_resultado` y el reenvío del token | Parcialmente `P`; **NUEVO** para el flujo con restauración |
| M4-14 | **Retención y purga** con tiempo controlado | #123 (retención) | `P`: #178 criterio 5 (token caducado sin informe, frontera exacta de 24 h) · #179 criterio 5 (purga con las dos condiciones) · U19 `test_t10l` (purga real a ambos lados del vencimiento, con la hora de la base) · U19 `test_t10h…k` (vencimiento lógico frente a purga física) | **Nada que ejecutar.** No se espera 24 h reales. Solo se **comprueba qué contrato cubre cada prueba** (§5.1) | **REUTILIZAR** |
| M4-15 | **Límites HTTP**: campo `token` en su máximo y un carácter más | #115 | `P`: `test_vinculacion_limite_pg::TestFronteraHTTP` y `test_tokens_vinculacion_limite` (#139) | — | **REUTILIZAR** (cubre el **campo `token`**) |
| M4-16 | **Límite HTTP: cuerpo entero excesivo** (p. ej. un JSON de varios MB) | #115 (parcial) | **Ninguna.** No hay límite de tamaño de cuerpo en `src/` (salvo la descarga de portadas); NFR-03 lo lista pendiente. El límite del campo `token` **no** prueba el cuerpo | **Definir antes** tamaño, formato, rutas, rechazo esperado y ausencia de efectos (§6, H-6); enviar solo cuerpos suficientes para demostrar el rechazo (no una carga ilimitada) y observar el rechazo y la ausencia de efectos | **NUEVO**, posible **HUECO** |
| M4-17 | **Riesgo #143** (cursor de página > 2.000): reproducción **por HTTP** | #115 (relacionado) | Medido hoy con la función real: un nombre de 255 bytes de caracteres de control da un cursor de **2.100** caracteres; con 63 emojis, 396; con 255 ASCII, 400. **No recorrido por HTTP** | §7: reproducir **por HTTP** con envío íntegro | **RIESGO CONOCIDO** |
| M4-18 | **Recorrido de varias páginas** con orden estable, sin omisiones ni duplicados | #118–#120 (decisión del 2026-10-18) | `P`: `test_asistente_vinculacion_pg` (paginación, borrador por página) y U20 `test_asistente_vinculacion_masivo_pg` (155 archivos, 2 páginas) · `Pi`: V-24, V-52 (cuatro páginas) | Recorrer un grupo de **>200** archivos (3 páginas) comprobando orden, ausencia de omisiones y duplicados | **NUEVO** (barato) |
| M4-19 | **Aislamiento y no-efectos** de toda la ejecución | DoD | `Pi`: V-40…V-43 | Repetir sobre la VM: la biblioteca sintética no cambia, no hay puertos extra, los logs no llevan rutas ni nombres, y **nada del anfitrión se ha tocado** (§3.3) | **NUEVO** |
| M4-20 | **Informe de aceptación** y decisión explícita | #121.8, #122.8, #123.8–.9 | Plantilla del §11 de `guion-validacion-pi-mvp.md` | Emitirlo al final | **NUEVO** |

### 5.1 Qué contrato cubre cada prueba de retención y purga (para M4-14)

| Prueba | Contrato que cubre | Lo que **no** cubre |
|---|---|---|
| #178 criterio 5 | Un token caducado **sin informe** responde `410 token_caducado`, con `puede_haberse_aplicado` falso antes de 24 h desde la firma y verdadero después; la frontera exacta | Que el informe se **borre** realmente |
| #179 criterio 5 | La purga exige **informe más antiguo que `RETENCION_HORAS` y token caducado** (las dos); −1 minuto no purga; con ambas, sí | Una purga que corra sola por el reloj real |
| U19 `test_t10l` | La **referencia de resultado** (`firma + 24 h`) y la **purga real** (con el reloj de PostgreSQL) son coherentes: una fila «casi 24 h» sobrevive, una «más de 24 h» se purga, y la lectura dice lo mismo | La retención más allá de ese contrato |
| U19 `test_t10h…k` | El vencimiento **lógico** manda sobre el **físico**; regenerar o leer la referencia no reinicia el plazo (reloj simulado en tres módulos) | El paso de 24 horas reales |

### 5.2 Lo que ya está resuelto en M2 y esta matriz no repite

La paridad entre el verificador del token y lo que ofrece la vista previa (#141, #142) ya está corregida y probada (#144, #146). **Un recorrido sistemático de todas las reglas del verificador sigue
siendo NOT RUN y opcional**, como dijo la reconciliación de #115.

## 6. Brechas del producto que este plan descubre (observar, no dispensar)

Son hallazgos de lectura, **no decisiones**. Se **observa el comportamiento existente antes de corregir**, una vez autorizado el ensayo. **Observar no es dispensar:** un FAIL de conservación o de restauración segura **bloquea la aceptación**
y **no** se convierte en «FAIL justificado». Corregir o aceptar una excepción es una decisión posterior sobre la evidencia, con candidato nuevo si cambia el producto.

| # | Hallazgo | Caso | Qué se observa y qué lo haría FAIL |
|---|---|---|---|
| H-1 | **No hay ninguna comprobación de espacio libre** en el instalador, la actualización, el backup ni el rollback | M4-07 | No tener un prechequeo **no demuestra por sí solo pérdida de datos**. Se observa **(a)** si la colección y la base quedan intactas, **(b)** el **mensaje** (¿explica la causa en español y propone una acción segura?) y **(c)** la **recuperación** (¿se puede repetir tras liberar espacio sin pasos ocultos?). FAIL si se pierde o se altera algo, o si presenta como completado lo que no lo está |
| H-2 | **Las copias no llevan metadatos** (commit, versión del esquema, origen, identificador) | M4-09 | La copia debe quedar **identificada de forma verificable**. Se admite **un manifiesto externo asociado inequívocamente al backup si forma parte del procedimiento documentado**; **no se exige necesariamente código nuevo**. FAIL si una copia no se puede identificar ni comprobar su compatibilidad con el procedimiento vigente |
| H-3 | `rollback.sh` valida que el fichero sea un `gzip` íntegro y que existan cuatro tablas, **no la compatibilidad** | M4-11 | **Compatibilidad y preservación del estado se comprueban antes de restaurar de forma destructiva.** Que el `gzip` sea íntegro no basta. FAIL si una copia incompatible se restaura sin aviso, o si el estado previo no se conserva |
| H-4 | El instalador no detecta el **controlador de memoria (cgroup)** desactivado | M4-01/02, §8 | **En la VM se comprueba que el tope se aplica de verdad** (§8). La particularidad de Raspberry Pi OS (el controlador desactivado por defecto) **permanece NOT RUN**: no se ve aquí |
| H-5 | **#143**: el cursor emitido puede superar el límite que acepta la propia petición | M4-17 | §7 |
| H-6 | **No hay límite de tamaño de cuerpo** en las rutas de escritura (solo el del campo `token`) | M4-16 | **Se define antes de enviar nada:** tamaño máximo a probar, formato, rutas, rechazo esperado y ausencia de efectos. Basta lo necesario para demostrar el rechazo; **no hace falta una carga ilimitada**. FAIL si se acepta, se bloquea el servicio o hay efectos |

## 7. Riesgo conocido: #143 (cursor de página)

**Estado:** defecto potencial **vigente** a nivel de servicio (medido: 2.100 > 2.000 con un nombre de 255 bytes de caracteres de control; 396 con 63 emojis; 400 con 255 ASCII), **sin reproducir por HTTP**. Es un riesgo, no un NOT RUN corriente.

**Reproducción (M4-17), solo en la VM:**
1. Un grupo de **>100** archivos de la biblioteca sintética cuyo **último de la primera página** (orden por nombre e id) tiene un nombre de 255 bytes de caracteres de control válidos en Linux; y otro con 63 emojis como control negativo.
2. Pedir la revisión de la vinculación y leer el cursor de «Página siguiente».
3. Enviar el cursor **íntegro, tal como lo emitió el sistema**, a `POST …/vinculacion/revisar` y a la API, y registrar la respuesta y que **no hay efectos**.

**Cómo se concluye (corregido):**
- **El fallo solo se considera descartado si el cursor viaja ÍNTEGRO, la petición se ACEPTA y devuelve la PÁGINA CORRECTA** (la siguiente en el orden estable, sin omisiones ni duplicados). Esa es la única evidencia que cumple el contrato del recorrido.
- **Un cursor truncado, recortado o alterado por otra capa NO demuestra un recorrido correcto** y puede perder la posición: se cuenta como defecto.
- **Un rechazo recuperable** (p. ej. `422` con un mensaje comprensible) demuestra **manejo del error**, **no cumplimiento del recorrido**: el sistema emitió un cursor que él mismo no acepta. **Se clasifica como defecto confirmado.**
- Si se confirma: **se conserva como defecto conocido** en el informe y **bloquea la aceptación de este candidato**. **La corrección o una excepción requerirán una decisión posterior sobre la evidencia; no se acepta por adelantado.** Si el producto cambia, habrá un candidato nuevo.

## 8. #122: umbrales (se acuerdan ANTES de medir)

| Métrica | Umbral (**aceptado por el responsable**) | Cómo se usa |
|---|---|---|
| Confirmar 100 archivos | **< 30 s**, sin errores ni `503` | Aprobado/rechazado. **En una VM x86-64 no acredita la Pi**: se marca «cumple en este entorno; Pi no medida» |
| Memoria | **topes efectivos de 512 M** (aplicación y base de datos, según `docker-compose.yml`): la medición queda **por debajo** de ellos | Aprobado/rechazado, **solo si el tope se aplica de verdad** (ver abajo) |
| OOM y reinicios | **cero OOM** y **cero reinicios INESPERADOS** durante las mediciones normales | Aprobado/rechazado. **Los reinicios provocados de M4-12 se registran como parte de ese caso**, no como incumplimiento |
| Memoria en reposo, CPU, E/S, duración de escaneo / propuesta / consulta | **sin umbral acordado** | **Informativo**, no aprobado ni rechazado (criterio #122.6) |
| Esfuerzo humano (tiempo por tarea, correcciones, ayudas) | **sin umbral** | **NOT RUN**: no hay persona de prueba. **No se cierra esa parte de #122 por inferencia** |

**Cómo se comprueba que el tope de memoria es efectivo (en la VM):** `docker inspect` del contenedor (límite de memoria no nulo y distinto del de la máquina) y el valor del cgroup (`memory.max`) de ese contenedor.
**Si el entorno no aplica el límite, la comprobación del presupuesto de memoria NO se da por PASS aunque el consumo observado sea bajo.** La comprobación del controlador de memoria **de Raspberry Pi OS** sigue siendo NOT RUN (§9).
Cualquier umbral nuevo (memoria en reposo, escaneo de un corpus, tamaño de biblioteca objetivo) lo aprueba el responsable **antes** de la ejecución; sin él, el dato es informativo.
El **corpus** es sintético, con contenido único y documentado (tamaño, formatos, duplicados, ambigüedades), como el del guion (321 archivos en la validación de la Pi).

## 9. Exclusiones (todo permanece NOT RUN; nada se convierte en PASS)

Rendimiento de Pi/ARM y de tarjeta SD · reinicio de la máquina física y disco lleno **reales** de la Pi · la particularidad de Raspberry Pi OS con el controlador de memoria · carga normal con Kavita/Transmission/Prowlarr · fuentes reales y su cobertura ·
móviles físicos · lectores de pantalla (se distingue el marcado probado de la verbalización no ejecutada) · esfuerzo humano medido con personas · producción. (La VM **sí** ejercita `systemd` y la instalación de Docker; el resto sigue fuera.)

## 10. Resoluciones del responsable (D-1…D-8) y cómo las recoge el plan

| Decisión | Resolución del responsable | Dónde queda recogida |
|---|---|---|
| **D-1** Cambio de contrato | Se acepta la **aceptación técnica del candidato en un Debian aislado**. **No acredita** hardware Raspberry, rendimiento ARM ni esfuerzo humano; esos límites impiden presentar el resultado como aceptación completa de esas capacidades | Cabecera, §4, §9 |
| **D-2** Entorno | **Opción B: VM Debian 12 desechable**, con Docker y PostgreSQL dentro. La opción C sirve para pruebas de aplicación, no para sustituir el ensayo de los scripts | §3 |
| **D-3** Descargas | El plan incluye orígenes, imágenes, versiones y presupuesto de descarga y almacenamiento; **la ejecución queda pendiente de autorización operativa. No se autorizan descargas todavía** | §3.2 (y D-3b: instalar Docker con el script remoto de `bootstrap.sh` o preinstalarlo desde Debian: **a decidir al autorizar**) |
| **D-4** Actualizaciones | **Ambas rutas, A y B, desde instalaciones independientes**, con estados anteriores documentados. No se declara soportada una versión por haberla elegido | §2 |
| **D-5** Brechas | **Observar antes de corregir**, una vez autorizado el ensayo. Un fallo de conservación o restauración segura **bloquea la aceptación**; no se dispensa llamándolo «FAIL justificado» | §6 |
| **D-6** #143 | **Reproducir por HTTP antes de decidir**; si se confirma, **defecto conocido**: corrección o excepción requerirán decisión posterior sobre la evidencia | §7 |
| **D-7** Umbrales | **< 30 s** (100 archivos), sin errores ni `503`; **topes efectivos de 512 M**; **cero OOM y cero reinicios inesperados**; el resto, informativo | §8 |
| **D-8** Obligatorios | **M4-01…M4-20 deben tener una salida trazable.** Los casos reutilizados requieren **correspondencia de contrato**; los diagnósticos de brechas pueden terminar en FAIL, pero **eso no equivale a aceptar el candidato** | §10.1 |

### 10.1 Qué significa «aceptado»

1. **Los veinte casos son obligatorios.** Cada uno termina en **PASS, FAIL o NOT RUN** con evidencia trazable (candidato, imagen, instantánea, resultado, enlace a la prueba o a la captura). **Un caso sin salida trazable cuenta como no ejecutado.**
2. **Un caso reutilizado (`P`) solo vale si su contrato coincide** con el criterio que se quiere acreditar: la matriz (§5) y §5.1 dicen qué cubre y qué **no** cubre; si la correspondencia no es exacta, el caso se ejecuta (NUEVO).
3. **El candidato se acepta técnicamente solo si no queda ningún FAIL** y los NOT RUN son únicamente los declarados en §9. **Un FAIL de conservación, de restauración segura, de migración, de presión de disco o de #143 bloquea la aceptación.**
4. **Un FAIL no se acepta por adelantado.** Cada uno se informa y se resuelve **después**, con una decisión sobre la evidencia: **corrección** (con **candidato nuevo** y repetición de la evidencia afectada) o **excepción explícita** del responsable, razonada y limitada.
5. Que los diagnósticos de brechas (H-1…H-6) puedan terminar en FAIL **no los convierte en aceptación**.
6. El informe final (M4-20) lleva la leyenda: **«aceptación técnica del candidato `0a591d6…` en Debian; no acredita Raspberry Pi/ARM, rendimiento real ni esfuerzo humano»**.

## 11. Límites de la fase de ejecución (cuando se autorice)

Solo dentro de la VM desechable y con datos sintéticos, cumpliendo las salvaguardas de §3.3 **antes** de empezar; sin tocar producción, la Pi, el equipo de trabajo fuera de la VM ni fuentes; las pruebas destructivas ocurren **únicamente allí**, cada una desde su instantánea y su superposición;
cada caso registra commit, imagen, resultado y evidencia; PASS, FAIL y NOT RUN se separan; **no se cambia código de producto para que un caso pase**; todo hallazgo de §6 se informa antes de corregir; si una condición de parada se cumple, se detiene y se informa.
**Esta propuesta no autoriza crear la VM, descargar imágenes, ejecutar scripts, corregir el producto, cambiar tarjetas ni desplegar.**
