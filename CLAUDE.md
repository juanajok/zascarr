# CLAUDE.md — Guía de trabajo para ZascArr

> Contexto operativo para agentes y personas que colaboren en este repo.
> Lee esto antes de tocar código. Si algo nuevo se decide en un hilo de
> trabajo y no figura aquí, **acaba ese hilo añadiéndolo aquí**.

---

## 1. Qué es este proyecto

ZascArr es un gestor self-hosted de tebeoteca (CBZ/CBR) tipo Sonarr/Radarr,
optimizado para Raspberry Pi 4/5 y pensado para el público hispanohablante.
Stack: **FastAPI + SQLAlchemy async + PostgreSQL + Jinja2 + HTMX**. Sin Redis (ADR-0011).
Sin SPA, sin build de Node, htmx vendorizado en disco (ADR-0001).

**Persona:** "El Coleccionista" — no técnico, no abre terminales ni JSON.
Las decisiones de producto se miden contra él, no contra el developer
experience.

**Restricción dura que nunca se rompe:** corre dentro de una Pi compartida
con Transmission, aMule, Prowlarr y Kavita. Presupuesto de RAM por contenedor
documentado en `docker-compose.yml` (512M). Todo lo "bonito" viene segundo;
lo ligero y lo fiable, primero.

## 2. Estilo de código (Python)

Sigue las guías oficiales con estas precisiones locales:

- **PEP 8 / PEP 257 nombres y docstrings en español, código en inglés.**
  `def asignar(self, file_id, ...)` — identificadores en inglés,
  comentarios y strings de usuario en español. El español va "de cara al
  coleccionista", el inglés "de cara al código".
- Type hints obligatorios: `from __future__ import annotations` en cabecera.
- Imports explícitos del paquete raíz: `from zascarr.models import X`,
  jamás relativos profundos ni `sys.path` hacks.
- Sin dependencias nuevas sin justificación: cada dependencia es RAM en la
  Pi y superficie de vulnerabilidad. Pregunta siempre: ¿se resuelve con la
  stdlib (`dataclasses`, `re`, `zipfile`, `asyncio`, `sqlite3` no — aquí
  siempre Postgres)?
- Sin magic strings: enums del dominio viven en `models/__init__.py`
  (`ComicTradition`, `WishlistStatus`, `MetadataSource`, `AgeRating`...).

## 3. Arquitectura

### 3.1 Reglas estructurales

1. **Capa services es la única fuente de verdad del negocio.** Los routers
   API y web son finos y se comparten la lógica (ej. `WishlistService`
   consumida por `api/wishlist.py` y `web/wishlist.py`). Duplicar lógica
   entre routers = bug seguro.
2. **El ORM nunca cruza `shutil.move` con la sesión viva.** Regla
   aprendida del tracker de Kapowarr: mueve primero, haz commit corto
   después. Auditado en `ReviewService.assign_to_series` (V6a, 2026-10-03:
   `docs/design/auditoria-mover-y-sesion.md`): **hoy no cumple la regla** (el `commit` de
   `get_db` ocurre tras la respuesta); `services/asignacion.py` (ADR 0006) la cumple y **es el único camino** de
   `POST /ui/pendientes/{id}/asignar`; `assign_to_series` queda como código heredado, sin rutas. Pendiente el importer (un solo `commit` por ciclo).
3. **Mass assignment prohibido en endpoints.** Los endpoints de escritura
   usan esquemas Pydantic explícitos (`WishlistCreate`, `SeriesCreate`),
   nunca `Model(**data)` ni `setattr(model, k, v)` sobre body crudo. El
   hallazgo M1 del peer review se cerró con ese patrón: aplicarlo a todos
   los routers nuevos.
4. **Sin hotlinking en UI.** Regla permanente (decisión de 2026-09-22):
   portadas servidor desde caché local o extracción del CBZ, nunca `src`
   externo directo. Cascada de portada en `web/series.py::portada`.
5. **Decisión de arquitectura → ADR.** Existe `docs/adr/0001-ui-stack.md`.
   Las decisiones previas (Postgres, enrutado del enricher) quedaron sin
   ADR retroactivo; las nuevas no.

### 3.2 Configuración y recetas

- Variables de entorno declaradas SOLO en `config.py` (pydantic-settings),
  jamás `os.environ` directo en el código. Bootsrap escribe `.env`;
  docker-compose lo inyecta.
- **Nada de datos reales en `.env.example`/defaults.** Valores por defecto:
  o vacío, o placeholder obvio (`cambia_esto_ahora`).
- **Credenciales (ADR 0012):** ninguna ruta de arranque soportada pone en servicio el sistema con una credencial
  obligatoria ausente, vacía o conocida por defecto. `DB_PASSWORD` la genera el instalador (`scripts/_credenciales.sh`)
  y la rechazan el servicio `credenciales` de Compose y la propia app; **nunca** un `:-valor` real en el compose. El `.env`
  se escribe SOLO con `env_escribir` (atómico, sin copias) y es de root `600`; el usuario de servicio no es dueño del
  código ni de la carpeta del `.env`. Los scripts de operación no imprimen credenciales.
- Integraciones P2P deshabilitadas por defecto (`FORUM_ENABLED=false` y
  análogos): el usuario opta, la app no facilita por defecto. Patrón
  explicado en `LEGAL.md`.
- **Fuentes de metadatos (Comic Vine, AniList, Tebeosfera, GCD) apagadas por defecto**
  (decisión del PO de 2026-10-19, ADR 0013): se encienden en Ajustes; el `.env` no las
  gobierna. Una actualización **no apaga en silencio** las de instalaciones con uso previo
  (migración 0020 las conserva y Ajustes avisa).
