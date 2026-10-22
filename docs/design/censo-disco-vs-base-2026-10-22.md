# Censo del disco frente a la base (Pi, 2026-10-22) — ficha del spike #297

> **Estado: medición completa; decisiones PROPUESTAS, nada ejecutado.** Solo lectura: no se registró, renombró, movió, borró ni apartó ningún fichero. Herramienta: `scripts/medicion/censo_disco_vs_base.py` (más `stat`, `file`, `sha256sum` y `awk` en la Pi). Entorno: la Pi del PO, ZascArr `245402e`, biblioteca `/media/WDElements/Tebeos`, datos del 2026-10-22. **NOT RUN:** abrir los contenedores para confirmar que contienen imágenes de tebeo; el contenido de los 14 ficheros desaparecidos.

## Pregunta
El inventario del disco da **1577** ficheros y la base tiene **1339** archivos. ¿Faltan tebeos en ZascArr? ¿Por qué hay ficheros del disco sin fila?

## Resultado en una línea
De los **252** ficheros del disco sin fila, **222 son copias exactas** de algo ya registrado (no falta nada), y **29 son contenido que ZascArr no conoce**, guardado en contenedores que ZascArr no lee (`.rar`, `.tar`) o que no tienen extensión. El resto (1) es una descarga a medias.

## Cómo cuadran las cifras

| Cuenta | Operación | Resultado |
|---|---|---|
| Ficheros del disco con fila en la base (misma ruta) | — | **1325** |
| Filas de la base sin fichero (todas `is_missing`, ninguna con huella) | 1339 − 1325 | **14** |
| Ficheros del disco **sin fila** | 1577 − 1325 | **252** |
| Diferencia «a ojo» entre totales | 1577 − 1339 | 238 = 252 − 14: **no** es una cantidad de copias ni de ficheros nuevos |

Los 252 se reparten así, **por contenido (SHA-256)**:

| Grupo | Ficheros | Qué son |
|---|---|---|
| Tebeos `.cbr`/`.cbz` sin registrar | 217 | **Copias exactas** de un archivo registrado (217/217 con la misma huella; 0 con contenido nuevo) |
| Sin extensión | 12 | **5 copias** (Carlos Gimenez: Barrio, Dani Futuro, Delta 99, España Una-Grande-Libre, Paracuellos) y **7 contenido nuevo** (Batman DK2, Beto Hernandez, Hard Boiled, Jaime Hernandez, Neil Gaiman, Paul Pope, Tillie Walden). `file` los identifica como contenedores comprimidos: 9 RAR, 2 ZIP y 1 7-zip (20–250 MB cada uno) |
| `.rar` | 21 | **Contenido nuevo:** 21 volúmenes de *One Piece* (Manga/One Piece, vols. 76–96; el 76 se llama `….cbz.rar`) |
| `.tar` | 1 | **Contenido nuevo:** *Paracuellos (Glenat)(1999-2022)* completo |
| Descarga a medias (`.part`) | 1 | No se hashea: es un fichero incompleto |
| **Total** | **252** | 217 + 5 = **222 copias**; 7 + 21 + 1 = **29 contenido nuevo**; 1 `.part` (217 + 12 + 21 + 1 + 1 = 252) |

Las **217 copias por carpeta**: `Comics/Superman Vol2 (Ed.Zinco)(1987-96)` 136 → `Comics/Superman (1987)`; 1 → `Comics/Flash (1987)`; `Comics/Nuevos Mutantes Vol3 (Panini)(2020-23)` 30 → `Comics/Nuevos Mutantes (2019)`; `Tebeos/Carlos Giménez` 26 → `Graphic Novels/Carlos Gimenez`; `Comics/_Omnibus` 12 → `Comics/Patrulla-X (Panini)`; `Comics/La Liga de los Hombres Extraordinarios (1999)` 7 → la misma carpeta (otro nombre); `Comics/Patrulla-X (Panini)` 4 → `Comics/Inferno (2021)`; `Comics/Superman (1987)` 1 → `Comics/Flash (1987)`. Total 136 + 1 + 30 + 26 + 12 + 7 + 4 + 1 = **217**.

