# Ficha de benchmarking — escritura segura de `ComicInfo.xml` (B6)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). El riesgo
> no es el XML: es **reemplazar el archivo del coleccionista** y **dejar la BD
> y los datos de `File` coherentes con lo que hay en disco**.

**Historia / problema observado:**
B6 — tras enriquecer, escribir `ComicInfo.xml` **dentro** del CBZ para que
Kavita/ComicTagger/cualquier otra herramienta lean la biblioteca sin depender de
ZascArr. Hoy `core/importer_triage.py` **solo lee** ComicInfo; `utils/comicinfo.py`
es únicamente un alias de ese lector. No existe ninguna escritura.

**Datos reales y medición de partida:**
Bibliotecas reales aportadas: mezcla de `.cbz` y `.cbr`. **CBR nunca se
parchea** (decisión de B20: escribir RAR exige una dependencia propietaria
descartada; sonda del 2026-09-25 → 0,5 % de ComicInfo en CBR). Campos que
ZascArr conoce hoy del esquema: `Series`, `Number`, `Volume`, `Year`,
`Publisher`, `Summary`, `Genre`, `LanguageISO`, `PageCount` y créditos por rol.
`File` persiste `sha256_hash` **y** `file_size_bytes`, y el importador usa el
**hash** para detectar duplicados.

**Referencias consultadas (URL, versión/commit):**
- **ComicTagger** (referencia de facto del formato): hace *merge* campo a campo,
  **respeta** lo que ya existe y escribe `ComicInfo.xml` como **una sola**
  entrada. Distingue estrategias de **overlay** (la fuente manda) y **add
  missing** (solo rellenar vacíos) — **no son equivalentes** y la elección es
  justo la decisión 1 de abajo. Versión/commit no fijado.
- **Mylar3** (GPL-3.0): anuncia escritura de ComicInfo tras enriquecer.
- **Sonarr/Radarr**: escriben `.nfo` **al lado**, no reescriben el archivo de
  medios — no sirven de patrón para «modificar el contenedor».
- **Kapowarr**: patchea CBZ; su tracker documenta bloqueos por hacerlo con el
  fichero de origen abierto (de ahí la regla de ZascArr: mover/cerrar primero,
  commit corto después — CLAUDE.md §3.1).

**Supuestos que NO valen en ZascArr:**
- ComicTagger opera sobre un archivo elegido a mano y con el usuario delante;
  aquí es un servicio desatendido sobre la biblioteca **canónica**. Un fallo a
  medias no puede costarle un tebeo.
- Sonarr/Radarr no reescriben el contenedor: su patrón no cubre el riesgo real
  (sustituir un ZIP de forma atómica **y** durable).

## Contrato local (lo que fija esta ficha)

1. **Conflicto con XML manual — regla explícita de procedencia.** `locked_fields`
   protege campos en la BD, pero **no demuestra** que un `Summary`, `Series` o
   crédito ya presente en el XML lo escribiera ZascArr. Para un campo
   **gestionado y ya presente con procedencia desconocida**, la regla es:
   - **vacío en el XML** → se rellena (*add missing*);
   - **presente y ZascArr puede probar que lo escribió** (marca de procedencia
     que ZascArr deja al escribir, o registro del último XML escrito) →
     **se actualiza** (*overlay*);
   - **presente y de procedencia desconocida → se conserva por defecto**; solo
     se sustituye con **autorización explícita** del coleccionista.
   Esto exige que ZascArr **deje rastro de autoría** al escribir (un marcador en
   el propio XML o el hash del último XML escrito persistido en `File.metadata_`),
   para poder distinguir «lo escribí yo» de «lo escribió una persona/otra
   herramienta».
2. **Sin duplicados.** `ComicInfo.xml` como **una sola** entrada; si el CBZ ya
   trae una o varias, se normaliza a una. Nunca dos.
