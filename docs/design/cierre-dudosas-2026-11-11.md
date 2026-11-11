# Cierre de las cuatro etiquetas dudosas (2026-11-11)

> Evidencia de archivo y fuentes bibliográficas. No se ha modificado la
> biblioteca. Los cuatro casos se cierran en la muestra de 200.

## 1. Método

Para cada archivo:

1. Se listó el contenido del CBR con `7z` (páginas y nombres internos).
2. Se extrajo la portada o primera página cuando el método de compresión lo
   permitió.
3. Se buscó la ficha bibliográfica de la edición.
4. Se comparó con **Zascarr**, **ComicTagger** y **Kapowarr**.
5. Mylar3, Kavita, Komga y Suwayomi se revisaron por código (no ejecutados).

## 2. Decisión por caso

### Flash v2 158 «2.0»

- Evidencia: 23 páginas, escaneo `Scan-*`, sin ComicInfo; el nombre separa
  claramente `Flash v2 158` y una marca `2.0` posterior.
- Nuestro parser: `Flash` #158.
- **ComicTagger**: serie `191.- Flash`, issue `2`, volumen `2`.
- **Kapowarr**: serie `Flash`, issue `158.0`, volumen `2`.
- Decisión: **Flash #158, grapa**. `2.0` es marca de versión/scan, no número.
- Confianza: alta.

### Crossover 07 - Dinastía de X 04

- Evidencia: la portada dice **DINASTÍA DE X 4 de 6** (Panini #94); dentro del
  CBR la carpeta es `Dinastía de X - 4(AluciCRG)` y las páginas `dx4001.jpg`…
- Nuestro parser tras la regla: `Dinastia de X` #4.
- **ComicTagger**: serie `Crossover 07 - Dinastia de X`, issue `4`.
- **Kapowarr**: serie `Crossover 07 Dinastia de X`, issue `4.0`.
- Decisión: **Dinastía de X #4, grapa**. `Crossover 07` es orden de lectura.
- Confianza: alta.

### GunSmith Cats [P2N2]

- Evidencia: 30 páginas; el ADR-0003 documenta `[P1N1]…[P3N9]` como
  **parte/número**; las páginas internas son `GSC_P2N2_01…31`.
- Nuestro parser: `GunSmith Cats`, issue `2`, volumen `2`.
- **ComicTagger**: serie completa con corchetes, sin número.
- **Kapowarr**: `GunSmith Cats`, sin número, `special_version=tpb`.
- Decisión: **GunSmith Cats #2, capítulo**. No es un tomo 2.
- Confianza: media-alta; el número 2 es el de la parte/número, no un tomo.

### Los detectives muertos

- Evidencia: CBR de **126 páginas**; Tebeosfera describe la edición ECC 2024
  como **libro cartoné de 176 pp, 1 número**, dentro de Universo Sandman.
- Nuestro parser: serie `Los detectives muertos`, sin número.
- **ComicTagger**: serie correcta, sin número.
- **Kapowarr**: serie correcta, sin número, `special_version=tpb`.
- Decisión: **tomo/recopilatorio**, sin número.
- Confianza: alta.

## 3. Benchmark de los cuatro casos

| Caso | Zascarr | ComicTagger `fa11a34` | Kapowarr `c191dda` | Otras referencias |
|---|---|---|---|---|
| Flash 158 2.0 | Flash #158 | `191.- Flash` #2 | Flash #158 | Kavita/Komga/Mylar no aportan versión; Suwayomi solo capítulo |
| Crossover 07 | Dinastía de X #4 | Crossover 07… #4 | Crossover 07… #4 | Kavita/Komga usan carpeta; no resuelven el prefijo |
| GunSmith P2N2 | GunSmith Cats #2 cap. | sin número | sin número, TPB | Mylar/Kavita leerían sin número; Komga libro |
| Los detectives | tomo sin número | sin número | sin número, TPB | Komga lo trataría como libro de la carpeta |

Ninguno de los comparadores resuelve los cuatro: **ComicTagger y Kapowarr
aciertan el número de Flash, pero fallan series/prefijos**; ambos ignoran
`[P2N2]` y no distinguen tomo de capítulo. La decisión final se apoya en
contenido y ficha bibliográfica, no en el parser.

## 4. Qué se adopta

- Regla de **prefijo de orden de lectura** `Crossover NN -` (implementada).
- Regla de **marca de versión** después del issue (`2.0` no es número).
- `[PpNn]` como parte/número, no como tomo (ya existente; se mantiene).
- Sin número + muchas páginas + ficha de edición → **tomo**; no se decide solo
  por el nombre.
- No se copia código de los proyectos comparados.

## 5. Resultado

Las cuatro filas pasan de `dudosa` a etiquetas cerradas. La muestra queda con
**200 filas**, sin exclusiones. Detalle en
[`muestreo-biblioteca-200-2026-11-11.md`](muestreo-biblioteca-200-2026-11-11.md).
