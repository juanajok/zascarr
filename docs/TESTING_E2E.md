# Plan de testing end-to-end — ZascArr (sandbox Docker)

> Runbook **ejecutable y reproducible** para un sandbox con Docker, previo a la
> Raspberry Pi. Principio rector: **no asumir contratos, descubrirlos del repo**.
> Antes de cada bloque que toca código se lee el fichero real y se extrae el
> nombre/ruta/env exacto; si algo difiere, se corrige el bloque en vez de
> continuar a ciegas.
>
> Convención de resultado: cada fase indica **comando**, **exit esperado**,
> **oráculo** (qué comprobar) y **PASS/FAIL**. Un FAIL se registra y se continúa.

---

## 0. Precondiciones, aislamiento y limpieza

```bash
set -Eeuo pipefail

# ── 0.1 Versiones (registrar al inicio) ──
python3 --version
git --version
docker version --format '{{.Server.Version}}' 2>/dev/null || echo "docker server: no disponible"
docker compose version

# ── 0.2 Aislamiento: proyecto Compose único + raíz efímera ──
ROOT="$(mktemp -d /tmp/zascarr-e2e.XXXXXX)"
export COMPOSE_PROJECT_NAME="zascarr-e2e-$(date +%s)-$$"
APP_PORT="${E2E_APP_PORT:-18000}"        # puerto de la app en el HOST (efímero)

# Fichero override para publicar la app en un puerto libre (postgres/redis se
# quedan en la red interna de Compose; no hace falta publicarlos al host).
cat > "$ROOT/docker-compose.e2e.yml" <<EOF
services:
  zascarr:
    ports:
      - "127.0.0.1:${APP_PORT}:8000"
EOF

# Helper de compose (proyecto aislado + override)
COMPOSE=(docker compose --project-name "$COMPOSE_PROJECT_NAME" \
  -f "$ROOT/zascarr/docker-compose.yml" -f "$ROOT/docker-compose.e2e.yml")
APP_URL="http://127.0.0.1:${APP_PORT}"

# ── 0.3 Cleanup SIEMPRE, incluso con error ──
cleanup() {
  "${COMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$ROOT"
}
trap cleanup EXIT
```

> **Limitar recursos (simular Pi)**: el compose ya declara `deploy.resources.limits.memory`
> (zascarr 512M, redis 128M, postgres 512M). Si el sandbox lo permite, verificar
> que esos límites se aplican con `docker stats --no-stream`. No es obligatorio
> emular la Pi con precisión; solo documentar qué se valida y qué no.

---

## 1. Descubrimiento de contratos (antes de tocar nada)

**Objetivo**: fijar los nombres y rutas reales para que el resto del runbook
no dependa de suposiciones.

```bash
cd "$ROOT"
git clone https://github.com/juanajok/zascarr.git
cd "$ROOT/zascarr"

# 1.1 Identificadores clave (el repo usa snake_case)
grep -nE 'def scan_and_import|class Importer' src/zascarr/services/importer.py
grep -nE 'async_session_factory|def get_db' src/zascarr/database.py
grep -nE 'def check_completions|class Orchestrator' src/zascarr/services/orchestrator.py
grep -nE 'class ReviewService|def assign_to_series|def dismiss' src/zascarr/services/review.py
grep -nE 'start_year|review_dismissed|issue_number|last_searched_at|enrichment_attempted_at|imported_at' src/zascarr/models/__init__.py | head

# 1.2 Rutas HTTP reales
grep -nE '@router\.(get|post)|prefix=' src/zascarr/web/*.py src/zascarr/api/*.py

# 1.3 Contrato legal real (esperado: GET /ui/legal, POST /ui/legal/accept con
#     Form(acepto_1, acepto_2, acepto_3), GET /legal)
grep -nE 'acepto_|ui/legal|/legal|require_legal_acknowledgment' src/zascarr/web/legal.py src/zascarr/services/legal.py

# 1.4 Variables de entorno y rutas de volúmenes reales
grep -nE 'HOST_(LIBRARY|DOWNLOADS|AMULE)' .env.example docker-compose.yml
grep -nE 'context:|\.\./config|/media/(library|downloads|incoming)|/config/covers' docker-compose.yml

# Registrar en el reporte TODO lo anterior (es la "tabla de contratos reales").
```

**Criterio**: existe una tabla de contratos extraída del repo; los bloques
siguientes usan esos nombres exactos, no los de este documento.

---

## 2. Validación estática

