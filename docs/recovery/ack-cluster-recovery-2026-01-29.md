# ACK Cluster Recovery - 2026-01-29

## Incident Summary

| Field | Detail |
|-------|--------|
| **Date of Incident** | 2026-01-27 |
| **Date of Recovery** | 2026-01-29 |
| **Severity** | P1 - Full production outage |
| **Duration** | ~48 hours (incident to full restoration) |
| **Affected Services** | All production services at klinecubic.cn and monitor.klinecubic.cn |
| **Root Cause** | API Server SLB (Server Load Balancer) accidentally deleted |
| **Resolution** | New cluster created and fully reconfigured |

---

## Incident Description

On 2026-01-27, the ACK (Alibaba Cloud Container Service for Kubernetes) cluster `klinecubic-financialagent` became unavailable after the API Server SLB (Server Load Balancer) was accidentally deleted. The SLB serves as the entry point for the Kubernetes API Server; without it, `kubectl` commands and all cluster management operations failed, rendering the entire production environment unreachable.

A new cluster was provisioned on 2026-01-29, and all services were restored after resolving six distinct infrastructure issues encountered during the recovery process.

---

## New Cluster Details

| Parameter | Value |
|-----------|-------|
| **Cluster ID** | `c061af4c23eb34eb0a5d39335a2f9b10c` |
| **Kubernetes Version** | 1.34.3 |
| **Region** | cn-shanghai (East China 2) |
| **VPC** | `vpc-uf61bb584xp7lmixq645v` |
| **VSwitch** | `vsw-uf6l2j4oyfyxam7lb2kyk` |
| **Pod CIDR** | `10.100.0.0/16` |
| **Service CIDR** | `192.168.0.0/16` |
| **CNI** | Flannel (ali-vpc backend) |
| **Proxy Mode** | IPVS |
| **Node Count** | 4 ECS instances |
| **Node IPs** | 172.22.192.247, .249, .250, .251 |
| **Public EIP** | `106.14.61.31` on node `.247` (instance `i-uf6d0t2id2gqfol0loxv`) |
| **Security Group** | `sg-uf678yj45sqqry5sfjim` |
| **API Server** | `47.102.113.54:6443` |

---

## Issues Encountered and Resolved

### Issue 1: Cross-Node Pod TCP Timeout (ICMP Works)

**Symptom**: Pods on different nodes could ping each other (ICMP), but TCP and UDP connections between pods on different nodes timed out. Same-node TCP worked normally.

**Diagnostic Matrix**:

| Test | Same Node | Cross Node |
|------|-----------|------------|
| ICMP (ping) | OK | OK |
| TCP | OK | TIMEOUT |
| UDP | OK | TIMEOUT |

**Root Cause**: The security group was missing rules for the Pod CIDR range. Flannel with the `ali-vpc` backend routes pod traffic through VPC route tables using the Pod IP as the source address (`10.100.x.x`), not the node IP (`172.22.x.x`). The default security group only allowed TCP from `172.16.0.0/12` and ICMP from `0.0.0.0/0`, so cross-node pod traffic with a `10.100.x.x` source IP was silently dropped at the security group level.

**Fix**: Added two ingress rules to security group `sg-uf678yj45sqqry5sfjim`:

| Protocol | Port Range | Source | Priority |
|----------|------------|--------|----------|
| TCP | 1-65535 | 10.100.0.0/16 | 1 |
| UDP | 1-65535 | 10.100.0.0/16 | 1 |

---

### Issue 2: ClickHouse Authentication Failure (Code 516)

**Symptom**: `langfuse-server` pod in CrashLoopBackOff with error: "password is incorrect" (error code 516), despite the credentials being correct in the Kubernetes secret.

**Root Cause**: The auto-generated password `<REDACTED-old-password-with-plus-sign>` contains a `+` character. When embedded in a `clickhouse://langfuse:PASSWORD@host:9000/db` connection URL, the Go clickhouse driver's URL parser interprets `+` as a space character (URL encoding convention), corrupting the password before authentication.

**Fix**:
1. Changed the ClickHouse password to `<REDACTED-alphanumeric-only>` (alphanumeric only, no special characters)
2. Updated the Kubernetes secret `langfuse-secrets` with the new password
3. Restarted ClickHouse to apply the new password
4. Updated the `CLICKHOUSE_MIGRATION_URL` environment variable in the langfuse-server deployment

