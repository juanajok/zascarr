# Embudo del parser y el matcher sobre la biblioteca real (2026-11-26)

> Diagnóstico de **solo lectura**. Se ejecutó en la Pi (código `4b5f9d7b`, idéntico a `main` en
> `naming.py`, `matcher.py` y `cohort.py`) dentro de una transacción `READ ONLY` terminada en
> `ROLLBACK`, sin abrir ningún archivo de la biblioteca. Este documento no incluye rutas ni nombres
> completos de archivo. Sigue al [benchmark del 2026-11-11](benchmark-parser-biblioteca-2026-11-11.md).

## 1. Método

Para cada archivo no ausente se reprodujo el tramo «parsear + decidir» de
`services/importer._triage_and_match`: cohorte calculada por carpeta, `parse_comic_filename` con
carpeta y contexto, formato esperado, anual y serie alternativa, y `SeriesMatcher.decide()`. Sin
ComicInfo: todos los archivos se miden por el nombre (en producción, 68 llegaron por ComicInfo).

| Dato | Valor |
|---|---:|
| Archivos no ausentes | **5.096** |
| Con Issue (vínculo actual) | **4.501** (1.478 por asignación manual, 66 por ComicInfo) |
| Sin Issue | **595** |
| Series / Issues en catálogo | 271 / 4.308 |
| Alias aprendidos activos | 0 |

El vínculo actual **no es verdad de referencia** (§2 del benchmark anterior): sirve para medir
coincidencia y para encontrar discrepancias, que luego hay que mirar una a una.

## 2. Resultado

### 2.1 Archivos con Issue: ¿el matcher de hoy reproduce el vínculo?

| Frente al vínculo | Archivos | % |
|---|---:|---:|
| Mismo Issue | **3.930** | 87,3 |
| Se abstiene (`unsorted` o sin Issue) | 537 | 11,9 |
| Elige **otra serie** | 34 | 0,8 |

Por origen: de los vínculos **manuales** (los más fiables), reproduce 1.205 de 1.453 (82,9 %). Las
partes no son independientes: parte del catálogo se creó a partir de estos mismos archivos.

**Los 34 de «otra serie» no son falsos positivos del matcher** (y ninguno llegaría a enlazar: el
número no existe en la otra serie). Miradas una a una:

- **22: el vínculo guardado es el erróneo.** Grapas de `Green Lantern Corps #N` vinculadas a
  `Green Lantern #N`; hoy el matcher elige `Green Lantern Corps Vol. 3`. Es una contaminación antigua
  en producción que conviene revisar.
- **11: orden de lectura.** Asignadas a mano a la serie del evento (`War of the Green Lanterns`, número
  = posición en la lectura); el matcher propone la serie real. Es el problema de modelo
  serie ↔ lectura, no del matcher. Una de ellas tiene el número de la grapa en lugar de la posición:
  inconsistencia de la asignación manual.
- **1: serie duplicada en el catálogo** (misma serie con distinta caja).

### 2.2 Por qué se abstiene (archivos con y sin Issue)

| Motivo | Con Issue | Sin Issue |
|---|---:|---:|
| Empate ambiguo | 206 | 2 |
| Parser sin número | 139 | 227 |
| Sin candidato por encima del umbral | 90 | 345 |
| Serie sí, número no en catálogo | 57 | 7 |
| Guardas (contaminado, ediciones, otra colección, anual) | 79 | 4 |
| Enlazaría hoy | — | 10 |

## 3. Familias de fallo, de mayor a menor efecto

### F1. Datos del catálogo que fabrican empates (207 archivos)

Los 206 empates salen de **solo 5 grupos**:

- **145**: `SUPERMAN` frente a `SUPERMAN EL HOMBRE DE ACERO`. Las dos dan coincidencia exacta (la
  segunda, probablemente por su `sort_title`). La carpeta dice `SUPERMAN (1987)`, pero el año de la
  carpeta **no llega** a `find_series`: solo el del nombre.
- **62**: tres series **duplicadas** en el catálogo (`Animal Man`, `Monstress`, `El Batman Que Rie`).

No se arregla en el matcher: es consolidar duplicados y revisar `sort_title`. Posible mejora de
código: pasar el año de la carpeta como discriminador (solo desempate).

### F2. La carpeta como señal de serie (B14): 99,6 % de precisión medida