```bash
cd "$ROOT/zascarr"

# 2.1 Shell
bash -n bootstrap.sh
bash -n scripts/_comun.sh
bash -n scripts/update.sh
bash -n scripts/rollback.sh
bash -n scripts/backup.sh
bash -n scripts/kavita.sh
bash -n scripts/vpn-state.sh
echo "PASS shell si exit 0"

# 2.2 Compose (combinado, con override)
"${COMPOSE[@]}" config -q && echo "PASS compose config"

# 2.3 Referencias personales filtradas (se excluye la doc histórica)
if grep -RInE 'WDElements|DiscoDuro|mnt/nvme|mnt/tebeoteca|Confiraspa' \
     --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.venv \
     --exclude='BACKLOG.md' --exclude='TESTING_E2E.md' \
     src scripts bootstrap.sh docker-compose.yml .env.example
then
  echo "FAIL: referencia personal encontrada"; exit 1
else
  echo "PASS: sin referencias personales"
fi

# 2.4 Suite unitaria (no fijar un conteo: solo "sin failures/errors")
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" -q
.venv/bin/pytest -q --maxfail=1 | tee "$ROOT/pytest.log"
#  Criterio: exit 0 (el tee propaga el exit de pytest); grep del resumen real:
grep -E 'passed|failed|skipped|error' "$ROOT/pytest.log" || true
```

**Criterio 2.4**: `failed=0`, `error=0`. Los `skipped` se aceptan (solo
`test_title_norm` se salta sin `TEST_DATABASE_URL`); si se quiere rigor,
documentar el motivo de cada skip.

---

## 3. Build de imagen (validar el Dockerfile de verdad)

```bash
cd "$ROOT/zascarr"
"${COMPOSE[@]}" build --no-cache zascarr

# 3.1 El paquete se importa y sus datos no-Python viajan en la imagen
"${COMPOSE[@]}" run --rm --no-deps zascarr python -c 'import zascarr; print(zascarr.__file__)'

# 3.2 Ficheros de datos presentes (plantillas, estáticos, LEGAL.md)
"${COMPOSE[@]}" run --rm --no-deps zascarr sh -c \
  'python -c "from zascarr import LEGAL_MD_PATH" 2>/dev/null || true;
   find / -name dashboard.html -path "*zascarr*" 2>/dev/null;
   find / -name htmx.min.js 2>/dev/null | head'
```

**Criterio**: la imagen construye sin error; `import zascarr` funciona; las
plantillas/estáticos/LEGAL están dentro de la imagen (el `find` devuelve rutas).

---

## 4. Stack vacío desde cero + migraciones

```bash
cd "$ROOT/zascarr"

# 4.1 Partir de cero (sin volúmenes previos)
"${COMPOSE[@]}" down -v --remove-orphans 2>/dev/null || true
rm -rf "$ROOT/config/postgres"; mkdir -p "$ROOT/config/postgres"

"${COMPOSE[@]}" up -d postgres redis
"${COMPOSE[@]}" run --rm zascarr alembic upgrade head     # aplica 0001..0008
"${COMPOSE[@]}" up -d zascarr

# 4.2 Salud por servicio (separar running de healthy)
"${COMPOSE[@]}" ps --format json
"${COMPOSE[@]}" exec -T postgres pg_isready -U comics_admin -d tebeoteca
"${COMPOSE[@]}" exec -T redis redis-cli ping          # → PONG

# 4.3 Estado de migración y esquema
"${COMPOSE[@]}" run --rm zascarr alembic current      # → head
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select version_num from alembic_version;"
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select table_name from information_schema.tables where table_schema='public' order by 1;"
#  Verificar columnas sensibles:
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select column_name from information_schema.columns where table_name in ('series','issues','wishlist','legal_acknowledgments') order by table_name, column_name;"
```

**Criterio**: postgres/redis `healthy`; zascarr `running` y su `/api/health`
responde (ver 4.4). `alembic current == head`. Existen las tablas `series`,
`issues`, `files`, `wishlist`, `import_runs`, `legal_acknowledgments`; y columnas
como `series.title_norm`, `series.enrichment_attempted_at`, `issues.locked_fields`,
`wishlist.download_ref`, `legal_acknowledgments.legal_version`.

### 4.4 Health endpoint y VPN (todos los estados)

