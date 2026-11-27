# Especificación BL-VINC1 — Vínculos dudosos

> **Estado:** **borrador**, pendiente de aprobación del PO. No se programa nada hasta entonces (SDD + TDD).
> **Origen:** el [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md) destapó vínculos guardados que
> parecen mal hechos (§2.1: 22 grapas de Green Lantern Corps en Green Lantern) y BL-PARSE2 dejó otros dos
> grupos «a revisar por el PO» ([§5](especificacion-BL-PARSE2.md)). El PO preguntó si un algoritmo
> determinista podría tener esas mismas sospechas: sí, y esta historia las enseña.
> **Código de referencia:** `main` en `74429ec6`; la medición se hizo en la Pi con `0bfebfb7`, idéntico a
> `main` en `src/`.
> **Principio:** el sistema informa, la persona decide. Esta revisión **no cambia ningún vínculo**.

## 1. Problema

Un archivo vinculado a un número que no es el suyo no se ve en ninguna parte: no está en «Por revisar»,
cuenta como «tengo» en la serie equivocada y como «me falta» en la buena, y BL-INF11 frena las copias
buenas que llegan después al mismo número. Hoy solo se encuentran a mano o con un embudo de diagnóstico.

Casos conocidos, que la revisión **tiene** que encontrar:

| Caso | Archivos | Qué pasa |
|---|---:|---|
| Grapas de Green Lantern Corps en la serie Green Lantern | 22 | contaminación antigua (embudo §2.1) |
| Animal Man de Lemire en la edición de Zinco de 1989 | 3 | la carpeta dice 2012 (BL-PARSE2 R2) |
| Una carpeta que declara el vol. 3 de Superman, en la edición de Zinco de 1987 | 8 | Zinco es el vol. 2 (BL-PARSE2 §5) |

## 2. Alcance

- **Dentro:** una búsqueda a demanda, de solo lectura sobre los vínculos, que marca archivos ya vinculados
  cuyo vínculo contradice alguna de las señales deterministas de §3, los agrupa y los ordena por cuántas
  señales cumplen; un bloque en la pantalla **Duplicados** (`/ui/auditoria`) que enseña el resultado y,
  para cada archivo, lleva a la acción que ya existe para deshacer la vinculación (BL-R1b,
  `web/desvinculacion.py`), con su propia vista previa y confirmación.
- **Fuera:** cambiar, deshacer o crear vínculos desde este bloque (nunca solo, ni en lote); tocar el
  matcher, el importer o `files.metadata`; marcar un vínculo como «está bien» para que no vuelva a salir
  (D4); migraciones de esquema; mover, renombrar o borrar archivos.

## 3. Reglas

### R1. Qué se revisa

Los archivos con número (`files.issue_id` no nulo) y no ausentes (`NOT is_missing`). Se miran **solo** su
nombre y las carpetas de su ruta guardada; no se abre ningún archivo de la biblioteca. Para cada uno se
calcula el nombre como lo hace el importer (`services/importer._triage_and_match`): cohorte por carpeta,
`parse_comic_filename` con carpeta y contexto, formato esperado, anual, serie alternativa y especial.

«Su serie» es la serie del número al que está vinculado; «su carpeta», la ruta del archivo sin el nombre.

### R2. Señal «otra serie»: el matcher de hoy elige otra serie

`SeriesMatcher.decide` sobre ese nombre devuelve una serie (`direct` o `fuzzy`) **distinta** de la suya.
Si se abstiene (`unsorted`), no hay señal. Motivo visible: `El nombre encaja con «{serie del matcher}»`.

### R3. Señal «año»: el año de la carpeta contradice el inicio de la serie

La carpeta dice un año (`core/matcher.py::_anio_de_carpeta`, BL-PARSE2), la serie tiene `start_year` y la
diferencia es **mayor que 1**. Solo cuenta si **el título de la carpeta habla de esa serie** (guarda de
título, R6): un crossover guardado en la carpeta de otra serie no contradice nada. Desconocer el año no es
una contradicción. Motivo visible: `La carpeta dice {AAAA}; la serie empieza en {AAAA}`.

### R4. Señal «volumen»: el volumen declarado no es el de la serie

El volumen declarado es el del nombre (`parsed.volume`) o, si no lo trae, el de la carpeta
(`_volumen_en_carpeta`) **con la guarda de título de R6**. El volumen de la serie es `Series.volume`, o el
de su título («Batman Vol 1»), o, si no tiene ninguno, el **dominante** entre los volúmenes declarados de
sus archivos: el más repetido, con al menos **2/3** de las declaraciones y habiendo al menos dos valores
distintos. Hay señal si los dos se conocen y son distintos.

Motivo visible: `Dice vol. {N}; la serie es vol. {M}` o, si el de la serie es el dominante,
`Dice vol. {N}; el resto de la serie es vol. {M}`.

