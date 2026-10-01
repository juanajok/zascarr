# Inventario de la UI actual y mapa de migración (V0)

> Documento de la historia **V0** de la Épica V (`docs/BACKLOG.md`). Es el inventario que pedía
> su criterio 1 y 2, más lo que se ha aprendido al leer el código. **No cambia código de la
> aplicación.** Estado de `main` inventariado: `ab49c76` (2026-10-01, ZascArr 1.15.1 + A11).

## 1. Método y límites

- **Se ha leído** el código, no se ha supuesto: los 11 routers de `src/zascarr/web/`, las
  28 plantillas de `web/templates/` (13 páginas y 15 parciales), `static/web.css`,
  `main.py`, `services/auth.py` (`AuthMiddleware`), `services/review.py` y los tests que fijan la UI.
- Las tablas de **rutas** y de **plantillas** de abajo se han **generado** recorriendo el AST de los
  routers y las plantillas (decoradores `@router.get|post`, `Form(...)`, `TemplateResponse(...)`,
  atributos `hx-*`), no transcritas a mano. Los contrastes de color se han **calculado** (fórmula WCAG).
- **Lo que depende de la ejecución se comprobó después, en la línea base** (`docs/design/ui-baseline/`):
  la aplicación se levantó con Postgres propio y datos sintéticos, y se midió en Chrome 154 cómo trata
  htmx 4 un `409` y qué hace `/estado` con la BD caída. Las secciones 2.1 y 2.5 llevan **esos
  resultados**, no suposiciones. Lo que **sigue sin verificar** se marca como tal.
- **Línea base de capturas (criterio 3 de V0): hecha** — 37 capturas y 4 ficheros de datos
  reproducibles con los comandos de `docs/design/ui-baseline/README.md`. Límites allí: un navegador, un
  equipo, datos sintéticos, no sustituye la verificación en la Pi (V13).

## 2. Lo que el inventario corrige de la Épica V

La épica se redactó **sin leer las plantillas** (ella misma lo declara). Esto es lo que no
coincidía o faltaba, ordenado por impacto en el plan:

1. **`Estado` vive en `/estado`, no en `/ui/estado`** (`web/estado.py`: `APIRouter(tags=["ui"])` sin
   prefijo). No es un descuido: `/estado` está en `_RUTAS_DIAGNOSTICO` (`services/auth.py`) y se sirve
   incluso con la base de datos caída (arranque degradado, E6), igual que `/api/health`, `/login` y
   `/legal`. **Consecuencia para V3/V9:** cualquier fragmento de menú o de estado que se añada
   (`/ui/_nav/estado`) cae bajo `/ui/*`, que en modo degradado devuelve un **503 HTML**; con htmx 4
   (ver punto 5) ese HTML acabaría pintado en el menú. **Medido en la línea base:** con la BD caída y
   la app **ya en marcha**, `/ui/` responde un **`500` de texto plano** (`Internal Server Error`), y
   solo con la BD caída **desde el arranque** responde el `503` descrito; `/estado` y `/api/health`
   responden `200` en ambos casos. Por tanto el fragmento debe contemplar **cualquier** fallo, no
   solo el modo degradado de E6. Hay que decidir explícitamente cómo se
   comporta el fragmento con la BD caída, y la decisión «las URL no cambian» **incluye** que `/estado`
   se queda en `/estado`.
2. **La página estática `/` ya no existe.** `main.py` registra `GET /` como redirección 307 a `/ui/`
   (la estática de E1 se retiró). **El criterio 6 de V0 queda resuelto**: no hay nada que unificar; lo
   que sí hay son **dos pantallas distintas** —`/ui/` (métricas de la colección) y `/estado` (salud)—
   y la maqueta fusiona la primera en «Inicio». Ver §5.
3. **«Cero JavaScript propio» no describe el estado actual**: `estado.html` lleva **~100 líneas de JS
   inline** (`fetch("/api/health")` cada 10 s y pintado en el cliente), y `pendientes.html` usa
   `onerror="…"` en la portada. La decisión 3 de la épica debe redactarse como **«no se añade JS
   propio nuevo; el existente se retira cuando su pantalla se migra»** (ADR 0005), y V9 debe
   resolver cómo se sustituye el sondeo (ver §6).
4. **El menú actual no coincide con las pantallas**: «Biblioteca» enlaza a `/ui/` (el panel de
   métricas), «Mi biblioteca» a `/ui/auditoria` (duplicados) y **la rejilla real, `/ui/biblioteca`, no
   está en el menú** (solo se llega desde un enlace del panel y del aviso legal). La maqueta lo
   ordena (Inicio / Biblioteca / Duplicados), pero eso **mueve** qué ruta cuelga de cada etiqueta.
