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

**Estados** (nombres neutros; **no existe «lista»**): `se_vincularia` · `requiere_numero` · `numero_repetido_en_el_grupo` · `numero_ya_existe` · `colision_de_edicion` (B15) · `ya_vinculado` · `origen_no_encontrado` («registro pendiente de verificar, no archivo confirmado») · `con_conflicto_de_carpeta` · `en_curso` (operación de asignación viva) · `fuera_del_limite`.

**Límite por confirmación (D8):** **100 archivos como hipótesis inicial conservadora**, no validada ni garantía de tiempo; sirve para acotar los `stat` y la transacción. Lo que exceda sale `fuera_del_limite`. **El límite de bytes (4 GB) pertenece a «organizar», no a vincular**, que no mueve bytes.

**Cualquier cambio regenera la vista previa y el token.** Cambiar un número, marcar o desmarcar un archivo, cambiar la serie o el modo vuelve a calcular la vista previa **completa** y emite un **token nuevo**; el token anterior deja de servir. La vista previa **no guarda estado en el servidor**.

**Salida:** JSON + vista, y el token de vinculación.

## D. Confirmación explícita y vinculación

**La confirmación solo acepta el token.** `POST /api/revision/vinculacion` recibe **únicamente** `{token}`: ni números, ni selección, ni serie. Todo lo que cambie la operación aprobada **ha tenido que pasar por una vista previa nueva** (bloque C), así que **lo que se ejecuta es exactamente lo que se vio**. El servidor **vuelve a calcular** las precondiciones dentro de la transacción y **omite por archivo** lo que haya cambiado desde entonces (`cambio_desde_la_vista_previa`, `en_curso`, `origen_no_encontrado`…) **sin abortar** el resto.

**Ejecución (ADR 0007): una transacción, sin ficheros.** `SELECT … FOR UPDATE` de las filas en orden de id, reverificación, confirmación de todo lo aceptado **o de nada**. **No hay segundo plano, ni progreso, ni nada que reconciliar:** la respuesta lleva el resultado completo.

**Semántica única de reintentos.** La clave es el **`operacion_id` del token**:

| Situación | Respuesta |
|---|---|
| Primer envío de un token válido | `200` con el resultado |
| **El mismo token otra vez** (con o sin caducidad, si la operación ya se ejecutó) | `200` con **el mismo resultado**, reconstruido; **no ejecuta nada** |
| Token válido, **sin ejecutar** y caducado | `410`: «caducó; repite la vista previa» |
| Dos envíos **simultáneos** del mismo token | Se serializan por un candado sobre el `operacion_id`; el segundo recibe el resultado del primero |
| Token alterado, de otro propósito o de otro contexto | `400` |
| Otro token distinto sobre archivos que ya están vinculados | Esos archivos salen `ya_vinculado`; no es un error |

Un token usado **no se «rechaza»** (eso sería otra semántica): se devuelve su resultado.

**Recuperación del informe.** Cada archivo vinculado lleva `metadata_["vinculo"]["operacion_id"]` (ADR 0007). Para reconstruir el informe de un lote: con el token vigente se conoce **el conjunto pretendido** (los ids están firmados dentro) y **cuáles quedaron vinculados**; con el token caducado solo se puede decir **qué quedó vinculado**, **no qué se pretendía**, y **se dice así**. Como la operación es atómica no hay un estado intermedio que reconstruir.

**Informe honesto:** cuenta cada estado; nunca anuncia éxito si algún archivo no quedó vinculado.

**Alias (D7, aceptada):** **desactivado por defecto**. Es una casilla **separada y explícita** («Recordar este nombre para las próximas descargas»); un alias aprendido hace que las descargas futuras con ese nombre se asignen **sin preguntar**, justo el fallo que la rebanada 1 evita.

## E. Conflictos sin preselección; duplicados y obsoletas fuera de alcance

- **Ninguna serie preseleccionada**, ni con un único resultado, ni con título exacto (`BATMAN (2025)` frente a `Batman - Saga de Scott Snyder (2019)`).
- **Ningún archivo marcado de antemano**, tenga o no conflicto.
- **Duplicados y las 14 referencias obsoletas:** las segundas salen **bloqueadas** (`origen_no_encontrado`) y **no hay ninguna acción** sobre ninguna de las dos; D5 sigue abierta.

## Contratos (resumen; el detalle se fija en la PR de cada paso)

| Paso | Endpoint propuesto | Efectos |
|---|---|---|
| A | `POST /api/revision/descubrir` `{clave, consulta?}` | Red (solo aquí). Sin escrituras |
| B | `POST /api/revision/serie/previsualizar` y `POST /api/revision/serie` `{token}` | La segunda escribe **solo** `series` (y la procedencia) |
| C | `POST /api/revision/vinculacion/previsualizar` `{clave, series_id, numeros?, marcados?}` | `SELECT` + `stat`. Devuelve `archivos[]`, `totales`, `avisos_de_grupo`, `token?` |
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
