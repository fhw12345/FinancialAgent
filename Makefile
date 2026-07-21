# Financial Agent Development Makefile
# Following the coding guide requirements for fmt, test, lint commands

.PHONY: help dev build test test-e2e test-e2e-real test-e2e-uaw002 test-e2e-uaw003 test-e2e-uaw004 test-e2e-uaw005 test-e2e-uaw006 test-e2e-uaw007 test-e2e-uaw008 test-e2e-uaw009 test-e2e-uaw010 lint fmt clean up down logs copilot-reverse

# Default target
help:
	@echo "Financial Agent Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  dev          Start development environment with hot reload"
	@echo "  up           Start all services with Docker Compose"
	@echo "  down         Stop all services"
	@echo "  logs         View logs from all services"
	@echo "  copilot-reverse  Start ../copilot-bridge on port 8765"
	@echo ""
	@echo "Code Quality:"
	@echo "  fmt          Format code (backend: black+ruff, frontend: prettier)"
	@echo "  lint         Lint code (backend: ruff+mypy, frontend: eslint)"
	@echo "  test         Run all tests"
	@echo "  test-e2e     Run deterministic Playwright browser tests"
	@echo "  test-e2e-real Run real-stack Playwright browser tests"
	@echo "  test-e2e-uaw002 Run Mongo-authority restart E2E"
	@echo "  test-e2e-uaw003 Run Deep Research context E2E"
	@echo "  test-e2e-uaw004 Run Watchlist persistence E2E"
	@echo "  test-e2e-uaw005 Run Agent cancellation E2E"
	@echo "  test-e2e-uaw006 Run Honest streaming semantics E2E"
	@echo "  test-e2e-uaw007 Run Shared durable Run model E2E"
	@echo "  test-e2e-uaw008 Run Unified chat lifecycle E2E"
	@echo "  test-e2e-uaw009 Run Standard agent events E2E"
	@echo "  test-e2e-uaw010 Run Request idempotency E2E"
	@echo ""
	@echo "Building:"
	@echo "  build        Build Docker images"
	@echo "  clean        Clean up Docker resources"

# Development
dev: up
	@echo "🚀 Development environment started!"
	@echo "Frontend: http://localhost:3000"
	@echo "Backend API: http://localhost:8000"
	@echo "Backend Docs: http://localhost:8000/docs"

up:
	docker-compose up -d
	@echo "⏳ Waiting for services to be ready..."
	@sleep 10
	@echo "✅ Services should be ready!"

down:
	docker-compose down

logs:
	docker-compose logs -f

copilot-reverse:
	cd ../copilot-bridge && dotnet run --project src/CopilotBridge.Cli -- serve --port 8765

# Code Quality - Backend
fmt-backend:
	@echo "🎨 Formatting backend code..."
	cd backend && python -m black src/
	cd backend && python -m ruff check --fix src/
	@echo "✅ Backend formatting complete"

lint-backend:
	@echo "🔍 Linting backend code..."
	cd backend && python -m ruff check src/
	cd backend && python -m mypy src/
	@echo "✅ Backend linting complete"

test-backend:
	@echo "🧪 Running backend tests..."
	docker-compose exec backend /home/app/.local/bin/pytest tests/ --cov=src --cov-report=term-missing
	@echo "✅ Backend tests complete"

# Code Quality - Frontend
fmt-frontend:
	@echo "🎨 Formatting frontend code..."
	cd frontend && npm run lint:fix
	@echo "✅ Frontend formatting complete"

lint-frontend:
	@echo "🔍 Linting frontend code..."
	cd frontend && npm run lint
	cd frontend && npm run type-check
	@echo "✅ Frontend linting complete"

test-frontend:
	@echo "🧪 Running frontend tests..."
	cd frontend && npm run test
	@echo "✅ Frontend tests complete"

# Combined commands
fmt: fmt-backend fmt-frontend
	@echo "🎨 All code formatted!"

lint: lint-backend lint-frontend
	@echo "🔍 All code linted!"

test: test-backend test-frontend
	@echo "🧪 All tests completed!"

test-e2e:
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; npm run test:e2e"

test-e2e-real:
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; npm run test:e2e:real"

test-e2e-uaw002:
	docker compose --profile e2e up -d --build llm-e2e backend-e2e frontend-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 1 FLUSHDB
	docker compose --profile e2e restart backend-e2e
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-002:seed"
	docker compose --profile e2e restart backend-e2e
	docker compose --profile e2e run --rm e2e sh -c "until curl -fsS http://host.docker.internal:18081/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-002:resume"

test-e2e-uaw003:
	docker compose --profile e2e up -d --build llm-e2e backend-deep-e2e frontend-deep-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_deep_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 2 FLUSHDB
	docker compose --profile e2e restart backend-deep-e2e frontend-deep-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3002 e2e sh -c "until curl -fsS http://host.docker.internal:18083/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-003"

