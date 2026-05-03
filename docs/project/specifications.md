# Financial Agent - Project Specifications

## Executive Summary

**Project Goal**: Build a full-stack, cloud-native web application that provides on-demand Fibonacci and market structure analysis for financial symbols. The platform generates chart images and supplements them with AI-powered interpretations.

**Core Architecture**: Decoupled application with a Python backend, React frontend, NoSQL database, and multimodal AI model.

**Technology Ecosystem**: Hybrid cloud deployment on Azure (primary) and Alibaba Cloud (specialized services).

## Project Structure

```
financials/
├── README.md
├── CONTRIBUTING.md
├── LICENSE
├── Makefile
├── .editorconfig
├── .gitignore
├── .env.example
├── backend/
│   ├── pyproject.toml
│   ├── README.md
│   ├── src/
│   ├── tests/
│   │   ├── unit/
│   │   ├── api/
│   │   └── integration/
│   ├── scripts/
│   │   ├── dev_run.sh
│   │   └── lint.sh
│   └── Dockerfile
├── frontend/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── src/
├── docs/
│   ├── architecture/
│   ├── deployment/
│   ├── development/
│   └── project/
├── .pipeline/
│   ├── k8s/
│   │   ├── base/
│   │   └── overlays/
│   ├── workflows/
│   └── scripts/
├── .github/
│   └── workflows/
│       ├── backend-ci.yml
│       ├── frontend-ci.yml
│       ├── build-and-push-images.yml
│       └── deploy-ack.yml
└── tools/
    ├── schema/
    └── openapi/
```

## Backend Service

### Framework
- **Language**: Python 3.12
- **Framework**: FastAPI
- **Architecture**: Asynchronous, RESTful API

### API Endpoints
- `POST /api/charts/fibonacci`: Request Fibonacci chart generation
- `POST /api/chat`: Conversational AI interface
- `GET /api/market/search`: Symbol search with validation
- `GET /api/analysis/history`: User analysis history
- `GET /api/health`: Comprehensive system health check
- `GET /api/health/ready`: Kubernetes readiness probe
- `GET /api/health/live`: Kubernetes liveness probe

### Authentication
- **Method**: OAuth2 / OIDC Bearer JWTs
- **Provider**: Azure AD B2C (planned)
- **Scopes**: `charts:read`, `charts:write`, `analysis:read`

### Database (Data Persistence)
- **Primary**: Azure Cosmos DB (MongoDB API)
- **Purpose**: Analysis results, user requests, metadata
- **Features**: Multi-region, auto-scaling, encryption at rest

### Chat Message Storage
- **Service**: Alibaba Cloud Tablestore (planned)
- **Purpose**: Chat conversation history and messages
- **Features**: Time-series optimization, fast retrieval, automatic scaling

### Caching
- **Service**: Redis
  - Development: In-cluster Redis
  - Production: ApsaraDB for Redis
- **Purpose**: Cache external data sources (yfinance), reduce latency
- **TTL**: 1 hour for market data, 24 hours for fundamentals

### File Storage
- **Service**: Alibaba Cloud OSS (Object Storage Service)
- **Purpose**: Generated chart images
- **Access**: Temporary pre-signed URLs for secure client access
- **Features**: Multi-region replication, CDN integration

### Containerization
- **Technology**: Docker with multi-stage builds
- **Image Size**: Optimized for small, secure runtime
- **Registry**: Azure Container Registry (ACR)

## Frontend Application

### Framework
- **Library**: React 18
- **Language**: TypeScript 5.x
- **Build Tool**: Vite
- **Styling**: TailwindCSS

### Key Features
1. **Authentication Flow**
   - Secure login using OIDC Authorization Code + PKCE
   - Token refresh and session management
   - Role-based UI rendering

2. **Conversational Interface**
   - Modern chat UI with message history
   - Quick action buttons for common analyses
   - Symbol search with autocomplete
   - Timeframe selection

3. **Analysis Dashboard**
   - Chart visualization with AI interpretations
   - Historical analysis list
   - Filter and search capabilities
   - Export functionality

4. **User Experience**
   - Responsive design (mobile, tablet, desktop)
   - Loading states and error handling
   - Real-time updates via WebSocket (planned)
   - Accessibility compliance (WCAG 2.1)

