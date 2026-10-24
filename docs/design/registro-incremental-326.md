# Registro incremental de la biblioteca (#326)

> Estado: **implementado en una PR en borrador; revisión 1 atendida** (recorrido incompleto, exclusión entre procesos, archivo que cambia, reenlace con original presente). Parte del refinamiento v1 de #326 (2026-10-23). Las decisiones marcadas «por defecto»
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
  vuelve a salir en la siguiente búsqueda. *Límite:* un cambio que conserve tamaño **y** fecha no se detecta.
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
- **Si se pierde la respuesta o se cierra la página:** el registro sigue en segundo plano y la pantalla recupera el estado en curso. *Límite:* el estado vive en memoria (se pierde
  al reiniciar el proceso); el informe persistido (`registro_incremental`) se escribe al terminar. Tras un reinicio se busca de nuevo y lo ya confirmado consta.
- **Continuar:** «Buscar archivos sin registrar otra vez» vuelve a calcular qué falta; es idempotente por ruta (`files.file_path` es único), así que repetir no duplica.
- **Pulsar confirmar dos veces / dos pestañas / dos procesos:** el botón se deshabilita; en el proceso, una sola ejecución; entre procesos, el cerrojo de Postgres.
- **Cancelación:** no hay botón de cancelar. Parar el proceso deja lo confirmado y el cerrojo se suelta solo (Postgres lo libera al cerrarse la conexión).

### 6.4 «Sin registrar» no es «tebeo nuevo»
La búsqueda no lee contenido, así que la pantalla habla de **rutas sin registrar** («archivos encontrados sin registrar») y lo dice: aún no se sabe si son tebeos distintos de los
que ya tienes. El resultado separa fichas nuevas, reenlaces, repetidos, no atribuidos, errores y de otra ejecución; los errores y los no atribuidos se listan **uno a uno con su causa**
(hasta 50 en pantalla). Una copia que sigue en la carpeta vuelve a salir en cada búsqueda y se informa como repetida; nunca crea una segunda fila.

## 7. Límites conocidos (no resueltos)

- **Cobertura del cerrojo:** protege los registros de `LibraryAdopter` (inicial e incremental) entre procesos. **No** lo toma el importador de descargas: un archivo con el mismo
  contenido que llegue por descargas mientras se registra desde la biblioteca podría, en teoría, crear dos filas (no hay restricción única por contenido en la base; ambos
  comprueban el hash antes de insertar, así que la ventana es mínima). Cerrarlo exige una restricción única o que el importador también tome el cerrojo (decisión pendiente).
- **Cambios que conservan tamaño y fecha** no se detectan al leer (§6.1).
- **Un contenido distinto en una ruta ya registrada** (archivo sustituido) no se detecta: es otro problema, no una alta.
- **Los formatos fuera de `COMIC_EXTS`** (`.rar`, `.tar`…) no se cuentan aquí: los enseña «Revisar mi biblioteca».
- **Rutas anteriores en otro disco:** un reenlace cuya ruta vieja cuelga de otro disco no se hace (no se puede afirmar que falte).

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
| Fallo de un lote: lo confirmado se conserva; buscar de nuevo completa sin duplicar | `TestFalloParcialYRecuperacion` |
| Un fallo no toca el marcador y el resto se registra | `test_un_fallo_no_toca_el_marcador_y_el_resto_se_registra` |
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
