# Production Verification Guide

> **Platform**: Kubernetes (AKS) + Azure + Alibaba Cloud
> **Last Updated**: 2025-10-08

This guide helps you verify the Financial Agent platform is working correctly in Kubernetes test environment.

## Prerequisites

- ✅ kubectl configured for AKS cluster
- ✅ Azure CLI authenticated (`az login`)
- ✅ Access to `financial-agent` namespace
- ✅ Web browser for testing endpoints

## Step 1: Verify Kubernetes Deployment

### 1.1 Check All Pods Running

```bash
kubectl get pods -n financial-agent
```

**Expected Output**:
```
NAME                        READY   STATUS    RESTARTS   AGE
backend-xxxxxxxxx-xxxxx     1/1     Running   0          5m
frontend-xxxxxxxxx-xxxxx    1/1     Running   0          5m
redis-xxxxxxxxx-xxxxx       1/1     Running   0          5m
```

**What to Look For**:
- All pods show `1/1 Ready`
- Status is `Running`
- Low restart count (0-2)

### 1.2 Check Services

```bash
kubectl get svc -n financial-agent
```

**Expected Output**:
```
NAME               TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
backend-service    ClusterIP   10.0.xxx.xxx    <none>        8000/TCP   10m
frontend-service   ClusterIP   10.0.xxx.xxx    <none>        80/TCP     10m
redis-service      ClusterIP   10.0.xxx.xxx    <none>        6379/TCP   10m
```

### 1.3 Verify Ingress

```bash
kubectl get ingress -n financial-agent
```

**Expected Output**:
```
NAME              CLASS   HOSTS                ADDRESS        PORTS     AGE
       nginx   localhost      20.xx.xx.xx    80, 443   30m
```

**Check**:
- HOSTS matches your domain
- ADDRESS is populated (not pending)
- Both HTTP (80) and HTTPS (443) ports

## Step 2: Test Health Endpoints

### 2.1 Backend Health Check

**From Internet**:
```bash
curl http://localhost:3000/api/health
```

**From within cluster**:
```bash
kubectl exec -n financial-agent deployment/backend -- curl -s http://localhost:8000/api/health
```

**Expected Response**:
```json
{
  "status": "ok",
  "version": "0.4.5",
  "environment": "test",
  "dependencies": {
    "mongodb": {
      "connected": true,
      "version": "4.2.0"
    },
    "redis": {
      "connected": true,
      "version": "7.2.0"
    }
  }
}
```

### 2.2 Frontend Health Check

```bash
curl http://localhost:3000/health
```

**Expected Response**:
```
healthy
```

### 2.3 Test with Python Script

```bash
python3 << 'EOF'
import requests
import json

print("🧪 PRODUCTION HEALTH CHECK")
print("=" * 50)

# Backend health
try:
    response = requests.get("http://localhost:3000/api/health", timeout=10)
    if response.status_code == 200:
        health = response.json()
        print("✅ Backend: OK")
        print(f"   Version: {health['version']}")
        print(f"   MongoDB: {'✅' if health['dependencies']['mongodb']['connected'] else '❌'}")
        print(f"   Redis: {'✅' if health['dependencies']['redis']['connected'] else '❌'}")
    else:
        print(f"❌ Backend: HTTP {response.status_code}")
except Exception as e:
    print(f"❌ Backend: {e}")

# Frontend health
try:
    response = requests.get("http://localhost:3000/health", timeout=10)
    if response.status_code == 200:
        print("✅ Frontend: OK")
    else:
        print(f"❌ Frontend: HTTP {response.status_code}")
except Exception as e:
    print(f"❌ Frontend: {e}")

print("=" * 50)
EOF
```

## Step 3: Verify External Dependencies

### 3.1 MongoDB (Cosmos DB)

```bash
# Check External Secret sync
kubectl get externalsecret mongodb-secret -n financial-agent

# Verify secret exists
kubectl get secret mongodb-secret -n financial-agent

# Test connection from pod
kubectl exec -n financial-agent deployment/backend -- python3 -c "
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os

async def test():
    client = AsyncIOMotorClient(os.environ['MONGODB_CONNECTION_STRING'])
    await client.admin.command('ping')
    print('✅ MongoDB connection successful')

asyncio.run(test())
"
```