5. **htmx 4.0.0 está vendorizado** (`static/vendor/README.md`), y su configuración por defecto tiene
   `noSwap:[204,304]` (leído en `htmx.min.js`): **todo estado distinto de 204/304 se intercambia**,
   incluidos 4xx y 5xx. Hoy `asignar` responde `409`/`400` con un cuerpo JSON de FastAPI.
   **Verificado en la línea base (Chrome 154, htmx 4.0.0):** al asignar un ómnibus a una serie cuyo
   nº 12 es una grapa, el servidor responde `409` + `{"detail": "…"}` y **htmx intercambia ese
   cuerpo: la tarjeta desaparece y en su lugar queda el JSON en crudo**, como texto suelto en la
   rejilla. El estado real es correcto (el archivo no se movió, queda pendiente con su motivo en la
   BD); lo que falla es **lo que ve el coleccionista**, que puede creer que ha perdido el archivo. Es un
   defecto **ya existente en producción**, no se corrige en V0 (`ui-baseline/README.md` §1), y
   condiciona V6b: el lote **no** puede depender de `HTTPException`.
6. **Pendientes tiene tope y no tiene recuento**: `ReviewService.pending_files(limit=50)`; no hay
   consulta de recuento. La maqueta enseña «14» y un contador en el menú: con >50 pendientes el
   número sería falso. Hace falta un `contar_pendientes()` (servicio puro con prueba).
7. **Asignar exige número de issue por archivo** (`issue_number: str = Form(...)`; `ValueError` si va
   vacío). **La maqueta asigna 14 archivos a una serie sin pedir ningún número** y varios nombres no
   lo traen («LA PATRULLA X por Whedon y Cassaday…», «Los Años Perdidos»). El lote real necesita un
   número por fila (prefill desde `parse_comic_filename`, como ya hace la sugerencia de un clic) y un
   camino para «sin número».
8. **El alias se aprende SIEMPRE** (`_learn_alias`, B13, incondicional en `assign_to_series`). La
   maqueta ofrece una casilla «Recordar el patrón» marcada. **Hacerla opcional cambia el
   comportamiento de B13** (firma de `assign_to_series` y sus tests de B13) y el patrón que se
   guarda es `normalize_title(parsed.series)` **por archivo**, no el «grupo» que la maqueta escribe a
   mano. El agrupado por patrón de la maqueta (`g`) es **dato inventado**: no existe ninguna función
   que agrupe; hay que escribirla y probarla.
9. **El patrón mover + `flush` con la sesión viva sigue sin auditar**: `assign_to_series` llama a
   `safe_move_async` y solo hace `flush` (el `commit` lo hace la dependencia al final de la
   petición: `get_db` hace `commit` al salir y `rollback` si hay excepción). `CLAUDE.md` §3.1.2 lo deja explícitamente «pendiente de auditar». **Un lote
   multiplica el riesgo** (N movimientos con una sesión): el «commit por archivo» de V6a exige hacer esa
   auditoría **antes**, no durante.
10. **Ignorar no es reversible hoy**: `ReviewService.dismiss` pone `File.review_dismissed = True` y
    **no existe** método de recuperar ni consulta de ignorados. La columna sí existe, así que V7 es
    posible sin migración, pero no es solo presentación: hace falta servicio + rutas + pruebas.
11. **Ajustes y A11 (la maqueta contradice la postura ya implementada):** el panel «Proteger con
    contraseña» de la maqueta incluye un selector **«Quién puede entrar: solo esta máquina / red local
    / internet»**. **Eso no se puede implementar en Ajustes**: el puerto publicado es de Docker en el
    host y la aplicación no puede cambiar el suyo (ADR 0004, A11). Ajustes debe **informar** de la
    exposición efectiva (`estado_de_seguridad`: `exposicion`, `contrasena`, `atencion`) y decir cómo
    cambiarla (**volver a ejecutar el instalador**), nunca ofrecer el conmutador. Además, el campo
    `base_url` **sigue en Ajustes** (`/ui/ajustes/guardar/seguridad`) y tiene dos dueños (`.env` y
    Ajustes; manda Ajustes): el instalador ya lo reconcilia, y la UI nueva debe conservarlo (el
    mensaje existente explica el caso del proxy que cambia `Host`). También: la maqueta usa
    `type="text"` para la contraseña; en producción es `type="password"`.
12. **A11 ya da a V9 la señal de seguridad**: `/api/health` trae `seguridad.atencion` (abierto sin
    contraseña), separada de `status`. El «Estado» nuevo debe pintarla como «Atención» sin cambiar
    el semáforo técnico.
