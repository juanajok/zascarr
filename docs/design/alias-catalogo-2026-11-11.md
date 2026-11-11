# Alias de catálogo seguros (2026-11-11)

> Las métricas de este documento son las de **antes** del lote 1 de series
> ausentes; la medición actualizada está en
> [`muestreo-biblioteca-200-2026-11-11.md`](muestreo-biblioteca-200-2026-11-11.md).

> Alias **de título**, no de identidad. Solo se aplican cuando la serie ya
> existe en el catálogo y comparte el mismo espacio de numeración. No se usa
> para inventar series ausentes.

## 1. Alias incorporados

| Título de release / etiqueta | Serie canónica |
|---|---|
| `100 Balas` | `100 Bullets` |
| `Shadow of the Bat` | `Batman: Shadow of the Bat` |
| `Shadow of the Bat Annual` | `Batman: Shadow of the Bat Annual` |
| `Smallville Temporada 11` | `Smallville: Season Eleven` |
| `WildCATS` | `WildC.A.T.s: Covert Action Teams` |

El matcher normaliza el título, consulta el alias y busca **exactamente** el
título canónico. No es fuzzy. El alias no cambia el número ni el formato.

## 2. Por qué no hay más

Estas series **no se aliasan** porque no son la misma línea de numeración o no
existen en el catálogo:

- `Green Lantern: Emerald Warriors` (serie propia, no `Green Lantern`).
- `Forever Evil: A.R.G.U.S`, `Arkham War`, `Rogues Rebellion` (tie-ins).
- `Injustice: Gods Among Us - Año 2/3/4/5` (líneas por año).
- `Supergirl: Woman of Tomorrow`.
- `The Corinthian: Death in Venice`.
- `Joe Kubert Presents` (el parser ya usa la carpeta; no hay serie canónica).
- `Green Lantern - Origenes Secretos`.

Aliasarlas a la serie madre produciría enlaces con el número equivocado. Para
esas hace falta **crear/enriquecer la serie**, no un alias.

## 3. Efecto medido

Sobre la muestra humana de 200:

| Medida | Antes | Con alias |
|---|---:|---:|
| Parser serie (evaluación alias-aware) | 162 | **169 / 200** |
| Parser número | 195 | **195 / 200** |
| Parser ambos | 161 | **168 / 200** |
| Matcher `direct` | 53 | **68** |
| Matcher enlaces con Issue | 65 | **73** |
| Matcher identidad serie+número | 65/65 | **73/73** |
| Cobertura | 32,5 % | **36,5 %** |
| Desajustes de formato | 2 | **3** |

Los tres desajustes de formato son `La Espada del Inmortal`, `XIII` y
`100 Balas Integral`: el humano los etiqueta como tomo, pero el catálogo tiene
el Issue como `single_issue`. Son problemas de formato/edición, no de
identidad.

## 4. Implementación

- `CATALOG_ALIASES` en `core/matcher.py`, con claves normalizadas.
- `find_series()` aplica el alias antes del exacto/fuzzy; nunca promociona un
  candidato fuzzy.
- Test PG que comprueba que el alias conserva la serie y el número.
- El evaluador también entiende los alias, para no contar `100 Balas` contra
  `100 Bullets` como un fallo de identidad.
