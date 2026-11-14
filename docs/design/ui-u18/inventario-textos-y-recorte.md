# U18 — Inventario de textos y recorte independiente del glosario


> **Nota (2026-11-14):** este informe originó la tarjeta **#789 BL-U18b** (recorte de erratas
> independientes del glosario). El PR de #789 implementa H1–H4/R1–R4 y **no cierra #205**: la
> unificación terminológica sigue bloqueada por U7.

**Fecha:** 2026-11-14
**Rama y worktree:** `docs/205-refinamiento`, `.squad/wt-205`
**SHA inspeccionado:** `c90b8ed0b27a2591bdf5c6d07e40a1bb2c922048`
**Issue:** #205 (BL-U18, P2). Antecedente inmediato: #270 (BL-U18a, cerrado).
**Rol:** SPEC/UX. Este documento no modifica código ni plantillas, no crea el glosario U7 y no cierra #205.
**Estado:** refinamiento. No es implementación, ni evidencia de navegador, ni autorización de despliegue.

---

## 0. Límites y método

Este documento es un análisis **estático** del árbol de `c90b8ed0`. No se ha ejecutado la suite, no se ha abierto
un navegador y no se ha tocado la Pi. Las líneas citadas son las del SHA indicado; si el código cambia, el
inventario debe revisarse contra el SHA nuevo antes de implementar.

No se ha modificado ninguna plantilla, router, prueba ni documento de decisiones. El único artefacto de este
trabajo es este fichero. Tampoco se ha creado la tarjeta de U7 ni la del posible recorte: eso corresponde a
quien coordina y al PO.

---

## 1. Estado de U7: no hay glosario que citar

### 1.1 Respuesta corta

**No existe el glosario de vocabulario de producto en `CLAUDE.md`.** No hay una tarjeta de U7, no hay una PR de
U7 y no hay un documento con versión y aprobación que se pueda citar. La única fuente disponible es la
**definición de U7 en `docs/BACKLOG.md`**, que sigue siendo un requisito, no un glosario aprobado.

Por tanto, **la unificación terminológica sigue bloqueada**. No se puede declarar cumplido el criterio 5 de
#205 ni cerrar su DoR con el estado actual.

### 1.2 Comprobaciones realizadas

