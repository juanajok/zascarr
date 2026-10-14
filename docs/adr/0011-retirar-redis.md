# ADR 0011: Retirar Redis del stack

- Estado: **Aceptado** · 2026-10-15. Decisión de la persona responsable del producto, tomada en la conversación del
  2026-10-15 («Retiramos redis») a la vista del informe de la validación en la Pi
  ([`informe-validacion-pi-mvp-2026-10-13.md`](../design/informe-validacion-pi-mvp-2026-10-13.md), hallazgos 2–5) y de
  la entrada «Redis adoptado por otro proceso del host» del BACKLOG, que dejaba esta decisión pendiente (b).
- Relacionado: [ADR 0004](0004-exposicion-de-red.md) (enmienda del 2026-10-13: Redis ya no se publica), CLAUDE.md §1 y §4,
  `docs/BACKLOG.md` («Redis adoptado por otro proceso del host»), PR #191.

## Contexto

ZascArr llevaba un Redis en el `docker-compose.yml` («PostgreSQL + Redis» en el stack de CLAUDE.md §1) con un tope de
128 MB, un volumen de datos propio, `redis[hiredis]` y `arq` en las dependencias, un `FLUSHDB` en `rollback.sh` y una
variable `REDIS_URL`. En la validación en la Raspberry Pi (2026-10-13/14) apareció que **nada lo usa**:

| Comprobación | Resultado (sobre `main` en `a5369ef`) |
|---|---|
| ¿Algún módulo de `src/` importa `redis` o `arq`? | **No.** Solo aparecen en `pyproject.toml`, en dos campos de `config.py` y en docstrings. |
| ¿Se leyó `redis_url` o `redis_cache_ttl` alguna vez? | **No** (`git grep`: solo su definición). |
| ¿Hubo alguna vez un `import redis` / `from redis` / `import arq` / `from arq` en `src/`? | **No, en ninguna rama** (`git log --all -S"import redis" -- src` y las tres equivalentes: vacío). |
| ¿Qué dice la documentación? | CLAUDE.md §4: «el refresco periódico … usa Redis como canal»; `comic_vine.py`: «cacheadas en Redis 24h». **Ninguna de las dos cosas existe en el código.** |
| ¿Qué guardaba? | Nada de ZascArr: un `dump.rdb` heredado de ~160 MB con 7510 claves de prefijo `pcp`, ajeno. |

Con el tope aplicado y el puerto publicado en `127.0.0.1`, otro proceso del equipo lo adoptó y Redis entró en un bucle
de reinicios por OOM (hallazgo 2 del informe). #191 dejó de publicarlo; eso corrigió el síntoma, no la causa: seguía
siendo un servicio sin consumidor, con 128 MB de presupuesto en una Pi compartida (CLAUDE.md §1: «lo ligero y lo fiable,
primero»).

## Decisión

**Redis se retira del stack.** ZascArr no tiene cola ni caché externa: el refresco periódico corre en el propio proceso
(un solo worker, `uvicorn --workers 1`) con los intervalos de `config.py`, y lo que se guarda, se guarda en PostgreSQL.

### Qué cambia

| Pieza | Cambio |
|---|---|
| `docker-compose.yml` | Sin servicio `redis`, sin `REDIS_URL`, sin `depends_on` hacia él. |
| `pyproject.toml` | Se quitan `redis[hiredis]` y `arq` (dos dependencias menos en la imagen). |
| `config.py` | Se quitan `redis_url` y `redis_cache_ttl`. Un `REDIS_URL` que quede en un `.env` se ignora (`extra="ignore"`). |
| `bootstrap.sh` | No crea `redis/` ni levanta `redis`. |
| `scripts/update.sh` y `rollback.sh` | `up -d --remove-orphans`: una instalación anterior tiene un contenedor `zascarr-cache` que ya no está en el compose y, sin esto, seguiría vivo. `rollback.sh` ya no vacía ninguna caché. |
| `scripts/uninstall.sh` | **Sin cambio de lógica:** `down --remove-orphans` ya retira el contenedor heredado, y `--purge` sigue borrando `redis/` si existe (instalaciones anteriores). |
| Documentación | CLAUDE.md §1 y §4, README, SECURITY, runbooks de prueba y el guion de la Pi dejan de describir un Redis. **Los registros históricos** (BACKLOG, ADR 0004, CHANGELOG) **no se reescriben**: dicen lo que se sabía entonces. |

### Instalaciones existentes

1. Tras actualizar (`update.sh`), el contenedor `zascarr-cache` desaparece solo.
2. El directorio `<ZASCARR_DATA_DIR>/redis/` **no se borra automáticamente**: es de datos, y el `dump.rdb` puede ser ajeno
   a ZascArr (como en la Pi validada). Se puede borrar a mano cuando la persona lo decida; `uninstall --purge` lo borra.
3. La imagen `redis:7-alpine` queda en Docker, sin uso, hasta un `docker image prune` o `uninstall`.
4. Un **rollback** a un commit anterior vuelve a traer el servicio `redis` (su compose lo tenía); es inofensivo.

## Alternativas descartadas

- **Mantenerlo sin publicar** (lo que dejó #191). Arregla el vecino, no el problema: un contenedor, 128 MB y dos
  dependencias para nada, y una documentación que miente sobre el uso.
- **Mantenerlo «por si hace falta».** Una dependencia sin consumidor es superficie y RAM hoy a cambio de una necesidad
  hipotética; si aparece, se reintroduce con su motivo y su ADR (CLAUDE.md §2: «sin dependencias nuevas sin
  justificación», y su inverso: sin dependencias antiguas sin uso).
- **Sustituirlo por una caché en proceso o en PostgreSQL ahora.** No hay nada que cachear hoy: sería inventar el
  consumidor para justificar el reemplazo.

## Consecuencias

- **Menos:** un contenedor, hasta 128 MB de tope (≈ 4–12 MB reales en reposo), un volumen, dos dependencias y una
  variable de entorno; y una fuente de confusión en el mapa de puertos y en `docker ps`.
- **Se mantiene el límite de un solo proceso:** el espaciado de cortesía con las fuentes es **por proceso**
  (`utils/cortesia.py`), así que `--workers 1` sigue siendo una invariante. Si algún día se quisiera más de un proceso, el
  estado compartido (p. ej. en PostgreSQL) sería una decisión nueva.
- **Reversible:** reintroducir Redis es aditivo (servicio, dependencia y consumidor), y no hay datos de ZascArr en él.

## Lo que este ADR no decide ni verifica

- **No está ejecutado en la Pi ni desplegado.** La validación del 2026-10-13/14 se hizo con Redis en la pila; esta
  retirada tiene pruebas en el repositorio (`tests/test_sin_redis.py`) pero **no** una ejecución real de `update.sh` sobre
  una instalación con Redis.
- **`dump.rdb.ajeno`** (~160 MB, apartado en la Pi) es del operador: no se toca aquí.
- **La detección del cgroup de memoria en el instalador** (hallazgo 1 del informe) es una decisión separada.