13. **El «un solo buscador» de la maqueta junta dos contratos distintos**: `/ui/wishlist/buscar-serie`
    (busca en **tu** base de datos; lo usan el panel y Deseados) y `/ui/descubrir/buscar` (busca en
    **fuentes externas** y da de alta con `/ui/descubrir/crear`). Unificarlos es una decisión de
    producto. **Decidido (2026-10-01):** el Inicio tiene una entrada principal «Buscar una serie» que lleva
    a **Descubrir**; **no se unifican** todavía la búsqueda local y la externa; Deseados conserva su
    búsqueda local, claramente etiquetada.
14. **El panel (`/ui/`) lleva la lógica en el router**: cinco consultas y el cálculo de huecos dentro
    de `web/dashboard.py`. V4 («`PrimerosPasos` servicio puro») implica **extraer** esa lógica a
    `services/` antes de poder reutilizarla — coherente con `CLAUDE.md` §3.1.1, pero es trabajo que
    V4 no listaba.
15. **«Hemos leído tu biblioteca» no es automático**: la adopción (B11) es una **acción explícita**
    (`POST /ui/auditoria/adoptar`, `LibraryAdopter.should_run()`), y el último informe de duplicados
    se guarda en `ImportRun` (`details.kind == "audit"`). El paso 1 del Inicio se deriva de ambas
    cosas; «432 comparados a fondo» solo existe si hay un informe previo.
16. **El análisis de duplicados es síncrono dentro de la petición** (`POST /ui/auditoria/analizar`
    espera a `LibraryAudit.run()`): sin progreso real (V11b = backend nuevo, ya lo decía la épica) y,
    en una biblioteca grande en una Pi, es una petición larga con el navegador esperando.
17. **Contraste: las cifras de V1 se confirman** (calculadas): `--ink-faint` 3,05:1 sobre `--paper` y
    2,82:1 sobre `--paper-2`; `--cyan` 2,84:1; `--ok` 3,83:1; en oscuro `--ink-faint` 4,47:1 y 4,14:1.
    `--warn` sobre `--paper` da 4,91:1 (pasa; la épica no lo daba por fallido). **Defecto en la
    propia maqueta:** la insignia `.badge.hot` en **modo oscuro** (texto blanco sobre `#f04d97`) da
    **3,38:1**, por debajo de 4,5:1 para texto normal. La prueba automática de V1 lo habría cazado;
    hay que corregir ese par antes de copiar los tokens. El resto de pares de la maqueta, claro y
    oscuro, supera 4,5:1 (§7).

## 3. Mapa de plantillas (las 28)

«Clases» es el número de clases CSS distintas que usa la plantilla (para V2: lo que hay que mapear a
componentes). «JS» marca JavaScript propio dentro de la plantilla.

