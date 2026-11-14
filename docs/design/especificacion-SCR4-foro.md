# SPEC: foro IPB de La Mansión CRG (SCR4, #705) — v0.1

> **Estado:** spec implementable (P1, S); sin código ni commits. La validación **con credenciales** la hará el Lead/usuario con el script de §5.
> **Base:** `main` `03beeed3` (SCR1–SCR3 fusionadas), 2026-11-14; manda el código real.
> **Comprobación anónima en vivo** (2 GET, UA `ZascArr/1.15.1 (+…; SCR4)`, 3 s, sin credenciales) de `http://lamansion-crg.net/forum/index.php`: `200`,
> `Content-Type: text/html` **SIN `charset`** y `<meta charset="iso-8859-1">`; login `POST` a acción con `s=<sesión>`; temas absolutos al mismo origen.
> **Hoy httpx decodificaría como UTF-8: tildes rotas** (validación 1 confirmada). Fuentes: estudio §3/§5.7, `hallazgo-h5-foro.md` (origen/cookies ya corregidos,
> no tocar), fila SCR4 y specs SCR1/SCR3. **Deuda:** sin URLs de hilos la lectura de temas se prueba con simulacro y se validará en vivo.

## 0. Estado real (qué cumple y qué falta)

| Pieza | Estado hoy (fichero:línea) | Falta |
|---|---|---|
| Origen y cookies (H5) | **Cumple**: allowlist de origen exacto, enlaces/redirecciones de otro host cortados, cookie solo al origen (`forum_scraper.py:127-132,134-164,166-189`; `peticiones.py:170-221`) | Nada; no romper |
| Login | `POST` a acción **fija** `act=Login&CODE=01` sin GET previo (`forum_scraper.py:109-125`); éxito = «hay cookies» (no distingue sesión de miembro) | GET previo, acción del formulario, charset, flood, éxito real |
| **Charset** | `POST` `data=dict` → httpx codifica **UTF-8** (`peticiones.py:154-167`); búsqueda `quote(query)` UTF-8 (`forum_scraper.py:194`); respuesta por `r.text`, que asume UTF-8 sin `charset` (`:189`) | Validación 1 (§1) |
| **Flood** | Sin detector; una página de flood (HTTP 200) se procesa como «sin resultados» (`:191-206`) | Validación 2 (§2) |
| **Aviso HTTP** | `LEGAL.md:65` no lo menciona; **no hay tarjeta Foro en Ajustes** (`web/ajustes.py:118-176`, `templates/ajustes.html` sin foro) pese a que `config.py:51-55` dice que se configura ahí | Validación 3 (§3); D-1 |
| Intervalos | Uno solo `forum_rate_limit=2,0 s` (`config.py:145`; `cortesia.py:245-246`) para login, búsqueda y lectura | Separar (§4) |
| Config/UI/higiene | Solo `.env` (`docker-compose.yml:131-134`; `.env.example:36-39`); sin grupo `foro` en `runtime_settings.py:38-47`; UA `"ZascArr/0.1"` (`:129`); `forum.topic_failed` registra la URL con `s=` (`:227`) | D-1; UA del proyecto y log sin query (§8) |
| Orquestador | Tras el foro, un vacío escribe `MOTIVO_SIN_RESULTADOS` (`orchestrator.py:396`); el mark de intento va antes (`:307`) | Flood como espera, no como vacío (§2) |

No hay caché negativa de 30 días en el foro (eso es del enricher); sí el cooldown de 6 h por intento (D1/H2, `orchestrator.py:303-306`).

## 1. Validación 1 — charset (ISO-8859-1/cp1252)

Helpers en `services/forum_scraper.py`, reutilizados por §5:
1. `detectar_charset(respuesta)`: (a) `charset` de `Content-Type` si `codecs.lookup` lo acepta; (b) si no, `<meta charset>`/`<meta http-equiv=content-type>`
   en los primeros 4096 B; (c) si no hay ninguno, **`cp1252`** (nunca UTF-8) con aviso `forum.charset_no_declarado`; alias normalizados.
2. **POST en el charset detectado**: extender `pedir_con_cortesia(..., form_charset=…)` y `_enviar` (`peticiones.py:154-167,199-201`) para mandar
   `urlencode(datos, encoding=charset)` como `content` con `Content-Type: …; charset=<charset>`; carácter que no cabe → cp1252 o rechazo con mensaje.
