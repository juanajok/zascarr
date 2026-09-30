#!/usr/bin/env bash
# =============================================================================
# medir-pbkdf2.sh — mide el coste real de PBKDF2 en la Pi.
#
# SOLO LEE: no cambia iteraciones ni ningún fichero. Imprime los valores, las
# medianas y la decisión que toca; aplicar el cambio es cosa de quien lo lea.
#
# Contexto: `_PBKDF2_ITERATIONS` (services/auth.py) está en 260.000. OWASP pide
# que un hash tarde menos de un segundo, pero avisa de que un coste alto se
# puede usar para agotar la CPU. Regla de decisión:
#
#   mediana con DOS a la vez < 0,8 s  → subir a 600.000
#   0,8 s o más                       → dejar 260.000
#
# Se decide con la mediana de **dos verificaciones a la vez**, no en solitario:
# la app verifica con dos hilos de PBKDF2, y de una en una el coste se subestima
# cuando compite con Postgres o con Redis. La mediana en solitario se imprime
# como referencia.
#
# Uso:
#   scripts/medir-pbkdf2.sh
#
# Se ejecuta en el HOST (la Pi): lanza las mediciones dentro del contenedor con
# el mismo intérprete que usa la app.
#
# Al terminar, anota en docs/design/benchmark-seguridad-auth-origen-host.md la
# fecha, el modelo de la Pi y el valor medido, y aplica (o no) el cambio.
# =============================================================================
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_comun.sh"

ITERACIONES="${PBKDF2_ITERACIONES:-600000}"
REPETICIONES="${PBKDF2_REPETICIONES:-5}"
REPETICIONES_PARALELAS="${PBKDF2_REPETICIONES_PARALELAS:-3}"
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

# mediana VALOR...  → el valor central (o la media de los dos centrales)
# `LC_ALL=C` a propósito: con locale español, `awk printf` escribiría «0,580» y
# la comparación de la decisión lo leería como 0 (decidiría subir siempre).
mediana() {
    local -a ordenados
    mapfile -t ordenados < <(printf '%s\n' "$@" | LC_ALL=C sort -n)
    local n="${#ordenados[@]}"
    if (( n == 0 )); then
        printf ''
    elif (( n % 2 == 1 )); then
        printf '%s' "${ordenados[$(( n / 2 ))]}"
    else
        LC_ALL=C awk -v a="${ordenados[$(( n / 2 - 1 ))]}" \
                     -v b="${ordenados[$(( n / 2 ))]}" \
            'BEGIN { printf "%.3f", (a + b) / 2 }'
    fi
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
info "Iteraciones medidas: ${ITERACIONES}"
echo

# ── 1) En reposo, de una en una ──────────────────────────────────────────────
info "En reposo (${REPETICIONES} veces, de una en una):"
valores=()
for i in $(seq 1 "${REPETICIONES}"); do
    valor="$(medir)"
    valores+=("${valor}")
    info "  ${i}/${REPETICIONES}: ${valor} s"
done
mediana_sola="$(mediana "${valores[@]}")"

# ── 2) Dos a la vez (lo que de verdad hace la app) ───────────────────────────
echo
info "Dos a la vez (${REPETICIONES_PARALELAS} rondas): es el caso real — la app"
info "verifica con dos hilos de PBKDF2, compitiendo con Postgres y Redis."
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
valores_par=()
for ronda in $(seq 1 "${REPETICIONES_PARALELAS}"); do
    medir > "${tmp}/a" & p1=$!
    medir > "${tmp}/b" & p2=$!
    wait "${p1}" "${p2}"
    a="$(cat "${tmp}/a")"; b="$(cat "${tmp}/b")"
    valores_par+=("${a}" "${b}")
    info "  ${ronda}/${REPETICIONES_PARALELAS}: ${a} s y ${b} s"
done
mediana_par="$(mediana "${valores_par[@]}")"

# ── Resumen y decisión ───────────────────────────────────────────────────────
echo
success "Mediana en reposo (referencia):      ${mediana_sola} s  (${valores[*]})"
success "Mediana con dos a la vez (decisión): ${mediana_par} s  (${valores_par[*]})"
success "Modelo: ${modelo} · $(date -u +%Y-%m-%d)"

echo
if LC_ALL=C awk -v m="${mediana_par}" -v u="${UMBRAL}" 'BEGIN { exit !(m < u) }'; then
    success "DECISIÓN: subir _PBKDF2_ITERATIONS a ${ITERACIONES} (dos a la vez < ${UMBRAL} s)."
else
    warn "DECISIÓN: dejar 260.000 (dos a la vez ≥ ${UMBRAL} s). Anota ${mediana_par} s en la ficha."
fi

echo
info "Referencia opcional — durante una importación:"
echo "  1. Lanza una importación o espera al ciclo periódico."
echo "  2. Repite: ${COMPOSE[*]} exec -T ${SERVICIO} python -c '<el código>' ${ITERACIONES}"
if [[ -t 0 ]]; then
    read -rp "  Valor medido con carga, en segundos (Enter para omitir): " con_carga || con_carga=""
    if [[ -n "${con_carga}" ]]; then
        echo "  Con carga: ${con_carga} s"
    fi
fi
