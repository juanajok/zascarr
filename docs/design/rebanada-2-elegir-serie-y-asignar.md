# Ficha técnica — Rebanada 2: elegir o crear la serie correcta y asignar con vista previa y confirmación

> Desarrolla las rebanadas 2-4 de `docs/design/ficha-propuestas-desde-carpetas.md` tras cerrar la rebanada 1 (`docs/design/rebanada-1-superficie-de-revision.md`, en `main` desde `5645628`).
> **Esta ficha no implementa nada**: fija el problema, los contratos y las pruebas de aceptación **antes** de escribir código. **No autoriza** crear series, asignar archivos ni tocar producción.
> Estado: **propuesta para revisión**. Las decisiones abiertas (D0-D10) están al final, con recomendación.

## Historia

Como coleccionista con cientos de CBZ/CBR ya registrados «en su sitio» pero **sin serie**, quiero buscar en las fuentes la serie y la edición correctas, crearla (o reutilizar una que ya tengo),
ver **qué pasará con cada archivo** y confirmarlo, para que mis tebeos queden clasificados **sin que nadie me lo haga a escondidas**.

## El bloqueo original

Primer registro real en producción (2026-10-05, ver `BACKLOG.md`): **1.322 registros «Sin serie»** (1.308 + 14 filas previas), **17 con serie sugerida** pero sin `Issue`, y **solo 5 series locales**:
no existen `Superman`, `Patrulla-X`, `Nuevos Mutantes`, `The Boys` ni `Carlos Giménez`. La rebanada 1 ya **muestra** esos grupos y por qué; la persona **no puede hacer nada con ellos**:

- «Por revisar» solo sabe **asignar un archivo a una serie que ya existe**, uno a uno (`POST /ui/pendientes/{id}/asignar`).
- «Descubrir» sabe **buscar en fuentes y crear una serie suelta**, pero no conoce los archivos: la persona tiene que buscar a mano, crear, ir a «Por revisar» y asignar **cada tebeo** otra vez.
- Nada une las dos cosas ni deja ver, **antes de moverse nada**, qué le pasaría a cada archivo.

## Qué existe hoy (verificado leyendo el código en `main`)

| Pieza | Dónde | Qué hace | Qué le falta para esta historia |
|---|---|---|---|
| Superficie de revisión | `services/revision_carpetas.py`, `/api/revision/carpetas`, `/ui/pendientes/carpetas` | Grupos por carpeta, estados, señales por archivo contra **su** candidata, `senales[].archivos` | Ninguna acción. Las señales se calculan contra la candidata **guardada** de cada archivo, no contra una serie que la persona elija ahora |
| Buscar en fuentes | `services/discovery.py::DiscoveryService.search` | Consulta en paralelo Comic Vine, AniList, Tebeosfera y GCD; tolera que una falle; devuelve avisos en español | Busca por texto libre: no parte de un grupo. No dice si ya existe una serie local ni si la carpeta corrobora o contradice el resultado |
| Crear serie desde una fuente | `web/discovery.py::crear` → `get_or_create_series` | Crea la `Series` con el id externo; **no duplica por id externo** | **No valida colisiones por título/año.** **Confía en `title`, `start_year`, `description` y `cover_url` que llegan en campos ocultos del formulario** (ver H1). Comprobar-y-luego-insertar sin tratar la carrera |
| Crear serie a mano | `api/series.py::create_series` (`POST /api/series`) | Crea una `Series` con los campos del esquema | Sin ninguna comprobación de colisión; sin registro de por qué existe |
| Asignar un archivo | `services/asignacion.py::AsignacionService.asignar(file_id, series_id, issue_number, aprender_alias=True)` | **Recuperable** (ADR 0006): copia verificada → publica → confirma en una transacción → retira el origen; reconcilia al arrancar; `colision_edicion`; crea el `Issue` si no existe | Es **de un solo archivo** y **no tiene vista previa**: `_preparar` reserva el destino (escribe) y hace el hash. Calcula la ruta con `build_library_path` (pura) |
| Textos de resultado | `web/pendientes.py::RESPUESTAS` | Un texto en español por `EstadoResultado` | Pensados para un archivo; hay que agregarlos para un lote |
| Ejecución en segundo plano | `services/registro_biblioteca.py` | Una ejecución por proceso (`--workers 1`), progreso consultable, sin reanudar sola, causa saneada | Es del registro; no hay un equivalente para asignar |
| Token firmado | `services/orchestrator.py::crear_token_candidato` / `verificar_token_candidato` (sobre `auth.sign_token`) | El formulario solo reenvía un token HMAC con caducidad; nada viaja suelto | Solo lo usa Deseados |
| Modelo de ediciones | ADR 0003 (**Propuesto**) | Edición = espacio de numeración; sello = atributo | **No hay tabla `editions`**: hoy la edición vive en `Issue.format` (B15, `edition_kind` del nombre del archivo) y, entre fuentes, en **el resultado concreto elegido** (una ficha de Tebeosfera ya es una edición) |
| Clientes de fuentes | `services/{comic_vine,anilist,tebeosfera,gcd}.py` | Solo **`search_series`** | **Ninguno tiene «obtener por id»** |

