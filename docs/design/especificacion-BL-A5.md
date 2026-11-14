# Especificación — BL-A5: repartir tradiciones entre discos (#156)

> **Estado: DISEÑO PROPUESTO. NO APROBADO. NO IMPLEMENTADO. MIGRACIÓN NO AUTORIZADA NI
> APLICADA.** Este documento **no escribe código, no crea la migración, no toca el disco, no
> ejecuta pruebas y no despliega nada**. Las decisiones de producto de §2 están **pendientes del
> PO**; se proponen, no se dan por aprobadas.
> **Base contrastada:** `origin/main` **`acb82a40`** (2026-11-14), worktree `.squad/wt-156bench`,
> rama `docs/156-benchmark`. La ficha de benchmark
> [`benchmark-BL-A5-repartir-tradiciones.md`](benchmark-BL-A5-repartir-tradiciones.md) es insumo,
> no aprobación. **Estimación: L** (§8); **A5 no se cierra con un corte parcial** (§8).
> **ADR:** se recomienda **ADR 0020** si el PO acepta persistir raíces y `root_id` (§9); **no se
> crea en este encargo**.

---

## 0. Resumen ejecutivo

Hoy ZascArr tiene **una sola raíz de biblioteca** en todos los niveles: una `library_path`, un
`host_library_dir`, un bind mount, un `File.file_path` absoluto sin `root_id`, y un importer que
construye `library / {tradición} / {Serie (Año)} / archivo` con esa única raíz
(`src/zascarr/config.py:188,194-196`; `docker-compose.yml:137,171-175`;
`services/importer.py:490,914-954`; `models/__init__.py:780-786`). A5 quiere que **cada tradición
tenga su raíz** y que el importer escriba en la raíz que le toca, sin que el catálogo, el escaneo,
la disponibilidad, las portadas, la auditoría o la cuarentena empiecen a mentir.

La propuesta es una entidad `library_roots` persistida, un mapeo **tradición → una raíz**
(`library_root_traditions`), `File.root_id` nullable con FK `RESTRICT`, y un `RaicesService` único
que resuelve raíz, ruta relativa, estado y `ruta_visible`. El importer y la asignación **eligen
raíz antes de construir la ruta**; una tradición sin raíz **no se mueve y se avisa** (fallo
cerrado, sin raíz por defecto silenciosa). El escaneo, la desaparición y la disponibilidad se
calculan **por raíz**, y una raíz caída no contamina a las demás. **No se mueven archivos
existentes** al cambiar la configuración; eso es otra historia. La migración 0041 es aditiva y no
reescribe `File.file_path`; la instalación de una raíz sigue funcionando igual.

**Corte:** cuatro cortes acumulativos A (cimiento+migración), B (importer/asignación), C (operar N
raíces), D (Ajustes/operación). A5 solo se cierra con C+D; A+B+C sin D no permite configurar el
segundo disco desde la UI, y A+B sin C miente en el escaneo.

---

## 1. Historia, valor y alcance

### 1.1 Historia y valor

**Como coleccionista con el disco casi lleno**, quiero repartir **tradiciones** entre discos para
seguir importando sin llenar el disco de siempre y sin que ZascArr me diga que tiene cosas que no
encuentra. La unidad de decisión es la **tradición editorial de la serie** (`ComicTradition`), no
el archivo suelto ni la serie (`docs/BACKLOG.md:49`). El valor no es «mover archivos»: es que el
siguiente tebeo de manga aterrice en el disco de manga, el de tebeo español en el suyo, y que el
resto de la aplicación sepa **dónde está cada cosa y qué raíz está caída**.

### 1.2 Entra en A5

- **N raíces de biblioteca** persistidas, con nombre, ruta de contenedor, ruta de host para
  mostrar, estado habilitado/deshabilitado y tradiciones asignadas.
- **Mapeo tradición → raíz**: una raíz puede servir N tradiciones; **cada tradición resuelve a una
  sola raíz** (propuesta pendiente, §2).
- **Importer** escribe en la raíz correcta, conservando el layout actual bajo ella:
  `{raíz}/{carpeta de tradición}/{Serie (Año)}/archivo`; `_Unsorted` en la raíz por defecto.
- **Asignación/organización** (ReviewService y AsignacionService) usan la raíz de la serie, no una
  raíz global.
- **Escaneo, rescan, adopción, desaparición y disponibilidad por raíz**: una raíz caída no marca
  ausentes las demás ni convierte el estado global en «todo bien».
- **Auditoría, cuarentena de apartados, conversión, vinculación, portadas, `ruta_visible` y
  exportación** respetan la raíz del archivo o de la operación.
- **Ajustes** para gestionar **raíces ya montadas**: listar, mapear tradiciones, habilitar/
  deshabilitar, estado/espacio, y decir claramente que un disco nuevo exige montaje + reinicio.
- **Compatibilidad de una instalación de una raíz**: misma ruta visible, mismo `relative_to`,
  mismo `is_missing` y mismos recuentos.

### 1.3 No entra en A5 (fuera de alcance explícito)

| Fuera | Por qué / qué queda |
|---|---|
| **Mover archivos ya registrados** al cambiar el mapeo o la ruta de una raíz | A5 solo afecta a importaciones nuevas. Mover es una operación masiva con dry-run, confirmación, rollback y su propia historia/ADR; el benchmark lo descarta en el MVP (`benchmark…:302`) |
| **Docker socket / montar discos desde la UI** | Ajustes gestiona raíces **ya montadas**; añadir un disco exige editar Compose/.env y reiniciar. No se da a la app acceso al socket de Docker |
| **Alta automática de discos** | No se detectan ni se montan discos; el operador autoriza el montaje |
| **Migración de datos de usuarios** | La migración solo crea la raíz 1 y rellena `root_id`; no mueve, renombra ni borra archivos; no toca datos de otras instalaciones |
| **Borrar/renombrar archivos, vaciar la cuarentena, puntuar, etiquetas, conversión de formatos** | Ya fuera por ADR 0017/BL-DUP1 y las historias de limpieza; A5 no las absorbe |
| **Detección de contenido distinto, carpetas o enlaces duros** | BL-R6/BL-DUP3/BL-DUP2; no es «repartir tradiciones» |
| **Cambiar el instalador para preguntar N raíces** | Posible extensión futura de A9; A5 valida en runtime/Ajustes y documenta la limitación del montaje |
| **Reasignación explícita de una raíz con archivos** | Bloqueada en A5; se diseña como historia aparte |

**No se declara hecho nada de lo anterior.** El alcance es una propuesta para el PO.

---

## 2. Decisiones de producto (pendientes del PO)

Las siete preguntas del benchmark (`benchmark…:295-305`), con opciones y recomendación. **Ninguna
está aprobada**; la columna «Decisión del PO» queda **PENDIENTE** hasta que el PO la cierre. Si el
PO no decide, la implementación **no empieza** por las que bloquean el contrato (1, 2, 3, 6).

