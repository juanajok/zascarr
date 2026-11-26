# Especificación BL-PARSE3 — la carpeta sugiere la serie en «Por revisar» (F2)

> **Estado:** **propuesta, pendiente de aprobación del PO.**
> **ID provisional:** `BL-PARSE3`, sin tarjeta todavía.
> **Origen:** [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md), familia F2, medida otra vez con
> BL-PARSE2 desplegado (`eb9d8c4a`), y el experimento Fellegi-Sunter del mismo día (§6).
> **Relación:** B14 está hecha (el asistente que vincula **desde** la carpeta, a mano). Esto no lo cambia:
> añade una sugerencia de un clic en la tarjeta de «Por revisar» (B12), con el mismo formulario.
> **Código de referencia:** `main` en `8b300539`.

## 1. Problema

Cuando una carpeta ya tiene sus archivos en una serie, el que queda suelto en «Por revisar» no lo
aprovecha: la sugerencia de la tarjeta (B12) sale **solo** del candidato que guardó el matcher al
importar, con su porcentaje de parecido del título. Si el nombre no da un título que case (créditos
pegados, título traducido, número sin serie) no hay sugerencia, aunque los vecinos de carpeta digan cuál es.

## 2. Alcance

- Dentro: calcular, al pintar «Por revisar», una **sugerencia por la carpeta** para cada tarjeta, y
  mostrarla en el bloque «¿Es esta serie?» que ya existe, con su motivo.
- Fuera: enlazar solo (nunca); cambiar el matcher, el importer o lo que se guarda en `files.metadata`;
  migraciones; la vista «Pendientes por carpeta» y el asistente de B14; el filtro «solo con sugerencia» (D1).

## 3. Reglas

### R1. Hermanos unánimes

Para un pendiente en la carpeta `C` (la ruta de su archivo sin el nombre, completa, no solo el último
tramo), sus **hermanos** son los demás archivos de `C` con número asignado (`issue_id` no nulo) y no
ausentes (`NOT is_missing`). Hay sugerencia si hay **al menos 3** hermanos y **todos** están en la misma
serie `S`. Cuentan todos los vínculos, sean manuales o no (§6 explica por qué no solo los manuales).

### R2. Guarda de anual

No hay sugerencia si el nombre es de un anual (`parse_comic_filename(...).is_annual`) y `S` no lo es
(`es_titulo_de_anual(S.title)`), ni al revés. Es la misma regla que ya aplica el matcher.

### R3. Qué enseña la tarjeta

- Si hay sugerencia por la carpeta, **sustituye** a la del matcher en el bloque «¿Es esta serie?»: misma
  serie en el campo oculto, mismo número precargado desde el nombre, mismos botones.
- En lugar del chip de porcentaje, el chip dice `Por la carpeta` (nivel `ok`), y debajo del título de la
  serie una línea: `Otros {n} archivos de esta carpeta ya están en esta serie.` (`n` = hermanos de R1).
- Si no hay sugerencia por la carpeta, la tarjeta queda **exactamente** como hoy.

### R4. Coste

Una sola consulta por página de «Por revisar» (y una por tarjeta cuando se vuelve a pintar una sola, tras
un error de asignación): agrupa por carpeta y serie los archivos con número de las carpetas de esa página.
Sin estado nuevo: lo que se ve sale siempre de los vínculos de ese momento, así que asignar tres archivos de
una carpeta hace que el cuarto ya salga sugerido.

### R5. Dónde vive

La regla está en un servicio (`services/sugerencia_carpeta.py`), que consume `web/pendientes.py` al montar
las tarjetas (CLAUDE.md §3.1.1). La plantilla solo pinta lo que recibe.

## 4. Decisión para el PO

- **D1. Filtro «solo con sugerencia».** Hoy cuenta solo los pendientes con candidato del matcher guardado.
  Propuesta: **dejarlo como está** en esta historia (los 27 pendientes que solo tienen sugerencia por la
  carpeta no aparecerán al filtrar) y abrir otra si molesta. Meterlo aquí obliga a llevar R1 a la consulta
  paginada de `ReviewService`, que es más riesgo que la propia historia.

## 5. Considerado y descartado

- **Contar solo los vínculos manuales:** medido peor (93 % frente a 99,9 %, §6).
- **Mayoría ≥ 80 % en vez de unanimidad:** 97,9 % de acierto; la unanimidad es la que deja fuera la
  carpeta de Green Lantern Corps cuyo vínculo histórico está mal.
- **Usar la carpeta como peso en el matcher o para enlazar solo:** circular (§6).
- **Guardar la sugerencia al importar:** se quedaría vieja al asignar vecinos.