| Qué se buscó | Comando o comprobación | Resultado |
|---|---|---|
| Glosario en `CLAUDE.md` | `grep -n -i "glosario" CLAUDE.md` | Sin coincidencias (exit 1). La palabra «vocabulario» solo aparece en `CLAUDE.md:362`, dentro de §13, referida al vocabulario del *benchmark*, no al de producto. |
| Glosario entre los documentos vivos | `CLAUDE.md:319-333` (§11) | La tabla de documentos vivos no contiene ningún glosario; además, no existe un directorio `docs/design/ui-u7/`. |
| Requisito de U7 | `docs/BACKLOG.md:959-968` | U7 pide «un término por concepto» y, en el criterio 4 (`:967`), un «Glosario de vocabulario de producto en `CLAUDE.md`». También figura en la tabla de la épica (`:867`). |
| Tarjeta de U7 | `gh issue list --state all --search "U7" --json number,title,state` | Devuelve #205, #270 y #196. Ninguna es U7: son U18, U18a y la feature de auditoría. |
| Tarjeta por «glosario» | `gh issue list --state all --search "glosario" --json number,title,state` | Los mismos tres resultados. No hay una tarjeta dedicada. |
| Historias de la feature #196 | `gh issue view 196` | Enumera las historias #197–#208; no incluye U7. |
| PR de U7 | `gh pr list --state all --search "U7" --json number,title,state` | `[]`. Las coincidencias por «glosario» o «vocabulario» son de otras fichas (por ejemplo, #554, #180 o #386), no del glosario de producto. |
| Ficheros de U7 | `ls docs/design \| grep -i "u7\|glos"` y búsqueda de `*glos*` o `*u7*` bajo `docs/` | Sin resultados. |

### 1.3 Qué se puede citar y qué no

**Se puede citar** la definición de U7 en `docs/BACKLOG.md:959-968`, con su criterio 4 en `:967`, y la nota del
2026-10-21 en `docs/BACKLOG.md:1062`, que dice que #205 sigue bloqueada por U7. Es una **definición de
backlog**, sin versión, sin fecha de aprobación y sin tabla de conceptos.

**No se puede citar** un documento aprobado, una versión del glosario, una tabla de «concepto → etiqueta por
contexto» ni una decisión del PO sobre los términos. Tampoco existe una tarjeta de U7 en el tablero: si el PO
decide hacer U7 primero, hay que **crear esa tarjeta** con su propio alcance y su propio DoD.

### 1.4 Los otros «glosarios» del repositorio no sirven para U7

Hay secciones llamadas «Glosario» en especificaciones concretas: `docs/design/especificacion-BL-OPS1.md:92`,
`especificacion-BL-OPS2.md:79` y `especificacion-BL-OPS3.md:54`; y un «Glosario plegado» en
`ui-BL-INF1-ficha-numero.md:352`. Son glosarios **técnicos de una ficha** (protocolo del auxiliar, contraseña
en vigor, papeles de una edición), no
el vocabulario transversal de producto que U7 exige en `CLAUDE.md`. No sustituyen a U7 ni se pueden usar para
definir «archivo», «registro», «pendiente» o «tebeo» en toda la UI.

### 1.5 Consecuencia para #205

El DoR de #205 pide: «Documento/version de U7 identificado y conceptos revisados, o recorte independiente
aprobado por el responsable». Hoy no se cumple ninguna de las dos ramas: no hay documento de U7 y el recorte
independiente **no está aprobado** (este documento solo lo propone).

El criterio 5 de #205 («Terminología trazable») y su DoD («Tabla de cambios y referencia al glosario vigente»)
dependen de U7. Sin glosario no se puede acreditar que «archivo», «registro», «pendiente» y «tebeo» signifiquen
cosas distintas o la misma, ni que la etiqueta de cada contexto sea la acordada.

---

## 2. Vigencia de la auditoría y de #270 en `c90b8ed0`

La auditoría `docs/design/auditoria-ui-2026-10-15.md` describe `main` en `a5369ef` (2026-10-15), no el estado
actual. Esta es la reclasificación de sus hallazgos de lenguaje en el SHA inspeccionado.

| Pieza histórica | Estado en `c90b8ed0` | Evidencia |
|---|---|---|
| m1: el login dice «Usuario o contraseña incorrectos» con un solo campo | **Corregido** para el modo `password`; el modo `user_password` conserva el mensaje con usuario. | `src/zascarr/web/auth.py:93-95`; cambio `8164781a`, fusionado en `a2721722` (ambos ancestros de `c90b8ed0`); pruebas en `tests/test_web_auth.py:163-180`. |
| m4: la tarjeta de Biblioteca muestra el valor interno `tebeo` | **Corregido**: se pinta la etiqueta «Tebeo español», no el valor. | `src/zascarr/web/library.py:60-68` y `:88-99`; `_rejilla_biblioteca.html:126,154`. En `a5369ef`, `_rejilla_biblioteca.html:18` imprimía `series.tradition.value`. |
| m4: «Todas las editoriales» es un `select` sin opciones | **Corregido en página completa**; **queda un residuo en el fragmento HTMX** (ver §2.1). | `_filtros_panel_campos.html:11`; `tests/test_web_library.py:133-153`; #270 fusionado en #273. |
| M4: el subtítulo de Estado habla de «JSON crudo» | **Corregido**: el subtítulo es llano y no contiene «JSON». | `estado.html:5`; cambio `518cdfd1` (ancestro de `c90b8ed0`). Solo quedan `res.json()` en `estado.html:265` y la frase «JSON crudo» en el docstring de `estado.py:3`, que no son texto visible. |
| m5: vocabulario inestable («Por revisar» / «Pendientes por carpeta» / «registros» / «archivos» / «tebeos») | **Sin resolver**. Es el núcleo de U18 que depende de U7. | `pendientes.html:5`; `carpetas.html:2,29,92,99`; `_pendientes_rango.html:4`; auditoría `docs/design/auditoria-ui-2026-10-15.md:151`. |
| Texto del modo con usuario | **Pendiente**: el formulario pide usuario y contraseña, pero el subtítulo solo menciona la contraseña. | `login.html:15` frente a `login.html:18-21`; la prueba `tests/test_web_auth.py:119-124` solo comprueba que aparece el campo `username`. |
| Valor interno reservado en la ficha de serie | **Pendiente**: en un caso defensivo se pinta `futuros` o `todos` en crudo. | `_politica_serie.html:29-34`; la etiqueta ya existe en `_politica_serie.html:50` y en `series.py:467`. |
| Hallazgo propio: mensaje «La presentación pedida no existe» | **Pendiente, baja prioridad**: aparece solo ante una URL de vista manipulada. | `src/zascarr/web/library.py:201`; prueba que fija el texto en `tests/test_web_library.py:633-637`. |

### 2.1 El residuo del `select` de editorial (regresión de #628)

#270 cerró el caso de la página completa, pero #628 movió los campos a un parcial y añadió una condición nueva:

- `_filtros_panel_campos.html:11` renderiza el bloque si `publishers or es_fragmento`.
- `_rejilla_biblioteca.html:14-19` incluye ese parcial en **toda** respuesta de fragmento, con `hx-swap-oob`.
- `library.py:568` pone `ctx["es_fragmento"] = True` en `_respuesta_fragmento`.

Con cero editoriales y sin filtro de editorial activo, una respuesta HTMX (por ejemplo, cambiar la tradición)
vuelve a pintar el `select` con la única opción «Todas las editoriales», sin opciones útiles. La página completa
sí lo oculta porque `es_fragmento` no está definido allí. La prueba existente solo cubre la página completa
(`tests/test_web_library.py:133-153`); no hay prueba del fragmento.

Esto no es un fallo de vocabulario: es una regresión de comportamiento visible que #205 puede corregir sin U7.
Se incluye en el recorte como cambio independiente (R2).

### 2.2 El triángulo de vocabulario que U7 debe resolver

No son sinónimos mecánicos. El contrato de #205 lo prohíbe expresamente: «Archivo, registro, estado pendiente y
tebeo no se sustituyen mecánicamente unos por otros». Lo que falta es la definición de qué representa cada uno
y qué etiqueta le corresponde en cada contexto.

| Concepto | Texto A | Texto B | Texto C | Lo que falta |
|---|---|---|---|---|
| La cola de revisión | «Archivos que el sistema no supo clasificar solo» (`pendientes.html:5`) | «Mostrando X–Y de N pendientes» (`_pendientes_rango.html:4`) | «N registros visibles» (`carpetas.html:92`) | Definir si «archivo», «registro» y «pendiente» son el mismo concepto o tres; no sustituir uno por otro sin definición. |
| La vista por carpetas | Entrada de menú «Por revisar» (`menu.py:32`) | Título «Pendientes por carpeta» (`carpetas.html:2,29`) | CTA «Revisar por carpeta (N carpetas)» (`_pendientes_carpetas_enlace.html:3`) | Decidir el nombre de la vista y si el título debe coincidir con el menú (criterio 3 de U7). |
| La unidad que se cuenta | «archivos» (`pendientes.html:5`) | «registros» (`carpetas.html:195`) | «tebeos» en otras rutas (auditoría m5, `:151`) | Definir la unidad de conteo y el término de cada contexto; no convertir «tebeo» en sinónimo de «registro». |

---

## 3. Inventario de textos de las rutas afectadas

### 3.1 Criterio de las columnas

- **Concepto (dominio):** qué representa el texto, no la pantalla.
- **¿Interno?:** «sí» solo cuando lo visible es un valor o código que también vive en la BD, en la URL o en el
  contrato (`tebeo`, `futuros`, `todos`, una fuente cruda). La jerga como «base de datos» es «no», aunque puede
  ser `técnico justificado`.
- **Clasificación:** `independiente` (se puede decidir sin glosario), `depende de U7` (cambiar el término de un
  concepto) o `técnico justificado` (no se toca: detalle de diagnóstico o formato).
- Las plantillas con variables se citan por la línea que las renderiza, no por el valor de los datos.

### 3.2 Acceso

| ID | Concepto (dominio) | Texto actual visible | Ubicación | ¿Interno? | Propuesta de texto llano | Clasificación |
|---|---|---|---|---|---|---|
| A1 | Acceso | «Introduce tu contraseña para continuar.» | `login.html:15` | No | En modo con usuario: «Introduce tu usuario y contraseña para continuar.»; en modo solo contraseña, mantener el actual. | `independiente` |
| A2 | Acceso / campo | «Usuario» | `login.html:19` | No | Mantener; solo se pinta si `pide_usuario`. No revela si la cuenta existe. | `independiente` |
| A3 | Acceso / error | «Contraseña incorrecta.» en modo `password`; «Usuario o contraseña incorrectos.» en `user_password` | `auth.py:93-95` | No | Mantener; ya distingue modos y no cambia el estado HTTP ni la cookie. | `independiente` (guarda) |
| A4 | Acceso / límite | «Demasiados intentos a la vez. Espera unos segundos y vuelve a probar.» | `auth.py:87` | No | Mantener. | `independiente` (guarda) |

### 3.3 Biblioteca

| ID | Concepto (dominio) | Texto actual visible | Ubicación | ¿Interno? | Propuesta de texto llano | Clasificación |
|---|---|---|---|---|---|---|
| B1 | Tradición | «Tebeo español» | `library.py:63`; `_rejilla_biblioteca.html:126,154` | No | Mantener «Tebeo español»; el valor `tebeo` sigue en `value`, en la URL y en la BD. El término exacto lo confirma U7. | `depende de U7` |
| B2 | Editorial / filtro | «Todas las editoriales» (opción del `select`) | `_filtros_panel_campos.html:11,15` | No | No renderizar el bloque si no hay editoriales y no hay `publisher_id` activo; si hay filtro activo, mostrar el `select` con la opción seleccionada. | `independiente` |
| B3 | Lectura | «Toda la lectura», «Con leídos», «Leyendo», «Sin leídos» | `_filtros_panel_campos.html:26-31` | No | Mantener hasta U7; si U7 lo autoriza, valorar «Con algún número leído» y «Sin números leídos». No cambiar los valores `si`, `leyendo`, `no`. | `depende de U7` |
| B4 | Número | «Números» y «X de Y números» | `_rejilla_biblioteca.html:106,146` | No | Mantener «Números»; U7 decide la etiqueta del concepto «número». | `depende de U7` |
| B5 | Biblioteca vacía | «Añade lo que tengas en el disco desde Por revisar.» | `_rejilla_biblioteca.html:95` | No | Mantener; es llano y no introduce un término nuevo. | `independiente` (guarda) |
| B6 | Vista / error de URL | «La presentación pedida no existe; se muestran tarjetas.» | `library.py:201` | No | «La vista pedida no existe; se muestran tarjetas.» | `independiente` |
| B7 | Orden | «A-Z», «Z-A», «Recientes», «Antiguas», «Añadidas» | `library.py:524-526` | No | Mantener. | `independiente` (guarda) |
| B8 | Tradición / columna | «Tradición» | `_rejilla_biblioteca.html:105` | No | Mantener; U7 decide la etiqueta del concepto. | `depende de U7` |

### 3.4 Por revisar y vista por carpetas

| ID | Concepto (dominio) | Texto actual visible | Ubicación | ¿Interno? | Propuesta de texto llano | Clasificación |
|---|---|---|---|---|---|---|
| C1 | Cola de revisión | «Archivos que el sistema no supo clasificar solo. Busca la serie correcta y confirma el número, o ignóralos si no pertenecen a tu colección.» | `pendientes.html:5` | No | No cambiar «archivos» ni «clasificar» hasta U7; U7 decide si el sujeto es «archivos», «registros» o «pendientes». | `depende de U7` |
| C2 | Cola / recuento | «Mostrando X–Y de N pendientes.» | `_pendientes_rango.html:4` | No | No cambiar «pendientes»; U7 decide si es la etiqueta de la cola o solo un estado. | `depende de U7` |
| C3 | Vista por carpetas | «Pendientes por carpeta» (título de página y `h1`) | `carpetas.html:2,29` | No | No renombrar; U7 decide si el título debe coincidir con el menú «Por revisar» o con el CTA «Revisar por carpeta». | `depende de U7` |
| C4 | Carpeta / resumen | «N por revisar: N en N carpetas + N sueltos. N con serie sugerida, aparte. N registros visibles.» | `carpetas.html:92` | No | No tocar la frase; es el ejemplo más claro de la mezcla que U7 debe resolver. | `depende de U7` |
| C5 | Registro frente a archivo | «Son registros pendientes de verificar, no archivos confirmados.» | `carpetas.html:99` | No | No tocar; esta frase define exactamente la diferencia que U7 debe fijar. | `depende de U7` |
| C6 | Procedencia / base de datos | «Esta pantalla lee la base de datos y no comprueba el disco: un registro puede apuntar a un archivo que ya no esté donde se anotó.» | `carpetas.html:100` | No (jerga) | No tocar en este recorte: va dentro de «¿De dónde salen estos datos?» y es una explicación de procedencia; si se aborda, que sea en U21/#231, no aquí. | `técnico justificado` |
| C7 | Operación / organizar | «Organizar mueve y renombra el archivo. Antes verás la carpeta y el nombre final.» | `_tarjeta_pendiente.html:41` | No | No cambiar «Organizar» ni «archivo»; son operaciones y entidades que U7 debe definir. | `depende de U7` |
| C8 | Operación / vincular | «Vincular no mueve ni renombra: solo funciona si esa publicación ya existe en la serie.» | `_tarjeta_pendiente.html:29` | No | No cambiar «Vincular» ni «publicación»; U7 decide la etiqueta de la operación y del concepto. | `depende de U7` |
| C9 | Operación / ignorar | «¿Ignorar este archivo? No volverá a aparecer aquí.» | `_tarjeta_pendiente.html:63` | No | No cambiar «Ignorar» ni «archivo»; U7. | `depende de U7` |
| C10 | Archivos sueltos | «Ver los archivos sueltos»; «Archivos sueltos» | `pendientes.html:16`; `sueltos.html:2,8` | No | No cambiar «sueltos»; el kit de U10 lo mide como hipótesis abierta (F4) y U7 debe decidirlo. | `depende de U7` |
| C11 | Vistas de trabajo | «Ver las vistas de trabajo» | `pendientes.html:18` | No | No cambiar «vistas de trabajo»; el kit de U10 lo mide como hipótesis abierta (F4) y U7 debe decidirlo. | `depende de U7` |
| C12 | Recuento de carpetas | «Revisar por carpeta (N carpetas)» | `_pendientes_carpetas_enlace.html:3` | No | Mantener; cuenta carpetas, no archivos, y usa un verbo claro. Es un buen texto de referencia para U7. | `independiente` (guarda) |
| C13 | Estado de la carpeta | «Serie sugerida, falta confirmar número y edición»; «Mezcla: archivos sin serie y con serie sugerida…» | `revision_carpetas.py:50-52`; `carpetas.html:156` | No | No tocar; U7 decide «número», «edición» y la relación entre «archivo» y «serie sugerida». | `depende de U7` |

### 3.5 Estado, búsqueda automática y piezas compartidas

| ID | Concepto (dominio) | Texto actual visible | Ubicación | ¿Interno? | Propuesta de texto llano | Clasificación |
|---|---|---|---|---|---|---|
| D1 | Estado / subtítulo | «Cómo están las piezas de las que depende ZascArr. Se actualiza sola cada 10 segundos.» | `estado.html:5` | No | Mantener; ya no contiene «JSON». | `independiente` (guarda) |
| D2 | Estado / semáforo | «Todo bien», «Atención», «Error», «ZascArr no responde» | `estado.html:193-196` | No | Mantener. | `independiente` (guarda) |
| D3 | Estado / VPN | «Sin datos» frente a «No protege» | `estado.html:149` | No | Mantener; la distinción entre «no sabemos» y «no protege» es deliberada (U6). | `independiente` (guarda) |
| D4 | Estado / diagnóstico | Texto crudo del aviso dentro de «Detalle técnico» | `estado.html:243`; `estado.html:155-160` | Sí | No tocar en U18: el detalle crudo debe seguir disponible, plegado. Los comandos `sudo` de la fila de base de datos son deuda de V9/U6, no de este recorte. | `técnico justificado` |
| D5 | Estado / exportación | «Descargar colección y deseados (CSV)» | `estado.html:115` | No (formato) | Mantener; «CSV» es un formato, no un término interno de dominio. | `técnico justificado` |
| D6 | Búsqueda automática | «La política efectiva es «X», aunque la guardada sea «Y».» | `_politica_serie.html:49-50` | No (jerga de producto) | No tocar; U7 decide «política» frente a «búsqueda automática». | `depende de U7` |
| D7 | Búsqueda automática / valor reservado | «{{ politica_actual.value }} — reservado, todavía no hace nada» | `_politica_serie.html:29-34` | Sí (`futuros`, `todos`) | «{{ politica_actual_etiqueta }} — valor guardado, todavía no hace nada». El `value` del `option` sigue siendo el valor persistido. | `independiente` |
| D8 | Búsqueda automática / fuente | «Fuente registrada: <code>{{ v.fuente }}</code>» dentro de «Ver el dato técnico» | `_politica_serie.html:98-102` | Sí | No tocar; es un detalle técnico plegado. | `técnico justificado` |
| D9 | Búsqueda automática / retirada | «Se conserva como registro, no se borra.» | `_politica_serie.html:128-135` | No | No tocar; U7 decide «registro» frente a «archivo» y «pendiente». | `depende de U7` |

### 3.6 Resumen de clasificación

| Clasificación | Nº de filas | Qué significa para el recorte |
|---|---:|---|
| `independiente` | 13 | 4 cambios de texto/visibilidad (A1, B2, B6, D7) y 9 guardas que no se reescriben. |
| `depende de U7` | 17 | No se toca ningún término hasta que exista el glosario. |
| `técnico justificado` | 4 | Se conserva: diagnóstico plegado, formato o explicación de procedencia. |
| **Total** | **34** | Inventario acotado a las rutas de #205; no incluye toda la UI. |

---

## 4. Recorte propuesto (solo si el PO lo autoriza)

### 4.1 Cambios independientes: lista cerrada

Son cuatro cambios pequeños. Ninguno renombra una entidad del dominio, ninguno cambia valores persistidos o
enviados y ninguno toca la lógica de autenticación.

1. **R1 — Acceso: subtítulo según el modo.**
   - Dónde: `login.html:15`.
   - Hoy: «Introduce tu contraseña para continuar.» también cuando el formulario pide usuario.
   - Propuesta: si `pide_usuario`, «Introduce tu usuario y contraseña para continuar.»; si no, mantener el texto
     actual.
   - Por qué es independiente: no cambia el modo, ni el estado HTTP, ni la cookie, ni revela si la cuenta existe;
     solo hace que el texto coincida con los campos que se ven.
   - Prueba: `GET /login` en `password` y en `user_password`; además del texto, comprobar que en `password` no
     aparece la palabra «Usuario» y que el mensaje de error sigue siendo el de `auth.py:93-95`.

2. **R2 — Biblioteca: no renderizar el `select` de editorial vacío en el fragmento.**
   - Dónde: `_filtros_panel_campos.html:11`.
   - Hoy: `{% if publishers or es_fragmento %}` hace que cualquier respuesta HTMX incluya el `select` aunque no
     haya editoriales ni filtro activo.
   - Propuesta: `{% if publishers or filtros.publisher_id %}`. Si hay editoriales, se muestran; si hay un filtro
     de editorial activo aunque la lista esté vacía, se conserva el `select` con la opción seleccionada
     (`publisher_conocido`); si no hay ninguna de las dos cosas, el bloque no se pinta.
   - Por qué es independiente: es la misma condición de #270, aplicada también al fragmento; no cambia el nombre
     de nada.
   - Prueba: página completa sin editoriales (ya existe, `tests/test_web_library.py:133-153`); fragmento
     `/ui/biblioteca/resultados` sin editoriales y sin `publisher_id` (nuevo); fragmento con `publisher_id`
     activo (nuevo, debe conservar el `select` y la opción seleccionada); página completa con editoriales (ya
     existe).

3. **R3 — Búsqueda automática: no pintar el valor reservado en crudo.**
   - Dónde: `_politica_serie.html:29-34`.
   - Hoy: en el caso defensivo de una BD antigua con `futuros` o `todos`, se lee «futuros — reservado, todavía no
     hace nada».
   - Propuesta: usar la etiqueta que ya existe en el contexto, «{{ politica_actual_etiqueta }} — valor guardado,
     todavía no hace nada». Mantener `value="{{ politica_actual.value }}"` en el `option`: el valor persistido no
     cambia, solo el texto visible.
   - Por qué es independiente: no decide ningún término nuevo; reutiliza `politica_actual_etiqueta`
     (`series.py:467`), que ya se usa en `_politica_serie.html:50`.
   - Prueba: una serie con `WishlistPolicy.FUTURE` y otra con `WishlistPolicy.ALL`; el texto visible no contiene
     `futuros` ni `todos`, y sí la etiqueta. La prueba existente
     `tests/test_web_series.py:291-306` solo cubre el estado normal, no el valor reservado guardado.

4. **R4 — Biblioteca: «presentación» → «vista» en el aviso de URL manipulada.**
   - Dónde: `library.py:201`.
   - Hoy: «La presentación pedida no existe; se muestran tarjetas.»
   - Propuesta: «La vista pedida no existe; se muestran tarjetas.»
   - Por qué es independiente: «vista» ya es la palabra que usa el control (`aria-label="Vista de la
     biblioteca"`, `_control_vista.html:1`) y el parámetro `vista`; no es un término de dominio nuevo.
   - Prueba: actualizar `tests/test_web_library.py:633-637`; `GET /ui/biblioteca?vista=inventada` debe mostrar el
     texto nuevo y seguir pintando la rejilla de tarjetas.

### 4.2 Guardas sin cambio (se prueban, no se reescriben)

Estas filas del inventario son `independiente` porque no necesitan glosario, pero **no proponen un texto nuevo**:
se conservan y se cubren con pruebas para que un cambio futuro no las rompa.

- A2, A3 y A4: la etiqueta «Usuario» del modo con usuario, los dos mensajes de acceso y el límite de intentos.
- B5 y B7: el vacío de Biblioteca y las etiquetas de orden.
- C12: «Revisar por carpeta (N carpetas)».
- D1, D2 y D3: el subtítulo de Estado, los rótulos del semáforo y la distinción «Sin datos» / «No protege».

B1 y B4 también se conservan, pero no son guardas `independiente`: su término («Tebeo español», «Números»)
depende de U7 y por eso aparecen en la lista de §4.3.

### 4.3 Lo que NO se toca por depender de U7

No se renombra nada de esta lista en el recorte:

- **Los términos de la cola:** «archivos», «registros», «pendientes», «sueltos», «tebeos». No se sustituyen
  mecánicamente; U7 debe definir qué representa cada uno y en qué contexto se usa.
- **El título de la vista por carpetas:** «Pendientes por carpeta», sus enlaces de vuelta
  (`asistente_alta.html:10`, `asistente_carpeta.html:7`, `contexto_declarado.html:4`, entre otros) y su relación
  con el menú «Por revisar».
- **Las operaciones:** «Vincular», «Organizar», «Asignar» e «Ignorar», con sus notas de efecto.
- **Las etiquetas de estado de carpeta:** «Serie sugerida, falta confirmar número y edición», «Mezcla…», «por
  confirmar», «en conflicto».
- **«Tradición» y «Tebeo español»** como término definitivo: la etiqueta actual es correcta y legible, pero el
  término acordado depende de U7.
- **«Lectura» / «leídos» y «Números»**: no se cambian sus etiquetas ni sus valores (`si`, `leyendo`, `no`).
- **«Política efectiva»** y «registro» en la ficha de serie: son vocabulario de producto que U7 debe fijar.
- **Cualquier entidad, estado, operación, URL, clave de menú, columna o valor de BD.** Tampoco se crea el
  glosario en `CLAUDE.md` desde #205: eso es U7.

### 4.4 Lo que este recorte no cierra

- **No cierra #205.** Faltan los criterios de terminología (5) y la referencia al glosario vigente del DoD.
- **No cierra U7.** No crea el glosario, no fija términos y no sustituye la decisión del PO.
- **No reabre #270.** #270 ya está cerrado y fusionado; R2 corrige una regresión posterior de #628, no un
  incumplimiento de #270.
- **No autoriza despliegue ni validación en la Pi.** Eso sigue siendo una decisión separada.
- **No crea la tarjeta del recorte.** Este documento solo la propone; la tarjeta la crea quien coordina.

---

## 5. Riesgos y criterios de implementación

### 5.1 Valores que se conservan

| Valor | Dónde vive | Regla |
|---|---|---|
| `tebeo` | `ComicTradition.TEBEO` (`models/__init__.py:40`), `library.py:63`, `_filtros_panel_campos.html:7` | Sigue siendo el valor de BD y de la URL `tradition=tebeo`; solo se cambia la etiqueta visible si U7 lo decide. |
| `futuros`, `todos` | `WishlistPolicy` (`models/__init__.py:199-200`), `_politica_serie.html:29-34` | Siguen siendo los valores del `option` y de la BD; R3 solo cambia el texto visible del caso defensivo. |
| `publisher_id` | `_filtros_panel_campos.html:14,17` | Es un UUID; el nombre visible es `p.name`. No se toca. |
| `vista` | `tarjetas` / `lista`; `_control_vista.html:1-20`; `library.py` | No se renombran los valores ni el parámetro. |
| `leido` | `si` / `leyendo` / `no`; `_filtros_panel_campos.html:29-31` | No se renombran. |
| `orden` | `titulo`, `titulo_desc`, `anio_desc`, `anio_asc`, `reciente`; `library.py:524-526` | No se renombran. |
| `quitar` | Lista cerrada en `_rejilla_biblioteca.html:9-13` | No se amplía ni se cambia. |
| `auth_mode` | `password` / `user_password`; `auth.py:60,86,92` | No se toca. R1 solo lee `pide_usuario`. |
| `next` | `login.html:17`; `auth.py` | No se toca. |
| `review_motivo` | `pendientes.py:112`; `services/review.py:55` | Es metadata; no se reescribe desde la plantilla. |

Ningún cambio de este recorte modifica el esquema, las migraciones, los contratos de API ni los parámetros de
las rutas. Las pruebas deben comprobar que los valores siguen ahí (`value="tebeo"`, `value="futuros"`) y que lo
que cambia es solo el texto visible.

### 5.2 Autenticación: solo texto

R1 no cambia `intentar_credenciales`, ni el estado 401/429, ni la cookie, ni el rehash, ni el manejo de `next`.
La condición debe depender de `settings.auth_mode` / `pide_usuario`, **nunca** del usuario enviado. En modo
`password` el texto no debe mencionar «usuario»; en `user_password` puede mencionarlo porque el campo existe.
No se añade ninguna pista sobre si una cuenta existe: el mensaje de error sigue siendo el mismo para cualquier
usuario.

### 5.3 Accesibilidad

- Mantener los `label for` y los `id` de los campos; R2 solo elimina un `select` que no tenía opciones útiles, no
  deja un `label` huérfano ni un control invisible enfocable.
- Cuando el `select` de editorial se muestra con un filtro activo y la lista está vacía, conservar su nombre
  accesible («Editorial») y la opción seleccionada (`publisher_conocido`).
- No cambiar `aria-live`, `aria-controls`, `aria-label` ni el orden de tabulación de los controles que se
  conservan.
- R1 no cambia las etiquetas «Usuario» y «Contraseña»; el foco inicial sigue siendo el campo correcto.
- R3 y R4 no afectan a nombres accesibles ni a la navegación por teclado.

### 5.4 Cómo se prueba el texto visible

La regla del criterio 7 de #205 es inspeccionar **texto visible en rutas y fragmentos**, no hacer búsquedas
indiscriminadas sobre el HTML, el código o los datos internos. Hay tres falsos positivos que una prueba ingenua
encontraría siempre:

- `estado.html:265` contiene `res.json()` y `estado.py:3` contiene «JSON crudo» en un docstring: no son texto
  visible.
- `_tarjeta_pendiente.html:3` menciona «JSON» en un comentario de plantilla.
- El HTML renderizado de `_filtros_panel_campos.html:7` contiene `value="tebeo"` y las URLs contienen
  `tradition=tebeo`: una búsqueda de «tebeo» sobre el HTML siempre acertaría aunque la etiqueta visible sea
  «Tebeo español».

Por eso las pruebas deben extraer el texto visible (por ejemplo, el contenido de `main` sin `<script>`, o el
bloque `#rejilla` / `#politica-serie`) y buscar ahí. Como referencia de patrón ya existente:
`tests/test_web_series.py:306` hace un recorte del bloque y quita etiquetas antes de buscar `futuros`.

Pruebas concretas propuestas:

| Cambio | Fichero de prueba | Qué se comprueba |
|---|---|---|
| R1 | `tests/test_web_auth.py` (ampliar `:119-124`) | `GET /login` en ambos modos: el subtítulo coincide con los campos; en `password` no aparece «Usuario»; el error sigue distinguiendo modos (`:163-180`). |
| R2 | `tests/test_web_library.py` (ampliar `:133-153`) | Página completa y fragmento sin editoriales: no hay `#f-publisher` ni «Todas las editoriales» visible; con `publisher_id` activo: sí hay `select` y opción seleccionada; con editoriales: opciones. |
| R3 | `tests/test_web_series.py` (ampliar `:291-306`) | `WishlistPolicy.FUTURE` y `ALL`: el texto visible no contiene `futuros` ni `todos`; sí la etiqueta; el `option` conserva su `value`. |
| R4 | `tests/test_web_library.py` (actualizar `:633-637`) | `?vista=inventada`: aparece «La vista pedida no existe…» y no «presentación»; la rejilla sigue siendo de tarjetas. |
| Guarda de Estado | `tests/test_web_estado_cortesia.py:102,135` o `tests/test_web.py:109` | El texto visible de `/estado` no contiene «JSON»; el `<script>` y los comentarios no cuentan. |
| Guarda de tradición | `tests/test_web_library.py` | Una serie `tebeo` muestra «Tebeo español» y el HTML conserva `value="tebeo"` / `tradition=tebeo`. |

No se propone una prueba de «grep global» sobre plantillas o código: sería frágil y contradice el criterio 7.

### 5.5 Verificación en navegador

Cuando el recorte se implemente como tarjeta, el DoD de #205 exige navegador real con entorno, SHA y capturas
(1280 y 360 px, claro y oscuro, teclado y árbol de accesibilidad). Eso no se acredita con este documento. La
validación en la Pi sigue siendo una autorización separada y no se incluye aquí.

### 5.6 Riesgos de proceso

- **Doble renombrado:** si se renombra «archivos» o «Pendientes por carpeta» antes de U7, es probable que U7 lo
  vuelva a cambiar. Por eso el recorte no toca esos términos.
- **Confundir este recorte con #205:** un PR verde de R1–R4 no acredita los criterios 2, 5 ni 6 de #205. El
  tablero no debe pasar #205 a «Hecha» por esto.
- **Reabrir #270:** R2 no reabre #270; documenta una regresión de #628 y la corrige en el mismo punto.
- **Cambiar el valor por el texto:** cualquier propuesta que cambie `option value`, el parámetro `tradition` o
  `wishlist_policy` rompe datos y contratos. En este recorte no ocurre.

---

## 6. Recomendación y decisión del PO

### 6.1 Recomendación

**Hacer U7 primero, con su propia tarjeta.** Es el desbloqueo real de #205: sin glosario no se pueden acreditar
los criterios de terminología ni la tabla de cambios del DoD. U7 debe producir el documento, su versión y la
tabla de conceptos; #205 solo podrá citarlo.

**El recorte puede ir en paralelo, pero como tarjeta aparte.** R1–R4 son cambios independientes, pequeños y
sin renombres de dominio. Si el PO quiere mejorar ya el acceso y la biblioteca, autorizarlos en una tarjeta
separada (por ejemplo, «U18b») es razonable; lo que no es razonable es presentarlos como cierre de #205.

### 6.2 Qué debe decidir el PO

1. **Orden:** ¿U7 primero, o U7 y el recorte en paralelo? La recomendación es U7 primero; el recorte no bloquea
   a U7 y U7 no necesita el recorte.
2. **Alcance del recorte:** ¿autoriza R1–R4 como tarjeta aparte, con sus pruebas y su evidencia de navegador?
3. **Propiedad y fecha de U7:** quién redacta el glosario, dónde vive (la definición de U7 exige `CLAUDE.md`) y
   cuándo se aprueba su versión. Sin una versión aprobada, #205 sigue bloqueada.
4. **DoR de #205:** cuando exista U7, actualizar la casilla «Documento/version de U7 identificado…» y la tabla
   de cambios; no antes.

### 6.3 Qué no cierra #205

Ni U18a, ni R1–R4, ni un CI verde, ni una captura de las rutas independientes cierran #205. #205 sigue abierta
mientras no exista el glosario U7 y no se acredite el criterio 5 del issue con la tabla de conceptos, texto
anterior, texto acordado y ubicación, además de la tabla de cambios del DoD. La fusión y el despliegue son
decisiones separadas.

---

## Resumen de 5 líneas

- U7 no existe como glosario, tarjeta ni PR: solo hay una definición en `docs/BACKLOG.md:959-968`; la unificación terminológica sigue bloqueada.
- #270 cerró las erratas independientes y está fusionado, pero quedan dos residuos: el subtítulo del login con usuario (`login.html:15`) y el `select` de editorial vacío en fragmentos HTMX (`_filtros_panel_campos.html:11`).
- La auditoría m5 sigue vigente: «archivos», «registros», «pendientes» y «sueltos» se mezclan, y «Pendientes por carpeta» no coincide con el menú «Por revisar».
- El recorte independiente cerrado es R1–R4 (subtítulo de acceso, editorial vacía, valor reservado de política y «presentación» → «vista»), sin tocar entidades ni valores persistidos.
- Recomendación: U7 primero con su propia tarjeta; el recorte, aparte y sin declarar #205 cerrada.