**Prevention**: The recovery script now uses `openssl rand -hex 16` for ClickHouse passwords, producing only hexadecimal characters (0-9, a-f) that are safe for URL embedding.

---

### Issue 3: ERR_SSL_PROTOCOL_ERROR

**Symptom**: Browsers displayed `ERR_SSL_PROTOCOL_ERROR` when accessing `https://klinecubic.cn`.

**Root Cause**: The previous cluster used an SLB with HTTPS termination on port 443. The new cluster had nginx-ingress deployed with NodePort service (ports 30080/30443), but:
- The browser had HSTS cached, forcing HTTPS on the standard port 443
- No service was listening on port 443 on the node with the public EIP
- NodePort range (30000+) is not reachable from the internet without explicit SLB forwarding

**Fix**: Switched nginx-ingress from NodePort mode to `hostNetwork` mode, which binds the nginx-ingress pod directly to ports 80 and 443 on the host node. Combined with a `nodeSelector` targeting the node with the public EIP, this allows direct internet traffic to reach nginx-ingress without an SLB.

---

### Issue 4: nginx-ingress Scheduled on Wrong Node

**Symptom**: Website unreachable despite nginx-ingress pod running in hostNetwork mode.

**Root Cause**: The public EIP `106.14.61.31` was bound to node `.247`, but the nginx-ingress DaemonSet was scheduled on node `.250` due to the `ingress=true` label being on the wrong node. The initial assumption about which node had the EIP was incorrect.

**Fix**:
1. Removed `ingress=true` label from node `.250`
2. Applied `ingress=true` label to node `.247` (the node with the EIP)
3. The DaemonSet controller automatically rescheduled nginx-ingress to the correctly labeled node

**Verification**:
```bash
kubectl get nodes --show-labels | grep ingress
kubectl get pods -n ingress-nginx -o wide
```

---

### Issue 5: cert-manager Leader Election Failure

**Symptom**: cert-manager pods were running but no certificates were being issued. The controller log showed leader election errors.

**Root Cause**: Missing RBAC Role for the `leases` resource in the `coordination.k8s.io` API group. The default Helm install of cert-manager did not grant this permission in the ACK environment. Without leader election, the cert-manager controller pod could not acquire the lock and remained idle.

**Fix**: Created a Role and RoleBinding in the `cert-manager` namespace:

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: cert-manager:leaderelection
  namespace: cert-manager
