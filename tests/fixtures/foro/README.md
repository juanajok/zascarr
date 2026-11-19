Fixtures del foro IPB (SCR4).

- `login_latin1.html`: página de entrada real en ISO-8859-1 con `<meta charset>` y formulario
  de login con `action` real y `s=` oculto.
- `resultados_latin1.html` / `resultados_cp1252.html`: búsqueda con tildes/ñ y con `€` en cp1252.
- `flood_es.html` / `flood_en.html`: aviso de *Search Flood Control* de IPB (HTTP 200).
- `cero_resultados.html`: búsqueda vacía de verdad (sin caja de error).
- `showforum_real_anonimizado.html`: fragmento de un `showforum=5` real (IPB) con la estructura de
  la lista de temas (icono «nuevo mensaje», `tid-link`, paginación y `lastaction`); host, ids,
  títulos y usuarios son ficticios. Lo usa el humo del parser de #1017.

Son bytes reales: el charset se detecta como en el foro, no se fuerza en la prueba.