3. **Búsqueda GET**: `quote(query, encoding=charset)` (`forum_scraper.py:194`) → `%E1`/`%F1` latin-1, no `%C3%A1`. **Decodificar antes de parsear**:
   `respuesta.content.decode(charset, errors="replace")` + `lxml.html.HTMLParser(recover=True, no_network=True)` (en bytes, `encoding=charset` obligatorio);
   **prohibido `r.text`** (`:189`); el charset del GET de entrada se guarda para login/búsqueda.
4. Login: **GET de `{FORUM_URL}/index.php` primero** (charset, sesión y `action` del formulario), `action` validada con `_resolver_enlace` (mismo origen) y
   `POST` con `UserName`/`PassWord`/`CookieDate=1` + `s=`. Éxito = cookie de miembro nueva (`member_id`/`pass_hash`/equivalente), no la de la visita;
   ambiguo → `False` con `login_no_confirmado` (sin usuario ni contraseña en el log).
**AC-CHA-1** cabecera con `charset` → se usa. **AC-CHA-2** cabecera sin `charset` + meta latin-1 (caso real) → se usa la meta y el POST va en latin-1.
**AC-CHA-3** sin cabecera ni meta → cp1252 + aviso. **AC-CHA-4** bytes `Capit\xe1n`/`A\xf1o` → «Capitán»/«Año» sin `�`. **AC-CHA-5** cp1252 con `\x80`
decodifica. **AC-CHA-6** el login usa el `action` del formulario y rechaza uno de otro origen.

## 2. Validación 2 — Search Flood Control en HTTP 200

`detectar_flood(html: str) -> float | None` (None = no; segundos = espera), tras decodificar y **antes** de interpretar resultados, en login y búsqueda.
Patrones (sin distinguir mayúsculas; el board está en español): `flood control`, `control de (flood|saturación)`, `cannot make another search`,
`you (can|may) only search`, `no puedes (hacer|realizar) otra búsqueda`, `solo puedes (hacer|realizar) una búsqueda`, `try again in (\d+) seconds`,
`espera (\d+) segundos`, `int[ée]ntalo de nuevo en (\d+) segundos`, **junto a** la caja de error de IPB (`#errorwrap`, `div[class*=errorwrap]`,
`div[class*=errorbox]`) para no confundir prosa que menciona «búsqueda». Sin nº de segundos: 30; recorte a **[20, 60] s**; si hay resultados y flood
a la vez, gana el flood. Al detectarlo: `cortesia.bloquear("foro", origen_normalizado(FORUM_URL), segundos, motivo="flood")` y se lanza
`ForumFloodControl(CortesiaEnEspera)` (`motivo="flood"`). No hay reintento dentro de la petición (es HTTP 200, fuera del bucle de 429/5xx) y **nunca**
se devuelve `[]` ni se escribe «sin resultados». Orquestador: `_forum_fallback` (`orchestrator.py:604-630`) deja propagar `ForumFloodControl`;
`_search_and_rank` lo captura, escribe `MOTIVO_FORO_ESPERA = "El foro pidió esperar unos segundos; se reintentará"`, deja `status=WANTED` y devuelve
`None` (no `[]`). El bloqueo compartido hace que el siguiente intento espere u omita el ciclo.

**AC-FLD-1** flood inglés y español → `ForumFloodControl` con 20–60 s. **AC-FLD-2** `use_ipb_search` **lanza**, no devuelve `[]`. **AC-FLD-3** «0 resultados»
sin caja de error → `[]` sin excepción. **AC-FLD-4** segunda llamada tras el flood = `CortesiaEnEspera`/sin red. **AC-FLD-5** una sola petición de
búsqueda (no consume `max_intentos`). **AC-FLD-6** el orquestador deja `last_error=MOTIVO_FORO_ESPERA`, no `MOTIVO_SIN_RESULTADOS`.

## 3. Validación 3 — HTTP plano sin TLS

