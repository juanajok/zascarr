# Cortesía con Tebeosfera: espaciado compartido por proceso

## Qué decisión es

2,5 s como mínimo entre peticiones a Tebeosfera es una **decisión conservadora del proyecto**, no una afirmación
sobre una política oficial del sitio (que es de una asociación cultural sin ánimo de lucro). Se mantiene como
mínimo duro: una configuración (`TEBEOSFERA_RATE_LIMIT`) por debajo se **eleva** a 2,5 y se registra
`tebeosfera.rate_limit_elevado`; por encima se respeta.

## Qué fallaba

El límite vivía en la instancia (`TebeosferaClient._last_req`, a 0 al crearla). Descubrir crea un cliente por
búsqueda y el enriquecedor uno por ciclo, así que la primera petición de cada instancia no esperaba nada: dos
búsquedas seguidas, o una búsqueda durante el ciclo del enriquecedor, llegaban al sitio sin espacio entre ellas.
Cambiar solo el valor por defecto no lo arreglaba.

## Cómo se garantiza

`utils/cortesia.py::LimitadorDeCortesia`: un limitador **por sitio y por proceso** (`limitador_de("tebeosfera")`),
con un candado que hace cola FIFO y la marca de la última petición medida con `time.monotonic`. El único punto
HTTP del cliente (`_search_table` → `_throttle`) espera en él. Garantía: entre el **inicio** de dos peticiones HTTP a
Tebeosfera hay al menos 2,5 s, sea cual sea la instancia, el camino (Descubrir, enriquecedor) o la tarea
concurrente. **«Petición» es cada salto HTTP**, no cada llamada de alto nivel: una búsqueda emite dos
(colecciones y sagas) y cada redirección que se sigue es otra más, que espera igual. Las peticiones fallidas también cuentan; una espera cancelada no cuenta como petición hecha.

## Redirecciones

Antes el cliente usaba `follow_redirects=True` (los CDN devuelven 302): httpx emitía los saltos sin volver a pasar por
`_throttle`, así que una petición autorizada con un 302 producía dos peticiones sin los 2,5 s. Ahora
`follow_redirects=False` y `TebeosferaClient._enviar` sigue los saltos **a mano**, cada uno por el limitador:

- **Máximo `MAX_SALTOS = 3`** redirecciones (hasta 4 peticiones por consulta, ≥ 7,5 s entre la primera y la última).
  Pasado ese tope, o con una redirección sin `Location` o con un `Location` que no se pueda interpretar: la consulta
  se da por fallida (sin resultados) y no se sigue.
- **Destinos aceptados** (`destino_permitido`): solo el **origen del sitio**: https, host `www.tebeosfera.com`,
  puerto 443 o implícito, sin credenciales; una ruta relativa se resuelve contra la URL actual. Se rechazan otro host
  (también `tebeosfera.com` sin `www` y subdominios), `http`, otro puerto, `//otrohost`, credenciales y cualquier otro
  esquema. Al destino rechazado **no se envía nada**; se registra solo el host (`tebeosfera.redireccion_rechazada`).
- **Método:** 301/302/303 pasan a GET sin cuerpo; 307/308 conservan método y cuerpo. Otras 3xx (300, 304, 305…) no
  son redirecciones: fallo.
- Consecuencia: si Tebeosfera moviera el sitio a otro host (p. ej. sin `www`), las búsquedas dejarían de devolver
  resultados hasta actualizar `_BASE_URL`; se prefiere eso a seguir saltos a destinos no revisados.

## Qué NO garantiza (declarado)

- **Depende de un único proceso.** La imagen arranca `uvicorn --workers 1`, hay un solo servicio `zascarr` y el
  enriquecedor corre en ese mismo proceso (`main._enrichment_loop`): hoy cubre todos los caminos. Con varios
  workers o réplicas, cada proceso tendría su limitador (haría falta estado compartido, p. ej. en Redis).
- El espaciado de 3 s de `POST /api/revision/descubrir` (PR 2a) es una protección **provisional y propia de ese
  endpoint**; no es una garantía global de cortesía. La garantía global con Tebeosfera es esta.
- Los demás clientes (GCD, Comic Vine, AniList) siguen con el mismo patrón por instancia. Fuera de alcance de
  esta PR; se anota para una revisión aparte.

## Pruebas

`tests/test_cortesia.py` (limitador, reloj y espera simulados) y `tests/test_tebeosfera_cortesia.py` (cliente con
`httpx.MockTransport` y reloj simulado): instancias distintas en secuencia y concurrentes, los dos caminos de uso,
mínimo elevado/respetado, fallos, cancelación, bucles de eventos distintos y, para las redirecciones, un transporte que
registra **todos** los saltos: cadenas de 1 a 3, tope, destinos rechazados (sin que llegue nada al destino), método y
cuerpo por código, `Location` ausente o malformado, y cuatro búsquedas concurrentes con un 302 cada petición. No hay consultas reales ni esperas
reales.
