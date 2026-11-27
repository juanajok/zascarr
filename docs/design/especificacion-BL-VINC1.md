# Especificación BL-VINC1 — Vínculos dudosos

> **Estado:** **borrador**, pendiente de aprobación del PO. No se programa nada hasta entonces (SDD + TDD).
> **Origen:** el [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md) destapó vínculos guardados que
> parecen mal hechos (§2.1: 22 grapas de Green Lantern Corps en Green Lantern) y BL-PARSE2 dejó otros dos
> grupos «a revisar por el PO» ([§5](especificacion-BL-PARSE2.md)). El PO preguntó si un algoritmo
> determinista podría tener esas mismas sospechas: sí, y esta historia las enseña.
> **Revisión externa (2026-11-27):** el PO aportó lotes nuevos y tres criterios. Los lotes se comprobaron en la
> Pi con una tanda de solo lectura (§1, §5) y los criterios están en §3.0.
> **Código de referencia:** `main` en `74429ec6`; la medición se hizo en la Pi con `0bfebfb7`, idéntico a
> `main` en `src/`.
> **Principio:** el sistema informa, la persona decide. Esta revisión **no cambia ningún vínculo**.

## 1. Problema

Un archivo vinculado a un número que no es el suyo no se ve en ninguna parte: no está en «Por revisar»,
cuenta como «tengo» en la serie equivocada y como «me falta» en la buena, y BL-INF11 frena las copias
buenas que llegan después al mismo número. Hoy solo se encuentran a mano o con un embudo de diagnóstico.

Casos conocidos, que la revisión **tiene** que encontrar (128 archivos):

| Caso | Archivos | Qué pasa | Fuente |
|---|---:|---|---|
| Grapas de Green Lantern Corps en Green Lantern (2005, Comic Vine 18216) | 22 | contaminación antigua; la ficha buena (`Green Lantern Corps Vol. 3`, 2011) existe, pero sin números | embudo §2.1 |
| Animal Man de Lemire en la edición de Zinco de 1989 | 3 | la carpeta dice 2012 | BL-PARSE2 R2 |
| Una carpeta que declara el vol. 3 de Superman, en la edición de Zinco de 1987 | 8 | Zinco es el vol. 2 | BL-PARSE2 §5 |
| Una carpeta que declara el vol. 2 de Batman, en `Batman Vol 1` (1939, Comic Vine 796) | 51 | la misma ficha que recibe la carpeta del vol. 1 (359 archivos); el catálogo no tiene la serie de 2011 | revisión externa |
| Los 4 anuales de esa carpeta, en `Batman Annual` (1961) | 4 | vinculados aparte, en la línea anual de 1961 | revisión externa |
| Una carpeta que declara el vol. 5 de Green Lantern, en Green Lantern (2005) | 30 | la misma ficha que recibió las 22 de Green Lantern Corps; sus 2 anuales están bien, en `Green Lantern Annual` (2012, vol. 5) | revisión externa |
| Peacemaker: vol. 1 (6) y vol. 2 (4) en una sola ficha | 10 | sin año ni id de fuente; los #1–#4 tienen un archivo de cada volumen | revisión externa |

Y un caso que **no** debe contar como error por sí solo: **22 archivos** de dos sagas asignados a mano con un
número distinto del de su nombre (12 en `Green Lantern: War of the Green Lanterns` y 10 en `Batman R.I.P.`).
Encajan con un orden de lectura, en el que el número es la posición en la saga (revisión externa).

## 2. Alcance

- **Dentro:**
  - Una búsqueda a demanda, de solo lectura sobre los vínculos, que marca los archivos ya vinculados cuyo
    vínculo contradice alguna de las señales deterministas de §3.
  - Los marcados se agrupan en **lotes** (carpeta y serie) y se ordenan por cuántas señales cumplen.
  - Cada lote indica el **destino posible** si el catálogo lo tiene, o dice que no lo tiene.
  - Un bloque en la pantalla **Duplicados** (`/ui/auditoria`) enseña el resultado. Para cada archivo, lleva
    a la acción que ya existe para deshacer la vinculación (BL-R1b, `web/desvinculacion.py`), que tiene su
    propia vista previa y confirmación.
