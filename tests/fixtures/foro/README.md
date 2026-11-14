Fixtures del foro IPB (SCR4).

- `login_latin1.html`: página de entrada real en ISO-8859-1 con `<meta charset>` y formulario
  de login con `action` real y `s=` oculto.
- `resultados_latin1.html` / `resultados_cp1252.html`: búsqueda con tildes/ñ y con `€` en cp1252.
- `flood_es.html` / `flood_en.html`: aviso de *Search Flood Control* de IPB (HTTP 200).
- `cero_resultados.html`: búsqueda vacía de verdad (sin caja de error).

Son bytes reales: el charset se detecta como en el foro, no se fuerza en la prueba.
