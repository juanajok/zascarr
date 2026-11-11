# Benchmark — MIT-M7-US03: revisar y retirar decisiones reutilizables (#132)

> **Ficha de benchmarking §13 (nivel 2, addendum).** Historia **#132** (US03 de #110).
> Complementa `docs/design/benchmark-MIT-M7-contexto-declarado.md` (lectura 2026-11-10,
> `main` `3a8b506`), que ya cubre #130/#131/#132 y fija las referencias a commit. Aquí se
> concreta **lo que #132 necesita decidir**: ciclo de alias aprendido, consentimiento,
> alias importado, inventario conjunto y precedencia.
>
> Lectura de contraste: **2026-11-11**, `main` **`309083f`** (con #607 y #622 fusionados).
> No se ha ejecutado ninguna aplicación; no se reutiliza código de las referencias. Decide
> el PO. Caducidad: **2027-01-10** (~60 días), o antes si cambia una referencia o la historia.

## 1. Problema local (verificado en el código vigente)

- **Alias aprendido B13**: `local_aliases.pattern_norm → series_id`, único global. El
  aprendizaje (`ReviewService._learn_alias`) **escribía una regla activa sin consentimiento**
  y `SeriesMatcher.find_alias` la aplicaba antes del fuzzy, pudiendo mover archivos
  (`docs/design/inventario-entradas-heredadas-y-alias-2026-10-09.md`).
- **No había pantalla ni ciclo** para listar, desactivar o retirar alias; tampoco estado,
  versión, origen ni historial.
- **Alias de importación no existía** como entidad. El spec de #132 (P9) lo separa del
  alias aprendido y lo deja subordinado a la decisión local.
- **#130/#131 ya están**: declaraciones y correspondencias versionadas por filas, con
  desactivar/reactivar/retirar; su UI de declaraciones existe y la de correspondencias es
  solo diseño.
- **Resultado deseado**: inventario único, consentimiento explícito por alias, conflictos y
  precedencia visibles, acciones reversibles (salvo retiro) y **nada retroactivo**.

## 2. Referencias (reutilizadas de la ficha de #110; verificadas allí)

| Referencia | Commit de la lectura | Licencia | Qué aporta a #132 |
|---|---|---|---|
| Sonarr | `c018578e` (2026-11-02) | GPL-3.0 | Importación explícita en sitio; **sin** ciclo de alias aprendido ni estado de consentimiento |
| Radarr | `7e3f80c9` (2026-11-08) | GPL-3.0 | Igual que Sonarr para raíces/importación |
| Kapowarr | `c191dda6` (v1.3.2) | GPL-3.0 | Raíces y volúmenes; no hay alias de nombre con estado |
| Mylar3 | `cdc94a44` (2025-08-17) | GPL-3.0 | Interruptores de importación y metadatos; sin inventario de reglas |
| Komga | `6e161b6c` (2026-11-10) | MIT | *Locks* de metadatos (imagen/portada): una elección manual queda protegida; patrón de «la decisión explícita gana» |
| Kavita | `f059e277` (0.9.1.21) | GPL-3.0 | `CoverImageLocked` y metadatos bloqueados por el usuario; precedente de lock explícito |
| Calibre | `fd2df1f9` (2026-11-10) | GPL-3.0 | Historial/versiones y operaciones no destructivas por defecto |

**Método:** se reutiliza la lectura y las citas de la ficha de #110 (misma fecha de
referencia); para esta historia solo se contrasta con el código de ZascArr. «No lo
encontré» no equivale a «no existe»; no se infiere soporte por la UI.

## 3. Resultado por idea

