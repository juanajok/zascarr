# Benchmark — features de coleccionista en Metron y otras referencias

> **Ficha de benchmarking (exploración de nivel 2 por alcance)** según
> [`benchmark-referencias.md`](benchmark-referencias.md) (CLAUDE.md §13).
> **Pregunta del PO (2026-11-09):** no integrar Metron como fuente; estudiar qué
> funciones de cara al coleccionista tienen Metron y otros trackers de cómics que
> ZascArr no tenga, para copiar **ideas y patrones**, no datos ni código.
> **Persona:** «El Coleccionista» — no técnico, no abre terminales ni JSON; Raspberry Pi
> 4/5 compartida; sin SPA, sin Redis; presupuesto de 512 MB de RAM.
> **Base contrastada de ZascArr:** `origin/main` `0694b28` (2026-11-09).
> **Referencias:** Metron (`Metron-Project/metron` `c6e1c48`, 2026-11-07, API v1.12),
> League of Comic Geeks, CLZ Comics, Whakoom y ComicBookRealm, en las fechas y con las
> limitaciones que se indican en «Fuentes».
> **Método:** lectura de documentación pública, código de Metron y plantillas/rutas de
> ZascArr. **No** se ha llamado a la API de Metron, **no** se ha descargado su base, **no**
> se ha abierto su interfaz (está tras Anubis), **no** se ha ejecutado ZascArr y **no** se
> han tocado ficheros reales. Lo que no se pudo abrir va marcado **`[sin verificar]`**.
> **Autor:** SCOUT.bench. **Esto es insumo, no aprobación:** decide el PO.

---

## 0. Respuesta para el PO

1. **Metron no se integra como fuente.** La puerta ya está cerrada en
   [`benchmark-fuentes-metadatos-referencias.md`](benchmark-fuentes-metadatos-referencias.md):
   su API es excelente, pero solo cubre series en **inglés e italiano**, exige cuenta/token
   y sus datos son **CC BY-SA 4.0**; para la edición española no resuelve el problema. Aquí
   solo se estudian sus **funciones de coleccionista**, leyendo su API y su código.
2. **Lo que Metron hace bien y ZascArr no tiene** es, sobre todo, el **seguimiento de
   lectura**: marcar leído, varias fechas de lectura, valoración de 1 a 5, historial y
   estadísticas de lectura. ZascArr ya tiene las tablas `reading_progress` y
   `reading_lists`, pero **no las expone en ninguna ruta ni pantalla**.
3. **Lo que ZascArr ya cubre bien** —y no hay que copiar— es la **wishlist** (estados,
   prioridad, notas, búsqueda, política por serie), las **etiquetas** con filtros
   booleanos y el **«qué me falta»** por serie, con una honestidad que Metron no necesita:
   si no hay recuento acreditado, ZascArr dice «no sé», no inventa huecos.
4. **Lo que no encaja** en ZascArr: la ficha física de Metron/CLZ/Whakoom (grado, precio,
   tienda, caja, valor), el **pull list de novedades** (necesita un catálogo de números no
   poseídos y futuros que ZascArr no tiene), los **préstamos** y la **comparación con
   amigos** (ZascArr es de un solo operador; el multiusuario está en el parking lot).
5. **Recomendación primero:** **C3 — marcar leído/leyendo/pendiente y valorar**, sobre la
   tabla que ya existe, sin migración y sin llamadas externas. Es la función con mejor
   relación valor/coste para esta persona y la que más se acerca a lo que hacen Metron,
   Whakoom y LoCG con un solo clic. El corte mínimo es **S**; el backlog la estima **M**
   por el conjunto (filtros, contadores y notas).

**Las 7 ideas priorizadas, en una línea cada una:**

| # | Idea | Veredicto | Por qué |
|---|---|---|---|
| 1 | Leído / leyendo / pendiente + valoración + nota | **Adoptar** (sobre lo propio) | La tabla existe; no hay migración; valor altísimo; encaja con Kavita |
| 2 | Estadísticas de lectura | **Adaptar** | Barato una vez existe #1; sin gráficos ni dependencias |
| 3 | Historial de lectura / relecturas | **Adaptar** | Solo si las relecturas importan; exige migración |
| 4 | Estanterías / listas propias | **Adaptar** (sobre lo propio) | Las etiquetas ya cubren «estantería»; las listas ordenadas son C4 |
| 5 | Pull list / novedades | **Descartar por ahora** | ZascArr es file-first; no hay catálogo de futuros; L–XL |
| 6 | Ficha física (grado, precio, tienda, valor) | **Descartar** | Unidad equivocada: ZascArr gestiona archivos, no colección física |
| 7 | Préstamos + comparación social | **Descartar** | Sin usuarios ni amigos; multiusuario fuera de alcance; poco valor |

---

## 1. Problema local y persona

### 1.1 Qué se pregunta

No «¿qué API tiene Metron?», sino: **¿qué tareas de coleccionista resuelven Metron, LoCG,
CLZ, Whakoom o ComicBookRealm que ZascArr todavía no resuelva, y cuáles merecen la pena
para una persona no técnica con una Pi y una tebeoteca digital?**

Las tareas que el PO enumera: seguimiento de lectura, estanterías/colecciones,
valoraciones, pull list/suscripciones, estadísticas, wishlist, préstamos, etiquetas, notas,
«qué me falta para completar una serie» y comparación con amigos.

### 1.2 La diferencia de unidad, que condiciona todo

Metron, CLZ, Whakoom y ComicBookRealm son, en lo esencial, **catálogos de ejemplares
poseídos** (o deseados) con datos físicos: grapa, tomo, variante, grado, precio, caja.
ZascArr es un **gestor de archivos**: lo que hay en el disco, con su ruta, su hash y su
formato. La unidad de ZascArr es el `File` enlazado a un `Issue`; la de Metron es el
`CollectionItem` de un usuario. Esa diferencia explica por qué casi todo lo «físico» de
Metron no se puede trasplantar sin construir otro producto.

También explica el límite del «pull list»: Metron puede enseñar números futuros porque
tiene un catálogo completo de la serie; ZascArr solo tiene filas `Issue` de lo que ha
importado o dado de alta, más un `total_issues` de la fuente. No hay una lista de números
no poseídos que se pueda seguir.

### 1.3 Criterios de encaje

Una idea se considera buena para esta persona si:

- resuelve una pregunta que se hace **antes o después de leer** («¿lo tengo?», «¿lo he
  leído?», «¿qué me falta?», «¿qué me pareció?»);
- no exige abrir terminal, editar JSON ni entender una API;
- no añade dependencias, servicios ni RAM (nada de Redis, nada de SPA, nada de librerías
  de gráficos);
