# Financial Agent - Development Guide

> **RULE**: Only concise, actionable rules here. No details, no repetition. See [docs/](docs/) for comprehensive documentation.

## 🎯 Recent Architecture Changes

**ACK Cluster Recovery** (2026-01-29 - Active): New cluster after SLB deletion incident.
- **Cluster ID**: `c061af4c23eb34eb0a5d39335a2f9b10c` (K8s 1.34.3)
- **Architecture**: hostNetwork nginx-ingress (no SLB) on node with EIP `106.14.61.31`
- **Key Lessons**: Security group needs Pod CIDR rules, ClickHouse password no URL-special chars, cert-manager needs RBAC patch
- **Recovery Script**: `scripts/ack-recovery.sh` (v2, all lessons baked in)
- **Details**: [docs/recovery/ack-cluster-recovery-2026-01-29.md](docs/recovery/ack-cluster-recovery-2026-01-29.md)

**GitHub Actions CI/CD** (2025-12-15 - Active): Automated deployment pipeline.
- **PR Workflow**: `users/{name}/{feature}` branch → PR → Unit Tests → Review → Merge
- **Deploy Workflow**: Push to main → Build images → Deploy to ACK (automatic)
- **Manual Trigger**: GitHub Actions UI → "Deploy to Production" → Run workflow
- **Details**: [docs/deployment/workflow.md](docs/deployment/workflow.md)

**Langfuse Observability** (2025-11-29 - Deployed): LLM tracing deployed to production ACK.
- **URL**: https://monitor.klinecubic.cn
- **Stack**: Langfuse Server v3.135.0 + PostgreSQL + ClickHouse + Alibaba OSS
- **Backend Integration**: Automatic trace capture via `@observe` decorators
- **Secrets**: `langfuse-secrets` (infra) + `backend-secrets` (API keys)
- **Details**: [docs/features/langfuse-observability.md](docs/features/langfuse-observability.md)

