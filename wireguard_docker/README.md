# WireGuard Docker auditado — Ubuntu

Kit de instalación y operación de una **VPN WireGuard en modo servidor**, sobre Docker Compose 2.20 o superior, basado en la imagen mantenida por LinuxServer.io. Diseñado para ejecutar en Ubuntu existente **sin alterar tus otros proyectos/contenedores**. Preparado el 17 de noviembre de 2026.

> Docker aísla procesos y redes, **pero no sustituye una VM como frontera de aislamiento**: usa el kernel del host. Si necesitas aislamiento fuerte, instala Ubuntu en una VM separada y corre este mismo kit dentro de ella. Este ZIP **no clona ni crea VMs automáticamente**.

## Instalar — 2 comandos

Extrae el ZIP, entra en `WireGuard_Docker_Auditado` y ejecuta:

```bash
bash install.sh
./wgctl.sh status
```

Requisitos: Ubuntu/Linux con Docker Engine funcionando, `docker compose` 2.20 o superior, Python 3.9+ estándar, conexión para descargar la imagen y kernel con soporte WireGuard. El script **no ejecuta sudo/apt**, no modifica UFW, NAT, `/etc`, interfaces del host ni otros contenedores.

**Advertencia:** ejecutar Docker con permisos de administrador es de alto privilegio en el host. Comprueba la procedencia de los scripts antes de ejecutarlos. Si Docker no responde desde tu usuario, comprueba `docker info`; evita usar `sudo ./install.sh` sin comprender qué cambiará.

## Qué crea

```text
WireGuard_Docker_Auditado/
├── install.sh                Instalación con pre-auditoría y post-auditoría
├── wgctl.sh                  Gestor para ciclo de vida, peers, auditorías
├── audit.sh                  Atajo Bash de auditoría
├── compose.yaml              UN solo servicio WireGuard
├── env.example               Plantilla SIN secretos
├── .gitignore                Ignora /env/ completamente
├── AUDITORIAS.md             Qué se comprueba y límites
├── SEGURIDAD.md              Guía de endurecimiento y red
├── scripts/
│   ├── audit.py              Auditoría JSON/Markdown, sin dependencias
│   ├── peers.py              Edición atómica de perfiles
│   ├── selftest.sh           Autoverificación y pruebas de regresión
│   ├── smoke.sh              Prueba real con cliente temporal
│   └── audit-timer.sh        Opción de auditoría diaria (no se activa sola)
├── tests/                    Pruebas automatizadas sin dependencias
├── VALIDACION.md             Evidencia del despliegue y límites
└── env/                      TODO ESTE DIRECTORIO ESTÁ IGNORADO EN GIT
    ├── .env                  Variables locales, no subir
    ├── audits/               Históricos <UTC>_pre/post/full/security.{json,md}
    ├── config/               Claves, WG confs, perfiles QR (SECRETOS)
    ├── exports/              Perfiles exportados (SECRETOS)
    ├── revoked/              Material de peers revocados (SECRETOS)
    └── backups/              TARs con claves (SECRETOS)
```

El instalador crea `env/` y usa `0700` en directorios y `0600` en `.env`, auditorías y exportaciones. **La carpeta `env/audits/` está fuera de Git** y los reportes nunca imprimen el contenido de una clave privada.

## Comandos útiles

| Comando | Acción |
|---|---|
| `./wgctl.sh install` | Instalación inicial o repetir sin sobreescribir `.env` |
| `./wgctl.sh up` | Inicia el servicio |
| `./wgctl.sh apply` | Recrea el contenedor para aplicar cambios de `.env` |
| `./wgctl.sh down` | Detiene y elimina contenedor/red del proyecto, sin eliminar claves |
| `./wgctl.sh restart` | Reinicia contenedor existente |
| `./wgctl.sh status` | Consulta contenedor, interfaz y puerto |
| `./wgctl.sh audit` | Auditoría integral y reportes en `env/audits/` |
| `./wgctl.sh audit pre` | Comprueba requisitos y conflictos |
| `./wgctl.sh audit post` | Comprueba configuración y funcionamiento |
| `./wgctl.sh audit security` | Revisa privilegios, puertos, secretos y Git |
| `./wgctl.sh peers` | Lista perfiles generados |
| `./wgctl.sh qr android` | QR en terminal si tienes `qrencode` |
| `./wgctl.sh export laptop` | Copia perfil a `env/exports/laptop.conf` |
| `./wgctl.sh add-peer tablet` | Crea cliente y recrea **solo** este contenedor |
| `./wgctl.sh revoke-peer tablet` | Revoca cliente (deja su clave histórica en `env/revoked/`) |
| `./wgctl.sh backup` | Backup **sensible**, dentro de `env/backups/` |
| `./wgctl.sh update` | Actualiza **solo** WireGuard (no `docker system prune`) |
| `bash scripts/selftest.sh` | Sintaxis y 16 pruebas de regresión sin desplegar VPN |

