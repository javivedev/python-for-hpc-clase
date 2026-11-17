#!/usr/bin/env python3
"""Auditoría no intrusiva de WireGuard Docker. Stdlib, sin guardar secretos.

Todos los resultados se almacenan EXCLUSIVAMENTE en env/audits, ignorado en Git.
No modifica firewall, contenedores, configuración de WireGuard ni claves.
"""
import argparse
import datetime as dt
import ipaddress
import json
import os
from pathlib import Path
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / 'env'
AUDITS = RUNTIME / 'audits'
CONFIG = RUNTIME / 'config'
ENV_FILE = RUNTIME / '.env'
SERVICE = 'wg_auditado_vpn'

CHECKS = []


def check(code, status, message, fix=''):
    CHECKS.append({'code':code, 'status':status, 'message':message, 'remediation':fix})


def run(command, timeout=12):
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired):
        return 127, '', ''


def env_read():
    env = {}
    if not ENV_FILE.is_file():
        return env
    for line in ENV_FILE.read_text(encoding='utf8').splitlines():
        line = line.strip()
        if not line or line.startswith('#'): continue
        if '=' not in line:
            check('ENV_SYNTAX','FAIL','Línea inválida en env/.env.')
            continue
        k, v = line.split('=',1)
        k, v = k.strip(), v.strip()
        if k in env:
            check('ENV_DUPLICATE','FAIL',f'Variable duplicada: {k}.')
        if re.search(r'[$`\'"\s#]', v):
            check('ENV_LITERAL','FAIL',f'{k} debe ser un valor literal sin comillas, espacios ni interpolaciones.')
        env[k] = v
    return env


def compose(*cmd):
    return run(['docker','compose','--project-name','wireguard-auditado',
                '--env-file',str(ENV_FILE),'-f',str(ROOT/'compose.yaml'),*cmd], timeout=25)


def parse_network(v):
    try:
        return ipaddress.ip_network(v if '/' in v else v+'/24', strict=False)
    except ValueError:
        return None


