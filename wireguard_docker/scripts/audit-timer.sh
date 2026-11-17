#!/usr/bin/env bash
# Opción EXPLÍCITA, no se activa en la instalación por defecto.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/wireguard-audit.service"
TIMER="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/wireguard-audit.timer"
case "${1:-}" in
 install)
  command -v systemctl >/dev/null || { echo 'systemctl no encontrado'; exit 1; }
  [[ "$(id -u)" != 0 ]] || { echo 'No instales este timer de usuario como root'; exit 1; }
  mkdir -p "$(dirname "$SERVICE")"
  AUDIT_SCRIPT="$(python3 - "$ROOT/scripts/audit.py" <<'PY'
import sys
print('"'+sys.argv[1].replace('\\','\\\\').replace('"','\\"').replace('%','%%').replace('$','$$')+'"')
PY
)"
  printf '%s\n' '[Unit]' 'Description=Auditoría diaria de WireGuard Docker (sin modificar estado)' '' \
    '[Service]' 'Type=oneshot' "ExecStart=/usr/bin/python3 $AUDIT_SCRIPT full --fail-on-error" > "$SERVICE"
  cat > "$TIMER" <<'TXT'
[Unit]
Description=Auditoría WireGuard diaria (reportes en env/audits)

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true
Unit=wireguard-audit.service

[Install]
WantedBy=timers.target
TXT
  systemctl --user daemon-reload
  systemctl --user enable --now wireguard-audit.timer
  echo 'Auditoría diaria activada a las 09:00 hora local de la VM/PC.'
  ;;
 remove)
  systemctl --user disable --now wireguard-audit.timer || true
  rm -f "$SERVICE" "$TIMER"
  systemctl --user daemon-reload
  echo 'Auditoría diaria desactivada.'
  ;;
 *) echo 'Uso: bash scripts/audit-timer.sh install|remove'; exit 2 ;;
esac
