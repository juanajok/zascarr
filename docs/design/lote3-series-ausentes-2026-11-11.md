# Lote 3 de series ausentes — propuesta revisada (2026-11-11)

> **No aplicado.** No se han creado series, Issues ni enlaces. La propuesta
> está en `/mnt/Datos/Documentos/propuesta_lote_series_ausentes_3_2026-11-11.json`.

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

## 3. Qué se escribiría si se aprueba

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