| Idea / decisión | Referencia o hueco | Resultado | Motivo |
|---|---|---|---|
| El alias aprendido **no ejecuta sin consentimiento** | Sonarr/Radarr no tienen alias aprendidos; B13 sí ejecutaba | **Construir sobre lo propio** | ADR 0008: el alias aporta evidencia, no permiso; hay que añadir estado y conservar el patrón único |
| Alias nace `propuesto`; activar pide confirmación explícita e independiente | Patrón de *lock* manual de Komga/Kavita | **Adaptar** | La unidad es distinta (patrón de nombre → serie), pero el principio «la elección manual explícita gana» sí vale |
| Estado `activo/desactivado/retirado` + versión + historial | Komga/Kavita logran parte con flags; Calibre usa historial | **Adaptar** | Se queda en JSONB + versión (P-B), sin convertir `local_aliases` en tabla de versiones |
| Desactivar ≠ borrar; reactivar; retirado terminal | Servicios de #130/#131 ya versionados | **Construir sobre lo propio** | El contrato ya existe y es el mismo para las cuatro fuentes |
| Alias de importación como entidad propia, versionada por filas | No existe en las referencias | **Construir sobre lo propio** | P9; evita competir con `pattern_norm` único y permite evidencia/futuro consumidor |
| Alias importado **solo administración** en #132 (sin consumo en matcher) | Sonarr/Radarr no tienen segunda capa de alias | **Adoptar** (P-C) | Mantiene el corte reversible; su consumo es 132-c |
| Inventario único de cuatro fuentes con filtros | Ninguna referencia tiene esta pantalla | **Construir sobre lo propio** | Reutiliza servicios #130/#131 + alias; sin N+1 (4 consultas + 1 de series) |
| Precedencia **local > importado > aprendido**, sin elegir sola | Sonarr/Radarr no exponen precedencia; Komga/Kavita protegen la elección | **Adaptar** | Se muestra la precedencia y el conflicto; resolver es desactivar/retirar o cambiar la regla local |
| Importadas **solo lectura** en el inventario (P-D) | — | **Adoptar** | Pertenecen a su origen; la UI de #130 ya las muestra sin gestionar |
| Activación masiva | — | **Descartar** (P-F) | AC6 exige confirmación por alias |
| Consumo del alias importado en matcher/evaluador ya | — | **Descartar en #132** (P-C) | Suma S/M y pruebas de integración; queda para 132-c |
| Ejecutar alias aprendido sin estado (comportamiento actual) | B13 | **Descartar** | Contradice AC6/AC8 y el objetivo «sin aprendizaje invisible» |

## 4. Invariantes de ZascArr que la implementación respeta

- No mueve, renombra ni borra archivos; no reasigna series/issues ya confirmados.
- Activar/desactivar/retirar solo escribe estado/versión/historial (y versiones del alias
  importado); no toca series, issues, metadata ni declaraciones/correspondencias.
- El matcher y el orquestador **solo** aplican alias `activo`; `propuesto`/`desactivado`/
  `retirado` no se aplican.
- La precedencia no autoriza a ejecutar: solo ordena evidencia. Un conflicto se muestra y lo
  resuelve una acción explícita (P-D/P-E).
- Sin activación por coincidencia de nombre, frecuencia ni efecto secundario.

## 5. Casos de prueba que fija esta historia

1. Migración 0025→head: alias existentes conservados, `propuesto`, versión 1 e historial
   inicial; ninguna fila duplicada.
2. Alias nuevo de aprendizaje: `propuesto`; el matcher **no** lo aplica; activar con
   confirmación lo aplica; desactivar deja de aplicarlo; retirar es terminal.
3. Aprender sobre un alias activo de otra serie: **no lo pisa**, deja evento de conflicto;
   la UI lo muestra y no lo activa sola.
4. Alias importado: versiona por filas (activo/desactivado/reactivado/retirado) y retiro
   terminal; no se consume en el matcher (P-C).
5. Inventario: cuatro fuentes con tipo/origen/estado/alcance/versión/efectos/precedencia,
   filtros combinables y «incluir historial»; importadas solo lectura; conflictos visibles
   sin botón «elegir esta».
6. **Rendimiento**: 4 consultas fijas de fuentes + 1 de títulos (sin consulta por fila);
   tope 500 filas; sin abrir archivos ni red al pintar el inventario.
7. Efectos previos: desactivar/retirar no cambia archivos, series, issues ni vínculos ya
   confirmados.

## 6. NOT RUN

- Navegador real, lector de pantalla y prueba a 320 px: pendiente de QA en Pi.
- Medición de latencia en la Pi con una biblioteca grande (el inventario es lectura de BD,
  no abre archivos).
- Consumo del alias importado en matcher (fuera de #132, P-C).

## 7. Huella en el código

Implementación en `services/alias_decisiones.py`, `services/decisiones_reutilizables.py`,
`web/decisiones_reutilizables.py`, plantillas `decisiones_reutilizables.html`/
`confirmar_decision.html`, migración `0026`, filtros de estado en `core/matcher.py` y
`services/orchestrator.py`. La lectura de referencias, veredictos y licencias es la de la
ficha de #110; esta ficha **no** cambia decisiones arquitectónicas ni crea ADR.
