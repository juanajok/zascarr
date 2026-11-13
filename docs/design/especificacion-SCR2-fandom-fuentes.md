# SPEC: Fandom (DC Database y Marvel Database) como fuente de fichas y arcos — SCR2 (#703) — v0.1

> **Estado:** borrador de especificación (spec, 2026-11-13). **No autoriza fusionar.** Fija qué cubre
> la integración en los tres niveles que pidió el PO (serie, número e issue, arcos/orden de lectura),
> con criterios verificables, y separa lo que está hecho en el árbol de trabajo de lo que falta.
> Solo documento: no se ha tocado código, ni migraciones, ni se ha hecho commit.
>
> **Base contrastada:** `main` en `17a5995e` **más los cambios sin commitear** de la integración,
> leídos y ejecutados el 2026-11-13 a las 13:24 (hora local). La rama `feat/fandom-fuentes` apunta a
> `8f90aa4b` y **no** contiene estos cambios. Cuando este documento dice «hecho», significa «hecho en
> el árbol de trabajo revisado», no «fusionado».
>
> **Documentos de referencia:** no están en `main`. Viven en la rama `docs/scraping-v2`:
> `docs/estudio-scraping-fuentes-v2.md` y `docs/ANEXOS-IMPLEMENTACION-ZASCARR-V2.md` (`db200c35`),
> la épica SCR en `docs/BACKLOG.md` (`c22fa831`, enlaces a issues `#702`–`#706` en `573149a2`) y
> `docs/design/informe-fase0-scraping-2026-11-13.md` + `docs/adr/0018-cache-http-y-fuentes-externas-lectura.md`
> (mismo commit). Esta spec los cita por su contenido, **no como si ya estuvieran en `main`**.
>
> **Insumo de benchmarking:** `docs/design/benchmark-SCR2-fandom-fuentes.md` (ficha §13 de CLAUDE.md,
> en el árbol sin commitear). Esta spec **no lo sustituye ni lo aprueba**: lo usa como evidencia y
> remite a él para las decisiones de adoptar/adaptar/descartar.
>
> **Notación:** requisitos y criterios con palabras clave en español (CUANDO, SI/ENTONCES, DONDE);
> identificadores de código en inglés; textos de cara a la persona, en español llano (CLAUDE.md §6).
> «Issue» = número individual de una serie; no es un tomo recopilatorio. Los estados son
> **Hecho / Parcial / Falta**, y `[B]` marca lo que bloquea la fusión.
>
> **Caducidad:** 2027-01-12 (~60 días), o antes si cambia MediaWiki, el estudio o el contrato del
> enricher.

---

## 0. Resumen ejecutivo

**Qué pide la historia.** SCR2 dice, en una frase: que DC Database y Marvel Database aporten fichas y
portadas *cuando la consulta lo pida*, con **doble enlace visible CC-BY-SA 3.0** (artículo y
licencia), portadas cacheadas en local, fuentes apagadas por defecto, `LEGAL.md` actualizado y
prioridad en el enricher según la decisión del PO. El PO, además, lo pidió «a nivel de issue, serie y
arcos/orden de lectura».

**Qué hay hoy en el árbol.** Un cliente MediaWiki real (`services/fandom.py`) que solo usa
`/api.php`, con `missingtitle` y `maxlag` tratados; una cadena de fuentes para `american`/`british`
(Comic Vine → DC Database → Marvel Database) con emparejamiento exacto por título —**ratificada por el
PO el 2026-11-13: Comic Vine prevalece sobre Fandom, que queda como respaldo**—; enriquecimiento de
número (fecha, sinopsis, título de historia, créditos, portada) **solo para series identificadas por
Fandom**; y arcos de **DC Database** volcados a `story_arcs`/`story_arc_issues.reading_order`, que la
vista ya existente `/ui/arcos` muestra sola. `LEGAL.md` tiene fila nueva; el hash de
`services/legal.py` versiona la aceptación sin paso manual.

**Qué falta, y es bloqueante.** La migración 0035 añade `fandom_dc_slug`/`fandom_marvel_slug` a
`series` e `issues`, pero **el ORM no las mapea** en `models/__init__.py` (solo añade los valores del
enum). El enricher consulta esas columnas en su primer `SELECT` (`enricher.py:415-416`), así que
**todo ciclo de enriquecimiento revienta** con `AttributeError`, tenga o no Fandom encendida. Verificado: `tests/test_enricher.py` da **17 fallos y 36 aprobados**; los 21 tests de
`tests/test_fandom.py` pasan porque solo prueban el cliente y `_sources_for`, nunca el servicio
contra el ORM. Además: la fecha DC mezcla día de venta con mes de portada, la atribución CC-BY-SA no
es visible en la ficha y `procedencia.NOMBRE_DE_FUENTE`/`ID_FIELDS` no conocen las fuentes Fandom.

**Veredicto:** el diseño encaja con los tres niveles pedidos, pero **la integración no es apta para
fusionar en el estado revisado** (AC-SCR2-01 a AC-SCR2-05 en rojo). La cobertura real,
una vez arreglados los bloqueantes, sería: **serie** completa (identificación + metadatos + portada),
**número** completo solo para series identificadas por Fandom, y **arcos** solo DC y solo con los
números que ya están en la biblioteca local. Las guías externas de lectura (SCR3) no están, y Marvel
no tiene arcos.

---

## 1. Los tres niveles del PO, traducidos

