# Refinamiento y partición de #183 — Elegir una publicación identificada

> **Estado:** propuesta de refinamiento para el PO. **Solo documentación.** No implementa código, no
> crea migraciones, no escribe en la base, no consulta fuentes reales, no toca la Pi ni la biblioteca y
> **no fusiona** nada. Los límites de ejecución de #183 siguen vigentes.
> **Base:** `origin/main` = **`f292c7a7854a3f07986162e065e6f76a83c45163`** (2026-11-11), leído en el
> worktree `.squad/wt-183-spec`, rama `docs/183-refinamiento`. Cada cita `fichero:línea` se refiere a
> ese SHA.
> **Insumos:** #183, #125 (orientación aprobada el 2026-10-23), #182 y
> `docs/design/discriminantes-publicacion.md`, #181 y `docs/design/censo-identidad-real.md`, ADR 0003,
> ADR 0007, `docs/design/rebanada-2-elegir-serie-y-vincular.md`, `docs/design/ui-M6-US03-asociar-fuente.md`
> y el código de `vinculacion_previa`, `vinculacion`, `asistente_vinculacion`, `asistente_carpetas`,
> `asignacion`, `ficha_numero`, `discovery` y `detalle_edicion`.
> **Método:** lectura de código y documentos; sin pruebas ejecutadas, sin red, sin navegador ni Pi. Lo no
> comprobado va marcado **NOT RUN**; ninguna fuente real se ha consultado y no se ha tocado ningún dato.
>
> **Benchmark:** `docs/design/benchmark-identidad-editorial.md` (cerrado 2026-10-01) es el insumo de las
> decisiones de identidad; #182 ya lo consumió y este refinamiento **no reabre** el benchmark ni toma una
> decisión arquitectónica nueva: reutiliza el patrón JSONB, el token firmado y la vista previa existentes.

---

## 0. Resumen para el PO

#183 pide comparar publicaciones y elegir una explícitamente, sin que el sistema decida y sin crear
ediciones, vinculaciones ni cambiar recuentos. La investigación encuentra **una sola entrada real** en la
app: el estado `numero_ambiguo` de la vista previa de **Vincular archivos** (asistente de vinculación,
`POST /revisar`). Hoy ese estado es un callejón sin salida: sabe que hay más de una publicación local con
el mismo número y no muestra ninguna, con el texto «La serie tiene más de un número así (volúmenes
distintos): no se elige uno por ti.» (`services/vinculacion_previa.py:93`).

La propuesta: en esa misma fila, **mostrar las publicaciones locales candidatas** con los discriminantes
que existen de verdad, **elegir una explícitamente**, guardar la elección en `File.metadata_`
(`publicacion_identificada`, JSONB, sin migración) y, en un paso separado y ya existente, **usar esa
publicación al confirmar la vinculación**. Nada se elige solo, nada se crea y nada se vincula como efecto
de la elección. Las candidatas de **fuente** no están disponibles hoy como lista (solo hay detalle de una
ficha) y quedan para una historia opcional.

La partición propuesta tiene **3 historias de núcleo** (candidatas locales y elección visible →
consumo en la confirmación → ambigüedad persistente y vía manual) y **2 opcionales** (candidatas de
fuente; historial/atribución). El **primer corte vertical demostrable end-to-end** es H1 + H2: dos
`Issue` sintéticos de la misma serie y número, elegir uno, vincular con él y ver el informe. H1 sola se
puede demostrar en pantalla pero **no es comercializable** porque la vinculación seguiría bloqueada.

**Hecho incómodo:** el censo de #181 no encontró ninguna publicación homónima en la base real
(`grupos_con_multiples = 0`, `otras_ediciones_posibles = 0`; `docs/design/censo-identidad-real.md:33-35`).
#183 resuelve un callejón que hoy **no se dispara con los datos del PO**, pero sí está codificado y puede
dispararse con una importación futura. El PO decide si se construye ahora (pequeño, cierra un mal estado
conocido) o se pospone hasta que el disparador ocurra; el refinamiento deja ambas salidas documentadas
(§8, P1).

---

## 1. Problema local, valor y alcance

### 1.1 Lo que pide #183

Como coleccionista, quiero comparar candidatas y elegir explícitamente una publicación identificada para
continuar sin que el sistema decida por mí. La historia exige: candidatas comparables con los
discriminantes de #182; elección explícita; no elegir en ambigüedad; no crear edición, serie, publicación
ni vinculación como efecto secundario; no migrar ni alterar recuentos; reversibilidad visible según lo que
permita el contrato; fallos visibles; y pruebas de candidata única, varias distinguibles, ambigüedad,
elección manual, fallo y ausencia de creación automática.

La orientación de #125 añade dos precisiones que este documento asume: **una candidata única tampoco se
aplica sola** si se presenta, y la **persistencia/reversibilidad** hay que concretarla sin inventar
usuarios, auditoría ni operación inversa (`#125`, comentario de refinamiento del 2026-10-23). #182 fija el
contrato de candidata, elección y salida `publicacion_identificada`, y deja a #183 la persistencia
(`docs/design/discriminantes-publicacion.md:79-110`).

### 1.2 Estado actual, verificado en código

- La vista previa de vinculación consulta los `Issue` de la serie con esa clave de número y, si hay más
  de uno, marca el archivo como `numero_ambiguo`, **no marcable** y con un texto que remite a una decisión
  humana que la pantalla no ofrece (`services/vinculacion_previa.py:76-79,516-534,562-566,579-580`).
- La confirmación vuelve a encontrar más de un `Issue` y **omite** el archivo con `numero_ambiguo`: no
  adivina (`services/vinculacion.py:332-340`; contrato en `docs/design/rebanada-2-elegir-serie-y-vincular.md:355-379`).
- La consulta de candidatas solo devuelve `(formato, nº de archivos)` por número; **no devuelve IDs,
  volumen, editorial, procedencia ni nada con lo que comparar** (`vinculacion_previa.py:516-534`).
- La elección no existe en ninguna otra ruta: no hay alta ni edición de `Issue` en la UI, la asociación de
  #129 es de serie, la asignación de Pendientes no ofrece candidatas y la ficha de número muestra «Otras
  publicaciones con este número» solo como lectura y solo cuando el número ya tiene más de un archivo
  (`web/templates/issue_detail.html:92-104`; `services/ficha_numero.py:250,360-379`).
