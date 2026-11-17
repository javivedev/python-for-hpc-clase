# Seguridad operativa

## Alcance y decisiones

- Se publica únicamente un puerto **UDP** para WireGuard. No se añade panel web ni una API administrativa expuesta.
- Se usa **NET_ADMIN** y reenvío IPv4 en el namespace de red del contenedor. No `privileged` ni `SYS_MODULE`; el módulo WireGuard debe existir/cargarse en el kernel host.
- Se añade `no-new-privileges`, rotación de logs (tres archivos de 5 MB) y `LOG_CONFS=false` para no imprimir códigos QR en los logs.
- Se generan claves distintas por dispositivo y se guardan en `env/config/` con `UMASK=077`.
- `docker compose` usa un proyecto independiente; no se alteran puertos/configuración de FastAPI, Streamlit, Postgres, MinIO, Nginx u otros contenedores.
- El perfil `ALLOWEDIPS=0.0.0.0/0` en el cliente cifra y envía su tráfico IPv4 por VPN; **no es un mecanismo de segregación de acceso a la LAN**. Si los clientes son no confiables, necesitas reglas adicionales de firewall entre la interfaz WireGuard y tus redes/servicios.
- Docker comparte kernel con el host. Para aislamiento fuerte separa la VPN en una VM/host distinto y aplica controles de firewall de red.
- `latest` recibe cambios de imagen cuando ejecutas `update`; haz backup protegido y revisa los reportes. Para reproducibilidad de producción, cambia el tag por versión/digest validado antes de desplegar.

## Consideraciones importantes

1. **Claves**: nunca agregues a Git `env/.env`, `env/config`, `env/exports`, `env/revoked`, `env/backups` o `env/audits`. El patrón `/env/` cubre todos.
2. **Enrutamiento**: el cliente puede llegar al equipo host o a servicios que su política de red permita; controla la exposición con el firewall de LAN/router y reglas adecuadas de Docker, sin modificar automáticamente `DOCKER-USER`.
3. **Acceso remoto**: valida doble NAT/CGNAT e IP de origen; el script no puede abrir puertos en tu router.
4. **Revocación**: `revoke-peer` quita su peer de la configuración activa, recrea el servicio y conserva un archivo histórico de su clave en `env/revoked`; valida luego que ya no puede establecer handshake. No confundas archivo local presente con acceso válido.
5. **Backups**: contienen las claves del servidor y de los clientes y requieren almacenamiento cifrado y controlado. El script de respaldo no cifra automáticamente los TAR.
6. **Auditorías**: sólo inspeccionan; no hacen cambios ni reproducen llaves. Revisa el reporte `full` tras actualizar o agregar peers.
7. **Logs**: aunque no se impriman códigos QR, evita compartir públicamente logs sin revisarlos. Pueden contener metadatos de red.
8. **DNS**: `1.1.1.1` es DNS público de Cloudflare. Si buscas resolver nombres de una LAN interna, configura tu propio DNS accesible desde la VPN.
9. **IPv6**: el kit configura túnel completo **IPv4** por defecto y no anuncia `::/0`. El tráfico IPv6 del cliente podría continuar fuera del túnel dependiendo de sistema/cliente; configura y prueba IPv6 por separado si necesitas evitar esa fuga.

## Buenas prácticas

Usa perfiles diferentes para cada dispositivo; mantén Ubuntu, Docker y clientes actualizados; usa claves sólo en clientes confiables; prueba desde datos móviles; ejecuta auditorías regularmente y documenta cualquier excepción. Considera un VPS si el servidor de tu casa/empresa opera tras CGNAT.

El contenedor espera UDP 51820 internamente; el puerto externo se controla mediante `SERVERPORT`. El ZIP distribuible excluye por completo `env/`, incluidos backups, auditorías y perfiles revocados.