| Nivel pedido | Qué significa en ZascArr | Dónde vive en el árbol |
|---|---|---|
| **Serie** | Identificar la serie contra el «volume» de la wiki, guardar su identidad por fuente y completar sinopsis, portada, años y nº total | `fandom.get_volume` + cadena de `enricher._sources_for` + `_find_fandom_match` + `_apply_series_match` |
| **Issue (número)** | Para series ya identificadas por Fandom, completar fecha, sinopsis, título de historia, créditos y portada de cada número | `fandom.get_issue` + `enricher._enrich_issues_fandom` + `_apply_credits_fandom` |
| **Arcos / orden de lectura** | Volcar los arcos que declara la ficha de un volumen de DC con sus números en orden, sin crear modelo nuevo | `fandom.get_arc` + `enricher._enrich_arcs_fandom`/`_upsert_arc` sobre `story_arcs` y `story_arc_issues.reading_order` (BL-C4) |

**Lo que el nivel «arcos» NO es en SCR2.** Las guías curadas de `comicbookreadingorders.com` y
`continuityguide.net`, con su normalizador puro y su posible tabla `ReadingOrder`, son **SCR3** (y
`docs/estudio-scraping-fuentes-v2.md` Fase 3). SCR2 usa los arcos que declara la propia wiki de DC; no
importa guías externas y no decide el modelo de producto de las órdenes de lectura (§7, D-2).

---

## 2. Evidencia verificada en el árbol revisado

