# ACK Production Architecture

Comprehensive guide to the Alibaba Cloud Container Service for Kubernetes (ACK) production environment architecture, authentication mechanisms, and operational procedures.

## Cluster Details

| Property | Value |
|----------|-------|
| **Cluster ID** | `c061af4c23eb34eb0a5d39335a2f9b10c` |
| **API Server** | `47.102.113.54:6443` |
| **Region** | Shanghai (cn-shanghai) |
| **Node IPs** | `172.22.192.247`, `172.22.192.249`, `172.22.192.250`, `172.22.192.251` |
| **Public EIP** | `106.14.61.31` (bound to node `172.22.192.247`) |
| **Security Group** | `sg-uf678yj45sqqry5sfjim` |
| **Pod CIDR** | `10.100.0.0/16` |
| **Service CIDR** | `192.168.0.0/16` |
| **Namespace** | `klinematrix-prod` |

---

## Architecture Overview

```
Internet (HTTPS/HTTP)
     |
     v
EIP 106.14.61.31 (bound to node 172.22.192.247)
     |
     v
Node:80/443 (hostNetwork nginx-ingress pod, labeled ingress=true)
     |
     v
ClusterIP Services (cluster-internal routing)
     |
     +--> klinecubic.cn/api/* --> backend-service:8000 --> Backend Pod
     |
     +--> klinecubic.cn/*     --> frontend-service:80  --> Frontend Pod
                                                            |
Backend Pod <--> MongoDB (StatefulSet)                      |
     |          Redis (Deployment)                          |
     v                                                      |
External APIs (DashScope, Alpaca, Alpha Vantage)            |
```

### Key Components

| Component | Purpose | Namespace | Access |
|-----------|---------|-----------|--------|
| **NGINX Ingress** | TLS termination, routing | `ingress-nginx` | hostNetwork on EIP node |
| **Cert-Manager** | SSL certificate management | `cert-manager` | Internal |
| **Backend** | FastAPI application | `klinematrix-prod` | Via Ingress |
| **Frontend** | React application | `klinematrix-prod` | Via Ingress |
| **MongoDB** | Database (StatefulSet) | `klinematrix-prod` | Internal |
| **Redis** | Cache (Deployment) | `klinematrix-prod` | Internal |

---

## hostNetwork Architecture (No SLB)

This cluster uses **hostNetwork mode** for the nginx-ingress controller instead of a traditional cloud load balancer (SLB). This is a deliberate cost-saving architecture choice.

### How It Works

1. **Node Labeling**: One node (`172.22.192.247`) is labeled `ingress=true`
2. **EIP Binding**: A public Elastic IP (`106.14.61.31`) is bound directly to that node
3. **hostNetwork Mode**: The nginx-ingress pod uses `hostNetwork: true`, binding directly to the node's network interface on ports 80 and 443
4. **No SLB Required**: Traffic flows directly from the internet to the node's ports, eliminating the need for a cloud load balancer

### Traffic Flow

```
Internet
  |
  v
DNS: klinecubic.cn --> 106.14.61.31 (EIP)
  |
  v
Node 172.22.192.247:80/443 (hostNetwork)
  |
  v
nginx-ingress controller (running as host process)
  |
  v
ClusterIP services (backend-service, frontend-service)
  |
  v
Application pods
```

### Cost Savings

| Architecture | Monthly Cost | Components |
|-------------|-------------|------------|
| **SLB-based** | ~$15-30/month | SLB instance + traffic fees |
| **hostNetwork** | $0 additional | EIP already required for outbound |

### Trade-offs

- **No built-in HA for ingress**: If the ingress node goes down, traffic stops (acceptable for current scale)
- **Port conflicts**: No other process can use ports 80/443 on the ingress node
- **Node affinity required**: nginx-ingress must be scheduled on the labeled node

### Security Group

