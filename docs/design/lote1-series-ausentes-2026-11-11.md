# Lote 1 de series ausentes — propuesta revisada (2026-11-11)

> **No aplicado.** No se han creado series, Issues ni enlaces. La propuesta
> está en `/mnt/Datos/Documentos/propuesta_lote_series_ausentes_1_2026-11-11.json`
> y contiene IDs y nombres reales.

## 1. Criterios de selección

Se eligen series que cumplen todo:

- no existen en el catálogo (0 coincidencias exactas);
- una sola carpeta de serie, sin mezclar volúmenes/años;
- issues numéricos, sin anuales, especiales, packs ni rangos;
- al menos 19 archivos;
- título canónico claro, sin abreviaturas (`JLD`, `OP`).

Se descartaron para este lote: `Flash`/`The Flash`, `Catwoman` (varios
volúmenes), `Injustice` (Año N), `JLD` (abreviatura), `OP`/`One Piece`
(volúmenes), `Monstress` (dos carpetas) y `Dreadstar` (posible solape con la
serie ya catalogada `Dreadstar: La Odisea…`).

## 2. Contenido

| Serie propuesta | Archivos | Issues | Duplicados | Tradición |
|---|---:|---:|---|---|
| `Superman/Batman` | 88 | 88 (#0–#87) | — | american |
| `Transmetropolitan` | 53 | 53 (#1–#53) | — | american |
| `Irredeemable` | 38 | 37 (#1–#37) | #1 ×2 | american |
| `20th Century Boys` | 24 | 22 (#1–#22) | #1 ×2, #2 ×2 | manga |
| `Doomsday Clock` | 19 | 11 (#1–#11) | #1–#3 ×3, #4–#5 ×2 | american |
| **Total** | **222** | **211** | **11 archivos** | |

Los duplicados son varias copias/portadas del **mismo número**: se enlazarán
al mismo Issue, no se borrará ninguno.

## 3. Qué se escribiría si se aprueba

En una transacción:

1. 5 filas `series`:
   - `kind=regular`
   - `tradition=american` salvo `20th Century Boys` (`manga`)
   - `parent_series_id=NULL`
   - `metadata_source=manual`
   - `start_year=NULL` (se enriquecerá después)
   - `metadata={"origen":"propuesta_series_ausentes_lote1","carpeta":...}`
2. 211 filas `issues` con `format=single_issue`, `locked_fields` de identidad y
   `sort_order` numérico.
3. 222 actualizaciones de `files.issue_id`.
4. **Ningún archivo se mueve, renombra ni borra.**

## 4. Por qué no se aplica todavía

- No hay IDs de Comic Vine/GCD: son series locales manuales.
- Los títulos canónicos (`Superman/Batman`) y la tradición manga deben ser
  confirmados.
- Hay 11 archivos duplicados que conviene revisar como copias/portadas antes
  de enlazarlos al mismo Issue.
- Crear 211 Issues desde nombres es una mutación grande; mejor revisión
  explícita.

## 5. Validación ya hecha

- 222 IDs existen, no están `missing` y no tienen `issue_id`.
- 0 series con esos títulos en el catálogo.
- 0 anuales/especiales/packs/archivos sin número en el lote.
- 211 números únicos; 11 archivos extra por duplicado del mismo número.
- Sin archivos con rangos.

## 6. Siguiente

1. Revisar títulos/tradiciones y duplicados.
2. Backup + preflight + transacción única.
3. Aplicar y verificar 5/211/222.
4. Repetir con el siguiente bloque, dejando fuera las series ambiguas.
