#!/bin/bash
# DEPRECATED: Use scripts/ack-recovery.sh instead (v2, hostNetwork mode)
#
# This NodePort-based script was superseded on 2026-01-29 by the hostNetwork
# approach which provides standard port 80/443 access (required for HTTPS/HSTS).
# See: docs/recovery/ack-cluster-recovery-2026-01-29.md
#
# Original: ACK Cluster Recovery Script - NodePort Edition (No SLB)
# Low-cost setup using NodePort instead of LoadBalancer
#
# Architecture:
#   Internet → EIP → Worker Node:NodePort → Pods
#
# Prerequisites:
# 1. New ACK cluster created (no public API SLB)
# 2. SSH access to worker node OR internal kubeconfig
# 3. EIP attached to one worker node
#
# Usage: ./scripts/ack-nodeport-recovery.sh

set -e

# === CONFIGURATION ===
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config-ack-prod}"
NAMESPACE="klinematrix-prod"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# NodePort configuration (30000-32767 range)
FRONTEND_NODEPORT=30080
BACKEND_NODEPORT=30800
LANGFUSE_NODEPORT=30300

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_step() { echo -e "${GREEN}==>${NC} $1"; }
echo_warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
echo_error() { echo -e "${RED}❌ $1${NC}"; }
echo_info() { echo -e "${BLUE}ℹ️  $1${NC}"; }

# === PRE-FLIGHT CHECKS ===
echo_step "Pre-flight checks..."

if [ ! -f "$KUBECONFIG" ]; then
    echo_error "Kubeconfig not found at $KUBECONFIG"
    echo "For private cluster, you need to:"
    echo "  1. SSH to a worker node"
    echo "  2. Copy kubeconfig from ACK console (internal endpoint)"
    echo "  3. Or set up SSH tunnel to internal API"
    exit 1
fi

# === Step 1: Verify Connection ===
echo_step "Step 1: Verifying cluster connection..."
if ! kubectl get nodes 2>/dev/null; then
    echo_warn "Direct connection failed. Trying with proxy bypass..."
    if ! HTTPS_PROXY= HTTP_PROXY= kubectl get nodes; then
        echo_error "Cannot connect to cluster."
        echo ""
        echo "For private clusters, set up SSH tunnel first:"
        echo "  ssh -L 6443:<INTERNAL_API_IP>:6443 root@<WORKER_EIP>"
        echo ""
        echo "Then update kubeconfig to use localhost:6443"
        exit 1
    fi
fi
echo -e "${GREEN}✓${NC} Cluster connection verified"

# Show nodes
kubectl get nodes -o wide

# === Step 2: Create Namespace ===
echo_step "Step 2: Creating namespace..."
kubectl create namespace $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} Namespace $NAMESPACE ready"

# === Step 3: ACR Pull Secret ===
echo_step "Step 3: Creating ACR pull secret..."

if [ -z "$ACR_USERNAME" ] || [ -z "$ACR_PASSWORD" ]; then
    echo_warn "ACR credentials not found in environment."
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

# === Step 4: Generate MongoDB Password ===
echo_step "Step 4: Generating MongoDB credentials..."
MONGO_PASSWORD=$(openssl rand -base64 32)
MONGO_PASSWORD_ENCODED=$(python3 -c "import urllib.parse; import sys; print(urllib.parse.quote(sys.argv[1], safe=''))" "$MONGO_PASSWORD")
MONGODB_URL="mongodb://admin:${MONGO_PASSWORD_ENCODED}@mongodb-service:27017/klinematrix_prod?authSource=admin"
echo -e "${GREEN}✓${NC} MongoDB password generated"

# === Step 5: Create MongoDB Secret ===
echo_step "Step 5: Creating MongoDB secret..."
kubectl create secret generic mongodb-secret \
  --from-literal=mongodb-root-password="$MONGO_PASSWORD" \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} MongoDB secret created"

# === Step 6: Create Backend Secrets ===
echo_step "Step 6: Creating backend secrets..."

JWT_SECRET="prod-jwt-$(openssl rand -hex 32)"
ADMIN_SECRET="${ADMIN_SECRET:-admin-$(openssl rand -hex 16)}"