3. **Integridad real, no solo `testzip()`.** `ZipFile.testzip()` valida CRC y
   cabeceras del ZIP **nuevo**, pero no acredita que cada página conserve los
   mismos bytes. Además de él: **manifiesto de hashes por entrada** (nombre →
   SHA256 del contenido, calculado **por streaming**) de todas las entradas
   **no-XML**, exigiendo coincidencia exacta con el original, y **exactamente
   una** entrada `ComicInfo.xml`.
4. **Verificar ANTES de sustituir.** El CBZ nuevo se construye en un temporal
   **en el mismo directorio** (mismo sistema de ficheros); se comprueban los
   puntos 2 y 3; y **solo entonces** `os.replace(temp, original)`. Nada de
   escribir sobre el original in situ.
5. **Durabilidad (distinta de atomicidad).** `os.replace` da atomicidad, **no**
   persistencia frente a un corte de luz. Antes del reemplazo se hace
   `fsync` del **temporal**; después, cuando el sistema de ficheros lo permite,
   `fsync` del **directorio** para persistir el renombrado. Se documenta que son
   dos garantías distintas.
6. **`File.sha256_hash`/`file_size_bytes` cambian con el XML.** Añadir XML
   cambia los bytes del CBZ: tras `os.replace` deben **recalcularse y
   persistirse**. **Reconciliación si el reemplazo tiene éxito pero falla el
   commit de BD:** el fichero queda etiquetado y la BD con el hash viejo; el
   reetiquetado es **idempotente** (si el XML ya es el que ZascArr escribió, no
   rehace nada) y el siguiente ciclo **reconcilia** (hash de disco ≠ hash
   guardado → actualizar `File`, sin tratar el fichero como duplicado nuevo).
   Efecto colateral a cubrir: dos copias antes idénticas (mismo hash) pueden
   dejar de serlo si se etiquetan en momentos distintos.
7. **Espacio temporal en la Pi = criterio de seguridad.** El temporal ocupa
   ~el tamaño del original. Antes de empezar se comprueba el espacio libre
   necesario (+ margen) y, si no lo hay, se **aborta sin tocar el original**.
   En una Pi compartida (512 M de presupuesto, disco del usuario) no es una
   optimización: es la diferencia entre «no se pudo etiquetar» y «se llenó el
   disco a mitad de la copia».
8. **CBR/CB7/PDF no se parchean.** Viajan tal cual (B20); un CBZ hardlinkeado
   desde una exportación se respeta (B20 ya decide `copy` si se va a parchear).
9. **Nada bloqueante en el loop async.** `zipfile` + disco van a
   `asyncio.to_thread` (CLAUDE.md §4).

**Invariantes de ZascArr:**
- El original **no se borra ni se trunca** hasta que el reemplazo está
  verificado (integridad, no solo CRC).
- Un fallo a mitad deja el original intacto y limpia el temporal.
- Ningún campo manual se pisa sin autorización o prueba de autoría.

**Casos de prueba antes de implementar:**
- **Procedencia:** XML manual con `Summary`/créditos propios y sin marca de
  ZascArr → **no** se sobrescriben; con marca de ZascArr → sí se actualizan.
- **Duplicados:** CBZ con **dos** `ComicInfo.xml` → exactamente uno tras escribir.
- **Integridad:** hashes de las entradas no-XML idénticos al original; todas las
  páginas conservadas.
- **Fallo a mitad:** ZIP corrupto en la reconstrucción → original intacto.
- **Espacio:** libre insuficiente → aborta, original intacto.
- **Hash/BD:** tras etiquetar, `sha256_hash`/`file_size_bytes` actualizados.
- **Fallo entre reemplazo y BD:** reemplazo correcto + commit fallido →
  reetiquetado idempotente y el siguiente ciclo reconcilia el hash.
- **`.cbr`** → no se toca.
- **Campo en `locked_fields`** → no se sobrescribe.

**Decisión final / ADR:** no requiere ADR propio (operación de fichero, no de
arquitectura); la frontera con B20 (hardlink + parche) ya está en su spec.
**Esta ficha sigue siendo solo documental**: fija el contrato y los casos de
prueba, no implementa aún la escritura.
