# Especificación BL-PARSE4 — el título del tomo no se pega a la serie (F5)

> **Estado:** **borrador para el PO** (2026-11-27). No se programa hasta que esté aprobada.
> **ID provisional:** `BL-PARSE4`, sin tarjeta todavía.
> **Origen:** [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md), familia F5 («el parser mete
> créditos y subtítulos en la serie»), medida aquí por primera vez.
> **Código de referencia:** `main` en `74429ec6`.

## 1. Problema

Cuando el número de un archivo sale de un marcador de tomo o de recopilación (`Tomo 08`, `Vol.1`,
`Integral 01`) y detrás viene ` - ` con el título del tomo o los autores, la serie se queda con ese texto
pegado: `Serie Tomo 08 - Título del tomo` se lee como la serie «Serie Título del tomo». El matcher no
encuentra esa serie (no existe) y el archivo se queda en «Por revisar» sin sugerencia, aunque la serie
buena esté en el catálogo.

**Mecanismo.** El parser corta el subtítulo bien: `Serie` queda como serie y el texto de detrás del
guion queda como subtítulo. Pero guarda «serie + subtítulo» como serie alternativa, y
`_serie_desde_carpeta` la **adopta** cuando la carpeta es la serie corta: es la regla que da bien
`Forever Evil: Rogues Rebellion` en la carpeta `Forever Evil`. En esos casos, sin embargo, el número va
**detrás** del guion (`Forever Evil - Rogues Rebellion 01`) y el guion separa la serie de su línea. En
los de F5 el número va **delante** (`Serie Tomo 08 - Título`) y lo que sigue al guion es el título
del tomo o los créditos.

## 2. Alcance

- Dentro: la serie alternativa y la serie que sale de `parse_comic_filename` cuando el número aparece
  en el nombre antes del primer ` - `.
- Fuera: el matcher, el importer y la BD; las palabras de recopilación que el parser deja a propósito en
  el título (`Serie Integral`); el texto que sigue a `Vol NN` sin guion (D1); `INT1` y otras
  abreviaturas.

## 3. Reglas

### R1. Con el número antes del guion, lo de detrás no forma parte de la serie

Si el número que se queda el parser aparece en el nombre **antes** del primer separador ` - ` (con la
misma definición de separador que hoy: espacio delante, espacio detrás opcional), el texto de detrás es
el título del número o sus créditos:

- `series_alternativa` queda vacía;
- `series` es la parte de delante del guion, como ya es hoy antes de que la carpeta la cambie;
- `subtitulo` no cambia: sigue guardando ese texto.

Un número que solo es un prefijo de orden al principio del nombre (`00 - Evento - Prólogo #0`) **no**
cuenta como «antes del guion»: ahí el primer guion separa ese prefijo y el comportamiento de hoy se
mantiene.

### R2. Lo demás no cambia

Con el número detrás del guion (`Serie - Línea 01`) o sin guion, la serie, la alternativa y la carpeta
funcionan como hoy.

## 4. Decisión para el PO

- **D1. Texto tras `Vol NN` sin guion** (`01 Serie Vol 02 Título del número`). Pega el título igual, y
  cortarlo daría la serie buena en 14 archivos sin vínculo y en 1 con vínculo, sin ningún contraejemplo.
  Pero los 15 son de **una sola carpeta**: es una regla que sale de un caso, no de una familia.
  Propuesta: **dejarla fuera**. Esa carpeta se resuelve de una vez con el asistente por carpeta (B14).

## 5. Considerado y descartado

- **Quitar la regla que adopta la alternativa:** la alternativa acierta en 307 de 371 adopciones sobre
  archivos vinculados (§6). Quitarla perdería `Forever Evil: …`, `Batman: Odyssey` o
  `Injustice: Gods Among Us`.
- **Reconocer los créditos por `&` o `VVAA`:** cubre 15 de los 19 casos y ninguno más. R1 cubre los 19
  con una sola regla de posición y sin una lista de palabras.
- **Quitar `Integral` del título:** el parser la deja a propósito (comentario de
  `EDITION_NUMBER_PATTERN`); cambiarlo es otra historia y ninguna serie del catálogo la necesita hoy.

## 6. Medición (foto del embudo del 2026-11-26 tras BL-PARSE2, en local)

