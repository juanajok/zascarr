# Medición BL-DUP0 (#263) — Pi del PO, 2026-11-05

> Resultados de la medición delta acordada en
> `docs/design/benchmark-bl-dup0-duplicados.md` §7. Se ejecutó en **solo
> lectura** sobre la base de la Pi del PO. **No se publican rutas, nombres ni
> hashes**: solo cifras. No se ha tocado la biblioteca, ni el catálogo, ni el
> disco.

## 1. Entorno y comando

- **Máquina:** Pi del PO (no el entorno de desarrollo).
- **Fecha de ejecución:** 2026-11-05.
- **Acceso:** `docker compose exec` sobre el servicio `postgres`, en una sesión
  con `default_transaction_read_only = on`.
- **Informe:** `ImportRun` **`48b5624f-49f6-4382-aa69-18d7bcb75b21`**, del
  **2026-10-29 21:06:30 UTC** (`details.kind = "audit"`). Es una foto del
  2026-10-29, no del momento de esta ficha.
- **Sin escrituras:** solo `SELECT`; no se ejecutó la auditoría ni se creó
  ningún `ImportRun`.

Comando ejecutado (patrón; los placeholders no contienen credenciales ni rutas
reales):

```bash
docker compose exec -T postgres psql \
  -U "<USUARIO_BD>" -d "<BASE_BD>" -X -A -F $'\t' <<'SQL'
SET default_transaction_read_only = on;

WITH u AS (
  SELECT id, started_at, files_scanned, duplicate_count, unsorted_count, details
  FROM import_runs
  WHERE details->>'kind' = 'audit'
  ORDER BY started_at DESC
  LIMIT 1
)
SELECT 'M1_informe', id, started_at, files_scanned, duplicate_count, unsorted_count,
       details->>'truncado' AS truncado,
       jsonb_array_length(details->'mismo_contenido') AS grupos_identicos_lista,
       (SELECT coalesce(sum(jsonb_array_length(e->'rutas')), 0)
          FROM jsonb_array_elements(details->'mismo_contenido') e) AS ficheros_identicos_lista,
       details->>'bytes_recuperables' AS bytes_recuperables
FROM u;
SQL
```

Es la consulta exacta que se ejecutó (selecciona el último informe de auditoría
y lo etiqueta como `M1_informe`); así la salida de
`medicion-BL-DUP0-2026-11-05.txt` es reproducible sin sustituir nada.

Las consultas M2–M4 fueron las de `benchmark-bl-dup0-duplicados.md` §7.2, con la
misma selección del último informe (`WHERE details->>'kind' = 'audit' ORDER BY
started_at DESC LIMIT 1`).
M5 no se ejecutó (necesita `stat` dentro del contenedor de la app).

## 2. Resultados

| Métrica | Valor | Unidad | Naturaleza |
|---|---:|---|---|
| M1 `files_scanned` | 1.542 | ficheros | **completo** |
| M1 `duplicate_count` | **215** | grupos idénticos | **completo** |
| M1 `unsorted_count` | 28 | grupos de misma obra | **completo** |
| M1 `truncado` | **true** | — | **completo** (marca del informe) |
| M1 grupos idénticos en la lista | **200** de 215 | grupos | **mínimo** (93,0 % de los 215) |
| M1 ficheros idénticos en la lista | **401** | ficheros | **mínimo** |
| M1 `bytes_recuperables` | **8.058.146.534 B** (7,50 GiB / 8,06 GB) | bytes | **completo** |
| M2 grupos con copia en catálogo | **200 de 200** | grupos (lista) | **mínimo** |
| M2 con copia vinculada a un issue | **112** (56 %) | grupos (lista) | **mínimo** |
| M2 con copia sin vincular | **88** (44 %) | grupos (lista) | **mínimo** |
| M3a cruzan primera carpeta | **26** (13 %) | grupos (lista) | **mínimo** |
| M3a una sola primera carpeta | **174** | grupos (lista) | **mínimo** |
| M3a sin raíz | **0** | grupos (lista) | **mínimo** |
| M3b cruzan tradición estricta | **0** | grupos (lista) | **mínimo** |
| M3b sin mapeo a catálogo | **88** | grupos (lista) | **mínimo** |
| M4 pares de carpetas repetidas | **6** | pares | **mínimo** |
| M4 a ⊆ b | **4** | pares | **mínimo** |
| M4 b ⊆ a | **6** | pares | **mínimo** |
| M4 iguales (ambas ⊆) | **4** | pares | **mínimo** |
| M4b carpetas distintas subconjunto | **10** | carpetas | **mínimo** |
| M5 grupos que cruzan monturas | — | grupos | **NOT RUN** |

**Lectura de M4:** los 6 pares son subconjunto en algún sentido: **4 son
conjuntos iguales** (ambas ⊆) y **2 son b⊆a estricto** (a⊆b solo aparece en los
4 iguales). Las **10 carpetas distintas** de M4b son compatibles con 4 pares
iguales (8 lados) más 2 estrictos (4 lados): desde 8 hasta 10 hay **2 solapes**
entre parejas, que no se pueden identificar sin la lista. No se publica, así que
el 10 se lee como cota inferior de carpetas distintas implicadas, no como suma
exacta.

**Filas de clase que no venían en el extracto:** no se recibieron recuentos de
`carpetas_vacias` ni de `no_reconocidos`. No se ponen a cero ni se infieren: se
dejan como **no reportadas / NOT RUN**.

