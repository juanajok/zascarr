#!/usr/bin/env bash
# Base de datos y contenedor efímeros, sin puertos publicados ni volúmenes del host.
set -euo pipefail

imagen="${1:?Indica la imagen de ZascArr}"
red="zascarr-ci-$$"
db="${red}-db"
app="${red}-app"
clave='prueba@local%:/#?'

docker network create "$red" >/dev/null
limpiar() {
    docker rm -f "$app" "$db" >/dev/null 2>&1 || true
    docker network rm "$red" >/dev/null
}
trap limpiar EXIT

esperar() {
    local intento
    for ((intento=0; intento<30; intento++)); do
        if "$@" >/dev/null 2>&1; then
            return
        fi
        sleep 1
    done
    printf 'No se cumplió la condición: %s\n' "$*" >&2
    docker logs "$app" >&2 || true
    return 1
}

docker run -d --name "$db" --network "$red" --network-alias postgres \
    -e POSTGRES_USER=comics_admin -e POSTGRES_DB=zascarr -e "POSTGRES_PASSWORD=$clave" \
    postgres:15-alpine >/dev/null
esperar docker exec "$db" pg_isready -h 127.0.0.1 -U comics_admin -d zascarr

docker run -d --name "$app" --network "$red" --security-opt no-new-privileges:true \
    --pids-limit 256 -e "ZASCARR_DB_PASSWORD=$clave" "$imagen" >/dev/null
esperar docker exec "$app" python -c '
import httpx
base = "http://127.0.0.1:8000"
assert httpx.get(base + "/api/health").json()["checks"]["database"] == "migration_required"
assert httpx.get(base + "/api/series").status_code == 503
'

docker exec -e "ZASCARR_DB_PASSWORD=$clave" "$app" alembic upgrade head
docker exec -e 'DATABASE_URL=postgresql+asyncpg://comics_admin:prueba%40local%25%3A%2F%23%3F@postgres:5432/zascarr' \
    "$app" alembic current
esperar docker exec "$app" python -c '
import httpx
base = "http://127.0.0.1:8000"
assert httpx.get(base + "/api/health").json()["checks"]["database"] == "ok"
httpx.get(base + "/api/series", follow_redirects=True).raise_for_status()
'
registro="$(docker logs "$app" 2>&1)"
test "$(grep -c 'zascarr.db_recuperada' <<< "$registro")" = 1
if grep -Fq -- "$clave" <<< "$registro"; then
    echo "La contraseña de prueba apareció en los registros" >&2
    exit 1
fi
test "$(docker inspect "$app" --format '{{.RestartCount}}')" = 0