echo_info "Generated ADMIN_SECRET: $ADMIN_SECRET"

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
  --from-literal=fred-api-key="${FRED_API_KEY:-placeholder}" \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} Backend secrets created"

# === Step 7: Create Langfuse Secrets ===
echo_step "Step 7: Creating Langfuse secrets..."
POSTGRES_PASSWORD=$(openssl rand -base64 24)
CLICKHOUSE_PASSWORD=$(openssl rand -base64 24)
NEXTAUTH_SECRET=$(openssl rand -base64 32)
SALT=$(openssl rand -base64 16)

kubectl create secret generic langfuse-secrets \
  --from-literal=postgres-password="$POSTGRES_PASSWORD" \
  --from-literal=clickhouse-password="$CLICKHOUSE_PASSWORD" \
  --from-literal=nextauth-secret="$NEXTAUTH_SECRET" \
  --from-literal=salt="$SALT" \
  --from-literal=oss-access-key-id="${OSS_ACCESS_KEY:-<REDACTED>}" \
  --from-literal=oss-access-key-secret="${OSS_SECRET_KEY:-<REDACTED>}" \
  -n $NAMESPACE --dry-run=client -o yaml | kubectl apply -f -
echo -e "${GREEN}✓${NC} Langfuse secrets created"

# === Step 8: Install cert-manager (for internal TLS if needed) ===
echo_step "Step 8: Installing cert-manager..."
helm repo add jetstack https://charts.jetstack.io 2>/dev/null || true
helm repo update

if ! helm status cert-manager -n cert-manager &>/dev/null; then
    helm install cert-manager jetstack/cert-manager \
      --namespace cert-manager --create-namespace \
      --set installCRDs=true
fi
echo -e "${GREEN}✓${NC} cert-manager installed"

# === Step 9: Deploy Base Applications (Without Ingress) ===
echo_step "Step 9: Deploying base applications..."
cd "$PROJECT_ROOT"

# Apply base resources manually (skip ingress-related)
kubectl apply -f .pipeline/k8s/overlays/prod/namespace.yaml || true
kubectl apply -f .pipeline/k8s/base/redis/configmap.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/redis/secret.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/redis/deployment.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/redis/service.yaml -n $NAMESPACE

# MongoDB
kubectl apply -f .pipeline/k8s/overlays/prod/mongodb-statefulset.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/overlays/prod/mongodb-service.yaml -n $NAMESPACE

# Wait for MongoDB
echo "  Waiting for MongoDB to be ready..."
kubectl wait --for=condition=ready pod -l app=mongodb -n $NAMESPACE --timeout=300s || true

# Backend & Frontend with patches
kubectl apply -f .pipeline/k8s/base/backend/deployment.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/frontend/deployment.yaml -n $NAMESPACE

# Apply prod patches
kubectl patch deployment backend -n $NAMESPACE --patch-file .pipeline/k8s/overlays/prod/backend-prod-patch.yaml || true
kubectl patch deployment frontend -n $NAMESPACE --patch-file .pipeline/k8s/overlays/prod/frontend-prod-patch.yaml || true

# Langfuse stack
kubectl apply -f .pipeline/k8s/base/langfuse/postgres-statefulset.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/langfuse/postgres-service.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/langfuse/clickhouse-statefulset.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/langfuse/clickhouse-service.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/langfuse/server-deployment.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/langfuse/worker-deployment.yaml -n $NAMESPACE

echo -e "${GREEN}✓${NC} Base applications deployed"

# === Step 10: Create NodePort Services ===
echo_step "Step 10: Creating NodePort services..."

# Frontend NodePort Service
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: frontend-nodeport
  namespace: $NAMESPACE
spec:
  type: NodePort
  selector:
    app: frontend
  ports:
  - port: 80
    targetPort: 80
    nodePort: $FRONTEND_NODEPORT
    name: http
EOF

# Backend NodePort Service
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: backend-nodeport
  namespace: $NAMESPACE
spec:
  type: NodePort
  selector:
    app: backend
  ports:
  - port: 8000
    targetPort: 8000
    nodePort: $BACKEND_NODEPORT
    name: http
EOF

# Langfuse NodePort Service
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: langfuse-nodeport
  namespace: $NAMESPACE
