# Benchmark — flujo de «Deseados»: buscar, elegir, descargar e importar

> **Nivel 2** (§13 de CLAUDE.md): toca búsqueda, descarga e importación. **Fecha:** 2026-11-16.
> **Caducidad:** 2027-01-15 o antes si cambia una referencia o una historia.
> **Estado:** ficha de cierre de la pasada de Deseados; las correcciones citadas ya están en `main`
> (PRs indicados). No es una aprobación: es insumo para decidir los huecos que quedan.
> **Sin instalaciones reales de las referencias:** se revisó documentación, notas de versión y
> comportamiento descrito. Lo no verificado va marcado como **NOT RUN**, no como ausencia.

## 1. Problema local (antes de mirar referencias)

- **Historia:** D1/D8/D10 y el flujo real de «Deseados»: añadir una serie ya catalogada, esperar el
  ciclo (Prowlarr + foro), buscar a mano cuando algo no aparece, elegir release entre los resultados
  y ver cómo se descarga e importa.
- **Casos reales (Pi, 2026-11-16):**
  - `DC K.O.` (evento DC): Prowlarr devolvía 101 resultados basura por el token «DC»; el foro tenía
    un tema con **27 enlaces `ed2k`**. La búsqueda del foro se saltaba por cortesía y el mensaje
    visible culpaba al foro aunque el descarte fuera de Prowlarr.
  - `Absolute Wonder Woman`: el mismo release aparecía **dos veces** (dos indexers), uno de los
    envíos funcionaba y el otro fallaba; además Transmission rechazaba por `download-dir` inválido.
  - `Sector Lejano`: un **tomo único que recopila las 12 grapas** de la miniserie; el nombre no trae
    número, acababa en `_Unsorted` y el deseo se quedaba «Descargando…» para siempre.
- **Comportamiento actual verificado en `origin/main`** (no en un checkout atrasado):
  - `services/orchestrator.py:402` `_search_and_rank`: Prowlarr y foro en paralelo, relevancia,
    filtro por número, filtro por backend, motivo de espera/descarte.
  - `:582` `preview_candidates` y `:603` `send_manual_candidate`: búsqueda manual sin tocar clientes
    hasta confirmar; token firmado por candidato (`crear_token_candidato`).
  - `web/wishlist.py:207` `buscar_ahora`, `:243` `enviar_candidato`, `:146` `marcar_conseguido`.
  - `web/pendientes.py:727` + `services/especiales.py:72`: alta de especial sin número (ADR 0016).
  - `services/series.py:530` `numeros_poseidos`: presencia por `File` enlazado; desde #966 también
    cuenta el rango declarado por un tomo.
- **Resultado deseado:** que el coleccionista vea qué se está buscando, reciba opciones claras y
  distintas, pueda enviar varias sin repetir la espera, entienda los fallos y pueda cerrar el deseo
  cuando el fichero ya esté (aunque haya acabado como especial).

## 2. Referencias revisadas