| # | Hecho | Evidencia | Comprobación |
|---|---|---|---|
| E-1 | El cliente no raspa HTML: solo `/api.php`, con `format=json`, `formatversion=2`, `redirects=1`, `maxlag=5` | `services/fandom.py:459-492` | Lectura de código |
| E-2 | `missingtitle` en HTTP 200 → `None`; `maxlag` → bloqueo compartido y excepción transitoria | `fandom.py:71-73, 477-492, 629-640`; tests `test_missingtitle_es_none`, `test_maxlag_lanza_y_bloquea_cortesia` | 21 tests de `tests/test_fandom.py` **aprobados** |
| E-3 | La portada se resuelve por `imageinfo` (`iiprop=url`) y el host `static.wikia.nocookie.net` está en la lista blanca y con intervalo propio | `fandom.py:516-529`; `utils/url_portada.py:50-56`; `utils/cortesia.py:130-131` | Lectura + test del cliente |
| E-4 | Cadena de fuentes para `american`/`british`: Comic Vine → DC → Marvel (ratificado: CV prevalece); el resto mantiene su fuente única | `enricher.py:541-556`; test `test_cadena_de_fuentes_american_con_fandom` | Test aprobado |
| E-5 | **El ORM no mapea las columnas de 0035.** `getattr(Series, "fandom_dc_slug")` → ausente; `Issue` idem | `models/__init__.py` (solo enum en `:282-287`); migración `alembic/versions/20261113_0035_fandom_slugs.py:23-37` | Comprobado con el intérprete del venv de pruebas |
| E-6 | Consecuencia de E-5: cualquier `enrich_pending()` falla antes de tocar la BD, porque el `SELECT` de series usa esas columnas | `enricher.py:415-416` | `PYTHONPATH=src .tmp-test-venv/bin/python -m pytest tests/test_enricher.py -q` → **17 failed, 36 passed**; el fallo es `AttributeError` en `enricher.py:415` (no se ejecutó la suite completa: la corre QA) |
| E-7 | El enricher crea arcos y enlaces de lectura con la marca `metadata_["fandom_arcos_intentado"]` para no releer la ficha | `enricher.py:874-989` | Lectura de código; **sin prueba** |
| E-8 | `/ui/arcos` ya lista cualquier `StoryArc` con sus números, sin cambio de plantilla | `services/arcos.py:55-75`; `web/arcos.py:38-43` | Lectura de código |
| E-9 | `LEGAL.md` tiene fila de Fandom (texto CC-BY-SA 3.0, portadas *fair use*, `/api.php`, 1,5 s, apagadas) | `src/zascarr/LEGAL.md:107` | Lectura; `legal_version` es el hash del fichero (`services/legal.py:41-45`), no hay constante que subir |
| E-10 | Interruptores nuevos apagados por defecto, en Ajustes y en ajustes en caliente | `config.py:100-103`; `services/runtime_settings.py:44-48`; `web/ajustes.py:125-129,274-290`; `templates/ajustes.html:41-48` | Lectura de código |
| E-11 | La atribución CC-BY-SA **no** está en la UI: la nota de la ficha es genérica y no enlaza a Fandom ni a la licencia | `templates/_legal_disclaimer.html:21-27`; uso en `templates/series_detail.html:48` | Lectura de código |
| E-12 | `procedencia` no conoce Fandom: sin nombre legible ni campo de identidad | `services/procedencia.py:48-62` | Lectura de código |
| E-13 | El plan de enriquecimiento por campo (#128) no consulta Fandom: solo CV/AniList/Tebeosfera | `services/enriquecimiento_plan.py:254-272,347-354` | Lectura de código |
| E-14 | `/api/health` no lista las fuentes Fandom en `fuentes` (B8 solo cubre CV/AniList/Tebeosfera/GCD) | `api/health.py:464-469` | Lectura de código |
| E-15 | El CDN de portadas no está en `HOST_DE_FUENTE_PARA_PORTADAS`: apagar Fandom **no** corta la descarga de una portada suya ya guardada | `utils/cortesia.py:135-153`; gate en `utils/url_portada.py:249-250` | Lectura de código |
| E-16 | `tests/test_fandom.py` no cubre el servicio; `test_enricher.py` no tiene casos Fandom; no hay prueba de la migración 0035 ni de los defaults nuevos | `tests/test_fandom.py`; `tests/test_enricher.py`; `tests/test_fuentes_apagadas_por_defecto.py:11` (`CAMPOS` de cuatro); `tests/test_migracion_fuentes_pg.py` (solo 0020) | Lectura + ejecución de E-6 |
| E-17 | La documentación citada por el código no está en `main`/`feat/fandom-fuentes` | `fandom.py:3,15`; docstring de la migración 0035 | `git ls-tree` y búsqueda en `docs/` |

**No ejecutado en esta revisión:** suite completa, tráfico real, peticiones en vivo nuevas, migración
sobre Postgres (no hay `TEST_DATABASE_URL` configurada para esta revisión). Los datos «en vivo» que se
citan vienen del `informe-fase0-scraping-2026-11-13.md` y de la ficha de benchmarking, no se han
reverificado aquí.

---

## 3. Cobertura por nivel: nivel → capacidad → estado → riesgo

### 3.1 Nivel serie

| Capacidad | Estado | Evidencia / dónde | Riesgo si queda así |
|---|---|---|---|
| Identidad por wiki (`fandom_dc_slug`, `fandom_marvel_slug`) | **Falta [B]** | Migración 0035 sí; ORM no (`models/__init__.py`); el enricher ya las usa | E-5/E-6: el ciclo del enricher entero cae; QA no puede pasar |
| Búsqueda y emparejamiento conservador (título base normalizado exacto; año ±1) | **Parcial** | `enricher.py:641-675`; `_pick_by_year` `:678-687` | Con un único candidato exacto se acepta **sin mirar el año** (`_pick_by_year` devuelve el primero si `len == 1` o no hay año destino): puede atar «Batman» a otro volumen; no hay prueba de integración |
| Cadena CV → DC → Marvel para `american`/`british` | **Hecho y ratificado** (PO, 2026-11-13: Comic Vine prevalece; Fandom, respaldo) | `enricher.py:542-556,445-500` | Fandom nunca es fuente primaria; un fallo transitorio de CV hace gastar 2 búsquedas más; orden DC→Marvel fijo (una serie Marvel no-CV gasta una búsqueda en DC) |
| Marcar intento solo cuando se han probado todas las fuentes de la tradición; no marcar si fallo transitorio | **Hecho** | `enricher.py:493-500` | Un error de payload desconocido (`FandomPayloadError`) se trata como transitorio y **reintenta cada ciclo para siempre** (no entra en la negativa de 30 días) |
| Sinopsis, portada, `total_issues`, `start_year`/`end_year` | **Parcial** | `enricher.py:558-579,641-675`; `fandom.py:543-579` | `total_issues` de Marvel solo si la plantilla de volumen lo declara (no verificado en vivo); `description` sale del primer párrafo y puede ser `None`; `start_year`/`end_year` solo rellenan huecos (no corrigen un año mal puesto en el alta) |
| Portada: URL por `imageinfo` + caché local en `covers/externa/` | **Parcial** | `enricher.py:570`, `web/series.py:1355-1356`; host/intervalo en `url_portada.py:50-56`, `cortesia.py:122-131` | El gate «fuente apagada no recibe portadas» no aplica a este CDN (E-15): con Fandom apagado se puede seguir descargando una portada suya; no hay prueba del flujo completo |
| Apagada por defecto + Ajustes + ajuste en caliente | **Hecho** | E-10 | Sin prueba de los defaults nuevos ni de que apagarla deje «cero tráfico» (B8) |
| Descubrir (`/ui/descubrir`, C0) | **Falta (fuera del alcance declarado de SCR2)** | `services/discovery.py` no tiene rama Fandom | El PO podría esperarlo; si se quiere, es historia aparte (misma pregunta que D-9) |
| Plan de enriquecimiento por campo (#128) | **Falta** | E-13 | La vista previa manual de una serie no puede proponer datos de Fandom; el coleccionista no puede «revisar y aplicar» lo que el ciclo automático haría |
| Procedencia y atribución en la ficha | **Falta [B] legal** | E-11, E-12 | `LEGAL.md` exige enlace al artículo **y** a CC-BY-SA 3.0; hoy la ficha dice «fuentes de terceros (Comic Vine, AniList, Tebeosfera)» y no enlaza nada de Fandom |
| Estado (`/api/health`) | **Falta** | E-14 | B8 dejó el patrón: las fuentes nuevas se ven en `/api/health.fuentes`; las Fandom no aparecen (el snapshot de cortesía de Ajustes sí las lista, `cortesia.py:116-118`) |
| ADR y documentación | **Falta** | ADR 0018 solo existe en `docs/scraping-v2`; README sigue diciendo «cuatro fuentes» (`README.md:391-397`); el código cita documentos que no están (E-17) | Una fusión sin el ADR ni los docs deja referencias rotas y una decisión sin registrar; CLAUDE.md §3.1.5 y §13 |

### 3.2 Nivel issue (número)

| Capacidad | Estado | Evidencia / dónde | Riesgo si queda así |
|---|---|---|---|
| Identidad por número (`issues.fandom_*_slug`, UQ por wiki) | **Falta [B]** | Migración 0035 sí; ORM no | Mismo bloqueo que la serie; sin columnas no hay ni `INSERT` ni caché negativa por número |
| Página del número «`<volumen> <número>`» | **Hecho** (construcción) | `enricher.py:794-795` | Anuales, especiales y números con formato raro (`1/2`, `12.NOW`, `1A`) usan otra convención de título: la página no existe y el número queda en negativa de 30 días |
| Fecha | **Hecho** (decisión PO 2026-11-13: fecha de **venta**) | `fandom.py` usa `Pubmonth`/`Pubyear`+`Day` (venta) y deja `Month`/`Year` como respaldo; `comic_vine.py` añade `store_date` y el enricher lo prefiere con `cover_date` como respaldo; etiqueta «Fecha de publicación» en `services/ficha_numero.py:35` | Batman #404 en vivo: venta 1986-10-21 (portada 1987-02) — regresión con esos parámetros reales; la portada, si se quiere, irá a `metadata_` en otra historia |
| Sinopsis, título de historia y créditos | **Hecho** (solo si el número no tiene ya créditos) | `fandom.py:601-608`; `enricher.py:829-871` | Marvel `Synopsis1`/`StoryTitle1` no verificados en vivo; créditos por nombre reutilizan el creador existente (misma convención que CV) |
| Portada del número | **Parcial** | `enricher.py:825-826`; la ficha del número pinta la portada del **archivo**, no la de la fuente (`templates/issue_detail.html:8`; `services/portada_numero.py`) | `issues.cover_url` se guarda y no se muestra ni se cachea: dato muerto salvo que otra vista lo use (hoy no) |
| No pisar lo manual ni lo bloqueado (`locked_fields`) | **Hecho** | `enricher.py:816-830` (patrón de CV) | Correcto por diseño; sin prueba específica de Fandom |
| Caché negativa por número (30 días) | **Hecho** (heredado) | `enricher.py:773-781,811-815` | La «negativa corta» que pide SCR2 (12 h) no existe; un fallo de maquetación se recuerda un mes |
| Solo se enriquece el número si la serie la identificó Fandom (no CV) | **Hecho** | `enricher.py:771-773` | Si CV identifica la serie, sus números siguen siendo solo de CV; Fandom nunca completa huecos de números de una serie CV. Es una decisión de producto que debe ratificarse (D-1) |

### 3.3 Nivel arcos / orden de lectura

| Capacidad | Estado | Evidencia / dónde | Riesgo si queda así |
|---|---|---|---|
| Arcos declarados por la plantilla de volumen de **DC** (`StoryArcs`) | **Hecho** (sin commitear) | `fandom.py:563-567`; `enricher.py:874-938` | Solo el campo de la plantilla de volumen: los `StoryArc` de la plantilla de **número** no se leen; si la wiki deja de declararlos, no hay arcos y queda la marca de «intentado» |
| Arcos en **Marvel** | **Falta por diseño actual** | `fandom.py:565-567` (comentario explícito: la plantilla de Marvel no declara `StoryArcs`) | Se cumple «Marvel sin arcos», pero debe quedar escrito como límite, no como bug. Si el PO lo quiere, es otra vía (páginas de arco de Marvel o CV) |
| Números del arco en `story_arc_issues.reading_order` | **Parcial** | `enricher.py:940-989` | Solo se enlazan números **que ya existen** en la biblioteca; un crossover con series aún no identificadas por Fandom se queda fuera. El `reading_order` cuenta solo los enlazados (colapsa huecos): 1..N de lo que hay, no la posición real en la saga |
| Fuente del orden | **Parcial** | `fandom.py:610-626` | Usa la sección `Issues`; si no existe, cae a «todos los enlaces a números del artículo» en orden de aparición (puede incluir navegación/«related» y desordenar) |
| Idempotencia y tope por ciclo (8 arcos) | **Hecho** (según código) | `enricher.py:753,913,935-938` | Sin prueba: un segundo ciclo no debe duplicar `StoryArc` ni `StoryArcIssue`, y un arco con más de 8 no debe cerrarse como completo |
| Visibilidad en `/ui/arcos` | **Hecho** (reutiliza BL-C4) | `services/arcos.py`, `web/arcos.py` | El arco aparece, pero sin `is_crossover`, sin `universe_id` y sin enlace a la fuente; el texto (`description`) es prosa de Fandom y **no lleva atribución** |
| Deduplicación de arcos | **Parcial** | `enricher.py:942-951` (por `title` exacto) | Títulos genéricos o repetidos entre editoriales pueden fusionar arcos distintos en una fila; el título sale del **nombre de página**, no del campo `Title` de la plantilla |
| Guías externas de lectura (Reading Orders, Continuity Guide, Herald) | **Falta** (SCR3/SCR5, fuera de SCR2) | No hay extractores ni `reading_order_resolver.py` | No se promete; el modelo de producto (`ReadingOrder`) sigue abierto (D-2) |

### 3.4 Transversal

| Capacidad | Estado | Evidencia / dónde | Riesgo si queda así |
|---|---|---|---|
| Corte de cortesía propio por wiki (1,5 s, 2 intentos, bloqueo `maxlag` compartido) | **Hecho** | `cortesia.py:237-242`; `config.py:100-103`; `fandom.py:480-492` | El coste real por serie puede ser alto (ver R-2); el intervalo no se puede cambiar desde Ajustes (solo el `.env`) |
| `robots.txt` y caché HTTP condicional (Fase 1 / SCR1) | **Falta** | No existen `utils/robots.py` ni `utils/cache_http.py`; `pyproject.toml` no tiene `protego` | Se ha implementado SCR2 **antes** que SCR1, contra el orden propuesto. Para `/api.php` el riesgo es bajo (API abierta y `robots.txt` 403 ⇒ «sin restricciones» según RFC 9309), pero la «negativa corta» de SCR2 no existe y cada apertura de ficha repite consultas |
| Doble enlace legal CC-BY-SA 3.0 (artículo + licencia) | **Falta [B]** | E-11 | Incumple `LEGAL.md` mientras la fuente pueda aportar texto visible |
| `LEGAL.md` actualizado | **Hecho** | E-9 | El hash invalida la aceptación previa solo, sin paso manual |
| Pruebas de integración (servicio + ORM + migración) | **Falta** | E-16 | Los 21 tests del cliente dan falsa sensación de cobertura; el enricher está en rojo |
| Defaults apagados y cero tráfico al apagar | **Parcial** | E-10; `test_fuentes_apagadas_por_defecto.py` no incluye Fandom | Regresión de ADR 0013 sin red de seguridad |
| Docs v2, ADR 0018 y épica SCR en `main` | **Falta** | E-17 | Los enlaces del código mueren y la decisión no queda registrada |

---

## 4. Criterios de aceptación verificables

Cada criterio dice **cómo se comprueba** y **estado en el árbol revisado**. Los que bloquean la
fusión van marcados `[B]`.

**Bloqueantes técnicos y legales**

- **AC-SCR2-01 `[B]` — El ORM mapea las columnas de 0035.** DADO el modelo cargado, CUANDO se evalúa
  `Series.fandom_dc_slug`, `Series.fandom_marvel_slug`, `Issue.fandom_dc_slug` e
  `Issue.fandom_marvel_slug`, ENTONCES existen como columnas `String(255)` únicas, y la migración
  0035 sube y baja en una BD efímera. *Verificación:* prueba de esquema (ORM) + prueba de migración
  con `tests._pg.bd_efimera()` (patrón `test_migracion_fuentes_pg.py`). *Hoy:* **falla** (E-5).
- **AC-SCR2-02 `[B]` — El ciclo del enricher no revienta y es idempotente.** CUANDO corre
  `EnrichmentService.enrich_pending()` con cualquier combinación de fuentes (todas apagadas, solo
  Fandom, Fandom + CV), ENTONCES no lanza `AttributeError` y procesa los lotes de serie, número y
  arco sin duplicar filas en un segundo ciclo. *Verificación:* prueba de integración con
  `FakeSession`/Postgres real, una por combinación; regresión nombrada por el mecanismo (columna sin
  mapear). *Hoy:* **falla** (E-6).
- **AC-SCR2-03 `[B]` — Atribución visible de Fandom.** CUANDO la ficha de una serie, de un número o
  de un arco muestra texto o metadatos cuyo origen es Fandom, ENTONCES aparecen **dos enlaces**: al
  artículo original (`https://<wiki>/wiki/<página>`) y a
  `https://creativecommons.org/licenses/by-sa/3.0/`, y la portada **no** se etiqueta CC-BY-SA.
  *Verificación:* `TestClient` sobre la ficha con una serie marcada `fandom_dc`/`fandom_marvel`;
  aserción de ambos `href` y de que no hay la etiqueta CC-BY-SA junto a la portada. *Hoy:* **falla**
  (E-11/E-12).
- **AC-SCR2-04 `[B]` — La fecha DC sale de una sola convención.** DADO un `Comic Template` de DC con
  `Day`/`Month`/`Year` y `Pubmonth`/`Pubyear`, CUANDO se enriquece el número, ENTONCES
  `Issue.release_date` es la fecha de **venta** (decisión del PO del 2026-11-13, D-5): Fandom la saca
  de `Pubmonth`/`Pubyear` + `Day` y Comic Vine de `store_date` (con `cover_date` solo como
  aproximación si falta la de venta); la etiqueta visible dice «Fecha de publicación». *Verificación:*
  regresión con los parámetros reales de Batman #404 (`Day=21`, `Month=2`, `Year=1987`,
  `Pubmonth=10`, `Pubyear=1986` → 1986-10-21) y con `store_date`/`cover_date` de Comic Vine.
  *Hoy:* **pasa**.
- **AC-SCR2-05 `[B]` — `LEGAL.md` y la UI cuentan lo mismo.** DADO que la fila de Fandom exige enlace
  al artículo y a la licencia, CUANDO se revisa la superficie donde se muestra el dato, ENTONCES no
  queda ninguna vista que enseñe texto de Fandom con un aviso genérico. *Verificación:* revisión
  cruzada de `LEGAL.md:107` con las plantillas tocadas + la prueba de AC-03. *Hoy:* **falla**.

**Serie**

- **AC-SCR2-06 — Emparejamiento conservador.** DADO un título de serie y los resultados de la wiki,
  CUANDO se busca el volumen, ENTONCES solo se acepta la página cuyo **título base normalizado**
  coincide exactamente y, si hay varios candidatos, desempata el año (`±1`); si no hay coincidencia
  exacta, no se enriquece. *Verificación:* pruebas con candidatos reales (exacto único, varios
  exactos con año, solo coincidencia parcial, página de número que no debe confundirse con volumen).
  *Hoy:* el criterio está, pero **sin prueba de integración** y con la excepción del único candidato
  aceptado sin año (R-3).
- **AC-SCR2-07 — Cadena de fuentes y fuentes apagadas.** DADO `american`/`british`, CUANDO CV, DC o
  Marvel están desactivadas, ENTONCES el enricher no instancia ni llama a las apagadas (cero
  tráfico), y solo marca `enrichment_attempted_at` cuando ha probado todas las activas sin match.
  *Verificación:* pruebas B8 extendidas a Fandom con cliente inyectado que registra llamadas.
  *Hoy:* el código lo hace; **falta la prueba**.
- **AC-SCR2-08 — Datos de serie sin pisar lo humano.** DADO un campo bloqueado o una serie manual,
  CUANDO se aplica el match de Fandom, ENTONCES no se toca. *Verificación:* pruebas de
  `locked_fields`/`manual` con un match Fandom simulado. *Hoy:* el patrón existe; **falta prueba**.
- **AC-SCR2-09 — Portada externa cacheada, servida en local y con la fuente apagada respetada.** DADO
  `series.cover_url` con URL del CDN de Fandom, CUANDO se pide la portada, ENTONCES se descarga una
  vez a `covers/externa/<serie>.jpg` con cortesía de host y se sirve local; si la fuente Fandom está
  apagada, **no** se descarga (o la excepción está documentada y aprobada, D-7). *Verificación:*
  prueba de la cascada con `MockTransport`/transport falso + prueba del gate de fuente apagada.
  *Hoy:* descarga y caché sí; gate **no** (E-15).
- **AC-SCR2-10 — Defaults apagados.** CUANDO se construye `Settings(_env_file=None)`, ENTONCES
  `fandom_dc_enabled` y `fandom_marvel_enabled` son `False`, y Ajustes los muestra apagados y
  persistibles. *Verificación:* ampliar `CAMPOS` en `tests/test_fuentes_apagadas_por_defecto.py` y
  la prueba de la tarjeta de Ajustes. *Hoy:* **falta la prueba** (el código es correcto).

**Issue**

- **AC-SCR2-11 — Número enriquecido desde Fandom, sin pisar.** DADO un número de una serie
  identificada por Fandom, CUANDO se enriquece, ENTONCES se rellenan fecha, sinopsis, título de
  historia, créditos y `fandom_*_slug` solo en huecos, y no se toca nada manual/bloqueado.
  *Verificación:* prueba de integración con wikitext de fixture y `FakeSession`/Postgres real.
  *Hoy:* implementado; **sin prueba**.
- **AC-SCR2-12 — Número sin página se comporta, no rompe.** DADO un número que la wiki no tiene
  (anual, especial o formato raro), CUANDO se consulta, ENTONCES se devuelve sin error, se marca el
  intento (negativa de 30 días) y el ciclo sigue con el resto. *Verificación:* prueba con
  `missingtitle` real (HTTP 200) para ese número. *Hoy:* comportamiento heredado; **sin prueba de
  Fandom**; y la negativa larga es un riesgo aceptado (R-4).
- **AC-SCR2-13 — Portada del número: visible o declarada fuera de alcance.** Si SCR2 promete portadas
  a nivel de número, CUANDO se abre la ficha del número, ENTONCES se ve la portada de la fuente (o la
  del archivo con la de la fuente como alternativa), servida en local; si no, se documenta
  expresamente que solo la serie usa portada externa. *Verificación:* revisión de la ficha +
  prueba de que `issue.cover_url` tiene consumidor. *Hoy:* **no visible** (§3.2).

**Arcos**

- **AC-SCR2-14 — Arcos de DC volcados en orden e idempotentes.** DADO un volumen DC con `StoryArcs` y
  números locales, CUANDO corre el enricher, ENTONCES existen los `StoryArc` (≤8 por ciclo) con
  `metadata_["origen"]="fandom_dc"`, y los `StoryArcIssue` enlazan solo números locales con
  `reading_order` 1..N en el orden declarado, sin duplicados en una segunda pasada.
  *Verificación:* prueba con Postgres real (accesos directos a `story_arcs`/`story_arc_issues`) y
  fixture de wikitext de arco. *Hoy:* implementado; **sin prueba**.
- **AC-SCR2-15 — Marvel sin arcos, declarado.** DADO un volumen de Marvel, CUANDO se enriquece,
  ENTONCES no se crean arcos y no es un error; queda escrito que Marvel no los aporta por esta vía.
  *Verificación:* prueba con plantilla Marvel de fixture. *Hoy:* el código lo hace; **falta prueba**.
- **AC-SCR2-16 — Arcos visibles y atribuidos.** CUANDO se abre `/ui/arcos/<id>` para un arco de
  origen Fandom, ENTONCES se ve el nombre, sus números y la atribución de AC-03 (enlace al artículo
  del arco + licencia). *Verificación:* `TestClient` con un arco sembrado. *Hoy:* se ve el arco; la
  atribución **falta**.

**Transversal**

- **AC-SCR2-17 — Estado y procedencia conocen Fandom.** CUANDO se consulta `/api/health` y la ficha
  de una serie enriquecida por Fandom, ENTONCES las dos fuentes aparecen con su estado en
  `fuentes`/Ajustes y la ficha muestra «DC Database»/«Marvel Database» como origen y su identificador.
  *Verificación:* ampliar `NOMBRE_DE_FUENTE`/`ID_FIELDS` y las pruebas de health/procedencia. *Hoy:*
  **falla** (E-12/E-14).
- **AC-SCR2-18 — Errores lógicos no envenenan el ciclo.** DADO un `error` de MediaWiki desconocido o
  un JSON con forma inesperada, CUANDO se procesa, ENTONCES se registra sin URL y no se rompe el
  ciclo; un error desconocido no se reintenta en bucle infinito (o se acota con la negativa corta de
  SCR1). *Verificación:* prueba con payloads hostiles (`internal_api_error`, `maxlag`, JSON roto,
  404/5xx). *Hoy:* `FandomPayloadError` cae en el genérico «transitorio» y **reintenta cada ciclo**
  (R-5).
- **AC-SCR2-19 — Documentación coherente.** CUANDO se fusiona SCR2, ENTONCES están en `main` el
  estudio, los anexos, el informe de Fase 0, el ADR 0018, la épica SCR y esta spec; `README.md` cita
  las fuentes Fandom y el código no remite a ficheros ausentes. *Verificación:* `git ls-tree` de los
  ficheros citados + búsqueda de referencias rotas. *Hoy:* **falta** (E-17).
- **AC-SCR2-20 — Pruebas sin red y con fixtures reales.** CUANDO corre la suite, ENTONCES toda prueba
  de Fandom usa `httpx.MockTransport` y fixtures recortados de wikitext real (sin tráfico), y la suite
  completa queda en verde sin `TEST_DATABASE_URL` salvo las marcadas. *Verificación:* ejecución de la
  suite por QA. *Hoy:* el cliente cumple; el servicio no tiene pruebas.

---

## 5. Huecos reales (sin inflarlos)

1. **La migración 0035 va por delante del ORM.** Es el único hueco que hoy rompe el enricher entero;
   los demás son cobertura o cumplimiento. No es un fallo de diseño del cliente.
2. **Anuales y especiales sin página estándar.** La página del número se construye como
   «`<volumen> <número>`»; la convención de anuales de DC Database es un volumen propio
   («Batman Annual Vol 1 1») y los `Issue.issue_number` de la biblioteca pueden ser `Annual 1`,
   `1`, `1.5`… Cuando no casa, se marca intento y se recuerda **30 días**. No se promete soporte;
   debe declararse límite y decidir si se aborda (D-8).
3. **Marvel no aporta arcos por esta vía.** Su plantilla de volumen no declara `StoryArcs`; el
   código lo deja explícito. No es un bug: es el límite de la vía elegida.
4. **Los arcos solo enlazan números que ya están en la biblioteca.** Un crossover con una serie que
   ZascArr no tiene (o no ha identificado por Fandom) se omite; el `reading_order` es 1..N de lo
   enlazado, no la posición real en la saga. Coherente con BL-C4, pero hay que decirlo.
5. **La fecha DC no es ni de portada ni de venta.** Ver AC-04; afecta a la ficha del número y a la
   ordenación por fecha, no a la identidad.
6. **Atribución CC-BY-SA ausente.** `LEGAL.md` ya la exige; la UI no la tiene. Es el hueco legal real,
   más importante que cualquier cosmética.
7. **`procedencia` y `/api/health` no conocen las fuentes.** Una serie enriquecida por Fandom se
   presenta como «una fuente externa» y su identificador no aparece. No rompe nada, pero desperdicia
   el trabajo de identidad.
8. **El plan de enriquecimiento por campo y Descubrir no usan Fandom.** Fuera del alcance declarado
   del estudio (que solo integra el enricher), pero son dos sitios donde el coleccionista esperaría
   verla. Decisión de producto (D-9).
9. **La «negativa corta» de SCR2 no existe sin SCR1.** Hoy, un `missingtitle` se recuerda 30 días en
   la tabla de enriquecimiento; con `http_cache` serían 12 h. No es un fallo de Fandom, es el orden de
   las historias (D-4).
10. **El coste por serie es mayor de lo que sugiere el estudio.** `get_volume` hace 2–3 peticiones y
    `_find_fandom_match` abre hasta 2 candidatos; con 1,5 s de intervalo el peor caso ronda ~10 s por
    serie, sin contar la cadena previa de CV. No bloquea la Pi, pero conviene condicionar `imageinfo`
    a «falta portada» (mejora barata, no bloqueante).

---

## 6. Riesgos

| # | Riesgo | Impacto | Mitigación propuesta |
|---|---|---|---|
| R-1 | **ORM y migración desalineados** (§2, E-5/E-6) | Alto: el enricher entero deja de funcionar; QA no puede validar nada | AC-01/AC-02 en el mismo PR; prueba de migración con Postgres real |
| R-2 | **Coste de cortesía por serie** (2–3 peticiones × candidatos, 1,5 s) en la Pi compartida | Medio: ciclos más lentos; la cola es compartida por proceso | Condicionar `imageinfo` a «falta portada»; no abrir un segundo candidato si el primero casa; medir en la Pi |
| R-3 | **Falso positivo de edición** con un único candidato exacto sin comprobar año (`_pick_by_year`) | Medio: sinopsis/portada de otra edición en una serie correcta | Exigir año cuando la wiki declara más de un volumen con el mismo título base; prueba del caso |
| R-4 | **Negativa de 30 días** por página ausente (anuales, formatos raros, cambios de convención) | Medio: un dato que la wiki sí tiene tarda un mes en aparecer | D-8; o negativa corta cuando exista SCR1 |
| R-5 | **Bucle de reintento** con `FandomPayloadError` (tratado como transitorio) | Medio: cada ciclo repite la misma consulta fallida | Distinguir error lógico de red: no marcar intento de 30 días pero acotar reintentos (SCR1 o contador) |
| R-6 | **Colisión de arcos por título exacto** y título tomado del nombre de página | Bajo/Medio: dos arcos distintos en una fila, o nombre poco legible | Usar el campo `Title` de la plantilla cuando exista; incluir `page_title` en `metadata_` para deduplicar |
| R-7 | **Atribución legal ausente** si se fusiona así | Alto (legal) | AC-03/AC-05; `LEGAL.md` ya lo exige, no es opcional |
| R-8 | **Docs y ADR fuera de `main`** | Medio: decisión sin registrar y referencias rotas | AC-19; fusionar `docs/scraping-v2` o mover los documentos antes de SCR2 |
| R-9 | **CDN no mapeado a fuente** (E-15): apagar Fandom no corta descargas de su CDN | Bajo/Medio: contradice el patrón ADR 0013/AC-12 | D-7; mapear el host a «Fandom» (bloquear solo si **ambas** fuentes están apagadas) o documentar la excepción |
| R-10 | **Peticiones `imageinfo` aunque ya haya portada** | Bajo: tráfico evitable | Mejora barata, no bloqueante |

---

## 7. Decisiones pendientes del PO (estudio §8 y derivadas)

**Las tres del estudio (§8), sin cerrar:**

| # | Decisión | Estado en el árbol | Recomendación de la spec |
|---|---|---|---|
| D-1 | **Prioridad de Fandom en el enricher** (§8.2): ¿solo rellena huecos tras Metron/Comic Vine/GCD, o puede ser fuente primaria de serie? | El código ya eligió **respaldo**: cadena CV → DC → Marvel (`enricher.py:542-556`). No hay opción configurable | **Decidido por el PO (2026-11-13): Comic Vine prevalece sobre Fandom; Fandom queda como respaldo** (y fuente de los arcos de DC). No se añade opción configurable en SCR2 |
| D-2 | **Modelo de producto de las órdenes de lectura** (§8.1): ¿listas seguidas que marcan «tengo / me falta → wishlist», o solo consulta? Determina si hacen falta `ReadingOrder`/`ReadingOrderItem` (SCR3) | SCR2 **no** crea modelo nuevo: reutiliza `story_arcs`/`story_arc_issues.reading_order` de BL-C4; SCR3 no está | Aprobar «construir sobre lo propio» para esta historia y dejar la decisión de `ReadingOrder` para SCR3, sin bloquear SCR2 |
| D-3 | **Comic Book Herald** (§8.3): ¿se descarta para el MVP o se contacta al autor? | No implementado. Dato nuevo: el informe de Fase 0 verificó que `/feed/` responde 200 aunque el WAF bloquee `robots.txt`/`wp-json` | Mantener en cuarentena hasta que el PO decida; no entra en SCR2 |

**Decisiones derivadas que esta spec necesita para cerrar:**

| # | Decisión | Por qué | Recomendación | ¿Bloquea fusión? |
|---|---|---|---|---|
| D-4 | **Orden SCR1 → SCR2**: ¿se acepta fusionar SCR2 sin la infraestructura común (`robots.py` + `http_cache`), contra el orden propuesto en la épica? | Afecta a la «negativa corta» de SCR2 y a la caché condicional; sin ella cada apertura repite consultas | Aceptar la desviación **por escrito** (el tráfico a `/api.php` es bajo y la API está abierta) y dejar la negativa corta como deuda de SCR1; o bloquear SCR2 hasta SCR1 | No (con la desviación escrita) |
| D-5 | **Semántica de `Issue.release_date`**: fecha de portada o fecha de venta | La ficha decía «Fecha de portada» y CV escribía `cover_date`; DC da ambas y el código las mezclaba (AC-04) | **Decidido por el PO (2026-11-13): fecha de VENTA.** Fandom usa `Pubmonth`/`Pubyear`+`Day`; CV añade `store_date` (preferido, `cover_date` como respaldo); etiqueta «Fecha de publicación»; regresión con Batman #404 | Hecho (AC-04 pasa) |
| D-6 | **Superficie de atribución**: ¿basta la ficha de serie, o también la del número y `/ui/arcos`? | `LEGAL.md` dice «en las vistas donde se muestre texto/metadatos» | Las tres, con un helper común de enlace artículo+licencia; es cumplimiento, no diseño | Sí (AC-03/AC-05) |
| D-7 | **Gate del CDN de portadas**: mapear `static.wikia.nocookie.net` a Fandom (¿qué pasa si una wiki está encendida y la otra no?) o aceptar la excepción | El host es común a las dos wikis; el patrón actual bloquea por fuente | Mapear a una fuente lógica «fandom» que solo se considera apagada si **ambas** lo están; alternativa: excepción documentada | No (pero sí antes de fusionar por coherencia ADR 0013) |
| D-8 | **Anuales, especiales y formatos raros**: ¿soporte en SCR2 o límite declarado? | Ver §5.2; hoy caen en negativa de 30 días | Declarar límite en SCR2 y abrir historia aparte si el PO lo quiere; no inventar títulos | No |
| D-9 | **Descubrir (C0) y plan de enriquecimiento por campo (#128)**: ¿entran en SCR2 o quedan fuera? | El estudio solo integra el enricher; el coleccionista los esperaría en «Descubrir» y en la vista previa por campo | Fuera de SCR2; documentarlo y decidir si se abre SCR2b/SCR6 | No (con el alcance escrito) |
| D-10 | **Verificación en vivo de Marvel** (plantilla de volumen: `TotalIssues`, `startyear`, `displaytitle`; número: `Synopsis1`/`StoryTitle1`) | La ficha de benchmark no la hizo y el código la asume | 2–3 peticiones puntuales en Fase 0 antes de fusionar y fixture con la respuesta real | No, pero sí antes de prometer «Marvel aporta sinopsis/año total» |

---

## 8. Fuera de alcance y no ejecutado

- **Fuera de alcance de SCR2:** SCR1 (`robots.py` + `http_cache` + `protego`), SCR3 (guías de lectura
  y `reading_order_resolver.py`), SCR4 (foro CRG con credenciales), SCR5 (Comic Book Herald),
  Descubrir (C0) y el plan de enriquecimiento por campo (#128). Se citan solo para no confundirlos
  con la cobertura de esta historia.
- **No ejecutado aquí:** suite completa (la corre QA), tráfico real, migración sobre Postgres,
  peticiones nuevas en vivo. Los datos de campo vienen del informe de Fase 0 y de la ficha de
  benchmarking, y se citan como tales.
- **No se ha tocado** código, migración, LEGAL.md ni configuración; esta spec es solo el documento.

---

## 9. Trazabilidad y registro

| Objetivo (PO / SCR2) | Requisito / criterio | Evidencia en código |
|---|---|---|
| «Fuentes con API a nivel de serie» | AC-06, AC-07, AC-08 | `fandom.get_volume`, `enricher._sources_for`/`_find_fandom_match` |
| «a nivel de issue» | AC-11, AC-12, AC-13 | `fandom.get_issue`, `_enrich_issues_fandom` |
| «y arcos / orden de lectura» | AC-14, AC-15, AC-16 | `fandom.get_arc`, `_enrich_arcs_fandom`, `_upsert_arc`, `/ui/arcos` |
| Solo `/api.php`, nunca HTML | AC-18 y §2 E-1 | `fandom._api` |
| CC-BY-SA 3.0 visible, portadas sin etiquetar | AC-03, AC-05 | `LEGAL.md:107` + plantillas (falta) |
| Apagadas por defecto | AC-10 | `config.py:100-103` + Ajustes |
| No dañar a la web | §3.4, R-2, D-4 | `cortesia.py:237-242`, `maxlag` |
| Fusión con evidencia | AC-01…AC-20 | Pruebas nombradas por mecanismo |

**Correspondencia con la épica SCR:** SCR2 (#703) pide «fichas y portadas cuando la consulta lo
pida», sin mencionar arcos; el nivel de arcos/orden lo añadió el PO. Esta spec lo incluye, pero lo
separa de las guías externas de SCR3. La prioridad en el enricher (SCR2, última frase) es la D-1.

**Registro de cambios**

| Versión | Fecha | Qué cambia |
|---|---|---|
| v0.1 | 2026-11-13 | Primera especificación contra el árbol de trabajo (`main` 17a5995e + cambios sin commitear). Cobertura por nivel, 20 criterios, 10 huecos, 10 riesgos y 10 decisiones (3 del estudio + 7 derivadas). No autoriza fusión. |
