# Disponibilidad de los archivos y resultado de la comprobación (BL-R2, #231)

> Contrato **implementado** de la historia #231 (hija de #228), sobre `main` `b7e8a09`. Ficha de referencias: `docs/design/benchmark-reconciliacion-plex.md`
> (§10, Sonarr/Radarr leídos el 2026-10-28). **Sin migración**: todo vive en `import_runs.details` (JSONB) y en las columnas que ya existían.
> No cambia umbrales ni reglas de baja de B7.

## 1. Qué hace

1. El ciclo del importador **anota lo que observó** al revisar la biblioteca: `details["comprobacion_biblioteca"]`.
2. **Estado** (`/estado`) enseña ese resultado arriba, con enlace a la lista.
3. **`/ui/no-disponibles`** lista, de solo lectura y paginada, los archivos con `is_missing`.
4. Nada de esto toca el disco al mostrarse (decisión del PO, 2026-10-24).

## 2. El esquema (`details["comprobacion_biblioteca"]`)

| Campo | Contenido |
|---|---|
| `ambito` | `"biblioteca"` (único valor hoy; #232 podrá añadir otros) |
| `resultado` | `comprobada` · `raiz_inaccesible` · `raiz_vacia` · `desaparicion_masiva` · `fallo_deteccion` (`ResultadoComprobacion`, `models/__init__.py`) |
| `archivos_registrados` | filas de `files` en el momento; `null` si no se pudo contar |
| `ausentes` | rutas registradas que no estaban; `null` si no se llegó a mirarlas |
| `bajas_omitidas` | `true` salvo en `comprobada` |
| `fecha` | cuándo hizo el ciclo esa comprobación (ISO 8601, UTC) |

- **Quién lo escribe:** `Importer._persist_run`, en la misma transacción que el `ImportRun` (`ImportReport.comprobacion`).
- **Quién lo lee:** `services/disponibilidad.py`. #232 puede reutilizarlo al lanzar la comprobación a mano: el esquema no depende de quién la dispare.
- **Cómo se distingue un ciclo del importador:** su `details` **no lleva `kind`**; auditoría, adopción y registro incremental sí. La lectura exige `kind` ausente, de modo que ningún otro informe se lee como «el último ciclo» aunque algún día copiara la clave.
- **Ciclos anteriores** (sin la clave): se leen como **«Sin dato de última comprobación válida»**; no se reconstruye ninguna fecha, ni siquiera si hay una comprobación completa más antigua.
- **«Última comprobación válida»** = la fecha del último ciclo del importador con `resultado == comprobada`. `missing_since` no la sustituye jamás.

## 3. Qué cambia en el ciclo

- `Importer._comprobar_biblioteca()` devuelve un `ComprobacionBiblioteca` (resultado, recuentos, listas de bajas y altas aplicadas). `_detectar_desaparecidos()` se conserva como envoltorio que devuelve las dos listas de siempre.
- `scan_and_import` recoge una **excepción** de la comprobación y la anota como `fallo_deteccion` (antes solo iba al log). No se guarda el texto de la excepción.
- **Un coste nuevo:** con la raíz inaccesible se hace un `COUNT(*)` sobre `files` para dejar el recuento (antes no se consultaba la base en ese camino).
- **`_existe(ruta)` sustituye a `Path(r).exists()`** al buscar ausentes. Hallazgo del criterio 11: `Path.exists()` hasta Python 3.13 solo ignora `ENOENT/ENOTDIR/EBADF/ELOOP`, así que un `EACCES` **subía** como excepción y llegaba al cuarto camino (nunca daba de baja); desde Python 3.14 `exists()` traga todos los errores y habría tratado una carpeta sin permiso de paso como «ausente», dando de baja sus archivos. El proyecto admite `>=3.11` y la imagen usa 3.11, pero el comportamiento no debía depender del intérprete: `_existe` fija el de 3.11 (solo esos cuatro errno significan ausencia; cualquier otro hace fallar la comprobación). **En producción (3.11) el resultado es el mismo que antes.**
- Sin cambios: umbrales (`UMBRAL_DESAPARICION_MASIVA_*`), cuándo se marca una baja, la reversión al reaparecer.

## 4. La lista

- **Orden** (decisión del PO, 2026-10-27): `missing_since` descendente (lo más reciente primero); **los que no tienen fecha, al final**; desempate por nombre y por `id`.
- **Páginas de 100.** Paginación por **cursor** (no `OFFSET`): el token codifica (¿sin fecha?, fecha, nombre, id) del último archivo visto. Si entre dos peticiones un archivo reaparece o llega otro, no se repite ni se salta ninguno de los que seguían por delante. Un token ilegible vuelve al principio.
- **Total visible** en cada página (`COUNT`). Sin «Anterior»: hay «Volver al principio» y «Ver los siguientes» (límite aceptado, §6).
- Cada fila: nombre, serie y número si el archivo sigue vinculado (si se desvinculó, ADR 0014: «sin vincular a ninguna serie»), y desde cuándo.
- **Consultas:** lista = 4 (último ciclo, última válida, total, página); Estado = 3. Ninguna escribe; ninguna toca el disco.
- **Error de lectura:** la lista responde 503 con «No se ha podido leer la lista… esto no significa que todo esté disponible»; Estado sigue sirviéndose y lo dice. Nunca una lista vacía que parezca «todo disponible». El texto de la excepción no llega a la pantalla (solo la clase, en el log).

## 5. Redacción: qué se afirma y qué no

Se describe **lo observado** y **lo que hizo el guardarraíl**, nunca una causa. Ningún mensaje contiene «desmontado», «perdido» ni «borrado» (lo comprueba `tests/test_disponibilidad.py::TestMensajes`). «No se han marcado archivos como no encontrados en esta comprobación» significa solo que no se dieron bajas en ese ámbito, no que el catálogo no cambiara.

## 6. Límites (de la primera entrega)

- **Sin causa por archivo** («permiso denegado»…): decidido por el PO el 2026-10-27; obligaría a hacer `os.stat` al navegar.
- **Sin lanzar la comprobación desde la interfaz:** es #232.
- **Sin «Anterior»** en la lista: con cursor, ir hacia atrás exigiría invertir el orden; se ofrece volver al principio.
- **El guardarraíl es global a la biblioteca**, no por serie ni por subcarpeta (ZascArr registra archivos por ruta absoluta; Sonarr/Radarr, carpetas de serie bajo una raíz).
- **`COMPROBADA` con 0 archivos registrados** significa «raíz accesible, nada que comprobar», no «todo bien».
- **Una comprobación completa no acredita que cada archivo sea legible:** solo que la ruta existe (`stat`).
- **La raíz** se comprueba aún con `Path.exists()/is_dir()`: en 3.14 un permiso denegado sobre la propia raíz se leería como `raiz_inaccesible` y en 3.11 como `fallo_deteccion`; ambos omiten las bajas.
- La **vista de archivo individual** («disponible/no disponible» en la ficha de la serie) no se añadió: el estado conocido de un archivo disponible es no estar en la lista; `archivos_por_numero` ya marca `falta_en_disco`.

## 7. Criterios ↔ pruebas

| # | Criterio | Prueba |
|---|---|---|
| 1 | Estado conocido y fecha del archivo | `test_disponibilidad_pg.py::TestPantallas::test_lista_y_estado_con_datos_reales`; `::TestListaDeNoDisponibles::test_250_…` |
| 2 | Raíz no comprobable: se conserva el estado y se dice «sin verificar» | `TestCicloCompletoDelImportador::test_raiz_inexistente_…`, `::test_un_ciclo_con_la_raiz_inaccesible_conserva_…`; `test_disponibilidad.py::TestMensajes` |
| 3 | Guardarraíl: ámbito, motivo, recuento, mensaje y sin cambios en `File` | `test_disponibilidad.py::TestResultadoDeLaComprobacion`; `…_pg.py::test_raiz_vacia_y_desaparicion_masiva` |
| 4 | Raíz vacía sin afirmar desmontaje | `TestMensajes::test_raiz_vacia_describe_lo_observado_sin_afirmar_desmontaje` |
| 5 | No disponible vinculado conserva serie y número | `…_pg.py::test_vinculado_conserva_serie_y_numero_y_desvinculado_no_da_error` |
| 6 | Reaparición | `…_pg.py::test_baja_reaparicion_e_idempotencia` |
| 7 | Fallo de lectura del informe | `test_disponibilidad.py::TestRutas::test_lista_con_lectura_fallida_…`, `::test_estado_sigue_sirviendose_…` |
| 8 | Navegar no modifica nada ni lanza comprobaciones | `TestRutas::test_abrir_la_lista_solo_hace_consultas_de_lectura`; `…_pg.py::test_navegar_no_modifica_nada` |
| 9 | Ciclos antiguos y otros informes en la misma tabla | `…_pg.py::TestLecturaDelUltimoInforme` (3 pruebas) |
| 10 | Archivo desvinculado ausente (ADR 0014) | `…_pg.py::test_vinculado_conserva_serie_y_numero_y_desvinculado_no_da_error` |
| 11 | La detección falla con una excepción | `TestFalloDeLaDeteccion` (incluye la prueba de permisos pedida); `TestExiste` |
| 12 | Más de 100: orden, cobertura, total y cursor estable | `…_pg.py::TestListaDeNoDisponibles` (4 pruebas, incluida la de datos que cambian y la de nombres y fechas repetidos) |
| — | Idempotencia: un ausente que sigue ausente no es baja nueva | `…_pg.py::test_baja_reaparicion_e_idempotencia` |

Las pruebas de la lista se comprobaron con **mutaciones**: cursor con `<=` en vez de `<` (falla), lectura sin excluir `kind` (falla) y desempate sin `id` (falla solo con la prueba de nombres repetidos, que se añadió por eso).

## 8. NOT RUN / no acreditado

- **Rendimiento en la Pi (p95 ≤ 1 s por página, ≤ 5 consultas, ≤ 32 MiB):** NOT RUN. Las consultas por página (4) están acreditadas por construcción; el tiempo y la memoria no se han medido. Medición local sintética: §9.
- **Navegador real y lector de pantalla:** ver el comentario de la PR para lo que sí se hizo; el lector de pantalla, NOT RUN.
- **Despliegue y ejecución con la biblioteca real:** NOT RUN y no autorizados.
- **Aceptación de las decisiones por defecto** de §6 (sin «Anterior», redacción): propuestas, revisables por el PO.

## 9. Medición local sintética (no es la Pi)

`scripts/medicion/medir_disponibilidad.py` (2026-10-28, Postgres 15 en un contenedor local, **no la Pi**): 1.500 archivos registrados,
300 no disponibles con fechas repetidas y 2.500 ciclos del importador (el tamaño de la Pi de referencia a 2026-10-20), 30 repeticiones
con una conexión nueva cada una.

| Operación | Consultas | Mediana | p95 |
|---|---|---|---|
| `ultima_comprobacion` (Estado y lista) | 2 | 22,8 ms | 25,6 ms |
| Lista · primera página (100) | 2 | 24,0 ms | 28,1 ms |
| Lista · página 2 (cursor) | 2 | 24,8 ms | 27,0 ms |
| Lista · página 3 (la última) | 2 | 24,5 ms | 27,0 ms |

Una petición a la lista = 4 consultas (≤ 5 del umbral propuesto); Estado = 3. RSS del proceso: sin aumento medible (91 MiB). **Son cifras de
un portátil, no del hardware de destino:** no acreditan el p95 ≤ 1 s en una Pi 4/5 con la base en su disco. Sigue siendo NOT RUN allí.