## Qué cambia respecto a la ficha anterior (D0: a decidir, no a dar por hecho)

La ficha de propuestas ordenó las rebanadas 2-4 así: **2** crear serie a mano (sin fuentes) → **3** asignar el grupo → **4** Descubrir como fuente opcional.
La revisión pide ahora **centrar la rebanada 2 en el bloqueo original**: buscar en fuentes, elegir o crear la serie y **preparar una asignación con vista previa y confirmación**, separando cinco bloques.
Es **otro orden**, así que se deja escrito en lugar de resolverlo en silencio:

| | Orden anterior | Orden pedido ahora |
|---|---|---|
| Primero | Crear a mano, sin red | Descubrir en fuentes desde el grupo |
| A favor | Cada PR sirve sin red ni claves; no depende de scrapers frágiles; avanza ya con 5 series locales | Datos de calidad e **id externo** (dedupe determinista), portada y año; resuelve «elegir edición» |
| En contra | La persona teclea título, año y tradición de cosas que una fuente le daría; no resuelve «elegir edición» | Depende de red, de la clave de Comic Vine y de los límites de cada fuente; Tebeosfera es scraping; un título genérico («Batman») devuelve resultados malos |

**Recomendación:** adoptar el orden pedido, **pero** conservar «crear a mano» como **camino de primera clase** dentro de 2b (es la misma candidata con origen `manual`): sin red, sin clave o con las fuentes apagadas la persona sigue pudiendo avanzar. Es la prueba nº 10 de la ficha anterior.

## Referencias consultadas (CLAUDE.md §13; lectura de código, no ejecutadas)

Versiones fijadas: **Sonarr** `v5-develop` @ `da99063` (src/NzbDrone.Core/Tv/AddSeriesService.cs, Validation/Paths/SeriesExistsValidator.cs y SeriesPathValidator.cs), **Kapowarr** @ `c191dda` (`backend/implementations/volumes.py`, `Library.add`),
**Kaizoku** `oae/kaizoku` @ `fc86b7d` (`router/manga.ts::add`, asistente de añadir; archivado). **Mylar3 no se ha leído para esta rebanada** (sí en la ficha de propuestas); Suwayomi y Aidoku se leyeron allí, no se releen aquí.
Licencias: Sonarr y Kapowarr GPL-3.0, Kaizoku MIT: **solo como patrón, no se copia código** (§13).

| Qué hacen | Sonarr | Kapowarr | Kaizoku |
|---|---|---|---|
| Identidad al añadir | **Id externo** (TVDB); «This series has already been added» por id | **Id externo** (CV); `VolumeAlreadyAdded(comicvine_id)` **antes** de escribir | **Título** (`Manga.title` único); el id de AniList no vive en la BD |
| ¿Confía en lo que manda el cliente? | **No**: `AddSkyhookData` **vuelve a pedir** la serie por id y falla si no existe | **No**: `fetch_volume(comicvine_id)` **vuelve a pedir** el volumen | Vuelve a resolver por título exacto y **se niega si hay 0 o varios** resultados |
| Validación de destino | `SeriesPathValidator`: «ya hay otra serie con esa ruta» | `RootFolderNotFound`; carpeta de volumen generada | No comprueba la carpeta de destino; la muestra, sin poder editarla |
| Lote | Omite duplicados por id y por *slug* dentro del mismo lote; `ignoreErrors` | Un volumen por llamada | Un asistente de pasos, un título cada vez |
| Preselección | Preselecciona el primer resultado | Elige el mejor por reglas | Ninguna: la persona busca y elige |