- **Fuera:**
  - Cambiar, deshacer o crear vínculos desde este bloque, nunca solo y tampoco en lote (la corrección por
    lotes es BL-VINC2, §7).
  - La guarda preventiva del matcher (BL-PARSE4, §7), y tocar el importer o `files.metadata`.
  - Marcar un vínculo como «está bien» para que no vuelva a salir (D4).
  - Migraciones de esquema, y mover, renombrar o borrar archivos.

## 3. Reglas

### R0. Criterios de la revisión externa y cómo se recogen

| Criterio | Dónde |
|---|---|
| Si el volumen o la edición del archivo contradicen la ficha de destino, no basta con que coincida el título para enlazar (regla preventiva) | Fuera de esta historia, que no enlaza nada: es **BL-PARSE4** (§7). Aquí, R4 y R4b detectan los vínculos que ya contradicen el volumen |
| La carpeta es una pista, no un veto por sí sola: anuales y cruces conviven con la serie principal | Ninguna señal sale solo de la carpeta: la de «minoría en la carpeta» se descarta (§5.3); el año y el volumen de la carpeta cuentan solo si la carpeta habla de esa serie (R6); un anual en la carpeta de su serie madre no se marca (C21) |
| Los vínculos existentes se corrigen por lotes, con el destino verificado, nunca solos | Esta historia no corrige nada. Enseña lotes con su destino posible (R7) para que la corrección de BL-VINC2 se haga por lotes; hasta entonces, la única acción es la desvinculación de un archivo, con su confirmación |

### R1. Qué se revisa

Los archivos con número (`files.issue_id` no nulo) y no ausentes (`NOT is_missing`). Se miran **solo** su
nombre y las carpetas de su ruta guardada; no se abre ningún archivo de la biblioteca. Para cada uno se
calcula el nombre como lo hace el importer (`services/importer._triage_and_match`): cohorte por carpeta,
`parse_comic_filename` con carpeta y contexto, formato esperado, anual, serie alternativa y especial.

«Su serie» es la serie del número al que está vinculado; «su carpeta», la ruta del archivo sin el nombre.

### R2. Señal «otra serie»: el matcher de hoy elige otra serie

`SeriesMatcher.decide` sobre ese nombre devuelve una serie (`direct` o `fuzzy`) **distinta** de la suya.
Si se abstiene (`unsorted`), no hay señal.

**Guarda de orden de lectura:** no hay señal si el vínculo es manual (`metadata_source = manual`) y el
número vinculado no es el del nombre (sin ceros a la izquierda). Es el patrón de una saga asignada en su
orden de lectura (§1). El número distinto, por sí solo, **nunca** es una señal.

Motivo visible: `El nombre encaja con «{serie del matcher}»`.

### R3. Señal «año»: el año de la carpeta contradice el inicio de la serie

La carpeta dice un año (`core/matcher.py::_anio_de_carpeta`, BL-PARSE2), la serie tiene `start_year` y la
diferencia es **mayor que 1**. Solo cuenta si **el título de la carpeta habla de esa serie** (guarda de
título, R6): un crossover guardado en la carpeta de otra serie no contradice nada. Desconocer el año no es
una contradicción. Motivo visible: `La carpeta dice {AAAA}; la serie empieza en {AAAA}`.

### R4. Señal «volumen»: el volumen declarado no es el de la serie

- **Volumen declarado:** el del nombre (`parsed.volume`). Si el nombre no lo trae, el de la carpeta
  (`_volumen_en_carpeta`), **con la guarda de título de R6**.
- **Volumen de la serie:** `Series.volume`, o el de su título («Batman Vol 1»). Si no tiene ninguno, el
  **dominante** entre los volúmenes declarados de sus archivos: el más repetido, con al menos **2/3** de
  las declaraciones y habiendo al menos dos valores distintos.
- Hay señal si los dos se conocen y son distintos.

Motivo visible: `Dice vol. {N}; la serie es vol. {M}` o, si el de la serie es el dominante,
`Dice vol. {N}; el resto de la serie es vol. {M}`.

**Por qué el dominante:** casi ninguna serie del catálogo tiene `volume`, y comparar contra «la serie no
declara volumen» marcaba 717 archivos, casi todos bien. El 2/3 deja fuera los tomos de manga guardados en
una carpeta por tomo («Volumen N»): cada uno es un tomo, no un volumen de la serie.

### R4b. Señal «serie con varios volúmenes»: la ficha mezcla volúmenes

