# ADR 0020: raíces de biblioteca múltiples por tradición

- **Estado:** **Aceptado por el PO (2026-11-14) solo para el corte A** (cimiento y migración).
  Los cortes B–D quedan **pendientes de planificación**. Aceptar esta ADR **no implementa nada,
  no aplica la migración 0041 en producción ni despliega**; cada paso exige su autorización.
- **Relación:** #156 BL-A5 (feature #148); benchmark
  [`benchmark-BL-A5-repartir-tradiciones.md`](../design/benchmark-BL-A5-repartir-tradiciones.md)
  (nivel 2, `main@acb82a40`); especificación
  [`especificacion-BL-A5.md`](../design/especificacion-BL-A5.md) (D1–D7 aprobadas por el PO).
- **Base:** `origin/main` `acb82a40` (2026-11-14; worktree `.squad/wt-156bench`).
- **No sustituye** al benchmark ni a la especificación: fija la decisión duradera y remite a ellos
  para contratos, pruebas y detalle de implementación.

## Contexto

ZascArr nació con **una sola raíz de biblioteca**: una `library_path` (`/media/library` por
defecto, `src/zascarr/config.py:188`), un único bind mount en Compose
(`docker-compose.yml:137,171-175`) y un `File.file_path` absoluto sin pertenencia explícita a una
raíz (`models/__init__.py:780-786`). El importer construye su destino bajo esa raíz global
(`services/importer.py:490,914-954`); el escaneo, la desaparición, la auditoría, la cuarentena y
las rutas visibles también asumen una sola biblioteca.

Eso deja de servir cuando el disco se llena y las tradiciones crecen a ritmos distintos: el
coleccionista quiere que **manga** vaya a un disco y **tebeo español** a otro, sin que la app
empiece a decir que tiene archivos que no encuentra. A5 pide N raíces, un mapeo
tradición→raíz y que el importer escriba en la raíz que toca. **No incluye mover archivos ya
registrados ni montar discos desde la app**; el montaje sigue siendo una decisión del operador.

## Decisión

Se aprueban las siete decisiones D1–D7 de la especificación:

- **D1 — Configuración híbrida.** `.env`/Compose autoriza **qué montajes pueden usarse**; la BD
  guarda las raíces (nombre, ruta de contenedor, ruta de host para mostrar, habilitada,
  predeterminada) y su mapeo. Ajustes gestiona **solo raíces ya montadas**; añadir un disco exige
  montarlo y reiniciar. **No hay socket de Docker ni rutas arbitrarias desde la UI.**
- **D2 — Mapeo.** Una raíz puede servir **N tradiciones**; cada tradición resuelve a **una sola
  raíz**. No hay prioridades ni fallback implícito.
- **D3 — Tradición sin raíz: fallo cerrado.** El archivo **no se mueve**, se conserva en la cola
  de entrada y se informa con causa. No se inventa una raíz por defecto ni se elige la de más
  espacio; `_Unsorted` va solo a la raíz predeterminada explícita.
- **D4 — Los archivos existentes no se mueven.** Cambiar el mapeo o la ruta de una raíz solo
  afecta a importaciones nuevas; los `File` conservan ruta y `root_id`. Mover es otra historia,
  con dry-run, confirmación y rollback.
- **D5 — Un único `RaicesService`.** Resuelve raíz, ruta relativa, estado y `ruta_visible` para
  importer, asignación, adopter, rescan, auditoría, disponibilidad, cuarentena, conversión y
  vinculación. Ningún servicio vuelve a iterar una raíz global por su cuenta.
- **D6 — Modelo persistido y migración aditiva.** Tablas `library_roots` y
  `library_root_traditions`; `files.root_id` **nullable** con FK `RESTRICT` (nulo solo para
  archivos fuera de toda raíz). Migración **0041** aditiva: inserta la raíz 1 desde
  `library_path`/`host_library_dir`, asigna todas las tradiciones, rellena `root_id` por
  **componentes** de ruta y **no reescribe** ningún `file_path`. El `downgrade` falla cerrado si
  ya hay más de una raíz o filas asignadas a otras, para no perder pertenencia en silencio.
