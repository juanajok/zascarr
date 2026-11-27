# Especificación BL-PARSE4 — el título del tomo no se pega a la serie (F5)

> **Estado:** **aprobada por el PO el 2026-11-27**, con D1 fuera (el texto tras `Vol NN` sin guion no se toca).
> **ID:** `BL-PARSE4`, tarjeta [#1339](https://github.com/juanajok/zascarr/issues/1339).
> **Origen:** [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md), familia F5 («el parser mete
> créditos y subtítulos en la serie»), medida aquí por primera vez.
> **Código de referencia:** `main` en `74429ec6`.
> **Revisión (2026-11-27):** R1 redactada de nuevo tras la revisión: la regla se ancla al número de tomo
> o recopilación, no al primer guion; se añade la regresión C8 y la aceptación compara archivo por
> archivo.
> **Qué no es:** esto corrige el parser de tomos y recopilaciones. **No** arregla los vínculos erróneos
> de la biblioteca (Green Lantern Corps, Animal Man, Superman, Batman Vol. 2…): es otro fallo, con su
> propia especificación («Vínculos dudosos»).

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

- Dentro: la serie alternativa y la serie que sale de `parse_comic_filename` cuando el número sale de
  un marcador de tomo o recopilación y le sigue un ` - `.
- Fuera: el matcher, el importer y la BD; las palabras de recopilación que el parser deja a propósito en
  el título (`Serie Integral`); el texto que sigue a `Vol NN` sin guion (D1); `INT1` y otras
  abreviaturas.

## 3. Reglas

### R1. El título o la autoría detrás de un tomo no entra en la serie

Si el parser ha sacado el número de un **marcador de tomo o recopilación** (`Tomo N`, `Vol N`/`Vol.N`,
`Integral N`, `Omnigold N`) y **detrás de ese marcador** viene un separador ` - ` (la misma definición de
hoy: espacio delante, espacio detrás opcional), lo que sigue a ese separador es el título del tomo o su
autoría:

- se conserva el título de serie que el parser ya extrajo de lo que hay **delante** del marcador, con
  sus propios guiones si los tiene (`Serie - Subserie TOMO 08 - Título` → `Serie Subserie`);
- no se genera ninguna alternativa que incorpore ese texto: la alternativa, si queda, se forma solo con
  lo de delante de ese separador;
- `subtitulo` no cambia;
- **no cambia ninguna señal de identidad**: número, volumen (`Vol. 2` sigue siendo el volumen 2 que el
  matcher usa para separar `Vol. 1` de `Vol. 2`), formato de edición, año ni las marcas de anual,
  especial o pack. Suprimir un subtítulo no borra evidencia de identidad.

La clave es **suprimir la alternativa incorrecta**, no recortar el título por el primer guion.

### R2. Lo demás no cambia

Un número que no sale de un marcador de tomo o recopilación (`Serie - Línea 01`, un prefijo de orden
como `00 - Evento - Prólogo #0`) no activa R1: la serie, la alternativa y la carpeta funcionan como hoy.
Lo mismo si no hay separador detrás del marcador.

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
- **Cortar por el primer guion** (primera redacción de R1): da los mismos 19 en esta foto, pero no ve
  `Serie - Subserie TOMO 08 - Título` (el número va detrás del primer guion) y, sin ancla en el
  marcador, podía crecer a «cualquier número antes del primer guion».
- **Quitar `Integral` del título:** el parser la deja a propósito (comentario de
  `EDITION_NUMBER_PATTERN`); cambiarlo es otra historia y ninguna serie del catálogo la necesita hoy.

## 6. Medición (foto del embudo del 2026-11-26 tras BL-PARSE2, en local)

El parser de `main` se reprodujo en local sobre los 5.096 nombres de la foto, con su carpeta, su
contexto y la cohorte calculada por carpeta: da la **misma serie que el embudo en los 5.096**.

Adopciones de una alternativa con subtítulo (la serie final es «serie + subtítulo»):

| | Número de tomo o recopilación con ` - ` detrás (**R1**) | Resto |
|---|---:|---:|
| Vinculados, la serie adoptada coincide con el vínculo | **0** | 307 |
| Vinculados, no coincide | **7** | 57 |
| Sin vínculo | **12** | 74 |

Es decir, R1 cambia **19** archivos y en ninguno de los 307 aciertos de hoy se aplica. Comprobado
volviendo a parsear cada nombre sin lo que sigue al separador de detrás del marcador: cambian la serie
o la alternativa de esos 19 y de ningún otro de los 5.096, y en **ninguno** cambian el número, el
volumen, el formato ni las marcas de anual, especial o pack. La foto y la lista de los 19 identificadores
son la referencia de la aceptación: se guardan **fuera del repo**, en una carpeta privada y persistente
del operador (no en un directorio temporal), junto con los scripts de medición, para poder repetir la
comparación archivo por archivo.

- Los **7** vinculados son una misma serie en tomos (`Serie..Tomo.N.-.Autora.&.Autor`). Con R1 la serie
  del parser es la del vínculo. **Mejoran la coincidencia del diagnóstico; no son 7 reparaciones**: el
  vínculo ya estaba bien.
- De los **12** sin vínculo, **2** son tomos cuya serie tiene ficha en el catálogo: candidatos a enlace
  (la carpeta de BL-PARSE3 ya los sugiere). Los otros **10** no tienen ficha (F6): **deben quedar sin
  enlazar**; R1 solo les deja un título limpio para cuando se cree la serie.
- Los 57 vinculados que no coinciden, con el número detrás, son sobre todo tie-ins de eventos asignados
  a la serie del evento (orden de lectura, §2.1 del embudo). No son de F5 y R1 no los toca.

**Efecto esperado:** hasta **+7** coincidencias del diagnóstico con el vínculo y hasta **2** candidatos
a enlace entre los pendientes. Que esos 2 se enlacen depende de que el número esté en el catálogo y de
los empates de F1: se cuenta en la Pi.

## 7. Criterios de aceptación y pruebas

Los nombres de las pruebas son sintéticos, con la misma forma que los reales (sin nombres de la
biblioteca).

| CA | Criterio | Prueba |
|---|---|---|
| C1 | `Serie..Tomo.2.-.Autora.&.Autor.[grupo].cbr` en la carpeta `Serie (2015)` → serie `Serie`, número `2`, sin alternativa, subtítulo `Autora & Autor` | `tests/test_naming_core.py::test_titulo_tras_el_tomo_no_entra_en_la_serie` (parametrizada, C1–C4) |
| C2 | `Serie TOMO 08 - Título del tomo (x) [Digital].cbr` en `Serie (2004)` → `Serie`, `8` | ídem |
| C3 | `Serie Vol.1 - Autora Nombre [x].cbr` en `Serie` → `Serie`, `1`, **volumen `1`** (se conserva) | ídem |
| C4 | `Serie. Integral 01 - Autor & Autor [x].cbr` en `Serie` → `Serie Integral`, `1` (la palabra se queda, como hoy) | ídem |
| C5 | `Forever Evil - Rogues Rebellion 01.cbr` en `Forever Evil Vol. 1` → `Forever Evil Rogues Rebellion` (sin cambio) | `…::test_numero_sin_marcador_de_tomo_conserva_la_linea` (parametrizada, C5–C6) |
| C6 | `Batman - Odyssey 03.cbr` en `Batman - Odyssey` → `Batman Odyssey` (sin cambio) | ídem |
| C7 | `00 - Evento - Prólogo #0.cbz` en `Evento` → como hoy (el prefijo de orden no activa R1) | `…::test_prefijo_de_orden_no_activa_la_regla` |
| C8 | `Serie - Subserie TOMO 08 - Título del tomo.cbr` en `Serie` → serie `Serie Subserie`, número `8`, sin alternativa con `Título del tomo` (hoy da `Serie Subserie Título del tomo`): el primer guion sí es del nombre de la serie | `…::test_guion_de_la_serie_delante_del_tomo_se_conserva` |
| C9 | `Batman Vol. 2 #01 - Título del número.cbr`, en `Batman Vol. 2` y en `Batman` → serie `Batman`, número `1`, **volumen `2`**, como hoy: el número no sale del marcador, R1 no se activa y la señal `Vol. 2` se conserva | `…::test_volumen_de_la_serie_se_conserva` |

**Aceptación en datos reales** (tras desplegar, con tu autorización para la tanda en la Pi): volver a
ejecutar el embudo **en solo lectura, sin reasignar nada**, y compararlo **archivo por archivo** con la
misma foto tras BL-PARSE2 (la guardada fuera del repo):

- la serie o la alternativa del parser cambia en **los mismos 19 archivos** de §6 (por identificador, no
  solo el mismo total) y en ninguno más;
- en ningún archivo cambian el número, el volumen, el formato ni las marcas que da el parser;
- **ningún cambio de destino** (serie o número que decide el matcher) en los 307 aciertos ni en ningún
  otro archivo fuera de los 19;
- **ninguna propuesta a una serie incorrecta**: entre los 19, ningún candidato ni enlace a una serie
  distinta de la del vínculo (los 7) o de la ficha existente (los 2); los 10 sin ficha, sin enlazar;
- se anotan, por separado, las coincidencias del diagnóstico (esperadas: hasta +7) y los candidatos a
  enlace (esperados: hasta 2).

## 8. Orden de los commits (SDD + TDD)

1. `spec:` este documento, aprobado.
2. `test:` C1–C9: en rojo C1–C4 y C8; en verde C5–C7 y C9, que fijan lo que no cambia. El motivo del rojo,
   en la PR.
3. Implementación mínima de R1 en `utils/naming.py` hasta el verde de la suite completa (`--basetemp`
   en el disco raíz).
4. `refactor:` si hace falta, con todo en verde.
5. Tanda en la Pi.
