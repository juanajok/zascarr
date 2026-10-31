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
  cultural sin ánimo de lucro, no cuestión de bugs. **Tebeosfera: el
  espaciado es COMPARTIDO por todo el proceso** (`utils/cortesia.py`, no
  por instancia de cliente; cada salto HTTP, redirecciones incluidas,
  espera, y estas solo van a su propio origen, ≤ 3) y 2.5 s es el mínimo
  del proyecto aunque la configuración diga menos; depende de `uvicorn --workers 1`. Ver
  `docs/design/cortesia-tebeosfera.md`. Los demás clientes aún llevan el
  espaciado por instancia.
- **Caché local-first.** Portadas, metadatos, TODO se escribe a disco/BD
  y se sirve local después. Endpoints de imagen llevan `Cache-Control:
  private, max-age=86400` + `ETag` por mtime (`utils/cover.py::
  cached_image_response`). `/static` va con `Cache-Control: no-cache`
  (`main.py::RevalidatedStaticFiles`): el navegador revalida con el ETag y recibe un 304
  vacío si nada cambió. Sin ello, tras `update.sh` seguía pintando el CSS antiguo.
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
- Tarjetas con gracia de fallo: portada rota = placeholder CSS
  `.cover-missing`, no imagen rota; campo ausente con icono claro.
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
| `docs/adr/` | Decisiones de arquitectura y de postura del producto (0001 UI, 0002 alcance del enricher, 0003 identidad editorial, 0004 exposición de red, 0005 migración de la UI, 0011 retirar Redis, 0012 credenciales del `.env`; 0006–0010 en el propio directorio) |
| `docs/design/ui-migracion.md` | Inventario de la UI (plantillas, rutas, contratos HTMX), maqueta frente a la realidad y estimaciones de la Épica V. **Consultar antes de tocar una plantilla o un contrato `hx-*`** |
| `src/zascarr/LEGAL.md` | Marco legal activo; si se actualiza, hay que el mismo día versionar/rehacer `legal_version` en services/legal.py (hash del fichero) |
| `pyproject.toml` | Fuente única de metadatos del paquete (nombre, license, deps) |
| `docs/design/benchmark-referencias.md` | Procedimiento y ficha para comparar referencias antes de features P0/P1 (ver §13) |
| `docs/design/contrato-307-formato-por-contenido.md` | Contrato de **formato por contenido** (#307): un único punto de decisión (`core/formato_contenedor.py`); `file_format` es la extensión **declarada**, el formato real va en `files.metadata["formato_contenido"]`. **Consultar antes de tocar `triage`, la portada o la auditoría de formatos** |
| `docs/design/registro-incremental-326.md` | **Registro incremental** (#326): buscar y registrar archivos nuevos de una biblioteca ya registrada, a mano y con confirmación; «nuevo» = ruta sin fila; sin automatismo. **Consultar antes de tocar `LibraryAdopter.adopt`, `registro_biblioteca` o el bloque «Registro» de la Auditoría** |
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

---

*Documento vivo. Cada decisión nueva que afecte a "cómo trabajamos" se
registra aquí el día que se decide, no cuando la recuerda alguien.*