| # | Pregunta | Opciones | Recomendación provisional | Decisión del PO |
|---|---|---|---|---|
| 1 | **¿Dónde vive la configuración?** | (a) `.env`/Compose estático; (b) Ajustes en caliente (D11); (c) tabla BD; (d) mezcla | **(d) Mezcla:** `.env`/Compose autoriza **qué está montado** (frontera de seguridad); la BD guarda nombre, `path`, `host_path`, `enabled` y tradiciones; Ajustes gestiona **solo raíces ya montadas**. Añadir disco = montaje + reinicio; no socket Docker. Se propone `LIBRARY_ROOTS`/`HOST_LIBRARY_ROOTS` como allowlist de montajes (§5) | **PENDIENTE** |
| 2 | **¿Mapeo tradición→raíz o raíz→varias tradiciones?** | (a) 1:1; (b) N tradiciones por raíz; (c) N raíces por tradición con prioridad | **(b) una raíz puede tener N tradiciones; cada tradición una sola raíz.** Varias raíces por tradición es ambigüedad silenciosa; si se quiere, debe ser lista ordenada explícita, nunca fallback | **PENDIENTE** |
| 3 | **¿Qué pasa si una tradición no tiene raíz?** | (a) raíz por defecto; (b) `_Unsorted`; (c) no mover y avisar; (d) elegir la raíz con más espacio | **(c) no mover y avisar** (fallo cerrado). Un default silencioso llena el disco equivocado; elegir por espacio rompe «cada tradición a su disco». `other` puede tener una raíz explícita «sin clasificar»; `_Unsorted` solo va a la raíz por defecto, que también es explícita | **PENDIENTE** |
| 4 | **¿Se mueven los ficheros ya registrados al cambiar la configuración?** | (a) sí automático; (b) preguntar y mover; (c) no mover; (d) comando aparte | **(c) no en A5.** El cambio de mapeo solo afecta a importaciones nuevas; los archivos antiguos conservan su `root_id` y su ruta. Mover es otra historia con dry-run/confirmación/rollback | **PENDIENTE** |
| 5 | **¿Un contrato único de escaneo o uno por consumidor?** | (a) cada servicio itera raíces; (b) un `RaicesService`/iterador común | **(b) un iterador único** (`RaicesService`) usado por importer, adopter, rescan, auditoría, disponibilidad, cuarentena, conversión y vinculación. Si cada uno hace su `rglob`, las diferencias serán bugs | **PENDIENTE** |
| 6 | **¿Ruta persistida o derivada?** | (a) solo derivar por prefijo; (b) `root_id` en `File`; (c) ambas | **(c) `root_id` persistido + `file_path` absoluto**; la derivación por prefijo es solo compatibilidad de migración. Sin `root_id`, una raíz retirada o dos prefijos solapados hacen ambigua la pertenencia y la auditoría no distingue «archivo de raíz A» de «huérfano» | **PENDIENTE** |
| 7 | **¿Alcance y esfuerzo?** | (a) L completo; (b) MVP sin UI; (c) partir en historias | **(a) L completo, cuatro cortes acumulativos** (§8); un «MVP sin UI» puede validar el contrato pero **no cierra A5**, porque el coleccionista no puede añadir el segundo disco | **PENDIENTE** |

**Consecuencia si no hay decisión:** no se implementa. El comportamiento actual (una raíz) sigue
siendo el único soportado; no se introduce una raíz «provisional» ni un fallback. Las decisiones 1,
2, 3 y 6 son **bloqueantes** para el contrato de datos; 4, 5 y 7 bloquean el cierre de la historia.

---

## 3. Contrato de datos

### 3.1 Tablas y columnas nuevas

#### `library_roots`

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `UUID PK` | Identidad local; nunca se reutiliza |
| `name` | `text NOT NULL` | Nombre visible, único normalizado (sin espacios sobrantes); no es ruta |
| `path` | `text NOT NULL` | Ruta **del contenedor**, absoluta, normalizada con `/`, sin barra final; única; no es la ruta del host |
| `host_path` | `text NULL` | Ruta real del host **solo para mostrar**; puede quedar vacía (se muestra `path`); no se usa para abrir/mover |
| `enabled` | `boolean NOT NULL DEFAULT true` | Si está deshabilitada, no se importa ni se escanea; sus `File` no se borran |
| `is_default` | `boolean NOT NULL DEFAULT false` | Raíz de `_Unsorted`; **exactamente una** raíz por defecto |
| `created_at`, `updated_at` | `timestamptz` | — |

Restricciones:

- `UNIQUE(path)` y `UNIQUE(name)` (normalizado en la aplicación; en BD `UNIQUE` simple sobre el
  texto ya normalizado).
- Índice parcial único `WHERE is_default` para que no haya dos raíces por defecto.
- `CHECK (path LIKE '/%' AND path <> '/' AND path NOT LIKE '%/../%' AND path NOT LIKE '%/.zascarr%')`.
  La validación de solapamientos y de montaje autorizado no cabe en un `CHECK`; va en el servicio
  (§5).
- `is_default` exige `enabled` (una raíz por defecto deshabilitada deja `_Unsorted` sin destino; la
  validación lo rechaza al guardar).

#### `library_root_traditions`

| Columna | Tipo | Regla |
|---|---|---|
| `root_id` | `UUID NOT NULL FK library_roots(id) ON DELETE CASCADE` | La raíz |
| `tradition` | `comic_tradition NOT NULL` | El enum existente (`ComicTradition`), **reutilizado**, no se crea un tipo nuevo |
| `PRIMARY KEY(root_id, tradition)` | — | Una raíz puede tener N tradiciones |
| `UNIQUE(tradition)` | — | **Cada tradición tiene como máximo una raíz** (decisión 2 recomendada) |

- El enum `comic_tradition` ya existe en la BD (`models/__init__.py:36-45,550-553`). La migración
  usa `postgresql.ENUM(..., create_type=False)`; no lo recrea.
- No se guardan «tradiciones» como JSONB: la unicidad por tradición es una garantía relacional y
  el conjunto es pequeño. Un JSONB no puede impedir dos raíces para la misma tradición sin un
  trigger; la tabla es más simple y auditable.
- Si el PO eligiera varias raíces por tradición (opción 2c), esta tabla cambiaría a una lista
  ordenada con prioridad; **no se implementa esa opción sin decisión explícita**.

#### `files.root_id`

| Columna | Tipo | Regla |
|---|---|---|
| `root_id` | `UUID NULL FK library_roots(id) ON DELETE RESTRICT` | La raíz a la que pertenece el `file_path` |

- **Nullable** para archivos fuera de toda raíz (vinculación externa, archivos antiguos no
  cubiertos, `_Unsorted` antes de la migración si no se pudo rellenar). No se inventa una raíz
  para ellos.
- `ON DELETE RESTRICT`: no se puede borrar una raíz con archivos; se deshabilita. La UI bloquea el
  borrado y explica que primero se reasigna (fuera de A5) o se deshabilita.
- `File.file_path` **no se reescribe** en la migración; `root_id` es la pertenencia explícita.
- Invariante de coherencia (aplicación + validación, no un trigger): si `root_id` no es nulo,
  `file_path` debe estar **bajo** `root.path` por componentes; si está bajo una raíz y no es
  externo, `root_id` debería estar relleno. La consulta de validación se define en §7.
- `File.root_id` no cambia al cambiar el mapeo o el `path` de una raíz; cambiar `path` con archivos
  se **rechaza** (§4.11).

#### Columnas de operación (compatibilidad de recuperación)

- `asignacion_operaciones.root_id UUID NULL FK library_roots(id) ON DELETE RESTRICT`: la raíz
  elegida al preparar la asignación, para que un cambio de mapeo/raíz no haga que la recuperación
  escriba en otro sitio. Filas antiguas quedan `NULL` y se reconcilian por su `destino`/prefijo
  (solo lectura/recuperación).
- Si **#264 (apartados) ya está fusionado**, añadir `root_id` a su cabecera/detalle de ítems (o
  guardarlo en el `detalle` JSONB si no se quiere otra columna); la cuarentena es **por raíz**
  (§4.7). Si #264 no está fusionado, A5 se coordina con él y no crea una segunda tabla de
  operaciones.
- No se añaden columnas a `conversion` ni a `vinculacion`: usan la ruta/`File` y su raíz; el
  diario/JSONB guarda `root_id` si hace falta para deshacer.

### 3.2 Migración 0041 (propuesta, no aplicada)

**Revisión `0041`, `down_revision = "0040"`** (la cabeza actual es `0040`; no existe
`library_roots` ni `root_id` — comprobado con `grep -RIn 'library_roots\|root_id' src alembic/versions`
sin resultados).

`upgrade`:

1. Crear `library_roots` y `library_root_traditions` con sus restricciones/índices.
2. Insertar **una** raíz:
   - `name = 'Biblioteca'` (nombre propuesto; no se inventa nombre editorial);
   - `path = str(settings.library_path)` (normalmente `/media/library`; la migración no depende de
     que exista en disco);
   - `host_path = settings.host_library_dir or NULL` (la ruta real existente);
   - `enabled = true`, `is_default = true`.
3. Insertar **todas** las tradiciones del enum `ComicTradition` para la raíz 1. Esto conserva el
   comportamiento actual para cualquier tradición futura; el PO puede retirar una asignación
   después, pero no se deja una tradición sin raíz en la migración.
4. Añadir `files.root_id` nullable y la FK `RESTRICT`.
5. Backfill **solo** de los `File` cuyo `file_path` cuelga de `root.path` **por componentes**:
   `file_path = path` o `file_path LIKE path || '/%'` (con path ya sin barra final); no un
   `startswith` de texto. Los demás quedan `NULL` y se muestran «fuera de raíz».