```bash
curl -s "$APP_URL/api/health" | python3 -m json.tool
#  Esperado: checks.database == "ok"; transmission/amule == "unreachable"; vpn == "unknown"

# Estados de VPN (contrato en src/zascarr/api/health.py):
VPN_DIR="$ROOT/config/vpn-state"; mkdir -p "$VPN_DIR"

#  a) activo reciente → vpn == "ok"
echo "{\"interface\":\"wg0\",\"vpn_active\":true,\"updated_at_epoch\":$(date +%s)}" > "$VPN_DIR/wg0.json"
curl -s "$APP_URL/api/health" | python3 -c 'import sys,json; print(json.load(sys.stdin)["checks"]["vpn"])'  # ok

#  b) inactivo → warning
echo "{\"interface\":\"wg0\",\"vpn_active\":false,\"updated_at_epoch\":$(date +%s)}" > "$VPN_DIR/wg0.json"
curl -s "$APP_URL/api/health" | python3 -c 'import sys,json; print(json.load(sys.stdin)["checks"]["vpn"])'  # warning

#  c) JSON corrupto → warning
echo "no es json" > "$VPN_DIR/wg0.json"
curl -s "$APP_URL/api/health" | python3 -c 'import sys,json; print(json.load(sys.stdin)["checks"]["vpn"])'  # warning

#  d) ausente → unknown
rm -f "$VPN_DIR/wg0.json"
curl -s "$APP_URL/api/health" | python3 -c 'import sys,json; print(json.load(sys.stdin)["checks"]["vpn"])'  # unknown

#  e) stale (más de 300s) → warning
echo "{\"interface\":\"wg0\",\"vpn_active\":true,\"updated_at_epoch\":$(( $(date +%s) - 400 ))}" > "$VPN_DIR/wg0.json"
curl -s "$APP_URL/api/health" | python3 -c 'import sys,json; print(json.load(sys.stdin)["checks"]["vpn"])'  # warning
```

**Criterio**: la VPN nunca pasa a `error`; un aviso no baja el `status` global.

---

## 5. Puerta legal

```bash
cd "$ROOT/zascarr"

# 5.1 Lectura pública SIN aceptar: todo 200
for p in /ui/ /ui/biblioteca /ui/pendientes /ui/wishlist /ui/legal /legal; do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$APP_URL$p"); echo "$p → $code"
done
#  Criterio: todos 200 (la lectura no está detrás del gate).

# 5.2 Acción de riesgo SIN aceptar: 403
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$APP_URL/api/wishlist" \
  -H 'Content-Type: application/json' -d '{}'
#  Criterio: 403 (legal_acknowledgment_required). Si se quiere, capturar el
#  header HX-Redirect que apunta a /ui/legal.

# 5.3 Aceptar (form-encoded, campos reales acepto_1/2/3)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$APP_URL/ui/legal/accept" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'acepto_1=true&acepto_2=true&acepto_3=true'          # → 303 (redirect)

# 5.4 Tras aceptar, la acción de riesgo ya no es 403 por el gate
#     (puede ser 4xx de validación de body; NO debe ser 403 legal)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$APP_URL/api/wishlist" \
  -H 'Content-Type: application/json' -d '{}'
#  Criterio: != 403 por legal_acknowledgment_required.

# 5.5 La aceptación es global y persistente (sin usuarios)
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select legal_version, accepted_at from legal_acknowledgments;"
```

---

## 6. Fixtures (por Python, no por el endpoint de escritura)

> No se usa `POST /api/series` para sembrar datos (ese endpoint se prueba
> aparte en 14.1, que verifica el rechazo de mass-assignment de M1, ya
> cerrado). Se siembra con la sesión async directamente, igual que hacen
> los tests.

