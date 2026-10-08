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

## 3. Repetición con la versión actual (mismas 81 rutas, mismas etiquetas, 62 únicos; ponderado por estrato)
| Configuración | `90e6b67` (2026-09-26) | `83a2943` (hoy) |
|---|---|---|
| Nombre aislado | 73,3 % / 76,4 % | **74,2 % / 77,3 %** |
| Nombre + cohortes (cohorte calculada sobre las 762) | 82,6 % / 85,7 % | **83,5 % / 86,7 %** |
| Pipeline completo (capa 0 ComicInfo + cohortes) | 82,6 % / 85,7 % | **83,5 % / 86,7 %** (vías: 74 nombre, 5 cohorte, 2 ComicInfo) |

- **Sin regresiones:** ningún veredicto empeora entre `90e6b67` y `83a2943` (el CSV privado de cambios). Mejoran 8 rutas (4 contenidos únicos) **en esta muestra de Descargas**; no es una tasa de clasificación de la biblioteca, todas de «número perdido» a «ok»: `Tomo 1`, `Vol.1`, `Vol.2`, `vol.3` (**B15 parcial, v1.7.0**), +0,9 puntos.
- La capa 0 **no añade nada** en la muestra (2 archivos, mismo resultado que el nombre).
- **Incertidumbre.** Los estratos A y B son censos de sus rutas; D_grande es 30 de 711 y pesa el 93 %: la cifra global es en la práctica D. D: 26 de 30 (IC 95 % de Wilson 70–95 %). Global ≈ 83,5 % ± 11 puntos: **método** — estimador estratificado (A y B tratados como censos, sin varianza; D con 30 de 711, corrección por población finita), error típico ≈ 5,8 puntos, **intervalo de aproximación normal al 95 %** (±1,96 × error típico). Es una aproximación con n = 30 en D; el IC de Wilson de D solo es 70–95 %. B_pequeña: «clasifica» 11 de 26 únicos (42 %), «veraz» 22 de 26 (85 %): ahí «clasifica» es bajo porque son obras únicas/tomos sin número (no es un fallo de veracidad).
- **Representatividad.** La muestra tiene 9 `.cbz` de 81 (11 %); la población, 190 de 762 (25 %). Aumentar n no basta: haría falta estratificar también por formato y por origen, y ponderar al universo que se quiere estimar.

## 4. ComicInfo y formatos (censo completo, no muestra; solo lee las cabeceras)
| Corpus | CBZ con ComicInfo | CBR con ComicInfo | cb7 |
|---|---|---|---|
| Descargas (762) | **144 de 190 (75,8 %)** | **1 de 570** | 0 de 2 |
| Biblioteca (1.542) | 76 de 308 (24,7 %) | 1 de 1.233 (+1 ilegible) | — |
- Los 144 CBZ con ComicInfo de Descargas son todos «candidato fuerte» de capa 0 y **coinciden en serie y número con el nombre** (144 de 144): la coincidencia entre ComicInfo y nombre es **coherencia entre señales**, no una validación independiente de la identidad editorial: no hay etiquetas para decir que ambas acierten.
- «1 de 200» (sonda) se confirma con censo: **poca presencia de ComicInfo en los CBR de estos dos corpus**. No se generaliza a otros CBR ni a la escena en general. La extensión `.cbz` no acredita idioma ni procedencia. No se propone ninguna dependencia ni eliminar soporte.

## 5. Errores residuales por archivo (9 contenidos únicos = 12 rutas; `residuales_por_archivo.csv`)
«Ausencia de serie local» **no se puede medir aquí**: requiere consultar el catálogo de producción (5 series el 2026-10-05), que no se ha tocado; con 5 series, casi ningún archivo tendría serie local.
| # | Forma del nombre | Etiqueta → resultado | Categoría |
|---|---|---|---|
| 1 | Abreviatura del título de la serie y separadores `_` (×2 copias) | serie completa + nº 3 → abreviatura + subtítulo, nº 3 | **contexto** (la abreviatura solo la resuelve la carpeta o el catálogo) |
| 2 | Subtítulo de tomo delante de una abreviatura de la serie (×2 copias) | serie + nº 1 → solo el subtítulo | **contexto** + identificación editorial |
| 3 | Título con subtítulo separado por puntos y autor | título corto → título + subtítulo | **identificación editorial** (¿es subtítulo?; etiqueta discutible, **no se cambia**) |
| 4 | Segmentos separados por `_` (edición, autor, subidor) tras el título (×2 copias) | título → título + edición + autor + subidor | **parser** (separador `_`) |
| 5 | Prefijo de orden de lectura, posesivo de autor y nº en `(NN Ed.X)` | serie + nº 2 → «autor's serie» sin número | **parser** (nº entre paréntesis) + identificación editorial |
| 6 | Obra única de una serie con prefijo de orden de lectura | serie → serie + «Novela gráfica» con el prefijo | **contexto / identificación editorial** (el prefijo no llegó al umbral de cohorte) |
| 7 | Autor delante de la obra y nº | obra + nº 14 → autor + nº 14 | **contexto** (ambiguo por construcción; la etiqueta lo marca `requiere_contexto`) |
| 8 | Prefijo de orden de lectura y nº en `(NN Ed.X)` | serie + nº 18 → serie sin número | **parser** (nº entre paréntesis) |
- Techo del nombre: 3 contenidos únicos de 62 con `requiere_contexto` (las formas 1, 2 y 7). Ninguno lo arregla el parser.
- **Observación acotada (no una regresión):** el patrón `(NN Ed.…)` deja **sin número 32 de 762 archivos** de Descargas (todos de una misma serie) y **0 de 1.542** de la biblioteca. No hay regresión en B21 ni B15; **no se propone cambio** (no autorizado).

## 6. Limitaciones que condicionan cualquier lectura
- **Una sola biblioteca de una sola persona.** Descargas y producción son corpus distintos; el benchmark describe Descargas. No es una tasa de clasificación de la biblioteca.
- **El solape de 369 archivos** se estableció por (nombre, tamaño). Solo una muestra aleatoria de 25 pares (semilla 1) se verificó por contenido (SHA256); el resto es una inferencia.
- **Sin etiquetas, «coincide» no es «acierta».** ComicInfo y nombre coinciden en 144 de 144, lo que es coherencia entre dos señales posiblemente correlacionadas, no validación independiente de la identidad editorial.
- **La métrica es de extracción** (título de serie y número). No mide el enlace con la serie, la edición ni el `Issue` del catálogo, ni la «ausencia de serie local».
- **Las etiquetas son juicio humano** escrito antes de ejecutar el parser; no se han modificado y alguna es discutible (marcada).
- **Reproducibilidad.** Los scripts están en `scripts/medicion/`; la revisión usó una copia del script en un directorio temporal para no sobrescribir `muestra81_etiquetada.csv`. SHAs: `90e6b67` (medición oficial) y `83a2943` (revisión).
