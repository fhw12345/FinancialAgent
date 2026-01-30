# Kubernetes Issues & Troubleshooting

Common Kubernetes issues encountered in ACK (Alibaba Cloud) and AKS (Azure) environments with detailed resolution steps.

---

## ENV001: Test Environment (klinematrix.com) Not Accessible

### Symptoms
- Documentation references https://klinematrix.com
- Site returns connection timeout or DNS error
- Confusion about which environment to use for testing

### Root Cause
Azure AKS test environment was planned but deployment prioritized Alibaba Cloud ACK for production first. Test environment has not yet been deployed.

### Current Environment Status

| Environment | Platform | URL | Status |
|------------|----------|-----|--------|
| **Dev/Local** | Docker Compose | http://localhost:3000 | ✅ Active |
| **Test** | Azure AKS | https://klinematrix.com | ⚠️ Planned (not deployed) |
| **Production** | Alibaba ACK | https://klinecubic.cn | ✅ Active |

### Resolution

**For local development:**
```bash
make dev  # Uses docker-compose
```

**For cloud testing:**
Use the production environment: https://klinecubic.cn

**Verify production health:**
```bash
curl https://klinecubic.cn/api/health
```

### Prevention
- Always check `docs/deployment/infrastructure.md` for latest environment status
- Refer to `CLAUDE.md` environment table before deploying

---

## ARCH001: ACR Image Pull Authentication

### Symptoms
- Pods stuck in `ImagePullBackOff` status
- Error: `Failed to pull image ... unauthorized: authentication required`
- Container images not pulling from Azure Container Registry

### Root Cause
Missing or incorrect `imagePullSecrets` configuration for Azure Container Registry (ACR) authentication.

### How ACR Authentication Works

```
Pod Scheduled
  ↓
Kubelet checks spec.imagePullSecrets
  ↓
Reads acr-secret (Docker registry credentials)
  ↓
HTTPS + Basic Auth to ACR
  ↓
ACR validates credentials
  ↓
Returns image layers → Container starts
```

### Resolution Steps

#### 1. Verify Secret Exists

```bash
kubectl get secret acr-secret -n klinematrix-prod
```

If missing, create it:

```bash
kubectl create secret docker-registry acr-secret \
  --docker-server=financialagent-gxftdbbre4gtegea.azurecr.io \
  --docker-username=<ACR_USERNAME> \
  --docker-password=<ACR_PASSWORD> \
  -n klinematrix-prod
```

#### 2. Verify Deployment References Secret

```bash
kubectl get deploy backend -n klinematrix-prod -o yaml | grep imagePullSecrets
```

Should show:
```yaml
imagePullSecrets:
- name: acr-secret
```

#### 3. Test ACR Credentials Locally

```bash
docker login financialagent-gxftdbbre4gtegea.azurecr.io
# Enter credentials - should succeed
```

#### 4. Check Pod Events

```bash
kubectl describe pod <pod-name> -n klinematrix-prod | grep -A 10 Events
```

Look for image pull errors.

#### 5. Restart Deployment

```bash
kubectl rollout restart deployment/backend -n klinematrix-prod
```

