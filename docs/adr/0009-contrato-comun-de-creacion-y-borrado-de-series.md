# ADR 0009: Contrato común de creación y borrado de series (refinamiento de #113)

- Estado: **Propuesto** · 2026-10-11 (documento pendiente de revisión; **no hay nada adoptado por este ADR hasta que se apruebe** y, aun así, **no se implementa** aquí)
- SHA de `main` revisado: [`1b107b2d`](https://github.com/juanajok/zascarr/tree/1b107b2d039cee9d4a4502bb288d212056535b0a) (`main` tras la fusión de #165)
- Relacionado: [#113](https://github.com/juanajok/zascarr/issues/113) (MIT-M1-US02, *Centralizar decisiones de dominio*), [#114](https://github.com/juanajok/zascarr/issues/114), ADR-0007 (vincular en su sitio), ADR-0008 (catalogación explícita), `docs/design/inventario-entradas-heredadas-y-alias-2026-10-09.md` (§2 y §6), `docs/design/rebanada-2-elegir-serie-y-vincular.md` (bloque B), CLAUDE.md §3.1.1

## Qué está decidido, qué es papel y qué falta

| Plano | Estado |
|---|---|
| **Decisiones previas que este documento da por vigentes** | Las de ADR-0007 y ADR-0008 (vincular ≠ organizar; la creación desde Descubrir se adapta al contrato del alta). No se reabren |
| **Contrato común propuesto (G1–G8)** | **Propuesta**: pendiente de revisión; no adoptada |
| **Salvaguardas del borrado** | **Opciones abiertas** (§Opciones). No se elige ninguna |
| **Implementación** | **Pendiente en todos los casos.** Ningún comportamiento cambia con este ADR: ni código, ni pruebas, ni contrato vigente |

**Leyenda de evidencia** (la misma que el inventario): **L** comprobado por lectura de código · **P** prueba identificada, **no ejecutada** en este refinamiento · **I** informe previo (referencia) · **X** ejecutado en esta revisión · **N** no verificado. En este refinamiento **no se ha ejecutado nada** salvo una consulta de metadatos del esquema ORM (las claves foráneas, 6.2) y lecturas de código y de GitHub.

## Contexto

La historia de #113 es: *«quiero obtener garantías iguales desde UI y API, para no depender del punto de entrada»*. Sus tres criterios de aceptación son: (1) dados los mismos datos, UI y API **delegan en el mismo servicio**; (2) un archivo adoptado vinculado desde cualquier entrada **conserva nombre y ruta**; (3) una colisión que llega por otra entrada **no elude la comprobación de dominio**.

El inventario fusionado en #165 muestra que **hoy hay tres caminos que crean una serie y un camino que la borra**, con garantías muy distintas, y que dos de ellos **no pasan por un servicio** aunque CLAUDE.md §3.1.1 lo exige («la capa services es la única fuente de verdad del negocio; los routers son finos»). Este ADR **no cambia nada**: documenta el estado, propone un contrato común y deja las decisiones abiertas a revisión.

## Estado actual (SHA `1b107b2d`)

### Los tres caminos que crean una serie (L, salvo donde se indica)

| Garantía | **C4** — alta por token (`POST /api/revision/serie/previsualizar` + `/serie`) | **C1** — `POST /ui/descubrir/crear` | **C3** — `POST /api/series` |
|---|---|---|---|
| Delegación | `AltaDeSerie` (`services/alta_serie.py`) | `DiscoveryService.get_or_create_series` (`services/discovery.py`), llamado desde `web/discovery.py` | **Ninguna**: `Series(**data.model_dump())` dentro del propio router (`api/series.py`) |
| Qué decide los datos | Un **token firmado** de la vista previa (la confirmación recibe solo el token) | **Campos ocultos del formulario** (`source`, `external_id`, `title`, `start_year`, `description`, `cover_url`) + el `select` de tradición | El cuerpo JSON, con esquema Pydantic explícito `SeriesCreate` (`extra="forbid"`) |
| Vista previa y confirmación | **Sí**: previsualizar sin escribir; confirmar con lo visto | **No**: un clic crea | **No** |
| Tradición | **Se elige**, sin valor por defecto | Preseleccionada con la suposición de la fuente (`tradition_guess`) en un `select` | **Valor por defecto `american`** si no se indica |
| Colisiones | Identificador externo exacto (la única coincidencia automática, **revalidada** al confirmar) y **parecidas** (título normalizado igual, año ±1, misma tradición) que decide la persona; al confirmar se rechaza si han aparecido otras que no vio | **Solo** por identificador externo: si existe, **reutiliza la fila sin avisar** (`creada=False`). No mira el título | **Ninguna.** El título no es único (solo lo son los identificadores externos), así que se pueden crear duplicados |
| Concurrencia | Candados consultivos (`alta_op:`, `alta_serie:`) y comprobación dentro de la transacción | Sin candados; la unicidad del identificador la impone la BD. **Cómo responde ante dos peticiones simultáneas: N** (el router solo captura `ValueError`) | Sin candados |
| Procedencia | `Series.metadata_["alta"]` versionada (con `operacion_id`); `metadata_source` = la fuente o `'manual'`; el campo del id externo en `locked_fields` | `metadata_source` = la fuente. **Sin** `locked_fields` ni `metadata_["alta"]` | `metadata_source` **nulo** (no `'manual'`): una fila que, por las reglas del enriquecedor, **puede completar el enriquecedor** |
| Idempotencia y comprobante | Operación con UUID y comprobante persistente `alta_operaciones`; repetir devuelve lo mismo; tras deshacer, `409 alta_deshecha` | Ninguno (la reutilización por id actúa como idempotencia parcial) | Ninguno |
| Reversibilidad | `POST /api/revision/serie/{id}/deshacer` mientras nada dependa de la serie | Ninguna | Ninguna (existe `DELETE`, ver abajo) |
| Límites | ≤ 100 parecidas firmadas; token con máximo calculado (#138) | Política H1 sobre `cover_url` | Política H1 sobre `cover_url`; `status` por defecto `ongoing` |
| Efectos laterales | Solo una fila de `series` (no números, archivos, búsquedas ni enriquecimientos) | Una fila de `series`, con título/descripción/portada que vienen del cliente | Una fila de `series` |
| Evidencia | I: #97, #138 · P: `alta_serie_pg`, `tokens_limites*` | P: `web_discovery`, `test_discovery_service` | P: `api_series` |

**Constructores de `Series(...)` en `src/`:** tres, en tres módulos (`services/alta_serie.py`, `services/discovery.py`, `api/series.py`) (L, búsqueda textual).

### El borrado: `DELETE /api/series/{id}` (L)

`delete_series` (en `api/series.py`, **sin servicio**) hace `db.delete(series)` y `flush`. **No hay ruta de interfaz** que lo llame (el barrido de rutas del inventario no halla ningún `DELETE` en `web/`). No tiene confirmación, ni vista previa de efectos, ni comprobante.

Efecto en la BD, por las claves foráneas del esquema (consulta de metadatos del ORM, **X**; la BD real las crea con Alembic, **N**: no se ha comparado con una base migrada):

| Tabla | Columna | Regla al borrar la serie |
|---|---|---|
| `issues` | `series_id` | **CASCADE** (se borran todos sus números) |
| `wishlist` | `series_id` | **CASCADE** |
| `local_aliases` | `series_id` | **CASCADE** (los alias aprendidos de esa serie) |
| `series_genres` | `series_id` | **CASCADE** |
| `asignacion_operaciones` | `series_id` | `SET NULL`, **pero** el `CHECK ck_asignacion_viva_con_referencias` impide el borrado si hay una operación **viva** → el endpoint lo traduce a `409` |
| Por el borrado de `issues`: `issue_characters`, `issue_creators`, `issue_tags`, `reading_list_items`, `reading_progress`, `story_arc_issues`, `wishlist` | `issue_id` | **CASCADE** |
| **`files`** | `issue_id` | **`SET NULL`**: los archivos **quedan sin vincular** |

**Consecuencias, separando lo leído de lo no ejecutado:**
- **Los archivos no se tocan en el disco** (el borrado solo opera sobre la BD; el módulo no mueve ni borra ficheros): nombre y ruta se conservan (L).
- **Desvincula sin avisar**: la persona no ve cuántos números, archivos, deseados ni alias se pierden. El único freno es la operación viva (`409`).
- **Hipótesis derivadas, no ejecutadas (N):** (a) los archivos desvinculados vuelven a cumplir `issue_id IS NULL` y no descartado, el predicado con el que la superficie de revisión selecciona lo pendiente (`services/revision_carpetas.py`), así que **reaparecerían como pendientes**; (b) conservarían `metadata_source = 'manual'` y `metadata["vinculo"]` con la serie ya borrada (procedencia obsoleta); (c) un comprobante de alta o un informe de vinculación **no tienen clave foránea** a `series`, así que sobreviven con el id de una serie inexistente; repetir un token de alta tras un borrado ajeno da `alta_serie_ausente` (409), no la recrea (el docstring de `AltaSerieAusenteError` lo dice).
- **Pruebas existentes (P):** `asignacion_integracion_pg` cubre `409` con una operación viva, `204` con la operación cerrada y que **otro** error de integridad no se disfraza de 409. **No se localizó ninguna prueba que fije la cascada de números ni la desvinculación de archivos** (N).

**Un cuarto hueco, registrado y no resuelto:** `PATCH /api/series/{id}` (`update_series`, también en el router) puede **cambiar el título, la tradición, los años y la política de búsqueda** sin ninguna comprobación de colisión: renombrar una serie a un título ya existente evita la detección de parecidas.

## Contrato común propuesto

### Decisiones previas (vigentes; no son nuevas)
- **D1.** Vincular en su sitio y organizar son operaciones distintas (ADR-0007).
- **D2.** La creación desde Descubrir se adapta al contrato del alta, con vista previa y confirmación (ADR-0008, apartado 2).
- **D3.** Las propiedades del alta C4 ya vigentes (la tradición se elige; el identificador externo exacto es la única coincidencia automática; lo que se ejecuta es lo que se vio) **no cambian**.

### Propuesta: garantías que debe tener **cualquier** camino que cree una serie (G1–G8)
*(Pendiente de revisión; no adoptadas.)*

| | Garantía | Hoy C4 / C1 / C3 |
|---|---|---|
| **G1** | **Decisión explícita sobre lo visto**: vista previa y confirmación con exactamente lo previsualizado | sí / no / no |
| **G2** | **Tradición elegida**, sin valor por defecto | sí / preselección / valor por defecto |
| **G3** | **Detección de colisiones**: identificador exacto (automática, revalidada) y parecidas (decididas por la persona, acotadas) | sí / solo identificador / no |
| **G4** | **Serialización de peticiones concurrentes** sobre la misma identidad o título | sí / no (N) / no |
| **G5** | **Procedencia versionada e identidad protegida** (`metadata_source`, `locked_fields`, `metadata_["alta"]`) | sí / parcial / no (nulo) |
| **G6** | **Idempotencia y comprobante persistente** | sí / no / no |
| **G7** | **Reversibilidad acotada** mientras nada dependa de la serie | sí / no / no |
| **G8** | **Sin efectos laterales**: ni archivos, ni números, ni búsquedas ni enriquecimientos | sí / sí / sí |

**Criterio de cumplimiento propuesto:** una entrada del recorrido MVP solo puede **crear** una serie si delega en el servicio que ofrece G1–G8 (hoy, `AltaDeSerie`). Lo que no delega **se adapta o se excluye** del recorrido; no se duplica la lógica en un router.

## Opciones abiertas (no se decide ninguna aquí)

### O-A. Cómo adaptar C1 (`POST /ui/descubrir/crear`)
La adaptación está decidida (D2); queda **abierta la forma**: (a) encadenar previsualizar y confirmar en dos pasos en la propia tarjeta de Descubrir; (b) mostrar la vista previa en línea con el botón de confirmar en la misma pantalla. Ambas conservan G1–G8; cambia la interfaz, que es de 2e/#114.

### O-B. Qué hacer con C3 (`POST /api/series`)
| Opción | Efecto | Coste / riesgo |
|---|---|---|
| **B1** Adaptarlo a `AltaDeSerie` (alta manual) | Todas las entradas comparten G1–G8 | Cambia el contrato de la API (hoy un solo paso, esquema distinto) |
| **B2** Excluirlo del recorrido MVP y documentarlo como API programática **sin** G1–G8 | No cambia nada; la brecha queda declarada | Sigue permitiendo duplicados y series enriquecibles |
| **B3** Retirarlo | Elimina la brecha | **No recomendable sin inventariar consumidores externos** (scripts, `curl`): no se ha comprobado (N) |

### O-C. Salvaguardas del borrado (`DELETE /api/series/{id}`)
| Opción | Qué haría | Coste / riesgo | Cómo se probaría |
|---|---|---|---|
| **S1** Vista previa de efectos + confirmación firmada | Muestra cuántos números, archivos, deseados y alias se pierden y exige un token (patrón de #97/#103) | Un paso más; reutiliza un patrón existente | Cascada contada = cascada real; repetir = mismo resultado |
| **S2** Bloquear si tiene archivos vinculados (`409 tiene_archivos`, como `deshacer`) | Solo se borran series **vacías**; desvincular sería otra operación explícita (que **no existe**) | Obliga a crear «desvincular» para el otro caso | Con archivos → 409 y nada cambia; sin archivos → borra |
| **S3** Excluirlo del recorrido MVP | Lo deja como operación de administración documentada | No arregla el efecto; solo lo aparta | — |
| **S4** Sustituirlo por «deshacer» (solo series creadas por una operación) | Reutiliza el contrato existente | **Pierde** el borrado de las series que no vienen del alta | — |
| **S5** Borrado lógico / archivado | Reversible | **Cambia el modelo** (migración): fuera del alcance del MVP | — |

Cualquier opción **conserva** el `409` por operación viva (ya probado). Combinaciones razonables: S1+S2, S2+S3, S4+S3.

### O-D. `PATCH /api/series/{id}` y las colisiones
(a) aplicar la detección de parecidas al cambiar título/tradición/año; (b) tratarlo como parte de C3 (misma decisión que B1/B2); (c) documentarlo como brecha.

## Criterios de aceptación refinados para #113 (propuestos)

Sustituirían a los tres actuales **sin cambiar su intención**; la correspondencia es A1←1, A5←2, A2←3.

- **A1. Delegación.** Cada entrada del recorrido MVP que cree una serie delega en `AltaDeSerie`; ninguna construye `Series(...)` directamente. *Evidencia futura:* una prueba por entrada que sustituya el servicio y compruebe que se invoca con los mismos datos, y una regresión que fije el número de constructores de `Series(` fuera del servicio (hoy: dos).
- **A2. Colisión.** Dados el mismo título normalizado, tradición y año, la detección es la misma desde cualquier entrada; **ninguna elude** la comprobación de identificador exacto ni de parecidas.
- **A3. Garantías por entrada.** Una tabla de cumplimiento G1–G8 por entrada, con la evidencia de cada celda (L / P / I / X / N), revisada antes de aceptar.
- **A4. Borrado.** Según la opción elegida en O-C: el efecto del borrado es **visible antes de ejecutarse** (S1) o **imposible con archivos vinculados** (S2) o **excluido del recorrido** (S3/S4), y en cualquier caso el borrado **no toca el disco**, conserva el `409` por operación viva y deja documentado qué ocurre con los archivos, los alias y los comprobantes.
- **A5. Vincular.** Cualquier entrada del recorrido que vincule **conserva nombre y ruta**. Hoy el único camino que vincula en sitio es `POST /api/revision/vinculacion`; la asignación heredada **mueve** y se trata en #114.
- **A6. Trazabilidad.** Cada decisión adoptada enlaza su evidencia; lo que queda abierto está listado.

## Pruebas: existentes, huecos y futuras

| | Detalle |
|---|---|
| **Existentes (P, no ejecutadas aquí)** | C4: `alta_serie_pg`, `tokens_limites*`. C1: `web_discovery`, `test_discovery_service`. C3: `api_series`. Borrado: `asignacion_integracion_pg` (409 / 204 / otro error de integridad). Vincular conserva rutas: `vinculacion_pg`, `vinculacion_limite_pg` |
| **Huecos (N)** | Ninguna prueba **compara C1, C3 y C4** entre sí. Sin prueba de la **cascada** del borrado ni de que los archivos quedan sin vincular **y el disco intacto**. Sin prueba de **concurrencia** de C1 (dos peticiones con el mismo id) ni de C3 con título duplicado. `PATCH` sin prueba de colisión |
| **Futuras (no autorizadas)** | Paridad de colisión entre entradas; delegación por entrada (A1); la «ceremonia» del borrado según la opción elegida; regresión «desvincular no toca el disco» |

## Trazado a #114

| Se decide aquí (#113) | Queda para #114 |
|---|---|
| El **contrato** común (G1–G8) y las **opciones** de C1, C3, borrado y `PATCH` | **Adaptar o retirar** los caminos: aplicar la opción elegida a C1/C3/`DELETE`/`PATCH` |
| Que la creación **delega** en un único servicio | **Sustituir** `POST /ui/pendientes/{id}/asignar` por vincular en el recorrido normal y **rotular «Organizar»** lo que mueve (criterio 2 de #112) |
| Qué prueba acredita la delegación | **Implementar** esas pruebas y los cambios |

## Alternativas consideradas
- **Un servicio común** (propuesto) frente a **normas por router**: lo segundo duplica lógica, es lo que hoy produce la brecha y contradice CLAUDE.md §3.1.1.
- **Elevar C3 y C1 al nivel del alta** frente a **degradar el alta a su nivel**: lo segundo perdería G1–G8, que existen y están probadas.

## Consecuencias
- Con el contrato adoptado e implementado, la UI y la API darían **garantías iguales** al crear series y se reduciría el riesgo de series duplicadas o enriquecibles sin querer.
- El coste es de **interfaz y de contrato de API** (C1 y C3 dejarían de ser «un clic»); por eso se separa en #114 y no se implementa aquí.
- El borrado tiene hoy un efecto **destructivo de catálogo sin aviso**; hasta que se decida una opción, sigue como está y **queda documentado**.

## Dependencias y exclusiones
- **Depende de:** ADR-0007, ADR-0008, #165 (inventario). **Desbloquea:** el refinamiento de #114.
- **No autoriza ni describe como hecho:** código, pruebas, migraciones, cambios de contrato, 2e, fuentes reales, despliegue, ni cambios en el tablero más allá de los estados de #113.
- **No cierra #113:** una PR documental no acredita por sí sola la centralización real de UI y API. Al fusionarse, quedan **adoptadas** las decisiones previas (D1–D3, ya vigentes), **abiertas** O-A, O-B, O-C y O-D, y **pendiente de implementación** todo el contrato G1–G8.
