# Historias de «reconciliación de la biblioteca» (patrones de Plex) — propuesta

> **Estado: propuesta para el PO. No crea tarjetas, no cambia el backlog y no autoriza código.** Cada historia está
> escrita con el formato de las tarjetas del Kanban para poder publicarse tal cual **cuando se decida**.
> Fecha: 2026-10-18 · `main` revisado: `f2c45c4`.
>
> **Revisado el 2026-10-18** (cabeza `5fe61e3`): esta versión incorpora las correcciones pedidas —criterios contradictorios o
> demasiado abiertos en BL-R1, BL-R2, BL-R3 y BL-R5, dependencias desalineadas y nombre de BL-R7— y recoge las resoluciones
> propuestas para D1–D7 (§6). **Las tarjetas BL-R (#228–#236) ya se habían creado en Backlog por orden del PO antes de esa
> revisión**: llevan el texto anterior hasta que se decida actualizarlas.

## 1. De dónde sale y qué se sabe de verdad

El origen es un análisis del revisor sobre Plex (documentación funcional de soporte y el repositorio oficial
`plexinc/tmdb-example-provider`, commit `3348a89009bb418e083646fbe1360f544774bf71`). **Yo no he verificado ni la
documentación de Plex ni ese repositorio**; lo que aquí se dice de Plex es «documentado por el revisor». Lo que sí está
verificado por mí es lo de **ZascArr**: cada fila de la tabla siguiente se contrastó con el código de `main` (`f2c45c4`)
y con las tarjetas abiertas.

Reglas que se mantienen:
- **No se copia código ni interfaz de Plex** (el servidor es propietario). Se adoptan **patrones de comportamiento**
  documentados, con implementación propia. El ejemplo oficial declara ISC: una reutilización literal exigiría revisar
  sus avisos y dependencias (CLAUDE.md §13, «barrera legal»).
- **Ninguna historia P0/P1 pasa a «Lista para desarrollar» sin su ficha §13** (historia BL-R0): el análisis de Plex no
  la sustituye, la alimenta.
- El `tmdb-example-provider` es un **ejemplo para desarrolladores**, no el algoritmo interno de Plex: no demuestra cómo
  identifica Plex.

## 2. Reconciliación, patrón por patrón

«Hoy» es lo **verificado en el repositorio**; «cubierto por» son tarjetas ya abiertas.

| Patrón de Plex (documentado) | Hoy en ZascArr | Cubierto por | Hueco real | Decisión |
|---|---|---|---|---|
| **Corregir / desvincular una identificación** (*Fix Match*, *Unmatch*) | `services/vinculacion.py` declara que **no desvincula ni reasigna jamás** un archivo ya vinculado; el vínculo guarda su `operacion_id` y el estado previo (`metadata.vinculo.previo`) | M5 (#124–#126, #181–#184) para la identidad bibliográfica | **No hay forma de deshacer ni corregir un vínculo.** | **Historia nueva: BL-R1** |
| **Bloqueo de campos editados a mano** | `locked_fields` en serie, número y creador; el enriquecedor lo respeta (`enricher.py`); el alta manual fija `metadata_source='manual'` | **#127** (mostrar), **#128** (plan por campo, «bloqueado», «propuesta sin pérdida») | Proteger la **relación** confirmada y registrar la discrepancia con una fuente | **Historia nueva acotada: BL-R4** (los valores ya los cubren #127/#128) |
| **Conservar lo no disponible** (papelera) | **B7 hecha**: `is_missing`/`missing_since`, reaparición automática, guardarraíles (raíz inaccesible o vacía, desaparición masiva ≥ 50 % y ≥ 10) y `ImportRun.disappeared_count`. Los guardarraíles **solo se escriben en el log** | — | **Hacerlo visible** y distinguir las causas en la interfaz | **Historia nueva: BL-R2** (no repite B7) |
| **Escanear ≠ refrescar metadatos** | Ciclos **separados** en `config.py` (importación, escaneo y enriquecimiento con intervalos propios) | #134 (cortesía) | La persona **no puede lanzar uno sin el otro** ni ver cuándo fue el último | **Historia nueva: BL-R3** |
| **Identificadores externos** | Columnas únicas por proveedor (`comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`); `Issue.isbn` **existe y nada la lee ni escribe** | #129 (otra fuente), #182 (discriminantes) | Resolver por id **antes** que por título, visible en la evidencia | **Historia nueva: BL-R5** (depende de #182) |
| **Proveedores con capacidades declaradas** | `DiscoveryService` enruta por tradición; sin contrato de capacidades | **#133** (estados y capacidades por fuente) | — | **Sin historia nueva**: ampliar #133 (§5) |
| **Versiones agrupadas / separar** | B16: informe de duplicados por hash; varios `File` por `Issue` posibles | M5 (identidad), B16 | Presentar **copia / variante / edición** sin confundirlas | **Historia nueva: BL-R6** (P2, tras M5) |
| **Colecciones inteligentes** | Listas (`reading_lists`) y arcos (`story_arc_issues.reading_order`) en el modelo; vistas de trabajo: **no** | #155 (colecciones de series), #151/#163 (listas y arcos) | Vistas de **trabajo** predefinidas (pendientes, conflictos…) | **Historia nueva: BL-R7** (P2) |
| **Órdenes alternativos** | `story_arc_issues.reading_order` | #151, #163 | — | **Sin historia nueva**: nota en esas tarjetas (§5) |
| **Coste real de paginar** | Revisión de vinculación pagina a 100 y evalúa solo la página | #122 (coste operativo) | Medir objetos procesados, no filas devueltas | **Sin historia nueva**: se mide en BL-R0 y #122 |

## 3. La feature y su orden

**BL-R — Reconciliación de la biblioteca (patrones de Plex).** Agrupa lo que mantiene la biblioteca utilizable pese a
errores de identificación, cambios de metadatos y almacenamiento que falla. Feature padre propuesta: la nueva BL-R
(las historias heredadas del Backlog de producto cuelgan de #148).

| Orden de entrega | Historia | Prioridad | Pts | Depende de |
|---|---|---|---|---|
| 1 | **BL-R0** Ficha §13 de la reconciliación | P0 | 3 | — |
| 2 | **BL-R2** Ver qué archivos no están disponibles y por qué | P1 | 5 | BL-R0 |
| 3 | **BL-R1** Corregir o deshacer la vinculación de un archivo | P0 | 8 | BL-R0; ADR 0006/0007 |
| 4 | **BL-R3** Comprobar el disco sin consultar las fuentes | P1 | 3 | BL-R0; #133; #134 |
| 5 | **BL-R4** Proteger una relación confirmada frente a una fuente | P1 | 5 | #127, #128, #129, BL-R1 |
| 6 | **BL-R5** Resolver una serie por un identificador de fuente | P1 | 5 | BL-R0; #129; #133 |
| 7 | **BL-R6** Varios archivos de una publicación | P2 | 5 | M5 (#125/#126), BL-R1 |
| 8 | **BL-R7** Vistas de trabajo predefinidas | P2 | 8 | BL-R2, BL-R4, BL-R6, #199, #200 |

Total **provisional de 42 puntos**, sin calibrar y **no un compromiso**: las decisiones de corrección, auditoría y persistencia
(D1–D4) pueden cambiar el esfuerzo. El orden recomendado por el análisis (conservación → protección →
corrección → escaneo/refresco → variantes y vistas) se respeta con un cambio: BL-R2 se **entrega** antes que BL-R1 porque
**B7 ya resolvió el núcleo** y lo que falta es barato y da visibilidad enseguida; BL-R1 es el hueco más caro y el que más
duele. **Es un orden de entrega, no una dependencia técnica:** BL-R1 no necesita a BL-R2.

---

## 4. Las historias

### BL-R — [Feature] Reconciliación de la biblioteca (patrones de Plex)

Agrupa las historias BL-R0 a BL-R7. Nace del análisis de patrones de Plex contrastado con el código y las tarjetas
existentes: lo ya cubierto por B7, #127, #128, #129 y #133 **no se duplica** (ver la tabla de reconciliación del
documento). Límites: publicar esta tarjeta no autoriza código, fuentes reales, migraciones en producción ni despliegue.

---

### BL-R0 — Ficha de benchmark de la reconciliación (spike documental)

Como responsable del producto, quiero una ficha §13 de los patrones de reconciliación, para decidir qué se adopta de
Plex y de los cómics sin copiar lo que no sirve.

**Planificación propuesta:** P0 · Must · 3 puntos · confianza Media. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** `docs/design/benchmark-referencias.md` (procedimiento) y
`docs/design/benchmark-identidad-editorial.md` (Kapowarr `c191dda`, Mylar3 `cdc94a4`, ya fijados). Es la **puerta** de
BL-R1 a BL-R7.

**Alcance.** Un documento `docs/design/benchmark-reconciliacion-plex.md`. No implementa código ni toca el backlog.

**Criterios de aceptación**
1. **Problema local primero.** Para cada uno de los seis escenarios (corregir una identificación equivocada, actualizar
   tras una edición manual, desconectar y reconectar una raíz, escanear sin cambios, dos digitalizaciones y dos
   ediciones, pedir una página de una colección grande) figura la historia, un caso real **anonimizado**, el comportamiento
   actual de ZascArr y el resultado deseado.
2. **Referencias fijadas.** Cada referencia lleva versión o commit y fecha de lectura: `tmdb-example-provider` en
   `3348a89…`, cada artículo de soporte de Plex con su URL, y Kapowarr, Mylar3 y Suwayomi donde sean pertinentes.
3. **Documentado frente a demostrado.** Cada afirmación sobre Plex se marca como «documentado» o «demostrado por código»;
   lo no verificado se dice. «No lo encontré» no se escribe como «no existe».
4. **Adoptar, adaptar o descartar**, con motivo, por patrón (incluidos los que la propuesta descarta: vaciado automático
   de la papelera, jerarquía audiovisual).
5. **Barrera legal.** Para el ejemplo ISC se revisa el fichero concreto antes de proponer reutilizar nada; Plex servidor
   no se usa ni se copia.
6. **Pruebas de benchmark definidas, no ejecutadas.** Los seis escenarios quedan con qué medir (llamadas externas,
   memoria, objetos procesados, lecturas y escrituras), dataset y umbral propuesto para la Pi.
7. **Decisiones abiertas** de las historias siguientes listadas (§6 de este documento) y respondidas o diferidas.

**Límites.** Fuera: código, migraciones, ejecutar Plex, fuentes reales.

---

### BL-R1 — Corregir o deshacer la vinculación de un archivo

Como coleccionista que vinculó un archivo al número equivocado, quiero corregir o deshacer esa vinculación, para no
tener que dejar la biblioteca mal clasificada ni tocar la base de datos.

**Planificación propuesta:** P0 · Must · 8 puntos · confianza Baja. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** `services/vinculacion.py` **no desvincula ni reasigna** un archivo ya vinculado
(es una decisión de diseño de 2d); cada vínculo guarda `metadata.vinculo` con `operacion_id`, `issue_creado` y el estado
previo (`previo.match_status`, `previo.review_motivo`), y el informe vive inmutable en `vinculacion_operaciones`.
`File.issue_id` tiene `ON DELETE SET NULL`. Patrones a reutilizar: vista previa → token firmado → comprobante
idempotente (#103, #116, #117, #120, ADR 0006/0007). La corrección **bibliográfica** (otra edición o publicación)
depende de M5 (#125/#126, #181–#184) y **queda fuera**: esta historia opera sobre serie + número.
Requiere BL-R0.

**Alcance.** **Deshacer** la vinculación de un archivo (vuelve a Pendientes) y, después, **volver a vincular** con el
recorrido existente. Son dos operaciones separadas; «corregir» es esa secuencia, no una sustitución atómica. No mueve ni
renombra archivos.

**Criterios de aceptación**
1. **Entrada.** Desde la ficha de la serie y la de un archivo vinculado hay «Deshacer esta vinculación». No hace falta
   pasar por el alta.
2. **Vista previa sin escribir.** Antes de confirmar se ve: de qué serie y número sale; si ese número se queda sin
   archivos; si lo creó esa misma vinculación (`issue_creado`); si algo depende de él (lecturas, deseados, otros
   archivos); y qué se conserva (ruta, nombre, contenido y hash).
3. **Deshacer.** `issue_id` vuelve a ser nulo y el archivo reaparece en «Por revisar». La fila no se borra y el fichero no
   se toca. **El estado previo (`match_status`, `review_motivo`) se conserva como evidencia histórica; no se restaura a
   ciegas:** el estado vigente tras desvincular cumple el contrato **actual** de Pendientes.
4. **Se deshace lo que se revisó.** La operación comprueba que el vínculo y su versión siguen siendo los de la vista
   previa; si han cambiado, rechaza la confirmación y exige una vista previa nueva. Nunca sobrescribe cambios posteriores
   ni convierte una instantánea antigua en la verdad actual.
5. **El número que creó esa vinculación se conserva siempre** (propuesta para D1). Retirarlo sería otra operación,
   explícita y fuera de esta primera versión.
6. **Volver a vincular** usa el recorrido existente (#119/#120) como una operación **aparte**, con su propia vista previa y
   confirmación. **Si se cancela o falla, el archivo queda pendiente de revisión**, y la pantalla lo explica **antes** de
   confirmar el deshacer. No se promete una reasignación atómica ni la restauración automática del vínculo anterior: si
   se quisiera, sería otro contrato y habría que reestimar.
7. **Historial.** Lo anterior queda anotado (que estuvo vinculado, a qué, y cuándo se corrigió) sin perder la procedencia
   original.
8. **Recuperable.** La operación es **idempotente y deja un comprobante duradero**: repetirla no duplica nada y un fallo
   incierto se resuelve comprobando el resultado, como en #116/#120. Si el comprobante va en una tabla nueva o en un
   mecanismo existente no se decide aquí (D2).
9. **Límites honestos.** Si el archivo lo movió una asignación de V6a, no se devuelve a su carpeta anterior y la pantalla
   lo dice. Un archivo con asignación en curso se rechaza como `en_curso`; uno `is_missing` sí se puede desvincular.
10. **Pruebas.** Postgres real, mutaciones y navegador real; PASS, FAIL y NOT RUN separados.

**Límites.** Fuera: corrección de edición o publicación (M5), cambios en lote, mover el archivo, aprender alias, retirar
el número creado y reasignación atómica.
Puede requerir una tabla de comprobantes (D2): sería una migración con su ADR, **no** autorizada por esta tarjeta.

---

### BL-R2 — Ver qué archivos no están disponibles y por qué

Como coleccionista con la biblioteca en un USB o un NAS, quiero ver qué archivos no están disponibles y por qué, para no
creer que he perdido tebeos cuando solo se ha desconectado un disco.

**Planificación propuesta:** P1 · Should · 5 puntos · confianza Media. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** **B7 está hecha** y no se repite: `is_missing`/`missing_since`, reaparición
automática y guardarraíles (raíz inaccesible o vacía; desaparición masiva ≥ 50 % y ≥ 10 archivos). Los guardarraíles
solo dejan una línea de log (`importer.biblioteca_inaccesible_omitiendo_desaparecidos`). `ImportRun` ya persiste cada
ciclo (`disappeared_count`, `details` JSON). El vocabulario de causas ya existe en `vinculacion_previa` (permiso, error
de lectura, biblioteca no accesible, no es un archivo). Requiere BL-R0.

**Alcance.** Hacer visible el estado de disponibilidad y su causa. No cambia cuándo se marca una baja.

**Criterios de aceptación**
1. **Dos niveles, no uno.** Por un lado, el **estado conocido del archivo** (disponible, «no se encuentra»,
   «sin permiso de lectura»); por otro, el **resultado de la última comprobación de su raíz** (accesible o «el disco no
   responde»). Se reutiliza el vocabulario de causas existente y no se mezclan en una sola etiqueta.
2. **El ciclo que no marca nada lo dice.** Si un guardarraíl omite las bajas, el resultado se guarda (en
   `ImportRun.details`, sin migración) y **Estado** lo muestra con la acción: «No se ha podido comprobar el disco; no se
   ha marcado nada».
3. **Raíz no comprobable ≠ archivos comprobados.** Cuando una raíz no puede comprobarse, se **conserva el último estado
   conocido** de sus archivos y se muestra que su disponibilidad **actual no está verificada**, con el motivo y la fecha
   de la última comprobación válida. Nunca se presentan como recién comprobados y disponibles.
4. **Lista de no disponibles** con desde cuándo (`missing_since`) y a qué serie y número estaban vinculados. No se borra
   ninguna ficha ni relación (prueba explícita).
5. **Reaparición visible.** Al volver, el archivo se restaura solo (ya ocurre) y el siguiente informe lo cuenta como
   recuperado.
6. **Desaparición masiva.** Si salta el umbral, se informa «parecen demasiados: no se ha marcado nada», con el recuento.
   **Un guardarraíl no demuestra pérdida de archivos**, y una **raíz vacía no demuestra por sí sola** que el disco esté
   desmontado: los mensajes no lo afirman.
7. **Nada destructivo.** La pantalla no ofrece borrar ni «vaciar» nada; el vaciado automático de la papelera de Plex se
   descarta expresamente.
8. **Sin red ni lectura de contenido.** Se permite comprobar acceso y existencia; se excluyen el hash, la descompresión
   y el OCR.
9. **Pruebas.** Raíz desmontada, raíz vacía, permiso denegado y archivo suelto: ninguna baja falsa y mensaje correcto.

**Límites.** Fuera: cambiar los umbrales, borrar fichas, reintentos de montaje.

---

### BL-R3 — Comprobar el disco sin consultar las fuentes

Como coleccionista, quiero comprobar mi disco sin que ZascArr consulte ninguna fuente, y actualizar los datos de las
fuentes sin recorrer el disco, para controlar cuándo se hace cada cosa.

**Planificación propuesta:** P1 · Should · 3 puntos · confianza Media. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** Los ciclos ya son independientes (`import_interval_minutes`, `scan_interval_minutes`,
`enrich_interval_minutes` en `config.py`; el enriquecedor corre por lotes). No hay ninguna ruta HTTP que lance ninguno de los dos (solo los bucles de `main.py`: verificado), así que falta que la
persona pueda **lanzar** cada uno y ver cuándo corrió el último. La auditoría («Revisar mi biblioteca») es un análisis de solo lectura, no esto. Dependencias:
BL-R0, #134 (cortesía), #133 (fuentes apagadas).

**Alcance.** Dos acciones y su estado en la interfaz. No cambia la frecuencia automática.

**Criterios de aceptación**
1. **Dos acciones con nombre claro:** «Comprobar el disco» y «Actualizar datos de las fuentes».
2. **«Comprobar el disco» no hace ninguna petición externa** (probado vigilando la red) y dice qué miró: archivos
   revisados, nuevos, no encontrados y cuánto tardó.
3. **«Actualizar…» respeta la cortesía y las fuentes apagadas** y no recorre el disco.
4. **Última ejecución** de cada una a la vista, y **próxima ejecución programada** por separado: lanzar una operación
   a mano no reprograma el ciclo automático.
5. **Una comprobación sin cambios no modifica archivos, relaciones ni metadatos del catálogo.** Se permiten las
   escrituras **operativas** necesarias para registrar y coordinar la ejecución (última ejecución, duración, resultado,
   candado), **contabilizadas por separado** del catálogo.
6. **Sin solapes.** Si ya hay una en marcha, se dice y no se lanza otra.
7. **Coste en la Pi** medido con más de 1.000 archivos sintéticos: lecturas y tiempo (NOT RUN hasta ejecutarse allí).

**Límites.** Fuera: nuevas frecuencias, nuevas fuentes, actualización parcial por serie.

---

### BL-R4 — Proteger una relación confirmada frente a lo que proponga una fuente

Como coleccionista que ha confirmado a qué publicación corresponde un archivo, quiero que una actualización de fuentes
no lo cambie nunca y que me avise si una fuente discrepa, para no perder mi trabajo ni aceptar un cambio a ciegas.

**Planificación propuesta:** P1 · Should · 5 puntos · confianza Baja. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** Los **valores** ya están cubiertos: `locked_fields` (respetado por el enriquecedor),
#127 (mostrar bloqueo) y #128 (plan por campo con «bloqueado» y «propuesta sin pérdida»). Lo que falta es la protección de
la **relación** archivo → publicación y el registro de la discrepancia. Una relación manual hoy se reconoce por
`metadata_source='manual'` y `metadata.vinculo`. Depende de #127, #128, #129 y BL-R1; si #128 absorbe estos criterios, esta
historia se cierra como duplicada.

**Alcance.** Garantía y visibilidad. No fusiona ni resuelve conflictos.

**Criterios de aceptación**
1. **Qué es «confirmada».** Una relación con una **aceptación explícita** de la persona y procedencia verificable de esa
   acción (D3). `metadata_source='manual'` por sí solo no basta, y las relaciones antiguas sin esa evidencia no se marcan
   retroactivamente.
2. **Nunca la cambia una fuente.** Ni el enriquecimiento ni la importación modifican o quitan `issue_id` ni la serie de un
   archivo confirmado (prueba de regresión con mutación).
3. **Discrepancia visible.** Si una fuente apunta a otra edición o identificador distinto del confirmado, se registra qué
   dice la fuente y qué confirmó la persona, sin aplicarlo. Primero se define su identidad, su procedencia y su ciclo de vida; dónde se guarda se difiere (D4).
4. **Dos salidas, ninguna destructiva:** «Mantener lo mío» (recuerda **esa propuesta concreta** para no repetirla; no silencia a la fuente) y
   «Revisar» (abre #129). No hay «aceptar» de un clic.
5. **Sin efectos en archivos.**
6. **Pruebas.** Una actualización con otra edición propuesta conserva la relación y deja la discrepancia; «Mantener lo mío»
   no vuelve a aparecer.

**Límites.** Fuera: fusionar, resolución automática, nuevos campos protegibles (eso es #127/#128).

---

### BL-R5 — Resolver una serie por un identificador de fuente

Como coleccionista que conoce el identificador o el enlace de una ficha, quiero identificar la serie con él, para no
depender de que el título coincida.

**Planificación propuesta:** P1 · Should · 5 puntos · confianza Baja. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** `Series` tiene `comic_vine_id`, `anilist_id`, `tebeosfera_slug` y `gcd_id`, únicos.
La búsqueda del asistente es **por título**. `Issue.isbn` existe y **nada la lee ni la escribe**. Depende de #129, #133
(estados por fuente) y BL-R0 (qué fuentes soportan consulta por id). El ISBN lo trata #182, no esta historia. Pasa por el
alta existente; no crea otro camino.

**Alcance.** Entrada «pegar identificador o enlace» en el asistente de elegir serie.

**Criterios de aceptación**
1. **Primero el identificador.** Si la persona aporta uno, se resuelve por id exacto **antes** de buscar por título, y la
   pantalla dice por cuál de los dos caminos se llegó.
2. **Error de la fuente ≠ no existe.** Una caída, una clave que falta o un límite de cortesía se muestran como tales
   (#133), nunca como «ese identificador no existe».
3. **Un solo resultado no es certeza:** la persona lo confirma; nada se elige por ella.
4. **Validación de la forma sin red;** tráfico solo a petición.
5. **ISBN queda fuera de esta historia.** Es un identificador de **publicación** (`Issue`), no de serie: su tratamiento se
   estudia en #182 con la entidad bibliográfica que corresponda y no se convierte implícitamente en identificador de serie.
6. **Pasa por la candidata firmada y el alta** (vista previa y confirmación separadas).

**Límites.** Fuera: nuevas fuentes, resolución automática, tratar el identificador externo como identidad principal, ISBN.

---

### BL-R6 — Varios archivos de una publicación: copia, variante o edición

Como coleccionista con dos archivos del mismo número, quiero saber si son la misma copia, dos versiones del mismo tebeo o
dos ediciones distintas, para no borrar ni agrupar por error.

**Planificación propuesta:** P2 · Could · 5 puntos · confianza Baja. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** B16 detecta repetidos por hash (`LibraryAudit`, `/ui/auditoria`); un `Issue` puede
tener varios `File`. La distinción edición frente a variante exige el modelo de M5 (#125/#126) y la corrección de BL-R1.

**Criterios de aceptación**
1. **Tres respuestas distintas** en la ficha: copia exacta (mismo contenido), variante (otro archivo de la misma
   publicación) y edición distinta (otra publicación). **Nunca se agrupa solo por título y número.**
2. **Se muestra lo que diferencia** (formato, tamaño, calidad) sin inventar lo desconocido.
3. **Separar** devuelve el archivo a Pendientes con BL-R1; nada se borra ni se mueve.
4. **Sin elección automática** de cuál es «el bueno».

**Límites.** Fuera: borrar duplicados, elegir versión preferente, fusionar ediciones.

---

### BL-R7 — Vistas de trabajo predefinidas

Como coleccionista, quiero vistas que me enseñen lo que necesita mi atención (sin identificar, dudosas, con
discrepancias, no disponibles, con varias variantes), para empezar por donde importa sin cambiar mis carpetas.

**Planificación propuesta:** P2 · Could · 8 puntos · confianza Baja. Estimación inicial, no calibrada.

**Trabajo existente y dependencias.** No hay vistas de trabajo. Las listas (`reading_lists`) y los arcos
(`story_arc_issues.reading_order`) son otra cosa, y #155 cubre colecciones **de series**. Depende de BL-R2, BL-R4, BL-R6,
#199 y #200 (la entrada por carpeta de «Por revisar»).

**Criterios de aceptación**
1. **Vistas predefinidas**, no un editor general: «Sin identificar», «Identificación dudosa», «Con discrepancias»,
   «No disponibles» y «Con varias variantes», cada una con su recuento.
2. **Son consultas, no tablas:** un elemento entra y sale solo al cumplir o dejar de cumplir la condición; no hay
   pertenencia almacenada.
3. **Distinta de una colección editorial (#155) y de una lista personal (#151):** el vocabulario lo deja claro.
4. **Coste real en la Pi:** pedir una página no construye el conjunto completo antes de recortarla (medido en objetos
   procesados y memoria, no solo en filas devueltas).
5. **Sin efectos:** abrir una vista no escribe nada.

**Límites.** Fuera: filtros guardados por la persona (v2) —por eso se llaman «predefinidas»—, tarjetas con portadas, orden de lectura.

---

## 5. Ampliaciones propuestas a tarjetas existentes (no se editan sin orden)

| Tarjeta | Qué se añadiría |
|---|---|
| **#133** | Criterio: el contrato declara por fuente qué capacidades ofrece (buscar, ficha por identificador, portadas) y las capacidades no declaradas no se consultan; y **un error del proveedor nunca se presenta como «no existe»**. |
| **#128** | Referencia cruzada a BL-R4: la discrepancia con una **relación** confirmada no es un campo del plan. Escenario de benchmark «actualizar tras una edición manual». |
| **#129** | Dependencia de BL-R5 para resolver por identificador. |
| **#151 / #163** | Nota: el orden de lectura es una vista independiente de la ubicación física; el modelo ya tiene `reading_order`. |
| **#155** | Vocabulario común con BL-R7: colección editorial ≠ lista personal ≠ vista guardada. |
| **#122** | Medir el coste real de paginación (objetos procesados), no solo el tamaño de la respuesta. |

## 6. Decisiones D1–D7: resolución propuesta por la revisión (pendiente de confirmar por el PO)

| ID | Decisión | Resolución propuesta | Afecta a |
|---|---|---|---|
| D1 | Número creado por la vinculación al deshacer | **Conservarlo siempre** en BL-R1; retirarlo es otra operación explícita y fuera de la primera versión | BL-R1 |
| D2 | Comprobante de la corrección | Exigir **persistencia duradera e idempotencia**; no decidir aún tabla nueva frente a mecanismo existente (contrato técnico y ADR si procede) | BL-R1 |
| D3 | Qué es una relación «confirmada» | Una **aceptación explícita** de la persona, con procedencia verificable de esa acción. `metadata_source='manual'` por sí solo **no basta**. Las relaciones antiguas sin evidencia **no** se marcan retroactivamente | BL-R4 |
| D4 | Dónde se guarda una discrepancia | Definir primero su **identidad, procedencia y ciclo de vida**; diferir el almacenamiento físico. «Mantener lo mío» recuerda una **propuesta concreta**, no silencia para siempre a esa fuente | BL-R4 |
| D5 | ¿BL-R1 con etiqueta MVP? | **Sí** para deshacer una vinculación equivocada y poder volver a vincular; no amplía a correcciones de M5, lotes ni mover archivos | BL-R1 |
| D6 | Kanban | La revisión proponía **no crear aún** la feature ni las tarjetas. **Superada por la orden del PO** (2026-10-18): las tarjetas #228–#236 existen en Backlog con el texto anterior | todas |
| D7 | ISBN | Estudiarlo en **#182**; **no** como identificador de serie en BL-R5 | BL-R5 |

Nota sobre D3: `metadata_source='manual'` y `metadata.vinculo` son hoy solo el **punto de partida** para hablar de
«relación manual»; la resolución propuesta exige más evidencia que eso para llamarla «confirmada».

## 7. Límites y NOT RUN

- **Plex no se ha ejecutado ni consultado por mí:** todo lo que se dice de su comportamiento es del análisis del revisor y
  debe verificarse en BL-R0.
- **Nada de esto está implementado ni medido.** Las estimaciones no están calibradas y las confianzas «Baja» son honestas.
- **No se crean tarjetas, no se cambia el orden del Kanban, no se toca `docs/BACKLOG.md`.** Publicar este documento
  tampoco autoriza código, fuentes reales, migraciones ni despliegue.
