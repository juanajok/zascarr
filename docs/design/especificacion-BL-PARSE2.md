# Especificación BL-PARSE2 — desempatar dos ediciones por el número que existe (F1)

> **Estado:** **aprobada por el PO el 2026-11-26.**
> **ID provisional:** `BL-PARSE2`, sin tarjeta todavía.
> **Origen:** [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md), familia F1, medida otra vez
> con BL-PARSE1 desplegado (`d1062090`).
> **Código de referencia:** `main` en `58197c04`.

## 1. Problema

El matcher se abstiene con «empate ambiguo» en **208** archivos (206 con vínculo). Salen de 5 grupos:

| Empate | Archivos | Las dos series del catálogo |
|---|---:|---|
| `SUPERMAN` / `SUPERMAN EL HOMBRE DE ACERO` | 145 | Zinco 1987, 136 grapas, `sort_title = SUPERMAN` / novela gráfica de alta manual, un único número **sin número** |
| `ANIMAL MAN` / `Animal Man` | 32 | Zinco 1989 vol. 2, grapas 1–26 / DC 2011, grapas `0, 2a, 2b, 2c` |
| `Monstress` / `Monstress` | 23 | grapas 2015, 1–23 / TPB 2016, 1–7 |
| `El Batman Que Rie` ×2 | 7 | grapas 1–7 / novela gráfica sin número |
| `Catwoman Vol. 2/4/5` | 1 | tres volúmenes con números distintos |

**El embudo de la mañana se equivocaba al llamarlas «series duplicadas»:** ninguna lo es. Son
**ediciones distintas con el mismo título**, y para el coleccionista cada edición es una serie (ADR 0020,
glosario §14). No hay nada que fusionar.

Comportamiento actual (`SeriesMatcher.decide`): si hay varias series empatadas, solo desempata
`_desempatar_por_carpeta`, que exige que la carpeta sea el título de la serie («Animal Man - Saga de Grant
Morrison (1988)» no lo es) y solo reconoce un año suelto `(1987)`, no un rango `(1987-96)`. En los 208,
no decide en ninguno.

Lo que el matcher no mira: **cuál de las series empatadas tiene el número del archivo**. En 199 de los 208,
solo una lo tiene.

## 2. Alcance

- Dentro: un desempate nuevo en `decide`, después del de la carpeta, y su guarda de año.
- Fuera: cambiar el umbral, el fuzzy, el alias, `find_series` o el desempate por carpeta existente; crear o
  fusionar series; datos del catálogo. F2 (la carpeta como señal de serie), F5 y los hallazgos del análisis
  externo (volumen del nombre que no llega al matcher, candidatos con «Vol N» ocultos por un exacto) van en
  historias propias.

## 3. Reglas

### R1. Desempate por número existente

Si tras `_desempatar_por_carpeta` siguen empatadas varias series, se busca en cada una el número efectivo
del archivo (el mismo que usaría `_resolve`, con la conversión `E{N}` de BL-PARSE1 R4 si es un especial),
con la semántica de `find_issue`: `ltrim` de ceros, sin filas de número vacío. **Si exactamente una** de las
empatadas lo tiene, se elige esa y se sigue por `_resolve` como hoy, que conserva todas sus guardas (B15
formato, BL-INF11 colecciones). Si ninguna o más de una lo tiene, se queda como hoy: `unsorted`,
«empate ambiguo».

Una sola consulta para todas las empatadas, no una por serie.

### R2. Guarda: el año de la carpeta no puede contradecir la elegida

Antes de aceptar la serie de R1: si la carpeta del archivo afirma un año, `(AAAA)` o un rango
`(AAAA-AA)` / `(AAAA-AAAA)` (se toma el primero), y la serie elegida tiene `start_year` conocido, la
diferencia tiene que ser **≤ 1**. Si no, R1 no decide (`unsorted`, empate ambiguo, con la nota de R3).

Desconocer el año (en la carpeta o en la serie) **no** es una contradicción.

**Por qué:** el catálogo puede no tener el número en la edición buena. Caso medido: 3 archivos de la
carpeta «Saga de Jeff Lemire (2012)», hoy vinculados a la edición de Zinco de 1989. La DC de 2011 no tiene
esos números en el catálogo, así que R1 sola los mandaría a Zinco. La guarda los deja en revisión.

### R3. Notas visibles