Regla medida: *la carpeta tiene ≥ 3 hermanos vinculados y todos a la misma serie*. Contando cada
archivo sin incluirse a sí mismo, esa serie coincide con la de su vínculo en **2.718 de 2.728**
(99,6 %).

- Entre los vinculados en que el matcher se abstiene, la regla daría serie a **337**, con 2 errores
  (199 empates, 47 bajo umbral, 44 sin número, 28 ediciones, 19 contaminados).
- Entre los 595 sin Issue: **46**.

Riesgo de circularidad (los hermanos los vinculó en parte el mismo matcher), así que el uso
propuesto es **sugerencia o desempate**, nunca crear una serie ni enlazar en silencio. El número
sigue teniendo que salir del nombre.

### F3. La cohorte borra el número real (83 archivos)

`NN Catwoman.cbr`, `NN Dreadstar (Epic Comics)(…)`. En carpetas donde el prefijo varía,
`detectar_ordenes_de_lectura` lo trata como orden de lectura y lo quita; como no queda otro número, el
parser se queda **sin número**. En los 83 casos en que el nombre empieza por el número del vínculo,
la cohorte estaba aplicada en los 83. Regla candidata: no quitar el prefijo si es el único número
del nombre.

### F4. Números inventados (error, no abstención)

- **Número = volumen** (`NN Catwoman Vol 02` → #2): 40 en la biblioteca, 27 con la cohorte aplicada
  (quita el `NN` real y queda el del volumen). Hoy solo 1 llega a enlazar Issue, pero 18 salen
  `direct`. Con el criterio «errores = 0», va antes que cualquier mejora de cobertura.
- **Cuatro cifras en el subtítulo** (`… _69 The Spirit of 2000` → #2000): 3.
- **`Vol2 Especial N`**: el catálogo usa `E1…E8`, y el parser da `N`. Siete casos.

### F5. El parser mete créditos y subtítulos en la serie

Observado en «sin candidato»: nombres con puntos como separador (`Serie..Integral.N.-.Autor.&.Autor`)
y `Serie. Integral NN - Autor & Autor` dejan `Integral` y los autores dentro de la serie; `SERIE TOMO
NN - Subtítulo` pega el subtítulo; `Serie Integral NN - Master Edition` se queda con «Master
Edition». No contado aún con precisión: es la siguiente medición.

### F6. Fuera del parser y el matcher

La mayoría de los 345 sin candidato del grupo sin Issue son series que **no están en el catálogo**
(352 sin hermanos vinculados; 492 con una serie que el parser no ha visto en ningún vínculo). Es
cobertura del catálogo o del enricher.

## 4. Orden propuesto

1. **F4: números inventados**, con pruebas de regresión por patrón. Es seguridad del dato.
2. **F3: cohorte que borra el único número.** Es pequeño, está medido (83) y se comprueba con este
   mismo embudo.
3. **F1: datos.** Consolidar las 3 series duplicadas, revisar `sort_title` de `SUPERMAN EL HOMBRE DE
   ACERO` y revisar los 22 vínculos de `Green Lantern Corps`. Lo decide el PO, no el código.
4. **F2: carpeta como sugerencia o desempate (B14)**, con especificación propia (SDD + TDD) y este
   embudo como prueba de aceptación.
5. **F5: medir y luego arreglar** créditos y subtítulos.

Cada cambio se valida volviendo a ejecutar el embudo: cuenta lo que gana y lo que pierde frente a
esta foto (0 enlaces nuevos a otra serie como condición).

## 5. Seguimiento (mismo día)

F3 y F4 se precisaron con un prototipo sobre esta misma foto y se especificaron en
[`especificacion-BL-PARSE1.md`](especificacion-BL-PARSE1.md):

- Sobre los 278 archivos con cohorte aplicada, en **ninguno** la cohorte acierta donde el parser solo
  falla. Quitarla cuando el prefijo es el único número, y dejar de contar el volumen como «otro
  número», da **+74 coincidencias con el vínculo y 0 pérdidas**. Dreadstar no cambia.
- La regla del año de 4 cifras (`The Spirit of 2000`) se descarta: rompe `AIDP 1946/1947/1948`.
- Los 8 `Superman Vol2 Especial N` son un **falso positivo latente**: solo los frena el empate de F1.
  Con el catálogo arreglado, el matcher buscaría la grapa #N, y el catálogo los guarda como `E1…E8`.
  Por eso F4 tiene que ir antes que F1.