No se arregla en código (el foro no ofrece TLS); se avisa y se documenta: (a) tarjeta «Foro» en Ajustes (grupo Descargas) con estado configurado/sin
configurar y, si `FORUM_URL` empieza por `http://`, un `ui.aviso("amber")`: «El foro usa HTTP sin cifrar: tu usuario y contraseña viajan sin protección.
No reutilices una contraseña que uses en otro sitio; si puedes, usa un foro con HTTPS.» La contraseña nunca se pasa a la plantilla. (b) `LEGAL.md:65`
añade la misma advertencia y enlace a «Aviso legal» (el hash de `services/legal.py` versiona la aceptación solo). (c) Se corrige el comentario falso de
`config.py:51-55` según D-1. La allowlist **no** cambia: `http://` sigue siendo válido (foro elegido por el operador, H5).

**AC-TLS-1** Ajustes con `http://` muestra el aviso y con `https://` no. **AC-TLS-2** la respuesta no contiene usuario, contraseña ni cookie.
**AC-TLS-3** `LEGAL.md` contiene la advertencia y `current_legal_version()` cambia. **AC-TLS-4** allowlist/cookies de H5 siguen verdes.

## 4. Intervalos separados (búsqueda vs lectura)

`config.py`: mantener `forum_rate_limit=2,0` (login y lectura de temas) y añadir **`forum_search_rate_limit=25,0`** (20–30 s). En `forum_scraper.py`:
`_politica_lectura = politica_de("foro")` y `_politica_busqueda = PoliticaFuente("foro", "Foro", forum_search_rate_limit, 1, 3)`; la búsqueda usa
la de búsqueda y login/temas la de lectura (`pedir_con_cortesia` registra la política en cada llamada). La cola es la misma fuente «foro» (una búsqueda
espera ≥25 s desde la petición anterior; más estricto, aceptado); `espera_max_s` de búsqueda = `max(30, forum_search_rate_limit + 5)`. El bloqueo por flood
(20–60 s) no consume intentos: se comparte en la cola. **AC-INT-1** `politica_de("foro")` sigue en 2 s. **AC-INT-2** búsqueda a 25 s y `max_intentos=1`.
**AC-INT-3** dos búsquedas seguidas esperan ≥25 s o lanzan `CortesiaEnEspera` sin red (reloj simulado). **AC-INT-4** el constructor toma ambos de settings.

## 5. Script de diagnóstico para el usuario (sin credenciales a la vista)

**`scripts/diagnostico_foro.py`** (nuevo): se ejecuta **dentro del contenedor**, lee `get_settings()` y usa los helpers reales de §1/§2 (no reimplementa
patrones). Máximo **3 peticiones** (4 con `--leer-tema`), pausa ≥3 s, UA `USER_AGENT`; no descarga ni escribe. Con el foro configurado en `.env` y
`FORUM_ENABLED=true` (tras editar `.env`, `docker compose up -d` para recrear):

```bash
docker compose exec zascarr python scripts/diagnostico_foro.py
# opcional: --consulta "Año Uno"  --leer-tema   (añade 1 GET al primer tema)
# sin compose: docker exec zascarr python scripts/diagnostico_foro.py
```

Salida anonimizada (esto es lo que se pega al Lead):
```text
ZascArr — diagnóstico del foro (SCR4)
Foro: http://lamansion-crg.net/forum/  [HTTP SIN TLS: las credenciales viajan sin cifrar]
[1] Entrada: HTTP 200 | charset cabecera: (ausente) | charset meta: iso-8859-1 | usado: iso-8859-1
[2] Login: OK (cookies recibidas: 2; no se imprimen) | flood: no
[3] Búsqueda «Año Uno»: HTTP 200 | flood: NO | resultados: 7 | muestra: tema (sin título)
Conclusión: charset OK; sin flood; 7 resultados. Pega estas líneas al Lead (no pegues el .env).
```
Reglas: **nunca** imprime contraseña, usuario completo, cookies ni `s=<sesión>`; títulos/enlaces no se imprimen (solo tipo `tema`/`ed2k`/`magnet`); tolerante a
fallos con códigos 0 ok, 2 sin configurar, 3 red, 4 flood (con segundos), 5 login fallido, y explicación en español de qué revisar. Si faltan variables lo dice
(sin valores). **AC-DIA-1** sin configurar → explicación, exit 2, 0 peticiones. **AC-DIA-2** `FORUM_PASSWORD`, cookies y `s=` no aparecen en stdout (valor
canario). **AC-DIA-3** flood → exit 4 con segundos y sin muestra. **AC-DIA-4** salida copiable con los 3 pasos y la conclusión.

