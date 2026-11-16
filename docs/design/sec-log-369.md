# SEC-LOG (#369): registros sin rutas ni datos de la colección

## Política

- De una ruta se registra `[ruta]`; de un archivo, `[archivo]`; de una URL, `[url]`
  (en texto libre se conserva solo el host, sin credenciales, ruta ni query).
- De una excepción se registra su **tipo** (`FileNotFoundError`, `OSError`…), no su
  mensaje ni la traza: el mensaje puede llevar la ruta de la biblioteca.
- Se conservan identificadores (`file_id`, `operation_id`, hashes cortos, contadores,
  estado y código de error), que son el diagnóstico suficiente.

## Mecanismo

`utils/log_privacidad.py`:

- `ruta_para_log`, `nombre_para_log`, `url_para_log`, `error_para_log` en las
  llamadas concretas, para que `structlog.testing.capture_logs` también vea el
  valor saneado.
- `sanear_evento`: procesador central para stdout y para el búfer de logs;
  redacta claves de ruta/archivo/URL, rutas embebidas y sustituye `exc_info` por
  `error_type`. Se instala en la cadena de `structlog` desde
  `registro_reciente.instalar_captura()`.
- `FiltroLogsSinRutas`: filtro de `uvicorn.error` para que las trazas 5xx
  tampoco publiquen rutas; deja el tipo de excepción y quita la traza.

## Inventario cubierto

`services/importer.py`, `services/library_adopter.py`, `services/tagger.py`,
`services/library_audit.py`, `services/forum_scraper.py`, `services/discovery.py`,
`services/blog_feed.py`, `services/exportacion_kavita.py`, `utils/cbz.py`,
`utils/cover.py` y `web/ajustes.py`.

## Pruebas

`tests/test_sec_log_369.py`: ayudantes, procesador central, búfer con excepción y
comprobación estática de las llamadas inventariadas. `tests/test_logs_recientes.py`
comprueba que el búfer ya no expone rutas.

## Límites

- Las trazas completas dejan de publicarse (se conserva el tipo); es una pérdida
  deliberada de detalle para no filtrar rutas.
- No cubre el registro de acceso de uvicorn (es #361), Postgres, Transmission ni un
  proxy inverso.
- No se ha probado con un lector de ficheros de logs externo.