```bash
cd "$ROOT/zascarr"

# 6.1 Series de prueba
"${COMPOSE[@]}" exec -T zascarr python - <<'PY'
import asyncio
from zascarr.database import async_session_factory
from zascarr.models import ComicTradition, Series

async def main():
    async with async_session_factory() as db:
        db.add_all([
            Series(title="Batman", tradition=ComicTradition.AMERICAN, start_year=2011),
            Series(title="Saga",    tradition=ComicTradition.AMERICAN, start_year=2012),
        ])
        await db.commit()

asyncio.run(main())
PY

# 6.2 CBZ de prueba (con imagen JPEG real + ComicInfo.xml). ROOT va por argv.
python3 - "$ROOT" <<'PY'
import io, sys, zipfile
from pathlib import Path
from PIL import Image

root = Path(sys.argv[1])
dl = root / "data" / "downloads" / "comics"
dl.mkdir(parents=True, exist_ok=True)

def jpeg_bytes(color=(200, 30, 30)):
    b = io.BytesIO(); Image.new("RGB", (16, 24), color).save(b, "JPEG"); return b.getvalue()

def make_cbz(name, series, number, year, evil_title=None):
    ci = (f'<?xml version="1.0"?><ComicInfo>'
          f'<Series>{evil_title or series}</Series><Number>{number}</Number>'
          f'<Year>{year}</Year><Publisher>DC</Publisher><PageCount>1</PageCount>'
          f'<LanguageISO>es</LanguageISO><Writer>Autor</Writer></ComicInfo>')
    with zipfile.ZipFile(dl / name, "w") as z:
        z.writestr("ComicInfo.xml", ci)
        z.writestr("page001.jpg", jpeg_bytes())

make_cbz("Batman 001.cbz", "Batman", "1", 2011)
make_cbz("Saga 007.cbz",    "Saga",    "7", 2012)

# CBZ "malicioso": título con '/' en ComicInfo → el destino NUNCA debe escapar
make_cbz("Escape 001.cbz", "Batman", "1", 2011, evil_title="Batman/Superman")

# CBZ sin ComicInfo (irá a _Unsorted)
with zipfile.ZipFile(dl / "zzz-misterioso.cbz", "w") as z:
    z.writestr("page001.jpg", jpeg_bytes())

# CBZ corrupto (zip inválido)
(dl / "corrupto.cbz").write_bytes(b"esto no es un zip")
PY

# Guardar copia de los fixtures ANTES de importar (para las pruebas de dedupe)
mkdir -p "$ROOT/fixtures"
cp "$ROOT/data/downloads/comics/Batman 001.cbz" "$ROOT/fixtures/Batman 001.cbz"
```

---

## 7. Importador (ciclo real + dedupe + saneado)

```bash
cd "$ROOT/zascarr"

# 7.1 Disparar el importador (mismo helper que usa el repo, snake_case)
"${COMPOSE[@]}" exec -T zascarr python - <<'PY'
import asyncio
from zascarr.database import async_session_factory
from zascarr.services.importer import Importer

async def main():
    async with async_session_factory() as db:
        r = await Importer(db).scan_and_import()
        await db.commit()
        print("importados:", r.imported)
        print("duplicados:", r.duplicates)
        print("sin_clasificar:", r.unsorted)
        print("errores:", r.errors)

asyncio.run(main())
PY

# 7.2 Verificar rutas DESDE LA BD (no fijar la ruta de ejemplo)
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select f.file_name, f.file_path from files f order by f.imported_at desc;"

#  Criterio:
#   - "Batman 001.cbz" y "Saga 007.cbz" están importados (no en downloads).
#   - Su file_path está BAJO el library_path montado (ver 1.4), no en downloads/_Unsorted.
#   - "zzz-misterioso.cbz" está en _Unsorted.
#   - "corrupto.cbz" está en errors (no tumba el ciclo).
#   - "Escape 001.cbz" aterriza en una carpeta con título saneado (sin '/') y
#     file_path es relativo a library (is_relative_to).

# 7.3 Deduplicación (el original se conservó en $ROOT/fixtures)
cp "$ROOT/fixtures/Batman 001.cbz" "$ROOT/data/downloads/comics/Batman 001 (copia).cbz"
# re-ejecutar 7.1 → debe aparecer en "duplicados" y NO crear un segundo File:
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select count(*) from files where file_name like 'Batman 001%';"   # sigue siendo 1
```

**Criterio 7.x (saneado adicional, reusando helpers de `tests/test_fs.py`)**:
cubrir `..`, `../fuera`, ruta absoluta, nombre vacío, solo puntos, Unicode/tildes
y longitud >255; y para cada uno assert `dest.resolve().is_relative_to(library.resolve())`.

---

## 8. Revisión manual (pendientes)

```bash
cd "$ROOT/zascarr"

# 8.1 Listar pendientes (debe incluir zzz-misterioso.cbz)
curl -s "$APP_URL/ui/pendientes" | grep -i "zzz-misterioso" && echo "PASS listado"

# 8.2 Obtener file_id y series_id
FILE_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select id from files where file_name='zzz-misterioso.cbz';" )
SERIES_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select id from series where title='Batman';" )

# 8.3 Asignar a una serie (número nuevo → crea Issue con locked_fields)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$APP_URL/ui/pendientes/$FILE_ID/asignar" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "series_id=$SERIES_ID&issue_number=12"          # → 200

# 8.4 Verificar efectos en BD
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select i.issue_number, i.locked_fields, f.file_path from files f left join issues i on i.id=f.issue_id where f.file_name='zzz-misterioso.cbz';"
#  Criterio: el archivo se movió a la biblioteca; file.issue_id está enlazado;
#  el Issue nuevo tiene locked_fields = {series_id, issue_number} (H3) y metadata_source no es 'manual'.

# 8.5 Doble asignación / ignorar / casos
#  - asignar el mismo file otra vez → comportamiento definido (sin duplicar Issue).
#  - ignorar un file → review_dismissed=true y desaparece de /ui/pendientes.
#  - asignar con número vacío → error 4xx claro, sin mover nada.
```