**Adoptar:** identidad por **id externo** y comprobar duplicado **antes** de escribir (Sonarr, Kapowarr); **no confiar en los datos del cliente** (Sonarr y Kapowarr lo hacen volviendo a pedir por id; ZascArr ya tiene el patrón del **token firmado** de Deseados); negarse ante la ambigüedad (Kaizoku); comprobar la **ruta de destino** antes de confirmar (Sonarr `SeriesPathValidator`).
**Adaptar:** las series **locales sin id externo** (las 5 que ya existen) no se pueden deduplicar por id: se usa `title_norm` + año ±1 + tradición, **como aviso que la persona resuelve**, no como regla silenciosa. Volver a pedir por id exigiría escribir «obtener por id» en los cuatro clientes: se propone el **token firmado** (D9) y dejar «obtener por id» para después.
**Descartar:** preseleccionar el primer resultado (Sonarr); elegir «el mejor» (Kapowarr); identidad por título (Kaizoku); monitorizar/buscar automáticamente al añadir (Sonarr).

## Alcance y no-alcance

**Dentro:** buscar en fuentes **desde un grupo**; elegir o crear la serie; validar colisiones; **vista previa** de lo que pasaría con cada archivo; **confirmación explícita**; asignar **por el servicio recuperable existente**, en lote, con progreso.
**Fuera (sin excepción):** duplicados (~200 grupos de copias idénticas, **D5**) y las 14 referencias obsoletas (la vista previa las **bloquea** y las llama «registros pendientes de verificar»; no hay acción); el modelo de ediciones del ADR 0003; fusionar, renombrar o borrar series; tocar el contador del menú (**D2**); desplegar en producción; cualquier asignación **automática** o **preseleccionada**.

## El flujo, en cinco pasos separados

```
 grupo (rebanada 1)
   └─ A. Descubrir     (red, solo a petición; no escribe)         → candidatas, ninguna elegida
        └─ B. Elegir o crear la serie  (escribe SOLO el catálogo)  → series_id   ← confirmación 1
             └─ C. Vista previa de la asignación (solo lee; stat de rutas) → qué pasaría con cada archivo
                  └─ D. Confirmar y asignar (mueve ficheros, recuperable)  → informe honesto   ← confirmación 2
 E. Conflictos y fuera de alcance: transversal (nada se preselecciona; duplicados y obsoletas no se tocan)
```

**Dos confirmaciones, no una:** crear la serie es del **catálogo** (reversible mientras no tenga asignaciones); asignar **mueve ficheros** (ADR 0006). Si la asignación falla, la serie ya creada no se pierde ni se repite.

## A. Descubrimiento y selección de edición desde fuentes (sin depender de una serie local)

**Entrada:** un grupo de la rebanada 1 (`clave`) y una **consulta** propuesta a partir de la carpeta limpia (`carpeta_limpia.titulo`) y el título dominante de los nombres; **editable**. La búsqueda **no se lanza sola**: solo con el botón «Buscar en las fuentes» (la red solo se usa a petición).

**Qué hace:** reutiliza `DiscoveryService.search` (las fuentes ya encendidas, tolerando que una falle). Por cada resultado añade, **calculado en local**:
- `ya_en_biblioteca`: serie local con **el mismo id externo** (coincidencia exacta);
- `parecidas_locales`: series locales con `title_norm` igual y año ±1 (sin id externo o con otro): **aviso**, no coincidencia;
- `coincidencia_con_la_carpeta`: las **mismas señales de la rebanada 1** evaluadas contra ese resultado como si fuera la candidata de todos los archivos del grupo (año, calificador, título exacto sin corroborar). **Se reutiliza el código** de `_Hallazgos` en lugar de escribirlo otra vez.

**Selección de edición.** Mientras el ADR 0003 siga «Propuesto» no existe `editions`: **elegir edición = elegir el resultado concreto de la fuente** (cada ficha de Tebeosfera ya es una edición, con su sello en el *slug*; un volumen de Comic Vine es una serie) y, por archivo, el **`Issue.format`** que ya deduce el nombre (B15). La ficha **no resuelve** el modelo de ediciones; lo dice en la pantalla («esta fuente distingue ediciones; elige la tuya») y deja el sello/editorial visible cuando la fuente lo da.

