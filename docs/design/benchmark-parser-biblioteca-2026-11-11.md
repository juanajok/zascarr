# Parser y matcher contra la biblioteca real (2026-11-11)

> Diagnóstico de solo lectura. No se ha escrito en la biblioteca ni en
> producción. Este documento no incluye rutas ni nombres completos de archivo.

## 1. Por qué hacía falta una medición nueva

El benchmark oficial de 2026-09-26 usó **81 rutas de la carpeta de Descargas**
(62 contenidos únicos). No medía la biblioteca de producción y se hizo con una
muestra pequeña y estratificada por carpetas, no por los patrones que hoy
aparecen en la biblioteca.

La foto usada aquí:

| Dato | Valor |
|---|---:|
| Archivos no ausentes | **5.049** |
| Con Issue | **1.493** |
| Sin Issue | **3.556** |
| Series | **51** |

La diferencia importante no es solo el tamaño: la biblioteca tiene colecciones,
ediciones, tie-ins, autores usados como serie y packs que la muestra antigua
casi no cubría.

## 2. El vínculo catálogo↔archivo no es verdad de referencia

Medir el parser contra `files.issue_id` es tentador, pero el vínculo no siempre
significa “esta es la serie y el número que dice el nombre”. Hay tres ruidos
reales:

- **Colecciones/reading order**: un archivo de una grapa suelta puede estar
  vinculado a una serie que representa un arco o una lectura completa.
- **Autor como serie**: varios tomos de un autor están vinculados a una serie
  que lleva el nombre del autor.
- **Packs**: un rango de números vinculado al primer número del rango.

Por eso el corpus de vínculos vale como **prueba de humo y de consistencia**,
no como *accuracy* del parser. La métrica que decide sigue necesitando
etiquetas manuales.

## 3. Línea base del parser

Sobre los 1.493 archivos vinculados, comparando el título/número del parser
con la serie/Issue actuales:

| Medida | Resultado |
|---|---:|
| Número exacto | 1.435 / 1.493 = **96,1 %** |
| Serie exacta (normalizada) | 742 / 1.493 = **49,7 %** |
| Serie tolerante (sin `Vol N`) | 1.090 / 1.493 = **73,0 %** |
| Ambos tolerantes | 1.078 / 1.493 = **72,2 %** |

Las 81 etiquetas manuales antiguas, recalculadas con el parser actual **sin
cohortes** (el benchmark original las usaba), dan 67/81 de serie, 77/81 de
número y 46/81 de ambos. No es comparable con el 83/86 oficial: aquel incluía
detección de cohortes y una población distinta.

## 4. Línea base del matcher

Se ejecutó `SeriesMatcher.decide()` sobre los 3.556 archivos sin Issue, con el
parser real y sin escribir nada. Antes de los cambios de esta sesión:

| Estado | Archivos |
|---|---:|
| `unsorted` | 3.324 |
| `direct` | 31 |
| `fuzzy` | 201 |
| Con Issue resuelto | **9** |

La mayoría de los `direct`/`fuzzy` no tienen Issue porque el número no existe
en el catálogo (hueco del enricher), no porque el matcher falle. De los 9
enlaces, uno era un falso positivo: un tie-in de un evento enlazado a la serie
principal.

Después de los cambios:

| Estado | Archivos |
|---|---:|
| `unsorted` | 3.234 |
| `direct` | 121 |
| `fuzzy` | 201 |
| Con Issue resuelto | **11** |

Se recuperaron **3 enlaces reales** (`Batman #25`, `#28`, `#30`) y se bloqueó
**1 falso positivo** de un Issue ya contaminado. **0 enlaces perdidos**. Los 90
`direct` nuevos sin Issue son sobre todo series identificadas correctamente
cuyo número aún no está en el catálogo.

## 5. Fallos corregidos en esta sesión

### 5.1 `Batman #400 Aniversario` perdía el número

`ANIVERSARIO_PATTERN` borraba cualquier “N aniversario” antes de buscar el
número. Con `#`/`nº`/`num.` delante, el número es de la grapa; solo se quita la
palabra. Un “20 aniversario” sin marcador sigue sin ser número.

### 5.2 `Batman` no encontraba `Batman Vol 1`

