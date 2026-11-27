# Especificación BL-VINC1 — Vínculos dudosos

> **Estado:** **borrador**, pendiente de aprobación del PO. No se programa nada hasta entonces (SDD + TDD).
> **Origen:** el [embudo del 2026-11-26](embudo-parser-matcher-2026-11-26.md) destapó vínculos guardados que
> parecen mal hechos (§2.1: 22 grapas de Green Lantern Corps en Green Lantern) y BL-PARSE2 dejó otros dos
> grupos «a revisar por el PO» ([§5](especificacion-BL-PARSE2.md)). El PO preguntó si un algoritmo
> determinista podría tener esas mismas sospechas: sí, y esta historia las enseña.
> **Revisión externa (2026-11-27):** el PO aportó lotes nuevos y tres criterios. Los lotes se comprobaron en la
> Pi con una tanda de solo lectura (§1, §5) y los criterios están en R0. Una **segunda revisión** (mismo día) dio
> por buena la dirección y pidió cuatro cambios: destino del lote solo si es compatible con todo el lote (R7);
> R4 separada en volumen explícito (R4) y mezcla de volúmenes (R4b), solo para revisar; la guarda preventiva
> como historia nueva sin especificar (§7); y una aceptación por archivo y por par archivo → número (§6).
> Una **tercera revisión** (mismo día) la da por lista para implementar con dos cambios: R4b se enseña como
> «Series que mezclan volúmenes», un grupo por serie con su desglose, y no como 263 vínculos dudosos sueltos;
> y el destino de R7 exige una señal positiva de identidad editorial, no solo que no haya contradicción.
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
  - Los marcados por una señal **del archivo** (R2–R5) se agrupan en **lotes** (carpeta y serie) y se
    ordenan por cuántas señales cumplen.
  - Cada lote indica un **destino posible** solo si una única candidata es compatible con todos sus
    archivos **y** tiene una señal positiva de identidad editorial; si no, dice «Destino por verificar» (R7).
  - Las series que mezclan volúmenes (R4b) salen aparte, **una por serie**, con el desglose por carpeta y
    volumen y los archivos plegados como evidencia.
  - Un bloque en la pantalla **Duplicados** (`/ui/auditoria`) enseña el resultado. Es un informe: no tiene
    ninguna acción que cambie vínculos (D5).
- **Fuera:**
  - Cambiar, deshacer o crear vínculos desde este bloque, nunca solo y tampoco en lote (la corrección por
    lotes es BL-VINC2, §7).
  - La guarda preventiva del matcher (una historia nueva, a proponer al PO, §7), y tocar el importer o
    `files.metadata`.
  - Marcar un vínculo como «está bien» para que no vuelva a salir (D4).
  - Migraciones de esquema, y mover, renombrar o borrar archivos.

## 3. Reglas

### R0. Criterios de la revisión externa y cómo se recogen

