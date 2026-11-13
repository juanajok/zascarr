# SecOps — Revisión de seguridad y legal de la integración Fandom (SCR2, #703)

**Rol:** SecOps · **Tarea:** task-5 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Árbol revisado:** *working tree* sobre `main` (`17a5995e`) con los cambios de SCR2 **sin commitear**
(20 ficheros modificados + 5 nuevos: `services/fandom.py`, `web/atribucion.py`,
`templates/_atribucion_fandom.html`, `tests/test_fandom.py`, `alembic/versions/20261113_0036_fandom_slugs.py`).
La rama `feat/fandom-fuentes` no contiene estos cambios; **este informe no dictamina ningún SHA**.
**Entorno:** `PYTHONPATH=src .tmp-test-venv/bin/python` (Python 3.14), sin `TEST_DATABASE_URL`.
**Alcance:** SSRF/red, apagado por defecto, marco legal y atribución, logs, robustez de parseo (ReDoS),
hotlinking, cortesía/`maxlag`, dependencias. **No se ha modificado código, tests ni configuración**;
este informe es el único fichero escrito.

> **Condición de proceso (CLAUDE.md §5.8).** El cambio toca `src/zascarr/web/ajustes.py` (toggles de
> las dos wikis). Esa regla exige la pasada final de SecOps **sobre el SHA final** que se fusione,
> aunque ya exista este informe sobre el árbol de trabajo. Este documento **no sustituye** ese dictamen.

---

## 0. Veredicto

**Favorable a fusionar: 0 bloqueantes, 1 mayor, 6 menores.**

No se ha encontrado ningún SSRF, ninguna descarga externa que esquive `utils/url_portada.py`, ninguna
fuente encendida por defecto, ni incumplimiento del doble enlace CC-BY-SA 3.0 que exige `LEGAL.md`.
El hash de `legal_version` invalida solo la aceptación anterior al cambiar `LEGAL.md` (verificado:
`77e66dcf43b13b5a` en el árbol frente a `cad93d00f1436e60` en `HEAD`).

El único hallazgo **mayor** es de disponibilidad, no de confidencialidad/integridad: **el parseo de
wikitext externo no es lineal** en varios patrones de `services/fandom.py` (retroceso cuadrático y, en
un caso, peor que cuadrático) y se ejecuta en el bucle de eventos. Recomendación firme: **corregirlo en
este mismo PR** (es barato) o, como mínimo, antes de encender las dos fuentes en una instalación real.
Los menores son de coherencia legal/UI y de cobertura de pruebas.

> **Actualización 2026-11-13 (fix del builder + cierre final):** el parseo se ha reescrito, medido y
> re-verificado; el hallazgo M-1 queda **CERRADO** tras RES-1/RES-2 (ver **§6**, veredicto en §6.5).
> Los menores m-1/m-2/m-3/m-5 siguen abiertos y fuera del alcance de este fix.

---

## 1. Método

1. Lectura del código nuevo y de los diffs (`git diff`) de los ficheros de seguridad/red/legal.
2. Verificación ejecutable de defaults, mapeo host→fuente y gate AC-12 (sin red).
3. Medición con Python de los parsers de wikitext con entradas `10⁵`–`10⁶` caracteres, anidamientos y
   cierres ausentes; comparación de tiempos al duplicar el tamaño para estimar el orden de complejidad.
4. Pruebas focalizadas (todas verdes): `tests/test_fandom.py`, `test_cortesia.py`, `test_web_arcos.py`,
   `test_web_ficha_447.py`, `test_web_estado_cortesia.py`, `test_fuentes_apagadas_por_defecto.py`
   → **102 passed in 4.51 s**.
5. La suite completa no se repite aquí: QA ya la ejecutó dos veces (6.567 passed, 2.256 skipped; un
   *flake* de señales en pasada 1, limpio en pasada 2 — `informe-qa-SCR2-fandom-2026-11-13.md` §§1.1-1.2).

---

## 2. Hallazgos

### 2.1 Bloqueantes

**Ninguno.**

### 2.2 Mayores

#### M-1 — Parseo de wikitext no acotado (ReDoS/DoS de disponibilidad) y sin tope de tamaño de respuesta

**Qué.** Cinco expresiones de `limpiar_markup` y la de `seccion` tienen retroceso superlineal con
entradas malformadas (cierres ausentes o repeticiones), y `enlaces_de_issues`/`enlaces_de_pagina`
hacen búsqueda lineal en una lista (`destino not in vistos`). No es exponencial en todos los casos,
pero sí **cuadrático** (y en `_RE_EXTERNO`, peor que cuadrático) sobre datos que vienen de una wiki
**pública y editable**.

**Evidencia de código**

| Pieza | Dónde | Problema |
|---|---|---|
| `_RE_COMENTARIO`, `_RE_REF`, `_RE_ENLACE`, `_RE_EXTERNO`, `_RE_ETIQUETA` | `src/zascarr/services/fandom.py:99-104` | `<!--.*?-->`, `<ref[^>]*>.*?</ref>`, `\[\[(?:[^\]|]+)\|...`, `\[...(?:...)?//[^\s\]]+\s*([^\]]*)\]`, `<[^>]+>`: cuantificadores anidados/ambivalentes sobre texto sin cierre |
| Aplicación | `src/zascarr/services/fandom.py:198-208` (`limpiar_markup`) | Se llama con valores de plantilla y con el primer párrafo de la página entera |
| `seccion` | `src/zascarr/services/fandom.py:245-252` | `={2,}\s*TITULO\s*={2,}(.*?)(?=\n=+\s*[^\n=]|\Z)` → O(n²) con rachas largas de `=` |
| `enlaces_de_issues` / `enlaces_de_pagina` | `src/zascarr/services/fandom.py:255-264` / `:267-276` | `vistos` es una **lista** y se consulta por cada enlace → O(k²) con k enlaces únicos |
| Sin tope de tamaño | `src/zascarr/services/fandom.py:466-499, 501-514` | `respuesta.json()` sobre la respuesta completa; `peticiones.py:162` hace `cliente.get(...)` sin `stream`: no hay límite de bytes (el docstring del módulo documenta páginas de ~3 MB como normales) |