---

## 9. Portadas (cascada, caché, ETag, sin hotlinking)

```bash
cd "$ROOT/zascarr"
SERIES_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select id from series where title='Batman';" )

# 9.1 Portada extraída del CBZ + cabeceras de caché
curl -s -D "$ROOT/cover.headers" -o "$ROOT/cover.jpg" "$APP_URL/ui/series/$SERIES_ID/portada"
grep -i '^content-type:' "$ROOT/cover.headers"     # image/jpeg
grep -i '^cache-control:' "$ROOT/cover.headers"    # private, max-age=86400
grep -i '^etag:' "$ROOT/cover.headers"

# 9.2 Caché en disco
ls -la "$ROOT/config/covers/"                       # <series_id>.jpg presente

# 9.3 304 con If-None-Match
ETAG=$(awk -F': ' 'tolower($1)=="etag"{gsub("\r","");print $2}' "$ROOT/cover.headers")
curl -s -o /dev/null -w '%{http_code}\n' -H "If-None-Match: $ETAG" "$APP_URL/ui/series/$SERIES_ID/portada"
#  Criterio: 304.

# 9.4 Sin hotlinking: el HTML no debe apuntar a cover_url externo
curl -s "$APP_URL/ui/" | grep -Eo 'src="[^"]+' | grep -vi '/ui/series/' || echo "PASS: sin src externo"

# 9.5 Serie sin portada → 404 (el template cae a placeholder CSS)
#  (crear una serie sin archivos y sin cover_url; GET /portada → 404)
```

### 9.6 Mock de servidor externo (prueba `follow_redirects` sin CDN real)

```bash
# Servidor local que devuelve 302 → 200 (regresión del bug de redirecciones)
python3 - "$ROOT" <<'PY' &
import http.server, socketserver, sys
from pathlib import Path
root = Path(sys.argv[1])
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/redirect":
            self.send_response(302); self.send_header("Location", "/img.jpg"); self.end_headers()
        else:
            b = b"\xff\xd8\xff\xe0" + b"0"*64   # JPEG simulado
            self.send_response(200); self.send_header("Content-Type", "image/jpeg"); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
with socketserver.TCPServer(("127.0.0.1", 18081), H) as s:
    s.serve_forever()
PY
MOCK_PID=$!
#  (opcional) apuntar temporalmente una serie a cover_url=http://127.0.0.1:18081/redirect
#  y verificar que la portada se descarga siguiendo el 302.
kill "$MOCK_PID" 2>/dev/null || true
```

---

## 10. Wishlist + orquestador (estados y cooldown)

