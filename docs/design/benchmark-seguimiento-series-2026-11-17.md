# Benchmark — «Seguir una serie»: nuevo número disponible → descarga y aviso

> **Nivel 2 de §13** (toca el ciclo de búsqueda/descarga, notificaciones y probablemente el
> modelo de datos). **Fecha:** 2026-11-17. **Caducidad:** 2027-01-15 o antes si cambia una
> referencia o la historia. **Estado:** ficha previa a especificar; **no implementa nada**.
> **Sin instalaciones reales de las referencias:** se revisó documentación y notas de versión;
> lo no verificado va como **NOT RUN**, no como ausencia.

## 1. Problema local

El coleccionista quiere **seguir una serie** y que ZascArr, como Sonarr con los capítulos de
una serie de TV:

1. detecte el **número nuevo** cuando se publica;
2. lo **busque y descargue** por su cuenta con las fuentes ya configuradas (Prowlarr/foro);
3. le **avise** de que hay un número nuevo (o de que ya se ha descargado/importado);
4. no duplique ni insista si ya lo tiene, si falla la fuente o si el número aún no ha salido.

Hoy ZascArr tiene tres piezas cercanas, pero **ninguna las une**:

- **Deseados** (`wishlist`): busca lo que se le pide a mano y lo que genera la política
  (`WishlistPolicy.MISSING`). La opción **«Números que aún no han salido» existe pero está
  deshabilitada**: `WishlistPolicy.FUTURE` está reservada y `querer_de_serie` devuelve
  «no computable» (`services/politica.py:40,137`; selector en `_politica_serie.html`). El motivo
  original —«haría falta que la fuente publique los números que aún no han salido»— quedó
  **desactualizado** cuando se añadió **Novedades (D5)**.
- **Novedades (D5)** (`services/novedades.py`): consulta Comic Vine por `cover_date` y las
  novedades de Norma/Panini, y las cruza con las series seguidas (deseos activos o política
  distinta de «ninguno»), marcando `interes` y `publicado`. Es **solo lectura**: no crea
  deseos, no busca y no avisa.
- **Avisos** (`services/notifier.py`): webhook de mejor esfuerzo para `generic`, `gotify`,
  `ntfy` y `telegram`; hoy solo `notify_imported()` (cuando el importador deja ficheros), y se
  llama después del commit desde `ciclo_importador.py`.

**Resultado deseado:** una opción por serie, independiente de «completar huecos», que active el
seguimiento de novedades y enlace con el ciclo de búsqueda y el notificador existentes.

## 2. Estado actual verificado (origin/main, 2026-11-17)

| Pieza | Comportamiento real | Evidencia |
|---|---|---|
| Política de búsqueda | `NONE`/`MISSING`; `FUTURE` y `ALL` reservadas. `FUTURE` devuelve «no computable» y el selector la muestra **deshabilitada**. | `models/__init__.py:200-208`, `services/politica.py:40,120-160`, `web/series.py:483` |
| Generación de deseos | `_generar_lo_que_falta` materializa números de `MISSING` (huecos) y `ALL` (1..total); no hay generación por fecha de publicación. | `services/orchestrator.py:1187` |
| Novedades | `cargar_semana` pide Comic Vine por `cover_date` (semana) + Norma/Panini; `construir_semana` cruza por `comic_vine_id` o título y marca `interes` (`wishlist`/política) y `publicado` (`fecha <= hoy`); caché 30 min. | `services/novedades.py` (`_items_de_la_semana`, `construir_semana`), `web/novedades.py` |
| Fechas de número | Comic Vine expone `cover_date` y `store_date`; `get_issue` pide ambos. Novedades usa **cover_date** y define publicado por ella. | `services/comic_vine.py:201-235`, `services/novedades.py` |
| Avisos | Webhook `generic/gotify/ntfy/telegram`; `webhook_enabled` global; `notify_imported(files)` tras commit; sin aviso de «número nuevo detectado» ni de «descarga lanzada»; los nombres solo si `webhook_incluir_nombres`. | `services/notifier.py`, `services/ciclo_importador.py`, `web/ajustes.py` (tarjeta Avisos) |
| Lo que NO existe | Seguimiento por serie independiente de la política, generación de deseo al publicarse un número, aviso de novedad y criterio de «fecha de disponibilidad real». | verificado en `origin/main`; no hay rutas/columnas |

