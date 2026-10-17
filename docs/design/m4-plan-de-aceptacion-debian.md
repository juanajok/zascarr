# M4 — Plan de aceptación del candidato en un Debian aislado (propuesta)

> **Estado: PROPUESTA documental, 2026-10-18. No se ha ejecutado nada**: ninguna instalación, actualización, restauración, prueba de fallo, consulta
> de fuentes, acceso a la Pi ni despliegue. Cubre #107 (M4) y sus historias #121 (instalar y actualizar), #122 (coste y esfuerzo) y #123 (restaurar y
> aceptar). **No cierra ni mueve ninguna tarjeta** y no autoriza código. El siguiente paso es que el responsable apruebe este plan (§10); después se
> autorizará su ejecución aislada con objetivos y límites concretos.
>
> **Esto es una propuesta de CAMBIO DE CONTRATO de M4.** Las tres tarjetas dicen «en una Raspberry Pi». Aquí se propone sustituir la Pi por un Debian
> aislado como entorno de aceptación, y separar expresamente lo que eso **no** acredita. **No es una extensión automática de la decisión de #203**
> (que se limitó a la validación emulada de la interfaz móvil): se somete a aprobación por separado.

## 1. Qué se propone y qué no

| Propone | No propone |
|---|---|
| Aceptar un **candidato** (un commit concreto) en un **Debian 12 aislado**, con PostgreSQL real y datos sintéticos | Tocar la Pi de producción o cualquier biblioteca real |
| Reutilizar la evidencia existente donde su contrato coincide, y **repetir solo lo que falte** | Repetir por formalismo lo ya demostrado |
| Declarar por escrito qué **no** acredita un Debian x86-64 frente a la Pi (rendimiento ARM, tarjeta SD/NVMe, memoria real) | Llamar PASS a lo que el entorno no puede ver |
| Llevar **#143 como riesgo conocido** con decisión explícita antes de aceptar (§7) | Marcar #143 como resuelta ni como un NOT RUN corriente |
| Fijar los **umbrales de #122 antes de medir** (§8) | Medir primero y poner el umbral después |

## 2. Candidato y versión anterior soportada

