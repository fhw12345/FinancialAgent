# nginx-ingress Helm Deployment

## Overview

nginx-ingress controller for **klinecubic-financialagent** ACK cluster in Alibaba Cloud (cn-shanghai).

**Chart**: `ingress-nginx/ingress-nginx` v4.14.0
**App Version**: 1.14.0
**Mode**: hostNetwork (no SLB/LoadBalancer)
**Public EIP**: 106.14.61.31 (bound to node 172.22.192.247)

> **History**: Previously used SLB LoadBalancer (IP 139.224.28.199). Migrated to hostNetwork mode on 2026-01-29 after SLB deletion incident. See [ACK Cluster Recovery](../../../docs/recovery/ack-cluster-recovery-2026-01-29.md).

## Deployment

### Prerequisites

```bash
# Add Helm repo
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update

# Configure kubectl for ACK cluster
export KUBECONFIG=/Users/allenpan/.kube/config-ack-prod
```

### Initial Installation

```bash
cd /Users/allenpan/Desktop/repos/projects/financial_agent

helm install nginx-ingress ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --create-namespace \
  --values .pipeline/helm/nginx-ingress/values.yaml \
  --values .pipeline/helm/nginx-ingress/values-prod.yaml
```

### Upgrade Existing Installation

```bash
export KUBECONFIG=/Users/allenpan/.kube/config-ack-prod

helm upgrade nginx-ingress ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --values .pipeline/helm/nginx-ingress/values.yaml \
  --values .pipeline/helm/nginx-ingress/values-prod.yaml
```

### Verify Deployment

```bash
# Check pods are running on the ingress node (hostNetwork mode)
kubectl get pods -n ingress-nginx -o wide
# Expected: Pod running on node 172.22.192.247 with hostNetwork

# Verify the controller is listening on the node
kubectl exec -n ingress-nginx -it $(kubectl get pods -n ingress-nginx -l app.kubernetes.io/component=controller -o name) -- curl -s http://localhost:80

# Test external access via EIP
curl -I http://106.14.61.31
```

## Configuration

### Files Structure

```
.pipeline/helm/nginx-ingress/
├── values.yaml          # Base configuration (all environments)
├── values-prod.yaml     # Production overrides
└── README.md           # This file
```

### Key Configuration Decisions

#### 1. hostNetwork Mode (No SLB/LoadBalancer)

**Architecture:**
```yaml
controller:
  hostNetwork: true
  dnsPolicy: ClusterFirstWithHostNet
  nodeSelector:
    ingress: "true"   # Targets node with EIP 106.14.61.31
  service:
    type: ClusterIP   # No LoadBalancer needed
```

**Reason**: After the SLB deletion incident on 2026-01-29, the cluster was recovered using hostNetwork mode. The nginx-ingress controller runs directly on the node's network stack, binding to ports 80/443 on the node with a static EIP.

**How it works**:
1. Node `172.22.192.247` is labeled `ingress=true` and has EIP `106.14.61.31`
2. nginx-ingress pod is scheduled to this node via `nodeSelector`
3. With `hostNetwork: true`, the pod binds directly to the node's ports 80/443
4. DNS records point `klinecubic.cn` to the EIP `106.14.61.31`
5. No SLB/LoadBalancer service is needed

**Impact**:
- ✅ No dependency on Alibaba Cloud SLB
- ✅ Simpler architecture, fewer moving parts
- ✅ Direct traffic path (no extra hop through SLB)
- ⚠️ Single-node ingress (acceptable for current scale)

> **Previously** (before 2026-01-29): Used SLB LoadBalancer with external IP 139.224.28.199. Removed annotation `service.beta.kubernetes.io/alibaba-cloud-loadbalancer-spec` due to CLB mismatch error.

#### 2. Admission Webhooks Disabled

**Configuration:**
```yaml
controller:
  admissionWebhooks:
    enabled: false
```