### State Management
- **Library**: React Query (TanStack Query)
- **Features**:
  - Server state caching
  - Optimistic updates
  - Automatic refetching
  - Mutation state management

### Deployment
- **Build**: Static assets via Vite
- **Hosting**: Alibaba Cloud OSS (planned) or nginx in Kubernetes
- **CDN**: Alibaba Cloud CDN for global delivery
- **SSL**: Let's Encrypt via cert-manager

## AI & Advanced Analytics

### Service
- **Provider**: Alibaba Cloud Model Studio (Bailian)
- **API**: DashScope API
- **Region**: cn-hangzhou

### Model
- **Name**: Qwen-VL-Max (or latest Vision-Language model)
- **Type**: Multimodal (text + image)
- **Capabilities**: Chart interpretation, natural language understanding

### Use Cases

#### 1. Chart Interpretation
Backend sends generated chart image to Qwen-VL model for analysis:
```python
interpretation = await ai_service.interpret_chart(
    chart_url=chart_url,
    context={
        "symbol": "AAPL",
        "timeframe": "6mo",
        "analysis_type": "fibonacci",
        "key_levels": [150.0, 165.0, 180.0]
    }
)
```

#### 2. Natural Language Querying
Chat interface allows natural language requests:
- "Show me the 3-month chart for Tesla and highlight key support levels"
- "Analyze AAPL fibonacci retracements for the past 6 months"
- "What's the macro sentiment right now?"

#### 3. Automated Report Generation
Each analysis automatically includes AI-generated summary:
- Key observations
- Support/resistance levels
- Trend analysis
- Risk assessment
- Trading suggestions (informational only)

## Infrastructure & DevOps

### Cloud Provider
**Hybrid Cloud Strategy:**
- **Azure**: Primary platform (AKS, Cosmos DB, monitoring)
- **Alibaba Cloud**: Specialized services (AI, OSS)

### Compute
- **Service**: Azure Kubernetes Service (AKS)
- **Cluster**: FinancialAgent-AKS
- **Region**: Korea Central
- **Scaling**: Horizontal Pod Autoscaler (HPA) based on CPU
- **Node Count**: 1-3 nodes (auto-scaling)

### API Management
- **Service**: Nginx Ingress Controller
- **Features**:
  - Traffic routing
  - Rate limiting
  - SSL/TLS termination
  - Load balancing

### CI/CD
- **Platform**: GitHub Actions
- **Pipeline Stages**:
  1. **Lint & Test**: Run all quality checks
  2. **Build**: Create Docker images
  3. **Scan**: Security scanning with Trivy
  4. **Push**: Push to Azure Container Registry
  5. **Deploy Staging**: Automatic deployment to staging
  6. **Manual Approval**: Required for production
  7. **Deploy Production**: Progressive rollout
  8. **Smoke Tests**: Verify deployment health

### Observability

#### Logging
- **Format**: Structured JSON logs
- **Fields**: Correlation IDs, user context, timing
- **Aggregation**: Azure Monitor Log Analytics

#### Metrics
- **Export**: Prometheus format
- **Scraping**: Azure Monitor for Prometheus
- **Custom Metrics**: Request latency, error rates, analysis duration

#### Tracing
- **Service**: Langfuse (self-hosted) for agent execution
- **Coverage**: Complete agent workflow visibility
- **Integration**: Correlation with application logs

#### Alerting
- **Platform**: Azure Monitor Alerts
- **Conditions**:
  - High error rate (> 5% for 5 minutes)
  - Increased latency (p95 > 2s for 5 minutes)
  - Pod failures or restarts
  - Database connection issues
  - API quota approaching limits

## Financial Analysis Features

### Current CLI Capabilities (Being Transformed)

#### 1. Fibonacci Analysis
- Automatic swing point detection
- Retracement levels: 0%, 23.6%, 38.2%, 50%, 61.8%, 78.6%, 100%
- Extension levels: 127.2%, 161.8%, 261.8%
- Confidence scoring based on price action
- Multiple timeframe support

#### 2. Market Structure
- Swing high/low identification
- Trend detection and classification
- Support/resistance zones
- Breakout/breakdown analysis
- Volume confirmation

