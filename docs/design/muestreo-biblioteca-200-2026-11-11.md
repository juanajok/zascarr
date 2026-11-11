# Muestreo de 200 archivos para etiquetar parser/matcher (2026-11-11)

> Muestreo de solo lectura. Los CSV contienen **rutas reales** de la biblioteca
> y se guardan fuera del repositorio. No se ha escrito en la biblioteca ni en
> la base de datos.

## 1. Objetivo

Sustituir el benchmark de 81 rutas de Descargas por una muestra de la
biblioteca real, etiquetada **antes** de mirar la salida del parser. Se mide el
parser y el matcher por separado; los vínculos actuales del catálogo no son
verdad de referencia (ver `benchmark-parser-biblioteca-2026-11-11.md`).

## 2. Población y muestra

Foto del 2026-11-11:

| Dato | Valor |
|---|---:|
| Archivos no ausentes | 5.049 |
| Con Issue | 1.493 |
| Sin Issue | 3.556 |
| Series | 51 |

Semilla: **20261111**. Script:
`scripts/medicion/muestreo_biblioteca.py`.

## 3. Cuotas

| Estrato | Población | Muestra |
|---|---:|---:|
| Con Issue + anual | 71 | **20** |
| Sin Issue + anual | 8 | **8** (toda la capa) |
| Con Issue + normal | 1.422 | **60** |
| Sin Issue + normal | 3.548 | **112** |
| **Total** | **5.049** | **200** |

Los anuales se sobremuestrean a propósito: son ~1,6% de la población y
concentran los fallos de identidad. La muestra no es proporcional; cualquier
estimación debe ponderar o decir explícitamente que es una muestra
enriquecida.

Composición resultante:

- **80 con Issue / 120 sin Issue**.
- **28 anuales** (20 con Issue + 8 sin Issue).
- **172 CBR / 28 CBZ**.
- Categorías: Comics 175, Manga 17, Graphic Novels 5, Tebeos 3.
- **0 SHA256 repetidos** en la muestra.

## 4. Archivos generados

Fuera del repo:

```text
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11.csv
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11_contexto.csv
```

### `...csv` (ciego, para etiquetar)

Columnas:

| Columna | Uso |
|---|---|
| `id` | UUID del archivo; no cambiar |
| `archivo`, `ruta` | Nombre y ruta reales; no se copian al repo |
| `extension` | `cbr`, `cbz`, etc. |
| `estrato` | `con_issue_anual`, `sin_issue_anual`, `con_issue_normal`, `sin_issue_normal` |
| `categoria_carpeta` | Comics/Manga/Graphic Novels/Tebeos/_Unsorted |
| `sha256` | Identidad de contenido |
| `serie_real` | **Etiqueta manual**; vacío al generar |
| `numero_real` | **Etiqueta manual**; vacío al generar |
| `tipo_real` | **Etiqueta manual**: `grapa`, `anual`, `tomo`, `obra_unica`, `pack`, `desconocido` |
| `requiere_contexto` | **Etiqueta manual**: `TRUE` si sin carpeta/catálogo no se puede decidir |
| `notas` | Motivo de duda o decisión |
| `etiquetado_por`, `fecha_etiqueta` | Trazabilidad |

### `..._contexto.csv` (NO abrir al etiquetar)

Contiene el Issue actual del catálogo. Sirve para auditar después si la
etiqueta coincide o discrepa del vínculo existente. No debe usarse para
etiquetar: sesgaría la medición.

## 5. Protocolo de etiquetado

1. Abrir solo el CSV ciego.
2. Etiquetar **antes de ejecutar** el parser o el matcher sobre la muestra.
3. `serie_real` es el título canónico que el archivo afirma; si es un
   one-shot/tomo sin número, dejar `numero_real` vacío y marcar `tipo_real`.
4. Si hay dos interpretaciones razonables, anotar en `notas` y marcar
   `requiere_contexto=TRUE`; no elegir una al azar.
5. Un pack/rango (`#608-619`, `#647-650 + anual`) no es una grapa: `tipo_real=pack`
   y `numero_real` vacío.
6. No corregir etiquetas después de ver la salida del parser. Si hace falta una
   segunda pasada, conservar la primera y documentar el cambio.
7. No usar el CSV de contexto hasta que las 200 etiquetas estén cerradas.

## 6. Qué se medirá después

- Parser: serie exacta/tolerante, número exacto, ambos, y **tasa de números
  inventados** (un número que no aparece en el nombre).
- Matcher: `direct`/`fuzzy`/`unsorted`, precisión de los enlaces, cobertura de
  los que tienen Issue y casos en que el catálogo no tiene el número.
- Corte por estrato: anual/no anual, con/sin Issue, español/inglés, formato.
- Criterio duro: **errores = 0** en los casos etiquetados; acertar más a costa
  de inventar no cuenta.
- Cada fallo etiquetado se convierte en test de regresión.

## 7. Limitaciones

- 200 etiquetas permiten detectar fallos y comparar versiones, no estimar
  precisión con un margen estrecho.
- La muestra está enriquecida en anuales y en archivos sin Issue; no es una
  estimación directa de la biblioteca completa.
- Las rutas y nombres son datos personales: los CSV no se commitean.