El parser de `main` se reprodujo en local sobre los 5.096 nombres de la foto, con su carpeta, su
contexto y la cohorte calculada por carpeta: da la **misma serie que el embudo en los 5.096**.

Adopciones de una alternativa con subtítulo (la serie final es «serie + subtítulo»):

| | Número antes del guion (**R1**) | Número detrás o prefijo de orden |
|---|---:|---:|
| Vinculados, la serie adoptada coincide con el vínculo | **0** | 307 |
| Vinculados, no coincide | **7** | 57 |
| Sin vínculo | **12** | 74 |

Es decir, R1 cambia **19** archivos y en ninguno de los 307 aciertos de hoy se aplica. Comprobado
aparte: de los 322 archivos con el número antes del guion, solo esos 19 tienen alternativa; en los
otros 303 vaciarla no cambia nada (ya no la tienen).

- Los **7** vinculados son una misma serie en tomos (`Serie..Tomo.N.-.Autora.&.Autor`). Con R1 la serie
  es la del vínculo; el matcher hoy se abstiene (candidato por debajo del umbral).
- De los **12** sin vínculo, 2 son tomos cuya serie está en el catálogo (la carpeta de BL-PARSE3 ya los
  sugiere). Los otros 10 son series que no están en el catálogo (F6): R1 les deja un título limpio para
  cuando se creen, pero no los enlaza.
- Los 57 vinculados que no coinciden, con el número detrás, son sobre todo tie-ins de eventos asignados
  a la serie del evento (orden de lectura, §2.1 del embudo). No son de F5 y R1 no los toca.

**Ganancia esperada:** hasta **+7** coincidencias con el vínculo y hasta 2 enlaces nuevos entre los
pendientes. Si se enlazan depende de que el número esté en el catálogo y de los empates de F1: se
cuenta en la Pi.

## 7. Criterios de aceptación y pruebas

Los nombres de las pruebas son sintéticos, con la misma forma que los reales (sin nombres de la
biblioteca).

| CA | Criterio | Prueba |
|---|---|---|
| C1 | `Serie..Tomo.2.-.Autora.&.Autor.[grupo].cbr` en la carpeta `Serie (2015)` → serie `Serie`, número `2`, sin alternativa, subtítulo `Autora & Autor` | `tests/test_naming_core.py::test_numero_antes_del_guion_no_pega_el_subtitulo` (parametrizada, C1–C4) |
| C2 | `Serie TOMO 08 - Título del tomo (x) [Digital].cbr` en `Serie (2004)` → `Serie`, `8` | ídem |
| C3 | `Serie Vol.1 - Autora Nombre [x].cbr` en `Serie` → `Serie`, `1` | ídem |
| C4 | `Serie. Integral 01 - Autor & Autor [x].cbr` en `Serie` → `Serie Integral`, `1` (la palabra se queda, como hoy) | ídem |
| C5 | `Forever Evil - Rogues Rebellion 01.cbr` en `Forever Evil Vol. 1` → `Forever Evil Rogues Rebellion` (sin cambio) | `…::test_numero_detras_del_guion_conserva_la_linea` (parametrizada, C5–C6) |
| C6 | `Batman - Odyssey 03.cbr` en `Batman - Odyssey` → `Batman Odyssey` (sin cambio) | ídem |
| C7 | `00 - Evento - Prólogo #0.cbz` en `Evento` → como hoy (el prefijo de orden no cuenta) | `…::test_prefijo_de_orden_no_cuenta_como_numero_antes_del_guion` |

**Aceptación en datos reales** (tras desplegar, con tu autorización para la tanda en la Pi): volver a
ejecutar el embudo de solo lectura y compararlo con la foto tras BL-PARSE2:

- la serie del parser cambia en **19** archivos, los de §6, y en ninguno más;
- **0** coincidencias perdidas con el vínculo y **0** enlaces a otra serie;
- las ganancias se cuentan y se anotan (esperadas: hasta +7 y hasta 2 enlaces nuevos).

## 8. Orden de los commits (SDD + TDD)

1. `spec:` este documento, aprobado.
2. `test:` C1–C7 en rojo (C1–C4) y en verde (C5–C7, que fijan lo que no cambia), con el motivo del rojo
   en la PR.
3. Implementación mínima de R1 en `utils/naming.py` hasta el verde de la suite completa (`--basetemp`
   en el disco raíz).
4. `refactor:` si hace falta, con todo en verde.
5. Tanda en la Pi.