```bash
cd "$ROOT/zascarr"

# 10.1 Añadir a deseados (form-encoded; requiere legal ya aceptado)
SERIES_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select id from series where title='Saga';" )
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$APP_URL/ui/wishlist/anadir" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "series_id=$SERIES_ID"                        # → 200

# 10.2 Estados y cooldown (fijar timestamps, no esperar horas)
"${COMPOSE[@]}" exec -T zascarr python - <<'PY'
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from zascarr.database import async_session_factory
from zascarr.models import Wishlist

async def main():
    now = datetime.now(timezone.utc)
    async with async_session_factory() as db:
        w = (await db.execute(select(Wishlist))).scalars().first()
        # 1) never searched → debe procesarse
        w.last_searched_at = None
        # 2) searched recientemente → NO debe procesarse (cooldown)
        # w.last_searched_at = now - timedelta(seconds=10)
        # 3) searched hace más del cooldown → debe procesarse
        # w.last_searched_at = now - timedelta(hours=7)
        await db.commit()
asyncio.run(main())
PY

# 10.3 Orquestador sin clientes externos (sin Prowlarr/Transmission/aMule):
#     procesar y verificar que no crashea y que marca last_searched_at.
"${COMPOSE[@]}" exec -T zascarr python - <<'PY'
import asyncio
from zascarr.database import async_session_factory
from zascarr.services.orchestrator import Orchestrator
async def main():
    async with async_session_factory() as db:
        o = Orchestrator(db)
        sent = await o.process_wishlist(limit=10)
        imported = await o.check_completions(limit=10)
        await db.commit()
        print("enviados:", sent, "importados:", imported)
asyncio.run(main())
PY
#  Criterio: sin excepción; sin clientes, "sent" queda 0 y el item no pasa a error.

# 10.4 Cierre del círculo DOWNLOADING → IMPORTED (la pieza clave de D1)
"${COMPOSE[@]}" exec -T zascarr python - <<'PY'
import asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from zascarr.database import async_session_factory
from zascarr.models import File, FileFormat, Issue, Series, Wishlist, WishlistStatus
from zascarr.services.orchestrator import Orchestrator

async def main():
    async with async_session_factory() as db:
        s = (await db.execute(select(Series))).scalars().first()
        i = Issue(series_id=s.id, issue_number="99")
        db.add(i); await db.flush()
        w = Wishlist(issue_id=i.id, status=WishlistStatus.DOWNLOADING)
        db.add(w); await db.flush()
        db.add(File(issue_id=i.id, file_path=f"/media/library/Comics/{s.title}/{s.title} #099.cbz",
                    file_name=f"{s.title} #099.cbz", file_format=FileFormat.CBZ,
                    imported_at=datetime.now(timezone.utc)))
        await db.commit()
        o = Orchestrator(db)
        imported = await o.check_completions(limit=10)
        await db.commit()
        w2 = (await db.execute(select(Wishlist).where(Wishlist.id == w.id))).scalar_one()
        print("importados:", imported, "estado:", w2.status, "downloaded_at:", w2.downloaded_at)
asyncio.run(main())
PY
#  Criterio: Wishlist.status == IMPORTED y downloaded_at no nulo.
```

---

## 11. Backup + restauración

```bash
cd "$ROOT/zascarr"

# 11.1 Volcado
BACKUP_DIR="$ROOT/backups" bash scripts/backup.sh
ls -la "$ROOT/backups"
gunzip -t "$ROOT"/backups/*.sql.gz && echo "PASS: gzip íntegro"

# 11.2 Restauración a una BD TEMPORAL (no tocar la activa)
"${COMPOSE[@]}" exec -T postgres dropdb -U comics_admin --if-exists restore_test 2>/dev/null || true
"${COMPOSE[@]}" exec -T postgres createdb -U comics_admin restore_test
gunzip -c "$ROOT"/backups/*.sql.gz | \
  "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d restore_test >/dev/null
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d restore_test -c \
  "select count(*) from series;"
#  Criterio: el dump restaura y la cuenta de series coincide con la BD activa.

# 11.3 Retención (RETENTION_DAYS)
touch -d "20 days ago" "$ROOT/backups/backup_viejo.sql.gz"
BACKUP_DIR="$ROOT/backups" bash scripts/backup.sh
test ! -f "$ROOT/backups/backup_viejo.sql.gz" && echo "PASS: retención aplicada"
```

> **Nota sobre "disco distinto"**: en `/tmp` el backup está en el mismo
> filesystem que `config/`. `stat -c '%d %n' "$ROOT/config/postgres" "$ROOT/backups"`
> lo confirma. En el sandbox solo se valida la lógica (dump + restore + retención),
> no el requisito físico de disco separado.

---

## 12. Persistencia y reinicio

```bash
cd "$ROOT/zascarr"

# 12.1 Reinicio del contenedor
"${COMPOSE[@]}" restart zascarr
sleep 5
curl -s -o /dev/null -w '%{http_code}\n' "$APP_URL/api/health"    # 200

# 12.2 down/up SIN borrar volúmenes → los datos persisten
"${COMPOSE[@]}" down
"${COMPOSE[@]}" up -d postgres redis zascarr
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "select (select count(*) from series) as series, (select count(*) from files) as files, (select count(*) from legal_acknowledgments) as legal;"
#  Criterio: las cuentas NO bajan; la portada cacheada sigue en $ROOT/config/covers.
```

---

## 13. Look-and-feel (navegador real)

Usar **Playwright** (o similar) contra `$APP_URL`:

```javascript
// 13.1 CSS cargado
const css = await page.locator('link[href*="web.css"]').count();   // >= 1
// 13.2 Estilo aplicado (no solo texto)
const bg = await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor);
// 13.3 Borde de "tinta" y sombra dura en una tarjeta
const card = await page.locator('.metric-card, .series-card').first();
const border = await card.evaluate(el => getComputedStyle(el).borderWidth);   // >= 2px
// 13.4 Foco por teclado: Tab recorre la nav y el foco tiene outline
// 13.5 Responsive 375px: sin scroll horizontal
// 13.6 Tema oscuro (emulate prefers-color-scheme: dark): fondo y texto legibles
// 13.7 Botón "Añadir a deseados": clic → se deshabilita, cambia texto, y recarga sin doble POST
```

