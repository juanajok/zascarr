# Ficha técnica — Rebanada 2: elegir o crear la serie correcta y clasificar con vista previa y confirmación

> Desarrolla las rebanadas 2-4 de `docs/design/ficha-propuestas-desde-carpetas.md` tras cerrar la rebanada 1 (`docs/design/rebanada-1-superficie-de-revision.md`, en `main`).
> **Esta ficha no implementa nada**: fija el problema, los contratos y las pruebas de aceptación **antes** de escribir código. **No autoriza** crear series, vincular ni mover archivos, ni tocar producción.
> **Versión 2** (2026-10-07): incorpora la revisión de la versión 1. **Clasificar ya no significa mover**: ver `docs/adr/0007-vincular-en-su-sitio.md` (Aceptado, sin implementar).

## Cambios respecto a la versión 1 (revisión del 2026-10-07)

| Punto de la revisión | Resolución | Dónde |
|---|---|---|
| **D0** orden | **Adoptado**: descubrimiento desde el grupo → elegir o crear serie → vista previa → confirmación. «Crear a mano» es un camino **completo** sin red ni claves | «El flujo», bloque B |
| **D6** archivos adoptados | **Vincular en su sitio** (serie y número, conservando nombre y ruta) es el camino previsto. **Organizar** (mover y renombrar) es **otra operación**, con consentimiento específico, **fuera de esta rebanada**. Se retira la recomendación de reutilizar el servicio de movimiento sin cambios | ADR 0007; bloques C y D |
| Selección inicial | **Todos los archivos empiezan sin marcar**; no hay `seleccionado_por_defecto` | Bloque C |
| Confirmación | Solo acepta el **token** de la vista previa definitiva; cualquier cambio (números, selección, serie, modo) **regenera vista previa y token** | Bloque D |
| Reintentos | **Una sola semántica**: el `operacion_id` del token es la clave de idempotencia; repetir devuelve el resultado, nunca ejecuta otro lote | Bloque D |
| Colisiones manuales | Candado sobre el **título normalizado** (no sobre título y año exactos) y **comprobación repetida dentro de la transacción** | Bloque B |
| Recuperación del informe | Vincular es **una transacción** sin ficheros: no hay lote que recuperar. El informe se reconstruye del token y de la procedencia por archivo | Bloque D, ADR 0007 |
| **D1** procedencia | `Series.metadata_["alta"]`, esquema versionado, preservación explícita, sin token ni sesión | Bloque B |
| **D8** límites | Hipótesis iniciales y conservadoras, **no validadas** ni garantía de duración | D8 |
| **D9** token | Token firmado con **propósito**, caducidad y vinculación al contexto | Bloque A, tabla de tokens |
| **D10** alta manual | **No** `NULL`: ver la regla de enriquecimiento | Bloque B |
| Tebeosfera | **2,5 s como mínimo** entre peticiones; alinear configuración, documentación y pruebas (PR aparte) | H3 |
| **H1** | Corrección **independiente y previa**; sin etiquetas de riesgo por escuchar en localhost o LAN | H1 |

## Historia

Como coleccionista con cientos de CBZ/CBR ya registrados «en su sitio» pero **sin serie**, quiero buscar en las fuentes la serie y la edición correctas, crearla (o reutilizar una que ya tengo),
ver **qué pasará con cada archivo** y confirmarlo, para que mis tebeos queden **clasificados sin que nadie los mueva ni me lo haga a escondidas**.

## El bloqueo original

Primer registro real en producción (2026-10-05, ver `BACKLOG.md`): **1.322 registros «Sin serie»** (1.308 + 14 filas previas), **17 con serie sugerida** pero sin `Issue`, y **solo 5 series locales**:
no existen `Superman`, `Patrulla-X`, `Nuevos Mutantes`, `The Boys` ni `Carlos Giménez`. La rebanada 1 ya **muestra** esos grupos y por qué; la persona **no puede hacer nada con ellos**:

- «Por revisar» solo sabe **asignar un archivo a una serie que ya existe**, uno a uno, y **al hacerlo lo mueve** (`POST /ui/pendientes/{id}/asignar`).
- «Descubrir» sabe **buscar en fuentes y crear una serie suelta**, pero no conoce los archivos.
- Nada une las dos cosas ni deja ver, **antes de cambiar nada**, qué le pasaría a cada archivo.

## Qué existe hoy (verificado leyendo el código en `main`)

| Pieza | Dónde | Qué hace | Qué le falta para esta historia |
|---|---|---|---|
| Superficie de revisión | `services/revision_carpetas.py`, `/api/revision/carpetas`, `/ui/pendientes/carpetas` | Grupos por carpeta, estados, señales por archivo contra **su** candidata, `senales[].archivos` | Ninguna acción. Las señales se calculan contra la candidata **guardada** de cada archivo, no contra una serie que la persona elija ahora |
| Buscar en fuentes | `services/discovery.py::DiscoveryService.search` | Consulta en paralelo Comic Vine, AniList, Tebeosfera y GCD; tolera que una falle | Busca por texto libre: no parte de un grupo, no dice si ya existe la serie ni si la carpeta la corrobora |
| Crear serie desde una fuente | `web/discovery.py::crear` → `get_or_create_series` | Crea la `Series` con el id externo; no duplica por id externo | **Sin validación de colisiones por título/año.** **Confía en los campos ocultos del formulario** (H1). Comprobar-y-luego-insertar sin tratar la carrera (H4) |
| Crear serie a mano | `api/series.py::create_series` | Crea una `Series` con los campos del esquema | Sin comprobación de colisión ni registro de por qué existe |
| **Asignar (mueve)** | `services/asignacion.py::AsignacionService.asignar` | Recuperable (ADR 0006): copia verificada → publica → confirma → retira el origen. **Mueve y renombra a `{tradición}/{Serie (Año)}/{Serie #NNN}`** | **Es «organizar», no «vincular»** (ADR 0007). Devuelve `ya_asignado` si el archivo ya está vinculado |
| Vincular sin mover | — | **No existe** | Operación nueva (ADR 0007) |
| Token firmado | `services/orchestrator.py::crear_token_candidato` (sobre `auth.sign_token`) | El formulario solo reenvía un token HMAC con caducidad | Solo lo usa Deseados |
| Modelo de ediciones | ADR 0003 (**Propuesto**) | Edición = espacio de numeración | **No hay tabla `editions`**: hoy la edición vive en `Issue.format` (B15) y, entre fuentes, en **el resultado concreto elegido** |
| Clientes de fuentes | `services/{comic_vine,anilist,tebeosfera,gcd}.py` | Solo `search_series` | **Ninguno tiene «obtener por id»** |

## Referencias consultadas (CLAUDE.md §13; lectura de código, no ejecutadas)

Versiones fijadas: **Sonarr** `v5-develop` @ `da99063` (`AddSeriesService.cs`, `SeriesExistsValidator.cs`, `SeriesPathValidator.cs`), **Kapowarr** @ `c191dda` (`backend/implementations/volumes.py`, `Library.add`), **Kaizoku** `oae/kaizoku` @ `fc86b7d` (`router/manga.ts::add`; archivado).
**Mylar3 no se ha leído para esta rebanada**; Suwayomi y Aidoku se leyeron en la ficha de propuestas. Sonarr y Kapowarr GPL-3.0, Kaizoku MIT: **solo como patrón, no se copia código**.

| Qué hacen | Sonarr | Kapowarr | Kaizoku |
|---|---|---|---|
| Identidad al añadir | **Id externo** (TVDB); «This series has already been added» | **Id externo** (CV); `VolumeAlreadyAdded` **antes** de escribir | **Título** (único); el id de AniList no vive en la BD |
| ¿Confía en lo que manda el cliente? | **No**: vuelve a pedir la serie por id (`AddSkyhookData`) | **No**: `fetch_volume(comicvine_id)` | Vuelve a resolver por título exacto y **se niega si hay 0 o varios** |
| Destino | `SeriesPathValidator`: ruta ya usada por otra serie | `RootFolderNotFound`; carpeta generada | No comprueba la carpeta; la muestra sin poder editarla |
| Preselección | Preselecciona el primer resultado | Elige el mejor por reglas | Ninguna |

**Adoptar:** identidad por **id externo** y comprobar duplicado **antes** de escribir; **no confiar en lo que manda el cliente**; negarse ante la ambigüedad. **Adaptar:** las series **locales sin id externo** (las 5 que existen) se comparan por `title_norm` + año ±1 + tradición, **como aviso que la persona resuelve**. **Descartar:** preseleccionar o elegir «el mejor»; identidad por título; buscar o monitorizar automáticamente al añadir.

## Alcance y no-alcance

**Dentro:** buscar en fuentes **desde un grupo**; elegir o crear la serie; validar colisiones; **vista previa** de lo que pasaría con cada archivo; **confirmación explícita**; **vincular en su sitio**, en una transacción.
**Fuera (sin excepción):** **organizar** (mover y renombrar) y «reubicar» un archivo ya vinculado (**rebanada 3**, con su ficha y su consentimiento); duplicados (~200 grupos, **D5**) y las 14 referencias obsoletas (la vista previa las **bloquea** y las llama «registros pendientes de verificar»); el modelo de ediciones del ADR 0003; fusionar, renombrar o borrar series; el contador del menú (**D2**); producción; cualquier clasificación **automática** o **preseleccionada**.

## El flujo, en cinco pasos separados

```
 grupo (rebanada 1)
   └─ A. Descubrir     (red, solo a petición; no escribe)              → candidatas, ninguna elegida
        └─ B. Elegir o crear la serie  (escribe SOLO el catálogo)       → series_id        ← confirmación 1
             └─ C. Vista previa de la vinculación (solo lee: SELECT + stat) → qué pasaría con cada archivo
                  └─ D. Confirmar y vincular  (UNA transacción, no toca ficheros) → informe  ← confirmación 2
 E. Conflictos y fuera de alcance: transversal (nada se preselecciona; duplicados y obsoletas no se tocan)
```

**Dos confirmaciones, no una:** crear la serie es del **catálogo** (reversible mientras no tenga archivos vinculados); vincular es **otra decisión** y se confirma aparte. **Ninguna de las dos mueve un fichero.**

## A. Descubrimiento y selección de edición desde fuentes (sin depender de una serie local)

**Entrada:** un grupo de la rebanada 1 (`clave`) y una **consulta** propuesta a partir de la carpeta limpia y del título dominante de los nombres; **editable**. La búsqueda **no se lanza sola**: solo con el botón «Buscar en las fuentes».

**Qué hace:** reutiliza `DiscoveryService.search` (las fuentes encendidas, tolerando que una falle). Por cada resultado añade, **calculado en local**:
- `ya_en_biblioteca`: serie local con **el mismo id externo** (coincidencia exacta);
- `parecidas_locales`: series locales con `title_norm` igual y año ±1 (sin ese id externo): **aviso**, no coincidencia;
- `coincidencia_con_la_carpeta`: las **mismas señales de la rebanada 1** evaluadas contra ese resultado como candidata de todos los archivos del grupo. **Se reutiliza el código de `_Hallazgos`** (hoy privado: se hará público), no se reescribe.

**Selección de edición.** Mientras el ADR 0003 siga «Propuesto» no existe `editions`: **elegir edición = elegir el resultado concreto de la fuente** (cada ficha de Tebeosfera ya es una edición; un volumen de Comic Vine es una serie) y, por archivo, el `Issue.format` que deduce el nombre (B15). La ficha **no resuelve** el modelo de ediciones y la pantalla lo dice.