- Healthcheck es **observacional, no bloqueante**: una VPN caída es
  WARNING, no ERROR; no congela ni el arranque ni el ciclo de descargas.

## 4. Rendimiento en Pi

- **Nada bloqueante en handlers async.** I/O síncrona (zipfile, Pillow,
  disco) dentro de `asyncio.to_thread()` — ver `web/pendientes.py`.
- **Descargas externas con semáforo:** `asyncio.Semaphore(2)` para
  portadas; una rejilla de 200 series no ataca el CDN.
- **Rate limits corteses en clientes externos** (config.py): Tebeosfera
  2.5s/req, Comic Vine 1.0s, AniList 1.5s. El motivo está en `services/
  tebeosfera.py`: scraping cortés porque la fuente es una asociación
  cultural sin ánimo de lucro, no cuestión de bugs. **El espaciado es
  COMPARTIDO por todo el proceso** (`utils/cortesia.py`, no por instancia de
  cliente): fuentes con cliente propio y portadas externas pasan por la cola
  por fuente y por host efectivo (cada salto HTTP, redirecciones incluidas),
  con espera visible y presupuestada. Tebeosfera mantiene 2.5 s como mínimo
  del proyecto aunque la configuración diga menos. Depende de **un solo
  proceso** (`uvicorn --workers 1`): con varias réplicas no hay coordinación
  entre ellas y la política es conservadora por instancia; qué se coordina y
  qué no está en `docs/design/cortesia-compartida.md`.
- **Caché local-first.** Portadas, metadatos, TODO se escribe a disco/BD
  y se sirve local después. Endpoints de imagen llevan `Cache-Control:
  private, max-age=86400` + `ETag` por mtime (`utils/cover.py::
  cached_image_response`). `/static` va con `Cache-Control: no-cache`
  (`main.py::RevalidatedStaticFiles`): el navegador revalida con el ETag y recibe un 304
  vacío si nada cambió. Sin ello, tras `update.sh` seguía pintando el CSS antiguo.