Se marcan **todos** los archivos con volumen declarado (R4) de una serie que cumple estas tres condiciones:

1. no tiene volumen propio (ni `Series.volume` ni en el título);
2. sus archivos declaran al menos dos volúmenes y ninguno llega al 2/3 de R4;
3. **algún número tiene archivos de dos volúmenes distintos**.

No se sabe qué lado es el bueno: decide la persona con la ficha delante. La condición 3 deja fuera las
series cuyos volúmenes son tomos de una numeración continua (un vol. 1 con los #1–12 y un vol. 2 con los
#13–32). Motivo visible: `Esta serie tiene archivos del vol. {N} y del vol. {M} en el mismo número`.

### R5. Señal «otro título en el número»: guarda de colecciones mezcladas (BL-INF11)

Hay señal si se cumplen las dos cosas:

- el número al que está vinculado tiene otros archivos y sus claves no son todas iguales
  (`utils/naming.clave_de_coleccion`, la misma función que BL-INF11);
- la clave del archivo no es la dominante de su serie (la más repetida entre los archivos de la serie, con
  mayoría estricta).

Así se marca el tebeo que sobra en el número, no los que están bien.
Motivo visible: `Comparte el #{N} con tebeos de otro título`.

### R6. Guarda de título de la carpeta

El título de la carpeta habla de la serie si, al compararlos, uno empieza por el otro. Antes de comparar se
quitan el volumen, los paréntesis y los corchetes, y se normaliza (minúsculas, sin acentos ni signos).

Ejemplos sintéticos: «Animal Man - Saga de un autor (2012)» habla de «ANIMAL MAN»; «Un evento Vol. 1» no
habla de «Justice League of America».

### R7. Lotes, destino posible y orden

- **Lote:** los archivos marcados con la misma **(carpeta, serie)**.
- **Destino posible del lote:** se busca en este orden.
  1. La serie que nombra R2, si todos los archivos del lote que tienen esa señal coinciden en ella.
  2. Si no, una serie del catálogo con el mismo título base (R6) y el volumen declarado del lote como
     `Series.volume`.
  3. Si no hay ninguna, el lote dice que no la hay.
- El destino es una pista para verificar, no una corrección: no se aplica nada.
- **Orden de los lotes:** por el mayor número de señales de sus archivos (de más a menos), después por
  número de archivos (de más a menos) y después por el título de la serie.
- **Orden dentro del lote:** por el orden del número (`Issue.sort_order`).

### R8. Solo lectura, coste y frescura

- La búsqueda se lanza a mano con un botón y corre **en segundo plano** con el indicador de tareas
  (`services/tareas.py`, con un tipo nuevo). Solo puede haber una a la vez. Medido en la Pi 5: unos 25 s
  para 4.506 archivos.
- El cálculo va en una transacción `READ ONLY`.
- Al terminar, se guarda el **informe** como un `ImportRun` con `details.kind = "vinculos_dudosos"`, el
  mismo patrón que el informe de «Revisar mi biblioteca». El informe lleva los ids de archivo, serie y
  número, las señales con sus datos y el destino posible. No se escribe nada más.
- Al pintar el bloque, una consulta comprueba que cada archivo del informe sigue vinculado al mismo número.
  El que ya no lo está no se enseña: el coleccionista lo acaba de arreglar.

### R9. Dónde vive

- La regla está en un servicio, `services/vinculos_dudosos.py`, que consumen la ruta web del bloque y el
  script de aceptación (CLAUDE.md §3.1.1).
- Las señales son funciones puras sobre los datos de R1 y se prueban sin base de datos.
- La plantilla solo pinta lo que recibe.

## 4. Dónde se ve y qué dice (glosario, CLAUDE.md §14)

Un bloque nuevo en **Duplicados** (`/ui/auditoria`), debajo de «Revisar mi biblioteca», que se pide al cargar
como los demás (`hx-get`, `hx-trigger="load"`). Es una revisión de la biblioteca, igual que el resto de esa
pantalla. No va en «Por revisar», que es la cola de pendientes, porque aquí no hay ningún pendiente.

| Sitio | Texto |
|---|---|
| Rótulo (`h2`) | `Vínculos dudosos` |
| Frase de entrada (≤ 20 palabras) | `Archivos que están en una serie, pero cuyo nombre o carpeta apuntan a otra.` |
| Botón (neutro, no `.primary`: el principal de la pantalla es «Registrar…») | `Buscar vínculos dudosos` |
| En curso (botón y chip del indicador de tareas) | `Buscando vínculos dudosos…` |
| Resumen | `{N} archivos en {G} grupos. Primero, los que tienen más motivos.` · `Última búsqueda: {fecha}` |
| Sin resultados | `No hay vínculos dudosos.` · `Última búsqueda: {fecha}` |
| Sin búsqueda aún | `Aún no se ha buscado.` |
| Cabecera de grupo (`.titulo-frase`) | `{n} archivos de «{carpeta visible}» están en «{serie}»` (ruta con `utils/ruta_visible`) |
| Destino posible (R7) | `Podría ser «{serie}».` · si no tiene números: `Podría ser «{serie}», que aún no tiene números en tu biblioteca.` · si no hay: `Ninguna serie de tu biblioteca encaja: habría que darla de alta.` |
| Motivos (chips, uno por señal) | los de R2–R5 |
| Fila de archivo | nombre del archivo, `#{N}`, motivos y el enlace `Deshacer la vinculación` (a `/ui/series/{serie}/archivos/{archivo}/deshacer`) |
| Desplegable (`<details>`) | `¿Por qué sale aquí?`: las cinco señales, en una frase cada una, y «Ninguna cambia nada: decides tú.» |

Términos: **archivo** (el fichero), **serie**, **número** (`#{N}`), **carpeta** y **tebeo** (en R5, el
objeto). No se usan «colección» (en §14 es otra cosa), «registro», «token», «lote», «matcher», «ficha» ni
«auditoría». «Lote» y «ficha» se usan en esta especificación, pero no en pantalla: el grupo se llama «grupo».
**Término nuevo:** «vínculo» / «vínculo dudoso» no está en §14. Si el PO aprueba el rótulo, se añade al
glosario antes de usarlo (D2).

## 5. Medición (Pi, 2026-11-27, código `0bfebfb7`)

Dos tandas de solo lectura, cada una autorizada por el usuario:

1. Un script dentro de `zascarr-orquestador`, en una transacción `SET TRANSACTION READ ONLY` terminada en
   `ROLLBACK`, sin abrir archivos de la biblioteca. Saca un resultado por archivo, con nombres, que se queda
   solo en el portátil.
2. Una consulta `READ ONLY` a las fichas de las series de los lotes: año, volumen, id de Comic Vine y número
   de números y de archivos.

Aquí solo van cifras agregadas. La tanda revisó 4.506 archivos vinculados: 1.457 manuales y 68 por ComicInfo.

**No hay verdad de referencia.** Cada lote marcado se miró a mano por su carpeta, su nombre y su ficha, y se
clasificó de forma provisional:

- *erróneo*: el vínculo es de otra serie, volumen u obra;
- *discutible*: el vínculo depende de una decisión del coleccionista o del modelo (una ficha que mezcla dos
  series y no se sabe qué lado manda, o tomos de manga que comparten número);
- *correcto*: un falso positivo.

La **precisión** cuenta solo los erróneos; «merece revisión» suma también los discutibles. La **cobertura** se
mide sobre los 128 casos conocidos de §1. La clasificación la confirma el PO en el bloque.

### 5.1 Por señal

| Señal | Marca | Conocidos (de 128) | Erróneo | Discutible | Correcto | Precisión | Merece revisión |
|---|---:|---:|---:|---:|---:|---:|---:|
| R2 otra serie (con guarda de orden de lectura) | 24 | 22 | 22 | 2 | 0 | 91,7 % | 100 % |
| R3 año (con guarda R6) | 3 | 3 | 3 | 0 | 0 | 100 % | 100 % |
| R4 volumen (R6 + dominante 2/3) | 63 | 63 | 63 | 0 | 0 | 100 % | 100 % |
| R4b serie con varios volúmenes | 99 | 62 | 66 | 27 | 6 | 66,7 % | 93,9 % |
| R5 otro título en el número | 60 | 22 | 51 | 3 | 6 | 85,0 % | 90,0 % |
| **Unión** | **205** | **128** | **161** | **32** | **12** | **78,5 %** | **94,1 %** |

Los 205 archivos marcados forman **24 lotes**.

- **R2:** la guarda de orden de lectura quita 10 grapas de una saga asignadas en su orden. Ninguna de las 22
  diferencias de número de §1 queda marcada solo por eso. Quedan 2 discutibles: una grapa de la misma saga
  con el número de la grapa y no el de su posición (inconsistencia de la asignación manual), y un `#0` en la
  carpeta de una edición cuyo catálogo no tiene ese número.
- **R4:** cubre los lotes de Superman (8), Batman vol. 2 (51) y sus 4 anuales. `Batman Vol 1` tiene
  `volume = 1`, así que la contradicción es directa.
- **R4b:** cubre los lotes de Green Lantern vol. 5 (30), las 22 de Green Lantern Corps y Peacemaker (10).
  También marca 3 grapas del vol. 3 de Green Lantern guardadas en la carpeta de un crossover; son erróneas
  porque la ficha de 2005 es el vol. 4 en Comic Vine. Marca además dos series que nadie había señalado:
  - **Batman: Odyssey:** 13 archivos. Los vol. 1 y vol. 2 están en una ficha de 2010; los 7 del vol. 2 son
    erróneos y los 6 del vol. 1, correctos.
  - **Gunsmith Cats:** 21 archivos. Tres partes comparten los números 1–9; se clasifican como discutibles.

  En Peacemaker, los 4 del vol. 2 son erróneos y los 6 del vol. 1, discutibles: la ficha no tiene año ni id
  de fuente.
- **R5:** los 51 erróneos son:
  - las 22 grapas de Green Lantern Corps;
  - 13 recopilaciones españolas con su propia numeración dentro de las grapas de Green Lantern;
  - 12 tie-ins de un evento dentro de otra serie;
  - 2 archivos de una secuela;
  - un especial y un one-shot, cada uno en el #1 de su serie madre.

  Los 6 correctos son copias del mismo número con otro título en el nombre: marcas del evento, «V.2» o
  abreviaturas de fansub.

### 5.2 Por número de señales

| Señales | Archivos | Erróneo | Conocidos |
|---:|---:|---:|---:|
| 3 | 22 | 22 | 22 (todas las de Green Lantern Corps: R2 + R4b + R5) |
| 1 | 183 | 139 | 106 |

Ningún archivo cumple dos señales, ni cuatro o más. Con el orden de R7, el lote de Green Lantern Corps sale
el primero; es el más seguro. Su destino posible, `Green Lantern Corps Vol. 3`, existe en el catálogo, pero
sin números. Para los lotes de Batman vol. 2 y Green Lantern vol. 5, el catálogo no tiene la serie de destino.

### 5.3 Variantes medidas y descartadas

| Variante | Marca | Por qué no |
|---|---:|---|
| Archivo minoría en su carpeta: ≥ 3 hermanos, todos en otra serie (BL-PARSE3 al revés) | 11 | 9 son anuales en la carpeta de su serie madre, bien vinculados. Con guarda de anual quedan 2, ninguno erróneo. No encuentra ningún caso conocido: en la carpeta de Green Lantern Corps, la mayoría es la contaminada |
| La misma, sin unanimidad (≥ 3 hermanos y ninguno en su serie / ≥ 5 y ≤ 20 %) | 45 / 220 | más ruido y ningún caso conocido |
| R2 sin la guarda de orden de lectura | 34 | los 10 de más son grapas de una saga asignadas en su orden, decisión del coleccionista |
| R2 cuando el matcher se abstiene, pero su mejor candidata es otra | 4 | los 4 son integrales bien vinculados |
| R3 sin la guarda de título | 7 | los 4 de más son crossovers en la carpeta de otra serie |
| R3 con el año del **nombre** | 75 | el año del nombre es el de la grapa, no el del inicio de la serie; ningún caso conocido |
| R4 contra «la serie no declara volumen» | 717 | casi todos correctos (R4) |
| R4b sin la condición del número repetido | 147 | añade 48 archivos de cuatro series bien vinculadas: una cuyos dos «volúmenes» son tomos con numeración continua (32) y tres de manga o tomos con un volumen por archivo (16) |
| R5 tal cual BL-INF11 (el número mezcla títulos) | 109 | marca los dos lados del número, también los buenos |

**Señal (4) del encargo, «minoría en la carpeta», descartada** por esta medición. Las otras cuatro se quedan
con sus guardas, y se añade R4b.

### 5.4 Lo que el matcher de hoy volvería a enlazar

De los 205 marcados, el matcher de hoy reproduce el mismo vínculo (`direct`) en **113**, de los que **80** son
erróneos:

- Batman vol. 2: 51;
- Green Lantern vol. 5: 8, más 3 grapas del vol. 3;
- Batman: Odyssey vol. 2: 7;
- Superman vol. 3: 7;
- Peacemaker vol. 2: 4.

Es la medida del criterio preventivo de la revisión externa. Corregir estos vínculos sin la guarda de
BL-PARSE4 no basta: un archivo nuevo con el mismo nombre y la misma carpeta se volvería a enlazar igual.

## 6. Criterios de aceptación y pruebas

| CA | Criterio | Prueba |
|---|---|---|
| C1 | R2: el matcher elige otra serie → marca, con la serie del matcher en el motivo | `tests/test_vinculos_dudosos.py::test_otra_serie_que_encaja_mejor_marca` |
| C2 | R2: el matcher reproduce el vínculo o se abstiene → no marca | `…::test_matcher_que_coincide_o_se_abstiene_no_marca` (parametrizada) |
| C3 | R2: vínculo manual con número distinto del nombre (orden de lectura) → no marca, aunque el matcher elija otra serie; el número distinto solo nunca marca | `…::test_orden_de_lectura_no_es_un_vinculo_dudoso` |
| C4 | R3: carpeta 2012 y serie 1989 marca; diferencia 1 o año desconocido no | `…::test_anio_de_carpeta_que_contradice_el_inicio` (parametrizada) |
| C5 | R3 + R6: el año de la carpeta de otra serie (crossover) no marca | `…::test_anio_de_carpeta_de_otro_titulo_no_marca` |
| C6 | R4: volumen declarado distinto de `Series.volume` o del título de la serie → marca | `…::test_volumen_distinto_del_de_la_serie_marca` |
| C7 | R4: la serie sin volumen marca la minoría si el dominante tiene ≥ 2/3; no la marca si no lo tiene (tomos de manga) | `…::test_volumen_dominante_de_la_serie` (parametrizada) |
| C8 | R4 + R6: el volumen de una carpeta de otro título no cuenta | `…::test_volumen_de_carpeta_de_otro_titulo_no_cuenta` |
| C9 | R4b: una serie sin volumen, con vol. 1 y vol. 2 en el mismo número y sin 2/3, marca todos sus archivos con volumen | `…::test_serie_con_varios_volumenes_en_el_mismo_numero_marca` |
| C10 | R4b: dos volúmenes con numeración continua (tomos) no marcan | `…::test_volumenes_con_numeracion_continua_no_marcan` |
| C11 | R5: en un número con dos títulos se marca el que no es el dominante de la serie, no el otro | `…::test_otro_titulo_en_el_numero_marca_solo_el_que_sobra` |
| C12 | Los siete casos conocidos de §1 salen marcados y las 22 de orden de lectura no, todo reproducido con nombres y catálogo sintéticos; el de Green Lantern Corps, con tres motivos | `…::test_casos_conocidos_salen_marcados` (parametrizada) |
| C13 | R7: lotes por (carpeta, serie), ordenados por motivos, tamaño y título | `…::test_orden_por_motivos_y_tamano_del_grupo` |
| C14 | R7: destino posible: la serie de R2; si no, la del mismo título con ese volumen; si no, ninguno | `…::test_destino_posible_del_grupo` (parametrizada) |
| C15 | R1: ausentes y pendientes no se revisan | `tests/test_vinculos_dudosos_pg.py::test_ausentes_y_pendientes_no_se_revisan` (pg) |
| C16 | R8: la búsqueda no cambia `files`, `issues` ni `series` (antes = después) y solo añade su informe | `tests/test_vinculos_dudosos_pg.py::test_la_busqueda_no_cambia_vinculos` (pg) |
| C17 | R8: un archivo desvinculado o reasignado después de la búsqueda no se enseña | `tests/test_vinculos_dudosos_pg.py::test_vinculo_cambiado_desde_la_busqueda_no_sale` (pg) |
| C18 | R8: corre en segundo plano con el indicador de tareas; una segunda petición mientras corre no lanza otra | `tests/test_web_vinculos_dudosos.py::test_busqueda_en_segundo_plano_una_a_la_vez` |
| C19 | §4: el bloque en Duplicados lleva rótulo, frase, botón neutro (sin `.primary`), resumen, grupos y destino posible | `tests/test_web_vinculos_dudosos.py::test_bloque_en_duplicados` |
| C20 | §4: cada fila enlaza a «Deshacer la vinculación» de ese archivo, y el bloque no tiene ningún formulario que cambie vínculos | `…::test_cada_archivo_enlaza_a_deshacer_la_vinculacion` |
| C21 | R0: un anual vinculado a su serie anual dentro de la carpeta de la serie madre no se marca (la carpeta no es un veto) | `tests/test_vinculos_dudosos.py::test_anual_en_la_carpeta_de_su_serie_madre_no_marca` |
| C22 | §4: textos sin búsqueda y sin resultados | `tests/test_web_vinculos_dudosos.py::test_sin_busqueda_y_sin_resultados` (parametrizada) |
| C23 | §4: el texto visible no dice «colección», «registro», «token», «lote», «ficha» ni «matcher» | `…::test_vocabulario_del_glosario` |

**Aceptación en datos reales** (tras desplegar, con tu autorización para la tanda en la Pi): un script de
solo lectura llama al servicio y comprueba:

- los **128** casos conocidos de §1, marcados (cobertura del 100 %);
- **ninguna** de las 22 grapas de orden de lectura de §1 marcada solo por R2;
- entre **195 y 215** archivos marcados (hoy, 205), con el lote de Green Lantern Corps el primero y con tres
  motivos;
- **0** cambios en vínculos (recuento de `files.issue_id` antes y después);
- una duración por debajo de **60 s**.

Además, revisas los lotes en el bloque, en el navegador: la precisión «merece revisión» tiene que ser
**≥ 90 %** (hoy, 94,1 % según la clasificación provisional de §5).

## 7. Decisiones para el PO y seguimiento

- **D1. Dónde se ve.** Propuesta: en **Duplicados** (`/ui/auditoria`), con las otras revisiones de la
  biblioteca. Alternativa: un aviso en la ficha de cada serie («N archivos de esta serie quizá sean de
  otra»), que puede ser una segunda historia sobre el mismo servicio.
- **D2. Rótulo y término nuevo.** «Vínculos dudosos» añade «vínculo» al glosario (§14.1: el número al que
  está unido un archivo). Alternativa sin término nuevo: «¿Están en su serie?».
- **D3. Guardar el informe.** Propuesta: como `ImportRun` (R8), igual que el informe de «Revisar mi
  biblioteca», para que sobreviva a un reinicio. Alternativa: solo en la memoria del proceso; se pierde al
  reiniciar, pero no escribe nada.
- **D4. «Está bien así».** Los 2 discutibles de R2, los lotes de Gunsmith Cats y del vol. 1 de Peacemaker y
  los 12 correctos volverán a salir en cada búsqueda. Propuesta: dejarlo **fuera** de esta historia; si
  molesta, otra historia con una marca por archivo, que es estado nuevo.
- **D5. Acción por archivo.** La revisión externa pide corregir por lotes. Propuesta: mantener el enlace a
  «Deshacer la vinculación» de un archivo, que ya existe y confirma, hasta que llegue BL-VINC2.
  Alternativa: un bloque sin ninguna acción hasta entonces.
- **Seguimiento (historias aparte, que se proponen a la vez que esta):**
  - **BL-PARSE4, guarda preventiva del matcher:** si el volumen o la edición del archivo contradicen la serie
    de destino, que el título coincida no basta para enlazar. Hoy repetiría 80 vínculos erróneos (§5.4). Se
    mide con el embudo, con 0 enlaces perdidos como condición.
  - **BL-VINC2, corrección por lotes:** desde un lote de esta revisión, con el destino verificado por la
    persona (y dado de alta si falta, como en B14) y una sola confirmación. Nunca sola. Antes hay que verificar
    las fichas que faltan: la serie de 2011 de Batman, el vol. 5 de Green Lantern y los dos volúmenes de
    Peacemaker.

## 8. Orden de los commits (SDD + TDD)

1. `spec:` este documento, aprobado.
2. `test:` C1–C23 en rojo, con el motivo de cada rojo en la PR.
3. Implementación mínima de R1–R9 hasta el verde de la suite completa (`--basetemp` en el disco raíz).
4. `refactor:` si hace falta, con todo en verde.
5. Comprobación del bloque en el navegador y tanda de aceptación en la Pi.
