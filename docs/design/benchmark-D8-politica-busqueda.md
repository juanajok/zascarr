# Ficha de benchmarking — D8: política de búsqueda por serie

> Ficha según `docs/design/benchmark-referencias.md` (CLAUDE.md §13). El riesgo
> aquí no es la UI: es **decidir qué se busca** en nombre del coleccionista y
> **inventar una lista de números** cuando los datos no dan para calcularla.

**Historia / problema observado:**
D8 — hoy la lista de deseados es una lista plana de items que el coleccionista
añade a mano (uno por serie o por número) y el orquestador los busca todos sin
distinción. No hay forma de decir «de esta serie quiero todo», «solo lo que me
falta» o «nada». El backlog pide un campo `wishlist_policy` por serie
(`ninguno`/`faltantes`/`futuros`/`todos`) leído por `Orchestrator.process_wishlist`
**antes de generar candidatos**.

**Datos reales y medición de partida (código, no suposiciones):**

- `wishlist_policy` **no existe** en el esquema. Es columna nueva.
- La unidad de trabajo del orquestador es el `Wishlist` (item), no la serie:
  `process_wishlist` selecciona items `WANTED`/`FAILED` con cooldown y llama a
  `_search_and_rank(item)`, que construye una **consulta de texto** (`_build_query`):
  `series.title` y, si el item tiene `issue_id`, `title + " " + issue_number`.
  La búsqueda va a Prowlarr/foro; **no hay búsqueda por número contra un catálogo**.
- **No existen filas `Issue` para los números que no tienes.** El enricher solo
  enriquece `Issue` ya existentes (`Issue.comic_vine_id IS NULL`); nada crea
  filas para números ausentes. Por tanto «los que me faltan» **no es una
  consulta a `issues`**: sale del cálculo de huecos.
- Ese cálculo ya existe y ya dice cuándo **no** se puede hacer:
  `api/series.py::huecos_de_serie()` devuelve `Huecos(faltantes, computable, motivo)`.
  `computable=False` cuando la serie no tiene `total_issues` o cuando su
  `metadata_source` no está en `UNIDAD_DE_GRAPA` (hoy solo `comic_vine`): AniList
  cuenta **capítulos** y sus ficheros son **tomos**, así que restarlos sería
  inventar. Además `_numero_de_grapa()` exige `format=SINGLE_ISSUE` y número
  entero, de modo que un ómnibus #12 no tapa la grapa #12 (regla de C2).
- `CheckCompletions`/`Orchestrator.check_completions` cierran el círculo
  «descargado → en tu biblioteca» **por la existencia de un `File` enlazado al
  item**, así que una búsqueda sin fila `Wishlist` no se podría ni seguir ni
  cerrar. Cualquier generación automática tiene que **materializar items**.

**Referencias consultadas (URL, versión/commit):**

- **Sonarr — «Monitor»**: es la referencia del modelo. Monitoriza a nivel de
  **serie** con una elección que se traduce en «qué episodios pasan a
  *wanted*», y admite combinarla con la monitorización por temporada/episodio.
  La clave para ZascArr: **el monitor no busca, decide qué se quiere**; el ciclo
  de búsqueda es un paso aparte sobre lo querido.
- **Kapowarr / Mylar3** (GPL-3.0), gestores de cómic: ambos tienen un concepto
  de «lo que quiero» por serie; Kapowarr trabaja sobre el catálogo de ComicVine
  (que sí le da la lista de números y sus fechas) y Mylar3 sobre su `wanted`
  list. **No he podido verificar los nombres exactos de sus opciones ni su
  comportamiento ante datos ausentes**: la búsqueda web no está disponible en
  este entorno y las consultas de documentación que intenté no devolvieron el
  detalle. Queda dicho aquí en vez de afirmarlo de memoria (procedimiento §3:
  «no lo encontré» no es «no existe»).
