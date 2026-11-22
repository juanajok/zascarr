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

# Fichero override para publicar la app en un puerto libre (postgres se
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
> (zascarr 512M, postgres 512M). Si el sandbox lo permite, verificar
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

"${COMPOSE[@]}" up -d postgres
"${COMPOSE[@]}" run --rm zascarr alembic upgrade head     # aplica 0001..0008
"${COMPOSE[@]}" up -d zascarr

# 4.2 Salud por servicio (separar running de healthy)
"${COMPOSE[@]}" ps --format json
"${COMPOSE[@]}" exec -T postgres pg_isready -U comics_admin -d zascarr

# 4.3 Estado de migración y esquema
"${COMPOSE[@]}" run --rm zascarr alembic current      # → head
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
  "select version_num from alembic_version;"
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
  "select table_name from information_schema.tables where table_schema='public' order by 1;"
#  Verificar columnas sensibles:
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
  "select column_name from information_schema.columns where table_name in ('series','issues','wishlist','legal_acknowledgments') order by table_name, column_name;"
```

**Criterio**: postgres `healthy`; zascarr `running` y su `/api/health`
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

# 5.2 Acción de riesgo SIN aceptar por API: 403 JSON, no-store, HX-Redirect compatible
curl -s -D - -o /dev/null -X POST "$APP_URL/api/wishlist" \
  -H 'Content-Type: application/json' -d '{}' | grep -Ei '^(HTTP/|cache-control|hx-redirect)'
#  Criterio: 403 legal_acknowledgment_required; Cache-Control: no-store; no Location.

# 5.2b Acción gateada por htmx: 403 + HX-Redirect con volver codificado y no-store
curl -s -D - -o /dev/null -X POST "$APP_URL/ui/wishlist/anadir" \
  -H "Origin: $APP_URL" \
  -H 'HX-Request: true' -H 'HX-Current-URL: '"$APP_URL"'/ui/wishlist' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'series_id=00000000-0000-0000-0000-000000000001' \
  | grep -Ei '^(HTTP/|cache-control|hx-redirect)'
#  Criterio: 403; HX-Redirect: /ui/legal?volver=%2Fui%2Fwishlist; no-store.

# 5.2c Formulario normal bajo /ui/ (sin htmx, navegador): 303 al wizard, no JSON 403
curl -s -D - -o /dev/null -X POST "$APP_URL/ui/wishlist/anadir" \
  -H "Origin: $APP_URL" -H 'Accept: text/html' \
  -H 'Referer: '"$APP_URL"'/ui/series/00000000-0000-0000-0000-000000000001' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'series_id=00000000-0000-0000-0000-000000000001' \
  | grep -Ei '^(HTTP/|location|cache-control)'
#  Criterio: 303; Location: /ui/legal?volver=...; no-store.

# 5.3 Aceptación INCOMPLETA primero: no registra, conserva el destino y el aviso es honesto/foco.
#     (Después de aceptar ya no se ve `falta`; por eso va antes que 5.3b.)
curl -s -D - -o /dev/null -X POST "$APP_URL/ui/legal/accept" \
  -H "Origin: $APP_URL" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'acepto_1=true&volver=%2Fui%2Fwishlist' \
  | grep -Ei '^(HTTP/|location|cache-control)'
#  Criterio: 303; Location: /ui/legal?volver=%2Fui%2Fwishlist&falta=1; no-store.
curl -s "$APP_URL/ui/legal?volver=%2Fui%2Fwishlist&falta=1" \
  | grep -E 'Faltan casillas por marcar|role="alert"|tabindex="-1" autofocus|Después volverás a Deseados'
#  Criterio: un aviso warn bajo .subtitle, role=alert, un solo autofocus y el destino nombrado.

# 5.3b Aceptación COMPLETA (después de 5.3): 303 al destino y una fila de acuse
curl -s -D - -o /dev/null -X POST "$APP_URL/ui/legal/accept" \
  -H "Origin: $APP_URL" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'acepto_1=true&acepto_2=true&acepto_3=true&volver=%2Fui%2Fwishlist' \
  | grep -Ei '^(HTTP/|location|cache-control)'
#  Criterio: 303; Location: /ui/wishlist; no-store.

# 5.3c Destino hostil o no canónico: respaldo, nunca 500 ni salida externa
for v in '%2F%2Fevil.example' '%2F%2F%2Fui%2Fwishlist' '%2Fui%2F%25%32%65%25%32%65%2Fapi' \
         '%2Fui%2Fmejoras%3Fpagina%3D%C2%B2' '%2Fui%2Fmejoras%3Fpagina%3D%EF%BC%91%EF%BC%92'; do
  curl -s -D - -o /dev/null -X POST "$APP_URL/ui/legal/accept" \
    -H "Origin: $APP_URL" \
    -H 'Content-Type: application/x-www-form-urlencoded' \
    --data 'acepto_1=true&acepto_2=true&acepto_3=true&volver='"$v" \
    | grep -Ei '^(HTTP/|location)'
done
#  Criterio: 303 a /ui/biblioteca; ningún Location empieza por //; «pagina=²» no da 500.

# 5.3d (re-render htmx con `volver` anidado) NO se ejecuta aquí: en 5.3b/5.3c el acuse ya
#      está registrado y el parcial de seguimiento no pinta el enlace al aviso. Se prueba
#      DESPUÉS de §6, cuando ya hay series reales: ver «6 bis».

# 5.4 Tras aceptar, la acción de riesgo ya no es 403 por el gate
#     (puede ser 4xx de validación de body; NO debe ser 403 legal)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$APP_URL/api/wishlist" \
  -H 'Content-Type: application/json' -d '{}'
#  Criterio: != 403 por legal_acknowledgment_required.

# 5.5 La aceptación es global y persistente (sin usuarios)
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
  "select legal_version, accepted_at from legal_acknowledgments;"
```

