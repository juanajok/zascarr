# Muestreo de 200 archivos y revisión simulada (2026-11-11)

> Muestreo de solo lectura. Los CSV contienen rutas reales de la biblioteca y
> se guardan fuera del repositorio. No se ha escrito en la biblioteca ni en la
> base de datos.

## 1. Población y muestra

Foto del 2026-11-11:

| Dato | Valor |
|---|---:|
| Archivos no ausentes | 5.049 |
| Con Issue | 1.493 |
| Sin Issue | 3.556 |
| Series | 51 |

Semilla **20261112**. Script:
`scripts/medicion/muestreo_biblioteca.py`.

| Estrato | Población | Muestra |
|---|---:|---:|
| Con Issue + anual | 71 | **20** |
| Sin Issue + anual | 8 | **8** (toda la capa) |
| Con Issue + normal | 1.422 | **60** |
| Sin Issue + normal | 3.548 | **112** |
| **Total** | **5.049** | **200** |

Composición: **80 con Issue / 120 sin Issue**, **28 anuales**, **186 CBR / 14
CBZ**, **0 SHA256 repetidos**. Los anuales se sobremuestrean a propósito
(~1,6% de la biblioteca); la muestra no es proporcional.

## 2. Archivos

```text
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11.csv
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11_etiquetada.csv
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11_etiquetada_revisada.csv
/mnt/Datos/Documentos/revision_simulada_200_2026-11-11.csv
/mnt/Datos/Documentos/cambios_revision_simulada_200.csv
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11_contexto.csv
```

El CSV de contexto no se usó para etiquetar. Los CSV con rutas no se commitean.

## 3. Etiquetado y revisión

La primera pasada se hizo **sin abrir el contexto ni ejecutar parser/matcher**;
las etiquetas llevan `etiquetado_por=asistente`.

La revisión independiente simulada dio 188 mantener / 10 corregir / 2 dudosas.
Después se recibió una **revisión humana** con 18 comentarios fila a fila. La
revisión humana manda sobre la simulada y revierte varias decisiones:

- 4 `Injustice ... #25/#41 - Anual`: el humano confirma que son **packs**
  (varios issues en un archivo), no anuales. Es la corrección más importante:
  el simulador los había convertido en anuales.
- `Catwoman 11.1 Annual 01`: annual de Catwoman, serie aparte con dependencia
  de la madre. `Catwoman 22.1 Year One`: se trata como especial análogo a un
  annual.
- `Horizontes Lejanos`: tomo de Las aventuras del Capitán Torrezno.
- `Bad Weekend - Criminal`: spin-off, se trata de forma análoga a
  anuales/especiales.
- `Lobo y Sovereign Seven`: se trata como especial.
- `Flash 158 2.0`: cerrado como **Flash #158, grapa**; `2.0` es versión/scan.
- `Crossover 07`: cerrado como **Dinastía de X #4, grapa**; el 07 es orden de
  lectura; la portada dice “4 de 6”.
- `GunSmith Cats [P2N2]`: cerrado como **GunSmith Cats #2, capítulo**; P2N2 es
  parte/número, no tomo 2.
- `Los detectives muertos`: cerrado como **tomo sin número**, edición ECC
  cartoné de 176 pp, 1 número.

Resultado final:

| Estado | Filas |
|---|---:|
| Mantener | **187** |
| Corregir | **13** |
| Dudosa | **0** |
| **Total** | **200** |

Las cuatro que quedaban dudosas se cerraron con evidencia de archivo y ficha
bibliográfica (portada, páginas internas, `7z`, Tebeosfera y comparación con
ComicTagger/Kapowarr). Ver
[`cierre-dudosas-2026-11-11.md`](cierre-dudosas-2026-11-11.md). **Siguen siendo
decisiones humanas, no una validación de catálogo.**

## 4. Resultados con las 200 filas

Normalización común: `Anual`≡`Annual` y sufijo de volumen fuera.

### Parser

| Medida | Resultado |
|---|---:|
| Serie correcta | **169 / 200 = 84,5 %** |
| Número correcto | **195 / 200 = 97,5 %** |
| Ambos correctos | **168 / 200 = 84,0 %** |