- Al desempatar: `desempatado por el número: «{serie}» es la única con el número «{N}»`.
- Si la guarda frena: `empate ambiguo: [...]; solo «{serie}» tiene el número «{N}», pero la carpeta dice
  {AAAA} y la serie empieza en {AAAA}`.

## 4. Considerado y descartado

- **Fusionar o renombrar series:** no son duplicados (§1).
- **Desempatar por formato** (los archivos sin marcador como grapas): B15 fija que «sin marcador» es
  «sin evidencia de formato». Se quedan en revisión los 7 Monstress 1–7 (grapa y TPB comparten número).
- **Guarda por volumen de la carpeta:** ninguna de las series empatadas tiene `volume` útil salvo Zinco
  Animal Man; no se mide nada que gane o evite. Queda para F2.
- **Desempatar por número sin guarda:** gana 3 enlaces más, que son los 3 de Lemire de §3 R2.

## 5. Medición (prototipo sobre el embudo del 2026-11-26 y los números del catálogo)

| | Archivos |
|---|---:|
| Empates hoy | 208 |
| R1 + R2 eligen y coinciden con el vínculo | **196** |
| R1 + R2 eligen en contra del vínculo | **0** |
| R1 elige y R2 frena (Lemire) | 3 |
| R1 no decide (Monstress 1–7 en dos ediciones) | 7 |
| R1 no decide (ninguna tiene el número) | 1 |
| R1 + R2 eligen en un archivo sin vínculo | 1 |

**A revisar por el PO, fuera de esta historia:** los 3 archivos de la carpeta de Lemire enlazados a la
edición de Zinco, y 8 de la carpeta `Superman Vol. 3` enlazados a la edición de Zinco de 1987-96.

## 6. Criterios de aceptación y pruebas

| CA | Criterio | Prueba |
|---|---|---|
| C1 | Dos empatadas, solo una con el número: elige esa, `direct`, con la nota de R3 | `tests/test_naming_core.py::test_empate_lo_desempata_la_unica_serie_con_el_numero` |
| C2 | Las dos tienen el número: `unsorted`, «empate ambiguo», como hoy | `…::test_empate_con_el_numero_en_las_dos_sigue_ambiguo` |
| C3 | Ninguna lo tiene: `unsorted`, como hoy | `…::test_empate_sin_el_numero_en_ninguna_sigue_ambiguo` |
| C4 | Carpeta con año a más de 1 del de la elegida: no decide, nota de R3 | `…::test_empate_por_numero_lo_frena_el_anio_de_la_carpeta` |
| C5 | Rango `(1987-96)` cuenta como 1987; año desconocido no frena | `…::test_empate_por_numero_rango_de_anios_y_anio_desconocido` (parametrizada) |
| C6 | Si `_desempatar_por_carpeta` ya decide, R1 no se consulta | `…::test_empate_la_carpeta_decide_antes_que_el_numero` |
| C7 | Especial: R1 busca `E{N}`, nunca `N` | `tests/test_matcher_sql_pg.py::test_empate_de_especial_busca_su_numero_e` (pg) |
| C8 | Con Postgres real: una sola consulta, semántica de `ltrim` y sin números vacíos (la novela gráfica sin número no cuenta) | `tests/test_matcher_sql_pg.py::test_desempate_por_numero_semantica_real` (pg) |
| C9 | Las guardas de `_resolve` siguen actuando tras R1 (formato B15) | `tests/test_matcher_sql_pg.py::test_desempate_por_numero_no_salta_la_guarda_de_formato` (pg) |

**Aceptación en datos reales** (tras desplegar, con tu autorización para la tanda en la Pi): repetir el
embudo de solo lectura frente a la foto de BL-PARSE1:
- ≥ 194 coincidencias más con el vínculo (corregido el 2026-11-26 con el PO: el 196 del prototipo de §5
  no simulaba la guarda BL-INF11 de `_resolve`, que R1 conserva a propósito; en el embudo frena 2
  Superman #1 cuyo número ya mezcla colecciones);
- **0** que dejan de coincidir;
- **0** enlaces nuevos a otra serie o a otro número;
- los 3 archivos de Lemire siguen sin enlazar.

## 7. Orden de los commits (SDD + TDD)

1. `spec:` este documento, aprobado.
2. `test:` C1–C9 en rojo, con el motivo de cada rojo en la PR.
3. Implementación mínima de R1–R3 hasta el verde de la suite completa (`--basetemp` en el disco raíz).
4. `refactor:` si hace falta, con todo en verde.
5. Embudo en la Pi y resultado en la PR.
