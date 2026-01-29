#!/bin/bash
# ACK Cluster Recovery Script v2
# Comprehensive recovery with all lessons from 2026-01-29 incident
#
# Architecture: hostNetwork nginx-ingress (no SLB/LoadBalancer)
#   Internet → EIP → Node:80/443 (hostNetwork nginx) → ClusterIP Services → Pods
#
# Prerequisites:
# 1. New ACK cluster created with Flannel CNI in existing VPC
# 2. Nodes attached to cluster (via ACK console or node pool)
# 3. New kubeconfig downloaded to ~/.kube/config-ack-prod
# 4. EIP attached to one worker node
# 5. Security group configured (see Step 0 below)
#
# Usage: ./scripts/ack-recovery.sh
#
# Key Lessons Baked In:
# - ClickHouse password uses hex-only chars (no URL-special chars)
# - Security group must allow Pod CIDR TCP/UDP traffic
# - cert-manager needs RBAC for leader election (leases API)
# - CoreDNS needs hosts plugin for hairpin NAT workaround
# - nginx-ingress uses hostNetwork mode (no SLB cost)

set -e

# === CONFIGURATION ===
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-ack-prod}"
NAMESPACE="klinematrix-prod"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo_step() { echo -e "${GREEN}==>${NC} $1"; }
echo_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
echo_error() { echo -e "${RED}❌ $1${NC}"; }
echo_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

# ═══════════════════════════════════════════════════════════════
# STEP 0: PRE-FLIGHT CHECKS & SECURITY GROUP WARNING
# ═══════════════════════════════════════════════════════════════
echo ""
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo -e "${YELLOW}  CRITICAL PRE-FLIGHT: Security Group Configuration${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════════${NC}"
echo ""
echo "Before running this script, ensure the cluster security group has:"
echo ""
echo "  1. TCP 1-65535 from Pod CIDR (e.g., 10.100.0.0/16)"
echo "  2. UDP 1-65535 from Pod CIDR (e.g., 10.100.0.0/16)"
echo "  3. TCP 80,443 from 0.0.0.0/0 (for HTTPS/Let's Encrypt)"
echo "  4. ICMP from 0.0.0.0/0 (usually default)"
echo ""
echo "Without rules #1 and #2, cross-node pod communication will fail!"
echo "(ICMP works but TCP/UDP times out - very confusing to debug)"
echo ""
echo "Find Pod CIDR: kubectl get nodes -o jsonpath='{.items[0].spec.podCIDR}'"
echo "Find Security Group: Alibaba Cloud Console → ACK → Cluster → Security Group"
echo ""
read -p "Have you configured the security group? (yes/no): " SG_CONFIRMED
if [ "$SG_CONFIRMED" != "yes" ]; then
    echo_error "Please configure the security group first. See docs/recovery/ack-cluster-recovery-2026-01-29.md"
    exit 1
fi

# === PRE-FLIGHT CHECKS ===
echo_step "Pre-flight checks..."

if [ ! -f "$KUBECONFIG" ]; then
    echo_error "Kubeconfig not found at $KUBECONFIG"
    echo "Please download the new kubeconfig from ACK Console first."
    exit 1
fi

# ═══════════════════════════════════════════════════════════════
# STEP 1: VERIFY CLUSTER CONNECTION
# ═══════════════════════════════════════════════════════════════
echo_step "Step 1: Verifying cluster connection..."
if ! kubectl get nodes; then
    echo_error "Cannot connect to cluster. Check kubeconfig."
    exit 1
fi
echo -e "${GREEN}✓${NC} Cluster connection verified"

# ═══════════════════════════════════════════════════════════════
# STEP 2: CREATE NAMESPACE
# ═══════════════════════════════════════════════════════════════
echo_step "Step 2: Creating namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} Namespace $NAMESPACE ready"

# ═══════════════════════════════════════════════════════════════
# STEP 3: ACR PULL SECRET
# ═══════════════════════════════════════════════════════════════
echo_step "Step 3: Creating ACR pull secret..."

