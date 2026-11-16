# Especificación — BL-PACK1: importar series desde paquetes RAR y ZIP de descarga (#344)

> **Estado: DISEÑO PROPUESTO. NO IMPLEMENTADO. MIGRACIÓN NO AUTORIZADA NI APLICADA.** Este
> documento no escribe código, no extrae paquetes, no toca Descargas, la biblioteca, la BD ni
> producción. Las decisiones del PO de §7 están **pendientes**; se recomiendan, no se aprueban.
> **Base:** `origin/main` `79238696` (2026-11-16), worktree `.squad/wt-344`. La ficha de benchmark
> paralela `benchmark-BL-PACK1-paquetes.md` **no existe en este SHA**; se cita cuando se incorpore
> y **esta spec no duplica sus tablas**. Insumos: issue #344 (10 AC), spike #305, evaluación #308,
> benchmark de formatos, contrato #307 y ADR 0015.
> **Corte:** cuatro rebanadas (§8); la historia es **L** no calibrada. Sin autorización de
> migración, solo las rebanadas de lectura (§8) pueden entregarse; la extracción no cierra #344.

---

## 0. Resumen

Hoy el importador recorre **Descargas** solo por extensión (`COMIC_EXTS = {.cbz,.cbr,.cb7,.pdf,.epub}`,
`services/importer.py:72,510-530`): un `.rar` o `.zip` con grapas dentro **no se importa**; la
auditoría de biblioteca lo avisa con causa (`library_audit.py:134,324-369`) y ahí se queda. #344
quiere que el coleccionista vea ese paquete como **«paquete pendiente de revisar»**, pida **a
mano** que se abra, vea qué trae y que las grapas `.cbz`/`.cbr` entren por el flujo normal,
**dejando el paquete intacto**.

La propuesta separa **derivar** de **persistir**: la lista de paquetes pendientes se deriva del
sistema de ficheros (sin tabla ni migración); la operación de extracción, su progreso, su
verificación, su resultado y la supresión del paquete ya importado necesitan una **tabla durable
`paquete_operaciones` (migración 0043 aditiva)**, porque no se pueden derivar de forma fiable y
sin ella un paquete ya procesado reaparecería como pendiente y una muerte a mitad no tendría
comprobante. La extracción va a un temporal **fuera de biblioteca y Descargas**, con topes antes
de escribir y verificación entrada a entrada; solo después se publica una carpeta de entrada en
Descargas para el importador normal. El paquete **no se mueve, renombra ni borra**.

**Decisión de producto pendiente:** conservar el paquete original (recomendado), limpiar el
extraído tras importar (recomendado) y dejar multivolumen para otra historia (recomendado).

---

## 1. Alcance exacto

### 1.1 Entra

- **Solo Descargas**: las carpetas que ya escanea el importador (`transmission_download_dir`,
  `amule_incoming_dir`, `downloads_path`; `importer.py:510-530`, `config.py:157,163,216`). **No
  se lee la biblioteca**; un paquete en la biblioteca no se procesa en #344.
- **Solo a demanda**: el paquete se detecta y se muestra como pendiente; **ningún ciclo, tarea
  periódica ni arranque lo abre, lista o extrae**. La extracción empieza con una petición
  explícita del coleccionista.
- **Paquete intacto**: el original no se mueve, renombra, convierte ni borra; solo se lee. La
  extracción escribe **copias** en un temporal y una carpeta de entrada nueva.
- **Formatos:** RAR (4/5, sólido/no sólido) con `unar`/`lsar` y ZIP con la biblioteca estándar
  (`zipfile`), decididos por **firma de contenido**, no por extensión.
- **Solo grapas `.cbz`/`.cbr`** del contenido pasan al flujo normal; el resto se lista y se
  ignora con causa.
- **Auditoría/UI**: paquete pendiente, listado, topes, vista previa, confirmación, progreso,
  resultado y errores; sin jerga.

### 1.2 No entra (frontera explícita)

| Fuera | Por qué |
|---|---|
| **7z, tar, `.cbt`, `.cba`, `.mobi` u otros contenedores** | Cada uno su tarjeta; #305 los descartó por ahora (`benchmark-formatos-contenedor.md:71-74`) |
| **Auto-extracción, auto-importación o abrir al detectar** | #344 exige «solo a demanda»; ningún proceso automático abre paquetes |
| **Borrar o mover el paquete original** | El original es del PO; #344 lo conserva. Papelera/limpieza es otra historia |
| **Leer paquetes de la biblioteca** | #344 es Descargas; la biblioteca la cubre #307/adopción, no esto |
| **Renombrar, convertir o normalizar el paquete** | La conversión CBR→CBZ ya existe en **BL-CNV** (backlog B10, `docs/BACKLOG.md:98`) y es otra decisión; aquí no se convierte el paquete |
| **Recursión en paquetes anidados** | Un paquete dentro de otro se **avisa y rechaza**; no se abre el de dentro (AC1) |
| **Multivolumen `.partN.rar`/`.r00`** | Decisión del PO recomendada: historia siguiente; aquí se detecta y se rechaza con causa |
| **Cifrado/contraseña** | No se pide contraseña; se rechaza con causa |
| **Cambios de identidad editorial, catálogo, `File` de la biblioteca** | El paquete no crea `File`; los `.cbz/.cbr` extraídos entran por el importer normal |
| **Instalar `unar` en la imagen** | Ya está en la imagen por ADR 0015; su despliegue y revisión de vulnerabilidades siguen su ventana. #344 no instala nada por sí sola |

**Frontera con #159/B10/BL-CNV:** la conversión CBR→CBZ y su cadena de preferencia ya están
entregadas en BL-CNV (B10 «repartida», `docs/BACKLOG.md:98`); #344 **no convierte**, solo extrae
paquetes de Descargas y entrega las grapas al importer. Un `.cbr` extraído se registra como
cualquier `.cbr` (hoy solo hash, sin portada; la conversión seguirá siendo una acción aparte).

