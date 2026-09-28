# Ficha de benchmarking — escritura segura de `ComicInfo.xml` (B6)

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). El riesgo
> no es el XML: es **reemplazar el archivo del coleccionista**.

**Historia / problema observado:**
B6 — tras enriquecer, escribir `ComicInfo.xml` **dentro** del CBZ para que
Kavita/ComicTagger/cualquier otra herramienta lean la biblioteca sin depender de
ZascArr. Hoy `core/importer_triage.py` **solo lee** ComicInfo; `utils/comicinfo.py`
es únicamente un alias de ese lector. No existe ninguna escritura.

**Datos reales y medición de partida:**
Bibliotecas reales aportadas: mezcla de `.cbz` y `.cbr`. **CBR nunca se
parchea** (decisión ya tomada en B20: escribir RAR exige una dependencia
propietaria descartada; sonda del 2026-09-25 → 0,5 % de ComicInfo en CBR).
Campos que ZascArr conoce hoy del esquema: `Series`, `Number`, `Volume`, `Year`,
`Publisher`, `Summary`, `Genre`, `LanguageISO`, `PageCount` y créditos por rol.

**Referencias consultadas (URL, versión/commit):**
- **ComicTagger** (referencia de facto del formato): hace *merge* campo a campo
  y **respeta** lo que ya existe; escribe `ComicInfo.xml` como **una sola**
  entrada. Patrón de referencia; versión/commit no fijado.
- **Mylar3** (GPL-3.0): anuncia escritura de ComicInfo tras enriquecer.
- **Sonarr/Radarr**: escriben `.nfo` **al lado**, no reescriben el archivo de
  medios — no sirven de patrón para «modificar el contenedor».
- **Kapowarr**: patchea CBZ; su tracker documenta bloqueos por hacerlo con el
  fichero de origen abierto (de ahí la regla de ZascArr: mover/cerrar primero,
  commit corto después — CLAUDE.md §3.1).

**Supuestos que NO valen en ZascArr:**
- ComicTagger opera sobre un archivo elegido a mano y con el usuario delante;
  aquí es un servicio desatendido sobre la biblioteca **canónica** del
  coleccionista. Un fallo a medias no puede costarle un tebeo.
- Sonarr/Radarr no reescriben el contenedor: su patrón no cubre el riesgo real
  (una sustitución atómica de un ZIP).

**Contrato local (lo que fija esta ficha):**

1. **Preservar campos manuales.** Se lee primero el `ComicInfo.xml` existente;
   se conserva **todo** lo que ZascArr no gestiona (p. ej. `Characters`,
   `StoryArc`, `Notes`, `ScanInformation`…) y **no** se pisan los campos que el
   humano fijó: si `Series.locked_fields`/`Issue.locked_fields` (H3) marca un
   campo, se respeta. La persona manda sobre la heurística.
2. **Sin duplicados.** El XML se escribe como **una sola** entrada
   `ComicInfo.xml`. Si el CBZ ya trae una (o varias), se **normaliza a una**;
   nunca se añade una segunda.
3. **Verificar ANTES de sustituir.** El CBZ nuevo se construye en un temporal
   **en el mismo directorio** (mismo sistema de ficheros) y se comprueba — ZIP
   íntegro (`testzip`), **mismo conjunto de entradas** que el original más el
   XML, y el XML **parseable** por el propio lector — y **solo entonces**
   `os.replace(temp, original)`, que es atómico. Nada de escribir sobre el
   original in situ.
4. **Espacio temporal en la Pi = criterio de seguridad.** El temporal ocupa
   ~el tamaño del original. Antes de empezar se comprueba el espacio libre
   necesario (+ margen) y, si no lo hay, se **aborta sin tocar el original**.
   En una Pi compartida (512 M de presupuesto, disco del usuario) esto no es
   una optimización: es la diferencia entre «no se pudo etiquetar» y «se llenó
   el disco a mitad de la copia».
5. **CBR/CB7/PDF no se parchean.** Viajan tal cual (B20); si algún día se
   quieren etiquetar, es una historia aparte (conversión opt-in).
6. **Nada bloqueante en el loop async.** `zipfile` + disco van a
   `asyncio.to_thread` (CLAUDE.md §4).

**Invariantes de ZascArr:**
- El original **no se borra ni se trunca** hasta que el reemplazo está
  verificado; un fallo a mitad deja el original intacto y limpia el temporal.
- Un CBZ hardlinkeado desde una exportación B20 puede compartir inodo con la
  canónica: B20 ya decidió exportar con `copy` si el fichero **se va a
  parchear**; B6 respeta esa frontera (nunca parchea el destino de una
  exportación).

**Casos de prueba antes de implementar:**
- CBZ con `ComicInfo.xml` manual → los campos manuales siguen ahí tras escribir.
- CBZ con **dos** `ComicInfo.xml` → el resultado tiene exactamente uno.
- ZIP corrupto a mitad de reconstrucción → original intacto, temporal limpiado.
- Espacio libre insuficiente → aborta, original intacto.
- `.cbr` → no se toca.
- El CBZ reconstruido se abre y conserva **todas** las páginas.
- Campo en `locked_fields` → no se sobrescribe.

**Decisión final / ADR:** no requiere ADR propio (es una operación de fichero,
no una decisión de arquitectura); la frontera con B20 (hardlink + parche) ya
está en su spec. **Implementación fuera de esta ficha**: esto fija el contrato y
los casos de prueba, no escribe aún el código.
