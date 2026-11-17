#!/usr/bin/env bash
# Instalación local, sin modificar Docker, UFW, rutas, ni otros contenedores del host.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
log() { printf '\n[WireGuard] %s\n' "$*"; }
fail() { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }

[[ "$(uname -s)" == Linux ]] || fail "Requiere Linux/Ubuntu; no ejecutar en Windows directamente."
command -v docker >/dev/null 2>&1 || fail "Docker no está instalado."
docker compose version >/dev/null 2>&1 || fail "Falta Docker Compose v2 (docker compose)."
command -v python3 >/dev/null 2>&1 || fail "Falta python3 (auditoría sin dependencias externas)."
command -v tar >/dev/null 2>&1 || fail "Falta tar."
docker info >/dev/null 2>&1 || fail "El daemon Docker no responde o no tienes permisos: comprueba 'docker info'."

mkdir -p env/config env/audits env/backups env/revoked
chmod 700 env env/config env/audits env/backups env/revoked
if [[ ! -f env/.env ]]; then
  log "Creando env/.env a partir de env.example con UID/GID de tu cuenta."
  cp env.example env/.env
  python3 - "$PWD/env/.env" "$(id -u)" "$(id -g)" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); body = p.read_text()
for key,value in [('PUID',sys.argv[2]),('PGID',sys.argv[3])]:
    body = '\n'.join(f'{key}={value}' if x.startswith(key+'=') else x for x in body.splitlines())+'\n'
p.write_text(body)
PY
else
  log "Manteniendo env/.env existente; no se sobrescribirá."
fi
chmod 600 env/.env

log "Auditoría previa (el reporte queda en env/audits y no se sube a Git)."
python3 scripts/audit.py pre --fail-on-error || fail "Revisa la auditoría previa antes de iniciar."
log "Validando Compose (sin imprimir valores de configuración)."
docker compose --project-name wireguard-auditado --env-file env/.env -f compose.yaml config --quiet \
  || fail "Compose inválido; revisa env/.env y compose.yaml."
log "Descargando imagen oficial de LinuxServer (no altera tus demás proyectos)."
docker compose --project-name wireguard-auditado --env-file env/.env -f compose.yaml pull wireguard
log "Creando solo WireGuard y esperando healthcheck (máximo 120 s)."
docker compose --project-name wireguard-auditado --env-file env/.env -f compose.yaml \
  up -d --wait --wait-timeout 120 wireguard \
  || fail "WireGuard no quedó saludable. Consulta ./wgctl.sh logs; la instalación no se completó."
log "Auditoría posterior y controles de seguridad."
python3 scripts/audit.py full --fail-on-error || fail "La auditoría final detectó fallas; consulta env/audits."
cat <<'TXT'

Instalación completada: contenedor saludable y auditoría local sin fallas.
Gestionar:       ./wgctl.sh status
Auditar:         ./wgctl.sh audit
Config Android:  ./wgctl.sh qr android
Config laptop:   ./wgctl.sh export laptop

IMPORTANTE: para conectar desde fuera de tu Wi-Fi debes redirigir UDP 51820
(o el SERVERPORT elegido) en tu router a la IP LAN de tu Ubuntu.
Si el proveedor usa CGNAT necesitarás IP pública/VPS/otra solución.
TXT