test-e2e-uaw004:
	docker compose --profile e2e up -d --build llm-e2e backend-watchlist-e2e
	docker compose --profile e2e build frontend-deep-e2e
	docker compose --profile e2e up -d frontend-watchlist-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_watchlist_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 3 FLUSHDB
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_watchlist_e2e").watchlist.insertOne({watchlist_id:"watch_uaw004_aapl",symbol:"AAPL",added_at:new Date("2026-07-17T05:00:00Z"),last_analyzed_at:null,notes:"UAW-004 persistence proof"})'
	docker compose --profile e2e restart backend-watchlist-e2e frontend-watchlist-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3003 e2e sh -c "until curl -fsS http://host.docker.internal:18084/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-004"

test-e2e-uaw005:
	docker compose --profile e2e up -d --build llm-e2e backend-cancel-e2e
	docker compose --profile e2e build frontend-deep-e2e
	docker compose --profile e2e up -d frontend-cancel-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_cancel_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 4 FLUSHDB
	docker compose --profile e2e restart backend-cancel-e2e frontend-cancel-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3004 e2e sh -c "until curl -fsS http://host.docker.internal:18085/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-005"

test-e2e-uaw006:
	docker compose --profile e2e up -d --build llm-e2e backend-streaming-e2e
	docker compose --profile e2e build frontend-deep-e2e
	docker compose --profile e2e up -d frontend-streaming-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_streaming_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 5 FLUSHDB
	docker compose --profile e2e restart backend-streaming-e2e frontend-streaming-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3005 e2e sh -c "until curl -fsS http://host.docker.internal:18086/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-006"

test-e2e-uaw007:
	docker compose --profile e2e up -d --build llm-e2e backend-run-e2e
	docker compose --profile e2e build frontend-deep-e2e
	docker compose --profile e2e up -d frontend-run-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_run_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 6 FLUSHDB
	docker compose --profile e2e restart backend-run-e2e frontend-run-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3006 e2e sh -c "until curl -fsS http://host.docker.internal:18087/api/health; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-007"

test-e2e-uaw008:
	docker compose --profile e2e up -d --build llm-e2e backend-lifecycle-e2e
	docker compose --profile e2e build frontend-deep-e2e
	docker compose --profile e2e up -d frontend-lifecycle-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_lifecycle_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 7 FLUSHDB
	docker compose --profile e2e restart backend-lifecycle-e2e frontend-lifecycle-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3007 e2e sh -c "until curl -fsS http://host.docker.internal:18088/api/health; do sleep 2; done; until curl -fsS http://host.docker.internal:3007; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-008"

test-e2e-uaw009:
	docker compose --profile e2e up -d --build llm-e2e backend-events-e2e
	docker compose --profile e2e build frontend-deep-e2e
	docker compose --profile e2e up -d frontend-events-e2e
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_events_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 8 FLUSHDB
	docker compose --profile e2e restart backend-events-e2e frontend-events-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3008 e2e sh -c "until curl -fsS http://host.docker.internal:18089/api/health; do sleep 2; done; until curl -fsS http://host.docker.internal:3008; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-009"

test-e2e-uaw010:
	docker compose exec mongodb mongosh --quiet --eval 'db.getSiblingDB("financial_agent_events_e2e").dropDatabase()'
	docker compose exec redis redis-cli -n 8 FLUSHDB
	docker compose --profile e2e restart backend-events-e2e frontend-events-e2e
	docker compose --profile e2e run --rm --no-deps -e PLAYWRIGHT_BASE_URL=http://host.docker.internal:3008 e2e sh -c "until curl -fsS http://host.docker.internal:18089/api/health; do sleep 2; done; until curl -fsS http://host.docker.internal:3008; do sleep 2; done; UPDATE_E2E_EVIDENCE=true npm run test:e2e:uaw-010"

# Building
build:
	@echo "🏗️ Building Docker images..."
	docker-compose build
	@echo "✅ Build complete"

# Cleanup
clean:
	@echo "🧹 Cleaning up Docker resources..."
	docker-compose down -v --remove-orphans
	docker system prune -f
	@echo "✅ Cleanup complete"

# Health checks
health:
	@echo "🏥 Checking service health..."
	@curl -s http://localhost:8000/api/health | python -m json.tool || echo "❌ Backend health check failed"
	@curl -s http://localhost:3000 > /dev/null && echo "✅ Frontend is responding" || echo "❌ Frontend health check failed"

# Database operations
db-shell:
	docker-compose exec mongodb mongosh financial_agent

redis-cli:
	docker-compose exec redis redis-cli

# Development utilities
install-backend:
	@echo "📦 Installing backend dependencies..."
	cd backend && pip install -e ".[dev]"

install-frontend:
	@echo "📦 Installing frontend dependencies..."
	cd frontend && npm install

install: install-backend install-frontend
	@echo "📦 All dependencies installed!"

# Git hooks setup
setup-hooks:
	@echo "🪝 Setting up git hooks..."
	cp scripts/pre-commit .git/hooks/pre-commit
	chmod +x .git/hooks/pre-commit
	@echo "✅ Git hooks installed"

backfill-translations:
	docker compose exec backend python -m scripts.backfill_translations --collection all