| Referencia | Versión / commit / fecha | Qué se revisó | Evidencia |
|---|---|---|---|
| **Sonarr** | `v4.0.20.3014`, commit `cab419ad`, 2026-09-16 | Wanted ⇒ Missing: lista de episodios que faltan, **Search Selected/Search All**, aviso con cuántos se van a buscar, y que **la búsqueda no se puede cancelar** sin reiniciar o desactivar indexers. Import manual/Interactive Import. | [wiki.servarr.com/sonarr/wanted](https://wiki.servarr.com/en/sonarr/wanted), [releases](https://github.com/Sonarr/Sonarr/releases/tag/v4.0.20.3014) |
| **Radarr** | `v7.0.3.10918`, commit `af772b0`, 2026-11-16 | Filtros de biblioteca **Missing/Wanted**, Search All/Filtered/Selected, import interactivo. En la nota de versión: «Fixed: Interactive search failing when a release couldn't be processed» y «New: Replace HTML Encoded values in release titles». | [wiki.servarr.com/radarr/library](https://wiki.servarr.com/en/radarr/library), [radarr/activity](https://wiki.servarr.com/en/radarr/activity), [release](https://github.com/Radarr/Radarr/releases/tag/v7.0.3.10918) |
| **Kapowarr** | `V1.3.2`, 2026-09-14 | «Search Monitored» para el backlog; **Manual Search** con lista de resultados, tamaño, botón rojo con motivo del rechazo y opción de **forzar**; descarga → post-proceso (renombrar, convertir, extraer); bloqueo del release que no vale; RSS cada 30 min para nuevos y búsqueda manual para antiguos. | [How To Use](https://casvt.github.io/Kapowarr/general_info/how_to_use/), [release V1.3.2](https://github.com/Casvt/Kapowarr/releases/tag/V1.3.2) |
| **Mylar3** | `v0.8.3`, 2025-08-17 | Wanted/Upcoming con **force queue de un subconjunto de issues**, selección múltiple con Shift, intervalo de búsqueda configurable, incidencias de numeración negativa y one-shots. Wiki: «Automatically Mark Upcoming Issues as Wanted» y proveedor de búsqueda obligatorio. | [release v0.8.3](https://github.com/mylar3/mylar3/releases/tag/v0.8.3), [wiki Tips and Tricks](https://github.com/mylar3/mylar3/wiki/Tips-and-Tricks), [wiki Torrents/DDL](https://github.com/mylar3/mylar3/wiki/Torrents,-Newsgroups-and-DDL) |
| **Suwayomi** | `v2.4.2366`, 2026-09-30 | Biblioteca, actualizaciones automáticas y descarga de capítulos nuevos; búsqueda/navegación por fuentes. No es una lista de «deseos» con elección de release: la unidad es manga/capítulo y la fuente manda. | [README](https://github.com/Suwayomi/Suwayomi-Server), [release](https://github.com/Suwayomi/Suwayomi-Server/releases/tag/v2.4.2366) |
| **htmx 4** (herramienta) | 4.0.0 | `hx-disable` (no `hx-disabled-elt`) para deshabilitar durante la petición; indicadores con `hx-indicator`; swaps OOB para conservar la lista de candidatos. | [guidance](https://github.com/bigskysoftware/htmx/blob/v4.0.0/src/skills/htmx-guidance.md) |

**NOT RUN / límites de esta ficha:**
- No se instaló ninguna referencia (Sonarr/Radarr/Kapowarr/Mylar3/Suwayomi) para pulsar su UI.
- El modal de búsqueda interactiva de Sonarr/Radarr no está descrito en las páginas de wiki revisadas:
  la evidencia es la nota de Radarr y un hilo de soporte; **no se verificó su comportamiento exacto**
  (qué se rechaza, qué se puede forzar).
- La UI de Wanted de Mylar3 no está documentada en las páginas revisadas; se usan sus notas de
  versión. No se infiere que no exista nada más.
- No se revisó el código fuente de ninguna referencia para esta ficha (solo docs/notas); la
  comparación de unidades se apoya en la documentación, no en el esquema real.

## 3. Identidad de datos: por qué no se trasplanta tal cual

| Referencia | Unidad | Fuente | Estados / decisión |
|---|---|---|---|
| Sonarr | serie/temporada/episodio (aired) | indexers (torrent/usenet) | monitored, quality profile, cut-off, cola del cliente |
| Radarr | película | indexers | monitored, disponibilidad mínima, quality profile, cut-off |
| Kapowarr | volumen + issue (ComicVine) | GetComics/indexers | monitored, special version (TPB/One Shot/Omnibus…), blocklist |
| Mylar3 | serie + issue (ComicVine) | proveedores de búsqueda (DDL/torrent/usenet) | wanted/upcoming, force queue, post-proceso |
| Suwayomi | manga + capítulo | extensión/fuente | biblioteca, actualizaciones, descarga |
| **ZascArr** | `Series` + `Issue` (`issue_number` VARCHAR, packs, especiales sin número), deseo de serie/número | **foro IPB (ed2k/magnet)** + **Prowlarr (torrent)** | `wishlist.status` + `last_error`; sin upgrades de calidad; ficheros CBR/CBZ y `_Unsorted` |

Consecuencias de diseño: no hay «quality profile» ni cut-off que justifiquen una lista de upgrades;
la unidad puede ser una grapa, un **tomo recopilatorio** o un **especial sin número**; y el foro
aporta muchos enlaces por tema, algo que las referencias (un episodio = un release elegido) no
modelan igual.

## 4. Matriz ponderada (nivel 2)

Pesos (1–3). Puntuación 0–3 por referencia; total ponderado sobre 69.

| Criterio | Peso | Sonarr | Radarr | Kapowarr | Mylar3 | Suwayomi | ZascArr (actual) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Búsqueda automática del backlog | 3 | 3 | 3 | 3 | 2 | 3 | 3 |
| Búsqueda manual y elección de release | 3 | 3 | 3 | 3 | 2 | 1 | 3 |
| Estados y motivo visible de por qué no avanza | 3 | 3 | 3 | 3 | 2 | 2 | 2 |
| Varios números/packs desde una misma búsqueda | 2 | 2 | 2 | 2 | 3 | 1 | 3 |
| Cola/progreso y recuperación de fallos | 2 | 3 | 3 | 3 | 2 | 2 | 1 |
| Ruido/duplicados en los resultados | 2 | 2 | 2 | 2 | 1 | 1 | 3 |
| UX/accesibilidad/móvil | 2 | 3 | 3 | 2 | 1 | 2 | 3 |
| Coste en la Pi / dependencias | 3 | 2 | 2 | 2 | 2 | 1 | 3 |
| Licencia y postura legal | 3 | 3 | 3 | 3 | 3 | 2 | 3 |
| **Total ponderado** | **23** | **62** | **62** | **60** | **47** | **39** | **62** |

Lectura: ZascArr ya **iguala** en lo que importa a este flujo (búsqueda, elección, estados, ruido,
UX y coste), y pierde sobre todo en **cola/progreso y recuperación de fallos** (punto 6). No es un
ranking para copiar: las referencias tienen unidades y fuentes distintas.

## 5. Decisiones por idea

| Idea / patrón | Referencia(s) | Decisión | En ZascArr |
|---|---|---|---|
| Lista de lo que falta separada de la biblioteca | Sonarr/Radarr (Wanted/Missing) | **Adoptar** | Deseados ya lo es; no se duplica «cut-off unmet» porque no hay upgrades. |
| Búsqueda manual con lista de releases y **confirmación explícita** | Sonarr/Radarr interactive; Kapowarr Manual Search | **Adoptar** | D10: `preview_candidates` + token firmado + `send_manual_candidate`; el deseo no se toca hasta confirmar. |
| Mostrar en cada resultado fuente, tamaño y seeders | Kapowarr (V1.3.2 añade tamaño) | **Adoptar** | `_candidatos_wishlist.html`: indexer, formato, tamaño o «tamaño desconocido», seeders si los hay. |
| **Motivo del rechazo** junto al release, con opción de forzar | Kapowarr (botón rojo + force) | **Adaptar** | Se descarta antes de listar (relevancia/número/backend) y se explica el motivo agregado (`MOTIVO_*`); **no se ofrece forzar** un enlace que no pasa la política legal/calidad. |
| Avisar de cuánto va a costar una búsqueda y qué se va a buscar | Sonarr (diálogo con nº de episodios) | **Adaptar** | «Buscar ahora» avisa de hasta 2 minutos y deshabilita el botón; no hay lote multi-ítem todavía. |
| Poder **cancelar** una búsqueda en curso | Sonarr (no se puede) | **Descartar** | No hay cancelación a mitad del POST; «Cerrar lista» solo cierra resultados ya recibidos. Se declara limitación. |
| RSS/cola para releases nuevos + búsqueda manual para el backlog | Kapowarr V1.3.2 | **Adoptar/Adaptar** | Ciclo automático + «Buscar ahora»; el foro no tiene RSS, así que la búsqueda manual es la vía del backlog. |
| Un tomo/pack que **cubre varios números** | Sonarr (packs de temporada; no verificado en Wanted) / Mylar (one-shots) | **Adaptar** | Especial sin número + `numeros_cubiertos` (1-12): cuenta como poseído y deja de ser hueco (#966). El detalle de la UI de packs de Sonarr queda **NOT RUN**; no se copia su contrato. |
| Encolar **varios** releases del mismo ítem desde una sola lista | Mylar (force queue de un subconjunto del Wanted), Sonarr (Search Selected) | **Mejorar** | #912: cada candidato se envía sin perder el resto; el mismo enlace no se repite. Evidencia del caso: 27 `ed2k` en un tema, una sola espera. Ninguna referencia revisada muestra esto para enlaces de un mismo tema. |
| Deduplicar el mismo release entre indexers | Sonarr/Radarr (no verificado el criterio exacto) | **Mejorar (propio)** | #969 (título normalizado + tamaño, se queda el de más seeders) y #957 (mismo `ed2k`/`btih` con distinta codificación). |
| Import manual/interactivo de lo que no casa | Sonarr/Radarr Manual Import; Kapowarr Manage Issues | **Adaptar** | «Por revisar» + asignar/vincular + especial; el matcher falla cerrado a `_Unsorted` y sugiere la serie cuando falta número (#961). |
| Cerrar el deseo cuando el fichero ya está, aunque no se enlace | — (no consta en referencias) | **Construir sobre lo propio** | «Ya lo tengo» (#967) para descargas manuales que acaban en `_Unsorted`/especial. |
| Bloqueo/blocklist automático de releases fallidos | Sonarr/Radarr blocklist; Kapowarr | **Descartar por ahora** | Se reintenta/descarta en cada búsqueda; no hay tabla de bloqueos. Se anota como hueco, no se copia la complejidad. |
| Upgrades de calidad / cut-off | Sonarr/Radarr | **Descartar** | Fuera de producto: el deseo es tener el número, no mejorar la edición. |
| Reemplazar valores HTML en títulos de release | Radarr (nota v7.0.3: «Replace HTML Encoded values in release titles») | **Adoptar** | #903 desescapa entidades de los títulos del foro; misma lección que Radarr, sin copiar código. |
| Manejo de límites de los indexers con espera visible | Kapowarr V1.3.2 (búsqueda «más lista» con rate limits), Sonarr (avisos) | **Adaptar** | Cortesía compartida + `CortesiaEnEspera`; #911 separa «espera» de «no hay nada»; #898 corrige el presupuesto del foro. |
| «Probar conexión» del cliente de descarga | **arr** (test de cliente) | **Adoptar** | Ajustes ya prueba Transmission/aMule; el caso real destapó que valida sesión pero no la carpeta: se añadió fallback y log (`#970`). Queda pendiente avisar de la carpeta inválida al probar. |

## 6. IGUALAR (mínimo competitivo) y MEJORAR (con evidencia)

**IGUALAR** (condición para considerarlo completo):
1. Lista de resultados por ítem con fuente, formato, tamaño y seeders, y envío **solo tras confirmar**.
2. Estado por deseo con un motivo concreto (no solo «sin resultados»), y acciones Reintentar/Buscar/Quitar.
3. Varias descargas sin perder la lista y sin repetir el mismo enlace.
4. Deduplicación de releases repetidos entre indexers y del mismo enlace del foro.
5. Móvil/teclado: botones con nombre accesible, `aria-live` en resultados y en la espera.

**MEJORAR** (hueco probado, no opinión):
1. **Foro + Prowlarr en una sola lista con procedencia**: ninguna referencia revisada mezcla foro
   `ed2k` y torrents en el mismo «Buscar ahora»; el caso DC K.O. lo exige. Criterio: los 27 enlaces
   del tema salen con nombre de fichero distinto y se pueden enviar varios.
2. **Tomo que cubre 1-12 grapas**: no consta en la documentación revisada que Wanted/Manual Search
   cierre huecos por un tomo; Sonarr tiene packs de temporada, cuyo detalle en la lista de Wanted no
   se verificó. Criterio: tras guardar el tomo, los 12 números dejan de aparecer como huecos.
3. **Cerrar un deseo cuando la descarga existe pero quedó sin enlace**: las referencias lo resuelven
   con Manual Import/Manage Issues, no desde el propio Wanted. Criterio: «Ya lo tengo» deja el deseo
   en «En tu biblioteca» sin volver a buscar.

**Huecos declarados (no implementados, no se finge que sí):**
- Vista única de **cola/progreso** de descargas — **cerrado** en #973 (panel «Descargas en curso»).
- Cancelar una búsqueda a mitad de petición — **cerrado** en #983 (aborta la espera del navegador; el servidor puede terminar la petición ya lanzada).
- Buscar en lote varios deseos seleccionados — **cerrado** en #983 (máx. 8 por tanda).
- Aviso de carpeta de descargas distinta al probar la conexión — **cerrado** en #984 (aviso con las dos rutas; queda pendiente comprobar la existencia real en el host, imposible desde el contenedor).
- Reintento automático/backoff tras un fallo de envío — **cerrado** en #985 (10 min → 30 min → 2 h → 6 h; «Reintentar» lo salta; el envío extra auxiliar no programa backoff).

## 7. Coste en la Pi y licencias

- Sonarr/Radarr (.NET) y Suwayomi (JVM) son pesados para la restricción de 512 MiB; Kapowarr
  (Python + web) es el más cercano en coste; Mylar3 es legado con búsqueda por proveedores.
  ZascArr ya usa foro + Prowlarr + clientes externos con un solo worker: **no se añade dependencia
  nueva** por este benchmark.
- Licencias: Sonarr/Radarr/Kapowarr/Mylar3 **GPL-3.0**; Suwayomi **MPL-2.0**. Aquí solo se copian
  **patrones de UX/contrato**, nunca código; cualquier reutilización futura exige revisar el fichero
  y sus obligaciones.

## 8. Criterios de aceptación que salen de esta ficha

- AC-B1: un candidato del foro muestra **nombre de fichero** (no el título del tema repetido) y su
  tamaño cuando el enlace lo declara (#945, #957).
- AC-B2: dos enlaces del mismo fichero (codificación distinta) o el mismo release en dos indexers
  aparecen **una sola vez** (#957, #969).
- AC-B3: se pueden enviar **varios** candidatos sin perder el resto y el mismo enlace no se repite
  (#912).
- AC-B4: si el foro espera y Prowlarr se descartó, el motivo lo dice, no culpa solo al foro (#911).
- AC-B5: un fichero sin número con serie reconocida ofrece **sugerencia** y se puede guardar como
  especial en `…/Serie (Año)/Especiales/` (#961, #964), declarando los números que cubre (#966).
- AC-B6: un deseo cuya descarga quedó sin enlace se puede cerrar con «Ya lo tengo» (#967).
- AC-B7: la búsqueda manual avisa de la espera, deshabilita el botón y no se puede disparar dos veces
  (pasada UI/UX #971).

## 9. Pruebas / evidencia

- `tests/test_orchestrator.py` (relevancia, motivos, dedupe Prowlarr, títulos de enlaces del foro,
  envío extra y no-repetición), `tests/test_web_wishlist.py` (parciales, aria, resumen, descarga
  múltiple, «Ya lo tengo»), `tests/test_especial_sin_numero_pg.py` y `tests/test_especiales_rango.py`
  (especiales y `numeros_cubiertos`), `tests/test_matcher_sin_numero.py` (sugerencia), suites de CSS
  y accesibilidad.
- Casos reales verificados en la Pi: DC K.O. (27 `ed2k`), Sector Lejano (tomo 1-12), Absolute Wonder
  Woman (duplicado y fallo de Transmission). Evidencia en `docs/BACKLOG.md` y en los PR citados.

## 10. Referencias (consultadas 2026-11-16)

- Sonarr Wanted: https://wiki.servarr.com/en/sonarr/wanted · release v4.0.20.3014:
  https://github.com/Sonarr/Sonarr/releases/tag/v4.0.20.3014
- Radarr Library: https://wiki.servarr.com/en/radarr/library · Activity:
  https://wiki.servarr.com/en/radarr/activity · release v7.0.3.10918:
  https://github.com/Radarr/Radarr/releases/tag/v7.0.3.10918
- Kapowarr How To Use: https://casvt.github.io/Kapowarr/general_info/how_to_use/ · release V1.3.2:
  https://github.com/Casvt/Kapowarr/releases/tag/V1.3.2
- Mylar3 release v0.8.3: https://github.com/mylar3/mylar3/releases/tag/v0.8.3 · wiki Tips:
  https://github.com/mylar3/mylar3/wiki/Tips-and-Tricks · Torrents/DDL:
  https://github.com/mylar3/mylar3/wiki/Torrents,-Newsgroups-and-DDL
- Suwayomi: https://github.com/Suwayomi/Suwayomi-Server · release v2.4.2366:
  https://github.com/Suwayomi/Suwayomi-Server/releases/tag/v2.4.2366
- htmx 4 guidance: https://github.com/bigskysoftware/htmx/blob/v4.0.0/src/skills/htmx-guidance.md
