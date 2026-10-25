# Kubernetes Deployment and Networking Lab

A small multi-service application for practicing Kubernetes Deployments,
Services, namespaces, service discovery, and internal versus external
connectivity. It is a working movie-voting app: submit a vote, then view the
vote totals through the results API. The app provides a practical workload for
learning how Kubernetes components are deployed and communicate inside a
cluster.

## Kubernetes concepts practiced

- **Deployments and replicas:** run the API servers, background worker, Redis,
  and PostgreSQL as independently managed workloads.
- **ClusterIP Services and DNS:** expose Redis and PostgreSQL only inside the
  cluster; applications connect using the `redis` and `postgres` service names.
- **NodePort Services:** expose the voting and results APIs outside the cluster
  on ports `30080` and `30081`.
- **Namespaces:** group resources in a namespace of your choice. The manifests
  omit `metadata.namespace`, so specify your namespace when applying them.
- **Application connectivity:** voting API -> Redis Stream -> worker ->
  PostgreSQL -> results API.

## Architecture

| Workload | Responsibility | Kubernetes Service |
| --- | --- | --- |
| `voting-app` | Accepts a vote through FastAPI | `voting-api` — NodePort `30080` |
| `redis-deployment` | Queues votes in a Redis Stream | `redis` — ClusterIP `6379` |
| `vote-worker` | Reads queued votes and stores them in PostgreSQL | None; outbound connections only |
| `db-deployment` | Stores votes in PostgreSQL | `postgres` — ClusterIP `5432` |
| `result-app` | Returns vote totals through FastAPI | `results-api` — NodePort `30081` |

The API docs are available at `/docs`. Redis and PostgreSQL are not exposed
outside the cluster.

## Setup

Prerequisites: Docker, a running Kubernetes cluster, and `kubectl` configured
to use that cluster. The example image names below use the Docker Hub account
currently configured in the manifests; replace them with your own account if
needed and update the image references in the Deployments.

From the project root, build and push the application images:

```powershell
docker build -t sameerchavan31/movie-voting-api:v1 .\voting-api\
docker build -t sameerchavan31/movie-result-api:v1 .\results-api\
docker build -t sameerchavan31/movie-vote-worker:v2 .\worker\

docker push sameerchavan31/movie-voting-api:v1
docker push sameerchavan31/movie-result-api:v1
docker push sameerchavan31/movie-vote-worker:v2
```

Choose a namespace name and set it in PowerShell. The commands below use
`<namespace>` as a placeholder; replace it with your chosen name:

```powershell
$NAMESPACE = "<namespace>"
kubectl create namespace $NAMESPACE
kubectl apply -n $NAMESPACE -f .\deployments\
kubectl apply -n $NAMESPACE -f .\services\
kubectl get deployments,pods,services -n $NAMESPACE
```

Replace `<namespace>` with a valid namespace name before running these
commands. If that namespace already exists, skip `kubectl create namespace`.
Wait for all Deployments to become ready before testing.

## Test connectivity

Open the API documentation:

- Voting API: `http://localhost:30080/docs`
- Results API: `http://localhost:30081/docs`

Or use PowerShell to submit a vote and fetch the totals:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:30080/votes `
  -ContentType "application/json" `
  -Body '{"choice":"Dune 3"}'

Invoke-RestMethod -Uri http://localhost:30081/results
```

Votes are processed asynchronously, so wait briefly before checking results.
Inspect workload status and worker logs with:

```powershell
kubectl get pods,services -n $NAMESPACE
kubectl logs -f deployment/vote-worker -n $NAMESPACE
```

## Learning extensions

- Split the workloads across namespaces and use fully qualified Service DNS
  names for cross-namespace communication.
- Replace NodePorts with Ingress or use `kubectl port-forward`.
- Move database credentials into Kubernetes Secrets.
- Add persistent storage for PostgreSQL and health probes for the workloads.

This is a learning project, not a production deployment. It uses demo database
credentials and does not configure persistent storage.
