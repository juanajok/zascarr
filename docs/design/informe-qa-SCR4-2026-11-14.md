# Informe QA — SCR4: charset, flood, Ajustes/LEGAL y diagnóstico del foro (2026-11-14)

**Rol:** QA · **Tarea:** task-28 · **Repositorio:** `/mnt/Datos/Documentos/Repos/zascarr`
**Worktree revisado:** `/mnt/Datos/Documentos/Repos/zascarr/.worktrees/scr4-foro`
**Rama:** `feat/scr4-foro`, SHA **`ca68881f82d9a80b4bcdce1c8c67a6964b1715d8`** (verificado con
`git rev-parse HEAD`; PR #783 según el encargo, no consultada por red).
Árbol limpio antes de la verificación; no se ha modificado código ni tests.
**Entorno:** `PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q`
(Python 3.14, pytest 9.2, ruff 0.17.5). Sin `TEST_DATABASE_URL` (SCR4 no usa Postgres en pruebas).
El único fichero escrito es este informe; el scratch de QA (`.qa-scr4/`) se borra al terminar.

> **Nota de proceso:** la primera sesión de QA se interrumpió a mitad de la suite completa.
> Al reanudar se ejecutaron primero las suites de foro aisladas, después la reproducción
> independiente y **una sola** pasada completa (el Lead autorizó expresamente una en lugar de
> dos por tiempo); queda anotado como limitación frente al criterio habitual de dos pasadas.

---

## 1. Regresión

| Comando (desde el worktree) | Resultado | Tiempo |
|---|---|---|
| `pytest -q tests/test_forum_charset.py tests/test_forum_flood.py tests/test_forum_intervalos.py tests/test_forum_ajustes_http.py tests/test_diagnostico_foro.py tests/test_forum_scraper.py` | **130 passed** | 2,92 s |
| `pytest -q` (suite completa, **una** pasada — ver nota) | **6866 passed, 2280 skipped**, 4 warnings, 0 fallos | 357,89 s (wall 6:01) |
| `ruff check src/` | **All checks passed!** | — |

Conteo aislado por fichero: `charset` 10, `flood` 7, `intervalos` 4, `ajustes_http` 4,
`diagnostico_foro` 6, `forum_scraper` existente completo; total 130. Los 2280 skips de la suite
completa son los esperados sin `TEST_DATABASE_URL` (pruebas `*_pg`), no de SCR4. Los 4 warnings
(`ComicInfo.xml` duplicado; `AsyncMock` sin await en importer) son preexistentes y ajenos.

---

## 2. Reproducción independiente con fixtures propios — **17/17 OK**

Además de las pruebas del builder, construí bytes y HTML propios (sin sus fixtures) y ejecuté
el scraper real: **17/17 comprobaciones OK**.

* **Charset.** Respuesta `text/html` sin `charset`, con `<meta charset=iso-8859-1>` y bytes
  latin-1 → `analizar_charset` da `cabecera=None`, `meta=iso8859-1` y «Capitán América» se
  decodifica sin `�`; con `charset=UTF-8` en cabecera manda la cabecera; sin cabecera ni meta
  cae en **cp1252** y el byte `0x80` se lee como `€`.
* **Login.** GET de entrada + POST a la `action` real con `s=SESION123`; cuerpo crudo en
  latin-1 (`UserName=Capit%E1n`, `PassWord=A%F1o`, `s=SESION123`), `Content-Type …
  charset=iso8859-1` y **sin** `Capit%C3%A1n` (UTF-8). Una `action` de otro origen se rechaza
  con `OrigenNoPermitidoError`. El `User-Agent` es el del proyecto (`ZascArr/1.0.0`).
* **Búsqueda.** La query viaja como `keywords=Capit%E1n` (latin-1) y el título del resultado
  latin-1 se lee sin caracteres rotos.
* **Flood.** HTML propio con caja de error IPB + frase inglesa/española → 42 s; sin caja o sin
  frase → `None`; `use_ipb_search` lanza `ForumFloodControl` con **una** petición y la segunda
  llamada espera sin red (`CortesiaEnEspera`); «0 resultados» real (sin caja de error) → `[]`
  sin excepción.
* **Intervalos.** Políticas de lectura 2 s y búsqueda 25 s (`max_intentos=1`, espera 30); dos
  búsquedas seguidas con reloj simulado duermen **25 s**.
* **Logs.** Un fallo de tema con `s=SESION123` en la URL registra solo `host=foro.example`;
  el volcado de logs no contiene `s=` ni la URL.
* **Contraseña en blanco.** `RuntimeSettingsService.save` real (sesión falsa, fila con
  `forum_password="CLAVE_VIEJA"`): un guardado con contraseña vacía **no pisa** el secreto y sí
  guarda URL/usuario/activado.
* **LEGAL y diagnóstico.** `LEGAL.md` contiene el aviso de HTTP sin cifrar + «aviso legal» y el
  hash versionado actual (`0c1b51a68cf08731`) difiere del de `HEAD~1`; el script
  `--help` funciona y sin configurar sale con código 2, mensaje en español y 0 peticiones.

---

## 3. Aceptación por AC (24 etiquetas de la spec; el encargo decía «22 AC»)

La spec `docs/design/especificacion-SCR4-foro.md` enumera **24** AC: AC-CHA-1…6, AC-FLD-1…6,
AC-TLS-1…4, AC-INT-1…4 y AC-DIA-1…4. Se verifican todos:

**AC-CHA-1…6 — charset (cabecera/meta/fallback cp1252, POST latin-1/cp1252, login con `s=`)**
PASA. `analizar_charset`/`detectar_charset`/`decodificar_respuesta` (`forum_scraper.py:156-206`)
priorizan cabecera → meta (4 KiB) → cp1252 con `forum.charset_no_declarado`; nunca `r.text`.
`pedir_con_cortesia(..., form_charset=…)` (`peticiones.py:154-195`) manda el formulario
`urlencode(encoding=…)` como `content` con su `Content-Type`; un carácter que no cabe reintenta
en cp1252. Login GET+POST con `action` del formulario y `s=` conservado (`:330-370`); la
búsqueda usa `quote(query, encoding=charset)` (`:441-455`). Pruebas: `test_forum_charset.py`
(10, incluida la captura del cuerpo crudo `Capit%E1n`) y sonda §2.

**AC-FLD-1…6 — Search Flood Control en HTTP 200**
PASA. `detectar_flood` exige caja de error IPB **y** frase (inglés/español), recorta a
[20,60] s y usa 30 si no hay número (`forum_scraper.py:209-219`); `_comprobar_flood` bloquea la
fuente y lanza `ForumFloodControl(CortesiaEnEspera)` (`:297-304`), sin reintento en la petición
(HTTP 200). `use_ipb_search` la propaga (nunca `[]`) y un vacío real devuelve `[]`. El
orquestador captura la excepción en `_search_and_rank`, deja `status=WANTED` y
`last_error=MOTIVO_FORO_ESPERA`, **no** `MOTIVO_SIN_RESULTADOS` (`orchestrator.py:342-356`);
`_forum_fallback` la deja propagar (`:638-644`). Pruebas: `test_forum_flood.py` (7) + sonda §2.
Nota: el `mark` de intento (`_marcar_busqueda`) sigue ocurriendo antes de las fuentes porque la
spec lo fija así (D-3: un flood gasta el cooldown de 6 h); «sin marcar intento» del encargo se
interpreta como «sin marcarlo como intento sin resultados», no como no tocar `last_searched_at`.

**AC-TLS-1…4 — HTTP plano sin TLS: aviso en Ajustes y LEGAL**
PASA. `_contexto` expone `forum_http_sin_tls` (`web/ajustes.py:143-150`); la tarjeta muestra
`ui.aviso("amber", «El foro usa HTTP sin cifrar…»)` solo con `http://` (`ajustes.html:238-262`);
la contraseña nunca se pasa (solo `forum_password_configurada`, `:147-149`). `guardar_foro`
(`:428-448`) guarda URL/usuario/contraseña/activar; un secreto vacío no se pisa (servicio,
`runtime_settings.py:139-148`). `LEGAL.md:65` añade la advertencia y el enlace a «Aviso legal»;
el hash de `legal_version` cambia (sonda §2). Grupo `foro` en `OVERRIDABLE_FIELDS:56-57` y
`forum_password` en `SECRET_FIELDS:73-76`. Pruebas: `test_forum_ajustes_http.py` (4); H5 sigue
verde (130 pruebas de foro incluyen `test_forum_scraper.py`).

**AC-INT-1…4 — intervalos separados**
PASA. `config.py:148-160` mantiene `forum_rate_limit=2.0` y añade
`forum_search_rate_limit=25.0`; `politica_de("foro")` sigue en 2 s (`cortesia.py:248-255`); el
constructor toma ambas de settings (`forum_scraper.py:236-261`), búsqueda con `max_intentos=1` y
`espera_max_s=max(30, 25+5)`. Pruebas: `test_forum_intervalos.py` (4) + sonda §2.

**AC-DIA-1…4 — script de diagnóstico**
PASA. `scripts/diagnostico_foro.py` lee `get_settings()`, usa los helpers reales, máximo 3
peticiones (4 con `--leer-tema`) y pausa de 3 s; nunca imprime contraseña, usuario completo,
cookies, `s=`, títulos ni enlaces; códigos 0/2/3/4/5 con explicación en español. Pruebas:
`test_diagnostico_foro.py` (6, con canario de contraseña/cookie/sesión) + sonda §2 (`--help`,
exit 2 sin configurar, 0 peticiones).

---

## 4. Observaciones y riesgos (ninguno bloqueante para SCR4)

**O1 — `TOPIC_PATTERN` no casa con el formato habitual de IPB `showtopic=N&s=…`.** El regex
`<a href="([^"]*showtopic=\d+)">` exige que `showtopic=N` cierre el `href`; un enlace
`index.php?showtopic=9&s=SESION` (IPB suele añadir la sesión a la query) **no** casa y la
búsqueda devolvería `[]` en silencio. Es un patrón preexistente (no lo introduce SCR4) y los
fixtures/tests usan `showtopic=N` limpio; no afecta a los AC de esta entrega, pero es un riesgo
para la validación en vivo (§6 de la spec, pendiente con credenciales). Recomendación: probar
la primera búsqueda real y, si los enlaces llevan `&s=`, ampliar el regex a
`showtopic=\d+[^"']*` conservando el filtro de origen.

**O2 — AC-TLS-2 dice «usuario, contraseña ni cookie»; la tarjeta muestra el usuario por diseño.**
La plantilla pinta `value="{{ forum_username }}"` (D-1 pide tarjeta completa), y las pruebas solo
prohíben contraseña/cookies. La contraseña y las cookies no aparecen (verificado con canario);
el «usuario» de AC-TLS-2 se interpreta como credencial/secreto, coherente con §3 («La contraseña
nunca se pasa a la plantilla»). Conviene aclarar la redacción del AC.

**O3 — Validación con credenciales pendiente.** El POST real con tildes, el login contra el foro
y la lectura de un tema no se pueden validar aquí sin credenciales; la spec y el script de §5 lo
dejan al usuario/Lead. La sonda cubre el contrato con bytes reales y transporte simulado.

**O4 — Una sola pasada completa** (interrupción de proceso + autorización del Lead para una).
Las suites de foro aisladas y la sonda independiente cubren el cambio; si el Lead quiere la
segunda pasada, puede lanzarla sin más.

**O5 — El encargo habla de 22 AC; la spec enumera 24** (6+6+4+4+4). Se han verificado las 24.

---

## 5. Veredicto

**APTO.** La pasada completa (única, ver O4) salió **verde: 6866 passed / 2280 skipped, 0
fallos**. Los AC de SCR4 están cubiertos y verificados con pruebas + sonda independiente
(17/17), `ruff check src/` limpio y las 130 pruebas de foro aisladas verdes. Sin bloqueantes para SCR4;
quedan O1 (patrón de temas con `&s=`) y O3 (validación en vivo con credenciales) como riesgos a
vigilar en el dictamen/validación siguientes.

---

## 6. Comandos reproducibles

```
cd .worktrees/scr4-foro
PYTHONPATH=src /mnt/Datos/Documentos/Repos/zascarr/.tmp-test-venv/bin/python -m pytest -q \
    [[tests/test_forum_charset.py …]]           # 130 passed
PYTHONPATH=src … -m pytest -q                   # suite completa (una pasada)
PYTHONPATH=src … -m ruff check src/             # All checks passed!
PYTHONPATH=src … <venv>/bin/python .qa-scr4/probe.py   # 17/17 OK
```

---

## 7. Inventario del cambio revisado (`ca68881f`)

22 ficheros, **+1314 / −83**: `scripts/diagnostico_foro.py`, `src/zascarr/LEGAL.md`,
`config.py`, `services/forum_scraper.py`, `services/orchestrator.py`,
`services/runtime_settings.py`, `utils/peticiones.py`, `web/ajustes.py`,
`web/templates/ajustes.html`, 5 fixtures de `tests/fixtures/foro/` y 5 ficheros de pruebas
(`test_forum_charset/flood/intervalos/ajustes_http/diagnostico_foro`) más el ajuste de
`test_forum_scraper.py`. **Sin** cambios en `models/` ni `alembic/`.
