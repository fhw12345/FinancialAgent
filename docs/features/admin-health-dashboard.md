# Feature: Admin Health Dashboard with Resource Metrics

> **Status**: Draft
> **Created**: 2025-10-08
> **Last Updated**: 2025-10-08
> **Owner**: Allen Pan

## Context

Before production launch, we need proper monitoring and administrative controls to ensure system health and security.

**User Story**:
As a system administrator, I want a comprehensive health dashboard to monitor resource usage and database statistics, so that I can proactively identify issues before they affect users.

**Background**:
- Current health endpoint is publicly accessible (security risk)
- No resource metrics (CPU, memory) visibility
- No database growth monitoring
- No favicon in browser tab (unprofessional)
- Production requires admin-only monitoring capabilities

**Business Impact**:
- Early detection of resource exhaustion
- Capacity planning for user growth
- Security: Prevent information disclosure
- Professional appearance (favicon)

## Problem Statement

**Current Pain Points**:
1. **No Access Control**: Anyone can view `/health` endpoint revealing system internals
2. **No Resource Visibility**: Cannot monitor CPU/memory usage without kubectl
3. **No Database Metrics**: Unknown database growth rate, collection sizes
4. **Missing Favicon**: Browser tab shows default icon (unprofessional)

**Success Metrics**:
- Admin can view comprehensive system metrics in <2 seconds
- Non-admin users cannot access health dashboard
- CPU/memory usage visible at pod and node level
- Database collection sizes tracked and sortable

## Proposed Solution

### High-Level Approach

1. **Access Control**: Implement admin role checking (username-based for MVP)
2. **Kubernetes Metrics**: Query metrics-server API for CPU/memory
3. **Database Statistics**: Aggregate MongoDB collection counts and sizes
4. **Enhanced UI**: Display metrics in organized dashboard
5. **Favicon**: Add professional icon to frontend

### Architecture Changes

**Admin Middleware**: `require_admin(username)` checks if username == "admin" (MVP). `@admin_required` decorator returns 403 for non-admins.

**Data Models** (`admin_models.py`):
- `PodMetrics`: name, cpu_usage, memory_usage, cpu_percentage, memory_percentage
- `NodeMetrics`: name, cpu/memory usage & capacity, percentages
- `DatabaseStats`: collection, document_count, size_bytes, size_mb, avg_document_size_bytes
- `SystemMetrics`: timestamp, pods[], nodes[], database[], health_status

**API Endpoints** (all admin-only):
- `GET /api/admin/health` - Complete system metrics
- `GET /api/admin/metrics/pods` - Pod resource usage
- `GET /api/admin/metrics/nodes` - Node resource usage
- `GET /api/admin/metrics/database` - Database statistics

### Technical Implementation Details

#### 1. Admin Access Control

**User Model**: Add `is_admin: bool = False` field. Property `admin` returns `username == "admin" or is_admin`.

**Frontend**: Conditionally render Health nav item based on `user?.username === 'admin'`

#### 2. Kubernetes Metrics Integration

**RBAC Setup**: ServiceAccount `backend-sa`, Role `metrics-reader` (get/list on metrics.k8s.io/pods,nodes), RoleBinding

**KubernetesMetricsService**: Use in-cluster config (fallback to kubeconfig), query `metrics.k8s.io/v1beta1` for pods/nodes, parse CPU (millicores) and memory (MiB) from container usage, handle ApiException gracefully

#### 3. Database Statistics

**DatabaseStatsService**: List collections, for each run `count_documents` and `collStats` command, return sorted by size descending

#### 4. Frontend Health Dashboard

**HealthPage.tsx**: React Query with 10s refetch interval, StatusBadge for overall health, PodMetricCard grid for resource usage, table for database collections (name, count, size MB, avg doc size)

#### 5. Favicon Implementation

**Assets**: `favicon.ico`, `favicon-16x16.png`, `favicon-32x32.png`, `apple-touch-icon.png`, `site.webmanifest`

**HTML**: Link tags in `index.html` for all favicon variants

## Implementation Plan

### Phase 1: Access Control & Favicon (2-3 hours)
- [ ] Add favicon assets to frontend/public/
- [ ] Update index.html with favicon links
- [ ] Create admin middleware in backend
- [ ] Protect health endpoints with @admin_required
- [ ] Add frontend route guard for /health
- [ ] Hide health nav item for non-admin users
- [ ] Test admin access control

### Phase 2: Kubernetes Metrics (4-6 hours)
- [ ] Add kubernetes Python client dependency
- [ ] Create RBAC ServiceAccount and Role
- [ ] Implement KubernetesMetricsService
- [ ] Add /api/admin/metrics/pods endpoint
- [ ] Add /api/admin/metrics/nodes endpoint
- [ ] Test metrics collection in dev cluster
- [ ] Handle metrics-server unavailable gracefully

### Phase 3: Database Statistics (2-3 hours)
- [ ] Implement DatabaseStatsService
- [ ] Add /api/admin/metrics/database endpoint
- [ ] Test with production-like data volumes
- [ ] Add caching for expensive stats queries
- [ ] Sort collections by size descending

