# Refinamiento y partición de #482 BL-CNV5 — completar el ComicInfo con varias fuentes

> **Estado:** propuesta de refinamiento para el PO. **Solo documentación.** No implementa código, no
> crea migraciones, no consulta fuentes reales, no toca la Pi ni la biblioteca y **no fusiona** nada.
> **Base:** `origin/main` = **`fceaf871c9f1d1a65481c5ca9cb67b8b48707cbf`** (2026-11-10), con #109, #449,
> #480, #481 y #488 ya fusionadas. Leído en el worktree aislado `.squad/wt-cnv5-spec`, rama
> `docs/bl-cnv5-refinamiento`. Cada cita `fichero:línea` se refiere a ese SHA.
> **Insumos:** issue #482 y su comentario de arranque (2026-11-10); `docs/design/refinamiento-BL-CNV.md`
> §7 (resumen previo); implementación de #109 (`services/procedencia.py`), #449
> (`services/cobertura.py`), #480 (`services/comicinfo_ficha.py`, rutas y plantillas), #481
> (`core/comicinfo_write.py`, `services/tagger.py`), #488 (`services/compartidos.py`); clientes
> `comic_vine`, `anilist`, `tebeosfera`, `gcd`; `services/discovery.py`; ADR 0002 y ADR 0013; LEGAL.md.
> **Método:** lectura de código y documentos; sin pruebas ejecutadas, sin red, sin Pi. Lo no comprobado
> va marcado **NOT RUN**; ninguna fuente real se ha consultado.

> **Enmienda del PO (2026-11-10): CNV5-4 CANCELADA.** El alcance se queda en **solo lectura/local**:
> no se escribe la sinopsis creativa de fuentes en el `ComicInfo.xml` ni en
> `metadata.comicinfo_fuente`. El plan de B6 solo propone `Summary` cuando la ficha es
> `manual`/`comicinfo_xml` o hay marcador `comicinfo_propio`; con Comic Vine, AniList, Tebeosfera, GCD
> o procedencia `None`, `Summary` queda `SIN_DATO` y se conserva el XML existente. La procedencia que
> decide es la del **número** (`Issue.metadata_source`), no la del archivo (`File.metadata_source`); el
> marcador propio (`comicinfo_propio`) sigue autorizando. Los campos factuales locales (año,
> editorial, créditos, género, páginas) siguen su plan normal. La tabla de §8.1 y los AC de CNV5-4 se
> conservan como histórico de la propuesta, no como alcance vigente.

---

## 0. Resumen para el PO

#482 pide completar el `ComicInfo.xml` con **propuestas campo a campo de varias fuentes**, con la
procedencia visible y elección explícita. La base ya existe: #480 firma y aplica un plan de ComicInfo,
#481 añade autores, género y páginas, #109 muestra procedencia y respeta `locked_fields`, #488 avisa si
el archivo se comparte y #449 mide la cobertura local. Falta la **capa de propuestas**: consultar las
fuentes **ya asociadas** y convertir sus datos en opciones por campo, sin escribir nada hasta la
confirmación.

La propuesta: **3 historias de núcleo** (contrato/capacidades → propuestas de fuentes → selección en la
ficha → aplicar con el plan firmado) y **2 historias opcionales** (ampliar campos/fuentes y persistir en
el catálogo). No se crea un segundo escritor de ComicInfo: se extiende el de #480. Nada se aplica
automáticamente ni se combinan fuentes a ciegas; el valor actual se conserva por defecto y `locked_fields`
manda. La primera entrega **no actualiza la BD**, solo el XML y una procedencia durable en `metadata_`;
persistir en el catálogo es una decisión aparte (P4). El refinamiento deja abiertas 11 decisiones; las
más caras son **qué se considera fuente válida sin identidad asociada**, **si se persiste en BD** y **el
encaje legal de embeber sinopsis de fuentes en archivos que pueden compartirse**.

---

## 1. Problema local, alcance y no-goals

### 1.1 Problema

Hoy el ComicInfo de un CBZ se rellena **solo con lo que ya está en la base** (#480/#481): sinopsis del
número, portada, total, autores de `issue_creators`, géneros de `series.genres` y páginas de
`issue.page_count` (`services/tagger.py:278-331`, `core/comicinfo_write.py:36-46`). Las fuentes
externas enriquecen la **serie** por el enricher o, a mano, con #128, pero sus datos **no llegan a la
vista previa de ComicInfo campo a campo**. El coleccionista no puede ver «Comic Vine dice este
guionista y Tebeosfera esta fecha» y elegir qué guardar para que Kavita lo lea.

#449 ya mide cuánta información local hay y de dónde viene (`services/cobertura.py`, bloque «Qué
información tengo» en Estado), pero **no hay ninguna cifra real de cobertura de las fuentes** ni de
cuántos campos vacíos se podrían completar: la biblioteca sintética de #449 no es una medición de
producción (NOT RUN).

### 1.2 User story EARS principal

> **CUANDO** abro la información de un tebeo que ya está asociado a una o varias fuentes, **SI**
> enciendo esas fuentes en Ajustes, **ENTONCES** puedo pedir que ZascArr me enseñe, campo a campo, qué
> dice cada fuente y qué tengo yo; **MIENTRAS** no elija, no se escribe nada; **SI** dos fuentes
> discrepan, veo las dos propuestas con su origen y decido yo; **DONDE** un campo está protegido, se
> muestra como protegido y no se toca; **CUANDO** guardo, el tebeo queda con lo que elegí y con la
> procedencia de cada dato, sin que se aplique nada por mi cuenta.

**Valor:** menos tecleo y un ComicInfo más completo, sin aceptar a ciegas datos de una fuente ni perder
lo que ya tenía. Se apoya en lo que #480/#481 hicieron bien: plan único, token, vista previa y escritura
verificada.

### 1.3 En alcance

1. Consultar **una o varias fuentes ya asociadas** a la serie (no buscarlas de nuevo) y construir
   propuestas por campo para el ComicInfo de un CBZ.