El parser extrae `Batman`; el catálogo llama a la serie `Batman Vol 1`. La
similitud era 0,54 y el umbral fuzzy 0,60, así que un número existente se
quedaba en Pendientes. No se baja el umbral: se reconoce el sufijo de edición
(`Vol N`, `Volume N`, `vN`, `Tomo N`) como equivalencia exacta. Si hay varias
ediciones, el año/volumen decide; sin evidencia, sigue siendo ambiguo.

### 5.3 Un Issue contaminado aceptaba más copias

La guarda BL-INF11 impedía añadir una colección distinta a un número, pero si el
Issue ya mezclaba varias colecciones, una copia de una de ellas pasaba. Ahora
un Issue con más de una clave de colección no recibe nada más hasta revisarse.

## 6. Fallos que quedan y prioridad

| Familia | Estado | Decisión |
|---|---|---|
| Alias entre idiomas (`100 Balas` / `100 Bullets`) | abierto | no hardcodear; usar alias locales aprendidos y, si se mide, una tabla de alias de catálogo |
| Tie-ins y colecciones | abierto | el matcher ya se abstiene en muchos; falta separar los Issues contaminados existentes |
| Packs/rangos | correcto | el parser no inventa número; el vínculo del catálogo es el que puede estar mal |
| Numeración de evento (`1.000.000`) | abierto | caso raro; necesita contexto de evento |
| Huecos de Issue | catálogo | 90 series identificadas sin Issue; es enricher, no parser |
| Cohortes numéricas | depende del importer | el parser solo no las ve; el pipeline las aplica antes |

## 7. Siguiente benchmark: etiquetas nuevas, no más vínculos

El siguiente paso no debería ser “medir contra más vínculos”, sino construir una
muestra etiquetada de la biblioteca:

1. **200 archivos estratificados** por: vinculado/sin Issue, anual/no anual,
   español/inglés, formato, carpeta y longitud del nombre.
2. Etiqueta manual de `serie_real`, `numero_real`, `tipo` y
   `requiere_contexto`, **antes** de ejecutar el parser.
3. Medir por separado:
   - parser: serie, número, ambos, y **tasa de números inventados**;
   - matcher: `direct`/`fuzzy`/`unsorted`, precisión de los enlaces y
     cobertura de los que tienen Issue.
4. Criterio duro: **errores = 0** en los casos etiquetados; acertar más a costa
   de inventar no cuenta.
5. Añadir cada fallo etiquetado como test de regresión.
6. Comparar con Kapowarr/Mylar sobre el mismo corpus, si se autoriza ejecutar
   sus parsers; no copiar su código.

Con 200 etiquetas se puede distinguir una mejora real de 2-3 puntos de una
fluctuación, cosa que con 81 no se podía.

## 8. Cambios de esta rama

- `naming.py`: número explícito antes de “aniversario”.
- `matcher.py`: equivalencia de sufijo de volumen; guarda de Issue contaminado.
- `matcher.py`: desempate por carpeta cuando hay varios candidatos ya
  empatados por encima del umbral.
- Tests: aniversario, volumen, contaminación y carpeta, incluidos tests PG reales.

## 9. Contexto de carpeta: implementado, sin efecto todavía

Se implementó `_desempatar_por_carpeta`: si el matcher tiene dos o más
candidatos empatados, mira el nombre de la carpeta padre. Solo elige si la
carpeta identifica a **uno** de los candidatos por título base, volumen o año.
Si la carpeta es genérica, contradictoria o no hay candidato, sigue `unsorted`.
**Nunca crea una serie ni mete un candidato que no hubiera pasado el umbral.**

Medición sobre los 3.556 archivos sin Issue:

| | Sin carpeta | Con carpeta |
|---|---:|---:|
| Enlaces con Issue | 11 | 11 |
| `direct` | 121 | 121 |
| `unsorted` | 3.234 | 3.234 |
| Nuevos/perdidos | — | 0 / 0 |

No cambia nada en esta foto porque no hay empates con evidencia de carpeta en
los pendientes actuales; sí queda cubierto para cuando aparezcan duplicados de
volumen/edición. Se probó con tests de volumen, año, carpeta genérica y carpeta
que contradice el volumen.