spec:
  type: NodePort
  selector:
    app: langfuse-server
  ports:
  - port: 3000
    targetPort: 3000
    nodePort: $LANGFUSE_NODEPORT
    name: http
EOF

# Also create internal ClusterIP services
kubectl apply -f .pipeline/k8s/base/backend/service.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/frontend/service.yaml -n $NAMESPACE
kubectl apply -f .pipeline/k8s/base/langfuse/server-service.yaml -n $NAMESPACE

echo -e "${GREEN}✓${NC} NodePort services created"

# === Step 11: Update Image Tags ===
echo_step "Step 11: Updating image tags..."
kubectl set image deployment/backend backend=financialagent-gxftdbbre4gtegea.azurecr.io/klinecubic/backend:prod-v0.10.0 -n $NAMESPACE
kubectl set image deployment/frontend frontend=financialagent-gxftdbbre4gtegea.azurecr.io/klinecubic/frontend:prod-v0.11.5 -n $NAMESPACE
echo -e "${GREEN}✓${NC} Image tags updated"

# === Step 12: Get Node Info ===
echo_step "Step 12: Getting node information..."
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}')
NODE_NAME=$(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')

# === Summary ===
echo ""
echo "============================================"
echo -e "${GREEN}✅ ACK Cluster Recovery Complete (NodePort)${NC}"
echo "============================================"
echo ""

echo "📊 Cluster Status:"
kubectl get nodes -o wide
echo ""

echo "📦 Pods in $NAMESPACE:"
kubectl get pods -n $NAMESPACE
echo ""

echo "🔌 NodePort Services:"
kubectl get svc -n $NAMESPACE | grep NodePort
echo ""

echo -e "${YELLOW}============================================${NC}"
echo -e "${YELLOW}⚠️  IMPORTANT: Manual Steps Required${NC}"
echo -e "${YELLOW}============================================${NC}"
echo ""
echo "1️⃣  ATTACH EIP TO WORKER NODE:"
echo "   - Go to Alibaba Cloud Console → ECS → Instances"
echo "   - Find node: $NODE_NAME"
echo "   - Bind an Elastic IP (EIP) to this instance"
echo "   - Note the EIP address: <YOUR_EIP>"
echo ""
echo "2️⃣  CONFIGURE SECURITY GROUP:"
echo "   - Go to ECS → Security Groups"
echo "   - Add inbound rules:"
echo "     - Port $FRONTEND_NODEPORT (TCP) from 0.0.0.0/0 - Frontend"
echo "     - Port $BACKEND_NODEPORT (TCP) from 0.0.0.0/0 - Backend API"
echo "     - Port $LANGFUSE_NODEPORT (TCP) from 0.0.0.0/0 - Langfuse"
echo "     - Port 22 (TCP) from your IP - SSH management"
echo ""
echo "3️⃣  UPDATE DNS RECORDS:"
echo "   - klinecubic.cn        → <YOUR_EIP>"
echo "   - monitor.klinecubic.cn → <YOUR_EIP>"
echo ""
echo "4️⃣  ACCESS YOUR APPS:"
echo "   - Frontend: http://<YOUR_EIP>:$FRONTEND_NODEPORT"
echo "   - Backend:  http://<YOUR_EIP>:$BACKEND_NODEPORT/api/health"
echo "   - Langfuse: http://<YOUR_EIP>:$LANGFUSE_NODEPORT"
echo ""
echo "5️⃣  FOR HTTPS (Optional - use Cloudflare):"
echo "   - Enable Cloudflare proxy for DNS records"
echo "   - Cloudflare will handle SSL termination"
echo "   - Set SSL mode to 'Flexible' (Cloudflare → HTTP → NodePort)"
echo ""
echo "🔐 Generated Credentials (SAVE THESE!):"
echo "   ADMIN_SECRET: $ADMIN_SECRET"
echo "   JWT_SECRET: $JWT_SECRET"
echo ""
echo "📋 Useful Commands:"
echo "   kubectl get pods -n $NAMESPACE"
echo "   kubectl logs -f deployment/backend -n $NAMESPACE"
echo "   kubectl get svc -n $NAMESPACE"
