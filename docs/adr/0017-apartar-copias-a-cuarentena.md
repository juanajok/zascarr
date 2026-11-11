# ADR 0017: apartar copias idénticas sobrantes a una cuarentena reversible

- **Estado:** **Aceptado** (2026-11-12, PO). Acepta D1-D4 con las recomendaciones del
  benchmark. **No autoriza migración en producción, ejecución sobre bibliotecas reales ni
  despliegue**: cada uno exige su decisión separada.
- **Fecha:** 2026-11-12.
- **Relación:** #264 BL-DUP1, feature #262 (principios D1-D4), #263 BL-DUP0 (benchmark y
  medición), ADR 0006 (asignación recuperable), ADR 0007 (vincular en su sitio), ADR 0008
  (propuestas sin ejecución silenciosa), ADR 0014 (deshacer una vinculación). Benchmark:
  `docs/design/benchmark-bl-dup0-duplicados.md` §5-§6; medición:
  `docs/design/medicion-BL-DUP0-2026-11-05.md`.
- **Base de código:** `origin/main` `5abe862` (2026-11-12; worktree `.squad/wt-264-spec`).

## Contexto

B16 detecta en «Revisar mi biblioteca» grupos de **contenido idéntico** (`MismoContenido`:
mismo `sha256` y tamaño, varias rutas) y calcula `bytes_recuperables`, pero la auditoría es de
**solo lectura** (`services/library_audit.py:78-89,162-181,223-250`). El coleccionista ve el
exceso y no puede actuar desde ZascArr.

La medición real del 2026-11-05 confirma el problema: **215 grupos** de contenido idéntico,
**8.058.146.534 B (7,50 GiB)** de `bytes_recuperables` en el informe de auditoría del
2026-10-29, con la lista de grupos truncada a 200 (401 archivos listados); **112/200 grupos**
tienen la copia del catálogo vinculada a un issue y **88/200** no
(`medicion-BL-DUP0-2026-11-05.md` §2-§4). El plan de limpieza del 2026-11-07 habla de 200 parejas
y ~20,1 GB; es otra foto/definición y **no se suma** a la anterior: cualquier acción debe partir
de una auditoría fresca, no de una cifra de archivo.

Hasta hoy ZascArr solo mueve archivos al importar; la biblioteca ya adoptada es de la persona y
ZascArr no la reorganiza. Apartar una copia idéntica es una **operación nueva sobre la
colección**: mueve un archivo que la persona elige, no lo borra, y debe poder deshacerse. Eso
exige una postura explícita (D4) antes de implementar.

## Decisión

### D4 — Postura: mover es una operación de colección, reversible y sin borrado

ZascArr **puede mover** un archivo de la colección a una cuarentena **solo** cuando:

- el contenido es **idéntico** (mismo hash verificado en el momento de mover);
- la persona ha **elegido** qué copia se queda, sin preselección ni puntuación;
- hay **vista previa** y **confirmación explícita** de un token firmado;
- el movimiento es a la **misma montura** (rename atómico, sin copia) y **nunca sobrescribe**;
- la operación es **idempotente**, tiene **comprobante durable** y se puede **deshacer**;
- el catálogo queda **coherente** en la misma operación (mover primero, commit corto después).

Nunca se borra, no se sustituye una copia por otra, no se puntúa, no se premarca, no se crea ni
se fusiona una entidad editorial, no se tocan los archivos que no se eligieron, y no se aplica a
contenido distinto (BL-R6), carpetas (BL-DUP3) ni enlaces duros (BL-DUP2). El vaciado de la
cuarentena es otra decisión (D2).

**Alternativas descartadas:** borrado permanente (Komga, Kapowarr); papelera del sistema o
`send2trash` (dependencia nueva y fuera de la BD); copia a otra montura (EXDEV, espacio y dos
copias); puntuación y copia premarcada (convierte la recomendación en decisión); enlaces duros
ya (BL-DUP2); reflinks/CoW (no acreditados en la Pi); purga automática (Sonarr la hace, pero
borra sin consentimiento en el momento).

### D1 — Dónde vive la cuarentena, y cómo se falla cerrado

Ruta: **`<library>/.zascarr/apartados/<operacion_id>/<ruta relativa original>`**.

