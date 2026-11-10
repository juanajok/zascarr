# Especificación — MIT-M7-US03: Revisar y retirar decisiones reutilizables (#132)

> **Estado:** propuesta de refinamiento para el PO. **No implementa código, no crea migraciones, no
> ejecuta pruebas y no toca archivos ni series.** Las citas de código se contrastan en `origin/main`
> **`52933d3`** (2026-11-10; worktree `.squad/wt-132-spec`), con #130 y #131 ya fusionadas.
> **Alcance:** #132 (US03) y lo que las decisiones P1-P10 de #110 dejan para esta entrega; no se
> implementan #130/#131 ni se reabren sus criterios.
> **Decide el PO.** Lo que es decisión de modelo se marca **PO**; lo demás es contrato.

---

## 0. Resumen para el PO

Hoy hay **cuatro tipos de cosas reutilizables** y ninguna pantalla única para revisarlas:

1. **Declaraciones de carpeta** (#130): tabla `declaraciones_carpeta`, servicio
   `services/declaraciones_carpeta.py`, pantalla «Contexto declarado»; versionadas, con estados y
   origen local/importación. Ya se pueden crear, cambiar, desactivar, reactivar y retirar.
2. **Correspondencias** (#131): tabla `correspondencias_contexto`, servicio
   `services/correspondencias_contexto.py`, evaluación con seis estados; **no hay rutas ni plantillas
   implementadas**: la UI «Correspondencias» existe solo como diseño
   (`docs/design/ui-MIT-M7-correspondencia.md`).
3. **Alias aprendido B13** (`local_aliases`): `pattern_norm → series_id` global, aprendido
   automáticamente, **sin estado, versión, origen visible ni UI**. `SeriesMatcher` y el orquestador
   lo usan sin preguntar; el importador puede mover archivos por él.
4. **Alias de importación**: **no existe** como entidad. P9 lo ratifica como pieza propia de #132,
   con estado y subordinado a la declaración local.

**Lo que se propone:**

- **Tabla nueva `alias_importado`** (versionada por filas) para las sugerencias importadas, y
  **ciclo de vida en `LocalAlias`** (estado `propuesto/activo/desactivado/retirado`, versión e
  historial), sin convertirlo en declaración ni en correspondencia.
- **Consentimiento explícito** para el alias aprendido: los nuevos nacen `propuesto`; los existentes
  se migran **`propuesto`** (recomendado) para que no sigan aplicándose por inferencia. La persona los
  activa de uno en uno desde el inventario.
- **Inventario único** «Decisiones reutilizables» que reúne declaraciones, correspondencias, alias
  aprendidos y alias importados, con tipo, origen, estado, alcance, versión, efectos previstos,
  conflictos y acciones de ciclo de vida. **No crea, no vincula, no mueve, no borra archivos.**
- **Precedencia explícita:** declaración/correspondencia local > alias de importación > alias
  aprendido. No se elige sola; los conflictos se muestran y se resuelven con acciones explícitas.
- **Nada retroactivo:** desactivar o retirar no reasigna, revierte ni mueve decisiones ya confirmadas.

**Corte:** #132-a (modelo, migración y servicios), #132-b (inventario/UI y pruebas), #132-c opcional
(consumo del alias importado en el matcher). Orden: #130 → #131 → #132; #130 y #131 ya están.

---

## 1. Contraste real: qué hay y qué falta

### 1.1 Lo reutilizable que existe hoy

| Pieza | Estado en `52933d3` | Qué ofrece | Qué falta para #132 |
|---|---|---|---|
| **Declaración de carpeta** | Fusionada (#130) | Modelo `models/__init__.py:954-996`; servicio `services/declaraciones_carpeta.py` (`declarar`, `cambiar`, `desactivar`, `reactivar`, `retirar`, `listar` `:289`, `historial` `:314`); UI `web/contexto_declarado.py:92-300` y plantillas `contexto_declarado.html`, `declarar_carpeta.html`, `cambiar_declaracion.html`, `retirar_declaracion.html` | Inventario conjunto; no hay que reinventar su ciclo, solo reutilizarlo |
| **Correspondencia** | Servicio fusionado (#131); **UI no implementada** | Modelo `models/__init__.py:998-1048`; servicio `services/correspondencias_contexto.py` (`crear`, `cambiar`, `desactivar`, `activar`, `retirar`, `listar` `:358`, `historial` `:379`, `evaluar` `:410`); diseño UX en `docs/design/ui-MIT-M7-correspondencia.md` | Rutas/plantillas de lista y acciones; el inventario de #132 debe cubrirlas o enlazarlas |
| **Alias aprendido B13** | Fusionado, sin ciclo | `LocalAlias`: `models/__init__.py:1050-1066` (`pattern_norm` único global → `series_id`, `created_at`); aprendizaje `services/review.py:327-349` y `services/asignacion.py:590-591`; lectura `core/matcher.py:216-235,313-318` y `services/orchestrator.py:323-334,585-637` | Estado, versión, historial, origen, UI, consentimiento, filtros en consumidores |
| **Alias de importación** | **No existe** | — | Tabla, ciclo, estado, precedencia, UI |
| **Inventario único** | **No existe** | — | Servicio de lectura conjunto, filtros, acciones, historial |
| **Contexto #286** | Documento `contexto-286.md` | Contexto de navegación (URL de vuelta), no semántico | No se mezcla con #132 |
| **Asociación #129** | Fusionada | Identidad externa serie ↔ fuente | No es una decisión local de contexto; no se mezcla |

### 1.2 Cómo funciona hoy, y por qué no basta

- **Declaraciones:** ya versionadas por filas, con `version`, `vigente_hasta`, estados y origen; la
  UI lista las vigentes por estado. La lista **no** incluye alias ni correspondencias; `listar` no
  filtra por carpeta ni ofrece una vista conjunta (`services/declaraciones_carpeta.py:289-312`).
- **Correspondencias:** el servicio está completo, pero **no hay `web/correspondencias.py` ni
  plantilla**; `docs/design/ui-MIT-M7-correspondencia.md` es solo diseño. La evaluación de #131
  (`services/correspondencias_contexto.py:410-580`) **no lee alias**: no hay conflicto
  correspondencia↔alias en el motor; #132 debe mostrarlo en el inventario, no inventarlo en la UI.
- **Alias aprendido:** `SeriesMatcher.find_alias` consulta `local_aliases` con SQL directo
  (`core/matcher.py:216-235`), devuelve `DIRECT`, y `decide` corta antes del fuzzy
  (`:313-318`); el importador puede mover el archivo. El orquestador usa los alias de la serie para
  aceptar candidatos (`services/orchestrator.py:323-334`, `:585-637`). **No hay estado**: un alias
  aprendido se aplica siempre, y `_learn_alias` **sobrescribe** el anterior
  (`services/review.py:327-349`). No hay pantalla, endpoint ni servicio de listado/gestión.
- **Alias de importación:** no hay tabla, enum, servicio ni origen `importado` en `local_aliases`;
  no se puede distinguir de una sugerencia externa. P9 lo deja para #132.
- **Inventario:** no hay servicio que una las cuatro fuentes; la UI «Contexto declarado» solo lee
  `declaraciones_carpeta`. No hay filtros por tipo/origen/estado/carpeta ni vista de historial
  conjunto.

### 1.3 Lo que no se toca

- `declaraciones_carpeta` y `correspondencias_contexto` no cambian de esquema en #132 (salvo que el
  PO pida un índice nuevo; no es necesario para el inventario).
- `metadata_source`, `locked_fields`, `files`, `series`, `issues`, `asignacion_operaciones` y
  `vinculacion_operaciones` no se modifican.
- El motor de evaluación de #131 no cambia su contrato de seis estados. #132 añade inventario y
  ciclo de alias; si el inventario muestra un conflicto con una correspondencia, lo hace con datos
  de lectura, sin convertirlo en un séptimo estado.
- La UI de #130 se conserva; el inventario enlaza con ella y no duplica sus formularios.

---

## 2. Modelo de #132

### 2.1 Decisión: `LocalAlias` se amplía; el alias importado es una tabla nueva

| Pieza | Decisión | Por qué |
|---|---|---|
| **Alias aprendido** | Se **amplía** `local_aliases` (misma tabla, sin duplicar) | Ya tiene identidad `pattern_norm` y dos consumidores; crear otra tabla para lo mismo rompería la fuente única |
| **Alias de importación** | **Tabla nueva `alias_importado`**, versionada por filas | P9 lo ratifica; tiene ámbito/evidencia/estado propios y no debe competir con el `pattern_norm` único de B13 |
| **Declaraciones/correspondencias** | No se tocan | Ya están versionadas y con ciclo; #132 las lee |

**No se reutilizan `origen_regla` ni `estado_regla` para alias.** `origen_regla` solo distingue
`local`/`importacion`, y un alias necesita `aprendido`/`importado`/`manual`; `estado_regla` no tiene
`propuesto`, que es el estado de consentimiento. Se añaden dos enums propios:

```text
origen_alias:  aprendido | importado | manual
estado_alias:  propuesto | activo | desactivado | retirado
```

- `propuesto`: aprendido/importado, **no se aplica**; espera consentimiento.
- `activo`: consentido; puede aplicarse a **nuevas** evaluaciones según su tipo.
- `desactivado`: no se aplica; reactivable.
- `retirado`: terminal; no se reactiva; historial conservado.

`estado_regla` se queda para declaraciones/correspondencias; no se contamina con `propuesto`.

### 2.2 `LocalAlias` ampliado (B13)

Columnas nuevas (la tabla y su `pattern_norm` único se conservan):

| Columna | Tipo | Regla |
|---|---|---|
| `origen` | `origen_alias NOT NULL DEFAULT 'aprendido'` | B13 es aprendido; `manual` se reserva para una creación explícita futura; no se escribe `importado` aquí |
| `estado` | `estado_alias NOT NULL` | Migración: **`propuesto`** (recomendado) o `activo` (alternativa PO) |
| `version` | `integer NOT NULL DEFAULT 1` | Incrementa con cambio de estado/contenido; no con un evento de conflicto sin cambio |
| `scope_path` | `text NULL` | `NULL` = global (B13); se reserva para un alias acotado futuro; no editable en #132 |
| `historial` | `jsonb NOT NULL DEFAULT '[]'` | Append-only de instantáneas; nunca se borra desde la UI |
| `actualizado_en` | `timestamptz NOT NULL` | `created_at` existente se conserva |

- **Sin `vigente_hasta`:** no se convierten las filas de B13 en versiones; el motivo es que
  `pattern_norm` es único y los dos consumidores hacen SQL directo. La historia va en `historial`
  (JSONB) y la versión en `version`; es un **historial de estados/contenido**, no una tabla de
  versiones. Si el PO prefiere filas versionadas, es una migración mayor (§7, P-B).
- **`historial`** guarda, por evento:
  ```json
  {"version": 1, "estado": "propuesto", "origen": "aprendido",
   "series_id": "…", "scope_path": null,
   "fecha": "2026-11-10T20:00:00+00:00",
   "motivo": "aprendizaje|migracion|activacion|desactivacion|retirada|conflicto",
   "operacion_id": "…"}
  ```
  La entrada inicial la escribe la migración; cada cambio de estado/contenido añade una. Un
  **conflicto de aprendizaje** (misma pauta, otra serie) añade un evento `conflicto` con la serie
  propuesta, sin cambiar el estado vigente.
- **`pattern_norm` y `series_id`:** el patrón es la identidad; no se edita desde la UI. Cambiar de
  serie es un nuevo aprendizaje (estado `propuesto`) o una propuesta en conflicto; nunca un
  `UPDATE` silencioso de un alias activo.
- **Un solo alias por patrón:** se mantiene `UNIQUE(pattern_norm)`. Una propuesta en conflicto se
  registra en `historial`, no como segunda fila; la UI la muestra como conflicto y no la activa sola.
- **Filtro en consumidores:** `SeriesMatcher.find_alias` y el orquestador pasan a exigir
  `estado='activo'`; `_learn_alias` deja de crear alias activos y crea `propuesto`. Sin ese filtro,
  los alias migrados a `propuesto` seguirían aplicándose y AC6/AC8 serían falsos.

### 2.3 `alias_importado` (tabla nueva)

Versionada por filas, como #130/#131:

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `uuid PK` | Fila/versión |
| `alias_id` | `uuid NOT NULL` | Identidad estable |
| `version` | `integer NOT NULL` | 1..n |
| `patron_norm` | `text NOT NULL` | Patrón normalizado; `normalize_title` para nombres de archivo |
| `scope_path` | `text NULL` | Ruta relativa normalizada; `NULL` = global; subordinado a la declaración local que cubra |
| `series_id` | `uuid NOT NULL REFERENCES series(id) ON DELETE CASCADE` | Destino existente; no se crea |
| `origen` | `origen_alias NOT NULL DEFAULT 'importado'` | Siempre `importado` en esta tabla |
| `estado` | `estado_alias NOT NULL` | `propuesto|activo|desactivado|retirado` |
| `vigente_desde` / `vigente_hasta` | `timestamptz` | Cierre de versión |
| `procedencia` | `jsonb NOT NULL DEFAULT '{}'` | Evidencia de la importación; sin secretos |
| `creado_en` | `timestamptz NOT NULL` | — |

- **Unicidad:** `UNIQUE(alias_id, version)`, parcial `UNIQUE(alias_id) WHERE vigente_hasta IS NULL`,
  parcial `UNIQUE(patron_norm, COALESCE(scope_path, '')) WHERE vigente_hasta IS NULL AND
  estado='activo'` (no dos activos iguales); índices por `patron_norm`, `scope_path`, `estado`.
- **No hay creación desde #132:** la tabla la llena una importación explícita (futura o migración);
  #132 solo lista, activa, desactiva y retira. Si no hay importador, la tabla queda vacía y el
  inventario lo dice; no se inventan filas.
- **Subordinado a la declaración local:** un alias importado no produce ni cambia declaraciones ni
  correspondencias; la declaración local que cubre su `scope_path` gana. `scope_path=NULL` es global
  pero sigue por debajo de una declaración local.
- **Sin consumidor en #132 por defecto:** el alias importado activo queda **disponible** para una
  integración posterior (matcher/evaluación); en #132 su efecto es de inventario/evidencia, no de
  ejecución. La alternativa (integrarlo ya) es un corte aparte (§7, P-C).

### 2.4 Migración

Una migración aditiva, después de `0025` (número propuesto `0026`):

1. Crear enums `origen_alias` y `estado_alias` con `postgresql.ENUM` explícito y
   `values_callable` minúsculas (regla del proyecto).
2. `ALTER TABLE local_aliases ADD COLUMN` `origen`, `estado`, `version`, `scope_path`, `historial`,
   `actualizado_en`; backfill:
   - `version=1`, `origen='aprendido'`, `scope_path=NULL`;
   - `historial` con la instantánea inicial;
   - `estado` **`propuesto`** (recomendado) o `activo` (P-A).
3. Crear `alias_importado` con sus índices.
4. No se borra ni se reescribe ninguna fila existente; `pattern_norm` sigue único.
5. `downgrade` elimina la tabla nueva, los enums y las columnas añadidas; **no** debe inventar ni
   borrar alias al bajar (la columna `historial` se va con la migración; se documenta).

**Datos existentes:** la migración no decide por la persona qué alias merece confianza; la decisión
de estado inicial es la P-A. No se ejecuta en producción desde esta spec.

---

## 3. Precedencia y conflictos (P9, AC9 de #130/AC7 de #131)

### 3.1 Orden explícito

| Orden | Capa | Qué puede hacer | Límite |
|---:|---|---|---|
| 1 | **Declaración/correspondencia local activa** | Orientar y preparar propuestas de contexto | No vincula, no crea, no mueve; no sobrescribe alias |
| 2 | **Alias de importación activo** (`alias_importado`) | Evidencia/sugerencia subordinada; no pisa la local | No crea ni modifica reglas locales; no produce propuesta de contexto por sí solo en #132 |
| 3 | **Alias aprendido activo** (`LocalAlias`) | Reutiliza una corrección manual para nuevas evaluaciones del matcher | No pisa local/importado; no amplía alcance; no aplica si está propuesto/desactivado/retirado |

**Regla de oro:** la precedencia **no autoriza a ejecutar**. Declaraciones/correspondencias solo
preparan propuestas; el alias aprendido activo, tras consentimiento, conserva el comportamiento
actual del matcher solo para material nuevo, nunca para lo ya decidido.

### 3.2 Conflictos visibles, sin elección automática

| Caso | Qué muestra el inventario | Qué **no** hace |
|---|---|---|
| Declaración local + alias importado en la misma carpeta | Dos filas con origen distinto y chip «Conflicto visible»; la local tiene prioridad | No borra, no desactiva ni activa el alias |
| Declaración local + alias aprendido | Alias marcado «en conflicto con una decisión local»; no se aplica a esa carpeta | No cambia el alias ni la declaración |
| Correspondencia local + alias | Alias «en conflicto»; la correspondencia es la que prepara propuesta | No convierte el alias en correspondencia |
| Dos alias importados activos con el mismo patrón/alcance y series distintas | Conflicto de alias; se listan los dos; no se elige | No fusiona ni ordena por fecha |
| Alias importado + alias aprendido activos | Importado gana en la tabla de precedencia; se muestra el conflicto | No borra el aprendido; el usuario decide con acciones |
| Varias correspondencias locales con destinos distintos | Estado de #131 `conflicto_de_correspondencias` (ya existe) | No añade una precedencia nueva |

- **Resolver es explícito:** desactivar/retirar el alias que no se quiere, o crear/cambiar la regla
  local. La UI del inventario **no** ofrece radios ni «elegir esta»; solo las acciones de ciclo.
- La precedencia se muestra como texto y como orden de filas; no depende solo del color.
- **No se extiende por parecido:** ni por nombre, ni por ruta vecina, ni por destino parecido.

### 3.3 Relación con el motor de #131 y con el matcher

- La evaluación de #131 sigue devolviendo sus seis estados y **no** se modifica para incluir alias.
  Si un alias contradice una propuesta, el inventario lo muestra como conflicto; el motor no elige
  por el alias.
- #132 **no** crea un séptimo estado ni reescribe la propuesta; lee reglas y alias por separado.
- `SeriesMatcher` se toca para **filtrar `estado='activo'`** de `LocalAlias` (sin eso, un alias
  `propuesto` migrado seguiría aplicándose) y, en el corte de integración 132-c, para **respetar la
  precedencia**: si una declaración/correspondencia local cubre la carpeta del archivo, el alias no
  se aplica y el inventario lo muestra como conflicto. Un alias no se convierte en `DIRECT` si la
  decisión local lo contradice.
- El orquestador aplica el mismo filtro y la misma precedencia cuando usa alias para aceptar
  candidatos (`services/orchestrator.py:323-334,585-637`); si se deja para 132-c, el inventario lo
  declara como pendiente y no se promete el efecto.
- `AliasImportado` no tiene consumidor en #132 (P-C): su estado se administra, pero no se presenta
  como aplicado al matcher.

---

## 4. Consentimiento del alias automático (AC6)

### 4.1 Flujo de activación

1. El alias nace/queda en `propuesto` (nuevo aprendizaje) o la migración lo deja `propuesto`.
2. En el inventario aparece en «Pendientes de activar», con patrón, serie destino, origen,
   evidencia/fecha y efectos previstos.
3. La acción **«Activar»** abre una pantalla de confirmación explícita:
   - H1 «Activar alias»;
   - entrada «Este alias se usará en nuevas interpretaciones; no cambia lo ya decidido.»;
   - resumen (patrón → serie, origen, alcance global);
   - botón principal «Sí, activar este alias» y neutro «Cancelar».
4. Al confirmar: `estado=activo`, `version+1`, evento `activacion` en `historial`; **no** se crea ni
   se vincula nada; no se activa ningún otro alias.
5. Un alias `desactivado` puede reactivarse con la misma confirmación; uno `retirado` **no**.
6. **Nadie más lo activa:** guardar una declaración/correspondencia, confirmar una vinculación,
   aceptar un alta o ejecutar cualquier otra acción **no** activa un alias (AC6). Tampoco se activa
   por coincidencia de nombre, por frecuencia de uso ni por aparecer en el inventario.
7. **No hay activación masiva** en v1; cada alias exige su propia confirmación (AC6/AC8). Si el PO
   quiere un «activar seleccionados», debe ser una acción explícita, con lista visible y confirmación
   propia; no se propone.

### 4.2 Qué pasa con los alias ya aprendidos (migración): decisión PO

Hoy B13 está activo por definición: `find_alias` no filtra estado y `_learn_alias` escribe sin
consentimiento. La migración tiene dos opciones:

| Opción | Efecto inmediato | Ventaja | Coste/riesgo |
|---|---|---|---|
| **A. Migrar a `propuesto` (recomendado)** | Ningún alias aprendido se aplica hasta que la persona lo active; el matcher filtra `activo` | Cumple AC6/AC8 y el objetivo «sin aprendizaje invisible»; no hay ejecución heredada sin consentimiento | Cambia el comportamiento actual: importaciones que antes movían por alias quedan en revisión hasta activar; hay que avisar en la UI y en las notas de versión |
| B. Migrar a `activo` (heredado) | Los alias existentes siguen aplicándose | Cero regresión en el flujo actual | No cumple AC6 al pie de la letra: un alias aprendido por inferencia sigue activo sin consentimiento; habría que marcarlo «heredado» y pedir confirmación aparte |

**Recomendación:** **A**, con una nota visible «Los alias aprendidos antes de esta versión quedan
pendientes de activar» y sin activación automática. Si el PO prioriza compatibilidad, B queda como
decisión explícita y el inventario debe mostrar «Activo heredado» con la misma posibilidad de
desactivar/retirar. **No se mezcla:** no se migran unos activos y otros pendientes sin criterio.

### 4.3 Aprendizaje futuro

- `_learn_alias` (`services/review.py:327-349`) deja de crear/actualizar un alias **activo**:
  - si no existe alias para el patrón: crea `propuesto` v1 con historial;
  - si existe un alias activo con la **misma** serie: no hace nada;
  - si existe un alias activo con **otra** serie: no lo pisa; añade un evento `conflicto` con la
    serie propuesta y la UI lo muestra; activar esa propuesta es una acción explícita (nueva
    versión de estado/contenido), no un efecto del aprendizaje;
  - si existe `propuesto`/`desactivado`: actualiza la serie, incrementa versión, deja `propuesto`
    (nunca activa);
  - si existe `retirado`: una **nueva** asignación manual no reactiva el alias retirado, pero puede
    dejar una propuesta nueva en la misma fila (`estado='propuesto'`, `version+1`, evento
    `reactivacion_por_aprendizaje`); no se aplica hasta que la persona la active. El retiro anterior
    queda en `historial` y no se borra.
- `AsignacionService` sigue llamando a `_learn_alias` cuando `aprender_alias=True`
  (`services/asignacion.py:590-591`); el cambio es que el resultado es una propuesta, no una regla
  activa.
- **Conflicto con una serie distinta:** el alias activo no se pisa. Si la persona quiere el nuevo
  destino, desactiva/retira el alias actual y una nueva asignación deja la propuesta; el evento de
  conflicto queda visible en el historial mientras tanto. No hay acción «aplicar propuesta de
  conflicto» sin pasar por ese ciclo explícito.
- **Quién activa:** la persona, desde el inventario, de uno en uno. No hay usuario/autenticación
  adicional: ZascArr es de un solo operador; el historial guarda fecha y `operacion_id`, no una
  identidad de persona.

---

## 5. Inventario (AC1, AC2, AC3, AC4, AC5, AC7)

### 5.1 Piezas y fuente

Nuevo servicio de **solo lectura** `services/decisiones_reutilizables.py` (nombre propuesto) que une:

| Tipo de fila | Fuente | Reutiliza |
|---|---|---|
| Declaración de carpeta | `declaraciones_carpeta` vigente | `services/declaraciones_carpeta.listar` (`:289`), `historial` (`:314`) |
| Correspondencia | `correspondencias_contexto` vigente | `services/correspondencias_contexto.listar` (`:358`), `historial` (`:379`), `evaluar` (`:410`) |
| Alias aprendido | `local_aliases` ampliado | Consulta nueva por estado/origen/patrón |
| Alias importado | `alias_importado` | Consulta nueva; no hay importador en #132 |

- **Sin N+1:** cuatro consultas acotadas (una por tipo) y, si hace falta, una de destinos en bloque;
  no se consulta serie por fila ni se evalúa cada fila con una consulta extra.
- **Solo lectura** para listar/filtrar; las acciones llaman a los servicios de ciclo existentes o a
  los nuevos de alias. No hay `UPDATE` en el listado.

### 5.2 Qué muestra cada fila

| Campo | Declaración | Correspondencia | Alias aprendido | Alias importado |
|---|---|---|---|---|
| **Tipo** | «Declaración de carpeta» | «Correspondencia» | «Alias aprendido» | «Alias importado» |
| **Origen** | «Local» / «Importación» | «Local» / «Importación» | «Aprendido» (o «Manual») | «Importación» |
| **Estado** | Activa/Desactivada/Retirada | Activa/Desactivada/Retirada | Propuesto/Activo/Desactivado/Retirado | Propuesto/Activo/Desactivado/Retirado |
| **Alcance** | `contexto_raiz` + «solo esta carpeta» / «y subcarpetas» | Heredado de la declaración + `tipo_de_registro` | «Global (sin carpeta)» | `scope_path` + subcarpetas, o «Global» |
| **Versión** | `version` | `version_de_regla` | `version` | `version` |
| **Destino** | — | serie/publicación | serie | serie |
| **Efectos previstos** | «Solo orienta; no crea ni vincula; no cambia lo ya decidido.» | «Solo prepara propuestas; no vincula ni aplica metadatos.» | «Se aplica a nuevas interpretaciones del matcher, si no lo bloquea una decisión local; no cambia lo ya decidido.» (activo) / «No se aplica hasta que lo actives.» (propuesto) / «No se aplica.» (desactivado/retirado) | «Sugerencia importada; subordinada a la declaración local. No se aplica automáticamente en esta entrega.» |
| **Conflicto / precedencia** | Chip «Conflicto visible» + alternativas | Chip + reglas | «En conflicto con una decisión local» o «En conflicto con un alias importado» | «Subordinado a la decisión local» |
| **Historial** | Enlace a versiones | Enlace a versiones | Enlace a `historial` JSONB | Enlace a versiones |

- **No se muestran ids internos** en la superficie; para las trazas de correspondencia se mantiene
  la excepción ya pactada en 131-b (`correspondencia_id`/`version_de_regla` dentro de un
  `<details>`).
- **No se muestra «procedencia desconocida»** como si fuera una decisión: se dice «Origen no
  registrado» cuando el alias/legado no tiene historial, sin inventarlo.
- **El estado vacío** explica qué es una decisión reutilizable y que no se ha configurado ninguna.

### 5.3 Filtros

- **Tipo:** todas / declaraciones / correspondencias / alias aprendidos / alias importados.
- **Estado:** todas / activas / desactivadas / retiradas / pendientes de activar.
- **Origen:** todos / local / importación / aprendido.
- **Carpeta:** texto que contiene, comparado sin mayúsculas ni tildes (mismo criterio que el filtro
  de #397); un valor inválido no rompe: 200 con aviso.
- **«Incluir historial»** (checkbox): añade versiones cerradas; por defecto solo vigentes. En alias
  aprendido, el historial es el JSONB; en importado, las versiones.
- Filtros combinables; recuento por sección; sin paginación compleja (nº de filas pequeño); si crece,
  se acota por `LIMITE_MAXIMO`.

### 5.4 Acciones por fila

| Tipo | Acciones |
|---|---|
| Declaración local | «Cambiar» (formulario existente), «Desactivar», «Reactivar», «Retirar» (confirmación); las mismas de #130 |
| Declaración de importación | **Solo lectura** en #132 (se muestra; no se cambia ni se retira desde aquí) — P-D |
| Correspondencia local | «Desactivar», «Reactivar», «Retirar»; «Cambiar» cuando exista UI de #131-b; sin crear destino |
| Correspondencia de importación | Solo lectura (P-D) |
| Alias aprendido | «Activar» (confirmación), «Desactivar», «Reactivar», «Retirar»; **no** se edita patrón/serie |
| Alias importado | «Activar» (confirmación), «Desactivar», «Reactivar», «Retirar»; no se crea desde aquí |
| Cualquiera retirado | Sin acciones; historial visible |

- **Retirar** pide confirmación y dice que el historial se conserva y que no se mueve/borra nada;
  **desactivar** es reversible y no borra; **reactivar** no se ofrece para retirados.
- **No hay «borrar»** en la UI; no hay acción para fusionar alias ni para resolver conflictos
  automáticamente.
- Las acciones de varias filas son neutras; no se añade un botón principal al listado.

### 5.5 Pantalla y rutas

- Nueva pantalla **«Decisiones reutilizables»** (H1, 2 palabras) bajo
  `/ui/pendientes/carpetas/decisiones` o `/ui/decisiones-reutilizables`; el sitio definitivo lo fija
  la implementación, pero debe ser enlazable desde «Contexto declarado» y «Correspondencias».
- Entrada: «Consulta y administra lo que ZascArr reutiliza en nuevas interpretaciones.» (10 palabras).
- Línea de efectos: «Desactivar o retirar no deshace nada ya decidido; no mueve archivos.».
- Lista agrupada por estado o por tipo, con filtros; no tabla de seis columnas a 320 px: tarjetas
  con chips y acciones, como la UI de #130.
- Enlace «← Volver a «Contexto declarado»» y, si hay correspondencias implementadas, «← Volver a
  «Correspondencias»».
- **La UI no decide precedencias:** pinta la que devuelve el servicio; no reordena por origen ni
  resuelve conflictos.

---

## 6. AC ↔ contrato

### 6.1 Los 9 criterios de #132

| # | Criterio | Contrato | AC propuesta | PO |
|---|---|---|---|---|
| 1 | Inventario comprensible: tipo, origen, estado, alcance, efectos; decisión vs sugerencia | §5.2; cuatro tipos; chips de origen/estado; conflictos visibles | AC-132-1 | Acciones en importadas (P-D) |
| 2 | Alcance futuro explícito; no retroactivo | §5.2 `efectos`; §3.3/§5.4; el pasado no se toca | AC-132-2 | Consumo del alias importado (P-C) |
| 3 | Desactivación reversible; no es borrado | §2.2/§5.4; `desactivado` + historial; reactivar | AC-132-3 | — |
| 4 | Retirada sin efectos destructivos; historial | §2.2/§2.3/§5.4; `retirado` terminal; historial JSONB/versiones | AC-132-4 | — |
| 5 | Efectos previos preservados | §3.3/§5.4; no `UPDATE` de vínculos/series/archivos | AC-132-5 | — |
| 6 | Alias automático con consentimiento propio | §4; `propuesto` por defecto; activación individual; ninguna otra acción activa | AC-132-6 | Migración activa/heredada (P-A) |
| 7 | Conflicto con declaración local y precedencia | §3.1/§3.2; local > importado > aprendido; conflicto visible; sin elegir; **si el alias activo sigue en el matcher, AC7 exige 132-c** | AC-132-7 | Acciones en importadas (P-D); P-E |
| 8 | Activación sin inferencia; no activo no aplica | §4.1; filtros de estado en matcher; migración pendiente; sin activación por coincidencia | AC-132-8 | P-A, P-C |
| 9 | Evidencia verificable del ciclo | §7 pruebas: listado, desactivar, retirar, preservación, activación, conflicto, no consentimiento; PASS/FAIL/NOT RUN | AC-132-9 | — |

### 6.2 Coherencia con #130/#131

- #130 AC9 (conflictos) y #131 AC7 (sin precedencia implícita) se cumplen en el inventario: se
  muestran las alternativas y la precedencia contractual; no se elige sola.
- #131 AC6 (seis estados) no se modifica; el inventario no crea un séptimo estado.
- #130 AC6/#131 AC1 (local vs importación) se conservan: la importación es una fila distinta, no una
  decisión local; no se pisa.

---

## 7. Cortes, migración y pruebas

### 7.1 Cortes

| Corte | Contenido | Talla | Migración | Depende |
|---|---|---|---|---|
| **132-a** | Enums `origen_alias`/`estado_alias`; ampliación de `LocalAlias` (estado/versión/historial); tabla `alias_importado`; servicios de ciclo (activar/desactivar/retirar/listar/historial); filtro `activo` en matcher/orquestador; `_learn_alias` a `propuesto`; pruebas de modelo y migración | **M** | 0026 aditiva | #130/#131 |
| **132-b** | Inventario `decisiones_reutilizables.py` (cuatro fuentes, filtros, conflictos), pantalla «Decisiones reutilizables», enlaces desde Contexto declarado/Correspondencias, acciones y confirmaciones, historial, pruebas de UI/AC | **M** | — | 132-a |
| **132-c (condicional)** | Precedencia efectiva en matcher/orquestador (alias no pisa declaración/correspondencia local) y, si P-C, consumo del alias importado; pruebas de integración | **S/M** | — | 132-a + decisión P-C/P-E |

- **#132 total M/L** (dos M y un opcional S/M), no L si P-C se deja fuera. El estimado original
  M/5 no incluía el consumo del alias importado; se advierte.
- **Orden:** #130 → #131 → #132. #130 y #131 ya están fusionadas; 131-b (UI de correspondencias) es
  el único hueco visible y #132-b puede cubrir la lista/acciones de administración sin duplicar el
  formulario de creación, que sigue en 131-b.
- **Migración 0026** aditiva; no reescribe filas; `local_aliases` conserva `pattern_norm` único y sus
  datos. El `downgrade` elimina columnas/tabla/enums; documenta que el historial de alias se pierde
  al bajar (no se inventa).

### 7.2 Pruebas obligatorias (definidas, no ejecutadas)

**Modelo/migración**
1. Migración en una BD de prueba con `local_aliases` existentes: filas conservadas, `version=1`,
   historial inicial, estado según P-A; ninguna fila duplicada.
2. `alias_importado`: versión única por `alias_id`, una vigente por alias, un activo por
   `(patron_norm, scope_path)`; no se crea desde la UI.
3. Enums explícitos y `values_callable` en minúsculas; `downgrade` coherente.

**Consentimiento/estado**
4. Alias nuevo de `_learn_alias` nace `propuesto`; no se aplica en matcher/orquestador.
5. Alias `propuesto` → activar con confirmación → `activo`, versión+1, historial; no activa otros.
6. Alias `activo` → desactivar → no aplica; reactivar → aplica; retirar → terminal; repetir retirada
   no duplica; retirado no reactiva.
7. Aprender sobre alias activo con otra serie no lo pisa: evento de conflicto, estado intacto.
8. Migración P-A: ningún alias antiguo se aplica hasta activar (o, si P-A=B, sigue activo y se
   prueba el aviso).

**Inventario**
9. Lista los cuatro tipos con tipo/origen/estado/alcance/versión/efectos; no muestra ids internos.
10. Filtros tipo/estado/origen/carpeta; valor inválido no rompe; «incluir historial» añade cerradas.
11. Dos fuentes/reglas en conflicto se muestran, no se elige; local > importado > aprendido.
12. Declaración/correspondencia importada se muestra solo lectura (P-D).
13. Alias importado activo aparece como subordinado; no pisa local.
14. Acciones de una fila no cambian otras ni tocan series/archivos; retirar no borra historial.
15. Pantalla 320 px, teclado, foco y textos; 14 px; sin botón principal en la lista; PASS/FAIL/NOT
    RUN separados.

**Integración (si P-C)** 16. Alias importado activo se usa como evidencia en nuevas evaluaciones
dentro de su `scope_path`; local gana; conflicto visible; sin efecto retrospectivo.

---

## 8. Decisiones que necesita el PO

| ID | Decisión | Recomendación | Alternativa y consecuencia |
|---|---|---|---|
| **P-A** | Migración de los alias aprendidos existentes: `propuesto` o `activo` heredado | **`propuesto`** (sin consentimiento no se aplican; cumple AC6/AC8) | `activo` heredado conserva el flujo actual pero un alias inferido sigue ejecutando sin consentimiento; exige aviso y prueba |
| **P-B** | Versionado de `LocalAlias`: `version` + `historial` JSONB o filas versionadas | **JSONB + versión** (M; no cambia `pattern_norm` único ni los dos consumidores) | Filas versionadas dan historial relacional pero exigen migrar la clave, el matcher y el orquestador; sube a L |
| **P-C** | ¿El alias importado se consume en #132 o solo se administra? | **Solo administración en #132** (P9; su consumo es 132-c opcional) | Consumirlo ya exige tocar matcher/evaluador y precedencia; suma S/M y pruebas de integración |
| **P-D** | ¿Se pueden desactivar/retirar declaraciones y correspondencias de origen importación desde el inventario? | **Solo lectura** en #132 (la importación pertenece a su origen) | Permitir acciones exige distinguir origen y actualizar el importador; contradice la UI de #130 que ya las muestra sin gestionar |
| **P-E** | ¿Un alias aprendido activo sigue alimentando el matcher como hoy, o solo es evidencia? | **Sigue alimentando el matcher tras consentimiento** (compatibilidad; AC8 habla de “nuevas evaluaciones”) | “Solo evidencia” exige cambiar `decide` (alias no `DIRECT`) y es un corte de comportamiento aparte; benchmark lo sugiere pero no está en #132 |
| **P-F** | ¿Activación masiva? | **No**: una confirmación por alias (AC6) | Un “activar seleccionados” exige lista, confirmación y pruebas propias; no se propone |
| **P-G** | ¿Alias importado global (`scope_path=NULL`) o solo con ámbito? | **Permitir global**, siempre por debajo de la declaración local | Exigir ámbito simplifica la precedencia pero deja fuera alias importados sin carpeta |

Sin P-A/P-B/P-C/P-D resueltas, #132 no está Ready. P-E/P-F/P-G pueden resolverse al implementar
132-b/132-c, pero deben quedar escritas antes de tocar el matcher o la UI.

---

## 9. Efectos y no-efectos

### 9.1 Qué hace cada operación

| Operación | Escribe | No escribe |
|---|---|---|
| Listar/filtrar inventario | Nada | Nada |
| Activar/desactivar/retirar alias | `local_aliases` (estado/versión/historial) o `alias_importado` (nueva versión) | Series, issues, archivos, metadata, declaraciones/correspondencias |
| Activar/desactivar/retirar declaración/correspondencia | Su tabla versionada (servicios #130/#131) | Series, issues, archivos, alias |
| Confirmar activación de alias | Estado/versión/historial; consentimiento | Ninguna creación/vinculación |
| Aplicar matcher (fuera de #132) | Archivo nuevo según flujo existente | Nada retroactivo |
| Retirar | Estado terminal + historial | Nada de lo ya confirmado |

### 9.2 No-efectos explícitos

- No se mueve, renombra, copia ni borra ningún archivo.
- No se crea ninguna serie, publicación ni destino.
- No se vincula ningún archivo; no se aplica `metadata_source`/`locked_fields`/metadatos.
- No se reasigna ni revierte ningún vínculo, asignación o serie ya confirmada.
- No se toca B13 desde una declaración/correspondencia, ni al revés.
- No se aprende por inferencia ni se activa un alias por coincidencia de nombre/título.
- No se consultan fuentes reales ni red; el inventario es local.
- No se borra historial; retirar conserva.

---

## 10. Riesgos y privacidad

| ID | Riesgo | Mitigación |
|---|---|---|
| R-01 | Migrar alias a `propuesto` cambia el flujo de importación (menos movimientos automáticos) | Aviso de versión; activación por alias; prueba de que no se aplica hasta activar; P-A |
| R-02 | Un alias activo sigue moviendo archivos nuevos y se percibe como «sistema que decide» | Consentimiento explícito; efectos previstos en la fila; no aplica a lo ya decidido; P-E |
| R-03 | Alias importado sin consumidor parece «activado pero inerte» | Texto de efectos claro y P-C; estado no promete ejecución |
| R-04 | `historial` JSONB crece o se corrompe | Append-only validado; lectura tolerante; sin borrado; pocas filas |
| R-05 | Inventario con muchas filas/N+1 | Cuatro consultas acotadas; índices por estado/origen/patrón; sin consulta por fila |
| R-06 | Conflictos resueltos por la UI por accidente | Servicio devuelve precedencia/alternativas; UI solo pinta; pruebas |
| R-07 | Migración deja alias activos por error | Test de migración; P-A explícita; no auto-activar |
| R-08 | Diferencia entre UI de correspondencias y servicio | 132-b reutiliza `listar`/`historial`; no segundo modelo |
| R-09 | Privacidad de rutas/patrones | Sin logs de rutas/patrones; inventario solo para la persona local; sin datos personales |
| R-10 | Borrado de serie elimina alias por CASCADE | Declarado: el alias hacia una serie borrada desaparece; la UI lo trata como no disponible; no se inventa historial |

**Privacidad:** no hay usuario, sesión, IP ni auditoría; el historial registra fechas y
`operacion_id`, no personas. Rutas y patrones no se envían a fuentes ni se registran en logs.
El inventario es local para el operador.

---

## 11. Referencias y NOT RUN

### 11.1 Documentos

| Documento | Uso |
|---|---|
| `docs/design/especificacion-MIT-M7-contexto-declarado.md` | Contrato de #130/#131 y P1-P10 |
| `docs/design/benchmark-MIT-M7-contexto-declarado.md` | Evidencia de referencias, alias como evidencia, lifecycle |
| `docs/design/ui-MIT-M7-declarar-carpeta.md` | UI de declaraciones implementada |
| `docs/design/ui-MIT-M7-correspondencia.md` | UI de correspondencias (diseño; no implementada) |
| `docs/design/inventario-entradas-heredadas-y-alias-2026-10-09.md` | B13: consumidores, ausencia de gestión |
| `docs/adr/0008-catalogacion-explicita-y-propuestas-sin-ejecucion-silenciosa.md` | Propuestas sin ejecución; alias no autoridad |
| `src/zascarr/LEGAL.md` | Sin datos personales ni redistribución |

### 11.2 NOT RUN

- **Código:** no se ha implementado nada de #132; esta spec no crea migraciones ni servicios.
- **Pruebas:** no ejecutadas; las de §7.2 están definidas.
- **Base de datos:** no se ha medido el inventario ni el historial; solo se proponen índices.
- **UI:** no existe pantalla de inventario; «Correspondencias» solo está diseñada, no implementada.
- **Consumo del alias importado:** no existe en #132 (P-C).
- **PO:** P-A/P-B/P-C/P-D/P-E/P-F/P-G pendientes.
- **SHA:** `52933d3`; si `main` avanza, re-ejecutar las citas.

---

## 12. Auto-revisión

- [x] Contraste real con `fichero:línea` de declaraciones, correspondencias, `LocalAlias` y huecos.
- [x] Confirmado: no hay tabla de alias importado, ni estado/versión/UI de `LocalAlias`, ni inventario;
      la UI de correspondencias no está implementada (solo diseño).
- [x] Modelo: `LocalAlias` ampliado (estado/versión/historial) y tabla nueva `alias_importado`;
      enums propios, no reutiliza `origen_regla`/`estado_regla`.
- [x] Consentimiento: `propuesto`, activación individual, migración de existentes decidida por PO;
      ninguna otra acción activa un alias.
- [x] Precedencia local > importado > aprendido; conflictos visibles; no elige sola.
- [x] Inventario: cuatro tipos, campos, filtros, acciones, historial; sin N+1 ni ids internos.
- [x] AC 9 mapeados; PO marcado; efectos y no-efectos.
- [x] Cortes 132-a/132-b/132-c y migración 0026; NOT RUN declarado.

### Registro de cambios

| Fecha | Versión | Cambio |
|---|---|---|
| 2026-11-10 | v1.0 | Primera especificación de #132 sobre #130/#131 fusionadas: contraste, modelo de alias y consentimiento, precedencia, inventario, AC y cortes. Sin código, sin migraciones aplicadas, sin pruebas. |