**Orden y presentación:** **neutros** (por fuente fija y luego por título; sin «recomendada» ni puntuación que parezca una recomendación). **Nada preseleccionado**, aunque solo haya un resultado.

**Sin fuentes:** si todas están apagadas, no hay clave de Comic Vine o no hay red, la pantalla lo dice (los avisos ya existen) y ofrece el camino **«crear a mano»** del bloque B. **Cero peticiones de red** si no se pulsa el botón.

**Seguridad:** los resultados son datos externos no fiables: se **escapan**; las portadas van por el proxy con lista blanca que ya existe (`/ui/descubrir/portada`); cada candidata sale con un **token firmado** (D9) y **el formulario solo reenvía el token**.

**Qué NO hace:** no escribe nada, no crea series, no hace asignaciones, no encadena búsquedas por sí sola.

## B. Creación o reutilización de la serie, con validación de colisiones

Tres salidas posibles al elegir una candidata, **siempre con vista previa del alta** y confirmación 1:

1. **Reutilizar** — existe una serie local con **el mismo id externo**: «ya está en tu biblioteca», se usa esa. Es la única coincidencia automática, porque es exacta.
2. **Posible duplicado** — hay series locales con `title_norm` igual y año ±1 y misma tradición, pero **sin ese id externo**: se muestran lado a lado y la persona elige **«es la misma → usar la existente»** o **«es distinta → crear igualmente»**. **No se decide en silencio.** (La tabla `series` **no tiene ninguna restricción de unicidad por título/año**: solo por ids externos.)
3. **Crear** — serie nueva con título, año y **tradición elegida por la persona** (D3: se **sugiere** por la fuente o por la carpeta de primer nivel, **sin valor por defecto**), el id externo y `metadata_source` de la fuente si viene de una, o ninguno si es manual (D10).

**Reglas:**
- La alta usa **solo** lo que dice el token firmado (o lo que la persona escribió en «a mano»), **nunca** campos sueltos del formulario.
- **Concurrencia:** dos confirmaciones solapadas no crean dos series. Con id externo lo impide `UNIQUE`; el código hoy comprueba y luego inserta **sin tratar la carrera** (H4) y debe capturar la violación y tratarla como «ya existía». Sin id externo se serializa con un **candado consultivo de transacción** sobre `(title_norm, año)`: sin migración.
- **Procedencia (D1):** se guarda **con la serie**, en `Series.metadata_["alta"]` (`origen`: `descubrir`/`manual`; `fuente`; `id_externo`; `desde_grupo` = `clave`; `fecha`; `confirmado_por`: la sesión, sin datos sensibles). **Ningún código de la aplicación escribe hoy en `Series.metadata_`** (se comprobó: todas las escrituras a `metadata_` son de `File`; el esquema `SeriesCreate` ni siquiera lo admite), así que no se pisa.
- **Deshacer el alta:** solo mientras la serie **no tenga ninguna asignación** (ningún `Issue` con archivo, ninguna operación viva). Hoy `DELETE /api/series/{id}` solo protege contra una operación viva (H2); el «deshacer» de este flujo comprueba además que no haya archivos asignados.

**Qué NO hace:** no asigna archivos, no mueve nada, no fusiona series, no edita las existentes.

## C. Vista previa de los registros afectados (números, ediciones y conflictos)

**Entrada:** el grupo y la serie elegida (existente o recién creada). **Solo lee**: consultas `SELECT` y **`stat` de cada ruta de origen y de destino** (metadatos, sin leer contenido). Es una **ampliación consciente** respecto a la rebanada 1 (que no miraba el disco): sin saber si el origen existe, la vista previa mentiría con las 14 filas obsoletas. **Sin hash, sin red, sin escribir** (el hash lo hace `_preparar` al ejecutar).

**Por archivo** (`archivos[]`):

| Campo | Contenido |
|---|---|
| `numero_propuesto`, `numero_origen` | Del nombre (`parse_comic_filename`); **editable**; `nombre`/`ninguno` |
| `edicion` | `edition_kind` → `Issue.format` (B15) |
| `origen`, `destino` | Rutas **relativas a la biblioteca**; el destino es `build_library_path` (pura): `{tradición}/{Serie (Año)}/{Serie #NNN.ext}`. Si ya existe, se informa que se guardará con sufijo ` (1)` |
| `estado` | Ver abajo |
| `conflictos` | Las señales de la rebanada 1 **recalculadas contra la serie elegida** |
| `seleccionado_por_defecto` | Solo si `estado = se_asignaria` **y** sin conflicto de carpeta |