The security group `sg-uf678yj45sqqry5sfjim` must allow inbound traffic on:
- Port **80** (HTTP, redirects to HTTPS)
- Port **443** (HTTPS)
- Port **6443** (Kubernetes API, restricted to admin IPs)

---

## 1. NGINX Ingress Controller

### Deployment

Installed via Helm chart with hostNetwork values files:

```bash
helm install nginx-ingress ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  -f .pipeline/helm/nginx-ingress/values.yaml \
  -f .pipeline/helm/nginx-ingress/values-prod.yaml
```

The values files configure:
- `controller.hostNetwork: true` - Binds directly to node network
- `controller.service.type: ClusterIP` - No LoadBalancer service needed
- `controller.nodeSelector.ingress: "true"` - Schedules on the EIP-bound node
- `controller.dnsPolicy: ClusterFirstWithHostNet` - Ensures DNS resolution works in hostNetwork mode

### How It Works

1. **hostNetwork Binding:**
   - nginx-ingress pod runs with `hostNetwork: true`
   - Binds directly to ports 80 and 443 on the node's network interface
   - No NodePort or LoadBalancer service required

2. **Traffic Routing:**
   ```
   Internet --> EIP:443 (HTTPS)
             --> Node:443 (hostNetwork)
             --> NGINX Ingress Pod (same network namespace as node)
             --> Backend/Frontend ClusterIP Services (HTTP internal)
   ```

3. **Routing Rules:**
   - `/api/*` --> backend-service:8000
   - `/*` --> frontend-service:80

### Ingress Configuration

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: klinematrix-ingress
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - klinecubic.cn
    secretName: klinecubic-tls
  rules:
  - host: klinecubic.cn
    http:
      paths:
      - path: /api
        backend:
          service:
            name: backend-service
            port:
              number: 8000
```

**Key Points:**
- TLS termination happens at Ingress level
- Internal cluster communication uses HTTP (secure network)
- Force SSL redirect ensures all traffic is HTTPS

---

## 2. Cert-Manager (SSL Certificate Management)

### Deployment

Installed via Helm in the `cert-manager` namespace:

```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --set installCRDs=true

# CRITICAL: Apply leader election RBAC
kubectl apply -f .pipeline/k8s/base/cert-manager/rbac.yaml
```

### Leader Election RBAC Patch

Cert-manager requires RBAC permissions for leader election using `leases` in the `coordination.k8s.io` API group. Without this patch, cert-manager pods may fail to start or experience intermittent leader election failures.

The RBAC patch (`.pipeline/k8s/base/cert-manager/rbac.yaml`) grants:
- `get`, `create`, `update`, `patch` on `leases` in `coordination.k8s.io`
- Applied to the `cert-manager` service account in the `cert-manager` namespace

**Symptoms of missing RBAC:**
- cert-manager controller pods in CrashLoopBackOff
- Logs showing `Failed to create lease` or `leases.coordination.k8s.io is forbidden`

### Automatic Certificate Workflow

1. **Certificate Request:**
   - Ingress annotation `cert-manager.io/cluster-issuer: "letsencrypt-prod"` triggers request
   - Cert-Manager creates Certificate resource

2. **ACME Challenge (HTTP-01):**
   ```
   Let's Encrypt --> HTTP request to klinecubic.cn/.well-known/acme-challenge/TOKEN
                 --> NGINX Ingress routes to cert-manager solver pod
                 --> Validation succeeds
   ```

3. **Certificate Issuance:**
   - Let's Encrypt issues certificate
   - Cert-Manager stores in Secret: `klinecubic-tls`
   - NGINX Ingress automatically uses the certificate

4. **Auto-Renewal:**
   - Cert-Manager monitors certificate expiration
   - Renews automatically 30 days before expiry
   - Zero downtime renewal

### Verification

```bash
# Check certificate status
kubectl get certificate -n klinematrix-prod

# Check certificate details
kubectl describe certificate klinecubic-tls -n klinematrix-prod

# Verify cert-manager pods
kubectl get pods -n cert-manager

