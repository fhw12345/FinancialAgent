# Secrets Management Architecture

## Overview

This document explains how secrets are managed across our hybrid-cloud architecture (Azure AKS for Test, Alibaba ACK for Production).

## Architecture Summary

### Test Environment (Azure AKS)
- **Cloud Provider**: Azure (West US)
- **Cluster**: `financialagent-cluster`
- **Secrets Method**: External Secrets Operator + Azure Key Vault
- **Authentication**: Azure Workload Identity (Federated Credentials)
- **Status**: ✅ Fully automated secret synchronization

### Production Environment (Alibaba ACK)
- **Cloud Provider**: Alibaba Cloud (cn-shanghai)
- **Cluster**: `klinecubic-financialagent` (ID: `c061af4c23eb34eb0a5d39335a2f9b10c`)
- **Secrets Method**: Manual `kubectl` secret creation
- **Authentication**: N/A (no External Secrets Operator)
- **Status**: ⚠️ Manual secret management
- **Last Updated**: 2026-01-29 (cluster recovery)

## How Test Environment Works

### 1. Azure Workload Identity Setup

ServiceAccount with Azure annotations:

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: klinematrix-sa
  annotations:
    azure.workload.identity/client-id: "03e41e5f-f062-45b2-9094-367e406c30a6"
    azure.workload.identity/tenant-id: "5cf107ca-3264-4ffd-ac28-4bc356e2f23f"
```

### 2. External Secrets Operator Flow

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│ Azure Key Vault │ ←────│ External Secrets │ ────→│ K8s Secret      │
│                 │      │ Operator (ESO)   │      │ (auto-created)  │
└─────────────────┘      └──────────────────┘      └─────────────────┘
         ↑                        ↑
         │                        │
    Azure AD                 Workload
    Identity                 Identity
```

**Configuration**:

```yaml
# SecretStore - defines HOW to connect to Azure Key Vault
apiVersion: external-secrets.io/v1
kind: SecretStore
metadata:
  name: azure-keyvault-store
spec:
  provider:
    azurekv:
      authType: WorkloadIdentity  # Uses ServiceAccount annotations
      vaultUrl: "https://klinematrix-test-kv.vault.azure.net"
      serviceAccountRef:
        name: klinematrix-sa  # References the annotated SA above

---
# ExternalSecret - defines WHAT secrets to sync
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: app-secrets
spec:
  refreshInterval: 1h  # Sync every hour
  secretStoreRef:
    name: azure-keyvault-store
  target:
    name: app-secrets  # Kubernetes secret that will be created
  data:
  - secretKey: jwt-secret-key
    remoteRef:
      key: jwt-secret-key-test  # Key name in Azure Key Vault
  - secretKey: dashscope-api-key
    remoteRef:
      key: alibaba-dashscope-api-key-test
```

### 3. Automatic Synchronization

- ESO polls Azure Key Vault every 1 hour (`refreshInterval`)
- Creates/updates Kubernetes secrets automatically
- No manual `kubectl` commands needed
- Secrets rotated in Azure Key Vault are automatically synced to pods

## Why Production Doesn't Use External Secrets

### Challenge: Cross-Cloud Authentication

```
┌──────────────────┐       ❌        ┌─────────────────┐
│ Alibaba ACK      │  ←────────────→ │ Azure Key Vault │
│ (China Mainland) │   Can't use     │ (West US)       │
│                  │   Workload      │                 │
│                  │   Identity      │                 │
└──────────────────┘                 └─────────────────┘
```

**Reasons**:

1. **No Azure Workload Identity**: ACK doesn't have Azure's federated identity system
2. **Alternative Auth Methods**:
   - Service Principal (less secure, requires rotating secrets IN secrets)
   - Managed Identity (only works within Azure)
3. **Network Latency**: Cross-region sync from China to US Azure regions
4. **Operational Complexity**: Not worth it for small production environment

### Current Production Approach

**Manual secret creation**:

```bash
# Create secret from literal values
export KUBECONFIG=/Users/allenpan/.kube/config-ack-prod
kubectl create secret generic backend-secrets \
  --from-literal=jwt-secret=<value> \
  --from-literal=dashscope-api-key=<value> \
  --from-literal=alpha-vantage-api-key=<value> \
  -n klinematrix-prod

# Or patch existing secret to add new key
kubectl patch secret backend-secrets -n klinematrix-prod \
  --type='json' \
  -p='[{"op": "add", "path": "/data/alpha-vantage-api-key", "value": "<base64-value>"}]'
```

## Secret References in Code

Both environments reference secrets the same way in deployments:

```yaml
env:
- name: ALPHA_VANTAGE_API_KEY
  valueFrom:
    secretKeyRef:
      name: backend-secrets  # Same secret name in both environments
      key: alpha-vantage-api-key  # Same key name
```

**The difference is HOW the secret gets created**:
- **Test**: External Secrets Operator creates `backend-secrets` automatically
- **Prod**: Manual `kubectl` command creates `backend-secrets`

## Secrets Inventory

### Shared Azure Key Vault Secrets

All secrets stored in: `klinematrix-test-kv` (West US)

| Secret Name in KV | Environment | Purpose |
|-------------------|-------------|---------|
| `jwt-secret-key-test` | Test | JWT signing key |
| `alibaba-dashscope-api-key-test` | Test | Qwen LLM API |
| `mongodb-connection-string-test` | Test | Database URL |
| `alpaca-api-key-test` | Test | Market data |
| `alpaca-secret-key-test` | Test | Market data |
| `alpha-vantage-api-key-prod` | Prod | Market data (stored in AKV but manually copied to ACK) |

### Production Kubernetes Secrets

Secrets in `klinematrix-prod` namespace (Alibaba ACK):

| K8s Secret Name | Keys | Source |
|-----------------|------|--------|
| `backend-secrets` | `jwt-secret`<br>`dashscope-api-key`<br>`mongodb-url`<br>`alpaca-api-key`<br>`alpaca-secret-key`<br>`alpha-vantage-api-key`<br>`oss-access-key`<br>`oss-secret-key`<br>`admin-secret`<br>`tencent-secret-id`<br>`tencent-secret-key`<br>`langfuse-public-key`<br>`langfuse-secret-key` | Manual kubectl |
| `langfuse-secrets` | `postgres-password`<br>`clickhouse-password`<br>`nextauth-secret`<br>`salt`<br>`oss-access-key-id`<br>`oss-access-key-secret` | Manual kubectl |
| `redis-auth` | `password` | Base kustomize |
| `acr-secret` | Docker registry credentials for Azure ACR | Manual kubectl |

> **⚠️ CRITICAL: ClickHouse Password Constraint**
>
> The `clickhouse-password` in `langfuse-secrets` must **NOT** contain URL-special characters (`+`, `@`, `/`, `=`, `%`, `#`, `?`). This password is embedded in a `clickhouse://` URL (`CLICKHOUSE_MIGRATION_URL`), and the Go clickhouse driver's URL parser corrupts these characters. Use only alphanumeric passwords.
>
> **Generate safe passwords**: `openssl rand -hex 16`
>
> See: [ACK Recovery 2026-01-29](../recovery/ack-cluster-recovery-2026-01-29.md)

### Langfuse API Keys (Backend Integration)

After deploying Langfuse, generate API keys from the Langfuse UI:
1. Access https://monitor.klinecubic.cn
2. Create account (first user becomes admin)
3. Navigate to Settings -> API Keys
4. Create new API key pair
5. Add to backend-secrets:

```bash
export KUBECONFIG=~/.kube/config-ack-prod
# Encode keys
PUBLIC_KEY_B64=$(echo -n 'pk-lf-YOUR-PUBLIC-KEY' | base64)
SECRET_KEY_B64=$(echo -n 'sk-lf-YOUR-SECRET-KEY' | base64)

# Patch secret
kubectl patch secret backend-secrets -n klinematrix-prod --type='json' \
  -p="[{\"op\": \"add\", \"path\": \"/data/langfuse-public-key\", \"value\": \"$PUBLIC_KEY_B64\"},{\"op\": \"add\", \"path\": \"/data/langfuse-secret-key\", \"value\": \"$SECRET_KEY_B64\"}]"
```

