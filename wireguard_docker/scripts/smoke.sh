#!/usr/bin/env bash
# Prueba real con un peer temporal; requiere un servidor ya instalado.
set -Eeuo pipefail
umask 077
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f env/.env ]] || { echo 'Primero ejecuta ./install.sh' >&2; exit 1; }
peer="diag$(date -u +%Y%m%d%H%M%S)$$"
cleanup() {
  local result=$?
  trap - EXIT
  if grep -Eq "^PEERS=([^,]+,)*${peer}(,|$)" env/.env && ! ./wgctl.sh revoke-peer "$peer"; then
    echo "No se pudo limpiar el peer temporal: ./wgctl.sh revoke-peer $peer" >&2
    result=1
  fi
  exit "$result"
}
trap cleanup EXIT
./wgctl.sh add-peer "$peer"
port="$(sed -n 's/^SERVERPORT=//p' env/.env)"
subnet="$(sed -n 's/^INTERNAL_SUBNET=//p' env/.env)"
image="$(docker inspect --format '{{.Config.Image}}' wg_auditado_vpn)"
docker run --rm --cap-add NET_ADMIN \
  --sysctl net.ipv4.conf.all.src_valid_mark=1 \
  --network bridge --add-host host.docker.internal:host-gateway \
  --env TEST_PORT="$port" --env TEST_GATEWAY="${subnet%.*}.1" \
  --mount "type=bind,src=$ROOT/env/config/peer_$peer/peer_$peer.conf,dst=/client.conf,readonly" \
  --entrypoint /bin/bash "$image" -ec '
    umask 077
    sed -e "/^DNS =/d" -e "s/^Endpoint =.*/Endpoint = host.docker.internal:${TEST_PORT}/" /client.conf > /tmp/wgtest.conf
    qrencode -o /tmp/peer.png < /client.conf
    test -s /tmp/peer.png
    wg-quick up /tmp/wgtest.conf
    ping -c 3 -W 4 "$TEST_GATEWAY"
    nslookup example.com 1.1.1.1 >/dev/null
    curl --interface wgtest --connect-timeout 10 --max-time 20 --fail --silent --output /dev/null https://example.com
    echo "PASS: QR, puerto UDP publicado, túnel cifrado, DNS e Internet HTTPS"
    wg-quick down /tmp/wgtest.conf
  '