**Por qué el dominante:** casi ninguna serie del catálogo tiene `volume`, y comparar contra «la serie no
declara volumen» marcaba 717 archivos, casi todos bien. El 2/3 deja fuera los tomos de manga guardados en
una carpeta por tomo («Volumen N»): cada uno es un tomo, no un volumen de la serie.

### R5. Señal «otro título en el número»: guarda de colecciones mezcladas (BL-INF11)

El número al que está vinculado tiene otros archivos y sus claves (`utils/naming.clave_de_coleccion`, la
misma función que BL-INF11) no son todas iguales, **y** la clave del archivo no es la dominante de su serie
(la más repetida entre los archivos de la serie, con mayoría estricta). Así se marca el tebeo que sobra en
el número, no los que están bien. Motivo visible: `Comparte el #{N} con tebeos de otro título`.

### R6. Guarda de título de la carpeta

El título de la carpeta habla de la serie si, quitando el volumen, los paréntesis y los corchetes y
normalizando (minúsculas, sin acentos ni signos), uno empieza por el otro (ejemplos sintéticos: «Animal Man -
Saga de un autor (2012)» habla de «ANIMAL MAN»; «Un evento Vol. 1» no habla de «Justice League of America»).

### R7. Grupos y orden

Los archivos marcados se agrupan por **(carpeta, serie)**. Los grupos se ordenan por el mayor número de
señales de sus archivos (de más a menos), después por número de archivos (de más a menos) y después por el
título de la serie. Dentro del grupo, por el orden del número (`Issue.sort_order`).

### R8. Solo lectura, coste y frescura

- La búsqueda se lanza a mano con un botón y corre **en segundo plano** con el indicador de tareas
  (`services/tareas.py`, tipo nuevo); solo una a la vez. Medido en la Pi 5: ~25 s para 4.506 archivos.
- El cálculo va en una transacción `READ ONLY`. Al terminar, se guarda el **informe** (ids de archivo,
  serie y número, y las señales con sus datos) como un `ImportRun` con `details.kind = "vinculos_dudosos"`,
  el mismo patrón que el informe de «Revisar mi biblioteca». No se escribe nada más.
- Al pintar el bloque, una consulta comprueba que cada archivo del informe sigue vinculado al mismo número;
  el que ya no lo está no se enseña (el coleccionista lo acaba de arreglar).

### R9. Dónde vive

La regla está en un servicio (`services/vinculos_dudosos.py`) que consumen la ruta web del bloque y el
script de aceptación (CLAUDE.md §3.1.1). Las señales son funciones puras sobre los datos de R1, probadas
sin base de datos; la plantilla solo pinta lo que recibe.

## 4. Dónde se ve y qué dice (glosario, CLAUDE.md §14)

Un bloque nuevo en **Duplicados** (`/ui/auditoria`), debajo de «Revisar mi biblioteca», que se pide al cargar
como los demás (`hx-get`, `hx-trigger="load"`). Es una revisión de la biblioteca, igual que el resto de esa
pantalla; «Por revisar» es la cola de pendientes y aquí no hay ninguno.

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
| Motivos (chips, uno por señal) | los de R2–R5 |
| Fila de archivo | nombre del archivo, `#{N}`, motivos y el enlace `Deshacer la vinculación` (a `/ui/series/{serie}/archivos/{archivo}/deshacer`) |
| Desplegable (`<details>`) | `¿Por qué sale aquí?`: las cuatro señales en una frase cada una y «Ninguna cambia nada: decides tú, archivo a archivo.» |

Términos: **archivo** (el fichero), **serie**, **número** (`#{N}`), **carpeta**, **tebeo** (en R5, el objeto).
No se usan «colección» (es otra cosa en §14), «registro», «token», «lote», «matcher» ni «auditoría».
**Término nuevo:** «vínculo» / «vínculo dudoso» no está en §14; si el PO aprueba el rótulo, se añade al
glosario antes de usarlo (D2).

## 5. Medición (Pi, 2026-11-27, código `0bfebfb7`)

Script de solo lectura dentro de `zascarr-orquestador`: una transacción `SET TRANSACTION READ ONLY`
terminada en `ROLLBACK`, sin abrir archivos de la biblioteca. Salida por archivo (con nombres, solo en el
portátil); aquí, solo cifras agregadas. 4.506 archivos vinculados (1.457 manuales, 68 por ComicInfo).

**No hay verdad de referencia.** Cada grupo marcado se miró a mano por su carpeta y su nombre y se clasificó
de forma provisional: *erróneo* (el vínculo es de otra serie u obra), *discutible* (decisión del
coleccionista o del modelo, p. ej. un orden de lectura asignado a la serie del evento) o *correcto* (falso
positivo). La **precisión** cuenta solo los erróneos; «merece revisión» suma los discutibles. La
**cobertura** se mide sobre los 33 casos conocidos de §1. La clasificación la confirma el PO en el bloque.

