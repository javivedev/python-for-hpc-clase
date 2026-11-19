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

El contenedor incluye `kubectl`. Para usarlo desde el anfitrión, instala el
[cliente oficial de Kubernetes](https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/)
y copia el archivo de configuración a tu directorio personal.

```bash
install -d -m 700 "$HOME/.kube"
docker compose cp server:/etc/rancher/k3s/k3s.yaml "$HOME/.kube/kubernetes-local.yaml"
chmod 600 "$HOME/.kube/kubernetes-local.yaml"
kubectl --kubeconfig "$HOME/.kube/kubernetes-local.yaml" get nodes
```

Si elegiste otro puerto, actualiza el campo `server` del archivo copiado.
Ese archivo da acceso administrativo al clúster. Guárdalo fuera del repositorio.

Para detener el clúster y conservar sus datos, ejecuta `docker compose stop`.
Puedes iniciarlo de nuevo con `docker compose up -d --wait`.

[Documentación oficial de K3s en Docker](https://docs.k3s.io/advanced#running-k3s-in-docker)