**Rutas alcanzables (externas):** `get_volume` → `limpiar_markup` de `type`/`format`
(`fandom.py:589`) y `primer_parrafo` → `limpiar_markup` (`fandom.py:225-242`); `get_issue` →
`limpiar_markup` de `synopsis1`, `storytitle1` y créditos (`fandom.py:618-621`); `get_arc` →
`seccion(wikitext, "Issues")` sobre la página completa (`fandom.py:629`) y, si no hay sección,
`enlaces_de_issues(wikitext)` sobre la página completa (`fandom.py:634`). Todo se ejecuta **de forma
síncrona dentro del bucle async** del enricher (`enricher.py:762-860, 881-945`); con `--workers 1`,
un parseo lento **bloquea también la UI web**, no solo el ciclo.

**Medición (misma máquina, Python 3.14; carga del sistema 3-5 por sesiones concurrentes; lo relevante
es la escala, no el valor absoluto).** Duplicar el tamaño ≈ ×4 de tiempo salvo en el último caso:

| Entrada hostil | 1.er punto | 2.º punto | Complejidad estimada |
|---|---|---|---|
| `limpiar_markup` con `<ref>` sin cierre | 100.000 chars → **10,75 s** | 200.000 chars → **42,8 s** | cuadrática |
| `limpiar_markup` con `[[` sin cierre | 20.000 chars → **3,58 s** | 40.000 chars → **14,47 s** | cuadrática |
| `limpiar_markup` con `<` sin `>` | 50.000 chars → **1,05 s** | 100.000 chars → **4,07 s** | cuadrática |
| `limpiar_markup` con `<!--` sin cierre | 80.000 chars → **10,65 s** | 160.000 chars → **> 40 s** | cuadrática |
| `limpiar_markup` con `[http://` sin cierre | 1.600 chars → **0,97 s** | 3.200 chars → **7,26 s** | peor que cuadrática (crece ×6–7,5 al duplicar) |
| `seccion(t, "Issues")` con `=` repetidos | 8.000 chars → **0,84 s** | 16.000 chars → **3,55 s** | cuadrática |
| `enlaces_de_issues` con enlaces únicos | 8.000 enlaces → **0,40 s** | 16.000 enlaces → **1,40 s** | cuadrática (lista `vistos`) |

**No afecta al contenido normal:** una página realista de 416 KB (3.000 enlaces a números, 6.000
`<ref>` cerradas, plantilla de volumen) tarda `extraer_plantilla` 44 ms, `seccion` 10 ms,
`enlaces_de_issues` 53-64 ms y `primer_parrafo` 11 ms. Los parsers lineales lo son de verdad:
`extraer_plantilla` 1 MB/60 ms, `_dividir_parametros` 1 MB/110-128 ms, `parametros_de_plantilla`
386 KB/114 ms. El problema es **entrada malformada o vandalizada**, no la operativa normal.

**Por qué es mayor y no bloqueante.** No hay fuga de datos ni ejecución: el impacto es un cuelgue
temporal del proceso (minutos u horas con unas decenas de KB de basura) desencadenable por quien pueda
editar la página de una wiki pública que casa con una serie del usuario. Mitigantes: Fandom está
apagado por defecto y requiere que el usuario encienda la fuente y tenga la serie; no hay persistencia
del daño. Aun así, **es trabajo sin cota sobre entrada no fiable dentro del bucle de eventos**: mi
recomendación es tratarlo como corrección obligatoria de este PR (o inmediata) y, si el equipo prefiere
no bloquear la fusión, **no encender las fuentes en producción hasta corregirlo**.

**Recomendación concreta**
1. Acotar tamaño antes de parsear: p. ej. rechazar revisiones > N MB y truncar/limitar los valores de
   plantilla que pasan a `limpiar_markup` (sinopsis, título de historia, créditos, primer párrafo).
   Alternativa mínima: tope de bytes en la respuesta de `/api.php` (hoy no existe; ver `fandom.py:483`).
2. Reescribir como escaneo lineal o con grupos atómicos/posesivos (Python ≥3.11 los soporta en `re`;
   **sin dependencias nuevas**): `_RE_EXTERNO` y `_RE_ENLACE` son los casos peores; `_RE_REF` y
   `_RE_COMENTARIO` pueden resolverse con búsqueda de cierre en índice, como ya hace
   `extraer_plantilla` (`fandom.py:130-147`).
3. `seccion`: localizar la cabecera con un escaneo de líneas y no con `.*?` + lookahead anidado.
4. `enlaces_de_issues`/`enlaces_de_pagina`: `set` para deduplicar conservando el orden (lista aparte).
5. Prueba de regresión con entradas de 10⁵ caracteres y presupuesto de tiempo (p. ej. < 0,5 s),
   sin red.

### 2.3 Menores

#### m-1 — Coherencia legal/UI: el aviso genérico no menciona Fandom y la atribución de la ficha de serie queda plegada
`LEGAL.md` exige «atribución **visible** en la UI». El doble enlace existe y es correcto, pero:
(a) el aviso genérico de metadatos sigue enumerando solo «Comic Vine, AniList, Tebeosfera»
(`templates/_legal_disclaimer.html:21-27`); (b) en la ficha de serie el aviso de Fandom va **dentro de
un `<details>` cerrado** «Fuentes y atribución» (`templates/series_detail.html:47-51`), mientras que en
la ficha de número (`issue_detail.html:44-45`) y en la saga (`arco.html:10`) sí es visible sin
desplegar. Recomendación: actualizar el aviso genérico (o hacerlo agnóstico de fuentes) y sacar el
aviso de Fandom del desplegable (o declarar en `LEGAL.md` que el desplegable etiquetado cuenta como
atribución). Es cumplimiento, no cosmética.

#### m-2 — El listado `/ui/arcos` muestra títulos de arcos Fandom sin atribución
`templates/arcos.html:13-18` pinta `a.title` (nombre de página de DC Database) sin el doble enlace; la
atribución solo aparece en el detalle (`web/arcos.py:105`). `LEGAL.md:107` habla de las vistas donde se
muestre texto/metadatos. Menor, pero conviene un enlace de licencia en el listado o un aviso común.