if [ -z "$ACR_USERNAME" ] || [ -z "$ACR_PASSWORD" ]; then
    echo_warn "ACR credentials not found in environment."
    echo "Please set ACR_USERNAME and ACR_PASSWORD environment variables."
    echo ""
    echo "Get them from GitHub: Repository → Settings → Secrets → Actions"
    echo "  - AZURE_ACR_USERNAME"
    echo "  - AZURE_ACR_PASSWORD"
    echo ""
    read -p "Enter ACR_USERNAME: " ACR_USERNAME
    read -s -p "Enter ACR_PASSWORD: " ACR_PASSWORD
    echo ""
fi

kubectl create secret docker-registry acr-secret \
  --docker-server=financialagent-gxftdbbre4gtegea.azurecr.io \
  --docker-username="$ACR_USERNAME" \
  --docker-password="$ACR_PASSWORD" \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} ACR pull secret created"

# ═══════════════════════════════════════════════════════════════
# STEP 4: GENERATE MONGODB PASSWORD
# ═══════════════════════════════════════════════════════════════
echo_step "Step 4: Generating MongoDB credentials..."
MONGO_PASSWORD=$(openssl rand -base64 32)
MONGO_PASSWORD_ENCODED=$(python3 -c "import urllib.parse; import sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$MONGO_PASSWORD")
MONGODB_URL="mongodb://admin:${MONGO_PASSWORD_ENCODED}@mongodb-service:27017/klinematrix_prod?authSource=admin"
echo -e "${GREEN}✓${NC} MongoDB password generated"

# ═══════════════════════════════════════════════════════════════
# STEP 5: CREATE MONGODB SECRET
# ═══════════════════════════════════════════════════════════════
echo_step "Step 5: Creating MongoDB secret..."
kubectl create secret generic mongodb-secret \
  --from-literal=mongodb-root-password="$MONGO_PASSWORD" \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} MongoDB secret created"

# ═══════════════════════════════════════════════════════════════
# STEP 6: CREATE BACKEND SECRETS
# ═══════════════════════════════════════════════════════════════
echo_step "Step 6: Creating backend secrets..."

JWT_SECRET="prod-jwt-$(openssl rand -hex 32)"

if [ -z "$ADMIN_SECRET" ]; then
    ADMIN_SECRET="admin-$(openssl rand -hex 16)"
    echo_warn "Generated new ADMIN_SECRET: $ADMIN_SECRET"
    echo "Save this for admin access!"
fi

kubectl create secret generic backend-secrets \
  --from-literal=mongodb-url="$MONGODB_URL" \
  --from-literal=redis-url="redis://:redis-prod-password@redis-service:6379/0" \
  --from-literal=jwt-secret="$JWT_SECRET" \
  --from-literal=admin-secret="$ADMIN_SECRET" \
  --from-literal=dashscope-api-key="${DASHSCOPE_API_KEY:-<REDACTED>}" \
  --from-literal=alpaca-api-key="${ALPACA_API_KEY:-<REDACTED>}" \
  --from-literal=alpaca-secret-key="${ALPACA_SECRET_KEY:-<REDACTED>}" \
  --from-literal=alpha-vantage-api-key="${ALPHA_VANTAGE_API_KEY:-<REDACTED>}" \
  --from-literal=polygon-api-key="${POLYGON_API_KEY:-<REDACTED>}" \
  --from-literal=oss-access-key="${OSS_ACCESS_KEY:-<REDACTED>}" \
  --from-literal=oss-secret-key="${OSS_SECRET_KEY:-<REDACTED>}" \
  --from-literal=tencent-secret-id="${TENCENT_SECRET_ID:-<REDACTED>}" \
  --from-literal=tencent-secret-key="${TENCENT_SECRET_KEY:-<REDACTED>}" \
  --from-literal=langfuse-public-key="pk-lf-placeholder" \
  --from-literal=langfuse-secret-key="sk-lf-placeholder" \
  --from-literal=langfuse-host="http://langfuse-server:3000" \
  --from-literal=fred-api-key="${FRED_API_KEY:-<REDACTED>}" \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} Backend secrets created"