**Orden y presentación:** **neutros** (fuente fija y luego título; sin «recomendada»). **Nada preseleccionado**, ni con un único resultado.

**Sin fuentes:** si están apagadas, falta la clave de Comic Vine o no hay red, la pantalla lo dice y el **camino «crear a mano»** del bloque B queda **completo y disponible**. **Cero peticiones de red** si no se pulsa el botón.

**Tokens firmados (D9).** El formulario **solo reenvía un token**; nada viaja suelto. Cada token lleva un **propósito**, una **caducidad corta (15 min)** y la **vinculación al contexto**; verificar uno exige coincidir en las tres cosas, así que **un token de un paso no sirve en otro**:

| Token | `proposito` | Contexto al que se liga | Contenido firmado |
|---|---|---|---|
| Candidata | `candidata` | `clave` del grupo | fuente, id externo, título, año, tradición sugerida, descripción, `cover_url` (que debe pasar la política de H1 **al emitirlo y al usarlo**) |
| Alta de serie | `alta` | `clave` + candidata o datos manuales | lo que se verá creado, el conjunto de **series parecidas vistas**, y si la persona **aceptó el duplicado** |
| Vinculación | `vincular` | `clave` + `series_id` | `operacion_id`, y por archivo `(id, número, formato, tamaño, mtime_ns)` |

Se firman con la misma clave que la cookie de sesión (`auth.sign_token`). **Un token garantiza la integridad de lo que vio la persona; no hace segura una URL externa**: por eso `cover_url` se valida aparte (H1).

**Qué NO hace:** no escribe, no crea, no vincula, no encadena búsquedas.

### Implementación 2a (`POST /api/revision/descubrir`): lo que se precisó o añadió

| Punto | Qué se hizo y por qué |
|---|---|
| **Estado por fuente** | `DiscoveryService.search_detallada` devuelve además `fuentes`: `ok`, `apagada`, `sin_clave` (Comic Vine encendida sin clave: no se consulta) o `error`. `search` conserva su contrato |
| **`consulta_propuesta`** | La respuesta devuelve la consulta usada **y** la propuesta (carpeta limpia; si no hay carpeta de serie, el título que dominan los nombres; **un «título» sin ninguna letra no cuenta**: el parser da «01» para `01.cbz`). Sin propuesta ni consulta escrita: 422 |
| **`parecidas_locales`** | Mismo **título normalizado** (con las mismas reglas que el resto de ZascArr: `The Flash` = `Flash`) y año compatible (±1; **un año desconocido no descarta**), **sin exigir la misma tradición**: se muestra la de cada parecida y la comparación estricta con tradición es de 2b |
| **`coincidencia_con_la_carpeta`** | Se llama a **la misma función** que usa la superficie de revisión (`senales_contra_serie` → `_senales`), con la candidata aplicada a **todos** los archivos del grupo (con serie sugerida o sin ella). Una prueba compara las señales con las de `GET /api/revision/carpetas` para el mismo grupo: **son idénticas** |
| **Portada** | Solo sale (y solo entra en el token) si cumple la política de H1, y **por el proxy** con lista blanca: nunca una URL externa como `src` |
| **Tokens** | `services/tokens_revision.py`: propósito + contexto (`clave`) + caducidad de 15 min, firmados con `auth.sign_token`. Sin clave del servidor **no se firma** (503) |
| **Ritmo** | El límite de cortesía de cada fuente vive **en la instancia del cliente** y cada búsqueda crea clientes nuevos (Tebeosfera arranca con `_last_req = 0`): dos búsquedas seguidas llegarían al sitio sin espera. El endpoint admite **una búsqueda a la vez** y exige **3 s** entre dos (429 con `Retry-After`); un 404 o un 422 no consumen ese espaciado |
| **Sin `editorial`** | Ningún cliente de fuente la devuelve hoy en `DiscoveryResult`: no se inventa el campo |
| **Consultas** | Dos por búsqueda (por identificador externo y por título normalizado), vengan 3 resultados o 40; más la lectura del grupo: ≤ 3 en total |

## B. Creación o reutilización de la serie, con validación de colisiones

Tres salidas al elegir una candidata, **siempre con vista previa del alta** y confirmación 1:

1. **Reutilizar** — existe una serie local con **el mismo id externo**: es la única coincidencia automática, porque es exacta.
2. **Posible duplicado** — hay series locales con `title_norm` igual, año ±1 y misma tradición, **sin ese id externo**: se muestran lado a lado y la persona elige **«es la misma → usar la existente»** o **«es distinta → crear igualmente»**. **No se decide en silencio.** (`series` **no tiene ninguna restricción de unicidad por título/año**.)
3. **Crear** — serie nueva con título, año y **tradición elegida por la persona** (**D3**: se sugiere por la fuente o por la carpeta de primer nivel; **sin valor por defecto ni confirmado de antemano**), y el id externo si viene de una fuente.

**Crear a mano es un camino completo:** misma pantalla, misma vista previa del alta, mismas colisiones y procedencia; solo cambia el origen (`manual`). No necesita red, ni clave, ni fuentes encendidas.

**Reglas:**
- El alta usa **solo** lo que dice el token (o lo que la persona escribió en «a mano»), **nunca** campos sueltos.
- **Concurrencia y colisiones.** Dos confirmaciones solapadas no crean dos series. La alta se hace en **una transacción** que **primero** toma un **candado consultivo de transacción** sobre el **título normalizado** (`pg_advisory_xact_lock` con `f_title_norm(título)`), **sin año ni tradición**: así se serializan **todas** las altas que podrían colisionar, incluidas las de años ±1 (un candado sobre título **y** año exactos no cubriría 1987 frente a 1988). **Dentro de esa misma transacción** se **repite** la comprobación: se vuelven a buscar las series parecidas y se compara su conjunto con el que la persona vio (`coincidentes_vistos`, en el token). Si **aparecieron otras** desde la vista previa, la alta se rechaza con 409 y hay que rehacer la vista previa. Si todas las parecidas vistas siguen siendo las mismas y la persona aceptó el duplicado, se crea. Con id externo, además, lo impide `UNIQUE`: hoy `get_or_create_series` comprueba y luego inserta sin tratar esa violación (**H4**); se captura y se trata como «ya existía».
- **Procedencia (D1, aceptada):** en `Series.metadata_["alta"]`, con **esquema versionado**: `{"version": 1, "origen": "descubrir"|"manual", "fuente", "id_externo", "desde_grupo": clave, "fecha", "tradicion_elegida": true}`. **Nunca** el token ni identificadores de sesión. **Hoy ninguna parte de la aplicación escribe en `Series.metadata_`** (todas las escrituras a `metadata_` son de `File`; `SeriesCreate` no lo admite). **Regla para cualquier escritor futuro** (enriquecedores incluidos): **fusionar por clave de primer nivel, nunca sustituir el objeto**, y **no modificar `alta`**. Una prueba lo comprueba con un escritor simulado.
- **Qué puede enriquecer un enriquecedor y qué requiere confirmación nueva (D10).** Hoy `Enricher._apply_series_match` **sustituye el id externo de la serie** (salvo que esté en `locked_fields`) y rellena descripción, portada y total **solo si están vacíos**. Por tanto:
  - **Alta desde una fuente:** `metadata_source` = esa fuente y **el campo del id externo entra en `locked_fields`**: el enriquecedor **no** puede cambiar la identidad elegida; sí puede rellenar los campos descriptivos que estén vacíos.
  - **Alta manual:** `metadata_source = 'manual'` (el bloqueo total que ya existe): **ningún enriquecedor la toca**. **No se deja en `NULL`**, porque eso permitiría que el enriquecedor la emparejara por título y le pusiera un id externo que **nadie confirmó**.
  - **Vincular una serie manual a una fuente después** es **una acción propia con confirmación** (cambia la identidad) y **no existe hoy**; queda **fuera de esta rebanada**.
- **Deshacer el alta:** solo mientras la serie **no tenga ningún archivo vinculado** ni operación viva. `DELETE /api/series/{id}` hoy solo protege contra una operación viva (**H2**); el «deshacer» de este flujo lo comprueba por su cuenta.

**Qué NO hace:** no vincula archivos, no mueve nada, no fusiona series, no edita las existentes.

### Implementación 2b (`/api/revision/serie/…`): lo que se precisó o añadió

Tres endpoints, todos con `Cache-Control: no-store`, sesión/Basic como el resto de `/api/*`, **sin** dependencia legal y **sin red**:

| Endpoint | Efectos |
|---|---|
| `POST /api/revision/serie/previsualizar` `{clave, candidata? \| manual?{titulo, anio?}, tradicion, decision?, serie_id?}` | **Solo lectura.** Devuelve `accion` (`reutilizar`, `elegir` o `crear`), `existente`, `parecidas[]`, `efectos` (`series_nuevas`, `numeros: 0`, `archivos: 0`) y el `token` de alta **salvo** que falte una decisión (`elegir`) |
| `POST /api/revision/serie` `{token}` | Reutilizar **no escribe**; crear escribe **una fila de `series`** y nada más (ni números, ni archivos, ni búsquedas, ni enriquecimientos) |
| `POST /api/revision/serie/{id}/deshacer` `{operacion_id}` | Borra una serie **creada por esa operación** mientras nada dependa de ella |