---

## 6. Fixtures (por Python, no por el endpoint de escritura)

> No se usa `POST /api/series` para sembrar datos (ese endpoint, hoy obsoleto,
> se prueba aparte en 14.1, que verifica el rechazo de mass-assignment de M1,
> ya cerrado). Se siembra con la sesión async directamente, igual que hacen
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

## 6 bis. Retorno legal con series reales (UATP-01, ex 5.3d)

> Ejecutar **después de §6** (ya hay series). En 5.3b/5.3c el acuse quedó registrado y el
> parcial de seguimiento no pinta el enlace al aviso: aquí se borra el acuse a propósito, se
> comprueba que el enlace con `volver` anidado existe **antes de aceptar** y se restaura el acuse
> para seguir el recorrido. Si algo falla a mitad, repetir 5.3b (aceptación completa) deja el
> acuse como estaba.

```bash
cd "$ROOT/zascarr"

# 6 bis.1 Acuse PENDIENTE y una serie real (la siembra §6)
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
  "delete from legal_acknowledgments;"
SERIES_ID=$("${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select id from series order by title limit 1;" | tr -d '[:space:]')
if [ -z "$SERIES_ID" ]; then
  echo "6 bis NOT RUN: no hay series; ejecutar §6 primero"
  exit 1
fi
echo "SERIES_ID=$SERIES_ID"

# 6 bis.2 Comprobar el enlace ANTES de aceptar (seguimiento bloqueado por el aviso)
RESP=$(curl -s -X POST "$APP_URL/ui/series/$SERIES_ID/seguimiento" \
  -H "Origin: $APP_URL" \
  -H 'HX-Request: true' -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'follow_new_issues=true' \
  --data-urlencode "volver=/ui/biblioteca#serie-$SERIES_ID")
printf '%s\n' "$RESP" | grep -F 'Falta aceptar el aviso legal'
ENLACE_ESPERADO="ui/legal?volver=/ui/series/$SERIES_ID%3Fvolver%3D/ui/biblioteca%2523serie-$SERIES_ID"
if printf '%s' "$RESP" | grep -qF "$ENLACE_ESPERADO"; then
  echo "OK: el enlace conserva el volver anidado de la ficha"
else
  echo "FALLO: no aparece el enlace esperado; ¿se perdió el volver en el re-render?"
  printf '%s\n' "$RESP" | grep -o 'ui/legal?volver=[^"]*' || true
  exit 1
fi
#  Criterio: el parcial de seguimiento bloqueado conserva `volver` anidado y el enlace
#  contiene /ui/series/$SERIES_ID...volver=.../ui/biblioteca...#serie-$SERIES_ID.

# 6 bis.3 Restaurar el acuse para el resto del recorrido (lo dejaba 5.3b)
curl -s -o /dev/null -X POST "$APP_URL/ui/legal/accept" \
  -H "Origin: $APP_URL" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'acepto_1=true&acepto_2=true&acepto_3=true&volver=%2Fui%2Fwishlist'
ACUSES=$("${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select count(*) from legal_acknowledgments;" | tr -d '[:space:]')
test "$ACUSES" -ge 1 && echo "acuse restaurado ($ACUSES fila(s))"
#  Criterio: el acuse vuelve a constar; si no, repetir 5.3b antes de seguir.
```

---

## 6 ter. Retorno y foco de Biblioteca (UATP-02)

> Ejecutar **después de §6** (ya hay series). No hay JavaScript: el foco lo decide
> el HTML (`autofocus`, `tabindex="-1"`). El E2E de navegador real (Chrome/Firefox)
> se marca **NOT RUN** aquí si no se ejecuta; el HTML no demuestra el foco.

