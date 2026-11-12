# Especificación — BL-DUP1: apartar una copia idéntica sobrante, con vista previa y deshacer (#264)

> **Estado: DISEÑO PROPUESTO. NO IMPLEMENTADO. MIGRACIÓN NO AUTORIZADA NI APLICADA.** No se toca
> disco, biblioteca, base de datos ni producción. Depende de la **ADR 0017** (Propuesta; la acepta el
> PO) y de BL-DUP0. **Sin código, sin migraciones ejecutadas y sin pruebas ejecutadas.**
> **Base:** `origin/main` `5abe862` (2026-11-12; worktree `.squad/wt-264-spec`). Las citas
> `fichero:línea` se refieren a ese SHA.

---

## 0. Resumen y alcance

**Problema.** La auditoría B16 detecta grupos de **contenido idéntico** (mismo SHA-256 y tamaño) y
calcula el espacio recuperable, pero es de solo lectura (`services/library_audit.py:78-89,162-181`).
En la biblioteca real hay **215 grupos** y **8.058.146.534 B** de `bytes_recuperables` en el informe
del 2026-10-29; la lista visible está truncada a 200 grupos/401 archivos (`medicion-BL-DUP0-2026-11-05.md`
§2). El plan de limpieza del 2026-11-07 habla de 200 parejas y ~20,1 GB: es **otra foto/definición** y
no se suma a la anterior; antes de actuar hace falta una auditoría fresca, no una cifra de archivo.

**Qué añade BL-DUP1.** Elegir, por grupo, **qué copia se queda**; ver una vista previa exacta; mover
las demás a una cuarentena reversible del mismo montaje; repuntar el catálogo si la copia movida era
la que `File` conocía; y deshacer. **Nunca se borra**, no se puntúa, no se premarca ninguna copia y no
se toca lo que no se eligió.

