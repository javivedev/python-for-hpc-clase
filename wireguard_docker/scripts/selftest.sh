#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
for f in install.sh wgctl.sh audit.sh scripts/*.sh; do
  bash -n "$f" && echo "PASS Bash: $f"
done
python3 -m py_compile scripts/audit.py scripts/peers.py
echo 'PASS Python: módulos compilan'
python3 -m unittest discover -s tests -v
grep -Fxq '/env/' .gitignore
echo 'PASS gitignore: /env/'
if grep -Eiq '^[[:space:]]*privileged:[[:space:]]*true|SYS_MODULE' compose.yaml; then
  echo 'FAIL privilegios excesivos en Compose' >&2; exit 1
fi
echo 'PASS Compose: sin privileged ni SYS_MODULE'
if [[ -f env/.env ]] && command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  docker compose --project-name wireguard-auditado --env-file env/.env -f compose.yaml config --quiet
  echo 'PASS Compose: sintaxis y interpolación'
else
  echo 'SKIP Compose: requiere env/.env y Compose disponible'
fi
echo 'Autoverificación estática completada.'
