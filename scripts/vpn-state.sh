#!/usr/bin/env bash
# =============================================================================
# vpn-state.sh — Confiraspa: publica el estado del túnel WireGuard para
# que SecuenciArr (contenedor, sin network_mode: host ni iproute2) pueda
# leerlo en su healthcheck.
#
# Instalación:
#   1. Copia este script a /usr/local/bin/vpn-state.sh y chmod +x
#   2. Instala el timer systemd incluido al final de este fichero:
#        sudo cp secuenciarr-vpn-state.{service,timer} /etc/systemd/system/
#        sudo systemctl daemon-reload
#        sudo systemctl enable --now secuenciarr-vpn-state.timer
#   3. Ajusta WG_INTERFACE si tu túnel no se llama wg0.
#
# Contrato con health.py:
#   Escribe /mnt/nvme/tebeoteca/config/vpn-state/wg0.json con:
#     {"interface": "wg0", "vpn_active": true|false, "updated_at_epoch": N}
#   Escritura atómica (.tmp + mv) para que health.py nunca lea medio JSON.
#   Idempotente: ejecutarlo N veces es seguro.
# =============================================================================
set -euo pipefail

WG_INTERFACE="${WG_INTERFACE:-wg0}"
STATE_DIR="/mnt/nvme/tebeoteca/config/vpn-state"
STATE_FILE="${STATE_DIR}/${WG_INTERFACE}.json"

mkdir -p "$STATE_DIR"

if ip link show "$WG_INTERFACE" >/dev/null 2>&1; then
    ACTIVE=true
else
    ACTIVE=false
fi

NOW=$(date +%s)
TMP="${STATE_FILE}.tmp"

printf '{"interface": "%s", "vpn_active": %s, "updated_at_epoch": %s}\n' \
    "$WG_INTERFACE" "$ACTIVE" "$NOW" > "$TMP"
mv "$TMP" "$STATE_FILE"

echo "[vpn-state] $WG_INTERFACE active=$ACTIVE → $STATE_FILE"

# =============================================================================
# unidades systemd para el timer (guardar como ficheros separados):
#
# --- /etc/systemd/system/secuenciarr-vpn-state.service ---
# [Unit]
# Description=Publica estado de WireGuard para SecuenciArr
# After=network-online.target wg-quick@wg0.service
#
# [Service]
# Type=oneshot
# ExecStart=/usr/local/bin/vpn-state.sh
#
# --- /etc/systemd/system/secuenciarr-vpn-state.timer ---
# [Unit]
# Description=Refresca estado de VPN cada minuto
#
# [Timer]
# OnBootSec=1min
# OnUnitActiveSec=1min
# AccuracySec=10s
#
# [Install]
# WantedBy=timers.target
# =============================================================================