### Matcher

| Medida | Resultado |
|---|---:|
| `direct` | 82 |
| `fuzzy` | 15 |
| `unsorted` | 103 |
| Enlaces con Issue | 87 |
| Enlaces con serie+número correctos | **87 / 87** |
| Cobertura | **87 / 200 = 43,5 %** |
| Desajustes de formato/tipo | **2** (La Espada del Inmortal y XIII, tomos enlazados a `single_issue`) |

Los 64 enlaces aciertan serie y número según las etiquetas. El único problema
de formato es `XIII 01`: el revisor lo etiquetó como tomo BD y el catálogo lo
tiene como `single_issue`; es una discrepancia de **edición**, no de identidad.

La cobertura sigue siendo el problema, pero los alias seguros recuperan
`100 Balas`, `Shadow of the Bat`, `Smallville` y `WildCATS`. Además se aplicaron los lotes 1 y 2 de series ausentes (10 series, 410 Issues,
422 archivos): +5 y +9 enlaces nuevos en esta muestra. Ver
[`alias-catalogo-2026-11-11.md`](alias-catalogo-2026-11-11.md),
[`lote1-series-ausentes-2026-11-11.md`](lote1-series-ausentes-2026-11-11.md) y
[`lote2-series-ausentes-2026-11-11.md`](lote2-series-ausentes-2026-11-11.md).

Se añadió además un fallback de **serie completa exacta** para títulos partidos
por ` - `: `Green Lantern - Origenes Secretos` puede probar la serie completa si
la corta no matchea o si la completa es una coincidencia exacta más específica.
No se usa fuzzy alternativo. En esta muestra no añadió enlaces nuevos (el
catálogo no tiene esas series completas), pero no introdujo regresiones.

## 5. Fallos pendientes

- Subtítulos/colecciones que siguen fallando: `Green Lantern: Emerald Warriors`,
  `Forever Evil: A.R.G.U.S`, `Injustice: Gods Among Us - Año N` y
  `Supergirl: Woman of Tomorrow`. En varios casos el catálogo no tiene la
  serie completa; no se fuerza el título sin evidencia.
- Créditos delante: `Hiroaki Samura - La Espada del Inmortal`.
- Año dentro del título: `American Vampire 1976 10`.
- Prefijos de número delante de la serie (`16 Catwoman`, `51 Catwoman`):
  corregidos usando la carpeta como contexto.
- Packs `#25 - Anual` sin rango: ya no producen número; la serie parcial
  (`Injustice`) sigue siendo el fallo restante.
- Créditos delante y años dentro del título: corregidos con carpeta/patrón
  (`Hiroaki Samura`, `American Vampire 1976`).
- Subtítulos con carpeta exacta (`Green Lantern - Origenes Secretos`,
  `Superman: Year One`, `Joe Kubert Presents`): corregidos; el resto se deja
  como fallo de catálogo, no como invención.
- Alias y huecos del catálogo: limitan la cobertura del matcher, no su
  precisión de identidad.

## 6. Qué falta para un benchmark definitivo

1. Convertir los cuatro casos cerrados en tests de regresión.
2. Decidir la política de títulos canónicos (`Shadow of the Bat` vs
   `Batman: Shadow of the Bat`, `Flash` vs `The Flash`, apóstrofos).
3. Repetir la medición manteniendo separado parser y matcher.
4. Convertir cada fallo confirmado en test de regresión.

## 7. Reproducción

- Muestreo: `scripts/medicion/muestreo_biblioteca.py --seed 20261112`.
- Aplicar revisión: `scripts/medicion/aplicar_revision_etiquetas.py`.
- Evaluar: `scripts/medicion/evaluar_muestra_200.py`.
- Resultado JSON: `/mnt/Datos/Documentos/resultados_muestra_200_humana.json`.
- Reglas añadidas: `#N - Anual` es pack; `Crossover NN -` es prefijo de orden;
  las cuatro dudosas se cerraron con evidencia.
