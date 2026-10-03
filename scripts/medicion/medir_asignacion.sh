#!/usr/bin/env bash
# Mide el coste del contrato de asignación recuperable (ADR 0006) DESDE EL CONTENEDOR, con ficheros
# sintéticos y una base de datos efímera. Herramienta de desarrollo.
#
#   medir_asignacion.sh --dir /ruta/de/ensayo [--dir /otra/ruta] [--salida informe.json]
#                       [--imagen IMAGEN] [--usuario UID:GID] [--tamanos 10,50,100,200]
#                       [--archivos 5] [--mb-extremo 100] --confirmo
#
# Qué toca, y NADA más:
#   - SOLO escribe dentro de cada `--dir` (una subcarpeta `zascarr_medicion_*` que borra al terminar).
#     Cada `--dir` debe EXISTIR ya, ser una ruta absoluta y real (no un enlace simbólico) y poder
#     escribirse. NO se crea ninguna carpeta, y NO se asume ninguna ruta de la biblioteca ni del NAS.
#   - Levanta una Postgres PROPIA (contenedor `zascarr-medicion-pg-*`, red propia `zascarr-medicion-*`,
#     datos en tmpfs, sin publicar ningún puerto) y la borra al terminar. No toca ningún contenedor,
#     red ni volumen existentes.
#   - Los ficheros son sintéticos (aleatorios). No lee ni modifica ninguna biblioteca.
#
# Sin `--confirmo` solo enseña el plan y sale sin hacer nada.
set -euo pipefail

AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "${AQUI}/../.." && pwd)"
DIRS=(); SALIDA=""; IMAGEN=""; USUARIO="$(id -u):$(id -g)"; TAMANOS="10,50,100,200"; ARCHIVOS="5"; MB_EXTREMO="100"; CONFIRMO=0

die() { echo "medir_asignacion.sh: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dir) [[ $# -ge 2 ]] || die "--dir necesita una ruta"; DIRS+=("$2"); shift 2 ;;
        --salida) SALIDA="$2"; shift 2 ;;
        --imagen) IMAGEN="$2"; shift 2 ;;
        --usuario) USUARIO="$2"; shift 2 ;;
        --tamanos) TAMANOS="$2"; shift 2 ;;
        --archivos) ARCHIVOS="$2"; shift 2 ;;
        --mb-extremo) MB_EXTREMO="$2"; shift 2 ;;
        --confirmo) CONFIRMO=1; shift ;;
        -h|--help) sed -n '2,22p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) die "argumento desconocido: $1" ;;
    esac
done

[[ ${#DIRS[@]} -gt 0 ]] || die "indica al menos una carpeta de ensayo con --dir (existente, nueva para este fin)."
[[ "${ARCHIVOS}" =~ ^[0-9]+$ && "${MB_EXTREMO}" =~ ^[0-9]+$ && "${TAMANOS}" =~ ^[0-9]+(,[0-9]+)*$ ]] \
    || die "--archivos, --mb-extremo y --tamanos deben ser números."

# Validación ANTES de tocar nada, incluida la existencia de Docker.
for d in "${DIRS[@]}"; do
    [[ "${d}" = /* ]] || die "${d}: la ruta debe ser absoluta."
    [[ "${d}" != "/" ]] || die "no se admite la raíz."
    [[ -e "${d}" ]] || die "${d} no existe. No creo carpetas: indica una carpeta de ensayo que ya exista."
    [[ -d "${d}" ]] || die "${d} no es una carpeta."
    [[ "$(realpath -m -s "${d}")" == "$(realpath -m "${d}")" ]] \
        || die "${d} pasa por un enlace simbólico (destino real: $(realpath -m "${d}")): usa la ruta real."
    [[ -w "${d}" ]] || die "${d} no es escribible por $(id -un)."
done
# Mismo punto de montaje dos veces o una dentro de otra: se rechaza (un solo bind por carpeta, sin ambigüedad).
for ((i = 0; i < ${#DIRS[@]}; i++)); do
    for ((j = i + 1; j < ${#DIRS[@]}; j++)); do
        a="$(realpath -m "${DIRS[$i]}")/"; b="$(realpath -m "${DIRS[$j]}")/"
        [[ "${a}" != "${b}"* && "${b}" != "${a}"* ]] || die "${DIRS[$i]} y ${DIRS[$j]} se solapan."
    done
done

echo "Plan (nada se ejecuta sin --confirmo):"
n=0
for d in "${DIRS[@]}"; do
    n=$((n + 1))
    echo "  - escribiré ficheros sintéticos de hasta ${TAMANOS##*,} MB en  ${d}/zascarr_medicion_*  (montada como /ensayo/${n}) y los borraré."
done
echo "  - levantaré una Postgres propia y efímera (zascarr-medicion-pg-*, sin puertos, datos en tmpfs) y la borraré."
echo "  - NO tocaré ninguna otra carpeta, contenedor, red ni volumen."
[[ "${CONFIRMO}" -eq 1 ]] || { echo "Sin --confirmo: no hago nada."; exit 2; }

command -v docker >/dev/null || die "no encuentro docker."
if [[ -z "${IMAGEN}" ]]; then
    IMAGEN="zascarr-medicion:local"
    docker build -q -t "${IMAGEN}" "${REPO}" >/dev/null || die "no se pudo construir la imagen."
fi

SUFIJO="$$-$(date +%s)"
RED="zascarr-medicion-${SUFIJO}"
PG="zascarr-medicion-pg-${SUFIJO}"
limpiar() {
    docker rm -f "${PG}" >/dev/null 2>&1 || true
    docker network rm "${RED}" >/dev/null 2>&1 || true
}
trap limpiar EXIT

docker network create "${RED}" >/dev/null
docker run -d --name "${PG}" --network "${RED}" --tmpfs /var/lib/postgresql/data \
    -e POSTGRES_USER=test -e POSTGRES_PASSWORD=medicion -e POSTGRES_DB=zascarr_test \
    postgres:15-alpine >/dev/null
for _ in $(seq 1 40); do
    docker exec "${PG}" pg_isready -U test -d zascarr_test -q 2>/dev/null && break
    sleep 1
done
docker exec "${PG}" pg_isready -U test -d zascarr_test -q || die "Postgres de medición no arrancó."

MONTAJES=(); ARGS=(); n=0
for d in "${DIRS[@]}"; do
    n=$((n + 1))
    MONTAJES+=(-v "$(realpath -m "${d}"):/ensayo/${n}")
    ARGS+=(--dir "/ensayo/${n}")
done

SALIDA_TMP="$(mktemp)"
docker run --rm --network "${RED}" --user "${USUARIO}" --entrypoint python \
    -e HOME=/tmp -e "TEST_DATABASE_URL=postgresql://test:medicion@${PG}:5432/zascarr_test" \
    -e PYTHONPATH=/app/src -w /app "${MONTAJES[@]}" "${IMAGEN}" \
    scripts/medicion/medir_asignacion.py "${ARGS[@]}" --tamanos "${TAMANOS}" \
    --archivos "${ARCHIVOS}" --mb-extremo "${MB_EXTREMO}" > "${SALIDA_TMP}"

if [[ -n "${SALIDA}" ]]; then cp "${SALIDA_TMP}" "${SALIDA}"; echo "Informe en ${SALIDA}" >&2; fi
cat "${SALIDA_TMP}"
rm -f "${SALIDA_TMP}"
n=0; for d in "${DIRS[@]}"; do n=$((n + 1)); echo "  /ensayo/${n} = ${d}" >&2; done