**Fuera:** contenido distinto (BL-R6/#235), carpetas (BL-DUP3), enlaces duros (BL-DUP2), borrado
definitivo, vaciar la cuarentena (D2), puntuaciones, etiquetas de grupos/sitios, convertir formatos y
renombrar. **El vaciado no es de esta historia**; la pantalla solo muestra cuánto ocupa y dónde está.

**Dependencias:** ADR 0017 (D4, D1, D2, D3), benchmark BL-DUP0 §5-§6, medición BL-DUP0, ADR 0006
(operación recuperable), ADR 0007 (vincular en sitio), ADR 0008 (sin ejecución silenciosa), ADR 0014
(deshacer) y la pauta de `services/conversion.py` (cuarentena, token, `os.replace`, fsync y deshacer).

---

## 1. Evidencia y estado actual

### 1.1 Medición real: cifras que no se suman

| Fuente | Qué dice | Lectura |
|---|---|---|
| Auditoría del **2026-10-29** (`medicion-BL-DUP0-2026-11-05.md` §2-§4) | 1.542 archivos, **215 grupos** idénticos, **8.058.146.534 B (7,50 GiB)** recuperables; lista truncada a 200 grupos/401 archivos; 112/200 con issue, 88/200 sin issue; 174/200 en una sola primera carpeta, 26/200 cruzan carpeta, 0 cruzan tradición | Foto de un informe; `bytes_recuperables` es contador completo; la lista es mínimo |
| Plan de limpieza del **2026-11-07** (`docs/design/plan-limpieza-duplicados-2026-11-07.md`, §B) | 200 parejas, **~20,1 GB** | Otra auditoría/foto y otra definición (parejas); no se suma a 8,06 GB ni se usa como cifra única |
| M5 monturas | **NOT RUN** | El cruce de montura no se midió; D1 lo exige en runtime y falla cerrado |

**Conclusión:** no se autoriza una acción masiva con una cifra heredada. La UI de BL-DUP1 trabaja
sobre una auditoría fresca y la operación recalcula los grupos elegidos; no publica una cifra de
ahorro que no haya verificado en el momento.

### 1.2 Piezas reutilizables y huecos

| Pieza existente | Qué aporta | Qué falta |
|---|---|---|
| `LibraryAudit` / `MismoContenido` | Agrupa por SHA-256+tamaño, rutas, `bytes_recuperables`; solo lectura; dedupe por inodo en el recorrido (`library_audit.py:78-89,207-250`) | No conserva una identidad de grupo estable; no actúa; no comprueba hash al actuar |
| Cuarentena de conversión | `_cuarentena` = `<library>/.zascarr/originales` (`conversion.py:205-206`); `os.replace` mismo sistema, `_fsync_dir` (`:167-191`), `deshacer` con «deshecho» (`:700-790`); diario JSONB en `.zascarr/diario` (`:209,574-610`) | Es por archivo/una fila, no multi-grupo; no repunta `File`; no separa la cuarentena de apartados |
| `safe_move` | Mueve sin sobrescribir, copia y verifica entre discos (`utils/fs.py:96-171`) | **No sirve para la cuarentena**: permite copiar en EXDEV; aquí se exige rename atómico y fallo cerrado |
| `.zascarr` excluido | `utils/fs.py:246-249`; `library_adopter.py:339,363-364`; `library_audit.py:72-74,208-209` | Mantener la exclusión al añadir recorridos; la cuarentena nueva vive bajo `.zascarr` |
| Tokens firmados | `tokens_revision.py` (TTL 15 min `:31`, propósitos `:38-47`, `crear_token` `:96-102`) | Nuevo `PROPOSITO_APARTAR`, cotas y payload multi-grupo |
| Comprobantes durables | `asignacion_operaciones` 0017, `alta_operaciones` 0018, `vinculacion_operaciones` 0019; idempotencia/replay | Nuevas tablas `apartado_operaciones`/`apartado_grupos`; no reutilizar una ajena |
| `File` | `file_path` único, `sha256_hash`, `issue_id`, metadata (`models/__init__.py:668-715`) | Repuntar la fila cuando la copia movida es la conocida, sin tocar identidad |

---

## 2. Contrato general

### 2.1 Términos de pantalla (español llano)

- **«la copia que se queda»**: la única que permanece en la biblioteca.
- **«apartar»**: mover una copia idéntica a la cuarentena; no borrar, no renombrar.
- **«se liberan»**: bytes que dejan de ocupar la biblioteca, sin prometer borrado definitivo.
- **«deshacer el apartado»**: devolver las copias a su ruta original y el catálogo a como estaba.
- Prohibido en superficie: «hash», «inodo», «renombrar», «operación», «token», ids internos.

### 2.2 Estados de una operación

| Estado | Significado |
|---|---|
| `en_curso` | Intención escrita antes de mover; puede haber grupos pendientes/movidos |
| `confirmada` | Todos los grupos tienen resultado (apartado, rechazado o error); no se reaplica |
| `deshecha` | Todos los grupos que se movieron volvieron; catálogo restaurado |
| `cancelada` | No se movió nada (preflight/token/errores); sin efectos |

Grupo: `pendiente`, `movido`, `deshecho`, `rechazado`, `error`. Un grupo no se presenta como resuelto
si su copia conservada no está catalogada (la medición ya distingue 112/200 con issue y 88/200 sin él).

### 2.3 Entradas y salidas

- **Entrada (Duplicados):** grupos de `MismoContenido` con rutas, tamaño y sha; cada copia con ruta
  relativa a la biblioteca, carpeta de tradición, si es la conocida por el catálogo y a qué serie/número
  está vinculada, fecha de modificación y si el nombre se entiende. **Ninguna copia premarcada**;
  ninguna pista preselecciona.
- **Salida de vista previa:** lista exacta de lo que se aparta, bytes liberados, cambios de catálogo
  previstos y token; **cero escrituras** en disco, catálogo o BD.
- **Salida de confirmación:** resultado por grupo + resumen de operación; por grupo, `apartado`,
  `rechazado` (con motivo) o `error`; totales; id de operación opaco para deshacer.
- **Salida de deshacer:** resultado por grupo; `deshecho` o `rechazado_ocupado`/`desactualizado`;
  nunca sobrescribe.

---

## 3. Token, vista previa y multi-grupo

### 3.1 Propósito y payload

Nuevo propósito `PROPOSITO_APARTAR = "apartar_duplicados"` en `services/tokens_revision.py`, con
`VERSION_TOKEN_APARTAR = 1`, TTL de 15 min (`TTL_SEGUNDOS`, `:31`) y contexto fijo (p. ej.
`"apartados"`; no hay usuario). Payload firmado:

```text
ApartarFirmada
  version=1
  operacion: UUID
  accion: "apartar" | "deshacer"
  grupos: tuple[GrupoFirmado]   # vacío para deshacer
GrupoFirmado
  sha256: 64 hex                # contenido del grupo
  rutas_digest: 64 hex          # SHA-256 de las rutas relativas ordenadas, separadas por NUL
  keep_index: int               # índice en la lista ordenada de rutas
  n_rutas: int
  caduca: epoch
```

- **No viajan rutas completas en el token:** viajan en el formulario (hidden/JSON) y se validan contra
  `rutas_digest`; el servidor recalcula el digest y comprueba `sha256` y `n_rutas`. Una ruta manipulada
  no puede mantener el digest; además se rehash-ea antes de mover.
- **`MAX_TOKEN_APARTAR`** calculado con el peor caso real (como `MAX_TOKEN_CONVERSION`,
  `tokens_revision.py:1180`); el campo del formulario usa exactamente esa cota. **Máximo 20 grupos por
  confirmación** (el token debe quedar acotado); la UI lo explica y permite revisar en tandas.
- **Deshacer:** token con `accion="deshacer"` y `operacion`; no incluye rutas; el servidor lee la
  operación y su detalle. Un token de apartar no sirve para deshacer y viceversa.
- **Preview sin escrituras:** no crea operación, no escribe BD, no toca archivos, no consulta fuentes.
  Solo hashea los grupos elegidos (streaming, `asyncio.to_thread`).

### 3.2 Flujo de vista previa

1. La persona abre **Duplicados** (auditoría existente) y elige uno o varios grupos; para cada grupo
   marca **una** copia que se queda. Sin elección, el grupo no entra.
2. `POST` de previsualización con los grupos y las rutas elegidas (no se confía en ellas: se validan).
3. El servidor comprueba por grupo:
   - ≥2 rutas, todas dentro de la biblioteca, ninguna bajo `.zascarr`;
   - mismo `sha256` y tamaño al rehash actual;
   - `rutas_digest` coincide con las rutas recibidas;
   - la copia que se queda y las que se apartan existen y son legibles.
4. Devuelve la lista exacta (qué se aparta, qué se queda, bytes, cambio de catálogo) y el token; no
   escribe nada. Un grupo que falla se marca **rechazado en la previsualización** y no se incluye.
5. La persona puede revisar varios grupos y confirmar juntos; el resumen dice «se apartan N archivos,
   se liberan X GB» (solo de lo previsualizado y revalidado).

### 3.3 Vista previa y no-escritura

- **No hay `INSERT`/`UPDATE`/filesystem writing** en previsualización; una prueba lo comprueba
  (contadores de operaciones, mtimes de archivos, `File`).
- El token se emite aunque la persona luego cancele; no crea operación ni deja basura.
- La confirmación no acepta grupos que no estén en el token ni un `keep_index` distinto.

---

## 4. Confirmación: mover, catálogo y resultados

### 4.1 Verificación antes de mover

1. Verificar token (firma, propósito, contexto, acción, caducidad). Si caducó/manipulado → sin mover,
   sin operación; se pide repetir la vista previa.
2. Recalcular `rutas_digest` del formulario y comparar; si no coincide → `token_invalido`.
3. Rehash **justo antes** de mover: `sha256` de la copia que se queda y de cada copia a apartar;
   tamaño y, si se quiere robustez, `mtime_ns`. Si alguna cambió, ese grupo se **rechaza** y no se
   mueve; los demás grupos de la confirmación siguen por separado.
4. Comprobar que las rutas siguen dentro de la biblioteca y que el destino de cuarentena no existe.
5. Comprobar la coherencia de catálogo:
   - localizar `File` por `file_path` entre las rutas del grupo;
   - 0 filas → no hay cambio de catálogo;
   - 1 fila en la copia que se queda → no hay repunte;
   - 1 fila en una copia que se aparta → repuntar a la que se queda (misma operación);
   - 1 fila en una copia y otra fila en otra copia del grupo (≥2 `File`) → **grupo rechazado**
     (`catalogo_ambiguo`), no se fusionan filas;
   - ninguna fila en la copia que se queda y una en la movida → repunte normal;
   - una fila apuntando a una ruta que ya no existe → grupo rechazado (`catalogo_incoherente`).
6. Un grupo rechazado no mueve nada; el resto de grupos se procesan y se informan por separado.

### 4.2 Operación durable antes de mover

- Crear `apartado_operaciones` con `estado='en_curso'`, `operacion_id` del token, `token_hasta`,
  `total_grupos`/`total_archivos`/`total_bytes` y una fila `apartado_grupos` por grupo con
  `estado='pendiente'` y `detalle` de items. **Commit antes de mover** (write-ahead) para que una
  muerte del proceso sea recuperable.
- Un lock consultivo global de apartados (o por operación) serializa confirmaciones/deshaceres; no
  compite con el importador porque mueve archivos ya registrados y no toca el ciclo de descargas.
- El mismo `operacion_id`/token repetido devuelve el resultado guardado; no reaplica.

### 4.3 Mover un grupo

1. Para cada copia a apartar, calcular `destino = <library>/.zascarr/apartados/<operacion>/<ruta
   relativa>`; crear el padre con el UID/GID del servicio.
2. Comprobar que el destino no existe, que origen y destino están en la **misma montura** (`st_dev`) y
   que la raíz de cuarentena es escribible; si no, **fallar cerrado** (no copiar, no `chmod 777`).
3. `os.replace(origen, destino)` (rename atómico; no `safe_move`); si el kernel devuelve `EXDEV` u otro
   error, abortar el grupo y no continuar. `fsync` del directorio destino y del padre del origen
   (patrón `conversion.py:167-191,476-477`).
4. Actualizar el `detalle` del grupo/ítem (`movido`, ruta, hash, stat) en un commit corto; si muere el
   proceso, la operación `en_curso` permite reconciliar por el estado y las rutas.
5. Si un grupo tiene varias copias y falla una, **compensar** las ya movidas del grupo devolviéndolas
   a su origen y marcar el grupo `error`/`rechazado`; si la compensación falla, el grupo queda
   `error` y la operación `en_curso` para recuperación; nunca se anuncia éxito.

### 4.4 Catálogo coherente (mover primero, commit corto)

- Si la copia movida era la que `File` conocía, **después de mover** (mismo grupo) actualizar la fila:
  `file_path` y `file_name` a la copia que se queda; `file_size_bytes`, `sha256_hash` y
  `file_mtime_ns` a los de esa copia (contenido idéntico); conservar `id`, `issue_id`, `metadata_`,
  `metadata_source`, `locked_fields`, `source_tag`, `original_sha256`, `covered_issue_ids` y el resto.
- Si la copia que se queda era la conocida, no se actualiza nada.
- Si no hay `File`, no hay cambio de catálogo.
- La actualización va en el mismo commit corto que el estado del grupo, **después** del move; si el
  commit falla, `resultado_incierto`: la operación queda `en_curso`, se relee y se reconcilia; nunca
  se presenta como «nada ha cambiado».
- `File.file_path` es único: si el repunte choca, se revierte/compensa el grupo y se rechaza; no se
  fusionan filas ni se crean series/issues.

### 4.5 Resultado por grupo y de la operación

| Resultado de grupo | Cuándo | Efecto |
|---|---|---|
| `apartado` | Movidas N-1, copia que se queda verificada, catálogo coherente | Archivos en cuarentena; `File` repuntado o intacto |
| `rechazado` | Cambió hash/stat/rutas, `File` ambiguo, destino ocupado, token de grupo no válido | Sin mover ese grupo; motivo en español |
| `error` | Fallo de disco/rename/compensación | Sin éxito; operación `en_curso` para recuperar; se explica |
| `deshecho` | Deshacer completado | Archivos y catálogo restaurados |

La operación resume «N grupos apartados, M archivos, X bytes; K rechazados/errores», sin ocultar
parciales. Los grupos con copia conservada **sin issue** se marcan como «sin vincular»: la cuarentena
no los presenta como resueltos.

---

## 5. Deshacer: contrato y no-sobrescritura

### 5.1 Vista previa de deshacer

- Entrada desde el resultado o la lista de operaciones; `POST` con `operacion_id`; token de acción
  `deshacer`, sin rutas.
- Comprueba: operación `confirmada`; cada ítem `movido` tiene su copia en cuarentena; el sitio
  original está libre; la copia que se quedó sigue existiendo y con su hash; si el catálogo fue
  repuntado, `File.file_path` sigue apuntando a la copia que se quedó.
- **Preflight completo:** si un solo sitio original está ocupado, se rechaza **toda** la operación y
  no se mueve ninguno; no se sobrescribe ni se elige parcialmente. Se explica qué ruta está ocupada
  (al operador, no en logs).

### 5.2 Confirmar deshacer

1. Token válido y operación `confirmada`; lock; idempotencia (si ya `deshecha`, mismo resultado).
2. Revalidar todos los ítems; mover de cuarentena a la ruta original con `os.replace` **solo si el
   destino no existe**; fallar cerrado en EXDEV/permiso; `fsync`.
3. Si la operación repuntó `File`, devolver `file_path`/`file_name`/stat a la copia movida; conservar
   identidad, metadata y protecciones.
4. Commit corto; `estado='deshecha'`; operación repetida no vuelve a mover.
5. Si falla a mitad, compensar devolviendo a cuarentena lo ya restaurado; si la compensación falla,
   `resultado_incierto` y operación `en_curso`; nunca éxito sin comprobación.

### 5.3 Invariantes de deshacer

- Nunca sobrescribe: si el sitio original existe (aunque sea otro archivo idéntico), se rechaza.
- Nunca borra: lo que no se puede devolver se queda en cuarentena y se explica.
- El catálogo vuelve a como estaba (misma fila, mismo `issue_id`, metadata, source/locks).
- Idempotente y durable: tras reinicio, la operación y su detalle permiten reintentar sin duplicar.
- No toca archivos de otros grupos ni la copia que se quedó.

---

## 6. Exclusiones, seguridad y coste

### 6.1 Recorridos que no ven la cuarentena

`.zascarr` ya se excluye en los recorridos actuales:

- `utils/fs.py::recorrer_comics` (`:223-260`, excluye `.zascarr` en `os.walk`);
- `services/library_adopter.py:339,363-364`;
- `services/library_audit.py:72-74,208-209`.

La cuarentena nueva vive en `<library>/.zascarr/apartados/`; **no** se registra como `File`, no
aparece en auditoría/adopción/importador y no se cuenta como pendiente. La comprobación de disco mira
rutas registradas; el repunte de `File` evita que una ruta movida quede registrada. Se prueba con una
carpeta señuelo dentro de la cuarentena: no aparece en inventario, auditoría, adopción ni en «no
reconocidos».

### 6.2 Seguridad y permisos

- Solo se mueve contenido **idéntico** y elegido; ninguna ruta externa a la biblioteca; se rechaza
  `.zascarr` como origen.
- La cuarentena se crea con el UID/GID del servicio; si no es escribible, fallo cerrado con carpeta y
  acción. Nunca `chmod 777` ni `chown -R` sobre la colección.
- No se publican rutas, nombres ni hashes en logs, documentación ni mensajes de error; el operable
  ve la ruta que necesita para decidir, no un id interno.
- No se sigue ningún enlace simbólico a otra ruta/montura: el archivo debe estar dentro de la
  biblioteca y la cuarentena en la misma montura; si no, se rechaza.

### 6.3 Coste en la Pi

- Solo se hashean los grupos previsualizados/confirmados, en streaming y con `asyncio.to_thread`
  (`sha256_streaming` ya usado por la auditoría, `library_audit.py:223-250`); no se abren imágenes, no
  se analiza el contenido.
- Máximo 20 grupos por confirmación; la previsualización no recorre toda la biblioteca.
- Rename sin copia; sin espacio extra en la cuarentena (solo el inodo movido).
- Operación serializada; no compite con el importador (que mueve desde descargas, no desde la
  biblioteca) y no bloquea el bucle.

---

## 7. UI en «Duplicados» (rebanada B)

- Entrada desde la pantalla de auditoría existente («Revisar mi biblioteca» / Duplicados). Cada grupo
  idéntico gana una acción **«Apartar copias»**; no hay botón principal en la lista.
- Cada copia se muestra con hechos: ruta relativa, carpeta de tradición, si el catálogo la conoce y a
  qué serie/número está vinculada, fecha de modificación y si el nombre se entiende. **Sin puntuación
  y sin copia premarcada**; no hay radio seleccionado por defecto. Las pistas («el resto de esta serie
  está en Tebeos/») son texto, no preselección.
- La persona marca **una** copia que se queda; sin elección, el grupo no se puede previsualizar.
- Pantalla de vista previa: lista de archivos que se apartan, «se liberan X», qué cambiará en el
  catálogo, y **«Confirmar y apartar»** (principal) / «Cancelar» (neutro). La garantía «no se borra;
  se puede deshacer» va junto al botón.
- Resultado: grupos apartados/rechazados/errores por separado, resumen y **«Deshacer»** por operación;
  si hay un grupo rechazado, se explica y el resto no se oculta.
- Deshacer: vista previa con las rutas que se devuelven; si un sitio está ocupado, se rechaza toda la
  operación y se explica; no se sobrescribe.
- Textos: «apartar», «la copia que se queda», «se liberan», «deshacer el apartado». Nada de «hash»,
  «inodo», «renombrar», «token» ni ids.
- Accesibilidad: formularios nativos, foco, teclado, `role="status"`/`alert`; 320 px sin scroll
  lateral; texto ≥14 px (CLAUDE.md §6). No hay `hx-confirm` ni diálogo nativo.

---

## 8. Mapa AC 1-12 → contrato

| AC #264 | Qué exige | Dónde |
|---|---|---|
| 1. Comparar con hechos, sin puntuación | Ruta relativa, tradición, catálogo/serie/número, mtime, nombre entendible; nada premarcado; pistas como texto | §7; §2.3 |
| 2. Elegir | Marca qué copia se queda; sin elección no pasa nada | §3.2, §7 |
| 3. Vista previa sin escribir | Lista, bytes, cambios de catálogo; varios grupos; resumen | §3.2-§3.3 |
| 4. Apartar no es borrar | Mueve a cuarentena misma montura, guarda ruta original; nunca borra | §4.3, ADR D1 |
| 5. Hash justo antes de mover | Rehash de la que se queda y las que se apartan; grupo cambiado se rechaza; demás por separado | §4.1, §4.5 |
| 6. Catálogo coherente | Repunta `File` a la copia que se queda en la misma operación; mover primero, commit corto; conserva serie/número/procedencia | §4.4, ADR D3 |
| 7. Cuarentena no reaparece | Fuera de importador, adopción, auditoría y comprobación de disco; no vuelve como pendiente/duplicado | §6.1 |
| 8. Deshacer / no sobrescribir | Devuelve a su sitio y catálogo; sitio ocupado rechaza; idempotente y comprobante durable; incierto se relee | §5, ADR D3 |
| 9. Vaciar fuera de alcance | D2: no hay purga; pantalla muestra tamaño/dónde | §0, ADR D2 |
| 10. Ligero en la Pi | Solo grupos tocados, streaming, `to_thread`, sin imágenes | §6.3 |
| 11. Lenguaje llano | «apartar», «la copia que se queda», «se liberan»; sin jerga | §2.1, §7 |
| 12. Pruebas | PG real, FS real, EXDEV, permisos PUID/PGID, muerte entre mover/confirmar, mutaciones, navegador; PASS/FAIL/NOT RUN separados | §10 |

**Criterio 12:** las pruebas son parte de la entrega de implementación; aquí se definen, no se
ejecutan.

---

## 9. Migración propuesta (no aplicada)

- **Migración aditiva `0032`** (siguiente libre tras `0029`), propuesta en la ADR 0017:
  - enums `apartado_estado` (`en_curso`, `confirmada`, `deshecha`, `cancelada`) y
    `apartado_grupo_estado` (`pendiente`, `movido`, `deshecho`, `rechazado`, `error`), con
    `postgresql.ENUM` explícito y `values_callable` en minúsculas;
  - `apartado_operaciones` (cabecera);
  - `apartado_grupos` (grupo + `detalle` JSONB con los ítems), `UNIQUE(operacion_id, grupo_clave)`,
    índices por operación/estado; FK a operación con `CASCADE`;
  - **no** toca `files`, `series`, `issues` ni las tablas de operaciones 0017-0019; no hay backfill.
- La migración y la implementación **no se ejecutan en este encargo**; no se aplica a producción.
- `down` elimina las dos tablas y los enums; como no hay datos previos, es reversible. Si una
  operación está `en_curso` o hay cuarentena con archivos, la implementación debe negarse a bajar /
  recuperar antes; se documenta en el ADR.

---

## 10. Rebanadas de implementación y pruebas

### 10.1 Rebanadas

| Rebanada | Contenido | Talla | Depende |
|---|---|---:|---|
| **A · servicio, tablas y token** | Migración 0032; modelo/servicio `apartar_duplicados.py`; `PROPOSITO_APARTAR` + `MAX_TOKEN_APARTAR`; previsualizar (sin escribir), confirmar multi-grupo, mover/compensar, repunte de `File`, deshacer; lock y idempotencia | **M** | ADR 0017; B16 |
| **B · UI en Duplicados** | Selección sin premarca, vista previa, resumen, confirmar, resultados por grupo, deshacer; textos, accesibilidad, 320 px, navegador real | **M** | A |
| **C · robustez** | EXDEV/permisos PUID/PGID, muerte entre mover y commit, reconciliación `en_curso`, deshacer con sitio ocupado, exclusión de `.zascarr`, pruebas de caos; no añade alcance | **S/M** | A |

- **Orden:** A → B; C endurece A/B en paralelo/después. La migración va con A, no antes.
- No se crea una historia para vaciar la cuarentena (D2); no se toca BL-DUP2/3.

### 10.2 Plan de pruebas (definido, no ejecutado)

**Postgres real**
1. Migración 0032: tablas/enums/índices/unique; `down` reversible; sin tocar tablas existentes.
2. Operación idempotente: mismo token dos veces → mismo resultado, una operación, sin mover dos veces.
3. Multi-grupo: un grupo cambia y se rechaza, otro se aparta; resultado por grupo y operación correcta.
4. Repunte: `File` de copia movida → `file_path` a la que se queda; identidad, `issue_id`,
   `metadata_source`, `locked_fields`, `metadata_` intactos; `file_path` único.
5. Sin `File` en el grupo → no se crea/actualiza catálogo; grupo con dos `File` → rechazo
   `catalogo_ambiguo`.
6. Deshacer restaura `File` y estado; repetido no duplica; token deshecho no reaplica.
7. Muerte entre mover y commit (failpoint): operación `en_curso`, reconciliación sin éxito falso.

**Sistema de ficheros real**
8. Mover en misma montura: rename, sin copia, ruta original desaparece, cuarentena conserva ruta
   relativa; fsync comprobable por mtime/estado (no por contenido de disco).
9. **EXDEV** (montura distinta o `os.replace` forzado): fallo cerrado, sin copia, archivo original
   intacto, operación sin éxito.
10. Permisos: cuarentena no escribible / archivo no legible → error claro; no `chmod 777`; PUID/PGID
    conserva propietario del archivo movido.
11. Destino de cuarentena ocupado → grupo rechazado; no sobrescribe.
12. Deshacer con sitio original ocupado → toda la operación rechazada, ningún archivo movido.
13. `.zascarr` señuelo: no aparece en inventario/adopción/auditoría/no reconocidos; no se registra.
14. Solo se hashean grupos elegidos; no se abren imágenes; `to_thread` no bloquea el bucle.

**UI/navegador**
15. Ninguna copia premarcada; sin elección el grupo no avanza; no hay puntuación.
16. Previsualizar no escribe (contadores/DB/mtimes); confirmar muestra resultados por grupo; rechazo
    visible; resumen correcto.
17. Deshacer con sitio ocupado se explica sin sobrescribir; foco/estado/teclado; 320 px; textos sin
    jerga; PASS/FAIL/NOT RUN separados.

---

## 11. Riesgos y NOT RUN

| Riesgo | Mitigación |
|---|---|
| La auditoría está desactualizada/truncada | Rehash de grupos elegidos justo antes; token con digest; cifras frescas; no usar 200/215 como total |
| Mover a otra montura rompe/duplica | Misma montura, rename atómico, abortar en EXDEV; no `safe_move` |
| Catálogo apunta a ruta movida | Repunte en la misma operación, mover primero, commit corto; validación y recuperación |
| Muerte entre mover y commit | Operación `en_curso` write-ahead, detalle por grupo, reconciliación; nunca éxito sin releer |
| Deshacer pisa un archivo nuevo | Preflight completo; si el sitio está ocupado, rechazo total; no sobrescribe |
| La cuarentena reaparece | `.zascarr` excluido en todos los recorridos; `File` repuntado; prueba con señuelo |
| PUID/PGID/permisos | Crear con UID/GID del servicio; fallo cerrado; sin `chmod 777` |
| Token grande / grupos | Máximo 20 grupos; `MAX_TOKEN_APARTAR` calculado; token con digests, no rutas |
| Vaciar sin querer | D2: fuera de alcance; no hay purga; solo mostrar tamaño/dónde |
| Privacidad | Rutas/nombres/hashes no se publican; el operable ve su ruta; sin logs sensibles |

**NOT RUN explícito:** no se ha implementado el servicio, no se ha creado/aplicado la migración, no se
ha tocado el disco ni producción, no se han ejecutado pruebas ni navegador. Las cifras del plan
(20,1 GB) y de la auditoría (8,06 GB) son fotos distintas y no se suman; la medición de monturas M5
sigue NOT RUN. La aceptación de la ADR y la autorización de la migración son decisiones separadas.

---

## 12. Trazabilidad

- ADR 0017: [`0017-apartar-copias-a-cuarentena.md`](../adr/0017-apartar-copias-a-cuarentena.md).
- Benchmark BL-DUP0: `docs/design/benchmark-bl-dup0-duplicados.md` §5-§6.
- Medición: `docs/design/medicion-BL-DUP0-2026-11-05.md` §2-§4 y PASS/FAIL/NOT RUN.
- Plan real: `docs/design/plan-limpieza-duplicados-2026-11-07.md` (otra foto; no se usa como cifra
  única).
- Código actual: `services/library_audit.py`; `services/conversion.py`; `utils/fs.py`;
  `services/tokens_revision.py`; `models/__init__.py`; migraciones 0017-0019.
- Issue #264 (12 AC), feature #262 (D1-D4), BL-DUP0 #263.
