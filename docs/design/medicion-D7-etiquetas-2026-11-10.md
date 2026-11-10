# Medición D-7 — uso real de etiquetas y CBZ con `<Tags>` (2026-11-10)

**Qué pedía D-7** (#402): antes de seguir con las historias ETQ3–ETQ6, medir dos cosas: si las
etiquetas se usan de verdad y cuántos CBZ traen `<Tags>`/`<Genre>` que ETQ2 pueda leer.

**Cómo se midió.** `scripts/medicion/medir_d7_etiquetas.py` (solo lectura) dentro del contenedor
de la Pi, lanzado con `scripts/medicion/medir_d7_etiquetas.sh`. Recorre `/media/library` leyendo
únicamente `ComicInfo.xml` (≤ 1 MiB) con los topes de §7.4 y consulta la base de datos (conteos,
por fuente y top). Los `.cbr` (RAR) se cuentan aparte y **no se leen**: ETQ2 solo lee ComicInfo de
ZIP (`importer_triage.triage` sale antes de parsear en los formatos que no son ZIP), así que los
CBR quedan fuera de su alcance hasta convertirlos (BL-CNV).

**Salida (Pi, 2026-11-10):**

```
Biblioteca: /media/library
CBZ (ZIP): 518 · CBR (RAR, no leídos aquí): 4548
ComicInfo.xml presente: 145 (27%)
  con <Tags>: 0 · con <Genre>: 76 · con ambos: 0
  valores: <Tags> 0 · <Genre> 76
  sin ComicInfo: 373 · XML roto: 0 · no es ZIP: 0 · ComicInfo > 1 MiB: 0
=== Etiquetas en la base de datos ===
Etiquetas (espacio «etiqueta»): 3
Asignaciones: 3 (visibles 3, ocultas 0)
Series con al menos una etiqueta: 2 · etiquetas distintas en uso: 3
Por fuente (visibles): manual=3
Top: DC (1), Superheroes (1), samurai (1)
=== Identidad estructurada (ETQ3) ===
Series con géneros: 0 · asignaciones de género: 0 · personajes de número: 0
```

**Lectura**

1. **Uso real de etiquetas: incipiente.** 3 etiquetas, 3 asignaciones y 2 series, todas `manual`
   (2 de las 28 series de la colección, ~7 %; ver el denominador abajo).
   Es lo esperado dos días después de desplegar 1a/1b (2026-11-08/09) y no permite concluir
   adopción: la biblioteca tiene 5.066 tebeos y la función acaba de estrenarse. No hay señal de NO
   uso, pero tampoco de que ampliar la feature sea lo urgente.
2. **`<Tags>` en CBZ: 0 de 518.** ETQ2 no añadiría ni una etiqueta desde ComicInfo hoy: los CBZ
   del coleccionista no traen `<Tags>`. La parte de etiquetas de ETQ2 queda como camino preparado.
3. **`<Genre>` en CBZ: 76 de 518 (14,7 %)**, de los cuales 145 tienen ComicInfo. ETQ2 sí tiene
   datos de géneros que leer: poblaría `Series.genres` en hasta 76 series, que hoy está a 0.
4. **La colección es 90 % CBR (4.548 de 5.066)** y ETQ2 no lee ComicInfo de RAR: el universo
   medible se ampliará cuando BL-CNV convierta CBR→CBZ. Medir ahora solo CBZ es medir el alcance
   real de ETQ2, no un subconjunto arbitrario.
5. **Las tablas «dormidas» de ETQ3, confirmadas.** 0 géneros y 0 personajes en la BD: la premisa
   técnica de ETQ3 se cumple, pero el uso real de etiquetas aún no da señal de que ampliar el
   catálogo de identidad sea lo siguiente.

**Consecuencia para D-7**

- **ETQ2: desplegar** (ya fusionada en #544; desplegada el 2026-11-10 en `265a250`). Aunque
  `<Tags>` sea 0, hay 76 CBZ con `<Genre>`: poblará `Series.genres` (idempotente, sin pisar
  `manual`) en las importaciones nuevas o re-triadas, y deja el camino listo para cuando lleguen
  CBZ con etiquetas (BL-CNV ampliará el universo).
- **ETQ3: no abrir todavía.** La premisa técnica se confirma, pero D-7 pedía medir antes de seguir
  y la señal de uso es mínima (2 series etiquetadas, 0 géneros); además el 90 % de la biblioteca
  son CBR, fuera del alcance de la lectura de ComicInfo hasta la conversión. Se queda en
  refinamiento (tarjeta #565): se vuelve a medir después de desplegar ETQ2 y de que BL-CNV avance;
  entonces la señal (géneros poblados, etiquetas usadas) dirá si toca abrirla.
- **Cierre de #402:** como MVP (1a + 1b + ETQ2), cuando ETQ2 esté desplegada y su despliegue
  conste (registro como #515/#534). **Decisión del PO (2026-11-10): cerrar como MVP**; ETQ3 queda
  en refinamiento hasta que el uso lo pida.

**Limitaciones**

- ETQ2 aplica al **importar** o al re-triar un fichero que cambió (`rescan` no re-lee los
  intactos, `library_adopter.py::rescanear`): los 76 CBZ con `<Genre>` ya registrados no se
  poblarán solos. Si se quieren sus géneros sin esperar a reimportarlos, hace falta una relectura
  de la biblioteca registrada — historia aparte, no parte del cierre del MVP.

- Los 4.548 CBR no se han leído: no se conoce el porcentaje de ComicInfo con `<Tags>`/`<Genre>` en
  RAR. No es accionable para ETQ2 (no puede leerlos), pero sí lo será tras BL-CNV.
- **Denominador** (verificación de restore del propio update, 2026-11-10): **28 series, 1.295
  números y 5.063 ficheros registrados**. El uso de etiquetas es, por tanto, 2 de 28 series
  (~7 %). La herramienta incluye ya estos totales para la próxima medición.
