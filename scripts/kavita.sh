#!/usr/bin/env bash
# kavita.sh — Gestión de Kavita en baremetal ARM64
# Uso: sudo bash kavita.sh {install|update|status|logs|restart|uninstall}
set -euo pipefail

KAVITA_USER="pi"; KAVITA_GROUP="pi"
INSTALL_DIR="/opt/kavita"
DATA_DIR="${KAVITA_DATA_DIR:-/opt/kavita/config}"
LIBRARY_DIR="${KAVITA_LIBRARY_DIR:-/media/library}"    # biblioteca real
PORT="5000"; ARCH="arm64"
RELEASES="https://api.github.com/repos/kareadita/kavita/releases/latest"
[[ ${EUID} -ne 0 ]] && echo "Ejecuta como root" && exit 1

get_version() { curl -sf "$RELEASES" | grep '"tag_name"' | head -1 | sed -E 's/.*"v?([^"]+)".*/\1/'; }
get_url()     { echo "https://github.com/kareadita/kavita/releases/download/v$1/kavita-linux-${ARCH}.tar.gz"; }

install() {
    mkdir -p "$INSTALL_DIR" "$DATA_DIR"
    local v; v=$(get_version)
    local tmp; tmp=$(mktemp -d); trap "rm -rf $tmp" EXIT
    curl -fL "$(get_url "$v")" -o "$tmp/kavita.tar.gz"
    tar -xzf "$tmp/kavita.tar.gz" -C "$tmp"
    cp -r "$tmp/kavita/"* "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/Kavita"
    chown -R "$KAVITA_USER:$KAVITA_GROUP" "$INSTALL_DIR" "$DATA_DIR"
    [[ -d "$INSTALL_DIR/config" ]] && rm -rf "$INSTALL_DIR/config"
    ln -s "$DATA_DIR" "$INSTALL_DIR/config"
    cat > /etc/systemd/system/kavita.service << EOF
[Unit]
Description=Kavita Comic Server
After=network.target
[Service]
Type=simple
User=$KAVITA_USER
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/Kavita
Restart=on-failure
Environment=ASPNETCORE_URLS=http://0.0.0.0:$PORT
StandardOutput=journal
SyslogIdentifier=kavita
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload && systemctl enable --now kavita
    echo "Kavita $v instalado — http://127.0.0.1:$PORT"
}

update() {
    local v; v=$(get_version)
    local cur="desconocida"; [[ -f "$INSTALL_DIR/VERSION" ]] && cur=$(cat "$INSTALL_DIR/VERSION")
    [[ "$cur" == "$v" ]] && echo "Ya tienes $v" && return
    systemctl stop kavita || true
    local tmp; tmp=$(mktemp -d); trap "rm -rf $tmp" EXIT
    curl -fL "$(get_url "$v")" -o "$tmp/kavita.tar.gz"
    tar -xzf "$tmp/kavita.tar.gz" -C "$tmp"
    rsync -a --exclude='config' "$tmp/kavita/" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/Kavita"
    echo "$v" > "$INSTALL_DIR/VERSION"
    systemctl start kavita
    echo "Kavita actualizado a $v"
}

case "${1:-help}" in
    install)   install ;;
    update)    update ;;
    status)    systemctl status kavita --no-pager ;;
    logs)      journalctl -u kavita -f --no-pager ;;
    restart)   systemctl restart kavita ;;
    uninstall) systemctl stop kavita; systemctl disable kavita; rm -rf "$INSTALL_DIR"; echo "Desinstalado. Datos en $DATA_DIR conservados." ;;
    *)         echo "Uso: sudo bash kavita.sh {install|update|status|logs|restart|uninstall}" ;;
esac