```bash
cd "$ROOT/zascarr"

SERIES_ID=$("${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select id from series order by title limit 1;" | tr -d '[:space:]')
test -n "$SERIES_ID" && echo "SERIES_ID=$SERIES_ID"

# 6 ter.1 Tarjeta enfocada (vista tarjetas): un solo autofocus y su href con foco
curl -s "$APP_URL/ui/biblioteca?page=1&foco=$SERIES_ID" > /tmp/bib-uatp02.html
test "$(grep -c autofocus /tmp/bib-uatp02.html)" -eq 1
grep -F '<a class="library-card" id="serie-'"$SERIES_ID"'"' /tmp/bib-uatp02.html
grep -F 'foco%3D'"$SERIES_ID" /tmp/bib-uatp02.html

# 6 ter.2 Vista lista: la fila (no la tarjeta) es la enfocable
curl -s "$APP_URL/ui/biblioteca?page=1&vista=lista&foco=$SERIES_ID" > /tmp/bib-lista.html
grep -F '<tr id="serie-'"$SERIES_ID"'" tabindex="-1" autofocus>' /tmp/bib-lista.html
test "$(grep -c autofocus /tmp/bib-lista.html)" -eq 1
! grep -q 'library-card' /tmp/bib-lista.html
# La tabla recorta: el anillo de la fila tiene que ir por dentro.
grep -A3 '^\.library-lista tr:focus' src/zascarr/static/web.css | grep -F 'outline-offset: -3px'

# 6 ter.3 Objetivo ausente o `foco` inválido: respaldo en #rejilla (200, sin 500/422)
OTRO=00000000-0000-0000-0000-000000000000
curl -s "$APP_URL/ui/biblioteca?page=1&foco=$OTRO" > /tmp/bib-ausente.html
grep -F '<div id="rejilla" tabindex="-1" autofocus' /tmp/bib-ausente.html
test "$(grep -c autofocus /tmp/bib-ausente.html)" -eq 1
curl -s -o /dev/null -w '%{http_code}\n' "$APP_URL/ui/biblioteca?page=1&foco=no-es-uuid"   # 200

# 6 ter.4 `volver` hostil en la ficha: respaldo «← Biblioteca», sin salir del servidor
curl -s "$APP_URL/ui/series/$SERIES_ID?volver=%2F%2F%2Fui%2Fbiblioteca" \
  | grep -F '← Biblioteca'
curl -s "$APP_URL/ui/series/$SERIES_ID?volver=%2Fui%2F%25%32%65%25%32%65%2Fui%2Fbiblioteca" \
  | grep -F '← Biblioteca'

# 6 ter.5 Colección (si existe): el enlace de su tarjeta lleva estado, no serie_ids
CID=$("${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select id from collections order by name limit 1;" | tr -d '[:space:]')
if [ -n "$CID" ]; then
  curl -s "$APP_URL/ui/colecciones/$CID?q=flash&tradicion=manga&pagina=1&vista=tarjetas" \
    | grep -o '/ui/series/[^" ]*volver=[^" ]*' | head -1
  # Criterio: el volver decodificado es /ui/colecciones/$CID?q=flash&tradicion=manga&pagina=1&vista=tarjetas
else
  echo "6 ter.5 NOT RUN: no hay colecciones (crear una desde /ui/colecciones)"
fi
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
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
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
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
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
FILE_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select id from files where file_name='zzz-misterioso.cbz';" )
SERIES_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select id from series where title='Batman';" )

# 8.3 Asignar a una serie (número nuevo → crea Issue con locked_fields)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$APP_URL/ui/pendientes/$FILE_ID/asignar" \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data "series_id=$SERIES_ID&issue_number=12"          # → 200

# 8.4 Verificar efectos en BD
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
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
SERIES_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
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
SERIES_ID=$( "${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
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
"${COMPOSE[@]}" up -d postgres zascarr
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
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

### 13.8 UATP-03 · asa, foco y reapertura del lector

> Requiere una serie con un número y un CBZ de ≥3 páginas. Ejecutar en Chrome estable
> (registrar versión) a 320×568, 390×844 y 568×320. Sin navegador, **NOT RUN**; el HTML
> no acredita el foco real.

```text
1. Abrir /ui/leer/<file_id> en modo pantalla. Con la barra oculta:
   #lector-asa visible, getBoundingClientRect() >= 44x44, aria-label/aria-controls.
   activeElement === body y ningún :focus-visible dentro de .lector-escena.
2. Tocar el asa: data-chrome="", asa oculta, foco en «Volver al número»; página,
   imagen, modo y zoom sin cambios; sin POST /progreso ni /sentido.
