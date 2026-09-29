# Ficha — Lote de integridad: hash de fichero, dedupe y etiquetado (B6 ↔ B3/B16)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). Es un
> **arreglo con cambio de esquema**, así que lleva ficha antes de código. El
> riesgo no es el volumen de código: es **perder la identidad de un fichero**
> y con ella el dedupe, o que un ciclo del importador reviente para siempre.

**Estado:** propuesta para validar. No hay código escrito.

## Historia / problema observado

Revisión de deuda técnica de las PR anteriores (2026-09-29). Tres hallazgos
del mismo mecanismo: **`File.sha256_hash` hace dos trabajos incompatibles**.

1. **Identidad del original (dedupe).** `Importer` y `LibraryAdopter` comparan
   el hash del fichero entrante con `File.sha256_hash`
   (`select(File).where(File.sha256_hash == tr.sha256)`, vía
   `_triage_and_match`).
2. **Huella de lo que hay ahora en disco (integridad).** `TaggerService` (B6)
   **recalcula y sobrescribe** `sha256_hash`/`file_size_bytes` tras cada
   `os.replace`, y la marca de revisión compara contra él.

Al etiquetar un CBZ, su hash cambia (el `ComicInfo.xml` cambia los bytes). Desde
ese momento, **el mismo tebeo entrante ya no coincide** con la fila de la
biblioteca: se importaría como un duplicado nuevo.

Dos problemas relacionados:

3. **Lectura frágil.** La consulta de dedupe usa `scalar_one_or_none()` sobre
   una columna con índice **no único** (`idx_files_hash`, migración 0001).
   Con dos filas con el mismo hash, SQLAlchemy lanza `MultipleResultsFound`.
4. **Confirmado al leer el código (B7 + D8).** El dedupe
   (`select(File).where(File.sha256_hash == tr.sha256)`) **no filtra por
   `is_missing`**: si la única fila coincidente tiene `is_missing = true` (el
   fichero desapareció), un fichero que vuelve a llegar se descarta como
   «duplicado de un archivo que ya no existe». Es justo lo que produce D8 al
   reactivar un item `IMPORTED` cuyo fichero desapareció: el fichero recién
   reencontrado nunca se reimporta y el item queda `WANTED` para siempre. La
   prueba de caracterización lo fija como regresión antes de aplicar el
   arreglo.

## Datos reales y medición de partida

Verificado en el código (`main` en `7f6f637`, que ya incluye D8 #34; los
ficheros citados —`importer.py`, `tagger.py`, `library_adopter.py` y el modelo—
no los tocó D8, así que lo de abajo sigue en pie):

- `models.File.sha256_hash`: `String(64)`, `index=True`, **sin unicidad**;
  la migración 0001 crea `idx_files_hash`, también no único.
- `importer.py` y `library_adopter.py` comparten `_triage_and_match`; el
  descarte por duplicado sale de `existing = select(File).where(File.sha256_hash
  == tr.sha256)` seguido de `scalar_one_or_none()`.
- `tagger.py::_anotar_escritura` hace `file.sha256_hash = sha` tras el reemplazo
  y `_sincronizar` lo reconcilia contra el disco.
- `library_audit.py` calcula sus propios hashes **sobre el disco** (solo de los
  ficheros que comparten tamaño), así que **no** depende de `File.sha256_hash`.

Alcance real hoy: B6 solo se ejecuta a mano (`scripts/etiquetar.sh --apply`); no
hay botón de UI ni automatización. El fallo 1 es **latente**: se materializa en
cuanto alguien etiqueta a escala o B6 se automatiza. Por eso se arregla ahora.

No hay medición contra la biblioteca real (la primera instalación sigue
pendiente): no sé cuántos ficheros están ya etiquetados.

## Referencias consultadas

- **SQLAlchemy**: `Result.scalar_one_or_none()` «raises MultipleResultsFound»
  si hay más de una fila — documentación oficial de `Result`/`Query`
  (`one_or_none`), comprobada.
- **Kavita, wiki de ComicInfo**: el fichero debe llamarse `ComicInfo.xml` y estar
  en la raíz del archivo. Confirma la decisión de B6 de normalizar a una sola
  entrada en la raíz; **no** dice nada del hash.
- **Sin referencia comparable encontrada** sobre qué hacen Kapowarr, Mylar3 o
  ComicTagger con la identidad de un fichero tras escribir `ComicInfo.xml`. No
  se cita de memoria: el diseño de abajo se apoya en el código propio y en el
  invariante de A3 («el importador nunca pierde un original»), no en una
  convención del ecosistema que no he podido verificar.

## Cómo lo resuelve cada una