- **El propio proyecto** es la referencia que más pesa aquí, porque la
  diferencia con Sonarr es de **datos disponibles**, no de diseño:
  `docs/BACKLOG.md` (nota «Huecos fiables», #13) fija el criterio de
  computabilidad, y la nota de fronteras (#14) prohíbe deducir cobertura
  editorial del número.

**Cómo lo resuelve cada una:**

- **Sonarr:** monitor por serie (`All`, `Future`, `Missing`, `Existing`, `First
  Season`, `Last Season`, `Pilot`, `None`, y combinaciones con temporadas) y
  **genera los *wanted* a partir del catálogo**, que le da la lista completa de
  episodios con fechas de emisión. «Future» = aún no emitido, y **solo es
  calculable porque la fuente publica el calendario**.
- **Kapowarr/Mylar3:** mismo patrón (catálogo → lista de números → qué se
  quiere), con ComicVine/otras fuentes como origen de la lista.

**Supuestos de su modelo que NO valen en ZascArr:**

- **Que existe una lista completa de números por serie.** Aquí `Issue` solo
  tiene filas de lo que ya tienes: la lista de lo ausente hay que **calcularla**,
  y solo se puede cuando la unidad está acreditada (los tomos de un manga no
  son grapas).
- **Que la fuente da fechas de lo que aún no ha salido.** No las pedimos: el
  enricher solo toca filas `Issue` existentes, y no hay ninguna para números
  futuros. **«Futuros» no es calculable hoy** y no se va a adivinar.
- **Que «monitorizar» es un booleano por serie.** Aquí convive con una lista de
  deseados hecha a mano, que es una petición **explícita** del coleccionista y no
  puede quedar silenciada por un ajuste.
- **Que la fuente devuelve lo que se pide.** La búsqueda es de **texto** contra
  Prowlarr/foro; no se puede «pedir el número 7» y garantizar que lo devuelto
  sea el 7. La política decide **qué consultas se lanzan**, no qué llega.

**Adoptar / adaptar / descartar, con motivo:**

- **Adoptar:** el modelo de Sonarr — **la política decide qué se quiere y el
  ciclo de búsqueda es un paso aparte** —, con los cuatro valores que fija el
  backlog.
- **Adoptar:** materializar los deseados como filas `Wishlist` (necesario para
  seguir la descarga y cerrarla con `check_completions`), y **de forma
  idempotente**: no se crea otro item para un número que ya tiene uno vivo.
- **Adaptar (`faltantes`):** se apoya en `huecos_de_serie()`, **reutilizando su
  veredicto de computabilidad** en vez de calcular por cuenta propia. Si
  `computable=False`, **no se genera nada** y se dice por qué (mismo criterio que
  #13 y que la frontera #14). Es literalmente lo que pedía la revisión: no
  restar tomos como si fueran grapas.
- **Adaptar (`todos`):** todos los números `1..total_issues` **cuando es
  computable**, incluidos los que ya tienes (el caso de uso es querer otra
  copia/edición). Tiene coste: N búsquedas; lo acotan el `limit` por ciclo y el
  cooldown que ya existen.
- **Descartar (`futuros` por ahora):** **no computable**, y se declara. La
  alternativa que se me ocurrió —«lo posterior al último número que tengo»— **se
  descarta a propósito**: no es «futuro», es «siguiente», y buscaría números que
  pueden ser de otra edición. Lo que haría falta para calcularlo de verdad:
  pedir a la fuente la lista de números de la serie con sus fechas (hoy no se
  pide) o que existan `Issue` con `release_date` futura (hoy no existen).
- **Descartar:** que un item **añadido a mano** quede silenciado por la
  política. Un item explícito es una orden del coleccionista; `ninguno` gobierna
  lo que ZascArr **genera**, no lo que él pide. (El backlog describe la política
  como «leída antes de generar candidatos», y eso es exactamente esto.)
- **Descartar:** buscar contra un catálogo para «resolver» un número. Eso es
  identidad/cobertura editorial (**B22**), no D8.

**Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi):**

- **No mentir:** una política que no se puede aplicar **se declara** con su
  motivo (el `motivo` que ya produce `huecos_de_serie()` y un motivo propio para
  `futuros`). Nunca se enseña una lista de números inventada.
- **Nada por defecto:** la migración deja `ninguno` en las series existentes;
  sin opt-in explícito por serie, D8 **no genera ni busca nada nuevo**. Se
  respeta el marco legal ya existente (`is_acknowledged` sigue siendo la puerta
  del ciclo).
- **Lo del coleccionista no se toca:** los items añadidos a mano siguen su
  curso; la generación automática solo **añade** items que no existían, nunca
  borra ni cambia los que hay.
- **Coste Pi:** una consulta agregada por serie con política activa y sin
  búsquedas nuevas si el cálculo no es computable; el número de búsquedas por
  ciclo queda acotado por el `limit` de `process_wishlist`.

**Casos de prueba antes de implementar:**

1. `faltantes` con cálculo computable (`comic_vine`, `total_issues=5`, tiene 1 y 3) → se generan items para 2, 4 y 5; **no** para 1 y 3.
2. `faltantes` con `computable=False` (AniList/manga) → **no se genera nada** y el motivo es el de `huecos_de_serie()`; no se inventan números.
3. `faltantes` con ómnibus del mismo número → el ómnibus **no** tapa la grapa (regla de C2, vía `_numero_de_grapa`).
4. `futuros` → no se genera nada y el motivo dice que no es computable.
5. `ninguno` → no se genera nada y los items a mano **siguen buscándose**.
6. `todos` con `total_issues=5` y 1,3 en disco → se generan 1..5.
7. **Idempotencia:** dos ciclos seguidos con `faltantes` no duplican items.
8. Un item vivo (WANTED/SEARCHING/DOWNLOADING) para ese número **no** se duplica; uno `DOWNLOADED`/`FAILED` sí se reutiliza en vez de crear otro.
9. `process_wishlist` no genera ni busca si no hay acuse legal.
10. La UI de serie muestra la política, los números que faltan y el motivo cuando no es computable.

**Decisión final / ADR:** no requiere ADR (feature de producto sobre esquema
propio; el criterio de computabilidad ya está decidido en #13). Entregable:
columna + migración `0015` + generación/filtro en `Orchestrator` + selector en
la ficha de serie.
