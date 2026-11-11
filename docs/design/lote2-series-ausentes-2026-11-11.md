# Lote 2 de series ausentes — propuesta revisada (2026-11-11)

> **Aplicado el 2026-11-11.** 5 series, 199 Issues y 200 enlaces. Backup:
> `/var/backups/zascarr/pre_lote2_series_ausentes_20261111_163720.sql.gz`
> (SHA-256 `80fb5cf3…2059`). Sin mover ni renombrar archivos.

## 1. Criterios

- serie sin coincidencia en catálogo;
- una sola carpeta/edición, sin mezclar volúmenes;
- issues numéricos, sin anuales, especiales ni packs;
- títulos canónicos con volumen cuando corresponde;
- duplicados del mismo número se enlazan al mismo Issue.

Se descartan para este lote: `Flash`/`The Flash`, `Catwoman`, `Injustice
Año N`, `JLD`, `OP`/`One Piece`, `Monstress`, `Dreadstar` y `The Sandman`
(varias carpetas/arcos). `Teen Titans`, `Birds of Prey`, `Action Comics`,
`Superboy` y `Batgirl` quedan para el lote 3.

## 2. Contenido

| Serie propuesta | Archivos | Issues | Duplicados |
|---|---:|---:|---|
| `Booster Gold Vol. 2` | 48 | 48 (#0–#47) | — |
| `Batwoman Vol. 2` | 41 | 41 (#0–#40) | — |
| `Trinity Vol. 1` | 39 | 39 (#1–#39) | — |
| `Batwing Vol. 1` | 36 | 36 (#0–#34 + #12.1) | — |
| `Earth 2 Vol. 1` | 36 | 35 (#0–#32 + #15.1/#15.2) | #1 ×2 |
| **Total** | **200** | **199** | **1 archivo** |

Sin anuales, especiales, packs ni archivos sin número. El duplicado de
`Earth 2 #1` se enlaza al mismo Issue.

## 3. Qué se escribió

1. 5 filas `series`: `kind=regular`, `tradition=american`,
   `metadata_source=manual`, `start_year=NULL`, sin fuente externa.
2. 199 filas `issues`: `format=single_issue`, identidad bloqueada, `sort_order`
   numérico; los decimales (`12.1`, `15.1`, `15.2`) también son Issues
   individuales.
3. 200 actualizaciones de `files.issue_id`.
4. **Ningún archivo se mueve, renombra ni borra.**

## 4. Validación ya hecha

- 200 IDs existen, no están `missing` y no tienen `issue_id`.
- 0 series con esos títulos en catálogo.
- 0 anuales/especiales/packs/archivos sin número.
- 199 números únicos; 1 archivo extra por duplicado.
- Sin rangos ni tomos.

## 5. Siguiente

1. Revisar títulos con volumen y el duplicado `Earth 2 #1`.
2. Backup + preflight + transacción única.
3. Aplicar y verificar 5/199/200.
4. Preparar lote 3 con las series DC restantes.

## 6. Aplicación y verificación

| Dato | Resultado |
|---|---:|
| Series creadas | **5** |
| Issues creados | **199** |
| Archivos enlazados | **200** |
| Issues duplicados por número | **0** |
| Archivos movidos/renombrados | **0** |
| App tras aplicar | **healthy** |

IDs de serie:

- `Booster Gold Vol. 2`: `55935e7f-8df9-4107-93d5-0b67d5779eca`
- `Batwoman Vol. 2`: `5d342489-785d-40eb-8f70-a664e7380d54`
- `Trinity Vol. 1`: `9deadfcd-8722-4565-b3b5-de7d0e4e4a39`
- `Batwing Vol. 1`: `53e98464-e466-48db-af51-f798ad21fd0c`
- `Earth 2 Vol. 1`: `21ba9fb1-57d2-48db-8dc9-ea1f8bf433e9`

Verificación: 200/200 archivos apuntan a la serie y número esperados;
`Earth 2 #1` tiene dos archivos en el mismo Issue; la app responde `healthy`.
