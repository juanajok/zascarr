#!/usr/bin/env bash
# bootstrap.sh — Arranque completo de la Tebeoteca Digital
# Ejecutar UNA SOLA VEZ desde /mnt/nvme/tebeoteca/
set -euo pipefail

TEBEOTECA_ROOT="/mnt/nvme/tebeoteca"
B='\033[1m'; G='\033[0;32m'; Y='\033[0;33m'; R='\033[0;31m'; N='\033[0m'
info()    { echo -e "${B}→${N} $*"; }
success() { echo -e "${G}✓${N} $*"; }
warn()    { echo -e "${Y}⚠${N}  $*"; }
die()     { echo -e "${R}✗${N} $*" >&2; exit 1; }

echo -e "\n${B}====================================${N}"
echo -e "${B}  Tebeoteca Digital — Bootstrap v1.3${N}"
echo -e "${B}====================================${N}\n"

command -v docker >/dev/null 2>&1 || die "Docker no encontrado."
docker compose version >/dev/null 2>&1 || die "docker compose plugin no encontrado."
command -v python3 >/dev/null 2>&1 || die "Python 3 no encontrado."

info "Creando estructura de directorios..."

# Configs Docker (en NVMe — rendimiento)
mkdir -p "${TEBEOTECA_ROOT}/config/"{postgres,redis}

# Biblioteca (en WDElements — capacidad)
LIBRARY="/media/WDElements/Tebeos"
for dir in "Comics/_Specials" "Comics/_Omnibus" \
           "Manga" "BD" "Tebeos" "Fumetti" "Manhwa" \
           "Graphic Novels" "_Unsorted"; do
    mkdir -p "${LIBRARY}/${dir}"
done

# Descargas
mkdir -p /media/DiscoDuro/downloads/comics 2>/dev/null || true
mkdir -p /media/DiscoDuro/aMule/Incoming   2>/dev/null || true

chown -R 1000:1000 "${TEBEOTECA_ROOT}" "${LIBRARY}" 2>/dev/null || \
    warn "Sin permisos para chown (ejecuta como root si es necesario)"
success "Directorios creados en ${LIBRARY}"

info "Validando .env..."
ENV_FILE="${TEBEOTECA_ROOT}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${TEBEOTECA_ROOT}/secuenciarr/.env.example" "${ENV_FILE}" 2>/dev/null || true
    die ".env no existe. Crea uno en ${ENV_FILE} a partir de .env.example y vuelve a ejecutar."
fi
grep -q "DB_PASSWORD=cambia_esto_ahora" "${ENV_FILE}" && \
    die "DB_PASSWORD tiene el valor por defecto. Cámbialo en ${ENV_FILE}."
success ".env válido"

info "Levantando PostgreSQL y Redis..."
cd "${TEBEOTECA_ROOT}"
docker compose up -d postgres redis

info "Esperando a PostgreSQL..."
MAX=60; ELAPSED=0
until docker compose exec -T postgres pg_isready -U comics_admin -d tebeoteca -q 2>/dev/null; do
    ELAPSED=$((ELAPSED+2))
    [[ $ELAPSED -ge $MAX ]] && die "PostgreSQL no responde tras ${MAX}s.\n  docker compose logs postgres"
    echo -n "."; sleep 2
done
echo ""; success "PostgreSQL listo"

info "Corriendo migraciones Alembic..."
source <(grep -E "^DB_PASSWORD=" "${ENV_FILE}")
export DATABASE_URL="postgresql+asyncpg://comics_admin:${DB_PASSWORD}@127.0.0.1:5432/tebeoteca"
cd "${TEBEOTECA_ROOT}/secuenciarr"
python3 -c "import alembic" 2>/dev/null || pip install --break-system-packages -e ".[dev]" -q
python3 -m alembic upgrade head
success "Migraciones aplicadas"

info "Levantando SecuenciArr..."
cd "${TEBEOTECA_ROOT}"
docker compose up -d secuenciarr

info "Verificando healthcheck..."
MAX=30; ELAPSED=0
until curl -sf http://127.0.0.1:8000/api/health >/dev/null 2>&1; do
    ELAPSED=$((ELAPSED+2))
    [[ $ELAPSED -ge $MAX ]] && warn "SecuenciArr aún no responde. Revisa:\n  docker compose logs secuenciarr" && break
    echo -n "."; sleep 2
done
echo ""

HEALTH=$(curl -sf http://127.0.0.1:8000/api/health 2>/dev/null || echo '{"status":"unreachable"}')
echo -e "\n${B}Estado del sistema:${N}"
echo "$HEALTH" | python3 -m json.tool 2>/dev/null || echo "$HEALTH"

echo -e "\n${B}====================================${N}"
echo -e "${G}${B}  Bootstrap completado${N}"
echo -e "${B}====================================${N}\n"
echo "  SecuenciArr API:  http://127.0.0.1:8000/api/docs"
echo "  Kavita:           http://127.0.0.1:5000  (si está instalado)"
echo "  Prowlarr:         http://127.0.0.1:9696  (si está instalado)"
echo ""
echo "  Logs en tiempo real:"
echo "    docker compose logs -f secuenciarr"
echo ""
curl -sf http://127.0.0.1:5000 >/dev/null 2>&1 || \
    warn "Kavita no detectado en :5000. Instala con:\n  sudo bash ${TEBEOTECA_ROOT}/secuenciarr/scripts/kavita.sh install"