## 6. Procedimiento de validación en vivo (usuario → Lead)

1. En la Pi: `.env` con `FORUM_ENABLED=true`, `FORUM_URL=http://lamansion-crg.net/forum/`, `FORUM_USERNAME=…`, `FORUM_PASSWORD=…`; `docker compose up -d`
   para recrear. No pegar el `.env` en ningún sitio.
2. Ejecutar el comando de §5: es **una** búsqueda, no repetir seguidas (IPB bloquea por saturación). Si hay flood, esperar los segundos indicados +5 y,
   como máximo, repetir una vez.
3. Pegar al Lead **solo** el bloque de salida. Si resultados=0 con tilde, esperar ≥30 s y repetir con `--consulta "Batman"` para distinguir charset de
   «no hay resultados»; anotar ambos números.
4. Cierre: charset usado latin-1/cp1252, login OK, flood NO, resultados >0 con tilde y aviso visible en Ajustes/LEGAL. La lectura de un tema real queda
   pendiente de que el usuario tenga URLs (deuda declarada, no bloquea SCR4).

## 7. Plan de pruebas sin red (`MockTransport`, sin Postgres)

`tests/test_forum_charset.py` (fixtures bytes reales `login_latin1.html` con meta, `resultados_latin1.html`, `resultados_cp1252.html`): AC-CHA-1…6;
captura del **cuerpo crudo** del POST (`Capit%E1n`, no `Capit%C3%A1n`) y título decodificado sin `�`. `tests/test_forum_flood.py` (`flood_es.html`,
`flood_en.html`, `cero_resultados.html`): AC-FLD-1…6 con cortesía simulada y `FakeSession` para el orquestador. `tests/test_forum_intervalos.py`:
AC-INT-1…4 con reloj simulado. `tests/test_forum_ajustes_http.py`: AC-TLS-1…4 con `TestClient`. `tests/test_diagnostico_foro.py`: AC-DIA-1…4 con
transporte falso y valor canario. Los existentes `test_forum_scraper.py` (369 líneas) y `test_forum_cortesia.py` deben seguir verdes: H5 no se toca.

## 8. Riesgos, límites y deudas

- La validación con credenciales no puede hacerse aquí: la meta confirma el charset, pero el POST con tilde solo se valida en vivo.
- Flood: el board está en español y el texto puede cambiar; el detector exige caja de error + frase (conservador). Falso negativo ⇒ comportamiento actual;
  falso positivo ⇒ espera visible, nunca vacío; el script dice si detectó flood para ajustar patrones.
- Cooldown de 6 h: el mark de intento (`orchestrator.py:307`) va antes del foro por D1/H2/C6; un flood no es «sin resultados» pero sí gasta ese cooldown
  (excluirlo exige reordenar el mark, D-3). Sin URLs de hilos, lectura de temas y `ed2k/magnet` solo con fixtures (deuda de validación en vivo).
- Cookie de sesión no se refresca (H5); sesión caducada ⇒ login por ciclo. HTTP plano no se arregla, solo se avisa. `s=<sesión>`: el log de tema pasa a
  host+motivo sin query y el script la enmascara; UA `"ZascArr/0.1"` pasa a `utils/robots.USER_AGENT`.

## 9. Decisiones para el PO

| # | Decisión | Recomendación |
|---|---|---|
| D-1 | ¿Foro configurable en Ajustes (URL/usuario/contraseña/activar, grupo runtime y secretos) o se queda en `.env` y Ajustes solo muestra aviso/estado? | Tarjeta completa: es lo coherente con «activa el foro en Ajustes» (`orchestrator.py:114`); si no, corregir ese texto y `config.py:51-55` |
| D-2 | ¿Se conserva `http://` (con aviso) o se exige HTTPS? | Conservar: el foro no ofrece TLS y el operador decide; aviso visible + LEGAL |
| D-3 | ¿El flood debe conservar el cooldown de 6 h? | Dejarlo (es un intento real), anotado como límite |
