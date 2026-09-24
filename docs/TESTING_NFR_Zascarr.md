# Anexo NFR — Seguridad, capacidad y resiliencia de ZascArr

Este anexo amplía `TESTING_E2E.md` con requisitos no funcionales (NFR). No sustituye las pruebas funcionales: añade controles para detectar vulnerabilidades, degradación operativa, agotamiento de recursos, aislamiento insuficiente y problemas de recuperación.

## Convenciones

- Ejecutar siempre en un proyecto Docker aislado y con datos sintéticos.
- No usar credenciales, portadas ni archivos reales de la biblioteca.
- Cada prueba debe guardar comando, versión, logs, métricas y resultado.
- Un hallazgo de seguridad no se marca como `known failure` silencioso: se clasifica con severidad y decisión de release.
- Las pruebas destructivas se ejecutan exclusivamente contra volúmenes efímeros.

## NFR-01 — Secretos y configuración segura

**Objetivo:** impedir que credenciales inseguras lleguen a ejecución, logs o imágenes.

```bash
# No aceptar placeholders operativos en configuración efectiva.
if grep -RInE 'changeme|cambia_esto_ahora|password123|comics_admin:changeme' \
  --exclude-dir=.git --exclude-dir=.venv --exclude='*.md' \
  .env docker-compose.yml alembic.ini src scripts; then
  echo "FAIL: secreto o placeholder inseguro en configuración ejecutable"
  exit 1
fi

# La configuración efectiva debe depender de DATABASE_URL/variables de entorno.
"${COMPOSE[@]}" run --rm --no-deps zascarr python - <<'PY'
import os
url = os.environ.get("DATABASE_URL", "")
assert url, "DATABASE_URL ausente en el contenedor"
assert "changeme" not in url.lower()
assert "cambia_esto_ahora" not in url.lower()
assert "INVALID" not in url, "DATABASE_URL es un placeholder (INVALID)"
PY
```

**Oráculo:** no hay contraseñas reales ni placeholders inseguros en configuración ejecutable, logs, `docker inspect` ni imagen final.

```bash
docker inspect "$COMPOSE_PROJECT_NAME-zascarr-1" | grep -Eqi 'changeme|cambia_esto_ahora|INVALID:INVALID' && exit 1 || true
"${COMPOSE[@]}" logs zascarr | grep -Eqi 'password|DATABASE_URL|asyncpg://[^ ]+:[^ ]+@' && echo "REVISAR: secreto potencial en logs"
```

**Severidad:** P0 si hay credenciales utilizables o secretos en logs; P1 si solo hay ejemplos no ejecutables.

## NFR-02 — Exposición de red y aislamiento Docker

**Objetivo:** garantizar que PostgreSQL y Redis no están expuestos innecesariamente.

```bash
"${COMPOSE[@]}" config > "$ROOT/compose.rendered.yml"

# Detectar EXPOSICIÓN (0.0.0.0). El binding loopback "127.0.0.1:5432:5432" es
# el estado actual y aceptable (el bootstrap corre alembic en el host contra
# 127.0.0.1:5432 — deuda M3); "0.0.0.0:5432:5432" o "5432:5432" sin host SÍ
# serían exposición a la LAN.
if grep -nE '0\.0\.0\.0:(5432|6379)' "$ROOT/compose.rendered.yml"; then
  echo "FAIL: DB/cache expuestos en 0.0.0.0"; exit 1
fi
grep -nE '"127\.0\.0\.1:(5432|6379):' "$ROOT/compose.rendered.yml" || true

# Puertos escuchando en el host: deben ser solo loopback, nunca 0.0.0.0
ss -ltn 2>/dev/null | grep -E ':(5432|6379)\b'
```

**Oráculo:** PostgreSQL y Redis no se publican en `0.0.0.0`. El estado actual
los publica en `127.0.0.1` (loopback) por compatibilidad con el alembic del
bootstrap; eso es aceptable, y eliminarlo es la deuda M3. La app queda en
loopback (`127.0.0.1:$APP_PORT`). ZascArr dentro de Compose usa los nombres
internos `postgres` y `redis`, no `127.0.0.1`.

