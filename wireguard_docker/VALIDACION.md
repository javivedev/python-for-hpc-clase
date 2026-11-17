# Validación del kit corregido

Fecha: 17 de noviembre de 2026. Despliegue en Linux con Docker Engine 29.1.3 y Docker Compose 5.1.3.

## Resultados comprobados

| Prueba | Resultado |
|---|---|
| Sintaxis de todos los scripts Bash y compilación Python | PASS |
| 16 pruebas de regresión con unittest, sin dependencias adicionales | PASS |
| Validación de Compose con variables locales | PASS |
| Inicio real de `wg_auditado_vpn` y healthcheck | PASS: healthy |
| Interfaz `wg0` y reenvío IPv4 del contenedor | PASS |
| Perfiles independientes Android y laptop | PASS |
| Cliente desechable: túnel cifrado y ping al gateway VPN | PASS: 3/3 respuestas |
| Cliente desechable: ping a Internet IPv4 | PASS: 3/3 respuestas |
| Consulta DNS y HTTPS a través del túnel | PASS |
| Acceso mediante el puerto UDP publicado del host, 51820 | PASS |
| Puerto alternativo externo 51821, con puerto interno 51820 | PASS |
| Alta de cliente de diagnóstico y generación de QR PNG | PASS |
| Exclusión de la clave del cliente revocado en el servidor | PASS |
| Intento real con perfil revocado: sin handshake ni acceso VPN | PASS |
| Exportación del perfil y backup TAR con permisos restrictivos | PASS |

Imagen probada: `lscr.io/linuxserver/wireguard:latest`, versión LinuxServer `1.0.20260223-r0-ls130`, compilación del 12 de noviembre de 2026. Digest descargado:

```text
sha256:10db56ad834f94541307d5dfdbe87370e26d155bb341a5bf65789f970f24ab5c
```

Al finalizar se restauró el puerto externo 51820 y quedaron solamente los clientes Android y laptop. Las claves, los perfiles, backups y reportes locales están bajo `env/` y quedan excluidos de Git y del ZIP distribuible.

## Alcance de las pruebas

El servidor y los clientes de prueba corrieron en contenedores con namespaces separados. Se comprobaron conexión cifrada, publicación UDP, NAT del contenedor y salida a Internet. Estas pruebas locales no demuestran acceso desde una red móvil o desde Internet a través del router del usuario. El port forwarding y CGNAT siguen dependiendo de esa red.

El entorno de automatización restringe el acceso al socket Docker desde los scripts locales. Por eso se ejecutaron las operaciones reales mediante comandos Docker autorizados y se validaron por separado las rutinas de auditoría con pruebas de regresión. No se afirma que una auditoría `full` del instalador haya aprobado en este entorno. En una terminal con acceso normal al daemon se puede ejecutar:

```bash
./wgctl.sh audit full --fail-on-error
bash scripts/smoke.sh
```

La prueba smoke automatiza el alta, QR, túnel, DNS, HTTPS y limpieza de un cliente temporal. La auditoría diaria es opcional; no se activó ningún timer durante esta revisión.

## Correcciones principales

- Mapeo de puertos compatible con LinuxServer: `SERVERPORT:51820/udp`.
- Reenvío IPv4 explícito dentro del contenedor.
- Arranque con espera de healthcheck y propagación de errores.
- Detección de interfaz realmente presente, salud, clientes activos y variables pendientes de aplicar.
- Validación de nombres, capacidad de clientes, IDs, red, DNS, zona horaria y sintaxis del `.env`.
- Plantillas sin claves excluidas del conteo de secretos; perfiles generados sí se revisan.
- QR disponible mediante el binario incluido en el contenedor, además del binario local.
- Archivado de exportaciones locales al revocar un cliente.
- Timer con rutas entrecomilladas y salida de error ante fallas de auditoría.
- Pruebas reproducibles y paquete sin datos privados.