#### m-3 — Deduplicación de arcos por título puede atribuir a Fandom un arco ya existente (manual)
`enricher.py:947-963`: si ya existe un `StoryArc` con el mismo `title`, se le añade
`metadata_["fandom_dc"] = <página>` y la UI lo presentará como de Fandom aunque su descripción sea
humana. No rompe nada, pero es una atribución incorrecta posible (y además el título sale del nombre de
página, riesgo R-6 de la spec). Recomendación: deduplicar por `metadata_["fandom_dc"]`/`page_title`
además de por título, o no tocar arcos manuales.

#### m-4 — El `code` de error de MediaWiki entra en el log sin sanear
`fandom.py:112-117` interpola el `code` tal cual en el mensaje de `FandomPayloadError`, y ese mensaje
llega a `logger.exception` (`enricher.py:814, 911, 934`). No hay URL ni credenciales, pero sí texto
arbitrario de un tercero en el log (saltos de línea/ANSI: forja de logs). Recomendación: acotar a un
identificador imprimible y corto (p. ej. `re.sub(r"[^\w:-]", "", str(codigo))[:64]`).

#### m-5 — Cobertura de regresión incompleta en los puntos que esta revisión considera críticos
* Los defaults de Fandom no están en `tests/test_fuentes_apagadas_por_defecto.py:11` (`CAMPOS` sigue
  con cuatro campos); el default es correcto (`config.py:100-103`, verificado aquí), pero no queda
  pinneado por una prueba parametrizada.
* AC-12 solo tiene prueba unitaria del helper (`tests/test_fandom.py:287-295`); no hay prueba de
  integración de «ambas fuentes apagadas ⇒ **cero** red» sobre `descargar_imagen`/`fetch_and_cache_cover`
  (lo he verificado a mano: `FuenteApagada` antes de DNS y de crear el cliente HTTP).
* La ficha de serie con `fandom_dc_slug` no tiene prueba de render (sí la de número
  `test_web_ficha_447.py:99-111` y la de saga `test_web_arcos.py:61-73`); el helper está probado
  (`test_fandom.py:298-314`).
* No hay pruebas de tamaño/tiempo del parseo (M-1).

#### m-6 — `imageinfo` guarda una URL no validada, pero la descarga sí se valida (defensa en profundidad)
`fandom.py:523-536` devuelve la `url` de `imageinfo` y el enricher la escribe en
`series.cover_url`/`issue.cover_url` (`enricher.py:576, 833`) sin pasar por
`es_url_de_portada_permitida`. **No es un SSRF**: el único consumidor que descarga es
`fetch_and_cache_cover` → `descargar_imagen` (`web/series.py:1360-1361`; `cover.py:320-334`), que
aplica allowlist, DNS público, conexión a IP validada, tope de tamaño y gate de fuente en cada salto.
Es el mismo patrón que las demás fuentes (la política H1 se aplica en el punto de descarga, no en el de
guardado) y no debe cambiarse por esta integración; se anota para que la defensa no se pierda en una
refactorización futura.

---

## 3. Verificaciones que pasan (con evidencia)

