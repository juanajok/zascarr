# Alta manual en catálogo de los títulos restantes (2026-11-11)

> Experimento aplicado. 4 series nuevas, 1 Issue y 1 enlace. Backup:
> `/var/backups/zascarr/pre_alta_catalogo_especiales_20261111_172812.sql.gz`
> (SHA-256 `1eeb1c21…1167`).

## 1. Qué se añadió

| Serie | Tipo | Issues | Archivos enlazados |
|---|---|---:|---:|
| `Catwoman Annual` | annual | 1 (`#2`) | 1 |
| `Criminal` | regular | 0 | 0 |
| `Lobo` | regular | 0 | 0 |
| `Lazarus: X+66` | regular | 0 | 0 |

- `Catwoman Annual #2` se creó y se enlazó **manualmente** al archivo
  `22.1 Catwoman Vol 02 Year One (1995).cbr`.
- `Criminal` (Bad Weekend), `Lobo - Año 1` y `Lazarus X+66` no tienen número
  canónico en la etiqueta humana: se creó la serie, **no un Issue inventado**.
- App: **healthy**. Sin mover ni renombrar archivos.

## 2. Resultado medido

| Medida | Antes | Después |
|---|---:|---:|
| Series en catálogo | 73 | **77** |
| Parser serie | 192 | **192 / 200** |
| Parser ambos | 192 | **192 / 200** |
| Matcher enlaces | 103 | **103** |
| Identidad serie+número | 103/103 | **103/103** |
| Cobertura | 51,5 % | **51,5 %** |
| Desajustes de formato | 2 | **2** |

El único enlace nuevo (`Catwoman Annual #2`) ya estaba contado por la
asignación manual; el matcher por nombre no lo encuentra porque el archivo
dice `22.1 Catwoman … Year One`.

## 3. Conclusiones

1. **Añadir la serie no arregla el parser.** El parser sigue extrayendo
   `Catwoman Year One`, `Lazarus`, `Bad Weekend` o `Lobo Año`; el catálogo
   solo aporta un destino.
2. **Para series con numeración propia y parser que emite la alternativa
   correcta** (Emerald Warriors, Forever Evil, Supergirl), el catálogo sí
   convierte el parser en enlace. Eso ya se vio en el lote 5.
3. **Para archivos especiales sin número no hay identidad que enlazar.**
   Crear un Issue `#1` habría sido inventar; la serie queda en catálogo pero
   el archivo sigue pendiente.
4. **El archivo de Catwoman está mal nombrado.** El anual #2 existe (julio
   1995), pero el nombre no lo dice; solo una asignación/manual o una regla
   de excepción puede resolverlo. No se generaliza.
5. **Falta una representación de “archivo de serie sin número”**: hoy
   `files.issue_id` obliga a tener un Issue. Para tomos/especiales haría falta
   un enlace a nivel de serie o un tipo de Issue especial explícito, no un
   número falso.

## 4. Recomendación

- Mantener las 4 series: son títulos reales y ayudan a la revisión manual.
- No inventar Issues para `Criminal`, `Lobo` ni `Lazarus: X+66`.
- Diseñar una vía de **pendiente de especial** con `series_id` sin
  `issue_number`, o un `Issue` marcado como one-shot sin número editorial.
- Para `Catwoman Annual #2`, conservar la asignación manual y documentar la
  excepción.
