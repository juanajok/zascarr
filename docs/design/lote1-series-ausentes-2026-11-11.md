# Lote 1 de series ausentes — propuesta revisada (2026-11-11)

> **Aplicado el 2026-11-11.** 5 series, 211 Issues y 222 enlaces. Backup:
> `/var/backups/zascarr/pre_lote1_series_ausentes_20261111_162955.sql.gz`
> (SHA-256 `86d5d094…b4c4`). Sin mover ni renombrar archivos.

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

## 3. Qué se escribió

En una transacción:

1. 5 filas `series`:
   - `kind=regular`
   - `tradition=american` salvo `20th Century Boys` (`manga`)
   - `parent_series_id=NULL`
   - `metadata_source=manual`
   - `start_year=NULL` (se enriquecerá después)
   - `metadata={"origen":"propuesta_series_ausentes_lote1","carpeta":...}`
2. 211 filas `issues` con `locked_fields` de identidad y `sort_order` numérico.
   `single_issue` en las cuatro series de grapas; `trade_paperback` en
   `20th Century Boys` (son volúmenes, corregido tras la validación).
3. 222 actualizaciones de `files.issue_id`.
4. **Ningún archivo se mueve, renombra ni borra.**

## 4. Decisiones tomadas

- No hay IDs de Comic Vine/GCD: son series locales `metadata_source=manual`.
- `Superman/Batman` se normaliza con barra; `20th Century Boys` es manga.
- Los 11 duplicados se enlazan al mismo Issue como copias/portadas.
- Se revisó antes de aplicar; no se creó nada fuera del lote.

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

## 7. Aplicación y verificación

| Dato | Resultado |
|---|---:|
| Series creadas | **5** |
| Issues creados | **211** |
| Archivos enlazados | **222** |
| Issues duplicados por número | **0** |
| Archivos movidos/renombrados | **0** |
| App tras aplicar | **healthy** |

IDs de serie:

- `Superman/Batman`: `80140880-69a8-4e0e-8891-738bb0a67399`
- `Transmetropolitan`: `5c684113-1efb-448c-abe4-092855305696`
- `Irredeemable`: `fc0e73df-6ba9-4571-bb64-a11c04aece6d`
- `20th Century Boys`: `616e1b0b-645c-4ed2-9962-8f5620386e96`
- `Doomsday Clock`: `8043439e-c14e-4f16-a305-9c13a2fc6bca`

Verificación posterior: 222/222 archivos apuntan a la serie y número
esperados; los 22 Issues de `20th Century Boys` quedaron en
`trade_paperback`; la app responde `healthy`.