- no mueve, renombra ni escribe archivos;
- funciona con la biblioteca real (CBR/CBZ españoles, fuentes incompletas) y **dice «no
  sé»** cuando no hay dato, en vez de inventarlo;
- no compite con Kavita: Kavita lee; ZascArr cataloga y busca.

---

## 2. Método y evidencia

### 2.1 Qué se abrió y qué no

| Referencia | Qué se consultó | Estado |
|---|---|---|
| **Metron** | Documentación de la API en `api/README.md` (v1.12); modelos y vistas de `user_collection`, `pull_list`, `wish_list`, `reading_lists`; rutas y plantillas; licencia | Abierto en crudo desde GitHub, commit `c6e1c48`. La **web** `metron.cloud` está tras Anubis: **`[sin verificar]`** |
| **League of Comic Geeks** | Descripción pública de la app «Comic Geeks» (App Store, id `874775221`, v3.4.4, 2026-11-06), obtenida por iTunes Lookup API | Web `leagueofcomicgeeks.com` devuelve **403**; la app y su web **`[sin verificar]`** |
| **CLZ Comics** | Descripción pública de «CLZ Comics» (App Store, id `320501548`, v11.4.1), obtenida por iTunes Search API | Web `clz.com` devuelve **403**; la función NCBD/pull list **`[sin verificar]`** |
| **Whakoom** | Páginas públicas `/features` y `/features/advanced` (es/en), abiertas el 2026-11-09 | Abiertas |
| **ComicBookRealm** | Portada pública, abierta el 2026-11-09 | Abierta |
| **ZascArr** | Código y plantillas en `origin/main` `0694b28`; inventario de rutas y modelos | Leído, **no ejecutado** |

No se ha llamado a la API de Metron ni se ha creado cuenta. No se ha descargado ningún dato
de ninguna referencia. No se ha copiado código: las ideas se describen en palabras y, cuando
se cita una implementación, se cita el fichero y el commit para poder leerla, no para
reutilizarla.

### 2.2 Por qué Metron no vuelve a ser fuente

Ya está decidido y medido en [`benchmark-fuentes-metadatos-referencias.md`](benchmark-fuentes-metadatos-referencias.md)
(2026-11-09), que a su vez recoge el estado de ComicTagger:

- Metron solo admite series en **inglés e italiano**; no cubre la edición española.
- Su API exige **token** y tiene límites (20/min, 5 000/día según la ficha de fuentes).
- Sus datos son **CC BY-SA 4.0** y el código **GPL-3.0**; la atribución importa.
- ComicTagger **retiró** su soporte en 2025 por el daño que causaba al servicio.

Por tanto, este documento **no propone** integrar Metron, ni como fuente de metadatos, ni
como backend de colección, ni como API de lectura. Solo mira sus funciones.

---

## 3. Qué tiene ZascArr hoy (verificado en `0694b28`)

### 3.1 Cuadro de cobertura

