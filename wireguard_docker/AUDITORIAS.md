# Sistema de auditorías

**Ubicación exacta: `env/audits/`.** Todos los archivos bajo `env/` se ignoran con la regla `/env/` de `.gitignore`. La auditoría evita escribir `.env`, claves, preshared keys, QR y perfiles en los informes. Los dos formatos por ejecución son Markdown legible y JSON estructurado.

## Fases

1. **Pre (`audit pre`)**: Linux, versiones Docker/Compose, daemon, sintaxis Compose, configuración requerida, puerto UDP, formato de peers, superposición de redes Docker/rutas del host, kernel y espacio libre. Nunca altera el host.
2. **Post (`audit post`)**: contenedor, estado de healthcheck, interfaz `wg0`, puerto en uso, presencia de `wg0.conf` y de archivos cliente; coincidencia entre clientes activos y configurados, reenvío IPv4 y cuenta de handshakes **sin incluir claves en los informes**.
3. **Security (`audit security`)**: permisos de `/env`, `.env`, y archivos de configuración, ausencia de archivos rastreados por Git, no privileged, ausencia de SYS_MODULE/ALL, red de bridge, no montaje de `docker.sock`, sólo puerto UDP esperado, `LOG_CONFS=false`, `UMASK=077`, rotación de logs y política de reinicio.
4. **Full (`audit`)**: conjunto de las tres fases anteriores.

La instalación ejecuta `pre` **antes** del despliegue y `full` **después**. `pre` bloquea la instalación si se detecta alguna condición FAIL. `post/full` siempre guardan resultados. Con `--fail-on-error`, devuelven código 2 si hay algún FAIL; el instalador y las operaciones de arranque usan esa opción y no anuncian éxito cuando falla el servicio. Se pueden ejecutar a demanda:

```bash
./wgctl.sh audit pre
./wgctl.sh audit post
./wgctl.sh audit security
./wgctl.sh audit full
bash audit.sh
```

## Significado de estados

- `PASS`: comprobación local satisfactoria.
- `WARN`: riesgo posible o verificación incompleta; requiere revisión.
- `FAIL`: falla comprobada de prerequisito/configuración detectada por la auditoría.
- `INFO`: contexto o limitación, sin declarar éxito ni falla.

## Limitaciones expresas

Estas comprobaciones no constituyen un pentest, escaneo de Internet, análisis de vulnerabilidades de código, validación criptográfica independiente o verificación real desde tu red móvil. La disponibilidad del puerto externo, NAT del ISP, bloqueos de CGNAT y filtrado efectivo en el router **no se pueden confirmar** con la auditoría local.

Los permisos `0600/0700` previenen lectura por otros usuarios ordinarios, **no** protegen frente a `root`, un Docker daemon comprometido o backups copiados fuera de `env/`. El historial Git anterior tampoco queda protegido automáticamente.

Para activar una auditoría diaria opcional por `systemd --user`:

```bash
bash scripts/audit-timer.sh install
systemctl --user list-timers '*wireguard-audit*'
```

Para desactivarla:

```bash
bash scripts/audit-timer.sh remove
```

No se activa ninguna tarea programada de forma predeterminada. Los servicios `systemd --user` dependen del inicio de sesión y de la política de linger del sistema; no se modifica linger. La auditoría diaria escribe en `env/audits/`.

Los archivos de `config/templates/` son plantillas sin claves reales y no se clasifican como secretos. La prueba con un cliente real es opcional: `bash scripts/smoke.sh`. La evidencia de esta revisión está en `VALIDACION.md`.