# Check leader election lease
kubectl get leases -n cert-manager
```

---

## 3. CoreDNS Configuration

### Hairpin NAT Workaround

When pods inside the cluster attempt to reach `klinecubic.cn` (the public domain), traffic would normally route out to the EIP and back in. This hairpin NAT scenario can fail in hostNetwork setups.

The workaround is to add a `hosts` plugin entry in CoreDNS so that in-cluster DNS resolves `klinecubic.cn` directly to the nginx-ingress ClusterIP or the node's internal IP, bypassing the public network path entirely.

```bash
# Edit CoreDNS configmap
kubectl edit configmap coredns -n kube-system
```

Add the `hosts` block inside the Corefile to map `klinecubic.cn` to the internal service or node IP.

---

## 4. Azure Container Registry (ACR) Authentication

### Registry Details

- **Registry**: `financialagent-gxftdbbre4gtegea.azurecr.io`
- **Image Naming Convention**:
  - Test: `klinematrix/backend:test-v*`, `klinematrix/frontend:test-v*`
  - Prod: `klinecubic/backend:prod-v*`, `klinecubic/frontend:prod-v*`

### Authentication Mechanism

ACK pulls images from Azure ACR using Docker registry secrets:

#### 1. Create Docker Registry Secret (One-time setup)

```bash
kubectl create secret docker-registry acr-secret \
  --docker-server=financialagent-gxftdbbre4gtegea.azurecr.io \
  --docker-username=<ACR_USERNAME> \
  --docker-password=<ACR_PASSWORD> \
  -n klinematrix-prod
```

#### 2. Reference in Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      imagePullSecrets:
      - name: acr-secret
      containers:
      - name: backend
        image: financialagent-gxftdbbre4gtegea.azurecr.io/klinecubic/backend:prod-v0.7.0
```

#### 3. Image Pull Workflow

```
Pod scheduled
  |
Kubelet checks imagePullSecrets
  |
Reads acr-secret credentials
  |
HTTPS + Basic Auth to ACR
  |
ACR validates credentials
  |
Returns image layers
  |
Container starts
```

### Troubleshooting Image Pull

```bash
# Verify secret exists
kubectl get secret acr-secret -n klinematrix-prod

# Check deployment references secret
kubectl get deploy backend -n klinematrix-prod -o yaml | grep imagePullSecrets

# Test ACR credentials locally
docker login financialagent-gxftdbbre4gtegea.azurecr.io

# Check pod events for image pull errors
kubectl describe pod <pod-name> -n klinematrix-prod
```

---

## 5. Secrets Management

### Current Approach: Manual Kubernetes Secrets

Application secrets are manually created as Kubernetes secrets:

```bash
kubectl create secret generic backend-secrets \
  --from-literal=mongodb-url="mongodb://..." \
  --from-literal=dashscope-api-key="sk-..." \
  --from-literal=jwt-secret="..." \
  --from-literal=alpaca-api-key="..." \
  --from-literal=alpha-vantage-api-key="..." \
  -n klinematrix-prod
```

### Secret Injection

Secrets are injected as environment variables:

```yaml
containers:
- name: backend
  env:
  - name: MONGODB_URL
    valueFrom:
      secretKeyRef:
        name: backend-secrets
        key: mongodb-url
  - name: DASHSCOPE_API_KEY
    valueFrom:
      secretKeyRef:
        name: backend-secrets
        key: dashscope-api-key
```

### Planned: External Secrets Operator + Azure Key Vault

**Future integration** (not currently active):

```yaml
# Planned: Azure Key Vault --> External Secrets Operator --> K8s Secrets
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: azure-keyvault
spec:
  provider:
    azurekv:
      vaultUrl: "https://klinematrix-test-kv.vault.azure.net/"
      authType: ServicePrincipal
```

**Why not active yet:**
- Requires External Secrets Operator installation
- Cross-cloud (Azure <-> Alibaba) integration complexity
- Manual secrets management sufficient for current scale