| # | Requisito | Evidencia | Comprobación |
|---|---|---|---|
| 1 | **SSRF**: solo `/api.php`; host fijo por wiki, query con `urlencode`, redirecciones solo mismo origen | `fandom.py:466-499` (`urlencode` en `:475`, `maxlag` en `:471`, errores en `:484-498`); `peticiones.py:127-151` (`origen == origen_inicial` por defecto) y `:183-221`; `FandomClient` rechaza hosts fuera de `FUENTES` (`fandom.py:428-429`) | Lectura + pruebas del cliente (24 verdes) |
| 2 | **SSRF en portadas**: CDN de Fandom en la allowlist y descarga solo por la cascada validada | `url_portada.py:50-56` (host), `:100-132` (sintaxis: esquema, credenciales, IP escrita, puerto, lista), `:225-267` (DNS público, IP fijada, redirecciones a mano, tamaño, tiempo) | Verificado a mano: `static.wikia.nocookie.net` permitido; `evil.example`, `user:pass@…`, `static.wikia.nocookie.net.evil.example`, `127.0.0.1` y `ftp:` rechazados con código corto |
| 3 | **Ninguna URL externa se descarga fuera de `descargar_imagen`** | `fandom.py` no importa `httpx` para descargar imágenes: `_url_de_imagen` solo devuelve la URL (`:523-536`); el enricher no descarga (`grep httpx/descargar` en `enricher.py` = vacío); único consumidor `web/series.py:1360-1361` → `cover.py:331-334` | Lectura + búsqueda |
| 4 | **Apagado por defecto** | `config.py:100-103` (`False`/`1.5`); Ajustes lo muestra y persiste (`web/ajustes.py:128-129, 277-289`; `templates/ajustes.html:41-47`); `runtime_settings.py:46` | `Settings(_env_file=None)` → `False/False` (ejecutado); QA verificó con `TestClient` que los checkboxes salen sin `checked` y que el POST persiste |
| 5 | **Cero tráfico con la fuente apagada** | `enricher.py:263-278` solo instancia clientes si el toggle está activo; `peticiones.py:249-255` (y en cada salto, `:184-197`) | `test_fandom.py::test_fuente_apagada_no_envia`; lectura |
| 6 | **`LEGAL.md` + hash automático** | Fila nueva en `LEGAL.md:107`; `legal_version` = SHA-256 del fichero empaquetado (`legal.py:35-45`), y la aceptación se busca por esa versión (`legal.py:52-58, 65-72`) | Hash del árbol (`77e66dcf43b13b5a`) ≠ hash de `HEAD` (`cad93d00f1436e60`): cambiar `LEGAL.md` **invalida solo** la aceptación previa, sin paso manual; `test_legal.py:66-74` lo fija |
| 7 | **Doble enlace legal y portadas no CC-BY-SA** | `web/atribucion.py:16-19, 27, 30-49` (artículo por slug + licencia CC BY-SA 3.0, URLs construidas con `quote`, nunca imágenes); `_atribucion_fandom.html:6-16` (dos enlaces, `rel="noopener noreferrer"`, texto «La portada no está incluida en esa licencia»); uso en serie/número/saga (`series_detail.html:50`, `issue_detail.html:45`, `arco.html:10`) | `test_fandom.py:298-314`, `test_web_arcos.py:61-73`, `test_web_ficha_447.py:99-111` |
| 8 | **Sin hotlinking** | Plantillas: la portada se sirve por endpoints locales (`ui.portada`, `series_detail.html:13`; `issue_detail.html:8`); los `src` dinámicos son rutas generadas por el servidor (`/ui/.../portada`, `/ui/.../portada/externa.jpg`, `/ui/.../previa.jpg`; p. ej. `services/portada_serie.py:164,171`) y no hay ningún `src="http…"` en `web/templates/`; los enlaces de atribución son navegación del usuario, no descargas del servidor | Búsqueda |
| 9 | **Logs sin URLs ni payloads** | `fandom.py:563, 603` loguean `wiki` (host fijo) y `page` (nombre de página); errores con código corto (`:112-125`); `enricher.py` loguea título de serie/etiqueta de número/fuente/segundos (`:814, 903-911, 924-934`); `peticiones.py` documenta códigos cortos y no loguea URLs | Lectura + búsqueda de `url=`/`query=` en logs (vacía) |
| 10 | **Cortesía 1,5 s por wiki, compartida por proceso** | `cortesia.py:240-244` (política `fandom_dc`/`fandom_marvel`: 1,5 s, 2 intentos, 3 redirecciones); mapa de fuentes y nombres en `:106-118`; el mismo `CortesiaProceso` del proceso (`fandom.py:461-464`) | `Settings(_env_file=None)` → `1.5/1.5`; `test_cortesia.py` (snapshot con 10 fuentes) |
| 11 | **`maxlag` siempre y bloqueo compartido** | `fandom.py:471` (`maxlag=5` en toda petición); `:487-495` (error `maxlag` → `cortesia.bloquear(fuente, origen, segundos)`); `cortesia.py:528-544` (bloquea fuente y host, con tope de 1 h) | `test_fandom.py::test_maxlag_lanza_y_bloquea_cortesia` (comprueba `retry_after_s == 20`) |
| 12 | **AC-12: apagar AMBAS corta la descarga; con una sola, se permite** | `cortesia.py:143-146` (CDN → origen lógico `fandom`) y `:259-265` (`OR` de las dos wikis); gate antes de la descarga en `cover.py:320-327` y en cada salto de `url_portada.py:249-258`; re-chequeo tras la espera (`:256-258`) | Ejecutado: ambas off → `FuenteApagada("fandom")` **sin DNS ni cliente HTTP**; solo DC on → pasa el gate y llega a resolver DNS (rechazado después por IP privada en la prueba). `test_fandom.py:287-295` |
| 13 | **Sin dependencias nuevas** | `git diff pyproject.toml` vacío; `services/fandom.py` usa `asyncio`, `re`, `time`, `dataclasses`, `datetime`, `urllib.parse` (stdlib), `httpx` y `structlog` ya presentes | `git diff` + lectura de imports |
| 14 | **Parseo lineal en los helpers de plantilla** | `extraer_plantilla` (`fandom.py:130-147`), `_dividir_parametros` (`:150-182`), `parametros_de_plantilla` (`:185-195`) | 1 MB de anidamientos en 60-128 ms (ver §2.2); la página realista de 416 KB, en 44 ms |

**Fuera del alcance de esta revisión (no evaluado aquí):** `/api/health` de fuentes Fandom (AC-17 de
la spec), migración 0036 contra Postgres real, y tráfico en vivo a las wikis. No son de
seguridad/legal o ya los cubre QA.

---

## 4. Recomendaciones, por orden

1. **M-1 en este PR** (o ticket bloqueante de «encendido»): tope de tamaño de respuesta + sanear
   `_RE_EXTERNO`/`_RE_ENLACE`/`_RE_REF`/`_RE_COMENTARIO`/`_RE_ETIQUETA` y `seccion`, y `set` en
   `enlaces_de_*`; añadir prueba de tiempos con entrada hostil de 10⁵ caracteres.
2. m-1 y m-2 (atribución visible y listado de sagas): cambios de plantilla baratos; tocar también
   `_legal_disclaimer.html` para que el aviso genérico deje de enumerar fuentes.
3. m-3 (dedup de arcos) y m-4 (código de error saneado): una línea cada uno.
4. m-5: ampliar `CAMPOS` de `test_fuentes_apagadas_por_defecto.py`, prueba de integración del gate
   AC-12 (sin red) y prueba de render de la ficha de serie.
5. **CLAUDE.md §5.8:** al fusionar, repetir este dictamen sobre el SHA final (el cambio toca
   `web/ajustes.py`).

---

## 5. Trazabilidad

| Punto de la tarea | Sección |
|---|---|
| SSRF/red (url_portada, peticiones, cortesia, `_api`, `_url_de_imagen`) | §3 #1-3, #12, m-6 |
| Apagado por defecto y marco legal (config, ajustes, LEGAL.md, legal.py, atribución) | §0, §3 #4-8, m-1 |
| Logs (fandom, enricher) | §3 #9, m-4 |
| Robustez de parseo (extraer_plantilla, _dividir_parametros, limpiar_markup, seccion, enlaces_de_issues) | §2.2 M-1, §3 #14 |
| Sin hotlinking; 1,5 s por wiki; `maxlag`; dependencias | §3 #8-13 |
| AC-12 gate de portadas | §3 #12 |

---

## 6. Verificación del fix M-1 (2026-11-13)