| Plantilla | Bytes | Hereda | Incluye | La sirve | Endpoints `hx-*` que dispara | Clases | JS |
|---|---:|---|---|---|---|---:|---|
| `_ajustes_guardado.html` | 231 | — | — | POST /ui/ajustes/guardar/comic-vine ; POST /ui/ajustes/guardar/avisos ; POST /ui/ajustes/guardar/fuentes ; POST /ui/ajustes/guardar/prowlarr ; POST /ui/ajustes/guardar/transmission ; POST /ui/ajustes/guardar/amule ; POST /ui/ajustes/guardar/seguridad | — | 3 | — |
| `_ajustes_prueba.html` | 116 | — | — | POST /ui/ajustes/probar/avisos ; POST /ui/ajustes/probar/comic-vine ; POST /ui/ajustes/probar/prowlarr ; POST /ui/ajustes/probar/transmission ; POST /ui/ajustes/probar/amule | — | 4 | — |
| `_auditoria_adopcion.html` | 844 | — | — | POST /ui/auditoria/adoptar | — | 4 | — |
| `_auditoria_informe.html` | 5190 | — | — | POST /ui/auditoria/analizar | `/ui/auditoria/adoptar` | 11 | — |
| `_candidatos_wishlist.html` | 1272 | — | — | POST /ui/wishlist/{item_id}/buscar-ahora | `/ui/wishlist/{…}/cancelar-busqueda`<br>`/ui/wishlist/{…}/enviar-candidato` | 8 | — |
| `_fila_wishlist.html` | 1342 | — | — | POST /ui/wishlist/anadir ; POST /ui/wishlist/{item_id}/reintentar ; POST /ui/wishlist/{item_id}/enviar-candidato | `/ui/wishlist/{…}/buscar-ahora`<br>`/ui/wishlist/{…}/quitar`<br>`/ui/wishlist/{…}/reintentar` | 9 | — |
| `_legal_disclaimer.html` | 874 | — | — | (incluida) | — | 4 | — |
| `_politica_serie.html` | 3867 | — | — | POST /ui/series/{series_id}/politica | `/ui/series/{…}/politica` | 11 | — |
| `_rejilla_biblioteca.html` | 1356 | — | — | GET /ui/biblioteca/resultados | `{…}` | 12 | `onerror` |
| `_resultados_descubrir.html` | 2171 | — | — | GET /ui/descubrir/buscar | `/ui/descubrir/crear` | 10 | `onerror` |
| `_resultados_personaje.html` | 243 | — | — | GET /ui/biblioteca/buscar-personaje | — | 2 | — |
| `_resultados_saga.html` | 250 | — | — | GET /ui/biblioteca/buscar-saga | — | 2 | — |
| `_resultados_serie.html` | 664 | — | — | GET /ui/pendientes/{file_id}/buscar-serie | `/ui/pendientes/{…}/asignar` | 5 | — |
| `_resultados_series_wishlist.html` | 715 | — | — | GET /ui/wishlist/buscar-serie | `/ui/wishlist/anadir` | 4 | — |
| `_serie_creada.html` | 945 | — | — | POST /ui/descubrir/crear | `/ui/wishlist/anadir` | 7 | `onerror` |
| `ajustes.html` | 12567 | base.html | _legal_disclaimer.html | GET /ui/ajustes | `/ui/ajustes/guardar/amule`<br>`/ui/ajustes/guardar/avisos`<br>`/ui/ajustes/guardar/comic-vine`<br>`/ui/ajustes/guardar/fuentes`<br>`/ui/ajustes/guardar/prowlarr`<br>`/ui/ajustes/guardar/seguridad`<br>`/ui/ajustes/guardar/transmission`<br>`/ui/ajustes/probar/amule`<br>`/ui/ajustes/probar/avisos`<br>`/ui/ajustes/probar/comic-vine`<br>`/ui/ajustes/probar/prowlarr`<br>`/ui/ajustes/probar/transmission` | 7 | — |
| `auditoria.html` | 822 | base.html | _auditoria_informe.html | GET /ui/auditoria | `/ui/auditoria/analizar` | 3 | — |
| `base.html` | 1079 | — (autónoma) | _legal_disclaimer.html | — | — | 6 | — |
| `biblioteca.html` | 2141 | base.html | _rejilla_biblioteca.html | GET /ui/biblioteca | `/ui/biblioteca/buscar-personaje`<br>`/ui/biblioteca/buscar-saga`<br>`/ui/biblioteca/resultados` | 6 | — |
| `dashboard.html` | 3015 | base.html | — | GET /ui/ | `/ui/wishlist/buscar-serie` | 23 | `onerror` |
| `descubrir.html` | 656 | base.html | — | GET /ui/descubrir | `/ui/descubrir/buscar` | 3 | — |
| `estado.html` | 4682 | base.html | — | GET /estado | — | 16 | JS inline |
| `legal_full.html` | 181 | base.html | — | GET /legal | — | 1 | — |
| `legal_wizard.html` | 1362 | base.html | — | GET /ui/legal | — | 3 | — |
| `login.html` | 1010 | — (autónoma) | — | GET /login ; POST /login | — | 5 | — |
| `pendientes.html` | 2552 | base.html | — | GET /ui/pendientes | `/ui/pendientes/{…}/asignar`<br>`/ui/pendientes/{…}/buscar-serie`<br>`/ui/pendientes/{…}/ignorar` | 19 | `onerror` |
| `series_detail.html` | 1671 | base.html | _legal_disclaimer.html, _politica_serie.html | GET /ui/series/{series_id} | — | 11 | `onerror` |
| `wishlist.html` | 1156 | base.html | _fila_wishlist.html, _legal_disclaimer.html | GET /ui/wishlist | `/ui/wishlist/buscar-serie` | 7 | — |

Observaciones del mapa:

- **`login.html` no hereda de `base.html`** (es autónoma, sin menú ni pie): V1/V2/V3 no la alcanzan por
  herencia; hay que tocarla aparte (V12 la lista, pero sus tokens dependen de V1).
- Las páginas que **no** dispararon ningún `hx-*` son `estado.html` (usa `fetch`), `series_detail.html`
  (solo incluye `_politica_serie.html`, que sí lo hace), `legal_*` y `login.html`.
- **Herencia:** 11 de las 13 «páginas» heredan de `base.html`; las otras dos son la propia `base.html`
  (la raíz) y `login.html` (autónoma). La afirmación «las 13 páginas heredan de `base.html`» de la épica
  era inexacta y está corregida.