### 3.2 Redis

```bash
# Test from backend pod
kubectl exec -n financial-agent deployment/backend -- redis-cli -h redis-service -p 6379 ping
# Expected: PONG

# Set/get test
kubectl exec -n financial-agent deployment/backend -- redis-cli -h redis-service -p 6379 set test_key "hello"
kubectl exec -n financial-agent deployment/backend -- redis-cli -h redis-service -p 6379 get test_key
# Expected: "hello"
```

### 3.3 Alibaba Cloud (DashScope)

```bash
# Check External Secret sync
kubectl get externalsecret alibaba-secret -n financial-agent

# Verify secret exists
kubectl get secret alibaba-secret -n financial-agent

# Test API key (from backend pod)
kubectl exec -n financial-agent deployment/backend -- python3 -c "
import os
import requests

api_key = os.environ.get('ALIBABA_DASHSCOPE_API_KEY')
if api_key and api_key.startswith('sk-'):
    print('✅ Alibaba API key configured')
else:
    print('❌ Alibaba API key missing or invalid')
"
```

## Step 4: Test Full Application Flow

### 4.1 Access Frontend

Open browser: **http://localhost:3000**

**Expected**:
- ✅ Page loads over HTTPS (valid certificate)
- ✅ "Financial Agent" header visible
- ✅ Login/signup options available
- ✅ Modern UI with TailwindCSS styling

### 4.2 Test Authentication

1. Click **"Sign Up"** or **"Log In"**
2. Create test account or log in

**Expected**:
- ✅ Registration successful
- ✅ Login redirects to chat interface
- ✅ User session persists (refresh page)

### 4.3 Test Chat Interface

1. Navigate to chat interface
2. Send test message: "Analyze AAPL stock"

**Expected**:
- ✅ Message sent successfully
- ✅ Backend processes request
- ✅ AI response received
- ✅ Chat history persisted (check MongoDB)

### 4.4 Test Market Data API

```bash
# Search for symbol
curl -s "http://localhost:3000/api/market/search?q=apple" | jq '.'

# Expected: Array of matching symbols including AAPL

# Get price data
curl -s "http://localhost:3000/api/market/price/AAPL?interval=1d&period=1mo" | jq '.data[0]'

# Expected: OHLCV data for AAPL
```

## Step 5: Security Verification

### 5.1 Check Security Contexts

```bash
# Verify non-root execution
kubectl get pods -n financial-agent -o json | \
  jq '.items[].spec.containers[].securityContext.runAsUser'
# Expected: 1000 (backend), 101 (frontend), 999 (redis)

# Verify read-only filesystem
kubectl get pods -n financial-agent -o json | \
  jq '.items[].spec.containers[].securityContext.readOnlyRootFilesystem'
# Expected: true

# Verify dropped capabilities
kubectl get pods -n financial-agent -o json | \
  jq '.items[].spec.containers[].securityContext.capabilities.drop'
# Expected: ["ALL"]
```

### 5.2 HTTPS/TLS Verification

```bash
# Check certificate validity
curl -vI http://localhost:3000 2>&1 | grep "SSL certificate verify"
# Expected: "SSL certificate verify ok"

# Check TLS version
nslookup localhost
openssl s_client -connect localhost:443 -tls1_2 < /dev/null | grep "Protocol"
# Expected: TLSv1.2 or higher
```

### 5.3 Network Policies (if configured)

```bash
kubectl get networkpolicies -n financial-agent
```

## Step 6: Performance and Monitoring

### 6.1 Check Resource Usage

```bash
# Pod resource usage
kubectl top pods -n financial-agent

# Node resource usage
kubectl top nodes
```

**Expected**:
- CPU < 50% per pod under normal load
- Memory < 500Mi per pod
- Node has capacity for pod restarts

### 6.2 View Logs

```bash
# Backend logs (last 50 lines)
kubectl logs -n financial-agent deployment/backend --tail=50

# Frontend logs
kubectl logs -n financial-agent deployment/frontend --tail=50

# Follow logs in real-time
kubectl logs -n financial-agent deployment/backend -f
```

### 6.3 Check Pod Events

```bash
kubectl get events -n financial-agent --sort-by='.lastTimestamp' | tail -20
```