## 3. Referencias revisadas

| Referencia | Versión / commit / fecha | Qué se revisó | Evidencia |
|---|---|---|---|
| **Sonarr** | `v4.0.20.3014`, commit `cab419ad`, 2026-09-16 | Series monitorizadas; **RSS Sync** en segundo plano (no búsqueda activa del pasado): consulta releases nuevos y los cruza con episodios monitorizados; ventana de «recent episodes» de 14 días; episodios sin `airdate` se saltan; monitorización al añadir (All/Future/Missing/…); Calendar con iCal (±7/28 días); Wanted/Missing con Search Selected/All. | [FAQ](https://wiki.servarr.com/en/sonarr/faq), [Library](https://wiki.servarr.com/en/sonarr/library), [Wanted](https://wiki.servarr.com/en/sonarr/wanted), [Calendar](https://wiki.servarr.com/en/sonarr/calendar), [release](https://github.com/Sonarr/Sonarr/releases/tag/v4.0.20.3014) |
| **Radarr** | `v7.0.3.10918`, commit `af772b0`, 2026-11-16 | Mismo patrón *arr: biblioteca monitorizada, filtros Missing/Wanted, cola y notificaciones; eventos de aviso por release/import/upgrade/health. | [Library](https://wiki.servarr.com/en/radarr/library), [Activity](https://wiki.servarr.com/en/radarr/activity), [release](https://github.com/Radarr/Radarr/releases/tag/v7.0.3.10918) |
| **Sonarr/Radarr — Connect** | API de notificaciones | El recurso de notificación expone eventos por tipo: `on_grab`, `on_download`, `on_upgrade`, `on_import_complete`, `on_rename`, `on_series_add`, salud, actualización, intervención manual; implementaciones por proveedor (webhook, correo, etc.). | [NotificationResource (sonarr-py)](https://github.com/devopsarr/sonarr-py/blob/main/docs/NotificationResource.md) |
| **Mylar3** | `v0.8.3`, 2025-08-17 | **Watchlist de series monitorizadas para nuevos números**, pull-lists semanales (hasta 4 semanas), TPB/GN monitorizables, «failed download handling» (descarga otra si falla), **notificaciones de snatch/descarga** con varias apps; Wanted con force queue de un subconjunto. | [README](https://github.com/mylar3/mylar3/blob/master/README.md), [release v0.8.3](https://github.com/mylar3/mylar3/releases/tag/v0.8.3), [Pushbullet issue](https://github.com/mylar3/mylar3/issues/292) |
| **Kapowarr** | `V1.3.2`, 2026-09-14 | Issues monitorizados por volumen; **Search Monitored** para backlog; desde V1.3.2 un sistema **RSS(-like) cada 30 min** para releases nuevos y búsqueda manual para lo antiguo (explícitamente «como Sonarr con episodios antiguos»); Manual Search con tamaño/motivo/forzar; post-proceso. En la documentación revisada **no consta** sección de notificaciones. | [How To Use](https://casvt.github.io/Kapowarr/general_info/how_to_use/), [release V1.3.2](https://github.com/Casvt/Kapowarr/releases/tag/V1.3.2), [FAQ](https://casvt.github.io/Kapowarr/other_docs/faq/) |
| **Suwayomi** | `v2.4.2366` (servidor) / WebUI `v20260929.01`, 2026-09-30 | Biblioteca y actualizaciones de capítulos; cola de descargas; opción de **descargar automáticamente los capítulos siguientes** mientras se lee; selección múltiple; no se encontró un sistema de suscripción por serie con aviso al publicarse (no se infiere ausencia). | [Server README](https://github.com/Suwayomi/Suwayomi-Server), [WebUI README](https://github.com/Suwayomi/Suwayomi-WebUI), [release](https://github.com/Suwayomi/Suwayomi-Server/releases/tag/v2.4.2366) |

**NOT RUN / límites:**
- No se instaló ni se pulsó la UI de ninguna referencia.
- No se verificó en vivo el payload exacto de Connect ni los eventos que soporta cada proveedor.
- No se verificó la ventana/intervalo real de RSS Sync en Sonarr (el FAQ da 10–144 consultas/día,
  es decir, 10–120 min); se cita el contrato descrito, no una medición propia.
- Para Kapowarr/Mylar3 no se revisó el código; se usan README/notas de versión.
- **No se probó Comic Vine con datos futuros ni la fiabilidad de `store_date`** para este caso.

## 4. Identidad de datos: la diferencia que decide el diseño

| Referencia | Unidad de seguimiento | Señal de disponibilidad | Aviso |
|---|---|---|---|
| Sonarr | serie/ temporada / episodio | `airdate` de TVDB | Connect: grab/import/upgrade… |
| Radarr | película | fecha de estreno / disponibilidad mínima | Connect |
| Mylar3 | serie + issue (ComicVine) | fecha de portada/venta del issue y pull-list | snatch/descarga |
| Kapowarr | volumen + issue (ComicVine) | RSS de releases nuevos + búsqueda del backlog | no consta |
| Suwayomi | manga + capítulo | fuente/actualización de capítulos | no consta (sin suscripción por serie) |
| **ZascArr** | `Series` + `Issue` (`issue_number` VARCHAR; especiales; tomos) | `Issue.release_date` (fecha de venta, decisión PO 2026-11-13) y Novedades por `cover_date` | webhook de importación (4 tipos) |

Dos consecuencias:

1. **«Publicado» no es lo mismo que «disponible»**: `cover_date` de Comic Vine es la fecha de
   portada (a menudo posterior a la venta); `store_date` es la de venta y suele faltar en
   futuros. Novedades ya marcó `publicado = cover_date <= hoy`, pero para descargar «cuando
   esté disponible» hay que decidir la señal (store_date si existe → cover_date como respaldo)
   y probar cuántos futuros traen store_date.
2. **La unidad de ZascArr no es un episodio**: un número puede ser un especial, un tomo con
   rango cubierto (#966) o un anual; el seguimiento debe generar **solo números de grapa
   identificables** y no duplicar los ya poseídos (fichero o deseo).

## 5. Matriz ponderada (nivel 2)

Pesos 1–3; máximo 72.

| Criterio | Peso | Sonarr | Radarr | Mylar3 | Kapowarr | Suwayomi | ZascArr actual |
|---|---:|---:|---:|---:|---:|---:|---:|
| Descubrir lanzamientos nuevos | 3 | 3 | 3 | 3 | 3 | 3 | 2 |
| Seguimiento por serie (monitor) | 3 | 3 | 3 | 3 | 3 | 2 | 2 |
| Auto-descarga al estar disponible | 3 | 3 | 3 | 3 | 3 | 3 | 1 |
| Avisos (eventos y canales) | 3 | 3 | 3 | 2 | 1 | 1 | 3 |
| Encaje con fuentes españolas/Comic Vine | 2 | 1 | 1 | 3 | 3 | 1 | 3 |
| Dedupe/control de lo ya poseído | 2 | 3 | 3 | 2 | 2 | 1 | 2 |
| Coste en la Pi / cuotas | 3 | 2 | 2 | 1 | 2 | 1 | 3 |
| UX y control humano | 2 | 3 | 3 | 1 | 3 | 2 | 3 |
| Legal / postura del producto | 3 | 3 | 3 | 3 | 3 | 2 | 3 |
| **Total ponderado** | **24** | **65** | **65** | **57** | **61** | **44** | **58** |

Lectura: ZascArr ya tiene **el aviso y las fuentes**, y Novedades hace el descubrimiento semanal;
pierde en lo que pide la historia: **seguimiento y auto-descarga**. No hay que construir un
Sonarr: hay que cerrar ese hueco con las piezas propias.

## 6. Decisiones por idea

| Idea / patrón | Referencia(s) | Decisión | Cómo encaja en ZascArr |
|---|---|---|---|
| Monitorizar una serie y buscar solo lo nuevo, sin re-buscar el pasado en cada ciclo | Sonarr (RSS Sync, FAQ) | **Adoptar** | Un job de novedades (semanal/diario) genera deseos para lo recién publicado; el ciclo de Deseados ya busca y descarga. |
| Separar «completar lo que falta» de «seguir lo nuevo» | Sonarr (monitor All/Future/Missing), Mylar (watchlist) | **Adoptar** | No reutilizar `WishlistPolicy` para dos cosas: la política actual = huecos; el seguimiento es un **flag por serie** (`follow_new_issues`) con su propio aviso. Alternativa: activar `FUTURE`, pero impide «faltantes + futuros» a la vez; se descarta para v1. |
| Avisar en eventos distintos (detectado / enviado / importado) | Sonarr/Radarr Connect | **Adaptar** | Reutilizar `Notifier` y su `webhook_enabled` para un evento «número nuevo»; el aviso de importación ya existe. Sin proveedores nuevos. |
| Descubrir números nuevos por una fuente de calendario | Sonarr Calendar, Mylar pull-list | **Adaptar** | `novedades.cargar_semana` (Comic Vine + Norma/Panini) ya cruza por `comic_vine_id`/título y marca `interes`; hay que añadir «seguimiento» a `interes` y usar `publicado`/fecha de venta. |
| Marcar lo ya poseído y no duplicar | Sonarr/Mylar | **Adoptar** | Antes de crear el deseo: comprobar `Files` por número y `Wishlist` existente; usar el índice único parcial de política solo si se elige origen política. |
| Backlog histórico (buscar todo lo antiguo al añadir) | Sonarr (no lo hace por RSS; sí Search All), Kapowarr (Search Monitored) | **Descartar/Adaptar** | Lo antiguo sigue con «completar» (MISSING) y «Buscar ahora»; el seguimiento cubre solo lo nuevo. |
| Upgrades de calidad / cut-off | Sonarr/Radarr | **Descartar** | Fuera de producto: se quiere tener el número, no mejorar la edición. |
| Notificaciones rich por proveedor (Discord/Telegram/…) | Sonarr Connect | **Construir sobre lo propio** | Ya hay generic/gotify/ntfy/telegram con mejor esfuerzo; ampliar catálogo no es requisito. |
| Pull-list semanal con acción manual | Mylar3 | **Construir sobre lo propio** | Novedades ya muestra «Te interesa»; se puede añadir un botón «Seguir esta serie» junto a la novedad. |
| Autodescarga de capítulos al leer | Suwayomi | **Descartar** | Unidad y fuente distintas; no aporta al caso de series. |

## 7. Opciones de implementación y recomendación

### Opción A (recomendada): flag `follow_new_issues` + generador desde Novedades

- Migración: `series.follow_new_issues BOOLEAN NOT NULL DEFAULT false` (y un `WishlistOrigin`
  nuevo si se quiere retirar en bloque; ver abajo). UI en la ficha: «Seguir esta serie» (con la
  explicación de que avisará y buscará los números nuevos; no sustituye a «completar»).
- `interes` de Novedades incluye también `follow_new_issues`, además de deseo/política.
- Nuevo job periódico (`seguimiento`, p. ej. 1 vez/día, reutilizando `cargar_semana` con su
  caché) → para cada novedad **publicada**, `interes`, con `series_id` y número de grapa:
  - si ya hay `File` para ese número o deseo vivo → nada;
  - si no, crear deseo (`origen=SEGUIMIENTO` ideal; `MANUAL` como v1 si se evita migración de
    enum), `numero=N`, y **no** marcarlo como política de huecos;
  - el ciclo normal de `process_wishlist` lo busca con Prowlarr/foro.
- Aviso: nuevo `Notifier.notify_novedad(serie, numero, estado)` tras crear el deseo (o al
  importar). Mensaje llano, sin nombres salvo `webhook_incluir_nombres`; enlace a la serie.
- «Dejar de seguir»: deja de generar; los deseos pendientes se pueden retirar a mano (o por
  origen SEGUIMIENTO en una segunda pasada).

**Ventajas:** mantiene la política D8 intacta (una serie puede «completar huecos» y «seguir
nuevos» a la vez); no hay que tocar `querer_de_serie`; el aviso y el ciclo se reutilizan.
**Coste:** una migración pequeña + job + UI + notificador; la fecha de disponibilidad sigue
siendo la incógnita (punto 4).

### Opción B (mínima, sin migración): activar `WishlistPolicy.FUTURE`

- `querer_de_serie` para FUTURE dejaría de devolver «no computable»; un job de novedades
  materializa items de política solo para lo publicado; `_retirar...` tendría que dejar de
  retirar los items de seguimiento de una serie FUTURE (o `querer` devolver los ya generados).
- Sin columna nueva; el selector ya existe (hoy deshabilitado).
- **Problema:** una serie no puede «completar huecos» y «seguir nuevos» a la vez; la política es
  una sola opción. Para v1 podría aceptarse, pero es peor encaje con el coleccionista.

### Opción C (solo manual): Novedades con botón «Buscar este número»

- Sin job ni aviso automático; el usuario ve la novedad y pulsa. No cumple «que me lo descargue
  cuando esté disponible».

**Recomendación:** Opción A. Se puede trocear: (1) flag + UI + descubrimiento + deseo a mano
del ciclo; (2) aviso; (3) fecha de venta fiable y prueba con datos reales.

## 8. Diseño de datos y contratos (para la especificación)

- `Series.follow_new_issues` (bool). Independiente de `wishlist_policy`.
- `WishlistOrigin.SEGUIMIENTO` (enum; migración) **recomendado** para poder retirar en bloque y
  distinguirlo en la UI. Si se evita en v1: `origen=MANUAL` y documentarlo como deuda.
- `Notifier.notify_novedad(serie, numero, url_serie)` reutilizando `enviar()`; sin reintentos
  (mejor esfuerzo). `webhook_enabled` global; opcional futuro `webhook_eventos` (no necesario).
- Fecha de disponibilidad: usar `store_date` si existe; si no, `cover_date`; documentar el
  desfase y probarlo con una muestra real (NOT RUN hoy). Posible consulta adicional a Comic
  Vine por `store_date` si el filtro existe.
- Dedupe: número ya con `File` (no `is_missing`) o deseo vivo → no crear. Especiales/anuales/
  tomos: no generar salvo que el nombre sea una grapa inequívoca.
- Límites: por ciclo, como `orchestrator_politica_lote`/cupo por hora; no inundar Prowlarr/foro
  con una semana de 100 novedades (solo series seguidas e «interes»).

## 9. Aceptación propuesta (semilla, no cerrada)

- AC-1: ficha de serie con «Seguir esta serie» (on/off), independiente de «Qué buscar».
- AC-2: con seguimiento activo y una novedad publicada de esa serie en Novedades, el siguiente
  ciclo crea **un** deseo para ese número (una vez), sin tocar los ya poseídos.
- AC-3: el deseo se busca con Prowlarr/foro; si falla, el motivo por cliente (ya existente) y
  el backoff (#985) se aplican.
- AC-4: se envía un aviso por el webhook existente (si está activo) al detectar/importar el
  número; mensaje en llano, sin nombres salvo la opción ya existente.
- AC-5: «dejar de seguir» detiene la generación; no borra la biblioteca; los deseos pendientes
  se pueden retirar.
- AC-6: no se generan deseos para números ya poseídos, especiales/tomos sin número de grapa ni
  para series con seguimiento apagado.
- AC-7: coste: una consulta de Novedades al día (caché 30 min ya existente) y el ciclo actual;
  sin dependencias nuevas.

## 10. Riesgos / preguntas abiertas

1. **`store_date` vs `cover_date`**: es la decisión más importante; sin ella se avisará tarde
   (portada) o nunca (si no hay fecha). Necesita muestra real de Comic Vine.
2. Cobertura de **Norma/Panini**: `novedades_es` ya los trae, pero su fecha puede no ser la de
   venta; revisar el HTML de origen.
3. Series sin `comic_vine_id`: el cruce por título puede fallar; el seguimiento debe fallar
   cerrado y no crear deseos dudosos.
4. Especiales/anuales: no son grapas; el matcher actual ya los distingue, pero el generador
   debe ser conservador.
5. Cuotas/foro: no buscar en lote todos los números de una semana; el cupo por hora y el lote
   de política ya existen, reutilizarlos.

## 11. Referencias (consultadas 2026-11-17)

- Sonarr FAQ: https://wiki.servarr.com/en/sonarr/faq · Library:
  https://wiki.servarr.com/en/sonarr/library · Wanted: https://wiki.servarr.com/en/sonarr/wanted ·
  Calendar: https://wiki.servarr.com/en/sonarr/calendar · release v4.0.20.3014:
  https://github.com/Sonarr/Sonarr/releases/tag/v4.0.20.3014
- Notificaciones *arr (recurso): https://github.com/devopsarr/sonarr-py/blob/main/docs/NotificationResource.md
- Radarr Library: https://wiki.servarr.com/en/radarr/library · Activity:
  https://wiki.servarr.com/en/radarr/activity · release v7.0.3.10918:
  https://github.com/Radarr/Radarr/releases/tag/v7.0.3.10918
- Mylar3 README: https://github.com/mylar3/mylar3/blob/master/README.md · release v0.8.3:
  https://github.com/mylar3/mylar3/releases/tag/v0.8.3 · Pushbullet issue:
  https://github.com/mylar3/mylar3/issues/292
- Kapowarr How To Use: https://casvt.github.io/Kapowarr/general_info/how_to_use/ · FAQ:
  https://casvt.github.io/Kapowarr/other_docs/faq/ · release V1.3.2:
  https://github.com/Casvt/Kapowarr/releases/tag/V1.3.2
- Suwayomi Server README: https://github.com/Suwayomi/Suwayomi-Server · WebUI README:
  https://github.com/Suwayomi/Suwayomi-WebUI · release v2.4.2366:
  https://github.com/Suwayomi/Suwayomi-Server/releases/tag/v2.4.2366


## 12. Addendum (2026-11-17): la señal es la FUENTE, no la fecha de papel

**Corrección del PO:** «las novedades son publicaciones en papel, no novedades en las fuentes de
descarga». Tiene razón: una fecha de portada/venta no dice cuándo hay un `ed2k`/torrent
disponible. El símil correcto no es el calendario de TVDB, es el **RSS Sync de Sonarr**: Sonarr
consulta los **releases que publican los indexers** y los cruza con los episodios monitorizados;
no espera a la parrilla. ZascArr debe hacer lo mismo con sus fuentes:

- **Foro**: el subforo **E-links diarios** (`index.php?showforum=5`) es el feed real de lo que se
  publica cada día. Requiere sesión (sin login devuelve «no tienes permiso»; el `lofiversion` no
  sirve para f-5 sin autenticar). Autenticado, el scraper ya puede `_get`/`_pedir` y abrir temas;
  falta un parser de **listado de foro** (título, id, última actividad) y decidir qué es «nuevo»:
  tema nuevo del día o **tema actualizado** con enlaces añadidos.
- **Prowlarr**: releases recientes (RSS/API) cruzados con las series seguidas; el cliente actual
  busca por consulta, así que hay que comprobar si Prowlarr expone RSS por indexer o hacer una
  consulta periódica por serie (con presupuesto).
- **Novedades (Comic Vine + Norma/Panini)** deja de ser el disparador y pasa a ser
  **calendario/anticipación y pista de matching**: sirve para saber qué esperar y para cruzar
  títulos, pero **no** para decidir que se puede descargar.

### Diseño revisado (sigue siendo Opción A: flag independiente)

1. `Series.follow_new_issues` (flag) + UI «Seguir esta serie», independiente de «completar huecos».
2. Job `seguimiento` cada 30–60 min (no cada 5: la cortesía del foro manda):
   - **Foro**: leer `showforum=5` autenticado; por cada tema nuevo o actualizado desde la última
     pasada, abrir y extraer `ed2k`/`magnet` (reutilizar `_enlaces_del_tema`); casar el **nombre del
     fichero** con las series seguidas (el título del tema diario no basta; los enlaces sí llevan
     serie y número). Descartar lo ya poseído/deseado.
   - **Prowlarr**: releases nuevos; mismo cruce.
   - **Novedades**: solo se consulta como calendario; no genera deseos por sí sola.
3. Estado de «visto»: hace falta persistir qué temas/última actividad y qué enlaces se procesaron
   (tabla `seguimiento_visto` o marca equivalente; migración) para no reabrir los mismos temas ni
   duplicar deseos. El `Wishlist` y el `File` cubren el dedupe de contenido, pero no el de la fuente.
4. Aviso: `Notifier` (webhook existente) con evento «número nuevo detectado» y/o «importado».
5. Dejar de seguir: deja de escanear fuentes para esa serie; los deseos pendientes se retiran a mano
   (o por origen `SEGUIMIENTO` en una segunda pasada).

### Riesgos nuevos (además de los de §10)

- **Login del foro y cortesía**: cada lectura cuenta para la cola compartida; escanear solo temas
  nuevos/actualizados, con tope por pasada, y no usar la búsqueda (25 s) para esto.
- **Temas actualizados, no solo nuevos**: el hilo diario se edita/añade; hay que mirar la última
  actividad del tema, no solo su creación.
- **Nombre del fichero ≠ nombre del tema**: el match debe hacerse por los `ed2k`/título del fichero
  (ya lo hace `_forum_fallback`), no por el título del hilo.
- **Prowlarr sin RSS claro**: verificar endpoints; si no, consulta periódica por serie acotada.
- **Falsos positivos**: sin número de grapa inequívoco no se crea deseo (especiales/tomos).

### Impacto en la recomendación

La **Opción A** sigue siendo la elegida, pero el generador de deseos **no** sale de
`cargar_semana` (papel): sale de un adaptador de **fuentes** (foro E-links diarios + Prowlarr),
con Novedades como calendario. Esto añade un parser de listado de foro, estado «visto» y un
pequeño adaptador de Prowlarr; no cambia el flag ni el notificador.

### Ratificación O-1 (2026-11-17): el foro sigue sin consultar `robots.txt`

El PO **ratifica la postura actual** para cerrar la deuda #1017: la integración del foro es
**opt-in** (apagada por defecto, URL y credenciales del operador, aviso legal y acuse) y **no**
consulta `robots.txt`, tal como ya declaraba M4 (`FUENTES_CON_ROBOTS` no incluye `foro`). El
benchmark deja constancia del `Disallow: /` observado y de que la decisión es consciente; no se
añade una consulta de robots ni un aviso nuevo, y esta ratificación cubre el scraping periódico
del job, no solo la búsqueda manual. Si en el futuro se decide lo contrario, `foro` debe entrar en
el mapa de robots y el job debe tratar `AccesoProhibidoPorRobots` como parada, no como error.