- No hay cuentas de usuario: la autenticación es una contraseña o un usuario+contraseña **únicos de la
  instalación**; la cookie solo sella la versión de la sesión (`config.py:232-234`, `web/auth.py:104-112`).
  No existe tabla de usuarios ni historial de auditoría.

### 1.3 Valor

Cerrar un estado sin salida: hoy, cuando ocurre, el coleccionista ve «no se elige uno por ti» y no puede
hacer nada desde esa pantalla. La elección explícita permite continuar con la publicación correcta sin
que ZascArr invente una identidad ni cree una edición. Además deja una salida trazable para una futura
migración de identidad (#184, hoy pospuesta), sin acoplarse a ella.

### 1.4 En alcance

1. Mostrar candidatas locales con los discriminantes disponibles y la ausencia explícita («no consta»).
2. Elección explícita de una candidata, con revalidación al confirmar.
3. Guardar `publicacion_identificada` de forma reversible y visible, sin migración.
4. Usar la elección en la confirmación de vinculación, que sigue siendo un paso explícito separado.
5. Estados de ambigüedad, sin candidatas, candidata desaparecida/cambiada, token caducado, fallo y
   ausencia de creación automática.
6. Pruebas con Postgres real y dobles; sin red.

### 1.5 NO-goals

- **No elegir automáticamente** ni preseleccionar una candidata; tampoco «la primera» ni «la del id más
  bajo» (`docs/design/rebanada-2-elegir-serie-y-vincular.md:355-379`).
- **No crear** serie, edición, `Issue` ni publicación; **no vincular** archivos, **no migrar**, **no
  cambiar recuentos** como efecto de la elección.
- **No crear una pantalla huérfana**: la elección vive en la vista de vinculación que ya existe.
- **No asociar fuentes ni pedir candidatas de fuente** en el primer corte: hoy no hay una lista de
  publicaciones de fuente (§3.2); sería otra historia.
- **No inventar** usuarios, historial de auditoría ni operación inversa; lo que no exista se recorta y se
  dice (P4, P5).
- **No cambiar** las reglas de vinculación (bloqueos, token v2, ocupación del `Issue`, no reasignar) más
  allá de consumir una elección revalidada; el token v3 solo añade el dato elegido y lo revalida.
- **No tocar** el modelo de ediciones (`editions`/`edition_id` no existen) ni el esquema: la elección va
  en JSONB. La migración de #184 no se diseña aquí.

---

## 2. Entrada concreta en la app

### 2.1 Candidatas descartadas (y por qué)

| Posible entrada | Qué hay de verdad en el código | ¿Entrada de #183? |
|---|---|---|
| **Alta o edición de un `Issue`** | No existe ruta ni pantalla de alta/edición de `Issue`. Los `Issue` se crean implícitamente al **organizar** (`services/asignacion.py:594-600`), al **vincular** (`pg_insert` en `services/vinculacion.py:345-360`) y en el camino heredado de revisión (`services/review.py:302`). | **No**: no hay formulario donde elegir una publicación; crear uno sería una pantalla nueva sin consumidor. |
| **Asociar otra fuente (#129)** | Es a nivel de **serie**; su propio diseño excluye la ficha de publicaciones (`docs/design/ui-M6-US03-asociar-fuente.md:695`; `docs/design/refinamiento-129.md:111`). La UI de #129 está en `web/asociar_fuente.py:90-181`. | **No**: otra entidad y otra capacidad; duplicaría #129. |
| **Pendientes / organizar un archivo** | La asignación busca un `Issue` por `(serie, número)` y, si el formato no coincide, devuelve `colision_edicion`; si ya tiene archivo, `numero_ya_existe` (`services/asignacion.py:337-345,785-835`; `web/pendientes.py:617-680`). No enumera candidatas ni permite elegir. Además **mueve y vincula** en el mismo flujo. | **No** para una elección sin efectos: sería mezclar la elección con una acción que mueve el archivo. |
| **Importación** | Crea o reutiliza `Issue` a partir del nombre; no pregunta y no tiene una elección de publicación. | **No**: es automática por diseño. |
| **Ficha de número** | «Otras publicaciones con este número» es solo lectura, se pinta solo si `len(archivos) > 1` y no tiene acción (`issue_detail.html:92-104`; `ficha_numero.py:250,360-379`). Es una **superficie de consulta** útil, no una entrada. | **No** como entrada; sí como precedente de discriminantes. |
| **Vinculación de archivos** | El estado `numero_ambiguo` ya existe, ya detecta >1 `Issue` y ya se niega a elegir; es el único sitio donde varias publicaciones del mismo número se comparan en una decisión real. | **Sí**: entrada real y sin pantalla nueva. |

### 2.2 La entrada elegida

**Ruta:** `GET /ui/pendientes/carpetas/asistente/vinculacion?clave=<grupo>&series_id=<uuid>`
(`web/asistente_vinculacion.py:379-390`), que muestra la revisión de `_vinculacion_revision.html`; cada
archivo tiene su fila con estado y motivos. Cuando el estado es `numero_ambiguo`, la fila muestra hoy el
texto y **ningún control** (`web/templates/_vinculacion_revision.html:62-111`). Es la pantalla de
«Vincular archivos» del asistente de carpetas (M3), no una pantalla nueva.

**Qué se añade:** un bloque de candidatas en esa fila, con una acción explícita por candidata y el estado
de la elección vigente. El botón principal de la pantalla sigue siendo el de vincular; las acciones por
candidata son neutras y repetidas (mismo patrón que las tarjetas de #129: `ui-M6-US03-asociar-fuente.md:229-270`).

**Por qué no una pantalla aparte:** la ambigüedad ya está contextualizada (grupo, serie, archivo, número,
página); una pantalla nueva duplicaría la carga de contexto y el token. La ficha de número puede mostrar
la elección más adelante (H3), pero no es la entrada.

### 2.3 La realidad del censo

El censo de #181 no encontró homónimas: 0 colisiones, 0 «otras ediciones posibles», 443 `Issue` todos
`single_issue` (`censo-identidad-real.md:33-35`). El estado `numero_ambiguo` **no se dispara con los datos
actuales**, pero está implementado y probado con datos sintéticos
(`tests/test_vinculacion_previa_pg.py:386-394`, `tests/test_asistente_vinculacion_pg.py:325-334`,
`tests/test_vinculacion_pg.py:580-599`). El primer corte se demuestra con dos `Issue` sintéticos de la
misma serie y número, en volúmenes distintos. Si el PO no quiere invertir en un caso que hoy no ocurre,
la salida honesta es **posponer** (P1); el documento queda listo para cuando ocurra.

---

## 3. Fuente de candidatas disponible hoy y campos reales

### 3.1 Candidatas locales (`Issue`)

La fuente disponible es la tabla `issues` de la propia serie: se consulta por `(series_id, número)` sin
distinguir mayúsculas y sin filtrar por volumen, igual que la vinculación
(`vinculacion_previa.py:516-534`; `vinculacion.py:374-380`). Un `Issue` es candidato si pertenece a la
serie y su `issue_number` coincide con la clave del archivo; el `volume` y el `format` son
**discriminantes**, no identidad.

Campos de §6.1 y de §4.2 de #182, con lo que existe de verdad:

| Campo del contrato | ¿Existe hoy? | Dónde / cómo se obtiene | Qué se muestra |
|---|---|---|---|
| `candidate_id` | Sí | UUID del `Issue` (`models/__init__.py:576-580`) | No se muestra el UUID; es el valor opaco de la acción |
| `series_id` local | Sí | `Issue.series_id` | Se usa para validar; no se pinta como id |
| Título y año de la serie | Sí | `Series.title`, `Series.start_year` | Texto; pueden faltar, pero el título es obligatorio |
| Número | Sí | `Issue.issue_number` (`String(20)`, nullable) | Tal cual; «sin número» no se inventa |
| Formato | Sí | `Issue.format` (`IssueFormat`; `models/__init__.py:587-589`) | Etiqueta legible (`grapa`, `tomo en rústica`, `ómnibus`…) |
| Editorial / sello | A veces | `Series.publisher` / `Series.imprint`; el `Issue` no los tiene | «No consta» si faltan; se etiqueta que es de la serie, no del número |
| Tradición | Sí | `Series.tradition` | Etiqueta legible; es de la serie |
| Fuente / procedencia | A veces | `Issue.metadata_source`; si falta, **no se infiere** de la serie | «No consta» / etiqueta de la fuente; no se inventa |
| Id externo de la publicación | Solo CV | `Issue.comic_vine_id` (`BigInteger`, único; `models/__init__.py:600-601`); las demás fuentes no tienen id de número | Se muestra solo si existe, con su fuente; los ids de **serie** no se presentan como id de publicación |
| URL de ficha de la fuente | **No** | No hay columna en `Issue`; `detalle_edicion` la tiene, pero no se persiste | «No consta»; no se construye una URL por deducción |
| `volume` | Sí, pero **solo advertencia** | `Issue.volume` (nullable en Postgres) | «Volumen registrado: N»; nunca identidad (#182) |
| Fecha de portada, páginas, sinopsis, portada | Sí, pero **no son discriminantes acordados** | `Issue.release_date/page_count/synopsis/cover_url` | No se usan para comparar ni como identidad; no se añaden sin decisión |
| ISBN | **No** | `Issue.isbn` existe, pero nada la escribe ni la lee | «No consta»; no se usa |
| Idioma, país, edición, reimpresión, obra, cobertura | **No** | No modelados o no escritos | «No consta»; no se inventan (#182 §4.3) |

**Candidatas distinguibles:** con la clave `UNIQUE(series_id, issue_number, volume)`
(`models/__init__.py:578`), dos publicaciones de la misma serie y número solo pueden coexistir con `volume` distinto
o con `volume NULL` (los NULL no chocan). Por eso las candidatas locales suelen ser distinguibles por
**volumen y/o formato**; si dos filas tienen los mismos valores disponibles y ninguna fuente/id externo,
son **indistinguibles** y no se eligen (vía manual, §4.4).

### 3.2 Resultados de fuentes y detalle de edición

- `DiscoveryResult` es **de serie**, no de publicación: `source`, `external_id`, título, año, sinopsis,
  portada, tradición sugerida (`services/discovery.py:142-175`). Las búsquedas de #129/#465 no devuelven
  una lista de números.
- `DiscoveryService.detalle_de` devuelve **el detalle de una ficha** (colección, serie GCD o número de
  Tebeosfera si se le pasa `numero_esperado`), no una lista de candidatas
  (`discovery.py:250-340`). `DetalleEdicion` aporta editorial, sello, año, numeración, número de
  publicación, páginas, formato, país, idioma, `campos_ausentes` y URL de ficha
  (`services/detalle_edicion.py:22-49`).
- **No existe hoy** una operación que enumere las publicaciones de una fuente. Enumerar números de una
  colección de Tebeosfera o de un volumen de CV exigiría peticiones adicionales y una decisión de
  producto; no es una fuente de candidatas disponible «hoy» y queda fuera del primer corte (H4 opcional).
- **Sin red en tests:** el primer corte no consulta fuentes; las pruebas usan `Issue` sintéticos y
  `FakeSession`/Postgres real. H4 usaría dobles de cliente, nunca red.

### 3.3 La ficha de número como precedente, no como fuente

`ficha_numero._otras_ediciones` ya calcula publicaciones de la misma serie con el mismo número y distinto
volumen o formato (`ficha_numero.py:360-379`), y la plantilla las pinta en un `<details>` («Otras
publicaciones con este número») solo si el número tiene más de un archivo (`issue_detail.html:92-104`).
Sirve como precedente de los discriminantes y como superficie de consulta posterior, pero **no** como
entrada ni como proveedor de candidatas para la vista previa: su consulta no está pensada para eso y
solo se pinta con varios archivos.

---

## 4. Contrato de candidata, elección, salida y reversibilidad

### 4.1 Candidata

```text
CandidataPublicacion
  candidate_id: str          # "local:<uuid del Issue>" (opaco en la acción)
  issue_id: str              # UUID local; solo si la publicación ya existe
  series_id: str
  serie_titulo: str
  serie_anio: int | None
  numero: str
  formato: str               # valor de IssueFormat
  volumen: int | None        # dato heredado/advertencia
  editorial: str | None      # de la serie, etiquetado
  sello: str | None          # de la serie, etiquetado
  tradicion: str
  source: str | None         # metadata_source del Issue, si consta
  external_id: str | None    # solo Issue.comic_vine_id si consta
  url_ficha: str | None      # no consta hoy en Issue
  nivel_editorial: "numero"  # para no confundir con serie
  snapshot: str              # hash canónico de los campos mostrados
```

- `candidate_id` no es una identidad editorial nueva: es la clave de la candidata en el contrato y
  apunta al UUID del `Issue` existente. No se crea un identificador para desempatar (#182 §5).
- Los campos ausentes se serializan como `None` y se muestran **«No consta»**; no se rellenan por
  inferencia. El nivel editorial se marca para que editorial/sello/tradición no se lean como si fueran del
  número.
- **Elegible** = candidata local existente, de la serie, con el número de la clave; no se exige que no
  tenga archivos. Si ya tiene archivos, se muestra «ya tiene archivos» como dato, y la confirmación de
  vinculación decidirá con sus reglas (H2); #183 no la descarta por eso.
- **Indistinguibles** = mismo número y mismos valores disponibles (formato, volumen, editorial/sello,
  fuente/id externo) sin ningún dato que las separe. Se muestran, pero **sin acción de elegir**; se explica
  y se ofrece la vía manual/aplazamiento (§4.4).

### 4.2 Elección explícita

- La persona pulsa **«Elegir esta publicación»** en una candidata concreta. No hay radio preseleccionado,
  ni valor por defecto, ni elección por ausencia; el formulario envía el `candidate_id` y el **token
  firmado** de la vista previa.
- El servidor comprueba: token válido y vigente; archivo, grupo y serie del token; candidata ofrecida en
  ese token; `Issue` existente, de la serie y con el número de la clave; archivo todavía sin `issue_id`
  (una elección no compite con una vinculación ya hecha); y `snapshot` sin cambios.
- Si todo vale, escribe **solo** `File.metadata_["publicacion_identificada"]`; no toca `Issue`,
  `Series`, `File.issue_id`, `metadata_source` ni recuentos. Es la única escritura de #183 y se delimita
  así por la orientación de #125 («las escrituras estrictamente necesarias…»).
- Repetir la misma elección devuelve `ya_elegida` y **no** cambia la fecha ni escribe de nuevo. Elegir otra
  reemplaza la anterior y actualiza la fecha; no hay historial (§4.5).
- **Cambiar** o **quitar** la elección son acciones explícitas desde la misma fila; «quitar» borra la clave
  y deja la fila como estaba antes de elegir.

### 4.3 Revalidación, token y concurrencia

- El token es el de la vista previa, firmado con el `secret` de la app y propósito propio (mismo patrón
  que `tokens_revision.py:375-419`; TTL 15 min, `tokens_revision.py:31`). Incluye archivo, serie, clave de
  número, ids de las candidatas mostradas y el `snapshot` de cada una; no incluye la elección anterior.
- Al elegir se **revalida** contra la base: candidata existente y con el mismo `snapshot`; archivo sin
  `issue_id`; número del token igual al que se está mostrando; token no caducado; candidata en la lista
  firmada. Si algo cambió: `candidata_desaparecida`, `candidata_cambiada`, `archivo_ya_vinculado`,
  `vista_caducada` o `token_invalido`, con explicación y **sin escribir**. La elección anterior, si
  existía, no se borra automáticamente; se muestra como no vigente y se pide revisar.
- **Concurrencia:** `SELECT … FOR UPDATE` sobre la fila `File` antes de comprobar y escribir; el `Issue`
  solo se lee (no se escribe). Un doble POST del mismo token converge en `ya_elegida`; dos elecciones
  simultáneas se serializan en el archivo y gana la última transacción (la persona es la única usuaria).
- **Idempotencia:** mismo token + misma candidata ⇒ mismo resultado, sin duplicar; no hay estado en
  memoria ni sesión de servidor.
- **No se reutiliza** el token de vinculación para la elección ni al revés: son propósitos distintos.

### 4.4 Salida `publicacion_identificada`

Se guarda en `File.metadata_["publicacion_identificada"]` (JSONB, `File.metadata_` ya existe,
`models/__init__.py:697`), con una forma versionada:

```json
{
  "version": 1,
  "series_id": "…",
  "issue_id": "…",
  "candidate_id": "local:…",
  "serie_titulo": "…",
  "serie_anio": 1987,
  "numero": "3",
  "formato": "single_issue",
  "volumen": 2,
  "editorial": null,
  "sello": null,
  "tradicion": "american",
  "source": null,
  "external_id": null,
  "elegida_en": "2026-11-11T15:00:00+00:00",
  "operacion_id": "…",
  "origen": "vinculacion_asistente",
  "snapshot": "…"
}
```

- **`issue_id` es local y obligatorio en el primer corte** (la publicación ya existe). En una candidata de
  fuente futura, `issue_id` sería `null` y no se inventaría; hoy no aplica.
- La salida es la que consume el paso siguiente (H2), no una vinculación. El objeto se devuelve también en
  la respuesta de la elección para pintar el estado.
- No se escribe `metadata_source` del archivo ni del `Issue`; no se toca `metadata_["vinculo"]` (lo
  escribe la vinculación, no la elección). La clave nueva está en espacio de nombres propio.

### 4.5 Reversibilidad y «quién»

- **Reversible mientras no se haya consumido:** quitar la elección es explícito y deja la fila como
  antes; cambiar la elección reemplaza el objeto. No hay efecto colateral que deshacer porque la elección
  no vinculó nada.
- **No hay historial:** solo la elección vigente. Cambiar o quitar pierde la anterior. No se inventa una
  auditoría ni una operación inversa (la orientación de #125 lo prohíbe si no existe).
- **«Quién»:** ZascArr **no tiene cuentas de usuario**: la autenticación es una credencial única de la
  instalación (`config.py:232-234`) y la cookie solo lleva la versión de sesión (`web/auth.py:104-112`).
  No se puede afirmar quién hizo la elección sin inventar una identidad. Se registra **cuándo**
  (`elegida_en`), **sobre qué** (candidata/snapshot) y **desde qué operación** (`operacion_id`); la UI dice
  «Elegida el …», no «por Fulano». Es un **recorte explícito** del criterio 6 de #183, aprobado o
  rechazado por el PO (P4). Si más adelante hay usuarios reales, el campo se añadiría a este contrato sin
  migración (JSONB versionado).
- **Consumo posterior:** si H2 vincula usando la elección, deshacer la vinculación es el camino existente
  (`desvincular`, BL-R1); quitar la elección **no** desvincula ni cambia retroactivamente un vínculo ya
  hecho. El contrato lo dice en pantalla.

### 4.6 Consumo en la confirmación (H2)

La confirmación de vinculación actual recibe solo el token v2 y vuelve a decidir por clave; si encuentra
más de un `Issue`, omite (`vinculacion.py:332-340`). Para consumir la elección sin romper el contrato:

- El token de vinculación sube a **v3** y añade, por archivo, `issue_id_elegida` **opcional**. Los tokens
  v2 se rechazan igual que hoy se rechazan versiones antiguas (`tokens_revision.py:400-445`), y la vista
  previa se regenera.
- Al construir el token, la vista previa solo incluye `issue_id_elegida` si la elección guardada sigue
  vigente y la candidata está en la lista revalidada. Si no, no la incluye y el archivo sigue
  `numero_ambiguo`.
- Al confirmar, con el archivo bloqueado y la clave tomada, se lee el `Issue` elegido y se comprueba:
  existe, es de la serie, su número coincide con la clave y no está ocupado por otro archivo. Si vale, se
  vincula a **ese** `Issue` (el informe lo dice); si no, se omite con el motivo actualizado
  (`candidata_desaparecida`, `candidata_cambiada`, `colision_de_edicion`, `numero_ya_existe`,
  `cambio_desde_la_vista_previa`). No se crea un `Issue` distinto.
- **Formato:** si el `Issue` elegido tiene un `format` distinto del que deduce el nombre del archivo, se
  mantiene el bloqueo `colision_de_edicion` de la vinculación (no se cambia una regla existente por una
  elección); el archivo se omite con explicación. La elección sigue guardada para revisión. Esto evita que
  elegir un ómnibus «convierta» un archivo de grapa sin un cambio de formato explícito (P7).
- El **único** efecto de H2 es la vinculación que la persona ya confirma con el botón existente; no hay
  vinculación automática al elegir. El informe y la idempotencia (misma operación, mismo resultado) se
  mantienen.

### 4.7 Ambigüedad persistente, sin candidatas y errores

| Situación | Qué se hace | Texto propuesto |
|---|---|---|
| Más de una candidata distinguible | Se muestran todas con sus discriminantes; una acción por candidata; no hay preselección | «Hay varias publicaciones con este número. Elige la que corresponda; no se elige sola.» |
| Una sola candidata (si se presenta en el futuro) | Se muestra; **sigue exigiendo** una acción explícita | «Esta es la única publicación con ese número. Confírmala si es la correcta.» |
| Candidatas indistinguibles | No se habilita elegir; se explica y se ofrece aplazar | «No puedo distinguir estas publicaciones con los datos que tengo. No elijo por ti. Déjalo para después o revísalo a mano.» |
| Sin candidatas | No hay bloque de elección; el flujo actual (que puede crear al vincular) no se cambia | «No hay publicaciones con ese número en la serie.» |
| Candidata desaparecida o cambiada al confirmar | Se rechaza, no se escribe; la elección anterior se muestra no vigente | «La publicación cambió o ya no existe. Vuelve a abrir la vista previa y elige otra vez. No se ha cambiado nada.» |
| Archivo ya vinculado mientras se elegía | Se rechaza; no se reasigna | «Ese archivo ya se vinculó. La elección no se ha guardado; recarga la vista previa.» |
| Token caducado o manipulado | Se rechaza; no se escribe | «La vista previa caducó. Vuelve a abrirla; no se ha cambiado nada.» |
| Fallo de BD al escribir | Rollback; no se anuncia éxito; se puede reintentar | «No se pudo guardar la elección. No se ha cambiado nada; vuelve a intentarlo.» |
| Sin red / fuente | **No aplica en el primer corte**; el registro es local | — |

**Vía manual:** si la ambigüedad persiste, la salida es **aplazar** (dejar el archivo sin elegir y sin
vincular) y volver a la ficha de la serie. No se ofrece «crear una publicación» ni «editar el `Issue`»
porque no existen en la UI; ofrecerlo sería una pantalla nueva y una creación implícita. La limitación se
dice tal cual y se eleva al PO (P10). Si el archivo está en Pendientes, el enlace de vuelta a la lista es
el existente; no se promete que esa vía resuelva la ambigüedad.

---

## 5. UX

### 5.1 Dónde y flujo

- Se **extiende la fila del archivo** en la revisión de vinculación (`_vinculacion_revision.html:62-111`).
  No hay pantalla nueva ni paso adicional en el asistente.
- Bajo el texto de `numero_ambiguo`, un bloque `<fieldset>` «¿Cuál de estas publicaciones es?» con una
  tarjeta por candidata y el detalle de sus discriminantes.
- Cada tarjeta tiene un botón neutro **«Elegir esta publicación»** (se repite por candidata; no es el botón
  principal de la pantalla). Tras elegir, la tarjeta elegida se marca como «Elegida» y aparecen **«Cambiar»**
  y **«Quitar la elección»** (secundarios).
- El botón principal de la pantalla sigue siendo **«Vincular seleccionados»** (o el que corresponda al
  flujo existente); la elección no lo sustituye ni lo pulsa sola.
- H2 hace que, tras elegir, el archivo pase a ser marcable y el token incluya la publicación elegida; la
  vinculación sigue siendo un **envío aparte** y explícito. Si H1 se entrega sola, el archivo sigue no
  marcable y el texto lo dice («elegida para el paso siguiente; la vinculación sigue pendiente»); por eso
  H1 no se comercializa sola.
- HTMX: la acción devuelve el fragmento de la fila actualizado, con `no-store`; no recarga la página, no
  usa JavaScript propio (ADR 0005) y no usa `hx-confirm` (la elección es reversible; el guardado no es
  destructivo).

### 5.2 Contenido de cada tarjeta

- «Publicación #3 · grapa · volumen 2»; «Serie: Título (1987)»; «Editorial: …» o «No consta»;
  «Sello: …» o «No consta»; «Tradición: …»; «Fuente: …» o «No consta»; «Ficha en la fuente» solo si
  `url_ficha` consta (hoy no consta en `Issue`; no se inventa).
- El volumen se etiqueta **«Volumen registrado»** con una nota «dato heredado, no identifica por sí solo»
  (ADR 0003/#182); no se usa para ordenar ni para decidir.
- Si dos candidatas son indistinguibles, se muestran igualmente y el botón de elegir no aparece; el bloque
  explica por qué.
- No se muestran tokens, UUID, `candidate_id`, rutas ni nombres de columnas.

### 5.3 Textos y presupuesto

- Frase de entrada del bloque ≤20 palabras; el detalle de procedencia/«por qué no puedo distinguirlas»
  va en `<details>` (presupuesto U21).
- Una sola acción principal por pantalla (la de vincular). Las acciones repetidas por candidata son
  neutras, como en #129 (`ui-M6-US03-asociar-fuente.md:229-270`).
- Estados y textos de la tabla §4.7; nada de «token», «snapshot», «Issue» ni «metadata» en pantalla.
  Las etiquetas de formato salen de `FORMATOS_LEGIBLES` (`ficha_numero.py:50-56`).
- El estado de la elección se anuncia y se puede leer: «Elegida: Publicación #3, volumen 2, grapa» +
  fecha. Si no hay elección: «Sin elegir; no se elige sola».

### 5.4 Accesibilidad

- Cada bloque es un `fieldset` con `legend`; cada tarjeta tiene un nombre accesible completo (número,
  formato, volumen) y el botón incluye ese nombre en su texto accesible; no hay información solo por
  color; el foco va al estado de la elección tras la respuesta; `aria-live="polite"` para el resultado.
- En móvil, tarjetas en una columna, sin tabla ancha; texto ≥14 px; no se usan iconos como única
  información. El bloque no añade un segundo `h2` de página: usa `h3` o `legend` dentro de la fila.
- Si el archivo está bloqueado por otro motivo, el bloque de candidatas no se pinta (no confundir).

### 5.5 Qué NO crea esta UX

- No crea serie, edición, `Issue`, publicación ni vínculo.
- No migra, no altera recuentos, no mueve ni renombra el archivo, no toca la biblioteca.
- No asocia fuentes, no consulta la red, no pide portadas.
- No elige por la persona, no preselecciona y no ordena por «mejor».

---

## 6. Seguridad, legal y privacidad

- **Entrada explícita:** solo `POST` bajo `/ui/...` con `Form(...)` explícito y el token firmado; no hay
  mass assignment; el cliente no manda los discriminantes ni el `issue_id` como verdad: manda una clave de
  candidata y el token se revalida contra la base.
- **Integridad:** token HMAC con propósito propio y TTL 15 min; `snapshot` canónico por candidata; la
  escritura se hace con la fila del archivo bloqueada; no se acepta una candidata que no estuviera en el
  token; no se acepta cambiar el número sin regenerar la vista previa.
- **Sin efectos ocultos:** solo se escribe `File.metadata_["publicacion_identificada"]`; no se tocan
  `Issue`, `Series`, `File.issue_id`, `metadata_source`, `locked_fields` ni recuentos. Prueba explícita de
  que no se crea ninguna fila y de que los contadores no cambian.
- **XSS:** todos los valores de candidata son datos de la base y se escapan con Jinja; nunca se usan en
  `class`, `id`, `style`, `hx-*` ni con `|safe`/`Markup`; no se pintan imágenes de fuente; no se abren
  URLs de candidata en el primer corte (si H4 las añade, solo `http(s)` validados y sin hotlinking).
- **Privacidad:** no se guardan usuarios, IP, sesión ni datos personales; solo catálogo y fecha. Logs sin
  valores de candidata ni tokens (`structlog` con evento y código de error, no datos).
- **Sin red y sin scraping:** el primer corte no consulta fuentes; H4 usaría los clientes existentes con
  cortesía y sin endpoints nuevos. No se añade telemetría.
- **Legal:** los datos son del catálogo local; no se redistribuye nada nuevo. La elección no embebe
  metadatos de fuentes ni cambia el archivo. GCD/CC BY-SA, Tebeosfera etc. no aplican al primer corte;
  si H4 usa una fuente, se respetan sus términos y la atribución/enlace que ya usa Descubrir.
- **No-store** en el fragmento con estado; sin caché de la elección en el navegador.

---

## 7. Partición en historias

### 7.1 Tabla

| Historia | Contenido | Escribe | No escribe | Depende de | Est. |
|---|---|---|---|---|---|
| **H1 · Candidatas locales y elección visible** | Extiende `VistaPreviaDeVinculacion` para devolver candidatas locales de `numero_ambiguo` (id, discriminantes, snapshot); bloque UX en la fila; `POST` de elección con token; persiste `publicacion_identificada` en `File.metadata_`; cambiar/quitar; revalidación; tests. | JSONB del `File` al elegir | `Issue`, `Series`, `File.issue_id`, vínculo, recuentos, archivos | #182; #125; código actual; #184 no | **M (5)** |
| **H2 · Consumir la elección al vincular** | Token v3 con `issue_id_elegida` opcional; la vista previa lo emite solo si la elección vigente se revalidó; `VinculacionDeArchivos._decidir` usa el elegido y mantiene bloqueos; informe; tests end-to-end. | `File.issue_id` y `metadata.vinculo` **solo al confirmar** | Serie/Issue nuevos por la elección; archivos; migración | H1; #120; reglas de vinculación | **M (5)** |
| **H3 · Ambigüedad persistente y vía manual** | Indistinguibles, sin candidatas, candidata cambiada/desaparecida, token caducado, archivo ya vinculado; textos; accesibilidad; consulta de la elección en la ficha de número (opcional, si el PO la quiere); pruebas de web y composición. | Nada (solo lectura) | Nada | H1 (y H2 para el estado final) | **S (2)** |
| **H4 · Candidatas de fuente (opcional)** | Proveedor de candidatas de publicación desde `DetalleEdicion`/clientes; estados #133; revalidación con red o dobles; mezcla con locales; sin scraping nuevo. | Nada (solo lectura) | Nada | H1/H2; PO P8; capacidades de fuente NOT RUN | **M (5)** |
| **H5 · Historial/atribución (opcional)** | Si el PO quiere «quién/cuándo» con usuarios reales o historial; alternativas sin migración (JSONB de últimas N) o con migración; decisión aparte. | Según contrato | — | P4/P5; auth | **S (2)** (posible M) |

**Núcleo H1+H2+H3 = 12 puntos**, coherente con los 13/XL de #183; las estimaciones son provisionales y
la confianza declarada de #183 era **baja**, así que se recalibran al implementar, no son compromiso de sprint.
**Primer corte vertical demostrable end-to-end = H1 + H2**: dos `Issue` sintéticos de la misma serie y
número (volúmenes 1 y 2), abrir el asistente, ver las dos candidatas, elegir una, verla persistida,
vincular con el botón existente y comprobar el informe; sin elección, el archivo sigue omitido. H1 sola se
puede demostrar en pantalla (candidatas, elección, JSONB, quitar) pero deja la vinculación bloqueada; **no
se comercializa sola**. H3 puede ir en el mismo tren que H2; H4/H5 no se comprometen.

### 7.2 AC EARS por historia

**H1 — candidatas y elección**

- **CUANDO** la vista previa detecta más de un `Issue` con la clave del número, **ENTONCES** la fila
  devuelve las candidatas con número, formato, volumen (como advertencia), editorial/sello, tradición,
  procedencia e id externo **solo si constan**, y «no consta» en el resto; no se inventa ningún campo.
- **CUANDO** la persona pulsa «Elegir esta publicación», **ENTONCES** el servidor revalida token,
  archivo, serie, número, candidata y snapshot, y escribe solo `File.metadata_["publicacion_identificada"]`;
  si algo no cuadra, no escribe y explica.
- **DADO** que no hay elección, **ENTONCES** no hay candidata preseleccionada y no se elige sola.
- **SI** se presenta una única candidata (caso futuro), **ENTONCES** también exige una acción explícita y
  no se aplica sola.
- **CUANDO** se repite la misma elección, **ENTONCES** el resultado es idempotente y no duplica ni pierde
  datos; **CUANDO** se quita, **ENTONCES** la clave desaparece y la fila vuelve al estado anterior.
- **DADO** un archivo ya vinculado, **ENTONCES** no se escribe una elección y se explica.
- **DADO** el flujo completo, **ENTONCES** no se crea ninguna fila en `issues`/`series` y los recuentos no
  cambian.
- Pruebas: unitarias del contrato de candidata; Postgres real con dos `Issue` sintéticos, elegir, releer,
  quitar, repetir, candidata cambiada/desaparecida, token caducado/manipulado, archivo ya vinculado,
  contar filas y recuentos; web del bloque (textos, `fieldset`, botones, no preselección, `no-store`).

**H2 — consumir al vincular**

- **CUANDO** la elección vigente pasa a la vista previa, **ENTONCES** el token v3 incluye
  `issue_id_elegida` solo si la candidata se revalidó; si no, el archivo sigue `numero_ambiguo`.
- **CUANDO** se confirma la vinculación, **ENTONCES** el archivo se vincula a **ese** `Issue` si sigue
  existiendo, es de la serie, el número coincide y está libre; si no, se omite con el motivo actualizado.
- **DADO** un `format` del `Issue` elegido distinto del del nombre, **ENTONCES** se mantiene
  `colision_de_edicion` (no se cambia la regla por la elección).
- **DADO** el token v2, **ENTONCES** se rechaza como hoy y se pide una vista previa nueva.
- **DADO** que la persona no elige, **ENTONCES** el comportamiento actual no cambia: `numero_ambiguo`, sin
  adivinar.
- Pruebas: PG real y extremo a extremo; repetir token; sin selección; selección obsoleta; formato
  distinto; informe y recuentos.

**H3 — ambigüedad persistente y vía manual**

- **DADO** candidatas indistinguibles, **ENTONCES** no hay acción de elegir, se explica y se ofrece
  aplazar; no se crea nada.
- **DADO** sin candidatas, **ENTONCES** no se pinta el bloque y el flujo actual no cambia.
- **DADO** un fallo de BD/token/vista, **ENTONCES** el aviso está en llano, no se anuncia éxito y no se
  escribe; la pantalla sigue usable.
- **DADO** un lector de pantalla o teclado, **ENTONCES** el bloque es navegable, los botones tienen nombre
  completo y el estado se anuncia.
- Pruebas de composición web, textos exactos, accesibilidad y estados; no se necesita red.

### 7.3 Dependencias y orden

1. **H1** primero; no depende de #184 ni de fuentes. Reutiliza el contrato de #182 y la vista previa de
   #119/#120; no duplica #129.
2. **H2** después de H1; toca `tokens_revision.py` (v3) y `vinculacion.py`; debe coordinarse con cualquier
   cambio en la vinculación. Sin H2, H1 no se despliega.
3. **H3** con H2 o justo después; no bloquea.
4. **H4** solo si el PO lo pide y las capacidades de fuente se acreditan (NOT RUN); no en el primer corte.
5. **H5** solo si el PO decide que merece la pena; probablemente no con la autenticación actual.
6. **#184** (migración) no es dependencia: no se diseña ni se ejecuta. La elección en JSONB puede servir
   de evidencia futura, pero no se promete como fuente autorizada de migración.

### 7.4 Mapa con los criterios de #183

| Criterio | Dónde se acredita |
|---|---|
| 1. Candidatas comparables | H1 §4.1/§5.2; pruebas de campos y «no consta» |
| 2. Elección explícita | H1 §4.2; sin preselección, POST explícito |
| 3. Ambigüedad sin decisión automática | H3; indistinguibles sin acción |
| 4. Sin creación implícita | H1/H2; pruebas de filas y recuentos |
| 5. Sin migración ni recuentos | H1; JSONB, cero migraciones |
| 6. Reversibilidad visible | H1/H3; quitar/cambiar, fecha; **sin «quién»** (P4) |
| 7. Fallos visibles | H1/H2/H3 §4.7; sin éxito ficticio |
| 8. Evidencia verificable | pruebas de H1/H2/H3; NOT RUN de navegador/Pi |

---

## 8. Decisiones del PO, riesgos y límites

### 8.1 Hechos vs propuestas

**Hechos verificados en `f292c7a`:** la única superficie que detecta varias publicaciones del mismo
número es la vista previa de vinculación (`numero_ambiguo`); no muestra candidatas ni permite elegir; la
confirmación omite el archivo; no hay alta/edición de `Issue` en la UI; #129 es de serie y no cubre
publicaciones; `detalle_de` devuelve una ficha, no una lista; los campos de §6.1 disponibles se reducen a
los locales; no hay cuentas de usuario; el censo no encontró homónimas.

**Propuestas (no hechos):** persistir en `File.metadata_`; token v3 con `issue_id_elegida`; H1/H2/H3;
mantener `colision_de_edicion` si el formato difiere; no historial ni «quién».

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **P1** | ¿Se construye ahora o se pospone? | (a) H1+H2+H3 ahora; (b) posponer hasta el disparador del censo | **(a) si el PO quiere cerrar el callejón conocido**; es pequeño y reutiliza la entrada. Si prioriza evidencia, **(b)** y se deja este documento listo. No se finge necesidad: hoy no ocurre en la base real. |
| **P2** | Dónde persistir | (a) `File.metadata_` JSONB; (b) tabla nueva (migración); (c) solo memoria/token | **(a)**: sin migración, reutiliza el patrón JSONB, reversible por archivo; (b) fuera de alcance; (c) no cumple consulta/reversibilidad |
| **P3** | ¿H1 sola o con H2? | (a) entregar H1 y dejar el bloqueo; (b) H1+H2 para que sirva | **(b)**: H1 sola deja al usuario peor («elegí y sigo bloqueado»); el corte vertical demostrable es H1+H2 |
| **P4** | «Quién» de la elección | (a) recortar a fecha + candidata, sin usuario; (b) añadir identidad de usuario | **(a)**: no hay cuentas; (b) sería inventar o cambiar auth, otra historia |
| **P5** | Historial y deshacer | (a) solo elección vigente, quitar/cambiar; (b) historial de N en JSONB; (c) tabla de auditoría | **(a)** en el núcleo; (b)/(c) solo si el PO los pide (H5). No se promete lo que no existe |
| **P6** | Ámbito | (a) por archivo; (b) por número/grupo | **(a)**: la ambigüedad es archivo→publicación; (b) complica y puede seleccionar por otros |
| **P7** | Formato distinto del elegido | (a) mantener `colision_de_edicion` al vincular; (b) permitirlo y cambiar el formato | **(a)**: no se cambian reglas de vinculación por una elección; (b) merece su propia decisión |
| **P8** | Candidatas de fuente | (a) fuera del primer corte; (b) incluirlas ya | **(a)**: hoy no hay lista de publicaciones de fuente; (b) exige contrato y red nuevos (H4) |
| **P9** | Candidata única | (a) no presentarla (flujo actual); (b) presentarla y exigir confirmación | **(a)** en la entrada de ambigüedad; el contrato deja (b) para el futuro. Si se presenta, nunca se autoaplica |
| **P10** | Vía manual | (a) aplazar y volver; (b) crear/editar publicación desde aquí | **(a)**: (b) no existe y sería creación implícita; si el PO la quiere, historia aparte |
| **P11** | Ficha de número | (a) solo el asistente; (b) mostrar la elección también en la ficha | **(a)** en el núcleo; (b) H3 opcional, solo lectura |

### 8.2 Riesgos

| ID | Riesgo | Prob./impacto | Mitigación |
|---|---|---|---|
| R1 | El caso no ocurre hoy y la feature queda sin uso | Alta/media | H1–H3 pequeñas, pruebas sintéticas, PO decide P1; no se construyen H4/H5 |
| R2 | H1 queda a medias y el usuario sigue bloqueado | Media/alta | Entregar H1+H2 juntas; H1 no se despliega sola |
| R3 | Elección equivocada y vínculo a la publicación incorrecta | Baja/alta | Discriminantes visibles, sin auto, revalidación, informe; desvincular existente; no se crea nada |
| R4 | Candidata cambia/desaparece entre ver y confirmar | Media/media | Token + snapshot + revalidación + `FOR UPDATE`; omitir con motivo |
| R5 | Formato distinto tratado como identidad | Media/alta | P7: se mantiene `colision_de_edicion`; no se cambia la regla |
| R6 | «Quién»/historial prometidos y no existen | Media/media | Recorte explícito P4/P5; UI dice fecha, no usuario |
| R7 | Crecimiento de JSONB o claves ajenas | Baja/baja | Objeto versionado, campos fijos, sin datos de fuente; tamaño acotado |
| R8 | Token v3 rompe tokens/clientes existentes | Media/media | Versionado como v2; rechazo explícito y vista nueva; pruebas de tokens |
| R9 | Duplicar o contradecir #129/#120 | Media/media | Entrada distinta (publicación vs serie); reutiliza patrones, no endpoints |
| R10 | Sin datos reales, la UX no se valida | Alta/media | Pruebas sintéticas y demo; navegador/Pi NOT RUN; medir cuando ocurra |
| R11 | Escritura JSONB sin migración choca con rescan/otros | Baja/media | Clave namespaced, merge JSONB, pruebas de rescan/lectura; no toca `vinculo` |
| R12 | La elección se lee como identidad editorial definitiva | Media/media | Se llama «elección», no «identidad»; se puede quitar; no crea edición |

### 8.3 PASS / FAIL / NOT RUN de esta investigación

- **PASS (código y documentos leídos):** entrada real localizada; estado `numero_ambiguo` y su texto;
  confirmación que omite; ausencia de candidatas en el contrato; ausencia de alta/edición de `Issue`;
  #129 fuera de publicación; `DiscoveryResult` de serie y `detalle_de` de una ficha; campos locales
  disponibles y ausentes; ausencia de cuentas; censo sin homónimas; tests existentes de ambigüedad.
- **FAIL:** ninguno de la lectura. No hay evidencia de que el caso ocurra en la base real; no es un fallo,
  es el límite del censo.
- **NOT RUN:** no se ejecutó ningún test; no se abrió navegador, lector, Pi ni móvil; no se consultaron
  fuentes; no se midió accesibilidad; no se probó la migración (no hay); no se validó con coleccionistas;
  no se comprobó que la base real tenga o no ambigüedades ocultas en los 897 archivos sin `Issue`.
- **Límites:** #183 no autoriza código, migraciones, fuentes reales ni despliegue; este documento no mueve
  el tablero ni crea tarjetas hijas.

### 8.4 Caducidad

Caduca con la ficha de identidad editorial (~2027-01-06) o antes si cambia el contrato de #182, la
vinculación, el token, el modelo de `Issue` o la autenticación. La PR es **solo documentación** y no se
fusiona en este encargo.

---

## 9. Trazabilidad

- Decisión de discriminantes y contrato: `docs/design/discriminantes-publicacion.md` (§4-§6),
  merge `4b09a6a`.
- Censo: `docs/design/censo-identidad-real.md`, PR #401, merge `35283b5`.
- ADR: `docs/adr/0003-identidad-editorial.md` (reglas 1–7, decisiones diferidas).
- Contrato de vinculación: `docs/design/rebanada-2-elegir-serie-y-vincular.md` (§2c/2d).
- Código: `services/vinculacion_previa.py`, `services/vinculacion.py`, `services/tokens_revision.py`,
  `web/asistente_vinculacion.py`, `web/asistente_carpetas.py`,
  `services/asignacion.py`, `services/ficha_numero.py`, `services/discovery.py`, `services/detalle_edicion.py`.
- Issue #183 y comentario de arranque del 2026-11-11; PR de este refinamiento (solo documentación, sin
  fusionar).
