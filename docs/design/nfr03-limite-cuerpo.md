# NFR-03 — límite del cuerpo de las peticiones (#363)

## Decisión

Tope por defecto: **256 KiB** (`max_cuerpo_peticion_bytes = 262.144`), configurable
solo por `.env` (`config.py`). Es un contrato distinto del límite del campo `token`
de #115.

## Medición del cuerpo válido máximo de #115

`MAX_TOKEN_VINCULACION` es **73.229 caracteres** (calculado por el propio servidor).
La petición de confirmación válida máxima medida con `application/x-www-form-urlencoded`
y sus campos reales (`token`, `cursor_actual`, `pagina_desde`, `pagina_hasta`) es de
**~73,5 KiB**. 256 KiB deja un margen superior a **3×** y no rompe el lote máximo.

## Comportamiento

`LimiteCuerpoMiddleware` (ASGI puro) actúa en `POST`, `PUT`, `PATCH` y `DELETE`:

1. Si `Content-Length` declara más que el tope, responde **413** sin leer el cuerpo.
2. Si no hay cabecera, es falsa o el cuerpo llega `chunked`, cuenta los bytes
   realmente recibidos y corta en cuanto supera el tope. No llama a FastAPI, así que
   no hay validación, escritura ni efectos.
3. Un cuerpo dentro del tope se reproduce intacto para el resto de la aplicación.

GET/HEAD no pasan por el contador. El límite está cubierto por
`tests/test_nfr03_cuerpo.py` (cabecera declarada, cabecera falsa, chunked, cuerpo
pequeño y una ruta real de ZascArr).

## Límites

No se ha medido en la Pi ni con un servidor ASGI real de producción; las pruebas usan
el cliente de test y un servidor ASGI mínimo además de la app real.