- **D7 — Cortes acumulativos A→B→C→D.** A: cimiento y migración, sin cambio de comportamiento;
  B: importer y asignación; C: operar N raíces (escaneo/desaparición por raíz, servicios);
  D: Ajustes y operación. A5 no se cierra con A+B+C sin D; solo A está aceptado por esta ADR.

La compatibilidad de una instalación de una raíz es parte de la decisión: misma ruta visible,
mismo `relative_to`, mismo `is_missing` y mismos recuentos tras la migración.

## Alternativas descartadas

- **`.env` como única fuente de raíces y mapeo.** Obliga a reiniciar para cada cambio, no permite
  gestionar el mapeo desde Ajustes y mezcla frontera de seguridad con datos de producto. Se
  mantiene `.env`/Compose **solo** para autorizar montajes.
- **Una raíz por tradición sin persistir.** La relación quedaría implícita en el orden de una
  lista o en el nombre de la carpeta; con dos raíces que sirven varias tradiciones, la pertenencia
  y el escaneo se vuelven ambiguos. Se persiste el mapeo con unicidad por tradición.
- **Mover los archivos existentes al cambiar la configuración.** Un ajuste podría lanzar cientos
  de GB de copia en la Pi, con disco lleno o corte a mitad; contradice A3 y la promesa de que un
  cambio de configuración no toca la colección. Será una operación explícita y separada.
- **Elegir raíz por espacio libre o por prioridad.** Rompe la promesa «cada tradición a su disco»
  y llena el disco equivocado en silencio. Sin raíz, fallo cerrado.
- **Ruta libre escrita en Ajustes.** Permitiría escribir fuera de los montajes autorizados
  (path traversal, symlink, disco del sistema). Solo se eligen montajes declarados por el
  operador; la ruta se valida por componentes, inodo y symlink resuelto.
- **Múltiples `rglob`/raíces por consumidor.** Cada servicio implementaría su propia semántica de
  raíz; las diferencias serían bugs de disponibilidad y de archivos ausentes. Un solo
  `RaicesService`.

## Consecuencias

- **Migración 0041:** crea `library_roots`/`library_root_traditions`, añade `files.root_id` y
  rellena la raíz 1; es aditiva y no mueve archivos. `upgrade` no depende de que la raíz esté
  montada; `downgrade` se niega si ya hay raíces adicionales o pertenencia que se perdería.
- **`root_id` nullable:** los archivos fuera de toda raíz se muestran «fuera de raíz»; no se les
  inventa raíz ni se marcan ausentes por la caída de una raíz.
- **Corte B:** importer y asignación resuelven raíz antes de construir la ruta y guardan
  `root_id`; una tradición sin raíz no mueve el archivo.
- **Corte C:** escaneo, rescan, desaparición y disponibilidad **por raíz**; una raíz caída no
  contamina a las demás; auditoría/cuarentena/conversión/vinculación/portadas/rutas visibles usan
  la raíz del archivo.
- **Corte D:** Ajustes lista raíces montadas, estado/espacio, mapeo tradición→raíz, alta solo de
  montados, habilitar/deshabilitar y borrado bloqueado con archivos.
- **Pruebas:** Postgres real para 0041/backfill/constraints y filesystem real para dos raíces,
  raíz caída, EXDEV, disco lleno, permisos y no-regresión de una sola raíz.
- **No se implementa ni se migra en este ADR.** No hay código nuevo, no se aplica 0041 y no se
  toca producción; la aceptación es para el corte A y los cortes B–D siguen sin planificar.

## Estado

**Aceptado por el PO el 2026-11-14, únicamente para el corte A.** B–D quedan pendientes de
planificación; la migración 0041 no está aplicada y este ADR no autoriza ejecución en producción
ni despliegue. Referencias: #156, benchmark y especificación enlazados arriba.