# ═══════════════════════════════════════════════════════════════
# STEP 7: CREATE LANGFUSE SECRETS
# LESSON: ClickHouse password MUST NOT contain URL-special chars
#         (+, @, /, =, %, #, ?) because it's embedded in clickhouse:// URL
# ═══════════════════════════════════════════════════════════════
echo_step "Step 7: Creating Langfuse secrets..."
POSTGRES_PASSWORD=$(openssl rand -base64 24)
# CRITICAL: Use hex-only password for ClickHouse (no URL-special characters!)
# base64 can produce +, /, = which break clickhouse:// URL parsing in Go driver
CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)
NEXTAUTH_SECRET=$(openssl rand -base64 32)
SALT=$(openssl rand -base64 16)

echo_info "ClickHouse password (hex-safe): $CLICKHOUSE_PASSWORD"

kubectl create secret generic langfuse-secrets \
  --from-literal=postgres-password="$POSTGRES_PASSWORD" \
  --from-literal=clickhouse-password="$CLICKHOUSE_PASSWORD" \
  --from-literal=nextauth-secret="$NEXTAUTH_SECRET" \
  --from-literal=salt="$SALT" \
  --from-literal=oss-access-key-id="${OSS_ACCESS_KEY:-<REDACTED>}" \
  --from-literal=oss-access-key-secret="${OSS_SECRET_KEY:-<REDACTED>}" \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} Langfuse secrets created"

# ═══════════════════════════════════════════════════════════════
# STEP 8: INSTALL HELM CHARTS (nginx-ingress + cert-manager)
# ═══════════════════════════════════════════════════════════════
echo_step "Step 8: Installing Helm charts..."

helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
helm repo update

# Install nginx-ingress with hostNetwork mode
echo "  Installing nginx-ingress (hostNetwork mode)..."
if helm status nginx-ingress -n ingress-nginx &>/dev/null; then
    echo "  nginx-ingress already installed, upgrading..."
    helm upgrade nginx-ingress ingress-nginx/ingress-nginx \
      --namespace ingress-nginx \
      -f "$PROJECT_ROOT/.pipeline/helm/nginx-ingress/values.yaml" \
      -f "$PROJECT_ROOT/.pipeline/helm/nginx-ingress/values-prod.yaml"
else
    helm install nginx-ingress ingress-nginx/ingress-nginx \
      --namespace ingress-nginx --create-namespace \
      -f "$PROJECT_ROOT/.pipeline/helm/nginx-ingress/values.yaml" \
      -f "$PROJECT_ROOT/.pipeline/helm/nginx-ingress/values-prod.yaml"
fi
echo -e "${GREEN}✓${NC} nginx-ingress installed (hostNetwork mode)"

# Install cert-manager
echo "  Installing cert-manager..."
if helm status cert-manager -n cert-manager &>/dev/null; then
    echo "  cert-manager already installed"
else
    helm install cert-manager jetstack/cert-manager \
      --namespace cert-manager --create-namespace \
      --set installCRDs=true
fi
echo -e "${GREEN}✓${NC} cert-manager installed"

# Wait for cert-manager
echo "  Waiting for cert-manager to be ready..."
kubectl wait --for=condition=available deployment/cert-manager -n cert-manager --timeout=120s || true
kubectl wait --for=condition=available deployment/cert-manager-webhook -n cert-manager --timeout=120s || true

# ═══════════════════════════════════════════════════════════════
# STEP 9: APPLY CERT-MANAGER RBAC (Leader Election Fix)
# LESSON: Default Helm install may not grant 'leases' permission
#         in coordination.k8s.io API group, causing leader election failure
# ═══════════════════════════════════════════════════════════════
echo_step "Step 9: Applying cert-manager RBAC patch..."
kubectl apply -f "$PROJECT_ROOT/.pipeline/k8s/base/cert-manager/rbac.yaml"
echo -e "${GREEN}✓${NC} cert-manager RBAC applied"