- `<library>` es `settings.library_path`; el destino es una subcarpeta de **`.zascarr`**, el
  mismo árbol que ya usan la conversión (`services/conversion.py:205-206`,
  `<library>/.zascarr/originales`) y el diario (`:209`).
- **Misma montura obligatoria.** No basta `st_dev`: un bind mount distinto puede compartir
  `st_dev` y fallar `rename` con `EXDEV` (`utils/fs.py:96-171`, especialmente `:140-145`). Se
  comprueba `st_dev` y se intenta el `os.replace`; si el kernel devuelve `EXDEV` u otro error,
  **se aborta la operación, no se copia**. No se usa `safe_move` para la cuarentena porque su
  contrato permite copiar entre sistemas: aquí se quiere rename atómico.
- **PUID/PGID:** la carpeta se crea con el UID/GID del servicio o en bootstrap, nunca con
  `chmod 777` ni `chown -R` sobre la colección. Si no es escribible, **fallar cerrado** con un
  mensaje que diga qué carpeta y qué hacer.
- **Exclusión explícita:** `.zascarr` no es biblioteca. Los recorridos ya lo excluyen en
  `utils/fs.py::recorrer_comics` (`:246-249`), `services/library_adopter.py:339,363-364`,
  `services/library_audit.py:72-74,208-209`; cualquier recorrido nuevo debe usar el mismo
  criterio. El importador escanea descargas, no la biblioteca; la comprobación de disco mira
  rutas registradas, así que la operación debe repuntar `File` (§D3) y no registrar la
  cuarentena.
- **Sin colisión:** `<operacion_id>` es único por operación; la ruta relativa conserva la
  jerarquía original; si el destino ya existe, se aborta el grupo (no se sobrescribe).
- **fsync:** tras mover, `fsync` del directorio destino y del padre de origen (patrón de
  `services/conversion.py:167-191,476-477`).
- **La cuarentena puede ser visible para otros lectores** que escaneen la misma raíz (p. ej.
  Kavita); es una consecuencia documentada, no se monta otra ruta ni se asume invisible. La
  exclusión de ZascArr es explícita, no por ser un punto.

### D2 — Vaciar la cuarentena no es de esta historia

No hay purga automática ni programador. En v1 **no se borra** la cuarentena. La pantalla muestra
cuánto ocupa, dónde está y que el deshacer está disponible. «Vaciar» será una acción explícita,
separada, con vista previa de archivos/bytes y confirmación reforzada; irreversible y con aviso
de que el deshacer deja de estar disponible. Es una decisión posterior, no un efecto de BL-DUP1.

### D3 — Persistencia: dos tablas nuevas, no un diario JSONB

Se propone una **migración aditiva** con dos tablas:

```text
apartado_operaciones
  id UUID PK                    # operacion_id, también el del token
  estado enum                   # en_curso | confirmada | deshecha | cancelada
  token_hasta timestamptz
  creada, actualizada timestamptz
  total_grupos int
  total_archivos int
  total_bytes bigint
  resultado JSONB               # resumen final por grupo, para replay idempotente

apartado_grupos
  id UUID PK
  operacion_id UUID NOT NULL REFERENCES apartado_operaciones(id) ON DELETE CASCADE
  grupo_clave text NOT NULL     # sha256 del contenido; interno, no se muestra
  sha256 char(64) NOT NULL
  size_bytes bigint NOT NULL
  estado enum                   # pendiente | movido | deshecho | rechazado | error
  detalle JSONB NOT NULL        # keep + items (origen, destino, estado, hash, stat, file_id)
  UNIQUE (operacion_id, grupo_clave)
  INDEX (operacion_id), (estado)
```

- **Por qué tabla y no el diario de `conversion.py`:** la conversión es un archivo/una fila y
  usa `File.metadata_` + `.zascarr/diario`; esto es una operación **multi-grupo**, con replay
  idempotente, resultado por grupo y deshacer durable. `ImportRun.details` no sirve: es un
  informe de pantalla que se trunca a 200 (`services/library_audit.py:376-410`). Las tablas
  `asignacion_operaciones` (0017), `alta_operaciones` (0018) y `vinculacion_operaciones` (0019)
  son el patrón probado de comprobante durable; esta tabla es propia de su dominio, no se
  reutiliza una ajena.