**Estados** (nombres neutros; **no existe «lista»**): `se_asignaria` · `requiere_numero` · `numero_repetido_en_el_grupo` · `numero_ya_existe` (ya hay un `Issue` con ese número) · `colision_de_edicion` (B15: otro `Issue.format`) · `ya_asignado` · `origen_no_encontrado` («registro pendiente de verificar, no archivo confirmado») · `con_conflicto_de_carpeta` · `fuera_del_limite`.

**Qué ve la persona antes de confirmar:** cuántos archivos, **cuántos bytes**, **tiempo estimado** y, sobre todo, la frase **«se moverán de su carpeta actual a la de la biblioteca»** con ejemplos (D6). Las estimaciones salen de las mediciones del repositorio (`docs/design/medicion-pi-resumen-2026-10-04.csv`): **≈ 1,1 s por cada 100 MB en NVMe, ≈ 1,2-1,4 s en la carpeta de descargas y ≈ 2,9-3,3 s en el disco USB (WDElements)**; 50 archivos de 100 MB serían entre 54 y 164 s.

**Límites por confirmación** (D8, **hipótesis a medir**): ≤ 100 archivos y ≤ 4 GB; lo que exceda sale `fuera_del_limite` y se hace en otra pasada. `asignacion_simultaneas` sigue en 1.

**Sin preselección:** un archivo con conflicto de carpeta **no** viene marcado; para incluirlo hay que marcarlo a mano. La serie **tampoco** se preselecciona nunca.

**Salida:** JSON + vista, y un **token de confirmación** firmado que liga `(clave, series_id, ids, números, huella de cada archivo = (tamaño, mtime_ns), caducidad corta)`.

## D. Confirmación explícita y operación recuperable

- **Confirmación 2** = una acción por grupo: «Asignar *N* archivos a «*Serie (año)*»». Recibe **solo el token** y los números/selecciones que la persona cambió; el servidor **vuelve a calcular** la vista previa y **rechaza** lo que haya cambiado desde entonces **por archivo** (`cambio_desde_la_vista_previa`), sin abortar el resto.
- **Ejecución:** un **lote en segundo plano** (mismo patrón que `registro_biblioteca`: una ejecución por proceso, progreso consultable, sin reanudarse solo) que llama **una a una** a `AsignacionService.asignar(...)`, **sin cambiarlo**. La durabilidad es la de cada operación (`asignacion_operaciones`); el lote en sí no necesita tabla: al reiniciar, `reconciliar_al_arrancar` termina lo vivo y **lo no empezado sigue pendiente**; abrir el grupo de nuevo recalcula la vista previa (`ya_asignado` donde ya está).
- **Informe honesto:** cuenta por `EstadoResultado` con los textos de `RESPUESTAS`, **agregados**. «Terminado» no es «correcto»: nunca se anuncia éxito si algún archivo no quedó `asignado`; lo recuperable (`asignado_limpieza_pendiente`, `reparacion_pendiente`, `pendiente`) se dice tal cual.
- **Alias (D7):** `aprender_alias=False` **por defecto**. Un alias aprendido hace que las descargas futuras con ese nombre se asignen **sin preguntar**; justo el fallo que la rebanada 1 evita. La persona puede marcar «Recordar este nombre» **explícitamente**.
- **Idempotencia:** confirmar dos veces no duplica nada (`YA_ASIGNADO`/`YA_EN_CURSO`); un segundo lote mientras corre otro recibe 409 con el progreso del primero.

## E. Conflictos sin preselección; duplicados y obsoletas fuera de alcance

- **Ninguna serie preseleccionada**, ni con un único resultado, ni con coincidencia exacta de título (el caso `BATMAN (2025)` frente a `Batman - Saga de Scott Snyder (2019)`).
- **Ningún archivo con conflicto preseleccionado.**
- **Duplicados** (copias idénticas no registradas) **y las 14 referencias obsoletas**: la vista previa **bloquea** las segundas (`origen_no_encontrado`) y **no ofrece ninguna acción** sobre ninguna de las dos; D5 sigue abierta.