## Future Improvements

### Option 1: Alibaba Cloud Secrets Manager

Replace Azure Key Vault with Alibaba Cloud Secrets Manager for production:

```
Production: Alibaba KMS → ACK (native integration)
Test: Azure Key Vault → AKS (External Secrets)
```

**Pros**: Native integration, lower latency
**Cons**: Two secret stores to manage

### Option 2: HashiCorp Vault

Use Vault as centralized secret store for both environments:

```
Both: HashiCorp Vault → K8s (Vault Agent Injector)
```

**Pros**: Single source of truth, advanced features
**Cons**: Additional infrastructure to maintain

### Option 3: Keep Manual (Current)

Continue manual secret management in production.

**Pros**: Simple, no dependencies
**Cons**: Manual rotation, human error risk

## Security Best Practices

### Secrets Rotation

**Test Environment**:
1. Update secret value in Azure Key Vault
2. Wait up to 1 hour (or restart ESO pods to force sync)
3. Restart affected pods to pick up new secret

**Production Environment**:
1. Update secret in local password manager
2. Base64 encode: `echo -n "new-value" | base64`
3. Patch Kubernetes secret: `kubectl patch secret ...`
4. Restart affected pods: `kubectl rollout restart deployment/backend`

### Access Control

**Azure Key Vault**:
- Access via Azure RBAC
- Service Principal has read-only access
- Audit logs in Azure Monitor

**Alibaba ACK**:
- Secrets accessed via K8s RBAC
- Only backend ServiceAccount can read `backend-secrets`
- Audit logs in ACK console

### Secret Scanning

**Pre-commit hooks** prevent secrets in code:
- `.env` files excluded from git
- Secret scanning with `detect-secrets`
- GitHub secret scanning enabled

## Troubleshooting

### Test Environment

**Problem**: Secret not syncing from Azure Key Vault

```bash
# Check ESO status
kubectl get externalsecret app-secrets -n klinematrix-test
kubectl describe externalsecret app-secrets -n klinematrix-test

# Check ESO logs
kubectl logs -n external-secrets-system deployment/external-secrets

# Force refresh
kubectl delete externalsecret app-secrets -n klinematrix-test
kubectl apply -f .pipeline/k8s/overlays/test/secrets.yaml
```

**Problem**: Workload identity not working

```bash
# Verify ServiceAccount annotations
kubectl get sa klinematrix-sa -n klinematrix-test -o yaml

# Check Azure AD federated credential configuration
az ad app federated-credential list \
  --id 03e41e5f-f062-45b2-9094-367e406c30a6
```

### Production Environment

**Problem**: Secret not found

```bash
# List all secrets
export KUBECONFIG=/Users/allenpan/.kube/config-ack-prod
kubectl get secrets -n klinematrix-prod

# Check secret contents (base64 encoded)
kubectl get secret backend-secrets -n klinematrix-prod -o yaml

# Decode specific key
kubectl get secret backend-secrets -n klinematrix-prod \
  -o jsonpath='{.data.alpha-vantage-api-key}' | base64 -d
```

**Problem**: Pod can't read secret

```bash
# Check RBAC
kubectl auth can-i get secrets --as=system:serviceaccount:klinematrix-prod:backend-sa

# Check if secret is mounted
kubectl exec -n klinematrix-prod deployment/backend -- ls /var/run/secrets/
kubectl exec -n klinematrix-prod deployment/backend -- env | grep ALPHA_VANTAGE
```

## Related Documentation

- [Deployment Workflow](./workflow.md)
- [Azure Key Vault Setup](./azure-setup.md)
- [Kustomize Configuration](../k8s/)
