#!/usr/bin/env python3
"""Edición atómica y segura de PEERS en env/.env; usa solo stdlib."""
from pathlib import Path
import os, re, sys, tempfile

if len(sys.argv) != 4 or sys.argv[1] not in ('add-peer','revoke-peer'):
    sys.exit('Uso: peers.py add-peer|revoke-peer <nombre> <envfile>')
cmd, peer, dest = sys.argv[1:]
if not re.fullmatch('[A-Za-z][A-Za-z0-9]*',peer):
    sys.exit('Nombre inválido')
p = Path(dest)
original = p.read_text(encoding='utf8')
match = re.findall(r'^PEERS=(.*)$', original, re.M)
if len(match) != 1:
    sys.exit('No se encuentra un solo PEERS= en .env')
peers = [x.strip() for x in match[0].split(',') if x.strip()]
if len(set(peers)) != len(peers):
    sys.exit('Duplicados en PEERS')
if not peers or not all(re.fullmatch('[A-Za-z][A-Za-z0-9]*', x) for x in peers):
    sys.exit('PEERS debe contener nombres que empiecen con letra (sin modo numérico)')
if cmd == 'add-peer':
    if peer in peers:
        sys.exit('Peer ya existe')
    if len(peers) >= 250:
        sys.exit('Límite de 250 clientes alcanzado')
    peers.append(peer)
else:
    if peer not in peers:
        sys.exit('Peer no encontrado')
    if len(peers) == 1:
        sys.exit('Es el último peer: detén el servidor con ./wgctl.sh down')
    peers.remove(peer)
updated = re.sub(r'^PEERS=.*$', 'PEERS=' + ','.join(peers), original, count=1, flags=re.M)
fd, tmp = tempfile.mkstemp(prefix='.env-update-',dir=str(p.parent))
try:
    with os.fdopen(fd,'w',encoding='utf8') as f:
        f.write(updated)
    os.chmod(tmp,0o600)
    os.replace(tmp,p)
finally:
    if os.path.exists(tmp): os.unlink(tmp)
print('PEERS modificado. Listado actual:', ', '.join(peers))
