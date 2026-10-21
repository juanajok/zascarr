# U15 — Verificación de presentación en navegador real (2026-10-21)

> **Estado: PASS de presentación en Chrome real para CA4 y para el escenario «elección explícita» de CA6.**
> Esta comprobación **no cierra #202**: la ausencia de sugerencia y la procedencia siguen bloqueadas por el contrato
> actual y se trabajan en **#276 (U15b)**. Tampoco es una validación con personas: es una verificación de renderizado y
> comportamiento en un navegador, con datos reales de GCD y Tebeosfera.

## 1. Qué se comprueba

1. Que la búsqueda real pinta las tarjetas con la pista de la fuente y **sin tradición preseleccionada**.
2. Que el texto aplicado es el acordado: «La fuente lo clasifica como X. Es solo una pista de la fuente, no de la
   obra: elige tú.».
3. Que a 360 px no hay desbordamiento horizontal y la tarjeta sigue siendo usable.
4. Que, cuando la fuente sugiere «Tebeo español» y la persona elige «Manga», la vista previa muestra **Manga** y no
   escribe ninguna serie.

No se prueba el alta definitiva desde el navegador: habría creado una serie en la base de verificación y el contrato de
creación ya está cubierto por las pruebas de Postgres. Tampoco se prueban la ausencia de sugerencia ni la procedencia
(impedimento contractual, #276).

## 2. Entorno

| Elemento | Valor |
|---|---|
| Repositorio / commit | `juanajok/zascarr` @ `a2721722a0cff54dfe7a4e878a528f43b21a602e` (`origin/main` tras fusionar la PR #273) |
| Aplicación | `PYTHONPATH="$PWD/src" uvicorn zascarr.main:app`, un worker, `http://127.0.0.1:8766` |
| Entorno Python | venv `/tmp/opencode/zascarr-venv`; su editable install apunta a otro worktree, por eso se fuerza `PYTHONPATH` |
| Base de datos | PostgreSQL 15.19, base **nueva** `zascarr_verify_u15_main`, `alembic upgrade head` |
| Fuentes | GCD y Tebeosfera **activas**; Comic Vine y AniList desactivadas (sin clave / 403) |
| Navegador | Google Chrome **154.0.8037.92**, modo headless, motor real (no una simulación de HTML) |
| Automatización | Playwright **1.64.0** sobre Python **3.14.4** |
| Sistema | Linux 7.0.0-38-generic x86_64 |
| Viewports | 1280 × 900 y 360 × 800, locale `es-ES` |
| Autenticación | `AUTH_MODE=none`, solo `127.0.0.1`; la Pi no se ha tocado |
| Consulta | `Mortadelo` |
| Fecha de la captura | 2026-10-21T16:57:57Z |

La app se arrancó con una biblioteca y una caché de portadas temporales (`/tmp/opencode/...`), no con la biblioteca real.
El resumen legible por máquina está en [`verificacion-navegador.json`](verificacion-navegador.json).

**Nota de entorno:** el venv del proyecto tiene un editable install que apunta a otro worktree. Sin
`PYTHONPATH="$PWD/src"`, `uvicorn` importaría el paquete de ese otro árbol y la evidencia no correspondería al SHA
`a2721722`. Los comandos de §3 incluyen la variable; la ejecución de esta evidencia la usó. La rama de evidencia
solo añade documentación sobre ese código.

## 3. Montaje reproducible

```bash
# Base de datos desechable
docker exec zascarr-u19-pg psql -U test -d postgres \
  -c "DROP DATABASE IF EXISTS zascarr_verify_u15_main;" \
  -c "CREATE DATABASE zascarr_verify_u15_main;"

PYTHONPATH="$PWD/src" \
DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:15450/zascarr_verify_u15_main' \
  /tmp/opencode/zascarr-venv/bin/alembic upgrade head

# App local; no usa la biblioteca real
PYTHONPATH="$PWD/src" \
DATABASE_URL='postgresql+asyncpg://test:test@127.0.0.1:15450/zascarr_verify_u15_main' \
SECRET_KEY="$(openssl rand -hex 32)" \
LIBRARY_PATH='/tmp/opencode/zascarr-u15-verify/library' \
COVERS_CACHE_PATH='/tmp/opencode/zascarr-u15-verify/covers' \
GCD_ENABLED=true TEBEOSFERA_ENABLED=true ANILIST_ENABLED=false COMICVINE_ENABLED=false \
AUTH_MODE=none \
  /tmp/opencode/zascarr-venv/bin/uvicorn zascarr.main:app --host 127.0.0.1 --port 8766 --loop asyncio
```

La verificación se ejecutó con el script del repositorio, no con clics manuales sin traza:

```bash
/tmp/opencode/zascarr-venv/bin/pip install playwright==1.64.0
/tmp/opencode/zascarr-venv/bin/python docs/design/ui-u15/verificar_navegador.py \
  --base-url http://127.0.0.1:8766 \
  --out /tmp/opencode/zascarr-u15-verify-final \
  --sha a2721722a0cff54dfe7a4e878a528f43b21a602e
```

El script busca, espera a que htmx pinte los resultados, comprueba los selectores, hace las capturas, elige «Manga» en
una tarjeta con pista «Tebeo español» y pulsa «Revisar». **No pulsa «Crear serie vacía».**

## 4. Resultado

### 4.1 Búsqueda real: pista visible y ninguna preselección

![Búsqueda de Mortadelo en Descubrir, 1280 px](capturas/2026-10-21-descubrir-mortadelo-1280.png)

- **20 tarjetas**, **20 selectores** de tradición.
- **20/20** son `required`, tienen `value=""` y solo el marcador vacío está seleccionado.
- **0/20** traen una tradición preseleccionada.
- **20/20** llevan el texto completo. El valor de la pista es «Tebeo español» en **19** tarjetas y «Otra» en **1**;
  «Otra» es un valor que devuelve la fuente, no un valor inventado por la UI. El texto nunca aplica ese valor al
  selector.
- La primera tarjeta es **«ALEGRES HISTORIETAS (1980)»** (Tebeosfera), no «Mortadelo». Es un problema de relevancia de
  la fuente, ya observado en la medición; no afecta a la conclusión de esta comprobación: la sugerencia es texto y la
  persona elige.

### 4.2 Móvil: 360 px sin desbordamiento horizontal

![Búsqueda de Mortadelo en Descubrir, 360 px](capturas/2026-10-21-descubrir-mortadelo-360.png)

Medido en el navegador: `window.innerWidth = 360`, `documentElement.clientWidth = 360`,
`documentElement.scrollWidth = 360` y `body.scrollWidth = 360`. La tarjeta, el selector, el botón y el texto caben en el
ancho; no hay scroll horizontal. La barra inferior fija puede tapar contenido al hacer una captura de página completa,
pero no genera desbordamiento.

### 4.3 Elección explícita: la persona manda sobre la pista

En la tarjeta «ALEGRES HISTORIETAS (1980)», cuya fuente sugiere **Tebeo español**, se eligió **Manga** y se pulsó
«Revisar». La vista previa (sin escribir) muestra:

> Se guardará como «ALEGRES HISTORIETAS» (1980). **Tradición elegida: Manga.**

![Vista previa tras elegir Manga](capturas/2026-10-21-descubrir-revision-manga-1280.png)

Comprobación adicional: `select count(*) from series` seguía en **0** después de la vista previa. No se creó ninguna
serie. La creación real con la tradición elegida está cubierta por
`tests/test_descubrir_dos_pasos_pg.py::TestCrear::test_crea_la_serie_con_la_tradicion_elegida_el_identificador_protegido_y_la_procedencia`.

## 5. Trazabilidad con #202

| Criterio / escenario | Antes | Ahora |
|---|---|---|
| CA4: no preseleccionar; explicar en español que la persona elige | PASS con pruebas HTML/Postgres | **PASS también en Chrome real**: 20/20 vacíos, texto presente, elección explícita respetada |
| CA6 «Elección explícita de la persona» | PASS en Postgres | **PASS en Chrome real**: pista Tebeo español → elección Manga → vista previa Manga; 0 series escritas |
| CA6 «Ausencia de sugerencia» | IMPEDIMENTO contractual | **Sigue IMPEDIMENTO**; no se simula con `other`. Trabajo separado: #276 |
| CA6 «Origen desconocido» / procedencia | PASS con límite | Sin cambios: el contrato no expone procedencia; #276 |
| Cierre de #202 | Abierta | **Sigue abierta**; esta PR es evidencia parcial, no cierra la historia |

## 6. Límites

- **Chrome real, pero headless**: el motor y el DOM son los de Chrome; no hay una persona mirando la pantalla ni una
  comprobación manual con ratón. Si el PO exige una pasada manual, es un paso adicional, no lo que aquí se declara.
- **Una consulta (`Mortadelo`) y una elección explícita**: no es una muestra representativa ni una tasa de acierto.
- **Solo GCD y Tebeosfera**: Comic Vine y AniList siguen **NOT RUN** (sin clave / 403). No se extrapola su
  comportamiento.
- **Sin lector de pantalla ni teclado**: esta pasada no sustituye las comprobaciones de accesibilidad de U21; solo mide
  presentación y flujo de elección de U15.
- **Sin despliegue**: no se toca la Pi. #202 no se marca «Hecha» por esta verificación.

## 7. Archivos

- `verificar_navegador.py` — script reproducible (Playwright + Chrome del sistema).
- `verificacion-navegador.json` — resumen de la ejecución: commit, navegador, viewports, 20 tarjetas, 20 selectores,
  0 preselecciones, pistas y elección.
- `capturas/2026-10-21-descubrir-mortadelo-1280.png` — búsqueda completa en escritorio.
- `capturas/2026-10-21-descubrir-mortadelo-360.png` — búsqueda completa en móvil.
- `capturas/2026-10-21-descubrir-revision-manga-1280.png` — vista previa tras elegir Manga.
- `medicion.md` — ficha de U15 y mapeo 1:1 a los criterios de #202.