def validate_env(env):
    if not env:
        check('ENV_EXISTS','FAIL','No existe env/.env.','Ejecuta ./install.sh.')
        return None
    mandatory = ('SERVERPORT','SERVERURL','PEERS','INTERNAL_SUBNET','ALLOWEDIPS',
                 'PUID','PGID','TZ','PEERDNS')
    missing = [x for x in mandatory if not env.get(x)]
    check('ENV_REQUIRED','FAIL' if missing else 'PASS',
          'Faltan variables requeridas.' if missing else 'Variables mínimas presentes.',
          'Completa env/.env usando env.example.' if missing else '')
    try:
        port = int(env.get('SERVERPORT',''))
        valid_port = 1024 <= port <= 65535
    except ValueError:
        port, valid_port = None, False
    check('UDP_PORT','PASS' if valid_port else 'FAIL',
          f'Puerto UDP válido: {port}.' if valid_port else 'Puerto SERVERPORT inválido o reservado.',
          'Configura SERVERPORT entre 1024 y 65535.' if not valid_port else '')
    url = env.get('SERVERURL','')
    valid_url = url == 'auto'
    if not valid_url and url:
        try:
            valid_url = isinstance(ipaddress.ip_address(url), ipaddress.IPv4Address)
        except ValueError:
            valid_url = bool(re.fullmatch(r'(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?',url)) and '..' not in url
    check('ENDPOINT','PASS' if valid_url else 'FAIL',
          'Endpoint configurado (sin registrar el valor).' if valid_url else 'SERVERURL inválido.',
          'Usa SERVERURL=auto o un dominio/IP público.' if not valid_url else '')
    if url == 'auto':
        check('PUBLIC_IP','INFO','SERVERURL=auto: se usará detección de IP pública. Si cambia, el peer puede necesitar regeneración.',
              'Para IP dinámica considera DDNS y actualiza SERVERURL.')
    peers = env.get('PEERS','').split(',')
    valid_peers = bool(peers) and len(set(peers))==len(peers) and all(re.fullmatch('[A-Za-z][A-Za-z0-9]*',p) for p in peers)
    check('PEER_FORMAT','PASS' if valid_peers else 'FAIL',
          f'{len(peers)} peers con nombres válidos.' if valid_peers else 'PEERS vacío, duplicado o contiene caracteres inválidos.',
          'Usa PEERS=android,laptop; cada nombre debe empezar con letra.' if not valid_peers else '')
    ipnet = parse_network(env.get('INTERNAL_SUBNET',''))
    correct = bool(ipnet and isinstance(ipnet,ipaddress.IPv4Network) and ipnet.prefixlen==24
                   and env.get('INTERNAL_SUBNET')==str(ipnet.network_address)
                   and any(ipnet.subnet_of(ipaddress.ip_network(block)) for block in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')))
    check('TUNNEL_SUBNET','PASS' if correct else 'FAIL',
          'Red IPv4 privada de túnel /24 válida.' if correct else 'INTERNAL_SUBNET debe ser una red IPv4 privada terminada en .0, sin /24.',
          'Ejemplo: INTERNAL_SUBNET=10.67.47.0' if not correct else '')
    if correct and len(peers)>250:
        check('PEER_CAPACITY','FAIL','Demasiados peers para red /24.','Usa menos de 251 clientes.')
    try:
        allowed = [ipaddress.ip_network(x.strip(),strict=False) for x in env.get('ALLOWEDIPS','').split(',')]
        ok = bool(allowed)
    except ValueError: ok = False
    check('ROUTING_MODE','PASS' if ok else 'FAIL',
          'AllowedIPs de cliente sintácticamente correcto.' if ok else 'ALLOWEDIPS inválido.',
          'Ejemplo de túnel completo IPv4: ALLOWEDIPS=0.0.0.0/0' if not ok else '')
    if ok:
        if any(str(x)=='0.0.0.0/0' for x in allowed):
            check('ROUTING_SCOPE','INFO','Túnel completo IPv4: el tráfico del cliente usará el servidor.')
        else:
            check('ROUTING_SCOPE','INFO','Túnel dividido: solo las redes indicadas usan VPN; comprobar acceso deseado.')
    for key in ('PUID','PGID'):
        value=env.get(key,'')
        valid=value.isdecimal() and 0 < int(value) < 2**32-1
        check(key,'PASS' if valid else 'FAIL',f'{key} válido.' if valid else f'{key} debe ser un ID numérico no root.')
    try:
        ZoneInfo(env.get('TZ',''))
        tz_ok=True
    except (ZoneInfoNotFoundError,ValueError):
        tz_ok=False
    check('TIMEZONE','PASS' if tz_ok else 'FAIL','Zona horaria válida.' if tz_ok else 'TZ no corresponde a una zona IANA instalada.')
    dns=env.get('PEERDNS','')
    try:
        dns_ok=dns=='auto' or bool(dns) and all(ipaddress.ip_address(x) for x in dns.split(','))
    except ValueError:
        dns_ok=False
    check('PEER_DNS','PASS' if dns_ok else 'FAIL','PEERDNS válido.' if dns_ok else 'PEERDNS requiere auto o direcciones IP separadas por coma.')
    return {'port':port,'network':ipnet if correct else None,'peers':peers}


def check_paths():
    for path, title, mode in [(RUNTIME,'env/',0o700),(ENV_FILE,'env/.env',0o600),
                               (CONFIG,'env/config/',0o700),(AUDITS,'env/audits/',0o700)]:
        if not path.exists():
            check('PATH_'+title,'WARN',f'No existe {title}.','Ejecuta ./install.sh.')
            continue
        actual=stat.S_IMODE(path.stat().st_mode)
        safe = (actual & 0o077)==0
        check('PERMS_'+title,'PASS' if safe else 'FAIL',
              f'{title}: permisos {actual:04o}, '+('sin acceso de grupo/otros.' if safe else 'expuesto a grupo/otros.'),
              f'chmod {mode:03o} {title}' if not safe else '')
    gitignore = ROOT / '.gitignore'
    good = gitignore.is_file() and any(x.strip() == '/env/' for x in gitignore.read_text().splitlines())
    check('GITIGNORE','PASS' if good else 'FAIL',
          'Git excluye todo /env/.' if good else 'Falta patrón /env/ en .gitignore.',
          'Agrega /env/ a .gitignore.' if not good else '')
    # Si ya fue agregado en algún repo, .gitignore NO lo elimina del índice.
    isrepo, _, _ = run(['git','-C',str(ROOT),'rev-parse','--is-inside-work-tree']) if shutil.which('git') else (1,'','')
    if isrepo == 0:
        rc, tracked, _ = run(['git','-C',str(ROOT),'ls-files','--','env/'])
        if rc == 0:
            n = len([s for s in tracked.splitlines() if s.strip()])
            check('GIT_TRACKED_SECRETS','FAIL' if n else 'PASS',
                  f'{n} archivos de env/ ya están rastreados por Git.' if n else 'No hay archivos env/ versionados.',
                  'Usa git rm -r --cached env/; rota las claves si ya fueron publicadas.' if n else '')
    if CONFIG.exists():
        unsafe=[]; count=0
        for path in CONFIG.rglob('*'):
            if path.is_symlink():
                unsafe.append('Enlace simbólico en configuración')
                continue
            if not path.is_file(): continue
            # Las plantillas contienen referencias a claves, no las claves generadas.
            if CONFIG/'templates' in path.parents: continue
            # Sin reportar nombres de claves ni valores, solo conteos.
            if path.name.endswith(('.conf','.png')) or 'key' in path.name.lower():
                count += 1
                if stat.S_IMODE(path.stat().st_mode) & 0o077:
                    unsafe.append('Material privado accesible a grupo/otros')
        check('SECRET_FILE_PERMS','FAIL' if unsafe else 'PASS',
              f'{len(unsafe)} anomalías de permisos entre {count} archivos sensibles.' if unsafe
              else f'{count} archivos sensibles revisados, sin permisos de grupo/otros.',
              'Restringe archivos sensibles a 0600 y directorios a 0700.' if unsafe else '')


def preflight(env, vals):
    check('OS','PASS' if platform.system()=='Linux' else 'FAIL',
          'Host Linux detectado.' if platform.system()=='Linux' else 'Solo Linux soportado.')
    if not shutil.which('docker'):
        check('DOCKER_CLI','FAIL','No existe docker en PATH.','Instala Docker Engine y Compose v2.')
        return
    rc, v, _ = run(['docker','--version'])
    check('DOCKER_CLI','PASS' if rc==0 else 'FAIL',
          v.strip()[:100] if rc==0 else 'Docker CLI no funciona.')
    rc, v, _ = run(['docker','compose','version'])
    check('COMPOSE','PASS' if rc==0 else 'FAIL',
          v.strip()[:100] if rc==0 else 'Compose v2 ausente.',
          'Instala docker-compose-plugin.' if rc!=0 else '')
    rc,_,_ = run(['docker','info'],timeout=15)
    check('DOCKER_DAEMON','PASS' if rc==0 else 'FAIL',
          'Daemon accesible.' if rc==0 else 'No hay acceso a Docker daemon.',
          'Inicia Docker y revisa permisos del usuario.' if rc!=0 else '')
    if rc!=0: return
    rc,_,_ = compose('config','--quiet') if env else (1,'','')
    check('COMPOSE_VALID','PASS' if rc==0 else 'FAIL',
          'Compose valida contra env/.env.' if rc==0 else 'Compose no valida.',
          'Revisa compose.yaml y env/.env.' if rc else '')
    # Comprueba módulo sin intentar cargarlo; modinfo no prueba que esté cargado.
    kernel_loaded = Path('/sys/module/wireguard').exists()
    rc,_,_ = run(['modinfo','wireguard']) if shutil.which('modinfo') else (1,'','')
    check('KERNEL_WG','PASS' if kernel_loaded else ('INFO' if rc==0 else 'WARN'),
          'WireGuard cargado/disponible en kernel.' if kernel_loaded else
          ('Módulo instalado, pero no se verificó su carga.' if rc==0 else 'No se confirmó soporte de módulo WireGuard.'),
          'Si el contenedor falla: sudo modprobe wireguard; revisa kernel/headers.' if not kernel_loaded else '')
    rc, v, _ = run(['df','-Pk',str(ROOT)])
    if rc==0 and len(v.splitlines())>1:
        try:
            avail_kib = int(v.splitlines()[-1].split()[3])
            check('DISK','PASS' if avail_kib>=1024*1024 else 'WARN',
                  'Espacio disponible >=1 GiB.' if avail_kib>=1024*1024 else 'Espacio libre inferior a 1 GiB.',
                  'Libera espacio antes del pull de la imagen.' if avail_kib<1024*1024 else '')
        except (IndexError,ValueError): pass
    net=vals.get('network') if vals else None
    if net:
        conflicts=[]
        rc, routes,_=run(['ip','-j','-4','route','show']) if shutil.which('ip') else (1,'','')
        if rc==0:
            try:
                for item in json.loads(routes):
                    dst=item.get('dst','')
                    if dst and dst!='default':
                        maybe=parse_network(dst)
                        if maybe and maybe.overlaps(net): conflicts.append('host route')
            except (ValueError,TypeError): pass
        rc,ids,_=run(['docker','network','ls','-q'])
        if rc==0 and ids.strip():
            rc, raw, _ = run(['docker','network','inspect',*ids.splitlines()],timeout=20)
            if rc==0:
                try:
                    for net_item in json.loads(raw):
                        for cfg in (net_item.get('IPAM',{}).get('Config') or []):
                            subnet=cfg.get('Subnet') if cfg else None
                            if subnet:
                                candidate=parse_network(subnet)
                                if candidate and candidate.version==net.version and candidate.overlaps(net): conflicts.append('Docker network')
                except (ValueError,TypeError): pass
        check('SUBNET_OVERLAP','FAIL' if conflicts else 'PASS',
              'Red del túnel coincide con rutas/redes existentes.' if conflicts else 'No hay colisiones detectadas de subnet.',
              'Cambia INTERNAL_SUBNET por otra red libre.' if conflicts else '')
    port=vals.get('port') if vals else None
    if port and shutil.which('ss'):
        rc, ports, _ = run(['ss','-H','-lun'])
        if rc==0:
            busy = any(re.search(r':'+str(port)+r'(?=\s|$)',line) for line in ports.splitlines())
            # Si ya está nuestro contenedor, el puerto ocupado es normal.
            rc, v,_=run(['docker','inspect',SERVICE])
            owned=False
            if rc==0:
                try:
                    obj=json.loads(v)[0]
                    labels=(obj.get('Config') or {}).get('Labels') or {}
                    bindings=(obj.get('HostConfig') or {}).get('PortBindings') or {}
                    owned=(obj.get('State',{}).get('Running',False)
                           and labels.get('com.docker.compose.project')=='wireguard-auditado'
                           and any(str(b.get('HostPort'))==str(port) for entries in bindings.values() for b in (entries or [])))
                except (ValueError,IndexError,TypeError): pass
            check('PORT_AVAILABILITY','PASS' if not busy or owned else 'FAIL',
                  'Puerto UDP disponible o usado por este WireGuard.' if not busy or owned else 'Puerto UDP ocupado por otro proceso.',
                  'Cambia SERVERPORT o libera ese puerto.' if busy and not owned else '')
    # La apertura del puerto en UFW no garantiza que Docker respete el filtrado.
    check('EXTERNAL_NETWORK','INFO',
          'No se puede demostrar alcance externo, IP pública, CGNAT ni port-forward solo desde este host.',
          'En router redirige UDP al Ubuntu y prueba con celular en datos móviles.')
    if shutil.which('ufw'):
        rc, out, _ = run(['ufw','status'])
        if rc==0 and out.lower().startswith('status: active'):
            check('UFW','WARN','UFW activo: verifica explícitamente el puerto UDP publicado; Docker puede eludir reglas INPUT de UFW.',
                  'Revisa reglas DOCKER-USER y router; no se modifica firewall automáticamente.')
        else:
            check('UFW','INFO','No se confirmó filtrado de UFW; la auditoría no realiza cambios.')


def inspect_container():
    rc, raw,_ = run(['docker','inspect',SERVICE],timeout=20)
    if rc!=0:
        check('CONTAINER_PRESENT','FAIL','No existe el contenedor de este proyecto.',
              'Ejecuta ./wgctl.sh up (o ./install.sh).')
        return None
    try:
        obj=json.loads(raw)[0]
        labels=(obj.get('Config') or {}).get('Labels') or {}
        owned=(labels.get('com.docker.compose.project')=='wireguard-auditado'
               and labels.get('com.docker.compose.service')=='wireguard')
        check('CONTAINER_PROJECT','PASS' if owned else 'FAIL',
              'Contenedor pertenece a este proyecto.' if owned else 'El nombre del contenedor está ocupado por otro proyecto.')
        return obj if owned else None
    except (IndexError,ValueError,TypeError):
        check('CONTAINER_INSPECT','FAIL','Docker inspect devolvió datos inválidos.')
        return None


def runtime(env, vals, obj):
    if obj is None: return
    state=obj.get('State',{})
    running=bool(state.get('Running'))
    check('RUNNING','PASS' if running else 'FAIL',
          'Contenedor en ejecución.' if running else 'Contenedor detenido.',
          'Revisa ./wgctl.sh logs si está detenido.')
    hs=(state.get('Health') or {}).get('Status','unknown')
    check('HEALTH','PASS' if hs=='healthy' else ('INFO' if hs=='starting' else 'FAIL'),
          f'Healthcheck: {hs}.',
          'Revisa ./wgctl.sh logs y vuelve a auditar tras iniciar.' if hs not in ('healthy','starting') else '')
    if running:
        rc,interfaces,_=run(['docker','exec',SERVICE,'wg','show','interfaces'])
        active=rc==0 and 'wg0' in interfaces.split()
        check('WG_INTERFACE','PASS' if active else 'FAIL',
              'Interfaz wg0 activa.' if active else 'Interfaz wg0 no responde.',
              'Revisa logs, soporte kernel y módulos iptables.' if not active else '')
        if active:
            rc2,port,_=run(['docker','exec',SERVICE,'wg','show','wg0','listen-port'])
            correct=(rc2==0 and port.strip()=='51820')
            check('WG_LISTEN','PASS' if correct else 'FAIL',
                  'WireGuard escucha en 51820 dentro del contenedor.' if correct else 'Puerto interno WireGuard distinto de 51820.',
                  'El puerto interno debe ser 51820; SERVERPORT controla el puerto externo.' if not correct else '')
            rc4,keys,_=run(['docker','exec',SERVICE,'wg','show','wg0','peers'])
            expected_keys=[]
            for peer in vals.get('peers',[]):
                keyfile=CONFIG/f'peer_{peer}'/f'publickey-peer_{peer}'
                if keyfile.is_file(): expected_keys.append(keyfile.read_text().strip())
            matching=(rc4==0 and len(expected_keys)==len(vals.get('peers',[]))
                      and set(keys.split())==set(expected_keys))
            check('ACTIVE_PEERS','PASS' if matching else 'FAIL',
                  'Clientes activos coinciden con PEERS y sus claves locales.' if matching else 'Clientes activos no coinciden con PEERS.')
            rc3,hsraw,_=run(['docker','exec',SERVICE,'wg','show','wg0','latest-handshakes'])
            if rc3==0:
                handshakes=0
                for line in hsraw.splitlines():
                    cells=line.split()
                    if len(cells)>=2 and cells[-1].isdigit() and int(cells[-1])>0:
                        handshakes+=1
                check('HANDSHAKES','INFO',f'{handshakes} peers con handshake registrado (0 es normal antes de conectar).')
        rc,forward,_=run(['docker','exec',SERVICE,'cat','/proc/sys/net/ipv4/ip_forward'])
        check('IP_FORWARD','PASS' if rc==0 and forward.strip()=='1' else 'FAIL',
              'Reenvío IPv4 activo.' if rc==0 and forward.strip()=='1' else 'Reenvío IPv4 no confirmado.')
    active_env=dict(v.split('=',1) for v in obj.get('Config',{}).get('Env',[]) if '=' in v)
    drift=[k for k in ('PUID','PGID','TZ','SERVERURL','SERVERPORT','PEERS','PEERDNS','INTERNAL_SUBNET','ALLOWEDIPS')
           if active_env.get(k)!=env.get(k)]
    check('ENV_APPLIED','FAIL' if drift else 'PASS',
          'Configuración local coincide con el contenedor.' if not drift else 'Variables pendientes de aplicar: '+', '.join(drift),
          'Ejecuta ./wgctl.sh apply.' if drift else '')
    if CONFIG.exists():
        serverconf=CONFIG/'wg_confs'/'wg0.conf'
        check('SERVER_CONFIG','PASS' if serverconf.is_file() else 'FAIL',
              'wg0.conf generado.' if serverconf.is_file() else 'No se encuentra wg0.conf.',
              'Comprueba logs de inicialización.' if not serverconf.is_file() else '')
        peer_missing=[]
        for peer in vals.get('peers',[]):
            if not (CONFIG/f'peer_{peer}'/f'peer_{peer}.conf').is_file():
                peer_missing.append(peer)
        check('CLIENT_CONFIGS','PASS' if not peer_missing else 'FAIL',
              f'{len(vals.get("peers",[]))-len(peer_missing)} de {len(vals.get("peers",[]))} perfiles presentes.',
              'Espera inicialización o consulta ./wgctl.sh logs.' if peer_missing else '')


def security(env, vals, obj):
    check_paths()
    compose_file=(ROOT/'compose.yaml').read_text(encoding='utf8') if (ROOT/'compose.yaml').exists() else ''
    check('NOT_PRIVILEGED_STATIC','PASS' if 'privileged: true' not in compose_file else 'FAIL',
          'Compose no solicita privileged.' if 'privileged: true' not in compose_file else 'Compose solicita privileged.')
    if obj is None:
        check('RUNTIME_SECURITY','INFO','Seguridad del contenedor pendiente hasta desplegarlo.')
        return
    host=obj.get('HostConfig') or {}
    check('PRIVILEGE','PASS' if not host.get('Privileged') else 'FAIL',
          'Sin modo privileged.' if not host.get('Privileged') else 'Contenedor en modo privileged.',
          'Quita privileged y recrea solo el servicio.' if host.get('Privileged') else '')
    caps=set(host.get('CapAdd') or [])
    check('CAPABILITIES','PASS' if caps=={'NET_ADMIN'} else 'FAIL',
          'Solo NET_ADMIN como capacidad adicional.' if caps=={'NET_ADMIN'} else 'Capacidades no ajustadas.',
          'Mantén solo NET_ADMIN adicional.' if caps!={'NET_ADMIN'} else '')
    opts=host.get('SecurityOpt') or []
    nnp=any(o in ('no-new-privileges','no-new-privileges:true') for o in opts)
    check('NO_NEW_PRIVILEGES','PASS' if nnp else 'WARN',
          'No-new-privileges activo.' if nnp else 'No-new-privileges no confirmado.')
    hostmode=str(host.get('NetworkMode',''))=='host'
    check('HOST_NETWORK','PASS' if not hostmode else 'FAIL',
          'Red Docker aislada (no network_mode=host).' if not hostmode else 'Contenedor comparte red del host.')
    exposed=host.get('PortBindings') or {}
    expected='51820/udp'
    safe_ports=set(exposed)=={expected} and bool(exposed.get(expected)) and all(str(b.get('HostPort'))==str(vals.get('port'))
                            for b in exposed.get(expected,[]) if isinstance(b,dict))
    check('EXPOSED_PORTS','PASS' if safe_ports else 'FAIL',
          'Solo el puerto UDP configurado está publicado.' if safe_ports else 'Publicación de puertos distinta de la esperada.',
          'Verifica ports: solo SERVERPORT:51820/udp.' if not safe_ports else '')
    socket_mounted=False; other_mounts=[]
    config_mounts=[m for m in obj.get('Mounts',[]) if m.get('Destination')=='/config']
    valid_config=(len(config_mounts)==1 and config_mounts[0].get('Type')=='bind'
                  and config_mounts[0].get('Source')==str(CONFIG) and config_mounts[0].get('RW'))
    for mount in obj.get('Mounts',[]):
        if '/var/run/docker.sock' in (mount.get('Source',''),mount.get('Destination','')): socket_mounted=True
        if mount.get('Destination') != '/config': other_mounts.append(mount.get('Destination','desconocido'))
    mounts_ok=valid_config and not socket_mounted and not other_mounts
    check('MOUNTS','PASS' if mounts_ok else 'FAIL',
          'Solo se monta env/config en /config, sin socket Docker.' if mounts_ok else 'Montaje /config ausente, distinto o con montajes adicionales.',
          'Revisa volumes: en compose.yaml.' if not mounts_ok else '')
    envlist=obj.get('Config',{}).get('Env') or []
    lc=[v.partition('=')[2] for v in envlist if v.startswith('LOG_CONFS=')]
    check('NO_QR_LOGS','PASS' if lc==['false'] else 'FAIL',
          'QR/perfiles privados no se imprimen en logs.' if lc==['false'] else 'LOG_CONFS no está en false.',
          'Establece LOG_CONFS: "false" y recrea.' if lc!=['false'] else '')
    um=[v.partition('=')[2] for v in envlist if v.startswith('UMASK=')]
    check('UMASK','PASS' if um==['077'] else 'WARN',
          'UMASK=077.' if um==['077'] else 'No se confirmó UMASK=077.')
    restart=host.get('RestartPolicy',{}).get('Name')
    check('RESTART','PASS' if restart=='unless-stopped' else 'WARN',
          'Reinicio automático salvo parada manual.' if restart=='unless-stopped' else 'Reinicio automático no configurado.')
    logconf=host.get('LogConfig') or {}
    lgopts=logconf.get('Config') or {}
    log_ok=lgopts.get('max-size')=='5m' and lgopts.get('max-file')=='3'
    check('LOG_ROTATION','PASS' if log_ok else 'WARN',
          'Rotación de logs limitada a 3 x 5 MB.' if log_ok else 'Rotación de logs no verificada.')



def main():
    parser = argparse.ArgumentParser(description='Auditoría WireGuard Docker')
    parser.add_argument('phase', choices=['pre', 'post', 'security', 'full'])
    parser.add_argument('--fail-on-error', action='store_true')
    args = parser.parse_args()
    os.umask(0o077)
    AUDITS.mkdir(parents=True, exist_ok=True, mode=0o700)
    AUDITS.chmod(0o700)
    CHECKS.clear()
    env=env_read()
    vals=validate_env(env)
    if args.phase in ('pre','full'):
        preflight(env,vals)
    if args.phase in ('post','full'):
        if env:
            obj=inspect_container()
            runtime(env,vals or {},obj)
        else:
            check('RUNTIME','FAIL','No hay configuración local.')
    if args.phase in ('security','full'):
        obj = inspect_container() if env else None
        security(env,vals or {},obj)

    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    summary = {x:sum(c['status']==x for c in CHECKS) for x in ['PASS','WARN','FAIL','INFO']}
    report={
      'schema':'wireguard-audit-v1',
      'generated_at_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
      'phase':args.phase,
      'service':SERVICE,
      'host_os':platform.system(),
      'kernel_release':platform.release(),
      'checks':CHECKS,
      'summary':summary,
      'notice':'No se adjuntan private keys, PSK, claves de pares, perfiles o .env.'
    }
    base=AUDITS/f'{stamp}_{args.phase}'
    js=base.with_suffix('.json'); md=base.with_suffix('.md')
    js.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    md_lines=[
        f'# Auditoría WireGuard — {args.phase}',
        '',
        f'**Fecha UTC:** {report["generated_at_utc"]}',
        f'**Host:** {report["host_os"]} (kernel {report["kernel_release"]})',
        f'**Resumen:** {summary["PASS"]} PASS · {summary["WARN"]} WARN · {summary["FAIL"]} FAIL · {summary["INFO"]} INFO',
        '',
        '| Resultado | Control | Hallazgo |',
        '|---|---|---|',
    ]
    for c in CHECKS:
        msg=c['message'].replace('|','\\|').replace('\n',' ')
        md_lines.append(f'| {c["status"]} | `{c["code"]}` | {msg} |')
    md_lines.extend(['','## Recomendaciones pendientes',''])
    fixes=[c for c in CHECKS if c.get('remediation') and c['status'] in ('WARN','FAIL')]
    if fixes:
        for c in fixes:
            md_lines.append(f'- **{c["code"]} ({c["status"]})**: {c["remediation"]}')
    else:
        md_lines.append('Sin acciones técnicas prioritarias detectadas por estas verificaciones.')
    md_lines.extend(['','**Alcance:** pruebas locales, de configuración, Docker y host. No sustituye un pentest ni confirma alcanzabilidad desde Internet; no se ejecutaron pruebas de intrusión.',''])
    md.write_text('\n'.join(md_lines),encoding='utf8')
    for path in (js,md): path.chmod(0o600)
    print(f'Auditoría {args.phase}: {summary["PASS"]} PASS, {summary["WARN"]} WARN, {summary["FAIL"]} FAIL, {summary["INFO"]} INFO')
    for c in CHECKS:
        if c['status'] in ('FAIL','WARN'):
            print(f'  {c["status"]:<4} {c["code"]}: {c["message"]}')
    print(f'Informe Markdown: {md.relative_to(ROOT)}')
    print(f'Informe JSON:     {js.relative_to(ROOT)}')
    if args.fail_on_error and summary['FAIL']:
        sys.exit(2)


if __name__ == '__main__':
    main()