**Prueba negativa:** desde un contenedor externo en una red distinta, DB y Redis no deben ser accesibles; desde el servicio ZascArr sí deben serlo mediante los nombres internos `postgres` y `redis`.

**Severidad:** P0 si PostgreSQL/Redis están accesibles desde la LAN sin justificación.

## NFR-03 — Mass assignment y límites de entrada

**Objetivo:** detectar escritura de campos protegidos y payloads excesivos.

```bash
# Crear o usar una serie de fixture.
for field in id metadata_source locked_fields comic_vine_id anilist_id \
  tebeosfera_slug enrichment_attempted_at created_at updated_at title_norm; do
  payload="{\"title\":\"NFR-$field\",\"$field\":\"forged\"}"
  code=$(curl -s -o "$ROOT/mass-$field.json" -w '%{http_code}' \
    -X POST "$APP_URL/api/series" \
    -H 'Content-Type: application/json' -d "$payload")
  test "$code" = 422 || echo "FAIL conocido: $field aceptado con HTTP $code"
done
```

**Oráculo:** campos no declarados producen `422`; los campos protegidos nunca se modifican aunque el cliente envíe valores válidos en formato correcto.

Añadir también:

- JSON con 10 MB de texto.
- Título de más de 500 caracteres.
- Enteros fuera de rango.
- Arrays anidados inesperados.
- Content-Type incorrecto.
- Método HTTP no permitido.

**Severidad:** P0 para modificación de identidad, origen de metadatos o controles; P1 para ausencia de límites de tamaño.

## NFR-04 — XML, ZIP bombs y traversal

**Objetivo:** impedir DoS por `ComicInfo.xml`, extracción ZIP o rutas internas maliciosas.

Fixtures mínimas:

- XML con DTD y entidad recursiva.
- Entidad externa.
- XML de más de 1 MiB.
- ZIP con `../../evil.txt`.
- ZIP con muchas entradas.
- ZIP con tamaño descomprimido muy superior al comprimido.
- CBZ corrupto.
- CBR sin herramienta de extracción.

```bash
# Tras procesar cada fixture:
find "$ROOT" -name evil.txt -o -name outside-marker.txt
# Debe devolver vacío fuera de la zona temporal autorizada.

# El proceso no debe superar el timeout de protección.
timeout 30s "${COMPOSE[@]}" exec -T zascarr python /tmp/run_fixture.py
```

**Oráculo:** el ciclo termina, registra warning, no escribe fuera de la biblioteca y no aumenta el uso de memoria de forma descontrolada. Un XML normal sigue importándose.

Medir límite de memoria:

```bash
/usr/bin/time -v docker compose ...
```

**Severidad:** P0 si hay escritura fuera de la raíz; P1 si un fixture provoca crash o agotamiento de memoria.

## NFR-05 — Path traversal y enlaces simbólicos

**Objetivo:** impedir que nombres, rutas o symlinks escapen de `LIBRARY_PATH`.

Casos:

- Serie `../../outside`.
- Serie `/tmp/outside`.
- Número `../7`.
- Nombre Unicode normalizado.
- Archivo origen symlink a fuera de `DOWNLOADS_PATH`.
- Destino preexistente.
- Colisión con contenido distinto.

```python
assert destination.resolve().is_relative_to(library.resolve())
assert not destination.is_symlink()
```

**Oráculo:** se rechaza o sanea la entrada; nunca se sobrescribe el destino de otro archivo; el original permanece si la operación falla.

**Severidad:** P0.

## NFR-06 — Transacciones, consistencia e idempotencia de movimientos

**Objetivo:** detectar divergencias entre BD y filesystem tras fallos.

Inyectar fallos en estos puntos:

1. Antes del movimiento.
2. Durante copia entre discos.
3. Tras completar el movimiento, antes del commit.
4. Tras commit de BD.
5. Al actualizar File.
6. Durante compensación.

Comprobar tras cada fallo:

- El original no se pierde.
- No aparece un File apuntando a una ruta inexistente.
- No aparece un Issue duplicado.
- Repetir la operación es seguro.
- Un reconciliador o informe detecta cualquier operación incompleta.

**Criterio:** consistencia eventual documentada y operación repetible. Si no existe reconciliación, el fallo posterior al movimiento debe quedar registrado como P1.

## NFR-07 — Agotamiento de recursos y capacidad

**Objetivo:** comprobar que la aplicación respeta el presupuesto de Raspberry Pi.

Medir durante una carga sintética:

- RSS de ZascArr.
- RSS de PostgreSQL y Redis.
- CPU.
- conexiones activas de PostgreSQL.
- tamaño de pool.
- latencia p50/p95/p99.
- errores 4xx/5xx.
- tareas async pendientes.

```bash
docker stats --no-stream
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
  "select count(*) from pg_stat_activity;"
```

Carga recomendada:

- 1000 series sintéticas.
- 10.000 issues.
- 500 archivos CBZ pequeños.
- 200 consultas concurrentes a biblioteca.
- 20 peticiones simultáneas de portada.
- 50 archivos pendientes.

Criterios iniciales a ajustar con medición real:

- No superar el límite de memoria del contenedor.
- No bloquear el event loop con Pillow, ZIP o disco.
- p95 de lectura de biblioteca < 1 s en sandbox.
- Cero errores de conexión por agotamiento del pool.
- La concurrencia de portadas respeta el semáforo configurado.

No convertir estos umbrales en garantía universal para toda Raspberry: registrar hardware y dataset.

## NFR-08 — Resiliencia de PostgreSQL, Redis e integraciones

**Objetivo:** comprobar recuperación y degradación controlada.

### PostgreSQL

```bash
"${COMPOSE[@]}" stop postgres
curl -s -o /dev/null -w '%{http_code}\n' "$APP_URL/api/health"
"${COMPOSE[@]}" start postgres
# Esperar pg_isready y volver a probar salud.
```

Esperado:

- health reporta DB no disponible sin filtrar stack traces.
- no se corrompe estado.
- los loops reintentan en el siguiente ciclo.

### Redis

Repetir con Redis. Confirmar si Redis es obligatorio para arrancar o solo para caché; el criterio debe coincidir con la arquitectura.

### Servicios externos

Simular:

- timeout.
- DNS failure.
- HTTP 429 con `Retry-After`.
- HTTP 500.
- respuesta JSON inválida.
- redirección 302.
- conexión cerrada a mitad de respuesta.

**Oráculo:** timeout acotado, error registrado sin secretos, loop no bloqueado, reintento según política, no se marca caché negativa por un fallo transitorio.

## NFR-09 — Supervisión de tareas y cancelación limpia

**Objetivo:** detectar tareas huérfanas y shutdown incompleto.

```bash
"${COMPOSE[@]}" restart zascarr
sleep 5
"${COMPOSE[@]}" logs zascarr --tail 100
```

Durante el shutdown comprobar:

- las tareas de importer, enricher y orchestrator reciben cancelación;
- no quedan tareas Python pendientes;
- no se pierden commits ya confirmados;
- no quedan archivos temporales a medio copiar;
- el contenedor termina dentro de un timeout razonable.

Repetir 20 ciclos `restart` y comprobar que no aumenta el número de tareas ni conexiones.

## NFR-10 — Backpressure, concurrencia y doble procesamiento

**Objetivo:** evitar que dos ciclos procesen el mismo archivo o wishlist.

Lanzar dos importadores y dos orquestadores simultáneos con el mismo dataset.

Criterios:

- un archivo no se importa dos veces;
- no se crean dos Issues iguales;
- no se envían dos descargas para el mismo Wishlist;
- no se pisan destinos;
- el estado final es válido aunque haya carreras.

Si el diseño no incorpora locks o constraints suficientes, registrar el caso como P1, no como comportamiento aceptable implícito.

## NFR-11 — Segregación de roles y autorización

ZascArr es actualmente de un solo operador y no implementa usuarios ni roles. Por eso la prueba no debe inventar una separación que el producto no ofrece: debe comprobar que la ausencia de autenticación está declarada como riesgo de despliegue.