**Reason**: Image pull failures due to SHA digest not available in Alibaba Cloud registry:
```
registry.cn-hangzhou.aliyuncs.com/google_containers/kube-webhook-certgen:v1.6.4@sha256:bcfc926e...
```

**Impact**:
- ✅ No ImagePullBackOff errors
- ✅ Clean pod status
- ℹ️ Admission webhook is optional - ingress controller works fine without it

#### 3. Alibaba Cloud Registry

**Configuration:**
```yaml
controller:
  image:
    registry: registry.cn-hangzhou.aliyuncs.com
    image: google_containers/nginx-ingress-controller
    tag: v1.9.4
    digest: ""  # No SHA digest
```

**Benefits**:
- Faster image pulls from China region
- Avoid Docker Hub rate limits
- Use mirrored images

## Troubleshooting

### Cleanup Old Webhook Job

If old admission webhook job exists from previous deployment:

```bash
kubectl delete job nginx-ingress-ingress-nginx-admission-create -n ingress-nginx
```

### Check Helm Values

```bash
helm get values nginx-ingress -n ingress-nginx
```

### Check hostNetwork Pod Status

```bash
# Verify pod is on the correct node with hostNetwork
kubectl get pods -n ingress-nginx -o wide
# Expected: Running on node 172.22.192.247

# Check the node has the ingress label
kubectl get nodes -l ingress=true
```

### Rollback

```bash
# List revisions
helm history nginx-ingress -n ingress-nginx

# Rollback to previous revision
helm rollback nginx-ingress <revision> -n ingress-nginx
```

## Changelog

### 2026-01-29: Migrate to hostNetwork Mode (No SLB)

**Reason**: SLB deletion incident required cluster recovery with simplified architecture.

**Changes:**
- Switched from `LoadBalancer` service type to `hostNetwork: true` with `ClusterIP` service
- Added `nodeSelector: ingress: "true"` to target EIP-bound node
- Set `dnsPolicy: ClusterFirstWithHostNet`
- Updated DNS records from old SLB IP (139.224.28.199) to node EIP (106.14.61.31)

**Result:**
- ✅ No SLB dependency
- ✅ Direct traffic routing via node EIP
- ✅ All services accessible via klinecubic.cn

### 2025-11-13: Fix LoadBalancer Annotation Mismatch + Webhook Issues

**Issues Fixed:**
1. ❌ LoadBalancer annotation `slb.s1.small` didn't match actual CLB configuration
2. ❌ nginx-ingress-admission-create pod stuck in ImagePullBackOff

**Changes:**
- Removed `service.beta.kubernetes.io/alibaba-cloud-loadbalancer-spec` annotation
- Disabled admission webhooks (`controller.admissionWebhooks.enabled: false`)
- Added production HA configuration (2 replicas, pod anti-affinity)
- Created git-tracked Helm values for reproducible deployments

**Result:**
- ✅ ACK console warnings cleared
- ✅ All pods healthy
- ✅ External IP unchanged (139.224.28.199)
- ✅ Zero downtime deployment

> **Note**: This SLB-based configuration was superseded by the 2026-01-29 hostNetwork migration.

## Maintenance

### Upgrade nginx-ingress Chart Version

```bash
# Check available versions
helm search repo ingress-nginx/ingress-nginx --versions

# Upgrade to specific version
helm upgrade nginx-ingress ingress-nginx/ingress-nginx \
  --namespace ingress-nginx \
  --version <chart-version> \
  --values .pipeline/helm/nginx-ingress/values.yaml \
  --values .pipeline/helm/nginx-ingress/values-prod.yaml
```

### Monitor Controller Logs

```bash
kubectl logs -f -n ingress-nginx \
  -l app.kubernetes.io/component=controller
```

## References

- [nginx-ingress Helm Chart](https://github.com/kubernetes/ingress-nginx/tree/main/charts/ingress-nginx)
- [ACK Cluster Recovery (2026-01-29)](../../../docs/recovery/ack-cluster-recovery-2026-01-29.md)
- [Alibaba Cloud Registry Mirror](https://help.aliyun.com/document_detail/60750.html)