2. Mostrar por campo: valor actual, propuesta(s), **fuente**, nivel (número o serie) y enlace a la
   ficha; elegir explícitamente y guardar con el plan de #480.
3. Respetar fuentes apagadas, tradición, cola de cortesía, topes de peticiones y `locked_fields`.
4. Dejar procedencia durable por campo en `File.metadata_` (sin usuario, sesión ni IP) y mostrarla en
   la vista previa.
5. Fallos parciales: una fuente caída no impide ver/guardar las demás ni el plan local.
6. Pruebas sin red (dobles de cliente) y con Postgres/fichero simulados; textos en español llano.

### 1.4 NO-goals explícitos

- **No aplicar automáticamente** ni «rellenar huecos» sin elección; nada de agregación estilo Komf
  (`aggregate`), que la ficha BL-CNV §4.2/§6-I11 descarta.
- **No combinar fuentes a ciegas**: no hay prioridad que gane sola; si difieren, decide la persona.
- **No buscar/asociar fuentes nuevas aquí**: si la serie no tiene identidad, #482 remite a #129
  (`/ui/series/{id}/asociar`); no hace búsqueda por título como atajo.
- **No escribir sin confirmación** ni tocar el archivo hasta el «Guardar» de #480; la propuesta es
  solo lectura.
- **No inventar datos**: ausencia = «no consta»; `LanguageISO` nunca se infiere (B6).
- **No ampliar clientes ni hacer scraping nuevo en el núcleo**: los campos que hoy no devuelven los
  clientes quedan para una historia aparte (S5), no se simulan.
- **No migraciones** en el núcleo; la sesión de propuestas es efímera en memoria y la procedencia va
  en JSONB. Una tabla de propuestas/procedencia sería decisión separada (P6).
- **No cambiar** el contrato de #480/#481, `locked_fields`, el plan de B6 ni el guardián #488; se
  extienden sin duplicarlos.
- **No persistir en BD** los valores elegidos en la primera entrega (decisión P4); el catálogo no
  cambia y #449 no mejora con esto. Se dice al PO, no se esconde.

---

## 2. Decisiones de diseño propuestas (D-CNV5)