- `base.html` incluye el aviso legal del pie (`_legal_disclaimer.html`) y el menú; **el menú no tiene
  clase de «página actual»** (no hay `aria-current`) ni contadores.
- Familias de clases en `web.css` (856 líneas, 52 declaraciones de `font-size`): `topnav`, `pending-*`,
  `estado-*`, `audit-*`, `ajustes-*`, `library-*`, `discovery-*`, `wishlist-*`, `candidato*`,
  `politica-*`, `legal-*`, `issue-*`, `series-*`, `metric-*`. La maqueta propone `.btn`, `.chip`,
  `.card`, `.group`, `.caption`…: **hoy existen `.caption`, `.empty` y el estilo de botones**
  (`button` global más `.btn`, `.btn-primary`, `.btn-ignorar`, `.btn-reintentar`…); **no existen**
  `.chip`, `.card`, `.group`/`.ghead`, `.progress`, `.hero-state`, `.toast`, `.badge`, pestañas ni
  barra lateral (el menú actual es horizontal, `.topnav`, con solo dos puntos de corte `max-width`:
  768 y 480 px). V2 es mayormente **crear** componentes, no renombrar, y V3 es un cambio de
  disposición (de barra superior a lateral + barra inferior móvil), no de etiquetas.

## 4. Rutas y contratos HTMX a conservar

Generada del AST de los routers. `*` = campo obligatorio de formulario. «Errores explícitos» son los
códigos HTTP que el handler lanza o devuelve. «Gate legal» = lleva `Depends(require_legal_acknowledgment)`
(responde `403` con cabecera `HX-Redirect: /ui/legal`, un mecanismo que htmx interpreta solo).