No aplica de forma verificada (ver arriba). Lo que sí se sabe del propio
proyecto: B16 ya separa «mismo contenido» (SHA256 idéntico) de «misma obra, otra
copia» (mismo título y número, contenido distinto); y B6 ya decidió que
recalcular el hash tras escribir es necesario para reconciliar la BD con el
disco.

## Supuestos que NO valen en ZascArr

- **«Un fichero tiene un único hash a lo largo de su vida».** B6 cambia sus
  bytes a propósito.
- **«`sha256_hash` es único».** El esquema no lo garantiza y una carrera entre
  dos ciclos del importador puede crear dos filas con el mismo hash.
- **«Una fila de `File` implica que el fichero existe».** B7 introdujo
  `is_missing`; el dedupe tiene que decidir qué hace con esas filas.

## Adoptar / adaptar / descartar, con motivo

- **Adoptar (arreglo 1): columna `File.original_sha256`**, nullable, con índice
  no único. Guarda el hash del fichero **tal como se importó**, antes de la
  primera reescritura por B6. El dedupe busca por `sha256_hash` **o**
  `original_sha256`. No obliga a rehashear nada y sirve para CBR y demás
  formatos.
- **Adoptar (arreglo 2): lectura robusta.** `select(...).order_by(...).limit(1)`
  con `.first()`, orden determinista (las presentes —`is_missing = false`—
  primero, luego por `imported_at`), y un `logger.warning` si hay más de una
  coincidencia para que los duplicados en la BD sean visibles.
- **Adaptar (cuándo se fija `original_sha256`):** solo la **primera** vez que
  B6 reemplaza un CBZ y solo si aún es `NULL`. El valor sale de
  `file.sha256_hash` **si** `file_size_bytes` coincide con el `stat` actual; si
  no coincide (la BD estaba desfasada), se calcula del disco justo antes de
  reemplazar. Nunca se sobrescribe después: ni el *overlay* ni
  `--reconciliar-todo` lo tocan.
- **Descartar: un hash del manifiesto de páginas** (como clave de dedupe
  independiente de los metadatos). Sería más fuerte, pero obliga a descomprimir
  cada entrada de cada CBZ en la Pi, no sirve para CBR y `original_sha256` da lo
  que hace falta sin coste extra.
- **Descartar: índice único en `sha256_hash`.** Fallaría al migrar si ya hay
  filas repetidas y prohibiría un caso que debe poder representarse (dos
  copias conocidas). Se resuelve leyendo con robustez, no con una restricción
  que pueda romper la instalación.
- **Descartar: rellenar `original_sha256` de lo ya etiquetado.** El hash
  original de esos ficheros ya se perdió y no se puede reconstruir. Se dice, no
  se inventa: esos ficheros solo los detecta la auditoría B16 como «misma obra,
  otra copia».
- **Arreglo (hallazgo 4, confirmado): reenlazar** la fila existente en vez de
  descartar el fichero, **solo cuando TODAS las coincidencias por hash están
  `is_missing`** (el orden de lectura ya trae las presentes primero: si hay una
  presente, es un duplicado real y se descarta). El reenlace conserva la fila
  vieja (y su enlace a `Issue`/`Series`) y hace tres cosas que no pueden
  omitirse:
  1. **`imported_at = now()`.** D8 cierra un item con
     `File.imported_at >= Wishlist.added_at`, y reactivar un `IMPORTED` reinicia
     `added_at`. Si el reenlace conserva el `imported_at` viejo, el item
     reactivado no se cierra nunca — el mismo bucle, movido de sitio. Se fija con
     una prueba de extremo a extremo (ver caso 9).
  2. **La fila describe el fichero nuevo:** se actualizan `file_path`,
     `file_name`, `file_size_bytes` y `sha256_hash` con los del entrante, y
     `is_missing = false` / `missing_since = NULL`. Si el entrante es el
     **original** de una fila que estaba etiquetada, se vacían `comicinfo_estado`
     y `comicinfo_propio` (describen un fichero que ya no existe).
     `original_sha256` se conserva.
  3. **Qué informa el ciclo:** cuenta como **importado**, con una línea del
     informe que diga «recuperado» para distinguirlo — así el aviso E4 se
     dispara igual que con una importación normal (el coleccionista ve que un
     deseo se ha cumplido), sin esconder que no fue una importación nueva.

## Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi)

- **No perder un original:** un fichero entrante que es el mismo tebeo que uno
  ya etiquetado se reconoce como duplicado; nunca se importa dos veces en
  silencio ni se descarta uno que no lo es.
- **No mentir:** si `original_sha256` es desconocido (fichero ya etiquetado
  antes de este cambio), no se rellena con un valor inventado.
- **Coste Pi:** cero hashes extra en el caso normal; un solo hash del disco
  cuando la BD estaba desfasada, y solo la primera vez que se etiqueta ese
  fichero.