---

## 2. Contrato de datos y estado

### 2.1 Qué se deriva (sin migración)

**Paquete pendiente** = fichero en una carpeta de Descargas que:

1. tiene extensión final `.rar` o `.zip` (incluye dobles `.rar.zip`/`.zip.rar`; no `.cbz`/`.cbr`,
   que son cómics normales), y
2. su **firma** de contenido es `RAR` o `ZIP` (`core/formato_contenedor.py:88-106`), y
3. no coincide con una operación de paquete **`importado`** de la misma identidad (si la tabla
   existe; §2.2).

`PaquetePendiente` es un **DTO derivado**, no una fila: ruta absoluta/relativa, nombre, tamaño,
`mtime`, firma, carpeta de descarga, y si hay una operación en curso/error. Se calcula al abrir la
pantalla o al pedir la lista; no se guarda. Un paquete que cambia de tamaño/mtime/inodo vuelve a
ser pendiente aunque hubiera sido importado.

**Nada de runtime settings ni `File.metadata_` para el estado:** runtime settings es JSONB de
configuración, no una cola de operaciones; `File` no existe para el paquete; `ImportRun.details`
es un informe de pantalla truncado a 200 y no sirve para reanudar (mismo motivo que en ADR 0017
§D3). Un diario JSON en el temporal no sobrevive de forma fiable a la limpieza y no permite
consultar la UI.

### 2.2 Qué se persiste (migración propuesta 0043)

La extracción **sí** necesita estado durable: progreso, causas, reanudación/reintento, evitar dos
extracciones del mismo paquete y **suprimir de pendientes** un paquete ya importado. Se propone
una migración **0043** (siguiente tras la cabeza actual `0042_favoritos`), **aditiva y
reversible**:

```text
paquete_operaciones
  id UUID PK
  paquete_clave text NOT NULL        # identidad estable: path + dev + ino + size + mtime_ns + firma
  paquete_path text NOT NULL         # ruta absoluta; no se muestra en logs
  paquete_dev bigint NOT NULL
  paquete_ino bigint NOT NULL
  paquete_size bigint NOT NULL
  paquete_mtime_ns bigint NOT NULL
  firma text NOT NULL                # zip | rar
  estado enum NOT NULL               # listando|extrayendo|verificando|publicando|importando|importado|error
  temp_dir text NULL                 # temporal fuera de biblioteca/Descargas; se borra siempre
  staging_dir text NULL              # carpeta oculta de publicación en Descargas
  destino_dir text NULL              # carpeta final de entrada en Descargas
  items JSONB NOT NULL DEFAULT '[]'  # una entrada por fichero: estado, nombre, tamaño, CRC, destino
  total_entradas int, total_bytes bigint
  error_codigo text NULL, error_mensaje text NULL
  creada timestamptz, actualizada timestamptz, finalizada timestamptz NULL
  UNIQUE parcial (paquete_clave) WHERE estado IN ('listando','extrayendo','verificando','publicando','importando')
  INDEX (paquete_clave), (estado), (creada)
```

- **Estados:** `listando` (lista y topes), `extrayendo` (solo temporal), `verificando` (entrada a
  entrada), `publicando` (carpeta de entrada, aún fuera del alcance del importer),
  `importando` (flujo normal), `importado` (paquete original intacto y resultado guardado),
  `error` (causa y acción; el paquete vuelve a pendiente/reintentable). No se persiste
  `pendiente`: es derivado.
- **Identidad:** `paquete_clave` = combinación normalizada de `path`, `(st_dev, st_ino)`, tamaño,
  `mtime_ns` y firma. **No se hashea el paquete entero por defecto**: puede ser de varios GB y el
  hash no aporta seguridad frente a un cambio de fichero (el stat sí); la firma y el stat son la
  identidad operativa. Se puede añadir `sha256` opcional en otra historia si hace falta
  deduplicación/evidencia; no es requisito de #344.
- **Idempotencia:** token y `id` de operación; un mismo token no extrae dos veces; una operación
  `importado` no se reaplica. El índice parcial impide dos operaciones vivas de la misma
  identidad.