### 5.1 Por señal

| Señal | Marca | Conocidos (de 33) | Erróneo | Discutible | Correcto | Precisión | Merece revisión |
|---|---:|---:|---:|---:|---:|---:|---:|
| R2 otra serie | 34 | 22 | 22 | 12 | 0 | 64,7 % | 100 % |
| R3 año (con guarda R6) | 3 | 3 | 3 | 0 | 0 | 100 % | 100 % |
| R4 volumen (R6 + dominante 2/3) | 63 | 8 | 63 | 0 | 0 | 100 % | 100 % |
| R5 otro título en el número | 60 | 22 | 51 | 3 | 6 | 85,0 % | 90,0 % |
| **Unión R2–R5** | **138** | **33** | **117** | **15** | **6** | **84,8 %** | **95,7 %** |

- **R2:** los 12 discutibles son 11 grapas asignadas a mano a la serie de un evento con el número de su
  posición en la lectura (el problema de modelo serie ↔ lectura del embudo) y un `#0` en la carpeta de una
  edición cuyo catálogo no tiene ese número.
- **R4:** además de los 8 conocidos, marca **55 que no estaban en la lista**: una carpeta que declara
  el vol. 2 de Batman (la serie de 2011) vinculada a la serie de 1939 del catálogo (51 grapas) y 4 anuales de
  esa misma carpeta en la línea anual de 1961. El catálogo no tiene la serie de 2011, y el matcher de hoy
  los vuelve a enlazar `direct` (seguimiento, §7).
- **R5:** los erróneos son, además de las 22 grapas de Green Lantern Corps, 13 recopilaciones españolas con
  su propia numeración dentro de las grapas de Green Lantern, 12 tie-ins de un evento dentro de otra serie,
  2 de una secuela, un especial y un one-shot en el #1 de su serie madre. Los 6 correctos son copias del mismo
  número con otro título en el nombre (marcas del evento, «V.2», abreviaturas de fansub).

### 5.2 Por número de señales

| Señales | Archivos | Erróneo | Conocidos |
|---:|---:|---:|---:|
| 2 | 22 | 22 | 22 (todas las de Green Lantern Corps) |
| 1 | 116 | 95 | 11 |

Ningún archivo cumple tres o más. El orden de R7 pone primero el único grupo que es seguro.

### 5.3 Variantes medidas y descartadas

| Variante | Marca | Por qué no |
|---|---:|---|
| Archivo minoría en su carpeta: ≥ 3 hermanos, todos en otra serie (BL-PARSE3 al revés) | 11 | 9 son anuales en la carpeta de su serie madre (correctos); con guarda de anual quedan 2, ninguno erróneo. No encuentra ninguno de los conocidos: en la carpeta de Green Lantern Corps la mayoría es la contaminada |
| La misma, sin unanimidad (≥ 3 hermanos y ninguno en su serie / ≥ 5 y ≤ 20 %) | 45 / 220 | más ruido y ningún conocido |
| R2 cuando el matcher se abstiene pero su mejor candidata es otra | 4 | los 4 son integrales bien vinculados |
| R3 sin la guarda de título | 7 | los 4 de más son crossovers en la carpeta de otra serie |
| R3 con el año del **nombre** | 75 | el año del nombre es el de la grapa, no el del inicio de la serie; ningún conocido |
| R4 contra «la serie no declara volumen» | 717 | casi todos correctos (§R4) |
| R5 tal cual BL-INF11 (el número mezcla títulos) | 109 | marca los dos lados del número, también los buenos |

**Señal (4) del encargo, «minoría en la carpeta», descartada** por esta medición; las otras cuatro se
quedan con sus guardas.

## 6. Criterios de aceptación y pruebas

