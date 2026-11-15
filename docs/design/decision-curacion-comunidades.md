# Decisión — Benchmark de UX y curación de comunidades de escaneos/tradumaquetas

**Fecha:** 2026-11-15
**Estado:** decisión de producto. **No integra fuentes externas.**
**Alcance:** benchmark de interacción y curación a partir de la lista aportada por el PO.
**Límites de evidencia:** no se han visitado canales de Telegram, grupos de Facebook ni foros
privados, y no se ha descargado material. La observación directa de esas interfaces es
**NOT RUN**. CompartiComics se observó solo en HTML público y se documenta aparte en
[benchmark-comparticomics.md](benchmark-comparticomics.md).

## 1. Decisión

**No se añade ninguna de estas comunidades como fuente de metadatos ni de descarga.**
Se usan únicamente como referencia de UX y curación. La app sigue gestionando la biblioteca
del usuario y, si este lo configura, habla con Prowlarr y sus clientes; no conoce ni
scrapea estos sitios.

Motivos:

- no hay licencia ni términos que autoricen el acceso automatizado o la redistribución;
- el contenido es de terceros (escaneos, tradumaquetas, recopilaciones) y en muchos casos
  enlaza a Telegram, Mega o foros;
- integrar descargas convertiría a ZascArr en facilitador de acceso, contra `LEGAL.md`
  §1 y §3;
- no hay API estable ni metadata fiable y persistente.

## 2. Modelos y matriz

Escala 1–5 **cualitativa, no medida**. Mide UX/curación, no volumen.

| Dimensión | Telegram | Foros | Blogs/FB | Guías | Agregadores | ZascArr hoy |
|---|---:|---:|---:|---:|---:|---:|
| Descubrimiento | 2 | 3 | 3 | 3 | 4 | 4 |
| Curación | 2 | 4 | 4 | 5 | 2 | 3 |
| Orden de lectura | 1 | 3 | 2 | 5 | 1 | 3 |
| Metadata/procedencia | 1 | 2 | 2 | 4 | 2 | 4 |
| Móvil | 5 | 2 | 4 | 2 | 4 | 4 |
| Baja fricción | 4 | 3 | 5 | 4 | 3 | 5 |
| Durabilidad | 2 | 3 | 3 | 3 | 1 | 5 |
| Legalidad | 1 | 1 | 1 | 2 | 1 | 5 |

Lectura: Telegram gana en inmediatez y móvil, pero pierde en búsqueda, metadata, orden y
persistencia. Las **guías cronológicas** son el activo de curación más valioso y el más
transferible a ZascArr. Los agregadores ganan en volumen, no en confianza.

## 3. Qué se adopta y qué se descarta

| Idea | Decisión |
|---|---|
| Órdenes de lectura y cronologías | **Adoptar/mejorar** la visibilidad de sagas y su orden ya existente |
| Curaduría con identidad (descripción, criterio, portada) | **Adoptar** en colecciones y sagas |
| Calidad y procedencia visibles | **Ya existe**; no importar etiquetas de terceros |
| Búsqueda por autor/etapa/año | **Adoptar** como mejora local de biblioteca |
| Favoritos y vistos recientemente | **Adoptar solo favoritos locales**; sin telemetría ni fuente externa |
| Tendencias/novedades de la comunidad | **Descartar**: sin datos propios sería inventado |
| Canales de Telegram como “fuente” | **Descartar**: sin catálogo, sin API, sin licencia |
| Mega, enlaces efímeros, invites | **Descartar**: rotura, seguridad y legalidad |
| Lectores externos recomendados | **Descartar**: ZascArr sirve su propia biblioteca |
| Contenido +18 | **Fuera de alcance** |

## 4. Tres mejoras locales priorizadas

### P1 · Sagas en la ficha de serie y orden de lectura

- **Problema:** el modelo ya guarda `story_arc_issues.reading_order` y existe `/ui/arcos`,
  pero desde la ficha de una serie no se ve en qué sagas participa ni en qué posición.
- **Qué:** fragmento perezoso «Sagas» en la ficha, con enlaces a `/ui/arcos/{id}` y la
  posición de la serie; sin nuevas fuentes.
- **Valor:** el activo que mejor funciona en las guías cronológicas, ya soportado por los
  datos existentes.
- **Esfuerzo:** S/M. **Dependencias:** servicio de arcos; sin migración.
- **Aceptación:** una serie en una saga muestra el enlace y la posición; una serie sin sagas
  no añade ruido; no se consulta hasta abrir/decidir el fragmento.

### P2 · Filtro por autor en Biblioteca

- **Problema:** los foros y comunidades se organizan por autores y etapas; Biblioteca
  permite editorial, personaje, saga y etiquetas, pero no autor.
- **Qué:** filtro por autor/creador usando `creators`/`issue_creators`, con enlace desde la
  ficha de serie y limpieza del filtro en la URL.
- **Valor:** navegación de curación real sobre datos ya existentes; sin scraping.
- **Esfuerzo:** M. **Dependencias:** consulta de creadores; sin migración.
- **Aceptación:** filtro por autor exacto, combinable con editorial/tradición, paginación y
  estado en URL; sin N+1 evidente.

### P3 · Favoritos locales

- **Problema:** las comunidades ofrecen favoritos/recientes; ZascArr no tiene una marca
  explícita de “serie favorita” (sí estado de lectura y Deseados).
- **Qué:** `favorite` local por serie (columna booleana), estrella en ficha/Biblioteca y
  filtro «Favoritas». Sin sincronización, sin telemetría, sin fuente externa.
- **Valor:** curación personal rápida; útil con cientos de series.
- **Esfuerzo:** M (migración + UI + filtros). **Dependencias:** nueva migración; no toca
  ficheros.
- **Aceptación:** marcar/desmarcar es idempotente; filtro y estado en URL; no altera
  búsqueda, etiquetas ni archivos; migración reversible.

## 5. Orden recomendado

1. **P1 Sagas en ficha** — mayor valor con el menor coste; aprovecha datos existentes.
2. **P2 Autor en Biblioteca** — curación real y combinable con filtros actuales.
3. **P3 Favoritos** — nueva persistencia; hacerla después de cerrar P1/P2.

## 6. PASS / FAIL / NOT RUN

- **PASS (decisión):** se separan ideas de UX de la copia/descarga; se descarta integrar
  las comunidades; se priorizan tres mejoras locales.
- **PASS (estado actual):** ZascArr ya tiene sagas/orden, colecciones, etiquetas, calidad y
  procedencia; no hay que reinventarlos.
- **FAIL (como fuentes):** todas las comunidades listadas carecen de licencia/términos y
  de API estable; no cumplen `LEGAL.md`.
- **NOT RUN:** observación directa de Telegram/Facebook/foros, validación con
  coleccionistas y estimaciones de esfuerzo reales (son orientativas, sin calibrar).
