# Kubernetes local con K3s

Esta carpeta instala un clúster Kubernetes de un nodo con Docker Compose.

## Requisitos

- Linux con Docker Engine en ejecución y Docker Compose v2.
- Permiso para ejecutar Docker. K3s requiere un contenedor con `privileged: true`.

## Instalar y verificar

Ejecuta estos comandos desde esta carpeta.

```bash
docker compose up -d --wait
docker compose exec -T server kubectl wait --for=condition=Ready nodes --all --timeout=120s
docker compose exec -T server kubectl get nodes
```

El nodo `kubernetes-local` debe aparecer como `Ready`. La API escucha en
`127.0.0.1:6443`. Si el puerto está ocupado, ejecuta `export K3S_API_PORT=16443`
antes de iniciar el clúster. Usa el mismo valor cada vez que lo inicies.

## Configurar el acceso desde el anfitrión

Copia el archivo de configuración a tu directorio personal. El último comando
ajusta la dirección al puerto publicado por Compose.

```bash
install -d -m 700 "$HOME/.kube"
docker compose cp server:/etc/rancher/k3s/k3s.yaml "$HOME/.kube/kubernetes-local.yaml"
chmod 600 "$HOME/.kube/kubernetes-local.yaml"
endpoint=$(docker compose port server 6443)
sed -i "s|https://127.0.0.1:6443|https://$endpoint|" "$HOME/.kube/kubernetes-local.yaml"
```

Ese archivo da acceso administrativo al clúster. Guárdalo fuera del repositorio.

## Abrir la interfaz de terminal con K9s

Con el clúster en marcha y el archivo de configuración copiado, ejecuta los
siguientes comandos.

```bash
./install-k9s.sh
"$HOME/.local/bin/k9s" --kubeconfig "$HOME/.kube/kubernetes-local.yaml" --readonly --command nodes
```

El instalador requiere `curl` en Linux x86_64 o ARM64, verifica la descarga con
SHA-256 e instala K9s en `~/.local/bin` sin `sudo`.

Usa las flechas para navegar. Escribe `:pods` para ver los pods, `:nodes` para
volver a los nodos y presiona `Ctrl+C` para salir. [Documentación de K9s](https://k9scli.io/)

## Detener y volver a iniciar

Para detener el clúster y conservar sus datos, ejecuta `docker compose stop`.
Puedes iniciarlo de nuevo con `docker compose up -d --wait`.

[Documentación oficial de K3s en Docker](https://docs.k3s.io/advanced#running-k3s-in-docker)
