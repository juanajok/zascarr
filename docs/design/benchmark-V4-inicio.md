# Ficha de benchmarking — V4b: Inicio guiado (primeros pasos)

> Procedimiento: `docs/design/benchmark-referencias.md`. Esfuerzo proporcional: es una pantalla de
> orientación sobre estados que ya existen, no un cambio de dominio.

**Historia / problema observado.** Un coleccionista recién instalado veía «5 series · 0 % completitud ·
0 pendientes» (U2 de la maqueta): ceros que se contradicen entre sí y que no le dicen qué hacer.
Además, el 0 % **mentía** de dos maneras: dividía los números que hay entre la suma del catálogo de
**todas** las fuentes (grapas de Comic Vine, capítulos de AniList, «números» de Tebeosfera), y mostraba
«0 %» cuando simplemente no había catálogo contra el que medir.

**Datos reales y medición de partida.** Entorno de ensayo con datos sintéticos (`docs/design/ui-v4/`):
3 series sin recuento de grapas, 6 por revisar, 5 deseados, un informe de duplicados guardado. El Inicio
anterior enseñaba `0%` y «Actualizadas recientemente: 3» (la longitud de una lista topada a 10).

**Referencias consultadas.** Sonarr, rama `v5-develop`, commit
`a8a82905e7cebad06a8414d84124cd13899abb89` (GPL-3.0; solo como patrón, **no se copia código**):
`frontend/src/Series/NoSeries.tsx` y `frontend/src/AddSeries/AddNewSeries/AddNewSeries.tsx`; textos en
`src/NzbDrone.Core/Localization/Core/en.json` (`NoSeriesFoundImportOrAdd`, `ImportExistingSeries`,
`AddNewSeries`). **No consultadas:** Radarr, Kapowarr, Mylar3, Suwayomi — no se buscó en ellas un
patrón de primera ejecución, así que **no se afirma que no lo tengan**.

**Cómo lo resuelve Sonarr.** Sin series en la biblioteca, la vista principal sustituye la cuadrícula por
un mensaje («importa tus series o añade una nueva») y **dos botones**: *Importar series existentes* y
*Añadir serie nueva*. No hay lista de pasos ni estado derivado: es un estado vacío con dos salidas.
*Añadir serie* acepta un parámetro `term` en la URL que prellena la caja y busca (`useQueryParams`).

**Supuestos de su modelo que NO valen en ZascArr.**
- Sonarr solo distingue «no hay series»; ZascArr tiene **cuatro** situaciones reales distintas (tebeos
  en el disco sin registrar, registrados sin clasificar, catálogo previo, nada) y dos acciones previas
  a tener series (mirar el disco → registrar) que Sonarr no tiene.
- Su «importar» es una sola acción; aquí **auditoría y adopción son hechos distintos** (B11/B16): un
  informe acredita que se miró el disco, no que la biblioteca esté registrada.
- Sonarr conoce el recuento de episodios por serie en una sola unidad; aquí el recuento solo es
  fiable para grapas de Comic Vine (`UNIDAD_DE_GRAPA`).

**Adoptar / adaptar / descartar.**
- **Adaptar:** estado guiado con acciones explícitas, no automáticas (el equivalente de «Importar
  existentes» es «Preparar mi biblioteca», que lleva a Duplicados, donde se mira y se registra).
- **Adoptar:** el parámetro de URL que prellena y lanza la búsqueda (`/ui/descubrir?q=`).
- **Descartar:** el estado vacío de dos botones como única guía (no cubre las cuatro situaciones) y
  cualquier importación automática al arrancar (B11: la adopción es una acción explícita).

**Invariantes de ZascArr (no mentir, no borrar, confirmación, coste Pi).**
- Ningún estado se marca a mano: cada uno sale de un hecho observado con una única fuente.
- Una cifra sin catálogo no se muestra como 0 %; un «0 huecos» no se presenta como colección completa.
- Nada se mueve, renombra ni borra desde el Inicio.
- Coste: 7 consultas de resumen + 5 pequeñas (pendientes, deseados, adopción, último informe, aviso
  legal) por carga. No se lee el JSON del informe (solo tres columnas). El recorrido del disco de
  `LibraryAdopter.estado()` ocurre **solo** mientras no hay marcador ni series (instalación nueva) y se
  detiene en el primer cómic; **no medido en la Pi**.

**Casos de prueba antes de implementar.** Matriz de la función pura (`tests/test_primeros_pasos.py`,
incluida una comprobación exhaustiva de invariantes sobre todas las combinaciones), pegamento
(`tests/test_inicio.py`), cifras (`tests/test_resumen.py`) y plantilla en cada estado
(`tests/test_web_dashboard.py`).

**Decisión final.** No cambia la arquitectura: sin ADR. Las decisiones de producto quedan en la ficha
V4 de `docs/BACKLOG.md`.
