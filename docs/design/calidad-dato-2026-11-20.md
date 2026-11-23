# Calidad del dato de ZascArr — 2026-11-20

> **Medición de solo lectura sobre la Pi.** La medición de referencia se hizo sobre
> `5b9fd994` (2026-11-20 22:22 UTC); a las 22:27 UTC el PO actualizó la Pi a
> `a255e4e3` (merge #1180) y la re-medición posterior es de las 22:48 UTC. Los
> ficheros de las comprobaciones y de `edicion_serie` no cambiaron entre ambos
> SHA. Alembic `0052 (head)`. 258 series, 4.300 números, 5.098 archivos, 77
> Deseados en la medición (54 en el perfil inicial de las 22:05; el ciclo de la
> aplicación siguió). 82
> comprobaciones: 29 con casos, 34 con población y 0 casos (PASS), 17 sin
> población (NOT RUN) y 2 no ejecutables (NOT RUN).
>
> **Actualización 2026-11-21.** La Pi está en `4e48fe5f`; el enricher saneado
> (#1191), el servicio L1 (#1193) y el de lotes L2/L3/L4 (#1202) están
> desplegados. **Aplicados:** L1 (622 sinopsis), L2 (26 vínculos), L3 (9
> pendientes) y L4 (4 `locked_fields`). F4a **0/826**, A1a **0/1.424**, D6a
> **0/606**, F5 **0/2.785**; A1b sube a 347 por el historial legítimo de L2. Ver
> §12 y §13. **L7/L8 revisados (2026-11-21):** L7 sin cambios; F1d/H2/F2a
> sin cambios; **I1 corregido (0/38)**. Total estimado **147**. Ver §14. La
> medición de referencia sigue siendo la del 2026-11-20.
>
> **Actualización 2026-11-23.** La Pi está en `0a58c9bd`; el censo pasa a **83
> comprobaciones** con **B9** (identidad de la serie frente a su registro de
> fuente actual). B9 mide 58 series no manuales: 39 con registro actual y **19
> sin él** (10 con un registro de otro id y 9 sin ninguno); el título y los años
> ±1 no se cuentan. De las 14 diferencias de editorial, se aplican **12** (11
> vacías + SUPERMAN) y quedan 2 variantes de nombre sin tocar. B9 **19/58**; ver
> §16. La medición de referencia de las demás comprobaciones sigue siendo la del
> 2026-11-20.
>
> **Actualización 2026-11-22.** La Pi está en `ce26086a`; el backfill estricto
> de H1 (PR #1215) está desplegado. **Aplicado:** 4 filas de
> `field_provenance` (Tebeosfera) en 58 series; **1 es un campo de H1** y las
> otras 3 quedan fuera de H1. H1 **244 → 243**. Los 243 restantes no tienen un
> valor de fuente que coincida y siguen «origen no registrado». Ver §15.
> Total estimado sin cambios (H1 no entra en él).
>
> **Aviso de precisión.** El PO confirmó «todo como la hipótesis»: la columna
> `etiqueta_esperada` se aceptó sin revisión fila a fila. Por tanto las
> precisiones de §6 son **declaradas**, no medidas con etiquetado independiente.
> Antes de aplicar un lote S1 hay que hacer una comprobación por muestreo de 5
> filas (§7). El CSV local de etiquetado está en
> `.work/muestra-calidad-s1s2-etiquetada.csv` y
> `.work/muestra-calidad-s3-etiquetada.csv` (no versionados).

---

## 1. Qué se midió y qué no

- **Se midió** el catálogo de `scripts/medicion/censo_calidad.py` sobre
  PostgreSQL de la Pi, en una única transacción `READ ONLY` terminada en
  `ROLLBACK`. Sin red, sin fuentes externas, sin recorrer el disco.
- **No se midió** el número que extrae el parser del nombre (`D1b`, NOT RUN) ni
  la existencia de copia local de portada (`I3`, NOT RUN). `C1` es un **proxy
  declarado** (último entero del nombre), no el parser desplegado.
- **B5b** (número local frente al número de la fuente) quedó **sin población**:
  no hay `entity_source_records` de número, solo de serie. No es PASS.
- La evidencia de fuente es escasa: 57 registros de serie (45 Comic Vine, 9
  Tebeosfera, 3 GCD) y 22 filas de `http_cache`. B1a/B7 se miden sobre esa
  cobertura; B1c mide lo que queda fuera.

## 2. Versión y referencias de la Pi

| Dato | Valor |
|---|---|
| SHA desplegado | `a255e4e3b0e58ea5ac149e289aa063641cf6ab60` (actualización de las 22:27 UTC) |
| SHA de la medición inicial | `5b9fd994d8b6e2b066426156b04892e890849e1d` |
| `origin/main` revisado | `a255e4e3` (merge #1180; los ficheros de las comprobaciones no cambiaron) |
| Alembic | `0052 (head)` |
| Último ciclo del importador | 2026-11-20 21:55:09 UTC |
| Última comprobación válida de biblioteca | 2026-11-20 21:55:10 UTC |
| Fuentes | todas encendidas; `fuentes_heredadas=false` |
| Huella del censo | `eeaa30de65ffe09a` |

## 3. Perfil del dato

| Tabla | Filas | | Tabla | Filas |
|---|---:|---|---|---:|
| series | 258 | | files | 5.098 |
| issues | 4.300 | | wishlist | 77 |
| collections | 27 | | reading_progress | 29 |
| publishers | 17 | | story_arcs / issues | 3 / 67 |
| creators | 105 | | import_runs | 5.619 (5.622 después) |
| entity_source_records | 57 | | field_provenance | **2** |
| http_cache | 22 | | upgrade_proposals | 0 |

- **Series:** 225 `regular`, 23 `annual`, 10 `one_shot`. Tradición: 217
  `american`, 29 `tebeo`, 7 `manga`, 4 `franco_belgian`, 1 `other`.
- **Fuente declarada:** 195 `manual`, 47 `comic_vine`, 9 `tebeosfera`, 2 `gcd`,
  5 sin fuente. 200 series sin ningún id de fuente, 57 con uno, 1 con dos.
- **Números:** 4.223 `single_issue`, 41 `graphic_novel`, 35 `trade_paperback`,
  1 `hardcover`; 44 con `issue_number` NULL.
- **Archivos:** 4.539 `.cbr`, 555 `.cbz`, 3 `.pdf`, 1 `.cb7`. Por contenido:
  4.196 RAR, 891 ZIP que son tebeo (incluye `.cbr` que por dentro son ZIP),
  5 ZIP `no_tebeo`, 2 `anidados`, 3 `otro`, 1 7z.
- **Nulos:** 606 archivos sin número; 0 sin `root_id`; 0 sin hash; 4.213 de
  4.300 números sin `page_count`; 211 series sin editorial; 71 sin
  `start_year`; 197 sin `total_issues`.
- **Procedencia:** solo 2 filas de `field_provenance` para 57 fichas de fuente.
- **Portadas:** 53 series con `cover_url` externa; sin dato de copia local.
- **Deseados:** 54 filas; ninguna con `issue_id` activo (E4a sin población).

## 4. Hallazgos

### 4.1 Con casos (29 comprobaciones)

`D` = defecto, `L` = legítimo, `NS` = no sé. La precisión se calcula sobre
`D+L`; la estimación es `casos × precisión`, con intervalo Wilson al 95 % cuando
la muestra es menor que los casos. «Exacto» = se etiquetaron todos los casos.

| id | S | Población | Casos | Muestra | D/L/NS | Precisión | Estimación | Estado | Causa |
|---|---|---:|---:|---:|---|---:|---|---|---|
| B5a | S1 | 607 | 75 | 20 | 20/0/0 | 100 % | 75 [63–75] | FAIL | `retirar_asociacion` no limpia ids de número (vivo) |
| B1b | S1 | 29 | 1 | 1 | 1/0/0 | 100 % | 1 exacto → **0 tras L6** | FAIL → PASS | año de la fuente distinto para el id vigente |
| D6b | S2 | 4.492 | 3.470 | 20 | 0/20/0 | 0 % | 0 [0–559] | LEGÍTIMO | convención: `match_status` no se actualiza al vincular |
| C2c | S2 | 4.223 | 38 | 20 | 20/0/0 | 100 % | 38 [32–38] | FAIL | anual/decimal como grapa (dato) |
| A1a | S2 | 1.450 | 26 | 20 | 20/0/0 | 100 % | 26 [22–26] → **0 tras L2** | FAIL → PASS | `DELETE /api/series` heredado (vivo/heredado) |
| C2b | S2 | 4.412 | 23 | 20 | 20/0/0 | 100 % | 23 [20–23] | FAIL | tomo/ómnibus como grapa (dato) |
| C1 | S2 | 4.370 | 17 | 17 | 0/0/17 | — | sin medir | SIN MEDIR | proxy del parser |
| B6c | S2 | 32 | 9 | 9 | 0/0/9 | — | sin medir | SIN MEDIR | ids sin sello de intento |
| D6a | S2 | 606 | 9 | 9 | 9/0/0 | 100 % | 9 exacto → **0 tras L3** | FAIL → PASS | `match_status` colgado tras borrado heredado |
| B3b | S2 | 10 | 6 | 6 | 0/0/6 | — | sin medir | SIN MEDIR | Tebeosfera en americana |
| C2a | S2 | 10 | 4 | 4 | 4/0/0 | 100 % | 4 exacto | FAIL | `single_issue` en `one_shot` (ADR 0022) |
| C3a | S2 | 10 | 4 | 4 | 0/0/4 | — | sin medir | SIN MEDIR | `#1` en `one_shot` |
| D4c | S2 | 4.297 | 3 | 3 | 3/0/0 | 100 % | 3 exacto | FAIL | número sin ningún archivo |
| B2b | S2 | 47 | 2 | 2 | 0/0/2 | — | sin medir | SIN MEDIR | tradición no americana con CV |
| B7 | S2 | 55 | 2 | 2 | 0/0/2 | — | sin medir | SIN MEDIR | título de fuente distinto |
| B8 | S3 | 50 | 10 | 10 | 0/0/10 | — | sin medir | SIN MEDIR | evidencia de un id no vigente (explica 8 de los 9 B1b) |
| B9 | S2 | 58 | 19 | 19 | 0/0/19 | — | 19 sin medir | SIN MEDIR (no sé) | serie con fuente sin registro actual: id no verificable (19) |
| G1 | S2 | 258 | 2 | 2 | 0/0/2 | — | sin medir | SIN MEDIR | pareja de series duplicadas |
| H2 | S2 | 1 | 1 | 1 | 1/0/0 | 100 % | 1 exacto | FAIL | procedencia contradice la fila |
| F4a | S3 | 593 | 583 | 20 | 20/0/0 | 100 % | 583 [489–583] → **0 tras L1** | FAIL → PASS | enricher guarda HTML (vivo; corregido) |
| A1b | S3 | 322 | 321 | 20 | 0/20/0 | 0 % | 0 [0–52] | LEGÍTIMO | historial append-only (ADR 0014) |
| H1 | S3 | 245 | 244 → **243 tras backfill** | 20 | 0/0/20 | — | sin medir | SIN MEDIR (aceptado) | CCM apenas ejecutado; 243 aceptados |
| C4b | S3 | 4.256 | 78 | 20 | 0/0/20 | — | sin medir | SIN MEDIR | formatos de número |
| E1 | S3 | 57 | 16 | 16 | 0/0/16 | — | sin medir | SIN MEDIR | total sin unidad acreditada |
| D5 | S3 | 5.098 | 15 | 15 | 0/15/0 | 0 % | 0 exacto | LEGÍTIMO | contrato #307: extensión declarada |
| F4b | S3 | 258 | 12 | 12 | 0/0/12 | — | sin medir | SIN MEDIR | ruido de título |
| F5 | S3 | 2.786 | 4 | 4 | 4/0/0 | 100 % | 4 exacto → **0 tras L4** | FAIL → PASS | `locked_fields` inexistentes |
| F1d | S3 | 3 | 3 | 3 | 3/0/0 | 100 % | 3 exacto | FAIL | `end_year` con serie en curso |
| F2a | S3 | 46 | 1 | 1 | 0/0/1 | — | sin medir | SIN MEDIR | editorial española/americana |
| I1 | S3 | 29 | 1 | 1 | 1/0/0 | 100 % | 1 exacto → **0 tras L8** | FAIL → PASS | progreso incoherente |

**Estimación puntual:** S1 76 antes de L6 y **75 después** (B5a) · S2 104 · S3 591
(F2a y B8 excluidos por quedar «sin medir»). Total **771 → 770** defectos estimados,
intervalo aproximado **652–770**; las cifras se solapan entre comprobaciones y no
corrigen la falta de etiquetado independiente. **Tras L1 (2026-11-21):** S3
**591 → 8** (F5 4, F1d 3, I1 1); total **770 → 187**. **Tras L2/L3/L4
(2026-11-21):** S2 **104 → 69** (A1a y D6a resueltos); S3 **8 → 4** (F5
resuelto); total **187 → 148**. A1b sube de 321 a 347 por las 26 entradas de
historial de L2; es el comportamiento legítimo de ADR 0014. **Tras revisar
L7/L8 (2026-11-21):** L7 sin cambios; F1d/H2/F2a sin cambios; I1 corregido
(1 → 0). S3 **4 → 3** (F1d 3); total **148 → 147**.

### 4.2 PASS (población > 0 y 0 casos)

No es «no hay defecto»: es «esta consulta no encuentra ninguno en esta
población». Los más fuertes por tamaño: A4b (5.098 rutas), A5a/A5b (5.098),
C3b (4.300), D2a/D2b (4.492), D4a (5.098), B6a (3.075), C4a (1.112).

`A2(107), A3(23), A4b(5.098), A4c(1), A5a(5.098), A5b(5.098), A6(43),
B2a(47), B4a(1), B4b(1), B6a(3.075), B6b(2), C3b(4.300), C4a(1.112),
C5a(10), C5b(2), C6(251), D2a(4.492), D2b(4.492), D4a(5.098), D4b(5.583),
E4b(76), E4c(76), F1a(3), F1b(187), F1c(36), F2b(1), F3a(23), F3b(23),
G2a(17), G2c(105), G3(4), G4a(27), G4b(1).`

Notas: B4a/B4b tienen población 1 (solo una serie con `asociaciones`): PASS
débil. G2c es PASS **por restricción** (`uq_creators_name_norm`, migración 0023),
no por ausencia de datos. D4b es PASS porque el último ciclo es reciente y
`comprobada`.

### 4.3 SIN POBLACIÓN (NOT RUN, no PASS)

`A4a` (no hay `volume IS NULL` con número), `A5c` (no hay `root_id` NULL),
`B1a`/`B1c` (no hay serie con id y `start_year` NULL), `B3a` (no hay
`anilist_id`), `B3c` (no hay slug de Fandom), `B5b` (no hay
`entity_source_records` de número), `D1a` (no hay correspondencias de carpeta),
`D3a`/`D3b`/`D3c` (no hay `covered_issue_ids`), `E2` (no hay tebeo con CV y
total), `E3` (no hay `no_completar`), `E4a` (no hay deseo con `issue_id`
activo), `G2b` (no hay sellos), `H3` (no hay discrepancias), `I2` (no hay
mejoras).

Algunas pueden volverse medibles con uso (D3, E3, I2); otras no aplican a esta
instalación (B3a/B3c). Ninguna se cuenta como PASS.

### 4.4 NOT RUN

- **I3** portada externa sin copia local y fallos recordados: exige recorrer
  `covers/externa/` y `covers/v3/fallos/`; no se recorre el disco sin permiso.
- **D1b** título del parser frente a la serie: exige ejecutar
  `naming.parse_comic_filename` de la versión desplegada; se hará en el
  diagnóstico con el parser fijado al SHA de la Pi.

## 5. Diagnóstico de causa (S1 y S2 principales)

### [B5a] Números con id de Comic Vine en series sin id de volumen — S1 — VIVO/POR CONFIRMAR

- **Población:** 607 números con `comic_vine_id`. **Casos:** 75 (12,4 %);
  muestra 20/20 defecto. La evidencia agrupa los 75 en **4 series**: 56, 13, 5 y
  1 números.
- **Síntoma:** el número conserva el id de un volumen que la serie ya no tiene.
  Si se vuelve a asociar el volumen correcto, el enricher **no** rellena esos
  números (`_enrich_issues_batch` filtra `Issue.comic_vine_id IS NULL`), así que
  la ficha puede seguir mostrando datos del volumen viejo y el nuevo nunca
  completa.
- **Evidencia:** `enricher.py:1029` escribe el id de número y `:1000-1010` solo
  selecciona números con el id vacío. Las 4 series **no tienen**
  `comic_vine_id`, ni asociación activa en JSONB, ni entrada en
  `asociaciones_historial`: el id de volumen se perdió sin procedencia. No se
  puede atribuir a `retirar_asociacion` con estos datos; esa ruta, en su versión
  actual, sí dejaría los ids de número huérfanos (prevención), pero no consta que
  sea la que produjo estos 4.
- **Causa:** id de volumen perdido sin historial (ruta no determinada:
  versión anterior, edición directa o metadata sobrescrita). Los ids de número
  quedaron.
- **Falsos positivos:** ninguno en la muestra; la contradicción serie/número es
  real en los 75.
- **Propuesta:** pregunta L5 por serie: ¿qué volumen de Comic Vine corresponde
  (asociar) o se limpian los ids de número? La lista de las 4 series está en
  `.work/evidencia-s1-v2.txt` (local).

### [B1b] Año de la serie a más de 1 del año de la fuente — S1 — POR CONFIRMAR

- **Población corregida:** 29 series con año, id de Comic Vine y registro de
  fuente **de ese mismo id**. **Casos:** 1 (3,4 %); muestra 1/1.
- **Qué pasó con los 9 iniciales:** 8 eran `entity_source_records` de ids
  anteriores, no de la ficha vigente; no son B1b. Se miden en B8 (10 registros
  históricos). Esta fue la corrección que hizo la evidencia: el check unía
  cualquier registro de la serie, no el del id vigente.
- **Síntoma del caso que queda:** el año local (1987) y el de la fuente (1990)
  difieren en 3; puede ser un volumen distinto o una convención de la fuente.
- **Causa:** por confirmar. `enricher.py:970 _pick_by_year` y `:858` siguen
  siendo el riesgo vivo, pero con un solo caso no se puede afirmar que sea un
  volumen homónimo.
- **Aplicado (L6, 22:48 UTC):** el PO aprobó corregir el año local a 1990. Se
  usó `EdicionDeSerie` en una transacción; la fila quedó `start_year=1990`,
  `updated_at=2026-11-20 22:48:24 UTC`. B1b pasó de **1/29 a 0/29**. La copia
  previa es el dump de la actualización `update_20261120_232733.sql.gz`
  (`/var/backups/zascarr/postgres/`, SHA-256
  `5d6e1709d612b9df6dc403dc745660ab1e25712f06a80e3977b86ead02937bf6`), más la
  copia diaria de las 22:22 (`backup_20261120_222250.sql.gz`, SHA-256
  `3cff3d22f4502d8c91ed89bc4af6894f9e845fe70d6937673da0e6c9acb45b2a`).

### [F4a] Sinopsis con HTML o entidades — S3 — APLICADO

- **Población:** 593 números con sinopsis. **Casos:** 583 (98,3 %); muestra
  20/20 defecto.
- **Síntoma:** la sinopsis enseña `<p>`, `<br>` o `&amp;` en vez de texto.
- **Evidencia:** `enricher.py:855` (`series.description = match.description`) y
  `:1031` (`issue.synopsis = match.description`) copian la descripción de la
  fuente sin limpiar; no hay sanitizador en el camino.
- **Causa:** viva en el enricher; los 583 son datos ya guardados.
- **Falsos positivos:** una sinopsis con marcado intencionado; el campo es texto
  plano y la muestra es homogénea.
- **Aplicado (2026-11-21):** L1 limpió **622** sinopsis (la medición del 20 era
  583; el enricher antiguo sumó 39 más hasta el despliegue de #1191), 0
  protegidas y 0 manuales. F4a pasó de 583 casos a **0/766**. La causa quedó
  cerrada con #1191 y la prevención con la issue #1186. Detalle en §12.

### [A1a] Referencia vigente a una serie que ya no existe — S2 — APLICADO

- **Población:** 1.450 archivos con vínculo vigente o cobertura. **Casos:** 26
  (1,8 %); muestra 20/20 defecto.
- **Síntoma:** un archivo pendiente afirma un vínculo con una serie borrada; la
  procedencia miente y la ficha puede enseñar un vínculo que ya no existe.
- **Evidencia:** `api/series.py::delete_series` (camino heredado) borra la serie
  con cascada y deja `files.issue_id` NULL sin limpiar `metadata.vinculo`;
  `services/borrado_serie.py` se niega a borrar una serie con números o
  archivos, así que no es el camino que produjo estos 26.
- **Causa:** viva en el endpoint heredado (sin UI) + datos heredados.
- **Propuesta:** lote L2 (26) + issue de prevención.

### [D6a] Pendiente con un estado que no es `unsorted` — S2 — APLICADO

- **Población:** 606 archivos sin número. **Casos:** 9 (1,5 %); muestra 9/9.
- **Síntoma:** el archivo no aparece en «Por revisar» (`review.py` exige
  `match_status='unsorted'`), así que queda invisible.
- **Evidencia:** mismo borrado heredado que A1a: `issue_id` pasa a NULL y
  `match_status` conserva `matched`/`auto`.
- **Causa:** viva en el endpoint heredado; 9 datos heredados.
- **Propuesta:** lote L3 (9) + issue de prevención.

### [D6b] Vinculado con `match_status='unsorted'` — S2 — LEGÍTIMO

- **Población:** 4.492 archivos vinculados. **Casos:** 3.470 (77,2 %); muestra
  20/20 legítimo.
- **Por qué no es defecto:** `match_status` es el resultado del **matcher**, no
  el estado del vínculo. `services/vinculacion.py` escribe `metadata.vinculo`
  pero no `match_status`; el archivo queda `unsorted` aunque esté vinculado. La
  cola de «Por revisar» exige `issue_id IS NULL`, así que no se cuela.
- **Causa:** convención del campo; el check confunde «último intento del
  matcher» con «estado actual del vínculo».
- **Propuesta:** no corregir. Documentar el campo o, si se quiere, actualizarlo
  al vincular (issue menor, no lote de datos).

### [C2b / C2c] Tomo o anual registrado como grapa — S2 — DATO

- **Casos:** 23 (tomo/ómnibus) y 38 (annual/decimal), muestras 20/20.
- **Síntoma:** `numero_de_grapa` solo cuenta `single_issue` con entero; un tomo
  como grapa puede tapar un hueco que no es, y un anual como grapa puede
  inventar el hueco del número entero.
- **Evidencia:** `services/series.py::numero_de_grapa`; ADR 0016/0022.
- **Causa:** dato/parser; requiere criterio humano por número.
- **Propuesta:** pregunta L7.

### [C2a / C3a] `single_issue` y `#1` en `one_shot` — S2 — VIVO/DATO

- **Casos:** 4 y 4 (población 10 cada uno); exactos.
- **Síntoma:** una obra autoconclusiva muestra un `#1` o una grapa; ADR 0022 dice
  que no se inventa número y que `single_issue` no es su formato.
- **Evidencia:** comprobación; las 10 series `one_shot` son recientes.
- **Causa:** datos creados con los valores por defecto; criterio humano.
- **Propuesta:** pregunta L7 + issue de prevención.

### [H2] `field_provenance` contradice el valor actual — S2 — DATO

- **Caso:** 1 de 1; exacto.
- **Síntoma:** la fuente trajo un valor y la fila tiene otro sin `locked_fields`;
  la ficha no puede afirmar de dónde salió.
- **Propuesta:** pregunta L8 (¿cuál es el valor correcto y quién lo cambió?).

### [F5] `locked_fields` con nombres inexistentes — S3 — APLICADO

- **Casos:** 4 de 2.786; exactos.
- **Síntoma:** la persona cree que un campo está protegido y el enricher lo pisa.
- **Propuesta:** lote L4 (4) + validación en el servicio/UI.

### [F1d / F2a / I1] Datos pequeños — S3 — REVISADO

- **F1d:** 3 series con `end_year` y `status='ongoing'`; hay que decidir cuál es
  el dato correcto (`edicion_serie`).
- **F2a:** 1 serie con editorial española y tradición `american`; el CSV la dejó
  «sin medir» por una discrepancia entre la tabla del chat («no sé») y la
  hipótesis del CSV («defecto»). Se queda SIN MEDIR, no se cuenta.
- **I1:** corregido; era una fila `unread`, página 0, sin archivos. I1 0/38
  (2026-11-21).

### [A1b / D5] Legítimos que la comprobación confunde

- **A1b:** 321 de 322 archivos con historial apuntando a filas borradas; ADR 0014
  dice que el historial es append-only y conserva la procedencia. No se corrige.
- **D5:** 15 archivos con extensión declarada distinta del contenido real (14
  `.cbz` que son RAR y 1 `.cb7` que es 7z); el contrato #307 dice que
  `file_format` es la extensión declarada y no se corrige en la base. Es
  informativo, no un defecto.

### [H1] Campos con fuente y sin procedencia — S3 — PROCESO

- **Casos:** 244 de 245; 20/20 «no sé». **Tras el backfill estricto
  (2026-11-22): 243.**
- **Síntoma:** la ficha no puede decir de dónde salió cada valor;
  `procedencia.py` lo llama «origen no registrado».
- **Causa:** `field_provenance` tiene 2 filas en toda la base; el recolector CCM
  apenas se ha ejecutado. No es un lote de filas: es un proceso que falta.
- **Aplicado (2026-11-22):** backfill estricto (§15). Escribió 4 filas de
  procedencia (Tebeosfera) de 58 series; **1 es campo de H1**. Los 243
  restantes no tienen un valor de fuente que coincida: siguen «origen no
  registrado», sin atribuirlos a «manual» por descarte. **El PO los acepta así
  (2026-11-22).**

## 6. Precisión: qué se midió y qué no

- **Declarada por el PO, no etiquetada fila a fila.** El PO respondió «todo como
  la hipótesis». Eso confirma las 13 comprobaciones marcadas `defecto`, las 3
  `legítimo` y deja 13 en `no sé` (incluida B8). Es una medición **débil**: no
  elimina el sesgo de confirmación del agente que escribió la hipótesis.
- **Antes de aplicar un lote S1** (B5a, B1b) hay que revisar 5 filas al azar de
  B5a y el único caso de B1b en el CSV local, y confirmar que siguen siendo
  defecto. Si 4 de 5 lo son, la precisión baja del 100 % y la estimación se
  ajusta.
- **Las comprobaciones `no sé`** quedan «sin medir, no accionable»: no se
  proponen correcciones para C1, B6c, B3b, C3a, B2b, B7, B8, G1, C4b, E1, F4b,
  H1, F2a.
- **Las de 0 casos** son PASS de la consulta, no una garantía de que el dato esté
  bien; el SQL no encuentra el patrón.

## 7. Lotes propuestos (sin aplicar)

> **L6 (B1b), L1 (F4a), L2 (A1a), L3 (D6a) y L4 (F5) están aplicados** (§11–§13). Los demás lotes no se han ejecutado.
> Cada uno exige copia de seguridad, transacción única, servicio del proyecto y
> remedición. Las listas exactas de ids están en `.work/lotes/` (local, no
> versionado). Las que necesitan criterio humano son **preguntas**, no lotes
> cerrados.

### L1 — Aplicado: limpiar el HTML de 622 sinopsis (F4a) · S3

- **Antes:** 622 sinopsis con HTML (la medición del 20 era 583; el enricher
  antiguo añadió 39 hasta el despliegue de #1191). 0 protegidas, 0 manuales.
- **Cambio:** `<p>`, `<br>`, `&amp;`… → texto plano (quitar etiquetas, deshacer
  entidades, colapsar espacios).
- **Servicio:** `services/limpiar_sinopsis.py` + CLI
  (`python -m zascarr.cli.limpiar_sinopsis`), con vista previa y `--apply`;
  guarda el original en `issues.metadata["sinopsis_original"]`. Desplegado en
  #1193.
- **Aplicación:** 7 tandas de ≤100 (6×100 + 22); **622 limpiadas**, 0 sin
  cambio, 0 cambiadas por otro proceso; `pendientes` 622 → 0.
- **Copia previa:** `update_20261121_124634.sql.gz`, SHA-256
  `c7b5e3ff4c3ac48db4992bb4068d09c781ffe69b832b4e552e9ad0346a1d909e`; copia
  diaria `backup_20261121_041148.sql.gz`, SHA-256 `d4f8eaa9…`.
- **Reversible:** sí, restaurando `sinopsis_original` o la copia.
- **Protecciones:** no toca `locked_fields` con `synopsis` ni
  `metadata_source='manual'`; no cambia identidad, número, formato ni archivos.
- **Efecto:** la ficha enseña texto limpio; F4a **0/766**.

### L2 — Aplicado: 26 vínculos huérfanos (A1a) · S2

- **Filas:** 26 archivos con `metadata.vinculo.serie_id` que ya no existe.
- **Cambio:** quitar `metadata.vinculo` y añadir una entrada a
  `metadata.vinculo_historial` con `deshecho` y `previo` (la procedencia no se
  pierde).
- **Servicio:** `services/limpieza_calidad.py` (`--lote l2`), con vista previa
  y `--apply`; desplegado en #1202.
- **Reversible:** sí, releyendo el historial; copia previa.
- **Protecciones:** no tocar archivos con vínculo vigente válido; son 26
  archivos ya pendientes.
- **Efecto:** dejan de afirmar un vínculo falso; siguen en Pendientes.
- **Aplicado (2026-11-21):** 26 → 0; A1b sube a 347 por el historial
  (legítimo); ver §13.
- **Prevención:** issue para el `DELETE /api/series` heredado.

### L3 — Aplicado: 9 archivos a «Por revisar» (D6a) · S2

- **Filas:** 9 archivos con `issue_id` NULL y `match_status` distinto de
  `unsorted`.
- **Cambio:** `match_status='unsorted'` (y limpiar `review_motivo` si procede).
- **Servicio:** `services/limpieza_calidad.py` (`--lote l3`); guarda
  `match_status_previo`; desplegado en #1202.
- **Reversible:** guardar el valor anterior en `metadata["match_status_previo"]`.
- **Protecciones:** no tocar `review_dismissed=true`.
- **Efecto:** aparecen en «Por revisar» en vez de quedar invisibles.
- **Aplicado (2026-11-21):** 9 → 0; D6a 0/606; ver §13.
- **Prevención:** issue para el borrado heredado.

### L4 — Aplicado: 4 nombres inválidos de `locked_fields` (F5) · S3

- **Filas:** 4 (serie/número/creador/personaje con un campo que no existe).
- **Cambio:** quitar solo esos nombres; el resto del array queda igual.
- **Servicio:** `services/limpieza_calidad.py` (`--lote l4`); los nombres
  válidos se leen de las columnas reales del modelo; desplegado en #1202.
- **Reversible:** volver a añadirlos (no protegían nada); copia previa.
- **Efecto:** desaparece una falsa sensación de protección.
- **Aplicado (2026-11-21):** 4 → 0; F5 0/2.785; ver §13.
- **Prevención:** validar los nombres contra el modelo en el servicio/UI.

### L5 — Pregunta: 75 números con id de Comic Vine sin volumen (B5a) · S1

- **Evidencia:** 75 números en 4 series (56, 13, 5 y 1). Las series no tienen
  `comic_vine_id`, ni asociación activa, ni historial de retirada: no consta qué
  volumen se perdió.
- **Decisión del PO, por serie:** (a) decir qué volumen de Comic Vine
  corresponde y asociarlo con `AsociacionDeFuente` (los números recuperan
  sentido); (b) limpiar los ids de número de esa serie (servicio nuevo) y dejar
  que el enricher rellene con el volumen correcto; (c) dejarlo como está. Los
  nombres y los ids están en el CSV local de evidencia.
- **No es un lote cerrado:** el id bueno no lo puede decidir el agente.

### L6 — Aplicado: 1 serie con año incompatible (B1b) · S1

- **Evidencia:** 1 serie (id 4366): año local 1987, año de la fuente 1990. Las
  otras 8 filas del lote inicial eran registros de ids anteriores (B8), no B1b.
- **Decisión del PO:** corregir el año local a 1990.
- **Ejecución:** `EdicionDeSerie.actualizar(id, {"start_year": 1990})`, una
  transacción, commit; copia previa de §11. Resultado: `start_year=1990`,
  B1b 0/29. Reversible con el mismo servicio (1990 → 1987) o con la copia.

### L7 — Revisado: 61 números con formato o número incoherente (C2b/C2c, C2a/C3a) · S2

- **Evidencia:** 23 tomos/ómnibus como grapa, 38 anuales/decimales como grapa, 4
  `one_shot` con `single_issue`, 4 con `#1` inventado.
- **Decisión del PO (2026-11-21): sin cambios.** Los 18 Catwoman «Vol 02» son
  números de volumen, no tomos (falso positivo de C2b); los 5 Saga sí son tomos,
  pero se dejan; los 38 decimales/anuales son números sueltos legítimos (C2c);
  las 4 obras únicas manuales conservan el `#1` (C2a/C3a). No se escribió nada.

### L8 — Revisado: F1d/H2/F2a sin cambios; I1 corregido

- **F1d (3):** se dejan; no se cambia `end_year` ni `ongoing`.
- **H2 (1):** se deja; `end_year=2020` y la procedencia Tebeosfera coinciden; el
  check no demuestra una contradicción.
- **I1 (1): corregido.** Se borró la fila `reading_progress`
  `d5249763-0a91-4ae5-80c4-3d67f1a57c2d` (issue
  `ede1d8e1-0c0c-4117-adc1-a9f07a46de8b`, `unread`, página 0, sin archivos).
  I1 0/38. La copia de la actualización `update_20261121_144410.sql.gz` contiene
  la fila; las correcciones L2/L3/L4 posteriores son reversibles y están
  documentadas.
- **F2a (1):** se deja sin medir; editorial española con tradición `american`
  (edición de material americano).

### Lo que NO se propone corregir

- **D6b (3.470):** convención de `match_status`; no es defecto.
- **A1b (321):** historial append-only de ADR 0014; no se toca.
- **D5 (15):** extensión declarada frente a contenido; contrato #307; no se
  corrige en la base.
- **D4c (3):** los archivos faltan de verdad; el número no está poseído. No hay
  nada que arreglar en el dato.
- **H1 (244):** falta un proceso (CCM), no un `UPDATE` masivo.
- **PASS y SIN POBLACIÓN:** no se inventan correcciones donde no hay casos.

## 8. Prevención (propuesta, fase 6)

Cada defecto vivo, con el test de regresión nombrado por su mecanismo:

1. **B5a** — el id de volumen desaparece sin historial y deja ids de número
   huérfanos. Issue [#1185](https://github.com/juanajok/zascarr/issues/1185): «Ningún camino debe borrar `Series.comic_vine_id` sin
   historial; y retirar una asociación no debe dejar `issues.comic_vine_id`
   huérfanos». Test:
   `test_retirar_asociacion_no_deja_ids_de_numero_huerfanos` y
   `test_borrar_id_de_volumen_deja_historial_o_falla`.
2. **F4a** — el enricher guarda HTML. Issue [#1186](https://github.com/juanajok/zascarr/issues/1186): «La sinopsis se guarda como texto
   plano». Test: `test_enricher_limpia_html_de_la_sinopsis`.
3. **A1a/D6a** — el `DELETE /api/series` heredado deja `metadata.vinculo` y
   `match_status` colgados. Issue [#1187](https://github.com/juanajok/zascarr/issues/1187): «El borrado heredado no debe dejar vínculos ni
   pendientes invisibles». Test:
   `test_borrado_heredado_no_deja_vinculo_ni_match_status_colgados`.
4. **C2a/C3a** — el alta de `one_shot` no debe crear `single_issue` ni `#1` por
   defecto. Issue [#1188](https://github.com/juanajok/zascarr/issues/1188): «Obra única: sin `#1` inventado ni grapa por defecto». Test:
   `test_obra_unica_no_crea_single_issue_ni_numero_inventado`.
5. **F5** — `locked_fields` debe validarse contra el modelo. Issue [#1189](https://github.com/juanajok/zascarr/issues/1189): «Un campo
   bloqueado que no existe no protege nada». Test:
   `test_locked_fields_solo_admite_campos_del_modelo`.
6. **D6b** — opcional: actualizar `match_status` al vincular o documentar el
   campo. Issue menor: «`match_status` es el último intento del matcher, no el
   estado del vínculo». Test: `test_vinculacion_actualiza_match_status_o_lo_documenta`.
7. **B1b** — `_pick_by_year`/P1-P2: el enricher no debe aceptar un volumen
   homónimo sin año. Issue [#1190](https://github.com/juanajok/zascarr/issues/1190),
   «Homónimos sin año: no elegir `matches[0]`». Test:
   `test_enricher_no_elige_volumen_homonimo_sin_anio`. El único caso actual
   (3 años de diferencia) puede ser una convención; no se usa como prueba de
   que el mecanismo esté vivo.
8. **B8** — `entity_source_records` conserva registros de ids anteriores y B1b
   los confundía con la ficha vigente. Issue menor: «La evidencia de un id
   anterior no es la ficha vigente; B1b filtra por el id actual». Test:
   `test_evidencia_de_id_anterior_no_cuenta_como_b1b`.

**Chequeos periódicos propuestos para Estado/Duplicados:** B5a, A1a, D6a, F4a,
H1 y D2a, en solo lectura, con la huella del censo para comparar entre
ejecuciones. Es una propuesta al PO, no se construye aquí.

## 9. Límites y lo que no se ha hecho

- **No se ha escrito en la Pi**: ni base, ni `.env`, ni biblioteca, ni archivos.
  La única escritura es local (`.work/`, CSV de muestras y lotes).
- **No se ha consultado ninguna fuente externa**: la evidencia es
  `entity_source_records` (57), `http_cache` (22) y `Series.metadata_`.
- **No se ha recorrido el disco**: I3 y D1b quedan NOT RUN.
- **No se ha aplicado ningún lote**: las propuestas de §7 son eso, propuestas.
- **La precisión es declarada**, no medida con etiquetado independiente; la
  comprobación de 5 filas por S1 es obligatoria antes de aplicar.
- **El informe está seudonimizado**: no lleva títulos, rutas ni credenciales.
  Los CSV locales con títulos reales no se versionan.

## 10. Reproducción

```bash
# Censo completo, seudonimizado
DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --json

# Perfil
DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --perfil

# Muestras locales para etiquetar (no compartir)
DATABASE_URL=... python3 scripts/medicion/censo_calidad.py --local --csv - \
    --muestreo 20 --solo B1,B2b,B3b,B5a,B6c,B7,A1,C1,C2,C3,D4c,D6,G1,H2

# Pruebas (Postgres real, base con «test» en el nombre)
TEST_DATABASE_URL=... pytest -q tests/test_censo_calidad_pg.py
```

- `scripts/medicion/censo_calidad.py`: 81 comprobaciones, `READ ONLY`, sin
  dependencias nuevas, `--perfil`, `--json` con huella, `--local`, `--csv`,
  `--solo`, `--muestreo`.
- `tests/test_censo_calidad_pg.py` + `tests/fixtures/calidad_sintetica.sql`: 2
  pruebas pasadas en Postgres 15 local, un caso por comprobación, salida
  compartible sin títulos y `READ ONLY` verificado.
- `scripts/medicion/README.md`: sección del censo.

---

## 11. Aplicación del lote L6 (B1b)

- **Antes:** serie `e59dc382-07f0-4c1b-b715-d3afa76436df` (`Hawkworld Annual`),
  `start_year=1987`; B1b: 1 caso de 29.
- **Copia previa:** dump de la actualización
  `/var/backups/zascarr/postgres/update_20261120_232733.sql.gz`, SHA-256
  `5d6e1709d612b9df6dc403dc745660ab1e25712f06a80e3977b86ead02937bf6`,
  verificado por `probar_restauracion.sh` (restore-status: 47 tablas, 258
  series, 4.300 números, 5.098 archivos, 77 Deseados). Copia diaria adicional:
  `backup_20261120_222250.sql.gz`, SHA-256
  `3cff3d22f4502d8c91ed89bc4af6894f9e845fe70d6937673da0e6c9acb45b2a`.
- **Cambio:** `start_year` 1987 → 1990 con `services/edicion_serie.py`
  (`EdicionDeSerie`), una transacción, `commit`; `locked_fields` vacío, sin
  `metadata.alta`, sin parecidas con 1990. `updated_at` 2026-11-20 22:48:24 UTC.
- **Después:** B1b 0/29. Re-medición completa a las 22:48 UTC: B1b baja 1 → 0;
  B5a (75 casos), B6a, F1c y F4a suben en población/casos por un **ciclo de
  enriquecimiento sobre 20 números existentes a las 22:28:32 UTC**, antes de la
  corrección (los 19 casos nuevos de F4a tienen `updated_at=22:28:32` y **0**
  fueron tocados después de las 22:45). No es efecto del lote; no hay otra
  comprobación atribuible al cambio. No se revierte.
- **Qué queda pendiente:** B5a (75, el PO decidió dejarlo con prevención), los
  lotes L2–L4 (sin aprobar) y las preguntas L7/L8. L1 está aplicado (§12). La
  fase 6 está hecha: issues #1185–#1190 en el Kanban (Estado Backlog).

## 12. Aplicación del lote L1 (F4a)

- **Antes:** 622 sinopsis con HTML, 0 protegidas y 0 manuales (vista previa del
  2026-11-21 12:50). La medición del 2026-11-20 era 583; el enricher antiguo
  añadió 39 más hasta el despliegue de #1191.
- **Copia previa:** dump de la actualización
  `/var/backups/zascarr/postgres/update_20261121_124634.sql.gz`, SHA-256
  `c7b5e3ff4c3ac48db4992bb4068d09c781ffe69b832b4e552e9ad0346a1d909e`
  (restore-status ok, 47 tablas). Copia diaria adicional:
  `backup_20261121_041148.sql.gz`, SHA-256
  `d4f8eaa918f9fda2197fb079a157774d876b35ca1788837b98e8436eccd0b63a`.
- **Cambio:** `services/limpiar_sinopsis.py` (desplegado en #1193),
  `python -m zascarr.cli.limpiar_sinopsis --apply --limite 100`, 7 tandas:

  | tanda | pendientes antes | limpiadas | pendientes después |
  |---:|---:|---:|---:|
  | 1 | 622 | 100 | 522 |
  | 2 | 522 | 100 | 422 |
  | 3 | 422 | 100 | 322 |
  | 4 | 322 | 100 | 222 |
  | 5 | 222 | 100 | 122 |
  | 6 | 122 | 100 | 22 |
  | 7 | 22 | 22 | 0 |

- **Guardado:** `issues.metadata["sinopsis_original"]` en **622** filas; el
  resto de claves de `metadata` se conserva. No se tocó identidad, número,
  formato ni archivos.
- **Después:** F4a **0/766** (766 números con sinopsis; los demás siguen sin
  sinopsis o ya estaban limpios); `limpiar_sinopsis` en vista previa: 0
  pendientes; B1b 0/29; `sinopsis_original` 622. Censo completo: 82
  comprobaciones, huella `9c29c370b5d389a7`.
- **Otras comprobaciones:** ninguna cambió de casos por L1. Las poblaciones de
  A2, B5a, B6a, D4b y F1c crecieron por el ciclo de importación/enriquecimiento
  vivo; I1 mantiene 1 caso. No hay efecto atribuible al lote.
- **Reversible:** sí, restaurando `sinopsis_original` en las 622 filas o la
  copia previa.
- **Qué queda:** L7/L8 (preguntas) y H1 (proceso CCM); L2/L3/L4 aplicados
  (§13). S3 restante: 4 (F1d 3, I1 1). B5a sigue en 75 por decisión del PO.

## 13. Aplicación de los lotes L2, L3 y L4

- **Antes:** L3 **9**, L2 **26**, L4 **4** (vistas previas del 2026-11-21, sin
  escritura). L2 y L3 pueden solaparse; cada lote es independiente.
- **Copia previa:** dump de la actualización
  `/var/backups/zascarr/postgres/update_20261121_144410.sql.gz`, SHA-256
  `3fff8a4c3b2886ff2be33e56958a7342b03124f78d13b26a1df176f9ec925a9f`
  (restore-status ok, 47 tablas).
- **Cambio:** `python -m zascarr.cli.limpieza_calidad <lote> --apply --limite 100`
  (servicio de #1202), un `commit` por lote:
  - **L3:** 9 → 0; `match_status='unsorted'` y `match_status_previo` guardado.
  - **L2:** 26 → 0; `vinculo` retirado y conservado en `vinculo_historial` con
    `deshecho`; las demás claves de `metadata` intactas.
  - **L4:** 4 → 0; retirados los nombres que no son columnas del modelo; los
    válidos intactos.
- **Después:** D6a **0/606**, A1a **0/1.424**, F5 **0/2.785**; F4a 0/826; B1b
  0/29; **A1b 347**, las 26 nuevas entradas de historial de L2 (comportamiento
  legítimo de ADR 0014). Censo completo: 82 comprobaciones, huella
  `6e0816bde0967a33`.
- **Otras comprobaciones:** solo cambiaron de casos A1a, D6a, F5 y A1b; el resto
  de cambios son poblaciones que crecieron por el ciclo vivo (B5a, B6a, D4b,
  F1c, F4a). No hay efecto atribuible a los lotes fuera de los objetivos.
- **Reversible:** L2 por el historial; L3 por `match_status_previo`; L4
  volviendo a añadir los nombres (no protegían nada); y la copia previa.
- **Qué queda:** L7/L8 revisados (§14); F1d/H2/F2a se dejan como dato; H1
  (proceso CCM), B5a (75, decisión del PO) y la prevención de código (#1185,
  #1187, #1188, #1189, #1190).

## 14. Decisiones L7/L8

- **L7 (61 + 8):** sin cambios. C2b: 18 Catwoman «Vol 02» son números de
  volumen (falso positivo), 5 Saga son tomos reales; C2c: 38 decimales/anuales
  son números sueltos legítimos; C2a/C3a: 4 obras únicas manuales conservan el
  `#1`. No se escribió nada.
- **L8:** F1d (3) se deja; H2 (1) se deja (valor y procedencia coinciden); F2a
  (1) queda sin medir; **I1 (1) corregido**: borrada la fila de
  `reading_progress` `d5249763-0a91-4ae5-80c4-3d67f1a57c2d` (issue
  `ede1d8e1-0c0c-4117-adc1-a9f07a46de8b`, `unread`, página 0, sin archivos).
- **Después:** I1 **0/38**; censo completo 82 comprobaciones, huella
  `32a53151c679af54`; ninguna otra comprobación cambió de casos. Total estimado
  **147** (S1 75, S2 69, S3 3: F1d).
- **Copia:** `update_20261121_144410.sql.gz` (contiene la fila I1); las
  correcciones L2/L3/L4 posteriores están documentadas y son reversibles.
- **Qué queda:** B5a (75, decisión del PO), H1 (243 aceptados como «origen no
  registrado»; backfill estricto aplicado en §15), la prevención de código
  (#1187, #1188, #1189, #1190; #1185 cerrada con #1208) y los datos
  F1d/H2/F2a, que el PO decidió no tocar.

## 15. Backfill estricto de H1 (2026-11-22)

- **Vista previa:** 58 series con `metadata_source` no manual; **4 coincidencias**
  (todas Tebeosfera); 0 campos con candidato y sin coincidencia.
- **Aplicado:** `python -m zascarr.cli.consolidacion --backfill --apply`;
  **4 filas** de `field_provenance` con `confianza: fuente`. De ellas, **1 es
  un campo de H1**; las otras 3 son `title`/`publisher_name`/`language`, que
  H1 no cuenta. H1 **244 → 243**.
- **Por qué tan pocas:** los 57 `entity_source_records` del CCM no contienen el
  valor de los 244 campos de H1; el backfill estricto **no inventa** ni marca
  `legado`. Además `cover_url` y `status` no están en `CAMPOS_SERIE`. Los 243
  restantes siguen «origen no registrado».
- **Copia:** `update_20261122_112631.sql.gz`, SHA-256
  `6ddca96185ac950acc7ceb74a45b69ab4812bf07fe30033acd0bd494e7a3e355`; copia
  diaria `backup_20261122_041330.sql.gz`, SHA-256 `776f7de2…`.
- **Después:** H1 **243/245**; censo completo 82 comprobaciones, huella
  `3201507c2eb6b3d2`; ninguna otra comprobación cambió de casos.
- **Decisión del PO (2026-11-22): aceptar los 243 como «origen no registrado».**
  No se fuerza la procedencia: los 57 registros del CCM no contienen esos
  valores y atribuirlos sería inventar. El backfill estricto queda disponible
  para cuando el recolector CCM traiga fichas nuevas y los valores coincidan; no
  se usa el `legado` para maquillar H1.

## 16. Identidad de la serie frente a la fuente (2026-11-23)

- **Qué se midió (B9, nueva):** para las 58 series no manuales, que el id vivo
  (`comic_vine_id`, `tebeosfera_slug` o `gcd_id`) tenga un registro **actual** en
  `entity_source_records` (mismo `source` y `external_id`) y que la editorial no
  contradiga la edición del registro. El título puede diferir por la edición
  (original frente a española) y **no se cuenta**; los años ±1 tampoco. Una
  editorial vacía es completitud, no contradicción; «Image Comics» contiene
  «Image».
- **Cobertura:** **39** con registro actual; **19** sin él (10 con un registro de
  otro id — B8 — y 9 sin ninguno). De las 39: 8 títulos distintos (edición o
  puntuación), 2 años ±1, 0 totales y 14 diferencias de editorial.
- **Las 14 editoriales, en detalle:** 11 series con editorial local **vacía**
  (rellenadas desde la fuente), **2 variantes de nombre** (The Wicked + The
  Divine y WildC.A.T.s: local «Image Comics», fuente «Image»; no se tocan) y **1
  contradicción** (SUPERMAN: local DC Comics, fuente Tebeosfera-Zinco).
- **Aplicado (12 filas):** las 11 editoriales vacías + SUPERMAN (título
  `SUPERMAN EL HOMBRE DE ACERO` y editorial `Ediciones Zinco, S. A.`; el id
  `superman_1987_zinco` se queda). El título se cambió por el servicio de
  edición; las editoriales, por el mismo camino de datos con `Publisher`. Copia
  previa: `backup_20261123_1235.sql.gz`, SHA-256
  `cfcc26127c611fa639b75d508cccc9d040c5912623c698e396aea3d8fc4b8f14`.
- **Después:** B9 **20 → 19/58** (las 2 variantes de Image no cuentan por
  contención); las 19 son las que no tienen registro actual y su id **no se
  puede afirmar** todavía. La huella del censo completo cambia por B9.
- **Siguiente:** recolectar la ficha actual de las 19 (CCM) y volver a medir.

*Informe de las fases 2–6. Las issues de prevención están creadas (#1185–#1190).
L6, L1, L2, L3 y L4 están aplicados; L7/L8 revisados (I1 aplicado); H1 con
backfill estricto (243 restantes); F1d/H2/F2a se dejan como dato. **B9 añadida
el 2026-11-23** (83 comprobaciones); **12 editoriales aplicadas** (11 vacías +
SUPERMAN) y **19 series con fuente pendientes de recolectar** para verificar su
id.*