6. Añadir el índice `ix_files_root_id`; opcional `ix_library_root_traditions_tradition` (el unique
   ya lo cubre).
7. Añadir `root_id` a `asignacion_operaciones` (y a las operaciones de apartado si existen) como
   nullable, con FK `RESTRICT`; no se rellena por inferencia en la migración (las operaciones
   vivas son raras y su recuperación usa el destino).

`downgrade`:

- **Se niega** si hay más de una fila en `library_roots` o si algún `File.root_id` apunta a una
  raíz distinta de la raíz 1, o si alguna operación tiene `root_id` no nulo distinto del de la raíz
  1. Bajar así perdería la pertenencia que el usuario ya configuró; se prefiere un error explícito
  a un borrado silencioso.
- Si solo existe la raíz 1 y los `File` están en ella: elimina `files.root_id`, las columnas de
  operación, `library_root_traditions` y `library_roots`. **No toca ninguna ruta de archivo**; el
  disco queda intacto y la app vuelve a `library_path`.
- La migración es reversible en esquema; el dato de pertenencia de raíces adicionales se pierde si
  se baja con ellas, razón por la que el `downgrade` falla cerrado. No se declara «reversible sin
  condiciones».

### 3.3 Invariantes

| # | Invariante | Dónde se garantiza |
|---|---|---|
| I1 | `library_roots.path` es absoluta, normalizada, única y no es `/` ni contiene `.zascarr` | `CHECK` + `RaicesService.validar` |
| I2 | Dos raíces no son iguales, ni padre/hijo **por componentes**, ni el mismo `(st_dev, st_ino)`; no se solapan con descargas, incoming, export, compartidas ni `.zascarr` | Servicio de validación; tests de igualdad/anidamiento/symlink/inodo |
| I3 | Cada tradición tiene **como máximo una** raíz (`UNIQUE(tradition)`); una raíz puede tener N | BD |
| I4 | Hay **exactamente una** raíz por defecto y está habilitada | Índice parcial + validación |
| I5 | `File.root_id` no nulo ⇒ `file_path` bajo esa raíz por componentes; `file_path` bajo una raíz ⇒ `root_id` de esa raíz; solo los `File` fuera de toda raíz pueden tener `root_id NULL` | Validación de datos y tests; no trigger |
| I6 | Borrar una raíz con `File.root_id` se bloquea; cambiar su `path` con archivos se rechaza; deshabilitar no borra ni mueve | FK `RESTRICT` + servicio/UI |
| I7 | Ningún cambio de mapeo/raíz mueve ni reescribe un `File` existente | Servicio; A5 no tiene «mover» |
| I8 | La raíz ausente **no se crea** (`mkdir` prohibido) y no se confunde con «archivos borrados» | Importer/adopter/auditoría; guardarraíles |
| I9 | `File.root_id` se actualiza en el mismo `commit` que la ruta cuando un archivo se mueve de raíz (rescan/relink) | Servicio de escaneo, transacción corta |
| I10 | Un `File` fuera de toda raíz (`root_id NULL`) no se asigna a una raíz por azar ni se marca ausente por una raíz caída | Servicio; estado «fuera de raíz» |

### 3.4 Relleno de la raíz 1 y compatibilidad

- `path`: `settings.library_path`; `host_path`: `settings.host_library_dir` (si está vacío,
  `ruta_visible` devuelve la ruta del contenedor como hoy, `utils/ruta_visible.py:16-27`).
- Todos los `File` que hoy cuelgan de `library_path` obtienen `root_id` de la raíz 1. **No se
  tocan** `file_path`, `file_name`, `sha256_hash`, `issue_id`, metadata, `metadata_source` ni
  `locked_fields`.
- Los `File` fuera de la raíz 1 quedan `root_id NULL`; se muestran como «fuera de raíz» y no se
  mueven. No se inventa una raíz para ellos ni se borran.
- Instalación de una raíz: tras la migración, `ruta_visible`, `relative_to`, `is_missing` y todos
  los recuentos deben ser **idénticos** a antes. La app sigue leyendo `library_path` para la raíz 1
  mientras no se cambie el mapeo; no hay cambio de comportamiento en el corte A.
- Si `library_path` no existe en el momento de migrar (disco desmontado), la fila se crea igual;
  la raíz se muestra **ausente** y la app no crea la carpeta. El `backfill` de `File` se hace por
  ruta registrada, no por acceso al disco; no depende de que esté montada.

### 3.5 Estados de raíz (derivados, no persistidos)

| Estado | Cómo se deriva | Efecto |
|---|---|---|
| `ok` | `enabled` y `path` existe, es directorio, legible/escribible | Importa/escanea |
| `ausente` | `enabled` y `path` no existe o no es directorio | No importa; no marca ausentes; muestra «disco no encontrado»; no crea |
| `sin_permiso` | Existe pero no se puede leer/escribir con el UID/GID del servicio | No importa; error claro; no `chmod` |
| `llena` | Espacio libre por debajo del margen de `comprobar_espacio` | Nuevas importaciones a esa raíz se rechazan; no fallback; las demás siguen |
| `deshabilitada` | `enabled=false` | No importa/escanea; archivos intactos; `ruta_visible` sigue mostrando su host_path |
| `fuera_de_raiz` | `File.root_id NULL` | No pertenece a ninguna; visible como tal; no se escanea como raíz |

El estado es **observacional** y se recalcula; no se persiste un `estado` que pueda quedar obsoleto.
Un fallo de `stat` no se convierte en «ausente» sin distinguir «no puedo mirar» de «no está»; el
informe lo dice.

---

## 4. Contratos de comportamiento (EARS)

Las cláusulas usan «Cuando…, el sistema…» y son verificables. **Ninguna está implementada.**

### 4.1 Resolución tradición → raíz

- **Cuando** una serie tiene `tradition` con una raíz habilitada, existente y escribible, **el
  sistema** resuelve esa raíz **antes** de construir la ruta y la usa para el destino.
- **Cuando** la tradición no tiene raíz, la raíz está deshabilitada, ausente, sin permiso o llena,
  **el sistema no mueve el archivo**, conserva el original en la cola, registra el motivo en el
  informe y **no** usa otra raíz, ni la raíz por defecto, ni la de más espacio.
- **Cuando** hay dos raíces candidatas para una tradición (configuración inválida), **el sistema**
  rechaza la operación y no elige por orden/prioridad; la unicidad de §3.1 lo impide en BD.
- **Cuando** la raíz cambia de mapeo entre la vista previa y la escritura, **el sistema** usa la
  raíz resuelta al inicio de la operación y no cambia de destino a mitad; si el cambio invalida la
  operación, la rechaza y se reintenta.
- **Cuando** la ruta resuelta no está bajo la raíz tras resolver symlinks, **el sistema** falla
  cerrado y no escribe.

### 4.2 Importer

- **Cuando** una importación tiene serie fiable y su tradición resuelve a raíz, **el sistema**
  construye `build_library_path(raiz.path, serie, …)`, mueve con `safe_move_async` y guarda
  `File.root_id` de esa raíz. El layout bajo la raíz se conserva: `{tradición}/{Serie (Año)}/…`.
- **Cuando** no hay serie fiable (`UNSORTED` o sin `series_id`), **el sistema** usa
  `{raíz_por_defecto}/_Unsorted/archivo` y guarda su `root_id`; **no** elige una raíz al azar.
- **Cuando** la raíz por defecto no existe/está deshabilitada/llena, **el sistema** deja el archivo
  en la cola de entrada, no crea `_Unsorted` en otra raíz y lo informa.
- **Cuando** una raíz falla, **el sistema** sigue con las demás raíces y con los archivos de otras
  tradiciones; el informe distingue por **nombre de raíz**, no por ruta completa.
- **Cuando** el destino ya existe, **el sistema** usa el comportamiento de `safe_move`
  (nombre único, sin sobrescribir) y registra la ruta **efectiva** y su `root_id`; no reemplaza.
- **Cuando** el `commit` de la BD falla después del movimiento, **el sistema** no afirma éxito:
  el archivo está en el destino, la fila no; se registra el resultado incierto y la conciliación/
  reimportación lo resuelve sin duplicar ni borrar el original. No se anuncia «importado» sin
  comprobación.
- **Cuando** una raíz no tiene espacio, **el sistema** comprueba `comprobar_espacio` **de esa raíz
  de destino** antes de copiar; si no cabe, no mueve y el original queda intacto.