**Fecha de la re-verificación final:** 2026-11-13, 14:29–14:36 (hora local, Europe/Madrid).
**Tarea:** task-10 (cierre de M-1, tras la re-verificación de task-8 y el fix RES-1/RES-2 del builder).
**Árbol revisado:** el mismo *working tree* sobre `main` (`17a5995e`), sin commitear. En esta ronda
`src/zascarr/services/fandom.py` queda en **922 líneas** (antes 888) y `tests/test_fandom.py` en
**578 líneas / 31 pruebas** (antes 28). Sin SHA: no dictamina fusión (sigue aplicando la condición de
proceso de CLAUDE.md §5.8).
**Alcance:** repetir §6.2–§6.4 sobre el estado actual del fichero y dar el veredicto final de M-1. No se
re-audita el resto de SCR2. No se ha tocado código ni se han hecho commits: solo este informe.

### 6.1 Correcciones acumuladas (verificado por lectura)

| Cambio | Evidencia | Estado |
|---|---|---|
| Topes `MAX_CUERPO_API` = 2 MiB y `MAX_WIKITEXT` = 1.000.000, con `None` sin parsear y aviso estructurado | `fandom.py:66-71`; comprobación de cuerpo en `:721-725` y de wikitext en `:763-767` | **Correcto** (§6.3) |
| `limpiar_markup` con seis escáneres manuales lineales (comentarios, refs, enlaces internos, externos y etiquetas) | `fandom.py:235-388`; las regex `_RE_COMENTARIO`/`_RE_REF`/`_RE_ENLACE`/`_RE_EXTERNO`/`_RE_ETIQUETA` ya no existen | **Correcto** (§6.2) |
| `seccion` por líneas (`_cabecera`/`_empieza_seccion`), sin lookahead sobre todo el texto; dedupe con `set` | `fandom.py:432-501` | **Correcto** (§6.2) |
| Saneado del `code` de MediaWiki en excepción y log (m-4) | `fandom.py:139-145`, usado en `:153` y `:738-743` | **Cerrado** |
| **RES-1:** `_RE_FECHA_EN` sustituida por dos patrones acotados (`[A-Za-z]{1,20}`, `\s{1,5}`, `\d{1,2}`, `\d{4}`) + `MAX_TEXTO_FECHA = 512` | Constantes `fandom.py:76-79`; patrones `:127-134`; `fecha_inglesa` `:504-534`. Búsqueda de `_RE_FECHA_EN` en el módulo: **0 referencias** | **Cerrado** (§6.2) |
| **RES-2:** `MAX_TITULO_PAGINA = 1024` y `titulo_base` no normaliza por encima del tope (devuelve recortado) | Constante `fandom.py:72-75`; cap `:391-401` | **Cerrado** (§6.2) |
| Pruebas nuevas: topes, saneado, presupuesto < 1 s con 200k, RES-1 directo y end-to-end, RES-2 | `tests/test_fandom.py:460-578` | 84 passed (§6.4) |

Detalle funcional de RES-1: el patrón acotado mantiene el reconocimiento de las fechas válidas
(`"August 8, 1961"`, `"Aug. 8, 1961"`, `"1961-08-08"`) y además ahora acepta el día primero
(`"8 August 1961"`, que el docstring prometía desde el principio y el patrón anterior no cubría).

### 6.2 Mediciones antes / después (misma máquina, Python 3.14; carga del sistema 3-5)

Las cifras «antes» son las de M-1 (§2.2) y de la re-verificación anterior (§6 de task-8); las «ahora»
se han vuelto a medir en esta pasada sobre el estado actual. Duplicar el tamaño multiplica el tiempo
por ≈2 (lineal), no por ≈4 (cuadrático).

| Entrada hostil | Antes (M-1) | Ahora (final) |
|---|---|---|
| `limpiar_markup` `<` (antes 100k chars; ahora 200k) | 4,07 s | **4,81 ms** |
| `limpiar_markup` `_` × 200k | (no medido; mismo mecanismo) | **3,80 ms** |
| `limpiar_markup` `=` × 200k | (no medido; mismo mecanismo) | **3,81 ms** |
| `limpiar_markup` `<ref>` × 200k chars | 42,8 s (100k: 10,75 s) | **14,61 ms** |
| `limpiar_markup` `[[` × 200k chars | (40k chars: 14,47 s) | **65,76 ms** |
| `limpiar_markup` `<!--` × 200k chars | 160k chars: >40 s (80k: 10,65 s) | **3,58 ms** |
| `limpiar_markup` `[http://` × 200k chars | 3,2k chars: 7,26 s (peor que cuadrática) | **24,85 ms** |
| `seccion("="×200k)` | 10k: 1,6 s; 50k: >40 s | **1,86 ms** |
| `enlaces_de_issues` con 16.000 enlaces únicos | 1.402 ms | **35,9 ms** |
| `extraer_plantilla` sin cierre × 200k | (ya era lineal: 1 MB/60 ms) | **12,25 ms** |
| **RES-1** `fecha_inglesa("A"×20.000)` | **6.220 ms** | **0,001 ms** (constante: el texto se recorta a 512) |
| **RES-1** `fecha_inglesa("A"×1.000.000)` | extrapolado: **horas** | **0,001 ms** |
| **RES-1 end-to-end** `get_issue` con `ReleaseDate = "A"×20.000` (MockTransport) | **6.320 ms** | **22,9 ms** (el builder declara 12 ms; la diferencia es la carga de la máquina) |
| **RES-1 end-to-end** `get_issue` con `ReleaseDate = "A"×200.000` | — | **113,8 ms** (lineal con el tamaño del wikitext, no con la fecha) |
| **RES-2** `titulo_base("a" + " "×40.000 + "b")` | **11.250 ms** | **0,002 ms** (devuelve recortado a 1.024) |
| **RES-2** `titulo_base("Batman" + " "×20.000 + "Vol 1")` | — | **0,003 ms** |
| Página realista **idéntica** a la del informe (415.676 chars, 3.000 números, 6.000 `<ref>` cerradas) | `seccion` 10 ms; `enlaces` 53-64 ms; `primer_parrafo` 11 ms; `extraer_plantilla` 44 ms | **1,5 ms; 7,0-8,3 ms; 14,0 ms; 66,5 ms** (mismo orden; la variación es carga de máquina, no código) |

