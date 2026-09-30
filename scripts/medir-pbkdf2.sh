#!/usr/bin/env bash
# =============================================================================
# medir-pbkdf2.sh — mide el coste real de PBKDF2 en la Pi.
#
# SOLO LEE: no cambia iteraciones ni ningún fichero. Imprime los valores, la
# mediana y la decisión que toca; aplicar el cambio es cosa de quien lo lea.
#
# Contexto: `_PBKDF2_ITERATIONS` (services/auth.py) está en 260.000. OWASP pide
# que un hash tarde menos de un segundo, pero avisa de que un coste alto se
# puede usar para agotar la CPU. Regla de decisión:
#
#   mediana < 0,8 s  → subir a 600.000
#   0,8 s o más      → dejar 260.000 (con la cola de 3 intentos, una
#                      verificación lenta alarga lo que un atacante puede
#                      mantener ocupadas las plazas)
#
# Uso:
#   scripts/medir-pbkdf2.sh
#
# Se ejecuta en el HOST (la Pi): lanza las mediciones dentro del contenedor con
# el mismo intérprete que usa la app. La medición "durante una importación" no
# se puede automatizar bien, así que el script la pide como paso manual.
#
# Al terminar, anota en docs/design/benchmark-seguridad-auth-origen-host.md la
# fecha, el modelo de la Pi y el valor medido, y aplica (o no) el cambio.
# =============================================================================
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_comun.sh"

ITERACIONES="${PBKDF2_ITERACIONES:-600000}"
REPETICIONES="${PBKDF2_REPETICIONES:-5}"
UMBRAL="${PBKDF2_UMBRAL:-0.8}"
SERVICIO="${PBKDF2_SERVICIO:-zascarr}"

CODIGO_PY='
import hashlib, sys, time
n = int(sys.argv[1])
inicio = time.perf_counter()
hashlib.pbkdf2_hmac("sha256", b"x", b"y" * 16, n)
print(f"{time.perf_counter() - inicio:.3f}")
'

medir() {
    "${COMPOSE[@]}" exec -T "${SERVICIO}" python -c "${CODIGO_PY}" "${ITERACIONES}"
}

comprobar_requisitos

info "¿Está el contenedor en marcha?"
if ! "${COMPOSE[@]}" ps --status running --services 2>/dev/null | grep -qx "${SERVICIO}"; then
    die "El servicio «${SERVICIO}» no está corriendo. Arráncalo con: ${COMPOSE[*]} up -d"
fi

modelo="$(cat /proc/device-tree/model 2>/dev/null | tr -d '\0' || true)"
[[ -n "${modelo}" ]] || modelo="no detectado (¿esto no es una Raspberry Pi?)"

echo
info "Modelo: ${modelo}"
info "Fecha:  $(date -u +%Y-%m-%dT%H:%M:%SZ)"
info "Iteraciones medidas: ${ITERACIONES} · repeticiones en reposo: ${REPETICIONES}"
echo

valores=()
for i in $(seq 1 "${REPETICIONES}"); do
    valor="$(medir)"
    valores+=("${valor}")
    info "  Reposo ${i}/${REPETICIONES}: ${valor} s"
done

# Mediana. Con 5 valores es el tercero; con un número par, la media central.
mapfile -t ordenados < <(printf '%s\n' "${valores[@]}" | sort -n)
total="${#ordenados[@]}"
if (( total % 2 == 1 )); then
    mediana="${ordenados[$(( total / 2 ))]}"
else
    mediana="$(awk -v a="${ordenados[$(( total / 2 - 1 ))]}" \
                   -v b="${ordenados[$(( total / 2 ))]}" \
                   'BEGIN { printf "%.3f", (a + b) / 2 }')"
fi

echo
success "Mediana en reposo: ${mediana} s  (valores: ${valores[*]})"
success "Modelo: ${modelo} · $(date -u +%Y-%m-%d)"

echo
if awk -v m="${mediana}" -v u="${UMBRAL}" 'BEGIN { exit !(m < u) }'; then
    success "DECISIÓN: subir _PBKDF2_ITERATIONS a ${ITERACIONES} (mediana < ${UMBRAL} s)."
else
    warn "DECISIÓN: dejar 260.000 (mediana ≥ ${UMBRAL} s). Anota ${mediana} s en la ficha."
fi

echo
info "Medición con carga (manual, para referencia):"
echo "  1. Lanza una importación o espera al ciclo periódico."
echo "  2. Repite: ${COMPOSE[*]} exec -T ${SERVICIO} python -c '<el código>' ${ITERACIONES}"
if [[ -t 0 ]]; then
    read -rp "  Valor medido con carga, en segundos (Enter para omitir): " con_carga || con_carga=""
    [[ -n "${con_carga}" ]] && echo "  Con carga: ${con_carga} s"
fi