| Fichero | Método | Ruta | Campos (`*` = obligatorio) | Responde | Errores explícitos | Gate legal |
|---|---|---|---|---|---|---|
| ajustes | GET | `/ui/ajustes` | — | ajustes.html | — | — |
| ajustes | POST | `/ui/ajustes/guardar/comic-vine` | comicvine_api_key | _ajustes_guardado.html | — | — |
| ajustes | POST | `/ui/ajustes/guardar/avisos` | webhook_enabled,webhook_type,webhook_url,webhook_token,webhook_chat_id,webhook_incluir_nombres | _ajustes_guardado.html | — | — |
| ajustes | POST | `/ui/ajustes/probar/avisos` | webhook_type,webhook_url,webhook_token,webhook_chat_id | _ajustes_prueba.html | — | — |
| ajustes | POST | `/ui/ajustes/guardar/fuentes` | comicvine_enabled,anilist_enabled,tebeosfera_enabled,gcd_enabled | _ajustes_guardado.html | — | — |
| ajustes | POST | `/ui/ajustes/guardar/prowlarr` | prowlarr_url*,prowlarr_api_key,prowlarr_enabled | _ajustes_guardado.html | — | — |
| ajustes | POST | `/ui/ajustes/guardar/transmission` | transmission_url*,transmission_username,transmission_password,transmission_enabled | _ajustes_guardado.html | — | — |
| ajustes | POST | `/ui/ajustes/guardar/amule` | amule_url*,amule_password,amule_enabled | _ajustes_guardado.html | — | — |
| ajustes | POST | `/ui/ajustes/guardar/seguridad` | auth_mode*,auth_username,auth_password,base_url | _ajustes_guardado.html | 400 | — |
| ajustes | POST | `/ui/ajustes/probar/comic-vine` | comicvine_api_key | _ajustes_prueba.html | — | — |
| ajustes | POST | `/ui/ajustes/probar/prowlarr` | prowlarr_url*,prowlarr_api_key | _ajustes_prueba.html | — | — |
| ajustes | POST | `/ui/ajustes/probar/transmission` | transmission_url*,transmission_username,transmission_password | _ajustes_prueba.html | — | — |
| ajustes | POST | `/ui/ajustes/probar/amule` | amule_url*,amule_password | _ajustes_prueba.html | — | — |
| auditoria | GET | `/ui/auditoria` | — | auditoria.html | — | — |
| auditoria | POST | `/ui/auditoria/analizar` | — | _auditoria_informe.html | — | — |
| auditoria | POST | `/ui/auditoria/adoptar` | — | _auditoria_adopcion.html | — | — |
| auth | GET | `/login` | next | login.html | — | — |
| auth | POST | `/login` | next,username,password | login.html | 303,401,429 | — |
| auth | POST | `/logout` | — | (redirige) | 303 | — |
| dashboard | GET | `/ui/` | — | dashboard.html | — | — |
| discovery | GET | `/ui/descubrir` | — | descubrir.html | — | — |
| discovery | GET | `/ui/descubrir/buscar` | q | _resultados_descubrir.html | — | — |
| discovery | GET | `/ui/descubrir/portada` | — | (otra) | 400,404 | — |
| discovery | POST | `/ui/descubrir/crear` | source*,external_id*,title*,tradition*,start_year,description,cover_url | _serie_creada.html | 400 | — |
| estado | GET | `/estado` | — | estado.html | — | — |
| legal | GET | `/ui/legal` | — | legal_wizard.html | — | — |
| legal | POST | `/ui/legal/accept` | acepto_1,acepto_2,acepto_3 | (redirige) | 303 | — |
| legal | GET | `/legal` | — | legal_full.html | — | — |
| library | GET | `/ui/biblioteca` | page,tradition,publisher_id,character_id,story_arc_id,q | biblioteca.html | — | — |
| library | GET | `/ui/biblioteca/resultados` | page,tradition,publisher_id,character_id,story_arc_id,q | _rejilla_biblioteca.html | — | — |
| library | GET | `/ui/biblioteca/buscar-personaje` | q | _resultados_personaje.html | — | — |
| library | GET | `/ui/biblioteca/buscar-saga` | q | _resultados_saga.html | — | — |
| pendientes | GET | `/ui/pendientes` | — | pendientes.html | — | — |
| pendientes | GET | `/ui/pendientes/{file_id}/portada` | — | (otra) | 404 | — |
| pendientes | GET | `/ui/pendientes/{file_id}/buscar-serie` | q | _resultados_serie.html | — | — |
| pendientes | POST | `/ui/pendientes/{file_id}/asignar` | series_id*,issue_number* | (vacío) | 400,409 | — |
| pendientes | POST | `/ui/pendientes/{file_id}/ignorar` | — | (vacío) | 404 | — |
| series | GET | `/ui/series/{series_id}` | — | series_detail.html | 404 | — |
| series | POST | `/ui/series/{series_id}/politica` | wishlist_policy* | _politica_serie.html | 404,422 | — |
| series | GET | `/ui/series/{series_id}/portada` | — | (otra) | 404 | — |
| wishlist | GET | `/ui/wishlist` | — | wishlist.html | — | — |
| wishlist | GET | `/ui/wishlist/buscar-serie` | q | _resultados_series_wishlist.html | — | — |
| wishlist | POST | `/ui/wishlist/anadir` | series_id* | _fila_wishlist.html | 400 | sí |
| wishlist | POST | `/ui/wishlist/{item_id}/quitar` | — | (vacío) | 404 | — |
| wishlist | POST | `/ui/wishlist/{item_id}/reintentar` | — | _fila_wishlist.html | 404 | sí |
| wishlist | POST | `/ui/wishlist/{item_id}/buscar-ahora` | — | _candidatos_wishlist.html | 404 | sí |
| wishlist | POST | `/ui/wishlist/{item_id}/cancelar-busqueda` | — | (vacío) | — | — |
| wishlist | POST | `/ui/wishlist/{item_id}/enviar-candidato` | token* | _fila_wishlist.html | 400,404 | sí |



**Contratos que no se pueden romper** (cualquier historia que los toque debe conservar URL, método,
campos y forma del fragmento hasta que otra los sustituya y esté escrito en su ficha):

| Contrato | Quién lo usa | Qué espera |
|---|---|---|
| `POST /ui/pendientes/{id}/asignar` → `""` | tarjeta de `pendientes.html`, `hx-target="#card-{id}"` `hx-swap="outerHTML"` | 200 con cuerpo vacío = la tarjeta desaparece; 400/409 → ver §2.5 |
| `POST /ui/pendientes/{id}/ignorar` → `""` | mismo patrón, con `hx-confirm` | idem |
| `GET /ui/pendientes/{id}/buscar-serie?q=` → `_resultados_serie.html` | `keyup changed delay:400ms` | fragmento con un `assign-form` por serie, que a su vez hace `hx-post` a `asignar` |
| `POST /ui/wishlist/anadir` (`series_id`) → `_fila_wishlist.html` | panel, Deseados, `_serie_creada.html`, `_resultados_series_wishlist.html` | una fila lista para insertar; `403`+`HX-Redirect` si falta el aviso legal |
| `POST /ui/wishlist/{id}/(quitar\|reintentar\|buscar-ahora\|cancelar-busqueda\|enviar-candidato)` | `_fila_wishlist.html`, `_candidatos_wishlist.html` | filas/candidatos como arriba; `enviar-candidato` exige `token` |
| `POST /ui/ajustes/guardar/*` y `probar/*` (12 rutas) | `ajustes.html` | `_ajustes_guardado.html` / `_ajustes_prueba.html`; **D11: guardar aplica al instante y los secretos nunca vuelven en claro**; **A6: el guardarraíl de contraseña** (400) |
| `GET /ui/biblioteca/resultados`, `buscar-personaje`, `buscar-saga` | `biblioteca.html`, paginación | rejilla / listas con enlaces `?character_id=`/`?story_arc_id=` |
| `POST /ui/auditoria/(analizar\|adoptar)` | `auditoria.html` | informe / resultado de adopción; **solo lectura salvo adoptar, y adoptar no mueve nada** |
| `GET /api/health` | `estado.html` (`fetch`) | JSON con `status`, `checks`, `warnings`, **`seguridad`** (A11), `version` |
| `GET /estado` | menú, mensaje del arranque degradado | página servida con la BD caída |
| `GET /` | todos | redirección 307 a `/ui/` |