2b. Con ratón, mover x=500 y=300→90→22 sin revelar: el asa sigue visible; el clic
   en el asa revela la barra y enfoca «Volver al número».
3. Tocar la franja superior (<=44 px) con la barra oculta: revela y NO cambia de página.
4. Tab desde body: entra en la barra y la revela; Tab desde el último enfocable vuelve
   al primero; Shift+Tab al revés; el foco no sale de .lector-escena. Con #fin abierto y
   foco en #fin-titulo, Tab va al primer control del fin, sin revelar/tapar con la barra.
5. Opciones: abrir con toque/Enter; tocar título/leyenda/párrafo no cierra ni manda el
   foco a main; «Cerrar» y Escape cierran, foco al disparador, aria-expanded=false,
   página/modo/imagen intactos.
6. «Volver al número» dentro del viewport, >=44 px de alto y scrollWidth <= innerWidth.
7. Reabrir: avanzar a N, volver al número y abrir: src /pagina/N y contador N/M;
   con progreso 99/3 se sirve 3.
8. RTL: sentido RTL, toque izquierdo avanza y derecho retrocede; etiquetas de acción;
   pareja doble espejada.
9. Regresión: pasar página por toque/deslizamiento no muestra la barra; fin y «Quedarme» OK.
```

**Evidencia:** `docs/design/uatp03/resultado-chrome.md` con SHA, versión de Chrome,
viewport, PASS/FAIL/NOT RUN por fila y capturas. Sin esa ejecución AC-09 queda NOT RUN.

### 13.9 UATP-05 · cerrar la vista previa del número sin mover el foco

> Requiere una serie con varios números con archivo (ficha: chips de «Números» y lista de
> «Archivos por número»), una lista de Biblioteca y una colección con ≥3 series. Ejecutar en
> Chrome estable (registrar versión) a 1440×900, 1024×768 (o zoom 125 %), 720×900 (zoom 200 % de
> 1440) y 390×844 táctil emulado. Sin navegador, **NOT RUN**; el HTML no acredita foco, hover ni
> clic reales. Contrato y CSS: `docs/design/uatp05-previa-teclado.md` (§3–§8).

```text
1. Teclado, 1440: Tab al chip de un número; esperar la tarjeta; Escape.
   El hueco queda vacío, activeElement sigue en el mismo enlace, su anillo :focus-visible
   se ve; no hay navegación ni POST. Repetir en la fija (enlace y «Ver portada»).
2. Siguiente control: con el puntero parado en el chip A y el foco en B (Tab), solo se pinta
   la previa de B; el rectángulo de B (texto y anillo) no lo tapa ninguna tarjeta y
   elementFromPoint en su centro devuelve el chip.
3. Puntero, 1440: hover en un chip; mover despacio hasta la tarjeta cruzando el hueco de 8 px
   (no parpadea ni se cierra), recorrerla sin timeout y ver la flecha; al salir, se oculta.
4. Clic que no atraviesa: en Colecciones, clic sobre la previa fija que tapa «Quitar de la
   colección»: descarta la previa y NO lanza el POST de baja ni navega.
5. Enter nativo: con la previa abierta, Enter en el chip navega a la ficha con el href, sin
   petición htmx ni trampa de foco; Tab/Shift+Tab siguen su orden.
6. Variante fija: en Biblioteca (vista lista) y Colecciones, pasar el ratón por el chip NO
   abre la tarjeta; abre con foco o con «Ver portada» (44 px, visible también con ratón);
   Escape/clic la apartan y dejan libre el control de debajo.
7. Red lenta: CDP Network.emulateNetworkConditions lento (o un CBR); con la petición de
   apertura en vuelo, Escape; la tarjeta no reaparece al terminar la carga. La ventana de
   150 ms previa al arranque es límite declarado (spec §3.4), no se exige.
8. reduced-motion (emulado): abrir, recorrer y Escape sin animación y con el mismo comportamiento.
9. 1024×768 / zoom 125 %: repetir 1–3 sin scroll horizontal y con la tarjeta dentro del
   viewport. A 720×900 la previa anclada no se sirve: registrar el límite de spec §8 y
   comprobar que foco/texto/Enter siguen intactos y que la fija con botón abre y se descarta.
10. Táctil emulado 390×844: «Ver portada» y toque en la tarjeta abren/cierran sin scroll
   horizontal; la anclada sigue oculta (límite declarado).
