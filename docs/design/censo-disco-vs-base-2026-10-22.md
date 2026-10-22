# Censo del disco frente a la base (Pi, 2026-10-22) — ficha del spike #297

> **Estado: medición hecha, decisiones PROPUESTAS, nada ejecutado.** Solo lectura: no se registró, movió, borró ni apartó ningún fichero. Herramienta: `scripts/medicion/censo_disco_vs_base.py`. Entorno: la Pi del PO, ZascArr `245402e`, biblioteca `/media/WDElements/Tebeos`, datos tomados el 2026-10-22 (dos listados de texto y las huellas SHA-256 de los tebeos sin registrar). **NOT RUN:** tamaño en GB de lo duplicado, y la identidad de los 12 ficheros sin extensión.

## Pregunta
El inventario del disco da **1577** ficheros y la base tiene **1339** archivos. ¿Faltan tebeos en ZascArr? ¿Por qué hay ficheros del disco sin fila?

## Resultado

| Qué | Cantidad |
|---|---|
| Ficheros en el disco | 1577 |
| Filas en la base | 1339 (**1325** con su fichero por la misma ruta; **14** marcadas `is_missing`, ninguna sin marcar) |
| En el disco sin fila en la base | **252** |
| · tebeos (`.cbr`/`.cbz`) sin registrar | **217** |
| · formato que ZascArr no lee (`.rar` ×21, `.tar` ×1) | 22 |
| · sin extensión | 12 |
| · descarga a medias (`.part`) | 1 |
| · misma ruta con otra forma (mayúsculas o Unicode) | 0 |

**Los 217 tebeos sin registrar son copias exactas de un archivo ya registrado**: los 217 tienen el mismo SHA-256 que una fila de la base (217/217, 0 con contenido nuevo, 0 sin hash). **No falta ningún tebeo en ZascArr por este motivo**: lo que no está registrado es el segundo ejemplar.

| Carpeta sin registrar | Copias | Carpeta donde está el original registrado |
|---|---|---|
| `Comics/Superman Vol2 (Ed.Zinco)(1987-96)` | 136 (+1) | `Comics/Superman (1987)` (+1 en `Comics/Flash (1987)`) |
| `Comics/Nuevos Mutantes Vol3 (Panini)(2020-23)` | 30 | `Comics/Nuevos Mutantes (2019)` |
| `Tebeos/Carlos Giménez` | 26 | `Graphic Novels/Carlos Gimenez` |
| `Comics/_Omnibus` | 12 | `Comics/Patrulla-X (Panini)` |
| `Comics/La Liga de los Hombres Extraordinarios (1999)` | 7 | la **misma** carpeta (copias con otro nombre) |
| `Comics/Patrulla-X (Panini)` | 4 | `Comics/Inferno (2021)` |
| `Comics/Superman (1987)` | 1 | `Comics/Flash (1987)` |

## Interpretación (lo que se sabe y lo que no)
- **Se sabe:** son copias byte a byte (mismo SHA-256) de ficheros registrados. El importador no registra la segunda copia de algo que ya conoce (deduplicación por huella), de ahí que no aparezcan. No es un fallo de la actualización del 22 de octubre (el actualizador no toca la biblioteca; la base tiene las mismas 1339 filas que antes).
- **Dos grupos son carpetas enteras duplicadas** (Superman Zinco y Carlos Giménez) y los demás son ejemplares sueltos en otras carpetas. Que un archivo de `Superman` o de `Patrulla-X` sea idéntico a uno de `Flash` o `Inferno` sugiere ejemplares **mal ubicados** en su carpeta (no se verificó a mano).
- **No se sabe:** (1) cuántos GB ocupan las 217 copias; (2) qué son los 12 ficheros sin extensión (carpetas `Graphic Novels/…`); (3) por qué las 14 filas `is_missing` no tienen fichero (la herramienta cuenta cuántos «idénticos» apuntan a una fila `is_missing`, que serían movimientos y no copias: no se había incluido en la primera ejecución); (4) si los `.rar`/`.tar` son tebeos en otro contenedor.
- Corrección de una lectura previa: al ver 1577 frente a 1339 se habló de «unos 200 tebeos sin registrar» como si faltaran en la colección; la medición por contenido dice que **no**: son duplicados.

## Decisiones propuestas (NO ejecutadas; del PO)
1. **217 copias idénticas:** no adoptarlas (registrarlas duplicaría la colección). Qué hacer con ellas (dejarlas, apartarlas o borrarlas a mano) es la historia de duplicados **#264** (apartar una copia idéntica, con vista previa y deshacer), cuyo spike de medición es **#263**: estas cifras son su primera muestra real. Hasta entonces, nada se mueve ni se borra.
2. **22 formatos no soportados (`.rar`, `.tar`):** decidir si ZascArr debe leerlos (historia nueva, con benchmark §13) o si se convierten fuera de ZascArr.
3. **12 sin extensión y 1 `.part`:** identificarlos a mano (`file` y tamaño) antes de decidir; el `.part` es una descarga a medias.
4. **14 filas `is_missing`:** comprobar si son movimientos (rutas nuevas con la misma huella) antes de tocar nada.
5. **Pantalla:** que «Duplicados» enseñe estas copias con la ruta real (#294) para que la persona las vea sin comandos.

## Cómo repetirlo
Los comandos están en la cabecera del script (`scripts/medicion/censo_disco_vs_base.py`): dos listados de solo lectura, `sha256sum` de los tebeos sin registrar y el propio script. Reproducible; el script no abre la base ni el disco.
