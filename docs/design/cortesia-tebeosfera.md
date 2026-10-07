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
HTTP del cliente (`_search_table` → `_throttle`) espera en él. Garantía: entre el **inicio** de dos peticiones a
Tebeosfera hay al menos 2,5 s, sea cual sea la instancia, el camino (Descubrir, enriquecedor) o la tarea
concurrente. Las peticiones fallidas también cuentan; una espera cancelada no cuenta como petición hecha.

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
mínimo elevado/respetado, fallos, cancelación, bucles de eventos distintos. No hay consultas reales ni esperas
reales.