```

**Evidencia:** `docs/design/uatp05/resultado-chrome.md` con SHA, versión de Chrome, fecha,
viewport, PASS/FAIL/NOT RUN por fila y capturas de abierta, descartada y siguiente control. Sin
esa ejecución AC-09 queda NOT RUN. Una prueba de humo headless sobre el marcado del contrato no
sustituye a esta matriz.
### 13.9 UATP-04 · ediciones homónimas en Deseados

> Fixture: dos series «Flash», 1987 y 2011, en Deseados. Requiere navegador real; sin él,
> **NOT RUN** (el HTML no sustituye la comprobación visual ni la de lector de pantalla).

```text
1. /ui/wishlist muestra «Flash (1987)» y «Flash (2011)» (reference_name), no solo «Flash».
2. Cada fila enlaza a /ui/series/<id>?volver=%2Fui%2Fwishlist; recargar conserva hrefs y textos.
3. Nombres accesibles distintos por fila: Seleccionar/Reintentar/Buscar/Cancelar/Marcar/Quitar
   y Progreso incluyen la referencia.
4. #resultados-wishlist anuncia resultados y «Sin coincidencias.» (aria-live=polite, sin role extra).
5. Selector: cada «Añadir a deseados» incluye su referencia; tras añadir dice «Añadido: …» y no
   se confunde con el otro resultado.
6. Abrir ficha desde una fila → «← Volver a Deseados» → /ui/wishlist.
7. 320×568 y 390×844: sin scroll horizontal; referencia completa (sin ellipsis), enlace ≥24 px,
   chip/estado y motivo legibles.
8. Teclado: enlace de fila alcanzable con Tab; sin cambios de foco inesperados.
```

**Criterio:** PASS solo si se ejecutó en Chrome (registrar versión y viewports). Lector de
pantalla real, Safari/iOS y dispositivo físico: **NOT RUN**.

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
#  `POST /api/series` está OBSOLETO (I3 de #114): sigue funcionando igual, pero no
#  ofrece las garantías del alta por token y se retirará. Cuando desaparezca, este
#  caso se sustituye por 14.1b, que comprueba el mismo rechazo sobre PATCH.

# 14.1b Mismo rechazo sobre PATCH (misma lista de campos internos; persiste tras
#       retirar POST /api/series). Requiere SERIES_ID (ver 8.2).
curl -s -o "$ROOT/m1b.json" -w '%{http_code}\n' -X PATCH "$APP_URL/api/series/$SERIES_ID" \
  -H 'Content-Type: application/json' \
  -d '{"id":"11111111-1111-1111-1111-111111111111","metadata_source":"manual","locked_fields":["id"]}'
#  Criterio esperado: 422 (SeriesUpdate también es extra="forbid"), y la serie no cambia.

# 14.2 ZIP con path traversal interno (../../evil.txt) → al importar/leer no
#     escribe fuera del destino.
# 14.3 CBR (sin unrar) → no se extrae portada, no crashea.
# 14.4 CBZ sin imágenes / JPEG corrupto → warning, no crash.
# 14.5 Título Unicode, con espacios, o de >255 bytes → ruta segura (is_relative_to).
# 14.6 (Redis retirado: ADR 0011; ya no hay dependencia que simular.)
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
> único proyecto `zascarr`, el `.env` en el **padre** del repo y la app en
> `127.0.0.1:8000`. No caben en paralelo con el stack E2E (compartirían los
> puertos 5432/6379/8000), así que esta fase va **después del teardown de la 15**,
> con esos puertos libres. Es la prueba que valida de verdad lo que la
> simulación no puede: `dropdb --force` y `psql -v ON_ERROR_STOP=1`
> contra Docker/PostgreSQL reales.

```bash
cd "$ROOT"

# ── 16.1 ZASCARR_ROOT aislado con su propio clon completo y .env ──
UT="$ROOT/update-test"
mkdir -p "$UT"
git clone -q "$ROOT/zascarr" "$UT/zascarr"    # clon local completo (tiene Dockerfile)
cd "$UT/zascarr"
V2="$(git rev-parse HEAD)"
git reset -q --hard HEAD~1                    # dejamos el clon UNA versión por detrás
V1="$(git rev-parse HEAD)"
# contraseña propia por ensayo: Compose rechaza las de ejemplo (ADR 0012); no se imprime
(umask 077; printf 'DB_PASSWORD=%s\n' "$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')" > "$UT/.env")
export ZASCARR_ROOT="$UT" BACKUP_DIR="$UT/backups"
PCOMPOSE=(docker compose -f "$UT/zascarr/docker-compose.yml" --env-file "$UT/.env")

# ── 16.2 Stack en v1: build, migrar y sembrar un dato "antes" ──
"${PCOMPOSE[@]}" build zascarr
"${PCOMPOSE[@]}" up -d postgres
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
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
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
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select count(*) from series;"        # → 2 (serie_antes + serie_despues)