### Comprobar superficie de administración

Enumerar rutas:

```bash
python - <<'PY'
from zascarr.main import app
for route in app.routes:
    print(getattr(route, "methods", None), getattr(route, "path", None))
PY
```

Clasificar:

- lectura pública;
- escritura de biblioteca;
- descarga/búsqueda;
- cambios de configuración;
- aceptación legal;
- documentación OpenAPI.

### Pruebas

- `GET /api/openapi.json` no expone secretos, contraseñas ni rutas locales.
- Swagger no permite ejecutar acciones peligrosas sin la protección prevista.
- Endpoints de escritura no son accesibles desde un listener público si el despliegue no tiene autenticación.
- El aviso legal no se trata como autenticación.
- La aplicación no afirma tener segregación de roles que no existe.

**Criterio de release:** si se despliega fuera de localhost sin reverse proxy/autenticación, FAIL de seguridad operacional o bloqueo de release según el perfil de despliegue.

## NFR-12 — CORS, cabeceras y exposición HTTP

> **Nota de estado:** el middleware CORS fue **eliminado** (la UI Jinja2/HTMX y
> la API viven en el mismo origen; no hay peticiones cross-origin legítimas).
> Este NFR verifica que NO se emite `Access-Control-Allow-Origin` en absoluto.

Comprobar:

```bash
curl -si "$APP_URL/api/health"
curl -si -H 'Origin: https://evil.example' "$APP_URL/api/health"
```

Revisar:

- No se emite `Access-Control-Allow-Origin` (sin middleware CORS; la UI es same-origin).
- No se filtran `Server` o versiones si se han decidido ocultar.
- `Cache-Control` es correcto para portadas y respuestas privadas.
- OpenAPI y redoc se desactivan o protegen cuando el despliegue lo requiera.
- No hay stack traces en respuestas 500.
- Los mensajes no incluyen URLs con credenciales.

## NFR-13 — Inyección, XSS y salida HTML

Usar fixtures con:

```text
<script>alert(1)</script>
<img src=x onerror=alert(1)>
"><svg/onload=alert(1)>
```

Introducirlos en:

- título de serie;
- nombre de archivo;
- notas de wishlist;
- nombre de editorial;
- resultados de personajes y sagas.

Comprobar que las plantillas Jinja escapan el contenido y que no se usa `|safe` salvo para Markdown legal previamente controlado.

Con navegador automatizado:

- no aparecen diálogos inesperados;
- no se ejecutan handlers inline procedentes de datos;
- el contenido aparece como texto.

## NFR-14 — Limitación de abuso y disponibilidad

Aunque sea single-user, probar:

- 100 peticiones simultáneas a endpoints de búsqueda;
- 100 peticiones de portada fría;
- 100 POST repetidos a wishlist;
- payloads de gran tamaño;
- conexiones que envían el body lentamente;
- peticiones canceladas a mitad.

Criterios:

- no crece sin límite el pool de conexiones;
- no se disparan cientos de descargas externas;
- no se degrada todo el servicio por una portada lenta;
- los semáforos y timeouts funcionan;
- se documenta si la limitación de peticiones se delega al reverse proxy.

## NFR-15 — Integridad de logs y privacidad

Buscar en logs:

```bash
"${COMPOSE[@]}" logs zascarr > "$ROOT/zascarr.log"
grep -Eiq 'password=|apikey=|authorization:|cookie=|DATABASE_URL|postgresql\+asyncpg://[^ ]+:[^ ]+@' "$ROOT/zascarr.log" \
  && echo "FAIL: secreto potencial en logs" || echo "PASS: sin patrón obvio de secretos"
```

También comprobar:

- rutas de usuario no se imprimen innecesariamente;
- consultas externas no incluyen credenciales;
- errores de terceros se truncan si contienen contenido potencialmente sensible;
- logs estructurados permiten correlacionar un ciclo sin exponer datos personales.

## NFR-16 — Integridad de backup y recuperación ante desastre

Además del `pg_dump` funcional:

