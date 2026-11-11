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

Semilla: **20261112**. Script:
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
- **186 CBR / 14 CBZ**.
- Categorías: Comics 175, Manga 17, Graphic Novels 5, Tebeos 3.
- **0 SHA256 repetidos** en la muestra.

## 4. Archivos generados

Fuera del repo:

```text
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11.csv
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11_etiquetada.csv
/mnt/Datos/Documentos/muestra_biblioteca_200_2026-11-11_contexto.csv
```

### `..._etiquetada.csv` (primera pasada de etiquetas)

Las etiquetas se rellenaron **sin abrir el CSV de contexto ni ejecutar el
parser**. Son una **primera pasada asistida**, no una validación humana:
`etiquetado_por=asistente`. Antes de usar los números como benchmark definitivo
hay que revisar, sobre todo, los 18 casos marcados `requiere_contexto=TRUE` y
los títulos canónicos con prefijo editorial (por ejemplo, si la etiqueta debe
ser `Shadow of the Bat` o `Batman: Shadow of the Bat`).

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
| `serie_real` | **Etiqueta** (primera pasada asistida); vacía al generar |
| `numero_real` | **Etiqueta** (primera pasada asistida); vacía al generar |
| `tipo_real` | **Etiqueta**: `grapa`, `anual`, `capitulo`, `tomo`, `obra_unica`, `pack`, `especial`, `desconocido` |
| `requiere_contexto` | **Etiqueta**: `TRUE` si sin carpeta/catálogo no se puede decidir |
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
8. La etiqueta `asistente` es una primera pasada: la revisión humana es
   obligatoria antes de publicar una métrica definitiva.

## 6. Resultado preliminar de la primera pasada

Métrica con la misma normalización para etiqueta y salida del parser
(`Anual`≡`Annual` y sufijo de volumen fuera). No es un benchmark humano
cerrado.

### Parser

| Medida | Resultado |
|---|---:|
| Serie correcta | 151 / 200 = **75,5 %** |
| Número correcto | 187 / 200 = **93,5 %** |
| Ambos correctos | 150 / 200 = **75,0 %** |
| Ambos + número no vacío | 146 / 200 = **73,0 %** |

### Matcher

| Medida | Resultado |
|---|---:|
| `direct` | 53 |
| `fuzzy` | 22 |
| `unsorted` | 125 |
| Enlaces con Issue | 64 |
| Enlaces correctos (serie y número) | **64 / 64** |
| Falsos positivos en pack/tomo/obra única/especial | **0** |
| Series correctas (con o sin Issue) | 66 / 200 |

La **precisión de los enlaces es 100%** en esta muestra, pero la cobertura es
baja: 64/200. La causa principal no es el matcher: hay series del catálogo con
otro título, alias de idioma (`100 Balas` vs `100 Bullets`), colecciones y
huecos de Issue. Eso es precisamente lo que hay que separar en la siguiente
iteración.

## 7. Segunda pasada de parser (sin tocar etiquetas)

Se corrigieron dos familias medidas:

- prefijos de orden de lectura (`13. Nightwing #73`, `14  JLD #11`,
  `73 Dreadstar ... 61`) y prefijo decimal (`22.1 Catwoman`);
- packs con rango + anual (`Batman #647-650 y anual 25`) que producían un
  número inexistente.

El parser pasó de **147 a 150** aciertos de serie+número. El matcher no cambió
en esta muestra (64 enlaces correctos), porque los archivos recuperados por el
parser siguen sin existir o sin alias en el catálogo. Las etiquetas no se
modificaron después de ver estos resultados.

### Familias de fallo observadas

- `Anual` vs `Annual` y títulos canónicos con prefijo (`Batman: Shadow of the
  Bat`).
- Prefijos numéricos de orden de lectura (`73 Dreadstar ... 61`,
  `13. Nightwing #73`) y números delante de la serie (`16 Catwoman`,
  `51 Catwoman`). Los primeros están corregidos; los segundos siguen siendo
  ambiguos sin carpeta.
- Packs que no son una grapa; el rango+anual ya no inventa número, pero
  `#25 - Anual` sin rango sigue necesitando una regla de contexto.
- Series con subtítulo/colección (`Green Lantern: Emerald Warriors`,
  `Forever Evil: A.R.G.U.S`).
- Créditos delante del título (`Hiroaki Samura - La Espada del Inmortal`).
- Años dentro del título (`American Vampire 1976 10`).

## 7. Qué se medirá después

- Parser: serie exacta/tolerante, número exacto, ambos, y **tasa de números
  inventados** (un número que no aparece en el nombre).
- Matcher: `direct`/`fuzzy`/`unsorted`, precisión de los enlaces, cobertura de
  los que tienen Issue y casos en que el catálogo no tiene el número.
- Corte por estrato: anual/no anual, con/sin Issue, español/inglés, formato.
- Criterio duro: **errores = 0** en los casos etiquetados; acertar más a costa
  de inventar no cuenta.
- Cada fallo etiquetado se convierte en test de regresión.

## 8. Limitaciones

- 200 etiquetas permiten detectar fallos y comparar versiones, no estimar
  precisión con un margen estrecho.
- La muestra está enriquecida en anuales y en archivos sin Issue; no es una
  estimación directa de la biblioteca completa.
- Las rutas y nombres son datos personales: los CSV no se commitean.