## Antes de instalar: personalizar (opcional)

Por defecto `bash install.sh` crea `env/.env` automáticamente. Si quieres elegir el dominio/DDNS o añadir peers, permite que el instalador cree el archivo y **luego edítalo**:

```bash
nano env/.env
./wgctl.sh audit pre
./wgctl.sh up
```

Si **aún no** lo instalas y deseas personalizar antes de iniciar, puedes ejecutar:

```bash
mkdir -p env && chmod 700 env
cp env.example env/.env
chmod 600 env/.env
nano env/.env
bash install.sh
```

En este segundo camino, recuerda cambiar `PUID`/`PGID` a los tuyos (`id -u` / `id -g`). Valores predeterminados del ejemplo:

- `SERVERURL=auto`: el contenedor busca tu IP externa. Para servidores con IP variable, usa DDNS, por ejemplo `vpn.tudominio.com`.
- `SERVERPORT=51820`: puerto de entrada WireGuard **UDP**. Si lo cambias, el Compose publica ese mismo puerto.
- `PEERS=android,laptop`: crea dos claves y perfiles **independientes** (no reutilices clave entre equipos).
- `INTERNAL_SUBNET=10.67.47.0`: formato sin `/24`, dirección privada terminada en `.0`; red VPN `10.67.47.0/24`, independiente de las de Docker ya existentes; el preflight intenta detectar colisiones.
- `ALLOWEDIPS=0.0.0.0/0`: túnel completo de tráfico **IPv4** del cliente.
- `PEERDNS=1.1.1.1`: DNS público predeterminado del cliente. Cámbialo por tu DNS interno si lo necesitas.
- `TZ=America/Mexico_City`: zona de tiempo.

Los nombres de clientes deben empezar con una letra y continuar con letras o números; no se admite el modo de cantidad numérica de LinuxServer. El límite es de 250 clientes.

`LOG_CONFS=false` y `UMASK=077` están **fijados en Compose** por seguridad. Para el cambio de nombre o eliminación de peers utiliza `wgctl.sh` y no borres a mano el servidor `wg0.conf` (es autogenerado).

## Conectar el celular Samsung/Android

1. Instala la app oficial **WireGuard** en Android desde una fuente confiable.
2. En Ubuntu: `./wgctl.sh qr android`. Usa `qrencode` local o el incluido en el contenedor automáticamente.
3. En Android: pulsa **+ → Escanear desde código QR** y habilita la VPN.
4. Prueba **fuera del Wi-Fi doméstico**, usando datos móviles. Haz un `./wgctl.sh audit post` y revisa los handshakes.

Alternativa al QR: importa por un canal seguro `env/config/peer_android/peer_android.conf` o un perfil exportado; evita correo público, chats sin protección o capturas del QR. Tanto QR como `.conf` contienen una **clave privada de cliente**.

Para Linux/Windows/laptop: `./wgctl.sh export laptop` y luego importa `env/exports/laptop.conf` en el cliente WireGuard apropiado. Bórralo de ubicaciones compartidas cuando termines.

## Internet remoto: lo que Docker NO puede configurar

Si la PC está detrás de tu módem/router:

1. Asegura una IP LAN estable para Ubuntu (preferible reserva DHCP en el router).
2. Redirige **UDP 51820** (o `SERVERPORT`) desde tu router a **IP_LAN_UBUNTU:51820/UDP**.
3. Revisa políticas de firewall/router; **Docker puede publicar puertos aun si UFW contiene reglas que parecían bloquearlos**.
4. Si tu ISP usa **CGNAT**, el port forwarding del router puede no bastar. Solicita IP pública o usa un VPS/alternativa con relay.
5. Si usas DDNS o el IP cambia, actualiza `SERVERURL` en `env/.env` y ejecuta `./wgctl.sh apply` para regenerar los perfiles (reiniciar sin recrear no basta).
6. Realiza prueba desde **otra red** y confirma handshakes; una VPN que funciona dentro del Wi-Fi no prueba acceso remoto.