# ── 16.5 Rollback a v1 (destructivo de verdad) ──
bash scripts/rollback.sh --yes
#  Criterio: exit 0; HEAD == $V1; serie_despues HA DESAPARECIDO; serie_antes
#  sigue; el informe dice "esquema de ZascArr completo"; existen
#  $UT/backups/rollback-safety_<TS>.sql.gz y refs/zascarr/rollback-rescue/<TS>.
git rev-parse HEAD                       # == $V1

# ── 16.6 Verificar la BD restaurada ──
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select count(*) from series;"        # → 1
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select title from series;"           # → serie_antes (serie_despues desapareció)
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select version_num from alembic_version;"

# ── 16.7 dropdb --force con una conexión concurrente abierta ──
#  El riesgo "database is being accessed by other users": se abre una psql que
#  duerme dentro de una transacción y, con ella viva, se repite el rollback.
"${PCOMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -c \
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

---

## 17. Recuperación UATP-06/07 (A6): copia de archivos manual y reapertura

> **Decisión D-1: la copia de archivos es un paso manual documentado, NO una función de ZascArr.**
> `backup.sh` sigue copiando solo PostgreSQL y **no** se añade herramienta de copia/restauración de
> archivos ni de portadas (el contenedor es de solo lectura para la app y la biblioteca puede ser de
> cientos de GB). Lo que se acredita aquí es el procedimiento del host y su evidencia en
> `docs/uat/A6/resultado.md` y `docs/uat/A6/evidencia/resultado.txt` (D-4), saneada según §7.6 de
> `docs/design/uatp06-07-recuperacion.md`: **sin rutas, hostnames, IPs, usuarios, nombres reales ni
> secretos**.
>
> Este bloque se ejecuta en **E-A6**, una instalación aislada de la candidata (proyecto Compose,
> puerto y volúmenes distintos), con `auth_mode=password`. La instalación real no se toca
> (`R-11` de la spec). Si el proyecto no se llama `zascarr`, exporta
> `ZASCARR_PRUEBAS=1 PROYECTO_PRODUCCION=<nombre>` (FR-17.f de BL-OPS2).

### 17.1 Lo que ya está en la candidata (comprobación previa)

| Pieza | Dónde | Comprobación |
|---|---|---|
| `version_de_la_copia = {head, build_sha, app_version, alembic}` en el manifiesto | `scripts/_comun.sh::escribir_manifiesto` | `jq .version_de_la_copia "$BACKUP_DIR"/MANIFIESTO-backup_<TS>.json`; `null` = «no consta», nunca se infiere |
| `intento`, `comprobacion`, `copia_version` en `ops-restaurar.json` | `scripts/restaurar_datos.sh::estado_restaurar` | `jq '{intento, comprobacion, copia_version}' "$BACKUP_STATUS_DIR/ops-restaurar.json"` |
| Registro por intento `ops-restaurar-intentos.jsonl` (máx. 20, `0644`) | `scripts/restaurar_datos.sh::registrar_intento_jsonl` | `tail -n 1 "$BACKUP_STATUS_DIR/ops-restaurar-intentos.jsonl"` |
| Preflight con tabla `issues` (D-6/FR-17(d)) | `scripts/restaurar_datos.sh` (bucle de tablas) | un dump sin `issues` se rechaza antes de todo contenedor |
| FR-17(d): relee HEAD/árbol al final de `--produccion` | `scripts/restaurar_datos.sh::ejecutar_produccion` (paso 9 bis) | si el código cambió, `fallida`/`unexpected`/`base_en_su_sitio:true` y no se declara terminada |

```bash
cd "$ROOT/zascarr"
bash -n scripts/_comun.sh && bash -n scripts/restaurar_datos.sh
pytest -q tests/test_restaurar_produccion.py tests/test_backup_script.py \
  tests/test_version_copia.py tests/test_restaurar_datos.py tests/test_restauracion_estado.py
#  Criterio: exit 0 para T-06-01…T-06-05 y T-07-01…T-07-03. T-07-05 (A6 real) queda NOT RUN hasta ejecutar candidata/copia/browser.
```

### 17.2 Semilla y copia buena B0

1. Serie, número y archivo testigo `ARCHIVO-A` (CBZ multipágina determinista) con UUID fijos.
2. Abrir el lector de la candidata, avanzar a la página **P = 3** y esperar el `POST`
   `/ui/leer/<file_id>/progreso` con `pagina=3` (204). La fila `reading_progress` la escribe el
   lector real, no SQL a mano.
3. Parar la app y ejecutar `backup.sh` (sin offsite puede terminar con `offsite_mount_missing`:
   B0 y su manifiesto ya están escritos; registrar el motivo y **no** invalidar B0).
4. Duplicar B0 con otro `<TS>` para la matriz negativa y mutar **solo el duplicado**; regenerar
   `copias.json` con `escribir_copias_json`. **B0 no se muta**.