**Pruebas que fijan la UI actual** (lo que se rompe si se toca sin cuidado): `tests/test_web_dashboard.py`
(l.109–110: `'<nav class="topnav">'` y `'href="/estado">Estado</a>'`), `tests/test_web_discovery.py`
(l.62: `'<nav class="topnav">'`), `tests/test_web.py` (`/estado`, raíz, estáticos, htmx `4.0.0`),
`tests/test_web_library.py` (l.118: el fragmento no repite el layout), más unas 140 referencias al
`.text` de las respuestas repartidas en `test_web_*.py` y `test_pendientes.py`. **V3 romperá a propósito las dos primeras**:
su ficha debe decir que se actualizan, no que se esquivan.

## 5. La maqueta frente a la realidad

Se incorpora tal cual como `docs/design/maqueta-ui.html` (sin modificar; mismo contenido que el
fichero recibido). **Es una propuesta navegable, no un producto**: lo que sigue **simula** o **inventa**.

**Simulado con JavaScript (no se traduce igual en producción; ver la tabla de la épica):**
deshacer tras asignar (**no existe operación inversa**), deshacer tras ignorar (sí es posible, V7),
selección múltiple y barra de acciones, confirmación en `<dialog>`, pestañas, objetivos de Ajustes,
conmutador claro/oscuro (se difiere), barra de progreso de la revisión (temporizador falso), toasts,
router por `#hash`, «Ver anotaciones UX».

**Datos inventados o fijos:** los 14 archivos y sus «grupos» y porcentajes, «1.542 tebeos», «432
comparados», «7,5 GB recuperables», «200 duplicados», los estados de Estado (VPN «no lo sabemos»),
«ZascArr v1.15.0», «5 peticiones iguales» de BPRD.

**Botones que no tienen backend hoy:** «Unir duplicadas» (en Deseados los items **manuales** no tienen unicidad a propósito (el índice único parcial `uq_wishlist_politica_numero`, migración 0015, cubre solo `origen = 'politica'` con número; decisión de D8 por la lección de Kapowarr: un `UNIQUE` en una tabla gestionada desde la UI exige una reconciliación amable), ni hay operación de
unir), «Silenciar aviso de VPN» (haría falta un indicador en `runtime_settings`), «Copiar comando»
(**el portapapeles exige JS**: sin JS se muestra el comando en un bloque seleccionable con
`user-select: all`), «Recuperar» ignorados, la pestaña «Ignorados», el recuento del menú, el orden
«por mayor ahorro» y los totales de ahorro del informe de duplicados (hay que comprobar qué trae ya
`_auditoria_informe`), y el progreso real.

**Lo que la maqueta no cubre** (V12 lo asume): Biblioteca y Descubrir (marcadas «fuera de alcance»),
ficha de serie, política de búsqueda de la serie (`_politica_serie`, D8), candidatos de búsqueda
manual (`_candidatos_wishlist`), login, aviso legal.

**Lo que ya existe y la maqueta omite o cambia:** «Cerrar sesión» (existe, condicionado a
`auth_activo()`); **Ajustes tiene hoy 7 bloques** (Fuentes de metadatos, Comic Vine, Prowlarr,
Transmission, aMule, Seguridad y Avisos) y la maqueta los reparte en **4 objetivos**: hay que decidir
dónde caen Fuentes (la maqueta solo lista Comic Vine, AniList y Tebeosfera: **falta GCD**, que sí
tiene casilla `gcd_enabled`) y la clave de Comic Vine, y que «Que se descarguen solos» junta tres
bloques (Prowlarr, Transmission y aMule; la maqueta solo enseña los dos primeros),
el aviso de uso responsable (la maqueta lo pone en un `<details>`; el aviso legal real **bloquea
acciones de riesgo** y tiene su propio flujo `/ui/legal`).

