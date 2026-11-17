#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# -eq 0 ]]; then set -- full; fi
exec python3 "$ROOT/scripts/audit.py" "$@"