```bash
"${COMPOSE[@]}" stop zascarr
sudo -E bash scripts/backup.sh || true
test -s "$BACKUP_DIR"/backup_<TS>.sql.gz && test -s "$BACKUP_DIR"/MANIFIESTO-backup_<TS>.json
jq .version_de_la_copia "$BACKUP_DIR"/MANIFIESTO-backup_<TS>.json
"${COMPOSE[@]}" start zascarr
```

### 17.3 Matriz negativa de producción (N-01…N-04)

Cada fila se ejecuta por el **mismo camino de producción** (`restaurar_datos.sh --produccion
--copia <TS>` o la acción «Restaurar…»). Antes y después se toma la instantánea canónica
(HEAD/árbol, `alembic_version`, recuentos, testigo, `/api/health`, SHA-256 de B0 y de su
manifiesto, `docker inspect` de `zascarr`/`postgres`).

| ID | Mutación de la copia | `error` | `comprobacion` | `base_en_su_sitio` | Eventos Docker |
|---|---|---|---|---|---|
| N-01 | manifiesto con `sha256` alterado, dump intacto | `copia_no_valida` | `sha256_copia` | `true` | 0 |
| N-02 | `.sql.gz` truncado y manifiesto/sidecar recalculados | `copia_no_valida` | `gzip_cabecera` | `true` | 0 |
| N-03a | dump sin `COPY public.series`, recomprimido y recalculado | `copia_no_valida` | `tablas_dump` | `true` | 0 |
| N-03b | dump sin `COPY public.issues`, recomprimido y recalculado | `copia_no_valida` | `tablas_dump` | `true` | 0 |
| N-04 | B0 válida (control positivo) | `null` | `null` | `true` | los del flujo aprobado |

```bash
# Eventos de contenedor en segundo plano: al final del intento, 0 líneas.
docker events --since <inicio> --until <fin> \
  --filter event=create --filter event=start --filter event=stop --filter event=kill \
  --filter event=die --filter event=destroy --filter event=exec_create --filter event=exec_start \
  --filter label=com.docker.compose.project=<PROYECTO> > "$ROOT/eventos.txt"

sudo -E bash scripts/restaurar_datos.sh --produccion --copia <TS>
cat "$BACKUP_STATUS_DIR/ops-restaurar.json"
tail -n 1 "$BACKUP_STATUS_DIR/ops-restaurar-intentos.jsonl"
wc -l "$ROOT/eventos.txt"          # 0 en N-01…N-03b
```

Criterio de cada fila negativa: `rc != 0`; estado `fallida` con el `error`/`comprobacion` de la
tabla; `base_en_su_sitio:true`; **cero eventos de contenedor** y ninguna sentencia de escritura;
B0 y su manifiesto con el mismo SHA-256; `copias.json` sigue ofreciendo B0; la persona ve
«Esa copia está dañada, así que no se ha usado. Elige otra.» y **no** el aviso de base fuera de
su sitio; dos intentos tienen `intento` distinto y el anterior sigue en el `.jsonl`.

### 17.4 Copia de archivos manual (D-1)

**Solo raíces de biblioteca.** Fuera: portadas (`covers/`), `.env`, credenciales, configuración
del host, volumen de PostgreSQL y los dumps de copia.

1. **Raíces.** Listar `library_roots` con `enabled` (`path`, `host_path`, `is_default`). Si
   `host_path` está vacío y es la raíz por defecto, usar `HOST_LIBRARY_DIR`; si sigue vacío,
   **abortar** (no se inventa una ruta: se declara en Ajustes). Rechazar raíces anidadas, `/`, la
   home del usuario, puntos de montaje de Docker/VPN y raíces no montadas o no legibles. En A6 se
   etiquetan `R1`, `R2`… (la ruta real solo en la consola privada del operador).
2. **Destino.** Vacío (`find "$DEST" -mindepth 1 -maxdepth 1 -print -quit` sin salida), en otro
   sistema de archivos (`stat -c %d` distinto de cada origen), montado y escribible, y **no** dentro
   de un origen ni conteniéndolo. Sin `--delete`. Se monta en el entorno aislado en la **misma ruta
   de contenedor** que tenía la instalación (`files.file_path` guarda rutas del contenedor).
3. **Orden.** Copiar archivos → restaurar catálogo → arrancar/verificar. La app está parada
   (PostgreSQL sigue en marcha) durante la copia y la restauración; si se restaura antes de copiar,
   el importador/auditoría pueden ver la biblioteca vacía (R-7 de BL-OPS2).
4. **Copia.** `rsync -aHAX --numeric-ids` (o `-aH` si el FS no soporta ACL/xattr), sin seguir
   enlaces (`-l`), con `--info=progress2`. Enlaces simbólicos como enlaces y hardlinks preservados.

