# ADR 0020: Edición y colecciones en la CCM — mantener `Series` y la colección local

- **Estado:** **Aceptado** · 2026-11-17
- **Relacionado:** [ADR 0003](0003-identidad-editorial.md) (identidad editorial y edición diferida), [ADR 0019](0019-relleno-de-huecos-enricher-secundario.md), [especificación CCM v2.1](../design/especificacion-CCM-v2.1-2026-11-17.md), issue [#1005](https://github.com/juanajok/zascarr/issues/1005)
- **Decisión del PO:** no crear todavía una entidad `Edition`; no añadir identidad externa a `collections`.

## Contexto

La Capa de Consolidación de Metadatos (CCM) ya separa `work_scope` (datos creativos/de obra) de
`edition_scope` (años, editorial, total, fecha, páginas, ISBN) y exige que cada vínculo externo
declare su rol (`edicion_propia` u `obra_referencia`). Las fases 1–5 están implementadas y
desplegadas: recolección por ID, motor por campo, roles, backfill, pantalla de revisión y cola de
`ComicInfo`.

Queda una pregunta de modelo: ¿hace falta una entidad `Edition` para que una `Series` pueda contener
varias ediciones, o el modelo actual (`Series` + roles + ámbitos) cubre el uso real?

### Datos de uso medidos en la Pi (solo lectura, 2026-11-17)

| Dato | Valor |
|---|---:|
| Series / issues | 228 / 4.229 |
| Colecciones locales | 27 |
| Series dentro de alguna colección | 224 |
| Máximo de series en una colección | 38 |
| Series con `Issue.volume` distinto dentro de la misma serie | **0** |
| Números repetidos con formatos distintos en la misma serie | **0** |
| Series con más de un ID externo | **2** de 55 con algún ID |
| Series con `edition_kind` distinto de NULL | 1 (`tradumaqueta`) |
| Series con `language` | 0 |
| Títulos normalizados con varios años de inicio | 1 |

No hay ninguna señal de que una misma `Series` esté conteniendo hoy dos líneas de numeración. Los dos
casos con más de un ID no son necesariamente dos ediciones: pueden ser una edición y su referencia
de obra.

## Alternativas

### A. Crear `Edition` bajo `Series` (ADR 0003, D2)

**Qué sería:** una tabla `editions` con `id`, `series_id`, `kind`, unidad de numeración y nombre; los
`Issue` colgarían de la edición; los IDs externos podrían colgar de la edición y la cobertura se
calcularía contra la edición.

**Ventajas:** modela correctamente varias ediciones; evita mezclar totales/numeración; prepara
colecciones editoriales.

**Coste:** migración no trivial; toca importador, matcher, `Issue.volume`, huecos, ficha, APIs y
todas las historias que asumen `Series → Issue`. No hay datos que justifiquen ese riesgo hoy.

### B. `Series` como unidad de catálogo; cada edición es una `Series` distinta

**Qué es:** la serie que el coleccionista cataloga sigue siendo la unidad. Si necesita dos
ediciones, crea dos `Series` (por ejemplo, «Patrulla-X» Forum y «Uncanny X-Men» Marvel) y las
relaciona con sus fuentes mediante roles. `work_scope` permite compartir datos creativos si se
declara una fuente de referencia.

**Ventajas:** cero migración; compatible con lo ya desplegado; el coleccionista entiende «una serie
= una línea de numeración»; los roles impiden mezclar edición y referencia.

**Límites:** no hay una entidad «obra» que agrupe ambas; la relación entre dos `Series` de la misma
obra es una convención (título/año/roles), no una FK. La colección local sigue siendo una agrupación
manual y no se enriquece desde fuera.

### C. Solo `work_id` / entidad «obra»

**Qué es:** agrupar por obra sin modelar edición.

**Por qué no:** no resuelve el problema real (la numeración y los totales son de la edición); añade
una entidad sin resolver el espacio donde un número identifica. Descartada.

## Decisión

1. **No se crea `Edition` en este ciclo.** `Series` sigue siendo la unidad de catálogo y cada línea
   de numeración que el coleccionista quiera conservar por separado es una `Series` distinta.
2. **No se añade `source` ni `external_id` a `collections`.** La colección local es una agrupación
   personal; la «colección editorial» es un atributo de la serie/edición, no de la estantería.
3. **Los roles mandan:** un vínculo `obra_referencia` no puede rellenar campos de
   `edition_scope`; `work_scope` puede compartirse con la referencia. Esto ya está implementado.
4. **Si aparece una segunda edición real:** se crea otra `Series`, no se mezclan issues/IDs en la
   existente; se documenta la relación en la UI mediante rol/referencia, no con una FK inventada.
5. **Sin migración ni tablas nuevas.** Cualquier cambio futuro de este ADR exige uno nuevo.

## Cuándo se revisa

Se reabre este ADR si se cumple **cualquiera** de estas condiciones, medidas sobre uso real:

- ≥ 12 series (≈5 % del catálogo actual) con dos o más ediciones que compartan una misma `Series` y
  no puedan separarse como dos `Series` sin perder datos;
- tres reportes reales de coleccionistas con el mismo caso;
- una fuente externa que entregue la edición como entidad propia y haga inviable representarla con
  roles;
- una migración de identidad editorial que ya esté planificada por otro motivo.

Mientras no se cumpla, el modelo actual es suficiente. La revisión no se hará por completitud.

## Consecuencias

**Positivas:** no se toca el esquema ni el importador; no se rompen huecos, matcher ni fichas; la
colección local no se contamina con identidad externa; la CCM puede seguir creciendo sin una
migración XL.

**Negativas (aceptadas):** no hay agrupación formal de dos `Series` como «misma obra»; si el
coleccionista mezcla ediciones en una sola `Series`, la CCM no lo adivina y los roles deben
declararse. La colección editorial no tiene ficha propia; se representa en la serie.

## Límites

- Este ADR **no implementa** nada: ni tablas, ni columnas, ni migraciones.
- No autoriza a enriquecer `collections` desde fuentes externas.
- No cambia la UI ni el contrato de la CCM; solo fija el modelo para las historias siguientes.

## Evidencia

- Medición de la Pi del 2026-11-17 (solo lectura; cifras agregadas, sin rutas ni nombres).
- Implementación CCM fases 1–5: PRs #1006, #1008, #1010, #1013, #1016, #1023, #1028.
- [ADR 0003](0003-identidad-editorial.md): vocabulario y decisión diferida sobre edición.
- [Especificación CCM v2.1](../design/especificacion-CCM-v2.1-2026-11-17.md): ámbitos y roles.
