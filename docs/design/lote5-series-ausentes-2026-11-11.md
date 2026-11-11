# Lote 5 de series ausentes — aplicado (2026-11-11)

> **Aplicado el 2026-11-11.** 6 series, 33 Issues y 33 enlaces, con 4
> reasignaciones correctivas. Backup:
> `/var/backups/zascarr/pre_lote5_series_ausentes_20261111_172321.sql.gz`
> (SHA-256 `92124240…047`).

## 1. Contenido

| Serie | Archivos | Issues | Reasignados |
|---|---:|---:|---:|
| `Green Lantern: Emerald Warriors` | 4 | 4 (#7–#10) | 4 |
| `Forever Evil: A.R.G.U.S` | 6 | 6 (#1–#6) | 0 |
| `Forever Evil: Arkham War` | 6 | 6 (#1–#6) | 0 |
| `Forever Evil: Rogues Rebellion` | 6 | 6 (#1–#6) | 0 |
| `Supergirl: Woman of Tomorrow` | 8 | 8 (#1–#8) | 0 |
| `The Corinthian: Death in Venice` | 3 | 3 (#1–#3) | 0 |
| **Total** | **33** | **33** | **4** |

## 2. Corrección de Emerald Warriors

Los 4 archivos estaban mal enlazados:

- `#07` a `Green Lantern: War of the Green Lanterns` #07;
- `#07/#08/#10` a `Green Lantern` #7/#8/#10.

Se creó `Green Lantern: Emerald Warriors` y se reasignaron los 4 archivos.
Los Issues antiguos no se borraron; simplemente dejan de tener esos archivos.

## 3. Validación

- 6 series nuevas con esos títulos; 0 colisiones.
- 33 IDs existentes y con nombre comprobado.
- 33 números únicos; sin anuales, especiales ni packs.
- 4 reasignaciones verificadas contra el `issue_id` anterior.
- App: **healthy**.
- Sin mover, renombrar ni borrar archivos.

## 4. Medición

| Medida | Antes | Después |
|---|---:|---:|
| Parser serie | 189 | **192 / 200** |
| Parser número | 197 | **197 / 200** |
| Parser ambos | 188 | **192 / 200** |
| Matcher enlaces | 95 | **103** |
| Identidad serie+número | 95/95 | **103/103** |
| Cobertura | 47,5 % | **51,5 %** |
| Desajustes de formato | 2 | **2** |

## 5. Lo que no se fuerza

- `Catwoman 22.1`: el archivo dice “22.1 … Year One” y la etiqueta humana es
  `Catwoman Annual #2`; el nombre no permite deducirlo. Investigación:
  el anual #2 existe (julio 1995), pero el archivo está mal nombrado.
- `Lazarus X+66`: sin catálogo, “Lazarus + X+66” es ambiguo con un subtítulo.
- `Bad Weekend`, `Lobo y Sovereign Seven`, `Lobo - Año 1`: especiales sin
  número canónico; no se inventan Issues.
- `Horizontes Lejanos`: se añadió alias de catálogo
  `Horizontes Lejanos` → `Las aventuras del Capitán Torrezno`.
