# Especificación — BL-R9: Reescanear la biblioteca (a demanda y periódico)

> Ficha de referencias: `docs/design/benchmark-BL-R9-rescan-biblioteca.md` (2026-11-06).
> Decisión del PO (2026-11-06, sobre las recomendaciones de la ficha): ver §1.
> `main` de partida: `f58274e`. Estado: **especificación para implementar**.

## 1. Decisiones del PO

| # | Decisión abierta de la ficha | Decisión del PO |
|---|---|---|
| 1 | Confirmación humana en el modo periódico | **Sin confirmación** en el periódico: lo identificado con confianza se añade a su serie; lo dudoso va a «Por revisar». El modo manual conserva la garantía junto a la acción. |
| 2 | Cadencia y valor por defecto | **Diaria** (`rescan_interval_minutes = 1440`); `0` desactiva el periódico. Ajuste de `.env`, como los demás intervalos. |
| 3 | Contenido sustituido | **Sí**: se persiste el stat (`file_size_bytes` ya existe + `file_mtime_ns` nueva) por ruta; si cambia, se re-triajea y se actualiza la fila o pasa a revisión. |
| 4 | Dónde vive el botón | **Auditoría**, junto al registro existente. |
| 5 | Watchdog | **No** en esta entrega (registrado como mejora futura). |

## 2. La operación «Reescanear la biblioteca»

Recorre la biblioteca UNA vez por ejecución, sin consultar fuentes externas, sin mover ni renombrar
ningún fichero, y decide por archivo (tabla de resultados):

