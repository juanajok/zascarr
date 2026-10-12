# ADR 0010: Plan de adaptación y retirada de caminos heredados (refinamiento de #114)

- Estado: **Aceptado parcialmente** · 2026-10-12. Redactado como **Propuesto** el 2026-10-11 ([#167](https://github.com/juanajok/zascarr/pull/167)). **Solo está adoptado lo que figura en «Estado de adopción»**, con su implementación y prueba en `main`; el resto sigue **propuesto o abierto**.
- SHA de `main` revisado: [`9a396591`](https://github.com/juanajok/zascarr/tree/9a39659152a5399a926c6f9d6b2031f513100eca) (`main` tras la fusión de #166, ADR 0009). Entre `1b107b2d` (el SHA que revisó el ADR 0009) y `9a396591` **solo cambia el propio ADR 0009** (`git diff --stat 1b107b2d 9a396591`: un fichero, 157 líneas añadidas; nada en `src/`, `tests/` ni `scripts/`), así que las citas de código del ADR 0009 siguen vigentes **sin repetir su lectura**; en este refinamiento se han **releído** los caminos que aquí se proponen cambiar (L).
- Relacionado: [#114](https://github.com/juanajok/zascarr/issues/114) (MIT-M1-US03, *Adaptar o retirar caminos heredados*), [#113](https://github.com/juanajok/zascarr/issues/113) (MIT-M1-US02), [#104](https://github.com/juanajok/zascarr/issues/104) (Feature M1, *Operaciones coherentes*), [#105](https://github.com/juanajok/zascarr/issues/105) (Feature M2, *Confirmación robusta*), [#112](https://github.com/juanajok/zascarr/issues/112), [#118](https://github.com/juanajok/zascarr/issues/118); ADR-0007, ADR-0008, [ADR-0009](0009-contrato-comun-de-creacion-y-borrado-de-series.md); `docs/design/inventario-entradas-heredadas-y-alias-2026-10-09.md` (§2 y §6); CLAUDE.md §3.1.1 y §3.1.3

## Estado de adopción (2026-10-12)

> **Qué cambia con esta sección.** El resto del documento es la propuesta del 2026-10-11 y **se conserva sin reescribir**. Aquí se separa lo **adoptado** —con su evidencia— de lo **abierto**. Se adopta **solo lo ya implementado y probado en `main`**. Las decisiones de producto de fondo (C1 en dos pasos, `DELETE` S2 + S3, `PATCH` con `409` y `vistas`, C3 en dos fases, G1–G8 con excepciones, D1–D6) las comunicó la persona responsable y constan en un [comentario de #114](https://github.com/juanajok/zascarr/issues/114#issuecomment-6111681080).

**Evidencia:** `main` en `d062366e`; CI de `main` [38248822432](https://github.com/juanajok/zascarr/actions/runs/38248822432) (unitaria 3141 passed, Postgres real 964 passed, Docker y pip-audit correctos; ruff informativo, los mismos 178/11 que antes). **Nada está desplegado.**

### Propuestas: qué se adopta y con qué evidencia
| | Decisión | Estado | Evidencia |
|---|---|---|---|
| **F1** | `AltaDeSerie` no podía delegar sin grupo | **Resuelto** con una variante sin grupo (contexto firmado reservado, límites recalculados) | [#172](https://github.com/juanajok/zascarr/pull/172) (`e316ba12`) |
| **P-1** | C1 en dos pasos, sobre la variante sin grupo; firma al buscar; `/ui/descubrir/crear` solo acepta el token. **Se mantiene D2** (la alternativa estructural de crear solo desde un grupo, #118, **no se adopta**) | **Adoptada e implementada** | [#173](https://github.com/juanajok/zascarr/pull/173) (`8e14f182`) |
| **P-2** | C3 en dos fases | Fase 1 (obsoleto, sin cambio de comportamiento) **adoptada e implementada**: [#169](https://github.com/juanajok/zascarr/pull/169) (`62ba2bd5`). **Fase 2 (I6): abierta** | ver abajo |
| **P-3** | `DELETE` S2 + S3, con el `409` por operación viva **comprobado primero** (desviación del orden propuesto, para conservar su texto) | **Adoptada e implementada** | [#168](https://github.com/juanajok/zascarr/pull/168) (`f3b467b1`) |
| **P-4** | `PATCH` con `409 serie_parecida` y `vistas` | **Adoptada e implementada** (el servicio no confirma: la transacción es la de la petición) | [#170](https://github.com/juanajok/zascarr/pull/170) (`f19a8323`) |
| **P-5** | G1–G8 como principios con excepciones | **Adoptada solo donde el ADR 0009 enumera implementación y prueba por entrada** (tabla «Evidencia por garantía», **borrador informativo**); las celdas sin prueba específica no se adoptan | [#174](https://github.com/juanajok/zascarr/pull/174) (`d062366e`) |
| **P-6** | D1–D6 como criterios de #114 | **Adoptados**; acreditación parcial (abajo) | — |
| **P-7** | Rotular «Organizar» y, después, sustituir por «Vincular» | Rotulado **adoptado e implementado**: [#171](https://github.com/juanajok/zascarr/pull/171) (`a15a5cd2`). Sustitución (I7): **bloqueada por 2e** | — |

### I1–I8 (división de #114)
| | Cambio | Estado |
|---|---|---|
| I1 | Variante de `AltaDeSerie` sin grupo | **Fusionada** [#172](https://github.com/juanajok/zascarr/pull/172) (`e316ba12`) |
| I2 | C1 en dos pasos | **Fusionada** [#173](https://github.com/juanajok/zascarr/pull/173) (`8e14f182`) |
| I3 | C3 fase 1 | **Fusionada** [#169](https://github.com/juanajok/zascarr/pull/169) (`62ba2bd5`) |
| I4 | `DELETE` protegido | **Fusionada** [#168](https://github.com/juanajok/zascarr/pull/168) (`f3b467b1`) |
| I5 | `PATCH` con colisiones | **Fusionada** [#170](https://github.com/juanajok/zascarr/pull/170) (`f19a8323`) |
| I6 | C3 fase 2 (retirada) | **No autorizada** |
| I7 | Sustituir la asignación por «Vincular» | **Bloqueada por 2e** |
| I8 | Rotular «Organizar» | **Fusionada** [#171](https://github.com/juanajok/zascarr/pull/171) (`a15a5cd2`) |

### D1–D6: qué está acreditado
| | Estado |
|---|---|
| **D1** decisión por camino | C1, `DELETE`, `PATCH` y el rotulado: **sí**. C3: fase 1 sí, fase 2 abierta. Asignación que mueve: rotulada; sustitución abierta |
| **D2** contrato G1–G8 y excepciones | **Sí** (ADR 0009, «Estado de adopción») |
| **D3** borrado acotado | **Sí** ([#168](https://github.com/juanajok/zascarr/pull/168) (`f3b467b1`)) |
| **D4** compatibilidad y retirada documentadas | **Sí** para lo adoptado: el changelog recoge `DELETE` (I4), `PATCH`, Descubrir, «Organizar» y la obsolescencia de C3. La retirada de C3 (I6) queda como **excepción expresa**: su mecanismo y su periodo están descritos, pero **no se ejecutan** |
| **D5** pruebas de aceptación enumeradas | **Sí** para lo adoptado: delegación, paridad de colisiones, el borrado protegido (rechazo con dependientes y sin tocar el disco) y la concurrencia. Lo que dependa de I6 o de I7 queda como **excepción expresa**, **NOT RUN** |
| **D6** división en cambios | **Sí** (I1–I8) |

### Abierto, sin adoptar
- **I6 (retirada de `POST /api/series`)**: no autorizada. Condiciones: un ciclo de versión, comprobación de consumidores, y decidir antes el hueco de la API (crear una serie vacía sin carpeta).
- **I7**: depende de 2e (interfaz de vinculación), sin autorizar.
- **Peso real de página** de Descubrir con 40 resultados, **token caducado en htmx real**, otro navegador y escritorio ancho: **NOT RUN**.
- **Consumidores externos de `POST /api/series`**: **no verificables** (sin telemetría).
- Tallas de las historias: **sin calibrar**.

---

> **Texto original (propuesta del 2026-10-11).** Lo que sigue se conserva tal como se redactó.

## Qué está decidido, qué es papel y qué falta

| Plano | Estado |
|---|---|
| **Decisiones previas que este documento da por vigentes** | ADR-0007 (vincular ≠ organizar) y ADR-0008 (la creación desde Descubrir se adapta al contrato del alta; D2). **No se reabren.** Una de las propuestas de abajo (P-1) toca el *cómo* de D2 y lo señala como punto de decisión de la persona que revisa |
| **Diagnóstico del ADR 0009** | Adoptado como diagnóstico al fusionarse #166 (ver el comentario de reconciliación de #113). Aquí solo se **amplía** con un hallazgo (F1) y con el inventario de consumidores de `POST /api/series` |
| **Decisiones de este ADR (P-1 … P-7)** | **Propuestas**, cada una con su alternativa y su consecuencia. Ninguna está adoptada |
| **Criterios de aceptación D1–D6 de #114** | **Propuestos**; no sustituyen aún a los de la tarjeta |
| **Implementación** | **Pendiente en todos los casos.** Ningún comportamiento cambia con este ADR: ni código, ni pruebas, ni contrato vigente |

**Leyenda de evidencia** (la del inventario y el ADR 0009): **L** comprobado por lectura de código · **P** prueba identificada, **no ejecutada** en este refinamiento · **I** informe previo (referencia) · **X** ejecutado en esta revisión · **N** no verificado. **En este refinamiento no se ha ejecutado nada** (ni la aplicación, ni las pruebas del repositorio, ni operaciones sobre una base de datos): solo lecturas de código, de pruebas, de documentos, del historial de `git` y de GitHub. Toda hipótesis lleva **N**.

## Contexto

#114 dice: *«como administrador, quiero retirar entradas incompatibles con el contrato, para mantener un sistema comprensible»*, con tres criterios: (1) una ruta antigua que se adapta deja **documentada** la compatibilidad o la sustitución; (2) un cambio de delegación se prueba con **regresiones y paridad**; (3) un camino que queda fuera tiene su **limitación explícita**. Está estimada en 8 puntos / L con confianza **baja** (estimación inicial, no calibrada).

El ADR 0009 dejó abiertas cuatro opciones (O-A … O-D), propuso las garantías G1–G8 y los criterios A1–A6, y trazó a #114 **la aplicación** de lo que se elija. Este ADR convierte esas opciones en **una propuesta concreta por camino**, y la parte en cambios implementables. **No implementa nada.**

## Hallazgo nuevo (F1): `AltaDeSerie` está acoplado a un grupo de carpeta, y C1 y C3 no tienen ninguno

Al preparar la delegación de C1 y C3 en `AltaDeSerie` (la premisa de D2 y de G1–G8) se ha leído su contrato de entrada, y **no es utilizable tal cual** por esos dos caminos (L):

| Dónde | Qué exige | Efecto sobre C1/C3 |
|---|---|---|
| `AltaDeSerie.previsualizar(clave, …)` (`services/alta_serie.py`) | `clave` obligatoria: si `RevisionCarpetas.archivos_del_grupo(clave)` no existe, lanza `GrupoNoEncontradoError` (404 «No hay registros pendientes en esa carpeta») | Descubrir libre y la API no parten de ninguna carpeta |
| Tokens de candidata y de alta (`tokens_revision.py`) | El **contexto** firmado es la `clave` del grupo: un token no sirve sobre otra carpeta | No hay contexto que firmar sin grupo |
| Procedencia `metadata_["alta"]` | Guarda `desde_grupo: alta.clave` | Sin grupo no hay valor que guardar |
| Límites calculados (#138) | `MAX_TOKEN_CANDIDATA` 20 313 y `MAX_TOKEN_ALTA` 25 681 se computan con una `clave` de **hasta 1000 caracteres** | Un contexto fijo y corto cambia el cálculo: hay que **recalcularlo y probarlo**, no heredarlo |

Consecuencia: «delegar en `AltaDeSerie`» **no es una sustitución de llamada**. Exige una **variante sin grupo** del servicio (un origen distinto, con un contexto firmado fijo y sin `desde_grupo`), con sus límites recalculados. Ese trabajo (cambio **I1** del plan) no estaba dimensionado en el ADR 0008 ni en la estimación de #114, y es la razón principal de que la tarjeta siga siendo grande. **N:** no se ha prototipado la variante; el coste real es una hipótesis.

## Estado actual por camino (de ADR 0009, SHA `9a396591`)

| Camino | Qué hace hoy | Garantías que le faltan (G1–G8) | Consumidores hallados |
|---|---|---|---|
| **C1** `POST /ui/descubrir/crear` | Un clic crea la serie (o reutiliza la que tenga ese identificador externo, sin avisar) con campos ocultos del formulario y un `select` de tradición preseleccionado (`web/discovery.py`, `services/discovery.py`) | G1, G2 (preselección), G3 (solo identificador), G4 (N), G5 (parcial), G6, G7 | Un único formulario (`_resultados_descubrir.html:28`); su respuesta ofrece «Añadir a deseados» (`_serie_creada.html`), que es el flujo de descargas, **fuera del MVP**. Enlace de entrada: el buscador del *dashboard* (`dashboard.html:156`) (L) |
| **C3** `POST /api/series` | `Series(**SeriesCreate)` dentro del router; tradición `american` por defecto; `metadata_source` nulo | G1–G7 | **En `src/`: ninguno** (`create_series` y `SeriesCreate` solo aparecen en `api/series.py`). **En el repositorio:** pruebas (`test_api_series.py::TestMassAssignmentSeries`, `test_cover_ssrf.py::TestPuntosDeEntrada`) y dos protocolos manuales (`docs/TESTING_E2E.md` §14.1, `docs/TESTING_NFR_Zascarr.md` NFR-03) que lo usan **para comprobar el rechazo de campos internos y de portadas**, no para crear datos (el propio E2E dice «no se usa `POST /api/series` para sembrar datos») (L). **Fuera del repositorio: no verificable (N)** |
| **`DELETE /api/series/{id}`** | Borrado físico con cascada; archivos desvinculados (`SET NULL`), disco intacto; `409` solo con operación viva | Sin vista previa, sin confirmación, sin ruta de interfaz | `test_asignacion_integracion_pg.py` (409 / 204 / otro error de integridad). **Ninguna ruta de interfaz ni código de `src/` lo llama** (L). Externos: N |
| **`PATCH /api/series/{id}`** | Cambia título, tradición, años, política de búsqueda… sin comprobar colisiones | G3 | Pruebas (`test_api_series.py`, `test_cover_ssrf.py`, `test_alta_serie_pg.py::test_la_api_de_series_no_deja_cambiar_la_procedencia`). La interfaz **no** lo usa: cambia la política por `POST /ui/series/{id}/politica` (L). Externos: N |
| **`POST /ui/pendientes/{id}/asignar`** | Asignación recuperable que **mueve y renombra** (ADR 0006); aprende alias por defecto | — (es «Organizar», no creación) | Botones de `_tarjeta_pendiente.html:20` y `_resultados_serie.html:8`; llamada única a `AsignacionService.asignar` (L, inventario E1–E4) |

**Lo que se ve de un consumidor externo.** Ni la aplicación ni el repositorio tienen telemetría (CLAUDE.md §5.3, «cero»), así que **no hay forma de medir desde la propia aplicación quién usa `POST /api/series`**. Lo único comprobable es lo anterior; lo demás (scripts de la persona, `curl`, integraciones caseras) es **N** y solo se puede mitigar con un **periodo de aviso**, no con una medición (ver P-2).

## Propuestas

Cada propuesta lleva: la decisión, la **alternativa** que se descarta y su **consecuencia**. Todas son *propuestas pendientes de aprobación*.

### P-1. C1 (`POST /ui/descubrir/crear`): dos pasos en la propia tarjeta (O-A, opción a) — propuesta preferente, sujeta a decisión sobre D2 de ADR-0008

**Propuesta preferente, sujeta a decisión sobre D2 de ADR-0008** (hay una alternativa estructural, #118, que **no es menor**: elimina I1, I2 y parte del riesgo de tokens, pero cambia el alcance de Descubrir; ver el último párrafo de este apartado). Sustituir «un clic crea» por **dos pasos en la misma tarjeta**: *«Revisar»* (el servidor firma la candidata y devuelve la vista previa en la tarjeta) y *«Crear serie»* / *«Usar esta»* (la confirmación recibe solo el token). Sobre la **variante sin grupo** de `AltaDeSerie` (cambio I1, ver F1). Hasta que se implemente, C1 **queda como está** y se declara **fuera del recorrido MVP** con su limitación explícita (D4); no se oculta ni se desactiva.

**Qué ve la persona antes de crear** (la vista previa del servicio, no datos del navegador):
1. **Título y año tal como se guardarán** (los que firmó el servidor), con la fuente y un enlace a la ficha original.
2. **La tradición, que elige ella**: el selector aparece **sin ninguna opción marcada** (G2); la suposición de la fuente se muestra como pista («la fuente sugiere: manga»), no como valor. Sin elegir, no hay botón de confirmar.
3. **Si ya existe** una serie con ese identificador: *«Ya está en tu biblioteca; se usará tal cual, sin modificarla»* (hoy se reutiliza sin avisar).
4. **Si hay series que se parecen** (mismo título normalizado, año ±1, misma tradición): la lista y la elección entre *«es esta»* y *«es distinta, crear igualmente»*; la confirmación se rechaza si han aparecido otras desde la vista previa.
5. **El efecto, en una línea:** *«Se creará una serie vacía: sin números ni archivos»* (`efectos` del servicio).
6. Tras crear: el comprobante y el enlace **«Deshacer»** mientras nada dependa de la serie (G6/G7).

**Alternativa descartada (O-A, opción b):** mostrar la vista previa **ya en el resultado de la búsqueda**, con el botón de confirmar en la misma pantalla. Obliga a **calcular una vista previa por cada resultado** (consulta por identificador y por parecidas, más un token firmado, para cada tarjeta de una búsqueda de hasta decenas de resultados) aunque la persona vaya a elegir una. En una Pi compartida (CLAUDE.md §1) es coste sin beneficio; con los dos pasos solo se calcula lo que se elige. **N:** el coste no se ha medido; el argumento es de cardinalidad (N consultas frente a 1).

**Consecuencia.** La interfaz de Descubrir pasa de «un clic» a «dos clics»; el cuerpo de `crear` deja de recibir `title`/`description`/`cover_url` del navegador (se retira la superficie de campos ocultos). Depende de **I1**.

**Punto que decide la persona que revisa (toca D2 de ADR-0008).** ADR-0008 decidió *adaptar* C1. F1 muestra que adaptar exige I1. **Alternativa estructural:** **retirar la creación desde Descubrir libre** (dejar Descubrir como búsqueda de solo lectura y crear series **solo desde un grupo de carpeta**, #118). Ventajas: no hay variante sin grupo, ni cambio de tokens, ni recálculo de límites; encaja con el MVP (el recorrido es «carpeta → alta → vincular»). Coste: la persona **no puede crear una serie vacía desde una búsqueda** (hoy lo usa el flujo de deseados, que es descargas y está fuera del MVP). **Recomendación provisional: mantener D2 (adaptar)**, porque es lo vigente y conserva el valor de producto de poder crear una serie vacía antes de que exista una carpeta o de vincular archivos; pero esa recomendación **depende de aceptar I1 y el recálculo de sus límites**. Si se prioriza reducir riesgo y alcance del MVP, la alternativa de #118 es razonable. **Ambas opciones quedan abiertas:** la decisión debe tomarse explícitamente **antes de implementar I1 o I2**, y este ADR no la toma.

### P-2. C3 (`POST /api/series`): B3 en dos fases, no B1 (O-B)

**Propuesta.** **Retirarlo en dos fases**, sin adaptarlo:
- **Fase 1 (dentro de #114):** declararlo *no recomendado y sin G1–G8* (marca `deprecated` en el esquema OpenAPI y nota en la documentación de la API; **sin cambiar su comportamiento**), y **tratar las comprobaciones que hoy hace sobre él** (rechazo de campos internos con `extra="forbid"`, política de portadas, y los dos protocolos manuales E2E §14.1 y NFR-03): las comprobaciones equivalentes deberán reubicarse o duplicarse en las pruebas que correspondan; **la cobertura exacta se decidirá al implementar I3**. **N:** `PATCH` y `POST /api/series` no comparten necesariamente el mismo contrato de rechazo (p. ej. `SeriesUpdate` admite `wishlist_policy` y `SeriesCreate` no) y esta revisión no ha verificado esa equivalencia.
- **Fase 2 (en la versión siguiente a la que contenga la fase 1, y solo con confirmación de quien opera el producto de que no hay consumidores):** eliminar la ruta o responder `410 Gone` con un mensaje en español que remita al alta. Mecanismo y periodo: **un ciclo de versión completo** con el aviso, porque no hay telemetría que permita medir uso (N).

**Por qué no B1 (adaptar).** Adaptar `POST /api/series` a `AltaDeSerie` obliga a un contrato **de dos pasos** (vista previa y token) para una ruta que **ningún componente del producto usa** (L) y que sirve a una persona que «no abre terminales ni JSON» (CLAUDE.md §1); y exige además I1 (F1). El resultado sería una API más compleja para un uso hipotético. **Por qué no B2 (dejarlo como está y excluirlo):** deja viva una brecha que permite duplicados y filas enriquecibles sin querer, sin plazo para cerrarla.

**Consecuencia.** Se pierde la creación programática de series desde fuera, si alguien la usara (**N**); queda el alta por token (`POST /api/revision/serie*`) como única vía API, con G1–G8. Los tres constructores de `Series(...)` en `src/` pasan a **dos** tras la fase 2 y a **uno** tras I2 (ver plan). **Antes de la fase 2** conviene anotar en el historial de cambios de la versión la retirada; esa anotación es parte de D4.

### P-3. `DELETE /api/series/{id}`: S2 + S3 ahora; S1 solo si algún día hay interfaz (O-C)

**Propuesta.** Combinar **S2** (bloquear si hay datos que dependen de la serie) con **S3** (excluirlo del recorrido MVP; sigue siendo una operación de administración sin ruta de interfaz):
- Mover la lógica a un servicio (`SeriesService.borrar`, hoy está en el router; CLAUDE.md §3.1.1).
- **Reutilizar los mismos predicados y el mismo orden de bloqueos que `deshacer`** (`services/alta_serie.py::_deshacer_en_transaccion`): bloquear la fila de la serie y comprobar, en este orden, **archivos vinculados** → `409 tiene_archivos`; **números** → `409 tiene_numeros`; **operación viva** → `409` (el actual, **se conserva**); **deseados o política de búsqueda distinta de `ninguno`** → `409 tiene_deseados`. Solo se borra una serie **sin dependientes**.
- **No toca el disco** (invariante que ya se cumple y hoy no tiene prueba).

**Destino de lo que hoy se pierde en silencio**, con S2 aplicado (el borrado ya no es posible si existen los tres primeros):

| Dato | Hoy | Con la propuesta |
|---|---|---|
| Archivos | Se **desvinculan** (`issue_id` → `NULL`), el disco intacto | **No se pueden desvincular por esta vía:** `409 tiene_archivos`. Desvincular sería otra operación explícita (no existe; fuera del MVP) |
| Números y todo lo que cuelga de ellos | Se borran en cascada | `409 tiene_numeros`: no se borra ninguno |
| Deseados | Se borran en cascada | `409 tiene_deseados` |
| **Alias locales** (`local_aliases`) | Se borran en cascada | **Se borran con la serie** (siguen en cascada): un alias es una correspondencia *hacia* esa serie y no tiene sentido sin ella. **Es una decisión a aprobar**; la alternativa (bloquear también por alias) hace imposible borrar una serie en la que el viejo flujo aprendió un alias, y se descarta por exigir un paso más sin proteger ningún dato de la biblioteca |
| Géneros de la serie | Cascada | Cascada (metadato de la propia fila) |
| **Comprobante de alta** (`alta_operaciones`) | Sobrevive, sin clave foránea, con el id de una serie que ya no existe | **Se conserva** (es el registro de lo ocurrido). Repetir ese token da `409 alta_serie_ausente`, sin recrear (comportamiento **vigente**, L) |
| **Informe de vinculación** (`vinculacion_operaciones`) | Sobrevive, inmutable, sin clave foránea | **Se conserva** (informe inmutable por diseño). **N:** su lectura posterior con una serie borrada no se ha comprobado |
| Operación de asignación viva | `409` | **`409` igual** (conservado) |

**Alternativas descartadas.** **S1** (vista previa de efectos + token): reutiliza un patrón sólido, pero construye maquinaria de confirmación para una operación **sin interfaz ni uso en el producto**; con S2 el borrado ya solo afecta a series vacías, así que la vista previa tendría casi nada que mostrar. Queda como **evolución natural** si algún día se añade un botón de borrar. **S4** (sustituir por «deshacer»): pierde el borrado de series que no vienen del alta (las creadas por C1/C3 no tienen comprobante) y `deshacer` ya cubre las del alta. **S5** (archivado / borrado lógico): único camino reversible, pero **cambia el modelo** (migración) y queda fuera del MVP y de #114.

**Consecuencia.** El `DELETE` deja de poder dañar el catálogo de la persona; a cambio **deja de poder borrar series con contenido** (hoy sí puede, sin avisar). Es un **cambio de contrato** (nuevos `409`); no hay consumidor conocido en `src/` (N fuera). Las series con contenido que alguien quiera quitar necesitarán una operación explícita de desvinculación que **no se propone aquí**.

### P-4. `PATCH /api/series/{id}`: detección de colisiones en los campos de identidad (O-D, opción a)

**Propuesta.** Cuando el cuerpo cambie **`title`, `tradition` o `start_year`**, el servicio ejecuta la **misma** detección de parecidas que el alta (`_parecidas`, hoy método privado de `AltaDeSerie`; se extrae a una función compartida) **excluyendo la propia serie**, bajo el **mismo candado del título normalizado** (`alta_serie:` + `f_title_norm`, G4). Si hay parecidas que el cliente no declaró haber visto, responde **`409 serie_parecida`** con la lista; para proceder, el cliente reenvía el mismo cuerpo con `vistas: [ids]` (el mismo principio que el alta: *«se rechaza si han aparecido otras que no vio»*). Los demás campos (`description`, `cover_url`, `status`, `wishlist_policy`…) **no cambian de comportamiento**.

**Alternativas descartadas.** (b) *Tratarlo con C3* (retirarlo con él): la interfaz **no** lo usa para nada hoy (L), pero sí las pruebas y es el único camino API para `wishlist_policy`/`status`; retirarlo es un recorte mayor del que justifica este hueco. (c) *Documentarlo como brecha*: deja a `PATCH` como puerta trasera para evitar la detección que se exige a todas las demás entradas, y A2 («ninguna entrada elude la comprobación») no se cumpliría. **Variante más ligera, aceptable si se prefiere (y que también cumple A2):** **rechazar `422` el cambio de `title`/`tradition`/`start_year` por esta vía** (la identidad de una serie se fija al crearla); coste: pierde la renombrada por API, que nadie usa hoy.

**Consecuencia.** El contrato de `PATCH` cambia **solo** para esos tres campos. Depende de extraer `_parecidas`, **no** de I1. **N:** no se ha comprobado si el candado del título normalizado puede tomarse desde `PATCH` sin contención con el enriquecedor (que escribe `Series` en otra transacción).

### P-5. Contrato G1–G8: cuáles se adoptan como vinculantes y con qué excepciones

*Propuesta de adopción* (el ADR 0009 las dejó propuestas):

| | Se adopta como vinculante para | Excepción explícita |
|---|---|---|
| **G1** vista previa y confirmación | Cualquier camino **que pueda ejecutar una persona** y cree una serie (C1 tras adaptarse; el alta) | `POST /api/series` hasta su retirada (P-2): **sin G1–G8, declarado** |
| **G2** tradición elegida, sin valor por defecto | **Todos** los que creen | La suposición de la fuente se muestra como pista, nunca como valor marcado |
| **G3** detección de colisiones | **Todos** los que creen **y** los que cambien título/tradición/año (`PATCH`, P-4) | — |
| **G4** serialización concurrente | **Todos** (se hereda al delegar en el servicio) | Para C1 hoy es **N**; la prueba de concurrencia (T-4) lo convierte en dato |
| **G5** procedencia versionada e identidad protegida | **Todos** los que creen | Las filas **ya existentes** creadas por C1/C3 (`metadata_source` de la fuente o nulo; sin `metadata_["alta"]`) **no se reescriben**: no hay migración de datos en este plan |
| **G6** idempotencia y comprobante | **Todos** los que creen | Las filas históricas no tienen comprobante |
| **G7** reversibilidad acotada | Las series **creadas por el alta** | Las creadas por C1/C3 **antes** del cambio no se pueden «deshacer»; para ellas queda el `DELETE` protegido (P-3). Se declara |
| **G8** sin efectos laterales | **Todos** (ya se cumple) | — |

### P-6. Criterios A1–A6: se añaden a #114 como D1–D6, no los sustituyen

A1–A6 se redactaron para #113 (*«centralizar decisiones»*). Para #114 (*«adaptar o retirar»*) **se propone mantener los tres criterios de la tarjeta como la intención y refinarlos en D1–D6** (abajo), y repartir A1–A6 así:

| Criterio del ADR 0009 | Dónde se acredita |
|---|---|
| A1 delegación en `AltaDeSerie` | **#114** (D5 y cambios I1–I2) |
| A2 colisión idéntica desde cualquier entrada | **#114** (D5; P-4 incluida) |
| A3 tabla de cumplimiento G1–G8 por entrada | **Documental**: la matriz de esta ADR (§Matriz) es su primera versión; se revisa al cerrar #114 |
| A4 borrado | **#114** (D3, cambio I4) |
| A5 vincular conserva nombre y ruta | Ya acreditado para `POST /api/revision/vinculacion` (`vinculacion_pg`, `vinculacion_limite_pg`, P); la **sustitución de la asignación en el recorrido normal** es el cambio I7 (bloqueado por 2e) |
| A6 trazabilidad | Este ADR y el comentario de reconciliación de cada PR |

### P-7. La asignación heredada (`POST /ui/pendientes/{id}/asignar`): rotular ahora, sustituir cuando exista el recorrido nuevo

**Propuesta.** Dos tiempos, que no hay que confundir:
1. **Rotular (independiente, pequeño):** los botones de `_tarjeta_pendiente.html` y `_resultados_serie.html` pasan a decir que **mueven y renombran** («Organizar: mover y renombrar a la biblioteca»), y dejan de presentarse como «Sí, es esta». Es un cambio de texto de interfaz, sin tocar `AsignacionService` (criterio 2 de #112).
2. **Sustituir en el recorrido normal por «Vincular»:** requiere la interfaz de vinculación (2e / M3 — #118–#120), **que no está autorizada ni diseñada aquí**. Hasta entonces el recorrido normal en el navegador **sigue usando la asignación que mueve**; esa es una limitación que #114 **declara**, no corrige.

**Alternativa descartada:** retirar la asignación heredada. Es el único camino de usuario que **crea alias** (inventario A1) y sin recorrido nuevo en el navegador dejaría a la persona sin forma de asignar desde la interfaz. **Consecuencia:** #114 **no puede cerrarse completa antes de que exista la interfaz de vinculación**; por eso el cambio I7 queda fuera de las dos primeras entregas.

## Matriz de garantías resultante (si se adoptan P-1 … P-5 e I1–I6 se implementan)

Estado **tras** el plan; hoy ninguna celda «propuesto» se cumple. Evidencia de la columna «hoy»: ADR 0009 y esta lectura (L).

| | C4 (alta) | C1 adaptado | C3 | `PATCH` identidad | `DELETE` |
|---|---|---|---|---|---|
| G1 vista previa y confirmación | sí (hoy) | propuesto | **retirado** (sin G1–G8 hasta entonces) | n/a: usa `vistas` | n/a |
| G2 tradición elegida | sí (hoy) | propuesto | retirado | n/a | n/a |
| G3 colisiones | sí (hoy) | propuesto | retirado | propuesto (409 + `vistas`) | n/a |
| G4 concurrencia | sí (hoy) | propuesto (T-4) | retirado | propuesto (N: contención) | propuesto (mismos bloqueos que `deshacer`) |
| G5 procedencia | sí (hoy) | propuesto | retirado | n/a (no cambia la procedencia) | n/a |
| G6 idempotencia / comprobante | sí (hoy) | propuesto | retirado | n/a | n/a (el comprobante del alta **se conserva**) |
| G7 reversibilidad | sí (hoy) | propuesto | retirado | n/a | n/a |
| G8 sin efectos laterales | sí (hoy) | sí | sí (hoy, hasta retirarse) | sí | **sí: no toca el disco** (invariante a probar, T-6) |
| Constructores de `Series(` fuera del servicio | — | 0 tras I2 | 0 tras fase 2 | — | — |

## Pruebas futuras (no ejecutadas; ninguna se añade en este ADR)

Cada una nombrada por el mecanismo que fija (CLAUDE.md §8). `PG` = Postgres real (`tests/_pg.py`).

| | Prueba | Qué fija |
|---|---|---|
| T-1 | `test_creacion_delega_en_alta_de_serie` (por entrada: C1; C3 mientras exista, como regresión de que **no** delega) | Sustituir el servicio y comprobar que se invoca con los mismos datos; falla si alguna entrada vuelve a construir `Series(...)` |
| T-2 | `test_un_solo_constructor_de_series_fuera_del_servicio` | Recuento textual de `Series(` en `src/` (hoy 3; objetivo 1: el servicio) |
| T-3 | `test_paridad_de_colision_entre_entradas` (PG) | Mismos título normalizado, tradición y año ⇒ misma detección desde C4, C1 y `PATCH` |
| T-4 | `test_c1_dos_peticiones_a_la_vez_con_el_mismo_identificador` (PG) y `…_con_el_mismo_titulo` | Que una crea y la otra reutiliza o recibe `409`, sin `500` ni duplicado (hoy **N**) |
| T-5 | `test_borrar_serie_con_archivos_da_409_y_no_cambia_nada` · `…_con_numeros…` · `…_con_deseados…` · `…_vacia_borra` · `…_con_operacion_viva_conserva_el_409` (PG) | La propuesta P-3 y la conservación del `409` ya existente |
| T-6 | `test_borrar_serie_no_toca_el_disco` (PG, con ficheros reales en un directorio temporal) | Regresión de la invariante «el borrado solo opera sobre la BD» (hoy sin prueba, N) |
| T-7 | `test_borrar_no_pierde_el_comprobante_de_alta` y `test_repetir_token_tras_borrar_da_alta_serie_ausente` (PG) | El destino documentado de los comprobantes |
| T-8 | `test_borrado_concurrente_con_vinculacion` (PG) | Que un `DELETE` y una vinculación sobre la misma serie no dejan archivos vinculados a números borrados (bloqueo `FOR SHARE` / `FOR UPDATE` común) |
| T-9 | `test_patch_de_identidad_con_parecidas_da_409` · `…_con_vistas_procede` · `…_otros_campos_no_cambian` | P-4 |
| T-10 | `test_c3_deprecated_en_openapi_y_sin_cambio_de_comportamiento` · `test_c3_retirado_responde_410` (fase 2) | P-2 |
| T-11 | `test_tokens_limites_alta_sin_grupo` (PG, siguiendo `test_tokens_limites*`) | Límite máximo **calculado** de la variante sin grupo, no heredado (F1) |
| T-12 | `test_rotulo_de_organizar_en_botones_que_mueven` | Que el texto de los botones de E1/E2 diga que mueven (P-7) |

**Pruebas existentes que habrá que reubicar o ajustar (P):** `test_web_discovery.py` (2 casos de crear/reutilizar), `test_discovery_service.py` (`get_or_create_series`), `test_api_series.py::TestMassAssignmentSeries`, `test_cover_ssrf.py::TestPuntosDeEntrada` (las que usan `POST /api/series`), `test_asignacion_integracion_pg.py` (los casos de `DELETE`). **N:** no se ha leído qué siembra su fixture `mundo` en esa clase; si la serie tiene números o archivos vinculados, «con la asignación cerrada el borrado procede» pasaría a dar `409` con P-3 y habría que sembrar una serie vacía. El caso «otro error de integridad no se disfraza de 409» parchea `zascarr.api.series.AsyncSession.flush` y habrá que reubicar el parche al mover la lógica al servicio.

## Plan de implementación: cambios, dependencias y orden

Se propone **dividir #114** en los cambios siguientes (cada uno, una PR; **no se crean las tarjetas** aquí: hacerlo cambia el tablero y no está autorizado). Tallas relativas, **N: sin calibrar**.

| | Cambio | Depende de | Orden | Criterio de «hecho» |
|---|---|---|---|---|
| **I3** | C3 fase 1: `deprecated`, nota de documentación y reubicación de pruebas y protocolos | — | 1.º | T-10 (fase 1); sin cambio de comportamiento; las comprobaciones equivalentes de rechazo de campos internos y de portadas quedan reubicadas o duplicadas donde corresponda (cobertura exacta decidida en I3) |
| **I4** | `DELETE` protegido y extraído a servicio (P-3) | — | 1.º (en paralelo con I3) | T-5, T-6, T-7, T-8 en verde; el `409` por operación viva conservado; `test_asignacion_integracion_pg` sin cambios de significado |
| **I5** | Detección compartida y colisión en `PATCH` (P-4) | extraer `_parecidas` | 2.º | T-9 y T-3 (parte `PATCH`) |
| **I1** | Variante sin grupo de `AltaDeSerie` (F1): contexto fijo, `desde_grupo` ausente, límites recalculados | — (pero **antes** de I2) | 2.º | T-11; el comportamiento del alta con grupo **no cambia** (las pruebas de `alta_serie_pg`, `tokens_*` siguen igual) |
| **I2** | C1 en dos pasos sobre I1 (P-1) | I1 | 3.º | T-1, T-3 (parte C1), T-4; C1 deja de construir `Series(...)`; el único constructor restante es el del servicio una vez retirado C3 (I6) |
| **I6** | C3 fase 2: retirar o `410` | I3 + un ciclo de versión + confirmación de que no hay consumidores | 4.º | T-10 (fase 2), T-2 |
| **I7** | Sustituir la asignación en el recorrido normal por «Vincular» (P-7, punto 2) | **2e / M3 (#118–#120), no autorizado** | último | Dependiente de otro plan; no se dimensiona aquí |
| **I8** | Rotular «Organizar» (P-7, punto 1) | — | cualquiera | T-12 |

**Tallas orientativas (N):** I3 S · I4 M · I5 M · I1 L (es el coste que F1 destapa) · I2 M · I6 S · I8 S. Si I1 se descarta (la alternativa estructural de P-1), I2 desaparece y P-1 se reduce a una retirada de interfaz (S).

**Qué es MVP y qué no.** I3, I4, I5 y I8 reducen riesgo **sin tocar** la interfaz de vinculación; I1/I2 y I7 dependen de la decisión sobre C1 y de 2e. El orden propone **cerrar primero lo que protege los datos de la persona** (I4) y lo que no cuesta nada (I3, I8).

## Criterios de aceptación de #114 (propuestos, no sustituyen aún a los de la tarjeta)

Mantienen los tres criterios actuales como intención y los hacen comprobables:

- **D1. Decisión por camino.** Cada camino heredado (C1, C3, `DELETE`, `PATCH`, la asignación que mueve) tiene **una decisión** (adaptar, retirar, proteger o declarar fuera), con su alternativa y su consecuencia, trazada a este ADR. *(Criterios 1 y 3 de la tarjeta.)*
- **D2. Contrato adoptado.** Constan **qué garantías G1–G8 se adoptan y con qué excepciones** (P-5), y la matriz refleja el estado real tras cada cambio.
- **D3. Borrado acotado.** `DELETE` no toca el disco, conserva el `409` por operación viva, bloquea con dependientes (archivos, números, deseados) y deja **documentado** el destino de archivos, alias, deseados y comprobantes (P-3).
- **D4. Compatibilidad.** Las rutas **adaptadas** conservan o sustituyen su contrato **por escrito**; las **retiradas** identifican consumidores (los del repositorio, listados; los externos, declarados **no verificables**), el mecanismo (`deprecated`, luego `410` o eliminación) y el **periodo** (un ciclo de versión). *(Criterio 1.)*
- **D5. Pruebas de aceptación enumeradas.** T-1 … T-12 de este ADR, cada una nombrada por su mecanismo, con las regresiones de **delegación, paridad de colisión, cascada, desvinculación sin tocar el disco y concurrencia**. *(Criterio 2.)*
- **D6. División en cambios.** El trabajo está dividido en I1–I8 con dependencias, orden y criterio de hecho (arriba), de modo que ninguna PR sola concentre la talla L. *(La tarjeta, estimada L con confianza baja, queda refinada; no se recalibra.)*

## Trazado

| Tarjeta | Qué aporta este ADR | Qué queda fuera |
|---|---|---|
| [#113](https://github.com/juanajok/zascarr/issues/113) (M1-US02) | Cierra el diagnóstico (F1), convierte O-A … O-D en propuestas y reparte A1–A6 | G1–G8 siguen **sin adoptarse** hasta aprobar este ADR; la centralización real es implementación. **#113 no se cierra** |
| [#114](https://github.com/juanajok/zascarr/issues/114) (M1-US03) | Es su refinamiento: D1–D6 propuestos y la división I1–I8 | Todo el código, las pruebas y la sustitución en el recorrido normal |
| [#104](https://github.com/juanajok/zascarr/issues/104) (Feature M1) | M1 pide «operaciones coherentes»: este plan ordena qué se adapta, qué se retira y qué se declara fuera | El avance de M1 solo se mide cuando los cambios I1–I8 estén fusionados **y** desplegados |
| [#105](https://github.com/juanajok/zascarr/issues/105) (Feature M2) | M2 es la «confirmación robusta» (tokens, límites, respuesta posterior al commit): P-1 **reutiliza** esa maquinaria para C1, y I1 obliga a **recalcular sus límites** como se hizo en #138/#139 | M2 no se modifica; los límites de la variante sin grupo se acreditan en I1, no aquí |
| [#112](https://github.com/juanajok/zascarr/issues/112), [#118](https://github.com/juanajok/zascarr/issues/118) | #112 (criterio 2, «Organizar») ← P-7; #118 («Descubrir o crear desde un grupo») es la alternativa estructural de P-1 | La interfaz de M3 está **pausada** |

## Alternativas consideradas (resumen)

- **Un servicio común** (propuesto, ADR 0009) frente a **normas por router**: no se reabre.
- **Adaptar todo** (C1, C3, `DELETE` con vista previa) frente a **retirar lo que el producto no usa**: se propone adaptar lo que una persona ejecuta (C1, `PATCH`), **proteger** lo que destruye (`DELETE`) y **retirar** lo que solo usan las pruebas (C3). Lo contrario (adaptar C3) multiplica el trabajo por un uso hipotético.
- **No hacer nada hasta que exista 2e:** descartado; I3, I4, I5 e I8 no dependen de 2e y quitan riesgo hoy.

## Consecuencias

- Los cambios de contrato son **cuatro** y deben comunicarse: C1 pasa a dos pasos; C3 se retira; `DELETE` deja de borrar series con contenido; `PATCH` puede dar `409` al cambiar identidad. Ninguno tiene consumidor conocido en `src/`; los externos son **N**.
- El mayor coste y riesgo es **I1** (variante sin grupo y recálculo de límites). Si la persona que revisa prefiere la alternativa estructural de P-1, el plan se simplifica a costa de revisar el alcance de D2 de ADR-0008.
- Mientras nada se implemente, **todo sigue como en el ADR 0009**: la brecha existe, está documentada y es la misma.

## Hipótesis abiertas (N)

1. El coste de la variante sin grupo (I1) y el recálculo de límites; no se ha prototipado.
2. Que no haya consumidores externos de `POST /api/series`, `PATCH` o `DELETE`; no hay telemetría ni forma de medirlo.
3. Que el candado del título normalizado pueda tomarse desde `PATCH` sin contención con el enriquecedor.
4. La lectura posterior de un informe de vinculación cuya serie se ha borrado.
5. El comportamiento de C1 ante dos peticiones simultáneas con el mismo identificador (el router solo captura `ValueError`; ADR 0009 ya lo marcó).
6. Que las claves foráneas de una base **migrada** coincidan con las del ORM (el ADR 0009 ya lo marcó).
7. Las tallas de I1–I8: sin calibrar.

## Dependencias y exclusiones

- **Depende de:** ADR-0007, ADR-0008, ADR-0009 y el inventario (#165). **Desbloquea:** las tarjetas de implementación I1–I8, **cuando se autoricen**.
- **No autoriza ni describe como hecho:** código, pruebas, migraciones, cambios de contrato, la interfaz de M3 (2e), fuentes reales, despliegue, la creación de tarjetas, ni cambios en el tablero más allá de los estados de #114.
- **No cierra #114 ni #113.** Al fusionarse, quedan **adoptadas** solo las decisiones previas (D1–D3 del ADR 0009, ya vigentes) si la persona que revisa aprueba el documento como «Aceptado»; mientras permanezca «Propuesto», P-1 … P-7 y D1–D6 siguen **pendientes de decisión**, y **toda la implementación** está pendiente.