## 3. Caveat que manda: el informe está truncado

`truncado = true` porque `mismo_contenido` tiene **215 grupos y la lista se
recortó a 200**. Faltan **15 grupos (7,0 %)** en la lista; **M2, M3a, M3b y M4
son mínimos, no totales**, y no se extrapolan (los 15 grupos ausentes pueden
tener otra composición). `duplicate_count = 215` y `bytes_recuperables` son
contadores completos del ciclo.

Matiz de M4: el recorte conocido afecta a `mismo_contenido`; los 6 pares de
carpetas caben en 200. Se marca **mínimo** igualmente por la regla conservadora
del encargo, no porque se haya comprobado que esa lista esté recortada.

## 4. Interpretación para D1–D4

**Lo que confirman los números.** Los duplicados existen y son recuperables:
**215 grupos y 8,06 GB** de exceso (7,50 GiB), sobre 1.542 ficheros escaneados.
No es una hipótesis de laboratorio; es una muestra real de la Pi. El censo #297
hablaba de 222 copias y 8,1 GB **en las 217 `.cbr`/`.cbz`**; aquí se cuentan
**grupos** (215) y bytes recuperables, no copias, así que las cifras son
compatibles sin sumarse.

**D1 (dónde y exclusión).** No cambia la recomendación: cuarentena oculta en la
misma montura, con PUID/PGID y exclusión explícita. Los datos añaden un matiz:
**174 de 200 grupos (87 %) están dentro de una sola primera carpeta** y solo
**26 (13 %)** cruzan primera carpeta; **0 cruzan tradición estricta**. No hay
evidencia de un problema «entre carpetas de tradición» que justifique otra
ubicación o otra política. Lo que sí hay es **88 grupos sin vincular a un
número** (44 %), que es un hueco de catálogo, no de montura.

**D2 (vaciar).** Los 8,06 GB son reales, pero no urgen un borrado: se mantiene
la recomendación de **vaciado explícito y sin purga automática**. La pantalla
debe mostrar bytes y fecha; el tamaño no justifica una tarea que borre sola.

**D3 (comprobante).** No cambia la idempotencia ni el token. Sí conviene que el
comprobante distinga si la copia que se queda está **vinculada a un issue o no**
(hoy 112 sí / 88 no): así el resultado no presenta como «resuelto» un grupo que
sigue sin número. Los **88 sin mapeo de M3b son coherentes con esos 88 sin
vínculo** (sin issue no hay serie ni tradición que consultar); no se ha
verificado la identidad uno a uno. No es una tabla nueva por este dato; es un
campo/estado más en el comprobante.

**D4 (postura y ADR).** Refuerza el ADR 0015: mover a cuarentena es reversible y
no borra. Añade una salida que el ADR y la UI deben reconocer: **«vincular»**
(el flujo de revisión ya existente) para los 88 grupos sin issue. La cuarentena
no debe ser la única salida ni sugerir que un grupo queda resuelto si su copia
conservada no está catalogada. Sin cambio de postura: no se borra, no se
puntúa, no se preselecciona, no se purga solo.

**Lo que no cambia:** referencias, D1 (misma montura/exclusión), D2 (sin purga
automática), D3 (comprobante idempotente) y D4 (ADR propuesto). M5 sigue
pendiente y no hay datos para reabrir enlaces duros, CoW ni «misma obra, otra
copia» (eso es BL-R6).

**Sobre la lectura del encargo:** coincide en lo esencial. Matiz: no son «0
cruces de tradición» y «todo en una carpeta» sin más: **174/200 dentro de una
sola primera carpeta y 26/200 cruzan primera carpeta**, pero **0 cruzan
`Series.tradition`**. El problema accionable no es la tradición: es el **44 % de
grupos cuya copia en catálogo no está vinculada a un número**, y eso empuja a
que cuarentena y vinculación convivan.

## 5. PASS / FAIL / NOT RUN

| Comprobación | Estado | Evidencia |
|---|---|---|
| M1 contadores completos (`files_scanned`, `duplicate_count`, `unsorted_count`, `bytes_recuperables`, `truncado`) | **PASS** | informe del 2026-10-29; contadores completos |
| M1 lista de grupos/ficheros | **PASS con caveat** | 200 de 215 grupos (93,0 %); lista truncada |
| M2 / M3a / M3b / M4 | **PASS como mínimos** | calculados sobre 200 grupos; faltan 15 (7,0 %) |
| M5 cruces de montura | **NOT RUN** | requiere `stat` dentro del contenedor de la app; no ejecutado |
| `carpetas_vacías` / `no_reconocidos` | **NOT RUN / no reportado** | no venían en el extracto; no se infieren |
| Sin escrituras en la medición | **PASS** | sesión `default_transaction_read_only=on`; solo `SELECT` |
| Privacidad de lo publicado | **PASS** | esta ficha no contiene rutas, nombres ni hashes |
| **FAIL** | — | Ninguno: no hay contradicción entre métricas; el truncado está declarado |

## 6. Límites y caducidad

- La foto es del **2026-10-29 21:06:30 UTC**; la biblioteca pudo cambiar
  después. No se ha reejecutado la auditoría.
- M2–M4 son mínimos por el recorte a 200; **no se extrapolan** a 215.
- M5 y los recuentos de carpetas vacías/no reconocidos siguen pendientes.
- Esta ficha **caduca** el **2027-01-04** (~60 días), o antes si se repite el
  censo, cambia la biblioteca o cambia la historia #263.