| # | Decisión | Contrato |
|---|---|---|
| **D1** | Entidad y campos | Se proponen **solo campos de valor no identitarios**: `Year`, `Publisher`, `Summary`, los ocho autores, `Genre` y `PageCount`. **Nunca** `Series`, `Number`, `Volume` (identidad local; no se dejan reescribir por una fuente) ni `LanguageISO` (B6). |
| **D2** | Fuente por tradición | Solo fuentes **ya asociadas** y **encendidas**, y solo si la tradición las admite (ADR 0002): CV = american/british; AniList = manga/manhwa/manhua; Tebeosfera = tebeo/franco_belgian; GCD = fumetti/BD antigua (y como secundaria opcional de american/british si el PO lo ratifica). Varias asociadas ⇒ varias propuestas, nunca una elegida sola. |
| **D3** | Propuesta, no aplicación | Por campo: `anadir` (vacío), `conservar` (igual), `proponer_sustitucion` (distinto) o `bloqueado`; se muestran todas las opciones con su fuente. Sin elección, no hay cambio; el valor actual es el estado por defecto. |
| **D4** | Precedencia y autorización | Se reutiliza el plan de B6: lo que ZascArr escribió (`comicinfo_propio`) se puede actualizar; lo de procedencia desconocida se **conserva salvo elección explícita del campo**; `locked_fields` siempre gana. La elección de una propuesta concreta **es** la autorización explícita que B6 exige para sustituir; queda firmada en la selección. |
| **D5** | Un solo plan y un solo escritor | #482 no crea otro plan ni otro escritor: genera una lista de `CampoPlan` compatible con B6 y la aplica con `TaggerService.aplicar_plan`/`ComicInfoFichaService` tras verificar token, sesión, stat y hash. |
| **D6** | Procedencia durable | `metadata_["comicinfo_fuente"]` = `{tag: {fuente, id_externo, url_ficha, nivel, fecha}}` para los tags escritos desde una fuente; sin usuario/sesión/IP. `comicinfo_propio` sigue siendo la autoría de ZascArr. No hay procedencia por campo en BD. |
| **D7** | Sin identidad no hay propuesta | Requiere `series` con al menos una identidad externa asociada; para campos del número con CV, `issue.comic_vine_id`; para Tebeosfera, colección/slug y número resoluble. Si falta: aviso + enlace a #129. Sin búsqueda automática. |
| **D8** | Sesión de propuesta efímera | Las propuestas viven en memoria del proceso (single worker) con `operacion_id`, TTL 15 min, tope de sesiones y limpieza al usar/expirar; no en token (no cabe: #480 limita a 8192 bytes, `comicinfo_ficha.py:48`) ni en BD. Si el proceso reinicia, se vuelve a buscar. |
| **D9** | Presupuesto y cortesía | Una sola ronda por acción; ≤3 peticiones por fuente y ≤5 en total; `espera_max_s` interactivo (p. ej. 3 s); estados de #133; cola compartida de `utils/cortesia.py`; sin reintentos ni segundo plano; fuente apagada = cero tráfico. |
| **D10** | Fallos parciales | Estado por fuente; una fuente caída no borra las propuestas de las demás ni el plan local. Si no hay propuestas, se puede guardar el plan local de #480. |
| **D11** | Datos de fuente no confiables | HTML → texto plano (`utils/texto_html.py:51`), topes de longitud, sin `safe`/`Markup`, sin ids internos en pantalla, enlaces validados; valores nunca van al token ni a los logs. |
| **D12** | Primera entrega solo XML | Los valores elegidos se escriben en el `ComicInfo.xml` y en `metadata.comicinfo_fuente`; **no** se actualizan columnas de la BD. Persistir en catálogo (y #449) es S6, decisión P4. |

---

## 3. Contrato por campo

### 3.1 Matriz de campos y fuentes (capacidades **hoy**, sin ampliar clientes)

Leyenda: **S** = dato de serie (nivel serie), **N** = dato del número, **—** = no lo devuelve el
cliente actual, **?** = existe en la fuente pero no se ha verificado/leído (NOT RUN).

| Campo ComicInfo | CV (american/british) | AniList (manga) | Tebeosfera (tebeo/BD) | GCD (fumetti/BD) | ¿Se propone en núcleo? |
|---|---|---|---|---|---|
| `Series` | nombre S | título S | título S | nombre S | **No** (identidad local) |
| `Number` | `issue_number` N (contraste) | — | número N (contraste) | — | **No** (identidad local) |
| `Volume` | — | — | — | — | **No** (no hay fuente) |
| `Year` | `cover_date` N / `start_year` S | `startDate.year` S | fecha N / año colección S | `year_began` S | **Sí**, con nivel visible |
| `Publisher` | `volume.publisher` S | — | editorial S/N | `publisher` S (1 petición extra) | **Sí** |
| `Summary` | descripción N / del volumen S | descripción S | solo descripción de **saga** en búsqueda, no del detalle | — | **Sí**, con nivel visible |
| `Writer`…`Translator` | `person_credits` N (detalle de número) | — | — | — | **Solo CV**; el resto no |
| `Genre` | no se pide `genres` | no se piden `genres`/`tags` | — | — | **No en núcleo** (S5) |
| `PageCount` | no se pide `page_count` (?) | — | `paginas` N (semántica a verificar) | — | **Solo Tebeosfera número**, si #477/verificación lo acredita; si no, S5 |
| `LanguageISO` | — | — | — | — | **Nunca** (B6) |

Evidencia de las capacidades actuales: CV `search_series`/`get_volume`/`get_issue_detail`
(`services/comic_vine.py:152-232`, `CVResult:43`, `CVVolume:55`, `CVIssueResult:87`, `CVCredit:74`);
AniList (`services/anilist.py:60-69,105-119`, con `title/description/cover/startDate` y **sin**
géneros ni tags); Tebeosfera (`services/tebeosfera.py:117-135,236-290`; detalle de colección y número);
GCD (`services/gcd.py:112-175,224-262`, con editorial solo por petición aparte); y el detalle
normalizado `DetalleEdicion` (`services/detalle_edicion.py:20-45`).

**Lo que no se promete:** `Genre` (ningún cliente lo pide hoy), `PageCount` de CV (no se pide), datos de
número en AniList/GCD (sus modelos no los tienen en este código) y ninguna sinopsis de Tebeosfera en
detalle. Eso es trabajo de S5, no un dato que se rellene por inferencia.

### 3.2 Reglas por campo

- **Vacío actual + propuesta**: `anadir`; si se selecciona, se escribe.
- **Actual igual a la propuesta**: `conservar`/`ya_coincide`; no hay nada que elegir ni escribir.
- **Actual distinto**:
  - si el tag está en `locked_fields` → `bloqueado` (no se propone sustituir, se muestra el motivo:
    «Protegido: no se toca»);
  - si el actual es authored por ZascArr (`comicinfo_propio[tag] == actual`) → `proponer_sustitucion`;
  - si el actual es de procedencia desconocida → se muestra la propuesta, pero por defecto
    `conserva`; **solo se cambia si la persona marca ese campo** (D4).
- **Varias fuentes para el mismo campo**: si coinciden, una sola opción con las fuentes listadas; si
  difieren, una opción por valor y fuente, más «conservar lo actual». Nunca hay prioridad automática.
- **Nivel**: un dato de serie usado en un campo del número se etiqueta «de la serie, no del número»
  (p. ej. año de inicio) y solo se ofrece para `Year`/`Publisher`; no se ofrece una sinopsis de serie
  como sinopsis del número (P10).
- **Normalización y topes:** texto plano, `strip`, espacios colapsados; `Summary` ≤4000 caracteres;
  `Publisher` ≤255; lista de autores ≤500 por tag, sin duplicados por `casefold`; `Year` entero
  1000–2999; `PageCount` entero 1–10000 (misma regla que #481, `tagger.py:305-310`); `Genre` (cuando
  exista) lista sin duplicados y ≤500. Un valor que no cumple se descarta con aviso, no se recorta en
  silencio.
- **Lo que nunca se propone:** `Series`, `Number`, `Volume`, `LanguageISO`, campos fuera de
  `CAMPOS_GESTIONADOS` (`core/comicinfo_write.py:36-46`) y valores de portada (ComicInfo no tiene ese
  campo).

### 3.3 Cómo se construye el plan final

1. Se parte del plan local de #480/#481 (`TaggerService.planificar`, `tagger.py:351-370`) y del plan de
   B6 (`core/comicinfo_write.py:78-135`).
2. Por cada campo elegido se sustituye el «deseado» por el valor elegido y se marca **autorizado**;
   se recalcula el `CampoPlan` con la precedencia de B6 + la autorización explícita de D4.
3. `locked_fields` se aplica al final (`tagger.py:317`): un tag bloqueado nunca pasa a `cambia`.
4. El plan resultante se aplica con el token de #480 y `TaggerService.aplicar_plan` (`tagger.py:645`),
   con el guardián #488 y la misma escritura atómica de B6.
5. Solo se anotan en `metadata.comicinfo_fuente` los tags que cambian **por una fuente**; los que
   cambian por el plan local no cambian de procedencia (o quedan como «zascarr» si no constaba).

---

## 4. Fuentes, tradición y cortesía

### 4.1 Identidad y fuentes consultadas

- Se usan las identidades **ya asociadas** (`Series.comic_vine_id`, `anilist_id`,
  `tebeosfera_slug`, `gcd_id`; `Issue.comic_vine_id` para el número). #129 A/B ya permite asociarlas
  con confirmación; #482 no repite esa operación.
- Si no hay identidad para la tradición: «Esta serie no está asociada a una fuente. Asóciala primero»
  + enlace a `/ui/series/{id}/asociar` (`web/asociar_fuente.py:90-156`). **No** se busca por título
  como atajo (evita equivalencias falsas; se apoya en la decisión de #129 de que asociar es explícito).
- Fuentes por tradición (ADR 0002): la misma tabla del enricher (`services/enricher.py:82-84,286-295`):
  CV para american/british, AniList para manga/manhwa/manhua, Tebeosfera para tebeo/franco_belgian.
  GCD queda para fumetti/BD antigua; como **secundaria** de american/british es decisión P2 (hoy el
  enricher no la usa; sí Descubrir y el detalle de #465).
- Las fuentes encendidas se leen de Ajustes (ADR 0013, `config.py:55-61`); una fuente apagada **no se
  instancia ni se consulta** (`discovery.py:453-470` ya hace esa comprobación y #133 clasifica).
- Varias fuentes asociadas y encendidas de la misma tradición: se consultan todas; la persona elige.
  No hay «prioridad» en el núcleo.

### 4.2 Peticiones, presupuesto y cortesía

| Fuente | Peticiones para una propuesta de número | Notas |
|---|---:|---|
| CV | ≤2 | `get_volume` (editorial/año) + `get_issue_detail` (sinopsis/fecha/créditos); si falta `issue.comic_vine_id`, 1 búsqueda de número más (≤3) |
| Tebeosfera | ≤2 | `get_collection` + `get_numero_de_coleccion` (o `get_numero`); el detalle ya normaliza |
| GCD | ≤2 | `get_series` + `get_publisher` (solo para el nombre); sin detalle de número |
| AniList | 1 | Búsqueda por título y comprobación de que el id coincide con la identidad asociada; si no hay forma fiable, `sin_metodo_autorizado` (S5 puede añadir consulta por id) |

- **Total ≤5 peticiones por acción** (no por campo). Una sola ronda; sin reintentos automáticos; sin
  segundo plano; sin caché entre aperturas.
- **Cortesía compartida:** todos los clientes pasan por `utils/peticiones.py:228` y
  `utils/cortesia.py` (cola por fuente/host). Ritmos de `config.py:44,72,82,90` (CV 1,0 s, AniList
  1,5 s, Tebeosfera 2,5 s, GCD 2,0 s). `espera_max_s` interactivo bajo (p. ej. 3 s): si la espera
  estimada lo supera, se devuelve `limite_de_cortesia` con el reintento y **no se hace esperar al
  navegador**; el usuario puede volver a pulsar.
- **Estados cerrados de #133** (`services/estados_fuentes.py:12-31`): `ok`, `sin_resultados`,
  `fallo_transitorio`, `configuracion_incompleta`, `limite_de_cortesia`, `fuente_apagada`. Cada uno
  con su texto llano; ninguno se presenta como «no existe el tebeo».
- Fuente apagada o CV sin clave: **cero peticiones**, estado explicado, resto de fuentes sigue.
- Fallo de una fuente: se muestran las demás; si todas fallan, no se borra el plan local.

### 4.3 Qué se guarda de la fuente

Solo lo que la persona elija. El valor y la etiqueta de fuente viven en la sesión de propuesta; al
guardar se escriben en el XML y en `metadata.comicinfo_fuente` (D6). No se crean fuentes, no se
modifican sus ajustes, no se guardan credenciales ni URLs con claves. Enlaces a fichas: solo
`http(s)`, validados por el mismo criterio que `site_url` en Descubrir/asociar; nunca se usan como
`<img src>` (regla de hotlinking).

---

## 5. Encaje con #109, #480 y #481

### 5.1 Lo que ya hay (no se duplica)

- **#480**: vista previa del plan de B6 y token firmado (propósito `comicinfo_ficha`, TTL 15 min,
  `MAX_TOKEN_COMICINFO = 8192`), aplicación del **mismo** plan con verificación de stat/hash y guardián
  #488 con aviso + confirmación (`services/comicinfo_ficha.py:47-48,81-182,254`; rutas
  `web/series.py:1083-1118`; plantilla `_comicinfo_previa.html`).
- **#481**: `CAMPOS_GESTIONADOS` con autores/género/páginas (`core/comicinfo_write.py:36-46`), mapa
  `_LOCK_DE` (`tagger.py:69-88`), autores desde `issue_creators`, géneros de `series.genres` y páginas
  de `issue.page_count` (`tagger.py:278-331`), escritura con `comicinfo_propio` (`tagger.py:692-714`).
- **#109**: procedencia visible **por heurística**, no por campo guardado: el docstring de
  `services/procedencia.py:1-17` dice explícitamente que no hay registro por campo y que no se
  inventa; `metadata_source` es univaluada. `locked_fields` y las propuestas de #128 tampoco se
  persisten.
- **#449**: cobertura local (sinopsis/autores/fecha) en Estado (`services/cobertura.py:33-70`,
  `web/estado.py:56`); no hay cifras reales de producción (NOT RUN).
- **#488**: `estado_de_comparticion` (`services/compartidos.py:31-50,146`) y su aviso en #480; escribir
  ComicInfo sobre un compartido pide confirmación explícita (no bloqueo duro, enmienda del PO).

### 5.2 Cómo encaja #482

- **No hay segunda vista previa ni segundo plan.** `ComicInfoFichaService` gana una operación de
  propuestas de fuentes (solo lectura) y la aplicación de una **selección** sobre el plan de #480:
  el plan se recalcula una vez con los valores elegidos (D4) y se aplica por el mismo camino y las
  mismas comprobaciones.
- **Sesión de propuestas efímera (D8)**: el token de #480 no puede llevar valores de fuente (topes de
  8192 bytes y muchos campos); las propuestas se guardan en memoria del proceso con
  `operacion_id` (UUID), TTL 15 min, tope de sesiones y limpieza. El formulario final envía el token de
  #480, el `operacion_id` y las **claves** de las opciones elegidas; el servidor comprueba que el
  archivo/serie coinciden, que la sesión sigue viva, que las claves existen en la sesión y que
  stat/hash no cambiaron, y solo entonces construye y aplica el plan. El cliente nunca envía valores
  crudos.
- **Procedencia**: `metadata_["comicinfo_fuente"]` por tag (D6) y `comicinfo_propio` como hasta ahora.
  No se toca `metadata_source` (serie) ni se inventa un usuario. La vista previa enseña la fuente y el
  enlace; #109 podría leerla en una entrega posterior (no en el núcleo).
- **Precedencia**: se reutiliza B6 (`core/comicinfo_write.py:78-135`) con una autorización adicional
  por campo elegido; `locked_fields` se aplica al final (`tagger.py:317`). La edición del plan local
  (sin fuente) sigue funcionando aunque no haya ninguna propuesta.
- **Idempotencia y resultado incierto**: `operacion_id` + token + selección; repetir devuelve el mismo
  resultado sin reescribir; sesión caducada ⇒ «vuelve a buscar»; fallo del `commit` tras escribir ⇒
  resultado incierto y reconciliación por el patrón #480/B6; nada de éxito sin releer.
- **#488**: la propuesta es solo lectura; el aviso/confirmación de compartido se mantiene en el paso de
  guardar, no en la propuesta.
- **#478**: los CBR no se pueden etiquetar: la vista previa ya muestra «Conviértelo primero» (#480); la
  propuesta de fuentes sigue el mismo camino (no se propone para un CBR hasta convertirlo).

---

## 6. UX y textos

### 6.1 Dónde

- Se **extiende la vista previa de #480**, que ya se abre desde la lista de archivos de la ficha de
  serie (`series_detail.html:212-215`) y de la ficha de número (`issue_detail.html:71-74`). No hay
  pantalla nueva ni un segundo botón principal.
- En esa vista, tras el plan local: una sección «Datos de las fuentes» con el botón secundario
  **«Buscar datos en las fuentes»**. Sin fuentes asociadas/encendidas no se muestra el botón: se
  muestra la explicación y el enlace a #129/Ajustes.
- Al pulsar, se sustituye solo esa sección (HTMX, `hx-target` local, `no-store`), sin recargar ni
  perder el plan local. Mientras consulta: «Consultando las fuentes…» (indicador existente, sin JS).
- El botón principal sigue siendo **«Guardar información en el tebeo»**, que envía el token de #480,
  la sesión y lo elegido.

### 6.2 Tabla de propuestas (por campo)

Una fila por campo con propuesta, con etiqueta en español (`Year` → «Año», `Publisher` → «Editorial»,
`Summary` → «Sinopsis», `Writer` → «Guionista», `Penciller` → «Dibujante», etc.):
- valor actual (o «Sin dato»), y opciones: una por fuente con su valor, su nombre y el enlace a la
  ficha; «Conservar lo actual» siempre disponible;
- cada opción es un `input type="radio"` con `name="campo:<tag>"` y valor opaco de la opción
  (p. ej. `fuente:id`); el servidor valida la clave contra la sesión;
- si el dato es de serie, se añade «(de la serie, no del número)»;
- si está protegido, chip «Protegido» y sin opciones (solo lectura);
- si solo hay una fuente y coincide con el actual, no se ofrece cambio; se dice «Ya coincide»;
- los campos sin propuesta se agrupan al final en `<details>` «Sin datos nuevos en las fuentes», para
  no alargar la pantalla.

Resumen antes de guardar: «Has elegido 3 cambios de 12 campos con propuesta.» Si no se elige nada, el
botón guarda el plan local como hoy; no se bloquea.

### 6.3 Estados vacío/error (textos llano, sin jerga)

| Situación | Texto propuesto |
|---|---|
| Ninguna fuente encendida | «No hay fuentes de datos encendidas. Enciéndelas en Ajustes o guarda lo que ya tienes.» (sin tráfico) |
| Serie sin identidad asociada | «Esta serie todavía no está asociada a ninguna fuente. Asíciala primero para poder completar sus datos.» + enlace a #129 |
| Fuente apagada para esa tradición | «{Fuente} está apagada en Ajustes; no se ha consultado.» |
| Ninguna propuesta | «Las fuentes no tienen datos nuevos para este tebeo. Puedes guardar lo que ya tienes.» |
| Una fuente falla | «{Fuente} no responde ahora. Se muestran los datos de las demás.» |
| Cortesía | «Hay que esperar unos segundos antes de volver a preguntar a {Fuente}.» + reintento |
| Sesión caducada | «La búsqueda de datos ha caducado. Vuelve a buscar; no se ha cambiado nada.» |
| Archivo cambiado | «El tebeo cambió desde que viste la vista previa. Vuelve a abrirla; no se ha cambiado nada.» |
| Archivo compartido | El aviso de #488, junto al botón de guardar y con su confirmación explícita |
| Error al guardar | Causa y acción en llano; nunca un código ni un JSON en la rejilla |

### 6.4 Presupuesto de texto y accesibilidad

- Una frase de entrada por bloque de ≤20 palabras; ≤50 palabras visibles antes del primer control;
  el detalle de fuentes/errores va en `<details>` (U21). No aparecen «token», «proveedor», «API»,
  «id externo» ni etiquetas inglesas del XML en pantalla.
- Cada campo es un `fieldset` con `legend`; los radios tienen nombre accesible que incluye el campo y
  la fuente; el resultado se anuncia en `aria-live`; tras cargar propuestas, el foco va al título de
  la sección (no se roba al escribir); nada depende solo del color; texto ≥14 px; en móvil, tarjetas
  en una columna (sin tabla horizontal); no se usa `hx-confirm` para lo destructivo (aquí no hay
  destrucción; el guardado ya confirma).
- Una sola acción principal por pantalla: «Guardar información en el tebeo». «Buscar datos en las
  fuentes» es secundaria.

---

## 7. Seguridad y legal

### 7.1 Seguridad

- **Propuesta = solo lectura**: no escribe BD, archivos, `locked_fields` ni `metadata_`; solo consulta
  fuentes encendidas y guarda la sesión efímera en memoria. La escritura ocurre solo en el guardado
  explícito por el camino de #480.
- **Sin mass assignment**: formulario con `Form(...)` explícito; el servidor acepta solo el token de
  #480, el `operacion_id` y claves de opción **validadas contra la sesión**; los valores crudos nunca
  llegan del cliente. Las claves deducidas no se reconstruyen por el cliente.
- **XSS/inyección**: valores de fuente son datos no confiables; se pasan a texto plano
  (`utils/texto_html.py:51`), se escapan con Jinja y nunca se usan en `class`/`id`/`style`/`hx-*` ni
  con `|safe`/`Markup`. Enlaces solo `http(s)` validados; sin imágenes de fuente (hotlinking prohibido).
- **Topes**: campos y longitudes (§3.2), número de propuestas por campo/fuente, sesiones en memoria,
  peticiones por acción (§4.2); sin bucles ni reintentos; sin abrir clientes de fuentes apagadas.
- **Privacidad**: sin usuario, sesión ni IP en la procedencia; no se guardan valores ni URLs de fuente
  en `structlog`; errores con clase de error y fuente, no con datos del coleccionista; `no-store` en
  fragmentos con estado. El `operacion_id` es opaco y no da acceso a datos por sí solo (se valida token
  + sesión + archivo).
- **Cortesía y superficie**: solo los clientes existentes, con sus rate limits y cola compartida; sin
  scraper nuevo, sin peticiones masivas ni en segundo plano; sin socket Docker/root; sin cambios de
  middleware; sin credenciales en URLs/logs.
- **Regresión**: `locked_fields` sigue mandando; una fuente no puede pisar un campo protegido por
  mucho que se seleccione. El plan firmado de #480 y el guardián #488 no se debilitan.

### 7.2 Legal

- Las fuentes se consultan solo si el coleccionista las enciende (ADR 0013) y con la cortesía
  existente; #482 no añade scraping nuevo.
- LEGAL.md: los metadatos son «cache local del usuario final, para uso privado» y no se redistribuye
  ninguna base pre-poblada (LEGAL.md:43-44,108). **Riesgo nuevo a valorar:** escribir sinopsis o
  créditos de una fuente dentro del archivo y que el usuario comparta ese archivo (D3 de BL-CNV:
  archivos de la biblioteca pueden estar en Transmission/aMule). Es una forma de redistribuir el
  metadato, aunque sea el usuario quien comparte. No se decide aquí: lo eleva el PO/legal (P7).
- GCD es CC BY-SA 4.0: si se usa como fuente (P2), la atribución/enlace de vuelta es obligatoria en los
  resultados; embeber sus datos en el archivo sin atribución es un riesgo añadido. Recomendación:
  GCD solo factual (año/editorial) y enlace visible, o excluirla del núcleo.
- Tebeosfera es *sui generis* y el espaciado de 2,5 s es mínimo del proyecto; se respeta igual que en
  el enricher.
- Sin telemetría; sin nuevos datos personales.

---

## 8. Partición en historias

### 8.1 Núcleo (4 PR)

| Historia | Contenido | Escribe | No escribe | Depende de | Est. |
|---|---|---|---|---|---|
| **CNV5-1 · Contrato y capacidades** | Módulo puro `propuestas_comicinfo` con la matriz fuente×campo, elegibilidad (identidad/`LanguageISO` fuera), normalización/topes, tipos `PropuestaCampo`/`OpcionPropuesta`, presupuesto de peticiones; pruebas unitarias. Sin red ni UI. | Nada | BD, archivos, red | #480/#481 (contrato), #133, ADR 0002 | **S (2)** |
| **CNV5-2 · Propuestas desde fuentes asociadas** | Servicio de solo lectura que, para un archivo, consulta las fuentes asociadas+encendidas de la tradición, reúne detalles por fuente, construye propuestas por campo y estados #133; fallos parciales; sin UI ni escritura. Pruebas con dobles de los cuatro clientes y fixtures. | Nada (solo lee) | BD, archivos, sesión persistente | CNV5-1; #129 A (identidad); #488 no aplica (no escribe) | **M (5)** |
| **CNV5-3 · UX de propuesta y selección** | Rutas `GET/POST …/comicinfo/fuentes`, almacén de sesiones en memoria con TTL, plantilla de tabla por campo, estados vacío/error, textos, accesibilidad; el guardado sigue siendo el de #480. Pruebas web/HTMX y composición. | Sesión en memoria; nada de BD/archivo | Archivo, BD, token nuevo | CNV5-2 | **M (5)** |
| **CNV5-4 · Aplicar la selección con el plan firmado** | **CANCELADA por el PO (2026-11-10):** no se escriben datos de fuentes en el archivo ni en `metadata_`; el alcance queda en solo lectura/local (CNV5-1..3). Se conserva como histórico de la propuesta. | Nada | Archivo, BD, `metadata_` | — | **Cancelada** |

**Núcleo: 2+5+5+5 = 17 puntos nominales**, por encima de los 13/XL originales; la estimación 13 era
«confianza Baja» y este reparto es más honesto. Si el PO necesita ≤13, se puede fusionar CNV5-1 con
CNV5-2 (contrato + servicio, 5) y dejar el núcleo en 15, o recortar campos del núcleo (p. ej. sin
créditos ni PageCount) a CNV5-5. No se crean tarjetas hijas en este encargo.

### 8.2 Historias opcionales

| Historia | Contenido | Depende de | Est. |
|---|---|---|---|
| **CNV5-5 · Ampliar fuentes/campos** | GCD como secundaria (P2), `Genre` desde AniList/CV (consulta de campos en la misma petición), `PageCount` de CV y semántica de `paginas` de Tebeosfera, créditos en fuentes que los tengan; pruebas de contrato y de topes. | CNV5-1/2, PO P2/P3, legal P7 | **M (5)** (posible partición) |
| **CNV5-6 · Persistir en el catálogo** | Llevar lo elegido a las columnas/relaciones de la BD (`Series`/`Issue`/autores/géneros/páginas) con el plan de #128 y la procedencia por campo de M6, antes del ComicInfo; actualizar #449. | CNV5-4, PO P4; #109/#128 | **M (5–8)** |

### 8.3 AC y EARS por historia

**CNV5-1 (contrato)**
- EARS: **DONDE** un tag es identidad o `LanguageISO`, el contrato no lo ofrecerá.
- AC-1: la matriz declara fuente y nivel por campo; un test recorre `CAMPOS_GESTIONADOS` y comprueba
  que identidad/`LanguageISO` nunca son elegibles.
- AC-2: normalización (HTML→texto, topes, año, páginas, listas) con casos límite; valores fuera de
  tope se descartan con motivo.
- AC-3: presupuesto y estados #133 definidos como constantes/tipos; 0 peticiones para fuentes
  apagadas (prueba de que el contrato no instancia clientes).

**CNV5-2 (propuestas de fuentes)**
- EARS: **CUANDO** pido datos de un tebeo asociado, **ENTONCES** se consulta solo cada fuente
  encendida y admitida por su tradición, con una ronda y el presupuesto; **SI** una falla, las demás
  siguen; **MIENTRAS** no haya escrito, no se escribe nada.
- AC-1: una fuente asociada y encendida produce propuestas con valor, fuente, nivel y enlace;
  ninguna fuente apagada produce tráfico (doble que falla si se instancia).
- AC-2: CV devuelve sinopsis/fecha/editorial/créditos del número cuando hay detalle; Tebeosfera
  devuelve año/editorial/páginas del número; AniList solo nivel serie; GCD solo año/editorial de serie.
- AC-3: fallo/parcial: una fuente `fallo_transitorio` se explica y no impide las otras; cero
  propuestas no es un error.
- AC-4: cortesía: espera por encima del presupuesto ⇒ `limite_de_cortesia` con reintento; no se
  espera bloqueando la petición HTTP de la UI.
- AC-5: sin identidad ⇒ no se consulta ninguna fuente y se devuelve el motivo + acción #129.
- AC-6: 0 escrituras en BD/archivo (contador de sentencias/efectos).

**CNV5-3 (UX)**
- EARS: **CUANDO** abro la vista previa de ComicInfo y pido datos de fuentes, veo una fila por campo
  con el actual, las opciones y su fuente; **SI** no hay fuentes/identidad/datos, veo el estado
  explicado; **MIENTRAS** elijo, el archivo no cambia.
- AC-1: fragmento con una fila por campo propuesto, etiquetas en español, opciones con fuente y
  «conservar»; ningún valor crudo en atributos ni en `hx-*`.
- AC-2: estados de §6.3 con textos exactos; sin jerga interna; presupuesto ≤50 palabras antes del
  primer control.
- AC-3: accesibilidad: `fieldset`/`legend`, radios con nombre que incluye campo+fuente, foco al
  cargar, `aria-live` del resumen, sin depender del color; composición HTMX sin controles sin nombre.
- AC-4: sesión caducada/reinicio ⇒ no se puede aplicar; «vuelve a buscar»; cero escrituras.
- AC-5: `no-store` en el fragmento; sin JS nuevo; un solo botón principal.

**CNV5-4 (aplicar)**
- EARS: **CUANDO** guardo con una selección, **ENTONCES** se aplica el plan de #480 con esos valores,
  se respeta `locked_fields` y se anota la procedencia; **SI** el archivo o la selección cambiaron,
  **ENTONCES** no se escribe y se pide revisar; **SI** se repite, no se duplica.
- AC-1: selección válida ⇒ plan con `cambia`/`conserva`/`bloqueado` correcto; los tags no elegidos no
  cambian; `Series`/`Number`/`Volume`/`LanguageISO` no aparecen aunque una fuente los traiga.
- AC-2: `locked_fields` bloquea aunque se seleccione; el valor actual de procedencia desconocida se
  conserva si no se elige.
- AC-3: `metadata.comicinfo_fuente` con fuente/id/enlace/nivel por tag cambiado; `comicinfo_propio`
  sigue como autoría; sin usuario/IP.
- AC-4: archivo/hash/stat distinto desde el token/sesión ⇒ `propuesta_desactualizada`, sin escritura;
  sesión caducada ⇒ `caducado`; sin token/sesión/manipulación ⇒ rechazo.
- AC-5: compartido ⇒ aviso #488 y confirmación explícita antes de escribir (no bloqueo duro, como
  #480); resultado incierto ⇒ 503 + «Comprobar»; repetir token+selección no duplica.
- AC-6: prueba de integración Postgres real + CBZ de fixture: solo se cambian los tags elegidos,
  hash/tamaño se recalculan, y el resto del XML se preserva (B6).

**CNV5-5/6 (opcionales)**: AC propios al refinarlas; dependen de decisiones P2/P3/P4 y no se
comprometen ahora. No se inventan campos: si un cliente no los devuelve, no hay propuesta.

---

## 9. Decisiones abiertas del PO, riesgos y límites de esta investigación

### 9.1 Decisiones del PO (hechos vs propuestas)

**Hechos verificados en `fceaf87`:** #480 ya firma/aplica el plan de ComicInfo y #481 amplió campos y
locks; #109 no guarda procedencia por campo (solo heurística) y `metadata_source` es univaluada; #449
mide cobertura local sin datos reales de producción; #488 avisa de compartidos; los clientes actuales
devuelven los campos de §3.1 y **no** devuelven géneros ni datos de número en AniList/GCD; GCD no está
en el enrutado del enricher; no hay tabla de propuestas ni de procedencia por campo.

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| **P1** | ¿Se exige identidad asociada? | (a) solo fuentes ya asociadas (#129); (b) buscar por título dentro de #482 | **(a)**: evita equivalencias falsas y reutiliza la confirmación de #129; (b) reabre el problema de identidad |
| **P2** | Fuentes por tradición y GCD | (a) solo el mapa de ADR 0002 (CV/AniList/Tebeosfera); (b) GCD secundaria para american/british y fumetti/BD | **(a) en el núcleo**; (b) en CNV5-5 tras verificar API/términos y con atribución |
| **P3** | Campos del núcleo | (a) Year, Publisher, Summary y créditos CV; (b) además PageCount de Tebeosfera; (c) además Genre | **(a) + PageCount solo si se verifica la semántica**; (c) cosa de CNV5-5 |
| **P4** | ¿Persistir en BD? | (a) solo XML + `metadata.comicinfo_fuente`; (b) actualizar también `Series`/`Issue`/autores/géneros/páginas con #128/M6 | **(a) en el núcleo** (menos riesgo, respeta el alcance «ComicInfo»); (b) CNV5-6, decisión con #449 |
| **P5** | Sustituir valores existentes | (a) solo si la persona marca ese campo (autorización explícita); (b) nunca sustituir, solo rellenar | **(a)**, con `locked_fields` intocable y valor actual por defecto; (b) obliga a #480/borrado manual |
| **P6** | Almacenamiento de la sesión | (a) memoria con TTL (single worker); (b) tabla+migración; (c) firmar valores en token | **(a)**: no hay migración, el token de #480 no cabe con valores y la sesión es efímera por naturaleza; (b) si se quiere propuesta persistente/auditoría, decisión aparte |
| **P7** | Legal de embeber sinopsis/créditos de fuentes y compartir el archivo | (a) mantener como #480/B6 (ya escribe sinopsis locales) + aviso; (b) limitar a campos factuales; (c) revisión legal antes | **(c)**: es un cambio de frontera (redistribución por el usuario); no se decide en la spec |
| **P8** | Nivel serie vs número | (a) solo datos del número para campos del número; (b) permitir nivel serie etiquetado para Year/Publisher, no para Summary | **(b)** para Year/Publisher; **nunca** sinopsis de serie como del número |
| **P9** | Presupuesto/cortesía de UI | (a) ≤5 peticiones, `espera_max_s` 3 s, sin esperar en el navegador; (b) esperar hasta completar | **(a)**; si el PO ve demasiadas fricciones, subir a 5 s y medir en Pi |
| **P10** | Si no hay propuestas | (a) dejar guardar el plan local de #480; (b) bloquear | **(a)**: #482 no debe romper el camino que ya funciona |
| **P11** | Idioma de campos de fuente | (a) valor tal como lo da la fuente, sin traducir; (b) traducir géneros/roles a español | **(a)** para no inventar; los nombres de roles ya se muestran en español, el valor de `Genre` se decide en CNV5-5 |

### 9.2 Riesgos

| ID | Riesgo | Prob./impacto | Mitigación |
|---|---|---|---|
| R1 | Identidad/asociación equivocada ⇒ propuestas de otro tebeo | Media/alta | Solo identidades confirmadas por #129; sin búsqueda por título; fuente y enlace visibles; elección manual |
| R2 | Cobertura real de las fuentes baja; la historia no aporta | Media/media | #449 (local) y censo de campos reales antes de comprometer; S5 opcional; no se prometen campos que no existen |
| R3 | Fuente caída/cortesía ⇒ frustración | Media/media | Estados #133, fallos parciales, presupuesto, reintento explícito; no bloquear el plan local |
| R4 | Valores con HTML/scripts o demasiado largos | Baja/alta | Texto plano, topes, autoescape, sin `safe`/`Markup`, pruebas XSS |
| R5 | Sustituir un dato manual sin querer | Baja/alta | Default conservar; solo el campo marcado; `locked_fields` siempre; aviso del cambio |
| R6 | Sesión perdida al reiniciar/worker | Media/baja | TTL y mensaje «vuelve a buscar»; no se anuncia éxito; idempotencia por operación |
| R7 | Token/sesión manipulados | Baja/alta | Token HMAC de #480 + sesión con claves opacas; validación de archivo/serie/stat/hash; el cliente nunca manda valores |
| R8 | Escribir en un archivo compartido | Baja/alta | Guardián #488 con aviso + confirmación; no se toca nada hasta el `os.replace` de #480 |
| R9 | Embeber datos de fuente y compartirlos (legal) | Media/media | P7; atribución GCD; limitar a factuales si el legal lo pide |
| R10 | Duplicar la lógica de #128/#480 | Media/media | Un único plan (B6) y un único escritor (#480); #482 solo propone y elige |
| R11 | Coste en Pi (5 peticiones con cortesía) | Media/baja | Topes, `espera_max_s`, sin caché oculta, medir antes de desplegar (NOT RUN) |
| R12 | Confusión por exceso de campos/fuentes | Media/media | Resumen y `<details>`, etiquetas claras, defaults, presupuesto de texto |

### 9.3 PASS / FAIL / NOT RUN de esta investigación

- **PASS (código leído):** #480 y #481 implementados y sus contratos localizados; #109 no tiene
  procedencia por campo; #449 mide cobertura local; #488 avisa; capacidades actuales de los cuatro
  clientes y su enrutado por tradición; no hay búsqueda automática ni tabla de propuestas.
- **FAIL:** no se ha ejecutado nada; no hay evidencia de que la cobertura real de campos sea
  suficiente; no existe hoy ningún campo de género/página de CV ni géneros de AniList.
- **NOT RUN:** llamadas a fuentes reales; censo real de campos vacíos por tradición; semántica de
  `paginas` de Tebeosfera (número vs colección); `page_count` de CV; géneros/tags de AniList; datos de
  número en GCD; pruebas en navegador, lector (Kavita), Pi y móvil; revisión legal de P7; validación
  con coleccionistas.
- **Límites:** #482 no autoriza código, fuentes reales, migraciones en producción ni despliegue; este
  documento es insumo para el PO y no mueve el tablero.

### 9.4 Caducidad y seguimiento

Caduca con la ficha BL-CNV (~2027-01-06) o antes si cambia el contrato de #480/#481, el plan de B6,
`locked_fields`, la cobertura de #449 o las fuentes. La PR es **solo documentación** y no se fusiona en
este encargo; el Lead decide cuándo entra y qué tarjetas crea (no se crean hijas aquí).