Cifras declaradas por el builder: 20k letras → 0,54 ms; 1M letras → 1,1 ms; `get_issue` end-to-end
12 ms. Se reproducen dentro de la variación por carga (mi medición directa es aún menor porque el
texto se recorta a 512 antes de buscar; la end-to-end queda en 22,9 ms). Los 200k de `<`/`_`/`=` a
≈4 ms, `[` a ≈66 ms y `seccion` a ≈1,9 ms también coinciden.

**Otras regex que sobreviven (inventario de `fandom.py:111-145, 406, 485, 556-561, 576, 914, 921`):**
ninguna queda con cuantificador superlineal sobre entrada sin tope:
`_RE_VOL_FINAL`/`_RE_COLLECTED` llevan ahora el cap de 1.024 de `titulo_base`;
`_RE_ANIO_RANGO`, `_RE_FECHA_ISO`, `_RE_FECHA_MES`, `_RE_FECHA_DIA` y `_RE_NEGRITA` son de
cuantificador acotado; `referencia_de_issue` es un `.+?` anclado con coste lineal por destino. Medido
sobre entradas hostiles: `anios_de_displaytitle` con 1M chars → **67,7 ms** (lineal; y el texto está
acotado por `MAX_CUERPO_API`), `referencia_de_issue("x"×1M)` → **35,7 ms** (lineal).

**Diferencial funcional (viejo vs nuevo, ya validado en §6 de task-8):** 4.000 cadenas malformadas
comparadas contra la implementación anterior → 6 diferencias en `limpiar_markup`, 2 en `seccion`, 0 en
`enlaces`, todas en basura con cierres solapados o cabeceras a mitad de línea (el nuevo es más
conservador); ninguna en fixtures reales.

### 6.3 Topes: devuelven `None` sin parsear (re-verificado)

Con los parsers instrumentados para lanzar si se invocan, sobre el estado actual:

* Cuerpo de `/api.php` > `MAX_CUERPO_API` → `get_volume(...)` devuelve **`None`**, sin `json()` ni
  parser (se emite `fandom.respuesta_demasiado_grande` con `bytes`/`limite`, nunca la URL).
* Wikitext > `MAX_WIKITEXT` (cuerpo JSON válido de ~1,0 MB, por debajo del tope de cuerpo) →
  `get_volume` y `get_issue` devuelven **`None`** sin parser
  (`fandom.wikitext_demasiado_grande`, con página/caracteres/límite).
* Control con wikitext normal: `total_issues=7`, `start_year=1940` (mismo resultado que antes).

### 6.4 Tests

`PYTHONPATH=src .tmp-test-venv/bin/python -m pytest -q tests/test_fandom.py tests/test_enricher.py`
→ **84 passed in 2,97 s** (coincide con lo declarado por el builder). `tests/test_fandom.py` tiene
**31 pruebas**, incluidas las nuevas de RES-1 (directa y `get_issue` end-to-end con `ReleaseDate`
hostil) y RES-2 (`tests/test_fandom.py:537-578`), además del presupuesto < 1 s con nueve entradas de
200k (`:513-533`).

### 6.5 Veredicto final: **M-1 CERRADO**

Se cierra el hallazgo mayor de §2.2 con evidencia reproducible:

1. Las cinco expresiones que tenían retroceso y las funciones `seccion`/`enlaces_de_issues` son
   ahora **lineales**: 200k chars de markup hostil cuestan 3-66 ms (antes segundos u horas).
2. El último residuo de la re-verificación de task-8 (**RES-1**) pasa de **6,22 s a 0,001 ms** en
   directo y de **6,32 s a 22,9 ms** end-to-end; 1M de letras ya no escala (el texto se acota a 512).
3. **RES-2** queda acotado: `titulo_base` con rachas de 40.000 espacios pasa de **11,25 s a 0,002 ms**,
   y el cap devuelve como mucho 1.024 caracteres.
4. No queda ningún patrón con cuantificador superlineal sobre entrada sin tope: los que siguen son de
   cuantificador acotado o están protegidos por `MAX_TITULO_PAGINA`, y se han medido lineales hasta 1M
   de caracteres.
5. Los topes `MAX_CUERPO_API`/`MAX_WIKITEXT` devuelven `None` **sin parsear** (verificado con parsers
   instrumentados) y el comportamiento funcional no cambia (84 tests verdes; página realista sin
   regresión; fechas válidas se siguen reconociendo).

### 6.6 Residuos que quedan (ninguno bloquea M-1)

* **m-6 (menor, sin cambios):** la URL de `imageinfo` se guarda sin validar, pero la única descarga
  pasa por `descargar_imagen` (`cover.py:331-334`), que aplica allowlist, IP pública, tamaño,
  redirecciones y gate de fuente en cada salto. Sigue como menor.
* **RES-3 (menor, deuda):** `MAX_CUERPO_API` se comprueba sobre `respuesta.content`
  (`fandom.py:721`), que httpx ya bufferizó: acota el parseo, no la transferencia ni la memoria. Un
  tope real exige `cliente.stream(...)` en `utils/peticiones.py` (cambio compartido, fuera de este
  fix). No es un retroceso ni afecta al cierre de M-1.
* **Observación funcional (RES-1):** `fecha_inglesa` examina como mucho 512 caracteres; una fecha
  válida precedida de >512 caracteres de basura ya no se detecta. No es realista (un `ReleaseDate`
  real ocupa <30 caracteres) y está declarado en el docstring.
* **Observación funcional (topes):** un wikitext > 1.000.000 caracteres se trata como «sin ficha» y
  el enricher lo marcará como intentado (negativa de 30 días). Las páginas reales medidas son
  ≤ 416 KB, así que no es una regresión práctica.
* **Nota RES-2:** un título > 1.024 caracteres se devuelve recortado y sin normalizar; MediaWiki limita
  los títulos a ~255 bytes, así que no afecta a títulos reales.
* **Fuera del alcance de este fix y siguen abiertos:** m-1, m-2, m-3 y m-5 (coherencia legal/UI,
  atribución del listado de sagas, dedup de arcos y cobertura de pruebas) y `/api/health` de fuentes
  Fandom (AC-17 de la spec; no es seguridad).

### 6.7 Recomendación final