## Contratos (resumen; el detalle se fija en la PR de cada paso)

| Paso | Endpoint propuesto | Efectos |
|---|---|---|
| A | `POST /api/revision/descubrir` `{clave, consulta?}` | Red (solo aquí). Sin escrituras. Respuesta: `consulta`, `fuentes{estado}`, `avisos`, `candidatas[]` (`token`, `fuente`, `titulo`, `anio`, `tradicion_sugerida`, `editorial?`, `sitio_url`, `portada`, `ya_en_biblioteca`, `parecidas_locales[]`, `coincidencia_con_la_carpeta`) |
| B | `POST /api/revision/serie/previsualizar` y `POST /api/revision/serie` | La segunda escribe **solo** `series` (y la procedencia). Devuelve `series_id` y si fue reutilizada o creada |
| C | `POST /api/revision/asignacion/previsualizar` `{clave, series_id, numeros?, seleccion?}` | `SELECT` + `stat`. Devuelve `archivos[]`, `totales`, `avisos_de_grupo`, `token` |
| D | `POST /api/revision/asignacion` `{token, ...}` → `202` + `GET /api/revision/asignacion/estado` | Mueve ficheros por el servicio recuperable |

Todos exigen sesión/Basic como el resto de `/api/*`, llevan `Cache-Control: no-store`, **no** dependen de la aceptación legal (no son búsquedas ni descargas de P2P; ver `web/discovery.py`) y no registran rutas ni nombres. El HTML (`/ui/pendientes/carpetas/...`) reutiliza estos servicios sin duplicar lógica (como en 1b).

## Invariantes (se repiten porque son la razón de la rebanada)

No mentir («serie sugerida» no es «clasificada»; «registro» no es «archivo confirmado»). Nada se asigna ni se elige solo. Nada viaja suelto en un formulario: **token firmado**. Crear serie y asignar son **dos confirmaciones**. Se reutiliza `AsignacionService` **sin cambiarlo**. La red solo a petición y con los límites de cada fuente. Sin borrar nada. Sin dependencias nuevas.

## Pruebas de aceptación (Postgres real, ficheros reales en `tmp`, red simulada; ningún dato personal)

**A — Descubrimiento**
1. **Sin clic no hay red:** abrir el grupo no hace ninguna petición saliente (cliente HTTP parcheado para fallar).
2. **Fuentes caídas o apagadas:** una fuente que falla no tumba las demás; sin ninguna, la respuesta lo explica y el camino «a mano» sigue disponible.
3. **Nada preseleccionado:** un único resultado, o uno con título exacto, sale **sin** serie elegida; el orden es el neutro fijado.
4. **`ya_en_biblioteca` solo por id externo exacto**; el mismo título sin id sale como `parecidas_locales` (aviso).
5. **La carpeta contradice al resultado** (`Batman - Saga de Scott Snyder (2019)` frente a `BATMAN (2025)`) ⇒ `coincidencia_con_la_carpeta` en conflicto, con las mismas señales que la rebanada 1 (**un solo código**: prueba de que ambos usan `_Hallazgos`).
6. **Los datos externos se escapan** (título con HTML) y las portadas solo salen por el proxy con lista blanca.
7. **Un token manipulado, de otro grupo o caducado** se rechaza; **el formulario no puede colar** `title`, `description` ni `cover_url`.

**B — Alta**
8. **Mismo id externo** ⇒ se reutiliza, no se crea.
9. **Parecida sin id** (mismo `title_norm`, año ±1, misma tradición) ⇒ **no** se crea ni se reutiliza en silencio: exige elegir.
10. **Tradición obligatoria** sin valor por defecto.
11. **Dos confirmaciones solapadas** crean **una** serie (con y sin id externo).
12. **Procedencia** guardada en `metadata_["alta"]` y no pisada por el enriquecedor.
13. **Deshacer** solo sin asignaciones; con un `Issue` con archivo, se niega con un motivo legible.
14. **Cero escrituras en A y en la vista previa de B.**