**Market Insights v0.9.0** (2025-12-30 - Deployed): 7 metrics with Options PCR and FRED Liquidity.
- **New Metrics**: Options Put/Call Ratio (HISTORICAL_OPTIONS), Market Liquidity (FRED API)
- **Features**: Sparklines, expanded trend charts, composite score tracking
- **CronJob**: `insights-snapshot-trigger` runs at 14:30 UTC daily
- **Storage**: MongoDB `insight_snapshots` + Redis cache (24hr TTL)
- **Management**: See [CronJob Management](docs/deployment/workflow.md#cronjob-management)
- **Details**: [docs/features/market-insights-trend-visualization.md](docs/features/market-insights-trend-visualization.md)

**Portfolio Analysis CronJob** (2025-11-27 - Suspended): Migrated from dedicated pod (1.14GB image) to HTTP trigger pattern (5MB curl image).
- **Status**: ❌ Suspended in production (set `suspend: true` in YAML)
- **Old**: CronJob → Dedicated Pod → Python script → Direct DB access
- **New**: CronJob → curl (5MB) → Backend API → Background Task
- **Schedule**: `30 14 * * *` (9:30 AM ET / US market open)
- **Image**: ACR-hosted curl (`klinecubic/curl:8.5.0`) - Docker Hub blocked in China
- **Admin UI**: CronController component (admin-only, manual trigger button)
- **Details**: [docs/features/portfolio-analysis-cronjob-http.md](docs/features/portfolio-analysis-cronjob-http.md)

## 🔐 Security Rules

**🚨 NEVER COMMIT SECRETS 🚨** - API keys, passwords, tokens, credentials, connection strings, certificates
- ✅ Use placeholders: `<REDACTED>`, `YOUR_SECRET_HERE`, `AKID*****`
- ✅ Store in Azure Key Vault, reference by name only
- ✅ Before commit: Run `git diff --staged`, scan for secrets/passwords/keys
- ❌ **GitHub Push Protection blocks secret commits → painful git history rewrite!**

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12 + FastAPI + MongoDB + Redis |
| **Frontend** | React 18 + TypeScript 5 + Vite + TailwindCSS |
| **Deployment** | Kubernetes (ACK/AKS) + Azure AKV/ACR + Alibaba Cloud |
| **AI/LLM** | LangChain + LangGraph + Alibaba DashScope |

> 📖 **See [System Design](docs/architecture/system-design.md) for architecture details**

## 🌍 Environment Rules

**Current Active Environments:**

| Environment | Deployment Method | Access | Purpose | Status |
|-------------|------------------|--------|---------|--------|
| **Dev/Local** | Docker Compose | `localhost:3000` | Local development | ✅ Active |
| **Production** | GitHub Actions CI/CD → ACK | `https://klinecubic.cn` | Production | ✅ Active |
| **Test** | Kubernetes (AKS - Planned) | `https://klinematrix.com` | Cloud testing | 🚧 Planned |

**Current Workflow**: Dev/Local → PR to main → CI/CD auto-deploys to Production

### Dev/Local Environment
- **How to run**: `make dev` (starts docker-compose)
- **Services**: Backend, Frontend, MongoDB, Redis, Langfuse Stack (all in containers)
- **Access Points**:
  - Frontend: http://localhost:3000
  - Backend API: http://localhost:8000
  - Langfuse UI: http://localhost:3001 (LLM trace visualization)
  - MinIO Console: http://localhost:9003 (S3 storage)
- **Frontend commands**: `docker compose exec frontend npm ...`
- **Backend commands**: `cd backend && make test && make lint`
- **Hot reload**: ✅ Works for 90% of changes
- **When to use**: Daily development, testing features locally

### Production Environment (ACK - Active)
- **Platform**: Alibaba Cloud Container Service for Kubernetes (ACK)
- **Access**: https://klinecubic.cn
- **Langfuse**: https://monitor.klinecubic.cn (LLM trace visualization)
- **Namespace**: `klinematrix-prod`
- **Cluster**: `klinecubic-financialagent` (Shanghai/华东2, ID: `c061af4c23eb34eb0a5d39335a2f9b10c`)
- **K8s Version**: 1.34.3, Flannel CNI, IPVS proxy
- **Images**: `financialagent-gxftdbbre4gtegea.azurecr.io/klinecubic/*`
- **Ingress**: hostNetwork nginx on node `172.22.192.247` (EIP: `106.14.61.31`, label: `ingress=true`)
- **Security Group**: `sg-uf678yj45sqqry5sfjim` (must include Pod CIDR 10.100.0.0/16 TCP/UDP rules)
- **Status**: ✅ Active - Production deployment (recovered 2026-01-29)

### Test Environment (AKS - Planned, Not Active)
- **Platform**: Azure Kubernetes Service (AKS)
- **Access**: https://klinematrix.com (not active)
- **Namespace**: `klinematrix-test`
- **Images**: `financialagent-gxftdbbre4gtegea.azurecr.io/klinematrix/*`
- **Status**: 🚧 Planned - Not yet deployed (reserved for future)

### 🏗️ Hybrid Cloud Architecture

**Shared Services (Azure)**:
- **Container Registry**: Azure ACR (`financialagent-gxftdbbre4gtegea.azurecr.io`)
- **Key Vault**: Azure Key Vault (`klinematrix-test-kv`)

**Production Compute Platform**:
- **Alibaba Cloud ACK** (Shanghai) - ✅ Active

**Image Naming Convention**:
```
Production: financialagent-gxftdbbre4gtegea.azurecr.io/klinecubic/backend:prod-v0.7.1
            financialagent-gxftdbbre4gtegea.azurecr.io/klinecubic/frontend:prod-v0.10.1
```

**Golden Rule**: Develop locally → Create PR → CI/CD auto-deploys to Production after merge.

## 🧪 Testing & Iteration Rules

**When using webapp-testing skill for E2E testing:**

1. **Test First** - Run comprehensive E2E test to identify all issues
2. **Document Findings** - Write findings to `/tmp/webtesting/{scenario}/FINDINGS.md`
3. **Auto-Fix Loop** - Once testing complete, AUTOMATICALLY start fixing issues WITHOUT waiting for user prompt:
   ```
   WHILE issues exist:
     - Fix the issue in code
     - Restart affected services (docker compose restart)
     - Use Playwright/Chromium to trigger actions in UI
     - Re-run verification checks (logs + database + frontend)
     - IF new issues found: Add to list and continue
     - IF all checks pass: DONE
   ```
4. **No Manual Intervention** - Keep iterating until ALL checks pass (backend logs + database + frontend + APIs)
5. **Use Browser Automation** - Install playwright and use Chromium to:
   - Login with credentials (allenpan/admin123)
   - Navigate to features
   - Click buttons, trigger actions
   - Verify UI updates
6. **Verification Required** - After each fix, verify:
   - ✅ Backend logs show expected behavior
   - ✅ Database contains correct data
   - ✅ Frontend displays correctly
   - ✅ 3rd party APIs reflect changes

**Example:**
```
Test finds: Agent not being invoked
→ Fix: Inject agent into WatchlistAnalyzer
→ Restart: docker compose restart backend
→ Use Playwright: Login, click "Analyze Now"
→ Check logs for "Agent invoked"
→ IF fails: Fix and repeat
→ IF passes: Move to next issue
```

**Browser Automation Setup:**
```bash
pip install playwright
python -m playwright install chromium
```

**CRITICAL:** Don't stop at first fix - keep going until EVERYTHING works!

> 📖 **See [E2E Automation Guide](docs/testing/e2e-automation-guide.md) for complete E2E testing procedures**
> 📖 **See [E2E Reference](docs/testing/e2e-reference.md) for API endpoints, selectors, and workflows**
> 📖 **See [Testing Strategy](docs/development/testing-strategy.md) for unit test coverage plans**

## Development Workflow

> 📖 **Full Guide**: See [CONTRIBUTING.md](CONTRIBUTING.md) for complete development workflow, coding standards, and PR process.

### Quick Reference

```bash
# 1. Create feature spec (for new features)
touch docs/features/<feature-name>.md

# 2. Make changes and test
cd backend && make test && make lint
docker compose exec frontend npm run lint && npm test

# 3. Bump version (required for every commit)
./scripts/bump-version.sh backend patch   # 0.1.0 → 0.1.1
./scripts/bump-version.sh frontend minor  # 0.1.0 → 0.2.0

# 4. Commit (pre-commit hooks run automatically)
git add . && git commit -m "feat(scope): description"
```

### Key Rules

**⚠️ Frontend Commands**: Always use `docker compose exec frontend npm ...` (node_modules isolated in container)

**⚠️ Package Management**: Check before installing - reuse existing venvs (`/tmp/webtesting/*/venv`)

**⚠️ Version Required**: Pre-commit hook enforces version bump on every commit

### Deploy to Production

**CI/CD (Recommended)**: Merge PR to main → GitHub Actions auto-deploys

**Manual Trigger**: GitHub → Actions → "Deploy to Production" → Run workflow

> 📖 **See [Deployment Workflow](docs/deployment/workflow.md) for details**
> 📖 **See [Version Management](docs/project/versions/README.md) for versioning

## Code Standards

### Pre-commit Hooks
- **Version validation**: Every commit must bump version
- **File length**: Max 500 lines per file (Python, TypeScript, JavaScript)
- **Security**: eslint-plugin-security for vulnerability detection
- **Performance**: eslint-plugin-perf-standard for optimization
- **Code quality**: Black, Ruff, mypy, ESLint, Prettier

**See [docs/development/coding-standards.md](docs/development/coding-standards.md) for patterns & debugging**

## Project Methodology

**See [docs/development/verification.md](docs/development/verification.md) for validation procedures**

## Quick Reference Commands

```bash
# Dev/Local Environment
make dev            # Start all services
make test           # Run all tests
make fmt && make lint  # Format and check code quality
docker compose logs -f backend  # View logs

# Production K8s (ACK)
export KUBECONFIG=~/.kube/config-ack-prod
kubectl get pods -n klinematrix-prod           # Check status
kubectl logs -f deployment/backend -n klinematrix-prod  # View logs
kubectl rollout restart deployment/backend -n klinematrix-prod  # Restart

# Health Checks
curl http://localhost:8000/api/health          # Dev/Local
curl -s https://klinecubic.cn/api/health       # Production (may need proxy bypass)

# Langfuse Observability (Dev/Local)
open http://localhost:3001                     # UI
docker compose logs langfuse-server --tail=50  # Logs
```

> 📖 **See [Deployment Workflow](docs/deployment/workflow.md) for detailed commands and procedures**

## Important Reminders

### ⚠️ Before Committing

**🚨 CRITICAL: TEST FIRST, THEN COMMIT**
- **ALWAYS test changes before committing**
- Test locally with docker-compose first
- Check browser console for errors
- Test the actual user flow (click buttons, check UI updates)
- **DO NOT commit without testing**

**Checklist:**
- [ ] **Test locally first** - Verify changes work in browser/terminal
- [ ] **Docker running** (required for frontend tests): `open -a Docker` if needed
- [ ] **Feature spec created** (for new features): Document in `docs/features/`
- [ ] Run `make fmt && make test && make lint`
- [ ] **Bump version** (required): `./scripts/bump-version.sh [component] [patch|minor|major]`
- [ ] **Update CHANGELOG** (required): Add entry to `docs/project/versions/[component]/CHANGELOG.md`
- [ ] Check data contracts (Pydantic ↔ TypeScript)
- [ ] Verify no secrets in code

### 🚀 Before Deploying to Production
- [ ] Test locally with docker-compose
- [ ] Bump version (backend and/or frontend)
- [ ] Build images in ACR with prod prefix
- [ ] Update kustomization.yaml with new versions
- [ ] Deploy and restart pods
- [ ] Check pod status (1/1 Running)
- [ ] Test health endpoint (bypass proxy)
- [ ] Monitor logs for 5-10 minutes

**⚠️ Deployment Strategy Notes:**
- **Strategy: `Recreate`** (intentional) - Limited cluster resources can't run 2 backend pods simultaneously
- **Image pull time**: Azure ACR (East Asia) → Alibaba ACK (Shanghai) can take 10-20 min for ~240MB image
- **CI/CD pre-pull**: Pipeline creates a Job to cache image BEFORE deployment restart
- **Pre-pull timeout**: 15 minutes (`--timeout=900s`) for slow pulls
- **Rollout timeout**: 10 minutes (`--timeout=600s`) - should be fast after pre-pull
- **Downtime expected**: `Recreate` strategy kills old pod before new one is ready
- **If pre-pull fails**: Deployment continues but may be slow; check node cache

### 🔍 When Debugging
1. Check pod logs first
2. Verify data contracts alignment
3. Test backend directly (kubectl exec)
4. Check Redis cache if caching issues
5. Review External Secrets sync
6. **Dependencies**: For missing Python packages, install directly first (`docker compose run --rm backend pip install <pkg>`), THEN commit container - don't rebuild entire image
7. **🚨 Docker env vars**: After changing `.env` files, ALWAYS recreate containers (`docker compose up -d --force-recreate <service>`) - `restart` does NOT reload env vars!

### 💰 Cost Management
- **Monitor weekly**: `kubectl get nodes | wc -l` should always return 2
- See [Cost Optimization Guide](docs/deployment/cost-optimization.md) for troubleshooting

### 💡 Development Principles
- **Find the root cause** - Don't fix symptoms, fix the underlying problem
- **Start simple** - Try the simplest solution first (10 seconds) before complex ones (20+ minutes)
- **Less code is more** - Simplest solution that works is usually correct
- **Avoid duplication** - Same logic in multiple places = bug waiting to happen
- **Don't overcomplicate** - Complex solutions are harder to debug and maintain
- **Compare environments** - When cloud differs from local, check config/credentials first

**Examples**:
- Database name parsing bug existed in TWO places (config.py + mongodb.py). Fix once, extract to shared utility if needed.
- Portfolio cron ran every 5min despite `.env` saying disabled - container had stale env vars. **Always recreate after env changes!**

---

## 🚨 Critical Docker Rules

### Environment Variable Management

**NEVER TRUST `docker compose restart` TO RELOAD ENV VARS!**

Docker containers **bake in** environment variables at creation time. Changing `.env` files does NOT affect running containers.

**✅ CORRECT Way to Reload Env Vars:**
```bash
# After changing .env files
docker compose up -d --force-recreate <service-name>

# Or explicit recreation
docker compose stop <service-name>
docker compose rm -f <service-name>
docker compose up -d <service-name>
```

**❌ WRONG - Does NOT reload env:**
```bash
docker compose restart <service-name>  # Only restarts process, keeps old env!
```

**✅ ALWAYS Verify After Recreation:**
```bash
docker compose exec <service> printenv | grep <VAR_PREFIX>
docker compose logs <service> --tail=20
```

**See**: [docs/troubleshooting/docker-env-reload-issue.md](docs/troubleshooting/docker-env-reload-issue.md) for detailed incident report.

## 🎯 Kubernetes Operations Best Practices

### Declarative Configuration
- **Always use explicit values** - Don't rely on implicit transformations
- **Include image references** - Strategic merge patches need explicit `image:` field
- **Verify before apply**: `kubectl kustomize <path>` to check rendered manifests
- **Never force with kubectl** - All changes must be in YAML files

### Resource Management
- **Use resource requests for scheduling** - High memory requests → high-memory nodes
- **Right-size based on metrics**: `kubectl top pods --containers`
- **Memory ≠ Pod slots** - Node can have free memory but hit pod limit
- **Node pool limits are immutable**:
  - `max-pods` cannot be changed after creation
  - Must delete/recreate node pool to modify

### Node Pool Strategy
```yaml
# High-memory workloads (2Gi request) → userpoolv2 (Standard_E2_v3, 16GB)
langfuse-worker, langfuse-clickhouse, backend

# Lightweight workloads (< 256Mi) → userpool (Standard_D2ls_v5, 4GB)
redis, frontend
```

### Troubleshooting Checklist
1. **Deployment version reverts** → Check explicit image in patch files
2. **Pod pending with free memory** → Check `kubectl describe node` for pod limit
3. **CPU throttling** → Review `kubectl top pods` and adjust limits
4. **Pods on wrong node** → Verify resource requests match node capacity

---

**Before any actions, always get context by reading the [docs main page](docs/README.md).**