| Función | Estado real en ZascArr | Evidencia | Hueco |
|---|---|---|---|
| **Leído / leyendo / pendiente** | Modelo completo, **sin UI ni API**. `ReadingStatus` tiene `unread`, `reading`, `completed`, `on_hold`, `dropped`; `ReadingProgress` es 1:1 con `Issue` y guarda `current_page`, `rating`, `started_at`, `completed_at`, `notes` | [`models/__init__.py:180-185`](../../src/zascarr/models/__init__.py#L180-L185) y [`:807-824`](../../src/zascarr/models/__init__.py#L807-L824) | Exponerlo: no hay ruta que lo cree, lea ni actualice |
| **Valoración** | Columna `rating` (`SmallInteger`) en `ReadingProgress`, **sin UI ni validación** | [`models/__init__.py:820`](../../src/zascarr/models/__init__.py#L820) | UI 1–5 y validación |
| **Notas** | `Wishlist.notes` y `ReadingProgress.notes` existen; **no se muestran** en las pantallas | [`models/__init__.py:778`](../../src/zascarr/models/__init__.py#L778) y [`:823`](../../src/zascarr/models/__init__.py#L823) | Superficie mínima; no hace falta modelo nuevo |
| **Estanterías / colecciones** | Etiquetas de serie con filtros booleanos, facetas y sugerencias. Tablas `reading_lists` / `reading_list_items` existen, **sin servicio ni rutas** | [`models/__init__.py:541-553`](../../src/zascarr/models/__init__.py#L541-L553), [`:827-871`](../../src/zascarr/models/__init__.py#L827-L871), [`services/etiquetas.py`](../../src/zascarr/services/etiquetas.py) | «Estantería» ya se puede hacer con etiqueta; lista ordenada, no |
| **Pull list / suscripciones** | `WishlistPolicy.MISSING` genera los números que faltan; `FUTURE` está **reservado y no es computable**; no hay catálogo de números futuros | [`models/__init__.py:160-168`](../../src/zascarr/models/__init__.py#L160-L168); D8 en [`BACKLOG.md:562`](../BACKLOG.md#L562) | Falta catálogo de no poseídos/futuros; sin él no hay pull list |
| **Wishlist** | Estados, prioridad, notas, búsqueda, política por serie, «Completar», integración con el orquestador | [`models/__init__.py:751-804`](../../src/zascarr/models/__init__.py#L751-L804), [`web/wishlist.py`](../../src/zascarr/web/wishlist.py), [`api/wishlist.py`](../../src/zascarr/api/wishlist.py) | Núcleo cubierto; los campos físicos de Metron no aplican |
| **Estadísticas** | Inicio: series, tebeos registrados, archivos, huecos, completitud global, últimas series | [`services/resumen.py:47-116`](../../src/zascarr/services/resumen.py#L47-L116), [`dashboard.html`](../../src/zascarr/web/templates/dashboard.html) | No hay estadísticas **de lectura** |
| **Préstamos** | No existe modelo ni pantalla; `grep` de `préstamo/prestado/loan` no encuentra nada | — | Sin equivalente en las referencias consultadas |
| **Etiquetas** | Cubiertas y probablemente por delante de las referencias: expresión booleana, facetas, sugerencias, normalización | [`services/etiquetas.py`](../../src/zascarr/services/etiquetas.py), [`web/library.py`](../../src/zascarr/web/library.py) | Nada urgente; `Issue.tags` existe pero no se expone |
| **Qué me falta** | Por serie (`huecos_de_serie`), en la ficha y en el Inicio; avisa cuando **no es computable**; «Completar» lo lleva a la wishlist | [`services/series.py:246-273`](../../src/zascarr/services/series.py#L246-L273), [`web/series.py:379-389`](../../src/zascarr/web/series.py#L379-L389), [`api/series.py:330`](../../src/zascarr/api/series.py#L330) | Cubierto; el porcentaje por serie sería un pulido XS |
| **Comparación con amigos** | No existe: **un solo operador**, sin usuarios ni roles | [`services/auth.py:10-14`](../../src/zascarr/services/auth.py#L10-L14); parking lot en [`BACKLOG.md:2222-2226`](../BACKLOG.md#L2222-L2226) | Fuera de alcance |

### 3.2 Lo que parece que falta y no falta

- **No falta «qué me falta»**: está calculado desde los archivos disponibles y el recuento
  de grapas, con un caso explícito de «no computable» cuando la fuente no acredita la
  unidad. Es más honesto que una resta sobre un catálogo ajeno.
- **No falta wishlist**: está más integrada que la de Metron con la búsqueda y la
  importación de ZascArr; lo que no tiene son los campos físicos (grado, precio, tienda),
  que no aplican a archivos.
- **No faltan etiquetas**: el sistema de etiquetas de serie con filtros `+`/`-` cubre lo
  que pide el PO; no se ha visto un contrato equivalente en las referencias consultadas,
  pero **no se afirma que carezcan de etiquetas**.
- **Sí falta lectura**: el modelo está, la superficie no. Es el hueco real.

### 3.3 La prueba de que el modelo de lectura está sin usar

Las únicas referencias a `ReadingProgress` fuera del modelo son dos servicios que **las
preservan o las cuentan antes de borrar**:

- [`services/retirada_serie.py:247`](../../src/zascarr/services/retirada_serie.py#L247)
  cuenta lecturas para el informe de retirada y las exporta en `:274-279`.
- [`services/desvinculacion.py:297`](../../src/zascarr/services/desvinculacion.py#L297)
  cuenta lecturas antes de desvincular un archivo.

No hay ninguna ruta `GET`/`POST` que cree, lea o actualice una fila de `reading_progress`
en el inventario de rutas de `web/` y `api/`. Eso confirma que C3 no está
empezada, no que esté olvidada: sigue en el backlog como **P1 M**
([`BACKLOG.md:151`](../BACKLOG.md#L151)).

---

## 4. Qué hacen las referencias

### 4.1 Metron — el catálogo de coleccionista completo

Metron es la referencia más rica en **gestión de colección personal**. Su API documenta
varias piezas separadas, y cada una tiene su propia pantalla:

| Pieza | Qué guarda / qué permite | Detalle que importa |
|---|---|---|
| **Collection** | Ejemplares que el usuario posee: cantidad, formato (`PRINT`/`DIGITAL`/`BOTH`), grado CGC 0,5–10, empresa de grading (CGC/CBCS/PGX), fecha/precio/tienda de compra, ubicación física, notas, `is_read`, fechas de lectura, valoración 1–5 | El estado de lectura y la valoración viven **en el ejemplar**, no en una tabla aparte de «lectura» |
| **Read dates** | Varias fechas por ejemplar, con `read_count`; `is_read` y `date_read` se sincronizan con la última | Permite relecturas e historial; `add_read_date`/`delete_read_date` tienen ruta propia |
| **Scrobble** | `POST /api/collection/scrobble/`: marca leído, crea el ejemplar si no existe, añade fecha y admite valoración | Es el «un clic» que hace que el coleccionista lo use de verdad |
| **Collection stats** | Total de ejemplares y cantidades, valor, leídos/no leídos, por formato, por editorial, por tipo de serie, top series, top guionistas y dibujantes, lecturas por día/mes | Todo calculado en el servidor; gráficos con Chartkick; no es trasplantable a Pi sin cuidado |
| **Missing series / missing issues** | Series con alguna posesión pero incompletas, con `owned_issues`, `missing_count` y `completion_percentage`; los números que faltan, ordenados | Es la misma pregunta que C2/C6 de ZascArr, resuelta sobre su catálogo |
| **Pull List** | Series que el usuario sigue; `GET /api/pull_list/issues/` devuelve los números de esas series por `store_date` | Es un **seguimiento de novedades**, no una wishlist: no requiere querer comprar el número |
| **Wish List** | Números deseados con prioridad, grado deseado, precio máximo y moneda, estado `Wanted`/`Found`/`Acquired`, notas; «acquire» crea el ejemplar de colección | Separa «lo quiero» de «lo tengo»; la adquisición es un paso explícito |
| **Reading List** | Listas ordenadas de números, públicas o privadas, con tipo (`CREATOR`, `EVENT`, `STORY`, `CHARACTERS`, `TEAMS`, `MASTER`), `issue_type` (`Prologue`, `Core Issue`, `Tie-In`, `Epilogue`), valoración media, atribución y enlace anterior/siguiente | Es una lista **curada**, no una estantería personal; el orden es el producto |

**Lo que Metron asume y ZascArr no comparte:** usuario con cuenta, catálogo completo de la
serie (incluidos números que no posee), ejemplar físico o digital con valor/estado, lectura
dentro de Metron (de ahí el scrobble) y una web multi-usuario con listas públicas. Nada de
eso es ZascArr.

**Lo que sí se puede copiar sin traer nada de eso:** el **contrato de interacción** de
«marcar leído en un clic», la **valoración 1–5** pegada al número, la **fecha de lectura**
como dato opcional y la **distinción entre pendiente, leyendo y leído**. La tabla de
ZascArr ya tiene los campos; lo que falta es la superficie.

### 4.2 League of Comic Geeks — el flujo semanal

La ficha pública de la app (v3.4.4, 2026-11-06) describe: novedades y próximos lanzamientos
con meses de antelación, reseñas y discusión de la comunidad, catálogo ilimitado de la
colección, escaneo de portada o código de barras, **pull list**, **wish list**, **marcar
números como leídos**, listas de la comunidad y sincronización web/app.

Para ZascArr lo aprovechable es el **pull list como lista de series seguidas** y el
**marcar leído**; el resto (catálogo de novedades, escaneo, comunidad, tiendas) depende de
una base de datos global y de una app móvil que ZascArr no tiene. Su API solo está
disponible para retailers, según la ficha de fuentes; no es una vía de datos.

### 4.3 CLZ Comics — el catálogo físico, hecho cómodo

La ficha pública de CLZ Comics (v11.4.1) describe: alta por escaneo de portada o código de
barras, datos automáticos, edición de campos, **caja/ubicación, grado, fecha/precio/tienda
de compra, notas, campos personalizados**, varias colecciones (físico/digital/vendido),
sincronización y compartición en la nube, valores de CovrPrice como add-on de pago y la
función NCBD (pull list) en su web **`[sin verificar]`**.

Es la referencia más clara de que **estanterías = varias colecciones** y de que el
coleccionista físico quiere saber **dónde está** y **cuánto vale**. Para ZascArr, que
gestiona archivos, esas columnas serían ruido; la idea de «varias colecciones» se puede
aproximar con etiquetas, sin crear un segundo concepto de biblioteca.

### 4.4 Whakoom — el coleccionista hispanohablante

Las páginas públicas de Whakoom (2026-11-09) describen: colección, **lista de deseados**
(con cómics aún no publicados y aviso al salir), **control de leído/pendiente** —incluido
lo leído sin tenerlo—, valoraciones y reseñas, colecciones de amigos, recomendaciones,
novedades, búsqueda por código de barras/ISBN, alta de series completas y, en PRO, notas,
ubicaciones, estado, firmas y fotos.

Es la referencia más cercana a la persona (público español, no técnico). Dos ideas valiosas:

- **«Leído» no es lo mismo que «tenerlo»**: Whakoom deja marcar leído algo que no tienes.
  ZascArr **no puede** hacerlo sin crear un `Issue` que no posee, porque su modelo de
  lectura cuelga de `issues`. Es un límite estructural, no un olvido.
- **La lista de deseos avisa de lo que va a salir**: eso es pull list + notificaciones, y
  depende de un catálogo de futuros que ZascArr no tiene.

Whakoom es también la referencia que confirma que **no hay que inventar** una feature de
préstamos: su solución es una **nota** («¿a quién se lo presté?»), no un módulo de
préstamos. No consta en las referencias consultadas que haya préstamos de primera clase.

### 4.5 ComicBookRealm — precio y comunidad

La portada pública (2026-11-09) se presenta como guía de precios gratuita y base de datos
de seguimiento: colección, «wanted», valor seguido, analizador CGC, mercado/eBay y foro.
Es útil como recordatorio de que **el valor** es una función de coleccionista físico, y
como evidencia de que el mercado y la comunidad son otro producto. No aporta nada al
ZascArr digital que no esté ya en las otras referencias.

### 4.6 Supuestos de las referencias que NO valen en ZascArr

| Supuesto de la referencia | Por qué no vale aquí |
|---|---|
| El ejemplar tiene grado, precio, tienda y ubicación física | ZascArr gestiona un archivo con ruta, hash y formato; no hay «caja 3» |
| El catálogo de la serie es completo y conoce números futuros | ZascArr solo tiene `Issue` de lo importado/dado de alta y un `total_issues` de la fuente |
| La lectura ocurre en la propia aplicación | En ZascArr se lee en Kavita u otro lector; ZascArr solo puede anotar el estado |
| Hay usuarios, amigos y listas públicas | ZascArr es de un solo operador, privado por defecto |
| Varias copias del mismo número son una cantidad | ZascArr deduplica archivos idénticos; los archivos múltiples de un número son ediciones, no «copias» |
| Las listas son curadas y públicas, con atribución | Las listas de ZascArr serían privadas y sobre lo que ya tienes |

---

## 5. Matriz: feature × referencia × ZascArr × veredicto

> **Valor** = para El Coleccionista (1–5). **Coste** = XS (<½ día), S (≤2 días),
> M (~1 semana), L (~2–3 semanas), XL (>3 semanas o subsistema nuevo). **Modelo** = ¿toca
> modelo o migración? **Veredicto** = adoptar / adaptar / descartar / cubierta.

| Feature | Metron | Otras referencias | ZascArr hoy | Valor | Coste | Modelo | Veredicto |
|---|---|---|---|---|---|---|---|
| **Leído / leyendo / pendiente** | `is_read` + `read_dates` + scrobble; estado en el ejemplar | LoCG: marcar leído; Whakoom: leído/pendiente; CLZ/CBR: no consta | Modelo `ReadingProgress`, **sin UI ni API** | 5 | S–M | No | **Adoptar** (sobre lo propio) |
| **Valoración 1–5** | `rating` en el ejemplar; endpoint de rating; scrobble con rating | LoCG: reseñas; Whakoom: valoraciones; CLZ/CBR: no consta | Columna `rating`, sin UI ni validación | 5 | XS–S | No | **Adoptar** (incluida en #1) |
| **Notas** | Notas de colección | Whakoom: notas (PRO); CLZ: notas | `Wishlist.notes` y `ReadingProgress.notes`, sin mostrar | 3 | XS | No | **Adoptar** (incluida en #1) |
| **Historial / relecturas** | Varias `read_dates`, `read_count`; historial de lectura | Whakoom: historial de leído; LoCG: progreso; CLZ/CBR: no consta | Solo `started_at`/`completed_at`; sin historial | 3 | M | Sí (aditiva) | **Adaptar** (después de #1) |
| **Estanterías / colecciones** | Colección + listas de lectura | CLZ: varias colecciones y ubicación; Whakoom: listas; LoCG: listas | Etiquetas de serie potentes; `reading_lists` sin uso | 4 | XS–M | No (tablas ya existen) | **Adaptar** (sobre lo propio) |
| **Listas ordenadas / orden de lectura** | `ReadingList` + `ReadingListItem.order` + tipos | LoCG: Community Lists; Whakoom: listas | `story_arc_issues.reading_order` (C4) y `reading_lists` sin UI | 4 | M | No | **Adaptar** (solo si C4 lo pide) |
| **Pull list / novedades** | Series seguidas + números por `store_date` | LoCG: pull list; CLZ: NCBD; Whakoom: avisos de novedades | `WishlistPolicy.MISSING`; `FUTURE` reservado; sin catálogo de futuros | 3 | L–XL | Sí (nueva tabla + fuente) | **Descartar por ahora** |
| **Wishlist** | Prioridad, grado deseado, precio máximo, estado, adquirir | LoCG/CLZ/Whakoom/CBR: listas de deseados | Estados, prioridad, notas, búsqueda, política, «Completar» | 5 | — | No | **Cubierta** |
| **Estadísticas** | Leídos/no leídos, valor, formatos, editoriales, top series/autores, lecturas por día/mes | Whakoom: cuántos leídos; CLZ/CBR: valor; LoCG: no consta | Solo estadísticas de biblioteca, no de lectura | 4 | S–M | No | **Adaptar** |
| **Préstamos** | No consta | Whakoom: solo una nota; resto: no consta | No existe | 1 | M | Sí | **Descartar** |
| **Etiquetas** | No consta en la API/modelos consultados; no se infiere ausencia | CLZ: campos personalizados; Whakoom/LoCG: listas | Etiquetas de serie con filtros booleanos, facetas y sugerencias | 5 | — | No | **Cubierta** |
| **Qué me falta / completitud** | `missing_series`, `missing_issues`, `completion_percentage` | LoCG/Whakoom: progreso de serie; CLZ: no consta | Por serie y en Inicio; «no computable» explícito; «Completar» | 5 | — | No | **Cubierta** (porcentaje XS opcional) |
| **Comparación con amigos** | Listas públicas y usuarios; no grafo de amigos | Whakoom: colecciones de amigos; LoCG: comunidad | Sin usuarios; un solo operador | 2 | L | Sí (usuarios) | **Descartar** |

---

## 6. Priorización: 7 ideas

### 6.1 Orden recomendado

| # | Idea | Veredicto | Valor | Coste | Depende de | Cuándo |
|---|---|---|---|---|---|---|
| 1 | **Leído/leyendo/pendiente + valoración + nota** (C3) | Adoptar (sobre lo propio) | 5 | S (corte) / M (completo) | Nada | **Ahora** |
| 2 | **Estadísticas de lectura** | Adaptar | 4 | S | #1 | Después de #1 |
| 3 | **Historial de lectura / relecturas** | Adaptar | 3 | M | #1 + migración | Solo si el PO lo pide |
| 4 | **Estanterías / listas** | Adaptar (sobre lo propio) | 4 | XS (etiqueta) / M (lista) | Etiquetas; C4 para listas | Después de medir uso de etiquetas |
| 5 | **Pull list / novedades** | Descartar por ahora | 3 | L–XL | Fuente de futuros | Revisar si aparece fuente |
| 6 | **Ficha física** (grado, precio, tienda, valor) | Descartar | 1 | M | — | No |
| 7 | **Préstamos + comparación social** | Descartar | 2 | M–L | Usuarios | No |

### 6.2 Idea 1 — Leído / leyendo / pendiente + valoración + nota

**Qué copiamos.** El patrón de Metron (`is_read`, `rating`, scrobble), Whakoom
(leído/pendiente) y LoCG (marcar leído): un control **de un clic** en el número, una
**valoración 1–5** opcional y una **nota privada** corta. Nada de comunidad, nada de
reseñas públicas.

**Qué no copiamos.** Las varias fechas de lectura, el progreso por página y el scrobble
automático: ZascArr no lee; Kavita lee. Tampoco la valoración media de otros usuarios.

**Encaje.** La tabla `reading_progress` ya existe desde la migración 0001; el enum tiene
los cinco estados; `rating` y `notes` ya están. **No hay migración.** La escritura es una
fila por número; la lectura, una consulta por ficha. No hay llamadas externas. Es el
ejemplo perfecto de «construir sobre lo propio»: la referencia aporta el **contrato de
interacción**, no el modelo.

**Corte mínimo (S).** Servicio `services/lectura.py` con `marcar(issue_id, estado, rating,
nota)` idempotente; una ruta HTMX de escritura en la ficha de serie y el filtro de lectura; control en la fila de cada número
presente; filtro `?leido=si|no|leyendo` en Biblioteca; validación 1–5. El contador del
Inicio puede esperar a #2.

**Riesgos.** (a) No exponer los cinco estados de golpe: la persona pide tres; `on_hold` y
`dropped` pueden quedarse en el modelo sin superficie. (b) No poner un botón por chip de
«Te faltan»: esos números no tienen `Issue` y no se pueden marcar. (c) Validar la
valoración en el servicio, no confiar en el formulario. (d) Decidir qué pasa al
desmarcar «Leído»: se borra `completed_at`, pero se conservan valoración y nota (son
opiniones, no estado). (e) No tocar `current_page`: es de un lector que ZascArr no es.

**Por qué primero.** Es la única idea que responde a «¿lo he leído?» y «¿qué me pareció?»,
que es la pregunta siguiente a «¿lo tengo?». No tiene dependencias, no toca archivos, no
gasta RAM y ya está en el backlog como C3. Metron, Whakoom y LoCG coinciden en el mismo
gesto; la diferencia es que ZascArr puede hacerlo sin cuenta, sin nube y sin catálogo
ajeno.

### 6.3 Idea 2 — Estadísticas de lectura

**Qué copiamos.** El panel de Metron, reducido a lo que ZascArr puede calcular con datos
propios: **leídos / pendientes / leyendo**, **% de tu biblioteca leída**, **valoración
media** y **reparto por tradición o editorial**. Gráficos de barras en HTML/CSS, con el
número escrito al lado; nada de librería de charting.

**Qué no copiamos.** Valor económico, formatos físicos, top guionistas/dibujantes y
lecturas por día/mes. Lo primero no aplica; lo segundo depende de créditos que no siempre
están; lo tercero necesita el historial (#3).

**Encaje.** Una consulta agregada sobre `reading_progress` + `issues` + `series`; sin
migración; sin Redis; sin JS nuevo. Hay que cuidar el coste: contar por estado es barato;
cruzar con editorial/tradición es un `JOIN` más. Se puede limitar a las series con archivos
y decir «según los datos que tenemos» cuando falte crédito.

**Riesgo.** Las métricas de vanidad aburren si no llevan a una acción. La pantalla debe
responder «¿qué tengo pendiente?» con un enlace a la lista filtrada, no solo pintar un
porcentaje.

### 6.4 Idea 3 — Historial de lectura / relecturas

**Qué copiamos.** Las `read_dates` de Metron y el historial de Whakoom: saber **cuándo** se
leyó y si se ha releído. Es útil para el coleccionista que vuelve a un tomo años después.

**Qué no copiamos.** Sesiones de lectura, páginas por sesión ni tiempo de lectura.

**Encaje y coste.** `ReadingProgress` solo tiene `started_at`/`completed_at`. Para varias
fechas hay dos opciones: una tabla `reading_events` (issue_id, read_at, índice) o una lista
JSONB en `ReadingProgress`. La tabla es más limpia para estadísticas por mes; el JSONB es
menos migración y menos joins. **Cualquiera de las dos es una migración aditiva (M).**

**Cuándo.** Solo si el PO dice que las relecturas importan. Si no, `completed_at` ya
responde «la última vez que lo leí» y no merece una tabla.

### 6.5 Idea 4 — Estanterías / listas

**Qué copiamos.** La idea de CLZ de **varias colecciones** y la de Whakoom/Metron de
**listas**. Para ZascArr, la forma más barata no es una entidad nueva: **una estantería es
una etiqueta** (o una combinación de etiquetas) y la Biblioteca ya sabe filtrarlas. Lo que
falta es una **pantalla de estanterías** que agrupe las etiquetas con su recuento y lleve
al filtro; eso es XS y no toca modelo.

**Listas ordenadas.** Si lo que se quiere es «Court of Owls en orden» (C4), el modelo
`reading_lists`/`reading_list_items` ya existe, pero **no hay servicio ni UI**. Exponerlo
es M y compite conceptualmente con `story_arc_issues.reading_order`. Recomendación: no
crear dos conceptos; usar arcos para el orden editorial y `ReadingList` solo para listas
arbitrarias del coleccionista, cuando C4 lo pida.

**Riesgo.** Tres palabras para lo mismo («colección», «estantería», «lista») confunden a
la persona. La UI debe elegir una: **Estanterías** para etiquetas; **Listas** solo si hay
orden.

### 6.6 Idea 5 — Pull list / novedades

**Qué copiamos (si algún día se hace).** Seguir series y ver qué números salen, como Metron
(`pull_list/issues` por `store_date`), LoCG (pull list), CLZ (NCBD) y Whakoom (avisos).

**Por qué no ahora.** ZascArr es **file-first**: no tiene un catálogo de números no
poseídos ni futuros. `WishlistPolicy.FUTURE` está reservado y el propio D8 dice que no es
computable. Para hacerlo bien haría falta: una fuente que publique futuros, una tabla de
series seguidas, un bucle de fondo (un solo worker, sin Redis), notificaciones y una
política de cortesía con la fuente. Es **L–XL** y cambia el producto de «gestor de lo que
tengo» a «agenda de novedades».

**Alternativa barata.** Lo que ya existe: `WishlistPolicy.MISSING` para completar lo que
falta y la lista de Deseados. No duplicar.

**Veredicto.** Descartar por ahora. Revisar si alguna fuente que ZascArr ya usa publica
números futuros y el PO lo prioriza; entonces sería una historia aparte, con su ficha y su
ADR.

### 6.7 Idea 6 — Ficha física (grado, precio, tienda, valor)

**Qué copiamos.** Nada. Metron (grado CGC, precio, tienda, ubicación), CLZ (caja, grado,
precio, valor CovrPrice), Whakoom (estado, ubicación, firmas) y CBR (valor de mercado) son
funciones de **colección física**.

**Por qué no.** ZascArr no sabe si el tebeo está en una caja ni cuánto costó; sabe qué
archivo hay, dónde y con qué hash. Añadir esas columnas sería una migración, una UI y una
promesa que el producto no puede cumplir. Si alguna vez se quiere dejar constancia, una
**nota** en el número o en el deseo es suficiente.

**Veredicto.** Descartar. No es un hueco: es otro producto.

### 6.8 Idea 7 — Préstamos + comparación social

**Préstamos.** No consta que ninguna referencia consultada tenga un módulo de préstamos de primera clase:
Whakoom lo resuelve con una **nota** («¿a quién se lo presté?»); Metron, CLZ y LoCG no
exponen un campo de préstamo en lo consultado **`[sin verificar]`**. En ZascArr, un archivo
«prestado» es una copia que no está; el producto deduplica archivos, no gestiona devoluciones.
Un módulo de préstamos exigiría tabla, persona, fecha y recordatorios para un valor bajo.

**Comparación con amigos.** Whakoom enseña colecciones de amigos; LoCG tiene comunidad;
Metron tiene listas públicas. ZascArr es de **un solo operador** (`auth.py:14`) y el
multiusuario está explícitamente en el parking lot. Añadirlo exigiría usuarios, permisos,
privacidad, moderación y RAM; es otro producto.

**Veredicto.** Descartar los dos. Si algún día se quiere compartir, un **enlace de solo
lectura** a una lista es más barato y más seguro que cuentas y amistades; no ahora.

---

## 7. La primera: C3, leído/leyendo/pendiente + valoración

### 7.1 Objetivo de la historia

Que El Coleccionista, desde la ficha de una serie, pueda decir **«este número lo he leído»**,
**«lo estoy leyendo»** o **«lo tengo pendiente»**, y puntuarlo de 1 a 5, **sin salir de
ZascArr, sin tocar el archivo y sin abrir otra aplicación**.

### 7.2 Por qué esta y no otra

- **Valor inmediato:** es la pregunta que sigue a «¿lo tengo?». Hoy la ficha solo dice
  «en tu biblioteca»; no dice si se ha leído.
- **Coste mínimo:** la tabla existe; no hay migración; no hay dependencias; no hay
  llamadas externas. El corte S es UI + servicio + una consulta.
- **Encaja con Kavita:** ZascArr no lee; Kavita lee. Marcar «leído» a mano después de leer
  es honesto y no promete integración que no existe.
- **Ya está en el backlog:** C3, P1 M, «`reading_progress` ya está en el modelo; falta
  exponerlo + UI» ([`BACKLOG.md:151`](../BACKLOG.md#L151)).
- **Las referencias convergen:** Metron (scrobble + rating), Whakoom (leído/pendiente),
  LoCG (mark read). El gesto está validado; lo que cambia es que aquí no hay cuenta ni
  nube.

### 7.3 Corte mínimo propuesto (S)

1. **Servicio** `services/lectura.py`:
   - `marcar(issue_id, estado, rating=None, nota=None)` con `upsert` por `issue_id`
     (la tabla tiene `unique=True`); idempotente.
   - Valida que el `Issue` existe; 404 si no.
   - Valida `rating` entero 1–5 o `None`; `nota` texto corto, sin HTML.
   - Al pasar a `completed`: `completed_at = now()` si estaba vacío; al salir de
     `completed`: `completed_at = None`; conserva `rating`/`nota`.
   - No toca `current_page` ni los archivos.
2. **Rutas HTMX** en `web/series.py`:
   - `POST /ui/series/{series_id}/numero/{issue_id}/leido` con `estado` (`unread`,
     `reading`, `completed`) y, opcional, `rating` y `nota`.
   - Respuesta: el fragmento de la fila del número, no la página entera.
   - Sin puerta legal: no hay descarga ni acción de riesgo; es un dato local.
3. **UI en la ficha de serie**:
   - En `Archivos por número`, cada número presente lleva un control compacto:
     «Pendiente / Leyendo / Leído» y cinco estrellas (o un `<select>` si las estrellas
     añaden ruido).
   - Los chips de «Te faltan» **no** llevan control: no tienen `Issue`.
   - La nota va en un `<details>` «Nota» para no romper el presupuesto de texto.
   - Accesibilidad: `aria-pressed` en el estado, etiquetas visibles, foco de teclado,
     nada de color como único indicador.
4. **Filtro en Biblioteca**:
   - `?leido=si|no|leyendo` sobre `ReadingProgress`; contador en el resumen.
   - El filtro se combina con los existentes (tradición, editorial, etiquetas).
5. **Contador en Inicio** (opcional en el corte S; recomendable en el M):
   - «Leídos» y «Pendientes de leer» con una consulta agregada; si se añade, que las
     cifras cuadren con el filtro, como el resto de V4.

### 7.4 Criterios de aceptación

- Marcar el número 3 como leído desde la ficha: al recargar, la fila dice «Leído»; en BD,
  `reading_progress.status = 'completed'` y `completed_at` no nulo.
- Desmarcar: vuelve a «Pendiente»; `completed_at` nulo; `rating` y `nota` se conservan.
- Puntuar 4: se guarda 4; puntuar 0 o 6: 422 con mensaje en español; borrar la puntuación:
  `NULL`.
- Poner una nota con `<script>`: se muestra escapada, no se ejecuta.
- El filtro «Leídos» de Biblioteca devuelve exactamente los números marcados; el contador
  coincide con la lista.
- Marcar dos veces el mismo número no duplica filas ni falla.
- Un `issue_id` de otra serie devuelve 404; un `issue_id` inexistente, 404.
- **Ningún archivo cambia**: mtime, tamaño y hash iguales antes y después (prueba de
  regresión, como en las historias que tocan disco).
- Con HTMX desactivado, el formulario sigue funcionando (POST + recarga); no se depende
  de JS para lo esencial.
- En móvil, el control no desborda la fila; en teclado, se alcanza y se activa.

### 7.5 No objetivos (para que no crezca)

- No progreso por página ni por porcentaje: eso es del lector, no del catálogo.
- No integración con Kavita ni con ningún lector; no hay scrobble automático.
- No reseñas públicas, ni «me gusta», ni valoración media de otros.
- No historial de relecturas en esta historia (eso es #3).
- No migración, no tabla nueva, no dependencia nueva.
- No se toca el archivo ni se mueve nada.

### 7.6 Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Ruido visual en una ficha con 100 números | Control compacto en la fila de archivos, no en cada chip; el estado se ve, la nota se pliega |
| «Leído» se confunde con «lo he leído en Kavita» | Una línea junto al control: «Márcalo cuando lo termines; ZascArr no lee el archivo» |
| Valoración sin validar | Validar en servicio y en el esquema; CHECK en BD solo si se quiere endurecer (migración) |
| Desmarcar borra la opinión | Conservar `rating`/`nota`; borrar solo `completed_at` |
| El filtro hace N+1 | Un `LEFT JOIN` a `reading_progress` en la consulta de biblioteca, como los filtros actuales |
| La persona no lo usa | El gesto debe estar donde ya mira: la ficha y la lista; no crear una pantalla nueva |

### 7.7 Casos de prueba que habría que escribir antes de implementar

- Servicio: alta, cambio de estado, desmarcar, idempotencia, rating fuera de rango,
  nota larga, issue inexistente.
- Web: fragmento HTMX con estado y estrellas; 404 en issue de otra serie; filtro de
  Biblioteca con y sin resultados; contador del Inicio (si entra en el corte).
- Postgres real: `unique(issue_id)` con dos `upsert` concurrentes; carácter escapado en
  la nota.
- Disco: mtime/tamaño/hash del archivo antes y después (guardarraíl de «no toca archivos»).
- Accesibilidad: foco, `aria-pressed`, etiquetas; sin depender del color.

---

## 8. Lo que ya está cubierto y no hay que copiar

| Función | Por qué no se toca |
|---|---|
| **Wishlist** | ZascArr tiene estados, prioridad, notas, búsqueda, política por serie y «Completar». Metron añade grado/precio/tienda, que son físicos. Lo único que se podría hacer es **mostrar la nota** en la fila (XS), no urgente |
| **Etiquetas** | Series con filtros booleanos, facetas y sugerencias; no se ha visto un contrato equivalente en las referencias consultadas (sin afirmar que carezcan de etiquetas). No añadir un segundo sistema |
| **Qué me falta** | Por serie y en Inicio, con «no computable» explícito y «Completar». Es la respuesta correcta; el porcentaje por serie es un pulido XS, no una historia |
| **Completitud global** | El Inicio ya da «tienes X de Y (Z %)»; no hace falta copiar el `completion_percentage` de Metron |
| **Estadísticas de biblioteca** | Series, tebeos, archivos, huecos y últimas series ya están; lo que falta es lectura (#2) |

---

## 9. IGUALAR / MEJORAR

### 9.1 IGUALAR (mínimo competitivo)

- **Un clic para marcar leído**, con estado visible en la ficha.
- **Valoración 1–5** privada, sin comunidad.
- **Nota** corta por número.
- **Estadísticas básicas** de lectura (leídos/pendientes/valoración media).
- **Wishlist y «qué me falta»** ya igualados o por delante.

### 9.2 MEJORAR (con evidencia)

**No se propone ninguna mejora nueva.** El benchmark no encontró una debilidad probada de
Metron que ZascArr deba superar; la ventaja diferencial ya existe y no es una función:

- **Honestidad del dato:** ZascArr no inventa huecos si la fuente no acredita la unidad
  (`services/series.py:360-368`); Metron calcula sobre su catálogo, que no cubre la edición
  española.
- **Coste en Pi:** todo es local, sin nube, sin cuenta, sin Redis.
- **Etiquetas:** filtros booleanos y facetas; no se ha verificado que las referencias no
  tengan algo equivalente, así que no se reclama superioridad.

Copiar lo básico primero; si luego se mide que el coleccionista usa lectura y etiquetas,
se podrá hablar de mejorar.

---

## 10. Aviso legal

- **Solo ideas y patrones.** Este documento no copia código, datos, textos, iconos ni
  diseño de Metron, League of Comic Geeks, CLZ, Whakoom ni ComicBookRealm. No se ha
  descargado ninguna base de datos ni se ha llamado a sus API.
- **Metron:** código **GPL-3.0**; datos **CC BY-SA 4.0** según la ficha de fuentes. Su API
  exige cuenta/token y atribución. No se reutiliza nada; si en el futuro se reutilizara una
  implementación concreta, habría que revisar el fichero y sus avisos, no solo la licencia
  del repositorio.
- **Whakoom:** contenido textual **CC BY-SA 4.0**; sus términos **prohíben el acceso
  automatizado** (ficha de fuentes). Solo se han leído páginas públicas de funciones; no se
  ha raspado nada.
- **League of Comic Geeks, CLZ Comics y ComicBookRealm:** propietarios. Solo se han leído
  descripciones públicas de App Store y la portada de CBR; no se ha usado su API ni se ha
  raspado su web. Sus nombres se citan de forma descriptiva, sin afiliación ni respaldo.
- **Datos personales:** la lectura y la valoración se quedan en la Pi; no hay telemetría,
  no hay cuenta, no hay comparación social. Es una decisión de producto, no solo técnica.
- **Nada de este documento autoriza a implementar:** es insumo para que el PO decida; la
  especificación y los tests van después.

---

## 11. NOT RUN / límites

- **Metron UI:** no abierta; `metron.cloud` está tras Anubis. Las funciones se han
  verificado en la documentación de la API y en el código del repositorio, **no** en la
  interfaz. `[sin verificar]` en lo que solo se vería allí.
- **Metron API:** no se ha llamado; no hay cuenta ni token. No se ha comprobado el
  comportamiento real de `scrobble`, `collection/stats` ni `pull_list/issues`.
- **League of Comic Geeks:** web 403; la descripción es la de la ficha de App Store
  (iTunes Lookup). No se ha probado la app. `[sin verificar]` en la web.
- **CLZ Comics:** web 403; la descripción es la de la ficha de App Store (iTunes Search).
  La función NCBD/pull list se cita desde una nota de novedades que no se pudo abrir.
  `[sin verificar]`.
- **ZascArr:** leído, no ejecutado. No se ha medido una biblioteca real, ni RAM, ni
  tiempos. No se han ejecutado tests.
- **No se ha comprobado** que Metron tenga o no etiquetas de usuario, préstamos o
  comparación con amigos en su interfaz; no se infiere ausencia por no encontrarlo en la
  API. Se dice «no consta en lo consultado».
- **No se ha medido** el coste real de las estadísticas con 50 000 ficheros; la estimación
  S se basa en consultas agregadas y en el patrón de V3, no en una medición.

---

## 12. Caducidad y siguiente paso

- **Caduca:** 2027-01-08 (~60 días), o antes si Metron cambia de versión mayor, si ZascArr
  implementa C3, o si aparece una fuente que publique números futuros.
- **Siguiente paso propuesto:** llevar al PO la decisión de **C3** con el corte S de §7.3.
  Si dice sí, especificar los criterios de §7.4 y los casos de §7.7; si dice no, la
  siguiente candidata es **#2 estadísticas** (necesita #1) o **#4 estanterías** (no
  necesita #1).
- **Decisiones que necesito del PO:**
  1. ¿C3 es la siguiente historia P1, con el corte S (tres estados + rating + nota), o se
     espera al M completo (filtros + contadores)?
  2. ¿La valoración es 1–5 privada, sin reseña pública? (Recomendado: sí.)
  3. ¿Las relecturas importan? (Si no, #3 se descarta y `completed_at` basta.)
  4. ¿«Estantería» se queda en etiqueta o se quiere una lista ordenada propia? (Recomendado:
     etiqueta ahora; lista solo con C4.)

---

## Fuentes

| ID | Fuente | Qué acredita | Estado |
|---|---|---|---|
| M1 | [Metron API README, commit `c6e1c48`](https://github.com/Metron-Project/metron/blob/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad/api/README.md) | Colección, scrobble, stats, missing, pull list, wish list, reading list; versión 1.12 | Abierta en crudo |
| M2 | [Modelos de `user_collection`](https://github.com/Metron-Project/metron/blob/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad/user_collection/models.py) | `CollectionItem`, `ReadDate`, grado, precio, formato, `is_read`, `rating` | Abierta en crudo |
| M3 | [Modelos de `pull_list`](https://github.com/Metron-Project/metron/blob/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad/pull_list/models.py), [`wish_list`](https://github.com/Metron-Project/metron/blob/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad/wish_list/models.py) y [`reading_lists`](https://github.com/Metron-Project/metron/blob/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad/reading_lists/models.py) | Series seguidas, deseados con prioridad/grado/precio, listas ordenadas y tipos | Abierta en crudo |
| M4 | [Vistas de `user_collection`](https://github.com/Metron-Project/metron/blob/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad/user_collection/views.py) y [rutas](https://github.com/Metron-Project/metron/blob/c6e1c48e54ab3c716febb3ae542de36ffd5e2dad/user_collection/urls.py) | Stats, historial, missing, rating, read dates | Abierta en crudo |
| M5 | [Repositorio de Metron](https://github.com/Metron-Project/metron) | Licencia GPL-3.0; commit `c6e1c48` (2026-11-07) | Abierta |
| M6 | [metron.cloud](https://metron.cloud/) | Web pública | **Bloqueada por Anubis** `[sin verificar]` |
| L1 | [Comic Geeks en App Store (id 874775221)](https://apps.apple.com/us/app/comic-geeks/id874775221) | Colección, pull list, wish list, marcar leído, listas, escaneo | Descripción vía iTunes Lookup; web 403 `[sin verificar]` |
| C1 | [CLZ Comics en App Store (id 320501548)](https://apps.apple.com/us/app/clz-comics-collection-database/id320501548) | Escaneo, caja, grado, precio, notas, varias colecciones, valores, nube | Descripción vía iTunes Search; web 403 `[sin verificar]` |
| W1 | [Whakoom — funciones](https://en.whakoom.com/features) | Colección, deseados, leído/pendiente, valoraciones, amigos, novedades | Abierta |
| W2 | [Whakoom — funciones avanzadas](https://en.whakoom.com/features/advanced) | Barcode/ISBN, series completas, notas/ubicaciones/estado (PRO) | Abierta |
| B1 | [ComicBookRealm](https://comicbookrealm.com/) | Guía de precios, colección, wanted, valor, CGC, mercado | Abierta |
| Z1 | [`models/__init__.py`](../../src/zascarr/models/__init__.py#L807-L871) | `ReadingProgress`, `ReadingList`, `ReadingListItem` | Código en `0694b28` |
| Z2 | [`services/series.py`](../../src/zascarr/services/series.py#L246-L273) | Huecos, unidad de grapa, «no computable» | Código en `0694b28` |
| Z3 | [`services/resumen.py`](../../src/zascarr/services/resumen.py#L47-L116) | Estadísticas de biblioteca | Código en `0694b28` |
| Z4 | [`services/etiquetas.py`](../../src/zascarr/services/etiquetas.py) | Etiquetas, normalización, filtros | Código en `0694b28` |
| Z5 | [`services/auth.py`](../../src/zascarr/services/auth.py#L10-L14) | Un solo operador, sin usuarios | Código en `0694b28` |
| Z6 | [`BACKLOG.md`](../BACKLOG.md#L151) | C3 leído/puntuado, P1 M | Documento en `0694b28` |
| Z7 | [`benchmark-fuentes-metadatos-referencias.md`](benchmark-fuentes-metadatos-referencias.md) | Metron solo EN/IT, token, CC BY-SA 4.0; no integrar como fuente | Documento en `0694b28` |
