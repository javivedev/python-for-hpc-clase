#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
ENV_FILE="$ROOT/env/.env"
help_msg() {
cat <<'TXT'
Uso: ./wgctl.sh <comando> [nombre]
  install                Preauditoría, descarga y arranque (primera vez)
  up | down | restart    Gestiona solo este proyecto Compose
  apply                 Aplica cambios de env/.env recreando el servicio
  status                 Estado del servicio / interfaz (sin claves)
  audit [pre|post|security|full]   Auditoría a env/audits (full por defecto)
  logs                   Logs del contenedor (sin QR: LOG_CONFS=false)
  peers                  Lista de perfiles generados
  qr <nombre>            Muestra QR local en terminal (CONFIDENCIAL)
  export <nombre>        Copia config cliente a env/exports (CONFIDENCIAL)
  add-peer <nombre>      Agrega un cliente al .env y recrea WireGuard
  revoke-peer <nombre>   Revoca su acceso y aparta su perfil local
  update                 Actualiza solo la imagen de WireGuard
  backup                 Crea backup TAR sensible dentro de env/backups
  help                   Esta ayuda

No se crean VM, no se alteran firewall/router ni otros contenedores.
TXT
}
compose() {
  [[ -f "$ENV_FILE" ]] || { echo "No existe env/.env: primero ./install.sh" >&2; return 1; }
  docker compose --project-name wireguard-auditado --env-file "$ENV_FILE" -f "$ROOT/compose.yaml" "$@"
}
getenv() {
  local key="$1"
  sed -n "s/^${key}=//p" "$ENV_FILE" | tail -n 1
}
peer_check() {
  [[ "$1" =~ ^[A-Za-z][A-Za-z0-9]*$ ]] || { echo "Nombre inválido (empieza con letra; solo letras y números)." >&2; exit 1; }
}
peer_conf() {
  local peer="$1"
  printf '%s/env/config/peer_%s/peer_%s.conf' "$ROOT" "$peer" "$peer"
}
ready_env() { [[ -f "$ENV_FILE" ]] || { echo "Primero ejecuta bash install.sh" >&2; exit 1; }; }
preflight() { python3 scripts/audit.py pre --fail-on-error; }
wait_wg() { compose up -d --wait --wait-timeout 120 wireguard; }
postflight() { python3 scripts/audit.py "${1:-full}" --fail-on-error; }
cmd="${1:-help}"; shift || true
case "$cmd" in
  install) exec bash "$ROOT/install.sh" ;;
  up) preflight; wait_wg; postflight ;;
  down) compose down ;; # NO usa --volumes: preserva claves
  restart) preflight; compose restart wireguard; wait_wg; postflight ;;
  apply) preflight; compose up -d --force-recreate --wait --wait-timeout 120 wireguard; postflight ;;
  status)
    compose ps wireguard
    printf '\nEstado WireGuard (sin claves):\n'
    compose exec -T wireguard wg show wg0 listen-port
    printf '\nÚltima auditoría: '; ls -1t env/audits/*.md 2>/dev/null | head -n 1 || true
    ;;
  audit)
    ready_env
    mode="${1:-full}"
    case "$mode" in pre|post|security|full) ;; *) echo "Modo inválido" >&2; exit 1;; esac
    shift || true
    python3 scripts/audit.py "$mode" "$@" ;;
  logs) compose logs --tail=100 -f wireguard ;;
  peers)
    ready_env
    printf 'Peers definidos: %s\n' "$(getenv PEERS)"
    printf 'Archivos cliente disponibles:\n'
    find env/config -maxdepth 2 -name 'peer_*.conf' -type f -printf '  %P\n' 2>/dev/null | sort
    ;;
  qr)
    ready_env; peer="${1:-}"; peer_check "$peer"
    conf="$(peer_conf "$peer")"; [[ -f "$conf" ]] || { echo "Peer sin configuración: $peer" >&2; exit 1; }
    echo 'AVISO: el QR contiene una clave privada. No compartas ni captures esta terminal.'
    if command -v qrencode >/dev/null 2>&1; then
      qrencode -t ANSIUTF8 < "$conf"
    else
      compose exec -T wireguard qrencode -t ANSIUTF8 < "$conf"
    fi
    ;;
  export)
    ready_env; peer="${1:-}"; peer_check "$peer"
    conf="$(peer_conf "$peer")"; [[ -f "$conf" ]] || { echo "Peer sin configuración: $peer" >&2; exit 1; }
    mkdir -p env/exports; chmod 700 env/exports
    install -m 600 "$conf" "env/exports/${peer}.conf"
    printf 'Perfil sensible guardado en: %s/env/exports/%s.conf\n' "$ROOT" "$peer"
    ;;
  add-peer|revoke-peer)
    ready_env; peer="${1:-}"; peer_check "$peer"
    preflight
    python3 scripts/peers.py "${cmd}" "$peer" "$ENV_FILE"
    echo 'Recreando solamente este servicio para aplicar cambios...'
    compose up -d --force-recreate --wait --wait-timeout 120 wireguard
    if [[ "$cmd" == revoke-peer ]] && [[ -d "env/config/peer_$peer" ]]; then
      mkdir -p env/revoked; chmod 700 env/revoked
      mv "env/config/peer_$peer" "env/revoked/${peer}_$(date -u +%Y%m%dT%H%M%SZ)"
      echo 'Clave antigua conservada bajo env/revoked (no reutilizar).'
    fi
    if [[ "$cmd" == revoke-peer ]] && [[ -f "env/exports/$peer.conf" ]]; then
      mv "env/exports/$peer.conf" "env/revoked/${peer}_export_$(date -u +%Y%m%dT%H%M%SZ).conf"
    fi
    postflight
    ;;
  update)
    ready_env
    python3 scripts/audit.py pre --fail-on-error || { echo 'Auditoría previa falló, no se actualizó.' >&2; exit 1; }
    compose pull wireguard
    wait_wg
    postflight
    ;;
  backup)
    ready_env
    mkdir -p env/backups; chmod 700 env/backups
    dest="env/backups/wireguard_$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
    tar -czf "$dest" -- env/.env env/config
    chmod 600 "$dest"
    echo "Backup con CLAVES PRIVADAS: $dest"
    echo 'Mantén el backup cifrado si lo trasladas a otro equipo.'
    ;;
  help|-h|--help) help_msg ;;
  *) help_msg; exit 2 ;;
esac