| Dato | Propuesta | Comprobado |
|---|---|---|
| **Candidato** | un **commit de `main` fijado al aprobar este plan** (hoy `0a591d6`, `git describe` = `v1.15.1-316-g0a591d6`; `pyproject.toml` sigue en `1.15.1`, **no hay etiqueta de versión posterior**). El artefacto es el árbol de ese commit y la imagen que construye su `Dockerfile` | CI de `main` en `0a591d6`: suite unitaria, PostgreSQL real, build Docker y pip-audit correctos; ruff informativo en rojo (deuda #211) |
| **Esquema esperado** | cabeza de Alembic `20261009_0019_vinculacion_operaciones` (0019). `api/health.py` ya compara la versión de la base con la cabeza del código | `git ls-tree` de `alembic/versions` |
| **Versión anterior A (código)** | **`a5369ef`** (v1.15.1, la que corre en la Pi según el informe del 2026-10-14). **Entre `a5369ef` y el candidato no hay ninguna migración nueva** (`git diff` de `alembic/` vacío) | `git diff --stat a5369ef <candidato> -- alembic` |
| **Versión anterior B (migraciones)** | **`497e925`**: **dos migraciones por detrás** (0018 `alta_operaciones` y 0019 `vinculacion_operaciones`). Es el salto que `update.sh` hizo de verdad en la Pi | `git diff --stat 497e925 a5369ef -- alembic` |

**Consecuencia para la matriz:** actualizar desde A prueba el procedimiento y la conservación, pero **no ejercita ninguna migración**; solo B lo hace. Por eso se proponen
**las dos** rutas. Un «PASS» de la ruta A no se presentará como prueba de migraciones.

## 3. Entorno propuesto (decisión E-1)

Lo que se debe poder ejecutar: `bootstrap.sh` (instalación), `scripts/update.sh`, `scripts/backup.sh`, `scripts/rollback.sh` y el reinicio de contenedores, sobre **PostgreSQL real**
y una biblioteca **sintética**. Los scripts asumen un host con Docker Compose, un usuario de servicio y rutas del sistema; `bootstrap.sh` instala Docker si falta y arranca servicios.

| Opción | Qué es | Fidelidad | Coste y requisitos | Límite |
|---|---|---|---|---|
| **A (recomendada)** | Un contenedor **Debian 12 «bookworm»** con **Docker-en-Docker** y red propia, sin puertos al exterior; dentro se ejecutan los scripts reales y se levanta la pila | Alta para los scripts y el compose; baja para `systemd` (no hay timer de backup: se ejecuta `backup.sh` a mano) | El equipo ya tiene Docker 29.8 sin modo *rootless* y `python:3.11-slim-bookworm` en local. Necesita un contenedor **privilegiado** para el Docker interior y **descargar** la imagen del Docker-en-Docker (**descarga: requiere autorización**) | No prueba la instalación de Docker por `apt` ni el temporizador de `systemd` |
| **B** | Una **máquina virtual Debian 12** (`qemu` está instalado y `/dev/kvm` existe; **el acceso de este usuario no se ha comprobado**) | La más alta: `systemd`, `apt`, instalación real de Docker | Hay que **descargar una imagen de Debian** (autorización), más tiempo y disco | Más lenta de preparar; sigue siendo x86-64 |
| **C** | Solo el ensayo actual (`docs/design/ui-baseline/ensayo.sh`: compose aislado con PostgreSQL y datos sintéticos) | **No ejercita** `bootstrap.sh`, `update.sh`, `backup.sh` ni `rollback.sh` | Nulo | Insuficiente para #121 y #123: lo único que acreditaría son pruebas de aplicación |

**Recomendación:** **A**, y dejar **B** como ampliación solo si el responsable exige la instalación de Docker por `apt` o el temporizador. **Producción y la Pi quedan fuera de la ejecución.**
Todas las pruebas destructivas (matar procesos, llenar un disco, corromper una copia) ocurren **solo dentro** de ese Debian aislado, sobre datos sintéticos.

## 4. Qué NO acredita un Debian x86-64 (se declara, no se resuelve)

- **Rendimiento en Raspberry Pi / ARM:** tiempos, memoria pico real, latencia de una tarjeta SD o un NVMe. El informe del 2026-10-14 (Pi 5, NVMe) midió confirmar 100 archivos en 0,29–0,30 s y el ensayo x86 dio casi lo mismo: **el margen no es extrapolable a una Pi 4 con SD**.
- **Compatibilidad de imágenes ARM64** y del instalador en Raspberry Pi OS (p. ej. el controlador de memoria desactivado por defecto: hallazgo 1 de ese informe).
- **Carga normal de la Pi** (Kavita, Transmission, Prowlarr activos), **reinicio de la máquina física**, **disco real casi lleno** en la Pi.
- **Fuentes reales, móviles físicos, lectores de pantalla.**
Todo ello permanece **NOT RUN** y **no pasa a PASS** por este plan. El informe de aceptación lo listará con ese nombre.

## 5. Matriz de aceptación

**Leyenda de la evidencia.** `P` = prueba automática que ya existe y pasa en la CI de `main` (`0a591d6`) · `Pi` = ejecución en la Raspberry del 2026-10-13/14 sobre **`a5369ef`** (evidencia histórica de **otra versión** y otro entorno: orienta, no acredita este candidato) ·
`NUEVO` = hay que ejecutarlo en el entorno aislado · `HUECO` = **hoy el producto no lo hace o no lo demuestra**; no es un caso de ejecución sino un hallazgo (§6).

| # | Caso | Criterios de la tarjeta | Evidencia reutilizable (prueba · SHA · resultado) | Qué falta ejecutar | Estado inicial |
|---|---|---|---|---|---|
| M4-01 | **Instalación limpia** con `bootstrap.sh` del candidato, **sin terminal** (el instalador hace tres preguntas con valor por defecto y, sin terminal, usa el que ya hay; **hay que comprobar** que no queda ningún paso manual oculto) | #121.1, .2, .8 | `P`: `test_bootstrap_rutas` y `test_compose_env` (rutas y entorno) · `Pi`: instalación previa de otra versión | Ejecutar `bootstrap.sh` completo en el Debian aislado; registrar commit, imagen y URL | **NUEVO** |
| M4-02 | **Salud y esquema** tras instalar (`/api/health`, `/estado`) | #121.2 | `P`: `test_health`, `test_health_db_pg` (compara la versión de Alembic con la cabeza del código) · `Pi`: V-10 `database=ok` | Consultarlos sobre la instalación real y comprobar `alembic_version` = 0019 | **NUEVO** (con prueba que lo respalda) |
| M4-03 | **Actualización A → candidato** (`update.sh` desde `a5369ef`; sin migraciones) | #121.3, .4 | `Pi`: `update.sh` en la Pi llevó producción de otra versión a `a5369ef` (informe «Contexto») | Instalar `a5369ef`, sembrar datos, actualizar, comparar estado antes/después | **NUEVO** |
| M4-04 | **Actualización B → candidato** (`update.sh` desde `497e925`; migraciones 0018 y 0019) | #121.3, .4 | `P`: `test_migracion_alta_pg`, `test_migracion_vinculacion_pg` (esquema por migración) | Instalar `497e925`, sembrar datos, actualizar, comprobar que las dos migraciones aplican y los datos sobreviven | **NUEVO** |
| M4-05 | **Conservación**: base de datos, configuración, archivos y vínculos intactos tras la actualización | #121.4 | `Pi`: V-14 y V-40 (manifiesto de la biblioteca idéntico antes/después) | Repetir: huella de la biblioteca (nombre, tamaño, fecha), recuentos de tablas y vínculos antes/después de M4-03 y M4-04 | **NUEVO** |
| M4-06 | **Fallo de migración recuperable**: forzar una migración que falla en un entorno de prueba | #121.6 | `update.sh` deja el SHA de rescate y el dump emparejado (lectura del script); **no hay prueba de que informe versión y paso fallido** | Provocar el fallo y observar el mensaje, el estado previo y la ruta de `rollback.sh` | **NUEVO** (puede acabar en HUECO) |
| M4-07 | **Presión de disco** al instalar, actualizar o respaldar | #121.5, #123.6 | **Ninguna.** No hay comprobación de espacio libre en `bootstrap.sh`, `update.sh`, `backup.sh` ni `rollback.sh`; solo `utils/cbz.py` mira el espacio, y para otra cosa | Limitar el espacio del destino (volumen de tamaño fijo) y observar qué ocurre, con qué mensaje y si se toca la colección | **HUECO** hasta observarlo (§6) |
| M4-08 | **Diagnóstico sin SQL**: entender el fallo y la acción desde `/estado` o el instalador | #121.7 | `P`: `test_diagnostico_red`; semáforos de `/estado` (V1/V9) | Revisar que en M4-06/M4-07 el mensaje se entiende sin SQL ni comandos no documentados | **NUEVO** |
| M4-09 | **Copia identificable**: versión y commit del candidato, versión del esquema, fecha, origen e identificador | #123.1 | **Ninguna.** `backup.sh` produce `backup_<TS>.sql.gz` y `update.sh` empareja `update_<TS>` con una referencia de git; **no se guarda ni el commit ni la versión del esquema** | — (no es un caso de ejecución) | **HUECO de diseño** (§6) |
| M4-10 | **Restauración** de una copia compatible con `rollback.sh` (con `--sha` y `--backup`) y verificación de salud, esquema, series, archivos y vínculos | #123.2, .3 | `Pi`: V-33/V-34 restauraron **con comandos explícitos** (`pg_dump`→`dropdb`→restaurar), **no** con `rollback.sh` (el propio guion lo dice) · `P`: ninguna ejercita `rollback.sh` | Ejecutar `update.sh` y `rollback.sh` reales; comprobar recuentos, salud y que el mismo token devuelve el mismo informe | **NUEVO** |
| M4-11 | **Rechazo de copias inválidas**: vacía, corrupta (`gzip -t`), de otra versión, sin tablas de ZascArr | #123.7 | Lectura de `verificar_dump` (vacío / corrupto) y del control de tablas de `rollback.sh` (`alembic_version`, `series`, `files`, `wishlist`); **sin pruebas** | Probar cada caso y registrar que no se presenta como completada y que el estado previo se conserva | **NUEVO**; «de otra versión» = **HUECO** (§6) |
| M4-12 | **Reinicio de contenedor/servicio** y recuperación | #121 (estado), #123.5 | `P`: `test_vinculacion_recuperacion_pg` (`SIGKILL` de un **proceso** que monta la `app` con `ASGITransport`, no un contenedor) — la propia reconciliación de #117 lo deja **NOT RUN** · `Pi`: V-30/V-31 con `docker kill` + `start` sobre `a5369ef` | **Ejecutar `docker kill`/`restart` del servicio real** en el Debian aislado, con una confirmación en vuelo y repetir el token; no basta con la prueba de procesos | **NUEVO** (exigido: no se sustituye por la prueba de procesos) |
| M4-13 | **Operaciones reconocidas tras restaurar**: completadas, en curso, recuperables y fallidas, sin escanear la biblioteca | #123.4 | `P`: `test_vinculacion_resultado_pg` (#178), `test_vinculacion_recuperacion_pg` (#179), `test_u19_recorrido_pg` (T10: lectura del comprobante) · `Pi`: V-34 | Restaurar una copia que contenga informes y comprobar `leer_resultado` y el reenvío del token | Parcialmente `P`; **NUEVO** para el flujo con restauración |
| M4-14 | **Retención y purga** con tiempo controlado | #123 (retención) | `P`: #178 criterio 5 (token caducado sin informe, frontera exacta de 24 h) · #179 criterio 5 (purga con las dos condiciones) · U19 `test_t10l` (purga real a ambos lados del vencimiento, con la hora de la base) · U19 `test_t10h…k` (vencimiento lógico frente a purga física) | **Nada que ejecutar.** No se espera 24 h reales. Solo se **comprueba qué contrato cubre cada prueba** (§5.1) | **REUTILIZAR** |
| M4-15 | **Límites HTTP**: campo `token` en su máximo y un carácter más | #115 | `P`: `test_vinculacion_limite_pg::TestFronteraHTTP` y `test_tokens_vinculacion_limite` (#139) | — | **REUTILIZAR** (cubre el **campo `token`**) |
| M4-16 | **Límite HTTP: cuerpo entero excesivo** (p. ej. un JSON de varios MB) | #115 (parcial) | **Ninguna.** No hay límite de tamaño de cuerpo en `src/` (salvo la descarga de portadas); NFR-03 lo lista pendiente. El límite del campo `token` **no** prueba el cuerpo | Enviar un cuerpo excesivo a las rutas de escritura y observar el rechazo y la ausencia de efectos | **NUEVO**, posible **HUECO** |
| M4-17 | **Riesgo #143** (cursor de página > 2.000): reproducción **por HTTP** | #115 (relacionado) | Medido hoy con la función real: un nombre de 255 bytes de caracteres de control da un cursor de **2.100** caracteres; con 63 emojis, 396; con 255 ASCII, 400. **No recorrido por HTTP** | §7 | **RIESGO CONOCIDO** |
| M4-18 | **Recorrido de varias páginas** con orden estable, sin omisiones ni duplicados | #118–#120 (decisión del 2026-10-18) | `P`: `test_asistente_vinculacion_pg` (paginación, borrador por página) y U20 `test_asistente_vinculacion_masivo_pg` (155 archivos, 2 páginas) · `Pi`: V-24, V-52 (cuatro páginas) | Recorrer un grupo de **>200** archivos (3 páginas) comprobando orden, ausencia de omisiones y duplicados | **NUEVO** (barato) |
| M4-19 | **Aislamiento y no-efectos** de toda la ejecución | DoD | `Pi`: V-40…V-43 | Repetir sobre el Debian aislado: la biblioteca sintética no cambia, no hay puertos extra, los logs no llevan rutas ni nombres | **NUEVO** |
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

## 6. Brechas del producto que este plan descubre (no se corrigen aquí)

Son hallazgos de lectura, no decisiones. Cada una necesita **decisión explícita** antes de la ejecución: corregir, aceptar con excepción razonada o declarar NOT RUN.

| # | Hallazgo | Dónde aparece | Qué se propone decidir |
|---|---|---|---|
| H-1 | **No hay ninguna comprobación de espacio libre** en el instalador, la actualización, el backup ni el rollback. La conducta ante disco lleno es la que dé `pg_dump`/`gzip`/`docker`: puede ser segura (`set -e` y el dump verificado abortan antes de tocar nada) o no | M4-07 · #121.5, #123.6 | Ejecutar M4-07 para **observarla** y decidir si basta; si el mensaje no explica la causa en español, es un FAIL de producto |
| H-2 | **Las copias no llevan metadatos** (commit, versión del esquema, origen, identificador): se emparejan solo por marca de tiempo y por la referencia de git de `update.sh`. Una copia diaria (`backup_<TS>`) no se puede comprobar como compatible | M4-09 · #123.1 | Aceptar el criterio como **FAIL justificado**, o añadir un fichero de metadatos (código nuevo, fuera de este plan) |
| H-3 | **Restaurar una copia «de otra versión»** no se rechaza por versión: `rollback.sh` valida que el fichero sea un `gzip` íntegro y que existan cuatro tablas, no la versión del esquema | M4-11 · #123.7 | Observarlo; si no se rechaza, FAIL de producto o excepción |
| H-4 | **El instalador no detecta que el controlador de memoria (cgroup) está desactivado**, así que los topes de memoria del compose se descartan en silencio (hallazgo 1 del informe de la Pi) | M4-01, #122 | En el Debian aislado el controlador depende del núcleo del equipo anfitrión, que **no es Raspberry Pi OS**: **no se puede ver aquí**; queda NOT RUN para la Pi |
| H-5 | **#143**: el cursor emitido puede superar el límite que la propia petición acepta (§7) | M4-17 | §7 |
| H-6 | **No hay límite de tamaño de cuerpo** en las rutas de escritura (solo el del campo `token`) | M4-16 · #115 | Observar el rechazo; si no existe, decidir entre corregir o aceptar con excepción (NFR-03) |

## 7. Riesgo conocido: #143 (cursor de página)

**Estado:** defecto potencial **vigente** a nivel de servicio (medido hoy: 2.100 > 2.000 con un nombre de 255 bytes de caracteres de control), **sin reproducir por HTTP**. Es un riesgo, no un NOT RUN corriente: **no se acepta el candidato sin una decisión explícita sobre él.**

**Reproducción propuesta (M4-17), solo en el Debian aislado:**
1. En la biblioteca sintética, un grupo de **>100** archivos cuyo **último de la primera página** (orden por nombre e id) tiene un nombre de 255 bytes de caracteres de control válidos en Linux, y otro con 63 emojis como control negativo.
2. Pedir la revisión de la vinculación y leer el cursor de «Página siguiente»; enviarlo **tal cual** a `POST …/vinculacion/revisar` y a la API.
3. Registrar la respuesta (esperable `422` por longitud, sin mensaje comprensible) y que **no hay efectos**.

**Decisión previa a la aceptación (una de tres, a elegir por el responsable):**
- **(a) Corrección acreditada:** una PR de producto, fuera de este plan, con las pruebas de #143 (cursor acotado u opaco, sin pérdida de posición).
- **(b) Reproducción que descarte el fallo extremo a extremo:** si por HTTP no se produce (otra capa recorta o rechaza de forma recuperable), se documenta con la evidencia.
- **(c) Excepción razonada:** aceptar el candidato sabiendo que ese nombre concreto rompe la paginación de ese grupo, con su motivo y su alcance (grupos de >100 archivos y un último archivo con ese nombre), y registrarlo en el informe como defecto conocido.

No se marca como resuelta ni se trata como NOT RUN.

## 8. #122: umbrales (se acuerdan ANTES de medir)

| Métrica | Umbral propuesto | Origen | Cómo se usa |
|---|---|---|---|
| Confirmar 100 archivos | **< 30 s**, sin errores ni `503`, **dentro del tope de memoria** | **Aceptado** (D8, #123 y #188) | Aprobado/rechazado. **En un Debian x86-64 no acredita la Pi**: se marca «cumple en este entorno; Pi no medida» |
| Memoria pico por contenedor | por debajo del tope del compose (**512 M** aplicación y base de datos) | CLAUDE.md §1 y `docker-compose.yml` | Aprobado/rechazado; **el tope de Redis ya no existe** (ADR 0011) |
| Reinicios y OOM | **0** durante la medición | guion V-51 | Aprobado/rechazado |
| Memoria en reposo, CPU, E/S, duración de escaneo / propuesta / consulta | **sin umbral acordado** | — | **Informativo**, no aprobado ni rechazado (criterio #122.6) |
| Esfuerzo humano (tiempo por tarea, correcciones, ayudas) | **sin umbral** | requiere una persona con el guion | **NOT RUN**: no hay persona de prueba en el entorno aislado |

Para fijar cualquier umbral nuevo (memoria en reposo, escaneo de un corpus, tamaño de biblioteca objetivo) hace falta que lo apruebe el responsable **antes** de la ejecución; sin él, el dato es informativo.
El **corpus** debe ser sintético, con contenido único, y documentado (tamaño, formatos, duplicados, ambigüedades), como el del guion (321 archivos en la validación de la Pi).

## 9. Exclusiones (todo permanece NOT RUN; nada se convierte en PASS)

Rendimiento de Pi/ARM y de tarjeta SD · reinicio de la máquina física y disco lleno **reales** de la Pi · carga normal con Kavita/Transmission/Prowlarr · fuentes reales y su cobertura ·
móviles físicos · lectores de pantalla (se distingue el marcado probado de la verbalización no ejecutada) · esfuerzo humano medido con personas · instalación de Docker por `apt` y temporizador de `systemd` (salvo la opción B) · producción.

## 10. Decisiones que se piden al aprobar este plan

| # | Decisión | Recomendación |
|---|---|---|
| D-1 | **Cambio de contrato de M4:** sustituir la Pi por un Debian aislado como entorno de aceptación, con las exclusiones de §4 y §9 | Aprobar, **como cambio de M4**, no como extensión de #203 |
| D-2 | **Entorno** (§3): A (Docker-en-Docker), B (máquina virtual) o C | **A**; B solo si se exige instalar Docker por `apt` o el temporizador |
| D-3 | **Descargas** de imágenes (Docker-en-Docker y, si es B, una imagen de Debian): autorizar | Autorizar solo imágenes, nunca fuentes ni contenido |
| D-4 | **Versiones anteriores** (§2): rutas A y B | Ejecutar **las dos** |
| D-5 | **Brechas** H-1…H-3 y H-6: ¿se observan primero y se decide después (FAIL de producto, excepción o corrección)? | Observar primero; no corregir antes de ver |
| D-6 | **#143** (§7): reproducir por HTTP y elegir (a), (b) o (c) **antes de aceptar** | Reproducir primero |
| D-7 | **Umbrales** de §8 | Aprobar los tres «aprobados/rechazados» y dejar el resto informativo |
| D-8 | **Qué cuenta como aceptado** (#123.9): todos los casos obligatorios en PASS y cada FAIL o NOT RUN justificado y aceptado por escrito. Obligatorios propuestos: M4-01…05, 10, 11, 12, 13, 17, 19 | Aprobar esa lista |

## 11. Límites de la fase de ejecución (cuando se autorice)

Solo en el Debian aislado y con datos sintéticos; sin tocar producción, la Pi ni fuentes; las pruebas destructivas (matar procesos, limitar o llenar un volumen, corromper una copia) ocurren **únicamente allí**; cada caso registra commit, imagen, resultado y evidencia;
PASS, FAIL y NOT RUN se separan; no se cambia código de producto para que un caso pase; todo hallazgo de §6 se informa antes de corregir.