**Espacio:** las 217 copias ocupan **8,1 GB**; las 217 tienen un solo nombre (`stat %h = 1`), es decir, **ningún enlace duro**: son copias con almacenamiento propio. Eso mide lo que ocupan, no autoriza recuperarlo.

## Las 14 filas «no encontradas»
Todas están en `/media/library/_Unsorted/…` (sobre todo *La Patrulla X*, *Marvel Gold*, *La Imposible Patrulla X*, y *The Boys*), todas son `.cbr` y **ninguna tiene huella** en la base (14/14 sin `sha256_hash`), así que **no se pueden comparar por contenido**. Por nombre de fichero, **13 no aparecen en el disco** y 1 (*Marvel Gold - La Patrulla-X Original 2 (4).cbr*) sí. Conclusión honesta: 13 desaparecieron o se renombraron; de 1 hay un fichero con el mismo nombre en otra ruta; **no se puede afirmar que se movieran**.

## Interpretación (lo que se sabe y lo que no)
- **Se sabe:** las 217 + 5 son copias exactas (mismo SHA-256) de ficheros registrados; el importador no registra la segunda copia de algo que ya conoce. No lo causó la actualización del 22 de octubre: la base tiene las mismas 1339 filas de antes.
- **Se sabe:** 29 contenidos del disco **no están en ZascArr**, y no por ser copias sino por estar en un contenedor que ZascArr no lee o sin extensión (la decisión se toma por la extensión).
- **No se sabe:** si esos 29 contienen imágenes de tebeo (lo normal en un `.rar` de manga o en una novela gráfica, pero no se abrieron); si ZascArr puede leerlos si se renombraran (un RAR con extensión `.cbr` se lee igual; un `.tar` o un `.cbz.rar`, no está comprobado).
- Dos grupos de copias son carpetas enteras duplicadas (Superman Zinco y Carlos Giménez); que un archivo de `Superman` o de `Patrulla-X` sea idéntico a uno de `Flash` o `Inferno` sugiere ejemplares **mal ubicados** (no verificado a mano).
- Lecturas anteriores corregidas: «unos 200 tebeos sin registrar» **no** eran tebeos que faltaran (eran copias), y «los 12 sin extensión» **no** eran basura (7 son contenido nuevo y 5 copias).

## Decisiones propuestas (NO ejecutadas; del PO)
1. **29 contenidos nuevos (21 *One Piece* `.rar`, 7 novelas gráficas sin extensión, 1 `.tar`):** decidir si ZascArr debe leerlos (historia nueva, con benchmark §13: cómo lo hacen Kapowarr/Mylar con `.rar`, `.7z` y archivos sin extensión, y qué cambia en el importador y el etiquetador) o si el PO los convierte o renombra **fuera de ZascArr**. Hasta entonces, no se toca nada.
2. **222 copias exactas (8,1 GB las 217 de `.cbr`/`.cbz`):** no adoptarlas (duplicaría la colección). Qué hacer con ellas es la historia de duplicados **#264** (apartar una copia idéntica, con vista previa y deshacer), cuyo spike de medición es **#263**: estas cifras son su primera muestra real.
3. **14 filas `is_missing`:** sin huella y sin pistas de movimiento; dejarlas como están (ya constan como no encontradas) o decidir una limpieza aparte. No es urgente.
4. **Pantalla:** que «Duplicados» enseñe estas copias con la ruta real (#294).

## Cómo repetirlo
Los comandos están en la cabecera del script. Para los contenedores sin extensión y los `.rar`/`.tar`: `file -b` por fichero y el cálculo de huellas de esos grupos (el script los compara también por contenido a partir de la PR #302). Reproducible; el script no abre la base ni el disco.
