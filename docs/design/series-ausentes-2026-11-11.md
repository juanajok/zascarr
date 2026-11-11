# Series ausentes en la biblioteca (2026-11-11)

> Censo de solo lectura. No se han creado series, Issues ni enlaces. La
> propuesta está en `/mnt/Datos/Documentos/propuestas_series_ausentes_2026-11-11.json`
> y contiene nombres reales.

## 1. Alcance

| Dato | Valor |
|---|---:|
| Archivos sin Issue | **3.556** |
| Archivos agrupados por parser/carpeta | **3.350** |
| Grupos de serie/título no presentes en catálogo | **534** |
| Grupos con ≥3 archivos (`crear_serie`) | **227** |
| Grupos con 1–2 archivos (`revisar`) | **307** |
| Confianza alta / media / baja | 87 / 140 / 307 |

La diferencia entre 469 grupos del primer agrupamiento y 534 viene de separar
ediciones por carpeta: `Flash (1987)` no es lo mismo que `The Flash`,
`Injustice Año 2` no es `Injustice Año 3`, y `Catwoman Vol 04` no es
`Catwoman Vol 05`.

## 2. Top de la propuesta

| Archivos | Título propuesto | Tipo | Tradición | Confianza |
|---:|---|---|---|---|
| 121 | Flash (1987) | regular | american | alta |
| 88 | Superman - Batman | regular | american | alta |
| 64 | Dreadstar | regular | american | alta |
| 59 | Justice League Vol. 2 | regular | american | alta |
| 56 | Detective Comics Vol. 2 | regular | american | alta |
| 55 | Aquaman Vol. 7 | regular | american | alta |
| 53 | Catwoman Vol 04 | regular | american | alta |
| 53 | Transmetropolitan | regular | american | alta |
| 48 | Booster Gold Vol. 2 | regular | american | alta |
| 41 | Batwoman Vol. 2 | regular | american | alta |
| 41 | Injustice Año 5 | regular | american | alta |
| 39 | Trinity Vol. 1 | regular | american | alta |
| 37 | Injustice (Año 1) | regular | american | alta |
| 37 | Irredeemable | regular | american | alta |
| 36 | Batwing Vol. 1 | regular | american | alta |
| 36 | JLD | regular | american | alta |
| 35 | Earth 2 Vol. 1 | regular | american | alta |
| 33 | Teen Titans Vol. 4 | regular | american | alta |

Hay ruido de agrupamiento que exige revisión (`JLD` debería ser
`Justice League Dark`, `Injustice (Año 1)` y `Injustice Año 5` deben
normalizarse, `Superman - Batman` quizá `Superman/Batman`).

## 3. Benchmark: cómo tratan series ausentes

| Proyecto | Comportamiento | Consecuencia |
|---|---|---|
| **Kapowarr** | Requiere un volumen de Comic Vine; los archivos sin volumen van a unmatched. | No auto-crea series desde el nombre; buena integridad, poca cobertura. |
| **Mylar3** | Igual: Comic Vine/GCB; no crea una serie inventada. | No resuelve un catálogo incompleto sin fuente. |
| **Komga** | Carpeta = serie; cada carpeta nueva se convierte en serie al escanear. | Crearía cientos de series; no resuelve identidad/numeración. |
| **Kavita** | Parser de nombre/carpeta; puede crear serie nueva desde el archivo. | Cobertura alta, control de identidad bajo. |
| **Suwayomi** | La serie viene de la fuente; no hay biblioteca local de cómics. | No aplica. |
| **ComicTagger** | Etiqueta ficheros; no gestiona catálogo. | No aplica. |

La conclusión es que **Komga/Kavita auto-crean**, pero a costa de no tener una
identidad editorial verificada. Zascarr es catalog-first: crear 227 series
desde nombres sin fuente repetiría el problema que se quiere evitar.

## 4. Recomendación

1. **No crear las 227 series en bloque desde el parser.**
2. Importar metadatos de una fuente (Comic Vine/GCD) para los grupos de
   confianza alta; eso da IDs, años y ediciones.
3. Si se opta por creación local, hacerlo en lotes pequeños revisados, con
   `metadata_source=manual`, sin IDs inventados, y separando por edición.
4. Empezar por grupos con **≥20 archivos y edición inequívoca**; los 307
   grupos de 1–2 archivos no compensan el riesgo.
5. Mantener `JLD`/`OP`/`Injustice` como **pendientes de normalización**, no
   crear series con abreviaturas.

## 5. Herramienta

`scripts/medicion/proponer_series_ausentes.py`:

- lee la DB en READ ONLY;
- parsea cada archivo sin Issue con la carpeta como contexto;
- separa grupos por serie + carpeta;
- agrega issues, tipo, tradición y confianza;
- escribe JSON para revisión.

No crea series ni Issues. El JSON incluye `propuestas` (534) y `top` (20).