- **Cuando** el archivo se mueve entre raíces (cross-device), **el sistema** usa el camino de
  copia+verificación de `safe_move`, nunca un `rename` a ciegas; el original no se retira hasta que
  la copia está verificada.

### 4.3 Asignación manual y organización

- **Cuando** el coleccionista asigna un pendiente a una serie, **el sistema** resuelve la raíz de la
  serie **antes de crear el `Issue`** y antes de mover; si no hay raíz, devuelve un error claro y
  **no crea** el `Issue` ni mueve el archivo.
- **Cuando** la asignación usa `AsignacionService`, **el sistema** guarda la raíz elegida en la
  operación (`root_id`) para que la recuperación no dependa de un mapeo que pudo cambiar; el
  destino reservado pertenece a esa raíz.
- **Cuando** la asignación se recupera tras un fallo, **el sistema** usa la raíz persistida; si la
  raíz ya no existe/se deshabilitó, no mueve, conserva el original y deja la operación
  `pendiente_de_comprobar`/error, sin fallback.
- **Cuando** la organización (`ReviewService`) construye el destino, **el sistema** no usa
  `settings.library_path` global; usa la raíz resuelta. El camino heredado de `ReviewService` se
  adapta o se retira según #114 (§9), no se duplica.
- **Cuando** un archivo se vincula **en su sitio** (M1), **el sistema** no lo mueve, no le cambia la
  ruta y no le inventa `root_id`: si está bajo una raíz, conserva/hereda la raíz; si está fuera de
  toda raíz, queda `root_id NULL` y se muestra «fuera de raíz», sin bloquear el vínculo editorial.

### 4.4 `_Unsorted`

- **Cuando** un archivo no tiene serie fiable, **el sistema** lo deja en `_Unsorted` **de la raíz
  por defecto**; `_Unsorted` nunca se crea en una raíz no configurada como default.
- **Cuando** la raíz por defecto no está disponible, **el sistema no crea** `_Unsorted` en otra
  raíz; el archivo queda en la cola y se informa.
- **Cuando** se mueve un archivo de `_Unsorted` a una serie, **el sistema** actualiza `root_id` al
  de la raíz destino y no deja una fila en la raíz antigua.

### 4.5 Escaneo, adopción y rescan por raíz

- **Cuando** el adopter/rescan recorre la biblioteca, **el sistema** itera **solo raíces
  habilitadas**, una por una, y agrupa los `File` por `root_id`; no hace un `rglob` único sobre la
  raíz global.
- **Cuando** una raíz está ausente, vacía, sin permiso o deshabilitada, **el sistema** omite el
  escaneo/desaparición de **esa raíz**, no marca `is_missing` de sus archivos y no invalida las
  demás; el informe dice «sin verificar» para esa raíz, no «todo bien».
- **Cuando** una raíz está sana y sus archivos desaparecen de forma masiva por encima del umbral,
  **el sistema** aplica el guardarraíl **dentro de esa raíz**; no usa el total global de todas las
  raíces para decidir.
- **Cuando** un archivo cambia de una raíz a otra y el rescan/adopter lo reconoce por contenido,
  **el sistema** reenlaza **una sola fila**: actualiza `file_path` y `root_id` en el mismo commit,
  sin duplicar y sin borrar la fila; si hay más de una fila candidata o el contenido no coincide,
  no elige por azar y lo deja para revisión.
- **Cuando** hay un `File` con `root_id NULL`, **el sistema** no lo atribuye a una raíz ni lo marca
  ausente por una raíz caída; lo cuenta como «fuera de raíz».
- **Cuando** la raíz es accesible de nuevo, **el sistema** reanuda el escaneo y revierte
  `is_missing` solo si observa el archivo; no hay una reversión masiva sin observación.

### 4.6 Disponibilidad y estado

- **Cuando** termina la comprobación, **el sistema** guarda en `import_runs.details` el resultado y
  los recuentos **por raíz** (`raices`: id/nombre/estado/archivos/ausentes/resultado), además de
  las claves actuales para compatibilidad.
- **Cuando** una raíz no se pudo comprobar, **el sistema** muestra el estado global como
  «sin verificar», no como «todo bien», y la raíz concreta con su causa; la lista de no disponibles
  no afirma una causa que no observó.
- **Cuando** una raíz está deshabilitada, **el sistema** la muestra «Desactivada», no como error, y
  no la cuenta en el semáforo de fallos (mismo criterio que un servicio apagado en Ajustes).

### 4.7 Auditoría, cuarentena, conversión, vinculación y exportación

- **Cuando** la auditoría recorre la biblioteca, **el sistema** itera las raíces habilitadas y
  calcula cada grupo con **su** raíz; la ruta relativa es `relative_to(root)`, no
  `relative_to(library_path)`; el informe indica la raíz.
