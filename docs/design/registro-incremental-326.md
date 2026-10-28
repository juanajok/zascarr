# Registro incremental de la biblioteca (#326)

> Estado: **implementado en una PR en borrador; revisiones 1 y 2 atendidas** (recorrido incompleto, exclusión entre procesos, carrera con el importador de descargas, archivo que cambia, reenlace con original presente, contabilidad de omitidos). Parte del refinamiento v1 de #326 (2026-10-23). Las decisiones marcadas «por defecto»
> las tomó el implementador porque el refinamiento las dejaba abiertas; **están por ratificar** y se pueden cambiar sin tocar el resto.

## 1. Problema local (CLAUDE.md §13)

- **Historia:** BL-R8 / #326 — quien deja un tebeo en su biblioteca espera que ZascArr lo vea.
- **Caso real:** #297 encontró 252 ficheros del disco sin fila; el hallazgo de #307 (`contrato-307-formato-por-contenido.md` §12.4) probó que, tras el registro
  inicial, **nada** registra los archivos nuevos de la biblioteca (el importador solo recorre las descargas; el marcador `_library_adoption_done` cierra la
  puerta de `LibraryAdopter`).
- **Hoy:** `adopt()` ya es idempotente por ruta, con un savepoint por archivo, lotes y segundo plano. Lo que impide usarlo es la **puerta** (`puede_registrar`,
  estado `HECHA`), no el adoptador.
- **Deseado:** una acción manual y explícita que enseñe lo nuevo, pida confirmación y registre solo eso, sin repetir el onboarding.

## 2. Referencias (no verificadas en vivo)

El texto de la tarjeta cita el «Rescan» de Sonarr y el escaneo de Kavita como expectativa del coleccionista. **No se han consultado en esta
implementación ni se infiere de su UI cómo funcionan por dentro** (§13). Decisión: **adaptar solo el patrón de producto** (una acción manual de búsqueda
+ confirmación), con implementación propia sobre `LibraryAdopter`. No se copia código de Kapowarr/Mylar3 (GPL-3.0).

## 3. Qué se hizo

| Pieza | Cambio |
|---|---|
| `LibraryAdopter.ofrece_registro_incremental()` | Solo cuando el registro inicial ya consta (marcador). Antes de eso se ofrece el registro completo, como siempre. No lee el disco. |
| `LibraryAdopter.inventario()` | Añade `carpeta_accesible`, `rutas_nuevas` y `huella` (resumen de las rutas nuevas enseñadas). Sigue sin abrir ningún archivo. |
| `LibraryAdopter.adopt(alcance=…)` | Con `alcance` solo trata esas rutas; no toca el marcador; guarda el informe con `kind = "registro_incremental"` (el de la adopción inicial, que usa Inicio, no se pisa). |
| Ambigüedad | Solo en incremental: si el contenido coincide con **varias** filas desaparecidas, no se reenlaza ninguna ni se crea fila: se informa (`ambiguous`). El importador y el registro inicial siguen reenlazando la más antigua, como siempre. |
| `registro_biblioteca.iniciar(…, alcance)` | La misma exclusión (una ejecución a la vez) para el inicial y el incremental. |
| `utils/fs.recorrer_comics` | Como `listar_comics`, pero **cuenta lo que no pudo leer** (`ilegibles`): `rglob` saltaba en silencio una subcarpeta sin permisos. Lo usan el inventario y `adopt`. |
| `registro_biblioteca._cerrojo_de_registro` | Cerrojo consultivo de Postgres (`pg_try_advisory_lock`) en una conexión propia: **un solo registro (inicial o incremental) en marcha entre procesos**. Si no se obtiene, fase `ocupado` y no se hace nada. |
| `importer.tomar_cerrojo_de_contenido` | **Sección crítica compartida «buscar por contenido → insertar»**: un cerrojo de transacción de Postgres (`pg_try_advisory_xact_lock`, una sola clave) que toma `_triage_and_match` —el punto común del importador y del registro— antes de buscar por hash y conserva hasta el fin de su transacción. El segundo escritor espera (máx. 60 s) y, al entrar, ya ve lo que el primero confirmó: lo trata como repetido. Sin migración. |
| `LibraryAdopter._adopt_file` | Compara tamaño y fecha del archivo antes y después de leerlo: si cambió, **no se registra** un hash que ya no le corresponde. En incremental, un reenlace exige poder afirmar que la ruta anterior **ya no tiene** el archivo (`_fichero_de_la_fila_existe`). |
| `GET /ui/auditoria/nuevos` | Busca (solo lectura: nombres y rutas). |
| `POST /ui/auditoria/registrar-nuevos` | Registra **solo** las rutas que la persona vio: lleva la `huella`; si la carpeta ya no la da, no registra nada y enseña la lista actual. |