| CA | Criterio | Prueba |
|---|---|---|
| C1 | R2: el matcher elige otra serie → marca, con la serie del matcher en el motivo | `tests/test_vinculos_dudosos.py::test_otra_serie_que_encaja_mejor_marca` |
| C2 | R2: el matcher reproduce el vínculo o se abstiene → no marca | `…::test_matcher_que_coincide_o_se_abstiene_no_marca` (parametrizada) |
| C3 | R3: carpeta 2012 y serie 1989 marca; diferencia 1 o año desconocido no | `…::test_anio_de_carpeta_que_contradice_el_inicio` (parametrizada) |
| C4 | R3 + R6: el año de la carpeta de otra serie (crossover) no marca | `…::test_anio_de_carpeta_de_otro_titulo_no_marca` |
| C5 | R4: volumen declarado distinto de `Series.volume` o del título de la serie → marca | `…::test_volumen_distinto_del_de_la_serie_marca` |
| C6 | R4: la serie sin volumen marca la minoría si el dominante tiene ≥ 2/3; no si no lo tiene (tomos de manga) | `…::test_volumen_dominante_de_la_serie` (parametrizada) |
| C7 | R4 + R6: el volumen de una carpeta de otro título no cuenta | `…::test_volumen_de_carpeta_de_otro_titulo_no_cuenta` |
| C8 | R5: en un número con dos títulos se marca el que no es el dominante de la serie, no el otro | `…::test_otro_titulo_en_el_numero_marca_solo_el_que_sobra` |
| C9 | Los tres casos conocidos de §1, reproducidos con nombres y catálogo sintéticos, salen marcados; el de Green Lantern Corps con dos motivos | `…::test_casos_conocidos_salen_marcados` |
| C10 | R7: grupos por (carpeta, serie), ordenados por motivos, tamaño y título | `…::test_orden_por_motivos_y_tamano_del_grupo` |
| C11 | R1: ausentes y pendientes no se revisan | `tests/test_vinculos_dudosos_pg.py::test_ausentes_y_pendientes_no_se_revisan` (pg) |
| C12 | R8: la búsqueda no cambia `files`, `issues` ni `series` (antes = después) y solo añade su informe | `tests/test_vinculos_dudosos_pg.py::test_la_busqueda_no_cambia_vinculos` (pg) |
| C13 | R8: un archivo desvinculado o reasignado después de la búsqueda no se enseña | `tests/test_vinculos_dudosos_pg.py::test_vinculo_cambiado_desde_la_busqueda_no_sale` (pg) |
| C14 | R8: corre en segundo plano con el indicador de tareas; una segunda petición mientras corre no lanza otra | `tests/test_web_vinculos_dudosos.py::test_busqueda_en_segundo_plano_una_a_la_vez` |
| C15 | §4: el bloque en Duplicados con rótulo, frase, botón neutro (sin `.primary`), resumen y grupos | `tests/test_web_vinculos_dudosos.py::test_bloque_en_duplicados` |
| C16 | §4: cada fila enlaza a «Deshacer la vinculación» de ese archivo; el bloque no tiene ningún formulario que cambie vínculos | `…::test_cada_archivo_enlaza_a_deshacer_la_vinculacion` |
| C17 | §4: sin búsqueda y sin resultados, los textos de la tabla | `…::test_sin_busqueda_y_sin_resultados` (parametrizada) |
| C18 | §4: el texto visible no dice «colección», «registro», «token», «lote» ni «matcher» | `…::test_vocabulario_del_glosario` |

**Aceptación en datos reales** (tras desplegar, con tu autorización para la tanda en la Pi): un script de
solo lectura que llama al servicio y cuenta:

- los **33** casos conocidos de §1, marcados (cobertura 100 %);
- entre **130 y 145** archivos marcados (hoy, 138), con el grupo de Green Lantern Corps primero y dos motivos;
- **0** cambios en vínculos (recuento de `files.issue_id` antes y después);
- duración por debajo de **60 s**;

y una revisión tuya de los grupos en el bloque, en el navegador: **precisión «merece revisión» ≥ 90 %**
(hoy, 95,7 % según la clasificación provisional de §5).

## 7. Decisiones para el PO

- **D1. Dónde se ve.** Propuesta: **Duplicados** (`/ui/auditoria`), con las otras revisiones de la
  biblioteca. Alternativa: un aviso en la ficha de cada serie («N archivos de esta serie quizá sean de
  otra»), que puede ser una segunda historia sobre el mismo servicio.
- **D2. Rótulo y término nuevo.** «Vínculos dudosos» añade «vínculo» al glosario (§14.1: el número al que
  está unido un archivo). Alternativa sin término nuevo: «¿Están en su serie?».
- **D3. Guardar el informe.** Propuesta: como `ImportRun` (R8), igual que el informe de «Revisar mi
  biblioteca», para que sobreviva a un reinicio. Alternativa: solo en memoria del proceso (se pierde al
  reiniciar, sin escritura ninguna).
- **D4. «Está bien así».** Los 11 del orden de lectura y los 6 correctos volverán a salir en cada búsqueda.
  Propuesta: **fuera** de esta historia; si molesta, otra historia con una marca por archivo (es estado nuevo).
- **Seguimiento, fuera:** el matcher enlazaría hoy las 51 grapas del vol. 2 de Batman a la serie de 1939
  (usa el volumen de la carpeta solo para desempatar). Merece su propia medición en el embudo.

## 8. Orden de los commits (SDD + TDD)

1. `spec:` este documento, aprobado.
2. `test:` C1–C18 en rojo, con el motivo de cada rojo en la PR.
3. Implementación mínima de R1–R9 hasta el verde de la suite completa (`--basetemp` en el disco raíz).
4. `refactor:` si hace falta, con todo en verde.
5. Comprobación del bloque en el navegador y tanda de aceptación en la Pi.
