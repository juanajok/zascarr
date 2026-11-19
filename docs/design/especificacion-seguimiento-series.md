# Especificación — «Seguir una serie: descargar números nuevos y avisar» (#993) — v0.1

> **Estado:** especificación para implementar (Opción A confirmada por el PO). Sin código ni commits. Worktree `.worktrees/spec-seguimiento`,
> rama `docs/spec-seguimiento` desde `origin/main` `11e53924` (2026-11-17). Entrada obligatoria: `docs/design/benchmark-seguimiento-series-2026-11-17.md`,
> **incluido su §12**: el disparador son las **fuentes de descarga** (foro E-links diarios `showforum=5` y Prowlarr), **no** la fecha de papel de Novedades.
> **Decisiones ya cerradas (no reabrir):** flag por serie independiente de la política; foro + Prowlarr como disparadores; Novedades solo calendario/
> matching; deseo con `origen=SEGUIMIENTO`; descarga por el ciclo existente con su backoff (#985); aviso por el `Notifier` webhook existente.
> **Este documento fija** las decisiones que el benchmark dejaba abiertas (primera pasada, origen, intervalo, dedupe, contrato de adaptadores) y
> separa lo que **no** se ha podido verificar (NOT RUN: HTML real autenticado de `showforum=5`).

## 1. Alcance / no alcance

**Dentro:** columna `Series.follow_new_issues` (+ `follow_new_issues_since`), `WishlistOrigin.SEGUIMIENTO`, migración `0047`, tabla `seguimiento_vistos`,
adaptador de listado de foro y de Prowlarr, detector de hallazgos por nombre de fichero, creación de deseos, aviso «número nuevo detectado», job periódico,
UI en la ficha y pruebas sin red + PG. **Fuera:** ningún cliente de descarga nuevo; Novedades no genera deseos; en `querer_de_serie` solo se añade que los números con deseo vivo de
seguimiento cuentan como ocupados (el índice de política no cambia); no hay búsqueda por título para decidir identidad (solo matcheo de releases detectados); no se descarga en el job; sin
dependencias nuevas; sin backfill del catálogo antiguo (eso es «completar»/«Buscar ahora»); sin UI de intervalo/cupos (config); sin validación en vivo
autenticada en esta entrega (NOT RUN §12).

## 2. Modelo y migración `0047` + `0048` (aditivas; cabeza de partida `0046`)

- **`series.follow_new_issues`**: `BOOLEAN NOT NULL DEFAULT false`. Independiente de `wishlist_policy` (`models/__init__.py:628-633`); una serie puede
  completar huecos y seguir nuevos a la vez.
- **`series.follow_new_issues_since`**: `TIMESTAMPTZ NULL`. Se fija a `now()` al pasar de `false` a `true`; al desactivar se conserva (auditoría) y al
  reactivar se vuelve a fijar. Es la **frontera de la primera pasada**: sin esto no se distingue un tema de ayer de uno de hoy.
- **`WishlistOrigin.SEGUIMIENTO = "seguimiento"`** (`models/__init__.py:211-218`): migración `ALTER TYPE wishlist_origen ADD VALUE IF NOT EXISTS 'seguimiento'`.
  Es la vía para retirar en bloque y distinguirlo en la UI; no se usa `MANUAL` (el benchmark lo permitía como deuda, pero perderíamos la distinción y la
  prueba de «nunca tocar lo manual»). Nota PG 15 (misma que `0015`): el valor añadido no se puede **usar** en la misma transacción de la migración; solo se
  añade.
- **Nota de implementación (2026-11-17):** el índice único parcial va en una
  migración aparte (`0048`) con predicado `origen <> 'manual' AND numero IS NOT NULL`
  (cubre política + seguimiento y deja fuera los manuales). No puede nombrar
  `'seguimiento'` dentro de la transacción que añade el valor al enum, y
  `origen::text` no es IMMUTABLE para un predicado de índice en PostgreSQL.
- **`seguimiento_vistos`** (tabla nueva, genérica): `id UUID PK`, `fuente VARCHAR(20) NOT NULL`, `clave VARCHAR(255) NOT NULL`, `huella VARCHAR(255) NULL`,
  `visto_en TIMESTAMPTZ NOT NULL DEFAULT now()`, `procesado_en TIMESTAMPTZ NULL`; `UNIQUE (fuente, clave)`; índice por `visto_en` para purga. Uso:
  - foro: `clave='tema:<id>'`, `huella` = última actividad del listado (texto normalizado); `procesado_en` cuando se abrió y procesó;
  - Prowlarr: `clave='release:<sha256(indexer|title|size_bytes)[:32]>'` (estable aunque cambie la URL de proxy), `huella=publish_date`; y una fila de
    rotación por serie (`clave='serie:<uuid>'`, `visto_en` de la última consulta).
  **No** guarda magnet/ed2k ni títulos: el contenido ya vive en `Wishlist`/`File`; aquí solo el estado de la fuente. Purga: `DELETE` de filas con
  `visto_en < now()-90d` al final de la pasada (config `seguimiento_retencion_dias`).
- **Índice único parcial** `uq_wishlist_seguimiento_numero` sobre `wishlist (series_id, numero) WHERE origen='seguimiento' AND numero IS NOT NULL`
  (mismo patrón que `uq_wishlist_politica_numero`, `20260929_0015:65-71`), para que dos pasadas solapadas no dupliquen el deseo.
- **Downgrade:** `DROP TABLE seguimiento_vistos`, `DROP INDEX`, `DROP COLUMN follow_new_issues_since/follow_new_issues`; el valor de enum **no se puede
  quitar** en PostgreSQL: se documenta como irreversible y se deja (una instalación que vuelva atrás no inserta `seguimiento`).
- Modelo: las dos columnas en `Series`; el enum en `WishlistOrigin`; la tabla con su `__tablename__`. Sin más cambios.

## 3. Contratos

### 3.1 Servicio `services/seguimiento.py`

- Dataclasses: `TemaForo(id: int, titulo: str, url: str, ultima_actividad: str | None)`; `Hallazgo(fuente: str, clave: str, serie_id: UUID, numero: int,
  titulo: str | None)`; `InformeSeguimiento(desde_cache: int, temas: int, hallazgos: int, deseos: int, avisados: int, errores: list[str])`.
- `async def ejecutar_pasada(db, *, ahora=None, foro=None, prowlarr=None, notifier=None) -> InformeSeguimiento` — inyectable para pruebas; **una
  transacción corta**: detecta, escribe deseos y `seguimiento_vistos`, commit, y **después** avisa.
- Funciones puras (testables sin red/BD):
  - `casar_fichero(nombre: str, serie: Series, alias: set[str]) -> int | None`: `parse_comic_filename` (`utils/naming.py:580`); rechaza
    `edition_kind is not None` (tomo/ómnibus/anual) y número no entero; compara `normalize_series_name(parsed.series)` con el título o con los alias
    locales; sin coincidencia exacta ⇒ `None` (falla cerrado). Es la misma regla que `Orchestrator._candidato_es_del_numero` (`orchestrator.py:981-1036`),
    reutilizada **sin** instanciar el orquestador.
  - `elegir_serie(parsed, series_seguidas, alias_por_serie)` → `(serie, numero)` o `None`; si dos series seguidas casan, `None` + aviso al log.
- `async def crear_deseos(db, hallazgos) -> list[Hallazgo]`: por cada `(serie_id, numero)` deduplicado:
  1. **ya en biblioteca**: `Issue`+`File` con `numero_de_grapa` == N y algún `File` no `is_missing` ⇒ nada, sin aviso;
  2. deseo vivo de cualquier origen (`WANTED`, `SEARCHING`, `DOWNLOADING`, `DOWNLOADED`, `FAILED`) ⇒ nada, sin aviso;
  3. `RETIRADO` ⇒ nada (el coleccionista lo quitó; no resucitar) y marcar visto;
  4. si no, `INSERT`/`ON CONFLICT` con `status=WANTED`, `origen=SEGUIMIENTO`, `priority=PRIORIDAD_DE_SEGUIMIENTO=6` (manual 5, política 8;
     `orchestrator.py:284`), `numero=N`, `added_at=now()`; un deseo por número aunque lo detecten foro y Prowlarr en la misma pasada.
- **Interacción con la política:** `services/politica.py::querer_de_serie` (`:120-160`) debe considerar **ocupados** los números con un deseo vivo
  `origen=SEGUIMIENTO` (igual que ya hace con los manuales por número); así la política no crea un segundo deseo `POLICY` del mismo número. Es el único
  cambio en ese fichero: el índice `uq_wishlist_politica_numero` y la retirada (siempre `WHERE origen='politica'`) no cambian. Alternativa descartada:
  un único índice por número entre orígenes (rompería la distinción y la retirada por origen). Los deseos `SEGUIMIENTO` entran en el lote `manuales`
  (`origen != POLICY`, `orchestrator.py:345`) y no consumen el cupo por hora de política; los limita `max_concurrent_downloads` y
  `seguimiento_max_deseos` por pasada.
- `async def avisar(novedades)`: `Notifier.notify_novedades(...)` **una sola vez por pasada** con los deseos creados (máximo
  `seguimiento_max_avisos`); tras commit; best effort, no revierte nada.
- No descarga ni envía nada al cliente: solo crea deseos; el ciclo existente (`process_wishlist`, backoff `_programar_reintento`/`BACKOFF_ENVIOS`
  `orchestrator.py:89-94,417-436`) los busca con Prowlarr/foro, aplica cortesía y notifica la importación por el camino ya existente.

### 3.2 Foro: `ForumScraper` (extensión, sin cliente nuevo)

- `async def listar_temas(self, foro_id: int = 5, limite: int = 50) -> list[TemaForo]`: `GET {base}/index.php?showforum={foro_id}` por `_get` (GET autenticado,
  cookies, charset y flood ya resueltos, `forum_scraper.py:522-539`); **una sola petición de listado**, con el intervalo de **lectura**
  (`forum_rate_limit=2 s`), **nunca** `_buscar_ipb`/`Search` (25 s). Parser de filas: `tr` con `a[href*="showtopic="]`; id por regex; título del anchor;
  `ultima_actividad` del texto de la fila con patrones IPB (`Hoy`, `Ayer`, `dd/mm/yyyy`, `hh:mm`) normalizado; `None` si no se reconoce. Tope de
  `limite` temas y 1 página (la primera, ordenada por actividad); enlaces resueltos con `_resolver_enlace` (H5, mismo origen, sin `s=`).
- `leer_tema(url)` ya existe (`:549`): reutiliza `_enlaces_del_tema` para `ed2k`/`magnet`; una petición por tema abierto.
- Login: uno por pasada (`login`, `:449`); si falla ⇒ 0 temas y log `seguimiento.foro_login_fallido`; nunca propagar credenciales. `ForumFloodControl` y
  `CortesiaEnEspera` cortan la fuente en esa pasada sin marcar visto (se reintenta en la siguiente).
- Sin HTML real de `showforum=5` todavía: parser y fixture son sintéticos (NOT RUN); el selector exacto se fija con una captura autenticada en la Pi antes
  de cerrar la historia.

### 3.3 Prowlarr: adaptador v1 por serie

- Sin API nueva: `ProwlarrClient.search(series.title, categories=COMIC_CATEGORIES, indexer_ids=prowlarr_indexers_seleccionados(settings))`; el helper
  (`orchestrator.py:97-105`) y `COMIC_CATEGORIES` (`orchestrator.py:82`) se mueven a `services/prowlarr.py` y se reexportan desde el orquestador, para no
  cargar el orquestador desde el job.
- Solo series seguidas, por turnos de `seguimiento_max_series_prowlarr` (rotación por la fila `fuente='prowlarr', clave='serie:<id>'` de
  `seguimiento_vistos`: la más antigua primero). Una consulta por serie y pasada como máximo.
- Filtro: `publish_date` parseable y `>= follow_new_issues_since` (si no hay fecha, se descarta: no se adivina «nuevo»); `_candidato` equivalente por
  nombre de fichero, `edition_kind` nulo y número entero; sin coincidencia exacta/no alias ⇒ fuera; nunca se usa el título del release para inventar serie.
- Si Prowlarr está apagado/sin clave ⇒ cero peticiones. Si más adelante Prowlarr expone un RSS reciente, se sustituye solo este adaptador (mismo
  `Hallazgo`/`clave`).

### 3.4 Aviso: `Notifier.notify_novedades`

`Notifier` (`services/notifier.py:51-125`) gana `async def notify_novedades(novedades: list[tuple[str, int]]) -> ResultadoEnvio`:
- `webhook_enabled` global; si está apagado o mal configurado ⇒ registra y no envía (misma política de mejor esfuerzo).
- Título: «ZascArr: N número(s) nuevo(s) detectado(s)»; cuerpo: si `webhook_incluir_nombres`, una línea por «Serie #N» (máx. `_MAX_LINEAS`), si no,
  «Abre ZascArr para ver qué series que sigues tienen números nuevos.» Nunca URL, enlace ed2k/magnet ni datos del foro.
- Una llamada por pasada, después del commit. El aviso de **importación** ya existe (`notify_imported`, `ciclo_importador.py:25`) y no se duplica: v1
  solo añade el de detección; el de importación sigue siendo el existente.

### 3.5 Config y job

`config.py` (solo entorno; sin UI en v1): `seguimiento_interval_minutes: int = Field(default=45, ge=15, le=180)`,
`seguimiento_foro_id: int = 5`, `seguimiento_max_temas: int = 10`, `seguimiento_max_series_prowlarr: int = 10`, `seguimiento_max_deseos: int = 10`, `seguimiento_max_avisos: int = 5`,
`seguimiento_retencion_dias: int = 90`. `main.py`: nuevo `_seguimiento_loop(interval)` análogo a `_orchestrator_loop` (`main.py:228-260`), arrancado en
`background_tasks`; cada vuelta abre sesión propia, llama a `ejecutar_pasada` y duerme. Sin seguidos, sin fuentes o sin acuse legal ⇒ **no hace red** y
registra el motivo; un fallo se registra y no tumba el bucle.

### 3.6 UI (ficha de serie)

- Ruta `POST /ui/series/{series_id}/seguimiento` con `follow_new_issues: bool = Form(default=False)`; `series_detail.html` incluye un nuevo parcial
  `_seguimiento_serie.html` junto a `_politica_serie.html` (`series_detail.html:256`) y un enlace de nav «Seguimiento».
- Parcial: sección «Números nuevos», `hx-post`/`hx-target`/`hx-swap="outerHTML"`, «Seguir esta serie» como checkbox + etiqueta; texto llano:
  «ZascArr mirará el foro (E-links diarios) y Prowlarr. Si aparece un número nuevo, lo buscará y te avisará. No descarga lo anterior: para eso,
  «Qué buscar». Empieza en la próxima pasada.»; estado `role="status"`; si no hay foro ni Prowlarr configurados, aviso neutro «no hay fuente de
  descarga activa»; si el aviso legal no está aceptado y se intenta activar, se devuelve el parcial sin cambiar (misma puerta que `cambiar_politica`,
  `web/series.py:872-930`, con enlace a `/ui/legal`). Desactivar siempre se permite y no borra deseos pendientes (nota: «los ya pedidos siguen en
  Deseados»). Nunca tocar `wishlist_policy` desde esta ruta.
- Tras activar: `follow_new_issues=true`, `follow_new_issues_since=now()` (solo en la transición `false→true`).

## 4. Flujo de una pasada (paso a paso)

1. `is_acknowledged`; si no, log `seguimiento.sin_legal` y salir (no se crean deseos).
2. Cargar series con `follow_new_issues=true` y sus alias activos (una consulta por lote). Si no hay, salir.
3. **Foro** (si `forum_enabled`, URL y usuario): login; `listar_temas(showforum=5)`; para cada tema hasta `max_temas`:
   - `clave=tema:<id>`; si no está en `seguimiento_vistos`, o si `huella` cambió: abrir con `leer_tema`, extraer enlaces, casar cada nombre de fichero
     contra las series seguidas; los temas con actividad anterior a `follow_new_issues_since` en la primera pasada se marcan vistos **sin** abrir ni crear
     deseo; los demás se procesan (tope), y se marca `huella/procesado_en` solo si la lectura terminó bien. Un flood/cortesía aborta el foro en esta pasada.
     En un tema **ya visto** que se actualiza, la frontera de cada serie se compara con la actividad que tenía al procesarlo (huella guardada; si no es
     una fecha, `visto_en`), nunca con la nueva: una actualización no puede crear el histórico de una serie activada después (#1017/O-2).
4. **Prowlarr** (si `prowlarr_enabled` y clave): rotación de series; `search`; filtrar por fecha ≥ since y nombre de fichero; descartar ya vistos en
   `seguimiento_vistos` (`release:<hash>`); actualizar la fila de rotación de la serie.
5. Unir hallazgos y deduplicar por `(serie_id, numero)`; crear como máximo `seguimiento_max_deseos` (el resto queda para la siguiente pasada y no se
   marca visto de más), `commit`; `Notifier.notify_novedades` tras el commit; purgar
   `seguimiento_vistos` viejos; log `seguimiento.pass_done` con contadores (sin URLs/credenciales).

## 5. Estados, mensajes y silencio

- Desactivar seguimiento detiene el escaneo de esa serie; no borra deseos ni biblioteca; los deseos de `SEGUIMIENTO` pendientes siguen el ciclo normal
  (se pueden retirar a mano en Deseados; retirar en bloque por origen queda para una segunda pasada, no v1).
- Número ya en biblioteca, deseo vivo (`cualquier origen`), `RETIRADO` o tema/release ya visto: silencio total (sin aviso). Un fallo de fuente no avisa
  y no crea nada; se reintenta en la pasada siguiente respetando el bloqueo de cortesía.
- Mensajes de UI en español llano, con la acción: activar/desactivar, aviso legal, «no hay fuentes activas», y «empieza en la próxima pasada». No se
  muestran códigos (`showforum`, `Prowlarr`, `ed2k`) en el texto de la persona salvo que sean la tarea (menú de fuentes); el botón/etiqueta no usa
  `.primary` (la ficha ya tiene acciones) y mantiene el foco estándar.

## 6. Criterios de aceptación

- **AC-1** Migración `0047` aditiva y reversible: dos columnas de `Series`, valor de enum `seguimiento` (con `tests/test_enums_bd_strenum.py` ampliado),
  tabla `seguimiento_vistos` con `UNIQUE (fuente, clave)` e índice parcial de `wishlist`; `alembic upgrade head` y `downgrade -1` verdes con Postgres real;
  pivotes `false/NULL` y ninguna otra tabla tocada.
- **AC-2** La ficha muestra «Seguir esta serie» independiente de «Qué buscar»: activar/desactivar no cambia `wishlist_policy`, y cambiar la política no
  toca `follow_new_issues` (prueba de ida y vuelta y `FakeSession`).
- **AC-3** Primera pasada: temas/ofertas con actividad/anuncio anterior a `follow_new_issues_since` se marcan vistos y **no** crean deseo; uno posterior
  sí. Prueba con dos temas fechados y con `follow_since` inyectado.
- **AC-4** Foro: un tema nuevo con un fichero de una serie seguida y número N crea **un** deseo `origen=SEGUIMIENTO`, `numero=N`, `WANTED`; el título
  del tema no se usa para casar. Segundo pase sin cambios ⇒ 0 deseos y 0 peticiones de tema (solo el listado).
- **AC-5** Tema actualizado (misma id, `huella` distinta): se reabre; si el enlace ya estaba processado no crea otro deseo; un enlace nuevo sí.
- **AC-6** Coincidencia por nombre de fichero: «Batman Vol. 3 012.cbz» casa con «Batman» seguidas por título normalizado o alias; títulos
  parecidos («Batman Beyond») no casan; dos series seguidas que casan ⇒ no se crea y se registra `ambiguo`.
- **AC-7** Especiales/tomos/anuales (`edition_kind`) y números no enteros no crean deseo. Una serie sin `comic_vine_id` puede casar por título/alias
  (no se exige identidad externa).
- **AC-8** Prowlarr: consulta solo series seguidas, una por serie y pasada, con cupo y rotación; `publish_date` anterior a `since` o ausente ⇒ no; el
  resultado con nombre de fichero que casa crea el mismo deseo una vez; Prowlarr apagado/sin clave ⇒ cero red.
- **AC-9** Sin duplicados: número con `File` no `is_missing` o deseo vivo de cualquier origen ⇒ ni deseo ni aviso; `RETIRADO` no se resucita; dos
  fuentes en la misma pasada producen un único deseo.
- **AC-10** El deseo lo busca el ciclo existente; un fallo de envío usa `next_retry_at`/backoff (#985) sin cambios; no se descarga nada en el job.
- **AC-11** Aviso: con webhook activo se envía **una** llamada por pasada (máx. `seguimiento_max_avisos`), sin URL ni enlaces; nombres solo con
  `webhook_incluir_nombres`; con webhook apagado no hay red y el deseo se crea igual; un fallo del aviso no revierte el deseo.
- **AC-12** Puerta legal: sin acuse no se crean deseos, no se envía aviso y no se abre foro/Prowlarr; activar en la UI sin acuse devuelve el parcial con
  el aviso y no cambia el flag (desactivar siempre se permite).
- **AC-13** Límites: `max_temas`, `max_series_prowlarr`, `max_deseos`, `max_avisos` y una sola lista de foro por pasada; no se usa `Search` de IPB (25 s); sin series
  seguidas o sin fuentes no hay red; el job no bloquea el arranque ni los demás bucles.
- **AC-14** Logs: `seguimiento.pass_start/done`, contadores, login/flood/legal; sin URL con `s=`, cookies, credenciales, magnet/ed2k ni cuerpos.
- **AC-15** Pruebas sin red: fixtures de `showforum`/tema (incluido un fragmento anonimizado de captura real, #1017), `MockTransport` de
  Prowlarr, `FakeSession`/PG efímera para índice y enum; `test_migracion` PG skip sin URL; suite completa verde.
- **AC-16** Interacción con la política: con un deseo vivo `SEGUIMIENTO` del número N, la política no crea otro `POLICY` para N; la retirada de política
  no toca `SEGUIMIENTO`; los deseos de seguimiento no consumen el cupo por hora de la política (prueba con `FakeSession`/PG).
- **AC-17** Documentación: enlace a esta spec y al benchmark en BACKLOG; NOT RUN declarado; sin dependencias nuevas; `querer_de_serie` solo cambia en la
  ocupación de números por `SEGUIMIENTO`.

## 7. Casos límite decididos

Tema viejo editado: `huella` distinta ⇒ se reabre, pero el deseo ya creado impide duplicar; si el tema se edita sin enlaces nuevos, no pasa nada. Título
del hilo ≠ fichero: se casa por los enlaces, nunca por el título del tema. Tema con enlaces a varios números: se procesan todos los que casen (hasta el
tope de la pasada). Tema cuyo HTML no se puede parsear: no se marca visto (se reintenta); si es un 404 persistente, se puede marcar con error tras N
pasadas (no en v1). Foro con login fallido: no se abre nada y no se notifica. Primera pasada: **empieza en el siguiente** (los temas presentes al activar
quedan como vistos si su actividad es anterior a `since`; lo posterior sí cuenta). Desactivar mientras hay una pasada en curso: la pasada termina y no se
crea más en la siguiente (flag leído al empezar). Series seguidas con un deseo manual de serie: **decisión abierta** (recomendado no crear números mientras ese deseo de serie siga vivo, para no
duplicar la búsqueda; alternativa: crear y dejar que el ciclo deduplique por número). No se fija en v1 hasta que el PO lo diga. Sin CVE/seguridad de terceros: solo se reutilizan endpoints ya configurados.

## 8. Pruebas a añadir (sin red)

`tests/test_seguimiento_casar.py` (puro): nombres reales/variantes, `edition_kind`, alias, ambigüedad, título parecido, número no entero.
`tests/test_seguimiento_foro.py`: fixture `showforum` con 3 temas (uno viejo, uno nuevo, uno actualizado), `MockTransport`/doble de `_get` y
`login`; parser, frontera `since`, huella, flood, login fallido, 0 temas; `tests/test_seguimiento_prowlarr.py`: `ProwlarrClient` falso, fechas,
rotación/cupos, apagado; `tests/test_seguimiento_pasada.py`: `FakeSession`, dedupe con File/Wishlist/RETIRADO, dos fuentes, legal gate, aviso
(`Notifier` con `MockTransport`), tope de avisos, purga; `tests/test_web_serie_seguimiento.py`: toggle independiente, textos, foco/role,
`TestClient`; `tests/test_migracion_seguimiento_pg.py`: `bd_efimera`/`alembic` (columna, enum, tabla, índice único, downgrade). Nada de red ni skips
salvo los PG ya declarados.

## 9. Despliegue y rollback

Migración `0047` antes de arrancar el código (Alembic one-shot). El flag nace `false`: **cero cambios de comportamiento** hasta que una persona active
una serie. El job arranca siempre pero no hace red sin seguidos/fuentes/acuse. Rollback: parar, `alembic downgrade 0046` (borra tabla/columnas/índice;
el valor de enum queda documentado), volver a la imagen anterior. No requiere cambios de `.env` ni de Ajustes; no hay migración de datos.

## 10. Seguridad / legal / observabilidad

Fuentes ya opt-in (foro apagado por defecto, ADR 0013); el foro exige credenciales del usuario y su lectura respeta H5 (origen, cookies solo mismo
origen, sin `s=` en logs); la puerta legal se aplica a la creación de deseos (facilitar descargas) igual que a la política. Sin nuevos terceros ni
dependencias; los avisos no incluyen nombres por defecto (tema público de ntfy). Logs de `seguimiento.*` con fuente, contadores y tipo de error —nunca
URLs, query, cookies ni cuerpos—. La tabla de vistos no guarda enlaces ni títulos.

## 11. NOT RUN (a validar antes de cerrar)

- HTML real autenticado de `index.php?showforum=5`: **validado en la Pi** al cerrar #993 (temas diarios y `ed2k`); el humo del parser queda fijado con
  un fragmento anonimizado de esa captura (`tests/fixtures/foro/showforum_real_anonimizado.html`, #1017).
- Comportamiento real de IPB ante temas actualizados (si publica «tema actualizado» o solo cambia la fecha) y ante `Search Flood Control` en lectura
  repetida del subforo.
- Prowlarr: si expone RSS reciente por indexer; v1 usa búsqueda por serie. Formato de `publishDate` y resultados duplicados reales.
- Nombres de fichero reales del foro (edición española, anuales, grapas dobles) y calidad del parser; muestra de 20–50 releases antes de confiar en el
  matcher.
- Medición en la Pi: coste de una pasada con foro (login + listado + N temas), con Prowlarr (N series) y solapamiento con el ciclo del orquestador.
- Envío real de un aviso en cada tipo de webhook y con `webhook_incluir_nombres` on/off.

## 12. Plan de build (una PR, tres cortes de commits)

1. **Fase 1 — datos y puro:** migración `0047`, enum, tabla, modelo, `seguimiento_vistos`, `casar_fichero`/`elegir_serie` y pruebas puras/PG. Sin
   comportamiento visible.
2. **Fase 2 — foro:** `listar_temas`, parser/extracción, `ejecutar_pasada` (foro), creación de deseos, `next_retry_at` intacto, pruebas con
   fixtures sintéticos; feature apagada por defecto.
3. **Fase 3 — Prowlarr + UI + aviso:** rotación/cupos, `notify_novedades`, ruta y parcial de ficha, puerta legal, `_seguimiento_loop`, AC-13/14/17,
   fixtures definitivos (con captura real) y NOT RUN revisado en la Pi.

**Decisiones que quedan al PO (no bloquean el arranque):** (a) ¿la primera pasada debe procesar el tema del día en curso en lugar de empezar en el
siguiente? (recomendado: no, para no descargar el histórico); (b) ¿exponer intervalo/cupos en Ajustes o dejarlos en `.env`? (v1: `.env`); (c) ¿retirar
automáticamente los deseos `SEGUIMIENTO` pendientes al desactivar? (v1: no, quedan y se retiran a mano); (d) ¿añadir un aviso específico de importación
para seguimiento o basta el `notify_imported` actual? (v1: el actual); (e) ¿crear deseos de seguimiento cuando ya hay un deseo manual de serie vivo?
(recomendado: no, para no duplicar búsquedas; alternativa: sí y deduplicar por número).

## 13. Cierre de la deuda #1017 (2026-11-17)

- **O-2 — cerrado.** `_procesar_foro` aplica la frontera de cada serie también a las filas ya vistas: la referencia es la actividad previa del tema
  (huella guardada; si no se puede fechar, `visto_en`). La nueva actividad solo decide si hay que reabrir. Regresión multi-serie en
  `tests/test_seguimiento_foro_pasada.py` (serie vieja + serie nueva + tema actualizado; control positivo; fallback `visto_en`).
- **O-1 — ratificado por el PO.** Se mantiene la postura actual: el foro **no** consulta `robots.txt` (M4, `FUENTES_CON_ROBOTS` sin `foro`); la
  integración es **opt-in**, con URL/credenciales del operador, aviso legal y acuse, y el job solo hace red con esa configuración. No se añade una
  consulta de robots ni cambia el comportamiento; esta ratificación cubre también el scraping periódico (no solo la búsqueda manual).
- **O-3 — cobertura cerrada.** `tests/test_seguimiento_prowlarr.py` (rotación/cupo, corte por `publish_date`, cupo de deseos, una consulta por serie),
  aviso único y máximo 5 en `tests/test_seguimiento_pasada.py`, AC-16 explícito y humo del parser con el fixture real anonimizado.
- **O-4 — sigue abierta como deuda menor.** `crear_deseos` no usa `ON CONFLICT`; el job es secuencial y de un solo worker, sin cambio en esta deuda.