---

## 6. Kubernetes RBAC

### Service Account

Pods run with limited permissions via `klinematrix-sa`:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: klinematrix-sa
  namespace: klinematrix-prod
```

### Permissions (Role)

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
rules:
- apiGroups: [""]
  resources: ["secrets", "configmaps"]
  verbs: ["get", "list"]  # Read-only
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["get", "list"]  # Pod inspection
```

**Key Points:**
- **Least privilege**: Pods can read secrets/configmaps but not modify
- **No cluster-wide access**: Limited to `klinematrix-prod` namespace
- **Pod introspection**: Allows health checks to query pod metadata

---

## Authentication & Communication Summary

| Component | Auth Method | Credentials Storage | Protocol |
|-----------|-------------|---------------------|----------|
| **External --> Node (EIP)** | None (public) | N/A | HTTPS |
| **NGINX (hostNetwork) --> Services** | None (cluster internal) | N/A | HTTP |
| **TLS Certificates** | ACME (Let's Encrypt) | K8s Secret (`klinecubic-tls`) | HTTPS |
| **ACR Image Pull** | Docker Registry Secret | K8s Secret (`acr-secret`) | HTTPS + Basic Auth |
| **Backend Secrets** | K8s Secrets | K8s Secret (`backend-secrets`) | In-cluster (envFrom) |
| **MongoDB** | Password Auth | Embedded in `mongodb-url` | MongoDB Wire Protocol |
| **Redis** | No Auth | N/A (internal service) | Redis Protocol |

---

## Deployment Strategy

### Backend: Recreate Strategy

The backend uses `strategy: Recreate` instead of `RollingUpdate` due to memory constraints:

```yaml
spec:
  strategy:
    type: Recreate  # Terminates old pod before starting new one
```

**Cluster Resource Context:**
- **4 nodes** (`172.22.192.247`, `.249`, `.250`, `.251`)
- Backend requests 512Mi memory
- Node `.247` also hosts nginx-ingress (hostNetwork)

**Why Recreate:**

| Strategy | Behavior | Downtime | Resource Need |
|----------|----------|----------|---------------|
| RollingUpdate | New pod starts, then old pod stops | Zero | 2x pod memory |
| Recreate | Old pod stops, then new pod starts | ~10-30s | 1x pod memory |

RollingUpdate would fail with "Insufficient memory" when both pods need to run simultaneously.

---

## Deployment Workflow

### 1. Build Images in ACR

```bash
# Get current version
BACKEND_VERSION=$(grep '^version = ' backend/pyproject.toml | sed 's/version = "\(.*\)"/\1/')

# Build in Azure Container Registry
az acr build --registry financialAgent \
  --image klinecubic/backend:prod-v${BACKEND_VERSION} \
  --file backend/Dockerfile backend/
```

### 2. Update Kustomization

Edit `.pipeline/k8s/overlays/prod/kustomization.yaml`:

```yaml
images:
- name: klinematrix/backend
  newName: financialagent-gxftdbbre4gtegea.azurecr.io/klinecubic/backend
  newTag: "prod-v0.7.0"  # <-- Update version
```

### 3. Apply Configuration

```bash
export KUBECONFIG=/Users/allenpan/.kube/config-ack-prod
kubectl apply -k .pipeline/k8s/overlays/prod/
```

### 4. Force Rollout Restart

**CRITICAL:** ACK requires explicit restart to pull new images even if tag changed:

```bash
kubectl rollout restart deployment/backend deployment/frontend -n klinematrix-prod
```

**Why this is necessary:**
- Image tag changes in `kustomization.yaml` don't auto-trigger rollouts
- Must use `kubectl rollout restart` to force pod recreation
- Pods then pull latest image with updated tag

### 5. Verify Deployment

```bash
# Check pod status
kubectl get pods -n klinematrix-prod

# Verify image version
kubectl get deploy backend -n klinematrix-prod -o jsonpath='{.spec.template.spec.containers[0].image}'

# Test health endpoint
curl https://klinecubic.cn/api/health
```

---

## Operational Commands

### Cluster Access

```bash
# Set kubeconfig for ACK
export KUBECONFIG=/Users/allenpan/.kube/config-ack-prod

# Verify connection
kubectl cluster-info
kubectl get nodes
```

### Monitoring

```bash
# Check all pods
kubectl get pods -n klinematrix-prod

# View logs
kubectl logs -f deployment/backend -n klinematrix-prod
kubectl logs -f deployment/frontend -n klinematrix-prod

# Pod resource usage
kubectl top pods -n klinematrix-prod

# Node resource usage
kubectl top nodes
```

### Debugging

```bash
# Describe pod (events, status)
kubectl describe pod <pod-name> -n klinematrix-prod

# Shell into pod
kubectl exec -it <pod-name> -n klinematrix-prod -- /bin/sh

# Port forward for local testing
kubectl port-forward svc/backend-service 8000:8000 -n klinematrix-prod
```

### Ingress & Networking

```bash
# Check ingress status
kubectl get ingress -n klinematrix-prod
kubectl describe ingress klinematrix-ingress -n klinematrix-prod

# Check NGINX Ingress controller (hostNetwork pod)
kubectl get pods -n ingress-nginx -o wide
kubectl logs -f deployment/nginx-ingress-ingress-nginx-controller -n ingress-nginx

# Verify nginx is listening on host ports
kubectl exec -n ingress-nginx deployment/nginx-ingress-ingress-nginx-controller -- ss -tlnp | grep -E ':80|:443'

# Verify node label
kubectl get nodes --show-labels | grep ingress=true
```

### Certificates

```bash
# Check certificate status
kubectl get certificate -n klinematrix-prod
kubectl describe certificate klinecubic-tls -n klinematrix-prod

# Check cert-manager leader election
kubectl get leases -n cert-manager

# Force certificate renewal
kubectl delete secret klinecubic-tls -n klinematrix-prod
# Cert-manager will automatically recreate
```

---

## Architecture Comparison: ACK vs AKS

| Aspect | ACK (Production - Active) | AKS (Test - Planned) |
|--------|---------------------------|----------------------|
| **Cloud Provider** | Alibaba Cloud | Azure |
| **Region** | Shanghai (cn-shanghai) | Korea Central (planned) |
| **Domain** | klinecubic.cn | klinematrix.com (planned) |
| **Namespace** | klinematrix-prod | klinematrix-test |
| **Image Prefix** | klinecubic/* | klinematrix/* |
| **Ingress** | hostNetwork + EIP | Azure Load Balancer (planned) |
| **Secrets Mgmt** | Manual K8s Secrets | External Secrets + AKV (planned) |
| **Node Pools** | Standard nodes | Workload identity (planned) |
| **Status** | Active | Not deployed |

---

## Related Documentation

- [Deployment Workflow](workflow.md) - Step-by-step deployment procedures
- [Infrastructure Setup](infrastructure.md) - Cloud resource provisioning
- [SLS Logging Setup](sls-logging.md) - Application log collection to Alibaba Cloud SLS
- [Kubernetes Operations](../troubleshooting/kubernetes-issues.md) - Common K8s issues and solutions
- [Environment Configuration](../CLAUDE.md) - Environment variables and settings

---

## Notes

- **Hybrid Cloud Strategy**: Azure ACR for container registry + Alibaba ACK for compute
- **hostNetwork Ingress**: No SLB cost; nginx-ingress binds directly to EIP-bound node
- **Security**: TLS everywhere external, HTTP internal (trusted network)
- **Cost Optimized**: hostNetwork mode eliminates SLB monthly fees
- **Monitoring**: Integrated with Alibaba Cloud monitoring + Langfuse for LLM observability

**Last Updated:** 2026-01-29
