# Revisión de solo lectura del benchmark del parser (2026-10-08)

> Documento de metodología y resultados. **Sin rutas personales ni nombres de archivo completos**: el detalle por archivo (CSV de residuales y de cambios) se conserva en privado. Las categorías de error se describen por forma, no por nombre.

Solo lectura: no se ha escrito en la biblioteca, en el repositorio (los worktrees eran temporales), ni en producción. No se ha tocado el parser ni se ha añadido ninguna dependencia.

## 1. Qué se midió, con qué versión y con qué unidad
| Dato | Valor |
|---|---|
| Resultado oficial registrado | `scripts/medicion/README.md`, 2026-09-26: **83 % clasifica / 86 % veraz** con cohortes (73 % / 76 % antes), n = 62 contenidos únicos |
| SHA de esa medición | `90e6b67` (B21, v1.6.0, 2026-09-26) — **reproducido exactamente** aquí: 82,6 % / 85,7 % (→ 83 / 86) y, sin cohortes, 73,3 % / 76,4 % (→ 73 / 76) |
| SHA de esta revisión | `83a2943` (`main` tras #98), 2026-10-08 |
| Corpus de la muestra | carpeta de descargas del coleccionista (en adelante «Descargas»): 785 archivos, **762 «cómics»** por `COMIC_EXTS` (= 570 `.cbr` + 190 `.cbz` + 2 `.cb7`), 26 GB |
| Unidad de muestreo | la **ruta** de archivo (`muestra_bruta.csv`, semilla fija), estratificada por tamaño de la carpeta contenedora; 81 rutas = 62 contenidos únicos por SHA256 |
| Estratos | A_singleton: 6 de 6 rutas (censo); B_pequeña: 45 de 45 (censo); **D_grande: 30 de 711** (4,2 %). Pesos 6 / 45 / 711 |
| Etiquetas | `scripts/medicion/etiquetas.py`, escritas a mano antes de ejecutar el parser; **idénticas** en `90e6b67` y en `83a2943`. **Ninguna se ha corregido** |
| Integridad | el SHA256 de las 81 rutas coincide con el registrado el 2026-09-26 (0 diferencias) |

**Aclaración de alcance de la métrica.** «Clasifica» y «veraz» miden que el parser extrae el **título de serie y el número** que dice la etiqueta. **No** miden que el archivo se enlace con la serie, la edición ni el `Issue` correctos del catálogo.

## 2. Relación entre los 762 cómics y las 1.542 rutas
Son **dos corpus distintos que se solapan**, no uno el filtro del otro:
| | Descargas (benchmark) | Biblioteca de producción |
|---|---|---|
| Qué es | carpeta de descargas (origen del benchmark) | biblioteca registrada en producción |
| Archivos / cómics | 785 / **762** | 1.577 / **1.542** (la cifra de la auditoría B14 del 2026-10-05, `docs/design/auditoria-b14-carpetas.md`) |
| Formatos (cómics) | 570 cbr, 190 cbz, 2 cb7 | 1.234 cbr, 308 cbz |
| Tamaño | 26 GB | 171 GB |
| Copias exactas | 19 (SHA256) → **743 contenidos únicos** | 215 rutas repiten nombre y tamaño de otra (1.327 distintos); el SHA256 no se calculó entero (171 GB) |
| Solape | **369** pares idénticos de (nombre, tamaño) = 48 % de las 762 y 24 % de las 1.542; 25 de 25 pares muestreados (aleatorios, semilla 1) idénticos por SHA256 — **no acredita por sí solo los 369**: el solape se establece por (nombre, tamaño) y solo esa muestra se verificó por contenido | |
- De las 81 rutas de la muestra, 41 (51 %) están también en la biblioteca.
- Primer nivel de la biblioteca: Comics 1.156, Graphic Novels 140, Tebeos 95, Manga 87, BD 50, `_Unsorted` 14.
- **Consecuencia:** las cifras del benchmark describen la carpeta de descargas, **no** la biblioteca de 1.542. Para estimar la biblioteca habría que etiquetar una muestra de ella.
- La auditoría B14 se midió sobre la biblioteca (1.542 nombres) con el parser **anterior a #81**, y sin etiquetas de series: es otra medición, no comparable.

## 3. Repetición con la versión actual (mismas 81 rutas, mismas etiquetas)

### 3.1 La unidad del estimador (corrección de la revisión)
El diseño **selecciona rutas** y pondera con **poblaciones de rutas** (6 / 45 / 711). Pero la cifra oficial se calculó **deduplicando la muestra** por SHA256 (62 contenidos únicos) y **conservando esos pesos de rutas**: una mezcla de unidades que no estima bien ninguna de las dos cosas. Se publican, por tanto, **tres estimadores distintos** y se dice cuál es cuál:

| Estimador | Unidad | Pesos (población) | Denominadores A / B / D |
|---|---|---|---|
| **R** | ruta (las copias cuentan) | rutas: 6 / 45 / 711 | rutas de la muestra: 6 / 45 / 30 |
| **U-oficial** (el publicado el 2026-09-26) | mezcla: contenidos únicos **de la muestra**, pesos **de rutas** | rutas: 6 / 45 / 711 | únicos de la muestra: 6 / 26 / 30 |
| **U** | contenido único | contenidos únicos: **6 / 26 / 711** | únicos de la muestra: 6 / 26 / 30 |

**De dónde salen los pesos de U.** Los 38 archivos que comparten tamaño con otro (única forma de que dos archivos sean copias exactas) están **todos en el estrato B**, que se muestreó **entero** (45 de 45). Los 19 duplicados exactos de la población (762 → 743 únicos) son, por tanto, los 19 sobrantes de B (45 → 26): **A y D no tienen copias** y la población de contenidos únicos es 6 / 26 / 711 (suman 743).

Aciertos y denominadores por estrato y configuración (de ellos se reconstruyen exactamente las cifras; «clasifica» = serie y número correctos; «veraz» = no afirma nada falso):

**83a2943 (hoy)**

| Configuración | Estimador / unidad | Pesos (población) | Denominadores (A / B / D) | Aciertos «clasifica» (A / B / D) | Aciertos «veraz» (A / B / D) | Clasifica | Veraz |
|---|---|---|---|---|---|---|---|
| Nombre aislado | R — rutas | 6 / 45 / 711 | 6 / 45 / 30 | 1 / 22 / 23 | 6 / 38 / 23 | 74.6 % | 77.3 % |
| Nombre aislado | U-oficial — únicos de la muestra, pesos de rutas | 6 / 45 / 711 | 6 / 26 / 30 | 1 / 11 / 23 | 6 / 22 / 23 | 74.2 % | 77.3 % |
| Nombre aislado | U — únicos, pesos de contenidos únicos | 6 / 26 / 711 | 6 / 26 / 30 | 1 / 11 / 23 | 6 / 22 / 23 | 75.0 % | 77.1 % |
| Nombre + cohortes | R — rutas | 6 / 45 / 711 | 6 / 45 / 30 | 1 / 22 / 26 | 6 / 38 / 26 | 83.9 % | 86.6 % |
| Nombre + cohortes | U-oficial — únicos de la muestra, pesos de rutas | 6 / 45 / 711 | 6 / 26 / 30 | 1 / 11 / 26 | 6 / 22 / 26 | 83.5 % | 86.7 % |
| Nombre + cohortes | U — únicos, pesos de contenidos únicos | 6 / 26 / 711 | 6 / 26 / 30 | 1 / 11 / 26 | 6 / 22 / 26 | 84.5 % | 86.7 % |
| Pipeline completo | R — rutas | 6 / 45 / 711 | 6 / 45 / 30 | 1 / 22 / 26 | 6 / 38 / 26 | 83.9 % | 86.6 % |
| Pipeline completo | U-oficial — únicos de la muestra, pesos de rutas | 6 / 45 / 711 | 6 / 26 / 30 | 1 / 11 / 26 | 6 / 22 / 26 | 83.5 % | 86.7 % |
| Pipeline completo | U — únicos, pesos de contenidos únicos | 6 / 26 / 711 | 6 / 26 / 30 | 1 / 11 / 26 | 6 / 22 / 26 | 84.5 % | 86.7 % |

**90e6b67 (2026-09-26)**

| Configuración | Estimador / unidad | Pesos (población) | Denominadores (A / B / D) | Aciertos «clasifica» (A / B / D) | Aciertos «veraz» (A / B / D) | Clasifica | Veraz |
|---|---|---|---|---|---|---|---|
| Nombre aislado | R — rutas | 6 / 45 / 711 | 6 / 45 / 30 | 1 / 14 / 23 | 6 / 30 / 23 | 73.5 % | 76.3 % |
| Nombre aislado | U-oficial — únicos de la muestra, pesos de rutas | 6 / 45 / 711 | 6 / 26 / 30 | 1 / 7 / 23 | 6 / 18 / 23 | 73.3 % | 76.4 % |
| Nombre aislado | U — únicos, pesos de contenidos únicos | 6 / 26 / 711 | 6 / 26 / 30 | 1 / 7 / 23 | 6 / 18 / 23 | 74.4 % | 76.6 % |
| Nombre + cohortes | R — rutas | 6 / 45 / 711 | 6 / 45 / 30 | 1 / 14 / 26 | 6 / 30 / 26 | 82.8 % | 85.6 % |
| Nombre + cohortes | U-oficial — únicos de la muestra, pesos de rutas | 6 / 45 / 711 | 6 / 26 / 30 | 1 / 7 / 26 | 6 / 18 / 26 | 82.6 % | 85.7 % |
| Nombre + cohortes | U — únicos, pesos de contenidos únicos | 6 / 26 / 711 | 6 / 26 / 30 | 1 / 7 / 26 | 6 / 18 / 26 | 84.0 % | 86.2 % |
| Pipeline completo | R — rutas | 6 / 45 / 711 | 6 / 45 / 30 | 1 / 14 / 26 | 6 / 30 / 26 | 82.8 % | 85.6 % |
| Pipeline completo | U-oficial — únicos de la muestra, pesos de rutas | 6 / 45 / 711 | 6 / 26 / 30 | 1 / 7 / 26 | 6 / 18 / 26 | 82.6 % | 85.7 % |
| Pipeline completo | U — únicos, pesos de contenidos únicos | 6 / 26 / 711 | 6 / 26 / 30 | 1 / 7 / 26 | 6 / 18 / 26 | 84.0 % | 86.2 % |

**Lectura.** La cifra publicada (83,5 % / 86,7 %) es **U-oficial**. El estimador por rutas **R** da 83,9 % / 86,6 % y el de contenidos únicos **U**, 84,5 % / 86,7 %: las tres coinciden dentro de un punto y todas dependen de D. Se mantiene como cifra de referencia la publicada, **identificándola como U-oficial**, y se dan las otras dos como comprobación.

### 3.2 Resultados
- **Sin regresiones:** ningún veredicto empeora entre `90e6b67` y `83a2943` (el CSV privado de cambios). Mejoran 8 rutas (4 contenidos únicos) **en esta muestra de Descargas**, todas de «número perdido» a «ok»: `Tomo 1`, `Vol.1`, `Vol.2`, `vol.3` (**B15 parcial, v1.7.0**). No es una tasa de clasificación de la biblioteca.
- La capa 0 **no añade nada** en la muestra (2 archivos, mismo resultado que el nombre).
- **Incertidumbre.** Los estratos A y B son censos de sus rutas (sin varianza de muestreo); D son 30 de 711 y pesa el 93 %: la cifra global es en la práctica D, **26 de 30** (Wilson 95 %: 70,3–94,7 %). Error típico estratificado con la varianza atribuida solo a D: **5,7–5,8 puntos** (5,67 para R y 5,81 para U con corrección por población finita; ≈ 5,8 sin ella), de modo que el **margen normal al 95 % es ±11–11,4 puntos**. Es una aproximación con n = 30; no cubre el sesgo de selección ni de etiquetado.
- B_pequeña: «clasifica» baja (11 de 26 únicos) y «veraz» alta (22 de 26) porque son obras únicas o tomos sin número: no es un fallo de veracidad.
- **Representatividad.** La muestra tiene 9 `.cbz` de 81 (11 %); la población, 190 de 762 (25 %). Aumentar n no basta: haría falta estratificar también por formato y por origen, y ponderar al universo que se quiere estimar.

## 4. ComicInfo y formatos (censo completo, no muestra; solo lee las cabeceras)
| Corpus | CBZ con ComicInfo | CBR con ComicInfo | cb7 |
|---|---|---|---|
| Descargas (762) | **144 de 190 (75,8 %)** | **1 de 570** | 0 de 2 |
| Biblioteca (1.542) | 76 de 308 (24,7 %) | 1 de 1.233 (+1 ilegible) | — |
- Los 144 CBZ con ComicInfo de Descargas son todos «candidato fuerte» de capa 0 y **coinciden en serie y número con el nombre** (144 de 144): la coincidencia entre ComicInfo y nombre es **coherencia entre señales**, no una validación independiente de la identidad editorial: no hay etiquetas para decir que ambas acierten.
- «1 de 200» (sonda) se confirma con censo: **poca presencia de ComicInfo en los CBR de estos dos corpus**. No se generaliza a otros CBR ni a la escena en general. La extensión `.cbz` no acredita idioma ni procedencia. No se propone ninguna dependencia ni eliminar soporte.

## 5. Errores residuales (8 contenidos únicos = 11 rutas; detalle por archivo en un CSV privado)
Recuento corregido: la versión anterior de este informe decía «9 contenidos únicos = 12 rutas»; el recuento real es **8 únicos y 11 rutas** (62 únicos − 54 acertados o correctos-sin-número = 8; 11 filas con tres copias de dos archivos y una de otro). Cada residual tiene **una categoría principal**, de modo que los totales suman:

| Categoría principal | Únicos | Rutas | Formas |
|---|---|---|---|
| contexto | 3 | 5 | 1, 2, 7 |
| parser | 3 | 4 | 4, 5, 8 |
| identificación editorial | 2 | 2 | 3, 6 |
| **Total** | **8** | **11** | |

«Ausencia de serie local» **no se puede medir aquí** (requiere el catálogo de producción, que no se ha consultado). Detalle (la «categoría secundaria» cuando la hay):
| # | Forma del nombre | Rutas | Etiqueta → resultado | Principal (secundaria) |
|---|---|---|---|---|
| 1 | Abreviatura del título de la serie y separadores `_` | 2 (copias) | serie completa + nº 3 → abreviatura + subtítulo, nº 3 | contexto |
| 2 | Subtítulo de tomo delante de una abreviatura de la serie | 2 (copias) | serie + nº 1 → solo el subtítulo | contexto (identificación editorial) |
| 3 | Título con subtítulo separado por puntos y autor | 1 | título corto → título + subtítulo | identificación editorial (etiqueta discutible, **no se cambia**) |
| 4 | Segmentos separados por `_` (edición, autor, subidor) tras el título | 2 (copias) | título → título + edición + autor + subidor | parser |
| 5 | Prefijo de orden de lectura, posesivo de autor y nº en `(NN Ed.X)` | 1 | serie + nº 2 → «autor's serie» sin número | parser (identificación editorial) |
| 6 | Obra única de una serie con prefijo de orden de lectura | 1 | serie → serie + «Novela gráfica» con el prefijo | identificación editorial (contexto) |
| 7 | Autor delante de la obra y nº | 1 | obra + nº 14 → autor + nº 14 | contexto (etiqueta `requiere_contexto`) |
| 8 | Prefijo de orden de lectura y nº en `(NN Ed.X)` | 1 | serie + nº 18 → serie sin número | parser |
| | **Total** | **11** | | |

- Techo del nombre: 3 contenidos únicos de 62 llevan `requiere_contexto` (las formas 1, 2 y 7). Ninguno lo arregla el parser.
- **Observación acotada (no una regresión):** el patrón `(NN Ed.…)` deja **sin número 32 de 762 archivos** de Descargas (todos de una misma serie) y **0 de 1.542** de la biblioteca. No hay regresión en B21 ni B15; **no se propone cambio** (no autorizado).

## 6. Limitaciones que condicionan cualquier lectura
- **Una sola biblioteca de una sola persona.** Descargas y producción son corpus distintos; el benchmark describe Descargas. No es una tasa de clasificación de la biblioteca.
- **El solape de 369 archivos** se estableció por (nombre, tamaño). Solo una muestra aleatoria de 25 pares (semilla 1) se verificó por contenido (SHA256); el resto es una inferencia.
- **Sin etiquetas, «coincide» no es «acierta».** ComicInfo y nombre coinciden en 144 de 144, lo que es coherencia entre dos señales posiblemente correlacionadas, no validación independiente de la identidad editorial.
- **La métrica es de extracción** (título de serie y número). No mide el enlace con la serie, la edición ni el `Issue` del catálogo, ni la «ausencia de serie local».
- **Las etiquetas son juicio humano** escrito antes de ejecutar el parser; no se han modificado y alguna es discutible (marcada).
- **Reproducibilidad.** Los scripts están en `scripts/medicion/`; la revisión usó una copia del script en un directorio temporal para no sobrescribir `muestra81_etiquetada.csv`. SHAs: `90e6b67` (medición oficial) y `83a2943` (revisión).

## 7. Qué se reprodujo y qué se puede verificar desde lo publicado
| Cifra | Cómo se obtuvo | ¿Verificable solo con lo publicado? |
|---|---|---|
| 83 % / 86 % y 73 % / 76 % del 2026-09-26 (U-oficial en `90e6b67`) | **Reproducidas** aquí ejecutando el script en `90e6b67` con el corpus | **Parcialmente**: `scripts/medicion/etiquetas.py` (etiquetas) y `scripts/medicion/muestra81_etiquetada.csv` (rutas, estratos, veredictos de entonces) permiten recalcular el estimador U-oficial «con cohortes». **`muestra_bruta.csv` solo trae rutas y estratos, sin etiquetas ni resultados.** |
| Sin cohortes, con cohortes y pipeline completo en `83a2943` (y los estimadores R y U) | **Ejecutadas por mí** sobre el corpus (no publicado) en una copia temporal del script; resultados en un CSV privado | **No**: requieren los archivos del corpus (cohorte sobre la población y capa 0) |
| Poblaciones por estrato, 743 únicos, 38 archivos con tamaño repetido todos en B | Calculadas por mí sobre el corpus | **No** (corpus privado); el estrato de cada ruta sí consta en `muestra_bruta.csv` |
| Solape de 369 por (nombre, tamaño); 25 pares por SHA256 | Calculadas por mí | **No** |
| Censo de ComicInfo (144 de 190 CBZ; 1 de 570 CBR…) | Ejecutado por mí con `zipfile` y `7z l` (solo cabeceras) | **No** |
| Aritmética de la incertidumbre (Wilson, error típico, margen) | Recalculable a mano con los aciertos y denominadores de la tabla 3.1 | **Sí** |