- **Estados de operación:** `en_curso` (intención escrita antes de mover), `confirmada` (todos
  los grupos resueltos o rechazados con resultado), `deshecha` (todos los ítems devueltos),
  `cancelada` (falló antes de mover, sin efectos). Los ítems viven en `detalle` con sus estados
  `pendiente/movido/deshecho/error`; no se presenta un grupo como resuelto si su copia
  conservada no está catalogada (medición: 88/200 sin vínculo).
- **Idempotencia:** mismo token/`operacion_id` devuelve el mismo resultado; no se ejecuta dos
  veces ni se reaplica un token deshecho. El token de vista previa es firmado, con TTL corto
  (15 min, `services/tokens_revision.py:31`), y **no se escribe nada al previsualizar**: los
  paths viajan en el formulario y se validan contra un `rutas_digest` firmado; el servidor
  recompone y revalida. La confirmación escribe la intención (`en_curso`) **antes** de mover y
  actualiza por grupo con commits cortos.
- **Retención:** la operación y sus grupos se conservan mientras la cuarentena pueda deshacerse;
  no se purgan automáticamente. Un `DELETE` de una operación deshecha solo lo decidirá una
  política de limpieza futura (D2), nunca esta historia.
- **Migración:** `alembic/versions/0030_apartado_operaciones.py` (número propuesto; siguiente
  libre tras `0029`), aditiva y reversible; **no se aplica en este encargo**. No toca tablas
  existentes ni datos; los enums nuevos no reutilizan `asignacion_estado` (dominios distintos).

## Invariantes que la implementación debe fijar

1. Solo contenido idéntico, con hash verificado **justo antes** de mover.
2. Decide la persona; ninguna copia premarcada; sin puntuación; sin recomendación vinculante.
3. Nunca se borra ni se sobrescribe; mover a cuarentena, no a la papelera.
4. Mover y deshacer en la **misma montura**, con rename atómico; si no, fallar cerrado.
5. Catálogo coherente: `File` nunca apunta a una ruta movida; se repunta a la copia que se
   queda en la misma operación, moviendo primero y con commit corto.
6. Comprobante durable e idempotente; el fallo incierto se resuelve releyendo, nunca se anuncia
   éxito sin comprobarlo.
7. Coste acotado a los grupos elegidos: hash en streaming y fuera del bucle; sin abrir imágenes.
8. `.zascarr` excluido de importador, adopción, auditoría y comprobación de disco.
9. Rutas y nombres no se publican en logs ni en documentación; no hay datos personales.

## Consecuencias

- Nueva superficie de UI en «Duplicados» y un servicio de operaciones;
- una migración aditiva nueva y dos tablas;
- disciplina de exclusión en todos los recorridos;
- riesgo operativo nuevo acotado por esta ADR (mover, no borrar; token, confirmación, deshacer);
- **sin** cambio de identidad editorial, enriquecimiento, vínculos, rutas de archivos no
  elegidos ni recuentos;
- el PO debe aceptar esta ADR antes de «Lista para desarrollar». La aceptación **no** autoriza
  la migración ni la ejecución: son estados separados.

## Evidencia y referencias

- Benchmark BL-DUP0 §5 (EXDEV, PUID/PGID, exclusión) y §6 (D1-D4)
  (`docs/design/benchmark-bl-dup0-duplicados.md:249-405`).
- Medición real (`docs/design/medicion-BL-DUP0-2026-11-05.md` §2-§4): 215 grupos,
  8.058.146.534 B recuperables, 200/215 en la lista, 112/200 con issue, 88/200 sin él;
  M5 de monturas **NOT RUN**.
- Conversión existente: `services/conversion.py:167-191,205-206,400-500,700-790` (cuarentena
  `.zascarr/originales`, token, `os.replace`, fsync, deshacer).
- `utils/fs.py:89-171` (`safe_move`/EXDEV) y `:223-260` (recorrido con exclusiones).
- Operaciones durables: `models/__init__.py:740-861`, migraciones 0017-0019.
- Ley 1.542 archivos/215 grupos; plan de limpieza 2026-11-07 (otra foto; no se usa como cifra
  única).

## Aprobación pendiente

- [ ] PO acepta D4, D1, D2 y D3.
- [ ] Revisión de Seguridad confirma mount/PUID/exclusiones y el contrato de token.
- [ ] Se decide si BL-DUP1 puede pasar a «Lista para desarrollar».
- [ ] **No** implica autorización de migración: esa es una decisión posterior y separada.
