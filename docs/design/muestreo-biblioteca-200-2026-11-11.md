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
- `Flash 158 2.0`: el humano no entiende la variante; queda dudosa.
- `Crossover 07`: pendiente de una política de crossovers; queda dudosa.
- `GunSmith Cats [P2N2]` y `Los detectives muertos`: dudosas.

Resultado final:

| Estado | Filas |
|---|---:|
| Mantener | **187** |
| Corregir | **9** |
| Dudosa (excluida de métrica limpia) | **4** |
| **Total** | **200** |

Las 4 dudosas se marcan `excluir_benchmark=TRUE`. **Siguen siendo decisiones
humanas, no una validación de catálogo.**

## 4. Resultados con las 196 filas limpias

Normalización común: `Anual`≡`Annual` y sufijo de volumen fuera.

### Parser

| Medida | Resultado |
|---|---:|
| Serie correcta | **148 / 196 = 75,5 %** |
| Número correcto | **187 / 196 = 95,4 %** |
| Ambos correctos | **147 / 196 = 75,0 %** |

### Matcher

| Medida | Resultado |
|---|---:|
| `direct` | 53 |
| `fuzzy` | 22 |
| `unsorted` | 121 |
| Enlaces con Issue | 64 |
| Enlaces con serie+número correctos | **64 / 64** |
| Cobertura | **64 / 196 = 32,7 %** |
| Discrepancia de formato/tipo | **1** (XIII tomo enlazado a `single_issue`) |

Los 64 enlaces aciertan serie y número según las etiquetas. El único problema
de formato es `XIII 01`: el revisor lo etiquetó como tomo BD y el catálogo lo
tiene como `single_issue`; es una discrepancia de **edición**, no de identidad.

La cobertura sigue siendo el problema: alias de idioma (`100 Balas`/`100
Bullets`), series del catálogo con otro título, colecciones y huecos de Issue.

## 5. Fallos pendientes

- Subtítulos/colecciones: `Green Lantern: Emerald Warriors`,
  `Forever Evil: A.R.G.U.S`, `Green Lantern - Origenes Secretos`.
- Créditos delante: `Hiroaki Samura - La Espada del Inmortal`.
- Año dentro del título: `American Vampire 1976 10`.
- Prefijos de número delante de la serie (`16 Catwoman`, `51 Catwoman`): siguen
  ambiguos sin carpeta.
- Packs `#25 - Anual` sin rango: ya no producen número; la serie parcial
  (`Injustice`) sigue siendo el fallo restante.
- Alias y huecos del catálogo: limitan la cobertura del matcher, no su
  precisión de identidad.

## 6. Qué falta para un benchmark definitivo

1. Cerrar las 4 dudosas: Flash 2.0, crossover, GunSmith Cats y Los detectives
   muertos.
2. Decidir la política de títulos canónicos (`Shadow of the Bat` vs
   `Batman: Shadow of the Bat`, `Flash` vs `The Flash`, apóstrofos).
3. Repetir la medición manteniendo separado parser y matcher.
4. Convertir cada fallo confirmado en test de regresión.

## 7. Reproducción

- Muestreo: `scripts/medicion/muestreo_biblioteca.py --seed 20261112`.
- Aplicar revisión: `scripts/medicion/aplicar_revision_etiquetas.py`.
- Evaluar: `scripts/medicion/evaluar_muestra_200.py`.
- Resultado JSON: `/mnt/Datos/Documentos/resultados_muestra_200_humana.json`.
- Última regla: `#N - Anual` se trata como pack y no produce número; la
  métrica de número sube de 183 a **187**.