- **Migración aditiva:** una columna nullable y un índice; sin reescribir filas,
  compatible con `update.sh` y con `rollback.sh` (que restaura desde el volcado,
  no deshace la migración).

## Casos de prueba antes de implementar (deben fallar contra `main`)

1. **Etiquetar y volver a importar el original:** tras `ejecutar(dry_run=False)`,
   un CBZ con el contenido original se reconoce como duplicado. *(Falla hoy.)*
2. **Dos filas con el mismo hash:** el ciclo del importador con ese hash no lanza
   `MultipleResultsFound`, reporta el duplicado y deja un aviso en el log.
   *(Falla hoy.)*
3. **`original_sha256` se fija una vez:** una segunda escritura (por *overlay*)
   y `--reconciliar-todo` no lo cambian.
4. **Origen del valor:** con `sha256_hash` desfasado respecto al disco, se guarda
   el hash **del disco** previo al reemplazo, no el de la BD.
5. **Migración con sembrado previo:** las filas anteriores quedan con
   `original_sha256 = NULL` y el resto de columnas intactas (mismo patrón que
   `tests/test_migracion_d8_pg.py`).
6. **`LibraryAdopter`** usa la misma consulta: un CBZ etiquetado ya en la
   biblioteca no se readopta como nuevo.
7. **Caracterización de B7 + dedupe:** una fila `is_missing = true` con el hash
   de un fichero que reaparece. Confirmado por lectura del código que **falla
   hoy** (el dedupe descarta el fichero como duplicado); la prueba fija la
   regresión y el arreglo de reenlazado la hace pasar.
8. **Un CBR nunca cambia:** `original_sha256` permanece `NULL` porque B6 no lo
   toca.
9. **Extremo a extremo con D8:** un item de política `IMPORTED` cuyo fichero
   desaparece (`is_missing`) se reactiva a `WANTED` (D8), el fichero vuelve a
   llegar, se reenlaza la fila y el item pasa a `IMPORTED`. Fija el reinicio de
   `imported_at`: si el reenlace lo conservara viejo, `_is_fulfilled` no cerraría
   el item y quedaría `WANTED` para siempre.
10. **El reenlace describe el fichero nuevo:** `file_path`/`file_name`/
    `file_size_bytes`/`sha256_hash` pasan a los del entrante; si era el original
    de una fila etiquetada, `comicinfo_estado` y `comicinfo_propio` quedan vacíos;
    `original_sha256` se conserva.
11. **Solo se reenlaza si no hay ninguna presente:** con dos filas del mismo
    hash, una `is_missing` y otra presente, el entrante se descarta como
    duplicado (no se reenlaza nada).

## Orden de commits sugerido

1. Pruebas 1, 2 y 7 (las dos primeras deben fallar) más la de migración.
2. Modelo + migración 0016 (columna e índice).
3. `TaggerService` fija `original_sha256` la primera vez.
4. Consulta de dedupe compartida (`or_` de los dos hashes, `.first()`, orden
   determinista, aviso por coincidencias múltiples).
5. Arreglo del hallazgo 4 (reenlazado de la fila `is_missing`), exigido por la
   prueba 7.
6. Notas en `docs/BACKLOG.md` (deuda registrada, con lo que **no** se arregla).

La prueba 9 (extremo a extremo con D8) entra **en esta misma PR**: D8 ya está
en `main` (merge de #34, `7f6f637`), así que no hay que esperar a otra fusión
para escribirla. Los casos 10 y 11 entran junto al commit 5.

## Lo que no está verificado

- **Cuántos ficheros están ya etiquetados** en una biblioteca real: sin base de
  datos real en este entorno.
- **Comportamiento de otras herramientas** del ecosistema (ver «Referencias»).

> **Validación del agente (2026-09-29):** se leyó `importer.py` entero,
> `library_adopter.py`, `tagger.py` y el modelo `File`. Todo lo afirmado en
> «Datos reales» es exacto, y el hallazgo 4 queda **confirmado**: el dedupe
> (`importer.py::_triage_and_match`, ~línea 148) consulta
> `select(File).where(File.sha256_hash == tr.sha256).scalar_one_or_none()` **sin
> filtrar `is_missing`**, y `tagger.py::_anotar_escritura` (~línea 497)
> sobrescribe `sha256_hash`/`file_size_bytes` tras `os.replace`. La consulta
> frágil (`scalar_one_or_none` sobre columna no única, hallazgo 7) también está
> confirmada.

## Decisión final / ADR

No requiere ADR (cambio de esquema aditivo y de lectura, no de arquitectura).
Entregable: migración 0016 + `TaggerService` + consulta de dedupe compartida +
las once pruebas, en una PR separada de la ficha.