M-1 **cerrado**: no hace falta otra pasada de este hallazgo. Al fusionar, repetir el dictamen de
SecOps sobre el **SHA final** por CLAUDE.md §5.8 (el cambio toca `src/zascarr/web/ajustes.py`).
Quedan como tickets menores independientes: m-1, m-2, m-3, m-5 y la deuda RES-3 (tope de bytes en
`utils/peticiones.py`). Evidencia reproducible: mediciones de §6.2 con el venv de pruebas y
`httpx.MockTransport` (sin red), topes de §6.3 con los parsers instrumentados y la suite de §6.4.

---

## 7. Dictamen final de fusión (SHA 48c2920b)

**Fecha:** 2026-11-13, 15:08–15:22 (Europe/Madrid). **Tarea:** task-11. **PR:** #734 (`feat/fandom-fuentes` → `main`).
**Árbol:** *checkout* en el SHA exacto. Este dictamen se añade al informe con posterioridad al SHA: es solo
documentación (no se ha tocado código ni se han hecho commits; este informe es el único fichero modificado
en el árbol de trabajo).

### 7.1 SHA verificado

* `git rev-parse HEAD` → **`48c2920b7a2306fc52faac550f73c317db298f0d`**.
* `gh pr view 734 --json number,state,mergeable,headRefOid,baseRefName` →
  `{"baseRefName":"main","headRefOid":"48c2920b7a2306fc52faac550f73c317db298f0d","mergeable":"MERGEABLE","number":734,"state":"OPEN"}`.
* Base del rebase: `2c69a9bd2fa02e73e70400cd3e9cd0a9a7f67445`.
* Delta: `git diff 2c69a9bd..48c2920b --stat` → **29 ficheros, +3334/−73**; 4 commits
  (`b95ffadc`, `39223ccc`, `2f8071c3`, `48c2920b`).
* **Este dictamen aplica solo a ese SHA.** Cualquier commit añadido o rebase posterior exige repetirlo
  (CLAUDE.md §5.8).

### 7.2 Superficie §5.8: `web/ajustes.py` y `templates/ajustes.html`

**Hallazgo del delta:** la PR, tal como está rebasada, **no modifica** `src/zascarr/web/ajustes.py`,
`src/zascarr/web/templates/ajustes.html`, `src/zascarr/config.py` ni
`src/zascarr/services/runtime_settings.py`: `git diff --quiet 2c69a9bd..48c2920b -- <fichero>` es cierto
para los cuatro (idénticos a la base). El motivo es que la base `2c69a9bd` **ya contiene** los dos toggles
Fandom y los campos de configuración: el blame de `web/ajustes.py:128-129` apunta al commit `28d45a52e`
(«feat(d3): perfil de calidad…», 2026-11-13 13:01), que arrastró esa parte de SCR2 a `main`. Es una
**observación de proceso sobre `main`, no un cambio de esta PR** (los toggles quedan inertes sin el cliente
Fandom; conviene que Lead/PO conozca su origen). Por eso el disparador de §5.8 no se materializa en el delta
neto; aun así se revisa el estado del fichero en el SHA por ser la superficie que la regla protege:

* Toggles: `web/ajustes.py:302-303` son dos `Form(default=False)` explícitos dentro de `guardar_fuentes`; se
  persisten con `RuntimeSettingsService.save({...})` (`:313-314`) y sus campos están en
  `OVERRIDABLE_FIELDS["fuentes"]` (`services/runtime_settings.py:44-47`). Sin mass assignment desde el body.
* Flujo de contraseña/sesión: **sin cambios**. Las líneas de `COOKIE_NAME`/`SESSION_MAX_AGE`/
  `crear_cookie_sesion` del fichero son preexistentes (idénticas a `main`) y la PR no las toca;
  `services/seguridad.py` y `services/reautenticacion.py` no aparecen en el delta.
* Secretos: **ninguno nuevo** (Fandom no requiere credenciales; los indicadores
  `*_password_configurada`/`auth_password_configurada` existentes no cambian).

### 7.3 Resto de la superficie de seguridad (delta completo)

