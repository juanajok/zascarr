# SPEC: «Conservar la portada que ya tiene buena resolución» (BL-PORT5, issue #435) — v1.1

> **Estado:** **v1.1** (2026-11-06; registro de un cambio de QA, §15). **v1.0** (2026-11-06). **Aprobada por el PO, que ordena implementarla.** Sin decisiones abiertas: umbral
> 300 px inclusivo (aprobado a sabiendas de que JSA usará su portada local), regla de precedencia sobre `v2` sin `v3`
> (con las alternativas descartadas), cinco series y sus anchos medidos en la Pi (P-1 cubierto). Solo especificación:
> **sin código, sin dependencias, sin despliegue**; no toca repo, issues ni tablero. Siguen los supuestos (§12) y los NOT
> RUN (§11). Destino propuesto en el repo: `docs/design/especificacion-BL-PORT5.md` (lo lleva el Brain).
> **Base contrastada:** `origin/main` = `721345a983b8042ef82153ac315f9034951a9437` (2026-11-06). Todo lo de §1.1 está leído
> con `git show`; **nada ejecutado**.
> **Semilla:** issue #435 (cuerpo; sin comentarios), §16 de `especificacion-BL-PORT3.md` (cruce con #418),
> `docs/design/medicion-BL-PORT1-2026-11-06.md` (#411), `web/series.py::portada`, `utils/cover.py`.
> **Notación:** EARS con palabras clave en español (CUANDO, MIENTRAS, SI/ENTONCES, DONDE); criterios Given/When/Then;
> identificadores en inglés; esta historia **no añade texto visible** (CLAUDE.md §6).

---

## 0. Resumen ejecutivo

**Qué cambia.** Antes de mirar la caché de portada de serie (`covers/v2`) y los archivos, la ruta `portada` comprueba si
la serie ya tiene una **portada previa suficiente** —hoy, la caché antigua `covers/<id>.jpg`— con **ancho ≥ 300 px**
(umbral inicial de la issue, a ratificar). Si la hay, **se sirve esa**: no se extrae nada del archivo, no se escribe
`v2` y no se copia ni se toca la antigua. Si es menor (los 100×100 de Tebeosfera) o falta, la cascada sigue como hoy.

**Respuesta a la pregunta del Brain: ¿hace falta `v3` ya o basta una regla sobre `v2`?** **Basta una regla de
*precedencia*, sin `v3`.** Las cinco `v2` locales ya escritas no hay que borrarlas ni regenerarlas: la portada previa
suficiente **se sirve antes que `v2`**, así que `v2` queda sin uso en esas series (y reversible). **La alternativa
descartada** —subir a `v3` ahora— regeneraría las 9 portadas locales y volvería a descargar las externas **solo para
que `v2` deje de bloquear**, cuando una regla de orden lo consigue sin tocar el disco; y `v3` ya es el cambio de
estructura propio de #418 (D-2), que no conviene acoplar a esta historia.

**Función única, compartida con #418.** Una sola función, `portada_previa_suficiente(...)`, recorre una **lista ordenada de
portadas previas de solo lectura** definida en un único lugar: hoy `[covers/<id>.jpg]`; #418 le añadirá
`covers/externa/<id>.jpg`. Ni #435 ni #418 tienen su propia regla.

**Qué no cambia.** CBZ, ZIP y la regla de #419 (primer archivo legible, topes) cuando la previa falta o es pequeña;
`ETag`/`Cache-Control`/304; la antigua jamás se copia ni se modifica (Q-1 de #300); sin red; sin leer RAR; sin ajustes
nuevos; sin migración.

**Entrega.** Una historia = **una PR**, dos commits (§10). Tamaño S (la estimación la da quien implemente).

---

## 1. Problema y resultado deseado

### 1.1 Hecho verificado en `main` `721345a`

| # | Hecho | Evidencia |
|---|---|---|
| V1 | Orden actual de `portada`: (1) `covers/v2/<id>.jpg` si existe → se sirve; (2) si no, candidatos de archivo (#419) → `write_cover_cache(v2)`; (3) `covers/<id>.jpg` antigua → se sirve **sin copiar**; (4) `cover_url` → descarga y **se escribe en `v2`**; (5) 404. **El archivo local gana siempre a la antigua, sin mirar su resolución** (decisión de #300) | `web/series.py:290-` (docstring y cuerpo) |
| V2 | Ancho de lo que guarda la antigua: la extracción de un CBZ a 240 px (`_THUMB_MAX_WIDTH = 240`) o una descarga externa a 320 (`_COVER_MAX_WIDTH = 320`); `Image.thumbnail` **nunca amplía** | `utils/cover.py:57, 87`, `_resize_and_save` |
| V3 | La antigua **solo se lee** (`legacy_path.read_bytes()`), y se sirve con `ETag` = `mtime` del fichero | `web/series.py` (rama 3), `_etag_for` |
| V4 | `v2` también contiene portadas **externas** (rama 4 escribe `v2_path`) y una portada de archivo, indistinguibles por su nombre | `web/series.py` (rama 4) |
| V5 | `v2` se sirve antes de consultar archivos: una `v2` ya escrita bloquea cualquier regla que se ponga **después** de ella | `web/series.py` (rama 1) |
| V6 | El umbral 240 < 300 ≤ 320 separa lo que guarda la antigua: **una antigua sacada de un CBZ mide ≤ 240** (se regenera a 600, que es la misma imagen más nítida); una de Comic Vine puede medir 240–320 y **a ojo es otra imagen** | V2; §1.2 |
| V7 | Datos de la Pi (issue, 2026-11-06, `488cb03`, una instalación): 9 de 20 series con `v2` local a 600; **5 pasaron de una portada de Comic Vine de 240–320 px a la primera página de su CBZ** (Absolute Batman, Superman, JSA, The Wicked + The Divine, XIII); 2 con 100×100 de Tebeosfera (AIDP, MURENA) ganaron portada local; 2 no tenían ninguna | #435 |
| V8 | Informe de #411: 9 de 20 «ya a 600» y 11 CBR sin extractor, todas con `cover_url` (se descargan al abrir la ficha). **Observación mía, no ejecutada:** `fetch_and_cache_cover` limita el ancho a 600 pero **no amplía**, así que una externa de 100–320 px se guarda a ese ancho, no «a 600»; el informe cuenta como «en objetivo» solo `v2` ≥ 600 | `utils/cover.py` (`_resize_and_save`); `medicion-BL-PORT1-2026-11-06.md` §4 |
| V9 | Las comprobaciones de portada previa de #435 no pueden saber el **origen** de un `v2` (archivo o externa); sí el de la antigua: nunca se genera ya (solo se lee) | V3, V4 |
| V10 | **Anchos medidos en la Pi el 2026-11-06 (dato del Brain, solo lectura)** de la antigua de las **cinco** series de Comic Vine sustituidas: Absolute Batman **320**, Superman **320**, The Wicked + The Divine **320**, XIII **320**, JSA **240** | Medición del 2026-11-06 |

**Efecto del umbral de 300 sobre esas cinco:** cuatro (320 px) **vuelven a su portada de Comic Vine**; **JSA (240 px) no la alcanza** y se queda con su portada local de 600 (ya tenía `v2` local). El PO lo aprobó **a sabiendas**. Queda corregido «seis» del encargo: son **cinco**.

### 1.2 Resultado deseado, medible

| Objetivo | Métrica | Umbral |
|---|---|---|
| O-1 Conservar lo bueno | serie con antigua ≥ 300 px: portada servida | la antigua, byte a byte; 0 lecturas de archivos de la biblioteca; 0 escrituras |
| O-2 Seguir mejorando lo pequeño | serie con antigua < 300 px o sin ella | cascada actual (archivo → `v2` a 600) |
| O-3 Sin tocar el disco | `v2` ya escrita de una serie con antigua suficiente | ni se borra ni se regenera; se ignora |
| O-4 Coste | comprobar el ancho de la antigua | solo cabecera de imagen; ≤ 5 ms por petición caliente (propuesto, a medir) |
| O-5 Una sola regla | funciones que deciden «previa suficiente» | 1, compartida con #418 |
| O-6 Sin regresión | CBZ, ZIP, #419, `ETag`, 304 | idénticos |

## 2. Alcance

### 2.1 En alcance
La función única de «portada previa suficiente»; su precedencia en `web/series.py::portada`; el umbral; qué pasa con las
`v2` ya escritas y con las series cuyo primer archivo es RAR; criterios y pruebas.

### 2.2 Fuera de alcance
1. **Leer RAR** (#418) y el cambio de estructura `v3`/`covers/externa` (D-2 de #418).
2. Mostrar pequeña y centrada una portada pequeña.
3. Elegir la portada a mano o un botón «volver a leer la portada».
4. Borrar, mover o regenerar ficheros de `covers/` (la historia **no autoriza** borrar nada en la Pi).
5. Comparar visualmente dos imágenes o decidir cuál es «la oficial»: la regla es de **resolución**, no de contenido (compromiso aceptado en la issue).
6. Cambiar la regla de #419, `MAX_INTENTOS_PORTADA` o el recorrido.
7. El censo de #411 (`scripts/medicion/censo_portadas.py`) y la decisión de BL-PORT2.

## 3. Reglas de negocio y compromisos aceptados
- BR-01 Una portada previa **suficiente** (ancho ≥ umbral) se conserva; no se sustituye por la primera página del archivo. *(I, decisión del PO 2026-11-06)*
- BR-02 La antigua no se copia a `v2` ni se modifica. *(Q-1 de #300; criterio 3)*
- BR-03 **Compromiso aceptado en la issue:** la previa puede ser de otra edición que la del archivo del coleccionista. Si el PO prefiere lo contrario, la historia se descarta.
- BR-04 La regla mide **resolución**, no contenido ni origen; no puede distinguir una antigua sacada de un CBZ de una de Comic Vine del mismo ancho (V9).

## 4. Requisitos funcionales (EARS)

Origen: I = issue #435, V# = verificación (§1.1), Q = pregunta de §9.

- FR-01 (ubicuo) Existirá **una única función** `portada_previa_suficiente` (sugerido: `utils/cover.py`) que, dado el directorio de portadas y el id de la serie, devuelva la primera portada previa cuyo **ancho** sea ≥ `UMBRAL_PORTADA_PREVIA_PX`, o nada. La **lista ordenada** de portadas previas vive en un solo sitio; hoy contiene solo `covers/<id>.jpg`. *(O-5; compartida con #418)*
- FR-02 (evento) CUANDO se pida `GET /ui/series/{id}/portada`, el sistema deberá evaluar `portada_previa_suficiente` **antes** de servir `covers/v2/<id>.jpg` y antes de consultar archivos. *(V5; Q-1)*
- FR-03 (evento) CUANDO exista una portada previa suficiente, el sistema deberá servirla con `Content-Type: image/jpeg`, `ETag` = `mtime` de **ese** fichero y `Cache-Control: private, max-age=86400` (304 con `If-None-Match`), **sin** consultar archivos de la biblioteca, **sin** llamar a ningún extractor, **sin** descargar nada y **sin** escribir en `covers/`. *(I criterios 1, 3, 4)*
- FR-04 (ubicuo) El ancho se obtendrá leyendo **solo la cabecera** de la imagen (sin decodificarla) sobre **los mismos bytes que se van a servir** (una sola lectura). Una portada previa solo cuenta como suficiente si, además, **es un JPEG íntegro en lo comprobable**: empieza por el marcador `FF D8` y **termina exactamente en el marcador `FF D9` (EOI)**. SI la cabecera no se puede leer, la imagen no es válida, **está truncada (no acaba en `FF D9`)** o el fichero no existe, ENTONCES esa portada previa **no cuenta como suficiente** (falla cerrado) y la cascada sigue; se registra el tipo de error sin ruta. **Límite conocido:** un JPEG roto en mitad del cuerpo pero con `FF D8` al inicio y `FF D9` al final se seguiría aceptando (decodificar costaba 2,9 ms por petición; el marcador, 0,0002 ms). *(I criterio 4; CLAUDE.md §5.4; QA de #439)*
- FR-05 (ubicuo) El umbral será `UMBRAL_PORTADA_PREVIA_PX = 300` (inclusivo: 300 es suficiente, 299 no), una constante de módulo, no un ajuste de usuario. *(Q-2)*
- FR-06 (estado) MIENTRAS no exista una previa suficiente (falta, es menor que el umbral o ilegible), el sistema deberá comportarse **exactamente como hoy**: `v2` → candidatos de archivo (#419) → antigua → `cover_url` → 404, con las mismas cabeceras y escrituras. *(I criterios 2 y 5)*
- FR-07 (ubicuo) El sistema **no deberá borrar, mover, regenerar ni modificar** ningún fichero de `covers/` por esta regla: una `v2` ya escrita de una serie con previa suficiente **se ignora** (queda en disco, sin uso). *(O-3; Q-3)*
- FR-08 (ubicuo) Una serie cuyo primer archivo sea un RAR (hoy sin extractor) seguirá sin leerse: con previa suficiente se sirve esta; sin ella, la cascada actual. La función y la regla **no abren ningún archivo** y no dependen de #418. *(Q-4)*
- FR-09 (ubicuo) El registro **no llevará ruta, nombre de archivo ni nombre de serie**: el evento `cover.previa_suficiente` llevará `ancho` y `umbral`; el fallo de lectura, solo el tipo de error. *(I criterio 6; CLAUDE.md §5.4)* **Nota de implementación (QA y SecOps de #439, 2026-11-06):** el acierto **no emite ningún evento** (`cover.previa_suficiente` se retiró): se evalúa en cada petición, también las 304, y la app no filtra por nivel (`log_level` no se cablea a structlog), así que cada carga de una rejilla escribiría una línea por serie. La información (ancho y umbral) la cubren las pruebas. Solo se avisa (`cover.previa_ilegible`, con el tipo de error y sin ruta) una vez por fichero ilegible y versión.
- FR-10 (ubicuo) La comprobación del ancho no deberá acumular memoria sin límite: se podrá recordar `(ruta, mtime_ns, tamaño) → ancho` en una memoria acotada, invalidada por el cambio de `mtime_ns` o tamaño. *(O-4; opcional, solo si la medida lo justifica)*
- FR-11 (ubicuo) CBZ, ZIP y `.cbr`-ZIP, y las reglas de #419 (`MAX_INTENTOS_PORTADA`, `MAX_EVALUADOS_PORTADA`, `es_candidato_de_portada`), no cambian cuando la previa falta o es pequeña. *(I criterio 5)*
- FR-12 (ubicuo) La ruta seguirá respondiendo 404 con las mismas cabeceras cuando no haya nada; una previa suficiente **nunca** produce un 500 por I/O: cualquier `OSError` al medirla se trata como FR-04.

## 5. Contratos y datos

### 5.1 Cascada resultante de `GET /ui/series/{series_id}/portada`
1. **Previa suficiente** (`portada_previa_suficiente`: lista ordenada de portadas previas; hoy `covers/<id>.jpg` con ancho ≥ 300) → servir. *(nuevo)*
2. `covers/v2/<id>.jpg` → servir. *(igual)*
3. Candidatos de archivo (#419) → `write_cover_cache(v2)` → servir. *(igual)*
4. `covers/<id>.jpg` antigua (cualquier ancho) → servir sin copiar. *(igual; alcanzada solo si su ancho < umbral o ilegible)*
5. `cover_url` → descargar → `v2` → servir. *(igual)*
6. 404. *(igual)*

### 5.2 Constantes
| Constante | Valor | Origen |
|---|---|---|
| `UMBRAL_PORTADA_PREVIA_PX` | 300 | #435; separa 240 (antigua sacada de CBZ) de 320 (Comic Vine) |
| Lista de portadas previas | `[covers/<id>.jpg]` | hoy; #418 añade `covers/externa/<id>.jpg` |

### 5.3 Datos
Se lee `covers/<id>.jpg` (cabecera). **Sin cambios de modelo, de migración ni de ajustes.** No se lee `files` para decidir.

### 5.4 Qué se escribe
Nada nuevo. En particular **no** se escribe `v2` cuando hay previa suficiente.

## 6. Estados: qué ve la persona
Las series con una portada de Comic Vine suficiente vuelven a mostrarla (las cinco que cambiaron). Las de 100 px de Tebeosfera siguen recibiendo la del archivo. **Límite:** el navegador conserva la imagen anterior hasta 24 h (`max-age=86400`); el `ETag` cambia, así que se actualiza al revalidar. Sin texto nuevo.

## 7. Requisitos no funcionales
| Id | Requisito | Método |
|---|---|---|
| NFR-01 | Medir el ancho de la antigua cuesta solo la cabecera (≤ 5 ms por petición; propuesto) | Medición (AC-12) |
| NFR-02 | 0 lecturas de la biblioteca y 0 escrituras cuando hay previa suficiente | Prueba (AC-02) |
| NFR-03 | Sin dependencias nuevas, sin migración | Revisión (AC-15) |
| NFR-04 | Sin rutas ni nombres en los registros | `capture_logs` (AC-13) |

## 8. Criterios de aceptación (Given/When/Then)

- AC-01 *(FR-03, I-1)* Dada una serie con `covers/<id>.jpg` de 320 px y un CBZ legible, cuando se pide la portada, entonces la respuesta es la antigua, byte a byte, con `ETag` de su `mtime` y `Cache-Control: private, max-age=86400`; y un segundo `GET` con ese `ETag` da 304.
- AC-02 *(FR-03, NFR-02)* En el caso de AC-01, el extractor sustituido por una función que falla si se llama **no se llama**, no se consulta ningún `File` y no se crea ni modifica nada en `covers/` (comparación de árbol y de `mtime`).
- AC-03 *(FR-05)* Una antigua de **300** px es suficiente; de **299**, no.
- AC-04 *(FR-06, I-2)* Dada una antigua de 100×100 (Tebeosfera) y un CBZ legible, entonces la cascada actual: se extrae del archivo, se escribe `v2` a 600 (o al ancho del original) y se sirve esa.
- AC-05 *(FR-06)* Dada una serie sin antigua, entonces el comportamiento es el de `main` en todos los pasos (archivo → `v2` → externa → 404).
- AC-06 *(FR-02, FR-07, V5)* Dada una serie con **`v2` ya escrita** (de un CBZ) y una antigua de 320 px, entonces se sirve la **antigua**, `v2` sigue en disco con su contenido y `mtime` y no se regenera. *(Es el caso de las cinco series de la Pi.)*
- AC-07 *(FR-07, FR-06)* Dada una `v2` ya escrita y una antigua de 100 px, entonces se sirve `v2` como hoy.
- AC-08 *(FR-04)* Dada una antigua vacía, de 1 byte, sin `FF D8` inicial, **cortada a mitad del cuerpo con la cabecera íntegra**, **cortada justo tras la cabecera**, con **bytes sobrantes tras el `FF D9` final** o ausente, entonces **no** cuenta como suficiente, no hay 500 y la cascada sigue; con un `FF D9` **en mitad** del fichero (p. ej. una miniatura EXIF) pero sin él al final, tampoco cuenta; el registro lleva el tipo de error y ninguna ruta. **Mutación:** comprobar `FF D9` en cualquier posición, o no comprobarlo, rompe al menos una de estas pruebas. *(Límite conocido: AC no cubre un JPEG roto con `FF D9` al final.)*
- AC-09 *(FR-04)* Dada una antigua de 40 Mpx, entonces el ancho se lee por cabecera y la imagen **no se decodifica** (prueba con una imagen falsa que falla en `.load()`).
- AC-10 *(FR-08, Q-4)* Dada una serie cuyo primer archivo es un RAR y una antigua de 320 px, entonces se sirve la antigua sin abrir el archivo; con una antigua de 100 px, o sin ella, la cascada actual (la antigua o `cover_url`), sin leer el RAR.
- AC-11 *(FR-01, O-5)* La decisión «previa suficiente» está en **una sola función** y la ruta no tiene otra comparación de anchos; la lista de portadas previas está en un solo lugar y es ampliable con una línea (prueba con una lista de dos elementos: devuelve la primera suficiente en orden).
- AC-12 *(NFR-01)* Medir el ancho de la antigua en una petición caliente cuesta ≤ 5 ms (medida con el banco de BL-PORT1; **NOT RUN** hasta medir en la Pi).
- AC-13 *(FR-09, NFR-04)* Con `capture_logs`, ningún evento contiene ruta, nombre de archivo ni de serie; el evento `cover.previa_suficiente` lleva `ancho` y `umbral`. *Actualizado (#439):* el acierto y la ausencia de previa **no emiten ningún evento**; un fichero ilegible emite un solo `cover.previa_ilegible` por versión del fichero, sin ruta ni nombre.
- AC-14 *(FR-11, I-5)* Los CBZ, ZIP y `.cbr`-ZIP de las pruebas existentes (`test_cover*.py`, `test_web_portadas_v2.py`) siguen en verde sin cambios de aserciones cuando no hay antigua; y la regla de #419 (3 intentos, 50 evaluados) no cambia.
- AC-15 *(NFR-03)* El diff no toca `pyproject.toml`, migraciones ni ajustes.
- AC-16 *(FR-12)* Un `OSError` al abrir la antigua (permiso denegado) no da 500.
- AC-17 *(FR-07, BR-02)* La antigua conserva hash y `mtime` tras cualquier petición, y no existe `covers/v2/<id>.jpg` nuevo para una serie con previa suficiente que no lo tenía.
- AC-18 *(FR-03)* Con previa suficiente, ninguna petición externa (el cliente HTTP de descarga sustituido por uno que falla si se usa).
- **Prueba de regresión con el mecanismo en el nombre** *(I criterio 7)*: `test_previa_suficiente_gana_al_archivo_aunque_v2_exista`: serie con antigua de 320 px, un CBZ legible y una `v2` previa → conserva la antigua.

## 9. Registro de decisiones (aprobadas por el PO el 2026-11-06)

| Decisión | **Aprobada** | Alternativas descartadas |
|---|---|---|
| Q-1 `v3` o regla | **Regla de precedencia sobre `v2`**, sin `v3` ahora | **B** subir a `v3` (regenera 9 locales y re-descarga externas; acopla #435 al cambio de #418); **C** borrar las `v2` a mano (acción en la Pi no ordenada; no es una regla) |
| Q-2 umbral | **300 px inclusivo**, sabiendo que **JSA (240 px)** usa su local de 600 | 240 o menos (conservaría antiguas borrosas sacadas del CBZ); bajar a 241 para JSA (no se hace) |
| Q-3 `v2` ya escritas | No se tocan: se ignoran mientras haya previa suficiente | Regenerar o borrar |
| Q-4 series con RAR primero | Nada ahora; la misma función evitará que #418 sustituya la previa suficiente | Una regla propia en #418 |
| Q-5 función | Una sola, en `utils/cover.py`, ampliable con una línea | Comparación suelta en `web/series.py` |
| Cinco, no seis | **Cinco** series de Comic Vine sustituidas | — |

Más abajo se conserva el razonamiento original de cada decisión.

### Q-1 — ¿Hace falta `v3` ya, o basta una regla sobre `v2`?
| Opción | Cómo | Efecto en las `v2` ya escritas | Coste |
|---|---|---|---|
| **A (recomendada)** regla de **precedencia** sin `v3` | La previa suficiente se evalúa **antes** de `v2` | Las cinco `v2` locales (y cualquier otra) quedan **sin uso** pero intactas; vuelve la portada de Comic Vine; **ni se borra ni se regenera nada** | Una lectura de cabecera por petición caliente (≤ 5 ms propuesto); `v2` huérfana mientras dure la regla (reversible: quitar la regla la hace servir otra vez) |
| **B (descartada)** subir a `v3` ahora | `CACHE_VERSION = "v3"` + la regla después de `v3` | Todas las `v2` quedan ignoradas; **9 portadas locales se regeneran** y **las externas se vuelven a descargar** (red, cortesía) | Regeneración y descargas innecesarias para esta historia; acopla a #435 el cambio de estructura de #418 (D-2: `v3` solo de archivo, `externa` aparte); si #418 tarda, `v3` queda a medias |
| **C (descartada)** borrar las cinco `v2` a mano | Orden del operador con la lista a la vista | Las cinco vuelven a la antigua | No es una regla, es una acción en la Pi que el PO **no ha ordenado**; no cubre futuros casos |

**Recomiendo A.** El orden de precedencia consigue lo que `v3` y el borrado, sin tocar el disco. **Límite:** una `v2` huérfana de una serie con previa suficiente ocupa espacio sin servir (decenas de KB por serie). **Efecto en #418:** su salto a `v3` (D-2) sigue siendo necesario para sus propios fines (RAR y separar la externa), pero **ya no es la invalidación de las cinco `v2`**: esa la hace esta regla. §16 de BL-PORT3 pasa a decir que #435 puede desplegarse sola sin dejar el problema abierto.

### Q-2 — El umbral
La issue propone **300 px**. Razón: la antigua sacada de un CBZ mide ≤ 240 (V2) y la de Comic Vine ≤ 320, así que cualquier umbral **> 240 y ≤ 320** separa; con 240 o menos se **conservarían** antiguas borrosas sacadas del propio CBZ (justo lo que BL-PORT1 arregló). **Recomiendo 300.** Consecuencia: una portada de Comic Vine de 240–299 px **no** se conserva (se sustituye por el archivo): el ancho no distingue su origen (BR-04). **Dato medido (V10):** las cinco antiguas miden 320, 320, 320, 320 y **240 (JSA)**. **Aprobado por el PO el 2026-11-06**: 300 inclusivo, con JSA usando su portada local de 600. Si más adelante apareciera otra de Comic Vine de 240–299 px, se aplica lo mismo (BR-04).

### Q-3 — Las `v2` ya escritas
**No se tocan** (FR-07): se ignoran mientras haya previa suficiente. Sin borrar, sin migrar y sin orden de operador. Alternativa descartada: regenerar o borrar (Q-1 B y C).

### Q-4 — Series cuyo primer archivo es RAR
**Nada que hacer ahora:** no se lee ningún RAR (FR-08). Con previa suficiente se sirve esta (como ya ocurre hoy, porque el RAR no da portada); cuando llegue #418, **la misma función evita que el RAR la sustituya** (las 2 series de Comic Vine a 320 px de la medición). Por eso #435 va primero.

### Q-5 — Dónde vive la función y quién la amplía
`portada_previa_suficiente` en `utils/cover.py` (junto a `puede_tener_portada`, `es_candidato_de_portada`); #418 solo añade `covers/externa/<id>.jpg` a la lista. **Alternativa descartada:** dejar una comparación suelta en `web/series.py::portada` (dos reglas divergirían).

## 10. División en PR
Una historia = **una PR**, dos commits:
1. **Función y pruebas** (`utils/cover.py`: `portada_previa_suficiente`, la lista y el umbral; pruebas AC-03, 08, 09, 11, 13, 16).
2. **Ruta y documentación** (`web/series.py::portada`: precedencia; docstring; nota en `especificacion-BL-PORT1.md` donde dice que el archivo gana a la antigua; pruebas AC-01, 02, 04..07, 10, 14, 17, 18 y la de regresión).

**Puertas de fusión:** CI sin saltos (decisiones Q-1..Q-5 ya aprobadas). **Puerta de despliegue:** P-2 (medida de AC-12, coste de la cabecera por petición caliente; autorización por tanda). **P-1 está cubierto** (V10: anchos de las cinco antiguas medidos el 2026-11-06). **Ningún borrado** en la Pi.

## 11. NOT RUN / no verificado
1. Nada ejecutado: ni la suite, ni ZascArr, ni la Pi.
2. ~~P-1~~ **Cubierto** para las cinco series (V10). **Siguen sin medirse** las antiguas de las otras 4 series con `v2` local (2 de Tebeosfera a 100 px según la issue, 2 sin portada previa); no afectan a la decisión.
3. **P-2:** el coste de medir la cabecera por petición caliente (AC-12, NFR-01) y si hace falta la memoria acotada (FR-10).
4. Si la antigua de cada serie es la portada oficial o una variante (la diferencia la señaló el PO a ojo); la regla es de resolución.
5. La observación V8 (una externa no se amplía a 600) no está ejecutada.
6. Que las pruebas «existentes» citadas se ejecuten en la CI de `main`.

## 12. Supuestos y riesgo si son erróneos
| Id | Supuesto | Riesgo |
|---|---|---|
| S-1 | La antigua sacada de un CBZ mide ≤ 240 y la externa ≤ 320 (V2) | Si hubiera antiguas de otro ancho (versiones anteriores del código), el umbral las clasificaría distinto |
| S-2 | La antigua nunca se regenera (solo se lee) | Si algo la reescribiera, la precedencia cambiaría de resultado |
| S-3 | El navegador revalida a las 24 h (`max-age=86400`) | Las cinco series pueden mostrar la imagen anterior hasta entonces |
| S-4 | Una instalación representativa (la de la Pi) | Los números de V7 no se extrapolan |

## 13. Riesgos
| Id | Riesgo | Mitigación |
|---|---|---|
| R-1 | Una portada de Comic Vine de otra edición sustituye a la del archivo | Compromiso aceptado por el PO (BR-03); reversible quitando la regla |
| R-2 | Una antigua de 240–299 px de Comic Vine no se conserva (**caso real: JSA, 240 px**) | Aprobado por el PO (Q-2); el ancho no distingue el origen |
| R-3 | `v2` huérfana ocupa espacio | Decenas de KB por serie; limpieza fuera de alcance |
| R-4 | Dos reglas divergentes entre #435 y #418 | FR-01, AC-11 |
| R-5 | Coste por petición caliente | FR-10, AC-12, NFR-01 |
| R-6 | Una antigua corrupta bloquearía la cascada, o se serviría rota (QA de #439: truncada a mitad del cuerpo con la cabecera íntegra contaba como suficiente) | FR-04: falla cerrado; ancho por cabecera **y** `FF D8`…`FF D9` sobre los mismos bytes. Límite: un JPEG roto con EOI al final se aceptaría |

## 14. Trazabilidad
| Objetivo | FR | AC |
|---|---|---|
| O-1 conservar lo bueno | 02, 03, 05 | 01, 02, 03, 06, 18 |
| O-2 seguir mejorando lo pequeño | 06, 11 | 04, 05, 07, 14 |
| O-3 sin tocar el disco | 07 | 06, 17 |
| O-4 coste | 04, 10 | 09, 12 |
| O-5 una sola regla | 01 | 11 |
| O-6 sin regresión | 06, 11, 12 | 05, 14, 16 |

**Autorrevisión.** *Vaguedad:* «suficiente» está definido (ancho ≥ 300 por cabecera); el 5 ms es propuesta, marcada. *Compuestos:* FR-03, FR-04 y FR-07 separan servir, medir y no tocar. *Contradicciones a la superficie:* (a) el encargo habla de «seis `v2`» y la issue de cinco; (b) la issue dice que las externas se cachean «a 600» y `thumbnail` no amplía (V8); (c) §16 de BL-PORT3 decía que el salto a `v3` resolvía las `v2` ya escritas: con esta regla ya no es necesario para eso. *Estado:* v1.0 aprobada por el PO; sin decisiones abiertas; con 5 NOT RUN, 4 supuestos y la puerta de despliegue P-2.

## 15. Registro de cambios
| Versión | Fecha | Cambio |
|---|---|---|
| v1.0 | 2026-11-06 | Aprobada por el PO (registro de decisiones en §9). |
| **v1.1** | 2026-11-06 | **QA de #439:** una antigua truncada a mitad del cuerpo, con la cabecera íntegra, contaba como suficiente y se servía rota. FR-04 exige que la imagen **empiece por `FF D8` y acabe en `FF D9`**, sobre los bytes ya leídos (0,0002 ms; `load()` costaba 2,9 ms por petición); AC-08 y R-6 ampliados; límite conocido anotado. El builder lo aplicó en la copia de la PR; esta copia lo recoge. |

### 15.1 Huecos que veo en la regla del marcador (sin decidir; para el Brain y el builder)
1. **La antigua servida como último recurso no pasa por la misma comprobación.** La rama 4 de §5.1 sirve la antigua «de cualquier ancho»: una truncada o de menos de 300 px se serviría igualmente rota antes de intentar `cover_url`. Si se quiere coherencia, la misma comprobación de integridad debería aplicarse allí (la antigua rota cae a la externa o al 404). **Cambia el comportamiento actual de esa rama**, por eso es decisión del PO y no entra en v1.1.
2. **Solo se mira el ancho.** Una antigua de 320×10 o con dimensiones absurdas contaría como suficiente. Las antiguas las generó este código con `thumbnail` (≤ 320 de ancho, proporcional), así que el riesgo es bajo; si se quisiera cubrir, bastaría un alto mínimo y un ancho máximo razonable en la cabecera.
3. **Bytes sobrantes tras el EOI.** Exigir que el fichero acabe *exactamente* en `FF D9` rechaza un JPEG válido con relleno final (raro, pero existe). Es seguro (cae a la cascada) pero puede descartar una buena; las antiguas las escribió Pillow, que no deja relleno.
4. **Una sola lectura.** El ancho, la comprobación y el servido deben usar el mismo `bytes`: si se lee dos veces y el fichero cambia entre medias, se serviría otra cosa. Debería figurar en una prueba (que el fichero se sustituya a mitad con un doble).
5. **Si se memoriza el ancho (FR-10),** la memoria no debe recordar «suficiente» sin el resultado de la comprobación de integridad: la clave `(ruta, mtime_ns, tamaño)` la invalida si el fichero se trunca después, pero hay que probarlo.
6. **Otros formatos.** Se asume que la antigua es siempre JPEG (se sirve con `image/jpeg`). Una antigua en otro formato (PNG) quedaría fuera por `FF D8`: es lo correcto, pero conviene un caso de prueba.
7. **Sin cobertura de `v2`.** `v2` se escribe de forma atómica (`_publicar_atomico`); no se comprueba al servirse y no entra en esta regla.