# ═══════════════════════════════════════════════════════════════
# STEP 10: LABEL INGRESS NODE
# The node with EIP must be labeled for nginx-ingress nodeSelector
# ═══════════════════════════════════════════════════════════════
echo_step "Step 10: Labeling ingress node..."
echo ""
echo "Available nodes:"
kubectl get nodes -o wide
echo ""
echo "Which node has the public EIP attached?"
echo "(Enter the node name, e.g., cn-shanghai.172.22.192.247)"
read -p "Ingress node name: " INGRESS_NODE

if [ -n "$INGRESS_NODE" ]; then
    kubectl label node "$INGRESS_NODE" ingress=true --overwrite
    echo -e "${GREEN}✓${NC} Node $INGRESS_NODE labeled with ingress=true"

    # Extract internal IP for CoreDNS hosts
    INGRESS_NODE_IP=$(kubectl get node "$INGRESS_NODE" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')
    echo_info "Ingress node internal IP: $INGRESS_NODE_IP"
else
    echo_warn "No node specified. Label manually: kubectl label node <name> ingress=true"
fi

# ═══════════════════════════════════════════════════════════════
# STEP 11: COREDNS HAIRPIN NAT WORKAROUND
# LESSON: Internal pods can't reach public EIP (no hairpin NAT).
#         CoreDNS hosts plugin maps domains to internal node IP.
# ═══════════════════════════════════════════════════════════════
echo_step "Step 11: Applying CoreDNS hairpin NAT workaround..."

if [ -n "$INGRESS_NODE_IP" ]; then
    echo_info "Adding hosts entries for $INGRESS_NODE_IP to CoreDNS..."

    # Read existing CoreDNS ConfigMap, inject hosts block
    EXISTING_COREFILE=$(kubectl get configmap coredns -n kube-system -o jsonpath='{.data.Corefile}')

    if echo "$EXISTING_COREFILE" | grep -q "hosts {"; then
        echo_warn "CoreDNS already has hosts block. Skipping automatic patch."
        echo "Verify manually: kubectl get configmap coredns -n kube-system -o yaml"
    else
        # Create patched Corefile with hosts block before kubernetes block
        HOSTS_BLOCK="    hosts {\n      $INGRESS_NODE_IP klinecubic.cn\n      $INGRESS_NODE_IP www.klinecubic.cn\n      $INGRESS_NODE_IP monitor.klinecubic.cn\n      fallthrough\n    }"

        # Patch by inserting hosts block before the kubernetes line
        PATCHED_COREFILE=$(echo "$EXISTING_COREFILE" | sed "/kubernetes cluster.local/i\\
$HOSTS_BLOCK")

        kubectl patch configmap coredns -n kube-system --type merge \
          -p "{\"data\":{\"Corefile\":\"$(echo "$PATCHED_COREFILE" | sed ':a;N;$!ba;s/\n/\\n/g' | sed 's/"/\\"/g')\"}}" \
          && echo -e "${GREEN}✓${NC} CoreDNS patched with hairpin NAT workaround" \
          || echo_warn "Failed to patch CoreDNS automatically. Apply manually (see .pipeline/k8s/base/coredns/README.md)"

        kubectl rollout restart deployment/coredns -n kube-system 2>/dev/null || true
    fi
else
    echo_warn "Ingress node IP not known. Patch CoreDNS manually."
    echo "See: .pipeline/k8s/base/coredns/README.md"
fi

# Also apply the reference ConfigMap to production namespace
kubectl apply -f "$PROJECT_ROOT/.pipeline/k8s/base/coredns/hosts-patch-configmap.yaml" -n $NAMESPACE 2>/dev/null || true

# ═══════════════════════════════════════════════════════════════
# STEP 12: DEPLOY APPLICATIONS
# ═══════════════════════════════════════════════════════════════
echo_step "Step 12: Deploying applications via kustomize..."
cd "$PROJECT_ROOT"
kubectl apply -k .pipeline/k8s/overlays/prod/ --load-restrictor=LoadRestrictionsNone 2>/dev/null \
  || kustomize build .pipeline/k8s/overlays/prod --load-restrictor=LoadRestrictionsNone | kubectl apply -f -
echo -e "${GREEN}✓${NC} Applications deployed"

# ═══════════════════════════════════════════════════════════════
# STEP 13: WAIT FOR PODS
# ═══════════════════════════════════════════════════════════════
echo_step "Step 13: Waiting for pods to be ready..."
echo "  This may take 5-10 minutes for image pulls from Azure ACR..."

for DEPLOY in backend frontend redis mongodb langfuse-server langfuse-worker langfuse-postgres langfuse-clickhouse; do
    echo -n "  Waiting for $DEPLOY... "
    if kubectl wait --for=condition=available deployment/$DEPLOY -n $NAMESPACE --timeout=300s 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
    elif kubectl wait --for=condition=ready pod -l app=$DEPLOY -n $NAMESPACE --timeout=300s 2>/dev/null; then
        echo -e "${GREEN}✓${NC} (via pod ready)"
    else
        echo -e "${YELLOW}⚠ timeout${NC}"
    fi
done

# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "${GREEN}✅ ACK Cluster Recovery Complete (hostNetwork mode)${NC}"
echo "═══════════════════════════════════════════════════════════════"
echo ""

echo "📊 Cluster Status:"
kubectl get nodes -o wide
echo ""

echo "📦 Pods in $NAMESPACE:"
kubectl get pods -n $NAMESPACE -o wide
echo ""

echo "🌐 Ingress Configuration:"
kubectl get ingress -n $NAMESPACE
echo ""

echo "🔒 Certificates:"
kubectl get certificate -n $NAMESPACE 2>/dev/null || echo "  (certificates will be created after ingress applies)"
echo ""

echo "═══════════════════════════════════════════════════════════════"
echo -e "${YELLOW}📝 POST-RECOVERY CHECKLIST${NC}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  [ ] Security group has Pod CIDR TCP/UDP rules"
echo "  [ ] Security group has port 80/443 from 0.0.0.0/0"
echo "  [ ] EIP attached to ingress node"
echo "  [ ] Node labeled: ingress=true"
echo "  [ ] DNS records point to EIP:"
echo "      klinecubic.cn         → <EIP>"
echo "      www.klinecubic.cn     → <EIP>"
echo "      monitor.klinecubic.cn → <EIP>"
echo "  [ ] CoreDNS hosts patched for hairpin NAT"
echo "  [ ] SSL certificates issued (wait 5-10 min)"
echo "  [ ] Update GitHub secret ACK_KUBECONFIG"
echo "  [ ] Visit https://monitor.klinecubic.cn to create Langfuse account"
echo "  [ ] Generate Langfuse API keys and update backend-secrets"
echo "  [ ] Release any unused EIPs to save cost"
echo ""
echo "🔐 Generated Credentials (SAVE THESE!):"
echo "   ADMIN_SECRET:      $ADMIN_SECRET"
echo "   JWT_SECRET:        $JWT_SECRET"
echo "   CLICKHOUSE_PASS:   $CLICKHOUSE_PASSWORD (hex-safe, no URL-special chars)"
echo ""
echo "📋 Useful Commands:"
echo "   kubectl get pods -n $NAMESPACE -o wide"
echo "   kubectl logs -f deployment/backend -n $NAMESPACE"
echo "   kubectl get certificate -n $NAMESPACE"
echo "   kubectl get ingress -n $NAMESPACE"
echo "   kubectl describe ingress klinematrix-ingress -n $NAMESPACE"
echo ""
echo "📖 Reference: docs/recovery/ack-cluster-recovery-2026-01-29.md"
