# Cortesía compartida: qué coordina y qué no (#134, MIT-M8-US02)

Este documento acompaña a [`especificacion-cortesia-compartida.md`](especificacion-cortesia-compartida.md)
y a [`benchmark-cortesia-compartida.md`](benchmark-cortesia-compartida.md). No repite el contrato:
aclara **el alcance de la coordinación**, que es lo que más fácilmente se malinterpreta.

## Qué se coordina: un solo proceso

El limitador vive en memoria del proceso (`utils/cortesia.py`) y lo comparten **todas** las
peticiones de esa instancia de ZascArr, sin importar qué cliente, ruta o tarea las haga:

- **Fuentes con cliente propio**: Comic Vine, AniList, Tebeosfera, GCD y el foro (incluido su
  `login`). Dos clientes distintos de la misma fuente comparten cola; fuentes distintas no se
  bloquean entre sí (salvo que compartan un host efectivo).
- **Portadas externas**: la descarga pasa por la cola **del host** del sitio del que vienen, con su
  intervalo del mapa allowlist→fuente; no hay reintento.
- **Lo que se comparte**: el turno (FIFO), la marca del último hueco por fuente y por origen
  normalizado `(esquema, host, puerto)`, y el bloqueo de un `Retry-After` (fuente + host).
- **Lo que no se comparte**: el backoff de un reintento es local a la llamada; el presupuesto de
  espera lo pone cada llamador (UI 10 s, fondo 30 s, portada 5 s).

## Qué NO se coordina

- **Otras instalaciones de ZascArr**: cada una tiene su propio limitador; no hablan entre sí.
- **Otros procesos o workers del mismo host**: con `uvicorn --workers N` (N > 1) cada proceso
  tiene su propia copia del limitador. **No hay detección de multi-worker** y no se finge que la
  haya: la política es conservadora **por instancia**, no global. El despliegue soportado es un
  solo worker (el del `Dockerfile`), igual que el importer y el orchestrator.
- **Scripts, cron u otras herramientas externas** que pidan a las mismas fuentes: quedan fuera.
- No hay estado en Redis ni en PostgreSQL ni en disco: si el proceso se reinicia, la cola y los
  bloqueos se pierden (lo peor que pasa es una petición más espaciada, nunca una ráfaga).

## Cómo se declara

- El snapshot declara siempre `"coordinacion": "proceso"` (§6.1 de la spec).
- **Ajustes → Fuentes de datos** dice en llano que la espera se comparte dentro de este ZascArr y
  que otras instalaciones no se coordinan.
- **Estado → Cortesía con las fuentes** muestra el mismo alcance junto a la tabla.
- `GET /api/estado/cortesia` devuelve el snapshot con `Cache-Control: no-store`; exige la misma
  sesión que el resto de `/api/` y no publica URL, query, claves, credenciales ni hosts fuera de la
  allowlist (solo nombre de host, contadores y segundos).

## Por qué es conservador

Con varias réplicas, cada una espera su intervalo: la fuente recibe como mucho N veces más
peticiones que con una sola. Aun así el ritmo sigue siendo bajo (1–2,5 s entre peticiones por
fuente) y es preferible a un sistema que afirme una coordinación global que no tiene. Si algún día
se soporta multi-worker, este documento y el snapshot tendrán que cambiar juntos.