**Watch for**:
- ❌ `BackOff` - Image pull or startup failures
- ❌ `FailedScheduling` - Resource constraints
- ✅ `Pulled`, `Created`, `Started` - Normal pod lifecycle

## Step 7: Database Verification

### 7.1 MongoDB Data Check

```bash
# Get shell in backend pod
kubectl exec -it -n financial-agent deployment/backend -- python3

# Then in Python shell:
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio
import os

async def check():
    client = AsyncIOMotorClient(os.environ['MONGODB_CONNECTION_STRING'])
    db = client[os.environ['MONGODB_DATABASE']]

    # Count users
    users_count = await db.users.count_documents({})
    print(f"Users: {users_count}")

    # Count chats
    chats_count = await db.chats.count_documents({})
    print(f"Chats: {chats_count}")

    # Count messages
    messages_count = await db.messages.count_documents({})
    print(f"Messages: {messages_count}")

    # List indexes
    indexes = await db.messages.list_indexes().to_list(100)
    print(f"Message indexes: {[idx['name'] for idx in indexes]}")

asyncio.run(check())
exit()
```

### 7.2 Redis Cache Check

```bash
kubectl exec -n financial-agent deployment/backend -- redis-cli -h redis-service -p 6379 INFO stats
# Check: keyspace_hits, keyspace_misses, connected_clients

# List keys (careful in production - use SCAN instead)
kubectl exec -n financial-agent deployment/backend -- redis-cli -h redis-service -p 6379 --scan --pattern "market:*" | head -10
```

## Step 8: Image Version Verification

### 8.1 Check Deployed Images

```bash
kubectl get pods -n financial-agent -o json | \
  jq -r '.items[] | "\(.metadata.name): \(.spec.containers[0].image)"'
```

**Expected** (current versions as of 2025-10-15):
```
backend-xxx: backend:test-v0.5.4
frontend-xxx: frontend:test-v0.8.4
redis-xxx: redis:7.2-alpine
```

### 8.2 Verify Image Pull Policy

```bash
kubectl get pods -n financial-agent -o json | \
  jq '.items[].spec.containers[] | {name: .name, imagePullPolicy: .imagePullPolicy}'
```

**Expected**: `imagePullPolicy: Always` for backend/frontend

## Troubleshooting

For detailed troubleshooting guides, see:
- [Kubernetes Issues](../troubleshooting/kubernetes-issues.md) - Pod crashes, ingress, image pulls
- [Deployment Issues](../troubleshooting/deployment-issues.md) - General deployment problems
- [External Secrets Sync](../troubleshooting/external-secrets-sync.md) - Secret management issues

## Success Criteria

Your deployment is healthy if:

- ✅ All pods are `1/1 Running` with low restarts
- ✅ Health endpoints return 200 OK
- ✅ MongoDB and Redis connections successful
- ✅ HTTPS works with valid certificate
- ✅ Frontend loads and is interactive
- ✅ Chat interface sends/receives messages
- ✅ Market data API returns valid data
- ✅ Security contexts enforced (non-root, read-only FS)
- ✅ Logs show no recurring errors
- ✅ Resource usage within expected limits

## Continuous Verification

Run this automated check periodically:

```bash
#!/bin/bash
echo "🧪 KUBERNETES HEALTH CHECK"
echo "=" * 50

# Check pods
if kubectl get pods -n financial-agent | grep -q "0/1"; then
  echo "❌ Some pods not ready"
  kubectl get pods -n financial-agent
else
  echo "✅ All pods ready"
fi

# Check backend health
if curl -sf http://localhost:3000/api/health > /dev/null; then
  echo "✅ Backend health OK"
else
  echo "❌ Backend health failed"
fi

# Check frontend
if curl -sf http://localhost:3000/health > /dev/null; then
  echo "✅ Frontend health OK"
else
  echo "❌ Frontend health failed"
fi

echo "=" * 50
```

## References

- [Kubernetes Deployment Guide](../deployment/workflow.md)
- [Security Hardening](../deployment/security-hardening.md)
- [MongoDB Cosmos DB Troubleshooting](../troubleshooting/mongodb-cosmos-db.md)
- [Infrastructure Setup](../architecture/infrastructure.md)