#### 3. Macro Analysis
- VIX sentiment (fear index)
- Sector rotation analysis
- Buffett Indicator (market cap to GDP)
- Treasury yield analysis
- Economic indicators integration

#### 4. Chart Generation
- Professional matplotlib visualizations
- Candlestick charts
- Volume bars
- Indicator overlays
- Annotation support

#### 5. Fundamentals
- Stock metrics (P/E, P/B, ROE, etc.)
- Valuation ratios
- Financial statement data
- Analyst ratings
- Dividend information

### Web Platform Enhancements

#### 1. Conversational Interface
- Natural language query processing
- Context-aware responses
- Multi-turn conversations
- Session persistence

#### 2. AI Chart Interpretation
- Automated chart analysis via Qwen-VL
- Pattern recognition
- Trend identification
- Risk assessment
- Trading insights

#### 3. Real-time Updates
- Live price data streaming (planned)
- Real-time indicator calculations
- Push notifications for alerts
- WebSocket integration

#### 4. User Management
- Multi-user support
- Role-based access control
- Analysis history tracking
- Saved preferences
- Watchlists

#### 5. Cloud Storage
- Chart images in Alibaba OSS
- Global CDN delivery
- Secure access via pre-signed URLs
- Automatic cleanup of old charts

## Security & Compliance

### Authentication & Authorization
- OAuth2/OIDC via Azure AD B2C
- JWT token validation
- Scope-based access control
- Session management with refresh tokens

### Data Security
- Encryption in transit (TLS 1.3)
- Encryption at rest (Cosmos DB, OSS)
- Secrets in Azure Key Vault
- No hardcoded credentials

### Network Security
- Azure CNI networking
- Network policies
- Private endpoints for databases
- WAF protection (planned)

### Compliance
- GDPR considerations (data retention, right to deletion)
- Financial data handling best practices
- Audit logging
- Access control policies

## Deployment Topology

### Development Environment
- **Local**: Docker Compose for infrastructure (MongoDB, Redis), native Python/Node.js for code
- **Cloud (Test)**: AKS test namespace (`financial-agent`)
- **Database**: Local MongoDB (dev) or Azure Cosmos DB (test)
- **Cache**: Local Redis (dev) or in-cluster Redis (test, non-persistent)
- **Authentication**: Bypass mode (local) or JWT with email verification (test)
- **Resources**: Minimal (1 replica per pod in test, cost optimization)

### Staging Environment
- **Platform**: AKS dedicated namespace
- **Database**: Cosmos DB (separate from production)
- **Cache**: Redis (development tier)
- **Authentication**: Azure AD B2C (test tenant)
- **Resources**: Production-like configuration

### Production Environment
- **Platform**: AKS multi-region (planned)
- **Database**: Cosmos DB (multi-region, auto-scaling)
- **Cache**: ApsaraDB for Redis (managed)
- **Authentication**: Azure AD B2C (production tenant)
- **Deployment**: Blue-green or canary
- **Monitoring**: Full observability stack

## Roadmap

### Phase 1: Foundation (Complete)
- ✅ Infrastructure setup (AKS, Cosmos DB, ACR)
- ✅ Walking skeleton (end-to-end connectivity)
- ✅ Basic health monitoring
- ✅ Docker Compose development environment

### Phase 2: Agent Core (In Progress)
- LangChain agent implementation
- Financial analysis tool integration
- Conversational interface
- State management with LangGraph
- Langfuse observability

### Phase 3: Production (Planned)
- Azure AD B2C authentication
- AI chart interpretation via Qwen-VL
- Cloud deployment automation
- Monitoring and alerting
- Performance optimization

### Phase 4: Scale (Future)
- Advanced analytics and insights
- Multi-user support with collaboration
- Real-time data streaming
- Mobile application
- Geographic distribution
- Advanced caching strategies
- Machine learning for pattern detection

## Success Metrics

### Technical Metrics
- API response time: p95 < 2s
- Chart generation time: < 5s
- Availability: 99.9% uptime
- Error rate: < 1%
- Test coverage: > 95%

### Business Metrics
- User engagement (analyses per user)
- Session duration
- Feature adoption rates
- User retention
- Chart sharing/export frequency

### Performance Metrics
- Concurrent users supported
- Requests per second capacity
- Database query performance
- Cache hit rate (> 80%)
- CDN cache hit rate (> 90%)
