# Lote 3 de series ausentes — propuesta revisada (2026-11-11)

> **Aplicado el 2026-11-11.** 5 series, 147 Issues y 151 enlaces. Backup:
> `/var/backups/zascarr/pre_lote3_series_ausentes_20261111_164711.sql.gz`
> (SHA-256 `bc344f6d…5775`). Sin mover ni renombrar archivos.

## 1. Criterios

- serie sin coincidencia en catálogo;
- una carpeta principal, sin mezclar ediciones;
- issues numéricos, sin anuales, especiales ni packs;
- título canónico con volumen cuando corresponde;
- duplicados del mismo número se enlazan al mismo Issue.

`Batgirl` entra solo con su carpeta principal (#0–#25); se deja fuera la
carpeta separada `2. Joker War + Tie-ins` (#47–#50), que se revisará aparte.

## 2. Contenido

| Serie propuesta | Archivos | Issues | Duplicados |
|---|---:|---:|---|
| `Teen Titans Vol. 4` | 33 | 33 (#0–#30 + #23.1/#23.2) | — |
| `Birds of Prey Vol. 3` | 32 | 32 (rango incompleto) | — |
| `Action Comics Vol. 2` | 30 | 30 (#0–#25 + #23.1–#23.4) | — |
| `Superboy` | 30 | 26 (#0–#25) | #2, #4, #5, #6 ×2 |
| `Batgirl` | 26 | 26 (#0–#25) | — |
| **Total** | **151** | **147** | **4 archivos** |

`Birds of Prey` no es una carrera completa: faltan números intermedios. No se
inventan Huecos ni Issues ausentes; solo se crean los números con archivo.

Los duplicados de `Superboy` son copias/portadas del mismo número y se
enlazan al mismo Issue, sin borrar archivos.

## 3. Qué se escribió

1. 5 filas `series`: `kind=regular`, `tradition=american`,
   `metadata_source=manual`, `start_year=NULL`, sin fuente externa.
2. 147 filas `issues`: `format=single_issue`, identidad bloqueada,
   `sort_order` numérico; los decimales (`23.1`, etc.) son Issues individuales.
3. 151 actualizaciones de `files.issue_id`.
4. **Ningún archivo se mueve, renombra ni borra.**

## 4. Validación ya hecha

- 151 IDs existen, no están `missing` y no tienen `issue_id`.
- 0 series con esos títulos en catálogo.
- 0 anuales/especiales/packs/archivos sin número.
- 147 números únicos; 4 archivos extra por duplicados.
- Sin rangos ni tomos.
- `Batgirl` con 0 Issues fuera de la carpeta principal.

## 5. Siguiente

1. Revisar el rango incompleto de `Birds of Prey` y los duplicados de
   `Superboy`.
2. Backup + preflight + transacción única.
3. Aplicar y verificar 5/147/151.
4. Revisar aparte la carpeta `Batgirl: Joker War + Tie-ins`.

## 6. Aplicación y verificación

| Dato | Resultado |
|---|---:|
| Series creadas | **5** |
| Issues creados | **147** |
| Archivos enlazados | **151** |
| Issues duplicados por número | **0** |
| Archivos movidos/renombrados | **0** |
| App tras aplicar | **healthy** |

IDs de serie:

- `Teen Titans Vol. 4`: `24faf0bf-93fc-4848-a5d5-098ccb9f3080`
- `Birds of Prey Vol. 3`: `489bc283-dfe5-4c2a-b2ec-d5408467303c`
- `Action Comics Vol. 2`: `4c6c0559-eb42-49f6-aeb9-ead8157cc5fe`
- `Superboy`: `82c0b8bd-fac6-4bc0-920b-a04d02fbe76f`
- `Batgirl`: `03aee66a-0dee-49b5-a6f7-563e24dccf60`

Verificación: 151/151 archivos apuntan a la serie y número esperados;
`Superboy` tiene 30 archivos en 26 Issues; `Batgirl` solo la carpeta
principal; la app responde `healthy`.