### Phase 4: Frontend Dashboard (4-6 hours)
- [ ] Create SystemMetrics TypeScript interfaces
- [ ] Implement HealthPage with resource cards
- [ ] Add pod metrics visualization
- [ ] Add database statistics table
- [ ] Add auto-refresh (10s interval)
- [ ] Add loading and error states
- [ ] Style with TailwindCSS

### Phase 5: Testing & Polish (2-3 hours)
- [ ] Test admin vs non-admin access
- [ ] Test with high CPU/memory usage
- [ ] Test with large database collections
- [ ] Verify RBAC permissions in cluster
- [ ] Add error handling for metrics failures
- [ ] Update documentation

**Total Estimated Effort**: 14-21 hours (~2-3 days)

## Acceptance Criteria

- [ ] **Favicon**:
  - [ ] Favicon appears in browser tab
  - [ ] Icon works on Chrome, Firefox, Safari
  - [ ] Apple touch icon works on iOS

- [ ] **Access Control**:
  - [ ] Health page only accessible to admin (username: admin)
  - [ ] Non-admin receives 403 Forbidden on health endpoints
  - [ ] Health nav item hidden for non-admin users
  - [ ] Logged-out users cannot access health page

- [ ] **Resource Metrics**:
  - [ ] Display CPU usage for all pods (millicores and %)
  - [ ] Display memory usage for all pods (MiB and %)
  - [ ] Display node-level CPU and memory
  - [ ] Metrics auto-refresh every 10 seconds
  - [ ] Graceful degradation if metrics-server unavailable

- [ ] **Database Statistics**:
  - [ ] Show document count for each collection
  - [ ] Show size in MB for each collection
  - [ ] Collections sorted by size (largest first)
  - [ ] Average document size displayed
  - [ ] Stats update on page refresh

- [ ] **Technical Requirements**:
  - [ ] All tests passing
  - [ ] RBAC configured for metrics access
  - [ ] Error handling for K8s API failures
  - [ ] No performance degradation (<200ms response time)

## Testing Strategy

**Unit Tests**: Admin middleware (username validation), KubernetesMetricsService (CPU/memory parsing), DatabaseStatsService (aggregation), Frontend (conditional rendering)

**Integration Tests**: Admin login → health page, metrics from real cluster, database stats

**Manual Testing**: Admin vs non-admin access, compare pod metrics with `kubectl top pods`, database stats accuracy, auto-refresh, favicon on browsers

## Security Considerations

**Access Control**: Server-side admin check (not just frontend), JWT identity verification, rate limiting

**Information Disclosure**: Metrics reveal infrastructure → admin-only, sanitize error messages

**RBAC**: Minimal permissions (get/list only), no write access, namespace-scoped

**Future**: Database-driven admin roles, audit logging, IP allowlist

## Performance Considerations

**K8s API**: <100ms queries, cache 5-10s, async parallel

**Database**: Cache collStats 30-60s, timeout expensive queries

**Frontend**: Lazy load, React Query caching, debounce auto-refresh

## Rollout Strategy

**Dev**: Local cluster → kubectl port-forward → verify metrics

**Test**: RBAC first → backend endpoints → frontend → real metrics-server

**Prod**: Feature flag `ADMIN_HEALTH_ENABLED=true`, low-traffic deploy, monitor logs

**Rollback**: Disable feature flag, return cached data, revert ServiceAccount

## Open Questions

1. **Icon Design**: Use stock icon or custom design?
   - **Decision**: Use simple stock finance icon (chart/graph), custom design later

2. **Metrics Retention**: Should we store historical metrics?
   - **Decision**: No for MVP, just real-time data. Add Prometheus later for history.

3. **Alert Thresholds**: When to show "warning" vs "critical" status?
   - **Decision**: Warning: >70% CPU/memory, Critical: >90%

4. **Multiple Admins**: How to add more admin users?
   - **Decision**: Hardcoded list for MVP, database field in Phase 2

## Dependencies

- **kubernetes**: Python client library (~10MB)
- **motor**: Already installed (MongoDB async driver)
- **React Query**: Already installed (frontend state management)

**Infrastructure**:
- metrics-server must be running in cluster (already enabled in AKS)
- RBAC must be enabled (already enabled)

## Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| metrics-server unavailable | High | Low | Return cached data + error message |
| Kubernetes RBAC misconfiguration | High | Medium | Test thoroughly in dev, have rollback ready |
| Database stats query slow | Medium | Medium | Add caching, timeout queries at 5s |
| Hardcoded admin username inflexible | Low | High | Document plan to migrate to DB field |
| Favicon not loading | Low | Low | Test across browsers, use fallback |

## References

- [Kubernetes Metrics API](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/)
- [MongoDB collStats](https://www.mongodb.com/docs/manual/reference/command/collStats/)
- [Favicon Best Practices](https://evilmartians.com/chronicles/how-to-favicon-in-2021-six-files-that-fit-most-needs)
- Backend auth: `backend/src/api/dependencies/auth_deps.py`
- Frontend auth: `frontend/src/hooks/useAuth.ts`

---

## Change Log

- **2025-10-08**: Initial draft - comprehensive admin health dashboard spec
