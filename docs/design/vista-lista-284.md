# Biblioteca en lista compacta (BL-IT02, #284)

> Presentación alternativa de **Biblioteca** sobre las mismas series, filtros, orden y paginación. Sin entidad
> nueva, sin portadas en la lista, sin JavaScript ni consultas a fuentes. La presentación se elige con
> `vista=lista`; sin ese parámetro se mantiene la rejilla de tarjetas.

## 1. Columnas acordadas

La lista compacta muestra solo datos escalares del conjunto ya paginado:

| Columna | Origen | Si falta |
|---|---|---|
| Título | `Series.title`, enlace a la ficha | — |
| Año | `Series.start_year` | «No consta» |
| Tradición | `Series.tradition` con la etiqueta de la Biblioteca | «No consta» |
| Números | `Series.total_issues` | «No consta», nunca 0 |

No se incluye editorial: obligaría a cargar `Publisher` por fila o a una consulta extra; queda para otra
historia. Título completo siempre visible, sin `hover` ni portada.

## 2. Cambio de vista

- `GET /ui/biblioteca?vista=lista` (y `&vista=lista` en los fragmentos HTMX y en la URL canónica).
- El selector «Tarjetas / Lista» son enlaces GET que conservan `q`, tradición, editorial, personaje, saga y
  `page`; no hay ordenación nueva ni editor de columnas.
- La presentación se conserva en paginación, retirada de chips, «Limpiar todos», reintento y enlace de vuelta
  desde la ficha (que usa la URL canónica).
- `vista` inválida: 200, aviso «La presentación pedida no existe; se muestran tarjetas.» y rejilla normal.
- La vista no cambia la unidad: mismas series, mismo orden del servicio. Se añade `Series.id` como desempate
  final al `ORDER BY` para que dos series con mismo `sort_title`/año no se dupliquen ni se salten entre páginas.

## 3. Estados y accesibilidad

- La tabla usa `<caption>` para lectores, `<th scope="col">` y celdas con `data-label` en móvil; en ≤640 px
  cada fila se convierte en un bloque de pares etiqueta/valor, sin desborde horizontal.
- Vacío, sin resultados, error y reintento mantienen el contrato de #283; el selector de vista sigue disponible.
- En la lista no se pinta `ui.portada` ni se genera ninguna portada; abrir o paginar no descomprime cómics,
  no consulta fuentes y no escribe nada.
- Las tarjetas siguen siendo el valor por defecto y conservan su comportamiento.

## 4. Criterios → verificación

| # | Criterio | Prueba |
|---|---|---|
| 1 | Misma consulta/filtros/página y mismas series | `TestVistaLista::test_misma_serie_y_misma_pagina_al_cambiar_de_vista`, `…conserva_filtros_pagina_y_vuelta` |
| 2 | Título completo sin hover; solo columnas acordadas | `…la_lista_no_genera_portadas_y_muestra_titulo_completo`, `…encabezados_y_estado_actual` |
| 3 | Desconocido no es cero | `…valor_desconocido_no_se_convierte_en_cero` |
| 4 | Orden determinista y paginación sin duplicados | `Series.id` como desempate; prueba de paginación/URL en `TestVistaLista`; sin editor de orden |
| 5 | Vacío/error/carga distinguidos y contexto | Pruebas existentes de `TestIndex`/`TestResultados` + selector presente |
| 6 | Teclado, 375 px y zoom | Enlaces nativos y tabla semántica; captura real a 390 px; zoom 200 % **NOT RUN** |
| 7 | Sin portadas, fuentes ni escrituras | `…la_lista_no_genera_portadas…` y vista solo GET |
| 8 | No materializar todo el catálogo | Se reutiliza `list_series_paginado`; no se añade consulta por fila; medición Pi **NOT RUN** |

## 5. Browser y límites

- Chrome 156 + PostgreSQL 15 con 30 series: lista a 1722 y 390 px, sin desbordes; «No consta» se pinta en
  Números/Año; el selector Lista queda marcado con `aria-current="page"`.
- **NOT RUN:** lector de pantalla real, móvil físico, zoom 200 % con el control real, medición de prestaciones
  en la Pi y comparación de usabilidad con usuarios. No se ha ejecutado iTunes ni se ha copiado nada de Apple.
