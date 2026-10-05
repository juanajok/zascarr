# Auditoría B14: ¿qué aporta el nombre de la carpeta, y qué riesgo trae?

> Revisión del 2026-10-05 (punto 3 del orden del MVP): breve auditoría del código y prueba sobre una
> biblioteca con **nombres reales**, separando correcto / ambiguo / incorrecto. **No cambia ninguna lógica de
> producción.** Las cifras son de UNA biblioteca de UN coleccionista y las etiquetas de «correcta / ambigua /
> incorrecta» las puse **leyendo los nombres, sin catálogo**: son un juicio revisable, no una verdad medida. La
> tabla carpeta por carpeta lleva nombres reales y **no se publica** (queda en el equipo de quien midió); aquí
> solo hay recuentos y formas.
>
> **Versión de las cifras.** Se midieron con el parser **anterior a la PR #81** (que corrige el «no» final leído
> como «nº»: `Inferno`, `La Cosa del Pantano`). Se conservan como **evidencia histórica de esa versión**: no se
> han recalculado. El efecto de #81 sobre este corpus está acotado y medido aparte (14 de 1.542 nombres pasan a
> ser correctos, ninguno empeora), y aquí solo afecta a la columna «el nombre también falla».

## Qué hace hoy el código (leído, no supuesto)

- **La carpeta no se usa en ningún sitio.** `parse_comic_filename(nombre)` recibe solo el nombre;
  `SeriesMatcher.decide(triage, extractor)` solo ve `triage.path.name`; `Importer` y `LibraryAdopter` llaman a
  `_triage_and_match`, que tampoco la mira. Las únicas pistas de contexto que existen son la **cohorte**
  (`core/cohort.py`, solo sobre nombres) y el **alias local** (`local_aliases`, decidido por una persona).