- **Portada de serie** (#418, BL-PORT3): `covers/v3/<id>.jpg` guarda solo portadas sacadas de un archivo; la
  externa va a `covers/externa/`. Un `.cbr` que de verdad es RAR se lee con `unar` (`utils/lector_rar.py`,
  por subproceso acotado, uno a la vez, solo en la etapa `runtime` de la imagen); un fallo por causa del
  archivo se recuerda en `covers/v3/fallos/<file_id>.json` (sin ruta ni nombre) hasta que el archivo cambie.
  Ver `docs/design/especificacion-BL-PORT3.md`.
- El refresco periódico del orchestrator/importer corre en el propio proceso (un solo worker), con los
  intervalos de `config.py`; no hay cola ni caché externa (ADR-0011: Redis retirado).

## 5. Seguridad y blindaje legal

Contexto: LEGAL.md y la decisión de licencia GPL-3.0 están activados
como marco permanente.

1. **El software gestiona, nunca facilita.** Sin URLs hardcodeadas de
   foros dispuestos a enlaces; SCRAPER IPB genérico donde la URL la aporta
   el usuario en runtime (`FORUM_URL`).
2. **Aceptación legal bloquea solo acciones de riesgo** (`POST
   /api/wishlist`, `POST /api/wishlist/{id}/search`): dependencia
   `require_legal_acknowledgment` en services/legal.py. NUNCA un
   middleware global — rompería los tests con FakeSession y castiga al
   usuario por "ver su biblioteca".
3. **Datos cacheados = uso privado.** Telemetry: cero. No se redistribuye
   contenido (LEGAL.md tabla de fuentes: Whakoom CC-BY-SA, Tebeosfera
   sui generis, portadas ©).
4. **Logs sin datos sensibles** (structlog). Si un error lleva datos del
   usuario (rutas, credenciales), sanitiza antes.
5. Endpoints mutables usan `Form(...)` con campos explícitos en UI HTMX;
   `Cache-Control` documentado en `api/legal.py`; el 403 de la puerta legal lleva `HX-Redirect`
   (`services/legal.py::require_legal_acknowledgment`).
6. **La UI escucha en localhost por defecto** (`127.0.0.1` en la app; Postgres
   no se publica a la red en ningún caso). Abrir a la LAN es una decisión
   **explícita** del operador y exige contraseña; el exterior, proxy inverso con
   TLS y `BASE_URL`/`ALLOWED_HOSTS`. No se copia el valor por defecto de
   Sonarr/Radarr: es una elección del producto, no una herencia. Decisión
   completa en **ADR 0004** (`docs/adr/0004-exposicion-de-red.md`); la elección
   guiada está en el instalador (**A11**, `scripts/_exposicion.sh`): las dos opciones
   que abren fijan la contraseña **antes** de publicar el puerto.

7. **Toda petición del servidor a una URL que no sea fija pasa por `utils/url_portada.py`**
   (SSRF, H1): lista de nombres, direcciones resueltas públicas (IPv4 e IPv6), conexión a la IP
   validada, redirecciones a mano y tope de tamaño. Un token firmado garantiza integridad,
   **no** seguridad de una URL externa. Ver `docs/design/hallazgo-h1-cover-url.md`.

8. **Una fusión que toque «qué exige la contraseña actual» espera la pasada final de seguridad**
   (decidido el 2026-11-12, a propuesta de SecOps tras #508, cuyos dos últimos commits se
   fusionaron sin ella): una PR que modifique `services/seguridad.py`, `web/ajustes.py` o
   `services/reautenticacion.py` no se fusiona hasta que SecOps haya dictaminado **el SHA final**
   (el que se fusiona), aunque ya hubiera dictaminado uno anterior. Aplica también a los
   commits añadidos después de la revisión. Las pruebas estáticas de esa regla (quién llama a
   qué) son una red contra descuidos, no sustituyen a la pasada.

## 6. UX

- **Todo en español llano para el coleccionista**: el dashboard y las
  instrucciones del wizard placan eso. Errores tipo "exit code 1" están
  prohibidos en superficie de usuario: se mapean a causa y acción (historia
  A2).
- **Semáforos visibles** para el estado del sistema (`/api/health`), texto
  concreto sobre qué falló y qué hacer. Un servicio **apagado en Ajustes** no es un fallo: `/api/health`
  lo da como `disabled`, no lo sondea ni cuenta para el semáforo, y Estado lo pinta
  «Desactivado» en gris (decidido el 2026-10-21).
- **Sin diálogos nativos ni balas invisible**: `hx-confirm` ya se sabe que
  la automatización del navegador no lo resuelve; el usuario real sí.
  Documentado como limitación aceptada en B2.
- Tarjetas con gracia de fallo: portada rota = marcador debajo de la imagen
  (`ui.portada`: tinta de imprenta, trama e inicial; sin `onerror=`), no imagen
  rota; campo ausente con icono claro.
- **Texto informativo: 14 px como mínimo** (`.875rem`; lo comprueba `test_web_css_contraste`).
  Única excepción declarada: la etiqueta de la barra inferior del móvil (`.nav-enlace`,
  `clamp(.75rem, 3.3vw, .875rem)`), que baja hasta 12 px en pantallas de menos de 424 px
  para que «Deseados» quepa a 320 px (U16). Una excepción nueva se declara en esa prueba con
  su motivo; no se acorta la etiqueta.
- **Tipografía** (decidido el 2026-10-20): dos familias libres (OFL), servidas por la
  app desde `static/vendor/fonts` y nunca desde un CDN: **Anton** para titulares y
  rótulos en mayúsculas (`--font-display`), **Archivo** variable para todo lo que se
  lee y se usa (`--font-body`). Anton **solo en mayúsculas**: una frase (los títulos de
  paso del Inicio, por ejemplo) va en Archivo negrita, y los chips fijan su fuente en vez
  de heredarla del titular que los contiene. Sin tercera familia de «rotulación de
  cómic». Ni fuentes comerciales (el repo es GPL y cada
  instalación las redistribuiría) ni fuentes de cómic en controles o textos largos.
  Cifras que se comparan (contadores, números de grapa, métricas) con
  `font-variant-numeric: tabular-nums`. Ficha y forma de actualizar en
  `static/vendor/README.md`.
- **Iconos de la interfaz** (decidido el 2026-10-20): SVG de trazo de `web/iconos.py`
  (Lucide, ISC, con su aviso en el módulo), nunca caracteres de texto (⌂ ✎ ★…), que cada
  sistema dibuja distinto. Un icono nuevo se copia de `lucide-static` al diccionario.
- **Marca** (decidido el 2026-10-20): el estallido «¡ZAS!» bermellón con una Z rotulada
  encima, en `static/brand` (ficheros, colores y reglas en su README). Sustituye al
  cuadrado amarillo con trama. Se descartó, tras pruebas de iconos: un «¡» (se lee como
  la «i» de información), una Z sobre cuadrado rojo (se confunde con Zabbix y YouTube)
  y el amarillo (Mylar3, Kapowarr, Radarr). Por
  debajo de 24 px va la versión simplificada `zascarr-favicon.svg` (sin fondo: el estallido es la silueta); en la interfaz (24–48 px),
  `zascarr-icono.svg` sin trama ni líneas de impacto (2026-10-21: a 32 px la versión completa se
  veía gris y empastada). En ambos, la Z es grande y gruesa y sobresale un poco del estallido,
  que debe seguir viéndose (decisión del PO, 2026-10-21): así además se distingue de Komga, que
  lleva la letra dentro de un estallido. La trama y las líneas de impacto, solo en el icono de 180 px. Tamaño mínimo, espacio libre y
  versión en blanco y negro, en el README de la marca.
- **Guiños de imprenta: trama sí, desalineamiento casi nunca** (decidido el 2026-10-21). La trama de
  puntos va donde no hay nada que leer encima: el fondo (5 %), las tarjetas de cifras (10 %), los
  estados vacíos (una esquina fija bajo el texto) y la página de error (un disco a la derecha, solo con
  ancho ≥ 1100 px). Detrás de texto, como mucho al 5–10 %; sin texto encima puede llegar a ~30 %. El
  desalineamiento de planchas (cian y magenta corridos) va **solo** en el rótulo de la página de error:
  en texto pequeño se lee borroso y en un borde se confunde con la sombra dura de los botones. Todo se
  apaga con `prefers-contrast: more` y `forced-colors` (bloque al final de `web.css`; una prueba exige
  que cada trama nueva esté en él).
- **Un botón principal por pantalla** (decidido el 2026-10-20): el amarillo es la acción que hace
  avanzar la tarea de esa pantalla y se pide con `.primary` (`button.primary`, `.btn.primary`). Un
  `type="submit"` es neutro por defecto: los botones que se repiten (uno por resultado o por tarjeta) y
  los «Guardar» de Ajustes no son principales. Excepción con significado propio: el verde de
  «Sí, organizar» (aceptar una sugerencia).
- **Un aviso no parece un botón** (decidido el 2026-10-20): la sombra dura desplazada es de los botones
  (y del rótulo girado); `.caption` y `.aviso` van sin ella, con el canto de panel.
- **Títulos que son frases o rutas, en Archivo** (decidido el 2026-10-20): clase `.titulo-frase` para
  cualquier título de más de 3 palabras o que muestre una ruta de carpeta (en mayúsculas perdería su
  caja). Los `h1` de pantalla siguen siendo rótulos en Anton.
- **Las cifras del Inicio cuadran** (decidido el 2026-10-20): la frase de entrada desglosa lo
  registrado en partes que suman el total (`services/inicio.py::Desglose`, una sola consulta; «por
  revisar» con el filtro de la lista); lo del disco va aparte, con su fecha y el porqué de la
  diferencia (copias idénticas que el registro dejó fuera). Un paso no añade cifras sueltas.
- **Presupuesto de texto** (historia U21, decidido el 2026-10-15; los umbrales
  son provisionales hasta validarlos en U10):
  - Una frase de entrada por pantalla, de ≤ 20 palabras, que diga qué se hace aquí.
  - ≤ 50 palabras visibles antes de la primera acción. El resto va en
    `<details>` («¿De dónde salen estos datos?», «Avanzado»).
  - La garantía («no se mueve ni se renombra nada») va **junto a la acción
    con efecto** y en su confirmación, no en la cabecera de pantallas que
    no cambian nada.
  - Resumen antes que listado. Las mayúsculas, solo en rótulos de ≤ 3 palabras.
  - Los textos explican la tarea, no el contrato: nada de «token», «lote»
    ni códigos internos en superficie (ver A2 y U20).
- **Sistema de diseño:** las reglas de marca, color, tipografía, forma, trama, componentes y
  accesibilidad están en [`docs/design/sistema-de-diseno-zascarr.md`](docs/design/sistema-de-diseno-zascarr.md)
  (diffeable; el **PDF** con las muestras visuales, en `docs/design/sistema-de-diseno-zascarr.pdf`).
  Es la referencia para cualquier pantalla o componente nuevo: los tokens y las macros (`ui.*`,
  `web/componentes.py`) mandan sobre el aspecto heredado. Antes de pintar una pantalla o tocar
  `web.css`, léelo: la **deuda abierta** de la última revisión (escala de texto sin tokens,
  grosores de borde literales, clases inexistentes, avisos sin icono/`role`…) **no se copia**.

## 7. Base de datos

- Migraciones Alembic one-shot: `versions/` no se reescribe una vez
  aplicado (aplicado = IDs 0001-0008). Salarse esto rompe instalaciones
  reales.
- Enum Postgres con `postgresql.ENUM` explícito; el `create_table` vuelve
  a crear tipos si no se le dice lo contrario (bug documentado del 0001).
- Tradición en el modelo como String + values_callable `.value` en
  minúsculas — nunca `.name` mayúscula (bug real de 0001).
- Migraciones que tocan `CREATE EXTENSION` o `CREATE FUNCTION` van con
  `IF EXISTS`/`IF NOT EXISTS` y downgrade coherente (0006 f_title_norm
  como referencia de estilo).

## 8. Tests

- Patrón prevalente: `app.dependency_overrides[get_db]` + `FakeSession`
  queue-driven. Los ~220 tests ya montados son referencia
  (`tests/test_api_wishlist.py`, `tests/test_api_series.py`).
- **La suite se ejecuta también con el directorio temporal en el MISMO dispositivo que `/`** (`pytest --basetemp=<ruta en el disco raíz>`): en una máquina donde `/tmp` es un `tmpfs`, el comportamiento que depende del dispositivo (p. ej. la guarda de rutas obsoletas de `services/importer.py`) pasa distinto que en la CI y un fallo real queda enmascarado (ocurrió con la PR #84).
- **Ninguna dependencia nueva por "testing"**: los tests existentes ya
  cubren casos de UI-legal sin necesidad de BD (el hallazgo del wizard
  legal se cerró así).
- La única excepción a FakeSession: `test_title_norm.py` sí toca
  Postgres real, marcada skip sin TEST_DATABASE_URL.
- Cada bug real (sort_order truncado, mass assignment) se cierra con
  **test de regresión explícito** nombrado con el mecanismo del bug.
- Tests asíncronos: `pytest.mark.asyncio`, nunca asyncio.run() dentro.
- **Pruebas con Postgres real** (`TEST_DATABASE_URL`, siempre una base cuyo nombre lleve «test»): la
  sesión **migra esa BD a `head`** una vez (`tests/conftest.py`); lo que necesite otro estado (p. ej. «sin
  migrar») crea su propia BD con `tests._pg.bd_efimera()`. Los subprocesos de alembic usan
  `tests._pg.alembic`, que quita la raíz del repo de `PYTHONPATH` (si no, el `alembic/` del repo sombrea el
  paquete). Detalle y causa en `docs/design/diagnostico-postgres-pruebas.md`.

## 9. Git y ramas

- Commit pequeño y atómico; un cambio de dominio por commit ("rename:
  SecuenciArr → ZascArr" fue un commit, no repartido en 10).
- Mensajes en español en el formato `<área>: <qué> (<porqué> si no es
  obvio)`.
- No commitear cosas de depuración local (`.env`, *.prof, dumps).
- El histórico es documentación: cuando cierras una historia P0/P1 del
  backlog, actualiza `docs/BACKLOG.md` a "Hecho" con la nota del
  mecanismo ("cómo se cerró, no solo que se cerró").
- **Flujo: Scrumban hasta tener datos** (decidido el 2026-10-15). Sin sprints
  ni compromiso de puntos: se tira del campo **«Estado»** del Project 1 (el
  campo «Status» no se usa) con WIP **En curso 2** (máx. 1 MVP + 1),
  **En revisión 2**, **En refinamiento 4** y aviso con **≥ 5** en «Fusionado —
  pendiente de despliegue». «Lista para desarrollar» exige DoR completa y
  `Bloqueada = No`. Al entrar en «En curso» se rellena **Inicio**; al llegar a
  «Fusionado», **Fin**. El sprint se fija con la mediana y el p85 del tiempo
  de ciclo cuando haya 8 historias terminadas o el 2026-11-12, lo que llegue
  antes (umbrales provisionales).

## 10. Lo que NO se hace (anti-patrones del proyecto)

- ❌ SPA / Node build / Alpine/Vue/React: ADR-0001, definitivo.
- ❌ `create_type=False` esperando que funcione sin `postgresql.ENUM`.
- ❌ `Wishlist(**data)` desde el body crudo (cerrado con esquemas
   Pydantic).
- ❌ Hotlinking en UI (regla permanente).
- ❌ Copiar scrapers de documentos de referencia sin verificar en vivo
   (Tebeosfera exigió `follow_redirects=True` — los CDNs devuelven 302).
- ❌ Credenciales/fuentes por defecto en config o bootstrap.
- ❌ Middleware global de blooming que rompe todos los tests (por eso el
   wizard legal es dependencia, no middleware).

## 11. Documentos vivos

| Doc | Rol |
|---|---|
| `docs/BACKLOG.md` | Prioridades P0-P2, historias, estimaciones y decisión de hecho/cierre con nota mecánica de cómo se logró cada historia |
| `docs/adr/` | Decisiones de arquitectura y de postura del producto (0001 UI, 0002 alcance del enricher, 0003 identidad editorial, 0004 exposición de red, 0005 migración de la UI, 0011 retirar Redis, 0012 credenciales del `.env`, 0015 lector de RAR con `unar` y riesgo aceptado; 0006–0010 en el propio directorio) |
| `docs/design/ui-migracion.md` | Inventario de la UI (plantillas, rutas, contratos HTMX), maqueta frente a la realidad y estimaciones de la Épica V. **Consultar antes de tocar una plantilla o un contrato `hx-*`** |
| `docs/design/sistema-de-diseno-zascarr.md` (+ `.pdf`) | **Sistema de diseño publicado** (2026-11-13): libro de marca, principios, color y tokens de los dos temas, tipografía, forma, trama, iconografía, maquetación, interacción/accesibilidad, cómo se usa y la revisión de UI/UX con su deuda abierta. El `.md` es la referencia diffeable; el `.pdf`, las muestras visuales. **Consultar antes de tocar plantillas o CSS.** |
| `src/zascarr/LEGAL.md` | Marco legal activo; si se actualiza, hay que el mismo día versionar/rehacer `legal_version` en services/legal.py (hash del fichero) |
| `pyproject.toml` | Fuente única de metadatos del paquete (nombre, license, deps) |
| `docs/design/benchmark-referencias.md` | Procedimiento y ficha para comparar referencias antes de features P0/P1 (ver §13) |
| `docs/design/contrato-307-formato-por-contenido.md` | Contrato de **formato por contenido** (#307): un único punto de decisión (`core/formato_contenedor.py`); `file_format` es la extensión **declarada**, el formato real va en `files.metadata["formato_contenido"]`. **Consultar antes de tocar `triage`, la portada o la auditoría de formatos** |
| `docs/design/registro-incremental-326.md` | **Registro incremental** (#326): buscar y registrar archivos nuevos de una biblioteca ya registrada, a mano y con confirmación; «nuevo» = ruta sin fila; sin automatismo. **Consultar antes de tocar `LibraryAdopter.adopt`, `registro_biblioteca` o el bloque «Registro» de la Auditoría** |
| `docs/design/especificacion-BL-R9-rescan-biblioteca.md` | **Rescan de la biblioteca** (BL-R9): a demanda (Auditoría) y periódico (`rescan_interval_minutes`); registra lo nuevo, re-tría lo sustituido sobre la misma fila (`file_mtime_ns`, migración 0021), reenlaza movidos y marca/revierte desaparecidos, sin mover ni borrar. **Consultar antes de tocar `LibraryAdopter.rescanear`, `services/rescan_biblioteca.py`, el bloque «Reescanear la biblioteca» de Auditoría o el bucle `_rescan_loop` de `main`** |
| `docs/design/disponibilidad-231.md` | **Disponibilidad de archivos** (#231): qué anota el ciclo del importador (`import_runs.details["comprobacion_biblioteca"]`), cómo se lee y la lista `/ui/no-disponibles`; solo lectura, sin tocar el disco al mostrarse. **Consultar antes de tocar `Importer._comprobar_biblioteca`, `services/disponibilidad.py` o el bloque «Tu biblioteca en disco» de Estado** |

## 12. Principios de arquitectura del propio código (confirmados por
benchmarking ronda 2)

Decisiones ya validadas por comparación contra Kapowarr, Mylar3, Suwayomi
— **no tocar**:

- JSONB para metadata suelta (mismo patrón que `memo` de Suwayomi).
- IDs de proveedor en columnas paralelas (`comic_vine_id`, `anilist_id`,
  `tebeosfera_slug`), nunca una clave global acoplada a una fuente.
- `issue_number VARCHAR` + `Issue.sort_order FLOAT` (resuelve crossovers,
  Annuals, paquetes decimales sin un módulo entero).
- `story_arc_issues.reading_order` — modelo ya preparado para sagas que
  cruzan series.
- Calidad tri-estado legible para el coleccionista (lo mejor / equilibrado
  / lo que haya) mapeada internamente a `quality_tier`.

## 13. Benchmarking de referencia antes de features P0/P1

Antes de implementar una feature P0/P1 de comportamiento nuevo —o cualquier historia que
toque modelo de datos, ficheros, seguridad o el ciclo de búsqueda y descarga—: fijar el
problema local (historia + caso real + comportamiento actual en el código vigente +
resultado deseado), consultar las referencias pertinentes (Sonarr/Radarr para ciclo de
búsqueda/estados/importación; Kapowarr/Mylar3 para ediciones/ficheros/metadatos de cómic;
Suwayomi para capítulos/fuentes/lectura) y registrar, por idea, adoptar / adaptar /
mejorar / construir sobre lo propio / descartar, con versión/commit y pruebas. **No
inferir soporte de una función por su UI, ni ausencia por no encontrarla.** El benchmark
previo lo hace quien lo haga (p. ej. el rol SCOUT.bench) y lo entrega a quien coordina: su ficha es insumo para la
especificación, no aprobación; decide el PO. El procedimiento, el vocabulario y la ficha
viven en `docs/design/benchmark-referencias.md`; solo las decisiones arquitectónicas
duraderas pasan a ADR. El esfuerzo es proporcional al riesgo: un arreglo evidente de texto
o CSS no requiere investigación.

**Barrera legal (separada del procedimiento):** inspirarse en un patrón no es copiar
código. Kapowarr y Mylar3 son GPL-3.0; Suwayomi declara MPL-2.0 con componentes de
terceros Apache-2.0. Antes de reutilizar una implementación, revisar el fichero concreto,
sus avisos y obligaciones — no asumir «todas tienen la misma licencia».

## 14. Glosario de vocabulario de producto

> **Decidido el 2026-11-14 (BL-U7, #793).** Fuente única del vocabulario de superficie. La tabla de
> cambios que aplica #205 está en [`docs/design/ui-u7/glosario-u7.md`](docs/design/ui-u7/glosario-u7.md).
> Este glosario **no renombra** entidades, estados, operaciones, URLs ni valores persistidos: fija solo
> el texto visible. Si una pantalla nueva necesita un término, se añade aquí antes de usarlo.

**Principio.** Un término por concepto. Dos conceptos distintos no se convierten en sinónimos por
comodidad, y un mismo concepto no cambia de nombre según la pantalla. La UI habla como el coleccionista
(«tebeo», «número», «carpeta»), no como el esquema (`File`, `Issue`, `StoryArc`,
`ComicTradition.TEBEO`). Cuando la precisión importa, se usa el término del concepto, no el más corto.

### 14.1 Conceptos

| Concepto | Qué es | Texto en la UI | NO usar | Dónde |
|---|---|---|---|---|
| **serie** | Conjunto de números con una identidad editorial (`Series`). No es un número ni un archivo. | «Serie» / «Series»; «Series en la biblioteca», «Buscar una serie», «Nueva serie». | «Título» como sinónimo de serie; «colección»; «cómic» como término de producto (se tolera en nombres de fuentes o descripciones de terceros). | `menu.py`, `biblioteca.html`, `_rejilla_biblioteca.html`, `series_detail.html` |
| **número** | Unidad bibliográfica dentro de una serie (`Issue`); puede tener varios archivos. | «Número» / «Números»; «#12», «Números que te faltan», «N de M números». | «Tebeo» para contar números; «publicación» fuera de correspondencias; «tomo» salvo que sea el formato. | `_rejilla_biblioteca.html`, `series_detail.html`, `_tarjeta_pendiente.html` |
| **archivo** | Fichero físico en disco (CBZ/CBR/PDF/EPUB) de una ruta (`File.file_path`). | «Archivo» / «Archivos»; «Archivos no disponibles», «el archivo no se mueve». | «Registro» para el fichero; «pendiente» para el fichero; «tebeo» cuando se habla de la ruta o el formato. | `src/zascarr/models/__init__.py`, `no_disponibles.html`, `_tarjeta_pendiente.html` |
| **tebeo** | Palabra del coleccionista para un cómic como objeto o ejemplar; puede ser físico o un archivo. No es la unidad bibliográfica. | «Tebeo» / «Tebeos»; «Tebeos registrados», «En tu disco había N tebeos», «El mismo tebeo, dos veces». «Tebeo español» solo como tradición. | «Número» cuando se cuentan números; «registro» cuando se habla de la fila; «pendiente» como sinónimo; «tebeo» a secas como etiqueta de tradición. | `src/zascarr/models/__init__.py`, `library.py`, `dashboard.html`, `_auditoria_informe.html` |
| **registro** | Fila de la biblioteca: una ruta en `files` con su estado (`File`), exista o no el archivo y esté o no vinculada. | «Registro» / «Registros» solo en la explicación de procedencia («Son registros pendientes de verificar, no archivos confirmados») y en contextos técnicos; el proceso se dice «registrar» o «registro de la biblioteca». | Como sinónimo de archivo, tebeo o pendiente; como unidad de los contadores de la cola. | `carpetas.html`, `src/zascarr/models/__init__.py` |
| **pendiente** | Estado de un registro que aún no está asignado a un número y espera decisión (`issue_id IS NULL`, no descartado; la cola de «Por revisar» añade `match_status = unsorted`). | «Pendiente» / «Pendientes»; «Por revisar», «Mostrando X–Y de N pendientes», «Nada pendiente», «Pendientes sueltos». | «Archivo» para la cola; «registro»; «tebeo» como sinónimo. | `src/zascarr/services/review.py`, `pendientes.html`, `_pendientes_rango.html` |
| **suelto** | Pendiente cuya ruta no tiene una carpeta de serie contextual (`dividir_ruta(...).contextual is None`). | «Suelto» / «Sueltos»; «Pendientes sueltos», «N sueltos». | «Archivo suelto» en la superficie principal; «colección» o «carpeta» para un suelto. | `src/zascarr/services/revision_carpetas.py`, `sueltos.html`, `pendientes.html` |
| **carpeta** | Directorio del disco; en «Pendientes por carpeta», el grupo de pendientes que comparten una carpeta de serie contextual (una pista, no una clasificación). | «Carpeta» / «Carpetas»; «Pendientes por carpeta», «Revisar por carpeta (N carpetas)». | «Colección» para una carpeta; «serie» para la carpeta. | `src/zascarr/services/revision_carpetas.py`, `carpetas.html`, `_pendientes_carpetas_enlace.html` |
| **colección** | Agrupación manual de series con política de auto-búsqueda (`Collection`, #155). No es el conjunto entero ni una carpeta. | «Colección» / «Colecciones»; «Nueva colección», «Añadir series a esta colección». | Para el conjunto entero («tu colección»); para una carpeta; para el estado de completitud. | `src/zascarr/models/__init__.py`, `colecciones.html`, `menu.py` |
| **estado de la serie** | Completitud de tu colección para una serie: completa, le faltan números, no se puede calcular o no la vas a completar (`Series.metadata_["coleccion"]`, #340). | «Estado de la serie» (propuesto; hoy «Estado de la colección» en el filtro y la ficha). | «Estado de la colección» (colisiona con la pantalla «Colecciones»); «estado» a secas. | `_selector_coleccion.html`, `series_detail.html`, `src/zascarr/services/coleccion.py` |
| **tebeoteca** | Conjunto entero de tebeos del coleccionista; el producto es un gestor de tebeoteca. | «Tebeoteca»; «Tu tebeoteca». | «Colección» para el conjunto entero; «biblioteca» cuando se habla del conjunto y no de la pantalla. | `dashboard.html`; §1 de este documento |
| **biblioteca** | Pantalla `/ui/biblioteca` y catálogo de series; también, en minúscula, el conjunto de archivos en disco que ZascArr gestiona. | «Biblioteca» (pantalla, mayúscula); «tu biblioteca» (conjunto en disco). | «Mi biblioteca» para la revisión; «catálogo» en superficie; «colección» para la pantalla. | `menu.py`, `biblioteca.html`, `carpetas.html` |
| **Por revisar** | Pantalla `/ui/pendientes` y cola de pendientes que esperan clasificación. | «Por revisar» (menú, título y h1); «Pendientes por carpeta» y «Pendientes sueltos» son vistas de esa cola. | «Pendientes» como nombre de la pantalla; «Revisión» sola; «Revisión de mi biblioteca». | `menu.py`, `pendientes.html`, `carpetas.html`, `sueltos.html` |
| **revisión de la biblioteca (Duplicados)** | Revisión del disco: duplicados, registro, reescaneo y originales. La pantalla es `/ui/auditoria` y el menú dice «Duplicados»; la acción es «Revisar mi biblioteca». | «Duplicados» (menú, título, h1); «Revisar mi biblioteca» (acción). | «Mi biblioteca» o «Revisión de mi biblioteca» para la pantalla; «Por revisar» para esta revisión. | `menu.py`, `auditoria.html` |
| **duplicado** | Grupo de archivos con el mismo contenido (mismos bytes). Dos ediciones del mismo número no son un duplicado. | «Duplicado» / «Duplicados»; «copias idénticas», «El mismo tebeo, dos veces». | Para «El mismo número, en dos ediciones»; para un pendiente. | `_duplicados.html`, `_auditoria_informe.html` |
| **editorial** | Casa editorial de una serie (`Publisher`). El sello (`Imprint`) es otra cosa. | «Editorial» / «Editoriales»; «Todas las editoriales». | «Sello» como sinónimo; «colección». | `src/zascarr/models/__init__.py`, `_filtros_panel_campos.html`, `editar_serie.html` |
| **tradición** | Tradición editorial de una serie (`ComicTradition`): grapa americana, tebeo español, manga… | «Tradición»; valores «Tebeo español», «Grapa americana», «Franco-belga (BD)», «Manga»… | El valor interno (`tebeo`, `franco_belgian`, `american`); «tebeo» a secas como etiqueta de tradición. | `src/zascarr/models/__init__.py`, `library.py`, `_filtros_panel_campos.html` |
| **saga / arco** | Arco argumental o lista de lectura que puede cruzar series (`StoryArc`). | «Saga» / «Sagas»; «Sagas en orden», «Nueva saga». | «Arco» en superficie; «colección» para una saga. | `src/zascarr/models/__init__.py`, `arcos.html`, `_filtros_panel_campos.html` |
| **edición** | Edición concreta de un número: formato, editorial, idioma, calidad (`IssueFormat` y filas de `Issue` distintas). | «Edición» / «Ediciones»; «Mejores ediciones», «Otras ediciones de este número». | «Número» o «publicación» para una edición. | `mejoras.html`, `_auditoria_informe.html`, `issue_detail.html` |
| **mejora** | Edición mejor que la que ya tienes para un número; la propone ZascArr y el PO decide. | «Mejora» / «Mejoras»; «Mejoras» (pantalla), «Buscar mejoras ahora», «N pendientes» de mejoras. | «Mejoras de edición» como nombre de pantalla; «sugerencia» para la propuesta (la sugerencia es de la cola). | `mejoras.html`, `menu.py`, `web/mejoras.py` |
| **publicación** | En declaraciones de carpeta y correspondencias, la unidad de destino: un número o un tomo de la biblioteca. En la ficha de número, la fecha de publicación es un dato de la edición. No es sinónimo general de número. | «Publicación» / «Publicaciones» solo en el flujo de correspondencias; «Una publicación es un número o tomo de tu biblioteca»; en la ficha, «Fecha de publicación». | Fuera de esos dos contextos; «Otras publicaciones con este número» cuando se habla de ediciones; «publicación» como sinónimo de número en la cola. | `crear_correspondencia.html`, `contexto_declarado.html`, `issue_detail.html` |
| **catálogo** | Nombre interno del catálogo de la base de datos. No es un término de superficie. | — (usar «biblioteca»). | «Catálogo» en la superficie; se sustituye por «biblioteca» cuando se toque la pantalla (deuda de V11 en Auditoría). | `auditoria.html`, `_auditoria_registro.html` |

### 14.2 Reglas de contexto

- **Tebeo.** «Tebeo español» es la etiqueta de la tradición (`ComicTradition.TEBEO`), siempre con
  «español» y en mayúscula cuando encabeza. «Tebeo» a secas es el objeto o ejemplar: «El mismo tebeo,
  dos veces» (dos archivos idénticos) o «En tu disco había 1.542 tebeos» (ficheros leídos). No es
  «número» cuando se cuenta la numeración de una serie y no es «registro» cuando se habla de la fila.
- **Pendiente no es archivo.** Un **pendiente** es un registro en un estado (sin número, sin descartar);
  el **archivo** es el fichero del disco. «Por revisar» lista pendientes, y algunos pueden apuntar a un
  archivo que ya no está: por eso el subtítulo no dice «archivos».
- **Suelto = pendiente sin carpeta.** Un **suelto** es un pendiente cuya ruta no tiene carpeta de serie
  contextual. No es una categoría distinta de «pendiente»; es un pendiente más.
- **Registro = fila, no archivo.** El **registro** es la fila de `files`; el **archivo** es el fichero.
  La frase que lo explica —«Son registros pendientes de verificar, no archivos confirmados»— se conserva
  en el desplegable de procedencia; fuera de ahí, «registro» no es una unidad de contador.
- **Biblioteca, tebeoteca, colección y catálogo.** **Biblioteca** es la pantalla `/ui/biblioteca` (y, en
  minúscula, el conjunto en disco); **tebeoteca** es el conjunto entero del coleccionista; **colección**
  es un grupo con nombre de series (#155); **catálogo** es el nombre interno de la BD. No se usan como
  sinónimos: «Tu colección ahora» del Inicio es «Tu tebeoteca ahora»; «meter en el catálogo» es
  «registrar en la biblioteca».
- **Revisión (Duplicados) no es «Por revisar».** **Por revisar** es la cola de pendientes
  (`/ui/pendientes`). **Duplicados** es la revisión del disco (`/ui/auditoria`); su acción es «Revisar
  mi biblioteca». «Revisión de mi biblioteca» y «Mi biblioteca» no son nombres de pantalla.
- **Número, tebeo, edición y publicación.** **Número** es la unidad bibliográfica; **tebeo** es el
  objeto o archivo; **edición** es una versión concreta de ese número; **publicación** es la unidad de
  destino en una declaración de carpeta (un número o un tomo). No se intercambian al contar.
- **Saga, arco, editorial y sello.** En superficie, «Saga»; «arco» y `StoryArc` son código. «Editorial»
  es `Publisher`; «sello» es `Imprint` y solo se usa cuando el dato distingue el sello.

### 14.3 Excepciones y términos técnicos

- **Valores persistidos que no se tocan:** `tebeo` (`ComicTradition.TEBEO` y `ClaseZip.TEBEO`),
  `futuros` y `todos` (`WishlistPolicy`), `publisher_id`, `vista` (`tarjetas`/`lista`),
  `leido` (`si`/`leyendo`/`no`), `orden`, `coleccion`, `story_arc_id`, `review_motivo` y `auth_mode`.
  Pueden aparecer en `value`, en la URL o en la BD; **no** en el texto visible como etiqueta.
- **Código y diagnóstico:** `File`, `Issue`, `Series`, `StoryArc`, `Collection`, `Publisher`, `Imprint`,
  `LibraryAdopter`, `ReviewService`, `revision_carpetas`, `catálogo`, `auditoría`, `arco`, `token`,
  `lote` y `motivo` pueden vivir en código, JSON, pruebas o detalle técnico plegado. En superficie se
  traducen o se omiten (A2, U20).
- **«Tebeo» en un `value` o en una URL** (`tradition=tebeo`) es correcto; la etiqueta visible es
  «Tebeo español». Una prueba que busque «tebeo» en todo el HTML siempre acertará: hay que mirar el
  texto visible, como hace `tests/test_pendientes.py:212-215`.
- **`ClaseZip.TEBEO`** (`src/zascarr/models/__init__.py:125`) clasifica el contenido de un ZIP; no es la tradición
  ni una etiqueta de superficie.

### 14.4 Evidencias

- Definición de la historia y criterios: [`docs/BACKLOG.md`](docs/BACKLOG.md) U7 (`:959-968`) y U18
  (`:1041`).
- Inventario y vigencia de #205: [`inventario-textos-y-recorte.md`](docs/design/ui-u18/inventario-textos-y-recorte.md)
  y [`vigencia-2026-11-14.md`](docs/design/ui-u18/vigencia-2026-11-14.md).
- Tabla de cambios y navegación: [`docs/design/ui-u7/glosario-u7.md`](docs/design/ui-u7/glosario-u7.md).
- Menú y grupos: [`src/zascarr/web/menu.py`](src/zascarr/web/menu.py) (`:28-44`) y
  [`_componentes.html`](src/zascarr/web/templates/_componentes.html) (`:78-101`).
- Condición de pendiente: [`src/zascarr/services/review.py`](src/zascarr/services/review.py) (`:130-137`);
  sueltos y carpetas: [`src/zascarr/services/revision_carpetas.py`](src/zascarr/services/revision_carpetas.py)
  (`:362-363`, `:487-492`).
- Modelo: [`src/zascarr/models/__init__.py`](src/zascarr/models/__init__.py) (`ComicTradition:36-45`,
  `ClaseZip:123-129`, `WishlistPolicy:192-200`, `Publisher:371`, `Imprint:391`, `Collection:494`,
  `Series:516`, `StoryArc:628`, `Issue:646`, `File:780`).

---

*Documento vivo. Cada decisión nueva que afecte a "cómo trabajamos" se
registra aquí el día que se decide, no cuando la recuerda alguien.*
