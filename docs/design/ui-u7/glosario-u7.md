# U7 — Glosario de vocabulario de producto y tabla de cambios para #205

| Dato | Valor |
|---|---|
| **Estado** | **Glosario acordado (SPEC/UX, 2026-11-14); no aplica los cambios de #205.** La aprobación formal del PO se registra en #793. |
| **Fecha** | 2026-11-14 (Europe/Madrid) |
| **SHA de partida** | `c90b8ed0` (base documental de #205) |
| **Árbol inspeccionado** | `0816bd8e` (`docs/u7-glosario`; incluye #791, el recorte U18b) |
| **Issues** | #793 (BL-U7, esta historia) · #205 (BL-U18, consumidor) |
| **Rol** | SPEC/UX |
| **Alcance** | Glosario, tabla de cambios, navegación y criterios. El **PR de #793** incluye además el arreglo de navegación (Mejoras, `PAGINAS`, prefijos de `entrada_activa`); no aplica los textos de #205 ni toca autenticación, datos o URLs. |
| **Fuera de alcance** | Aplicar textos, renombrar entidades o valores persistidos, migraciones, despliegue, validación en navegador o en la Pi. |

> **Fuente normativa:** `CLAUDE.md` §14. Este documento no duplica el glosario completo: lo
> operativiza para #205. Si hay discrepancia entre el resumen de §2 y la tabla de `CLAUDE.md`, manda
> `CLAUDE.md`. Las líneas citadas se comprobaron en el árbol indicado; el inventario de #205 es de
> `c90b8ed0` y puede desplazarse si el código cambia.

---

## 1. Qué cierra este documento y qué no

**Cierra de U7 (documentación):**

- El glosario de producto en [`CLAUDE.md`](../../../CLAUDE.md) §14, con concepto, definición, texto
  por contexto, términos prohibidos y ubicaciones.
- La tabla de cambios que #205 puede aplicar, con texto anterior, texto acordado, ubicación y prueba
  visible propuesta (§3).
- La comprobación de navegación (§4): los tres grupos ya existen y solo hay un desajuste real de
  título/h1/menú en las entradas principales.

**No cierra:**

- **#205.** Este documento no aplica los textos ni ejecuta las pruebas. #205 conserva sus criterios 1–8
  y su DoD; el AC5 (“Terminología trazable”) pasa de “no hay glosario que citar” a “hay glosario y
  tabla, falta aplicarlos y probarlos”.
- **#793** como “hecha”: la aprobación del PO y la decisión sobre las dudas de §7 siguen abiertas.
- **Ninguna entidad, estado, operación, URL o valor persistido.** El glosario fija texto visible; no
  renombra el modelo ni la base de datos.

**Relación con #205:** #205 es el consumidor. Su DoR pedía “Documento/versión de U7 identificado y
conceptos revisados”; la versión es este documento (con el glosario de `CLAUDE.md` §14) y la fecha
2026-11-14. Su AC5 y su DoD pueden citarlo, pero solo se acreditan cuando #205 aplique los cambios y
las pruebas pasen.

**Evidencias principales:** [`CLAUDE.md` §14](../../../CLAUDE.md) ·
[`docs/BACKLOG.md` U7](../../BACKLOG.md#L959) y [U18](../../BACKLOG.md#L1041) ·
[inventario de #205](../ui-u18/inventario-textos-y-recorte.md) ·
[vigencia 2026-11-14](../ui-u18/vigencia-2026-11-14.md) ·
[`menu.py`](../../../src/zascarr/web/menu.py#L28) ·
[prueba de navegación](../../../tests/test_web_navegacion.py#L429-L448) ·
[plantillas](../../../src/zascarr/web/templates).

---

## 2. Términos acordados (resumen operativo)

| Concepto | Regla de una línea |
|---|---|
| **biblioteca** | La pantalla `/ui/biblioteca` y el catálogo de series; **no** «Mi biblioteca». |
| **tebeoteca** | El conjunto entero de tebeos del coleccionista; **no** «colección». |
| **colección** | Un grupo con nombre de series (#155); **no** el conjunto entero ni una carpeta. |
| **Por revisar** | La cola `/ui/pendientes`; **no** «Pendientes» como nombre de pantalla. |
| **Duplicados / revisión** | La revisión del disco en `/ui/auditoria`; acción «Revisar mi biblioteca»; **no** «Revisión de mi biblioteca». |
| **pendiente** | Estado de un registro sin número; **no** «archivo». |
| **archivo** | El fichero físico del disco; **no** «registro». |
| **registro** | La fila de `files`; solo en la explicación de procedencia y en contextos técnicos. |
| **suelto** | Un pendiente sin carpeta de serie contextual. |
| **tebeo** | El objeto o ejemplar; «Tebeo español» solo como tradición. |
| **número** | La unidad bibliográfica (`Issue`); **no** «tebeo» al contar números. |
| **saga** | La superficie; «arco» y `StoryArc` son código. |

---

## 3. Tabla de cambios

### 3.1 Cambios de vocabulario en las rutas de #205

Columnas: **concepto** · **texto anterior (fichero:línea)** · **texto acordado** · **ubicación
(ruta/fragmento)** · **prueba de texto visible propuesta**.

| Concepto | Texto anterior (fichero:línea) | Texto acordado | Ubicación (ruta/fragmento) | Prueba de texto visible propuesta |
|---|---|---|---|---|
| **pendiente** (cola) | «Archivos que el sistema no supo clasificar solo.» — `pendientes.html:5` | «Pendientes que el sistema no supo clasificar solo.» | `/ui/pendientes`, subtítulo (`pendientes.html:5`) | `GET /ui/pendientes`: el texto visible del subtítulo contiene «Pendientes que el sistema no supo clasificar» y no «Archivos que…». Usar el patrón `_texto_visible` de `tests/test_pendientes.py:212-215`, acotado al subtítulo. |
| **pendiente** (recomendación) | «Empieza por carpeta: resuelves varios archivos con una sola decisión.» — `pendientes.html:6` | «Empieza por carpeta: resuelves varios pendientes con una sola decisión.» | `/ui/pendientes`, pista (`pendientes.html:6`) | `GET /ui/pendientes` con tarjetas: el texto visible contiene «varios pendientes» y no «varios archivos». |
| **suelto** (enlace) | «Ver los archivos sueltos» — `pendientes.html:16` | «Ver los pendientes sueltos» | `/ui/pendientes`, enlace (`pendientes.html:16`) | El texto visible del enlace es «Ver los pendientes sueltos»; no «Ver los archivos sueltos». |
| **suelto** (vista) | «Archivos sueltos» — `sueltos.html:2,8,13,18`; «No se pudieron leer los archivos sueltos» — `:9`; «No hay archivos sueltos» — `:14` | «Pendientes sueltos»; «No se pudieron leer los pendientes sueltos»; «No hay pendientes sueltos» | `/ui/pendientes/sueltos`, `<title>`, `h1`, error y vacío | `<title>` y `h1` son «Pendientes sueltos — ZascArr» y «Pendientes sueltos»; el error y el vacío dicen «pendientes sueltos»; no aparece «Archivos sueltos» en el texto visible. |
| **suelto** (en carpetas) | «Los archivos sueltos y las carpetas sin contexto…» — `carpetas.html:8`; «Los archivos de la raíz, de la tradición o dentro de contenedores se cuentan como sueltos» — `:102` | «Los pendientes sueltos y las carpetas sin contexto…»; «Los pendientes de la raíz, de la tradición o dentro de contenedores se cuentan como sueltos» | `/ui/pendientes/carpetas`, vacío y detalle plegado | El texto visible del bloque vacío y de «¿De dónde salen estos datos?» usa «pendientes sueltos» y «pendientes de la raíz»; no «archivos sueltos» ni «archivos de la raíz». |
| **registro** (contador) | «N registros visibles.» — `carpetas.html:92` | «N pendientes visibles.» | `/ui/pendientes/carpetas`, subtítulo de resumen (`carpetas.html:92`) | El subtítulo contiene «pendientes visibles» y no «registros visibles». El desplegable de procedencia queda fuera de esta aserción. |
| **registro** (resumen y detalle) | «{{ g.n_archivos }} registros» — `carpetas.html:162`; «Afecta a N registros» — `:226`; «Registros» — `:195`; «Ver registros (N)» — `:240` | «N pendientes» en la tarjeta y el resumen; «Registros» se conserva en el desplegable de procedencia (`carpetas.html:97-110`), que distingue la fila del archivo | `/ui/pendientes/carpetas`, tarjeta y detalle de grupo | El texto visible de `.carpeta-resumen`, del resumen de señales y del `<summary>` «Ver pendientes» usa «pendientes»; «registros» solo se permite dentro de `details.carpeta-explicacion`. |
| **Por revisar / Pendientes por carpeta** (título y padre) | «Pendientes por carpeta» — `carpetas.html:2,29`; menú «Por revisar» — `menu.py:32`; CTA «Revisar por carpeta (N carpetas)» — `_pendientes_carpetas_enlace.html:3` | Se conserva «Pendientes por carpeta» como título de la vista; `<title>` pasa a «Pendientes por carpeta — Por revisar — ZascArr» y se añade la miga «Por revisar › Pendientes por carpeta». El CTA no cambia: cuenta carpetas y es una acción, no un nombre de pantalla. | `/ui/pendientes/carpetas`, `<title>`, miga y CTA | `<title>` contiene «Pendientes por carpeta — Por revisar»; el `h1` es «Pendientes por carpeta»; el menú sigue diciendo «Por revisar»; el CTA sigue diciendo «Revisar por carpeta (N carpetas)». |
| **estado de la serie** (Biblioteca) — decisión del PO | «Estado de la colección» — `_selector_coleccion.html:1`; `series_detail.html:156` | «Estado de la serie». Si el PO prefiere «Completitud», solo cambia la etiqueta; el parámetro `coleccion` y sus valores no se tocan. | `/ui/biblioteca`, filtro de estado; `/ui/series/{id}`, sección de estado | La etiqueta visible es «Estado de la serie» y el `select` conserva `name="coleccion"` y los valores `completa`, `faltan`, `no_calculable`, `no_completar`. |
| **registro** (acto) | «Hay un registro en marcha» — `carpetas.html:16`; «El registro está en Duplicados» — `:20` | «Estamos registrando la biblioteca»; «Registrar la biblioteca está en Duplicados» | `/ui/pendientes/carpetas`, aviso de registro en curso | El texto visible habla de «registrar», no de «un registro» como sustantivo. |
| **registro** (vacío) | «No hay registros pendientes» — `carpetas.html:124` | «No hay pendientes por carpeta» | `/ui/pendientes/carpetas`, vacío | El vacío usa «pendientes», no «registros». |
| **tebeoteca** (conjunto) | «Descargar colección y deseados» — `estado.html:115` | «Descargar tebeoteca y deseados» | `/estado`, bloque de descarga | El texto visible usa «tebeoteca» para el conjunto, no «colección». |
| **tebeoteca** (conjunto, Ajustes/Exportar) | «Descarga tu colección» — `ajustes.html:401`; «Exportar colección y deseados» — `exportar.html:2,5` | «Descarga tu tebeoteca»; «Exportar tebeoteca y deseados» | `/ui/ajustes` y `/ui/exportar` (fuera de #205; U7/V10) | El texto visible usa «tebeoteca»; «colección» queda para un grupo con nombre. |

> **Nota de alcance:** las filas de esta tabla son las que #205 puede aplicar en sus rutas (Acceso,
> Biblioteca, Por revisar y Estado). La fila de «estado de la serie» es la única que depende de una
> decisión de producto; el resto de 3.1 son cambios de texto o de título sin efecto en datos.

## 3.2 Cambios de navegación y de otras pantallas (U7 / PR de código, no #205)

Estos cambios están acordados por el glosario, pero **no los aplica #205**: van en el PR de código de
U7 o en la historia que corresponda. Se registran aquí para que no se pierdan.

| Concepto | Texto anterior (fichero:línea) | Texto acordado | Ubicación (ruta/fragmento) | Prueba de texto visible propuesta |
|---|---|---|---|---|
| **Mejoras** (título/h1) | «Mejoras de edición» — `mejoras.html:2,5`; el menú dice «Mejoras» — `menu.py:35`; el enlace de Biblioteca dice «Mejoras» — `biblioteca.html:8` | `<title>` y `h1`: «Mejoras»; subtítulo: «Mejores ediciones para números que ya tienes. ZascArr propone; tú decides.» «Mejoras de edición» no es nombre de pantalla; el concepto es «mejora» (§14 de `CLAUDE.md`). **Corregido en el PR de código de #793**: `<title>`/`h1` ya dicen «Mejoras» y el test recorre las 10 entradas. | `/ui/mejoras`, `<title>` y `h1` | Ampliar `PAGINAS` de `tests/test_web_navegacion.py:429-433` con `("mejoras", "/ui/mejoras")`: `<title>` y `h1` coinciden con la entrada «Mejoras»; el subtítulo contiene «Mejores ediciones». |
| **pendiente** (Inicio) | «tebeos sin clasificar» — `dashboard.html:120` | «pendientes sin clasificar» | `/ui/`, tarjeta «Por revisar» | El texto visible del enlace de la tarjeta dice «pendientes sin clasificar»; no «tebeos sin clasificar». |
| **tebeoteca** (Inicio) | «Tu colección ahora» — `dashboard.html:100` | «Tu tebeoteca ahora» | `/ui/`, cabecera de sección | El `h2.seccion` dice «Tu tebeoteca ahora»; no «Tu colección ahora». |
| **saga** (Sagas) | «el orden que marca cada arco» — `arcos.html:6`; «Cuando ZascArr tenga arcos con números enlazados» — `arcos.html:10` | «el orden que marca cada saga»; «Cuando ZascArr tenga sagas con números enlazados» | `/ui/arcos`, subtítulo y vacío | El texto visible de `/ui/arcos` usa «saga/sagas»; no «arco/arcos». La URL `/ui/arcos` no cambia. |
| **saga** (Ajustes) | «serie, número y arcos» — `ajustes.html:43` | «series, números y sagas» | `/ui/ajustes`, descripción de la fuente DC Database (V10) | El texto visible de Ajustes usa «sagas»; no «arcos». Fuera de #205. |
| **edición** (ficha de número) | «Otras publicaciones con este número» — `issue_detail.html:103` | «Otras ediciones de este número» | `/ui/series/{id}/numero/{id}`, resumen plegable | El texto visible del `<summary>` dice «Otras ediciones de este número»; no «Otras publicaciones con este número». |
| **registro** (ficha de serie) | «Se conserva como registro, no se borra.» — `_politica_serie.html:131,133` | «Se conserva anotado, no se borra.» | `/ui/series/{id}`, nota de números retirados | El texto visible de la nota dice «se conserva anotado»; no «como registro». |
| **biblioteca** (Auditoría) | «Antes de meter tu colección en el catálogo» — `auditoria.html:6`; «Registrar mete tus tebeos en el catálogo de ZascArr» — `_auditoria_registro.html:297` | «Antes de registrar tu biblioteca»; «Registrar mete tus tebeos en tu biblioteca» | `/ui/auditoria`, introducción y bloque de registro (V11) | El texto visible de `/ui/auditoria` y del fragmento `/ui/auditoria/registro` usa «biblioteca» en esas frases; no «catálogo». Fuera de #205. |

### 3.3 No cambia: conceptos distintos que no se sustituyen

| Concepto | Texto actual (fichero:línea) | Por qué no cambia | Prueba de guarda propuesta |
|---|---|---|---|
| **Tebeo español** (tradición) | `library.py:63`; `_rejilla_biblioteca.html:126,155`; el valor `tebeo` sigue en `library.py:522` y se renderiza en `_filtros_panel_campos.html:7` | Es la etiqueta correcta de `ComicTradition.TEBEO`; el valor interno y la URL `tradition=tebeo` no se tocan. | `tests/test_web_library.py:768`: una tarjeta `tebeo` muestra «Tebeo español»; el HTML conserva `value="tebeo"`. |
| **Números** (Biblioteca) | `_rejilla_biblioteca.html:106,127`; `series_detail.html:26` | Cuenta unidades bibliográficas (`Issue`), no archivos ni tebeos. | `tests/test_web_library.py:595,609`: la cabecera es «Números» y una serie sin dato muestra «No consta». |
| **Tebeos registrados** vs **Números que te faltan** (Inicio) | `dashboard.html:105,126` (y `:46,62`) | «Tebeos registrados» cuenta ejemplares presentes (filas de `files`); «Números que te faltan» cuenta huecos de numeración. Son conceptos distintos. | Guarda de texto visible: la tarjeta de tebeos usa «Tebeos registrados»; la de huecos usa «Números que te faltan»; no se intercambian. |
| **El mismo tebeo, dos veces** vs **El mismo número, en dos ediciones** | `_auditoria_informe.html:44,58` | El primero es contenido idéntico (duplicado); el segundo es el mismo número con archivos distintos (ediciones). Es el ejemplo canónico de la distinción. | Guarda de texto visible en `/ui/auditoria`: ambos títulos se conservan y no se convierten en sinónimos. |
| **Mostrando N pendientes** / **Nada pendiente** | `_pendientes_rango.html:4`; `pendientes.html:21` | «Pendiente» es el estado correcto de la cola; no es «registro» ni «archivo». | `tests/test_pendientes.py` ya usa el rango; guarda de texto visible de `#pend-rango`. |
| **Revisar por carpeta (N carpetas)** | `_pendientes_carpetas_enlace.html:3` | Cuenta carpetas y es una acción; no es el nombre de la pantalla. | Guarda: el CTA conserva «Revisar por carpeta» y el número cuenta carpetas. |
| **Publicación** (correspondencias) | `crear_correspondencia.html:21`: «Una publicación es un número o tomo de tu biblioteca.» | En ese flujo, «publicación» es la unidad de destino (número o tomo); no es sinónimo general de «número». | Guarda de texto visible en el flujo de correspondencias; no se renombra a «número». |
| **Registros** en la explicación de procedencia | `carpetas.html:99-100,103,105,108` (varias frases con «registros»); p. ej. «Son registros pendientes de verificar, no archivos confirmados.» — `:99` | Es el desplegable que define la fila de la BD frente al archivo; es una excepción técnica justificada. | Guarda: las frases se conservan dentro de `details.carpeta-explicacion`; no se usan en los contadores principales. |
| **Selector de editorial vacío** | «Todas las editoriales» como única opción — `_filtros_panel_campos.html:15` (ya corregido) | Ya corregido por #791 (U18b): el bloque depende de `publishers or filtros.publisher_id` (`:11`), no de `es_fragmento`; se comprueba en `/ui/biblioteca` y en el fragmento `/ui/biblioteca/resultados`. | No reabrir #270/#791; la prueba existente de página completa y la nueva de fragmento cubren el caso. |
| **Aviso de vista manipulada** | «La vista pedida no existe; se muestran tarjetas.» — `library.py:201` (ya corregido) | Ya corregido por #791 (R4); se conserva como guarda en `/ui/biblioteca?vista=inventada`. | La prueba de `?vista=inventada` fija «La vista pedida no existe»; no se reabre. |

---

## 4. Navegación

### 4.1 Los tres grupos ya existen

`menu.py:28` declara `GRUPOS = ("Mi colección", "Añadir", "Sistema")`; `_componentes.html:84-91` pinta
un `<div class="nav-grupo" role="group" aria-label="…">` por grupo; `tests/test_web_navegacion.py:257-266`
fija las etiquetas y el reparto. **No hay que crear la agrupación**: el criterio 2 de U7 ya está
cumplido en el árbol actual.

### 4.2 Entradas principales: título, h1 y menú

| Entrada (`menu.py`) | Ruta | `<title>` | `h1` | ¿Coincide? |
|---|---|---|---|---|
| Inicio — `:31` | `/ui/` | `dashboard.html:3` | `dashboard.html:40` | Sí |
| Por revisar — `:32` | `/ui/pendientes` | `pendientes.html:2` | `pendientes.html:4` | Sí |
| Biblioteca — `:34` | `/ui/biblioteca` | `biblioteca.html:2` | `biblioteca.html:5` | Sí |
| **Mejoras — `:35`** | `/ui/mejoras` | `mejoras.html:2` («Mejoras») | `mejoras.html:5` («Mejoras») | **Sí** (corregido en el PR de #793) |
| Colecciones — `:36` | `/ui/colecciones` | `colecciones.html:2` | `colecciones.html:4` | Sí |
| Duplicados — `:37` | `/ui/auditoria` | `auditoria.html:2` | `auditoria.html:4` | Sí |
| Descubrir — `:38` | `/ui/descubrir` | `descubrir.html:2` | `descubrir.html:4` | Sí |
| Deseados — `:39` | `/ui/wishlist` | `wishlist.html:2` | `wishlist.html:4` | Sí |
| Estado — `:41` | `/estado` | `estado.html:2` | `estado.html:4` | Sí |
| Ajustes — `:43` | `/ui/ajustes` | `ajustes.html:2` | `ajustes.html:4` | Sí |

**Las 10 entradas coinciden** título = `h1` = menú tras el PR de #793 (Mejoras era el único desajuste:
su `<title>`/`h1` decía «Mejoras de edición»). El subtítulo conserva «Mejores ediciones…» como
descripción. El test se amplió a las 10 entradas y una prueba exige que `PAGINAS` cubra `ENTRADAS`
(verificado por mutación en QA).

### 4.3 Vistas que no son entradas de menú

| Vista | Ruta | Título/h1 | Padre | Nota |
|---|---|---|---|---|
| Pendientes por carpeta | `/ui/pendientes/carpetas` | «Pendientes por carpeta» — `carpetas.html:2,29` | «Por revisar» | Es una vista de la cola; no es una entrada de menú. Se propone añadir el padre al `<title>` y una miga, sin renombrar la vista. El CTA «Revisar por carpeta (N carpetas)» es una acción, no un nombre. |
| Pendientes sueltos | `/ui/pendientes/sueltos` | «Archivos sueltos» — `sueltos.html:2,8` | «Por revisar» | Se propone «Pendientes sueltos» (§3.1); sigue siendo una vista de la cola. |
| Sagas en orden | `/ui/arcos` | «Sagas en orden» — `arcos.html:2,5` | «Biblioteca» | `entrada_activa` ya devuelve `biblioteca` (añadido en el PR de #793). |
| Vistas de trabajo | `/ui/vistas` | «Vistas de trabajo» — `vistas_trabajo.html:2,4` | «Por revisar» | `entrada_activa` ya devuelve `revisar` (añadido en el PR de #793). |
| Exportar tebeoteca y deseados | `/ui/exportar` | «Exportar colección y deseados» — `exportar.html:2,5` | — | Sin entrada; sin marca de menú. **Deuda declarada**: se alcanza desde Estado y Ajustes; no se toca aquí. |
| Archivos no disponibles | `/ui/no-disponibles` | «Archivos no disponibles» — `no_disponibles.html:2,4` | «Estado» | No es entrada de menú; cuelga de Estado (`menu.py:59`). |

### 4.4 El nombre antiguo «Mi biblioteca» ya no está en el árbol

`grep` sobre `src/zascarr/web/templates` y `src/zascarr/web/*.py` no encuentra «Mi biblioteca» ni
«Revisión de mi biblioteca» en el árbol inspeccionado. El menú y el título son «Duplicados»
(`menu.py:37`, `auditoria.html:2,4`) y la acción es «Revisar mi biblioteca» (`auditoria.html:13`). Por
tanto:

- El problema original de #793 («Biblioteca» vs «Mi biblioteca») **ya no se reproduce con ese nombre**;
  la evidencia de `docs/BACKLOG.md:962` es histórica.
- La ambigüedad vigente es otra: **«Duplicados»** (pantalla que también registra y reescanea) frente a
  **«Revisar mi biblioteca»** (acción) y frente a **«Por revisar»** (cola de pendientes). El glosario
  la resuelve sin renombrar la pantalla ni la URL.

### 4.5 Cobertura de la prueba de navegación

`tests/test_web_navegacion.py` recorre ya las **10 entradas** en `PAGINAS` (mejoras y colecciones
incluidas) y comprueba `<title>`, `h1` y la entrada activa. Una prueba adicional exige
`{clave for clave, _ in PAGINAS} == {e.clave for e in ENTRADAS}`: si se añade una entrada al menú sin
su página, el test falla. QA lo verificó quitando Mejoras de `PAGINAS` (1 failed).

---

## 5. Criterios de aceptación de U7

| Criterio | Estado | Evidencia |
|---|---|---|
| **1. Un término por concepto** en toda la UI y la documentación, distinguiendo archivo, registro, pendiente, tebeo, serie y número. | ✅ Documentado | `CLAUDE.md` §14 (tabla de conceptos y reglas de contexto); §2 y §3 de este documento. No aplicado a plantillas: eso es #205. |
| **2. Entradas agrupadas por tarea** (Mi colección · Añadir · Sistema) o justificación escrita. | ✅ Cumplido en el árbol | `menu.py:28`; `_componentes.html:84-91`; `tests/test_web_navegacion.py:257-266`. |
| **3. El título de cada página coincide con su entrada de menú.** | ✅ Cumplido en el PR de #793 | Las 10 entradas coinciden (§4.2); `PAGINAS` cubre `ENTRADAS` y el test lo exige (`tests/test_web_navegacion.py`). |
| **4. Glosario de vocabulario de producto en `CLAUDE.md`.** | ✅ Hecho | `CLAUDE.md` §14: principio, 22 conceptos, reglas de contexto, excepciones y evidencias. |
| **5. Tabla de cambios para #205** (concepto → texto anterior → texto acordado → ubicación → prueba). | ✅ Hecho | §3.1 (rutas de #205), §3.2 (U7/otras pantallas) y §3.3 (no cambia). |
| **DoR: inventario de textos de las rutas afectadas.** | ✅ Existente | `docs/design/ui-u18/inventario-textos-y-recorte.md` (SHA `c90b8ed0`) y `vigencia-2026-11-14.md`. |
| **DoR: aprobación del PO del glosario y su versión.** | ⏳ Pendiente | Este documento y `CLAUDE.md` §14 son la versión propuesta; la aprobación se registra en #793. Las dudas están en §7. |

**Lectura para #205:** el AC5 de #205 puede citar este documento como “glosario U7, versión
2026-11-14”, pero no puede marcarlo como PASS hasta aplicar los textos de §3.1 y ejecutar las pruebas
visibles. El AC3 de U7 quedó cubierto al corregir Mejoras y ampliar `PAGINAS` en el PR de #793.

---

## 6. Riesgos

- **No renombrar entidades ni valores persistidos.** `tebeo` (`ComicTradition.TEBEO`,
  `src/zascarr/models/__init__.py:40`; `ClaseZip.TEBEO`, `:125`), `futuros` y `todos` (`WishlistPolicy`, `:192-200`),
  `publisher_id`, `vista` (`tarjetas`/`lista`), `leido` (`si`/`leyendo`/`no`), `orden`, `coleccion`,
  `story_arc_id`, `review_motivo` y `auth_mode` siguen siendo los valores de la BD, la URL y los
  contratos. Cambiar el texto visible no cambia ninguno.
- **No tocar autenticación.** El subtítulo del login ya distingue modos (`login.html:15-17`) y el error
  ya no menciona usuario en modo `password` (`auth.py:93-95`). Este glosario no cambia
  `intentar_credenciales`, el 401/429, la cookie, el rehash ni `next`; no hay ninguna fila de #205 que
  toque acceso.
- **Accesibilidad de etiquetas.** Al cambiar títulos y textos: conservar los `label for` y los `id`,
  no dejar etiquetas huérfanas, mantener `aria-label`, `aria-live` y el orden de tabulación. El cambio
  «Archivos sueltos → Pendientes sueltos» afecta al `h1` y al `<title>`, no a la estructura de
  navegación; el cambio «Pendientes por carpeta» añade miga, no un `<nav>` nuevo.
- **Pruebas de texto visible, no `grep` global.** El HTML contiene `value="tebeo"`, URLs
  `tradition=tebeo`, comentarios con «JSON» y `res.json()` en un `<script>`; una búsqueda global da
  falsos positivos. Usar el patrón de `tests/test_pendientes.py:212-215` (quita etiquetas y
  comentarios) o acotar al bloque visible.
- **«Tebeo» es ambiguo por diseño.** Es la tradición (`Tebeo español`), el objeto («El mismo tebeo, dos
  veces») y el valor interno (`tebeo`). Nunca sustituir mecánicamente: una regla global rompería la
  etiqueta de tradición o el `value` del filtro.
- **«Registro» es ambiguo.** Es la fila (`carpetas.html:99-100`) y el proceso de registrar la
  biblioteca (`_auditoria_registro.html`). El glosario reserva «registro» para la fila y «registrar»
  para la acción; no sustituir todas las apariciones.
- **«Colección» tiene tres sentidos.** El grupo con nombre (`Collection`), el conjunto entero
  («tu colección») y el estado de completitud («Estado de la colección»). El glosario reserva
  «colección» para el grupo; los otros dos se cambian o se registran como deuda (§3.2 y §7).
- **«Catálogo» y «arco» son deuda fuera de #205.** Auditoría (V11) y Sagas/Ajustes no están en las
  cuatro rutas de #205; se registran para el PR de código o la historia correspondiente, no se
  reescriben aquí.
- **El glosario no es código.** Este documento no aplica los textos, no crea migraciones y no toca la
  BD. #205 sigue siendo quien aplica y prueba; la fusión y el despliegue son decisiones separadas.

---

## 7. Dudas para el PO

**Resuelta por el PR de #793:** «Mejoras» es el nombre de pantalla (menú, `<title>` y `h1`) y el
subtítulo conserva «Mejores ediciones…». No se alarga la entrada del menú.

1. **Pendientes sueltos.** ¿Se adopta «Pendientes sueltos» en lugar de «Archivos sueltos»? Es coherente
   con «suelto = pendiente sin carpeta», pero cambia una etiqueta que ya existe y un enlace de la
   pantalla de Por revisar.
2. **Estado de la serie.** ¿Se cambia «Estado de la colección» por «Estado de la serie» en el filtro de
   Biblioteca y en la ficha? Evita la colisión con «Colecciones», pero puede confundirse con el estado
   de publicación de la serie. Alternativa: «Completitud».
3. **Alcance de #205.** El issue nombra acceso, Biblioteca, Por revisar y Estado. ¿Se incluyen en #205
   los cambios de Inicio («Tu tebeoteca ahora», «pendientes sin clasificar») o se dejan para una
   historia de Inicio? Sin esa decisión, §3.2 queda registrado pero no aplicado.
4. **Duplicados.** ¿Se mantiene «Duplicados» como nombre de menú y pantalla (URL `/ui/auditoria`
   intacta) y «Revisar mi biblioteca» como acción? Es lo que hay hoy; renombrar la pantalla a
   «Revisión» obligaría a tocar menú y pruebas, y no es necesario para el glosario.
5. **Contador «Tebeos registrados».** ¿La unidad son archivos (`File`), ejemplares o números? Hoy cuenta
   filas; el glosario define «tebeo» como ejemplar y «número» como unidad bibliográfica.

---

## 8. Límites de la evidencia

- El **glosario y la tabla** son análisis documental del árbol `0816bd8e`; el inventario de #205 es de
  `c90b8ed0`. El **PR de #793** añade además el arreglo de navegación (`mejoras.html`, `menu.py`,
  `test_web_navegacion.py`): ahí sí se ejecutó la suite completa (**6936 passed, 2282 skipped**), ruff
  y revisión de QA con mutación de la prueba de cobertura.
- Las líneas citadas son las del árbol indicado; si #205 se implementa sobre otro SHA, hay que
  revisarlas antes de aplicar.
- **NOT RUN:** navegador real, lector de pantalla y Pi. Las pruebas de §3 son propuestas de prueba, no
  resultados de sesiones.
- Los cambios de texto de #205 **no** están aplicados: este PR no toca sus plantillas.

---

## 9. Resumen de 8 líneas

- Se decide que **biblioteca** es la pantalla, **tebeoteca** el conjunto entero y **colección** el grupo con nombre; «catálogo» queda fuera de la superficie.
- Se decide que **Por revisar** es la cola, **Duplicados** la revisión del disco y «Revisar mi biblioteca» su acción; «Mi biblioteca» y «Revisión de mi biblioteca» no son nombres de pantalla.
- Se decide que **pendiente** es un estado, **archivo** el fichero, **registro** la fila y **suelto** un pendiente sin carpeta; no se sustituyen entre sí.
- Se decide que **tebeo** es el objeto o ejemplar y «Tebeo español» solo la tradición; **número** es la unidad bibliográfica y no se cuenta con «tebeos».
- Se decide que **saga** es la superficie y «arco» el código; **editorial** es `Publisher` y **sello** es `Imprint`.
- La tabla de #205 queda en §3.1; los cambios de navegación y de otras pantallas, en §3.2; lo que no cambia, en §3.3.
- Los tres grupos del menú ya existen (`menu.py:28`); las 10 entradas coinciden título = `h1` = menú y la prueba de navegación las cubre todas con una guarda `PAGINAS == ENTRADAS`.
- Dudas para el PO: «Pendientes sueltos» vs «Archivos sueltos», «Estado de la serie» vs «Estado de la colección», alcance de Inicio en #205, si «Duplicados» se mantiene y la unidad del contador «Tebeos registrados».
