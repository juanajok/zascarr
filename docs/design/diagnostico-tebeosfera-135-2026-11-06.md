# Diagnóstico de Tebeosfera en el banco de cobertura (#135) — 2026-11-06

> **Conclusión:** el parser y el formulario **no** están mal. La respuesta real de Tebeosfera
> devuelve, dentro de su único contenedor de resultados, las filas ajenas **antes** de la
> coincidencia buscada. No se cambia el parser ni la cortesía; la decisión de filtrar/reordenar
> candidatos es del PO.

## Petición de diagnóstico

- Endpoint: `POST https://www.tebeosfera.com/neko/templates/ajax/buscador_txt_post.php`
- Formulario: `tabla=T3_publicaciones`, `busqueda="Dragon Ball"` (dos campos esperados por
  `services/tebeosfera.py`).
- Cabeceras del cliente real: User-Agent de ZascArr, `Referer: https://www.tebeosfera.com/`,
  `Accept-Language: es-ES,es;q=0.9`.
- Respuesta: **HTTP 200**, `text/html`, **70 354 bytes**.
- Sin cookies de sesión, sin redirecciones y sin más peticiones: es la búsqueda de diagnóstico.
- Una petición previa **sin** `Referer`/`Accept-Language` devolvió `Error de acceso ajax (82943)`
  (29 bytes); el cliente de la app ya envía esas cabeceras, así que no es un fallo del arnés.

## Estructura observada

- Un solo `div#div_buscador_txt_T3_publicaciones`.
- **83** `div.linea_resultados`, **todas dentro** de ese contenedor; **0** fuera.
- No hay bloque de destacados/sidebar con `linea_resultados`: el XPath global actual no está
  cogiendo un bloque ajeno.
- Primeras filas reales del HTML:

  | # | Título (limpio) | Slug |
  |---|---|---|
  | 1 | BATMAN | `batman_2009_planeta-deagostini_-barcelona-` |
  | 2 | BATMAN | `batman_2014_ecc_-en_barcelona-` |
  | 3 | BOLA DE DRAC | `bola_de_drac_1992_planeta-deagostini_-col._superior-` |
  | 4 | BOLA DE DRAC | `bola_de_drac_1992_planeta-deagostini_-serie_vermella-` |
  | … | … | … (hasta 83) |

- `TebeosferaClient.search_series` concatena colecciones + sagas y recorta a `limit=10`; por eso
  el banco veía primero los dos BATMAN y luego las BOLA DE DRAC. La búsqueda de Mortadelo
  reproduce el mismo patrón con otros ajenos delante.

## Qué NO se toca

- El parser: los selectores y la limpieza del título siguen siendo válidos contra el HTML real.
- El formulario: `T3_publicaciones`/`T3_series` y `busqueda` siguen devolviendo resultados de la
  consulta (la cola incluye BOLA DE DRAC para "Dragon Ball").
- La cortesía (2,5 s, origen único, ≤3 saltos) ni el cliente.

## Qué decide el PO

1. Aceptar que Tebeosfera ordena resultados de forma amplia y que el banco debe marcar los
   ajenos como `incorrecto` en la revisión humana (no es un fallo de identidad del parser).
2. O pedir una política de filtrado/ranking de candidatos (p. ej. filtrar por similitud de título
   antes de recortar a 10), que sería una historia aparte: cambia la selección de candidatos, no
   el parser.

## Evidencia guardada

`docs/design/fixtures-cobertura/tebeosfera_dragon_ball_2026-11-06.html`: fragmento **recortado**
(contenedor + 3 primeras filas, sin imágenes) de la respuesta real, suficiente para el test de
diagnóstico `tests/test_tebeosfera_parser_135.py`. La respuesta completa no se versiona para no
redistribuir contenido de Tebeosfera.