**C — Vista previa**
15. **Solo lectura y sin red:** solo `SELECT`; el único acceso a disco es `stat` de origen y destino; **sin hash**; número de consultas constante (≤ 4) con 20 y con 2.000 archivos.
16. **Cada estado:** número vacío, repetido en el grupo, ya existente, colisión de edición (B15), ya asignado, origen no encontrado, destino ocupado (se anuncia el sufijo), archivo cambiado, fuera del límite.
17. **Las 14 filas obsoletas** salen `origen_no_encontrado`, con el texto «registro pendiente de verificar», y **no se pueden seleccionar**.
18. **Sin preselección con conflicto:** un archivo con año discrepante no viene marcado; marcarlo a mano lo incluye.
19. **Rutas relativas** a la biblioteca y sin salir de ella (`sanitize_segment`).
20. **Estimación de tiempo y bytes** coherentes con los tamaños reales.

**D — Confirmación y lote**
21. **Token**: manipulado, caducado, de otra serie o reutilizado ⇒ rechazado.
22. **Un archivo cambia entre la vista previa y la confirmación** ⇒ ese archivo se omite (`cambio_desde_la_vista_previa`); el resto se asigna.
23. **Resultado agregado honesto:** un lote con un `asignado_limpieza_pendiente` y un `colision_edicion` **no** anuncia éxito; el informe cuenta cada estado.
24. **Idempotencia:** confirmar dos veces no duplica; un segundo lote en marcha ⇒ 409 con el progreso.
25. **Reinicio a mitad:** se mata el proceso entre dos archivos; al arrancar, `reconciliar` termina el vivo, el resto sigue pendiente y reabrir el grupo muestra `ya_asignado` donde corresponde.
26. **Alias:** por defecto **no** se aprende; con la casilla marcada, sí.
27. **El servicio de asignación no cambia**: el lote solo llama a `asignar` (prueba por inspección de la llamada).
28. **Auth, `no-store`, sin rutas ni nombres en los logs.**

**Mutaciones:** cada defensa (preselección, colisión, token, límites, idempotencia, alias) se rompe a propósito y alguna prueba debe fallar (con bytecode desactivado).

**Medición previa (informativa, no bloquea):** un script de solo lectura (`scripts/medicion/medir_descubrimiento.py`, a ejecutar en la Pi con las fuentes reales y los límites de cortesía) que, para los 20 grupos mayores, cuente resultados, si el primero cuadra en año ±1 y si la fuente distingue ediciones. **No se afirma que las fuentes encuentren las series**: se mide.

## Entrega en PR (cada una pequeña; ninguna es la interfaz completa)

| PR | Contenido | Escribe |
|---|---|---|
| **Previa (independiente)** | Cerrar **H1** (`cover_url` sin lista blanca): ya señalado como tarea aparte | — |
| **2a** | Descubrimiento contextualizado: servicio + JSON + token firmado + candidatas con `ya_en_biblioteca`, `parecidas_locales` y `coincidencia_con_la_carpeta` | Nada |
| **2b** | Alta: previsualizar y confirmar la serie, colisiones, concurrencia, procedencia, deshacer | Solo `series` |
| **2c** | Vista previa de la asignación (servicio + JSON), con `stat` y sin hash | Nada |
| **2d** | Confirmación y lote en segundo plano sobre `AsignacionService`, informe agregado, alias | Ficheros y BD, por el servicio recuperable |
| **2e** | Vistas HTML de los cuatro pasos, **verificadas en navegador real** (móvil, tema claro/oscuro, teclado) | Solo lo que ya hacen los servicios |

## Decisiones abiertas para la revisión (D0-D10)