1. Restaurar en una BD temporal.
2. Comparar conteos de series, issues, files, wishlist y legal acknowledgments.
3. Comprobar que el gzip pasa `gunzip -t`.
4. Crear backup corrupto y verificar que se detecta.
5. Simular disco de backup lleno.
6. Simular `pg_dump` fallido.
7. Verificar que un backup parcial nunca se presenta como válido.
8. Comprobar permisos del archivo y que no es world-readable si contiene datos sensibles.

**Criterio:** el script usa temporal + `mv` atómico; cualquier error devuelve exit code distinto de cero; no borra backups válidos anteriores.

## NFR-17 — Escaneo de dependencias e imagen

En CI o entorno controlado:

```bash
pip-audit -r <(python -m pip freeze) || true
trivy fs --exit-code 1 --severity HIGH,CRITICAL .
trivy image --exit-code 1 --severity HIGH,CRITICAL zascarr:latest
```

Si las herramientas no están disponibles, registrar `NOT RUN`, no `PASS`.

Revisar también:

- imagen base actualizada;
- usuario no root si es compatible;
- filesystem de la aplicación de solo lectura si el diseño lo permite;
- capabilities Linux mínimas;
- no se concede `privileged: true`;
- no se usa `network_mode: host` sin justificación.

## NFR-18 — Observabilidad y alertas operativas

Provocar deliberadamente:

- PostgreSQL caído;
- Redis caído;
- VPN stale;
- importador con corruptos;
- backend de descargas inaccesible;
- backup fallido.

Comprobar que:

- `/api/health` distingue error crítico de warning;
- el ciclo no se detiene permanentemente;
- el log identifica el componente y el ciclo;
- el usuario ve warnings relevantes en la UI;
- no se reporta `healthy` cuando la base de datos está caída.

## NFR-19 — Prueba de compatibilidad y portabilidad

Ejecutar al menos en:

- Python 3.11 y versión soportada superior;
- arquitectura x86_64 si es CI;
- ARM64 si existe runner o Pi real;
- filesystem con espacios y Unicode;
- directorios de host con permisos no root.

Registrar diferencias. No asumir que una prueba de Docker x86 demuestra rendimiento en Raspberry Pi.

## NFR-20 — Matriz de decisión de release

| NFR | Resultado | Severidad | Bloquea release | Evidencia |
|---|---|---:|---:|---|
| Secretos por defecto | PASS/FAIL | P0 | Sí | logs/config |
| Exposición DB/Redis | PASS/FAIL | P0 | Sí | compose/ports |
| Mass assignment | PASS/FAIL | P0 | Sí | HTTP + BD |
| Traversal/ZIP | PASS/FAIL | P0 | Sí | paths/logs |
| DoS XML/ZIP | PASS/FAIL | P1 | Sí si crash | RSS/timeout |
| Consistencia move/BD | PASS/FAIL | P1 | Sí si pérdida | BD/fs |
| Límite de memoria | PASS/FAIL | P1 | Según hardware | docker stats |
| Reinicio/resiliencia | PASS/FAIL | P1 | Sí | logs/cuentas |
| Segregación/autorización | PASS/FAIL/NA | P1 | Según exposición | mapa rutas |
| Backup/restore | PASS/FAIL | P1 | Sí | BD restaurada |
| XSS/inyección | PASS/FAIL | P0 | Sí | navegador/HTML |
| Dependencias/imágenes | PASS/FAIL/NOT RUN | P1 | Según política | scanner |

## Orden recomendado

1. Secretos, configuración y puertos.
2. Mass assignment y autorización.
3. Traversal, ZIP/XML y XSS.
4. Consistencia de filesystem/BD.
5. Resiliencia de PostgreSQL, Redis e integraciones.
6. Concurrencia, backpressure y capacidad.
7. Backup, restore y disaster recovery.
8. Observabilidad, portabilidad y escaneo de dependencias.

Un `known failure` solo puede mantenerse si está explícitamente aceptado,
tiene propietario, mitigación temporal y fecha de corrección. Nunca debe
contar como PASS.