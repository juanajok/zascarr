# Refinamiento de #129 (MIT-M6-US03) — y desbloqueo de #233 (BL-R4)

> **Estado:** propuesta de refinamiento para el PO. **No implementa código, no crea migraciones, no
> ejecuta pruebas, no consulta fuentes reales y no toca el tablero ni el backlog.** Recomendar no es
> decidir: las casillas abiertas de §6 las marca el PO.
> **Contraste:** `origin/main` = **`5f27b3ef967130266a892c7244fbded590f1e9f0`** (2026-11-09), leído en el
> worktree aislado `.squad/wt-129-spec`, rama `docs/129-spec`, creada desde ese `origin/main`.
> El código no cambió entre `ea230e5` y `5f27b3e` (solo entró el borrador previo citado abajo); las
> citas `fichero:línea` se refieren a este SHA y caducan cuando `main` avance.
> **Insumos:** issue #129 completo (cuerpo y comentarios), #109 (contrato compartido), #128 y #127
> (implementadas), #233/BL-R4, #124/#182/ADR 0003 (vocabulario e identidad), #133/#134 (estados y
> cortesía), `docs/design/historias-reconciliacion-plex-2026-10-18.md`,
> `docs/design/benchmark-reconciliacion-plex.md`, `docs/design/rebanada-2-elegir-serie-y-vincular.md`,
> `docs/design/procedencia-127.md`, `docs/design/enriquecimiento-preview-128.md` y
> `docs/design/bl-r1-deshacer-vinculacion.md`.
> **Borrador previo (ya en `main`):** `docs/design/especificacion-M6-US03-asociar-fuente.md`
> (612 líneas, commit `703f266`, fusionado en `5f27b3e` por el PR #535; contrastado a `04ab6ee`).
> Se conserva como inventario del código y detalle de contrato; **este documento fija la decisión de
> entidad, la frontera con #128/#233, la partición y los D3/D4 de BL-R4**, que el borrador no cerraba.
> Donde difieran, manda este refinamiento.
> **Método:** lectura de código, issues y documentos en ese SHA; sin ejecutar pruebas ni peticiones a
> fuentes. Lo no comprobado va marcado **NOT RUN** o `[sin verificar]`; ningún dato de fuente real.

---

## 1. Problema local y frontera con #128 y #233

### 1.1 Qué pide #129

La historia pide **proponer y confirmar correspondencias entre catálogos** para enriquecer sin
identidades falsas. Su troceo propuesto (A: proponer y comparar; B: confirmar y guardar) y sus once
criterios están en el issue; su DoR exige cerrar **qué entidad se asocia**, la **cardinalidad**, la
**procedencia**, la **corrección** y la **vigencia/idempotencia** antes de estar lista. #129 no
autoriza metadatos, archivos, migraciones ni consultas masivas.

### 1.2 Qué existe hoy (verificado en el SHA de contraste)

| Hecho | Evidencia | Consecuencia para #129 / #233 |
|---|---|---|
| Una serie tiene, como máximo, **un id por fuente**, en columnas únicas paralelas: `comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`. Varias pueden estar llenas a la vez, pero **nada las lee en conjunto**. | `src/zascarr/models/__init__.py:410-421` | El modelo ya soporta la asociación múltiple **sin migración**; falta la operación y su procedencia. |
| **No hay** tabla, campo, servicio, ruta ni plantilla de «asociar fuente»; tampoco «relación confirmada» ni «discrepancia». | Un `git grep` de «asociar» y «discrepancia» en `src/zascarr` solo devuelve comentarios de cortesía (p. ej. `services/tebeosfera.py:78`); rutas de ficha en `web/series.py:341,375,395`; revisión en `api/revision.py:331-476` | A y B son trabajo nuevo; no hay contrato previo que reutilizar, solo mecanismos (tokens, comprobantes, huellas). |
| El enricher **excluye** any serie con uno de los cuatro ids y nunca asocia otra fuente: «es una acción explícita y confirmada, que no existe todavía». | `services/enricher.py:33-36`, `:194-202` | #129 no contradice al enricher: le da el camino que el propio código reclama. |
| `metadata_source` es **univaluada** y significa fuente del alta/enriquecimiento; `manual` bloquea el enriquecimiento entero. | `models:424`, `services/enricher.py:202`, `services/enriquecimiento_plan.py:343-348` | No sirve para representar varias fuentes; no se toca al asociar. |
| `locked_fields` protege **campos** por nombre y el plan #128 lo respeta (`bloqueado`, `conservar`, «la identidad existente no se sustituye»). | `models:431`, `services/enricher.py:287-297`, `services/enriquecimiento_plan.py:138-158,181-206` | #128 protege **valores**; no modela ni protege la **relación archivo → publicación**. |
| La vista previa de #128 firma el plan con HMAC, TTL 15 min y una **huella** de la ficha; aplicar consume el **mismo** plan y rechaza si cambió. | `services/enriquecimiento_plan.py:343-378,381-420`; `services/tokens_revision.py:30,90-160` | Es el patrón exacto que debe reutilizar #129 A→B, sin duplicar plan por campo. |
| La vinculación en su sitio (2d) guarda, en una sola transacción, `File.issue_id`, `metadata_source='manual'` y **`metadata.vinculo`** con `version, operacion_id, fecha, serie_id, numero, formato, previo`. | `services/vinculacion.py:380-397` | Es la **evidencia durable** de una relación archivo→publicación confirmada por una persona (base de D3 de BL-R4). |
| Los caminos manuales heredados («organizar» V6a y asignar desde Pendientes) escriben `issue_id` y `metadata_source='manual'` **sin** `metadata.vinculo`. | `services/asignacion.py:578-581`; `services/review.py:319-322`; `docs/design/bl-r1-deshacer-vinculacion.md` H4 | Serán relaciones **manuales sin comprobante**: no se pueden llamar «confirmadas» retroactivamente (D3). |
| Deshacer una vinculación (BL-R1) ya existe: quita `issue_id`, conserva la procedencia en `metadata.vinculo_historial`, y admite deshacer **cualquier** vínculo, conste o no su procedencia. | `services/desvinculacion.py:160-176,194-229`; `web/desvinculacion.py:83,101`; tests `test_desvinculacion_pg.py` | #233 tiene ya su operación de corrección y su precedente de «procedencia desconocida». |
| El **rescan** (#BL-R9) re-tría un archivo cuyo contenido cambió sobre la **misma fila** y **cambia o vacía `issue_id`** si la nueva lectura identifica otra publicación o ninguna. No consulta `metadata.vinculo` ni protege la relación manual. | `services/library_adopter.py:600-700` (`_re_triar_cambio`; `fila.issue_id = None` en `:679`, `fila.issue_id = nuevo_vinculo` en `:686`) | **Hoy incumple el criterio 2 de #233**: un rescan puede pisar una relación confirmada. Es el disparador real que BL-R4 debe cubrir. |
| El importador normal no re-tría archivos ya registrados: recorre **solo carpetas de descargas** y deduplica lo repetido; el **enricher** no cambia `File.issue_id` ni la serie de un archivo. | `services/importer.py:489` (`listar_comics(self._scan_dirs, …)`) y dedupe por contenido; `services/enricher.py:382-430` (solo campos del `Issue`) | La única vía automática de disco/BD que hoy puede cambiar la relación es el rescan; las fuentes no proponen relaciones archivo→publicación. |
| #127 (procedencia visible) y #128 (plan por campo) están implementadas; BL-R1 también (servicio, rutas y pruebas). | `services/procedencia.py:175`; `web/series.py:375,395`; `services/vinculacion.py`; `tests/test_desvinculacion_pg.py` | #129 no las duplica; #233 se apoya en ellas. |

### 1.3 Frontera con #128 (previsualizar y aplicar metadatos)

- #128 gestiona **campos** (identidad externa, sinopsis, portada, total, y campos de números
  candidatos) con acciones `anadir / conservar / proponer_sustitucion / omitir_por_ausencia /
  bloqueado`. Su huella incluye los ids y `locked_fields`, y **no toca `File.issue_id`**
  (`services/enriquecimiento_plan.py:447-485`).
- Por tanto, #128 **no puede absorber** los criterios de #233: una discrepancia sobre la **relación**
  archivo → publicación no es un campo del plan y no se puede representar con `bloqueado` ni con
  `conservar`. Esta frontera ya estaba anotada en
  `historias-reconciliacion-plex-2026-10-18.md` §5 y se confirma en el código actual.
- #129 tampoco aplica metadatos: confirma **identidad** (qué ficha externa corresponde a la serie),
  no rellena sinopsis/portada/total ni cambia `metadata_source` ni `locked_fields`.

### 1.4 Frontera con #233 (BL-R4: proteger una relación confirmada y registrar discrepancia)

| Aspecto | #129 (esta historia) | #233 / BL-R4 (la que se desbloquea) |
|---|---|---|
| Objeto | **Serie local ↔ fuente externa**: un identificador de una fuente. | **Archivo → publicación**: la relación que ya existe en `File.issue_id` y que una persona confirmó. |
| Operación | Proponer candidatas y **confirmar** la asociación (escribe el id y su procedencia). | **Garantía**: ninguna actualización automática cambia ni quita esa relación; y **visibilidad** de la discrepancia si una afirmación automática apunta a otra publicación. |
| Efectos | Id de la columna de la serie + `metadata.asociaciones`; nada de metadatos ni archivos. | Guarda la discrepancia y la decisión «Mantener lo mío»; no aplica nada, no toca archivos. |
| Dependencias | #133/#134 para consultar; #127 para mostrar procedencia; #128 como patrón de token/huella. | **D3/D4 de este documento**, #129 **A** como destino de «Revisar», BL-R1 (hecha) para corregir. No depende de #129 B. |
| Lo que NO se duplica | No protege ni registra discrepancias de archivos. | No crea una segunda operación de «asociar fuente» ni otro modelo de procedencia. |

**Consecuencia para desbloquear #233:** #233 no necesita que #129 esté implementada para empezar su
garantía ni su registro de discrepancia; necesita (a) la **decisión de entidad** de §2, (b) **D3/D4**
de §5 ratificados, y (c) que la ruta «Revisar» tenga destino. Como «Revisar» apunta a #129, el orden
recomendado es **#129 A primero** (solo lectura, sin persistencia) y #233 en paralelo con #129 B.

### 1.5 Qué falta (resumen)

1. Decidir **qué entidad se asocia** y con qué identidad mínima (§2).
2. Partir #129 en entregas que permitan empezar #233 sin esperar la persistencia (§3).
3. Contrato EARS/AC por entrega, con errores, idempotencia, propuesta caducada, conflicto,
   repetición y resultado desconocido (§4).
4. **D3 y D4 para BL-R4**: evidencia de «relación confirmada», identidad/procedencia/ciclo de vida de
   la discrepancia y semántica de «Mantener lo mío» (§5).
5. Decisiones del PO, riesgos y pruebas futuras (§6–§7). El benchmark §13 de #129 sigue **NOT RUN**.

---

## 2. Decisión de entidad (D1)

### 2.1 Vocabulario (ADR 0003, aceptado con decisiones diferidas)

| Término | Qué es | ¿Entidad hoy? | ¿Identidad de fuente? |
|---|---|---|---|
| **Obra** | Creación por su título, independiente de ediciones | **No** | Ninguna fuente la aporta; crearla exigiría inventar id (ADR 0003). |
| **Serie** | Agrupación que el coleccionista cataloga | **Sí** (`Series`) | **Sí**: `comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`, uno por fuente (`models:410-421`). |
| **Edición** | Línea de publicación con numeración propia | **No** (ADR 0003; #182 confirma que no está modelada) | No se puede asociar lo que no existe; depende de #184, no de #129. |
| **Publicación / número** | Unidad editorial concreta (grapa, tomo…) | **Sí** (`Issue`) | **Solo** `Issue.comic_vine_id` (`models:489`); AniList/Tebeosfera/GCD no dan id de número en los clientes actuales. |
| **Formato** | Forma de presentación de la publicación | Atributo (`Issue.format`) | No identifica. |
| **Archivo** | Copia física en disco | **Sí** (`File`) | Ninguna fuente lo identifica; su relación con la publicación es **local** (`File.issue_id`). |

### 2.2 Opciones y veredicto

| Opción | Identidad suficiente | Veredicto |
|---|---|---|
| (a) **Serie** (`Series`) | Sí, en las cuatro fuentes; es la unidad del catálogo y la que ya tiene columnas únicas | **Elegida**. `entidad: "serie"` en la propuesta firmada y en la procedencia. |
| (b) **Publicación/número** (`Issue`) | No: hoy solo Comic Vine tiene id de número; no hay capacidad verificada de número para las otras tres (#133 solo acredita `busqueda`, y `detalle` no uniforme por fuente) | **Descartada en #129**. Su identidad es campo del plan #128 (CV) o de #183, con su propio contrato. |
| (c) **Edición** | No existe como entidad ni columna; no hay id externo que la individualice | **Descartada** hasta que #184 decida el modelo. |
| (d) **Archivo → publicación** | No es una asociación a fuente: el archivo no tiene identificador externo | **Fuera de #129**; es la relación que protege **#233**. |
| (e) **Obra** | Ninguna fuente da identidad de obra | **Descartada** por ADR 0003. |

### 2.3 Identidad mínima y vocabulario de la asociación

- **Entidad:** serie local (`Series.id`, UUID) + **fuente** (`comic_vine | anilist | tebeosfera |
  gcd`) + **identificador externo** (entero para CV/AniList/GCD; slug para Tebeosfera), tal como lo
  devuelve la fuente. Título/año **no** son identidad: solo discriminantes visibles.
- **Cardinalidad:** como máximo **una** asociación por `(serie, fuente)` y **varias** fuentes por
  serie. Es lo que ya impone el modelo: una columna física por fuente. Si la serie ya tiene **otro**
  id de esa fuente, no se sustituye: se rechaza y se remite a retirar (B2). Si el id ya pertenece a
  **otra** serie, conflicto explícito, nunca reasignación silenciosa.
- **Procedencia:** `metadata.asociaciones` (JSONB, sin migración) con una entrada por fuente:
  `{version, fuente, id_externo, entidad:"serie", fecha, operacion_id}`. **No** se toca
  `metadata_source` (sigue diciendo quién hizo el alta o el enriquecimiento) ni `locked_fields`.
- **Fuera del vocabulario de #129:** «edición», «obra», «universo», «volumen» como identidad,
  ISBN como id de serie (#182 D7) y «archivo como fuente».

---

## 3. Partición en entregas

| Entrega | Valor | Efectos | Fuera de alcance | Depende de | Talla / PR |
|---|---|---|---|---|---|
| **D0 · Este refinamiento** | Decisiones de entidad, frontera y D3/D4 que desbloquean #233 | Ninguno (documento) | Código, migración, UI | PO | — (esta PR) |
| **A · Proponer y comparar** | Elegir una fuente y ver candidatas con sus discriminantes, sin escribir nada | Solo lectura local + **una** consulta autorizada por acción; **cero** escrituras, metadatos, archivos o catálogo | Persistir la asociación; aplicar metadatos | #133/#134; decisión D1 de §2; patrón #128 | **M** (1 PR) |
| **B · Confirmar la asociación** | Guardar la correspondencia con procedencia y alcance explícitos | Id de la columna de la serie + entrada en `metadata.asociaciones` + informe inmutable; nada más | Enriquecer, fusionar, mover/leer archivos, cambiar `locked_fields`/`metadata_source` | A (token); D3 de §5 (para que BL-R4 consuma la misma evidencia, no obliga a B) | **M** (1 PR) |
| **B2 · Retirar/corregir** | Poder deshacer una asociación equivocada sin perder su historia | Quita el id de **esa** fuente y pasa la procedencia a `metadata.asociaciones_historial` con `deshecho`; no borra serie ni toca otras fuentes | Sustitución atómica; fusión de series | B (mismo release; sin B2 un error de B es permanente) | **S** (en la PR de B o una propia) |

**Orden recomendado y desbloqueo de #233:** `D0 → A → (B + B2)`; **#233 empieza en paralelo a B**, en
cuanto el PO ratifique D0. Motivo: la garantía y el registro de discrepancia de #233 no usan el id
externo ni la persistencia de B; lo único que necesitan de #129 es que «Revisar» tenga una pantalla
destino, y esa es **A** (comparar candidatas). Esperar a B retrasaría #233 sin ganar nada.

**Qué NO se crea todavía:** las tarjetas A, B y B2 no se crean en este encargo; lo decide el Lead
según el flujo. Este documento no mueve el Project ni cambia etiquetas o estimaciones.

---

## 4. Contrato EARS y criterios de aceptación por entrega

### 4.1 Entrega A — Proponer y comparar (solo lectura + propuesta firmada)

**Entradas:** `series_id` (UUID, existe o 404); `fuente` explícita (una de las cuatro, **sin valor por
defecto**); `q` opcional (por defecto `Series.title`, no se inventa con sinopsis ni ids); límite fijo
**≤ 10** candidatas, sin paginar.

**Salidas:** estado de la fuente del conjunto cerrado de #133 para la capacidad `busqueda` (con
`motivo` en español y `reintentar_en` solo si consta); lista de candidatas con título, año, id
externo, URL de ficha y tradición **solo si consta**; los campos ausentes se dicen «no consta»; avisos
(Tebeosfera solo devuelve sagas, fuente apagada, falta de clave, cortesía…); **token firmado** de la
candidata elegida (no de todas), emitido en la previsualización.

**Reglas:** fuente apagada o sin configurar → **sin tráfico** y estado propio; una sola petición de
búsqueda por acción; Tebeosfera no ofrece sagas como candidatas; GCD mantiene el filtro de edición
española ya usado por Descubrir; nada preseleccionado, ni con una sola candidata; ninguna escritura;
ningún fichero leído; ninguna fuente consultada «por si acaso».

**EARS (resumen):**
- **CUANDO** la persona elige una serie identificada, una fuente y pide candidatas, el sistema
  consultará **solo** esa fuente autorizada y devolverá candidatas, no equivalencias.
- **SI** la fuente está apagada, incompleta, en cortesía o falla, **ENTONCES** el sistema distinguirá
  el estado de «no hay candidatas» y no presentará el error como ausencia de la entidad.
- **MIENTRAS** no se confirme, el sistema **no** guardará asociación, no aplicará metadatos y no
  modificará archivos ni catálogo.
- **CUANDO** una candidata se previsualiza, el sistema firmará lo que se vio (serie, fuente, id,
  discriminantes y huella) con caducidad, y rechazará una propuesta manipulada.

**AC-A (cada una con prueba futura):** A1 una sola fuente y sin tráfico si está apagada/sin clave;
A2 candidata ≠ equivalencia y sin preselección; A3 discriminantes acreditados y ausentes como «no
consta»; A4 estados distinguidos (ok/sin resultados/error/apagada/cortesía/incompleta); A5 homónimas y
candidata única exigen elección explícita; A6 saga de Tebeosfera no es candidata; A7 cero efectos (ni
`UPDATE` ni `INSERT`, ni lectura de ficheros, ni proveedores distintos); A8 token con propósito
`asociar_fuente`, contexto y caducidad; A9 huella de la serie + propuesta; A10 repetir la consulta no
duplica ni escribe.

**Criterios de #129 cubiertos:** 1, 2, 3, 4 y 5.

### 4.2 Entrega B — Confirmar la asociación (persistencia idempotente)

**Entrada:** **solo** el token de la previsualización (formulario `Form(...)`, longitud acotada); el
`series_id` de la URL debe coincidir con el contexto firmado.

**Transacción (una sola):** candado consultivo por `operacion_id`; comprobante previo en
`vinculacion_operaciones` con `tipo="asociar_fuente"` → mismo resultado con `repetida: true`; lectura
con `FOR UPDATE` de la serie; revalidación de la huella (título, año, tradición, cuatro ids,
`metadata_source`, `locked_fields`, `metadata.asociaciones` y la identidad firmada de la candidata);
conflicto si el id ya está en otra serie; conflicto si la serie ya tiene **otro** id de esa fuente;
si ya tiene el **mismo**, `ya_asociada` sin escribir; `UPDATE` solo de la columna, `metadata` y
`updated_at`; `INSERT` del comprobante; `commit` al final.

**Salidas:** `asociada | ya_asociada | omitida`, con `motivo` (conflicto de identificador, ya tiene
identidad en esa fuente, propuesta desactualizada, serie inexistente), `repetida`, fecha, fuente, id y
`operacion_id`; efectos contados (`campos_serie:1, asociaciones:1, comprobantes:1, numeros:0,
archivos:0, metadatos_aplicados:0`).

**EARS (resumen):**
- **CUANDO** la persona confirma, el sistema guardará **entidad local, fuente, id externo y tipo de
  entidad**, y nada que no venga del token; no asociará por título/año.
- **SI** repite la confirmación, **ENTONCES** devolverá el mismo resultado sin duplicar ni escribir.
- **SI** el id ya pertenece a otra serie, **ENTONCES** informará del conflicto y no reasignará.
- **SI** la entidad o la candidata cambiaron desde la vista, **ENTONCES** pedirá revisar de nuevo.
- **SI** se pierde la respuesta tras pedir el `commit`, **ENTONCES** no anunciará éxito sin releer y
  un reintento no duplicará.
- **MIENTRAS** queda asociada, el sistema conservará procedencia y alcance y **no** fusionará,
  enriquecerá ni quitará protecciones.

**AC-B:** B1 identidad completa y sin invención; B2 idempotencia por comprobante y por entrada durable
tras la purga; B3 conflicto de identificador; B4 conflicto de misma fuente; B5 huella y propuesta
desactualizada; B6 resultado desconocido (503 + releer, nunca éxito sin leer); B7 cero efectos
colaterales (sin `locked_fields`, sin `metadata_source`, sin `Issue`, sin `File`, sin archivos); B8
procedencia `metadata.asociaciones` versionada y fusionada sin pisar `alta`; B9 repetir la misma
propuesta con otro token no duplica; B10 token caducado con o sin comprobante se explica según
contrato (reutiliza la semántica de `tokens_revision`).

**Criterios de #129 cubiertos:** 6, 7, 8, 9, 10 y 11.

### 4.3 Entrega B2 — Retirar/corregir una asociación

**EARS (resumen):** **CUANDO** la persona retira una asociación, el sistema quitará **solo** el id de
esa fuente y añadirá a `metadata.asociaciones_historial` la procedencia íntegra con
`deshecho:{operacion_id, fecha}`; **no** borrará la serie, **no** tocará otras fuentes ni archivos,
**no** aplicará metadatos; **SI** la procedencia no consta, dirá «procedencia desconocida» y retirará
igual (patrón D9 de BL-R1); repetir la retirada devolverá lo mismo sin escribir.

**AC-B2:** R1 retirar quita solo esa columna; R2 historial conserva la evidencia y no se pisa; R3
serie/otros ids/archivos intactos; R4 procedencia desconocida se puede retirar; R5 idempotencia y
resultado incierto resuelto releyendo. **Criterio de #129 cubierto:** el DoR de corrección y el
criterio 10 (alcance editorial).

### 4.4 Contrato compartido de errores y estados (A/B/B2)

- Fuente: `fuente_apagada`, `configuracion_incompleta`, `limite_de_cortesia`, `fallo_transitorio`,
  `sin_resultados`, `ok` (conjunto cerrado de #133, `services/estados_fuentes.py:12-31`). Nunca un
  error se presenta como «no existe».
- Confirmación: `token_invalido`, `token_caducado`, `propuesta_desactualizada`,
  `conflicto_identificador`, `ya_tiene_identidad_en_esa_fuente`, `serie_inexistente`,
  `conflicto_de_bloqueo`, `resultado_incierto` con textos en español llano y sin códigos internos en
  superficie (`CLAUDE.md` §6/U20).
- Privacidad: sin usuario, sesión, IP ni auditoría; el comprobante no guarda token, rutas ni títulos;
  los logs no llevan valores del coleccionista. Cortesía: **una** petición por acción y los ritmos
  compartidos (Tebeosfera 2,5 s; CV 1,0; AniList 1,5; GCD 2,0 — `config.py:44,72,82,90`).

---

## 5. D3/D4 para BL-R4 (la relación confirmada y la discrepancia)

Estas dos decisiones son **de BL-R4**, no de #129: #129 asocia **series a fuentes**; BL-R4 protege la
relación **archivo → publicación**. Se fijan aquí porque #233 las necesita y porque reutilizan la
evidencia y el patrón de confirmación de #129. Nombres `D3-B4`/`D4-B4` para no confundirlos con los
D1–D5 del borrador previo de #129.

### 5.1 D3-B4 · Qué convierte una relación archivo → publicación en «confirmada»

**Hechos.** Hoy `File.issue_id` lo escriben: (a) la vinculación 2d con evidencia durable
`metadata.vinculo` (`services/vinculacion.py:381-397`); (b) los caminos manuales heredados «organizar»
y asignar desde Pendientes, **sin** esa evidencia (`services/asignacion.py:578-581`,
`services/review.py:319-322`); (c) el importador/matcher y el rescan, automáticamente
(`services/importer.py`, `services/library_adopter.py:679-686`). El rescan **puede cambiar o vaciar**
una relación manual o confirmada sin mirar la evidencia (ver §1.2). BL-R1 ya sabe deshacer cualquier
vínculo y etiquetar la procedencia desconocida (`services/desvinculacion.py:160-176`).

**Estados propuestos (predicado único, sin migración):**

| Estado de la relación | Predicado | ¿Confirmada? | ¿Protegida del cambio automático? |
|---|---|---|---|
| `sin_relacion` | `issue_id IS NULL` | No | — (es re-tríable) |
| `confirmada` | `issue_id` no nulo **y** `metadata.vinculo` válido y coherente: `operacion_id` UUID, `serie_id` UUID igual a la serie del `Issue`, `fecha` y `version` conocidas; escrito por una operación de confirmación que consumió un token firmado de una vista previa | **Sí** | **Sí** |
| `manual_sin_comprobante` | `issue_id` no nulo, `metadata_source='manual'` y **sin** `metadata.vinculo` válido (caminos heredados; relaciones antiguas) | **No** (no se marca retroactivamente) | **Sí, por decisión propuesta**: es una aceptación humana, aunque no conste el comprobante |
| `automatica` | `issue_id` no nulo, `metadata_source` distinto de `manual` y sin `metadata.vinculo` (importador/matcher) | No | No: el rescan puede re-tríarla como hoy |

- **No hay backfill**: las relaciones antiguas no se convierten en «confirmadas» por migración ni por
  fecha; si más adelante se quiere acreditarlas, es una operación explícita de la persona (revisar y
  confirmar), no una inferencia.
- **Evidencia verificable sin usuario ni auditoría:** `metadata.vinculo` (durable) + el comprobante
  inmutable `vinculacion_operaciones` mientras viva (24 h). Pasada la purga, la entrada durable sigue
  siendo la prueba de que una operación de confirmación la escribió; **no se inventa** un usuario,
  sesión, IP ni «quién» lo hizo.
- **Alternativa descartada por ahora:** considerar también los comprobantes de «organizar» en
  `asignacion_operaciones` (filas `limpiada` con `file_id`, `series_id`, `issue_number`, `creado`)
  como evidencia. Es defendible, pero exige casar la fila con el `Issue` actual y añade consultas y
  casos límite; se deja como opción si el PO quiere acreditar más relaciones heredadas.
- **Implementación futura:** función pura `estado_de_relacion(file, issue) -> EstadoRelacion` (sin
  BD) y un guardián de escritura compartido por rescan/importador; pruebas unitarias y de regresión.

### 5.2 D4-B4 · Identidad, procedencia y ciclo de vida de una discrepancia

**Qué es una discrepancia.** Una **afirmación automática** sobre a qué publicación corresponde un
archivo que **difiere** de la relación protegida. No se aplica nunca: se registra para que la persona
decida. Orígenes admitidos (conjunto cerrado): `rescan` (re-triaje de un archivo cuyo contenido
cambió), `comicinfo` (candidato fuerte del XML del propio archivo), `importador`, y en el futuro
`fuente:<comic_vine|anilist|tebeosfera|gcd>` cuando una fuente proponga una identidad de publicación.
Hoy **solo** el rescan y ComicInfo pueden producir una discrepancia; el enricher no cambia
`File.issue_id` ni propone otra publicación para un archivo (verificado en §1.2), así que **no se
inventa** una discrepancia de fuente que el código no genera.

**Identidad de la propuesta (clave estable).** `clave = sha256(json_canónico({origen, fuente?, 
id_externo?, serie_destino_id?, issue_destino_uuid?, numero, formato, titulo_norm?, anio?}))`:
- Incluye **qué afirma** el origen (destino propuesto) y los discriminantes que cambian la decisión;
  **no** incluye la fecha de observación, el score, el nombre del archivo ni la ruta.
- La misma afirmación repetida reutiliza la entrada (no duplica); una afirmación distinta genera
  **otra** entrada (la fuente no queda silenciada).
- La huella de la **relación confirmada** en el momento de detectar (issue_id + serie_id +
  `metadata.vinculo.operacion_id`) se guarda como contexto; si la relación cambia, la entrada deja de
  ser aplicable.

**Procedencia de la discrepancia (sin auditoría):** `origen`, `fuente` si existe, `id_externo` si
existe, `propuesta` (destino y discriminantes vistos), `relacion` (issue/serie/operación
confirmada), `observada_en`, `version`. Sin usuario, sesión, IP ni token.

**Almacenamiento (D4 diferido en la tarjeta; recomendación para no bloquear):**
`File.metadata_["discrepancias"]` como lista versionada limitada (p. ej. 20 entradas; las
`resueltas`/`obsoletas` más antiguas se archivan antes de descartarse). **Sin migración**. Si el PO
prefiere una tabla (p. ej. para vistas de BL-R7), la clave estable permite migrarla después; la
tabla es una decisión aparte con su migración y ADR si toca esquema. La opción JSONB mantiene el
coste en la Pi y el patrón `metadata` ya usado por `vinculo`/`vinculo_historial`.

**Ciclo de vida (conjunto cerrado):**

| Estado | Se llega por | Efecto visible | Sale por |
|---|---|---|---|
| `pendiente` | Detección de una afirmación distinta sobre una relación protegida | Aviso en la ficha (junto a los archivos del número): «una actualización propone otra publicación; no se ha aplicado» | «Mantener lo mío» → `mantenida`; «Revisar» → sigue `pendiente` mientras se revisa; cambio/retirada de la relación → `obsoleta` |
| `mantenida` | Acción explícita «Mantener lo mío» sobre **esa** clave, con confirmación (token) | Deja de mostrarse en el aviso principal; queda en «propuestas descartadas»/historial | Una afirmación **distinta** crea otra `pendiente`; la persona puede reabrir la entrada desde el historial |
| `resuelta` | La persona corrige la relación mediante una operación explícita (BL-R1: deshacer y volver a vincular; o #129 A si la discrepancia es de serie) y la afirmación deja de diferir | Se conserva como historial, sin aviso | — |
| `obsoleta` | La relación confirmada cambió o desapareció, o la afirmación ya no se puede evaluar (la fuente/el número ya no existe) | Se conserva hasta archivarse | — |

- **«Mantener lo mío» no silencia a la fuente.** Recuerda **esa propuesta concreta** (la clave), no
  la fuente ni el archivo. La fuente se sigue consultando en cada ciclo; una **nueva** afirmación
  (aunque venga de la misma fuente) vuelve a aparecer como `pendiente`. No hay «silenciar siempre»,
  ni por archivo ni por fuente. La acción exige confirmación explícita, es idempotente (misma clave →
  mismo resultado, sin duplicar) y deja comprobante en el almacén inmutable que ya usa la retirada
  (`vinculacion_operaciones`, `tipo="mantener_lo_mio"`, purgado a 24 h; la entrada JSONB es durable).
- **«Revisar»**: con la decisión de entidad de §2, abre la revisión que corresponda: **#129 A** si la
  discrepancia es sobre la identidad de la **serie**; el camino existente de deshacer/volver a
  vincular (BL-R1 + 2d) si es sobre la **publicación**. La tarjeta #233 dice literalmente «abre
  #129»; se propone corregir ese texto (decisión PO, §6 P5), porque #129 no mueve archivos ni cambia
  `File.issue_id`.
- **Sin efectos en archivos:** solo lectura de BD y escritura de `File.metadata_` (y del comprobante
  de la acción); ni bytes, ni rutas, ni renombrado, ni borrado. La relación confirmada **no** se
  modifica al registrar ni al mantener: solo una operación explícita de corrección la cambia.

**EARS/AC futuros de BL-R4 (para que #233 pueda refinarse a Ready):**

| AC | Given/When/Then |
|---|---|
| AC-B4-1 | Given un archivo vinculado con la evidencia de D3, Then el sistema lo clasifica `confirmada` (y `manual_sin_comprobante` si es manual sin comprobante, sin marcarlo retroactivamente como confirmado). |
| AC-B4-2 | Given una relación protegida, When el rescan (o cualquier camino automático) obtiene otra publicación o ninguna, Then **no** cambia `issue_id` ni la serie y registra la discrepancia; prueba de mutación: el `UPDATE` automático no toca filas protegidas. |
| AC-B4-3 | Given una discrepancia, Then la ficha muestra qué afirma la fuente y qué se confirmó, sin aplicarlo, y `metadata.vinculo`/`issue_id` permanecen intactos. |
| AC-B4-4 | Given una discrepancia, Then «Mantener lo mío» guarda la huella de **esa** propuesta y desaparece del aviso; otra propuesta distinta vuelve a aparecer; la fuente sigue consultándose. |
| AC-B4-5 | Given «Mantener lo mío» repetido o simultáneo, Then es idempotente (misma entrada, mismo comprobante, sin duplicar). |
| AC-B4-6 | Given cualquier acción de BL-R4, Then 0 archivos leídos/movidos/renombrados y 0 modificaciones de `locked_fields`/`metadata_source`/`Issue`; solo `File.metadata_` (y el comprobante de la acción). |
| AC-B4-7 | Given relaciones antiguas sin evidencia, When se aplica D3, Then no se marcan `confirmada` retroactivamente y se conserva su protección (si el PO ratifica P3). |

### 5.3 Qué queda fuera de D3/D4

Fuera: fusionar series, resolver la discrepancia automáticamente, «aceptar» de un clic, nuevas tablas
o migraciones (se difiere el almacenamiento), auditoría con usuario/IP, notificaciones externas y
vistas de trabajo de biblioteca (BL-R7). #129 no registra discrepancias de archivos; BL-R4 no asocia
fuentes.

---

## 6. Riesgos y decisiones abiertas del PO

### 6.1 Decisiones que debe ratificar el PO (con recomendación)

| # | Decisión | Opciones | Recomendación |
|---|---|---|---|
| P1 | **Entidad de #129** | (a) serie; (b) serie + número; (c) esperar a edición | **(a) serie**, `entidad:"serie"`; el resto no tiene identidad suficiente (§2). |
| P2 | **Cardinalidad** | (a) una por (serie, fuente), varias fuentes; (b) una sola fuente | **(a)**: es lo que el modelo impone y lo que la persona espera de «también está en GCD». |
| P3 | **Relaciones heredadas** | (a) solo `metadata.vinculo` cuenta como confirmada; las heredadas quedan sin protección; (b) solo confirmadas con evidencia, pero **toda relación manual se protege** y se etiqueta sin comprobante | **(b)**: evita que el rescan pise trabajo humano y no finge una confirmación que no consta. |
| P4 | **Almacenamiento de la discrepancia** | (a) `File.metadata_["discrepancias"]` sin migración; (b) tabla nueva con migración (0023) y ADR | **(a) para BL-R4**; (b) si se necesitan vistas de biblioteca (BL-R7), después con la clave estable. |
| P5 | **Destino de «Revisar»** | (a) #129 A para serie y BL-R1/2d para publicación (y corregir el texto de #233); (b) esperar a #129 B; (c) dejar un aviso sin enlace | **(a)**; #233 no debe prometer una operación que no existe. |
| P6 | **Orden de entregas** | (a) A → #233 ∥ (B+B2); (b) A → B → #233; (c) todo junto | **(a)**: es lo que desbloquea #233 antes y no depende de la persistencia de B. |
| P7 | **Benchmark §13 de #129** | (a) hacerlo antes de implementar (Sonarr/Radarr/Kapowarr con varios ids y conflictos); (b) aceptar el patrón ya validado en CLAUDE.md §12 (columnas paralelas) sin ficha nueva | **(a)**, aunque sea ficha breve: #129 toca identidad y fuentes externas; el DoR la exige. **NOT RUN** aquí. |
| P8 | **B2 en el mismo release que B** | (a) sí; (b) B solo y B2 después | **(a)**: sin retirada, un error de B es permanente (mismo argumento que BL-R1). |
| P9 | **Evidencia heredada de «organizar»** | (a) no usarla; (b) considerar `asignacion_operaciones` como evidencia adicional | **(a) en v1**; (b) es una mejora futura que exige casar la operación con el `Issue` actual. |

### 6.2 Riesgos

| ID | Riesgo | Prob./impacto | Mitigación |
|---|---|---|---|
| R1 | El rescan actual pisa una relación confirmada | **Alta/alta** (código vigente) | D3 + guardián de escritura; regresión de mutación (AC-B4-2). |
| R2 | Proteger relaciones heredadas impide re-tríar un archivo sustituido | Media/media | La discrepancia explica el conflicto y la persona deshace/revincular explícitamente (BL-R1); no se pierde nada. |
| R3 | Crecimiento de `File.metadata_` con discrepancias | Baja/media | Lista acotada + archivado de resueltas/obsoletas; clave estable para migrar a tabla. |
| R4 | Ruido por claves inestables (cambios de título/año de la fuente) | Media/baja | La clave usa la afirmación de identidad, no la fecha ni el score; incluye los discriminantes que cambian la decisión; se documenta. |
| R5 | Sin usuario/auditoría no se sabe «quién» confirmó | Baja/baja | Decisión de producto: no se inventa; consta operación y fecha. |
| R6 | Dependencia circular #129 ↔ #233 | Media/media | Cortar en A (destino de «Revisar») y no esperar a B; D3/D4 independientes de #129 B. |
| R7 | Benchmark de #129 NOT RUN | Media/media | Ficha §13 antes de implementar A/B (P7). |
| R8 | Duplicación con #127/#128 | Baja/baja | Verificado: #128 no toca `File.issue_id`; #127 es solo lectura; #129/BL-R4 se apoyan, no duplican. |
| R9 | Coste en la Pi por consultas/escrituras nuevas | Media/media | Una consulta por acción en A; escrituras acotadas a una fila en B; discrepancia solo en re-triaje/actualización, sin N+1; medir en Pi antes de fusionar (NOT RUN). |
| R10 | «Mantener lo mío» se interpreta como silencio permanente | Media/media | Texto + historial + nueva clave reaparece; prueba AC-B4-4. |

### 6.3 Bloqueos para pasar #233 a «Lista para desarrollar»

1. **D3-B4 y D4-B4 ratificados** (§5) y P3/P4/P5 decididos.
2. **#129 A** refinada con este documento y con su ficha §13 (P7); su pantalla es el destino de
   «Revisar». Hasta entonces, #233 puede refinarse y escribir sus pruebas, pero no cerrar su DoR.
3. **BL-R1** ya está hecha (verificado); #128 y #127 también.
4. Sin migración si se acepta P4(a); si el PO elige tabla, migración y ADR aparte.

---

## 7. Pruebas futuras y límites NOT RUN

### 7.1 Pruebas por criterio (definidas; no implementadas)

| Entrega / criterio | Prueba futura |
|---|---|
| A · fuente única y estados | `tests/test_asociar_fuente.py` con dobles de clientes y estados de #133; sin red. |
| A · candidatas, discriminantes, sin preselección | `tests/test_web_asociar_fuente.py` (TestClient + FakeSession): HTML, sin token en resultados, «no consta». |
| A · cero efectos y token | `tests/test_tokens_asociar.py` (firma, propósito, contexto, caducidad, manipulación) + contador de sentencias/escrituras. |
| B · confirmación feliz y efectos exactos | `tests/test_asociar_fuente_pg.py` (PostgreSQL real): columna + `metadata.asociaciones` + comprobante; nada más; `updated_at` solo por `onupdate`. |
| B · idempotencia, conflicto, huella, resultado incierto | `tests/test_asociar_fuente_pg.py`: repetir token, id en otra serie, otro id misma fuente, ficha cambiada, fallo tras commit. |
| B2 · retirada e historial | `tests/test_retirar_asociacion_pg.py`: quita solo esa columna, historial, otras fuentes intactas, idempotencia. |
| D3 · relación confirmada | `tests/test_relacion_confirmada.py` (puro): matriz de evidencias (vinculo válido/incoherente, manual sin comprobante, automática, sin relación). |
| D3 · no pisar confirmadas | `tests/test_rescan_protege_confirmada_pg.py`: re-triaje con otra publicación y con ninguna; mutación del guardián; `issue_id` intacto. |
| D4 · discrepancia y ciclo de vida | `tests/test_discrepancias_pg.py`: detectar, deduplicar por clave, mantener, nueva clave, resolver, obsoleta, tope/archivado. |
| D4 · «Mantener lo mío» idempotente y no silencia | `tests/test_web_discrepancias.py` + PG: repetido, simultáneo, comprobante, texto en llano, otra propuesta reaparece. |
| BL-R4 · UI en ficha | `tests/test_web_series.py` y composición HTMX de `tests/test_web_nombre_y_foco.py` (lista de archivos por número ya existe, BL-R1b). |
| BL-R4 · sin efectos en archivos | Prueba de mutación: 0 `Path`/hash/renombrado; solo `files.metadata` y comprobante. |

### 7.2 NOT RUN (no medido, no inferido)

- **Benchmark §13 de #129** (varios ids por entidad, conflictos) y de #233: no ejecutado; el de BL-R0
  existe y no se rehace aquí.
- **Fuentes reales:** no se ha consultado ninguna; no se sabe qué devuelven hoy para cada serie ni si
  Tebeosfera/GCD aportan los discriminantes que la UI mostrará.
- **Pruebas:** no se ejecutó la suite; las citas de pruebas existentes son lectura.
- **Navegador, accesibilidad y Pi:** no se abrió la app, no se midió memoria/latencia; el coste de
  §6 R9 es una estimación de diseño.
- **Datos reales:** no se ha contado cuántas relaciones tienen `metadata.vinculo` ni cuántas son
  manuales heredadas; la forma se afirma por el código, no por un recuento nuevo.
- **Decisiones del PO:** P1–P9 y D3/D4 no están ratificados. Este documento **no** autoriza código,
  migraciones, fuentes reales ni despliegue, y **no** mueve el tablero.

---

## 8. Trazabilidad y caducidad

- **#129 → este documento:** troceo A/B del issue → §3 y §4; criterios 1–11 → AC-A/B/B2 (§4);
  decisiones bloqueantes del issue (entidad, cardinalidad, procedencia, corrección, vigencia,
  contraste) → §2, §3, §4 y §5.1; frontera con #128 → §1.3; dependencia de #133/#134 → §1.2/§4.4.
- **#233 → este documento:** criterios 1 (D3) → §5.1; 2 (nunca la cambia una fuente) → §5.1 y
  AC-B4-2; 3 (discrepancia visible) → §5.2; 4 (dos salidas) → §5.2; 5 (sin efectos en archivos) →
  AC-B4-6; 6 (pruebas) → §7.1.
- **Borrador previo:** `especificacion-M6-US03-asociar-fuente.md` (commit `703f266`, ya en `main` por
  el PR #535) queda como inventario y detalle de contrato de A/B; **sus D1–D6 no son las D3/D4 de
  BL-R4** y su SHA (`04ab6ee`) es anterior al de este contraste. Si el PO prefiere conservar un solo
  documento, se puede sustituir por este y enlazar el borrador como anexo histórico.
- **Caducidad:** revisar cuando cambie el contrato de #128/#233, cuando se decida el modelo de
  edición (#184) o si `main` avanza (re-ejecutar las citas). Fecha de este documento: 2026-11-09;
  contraste `5f27b3e`.

---

## 9. Implementación de BL-R4 (2026-11-09, #233)

Se implementan D3-B4 y D4-B4 **sin migración y sin tocar archivos**:

| Pieza | Dónde | Contrato |
|---|---|---|
| Predicado D3 puro | `src/zascarr/services/relacion_confirmada.py` | `estado_de_relacion(file, issue)` → `sin_relacion`/`confirmada`/`manual_sin_comprobante`/`automatica`; `es_protegida`; `vinculo_valido` exige UUID de operación, serie del `Issue`, `version` entera y `fecha` ISO; `relacion_actual` devuelve `{issue_id, serie_id, operacion_id}` sin ruta ni usuario |
| Guardián del rescan | `services/library_adopter.py::_re_triar_cambio` | Una relación protegida **no cambia ni vacía** `issue_id`; actualiza stat/hash/metadatos no relacionales y registra la discrepancia (incluida «ninguna publicación»). `metadata_source` y `metadata.vinculo` se conservan. Solo esta vía automática hoy; el helper es reutilizable |
| Discrepancia D4 | `services/discrepancias.py` | `File.metadata_["discrepancias"]` (lista versionada; tope 20 activas, archivo de 50). `clave = sha256` del JSON canónico de `{origen, fuente, id_externo, serie_destino_id, issue_destino_uuid, numero, formato, titulo_norm, anio}`; **sin** fecha/score/ruta/nombre. Dedupe por clave; ciclo `pendiente → mantenida/resuelta/obsoleta`; `origen` cerrado (`rescan`, `comicinfo`, `importador`, `fuente:*`). Sin usuario/IP/token |
| «Mantener lo mío» | `services/discrepancias.py::mantener_lo_mio` + `services/tokens_revision.py` | Token nuevo `mantener_lo_mio`, contexto `file_id`, caducidad 15 min; actualiza **esa** clave a `mantenida` con `mantenida_en`/`operacion_id` e inserta el comprobante inmutable `vinculacion_operaciones` (`resultado.tipo="mantener_lo_mio"`, purga 24 h). Idempotente; no cambia la publicación ni silencia la fuente |
| UI | `web/series.py`, `templates/series_detail.html`, `_discrepancias_serie.html`, `mantener_discrepancia.html`, `web.css` | Aviso «una actualización propone otra publicación; no se ha aplicado», qué propone vs qué se confirmó, «Mantener lo mío» (confirmación aparte con token) y «Revisar» (publicación → deshacer BL-R1; serie → `/ui/series/{id}/asociar` de #129 A). `no-store`; sin JS propio |

Pruebas: `tests/test_relacion_confirmada.py` y `tests/test_discrepancias.py` (puros), `tests/test_rescan_relacion_confirmada_pg.py` (Postgres: confirmada, manual sin comprobante, automática, ninguna publicación, dedupe, mutación e idempotencia) y `tests/test_web_discrepancias.py` (ficha, confirmación y token). **PASS** en estas suites; **NOT RUN** en navegador real y en la Pi (esta entrega no consulta fuentes ni usa ficheros reales de biblioteca), como en el resto de #129. El marcado `obsoleta`/`resuelta` por cambio de relación se aplica al volver a re-triar el archivo; una entrada de una relación que ya no coincide no se muestra en la ficha (`pendientes` exige la relación actual).

Cierre de QA/SecOps (#545): `metadata.vinculo.version` es una **lista cerrada** (`VERSIONES_CONOCIDAS = {1}`) —una versión futura no se interpreta como confirmación—. Rescan, «Mantener lo mío», tagger y asignación manual comparten un advisory lock por `File.id` (`utils/bloqueo_archivo.py`); rescan y «Mantener» lo toman en su transacción y releen la fila, y el tagger lo toma en la **transacción de su sesión** (vive hasta el commit del lote) y, ya con los dos locks (metadata y CBZ), **relee File/Issue/Series/Publisher y reconstruye `ctx`/`path`** antes de escribir (antes usaba objetos cargados fuera del lock y soltaba el advisory antes del commit). El lock del CBZ del tagger usa un espacio de clave distinto para no esperar su propia otra conexión. Tagger y rescan ordenan **globalmente por `File.id`** los ficheros cuyo lock piden (el tagger ya no usa `imported_at`): con locks retenidos hasta el commit, dos procesos multi-fichero podían tomar A/B en órdenes opuestos y bloquearse mutuamente. Nota fuera de alcance: `services/vinculacion.py` y `services/desvinculacion.py` todavía no comparten este lock con rescan/tagger; SecOps lo considera no bloqueante para #545 y queda anotado. El rescan relee con `with_for_update`; la comparación de serie propuesta vs. actual se hace como cadena (UUID y `str` no son iguales en Jinja); la clave de una discrepancia se valida (64 hex) y se URL-encodea; y `discrepancias_registradas` solo cuenta una entrada nueva o un cambio de relación, no una mera re-observación. Pruebas nuevas de concurrencia en `tests/test_concurrencia_escritores_pg.py` (tagger↔mantener, tagger↔rescan y mutación sin lock).