### See Also
- [ACK Architecture](../deployment/ack-architecture.md#3️⃣-azure-container-registry-acr-authentication) for complete authentication flows

---

## DEPLOY001: Image Update Not Reflected After `kubectl apply`

### Symptoms
- Updated `kustomization.yaml` with new image tag
- Ran `kubectl apply -k overlays/prod/`
- Pods still running old image version
- No errors, but changes not applied

### Root Cause
In ACK (Alibaba Cloud Kubernetes), updating image tags in `kustomization.yaml` does NOT automatically trigger pod rollouts. Kubernetes only recreates pods when the **pod template** changes, not when external references change.

### Resolution

**Always run `kubectl rollout restart` after `kubectl apply`:**

```bash
# 1. Apply configuration
kubectl apply -k .pipeline/k8s/overlays/prod/

# 2. Force rollout restart (REQUIRED for ACK)
kubectl rollout restart deployment/backend deployment/frontend -n klinematrix-prod

# 3. Verify new image is running
kubectl get deploy backend -n klinematrix-prod -o jsonpath='{.spec.template.spec.containers[0].image}'
```

### Why This Happens

```yaml
# Kustomize transforms this:
images:
- name: klinematrix/backend
  newTag: "prod-v0.6.0"

# Into this in the deployment:
spec:
  template:
    spec:
      containers:
      - image: financialagent-.../backend:prod-v0.6.0

# BUT: If the image REFERENCE changes without the template hash changing,
# Kubernetes won't detect it as a pod template update.
```

### Prevention
- **Always** use `kubectl rollout restart` after `kubectl apply -k`
- Add to deployment checklist
- Consider using `imagePullPolicy: Always` for non-production environments

---

## CERT001: SSL Certificate Not Renewing

### Symptoms
- Certificate expiration warnings
- HTTPS site showing "Certificate expired" error
- Cert-Manager logs show renewal failures

### Resolution Steps

#### 1. Check Certificate Status

```bash
kubectl get certificate -n klinematrix-prod
kubectl describe certificate klinecubic-tls -n klinematrix-prod
```

#### 2. Check Cert-Manager Logs

```bash
kubectl logs -f deployment/cert-manager -n cert-manager
```

Look for ACME challenge failures.

#### 3. Verify ClusterIssuer

```bash
kubectl get clusterissuer letsencrypt-prod -o yaml
```

#### 4. Force Certificate Renewal

```bash
# Delete the secret (cert-manager will recreate)
kubectl delete secret klinecubic-tls -n klinematrix-prod

# Delete the certificate resource to trigger fresh request
kubectl delete certificate klinecubic-tls -n klinematrix-prod

# Cert-Manager will automatically recreate based on Ingress annotation
```

#### 5. Verify HTTP-01 Challenge Access

```bash
# Ensure /.well-known/acme-challenge is reachable
curl -I http://klinecubic.cn/.well-known/acme-challenge/test
```

Should return 404 (handled by cert-manager solver), not 403/500.

---

## SECRET001: Backend Secrets Not Found

### Symptoms
- Backend pods crashing with "KeyError" or "Environment variable not set"
- Logs show missing environment variables
- Deployment succeeds but pods fail to start

### Resolution Steps

#### 1. Verify Secret Exists

```bash
kubectl get secret backend-secrets -n klinematrix-prod
```

#### 2. Check Secret Keys

```bash
kubectl get secret backend-secrets -n klinematrix-prod -o jsonpath='{.data}' | jq 'keys'
```

Should include:
- `mongodb-url`
- `dashscope-api-key`
- `jwt-secret`
- `alpaca-api-key`
- `alpha-vantage-api-key`

#### 3. Verify Environment Variable Mapping

```bash
kubectl get deploy backend -n klinematrix-prod -o yaml | grep -A 5 "secretKeyRef"
```

#### 4. Recreate Secret if Missing

```bash
kubectl create secret generic backend-secrets \
  --from-literal=mongodb-url="mongodb://..." \
  --from-literal=dashscope-api-key="sk-..." \
  --from-literal=jwt-secret="..." \
  --from-literal=alpaca-api-key="..." \
  --from-literal=alpaca-secret-key="..." \
  --from-literal=alpha-vantage-api-key="..." \
  -n klinematrix-prod
```

#### 5. Restart Deployment

```bash
kubectl rollout restart deployment/backend -n klinematrix-prod
```

---

## INGRESS001: NGINX Ingress Not Routing Traffic

### Symptoms
- Cannot access application via domain (klinecubic.cn)
- Direct service access works (port-forward)
- NGINX Ingress controller pod running

### Architecture

> **Current (since 2026-01-29)**: hostNetwork nginx-ingress on node 172.22.192.247 with EIP 106.14.61.31. No SLB/LoadBalancer.
>
> **Previously**: SLB LoadBalancer with external IP 139.224.28.199 (retired after SLB deletion incident).

### Resolution Steps

#### 1. Check Ingress Status

```bash
kubectl get ingress -n klinematrix-prod
kubectl describe ingress klinematrix-ingress -n klinematrix-prod
```

Verify:
- `ingressClassName: nginx` is set
- Hosts match DNS records
- Backend services exist

#### 2. Check hostNetwork Pod on Ingress Node

```bash
# Verify nginx-ingress pod is running on the correct node
kubectl get pods -n ingress-nginx -o wide
# Expected: Pod running on node 172.22.192.247 with STATUS=Running
```

If the pod is not on the correct node:
```bash
# Check the ingress node label exists
kubectl get nodes -l ingress=true
# Should return node 172.22.192.247

# If label is missing, re-apply it
kubectl label node 172.22.192.247 ingress=true --overwrite
```

If the pod is not running:
```bash
# Check pod events for scheduling or startup errors
kubectl describe pods -n ingress-nginx -l app.kubernetes.io/component=controller
```

#### 3. Verify EIP and Port Binding

```bash
# Test that ports 80/443 are reachable on the EIP
curl -I http://106.14.61.31
curl -Ik https://106.14.61.31

# If connection refused, check if the pod has hostNetwork enabled
kubectl get pods -n ingress-nginx -o yaml | grep hostNetwork
# Should return: hostNetwork: true
```

#### 4. Check DNS Records

```bash
nslookup klinecubic.cn
dig klinecubic.cn
```

Should point to EIP `106.14.61.31`.

#### 5. Check Security Group Rules

The Alibaba Cloud security group (`sg-uf678yj45sqqry5sfjim`) must allow:
- Inbound TCP 80 (HTTP) from 0.0.0.0/0
- Inbound TCP 443 (HTTPS) from 0.0.0.0/0
- Pod CIDR rules: TCP/UDP from 10.100.0.0/16 (required for hostNetwork pod to reach cluster services)

#### 6. Test NGINX Controller Logs

```bash
kubectl logs -f -n ingress-nginx -l app.kubernetes.io/component=controller | grep klinecubic
```

Look for routing errors or 404s.

#### 7. Verify Backend Service

```bash
# Port-forward to test backend directly
kubectl port-forward svc/backend-service 8000:8000 -n klinematrix-prod
curl http://localhost:8000/api/health
```

If this works but Ingress doesn't, issue is in NGINX routing or hostNetwork connectivity.

---

## POD001: Pods in CrashLoopBackOff

### Symptoms
- Pods repeatedly restarting
- Status shows `CrashLoopBackOff`
- Application not accessible

### Resolution Steps

#### 1. Check Pod Logs

```bash
kubectl logs <pod-name> -n klinematrix-prod --previous
```

The `--previous` flag shows logs from the crashed container.

#### 2. Describe Pod for Events

```bash
kubectl describe pod <pod-name> -n klinematrix-prod
```

Look for:
- Image pull errors
- Resource limits exceeded (OOMKilled)
- Liveness/readiness probe failures

#### 3. Common Causes & Fixes

**OOMKilled (Out of Memory):**
```yaml
# Increase memory limits
resources:
  limits:
    memory: "1Gi"  # Increase from 512Mi
```

**Missing Environment Variables:**
```bash
# Check SECRET001 above
kubectl get secret backend-secrets -n klinematrix-prod
```

**Database Connection Failures:**
```bash
# Verify MongoDB is running
kubectl get pods -n klinematrix-prod | grep mongodb

# Check MongoDB logs
kubectl logs mongodb-0 -n klinematrix-prod
```

#### 4. Disable Health Checks Temporarily

```bash
# Edit deployment to comment out liveness/readinessProbe
kubectl edit deploy backend -n klinematrix-prod
```

This allows pod to start for debugging, then re-enable after fixing root cause.

---

## NODE001: Node Resource Exhaustion

### Symptoms
- Pods stuck in `Pending` status
- Events show "Insufficient cpu" or "Insufficient memory"
- Some pods running, others can't be scheduled

### Resolution Steps

#### 1. Check Node Resources

```bash
kubectl top nodes
kubectl describe nodes
```

Look for memory/CPU usage near 100%.

#### 2. Check Pod Resource Requests

```bash
kubectl top pods -n klinematrix-prod --containers
```

#### 3. Scale Down Non-Critical Workloads

```bash
# Temporarily reduce replicas
kubectl scale deployment frontend --replicas=0 -n klinematrix-prod
```

#### 4. Increase Node Pool Size (ACK)

```bash
# Via Alibaba Cloud Console
# Container Service → Clusters → Node Pools → Scale
```

Or use auto-scaling if configured.

#### 5. Evict Low-Priority Pods

```bash
# Check for non-essential pods
kubectl get pods --all-namespaces

# Delete if safe
kubectl delete pod <pod-name> -n <namespace>
```

---

