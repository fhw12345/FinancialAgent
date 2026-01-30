# Production Deployment to Alibaba Cloud ACK

## Overview

Production environment deployed on Alibaba Cloud Container Service for Kubernetes (ACK) in Shanghai region with hybrid cloud architecture:
- **Compute**: ACK cluster (4 nodes)
- **Container Registry**: Azure ACR
- **Domain**: klinecubic.cn
- **TLS**: Let's Encrypt via cert-manager

## Cluster Information

- **Cluster Name**: klinecubic-financialagent
- **Region**: Shanghai (华东2)
- **Namespace**: klinematrix-prod
- **Nodes**:
  - 1× ecs.r8a.large (2c16GB, 100GB SSD)
  - 3× ecs.u1-c1m2.large (2c4GB, 40GB SSD)
- **Ingress Mode**: hostNetwork nginx-ingress (no SLB)
- **Ingress Node**: 172.22.192.247 (label: `ingress=true`)
- **Public EIP**: 106.14.61.31

> **History**: Previously used SLB LoadBalancer (IP 139.224.28.199). Migrated to hostNetwork on 2026-01-29 after SLB deletion incident.

## Pre-deployment Setup

### 1. Install Infrastructure Components

```bash
# Set kubeconfig
export KUBECONFIG=~/.kube/config-ack-prod

# Install cert-manager (v1.16.2)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml

# Install nginx-ingress in hostNetwork mode (no SLB)
# Uses values files with hostNetwork config, nodeSelector, and Alibaba Cloud mirrors
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

# Label the ingress node (node with EIP 106.14.61.31)
kubectl label node 172.22.192.247 ingress=true --overwrite

helm install nginx-ingress ingress-nginx/ingress-nginx \
  --namespace ingress-nginx --create-namespace \
  -f .pipeline/helm/nginx-ingress/values.yaml \
  -f .pipeline/helm/nginx-ingress/values-prod.yaml

# Verify nginx-ingress pod is running on the ingress node
kubectl get pods -n ingress-nginx -o wide
```

### 2. Configure DNS

Point your domain to the node EIP (hostNetwork mode, no SLB):

```
Type: A
Name: klinecubic.cn
Value: 106.14.61.31

Type: A
Name: www.klinecubic.cn
Value: 106.14.61.31

Type: A
Name: monitor.klinecubic.cn
Value: 106.14.61.31
```

> **Note**: DNS points to the EIP bound to node 172.22.192.247 where nginx-ingress runs in hostNetwork mode. Previously pointed to SLB IP 139.224.28.199 (before 2026-01-29).

### 3. Fix cert-manager DNS Resolution (ACK-specific)

ACK's CoreDNS cannot resolve external domains. Apply DNS patch:

```bash
kubectl patch deployment cert-manager -n cert-manager \
  --patch-file cert-manager-dns-patch.yaml
```

## Deployment Process

### 1. Create Namespace and RBAC

```bash
kubectl apply -f namespace.yaml
kubectl apply -f rbac.yaml
```

### 2. Create ACR Pull Secret

```bash
kubectl create secret docker-registry acr-secret \
  --docker-server=financialagent-gxftdbbre4gtegea.azurecr.io \
  --docker-username=financialAgent \
  --docker-password=<ACR_PASSWORD> \
  --namespace klinematrix-prod
```

### 3. Initialize Secrets

```bash
chmod +x init-secrets.sh
./init-secrets.sh
```

**Important**: Update placeholder values after deployment:
```bash
kubectl edit secret backend-secrets -n klinematrix-prod
# Update: dashscope-api-key, tencent-secret-id, tencent-secret-key
```

### 4. Deploy Application

```bash
# Apply all resources using Kustomize
kubectl apply -k .

# Verify deployment
kubectl get pods -n klinematrix-prod
kubectl get certificate -n klinematrix-prod
kubectl get ingress -n klinematrix-prod
```

## Key Fixes Applied

### 1. Backend Image Version
- **Issue**: v0.5.13 doesn't exist in ACR
- **Fix**: Updated kustomization.yaml to use v0.5.12
- **File**: `kustomization.yaml` line 49

### 2. Ingress Class
- **Issue**: Ingress not associated with nginx-ingress controller
- **Fix**: Added `ingressClassName: nginx` to ingress spec
- **File**: `ingress-prod-patch.yaml` line 10

### 3. MongoDB URL Encoding
- **Issue**: MongoDB password contains `/` which breaks URL parsing
- **Fix**: URL-encode password in connection string (`/` → `%2F`, `=` → `%3D`)
- **File**: `init-secrets.sh` line 24-26

### 4. cert-manager DNS Resolution
- **Issue**: ACK CoreDNS cannot resolve external domains
- **Fix**: Configure cert-manager to use Google DNS (8.8.8.8)
- **File**: `cert-manager-dns-patch.yaml`

## Verification

### Check All Services

```bash
# Pods
kubectl get pods -n klinematrix-prod
# Expected: backend, frontend, mongodb, redis all Running

# Ingress controller (hostNetwork mode)
kubectl get pods -n ingress-nginx -o wide
# Expected: Pod running on node 172.22.192.247 with hostNetwork

# Certificate
kubectl get certificate -n klinematrix-prod
# Expected: klinecubic-tls READY=True

# Ingress
kubectl get ingress -n klinematrix-prod
# Expected: PORTS=80,443 (ADDRESS may be empty in hostNetwork mode - this is normal)
```

### Test Endpoints

```bash
# Frontend
curl -I https://klinecubic.cn

# Backend API
curl https://klinecubic.cn/api/health

# Certificate details
kubectl get secret klinecubic-tls -n klinematrix-prod -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -text
```

## Storage Configuration

- **MongoDB**: 10Gi emptyDir (ephemeral, cost-free)
- **Redis**: In-memory only
- **Tradeoff**: Data lost on pod restart (acceptable for Phase 1 testing)

## Cost Optimization

- Using existing node SSDs via emptyDir: **$0 additional cost**
- Cross-cloud image pulls: Within ACR free tier (<100GB/month)
- No SLB cost: hostNetwork mode eliminates LoadBalancer fees (previously slb.s1.small)

## Troubleshooting

### Certificate Not Issuing

```bash
# Check certificate status
kubectl describe certificate klinecubic-tls -n klinematrix-prod

# Check challenges
kubectl get challenges -n klinematrix-prod

# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager
```

### 404 Not Found

Verify ingress class is set:
```bash
kubectl get ingress klinematrix-ingress -n klinematrix-prod -o jsonpath='{.spec.ingressClassName}'
# Should return: nginx
```

### Backend Crashes

Check MongoDB connection:
```bash
kubectl logs -n klinematrix-prod deployment/backend --tail=50
# Look for "MongoDB connection established"
```

## Rollback

```bash
# Rollback deployment
kubectl rollout undo deployment/backend -n klinematrix-prod
kubectl rollout undo deployment/frontend -n klinematrix-prod

# Or delete and redeploy
kubectl delete -k .
kubectl apply -k .
```

## Future Improvements

1. **Persistent Storage**: Migrate from emptyDir to Alibaba Cloud Disk
2. **Azure Key Vault**: Enable External Secrets Operator integration
3. **Monitoring**: Add Prometheus/Grafana
4. **Backup**: Implement MongoDB backup strategy
5. **Autoscaling**: Configure HPA based on CPU/memory