## 6. Medición (embudo del 2026-11-26 tras BL-PARSE2, en local)

Contra los 4.501 archivos con vínculo, dejando fuera el propio archivo:

| Variante | Sugiere | Acierta |
|---|---:|---:|
| Todos los vínculos, ≥ 3, unánime, guarda de anual (**R1 + R2**) | 2.713 | **99,89 %** (3 fallos) |
| La misma, sin guarda de anual | 2.721 | 99,60 % (11 fallos, 8 anuales) |
| Solo vínculos manuales, ≥ 3, unánime | 1.020 | 93,14 % |

Los manuales salen peor porque se concentran en carpetas de eventos (Flashpoint, Batman R.I.P.), donde unos
archivos se asignaron a la serie del evento y el resto son tie-ins de la suya. Las 22 grapas de Green
Lantern Corps mal vinculadas **no** reciben sugerencia: su carpeta no es unánime. Los 3 fallos que quedan:
dos ediciones con el mismo título (`El Batman Que Rie`), una subserie (`Lazarus: X+66`) y un anual.

En el experimento Fellegi-Sunter (señales de la Pi, pesos calibrados con las 1.453 asignaciones manuales),
la carpeta usada como peso **daba la razón** a esas 22 grapas contaminadas frente al matcher: por eso solo
sugiere.

**Efecto hoy**, sobre los 595 archivos sin vínculo:

| | Archivos |
|---|---:|
| Sugerencia por la carpeta nueva (hoy sin sugerencia) | 27 |
| Igual que la del matcher (cambia el motivo) | 14 |
| Distinta de la del matcher | 1 |
| Sin sugerencia: menos de 3 hermanos con número | 372 |
| Sin sugerencia: hermanos no unánimes | 177 |
| Sin sugerencia: guarda de anual | 4 |

Donde la carpeta y el matcher discrepan, en los vinculados del embudo la carpeta acierta en 7 de 8.

## 7. Criterios de aceptación y pruebas

| CA | Criterio | Prueba |
|---|---|---|
| C1 | 3 hermanos con número, todos en `S`: sugiere `S` con `n = 3` | `tests/test_sugerencia_carpeta.py::test_tres_hermanos_unanimes_sugieren_su_serie` |
| C2 | 2 hermanos: no sugiere | `…::test_menos_de_tres_hermanos_no_sugiere` |
| C3 | Hermanos en dos series: no sugiere | `…::test_hermanos_no_unanimes_no_sugiere` |
| C4 | Anual en carpeta de serie no anual, y al revés: no sugiere | `…::test_la_guarda_de_anual_frena` (parametrizada) |
| C5 | Una página entera: una sola consulta | `…::test_una_consulta_por_pagina` |
| C6 | Con Postgres real: la carpeta es la ruta completa (dos `Vol 1` en series distintas no se mezclan), los ausentes y los pendientes no cuentan | `tests/test_sugerencia_carpeta_pg.py::test_hermanos_semantica_real` (pg) |
| C7 | La tarjeta con sugerencia por la carpeta: chip `Por la carpeta`, la línea de R3 y la serie en el campo oculto | `tests/test_pendientes_tarjeta.py::test_tarjeta_con_sugerencia_por_la_carpeta` |
| C8 | Sin sugerencia por la carpeta, la tarjeta es idéntica a la de hoy | `tests/test_pendientes_tarjeta.py::test_tarjeta_sin_sugerencia_por_la_carpeta_no_cambia` |
| C9 | La tarjeta que se vuelve a pintar sola (tras un error) también la lleva | `tests/test_pendientes_tarjeta.py::test_tarjeta_repintada_conserva_la_sugerencia_por_la_carpeta` |

**Aceptación en datos reales** (tras desplegar, con tu autorización para la tanda en la Pi): un script de
solo lectura que llama al servicio sobre los pendientes reales y cuenta:
- ≥ 40 pendientes con sugerencia por la carpeta (hoy, 42);
- ninguno que sea anual con serie no anual o al revés;

y una revisión tuya en «Por revisar» de una muestra de 10, en el navegador, con el resultado en la tarjeta.
No hay verdad de referencia para estos archivos: por eso la última palabra es tuya.

## 8. Orden de los commits (SDD + TDD)

1. `spec:` este documento, aprobado.
2. `test:` C1–C9 en rojo, con el motivo de cada rojo en la PR.
3. Implementación mínima de R1–R5 hasta el verde de la suite completa (`--basetemp` en el disco raíz).
4. `refactor:` si hace falta, con todo en verde.
5. Comprobación en el navegador de la tarjeta (con y sin sugerencia) y tanda en la Pi.