- **El matcher solo enlaza con series que YA existen** en el catálogo (`find_series` / alias). La adopción
  (`LibraryAdopter`) registra los archivos en su sitio y los deja sin serie si no hay coincidencia; **no crea
  series**. Las series nacen de Descubrir (`DiscoveryService.get_or_create_series`), de una en una.
  Consecuencia para el MVP: sin series, ninguna señal —ni el nombre ni la carpeta— puede enlazar nada.
  **Contexto ya comprobado en la instalación de producción** (consulta de solo lectura, 2026-10-05): tiene
  **5 series**, **14 archivos registrados** (todos sin Issue), **1.542 visibles** en la carpeta y **ningún marcador
  de adopción**. El catálogo, por tanto, **no estaba vacío**, y el bloqueo confirmado no era «reconocer mejor»
  sino que con catálogo previo **el registro de la biblioteca no se ofrecía** (se corrige en la PR #83). La
  cobertura de esas 5 series sobre los nombres de la biblioteca sigue siendo **limitada** (no cubren los 14
  archivos ya registrados), así que crear series a partir de las carpetas sigue siendo un paso necesario después.
- B15 ya separó «la carpeta que no es una serie» como caso conocido (autor, saga, crossover); sigue abierto.

## Método

`scripts/medicion/medir_carpetas.py` (solo lectura, sin BD) recorre una biblioteca, parsea cada nombre con el
parser de producción y lo compara con la carpeta contenedora (el primer nivel, la tradición, se descarta). No
decide ninguna serie: clasifica la relación entre las dos señales. Después revisé **todas** las discrepancias a mano.

Biblioteca medida: **1.542 archivos** (`.cbz`/`.cbr`), 90 % con la forma `Tradición/Serie/archivo`, 6 % con un
nivel más, 3 % sueltos en la tradición.

## Resultado

| Relación entre el título del nombre y el de la carpeta | Archivos | % |
|---|---:|---:|
| Iguales (la carpeta no añade nada sobre la serie) | 972 | 63,0 % |
| El título del nombre está dentro del de la carpeta (la carpeta lo **refina**: volumen, año, editorial, saga) | 253 | 16,4 % |
| El título de la carpeta está dentro del del nombre | 58 | 3,8 % |
| **Distintos** | 207 | 13,4 % |
| Sin carpeta de serie (sueltos en la tradición; ahí B14 no puede ayudar) | 52 | 3,4 % |

### Las 518 discrepancias, revisadas a mano

| Veredicto sobre «usar la carpeta como serie» | Archivos | En qué consisten |
|---|---:|---|
| **Correcto** | 285 | la carpeta es la serie y el nombre la refina o la contradice por error (autor como título, `WildC A T S`, título cortado) |
| **Misma serie con otro título** | 34 | la carpeta y el nombre nombran la misma serie en idiomas o ediciones distintas (`Top Ten`/`Top 10`, `Fallen Angel`/`El Ángel Caído`) |
| **Ambiguo** | 76 | la carpeta es un arco, un crossover, una colección o un spin-off; nadie puede decidir sin catálogo |
| **Incorrecto** | 123 | la carpeta **no es la serie del archivo** |

Las **123 carpetas-que-mienten (8,0 % de la biblioteca)** son de cuatro formas, todas reales y todas ya
descritas en el backlog: **autor** (`Carlos Giménez`, en dos carpetas casi gemelas: 52 archivos y 26 obras distintas por carpeta), **contenedor**
(`_Specials`, `spin offs`, `_Omnibus`), **orden de lectura / crossover** (`Flash (1987)` con `Green Lantern`,
`Impulse`, `Justice League…` dentro; `Green Lantern - Saga de Geoff Johns` con `Green Lantern Corps`) y
**arco dentro de una serie** (`Locas - La muerte de Speedy` sobre archivos que son `Locas`).

**El nombre también falla**, y la carpeta lo corrige: un autor leído como título (`Hiroaki Samura`, 30;
`Katsuhiro Otomo`, 7), `WildC A T S` (3) y un **defecto del parser independiente de B14**: el «no» final de
`Inferno 01` y `La Cosa del Pantano 01` se leía como el marcador «nº 01» y el título quedaba en `Infer` y
`La Cosa del Panta` (14 archivos). Se corrige en una PR aparte, con su prueba de regresión.

### La prueba que decide: ¿vale una regla por carpeta?

Se probó la heurística más natural —«la carpeta es una serie si la mayoría de sus archivos coincide con ella»—
contra los veredictos de arriba. **En este corpus no basta**: con los umbrales ensayados (50, 60, 70 y 80 %), 5 de
las 16 carpetas «incorrectas» **pasan** (`Flash (1987)`: 89 % de acuerdo; `20th Century Boys`: 92 %; `Locas…`, `Marvel-Inhumanos`,
`_Omnibus`: 100 %). Son ~38 archivos (2,5 % de la biblioteca) que una regla por carpeta enlazaría **en
silencio a una serie equivocada**, aun con el mejor umbral; y a la vez rechazaría 11 de 95 carpetas buenas.
Una carpeta puede ser una serie casi entera y esconder en su interior series ajenas; solo el nombre de cada
archivo lo delata.

**Alcance de la conclusión.** Se mide una biblioteca, una heurística (la mayoría de acuerdo) y cuatro umbrales: lo
que queda demostrado es que **esa heurística y esos umbrales no garantizan ausencia de errores en este corpus**,
no que ninguna regla por carpeta pueda funcionar jamás. La política conservadora que se propone abajo (la carpeta
sugiere y agrupa, no asigna sola) se sostiene por el coste de equivocarse en silencio —el patrón de la medición del
2026-09-25: una heurística floja, automatizada, se convierte en dato persistente—, no por una imposibilidad.

## Lo que la carpeta SÍ aporta

1. **Desambiguar**, no decidir: `Superman Vol2 (Ed.Zinco)(1987-96)` frente al nombre `Superman` es la diferencia
   entre dos series con el mismo título. Es el 16 % «refina» de la tabla, y casi todo es correcto.
2. **Agrupar**: 32 de las 111 carpetas con serie tienen ≥ 10 archivos. Confirmar «estos 30 archivos son *La
   Espada del Inmortal*» **una vez** y no treinta es el ahorro real para «clasificar cientos de CBZ sin ayuda
   técnica», con el número de cada archivo leído de su propio nombre.
3. **Rescatar al nombre** cuando este falla (autor como título, título cortado).

## Decisión propuesta (para que la acepte la revisión)

1. **La carpeta nunca asigna sola.** Ni como sustituto del nombre ni como desempate silencioso. La decisión
   manual y los metadatos fiables (ComicInfo) siguen mandando, en ese orden.
2. **La carpeta es una señal que se MUESTRA y se valida contra el catálogo**: (a) en Pendientes, como
   sugerencia explícita («la carpeta se llama X»), con su evidencia; (b) como agrupación para el lote (V5/V6b),
   donde una persona confirma la serie de la carpeta y el número sale del nombre de cada archivo.
3. **Una carpeta con archivos de títulos distintos no se propone como serie del grupo** (autor, contenedor): se
   mide por archivo, no por carpeta (ver la prueba). Se limpian volumen, año, editorial y «Saga de…» antes de comparar.
4. El catálogo de producción **no está vacío** (5 series) y ya se sabe cuál era el bloqueo (el registro con
   catálogo previo, PR #83). Después del registro, las series que faltan hay que proponerlas/crearlas con
   confirmación humana (p. ej. a partir de las carpetas); B14 se subordina a ese paso y a la política de arriba.

## Límites

Una biblioteca, un coleccionista, 1.542 archivos; etiquetas puestas por mí leyendo nombres; sin catálogo ni
BD; la segunda biblioteca del backlog (jerárquica, hasta 5 niveles) **no se midió**; las cifras de «correcto»
suponen que una persona confirmaría la propuesta. No se midió cuántos Pendientes resolvería un candidato por
carpeta, porque eso exige un catálogo.