| Punto | Qué se hizo y por qué |
|---|---|
| **Tradición** | Campo **obligatorio** y sin valor por defecto en la petición (falta o valor desconocido: 422). La candidata trae una *sugerida* que se devuelve aparte (`tradicion_sugerida`); la guardada es la elegida |
| **Reutilizar** | Dos criterios, **distintos y guardados en el token** (`criterio`): **`identificador`** (la única coincidencia automática: el mismo identificador externo) y **`eleccion`** (`decision: "reutilizar"` + `serie_id`, que debe estar entre las parecidas). **Por identificador se revalida al confirmar:** si la serie ya no tiene ese identificador (cambiado, borrado o movido a otra), **409 `identificador_cambiado`** y vista previa nueva; no se convierte en «elegida por la persona», que nunca ocurrió, ni se redirige a la serie que ahora lo tenga. **Por elección** el `motivo` es siempre `elegida_por_la_persona`: aunque la serie adquiera después ese identificador, no se le atribuye retrospectivamente una coincidencia automática. La serie existente **no se modifica** (una prueba compara la fila entera antes y después). Con el identificador existente no se ofrece «crear otra» (lo impide el `UNIQUE`): `decision: "crear_igualmente"` se ignora |
| **Posible duplicado** | Mismo `f_title_norm` **de Postgres** (no una normalización paralela en Python), **misma tradición** (la elegida) y año compatible (±1; un año desconocido no descarta). Es más estricta que `parecidas_locales` de 2a, que avisa también de otras tradiciones. La regla de ±1 **no es transitiva** (1986 y 1988 no son parecidas entre sí): es una consecuencia aceptada, no un error. Orden fijo (año, id); ninguna preseleccionada ni recomendada |
| **Token de alta** | Propósito `alta`, caducidad de 15 min y **contexto = la `clave` del grupo desde el que se hizo la vista previa**. Como la confirmación recibe **solo** el token, el contexto se lee **de dentro del token firmado** (firma, propósito y caducidad se comprueban igual): la vinculación del contexto con el grupo queda garantizada en la **vista previa** (la candidata de 2a solo vale para su grupo), no en una comparación externa en la confirmación. Lleva `modo`, `origen`, fuente e id, título, año, tradición, descripción y portada, `vistas` (ids de las parecidas que se vieron), `serie_id` (si se reutiliza) y `operacion`. Con firma válida se exige además el esquema (cadenas reales, enumeraciones, UUID canónicos, año no booleano) |
| **Concurrencia (crear)** | Una transacción: **1)** candado de la **operación** (`operacion_id`); **2)** comprobante persistido: ya creada → su resultado, deshecha → 409; **3)** `pg_advisory_xact_lock` sobre `f_title_norm(título)` con prefijo propio (sin año ni tradición); **4)** si ya existe el identificador externo → **reutilización**, no error; **5)** se **repite** la búsqueda de parecidas y, si hay alguna que la persona **no vio**, 409 `aparecieron_parecidas` con las nuevas (si desapareció alguna de las vistas, se crea igualmente); **6)** `INSERT` de la serie en un *savepoint*: si salta el `UNIQUE` del identificador (otra confirmación con otro título, que usa otro candado), se trata como reutilización; **7)** se inserta el comprobante y se purga lo antiguo, y se hace `commit`. **Cierra H4 en este flujo**; `DiscoveryService.get_or_create_series` (la ruta HTML antigua de Descubrir) **no se ha tocado** y conserva la carrera |
| **Reintentos y comprobante** | La operación se persiste en **`alta_operaciones`** (migración 0018; ver «El comprobante de la operación»). Confirmar el **mismo token** otra vez —también a la vez, o tras reiniciar— devuelve **la misma serie** con `repetida: true` y no crea otra; si esa operación se **deshizo**, devuelve **409 `alta_deshecha`** y nunca la recrea. La procedencia sigue guardando el `operacion_id` (no es un token ni un identificador de sesión: es el UUID de la vista previa). Adición al esquema de D1 |
| **Procedencia (D1)** | `Series.metadata_["alta"]` = `{version: 1, origen, fuente, id_externo, desde_grupo, fecha, tradicion_elegida: true, operacion_id}`. Nunca el token ni nada de sesión. `fusionar_metadata(actual, cambios)` es la regla para cualquier escritor futuro (fusionar por clave de primer nivel, no tocar `alta`); la API de series hoy **no** puede escribir `metadata_`, `metadata_source` ni `locked_fields` |
| **Identidad frente al enriquecedor (D10)** | Alta **manual**: `metadata_source = 'manual'` (la query del enriquecedor la excluye) y sin identificador. Alta **desde una fuente**: `metadata_source` = esa fuente y el campo del identificador en `locked_fields` (segunda barrera: la primera es que, con el identificador puesto, el enriquecedor no la selecciona). **Excepción conocida, corregida aparte:** la query del enriquecedor no mira `gcd_id`, así que a una serie con identidad GCD elegida le podía **añadir** un id de Comic Vine por título; **no es un comportamiento válido** (conservar `gcd_id` no prueba que el otro id sea de la misma edición) y se corrige en una PR independiente. Asociar otra fuente a una serie ya identificada será una acción explícita y confirmada |
| **Deshacer** | Solo con el `operacion_id` que devolvió **la confirmación que creó** la serie (`deshacer` en la respuesta; una reutilización no lo devuelve). El permiso lo da **el comprobante** (`alta_operaciones`: esa operación, esa serie, estado `creada`), no un campo de la serie: una serie reutilizada, o con la procedencia de otra operación, **nunca** se borra desde aquí, y una reutilización no deja comprobante. Se niega (409, con `motivo`) si tiene **archivos** vinculados, **números** (más estricto que «archivos»: protege el candado, ver abajo), una **operación de asignación viva** o **deseados** (o una política de búsqueda distinta de `ninguno`). Al borrar, **la misma transacción** marca la operación `deshecha`. Segunda llamada: 404 |
| **Deshacer y concurrencia** | Bloqueos en un **orden común** a confirmar, repetir y deshacer: **1)** la operación (candado consultivo por `operacion_id`), **2)** el título normalizado (solo al crear), **3)** la fila de la serie (`FOR UPDATE`, solo al deshacer): nadie toma uno posterior antes que uno anterior, así que no hay interbloqueo. Quien cuelgue un **número nuevo** (`INSERT` en `issues`, que toma `FOR KEY SHARE` por la clave foránea) espera a ese candado o lo hace esperar, y al despertar el deshacer ve el número y se niega (dos pruebas, una por sentido). **Requisito para 2d:** vincular archivos a números ya existentes de la serie no toma ese candado por sí solo; 2d debe tomar `FOR SHARE` sobre la serie antes de comprobar. Mientras no exista 2d, ese camino no existe |
| **Efectos** | Una prueba cuenta las sentencias: la vista previa no emite ningún `INSERT`/`UPDATE`/`DELETE`; confirmar crea emite dos `INSERT` —la serie y su comprobante— tras los candados (más la purga acotada del propio comprobante); reutilizar no escribe nada; `files`, `issues`, `wishlist` y `asignacion_operaciones` quedan **idénticos** (rutas y nombres incluidos) |
| **Portada** | Solo se guarda si cumple la política de H1 **también al confirmar** (la firma no garantiza que una URL sea segura) |
| **Grupo** | La vista previa exige que el grupo exista (404 si no); la confirmación **no** lo vuelve a exigir (puede haberse vaciado ya) |

#### El comprobante de la operación (`alta_operaciones`, migración 0018; opción A, decidida en la revisión)

La idempotencia vivía en la propia fila de `series`, y deshacer la borra: reenviar el token original, **si aún no había caducado** (≤ 15 min), la creaba otra vez y **revertía el deshacer**. Ahora el comprobante sobrevive a la serie.

| Punto | Contrato |
|---|---|
| **Tabla** | `alta_operaciones(operacion_id uuid PK, series_id uuid, estado creada\|deshecha, token_hasta, creada, actualizada)`. **Sin token, sesión, credenciales ni título.** `series_id` **no es clave foránea**: borrar la serie no borra su comprobante (ni `CASCADE` ni `SET NULL`) |
| **Atomicidad** | Crear la serie y registrar la operación: **una transacción**. Deshacer (borrar la serie) y marcar `deshecha`: **una transacción**. Un fallo antes del `commit` no deja ni serie ni comprobante parcial (probado en el registro y en el `commit`) |
| **Serialización** | Confirmar, repetir y deshacer de la **misma** operación se coordinan por el mismo candado consultivo de `operacion_id`, el **primero** de un orden común (operación → título → serie) |
| **Repetir** | Operación `creada` → el mismo resultado (`repetida: true`), sin crear otra serie. Si la serie ya no existe por otra vía (p. ej. `DELETE /api/series`) → **409 `alta_serie_ausente`**: no se recrea |
| **Deshacer prevalece** | Operación `deshecha` → **409 `alta_deshecha`**, nunca recrea. Un deshacer de una operación **aún no confirmada** no hace nada (no hay serie) y **no deja comprobante**: no la envenena |
| **Reutilización** | **No escribe** (sin cambios en su contrato) y por tanto **no deja comprobante** ni da permiso para borrar nada. Persistir también su resultado sería ampliar el efecto aprobado de ese camino: no se hace |
| **Retención** | **24 h Y token caducado** (lo que tarde más): se conserva mientras pueda existir un token de ejecución válido asociado (`token_hasta` es la caducidad del propio token). Se purga de forma **acotada** (100 por confirmación, `SKIP LOCKED`), solo `alta_operaciones`, **nunca series**, al crear. **No es un historial de auditoría.** Tras purgar, un token caducado **nunca ejecuta** un alta: se rechaza por caducado y hay que rehacer la vista previa |
| **Bajada** | Destructiva: se pierden los comprobantes. Se **niega** si queda alguno con el token todavía válido (bajar permitiría recrear una serie deshecha); toma `ACCESS EXCLUSIVE` antes de contar |
| **Revisión** | `0018` (la última en `main` y en todas las ramas era la `0017`) |

**Qué no hace 2b:** vistas HTML, vista previa de archivos, vincular, fusionar series, editar las existentes, ni consultar fuentes reales.

#### Límites de tamaño de los tokens de candidata y alta (corrección posterior a #97; ADR 0008, apartado 1)

