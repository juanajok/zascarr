# CLAUDE.md — Guía de trabajo para ZascArr

> Contexto operativo para agentes y personas que colaboren en este repo.
> Lee esto antes de tocar código. Si algo nuevo se decide en un hilo de
> trabajo y no figura aquí, **acaba ese hilo añadiéndolo aquí**.

---

## 1. Qué es este proyecto

ZascArr es un gestor self-hosted de tebeoteca (CBZ/CBR) tipo Sonarr/Radarr,
optimizado para Raspberry Pi 4/5 y pensado para el público hispanohablante.
Stack: **FastAPI + SQLAlchemy async + PostgreSQL + Redis + Jinja2 + HTMX**.
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
   después. Pendiente de auditar en `ReviewService.assign_to_series` y el
   importer (ver BACKLOG pendientes).
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
- Integraciones P2P deshabilitadas por defecto (`FORUM_ENABLED=false` y
  análogos): el usuario opta, la app no facilita por defecto. Patrón
  explicado en `LEGAL.md`.
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
  cultural sin ánimo de lucro, no cuestión de bugs.
- **Caché local-first.** Portadas, metadatos, TODO se escribe a disco/BD
  y se sirve local después. Endpoints de imagen llevan `Cache-Control:
  private, max-age=86400` + `ETag` por mtime (`utils/cover.py::
  cached_image_response`).
- El refresco periódico del orchestrator/importer usa Redis como canal,
  no polling contra la BD.

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
   `Cache-Control` y `X-Legal-Redirect` documentados en `api/legal.py`.

## 6. UX

- **Todo en español llano para el coleccionista**: el dashboard y las
  instrucciones del wizard placan eso. Errores tipo "exit code 1" están
  prohibidos en superficie de usuario: se mapean a causa y acción (historia
  A2).
- **Semáforos visibles** para el estado del sistema (`/api/health`), texto
  concreto sobre qué falló y qué hacer.
- **Sin diálogos nativos ni balas invisible**: `hx-confirm` ya se sabe que
  la automatización del navegador no lo resuelve; el usuario real sí.
  Documentado como limitación aceptada en B2.
- Tarjetas con gracia de fallo: portada rota = placeholder CSS
  `.cover-missing`, no imagen rota; campo ausente con icono claro.

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
- **Ninguna dependencia nueva por "testing"**: los tests existentes ya
  cubren casos de UI-legal sin necesidad de BD (el hallazgo del wizard
  legal se cerró así).
- La única excepción a FakeSession: `test_title_norm.py` sí toca
  Postgres real, marcada skip sin TEST_DATABASE_URL.
- Cada bug real (sort_order truncado, mass assignment) se cierra con
  **test de regresión explícito** nombrado con el mecanismo del bug.
- Tests asíncronos: `pytest.mark.asyncio`, nunca asyncio.run() dentro.

## 9. Git y ramas

- Commit pequeño y atómico; un cambio de dominio por commit ("rename:
  SecuenciArr → ZascArr" fue un commit, no repartido en 10).
- Mensajes en español en el formato `<área>: <qué> (<porqué> si no es
  obvio)`.
- No commitear cosas de depuración local (`.env`, *.prof, dumps).
- El histórico es documentación: cuando cierras una historia P0/P1 del
  backlog, actualiza `docs/BACKLOG.md` a "Hecho" con la nota del
  mecanismo ("cómo se cerró, no solo que se cerró").

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
| `docs/adr/0001-ui-stack.md` | Stack de UI y razonamiento |
| `LEGAL.md` | Marco legal activo; si se actualiza, hay que el mismo día versionar/rehacer `legal_version` en services/legal.py (hash del fichero) |
| `pyproject.toml` | Fuente única de metadatos del paquete (nombre, license, deps) |
| `docs/PLAN_RELEASE_1.0.md` | Cola ordenada de release (creada con PO 2026-09-22) |

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

---

*Documento vivo. Cada decisión nueva que afecte a "cómo trabajamos" se
registra aquí el día que se decide, no cuando la recuerda alguien.*