**Criterio**: CSS cargado; `backgroundColor` ≈ el token `--paper`; bordes >= 2px;
sin overflow horizontal en móvil; tema oscuro aplica; el botón no permite doble envío.

---

## 14. Casos de error / seguridad / regresión

```bash
cd "$ROOT/zascarr"

# 14.1 Mass-assignment en POST /api/series (deuda M1, cerrada): regresión.
curl -s -o "$ROOT/m1.json" -w '%{http_code}\n' -X POST "$APP_URL/api/series" \
  -H 'Content-Type: application/json' \
  -d '{"title":"M1","id":"11111111-1111-1111-1111-111111111111","metadata_source":"manual","locked_fields":["id"]}'
#  Criterio esperado: 422 (Pydantic con extra="forbid" rechaza id/
#  metadata_source/locked_fields inyectados). Un 201 aquí es una
#  regresión real de M1, no un known failure — FAIL del release.

# 14.2 ZIP con path traversal interno (../../evil.txt) → al importar/leer no
#     escribe fuera del destino.
# 14.3 CBR (sin unrar) → no se extrae portada, no crashea.
# 14.4 CBZ sin imágenes / JPEG corrupto → warning, no crash.
# 14.5 Título Unicode, con espacios, o de >255 bytes → ruta segura (is_relative_to).
# 14.6 Redis caído durante el arranque → la app arranca (degradado) o falla con
#     mensaje claro, sin dejar el stack a medias.
# 14.7 Errores de red/timeouts de integraciones (Prowlarr/Transmission/aMule/
#     Tebeosfera/Comic Vine) → el ciclo no se bloquea, registra error y reintenta
#     según política (un error de red NO debe marcar caché negativa).
```

**Criterio 14.x**: cada caso deja el sistema en estado coherente (no se corrompe
BD ni se escribe fuera de la biblioteca) y no bloquea el ciclo.

---

## 15. Teardown y reporte

```bash
# cleanup automático por trap (0.3); opcional explícito:
"${COMPOSE[@]}" down -v --remove-orphans
```

**Plantilla de reporte**:

| Fase | Resultado | Evidencia / notas |
|---|---|---|
| 0. Aislamiento | PASS/FAIL | … |
| 1. Contratos | PASS/FAIL | tabla de nombres/rutas |
| 2. Estática | PASS/FAIL | pytest.log (failed=0) |
| 3. Build | PASS/FAIL | … |
| 4. Stack/migraciones | PASS/FAIL | alembic current, tablas |
| 5. Legal | PASS/FAIL | 403→303→no-403 |
| 6. Fixtures | PASS/FAIL | … |
| 7. Importer | PASS/FAIL | rutas desde BD |
| 8. Revisión | PASS/FAIL | … |
| 9. Portadas | PASS/FAIL | ETag/304, no-hotlinking |
| 10. Wishlist/orquestador | PASS/FAIL | cooldown, IMPORTED |
| 11. Backup | PASS/FAIL | restore ok |
| 12. Persistencia | PASS/FAIL | cuentas tras restart |
| 13. Look-and-feel | PASS/FAIL | capturas |
| 14. Edge/seguridad | PASS/FAIL | … |
| 16. Update+rollback | PASS/FAIL | destructivo real (dropdb --force, ON_ERROR_STOP, FLUSHDB) |

> Reglas de reporte: no hay "known failures" aceptados en el release; todo
> FAIL (incluido 14.1 si algún día regresa) se acompaña de logs, HTTP status
> y ruta inesperada para poder corregirlo antes de la Pi.

---

## 16. Actualización + rollback (prueba destructiva, layout de producción)

> `update.sh`/`rollback.sh` están pensados para el layout de producción: un
> único proyecto `tebeoteca-arr`, el `.env` en el **padre** del repo y la app en
> `127.0.0.1:8000`. No caben en paralelo con el stack E2E (compartirían los
> puertos 5432/6379/8000), así que esta fase va **después del teardown de la 15**,
> con esos puertos libres. Es la prueba que valida de verdad lo que la
> simulación no puede: `dropdb --force`, `psql -v ON_ERROR_STOP=1` y
> `redis-cli FLUSHDB` contra Docker/PostgreSQL reales.