- **Cuando** se aparta una copia (ADR 0017/#264), **el sistema** usa la cuarentena **de la raíz de
  origen**: `{root}/.zascarr/apartados/{operacion}/…`, en la misma montura; si un grupo abarca
  varias raíces, cada ítem se guarda en la cuarentena de **su** raíz y la operación conserva el
  `root_id` por ítem. No se mueve a una cuarentena de otra montura ni se usa una raíz global.
- **Cuando** se convierte un archivo, **el sistema** usa la cuarentena/diario de **su** raíz; la
  conversión y su deshacer no cruzan a otra raíz; si no hay misma montura, falla cerrado.
- **Cuando** se vincula/desvincula un archivo, **el sistema** comprueba la raíz del archivo, no una
  biblioteca global; un archivo fuera de toda raíz no se considera «en su sitio» para organizar,
  pero puede vincularse en sitio si el contrato M1 lo permite.
- **Cuando** se calcula una portada, **el sistema** usa el `File` de su raíz; si la raíz está caída,
  no busca el mismo contenido en otra raíz ni muestra una portada ajena; deja la portada no
  disponible y explica la raíz.
- **Cuando** se exporta a Kavita, **el sistema** valida que `export_path` no esté dentro ni sea
  padre de **ninguna** raíz (además de descargas/incoming/compartidas) y lee cada fuente de su
  raíz; no escribe dentro de una raíz.
- **Cuando** se muestra una ruta en la UI, **el sistema** usa `ruta_visible(ruta, root)` con el
  `host_path` de **esa** raíz; si no hay `host_path` o el `File` está fuera de raíz, muestra la
  ruta del contenedor, nunca el host de otra raíz.

### 4.8 Raíz caída, deshabilitada o llena

- **Cuando** una raíz está ausente/no es directorio/sin permiso, **el sistema no ejecuta `mkdir`**,
  no crea una carpeta sustituta, no mueve archivos hacia ella y conserva todos los `File` y sus
  estados; el importer omite esa raíz y sigue con las demás.
- **Cuando** una raíz está deshabilitada, **el sistema** no importa ni escanea en ella; no borra,
  mueve ni marca sus archivos; su `host_path` sigue disponible para mostrar.
- **Cuando** una raíz está llena, **el sistema** rechaza nuevas importaciones a esa raíz con causa
  «no hay espacio»; no usa otra raíz como fallback.
- **Cuando** una raíz vuelve, **el sistema** la vuelve a considerar en el siguiente ciclo, sin
  reintentar automáticamente los archivos que quedaron en la cola de entrada.

### 4.9 Conflicto de destino, disco lleno y cross-device

- **Cuando** el destino canónico existe, **el sistema** no sobrescribe: `safe_move` usa un nombre
  único y se guarda la ruta efectiva; el `root_id` es el de la raíz del destino efectivo.
- **Cuando** no hay espacio en la raíz de destino, **el sistema** comprueba **esa** raíz antes de
  copiar y aborta sin tocar el original.
- **Cuando** origen y destino están en sistemas de ficheros distintos, **el sistema** copia a un
  temporal en el destino, verifica tamaño/hash y solo entonces retira el original; si falla, el
  original permanece y se limpian temporales.
- **Cuando** el movimiento falla después de crear el temporal o a mitad de una copia entre
  raíces, **el sistema** hace rollback de los temporales/destinos parciales de esa operación, **no
  retira el original** y no lo presenta como importado; el informe lo marca como error y la
  siguiente pasada reconcilia. Un fallo de este tipo **no** se convierte en «archivo movido».
- **Cuando** el `commit` de BD falla después del movimiento, **el sistema** no presenta un éxito
  falso; deja el resultado incierto para reconciliación; no borra el archivo movido por el fallo.

### 4.10 Concurrencia

- **Cuando** el ciclo del importer y el rescan coinciden, **el sistema** mantiene el cerrojo de
  ciclo existente (`rescan_biblioteca.py:1-15,51-55`); no hay dos paseos de la biblioteca a la vez,
  ahora con N raíces.
- **Cuando** se cambia el mapeo/raíz mientras un ciclo está en curso, **el ciclo usa la foto de
  raíces tomada al empezar**; el cambio se aplica al siguiente ciclo; no se cambia el destino a
  mitad de una importación.
- **Cuando** dos operaciones intentan mover el mismo `File`/destino, **el sistema** usa los locks
  de archivo/operación existentes (`services/asignacion.py`, `utils/bloqueo_archivo`) y una sola
  operación gana; la otra se rechaza o espera, sin duplicar destino.
- **Cuando** se deshabilita una raíz, **el sistema** no interrumpe un movimiento en curso; termina
  la operación y el siguiente ciclo ya no la usa.

### 4.11 Cambios de configuración

- **Cuando** se cambia el mapeo de una tradición, **el sistema** no mueve ningún archivo existente;
  solo afecta a nuevas importaciones. La UI lo dice explícitamente.
- **Cuando** se intenta cambiar `path` de una raíz con `File.root_id`, **el sistema** lo rechaza;
  se debe crear una raíz nueva y reasignar (fuera de A5).
- **Cuando** se intenta borrar una raíz con archivos, **el sistema** lo bloquea; deshabilitar es la
  acción permitida.
- **Cuando** se intenta borrar una raíz vacía, **el sistema** lo permite solo si no hay `File` ni
  operaciones vivas que la referencien.

### 4.12 Exportación, compartidas y contexto

- **Cuando** el exportador resuelve su raíz, **el sistema** comprueba solapamiento con **todas** las
  raíces y con descargas/incoming/compartidas; no exporta dentro de una biblioteca.
- **Cuando** una ruta de un cliente de descargas se traduce, **el sistema** usa los pares
  host→contenedor de **cada raíz** además de los actuales; si no puede traducir, falla cerrado.
- **Cuando** se declara contexto de carpeta, **el sistema** normaliza contra la raíz del archivo, no
  contra `library_path` global; una ruta fuera de toda raíz se rechaza como contexto de biblioteca.

---

## 5. Seguridad de rutas y garantías A3

### 5.1 Montajes autorizados

- **Frontera de seguridad:** la app **no acepta rutas arbitrarias** desde Ajustes. Las rutas
  permitidas son los montajes declarados por el operador en Compose/.env. Se propone:
  - `LIBRARY_ROOTS`: lista ordenada de rutas **del contenedor** montadas (separadas por comas),
    p. ej. `/media/library,/media/library2`;
  - `HOST_LIBRARY_ROOTS`: lista opcional y paralela de rutas **del host** para mostrar; si falta
    una, se muestra la ruta del contenedor.
  - La raíz 1 sigue siendo `library_path`/`host_library_dir`; con una sola raíz, la allowlist por
    defecto es `[library_path]` y no cambia nada.
  - `bootstrap.sh`/Compose pasan estas variables; **no** se añade socket Docker. Añadir un disco
    exige editar Compose/.env, montar y `docker compose up -d`; Ajustes solo ve lo ya montado.
- **Validación:** toda raíz de BD debe estar **bajo** una ruta de `LIBRARY_ROOTS` (misma ruta
  canónica o dentro por componentes). Una fila antigua que ya no esté autorizada se muestra
  «deshabilitada por configuración» y no se importa; no se borra.
- **Ajustes no crea rutas:** el formulario selecciona entre los montajes autorizados; el nombre y
  el mapeo son datos de BD. Si el PO prefiere escribir la ruta, se sigue validando contra la
  allowlist y se rechaza cualquier otra.

### 5.2 Validación de solapamientos y symlinks

Reutiliza la semántica de A9 (`scripts/_rutas.sh:87-230`: ruta efectiva, igualdad, anidamiento por
componentes, mismo `(st_dev, st_ino)`) y la aplica en Python antes de guardar:

1. **Absoluta y normalizada:** `Path.resolve(strict=False)`; sin `..`; sin barra final; no `/`; no
   `.zascarr`.
2. **Montaje autorizado:** bajo `LIBRARY_ROOTS` (resuelto), no solo por texto.
3. **No solapes:** contra todas las raíces, descargas, incoming, `export_path`,
   `carpetas_compartidas` y `.zascarr`:
   - igualdad de ruta canónica;
   - padre/hijo **por componentes** (`root_a` es padre de `root_b` si `b.relative_to(a)` no falla),
     no por prefijo textual (`/media/lib` no es padre de `/media/library`);
   - si ambas existen, mismo `(st_dev, st_ino)` (bind mount/otra ruta a la misma carpeta).
4. **Symlinks:** resolver todos los componentes; rechazar un symlink roto o un destino real fuera
   de la raíz permitida. No se sigue un symlink de directorio al escanear; no se escribe fuera de
   la raíz resuelta.
5. **Permisos:** comprobar que el UID/GID del servicio puede leer/escribir (prueba de escritura de
   un temporal **dentro** de la raíz, con borrado) al guardar y antes de importar; si no, error
   cerrado con la carpeta y el usuario, sin `chmod`/`chown` automáticos.
6. **Raíz ausente:** no se crea; se puede guardar solo si el montaje está presente y es
   directorio/escribible en ese momento (decisión propuesta; si el PO quiere configurar un disco
   desconectado, deberá permitirlo explícitamente y la raíz quedará «ausente», nunca se creará).

### 5.3 Garantías A3 (no dañar la colección)

| Garantía | Cómo se conserva con N raíces |
|---|---|
| Nunca borrar el original antes de una copia verificada | `safe_move`: entre sistemas copia+verifica y solo entonces retira; dentro del mismo sistema `os.replace`; A5 no añade un camino que borre antes |
| Nunca sobrescribir | `safe_move` elige nombre único; el destino efectivo se registra; la cuarentena/undo también rechaza destino ocupado |
| Fallo de movimiento no deja el original perdido | Si la copia/rename falla, el origen sigue; se hace rollback de temporales/destinos parciales; no se marca importado |
| Disco lleno | `comprobar_espacio` **por raíz de destino** antes de copiar; no hay fallback a otra raíz |
| Cross-device/EXDEV | Se usa el camino copia+verificación de `safe_move`; nunca `shutil.move` a ciegas |
| Fallo de BD después de mover | No se declara éxito; conciliación/reimportación; nunca se borra el archivo movido por el fallo |
| Raíz retirada/deshabilitada | No se borran archivos; se bloquea el borrado con filas; se deshabilita y se explica |
| Symlink/path traversal | Resolución real y comprobación de que el destino queda bajo la raíz permitida; no se crean carpetas fuera |
| Nunca tocar archivos de otra raíz | Toda operación resuelve la raíz del `File`/serie; los escaneos son por raíz |

**No se cambia** la firma de `safe_move` para relajar estas garantías; A5 la usa con la raíz
correcta.

---

## 6. UX de Ajustes

### 6.1 Tarjeta «Discos de la biblioteca»

En `/ui/ajustes`, una tarjeta nueva (sección «Biblioteca» o «Archivos»):

- **Frase de entrada (≤20 palabras):** «Reparte tus tradiciones entre los discos que ya tienes montados.»
- **Lista de raíces montadas**, una fila por raíz:
  - nombre visible;
  - **ruta del host** (`host_path`) como texto principal; ruta del contenedor solo en
    `<details>`/detalle técnico;
  - estado con palabra + color/icono (no solo color): **Disponible**, **Disco no encontrado**,
    **Sin permiso**, **Llena**, **Desactivada**;
  - espacio libre/total si se puede leer; fecha de la última comprobación;
  - tradiciones asignadas como chips;
  - marca «Por defecto» (la de `_Unsorted`).
- **Mapa tradición → raíz:** una fila por tradición (`ComicTradition`), con un `<select>` de raíces
  habilitadas. Una tradición sin raíz se marca «Sin disco asignado»; no hay opción «automática».
  Guardar muestra un resumen de qué tradiciones cambian de disco y recuerda: «Los archivos que ya
  tienes no se mueven; solo cambia dónde se importan los nuevos.».
- **Añadir disco:** solo aparecen los montajes autorizados que aún no son raíz; el nombre se
  escribe; `host_path` viene del montaje o se muestra la del contenedor. Si no hay ninguno:
  «Para añadir otro disco, móntalo en el servidor y reinicia ZascArr; aquí solo se gestionan discos
  ya montados.» **No hay campo de ruta libre ni botón de montar.**
- **Habilitar/deshabilitar:** deshabilitar no mueve ni borra; aviso de que no se importará ahí.
- **Borrar:** solo si no tiene archivos; si tiene, el botón está deshabilitado y se explica
  «Este disco tiene N archivos registrados; deshabilítalo o reasígnalos en otra historia.».
- **Cambiar ruta:** bloqueado si tiene archivos; se explica que se cree una raíz nueva.
- **Reinicio:** banner persistente si hay un montaje nuevo pendiente: «Montaste un disco nuevo;
  reinicia ZascArr para que aparezca». No se reinicia desde la app.
- **Predeterminada:** elegir la raíz de `_Unsorted`; exactamente una; si se deshabilita, hay que
  elegir otra antes de guardar.

### 6.2 Mensajes y accesibilidad

- Español llano; causa + acción; sin «root», «mount», «path», «hash», «EXDEV», «inodo» ni rutas
  internas en superficie. Ejemplos: «El disco de Manga no está montado. Conéctalo y reinicia
  ZascArr.»; «No se puede escribir en el disco de Tebeo español: revisa los permisos de la carpeta.»
- **Presupuesto de texto:** frase de entrada ≤20 palabras; ≤50 palabras visibles antes de la
  primera acción; el detalle técnico (ruta del contenedor, última comprobación) en `<details>`.
- **A11y:** `<fieldset>/<legend>` para el mapa; `<label>` por select; estado con texto, no solo
  color; `role="status"` para el resumen guardado y `role="alert"` para errores; foco al primer
  error; navegación por teclado; 320 px sin scroll horizontal; texto ≥14 px; botones con verbos;
  sin diálogos nativos. Respetar `docs/design/sistema-de-diseno-zascarr.md`.
- **Un botón principal por pantalla:** «Guardar cambios» es neutro (Ajustes), no principal; la
  acción de la tarjeta no compite con la acción principal de la página.

### 6.3 Rutas visibles en el resto de la UI

- Toda ruta mostrada al coleccionista usa `ruta_visible(ruta, root)` con el `host_path` de la raíz
  del `File`; `ruta_visible` se generaliza para aceptar la raíz (hoy recibe `biblioteca`/`host`
  globales, `utils/ruta_visible.py:16-27`).
- Si `File.root_id` es `NULL` o la raíz no tiene `host_path`, se muestra la ruta del contenedor;
  nunca se usa el host de otra raíz.
- En la lista de no disponibles, auditoría y ficha, se indica la raíz por **nombre** cuando ayuda a
  encontrar el disco («Manga — disco no encontrado»), no la ruta interna.

---

## 7. Plan de pruebas

### 7.1 Unitarias / sin BD

| Grupo | Casos | Criterio |
|---|---|---|
| Validación de rutas | absoluta/relativa, `..`, `/`, barra final, `.zascarr`, ruta de descargas/incoming/export/compartida | Rechazo con causa; no se normaliza a algo inseguro |
| Solapamientos | iguales, padre/hijo por componentes, prefijo textual que **no** es anidamiento (`/media/lib` vs `/media/library`), symlink al mismo destino, bind mount mismo `(st_dev, st_ino)` | Rechazo en igualdad/anidamiento/inodo; aceptación del prefijo textual no anidado |
| Symlinks | roto, bucle, componente intermedio, destino fuera de la allowlist | Rechazo; no se sigue fuera |
| Mapeo | tradición sin raíz, tradición con dos (BD), raíz con N, default ausente/dos | Invariantes I3/I4; errores claros |
| `relative_to` / `ruta_visible` | raíz A/B, `File.root_id` nulo, host vacío, prefijo textual | Relativa a la raíz correcta; host correcto; sin host global |
| Migración (modelo) | `library_roots`, `library_root_traditions`, `files.root_id`, constraints | Modelo coincide con §3 |

### 7.2 Postgres real

| Caso | Criterio |
|---|---|
| `0041 upgrade` sobre una BD con `File` de una raíz | Una raíz, todas las tradiciones, `root_id` relleno para los que cuelgan; **ninguna** `file_path` cambia; recuentos iguales |
| `File` fuera de la raíz | `root_id NULL`; no se borra ni se mueve; se muestra «fuera de raíz» |
| `downgrade` con una raíz | Borra tablas/columnas; `File.file_path` intactos; la app vuelve a `library_path` |
| `downgrade` con dos raíces o `root_id` de otra | **Falla cerrado**; no se pierde la pertenencia |
| Constraints | `path`/`name` unique, una default, `UNIQUE(tradition)`, FK `RESTRICT` al borrar raíz con archivos |
| Migración idempotente/orden | `alembic upgrade head` desde `0040`; no toca tablas ajenas; `alembic_version=0041` |
| Relleno de `root_id` por prefijo de componentes | Ruta `/media/library2/x` **no** se asigna a `/media/library`; ruta con `/media/library/x` sí |
| Operaciones | `asignacion_operaciones.root_id` nullable; recuperación no cambia de raíz |

### 7.3 Importador, asignación y sistema de ficheros

| Caso | Criterio |
|---|---|
| Dos raíces | Cada tradición importa a su raíz; `File.root_id` correcto; layout bajo la raíz |
| Tradición sin raíz | No mueve; el archivo queda en la cola; informe con causa; **no** fallback |
| `_Unsorted` | Va a la raíz por defecto; si no está, no se crea en otra |
| Raíz caída/deshabilitada | No `mkdir`; no mueve; otros archivos siguen; los `File` existentes intactos |
| Destino ocupado | Nombre único; no sobrescribe; ruta efectiva y `root_id` correctos |
| Disco lleno | `comprobar_espacio` por raíz; no mueve; original intacto; no fallback |
| Cross-device/EXDEV | `safe_move` copia+verifica; original no se retira si falla; test con FS real y simulación de EXDEV |
| Permisos PUID/PGID | Raíz no escribible → error claro; no `chmod 777`; archivo original intacto |
| Fallo de BD tras mover | Resultado incierto; no éxito falso; conciliación; original/destino no se borran por el fallo |
| Asignación | Resuelve raíz antes de crear `Issue`; si no hay raíz, no crea ni mueve; operación guarda `root_id` |
| Un solo disco (no regresión) | Misma ruta, mismo nombre, mismo `relative_to`, mismo `is_missing`, mismos recuentos que antes |

### 7.4 Escaneo, rescan y desaparición por raíz

| Caso | Criterio |
|---|---|
| Dos raíces con una caída | La caída se omite; la otra se escanea; **no** se marcan ausentes de la caída; estado global «sin verificar» |
| Desaparición masiva en una raíz | Umbral por raíz; no se dispara por el total global; no contamina la otra |
| Desaparición normal | Se marca `is_missing` solo en la raíz observada; reversión al ver el archivo |
| Archivo movido de raíz A a B | Rescan/adopter reenlaza **una** fila, actualiza `path` y `root_id`, sin duplicar; si no hay match único, no elige |
| `root_id NULL` | No se atribuye a raíz; no se marca ausente por una caída |
| Raíz vuelve | Se reanuda; no se revierte sin observación |
| Adopter/inventario | Recuentos por raíz; raíz inaccesible no se presenta como 0 archivos; prefijo por raíz |

### 7.5 Servicios de lectura/escritura y UI

| Caso | Criterio |
|---|---|
| Auditoría | Itera raíces; ruta relativa por raíz; informe con raíz; no mezcla |
| Cuarentena | `{root}/.zascarr/apartados` en misma montura; grupo multi-raíz guarda por ítem; undo no cruza; no sobrescribe |
| Conversión | Cuarentena/diario en la raíz del archivo; cross-device falla cerrado |
| Vinculación/desvinculación | Raíz del archivo; archivo fuera de raíz manejado; no usa `library_path` global |
| Portadas | Extrae del `File` de su raíz; raíz caída no busca en otra; estado explica |
| `ruta_visible` | Host de la raíz correcta; `root_id` nulo → contenedor; sin host ajeno |
| Exportación | `export_path` no solapa ninguna raíz; fuentes por raíz |
| Ajustes (navegador real) | Lista/estado/mapa; añadir solo montados; no ruta libre; borrar con archivos bloqueado; cambiar path bloqueado; reinicio; mensajes; a11y/320 |
| Seguridad | Allowlist, solapamientos, symlink, inodo, path traversal, no `mkdir` de raíz, no borrado de originales |

### 7.6 PASS / FAIL / NOT RUN de esta especificación

- **PASS:** lectura del benchmark y contraste con el código de `acb82a40`; contrato de datos,
  comportamiento, seguridad, UX, pruebas y partición definidos; no se ejecutó nada.
- **FAIL:** ninguno de la especificación. Un fallo real solo puede aparecer al implementar/probar.
- **NOT RUN:** migración 0041, tests, dos discos/montajes, `safe_move` con EXDEV/disco lleno,
  escaneo real con raíz caída, navegador/Ajustes, producción y Pi. La ficha de benchmark ya declaró
  NOT RUN las ejecuciones de referencias y la prueba con dos discos; esta spec **no las convierte en
  PASS**.

---

## 8. Partición y estimación

### 8.1 Cuatro cortes acumulativos

| Corte | Contenido | ¿Cierra A5? | Esfuerzo | AC del corte |
|---|---|---|---|---|
| **A · Cimiento y migración** | `library_roots`, `library_root_traditions`, `files.root_id`, `RaicesService`/validadores, migración 0041/backfill, una raíz por defecto, compatibilidad de una raíz, tests de modelo y migración; **comportamiento actual intacto** | No | **M** | AC-01, AC-02, AC-07, AC-13 (validación), AC-15 parcial |
| **B · Importer y asignación** | Resolver tradición→raíz; `build_library_path(root, …)`; `_Unsorted` por defecto; `File.root_id`; `ReviewService`/`AsignacionService` con raíz; informe por raíz; A3 por raíz | Parcial (escribe en la raíz correcta) | **M/L** | AC-03, AC-04, AC-05, AC-06, AC-12 |
| **C · Operar N raíces** | Adopter/rescan por raíz; desaparición por raíz; disponibilidad/estado; auditoría; cuarentena/conversión/vinculación; portadas; `ruta_visible`; export/compartidas | Sí, de extremo a extremo | **L** | AC-08, AC-09, AC-10, AC-11, AC-12 |
| **D · Ajustes y operación** | Tarjeta de raíces, mapa tradición→raíz, alta desde montados, habilitar/deshabilitar, borrar bloqueado, estado/espacio, reinicio, mensajes, a11y, documentación | Sí, para el coleccionista | **M** | AC-14, AC-15 |

**Dependencias:** A → B y A → C; B y C pueden solaparse solo si el contrato de raíz está cerrado;
D depende de A (datos) y B (para que el mapeo tenga efecto); C debe estar antes de declarar A5
cerrada. **No hay un corte vertical pequeño que cierre A5:** el primer cambio visible (importar a
otra raíz) sin escaneo por raíz haría que la app mintiera, que es justo lo que A5 evita.

### 8.2 Estimación revisada

- **L** (se mantiene la del benchmark; no baja a M): toca modelo + migración, importer,
  asignación/organización, adopter/rescan, auditoría, disponibilidad, cuarentena, conversión,
  vinculación, portadas, `ruta_visible`, exportación, Ajustes, salud y pruebas con dos sistemas de
  ficheros.
- **Sin fecha ni compromiso de sprint:** no está calibrado. Los cortes A y D son M; B es M/L; C es
  L; el total es L. La estimación se refina al implementar, no se convierte en promesa.
- **Orden recomendado:** A (sin cambio visible) → B → C → D. Se puede parar tras A sin romper
  nada, pero **A5 no está hecho** hasta C+D.

---

## 9. Reconciliación con otras historias y ADR

| Historia / decisión | Solapamiento | Resolución propuesta |
|---|---|---|
| **#113 / MIT-M1-US02 «Centralizar decisiones de dominio»** | La resolución de raíz es una decisión de dominio que no puede quedar duplicada en importer, review, asignación y adopter | Un solo `RaicesService` en la capa services; UI y API lo comparten. A5 **depende** de que el camino de dominio esté centralizado o lo centraliza como parte de A; no añade una segunda regla |
| **#114 / MIT-M1-US03 «Adaptar o retirar caminos heredados»** | `ReviewService.assign_to_series` es el camino heredado que mueve con `library_path` global (`services/review.py:127,314`); `AsignacionService` es el camino estricto | A5 adapta el camino que se conserve para resolver raíz; el que se retire, no se parchea. No se crea un tercer camino. La decisión de retirar/adaptar es de #114 y debe coordinarse antes de B |
| **M1 «vincular en sitio»** | No mueve; no debe exigir raíz ni cambiar `file_path` | Si el archivo está bajo una raíz, conserva su `root_id`; si está fuera, `root_id NULL` y se muestra «fuera de raíz». El vínculo editorial no se bloquea por no tener raíz |
| **B7 desaparición** | Hoy lee **todos** los `File` y comprueba contra **una** raíz (`importer.py:649-713`); la limitación está escrita en `docs/BACKLOG.md:124` | A5 la sustituye por comprobación **por raíz**: agrupar por `root_id`, guardarraíles por raíz, una caída no contamina. Mantiene los umbrales y la semántica de «sin dato» de #231 |
| **A3 «nunca dañar la colección»** | `safe_move` es la base; A5 no puede relajarlo | Se conserva el contrato de `safe_move`; no se añade borrado antes de verificar; disco lleno/EXDEV/conflicto se prueban **por raíz** |
| **A9 solapamientos** | El instalador ya valida biblioteca vs descargas por ruta efectiva/componentes/inodo (`scripts/_rutas.sh:87-230`) | A5 reutiliza la misma semántica para raíces; el instalador no cambia en A5 (fuera de alcance), pero la validación de Ajustes es equivalente. Una futura extensión del instalador a N raíces sería otra historia |
| **BL-R9 / #326 rescan** | Rescan hoy hereda una raíz (`library_adopter.py:290,339,499`; `rescan_biblioteca.py:1-15,51-55`) | A5 lo hace iterar raíces; conserva el registro incremental, el cerrojo y los contratos de #326 |
| **#231 disponibilidad** | Hoy la comprobación es global; el estado puede mentir si una raíz cae | A5 añade resultado/recuentos por raíz y un estado global «sin verificar» si alguna no se pudo mirar; no cambia la regla de solo lectura de la lista |
| **#264 / ADR 0017 apartados** | La cuarentena actual es `<library>/.zascarr/apartados` global y la ruta relativa es única (`web/auditoria.py:395-399,437`) | Con N raíces, la cuarentena es **por raíz de origen**; la operación guarda `root_id` por ítem; undo no cruza monturas. Si #264 está fusionado, se adapta; si no, se coordina antes de C |
| **ADR 0020** | Persistir raíces y `root_id` es una decisión duradera de modelo/configuración/seguridad | **Se recomienda crear ADR 0020** (siguiente número libre; no se crea aquí) que fije: entidad raíz, allowlist de montajes, unicidad tradición→raíz, `root_id`, migración y no-mover-existentes. Sin ADR aceptado, no se implementa el corte A |

**No se resuelve por decreto:** las decisiones 1, 2, 3, 6 y 7 del PO son previas al ADR; el ADR
registra la decisión, no la sustituye.

---

## 10. Criterios de aceptación EARS y trazabilidad

### 10.1 AC completos

- **AC-01 — Raíces persistidas.** Dado un montaje autorizado, cuando el PO/operador lo configura
  como raíz, entonces queda una fila `library_roots` con `path` canónico, `host_path` de mostrar,
  `enabled`, una sola raíz por defecto y tradiciones asignadas; dos raíces no pueden compartir
  `path`, nombre ni solaparse.
- **AC-02 — Mapeo unívoco.** Dada una tradición, cuando se guarda el mapa, entonces tiene como
  máximo una raíz; una raíz puede tener N tradiciones; una tradición sin raíz queda «sin disco
  asignado» y no se inventa.
- **AC-03 — Importación a la raíz correcta.** Dada una serie con tradición mapeada a una raíz
  disponible, cuando el importer importa un archivo, entonces el destino está bajo **esa** raíz,
  conserva el layout y `File.root_id` apunta a ella.
- **AC-04 — Tradición sin raíz = fallo cerrado.** Dada una serie cuya tradición no tiene raíz
  (o está deshabilitada/ausente/sin permiso/llena), cuando el importer intenta importar, entonces
  **no mueve** el archivo, no crea una raíz y lo informa con causa accionable; los demás archivos
  siguen.
- **AC-05 — `_Unsorted` explícito.** Dado un archivo sin serie fiable, cuando se importa, entonces
  va a `_Unsorted` de la **raíz por defecto**; sin raíz por defecto disponible, no se mueve ni se
  elige otra raíz.
- **AC-06 — Asignación/organización con raíz.** Dado un pendiente asignado a una serie, cuando se
  organiza, entonces la raíz se resuelve **antes** de crear el `Issue`/mover; sin raíz no se crea
  el `Issue` ni se mueve; la operación conserva la raíz elegida.
- **AC-07 — Compatibilidad de una raíz.** Dada una instalación existente de una raíz, cuando se
  aplica la migración, entonces `ruta_visible`, `relative_to`, `is_missing` y todos los recuentos
  son idénticos; ninguna `file_path` se reescribe; los `File` fuera de la raíz quedan
  `root_id NULL`.
- **AC-08 — Escaneo por raíz.** Dadas N raíces, cuando se escanea, entonces se itera cada raíz
  habilitada; una raíz inaccesible/vacía no marca ausentes sus archivos ni contamina las demás; el
  informe distingue raíz.
- **AC-09 — Desaparición por raíz.** Dada una caída o desaparición masiva en una raíz, cuando se
  comprueba, entonces el guardarraíl se aplica **solo a esa raíz**; las demás no se marcan; la
  reaparición revierte solo lo observado.
- **AC-10 — Servicios por raíz.** Dados auditoría, cuarentena, conversión, vinculación, portadas,
  exportación y `ruta_visible`, cuando operan sobre un archivo, entonces usan **su** raíz; una raíz
  caída no hace que se busque en otra ni que se muestre el host de otra; la cuarentena queda en la
  montura de origen.
- **AC-11 — Raíz caída/deshabilitada/llena.** Dada una raíz en esos estados, cuando el importer o
  el escaneo la encuentran, entonces no se crea la carpeta, no se mueve ni se borra nada, no se
  marca ausente por la caída y las demás raíces siguen; el estado se muestra con causa.
- **AC-12 — A3 en destino.** Dados conflicto de destino, disco lleno o cross-device, cuando se
  mueve, entonces no se sobrescribe, se comprueba espacio en **esa** raíz, se copia+verifica antes
  de retirar el original, no hay fallback y un fallo de BD no se presenta como éxito.
- **AC-13 — Seguridad de rutas.** Dadas rutas de Ajustes/BD, cuando se guardan o usan, entonces
  solo se aceptan bajo montajes autorizados, sin solapamientos (igualdad, componentes, inodo,
  symlink resuelto), sin `..`/`/`/`.zascarr`, con escritura comprobada y fallo cerrado; no se crean
  raíces ausentes ni se permiten rutas arbitrarias.
- **AC-14 — Ajustes operables.** Dada la tarjeta de discos, cuando el coleccionista gestiona
  raíces, entonces ve lista/estado/espacio, mapa tradición→raíz, alta solo de montados,
  habilitar/deshabilitar, borrado bloqueado con archivos, cambio de ruta bloqueado, aviso de
  reinicio, mensajes en español llano y a11y mínima.
- **AC-15 — Verificación y no regresión.** Dados los cortes A-D, cuando se cierran, entonces hay
  pruebas PG/FS/navegador y de una raíz; PASS/FAIL/NOT RUN separados; no se declara hecho nada sin
  evidencia; la migración no se aplica a producción sin autorización separada.

### 10.2 Trazabilidad AC → prueba → corte

| AC | Pruebas previstas (nombres propuestos) | Corte |
|---|---|---|
| AC-01 | `test_raices_modelo`, `test_migracion_0041`, `test_validacion_raices` | A |
| AC-02 | `test_mapeo_tradiciones`, `test_migracion_0041` | A |
| AC-03 | `test_importer_dos_raices`, `test_build_library_path_raiz` | B |
| AC-04 | `test_importer_sin_raiz`, `test_importer_raiz_caida` | B |
| AC-05 | `test_unsorted_raiz_defecto`, `test_unsorted_sin_defecto` | B |
| AC-06 | `test_asignacion_raiz`, `test_review_raiz`, `test_asignacion_sin_raiz` | B |
| AC-07 | `test_migracion_compatibilidad_una_raiz` | A |
| AC-08 | `test_rescan_dos_raices`, `test_adopter_raiz_caida` | C |
| AC-09 | `test_desaparicion_por_raiz`, `test_reaparicion_raiz` | C |
| AC-10 | `test_auditoria_por_raiz`, `test_cuarentena_por_raiz`, `test_conversion_raiz`, `test_vinculacion_raiz`, `test_portada_raiz`, `test_ruta_visible_raiz`, `test_export_solape_raices` | C |
| AC-11 | `test_importer_raiz_ausente`, `test_rescan_raiz_deshabilitada`, `test_no_mkdir_raiz` | B/C |
| AC-12 | `test_safe_move_conflicto`, `test_safe_move_disco_lleno`, `test_safe_move_exdev`, `test_commit_tras_move` | B/C |
| AC-13 | `test_validacion_solapes`, `test_symlink_escape`, `test_allowlist_montajes`, `test_no_ruta_arbitraria` | A/C |
| AC-14 | `test_ajustes_raices_browser`, `test_ajustes_a11y_320` | D |
| AC-15 | Suite completa + `test_no_regresion_una_raiz` + PASS/FAIL/NOT RUN | A-D |

### 10.3 Lo que **NO** se hace

- No se crea la migración 0041 ni se aplica.
- No se implementa `RaicesService`, ni `library_roots`, ni `root_id`, ni la UI.
- No se mueven archivos existentes, no se renombran, no se borran, no se crea una raíz ausente.
- No se añade socket Docker, no se montan discos, no se cambia Compose/bootstrap en este encargo.
- No se introduce una raíz por defecto implícita ni un fallback a otra raíz.
- No se declara aprobada ninguna decisión de §2; no se declara hecho A5; no se estima una fecha.
- No se ejecutan pruebas ni se declara PASS lo que está NOT RUN.

---

## 11. Referencias y caducidad

- Ficha: [`benchmark-BL-A5-repartir-tradiciones.md`](benchmark-BL-A5-repartir-tradiciones.md)
  (nivel 2, `main@acb82a40`, 2026-11-14; §1, §4.1-4.6, §5, §7).
- Historia: `docs/BACKLOG.md:49`; issue #156; feature #148.
- Código actual: `src/zascarr/config.py:188,194-196`; `docker-compose.yml:137,171-175`;
  `bootstrap.sh:316,329,347`; `services/importer.py:490,497-532,649-713,741,860-867,914-954`;
  `services/asignacion.py:1-35,377,746,833`; `services/review.py:127,314`;
  `services/library_adopter.py:290,339-357,391,499`; `services/rescan_biblioteca.py:1-15,51-55`;
  `services/library_audit.py:167,207-250`; `services/disponibilidad.py:1-127`;
  `services/apartado_duplicados.py:113,141,153-161,222-228`; `services/conversion.py:205-210`;
  `services/vinculacion.py:185`; `services/exportacion_kavita.py:85-110`;
  `models/__init__.py:36-45,550-553,780-786`; `utils/ruta_visible.py:16-27`;
  `web/auditoria.py:395-399,437`; `web/ajustes.py:167-174,545-553`;
  `scripts/_rutas.sh:87-230`; migración `0040` (cabeza actual).
- Referencias del benchmark: Sonarr/Radarr, Kapowarr, Mylar3 y Komga, leídas por el SCOUT; no
  ejecutadas. Licencias GPL-3.0; no se copia código, solo contratos.
- **Caducidad:** 2027-01-13 (~60 días), o antes si cambia `library_path`, el montaje de Compose,
  el modelo `File`, el importer, el escaneo o alguna referencia. Si cambia, esta spec se revisa y
  no se aplica a ciegas.

---

*Fin de la especificación. Diseño propuesto; no aprobado; no implementado; no migrado.*
