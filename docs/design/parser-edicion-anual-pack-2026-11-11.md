# Parser: Integral, Annual con prefijo y pack con rango (2026-11-11)

Tres fallos deterministas corregidos en `naming.py`, con tests.

## 1. `Integral` sin número pegado

Antes:

`100 Balas - Integral (Ed.Planeta) 01` → serie `100 Balas`, número `1`, sin
`edition_kind`; el matcher podía enlazarlo a una grapa `single_issue`.

Ahora:

- `edition_kind = "integral"` (formato esperado `omnibus`);
- serie `100 Balas`, número `1`;
- no se enlaza a una grapa si el catálogo no tiene el formato.

Se distingue de `Integral 20 aniversario` (efeméride, sin edición) y de
`La Patrulla X ... Omnigold nº 2` (Omnigold se conserva en el título).

## 2. `11.1 Annual 01 Catwoman`

Antes: serie `Annual 01 Catwoman`, número `11.1`.
Ahora: serie **`Catwoman Annual`**, número **`1`**, `is_annual=True`.

El patrón se aplica antes del prefijo numérico; el `11.1` de Villains Month
no secuestra el anual.

## 3. Pack `Batman #647-650 y anual 25`

Antes: serie `Batman # y anual 25`, sin número.
Ahora: serie **`Batman`**, sin número, `is_annual=True`.

Solo se limpia cuando hubo rango y no se encontró número único; no se toca
un pack que identifica un tomo (`Omnigold nº 2`).

## 4. Medición

| Medida | Antes | Después |
|---|---:|---:|
| Parser serie | 169 | **171 / 200** |
| Parser número | 195 | **196 / 200** |
| Parser ambos | 168 | **170 / 200** |
| Matcher enlaces | 91 | **94** |
| Identidad serie+número | 91/91 | **94/94** |
| Cobertura | 45,5 % | **47,0 %** |
| Desajustes de formato | 3 | **2** |

Los 2 desajustes restantes son `La Espada del Inmortal` y `XIII` (tomos
etiquetados por el humano, sin marca de edición en el nombre).

Tests: **177** del parser en verde; suite afectada completa en verde.