```bash
cd "$ROOT"

# ── 16.1 TEBEOTECA_ROOT aislado con su propio clon completo y .env ──
UT="$ROOT/update-test"
mkdir -p "$UT"
git clone -q "$ROOT/zascarr" "$UT/zascarr"    # clon local completo (tiene Dockerfile)
cd "$UT/zascarr"
V2="$(git rev-parse HEAD)"
git reset -q --hard HEAD~1                    # dejamos el clon UNA versión por detrás
V1="$(git rev-parse HEAD)"
printf 'DB_PASSWORD=SuperSecretPassword123\n' > "$UT/.env"
export TEBEOTECA_ROOT="$UT" BACKUP_DIR="$UT/backups"
PCOMPOSE=(docker compose -f "$UT/zascarr/docker-compose.yml" --env-file "$UT/.env")

# ── 16.2 Stack en v1: build, migrar y sembrar un dato "antes" ──
"${PCOMPOSE[@]}" build zascarr
"${PCOMPOSE[@]}" up -d postgres redis
"${PCOMPOSE[@]}" run --rm zascarr alembic upgrade head
"${PCOMPOSE[@]}" run --rm zascarr python - <<'PY'
import asyncio
from zascarr.database import async_session_factory
from zascarr.models import ComicTradition, Series
async def main():
    async with async_session_factory() as db:
        db.add(Series(title="serie_antes", tradition=ComicTradition.AMERICAN, start_year=2011))
        await db.commit()
asyncio.run(main())
PY
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select count(*) from series;"        # → 1 (serie_antes)

# ── 16.3 Actualización v1 → v2 ──
bash scripts/update.sh
#  Criterio: exit 0; HEAD == $V2; existe $UT/backups/update_<TS>.sql.gz y
#  `gzip -t` lo da íntegro; refs/zascarr/update/<TS> apunta a $V1; healthcheck ok.
git rev-parse HEAD                       # == $V2
git for-each-ref refs/zascarr/update --format='%(refname) %(objectname)'

# ── 16.4 Sembrar un dato "después" en v2 (no está en el dump de v1) ──
"${PCOMPOSE[@]}" exec -T zascarr python - <<'PY'
import asyncio
from zascarr.database import async_session_factory
from zascarr.models import ComicTradition, Series
async def main():
    async with async_session_factory() as db:
        db.add(Series(title="serie_despues", tradition=ComicTradition.AMERICAN, start_year=2012))
        await db.commit()
asyncio.run(main())
PY
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select count(*) from series;"        # → 2 (serie_antes + serie_despues)

# ── 16.5 Rollback a v1 (destructivo de verdad) ──
bash scripts/rollback.sh --yes
#  Criterio: exit 0; HEAD == $V1; serie_despues HA DESAPARECIDO; serie_antes
#  sigue; el informe dice "esquema de ZascArr completo"; existen
#  $UT/backups/rollback-safety_<TS>.sql.gz y refs/zascarr/rollback-rescue/<TS>.
git rev-parse HEAD                       # == $V1

# ── 16.6 Verificar la BD restaurada ──
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select count(*) from series;"        # → 1
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select title from series;"           # → serie_antes (serie_despues desapareció)
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -tAc \
  "select version_num from alembic_version;"

# ── 16.7 dropdb --force con una conexión concurrente abierta ──
#  El riesgo "database is being accessed by other users": se abre una psql que
#  duerme dentro de una transacción y, con ella viva, se repite el rollback.
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d tebeoteca -c \
  "begin; select pg_sleep(120);" &
PSQL_PID=$!
sleep 2
bash scripts/rollback.sh --yes --forzar   # el código ya está en v1 → hace falta --forzar
kill "$PSQL_PID" 2>/dev/null || true
#  Criterio: exit 0 incluso con la conexión abierta (dropdb --force la corta).
#  Si dropdb fallara, el rollback aborta dejando la BD intacta y su copia de
#  seguridad; registrar el mensaje exacto como evidencia.

# ── 16.8 Limpieza del subproyecto ──
"${PCOMPOSE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
rm -rf "$UT"
```

**Criterio 16.x**: el ciclo completo `update → rollback` revierte **código y
base de datos** a la vez (la serie sembrada en v2 desaparece, la de v1 persiste);
`dropdb --force` corta una conexión concurrente; y el informe final de
`rollback.sh` imprime la revisión de Alembic y el recuento `series/files/wishlist`
de la BD restaurada. Cualquier `exit != 0` se registra con el log
`$UT/backups/rollback_<TS>.log` y la copia de seguridad correspondiente.