| Área | Evidencia en el SHA | Resultado |
|---|---|---|
| Red/SSRF | `url_portada.py:50-55` (CDN en la allowlist); `services/fandom.py` solo `/api.php`, host fijo, `urlencode`, `follow_redirects=False`, `maxlag=5`; descargas de `imageinfo` únicamente por `descargar_imagen` | Sin cambio de política (§3 #1-3); el CDN entra en la allowlist existente |
| Cortesía / `maxlag` | `cortesia.py:240-244` (1,5 s × 2 intentos por wiki), `:259-263` (origen lógico `fandom` apagado solo si ambas wikis lo están); `maxlag` comparte bloqueo con tope de 1 h | Correcto (§3 #10-12) |
| Legal / atribución | `LEGAL.md:107` fila CC-BY-SA; `legal_version` = hash del fichero (base `cad93d00f1436e60` → SHA `77e66dcf43b13b5a`: la aceptación anterior se invalida sola); doble enlace artículo + CC-BY-SA 3.0 en `web/atribucion.py:16-48` y plantillas; portadas no etiquetadas y sin hotlinking | Correcto (§3 #6-8) |
| Apagado por defecto | `config.py:100-103` (`False`/`1.5`, ya en la base); Ajustes y `runtime_settings` | Correcto (§3 #4-5) |
| Dependencias | `git diff 2c69a9bd..48c2920b -- pyproject.toml` vacío; `services/fandom.py` usa stdlib + `httpx` + `structlog` ya presentes | Sin dependencias nuevas |
| Migración 0036 | Solo `add_column` + `create_unique_constraint`; `downgrade` revierte columnas y constraints; sin tocar datos ni tipos | Aditiva y reversible |
| Logs y datos | Código nuevo loguea códigos/nombres de página, nunca URLs ni payloads (§3 #9); `comic_vine.py` (nuevo `store_date`) y `enricher.py` (`_fecha_iso` con `date.fromisoformat`) son cambios de datos, sin red nueva ni entradas de usuario | Correcto |
| Grep de superficie sensible en el delta | `os.environ`/contraseñas/secretos: sin coincidencias relevantes (solo `FakeSession` de tests) | Correcto |

### 7.4 M-1 re-verificado en este SHA (sigue cerrado)

Medido sobre el árbol del SHA (Python 3.14, venv de pruebas):

* `fecha_inglesa("A"×20.000)` → **0,37 ms**; `×1.000.000` → **0,36 ms** (antes: 6.220 ms / horas).
* `limpiar_markup("<"×200.000)` → **3,2 ms**; `"["×200.000` → **48,0 ms**; `seccion("="×200.000)` →
  **1,3 ms**; `titulo_base("a" + " "×40.000 + "b")` → **0,002 ms**.
* `_RE_FECHA_EN` ya no existe en el SHA; `MAX_CUERPO_API`/`MAX_WIKITEXT`/`MAX_TEXTO_FECHA`/
  `MAX_TITULO_PAGINA` presentes (`fandom.py:68,71,75,79`); las fechas válidas se siguen reconociendo.
* `pytest tests/test_fandom.py tests/test_enricher.py` → **86 passed**. Detalle y comparativa completa en §6.

### 7.5 Regresión focal

```
PYTHONPATH=src .tmp-test-venv/bin/python -m pytest -q tests/test_web*.py \
    tests/test_seguridad.py tests/test_legal.py tests/test_runtime_settings.py
→ 1287 passed, 107 skipped in 23.39 s
```
(Los 107 *skips* son los esperados sin `TEST_DATABASE_URL` y dependencias de entorno, como en §1 del
informe de QA.)

```
ruff check src/                → All checks passed!
ruff check --select S src/     → All checks passed!
```
Gate de CI de ruff (`ci.yml:115,118`) **verde**. `tests/test_enricher.py` tiene 16 hallazgos de ruff
(E501/I001/UP017) **idénticos en la base y en el SHA**: son deuda pre-existente, `tests/` no está en el gate
de CI y la PR no los introduce.

### 7.6 Veredicto: **FAVORABLE**

**Favorable a fusionar el SHA `48c2920b7a2306fc52faac550f73c317db298f0d` en `main` (`2c69a9bd`).**

* **0 bloqueantes:** sin SSRF nuevo, sin cambios en contraseña/sesión, sin secretos ni dependencias nuevas,
  migración aditiva/reversible, fuentes apagadas por defecto, `legal_version` por hash y atribución
  CC-BY-SA 3.0 completa.
* **M-1 cerrado** y re-verificado en este SHA (§7.4).
* **Regresión de seguridad/web verde** y gates de ruff de CI verdes (§7.5).
* **Observaciones no bloqueantes (no condicionan la fusión):** (a) `main` ya contenía los toggles Fandom
  desde `28d45a52e` —observación de proceso, ver §7.2—; (b) deuda de lint pre-existente en
  `tests/test_enricher.py`; (c) siguen abiertos los menores m-1, m-2, m-3 y m-5 y la deuda RES-3 (§6.6),
  ya documentados como tickets independientes.
* **Condición de vigencia:** cualquier commit o rebase posterior invalida este dictamen y exige repetirlo
  sobre el nuevo SHA (§5.8).

**Comentario en el PR #734:** publicado el 2026-11-13 con este veredicto y el SHA citado —
<https://github.com/juanajok/zascarr/pull/734#issuecomment-6855377310>.

---

## 8. Addendum de vigencia (SHA 1f6a7790)

**Fecha:** 2026-11-13. **Tarea:** task-12. **PR:** #734 (`feat/fandom-fuentes` → `main`).

El commit **`1f6a7790971a17ced28e11348e2f6e8964130b68`** («docs(SCR2): dictamen final de fusión de SecOps
sobre el SHA 48c2920b», 2026-11-13 15:11) es hijo de `48c2920b` y **solo añade documentación**: incorpora la
§7 anterior al informe. Verificación de que no cambia nada ejecutable:

```
$ git diff --stat 48c2920b..1f6a7790
 docs/design/secops-SCR2-fandom-2026-11-13.md | 102 +++++++++++++++++++++++++++
 1 file changed, 102 insertions(+)

$ git diff --name-status 48c2920b..1f6a7790
M	docs/design/secops-SCR2-fandom-2026-11-13.md
```

* `git diff --stat 48c2920b..1f6a7790 -- . ':(exclude)docs/design/secops-SCR2-fandom-2026-11-13.md'` →
  **vacío**: ningún fichero de `src/` (código, configuración, plantillas) ni de `alembic/` cambia.
* `git log --oneline 48c2920b..1f6a7790` → un único commit (`1f6a7790`).
* `gh pr view 734` → `headRefOid = 1f6a7790971a17ced28e11348e2f6e8964130b68`, base `2c69a9bd…`,
  `MERGEABLE`.

**Veredicto:** el dictamen **FAVORABLE** de §7 **se extiende al SHA
`1f6a7790971a17ced28e11348e2f6e8964130b68`**: la superficie ejecutable revisada (código, configuración,
plantillas, migración y legal) es exactamente la de `48c2920b`, y las mediciones de M-1 y la regresión de
§7.4-§7.5 siguen aplicando sin cambios. Se mantiene la condición de vigencia: cualquier commit o rebase
posterior exige un nuevo dictamen (CLAUDE.md §5.8).

**Comentario en el PR #734 con el SHA nuevo:** publicado el 2026-11-13 —
<https://github.com/juanajok/zascarr/pull/734#issuecomment-6855412854>.


---

## Nota de mantenimiento post-fusión (2026-11-13)

Tras la fusión, la resolución de `main` renumeró la migración de Fandom de `0034` a **`0036`**
(había colisión con la migración de BL-D3; cadena `0034 mejoras` → `0035 portada` → `0036 fandom`).
El cambio es **solo de identificador y `down_revision`**, no de SQL: el dictamen de seguridad no
se ve afectado en su sustancia, pero por CLAUDE.md §5.8 cualquier cambio posterior al SHA dictaminado
exige pasada sobre el SHA final. Verificado además con Postgres real en la sesión de despliegue
(`upgrade` desde 0033, columnas+UNIQUE, `downgrade`/`upgrade`) y añadida la regresión
`tests/test_migracion_fandom_pg.py`.
