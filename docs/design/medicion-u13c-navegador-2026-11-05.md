# Medición en navegador real — U13c (#289)

> **Estado:** medición local en navegador real **registrada**. **No** declara el `PASS` de rendimiento
> del entorno de referencia (Pi 4/5 + LAN): eso sigue **NOT RUN**. No rebaja ningún umbral.
> **SHA medido:** `14af5d802f51037e89e19acc474cdd1f7cab654b` (`origin/main`), en un
> *worktree* aislado `.squad/wt-327` (el árbol principal está en otra rama).
> **Fecha:** 2026-11-05. **Casilla:** #327, casilla 2 (la medición de #289 que quedó NOT RUN).
> **Protocolo de referencia:** `docs/design/ui-u13/medicion-u13c-2026-10-23.md` (fixture de 155
> archivos, 2 calentamientos + 20 medidas, p95 por rango más cercano, fría aparte) y presupuesto de
> `docs/design/ui-u13/u13c-contraste-dor-289.md` §6.4: **P1 p95 ≤ 1.500 ms**, **P2 p95 ≤ 900 ms**.

## 1. Entorno

| Pieza | Valor |
|---|---|
| Máquina | Intel Core i5-8365U, 8 CPU lógicas, 1,60 GHz; 30 GiB de RAM (la misma del protocolo) |
| Sistema | Ubuntu 26.04.1 LTS, Linux 7.0.0-38-generic, x86_64 |
| Navegador | **Google Chrome 156.0.8078.47, headless**; DPR 1; ventana real **1280×900** (viewport 1280×813) |
| Emulación | **Ninguna**: no se llamó a `Emulation.setDeviceMetricsOverride` ni hay *throttle* de red/CPU. La ventana se fija con `Browser.setWindowBounds` |
| Servidor | `uvicorn` 0.54.0 local, `--lifespan off`, `127.0.0.1:18101` (**loopback**, sin LAN) |
| Base de datos | PostgreSQL **16.15** en contenedor Docker desechable, migrada a `head` (0020) |
| Python | 3.14.4 |
| Datos | Fixture sintético de **155 archivos reales en disco**; sin biblioteca real, sin red externa |
| Herramienta | Script propio por CDP con `websockets` (`medir289.py`); sin Playwright ni dependencia nueva |
| Autenticación | `AUTH_MODE=none`, solo para la prueba local |

## 2. Método

### 2.1. Fixture

- **155 archivos reales en disco** en `Comics/Flash 155 (1987)` (`Flash 155 001 (1987).cbz` …
  `Flash 155 155 (1987).cbz`), todos pendientes de la población A de la revisión
  (`issue_id NULL`, `review_dismissed = false`, `metadata.match_status = "unsorted"`).
- Serie local **`Flash 155 (1987)`**, sin números ni vínculos, para que la revisión los trate como
  «se vincularía» sin conflictos de calidad.
- Página 1 = **100 filas** (`LIMITE_ARCHIVOS = 100`); página 2 = **55 filas**. Verificado en cada
  medida: 100 y 55 filas, primera fila de la página 2 = `Flash 155 101 (1987).cbz`.
- La respuesta de la revisión lleva `Cache-Control: no-store`; HTML de la página 1 ≈ **454.590 bytes**
  decodificados; fragmento de la página 2 ≈ **181.951 bytes**.

### 2.2. Qué se mide y con qué marcas

Todo en `performance.now()` relativo a `navigationStart` (`performance.timeOrigin`).

**P1 — primera revisión** (`GET` de la revisión, sin marcas ni números editados):

- **Marca primaria `t_visible`:** `performance.now()` en el **segundo callback de
  `requestAnimationFrame`** después de que (a) exista `#revision .vinculacion-lista` con sus
  `.vinc-fila` y (b) el navegador haya emitido `first-contentful-paint` (se sondea
  `performance.getEntriesByType('paint')`; si no llega FCP en 5 s, la medida se descarta).
  Es una **cota conservadora** del «contenido visible»: siempre es ≥ FCP.