**Importante:** cambiar `SERVERURL`, `SERVERPORT`, `PEERS` o `ALLOWEDIPS` requiere **recrear el contenedor** para regenerar los perfiles. Puedes hacerlo con `./wgctl.sh apply` (ver abajo).

## Aplicar cambios de .env

```bash
./wgctl.sh apply
./wgctl.sh audit
```

## Git: los archivos sensibles no se versionan

```bash
git init
git status --short --ignored
```

La salida debe indicar `!! env/` (o la ruta relativa equivalente dentro de un repositorio mayor). Si alguien ya versionó secretos antes de añadir `.gitignore`, **.gitignore no limpia el historial**: hay que retirar los secretos del índice/historial y **rotar claves expuestas**.

## Diagnóstico rápido

- **Sin `wg0` / error module:** verifica `modinfo wireguard`; si existe, carga en el **host** con `sudo modprobe wireguard` (acción manual). Para algunos kernels quizá debas instalar módulos; no otorgamos `SYS_MODULE` al contenedor.
- **Puerto en conflicto:** `./wgctl.sh audit pre`, cambia `SERVERPORT` si es necesario y luego `./wgctl.sh apply`.
- **Handshake 0:** prueba datos móviles, router UDP, IP pública, DDNS, CGNAT, endpoint en perfil cliente.
- **Handshake existe pero sin Internet:** revisa DNS, MTU, NAT, firewall de red; usa `./wgctl.sh logs` y `./wgctl.sh audit post`.
- **Al volver a tu Wi-Fi falla:** algunos routers requieren NAT reflection/hairpin o split DNS; no es un bug de cifrado.
- **`permission denied` al leer configuraciones:** revisa permisos/propiedad de `env/config` y no hagas `chmod -R 777`.

## Referencia técnica

Documentación de la imagen LinuxServer.io (consultada el 17-11-2026):
https://docs.linuxserver.io/images/docker-wireguard/

Software y especificación WireGuard:
https://www.wireguard.com/

No se incluyen imágenes Docker ni llaves precalculadas: las genera localmente tu PC en el primer arranque.

## Correcciones y comprobación de esta versión

`SERVERPORT` configura el puerto **externo**. El mapeo correcto es `SERVERPORT:51820/udp`; WireGuard escucha siempre en `51820` dentro de esta imagen. Por ejemplo, con `SERVERPORT=51821`, el router debe enviar UDP 51821 al puerto 51821 del host. El cliente verá ese puerto en su Endpoint.

El instalador y las operaciones de arranque esperan un contenedor saludable hasta 120 segundos. Si falla el arranque o la auditoría final, devuelven un código de error. La auditoría comprueba que `wg0` existe, que están activos los clientes esperados y que el contenedor recibió el `.env` vigente. El reenvío IPv4 se activa en el namespace del contenedor.

Usa valores literales sin espacios, comillas ni interpolaciones en `env/.env`. Se detectan variables duplicadas, IDs inválidos, errores de DNS, zona horaria y redes incompatibles con el generador de la imagen.

Para repetir las pruebas sin iniciar servidores:

```bash
bash scripts/selftest.sh
```

Para probar el túnel real después de instalar:

```bash
bash scripts/smoke.sh
```

La prueba crea un cliente temporal, genera su QR, comprueba el puerto UDP publicado, el gateway VPN, DNS y HTTPS y revoca el cliente al finalizar. Recrea el servicio al agregar y quitar el cliente, por lo que las conexiones existentes se interrumpen brevemente. Usa las rutas IPv4 predeterminadas del kit y requiere salida a Internet. No modifica las rutas del host; el cliente de prueba vive en un contenedor desechable.

Para usar auditorías en automatizaciones:

```bash
./audit.sh full --fail-on-error
./wgctl.sh audit full --fail-on-error
```

El ZIP corregido y Git incluyen únicamente fuentes y documentación. `env/` permanece local e incluye los perfiles para Android/laptop; cada instalación genera sus propias claves.
