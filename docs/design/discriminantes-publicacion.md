# Discriminantes de publicación (MIT-M5-US01, #182)

> **Decisión de producto registrada el 2026-11-06.** Cierra la pregunta abierta del ADR 0003 sobre qué
> discriminantes se muestran para homónimas y la vía manual. **No autoriza** UI, API, migración, creación de
> entidades ni cambios de esquema: solo fija el acuerdo y el contrato que consume #183.
>
> Base: `main` `7c8875e`; censo de #181 en `docs/design/censo-identidad-real.md` (PR #401, `35283b5`).

## 1. Evidencia del censo

| Dato | Valor |
|---|---|
| Issues | 443; **100 % `single_issue`** |
| Colisiones de la clave actual | **0** |
| Recopilaciones / cobertura | **0** recopilaciones; **0** `covered_issue_ids` |
| ComicInfo leído | **0** archivos con ComicInfo |
| Sin fuente de metadatos | 272/443 (61,4 %) |
| Archivos sin Issue | 897 (no se ha probado que sean packs o tomos) |

El censo **no observa hoy** el problema que la migración de identidad resolvería. Eso no convierte el modelo
actual en correcto para publicaciones homónimas: solo significa que la base real todavía no las contiene.

## 2. Vocabulario

Se usan los términos del ADR 0003: **serie**, **edición** (no existe como entidad), **publicación/número**,
**formato de publicación**, **archivo** y **cobertura**. Título y año sirven para buscar; no son identidad.

## 3. Qué identifica hoy

| Elemento | Identifica | No identifica |
|---|---|---|
| `Issue.id` (UUID) | la fila de publicación | la publicación editorial fuera de ZascArr |
| `Issue.comic_vine_id` (único), `Series.comic_vine_id`/`anilist_id`/`tebeosfera_slug`/`gcd_id` | identidad **dentro de su fuente**, cuando existe | una identidad universal de obra o edición |
| `Series.id` (UUID) | la serie del catálogo | la obra ni la edición |
| `UNIQUE(series_id, issue_number, volume)` | evita colisiones de implementación | identidad editorial: ni `number_key` ni edición |
| `Issue.number_key` | **no existe** | — |
| `editions` / `edition_id` | **no existen** | — |
| `Issue.isbn` | columna existente, **nada la escribe ni la lee** | discriminante disponible |
| `Issue.language` / país / edición / reimpresión | **no modelados** | no se pueden usar |
| `File.file_path` / `sha256_hash` | archivo y contenido | publicación |

La clave actual no incluye `format`: con el mismo `volume` dos publicaciones del mismo número chocan; con
`volume` distinto o `NULL` pueden coexistir **por accidente**. No se interpreta como identidad.

## 4. Discriminantes acordados

### 4.1 Identidad (cuando existe)

1. UUID local de la serie/publicación.
2. Identificador externo de **su** fuente (`comic_vine_id`, `anilist_id`, `tebeosfera_slug`, `gcd_id`), único
   dentro de esa fuente. Un id de una fuente no identifica a otra.
3. Para una publicación local ya existente, su UUID. No hay identidad editorial universal.

### 4.2 Discriminantes para mostrar y comparar (nunca deciden solos)

- Título y año de la serie; tradición; editorial/sello (`Publisher`, `Imprint`) cuando constan.
- Número de la publicación, tal como está (`issue_number`), y formato de publicación (`Issue.format`).
- Fuente y procedencia del candidato (`metadata_source` / alta), su id externo y su URL de ficha si la fuente la da.
- `Issue.volume` se muestra solo como **dato heredado/advertencia** («volumen registrado»), no como identidad.
- Campos ausentes se muestran como **«no consta»**; no se rellenan por inferencia.

### 4.3 No disponibles (no se inventan)

Idioma y país de la serie o edición, identidad de obra, edición/reimpresión, ISBN, «reproduce a» y cobertura:
no están modelados o no se escriben/leen hoy. No se usan como discriminantes en #183.

## 5. Homónimas y ambigüedad

| Caso | Resolución acordada |
|---|---|
| Dos series con el mismo título y año | La serie se elige por su UUID/ID de fuente, no por título+año. Si solo coinciden título/año y no hay más evidencia, son candidatas distintas y la persona elige; nunca se funden por título. |
| Mismo número en dos formatos (grapa/tomo) | El formato se muestra, pero **no basta como identidad**. Si no hay ID externo que las separe y el modelo no puede representarlas, es ambiguo: no se elige, se explica y se va al camino manual. |
| Mismo número, misma serie, misma volumen, dos publicaciones | El modelo actual no las representa; no se inventa una edición. Ambigüedad persistente → manual; queda para #184 si se decide migrar. |
| Una candidata única | Se muestra con sus discriminantes; **sigue requiriendo elección explícita**; no se autoselecciona. |
| Candidatas indistinguibles con los campos disponibles | No se elige automáticamente, se explica la ambigüedad y se ofrece el camino manual. |