- **Secundarias:** `first-contentful-paint` (FCP) y `largest-contentful-paint` (LCP) de la línea de
  tiempo del navegador (`PerformanceObserver` con `buffered: true`), y los campos de
  `Navigation Timing` (`requestStart`, `responseStart`, `responseEnd`, `DOMContentLoaded`, `load`).
- Cada navegación lleva un parámetro `&med=N` no interpretado por la app, para forzar una
  navegación completa nueva (nunca una restauración del mismo documento).

**P2 — cambio a la página 2** (`POST` HTMX a `/ui/pendientes/carpetas/asistente/vinculacion/revisar`
con `ir_a` al cursor de la página 2, con `HX-Request`):

- Con la página 1 cargada y 100 filas presentes se hace un **clic real** en el botón de envío
  «Página siguiente →» (`.vinculacion-paginas button[name="ir_a"]`), no una petición fabricada.
- **Marca primaria `click_a_visible`:** `t0 = performance.now()` justo antes del clic → `t1 =
  performance.now()` en el **segundo `requestAnimationFrame` después de que un `MutationObserver`
  detecte que `#revision` ha sido sustituido** por el fragmento nuevo. Se comprueba que el nuevo
  `#revision` tiene **55 filas** y que la primera es la 101; si no, la medida se descarta.
- **Secundaria:** `Resource Timing` de la petición `POST` (`requestStart`, `responseStart`,
  `responseEnd`, `duration`, `decodedBodySize`).
- Cada medida de P2 se toma tras **recargar la página 1** (preparación no medida), para que el clic
  parta siempre del mismo estado.

### 2.3. Repeticiones, fría y estadístico

- **2 calentamientos + 20 medidas por escenario.** Los calentamientos no se registran.
- **p95 por rango más cercano:** con n = 20, `k = ceil(0,95·20) = 19` → **19.º valor ordenado**;
  p50 = 10.º valor ordenado.
- **Fría P1:** primera navegación después de arrancar `uvicorn`, con **perfil de Chrome nuevo**
  (caché del navegador vacía). Incluye, por tanto, proceso del servidor frío y caché del navegador
  vacía; no se usa para declarar el presupuesto.
- **Fría P2:** primer `POST /revisar` de la tanda, justo después de cargar la página 1 para poder
  pulsar. El proceso ya no está frío (lo calentó P1): un POST no puede ser «frío de proceso» sin un
  GET previo. Se documenta y **no se usa para el veredicto**.
- Sin límites de CPU ni de red; cliente y servidor en la misma máquina por loopback.

## 3. Resultados

| Escenario | p50 | **p95** | mín. | máx. | media | Fría | n | Umbral p95 | Veredicto local |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **P1 — primera revisión** | 299,8 ms | **332,6 ms** | 283,1 ms | 342,1 ms | 302,7 ms | **789,4 ms** | 20 | ≤ 1.500 ms | **PASS local** |
| **P2 — cambio de página** | 132,0 ms | **196,6 ms** | 119,8 ms | 214,9 ms | 142,9 ms | **121,8 ms** | 20 | ≤ 900 ms | **PASS local** |

**Datos secundarios (misma tanda):**

| Dato | P1 | P2 |
|---|---|---|
| FCP p50 / p95 | 228,0 / 268,0 ms | — |
| LCP p50 / p95 | 228,0 / 268,0 ms (coincide con FCP en las 20 medidas) | — |
| `responseStart` (P1) / `duration` del POST (P2), p50 / p95 | 50,1 / 80,6 ms | 63,0 / 87,4 ms |
| `DOMContentLoaded` p50 / p95 | 84,1 / 187,9 ms | — |
| De `responseEnd` a visible (P2), p50 / p95 | — | 66,8 / 109,5 ms |

Lectura: en caliente, el servidor tarda ~50 ms en empezar a responder la página completa y ~63 ms
en devolver el fragmento; el resto hasta «contenido visible» es descarga + *parseo* + pintado en el
navegador. Con 155 archivos, el margen local es amplio: **P1 4,5×** y **P2 4,6×** por debajo del
umbral. No hay señal de que haga falta optimizar ni trocear.

## 4. PASS / FAIL