| Situación en disco | Acción | Categoría del informe |
|---|---|---|
| Ruta sin fila, contenido nuevo, identificado con confianza | Fila nueva enlazada a serie/número (mismo camino que `adopt`) | «registrados» |
| Ruta sin fila, sin identificar | Fila nueva `unsorted` → aparece en «Por revisar» | «a revisar» |
| Ruta sin fila cuyo hash coincide con una fila desaparecida (movido) | Reenlace de la fila (contrato `_reenlazar_fila`); con varias, ninguna | «reenlazados» / «ambiguos» |
| Ruta sin fila cuyo hash coincide con una fila presente (copia) | No se crea fila (idempotencia del dedupe) | «repetidos» |
| Ruta con fila, stat sin cambios | No se abre el CBZ: solo se cuenta | «sin cambios» |
| Ruta con fila, stat cambiado (o `file_mtime_ns` NULL: línea de base) | Re-triaje por contenido: actualizar hash/size/mtime/nombre/`metadata`; si ahora identifica otra publicación → actualizar vínculo; si no identifica → desvincular y a «Por revisar»; si es copia de otra fila presente → conservar vínculo y avisar | «re-triados» (con sub-causa) |
| Ruta con fila `review_dismissed` y stat cambiado | Actualizar solo el stat; NO se reactiva el descarte (regla #326) | «re-triados» (descartado, sin tocar) |
| Ruta con fila desaparecida | `is_missing`/`missing_since`; reaparece → revierte (B7, sin cambios) | «desaparecidos» / «reaparecidos» |
| Raíz inaccesible / vacía / desaparición masiva | Guardarraíles de B7: no se marca nada, categoría «no revisado» | «no revisado» |
| Archivo ilegible o que cambia mientras se lee | Omitido con causa (contrato #326/#332) | «omitidos» |

**Dónde se guarda el stat:** todo escritor de un hash guarda también el stat que lo describe
(`file_size_bytes` + `file_mtime_ns`): importador, adoptador, reenlace, re-triaje y el reemplazo del
etiquetador (B6). Regla: *el stat guardado describe los bytes del hash guardado*.

**Exclusión:** el rescan toma el mismo cerrojo de ciclo `(326,2)` que el ciclo del importador (nunca
coinciden) y comparte el cerrojo de contenido `(326,1)` dentro del triaje (contrato #326 §6.5). Un
segundo rescan en curso no se duplica: estado en memoria y «ocupado» honesto.

**Informe:** `ImportRun` con `details["kind"]="rescan"` (así la lectura de #231 —que excluye `kind`— no
lo lee como «el último ciclo») + contadores y categorías. El estado en memoria (progreso) vive en el
módulo del servicio, como `comprobacion_disco` y `registro_biblioteca` (se pierde al reiniciar; el
informe persistido no).

**Sin automatismo del registro incremental:** el rescan NO pasa por `registro_biblioteca.iniciar`;
#326 sigue siendo manual y su test («solo la pantalla lanza el registro») sigue en verde.

## 3. Piezas

| Pieza | Cambio |
|---|---|
| Migración `0021` | `ALTER TABLE files ADD COLUMN file_mtime_ns BIGINT` (nullable, sin default). Downgrade la quita. One-shot. |
| `models.File` | `file_mtime_ns: Mapped[int|None]` (BigInteger). |
| `services/importer.py` | `_import_file` y `_reenlazar_fila` escriben `file_mtime_ns` (el stat que describe el hash). |
| `services/library_adopter.py` | `_adopt_file` escribe `file_mtime_ns`; nuevo método `rescanear(...)` que parte el recorrido en nuevos / cambiados / iguales y re-tría los cambiados reutilizando `_triage_and_match`; informe y persistencia propios (`kind="rescan"`). |
| `services/rescan_biblioteca.py` (nuevo) | Estado en memoria (`EstadoRescan`), `iniciar_manual`, `ejecutar_automatico`, cerrojo `(326,2)` reutilizado, `detener`. Patrón de `comprobacion_disco.py`. |
| `services/tagger.py` | Al reemplazar el CBZ (B6) y al reconciliar, actualiza `file_mtime_ns` con el hash. |
| `config.py` | `rescan_interval_minutes: int = Field(default=1440, ge=0)` (0 = apagado) + `.env.example`. |
| `main.py` | Bucle `_rescan_loop` (solo si el intervalo > 0); se registra en `lifespan` con los demás; `detener` en el apagado. |
| `web/auditoria.py` + plantilla | Bloque «Reescanear la biblioteca» en Auditoría: botón (POST `/ui/auditoria/rescanear`), fragmento de estado con polling mientras corre, resultado con las categorías y la garantía U21 junto a la acción. |
| Tests | `tests/test_rescan_biblioteca_pg.py` (Postgres y ficheros reales), `tests/test_rescan_biblioteca.py` (sin BD), actualizaciones puntuales de regresión. |

## 4. Criterios de aceptación ↔ pruebas

Los 14 casos semilla de la ficha §8, más los de las decisiones del PO:

1. Ruta nueva identificada → fila enlazada; sin identificar → «Por revisar» sin pasos manuales (test pg).
2. Idempotencia: repetir no duplica; segundo rescan sin cambios informa «sin cambios» (test pg).
3. Stat cambiado → re-triaje: misma publicación (mejor copia) actualiza la fila sin tocar el vínculo;
   otra publicación → actualiza el vínculo; sin identificar → desvincula y pasa a «Por revisar» (test pg).
4. Cambio que conserva tamaño y mtime: no se detecta — límite declarado y testeado (test pg).
5. `review_dismissed` + contenido cambiado: solo stat, no se reactiva el descarte (test pg).
6. Desaparecido → `is_missing`; reaparece → revierte; la fila nunca se borra (test pg).
7. Movido → reenlace; ambigüedad → no se reenlaza (test pg).
8. Rescan manual vs ciclo del importador (cerrojo `(326,2)`): «ocupado» honesto, sin efectos (test pg).
9. Segundo disparo con un rescan en curso → no se duplica (test unitario del estado).
10. Raíz inaccesible → «no revisado», no excepción; desaparición masiva → guardarraíl (test pg).
11. ~1.500 rutas sin cambios → solo stats, sin abrir un CBZ (test con conteo de lecturas).
12. Sin red: el rescan no llama a fuentes (mock, cero llamadas).
13. Informe persistido con `kind="rescan"` y legible con el contrato de #231 (test pg).
14. El test de #326 «solo la pantalla lanza el registro» sigue en verde (regresión).
15. La línea de base (`file_mtime_ns` NULL) se re-tría una sola vez y queda fijada (test pg).
16. El etiquetador (B6) mantiene el stat coherente tras reemplazar un CBZ (regresión).
17. Periódico: solo el bucle de `main` lanza `ejecutar_automatico`; con intervalo 0 no se arranca (test).
18. UI: botón en Auditoría, garantía U21 junto a la acción, textos en español llano, sin palabras internas.

## 5. Límites declarados

- Watchdog/inotify: fuera de esta entrega (decisión del PO).
- Un cambio que conserva tamaño y mtime no se detecta (guarda de cobertura, no instantánea).
- El estado en memoria del rescan se pierde al reiniciar; el informe persistido no.
- Coste en la Pi con la biblioteca real: NOT RUN hasta ejecutarse allí (medición sintética local sí).
- Sin «Anterior» ni filtros por carpeta en el informe: una sola operación por biblioteca.
- El rescan periódico y el ciclo del importador se excluyen: si coinciden, uno espera al otro (cerrojo sin espera: el perdedor se salta ese turno y consta en su informe).

## 6. Garantías heredadas que no se tocan

- `adopt` inicial e incremental (#326): sin cambios de comportamiento.
- B7 (`is_missing`, guardarraíles): sin cambios; el rescan llama la misma comprobación.
- #231/#232 (disponibilidad y «Comprobar el disco»): sin cambios; el rescan es otra operación con su
  propio `kind`, que esas lecturas excluyen por diseño.
- No hay migración destructiva ni dependencia nueva; el cerrojo de ciclo `(326,2)` se comparte a
  propósito (una sola operación de disco a la vez).

## 7. Medición sintética local (no es la Pi)`scripts/medicion/medir_rescan_biblioteca.py` (2026-11-06, Postgres 15 en contenedor local, **no la
Pi**, ficheros en caché de disco): 1.300 `.cbz` de 12 imágenes pequeñas (100 registrados + 1.200
nuevos), x86, Python 3.14.

| Pasada | Resultado |
|---|---|
| Rescan 1 — 1.200 nuevos (leer y registrar) | **18,6 s** (CPU 11,8 s), pico RSS **88 MiB**, 0 errores |
| Rescan 2 — 1.300 sin cambios (solo `stat`) | **0,28 s** (CPU 0,2 s), sin abrir un solo CBZ |
| Rescan 3 — 10 sustituidos (re-triaje) | **0,48 s** |

Confirma que el coste de la pasada periódica es el paseo de rutas (no el contenido) y crece de forma
lineal; **no** predice la Pi ni el USB (los archivos reales pesan decenas de MB y el disco no está en
caché). Coste en la Pi con la biblioteca real: **NOT RUN**.

## 8. Revisión del peer review (2026-11-06) — decisiones y ajustes

El revisor (rol SCOUT.bench) entregó «aprobar con cambios» sobre los commits `0783d4a`→`d644b1d`.
Resolución por hallazgo:

| Hallazgo | Decisión |
|---|---|
| B1: el fragmento reventaba tras reiniciar el proceso (`_resumen` no entendía el dict persistido → 500) | **Corregido**: `_resumen` normaliza dict y `RescanReport`; regresión en `test_el_fragmento_tras_reinicio_pinta_el_informe_persistido` |
| M1: el automático se disparaba al arrancar (la primera pasada es la más cara) | **Corregido**: el primer paseo espera un intervalo completo (`rescan.first_delayed`); el checklist recomienda lanzar la línea de base a mano |
| M2: la UI callaba el guardarraíl de disponibilidad (`resultado_biblioteca`) | **Corregido**: el fragmento lo pinta con el vocabulario observacional de #231 («no se han marcado archivos…») |
| m1: presupuesto de texto U21 | **Corregido**: entrada ≤ 50 palabras; el detalle va en `<details>` |
| m2: `metadata_source` se borraba al re-triar | **Decidido**: se conserva; un ComicInfo nuevo solo lo actualiza si no era `manual` (protección del enricher) |
| m3: doble contabilidad con commit de lote fallido | **Corregido**: los contadores del lote se revierten y pasan a «por comprobar»; regresión pg |
| m4: rama `recuperar` (contenido = fila desaparecida) sin contrato | **Declarado**: la fila sigue en su ruta, conserva el vínculo y se actualiza el stat; cuenta como `re_triados_igual` |
| m5: `copias_de_otra` no se pintaba | **Corregido**: línea propia en el resumen |
| m6: `stat` fallido en `_partir` no contaba | **Corregido**: suma a `unreadable` y enciende `no_revisado` |
| s1: seq scan sobre `import_runs.details` | **Diferido**: medir en la Pi; si molesta, columna `kind` o índice GIN |
| s2: `original_sha256` describe el tebeo sustituido | **Declarado**: no se toca (contrato «tal como se importó», `models`); el dedupe por `original_sha256` sigue valiendo para la copia original |
| s3: línea de base NULL + fichero ilegible se reintenta | **Declarado**: correcto; no se fija un stat no acreditado |
| s4: caminos de fallo de commit sin prueba | **Corregido**: dos pruebas pg nuevas (lote fallido e informe final fallido) |
| s5: el rescan no mira el marcador de adopción | **Declarado**: el rescan usa `adopt(alcance=…)`, que no toca el marcador; con el registro inicial a medias, lo que ve se registra y el registro inicial sigue ofreciéndose |
| s6: un rescan con nuevos escribe dos `ImportRun` | **Declarado**: el `kind="registro_incremental"` de `adopt` es el registro de los nuevos; el `kind="rescan"` es el informe de la operación completa |