**Qué había.** `candidata` (vista previa del alta) y `token` (confirmación) aceptaban como mucho **8.000** caracteres, un número que no salía de ningún cálculo, mientras que el productor firmaba sin cota lo que devolviera una fuente (título, identificador, portada). El límite de la vinculación (#103) sí estaba calculado; estos dos no.

**Qué se midió** (con `crear_token_*`, `ensure_ascii=False` + base64 URL-safe + firma, es decir, la serialización real; no multiplicando a ojo). De las cifras estimadas antes a mano (4.625 / 5.889 y 14.625 / 15.889), solo la primera coincide con una medición (la candidata ASCII); las demás **no eran estos máximos** y no se usaron. El primer cálculo de esta corrección (17.649 / 23.013) tampoco valía: suponía cuatro bytes por carácter también en la clave del grupo (ver abajo).

| Caso | Longitud del token |
|---|---|
| Candidata normal (título y id cortos, descripción de 1.000 caracteres) | 1.765 |
| Candidata con TODO en sus cotas, ASCII | 4.625 |
| Alta que reutiliza, todo en sus cotas, ASCII | 4.861 |
| Alta que crea con 100 vistas, todo en sus cotas, ASCII | 9.993 (el límite antiguo la rechazaba) |
| Candidata, textos de 4 bytes y clave de 1000 caracteres de 4 bytes | 17.645 |
| Alta que crea con 100 vistas, textos y clave de 4 bytes | 23.013 |
| Candidata, textos de 4 bytes y clave de 1000 controles (seis bytes) | **20.313** (= `MAX_TOKEN_CANDIDATA`) |
| Alta que crea con 100 vistas, textos de 4 bytes y clave de controles | **25.681** (= `MAX_TOKEN_ALTA`) |
| Un alta con N series parecidas, título corto, ASCII (script de reproducción) | 5.665 con 100; 6.497 con 116; 8.265 con 150 (rechazada por el límite antiguo) |

**La clave del grupo pesa más que los demás textos.** Es la ruta de la carpeta tal como está en `files.file_path` (`"/".join` de los nombres de carpeta): se usa tal cual porque identifica al grupo, no se depura ni se renombra. Un nombre de carpeta de Linux puede llevar cualquier byte salvo `/` y NUL, es decir, controles, y `json.dumps(..., ensure_ascii=False)` escribe los controles como `\u00XX`: **seis bytes**, no cuatro. Un barrido de los 1.112.064 puntos de código con el serializador real lo confirma: 27 caracteres pesan seis bytes (los controles U+0000–U+001F salvo `\b \t \n \f \r`, que pesan dos) y ningún otro pasa de cuatro; el NUL no puede estar en la clave (Postgres no lo guarda). Los demás textos del token (título, identificador, descripción, portada) pasan por `texto_firmable` y no pueden llevar esos controles. Por eso el máximo se calcula con una clave de 1000 caracteres U+0001, y una prueba compara ese cálculo con el efecto de una clave de cuatro bytes (más de 2.600 caracteres de diferencia).

**Qué cota es conservadora.** La clave real nunca llega a 1000 caracteres (el tope de la petición): `files.file_path` es `String(1000)` y la clave es un prefijo de la ruta, de modo que como mucho mide ≈ 970 con la biblioteca de las pruebas (algo más con una ruta más corta, nunca 1000). La portada real empieza por un host ASCII (un byte por carácter, no cuatro). Por eso un token que sale del servicio queda unos cientos de caracteres por debajo del máximo (las pruebas fijan esa holgura) y **el máximo de la candidata no se puede alcanzar de extremo a extremo**: la vista previa necesita un grupo con esa clave. El del alta sí se alcanza, porque su contexto viaja dentro del token y la confirmación no busca el grupo: una prueba firma un alta de exactamente 25.681 caracteres, la envía por HTTP y el servicio la procesa.

**Qué se confirmó con el código anterior** (script de reproducción contra `main` en `94d35e2`): (A) una candidata con todos sus campos dentro de las cotas del sistema pero en texto CJK (título 500, descripción 1000, carpeta 500, portada 300) mide 8.749 y la confirmación del alta 8.917: el esquema las **rechazaba con `string_too_long`**; (B) una fuente que devuelva un título de 9.000 caracteres ASCII se firmaba sin queja (12.305) y se rechazaba después; (C) un alta que crea con 150 series parecidas medía 8.265 y se rechazaba; (D) un sustituto suelto de Unicode (`"\ud800"`) en un título hacía que `crear_token_candidata` lanzara `UnicodeEncodeError`, es decir, un 500 en la búsqueda entera. **Lo que no se confirmó:** que el caso corriente se vea afectado (una candidata normal mide ≈ 1.800) ni que las fuentes reales devuelvan hoy textos que lo provoquen; no se ha consultado ninguna fuente real.

**Qué se corrigió.**
- **Cotas de campo** (`tokens_revision.py`), las que el alta ya podía guardar: título 500 (`Series.title`), identificador 255 (`tebeosfera_slug`), portada 500 (`Series.cover_url` y la política de portadas), descripción 1000 (el recorte que ya existía), año dentro de una `SmallInteger`, clave de grupo 1000 y **como mucho 100 series parecidas** firmadas en `vistas`.
- **Texto firmable.** Sin sustitutos sueltos de Unicode (no se codifican) ni controles salvo tabulador y saltos de línea (Postgres no admite el NUL en un `text`, y JSON escribe cada control con seis bytes, lo que rompería la cota).
- **Productor** (`candidata_firmable`): ajusta lo que puede (título sin espacios ni controles, descripción depurada y recortada, portada o año omitidos si no caben) y **descarta** la candidata cuyo título o identificador no caben o no son firmables, **con un aviso** en la respuesta de `descubrir` (no en silencio). **Esto ocurre ANTES de las consultas locales**: un resultado descartado no llega a la base (el identificador de Tebeosfera es texto y va en un `IN` de SQL), y las consultas, las señales, lo mostrado y el token trabajan con la misma representación depurada.
- **Verificadores**: exigen las mismas cotas aunque la firma sea válida.
- **Límites de la petición**: `MAX_TOKEN_CANDIDATA` (20.313) y `MAX_TOKEN_ALTA` (25.681), **calculados** como el token más largo que se puede emitir y verificar (cada texto en su cota, 4 bytes por carácter, año de seis caracteres, una fuente de las que el servidor emite y una `clave` de 1000 controles de seis bytes), y no un número redondo.
- **Parecidas.** Un alta que **crea** con más de 100 series parecidas no emite token (`422 demasiadas_parecidas`, sin efectos): firmar la lista de las que vio la persona era lo único que no tenía cota. Reutilizar una existente no firma ninguna y sigue funcionando con cualquier número.

**Qué no cambia.** El formato, la firma y el máximo del token de vinculación (`MAX_TOKEN_VINCULACION`; una prueba lo fija). Ningún límite de la ficha de 2c/2d.

**Hallazgo previo, sin tocar.** El máximo del token de vinculación se calculó con una clave de cuatro bytes por carácter: con una clave de 1000 controles (seis bytes) el peor caso medido es 58.697, no 56.029. Se registra aparte; esta corrección no lo modifica.

**Limitaciones conocidas.** (1) Un sustituto suelto de Unicode escrito como `\ud800` en el JSON de **cualquier** petición lo rechaza el esquema, y el manejador de errores de validación de FastAPI intenta devolverlo en el cuerpo del `422` y falla (500): es del marco, no de los tokens, y queda sin tocar. (2) Los máximos son cotas de seguridad, no previsiones: una candidata normal usa una décima parte del máximo.

## C. Vista previa de los registros afectados (números, ediciones y conflictos)

**Entrada:** el grupo y la serie elegida. **Solo lee**: `SELECT` y **`stat` de la ruta de origen de cada archivo** (metadatos; sin leer contenido). Es una ampliación consciente respecto a la rebanada 1: sin saber si el origen existe, la vista previa mentiría con las 14 filas obsoletas. **Sin hash, sin red, sin escribir.** Como vincular no mueve nada, **no hay ruta de destino que calcular ni comprobar**.

**Todos los archivos empiezan sin marcar.** No existe «seleccionado por defecto». La persona marca los que quiere vincular; **marcar los que no tienen conflicto no es un valor por defecto**, y un botón «marcar los N sin conflicto» **no forma parte de esta primera entrega**. Sin ningún archivo marcado **no se emite token** y no se puede confirmar.

**Por archivo** (`archivos[]`):

| Campo | Contenido |
|---|---|
| `numero_propuesto`, `numero_origen` | Del nombre (`parse_comic_filename`); **editable**; `nombre`/`ninguno` |
| `edicion` | `edition_kind` → `Issue.format` (B15) |
| `ruta_actual` | Ruta **relativa a la biblioteca**, que **se conserva**: «se conservará su nombre y su carpeta» |
| `estado` | Ver abajo |
| `conflictos` | Las señales de la rebanada 1 **recalculadas contra la serie elegida** |
| `marcado` | Lo que la persona marcó; **vacío al principio** |

**Estados** (nombres neutros; **no existe «lista»**): `se_vincularia` · `requiere_numero` · `numero_repetido_en_el_grupo` · `numero_ya_existe` · `colision_de_edicion` (B15) · `ya_vinculado` · `origen_no_encontrado` («registro pendiente de verificar, no archivo confirmado») · `con_conflicto_de_carpeta` · `en_curso` (operación de asignación viva) · `fuera_de_la_pagina`.

**Límite por confirmación y por vista previa (D8):** **100 archivos como hipótesis inicial conservadora**, no validada ni garantía de tiempo; sirve para acotar los `stat` y la transacción. El grupo se recorre **por páginas con cursor** (ver 2c); lo que no está en la página sale `fuera_de_la_pagina`. **El límite de bytes (4 GB) pertenece a «organizar», no a vincular**, que no mueve bytes.

**Cualquier cambio regenera la vista previa y el token.** Cambiar un número, marcar o desmarcar un archivo o cambiar la serie vuelve a calcular la vista previa **completa** y emite un **token nuevo**. La vista previa **no guarda estado en el servidor**. **Qué significa «el token anterior deja de servir» y qué no:** ver «Sustitución de tokens» en la implementación 2c: sin persistencia, el servidor **no puede** invalidar un token anterior; la interfaz solo conserva el último, y 2d re-verifica todo dentro de la transacción.

**Salida:** JSON + vista, y el token de vinculación.

### Implementación 2c (`POST /api/revision/vinculacion/previsualizar`): lo que se precisó o añadió

**Entrada:** `{clave, series_id, numeros?, marcados?, cursor?}`. `numeros` (id de archivo → número) son las **modificaciones explícitas** de la persona (un texto vacío quita el número); `marcados` son los archivos que ha marcado. **Nada viene marcado y no hay serie ni número por defecto.** **Solo lectura:** `SELECT` y `stat` de la ruta de cada archivo (metadatos, en un hilo aparte); **sin leer contenido, sin hash, sin red, sin consultar fuentes, sin escribir** (ni `Issue`, ni `files`, ni alias) y **sin calcular destinos**: vincular conserva el nombre y la ruta. No existe el endpoint que ejecuta (2d).

| Punto | Qué se hizo y por qué |
|---|---|
| **Lo que se trata: páginas** | Los archivos pendientes del grupo (los mismos que la rebanada 1), ordenados por nombre e id, **de 100 en 100** (`LIMITE_ARCHIVOS`, hipótesis conservadora D8: no validada ni garantía de duración). **Paginación por cursor:** `cursor` (opcional) es una posición `(nombre, id)` y la respuesta trae `pagina.siguiente`; es una **clave de orden estable**, así que sigue señalando el mismo punto aunque otros archivos se vinculen entre peticiones. Se puede llegar a **cualquier** archivo del grupo aunque los de la primera página estén bloqueados. **La selección, los números editados y el token valen solo para los archivos de la página**: uno pedido que está en otra página sale `fuera_de_la_pagina` (no marcable, no entra en el token). `pagina` informa de `desde`/`hasta`/`en_el_grupo`/`hay_mas`. Un archivo **pedido** que no es del grupo es **422 `archivo_ajeno_al_grupo`**, salvo que ya esté vinculado: sale `ya_vinculado`. Un cursor mal formado es 422 `cursor_no_valido`; uno al final da una página vacía |
| **Número y edición** | Del nombre (`parse_comic_filename`) y de `edition_kind` → `Issue.format` (`EDITION_KIND_A_FORMAT`, el mismo mapa que usa la asignación), salvo lo que la persona edite (`numero_origen`: `nombre`, `persona`, `ninguno`). **No se aplican las cohortes** del importador (necesitan la foto de todos los archivos): un prefijo de orden de lectura puede dejar el número vacío, y entonces se pide a mano (`requiere_numero`). Máximo 20 caracteres (`Issue.issue_number`) |
| **Señales** | `senales_contra_serie` (la función de la rebanada 1 y 2a) evaluada contra la **serie elegida** con **todos** los archivos del grupo. Las señales que citan un archivo van en su `conflictos` (**también las minoritarias**: la mayoría no las oculta); las del grupo, en `avisos_de_grupo` |
| **Conflicto de carpeta** | Es **informativo, no bloqueante** (decisión aceptada en la revisión): si una señal de severidad «conflicto» cita al archivo, su estado es `con_conflicto_de_carpeta`, **se puede marcar** con las señales visibles y sin preselección; la persona eligió la serie sabiéndolo. **La confirmación (2d) no podrá ocultar que incluye registros en conflicto** (debe mostrarlos y contarlos). Los impedimentos reales (abajo) sí impiden marcar |
| **Número ya existente** | `numero_ya_existe` = la serie ya tiene un `Issue` con ese número y edición **y un archivo vinculado a él** (otra copia: D5, solo se bloquea). Un `Issue` **sin archivo** (p. ej. de un enriquecedor) **no bloquea**: se reutilizaría y consta `issue_existente: true`. `colision_de_edicion` = ese número existe con **otra** edición (B15) |
| **Número repetido (copias)** | La vista **identifica todos** los números repetidos de la página (`repetido_con`, `totales.numeros_repetidos`, sin distinguir mayúsculas) pero **no los bloquea por sí solos**. **Regla:** la selección ejecutable no puede contener dos archivos con el mismo número. **Marcar solo uno permite vincularlo y el otro queda pendiente**; marcar los dos bloquea a ambos (`numero_repetido_en_el_grupo`: *«marca solo uno de los dos»*); marcar ninguno no bloquea nada. Un marcado bloqueado por otro motivo no cuenta. **No se elige, fusiona ni elimina ninguna copia automáticamente** y no se obliga a falsear el número de una (D5 sigue abierta: esto permite una elección humana sin falsear el catálogo). Los repetidos entre páginas distintas no se ven juntos: si luego se vincula la segunda copia, será `numero_ya_existe` |
| **Precedencia (varios impedimentos)** | El `estado` es el **primero** de: `ya_vinculado` › `en_curso` › `origen_no_encontrado` › `origen_no_verificable` › `requiere_numero` › `numero_repetido_en_el_grupo` › `colision_de_edicion` › `numero_ya_existe`. **Todos** los impedimentos constan, en ese orden, en `motivos` (nada se oculta). Sin impedimentos: `con_conflicto_de_carpeta` o `se_vincularia`. **`numero_repetido_en_el_grupo` solo aparece entre archivos marcados y ejecutables** (ver «Número repetido»). No existe «lista» |
| **Errores de disco** | **`origen_no_encontrado`** (`FileNotFoundError` con la biblioteca accesible): «registro pendiente de verificar, en la ruta registrada no hay ningún archivo». **`origen_no_verificable`** con `causa`: `permiso`, `error_de_lectura` (cualquier otro `OSError`), `no_es_un_archivo` y **`biblioteca_no_accesible`** (el archivo no está **y la carpeta de la biblioteca tampoco responde**: un volumen desmontado no es una colección de archivos desaparecidos). Su texto dice **«No significa que haya desaparecido»**. Los dos bloquean. Si ≥ 5 archivos y **todos** faltan con la biblioteca accesible, `avisos_de_grupo` añade que puede ser el disco. *Límite conocido:* un punto de montaje vacío con la carpeta presente no se distingue de archivos borrados (para eso está el aviso); no se lista la carpeta |
| **Q1 del ADR 0007** | «¿Se admite vincular un archivo cuyo origen no se pudo comprobar?»: **no**, y ahora con un estado propio (`origen_no_verificable`) distinto de `origen_no_encontrado` |
| **Marcar** | `marcable` = sin impedimentos. `incluido_en_token` = marcado **y** marcable. Un archivo marcado y bloqueado **consta** (`marcado: true`) pero **no entra** en el token y se cuenta en `totales.marcados_bloqueados` |
| **Token `vincular`** | Solo si hay al menos un archivo marcado y ejecutable; si no, `token: null` y `motivo_sin_token` (sin marcados, o ninguno ejecutable). Contexto: la `clave` del grupo (leída del propio token, como en el alta); la `series_id`, el `operacion_id` y, por archivo, `(id, número, formato, tamaño, mtime_ns)` van **firmados dentro** (los de `stat`, no un hash). Esquema exigido con firma válida (UUID canónicos, formatos de la enumeración, números recortados de ≤ 20, enteros no booleanos, ≤ 100, sin ids repetidos). Ni rutas, ni nombres, ni hash |
| **Totales** | `marcados`, `a_vincular`, `marcados_bloqueados`, `sin_marcar`, `numeros_repetidos`, `por_estado`. Consultas constantes (≤ 8) con 20 o con 100 archivos |
| **Logs** | El servicio no registra nada: ni rutas ni nombres (probado) |

#### Sustitución de tokens (decidida en la revisión: opción A)

**Decisión:** para la primera entrega, **una vista previa nueva no revoca las anteriores**. Cada token autoriza **exclusivamente su fotografía**, caduca a los 15 min y exige reverificación en 2d. **No se añade una tabla de generaciones ni se reutiliza `alta_operaciones`.** Lo que sigue es el razonamiento y las alternativas descartadas por ahora.

La ficha pedía que, al crear una vista previa nueva, **«el token anterior deje de servir»**. Con tokens firmados **sin estado en el servidor eso no es posible**: emitir uno nuevo no cambia nada que el anterior compruebe. Hoy, por tanto:
- **Cada token es una fotografía firmada e independiente** que ejecuta exactamente la vista previa que lo emitió y **caduca a los 15 min**. Dos vistas previas dan dos tokens válidos a la vez (una prueba lo documenta).
- **Lo que sí garantiza la arquitectura:** (1) la interfaz (2e) solo conserva el **último** token; (2) 2d **vuelve a calcular las precondiciones dentro de la transacción** y omite por archivo lo que haya cambiado (`ya_vinculado`, `en_curso`, huella `(tamaño, mtime_ns)` distinta…); (3) la idempotencia por `operacion_id` impide ejecutar dos veces el **mismo** token; (4) ejecutar un segundo token sobre los mismos archivos los deja `ya_vinculado`, no es un error.
- **Riesgo residual:** una pestaña olvidada puede ejecutar una vista previa **anterior** —que la persona llegó a ver y confirmar— dentro de los 15 min, por ejemplo con una selección que luego cambió.
- **Opciones para invalidar de verdad (cada una exige persistencia: no se implementa sin decisión):**
  | Opción | Qué es | Contras |
  |---|---|---|
  | **A** | Aceptar la semántica de arriba (tokens independientes y caducidad corta) y **reescribir la frase de la ficha** | El riesgo residual existe |
  | **B (recomendada si se quiere invalidar)** | Tabla propia de **generación por `(clave, series_id)`** (migración nueva): la vista previa la incrementa y el token lleva su generación; 2d rechaza un token cuya generación ya no es la vigente | Escribe en la vista previa (rompe su «solo lectura») o exige un paso aparte; migración |
  | **C** | Reutilizar `alta_operaciones` | **No**: su contrato es el comprobante de un alta de serie, con retención y bajada propias; mezclarlo cambiaría ambos |
  La opción B convertiría la vista previa en una operación que escribe; queda **descartada por ahora** (decisión de la revisión).

## D. Confirmación explícita y vinculación

> **El contrato técnico definitivo de la ejecución está en «Contrato técnico de 2d» (más abajo, tras la implementación 2c)** y prevalece sobre lo que sigue donde difieran (resultado persistido en tabla propia, `422` en lugar de `400`, conflictos firmados, orden de bloqueos).

**La confirmación solo acepta el token.** `POST /api/revision/vinculacion` recibe **únicamente** `{token}`: ni números, ni selección, ni serie. Todo lo que cambie la operación aprobada **ha tenido que pasar por una vista previa nueva** (bloque C), así que **lo que se ejecuta es exactamente lo que se vio**. El servidor **vuelve a calcular** las precondiciones dentro de la transacción y **omite por archivo** lo que haya cambiado desde entonces (`cambio_desde_la_vista_previa`, `en_curso`, `origen_no_encontrado`…) **sin abortar** el resto.

**Ejecución (ADR 0007): una transacción, sin ficheros.** `SELECT … FOR UPDATE` de las filas en orden de id, reverificación, confirmación de todo lo aceptado **o de nada**. **No hay segundo plano, ni progreso, ni nada que reconciliar:** la respuesta lleva el resultado completo.

**Semántica única de reintentos.** La clave es el **`operacion_id` del token**:

| Situación | Respuesta |
|---|---|
| Primer envío de un token válido | `200` con el resultado |
| **El mismo token otra vez** (con o sin caducidad, si la operación ya se ejecutó) | `200` con **el mismo resultado**, reconstruido; **no ejecuta nada** |
| Token válido, **sin ejecutar** y caducado | `410`: «caducó; repite la vista previa» |
| Dos envíos **simultáneos** del mismo token | Se serializan por un candado sobre el `operacion_id`; el segundo recibe el resultado del primero |
| Token alterado, de otro propósito o de otro contexto | `422` (antes `400`; ver el contrato de 2d) |
| Otro token distinto sobre archivos que ya están vinculados | Esos archivos salen `ya_vinculado`; no es un error |

Un token usado **no se «rechaza»** (eso sería otra semántica): se devuelve su resultado.

**Recuperación del informe.** Cada archivo vinculado lleva `metadata_["vinculo"]["operacion_id"]` (ADR 0007). Para reconstruir el informe de un lote: con el token vigente se conoce **el conjunto pretendido** (los ids están firmados dentro) y **cuáles quedaron vinculados**; con el token caducado solo se puede decir **qué quedó vinculado**, **no qué se pretendía**, y **se dice así**. Como la operación es atómica no hay un estado intermedio que reconstruir.

**Informe honesto:** cuenta cada estado; nunca anuncia éxito si algún archivo no quedó vinculado.

**Alias (D7, aceptada):** **desactivado por defecto**. Es una casilla **separada y explícita** («Recordar este nombre para las próximas descargas»); un alias aprendido hace que las descargas futuras con ese nombre se asignen **sin preguntar**, justo el fallo que la rebanada 1 evita.

### Contrato técnico de 2d (`POST /api/revision/vinculacion`): definitivo, **sin implementar**

Sustituye lo que bloque D y el ADR 0007 dejaban abierto. Nada de esto se implementa hasta aprobarlo. Entrada: `{token}` (solo el token; `extra="forbid"`). Efectos: **una transacción** sobre `files`, `issues` y una tabla nueva de resultados (migración **0019**); **ningún fichero** (ni mover, ni copiar, ni renombrar, ni leer contenido, ni hash, ni red).

#### 1. Idempotencia y resultado tras reiniciar

| Punto | Contrato |
|---|---|
| **Dónde se guarda el resultado** | Tabla **propia** `vinculacion_operaciones` (migración **0019**; la última en `main` y en todas las ramas es la 0018). **No se reutiliza `alta_operaciones`**: su contrato es el comprobante de un alta de serie (estados `creada`/`deshecha`, sin informe). Columnas: `operacion_id uuid PK`, `series_id uuid` (**sin FK**: borrar la serie no borra el informe), `resultado jsonb` (esquema versionado abajo), `token_hasta timestamptz` (el `exp` del token), `creada timestamptz`. **Ni token, ni sesión, ni credenciales, ni rutas, ni nombres, ni hash** |
| **Inmutable** | El `resultado` se **escribe una sola vez**. La aplicación nunca hace `UPDATE`, y la migración añade un **disparador `BEFORE UPDATE`** que lo rechaza (solo se permite `DELETE`, para la purga): ni un fallo de programación puede reescribir un informe. Lo que se muestre además al responder (el **nombre actual** del archivo, `nombre_actual`) es **presentación**, va fuera de `resultado` y puede cambiar sin que cambie el informe original; repetir un token devuelve el `resultado` **idéntico byte a byte** |
| **Qué contiene `resultado` (v1)** | `{version: 1, global, totales, archivos: [{id, estado, motivo, numero, formato, issue_creado, conflictos: [códigos]}]}`. **Todos** los archivos del token, también los omitidos y su motivo (la procedencia de los vinculados no basta para reproducir un informe que también tiene fallos). Los **nombres** no se guardan: se leen de `files` al mostrar el informe (el nombre actual; si el archivo ya no existe, solo su id) |
| **Misma transacción** | El resultado se escribe en la **misma transacción** que los vínculos. Si falla, **no hay fila**: reintentar el mismo token ejecuta de nuevo (no hubo efectos) |
| **Reiniciar** | Nada vive en el proceso: el informe y la idempotencia salen de Postgres. Prueba: otro motor y otras sesiones entre la ejecución y la repetición |
| **Semántica de un token (tabla única)** | Se verifica firma, propósito y esquema **ignorando la caducidad** para leer su `operacion_id`; después: |

| Situación | Respuesta |
|---|---|
| Token alterado, de otro propósito o con esquema inválido | `422 token_invalido` (la ficha decía 400; se unifica con el resto de endpoints) |
| **Hay fila de esa operación** (token vigente **o caducado**) | `200` con **el mismo resultado**, `repetida: true`. No ejecuta nada |
| No hay fila y el token **no ha caducado** | Se ejecuta |
| No hay fila y el token **ha caducado** (nunca se ejecutó, **o su resultado ya se purgó**) | `410 token_caducado`: «caducó; repite la vista previa». Si se purgó, el informe ya no se conserva; lo vinculado consta en la procedencia de cada archivo (`metadata.vinculo.operacion_id`) pero **no** se reconstruye el informe |
| Token con **solo parte ejecutable** | Se ejecuta lo ejecutable, se omite el resto con su motivo y se guarda **todo** en el resultado (`global: vinculados_parcialmente`) |
| **Nada** ejecutable | Se guarda igualmente (`global: nada_vinculado`): repetir el mismo token devuelve lo mismo; **para reintentar hace falta una vista previa nueva**. El resultado es definitivo, no un intento a medias |
| Fallo inesperado | `500 error_inesperado`, **sin fila y sin cambios**: repetir el token ejecuta de nuevo |

**Retención del resultado:** igual que el comprobante del alta pero **propia**: se conserva mientras exista un token válido (`token_hasta`) **y** al menos 24 h desde `creada`; purga **acotada** (100 por ejecución, `SKIP LOCKED`), solo de esta tabla, nunca de `files`/`issues`/`series`. **No es un historial de auditoría.** Bajada de la migración: se **niega** si queda alguna fila con `token_hasta` futuro; `ACCESS EXCLUSIVE` antes de contar.

#### 2. Reverificación y atomicidad

**Qué se vuelve a comprobar, dentro de la transacción** (todo lo que la vista previa miró, más lo que podía cambiar):

| Comprobación | Si falla (por archivo) |
|---|---|
| La **serie** existe | **Todo el token**: `409 la_serie_ya_no_existe`; no se guarda fila (no se ejecutó nada; una vista previa nueva dirá qué hay) |
| El **archivo** existe en `files` (y no está descartado) | `archivo_inexistente` / `descartado` |
| **Vinculación previa**: `issue_id` ya es el `Issue` de esta serie y número | `ya_estaba_vinculado` (idempotente: cuenta como bien, no cambia nada) |
| `issue_id` apunta a **cualquier otro** `Issue` (otra serie u otro número) | `ya_vinculado_a_otro`: **nunca se reasigna**; sigue donde estaba |
| **Operación de asignación viva** (organizar) | `en_curso` |
| **Origen** (`stat`, en un hilo, sin leer): ausente / no verificable | `origen_no_encontrado` / `origen_no_verificable` (con su causa; sin afirmar que desapareció) |
| **Ruta registrada** distinta de la que se comprobó (ver «Enlace entre el `stat` y la fila bloqueada») | `cambio_desde_la_vista_previa`: **no se aplica a una ruta nueva la huella de la anterior** |
| **Huella** `(tamaño, mtime_ns)` distinta de la firmada | `cambio_desde_la_vista_previa`. Es una comprobación de **coherencia**, **no una prueba criptográfica del contenido** (un fichero puede cambiar conservando tamaño y mtime): por eso vincular no afirma nada sobre los bytes |
| **Número** vacío o duplicado entre dos archivos del propio token (defensa: el esquema del token lo rechaza) | token inválido (`422`) |
| **Formato / ocupación del `Issue`** (con el bloqueo descrito en «Ocupación del `Issue`») | `colision_de_edicion` / `numero_ya_existe` / `numero_ambiguo`. Un `Issue` existente **sin** archivo y del mismo formato **se reutiliza** |

**Omitir frente a abortar.** Los impedimentos de la tabla son **previstos**: el archivo se omite con su código, se guarda en el informe y **los demás se confirman juntos**. **Cualquier otra cosa** (excepción, `IntegrityError` no previsto, caída de la conexión) es un fallo **inesperado**: se revierte **todo el intento**, no se guarda nada y se responde `500`. No hay estados intermedios ni segundo plano.

#### Enlace entre el `stat` y la fila bloqueada
1. Dentro de la transacción se lee la **ruta registrada** de cada archivo del token (`SELECT id, file_path`) y se hace el `stat` **sobre esa ruta** (en un hilo, sin leer contenido).
2. Después se bloquean las filas (`FOR UPDATE`, por id) y se **vuelve a leer `file_path`**: debe ser **la misma** que se comprobó.
3. Si cambió (otra sesión movió o renombró el archivo, p. ej. *organizar*), ese archivo se **omite** como `cambio_desde_la_vista_previa`: **nunca** se aplica a una ruta nueva la huella obtenida de la anterior. La huella firmada en el token se compara con el `stat` de la ruta comprobada.
4. Prueba: un gancho de pruebas **pausa después del `stat`**, otra sesión cambia `file_path` y se reanuda; el archivo sale omitido y los demás se vinculan.
Límite declarado: entre el `stat` y el `commit` el contenido de un fichero puede cambiar sin que lo veamos; tamaño y `mtime_ns` no son una prueba criptográfica.

#### Ocupación del `Issue` (cómo se impide el doble vínculo)
La restricción real del esquema es `UNIQUE (series_id, issue_number, volume)` y **`volume` admite NULL** (default 1): en una restricción única los NULL **no chocan entre sí**, así que `ON CONFLICT` **no es la garantía** de unicidad ni de ocupación. La garantía es el bloqueo + volver a consultar:
1. **Se serializa cada clave `(serie, número)`** con un candado consultivo de transacción (`vinc_num:` + `series_id` + número, sin distinguir mayúsculas), tomado **en orden de número** (comparación estable) antes de mirar nada. La **edición no entra en la clave**: dos archivos del mismo número y distinta edición son una colisión (`colision_de_edicion`), no dos claves.
2. **Con el candado ya tomado** se **consulta** el `Issue` de `(serie, número)` **sin filtrar por `volume`** (los NULL incluidos) y, si existe, se **bloquea la fila** (`SELECT … FOR UPDATE`; así un *organizar* que enlace un archivo a ese `Issue` —su clave foránea pide `KEY SHARE`— espera) y **se cuenta de nuevo cuántos archivos tiene**. Esa consulta de ocupación se hace **después** de obtener el bloqueo, nunca antes.
3. Decisión por clave: 0 `Issue`s → se crea; 1 `Issue` con otra edición → `colision_de_edicion`; 1 `Issue` **con** archivo → `numero_ya_existe` (el archivo se omite); 1 `Issue` **sin** archivo y misma edición → se reutiliza; **más de uno** (distintos `volume`, o NULL) → `numero_ambiguo` (omitido: no se adivina cuál). Solo **un** archivo por clave puede ganar dentro de una transacción (el token ya no puede traer dos con el mismo número).
4. **Crear:** `INSERT … (series_id, issue_number, volume=1, …) ON CONFLICT (series_id, issue_number, volume) DO NOTHING RETURNING id` con el objetivo exacto de la restricción y `volume = 1` explícito (el valor que escriben los demás caminos). Es una **red de seguridad frente a otros escritores** (organizar, enriquecedor); si no devuelve fila se repite el paso 2 (consulta, bloqueo y ocupación). Nunca sale como `IntegrityError`.
5. Efecto: con dos archivos distintos, mismo número y el `Issue` aún vacío o inexistente, **solo el primero que obtiene el candado se vincula**; el segundo, al obtenerlo, ve el `Issue` ocupado y se omite como `numero_ya_existe`. No basta con que termine habiendo un único `Issue`: se **impide el doble vínculo** que la vista previa bloqueaba.
Mismos campos que `AsignacionService._confirmar` **menos la ruta**: `locked_fields=["series_id","issue_number"]`, `format` del token; el archivo recibe `issue_id` y `metadata_source='manual'`; **`file_path`/`file_name` no cambian**.

**Procedencia por archivo** (fusión JSONB `||`, nunca sustituir el objeto): `metadata.vinculo` v1 = `{version: 1, operacion_id, fecha, serie_id, numero, formato, issue_creado, conflictos: [códigos], previo: {match_status, review_motivo}}`. Sin token ni sesión.

**Conflictos de contexto incluidos: esquema versionado.** El token de vinculación pasa a **versión 2** con `version: 2` y, **por cada archivo, `conflictos` obligatorio** (lista, vacía `[]` si no había): los códigos de las señales de severidad «conflicto» que la persona vio al marcarlo. Ausencia **no** significa «ninguno»: un token **sin `version: 2` o con algún archivo sin `conflictos`** se rechaza (`422 token_invalido`, «repite la vista previa»); **no se conserva compatibilidad** con los tokens de 2c porque nunca hubo ejecución de 2d desplegada. La vista previa (2c) pasa a emitir la versión 2 **en la PR de 2d**. El informe repite los códigos por archivo y cuenta `totales.con_conflicto_incluidos`: **la confirmación nunca los oculta**. Se firman (no se recalculan al confirmar) para informar de lo que se vio.

**Alias:** **no se aprende ninguno en 2d** (D7: sería una casilla propia dentro de la vista previa y del token; se difiere). **Desvincular** tampoco entra: el contrato futuro del ADR 0007 conserva `previo` para poder hacerlo.

**Informe** (`200`): `{operacion_id, repetida, resultado {global (vinculados_todos | vinculados_parcialmente | nada_vinculado), totales {vinculados, ya_estaban, omitidos, issues_creados, con_conflicto_incluidos}, archivos[]}, presentacion {nombres_actuales}}`: `resultado` es **el informe inmutable** guardado; `presentacion` (nombres actuales) se añade al mostrarlo y **no forma parte** de él. **Nunca anuncia éxito si algún archivo no quedó vinculado.** `Cache-Control: no-store`.

#### 3. Concurrencia: orden de bloqueos y pruebas

**Orden único** (confirmar el alta, repetirla, deshacerla y vincular lo comparten; nadie toma uno posterior antes que uno anterior):
1. candado consultivo de la **operación** (`vinc_op:` + `operacion_id`; en el alta, `alta_op:`);
2. candado consultivo del **título normalizado** (solo al crear una serie);
3. fila de la **serie**: `FOR UPDATE` al deshacer el alta; **`FOR SHARE` al vincular** (también cuando solo reutiliza números existentes);
4. filas de **`files`** `FOR UPDATE`, **en orden de id** (y se relee `file_path`);
5. candados consultivos `vinc_num:` **en orden de número**, y después las filas de **`issues`** `FOR UPDATE` en el mismo orden: crear/reutilizar.
`stat` de los orígenes **antes** de los pasos 3–4 (no se retienen filas durante E/S), en un hilo aparte, con el enlace a la ruta descrito arriba.

**Por qué debería no haber interbloqueo — y qué pasa si lo hay.** La compatibilidad de modos de bloqueo es un argumento, **no una prueba**: se comprueba con una prueba de **tres sesiones** (abajo). *Organizar* (`AsignacionService`) toma `FOR UPDATE` solo del archivo y crea `Issue` (`KEY SHARE` de la serie, compatible con el `FOR SHARE` de vincular); *deshacer el alta* toma la serie `FOR UPDATE` y **no** toma archivos; *insertar una operación viva de organizar* pide `KEY SHARE` sobre la fila del archivo y **espera** a que vincular termine (después organizar prevalece sin fila rota, ADR 0007). **Si aun así Postgres detecta un interbloqueo** (`40P01`) o un fallo de serialización, esa transacción es la víctima: **rollback completo, sin resultado persistido y sin efectos parciales**, y la respuesta es `503 conflicto_de_bloqueo` (`Retry-After: 1`, «otra operación coincidió; repite la confirmación»). El mismo token se puede repetir: no hay fila. **No hay reintento automático.**

**Pruebas obligatorias (Postgres real):**
1. **Doble envío simultáneo** del mismo token: un solo conjunto de efectos, ambos `200`, uno `repetida: true`.
2. **Tokens distintos sobre el mismo archivo** (vista previa dos veces): el primero vincula; el segundo ve `ya_estaba_vinculado` (mismo serie y número) o `ya_vinculado_a_otro` (otro número u otra serie) y **nunca reasigna**.
3. **Creación concurrente del mismo número** con archivos distintos: un solo `Issue`; uno vincula, el otro `numero_ya_existe`; sin `IntegrityError` ni 500.
4. **Deshacer el alta a la vez que vincular:** o vincular primero (el deshacer se niega) o el deshacer primero (vincular da `409`); **nunca** una serie borrada con archivos vinculados ni `Issue`s huérfanos.
5. **Organizar ya vivo:** `en_curso`, sin escribir; y organizar que nace mientras vincular retiene el archivo **espera** y gana después sin fila rota.
6. **Serie protegida al reutilizar números existentes:** con la serie bloqueada `FOR UPDATE` desde fuera, vincular **espera**; al borrarse la serie, `409`.
7. **Fallo inesperado** a mitad (inyectado): ni vínculos, ni `Issue`s, ni fila de resultado; reintentar ejecuta.
8. **Omisión previa + confirmación conjunta:** un lote con `en_curso`, huella cambiada, origen ausente y un conflicto de carpeta: se vinculan los demás, el informe cuenta cada estado y **no anuncia éxito**.
9. **Reiniciar** entre ejecutar y repetir; **token caducado con y sin fila**; **purga** (24 h y token caducado, acotada, sin tocar `files`/`issues`/`series`).
10. **Nombre y ruta intactos** (`file_path`, `file_name`, bytes, `mtime`); **sin hash ni red ni lectura de contenido**; ningún alias.
11. **Auth, `no-store`, logs sin rutas ni nombres.**
12. **Enlace del `stat` con la fila:** un gancho pausa **después del `stat`**, otra sesión cambia `file_path` y se reanuda: ese archivo se omite como `cambio_desde_la_vista_previa`, sin aplicar la huella de la ruta anterior; los demás se vinculan. Y la huella distinta con la misma ruta, también omitida.
13. **Doble vínculo por el mismo número** (los dos casos: `Issue` **inexistente** y `Issue` **existente sin archivo**), dos archivos distintos desde dos tokens a la vez: **gana uno**; el otro `numero_ya_existe`; un solo `Issue`; **nunca dos archivos en el mismo `Issue` por vincular**. Un `Issue` con `volume` NULL se encuentra (la búsqueda no filtra por volumen) y no se duplica; dos `Issue`s del mismo número (volúmenes distintos) → `numero_ambiguo`.
14. **Tres sesiones:** vincular retiene la serie (`FOR SHARE`), *organizar* retiene el archivo (`FOR UPDATE`) y *deshacer el alta* espera por la serie (`FOR UPDATE`): no hay interbloqueo; terminan en un orden consistente (organizar, vincular, deshacer se niega por `tiene_archivos`) y ninguna serie queda borrada con archivos vinculados. Con un **interbloqueo provocado** (dos sesiones tomando recursos en orden inverso) la víctima responde `503 conflicto_de_bloqueo`, sin fila de resultado ni efectos parciales, y el token se puede repetir.
15. **Informe inmutable:** un `UPDATE` de `vinculacion_operaciones.resultado` falla (disparador); renombrar un archivo después no cambia el `resultado`; repetir el token devuelve el `resultado` idéntico y solo `nombre_actual` puede variar.
16. **Token versionado:** un token de 2c (sin `version` o sin `conflictos` en algún archivo) se rechaza (`422`); uno con `conflictos: []` se acepta; los códigos firmados salen en el informe aunque el archivo haya dejado de estar en conflicto.
**Mutaciones:** cada defensa de las tablas de arriba se rompe a propósito (bytecode desactivado).

#### Decisiones que este contrato cierra o trae a revisión
- **Cerradas (aceptadas en la revisión):** resultado persistido en tabla propia (0019); bajada de la 0019 negada con filas vigentes; `FOR SHARE` de la serie siempre al vincular; resultado guardado aunque no se vincule nada; `422 token_invalido`; alias y desvincular fuera de 2d.
- **Cierra este contrato:** enlace del `stat` con la ruta bloqueada; ocupación del `Issue` por candado de `(serie, número)` + `FOR UPDATE` + nueva consulta (no por `ON CONFLICT`, que no cubre `volume` NULL); token **versionado** con `conflictos` obligatorio (sin compatibilidad con los de 2c); rollback completo y `503` ante interbloqueo; informe **inmutable** (disparador) y nombres solo como presentación.
- **Declara límites:** tamaño y `mtime_ns` no prueban el contenido; entre el `stat` y el `commit` el fichero puede cambiar; tras purgar no se reconstruye el informe; el informe guarda ids, no nombres.
- **A revisar:** (a) el disparador `BEFORE UPDATE` de la 0019 (función y bajada coherentes, estilo de la 0006); (b) `numero_ambiguo` como motivo previsto nuevo; (c) la clave del candado de número ignora mayúsculas.

#### Implementación 2d: lo que se implementó y lo que se observó

Implementado tal como fija el contrato: `POST /api/revision/vinculacion` `{token}` (`services/vinculacion.py`), migración **0019** (`vinculacion_operaciones` con el disparador `BEFORE UPDATE` que rechaza todo `UPDATE`), token de vinculación **v2** emitido por la vista previa (con `conflictos` explícitos por archivo), y la vista previa alineada con la misma equivalencia de números (sin distinguir mayúsculas) y el impedimento `numero_ambiguo`. Sin alias, sin desvincular, sin contenido, hash ni red; `file_path` y `file_name` no cambian.

| Punto | Precisión de la implementación |
|---|---|
| **«Resultado idéntico»** | Se comprueba como **igualdad del documento JSON persistido** (forma canónica), **no** como identidad de bytes de la respuesta HTTP (el serializador puede variar orden o formato). `presentacion` queda fuera del resultado |
| **Una sola equivalencia de números** | `clave_de_numero` (recortar y pasar a minúsculas) se usa en: duplicados del token, clave y orden de los candados, búsqueda del `Issue` (`lower(issue_number)`), ocupación y la vista previa. El texto presentado se conserva (`5A` se crea como `5A`). Probado: `5A` y `5a` no permiten un doble vínculo |
| **`numero_ambiguo`** | Impedimento previsto: si hay **varios** `Issue` para la clave (volúmenes distintos o `volume` NULL), el archivo se omite, se registra el motivo y **no se modifica ninguno ni se elige volumen** |
| **Comprobación de la serie** | Solo la de `FOR SHARE` (la consulta previa sin bloqueo era redundante y se retiró) |
| **Bajada de la 0019** | Retira, en orden, disparador, función y tabla (el índice se va con ella); se niega con informes de token vigente (`ACCESS EXCLUSIVE` antes de contar) |

**La respuesta se prepara ANTES del commit.** El informe, la presentación (`nombres_actuales`) y la respuesta entera se construyen y validan **antes** de `COMMIT`; el commit es lo último que se hace. Un fallo al leer los nombres o al construir la respuesta todavía **revierte todo** (y «no se ha cambiado nada» es entonces verdad: cero vínculos, cero `Issue`s, cero informe; se prueba). Desde que se pide el commit, un fallo **ya no puede afirmar eso**: se responde **`503 resultado_incierto`** («no se pudo confirmar si se aplicó; repite la confirmación con el mismo token»), con `Retry-After`, y repetir el token devuelve el informe persistido si se aplicó o lo aplica si no. Una cancelación no se convierte en resultado incierto.

**Límite del cuerpo.** El token que acepta `POST /api/revision/vinculacion` mide como mucho **`MAX_TOKEN_VINCULACION`** caracteres: **calculado, no elegido** (100 archivos, número de 20 caracteres, la edición de nombre más largo, tamaño y mtime de 63 bits, todos los códigos de señal como conflicto y una `clave` de 1000 caracteres de 4 bytes: **56.021**). El límite anterior de 20.000 rechazaba con `422` tokens legítimos (el caso de 100 archivos con números 1–100 y 100 MB mide 20.445). Una prueba recalcula el peor caso con un token emitido de verdad y comprueba que los códigos coinciden con los del código fuente de las señales; otra recorre `100 archivos → vista previa → token → POST` con conflictos, números de 20 caracteres y una clave larga.

**Tres sesiones, observado (no forzado).** Con S2 (organizar) reteniendo el archivo, S1 (vincular) tomando la serie `FOR SHARE` y esperando al archivo, y S3 (deshacer) esperando la serie `FOR UPDATE`: el `INSERT` de un `Issue` de S2 (necesita `KEY SHARE` de la serie) **no se bloqueó** tras el `FOR UPDATE` en cola (0,01 s); S2 confirmó, S1 omitió el archivo como `ya_vinculado_a_otro`, y S3 se negó con `tiene_archivos`/`tiene_numeros`. No apareció ningún interbloqueo en ese escenario. **Interbloqueo provocado** (dos sesiones con archivos en orden inverso): Postgres elige la víctima —en la práctica, la sesión que lleva más esperando— y **eso no es una propiedad garantizada del servicio**. La prueba de integración lo **observa** y comprueba la integridad en cualquier caso; la respuesta `503 conflicto_de_bloqueo` con `Retry-After`, el rollback completo y la ausencia de informe se demuestran **de forma determinista** inyectando un `40P01`.

## E. Conflictos sin preselección; duplicados y obsoletas fuera de alcance

- **Ninguna serie preseleccionada**, ni con un único resultado, ni con título exacto (`BATMAN (2025)` frente a `Batman - Saga de Scott Snyder (2019)`).
- **Ningún archivo marcado de antemano**, tenga o no conflicto.
- **Duplicados y las 14 referencias obsoletas:** las segundas salen **bloqueadas** (`origen_no_encontrado`) y **no hay ninguna acción** sobre ninguna de las dos; D5 sigue abierta.

## Contratos (resumen; el detalle se fija en la PR de cada paso)

| Paso | Endpoint propuesto | Efectos |
|---|---|---|
| A | `POST /api/revision/descubrir` `{clave, consulta?}` | Red (solo aquí). Sin escrituras |
| B | `POST /api/revision/serie/previsualizar` y `POST /api/revision/serie` `{token}` | La segunda escribe **solo** `series` (y la procedencia) |
| C | `POST /api/revision/vinculacion/previsualizar` `{clave, series_id, numeros?, marcados?, cursor?}` | `SELECT` + `stat`. Devuelve `archivos[]`, `limite`, `totales`, `avisos_de_grupo`, `token?` y `motivo_sin_token?` (**implementado en 2c**, con `cursor?` y `pagina`) |
| D | `POST /api/revision/vinculacion` `{token}` | Una transacción sobre `files` e `issues`; **ningún fichero** |

Todos exigen sesión/Basic como el resto de `/api/*`, llevan `Cache-Control: no-store`, **no** dependen de la aceptación legal (no son búsquedas ni descargas de P2P) y no registran rutas ni nombres. El HTML reutiliza estos servicios **sin duplicar lógica** (como en 1b).

## Invariantes (se repiten porque son la razón de la rebanada)

No mentir («serie sugerida» no es «clasificada»; «registro» no es «archivo confirmado»). **Nada se clasifica ni se elige solo, ni viene marcado.** **No se mueve, copia, renombra ni borra ningún fichero.** Nada viaja suelto en un formulario: **token firmado con propósito**. Crear serie y vincular son **dos confirmaciones**. **Lo que se ejecuta es lo que se vio.** La red solo a petición y con los límites de cada fuente. Sin dependencias nuevas.

## Pruebas de aceptación (Postgres real, ficheros reales en `tmp`, red simulada; ningún dato personal)

**A — Descubrimiento**
1. **Sin clic no hay red** (cliente HTTP parcheado para fallar).
2. **Fuentes caídas o apagadas:** una que falla no tumba las demás; sin ninguna, el camino «a mano» sigue completo.
3. **Nada preseleccionado:** un único resultado, o uno con título exacto, sale sin serie elegida; el orden es el neutro fijado.
4. **`ya_en_biblioteca` solo por id externo exacto**; el mismo título sin id sale como `parecidas_locales`.
5. **La carpeta contradice al resultado** ⇒ `coincidencia_con_la_carpeta` en conflicto, **con el mismo código que la rebanada 1** (`_Hallazgos` compartido).
6. **Los datos externos se escapan**; las portadas solo salen por el proxy con lista blanca.
7. **Tokens:** manipulado, **de otro propósito**, de otro grupo o caducado ⇒ rechazado; el formulario **no puede colar** `title`, `description` ni `cover_url`.

**B — Alta**
8. **Mismo id externo** ⇒ se reutiliza, no se crea.
9. **Parecida sin id** (mismo `title_norm`, año ±1, misma tradición) ⇒ exige elegir; no se crea ni se reutiliza en silencio.
10. **Tradición obligatoria**, sin valor por defecto.
11. **Concurrencia:** dos altas simultáneas de `Flash (1987)` y `Flash (1988)` (a mano) crean **una**; la otra recibe el aviso de duplicado. Lo mismo con y sin id externo, y con un candidato de fuente frente a uno manual del mismo título.
12. **Aparece una parecida entre la vista previa y la confirmación** ⇒ 409, hay que rehacer la vista previa.
13. **Procedencia** en `metadata_["alta"]` con `version`, **sin token ni sesión**, y **un escritor simulado de `metadata_` no la pisa**.
14. **El enriquecedor no sustituye el id externo** de una serie dada de alta por la persona (`locked_fields`), y **no toca** una manual (`metadata_source = 'manual'`).
15. **Deshacer** solo sin archivos vinculados.
16. **Cero escrituras en A y en la vista previa del alta.**

**C — Vista previa**
17. **Solo `SELECT` y `stat`** (sin hash, sin red, sin escribir); consultas constantes (≤ 4) con 20 y con 2.000 archivos.
18. **Todos sin marcar:** sin ningún archivo marcado **no hay token**; marcar uno lo emite.
19. **Cada estado:** número vacío, repetido en el grupo, ya existente, colisión de edición, ya vinculado, origen no encontrado, en curso, archivo cambiado, fuera del límite.
20. **Las 14 filas obsoletas** salen `origen_no_encontrado`, con «registro pendiente de verificar», y **no se pueden marcar**.
21. **Cambiar un número, una marca o la serie regenera la vista previa y el token**; el token anterior ya no sirve.
22. **No hay destino:** la respuesta no contiene ninguna ruta de destino; `ruta_actual` es relativa.

**D — Confirmación**
23. **La confirmación acepta solo `{token}`:** un cuerpo con `numeros` o `marcados` se ignora o se rechaza (422), nunca modifica la operación.
24. **Nombre y ruta intactos** tras vincular (`file_path`, `file_name`, contenido y `mtime`).
25. **Una transacción:** si algo falla tras decidir el resto, **no queda ningún archivo vinculado**.
26. **Reintentos:** el mismo token otra vez devuelve **el mismo resultado** sin ejecutar nada; **dos envíos simultáneos** se serializan; un token caducado y sin ejecutar da 410.
27. **Un archivo cambia entre la vista previa y la confirmación** ⇒ se omite ese archivo; el resto se vincula.
28. **Recuperación del informe:** tras vaciar la memoria del proceso, el mismo token devuelve el conjunto pretendido y el vinculado; con el token caducado, solo lo vinculado y el texto que lo dice.
29. **Informe honesto:** un lote con un `en_curso` y una `colision_de_edicion` **no** anuncia éxito.
30. **Alias:** por defecto no se aprende; con la casilla, sí.
31. **Vincular y `organizar` a la vez** sobre un archivo: gana el segundo y no queda ninguna fila rota.
32. **Auth, `no-store`, sin rutas ni nombres en los logs.**

**Mutaciones:** cada defensa (marcas, colisión y candado, token y propósito, límites, idempotencia, atomicidad, alias) se rompe a propósito y alguna prueba debe fallar (bytecode desactivado).

**Medición previa (informativa, no bloquea):** un script de solo lectura (`scripts/medicion/medir_descubrimiento.py`, en la Pi, con las fuentes reales y sus límites de cortesía) que, para los 20 grupos mayores, cuente resultados, si el primero cuadra en año ±1 y si la fuente distingue ediciones. **No se afirma que las fuentes encuentren las series**: se mide.

## Entrega en PR (cada una pequeña; ninguna es la interfaz completa)

| PR | Contenido | Escribe |
|---|---|---|
| **H1 (independiente, previa)** | Proteger la descarga de `Series.cover_url` (ver H1) | — |
| **Tebeosfera (independiente)** | 2,5 s como mínimo entre peticiones: configuración, documentación y pruebas | — |
| **2a** | Descubrimiento contextualizado: servicio + JSON + tokens `candidata` | Nada |
| **2b** | Alta: previsualizar y confirmar la serie; colisiones, candado, procedencia, regla de enriquecimiento, deshacer | Solo `series` |
| **2c** | Vista previa de la vinculación (servicio + JSON), con `stat` y sin hash | Nada |
| **2d** | **Vincular** (ADR 0007, aceptado): una transacción, token `vincular`, idempotencia, alias opcional | `files` e `issues`; **ningún fichero** |
| **2e** | Vistas HTML de los cuatro pasos, **verificadas en navegador real** (móvil, claro/oscuro, teclado) | Lo que ya hacen los servicios |
| **Rebanada 3** | **Organizar** y «reubicar» (ficha propia, con relación lote↔operaciones durable si se promete informe tras reinicio) | Ficheros, por el servicio recuperable |

## Decisiones (estado tras la revisión del 2026-10-07)

| Decisión | Estado | Resolución |
|---|---|---|
| **D0** Orden | **Decidida** | Descubrimiento → serie → vista previa → confirmación; «crear a mano» completo sin red ni claves |
| **D1** Procedencia | **Aceptada** | `Series.metadata_["alta"]`, esquema versionado, preservación explícita, sin token ni sesión |
| **D2** Los 17 y la bandeja | Fuera | Sigue abierta; no se toca el contador |
| **D3** Tradición | **Aceptada** | Sugerencia visible y elección explícita, sin valor confirmado por defecto |
| **D4** Perfil por raíz | Fuera | Se infiere y se muestra |
| **D5** Duplicados y obsoletas | Fuera | La vista previa solo las bloquea |
| **D6** Archivos adoptados | **Decidida** | **Vincular en su sitio**; **organizar** es otra operación (rebanada 3); ADR 0007 |
| **D7** Alias | **Aceptada** | Desactivado por defecto; aprendizaje separado y explícito |
| **D8** Límites | **Hipótesis** | 100 archivos (vincular) y 100 archivos / 4 GB (organizar) como **valores iniciales conservadores, no validados ni garantía de duración**; configurables |
| **D9** Candidatas | **Aceptada** | Token firmado con propósito, caducidad y vinculación al contexto |
| **D10** Alta manual | **Redefinida** | `metadata_source = 'manual'` (nadie la enriquece); alta desde fuente con el id en `locked_fields`; vincular una manual a una fuente después es una acción propia con confirmación, fuera de esta rebanada |
| **D11** Tebeosfera | **Decidida** | 2,5 s como mínimo entre peticiones; decisión conservadora **del proyecto**, no una afirmación sobre una política oficial del sitio |

## Hallazgos laterales

- **H1 — `Series.cover_url` sin lista blanca (seguridad).** Entradas: el campo oculto de `POST /ui/descubrir/crear`, `POST /api/series` y `PATCH /api/series/{id}`; también lo escribe el enriquecedor con lo que le devuelve una fuente. Punto de descarga: `GET /ui/series/{id}/portada` → `fetch_and_cache_cover` (`utils/cover.py`), que descarga **en el servidor** con `follow_redirects=True` y **sin ninguna restricción de destino** (solo el proxy `GET /ui/descubrir/portada` tiene lista de nombres). **Condiciones de explotación** (sin etiquetas de riesgo): hace falta poder enviar una petición del mismo origen que cree o edite una serie, o que una fuente devuelva una URL hostil; con `auth_mode = none` eso lo puede hacer **cualquiera que alcance el puerto con el `Host` permitido**, con contraseña, **cualquier sesión autenticada**. Lo que permite: que el servidor haga una petición `GET` a un destino elegido (incluidos servicios de la propia Pi), con el **tiempo de respuesta como canal lateral**; la respuesta solo se devuelve si decodifica como imagen. Lo que **no** permite: leer respuestas que no sean una imagen válida. Un token firmado no cambia nada de esto. **Se corrige en una PR independiente y previa**, que protege el punto común de descarga —también para los registros ya guardados—, valida las **direcciones IP resueltas (IPv4 e IPv6)**, **no sigue redirecciones automáticamente** y **conecta a la dirección ya validada** (una lista de nombres no evita el *DNS rebinding*). La rebanada 2 **no empieza 2b antes de que esté cerrada**.
- **H2 — `DELETE /api/series/{id}`** solo se niega ante una operación de asignación **viva**; no ante archivos ya asignados (queda `File.issue_id = NULL` por `SET NULL`). El «deshacer alta» de esta ficha lo comprueba por su cuenta.
- **H3 — Cortesía con Tebeosfera.** `CLAUDE.md` §4 dice 2,5 s y `config.py` fija 2,0 s. **Decidido (D11): 2,5 s**; se alinea en una PR aparte.
- **H4 — Carrera en `get_or_create_series`.** Comprueba y luego inserta sin tratar la violación de `UNIQUE`: dos altas simultáneas del mismo id externo dan un 500 al segundo en vez de «ya existía». Se corrige en 2b con prueba de regresión.

## Límites de esta ficha

Lectura de código en `main`; **Mylar3 no se ha leído** para esta rebanada y las referencias externas se leyeron sin ejecutarse. **No se ha medido** que las fuentes encuentren las series de la biblioteca real. Los límites de D8 son hipótesis. **Vincular y su deshacer no existen todavía**: el ADR 0007 está «Aceptado» pero sin implementar. No se ha ejecutado nada contra producción ni contra fuentes reales.