| Criterio | Dónde |
|---|---|
| Si el volumen o la edición del archivo contradicen la ficha de destino, no basta con que coincida el título para enlazar (regla preventiva) | Fuera de esta historia, que no enlaza nada: es una **historia nueva** que se propone al PO, sin ID ni especificación (§7). No es BL-PARSE4 (#1338), que evita que el subtítulo de un tomo se pegue al título de la serie. Aquí, R4 detecta los vínculos que ya contradicen el volumen explícito de su ficha, y BL-VINC1 aporta los casos para probar esa guarda |
| La carpeta es una pista, no un veto por sí sola: anuales y cruces conviven con la serie principal | Ninguna señal sale solo de la carpeta: la de «minoría en la carpeta» se descarta (§5.3); el año y el volumen de la carpeta cuentan solo si la carpeta habla de esa serie (R6); un anual en la carpeta de su serie madre no se marca (C21) |
| Los vínculos existentes se corrigen por lotes, con el destino verificado, nunca solos | Esta historia no corrige nada. Enseña lotes y, solo cuando es seguro, un destino posible (R7), para que la corrección de BL-VINC2 se haga por lotes. Hasta entonces, el bloque no tiene acciones (D5) |
| R4b señala la **serie**, no cada archivo: cuando sale sola, la mayoría de sus archivos están bien (tercera revisión) | Un grupo por serie, «Series que mezclan volúmenes», con desglose por carpeta y volumen y los archivos plegados (R4b, §4). Detectar la serie mezclada no equivale a saber qué archivos sobran (§6) |
| «No hay contradicción» no es «hay evidencia a favor» (tercera revisión) | El destino exige, además de la compatibilidad, título y volumen o título y año que coincidan explícitamente (R7). Una homónima sin año, volumen ni números no se propone (C14d) |

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

### R4. Señal «contradice el volumen de la ficha»: el volumen explícito no es el del archivo

- **Volumen declarado del archivo:** el del nombre (`parsed.volume`). Si el nombre no lo trae, el de la
  carpeta (`_volumen_en_carpeta`), **con la guarda de título de R6**.
- **Volumen de la ficha:** solo el **explícito**, `Series.volume` o el de su título («Batman Vol 1»). Si la
  ficha no tiene volumen explícito, R4 no se evalúa: la mayoría de sus archivos no es la identidad editorial
  de la ficha (puede estar mal vinculada, y «Vol» puede ser un tomo y no un volumen de serie).
- Hay señal si los dos se conocen y son distintos.

Motivo visible: `Dice vol. {N}; la serie es vol. {M}`.

### R4b. Señal «la ficha mezcla volúmenes»: una señal de la serie, solo para revisar

La señal es de la **serie**, no de cada archivo. Se señala la serie, y sus archivos con volumen declarado
(R4) van con ella como evidencia, cuando cumple estas condiciones:

1. no tiene volumen explícito (R4);
2. sus archivos declaran al menos dos volúmenes distintos;
3. **o** algún número tiene archivos de dos volúmenes distintos, **o** los volúmenes vienen de al menos
   dos carpetas que hablan de esa serie (R6), una por volumen.

Esta señal **no dice qué lado sobra**: la evidencia lleva los dos lados, y la persona decide con la ficha
delante. Tampoco sirve para vetar un enlace futuro ni para elegir destino (R7).

**Presentación:** cada serie señalada es **un grupo** de «Series que mezclan volúmenes», no un lote de
vínculos dudosos. El grupo lleva el desglose por **(carpeta, volumen)** con su número de archivos, y los
archivos en un desplegable. Un archivo de esa serie que además tiene una señal propia (R2–R5) sale **también**
en su lote, con el chip de R4b como contexto; los que solo tienen R4b no forman lotes. R4b no cuenta para el
orden de los lotes (R7). La condición 3 deja fuera los volúmenes que
son tomos de una numeración continua, declarados solo en el nombre y dentro de una misma carpeta (un vol. 1
con los #1–12 y un vol. 2 con los #13–32), y las series de manga con un volumen distinto en cada archivo.

Texto visible: `Esta serie tiene archivos del vol. {N} ({a}) y del vol. {M} ({b})` en la cabecera del grupo;
una línea por carpeta y volumen en el desglose.

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

- **Lote:** los archivos con alguna señal **del archivo** (R2–R5) y la misma **(carpeta, serie)**.
- **Destino posible del lote.** Las candidatas son las series distintas de la vinculada que el matcher
  propone (como elegida o como candidata por encima del umbral) para **todos** los archivos del lote. Una
  candidata es **compatible** con un archivo si no contradice nada de lo que se sabe de él:
  - su volumen explícito no es distinto del volumen declarado del archivo (R4);
  - su `start_year` no contradice en más de un año el año de la carpeta (R3);
  - es una serie anual si y solo si el archivo es un anual;
  - tiene el número del archivo, o todavía no tiene ningún número.

  Las guardas solo descartan: una candidata sin año, sin volumen y sin números las pasa todas por falta de
  datos. Por eso, además, la candidata necesita una **señal positiva de identidad editorial**, las dos cosas:
  - su título, sin el volumen, es **igual** al del lote (normalizado como en R6; el del nombre o el de la
    carpeta), y no solo uno prefijo del otro;
  - y coincide explícitamente **al menos uno** de estos datos, en todos los archivos del lote que lo
    declaran (y al menos uno lo declara):
    - su volumen explícito es el volumen declarado del archivo (R4);
    - su `start_year` está a un año o menos del año de la carpeta (R3).

  Tener el número del archivo no es identidad: cualquier serie tiene un #1. Coincidir solo en el título
  tampoco.

  Se enseña un destino solo si **exactamente una** candidata es compatible con **todos** los archivos del lote
  y tiene identidad positiva. Si hay cero o más de una, el lote dice **«Destino por verificar»**. Nunca dice
  que la serie no existe: el catálogo puede tenerla con otro título.
- La señal R4b no aporta destino, y el destino es una pista para verificar, no una corrección.
- **Orden de los lotes:** primero por el mayor número de señales **del archivo** (R2, R3, R4 y R5) de sus
  archivos, después por número de archivos (de más a menos) y por último por el título de la serie.
- **Orden de las series que mezclan volúmenes:** por número de archivos (de más a menos) y por título. Van
  detrás de los lotes.
- **Orden dentro del lote:** por el orden del número (`Issue.sort_order`).

### R8. Solo lectura, coste y frescura

- La búsqueda se lanza a mano con un botón y corre **en segundo plano** con el indicador de tareas
  (`services/tareas.py`, con un tipo nuevo). Solo puede haber una a la vez. Medido en la Pi 5: unos 25 s
  para 4.506 archivos.
- El cálculo va en una transacción `READ ONLY`.
- Al terminar, se guarda el **informe** como un `ImportRun` con `details.kind = "vinculos_dudosos"`, el
  mismo patrón que el informe de «Revisar mi biblioteca». El informe lleva los ids de archivo, serie y
  número, las señales con sus datos y el destino posible, si lo hay, y las series de R4b con su desglose.
  No se escribe nada más.
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
| Resumen | `{N} archivos en {G} grupos. Primero, los que tienen más motivos.` · si hay R4b: `Además, {S} series mezclan volúmenes.` · `Última búsqueda: {fecha}` |
| Aviso junto al resumen (`ui.aviso`, informativo) | `Esto es solo un informe. Corregir estos archivos llegará más adelante, por grupos.` |
| Sin resultados | `No hay vínculos dudosos.` · `Última búsqueda: {fecha}` |
| Sin búsqueda aún | `Aún no se ha buscado.` |
| Cabecera de grupo (`.titulo-frase`) | `{n} archivos de «{carpeta visible}» están en «{serie}»` (ruta con `utils/ruta_visible`) |
| Destino posible (R7) | `Podría ser «{serie}».` · si aún no tiene números: `Podría ser «{serie}», que aún no tiene números en tu biblioteca.` · en otro caso: `Destino por verificar.` |
| Motivos (chips, uno por señal) | los de R2–R5; si el archivo es de una serie de R4b, además el chip `Su serie mezcla volúmenes` como contexto |
| Subapartado de R4b (`h3`, en Archivo: es una frase) | `Series que mezclan volúmenes` · frase: `Tienen archivos de varios volúmenes. Puede sobrar uno de ellos, o ninguno.` |
| Cabecera de cada serie (`.titulo-frase`) | `«{serie}»: archivos del vol. {N} ({a}) y del vol. {M} ({b})`; el nombre enlaza a su ficha |
| Desglose (una línea por carpeta y volumen) | `vol. {N} · {n} archivos · «{carpeta visible}»` |
| Archivos de la serie (`<details>`, plegado) | `Ver los {n} archivos`: nombre, `#{N}` y volumen; sin acciones |
| Fila de archivo | nombre del archivo, `#{N}` y motivos; el nombre de la serie enlaza a su ficha (`/ui/series/{serie}`). Sin botón ni enlace de desvinculación (D5) |
| Desplegable (`<details>`) | `¿Por qué sale aquí?`: las cinco señales (la de R4b, «esto dice que la serie mezcla volúmenes, no qué archivos están mal»), en una frase cada una, y «Ninguna cambia nada: decides tú. Desvincular un archivo no lo pasa a la serie buena: lo devuelve a «Por revisar».» |

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
Las cifras de esta sección están calculadas otra vez con las reglas de la segunda y la tercera revisión, sobre
los mismos datos (sin otra tanda en la Pi).

**No hay verdad de referencia.** Cada lote marcado se miró a mano por su carpeta, su nombre y su ficha, y se
clasificó de forma provisional:

- *erróneo*: el vínculo es de otra serie, volumen u obra;
- *discutible*: el vínculo depende de una decisión del coleccionista o del modelo (una ficha que mezcla dos
  series y no se sabe qué lado manda, o tomos de manga que comparten número);
- *correcto*: un falso positivo.

Se publican **dos proporciones distintas**, no dos medidas de precisión equivalentes:

- **proporción de erróneos**: erróneos / marcados, según la clasificación provisional;
- **proporción que merece revisión**: (erróneos + discutibles) / marcados.

La **cobertura** se mide sobre los 128 archivos concretos de §1 (por id, no por recuento). La clasificación la
confirma el PO en el bloque.

### 5.1 Por señal

| Señal | Marca | Conocidos (de 128) | Erróneo | Discutible | Correcto | Proporción de erróneos | Proporción que merece revisión |
|---|---:|---:|---:|---:|---:|---:|---:|
| R2 otra serie (con guarda de orden de lectura) | 24 | 22 | 22 | 2 | 0 | 91,7 % | 100 % |
| R3 año (con guarda R6) | 3 | 3 | 3 | 0 | 0 | 100 % | 100 % |
| R4 contradice el volumen explícito de la ficha | 51 | 51 | 51 | 0 | 0 | 100 % | 100 % |
| R5 otro título en el número | 60 | 22 | 51 | 3 | 6 | 85,0 % | 90,0 % |
| **Señales del archivo (R2, R3, R4, R5)** | **116** | **76** | **105** | **5** | **6** | **90,5 %** | **94,8 %** |
| R4b la ficha mezcla volúmenes (solo para revisar) | 263 | 74 | 78 | 27 | 158 | 29,7 % | 39,9 % |
| Unión por archivo (referencia; no es lo que se enseña) | 357 | 128 | 161 | 32 | 164 | 45,1 % | 54,1 % |

**Lo que se enseña** (tercera revisión):

| Apartado | Grupos | Archivos | Conocidos (de 128) |
|---|---:|---:|---:|
| Vínculos dudosos (lotes por señales del archivo) | 16 lotes | 116 | 76 |
| Series que mezclan volúmenes (R4b) | 6 series, 14 líneas de desglose | 263 (241 sin señal propia) | 74 (52 solo aquí) |

Los 128 conocidos salen todos: 76 en un lote (51 por R4; Green Lantern Corps por R2 y R5, con el chip de
R4b; Lemire por R3) y 52 solo como evidencia de una serie que mezcla volúmenes (Superman vol. 3, los 4
anuales de Batman, Green Lantern vol. 5 y Peacemaker). Antes se enseñaban 357 filas en 26 lotes; ahora, 116
filas en 16 lotes y 6 series con el resto plegado. Solo en Superman, el coleccionista ya no criba 144 filas
para un problema de 8: ve una serie con dos líneas (vol. 2 y vol. 3).

- **R2:** la guarda de orden de lectura quita 10 grapas de una saga asignadas en su orden. Ninguna de las 22
  diferencias de número de §1 queda marcada solo por eso. Quedan 2 discutibles: una grapa de la misma saga
  con el número de la grapa y no el de su posición (inconsistencia de la asignación manual), y un `#0` en la
  carpeta de una edición cuyo catálogo no tiene ese número.
- **R4:** solo `Batman Vol 1` tiene un volumen explícito contradicho (`volume = 1` y 51 archivos de una
  carpeta del vol. 2).
- **R4b** señala seis series. **Por serie**, las seis merecen revisión: en cinco al menos un lado es
  erróneo y la sexta es discutible. **Por archivo**, su proporción de erróneos es baja (29,7 %) porque la
  evidencia lleva los dos lados a propósito: cuando sale sola, 158 de sus archivos son correctos (136 solo en
  Superman, frente a 8 erróneos). Por eso se enseña por serie: es una pista para abrir la ficha, no un
  dictamen sobre cada archivo.

  | Ficha | Archivos | Erróneo | Discutible | Correcto |
  |---|---:|---:|---:|---:|
  | Green Lantern (2005, vol. 4 en Comic Vine): grapas de los vol. 3 y 5 | 55 | 55 | 0 | 0 |
  | Superman de Zinco: vol. 2 y una carpeta del vol. 3 | 144 | 8 | 0 | 136 |
  | Batman Annual (1961): anuales de las carpetas de los vol. 1 y 2 | 20 | 4 | 0 | 16 |
  | Batman: Odyssey (2010): vol. 1 y vol. 2 | 13 | 7 | 0 | 6 |
  | Peacemaker (sin año ni id): vol. 1 y vol. 2 | 10 | 4 | 6 | 0 |
  | Gunsmith Cats: tres partes con los números 1–9 | 21 | 0 | 21 | 0 |

- **R5:** los 51 erróneos son:
  - las 22 grapas de Green Lantern Corps;
  - 13 recopilaciones españolas con su propia numeración dentro de las grapas de Green Lantern;
  - 12 tie-ins de un evento dentro de otra serie;
  - 2 archivos de una secuela;
  - un especial y un one-shot, cada uno en el #1 de su serie madre.

  Los 6 correctos son copias del mismo número con otro título en el nombre: marcas del evento, «V.2» o
  abreviaturas de fansub.

### 5.2 Por número de señales y destino

| Señales | Archivos | Erróneo | Conocidos |
|---|---:|---:|---:|
| R2 + R4b + R5 | 22 | 22 | 22 (Green Lantern Corps) |
| una señal del archivo | 94 | 83 | 54 |
| solo R4b (en su serie, sin lote) | 241 | 56 | 52 |

Con el orden de R7, el lote de Green Lantern Corps sale el primero; es el más seguro.

**Destino (R7):** 5 de los 16 lotes tienen alguna candidata común. Con las cuatro condiciones de
compatibilidad y la identidad positiva, solo el de Green Lantern Corps tiene destino:
`Green Lantern Corps Vol. 3`. Aún no tiene números, así que las guardas no le dicen nada; la identidad sí:
el título coincide y su volumen explícito (3) es el que declara la carpeta de las 22 grapas. Su anual
(`Green Lantern Corps Annual`) queda fuera por no ser un anual el archivo. Los demás dicen «Destino por
verificar»:

- Superman vol. 3 ya no es un lote: solo tiene R4b y va en su serie, que no propone destino. Con la regla de
  la segunda revisión, su única candidata era una novela gráfica sin número titulada `SUPERMAN`.
- Lemire y el `#0`: las ediciones candidatas no tienen esos números. Animal Man (2011) tendría identidad por
  año (carpeta 2012), pero no es compatible.
- Batman vol. 2: tiene dos candidatas, ninguna tiene sus números y ninguna tiene identidad positiva (otro
  título, sin año ni volumen).
- El lote de una sola grapa de orden de lectura tiene dos candidatas. Si las dos tienen su número, dice
  «Destino por verificar»; se comprobará en la aceptación.

La condición del número se comprobó con las fichas de la segunda tanda y con BL-PARSE2, no con el script de
la captura.

### 5.3 Variantes medidas y descartadas

| Variante | Marca | Por qué no |
|---|---:|---|
| Archivo minoría en su carpeta: ≥ 3 hermanos, todos en otra serie (BL-PARSE3 al revés) | 11 | 9 son anuales en la carpeta de su serie madre, bien vinculados. Con guarda de anual quedan 2, ninguno erróneo. No encuentra ningún caso conocido: en la carpeta de Green Lantern Corps, la mayoría es la contaminada |
| La misma, sin unanimidad (≥ 3 hermanos y ninguno en su serie / ≥ 5 y ≤ 20 %) | 45 / 220 | más ruido y ningún caso conocido |
| R2 sin la guarda de orden de lectura | 34 | los 10 de más son grapas de una saga asignadas en su orden, decisión del coleccionista |
| R2 cuando el matcher se abstiene, pero su mejor candidata es otra | 4 | los 4 son integrales bien vinculados |
| R3 sin la guarda de título | 7 | los 4 de más son crossovers en la carpeta de otra serie |
| R3 con el año del **nombre** | 75 | el año del nombre es el de la grapa, no el del inicio de la serie; ningún caso conocido |
| R4 contra «la serie no declara volumen» | 717 | casi todos correctos |
| R4 con el volumen **dominante** (≥ 2/3) de los archivos como volumen de la ficha (primera versión) | 63 | la mayoría no demuestra la identidad editorial de la ficha (segunda revisión): pasa a R4b, que no decide qué lado sobra |
| R4b solo con el número repetido | 243 | pierde los 4 anuales de Batman vol. 2, que no comparten número con los del vol. 1 |
| R4b sin la condición 3 | 311 | añade 48 archivos de cuatro series bien vinculadas: tomos con numeración continua (32) y manga con un volumen por archivo (16) |
| Destino con una única candidata compatible, sin exigir identidad positiva (segunda versión) | — | una homónima sin año, volumen ni números pasa todas las guardas por falta de datos (tercera revisión). En la captura no cambia el resultado, pero no es una regla segura |
| R4b como lote de vínculos dudosos, archivo por archivo (segunda versión) | 263 filas | 158 correctos entre los que solo tienen R4b; el problema de una serie se reparte en varias filas (tercera revisión) |
| Destino si coinciden en él los archivos con R2 (primera versión) | — | no exigía que fuera compatible con los demás archivos del lote ni que no hubiera otra candidata (segunda revisión); con solo volumen, año y anual, el lote de Superman vol. 3 recibiría la novela gráfica `SUPERMAN` |
| R5 tal cual BL-INF11 (el número mezcla títulos) | 109 | marca los dos lados del número, también los buenos |

**Señal (4) del encargo, «minoría en la carpeta», descartada** por esta medición. Las otras cuatro se quedan
con sus guardas; la de volumen queda partida en R4 (explícito) y R4b (mezcla, solo para revisar).

### 5.4 Lo que el matcher de hoy volvería a enlazar

De los 161 erróneos, el matcher de hoy reproduce el mismo vínculo (`direct`) en **80**:

- Batman vol. 2: 51;
- Green Lantern vol. 5: 8, más 3 grapas del vol. 3;
- Batman: Odyssey vol. 2: 7;
- Superman vol. 3: 7;
- Peacemaker vol. 2: 4.

Es la medida del criterio preventivo de la revisión externa. Corregir estos vínculos sin una guarda de volumen
y edición en el matcher no basta: un archivo nuevo con el mismo nombre y la misma carpeta se volvería a enlazar
igual. Esa guarda es otra historia (§7). Estos 80 son sus casos de prueba de «deja de repetir»; los de «conserva
los correctos» salen del embudo.

## 6. Criterios de aceptación y pruebas

| CA | Criterio | Prueba |
|---|---|---|
| C1 | R2: el matcher elige otra serie → marca, con la serie del matcher en el motivo | `tests/test_vinculos_dudosos.py::test_otra_serie_que_encaja_mejor_marca` |
| C2 | R2: el matcher reproduce el vínculo o se abstiene → no marca | `…::test_matcher_que_coincide_o_se_abstiene_no_marca` (parametrizada) |
| C3 | R2: vínculo manual con número distinto del nombre (orden de lectura) → no marca, aunque el matcher elija otra serie; el número distinto solo nunca marca | `…::test_orden_de_lectura_no_es_un_vinculo_dudoso` |
| C4 | R3: carpeta 2012 y serie 1989 marca; diferencia 1 o año desconocido no | `…::test_anio_de_carpeta_que_contradice_el_inicio` (parametrizada) |
| C5 | R3 + R6: el año de la carpeta de otra serie (crossover) no marca | `…::test_anio_de_carpeta_de_otro_titulo_no_marca` |
| C6 | R4: volumen declarado distinto de `Series.volume` o del título de la serie → marca | `…::test_volumen_distinto_del_explicito_de_la_ficha_marca` |
| C7 | R4: una ficha sin volumen explícito no se evalúa en R4, aunque la mayoría de sus archivos diga otro volumen | `…::test_ficha_sin_volumen_explicito_no_usa_la_mayoria` |
| C8 | R4 + R6: el volumen de una carpeta de otro título no cuenta | `…::test_volumen_de_carpeta_de_otro_titulo_no_cuenta` |
| C9 | R4b: una ficha sin volumen explícito, con vol. 1 y vol. 2 en el mismo número o en dos carpetas propias, señala la serie con **los dos** lados como evidencia | `…::test_ficha_que_mezcla_volumenes_marca_los_dos_lados` (parametrizada) |
| C9b | R4b: la serie sale como **un** grupo con su desglose por (carpeta, volumen) y sus archivos; los que solo tienen R4b no forman lote, y el que además tiene una señal propia sale en su lote con el chip de contexto | `…::test_mezcla_de_volumenes_es_un_grupo_por_serie` |
| C10 | R4b: tomos con numeración continua en una carpeta, o un volumen por archivo, no marcan | `…::test_volumenes_que_son_tomos_no_marcan` (parametrizada) |
| C11 | R5: en un número con dos títulos se marca el que no es el dominante de la serie, no el otro | `…::test_otro_titulo_en_el_numero_marca_solo_el_que_sobra` |
| C12 | Los siete casos conocidos de §1 salen (en un lote o como evidencia de su serie de R4b) y las 22 de orden de lectura no, todo reproducido con nombres y catálogo sintéticos; el de Green Lantern Corps, en un lote con dos motivos propios y el chip de R4b | `…::test_casos_conocidos_salen_marcados` (parametrizada) |
| C13 | R7: lotes por (carpeta, serie), ordenados por señales del archivo, tamaño y título; R4b no cuenta para el orden y las series de R4b van detrás | `…::test_orden_por_motivos_y_tamano_del_grupo` |
| C14 | R7: hay destino solo con una única candidata compatible con todos los archivos; con cero o dos, «Destino por verificar» | `…::test_destino_solo_si_es_compatible_con_todo_el_grupo` (parametrizada) |
| C14b | R7: una candidata que contradice el volumen, el año, el anual o el número de un solo archivo del lote no es destino (el caso de la novela gráfica `SUPERMAN`) | `…::test_candidata_incompatible_con_un_archivo_no_es_destino` (parametrizada) |
| C14c | R7: R4b no aporta destino | `…::test_mezcla_de_volumenes_no_propone_destino` |
| C14d | R7: una homónima **vacía** (mismo título, sin año, sin volumen y sin números), única candidata compatible, **no** se propone: «Destino por verificar» | `…::test_homonima_vacia_no_es_destino` |
| C14e | R7: `Green Lantern Corps Vol. 3`, sin números, **sí** se propone para el lote de sus grapas, porque coincide explícitamente en título y volumen (sintético) | `…::test_titulo_y_volumen_explicitos_bastan_sin_numeros` |
| C14f | R7: coincidir solo en el título, o solo en el número, no es identidad; coincidir en título y año (±1) sí | `…::test_identidad_editorial_positiva` (parametrizada) |
| C15 | R1: ausentes y pendientes no se revisan | `tests/test_vinculos_dudosos_pg.py::test_ausentes_y_pendientes_no_se_revisan` (pg) |
| C16 | R8: la búsqueda no cambia `files`, `issues` ni `series`: el **conjunto de pares (archivo, número)** y las filas de `issues` y `series` son idénticos antes y después, y solo se añade su informe | `tests/test_vinculos_dudosos_pg.py::test_la_busqueda_no_cambia_vinculos` (pg) |
| C17 | R8: un archivo desvinculado o reasignado después de la búsqueda no se enseña | `tests/test_vinculos_dudosos_pg.py::test_vinculo_cambiado_desde_la_busqueda_no_sale` (pg) |
| C18 | R8: corre en segundo plano con el indicador de tareas; una segunda petición mientras corre no lanza otra | `tests/test_web_vinculos_dudosos.py::test_busqueda_en_segundo_plano_una_a_la_vez` |
| C19 | §4: el bloque en Duplicados lleva rótulo, frase, botón neutro (sin `.primary`), resumen, grupos, destino posible y el subapartado «Series que mezclan volúmenes» con el desglose y los archivos plegados | `tests/test_web_vinculos_dudosos.py::test_bloque_en_duplicados` |
| C20 | §4 y D5: el bloque no tiene formularios ni enlaces de desvinculación; la serie enlaza a su ficha; el desplegable dice que desvincular no reasigna | `…::test_el_informe_no_tiene_acciones_sobre_vinculos` |
| C21 | R0: un anual vinculado a su serie anual dentro de la carpeta de la serie madre no se marca (la carpeta no es un veto) | `tests/test_vinculos_dudosos.py::test_anual_en_la_carpeta_de_su_serie_madre_no_marca` |
| C22 | §4: textos sin búsqueda y sin resultados | `tests/test_web_vinculos_dudosos.py::test_sin_busqueda_y_sin_resultados` (parametrizada) |
| C23 | §4: el texto visible no dice «colección», «registro», «token», «lote», «ficha» ni «matcher» | `…::test_vocabulario_del_glosario` |

**Aceptación en datos reales** (tras desplegar, con tu autorización para la tanda en la Pi): un script de
solo lectura llama al servicio y comprueba:

- **los 128 archivos concretos** de §1, por id: la lista de ids de la captura del 2026-11-27 (archivo, serie y
  número vinculados; sin nombres ni rutas) está fuera del repositorio, en la carpeta de notas del operador.
  Cada uno tiene que salir marcado. Si alguno ya no está vinculado como en la captura, se informa aparte y no
  cuenta como fallo;
- **ninguna** de las 22 grapas de orden de lectura de §1 marcada solo por R2;
- de ellos, los **76** de §5.1 en un lote y los **52** restantes como evidencia de su serie en «Series que
  mezclan volúmenes». Que un archivo salga como evidencia de R4b **no** cuenta como identificarlo como mal
  vinculado: R4b encuentra la serie, y qué archivos sobran lo decide el PO con ella delante;
- las **6** series de R4b, cada una una sola vez, con su desglose;
- el lote de Green Lantern Corps, el primero, con sus motivos y destino `Green Lantern Corps Vol. 3`; ningún
  otro lote con destino que el PO no dé por bueno, y ninguno cuya candidata solo coincida en el título;
- **0** cambios en vínculos: el conjunto de pares (archivo, número) de todos los archivos, tomado antes y
  después de la búsqueda, es idéntico. Se compara el conjunto, no el recuento, porque una reasignación
  indebida deja el recuento igual;
- una duración por debajo de **60 s**.

Además, revisas los lotes en el bloque, en el navegador. Se anotan las dos proporciones de §5, con las señales
del archivo y con R4b por separado: la proporción que merece revisión de las señales del archivo tiene que ser
**≥ 90 %** (hoy, 94,8 % según la clasificación provisional). R4b se anota **por serie** (hoy, 6 de 6
merecen revisión) y no tiene umbral por archivo: es una pista sobre la serie.

## 7. Decisiones para el PO y seguimiento

- **D1. Dónde se ve.** Propuesta: en **Duplicados** (`/ui/auditoria`), con las otras revisiones de la
  biblioteca. Alternativa: un aviso en la ficha de cada serie («N archivos de esta serie quizá sean de
  otra»), que puede ser una segunda historia sobre el mismo servicio.
- **D2. Rótulo y término nuevo.** «Vínculos dudosos» añade «vínculo» al glosario (§14.1: el número al que
  está unido un archivo). Alternativa sin término nuevo: «¿Están en su serie?».
- **D3. Guardar el informe.** Propuesta: como `ImportRun` (R8), igual que el informe de «Revisar mi
  biblioteca», para que sobreviva a un reinicio. Alternativa: solo en la memoria del proceso; se pierde al
  reiniciar, pero no escribe nada.
- **D4. «Está bien así».** Los 2 discutibles de R2, los lotes de Gunsmith Cats y del vol. 1 de Peacemaker, los
  correctos de R5 y el lado bueno de las fichas de R4b (136 de Superman, 16 de Batman Annual y 6 de Batman:
  Odyssey) volverán a salir en cada búsqueda. Propuesta: dejarlo **fuera** de esta historia; si molesta, otra
  historia con una marca por archivo o por ficha, que es estado nuevo.
- **D5. Sin acciones en el informe.** Lo pide la segunda revisión: el primer resultado útil es encontrar el
  problema sin empeorar la biblioteca. El bloque no tiene ninguna desvinculación, destacada ni discreta,
  mientras no exista BL-VINC2. Desde la ficha de la serie sigue estando la desvinculación de siempre, con su
  confirmación. El desplegable avisa de que desvincular no reasigna: el archivo vuelve a «Por revisar».
- **Seguimiento.** Ninguna de estas historias tiene ID ni especificación: se proponen al PO, que decide si
  existen.
  - **Guarda de volumen y edición del matcher (historia nueva):** si el volumen o la edición del archivo
    contradicen la ficha de destino, que el título coincida no basta para enlazar. Se mediría de dos formas:
    cuántos de los 80 enlaces erróneos de §5.4 deja de repetir el matcher, y cuántos enlaces correctos del
    embudo conserva. BL-VINC1 aporta los casos para probarla. No es BL-PARSE4 (#1338).
  - **BL-VINC2, corrección por lotes:** desde un lote de esta revisión, con el destino verificado por la
    persona (y dado de alta si falta, como en B14) y una sola confirmación. Nunca sola. Antes hay que verificar
    las fichas que faltan: la serie de 2011 de Batman, el vol. 5 de Green Lantern y los dos volúmenes de
    Peacemaker.

## 8. Orden de los commits (SDD + TDD)

1. `spec:` este documento, aprobado.
2. `test:` C1–C23 (con C9b y C14b–C14f) en rojo, con el motivo de cada rojo en la PR.
3. Implementación mínima de R1–R9 hasta el verde de la suite completa (`--basetemp` en el disco raíz).
4. `refactor:` si hace falta, con todo en verde.
5. Comprobación del bloque en el navegador y tanda de aceptación en la Pi.