```bash
# Espacio suficiente para el inventario + 10 % (du -sb y df -B1), y destino vacío y distinto.
findmnt -T "$DEST"
test -z "$(find "$DEST" -mindepth 1 -maxdepth 1 -print -quit)"
stat -c '%d %n' "$RAIZ" "$DEST"                       # %d distinto
rsync -aHAX --numeric-ids --info=progress2 "$RAIZ"/ "$DEST"/
```

Verificación (obligatoria) antes y después, con el hash final idéntico:

```bash
# Mtime (con nanosegundos) + tamaño de todos los ficheros de la raíz:
find "$RAIZ" -type f -printf '%P\0%T@\0%s\0' | sort -z | sha256sum
# Inventario: nº de ficheros y bytes; huella testigo del CBZ (y de la página P).
stat -c '%y' "$ARCHIVO_A"                              # con nanosegundos
sha256sum "$ARCHIVO_A"
# Opcional y costoso: sha256 de TODA la raíz; si no se ejecuta, NOT RUN motivo=coste.
```

Criterio: mtime/inventario y SHA-256 testigo idénticos; `files.sha256_hash` del testigo coincide
con el archivo copiado; el FS destino conserva nanosegundos (exFAT/NTFS = FAIL de F-02, no
«aceptable»).

### 17.5 Reapertura en la página guardada (R-01…R-05)

Con el catálogo restaurado en el entorno aislado y los archivos en su ruta de contenedor:

```bash
curl -fsS -b <COOKIE> "$APP_URL/ui/series/<SERIE>/numero/<NUMERO>" | grep 'Continuar (pág. 3)'
curl -fsS -b <COOKIE> "$APP_URL/ui/leer/<FILE_ID>"                 | grep 'data-pagina="3"'
curl -fsS -b <COOKIE> "$APP_URL/ui/leer/<FILE_ID>/pagina/3"        | sha256sum
"${COMPOSE[@]}" exec -T postgres psql -U comics_admin -d zascarr -tAc \
  "select current_page, status from reading_progress where issue_id = '<NUMERO>';"
```

Criterio: la ficha ofrece «Continuar (pág. P)»; el lector abre en `data-pagina=P`; la página P
servida tiene el SHA-256 testigo; `files.file_path` existe con el `sha256_hash` correcto; y las
relaciones y el progreso (`reading_progress.current_page=P`, `file_id`, estado) coinciden sin
huérfanos. Si R-01/R-02/R-03 fallan, UATP-07 no se acredita aunque los recuentos cuadren.

### 17.6 A6: evidencia y cierre

- `docs/uat/A6/resultado.md`: cabecera (historias, fecha ISO, entorno `E-A6`, candidata T1/C con
  `tag_commit`/`build_sha`/`app_version`/`alembic`, tag antiguo `v1.15.1`), tabla de comprobaciones
  con `ID`/`Esperado`/`Obtenido`/`PASS|FAIL|NOT RUN`/evidencia, instantánea antes/después, versión,
  copia de archivos, reapertura y pendientes.
- `docs/uat/A6/evidencia/resultado.txt`: una línea `CHECK <ID> <PASS|FAIL|NOT RUN> [clave=valor …]`
  por comprobación, comandos exactos y salida saneada.
- **Versión declarada:** `tag_commit == head == build_sha` y `app_version` coincidente con
  `pyproject.toml`/`/api/health`; si falta `build_sha` se dice «la identidad de la imagen no
  consta» y V-01 es FAIL, no PASS parcial. **Nunca** se declara la copia solo como «1.15.1».
- **Cierre:** `PASS` global solo si todas las comprobaciones obligatorias están en PASS y el saneado
  no encuentra secretos. `NOT RUN` en una obligatoria impide declarar cumplida la historia; no se
  convierte en PASS por «lo demás funciona».

```bash
grep -nE 'DB_PASSWORD|PASSWORD=|SECRET|TOKEN|api[_-]?key|auth_password|webhook|/home/|/mnt/|/media/|([0-9]{1,3}\.){3}[0-9]{1,3}' \
  docs/uat/A6/resultado.md docs/uat/A6/evidencia/resultado.txt || true
#  Criterio: sin coincidencias (A-02); si hay alguna, se redacta antes de publicar el fichero.
```

> **Estado de esta rama:** el código, los tests y este runbook están entregados. La ejecución real
> de A6 (E-A6, Pi/navegador, `docker events`, copia de archivos en disco secundario) queda
> **NOT RUN** hasta que QA/PO la ejecuten sobre la candidata identificada; este documento no
> declara cumplidas UATP-06 ni UATP-07.
