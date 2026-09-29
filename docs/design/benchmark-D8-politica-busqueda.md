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

- **Sonarr** — [`MonitoringOptions.cs` @develop](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/Tv/MonitoringOptions.cs)
  (enum: `all`, `future`, `missing`, `existing`, `recent`, `pilot`,
  `firstSeason`, `lastSeason`, `monitorSpecials`, `unmonitorSpecials`, `none`,
  más `unknown`, `latestSeason` obsoleto y `skip` interno),
  [`EpisodeMonitoredService.cs` @develop](https://github.com/Sonarr/Sonarr/blob/develop/src/NzbDrone.Core/Tv/EpisodeMonitoredService.cs)
  y la [wiki de la biblioteca](https://wiki.servarr.com/sonarr/library)
  ([fuente markdown](https://github.com/Servarr/Wiki/blob/master/sonarr/library.md),
  editada 2026-06-07; **la página no declara versión**, se ha cruzado con
  `develop` y con la última release v4.0.20.3014).
- **Kapowarr** (GPL-3.0), commit **`c191dda6617929c81292483a8cc07f631111dae2`**:
  `backend/internals/db.py:397,425` (`volumes.monitored`,
  `volumes.monitor_new_issues`, `issues.monitored`),
  `backend/base/definitions.py:446` (`MonitorScheme = all | missing | none`),
  `backend/implementations/volumes.py:617` (`apply_monitor_scheme`) y
  `~1547-1562`, [docs](https://casvt.github.io/Kapowarr/general_info/how_to_use/#monitoring).
- **Mylar3** (GPL-3.0), commit **`cdc94a44425b6f3f9cdb9b6e5f9d88ae2fee3316`**:
  `mylar/__init__.py:806` (estados por número), `mylar/updater.py:311-321` y
  `mylar/config.py:83-84` (`AUTOWANT_UPCOMING` / `AUTOWANT_ALL`),
  `mylar/helpers.py:1510-1545` (Continuing/Ended),
  [wiki de metadatos](https://github.com/mylar3/mylar3/wiki/Where-Mylar-gets-the-metadata-from).

**Cómo lo resuelve cada una:**

- **Sonarr** materializa el enum de **serie** sobre los episodios y deriva de ahí
  `Season.Monitored`. `missing` = **`!HasFile`** (con fichero o sin él, aireado o
  no); `future` = **`!AirDateUtc.HasValue || AirDateUtc >= UtcNow`** — es decir,
  **si la fecha es desconocida la cuenta como futura y la monitoriza**. Un
  segundo eje independiente, «Monitor New Items» (`all`/`none`), decide qué pasa
  con las temporadas que aparezcan después. Al conseguir el episodio **no se
  desmonitoriza**: pasa de Wanted a Cutoff Unmet si no llega al corte.
- **Kapowarr** tiene **dos ejes**: un *scheme* (`all`/`missing`/`none`) que es una
  **acción de un solo uso** («applied once, on save», y por defecto «Don't apply»)
  y `monitor_new_issues` por volumen, que sí es **persistente**. `missing` es «sin
  fichero» y se aplica **solo a los números que ya existen** en su BD. **No tiene
  `future`**: un número futuro sin fichero es «missing». Su fuente es ComicVine
  (`issue_number`, `cover_date`/`store_date`, `count_of_issues`), y los números
  ausentes de una respuesta se borran **solo si** `len(fetched) == issue_count`.
- **Mylar3** **no tiene monitor por serie**: lo querido son los estados por
  número (`Wanted`/`Skipped`/`Snatched`/`Downloaded`/…), `comics.Status` =
  Active/Paused, y los números nuevos entran como `Wanted` si
  `AUTOWANT_UPCOMING` (por defecto **sí**) o todos si `AUTOWANT_ALL`. Su
  «futuro» sale de la lista de números de la fuente; la wiki admite que ComicVine
  publica los datos **días después** de la salida.

**Supuestos de su modelo que NO valen en ZascArr:**

- **Que existe una lista completa de números por serie.** Aquí `Issue` solo tiene
  filas de lo que ya tienes: la lista de lo ausente hay que **calcularla**, y solo
  cuando la unidad está acreditada (los tomos de un manga no son grapas).
- **Que la fuente da fechas de lo que aún no ha salido.** No las pedimos: el
  enricher solo toca filas `Issue` existentes y no hay ninguna para números
  futuros. Sonarr puede permitirse contar una fecha desconocida como futura
  porque **su fuente publica el calendario**; aquí eso sería inventar.
- **Que el esquema se aplica una vez.** El de Kapowarr es una acción puntual;
  aquí hace falta una política **declarativa**, que se recalcula cada ciclo y por
  eso responde sola a «¿y los números que aparezcan después?».
- **Que «missing» es una consulta a la tabla de números.** En Kapowarr/Mylar3 la
  fuente les da la lista y `missing` es un `LEFT JOIN`; en ZascArr **no hay filas
  que consultar** para lo ausente.
- **Que la búsqueda es por número contra un catálogo.** Aquí es **texto** contra
  Prowlarr/foro: no se puede «pedir el 7» y garantizar que vuelva el 7.
- **Que la numeración es entera.** Sonarr razona con rangos de episodios; aquí hay
  Annuals, `.5` y crossovers (por eso `issue_number` es `VARCHAR` +
  `sort_order FLOAT`, decisión ya validada en CLAUDE.md §12).

**Adoptar / adaptar / descartar, con motivo:**

- **Adoptar:** el modelo de Sonarr — **la política decide qué se quiere y el ciclo
  de búsqueda es un paso aparte** —, con los cuatro valores que fija el backlog.
- **Adoptar:** **declarativa y recalculada en cada ciclo**, en vez del esquema
  *one-shot* de Kapowarr: es lo que contesta por sí solo al caso «aparecen números
  nuevos» (si te haces con el 4, `faltantes` deja de pedirlo sin que nadie toque la
  política).
- **Adaptar (`faltantes`):** se apoya en `huecos_de_serie()` y **reutiliza su
  veredicto de computabilidad** en vez de calcular por su cuenta. Si
  `computable=False` —manga: AniList cuenta capítulos y sus ficheros son tomos—,
  **no se genera nada** y se dice por qué (mismo criterio que #13 y que la frontera
  #14). Es lo que pedía la revisión: no restar tomos como si fueran grapas. La
  propia investigación lo refuerza: `missing` depende de que la fuente tenga el
  número, y en volúmenes españoles ComicVine a menudo no lo tiene.
- **Adaptar (`todos`):** todos los números `1..total_issues` **cuando es
  computable**, incluidos los que ya tienes (el caso de uso es querer otra
  copia/edición, que es donde engancharía D3). Tiene coste —N búsquedas—; lo acotan
  el `limit` por ciclo y el cooldown que ya existen.
- **Descartar (`futuros` por ahora):** **no computable**, y se declara.
  Consecuencias de implementación: el valor **entra en el tipo de Postgres desde
  la primera migración** (añadir valores a un ENUM después es incómodo), la
  columna se declara con **`values_callable`** —el fallo que ya mordió en B4— y
  el selector lo muestra **deshabilitado con su motivo**, no como una opción que
  parece funcionar y no hace nada. Sonarr y
  Mylar3 pueden calcularlo porque su fuente publica números y fechas que aún no han
  salido (Mylar usa incluso el *pull list* semanal); **aquí no se pide eso**. La
  lectura alternativa que se me ocurrió —«lo posterior al último número que
  tengo»— **se descarta a propósito**: no es «futuro», es «siguiente», y buscaría
  números que pueden ser de otra edición. Lo que haría falta para calcularlo de
  verdad: pedir a la fuente la lista de números de la serie con sus fechas (hoy no
  se pide) o que existan `Issue` con `release_date` futura (hoy no existen).
- **Añadir — `Wishlist.origen` (`manual`/`politica`):** sin distinguir el origen,
  «lo que ya estaba sigue» vale para lo que el coleccionista pidió y **no** para
  lo que generó la política: alguien que pasa de `faltantes` a `ninguno`
  esperando que pare seguiría viendo esos items en `WANTED` y buscándose. Con la
  columna: al dejar de querer un número, los items de origen `politica` **que no
  han empezado se retiran** con un estado propio (no se borran), los
  `DOWNLOADING` **no se tocan** (hay una descarga en marcha) y los `manual`
  **nunca** se tocan.
- **Añadir — `Wishlist.numero`:** un número que no tienes **no tiene fila
  `Issue`** (la propia ficha lo dice), así que un item generado no tendría a qué
  enlazar. Se guarda el número en el propio item **en vez de crear `Issue`
  vacíos**, que contaminarían el catálogo justo mientras B22 decide la identidad
  editorial. Y `check_completions` tiene que **emparejar por número**: si un item
  generado quedara ligado solo a la serie, cualquier `File` nuevo de esa serie lo
  cerraría (y cerraría **todos** los generados a la vez — verificado en `main`:
  `_is_fulfilled` da por cumplido un item de serie con cualquier `File` de la
  serie cuyo `imported_at >= added_at`, y un item **con `issue_id`** con
  cualquier `File` de ese issue, **sin criterio temporal**).
- **Descartar:** que un item **añadido a mano** quede silenciado por la política.
  Un item explícito es una orden del coleccionista; `ninguno` gobierna lo que
  ZascArr **genera**. (El backlog la describe como «leída antes de generar
  candidatos», que es exactamente esto.)
- **Descartar (`todos`, de momento):** **se reserva el valor en el tipo y NO se
  ofrece en el selector** hasta que D3 le dé un significado distinto de
  `faltantes`. Dos motivos. **(a)** Choca con el cierre: un item para un número
  que ya tienes lo daría por cumplido `_is_fulfilled` **sin buscar nada** (o
  marcaría `IMPORTED` en cuanto se enviara la descarga), porque el `File` que ya
  tenías lo satisface — haría falta un criterio nuevo («`File` posterior a la
  creación del item»), y **ése es el hueco de D3**. **(b)** Se aparta de la
  referencia: en Sonarr `all` monitoriza todo pero el ciclo solo busca lo que
  **no** tiene fichero (`missing = !HasFile`); volver a descargar lo que ya
  tienes es mejora de edición, no «tener todos los números». Con las reglas de
  hoy sería idéntico a `faltantes`, y dos opciones que hacen lo mismo confunden.
  Si algún día se ofrece, exigirá: confirmación en la UI diciendo cuántas
  búsquedas son y cuántas de números que ya tienes, el criterio de cierre nuevo,
  y una prueba de qué hace el importador con una segunda copia del mismo número.
- **Descartar:** buscar contra un catálogo para «resolver» un número. Eso es
  identidad/cobertura editorial (**B22**), no D8.
- **Descartar:** copiar `existing`/`recent` de Sonarr (90 días no significa nada
  con cadencia mensual/irregular) ni sus presets `pilot`/`firstSeason`/`lastSeason`
  (la jerarquía serie→temporada no traduce a grapa/tomo).

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
- **Generación acotada:** materializar `1..N` de golpe llenaría la lista con
  cientos de filas para una serie larga. Se genera **por lotes por ciclo, con un
  tope**, y repartiendo de forma justa entre series (no «la primera se lleva
  todo el cupo»).
- **Idempotencia en la base de datos, no solo en Python:** un **índice único
  parcial** sobre (serie, número) para los items de política con número. Dos
  ciclos solapados no pueden duplicar por una comprobación que solo existe en el
  código, y su ámbito **excluye los manuales**: si abarcara los manuales, quien
  añada a mano un número ya generado recibiría un error de integridad crudo.
- **El índice NO mira el estado, y por eso la generación REACTIVA en vez de
  insertar.** Limitarlo a los estados vivos dejaría fuera de la garantía a las
  filas `retirado`/`imported`/`failed`, que seguirían ocupando el hueco: pasar la
  serie a `ninguno` y volver a `faltantes` daría error de integridad, y un número
  importado cuyo fichero desapareció (`is_missing`) no se podría volver a querer.
  La generación usa `INSERT ... ON CONFLICT (series_id, numero) WHERE
  origen='politica' AND numero IS NOT NULL DO UPDATE` y **reinicia `status`,
  `added_at`, `download_ref`, `download_backend` y `last_error`**. Reiniciar
  `added_at` no es cosmético: el cierre compara `File.imported_at >=
  Wishlist.added_at`, así que sin reiniciarlo el cierre se comportaría mal.
  Queda **una sola fila por número**. Verificado contra PostgreSQL 15.
- **El backfill real es el `server_default`, no un `UPDATE`.** `ADD COLUMN ...
  NOT NULL DEFAULT 'manual'` ya rellena las filas existentes, así que un
  `UPDATE ... WHERE origen IS NULL` no tocaría nada. La prueba de la migración
  tiene que **sembrar filas antes de la 0015**, subirla y comprobar que quedan en
  `manual` con `numero` nulo.
- **`todos` y `futuros` se rechazan también en el servidor**, no solo
  deshabilitados en el selector: con los valores ya en el tipo, un `PATCH` a la
  API podría fijarlos. Validación explícita con 422 y motivo legible, y el campo
  declarado en `SeriesUpdate` (que es `extra=forbid`).
- **Estilo de la migración:** `postgresql.ENUM(..., create_type=False)` y no el
  `sa.Enum` genérico, que no tiene ese parámetro (nota del BACKLOG). Aquí los
  tipos se crean a mano y `add_column` no los recrea, pero la forma explícita
  evita que alguien lo rompa al refactorizar.
- **Límite conocido — arranque en frío de los alias (D8 + B13):** un alias local
  se aprende **solo** cuando el coleccionista asigna a mano un fichero desde
  Pendientes, y ese fichero tiene que existir ya. Con una serie de Comic Vine en
  inglés, `faltantes` activo y **ningún alias**, los releases en español se
  descartan y el item no avanza: **no llega nunca el fichero que enseñaría el
  alias**. La salida de los alias sirve cuando ya hay historial, no en la primera
  búsqueda de una serie recién dada de alta. Mitigación incluida: el motivo del
  item (D9) invita a lo que sí funciona —«si el release usa otro nombre para la
  serie, importa un fichero y asígnalo una vez en Pendientes»—. Alternativa
  futura, ya otra historia: un campo «otros nombres de esta serie» en su ficha.
  Y el tamaño real de este límite lo decidirá la comparación contra la base de
  datos real en la primera instalación, que hoy no se puede hacer.
- **Un item manual a nivel de serie + `faltantes`:** mientras exista uno vivo,
  **no se genera por número** para esa serie (si no, se buscaría la serie
  genérica *y además* cada número, quemando el doble). Se dice en la UI.

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
11. **Números que aparecen después:** con `faltantes`, si el ciclo siguiente ya
    tiene el número (importado a mano), **deja de generar** ese item sin tocar la
    política — la política es declarativa, no una acción de una sola vez.
12. **Numeración no entera:** un `Annual 1` o un `1.5` no entran en el rango
    `1..total_issues` y no se generan para ellos (misma regla de C2 que en los
    huecos).
13. **Un `File` de un número no cierra los items generados de otros números**
    (el cierre tiene que emparejar por número, no por serie).
14. **Pasar de `faltantes` a `ninguno`** retira los items generados pendientes,
    **no** los manuales y **no** los `DOWNLOADING`.
15. **Item manual de serie + `faltantes`** → no se generan duplicados por número.
16. **Sin acuse legal no se generan filas** ni se busca: generar también queda
    detrás de la puerta legal, no solo buscar.
17. **Una serie de 200 números respeta el tope por ciclo** y no acapara el cupo
    de las demás.
18. **Dos ciclos solapados no duplican** un item generado (índice único parcial,
    no solo la comprobación en Python).

**Decisión final / ADR:** no requiere ADR (feature de producto sobre esquema
propio; el criterio de computabilidad ya está decidido en #13). Entregable:
columna + migración `0015` + generación/filtro en `Orchestrator` + selector en
la ficha de serie.

---

## Notas de implementación (2026-09-29, ampliadas tras la revisión de #34)

Lo que el código decidió y no estaba cerrado en el diseño de arriba. Se anota
aquí porque cambia el contrato, no porque sea un detalle.

- **El predicado vive en `services/politica.py`** (`Querer`, `querer_de_serie`)
  y es la fuente única: lo consumen la generación, la retirada **y la ficha de
  serie**. No está en el orquestador a propósito — la ficha no debe instanciar
  un `Orchestrator` (con sus clientes de Prowlarr/Transmission/aMule) solo para
  preguntar si hay números que buscar. Devuelve `numeros` (lo que la política
  quiere ahora), `computable` y `motivo`.
- **La reactivación de la generación es SOLO `RETIRADO` e `IMPORTED`**
  (`ESTADOS_REACTIVABLES`), no «todo lo que no esté en vuelo». Corregido tras la
  revisión de #34: reiniciar un `FAILED` cada ciclo le borraba el `last_error`
  (el motivo de D9 desaparece justo cuando el coleccionista lo necesita),
  alternaba su estado entre `FAILED` y `WANTED` y **gastaba el lote** en items
  que ya existían — con 25 fallidos, los números nuevos no llegaban a generarse.
  Un `FAILED` ya lo reintenta `process_wishlist` tras el cooldown, y un
  `DOWNLOADED` está esperando al importador (reiniciarlo volvería a buscar algo
  que ya viene de camino). El `DO UPDATE` lleva `WHERE status IN
  ('retirado','imported')`, así que dos ciclos solapados tampoco lo reinician.
- **Un item manual de un NÚMERO concreto también ocupa ese número** (no solo el
  manual de serie que recogía el diseño). El índice único parcial no cubre los
  manuales, así que sin esta exclusión el coleccionista que ya pidió el nº 2 a
  mano recibiría además el nº 2 generado: la misma duplicación que la regla del
  item de serie, por otra puerta.
- **`todos` está implementado en el predicado** (`1..total_issues` cuando es
  computable, caso 6) pero **no se ofrece ni se acepta**: el selector no lo
  pinta y `SeriesUpdate` lo rechaza con 422. Queda listo para cuando D3 decida
  el criterio de cierre, que es lo único que falta para poder ofrecerlo.
- **La retirada es asimétrica respecto a la generación.** Generar espera al
  siguiente ciclo (es lo declarativo). Retirar se aplica **al guardar la
  política**, solo para esa serie y con el mismo `UPDATE` atómico: cuando el
  coleccionista pide parar, no puede seguir buscándose hasta una hora. La
  sentencia se comparte (`services/politica.py::retirar_de_serie`), así que da
  igual quién llegue antes.
- **La retirada solo toca `WANTED`/`FAILED`.** `SEARCHING` queda fuera además de
  `DOWNLOADING`: es transitorio (hay una búsqueda en vuelo) y marcarlo `retirado`
  sería mentir (D9). Un item varado en `SEARCHING` por una caída del proceso es
  un problema previo a D8 y no se resuelve aquí.
- **La ficha de serie no lista un chip por número.** Resume («faltan 200; se
  generan hasta 25 por ciclo, repartidos entre las series con política activa»),
  y solo pinta los chips si son 12 o menos. Además dice si el aviso legal está
  pendiente (sin acuse el ciclo no genera ni busca: prometer búsquedas sin
  decirlo sería engañar) y cuántos números están retirados.
- **Los items `retirado` se ocultan del listado de deseos** pero **no se
  borran**: pasar una serie de 200 números a `ninguno` no puede llenar la
  pantalla de filas muertas. Siguen en la BD y en la API (`?status=retirado`), y
  la ficha de serie dice cuántos hay.
- **Ventana conocida (generación ↔ dos ciclos solapados):** entre el `SELECT`
  que mira qué falta y el `INSERT ... ON CONFLICT` no hay bloqueo, así que un
  ciclo podría intentar crear una fila para un número que el otro acaba de
  reclamar. La resuelve la BASE: índice único parcial (una sola fila por número)
  y `DO UPDATE ... WHERE status IN ('retirado','imported')` (si la fila ya está
  `WANTED`/`SEARCHING`/`DOWNLOADING`/`DOWNLOADED`/`FAILED`, no se toca).
  Verificado con dos conexiones y `COMMIT` real en
  `tests/test_politica_d8_pg.py::test_dos_ciclos_solapados_de_verdad_no_duplican`.
- **Ventana conocida (guardar `ninguno` justo a mitad de ciclo):** si el
  coleccionista guarda `ninguno` mientras el ciclo ya calculó sus planes con
  `faltantes`, ese ciclo puede generar items que la pasada siguiente retira (la
  retirada al guardar solo actúa sobre lo que había en ese momento, y la
  generación en vuelo no lo ve). Se cura sola en menos de un ciclo (≤ 1 h por
  defecto) y no deja estado incorrecto: los items acaban `retirado`.
- **Imprecisión conocida del contador `generados`:** `_materializar` no devuelve
  si el upsert cambió algo, así que un ciclo que pierde una carrera cuenta como
  generado un item que no creó. Es solo ruido de log y del cupo por ciclo —sin
  efecto en los datos— y no se corrige aquí.
- **Pruebas:** el comportamiento completo contra PostgreSQL 15 está en
  `tests/test_politica_d8_pg.py`; el `WHERE` de las dos sentencias, las ramas sin
  BD y el flujo con `FakeSession` en `tests/test_orchestrator.py`; el selector y
  el efecto inmediato de la retirada, en `tests/test_web_series.py`. La
  migración con sembrado previo, en `tests/test_migracion_d8_pg.py`.
- **Límites abiertos que dependen de medir con la biblioteca real** (primera
  instalación; hoy no hay BD real en este entorno):
  - **Arranque en frío de los alias (B13 + D8):** un alias solo se aprende cuando
    ya existe un fichero que asignar a mano, así que la *primera* búsqueda de
    una serie nueva (sobre todo si está catalogada en inglés y los releases son
    en español) se queda sin candidatos. El motivo del item (D9) invita a lo que
    sí funciona; un campo «otros nombres de esta serie» sería otra historia.
  - **Hipótesis sin medir:** cuánto pesa ese desajuste inglés/español sobre una
    biblioteca real. Es exactamente lo que decidirá si el arranque en frío es un
    caso raro o el caso normal.
  - **Rango `1..total_issues`:** `compute_missing_issues` (C2) asume numeración
    que empieza en el #1. Una serie que arranca en el #0 pediría un #5 inexistente
    y nunca pediría el #0. Es previo a D8 (vive en `huecos_de_serie`), pero D8 lo
    hereda; medirlo con la biblioteca real dirá si hace falta una regla de
    numeración por serie.