## 6. Estimaciones revisadas con el inventario

| Historia | Antes | Ahora | Por qué |
|---|---|---|---|
| V0 | S | S | En curso: inventario terminado, línea base de capturas pendiente. |
| V1 | M | **M** (confirmada) | 31 de 52 `font-size` están por debajo de 14 px (`.875rem`), 11 `color: var(--cyan\|ok\|warn)` sobre texto y 18 usos de `--ink-faint` → trabajo acotado y mecánico; la prueba de contraste es nueva. **Corregir `.badge.hot` oscuro** (§2.17). |
| V2 | M | **M** | Mayormente crear componentes (§3), no renombrar. Las macros se registran en `crear_templates()`. |
| V3 | M | **M, con riesgo** | Cambiar `base.html` rompe 2 pruebas fijadas a propósito; el fragmento de contadores necesita decidir su comportamiento con la BD caída (§2.1) y no existe `aria-current`. |
| V4 | M | **M→L** | Antes hay que **extraer** las 5 consultas del router a un servicio (§2.14), y el paso 1 se deriva de `LibraryAdopter` + `ImportRun`. |
| V5 | L | **L** | Falta `contar_pendientes()`, el tope de 50 y la función pura de agrupado por patrón (§2.6, §2.8). |
| V6 | L | **XL → dividir** | **V6a** (servicio): lote con `commit` por archivo, número por fila, alias opcional (cambia B13) y la **auditoría previa de mover + sesión viva** (§2.7–2.9). **V6b** (UI): previsualizar/confirmar y éxito parcial, **tras verificar el comportamiento htmx de los 4xx** (§2.5). |
| V7 | S | **S→M** | La columna existe, pero no hay servicio ni rutas de recuperar ni lista de ignorados (§2.10). |
| V8 | M | **M** | «Unir duplicadas» **queda fuera de la migración** (decisión de producto 7b): V8 agrupa visualmente y muestra número, edición y estado; no borra ni fusiona filas. |
| V9 | M | **M→L** | Hay que sustituir ~100 líneas de JS (§2.3) por HTMX **sin depender de la BD** (`/estado` es diagnóstico), añadir el bloque `seguridad` (§2.12) y «silenciar VPN» (indicador nuevo). «Copiar comando» sin JS: bloque seleccionable. |
| V10 | L | **L** | 12 endpoints de D11 intactos; **no** copiar el selector de exposición de la maqueta (§2.11); conservar `base_url`. |
| V11 | M | **M** | Comprobar qué trae ya el informe (tamaños) antes de prometer el orden por ahorro; V11b (progreso) sigue siendo backend. |
| V12 | M | **M→L** | Cinco pantallas **sin maqueta** (+ política de serie y candidatos) y `login.html` fuera de la herencia. |
| V13 | M | **M** | Sin cambios. |
| V14 | S | **S** | Sin cambios. |

Por tanto: el orden de fusión cambia solo en que **V6 se divide** (V6a —servicio y auditoría— antes de la
puerta G1; V6b —interfaz— después) y la verificación de htmx 4 con errores 4xx pasa a ser
**precondición de V6b**. Si la auditoría de V6a exige esquema, esa dependencia se separa (decisión 5).

## 7. Contrastes calculados (WCAG 2.x, razón de luminancia relativa)

**Hoy, `web.css`**: `--ink-faint` sobre `--paper` 3,05 · sobre `--paper-2` 2,82 · `--cyan`/`--paper`
2,84 · `--ok`/`--paper` 3,83 · `--warn`/`--paper` 4,91 · `--ink-soft`/`--paper` 7,94. **Oscuro:**
`--ink-faint`/`--paper` 4,47 · /`--paper-2` 4,14.

**Maqueta, claro** (todos ≥ 4,5): `--faint` 5,37 (paper) · 4,96 (paper-2) · 5,86 (card) · `--cyan-t` 5,39 ·
5,15 (info-bg) · `--ok-t`/`--ok-bg` 5,57 · `--warn-t`/`--warn-bg` 5,50 · `--amber-t`/`--amber-bg` 5,60 ·
`--mag-t` 6,12 · texto sobre `--yellow` 10,87 · blanco sobre `--magenta` (insignia) 4,86.
**Maqueta, oscuro** (todos ≥ 4,5 **salvo uno**): `--faint` 6,66 · `--cyan-t` 9,37 · `--ok-t` 9,67 ·
`--warn-t` 6,81 · `--amber-t` 11,22 · **blanco sobre `#f04d97` (insignia `.badge.hot`) 3,38 ✗**.