Sin migración, sin dependencias nuevas, sin red, sin automatismo (un test comprueba que solo la pantalla lanza el registro).

## 4. Reglas

1. **Nuevo = ruta sin fila** (en `COMIC_EXTS`: `.cbz .cbr .cb7 .pdf .epub`). Una ruta con fila —incluida una descartada o de una serie retirada— no es nueva y no
   se toca; **no se reactiva ningún descarte**.
2. **El inventario no lee contenido.** El hash solo se calcula al confirmar, y solo para las rutas confirmadas.
3. **Alcance confirmado.** Lo que aparece después de revisar no se cuela; lo que desaparece o ya estaba registrado se cuenta aparte (`ya_no_pendientes`).
4. **Al registrar**, cada archivo acaba en UNA categoría: ficha nueva (con serie sugerida o sin identificar → «Por revisar»), repetido de otro presente (no se añade,
   no se toca ninguna copia), reenlace de una fila desaparecida (misma fila, vínculo e historial conservados), ambiguo (no se toca nada), error, de otra ejecución.
5. **Nunca se vincula por el nombre de la carpeta** y no se crean series: es el mismo emparejamiento del adoptador (`_triage_and_match`), que no mira carpetas.
6. **Carpeta o recorrido ilegible:** si la carpeta no es accesible **o** el recorrido no pudo leer alguna carpeta/archivo (`ilegibles > 0`), la búsqueda lo dice y **no ofrece confirmación global** (el servidor tampoco la acepta aunque se fuerce la petición); no cuenta «registrados sin fichero» (sería fabricar bajas). Este flujo **nunca** marca filas como desaparecidas.
7. **Resultado honesto:** «mirados» ≠ «añadidos»; con errores no se anuncia éxito; un commit incierto queda «por comprobar» (mecanismo existente de `_confirmar_lote`).
8. **Formatos (#307):** los archivos nuevos se triarán con el mismo punto de decisión; lo no utilizable queda registrado/avisado como hoy (no se amplía el universo).

## 5. Decisiones por defecto (a ratificar)

| # | Decisión | Por qué |
|---|---|---|
| a | **Punto de entrada: la pantalla de Auditoría**, donde ya vive el registro. #232 («Comprobar el disco») no está implementada. Cuando lo esté, «Buscar archivos nuevos» pasa a ser su continuación. | Evita esperar a #232 sin crear una acción que la duplique. |
| b | **Ignorados / retirados (#303): ninguna regla de reaparición.** Una fila nunca vuelve a ser «nueva». Un archivo con contenido ya conocido se trata por contenido (repetido o reenlace), sin reactivar descartes. | No hay un concepto de «ignorar» que inferir; no se borran decisiones por inferencia. |
| c | **Hash solo al confirmar**; lote existente de 25; sin tope nuevo. | El coste de leer el USB no está medido (§7). |
| d | **Informe con las categorías de §4.4**; sin categoría «no utilizables» propia, pero **cada archivo que no se pudo registrar o atribuir se lista con su causa** (§6.4); los formatos fuera de `COMIC_EXTS` los enseña «Revisar mi biblioteca». | No duplicar la auditoría sin ocultar fallos. |

## 6. Contratos

### 6.1 Qué protege la huella de confirmación (y qué no)
La huella resume **el conjunto de rutas** que la persona vio. Garantiza «registrar solo lo revisado»: si al confirmar la carpeta ya no da la misma huella (apareció o
desapareció una ruta), no se registra nada y se enseña la lista de ahora; además `adopt(alcance=…)` solo trata esas rutas aunque hayan aparecido más.
**No protege el contenido**: el hash se calcula al registrar. Para que no se guarde un hash que ya no corresponda al archivo:
- **Cambia manteniendo su ruta** mientras se lee: se compara (tamaño, fecha) antes y después de leerlo; si difieren, **no se registra**, se cuenta como error con causa y
  vuelve a salir en la siguiente búsqueda. *Límite:* un cambio que conserve tamaño **y** fecha no se detecta. Es una **guarda**, no una instantánea inmutable del contenido.
- **Desaparece** entre la búsqueda y la lectura: no es un error; se cuenta como «ya no estaba pendiente».
- **Se sustituye** antes de leerlo: se registra lo que hay en ese momento (el hash describe esos bytes).

### 6.2 Reenlace de una ficha existente
Solo si (1) hay **una única** fila desaparecida con ese contenido (con varias, no se toca ninguna), y (2) se puede afirmar que su ruta anterior **ya no tiene** el archivo (el
mismo criterio conservador del importador: si sigue ahí, o está en otro disco que podría estar desmontado, o falla la consulta, **no se reenlaza**). Entonces se reutiliza la
**misma fila** (id, vínculo, `original_sha256` y `metadata` se conservan). En los demás casos se informa «no se ha podido atribuir» y no se modifica ninguna ficha.

### 6.3 Repetición, fallo parcial y recuperación
- **Transacciones:** cada archivo en su savepoint; confirmación cada **25** archivos (valor provisional: ni garantía de coste ni de plazo). Lo confirmado se conserva.
- **Si falla un lote:** el commit se acredita con otra sesión (`_contrastar`): guardado → se cuenta; no guardado → «no guardados»; incierto → «por comprobar». Nunca se presenta
  como añadido lo que no se acreditó.
- **Si el `commit` termina pero se pierde la respuesta:** se acredita con otra sesión por **identidad** de lo que escribió esa transacción (`_contrastar`): si estaba todo, se cuenta y se sigue sin
  lanzar; si no estaba nada, «no guardados»; si no se puede saber, «por comprobar». El informe persistido (`registro_incremental`) cuenta lo que pasó y buscar de nuevo no encuentra nada pendiente.
- **Si se pierde la respuesta HTTP o se cierra la página:** el registro sigue en segundo plano y la pantalla recupera el estado en curso. *Límite:* el estado vive en memoria (se pierde
  al reiniciar el proceso); el informe persistido (`registro_incremental`) se escribe al terminar. Tras un reinicio se busca de nuevo y lo ya confirmado consta.
- **Continuar:** «Buscar archivos sin registrar otra vez» vuelve a calcular qué falta; es idempotente por ruta (`files.file_path` es único), así que repetir no duplica.
- **Pulsar confirmar dos veces / dos pestañas / dos procesos:** el botón se deshabilita; en el proceso, una sola ejecución; entre procesos, el cerrojo de Postgres.
- **Cancelación:** no hay botón de cancelar. Parar el proceso deja lo confirmado y el cerrojo se suelta solo (Postgres lo libera al cerrarse la conexión).

### 6.4 «Sin registrar» no es «tebeo nuevo»
La búsqueda no lee contenido, así que la pantalla habla de **rutas sin registrar** («archivos encontrados sin registrar») y lo dice: aún no se sabe si son tebeos distintos de los
que ya tienes. El resultado separa fichas nuevas, reenlaces, repetidos, no atribuidos, errores, de otra ejecución y **omitidos** (ya no estaban pendientes al empezar, o desaparecieron antes de leerlos: no son un
error, pero tampoco quedan registrados, así que constan con su causa). Cada archivo mirado cae en **una** categoría y el total cuadra (prueba). Los errores, los no atribuidos y los omitidos se listan **uno a uno con su causa**; si hay más de 50, la
pantalla dice el total y que el listado está limitado. Una copia que sigue en la carpeta vuelve a salir en cada búsqueda y se informa como repetida; nunca crea una segunda fila.

### 6.5 Concurrencia con el importador de descargas
Los dos crean filas buscando antes por contenido y la columna `sha256_hash` no es única, así que podían leer «nadie tiene esto» a la vez e insertar uno cada uno.
Ahora ambos pasan por `tomar_cerrojo_de_contenido` en `_triage_and_match`:
- **Dónde se toma y cuándo se suelta:** en `_triage_and_match`, justo después de calcular el hash del archivo y **antes de cualquier búsqueda por contenido** (prueba del orden: primero el cerrojo, luego la búsqueda).
  Se suelta al terminar **la transacción de quien lo tiene**: el registro confirma por lotes (≤ 25 archivos); el importador, al hacer `commit` el llamador al acabar el ciclo (`main._ejecutar_ciclo_y_avisar`). Un fallo de un
  archivo suelto no lo suelta (la transacción sigue); un fallo del ciclo entero cierra la sesión con *rollback* y lo suelta (pruebas: tras el commit está libre y antes no; tras un fallo a medias queda libre).
- **Qué ocurre durante la espera de 60 s:** quien llega con el cerrojo ocupado **no abre otra transacción ni aborta la suya**: reintenta la misma consulta cada 0,25 s (sin bloquear el bucle de eventos).
  Si pasan 60 s lanza `CerrojoDeContenidoOcupado` **antes de insertar nada**:
  - **importador:** anota «otra operación estaba registrando contenido; se reintentará en el próximo ciclo» **y corta el recorrido** («El ciclo se detuvo antes de mirar el resto de las descargas»), para no esperar 60 s por
    cada archivo. Los archivos siguen en descargas, intactos; el siguiente ciclo (cada `import_interval_minutes`) los retoma. Lo ya procesado en ese ciclo se confirma como siempre. Queda visible en el informe del ciclo
    (`errors`), no es un fallo silencioso.
  - **registro:** se detiene en la fase «El catálogo estaba ocupado» (lo confirmado se conserva, el lote en curso no se guarda) y la pantalla pide buscar de nuevo; no se crea el informe `registro_incremental` de un registro que no terminó.
  Si la ocupación se repite, cada ciclo/intento vuelve a fallar visiblemente con el mismo mensaje; ninguna operación queda esperando indefinidamente.
- **Informes de los dos lados:** el que perdió la carrera lo cuenta como repetido y nombra el archivo del que es copia («duplicado de …»); el que ganó cuenta lo que registró. Ninguno dice «nada» ni queda sin explicar (prueba).
- **Coste:** mientras un ciclo del importador tiene una transacción abierta, un registro de la biblioteca espera (hasta 60 s por archivo y luego se detiene). Es un reparto asumido:
  no hay carrera y nada se pierde, a cambio de que los dos no avancen a la vez cuando coinciden. No hay restricción única nueva (habría que revisar los datos existentes).
- **Otros escritores:** el etiquetado y las asignaciones no crean filas por contenido; no pasan por el cerrojo.

### 6.6 Recorrido parcial en `adopt` (#332, residual 2 de #329)
La búsqueda ya bloqueaba la confirmación con un recorrido incompleto, pero `adopt` ignoraba `Recorrido.ilegibles`: una adopción inicial podía terminar «completa» y poner `_library_adoption_done` sin haber visto
toda la carpeta. Ahora `adopt` guarda `unreadable` en su informe (y en el `ImportRun`): con `unreadable > 0` **no pone el marcador**, el estado del registro **no es «completo»**, la pantalla lo dice
(«No se ha podido leer N carpetas o archivos… Arregla el acceso y continúa») y ofrece continuar. Es el mismo criterio que usa `inventario()` (ambos cuentan con `recorrer_comics`). En el registro **incremental**,
los archivos del alcance que no se vieron constan como omitidos con la causa «su carpeta no se pudo leer» en lugar de «desapareció».

### 6.7 Archivo ilegible: `OSError` no es `BadZipFile` (#332, residual 1 de #329)
Un archivo que se puede `stat` pero falla al leer (`open`/`read`: permisos, error de E/S, USB que se cae) es un **error de lectura**, no un ZIP roto. `triage` deja `error_lectura` con la causa (tipo de `OSError` y `strerror`, sin ruta) y `sha256=None`; no guarda `formato_contenido` (una firma `ILEGIBLE` no se fija en la base) y no publica un hash parcial aunque la caída ocurra a mitad de lectura. `_triage_and_match` corta antes de deduplicar o buscar match: ni `adopt` ni el importador crean fila, mueven, reenlazan o descartan el archivo; lo apuntan en `errores` con la causa. Por eso `completo` es falso y el marcador no se pone: el residual 1 no reabre el hueco del residual 2. Un `BadZipFile` sigue siendo el caso intencional de contenido inválido: `sha256=None`, `formato_contenido.clase = "invalido"`, sin `error_lectura` y sin contar como error.

**Filas existentes con `sha256_hash IS NULL`:** no se rellenan. El recuento de solo lectura del 2026-10-28 sobre la base de la Pi dio **14 filas de 1.339** con hash nulo: todas `cbr`, **0** con `formato_contenido.clase = "invalido"`, **0** con `firma = "ilegible"` y **14** sin `formato_contenido`. El patrón encaja con las filas anteriores al arreglo de B16 que dejaba los `.cbr` sin hash, no con una lectura fallida; aun así, los datos actuales no permiten demostrar fila a fila cuál es cuál. Inventar un hash afirmaría una identidad que no se midió. Cualquier relleno futuro exige volver a leer el archivo y es una escritura sobre filas reales: tendrá su propia ventana y su procedimiento; mientras tanto esas filas se quedan como están y no participan del dedupe por contenido.

## 7. Límites conocidos (no resueltos)

- **Cobertura del cerrojo de contenido:** lo toman el importador y los registros de la biblioteca (los escritores que crean filas por contenido). Si en el futuro aparece otro, debe pasar también por `_triage_and_match`.
- **El cerrojo no sustituye a una restricción única:** si algo insertara filas sin pasar por ahí, la base no lo impediría (revisarlo es otra decisión).
- **Deriva de nombre o formato:** la guarda de coherencia mira tamaño y fecha, no el contenido: un archivo sustituido por otro de **otro formato o estructura interna** conservando ambos pasaría. Un mismo nombre con contenido en otro formato se trata por
  el triaje de #307 en el momento de leer (`triage` decide por contenido); este flujo no amplía eso. Si se amplía el flujo (p. ej. a otros contenedores), hay que revisar esta guarda.
- **Cambios que conservan tamaño y fecha** no se detectan al leer (§6.1).
- **Un contenido distinto en una ruta ya registrada** (archivo sustituido) no se detecta: es otro problema, no una alta.
- **Los formatos fuera de `COMIC_EXTS`** (`.rar`, `.tar`…) no se cuentan aquí: los enseña «Revisar mi biblioteca».
- **Rutas anteriores en otro disco:** un reenlace cuya ruta vieja cuelga de otro disco no se hace (no se puede afirmar que falte).
- **Carpeta ilegible permanente:** si una carpeta no se puede leer y la causa no se corrige, la adopción inicial no se da por completa y el marcador no se pone nunca; como el registro incremental exige el marcador, tampoco se ofrece. `completo` exige `ilegibles == 0`. No hay hoy una salida «completar con N ilegibles»: aceptar explícitamente esa exclusión es el residual 4 de #332.
- **Ilegibles ajenos al alcance confirmado:** el registro incremental recorre toda la biblioteca y cuenta `Recorrido.ilegibles` antes de filtrar por `alcance`; una carpeta ilegible que no tiene nada que ver con lo confirmado marca la ejecución como incompleta. Es conservador (no se puede afirmar que lo confirmado esté completo si el recorrido no vio todo), pero se documenta para que no se lea como un fallo del alcance.

## 8. Garantías ↔ pruebas

| Garantía | Prueba |
|---|---|
| El inventario no abre archivos ni escribe | `test_registro_incremental_pg::TestInventarioIncremental::test_enseña_lo_nuevo_por_ruta_sin_abrir_ni_escribir_nada` |
| Recorrido incompleto: se distingue, no se confirma (ni forzando la petición), no fabrica bajas | `TestRecorridoIncompleto` (2 pruebas); `test_registro_incremental::TestRecorrerComics`, `TestPantallaRecorridoIncompleto` |
| Carpeta inaccesible no fabrica nuevos ni bajas | `test_carpeta_inaccesible_no_fabrica_nuevos_ni_bajas` |
| Solo se registra lo confirmado (huella, aparece/desaparece algo) | `test_solo_se_registra_lo_que_la_persona_vio_y_confirmó`, `test_si_la_carpeta_cambio_tras_revisar_no_se_registra_nada` |
| Archivo que cambia mientras se lee: no se registra su hash; luego sí | `TestArchivoQueCambiaOSeVa::test_si_cambia_mientras_se_lee…` |
| Desaparece entre búsqueda y lectura: no es error | `test_si_desaparece_entre_la_busqueda_y_la_lectura_no_es_un_error` |
| Conserva lo existente; marcador e informe inicial intactos | `test_registra_solo_lo_nuevo_y_conserva_lo_existente` |
| Reenlace conserva fila, vínculo y decisiones | `test_un_archivo_movido_reenlaza_su_ficha…` |
| Reenlace exige que la ruta anterior ya no tenga el archivo | `TestReenlaceExigeAusenciaDelOriginal` |
| Coincidencia ambigua no modifica ninguna ficha | `test_un_contenido_que_coincide_con_varias_filas_desaparecidas…` |
| Copia idéntica: sin segunda fila, ni tocar la copia (también repetida) | `test_una_copia_identica_*` (2 pruebas) |
| Dos confirmaciones a la vez / mismo proceso | `test_dos_confirmaciones_a_la_vez_lanzan_una_sola_ejecucion`, `test_el_registro_incremental_comparte_la_exclusion_con_el_inicial` |
| Exclusión entre procesos (cerrojo ajeno → «ocupado», sin efectos; se suelta al terminar y al fallar) | `TestExclusionEntreProcesos` (3 pruebas) |
| Registro incremental e importación del MISMO contenido a la vez: una sola fila y ambos resultados fieles | `TestCarreraConElImportadorDeDescargas::test_con_el_cerrojo_hay_una_sola_fila…` |
| La carrera era real (el mismo escenario sin el cerrojo duplica) | `…::test_control_negativo_sin_el_cerrojo_el_mismo_escenario_si_duplica` |
| Cerrojo ocupado por el importador → el registro se detiene en «ocupado» sin insertar; por el registro → el importador deja el archivo y reintenta | `…::test_si_el_importador_tiene_el_cerrojo…`, `…::test_si_el_registro_tiene_el_cerrojo…` |
| El cerrojo se libera aunque falle quien lo tenía | `…::test_el_cerrojo_se_libera_al_acabar_la_transaccion_aunque_falle`, `…::test_si_el_ciclo_del_importador_falla_a_medias…` |
| El importador toma el cerrojo antes de buscar por contenido y lo suelta tras el commit del ciclo | `…::test_el_cerrojo_se_toma_antes_de_buscar_por_contenido_y_se_suelta_tras_el_commit_del_ciclo` |
| Con el cerrojo ocupado el importador espera una sola vez, corta el ciclo, deja las descargas y las incorpora en el siguiente | `…::test_si_el_registro_tiene_el_cerrojo_el_importador_deja_el_archivo_y_lo_reintenta` |
| Cada archivo mirado cae en una categoría y el total cuadra; omitidos con su causa | `TestContabilidadYRecuperacion::test_cada_archivo_del_alcance_cae_en_una_categoria…` |
| Commit aplicado con la respuesta perdida: se acredita sin duplicar ni decir «no se hizo nada» | `TestContabilidadYRecuperacion::test_commit_aplicado_con_la_respuesta_perdida…` |
| El límite de 50 incidencias dice el total | `test_registro_incremental::TestLimiteVisibleDeIncidencias` |
| Fallo de un lote: lo confirmado se conserva; buscar de nuevo completa sin duplicar | `TestFalloParcialYRecuperacion` |
| Un fallo no toca el marcador y el resto se registra | `test_un_fallo_no_toca_el_marcador_y_el_resto_se_registra` |
| La adopción no se da por completa tras un recorrido parcial (sin marcador, no «completo», pantalla, continúa) | `tests/test_adopt_recorrido_parcial_pg.py` (7 pruebas) y `test_registro_incremental::TestEstadoConRecorridoIlegible` |
| Sin automatismo | `test_el_unico_que_lanza_el_registro_incremental_es_la_pantalla` |
| Textos: rutas sin registrar, aviso de lectura, ignorados no se reactivan, sin palabras internas | `test_registro_incremental::TestPantallaIncremental`, `TestPantallaRecorridoIncompleto` |

## 9. Pruebas y lo que NO se ha ejecutado

- `tests/test_registro_incremental_pg.py` (Postgres y ficheros reales): inventario sin leer ni escribir; huella; carpeta inaccesible; registrar solo lo nuevo
  conservando lo existente (ids, metadata, originales intactos, marcador y informe inicial sin tocar); repetir; alcance confirmado; copia idéntica (también repetida);
  archivo movido; ambigüedad (y que el registro inicial no cambia); fallo sin tocar el marcador; pantalla; huella obsoleta; dos confirmaciones a la vez; exclusión
  compartida; que solo la pantalla lanza el registro.
- `tests/test_registro_incremental.py` (sin BD): huella, cuentas del estado y textos de la pantalla.
- **Medición sintética LOCAL (no la Pi)** — `scripts/medicion/medir_registro_incremental.py`: 1.300 `.cbz` de 12 imágenes pequeñas (100 ya registrados + 1.200 nuevos), x86, Python 3.14,
  Postgres local, ficheros en caché de disco. Buscar (solo rutas): **0,02 s**. Registrar los 1.200: **8,6–8,8 s** (≈ 7 ms/archivo, 5,7 s de CPU), pico de memoria del proceso **83 MiB**, 0 errores. Segunda búsqueda: 0 nuevos.
  Sirve para comprobar que el coste crece de forma lineal y acotada; **no** predice la Pi ni el USB (los archivos reales pesan decenas de MB y el disco no está en caché).
- **NOT RUN:** coste en la Pi con >1000 archivos (criterio 9 de #326) y con el disco USB real; memoria y E/S en la Pi; ejecución sobre la biblioteca real.
