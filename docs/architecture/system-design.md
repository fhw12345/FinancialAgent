# Financial Agent System Design

## Executive Summary

AI-Enhanced Financial Analysis Platform that provides on-demand Fibonacci and market structure analysis for financial symbols. The platform generates chart images and supplements them with AI-powered interpretations using a decoupled, cloud-native architecture.

## Overall Direction

The project transforms a sophisticated CLI financial analysis tool into a modern, cloud-native, AI-enhanced web application. The architecture is designed to be scalable, secure, and observable from the ground up, prioritizing managed services to reduce operational overhead while maintaining focus on core financial analysis features.

## Technology Stack

### Cloud Platform
**Hybrid Cloud Strategy**
- **Production Platform**: Alibaba Cloud
  - Container orchestration (ACK - Shanghai)
  - AI/LLM (Qwen-VL Model via DashScope)
  - Object Storage (OSS for charts)

- **Shared Services**: Microsoft Azure
  - Container Registry (ACR)
  - Secrets management (Key Vault)
  - Database (Cosmos DB with MongoDB API)

- **Test Platform**: Azure AKS (Planned)

> **Environment details**: See [CLAUDE.md](../../CLAUDE.md#-environment-rules)

### Backend
- **Framework**: Python 3.12 with FastAPI
- **Rationale**: High performance, asynchronous capabilities, automatic API documentation
- **Features**:
  - RESTful API endpoints
  - OAuth2/OIDC Bearer JWTs for authentication
  - Scope-based authorization
  - Automatic OpenAPI documentation

### Frontend
- **Framework**: React 18 with TypeScript 5.x
- **Build Tool**: Vite
- **Styling**: TailwindCSS
- **State Management**: React Query for server state
- **Features**:
  - Secure login flow using OIDC Authorization Code + PKCE
  - Conversational chat interface with quick actions
  - Chart visualization and AI-generated summaries
  - Historical request dashboard

### Compute & Orchestration
- **Platform**: Azure Kubernetes Service (AKS)
- **Container Runtime**: Docker
- **Node Configuration**: 3 nodes across 3 pools (agentpool, userpool, userpoolv2)
  - agentpool: 1 × Standard_D2ls_v5 (System mode, 2 vCPU, 4GB)
  - userpool: 1 × Standard_D2ls_v5 (User mode, 2 vCPU, 4GB)
  - userpoolv2: 1 × Standard_E2_v3 (User mode, 2 vCPU, 16GB, memory-optimized)
- **Deployment Pattern**: Separate pods for each service (frontend, backend, redis)
- **Rationale**:
  - Independent scaling (frontend: 3-5 replicas, backend: 2-3 replicas, redis: 1 replica)
  - Independent updates (update backend without frontend downtime)
  - Failure isolation (backend crash doesn't affect frontend)
  - Fine-grained resource allocation per service
- **Scaling**: Horizontal Pod Autoscaler (HPA) based on CPU load, autoscaler capped at max-count=1 per pool
- **Pod Distribution**: Kubernetes scheduler distributes pods across nodes based on resource requests
- **Features**:
  - Automated scaling per component (with cost guardrails)
  - Self-healing deployments
  - Zero-downtime rolling updates
  - Independent service lifecycle management

### Data Layer

#### Primary Database
- **Service**: Azure Cosmos DB (MongoDB API)
- **Rationale**: Flexible document-based structure ideal for complex analysis results
- **Usage**: Analysis results, user requests, metadata

#### Chat Storage
- **Service**: Alibaba Cloud Tablestore (planned)
- **Rationale**: Optimized for time-series data like chat messages
- **Features**: Automatic scaling, fast conversation thread retrieval

#### Caching
- **Service**: Redis (in-cluster for dev, ApsaraDB for Redis in production)
- **Purpose**: Distributed cache for external data sources (yfinance)
- **Benefits**: Reduced latency and API calls across horizontally scaled replicas

#### Object Storage
- **Service**: Alibaba Cloud OSS
- **Purpose**: Chart image storage
- **Access**: Temporary pre-signed URLs for secure client access

### AI & Analytics
- **Service**: Alibaba Cloud Model Studio (Bailian)
- **Model**: Qwen-VL-Max (multimodal vision-language model)
- **Agent Framework**: LangGraph SDK ReAct Agent
  - `create_react_agent` with autonomous tool chaining
  - Flexible, context-driven routing
  - Compressed tool results for efficiency
- **Use Cases**:
  1. Chart interpretation and analysis
  2. Natural language query processing with tool calling
  3. Automated report generation
  4. Autonomous financial analysis with multi-tool chaining

### Infrastructure & DevOps

#### API Management
- **Service**: Nginx Ingress Controller
- **Features**:
  - Traffic management
  - Rate limiting
  - SSL termination
  - Reverse proxy

#### CI/CD
- **Platform**: GitHub Actions
- **Pipeline Stages**:
  1. Lint, test, and build application code
  2. Build and scan Docker images (Trivy)
  3. Push to Azure Container Registry (ACR)
  4. Deploy to staging
  5. Manual approval for production
  6. Progressive rollout with health checks

#### Observability
- **Logging**: Structured JSON logs
- **Metrics**: Application performance monitoring
- **Tracing**: Langfuse (self-hosted) for agent execution traces and LLM observability
- **Monitoring**: Azure Monitor with custom dashboards
- **Alerting**: Automated alerts for critical conditions

## Architecture Patterns

### Walking Skeleton Methodology
1. **Milestone 1**: End-to-end connectivity (Frontend → API → DB → Cache)
2. **Milestone 2**: Authentication + core business logic
3. **Milestone 3+**: Layer features incrementally

### 12-Factor Agent Principles
See [Agent 12-Factors](agent-12-factors.md) for the complete philosophy and [Agent Architecture](agent-architecture.md) for implementation details.

## Financial Analysis Features

### Current CLI Capabilities
- **Fibonacci Analysis**: Retracement levels with confidence scoring
- **Market Structure**: Swing point detection and trend analysis
- **Macro Analysis**: VIX sentiment, sector rotation, Buffett Indicator
- **Chart Generation**: Professional matplotlib visualizations
- **Fundamentals**: Stock metrics and valuation data

### Web Platform Enhancements
- **Conversational Interface**: Natural language financial queries
- **AI Chart Interpretation**: Qwen-VL model for visual analysis
- **Real-time Updates**: Live data streaming and caching
- **User Management**: Authentication and session persistence
- **Cloud Storage**: Chart images with global CDN delivery

## Security & Compliance

### Authentication & Authorization
- **Current Implementation**: Local JWT-based authentication
  - Username/password with bcrypt hashing (cost factor 12)
  - Email verification for registration and password reset
  - JWT tokens (7-day expiry) signed with SECRET_KEY
  - Session management via localStorage
- **Planned Enhancements**:
  - Add OAuth2/OIDC providers (Microsoft, Google) for social login
  - Support multiple auth providers based on user region
  - Add MFA (TOTP) for enhanced security
  - Implement refresh tokens for better session management
- **Design Decision**: Separate pods architecture chosen over multi-container pods
  - Avoids OAuth complexity for MVP phase
  - Allows independent scaling and updates
  - Provides adequate security for initial user base (<10K users)

### Network Security
- HTTPS/TLS encryption (Let's Encrypt)
- Azure CNI networking
- Network policies
- VPN for cross-cloud communication

### Data Security
- Encryption at rest (Cosmos DB, OSS)
- Encryption in transit (TLS 1.3)
- Secrets management via Azure Key Vault
- External Secrets Operator for K8s integration

### Compliance
- No hardcoded secrets in manifests
- Audit logging
- RBAC with minimal permissions
- Signed container images

## Scalability & Performance

### Horizontal Scaling
- Stateless application design
- Kubernetes HPA for automatic scaling
- Load balancing via Nginx Ingress
- Distributed caching with Redis

### Performance Optimization
- CDN for static assets
- Redis caching for market data
- Async/await throughout backend
- Connection pooling for databases
- Image optimization for charts

### Cost Optimization
- Auto-scaling based on demand
- Managed services reduce operational overhead
- Development environment with minimal resources
- CDN reduces bandwidth costs

## Deployment Topology

### Pod Architecture (All Environments)
```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│  Frontend   │   │  Backend    │   │   Redis     │
│    Pod      │   │    Pod      │   │    Pod      │
│             │   │             │   │             │
│  Replicas:  │   │  Replicas:  │   │  Replicas:  │
│   3-5       │   │   2-3       │   │   1         │
└─────────────┘   └─────────────┘   └─────────────┘
      ↓                 ↓                  ↓
  Service           Service            Service
   (ClusterIP)       (ClusterIP)       (ClusterIP)
```

**Why Separate Pods?**
1. **Independent Scaling**: Frontend scales 3-5x during market hours, backend 2-3x for LLM load, Redis stays at 1
2. **Zero-Downtime Updates**: Update backend without restarting frontend/Redis
3. **Failure Isolation**: Backend crash doesn't affect frontend UI or Redis cache
4. **Resource Efficiency**: Fine-grained CPU/memory limits per service
5. **Monitoring**: Easy to identify which component is unhealthy

**Not Using Multi-Container Pods Because:**
- ❌ All containers restart when any one fails
- ❌ Can't scale components independently
- ❌ Updates require full pod restart (Redis cache lost)
- ❌ Resource limits shared across all containers

### Environments

| Environment | Platform | URL | Status |
|-------------|----------|-----|--------|
| **Local Dev** | Docker Compose | http://localhost:3000 | Active |
| **Test** | Azure AKS | http://localhost:3000 | Planned |
| **Prod** | Alibaba ACK (Shanghai) | http://localhost:3000 | Active |

> **Full environment configuration**: See [CLAUDE.md](../../CLAUDE.md#-environment-rules)

## Integration Points

### Cross-Cloud Integration
1. **Authentication Flow**: JWT → AKS → Services
2. **Data Flow**: Azure Cosmos DB ↔ Application ↔ Alibaba OSS
3. **AI Processing**: Application → Qwen-VL Model → Response
4. **Monitoring**: Azure Monitor + custom metrics from Alibaba services

### External APIs
- yfinance for market data
- Alibaba DashScope for AI inference
- Azure Cosmos DB for persistence
- Redis for caching

## Agent Architecture

The platform uses **LangGraph's SDK ReAct Agent** for autonomous financial analysis.

**Endpoint**: `/api/chat/stream-react`

**Approach**: LangGraph SDK-based with autonomous tool chaining

**Key Features**:
- Auto-loop pattern with `create_react_agent`
- LLM-driven tool selection and chaining
- Compressed tool results (99.5% size reduction)
- Built-in message history with `MemorySaver`
- ~300 lines of implementation code
- Flexible, context-driven routing

**Capabilities**:
- Autonomous multi-tool chaining (LLM decides sequence)
- Adapts to complex queries dynamically
- Compressed tool results reduce tokens by 99.5%
- Thread-based conversation isolation
- Streaming responses with Server-Sent Events

**See**: [Agent Architecture Details](agent-architecture.md) | [SDK ReAct Agent Feature Spec](../features/langgraph-sdk-react-agent.md)

**Current Deployment**: Production at http://localhost:3000 (ACK)

---

## Roadmap

### Phase 1: Foundation (✅ COMPLETED)
- ✅ Infrastructure setup and walking skeleton
- ✅ Basic health monitoring and logging
- ✅ End-to-end connectivity verification

### Phase 2: Agent Core (✅ COMPLETED)
- ✅ LangGraph SDK ReAct Agent implementation
  - Autonomous tool chaining with flexible routing
  - Compressed tool results (99.5% token reduction)
  - Built-in state management with MemorySaver
- ✅ Financial analysis tool integration
- ✅ Conversational interface with streaming responses
- ✅ Thread-based conversation persistence

### Phase 3: Production (🚧 IN PROGRESS)
- ✅ Authentication and authorization
- ✅ SDK ReAct Agent deployed to Test environment
- ⏳ Frontend integration for agent chat interface
- ⏳ AI chart interpretation
- ✅ Cloud deployment automation
- ✅ Monitoring and alerting (Langfuse)

### Phase 4: Scale (PLANNED)
- Advanced analytics and insights
- Multi-user support
- Performance optimization
- Geographic distribution