rules:
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["get", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: cert-manager:leaderelection
  namespace: cert-manager
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: cert-manager:leaderelection
subjects:
  - kind: ServiceAccount
    name: cert-manager
    namespace: cert-manager
```

This RBAC configuration is now persisted at `.pipeline/k8s/base/cert-manager/rbac.yaml` to prevent recurrence.

---

### Issue 6: cert-manager ACME Self-Check Failure

**Symptom**: Certificate challenges (HTTP-01) failed with "connection refused" during the ACME self-check phase.

**Root Cause (Layer 1)**: cert-manager had `dnsPolicy: None` configured with Google DNS (`8.8.8.8`) as the primary nameserver. When cert-manager resolved `klinecubic.cn` to verify the challenge, it got the public EIP (`106.14.61.31`). However, Alibaba Cloud VPC does not support hairpin NAT -- traffic from within the VPC destined for the public EIP cannot loop back to a pod on the same network.

**Fix (Layer 1)**: Changed cert-manager `dnsPolicy` from `None` to `ClusterFirst`, so it uses the cluster's CoreDNS.

**Root Cause (Layer 2)**: Even with `ClusterFirst`, CoreDNS forwards external domain queries to upstream DNS servers, which still resolve `klinecubic.cn` to the public EIP. The hairpin NAT problem persisted.

**Fix (Layer 2)**: Added a CoreDNS `hosts` plugin override to map the domain to the internal node IP:

```
hosts {
    172.22.192.247 klinecubic.cn
    fallthrough
}
```

This configuration is persisted at `.pipeline/k8s/base/coredns/` to survive cluster upgrades and CoreDNS restarts.

---

## Timeline

| Time | Event |
|------|-------|
| **2026-01-27** | API Server SLB accidentally deleted; cluster becomes unavailable |
| **2026-01-27 - 2026-01-28** | Impact assessment and recovery planning |
| **2026-01-29 AM** | New ACK cluster created with 4 nodes attached |
| **2026-01-29** | DNS intermittent failures observed; cross-node TCP timeout discovered |
| **2026-01-29** | Security group Pod CIDR rules added; cross-node networking restored |
| **2026-01-29** | ClickHouse password issue diagnosed; changed to alphanumeric-only password |
| **2026-01-29** | All 8 pods healthy: backend, frontend, redis, mongodb, langfuse-server, langfuse-worker, langfuse-postgres, langfuse-clickhouse |
| **2026-01-29** | SSL/HTTPS setup: hostNetwork mode, node label correction, cert-manager RBAC, CoreDNS hairpin NAT workaround |
| **2026-01-29** | Let's Encrypt certificates issued for `klinecubic.cn` and `monitor.klinecubic.cn` |
| **2026-01-29** | Full production service restored and verified |

---

## Current Infrastructure State

### Cluster Configuration

```
Cluster ID:     c061af4c23eb34eb0a5d39335a2f9b10c
K8s Version:    1.34.3
Region:         cn-shanghai
VPC:            vpc-uf61bb584xp7lmixq645v
VSwitch:        vsw-uf6l2j4oyfyxam7lb2kyk
Security Group: sg-uf678yj45sqqry5sfjim
Pod CIDR:       10.100.0.0/16
Service CIDR:   192.168.0.0/16
CoreDNS:        192.168.0.10
CNI:            Flannel (ali-vpc)
Proxy Mode:     IPVS
```

### Nodes

```
cn-shanghai.172.22.192.247 - Public EIP: 106.14.61.31 (ingress=true)
cn-shanghai.172.22.192.249
cn-shanghai.172.22.192.250
cn-shanghai.172.22.192.251
```

### EIPs

| EIP | Purpose | Status |
|-----|---------|--------|
| `106.14.61.31` | Bound to node .247 (web traffic ingress) | In use |
| `139.196.155.13` | NAT Gateway (outbound SNAT) | In use |
| `47.102.113.54` | API Server SLB | In use |
| `47.100.76.54` | Released | ✅ Released (2026-01-30) |

### Kubernetes Secrets

| Secret Name | Purpose |
|-------------|---------|
| `acr-secret` | Azure ACR docker-registry credentials |
| `backend-secrets` | All backend API keys and connection strings |
| `langfuse-secrets` | PostgreSQL, ClickHouse (alphanumeric only), NextAuth, OSS |
| `mongodb-secret` | MongoDB root password |
| `redis-auth` | Redis password |

### SSL Certificates

| Certificate | Domains | Issuer | Renewal |
|-------------|---------|--------|---------|
| `klinecubic-tls` | klinecubic.cn, www.klinecubic.cn | Let's Encrypt | Auto-renew via cert-manager |
| `langfuse-tls` | monitor.klinecubic.cn | Let's Encrypt | Auto-renew via cert-manager |

### Architecture Diagram

```
Internet (HTTPS)
     |
     v
DNS: klinecubic.cn --> 106.14.61.31
     |
     v
EIP --> Node .247 ports 80/443 (hostNetwork nginx-ingress)
     |
     v
nginx-ingress (TLS termination, Let's Encrypt auto-renew)
     |
     +---> klinecubic.cn/api      --> backend-service:8000
     |
     +---> klinecubic.cn/          --> frontend-service:80
     |
     +---> monitor.klinecubic.cn   --> langfuse-server:3000
     |
     v
Backend Pod <--> MongoDB (StatefulSet) + Redis + Langfuse
     |
     v
External APIs (DashScope, Alpaca, Alpha Vantage, FRED)
```

---

## Lessons Learned

### 1. Flannel Pod CIDR Security Group Rules Are Mandatory

When using Flannel CNI with the `ali-vpc` backend, the security group **must** allow TCP/UDP 1-65535 from the Pod CIDR (`10.100.0.0/16`). ICMP alone is not sufficient.

**Why**: Flannel ali-vpc routes pod-to-pod traffic through VPC route tables using the Pod IP as the source address, not the node IP. The security group evaluates against the source IP, so without explicit rules for the Pod CIDR, cross-node TCP/UDP traffic is silently dropped while ICMP (allowed from `0.0.0.0/0`) continues to work -- creating a misleading diagnostic signal.

### 2. ClickHouse URL Password Character Restrictions

Never use `+`, `@`, `/`, `=`, `%`, `#`, or `?` in passwords that are embedded in `clickhouse://` connection URLs. The Go clickhouse driver's URL parser corrupts these characters during parsing.

**Safe password generation**: `openssl rand -hex 16` (produces only hexadecimal characters: 0-9, a-f).

### 3. hostNetwork vs SLB Cost Trade-off

For cost-constrained clusters, `hostNetwork` nginx-ingress eliminates the SLB cost (~$15/month USD). The trade-offs are:
- Single point of failure (one node runs ingress)
- Must label the correct node with `ingress=true`
- Node replacement requires re-labeling and EIP rebinding

### 4. cert-manager RBAC in ACK Requires Manual Patching

The default Helm install of cert-manager may not grant the `leases` permission in the `coordination.k8s.io` API group on ACK clusters. This causes **silent** leader election failure -- pods appear healthy but do nothing.

**Always** apply the RBAC patch after installing cert-manager on ACK. The patch is persisted at `.pipeline/k8s/base/cert-manager/rbac.yaml`.

### 5. Hairpin NAT Does Not Work on Alibaba Cloud VPC

Internal pods that resolve an external domain to the cluster's public EIP will fail to connect. Traffic from within the VPC cannot loop back through the EIP.

**Workaround**: Use the CoreDNS `hosts` plugin to override domain resolution, mapping the external domain to the internal node IP where nginx-ingress runs. Configuration is persisted at `.pipeline/k8s/base/coredns/`.

### 6. Always Verify Node-to-EIP Binding

Do not assume which node has the public EIP. During this recovery, the initial assumption was wrong, causing nginx-ingress to run on a node without internet reachability.

**Verification steps**:
1. `kubectl get nodes -o wide` to list node IPs
2. Check Alibaba Cloud ECS console for EIP bindings
3. Confirm with: `ssh <node-ip> curl -s ifconfig.me`

### 7. Network Diagnostic Matrix

When pod networking fails, systematically test all four combinations to isolate the failure layer:

| Test | Protocol | Scope | What it tells you |
|------|----------|-------|-------------------|
| 1 | ICMP | Same node | Basic pod networking |
| 2 | ICMP | Cross node | VPC routing / basic security group |
| 3 | TCP | Same node | Container port binding |
| 4 | TCP | Cross node | Security group TCP rules for Pod CIDR |

If test 2 passes but test 4 fails, the issue is security group rules specific to TCP with Pod CIDR source IPs.

See the learned skill at `~/.claude/skills/learned/k8s-cross-node-network-diagnostic.md` for the full diagnostic procedure.

---

## Recovery Script

An updated recovery script incorporating all lessons learned is available at:

```
scripts/ack-recovery.sh
```

The script includes:
- Automated security group rule creation for Pod CIDR
- Hex-only password generation for ClickHouse
- cert-manager RBAC patching
- CoreDNS hairpin NAT configuration
- Node label management for nginx-ingress scheduling

---

## Post-Recovery Checklist

- [x] All pods running (8/8 healthy)
- [x] Website accessible (https://klinecubic.cn)
- [x] API health check passing (`/api/health`)
- [x] Langfuse accessible (https://monitor.klinecubic.cn)
- [x] SSL certificates valid and auto-renewing
- [x] Update GitHub secret `ACK_KUBECONFIG` with new cluster kubeconfig
- [x] Release unbound EIP `47.100.76.54` to reduce costs (confirmed released 2026-01-30)

---

## Related Documentation

- [ACK Architecture](../deployment/ack-architecture.md)
- [Secrets Architecture](../deployment/secrets-architecture.md)
- [Previous Recovery (2025-01-27)](ack-cluster-recovery-2025-01-27.md)
- [CoreDNS Hairpin NAT](../../.pipeline/k8s/base/coredns/README.md)
- [Deployment Workflow](../deployment/workflow.md)
- [Cost Optimization Guide](../deployment/cost-optimization.md)