| Comprobación | Resultado |
|---|---|
| **P1** en navegador real local, p95 ≤ 1.500 ms | **PASS local** (332,6 ms) |
| **P2** en navegador real local, p95 ≤ 900 ms | **PASS local** (196,6 ms) |
| **DoD en entorno de referencia (Pi 4/5 + LAN + Chromium de la Pi)** | **NOT RUN** |
| Fría P1 como dato informativo (< 1.500 ms) | 789,4 ms, por debajo; no se usa para el PASS |

**No hay FAIL.** Lo que hay es un **PASS local** en navegador real (mismo hardware y misma familia
que el protocolo) y un **NOT RUN del DoD**: la Pi, su Chromium y la latencia de LAN no se han medido
y no se pueden inferir de estos números. El presupuesto no se rebaja; el margen local es la evidencia
disponible, no la aceptación final.

## 5. Límites

- **No es la Pi ni su LAN**: cliente y servidor comparten máquina; la latencia de red es de loopback.
- **Navegador**: Chrome 156 de escritorio *headless*, no el Chromium de la Pi; ventana de 1280×900.
- **Caché**: los calentamientos dejan caché de navegador caliente; solo la fría arranca con perfil
  nuevo. Las medidas de P1 no repiten la descarga de CSS y fuentes.
- **Datos sintéticos**: 155 archivos reales en disco, sin biblioteca real ni fuentes externas.
- **Fuera de esta medición**: lector de pantalla, teclado, prueba de cinco segundos, rendimiento en
  la Pi y despliegue (siguen NOT RUN; este documento solo mide rendimiento de navegador).
- La comprobación de que la página 2 tiene 55 filas y empieza por la 101 se hizo en cada medida; no
  se ha validado aquí el resultado funcional de confirmar la vinculación (tiene sus propias pruebas
  y verificación de navegador).

## 6. Reproducción

1. *Worktree* `git worktree add --detach .squad/wt-327 origin/main` (`14af5d8`).
2. PostgreSQL 16 desechable, migrado a `head` con `alembic upgrade head`.
3. `sembrar155.py` crea la serie local y los 155 archivos reales en `Comics/Flash 155 (1987)`.
4. `uvicorn zascarr.main:app --host 127.0.0.1 --port 18101 --lifespan off` con
   `AUTH_MODE=none`, `LIBRARY_PATH` al fixture y `SECRET_KEY` de un solo uso.
5. Chrome headless con CDP; `medir289.py` hace 2 calentamientos + 20 medidas por escenario, guarda
   `mediciones-289.json`, la captura de la página 1 y la de la página 2.

Rig, capturas y datos crudos (untracked, sin commit): `.ux327-scratch/`
(`sembrar155.py`, `fixture155.json`, `medir289.py`, `mediciones-289.json`,
`p1-revision-1280.png`, `p2-pagina2-1280.png`, `entorno-289.txt`). El *worktree* es
`.squad/wt-327`; el árbol principal no se ha tocado para la medición (este documento es el único
fichero añadido, y queda sin commitear).

## 7. Anexo — valores individuales

**P1, `t_visible` (ms), 20 medidas:**
283,5 · 317,0 · 283,5 · 283,7 · 300,2 · 283,7 · 300,4 · 332,6 · 283,1 · 299,9 · 316,7 · 299,3 ·
342,1 · 316,2 · 299,8 · 283,1 · 315,4 · 298,7 · 299,4 · 315,7

**P2, `click_a_visible` (ms), 20 medidas:**
140,1 · 214,9 · 127,9 · 132,0 · 127,6 · 154,0 · 196,6 · 124,8 · 128,2 · 123,1 · 138,6 · 123,3 ·
119,8 · 128,7 · 152,4 · 149,8 · 129,2 · 132,4 · 160,1 · 154,8

**Fría P1:** `t_visible` 789,4 ms; FCP/LCP 648,0 ms; `responseStart` 308,6 ms; HTML 454.590 bytes.
**Fría P2:** `click_a_visible` 121,8 ms; POST `duration` 54,6 ms; fragmento 181.951 bytes.
