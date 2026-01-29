# CoreDNS Hairpin NAT Workaround

## Why This Exists

When using **hostNetwork** mode for nginx-ingress (no SLB/LoadBalancer), internal pods that resolve our domains (`klinecubic.cn`, `monitor.klinecubic.cn`) get the **public EIP** address. Traffic from inside the cluster to the public EIP fails because Alibaba Cloud VPC does not support hairpin NAT.

This causes cert-manager ACME HTTP-01 challenges to fail (cert-manager pod tries to reach `http://klinecubic.cn/.well-known/acme-challenge/...` but can't connect to the public IP from inside the cluster).

## Solution

We add a `hosts` plugin entry to the CoreDNS ConfigMap in `kube-system` namespace, mapping our domains to the **internal node IP** where nginx-ingress runs.

## How to Apply

After cluster creation or if the ingress node changes:

```bash
# 1. Edit CoreDNS ConfigMap
kubectl edit configmap coredns -n kube-system

# 2. Add this block BEFORE the "kubernetes" plugin block:
#    hosts {
#      172.22.192.247 klinecubic.cn
#      172.22.192.247 www.klinecubic.cn
#      172.22.192.247 monitor.klinecubic.cn
#      fallthrough
#    }

# 3. Restart CoreDNS
kubectl rollout restart deployment/coredns -n kube-system
```

## When to Update

- **Ingress node changes**: If the node with the public EIP changes, update the IP in CoreDNS
- **New domains added**: If new domains are added (e.g., `api.klinecubic.cn`), add them to the hosts block
- **Cluster recreation**: Must be reapplied after creating a new cluster

## Reference File

`hosts-patch-configmap.yaml` contains a reference ConfigMap stored in `klinematrix-prod` namespace with the current snippet. This is NOT the actual CoreDNS config — it's a reference for the recovery script to use.
