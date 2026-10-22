# U15 — Verificación del contrato #276 en navegador real (2026-10-22)

> **Estado: PASS de presentación en Chrome real para la copy con procedencia y para la ausencia de
> sugerencia.** Se ejecutó contra `origin/main` `bf67699` (merge de #281), con GCD y Tebeosfera reales.
> No es una validación con personas ni sustituye los NOT RUN de Comic Vine y AniList. #202 sigue abierta
> hasta que el responsable firme la decisión de los NOT RUN y se proponga su cierre.

## 1. Qué se comprueba

1. La copy de #276 en una búsqueda real de `Mortadelo`: procedencia `por_defecto` (Tebeosfera) y
   `transformada` (GCD), sin preselección.
2. Una tarjeta GCD con `tradition_guess: None`: **no** muestra texto de pista y su selector sigue
   obligatorio, vacío y sin tradición seleccionada.
3. La elección explícita sigue mandando: sobre una pista «Tebeo español» se elige «Manga», la vista
   previa muestra Manga y la procedencia como contexto, y no se escribe ninguna serie.
4. A 360 px no hay desbordamiento horizontal.

No se prueba el alta definitiva desde el navegador. La creación con la tradición elegida está cubierta
por `tests/test_descubrir_dos_pasos_pg.py`; aquí la base de verificación quedó con **0 series** y
**0 altas**.

## 2. Entorno

| Elemento | Valor |
|---|---|
| Código de producto | `juanajok/zascarr` @ `bf6769967ccbed8f6f229eb586b28edb32576c23` (`origin/main` tras #281) |
| Script de evidencia | `docs/design/ui-u15/verificar_navegador.py` de la rama `sprint0/u15-cierre` |
| Aplicación | `PYTHONPATH="$PWD/src" uvicorn zascarr.main:app`, un worker, `http://127.0.0.1:8768` |
| Entorno Python | venv `/tmp/opencode/zascarr-venv`; se fuerza `PYTHONPATH` para no usar el editable de otro worktree |
| Base de datos | PostgreSQL 15.19, base nueva `zascarr_verify_u15_cierre`, `alembic upgrade head` |
| Fuentes | GCD y Tebeosfera **activas**; Comic Vine y AniList **desactivadas** (sin clave / 403) |
| Navegador | Google Chrome **154.0.8037.92**, headless, motor real |
| Automatización | Playwright **1.64.0** sobre Python **3.14.4** |
| Sistema | Linux 7.0.0-38-generic x86_64 |
| Viewports | 1280 × 900 y 360 × 800, locale `es-ES` |
| Autenticación | `AUTH_MODE=none`, solo `127.0.0.1`; la Pi no se ha tocado |
| Consultas | `Mortadelo` (copy y elección) y `Lucky Luke` (ausencia de sugerencia en GCD) |
| Fecha | 2026-10-22T09:50:42Z |

La app usó una biblioteca y una caché de portadas temporales, no la biblioteca real. El resumen
legible por máquina está en [`verificacion-navegador-2026-10-22.json`](verificacion-navegador-2026-10-22.json).

## 3. Montaje reproducible

```bash
# Base de datos desechable
docker exec zascarr-u19-pg psql -U test -d postgres \
  -c "DROP DATABASE IF EXISTS zascarr_verify_u15_cierre;" \
  -c "CREATE DATABASE zascarr_verify_u15_cierre;"

PYTHONPATH="$PWD/src" \
DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:15450/zascarr_verify_u15_cierre' \
  /tmp/opencode/zascarr-venv/bin/alembic upgrade head

# App local; no usa la biblioteca real
PYTHONPATH="$PWD/src" \
DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:15450/zascarr_verify_u15_cierre' \
SECRET_KEY="$(openssl rand -hex 32)" \
LIBRARY_PATH='/tmp/opencode/zascarr-u15-cierre/library' \
COVERS_CACHE_PATH='/tmp/opencode/zascarr-u15-cierre/covers' \
GCD_ENABLED=true TEBEOSFERA_ENABLED=true ANILIST_ENABLED=false COMICVINE_ENABLED=false \
AUTH_MODE=none \
  /tmp/opencode/zascarr-venv/bin/uvicorn zascarr.main:app --host 127.0.0.1 --port 8768 --loop asyncio

# Verificación
/tmp/opencode/zascarr-venv/bin/python docs/design/ui-u15/verificar_navegador.py \
  --base-url http://127.0.0.1:8768 \
  --out /tmp/opencode/zascarr-u15-cierre/evidence \
  --sha bf6769967ccbed8f6f229eb586b28edb32576c23
```

El script busca con htmx, comprueba los selectores, hace las capturas, elige «Manga» en una tarjeta
con pista «Tebeo español» y pulsa «Revisar». **No pulsa «Crear serie vacía».**

## 4. Resultado

### 4.1 `Mortadelo`: copy con procedencia y ninguna preselección

![Búsqueda de Mortadelo, 1280 px](capturas/2026-10-22-descubrir-mortadelo-1280.png)

- **20 tarjetas**, **20 selectores**.
- **20/20** `required`, con `value=""` y solo el marcador vacío seleccionado.
- **0/20** con tradición preseleccionada.
- **19 pistas**: **10** con `por_defecto` («La fuente no indica tradición: se sugiere Tebeo español
  por defecto…») y **9** con `transformada` («La fuente no usa esta tradición: a partir de sus datos
  se sugiere Tebeo español…»). Las 19 conservan la frase común «Es solo una pista de la fuente, no de
  la obra: elige tú.».
- **1 tarjeta sin pista**: «Mortadelo e Salaminho (1969)», de GCD. Es una tarjeta con
  `tradition_guess: None`; no se muestra ningún `<small>` ni texto de pista.

Comprobación directa de la API de GCD el mismo día (no forma parte de la app):

| Tarjeta | `language` | `country` | Mapeo en `gcd.py` |
|---|---|---|---|
| Mortadelo e Salaminho (1969) | `pt` | `br` | Ninguno: `pt` no está en `_LANGUAGE_TRADITION` → `None` |
| De avonturen van Lucky Luke (2004) | `nl` | `fr` | Ninguno: `nl` no está en `_LANGUAGE_TRADITION` → `None` |

Así, la ausencia viene de un idioma/país real no reconocido, no de sustituir `other` por `None` en la
presentación.

![Tarjeta GCD sin sugerencia en Mortadelo](capturas/2026-10-22-descubrir-mortadelo-gcd-sin-sugerencia-1280.png)

### 4.2 Móvil: 360 px sin desbordamiento

![Búsqueda de Mortadelo, 360 px](capturas/2026-10-22-descubrir-mortadelo-360.png)

Medido en el navegador: `window.innerWidth = 360`, `documentElement.clientWidth = 360`,
`documentElement.scrollWidth = 360` y `body.scrollWidth = 360`. No hay scroll horizontal.

### 4.3 La elección explícita manda y la procedencia es contexto

En «ALEGRES HISTORIETAS (1980)» (Tebeosfera, `por_defecto`) se eligió **Manga** y se pulsó «Revisar».
La vista previa, sin escribir, muestra:

> Se guardará como «ALEGRES HISTORIETAS» (1980). **Tradición elegida: Manga.**
>
> Procedencia de la sugerencia: valor por defecto: la fuente no lo indica. La tradición aplicada es la
> que elegiste.

![Vista previa tras elegir Manga](capturas/2026-10-22-descubrir-revision-manga-1280.png)

La base de verificación siguió con **0 series** y **0 altas**. La creación real está cubierta por la
prueba de Postgres citada en §1.

### 4.4 `Lucky Luke`: siete tarjetas GCD sin sugerencia

![Búsqueda de Lucky Luke con tarjetas GCD sin pista](capturas/2026-10-22-descubrir-lucky-luke-gcd-sin-sugerencia-1280.png)

- **20 tarjetas** (10 GCD y 10 Tebeosfera); **7 tarjetas GCD** sin `<small>` de pista.
- Las 7 tienen el selector `required`, `value=""` y solo el marcador vacío seleccionado.
- No aparecen tarjetas sin pista de otra fuente: las 10 de Tebeosfera llevan su pista `por_defecto`.
- La consulta demuestra además que la ausencia no se simula con `other`: el contrato devuelve `None`
  y la plantilla no inventa un texto.

## 5. Trazabilidad con #202

| Criterio / escenario | Evidencia | Estado |
|---|---|---|
| CA4: no preseleccionar y explicar que la persona elige | 20/20 selectores vacíos y obligatorios; copy completa en las 19 pistas | **PASS en Chrome real** |
| CA6 «Dato explícito respaldado» | Pruebas de `test_web_discovery.py` y `test_asistente_carpetas_pg.py` (AniList no disponible en vivo) | **PASS automático** |
| CA6 «Sugerencia no fiable» | 10 tarjetas Tebeosfera con `por_defecto` y 9 GCD con `transformada`; ninguna aplicada | **PASS en Chrome real** |
| CA6 «Origen desconocido» | Token antiguo y prueba de presentación (`test_tokens_revision.py`) | **PASS automático**; no se fuerza en vivo |
| CA6 «Ausencia de sugerencia» | 1 tarjeta GCD sin pista en Mortadelo; 7 en Lucky Luke; selector vacío | **PASS en Chrome real** |
| CA6 «Elección explícita de la persona» | Pista Tebeo español → elección Manga → vista previa Manga; 0 series | **PASS en Chrome real y Postgres** |
| Comic Vine / AniList | Sin clave / 403; no se ejecutaron | **NOT RUN**, no PASS |

## 6. Límites

- **Chrome real, pero headless**: el motor y el DOM son los de Chrome; no hay una persona mirando la
  pantalla ni una comprobación manual con ratón. No sustituye una prueba con personas.
- **Una sesión y dos consultas**: no es una muestra representativa ni una tasa de acierto.
- **Sin AniList ni Comic Vine**: la procedencia `explicita` no se ejercita en vivo; queda cubierta por
  pruebas automáticas. No se extrapola el comportamiento de esas fuentes.
- **Sin lector de pantalla ni teclado**: esta pasada no sustituye las comprobaciones de accesibilidad de
  U21; solo mide presentación y flujo de elección de U15.
- **Sin despliegue**: no se toca la Pi. #202 no se marca «Hecha» por esta verificación; el cierre exige
  la decisión firmada sobre los NOT RUN.

## 7. Archivos

- `verificar_navegador.py` — script reproducible, adaptado a la copy de #276 y a la tarjeta GCD `None`.
- `verificacion-navegador-2026-10-22.json` — resumen de la ejecución: SHA, navegador, viewports,
  20 tarjetas, 20 selectores, 0 preselecciones, procedencias, elección y tarjetas GCD sin pista.
- `capturas/2026-10-22-descubrir-mortadelo-1280.png` — búsqueda completa en escritorio.
- `capturas/2026-10-22-descubrir-mortadelo-360.png` — búsqueda completa en móvil.
- `capturas/2026-10-22-descubrir-revision-manga-1280.png` — vista previa tras elegir Manga.
- `capturas/2026-10-22-descubrir-mortadelo-gcd-sin-sugerencia-1280.png` — tarjeta GCD sin pista.
- `capturas/2026-10-22-descubrir-lucky-luke-gcd-sin-sugerencia-1280.png` — siete tarjetas GCD sin pista.
- `decision-u15-not-run-2026-10-22.md` — propuesta de decisión de los NOT RUN para firma del responsable.