- **Retención:** la fila se conserva para poder explicar el resultado y suprimir pendientes; no
  guarda archivos. Una limpieza de filas antiguas es una decisión posterior (no automática en
  #344). `temp_dir`/`staging_dir` se intentan borrar al terminar y al arrancar si quedaron
  huérfanos; la fila no apunta a ellos después.
- **Migración:** `0043_paquete_operaciones.py`, enum Postgres explícito y `down` que elimina la
  tabla/tipo. **No se aplica en este encargo**; sin ella, la rebanada de extracción no se
  implementa (solo lectura/listado, §8).

### 2.3 Estados y transiciones

```text
(pendiente derivado)
   └─ solicitud de listado (sin fila)
        └─ confirmación → [listando] → [extrayendo] → [verificando]
             → [publicando] → [importando] → [importado]
             └─ cualquier fallo → [error] → reintento (nueva operación o misma con token nuevo)
```

- `listando`: solo lectura de metadatos/listado; no escribe ficheros. Si supera topes/nested/
  cifrado/multivolumen → `error` sin temp.
- `extrayendo`: escribe **solo** en `temp_dir`; nunca en biblioteca/Descargas.
- `verificando`: comprueba tamaño/CRC/imagen; si falla, borra temp y `error`; no publica.
- `publicando`: crea la carpeta de entrada en Descargas y la deja completa; no hay ficheros
  parciales visibles.
- `importando`: el importer normal procesa la carpeta; resultado por ítem.
- `importado`: el original sigue en Descargas intacto; la carpeta extraída puede quedar vacía y
  se limpia; la operación suprime el paquete de pendientes por su identidad.
- `error`: causa/acción; temp y staging limpiados; original intacto; reintentable.

---

## 3. Contrato de comportamiento (EARS)

### 3.1 Detección por firma

- **Cuando** se abre la lista de paquetes de Descargas, **el sistema** recorre solo las carpetas
  de Descargas configuradas y considera candidatos los ficheros con extensión final `.rar` o
  `.zip`, **sin abrirlos ni descomprimirlos**.
- **Cuando** un candidato se lee por firma (≤512 bytes, `firma_de`,
  `core/formato_contenedor.py:88-106`), **el sistema** lo clasifica como RAR/ZIP por contenido:
  `.rar` que por dentro es ZIP, `.zip` que por dentro es RAR, `.rar.zip`/`.zip.rar` y dobles
  extensiones se muestran igual; la extensión no decide el lector.
- **Cuando** un fichero con extensión `.rar`/`.zip` no tiene firma RAR/ZIP, **el sistema** no lo
  presenta como paquete importable; lo marca «no es un paquete legible» con causa, sin extraer.
- **Cuando** hay un paquete **dentro** de otro, **el sistema** lo detecta al listar el exterior,
  muestra «contiene otro paquete» y **rechaza la operación completa**; no abre el interior, no
  extrae el exterior y no crea recursión.
- **Cuando** el nombre indica multivolumen (`.partN.rar`, `.r00`, `.r01`…), **el sistema** lo
  rechaza con causa «paquete dividido en varios archivos» y no extrae; el multivolumen real queda
  para la historia siguiente.
- **Cuando** dos paquetes tienen el mismo contenido/nombre, **el sistema** no los une ni elige
  uno; cada ruta es un pendiente distinto (la identidad incluye ruta/inodo).

### 3.2 Listar antes de escribir y topes

- **Cuando** el coleccionista pide «ver qué contiene» (sin confirmar), **el sistema** lista el
  paquete **sin escribir ni extraer nada** y devuelve entradas, tamaños declarados, CRC si consta,
  tipo (`.cbz`/`.cbr`/otro), y qué se importaría/ignoraría.
- **Cuando** el listado supera un tope, **el sistema** rechaza con la causa concreta (entradas,
  tamaño total, tamaño por entrada, ratio, directorio central, salida) y **no crea temporal**.
  Topes propuestos, revisables por el PO/implementación:
  - **Entradas:** ZIP ≤ 2.000 (`MAX_ENTRADAS`, `formato_contenedor.py:54`); RAR ≤ 1.000
    (`RAR_MAX_ENTRADAS`, `lector_rar.py:42`); no se suben por esta historia.
  - **Tamaño declarado total del paquete:** ≤ **8 GiB** para el paquete completo (valor nuevo de
    #344; el límite de 500 MiB de `RAR_MAX_BYTES_DECLARADOS` es para leer **una página**, no para
    un paquete; `lector_rar.py:43`). Se justifica por los paquetes reales de varios GB del issue
    y por el disco temporal; **no está medido en la Pi para paquetes** (NOT RUN).
  - **Tamaño por entrada extraída:** ≤ **2 GiB** (una grapa/tebeo dentro del paquete); por
    encima, paquete rechazado.
  - **Ratio de compresión:** ≤ 100 por entrada ZIP (`MAX_RATIO_LEIDA`,
    `formato_contenedor.py:60`); en RAR no se puede calcular el ratio con el listado de `lsar`,
    así que se acota por **bytes escritos** y por tamaño declarado (no se finge un ratio).
  - **Directorio central ZIP:** ≤ 1 MiB (`MAX_DIRECTORIO_CENTRAL`,
    `formato_contenedor.py:69`); no se abre un ZIP con un índice mayor.
  - **Salida de listado RAR:** 4 MiB (`RAR_MAX_SALIDA_LISTADO`, `lector_rar.py:44`);
    `lsar -j -json-skip-solid-information` ya evita el sólido grande (#528).
  - **Entradas aceptadas:** solo `.cbz`/`.cbr`; si no hay ninguna, error «no contiene tebeos»
    antes de escribir.
- **Cuando** el listado declara un tamaño/CRC que no coincide con la extracción, **el sistema**
  no confía en el listado y verifica (3.4); un `rc 0` o un listado corto **no** son prueba
  (evaluación #308: `lsar` lista un truncado con código 0 y `unar` sale 0 sin escribir,
  `evaluacion-lector-rar-tanda2-2026-10-23.md:64-65`).
- **Cuando** el paquete está cifrado/protegido, **el sistema** rechaza con «tiene contraseña»; no
  pide contraseñas ni intenta fuerza bruta.
- **Cuando** el paquete está truncado o el listado es ilegible, **el sistema** rechaza con causa
  y no extrae.

### 3.3 Espacio y temporal

- **Cuando** el listado indica el tamaño declarado, **el sistema** comprueba el espacio libre del
  **temporal** (y de la carpeta oculta de publicación, si es otra) antes de escribir; si no hay
  margen, error «no cabe» **antes de empezar**, nunca a mitad.
- **Cuando** se extrae, **el sistema** usa un directorio temporal acotado **fuera de la
  biblioteca y de Descargas** (propuesta: `<covers_cache_path>/.paquetes/`, `config.py:224`; se
  puede añadir `PACK_TMP_PATH` si el operador quiere otro disco), con permisos `0700`, propiedad
  del UID/GID del servicio y limpieza garantizada (`try/finally`).
- **Cuando** el temporal no se puede crear/escribir o el disco se cae, **el sistema** falla
  cerrado, no toca el paquete, limpia lo que haya creado y deja causa accionable.
- **Cuando** el paquete supera el espacio disponible del temporal, **el sistema** no elige otro
  disco ni extrae parcialmente; el paquete sigue pendiente.

### 3.4 Extraer con control y verificar

- **Cuando** se confirma la extracción con un token válido, **el sistema** vuelve a comprobar la
  identidad del paquete (stat/firma) y el listado antes de escribir; si cambió, rechaza el token
  y pide repetir la vista previa.
- **Cuando** extrae un ZIP, **el sistema** usa `zipfile`/stdlib en un **proceso de trabajo
  acotado** (no en el bucle de eventos): cada entrada se escribe a un nombre generado dentro del
  temporal, nunca a partir del nombre de la entrada; si el nombre declara `..`, ruta absoluta,
  enlace simbólico o duro, se rechaza la entrada/paquete. El proceso tiene **timeout**, grupo de
  procesos propio y tope de memoria/bytes; se mata el grupo al vencer.
- **Cuando** extrae un RAR, **el sistema** reutiliza `utils/lector_rar.py` (sin shell, ruta
  absoluta, entorno mínimo, grupo de procesos, timeout, RSS 128 MiB, salida acotada,
  `RAR_SIMULTANEOS=1`, `lector_rar.py:42-64,197-247,391-425`), **por índice**, no por nombre
  (los nombres llevan comodines), con tope de bytes escritos y verificación de que el temporal
  solo contiene el fichero esperado.
- **Cuando** termina una entrada, **el sistema** comprueba: existe, es fichero regular (no
  symlink), tamaño = declarado, CRC = declarado si consta, y el fichero no ha salido del
  temporal. Si algo falla, **no publica nada**: borra temporal y marca error.
- **Cuando** la entrada extraída es un `.cbz`/`.cbr`, **el sistema** verifica que su firma
  corresponde al formato declarado (`ZIP` para `.cbz`, `RAR` para `.cbr`; si no, rechaza el
  fichero con causa), que el contenedor se puede listar y que **la primera imagen decodifica**
  (Pillow, con el tope de píxeles de #307, `formato_contenedor.py:70`). No se abren todas las
  imágenes: se verifica la entrada del contenedor y su primera página; el resto queda para el
  flujo normal.
- **Cuando** una entrada no es `.cbz`/`.cbr`, **el sistema** la lista como ignorada (imágenes
  sueltas, `.txt`, `.nfo`, `.html`, PDF/EPUB) y **no la escribe**; no es un fallo si el paquete
  tiene al menos una grapa válida.
- **Cuando** el número de entradas extraídas no coincide con las aceptadas del listado, **el
  sistema** rechaza el paquete; un listado corto no pasa.

### 3.5 Publicar e importar

- **Cuando** todas las grapas aceptadas están verificadas, **el sistema** las publica en una
  **carpeta de entrada nueva** dentro de la misma carpeta de Descargas del paquete, con nombre
  seguro y sin sobrescribir; la publicación se hace completa (carpeta oculta
  `<descargas>/.zascarr/paquetes/<operacion>/` → rename a
  `<descargas>/<nombre-del-paquete> (extraído)/`) para que el importer no vea ficheros a medias.
  `.zascarr` ya se excluye de `listar_comics`/`recorrer_comics` (`utils/fs.py:666-760`).
- **Cuando** la carpeta de entrada está publicada, **el sistema** lanza el flujo normal de
  importación (`Importer.scan_and_import`, `importer.py:510-530`), que solo ve `.cbz/.cbr` por
  `COMIC_EXTS`; no crea `File` para el paquete ni para las entradas ignoradas.
- **Cuando** el importer termina, **el sistema** mapea el resultado por fichero: importado,
  duplicado, a revisar o error; guarda el resumen en `items` y solo marca `importado` si todas
  las grapas publicadas tienen un resultado verificado. Si el importer falla o deja alguna sin
  procesar, la operación queda `error`/`importando` y se puede reintentar; no se anuncia
  importado sin comprobación.
- **Cuando** la importación termina, **el sistema** borra el temporal y, si la carpeta de entrada
  quedó vacía, la retira; **no borra ni mueve el paquete original**. El paquete `importado` deja
  de aparecer como pendiente por su identidad; si cambia, vuelve a aparecer.
- **Cuando** el paquete contiene una grapa duplicada de algo ya en el catálogo, **el sistema**
  aplica el comportamiento normal del importer (duplicado descartado, sin borrar el paquete); lo
  informa en el resultado.
- **Cuando** el contenido extraído no se puede importar por una causa normal (sin serie → `_Unsorted`,
  etc.), **el sistema** no lo considera fallo del paquete: el importer lo coloca en «Por revisar»
  y la operación informa «importado con pendientes» o el estado que corresponda, sin borrar nada.

### 3.6 Original, errores y reintento

- **Cuando** algo falla (listado, topes, contraseña, truncado, nested, multivolumen, espacio,
  timeout, permisos, extracción, verificación, importación), **el sistema** conserva el paquete
  **exactamente** donde estaba, limpia temporal/staging y muestra **causa + acción**; el paquete
  vuelve a «pendiente» o queda en `error` reintentable.
- **Cuando** el proceso muere entre estados, **el sistema** al arrancar marca las operaciones
  vivas como `error` recuperable, borra temporales huérfanos y deja el paquete pendiente; **no
  reanuda una extracción a medias**: el reintento es una operación nueva/limpia, idempotente, sin
  duplicar ficheros ni catálogo.
- **Cuando** el paquete se modifica durante la operación (stat/mtime/tamaño/inodo distinto),
  **el sistema** aborta con «el paquete cambió» y no publica; el original no se toca.
- **Cuando** el paquete se elimina/mueve durante la operación, **el sistema** aborta con causa;
  no recrea el paquete.
- **Cuando** el paquete ya fue importado y no cambió, **el sistema** no lo vuelve a ofrecer como
  pendiente; muestra el resultado histórico.
- **Cuando** el coleccionista reintenta un `error`, **el sistema** vuelve a listar y a verificar
  desde cero; no reutiliza ficheros de un temporal anterior.

### 3.7 Auditoría e informe

- **Cuando** termina una operación, **el sistema** deja en la UI/registro: paquete, firma,
  estado, recuentos, grapas importadas/ignoradas, bytes, causa de error y si el original sigue.
  No publica rutas completas, nombres de terceros ni hashes en logs; en la UI muestra lo necesario
  para encontrar el paquete.
- **Cuando** la auditoría de biblioteca se ejecuta, **no** procesa paquetes (solo avisa de
  contenedores en biblioteca, `library_audit.py:134,324-369`); #344 no cambia esa auditoría.
- **Cuando** el paquete está en Descargas y no en la biblioteca, **no** aparece en «Por revisar»
  (que es cola de catálogo): aparece en la sección de paquetes de Descargas de Auditoría.

---

## 4. Seguridad

### 4.1 Detección y decisión

- **Firma, no extensión:** `firma_de` lee ≤512 bytes; no se abre el paquete para decidir tipo
  (`core/formato_contenedor.py:88-106`). Es la misma lección de #307/#308 (un `.cbr` puede ser
  ZIP y un `.zip`/`.rar` puede ser lo contrario).
- **Solo candidatos de Descargas:** no se recorre la biblioteca ni rutas arbitrarias; las
  carpetas son las de `config.py:157,163,216`, sin seguir symlinks de directorio.
- **No auto-extracción:** ninguna tarea de fondo abre un paquete; el listado/extracción requieren
  petición explícita y token.

### 4.2 Listado y topes

- **Antes de escribir un solo byte** se lista y se aplican los topes de §3.2. Los topes se
  aplican sobre el **listado declarado** y, después, sobre lo **realmente escrito**; no se confía
  en el tamaño/CRC declarados.
- **ZIP:** se comprueba el registro final/central con el mismo lector que `zipfile`
  (`zipfile._EndRecData` encapsulado, `formato_contenedor.py:120-155`), se limita el índice a
  1 MiB, y al leer cada entrada se comprueba tamaño declarado, ratio, bytes reales y CRC
  (`leer_acotado`, `formato_contenedor.py:242-260`). Un ZIP que declara poco y descomprime mucho
  se corta por bytes reales, no por la cabecera.
- **RAR:** `lsar -j` acotado a 4 MiB/entradas/bytes declarados; `unar` por índice, con RSS
  128 MiB, timeout, grupo de procesos, salida y bytes escritos acotados; no se usa `RLIMIT_AS`
  (mata a `unar`, ADR 0015). Un RAR sólido puede tardar segundos en listar; se cachea el listado
  de la operación y no se repite por cada entrada.
- **Bomba de descompresión:** para ZIP, ratio/tamaño/bytes reales; para RAR, bytes escritos por
  entrada y total + RSS/timeout. **No hay ratio fiable en RAR**; se dice y se acota por salida.
- **Paquete anidado:** se detecta por extensión de contenedor en el listado
  (`EXT_CONTENEDOR`, `formato_contenedor.py:46-52`); se rechaza el paquete entero, sin abrir el
  interior.
- **Cifrado:** cualquier entrada cifrada (ZIP flag, `XADIsEncrypted` de `lsar`) → rechazo con
  «tiene contraseña»; no se pide contraseña.
- **Multivolumen/truncado:** `lsar`/firma no completos; rechazo con causa; no se intenta unir
  volúmenes.

### 4.3 Aislamiento de la extracción

- **Temporal fuera de biblioteca/Descargas**, `0700`, sin symlinks; el paquete original se abre
  en solo lectura. Nada se escribe junto al original.
- **Proceso de trabajo:** ZIP en subproceso propio (stdlib `zipfile` no se puede matar desde un
  hilo); RAR con `unar` en subproceso. Sin shell, ruta absoluta, entorno mínimo, `cwd` temporal,
  `start_new_session`/grupo de procesos, timeout y kill del grupo; sin red. Un solo paquete a la
  vez (`PACK_SIMULTANEOS=1`) por CPU/memoria de la Pi.
- **Path traversal/symlink/hardlink:** no se usan nombres del paquete para construir rutas; se
  extrae a nombres generados; después de extraer se comprueba `lstat` (regular, no symlink) y que
  el destino real esté dentro del temporal; se rechazan entradas con nombres absolutos, `..`,
  separadores o enlaces. Un `.cbz`/`.cbr` extraído se valida como contenedor y no se sigue ningún
  enlace interno.
- **Memoria/CPU:** presupuesto del contenedor 512 MiB; RAR RSS ≤128 MiB (ya medido 25,8 MiB en
  #308); ZIP worker con tope de memoria propio; un paquete a la vez; timeout por operación y por
  entrada; `pids`/procesos acotados por el contenedor.
- **Temporal limpiable:** `try/finally` y barrido al arrancar; si el disco se llena, se aborta y
  se borra; nunca se deja un temporal con contenido del PO sin dueño.

### 4.4 `unar` ya adoptado

- `unar`/`lsar` están en la imagen por **ADR 0015** (aceptado 2026-11-07), con las mitigaciones
  de `utils/lector_rar.py`: entorno mínimo, proceso propio, timeout, RSS, salida y bytes
  acotados, extracción por índice, un lector a la vez, `no-new-privileges` y límite de procesos
  en Compose.
- **Revisión de vulnerabilidades pendiente:** ADR 0015 declara que no hay análisis de código ni
  fuzzing y que la ausencia de CVE no es prueba de ausencia; antes de **desplegar** #344 hay que
  pasar la revisión de `unar`/GNUstep que el issue exige. Si aparece CVE aplicable, el lector se
  retira (`LECTOR_RAR_ENABLED=false`) y #344 no puede extraer RAR; los ZIP siguen con stdlib.
- **No se instala nada nuevo en #344:** la dependencia ya está; el despliegue de la imagen y la
  revisión son una puerta separada.

---

## 5. UX mínima

### 5.1 Dónde aparece

- **Auditoría → «Paquetes en Descargas»** (nueva sección; no «Por revisar», que es cola de
  catálogo). Cada fila: nombre, ruta relativa a la carpeta de descarga, tamaño, fecha, firma
  legible («ZIP»/«RAR») y estado: **Pendiente**, **En curso**, **Con error**, **Importado**.
- El paquete es un **contenedor**, no un tebeo: no se muestra como serie/número ni se marca como
  duplicado. La frase de entrada: «Paquetes comprimidos en Descargas que puedes abrir para
  importar los tebeos que contienen.»
- Botón **«Ver qué contiene»** (secundario): lista sin escribir. Si el paquete no se puede
  listar, explica la causa y no ofrece extraer.
- Vista previa: grapas que se importarán, contenido ignorado (con causa en una línea), espacio
  temporal necesario, y aviso «El paquete original no se mueve ni se borra.».
- Botón principal **«Extraer e importar»** solo en la vista previa; confirmación explícita. Sin
  elección de copia/premarcado: no aplica.
- Progreso: «Leyendo el paquete…», «Extrayendo 3 de 12…», «Comprobando…», «Importando…»; estado
  `role="status"`, sin bloquear la página; si tarda, se puede salir y volver (estado durable).
- Resultado: importados, ignorados, duplicados, a revisar, errores; «El paquete sigue en
  Descargas.» y botón «Reintentar» si error. No hay «borrar el paquete» en #344.
- Historial/errores: el paquete con error vuelve a la lista con causa y acción; no desaparece en
  silencio.

### 5.2 Textos y accesibilidad

- Español llano; sin «entrada», «firma», «contenedor», «ratio», «CRC», «zip-bomb», «proceso» ni
  rutas del contenedor. Ejemplos:
  - «El paquete tiene contraseña. ZascArr no la pide; quita la contraseña o extrae el contenido
    tú.»
  - «El paquete está incompleto (parece que falta una parte). Descárgalo de nuevo.»
  - «Contiene otro paquete dentro. Ábrelo fuera de ZascArr o espera a que se soporte.»
  - «No cabe en el espacio temporal. Libera espacio y vuelve a intentarlo.»
  - «Se ha tardado demasiado y se ha cancelado; el paquete no se ha tocado.»
- **Presupuesto de texto:** frase de entrada ≤20 palabras; ≤50 palabras antes de la primera
  acción; detalle técnico en `<details>`; resumen antes del listado.
- **A11y:** `<button>` nativos, foco al resultado/errores, `role="status"`/`aria-live`, estado
  con texto no solo color, 320 px sin scroll horizontal, texto ≥14 px; respetar el sistema de
  diseño (`docs/design/sistema-de-diseno-zascarr.md`).
- Sin `hx-confirm` ni diálogos nativos; confirmación en pantalla con garantía junto al botón.

---

## 6. Plan de pruebas

### 6.1 Unitarias (sin BD)

| Grupo | Casos | Criterio |
|---|---|---|
| Detección | `.rar` RAR, `.zip` ZIP, `.rar` que es ZIP, `.zip` que es RAR, `.rar.zip`, `.zip.rar`, extensión mentirosa, fichero vacío | Firma correcta; candidato/no candidato; no abre contenido |
| Listado | ZIP/RAR normal, paquete con 1 y N `.cbz/.cbr`, solo imágenes, solo TXT, PDF/EPUB, anidado, multivolumen, cifrado | Clasificación y causas; no extrae |
| Topes | entradas, total, por entrada, ratio ZIP, directorio, salida RAR; cada tope aislado | Rechazo por la causa exacta; no escribe |
| Nombres | `../`, absoluto, `..\\`, control, symlink/hardlink ZIP, nombre con comodines RAR | No se usa el nombre para la ruta; rechazo |
| Espacio | temporal sin espacio, cuota, disco lleno simulado | Error antes de extraer; original intacto |
| Verificación | tamaño/CRC falsos, listado corto, `rc 0` sin fichero, imagen corrupta, `.cbz` que es RAR | Rechazo; no publica |
| Limpieza | excepción, timeout, muerte simulada | Temp borrado; sin ficheros a medias |
| Textos UX | causas/acciones | Sin jerga; causa+acción; reglas de presupuesto |

### 6.2 Postgres real (si se autoriza 0043)

- Migración `0043`: tabla/enum/índice parcial; `upgrade`/`downgrade`; no toca `File`/biblioteca.
- Identidad/`paquete_clave`: dos operaciones vivas de la misma identidad → una sola; paquete
  cambiado → nueva identidad.
- Estados: `listando→…→importado`; fallo → `error`; reintento; idempotencia por token/id.
- Supresión de pendientes: `importado` con misma identidad no reaparece; modificar el paquete
  (mtime/size) sí.
- Muerte entre estados: operaciones vivas se marcan recuperables; no duplican; limpieza.
- No se crea `File` para el paquete; los `.cbz/.cbr` publicados los crea el importer normal.

### 6.3 Sistema de ficheros real / importer

- Paquete real sintético con 2–3 `.cbz`/`.cbr` y ruido; extraer, verificar, publicar, importar;
  original con mismo hash/mtime; biblioteca recibe las grapas; ignorados no aparecen.
- ZIP bomba (muchas entradas / gran descompresión / ratio alto), ZIP con `..`/symlink, ZIP
  truncado, RAR con `unar` real (si CI lo tiene) y RAR cifrado/truncado.
- Disco lleno, permisos, temporal no escribible, paquete borrado/movido durante la operación.
- Muerte del proceso entre extraer y publicar/importar; reanudación desde cero; sin fichas
  huérfanas ni duplicados.
- Paquete en cada una de las 3 carpetas de Descargas; dedupe por inodo; no procesa biblioteca.
- Original intacto en todos los fallos; staging `.zascarr` no visible al importer; carpeta final
  completa antes de importar.
- Importación normal: `.cbz`/`.cbr` según firma; `.cbz` que es RAR / `.cbr` que es ZIP → rechazo
  con causa (no se renombra ni se registra mal).

### 6.4 Navegador y rendimiento

- Navegador real (Playwright/arnés del repo): sección en Auditoría, lista, vista previa, confirmar,
  progreso, resultado, error, reintento; estados con texto, foco, teclado, 320 px; sin jerga.
- **Presupuesto:** memoria del contenedor 512 MiB; RAR RSS ≤128 MiB (medido 25,8 MiB en #308);
  ZIP worker con tope; temporal ≤ tamaño declarado + margen; un paquete a la vez. **p95 de
  extracción/importación de un paquete realista en la Pi: NOT RUN**; hay que medirlo antes de
  desplegar (tiempo, pico de RSS, pico de disco temporal) y registrar PASS/FAIL. Los números de
  #308 (≤25,8 MiB, primera página ≤0,09 s caliente, ~0,33 s frío; listado de 324 entradas 0,2 s)
  son de **lectura de RAR**, no de extracción de paquetes; no se extrapolan.

### 6.5 PASS / FAIL / NOT RUN de esta spec

- **PASS:** lectura del issue #344, #305/#308, `benchmark-BL-PACK1-paquetes.md`, benchmark de formatos, contrato #307, ADR 0015 y
  código de importer/lector/auditoría; contrato y pruebas definidos; sin ejecución.
- **FAIL:** ninguno de la spec. Un fallo real solo aparece al implementar/probar.
- **NOT RUN:** detección/listado/extracción reales, migración 0043, pruebas, paquetes reales,
  Pi, navegador, `unar` con paquetes (seguridad/vulnerabilidades y bomba real), multivolumen,
  extracción RAR5 sólida, y la ficha `benchmark-BL-PACK1-paquetes.md` (no existe en `79238696`;
  se cita cuando se incorpore, sin duplicar).

---

## 7. Decisiones del PO (pendientes)

| # | Decisión | Opciones | Recomendación | Estado |
|---|---|---|---|---|
| 1 | **¿Extraer y limpiar o conservar copia extraída?** | (a) extraer a temporal, importar y limpiar; (b) conservar la carpeta extraída en Descargas; (c) preguntar cada vez | **(a)** extraer a temporal, importar y limpiar temporal/carpeta vacía; el paquete original se queda. Evita duplicar espacio y una segunda copia que confunda al importer | **PENDIENTE** |
| 2 | **¿Original tras importación verificada?** | (a) conservar siempre; (b) ofrecer mover a papelera; (c) borrar | **(a) conservar siempre**; no hay borrado ni papelera en #344. Una limpieza explícita es otra historia/ADR | **PENDIENTE** |
| 3 | **¿Multivolumen en esta historia o la siguiente?** | (a) ahora; (b) siguiente | **(b) siguiente.** A5 detecta `.partN.rar`/`.r00` y rechaza con causa; implementar la unión de volúmenes añade superficie y no está en el alcance del issue | **PENDIENTE** |

**Ninguna está aprobada.** Si el PO elige (b) en 1 o 2, cambia el contrato de limpieza/original
y hay que actualizar esta spec antes de implementar; si elige multivolumen ahora, se amplía el
alcance y la estimación. La recomendación de producto no sustituye la decisión.

---

## 8. Partición, estimación y riesgos

### 8.1 Cortes verticales acumulativos

> La ficha de benchmark propone cuatro cortes **técnicos** (listado, ZIP, RAR, robustez). Los de
> abajo son **funcionales** y los contienen: 1 = detección/pendientes (listado), 2 = listar/topes/
> vista previa, 3 = extracción/verificación (ZIP+RAR+robustez), 4 = publicación/importación/UI.
> Manda la numeración funcional; los técnicos sirven para ordenar el trabajo dentro del corte 3.

| Corte | Contenido | ¿Cierra #344? | Esfuerzo | AC del corte |
|---|---|---|---|---|
| **1 · Detección y pendientes** | `PaquetePendiente` derivado de Descargas; firma; lista/estado; UI sección; sin abrir/extractar; sin migración | No (solo lectura) | **M** | AC1, AC6 (lista), AC9/10 parcial |
| **2 · Listado, topes y vista previa** | Listar ZIP/RAR sin escribir; topes; nested/cifrado/multivolumen/incompleto; vista previa y token; sin migración | No (aún no extrae) | **M/L** | AC1, AC2, AC3, AC8 (listado), AC10 |
| **3 · Extracción y verificación durable** | Migración 0043; temporal/proceso; verificación entrada a entrada; estado/reanudación; limpieza | Parcial | **L** | AC4, AC5, AC7, AC8 |
| **4 · Publicar, importar y UI completa** | Carpeta de entrada, importer normal, resultado por grupo, progreso, reintento, supresión de pendientes, navegador | Sí, con 1-4 | **M/L** | AC6, AC7, AC9, AC10, AC3 UI |

**Dependencias:** 1 → 2 → 3 → 4. Sin migración 0043, el corte 3 no se implementa y #344 no se
cierra; los cortes 1-2 pueden entregarse como lectura/preview, pero no cumplen el objetivo de
importar. **No hay un corte que cierre #344 sin extracción + importación.**

### 8.2 Estimación

- **L, no calibrada.** Toca UI/Auditoría, nueva sección, detección por firma, ZIP/RAR, topes,
  subproceso/tiempo/memoria, temporal, verificación, publicación, importer, tabla/migración,
  reanudación y pruebas hostiles en Pi. No es M: el camino feliz es pequeño, pero la seguridad y
  la recuperación son la mayor parte.
- **Sin fecha ni compromiso de sprint.** Los cortes 1-2 son M; 3 es L; 4 M/L. El total no baja de
  L. Se refina con la implementación y la medición real; no se promete un plazo.

### 8.3 Riesgos principales y mitigación

| Riesgo | Mitigación |
|---|---|
| Bomba ZIP/RAR | listar antes; entradas/tamaño/ratio (ZIP) o bytes/RSS/timeout (RAR); no confiar en cabeceras |
| Path traversal/symlink/hardlink | extraer por índice a nombres generados; `lstat`; destino dentro del temporal; no seguir enlaces |
| `unar` comprometido | mitigaciones ADR 0015, un lector, entorno mínimo, proceso aislado; revisión de vulnerabilidades antes de desplegar |
| Disco lleno en Pi | comprobar espacio del temporal y de publicación antes; abortar; no fallback |
| Muerte entre extraer/publicar/importar | tabla durable; estados; limpieza; reintento desde cero; sin fichas huérfanas |
| Paquete modificado | stat/firma y listado revalidados; token; abortar sin tocar |
| Reaparición de paquete ya importado | `paquete_operaciones` con identidad; supresión solo si no cambió |
| Paquete real > topes | rechazo con causa; medir/ajustar con datos reales, no subir topes a ciegas |
| `unar` apagado/ausente | RAR no se ofrece para extraer; ZIP sigue; causa clara; no fingir éxito |
| Original dañado | nunca se escribe/mueve/borra; solo lectura; verificación en copia |
| Multivolumen/nested | rechazo con causa; no abrir interior; no unir volúmenes |
| Cifrado | rechazo con causa; no pedir contraseña |
| UI miente sobre progreso | estados durables y polling; no `importado` hasta comprobar; causa/acción |

---

## 9. Trazabilidad AC #344 → contrato y pruebas

| AC #344 | Dónde se cumple | Pruebas |
|---|---|---|
| 1. Detecta por firma; anidado avisa | §3.1, §5.1 | detección unitaria; nested |
| 2. Listar antes de extraer y topes | §3.2, §4.2 | listado/topes aislados |
| 3. Espacio comprobado | §3.3 | disco lleno/simulado |
| 4. Extrae con control, sin path/symlink | §3.4, §4.3 | path traversal/symlink/timeout |
| 5. Verifica siempre | §3.4 | tamaño/CRC/listado corto/imagen |
| 6. Solo `.cbz/.cbr` entran; auditoría dice qué | §3.5, §3.7 | paquete mixto/ruido/ignorados |
| 7. Original intacto y reversible | §3.5-§3.6, §4.4 | hash/mtime del original en éxito/fallo |
| 8. Fallos con causa, nunca en silencio | §3.6, §5.2 | cifrado/truncado/nested/multivolumen/disco |
| 9. Coste medido en la Pi | §6.4 | p95/RSS/temp real o NOT RUN |
| 10. Comprobación adversa en cada criterio | §6.1-§6.3 | bomba, `..`, listado mentiroso, etc. |

**No se declara implementado ni aprobado nada.** El issue #344 sigue abierto; esta spec es
insumo para el PO y para quien implemente.

---

## 10. Referencias

- Issue #344 (contrato y 10 AC); #305 (spike); #308 (evaluación RAR); feature #148.
- `docs/design/benchmark-formatos-contenedor.md:5-8,27-32,63-74` (problema, qué hace hoy,
  opciones, paquetes).
- `docs/design/evaluacion-lector-rar-2026-10-23.md:1-9,94-106` y
  `evaluacion-lector-rar-tanda2-2026-10-23.md:1-8,44-73,87-119` (RAR4/5/sólido, `lsar` truncado,
  `unar` rc 0, topes, RSS, +22,5 MiB, NOT RUN de bomba/cifrado).
- `docs/design/contrato-307-formato-por-contenido.md:19-25,54-69,76-107` (firma, clases, topes,
  sin escritura).
- `docs/adr/0015-lector-de-rar-con-unar.md` (riesgo aceptado, mitigaciones, revisión pendiente).
- `src/zascarr/core/formato_contenedor.py:46-69,88-106,120-155,161-180,242-260`
  (firma, topes, ZIP).
- `src/zascarr/utils/lector_rar.py:42-64,197-247,318-370,391-425,428-440` (límites, proceso,
  listar, extraer una entrada, temporal).
- `src/zascarr/services/importer.py:72,510-530` (`COMIC_EXTS`, escaneo solo Descargas);
  `src/zascarr/utils/fs.py:666-760` (`listar_comics`/`recorrer_comics`); `src/zascarr/config.py:157,163,196,216,224,229`.
- `src/zascarr/services/library_audit.py:134,324-369` (avisos de contenedores; no procesa
  Descargas); `src/zascarr/web/auditoria.py` (pantalla de Auditoría).
- `src/zascarr/models/__init__.py:103-158,836,1256` (`FileFormat`/`Firma`/`MotivoRar`, `File`,
  `ImportRun`); migración actual `0042_favoritos` (la nueva sería 0043).
- `docs/BACKLOG.md:98` (B10/BL-CNV ya repartida; #344 no duplica conversión).
- [`benchmark-BL-PACK1-paquetes.md`](benchmark-BL-PACK1-paquetes.md): ficha de referencias y
  seguridad de esta historia; sus cortes técnicos (§7) se corresponden con los funcionales de §8.
  Esta
  spec no duplica sus tablas; cuando exista, se reconcilian referencias sin cambiar el contrato
  sin aprobación.

*Fin. Diseño propuesto; no implementado; migración no autorizada; sin datos reales.*