- **D0 — Orden de las rebanadas.** Ver la tabla de arriba. *Recomendación:* el orden pedido, con «crear a mano» como camino de primera clase en 2b.
- **D1 — Dónde guardar la procedencia del alta.** *(Cambia la recomendación de la ficha anterior.)* Opciones: `import_runs.details` (la documentación de esa columna dice que son **líneas legibles, no estructuradas**), una tabla propia (migración 0018) o **`Series.metadata_["alta"]`** (sin migración, estructurado, vive y muere con la serie; hoy nadie escribe ahí). *Recomendación:* `Series.metadata_["alta"]`. Las asignaciones ya quedan auditadas en `asignacion_operaciones`.
- **D2 — Los 17 y la bandeja.** Sin cambios: se mantiene abierta; esta ficha **no toca el contador del menú**. Asignar un archivo «serie sugerida» lo saca de la superficie.
- **D3 — Tradición de la serie nueva.** *Recomendación:* sugerir (la fuente da `tradition_guess`; la carpeta de primer nivel orienta) y **exigir elección explícita**, sin valor por defecto.
- **D4 — Perfil por carpeta raíz.** Fuera: se infiere y se muestra (sin cambios).
- **D5 — Duplicados y referencias obsoletas.** Fuera (sin cambios). La vista previa solo las **bloquea** con un texto claro.
- **D6 — ¿Asignar mueve?** **La decisión de producto más importante de esta ficha.** `AsignacionService` **mueve y renombra** cada archivo a `{tradición}/{Serie (Año)}/{Serie #NNN}` (ADR 0006): para un archivo registrado «en su sitio» eso **reorganiza la biblioteca de la persona** y cambia las rutas que ven Kavita u otros lectores. Alternativa: **«vincular en su sitio»** (crear el `Issue` y enlazar sin mover), que sería una operación **nueva** con su ADR. *Recomendación:* en la rebanada 2 **mantener el comportamiento de ADR 0006** (la revisión pidió reutilizar el servicio sin cambios) y **decirlo con toda claridad en la vista previa**; decidir «vincular en su sitio» **antes de 2d**, porque cambia lo que la persona espera de «registrar sin mover».
- **D7 — Alias.** *Recomendación:* `aprender_alias=False` por defecto; la persona lo activa a mano.
- **D8 — Límites por confirmación.** Hipótesis: ≤ 100 archivos y ≤ 4 GB. *Recomendación:* medirlos en la Pi antes de fijarlos; configurables en `config.py`.
- **D9 — Cómo no confiar en los datos del cliente.** (i) **Volver a pedir por id** (Sonarr, Kapowarr): exige «obtener por id» en los cuatro clientes y una petición más por alta; (ii) **token firmado** del servidor (patrón de Deseados, sin cliente nuevo ni petición extra). *Recomendación:* (ii) ahora; (i) como mejora posterior.
- **D10 — `metadata_source` de una serie creada a mano.** `NULL` (el enriquecedor puede intentar emparejarla por título, como con cualquier serie sin fuente) o `manual` (nadie la toca). *Recomendación:* `NULL`.

## Hallazgos laterales (no son parte de la historia, pero la tocan)

- **H1 — `Series.cover_url` sin lista blanca (seguridad).** `POST /ui/descubrir/crear`, `POST /api/series` y `PATCH /api/series/{id}` guardan el `cover_url` que reciben; `GET /ui/series/{id}/portada` lo **descarga en el servidor** (`fetch_and_cache_cover`, `follow_redirects=True`, sin lista blanca de hosts; solo el proxy de Descubrir la tiene). Es un SSRF **ciego** (la respuesta solo vuelve si decodifica como imagen). Con la configuración por defecto (solo localhost) el riesgo es bajo; con LAN abierta y contraseña (ADR 0004), moderado. **Se ha dejado como tarea aparte con prompt autocontenido**; la rebanada 2 **no debería empezar 2b antes de que se cierre**, porque 2b crea series.
- **H2 — `DELETE /api/series/{id}`** solo se niega ante una operación de asignación **viva**; no ante archivos ya asignados (el borrado deja sus `File.issue_id` en `NULL` por `SET NULL`). El «deshacer alta» de esta ficha lo comprueba por su cuenta; el endpoint general queda como está.
- **H3 — Cortesía con Tebeosfera.** `CLAUDE.md` §4 dice **2,5 s por petición**; `config.py` fija `tebeosfera_rate_limit = 2.0`. Antes de la PR 2a hay que decidir cuál vale y alinear el otro.
- **H4 — Carrera en `get_or_create_series`.** Comprueba y luego inserta sin tratar la violación de `UNIQUE`: dos altas simultáneas del mismo id externo darían un error 500 al segundo en vez de «ya existía». Se corrige en 2b (con prueba de regresión).

## Límites de esta ficha

Lectura de código en `main` @ `5645628`; **Mylar3 no se ha leído** para esta rebanada y las referencias externas se leyeron sin ejecutarse. **No se ha medido** que las fuentes encuentren las series de la biblioteca real (la medición previa lo hará); los límites de D8 son hipótesis; las estimaciones de tiempo proceden de las mediciones del repositorio en una Pi concreta. No se ha ejecutado nada contra producción ni contra fuentes reales.