Regla cerrada: **ninguna selección automática en ambigüedad**. El sistema no crea un identificador para desempatar.

## 6. Contrato para #183 («Elegir una publicación identificada»)

### 6.1 Candidata

Cada candidata debe exponer, como mínimo:

- `candidate_id` (identificador de la candidata en el contrato; no una invención editorial);
- `series_id` local y título/año de la serie;
- número (`issue_number`) y formato de publicación;
- editorial/sello, tradición y fuente/procedencia cuando constan;
- id externo y URL de ficha de la fuente cuando constan;
- los campos de §4.2 que estén disponibles, con ausencia explícita («no consta»), sin campos inferidos.

### 6.2 Elección válida

- La persona selecciona **explícitamente una** candidata; no hay valor preseleccionado ni elección por ausencia.
- La elección debe llevar el `candidate_id` y la procedencia que se mostraron; si el candidato ya no existe o
  cambió, se revalida y se rechaza/actualiza con explicación, sin continuar con una selección inválida.
- Una elección no crea serie, edición, publicación ni vinculación como efecto secundario.

### 6.3 Salida

`publicacion_identificada` para el paso siguiente, como mínimo:

- `series_id`;
- `candidate_id` y `source`/`external_id` si existen;
- los discriminantes mostrados (número, formato, editorial/sello, tradición, procedencia);
- `issue_id` local solo si la publicación ya existía; si no, no se inventa.

La persistencia, el formato y la reversibilidad de esa elección son de #183; #182 no los implementa.

### 6.4 Ambigüedad y fallo

- Ambigüedad persistente: sin selección, mensaje en llano y camino manual acordado (revisión/asignación manual
  existente); no se presenta una elección inventada.
- Sin candidatas, error de fuente o error de lectura: se explica, se distingue de «sin resultados» y no se
  continúa con una publicación identificada.

## 7. Casos de prueba mínimos

| Caso | Entrada | Resultado esperado |
|---|---|---|
| Publicación única | Una candidata con id de fuente | Se muestra; requiere elección explícita; salida con id |
| Homónimas distinguibles | Dos candidatas con id de fuente/editorial distintos | Se muestran ambos discriminantes; la persona elige uno; no se autoselecciona |
| Ambigüedad no resoluble | Dos candidatas idénticas en todos los campos disponibles, sin id externo | No se elige; se explica; camino manual |
| Sin candidatas / error | Sin resultados o fallo de consulta | «Sin resultados» o error distinto de vacío; no hay selección |
| Cambio concurrente | Candidata desaparece entre mostrar y confirmar | Se revalida y se rechaza con explicación; no se inventa |

#183 debe cubrir estos casos; #182 solo los fija.

## 8. Decisión sobre la migración

**No se diseña ni autoriza la migración ahora.** El censo no muestra colisiones ni diversidad de formatos, y
#184 queda pospuesto. Disparadores para reabrir la decisión:

- aparece un `format` distinto de `single_issue`;
- colisiones de clave > 0;
- `covered_issue_ids` > 0;
- los 897 archivos sin Issue resultan packs o tomos;
- una fuente real exige una edición/identidad que el modelo no puede representar.

Mientras no ocurra, el camino es el actual: discriminar con lo disponible, no elegir automáticamente y usar el
camino manual cuando la ambigüedad persiste.

## 9. Trazabilidad

- Censo: [`censo-identidad-real.md`](censo-identidad-real.md), salida [`censo-identidad-2026-11-04.txt`](censo-identidad-2026-11-04.txt), PR #401, merge `35283b5`.
- ADR: [`ADR 0003`](../adr/0003-identidad-editorial.md) (vocabulario y reglas 1–7).
- Benchmark: [`benchmark-identidad-editorial.md`](benchmark-identidad-editorial.md).
- Issues: #181 (censo), #182 (esta decisión), #183 (elección), #184 (migración), padre #125.

## 10. PASS / FAIL / NOT RUN

- **PASS:** censo con seis métricas; decisión de discriminantes y contrato de #183; casos mínimo y disparadores.
- **FAIL:** ninguno de la decisión.
- **NOT RUN:** UI/API de #183, migración de #184, verificación de los 897 archivos sin Issue y homónimas reales
  (el censo no encontró ninguna). No se ejecutó nada sobre datos.
