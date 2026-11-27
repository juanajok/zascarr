# Asociación automática de series a su fuente — aprendizajes (2026-11-23)

> Medición de solo lectura sobre la biblioteca real. Documento de trabajo: fija lo aprendido
> al buscar ID de fuente para 206 series sin fuente y propone el método corregido. No decide
> nada por sí solo; las asociaciones se aplican con confirmación y copia.

## 1. Qué se hizo

- Se buscó por **título** en Comic Vine (`search_series`, 5 candidatos) para las **206** series
  sin fuente y se puntuó cada candidato con: título 55 %, año 25 %, número de números 20 %.
- Se aplicaron las **7** propuestas con score ≥ 0,80 del piloto de 30 y después las **76**
  propuestas ≥ 0,80 de las 206.
- Resultado: **140 series con fuente** (130 Comic Vine + 9 Tebeosfera + 1 sin registro);
  **B9 = 1** (Monstress: editorial local «Cross Cult» frente a «Image» de la fuente: es la
  edición, no el ID).

## 2. Qué acertó y qué falló

| Confianza | Series | Lectura |
|---|---:|---|
| ≥ 0,80 | 76 | Aplicadas; identidad y año coinciden en su mayoría |
| 0,70–0,80 | 50 | A revisar: subconjuntos (local 30 de 57), ediciones españolas, anuales |
| < 0,70 | 65 | El título solo no basta; hay que mirar edición y archivos |
| Sin candidato | 15 | Títulos genéricos o de autor («Beto Hernandez», «1986a») |
| Error de fuente | 11 | Rate limit/red; reintentar |

**Falsos positivos vistos:** «Batgirl» local de 2011 contra la de 2025; «Batman DK2» contra
«Batman» (1940); «Batman v Superman» contra el cómic de General Mills; «Batman R.I.P.» (arco)
contra el one-shot; «100 Bullets Integral» (4 tomos) contra «100 Bullets» (2014, 1).
**Falsos negativos vistos:** «Action Comics Vol. 2» local 30 de 57 (es subconjunto, no error);
«Astérix» local 15 de 41; «Aquaman Vol. 7» local 55 contra una edición de 26.

## 3. Método corregido propuesto

1. **Normalizar el título** con `f_title_norm`: quitar acentos, artículos iniciales («The»,
   «La», «El»), sufijos de volumen («Vol. 2», «Vol 1»), «Integral/Omnibus/Tomo/Comp» como
   **marca de edición** (no del título) y comparar contra el título de la candidata.
2. **Leer los nombres de archivo** (`files.file_name`/`file_path`) y extraer año, número,
   «Annual», «Vol.», «Tomo/Integral/Omnibus»; usar el **año del archivo** cuando la serie no
   lo tenga y la **edición** para separar obra de recopilatorio.
3. **Comparar el número de números como subconjunto**: si la local tiene 30 y la candidata 57,
   es compatible (0,30 → no penalizar como si sobraran 27).
4. **Editorial**: pedir el detalle del volumen (`get_volume`, 1 petición) y comparar
   editorial; «DC Comics»/«DC» y «Image Comics»/«Image» son equivalentes (contención).
5. **Año con tolerancia ±1** y, si la serie no tiene año, usar el del archivo o la edición.
6. **Fuente según tradición**: Comic Vine para americana; Tebeosfera para tebeo español;
   GCD como contraste; AniList para manga. No buscar la misma serie en todas a ciegas.
7. **Umbrales**: ≥ 0,85 aplicar con evidencia; 0,70–0,85 revisión humana con la muestra;
   < 0,70 no proponer.
8. **Camino de alta**: el enricher **no toca** `metadata_source='manual'` y `AsociarFuente`
   exige identidad previa. Falta un camino explícito «asociar primera fuente» para series
   manuales, con confirmación y evidencia CCM; hoy se hizo con una escritura directa y
   recolección posterior, que no es un camino de usuario.
9. **Evidencia**: tras asociar, recolectar la ficha (`entity_source_records`) y medir B9; sin
   registro actual el ID no se puede afirmar.
10. **Evaluación**: guardar las propuestas y sus scores en un fichero local (títulos reales,
    no versionado) para medir precisión en la siguiente tanda.

## 4. Lo que no se debe automatizar

- Aplicar asociaciones por debajo de 0,85 sin revisión.
- Cambiar el `metadata_source` de series manuales en masa: el manual es una decisión del
  coleccionista.
- Dar por bueno un ID por el título: el año, la edición y el número de números son la prueba.
